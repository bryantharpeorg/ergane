"""A moved base costs a rebase, not an attempt.

069-US1. A node passes its ladder, opens a landing, and joins the queue. A
sibling lands first. The queue rejects the node's tree — not because the tree is
wrong, but because the world it was built for no longer exists. Today that
rejection is charged, and it is charged **twice**, from two independent budgets:

- `factory/workgraph/workflow.py` increments `Landing.recovery_cycles`, whose
  shipped bound is **one**; and
- `_recovery_attempt` ends by appending an `AttemptRecord` to `record.history`,
  which `factory/verify/ladder.py` counts — as an ordinary attempt after a clean
  sync, or as the single shipped debugger cycle after a conflicted one.

So a defect-free node in a three-way fan-out is dead after its siblings land: it
runs out of recovery cycles, or of attempts, whichever comes first. Freeing one
of the two leaves it dying of the other, which is why every assertion in this
file that says "unchanged" says it about **all three** counts at once.

What these tests are written to resist:

- **Charging nothing is not the fix.** `test_a_failing_check_on_an_unmoved_base_is_still_charged`
  and `test_a_conflicted_rebase_is_still_the_debuggers_cycle` are the controls
  (plan trap 1), and they assert *both* budgets. A control that watched one
  budget would only cover the one whoever wrote it happened to think about, and
  a diff that stopped charging rejections outright would pass it.
- **Stopping cheaply is not the fix either.** US1-S2: the free path has to end
  with the tree back in the queue, so the requeue is asserted directly rather
  than inferred from an unspent budget.
- **The free path is bounded** (plan trap 3, FR-004). Work moved off a budget
  and left unbounded converts a bounded expensive failure into an unbounded
  cheap one. `test_the_free_rebase_path_is_bounded` asserts the limit, and
  `test_a_bound_of_zero_charges_the_first_moved_base_rejection` asserts the
  bound is really the thing deciding.
- **Cause, not wording, and not a retry count** (plan trap 2, FR-005).
  `rejection_cause` takes three parameters and none of them is a message or a
  count; `test_the_classifier_cannot_see_a_message_or_a_count` holds it to that
  by signature, and the classification tests run over two structurally distinct
  moved-base causes and one code-fault cause.
- **The identical-tree refusal survives** (plan trap 4, FR-006). A free rebase
  that changed nothing must not re-offer the tree the queue just refused, and
  `test_a_free_rebase_that_changes_nothing_does_not_requeue` puts the existing
  refusal on the new path.
- **The fact has to exist in production.** A classifier that reads a field no
  forge ever fills is green in the suite and inert in the world — the "fully
  green run shipped a command that could not start" failure. `test_the_forge_reports_the_base_the_queue_is_testing`
  checks the `gh` field set and the payload reader that fill it.

The measured before/after readings these assertions turn on are pasted at the
bottom of this file, because the judge is given the diff and nothing else
(constitution VIII).
"""

from __future__ import annotations

import inspect
from dataclasses import replace
from typing import Any, AsyncIterator

import pytest
from temporalio.testing import WorkflowEnvironment

from factory.mergequeue.gh import _VIEW_FIELDS
from factory.mergequeue.models import (
    LandingConfig,
    LandingState,
    PrSnapshot,
    QueueOutcome,
    RejectionCause,
)
from factory.mergequeue.rejection import rejection_cause
from factory.verify.ladder import (
    DEBUGGER_PERSONA,
    _attempts_spent,
    _debugger_cycles_spent,
)
from factory.verify.models import EscalationChoice, VerificationConfig
from factory.workgraph.models import NodeState

from tests.test_interpreter import (
    ScriptedWorld,
    checks_failed_snapshot,
    conflict_snapshot,
    merged_snapshot,
    one_node,
    passing,
    run_epic,
    states,
)

#: The head the harness's `prepare_worktree` pins every node to — the base every
#: landing in this file is offered against.
NODE_BASE = "9" * 40

#: The head the target branch is at once a sibling has landed. Different from
#: `NODE_BASE`, which is the entire fact: the world moved.
SIBLING_LANDED = "5" * 40

