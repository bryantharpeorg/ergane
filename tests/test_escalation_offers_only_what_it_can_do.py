"""US1 — an escalation offers only what this node can execute.

079-US1. The offer was a constant: both escalation sites handed over
`DEFAULT_CHOICES` whole regardless of what the node behind it could still do.
Two measured losses came out of that:

    2026-08-19 22:08  KILL pressed three times on one node; each answered KILL
                      was followed within a second by a fresh escalation.
    2026-08-21 03:18  RETRY pressed on 075/us1 AFTER `recovery_cycles` hit its
                      cap of 1. The epic's next activity was `remove_worktree`.
                      No key was issued and no agent ran.

What is asserted is the **choice list handed to the escalation** — the
`SendEscalationInput.choices` the notifier receives — never the enum (trap 1).

"No attempt left" differs per path. On the ladder a press always buys one more
attempt, because `next_action` computes `allowed = max_attempts +
len(escalations)` (068 FR-003), so the ladder page where a press buys nothing is
the *launch-failure* one: US1-S1. On the landing the recovery budget is the
ceiling and nothing raises it: US1-S2, 075/us1 at 03:18Z. The premise test
asserts the first rather than trusting it.

The control (US1-S3, trap 3) is here twice, once per path: a change satisfying
S1 and S2 by never offering `RETRY` has deleted the feature. Both controls watch
an attempt key get issued *after* the press.
"""

from __future__ import annotations

from typing import Any

from temporalio.testing import WorkflowEnvironment

from factory.activities.notify_activities import SendEscalationInput
from factory.escalation.workflow import EscalationRequest
from factory.mergequeue.models import Landing, LandingConfig, LandingState
from factory.verify.ladder import (
    ENDING_CHOICES,
    grant_produces_work,
    is_unoffered,
    offered_choices,
)
from factory.verify.models import (
    AttemptRecord,
    EscalationChoice,
    OverallVerdict,
    VerificationConfig,
)
from factory.verify.store import EXPIRED
from factory.workgraph.models import NodeRecord, NodeState, ResolvedNode
from factory.workgraph.workflow import EpicInput, EpicWorkflow

from tests.test_interpreter import (
    EPIC_ID,
    PROXY_URL,
    ScriptedWorld,
    attempt_counts,
    branch_name,
    checks_failed_snapshot,
    env,  # noqa: F401  — pytest fixture, re-exported for this module
    failing,
    make_graph,
    make_node,
    merged_snapshot,
    one_node,
    passing,
    run_epic,
    states,
)
from tests.test_launch_is_not_an_attempt import LaunchFailingWorld

#: The whole vocabulary, by name. Spelled rather than imported so a change to
#: what is *offered* cannot silently change what these tests compare against.
ALL_FOUR = ["RETRY", "KILL", "PAUSE_EPIC", "KILL_EPIC"]

#: What is left when the node cannot be put back to work. Ending needs no
#: budget, so these three are executable on any node at any moment.
WITHOUT_RETRY = ["KILL", "PAUSE_EPIC", "KILL_EPIC"]

WORKER = "implementer"

#: The shipped landing budget: one automatic recovery cycle and no more — what
#: 075/us1 ran under at 03:18Z. `BUDGETED` leaves one to spend.
SPENT = LandingConfig(max_recovery_cycles=1, poll_interval_s=0)
BUDGETED = LandingConfig(max_recovery_cycles=2, poll_interval_s=0)


def offers(script: ScriptedWorld) -> list[list[str]]:
    """Every choice list handed to the notifier, by name, in raise order."""
    return [
        [str(choice) for choice in request.choices]
        for request in script.escalation_requests
    ]


def the_offer(script: ScriptedWorld) -> list[str]:
    """The one choice list this world raised — and the assertion that it is one."""
    raised = offers(script)
    assert len(raised) == 1, f"expected exactly one escalation, got {len(raised)}"
    return raised[0]


def keys_in(calls: list[str]) -> list[str]:
    """Every attempt key issued in this slice of the activity log.

    Matched by prefix: the log names the persona the key was minted for, and
    what this asserts is that a key was issued at all.
    """
    return [call for call in calls if call.startswith("issue_attempt_key")]


def assert_executable(offer: list[str]) -> None:
    """FR-003 on one offer: never empty, never anything outside the four.

    Called from every escalation this suite raises, so it is checked on every
    offer rather than on a hand-picked one.
    """
    assert offer, "an escalation with an empty keyboard is a park with no exit"
    assert set(offer) <= set(ALL_FOUR), f"offered something outside the enum: {offer}"
    assert set(WITHOUT_RETRY) <= set(offer), f"offer has no executable floor: {offer}"


