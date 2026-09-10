"""US3 of 131: a ready spec whose stories have already landed is not paid for."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, AsyncIterator

import pytest
from temporalio.testing import WorkflowEnvironment

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


async def test_query_agrees_with_the_pass_about_a_built_spec(
    env: WorkflowEnvironment,
    tmp_path: Path,
) -> None:
    """US3-S2: the read-only query uses the pass's cached landed answer."""
    specs_root = build_corpus(
        tmp_path,
        {"001-built": dict(state=SpecState.READY)},
    )
    world = RoadmapWorld(
        landed_runner=_built_landed("001-built"),
        drift_runner=lambda request: False,
    )

    async with run_roadmap(
        env,
        world,
        str(specs_root),
        hold_specs={"epic-001-built"},
    ) as handle:
        queried: RoadmapStatus | None = None
        for _ in range(100):
            candidate = await handle.query(
                "roadmap_status", result_type=RoadmapStatus
            )
            if candidate.specs:
                queried = candidate
                break
            await asyncio.sleep(0.01)
        assert queried is not None
        built = next(spec for spec in queried.specs if spec.spec_dir == "001-built")

    assert built.dispatchable is False
    assert built.rendered_state == "built"
    assert built.landed is True
    assert built.landed_kind is LandedKind.OBSERVED


async def test_a_spec_with_outstanding_work_still_clones_onboards_and_dispatches(
    env: WorkflowEnvironment,
    tmp_path: Path,
) -> None:
    """US3-S3: the new guard does not swallow genuine work."""
    specs_root = build_corpus(
        tmp_path,
        {"001-real": dict(state=SpecState.READY)},
    )
    world = RoadmapWorld()
    activity_names: list[str] = []
    child_starts: list[str] = []

    async with run_roadmap(
        env,
        world,
        str(specs_root),
        on_dispatch=child_starts.append,
        interceptors=[_ActivityRecordingInterceptor(activity_names)],
    ) as handle:
        status = await handle.result()

    assert child_starts == ["001-real"]
    assert "clone_target" in activity_names
    assert "onboard_target" in activity_names
    real = next(spec for spec in status.specs if spec.spec_dir == "001-real")
    assert real.dispatchable is False
    assert real.landed is True


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
