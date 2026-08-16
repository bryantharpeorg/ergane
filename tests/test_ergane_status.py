"""046 US1: `ergane status` answers the morning question in one screen.

Five sections, one invocation, nothing written: the roadmap's disposition (US2's
discovery ladder, reused rather than re-derived), every running epic with its
per-story table, the ready queue with each blocked spec's blockers, the drafts
awaiting a flip, and each running epic's measured attempt wall-times.

Three things this file is deliberately built to catch, because a status command
is the shape of command a test can accidentally make unable to fail:

- **The join, not the mention.** Asserting "the epic id is in the output" passes
  whether or not anything was joined. Every section assertion here names a value
  that can only appear if the query, the corpus read, or the store read actually
  happened — a node's state *and* its attempt number, a blocker's spec dir, a
  wall-time in minutes and seconds computed from two timestamps.
- **The filter.** The fake client answers an unrecognised list filter with
  *everything*, so a `status` that forgot to ask only for running executions
  would surface the seeded COMPLETED epic and fail
  `test_only_running_epics_are_listed`.
- **The control.** The readiness-basis tests come in pairs: the same corpus, the
  same repo, differing only in whether the dependency's stories were landed.

------------------------------------------------------------------------------
The readiness basis, and the finding this story must not inherit
------------------------------------------------------------------------------

`ergane spec list` computes readiness with no `landed_for` resolver
(`factory/roadmap/cli.py`), so a dependency edge is satisfied only by the
dependency's own frontmatter attestation. `RoadmapWorkflow` injects
`landed_for=self._observed_resolver()` and therefore disagrees: it resolves
landings it has observed. Live on 2026-08-15 that read

    $ ergane spec list specs
    011-agent-sandbox    ready   blocked by: 043-runtime-root-integrity

while every story of the blocker had landed (finding
`interpreter/spec-list-reports-blockers-the-scheduler-does-not-see`). An
operator reading "blocked" plans around a blocker that is not there.

`ergane status` does not inherit that. It injects a `landed_for` resolver that
reads the target repo's own landing history through the existing
`landed_facts` reader, and it *names the basis it used* on the queue header, so
"blocked by" is never mistaken for a fact about the scheduler when it is only a
fact about frontmatter. Both halves are proved below:
`test_a_dependency_whose_stories_landed_is_not_a_blocker` with its control, and
`test_the_queue_header_names_the_readiness_basis`.

------------------------------------------------------------------------------
Verbatim tool output, run in this worktree
------------------------------------------------------------------------------

Red first. With this file committed and `factory/cli/status.py` still a
placeholder — no noun registered, so argparse refuses the verb with exit 2:

    $ uv run pytest -q tests/test_ergane_status.py
    FAILED tests/test_ergane_status.py::test_the_five_sections_render_in_order
    FAILED tests/test_ergane_status.py::test_only_running_epics_are_listed
    FAILED tests/test_ergane_status.py::test_the_epic_table_is_the_queried_document
    FAILED tests/test_ergane_status.py::test_a_schedule_driven_floor_names_the_schedule_its_state_and_its_run
    FAILED tests/test_ergane_status.py::test_an_empty_floor_says_what_it_looked_for
    FAILED tests/test_ergane_status.py::test_pace_reports_measured_attempt_wall_times
    FAILED tests/test_ergane_status.py::test_pace_carries_no_projected_completion_time
    FAILED tests/test_ergane_status.py::test_pace_counts_the_stories_that_remain
    FAILED tests/test_ergane_status.py::test_pace_says_so_when_no_attempt_has_been_recorded
    FAILED tests/test_ergane_status.py::test_a_closed_port_degrades_the_temporal_sections_and_keeps_the_rest
    FAILED tests/test_ergane_status.py::test_the_degraded_exit_code_differs_from_the_clean_one
    FAILED tests/test_ergane_status.py::test_json_carries_every_section_the_human_view_renders
    FAILED tests/test_ergane_status.py::test_json_and_the_human_view_agree_on_the_numbers
    FAILED tests/test_ergane_status.py::test_status_creates_nothing_on_a_checkout_with_no_runtime_root
    FAILED tests/test_ergane_status.py::test_status_does_not_create_an_absent_evidence_store
    FAILED tests/test_ergane_status.py::test_the_evidence_store_is_opened_read_only
    FAILED tests/test_ergane_status.py::test_a_dependency_whose_stories_landed_is_not_a_blocker
    FAILED tests/test_ergane_status.py::test_control_the_same_dependency_with_no_landings_still_blocks
    FAILED tests/test_ergane_status.py::test_the_queue_header_names_the_readiness_basis
    FAILED tests/test_ergane_status.py::test_attestation_only_is_named_as_such_when_no_repo_can_be_read
    20 failed, 1 passed in 1.07s

The one passing test is `test_the_resolver_would_have_created_the_runtime_root`
— the control for the read-only assertion. It is *supposed* to pass before and
after: it proves the mkdir side effect the status command must avoid is real.

Green, with `factory/cli/status.py` and its noun in place:

    $ uv run pytest -q tests/test_ergane_status.py
    21 passed in 1.00s

    $ uv run pytest -q
    2494 passed, 44 skipped, 4 warnings in 281.47s (0:04:41)

And live, in this worktree, against the real floor — the reason the readiness
basis is not left to inherit the finding. Three commands, one after another,
against the same corpus and the same git history:

    $ ergane spec list specs
    011-agent-sandbox                 ready     blocked by: 043-runtime-root-integrity
    033-ergane-install                ready     blocked by: 043-runtime-root-integrity, 011-agent-sandbox
    034-ergane-init                   ready     blocked by: 043-runtime-root-integrity, 033-ergane-install
    041-escalation-workflow           ready     blocked by: 033-ergane-install
    042-supervised-services           ready     blocked by: 033-ergane-install, 041-escalation-workflow
    043-runtime-root-integrity        ready

    $ ergane status          # the same six lines of the queue section
      011-agent-sandbox              ready  dispatchable
      033-ergane-install             ready  dispatchable
      034-ergane-init                ready  blocked by: 033-ergane-install
      041-escalation-workflow        ready  blocked by: 033-ergane-install
      042-supervised-services        ready  blocked by: 033-ergane-install, 041-escalation-workflow
      043-runtime-root-integrity     ready  dispatchable

    $ ergane spec landed specs/043-runtime-root-integrity
    default branch: ergane-buildout
    US1 landed at cc806be3caae (observed)
    US2 landed at 4f6ebda2194a (observed)
    US3 landed at 4eb62382ea7f (observed)
    US4 landed at ca122ad1d556 (observed)

`033-ergane-install` was reported blocked by two specs whose every story has
landed. It is not blocked, and `ergane status` says so. The floor's own control
is on the next line: `034-ergane-init` is *still* blocked by
`033-ergane-install`, because 033 has three stories and only two of them have
landed —

    $ ergane spec landed specs/033-ergane-install
    default branch: ergane-buildout
    US1 landed at 5b4351a63ec6 (observed)
    US2 landed at 2ee4e3bb1440 (observed)
    $ grep -c "^### User Story" specs/033-ergane-install/spec.md
    3

so the resolver discriminates rather than clearing everything.

The whole verb, live, in 0.57s, with a schedule owning the roadmap:

    $ ergane status
    roadmap
      schedule: ergane-roadmap (paused)
      run: roadmap-specs-2026-08-15T09:40:00Z
      next tick: 2026-08-15T20:00:00+00:00
      dispatch: running
      running: -
      parked: 0

    epics
      none running

    queue (readiness: attestation, plus landings on ergane-buildout (b193b01ca424) in <worktree>, read without fetching)
      011-agent-sandbox              ready  dispatchable
      ...

    drafts
      017-peer-channel          draft
      022-validate-calibration  draft
      024-ledger-token-honesty  draft
      032-replay-determinism    draft
      035-operator-completion   draft

    pace
      no epic is running

    real    0m0.574s
    $ ls -a | grep -E "^\.(ergane|factory)"     # after the run
    nothing created

Degraded, against a closed port, in the same worktree:

    $ TEMPORAL_ADDRESS=127.0.0.1:1 ergane status
    note: cannot reach Temporal at 127.0.0.1:1 (namespace 'factory'): Failed client connect: Server connection error: tonic::transport::Error(Transport, ConnectError(ConnectError("tcp connect error", 127.0.0.1:1, Os { code: 111, kind: ConnectionRefused, message: "Connection refused" }))); the roadmap and epics sections could not be read

    roadmap
      unavailable (see note)

    epics
      unavailable (see note)

    queue (readiness: attestation, plus landings on ergane-buildout (b193b01ca424) in <worktree>, read without fetching)
      011-agent-sandbox              ready  dispatchable
      ...
    [exit 3]
------------------------------------------------------------------------------
"""

