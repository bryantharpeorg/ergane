"""Escalation is a workflow type: standalone, as a child, and settled by itself.

041-US2. `factory/escalation/workflow.py` hosts one escalation per workflow — the
workflow ID *is* the correlation id, delivery is an activity through US1's
configured adapter, expiry is the workflow's own durable timer, the answer
arrives as 008's `escalation_resolved` signal, and the result is
`ANSWERED(resolution, identity)` or `EXPIRED`.

Nothing here fakes the lifecycle. The workflow is the real one, the activities
are the real `send_escalation` / `expire_escalation` / `settle_escalation`, the
store is a real SQLite evidence store under `tmp_path`, and the only fake is the
socket: US1's `FakeAdapter` stands in for Telegram, exactly as 041-US1 landed it.
Nothing in this file sends a real message, and nothing in it can.

What each test pins down, and what would make it pass if the production code did
nothing — the question this repository has paid most to learn to ask:

- **US2-S1, standalone.** A no-op `run()` cannot return `ANSWERED`/`EXPIRED`
  carrying the operator's choice, and cannot leave a terminal store row. Both
  the result and the row are asserted, so a workflow that returned the right
  word without recording anything fails.
- **US2-S1, the undelivered fail-safe.** Asserted from *the absence of a timer
  in the workflow's own history*: a workflow that waited out the hour and then
  gave up would return the same two fields, so the result alone cannot tell
  patience from a fail-safe.
- **US2-S2, as a child.** A parent starts the escalation as a child and awaits
  it. The parent's own history is asserted to carry no timer and its source to
  declare no signal handler; a parent that had grown either would still pass a
  result-only assertion.
- **US2-S3, the race.** Two tests, one per ordering, each driving the *store* to
  the losing side out of band the way the bridge does. A workflow that trusted
  its own branch instead of the store's guarded UPDATE would return the loser's
  answer and overwrite the row; both are asserted against.
- **US2-S3, determinism.** Every recorded history is re-run through `Replayer`
  against the workflow code. Signal-versus-timer is where this repository has
  produced nondeterminism findings (032, 038, 039), and a `run()` that branched
  on anything but recorded history fails there.
- **US2-S5, the env guard.** The guard is asserted to have *discovered* the new
  module by name, and then an `os.environ` read is spliced into that module's
  real source and the guard asserted to flag it. Asserting only that the guard
  passed would read as compliance if discovery were broken.
- **US2-S6, settlement per channel.** One full lifecycle per channel — a signal
  nobody wrote a row for (the CLI/relay shape), a signal whose row the bridge
  already wrote (the button shape), and expiry — with no pending row surviving
  any of them. An abandoned row in trap 9's live-store shape sits in the same
  table throughout and must come out exactly as it went in.

Two properties of the harness are deliberate, and both were learned the
expensive way in this file rather than assumed.

**Nothing here polls the store to find out where a workflow is.** The waits ask
the workflow's own `escalation_status` query. Polling SQLite would open a second
connection to the file the send activity is still writing, and the out-of-band
writes below — the ones standing in for the bridge — would be racing the thing
they are meant to arrive after.

**Time skipping only advances while a *workflow result* is awaited, and it
advances to the next timer in the whole namespace.** So a test that awaited one
escalation's result while a sibling still held its hour would expire the sibling
as a side effect. Every answered lifecycle therefore waits until its own status
query reports a resolution *before* its result is awaited, and the only results
awaited with an hour outstanding are the ones whose expiry is the point.

Runtime evidence — the red run before the implementation, the mutation
transcripts, and the final suite line — is pasted verbatim at the bottom of this
file (constitution VIII / D-037: the judge sees this diff and nothing else).
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import textwrap
from contextlib import asynccontextmanager, closing
from pathlib import Path
from typing import Any, AsyncIterator, Iterator

import pytest
from temporalio import workflow
from temporalio.api.enums.v1 import EventType
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, UnsandboxedWorkflowRunner, Worker

from factory.activities.notify_activities import (
    ESCALATION_TIMEOUT_S,
    expire_escalation,
    send_escalation,
    settle_escalation,
)
from factory.activities.verify_activities import (
    ERGANE_VERIFICATION_DB_PATH_ENV,
    VERIFICATION_DB_PATH_ENV,
)
from factory.notify.adapter import (
    ESCALATION_ADAPTER_ENV,
    DeliveryReceipt,
    RenderedMessage,
    register_adapter,
    unregister_adapter,
)
from factory.escalation.client import mint_correlation_id, start_escalation
from factory.escalation.workflow import (
    ESCALATION_STATUS_QUERY,
    OUTCOME_ANSWERED,
    OUTCOME_EXPIRED,
    EscalationRequest,
    EscalationWorkflow,
    child_correlation_id,
)
from factory.notify.service import SIGNAL_NAME
from factory.verify import store
from factory.verify.models import EscalationChoice, EscalationRecord

from tests.test_messenger_adapter import Delivered, FakeAdapter

#: The queue this file's worker polls. Deliberately not the production queue:
#: nothing here should be servable by a worker an operator happens to be running.
TASK_QUEUE = "escalations-under-test"

EPIC = "041-escalation-workflow"
NODE = "us2"

HISTORY = "attempt 1 FAIL (gates)\nattempt 2 FAIL (judge)\nattempt 3 FAIL (gates)"

#: What the operator is being asked, in the words the list surface shows. Kept
#: distinct from `HISTORY` so a surface that scraped the store's
#: `history_summary` column instead of asking the workflow is visible.
QUESTION = "us2 has exhausted its ladder — retry, kill, or pause the epic?"

FAKE_ADAPTER_NAME = "fake-messenger-us2"

#: Timestamps written by the out-of-band writers that stand in for the bridge.
#: Distinctive so an assertion that the row was *not* overwritten is exact.
PRESS_AT = "2026-08-16T09:14:00Z"
TIMEOUT_AT = "2026-08-16T09:15:00Z"

#: Trap 9's live-store shape: an escalation delivered to Telegram for a node
#: that finished over a week ago, still pending, long past its deadline.
#: Fourteen of these sat in `.factory/verification.db` on 2026-08-14, and
#: `idx_esc_pending` was 70% of them. Anything this story adds has to survive a
#: table that contains them.
ABANDONED_ID = "abab12345678"
ABANDONED_SENT_AT = "2026-08-06T14:55:00Z"
ABANDONED_EXPIRES_AT = "2026-08-06T15:55:00Z"


# --- the world --------------------------------------------------------------


class SilentAdapter(FakeAdapter):
    """A transport that is down: it records the attempt and pages nobody.

    `delivered=False` is the whole vocabulary for "nobody was paged" (US1), and
    the escalation's answer to it is to apply the fail-safe default *now* rather
    than wait out an hour of silence that means nothing (002 R11).
    """

    async def deliver(
        self, message: RenderedMessage, correlation_id: str
    ) -> DeliveryReceipt:
        self.delivered.append(Delivered(message, correlation_id))
        return DeliveryReceipt(delivered=False)


@workflow.defn
class ParentUnderTest:
    """A parent that needs an operator answer and owns none of the machinery.

    US2-S2's whole claim in one class: it mints the child's correlation id in
    workflow scope (replay-safe, no `secrets`), starts an `EscalationWorkflow`
    as a child with that id, and awaits it. It declares no signal handler and
    starts no timer — the child owns both — which the test asserts from this
    class's own source and from the parent's own history rather than from the
    result. The `child_id` query exists so the test can press the *child's*
    button, which is exactly how a bridge reaches it: by correlation id, with no
    knowledge that a parent exists.
    """

    def __init__(self) -> None:
        self._child_id = ""

    @workflow.query
    def child_id(self) -> str:
        return self._child_id

    @workflow.run
    async def run(self, request: EscalationRequest) -> Any:
        self._child_id = child_correlation_id()
        return await workflow.execute_child_workflow(
            EscalationWorkflow.run, request, id=self._child_id
        )


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    environment = await WorkflowEnvironment.start_time_skipping()
    try:
        yield environment
    finally:
        await environment.shutdown()


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A real evidence store, under tmp, where the activities will find it."""
    path = tmp_path / ".factory" / "verification.db"
    monkeypatch.setenv(ERGANE_VERIFICATION_DB_PATH_ENV, str(path))
    monkeypatch.delenv(VERIFICATION_DB_PATH_ENV, raising=False)
    return path


