"""065 US2: a wedged scheduler is visible without an operator guessing.

`ergane roadmap status` and `ergane doctor` must both be able to say when a
roadmap workflow task is in failed state -- the silent-stall shape that US1
removes for null child results but that any unhandled workflow exception can
still produce.

The floor is faked at `Client.connect`, the same precedent
`tests/test_roadmap_schedule_discovery.py` and `tests/test_doctor_probes.py`
use, because the time-skipping Temporal server cannot be driven reliably into
the production "Workflow Task in failed state" query error. The *action*
objects are the real SDK `ScheduleActionStartWorkflow`, and the discovery path
under test is the real `factory.roadmap.discovery.resolve_roadmap`, so the fake
only supplies data and errors; it does not fake the ladder.
"""

from __future__ import annotations

import io
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, AsyncIterator, Callable, Iterable, NamedTuple

import pytest
import temporalio.client
from temporalio.client import ScheduleActionStartWorkflow
from temporalio.service import RPCError, RPCStatusCode

import factory.doctor.probes as probes
from factory.cli import main as main_module
from factory.doctor.models import Severity
from factory.doctor.probes import FindingReport, ServiceNotAnswering
from factory.roadmap.discovery import resolve_roadmap
from factory.roadmap.workflow import RoadmapSpecStatus, RoadmapStatus
from factory.roadmap.models import SpecState

SPECS_ROOT = "/srv/factory/ergane/specs"
BARE_ID = "roadmap-specs"
RUN_PREFIX = "roadmap-specs-"
OLDER_RUN = "roadmap-specs-2026-08-15T14:00:00Z"
NEWEST_RUN = "roadmap-specs-2026-08-15T15:00:00Z"
SCHEDULE_ID = "ergane-roadmap"

WEDGED_ERROR = "Unable to query workflow due to Workflow Task in failed state."


# --- the floor (reuses the FakeTemporalClient pattern) -----------------------


def _status_document() -> RoadmapStatus:
    return RoadmapStatus(
        specs=[
            RoadmapSpecStatus(
                spec_dir="011-agent-sandbox",
                state=SpecState.READY,
                dispatchable=True,
                blockers=[],
                landed=False,
                unlanded=[],
            )
        ],
        running=["011-agent-sandbox"],
        parked=[],
        max_concurrent_epics=1,
        max_concurrent_nodes=1,
        paused=False,
    )


@dataclass
class FakeSchedule:
    id: str
    action_workflow_id: str
    paused: bool = False
    next_action_times: list[datetime] = field(default_factory=list)


class _FakeScheduleHandle:
    def __init__(self, client: "FakeTemporalClient", schedule: FakeSchedule) -> None:
        self._client = client
        self._schedule = schedule

    async def describe(self) -> Any:
        return SimpleNamespace(
            id=self._schedule.id,
            schedule=SimpleNamespace(
                action=ScheduleActionStartWorkflow(
                    "RoadmapWorkflow",
                    id=self._schedule.action_workflow_id,
                    task_queue="ergane",
                ),
                state=SimpleNamespace(paused=self._schedule.paused, note=None),
            ),
            info=SimpleNamespace(
                next_action_times=list(self._schedule.next_action_times)
            ),
        )


class _FakeWorkflowHandle:
    def __init__(self, client: "FakeTemporalClient", workflow_id: str) -> None:
        self._client = client
        self.id = workflow_id

    async def describe(self) -> Any:
        self._client.described.append(self.id)
        if self.id not in self._client.workflows:
            raise RPCError("workflow not found", RPCStatusCode.NOT_FOUND, b"")
        return SimpleNamespace(id=self.id, workflow_type="RoadmapWorkflow")

    async def query(self, name: str, *args: Any, **kwargs: Any) -> Any:
        self._client.queried.append((self.id, name))
        wf = self._client.workflows[self.id]
        if wf.query_error is not None:
            raise wf.query_error
        return wf.status


@dataclass
class FakeWorkflow:
    status: RoadmapStatus
    start_time: datetime
    query_error: RPCError | None = None


class _AsyncIter:
    def __init__(self, items: Iterable[Any]) -> None:
        self._items = list(items)

    def __aiter__(self) -> AsyncIterator[Any]:
        async def gen() -> AsyncIterator[Any]:
            for item in self._items:
                yield item

        return gen()


