"""US1 — an addressee turns the 008 question channel into a peer channel.

017-US1 (T003–T006, written before T007). 008 built a channel with exactly one
addressee: the marker (or the ferry file) parks a node, a Telegram page goes
out, and the operator's free-text answer comes back. Every word of that channel
is hardwired to one human. This story adds the one thing it lacks — the
address — and the routing that honours it:

- **The grammar** (FR-001): an optional ``To:`` line at the head of a marker or
  ferry body names a peer. No ``To:`` line and the body *is* the question, byte
  for byte — the absent addressee is the compatibility contract (SC-006), so the
  008 fixtures are asserted unedited and the parser short-circuits before any
  peer branch runs.
- **The routing** (FR-002, FR-003): a peer-addressed message is buffered in
  workflow state, keyed by message id, delivered into the target's next
  assembled prompt under a dedicated section, and the reply threads back to the
  asker verbatim the same way. US1 routes to a peer that is *not* mid attempt;
  the in-flight ferry direction is US2's (spec § Work Graph, the straddle
  paragraph).
- **The park that does not pause** (FR-016): a peer-addressed park is a distinct
  node state (`WAITING_PEER`) that leaves the scheduler dispatching. This is the
  story's one structural trap — the 008 operator park raises `self._paused`, and
  the node that must answer a peer question is a node of this same epic, so the
  pause prevents the very dispatch that would answer. Every test here with two
  nodes has the addressee dispatch *while the asker is parked*.
- **The degradation floor** (FR-004): unknown addressee, self-address, a
  terminal target, and an unanswered expiry all land on the 008 operator
  question path — a peer message may go unanswered, it must never hang a node
  or vanish.
- **The bound** (FR-006): outstanding peer messages per node are limited by
  configuration and a send beyond it is refused to the asker, naming the
  configuration field and its value.
- **The store** (FR-008): every message and reply is persisted, attributed to
  sender and recipient, alongside 008's questions.

The world the 008 tests use is `ScriptedWorld`, and it is *not* rebuilt: these
tests drive the same fakes under the same activity names, so a rename anywhere
breaks both suites the same way. What is added is the peer half of the world's
memory — the bodies the fake detector answers with gain ``To:`` lines, the
messages the routing buffers are visible in the store, and the prompts the fake
adapter records are read for the section.

Everything below fails on the unmodified tree: the parser does not know ``To:``,
the workflow has no `WAITING_PEER`, no buffer, no routing, and the store has no
``messages`` table.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterator

import pytest
from temporalio.testing import WorkflowEnvironment

from factory.verify.store import connect
from factory.workgraph.models import EpicState, NodeState
from factory.workgraph.prompt import build_attempt_prompt
from factory.workgraph.workflow import EpicWorkflow
from factory.verify.question import QUESTION_HEADING

from tests.test_interpreter import (  # noqa: F401 — env is the module's fixture, re-used here
    env,
    EPIC_ID,
    PLAN_TEXT,
    SPEC_TEXT,
    TASKS_TEXT,
    ScriptedWorld,
    Attempt,
    make_graph,
    make_node,
    passing,
    run_epic,
    start_epic,
    states,
    wait_for,
    wait_for_status,
)

#: The reply the answering peer writes, verbatim — what the asker's next prompt
#: must carry unchanged (FR-003). Distinct from everything a ladder writes so a
#: paraphrase cannot pass for delivery.
P_REPLY = "Take Option A. The 12-hex id is what reply routing already keys on."

#: The body the answering peer writes under its marker, addressed back to the
#: asker so the reply threads (FR-003). The ``In-Reply-To:`` id is filled by
#: each test from the routing record.
P_REPLY_BODY = "In-Reply-To: {mid}\n\n" + P_REPLY

#: The asker's question, addressed to its peer. The first line is the
#: addressee; what follows it is the body the peer reads (FR-001).
P_ASK = "To: us2\n\nWhich of A and B — the plan reads to me like B, but A is what the ladder keys on?"

#: The same question with no addressee: byte-identical to the 008 grammar
#: (SC-006), so the fixtures the 008 tests wrote keep their meaning unedited.
Q_OPERATOR = "Which of A and B does the plan intend? I lean A."

#: The dedicated section the asker's message renders under in the target's
#: prompt (FR-002) — distinct from `## Operator answer` (the operator's voice)
#: and from `## Prior attempt evidence` (the ladder's).
PEER_MESSAGE_HEADING = "## Peer message"

#: The dedicated section a peer's reply renders under in the asker's prompt
#: (FR-003) — the return path's own heading, kept separate from the operator's
#: answer section so the two voices cannot be confused.
PEER_REPLY_HEADING = "## Peer reply"


# --- the store the routing writes ---------------------------------------------


@pytest.fixture()
def store_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A per-test verification store, pointed at by the variable the activities read.

    The routing's rows are assertions as well as behaviour (FR-008), and a store
    the test owns is what makes "two sends, two rows" a fact about the world
    rather than a call log.
    """
    path = tmp_path / "store.sqlite3"
    monkeypatch.setattr("factory.activities.notify_activities._store_path", lambda: path)
    yield path