@pytest.fixture
def adapter(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeAdapter]:
    """A transport that is not Telegram, selected the way a real one is."""
    fake = FakeAdapter()
    register_adapter(FAKE_ADAPTER_NAME, lambda **_seams: fake)
    monkeypatch.setenv(ESCALATION_ADAPTER_ENV, FAKE_ADAPTER_NAME)
    try:
        yield fake
    finally:
        unregister_adapter(FAKE_ADAPTER_NAME)


@pytest.fixture
def silent_adapter(monkeypatch: pytest.MonkeyPatch) -> Iterator[SilentAdapter]:
    fake = SilentAdapter()
    register_adapter(FAKE_ADAPTER_NAME, lambda **_seams: fake)
    monkeypatch.setenv(ESCALATION_ADAPTER_ENV, FAKE_ADAPTER_NAME)
    try:
        yield fake
    finally:
        unregister_adapter(FAKE_ADAPTER_NAME)


@asynccontextmanager
async def escalation_worker(env: WorkflowEnvironment) -> AsyncIterator[None]:
    """The real workflow and the real activities, on a queue of this file's own."""
    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[EscalationWorkflow, ParentUnderTest],
        activities=[send_escalation, expire_escalation, settle_escalation],
        workflow_runner=UnsandboxedWorkflowRunner(),
    ):
        yield