def report(*lines: str) -> None:
    """Print one block of the evidence pasted at the bottom of this file.

    The judge sees the diff and nothing else (constitution VIII), so SC-001 to
    SC-003 arrive as text — printed from the tests that already assert those
    runs, so the paste cannot drift without a test failing with it.
    """
    print("\n" + "\n".join(lines))


def resolved_for(node: Any) -> ResolvedNode:
    return ResolvedNode(
        node=node,
        model_alias="implementer-alias",
        models=["implementer-alias"],
        write_scope="worktree",
        timeout_s=1,
    )


# --- the four worlds ---------------------------------------------------------


def a_node_the_ladder_will_not_run_again(client: Any, press: str) -> LaunchFailingWorld:
    """Every launch fails, so `max_launch_retries` decides the node before the page."""
    return LaunchFailingWorld({"us1": [passing()]}, client=client, press=press)


def a_ladder_with_an_attempt_to_sell(client: Any, press: str) -> ScriptedWorld:
    """Three failures and a debugger cycle, then one more attempt a press can buy."""
    return ScriptedWorld(
        {"us1": [failing(1), failing(2), failing(3), failing(4), passing()]},
        client=client,
        press=press,
    )


def a_landing_with_its_budget_spent(client: Any, press: str) -> ScriptedWorld:
    """075/us1's shape: recovered once, re-enqueued, rejected again, budget gone.

    Run under `SPENT`: the first rejection is recovered automatically, the
    recovery re-enqueues, the queue rejects it again — so the scheduler picks the
    REJECTED landing back up with the budget spent and pages.
    """
    script = ScriptedWorld({"us1": [passing(), passing()]}, client=client, press=press)
    script.script_landing("us1", checks_failed_snapshot(), checks_failed_snapshot())
    script.script_sync("us1", clean=True, base_ref="c0ffee")
    return script


def a_landing_with_a_cycle_left(client: Any, press: str) -> ScriptedWorld:
    """The same rejection under `BUDGETED`, where the recovery attempt fails.

    One cycle is charged by the automatic recovery; the attempt fails; the page
    is raised with a second still to grant, and the press spends it.
    """
    script = ScriptedWorld(
        {"us1": [passing(), failing(2), passing()]}, client=client, press=press
    )
    script.script_landing("us1", checks_failed_snapshot(), merged_snapshot())
    script.script_sync("us1", clean=True, base_ref="c0ffee")
    return script


# --- the premise, asserted rather than trusted -------------------------------


def test_the_ladder_sells_one_more_attempt_for_every_press() -> None:
    """Why US1-S1 is asserted on the launch path, not on an exhausted ladder.

    A press raises `allowed` with it, so an exhausted ladder always has one more
    attempt to sell (068 FR-003) and `RETRY` on it is honest. If that stops being
    true, this fails loudly instead of S1 quietly asserting nothing.
    """
    config = VerificationConfig()
    spent = [
        AttemptRecord(attempt=n, persona=WORKER, verdict=OverallVerdict.FAIL)
        for n in (1, 2, 3)
    ]

    assert grant_produces_work(spent, config) is True
    # And after a grant that was itself spent, the next press still buys one.
    spent_again = [
        *spent,
        AttemptRecord(attempt=4, persona=WORKER, verdict=OverallVerdict.FAIL),
    ]
    assert grant_produces_work(spent_again, config, [EscalationChoice.RETRY]) is True

    # An answer that ended the node is the one thing no grant survives, which is
    # why FR-005's guard and not this function is what stops a second page.
    assert grant_produces_work(spent, config, [EscalationChoice.KILL]) is False


# --- US1-S1 (T001, FR-002): the ladder will not run this node again ----------


async def test_a_node_the_ladder_will_not_run_again_is_not_offered_retry(
    env: WorkflowEnvironment,
) -> None:
    """US1-S1: the launch-failure escalation offers no button that buys an attempt.

    `max_launch_retries` is spent, so `_run_node` has already decided the node
    ends KILLED and reads the resolution for `KILL_EPIC` alone. The press is
    `RETRY` deliberately — the button the operator was shown before this change —
    so the child refuses the reply, the hour runs out and the row expires: trap
    4's control, that `EXPIRED` is not an unoffered choice.
    """
    script = a_node_the_ladder_will_not_run_again(
        env.client, EscalationChoice.RETRY.value
    )

    status = await run_epic(env, script, graph=one_node())

    offer = the_offer(script)
    assert_executable(offer)
    assert "RETRY" not in offer, "a button that buys nothing was offered"
    assert offer == WITHOUT_RETRY

    # It ended on the expiry rather than on the press: the offer is what binds,
    # not the callback data.
    assert states(status) == {"us1": NodeState.KILLED}
    assert script.expirations == script.escalation_ids
    assert "AGENT_LAUNCH_FAILED" in (status.nodes["us1"].terminal_reason or "")


