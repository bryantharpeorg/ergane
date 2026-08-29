"""US1-S3/S4/S6 — peer routing: the exchange, the round trip, and the one trap.

017-US1. 008 built a channel with one addressee; this story adds the address
and the routing behind it. A message that names a same-epic peer is buffered in
workflow state, keyed by message id, and delivered to that peer — into the
peer's next assembled prompt when it is not running (US1's half; the live
ferry is US2's) — and the peer's reply threads back to the asker by the same
id, verbatim (FR-002, FR-003). What may never happen is the one structural
trap this story was held for eight days to name: **a peer-addressed park must
not raise the scheduler's operator-pause flag** (FR-016), because the node that
must answer is a node of this same epic, and the pause is exactly what stops it
being dispatched.

Every test here drives the epic through the scripted world
(`tests/test_interpreter.py`), so every assertion is about the world — the
addressee's assembled prompt, the epic's state, the store's rows — and not
about a call log of our own code.

The test the spec demands, and the one worth reading twice:

- **The addressee dispatches *while the asker is parked*.** A suite that only
  exercises the ferry path (both attempts alive) cannot observe the pause
  deadlock at all — the deadlock is a property of the parked asker and the
  never-dispatched answerer, and both-alive tests never enter that state.
  `test_a_parked_asker_does_not_pause_the_epic` scripts the asker to park on a
  peer question and asserts the epic keeps RUNNING, the addressee dispatches,
  answers, and the asker un-parks on the reply — not on the expiry.
- **No operator message is sent for a peer exchange.** `send_question` is the
  one paging surface; a peer exchange must not reach it (SC-001's claim).
- **Degradation is the floor, never a hang.** Unknown addressee, terminal
  target, and an unanswered expiry all degrade to the 008 operator question
  carrying the message body (FR-004) — the message may go unanswered, it may
  never hang a node or vanish.

Written before the routing exists (T004 precedes T007): until it lands, every
test here fails — a peer-addressed marker parks the node WAITING_OPERATOR and
pauses the epic today, because the addressee is not a concept the workflow has.
"""

from __future__ import annotations

from typing import Any

from temporalio.testing import WorkflowEnvironment

from factory.verify.store import ANSWERED
from factory.workgraph.models import EpicState, NodeState, WorkNode

from tests.test_interpreter import (
    ANSWER_TEXT,
    EPIC_ID,
    ScriptedWorld,
    env,  # noqa: F401  — pytest fixture, re-exported for this module
    make_node,
    passing,
    run_epic,
    start_epic,
    states,
    wait_for,
    wait_for_status,
)

#: The address line, as the grammar parses it: `To:` plus a node id.
TO_US2 = "To: us2"

#: The question `us1` asks `us2`, body only — the addressee is routing data and
#: travels on the message record, not in the body the peer reads (FR-002).
PEER_QUESTION = (
    "You wrote the plan this story implements. The reuse inventory cites the\n"
    "question seam at `factory/escalation/question.py` — does the addressee\n"
    "line belong in the marker body or beside it, and which half owns the\n"
    "peel?\n"
)

#: The reply `us2` sends back, verbatim — what the asker's next prompt must
#: carry unchanged under the peer-message section (FR-003).
PEER_REPLY = (
    "In the body's first line, peeled off by the parse — the marker is the\n"
    "agent's contract and the addressee is routing data, so the body a peer\n"
    "reads is the text under the address line.\n"
)

#: The peer-message section heading: the dedicated section a peer message
#: renders under, distinct from the operator-answer section (008's) and from
#: the evidence section — a peer's voice is neither the operator's decision
#: nor the gates' verdict (FR-002, FR-003).
PEER_SECTION_HEADING = "## Peer message"

#: The heading the reply renders under on the asker's side — a reply is a peer
#: message in its own right, answered by a different node, so it shares the
#: section grammar rather than borrowing the operator's.
PEER_REPLY_HEADING = "## Peer reply"

#: The ferry inbox file name: the file in `$ATTEMPT_ARCHIVE` a delivered peer
#: message is written to, distinct from `answer` so a peer message is never
#: confused with an operator answer (plan: "a distinct inbox file").
FERRY_PEER_FILE = "peer-message"

#: The default bound on outstanding peer messages per node (FR-006). Two, so a
#: scripted ping-pong has room for one exchange and a third send is the refusal.
DEFAULT_PEER_MESSAGE_LIMIT = 2


# --- the scripted world, extended for peer routing ---------------------------


