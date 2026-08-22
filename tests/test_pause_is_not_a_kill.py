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

from factory.cli.nouns.build import (
    _reset_epic,
    nodes_at_work,
    nodes_awaiting_operator,
    reset_refusal,
)
from factory.mergequeue.models import CheckFailure, LandingConfig, LandingState
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
    checks_failed_snapshot,
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


def show(what: str, status: Any) -> None:
    """Print the graph's states — SC-008's evidence, remade by `pytest -s`.

    Captured and invisible on an ordinary run, so it costs the suite nothing.
    It exists because the block at the foot of this file has to be reproducible
    by the next reader rather than trusted as a transcript: the same two tests
    under `-s` print it again.
    """
    print(f"\n{what}")
    for node_id, node in status.nodes.items():
        print(f"  {node_id:<4} {node.state.value:<17} attempt={node.attempt}")


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

        show("PAUSE_EPIC pressed on us1, which us2 depends on:", parked)
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

    show("after `resume_epic`:", status)
    # And the dependent is still there after the resume: PENDING, never KILLED.
    # Its edge is locked (nothing unlocks it but a PASS on us1), which is a
    # different fact from the edge being dead.
    assert states(status)["us2"] == NodeState.PENDING
    assert attempt_counts(status)["us2"] == 0


async def test_a_pause_press_on_the_landing_page_spares_the_merge_gated_dependents(
    env: WorkflowEnvironment,
) -> None:
    """US4-S1 at the other escalation site (trap 2): a fix to one is half a fix.

    The ladder pages from a spent attempt budget; the landing pages from a spent
    recovery budget. They are different methods with different callers, and the
    one-line defect was in both. This is 075/us1's landing shape — rejected,
    recovered once, rejected again, budget gone — with a *merge-gated* dependent
    behind it.

    That dependent is the second door onto the same lock-out, and it does not go
    through `_UNREACHABLE`: the press ends the landing KILLED (nothing drives
    that PR while the epic is stopped), and a landing that is terminal-but-
    unmerged is a dead edge for anything waiting on the merge. So `us2` would
    still have died with `us1` parked, on a graph the ladder test cannot build.
    `_dead_edge` reads the node's park and spares it.
    """
    graph = make_graph(
        [
            make_node("us1", "US1"),
            make_node("us2", "US2", depends_on_merged=["us1"]),
        ]
    )
    script = ScriptedWorld(
        {"us1": [passing(), passing()], "us2": [passing()]},
        client=env.client,
        press=EscalationChoice.PAUSE_EPIC.value,
    )
    script.script_landing("us1", checks_failed_snapshot(), checks_failed_snapshot())
    script.script_sync("us1", clean=True, base_ref="c0ffee")

    async with start_epic(
        env,
        script,
        graph=graph,
        landing_config=LandingConfig(max_recovery_cycles=1, poll_interval_s=0),
    ) as handle:
        parked = await wait_for_status(
            handle,
            paused_with("us1", PARKED),
            what="us1's landing to park and the epic to pause",
        )
        show("PAUSE_EPIC pressed on us1's landing page, us2 merge-gated on it:", parked)

        # The premise: this really is the landing page, with its budget spent.
        assert parked.nodes["us1"].recovery_cycles == 1
        assert parked.nodes["us1"].landing_state == LandingState.KILLED
        assert states(parked) == {"us1": PARKED, "us2": NodeState.PENDING}

        await handle.signal(RESUME_SIGNAL)
        status = await handle.result()

    # The edge is locked — `us2` waits for a MERGE that is not coming while the
    # node is parked — but it is not dead, and the node is not killed for it.
    assert states(status) == {"us1": PARKED, "us2": NodeState.PENDING}
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
        show("PAUSE_EPIC pressed on us3, with the us1 → us2 chain undispatched:", parked)
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

    show("after `resume_epic`:", status)
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


def test_the_blast_radius_is_the_last_thing_read_and_survives_the_clip() -> None:
    """It is footer, not evidence: it outlives the clip and follows every input.

    Two claims, and the second is what makes the first mean something.
    `_compose` reserves header and footer and eats the history from the front, so
    a block rendered into the footer is kept whole when a 32 KiB gate tail fills
    the message — an FR-015 line pushed off the end by evidence would be missing
    exactly when the epic is in the most trouble.

    But a block appended to the *end* of the body would survive that clip too,
    since the clip keeps the tail. What separates them is order: the footer
    follows the check evidence as well as the history, so what the operator reads
    last, immediately above the deadline, is what each press will do. The
    evidence answers "what happened"; this answers "what happens if I press",
    and the second question is the one they are being paged to decide.
    """
    record = make_escalation(
        history_summary="\n".join(["evidence line"] * 2000),
        check_evidence=(
            CheckFailure(
                name="build", url="https://forge/run/9", log_tail="E FAILED", note=""
            ),
        ),
    )

    message = escalation_message(record)

    assert len(message) <= MESSAGE_LIMIT
    assert set(effect_lines(message)) == {"RETRY", "KILL", "PAUSE_EPIC", "KILL_EPIC"}
    assert "truncated" in message.lower()
    assert record.node_id in message  # the header survives the clip too

    # Every input, then the consequence, then the deadline — in that order.
    assert (
        message.index("Failing check evidence:")
        < message.index("What each button does:")
        < message.index("No answer by")
    ), message[-1200:]


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