from __future__ import annotations

import io
import json
import os
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, AsyncIterator, Callable, Iterable, NamedTuple

import pytest
import temporalio.client
from temporalio.client import ScheduleActionStartWorkflow
from temporalio.service import RPCError, RPCStatusCode

from factory.cli import main as main_module
from factory.cli import status as status_module
from factory.env import (
    ERGANE_ROOT_ENV,
    ERGANE_VERIFICATION_DB_PATH_ENV,
    FACTORY_ROOT_ENV,
    FACTORY_VERIFICATION_DB_PATH_ENV,
)
from factory.notify.service import TEMPORAL_ADDRESS_ENV
from factory.verify.models import (
    GateResult,
    GateStatus,
    OutputCheck,
    OverallVerdict,
    VerificationForm,
    VerificationResult,
)
from factory.verify.store import connect as verify_connect, upsert_result

DEAD_ADDRESS = "127.0.0.1:1"

#: Named by an operator's hand in production; seed data only here, never matched
#: on (the discovery matches the action's workflow id — 046 plan trap 3).
SCHEDULE_ID = "some-operator-named-schedule"

RUNNING_SPEC = "030-running-thing"
BLOCKED_SPEC = "031-blocked-thing"
DRAFT_SPEC = "032-draft-thing"
ATTESTED_SPEC = "029-attested-thing"
FREE_SPEC = "033-free-thing"
STALE_EPIC = "999-finished-thing"


# --- the corpus ---------------------------------------------------------------


def spec_text(title: str, *, state: str | None, deps: Iterable[str] = ()) -> str:
    """One minimal, well-formed spec: frontmatter plus one parseable story."""
    front = ""
    if state is not None:
        depends = ""
        if deps:
            depends = "depends_on_landed: [" + ", ".join(deps) + "]\n"
        front = f"---\nstate: {state}\n{depends}---\n\n"
    return (
        f"{front}# Feature Specification: {title}\n\n"
        "### User Story 1 - The only story (Priority: P1)\n\n"
        "As an operator, I want the thing.\n\n"
        "**Acceptance Scenarios**:\n\n"
        "1. **Given** a floor, **When** status runs, **Then** the thing is true.\n"
    )


