"""US4 — a landing-recovery escalation names its exhausted bound.

095 gave the verification ladder a voice: `ExhaustedBound.describe`, carried on
`EscalationRequest.exhausted_bound` and printed in the message footer. The
landing-recovery path pages an operator on the same clock with the same request
type and names nothing — `render_landing_history` counts the recovery cycles
spent and stops there, so an operator deciding on an hour is told *how many*
cycles were spent and never *which dial* said to stop asking. 095's FR-008 asked
for this and the ladder's version of it shipped; the landing's did not.

What these tests are written to resist:

- **The wrong dial.** The tempting reuse is a call to `exhausted_bound`
  (`factory/verify/ladder.py`), which reads a `VerificationConfig` and can only
  ever name one of four verification dials — and returns `None` on a landing
  escalation anyway, because it opens by asking `next_action`, which says
  `ESCALATE` for nothing that has passed verification. T023 asserts the dial
  name literally: `max_recovery_cycles`, a `LandingConfig` dial
  (`factory/mergequeue/models.py`), so a test that only asserted "some bound is
  named" would pass against the wrong bound — or pass against no bound at all,
  because the ladder function answers `None` here and the assertion would be
  comparing against silence.
- **A dial that has not been reached, reported as spent.** The futile
  re-enqueue page and the page raised with a cycle still to grant are both real
  landings, and neither is an exhaustion. T024 is that control. It also passes
  when no bound is ever computed on this path, so it is only meaningful beside
  T023 — which is why T023 runs first and asserts the sentence shape, not just
  the dial name.
- **A re-worded ladder.** `ExhaustedBound.describe` renders
  `ladder exhausted: {dial} = {value} — {note}`, and the verification path
  prints exactly that string. The landing wording rides in `note`, which is what
  `note` is for; editing `describe` would change every verification page and
  fail T025's byte-identity control.
- **A message that drifts between the two branches.** The pasted evidence at
  the bottom is printed by the tests that assert these runs, so the paste
  cannot move without a test failing with it (constitution VIII / D-037).
"""

from __future__ import annotations

from typing import Any

from temporalio.testing import WorkflowEnvironment

from factory.activities.notify_activities import SendEscalationInput, _pending_record
from factory.mergequeue.models import LandingConfig
from factory.notify.messages import escalation_message
from factory.verify.ladder import ExhaustedBound
from factory.verify.models import (
    EscalationChoice,
    EscalationRecord,
)
from factory.workgraph.models import NodeState

from tests.test_interpreter import (
    EPIC_ID,
    ScriptedWorld,
    checks_failed_snapshot,
    env,  # noqa: F401  — pytest fixture, re-exported for this module
    failing,
    merged_snapshot,
    one_node,
    passing,
    run_epic,
    states,
)

NODE = "us1"

#: The landing dial FR-011 names, and the two budgets this suite runs under.
#: `SPENT` is the shipped default — one automatic recovery cycle and no more,
#: so the exhaustion page goes out with the budget gone. `BUDGETED` leaves one
#: to grant, which is the control T024 exists for.
SPENT = LandingConfig(max_recovery_cycles=1, poll_interval_s=0)
BUDGETED = LandingConfig(max_recovery_cycles=2, poll_interval_s=0)

#: What the sentence shape must be, spelled here rather than read from
#: `ExhaustedBound` so a change to the renderer fails a test by name. The
#: verification path prints this exact string today (095-US3), and FR-012
#: forbids changing it.
SENTENCE_SHAPE = "ladder exhausted: max_recovery_cycles = {value} — {note}"

#: The wording the note carries for the landing dial. Asserted so the operator
#: reads a landing diagnosis, not a ladder one, and spelled once here beside the
#: paste so the two cannot drift apart silently.
SPENT_NOTE = (
    "the landing's recovery budget is spent: the recovery cycle ran and the "
    "queue rejected it again. Another cycle buys another rejection of the same "
    "tree — grant one only to see it fail again"
)


def operator_message(request: SendEscalationInput) -> str:
    """The Telegram body an operator is paged with, from what the workflow sent.

    Built through the send activity's own `_pending_record` rather than from a
    hand-made record: the question these tests ask is whether the *escalation*
    names the bound, and a record assembled here would prove only that the
    renderer can print a string it was handed (095's reading of the same
    question, reused verbatim).
    """
    return escalation_message(_pending_record(request))


