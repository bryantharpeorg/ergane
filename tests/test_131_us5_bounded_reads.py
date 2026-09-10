"""US5 of 131: the roadmap's landed read is bounded and paid for once."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest
from temporalio.testing import WorkflowEnvironment

from factory.activities import roadmap_activities as ra
from factory.roadmap.models import LandedKind, LandedStatus, SpecState
from factory.roadmap.workflow import (
    _FAST,
    RoadmapStatus,
    RoadmapWorkflow,
)
from factory.worker import ACTIVITIES
from tests.roadmap_script import _SCRIPT
from tests.test_roadmap_scheduler import (
    RoadmapWorld,
    _ActivityRecordingInterceptor,
    build_corpus,
    run_roadmap,
)


BLOCK_S = 0.30
TICK_S = 0.01
MIN_TICKS = 5


def _activity_is_registered(activities: list[object], target: object) -> bool:
    """Return whether the worker's registration set names this activity."""
    return any(activity is target for activity in activities)


@pytest.fixture
async def temporal_env() -> Any:
    """Give scheduler tests a server, and restore the shared script state."""
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


def _activity_names_and_specs(calls: list[tuple[str, str | None]]) -> list[str]:
    return [f"{name}:{spec_dir}" for name, spec_dir in calls]


def _first_pass_calls(calls: list[tuple[str, str | None]]) -> list[tuple[str, str | None]]:
    """Isolate the activities between the first and second corpus reads."""
    read_indexes = [index for index, (name, _) in enumerate(calls) if name == "read_corpus_activity"]
    if len(read_indexes) < 2:
        return calls
    return calls[read_indexes[0] : read_indexes[1]]


@pytest.mark.asyncio
async def test_landed_for_spec_does_not_block_the_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The landed read leaves the worker loop free while git is blocked."""
    ticks = 0
    stop = False

    def slow_landed_from_git(_request: Any) -> None:
        time.sleep(BLOCK_S)

    async def ticker() -> None:
        nonlocal ticks
        while not stop:
            await asyncio.sleep(TICK_S)
            ticks += 1

    monkeypatch.setattr(ra, "_landed_runner", None)
    monkeypatch.setattr(ra, "_landed_from_git", slow_landed_from_git)
    request = ra.LandedInput(target_repo="/nonexistent", spec_dir="specs/x", spec_text="")
    ticker_task = asyncio.create_task(ticker())
    try:
        result = await ra.landed_for_spec(request)
    finally:
        stop = True
        ticker_task.cancel()
        try:
            await ticker_task
        except asyncio.CancelledError:
            pass

    assert result is None
    assert ticks >= MIN_TICKS


@pytest.mark.asyncio
async def test_landed_for_spec_test_detects_an_on_loop_git_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A scripted on-loop read starves the same ticker the activity control uses."""
    ticks = 0
    stop = False

    def slow_landed_runner(_request: Any) -> None:
        time.sleep(BLOCK_S)

    async def ticker() -> None:
        nonlocal ticks
        while not stop:
            await asyncio.sleep(TICK_S)
            ticks += 1

    monkeypatch.setattr(ra, "_landed_runner", slow_landed_runner)
    request = ra.LandedInput(target_repo="/nonexistent", spec_dir="specs/x", spec_text="")
    ticker_task = asyncio.create_task(ticker())
    try:
        result = await ra.landed_for_spec(request)
    finally:
        stop = True
        ticker_task.cancel()
        try:
            await ticker_task
        except asyncio.CancelledError:
            pass

    assert result is None
    assert ticks < MIN_TICKS


def test_landed_for_spec_is_registered_on_the_worker() -> None:
    """A workflow call to an unregistered activity is a timeout, not an import error."""
    assert _activity_is_registered(ACTIVITIES, ra.landed_for_spec)


def test_registration_test_detects_a_missing_activity() -> None:
    """The registration control notices the exact one-line omission it guards."""
    faulted = [activity for activity in ACTIVITIES if activity is not ra.landed_for_spec]
    assert not _activity_is_registered(faulted, ra.landed_for_spec)


async def _activity_calls(
    temporal_env: WorkflowEnvironment,
    specs_root: Path,
    world: RoadmapWorld,
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[str, str | None]]:
    calls: list[tuple[str, str | None]] = []
    async with run_roadmap(
        temporal_env,
        world,
        str(specs_root),
        idle_rescan_s=1,
        interceptors=[_ActivityRecordingInterceptor(calls)],
    ) as handle:
        await asyncio.sleep(0.05)
        for _ in range(200):
            read_count = sum(1 for name, _ in calls if name == "read_corpus_activity")
            if read_count >= 2:
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)
        await handle.cancel()
    monkeypatch.undo()
    return calls


