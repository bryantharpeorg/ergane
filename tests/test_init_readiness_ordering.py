"""050 US2: the control-plane verdict is reported before the act that depends on it.

The defect that made US1 necessary was legibility, not outcome: the refusal
reason was already in hand, but it was printed *after* the schedule line.  A
transcript that reads as a confession — "I scheduled, and by the way the
control plane is missing" — makes the next such act easy to add below the line.

Tests here assert on *position*, not presence (US2-S1, plan trap 5).  A test
that both lines appear would pass before the reordering, so it would fail to
prove the story.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest

import factory.cli.init as init_module
from factory.cli.errors import EXIT_OK
from factory.mergequeue.models import Finding
from factory.roadmap import schedule as sched

from tests.fake_schedules import FakeScheduleServer
from tests.test_ergane_init import ScriptedPrompter, _git, _invoke
from tests.test_ergane_init_check import bind_offline_seams

SLUG = "us2-widgets"
Init = Callable[..., Any]


@pytest.fixture
def floor(monkeypatch: pytest.MonkeyPatch) -> FakeScheduleServer:
    """The schedule backend; the control plane is not installed by default."""
    control_plane = FakeScheduleServer()
    bind_offline_seams(monkeypatch, schedules=control_plane, control_plane_installed=False)
    return control_plane


@pytest.fixture
def init(monkeypatch: pytest.MonkeyPatch) -> Init:
    """Run a full `ergane init`, scripting the interview."""

    def run(repo: Path, *, slug: str = SLUG) -> Any:
        answers = ["1", "bwrap", 'test: "uv run pytest -q"', "", "", "main", "", "", "", "", "", "", slug]
        monkeypatch.setattr(init_module, "_prompter_factory", lambda: ScriptedPrompter(answers))
        return _invoke(["init", str(repo)])

    return run


def bare_repo(tmp_path: Path, name: str = "us2-repo") -> Path:
    """A git repo with one commit and no Ergane presence at all."""
    repo = tmp_path / name
    (repo / "specs").mkdir(parents=True)
    _git(repo, "init", "-b", "main", "--quiet")
    (repo / "README.md").write_text(f"# {name}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "initial commit")
    return repo


def _index_of(lines: list[str], marker: str) -> int:
    """Return the index of the first line containing `marker`, or a sentinel."""
    for i, line in enumerate(lines):
        if marker in line:
            return i
    return -1


# --- T013 / US2-S1: control-plane verdict precedes the schedule line ------------


def test_control_plane_verdict_precedes_schedule_line_when_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, floor: FakeScheduleServer, init: Init
) -> None:
    """US2-S1: the precondition appears before the act it guards.

    Asserted on position, not presence.  Both lines already appear today, in the
    wrong order; the test compares their indices in the captured output.
    """
    repo = bare_repo(tmp_path)

    result = init(repo)

    assert result.code == EXIT_OK, result.stderr
    lines = result.stdout.splitlines()
    # The verdict line is a separate line, not the schedule line's embedded reason.
    verdict_index = _index_of(lines, "control plane:")
    schedule_index = _index_of(lines, "schedule: ")
    assert verdict_index != -1, "expected a control-plane verdict line"
    assert schedule_index != -1, "expected a schedule line"
    assert verdict_index < schedule_index, (
        f"control-plane verdict (line {verdict_index}) must precede "
        f"schedule line (line {schedule_index})"
    )


# --- T014 / US2-S2: passing run still ends with readiness report and guidance ---


def test_passing_run_still_ends_with_readiness_report_and_next_run_guidance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, init: Init
) -> None:
    """US2-S2: reordering the precondition must not reorder the operator's instructions.

    A fully passing run still ends with the readiness report and still prints
    the `next, run:` guidance naming the paths to commit.
    """
    repo = bare_repo(tmp_path)
    bind_offline_seams(
        monkeypatch,
        schedules=FakeScheduleServer(),
        probes=[
            Finding("temporal", True, "Temporal at localhost:7233 has namespace `factory`"),
            Finding("memory", True, "skipped by declaration: memory.backend is `none`"),
        ],
    )

    result = init(repo)

    assert result.code == EXIT_OK, result.stderr
    lines = result.stdout.splitlines()
    readiness_start = _index_of(lines, "ergane readiness for")
    next_run_index = _index_of(lines, "next, run:")
    assert readiness_start != -1, "readiness report should appear"
    assert next_run_index != -1, "next, run: guidance should appear"
    assert readiness_start > next_run_index, (
        "readiness report must still come after the operator's instructions"
    )
    # The guidance still names the paths to commit.
    next_line = lines[next_run_index + 1]
    assert "git add" in next_line or "git -C" in next_line, next_line
    assert "ergane.yaml" in next_line and ".gitignore" in next_line, next_line
    # Readiness report ends the output.
    assert lines[-1].startswith("all ") or "failed" in lines[-1], lines[-1]


# --- T015 / US2-S3, FR-006: the readability check is evaluated once and reused


def test_control_plane_readability_is_evaluated_once_and_reused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, init: Init
) -> None:
    """FR-006: the readability check runs once and its result is shared.

    Before the fix, a missing control plane caused `_control_plane_reason()` to
    run once for the schedule precondition and `_controlplane_probe()` to run
    once more for the readiness report — two evaluations for one answer.  After
    the fix, the single readability result is reused and the probe suite is
    skipped when we already know the control plane is unreadable.
    """
    reason_calls = 0
    probe_calls = 0

    def counting_reason() -> str | None:
        nonlocal reason_calls
        reason_calls += 1
        return "ControlPlaneConfigError: missing config"

    def counting_probe() -> tuple[list[Finding], int]:
        nonlocal probe_calls
        probe_calls += 1
        return [], 1

    monkeypatch.setattr(init_module, "_control_plane_reason", counting_reason)
    monkeypatch.setattr(init_module, "_controlplane_probe", counting_probe)

    repo = bare_repo(tmp_path)

    result = init(repo)

    assert result.code == EXIT_OK, result.stderr
    assert reason_calls == 1, f"_control_plane_reason ran {reason_calls} times, expected 1"
    assert probe_calls == 0, f"_controlplane_probe ran {probe_calls} times; result should be reused"