def plant(specs_root: Path, spec_dir: str, text: str) -> Path:
    directory = specs_root / spec_dir
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "spec.md").write_text(text, encoding="utf-8")
    return directory


@pytest.fixture
def specs_root(tmp_path: Path) -> Path:
    """The seeded corpus: a running spec, a spec blocked on it, and a draft.

    Plus an attested-landed spec and a ready spec that depends on it, so the
    queue has a dispatchable line as well as a blocked one — a render that
    printed "blocked by" for everything would pass a test that only ever seeded
    blocked specs.
    """
    root = tmp_path / "specs"
    root.mkdir()
    plant(root, RUNNING_SPEC, spec_text("Running", state="ready"))
    plant(root, BLOCKED_SPEC, spec_text("Blocked", state="ready", deps=[RUNNING_SPEC]))
    plant(root, DRAFT_SPEC, spec_text("Draft", state=None))
    plant(root, ATTESTED_SPEC, spec_text("Attested", state="landed"))
    plant(root, FREE_SPEC, spec_text("Free", state="ready", deps=[ATTESTED_SPEC]))
    return root


# --- the floor ----------------------------------------------------------------


def epic_document(nodes: dict[str, tuple[str, int]], *, epic_state: str = "RUNNING") -> dict:
    """The shape `epic_status` decodes to when queried without a result type."""
    return {
        "epic_state": epic_state,
        "nodes": {
            node_id: {
                "state": state,
                "attempt": attempt,
                "branch": f"factory/{RUNNING_SPEC}/{node_id}",
            }
            for node_id, (state, attempt) in nodes.items()
        },
    }


RUNNING_EPIC_NODES = {
    "us1": ("MERGED", 1),
    "us2": ("MERGED", 2),
    "us3": ("RUNNING", 1),
}


def roadmap_document(*, paused: bool = False) -> Any:
    """What `roadmap_status` answers — decoded without a result type, a dict."""
    return {
        "specs": [],
        "running": [RUNNING_SPEC],
        "parked": [],
        "max_concurrent_epics": 1,
        "max_concurrent_nodes": 1,
        "paused": paused,
    }


@dataclass
class FakeSchedule:
    id: str
    action_workflow_id: str
    paused: bool = False
    next_action_times: list[datetime] = field(default_factory=list)


@dataclass
class FakeWorkflow:
    document: Any
    status_name: str = "RUNNING"
    start_time: datetime = datetime(2026, 8, 15, 9, 0, tzinfo=timezone.utc)


class _FakeScheduleHandle:
    def __init__(self, schedule: FakeSchedule) -> None:
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
            info=SimpleNamespace(next_action_times=list(self._schedule.next_action_times)),
        )


class _FakeWorkflowHandle:
    def __init__(self, client: "FakeTemporalClient", workflow_id: str) -> None:
        self._client = client
        self.id = workflow_id

    async def describe(self) -> Any:
        if self.id not in self._client.workflows:
            raise RPCError("workflow not found", RPCStatusCode.NOT_FOUND, b"")
        return SimpleNamespace(
            id=self.id,
            status=SimpleNamespace(name=self._client.workflows[self.id].status_name),
        )

    async def query(self, name: str, *args: Any, **kwargs: Any) -> Any:
        self._client.queried.append((self.id, name))
        if self.id not in self._client.workflows:
            raise RPCError("workflow not found", RPCStatusCode.NOT_FOUND, b"")
        return self._client.workflows[self.id].document

    async def signal(self, name: str, *args: Any, **kwargs: Any) -> None:  # pragma: no cover
        raise AssertionError("status must never signal anything (FR-002)")


class _AsyncIter:
    def __init__(self, items: Iterable[Any]) -> None:
        self._items = list(items)

    def __aiter__(self) -> AsyncIterator[Any]:
        async def gen() -> AsyncIterator[Any]:
            for item in self._items:
                yield item

        return gen()


class FakeTemporalClient:
    """Just enough Temporal to read a floor — and deliberately permissive.

    An unrecognised list filter yields *every* seeded workflow rather than
    none. A `status` that forgot to narrow to running executions therefore
    surfaces the seeded COMPLETED epic and fails its test, instead of passing
    because the fake happened to hand back only what the assertion wanted.
    """

    def __init__(
        self,
        *,
        workflows: dict[str, FakeWorkflow] | None = None,
        schedules: list[FakeSchedule] | None = None,
    ) -> None:
        self.workflows = dict(workflows or {})
        self.schedules = list(schedules or [])
        self.queried: list[tuple[str, str]] = []
        self.list_queries: list[str | None] = []
        self.schedule_lists = 0

    def get_workflow_handle(self, workflow_id: str, **kwargs: Any) -> _FakeWorkflowHandle:
        return _FakeWorkflowHandle(self, workflow_id)

    def get_schedule_handle(self, schedule_id: str) -> _FakeScheduleHandle:
        for schedule in self.schedules:
            if schedule.id == schedule_id:
                return _FakeScheduleHandle(schedule)
        raise AssertionError(f"no such schedule seeded: {schedule_id}")

    async def list_schedules(self, query: str | None = None, **kwargs: Any) -> _AsyncIter:
        self.schedule_lists += 1
        return _AsyncIter(SimpleNamespace(id=s.id) for s in self.schedules)

    def list_workflows(self, query: str | None = None, **kwargs: Any) -> _AsyncIter:
        self.list_queries.append(query)
        items = [
            SimpleNamespace(
                id=wf_id,
                start_time=wf.start_time,
                status=SimpleNamespace(name=wf.status_name),
            )
            for wf_id, wf in sorted(self.workflows.items())
        ]
        if query and "STARTS_WITH" in query:
            prefix = query.split('"')[1]
            return _AsyncIter(item for item in items if item.id.startswith(prefix))
        if query and "ExecutionStatus" in query:
            wanted = query.split('"')[1].upper()
            return _AsyncIter(item for item in items if item.status.name == wanted)
        # Unrecognised (or absent) filter: everything. See the class docstring.
        return _AsyncIter(items)


