"""One verdict, two verbs, and two lines that stopped saying `running` at once.

`ergane status` and `ergane roadmap status` printed the same sentence from two
files — `state = "paused" if …schedule_paused else "running"` in
`factory/cli/status.py` and again in `factory/cli/roadmap.py` — so a schedule
whose every tick had been skipped for six hours said `(running)` in both. US2
moved the decision onto `RoadmapLocation`, where it is made once; this module is
the half the operator sees, and it holds both renderers to reading that decision
rather than re-deriving it.

Every location here is handed in whole. US1 owns the read that builds one off a
described schedule and proves it against four fakes; repeating that here would
buy nothing and would put a fifth fake in the tree — one more place for a
missing `spec` to degrade a verdict to `unknown` and take a suite green on a
fixture that never produced a verdict (085 plan, trap 6). So
`resolve_roadmap` is stubbed to hand back the location under test, and what is
exercised is `_disposition`, `_roadmap_lines`, `_render_disposition` and
`_render_status` — the four functions this story actually changes.

Two controls carry the weight:

- `test_both_verbs_render_the_same_schedule_line` renders **one** location
  through both and compares the whole line, in all four states. A diff where
  each renderer computes its own answer passes every other test in this file and
  fails that one (trap 2).
- `test_a_healthy_schedule_renders_byte_for_byte_what_it_rendered_before` pins
  today's output in both verbs, `next tick:` included. That line is true during
  starvation — the schedule really will tick, it will just skip — so it keeps its
  wording and its value (trap 9).

Elapsed times are seeded relative to the wall clock, because the verdict is
decided against the wall clock and a fixed fixture date would drift into
`starved` the day after it was written. The offsets are whole hours and whole
minutes, so the rendered phrase is stable to the second: an elapsed reading of
six hours plus a few microseconds still truncates to `6h 0m`.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from factory.cli import roadmap as roadmap_cli
from factory.cli import status as status_cli
from factory.cli.status import (
    FloorStatus,
    QueueEntry,
    ReadinessBasis,
    RoadmapDisposition,
)
from factory.roadmap.discovery import (
    RoadmapLocation,
    RoadmapOwner,
    RoadmapScheduleState,
)
from factory.roadmap.models import SpecState
from factory.roadmap.workflow import RoadmapSpecStatus, RoadmapStatus

SPECS_ROOT = "/srv/factory/ergane/specs"
BARE_ID = "roadmap-specs"
RUN_ID = "roadmap-specs-2026-08-22T15:00:00Z"
#: Named by an operator's hand, as the live one is; it is seed data here.
SCHEDULE_ID = "ergane-roadmap"
NEXT_TICK = "2026-08-22T16:00:00+00:00"
CADENCE_S = 300
RUNNING_SPEC = "011-agent-sandbox"


def _ago(**delta: float) -> str:
    """A timestamp that far in the past, phrased as the location carries them."""
    return (datetime.now(timezone.utc) - timedelta(**delta)).isoformat()


def _location(**dials: Any) -> RoadmapLocation:
    """A schedule-owned location that is healthy until a dial says otherwise."""
    fields: dict[str, Any] = dict(
        root_name="specs",
        bare_workflow_id=BARE_ID,
        run_prefix=f"{BARE_ID}-",
        owner=RoadmapOwner.SCHEDULE,
        workflow_id=RUN_ID,
        schedule_id=SCHEDULE_ID,
        schedule_paused=False,
        next_action_at=NEXT_TICK,
        looked_for=(f"workflow id {BARE_ID}",),
        skipped_overlap_count=0,
        last_action_started_at=_ago(minutes=1),
        schedule_created_at=_ago(hours=12),
        cadence_s=CADENCE_S,
    )
    fields.update(dials)
    return RoadmapLocation(**fields)


#: The dials that produce each of the four verdicts, and the word each is worth.
#: `starved` is six hours past a start on a five-minute cadence; `unknown` is a
#: cadence that could not be read, which the verdict tolerates by design.
VERDICTS: tuple[tuple[str, dict[str, Any], str], ...] = (
    ("running", {}, "running"),
    ("paused", {"schedule_paused": True}, "paused"),
    (
        "starved",
        {"last_action_started_at": _ago(hours=6), "skipped_overlap_count": 74},
        "starved",
    ),
    ("unknown", {"cadence_s": None}, "unknown"),
)


# --- `ergane status`'s half ---------------------------------------------------


_DOCUMENT: dict[str, Any] = {
    "paused": False,
    "running": [RUNNING_SPEC],
    "parked": [],
}


class _StubClient:
    """Enough Temporal for `_disposition` to reach the run's own query.

    The ladder is not exercised here — US1 owns that read and proves it against
    the four fakes — so the only call this has to answer is the `roadmap_status`
    query `_disposition` makes once a location names a run.
    """

    def __init__(self, document: Any) -> None:
        self._document = document

    def get_workflow_handle(self, workflow_id: str, **_kwargs: Any) -> Any:
        return SimpleNamespace(query=self._query)

    async def _query(self, name: str, *_args: Any, **_kwargs: Any) -> Any:
        assert name == "roadmap_status", f"unexpected query {name!r}"
        return self._document


def _disposition(
    monkeypatch: pytest.MonkeyPatch,
    location: RoadmapLocation,
    document: Any = None,
) -> RoadmapDisposition:
    """`ergane status`'s disposition, built by the real code off `location`."""

    async def _resolved(_client: Any, _specs_root: str) -> RoadmapLocation:
        return location

    monkeypatch.setattr(status_cli, "resolve_roadmap", _resolved)
    client = _StubClient(_DOCUMENT if document is None else document)
    return asyncio.run(status_cli._disposition(client, Path(SPECS_ROOT)))


