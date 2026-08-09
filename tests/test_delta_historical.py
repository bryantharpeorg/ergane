"""US2-S6: delta derivation subtracts historical pre-queue merges.

The `landed_facts` recognizer is tested in `tests/test_landed.py`; this file
closes the loop by proving that `derive_delta` (and therefore the activity and
CLI that wrap it) actually emits only the stories that are genuinely absent
when the baseline contains historical landings.

A string-level recognizer test would keep passing even if `_git_log_subjects`
gained `--no-merges`; this test builds real git merge commits and runs the
the full delta path end to end.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Callable

import pytest

from factory.workgraph.delta import derive_delta, fingerprint_for
from factory.workgraph.landed import landed_facts

DEFAULT_BRANCH = "main"
EPIC_ID = "006-interpreter-hardening"

#: Fixture identity and timestamps are fixed so commit hashes are reproducible.
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


def _merge(repo: Path, source_branch: str, *, env: dict[str, str], subject: str) -> str:
    """Merge `source_branch` into the current branch with the requested subject."""
    _git(repo, "merge", "--no-ff", "--no-edit", source_branch, env=env)
    _git(repo, "commit", "--amend", "--no-edit", "-m", subject, env=env)
    return _git(repo, "rev-parse", "HEAD", env=env).strip()


def _spec_text() -> str:
    """A minimal 006-like spec with five independent stories."""
    return (
        "---\n"
        "state: ready\n"
        "---\n"
        "# Feature\n\n"
        "## Requirements *(mandatory)*\n\n"
        "- **FR-001**: The system MUST do one thing.\n"
        "- **FR-002**: The system MUST do another thing.\n"
        "- **FR-003**: The system MUST do a third thing.\n"
        "- **FR-004**: The system MUST do a fourth thing.\n"
        "- **FR-005**: The system MUST do a fifth thing.\n\n"
        "### User Story 1 - Heartbeat cost (Priority: P1)\n\n"
        "As the operator, I want bounded history cost.\n\n"
        "**Acceptance Scenarios**:\n"
        "1. **Given** a long attempt, **When** it completes, **Then** history is bounded.\n\n"
        "### User Story 2 - Preflight (Priority: P2)\n\n"
        "As the operator, I want misconfiguration refused at start.\n\n"
        "**Acceptance Scenarios**:\n"
        "1. **Given** a bad registry, **When** start runs, **Then** it refuses.\n\n"
        "### User Story 3 - Orphan recovery (Priority: P3)\n\n"
        "As the operator, I want killed epics to restart.\n\n"
        "**Acceptance Scenarios**:\n"
        "1. **Given** an orphan key, **When** the epic restarts, **Then** it dispatches.\n\n"
        "### User Story 4 - Transient survival (Priority: P3)\n\n"
        "As the operator, I want brief hiccups to not lose work.\n\n"
        "**Acceptance Scenarios**:\n"
        "1. **Given** a transient outage, **When** it passes, **Then** work survives.\n\n"
        "### User Story 5 - Status honesty (Priority: P3)\n\n"
        "As the operator, I want status to report the real state.\n\n"
        "**Acceptance Scenarios**:\n"
        "1. **Given** a closed workflow, **When** status runs, **Then** it says so.\n\n"
        "## Work Graph\n\n"
        "```yaml\n"
        "US1:\n"
        "  depends_on: []\n"
        "  implements: [FR-001]\n"
        "US2:\n"
        "  depends_on: []\n"
        "  implements: [FR-002]\n"
        "US3:\n"
        "  depends_on: []\n"
        "  implements: [FR-003]\n"
        "US4:\n"
        "  depends_on: []\n"
        "  implements: [FR-004]\n"
        "US5:\n"
        "  depends_on: []\n"
        "  implements: [FR-005]\n"
        "```\n"
    )


@pytest.fixture
def historical_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fixture repo with 006's three pre-queue merges and two unlanded stories."""
    empty_home = tmp_path / "empty-home"
    empty_home.mkdir()
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
    (specs_dir / "spec.md").write_text(_spec_text(), encoding="utf-8")
    # Declare the landing branch so the reader scans the right history (US1).
    (repo / "factory.yaml").write_text(
        "version: 1\n"
        "runtime: python:3.11-bookworm\n"
        "gates:\n"
        "  test: uv run pytest -q\n"
        "landing_branch: ergane-buildout\n",
        encoding="utf-8",
    )
    _git(repo, "add", "-A", env=env)
    _commit(repo, "fixture skeleton", env=env)

    # Create the landing branch and merge each of the three historical node branches.
    _git(repo, "checkout", "--quiet", "-b", "ergane-buildout", env=env)
    for number in (1, 2, 5):
        branch = f"factory/{EPIC_ID}/us{number}"
        _git(repo, "checkout", "--quiet", "-b", branch, env=env)
        (specs_dir / f"us{number}.txt").write_text(f"us{number}\n", encoding="utf-8")
        _git(repo, "add", "-A", env=env)
        _commit(repo, f"factory/{EPIC_ID}/us{number}: implement US{number}", env=env)
        _git(repo, "checkout", "--quiet", "ergane-buildout", env=env)
        _merge(
            repo,
            branch,
            env=env,
            subject=f"Merge branch 'factory/{EPIC_ID}/us{number}' into ergane-buildout",
        )

    return repo


def _build_baseline(repo: Path, spec_dir: str, default_branch: str) -> dict:
    """Build a delta baseline from the landed facts of `repo`."""
    facts = landed_facts(repo, spec_dir, default_branch=default_branch)
    baseline: dict = {}
    spec_text = _spec_text()
    for story_key, fact in facts.items():
        pinned = fingerprint_for(spec_text, story_key)
        baseline[story_key] = {"commit": fact.commit, "fingerprint": pinned}
    return baseline


def test_delta_against_006_historical_merges(historical_repo: Path) -> None:
    """US2-S6: 006's three pre-queue merges leave only US3 and US4 in the delta.

    The baseline is read from the declared landing branch (`ergane-buildout`),
    not from `main`.  Historical landings for US1, US2 and US5 are subtracted,
    so the emitted graph contains exactly the two stories that never landed.
    """
    baseline = _build_baseline(historical_repo, EPIC_ID, default_branch="ergane-buildout")

    # Verify the baseline itself carries the three historical landings.
    assert set(baseline) == {"US1", "US2", "US5"}

    result = derive_delta(
        _spec_text(),
        baseline=baseline,
        epic_id=EPIC_ID,
        feature=EPIC_ID,
        specs_root="specs",
        target_repo="/home/admin/code/ergane-006-target",
    )

    assert {node.story_key for node in result.graph.nodes} == {"US3", "US4"}
