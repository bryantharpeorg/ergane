"""US5: the ladder can promote a struggling node to a stronger persona.

These tests cover the third rung of the retry ladder.  It sits between the
ordinary attempt budget and the debugger rung: once the ordinary attempts are
spent, a configured promotion persona gets one try before the node falls back
to the debugger and then escalation.

Every test is pure: it calls `next_action` with a fabricated history and
config, no workflow, no disk, no clock (constitution IV).
"""

from __future__ import annotations

import pytest

from factory.config import load_personas
from factory.verify.ladder import DEBUGGER_PERSONA, PROMOTION_PERSONA, next_action
from factory.verify.models import (
    AttemptRecord,
    EscalationChoice,
    JudgeOutcome,
    NextAction,
    OverallVerdict,
    VerificationConfig,
)

PASS = OverallVerdict.PASS
FAIL = OverallVerdict.FAIL

#: The ordinary builder persona used by most ladder tests.
WORKER = "implementer"

#: A stronger persona configured as the promotion target.  This must be a
#: persona that exists in the registry, but the ladder code must not hardcode
#: it (trap 2).  The test uses the registry as the operator would configure it.
CLOSER = "closer"

#: A persona name that is guaranteed not to be configured as a promotion target
#: in any of these tests, used for the "no promotion persona" regression control.
NO_PROMOTION = None


def attempt(
    number: int,
    *,
    verdict: OverallVerdict = FAIL,
    persona: str = WORKER,
    judge: JudgeOutcome | None = None,
) -> AttemptRecord:
    return AttemptRecord(
        attempt=number, persona=persona, verdict=verdict, judge_outcome=judge
    )


def failures(count: int, *, judge: JudgeOutcome | None = None, start: int = 1) -> list[AttemptRecord]:
    return [attempt(start + offset, judge=judge) for offset in range(count)]


def promotion_attempt(
    number: int,
    *,
    verdict: OverallVerdict = FAIL,
    judge: JudgeOutcome | None = None,
) -> AttemptRecord:
    # In real history a promoted attempt records the configured persona, not a
    # synthetic marker, because FR-012 requires it to be distinguishable from
    # both ordinary attempts and debugger cycles.
    return attempt(number, verdict=verdict, persona=CLOSER, judge=judge)


def debugger_cycle(number: int, *, verdict: OverallVerdict = FAIL) -> AttemptRecord:
    return attempt(number, verdict=verdict, persona=DEBUGGER_PERSONA)


def spent(config: VerificationConfig) -> list[AttemptRecord]:
    """A history with the ordinary attempt budget exhausted, debugger not yet run."""
    return failures(config.max_attempts)


# --- T032 [P] [US5] ordinary attempts spent -> promote ------------------------


def test_spent_ordinary_attempts_are_promoted_instead_of_escalated() -> None:
    # max_attempts is raised so the promotion rung is observable: at defaults
    # the ordinary budget and the debugger budget expire together (trap 9).
    config = VerificationConfig(
        max_attempts=4,
        promotion_persona=CLOSER,
        promotion_cycles=1,
    )
    history = spent(config)

    assert next_action(history, config) is NextAction.PROMOTE


# --- T033 [P] [US5] promotion used -> escalate, bounded -----------------------


def test_used_promotion_escalates_like_the_debugger_rung() -> None:
    # The promotion rung is bounded like the debugger rung: once the configured
    # stronger persona has been tried, the next decision falls through to the
    # debugger and then escalation.
    config = VerificationConfig(
        max_attempts=4,
        promotion_persona=CLOSER,
        promotion_cycles=1,
    )
    history = [*spent(config), promotion_attempt(config.max_attempts + 1)]

    assert next_action(history, config) is NextAction.DEBUGGER
    assert (
        next_action([*history, debugger_cycle(config.max_attempts + 2)], config)
        is NextAction.ESCALATE
    )


