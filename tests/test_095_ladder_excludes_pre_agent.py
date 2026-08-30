"""US2 — a pre-agent failure does not consume the attempt budget.

US1 made the pre-agent failure distinguishable: an attempt whose agent process
never produced a token is `Termination.PRE_AGENT_FAILURE`, and its record carries
a note naming authentication. US2 keys the ladder's accounting on that
distinction: a pre-agent failure is not a rung of the ladder at all, so it must
not count toward `max_attempts` — and, because an exclusion without a bound of
its own is a starvation bug (plan trap 2), it is bounded by a dial of its own
that escalates rather than retrying forever.

These tests pin the exclusion (T009-T011, T014), the bound (T012), the escalation
that the bound raises (T013), and the manifest refusal for the new dial (T015).
They run no workflow and touch no store: the ladder is a pure function over an
attempt history, and the escalation message is pure rendering.
"""

from __future__ import annotations

import pytest

from factory.notify.messages import escalation_message
from factory.verify.factory_yaml import FactoryConfigError, parse_factory_config
from factory.verify.ladder import (
    _attempts_spent,
    next_action,
    pre_agent_bound_spent,
    pre_agent_failures_spent,
)
from factory.verify.models import (
    AttemptRecord,
    EscalationChoice,
    EscalationRecord,
    NextAction,
    OverallVerdict,
    VerificationConfig,
)

PASS = OverallVerdict.PASS
FAIL = OverallVerdict.FAIL

#: Whatever persona the node dispatched under — the ladder distinguishes exactly
#: one persona (the debugger) and treats every other one as ordinary work.
WORKER = "implementer"

DEFAULTS = VerificationConfig()


def attempt(
    number: int,
    *,
    verdict: OverallVerdict = FAIL,
    persona: str = WORKER,
    pre_agent: bool = False,
) -> AttemptRecord:
    """One history entry, defaulting to the case the ladder exists for."""
    return AttemptRecord(
        attempt=number, persona=persona, verdict=verdict, pre_agent=pre_agent
    )


def pre_agent(number: int) -> AttemptRecord:
    """A pre-agent failure: no agent turn ran, so it is not a rung of the ladder."""
    return attempt(number, pre_agent=True)


# --- T009 [US2-S1] three pre-agent failures still grant another attempt -------


def test_three_pre_agent_failures_do_not_spend_the_attempt_budget() -> None:
    """A history of three pre-agent failures under `max_attempts=3` still grants.

    The pre-agent failure is not a rung, so `_attempts_spent` reads zero and the
    ladder grants another attempt rather than escalating. Before this change the
    same history read as three spent attempts and escalated.
    """
    config = VerificationConfig(max_attempts=3)
    history = [pre_agent(1), pre_agent(2), pre_agent(3)]

    assert next_action(history, config) is NextAction.RETRY


# --- T010 [US2-S2] a mixed history counts only the real attempts --------------


def test_a_mixed_history_counts_only_the_real_attempts() -> None:
    """Pre-agent failures are excluded; real attempts are counted as today."""
    history = [
        pre_agent(1),
        attempt(2),
        pre_agent(3),
        attempt(4),
    ]

    assert _attempts_spent(history, DEFAULTS) == 2


# --- T011 [US2-S3] the control: only real attempts is unchanged ---------------


def test_a_history_of_only_real_attempts_is_unchanged() -> None:
    """The control: with no pre-agent failures, the spent count is today's."""
    history = [attempt(1), attempt(2), attempt(3)]

    assert _attempts_spent(history, DEFAULTS) == 3


# --- T012 [US2-S4, trap 2] an unbroken run escalates on its own bound ---------


def test_an_unbroken_run_of_pre_agent_failures_escalates_on_its_own_bound() -> None:
    """The exclusion has a bound of its own, or a dead credential retries forever.

    `max_pre_agent_failures=3` with three consecutive pre-agent failures must
    escalate, not grant a fourth attempt that will fail the same way.
    """
    config = VerificationConfig(max_pre_agent_failures=3)
    history = [pre_agent(1), pre_agent(2), pre_agent(3)]

    assert next_action(history, config) is NextAction.ESCALATE


def test_the_pre_agent_bound_is_consecutive_not_cumulative() -> None:
    """A real attempt breaks the run, so the pre-agent counter resets.

    Five pre-agent failures followed by a real attempt is not an unbroken run:
    the tail is a real attempt, so the pre-agent bound is not spent.
    """
    config = VerificationConfig(max_pre_agent_failures=3)
    history = [
        pre_agent(1),
        pre_agent(2),
        pre_agent(3),
        pre_agent(4),
        pre_agent(5),
        attempt(6),
    ]

    assert pre_agent_failures_spent(history) == 0
    assert pre_agent_bound_spent(history, config) is False