def peer_graph() -> list[WorkNode]:
    """`us1` and `us2` independent, so the addressee is dispatchable while the
    asker is parked — the premise the deadlock test turns on.

    No `depends_on` edge between them: a dependent asker would hold its
    addressee PENDING for reasons that have nothing to do with the pause, and
    the test would pass against a pausing implementation for the wrong reason.
    """
    return [
        make_node("us1", "US1"),
        make_node("us2", "US2"),
        make_node("us3", "US3"),
    ]


def asking_peer(client: Any, **overrides: Any) -> ScriptedWorld:
    """`us1` completes attempt 1 with a peer-addressed question for `us2`.

    The attempt is otherwise an ordinary passing one — the marker is what
    routes it, not a verdict — and `us2` passes its own attempts when they
    dispatch, so the round trip completes only if routing works.
    """
    script = ScriptedWorld(
        {
            "us1": [passing(), passing()],
            "us2": [passing()],
            "us3": [passing()],
        },
        client=client,
        **overrides,
    )
    script.question_bodies["us1"] = f"{TO_US2}\n{PEER_QUESTION}"
    return script


def scripted_reply(script: ScriptedWorld, *, text: str = PEER_REPLY) -> None:
    """Arm the addressee's reply, delivered the moment its prompt carries the
    message — the ferry's timing, modeled the way `question_answer` models the
    operator's.

    The addressee answers from its own scripted attempt: the message reached
    its prompt, so the attempt it runs replies to it. Nothing here knows how
    the message travelled; the reply is the world's, not routing's.
    """
    script.peer_reply = text


# --- US1-S6 / FR-016: the park that must not pause ---------------------------


async def test_a_parked_asker_does_not_pause_the_epic(
    env: WorkflowEnvironment,
) -> None:
    """FR-016 / acceptance scenario 6: the addressee dispatches while the asker
    is parked, answers, and the asker un-parks on the reply.

    This is the story's one structural trap, and the test the spec says MUST
    exist: the addressee must be dispatched *while the asker is parked*, or the
    pause deadlock is invisible. 008's operator park raises `_paused`
    deliberately — an epic waiting on a sleeping human should idle rather than
    spend — and reusing that path here deadlocks the feature by construction:
    the pause stops the very dispatch that would answer. The asker would wait
    the whole window, expire, and degrade to the operator, for every peer
    question, while every scripted test passed.

    So: the asker parks in a *distinct* state, the epic stays RUNNING, the
    addressee is dispatched, its reply un-parks the asker — and the asker's
    next attempt's prompt carries the reply verbatim.
    """
    script = asking_peer(env.client)
    scripted_reply(script)

    async with start_epic(env, script) as handle:
        # The asker parks — but the epic does not. The state is distinct from
        # WAITING_OPERATOR (the operator park), and the scheduler keeps
        # dispatching, so the addressee runs *while the asker is parked*.
        parked = await wait_for_status(
            handle,
            lambda status: (
                states(status).get("us1")
                in (NodeState.WAITING_PEER,)
                if hasattr(NodeState, "WAITING_PEER")
                else False
            ),
            what="us1 to park on the peer question",
        )

        # FR-016's whole claim: the epic is RUNNING, not PAUSED. The operator
        # pause is what would stop the addressee from ever being dispatched.
        assert parked.epic_state == EpicState.RUNNING

        # The addressee is dispatched while the asker is parked — the
        # observable that a both-alive ferry test can never produce.
        await wait_for(
            lambda: any(
                context.node_id == "us2" for context in script.attempts
            ),
            what="the addressee to be dispatched while the asker is parked",
        )

        # The reply arrives and the asker un-parks on it — not on an expiry.
        await wait_for_status(
            handle,
            lambda status: states(status).get("us1") == NodeState.MERGED,
            what="the asker to un-park on the reply and pass",
        )

    # The asker's second attempt carries the reply verbatim (FR-003): the
    # round trip closed through the addressee, not through the operator.
    prompts = script.prompts_for("us1")
    assert len(prompts) == 2
    assert PEER_REPLY in prompts[1]
    assert PEER_SECTION_HEADING in prompts[1] or PEER_REPLY_HEADING in prompts[1]