#: And the heads after the sibling after that. Repeated moved-base rejections
#: need a *new* head each time, because a requeue records the base it was
#: re-offered against: re-using one head would make the second rejection compare
#: equal and classify as the node's own fault, and a bound test written that way
#: passes with the bound deleted. Measured — that is exactly what the first
#: draft of `test_the_free_rebase_path_is_bounded` did.
ANOTHER_LANDED = "7" * 40
A_THIRD_LANDED = "8" * 40

#: The caps the ladder is read under. Passed explicitly on every call, because
#: `_attempts_spent` takes `config` and excludes the promotion persona when one
#: is configured — reading it without the config measures the pre-070/US5
#: behaviour and would pass for the wrong reason.
LADDER = VerificationConfig()


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    """Temporal with a clock the test owns — a poll interval costs nothing."""
    environment = await WorkflowEnvironment.start_time_skipping()
    try:
        yield environment
    finally:
        await environment.shutdown()


# --- reading the two budgets --------------------------------------------------


def spend(status: Any, node_id: str = "us1") -> tuple[int, int, int]:
    """The three counts a rejection can move, read as one tuple.

    `(ladder attempts, ladder debugger cycles, landing recovery cycles)`. They
    are read together and asserted together on purpose: there are two budgets on
    this path, and a test that reads one of them cannot tell a node that stopped
    being charged from a node that is still being charged somewhere else.
    """
    node = status.nodes[node_id]
    return (
        _attempts_spent(node.history, LADDER),
        _debugger_cycles_spent(node.history),
        node.recovery_cycles,
    )


def moved_base_checks_failed(base: str = SIBLING_LANDED) -> PrSnapshot:
    """A required check failed after something landed under the enqueued tree.

    The first of the two moved-base causes: the base the forge reports is not
    the base the tree was offered against, so the checks that failed ran against
    a world this node was never shown. `base` is which head landed, and a test
    scripting several rejections has to advance it — see `ANOTHER_LANDED`.
    """
    return replace(checks_failed_snapshot(), base_sha=base)


def unmoved_base_checks_failed() -> PrSnapshot:
    """A required check failed on exactly the base the tree was built on.

    The control. Nothing landed in between; the queue tested what the node
    offered, against the world the node offered it for, and refused it.
    """
    return replace(checks_failed_snapshot(), base_sha=NODE_BASE)


def moved_base_conflict() -> PrSnapshot:
    """The target moved under the proposal and it no longer applies.

    The second moved-base cause, and structurally a different one: the forge
    observed it, and no base comparison is involved — this snapshot's base is
    the very one the tree was offered against.
    """
    return replace(conflict_snapshot(), base_sha=NODE_BASE)


# --- the premise --------------------------------------------------------------


async def test_one_clean_landing_spends_one_attempt_and_no_recovery(
    env: WorkflowEnvironment,
) -> None:
    """The baseline every "unchanged" below is measured against.

    A node that passes once and merges once has spent one ordinary attempt, no
    debugger cycle and no recovery cycle. Without this stated, "unchanged" is a
    claim about a number nobody has established.
    """
    script = ScriptedWorld({"us1": [passing()]}, client=env.client)
    script.script_landing("us1", merged_snapshot())

    status = await run_epic(env, script, graph=one_node())

    assert states(status) == {"us1": NodeState.MERGED}
    assert spend(status) == (1, 0, 0)


# --- US1-S1: all three counts are unchanged -----------------------------------


async def test_a_moved_base_rejection_spends_neither_budget(
    env: WorkflowEnvironment,
) -> None:
    """US1-S1 / FR-001: a check that failed under a base that moved costs nothing.

    All three counts asserted directly, and all three matter: `recovery_cycles`
    is bounded at one, so a node charged there dies on its first unlucky
    sibling; the ladder's attempt count is bounded at three, so a node charged
    there dies on its third. The reproduction is a node that spends *neither*.
    """
    script = ScriptedWorld({"us1": [passing()]}, client=env.client)
    script.script_landing("us1", moved_base_checks_failed(), merged_snapshot())
    script.script_sync("us1", clean=True, base_ref=SIBLING_LANDED)

    status = await run_epic(env, script, graph=one_node())

    assert states(status) == {"us1": NodeState.MERGED}
    assert status.nodes["us1"].rejection_cause == RejectionCause.BASE_MOVED
    # The whole story, in three numbers: identical to a landing that was never
    # rejected at all.
    assert spend(status) == (1, 0, 0)
    # And the free path is what did it — one rebase, taken off its own bound.
    assert status.nodes["us1"].free_rebases == 1