def _floor(disposition: RoadmapDisposition | None) -> FloorStatus:
    """A floor with every other section populated, so a report can be read whole."""
    return FloorStatus(
        specs_root=SPECS_ROOT,
        roadmap=disposition,
        epics=[],
        queue=[QueueEntry(spec_dir=RUNNING_SPEC, state="ready", dispatchable=True, blockers=[])],
        drafts=[QueueEntry(spec_dir="099-a-draft", state="draft", dispatchable=False, blockers=[])],
        pace=[],
        readiness_basis=ReadinessBasis(observed=True, detail="landed facts"),
        notes=[],
        degraded=False,
    )


def _status_block(
    monkeypatch: pytest.MonkeyPatch, location: RoadmapLocation, **kwargs: Any
) -> list[str]:
    """The roadmap section of `ergane status`, line by line and unindented."""
    return status_cli._roadmap_lines(_floor(_disposition(monkeypatch, location, **kwargs)))


# --- `ergane roadmap status`'s half -------------------------------------------


def _status_document() -> RoadmapStatus:
    return RoadmapStatus(
        specs=[
            RoadmapSpecStatus(
                spec_dir=RUNNING_SPEC,
                state=SpecState.READY,
                dispatchable=True,
                blockers=[],
                landed=False,
                unlanded=[],
            )
        ],
        running=[RUNNING_SPEC],
        parked=[],
        max_concurrent_epics=1,
        max_concurrent_nodes=1,
        paused=False,
    )


def _roadmap_block(location: RoadmapLocation) -> list[str]:
    """The disposition `ergane roadmap status` prints above the status document."""
    return roadmap_cli._render_disposition(location).splitlines()


# --- reading a rendered block -------------------------------------------------


def _schedule_line(lines: list[str]) -> str:
    matched = [line for line in lines if line.startswith("schedule:")]
    assert len(matched) == 1, f"expected exactly one schedule line, got {matched}"
    return matched[0]


def _verdict(line: str) -> str:
    """The word inside the parentheses, before any evidence it carries."""
    inside = line.split("(", 1)[1].rstrip(")")
    return inside.split(":", 1)[0]


def _headers(report: str) -> list[str]:
    """Each section's name, dropping the parenthetical the queue header carries."""
    return [
        line.split(" ", 1)[0]
        for line in report.splitlines()
        if line and not line.startswith(" ")
    ]


