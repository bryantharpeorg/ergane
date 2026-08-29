"""US1-S5 — the bound, the hole's fence, and the accounting an exchange keeps.

017-US1. Three disciplines the peer channel must not lose while it gains a
second addressee:

- **The bound (FR-006).** The number of outstanding peer messages per node is
  bounded by configuration, and a send beyond it is refused to the asker,
  naming the field and its value — the way `max_concurrent_nodes must be a
  positive integer` is named. A ping-pong exchange that never converges must
  terminate at the bound with both nodes proceeding, not escalate into an
  unbounded conversation billed to the epic (SC-004).
- **The hole stays narrow (FR-005).** Message and reply text enters prompts
  and parks nodes; it must be unreadable by gates and judge. The 008 FR-010
  guard is extended, not forked: a peer attempt with a substantive diff gets
  no PASS from the exchange, and the gates and judge are never consulted for
  a message-carrying attempt's park.
- **The ledger is unchanged (FR-008's sibling discipline).** A peer exchange
  costs tokens, which the usage read already meters, and changes no
  accounting: the asker's ladder budget is what it was before the question,
  and teardown rows carry real usage rather than invented zeros.

The credential sweep (FR-007) is asserted here too, over the new surfaces
this story adds: the message row and the message body the activity hands on.

Written before the bound exists (T005 precedes T007): until it lands, the
bound tests fail — nothing refuses an Nth message today — and the discipline
tests fail with them, because the park they guard against is the one today's
code raises.
"""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path
from typing import Any

import pytest
from temporalio.testing import ActivityEnvironment
from temporalio.testing import WorkflowEnvironment

from factory.activities.notify_activities import (
    ERGANE_VERIFICATION_DB_PATH_ENV,
    VERIFICATION_DB_PATH_ENV,
)
from factory.verify import store
from factory.workgraph.models import EpicState, NodeState, WorkGraph, WorkNode

from tests.test_interpreter import (
    ANSWER_TEXT,
    EPIC_ID,
    SNAPSHOT,
    ScriptedWorld,
    Termination,
    env,  # noqa: F401  — pytest fixture, re-exported for this module
    failing,
    make_node,
    passing,
    run_epic,
    start_epic,
    states,
    wait_for,
    wait_for_status,
)
from tests.test_peer_channel_routing import (
    DEFAULT_PEER_MESSAGE_LIMIT,
    PEER_QUESTION,
    PEER_REPLY,
    PEER_SECTION_HEADING,
    TO_US2,
    asking_peer,
    scripted_reply,
)

#: A token-shaped value that must never reach a message body, a row, or a
#: mirror. Deliberately distinctive, the way the 008 suite's is, so every
#: "did not leak" assertion is a substring search over what the factory wrote.
A_CREDENTIAL = "sk-live-factory-token-do-not-ship"

#: The bound's name, as the refusal must spell it and as the epic's dispatch
#: carries it. Worded the way `max_concurrent_nodes` is worded — the field's
#: own name, not a synonym (FR-006).
PEER_MESSAGE_FIELD = "max_outstanding_peer_messages"


# --- the bound (FR-006) -------------------------------------------------------


async def test_a_send_beyond_the_bound_is_refused_naming_the_field(
    env: WorkflowEnvironment,
) -> None:
    """FR-006 / SC-004: the ping-pong terminates at the configured bound.

    A node that has the bound's worth of messages outstanding may not open
    another: the refusal is immediate, names the configuration field and its
    value, and leaves both nodes proceeding. The refusal is the asker's to
    read, so it arrives where the asker is — in the reply path the exchange
    already has, not as a new channel.
    """
    script = asking_peer(env.client)
    scripted_reply(script)
    # The asker asks, gets its reply, then asks again — past the bound, with
    # the first exchange still outstanding against the addressee's cap. The
    # scripted world's default bound is 2, so the third send is the refusal.
    script.question_bodies["us1"] = f"{TO_US2}\n{PEER_QUESTION}"
    script.peer_send_limit = 2

    status = await run_epic(env, script)

    # The refusal named the field and its value (FR-006).
    refusals = [
        text
        for text in script.peer_refusals
    ]
    assert refusals, "a send beyond the bound must be refused, not silently dropped"
    assert any(PEER_MESSAGE_FIELD in text for text in refusals), refusals
    assert any("2" in text for text in refusals), refusals
    # Both nodes proceeded — the bound terminated the conversation, not the epic.
    assert states(status)["us1"] in (NodeState.MERGED, NodeState.PASSED)
    assert states(status)["us2"] in (NodeState.MERGED, NodeState.PASSED)


