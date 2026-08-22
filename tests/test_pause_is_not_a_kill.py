"""US4 — a pause parks; it does not kill what is left.

079-US4. `PAUSE_EPIC` routed the node through `NodeState.FAILED`, and `FAILED`
is in `_UNREACHABLE`, so `_lock_out_dependents` read the parked node as a dead
edge and killed everything waiting on it. One press ended three nodes
(2026-08-19): the blast radius of the button labelled "⏸️ Pause the epic" was
larger than the one labelled "🛑 Kill the node", and nothing in the message said
so.

The fix is one state, at both sites. A parked node ends `WAITING_OPERATOR` —
non-terminal, deliberately outside `_UNREACHABLE`, and the precedent is written
down at `factory/workgraph/models.py`: a question park is not a dead edge, so
its dependents stay PENDING rather than being KILLED. A `PAUSE_EPIC` press is
the same fact about the same node, reached by a different door.

What that buys, in the order the scenarios ask for it:

- **S1/FR-013**: the dependents are not killed.
- **S2/FR-014**: the epic's undispatched work — a dependent chain included —
  dispatches when the epic resumes. A park whose work cannot be resumed is a
  kill with a longer name.
- **S3/FR-015**: the message names what each offered button does to the node
  *and* to the epic, before the press rather than after it.
- **S4 is the control (trap 5)**: `_lock_out_dependents` is *correct* for a
  killed node — a dependency that will never merge means the dependent can
  never build — and a diff that satisfies S1 by weakening it has deleted the
  feature. A KILL press must still lock the dependents out, exactly as today.
- **S5**: `ergane build reset` acts on the state the press leaves behind. A
  park the operator cannot get out of by the documented verb is the deadlock
  the field report named, and the reason the park state must read as *waiting
  on a human* rather than as a terminal nobody is coming back to.

The worlds are 041-US3's and the interpreter's, not a third copy: S1, S2 and S4
script the ladder and the press; S5 presses for real, through the store and the
escalation child, because the state `reset` reads has to be the one a real press
produces.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from temporalio.testing import WorkflowEnvironment

from factory.cli.errors import OperatorError
from factory.cli.nouns.build import (
    _reset_epic,
    nodes_at_work,
    nodes_awaiting_operator,
    reset_refusal,
)
from factory.notify.messages import MESSAGE_LIMIT, escalation_message
from factory.verify.ladder import ENDING_CHOICES
from factory.verify.models import EscalationChoice, EscalationRecord
from factory.workgraph.models import EpicState, NodeState
from factory.workgraph.workflow import EpicWorkflow

from tests.test_epic_escalation_child import (  # noqa: F401 — pytest fixtures
    FakeAdapter,
    RealNotifyWorld,
    adapter,
    db_path,
    dialled,
    env,
    ladder_fails,
    pending,
    until,
)
from tests.test_interpreter import (
    EPIC_ID,
    RESUME_SIGNAL,
    SETTLE_S,
    ScriptedWorld,
    attempt_counts,
    exhausted,
    make_graph,
    make_node,
    passing,
    paused_with,
    run_epic,
    start_epic,
    states,
    wait_for_status,
)
from tests.test_killed_node_leaves_a_resettable_epic import (  # noqa: F401 — fixture
    press,
    reset_effect,
    survivors,
)

#: How the epic reads while a press is parked on it. Spelled once: S1 and S5 are
#: the same claim seen from the workflow and from the CLI, and two spellings is
#: how they would drift.
PARKED = NodeState.WAITING_OPERATOR


# --- T033 / US4-S1 / FR-013: the press does not kill the dependents ---------


async def test_a_pause_press_leaves_the_dependents_alive(
    env: WorkflowEnvironment,
) -> None:
    """US4-S1: PAUSE_EPIC on a node with dependents, and the dependents live.

    `us2` depends on `us1`, which is the node the press lands on; `us3` depends
    on nothing. Both must still be PENDING with the epic parked — untouched, no
    worktree, no key, no attempt — because a pause is a stop, not a verdict on
    the rest of the graph.

    Asserted on the state *at the pause* rather than at the end, because that is
    where the lock-out ran: `_reap_finished` applies it the moment the parked
    node's task is reaped, and a test reading only the final status could not
    tell "never killed" from "killed and something revived it".
    """
    script = exhausted(EscalationChoice.PAUSE_EPIC.value, env.client)

    async with start_epic(env, script) as handle:
        parked = await wait_for_status(
            handle,
            paused_with("us1", PARKED),
            what="us1 to park and the epic to pause",
        )

        assert states(parked) == {
            # Parked, not killed: the operator stopped the epic rather than
            # abandoning the node. Non-terminal, and outside `_UNREACHABLE`,
            # which is the whole of FR-013.
            "us1": PARKED,
            # The dependent of the parked node. FAILED here killed it.
            "us2": NodeState.PENDING,
            # Independent and undispatched: the pause outranks its readiness.
            "us3": NodeState.PENDING,
        }
        assert attempt_counts(parked) == {"us1": 4, "us2": 0, "us3": 0}
        # Nothing was spent on either survivor — no dispatch, no worktree, no key.
        assert script.sequence("us2") == []
        assert [r.node_id for r in script.prepare_requests] == ["us1"]
        assert [r.node_id for r in script.key_requests] == ["us1"] * 4

        # Constitution VI still holds on the park path: the work is on the branch
        # before the tree is swept, and the ref says which attempt left it there.
        assert script.sequence("us1")[-2:] == ["salvage_worktree", "remove_worktree"]
        assert [(s.node_id, s.attempt) for s in script.salvages] == [("us1", 4)]

        await handle.signal(RESUME_SIGNAL)
        status = await handle.result()

    # And the dependent is still there after the resume: PENDING, never KILLED.
    # Its edge is locked (nothing unlocks it but a PASS on us1), which is a
    # different fact from the edge being dead.
    assert states(status)["us2"] == NodeState.PENDING
    assert attempt_counts(status)["us2"] == 0


# --- T034 / US4-S2 / FR-014: the undispatched work dispatches on resume -----


async def test_the_undispatched_nodes_dispatch_when_the_epic_resumes(
    env: WorkflowEnvironment,
) -> None:
    """US4-S2: resume, and the work the pause caught undispatched runs.

    Declared `us3, us1, us2` so the node the press lands on is the *first* one
    scheduled and a whole dependent chain — `us1 → us2` — is still undispatched
    when the epic parks. That is the shape the field report described and the
    one a leaf-only test cannot prove: `us2`'s dispatch depends on `us1`'s PASS,
    so it can only happen if the pause left both of them alive *and* the
    scheduler came back for them.
    """
    graph = make_graph(
        [
            make_node("us3", "US3"),
            make_node("us1", "US1"),
            make_node("us2", "US2", depends_on=["us1"]),
        ]
    )
    script = ScriptedWorld(
        {"us3": ladder_fails(), "us1": [passing()], "us2": [passing()]},
        client=env.client,
        press=EscalationChoice.PAUSE_EPIC.value,
    )

    async with start_epic(env, script, graph=graph) as handle:
        parked = await wait_for_status(
            handle,
            paused_with("us3", PARKED),
            what="us3 to park and the epic to pause",
        )
        assert states(parked) == {
            "us3": PARKED,
            "us1": NodeState.PENDING,
            "us2": NodeState.PENDING,
        }
        # The pause really stopped dispatch: nothing but the parked node's own
        # attempts has run, and it stays that way while the epic is parked.
        assert script.dispatched == ["us3"] * 4
        await asyncio.sleep(SETTLE_S)
        assert script.dispatched == ["us3"] * 4

        await handle.signal(RESUME_SIGNAL)
        status = await handle.result()

    assert status.epic_state == EpicState.COMPLETED
    assert states(status) == {
        "us3": PARKED,
        "us1": NodeState.MERGED,
        "us2": NodeState.MERGED,
    }
    # The chain ran in declaration order after the resume, dependent included.
    assert script.dispatched == ["us3"] * 4 + ["us1", "us2"]


# --- T035 / US4-S3 / FR-015: the message names the blast radius -------------


def make_escalation(**overrides: Any) -> EscalationRecord:
    fields: dict[str, Any] = {
        "escalation_id": "0123456789ab",
        "workflow_id": "escalation-0123456789ab",
        "epic_id": EPIC_ID,
        "node_id": "us1",
        "choices": [EscalationChoice.RETRY, *ENDING_CHOICES],
        "history_summary": "attempt 4: gate test FAIL (exit 1)",
        "sent_at": "2026-08-22T11:00:00Z",
        "expires_at": "2026-08-22T12:00:00Z",
        "delivered": True,
    }
    fields.update(overrides)
    return EscalationRecord(**fields)


def effect_lines(message: str) -> dict[str, str]:
    """The rendered effect of each offered choice, keyed by choice name.

    Read off the message an operator is sent rather than out of the table it is
    built from: FR-015 is a claim about what reaches the chat, and comparing the
    table to itself would hold whatever the renderer did with it.
    """
    return {
        choice.value: line
        for line in message.splitlines()
        for choice in EscalationChoice
        if line.lstrip().startswith(f"{choice.value} ")
    }


def test_the_message_names_what_each_offered_button_does() -> None:
    """US4-S3: the blast radius is readable before the press, not after it.

    Every offered choice gets a line naming both halves — what the press does to
    *this node* and what it does to *the epic* — because the two differ per
    button and the pair is the whole decision. `KILL` and `PAUSE_EPIC` do the
    same thing to the node and opposite things to the epic's other work; that is
    exactly the distinction the 2026-08-19 press could not read.
    """
    message = escalation_message(make_escalation())
    lines = effect_lines(message)

    assert set(lines) == {"RETRY", "KILL", "PAUSE_EPIC", "KILL_EPIC"}
    for name, line in lines.items():
        assert "node:" in line, f"{name} does not say what it does to the node"
        assert "epic:" in line, f"{name} does not say what it does to the epic"

    # The two that end the node identically and the epic differently.
    assert "lock" in lines["KILL"], lines["KILL"]
    assert "not killed" in lines["PAUSE_EPIC"], lines["PAUSE_EPIC"]
    assert "resume" in lines["PAUSE_EPIC"], lines["PAUSE_EPIC"]
    assert "nothing else dispatches" in lines["KILL_EPIC"], lines["KILL_EPIC"]

    # The default is still stated: silence is not neutral (068 FR-008).
    assert "KILL the node" in message
    assert make_escalation().expires_at in message


def test_the_message_describes_the_offer_and_not_the_vocabulary() -> None:
    """A choice nobody offered gets no line — 079-US1's offer, read forward.

    The four values are the vocabulary; what an escalation *offers* is computed
    per node. A blast-radius block rendered from the enum would promise the
    operator a retry button on a node with nothing left to retry with, which is
    the defect US1 landed.
    """
    lines = effect_lines(escalation_message(make_escalation(choices=list(ENDING_CHOICES))))

    assert set(lines) == {"KILL", "PAUSE_EPIC", "KILL_EPIC"}
    assert "RETRY" not in lines


def test_the_blast_radius_survives_a_history_that_fills_the_message() -> None:
    """It is footer, not body: the clip takes evidence, never the consequence.

    A message clipped to Telegram's ceiling has to keep the part the operator is
    deciding from. `_compose` reserves the footer and eats the history, so the
    block is rendered there — an FR-015 line that a long gate log could push off
    the end would be absent exactly when the epic is in the most trouble.
    """
    record = make_escalation(history_summary="\n".join(["evidence line"] * 2000))

    message = escalation_message(record)

    assert len(message) <= MESSAGE_LIMIT
    assert set(effect_lines(message)) == {"RETRY", "KILL", "PAUSE_EPIC", "KILL_EPIC"}
    assert "truncated" in message.lower()
    assert record.node_id in message


# --- T036 / US4-S4: the control — KILL still locks the dependents out -------


async def test_a_kill_press_still_locks_out_the_dependents(
    env: WorkflowEnvironment,
) -> None:
    """US4-S4, **the control** (trap 5): `_lock_out_dependents` is not weakened.

    Same graph, same ladder, one different button. A dependency that ended
    KILLED will never merge, so the dependent can never build and is marked
    KILLED where it stands — no worktree, no key, no attempt. The independent
    leaf still runs, which is the difference between a locked edge and a stopped
    epic.

    This is the assertion a fix that satisfies S1 by removing the lock-out
    fails. It is written beside S1 on purpose: the two differ only in the press.
    """
    script = exhausted(EscalationChoice.KILL.value, env.client)

    status = await run_epic(env, script)

    assert status.epic_state == EpicState.COMPLETED
    assert states(status) == {
        "us1": NodeState.KILLED,
        "us2": NodeState.KILLED,
        "us3": NodeState.MERGED,
    }
    assert attempt_counts(status)["us2"] == 0
    assert script.sequence("us2") == []
    assert [r.node_id for r in script.key_requests] == ["us1"] * 4 + ["us3"]


# --- T037 / US4-S5: the park has an exit, and it is the documented verb ------


def paused_document(**nodes: dict[str, Any]) -> dict[str, Any]:
    """An `epic_status` answer in the shape the query hands the CLI: plain JSON."""
    return {"epic_state": "PAUSED", "nodes": dict(nodes)}


def test_reset_reads_a_parked_node_as_a_waiter_and_not_as_work() -> None:
    """US4-S5, the rule: the state a press leaves is one `reset` may act on.

    `reset_refusal` refuses a running epic unless somebody is being waited on
    *and* nothing is in flight behind them (068 FR-007). A `PAUSE_EPIC` press
    parks its node on the operator, so the epic satisfies both halves and the
    verb runs — where `FAILED` satisfied neither and the operator reached for
    `temporal workflow terminate`.
    """
    parked = {"state": PARKED.value, "awaiting_operator": True}
    waiting = {"state": "PENDING"}

    assert nodes_awaiting_operator(paused_document(us1=parked, us2=waiting)) == ("us1",)
    assert nodes_at_work(paused_document(us1=parked, us2=waiting)) == ()
    assert reset_refusal(EPIC_ID, paused_document(us1=parked, us2=waiting)) is None

    # The control, unchanged: a node genuinely working still refuses the reset,
    # parked sibling or not (068 US2-S4).
    refused = reset_refusal(
        EPIC_ID,
        paused_document(us1=parked, us2={"state": "RUNNING", "awaiting_operator": False}),
    )
    assert refused is not None and "us2" in refused, refused


async def test_reset_acts_on_the_epic_a_real_pause_press_leaves_behind(
    env: WorkflowEnvironment,
    db_path: Path,
    adapter: FakeAdapter,
    dialled: None,
    survivors: Any,
) -> None:
    """US4-S5, end to end: press PAUSE_EPIC for real, then run the verb.

    Nothing scripted between the button and the state `reset` reads — real
    escalation child, real store row, real signal — because the deadlock was in
    the state a real press produces, and a fake that produced a different one
    would prove the wrong thing. Then the second half of the scenario: the epic
    is *also* killable from where the press left it, so an operator who has
    archived the survivors can end it with the verb rather than with Temporal.
    """
    graph, repo, factory_root, worktrees = survivors
    script = RealNotifyWorld(
        {"us1": ladder_fails(), "us2": [passing()]}, client=env.client
    )

    async with start_epic(env, script, graph=graph) as handle:
        [row] = await until("us1's escalation", lambda: pending(db_path) or None)
        await press(env, row, EscalationChoice.PAUSE_EPIC)
        parked = await wait_for_status(
            handle,
            lambda status: status.epic_state == EpicState.PAUSED,
            what="the epic parked rather than ended",
            timeout=30.0,
        )
        assert states(parked) == {"us1": PARKED, "us2": NodeState.PENDING}

        assert await _reset_epic(graph) == 0
        reset_effect(repo, factory_root, worktrees)

        # The press is answered; the epic is the operator's to end, and the
        # documented verb reaches it from the park.
        await handle.signal(EpicWorkflow.kill_epic)
        killed = await handle.result()

    assert killed.epic_state == EpicState.KILLED
    assert states(killed) == {"us1": NodeState.KILLED, "us2": NodeState.KILLED}