# ============================================================================
# T027 / US3-S1 — `ergane status` says starved, and names its evidence
# ============================================================================


def test_ergane_status_names_the_starvation_its_age_and_the_skipped_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S1 / FR-009, FR-010: the line the reporter needed on 2026-08-15.

    Asserted **positively** — the word, the elapsed time and the count — and
    byte for byte. A test that merely checked the line was not `running` would
    be satisfied by `unknown`, which is the state a fixture with an unreadable
    cadence degrades to, and would pass having proved no verdict at all.

    Verbatim line:

        schedule: ergane-roadmap (starved: 6h 0m since a tick last started, 74 ticks skipped)
    """
    location = _location(
        last_action_started_at=_ago(hours=6), skipped_overlap_count=74
    )

    lines = _status_block(monkeypatch, location)

    assert _schedule_line(lines) == (
        f"schedule: {SCHEDULE_ID} (starved: 6h 0m since a tick last started, "
        "74 ticks skipped)"
    )
    # Trap 9: the next tick is a true statement during starvation — every tick
    # still fires, it is just skipped — so its wording and its value stand.
    assert f"next tick: {NEXT_TICK}" in lines


def test_a_starved_schedule_that_has_never_ticked_says_so_rather_than_a_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-010 degrading: "how long since a tick started" has no answer when none did.

    The schedule's own age is the reference the verdict measures against, but it
    is not a substitute for a start that never happened, so the evidence half
    says which it is instead of reporting the age as though a tick had run.
    """
    location = _location(
        last_action_started_at=None,
        schedule_created_at=_ago(hours=6),
        skipped_overlap_count=12,
    )

    assert _schedule_line(_status_block(monkeypatch, location)) == (
        f"schedule: {SCHEDULE_ID} (starved: no tick has ever started, "
        "12 ticks skipped)"
    )


def test_a_starved_schedule_whose_skipped_count_could_not_be_read_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Trap 3 inside the sentence: an unread count is named, never printed as zero."""
    location = _location(
        last_action_started_at=_ago(hours=6), skipped_overlap_count=None
    )

    assert _schedule_line(_status_block(monkeypatch, location)) == (
        f"schedule: {SCHEDULE_ID} (starved: 6h 0m since a tick last started, "
        "skipped count unknown)"
    )


@pytest.mark.parametrize(
    "ago, phrase",
    [
        ({"seconds": 45}, "45s"),
        ({"minutes": 30}, "30m"),
        ({"hours": 6}, "6h 0m"),
        ({"hours": 27}, "1d 3h"),
    ],
    ids=["seconds", "minutes", "hours", "days"],
)
def test_the_elapsed_time_is_phrased_at_the_scale_the_outage_reached(
    monkeypatch: pytest.MonkeyPatch, ago: dict[str, int], phrase: str
) -> None:
    """FR-010's first half: an operator reads "6h 0m", never "21600"."""
    location = _location(last_action_started_at=_ago(**ago), cadence_s=1)

    assert f"{phrase} since a tick last started" in _schedule_line(
        _status_block(monkeypatch, location)
    )