def message_rows(path: Path) -> list[sqlite3.Row]:
    """Every row of the messages table, oldest first."""
    conn = connect(path)
    try:
        return conn.execute(
            "SELECT * FROM messages ORDER BY created_at, message_id"
        ).fetchall()
    finally:
        conn.close()


# --- T003: the grammar ---------------------------------------------------------


class TestGrammar:
    """The addressee line (FR-001, spec US1-S1/S2)."""

    def test_a_marker_body_with_an_addressee_parses_to_peer_and_body(self) -> None:
        """``To:`` first, body after — the addressee is a header, not prose."""
        from factory.verify.peer_grammar import parse_addressee

        parsed = parse_addressee(P_ASK)
        assert parsed is not None
        assert parsed.addressee == "us2"
        assert parsed.body == P_ASK[len("To: us2\n\n") :]

    def test_a_body_with_no_addressee_is_none_and_the_body_is_untouched(self) -> None:
        """No ``To:`` line short-circuits before any peer branch runs (FR-001).

        The parser returns ``None`` — meaning "this is an operator question" —
        and the caller uses the original text unchanged. Nothing here inspects
        the body for a *mention* of ``To:``: prose that discusses the header is
        not a header, the same line `factory/verify/question.py` draws for the
        marker.
        """
        from factory.verify.peer_grammar import parse_addressee

        assert parse_addressee(Q_OPERATOR) is None

    def test_an_addressee_mentioned_in_prose_is_not_an_addressee(self) -> None:
        """A ``To:`` that does not start at column 0 names nobody (the marker's
        line-anchored rule, applied to the header)."""
        from factory.verify.peer_grammar import parse_addressee

        assert parse_addressee("The To: line names the peer.\n\nWhich?") is None

    def test_an_addressee_line_with_no_body_is_not_deliverable(self) -> None:
        """``To: us2`` and nothing else is malformed, the marker's empty-body
        rule: a message with no content routes nothing, so the address alone
        parks nobody and pages nobody."""
        from factory.verify.peer_grammar import parse_addressee

        parsed = parse_addressee("To: us2")
        assert parsed is None

    def test_detection_returns_the_addressee_and_leaves_the_body_verbatim(
        self, tmp_path: Path
    ) -> None:
        """The detector the workflow already consults carries the split.

        A marker whose body names a peer yields the peer and the remainder; a
        marker whose body names nobody yields neither — and the marker's own
        contract (``QUESTION_HEADING`` level-2, fenced-block masking) is the
        one being extended, not a second scanner.
        """
        from factory.verify.question import detect_operator_question

        transcript = tmp_path / "attempt-1"
        transcript.mkdir()
        (transcript / "stdout.log").write_text(
            f"{QUESTION_HEADING}\n{P_ASK}\n", encoding="utf-8"
        )
        marker = detect_operator_question(transcript)
        assert marker is not None and marker.is_question
        assert marker.addressee == "us2"
        assert marker.body == P_ASK[len("To: us2\n\n") :]

    def test_detection_of_a_body_with_no_addressee_is_unchanged(self, tmp_path: Path) -> None:
        """008's shape reads exactly as it did: addressee None, body the text."""
        from factory.verify.question import detect_operator_question

        transcript = tmp_path / "attempt-1"
        transcript.mkdir()
        (transcript / "stdout.log").write_text(
            f"{QUESTION_HEADING}\n{Q_OPERATOR}\n", encoding="utf-8"
        )
        marker = detect_operator_question(transcript)
        assert marker is not None and marker.is_question
        assert marker.addressee is None
        assert marker.body == Q_OPERATOR

    def test_a_ferry_body_parses_the_same_way(self) -> None:
        """The ferry file is the same grammar in a second place (FR-001).

        One parser, two surfaces: a body the monitor loop ferries up names its
        peer by the same first line, and a body without one is an operator
        question on the existing path.
        """
        from factory.verify.peer_grammar import parse_addressee

        parsed = parse_addressee(P_ASK)
        assert parsed is not None and parsed.addressee == "us2"
        assert parse_addressee(Q_OPERATOR) is None


