"""US4: drift detection degrades instead of dying when baselines are missing.

The roadmap's `drift_for_spec` activity compares pinned fingerprints against the
current spec text.  A story whose landing commit predates the spec file's first
commit has no baseline; the activity must skip such facts rather than propagate
the `git show` failure.  A drift-activity failure anywhere in the workflow must
be caught, reported once through the roadmap's existing failure-notice path, and
must not kill the run.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Callable

import pytest
from temporalio.testing import WorkflowEnvironment

from factory.activities.roadmap_activities import DriftInput, drift_for_spec
from factory.roadmap.models import SpecState
from factory.roadmap.workflow import RoadmapStatus
from factory.workgraph.landed import Fingerprint, WorktreeError, fingerprint

from tests.test_roadmap_failure_notifications import (
    NotificationRecorder,
    env,  # noqa: F401
    run_roadmap_with_notifications,
)
from tests.test_roadmap_scheduler import RoadmapWorld, build_corpus, _status_of

DEFAULT_BRANCH = "main"
EPIC_ID = "010-manifest-self-extension"

_FIXTURE_IDENTITY = ("Ergane Fixture", "fixture@ergane.invalid")
_FIXTURE_TIMESTAMP = "2026-01-01T00:00:00+00:00"


def _git_env(home: Path) -> dict[str, str]:
    """A git environment that ignores the host operator's configuration."""
    name, email = _FIXTURE_IDENTITY
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(home),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": name,
        "GIT_AUTHOR_EMAIL": email,
        "GIT_AUTHOR_DATE": _FIXTURE_TIMESTAMP,
        "GIT_COMMITTER_NAME": name,
        "GIT_COMMITTER_EMAIL": email,
        "GIT_COMMITTER_DATE": _FIXTURE_TIMESTAMP,
        "GIT_TERMINAL_PROMPT": "0",
    }


def _git(repo: Path, *args: str, env: dict[str, str]) -> str:
    """Run one git command in `repo`, returning stdout; raise on failure."""
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    return completed.stdout


def _commit(repo: Path, subject: str, *, env: dict[str, str], allow_empty: bool = False) -> str:
    """Commit and return the full sha of the new commit."""
    args = ["commit", "--quiet", "-m", subject]
    if allow_empty:
        args.append("--allow-empty")
    _git(repo, *args, env=env)
    return _git(repo, "rev-parse", "HEAD", env=env).strip()


@pytest.fixture
def repo_builder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., Path]:
    """Factory that builds a fresh git repo with an optional initial spec file."""
    empty_home = tmp_path / "empty-home"
    empty_home.mkdir()

    def build(*, with_spec: bool = False) -> Path:
        repo = tmp_path / "repo"
        repo.mkdir()
        env = _git_env(empty_home)
        for key in (
            "GIT_AUTHOR_NAME",
            "GIT_AUTHOR_EMAIL",
            "GIT_COMMITTER_NAME",
            "GIT_COMMITTER_EMAIL",
        ):
            monkeypatch.delenv(key, raising=False)
        _git(repo, "init", "-b", DEFAULT_BRANCH, "--quiet", env=env)
        specs_dir = repo / "specs" / EPIC_ID
        specs_dir.mkdir(parents=True)
        if with_spec:
            (specs_dir / "spec.md").write_text(_spec(stories=["US1"]), encoding="utf-8")
            _git(repo, "add", "-A", env=env)
            _commit(repo, "fixture skeleton", env=env)
        return repo

    return build


def _spec(*, stories: list[str], changed_us2: bool = False) -> str:
    """A minimal spec with the requested stories and a Work Graph block."""
    body = "---\nstate: landed\n---\n\n# Feature\n\n"
    body += "## Requirements *(mandatory)*\n\n- **FR-001**: The system MUST do one thing.\n\n"
    for number, title in enumerate(stories, start=1):
        scenario = "it works"
        if changed_us2 and title == "US2":
            scenario = "it works differently"
        body += (
            f"### User Story {number} - {title} (Priority: P{number})\n\n"
            "As the operator, I want this.\n\n"
            "**Acceptance Scenarios**:\n"
            f"1. **Given** a thing, **When** I act, **Then** {scenario}.\n\n"
        )
    body += "## Work Graph\n\n```yaml\n"
    for title in stories:
        body += f"{title}:\n  depends_on: []\n  implements: [FR-001]\n"
    body += "```\n"
    return body