async def test_a_moved_target_rejection_spends_neither_budget(
    env: WorkflowEnvironment,
) -> None:
    """US1-S1 over the *other* moved-base cause: the forge-observed conflict.

    The queue said the target moved under this proposal. Our own rebase merges
    it cleanly — so the node's tree was never the problem, and nothing is
    charged. Note the snapshot's base is `NODE_BASE`: this cause does not go
    through the base comparison at all, which is what makes it a second cause
    rather than a second spelling of the first.
    """
    script = ScriptedWorld({"us1": [passing()]}, client=env.client)
    script.script_landing("us1", moved_base_conflict(), merged_snapshot())
    script.script_sync("us1", clean=True, base_ref=SIBLING_LANDED)

    status = await run_epic(env, script, graph=one_node())

    assert states(status) == {"us1": NodeState.MERGED}
    assert status.nodes["us1"].rejection_cause == RejectionCause.BASE_MOVED
    assert spend(status) == (1, 0, 0)


# --- US1-S2: it rebases and requeues ------------------------------------------


async def test_the_free_path_rebases_and_puts_the_tree_back_in_the_queue(
    env: WorkflowEnvironment,
) -> None:
    """US1-S2 / FR-002: a node that stops cheaply is not a fix.

    Spending nothing is only half of it — the tree has to end up back on the
    queue. So this asserts the rebase ran, the same PR was enqueued a second
    time, and the landing rode that second ride to MERGED. And it asserts what
    did *not* happen: no second key was issued, because no agent ran. A key per
    attempt is the attribution primitive (constitution V), so exactly one key
    for a node that ran exactly one attempt is the same fact from the other
    side.
    """
    script = ScriptedWorld({"us1": [passing()]}, client=env.client)
    pr_number = script.script_landing(
        "us1", moved_base_checks_failed(), merged_snapshot()
    )
    script.script_sync("us1", clean=True, base_ref=SIBLING_LANDED)

    status = await run_epic(env, script, graph=one_node())

    # It rebased.
    assert [s.node_id for s in script.sync_requests] == ["us1"]
    # It requeued — the same PR, a second time.
    assert [r.pr_number for r in script.enqueue_requests] == [pr_number, pr_number]
    assert states(status) == {"us1": NodeState.MERGED}
    assert status.nodes["us1"].landing_state == LandingState.MERGED
    # And it ran no agent to get there: one attempt, one key, one teardown.
    assert status.nodes["us1"].attempt == 1
    assert len(script.key_requests) == 1
    assert len(script.teardowns) == 1


# --- US1-S3: the controls -----------------------------------------------------


async def test_a_failing_check_on_an_unmoved_base_is_still_charged(
    env: WorkflowEnvironment,
) -> None:
    """US1-S3 / FR-003: the node's own tree is wrong, and it pays for it — twice.

    The same rejection as US1-S1 in every respect but the one that matters: the
    base the forge reports is the base the tree was built on, so nothing landed
    under it and the failing check is about the tree. Both budgets move, exactly
    as they did before this story — `recovery_cycles` to one, and a second
    `AttemptRecord` for the ladder to count.
    """
    script = ScriptedWorld({"us1": [passing(), passing()]}, client=env.client)
    script.script_landing("us1", unmoved_base_checks_failed(), merged_snapshot())
    script.script_sync("us1", clean=True, base_ref=NODE_BASE)

    status = await run_epic(env, script, graph=one_node())

    assert states(status) == {"us1": NodeState.MERGED}
    assert status.nodes["us1"].rejection_cause == RejectionCause.NODE_CODE
    # Charged on both: a second ordinary attempt, and the one recovery cycle.
    assert spend(status) == (2, 0, 1)
    assert status.nodes["us1"].free_rebases == 0
    # An agent really did run again — the charge is for work, not for nothing.
    assert len(script.key_requests) == 2


