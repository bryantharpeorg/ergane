"""US3 of 131: a ready spec whose stories have already landed is not paid for."""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator
from typing import Any, AsyncIterator

import pytest
from temporalio.testing import WorkflowEnvironment

from factory.activities import roadmap_activities
from factory.roadmap.models import LandedKind, LandedStatus, SpecState
from factory.roadmap.workflow import RoadmapStatus
from tests.roadmap_script import _SCRIPT
from tests.test_roadmap_scheduler import (
    RoadmapWorld,
    _ActivityRecordingInterceptor,
    build_corpus,
    run_roadmap,
)


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
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


def _built_landed(spec_dir: str):
    def resolve(request: Any) -> LandedStatus | None:
        if request.spec_dir == spec_dir:
            return LandedStatus(landed=True, kind=LandedKind.OBSERVED)
        return None

    return resolve


async def test_built_ready_spec_never_reaches_clone_or_onboard(
    env: WorkflowEnvironment,
    tmp_path: Path,
) -> None:
    """US3-S1: the guard happens at selection, before dispatch activities."""
    specs_root = build_corpus(
        tmp_path,
        {
            "001-built": dict(state=SpecState.READY),
            "002-real": dict(state=SpecState.READY),
        },
    )
    world = RoadmapWorld(
        landed_runner=_built_landed("001-built"),
        drift_runner=lambda request: False,
    )
    activity_names: list[str] = []
    child_starts: list[str] = []

    async with run_roadmap(
        env,
        world,
        str(specs_root),
        max_concurrent_epics=2,
        on_dispatch=child_starts.append,
        interceptors=[_ActivityRecordingInterceptor(activity_names)],
    ) as handle:
        status: RoadmapStatus = await handle.result()

    built = next(spec for spec in status.specs if spec.spec_dir == "001-built")
    assert built.dispatchable is False
    assert built.rendered_state == "built"
    assert all("001-built" not in child_id for child_id in child_starts)
    assert "clone_target" not in activity_names
    assert "onboard_target" not in activity_names
