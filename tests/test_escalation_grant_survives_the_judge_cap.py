"""The RETRY button produces an attempt, even when the judge's budget is gone.

068-US1. An escalation offers three buttons; one of them did the opposite of
what it says. A node whose ordinary attempts *and* whose judge rewrites are both
spent escalates; the operator presses "🔁 Retry the node"; the ladder is asked
again and returns `ESCALATE` a second time — because `_judge_rewrites_spent`
vetoes the attempt the grant just bought — and the caller's
second-ESCALATE-means-KILLED rule turns that into a kill. The operator pressed
retry and watched the node die.

What is wrong is not the cap's number. The cap bounds *judge-driven* retries —
rewrites the judge asked for — and it is correct for that. What it must not do
is veto an attempt the judge never asked for and an operator explicitly paid an
escalation to buy. So the fix is a distinction, not a wider number, and these
tests are written so that widening or deleting the cap fails them:

- **The reproduction needs the exact history, in the exact order** (plan trap 6).
  The debugger rung must already be spent, or the ladder answers `DEBUGGER` and
  never reaches the veto; and the *latest* record must carry `JudgeOutcome.RETRY`
  with the count of such records exceeding `max_judge_retries`, because
  `_judge_rewrites_spent` keys on `history[-1]`. A history where only the last
  record is a judge RETRY returns `RETRY` today and proves nothing. Every test
  here builds that history through one helper, and the helper asserts its own
  premise (`test_the_reproducing_history_is_the_one_that_reproduces`) so a later
  edit that quietly stops reproducing fails loudly instead of passing vacuously.
- **The control runs under a raised `max_attempts`** (plan trap 1). At the
  shipped defaults the attempt budget and the judge cap expire together
  (`factory/verify/ladder.py:17-22`), so the ladder leaves the retry path on
  `attempts_left` before the cap is ever consulted — a control at defaults passes
  with the cap deleted outright and tells a reviewer nothing. Under
  `max_attempts=5` the two come apart and the assertion can actually fail.
- **The grant is not made twice** (plan trap 3). `allowed` is
  `max_attempts + len(escalations)` and this story does not touch it: one press
  buys one attempt, two presses buy two, and the test that says so would fail if
  a second grant were added on top.

The measured decisions these assertions turn on — before and after the change —
are pasted at the bottom of this file, because the judge is given the diff and
nothing else (constitution VIII).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, AsyncIterator

import pytest
from temporalio.testing import WorkflowEnvironment

from factory.activities.notify_activities import DEFAULT_CHOICES
from factory.mergequeue.models import LandingConfig
from factory.notify.messages import escalation_actions, parse_callback_data
from factory.verify.ladder import (
    DEBUGGER_PERSONA,
    _attempts_spent,
    _judge_rewrites_spent,
    next_action,
)
from factory.verify.models import (
    AttemptRecord,
    EscalationChoice,
    EscalationRecord,
    JudgeOutcome,
    NextAction,
    OverallVerdict,
    VerificationConfig,
)
from factory.verify.store import EXPIRED
from factory.workgraph.models import NodeState

from tests.test_interpreter import (
    JUDGE_PERSONA,
    attempt_counts,
    judge_pass,
    judge_retry,
    one_node,
    run_epic,
    scored,
    scored_world,
    states,
)

WORKER = "implementer"

#: The shipped caps, and the config every operator-facing sentence is written
#: against: 3 attempts, 2 judge rewrites inside them, 1 debugger cycle.
DEFAULTS = VerificationConfig()

#: The same deployment with room left in the attempt budget. Only under a raised
#: `max_attempts` do the two caps come apart far enough for the judge cap to be
#: observable on its own (`factory/verify/ladder.py:17-22`), which is what makes
#: the control able to fail.
RAISED = VerificationConfig(max_attempts=5)

GRANTED = (EscalationChoice.RETRY,)


def attempt(
    number: int,
    *,
    persona: str = WORKER,
    judge: JudgeOutcome | None = None,
    verdict: OverallVerdict = OverallVerdict.FAIL,
) -> AttemptRecord:
    return AttemptRecord(
        attempt=number, persona=persona, verdict=verdict, judge_outcome=judge
    )


def exhausted_by_the_judge() -> list[AttemptRecord]:
    """The one history that reproduces the defect (plan trap 6).

    The debugger cycle comes *first* so that rung is already spent — with it
    last, and carrying no judge outcome of its own, `_judge_rewrites_spent` reads
    `history[-1].judge_outcome is None`, short-circuits to False, and the ladder
    returns `RETRY` before the veto is ever reached. Then three ordinary attempts
    that each carry a judge RETRY: the count has to *exceed* `max_judge_retries`,
    so two would not be enough.
    """
    return [
        attempt(1, persona=DEBUGGER_PERSONA),
        *(attempt(number, judge=JudgeOutcome.RETRY) for number in (2, 3, 4)),
    ]


# --- the premise ------------------------------------------------------------


def test_the_reproducing_history_is_the_one_that_reproduces() -> None:
    """The recipe, asserted rather than trusted.

    Every test below is only worth its assertion if this history is the one the
    defect lives in: the ordinary budget spent, the debugger rung spent, and the
    judge's rewrites spent. An edit that reorders the records — the exact mistake
    plan trap 6 records — turns the reproduction into a history that already
    passes, and this is what fails when it does.
    """
    history = exhausted_by_the_judge()

    assert _attempts_spent(history, DEFAULTS) == DEFAULTS.max_attempts
    assert _judge_rewrites_spent(history, DEFAULTS) is True
    assert history[-1].judge_outcome == JudgeOutcome.RETRY

    # And with nobody paged it is genuinely exhausted: the escalation the
    # operator answers below is one the ladder really did ask for.
    assert next_action(history, DEFAULTS) is NextAction.ESCALATE


# --- US1-S1: the press produces an attempt (T001, FR-001, FR-002) -----------


def test_a_retry_press_grants_an_attempt_the_judge_cap_used_to_veto() -> None:
    """The story's whole claim, in one pure call (US1-S1).

    `next_action` reads no clock, runs no command and touches no store, so the
    defect needs no Temporal to reproduce: history in, decision out. Before the
    change this returned `ESCALATE`, which the caller
    (`factory/workgraph/workflow.py:1568-1573`) converts into `KILLED` — the
    operator pressing "retry" was pressing "kill".
    """
    history = exhausted_by_the_judge()

    assert next_action(history, DEFAULTS, escalations=GRANTED) is NextAction.RETRY


# --- US1-S4: the control, both directions (T002, trap 1) --------------------


def test_the_grant_is_what_lifts_the_veto_and_nothing_else() -> None:
    """One history, two decisions, side by side (US1-S4).

    Under `max_attempts=5` the attempt budget is not what ends the retries — the
    judge cap is — so the two answers differ for the reason this story is about
    and not for an arithmetic reason. At the defaults both sides return the same
    thing whether the cap exists or not, which is why the control is written
    here and not there (plan trap 1).
    """
    history = exhausted_by_the_judge()

    granted = next_action(history, RAISED, escalations=GRANTED)
    ungranted = next_action(history, RAISED, escalations=())

    assert granted is NextAction.RETRY
    assert ungranted is not NextAction.RETRY
    assert ungranted is NextAction.ESCALATE


def test_the_judge_cap_still_bounds_the_retries_the_judge_asked_for() -> None:
    """FR-002's other half: the cap keeps doing its job (SC-002).

    The same ungranted history, decided under two caps. If this story had fixed
    the defect by deleting or widening `_judge_rewrites_spent`, the first
    assertion would return `RETRY` and fail — which is the point of writing the
    control under `max_attempts=5`, where the attempt budget cannot mask the
    answer.
    """
    history = exhausted_by_the_judge()

    bounded = VerificationConfig(max_attempts=5, max_judge_retries=2)
    unbounded = VerificationConfig(max_attempts=5, max_judge_retries=99)

    assert next_action(history, bounded) is NextAction.ESCALATE
    assert next_action(history, unbounded) is NextAction.RETRY


# --- US1-S2: the granted attempt actually dispatches (T003) -----------------


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    """Temporal with a clock the test owns — an hour of silence costs nothing."""
    environment = await WorkflowEnvironment.start_time_skipping()
    try:
        yield environment
    finally:
        await environment.shutdown()


async def test_the_press_dispatches_an_attempt_and_the_node_leaves_the_escalation(
    env: WorkflowEnvironment,
) -> None:
    """A returned value is not a dispatch; this asserts the node moved (US1-S2).

    The whole loop, for real, under the interpreter: three attempts the judge
    asks to rewrite, the debugger cycle (which asks for one more rewrite of its
    own, so the *latest* record carries a judge RETRY exactly as it does in
    production), the escalation, the press, and then a fifth attempt that
    dispatches under the node's own persona and lands.

    Before the change the press produced `ESCALATE` a second time, the caller
    killed the node, and the fifth attempt never ran: `us1` ended `KILLED` at
    four attempts. Note the ordering here is the *opposite* of the pure test's —
    the debugger runs last, as the ladder actually calls it — and it still
    reproduces, because the debugger's own attempt carries the judge outcome
    that keeps `_judge_rewrites_spent` looking at a RETRY.
    """
    script = scored_world(
        scored(judge_retry()),
        scored(judge_retry()),
        scored(judge_retry()),
        scored(judge_retry()),  # the debugger cycle, judged like any other
        scored(judge_pass()),  # the attempt the operator's press buys
        client=env.client,
        press=EscalationChoice.RETRY.value,
    )

    status = await run_epic(
        env,
        script,
        graph=one_node(),
        landing_config=LandingConfig(poll_interval_s=0),
    )

    # It left the escalation: the node is neither killed nor parked, and a fifth
    # attempt exists to have taken it there.
    assert states(status) == {"us1": NodeState.MERGED}
    assert attempt_counts(status) == {"us1": 5}
    assert [key.persona for key in script.key_requests if key.persona != JUDGE_PERSONA] == [
        WORKER,
        WORKER,
        WORKER,
        DEBUGGER_PERSONA,
        WORKER,
    ]

    # One escalation, answered with the grant — and the attempt that followed it
    # is a real dispatch with its own prompt, not a value a function returned.
    [escalation] = script.escalation_requests
    assert escalation.node_id == "us1"
    assert {str(choice) for choice in escalation.choices} == {
        "RETRY",
        "KILL",
        "PAUSE_EPIC",
        # 068-US2 (FR-008): ending the epic joined the menu as its own answer.
        "KILL_EPIC",
    }
    assert [context.attempt for context in script.attempts] == [1, 2, 3, 4, 5]
    assert len(script.prompts_for("us1")) == 5
    assert script.expirations == []
    assert "overrun" not in script.calls


# --- US1-S3: a second ESCALATE that no grant explains is still a kill (T004) -


async def test_a_kill_press_on_the_same_node_is_still_terminal(
    env: WorkflowEnvironment,
) -> None:
    """The button that says kill still kills (US1-S3, FR-004).

    The same exhausted-by-the-judge node, answered the other way. Nothing this
    story does to the retry path may let a killed node take one more attempt:
    the escalation is answered once, the node dies, and the fifth scripted
    attempt is never reached.
    """
    script = scored_world(
        scored(judge_retry()),
        scored(judge_retry()),
        scored(judge_retry()),
        scored(judge_retry()),
        scored(judge_pass()),  # scripted, and must never be dispatched
        client=env.client,
        press=EscalationChoice.KILL.value,
    )

    status = await run_epic(
        env,
        script,
        graph=one_node(),
        landing_config=LandingConfig(poll_interval_s=0),
    )

    assert states(status) == {"us1": NodeState.KILLED}
    assert attempt_counts(status) == {"us1": 4}
    assert [context.attempt for context in script.attempts] == [1, 2, 3, 4]
    assert len(script.escalation_requests) == 1


@pytest.mark.parametrize(
    ("resolution", "case"),
    [
        (EscalationChoice.KILL, "the operator killed it"),
        (EscalationChoice.PAUSE_EPIC, "the epic is paused; this node parks"),
        (EXPIRED, "an hour of silence, the fail-safe default"),
        ("resolved", "a resolution the ladder has never heard of"),
    ],
)
def test_only_a_grant_produces_more_work(
    resolution: EscalationChoice | str, case: str
) -> None:
    """Everything that is not a press of RETRY still ends the node (FR-004)."""
    history = exhausted_by_the_judge()

    assert (
        next_action(history, DEFAULTS, escalations=(resolution,)) is NextAction.KILLED
    ), case


def test_a_second_escalate_no_grant_explains_stays_an_escalate() -> None:
    """The case the caller's KILLED rule was written for (US1-S3, trap 2).

    A grant buys one attempt; it does not buy an unbounded number. A history
    that has already spent more than the grants allow — the shape a node reaches
    when an unanswered operator question appends its own FAIL record
    (`factory/workgraph/workflow.py:1485-1491`) on top of a spent budget —
    escalates again, and the caller is what turns that into a kill rather than
    paging the operator forever.
    """
    over_spent = [*exhausted_by_the_judge(), attempt(5), attempt(6)]

    assert next_action(over_spent, DEFAULTS, escalations=GRANTED) is NextAction.ESCALATE


def test_the_callers_second_escalate_rule_is_still_in_the_workflow() -> None:
    """`workflow.py:1568-1573` survives this story (FR-004, trap 2).

    Read off the source rather than asserted from behaviour, because after the
    fix a *grant* no longer reaches this branch — that is the fix. The rule is
    still needed for every other way a re-decision can come back `ESCALATE`
    (the test above builds one), and deleting it would page an operator forever
    instead of ending the node, which is a worse outage than the one being
    fixed.
    """
    workflow_source = (
        Path(__file__).resolve().parents[1] / "factory" / "workgraph" / "workflow.py"
    )
    tree = ast.parse(workflow_source.read_text())

    def tests_escalate(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "action"
            and isinstance(node.test.comparators[0], ast.Attribute)
            and node.test.comparators[0].attr == "ESCALATE"
        )

    def names_killed(node: ast.AST) -> bool:
        return any(
            isinstance(child, ast.Attribute)
            and child.attr == "KILLED"
            and isinstance(child.value, ast.Name)
            and child.value.id == "NextAction"
            for child in ast.walk(node)
        )

    outer = [node for node in ast.walk(tree) if tests_escalate(node)]
    nested = [
        inner
        for branch in outer
        for statement in branch.body
        for inner in ast.walk(statement)
        if tests_escalate(inner)
    ]

    assert nested, "the second-ESCALATE branch is gone from the interpreter"
    assert all(names_killed(branch) for branch in nested)


# --- US1-S5: one press, one attempt (T005, FR-003, trap 3) ------------------


def test_each_press_buys_exactly_one_attempt() -> None:
    """Two grants, two attempts — not four, and not an unbounded number (US1-S5).

    The grant lives at `factory/verify/ladder.py`'s `allowed` and this story does
    not add a second one. If it had — the remedy the defect report proposed, and
    what plan trap 3 forbids — a single press would buy two attempts and the
    `once` half below would answer `RETRY` where it answers `ESCALATE`.
    """
    history = exhausted_by_the_judge()
    fourth = [*history, attempt(5, judge=JudgeOutcome.RETRY)]
    fifth = [*fourth, attempt(6, judge=JudgeOutcome.RETRY)]

    twice = (EscalationChoice.RETRY, EscalationChoice.RETRY)
    assert next_action(history, DEFAULTS, escalations=twice) is NextAction.RETRY
    assert next_action(fourth, DEFAULTS, escalations=twice) is NextAction.RETRY
    assert next_action(fifth, DEFAULTS, escalations=twice) is NextAction.ESCALATE

    # One press stops exactly one attempt earlier than two do.
    assert next_action(history, DEFAULTS, escalations=GRANTED) is NextAction.RETRY
    assert next_action(fourth, DEFAULTS, escalations=GRANTED) is NextAction.ESCALATE


# --- US1-S6: the menu contains no no-op (T006, FR-005) ----------------------


def offered_choices() -> list[str]:
    """Exactly what the operator is offered, read back off the buttons.

    Taken from `escalation_actions` and decoded through `parse_callback_data`
    rather than from `DEFAULT_CHOICES` directly: what reaches the ladder is the
    payload a press carries back, so decoding it is what proves the button the
    operator sees and the resolution the ladder decides on are the same thing.
    """
    record = EscalationRecord(
        escalation_id="0123456789ab",
        workflow_id="escalation-0123456789ab",
        epic_id="068-an-escalation-offers-only-answers-that-work",
        node_id="us1",
        choices=list(DEFAULT_CHOICES),
        history_summary="attempt 4: judge RETRY (rewrites spent)",
        sent_at="2026-08-20T11:00:00Z",
        expires_at="2026-08-20T12:00:00Z",
        delivered=True,
    )
    decoded = []
    for action in escalation_actions(record):
        press = parse_callback_data(action.payload)
        assert press is not None, action.label
        assert action.label.strip(), "a button with no face is a button nobody presses"
        decoded.append(press.choice)
    return decoded


def test_every_offered_option_can_change_the_nodes_state() -> None:
    """The story's real claim: the menu must not contain a no-op (US1-S6, FR-005).

    Each button the escalation offers, against the action it produces on the very
    node it is offered for. An option that leaves the node in `ESCALATE` changes
    nothing an operator can see — the caller kills the node either way — so it is
    a button whose label is a lie. Before this story, "🔁 Retry the node" was one.
    """
    history = exhausted_by_the_judge()
    offered = offered_choices()

    # 068-US2 added `KILL_EPIC` (FR-008): ending the node and ending the epic
    # became two answers rather than one. It is a non-grant, so the ladder ends
    # the node on it exactly as it does on KILL — the epic-level half is the
    # interpreter's, and `tests/test_killed_node_leaves_a_resettable_epic.py`
    # is where the two are held apart.
    assert offered == ["RETRY", "KILL", "PAUSE_EPIC", "KILL_EPIC"]

    decided = {
        choice: next_action(history, DEFAULTS, escalations=(choice,))
        for choice in offered
    }

    assert NextAction.ESCALATE not in decided.values(), decided
    assert decided == {
        "RETRY": NextAction.RETRY,
        "KILL": NextAction.KILLED,
        "PAUSE_EPIC": NextAction.KILLED,
        "KILL_EPIC": NextAction.KILLED,
    }
    # The retry button and the kill button must not be the same button.
    assert decided["RETRY"] is not decided["KILL"]


# --- measured, not described (constitution VIII) ----------------------------
#
# The decisions this file turns on, executed rather than reasoned about. The
# history is `exhausted_by_the_judge()`; `G = (EscalationChoice.RETRY,)`.
#
#   uv run python -c "
#   from factory.verify.ladder import next_action, _judge_rewrites_spent, _attempts_spent, DEBUGGER_PERSONA
#   from factory.verify.models import AttemptRecord, EscalationChoice, JudgeOutcome, VerificationConfig, OverallVerdict
#   def a(n, persona='implementer', judge=None):
#       return AttemptRecord(attempt=n, persona=persona, verdict=OverallVerdict.FAIL, judge_outcome=judge)
#   h=[a(1,DEBUGGER_PERSONA)]+[a(n,judge=JudgeOutcome.RETRY) for n in (2,3,4)]
#   D=VerificationConfig(); R=VerificationConfig(max_attempts=5); U=VerificationConfig(max_attempts=5,max_judge_retries=99)
#   G=(EscalationChoice.RETRY,)
#   print('spent', _attempts_spent(h,D), ' judge rewrites spent', _judge_rewrites_spent(h,D))
#   print('defaults, escalations=(RETRY,)          ->', repr(next_action(h,D,escalations=G)))
#   print('defaults, escalations=()                ->', repr(next_action(h,D)))
#   print('max_attempts=5, escalations=(RETRY,)    ->', repr(next_action(h,R,escalations=G)))
#   print('max_attempts=5, escalations=()          ->', repr(next_action(h,R)))
#   print('max_judge_retries=99, escalations=()    ->', repr(next_action(h,U)))
#   print('over-spent history, escalations=(RETRY,)->', repr(next_action(h+[a(5),a(6)],D,escalations=G)))
#   "
#
# BEFORE (the tree at the commit that added this file, ladder unchanged):
#
#   spent 3  judge rewrites spent True
#   defaults, escalations=(RETRY,)          -> <NextAction.ESCALATE: 'ESCALATE'>   <- the defect
#   defaults, escalations=()                -> <NextAction.ESCALATE: 'ESCALATE'>
#   max_attempts=5, escalations=(RETRY,)    -> <NextAction.ESCALATE: 'ESCALATE'>   <- the defect
#   max_attempts=5, escalations=()          -> <NextAction.ESCALATE: 'ESCALATE'>
#   max_judge_retries=99, escalations=()    -> <NextAction.RETRY: 'RETRY'>
#   over-spent history, escalations=(RETRY,)-> <NextAction.ESCALATE: 'ESCALATE'>
#
# AFTER (`_judge_vetoes_a_retry` in `factory/verify/ladder.py`):
#
#   spent 3  judge rewrites spent True
#   defaults, escalations=(RETRY,)          -> <NextAction.RETRY: 'RETRY'>         <- FR-001
#   defaults, escalations=()                -> <NextAction.ESCALATE: 'ESCALATE'>
#   max_attempts=5, escalations=(RETRY,)    -> <NextAction.RETRY: 'RETRY'>         <- US1-S4
#   max_attempts=5, escalations=()          -> <NextAction.ESCALATE: 'ESCALATE'>   <- US1-S4 control
#   max_judge_retries=99, escalations=()    -> <NextAction.RETRY: 'RETRY'>         <- the cap still bites
#   over-spent history, escalations=(RETRY,)-> <NextAction.ESCALATE: 'ESCALATE'>   <- FR-004
#
# And the control can fail, which is the only thing that makes it a control
# (SC-002, plan trap 1). `_judge_rewrites_spent` mutated to `return False` — the
# cap deleted outright — then reverted:
#
#   env -u TELEGRAM_BOT_TOKEN -u TELEGRAM_CHAT_ID FACTORY_ROOT="$(mktemp -d)" \
#     uv run pytest tests/test_escalation_grant_survives_the_judge_cap.py -q \
#     -k "still_bounds or lifts_the_veto"
#
#   >       assert ungranted is not NextAction.RETRY
#   E       AssertionError: assert <NextAction.RETRY: 'RETRY'> is not <NextAction.RETRY: 'RETRY'>
#   >       assert next_action(history, bounded) is NextAction.ESCALATE
#   E       AssertionError: assert <NextAction.RETRY: 'RETRY'> is <NextAction.ESCALATE: 'ESCALATE'>
#   FAILED ...::test_the_grant_is_what_lifts_the_veto_and_nothing_else
#   FAILED ...::test_the_judge_cap_still_bounds_the_retries_the_judge_asked_for
#   2 failed, 12 deselected in 0.12s
#
# The same mutation at the *defaults* changes nothing at all — `attempts_left` is
# already False, so the ladder leaves the retry path before the cap is consulted.
# That is why every line above that carries a verdict about the cap is written
# under `max_attempts=5`.