def test_a_grant_raises_the_pre_agent_bound_like_the_attempt_budget() -> None:
    """A RETRY press buys one more attempt, pre-agent or real, like the budget."""
    config = VerificationConfig(max_pre_agent_failures=3)
    history = [pre_agent(1), pre_agent(2), pre_agent(3)]

    # At the bound, a grant lifts it by one, so the press buys an attempt.
    assert (
        next_action(history, config, escalations=(EscalationChoice.RETRY,))
        is NextAction.RETRY
    )


# --- T013 [US2-S5, trap 6] the escalation names authentication, not KILL -------


def test_the_authentication_escalation_names_its_cause_and_remedy() -> None:
    """The escalation raised on the pre-agent bound names authentication.

    The operator reads the remedy — re-authenticate — rather than a generic
    "the node failed". The summary is the pre-agent note US1 already produces.
    """
    record = EscalationRecord(
        escalation_id="0" * 12,
        workflow_id="w",
        epic_id="095",
        node_id="us2",
        choices=[EscalationChoice.RETRY, EscalationChoice.PAUSE_EPIC],
        history_summary=(
            "no agent turn ran: the process exited before producing a single "
            "token. authentication: the worker host's agent session was refused. "
            "remedy: re-authenticate on the worker host, then re-dispatch."
        ),
        sent_at="2026-08-30T00:00:00Z",
        expires_at="2026-08-30T01:00:00Z",
        default_choice=EscalationChoice.PAUSE_EPIC,
    )

    message = escalation_message(record).lower()

    assert "authenticat" in message, "the escalation does not name authentication"
    assert "remedy" in message, "the escalation does not name the remedy"


def test_the_authentication_escalation_does_not_default_to_kill() -> None:
    """The fail-safe default for an authentication escalation is not KILL.

    A dead credential is fixed by re-authenticating, not by killing the node, so
    the default the message advertises — and the one applied on silence — is
    PAUSE_EPIC, and the text says so rather than leaving the operator to notice
    the button moved (trap 6).
    """
    record = EscalationRecord(
        escalation_id="0" * 12,
        workflow_id="w",
        epic_id="095",
        node_id="us2",
        choices=[EscalationChoice.RETRY, EscalationChoice.PAUSE_EPIC],
        history_summary="authentication: the worker host's agent session was refused.",
        sent_at="2026-08-30T00:00:00Z",
        expires_at="2026-08-30T01:00:00Z",
        default_choice=EscalationChoice.PAUSE_EPIC,
    )

    message = escalation_message(record).lower()

    # The default line names PAUSE_EPIC, not KILL.
    assert "applies the default: pause_epic" in message, (
        "the default is not named as PAUSE_EPIC in the message"
    )
    assert "applies the default: kill" not in message, (
        "the authentication escalation still defaults to KILL"
    )


# --- T014 [FR-005, trap 4] the exclusion applies at every call site -----------


def test_the_exclusion_applies_when_config_is_none() -> None:
    """`_attempts_spent` is called with and without `config`; the pre-agent
    exclusion is a property of the record, not of the config, so it applies
    even where `config` is None (trap 4)."""
    history = [pre_agent(1), pre_agent(2), attempt(3)]

    assert _attempts_spent(history, DEFAULTS) == 1
    assert _attempts_spent(history, None) == 1


# --- T015 [FR-006] the new bound is refused outside its range -----------------


def test_the_pre_agent_bound_is_refused_outside_its_range() -> None:
    """The new dial is refused in the shape the other ladder dials are refused."""
    base = (
        "version: 2\n"
        "runtime: bwrap\n"
        "gates:\n"
        "  unit: \"uv run pytest -q\"\n"
    )

    with pytest.raises(FactoryConfigError) as below:
        parse_factory_config(base + "ladder:\n  max_pre_agent_failures: 0\n")
    assert below.value.rule == "ladder_max_pre_agent_failures_min"

    with pytest.raises(FactoryConfigError) as above:
        parse_factory_config(base + "ladder:\n  max_pre_agent_failures: 11\n")
    assert above.value.rule == "ladder_max_pre_agent_failures_max"

    with pytest.raises(FactoryConfigError) as not_int:
        parse_factory_config(base + "ladder:\n  max_pre_agent_failures: true\n")
    assert not_int.value.rule == "ladder_max_pre_agent_failures_type"


def test_the_pre_agent_bound_parses_when_declared() -> None:
    """A declared `max_pre_agent_failures` is read into the config."""
    text = (
        "version: 2\n"
        "runtime: bwrap\n"
        "gates:\n"
        "  unit: \"uv run pytest -q\"\n"
        "ladder:\n"
        "  max_pre_agent_failures: 4\n"
    )

    config = parse_factory_config(text)

    assert config.ladder.max_pre_agent_failures == 4