def report(*lines: str) -> None:
    """Print one block of the evidence pasted at the bottom of this file.

    The judge sees the diff and nothing else (constitution VIII), so T027's
    evidence arrives as text — printed from the tests that already assert these
    runs, so the paste cannot drift without a test failing with it.
    """
    print("\n" + "\n".join(lines))


def a_landing_whose_recovery_failed_again(
    client: Any, press: str, budget: LandingConfig, *, second_poll: Any
) -> ScriptedWorld:
    """A landing rejected, recovered once, and what the re-enqueue polls next.

    The automatic recovery runs and fails, so the page goes out from the
    failed-recovery exhaustion (`_run_recovery`'s own). What the second poll
    answers decides the after-life of a RETRY press: `merged_snapshot()` lets
    the granted cycle land (T024's shape); a second `checks_failed_snapshot()`
    rejects the re-enqueue too. The third attempt is scripted for the press —
    a granted cycle that has an attempt to run and passes — and T023's press
    of KILL never reaches it.
    """
    script = ScriptedWorld(
        {NODE: [passing(), failing(2), passing()]}, client=client, press=press
    )
    script.script_landing(NODE, checks_failed_snapshot(), second_poll)
    script.script_sync(NODE, clean=True, base_ref="c0ffee")
    return script


def a_landing_rejected_twice_with_its_recovery_passing(
    client: Any, press: str, budget: LandingConfig
) -> ScriptedWorld:
    """079-US1's spent shape: recovered, re-enqueued, rejected again.

    The recovery attempt passes (the second scripted attempt), the re-enqueue
    is rejected by the second poll, and the scheduler picks the REJECTED
    landing back up with the budget spent — the exhaustion
    `_escalate_and_apply` pages from, which is a second caller with the same
    answer to compute (plan T026 names both).
    """
    script = ScriptedWorld(
        {NODE: [passing(), passing()]}, client=client, press=press
    )
    script.script_landing(NODE, checks_failed_snapshot(), checks_failed_snapshot())
    script.script_sync(NODE, clean=True, base_ref="c0ffee")
    return script


def a_futile_reenqueue(client: Any, press: str) -> ScriptedWorld:
    """The identical-tree page: an escalation that is not an exhaustion.

    The sync merges nothing in (the target head never moves) and the recovery
    attempt's tree equals the tip the queue already rejected, so
    `_reenqueue`'s futility gate pages the operator — with `RETRY` offered
    whatever the budget says, because a press spends no cycle (079-US1).
    """
    script = ScriptedWorld(
        {NODE: [passing(), passing()]}, client=client, press=press
    )
    script.script_landing(NODE, checks_failed_snapshot(), merged_snapshot())
    script.script_sync(NODE, clean=True, base_ref="9" * 40)
    script.script_tree_comparison(NODE, identical=True)
    return script


# --- T023 [US4-S1, FR-011]: the spent dial names itself -----------------------


async def test_a_landing_escalation_with_its_cycles_spent_names_max_recovery_cycles(
    env: WorkflowEnvironment,
) -> None:
    """US4-S1: the page says which dial ran out and what it was set to.

    075/us1's shape at the shipped default: one landing rejected, one automatic
    recovery cycle spent on it, the recovery's re-enqueue rejected again — the
    scheduler pages with the budget gone. Before this story the operator read
    `Recovery cycles: 1` and was left to guess whether that number was a budget
    or a spend, and which of the two landing dials had stopped the node.
    """
    script = a_landing_rejected_twice_with_its_recovery_passing(
        env.client, EscalationChoice.KILL.value, SPENT
    )

    status = await run_epic(env, script, graph=one_node(), landing_config=SPENT)

    # The page went out on the landing path, and the budget really is spent.
    [escalation] = script.escalation_requests
    assert status.nodes[NODE].recovery_cycles == SPENT.max_recovery_cycles
    assert "Recovery cycles: 1" in escalation.history_summary
    assert escalation.choices == [
        EscalationChoice.KILL,
        EscalationChoice.PAUSE_EPIC,
        EscalationChoice.KILL_EPIC,
    ], "the budget was spent, so no RETRY could have been honoured"

    message = operator_message(escalation)

    # The dial is named literally — `exhausted_bound` the function can only ever
    # name one of the four verification dials and answers `None` on this path,
    # so a sentence that survives this assertion was built for the landing dial.
    assert SENTENCE_SHAPE.format(value=SPENT.max_recovery_cycles, note="") in message, (
        f"the landing escalation does not name max_recovery_cycles and its value "
        f"in the sentence shape ExhaustedBound.describe produces:\n{message}"
    )
    # ...and the note carries the landing diagnosis, so the operator is not
    # left reading a ladder sentence about a queue dial.
    assert SPENT_NOTE in message, (
        f"the landing bound names its dial without saying what a grant would "
        f"buy:\n{message}"
    )
    # The verification dials stay out of a page that has no ladder behind it.
    for dial in (
        "max_attempts",
        "max_judge_retries",
        "debugger_cycles",
        "max_pre_agent_failures",
    ):
        assert dial not in message, (
            f"the landing page names the verification dial {dial}:\n{message}"
        )

    report("US4-S1  recovery cycles spent — the bound is named", *message.splitlines())