@pytest.fixture
def fake_temporal(monkeypatch: pytest.MonkeyPatch) -> Callable[..., FakeTemporalClient]:
    def setup(**kwargs: Any) -> FakeTemporalClient:
        client = FakeTemporalClient(**kwargs)

        async def _connect(target_host: str, **connect_kwargs: Any) -> FakeTemporalClient:
            return client

        monkeypatch.setattr(temporalio.client.Client, "connect", _connect)
        return client

    return setup


def bare_floor(setup: Callable[..., FakeTemporalClient]) -> FakeTemporalClient:
    """A bare `roadmap-specs`, one running epic, and one finished one."""
    return setup(
        workflows={
            "roadmap-specs": FakeWorkflow(roadmap_document()),
            f"epic-{RUNNING_SPEC}": FakeWorkflow(epic_document(RUNNING_EPIC_NODES)),
            f"epic-{STALE_EPIC}": FakeWorkflow(
                epic_document({"us1": ("MERGED", 1)}, epic_state="COMPLETED"),
                status_name="COMPLETED",
            ),
        }
    )


# --- the evidence store -------------------------------------------------------


def _result(
    node_id: str, attempt: int, verdict: OverallVerdict, started: str, finished: str
) -> VerificationResult:
    return VerificationResult(
        epic_id=RUNNING_SPEC,
        node_id=node_id,
        attempt=attempt,
        form=VerificationForm.PHASE,
        gate_results=[
            GateResult(
                name="test",
                command="uv run pytest -q",
                status=GateStatus.PASS,
                exit_code=0,
                duration_s=1.0,
                output_tail="",
            )
        ],
        output_check=OutputCheck(
            write_scope="worktree",
            has_diff=True,
            expected_artifacts=[],
            artifacts_present=None,
            passed=True,
        ),
        judge=None,
        verdict=verdict,
        judge_unavailable=False,
        criteria_drift=False,
        criteria_sha256="0" * 64,
        spec_ref=f"specs/{RUNNING_SPEC}/spec.md#US1",
        started_at=started,
        finished_at=finished,
    )


#: Three attempts with wall-times chosen to exercise all three renderings:
#: 750s → 12m30s, 45s → 45s, 7830s → 2h10m30s.
SEEDED_ATTEMPTS = (
    ("us1", 1, OverallVerdict.PASS, "2026-08-15T10:00:00Z", "2026-08-15T10:12:30Z"),
    ("us2", 1, OverallVerdict.FAIL, "2026-08-15T11:00:00Z", "2026-08-15T11:00:45Z"),
    ("us2", 2, OverallVerdict.PASS, "2026-08-15T12:00:00Z", "2026-08-15T14:10:30Z"),
)


@pytest.fixture
def evidence_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A real evidence store carrying the three seeded attempts."""
    path = tmp_path / "verification.db"
    monkeypatch.setenv(ERGANE_VERIFICATION_DB_PATH_ENV, str(path))
    monkeypatch.setenv(FACTORY_VERIFICATION_DB_PATH_ENV, str(path))
    conn = verify_connect(path)
    try:
        for node_id, attempt, verdict, started, finished in SEEDED_ATTEMPTS:
            upsert_result(conn, _result(node_id, attempt, verdict, started, finished))
    finally:
        conn.close()
    return path


# --- the CLI ------------------------------------------------------------------


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str

    @property
    def json(self) -> Any:
        return json.loads(self.stdout)


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


def headers(stdout: str) -> list[str]:
    """The section headers: the unindented, non-note lines of the report."""
    return [
        line.split(" (")[0]
        for line in stdout.splitlines()
        if line and not line.startswith(" ") and not line.startswith("note:")
    ]


def section(stdout: str, name: str) -> str:
    """One section's indented body, by header name."""
    lines = stdout.splitlines()
    for index, line in enumerate(lines):
        if line.split(" (")[0] == name and not line.startswith(" "):
            body: list[str] = []
            for follower in lines[index + 1 :]:
                if follower and not follower.startswith(" "):
                    break
                body.append(follower)
            return "\n".join(body)
    raise AssertionError(f"no section {name!r} in:\n{stdout}")


# ============================================================================
# T009 / US1-S1 — the five sections, against a seeded floor
# ============================================================================