def _make_unbounded_landed() -> Any:
    """Fault injection: widen the landed read to every declared state."""
    from temporalio import workflow

    async def compute_landed(self: Any, request: Any) -> dict[str, LandedStatus | None]:
        landed: dict[str, LandedStatus | None] = {}
        for entry in self._roadmap.entries:
            spec_text = await self._spec_text(request.specs_root, entry.spec_dir)
            landed[entry.spec_dir] = await workflow.execute_activity(
                ra.landed_for_spec,
                ra.LandedInput(
                    target_repo=request.target_repo,
                    spec_dir=entry.spec_dir,
                spec_text=spec_text,
                ),
                **_FAST,
            )
        return landed

    return compute_landed


@pytest.mark.asyncio
async def test_roadmap_landed_read_is_bounded_to_ready_and_drift_to_landed(
    temporal_env: WorkflowEnvironment,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One pass reads each ready spec and drifts only a supplied landed answer."""
    specs_root = build_corpus(
        tmp_path,
        {
            "001-built": dict(state=SpecState.READY),
            "002-unfinished": dict(state=SpecState.READY),
            "003-draft": dict(state=SpecState.DRAFT),
            "004-deferred": dict(state=SpecState.DEFERRED),
            "005-landed": dict(state=SpecState.LANDED),
        },
    )

    def landed(request: Any) -> LandedStatus | None:
        if request.spec_dir == "001-built":
            return LandedStatus(landed=True, kind=LandedKind.OBSERVED)
        return None

    calls = await _activity_calls(
        temporal_env,
        specs_root,
        RoadmapWorld(landed_runner=landed),
        monkeypatch,
    )
    first_pass = _first_pass_calls(calls)
    landed_calls = [name for name in _activity_names_and_specs(first_pass) if name.startswith("landed_for_spec:")]
    drift_calls = [name for name in _activity_names_and_specs(first_pass) if name.startswith("drift_for_spec:")]

    assert landed_calls == [
        "landed_for_spec:001-built",
        "landed_for_spec:002-unfinished",
    ]
    assert drift_calls == [
        "drift_for_spec:001-built",
        "drift_for_spec:005-landed",
    ]


@pytest.mark.asyncio
async def test_cost_control_detects_an_unbounded_landed_read(
    temporal_env: WorkflowEnvironment,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same corpus fails the bound when the ready-only gate is removed."""
    specs_root = build_corpus(
        tmp_path,
        {
            "001-built": dict(state=SpecState.READY),
            "002-unfinished": dict(state=SpecState.READY),
            "003-draft": dict(state=SpecState.DRAFT),
            "004-deferred": dict(state=SpecState.DEFERRED),
            "005-landed": dict(state=SpecState.LANDED),
        },
    )
    monkeypatch.setattr(RoadmapWorkflow, "_compute_landed", _make_unbounded_landed())
    calls = await _activity_calls(
        temporal_env,
        specs_root,
        RoadmapWorld(),
        monkeypatch,
    )
    landed_calls = [
        name
        for name in _activity_names_and_specs(_first_pass_calls(calls))
        if name.startswith("landed_for_spec:")
    ]

    assert len(landed_calls) == 5


@pytest.mark.asyncio
async def test_a_built_but_drifted_ready_spec_is_read_and_dispatched(
    temporal_env: WorkflowEnvironment,
    tmp_path: Path,
) -> None:
    """A real drift answer keeps an amendment in the dispatchable work."""
    specs_root = build_corpus(tmp_path, {"001-amended": dict(state=SpecState.READY)})
    world = RoadmapWorld(
        landed_runner=lambda _request: LandedStatus(
            landed=True, kind=LandedKind.OBSERVED
        ),
        drift_runner=lambda _request: True,
    )
    activity_calls: list[tuple[str, str | None]] = []
    child_starts: list[str] = []
    async with run_roadmap(
        temporal_env,
        world,
        str(specs_root),
        on_dispatch=child_starts.append,
        interceptors=[_ActivityRecordingInterceptor(activity_calls)],
    ) as handle:
        status = await handle.result()

    drift_calls = [
        name
        for name in _activity_names_and_specs(activity_calls)
        if name.startswith("drift_for_spec:")
    ]
    assert drift_calls == ["drift_for_spec:001-amended"]
    assert child_starts == ["001-amended"]
    assert world.clone_calls == ["/srv/factory/targets/library"]
    assert any(name == "onboard_target" for name, _ in activity_calls)


def _ready_only_drift() -> Any:
    """Fault injection: narrow the drift read away from attested landed specs."""
    from temporalio import workflow

    async def compute_drift(self: Any, request: Any) -> dict[str, bool]:
        drift: dict[str, bool] = {}
        for entry in self._roadmap.entries:
            if entry.state is not SpecState.READY:
                continue
            spec_text = await self._spec_text(request.specs_root, entry.spec_dir)
            drift[entry.spec_dir] = await workflow.execute_activity(
                ra.drift_for_spec,
                ra.DriftInput(
                    target_repo=request.target_repo,
                    spec_dir=entry.spec_dir,
                    spec_text=spec_text,
                ),
                **_FAST,
            )
        return drift

    return compute_drift


@pytest.mark.asyncio
async def test_a_landed_amended_spec_still_renders_amended(
    temporal_env: WorkflowEnvironment,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The widened drift read preserves today's amended render for landed specs."""
    specs_root = build_corpus(
        tmp_path,
        {
            "001-amended": dict(state=SpecState.LANDED),
            "002-held": dict(state=SpecState.READY),
        },
    )
    world = RoadmapWorld(drift_runner=lambda _request: True)
    activity_calls: list[tuple[str, str | None]] = []
    queried: RoadmapStatus | None = None
    async with run_roadmap(
        temporal_env,
        world,
        str(specs_root),
        hold_specs={"epic-002-held"},
        interceptors=[_ActivityRecordingInterceptor(activity_calls)],
    ) as handle:
        for _ in range(100):
            if any(
                name == "drift_for_spec" and account == "001-amended"
                for name, account in activity_calls
            ):
                break
            await asyncio.sleep(0.01)
        candidate = await handle.query("roadmap_status", result_type=RoadmapStatus)
        queried = candidate
        assert queried is not None
        amended = next(spec for spec in queried.specs if spec.spec_dir == "001-amended")
        assert amended.drifted is True
        assert amended.rendered_state == "amended"
        assert any(
            name == "drift_for_spec" and account == "001-amended"
            for name, account in activity_calls
        )
        await handle.cancel()


@pytest.mark.asyncio
async def test_amendment_control_detects_a_narrowed_drift_read(
    temporal_env: WorkflowEnvironment,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The amendment control fails if the landed-state branch is removed."""
    specs_root = build_corpus(
        tmp_path,
        {
            "001-amended": dict(state=SpecState.LANDED),
            "002-held": dict(state=SpecState.READY),
        },
    )
    world = RoadmapWorld(drift_runner=lambda _request: True)
    activity_calls: list[tuple[str, str | None]] = []
    monkeypatch.setattr(RoadmapWorkflow, "_compute_drift", _ready_only_drift())
    async with run_roadmap(
        temporal_env,
        world,
        str(specs_root),
        hold_specs={"epic-002-held"},
        interceptors=[_ActivityRecordingInterceptor(activity_calls)],
    ) as handle:
        for _ in range(100):
            status = await handle.query("roadmap_status", result_type=RoadmapStatus)
            if any(spec.spec_dir == "001-amended" for spec in status.specs):
                amended = next(
                    spec for spec in status.specs if spec.spec_dir == "001-amended"
                )
                break
            await asyncio.sleep(0.01)
        assert amended.drifted is False
        assert amended.rendered_state == "landed"
        assert not any(
            name == "drift_for_spec" and account == "001-amended"
            for name, account in activity_calls
        )
        await handle.cancel()


@pytest.mark.asyncio
async def test_dispatch_control_detects_a_suppressed_drift_read(
    temporal_env: WorkflowEnvironment,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The positive dispatch control fails if drift is supplied without a read."""
    specs_root = build_corpus(tmp_path, {"001-amended": dict(state=SpecState.READY)})
    world = RoadmapWorld(
        landed_runner=lambda _request: LandedStatus(
            landed=True, kind=LandedKind.OBSERVED
        ),
        drift_runner=lambda _request: True,
    )
    activity_calls: list[tuple[str, str | None]] = []
    child_starts: list[str] = []

    def suppress_drift(self: Any, _request: Any) -> Any:
        async def resolve(_spec_dir: str) -> bool:
            return True

        return resolve

    monkeypatch.setattr(RoadmapWorkflow, "_drift_resolver", suppress_drift)
    async with run_roadmap(
        temporal_env,
        world,
        str(specs_root),
        on_dispatch=child_starts.append,
        interceptors=[_ActivityRecordingInterceptor(activity_calls)],
    ) as handle:
        await handle.result()

    assert child_starts == ["001-amended"]
    assert not any(
        name == "drift_for_spec" and account == "001-amended"
        for name, account in activity_calls
    )