# --- US1-S2 (T002, FR-002): the landing's recovery budget is spent -----------


async def test_a_landing_with_no_recovery_cycle_left_is_not_offered_retry(
    env: WorkflowEnvironment,
) -> None:
    """US1-S2: 075/us1's exact configuration at 03:18Z on 2026-08-21.

    One landing, rejected; one recovery cycle spent (the whole budget at the
    shipped default); the re-enqueue rejected again. `RETRY` on that page fell
    through `_apply_landing_resolution` to the kill — `remove_worktree` at 03:18Z.
    """
    script = a_landing_with_its_budget_spent(env.client, EscalationChoice.KILL.value)

    status = await run_epic(env, script, graph=one_node(), landing_config=SPENT)

    # The premise: the budget really is spent when the page is raised.
    assert status.nodes["us1"].recovery_cycles >= 1

    offer = the_offer(script)
    assert_executable(offer)
    assert "RETRY" not in offer, "retry was offered on a spent recovery budget"
    assert offer == WITHOUT_RETRY

    assert states(status) == {"us1": NodeState.KILLED}
    assert status.nodes["us1"].landing_state == LandingState.KILLED

    # SC-001's left column and the whole of SC-003, printed from the run that
    # asserts them rather than from a second epic built to look like this one.
    node = status.nodes["us1"]
    report(
        "SC-001  a node with nothing left",
        f"  recovery_cycles={node.recovery_cycles}/{SPENT.max_recovery_cycles}"
        f"  offered {offer}",
        "SC-003  the answered KILL",
        f"  escalations raised for us1 afterwards: {len(script.escalation_requests)}",
        f"  node ends {node.state}, landing {node.landing_state}, branch {node.branch}",
    )
    assert len(script.escalation_requests) == 1
    assert node.recovery_cycles == SPENT.max_recovery_cycles


# --- US1-S3 (T003): the control, on both paths -------------------------------


async def test_a_node_with_an_attempt_left_is_offered_retry_and_the_press_issues_a_key(
    env: WorkflowEnvironment,
) -> None:
    """US1-S3, the ladder half (trap 3): the press buys a real attempt.

    Three failures, a debugger cycle, then the page. A press of `RETRY` must
    produce an `issue_attempt_key` *after* the escalation — a fifth attempt that
    dispatches, not a value a function returned.
    """
    script = a_ladder_with_an_attempt_to_sell(env.client, EscalationChoice.RETRY.value)

    status = await run_epic(
        env,
        script,
        graph=one_node(),
        landing_config=LandingConfig(poll_interval_s=0),
    )

    offer = the_offer(script)
    assert_executable(offer)
    assert offer == ALL_FOUR, "the node had an attempt to sell and was not offered it"

    # The press was executed: a key was issued after the page, and the attempt
    # it opened is the one that landed the node.
    page = script.calls.index("send_escalation")
    after_the_page = script.calls[page:]
    assert keys_in(after_the_page), "the press bought no attempt"
    assert [key.attempt for key in script.key_requests] == [1, 2, 3, 4, 5]
    assert attempt_counts(status) == {"us1": 5}
    assert states(status) == {"us1": NodeState.MERGED}

    # SC-001's right column and SC-002, from the run that asserts them.
    node = status.nodes["us1"]
    report(
        "SC-001  a node with an attempt left",
        f"  attempts={len(keys_in(script.calls[:page]))} spent when the page went "
        f"out, one more buyable  offered {offer}",
        "SC-002  the RETRY press on the node with budget",
        f"  activity log from the page: {script.calls[page : page + 4]}",
        f"  attempt keys issued after it: {keys_in(after_the_page)}",
        f"  node ends {node.state} at attempt {node.attempt}",
    )
    assert keys_in(after_the_page) == ["issue_attempt_key:implementer"]
    assert len(keys_in(script.calls[:page])) == 4  # three attempts + the debugger


