"""US4: the roadmap reconciles instead of ignoring (FR-009/010/011, SC-005).

The roadmap renders a landed spec whose story fingerprints drifted from their
landing baseline as `amended` — a read-only computed state distinct from
`landed` and from `ready` — and does not dispatch it until the operator flips
the state to `ready`. With scripted children, a re-readied partially-landed spec
dispatches exactly its computed remainder, an amended-then-readied spec dispatches
only its delta, and a fresh spec's dispatched graph is byte-compatible with the
pre-delta path.

Drift facts reach the workflow through the same injected resolver seam that
carries observed-landed facts for readiness, or through a dedicated activity —
git reads never happen inside workflow code.

Written before `factory.roadmap.models` carries drift/amended rendering and before
`derive_spec` calls `derive_delta`: every test here fails until US4 lands.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, AsyncIterator, Callable

import pytest
from temporalio.testing import WorkflowEnvironment

from factory.roadmap.models import (
    SpecState,
    compute_readiness,
    read_roadmap,
)
from factory.workgraph.models import WorkGraph

#: Fixture identity and timestamps are fixed so commit hashes are reproducible.
_FIXTURE_IDENTITY = ("Ergane Fixture", "fixture@ergane.invalid")
_FIXTURE_TIMESTAMP = "2026-01-01T00:00:00+00:00"

DEFAULT_BRANCH = "main"

TARGET_REPO = "/srv/factory/targets/library"


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


def _commit(
    repo: Path,
    subject: str,
    *,
    env: dict[str, str],
    body: str = "",
    allow_empty: bool = False,
) -> str:
    """Commit and return the full sha of the new commit."""
    message = subject if not body else f"{subject}\n\n{body}"
    args = ["commit", "--quiet", "-m", message]
    if allow_empty:
        args.append("--allow-empty")
    _git(repo, *args, env=env)
    return _git(repo, "rev-parse", "HEAD", env=env).strip()


@pytest.fixture
def repo_builder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., Path]:
    """Factory that builds a fresh git repo with a spec under `specs/<spec_dir>/`."""
    empty_home = tmp_path / "empty-home"
    empty_home.mkdir()

    def build(spec_dir: str, spec_text: str, *, default_branch: str = DEFAULT_BRANCH) -> Path:
        repo = tmp_path / f"repo-{spec_dir}"
        if repo.exists():
            shutil.rmtree(repo)
        repo.mkdir()
        env = _git_env(empty_home)
        for key in (
            "GIT_AUTHOR_NAME",
            "GIT_AUTHOR_EMAIL",
            "GIT_COMMITTER_NAME",
            "GIT_COMMITTER_EMAIL",
        ):
            monkeypatch.delenv(key, raising=False)
        _git(repo, "init", "-b", default_branch, "--quiet", env=env)
        specs_dir = repo / "specs" / spec_dir
        specs_dir.mkdir(parents=True)
        (specs_dir / "spec.md").write_text(spec_text, encoding="utf-8")
        _git(repo, "add", "-A", env=env)
        _commit(repo, "fixture skeleton", env=env)
        return repo

    return build


def _spec_text(
    *,
    state: str,
    stories: list[str],
    work_graph: str,
    depends_on_landed: list[str] | None = None,
) -> str:
    """A minimal Spec Kit feature spec."""
    lines = ["---", f"state: {state}"]
    if depends_on_landed:
        lines.append(f"depends_on_landed: {depends_on_landed}")
    lines.append("---")
    lines.append("")
    lines.append("# Feature")
    lines.append("")
    lines.append("## Requirements *(mandatory)*")
    lines.append("")
    lines.append("- **FR-001**: The system MUST do one thing.")
    lines.append("- **FR-002**: The system MUST do another thing.")
    lines.append("")
    for number, title in enumerate(stories, start=1):
        lines.append(
            f"### User Story {number} - {title} (Priority: P{number})\n\n"
            "As the operator, I want this.\n\n"
            "**Acceptance Scenarios**:\n"
            "1. **Given** a thing, **When** I act, **Then** it works.\n\n"
        )
    lines.append("## Work Graph")
    lines.append("")
    lines.append("```yaml")
    lines.append(work_graph)
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    """Temporal with a clock the test owns — the roadmap scheduler fixture pattern."""
    from tests.roadmap_script import _SCRIPT

    environment = await WorkflowEnvironment.start_time_skipping()
    _SCRIPT.statuses = {}
    _SCRIPT.on_dispatch = None
    _SCRIPT.on_complete = None
    _SCRIPT.hold = set()
    try:
        yield environment
    finally:
        await environment.shutdown()
        _SCRIPT.statuses = {}
        _SCRIPT.on_dispatch = None
        _SCRIPT.on_complete = None
        _SCRIPT.hold = set()


def _landed_spec_with_one_story(spec_dir: str = "016-delta-derivation") -> str:
    """A landed spec with one story, no dependencies."""
    return _spec_text(
        state="landed",
        stories=["US1"],
        work_graph="US1:\n  depends_on: []\n  implements: [FR-001]\n",
    )


# --- render: amended state ----------------------------------------------------


def _amended_resolver() -> Any:
    """Resolver that says the spec is landed and drifted, the US4 seam.

    Drift is a separate resolver (`drifted_for`) in `compute_readiness`, so this
    resolver carries only the observed-landed fact. The paired drift resolver
    is `_drifted_resolver`.
    """

    def resolve(spec_dir: str) -> Any:
        if spec_dir == "016-delta-derivation":
            return {"landed": True, "kind": "observed"}
        return None

    return resolve


def _drifted_resolver() -> Any:
    """Resolver that says the US4 spec has drifted from its landing baseline."""

    def resolve(spec_dir: str) -> bool:
        return spec_dir == "016-delta-derivation"

    return resolve


def test_render_marks_landed_spec_with_drifted_fingerprints_as_amended(
    repo_builder: Callable[..., Path], tmp_path: Path
) -> None:
    """FR-009 / acceptance 1: a landed spec whose fingerprints drifted renders as
    `amended`, distinct from `landed` and `ready`, and computed read-only."""
    spec_dir = "016-delta-derivation"
    repo = repo_builder(spec_dir, _landed_spec_with_one_story(spec_dir))
    git_env = _git_env(Path(os.environ.get("HOME", "/tmp")))
    # Land the one story so the baseline exists.
    _commit(
        repo,
        f"{spec_dir}/us1: US1 (#1)",
        env=git_env,
        allow_empty=True,
    )
    # Amend the spec in the working corpus (not the repo history yet — the drift
    # is detected against the corpus, not the target repo history in this render test).
    specs_root = tmp_path / "specs"
    specs_root.mkdir(parents=True)
    spec_path = specs_root / spec_dir / "spec.md"
    spec_path.parent.mkdir(parents=True)
    amended_text = _landed_spec_with_one_story(spec_dir).replace(
        "**Then** it works.", "**Then** it works differently."
    )
    spec_path.write_text(amended_text, encoding="utf-8")

    roadmap = read_roadmap(str(specs_root))
    ready = compute_readiness(
        roadmap, landed_for=_amended_resolver(), drifted_for=_drifted_resolver()
    )

    spec = ready.spec(spec_dir)
    # The declared frontmatter state is still `landed`; the computed rendered state
    # for a drifted landed spec is `amended`.
    assert spec.state is SpecState.LANDED
    assert spec.rendered_state == "amended"
    assert spec.dispatchable is False

    # Render the amended state visibly. The offline render cannot shell git, so
    # it relies on the injected drift resolver; here we patch the CLI resolver to
    # report drift for this spec so the render matches the computed readiness.
    from factory.roadmap import cli as roadmap_cli

    original_resolver = roadmap_cli._cli_drift_resolver

    def _drifted_cli_resolver(specs_root: str):
        def resolve(spec_dir: str) -> bool:
            return spec_dir == "016-delta-derivation"
        return resolve

    roadmap_cli._cli_drift_resolver = _drifted_cli_resolver
    try:
        captured = _invoke_render(str(specs_root))
    finally:
        roadmap_cli._cli_drift_resolver = original_resolver
    assert spec_dir in captured.out
    assert "amended" in captured.out


def test_amended_spec_does_not_dispatch_until_ready(
    repo_builder: Callable[..., Path], tmp_path: Path
) -> None:
    """FR-009 / acceptance 1: an amended spec is not dispatchable; it dispatches
    only after `state` flips to `ready`."""
    spec_dir = "016-delta-derivation"
    repo = repo_builder(spec_dir, _landed_spec_with_one_story(spec_dir))
    git_env = _git_env(Path(os.environ.get("HOME", "/tmp")))
    _commit(repo, f"{spec_dir}/us1: US1 (#1)", env=git_env, allow_empty=True)

    specs_root = tmp_path / "specs"
    spec_path = specs_root / spec_dir / "spec.md"
    spec_path.parent.mkdir(parents=True)
    amended_text = _landed_spec_with_one_story(spec_dir).replace(
        "**Then** it works.", "**Then** it works differently."
    )
    spec_path.write_text(amended_text, encoding="utf-8")

    roadmap = read_roadmap(str(specs_root))
    ready = compute_readiness(
        roadmap, landed_for=_amended_resolver(), drifted_for=_drifted_resolver()
    )
    spec = ready.spec(spec_dir)
    assert spec.rendered_state == "amended"
    assert spec.dispatchable is False

    # Flip to ready in the corpus.
    readied_text = amended_text.replace("state: landed", "state: ready")
    spec_path.write_text(readied_text, encoding="utf-8")
    roadmap = read_roadmap(str(specs_root))
    ready = compute_readiness(
        roadmap, landed_for=_amended_resolver(), drifted_for=_drifted_resolver()
    )
    spec = ready.spec(spec_dir)
    assert spec.state is SpecState.READY
    assert spec.rendered_state == "ready"
    assert spec.dispatchable is True


def _invoke_render(specs_root: str) -> Any:
    """Run the roadmap render CLI and return a simple capture object."""
    from factory.roadmap.cli import main

    class Capture:
        def __init__(self, code: int, out: str, err: str) -> None:
            self.code = code
            self.out = out
            self.err = err

    old_stdout = sys.stdout
    old_stderr = sys.stderr
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    try:
        sys.stdout = stdout_buf
        sys.stderr = stderr_buf
        try:
            from factory.roadmap.cli import main

            code = main(["render", specs_root])
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
    return Capture(code, stdout_buf.getvalue(), stderr_buf.getvalue())


# --- scheduler: scripted children + delta dispatch ------------------------------


async def test_re_readied_partially_landed_spec_dispatches_only_remainder(
    env: WorkflowEnvironment, tmp_path: Path, repo_builder: Callable[..., Path]
) -> None:
    """FR-010 / acceptance 3: a spec whose epic closed with some stories landed and
    some not, after being flipped to `ready`, dispatches only its computed remainder
    under the existing reuse-on-closed id convention."""
    from factory.workgraph.delta import derive_delta, fingerprint_for
    from tests.test_roadmap_scheduler import RoadmapWorld, run_to_completion

    spec_dir = "016-delta-derivation"
    base_text = _spec_text(
        state="landed",
        stories=["US1", "US2"],
        work_graph=(
            "US1:\n  depends_on: []\n  implements: [FR-001]\n"
            "US2:\n  depends_on: [US1]\n  implements: [FR-002]\n"
        ),
    )
    repo = repo_builder(spec_dir, base_text)
    git_env = _git_env(Path(os.environ.get("HOME", "/tmp")))
    us1_commit = _commit(repo, f"{spec_dir}/us1: US1 (#1)", env=git_env, allow_empty=True)

    specs_root = tmp_path / "specs"
    spec_path = specs_root / spec_dir / "spec.md"
    spec_path.parent.mkdir(parents=True)
    ready_text = base_text.replace("state: landed", "state: ready")
    spec_path.write_text(ready_text, encoding="utf-8")

    baseline = {
        "US1": {
            "commit": us1_commit,
            "fingerprint": fingerprint_for(ready_text, "US1"),
        }
    }
    expected = derive_delta(
        ready_text,
        baseline=baseline,
        epic_id=spec_dir,
        feature=spec_dir,
        specs_root=str(specs_root),
        target_repo=TARGET_REPO,
    )
    assert {n.story_key for n in expected.graph.nodes} == {"US2"}

    def _derive_delta(request) -> Any:
        from factory.workgraph.delta import derive_delta

        return derive_delta(
            request.spec_text,
            baseline=baseline,
            epic_id=request.epic_id,
            feature=request.feature,
            specs_root=request.specs_root,
            target_repo=request.target_repo,
        ).graph

    world = RoadmapWorld(derive_runner=_derive_delta)
    child_starts: list[Any] = []
    status = await run_to_completion(
        env,
        world,
        str(specs_root),
        child_starts=child_starts,
    )

    assert len(child_starts) == 1
    start = child_starts[0]
    assert start.id == f"epic-{spec_dir}"
    assert "ALLOW_DUPLICATE" in start.id_reuse_policy
    dispatched_graph: WorkGraph = start.args[0].graph
    assert dispatched_graph == expected.graph
    assert _status_of(status, spec_dir).landed is True


async def test_amended_then_readied_spec_dispatches_only_delta(
    env: WorkflowEnvironment, tmp_path: Path, repo_builder: Callable[..., Path]
) -> None:
    """FR-010 / acceptance 2: an amended landed spec, after being flipped to `ready`,
    dispatches only the delta (reopened US1) under the reuse-on-closed id convention."""
    from factory.workgraph.delta import derive_delta, fingerprint_for
    from tests.test_roadmap_scheduler import RoadmapWorld, run_to_completion

    spec_dir = "016-delta-derivation"
    base_text = _landed_spec_with_one_story(spec_dir)
    repo = repo_builder(spec_dir, base_text)
    git_env = _git_env(Path(os.environ.get("HOME", "/tmp")))
    us1_commit = _commit(repo, f"{spec_dir}/us1: US1 (#1)", env=git_env, allow_empty=True)

    specs_root = tmp_path / "specs"
    spec_path = specs_root / spec_dir / "spec.md"
    spec_path.parent.mkdir(parents=True)
    amended_text = base_text.replace(
        "**Then** it works.", "**Then** it works differently."
    ).replace("state: landed", "state: ready")
    spec_path.write_text(amended_text, encoding="utf-8")

    baseline = {
        "US1": {
            "commit": us1_commit,
            "fingerprint": fingerprint_for(base_text, "US1"),
        }
    }
    expected = derive_delta(
        amended_text,
        baseline=baseline,
        epic_id=spec_dir,
        feature=spec_dir,
        specs_root=str(specs_root),
        target_repo=TARGET_REPO,
    )
    assert {n.story_key for n in expected.graph.nodes} == {"US1"}

    def _derive_delta(request) -> Any:
        from factory.workgraph.delta import derive_delta

        return derive_delta(
            request.spec_text,
            baseline=baseline,
            epic_id=request.epic_id,
            feature=request.feature,
            specs_root=request.specs_root,
            target_repo=request.target_repo,
        ).graph

    world = RoadmapWorld(derive_runner=_derive_delta)
    child_starts: list[Any] = []
    status = await run_to_completion(
        env,
        world,
        str(specs_root),
        child_starts=child_starts,
    )

    assert len(child_starts) == 1
    dispatched_graph: WorkGraph = child_starts[0].args[0].graph
    assert dispatched_graph == expected.graph
    assert _status_of(status, spec_dir).landed is True


async def test_fresh_spec_dispatch_graph_is_identical_to_pre_delta_path(
    env: WorkflowEnvironment, tmp_path: Path, repo_builder: Callable[..., Path]
) -> None:
    """FR-006 / SC-005: a fresh spec with no landings dispatches a graph identical
    to what full derivation produces today — adopting delta dispatch changes nothing
    for the existing corpus."""
    from factory.workgraph.derive import derive_workgraph
    from factory.workgraph.models import WorkGraph
    from tests.test_roadmap_scheduler import RoadmapWorld, run_to_completion

    spec_dir = "016-delta-derivation"
    spec_text = _spec_text(
        state="ready",
        stories=["US1", "US2"],
        work_graph=(
            "US1:\n  depends_on: []\n  implements: [FR-001]\n"
            "US2:\n  depends_on: []\n  implements: [FR-002]\n"
        ),
    )
    repo = repo_builder(spec_dir, spec_text)

    specs_root = tmp_path / "specs"
    spec_path = specs_root / spec_dir / "spec.md"
    spec_path.parent.mkdir(parents=True)
    spec_path.write_text(spec_text, encoding="utf-8")

    expected_full = derive_workgraph(
        spec_text,
        epic_id=spec_dir,
        feature=spec_dir,
        specs_root=str(specs_root),
        target_repo=TARGET_REPO,
    )

    def _derive_full(request) -> WorkGraph:
        return derive_workgraph(
            request.spec_text,
            epic_id=request.epic_id,
            feature=request.feature,
            specs_root=request.specs_root,
            target_repo=request.target_repo,
        )

    world = RoadmapWorld(derive_runner=_derive_full)
    child_starts: list[Any] = []
    status = await run_to_completion(
        env,
        world,
        str(specs_root),
        child_starts=child_starts,
    )

    assert len(child_starts) == 1
    dispatched_graph: WorkGraph = child_starts[0].args[0].graph
    assert dispatched_graph == expected_full
    assert _status_of(status, spec_dir).landed is True


def _status_of(status: Any, spec_dir: str) -> Any:
    for spec in status.specs:
        if spec.spec_dir == spec_dir:
            return spec
    raise AssertionError(f"{spec_dir} not in roadmap status")