def a_request(**overrides: Any) -> EscalationRequest:
    fields: dict[str, Any] = {
        "epic_id": EPIC,
        "node_id": NODE,
        "history_summary": HISTORY,
        "question": QUESTION,
        "timeout_s": ESCALATION_TIMEOUT_S,
    }
    fields.update(overrides)
    return EscalationRequest(**fields)


# --- reading what happened --------------------------------------------------


def row(db_path: Path, escalation_id: str) -> EscalationRecord | None:
    with closing(store.connect(db_path)) as conn:
        return store.get_escalation(conn, escalation_id)


def pending_ids(db_path: Path) -> set[str]:
    with closing(store.connect(db_path)) as conn:
        return {record.escalation_id for record in store.pending_escalations(conn)}


def seed_abandoned(db_path: Path) -> None:
    """Plant trap 9's shape: delivered, unanswered, and long past its deadline."""
    with closing(store.connect(db_path)) as conn:
        store.insert_escalation(
            conn,
            EscalationRecord(
                escalation_id=ABANDONED_ID,
                workflow_id="epic-027-gate-suite-fake-time",
                epic_id="027-gate-suite-fake-time",
                node_id="us2",
                choices=[EscalationChoice.RETRY, EscalationChoice.KILL],
                history_summary="a node that finished over a week ago",
                sent_at=ABANDONED_SENT_AT,
                expires_at=ABANDONED_EXPIRES_AT,
                delivered=True,
            ),
        )


async def wait_until_waiting(client: Any, escalation_id: str) -> None:
    """Block until the escalation has been delivered and is awaiting an answer.

    Asked of the workflow itself rather than of the store, for two reasons. It
    opens no second connection to a SQLite file the send activity is writing —
    which is what the out-of-band writes below would otherwise be racing — and
    `expires_at` is only set once the send activity has *returned*, so a test
    that sees it knows the activity's own connection is closed.
    """
    for _ in range(1000):
        status = await client.get_workflow_handle(escalation_id).query(
            ESCALATION_STATUS_QUERY
        )
        if status["expires_at"]:
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"escalation {escalation_id} never reached its wait")


async def wait_until_settled(client: Any, escalation_id: str) -> None:
    """Block until the escalation has reached a terminal state.

    Used before awaiting a result that should *not* need the clock moved.
    Awaiting a workflow result is what unlocks time skipping, so a test that
    awaited one while its escalation was still holding a one-hour timer would
    be asking the server to choose between the answer in flight and the hour —
    and the answer would lose about as often as the scheduler felt like it.
    """
    for _ in range(1000):
        status = await client.get_workflow_handle(escalation_id).query(
            ESCALATION_STATUS_QUERY
        )
        if status["resolution"] is not None:
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"escalation {escalation_id} never settled")


async def wait_for_child(parent: Any) -> str:
    """The correlation id the parent minted for its child."""
    for _ in range(500):
        child = await parent.query("child_id")
        if child:
            return str(child)
        await asyncio.sleep(0.01)
    raise AssertionError("the parent never started a child")


async def event_names(handle: Any) -> list[str]:
    history = await handle.fetch_history()
    return [EventType.Name(event.event_type) for event in history.events]


async def replay(handle: Any) -> None:
    """Re-run one recorded history against the workflow code, with no worker."""
    await Replayer(
        workflows=[EscalationWorkflow, ParentUnderTest],
        workflow_runner=UnsandboxedWorkflowRunner(),
    ).replay_workflow(await handle.fetch_history())


# ============================================================================
# T008 — US2-S1: the standalone lifecycle
# ============================================================================


async def test_a_standalone_escalation_delivers_awaits_and_answers(
    env: WorkflowEnvironment, db_path: Path, adapter: FakeAdapter
) -> None:
    """US2-S1: no parent, no epic — deliver, await, answer, record.

    The correlation id is the workflow id: the starter mints it (trap 3 — a
    workflow id must exist before `start_workflow`, and `secrets.token_hex`
    cannot be called from workflow scope) and the delivery carries that same id,
    so a press can name the workflow without carrying one.
    """
    async with escalation_worker(env):
        handle = await start_escalation(
            env.client, a_request(), task_queue=TASK_QUEUE
        )
        await wait_until_waiting(env.client, handle.id)

        # Trap 3: one id, 12 hex digits wide, and it is the workflow's own.
        assert len(handle.id) == 12
        assert int(handle.id, 16) >= 0
        assert [sent.correlation_id for sent in adapter.delivered] == [handle.id]
        assert HISTORY in adapter.delivered[0].message.text

        await handle.signal(SIGNAL_NAME, args=[handle.id, "RETRY", "@bryan"])
        await wait_until_settled(env.client, handle.id)
        outcome = await handle.result()

    assert outcome.escalation_id == handle.id
    assert outcome.outcome == OUTCOME_ANSWERED
    assert outcome.resolution == EscalationChoice.RETRY.value
    assert outcome.identity == "@bryan"
    assert outcome.delivered is True
    assert outcome.late is None

    # The result is not the record: the row is terminal too (FR-006, FR-013).
    record = row(db_path, handle.id)
    assert record is not None
    assert record.resolution == EscalationChoice.RETRY
    assert record.resolved_at is not None
    assert handle.id not in pending_ids(db_path)