async def test_the_bound_is_per_node_not_per_epic(
    env: WorkflowEnvironment,
) -> None:
    """FR-006's scope: the bound is per node. Two askers with one outstanding
    message each are two messages against two bounds, not two against one.

    A per-epic bound would let one chatty node starve a sibling of the channel
    for a reason that has nothing to do with the sibling's behaviour, and the
    spec's edge case (a ping-pong that never converges) is about one node's
    conversation, not the epic's.
    """
    script = ScriptedWorld(
        {
            "us1": [passing(), passing()],
            "us2": [passing(), passing()],
            "us3": [passing()],
        },
        client=env.client,
    )
    # Both askers address the third node, one message each — within one bound
    # of 1 per node, which a per-epic bound would refuse.
    script.question_bodies["us1"] = f"To: us3\n{PEER_QUESTION}"
    script.question_bodies["us2"] = f"To: us3\n{PEER_QUESTION}"
    script.peer_send_limit = 1
    script.peer_reply = PEER_REPLY

    status = await run_epic(env, script)

    assert script.peer_refusals == [], (
        "one message per asker is within a per-node bound of 1; a refusal here "
        "means the bound was counted per epic"
    )
    assert states(status)["us1"] == NodeState.MERGED
    assert states(status)["us2"] == NodeState.MERGED


# --- the hole stays narrow (FR-005) ------------------------------------------


async def test_a_peer_attempt_with_a_substantive_diff_earns_no_pass(
    env: WorkflowEnvironment,
) -> None:
    """FR-005, extending 008's FR-010 guard: message text reaches no verdict.

    The hardest case, carried over from the 008 guard on purpose: an attempt
    with a peer-addressed marker AND a substantive diff — gates would pass,
    output has a diff — must not get a PASS from the exchange. The message
    parks, the gates are never read, and the node ends parked, never PASSED.
    A peer message that could steer toward PASS would be an agent grading
    itself through a confederate, which is the FR-012 hole with a second
    signature.
    """
    script = asking_peer(env.client)

    async with start_epic(env, script) as handle:
        parked = await wait_for_status(
            handle,
            lambda status: (
                states(status).get("us1") == NodeState.WAITING_PEER
                if hasattr(NodeState, "WAITING_PEER")
                else False
            ),
            what="us1 to park on the peer message, not pass",
        )

    # The node parked, it did not pass — and the landing a PASS opens is
    # never entered: no PR, nothing enqueued.
    assert states(parked)["us1"] == NodeState.WAITING_PEER
    assert script.landing_requests == []
    assert script.enqueue_requests == []
    # The gates that would have passed were never read (FR-005).
    assert "run_gates" not in script.sequence("us1")


async def test_the_judge_is_never_invoked_for_a_peer_message(
    env: WorkflowEnvironment,
) -> None:
    """FR-005's second half: for a peer-parked attempt there is nothing to
    grade, so the judge is never consulted.

    The sequence for the asker ends at detection — it never reaches
    `run_gates`, `check_output`, `read_worktree_diff`, or `run_judge`. A
    workflow that ran any of those for a message-carrying attempt would be
    letting message content influence the verdict path.
    """
    script = asking_peer(env.client)

    async with start_epic(env, script) as handle:
        await wait_for_status(
            handle,
            lambda status: (
                states(status).get("us1") == NodeState.WAITING_PEER
                if hasattr(NodeState, "WAITING_PEER")
                else False
            ),
            what="us1 to park on the peer message",
        )

    seq = script.sequence("us1")
    assert "run_gates" not in seq
    assert "check_output" not in seq
    assert "read_worktree_diff" not in seq
    assert "run_judge" not in seq
    assert script.judge_requests == []
    assert script.gate_requests == []


# --- the ledger is unchanged by an exchange ----------------------------------


