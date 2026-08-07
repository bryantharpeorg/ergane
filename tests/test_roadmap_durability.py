"""US3 durability: continue-as-new at quiescence bounds history (FR-007, SC-003).

The roadmap runs for months of epics without hitting Temporal's history limit by
continuing-as-new at quiescence — the one moment zero children are open, so no
completion event can be lost across the run boundary — and carrying its state
forward as an explicit input (parked findings, observed landings, promotions,
the pause flag, the bound). Everything else is re-read on the new run: re-reading
is what makes "restarting re-reads the world" true for free (SC-004).

This is the 006-US1 history-bound proof one level up. 006-US1 replaced a poll
loop with a plain await so an attempt's history was O(1), not O(duration); here a
run that processes N epics would grow history without bound (one event set per
epic per run), and continue-as-new bounds each run to one epic's worth of work.
The proof is the same shape: run the roadmap with many epics and assert every
run's history event count is under a fixed constant (SC-003) — continue-as-new
gives each epic its own run instead of piling N completions into one history.

Written before `factory/roadmap/workflow.py` carries continue-as-new (T014
precedes T016): until it lands, every test here fails. The harness lives in
`tests/test_roadmap_scheduler.py` (US2's file); these tests import it rather than
duplicate it, the way the existing suite tolerates the third `env` fixture copy
(plan § Testing — a fourth copy is acceptable; consolidation is not this epic's
job).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, AsyncIterator

import pytest
from temporalio.testing import WorkflowEnvironment

from factory.roadmap.models import SpecState
from factory.roadmap.workflow import (
    RoadmapInput,
    RoadmapStatus,
    RoadmapWorkflow,
    roadmap_workflow_id,
)
from factory.workgraph.workflow import EpicStatus

from tests.roadmap_script import _SCRIPT, landed_status
from tests.test_roadmap_scheduler import (
    RoadmapWorld,
    build_corpus,
    run_roadmap,
    run_to_completion,
)

TARGET_REPO = "/srv/factory/targets/library"
PROXY_URL = "http://litellm.test"

#: The fixed constant every run's history must stay under (SC-003). A single
#: run that processed ten epics without continue-as-new carries hundreds of
#: events (one child-completion set per epic, all in one history); with
#: continue-as-new each run carries one epic's worth — corpus read, capacity
#: read, one dispatch, one child-wait, the continue-as-new marker, and the
#: fixed-size carry-over — well under this constant. The number is a ceiling,
#: not a target: it is loose enough to absorb a child's landing phase and the
#: carry-over, and tight enough that a run which piled ten epics into one
#: history (the defect this story bounds) fails it by an order of magnitude.
HISTORY_BOUND = 150


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    """Temporal with a clock the test owns (the US2 harness's `env` fixture).

    A fourth copy of the fixture, which the plan tolerates (consolidation is
    not this epic's job). Resets the scripted-epic script so one test's
    statuses and hooks do not bleed into the next.
    """
    environment = await WorkflowEnvironment.start_time_skipping()
    _SCRIPT.statuses = {}
    _SCRIPT.on_dispatch = None
    _SCRIPT.on_complete = None
    try:
        yield environment
    finally:
        await environment.shutdown()
        _SCRIPT.statuses = {}
        _SCRIPT.on_dispatch = None
        _SCRIPT.on_complete = None


async def _history_event_count(handle: Any) -> int:
    """Total history events for the run the handle currently points at.

    After `result()`, the handle follows a continue-as-new chain to the *final*
    run, so this is the final run's event count — the run whose history we
    assert is bounded (the carry-over input is fixed-size, so the final pass's
    work is the same shape regardless of how many epics preceded it). A single
    run that processed every epic would carry all of them in one history; the
    final run after continue-as-new carries only the last pass's work.
    """
    history = await handle.fetch_history()
    return len(history.events)


def _write_chain(root: Path, n: int) -> Path:
    """A corpus of N independent `ready` specs the roadmap dispatches in series.

    Each spec is `ready` with no dependencies, so each dispatches and lands in
    its own scheduling pass. With the bound at one (the default), the roadmap
    runs them one at a time — N epics, N child completions, and (US3) N
    continue-as-new boundaries.
    """
    specs: dict[str, dict[str, Any]] = {}
    for i in range(1, n + 1):
        specs[f"{i:03d}-spec"] = dict(state=SpecState.READY)
    return build_corpus(root, specs)


# ============================================================================
# T014 — durability cases (must fail before continue-as-new lands)
# ============================================================================


async def test_no_runs_history_grows_with_n(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """SC-003 / FR-007 / acceptance 1: no run's history event count grows with N.

    The roadmap processes ten sequential epics, continuing-as-new after each
    child concludes so each run's history is bounded by a constant. The proof
    is the 006-US1 shape one level up: run the roadmap with one epic and with
    ten, and assert neither final run's history exceeds `HISTORY_BOUND` — and
    that the ten-epic run's final history is not larger than the one-epic
    run's by more than a small constant, because continue-as-new gave every
    epic its own run instead of piling ten completions into one history.

    Without continue-as-new the ten-epic run carries hundreds of events in one
    history (the defect); with it, the final run carries one epic's worth.
    """
    # N=1.
    root_one = _write_chain(tmp_path, 1)
    world = RoadmapWorld()
    async with run_roadmap(env, world, str(root_one)) as handle:
        await handle.result()
    one_count = await _history_event_count(handle)

    # N=10 — same roadmap, ten times the epics.
    root_ten = _write_chain(tmp_path, 10)
    world = RoadmapWorld()
    async with run_roadmap(env, world, str(root_ten)) as handle:
        await handle.result()
    ten_count = await _history_event_count(handle)

    # Every run's history is under the fixed constant (SC-003): the one-epic
    # run and the ten-epic run's final run both stay under HISTORY_BOUND.
    assert one_count < HISTORY_BOUND, (
        f"the one-epic run's history ({one_count} events) already exceeds the "
        f"bound {HISTORY_BOUND} — the bound constant is too tight"
    )
    assert ten_count < HISTORY_BOUND, (
        f"the ten-epic run's final history had {ten_count} events, over the "
        f"bound {HISTORY_BOUND} — continue-as-new is not bounding each run to a "
        "constant; a single run is piling all ten epics into one history"
    )
    # The ten-epic run's final history is not larger than the one-epic run's
    # by more than a small constant — the carry-over is fixed-size, so the
    # final pass's work is the same shape regardless of how many epics
    # preceded it.
    assert ten_count <= one_count + 40, (
        f"history grew with N: one-epic final run had {one_count} events, "
        f"ten-epic final run had {ten_count} — continue-as-new is not bounding "
        "each run to a constant"
    )


async def test_ten_epics_all_land_and_each_run_is_bounded(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """SC-003 / acceptance 1: ten sequential epics all land, and every run's
    history stays under the fixed constant.

    The roadmap processes ten epics through continue-as-new; every spec lands
    (the observed landings survive each run boundary in the carry-over), and
    the final run's history is under `HISTORY_BOUND` — the constant SC-003
    names. A single run that held all ten epics would blow the bound by an
    order of magnitude; continue-as-new is what keeps it.
    """
    specs_root = _write_chain(tmp_path, 10)
    world = RoadmapWorld()
    async with run_roadmap(env, world, str(specs_root)) as handle:
        status: RoadmapStatus = await handle.result()
        count = await _history_event_count(handle)

    # All ten landed (the carry-over's observed landings survived every CAN).
    landed = [s.spec_dir for s in status.specs if s.landed]
    assert len(landed) == 10, f"expected 10 landed, got {landed}"
    # The final run's history is under the fixed constant (SC-003).
    assert count < HISTORY_BOUND, (
        f"the ten-epic run's final history had {count} events, over the bound "
        f"{HISTORY_BOUND} — continue-as-new is not bounding each run"
    )


async def test_state_survives_continue_as_new(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """FR-007: parked findings and observed landings survive continue-as-new.

    A spec whose pre-dispatch refuses parks with its finding; a spec that lands
    is observed-landed. Across the continue-as-new boundary the new run must
    carry both through its carry-over input: the parked spec does not
    re-dispatch (it was already tried), and a landed spec is reported landed
    in the final status (its observed landing survived the carry-over).

    Eight specs: `001-parked` refuses at preflight and parks; `002`–`008` land.
    With the bound at one the roadmap runs them serially, continue-as-new
    after each child concludes, so the parked finding and the seven observed
    landings must each survive seven run boundaries in the carry-over. A
    single run that held all eight would blow `HISTORY_BOUND`; continue-as-new
    is what keeps it, and the carry-over is what keeps the state across it.
    """
    from factory.workgraph.preflight import PreflightFinding

    specs: dict[str, dict[str, Any]] = {"001-parked": dict(state=SpecState.READY)}
    for i in range(2, 9):
        specs[f"{i:03d}-lands"] = dict(state=SpecState.READY)
    specs_root = build_corpus(tmp_path, specs)
    refusal = PreflightFinding(
        check="model-aliases-served",
        passed=False,
        detail="the proxy does not serve every alias this registry names.",
    )
    world = RoadmapWorld(
        preflight=lambda epic_id: [refusal] if epic_id == "001-parked" else []
    )
    async with run_roadmap(env, world, str(specs_root)) as handle:
        status: RoadmapStatus = await handle.result()
        count = await _history_event_count(handle)

    # Continue-as-new happened (the final run's history is bounded).
    assert count < HISTORY_BOUND, (
        f"final history had {count} events — continue-as-new did not bound the "
        "run, so the carry-over was never exercised"
    )
    # The parked finding survived continue-as-new (carried in the carry-over).
    parked = {p.spec_dir: p for p in status.parked}
    assert "001-parked" in parked, f"parked finding lost across CAN: {status.parked}"
    assert parked["001-parked"].detail == refusal.detail
    # Every landing spec's observed landing survived continue-as-new.
    by_dir = {s.spec_dir: s for s in status.specs}
    for i in range(2, 9):
        name = f"{i:03d}-lands"
        assert by_dir[name].landed is True, (
            f"observed landing for {name} lost across CAN: {status.specs}"
        )


async def test_continue_as_new_never_fires_with_a_child_open(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """FR-007 / the lost-event risk: continue-as-new fires only at quiescence.

    The one moment continue-as-new is safe is when zero children are open — a
    child finishing mid-CAN would notify a corpse and lose its completion. The
    roadmap must not continue-as-new while a child is in flight; the in-flight
    child finishes first, then the boundary.

    Eight independent `ready` specs with the bound at one: each dispatches,
    completes, and *then* (zero children open) the roadmap continues-as-new —
    never CAN while a child is still running. The scripted epic reports the
    in-flight set the capacity seam also sees, so the bound of one gates each
    next spec until the current one completes. The final status reports no
    child running — the roadmap never CAN'd over an open child — and every
    spec landed across the CAN chain. A single run that held all eight would
    blow `HISTORY_BOUND`; the bounded final history is the proof the chain of
    quiescent boundaries happened.
    """
    specs_root = _write_chain(tmp_path, 8)

    # The scripted epic reports the in-flight set the capacity seam also sees,
    # so the bound of one gates each next spec until the current completes —
    # and the roadmap's status never lies about a child being in flight.
    open_state: set[str] = set()

    def on_dispatch(epic_id: str) -> None:
        open_state.add(f"epic-{epic_id}")

    def on_complete(epic_id: str) -> None:
        open_state.discard(f"epic-{epic_id}")

    world = RoadmapWorld(open_epics=lambda: set(open_state))
    async with run_roadmap(
        env,
        world,
        str(specs_root),
        on_dispatch=on_dispatch,
        on_complete=on_complete,
    ) as handle:
        await handle.result()
        # At the run's end (after all continue-as-new boundaries), no child is
        # in flight — CAN never fired over an open child.
        status: RoadmapStatus = await handle.query(
            "roadmap_status", result_type=RoadmapStatus
        )
        count = await _history_event_count(handle)

    assert status.running == [], (
        f"a child was in flight at a continue-as-new boundary: {status.running}"
    )
    # Every spec landed across the CAN chain.
    landed = [s.spec_dir for s in status.specs if s.landed]
    assert len(landed) == 8, f"expected 8 landed, got {landed}"
    # And continue-as-new bounded the run.
    assert count < HISTORY_BOUND, (
        f"final history had {count} events — continue-as-new did not bound the run"
    )


async def test_a_restart_re_reads_the_world_and_does_not_double_dispatch(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """SC-004 / FR-007: a run that resumes after continue-as-new re-reads the
    world and does not re-dispatch a spec already observed-landed.

    The carry-over carries observed landings forward; the new run re-reads the
    corpus (so a spec edited to `ready` between runs is seen) but does not
    re-dispatch a spec it already watched land — re-dispatching would
    double-charge a slot and re-run work whose result the carry-over holds.

    Eight `ready` specs land across the continue-as-new chain; each dispatches
    exactly once (the carry-over's observed landings stop every new run
    re-dispatching a spec a previous run already watched land). A single run
    that held all eight would blow `HISTORY_BOUND`; the bounded final history
    is the proof the chain of runs happened, and the per-spec dispatch count of
    one is the proof the carry-over stopped the double-dispatch.
    """
    specs_root = _write_chain(tmp_path, 8)

    # Count dispatches per spec across the whole run (every CAN run included):
    # each ready spec dispatches exactly once, never twice.
    dispatches: list[str] = []

    def on_dispatch(epic_id: str) -> None:
        dispatches.append(epic_id)

    world = RoadmapWorld()
    async with run_roadmap(env, world, str(specs_root), on_dispatch=on_dispatch) as handle:
        status: RoadmapStatus = await handle.result()
        count = await _history_event_count(handle)

    # Each of the eight ready specs dispatched exactly once — no double-dispatch
    # across the continue-as-new chain (the carry-over's observed landings
    # stopped every new run re-dispatching a spec a previous run landed).
    assert len(dispatches) == 8, dispatches
    assert len(set(dispatches)) == 8, f"a spec dispatched twice: {dispatches}"
    # Every spec landed; the carry-over carried the landings across each CAN.
    landed = [s.spec_dir for s in status.specs if s.landed]
    assert len(landed) == 8, f"expected 8 landed, got {landed}"
    # The final run's history is bounded — continue-as-new happened.
    assert count < HISTORY_BOUND, (
        f"final history had {count} events — continue-as-new did not bound the run"
    )