async def test_a_standalone_escalation_expires_at_its_own_deadline(
    env: WorkflowEnvironment, db_path: Path, adapter: FakeAdapter
) -> None:
    """US2-S1: silence runs out on the workflow's own durable timer."""
    async with escalation_worker(env):
        handle = await start_escalation(
            env.client, a_request(), task_queue=TASK_QUEUE
        )
        outcome = await handle.result()

    assert outcome.outcome == OUTCOME_EXPIRED
    assert outcome.resolution == store.EXPIRED
    assert outcome.identity == ""
    assert outcome.delivered is True

    record = row(db_path, handle.id)
    assert record is not None
    assert record.resolution == store.EXPIRED
    assert handle.id not in pending_ids(db_path)

    # The wait was a real durable timer, not a poll loop (006-US1's shape).
    assert "EVENT_TYPE_TIMER_STARTED" in await event_names(handle)


async def test_an_undelivered_escalation_gives_up_without_starting_a_timer(
    env: WorkflowEnvironment, db_path: Path, silent_adapter: SilentAdapter
) -> None:
    """US2-S1 / 002 R11: nobody was paged, so nothing is waited out.

    Asserted from the workflow's own history rather than from its result: a
    workflow that waited the full hour and then expired would return the same
    two fields. `EVENT_TYPE_TIMER_STARTED` is what tells patience from a
    fail-safe.
    """
    async with escalation_worker(env):
        handle = await start_escalation(
            env.client, a_request(), task_queue=TASK_QUEUE
        )
        outcome = await handle.result()

    assert outcome.delivered is False
    assert outcome.outcome == OUTCOME_EXPIRED
    assert silent_adapter.delivered, "the transport was never even tried"

    assert "EVENT_TYPE_TIMER_STARTED" not in await event_names(handle), (
        "an undelivered escalation started a timer: it is waiting out an hour "
        "for a message nobody received (002 R11)"
    )

    # FR-013: terminal is terminal, so no pending row outlives it — and the
    # undelivered path is one of the ways the live store grew fourteen of them.
    record = row(db_path, handle.id)
    assert record is not None
    assert record.resolution is not None
    assert handle.id not in pending_ids(db_path)


# ============================================================================
# T009 — US2-S2: a child of a test parent
# ============================================================================


async def test_a_test_parent_awaits_the_child_and_owns_no_lifecycle(
    env: WorkflowEnvironment, db_path: Path, adapter: FakeAdapter
) -> None:
    """US2-S2: answer and expiry both arrive as the child's result.

    The parent is signalled by nobody: the press names the *child*, because the
    child's workflow id is the correlation id. That is what lets a consumer
    without an epic use this at all — and why the 017 peer-park deadlock stops
    being structural.
    """
    async with escalation_worker(env):
        answered_parent = await env.client.start_workflow(
            ParentUnderTest.run,
            a_request(),
            id="parent-answered",
            task_queue=TASK_QUEUE,
        )
        answered_child = await wait_for_child(answered_parent)
        await wait_until_waiting(env.client, answered_child)
        await env.client.get_workflow_handle(answered_child).signal(
            SIGNAL_NAME, args=[answered_child, "PAUSE_EPIC", "@bryan"]
        )
        await wait_until_settled(env.client, answered_child)
        answered = await answered_parent.result()

        expired_parent = await env.client.start_workflow(
            ParentUnderTest.run,
            a_request(),
            id="parent-expired",
            task_queue=TASK_QUEUE,
        )
        expired_child = await wait_for_child(expired_parent)
        expired = await expired_parent.result()

    assert answered["outcome"] == OUTCOME_ANSWERED
    assert answered["resolution"] == EscalationChoice.PAUSE_EPIC.value
    assert answered["identity"] == "@bryan"
    assert expired["outcome"] == OUTCOME_EXPIRED
    assert expired["resolution"] == store.EXPIRED

    # The parent holds no timer of its own: the child's history has one, the
    # parent's does not.
    parent_events = await event_names(expired_parent)
    child_events = await event_names(env.client.get_workflow_handle(expired_child))
    assert "EVENT_TYPE_TIMER_STARTED" in child_events
    assert "EVENT_TYPE_TIMER_STARTED" not in parent_events, (
        "the parent started a timer of its own; expiry belongs to the child"
    )

    # And no signal handler of its own, read off the parent's own source.
    parent_source = ast.parse(textwrap.dedent(inspect.getsource(ParentUnderTest)))
    decorators = [
        ast.unparse(decorator)
        for node in ast.walk(parent_source)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for decorator in node.decorator_list
    ]
    assert not [name for name in decorators if "signal" in name], (
        f"the parent declares a signal handler ({decorators}); the child owns "
        "the answer"
    )