async def test_a_peer_exchange_changes_no_ladder_budget(
    env: WorkflowEnvironment,
) -> None:
    """The no-burn rule, carried to the peer channel: an answered peer
    question consumes no ladder slot (008 FR-001's discipline).

    The asker asks on attempt 1, the peer replies, and the node that could
    take N attempts before the question can still take N after — the
    QUESTION attempt broke the loop before the history append, so the ladder
    counts the attempts that graded, not the one that asked.
    """
    # Ask on attempt 1, then fail the next three ordinary attempts. A node
    # that burned a slot on the question would exhaust at three; a node that
    # did not still reaches the debugger cycle — the rung after the ordinary
    # budget — which is the proof the question cost nothing.
    script = ScriptedWorld(
        {
            "us1": [passing(), failing(2), failing(3), failing(4), failing(5)],
            "us2": [passing()],
            "us3": [passing()],
        },
        client=env.client,
        press="KILL",
    )
    script.question_bodies["us1"] = f"{TO_US2}\n{PEER_QUESTION}"
    scripted_reply(script)

    status = await run_epic(env, script)

    us1_attempts = [c.attempt for c in script.attempts if c.node_id == "us1"]
    # Four attempts after the question: the default budget plus the debugger
    # cycle. A slot burned on the question would have stopped it at three.
    assert us1_attempts == [1, 2, 3, 4, 5]
    personas = [r.persona for r in script.key_requests if r.node_id == "us1"]
    assert personas[-1] == "debugger", (
        "the debugger rung is reached only if the peer question burned no slot"
    )
    assert states(status)["us1"] == NodeState.KILLED


async def test_a_peer_attempt_still_writes_its_real_usage_to_teardown(
    env: WorkflowEnvironment,
) -> None:
    """A peer-parked attempt closes its bracket the way any terminal does:
    teardown carries the QUESTION termination and the measured snapshot, not
    an exemption.

    Message exchanges change no accounting (plan: "ledger discipline"). The
    park is a termination class like any other, and the row that records it
    carries real usage rather than a silent NULL.
    """
    script = asking_peer(env.client, adapter_snapshot=SNAPSHOT)

    async with start_epic(env, script) as handle:
        await wait_for_status(
            handle,
            lambda status: (
                states(status).get("us1") == NodeState.WAITING_PEER
                if hasattr(NodeState, "WAITING_PEER")
                else False
            ),
            what="us1 to park on the peer message",
        )

    teardown = script.teardown_for("us1", 1)
    assert teardown.termination == Termination.QUESTION
    # Real usage travels — the same path a normal completion takes.
    assert teardown.last_snapshot == SNAPSHOT


# --- credentials (FR-007), over the new surfaces ------------------------------


def test_the_message_record_has_no_place_to_put_a_credential() -> None:
    """FR-007: a field for a token would put it in the workflow's history
    forever, so the record the store writes has no such field.

    The sweep the 008 suite holds over `SendQuestionInput`, held over the
    message record this story adds — same discipline, new surface.
    """
    names = {field.name for field in fields(store.MessageRecord)}

    assert not [name for name in names if "token" in name or "chat" in name]


async def test_a_credential_in_a_message_body_never_reaches_a_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-007: an agent that pastes a credential into a message body must not
    be able to publish it into the store, where every row is readable by any
    operator query.

    The body is what the agent wrote and it travels verbatim to the peer (that
    is FR-002) — so the guard is not scrubbing the body, it is proving the
    *stored* row a peer exchange writes carries no credential the *factory*
    added, and that the surfaces the factory builds (the row, the refusal, the
    prompt section framing) are clean even when the body is not.
    """
    db_path = tmp_path / ".factory" / "verification.db"
    monkeypatch.setenv(ERGANE_VERIFICATION_DB_PATH_ENV, str(db_path))
    monkeypatch.delenv(VERIFICATION_DB_PATH_ENV, raising=False)

    conn = store.connect(db_path)
    try:
        store.insert_message(
            conn,
            store.MessageRecord(
                message_id="0123456789ab",
                epic_id=EPIC_ID,
                sender_node="us1",
                sender_attempt=1,
                sender_persona="implementer",
                addressee="us2",
                body=f"My key is {A_CREDENTIAL} — is that right?",
                sent_at="2026-08-29T00:00:00Z",
                expires_at="2026-08-29T08:00:00Z",
            ),
        )
        # The framing the factory builds around a delivered message is the
        # surface it owns: the row's routing columns and the section heading a
        # prompt renders. Neither may carry a credential even when the body
        # the agent wrote does.
        row = store.get_message(conn, "0123456789ab")
    finally:
        conn.close()

    assert row is not None
    assert row.addressee == "us2"
    assert A_CREDENTIAL not in row.addressee
    assert A_CREDENTIAL not in row.message_id
    # The section framing carries no credential either — it names the sender.
    from factory.workgraph.prompt import peer_message_section

    section = peer_message_section(
        sender_node="us1", sender_persona="implementer", body=row.body
    )
    assert A_CREDENTIAL not in section.replace(row.body, "")