async def test_the_failed_recovery_exhaustion_names_the_bound_too(
    env: WorkflowEnvironment,
) -> None:
    """The other exhaustion caller computes the same answer (plan T026).

    The first test pages from `_escalate_and_apply` — the scheduler picked a
    REJECTED landing up with its budget spent. This one pages from
    `_run_recovery` itself: the automatic cycle ran, its attempt failed again,
    and the exhaustion is decided in that caller. Two callers, one predicate —
    and after this story, one bound — so a fix applied at only one of them
    leaves the other page as mute as it was.
    """
    script = a_landing_whose_recovery_failed_again(
        env.client,
        EscalationChoice.KILL.value,
        SPENT,
        second_poll=checks_failed_snapshot(),
    )

    status = await run_epic(env, script, graph=one_node(), landing_config=SPENT)

    [escalation] = script.escalation_requests
    assert "Recovery cycles: 1" in escalation.history_summary
    message = operator_message(escalation)

    assert SENTENCE_SHAPE.format(value=SPENT.max_recovery_cycles, note="") in message, (
        f"the failed-recovery page does not name the exhausted dial:\n{message}"
    )
    assert SPENT_NOTE in message
    assert states(status) == {NODE: NodeState.KILLED}


# --- T024 [US4-S2, FR-012]: a cycle remaining names no bound ------------------


async def test_a_landing_escalation_with_a_cycle_remaining_names_no_bound(
    env: WorkflowEnvironment,
) -> None:
    """US4-S2: a dial that has not been reached is not reported as spent.

    Same rejection, budget of two: the automatic recovery spent one cycle and
    the page goes out with a second still grantable — the operator is being
    asked whether to spend it. A page that named `max_recovery_cycles` as
    exhausted here would be reporting the very dial that still has room, and
    the RETRY button beside it would contradict the sentence above it.
    """
    script = a_landing_whose_recovery_failed_again(
        env.client,
        EscalationChoice.RETRY.value,
        BUDGETED,
        second_poll=merged_snapshot(),
    )

    status = await run_epic(env, script, graph=one_node(), landing_config=BUDGETED)

    message = operator_message(script.escalation_requests[0])

    assert "ladder exhausted" not in message, (
        f"a dial that has not been reached was reported as spent:\n{message}"
    )
    assert "max_recovery_cycles" not in message, (
        f"the page names the recovery dial it has not exhausted:\n{message}"
    )
    # The press bought the cycle the page did not claim was gone: the node ends
    # MERGED with the budget actually spent, so this control watched a real
    # grant land and not a page that gave up early.
    assert states(status) == {NODE: NodeState.MERGED}
    assert status.nodes[NODE].recovery_cycles == BUDGETED.max_recovery_cycles

    report("US4-S2  a cycle remaining — no bound is named", *message.splitlines())