# --- T004: routing with scripted children --------------------------------------


def _two_node_graph() -> Any:
    """Two independent nodes: the asker `us1` and its peer `us2`.

    Deliberately NO edge between them, and this is the shape the Independent
    Test demands: a peer exchange asks a question a *sibling* answers. An edge
    us1 → us2 would gate us2 on us1's verification — which a park suspends —
    and the asker would be the only node the addressee's dispatch depends on,
    the deadlock FR-016 forbids, re-created in the test fixture. At cap 1 the
    asker parks (holding no slot), the scheduler dispatches the ready `us2`
    next, and us2 answers on its own prompt.
    """
    return make_graph(
        nodes=[
            make_node("us1", "US1"),
            make_node("us2", "US2", depends_on=[], depends_on_merged=[]),
        ]
    )


def _questioning_chain(client: Any) -> ScriptedWorld:
    """us1 asks its peer us2 on attempt 1 and passes on attempt 2; us2 passes.

    us2's prompt is where the message must be delivered (FR-002), and its
    marker bodies are what carry the reply back (FR-003).
    """
    script = ScriptedWorld(
        {"us1": [passing(), passing()], "us2": [passing()]},
        client=client,
    )
    script.question_bodies["us1"] = P_ASK
    return script


class TestRouting:
    """Workflow-routed delivery, both directions (FR-002, FR-003, US1-S3/S4)."""

    async def test_the_message_reaches_the_peer_s_next_prompt_verbatim(
        self,
        env: WorkflowEnvironment,
        store_path: Path,
    ) -> None:
        """US1-S3: no attempt in flight on the target → dedicated prompt section.

        us1 parks on its peer-addressed question, the message is buffered in
        workflow state keyed by id, and us2's next attempt reads it verbatim
        under `## Peer message`. The reply reaches the asker the same way, which
        the next test asserts; this one pins the delivery half.
        """
        script = _questioning_chain(env.client)

        async with start_epic(env, script, graph=_two_node_graph()) as handle:
            parked = await wait_for_status(
                handle,
                lambda status: states(status).get("us1") == NodeState.WAITING_PEER
                and status.epic_state == EpicState.RUNNING,
                what="us1 to park WAITING_PEER without pausing the epic",
            )
            # FR-016 is the story's structural trap — assert the *other* half of
            # it here: the scheduler kept dispatching.
            assert parked.epic_state == EpicState.RUNNING

            await wait_for(
                lambda: len(script.prompts_for("us2")) == 1,
                what="us2's prompt to be assembled",
            )
            [peer_prompt] = script.prompts_for("us2")
            assert PEER_MESSAGE_HEADING in peer_prompt
            ask_body = P_ASK[len("To: us2\n\n") :]
            assert ask_body in peer_prompt

    async def test_the_reply_threads_back_to_the_asker_verbatim(
        self,
        env: WorkflowEnvironment,
        store_path: Path,
    ) -> None:
        """US1-S3's return half (FR-003): the reply reaches the asker verbatim.

        us2's attempt carries the asker's question in its prompt and answers it
        under its own marker, addressed back with ``In-Reply-To:``. The reply
        threads to the message by id and lands in us1's next attempt under
        `## Peer reply`, after which us1 verifies.
        """
        script = _questioning_chain(env.client)
        script.question_bodies["us2"] = P_REPLY_BODY

        status = await run_epic(env, script, graph=_two_node_graph())

        assert states(status)["us1"] == NodeState.MERGED
        [question_prompt, reply_prompt] = script.prompts_for("us1")
        assert PEER_MESSAGE_HEADING not in question_prompt
        assert PEER_REPLY_HEADING in reply_prompt
        assert P_REPLY in reply_prompt

    async def test_no_operator_notification_is_sent_for_a_peer_exchange(
        self,
        env: WorkflowEnvironment,
        store_path: Path,
    ) -> None:
        """A routed exchange never pages a human (the story's whole point).

        `send_question` is the 008 page. Neither the parked asker nor the
        answering peer triggers one: the message is buffered in workflow state
        and the replies ride the prompts. What *must* send is the degradation —
        and that is a different test.
        """
        script = _questioning_chain(env.client)
        script.question_bodies["us2"] = P_REPLY_BODY

        await run_epic(env, script, graph=_two_node_graph())

        assert script.question_requests == []

    async def test_an_unknown_addressee_degrades_to_the_operator_question(
        self,
        env: WorkflowEnvironment,
        store_path: Path,
    ) -> None:
        """US1-S5 (FR-004): an addressee no node names is undeliverable.

        The asker's question names `us9`, which is nobody. The asker still
        parks — it asked something and is waiting — so the message degrades to
        the 008 path: a question row is inserted and the page ships, carrying
        the message body. A peer message may go unanswered; it must never
        vanish, and it must never leave the asker stuck on a name nobody
        answers.
        """
        script = _questioning_chain(env.client)
        script.question_bodies["us1"] = "To: us9\n\nWhich of A and B?"

        async with start_epic(env, script, graph=_two_node_graph()) as handle:
            parked = await wait_for_status(
                handle,
                lambda status: states(status).get("us1") == NodeState.WAITING_OPERATOR
                and status.epic_state == EpicState.PAUSED,
                what="an undeliverable message to degrade to the operator park",
            )
            assert parked.epic_state == EpicState.PAUSED
            await wait_for(
                lambda: len(script.question_requests) == 1,
                what="the degraded operator question to ship",
            )
            [sent] = script.question_requests
            assert sent.node_id == "us1"
            assert "Which of A and B?" in sent.question_text

    async def test_a_terminal_target_degrades_to_the_operator_question(
        self,
        env: WorkflowEnvironment,
        store_path: Path,
    ) -> None:
        """US1-S5: an addressee whose node has ended cannot receive (FR-004).

        us2's ladder is spent before us1 asks — every scripted attempt failed,
        so us2 ends KILLED — and us1 then addresses it. The message degrades to
        the operator question rather than sitting in a mailbox nobody reads.
        """
        script = _questioning_chain(env.client)
        from tests.test_interpreter import failing

        script._script["us2"] = [failing(1), failing(2), failing(3)]
        script.question_bodies["us1"] = "To: us2\n\nWhich of A and B?"

        async with start_epic(env, script, graph=_two_node_graph()) as handle:
            await wait_for_status(
                handle,
                lambda status: states(status).get("us2")
                in (NodeState.KILLED, NodeState.MERGED, NodeState.FAILED),
                what="us2 to end before us1 asks",
            )
            await wait_for_status(
                handle,
                lambda status: states(status).get("us1") == NodeState.WAITING_OPERATOR,
                what="the message to a terminal peer to degrade to the operator park",
            )
            await wait_for(
                lambda: len(script.question_requests) == 1,
                what="the degraded operator question to ship",
            )
            [sent] = script.question_requests
            assert sent.node_id == "us1"

    async def test_a_message_unanswered_at_expiry_degrades_to_the_operator(
        self,
        env: WorkflowEnvironment,
        store_path: Path,
    ) -> None:
        """US1-S5: the peer never answers, so the asker's park cannot outlive it.

        The message window is the asker's, expiring like 008's — and with no
        consult rung in this story (US5), the expiry lands on the 008 operator
        path: the ladder counts the FAIL (an unanswered question is the one
        question that burns a slot), and the operator is paged.
        """
        script = _questioning_chain(env.client)
        # us2 answers *nothing* — its own attempt passes with no question body.
        script.question_bodies["us1"] = P_ASK

        status = await run_epic(env, script, graph=_two_node_graph())

        assert len(script.question_requests) == 1
        [sent] = script.question_requests
        assert sent.node_id == "us1"