async def test_the_askers_park_is_a_distinct_state_from_the_operator_park(
    env: WorkflowEnvironment,
) -> None:
    """FR-016: a peer park MUST be a distinct node state, not WAITING_OPERATOR.

    The two parks differ in exactly one thing — who can end them — and that
    one thing is why they cannot share a state: an operator park is ended by a
    human typing into Telegram, and a peer park is ended by a node of this
    same epic being dispatched and answering. A shared state would carry the
    pause along with it (the seam the deadlock rides), and `ergane build reset`
    would read a peer wait as an operator wait.
    """
    assert hasattr(NodeState, "WAITING_PEER"), (
        "FR-016 requires a distinct node state for a peer park; sharing "
        "WAITING_OPERATOR is the deadlock's construction"
    )
    assert NodeState.WAITING_PEER != NodeState.WAITING_OPERATOR
    # The state is non-terminal and outside `_UNREACHABLE`, so a node parked on
    # a peer is not a dead edge — its dependents stay PENDING, not KILLED, and
    # it can be un-parked by the reply.
    from factory.workgraph.workflow import _UNREACHABLE

    assert NodeState.WAITING_PEER not in _UNREACHABLE


async def test_a_peer_parked_node_is_not_a_bracket_the_drain_waits_on(
    env: WorkflowEnvironment,
) -> None:
    """FR-016's drain exemption: `_drain_in_flight` must not wait on a peer
    park, the way it does not wait on an operator park.

    The drain runs on the pause and kill paths and waits for every in-flight
    node to finish. A parked node is in-flight but alive by design — its
    `_run_node` is parked in a `wait_condition` for the reply — so a drain that
    waited on it would deadlock the very pause that asked for the drain. The
    operator park earned this exemption in 008-US2; the peer park needs it too,
    or a kill pressed mid-peer-question hangs the drain forever.
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
            what="us1 to park on the peer question",
        )
        # A kill pressed while the asker is peer-parked must still end the
        # epic: the drain cannot be waiting on a live park. The signal is
        # buffered and the scheduler acts on it — the same discipline every
        # kill in this suite uses.
        await handle.signal("kill_epic")

    assert script.calls, "the epic ran"


# --- US1-S1: the exchange routes to the peer, not the operator ----------------


async def test_a_peer_question_is_not_paged_to_the_operator(
    env: WorkflowEnvironment,
) -> None:
    """FR-002 / acceptance scenario 1's clause: no operator notification is sent.

    `send_question` is the one paging surface the 008 channel has. A message
    that names a peer routes to the peer, so it must never reach the operator's
    phone — SC-001's whole claim, asserted as the absence of the call.
    """
    script = asking_peer(env.client)
    scripted_reply(script)

    status = await run_epic(env, script)

    assert states(status)["us1"] == NodeState.MERGED
    # No operator question was sent for the exchange — the addressee answered.
    assert script.question_requests == []


async def test_the_addressees_next_prompt_carries_the_message_verbatim(
    env: WorkflowEnvironment,
) -> None:
    """FR-002 / acceptance scenario 3: the peer-message section on the
    addressee's next dispatch, verbatim.

    The addressee is not running when the message routes (US1's half — the
    live ferry is US2's), so the delivery is into its next assembled prompt,
    under a section dedicated to peer messages. The body is what the asker
    wrote under the address line, byte for byte, and the section names who it
    is from so the addressee reads it as a peer's question rather than as
    standing instructions.
    """
    script = asking_peer(env.client)
    scripted_reply(script)

    status = await run_epic(env, script)

    assert states(status)["us2"] == NodeState.MERGED
    prompts = script.prompts_for("us2")
    assert len(prompts) == 1
    # Verbatim (FR-002): the body the asker wrote, unchanged.
    assert PEER_QUESTION in prompts[0]
    # A dedicated section, distinct from the operator-answer and evidence
    # sections — a peer's voice is neither the operator's nor the gates'.
    assert PEER_SECTION_HEADING in prompts[0]
    # The section names the asker, so the reply can be addressed back.
    assert "us1" in prompts[0]


async def test_the_reply_threads_back_to_the_asker_by_message_id(
    env: WorkflowEnvironment,
) -> None:
    """FR-003 / acceptance scenario 3's clause: the reply reaches the asker.

    The reply threads by message id — not by recency, not by "the last thing
    that happened" — so two open exchanges cannot cross. The store row is the
    record: the asker's message and the peer's reply are one row, attributed
    to sender and recipient, and the reply's text is what the asker's next
    prompt carries (FR-008).
    """
    script = asking_peer(env.client)
    scripted_reply(script)

    status = await run_epic(env, script)

    assert states(status)["us1"] == NodeState.MERGED
    # The exchange is recorded: one message row, sender us1, addressee us2,
    # reply set, resolution ANSWERED (FR-008).
    messages = script.messages_for(EPIC_ID)
    assert len(messages) == 1
    [message] = messages
    assert message.sender_node == "us1"
    assert message.addressee == "us2"
    assert message.body == PEER_QUESTION
    assert message.reply == PEER_REPLY
    assert message.resolution == ANSWERED


# --- US1-S5 / FR-004: degradation is the floor --------------------------------


async def test_an_unknown_addressee_degrades_to_the_operator_question(
    env: WorkflowEnvironment,
) -> None:
    """FR-004 / acceptance scenario 5: a name no node carries reaches the
    operator, carrying the message body.

    The operator is the floor, never the ceiling: a message that cannot be
    delivered must not hang a node or vanish, so it degrades to the 008
    operator-question path — the one channel whose delivery and expiry are
    proven. The operator question carries the message body, so the human who
    reads it sees what the agent actually asked.
    """
    script = ScriptedWorld(
        {"us1": [passing(), passing()], "us2": [passing()], "us3": [passing()]},
        client=env.client,
    )
    script.question_bodies["us1"] = f"To: nobody\n{PEER_QUESTION}"
    # The operator answers, so the node un-parks and the epic completes.
    script.question_answer = ANSWER_TEXT

    status = await run_epic(env, script)

    # Degraded: one operator question, carrying the message body.
    assert len(script.question_requests) == 1
    [question] = script.question_requests
    assert question.question_text == PEER_QUESTION
    # The node reached a terminal through the operator's answer, not a hang.
    assert states(status)["us1"] == NodeState.MERGED


async def test_a_self_addressed_message_is_refused_to_the_asker(
    env: WorkflowEnvironment,
) -> None:
    """FR-004 / the spec's edge cases: a node that wants to remember something
    has its worktree — a self-address is refused as undeliverable.

    The refusal is immediate and named, and the node is not consumed by it:
    the message degrades to the operator path rather than looping back to the
    sender, which would be a conversation with itself billed to the epic.
    """
    script = ScriptedWorld(
        {"us1": [passing(), passing()], "us2": [passing()], "us3": [passing()]},
        client=env.client,
    )
    script.question_bodies["us1"] = f"To: us1\n{PEER_QUESTION}"
    script.question_answer = ANSWER_TEXT

    status = await run_epic(env, script)

    # Refused to the asker, then degraded: the operator question carries the
    # body, and the exchange did not route to the sender itself.
    assert len(script.question_requests) == 1
    [question] = script.question_requests
    assert question.question_text == PEER_QUESTION
    assert states(status)["us1"] == NodeState.MERGED


async def test_a_terminal_addressee_degrades_to_the_operator_question(
    env: WorkflowEnvironment,
) -> None:
    """FR-004 / acceptance scenario 5: a peer that has already reached a
    terminal state can never answer, so the message degrades.

    `us3` merges before the asker's question routes — a merged node has no
    next attempt to carry a prompt section, so waiting for one would hang. The
    message reaches the operator with its body, and the asker proceeds on the
    operator's answer.
    """
    script = ScriptedWorld(
        {"us1": [passing(), passing()], "us2": [passing()], "us3": [passing()]},
        client=env.client,
    )
    script.question_bodies["us1"] = f"To: us3\n{PEER_QUESTION}"
    script.question_answer = ANSWER_TEXT

    status = await run_epic(env, script)

    assert len(script.question_requests) == 1
    [question] = script.question_requests
    assert question.question_text == PEER_QUESTION
    assert states(status)["us1"] == NodeState.MERGED


async def test_an_unanswered_peer_message_expires_to_the_operator(
    env: WorkflowEnvironment,
) -> None:
    """FR-004 / acceptance scenario 5: a peer message may go unanswered, and
    the expiry is the degradation, never a hang.

    The addressee never replies — its attempt ends without answering — so the
    message's own window elapses and the operator inherits it, carrying the
    body. The asker un-parks on the operator's answer, which is the floor
    doing its job: a message that goes unanswered costs one operator question,
    never a node.
    """
    script = asking_peer(env.client)
    # No `scripted_reply` — the addressee never answers. The operator does.
    script.question_answer = ANSWER_TEXT

    status = await run_epic(env, script)

    assert len(script.question_requests) == 1
    [question] = script.question_requests
    assert question.question_text == PEER_QUESTION
    assert states(status)["us1"] == NodeState.MERGED