async def test_fingerprint_missing_spec_file_returns_no_baseline_sentinel(
    repo_builder: Callable[..., Path],
) -> None:
    """US1-S1 / FR-001: a spec file missing at the landing commit yields a
    distinguished no-baseline result; nothing raises."""
    repo = repo_builder(with_spec=False)
    env = _git_env(Path(os.environ.get("HOME", "/tmp")))

    # Landing commit predates the spec file.
    landing = _commit(
        repo, f"{EPIC_ID}/us1: US1 (#1)", env=env, allow_empty=True
    )

    # Now commit the spec file.
    spec_path = repo / "specs" / EPIC_ID / "spec.md"
    spec_path.write_text(_spec(stories=["US1"]), encoding="utf-8")
    _git(repo, "add", "-A", env=env)
    _commit(repo, "add spec.md", env=env)

    fp = fingerprint(repo, landing, EPIC_ID, "US1")
    assert isinstance(fp, Fingerprint)
    assert fp.story_key == "US1"
    assert fp.revision == landing
    assert fp.digest is None


async def test_drift_for_spec_returns_not_drifted_when_all_facts_lack_baselines(
    repo_builder: Callable[..., Path],
) -> None:
    """US1-S2 / FR-002: a spec all of whose landed facts lack baselines is not
    drifted."""
    repo = repo_builder(with_spec=False)
    env = _git_env(Path(os.environ.get("HOME", "/tmp")))

    _commit(repo, f"{EPIC_ID}/us1: US1 (#1)", env=env, allow_empty=True)
    _commit(repo, f"{EPIC_ID}/us2: US2 (#2)", env=env, allow_empty=True)

    spec_path = repo / "specs" / EPIC_ID / "spec.md"
    spec_path.write_text(_spec(stories=["US1", "US2"]), encoding="utf-8")
    _git(repo, "add", "-A", env=env)
    _commit(repo, "add spec.md", env=env)

    current_text = spec_path.read_text(encoding="utf-8")
    result = await drift_for_spec(
        DriftInput(target_repo=str(repo), spec_dir=EPIC_ID, spec_text=current_text)
    )
    assert result is False


async def test_drift_for_spec_returns_drifted_when_one_comparable_fact_differs(
    repo_builder: Callable[..., Path],
) -> None:
    """US1-S3 / FR-002: a missing baseline never masks real drift on facts that
    can be compared."""
    repo = repo_builder(with_spec=False)
    env = _git_env(Path(os.environ.get("HOME", "/tmp")))

    # US1 lands before the spec file exists (no baseline).
    _commit(repo, f"{EPIC_ID}/us1: US1 (#1)", env=env, allow_empty=True)

    # US2 lands after the spec file exists (baseline exists).
    spec_path = repo / "specs" / EPIC_ID / "spec.md"
    spec_path.write_text(_spec(stories=["US1", "US2"]), encoding="utf-8")
    _git(repo, "add", "-A", env=env)
    _commit(repo, "add spec.md", env=env)
    _commit(repo, f"{EPIC_ID}/us2: US2 (#2)", env=env, allow_empty=True)

    # Current text changes US2's scenario relative to its pinned baseline.
    current_text = _spec(stories=["US1", "US2"], changed_us2=True)

    result = await drift_for_spec(
        DriftInput(target_repo=str(repo), spec_dir=EPIC_ID, spec_text=current_text)
    )
    assert result is True


async def test_fingerprint_still_refuses_unreachable_commit(
    repo_builder: Callable[..., Path],
) -> None:
    """FR-001 guard: a missing file is tolerated; an unreachable commit is not."""
    repo = repo_builder(with_spec=True)
    env = _git_env(Path(os.environ.get("HOME", "/tmp")))

    with pytest.raises(WorktreeError):
        fingerprint(repo, "deadbeef" * 4, EPIC_ID, "US1")


#: The verbatim error the scripted drift seam raises in the workflow scenario.
SCRIPTED_DRIFT_ERROR = "scripted drift failure"


async def test_drift_activity_failure_is_caught_and_reported_once(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """US1-S4 / FR-003: a failing `drift_for_spec` activity does not kill the
    roadmap run. The spec is rendered not-drifted for the pass, dispatch proceeds,
    and exactly one roadmap failure notice names the spec dir and the error
    verbatim."""
    specs_root = build_corpus(
        tmp_path,
        {
            "001-alpha": dict(state=SpecState.LANDED),
            "002-bravo": dict(state=SpecState.READY),
        },
    )

    def _raising_drift(request: Any) -> bool:
        raise RuntimeError(SCRIPTED_DRIFT_ERROR)

    world = RoadmapWorld(drift_runner=_raising_drift)
    recorder = NotificationRecorder()

    async with run_roadmap_with_notifications(
        env, world, str(specs_root), recorder
    ) as handle:
        status = await handle.result()

    # The run survived and dispatched bravo.
    alpha = _status_of(status, "001-alpha")
    assert alpha.drifted is False
    bravo = _status_of(status, "002-bravo")
    assert bravo.landed is True

    # Exactly one roadmap failure notice, naming the spec and the verbatim error.
    failure_calls = [
        call for call in recorder.calls if "drift_for_spec" in call.message
    ]
    assert len(failure_calls) == 1, recorder.calls
    notice = failure_calls[0]
    assert "001-alpha" in notice.message
    assert SCRIPTED_DRIFT_ERROR in notice.message
