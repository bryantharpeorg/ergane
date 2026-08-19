"""US1: the roadmap scheduler survives a child result it cannot read (FR-001/002/003/005/006).

A child epic that returns something the roadmap did not expect must cost that
epic its landed status, not the whole scheduler. These tests script the child
through `tests/roadmap_script.py` so the roadmap reaps `None` or a malformed
object instead of an `EpicStatus`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Interceptor
from temporalio.worker._interceptor import (
    WorkflowInboundInterceptor,
    WorkflowOutboundInterceptor,
)

from factory.roadmap.models import LandedKind, SpecState
from factory.roadmap.workflow import RoadmapWorkflow, _is_epic_status
from tests.roadmap_script import (
    ScriptedEpicWorkflow,
    _SCRIPT,
    _SCRIPT_RETURN_NONE,
    failed_status,
    landed_status,
)
from tests.test_roadmap_scheduler import (
    TARGET_REPO,
    RoadmapWorld,
    _status_of,
    build_corpus,
    run_to_completion,
)

PROXY_URL = "http://litellm.test"


@dataclass
class _MalformedResultSpec:
    """Which child spec dirs should return a raw malformed result."""

    spec_dirs: set[str] = field(default_factory=set)


class _MalformedResultInterceptor(Interceptor):
    """Let selected child specs return a raw value without type conversion.

    The SDK normally coerces a child workflow result into the return type the
    parent expects (`EpicStatus`). This interceptor widens `ret_type` to
    `None` for the selected children only, so a dict or object returned by
    `tests/roadmap_script.py` reaches the roadmap's reap path unchanged. Healthy
    children still convert normally.
    """

    def __init__(self, spec: _MalformedResultSpec) -> None:
        self._spec = spec

    def workflow_interceptor_class(self, input):
        spec = self._spec

        class _Inbound(WorkflowInboundInterceptor):
            def init(self, outbound):
                self.next.init(_Outbound(outbound, spec))

        return _Inbound


class _Outbound(WorkflowOutboundInterceptor):
    def __init__(self, next_outbound, spec: _MalformedResultSpec) -> None:
        super().__init__(next_outbound)
        self._spec = spec

    async def start_child_workflow(self, input):
        spec_dir = input.id.removeprefix("epic-")
        if spec_dir in self._spec.spec_dirs:
            input.ret_type = None
        return await self.next.start_child_workflow(input)


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    """Temporal with a clock the test owns."""
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


async def test_a_none_child_result_records_unlanded_and_dispatches_next_spec(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """US1-S1/S2: a child returning `None` does not raise, does not stall the line,
    and the next dispatchable spec is dispatched in the same run chain.

    `001-alpha` returns `None`; `002-bravo` depends on it and is `ready`, but a
    not-landed dependency blocks bravo. `003-charlie` is independent and ready,
    so it must still dispatch and land — the scheduler survived.
    """
    specs_root = build_corpus(
        tmp_path,
        {
            "001-alpha": dict(state=SpecState.READY),
            "002-bravo": dict(
                state=SpecState.READY, depends_on_landed=["001-alpha"]
            ),
            "003-charlie": dict(state=SpecState.READY),
        },
    )
    statuses = {"001-alpha": _SCRIPT_RETURN_NONE}

    status = await run_to_completion(env, RoadmapWorld(), str(specs_root), statuses=statuses)

    # alpha is recorded finished-but-not-landed, kind OBSERVED.
    alpha = _status_of(status, "001-alpha")
    assert alpha.landed is False
    assert alpha.landed_kind is LandedKind.OBSERVED

    # bravo is blocked by the unlanded dependency.
    bravo = _status_of(status, "002-bravo")
    assert bravo.dispatchable is False
    assert "001-alpha" in bravo.blockers
    assert "001-alpha" in bravo.unlanded

    # charlie dispatches and lands — the scheduler did not stop.
    assert _status_of(status, "003-charlie").landed is True
    assert status.running == []


@dataclass
class _MalformedEpicStatus:
    """An object with no `epic_state` attribute — wrong shape, non-null."""

    nodes: dict[str, Any]


def test_is_epic_status_rejects_none_malformed_object_and_dict():
    """US1-S4/S5: the runtime guard rejects `None`, dicts, and objects without
    the expected attributes, while accepting a real `EpicStatus`.
    """
    assert _is_epic_status(None) is False
    assert _is_epic_status({"epic_state": "COMPLETED"}) is False
    assert _is_epic_status(_MalformedEpicStatus(nodes={})) is False
    assert _is_epic_status(landed_status()) is True


async def test_a_malformed_child_result_records_unlanded_and_dispatches_next_spec(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """US1-S4: a non-null malformed value (no `epic_state`) takes the same path as
    `None`: not landed, kind OBSERVED, scheduler continues.
    """
    specs_root = build_corpus(
        tmp_path,
        {
            "001-alpha": dict(state=SpecState.READY),
            "002-bravo": dict(state=SpecState.READY),
        },
    )
    statuses = {"001-alpha": _MalformedEpicStatus(nodes={})}

    spec = _MalformedResultSpec(spec_dirs={"001-alpha"})
    status = await run_to_completion(
        env,
        RoadmapWorld(),
        str(specs_root),
        statuses=statuses,
        interceptors=[_MalformedResultInterceptor(spec)],
    )

    alpha = _status_of(status, "001-alpha")
    assert alpha.landed is False
    assert alpha.landed_kind is LandedKind.OBSERVED
    assert _status_of(status, "002-bravo").landed is True
    assert status.running == []


async def test_a_dict_child_result_records_unlanded_and_dispatches_next_spec(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """US1-S4 (alternate malformed shape): a dict returned instead of an
    `EpicStatus` is treated the same way.
    """
    specs_root = build_corpus(
        tmp_path,
        {
            "001-alpha": dict(state=SpecState.READY),
            "002-bravo": dict(state=SpecState.READY),
        },
    )
    statuses = {"001-alpha": {"epic_state": "COMPLETED"}}

    spec = _MalformedResultSpec(spec_dirs={"001-alpha"})
    status = await run_to_completion(
        env,
        RoadmapWorld(),
        str(specs_root),
        statuses=statuses,
        interceptors=[_MalformedResultInterceptor(spec)],
    )

    alpha = _status_of(status, "001-alpha")
    assert alpha.landed is False
    assert alpha.landed_kind is LandedKind.OBSERVED
    assert _status_of(status, "002-bravo").landed is True
    assert status.running == []


async def test_guard_is_a_runtime_check_not_an_annotation(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """US1-S5: the check is a runtime guard, not a type annotation.

    A child returning a dict (no `EpicStatus` shell) is recorded
    finished-but-not-landed and the scheduler continues. If the guard is removed,
    the dict reaches `_landed_status_for` and an `AttributeError` fails the
    workflow — this test fails.

    Verification transcript (guard removed):

    $ uv run pytest -q tests/test_roadmap_child_result.py::test_guard_is_a_runtime_check_not_an_annotation --tb=short
    F
    =================================== FAILURES ===================================
    _______________ test_guard_is_a_runtime_check_not_an_annotation ________________
    temporalio.exceptions.ApplicationError: AttributeError: 'dict' object has no attribute 'epic_state'
    The above exception was the direct cause of the following exception:
    ...
    E       ApplicationError: AttributeError: 'dict' object has no attribute 'epic_state'
    tests/test_roadmap_child_result.py:242: in test_guard_is_a_runtime_check_not_an_annotation
    ...
    1 failed in 0.33s
    """
    specs_root = build_corpus(
        tmp_path,
        {
            "001-alpha": dict(state=SpecState.READY),
            "002-bravo": dict(state=SpecState.READY),
        },
    )
    statuses = {"001-alpha": {"epic_state": "COMPLETED"}}

    spec = _MalformedResultSpec(spec_dirs={"001-alpha"})
    status = await run_to_completion(
        env,
        RoadmapWorld(),
        str(specs_root),
        statuses=statuses,
        interceptors=[_MalformedResultInterceptor(spec)],
    )

    alpha = _status_of(status, "001-alpha")
    assert alpha.landed is False
    assert alpha.landed_kind is LandedKind.OBSERVED
    assert _status_of(status, "002-bravo").landed is True
    assert status.running == []


async def test_well_formed_epic_status_derives_landed_unchanged(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """US1-S6: the healthy path is untouched. A well-formed `EpicStatus` lands when
    completed with all MERGED nodes and stays not-landed when it has a FAILED node.
    """
    specs_root = build_corpus(
        tmp_path,
        {
            "001-landed": dict(state=SpecState.READY),
            "002-failed": dict(state=SpecState.READY),
        },
    )
    statuses = {
        "001-landed": landed_status(),
        "002-failed": failed_status(),
    }

    status = await run_to_completion(env, RoadmapWorld(), str(specs_root), statuses=statuses)

    landed = _status_of(status, "001-landed")
    assert landed.landed is True
    assert landed.landed_kind is LandedKind.OBSERVED

    not_landed = _status_of(status, "002-failed")
    assert not_landed.landed is False
    assert not_landed.landed_kind is LandedKind.OBSERVED
    assert status.running == []