# ============================================================================
# T010 — US2-S3: the race, and only one winner
# ============================================================================


async def test_a_press_that_beat_the_timer_decides_the_escalation(
    env: WorkflowEnvironment, db_path: Path, adapter: FakeAdapter
) -> None:
    """US2-S3 / 002 R12: the timer fires second and takes the store's word.

    The press is written the way `CallbackBridge` writes it — the store's
    guarded UPDATE, out of band, while the workflow is still waiting — and no
    signal is ever delivered, which is what happens when the bridge cannot reach
    Temporal. The workflow's own timer then fires, so the only thing that can
    save the operator's decision is asking the store rather than trusting the
    branch it took (plan trap 2: two arbiters is how a press that beat the timer
    starts losing sometimes).
    """
    async with escalation_worker(env):
        handle = await start_escalation(
            env.client, a_request(), task_queue=TASK_QUEUE
        )
        await wait_until_waiting(env.client, handle.id)
        with closing(store.connect(db_path)) as conn:
            assert store.resolve_escalation(
                conn, handle.id, EscalationChoice.RETRY, resolved_at=PRESS_AT
            )
        outcome = await handle.result()

    # Exactly one outcome won, and it is the operator's.
    assert outcome.outcome == OUTCOME_ANSWERED
    assert outcome.resolution == EscalationChoice.RETRY.value
    assert outcome.late == OUTCOME_EXPIRED, (
        "the expiry lost and was not carried back as the late arrival"
    )

    # The loser did not overwrite the winner: the row is byte-for-byte the
    # press the bridge recorded.
    record = row(db_path, handle.id)
    assert record is not None
    assert record.resolution == EscalationChoice.RETRY
    assert record.resolved_at == PRESS_AT


async def test_an_answer_that_lost_to_the_hour_does_not_reopen_it(
    env: WorkflowEnvironment, db_path: Path, adapter: FakeAdapter
) -> None:
    """US2-S3, the mirror: the store expired first, so the answer is late.

    No error escapes — the workflow completes normally and reports what the
    store settled on, carrying the answer that arrived too late as evidence
    rather than dropping it on the floor.
    """
    async with escalation_worker(env):
        handle = await start_escalation(
            env.client, a_request(), task_queue=TASK_QUEUE
        )
        await wait_until_waiting(env.client, handle.id)
        with closing(store.connect(db_path)) as conn:
            assert store.expire_escalation(conn, handle.id, resolved_at=TIMEOUT_AT)
        await handle.signal(SIGNAL_NAME, args=[handle.id, "RETRY", "@bryan"])
        await wait_until_settled(env.client, handle.id)
        outcome = await handle.result()

    assert outcome.outcome == OUTCOME_EXPIRED
    assert outcome.resolution == store.EXPIRED
    assert outcome.late == EscalationChoice.RETRY.value

    record = row(db_path, handle.id)
    assert record is not None
    assert record.resolution == store.EXPIRED
    assert record.resolved_at == TIMEOUT_AT


async def test_a_choice_nobody_offered_is_not_an_answer(
    env: WorkflowEnvironment, db_path: Path, adapter: FakeAdapter
) -> None:
    """US2-S3, no error escapes: a forged or narrowed choice never resolves.

    The escalations table's CHECK constraints pin the vocabulary, so a signal
    carrying anything else would fail the settling activity and, through its
    retry policy, the whole workflow. The offered set is the workflow's own and
    is checked in workflow scope, where it is pure.
    """
    async with escalation_worker(env):
        handle = await start_escalation(
            env.client,
            a_request(choices=[EscalationChoice.RETRY, EscalationChoice.KILL]),
            task_queue=TASK_QUEUE,
        )
        await wait_until_waiting(env.client, handle.id)
        await handle.signal(SIGNAL_NAME, args=[handle.id, "PAUSE_EPIC", "@x"])
        await handle.signal(SIGNAL_NAME, args=[handle.id, "BANANA", "@x"])
        outcome = await handle.result()

    # The escalation waited out its hour: neither signal was an answer.
    assert outcome.outcome == OUTCOME_EXPIRED
    assert outcome.resolution == store.EXPIRED


# ============================================================================
# T010a — US2-S6: settlement is the workflow's, whatever channel answered
# ============================================================================