async def test_a_conflicted_rebase_is_still_the_debuggers_cycle(
    env: WorkflowEnvironment,
) -> None:
    """US1-S3's other half: the debugger budget is still charged where it should be.

    The queue observed a moved target *and* the rebase collides — the node's own
    work and what landed touch the same lines. That is not "only a moved base"
    (FR-001's word): reconciling them is work, an agent does it, and the
    debugger cycle it spends is the shipped budget of exactly one. Without this
    control, a diff could route every CONFLICT to the free path and never charge
    the debugger at all, and the attempt-count control above would not notice.
    """
    script = ScriptedWorld({"us1": [passing(), passing()]}, client=env.client)
    script.script_landing("us1", moved_base_conflict(), merged_snapshot())
    script.script_sync(
        "us1", clean=False, base_ref=SIBLING_LANDED, conflicted_files=("src/calc.py",)
    )

    status = await run_epic(env, script, graph=one_node())

    assert states(status) == {"us1": NodeState.MERGED}
    # Classified as a moved base — and still charged, because the rebase collided.
    assert status.nodes["us1"].rejection_cause == RejectionCause.BASE_MOVED
    # The debugger cycle moved, and the ordinary attempt budget did not: the
    # debugger's rung is its own (`factory/verify/ladder.py`).
    assert spend(status) == (1, 1, 1)
    assert status.nodes["us1"].free_rebases == 0
    assert [k.persona for k in script.key_requests][-1] == DEBUGGER_PERSONA


# --- US1-S4: the identical-tree refusal survives ------------------------------


async def test_a_free_rebase_that_changes_nothing_does_not_requeue(
    env: WorkflowEnvironment,
) -> None:
    """US1-S4 / FR-006: the existing futility refusal still fires, on the new path.

    A rebase that produces the tree the queue already rejected has nothing new
    to offer it, and re-offering it burns a CI run to be told the same thing.
    The refusal predates this story; what this asserts is that the free path
    goes through it rather than around it — the free route is the one where
    skipping it would be cheapest and therefore most tempting.
    """
    script = ScriptedWorld({"us1": [passing()]}, client=env.client)
    pr_number = script.script_landing(
        "us1", moved_base_checks_failed(), merged_snapshot()
    )
    script.script_sync("us1", clean=True, base_ref=SIBLING_LANDED)
    script.script_tree_comparison("us1", identical=True)

    status = await run_epic(env, script, graph=one_node())

    # The comparison ran, and the second enqueue did not.
    assert len(script.compare_trees_requests) == 1
    assert [r.pr_number for r in script.enqueue_requests] == [pr_number]
    assert states(status) == {"us1": NodeState.KILLED}
    # A human was asked, and the reason quoted was the futility.
    assert len(script.escalation_requests) == 1
    summary = script.escalation_requests[0].history_summary.lower()
    assert "identical" in summary
    assert "tree" in summary


# --- US1-S5: the free path is bounded -----------------------------------------


async def test_the_free_rebase_path_is_bounded(
    env: WorkflowEnvironment,
) -> None:
    """US1-S5 / FR-004: siblings landing forever do not buy rebases forever.

    With the bound at one, two moved-base rejections in a row get one free
    rebase and then one charged recovery — the node re-enters the budgets it
    always had rather than rebasing without end. Unbounding the free path leaves
    the second rejection free too, and this assertion fails on both numbers it
    names; that mutation is pasted at the bottom of the file.

    The second rejection reports a *different* head, because the requeue records
    the base it was re-offered against. Reporting the same head twice would make
    the second rejection compare equal, classify as the node's own fault, and
    charge it for a reason that has nothing to do with the bound.
    """
    script = ScriptedWorld({"us1": [passing(), passing()]}, client=env.client)
    script.script_landing(
        "us1",
        moved_base_checks_failed(SIBLING_LANDED),
        moved_base_checks_failed(ANOTHER_LANDED),
        merged_snapshot(),
    )
    script.script_sync("us1", clean=True, base_ref=SIBLING_LANDED)

    status = await run_epic(
        env,
        script,
        graph=one_node(),
        landing_config=LandingConfig(max_free_rebases=1),
    )

    assert states(status) == {"us1": NodeState.MERGED}
    # Exactly one rebase was free; the second rejection was charged on both.
    assert status.nodes["us1"].free_rebases == 1
    assert spend(status) == (2, 0, 1)