def test_promotion_cycles_are_bounded() -> None:
    # `promotion_cycles` bounds how many times the rung may fire.  After the
    # ordinary budget is spent and a promotion fails, an ordinary attempt keeps
    # the cycle alive; once `promotion_cycles` promotions have been recorded the
    # ladder falls through to the debugger/escalation path.
    config = VerificationConfig(
        max_attempts=4,
        promotion_persona=CLOSER,
        promotion_cycles=2,
    )
    # First promotion is requested when the latest failure is not the promotion
    # persona, so we end the ordinary budget with an implementer attempt.
    first = [
        *spent(config),
        attempt(config.max_attempts + 1),
    ]
    # The promoted attempt itself records the closer persona.  To ask for a
    # second promotion we need another ordinary attempt in between.
    second = [
        *first,
        attempt(config.max_attempts + 2, persona=CLOSER),
        attempt(config.max_attempts + 3),
    ]
    third = [
        *second,
        attempt(config.max_attempts + 4, persona=CLOSER),
        attempt(config.max_attempts + 5),
    ]

    assert next_action(first, config) is NextAction.PROMOTE
    assert next_action(second, config) is NextAction.PROMOTE
    assert next_action(third, config) is NextAction.DEBUGGER


# --- T034 [P] [US5] no promotion persona -> behave as today -------------------


def test_no_promotion_persona_keeps_todays_behaviour() -> None:
    # With no promotion persona configured, the ladder behaves exactly as before:
    # spent ordinary attempts go straight to the debugger.
    config = VerificationConfig(max_attempts=4)
    history = spent(config)

    assert next_action(history, config) is NextAction.DEBUGGER


def test_no_promotion_persona_still_escalates_after_debugger() -> None:
    config = VerificationConfig(max_attempts=4)
    history = [*spent(config), debugger_cycle(config.max_attempts + 1)]

    assert next_action(history, config) is NextAction.ESCALATE


# --- T035 [P] [US5] budget is operator-settable in _LADDER_KEYS -----------------


def test_promotion_cycles_is_a_ladder_key() -> None:
    from factory.verify.factory_yaml import _LADDER_KEYS, _LADDER_BOUNDS

    assert "promotion_cycles" in _LADDER_KEYS
    assert "promotion_cycles" in _LADDER_BOUNDS


def test_promotion_cycles_is_honoured_from_factory_yaml() -> None:
    from factory.verify.factory_yaml import parse_factory_config

    text = """
    version: 2
    runtime: bwrap
    gates:
      test: "true"
    ladder:
      max_attempts: 4
      promotion_persona: closer
      promotion_cycles: 2
    """
    config = parse_factory_config(text)

    assert config.ladder.promotion_persona == "closer"
    assert config.ladder.promotion_cycles == 2


# --- T036 [P] [US5] promoted attempts are distinguishable in history ----------


def test_promoted_attempts_do_not_corrupt_attempt_count() -> None:
    from factory.verify.ladder import (
        _attempts_spent,
        _debugger_cycles_spent,
        _promotion_cycles_spent,
    )

    config = VerificationConfig(
        max_attempts=4,
        promotion_persona=CLOSER,
        promotion_cycles=1,
    )
    history = [
        *spent(config),
        promotion_attempt(config.max_attempts + 1),
        debugger_cycle(config.max_attempts + 2),
    ]

    assert _attempts_spent(history, config) == config.max_attempts
    assert _promotion_cycles_spent(history, config) == 1
    assert _debugger_cycles_spent(history) == 1


# --- T037 [P] [US5] already promoted persona skips the rung -------------------


def test_already_promoted_persona_skips_the_rung() -> None:
    # If the failing attempt was already made by the promotion persona, promoting
    # again would just retry the same persona.  With ordinary attempts exhausted
    # and the latest failure already by the stronger persona, the ladder skips
    # the rung and falls through to the debugger/escalation path.
    config = VerificationConfig(
        max_attempts=4,
        promotion_persona=CLOSER,
        promotion_cycles=1,
    )
    history = [
        *spent(config),
        attempt(config.max_attempts + 1, persona=CLOSER),
    ]

    assert next_action(history, config) is NextAction.DEBUGGER


# --- registry sanity ----------------------------------------------------------


def test_promotion_persona_resolves_through_registry() -> None:
    # The configured promotion target must be a real registry persona.  The
    # placeholder role constant is deliberately not in the registry, because it
    # must never be dispatched; a configured factory.yaml must name a real one.
    assert CLOSER in load_personas()
