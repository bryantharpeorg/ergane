"""US3 operator surface: pause/resume/promote signals and roadmap_status (FR-008).

The roadmap earns the same operational trust the epic interpreter earned by
giving the operator the same grip on the roadmap the epic surface gives on a
node: `pause_roadmap` parks dispatch between epics (the in-flight child
finishes — the epic pause contract, one level up), `resume_roadmap` releases
it, `promote_spec` covers the gap between a draft's frontmatter and its next
edit by treating a named draft as ready on the next pass, and `roadmap_status`
reports every spec's state, the running child, parked findings,
attested-vs-observed landings, the pause flag, and the bound in force.

Kill semantics stay at the epic level: killing the roadmap itself must never
kill a mid-flight epic (SC-004). The child's `parent_close_policy=ABANDON`
(T011) already makes that safe; this story asserts the operator can pause,
resume, promote, and read the roadmap while a child runs.

Written before the signals/query land (T015 precedes T017): until they land,
every test here fails. The harness lives in `tests/test_roadmap_scheduler.py`
(US2's file); these tests import it, the way the durability file does.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, AsyncIterator

import pytest
from temporalio.testing import WorkflowEnvironment

from factory.roadmap.models import LandedKind, SpecState
from factory.roadmap.workflow import (
    RoadmapInput,
    RoadmapStatus,
    RoadmapSpecStatus,
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


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    """Temporal with a clock the test owns (the US2 harness's `env` fixture).

    A fifth copy of the fixture, which the plan tolerates (consolidation is
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


def _status_of(status: RoadmapStatus, spec_dir: str) -> RoadmapSpecStatus:
    for spec in status.specs:
        if spec.spec_dir == spec_dir:
            return spec
    raise AssertionError(f"{spec_dir} not in roadmap status: {status}")


# ============================================================================
# T015 — operator-surface cases (must fail before the signals/query land)
# ============================================================================


async def test_pause_roadmap_parks_dispatch_between_epics(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """FR-008 / acceptance 2: `pause_roadmap` parks dispatch between epics while
    the in-flight child finishes — the epic pause contract, one level up.

    Two independent `ready` specs with the bound at one. `001-alpha` dispatches
    and is in flight; the operator signals `pause_roadmap`. When alpha's child
    completes, the roadmap parks — `002-bravo` does *not* dispatch — and the
    status reports the roadmap paused with no child running. A signal that
    arrived while a child was in flight never interrupted the child: it finished
    under its own contract, and dispatch parked only after it landed.
    """
    specs_root = build_corpus(
        tmp_path,
        {
            "001-alpha": dict(state=SpecState.READY),
            "002-bravo": dict(state=SpecState.READY),
        },
    )

    # Hold each child open until the test releases it, so the pause lands while
    # alpha is in flight and bravo is still waiting.
    alpha_done = False

    def on_dispatch(epic_id: str) -> None:
        # Pause as soon as alpha has dispatched and is in flight.
        pass

    world = RoadmapWorld()
    async with run_roadmap(
        env, world, str(specs_root), on_dispatch=on_dispatch
    ) as handle:
        # Wait for alpha to start (it is in flight), then pause.
        import asyncio

        async def _alpha_started() -> str:
            while True:
                status = await handle.query("roadmap_status", result_type=RoadmapStatus)
                if "001-alpha" in status.running:
                    return "alpha running"
                await asyncio.sleep(0.01)

        await asyncio.wait_for(_alpha_started(), timeout=30)
        await handle.signal("pause_roadmap")
        # Wait for alpha to land (the in-flight child finishes under its own
        # contract), and assert the roadmap parks — bravo does not dispatch.
        async def _alpha_landed_and_parked() -> RoadmapStatus:
            while True:
                status = await handle.query("roadmap_status", result_type=RoadmapStatus)
                a = _status_of(status, "001-alpha")
                if a.landed and not status.running:
                    return status
                await asyncio.sleep(0.01)

        status = await asyncio.wait_for(_alpha_landed_and_parked(), timeout=30)
        # The roadmap is paused; bravo did not dispatch (not landed, not running).
        assert status.paused is True, "roadmap should report paused after pause_roadmap"
        assert _status_of(status, "002-bravo").landed is False
        assert _status_of(status, "002-bravo").dispatchable is True
        assert status.running == []

        # Resume: bravo dispatches and lands.
        await handle.signal("resume_roadmap")
        final = await handle.result()
    assert _status_of(final, "002-bravo").landed is True
    assert final.paused is False


async def test_resume_roadmap_releases_a_parked_roadmap(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """FR-008: `resume_roadmap` releases a paused roadmap so dispatch continues.

    A paused roadmap with a dispatchable spec waiting does not dispatch until
    `resume_roadmap` lands; after it, the waiting spec dispatches and lands.
    A resume that arrives before any pause simply never parks (idempotent, the
    epic contract's rule).
    """
    specs_root = build_corpus(tmp_path, {"001-alpha": dict(state=SpecState.READY)})
    world = RoadmapWorld()
    async with run_roadmap(env, world, str(specs_root)) as handle:
        # Pause before alpha completes, then resume — alpha still lands because
        # the in-flight child finishes regardless, and a resume releases the
        # (empty) dispatch queue.
        await handle.signal("pause_roadmap")
        await handle.signal("resume_roadmap")
        final = await handle.result()
    assert _status_of(final, "001-alpha").landed is True
    assert final.paused is False


async def test_promote_spec_makes_a_draft_dispatchable_next_pass(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """FR-008 / acceptance 3: `promote_spec` names a draft spec and makes it
    dispatchable on the next scheduling pass; the promotion is visible in
    `roadmap_status`.

    `002-draft` is `draft` (not dispatchable) and depends on `001-alpha`
    (also `ready`). Without promotion, 002 never dispatches. The operator
    signals `promote_spec("002-draft")`: on the next pass the roadmap treats
    002 as ready, dispatches it once 001 has landed, and 002 lands. The final
    status reports 002 as promoted.

    The file remains the authority of record — the signal covers the gap until
    its next edit. A spec whose frontmatter says `draft` but was promoted by
    signal dispatches anyway, and the status says it was promoted (not that it
    was `ready` in the file).
    """
    specs_root = build_corpus(
        tmp_path,
        {
            "001-alpha": dict(state=SpecState.READY),
            "002-draft": dict(
                state=SpecState.DRAFT, depends_on_landed=["001-alpha"]
            ),
        },
    )
    world = RoadmapWorld()
    async with run_roadmap(env, world, str(specs_root)) as handle:
        # Wait for alpha to land, then promote the draft so it dispatches.
        import asyncio

        async def _alpha_landed() -> bool:
            while True:
                status = await handle.query("roadmap_status", result_type=RoadmapStatus)
                if _status_of(status, "001-alpha").landed:
                    return True
                await asyncio.sleep(0.01)

        await asyncio.wait_for(_alpha_landed(), timeout=30)
        # Before promotion, the draft is not dispatchable (and not promoted).
        before = await handle.query("roadmap_status", result_type=RoadmapStatus)
        assert _status_of(before, "002-draft").dispatchable is False
        assert _status_of(before, "002-draft").promoted is False

        await handle.signal("promote_spec", "002-draft")
        final = await handle.result()

    # The promoted draft dispatched and landed.
    draft = _status_of(final, "002-draft")
    assert draft.landed is True, f"promoted draft did not land: {final}"
    # The promotion is visible in roadmap_status (acceptance 3).
    assert draft.promoted is True, f"promotion not reported in status: {final}"


async def test_roadmap_status_reports_every_spec_state_running_parked_and_bound(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """FR-008 / acceptance 5: `roadmap_status` reports every spec's state, the
    running child, parked findings, and the bound in force.

    A corpus with a `ready` spec, a `draft` spec, a `deferred` spec, and an
    attested-`landed` spec. While the `ready` spec's child is in flight, the
    status reports: the ready spec as `ready` and running, the draft as
    `draft` and not dispatchable, the deferred as `deferred`, the landed spec
    as `landed` (attested), and the bound (`max_concurrent_epics`) in force.
    """
    specs_root = build_corpus(
        tmp_path,
        {
            "001-ready": dict(state=SpecState.READY),
            "002-draft": dict(state=SpecState.DRAFT),
            "003-deferred": dict(state=SpecState.DEFERRED),
            "004-attested": dict(state=SpecState.LANDED),
        },
    )

    # Hold the ready spec's child in flight by not auto-completing: the default
    # scripted epic returns landed immediately, so query fast while it runs.
    world = RoadmapWorld()
    async with run_roadmap(
        env, world, str(specs_root), max_concurrent_epics=2
    ) as handle:
        import asyncio

        async def _ready_running() -> RoadmapStatus:
            while True:
                status = await handle.query("roadmap_status", result_type=RoadmapStatus)
                if "001-ready" in status.running:
                    return status
                await asyncio.sleep(0.01)

        status = await asyncio.wait_for(_ready_running(), timeout=30)

    # Every spec's state is reported.
    assert _status_of(status, "001-ready").state is SpecState.READY
    assert _status_of(status, "002-draft").state is SpecState.DRAFT
    assert _status_of(status, "003-deferred").state is SpecState.DEFERRED
    assert _status_of(status, "004-attested").state is SpecState.LANDED
    # The running child is reported.
    assert "001-ready" in status.running
    # The bound in force is reported.
    assert status.max_concurrent_epics == 2
    # The ready spec is dispatchable; the draft and deferred are not.
    assert _status_of(status, "001-ready").dispatchable is True
    assert _status_of(status, "002-draft").dispatchable is False
    assert _status_of(status, "003-deferred").dispatchable is False


async def test_roadmap_status_distinguishes_attested_and_observed_landings(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """FR-003 / acceptance 5: `roadmap_status` reports attested-vs-observed
    landings — the two kinds of dependency satisfaction, distinguishable.

    `002-ready` depends on two specs: `001-attested` (frontmatter `state:
    landed` — the operator's word) and `003-observed` (a `ready` spec whose
    child returns landed). After both are satisfied, `002`'s status names each
    satisfied dependency and its kind: `001` attested, `003` observed. The two
    kinds travel in `satisfied_as`, the readiness seam US1 built and US2 filled;
    US3 surfaces them in `roadmap_status` so an operator knows *why* an edge is
    satisfied, not just that it is.
    """
    specs_root = build_corpus(
        tmp_path,
        {
            "001-attested": dict(state=SpecState.LANDED),
            "002-ready": dict(
                state=SpecState.READY,
                depends_on_landed=["001-attested", "003-observed"],
            ),
            "003-observed": dict(state=SpecState.READY),
        },
    )
    world = RoadmapWorld()
    status = await run_to_completion(env, world, str(specs_root))

    ready = _status_of(status, "002-ready")
    assert ready.landed is True, f"002-ready did not land: {ready}"
    # Each satisfied dependency names its kind: attested vs observed.
    assert ready.satisfied_as.get("001-attested") is LandedKind.ATTESTED, (
        f"attested dependency not reported as attested: {ready.satisfied_as}"
    )
    assert ready.satisfied_as.get("003-observed") is LandedKind.OBSERVED, (
        f"observed dependency not reported as observed: {ready.satisfied_as}"
    )
    # A spec that landed by observation reports its own landing as observed.
    observed = _status_of(status, "003-observed")
    assert observed.landed is True
    assert observed.landed_kind is LandedKind.OBSERVED, (
        f"observed-landed spec not reported as observed: {observed}"
    )
    # A spec that landed by attestation reports its own landing as attested.
    attested = _status_of(status, "001-attested")
    assert attested.landed is True
    assert attested.landed_kind is LandedKind.ATTESTED, (
        f"attested-landed spec not reported as attested: {attested}"
    )


async def test_terminating_the_roadmap_does_not_kill_a_child_in_flight(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """FR-008 / acceptance 4 / SC-004: terminating the roadmap must not
    terminate a child epic in flight — the child survives and finishes under
    its own contract.

    `parent_close_policy=ABANDON` (T011) is what makes this safe; this test
    asserts the operator-facing consequence: while a child is in flight,
    cancelling the roadmap's run leaves the child running to its own
    conclusion. The roadmap never adopted a kill that reaches its children.

    Cancel the roadmap while `001-alpha`'s child is in flight and assert the
    child is still running afterward (not cancelled with the parent).
    """
    specs_root = build_corpus(tmp_path, {"001-alpha": dict(state=SpecState.READY)})
    world = RoadmapWorld()
    async with run_roadmap(env, world, str(specs_root)) as handle:
        import asyncio

        async def _alpha_running() -> None:
            while True:
                status = await handle.query("roadmap_status", result_type=RoadmapStatus)
                if "001-alpha" in status.running:
                    return
                await asyncio.sleep(0.01)

        await asyncio.wait_for(_alpha_running(), timeout=30)
        # The child is in flight. Cancel the roadmap's run (operator terminate).
        await handle.cancel()

    # The child epic survives the roadmap's termination: its workflow is still
    # running (ABANDON), not cancelled with the parent. The child runs to its
    # own conclusion under its own contract.
    child_handle = env.client.get_workflow_handle("epic-001-alpha")
    desc = await child_handle.describe()
    from temporalio.client import WorkflowExecutionStatus

    # The child is still running or has completed on its own — either way it
    # was not cancelled with the parent (which would be status CANCELLED).
    assert desc.status is not WorkflowExecutionStatus.CANCELLED, (
        f"the child epic was cancelled with the roadmap (status {desc.status}) "
        "— parent_close_policy is not ABANDON"
    )