async def test_a_bound_of_zero_charges_the_first_moved_base_rejection(
    env: WorkflowEnvironment,
) -> None:
    """US1-S5's control: the bound is what decides, not the classification.

    Same rejection, same classification, bound set to zero — and the node is
    charged exactly as it was before this story. That is what makes
    `max_free_rebases` a bound rather than a comment: turn it to nothing and the
    behaviour it governs disappears.
    """
    script = ScriptedWorld({"us1": [passing(), passing()]}, client=env.client)
    script.script_landing("us1", moved_base_checks_failed(), merged_snapshot())
    script.script_sync("us1", clean=True, base_ref=SIBLING_LANDED)

    status = await run_epic(
        env,
        script,
        graph=one_node(),
        landing_config=LandingConfig(max_free_rebases=0),
    )

    assert states(status) == {"us1": NodeState.MERGED}
    assert status.nodes["us1"].rejection_cause == RejectionCause.BASE_MOVED
    assert status.nodes["us1"].free_rebases == 0
    assert spend(status) == (2, 0, 1)


async def test_a_node_whose_siblings_land_forever_eventually_stops(
    env: WorkflowEnvironment,
) -> None:
    """US1-S5's other half, and the reason FR-004 exists at all.

    Moved-base rejections without end, and the node still reaches a terminal: one
    free rebase, then the ordinary charged recovery it always had, then the
    escalation that ends it. An unbounded free path would ride this queue for as
    long as siblings keep landing and never page anybody — a bounded expensive
    failure converted into an unbounded cheap one, which is the shape 067's US2
    trap named and this is the same trap.
    """
    script = ScriptedWorld({"us1": [passing(), passing()]}, client=env.client)
    script.script_landing(
        "us1",
        moved_base_checks_failed(SIBLING_LANDED),
        moved_base_checks_failed(ANOTHER_LANDED),
        moved_base_checks_failed(A_THIRD_LANDED),
    )
    script.script_sync("us1", clean=True, base_ref=SIBLING_LANDED)

    status = await run_epic(
        env,
        script,
        graph=one_node(),
        landing_config=LandingConfig(max_free_rebases=1, max_recovery_cycles=1),
    )

    # It stopped, and a human was told rather than left to notice.
    assert states(status) == {"us1": NodeState.KILLED}
    assert len(script.escalation_requests) == 1
    assert script.escalation_requests[0].choices == [
        EscalationChoice.RETRY,
        EscalationChoice.KILL,
        EscalationChoice.PAUSE_EPIC,
    ]
    # And it stopped at the bounds it was given: one free rebase, one charged
    # recovery, and no third of either.
    assert status.nodes["us1"].free_rebases == 1
    assert spend(status) == (2, 0, 1)


# --- US1-S6: classified by cause ----------------------------------------------


def test_a_forge_observed_conflict_is_a_moved_base() -> None:
    """The first moved-base cause: the target moved under the proposal.

    No base comparison takes part — the bases here are equal, and the answer is
    still BASE_MOVED. `in_conflict` is the factory's own vocabulary for "the
    target has moved under this proposal", translated at the boundary from
    whatever the forge spells it, so this reads a fact rather than a phrase.
    """
    assert (
        rejection_cause(
            QueueOutcome.CONFLICT,
            enqueued_base=NODE_BASE,
            observed_base=NODE_BASE,
        )
        is RejectionCause.BASE_MOVED
    )


def test_a_base_that_advanced_under_an_enqueued_tree_is_a_moved_base() -> None:
    """The second, structurally distinct: two shas that differ.

    No conflict is involved. The checks that failed ran against a base the node
    was never shown, which is a different observation from the one above and
    reaches the same verdict by a different route.
    """
    assert (
        rejection_cause(
            QueueOutcome.CHECKS_FAILED,
            enqueued_base=NODE_BASE,
            observed_base=SIBLING_LANDED,
        )
        is RejectionCause.BASE_MOVED
    )


def test_a_failing_check_on_the_base_it_was_built_on_is_the_nodes_own() -> None:
    """The code-fault cause. The queue tested what was offered and refused it."""
    assert (
        rejection_cause(
            QueueOutcome.CHECKS_FAILED,
            enqueued_base=NODE_BASE,
            observed_base=NODE_BASE,
        )
        is RejectionCause.NODE_CODE
    )


