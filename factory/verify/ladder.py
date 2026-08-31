"""What happens after an attempt fails — one pure decision over the history.

The retry policy is a function, not a shape in the interpreter's workflow body,
because constitution IV puts retry and routing decisions in deterministic code
and because a policy spread through workflow code cannot be tested without
Temporal or changed without a workflow migration. Everything the ladder needs is
in its arguments: the attempts that have run, the caps this deployment set, and
whatever an operator has already answered. It reads no clock, runs no command,
and touches no store — the module imports nothing that could (R9).

The rules it encodes (FR-006, FR-007, FR-008), and the readings that are not
obvious from the caps alone:

- **Only the latest attempt decides a PASS.** A history is not scored best-of:
  an earlier green attempt never rescues the failure after it, because a
  downstream edge unlocks on the state of the worktree now (FR-005).
- **Judge-driven retries are bounded inside the attempt total, never on top of
  it** (SC-003). Under the defaults the two caps expire together, so the
  distinction only shows under a config that raises `max_attempts`: once the
  judge has spent its rewrites, a further judge-RETRY stops granting attempts
  even with budget left. The cap binds on judge-driven failures only — a gate
  failure is not judge spend, so it still retries on the ordinary budget, and
  neither is an attempt an operator granted (068 FR-002): a cap on what the
  judge may ask for cannot bound what a human asked for, and applying it to a
  press left the escalation offering a button that could only kill the node.
- **The debugger cycle is a rung, not an attempt.** It runs once the ordinary
  budget is gone and is limited by `debugger_cycles` alone, so an escalation that
  grants more attempts never calls it back for a second turn.
- **Escalation resolutions arrive as an argument, not as history.** A button
  press is not an attempt; it is a fact about attempts *allowed*. It rides in a
  keyword-only sequence defaulting to empty so that `next_action(history, config)`
  — data-model.md's signature — stays the call for every decision made before
  anyone was paged. Each `RETRY` grants exactly one more attempt; a second grant
  takes a second escalation. A grant also settles which regime the ladder is in:
  once a human has answered, the retries are theirs and not the judge's, so the
  rewrite cap stops applying (068 FR-002) while the attempt total still bounds
  them.
- **Nothing but an explicit grant produces more work.** `KILL`, `KILL_EPIC`, the store's
  `EXPIRED` timeout value, `PAUSE_EPIC`, and any resolution this module has never
  heard of all end the node, and they outrank a trailing PASS. That asymmetry is
  deliberate: losing work an operator killed is recoverable (the branch and
  worktree are preserved by the lifecycle owner), unlocking a downstream edge
  after they killed it is not.

`PAUSE_EPIC` ends the node here for the same reason: parking it is the most a
per-node decision can say about an epic-level suspension, and the interpreter
that owns releasing nodes is what distinguishes a park from a kill — and, since
068 FR-008, a killed node from a killed epic.

079-US1 adds the other half. The ladder has always decided what a resolution
*does*; now it also decides what may be *offered*, because the two answers have
to come from one place or the offer starts advertising decisions this module
will not make. `offered_choices` is that computation, pure like everything else
here: a node's remaining budget in, a keyboard out. The vocabulary stays 068's
four, and the ending choices are the floor every offer stands on (FR-003).

095-US3 adds the third answer of the same kind. This module has always known
*which* of its bounds ran out — it is the branch that produced `ESCALATE` — and
has always thrown that away, so an exhausted node reached the operator as one
word for three very different endings. `exhausted_bound` reports it, beside the
decision rather than beneath a reader: a bound worked out a second time in a
renderer is a copy of the precedence below, living where nothing keeps it
honest, and it starts lying the day a bound moves (095 plan trap 5). What it
reports is a reading, never a decision — `next_action` is untouched, and the
function refuses to name anything for a history the ladder has not escalated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from factory.verify.models import (
    AttemptRecord,
    EscalationChoice,
    JudgeOutcome,
    NextAction,
    OverallVerdict,
    VerificationConfig,
)

#: The one persona the ladder recognises by name — a registry entry, never a
#: model (constitution VII). Every other persona is ordinary node work, so the
#: debugger's attempt can join the history without spending the attempt budget.
DEBUGGER_PERSONA = "debugger"

#: The role constant for the optional promotion rung.  The actual persona name
#: is operator-configured; this constant is only used as a placeholder when no name
#: has been configured.  It must not collide with any real registry name.
PROMOTION_PERSONA = "__promotion__"

#: Every choice that ends the node, in the order the buttons render — and so
#: every choice executable on any node at any moment, because ending spends no
#: budget (079-US1, FR-003). `KILL_EPIC` is last for 068-US2's reason: it is the
#: one press no other press undoes.
ENDING_CHOICES: tuple[EscalationChoice, ...] = (
    EscalationChoice.KILL,
    EscalationChoice.PAUSE_EPIC,
    EscalationChoice.KILL_EPIC,
)

#: What the store writes into `resolution` when the hour ran out and nobody
#: pressed anything — `factory.verify.store.EXPIRED`, spelled here rather than
#: imported because this module touches no store (R9). Offered by nobody, and it
#: must go on ending the node, which is why `is_unoffered` exempts it by name
#: rather than by omission (079 trap 4).
EXPIRED_RESOLUTION = "EXPIRED"

#: The actions that put a node back to work. Membership only — never iterated —
#: so a frozenset cannot make a workflow replay differently.
_PRODUCES_WORK = frozenset(
    {NextAction.RETRY, NextAction.PROMOTE, NextAction.DEBUGGER}
)


def offered_choices(*, retry_grants_work: bool) -> list[EscalationChoice]:
    """What one escalation may offer, given what its node can still do (FR-001).

    The offer used to be a module constant handed over whole at both escalation
    sites, so an operator was shown "🔁 Retry the node" on a node with nothing
    left to retry with. Pressing it recorded a press, delivered a signal, found
    no grant and tore the node down — a kill wearing a retry label (075/us1 at
    03:18Z on 2026-08-21).

    `retry_grants_work` is the caller's answer to one question: if the operator
    presses retry, will this node be put back to work? A parameter rather than
    computed here, because the two sites read different budgets — the ladder's
    attempts, the landing's recovery cycles — and only the site knows which.

    The ending choices are always offered: they need no budget, and an empty
    keyboard is a park with no exit (FR-003).
    """
    if retry_grants_work:
        return [EscalationChoice.RETRY, *ENDING_CHOICES]
    return list(ENDING_CHOICES)


def grant_produces_work(
    history: Sequence[AttemptRecord],
    config: VerificationConfig,
    escalations: Sequence[EscalationChoice | str] = (),
) -> bool:
    """Whether one more granted attempt would put this node back to work (FR-002).

    Asked of the ladder itself rather than recomputed beside it: the answer has
    to be the one `next_action` will give when the press arrives, and two
    implementations of one budget is how an offer starts lying. Asking in the
    ladder's own terms — decide again with one more grant on the end — makes the
    offer honest by construction. False for a node whose escalations already
    carry an answer that ended it: no grant survives that.
    """
    return (
        next_action(
            history,
            config,
            escalations=[*escalations, EscalationChoice.RETRY],
        )
        in _PRODUCES_WORK
    )


def is_unoffered(
    resolution: EscalationChoice | str,
    offered: Sequence[EscalationChoice | str],
) -> bool:
    """Whether a resolution names a choice this escalation never offered (FR-004).

    A stale message, a replayed callback, a row written by something that had no
    business writing it: none is an answer, and applying one as the node's kill
    is what the interpreter's fall-through used to do.

    `EXPIRED` is exempt: the store's timeout value rather than a button, offered
    by nobody, and it must keep ending the node — separating the two cases
    explicitly is the whole of trap 4.

    An empty `offered` is exempt for a different reason: nothing was ever put in
    front of an operator, so no resolution can contradict an offer. What arrives
    then is the workflow's own fail-safe, and refusing it would leave a node
    nothing can end.
    """
    if str(resolution) == EXPIRED_RESOLUTION:
        return False
    if not offered:
        return False
    return str(resolution) not in {str(choice) for choice in offered}


def next_action(
    history: Sequence[AttemptRecord],
    config: VerificationConfig,
    *,
    escalations: Sequence[EscalationChoice | str] = (),
) -> NextAction:
    """Decide what the node does next, given everything that has happened to it.

    `history` is every attempt recorded for this node, oldest first, the debugger
    cycle included. `escalations` is the resolution of each escalation already
    answered, in order — absent for every decision made before an operator was
    paged.

    Enum-valued fields are compared by value rather than identity throughout: an
    `AttemptRecord` that crossed a Temporal payload boundary carries the enum's
    string, and a comparison that only recognised the member would read a
    serialized PASS as a failure.
    """
    if any(_ends_the_node(resolution) for resolution in escalations):
        return NextAction.KILLED

    if history and history[-1].verdict == OverallVerdict.PASS:
        return NextAction.PASSED

    # Every resolution that survived the check above is a grant, and each buys
    # exactly one attempt (contracts/verification-flow.md). This is the only
    # grant there is: adding a second one here would make one press buy two
    # attempts (068 FR-003).
    grants = len(escalations)
    allowed = config.max_attempts + grants
    attempts_left = _attempts_spent(history, config) < allowed

    # 095-US2 (FR-006): a pre-agent failure is not a rung, so it does not spend
    # the attempt budget — which means `attempts_left` above is True even when a
    # run of pre-agent failures has gone on forever. An exclusion without a
    # bound of its own is a starvation bug (plan trap 2), so a run of
    # consecutive pre-agent failures escalates on its own dial, through the same
    # escalate path as every other exhausted bound, rather than retrying a dead
    # credential forever. Checked before the grant because the grant's own
    # `allowed` never sees pre-agent failures.
    if pre_agent_bound_spent(history, config, grants):
        return NextAction.ESCALATE

    if attempts_left and not _judge_vetoes_a_retry(history, config, grants):
        return NextAction.RETRY

    if _promotion_available(history, config):
        return NextAction.PROMOTE

    if _debugger_cycles_spent(history) < config.debugger_cycles:
        return NextAction.DEBUGGER

    return NextAction.ESCALATE


@dataclass(frozen=True)
class ExhaustedBound:
    """Which of the ladder's bounds ended a node, and what it was set to.

    `dial` is the name the bound is *declared* under — the key in a target
    repo's `factory.yaml` `ladder:` block and the field on `VerificationConfig`
    — so the sentence an operator reads in an escalation names the thing they
    would edit. `value` is that declaration's value, not the effective ceiling a
    grant may have raised; `note` carries the difference when there is one,
    because "max_attempts = 3" beside a node that ran five attempts is a reading
    an operator would rightly distrust.

    `describe` is the whole of the rendering. It lives here rather than in the
    message renderer because a renderer that formatted `dial` and `value` for
    itself would be a second place that has to change when a bound changes, and
    the two would disagree in silence (095 plan trap 5).
    """

    dial: str
    value: int
    note: str

    def describe(self) -> str:
        """The one line the operator reads: which bound ran out, and its value."""
        return f"ladder exhausted: {self.dial} = {self.value} — {self.note}"


def exhausted_bound(
    history: Sequence[AttemptRecord],
    config: VerificationConfig,
    *,
    escalations: Sequence[EscalationChoice | str] = (),
) -> ExhaustedBound | None:
    """Which bound produced this node's `ESCALATE`, or `None` if it has not (FR-008).

    Asked of the ladder for the reason `grant_produces_work` is: the answer has
    to be the one `next_action` actually gave, and two readings of one budget is
    how an operator-facing line starts lying. It opens by *asking the decision*
    rather than by inspecting the history, so a history with somewhere left to go
    can never be described as exhausted, whatever the counts say.

    Below that, the branches read in the order `next_action` reaches them, and
    they name the rung the node **stopped on** — which is the one an operator's
    next move turns on:

    - **The pre-agent bound** short-circuits first and means no rung ran at all:
      a dead credential, and more attempts buy nothing until it is fixed.
    - **The debugger's cycles**, when that rung is configured and spent. It is
      the last rung the ladder has, so it is the ending even though the ordinary
      attempts were spent before it — granting more attempts does not buy
      another cycle.
    - **`max_judge_retries`**, when attempts remain and were not granted. This is
      the shadowing the spec was written for: the node stopped with budget in
      hand, and raising `max_attempts` — the dial with the obvious name — buys
      nothing.
    - **`max_attempts`** otherwise: the ordinary budget, genuinely spent.

    The promotion rung is deliberately not one of the names. It runs only after
    the ordinary attempts are gone, so a node that exhausts it also reports
    `max_attempts` truthfully, and the spec asks for the three bounds an
    operator's dials actually move.
    """
    if next_action(history, config, escalations=escalations) != NextAction.ESCALATE:
        return None

    grants = len(escalations)
    granted = f", plus {grants} granted by escalation" if grants else ""

    if pre_agent_bound_spent(history, config, grants):
        return ExhaustedBound(
            dial="max_pre_agent_failures",
            value=config.max_pre_agent_failures,
            note=(
                f"{pre_agent_failures_spent(history)} consecutive attempts ended "
                "before the agent produced a token, so no rung of the ladder ever "
                f"ran{granted}. Re-authenticate on the worker host; another "
                "attempt buys nothing until that is done"
            ),
        )

    if config.debugger_cycles and _debugger_cycles_spent(history) >= config.debugger_cycles:
        return ExhaustedBound(
            dial="debugger_cycles",
            value=config.debugger_cycles,
            note=(
                "the debugger rung is the last one the ladder has, and its cycles "
                "are spent. It is bounded on its own dial, so granting more "
                "attempts does not buy another cycle"
            ),
        )

    if _attempts_spent(history, config) < config.max_attempts + grants:
        return ExhaustedBound(
            dial="max_judge_retries",
            value=config.max_judge_retries,
            note=(
                "the judge has asked for more rewrites than this dial allows, and "
                f"{config.max_attempts + grants - _attempts_spent(history, config)} "
                f"of max_attempts = {config.max_attempts}{granted} are unspent. "
                "Raising max_attempts alone will not lengthen this fight"
            ),
        )

    return ExhaustedBound(
        dial="max_attempts",
        value=config.max_attempts,
        note=(
            "every ordinary attempt is spent: "
            f"{_attempts_spent(history, config)} of them were charged to this "
            f"story{granted}"
        ),
    )


def _ends_the_node(resolution: EscalationChoice | str) -> bool:
    """Whether an operator's answer was anything other than "try again".

    Stated as "not a grant" rather than as a list of terminal values on purpose:
    `EXPIRED` is written by the timeout path and not by any button, and a
    resolution nobody here has heard of is a wiring bug. Both must stop the node
    rather than fall through to another attempt.
    """
    return resolution != EscalationChoice.RETRY


def _attempts_spent(
    history: Sequence[AttemptRecord], config: VerificationConfig | None = None
) -> int:
    """How much of the ordinary attempt budget this node has consumed.

    Records, not attempt numbers: the number keys the evidence-store row and the
    component-1 attribution key, and a node whose numbering continues from
    elsewhere still gets its full budget. The debugger's cycle is excluded — it
    is a rung of its own, limited by `debugger_cycles`.  A promoted attempt is
    also excluded when a promotion persona is configured, because it belongs to
    its own rung (US5-S5).  A pre-agent failure is excluded too (095-US2,
    FR-005): the agent never started, so it is not a rung at all — the same
    argument as the debugger's, from the other end. The exclusion is a property
    of the record (`AttemptRecord.pre_agent`), not of the config, so it applies
    even where `config` is None (plan trap 4).
    """
    promotion_target = config.promotion_persona if config is not None else None
    excluded = {DEBUGGER_PERSONA, promotion_target} if promotion_target else {DEBUGGER_PERSONA}
    return sum(
        1
        for record in history
        if record.persona not in excluded and not record.pre_agent
    )


def pre_agent_failures_spent(history: Sequence[AttemptRecord]) -> int:
    """How many *consecutive* pre-agent failures end the history.

    Consecutive, not cumulative: a real attempt breaks the run, because a real
    attempt is the story being attempted and the credential is no longer the
    thing standing in the way. The count is the length of the unbroken tail of
    pre-agent failures, which is what `max_pre_agent_failures` bounds.
    """
    count = 0
    for record in reversed(history):
        if record.pre_agent:
            count += 1
        else:
            break
    return count


def pre_agent_bound_spent(
    history: Sequence[AttemptRecord],
    config: VerificationConfig,
    grants: int = 0,
) -> bool:
    """Whether the consecutive pre-agent bound is spent (095-US2, FR-006).

    A grant lifts the bound by one, the way it lifts `max_attempts`: a press of
    RETRY buys one more attempt, pre-agent or real, so the operator can keep
    saying "try again" past the bound exactly as they can past the attempt
    budget. The bound is the ladder's own ceiling on *unprompted* retries of a
    dead credential.
    """
    return pre_agent_failures_spent(history) >= config.max_pre_agent_failures + grants


def _debugger_cycles_spent(history: Sequence[AttemptRecord]) -> int:
    """How many debugger cycles have already run."""
    return sum(1 for record in history if record.persona == DEBUGGER_PERSONA)


def _promotion_cycles_spent(
    history: Sequence[AttemptRecord], config: VerificationConfig
) -> int:
    """How many promotion cycles have already run.

    A promoted attempt is recorded under the configured promotion persona, so it
    is counted by matching that persona name.  When no persona is configured we
    fall back to the synthetic placeholder, which never appears in real history.
    """
    target = config.promotion_persona or PROMOTION_PERSONA
    return sum(1 for record in history if record.persona == target)


def _promotion_available(
    history: Sequence[AttemptRecord], config: VerificationConfig
) -> bool:
    """Whether the promotion rung is configured and still has budget.

    The rung fires only when ordinary attempts are exhausted, it is configured
    with a persona, and the latest failing attempt was not already made by that
    persona — promoting to the same builder again would be a plain retry, not a
    stronger one (US5 edge case).
    """
    if config.promotion_persona is None:
        return False
    if config.promotion_cycles == 0:
        return False
    if _attempts_spent(history, config) < config.max_attempts:
        # Ordinary attempts still remain; the promotion rung sits above them.
        return False
    # Never promote when the latest failure is already the stronger persona:
    # that would be a plain retry, not a promotion.
    latest = history[-1] if history else None
    if latest is not None and latest.persona == config.promotion_persona:
        return False
    if _promotion_cycles_spent(history, config) >= config.promotion_cycles:
        return False
    return True


def _judge_vetoes_a_retry(
    history: Sequence[AttemptRecord], config: VerificationConfig, grants: int
) -> bool:
    """Whether the rewrite cap may stop the attempt the ladder is about to grant.

    A distinction, not a wider number (068 FR-002). `max_judge_retries` bounds
    *judge-driven* retries — the ladder granting itself another attempt because
    the judge asked for another rewrite. An operator pressing RETRY on an
    escalation is not the judge, and the attempt they bought is not a rewrite
    anybody asked for, so the cap has no standing over it. Applying it anyway is
    what made the retry button page the operator a second time and then kill the
    node they had just asked to try again.

    What bounds the granted attempts instead is `allowed` in `next_action`: one
    attempt per press, and the operator is paged again when those run out. So
    lifting the cap here cannot loop — it hands the decision back to the human
    already holding it. With nobody paged (`grants == 0`) this is exactly the cap
    as it has always been, which is the whole of the judge-driven regime.
    """
    if grants:
        return False
    return _judge_rewrites_spent(history, config)


def _judge_rewrites_spent(
    history: Sequence[AttemptRecord], config: VerificationConfig
) -> bool:
    """Whether the judge has run out of rewrites to ask for (SC-003).

    Only the latest failure is tested, because the cap bounds *judge-driven*
    retries: an exhausted judge budget must not shorten the node's attempts over
    a gate failure the judge had no part in. Granting a retry now would be the
    n-th rewrite the judge asked for, so the budget is spent once that count
    exceeds the cap.
    """
    latest = history[-1] if history else None
    if latest is None or latest.judge_outcome != JudgeOutcome.RETRY:
        return False

    rewrites = sum(
        1 for record in history if record.judge_outcome == JudgeOutcome.RETRY
    )
    return rewrites > config.max_judge_retries