def test_the_disposition_carries_the_verdict_rather_than_the_renderer_deriving_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-009: `_disposition` copies the decision and its evidence off the location.

    The renderer is handed a finished verdict; it is not handed a boolean and a
    clock. This is what makes `ergane status --json` say the same thing its own
    human rendering does.
    """
    location = _location(
        last_action_started_at=_ago(hours=6), skipped_overlap_count=74
    )

    disposition = _disposition(monkeypatch, location)

    assert disposition.schedule_state == RoadmapScheduleState.STARVED.value
    assert disposition.skipped_overlap_count == 74
    assert disposition.seconds_since_last_start == 6 * 60 * 60
    # The flag the old sentence was built from is still carried, unchanged.
    assert disposition.schedule_paused is False


# ============================================================================
# T028 / US3-S2 — one location, two verbs, one answer
# ============================================================================


@pytest.mark.parametrize(
    "dials, word", [(dials, word) for _, dials, word in VERDICTS], ids=[n for n, _, _ in VERDICTS]
)
def test_both_verbs_render_the_same_schedule_line(
    monkeypatch: pytest.MonkeyPatch, dials: dict[str, Any], word: str
) -> None:
    """US3-S2 / FR-009: the whole line agrees, in all four states.

    Not merely the verdict word: the evidence is part of the sentence, and two
    renderers that agree on `starved` while disagreeing about how long it has
    been starved have drifted just as surely. A diff where each renderer
    computes its own answer passes every other test in this file and fails here
    (trap 2).
    """
    location = _location(**dials)

    from_status = _schedule_line(_status_block(monkeypatch, location))
    from_roadmap = _schedule_line(_roadmap_block(location))

    assert from_status == from_roadmap
    assert _verdict(from_status) == word


def test_the_four_words_both_verbs_can_print_are_the_four_the_spec_names() -> None:
    """The renderers may print no fifth word: they read a decided state."""
    assert {word for _, _, word in VERDICTS} == {
        state.value for state in RoadmapScheduleState
    }


# ============================================================================
# T029 / US3-S3 — the control: a healthy floor renders exactly as before
# ============================================================================


def test_a_healthy_schedule_renders_byte_for_byte_what_it_rendered_before(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S3 / FR-011. **This is the control**, and it is what keeps every
    existing status test honest.

    Verbatim `ergane status` roadmap section:

        schedule: ergane-roadmap (running)
        run: roadmap-specs-2026-08-22T15:00:00Z
        next tick: 2026-08-22T16:00:00+00:00
        dispatch: running
        running: 011-agent-sandbox
        parked: 0

    Verbatim `ergane roadmap status` disposition:

        schedule: ergane-roadmap (running)
        run: roadmap-specs-2026-08-22T15:00:00Z
        next tick: 2026-08-22T16:00:00+00:00
    """
    location = _location()

    assert _status_block(monkeypatch, location) == [
        f"schedule: {SCHEDULE_ID} (running)",
        f"run: {RUN_ID}",
        f"next tick: {NEXT_TICK}",
        "dispatch: running",
        f"running: {RUNNING_SPEC}",
        "parked: 0",
    ]
    assert roadmap_cli._render_disposition(location) == (
        f"schedule: {SCHEDULE_ID} (running)\n"
        f"run: {RUN_ID}\n"
        f"next tick: {NEXT_TICK}\n"
    )