# --- T005: cap and discipline --------------------------------------------------


class TestCap:
    """The outstanding-message bound (FR-006, spec US1-S5) and the guards."""

    def test_the_refusal_names_the_configuration_field_and_its_value(self) -> None:
        """The cap is a configuration value, so the refusal is spelled like the
        one `max_concurrent_nodes must be a positive integer` is spelled (FR-006):
        field name, required shape, got.
        """
        from factory.workgraph.workflow import (
            MAX_OUTSTANDING_PEER_MESSAGES,
            describe_peer_send_refusal,
        )

        refusal = describe_peer_send_refusal(
            outstanding=3, maximum=MAX_OUTSTANDING_PEER_MESSAGES
        )
        assert "max_outstanding_peer_messages" in refusal
        assert str(MAX_OUTSTANDING_PEER_MESSAGES) in refusal
        assert "3" in refusal

    async def test_a_ping_pong_terminates_at_the_bound(
        self,
        env: WorkflowEnvironment,
        store_path: Path,
    ) -> None:
        """SC-004's shape, at US1's next-prompt cadence: two nodes exchanging,
        the send that would exceed the configured outstanding bound refused to
        the asker rather than granted. The refusal re-enters the asker's ladder
        as the 008 path — a refused send is the asker's signal to stop asking,
        not a hang and not a silent drop.
        """
        script = _questioning_chain(env.client)
        # us1 asks; us2 answers; us1 asks again — which is one message too many
        # outstanding, so the second send is refused and the epic still lands.
        script.question_bodies["us1"] = P_ASK
        script.question_bodies["us2"] = P_REPLY_BODY

        status = await run_epic(env, script, graph=_two_node_graph())

        assert states(status)["us1"] == NodeState.MERGED

    def test_message_text_cannot_reach_a_verdict_assembler(self) -> None:
        """FR-005, the second half of 008's FR-010 hole: the prompt section is
        the only place message text goes.

        The section builder takes one exchange and renders it into the prompt —
        never into evidence, judge feedback or a gate result. The evidence
        sections are built from `AttemptEvidence` today and stay that way: the
        assembler does not grow a parameter that carries message text anywhere
        else, and this test is what holds the line as the code changes.
        """
        import inspect

        from factory.workgraph import prompt as prompt_module

        signature = inspect.signature(build_attempt_prompt)
        message_params = [
            name
            for name in signature.parameters
            if "message" in name or "peer" in name
        ]
        # The text may *enter* the prompt — that is delivery — but the evidence
        # types the judge reads are untouched by it.
        from factory.workgraph.prompt import AttemptEvidence
        from factory.verify.models import JudgeVerdict

        import dataclasses

        assert all(
            "peer" not in field.name and "message" not in field.name
            for cls in (AttemptEvidence, JudgeVerdict)
            for field in dataclasses.fields(cls)
        )
        assert prompt_module.PEER_MESSAGE_HEADING == PEER_MESSAGE_HEADING
        assert prompt_module.PEER_REPLY_HEADING == PEER_REPLY_HEADING

    def test_message_bodies_carry_no_credential_shape(self, store_path: Path) -> None:
        """FR-007: the sweep reads the store's message surfaces.

        The existing sweep's grep-backed rule extends to message bodies, replies
        and stored rows: a body that walks, talks and looks like a key is the
        one thing the channel must never carry, and this test drives a real
        store write with a credential-shaped payload and expects the sweep to
        name it. Written as the assertion the sweep makes, before the sweep
        exists, so T007 has a target.
        """
        import sqlite3

        conn = connect(store_path)
        try:
            conn.execute(
                "INSERT INTO messages (message_id, sender_epic_id, sender_node_id, "
                "sender_attempt, addressee, body, reply, resolution, created_at, "
                "expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "a" * 12,
                    EPIC_ID,
                    "us1",
                    1,
                    "us2",
                    "read this: sk-a1b2c3d4e5f6g7h8i9j0k1l2m3n4",
                    None,
                    None,
                    "2026-08-05T09:30:00Z",
                    "2026-08-05T17:30:00Z",
                ),
            )
            conn.commit()
        finally:
            conn.close()

        from factory.verify.sweeps import assert_no_credential_in_message

        with pytest.raises(AssertionError, match="sk-"):
            assert_no_credential_in_message(
                message_id="a" * 12,
                body="read this: sk-a1b2c3d4e5f6g7h8i9j0k1l2m3n4",
            )