async def test_settlement_is_the_workflows_own_transition_on_every_channel(
    env: WorkflowEnvironment, db_path: Path, adapter: FakeAdapter
) -> None:
    """US2-S6 / FR-013: no channel is the difference between settled and abandoned.

    One full lifecycle per channel:

    1. **A signal nobody wrote a row for** — the shape `ergane build resolve`
       and any webhook relay produce. This is the finding's measured defect
       (`interpreter/resolved-escalation-never-clears-in-the-store`, recurred):
       the CLI signals and walks away, so today the row stays pending forever.
       Nothing but the workflow can settle this one, which is what makes it a
       test that cannot pass accidentally.
    2. **A signal whose row the bridge already settled** — the button shape. The
       row must keep the bridge's own record, resolved exactly once.
    3. **Expiry**, which settles as `EXPIRED` via `TIMEOUT`.

    Trap 9's abandoned row sits in the same table for all three and must come
    out exactly as it went in: settling *an* escalation is not sweeping the
    table, and a surface that means "pending" is still reading it.
    """
    seed_abandoned(db_path)

    async with escalation_worker(env):
        # 1. the CLI/relay channel: a signal, and no other writer at all.
        relayed = await start_escalation(
            env.client, a_request(), task_queue=TASK_QUEUE
        )
        await wait_until_waiting(env.client, relayed.id)
        await relayed.signal(SIGNAL_NAME, args=[relayed.id, "KILL", "@bryan"])
        await wait_until_settled(env.client, relayed.id)
        relayed_outcome = await relayed.result()

        # 2. the button channel: the bridge settles the row, then signals.
        pressed = await start_escalation(
            env.client, a_request(), task_queue=TASK_QUEUE
        )
        await wait_until_waiting(env.client, pressed.id)
        with closing(store.connect(db_path)) as conn:
            assert store.resolve_escalation(
                conn, pressed.id, EscalationChoice.KILL, resolved_at=PRESS_AT
            )
        await pressed.signal(SIGNAL_NAME, args=[pressed.id, "KILL", "@bryan"])
        await wait_until_settled(env.client, pressed.id)
        pressed_outcome = await pressed.result()

        # 3. the clock.
        timed_out = await start_escalation(
            env.client, a_request(), task_queue=TASK_QUEUE
        )
        expired_outcome = await timed_out.result()

    assert relayed_outcome.resolution == EscalationChoice.KILL.value
    assert pressed_outcome.resolution == EscalationChoice.KILL.value
    assert expired_outcome.resolution == store.EXPIRED

    settled = {
        "relayed": row(db_path, relayed.id),
        "pressed": row(db_path, pressed.id),
        "expired": row(db_path, timed_out.id),
    }
    for channel, record in settled.items():
        assert record is not None, f"{channel}: the row vanished"
        assert record.resolution is not None, (
            f"{channel}: the lifecycle reached a terminal state and left a "
            "pending row — settlement belonged to the channel again (FR-013)"
        )
        assert record.resolved_at is not None

    # The button's row still carries the bridge's own record, resolved once.
    assert settled["pressed"].resolved_at == PRESS_AT

    # Nothing this story did touched the abandoned row.
    abandoned = row(db_path, ABANDONED_ID)
    assert abandoned is not None
    assert abandoned.resolution is None
    assert abandoned.sent_at == ABANDONED_SENT_AT
    assert pending_ids(db_path) == {ABANDONED_ID}


# ============================================================================
# T010 — determinism: every lifecycle above replays
# ============================================================================


async def test_every_lifecycle_replays(
    env: WorkflowEnvironment, db_path: Path, adapter: FakeAdapter
) -> None:
    """US2-S3: signal-versus-timer is deterministic, proven by replay.

    "Exactly one outcome wins deterministically" is a claim about replay, not
    about a single run: a `run()` that decided on anything but recorded history
    would produce a different command sequence the second time through, which is
    exactly what `Replayer` refuses. 032, 038 and 039 are this repository's
    nondeterminism findings, and every one of them was this shape.
    """
    async with escalation_worker(env):
        answered = await start_escalation(
            env.client, a_request(), task_queue=TASK_QUEUE
        )
        await wait_until_waiting(env.client, answered.id)
        await answered.signal(SIGNAL_NAME, args=[answered.id, "RETRY", "@b"])
        await wait_until_settled(env.client, answered.id)
        await answered.result()

        # The press wins at the store; the timer arrives second.
        raced = await start_escalation(env.client, a_request(), task_queue=TASK_QUEUE)
        await wait_until_waiting(env.client, raced.id)
        with closing(store.connect(db_path)) as conn:
            assert store.resolve_escalation(
                conn, raced.id, EscalationChoice.KILL, resolved_at=PRESS_AT
            )
        await raced.result()

        expired = await start_escalation(
            env.client, a_request(), task_queue=TASK_QUEUE
        )
        await expired.result()

        parent = await env.client.start_workflow(
            ParentUnderTest.run,
            a_request(),
            id="parent-replayed",
            task_queue=TASK_QUEUE,
        )
        await parent.result()

        for handle in (answered, raced, expired, parent):
            await replay(handle)


# ============================================================================
# T012 — US2-S5: 039's guard covers the new workflow module
# ============================================================================


