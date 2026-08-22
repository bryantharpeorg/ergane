"""050 US3: a schedule identity cannot collide with a stranger's.

Two repositories whose directory names happen to be the same can share a slug
if an operator confirms it.  The schedule id is derived from the slug, so init
must check that an existing schedule under that id is recorded for *this*
repository before it reconciles it.

Every claim about the schedule is read off the backend's state, not off a call
log or the local filesystem (US3-S1, US3-S3, plan trap 3 and trap 6).  Nothing
here reaches a real Temporal.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest

import factory.cli.init as init_module
from factory.cli.errors import EXIT_OK
from factory.notify.service import TEMPORAL_NAMESPACE_ENV
from factory.roadmap import schedule as sched
from factory.roadmap.schedule import schedule_id_for
from factory.usage.litellm_client import PROXY_URL_ENV

from tests.fake_schedules import FakeScheduleServer, desired_for, seed
from tests.test_ergane_init import ScriptedPrompter, _invoke
from tests.test_ergane_init_check import bind_offline_seams
from tests.test_init_schedule_precondition import bare_repo, schedule_line

SLUG = "widgets"
SCHEDULE = schedule_id_for(SLUG)
Init = Callable[..., Any]


@pytest.fixture
def floor(monkeypatch: pytest.MonkeyPatch) -> FakeScheduleServer:
    """Every outward seam bound; the control plane these tests may inspect."""
    control_plane = FakeScheduleServer()
    bind_offline_seams(monkeypatch, schedules=control_plane)
    monkeypatch.delenv(PROXY_URL_ENV, raising=False)
    monkeypatch.delenv(TEMPORAL_NAMESPACE_ENV, raising=False)
    return control_plane


@pytest.fixture
def init(monkeypatch: pytest.MonkeyPatch, floor: FakeScheduleServer) -> Init:
    """Run a full `ergane init`, scripting the interview in `_TOP_LEVEL_KEYS` order."""

    def run(repo: Path, *, slug: str = SLUG) -> Any:
        # version, runtime, gates, timeouts, standards, landing_branch, roadmap,
        # forge (049/US5, omitted), writes (084/US3, omitted), slug
        answers = [
            "1",
            "bwrap",
            'test: "uv run pytest -q"',
            "",
            "",
            "main",
            "",
            "",
            "",
            slug,
        ]
        monkeypatch.setattr(
            init_module, "_prompter_factory", lambda: ScriptedPrompter(answers)
        )
        return _invoke(["init", str(repo)])

    return run


# --- T019 / US3-S1, FR-008: a stranger's schedule is refused and untouched -----


def test_init_refuses_when_schedule_belongs_to_a_different_repo(
    tmp_path: Path, floor: FakeScheduleServer, init: Init
) -> None:
    """US3-S1: init must not adopt, overwrite or fight over a stranger's schedule.

    The schedule under this slug was created for a different repository root.  The
    refusal names both roots and the backend's snapshot is byte-identical after
    the run — the claim is about the world, not about whether `apply_schedule` was
    called.
    """
    repo = bare_repo(tmp_path, "widgets")
    stranger = bare_repo(tmp_path, "stranger")
    seed(floor, desired_for(stranger, slug=SLUG))

    before = floor.snapshot(SCHEDULE)
    before_calls = list(floor.calls)

    result = init(repo, slug=SLUG)

    assert result.code == EXIT_OK, result.stderr
    line = schedule_line(result.stdout)
    assert line.startswith(f"schedule: failed {SCHEDULE}"), line
    assert str(repo.resolve()) in line, line
    assert str(stranger.resolve()) in line, line
    assert floor.snapshot(SCHEDULE) == before, "stranger's schedule was modified"
    writes = [call for call in floor.calls if call[0] != "describe"]
    assert writes == before_calls, "the control plane was written to"


# --- T020 / US3-S2: the same repository may re-run init and reconcile -----------


def test_init_reconciles_when_schedule_belongs_to_this_repo(
    tmp_path: Path, floor: FakeScheduleServer, init: Init
) -> None:
    """US3-S2: re-running init in a joined repository is supported.

    The schedule under this slug records *this* repository's root, so the identity
    check must let init proceed exactly as it does today.
    """
    repo = bare_repo(tmp_path, "widgets")

    first = init(repo, slug=SLUG)
    assert first.code == EXIT_OK, first.stderr
    assert schedule_line(first.stdout).startswith(f"schedule: created {SCHEDULE}")

    before = floor.snapshot(SCHEDULE)
    floor.calls.clear()

    second = init(repo, slug=SLUG)

    assert second.code == EXIT_OK, second.stderr
    line = schedule_line(second.stdout)
    assert "failed" not in line, line
    assert floor.snapshot(SCHEDULE) == before, "matching schedule was modified"
    writes = [call for call in floor.calls if call[0] != "describe"]
    assert writes == [], "a matching re-run wrote to the control plane"


# --- T021 / US3-S3, FR-009: the comparison reads the schedule, not the disk ------


def test_identity_comparison_reads_schedule_not_local_filesystem(
    tmp_path: Path, floor: FakeScheduleServer, init: Init
) -> None:
    """US3-S3: the identity check consults state recorded on the schedule.

    A check that reads only the local filesystem cannot observe another
    operator's repository and would pass vacuously.  Here the schedule records a
    root that does not exist locally; the local repo *does* have a `specs/`
    directory, so a filesystem-based check would wrongly conclude the schedule
    belongs here and reconcile it.
    """
    repo = bare_repo(tmp_path, "widgets")
    # Recorded root is a stranger's repository that does not exist on this host.
    stranger_root = tmp_path / "another-checkout" / "repo"
    seed(floor, desired_for(stranger_root, slug=SLUG))

    before = floor.snapshot(SCHEDULE)
    before_calls = list(floor.calls)

    result = init(repo, slug=SLUG)

    assert result.code == EXIT_OK, result.stderr
    line = schedule_line(result.stdout)
    assert line.startswith(f"schedule: failed {SCHEDULE}"), line
    assert str(repo.resolve()) in line, line
    assert str(stranger_root) in line, line
    assert floor.snapshot(SCHEDULE) == before, "schedule mutated by a local-state check"
    writes = [call for call in floor.calls if call[0] != "describe"]
    assert writes == before_calls, "control plane was written to"
