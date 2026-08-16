"""`ergane escalations list`: what is waiting on me, asked of Temporal.

041-US2, US2-S4 / FR-008. Making escalation a workflow type buys operability for
free — "what is waiting on me" becomes a query over running workflows instead of
a scrape of `escalations WHERE resolution IS NULL`. A list command that read the
store would satisfy the *sentence* and betray the requirement, so this file is
built to fail such a command.

Two seeded facts make a SQL scrape impossible to pass with:

- **A running escalation whose store row was already settled out of band.** A
  pending-row scrape omits it; the workflow says it is still waiting, and it is.
  This is not a contrived shape: it is the measured asymmetry in
  `interpreter/resolved-escalation-never-clears-in-the-store`, where the channel
  that answered decided whether the row moved.
- **An abandoned pending row with no workflow behind it.** A scrape lists it;
  there is nothing to answer. Fourteen of these were live on 2026-08-14, the
  oldest eight days past its deadline (plan trap 9).

Every question and deadline printed comes back from a real `escalation_status`
query against a real running workflow, and the question text exists nowhere in
the store — the row's `history_summary` says something else on purpose.

The one thing not driven end to end is Temporal's visibility API itself: the
time-skipping test server answers `ListWorkflowExecutions` with `unimplemented`
(probed 2026-08-16, transcript at the bottom of this file), which is the same
constraint that made `roadmap_activities._list_open_epics` a seam guarded by
`tests/test_live_capacity.py`. So `_running_escalation_ids` is exercised against
a client that records the query it was handed — the production function, the
production query string — and the *listing* is driven against real workflows.

Runtime evidence is pasted verbatim at the bottom of this file (constitution
VIII / D-037).
"""

from __future__ import annotations

import asyncio
import json
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, NamedTuple

import pytest

from factory.cli import nouns
from factory.cli.main import main as ergane_main
from factory.notify import escalations
from factory.notify.escalations import (
    RUNNING_ESCALATIONS_QUERY,
    open_escalations,
)
from factory.notify.service import SIGNAL_NAME
from factory.verify import store
from factory.verify.models import EscalationChoice

from tests.test_escalation_workflow import (
    ABANDONED_ID,
    PRESS_AT,
    QUESTION,
    TASK_QUEUE,
    a_request,
    adapter,  # noqa: F401 - fixture
    db_path,  # noqa: F401 - fixture
    env,  # noqa: F401 - fixture
    escalation_worker,
    pending_ids,
    seed_abandoned,
    wait_until_settled,
    wait_until_waiting,
)
from tests.test_escalation_workflow import FakeAdapter
from temporalio.testing import WorkflowEnvironment

#: An id nothing has ever run under: the visibility index is eventually
#: consistent, so a list surface has to survive being told about one.
GHOST_ID = "ffff00001111"


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str

    @property
    def json(self) -> Any:
        return json.loads(self.stdout)


def _invoke(argv: tuple[str, ...]) -> int:
    try:
        code = ergane_main(list(argv))
    except SystemExit as exit_request:
        code = exit_request.code
    return 0 if code is None else int(code)


@pytest.fixture
def run_async(
    capsys: pytest.CaptureFixture[str],
) -> Callable[..., Awaitable[Run]]:
    async def invoke(*argv: str) -> Run:
        code = await asyncio.to_thread(_invoke, argv)
        captured = capsys.readouterr()
        return Run(code, captured.out, captured.err)

    return invoke


@dataclass
class FakeExecution:
    id: str


class RecordingClient:
    """A client that remembers the visibility query it was handed."""

    def __init__(self, ids: tuple[str, ...]) -> None:
        self.ids = ids
        self.queries: list[str] = []

    def list_workflows(self, query: str = "", **_kwargs: Any) -> Any:
        self.queries.append(query)

        async def iterate() -> AsyncIterator[FakeExecution]:
            for workflow_id in self.ids:
                yield FakeExecution(id=workflow_id)

        return iterate()


# ============================================================================
# T011 — US2-S4 / FR-008: the list is a Temporal read
# ============================================================================


async def test_the_running_read_asks_temporal_for_running_escalations() -> None:
    """FR-008: the enumeration is a visibility query, not a table scan.

    The query string is pinned because Temporal's visibility grammar wants the
    title-case status name rather than the SDK enum's `.name` — the same trap
    `_list_open_epics` documents — and because a query that dropped the
    `WorkflowType` clause would enumerate every workflow in the namespace.
    """
    client = RecordingClient(("aaaa11112222", "bbbb33334444"))

    found = await escalations._running_escalation_ids(client)

    assert found == ("aaaa11112222", "bbbb33334444")
    assert client.queries == [RUNNING_ESCALATIONS_QUERY]
    assert 'WorkflowType = "EscalationWorkflow"' in RUNNING_ESCALATIONS_QUERY
    assert 'ExecutionStatus = "Running"' in RUNNING_ESCALATIONS_QUERY