async def test_a_landing_with_a_cycle_left_is_offered_retry_and_the_press_spends_it(
    env: WorkflowEnvironment,
) -> None:
    """US1-S3, the landing half: a cycle remains, so the button is real.

    US1-S2's shape under a budget of two. The press spends the cycle that is
    left: a third attempt dispatches and it merges.
    """
    script = a_landing_with_a_cycle_left(env.client, EscalationChoice.RETRY.value)

    status = await run_epic(env, script, graph=one_node(), landing_config=BUDGETED)

    offer = the_offer(script)
    assert_executable(offer)
    assert offer == ALL_FOUR, "a cycle remained and RETRY was withheld"

    after_the_page = script.calls[script.calls.index("send_escalation") :]
    assert keys_in(after_the_page), "the press bought no recovery cycle"
    assert states(status) == {"us1": NodeState.MERGED}
    assert status.nodes["us1"].pr_number is not None
    assert status.nodes["us1"].recovery_cycles == 2
    assert attempt_counts(status) == {"us1": 3}


# --- US1-S4 (T004, FR-003): every offer has an exit ---------------------------


def test_every_offer_is_non_empty_and_every_choice_in_it_is_executable() -> None:
    """FR-003, at the one function that decides what an escalation shows.

    Both answers are asserted, so a computation returning nothing when a node can
    do nothing fails here rather than reaching an operator keyboardless.
    """
    for retry_grants_work in (True, False):
        offer = offered_choices(retry_grants_work=retry_grants_work)
        assert offer, "an escalation with an empty keyboard is a park with no exit"
        assert all(isinstance(choice, EscalationChoice) for choice in offer)
        assert set(ENDING_CHOICES) <= set(offer)

    assert offered_choices(retry_grants_work=True) == [
        EscalationChoice.RETRY,
        *ENDING_CHOICES,
    ]
    assert offered_choices(retry_grants_work=False) == list(ENDING_CHOICES)
    # 068-US2 put `KILL_EPIC` last on purpose: the buttons render in offer order
    # and it is the one press no other press undoes.
    assert offered_choices(retry_grants_work=True)[-1] == EscalationChoice.KILL_EPIC


def test_a_request_that_names_no_choices_offers_no_button_it_cannot_honour() -> None:
    """T008's decision, asserted: there is no all-four default left to inherit.

    A default cannot know a node's budget, so it is the ending floor, and a
    caller that wants `RETRY` has to have checked something to ask for it.
    """
    request = EscalationRequest(epic_id=EPIC_ID, node_id="us1", history_summary="")
    activity_input = SendEscalationInput(
        workflow_id="w", epic_id=EPIC_ID, node_id="us1", history_summary=""
    )

    for choices in (request.choices, activity_input.choices):
        assert choices, "a default with no choices is a park with no exit"
        assert EscalationChoice.RETRY not in choices
        assert list(choices) == list(ENDING_CHOICES)


# --- US1-S5 (T005, FR-004): a resolution nobody offered is refused -----------


def test_expired_is_not_an_unoffered_choice() -> None:
    """Trap 4: the two cases are separated explicitly, not by omission.

    `EXPIRED` is the store's timeout value rather than a button: nobody offers
    it and it must go on ending the node, so the predicate exempts it by name.
    """
    offer = list(ENDING_CHOICES)

    assert is_unoffered(EXPIRED, offer) is False
    assert is_unoffered(EscalationChoice.RETRY.value, offer) is True
    assert is_unoffered("resolved", offer) is True
    assert is_unoffered(EscalationChoice.KILL.value, offer) is False
    # A node that was never paged refuses nothing: what reaches one of those is
    # the workflow's own fail-safe — a page nobody received, an epic stopped
    # before it went out — not a press. Refusing it would leave a node nothing
    # can end, a worse deadlock than the one being fixed.
    assert is_unoffered(EscalationChoice.KILL.value, []) is False
    # An offer that includes RETRY does not refuse it — the predicate reads the
    # offer, never a hardcoded list.
    assert is_unoffered(EscalationChoice.RETRY.value, [EscalationChoice.RETRY]) is False


