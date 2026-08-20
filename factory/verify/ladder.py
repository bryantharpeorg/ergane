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
- **Nothing but an explicit grant produces more work.** `KILL`, `KILL_EPIC`, the
  store's `EXPIRED` timeout value, `PAUSE_EPIC`, and any resolution this module
  has never heard of all end the node, and they outrank a trailing PASS. That asymmetry is
  deliberate: losing work an operator killed is recoverable (the branch and
  worktree are preserved by the lifecycle owner), unlocking a downstream edge
  after they killed it is not.

`PAUSE_EPIC` and `KILL_EPIC` end the node here for the same reason: ending it is
the most a per-node decision can say about an epic-level suspension or stop, and
the interpreter that owns releasing nodes is what distinguishes a park from a
kill and a killed node from a killed epic (068 FR-008).
"""

from __future__ import annotations

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
    if attempts_left and not _judge_vetoes_a_retry(history, config, grants):
        return NextAction.RETRY

    if _promotion_available(history, config):
        return NextAction.PROMOTE

    if _debugger_cycles_spent(history) < config.debugger_cycles:
        return NextAction.DEBUGGER

    return NextAction.ESCALATE


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
    its own rung (US5-S5).
    """
    promotion_target = config.promotion_persona if config is not None else None
    excluded = {DEBUGGER_PERSONA, promotion_target} if promotion_target else {DEBUGGER_PERSONA}
    return sum(1 for record in history if record.persona not in excluded)


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