class FakeTemporalClient:
    def __init__(
        self,
        *,
        workflows: dict[str, FakeWorkflow] | None = None,
        schedules: list[FakeSchedule] | None = None,
        connect_error: Exception | None = None,
    ) -> None:
        self.workflows = dict(workflows or {})
        self.schedules = list(schedules or [])
        self.connect_error = connect_error
        self.described: list[str] = []
        self.queried: list[tuple[str, str]] = []
        self.schedule_lists = 0
        self.workflow_list_queries: list[str | None] = []

    def get_workflow_handle(self, workflow_id: str, **kwargs: Any) -> _FakeWorkflowHandle:
        return _FakeWorkflowHandle(self, workflow_id)

    def get_schedule_handle(self, schedule_id: str) -> _FakeScheduleHandle:
        for schedule in self.schedules:
            if schedule.id == schedule_id:
                return _FakeScheduleHandle(self, schedule)
        raise AssertionError(f"no such schedule seeded: {schedule_id}")

    async def list_schedules(self, query: str | None = None, **kwargs: Any) -> _AsyncIter:
        self.schedule_lists += 1
        return _AsyncIter(SimpleNamespace(id=s.id) for s in self.schedules)

    def list_workflows(self, query: str | None = None, **kwargs: Any) -> _AsyncIter:
        self.workflow_list_queries.append(query)
        prefix = _prefix_from(query)
        return _AsyncIter(
            SimpleNamespace(id=wf_id, start_time=wf.start_time)
            for wf_id, wf in sorted(self.workflows.items())
            if prefix is None or wf_id.startswith(prefix)
        )


def _prefix_from(query: str | None) -> str | None:
    if query is None:
        return None
    assert "STARTS_WITH" in query, f"unexpected list filter: {query}"
    return query.split('"')[1]


@pytest.fixture
def fake_temporal(monkeypatch: pytest.MonkeyPatch) -> Callable[..., FakeTemporalClient]:
    def setup(**kwargs: Any) -> FakeTemporalClient:
        client = FakeTemporalClient(**kwargs)

        async def _connect(target_host: str, **connect_kwargs: Any) -> FakeTemporalClient:
            if client.connect_error is not None:
                raise client.connect_error
            return client

        monkeypatch.setattr(temporalio.client.Client, "connect", _connect)
        return client

    return setup


def _at(hour: int) -> datetime:
    return datetime(2026, 8, 15, hour, 0, 0, tzinfo=timezone.utc)


def scheduled_floor(
    setup: Callable[..., FakeTemporalClient],
    workflows: dict[str, FakeWorkflow] | None = None,
    **kwargs: Any,
) -> FakeTemporalClient:
    """A schedule-driven floor with two timestamped runs and no bare workflow."""
    default_workflows: dict[str, FakeWorkflow] = {
        OLDER_RUN: FakeWorkflow(_status_document(), _at(14)),
        NEWEST_RUN: FakeWorkflow(_status_document(), _at(15)),
    }
    return setup(
        workflows=workflows if workflows is not None else default_workflows,
        schedules=[
            FakeSchedule(
                id=SCHEDULE_ID,
                action_workflow_id=BARE_ID,
                next_action_times=[_at(16)],
            )
        ],
        **kwargs,
    )


# --- CLI helper --------------------------------------------------------------


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str


def invoke(*argv: str) -> Run:
    old_stdout, old_stderr = sys.stdout, sys.stderr
    buf_out, buf_err = io.StringIO(), io.StringIO()
    try:
        sys.stdout, sys.stderr = buf_out, buf_err
        try:
            code = main_module.main(list(argv))
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
    return Run(code, buf_out.getvalue(), buf_err.getvalue())


# ============================================================================
# T011 / US2-S1 — status reports a wedged roadmap and names the run and remedy
# ============================================================================