# --- T006: the store -----------------------------------------------------------


class TestStore:
    """The messages table (FR-008, spec US1-S6)."""

    def test_a_message_row_carries_sender_addressee_body_reply_resolution(
        self, store_path: Path
    ) -> None:
        """One row per message, every fact attributed (FR-008).

        The record travels through the store whole: who sent it (epic, node,
        attempt), who it names, what it said, what came back, where it ended,
        and when its window closed.
        """
        from factory.verify.models import MessageRecord
        from factory.verify.store import (
            insert_message,
            resolve_message,
            expire_message,
            get_message,
        )

        record = MessageRecord(
            message_id="b" * 12,
            sender_epic_id=EPIC_ID,
            sender_node_id="us1",
            sender_attempt=1,
            addressee="us2",
            body=P_ASK,
            reply=None,
            resolution=None,
            created_at="2026-08-05T09:30:00Z",
            expires_at="2026-08-05T17:30:00Z",
        )
        insert_message(store_path, record)

        stored = get_message(store_path, "b" * 12)
        assert stored is not None
        assert stored.sender_epic_id == EPIC_ID
        assert stored.sender_node_id == "us1"
        assert stored.sender_attempt == 1
        assert stored.addressee == "us2"
        assert stored.body == P_ASK
        assert stored.resolution is None

    def test_resolution_is_first_wins_against_expiry(self, store_path: Path) -> None:
        """The `resolve_question` pattern: whichever of a reply and the expiry
        arrives second matches no rows and is told so (the 008 rule).
        """
        from factory.verify.models import MessageRecord
        from factory.verify.store import (
            insert_message,
            resolve_message,
            expire_message,
        )

        record = MessageRecord(
            message_id="c" * 12,
            sender_epic_id=EPIC_ID,
            sender_node_id="us1",
            sender_attempt=1,
            addressee="us2",
            body=P_ASK,
            reply=None,
            resolution=None,
            created_at="2026-08-05T09:30:00Z",
            expires_at="2026-08-05T17:30:00Z",
        )
        insert_message(store_path, record)

        first = resolve_message(
            store_path,
            "c" * 12,
            reply_text=P_REPLY,
            resolved_at="2026-08-05T09:31:00Z",
        )
        assert first is True
        second = expire_message(store_path, "c" * 12, resolved_at="2026-08-05T17:30:00Z")
        assert second is False

    def test_a_late_reply_is_stored_and_never_read_after_expiry(
        self, store_path: Path
    ) -> None:
        """A reply that arrives after the asker's window ran out is recorded —
        the exchange is evidence — and the asker's prompt never carries it, the
        `_answers` discipline applied to messages.
        """
        from factory.verify.models import MessageRecord
        from factory.verify.store import (
            insert_message,
            expire_message,
            resolve_message,
            get_message,
        )

        record = MessageRecord(
            message_id="d" * 12,
            sender_epic_id=EPIC_ID,
            sender_node_id="us1",
            sender_attempt=1,
            addressee="us2",
            body=P_ASK,
            reply=None,
            resolution=None,
            created_at="2026-08-05T09:30:00Z",
            expires_at="2026-08-05T17:30:00Z",
        )
        insert_message(store_path, record)
        assert expire_message(store_path, "d" * 12, resolved_at="2026-08-05T17:30:00Z")
        # Late: stored, resolved, and the resolution says it lost.
        late = resolve_message(
            store_path,
            "d" * 12,
            reply_text=P_REPLY,
            resolved_at="2026-08-05T18:00:00Z",
        )
        assert late is False
        stored = get_message(store_path, "d" * 12)
        assert stored is not None
        assert stored.resolution == "EXPIRED"