def test_039s_guard_found_this_workflow_module_and_can_still_fail() -> None:
    """US2-S5 / FR-012: discovered by construction, and provably not blind.

    Two claims, because either alone is worthless. The guard *found*
    `factory/escalation/workflow.py` — a discovery bug would otherwise read as
    compliance — and the guard still has teeth on that module's real source: an
    `os.environ` read spliced into `run()` is flagged, naming the function.

    This is the defect that wedged the roadmap for eleven hours on 2026-08-13: a
    `_verification_db_path()` reading `os.environ` from workflow code silently
    disabled the entire schedule, and nothing noticed for a day.
    """
    from tests.test_workflow_env_guard import (
        _collect_violations,
        _discover_workflow_modules,
    )

    import factory.escalation.workflow as escalation_workflow

    factory_root = Path(__file__).resolve().parent.parent / "factory"
    module_path = Path(escalation_workflow.__file__).resolve()

    discovered = {path.resolve() for path in _discover_workflow_modules(factory_root)}
    assert module_path in discovered, (
        f"039's guard did not discover {module_path}; it scans for the "
        "@workflow.defn decorator, so a module it cannot see is a module it "
        "cannot guard"
    )

    source = module_path.read_text(encoding="utf-8")
    assert _collect_violations(source, str(module_path)) == []

    # And the guard is not merely silent about this file: put the defect back.
    marker = "        self._request = request"
    assert marker in source, (
        "the mutation anchor moved; re-point it at the first line of run()"
    )
    mutated = source.replace(
        marker,
        "        import os\n\n        os.environ.get('ERGANE_ROOT')\n" + marker,
        1,
    )
    violations = _collect_violations(mutated, str(module_path))
    assert violations, (
        "an os.environ read inside run() was not flagged — 039's guard has "
        "stopped covering this module"
    )
    assert "run()" in violations[0]


def test_the_outcome_vocabulary_is_the_stores() -> None:
    """One spelling of EXPIRED, so a reader of either never has to translate."""
    assert OUTCOME_EXPIRED == store.EXPIRED
    assert OUTCOME_ANSWERED == store.ANSWERED