def test_status_reports_wedged_roadmap_and_names_run_and_remedy(
    fake_temporal: Callable[..., FakeTemporalClient],
) -> None:
    """US2-S1 / FR-007: a failing workflow task is rendered as a wedged roadmap.

    The message must name the failing run and tell the operator the run must be
    terminated, instead of forwarding Temporal's opaque sentence.
    """
    client = scheduled_floor(
        fake_temporal,
        workflows={
            NEWEST_RUN: FakeWorkflow(
                _status_document(),
                _at(15),
                query_error=RPCError(WEDGED_ERROR, RPCStatusCode.INVALID_ARGUMENT, b""),
            ),
        },
    )

    result = invoke("roadmap", "status", SPECS_ROOT)

    assert result.code != 0, result.stdout
    assert "wedged" in result.stderr.lower(), result.stderr
    assert NEWEST_RUN in result.stderr, result.stderr
    assert "terminate" in result.stderr.lower(), result.stderr


# ============================================================================
# T012 / US2-S2 — the doctor probe reports a finding naming the wedged run
# ============================================================================


class TestRoadmapWedgeProbe:
    """US2-S2/S3/S4/S5 and Edge Cases — the wedge probe's judgment."""

    def test_wedged_roadmap_files_finding_naming_run(
        self, fake_temporal: Callable[..., FakeTemporalClient]
    ) -> None:
        """US2-S2 / FR-008: a failing workflow task becomes a doctor finding."""
        scheduled_floor(
            fake_temporal,
            workflows={
                NEWEST_RUN: FakeWorkflow(
                    _status_document(),
                    _at(15),
                    query_error=RPCError(
                        WEDGED_ERROR, RPCStatusCode.INVALID_ARGUMENT, b""
                    ),
                ),
            },
        )

        snapshot = probes.RoadmapWedgeProbe().gather()
        findings = probes.RoadmapWedgeProbe().evaluate(snapshot)

        assert len(findings) == 1
        f = findings[0]
        assert f.key == f"ops/roadmap-wedged/{NEWEST_RUN}"
        assert f.category == "ops"
        assert f.severity == Severity.CRITICAL
        assert NEWEST_RUN in f.summary
        assert "terminate" in f.summary.lower()
        assert any(NEWEST_RUN in ref for ref in f.refs)

    def test_healthy_roadmap_is_silent(
        self, fake_temporal: Callable[..., FakeTemporalClient]
    ) -> None:
        """US2-S3: a normally-running roadmap raises no finding."""
        scheduled_floor(fake_temporal)

        snapshot = probes.RoadmapWedgeProbe().gather()
        findings = probes.RoadmapWedgeProbe().evaluate(snapshot)

        assert findings == []

    def test_idle_roadmap_at_epic_cap_is_silent(
        self, fake_temporal: Callable[..., FakeTemporalClient]
    ) -> None:
        """US2-S4: idle (nothing dispatched yet because of the epic cap) is not wedged."""
        idle_status = RoadmapStatus(
            specs=[
                RoadmapSpecStatus(
                    spec_dir="011-agent-sandbox",
                    state=SpecState.READY,
                    dispatchable=True,
                    blockers=[],
                    landed=False,
                    unlanded=[],
                )
            ],
            running=[],
            parked=[],
            max_concurrent_epics=1,
            max_concurrent_nodes=1,
            paused=False,
        )
        scheduled_floor(
            fake_temporal,
            workflows={NEWEST_RUN: FakeWorkflow(idle_status, _at(15))},
        )

        snapshot = probes.RoadmapWedgeProbe().gather()
        findings = probes.RoadmapWedgeProbe().evaluate(snapshot)

        assert findings == []

    def test_unreachable_temporal_is_service_not_answering(
        self, fake_temporal: Callable[..., FakeTemporalClient]
    ) -> None:
        """US2-S5 / FR-009: cannot reach Temporal => skipped probe, not a wedge."""
        fake_temporal(connect_error=RuntimeError("connection refused"))

        with pytest.raises(ServiceNotAnswering) as caught:
            probes.RoadmapWedgeProbe().gather()
        assert caught.value.service == "temporal"

    def test_completed_run_is_silent(
        self, fake_temporal: Callable[..., FakeTemporalClient]
    ) -> None:
        """Edge Case: a completed schedule run draining away is not a wedge."""
        scheduled_floor(
            fake_temporal,
            workflows={
                NEWEST_RUN: FakeWorkflow(
                    _status_document(), _at(15), query_error=RPCError(
                        "workflow completed", RPCStatusCode.NOT_FOUND, b""
                    )
                ),
            },
        )

        snapshot = probes.RoadmapWedgeProbe().gather()
        findings = probes.RoadmapWedgeProbe().evaluate(snapshot)

        assert findings == []