def test_the_five_sections_render_in_order(
    fake_temporal: Callable[..., FakeTemporalClient],
    specs_root: Path,
    evidence_store: Path,
) -> None:
    """US1-S1 / SC-001: disposition, epics, queue with blockers, drafts, pace.

    Verbatim stdout of this run:

        roadmap
          run: roadmap-specs
          dispatch: running
          running: 030-running-thing
          parked: 0

        epics
          epic 030-running-thing  RUNNING  execution RUNNING
          us1  MERGED   attempt 1  factory/030-running-thing/us1
          us2  MERGED   attempt 2  factory/030-running-thing/us2
          us3  RUNNING  attempt 1  factory/030-running-thing/us3

        queue (readiness: attestation only — no git repository holds ...)
          031-blocked-thing  ready  blocked by: 030-running-thing [attestation only]
          033-free-thing     ready  dispatchable

        drafts
          032-draft-thing  draft

        pace
          030-running-thing
            us1  attempt 1  PASS  verified in 12m30s
            us2  attempt 1  FAIL  verified in 45s
            us2  attempt 2  PASS  verified in 2h10m30s
            1 of 3 stories remaining
          measured wall-times of finished attempts only
    """
    bare_floor(fake_temporal)

    result = invoke("status", str(specs_root))

    assert result.code == 0, result.stderr
    assert headers(result.stdout) == ["roadmap", "epics", "queue", "drafts", "pace"]

    # The disposition came from the roadmap query, not from a constant.
    assert "running: 030-running-thing" in section(result.stdout, "roadmap")

    # The queue names the blocker on the blocked spec's own line, and the
    # unblocked ready spec is not reported blocked.
    queue = section(result.stdout, "queue")
    assert f"{BLOCKED_SPEC}" in queue and f"blocked by: {RUNNING_SPEC}" in queue
    assert re.search(rf"{FREE_SPEC}\s+ready\s+dispatchable", queue)
    # A draft is not in the queue, and a landed spec is in neither.
    assert DRAFT_SPEC not in queue
    assert ATTESTED_SPEC not in queue

    drafts = section(result.stdout, "drafts")
    assert DRAFT_SPEC in drafts
    assert BLOCKED_SPEC not in drafts


def test_only_running_epics_are_listed(
    fake_temporal: Callable[..., FakeTemporalClient],
    specs_root: Path,
    evidence_store: Path,
) -> None:
    """The listing is narrowed to running executions, not filtered after the fact.

    The fake answers an unrecognised filter with every seeded workflow, so a
    `status` that listed everything would surface `epic-999-finished-thing`
    here. It also seeds a `roadmap-specs` workflow, which is not an epic and
    must not appear in the epics section.
    """
    client = bare_floor(fake_temporal)

    result = invoke("status", str(specs_root))

    epics = section(result.stdout, "epics")
    assert f"epic {RUNNING_SPEC}" in epics
    assert STALE_EPIC not in epics
    assert "roadmap-specs" not in epics
    assert client.list_queries, "no workflow listing was ever performed"


def test_the_epic_table_is_the_queried_document(
    fake_temporal: Callable[..., FakeTemporalClient],
    specs_root: Path,
    evidence_store: Path,
) -> None:
    """US1-S1: per-story state *and* attempt, from the epic's own query.

    Every node's state and attempt number is asserted, so a table rendered
    from anything other than the queried document fails: the attempt numbers
    (1, 2, 1) exist nowhere else in the floor.
    """
    client = bare_floor(fake_temporal)

    result = invoke("status", str(specs_root))
    epics = section(result.stdout, "epics")

    assert re.search(r"us1\s+MERGED\s+attempt 1", epics)
    assert re.search(r"us2\s+MERGED\s+attempt 2", epics)
    assert re.search(r"us3\s+RUNNING\s+attempt 1", epics)
    assert (f"epic-{RUNNING_SPEC}", "epic_status") in client.queried


# ============================================================================
# T010 / US1-S2 — the disposition of a schedule-driven roadmap
# ============================================================================


def test_a_schedule_driven_floor_names_the_schedule_its_state_and_its_run(
    fake_temporal: Callable[..., FakeTemporalClient],
    specs_root: Path,
) -> None:
    """US1-S2: the disposition rides US2's ladder — schedule, state, newest run.

    No bare `roadmap-specs` exists on this floor, which is exactly the
    2026-08-15 shape: without the ladder the section would read "no roadmap".
    Verbatim roadmap section:

        roadmap
          schedule: some-operator-named-schedule (paused)
          run: roadmap-specs-2026-08-15T15:00:00Z
          next tick: 2026-08-15T16:00:00+00:00
          dispatch: running
          running: 030-running-thing
          parked: 0
    """
    newest = "roadmap-specs-2026-08-15T15:00:00Z"
    older = "roadmap-specs-2026-08-15T14:00:00Z"
    client = fake_temporal(
        workflows={
            older: FakeWorkflow(
                roadmap_document(), start_time=datetime(2026, 8, 15, 14, tzinfo=timezone.utc)
            ),
            newest: FakeWorkflow(
                roadmap_document(), start_time=datetime(2026, 8, 15, 15, tzinfo=timezone.utc)
            ),
        },
        schedules=[
            FakeSchedule(
                id=SCHEDULE_ID,
                action_workflow_id="roadmap-specs",
                paused=True,
                next_action_times=[datetime(2026, 8, 15, 16, tzinfo=timezone.utc)],
            )
        ],
    )

    result = invoke("status", str(specs_root))
    roadmap = section(result.stdout, "roadmap")

    assert result.code == 0, result.stderr
    assert f"schedule: {SCHEDULE_ID} (paused)" in roadmap
    assert f"run: {newest}" in roadmap
    assert older not in roadmap
    assert "next tick: 2026-08-15T16:00:00+00:00" in roadmap
    assert "no roadmap" not in result.stdout
    # It queried the newest run, and it read the schedule rather than guessing.
    assert (newest, "roadmap_status") in client.queried
    assert client.schedule_lists == 1