@pytest.mark.parametrize(
    "enqueued_base, observed_base",
    [(None, SIBLING_LANDED), (NODE_BASE, None), (None, None)],
)
def test_an_unread_base_is_charged_rather_than_guessed_about(
    enqueued_base: str | None, observed_base: str | None
) -> None:
    """An absent reading is not evidence of stillness.

    A pre-069 landing replaying, or a forge that reports no base, must be
    charged exactly as it was before this module existed. The free path is
    opt-in on a fact actually observed, never on the absence of one — the other
    way round, every rejection anyone forgot to wire up would become free.
    """
    assert (
        rejection_cause(
            QueueOutcome.CHECKS_FAILED,
            enqueued_base=enqueued_base,
            observed_base=observed_base,
        )
        is RejectionCause.NODE_CODE
    )


def test_the_classifier_cannot_see_a_message_or_a_count() -> None:
    """FR-005, held by signature rather than by intention (plan trap 2).

    A classifier keyed on the forge's rejection wording breaks the first time
    GitHub rewords something, and it breaks silently — it goes on classifying,
    just wrongly. One keyed on a retry count kills a defect-free node on its
    second unlucky sibling and gives a broken one a free ride on its first.
    Neither is reachable from here, because neither is a parameter: the whole
    input is one outcome and two shas.
    """
    parameters = list(inspect.signature(rejection_cause).parameters)
    assert parameters == ["outcome", "enqueued_base", "observed_base"]


def test_the_forge_wording_does_not_change_the_answer() -> None:
    """Two forges, two spellings, one cause.

    GitHub says `DIRTY`; the modelled forge in `tests/fake_forge.py` says
    nothing at all and sets the fact directly. Both arrive at the classifier as
    `QueueOutcome.CONFLICT` and both are a moved base. A string match on
    `merge_state_status` would agree with the first and miss the second.
    """
    githubs = PrSnapshot(
        state="OPEN",
        is_draft=False,
        auto_merge_requested=False,
        merge_state_status="DIRTY",
        merged_at=None,
        closed_at=None,
        failing_required_checks=(),
        observed_at="2026-08-19T10:00:00Z",
    )
    another = replace(githubs, merge_state_status="", in_conflict=True)

    assert githubs.in_conflict is True
    assert another.in_conflict is True
    assert githubs.merge_state_status != another.merge_state_status
    causes = {
        rejection_cause(
            QueueOutcome.CONFLICT, enqueued_base=NODE_BASE, observed_base=NODE_BASE
        )
        for _ in (githubs, another)
    }
    assert causes == {RejectionCause.BASE_MOVED}


def test_the_forge_reports_the_base_the_queue_is_testing() -> None:
    """The production wiring, because a fact nobody fills classifies nothing.

    `base_sha` is the whole of the second cause, and it arrives from one place:
    `gh pr view --json baseRefOid`, read by `PrSnapshot.from_gh_json`. Ask for
    the wrong field set and every rejection in production reads as the node's
    own fault while this file stays green — a suite proving a path that cannot
    run.
    """
    assert "baseRefOid" in _VIEW_FIELDS.split(",")

    observed = PrSnapshot.from_gh_json(
        {
            "state": "OPEN",
            "isDraft": False,
            "mergeStateStatus": "BLOCKED",
            "baseRefOid": SIBLING_LANDED,
            "statusCheckRollup": [],
        },
        observed_at="2026-08-19T10:00:00Z",
    )
    assert observed.base_sha == SIBLING_LANDED

    # And a payload without it is "unknown", not "unmoved" — the reading the
    # classifier charges rather than guesses about.
    silent = PrSnapshot.from_gh_json(
        {"state": "OPEN", "statusCheckRollup": []},
        observed_at="2026-08-19T10:00:00Z",
    )
    assert silent.base_sha is None


