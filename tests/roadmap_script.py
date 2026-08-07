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

    @workflow.run
    async def run(self, request: EpicInput) -> EpicStatus:
        epic_id = request.graph.epic_id
        if _SCRIPT.on_dispatch is not None:
            _SCRIPT.on_dispatch(epic_id)
        status = _SCRIPT.statuses.get(epic_id)
        if status is None:
            status = _landed_status({"us1": _merged_node()})
        if _SCRIPT.on_complete is not None:
            _SCRIPT.on_complete(epic_id)
        return status