def test_an_empty_floor_says_what_it_looked_for(
    fake_temporal: Callable[..., FakeTemporalClient],
    specs_root: Path,
) -> None:
    """Nothing running is a line of the report, never a refusal: the spec
    sections are the half the operator most needs during an outage."""
    fake_temporal()

    result = invoke("status", str(specs_root))

    assert result.code == 0, result.stderr
    assert "roadmap-specs" in section(result.stdout, "roadmap")
    assert headers(result.stdout) == ["roadmap", "epics", "queue", "drafts", "pace"]


# ============================================================================
# T011 / US1-S3 — pace is measurement
# ============================================================================


def test_pace_reports_measured_attempt_wall_times(
    fake_temporal: Callable[..., FakeTemporalClient],
    specs_root: Path,
    evidence_store: Path,
) -> None:
    """US1-S3 / FR-003: `started_at`/`finished_at`, subtracted, per attempt.

    The three figures appear nowhere in the seed data — they exist only if the
    two timestamps of each row were read and subtracted.
    """
    bare_floor(fake_temporal)

    result = invoke("status", str(specs_root))
    pace = section(result.stdout, "pace")

    assert re.search(r"us1\s+attempt 1\s+PASS\s+verified in 12m30s", pace)
    assert re.search(r"us2\s+attempt 1\s+FAIL\s+verified in 45s", pace)
    assert re.search(r"us2\s+attempt 2\s+PASS\s+verified in 2h10m30s", pace)


def test_pace_carries_no_projected_completion_time(
    fake_temporal: Callable[..., FakeTemporalClient],
    specs_root: Path,
    evidence_store: Path,
) -> None:
    """FR-003 / plan trap 5: measurement, never a promise.

    The moment the output carries an arrival time the operator starts trusting
    a number the store cannot support: it brackets one verification, not one
    story, and neither dispatch nor merge-queue time is in it.
    """
    bare_floor(fake_temporal)

    result = invoke("status", str(specs_root))

    for forbidden in (r"\beta\b", r"estimat", r"project", r"forecast", r"\bwill\b"):
        assert not re.search(forbidden, result.stdout, re.IGNORECASE), forbidden
    assert "measured wall-times of finished attempts only" in section(result.stdout, "pace")


def test_pace_counts_the_stories_that_remain(
    fake_temporal: Callable[..., FakeTemporalClient],
    specs_root: Path,
    evidence_store: Path,
) -> None:
    """US1-S3: the remaining-story count beside the wall-times.

    Two of the epic's three nodes are terminal (`MERGED`); the third is
    `RUNNING`. A count that ignored node state would say 3 or 0.
    """
    bare_floor(fake_temporal)

    result = invoke("status", str(specs_root))

    assert "1 of 3 stories remaining" in section(result.stdout, "pace")