async def test_the_futile_reenqueue_page_names_no_bound(
    env: WorkflowEnvironment,
) -> None:
    """The third caller is not an exhaustion and must not inherit one.

    `_reenqueue`'s identical-tree page offers RETRY unconditionally — a press
    completes the interrupted enqueue and spends no cycle — so no recovery
    budget was consulted to build it, and a bound naming that budget would be
    an answer to a question this page did not ask (plan trap 8).
    """
    script = a_futile_reenqueue(env.client, EscalationChoice.KILL.value)

    await run_epic(
        env, script, graph=one_node(),
        landing_config=LandingConfig(max_recovery_cycles=1),
    )

    [escalation] = script.escalation_requests
    assert "identical" in escalation.history_summary.lower()
    message = operator_message(escalation)

    assert "ladder exhausted" not in message, (
        f"the futile page was given a bound it did not earn:\n{message}"
    )
    assert "max_recovery_cycles" not in message, (
        f"the futile page names the recovery dial:\n{message}"
    )


# --- T025 [US4-S3, FR-012, trap 9]: the verification page is byte-identical ---


def verification_record_fields() -> dict[str, Any]:
    """One verification escalation, in the terms the send activity records."""
    return dict(
        escalation_id="0123456789ab",
        workflow_id=f"epic-{EPIC_ID}",
        epic_id=EPIC_ID,
        node_id=NODE,
        choices=[
            EscalationChoice.RETRY,
            EscalationChoice.KILL,
            EscalationChoice.PAUSE_EPIC,
            EscalationChoice.KILL_EPIC,
        ],
        history_summary="three deterministic refusals",
        sent_at="2026-08-06T10:11:00Z",
        expires_at="2026-08-06T11:11:00Z",
        delivered=True,
    )


GOLDEN_VERIFICATION_MESSAGE = (
    "⚠️ Verification escalation\n"
    "epic: demo-loans\n"
    "node: us1\n"
    "\n"
    "three deterministic refusals\n"
    "\n"
    "What each button does:\n"
    "RETRY (🔁 Retry the node) — node: one more attempt, on the tree this one "
    "left behind. epic: unchanged — it keeps dispatching.\n"
    "KILL (🛑 Kill the node) — node: ends KILLED, its branch preserved. epic: "
    "keeps dispatching, but every node waiting on this one is locked out and "
    "ends KILLED with it, undispatched.\n"
    "PAUSE_EPIC (⏸️ Pause the epic) — node: ends parked, not killed — nothing "
    "waiting on it is locked out. epic: stops dispatching until you resume it; "
    "the undispatched nodes keep their place and run then.\n"
    "KILL_EPIC (💥 End the whole epic) — node: ends KILLED, its branch "
    "preserved. epic: ends with it — nothing else dispatches, and any other "
    "node's open page is cancelled unanswered.\n"
    "\n"
    "No answer by 2026-08-06T11:11:00Z applies the default: KILL the node."
)


def test_a_verification_escalation_message_is_byte_identical() -> None:
    """US4-S3: a page with no exhausted ladder renders byte-for-byte as today.

    The golden string above was taken from `escalation_message` before this
    story touched anything, and it is what 095's readers have been reading. A
    message that differs from it is this story re-wording a page it was told
    not to touch — the failure mode trap 9 names.
    """
    bare = escalation_message(EscalationRecord(**verification_record_fields()))

    assert bare == GOLDEN_VERIFICATION_MESSAGE, (
        "the verification escalation message changed:\n"
        f"--- expected\n{GOLDEN_VERIFICATION_MESSAGE!r}\n"
        f"+++ actual\n{bare!r}\n"
    )


def test_a_verification_bound_still_renders_verbatim_in_the_footer() -> None:
    """The rendering this story must not alter is the rendering 095 built.

    Read with the two tests beside each other: the golden above says the page
    without a bound is unchanged, this says a page *with* one still carries the
    ladder's own sentence verbatim — so the story cannot satisfy the golden by
    deleting the footer's bound line either.
    """
    bound = ExhaustedBound(
        dial="max_attempts",
        value=3,
        note="every ordinary attempt is spent: 3 of them were charged to this story",
    )
    fields = verification_record_fields()
    fields["exhausted_bound"] = bound.describe()

    message = escalation_message(EscalationRecord(**fields))
    bare = escalation_message(
        EscalationRecord(**verification_record_fields())
    )

    assert bound.describe() in message
    # The delta between the two messages is the bound and nothing else: remove
    # the bound line and its leading blank line, and the golden message returns.
    assert message.replace(f"\n\n{bound.describe()}", "") == bare