def test_a_paused_schedule_renders_byte_for_byte_what_it_rendered_before(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-011's other half: the operator's own decision reads as it always did.

    A paused schedule is not starved however long since its last tick, so this
    stays a bare `(paused)` with no evidence clause bolted on.
    """
    location = _location(schedule_paused=True, last_action_started_at=_ago(hours=6))

    assert _schedule_line(_status_block(monkeypatch, location)) == (
        f"schedule: {SCHEDULE_ID} (paused)"
    )
    assert _schedule_line(_roadmap_block(location)) == (
        f"schedule: {SCHEDULE_ID} (paused)"
    )


# ============================================================================
# T030 / US3-S4 — `unknown` is printed, and the report survives it
# ============================================================================


def test_an_unknown_schedule_state_renders_as_such_in_both_verbs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S4 / FR-009: a reading that could not be taken is said, not guessed."""
    location = _location(cadence_s=None)

    assert _schedule_line(_status_block(monkeypatch, location)) == (
        f"schedule: {SCHEDULE_ID} (unknown)"
    )
    assert _schedule_line(_roadmap_block(location)) == (
        f"schedule: {SCHEDULE_ID} (unknown)"
    )


def test_an_unknown_schedule_state_leaves_every_other_line_rendering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S4, 052's principle: a degraded reading is one line, never a traceback.

    The whole floor report is rendered, not just its roadmap section, because
    the failure this guards against is an `unknown` that takes the queue and the
    drafts down with it.
    """
    location = _location(cadence_s=None, schedule_paused=None)

    report = status_cli.render_floor(_floor(_disposition(monkeypatch, location)))

    assert _headers(report) == ["roadmap", "epics", "queue", "drafts", "pace"]
    assert f"  schedule: {SCHEDULE_ID} (unknown)" in report.splitlines()
    assert f"  run: {RUN_ID}" in report.splitlines()
    assert f"next tick: {NEXT_TICK}" in report
    assert RUNNING_SPEC in report
    assert "099-a-draft" in report
    # The roadmap verb degrades the same way, on the same location.
    assert f"schedule: {SCHEDULE_ID} (unknown)" in _roadmap_block(location)


# ============================================================================
# T031 / US3-S5 — the line that said `roadmap: running` names dispatch
# ============================================================================


def test_the_roadmap_status_block_names_dispatch_rather_than_roadmap() -> None:
    """US3-S5 / FR-012: `factory/cli/roadmap.py`'s status block adopts
    `ergane status`'s word for the same fact.

    Verbatim stdout of the block:

        dispatch: running
        concurrency: 1 epic(s), 1 node(s)
        running: 011-agent-sandbox
        parked: 0
    """
    lines = roadmap_cli._render_status(_status_document()).splitlines()

    assert lines[0] == "dispatch: running"
    assert not [line for line in lines if line.startswith("roadmap:")]
    assert lines[:4] == [
        "dispatch: running",
        "concurrency: 1 epic(s), 1 node(s)",
        f"running: {RUNNING_SPEC}",
        "parked: 0",
    ]


def test_a_paused_roadmap_says_dispatch_paused() -> None:
    """The other value of the renamed line — the subject changed, not the fact."""
    paused = replace(_status_document(), paused=True)

    assert roadmap_cli._render_status(paused).splitlines()[0] == "dispatch: paused"


def test_both_verbs_use_the_same_word_for_the_dispatch_fact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-012: `ergane status` already called this dispatch; now both do."""
    from_roadmap = roadmap_cli._render_status(_status_document()).splitlines()
    from_status = _status_block(monkeypatch, _location())

    assert "dispatch: running" in from_roadmap
    assert "dispatch: running" in from_status


def test_the_schedule_line_and_the_dispatch_line_cannot_be_read_as_one_another(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S5's point: two lines both saying `running` for unrelated reasons is
    how the reporter lost six hours.

    Rendered together, on a starved floor, `ergane roadmap status` now says:

        schedule: ergane-roadmap (starved: 6h 0m since a tick last started, 74 ticks skipped)
        run: roadmap-specs-2026-08-22T15:00:00Z
        next tick: 2026-08-22T16:00:00+00:00
        dispatch: running
        concurrency: 1 epic(s), 1 node(s)
        running: 011-agent-sandbox
        parked: 0

    — one line about the schedule, one about dispatch, and no line at all that
    could be mistaken for the other.
    """
    location = _location(
        last_action_started_at=_ago(hours=6), skipped_overlap_count=74
    )

    rendered = roadmap_cli._render_disposition(location) + roadmap_cli._render_status(
        _status_document()
    )
    lines = rendered.splitlines()

    subjects = [line.split(":", 1)[0] for line in lines]
    assert len(subjects) == len(set(subjects)), f"two lines share a subject: {subjects}"
    assert _schedule_line(lines) != "schedule: ergane-roadmap (running)"
    assert "starved" in _schedule_line(lines)
    assert "dispatch: running" in lines
    assert "roadmap: running" not in lines


def test_the_status_verbs_roadmap_section_names_each_subject_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same property for `ergane status`, on the same starved floor."""
    location = _location(
        last_action_started_at=_ago(hours=6), skipped_overlap_count=74
    )

    lines = _status_block(monkeypatch, location)

    subjects = [line.split(":", 1)[0] for line in lines]
    assert len(subjects) == len(set(subjects)), f"two lines share a subject: {subjects}"
    assert "starved" in _schedule_line(lines)
    assert "dispatch: running" in lines