async def test_open_escalations_reports_workflows_and_not_the_store(
    env: WorkflowEnvironment,  # noqa: F811
    db_path: Path,  # noqa: F811
    adapter: FakeAdapter,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US2-S4: every open escalation, with its question and its deadline.

    The two seeded facts below are what make this impossible for a store scrape
    to satisfy: one row is settled while its workflow still waits, and one row is
    pending with no workflow at all.
    """
    seed_abandoned(db_path)

    async with escalation_worker(env):
        first = await escalations.start_escalation(
            env.client, a_request(node_id="us2"), task_queue=TASK_QUEUE
        )
        second = await escalations.start_escalation(
            env.client, a_request(node_id="us3"), task_queue=TASK_QUEUE
        )
        await wait_until_waiting(env.client, first.id)
        await wait_until_waiting(env.client, second.id)

        # Fact 1: this escalation's row is already settled, and it is still
        # waiting. A pending-row scrape would not list it.
        with closing(store.connect(db_path)) as conn:
            assert store.resolve_escalation(
                conn, first.id, EscalationChoice.KILL, resolved_at=PRESS_AT
            )

        # Fact 2: the abandoned row is pending and has no workflow behind it.
        assert ABANDONED_ID in pending_ids(db_path)

        async def running(_client: Any) -> tuple[str, ...]:
            # The visibility index also reports ids that no longer resolve.
            return (first.id, second.id, ABANDONED_ID, GHOST_ID)

        monkeypatch.setattr(escalations, "_running_escalation_ids", running)

        listed = await open_escalations(env.client)
        assert {item.escalation_id for item in listed} == {first.id, second.id}
        assert {item.node_id for item in listed} == {"us2", "us3"}
        assert all(item.question == QUESTION for item in listed)
        assert all(item.expires_at for item in listed)

        # The question came from the workflow, not from the row: the store's
        # own text for these escalations says something else entirely.
        with closing(store.connect(db_path)) as conn:
            record = store.get_escalation(conn, second.id)
        assert record is not None
        assert QUESTION not in record.history_summary

        # It drains as answers and expiries land (FR-008's second half).
        #
        # `first.result()` is deliberately not awaited here. Awaiting a workflow
        # result is what unlocks time skipping, and the server then fast-forwards
        # to the next timer in the namespace — which is `second`'s hour. The
        # list would drain for the wrong reason, and the assertion below would
        # pass on a bug. `wait_until_settled` already proves `first` is terminal.
        await first.signal(SIGNAL_NAME, args=[first.id, "KILL", "@bryan"])
        await wait_until_settled(env.client, first.id)
        assert {item.escalation_id for item in await open_escalations(env.client)} == {
            second.id
        }

        await second.result()  # its hour runs out
        assert await open_escalations(env.client) == ()


async def test_ergane_escalations_list_prints_what_is_waiting(
    env: WorkflowEnvironment,  # noqa: F811
    db_path: Path,  # noqa: F811
    adapter: FakeAdapter,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    run_async: Callable[..., Awaitable[Run]],
) -> None:
    """US2-S4 through the operator's actual verb, exit code and all."""
    seed_abandoned(db_path)

    async with escalation_worker(env):
        handle = await escalations.start_escalation(
            env.client, a_request(), task_queue=TASK_QUEUE
        )
        await wait_until_waiting(env.client, handle.id)

        async def running(_client: Any) -> tuple[str, ...]:
            return (handle.id, ABANDONED_ID)

        async def open_client() -> Any:
            return env.client

        monkeypatch.setattr(escalations, "_running_escalation_ids", running)
        monkeypatch.setattr(nouns, "_open_client", open_client)

        listed = await run_async("escalations", "list")
        assert listed.code == 0, listed.stderr
        assert handle.id in listed.stdout
        assert QUESTION in listed.stdout
        assert ABANDONED_ID not in listed.stdout, (
            "the abandoned row reached the operator's list: this is a store "
            "scrape wearing a workflow query's clothes (FR-008)"
        )

        as_json = await run_async("escalations", "list", "--json")
        assert as_json.code == 0, as_json.stderr
        document = as_json.json
        assert [item["escalation_id"] for item in document] == [handle.id]
        assert document[0]["question"] == QUESTION

        # Drained once it is answered.
        await handle.signal(SIGNAL_NAME, args=[handle.id, "KILL", "@bryan"])
        await wait_until_settled(env.client, handle.id)
        await handle.result()
        drained = await run_async("escalations", "list")
        assert drained.code == 0, drained.stderr
        assert handle.id not in drained.stdout
        assert "no open escalations" in drained.stdout


# ============================================================================
# EVIDENCE — pasted verbatim (constitution VIII / D-037)
# ============================================================================

TEST_SERVER_HAS_NO_VISIBILITY_API = """
$ uv run python probe_list.py     # two workflows running on the time-skipping server
query='WorkflowType = "Waiter"' -> ERROR RPCError: Method temporal.api.workflowservice.v1.WorkflowService/ListWorkflowExecutions is unimplemented
query='ExecutionStatus = "Running"' -> ERROR RPCError: Method temporal.api.workflowservice.v1.WorkflowService/ListWorkflowExecutions is unimplemented
query='WorkflowType = "Waiter" AND ExecutionStatus = "Running"' -> ERROR RPCError: Method temporal.api.workflowservice.v1.WorkflowService/ListWorkflowExecutions is unimplemented
query='' -> ERROR RPCError: Method temporal.api.workflowservice.v1.WorkflowService/ListWorkflowExecutions is unimplemented
query peek: waiting
h1 result: answered
after-list ERROR RPCError Method temporal.api.workflowservice.v1.WorkflowService/ListWorkflowExecutions is unimplemented
h2 result (timer skip): expired
"""

RED_BEFORE_THE_IMPLEMENTATION = """
Written before `factory/notify/escalations.py` and the `escalations` noun exist.

$ uv run pytest tests/test_escalation_workflow.py tests/test_ergane_escalations.py -q
tests/test_ergane_escalations.py:49: in <module>
    from factory.notify import escalations
E   ImportError: cannot import name 'escalations' from 'factory.notify'
    (.../factory/notify/__init__.py)
=========================== short test summary info ============================
ERROR tests/test_escalation_workflow.py
ERROR tests/test_ergane_escalations.py
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!!
2 errors in 0.11s
"""

MUTATIONS = """
(pasted by the implementation commit, from runs actually made)
"""