async def test_a_resolution_nobody_offered_is_refused_by_name_not_applied_as_a_kill() -> None:
    """US1-S5 at the fall-through the spec names.

    A replayed callback naming `RETRY` on a page that never offered it went
    straight into the "anything unoffered ends the node killed" branch. It is
    refused by name and recorded instead, and the landing stays REJECTED so the
    scheduler pages again rather than the refusal being spent as the node's
    death.

    Called directly rather than through Temporal because the refusal path emits
    no command — it returns before any activity, which is precisely the claim.
    `sources` and `judge` are `None` so a later edit that uses them fails loudly.
    """
    node = make_node("us1", "US1")
    workflow_under_test = EpicWorkflow()
    record = NodeRecord(
        node_id="us1",
        branch=branch_name(EPIC_ID, "us1"),
        state=NodeState.ENQUEUED,
        verified=True,
        landing=Landing(
            node_id="us1",
            branch=branch_name(EPIC_ID, "us1"),
            pr_number=1,
            state=LandingState.REJECTED,
        ),
        # What the page actually offered: the budget was spent, so no RETRY.
        offered_choices=list(WITHOUT_RETRY),
    )
    workflow_under_test._nodes["us1"] = record

    await workflow_under_test._apply_landing_resolution(
        make_graph([node]),
        EpicInput(graph=make_graph([node]), proxy_url=PROXY_URL),
        resolved_for(node),
        EscalationChoice.RETRY.value,
        None,
        None,
    )

    assert record.refused_resolutions == ["RETRY"], "the refusal was not recorded by name"
    assert record.state == NodeState.ENQUEUED, "an unoffered resolution killed the node"
    assert record.landing is not None
    assert record.landing.state == LandingState.REJECTED
    assert record.ending_answer is None, "a refusal was recorded as an operator's answer"


# --- US1-S6 (T006, FR-005): an answered KILL is the last page ----------------


async def test_an_answered_kill_leaves_exactly_one_escalation_on_the_ladder(
    env: WorkflowEnvironment,
) -> None:
    """US1-S6: the ladder's KILL is answered once and asked once.

    On 2026-08-19 three answered kills produced three fresh escalations for one
    node, and a hand-run `temporal workflow terminate` to stop it.
    """
    script = a_ladder_with_an_attempt_to_sell(env.client, EscalationChoice.KILL.value)

    status = await run_epic(env, script, graph=one_node())

    assert states(status) == {"us1": NodeState.KILLED}
    assert len(script.escalation_requests) == 1, offers(script)
    assert [request.node_id for request in script.escalation_requests] == ["us1"]
    for offer in offers(script):
        assert_executable(offer)


async def test_an_answered_kill_leaves_exactly_one_escalation_on_the_landing(
    env: WorkflowEnvironment,
) -> None:
    """US1-S6 on the other path: the landing's KILL is asked once too.

    The rejected-twice landing of US1-S2: the node ends KILLED with its branch
    preserved and no second page.
    """
    script = a_landing_with_its_budget_spent(env.client, EscalationChoice.KILL.value)

    status = await run_epic(env, script, graph=one_node(), landing_config=SPENT)

    assert states(status) == {"us1": NodeState.KILLED}
    assert len(script.escalation_requests) == 1, offers(script)
    assert status.nodes["us1"].branch == branch_name(EPIC_ID, "us1")


# --- The measured evidence (SC-001, SC-002, SC-003; constitution VIII) -------
#
# Stdout from this file, run in this worktree on 2026-08-22. Each block is
# printed by the test that asserts that scenario, so the paste cannot drift from
# the behaviour without a test failing with it. The choice lists are the
# `SendEscalationInput.choices` the notifier activity was actually handed.
#
#     $ uv run pytest -q -p no:randomly -s \
#           tests/test_escalation_offers_only_what_it_can_do.py
#
#     ..
#     SC-001  a node with nothing left
#       recovery_cycles=1/1  offered ['KILL', 'PAUSE_EPIC', 'KILL_EPIC']
#     SC-003  the answered KILL
#       escalations raised for us1 afterwards: 1
#       node ends KILLED, landing KILLED, branch factory/demo-loans/us1
#     .
#     SC-001  a node with an attempt left
#       attempts=4 spent when the page went out, one more buyable  offered ['RETRY', 'KILL', 'PAUSE_EPIC', 'KILL_EPIC']
#     SC-002  the RETRY press on the node with budget
#       activity log from the page: ['send_escalation', 'teardown_attempt:debugger', 'issue_attempt_key:implementer', 'run_agent_attempt']
#       attempt keys issued after it: ['issue_attempt_key:implementer']
#       node ends MERGED at attempt 5
#     ........
#     11 passed in 1.95s
#
# SC-001's two blocks are the whole story: one page, one computation, two
# keyboards, and the difference is a budget rather than a constant. SC-002 is
# trap 3's control in tool output — the press is followed by `issue_attempt_key`,
# so the button that says retry bought an attempt a real agent activity ran.
# SC-003 is 2026-08-19's shape, answered: one press, one escalation, no second.