# --- runtime evidence, pasted verbatim (constitution VIII / D-037) ----------
#
# T041 / SC-008 — the press, the dependents after it, and the resume. Printed by
# `show()` from the three tests that assert these runs, so the paste cannot drift
# without a test failing with it: `pytest tests/test_pause_is_not_a_kill.py -s`.
#
# BEFORE, at 974503c (tests committed, implementation not) — the defect:
#   AssertionError: timed out waiting for us1 to park and the epic to pause;
#   last status: EpicStatus(epic_state=PAUSED, nodes={'us1': NodeStatus(
#   state=<NodeState.FAILED: 'FAILED'>, ... 'us2': NodeStatus(
#   state=<NodeState.KILLED: 'KILLED'>, attempt=0, ...
#
# AFTER:
#   PAUSE_EPIC pressed on us1, which us2 depends on:
#     us1  WAITING_OPERATOR  attempt=4
#     us2  PENDING           attempt=0
#     us3  PENDING           attempt=0
#   after `resume_epic`:
#     us1  WAITING_OPERATOR  attempt=4
#     us2  PENDING           attempt=0
#     us3  MERGED            attempt=1
#
#   PAUSE_EPIC pressed on us1's landing page, us2 merge-gated on it:
#     us1  WAITING_OPERATOR  attempt=2
#     us2  PENDING           attempt=0
#
#   PAUSE_EPIC pressed on us3, with the us1 → us2 chain undispatched:
#     us1  PENDING           attempt=0
#     us2  PENDING           attempt=0
#     us3  WAITING_OPERATOR  attempt=4
#   after `resume_epic`:
#     us1  MERGED            attempt=1
#     us2  MERGED            attempt=1
#     us3  WAITING_OPERATOR  attempt=4
#
# US4-S5, from the run above under `-s`: reset acts on the park, and says the
# epic is still the operator's to end.
#   note: epic 'demo-loans' is still running, waiting on an operator for us1;
#         end it with `ergane build kill demo-loans`
#   us1: committed dirty state, removed worktree, archived branch
#   us2: committed dirty state, removed worktree, archived branch
#
# T042 / SC-009 — the rendered message, all four offered (the ladder page of a
# node with an attempt left). Body clipped here to the two lines that are not
# this story's; nothing else is elided.
#
#   ⚠️ Verification escalation
#   epic: demo-loans
#   node: us1
#
#   Attempt 4 — FAIL
#     gate test: FAIL (exit 1, 12.4s)
#
#   What each button does:
#   RETRY (🔁 Retry the node) — node: one more attempt, on the tree this one
#     left behind. epic: unchanged — it keeps dispatching.
#   KILL (🛑 Kill the node) — node: ends KILLED, its branch preserved. epic:
#     keeps dispatching, but every node waiting on this one is locked out and
#     ends KILLED with it, undispatched.
#   PAUSE_EPIC (⏸️ Pause the epic) — node: ends parked, not killed — nothing
#     waiting on it is locked out. epic: stops dispatching until you resume it;
#     the undispatched nodes keep their place and run then.
#   KILL_EPIC (💥 End the whole epic) — node: ends KILLED, its branch preserved.
#     epic: ends with it — nothing else dispatches, and any other node's open
#     page is cancelled unanswered.
#
#   No answer by 2026-08-22T12:00:00Z applies the default: KILL the node.
#
# On a page that offers only the ending three (079-US1's computed offer), the
# RETRY line is absent and the other three are unchanged.
#
# Six mutations, each reverted before the next, named by the claim it kills:
#  1. `_dead_edge`'s park guard removed -> FAILED ..._on_the_landing_page_spares_
#     the_merge_gated_dependents: us2 KILLED. The landing half of the lock-out.
#  2. the landing site back to `NodeState.FAILED` -> FAILED the same one.
#  3. the ladder site back to `NodeState.FAILED` -> FAILED 3: ..._leaves_the_
#     dependents_alive, ..._undispatched_nodes_dispatch..., ..._reset_acts_on...
#  4. `render_blast_radius` iterating `EscalationChoice` instead of the offer ->
#     FAILED ..._describes_the_offer_and_not_the_vocabulary.
#  5. the block moved from the footer into the body -> FAILED ..._is_the_last_
#     thing_read_and_survives_the_clip. Its first shape did NOT catch this (the
#     clip keeps the body's tail either way); the ordering assertion is what
#     does, and the docstring now claims only what it proves.
#  6. the PAUSE_EPIC line's epic half deleted -> FAILED ..._names_what_each_
#     offered_button_does.
#
# The gate `factory.yaml` declares, on the whole tree: 4212 passed, 52 skipped
# in 331.23s. Two pre-existing tests changed with the fix — both asserted the
# defect (`us1` FAILED, `us2` KILLED) and now assert the park.
#
# The diff was measured with `diffbounds` rather than estimated, because a story
# whose evidence outgrows its code is refused before a judge reads a line of it
# (constitution VIII / D-050): 47,161 bytes of the 65,536 ceiling.