def test_pace_says_so_when_no_attempt_has_been_recorded(
    fake_temporal: Callable[..., FakeTemporalClient],
    specs_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An epic with no rows yet is reported as such, not omitted or crashed."""
    monkeypatch.setenv(ERGANE_VERIFICATION_DB_PATH_ENV, str(tmp_path / "absent.db"))
    monkeypatch.setenv(FACTORY_VERIFICATION_DB_PATH_ENV, str(tmp_path / "absent.db"))
    bare_floor(fake_temporal)

    result = invoke("status", str(specs_root))

    assert result.code == 0, result.stderr
    assert "no attempt recorded" in section(result.stdout, "pace")


# ============================================================================
# T012 / US1-S4 — degraded is a mode, not an error
# ============================================================================


def test_a_closed_port_degrades_the_temporal_sections_and_keeps_the_rest(
    specs_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US1-S4 / FR-004: the file-derived half still renders, the note names the address.

    Against a genuinely closed port (`127.0.0.1:1`, the 043-US3 precedent), not
    a patched client: the operator reaching for `ergane status` during an outage
    is the operator who most needs the queue and the drafts.
    """
    monkeypatch.setenv(TEMPORAL_ADDRESS_ENV, DEAD_ADDRESS)

    result = invoke("status", str(specs_root))

    assert DEAD_ADDRESS in result.stdout
    assert result.stdout.splitlines()[0].startswith("note: ")
    # One note, not one per section.
    assert result.stdout.count("note: ") == 1
    # The Temporal half degrades...
    assert "unavailable" in section(result.stdout, "roadmap")
    assert "unavailable" in section(result.stdout, "epics")
    # ...and the file-derived half is untouched.
    queue = section(result.stdout, "queue")
    assert f"blocked by: {RUNNING_SPEC}" in queue
    assert DRAFT_SPEC in section(result.stdout, "drafts")


def test_the_degraded_exit_code_differs_from_the_clean_one(
    fake_temporal: Callable[..., FakeTemporalClient],
    specs_root: Path,
    evidence_store: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US1-S4: the exit code distinguishes degraded from clean, in one test.

    Both invocations run against the same corpus; only Temporal's reachability
    differs, so the codes cannot both be an accident of the environment.
    """
    bare_floor(fake_temporal)
    clean = invoke("status", str(specs_root))

    monkeypatch.setattr(
        temporalio.client.Client,
        "connect",
        _refuse_to_connect,
    )
    monkeypatch.setenv(TEMPORAL_ADDRESS_ENV, DEAD_ADDRESS)
    degraded = invoke("status", str(specs_root))

    assert clean.code == 0, clean.stderr
    assert degraded.code == 3
    assert clean.code != degraded.code


async def _refuse_to_connect(target_host: str, **kwargs: Any) -> Any:
    raise OSError(f"connection refused: {target_host}")


# ============================================================================
# T013 / US1-S5 — one machine-readable document
# ============================================================================


def test_json_carries_every_section_the_human_view_renders(
    fake_temporal: Callable[..., FakeTemporalClient],
    specs_root: Path,
    evidence_store: Path,
) -> None:
    """US1-S5 / FR-005: one document, every section, with the values in it."""
    bare_floor(fake_temporal)

    result = invoke("status", str(specs_root), "--json")

    assert result.code == 0, result.stderr
    document = result.json
    assert set(document) >= {
        "roadmap",
        "epics",
        "queue",
        "drafts",
        "pace",
        "readiness_basis",
        "degraded",
        "notes",
    }
    assert document["roadmap"]["workflow_id"] == "roadmap-specs"
    assert [epic["epic_id"] for epic in document["epics"]] == [RUNNING_SPEC]
    assert document["epics"][0]["nodes"]["us2"]["attempt"] == 2
    blocked = [entry for entry in document["queue"] if entry["spec_dir"] == BLOCKED_SPEC]
    assert blocked and blocked[0]["blockers"] == [RUNNING_SPEC]
    assert [entry["spec_dir"] for entry in document["drafts"]] == [DRAFT_SPEC]
    assert document["degraded"] is False


def test_json_and_the_human_view_agree_on_the_numbers(
    fake_temporal: Callable[..., FakeTemporalClient],
    specs_root: Path,
    evidence_store: Path,
) -> None:
    """FR-005: the same document the human view renders from, not a second read."""
    bare_floor(fake_temporal)

    human = invoke("status", str(specs_root))
    machine = invoke("status", str(specs_root), "--json").json

    pace = machine["pace"][0]
    assert pace["epic_id"] == RUNNING_SPEC
    assert pace["stories_remaining"] == 1
    assert pace["stories_total"] == 3
    assert [attempt["seconds"] for attempt in pace["attempts"]] == [750, 45, 7830]
    assert "1 of 3 stories remaining" in section(human.stdout, "pace")
    assert "verified in 12m30s" in section(human.stdout, "pace")


# ============================================================================
# T014 / US1-S6 — status is read-only
# ============================================================================


def _tree(root: Path) -> set[str]:
    return {str(path.relative_to(root)) for path in root.rglob("*")}


def test_status_creates_nothing_on_a_checkout_with_no_runtime_root(
    fake_temporal: Callable[..., FakeTemporalClient],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US1-S6 / SC-003 / FR-002: nothing on disk, asserted on the filesystem.

    The resolver at `factory/workgraph/worktree.py` creates the runtime root as
    a side effect when neither root exists, so every path that reaches it must
    be kept off. Both root variables are cleared (the session fixture sets them)
    and the working directory is a scratch tree, 043's discipline.
    """
    checkout = tmp_path / "checkout"
    (checkout / "specs").mkdir(parents=True)
    plant(checkout / "specs", RUNNING_SPEC, spec_text("Running", state="ready"))
    plant(checkout / "specs", DRAFT_SPEC, spec_text("Draft", state=None))
    for name in (
        ERGANE_ROOT_ENV,
        FACTORY_ROOT_ENV,
        ERGANE_VERIFICATION_DB_PATH_ENV,
        FACTORY_VERIFICATION_DB_PATH_ENV,
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(checkout)
    bare_floor(fake_temporal)

    before = _tree(checkout)
    result = invoke("status")
    after = _tree(checkout)

    # It ran, and it rendered — a command that fell over early would also have
    # created nothing.
    assert result.code == 0, result.stderr
    assert headers(result.stdout) == ["roadmap", "epics", "queue", "drafts", "pace"]
    assert after == before, f"status created {sorted(after - before)}"
    assert not (checkout / ".ergane").exists()
    assert not (checkout / ".factory").exists()


def test_the_resolver_would_have_created_the_runtime_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control for the test above: the mkdir it avoids is real and live.

    Without this, "nothing was created" is a claim about a side effect nobody
    proved exists in the first place.
    """
    from factory.workgraph.worktree import resolve_factory_root

    checkout = tmp_path / "control"
    checkout.mkdir()
    for name in (ERGANE_ROOT_ENV, FACTORY_ROOT_ENV):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(checkout)

    assert not (checkout / ".ergane").exists()
    resolve_factory_root()
    assert (checkout / ".ergane").is_dir()


def test_status_does_not_create_an_absent_evidence_store(
    fake_temporal: Callable[..., FakeTemporalClient],
    specs_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-002: a store that does not exist is not opened into existence.

    `factory.verify.store.connect` creates the parent directory and the file;
    the read path must check first.
    """
    absent = tmp_path / "nowhere" / "verification.db"
    monkeypatch.setenv(ERGANE_VERIFICATION_DB_PATH_ENV, str(absent))
    monkeypatch.setenv(FACTORY_VERIFICATION_DB_PATH_ENV, str(absent))
    bare_floor(fake_temporal)

    result = invoke("status", str(specs_root))

    assert result.code == 0, result.stderr
    assert not absent.exists()
    assert not absent.parent.exists()


def test_the_evidence_store_is_opened_read_only(evidence_store: Path) -> None:
    """FR-002: "no store opened for write" is a property of the connection.

    Proven by trying to write through the very connection the status reader
    uses. Verbatim, from a scratch reproduction of this assertion:

        write refused: OperationalError attempt to write a readonly database
    """
    conn = status_module.open_store_readonly(evidence_store)
    assert conn is not None
    try:
        with pytest.raises(sqlite3.OperationalError) as raised:
            conn.execute("CREATE TABLE intruder (a int)")
    finally:
        conn.close()
    assert "readonly" in str(raised.value)


# ============================================================================
# The readiness basis — the finding this story must not inherit
# ============================================================================


GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "Ergane Fixture",
    "GIT_AUTHOR_EMAIL": "fixture@ergane.invalid",
    "GIT_COMMITTER_NAME": "Ergane Fixture",
    "GIT_COMMITTER_EMAIL": "fixture@ergane.invalid",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
}


def _git(repo: Path, *args: str) -> str:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.devnull,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        **GIT_IDENTITY,
    }
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    ).stdout


