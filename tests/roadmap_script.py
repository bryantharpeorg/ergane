"""A scripted `EpicWorkflow` the roadmap scheduler tests dispatch to.

Lives in its own module — not the test file — because Temporalio forbids
`@workflow.run` on a local class *and* because the workflow sandbox traces
the defining module. Keeping the scripted workflow out of the test module
(which uses `pathlib` for its corpus fixtures) keeps the sandbox tracer from
flagging filesystem access the workflow never makes.

The class is registered under the real dispatch name `"EpicWorkflow"` so the
roadmap's `start_child_workflow(EpicWorkflow.run, ...)` resolves to it. A
test steers it through the module-level `_SCRIPT`: `statuses` maps a spec dir
to the `EpicStatus` its child returns (a spec with no entry lands by default),
and `on_dispatch` / `on_complete` hooks observe dispatch order and steer
capacity without a real Temporal list round trip.
"""

from __future__ import annotations

from typing import Callable

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from factory.workgraph.models import EpicState
    from factory.workgraph.workflow import EpicInput, EpicStatus, NodeState, NodeStatus
    from factory.mergequeue.models import LandingState


class _Script:
    """Per-test script the scripted `EpicWorkflow` reads at run time."""

    def __init__(self) -> None:
        self.statuses: dict[str, EpicStatus] = {}
        self.on_dispatch: Callable[[str], None] | None = None
        self.on_complete: Callable[[str], None] | None = None
        #: US3 (T015): specs whose children must stay open until the test
        #: releases them, so an operator signal or a `roadmap_status` query can
        #: observe a child *in flight*. The scripted epic returns instantly by
        #: default (US2's tests leave this empty); a spec in this set blocks on
        #: `wait_condition` until the test removes it, which is what makes
        #: `pause_roadmap` mid-flight and a `running`-child status observable.
        #: Additive only — unset, it changes nothing US2 relies on.
        self.hold: set[str] = set()

    def release(self, epic_id: str) -> None:
        """Drop a held child so it completes (the test's release signal)."""
        self.hold.discard(epic_id)


#: The single script tests set before starting the roadmap.
_SCRIPT = _Script()


def _landed_status(nodes: dict[str, NodeStatus]) -> EpicStatus:
    """COMPLETED with every node MERGED — landed."""
    return EpicStatus(epic_state=EpicState.COMPLETED, nodes=nodes)


def _merged_node(name: str = "us1") -> NodeStatus:
    """One MERGED node — the shape a landed single-story epic returns."""
    return NodeStatus(
        state=NodeState.MERGED,
        attempt=1,
        branch="factory/x/us1",
        verified=True,
        landing_state=LandingState.MERGED,
        pr_number=1,
    )


def _failed_node(name: str = "us1") -> NodeStatus:
    """One FAILED node — completed-but-not-landed (acceptance 4)."""
    return NodeStatus(
        state=NodeState.FAILED,
        attempt=1,
        branch="factory/x/us1",
        verified=False,
        landing_state=None,
        pr_number=None,
    )


def landed_status(nodes: dict[str, NodeStatus] | None = None) -> EpicStatus:
    """Public helper: a landed `EpicStatus` (one MERGED node by default)."""
    return _landed_status(nodes or {"us1": _merged_node()})


def failed_status(nodes: dict[str, NodeStatus] | None = None) -> EpicStatus:
    """Public helper: a finished-but-not-landed `EpicStatus` (one FAILED node)."""
    return EpicStatus(
        epic_state=EpicState.COMPLETED,
        nodes=nodes or {"us1": _failed_node()},
    )


@workflow.defn(name="EpicWorkflow")
class ScriptedEpicWorkflow:
    """A scripted `EpicWorkflow` registered under the real dispatch name."""

    def __init__(self) -> None:
        self._released = False

    @workflow.run
    async def run(self, request: EpicInput) -> EpicStatus:
        epic_id = request.graph.epic_id
        if _SCRIPT.on_dispatch is not None:
            _SCRIPT.on_dispatch(epic_id)
        # US3 (T015): if the test held this child open, block here until the
        # test signals `release`. The dispatch hook above has already fired, so
        # the roadmap sees the child in flight (`_children` holds its handle)
        # and the test can query `running` or signal the roadmap mid-flight.
        # The hold is per-spec and opt-in; a spec not in the set never blocks,
        # so US2's run-to-completion tests are unaffected.
        if epic_id in _SCRIPT.hold:
            await workflow.wait_condition(lambda: self._released)
        status = _SCRIPT.statuses.get(epic_id)
        if status is None:
            status = _landed_status({"us1": _merged_node()})
        if _SCRIPT.on_complete is not None:
            _SCRIPT.on_complete(epic_id)
        return status

    @workflow.signal
    def release(self) -> None:
        """Test release: let a held child complete (the hold's counterpart)."""
        self._released = True


# --- blocker workflows for the T011 child-policy tests ------------------------
#
# Two helpers the collision/closed-id-reuse cases need: a workflow that holds
# an `epic-*` id open (so a roadmap dispatch collides with a RUNNING workflow)
# and one that completes immediately (so the id is a closed run the roadmap can
# reuse). Both live here, not in the test module, for the same reason
# `ScriptedEpicWorkflow` does: the workflow sandbox traces the defining module.


@workflow.defn(name="BlockerRunningWorkflow")
class BlockerRunningWorkflow:
    """Hold its workflow id open until a `release` signal arrives.

    Started under an `epic-<spec>` id before the roadmap runs, so the roadmap's
    `start_child_workflow(EpicWorkflow.run, id=epic-<spec>)` collides with a
    RUNNING workflow — the case T011 parks with the collision named, never
    adopts (the `ALLOW_DUPLICATE` policy does not let a new run take a live id).
    """

    @workflow.run
    async def run(self) -> str:
        await workflow.wait_condition(lambda: False)
        return "unreachable"

    @workflow.signal
    def release(self) -> None:
        """No-op signal so the blocker can be released if a test needs it."""
        # `wait_condition(lambda: False)` never resolves, so the blocker only
        # ends when the test cancels it; the signal exists so the worker accepts
        # a release call without an unknown-signal error.
        return None


@workflow.defn(name="BlockerDoneWorkflow")
class BlockerDoneWorkflow:
    """Complete immediately, leaving a closed run under its id.

    Started under an `epic-<spec>` id, it returns at once, so the id is a closed
    run when the roadmap later starts `epic-<spec>` — the `ALLOW_DUPLICATE`
    policy lets the new run reuse the closed id cleanly (tonight's
    five-closed-runs precedent, T011).
    """

    @workflow.run
    async def run(self) -> str:
        return "done"