# --- measured evidence (constitution VIII) ------------------------------------
#
# Four rejections run end to end through the interpreter, printing
# `spend(status)` — `(ladder attempts, ladder debugger cycles, recovery cycles)`
# — plus the classification and the number of virtual keys issued. BEFORE is the
# behaviour at 399fa7d, reproduced exactly by neutralising `rejection_cause` to
# return `NODE_CODE` unconditionally (which is what the tree did before this
# story existed), then reverted:
#
#   moved base, checks failed          spend=(2, 0, 1)  cause=NODE_CODE  free_rebases=0  keys=2
#   moved target, clean rebase         spend=(2, 0, 1)  cause=NODE_CODE  free_rebases=0  keys=2
#   unmoved base, checks failed        spend=(2, 0, 1)  cause=NODE_CODE  free_rebases=0  keys=2
#   moved target, rebase collides      spend=(1, 1, 1)  cause=NODE_CODE  free_rebases=0  keys=2
#
# Every rejection costs one of one recovery cycle *and* one of three attempts
# (or the one debugger cycle). A node in a three-way fan-out reaches its second
# sibling with no recovery cycle left.
#
# AFTER, same four:
#
#   moved base, checks failed          spend=(1, 0, 0)  cause=BASE_MOVED  free_rebases=1  keys=1
#   moved target, clean rebase         spend=(1, 0, 0)  cause=BASE_MOVED  free_rebases=1  keys=1
#   unmoved base, checks failed        spend=(2, 0, 1)  cause=NODE_CODE   free_rebases=0  keys=2
#   moved target, rebase collides      spend=(1, 1, 1)  cause=BASE_MOVED  free_rebases=0  keys=2
#
# Rows 1 and 2 are FR-001 and FR-002: nothing spent, one fewer key issued
# because no agent ran, and the tree back on the queue. Rows 3 and 4 are FR-003:
# unchanged, on both budgets.
#
#   $ FACTORY_ROOT="$(mktemp -d)" uv run pytest \
#       tests/test_moved_base_is_not_charged.py -q
#   19 passed in 2.57s
#
# The controls can fail, which is the only thing that makes them controls
# (SC-002, plan trap 1). Three mutations, each applied and reverted:
#
# 1. `rejection_cause` returning `BASE_MOVED` unconditionally — every rejection
#    free. Measured, the third row above becomes
#    `spend=(1, 0, 0)  cause=BASE_MOVED  free_rebases=1  keys=1`:
#
#   >       assert status.nodes["us1"].rejection_cause == RejectionCause.NODE_CODE
#   E       AssertionError: assert <RejectionCau... 'BASE_MOVED'> == <RejectionCau...: 'NODE_CODE'>
#   FAILED ...::test_a_failing_check_on_an_unmoved_base_is_still_charged
#   1 failed, 1 passed, 17 deselected in 0.64s
#
# 2. The conflicted-rebase fallback (`if free and not sync.clean`) deleted, so a
#    CONFLICT is free even when reconciling it is real work:
#
#   >       assert spend(status) == (1, 1, 1)
#   E       assert (1, 0, 0) == (1, 1, 1)
#   E         At index 1 diff: 0 != 1
#   FAILED ...::test_a_conflicted_rebase_is_still_the_debuggers_cycle
#   1 failed, 18 deselected in 0.41s
#
#    Note that mutation 1 leaves this control green and mutation 2 leaves the
#    other one green. Neither budget's control covers the other's, which is why
#    both are here.
#
# 3. The bound (`landing.free_rebases < config.max_free_rebases`) deleted:
#
#   >       assert status.nodes["us1"].free_rebases == 1
#   E       AssertionError: assert 2 == 1
#   >       assert status.nodes["us1"].free_rebases == 0
#   E       AssertionError: assert 1 == 0
#   >       assert states(status) == {"us1": NodeState.KILLED}
#   E       AssertionError: assert {'us1': <Node...ED: 'MERGED'>} == {'us1': <Node...ED: 'KILLED'>}
#   FAILED ...::test_the_free_rebase_path_is_bounded
#   FAILED ...::test_a_bound_of_zero_charges_the_first_moved_base_rejection
#   FAILED ...::test_a_node_whose_siblings_land_forever_eventually_stops
#   3 failed, 16 deselected in 0.93s
#
#    The first draft of `test_the_free_rebase_path_is_bounded` **passed** under
#    this mutation, and finding that is why it is written the way it is now: it
#    scripted the same moved head for both rejections, so the requeue recorded
#    that head as the new `enqueued_base` and the second rejection classified as
#    the node's own fault. It charged, the assertion held, and the bound it
#    claimed to test was never consulted. Advancing the head per rejection is
#    what makes the second rejection actually reach the bound.
#
# 4. And the identical-tree refusal (FR-006, plan trap 4) — `if identical:` in
#    `_reenqueue` deleted, so the free path re-offers a tree the queue already
#    rejected:
#
#   >       assert [r.pr_number for r in script.enqueue_requests] == [pr_number]
#   E       assert [486, 486] == [486]
#   E         Left contains one more item: 486
#   FAILED ...::test_a_free_rebase_that_changes_nothing_does_not_requeue
#   1 failed, 18 deselected in 0.42s