def test_the_workflow_reads_no_wall_clock() -> None:
    """Constitution IV: no wall clock and no randomness in workflow code.

    A wall-clock read replays differently every time. It is the same class of
    defect as the env read above and is *not* covered by 039's guard, which
    looks only for the environment.

    This asserts the absence of the banned calls and deliberately does not
    assert the presence of `workflow.now()`. The escalation's timer is a
    duration — the row's own window, anchored at the send — because the row's
    `expires_at` is minted from the *worker host's* clock inside an activity
    while `workflow.now()` is Temporal's. Waiting until a deadline one clock
    produced, measured by another, expires escalations the instant they are
    raised whenever the two disagree; it was reproduced exactly that way here
    before this test file's implementation landed.
    """
    import factory.escalation.workflow as escalation_workflow

    source = Path(escalation_workflow.__file__).read_text(encoding="utf-8")
    banned = {"datetime.now", "time.time", "time.monotonic", "random.random"}
    called = {
        ast.unparse(node.func)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not (called & banned), f"workflow code reads a wall clock: {called & banned}"


# ============================================================================
# EVIDENCE — pasted verbatim (constitution VIII / D-037)
# ============================================================================

RED_BEFORE_THE_IMPLEMENTATION = """
Written before `factory/escalation/workflow.py` and `settle_escalation` exist, so
every test here fails at import until they land (the 005/008/039 precedent).

$ uv run pytest tests/test_escalation_workflow.py tests/test_ergane_escalations.py -q
==================================== ERRORS ====================================
______________ ERROR collecting tests/test_escalation_workflow.py ______________
ImportError while importing test module '.../tests/test_escalation_workflow.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/.../importlib/__init__.py:88: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
tests/test_escalation_workflow.py:73: in <module>
    from factory.activities.notify_activities import (
E   ImportError: cannot import name 'settle_escalation' from
    'factory.activities.notify_activities' (.../factory/activities/notify_activities.py)
______________ ERROR collecting tests/test_ergane_escalations.py _______________
tests/test_ergane_escalations.py:49: in <module>
    from factory.escalation import client as escalations
E   ImportError: cannot import name 'escalations' from 'factory.notify'
    (.../factory/notify/__init__.py)
=========================== short test summary info ============================
ERROR tests/test_escalation_workflow.py
ERROR tests/test_ergane_escalations.py
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!!
2 errors in 0.11s
"""

MUTATIONS = """
Seven behaviours, seven mutations of the *production* code, each watched go red
on its own and then reverted. Long absolute paths elided to `.../`; nothing else
is edited.

--- 1. the workflow stops settling an answered escalation (FR-013) ------------
    `_settle_answer`: drop the `settle_escalation` call and return the signal's
    choice, which is what the epic's park does today.

$ uv run pytest tests/test_escalation_workflow.py -q --tb=line
F....F.F....                                                             [100%]
E   AssertionError: assert None == <EscalationChoice.RETRY: 'RETRY'>
     +  where None = EscalationRecord(escalation_id='3de0b3f39da0', ... resolution=None, resolved_at=None, check_evidence=()).resolution
.../tests/test_escalation_workflow.py:383: AssertionError
E   AssertionError: assert 'ANSWERED' == 'EXPIRED'
.../tests/test_escalation_workflow.py:577: AssertionError
E   AssertionError: relayed: the lifecycle reached a terminal state and left a pending row - settlement belonged to the channel again (FR-013)
    assert None is not None
.../tests/test_escalation_workflow.py:681: AssertionError
FAILED tests/test_escalation_workflow.py::test_a_standalone_escalation_delivers_awaits_and_answers
FAILED tests/test_escalation_workflow.py::test_an_answer_that_lost_to_the_hour_does_not_reopen_it
FAILED tests/test_escalation_workflow.py::test_settlement_is_the_workflows_own_transition_on_every_channel
3 failed, 9 passed in 2.65s

--- 2. the undelivered fail-safe is removed (002 R11) -------------------------
    `run()`: drop the `if not sent.delivered` branch, so an undelivered
    escalation falls through to the timer.

$ uv run pytest tests/test_escalation_workflow.py -q --tb=line
..F.........                                                             [100%]
E   AssertionError: assert True is False
     +  where True = EscalationOutcome(escalation_id='7b171438912e', outcome='EXPIRED', resolution='EXPIRED', identity='', delivered=True, late=None).delivered
------------------------------ Captured log call -------------------------------
WARNING  factory.activities.notify_activities:notify_activities.py:532 escalation 7b171438912e: not delivered
.../tests/test_escalation_workflow.py:428: AssertionError
FAILED tests/test_escalation_workflow.py::test_an_undelivered_escalation_gives_up_without_starting_a_timer
1 failed, 11 passed in 2.90s

--- 3. the expiry path stops asking the store who won (FR-007, 002 R12) -------
    `_settle_unanswered`: `recorded = OUTCOME_EXPIRED` instead of taking what
    `expire_escalation` read back. This is plan trap 2's "two arbiters" as a
    one-line change.

$ uv run pytest tests/test_escalation_workflow.py -q --tb=line
....F.......                                                             [100%]
E   AssertionError: assert 'EXPIRED' == 'ANSWERED'
      - ANSWERED
      + EXPIRED
.../tests/test_escalation_workflow.py:543: AssertionError
FAILED tests/test_escalation_workflow.py::test_a_press_that_beat_the_timer_decides_the_escalation
1 failed, 11 passed in 2.86s

--- 4. any reply becomes an answer (no error escapes) -------------------------
    `_answer()`: return the first buffered reply without checking `_offered`.

$ uv run pytest tests/test_escalation_workflow.py -q --tb=line
......F.....                                                             [100%]
E   AssertionError: assert 'ANSWERED' == 'EXPIRED'
      - EXPIRED
      + ANSWERED
.../tests/test_escalation_workflow.py:609: AssertionError
FAILED tests/test_escalation_workflow.py::test_a_choice_nobody_offered_is_not_an_answer
1 failed, 11 passed in 2.90s

--- 5. a wall clock is read in workflow scope (constitution IV) ---------------
    `run()`: `datetime.now(timezone.utc)` at the top.

$ uv run pytest tests/test_escalation_workflow.py -q --tb=line
...........F                                                             [100%]
E   AssertionError: workflow code reads a wall clock: {'datetime.now'}
.../tests/test_escalation_workflow.py:835: AssertionError
FAILED tests/test_escalation_workflow.py::test_the_workflow_reads_no_wall_clock
1 failed, 11 passed in 3.14s

--- 6. an os.environ read is put back into workflow scope (FR-012) -----------
    `run()`: `os.environ.get('ERGANE_ROOT')`. This is the roadmap-wedging
    defect of 2026-08-13, in the new module, and 039's guard catches it with no
    edit of its own — which is the whole claim US2-S5 makes.

$ uv run pytest tests/test_workflow_env_guard.py -q --tb=line
F.                                                                       [100%]
E   AssertionError: workflow-scoped environment read(s) found:
    .../factory/escalation/workflow.py:295: run() reads process environment: os.environ
.../tests/test_workflow_env_guard.py:212: AssertionError
FAILED tests/test_workflow_env_guard.py::test_guard_discovers_workflow_modules_and_forbids_env_reads
1 failed, 1 passed in 0.10s

--- 7. the child's correlation id stops being replay-safe (US2-S3) -----------
    `child_correlation_id`: `uuid.uuid4()` instead of `workflow.uuid4()`. The
    only symptom is on replay, which is exactly why the replay test exists.

$ uv run pytest tests/test_escalation_workflow.py -q --tb=line
........F...                                                             [100%]
E   temporalio.workflow._exceptions.NondeterminismError: Workflow activation completion failed:
    "[TMPRL1100] Nondeterminism error: Child workflow id of scheduled event
    'f81e74af9ad4' does not match child workflow id of command '621a3b61a5e8'"
    force_cause: NonDeterministicError
FAILED tests/test_escalation_workflow.py::test_every_lifecycle_replays
1 failed, 11 passed in 3.02s
"""


FINAL_SUITE = """
$ uv run pytest -q
2673 passed, 44 skipped, 4 warnings in 290.23s (0:04:50)
"""