def _repo_with_corpus(tmp_path: Path, *, land: bool) -> Path:
    """A repo whose `specs/` holds a blocked spec and its one dependency.

    `land` is the single difference between the pair of tests below: whether
    the dependency's only story has a landing commit on the default branch.
    """
    repo = tmp_path / ("landed-repo" if land else "unlanded-repo")
    (repo / "specs").mkdir(parents=True)
    _git(repo, "init", "-b", "main", "--quiet")
    plant(repo / "specs", RUNNING_SPEC, spec_text("Dependency", state="ready"))
    plant(
        repo / "specs",
        BLOCKED_SPEC,
        spec_text("Dependent", state="ready", deps=[RUNNING_SPEC]),
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "the corpus")
    if land:
        # The merge queue's own attribution grammar (`factory/mergequeue/messages.py`).
        _git(repo, "commit", "--quiet", "--allow-empty", "-m", f"{RUNNING_SPEC}/us1: US1 (#12)")
    return repo


def test_a_dependency_whose_stories_landed_is_not_a_blocker(
    fake_temporal: Callable[..., FakeTemporalClient],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The finding, not inherited: the scheduler resolves observed landings, so does this.

    `031-blocked-thing` waits on `030-running-thing`, whose frontmatter says
    `ready`, not `landed` — attestation alone therefore calls it blocked, which
    is exactly what `ergane spec list` printed on 2026-08-15 for a dependency
    whose every story had landed. Here the landing commit exists, and the queue
    reports the spec dispatchable.
    """
    repo = _repo_with_corpus(tmp_path, land=True)
    monkeypatch.chdir(repo)
    fake_temporal()

    result = invoke("status", "specs")
    queue = section(result.stdout, "queue")

    assert result.code == 0, result.stderr
    assert re.search(rf"{BLOCKED_SPEC}\s+ready\s+dispatchable", queue)
    assert "blocked by" not in queue


def test_control_the_same_dependency_with_no_landings_still_blocks(
    fake_temporal: Callable[..., FakeTemporalClient],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control: identical corpus, identical repo, no landing commit.

    Without this the test above proves only that the queue can print
    "dispatchable" — not that the landing is what made it so.
    """
    repo = _repo_with_corpus(tmp_path, land=False)
    monkeypatch.chdir(repo)
    fake_temporal()

    result = invoke("status", "specs")
    queue = section(result.stdout, "queue")

    assert result.code == 0, result.stderr
    assert f"blocked by: {RUNNING_SPEC}" in queue


def test_the_queue_header_names_the_readiness_basis(
    fake_temporal: Callable[..., FakeTemporalClient],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """"blocked by" must never read as a fact about the scheduler unqualified.

    The header says which basis produced the answer — here, the repo, the
    branch, and that it was read without fetching.
    """
    repo = _repo_with_corpus(tmp_path, land=True)
    monkeypatch.chdir(repo)
    fake_temporal()

    result = invoke("status", "specs")
    header = next(
        line for line in result.stdout.splitlines() if line.startswith("queue")
    )

    assert "readiness:" in header
    assert "main" in header
    assert "without fetching" in header


def test_attestation_only_is_named_as_such_when_no_repo_can_be_read(
    fake_temporal: Callable[..., FakeTemporalClient],
    specs_root: Path,
) -> None:
    """No repo above the corpus: the basis degrades, and says so on every line.

    The degraded basis is the one that reproduces the finding's reading, so it
    is the one that must be labelled — both in the header and beside each
    blocker, because a blocked line read on its own is what misleads.
    """
    fake_temporal()

    result = invoke("status", str(specs_root))
    header = next(
        line for line in result.stdout.splitlines() if line.startswith("queue")
    )
    queue = section(result.stdout, "queue")

    assert "attestation only" in header
    assert f"blocked by: {RUNNING_SPEC} [attestation only]" in queue
