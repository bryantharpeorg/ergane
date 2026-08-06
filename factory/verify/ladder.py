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
  failure is not judge spend, so it still retries on the ordinary budget.
- **The debugger cycle is a rung, not an attempt.** It runs once the ordinary
  budget is gone and is limited by `debugger_cycles` alone, so an escalation that
  grants more attempts never calls it back for a second turn.
- **Escalation resolutions arrive as an argument, not as history.** A button
  press is not an attempt; it is a fact about attempts *allowed*. It rides in a
  keyword-only sequence defaulting to empty so that `next_action(history, config)`
  — data-model.md's signature — stays the call for every decision made before
  anyone was paged. Each `RETRY` grants exactly one more attempt; a second grant
  takes a second escalation.
- **Nothing but an explicit grant produces more work.** `KILL`, the store's
  `EXPIRED` timeout value, `PAUSE_EPIC`, and any resolution this module has never
  heard of all end the node, and they outrank a trailing PASS. That asymmetry is
  deliberate: losing work an operator killed is recoverable (the branch and
  worktree are preserved by the lifecycle owner), unlocking a downstream edge
  after they killed it is not.

`PAUSE_EPIC` ends the node here for the same reason: parking it is the most a
per-node decision can say about an epic-level suspension, and the interpreter
that owns releasing nodes is what distinguishes a park from a kill.
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
    # exactly one attempt (contracts/verification-flow.md).
    allowed = config.max_attempts + len(escalations)
    attempts_left = _attempts_spent(history) < allowed
    if attempts_left and not _judge_rewrites_spent(history, config):
        return NextAction.RETRY

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


def _attempts_spent(history: Sequence[AttemptRecord]) -> int:
    """How much of the ordinary attempt budget this node has consumed.

    Records, not attempt numbers: the number keys the evidence-store row and the
    component-1 attribution key, and a node whose numbering continues from
    elsewhere still gets its full budget. The debugger's cycle is excluded — it
    is a rung of its own, limited by `debugger_cycles`.
    """
    return sum(1 for record in history if record.persona != DEBUGGER_PERSONA)


def _debugger_cycles_spent(history: Sequence[AttemptRecord]) -> int:
    """How many debugger cycles have already run."""
    return sum(1 for record in history if record.persona == DEBUGGER_PERSONA)


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
