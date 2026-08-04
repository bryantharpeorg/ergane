"""What happens after an attempt fails — decided once, by one pure function.

The ladder is this component's entire retry policy: three attempts by default,
one debugger cycle, then a human (FR-006, FR-007, FR-008). It is a pure function
over an attempt history because constitution IV puts routing and retry decisions
in deterministic code, and because the alternative — the policy spread through
the interpreter's workflow body — is a policy that cannot be tested without
Temporal and cannot be changed without a workflow migration. So these tests run
no workflow, mint no key, read no clock, and touch no disk; the last test asserts
structurally that the module under test *can't*.

Five decisions are pinned here that the caps alone do not settle:

- **Only the latest attempt decides.** A history is not scored best-of; an
  earlier PASS never rescues a later failure. Verification is about the state of
  the worktree now, and the ladder reads the last record for the same reason
  `compose_result` has no third verdict.
- **Judge retries are bounded *inside* the total, never on top of it** (SC-003).
  Under the defaults the two caps expire together — 3 attempts is initial + 2
  retries, and 2 is also the judge-retry cap — so the distinction is only
  observable under a custom config that raises `max_attempts`. That is exactly
  where these tests look: with `max_attempts=5, max_judge_retries=1`, a second
  judge-driven failure stops granting attempts even though the attempt budget is
  half unspent. The cap binds on *judge-driven* failures only: a gate failure
  after the judge budget is gone still retries, which is what "exhausted judge
  retries consume attempts as failures" means from the other side.
- **The debugger cycle is a rung, not an attempt.** It runs after the ordinary
  budget is spent and does not consume it, so `debugger_cycles` is what limits
  it — exactly once by default, and never twice however many attempts a later
  escalation grants.
- **Escalation resolutions arrive as an argument, not as history.** An operator
  pressing a button is not an attempt; it is a fact about attempts *allowed*.
  It rides in a keyword-only `escalations` sequence defaulting to empty, so
  `next_action(history, config)` — data-model.md's signature — stays the call
  for every decision made before anyone was paged. Each `RETRY` resolution
  grants exactly one more attempt; a second grant requires a second escalation.
- **Nothing but an explicit grant produces more work.** `KILL`, the store's
  `EXPIRED` timeout value, `PAUSE_EPIC`, and any resolution string the ladder has
  never heard of all end it — and they outrank a trailing PASS, because the one
  asymmetry worth having is losing work the operator killed rather than
  unlocking a downstream edge after they killed it (FR-005). `PAUSE_EPIC` is a
  decision about the *epic*, and parking this node is the most the ladder can say
  about it; the interpreter that owns epic-level suspension is what distinguishes
  a park from a kill.

Written before `factory/verify/ladder.py` exists (T023 precedes T026): until the
module lands, every test here fails at import.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Sequence

import pytest

from factory.config import load_personas
from factory.verify.ladder import DEBUGGER_PERSONA, next_action
from factory.verify.models import (
    AttemptRecord,
    EscalationChoice,
    JudgeOutcome,
    NextAction,
    OverallVerdict,
    VerificationConfig,
)

# The store owns the persisted spelling of a timed-out escalation; the ladder has
# to terminate on that exact value, so the test takes it from the source.
from factory.verify.store import EXPIRED

PASS = OverallVerdict.PASS
FAIL = OverallVerdict.FAIL

#: The defaults every spec sentence is written against: 3 attempts, 2 judge
#: retries inside them, 1 debugger cycle (data-model.md § VerificationConfig).
DEFAULTS = VerificationConfig()

#: Whatever persona the node dispatched under — the ladder distinguishes exactly
#: one persona (the debugger) and treats every other one as ordinary work.
WORKER = "implementer"


def attempt(
    number: int,
    *,
    verdict: OverallVerdict = FAIL,
    persona: str = WORKER,
    judge: JudgeOutcome | None = None,
) -> AttemptRecord:
    """One history entry, defaulting to the case the ladder exists for."""
    return AttemptRecord(
        attempt=number, persona=persona, verdict=verdict, judge_outcome=judge
    )


def failures(
    count: int, *, judge: JudgeOutcome | None = None, start: int = 1
) -> list[AttemptRecord]:
    """`count` consecutive failed attempts, all failing the same way."""
    return [attempt(start + offset, judge=judge) for offset in range(count)]


def debugger_cycle(number: int, *, verdict: OverallVerdict = FAIL) -> AttemptRecord:
    """The debugger's attempt, which joins the history like any other."""
    return attempt(number, verdict=verdict, persona=DEBUGGER_PERSONA)


def spent(config: VerificationConfig = DEFAULTS) -> list[AttemptRecord]:
    """A history with the ordinary attempt budget exhausted, debugger not yet run."""
    return failures(config.max_attempts)


def escalated(config: VerificationConfig = DEFAULTS) -> list[AttemptRecord]:
    """…and the one debugger cycle spent too: the history that pages a human."""
    return [*spent(config), debugger_cycle(config.max_attempts + 1)]


# --- reading the history ----------------------------------------------------


def test_an_empty_history_starts_the_first_attempt() -> None:
    # Nothing has run, so nothing is spent: the first thing the ladder can ask
    # for is the attempt itself.
    assert next_action([], DEFAULTS) is NextAction.RETRY


@pytest.mark.parametrize(
    ("history", "case"),
    [
        ([attempt(1, verdict=PASS)], "first attempt"),
        ([*failures(2), attempt(3, verdict=PASS)], "after two failures"),
        (
            [*failures(2), attempt(3, verdict=PASS, judge=JudgeOutcome.PASS)],
            "judge agreed",
        ),
        (
            [*failures(2), attempt(3, verdict=PASS, judge=JudgeOutcome.UNAVAILABLE)],
            "judge unavailable, gates green",
        ),
        ([*spent(), debugger_cycle(4, verdict=PASS)], "debugger fixed it"),
    ],
)
def test_a_passing_attempt_ends_the_ladder(
    history: list[AttemptRecord], case: str
) -> None:
    assert next_action(history, DEFAULTS) is NextAction.PASSED, case


def test_only_the_latest_attempt_decides() -> None:
    # No best-of scoring: an earlier PASS does not rescue the attempt that
    # followed it, or a node could unlock its downstream edges on a verdict that
    # is no longer true of its worktree (FR-005).
    history = [attempt(1, verdict=PASS), attempt(2, verdict=FAIL)]

    assert next_action(history, DEFAULTS) is NextAction.RETRY


def test_the_budget_counts_records_not_attempt_numbers() -> None:
    # Attempt numbers are attribution (they key the evidence store rows and the
    # component-1 keys), not a counter the ladder may read. A node whose numbering
    # continues from elsewhere still gets its full budget.
    history = [attempt(7), attempt(8)]

    assert next_action(history, DEFAULTS) is NextAction.RETRY
    assert next_action([*history, attempt(9)], DEFAULTS) is NextAction.DEBUGGER


def test_the_ladder_decides_without_touching_its_input() -> None:
    history = spent()
    before = list(history)

    first = next_action(history, DEFAULTS)
    second = next_action(history, DEFAULTS)

    assert history == before, "the ladder mutated the history it was handed"
    assert first is second is NextAction.DEBUGGER


def test_any_sequence_of_records_is_accepted() -> None:
    # Workflow code holds its history in whatever shape it likes; the ladder asks
    # for a sequence, not a list it owns.
    history: Sequence[AttemptRecord] = tuple(spent())

    assert next_action(history, DEFAULTS) is NextAction.DEBUGGER


# --- the attempt budget: any mix of failures --------------------------------


MIXES: list[tuple[str, JudgeOutcome | None]] = [
    ("gate failure", None),
    ("judge asked for a rewrite", JudgeOutcome.RETRY),
    ("judge failed it outright", JudgeOutcome.FAIL),
]


@pytest.mark.parametrize(("label", "judge"), MIXES, ids=[m[0] for m in MIXES])
@pytest.mark.parametrize("count", [1, 2])
def test_failures_below_the_cap_retry_whatever_the_mix(
    count: int, label: str, judge: JudgeOutcome | None
) -> None:
    # "3 attempts per node (initial + 2 retries, from any mix of gate and judge
    # failures)" — spec US3 scenario 2.
    assert next_action(failures(count, judge=judge), DEFAULTS) is NextAction.RETRY, label


@pytest.mark.parametrize(
    ("history", "case"),
    [
        (failures(3), "three gate failures"),
        (failures(3, judge=JudgeOutcome.FAIL), "three judge failures"),
        (
            [
                attempt(1),
                attempt(2, judge=JudgeOutcome.RETRY),
                attempt(3, judge=JudgeOutcome.FAIL),
            ],
            "one of each",
        ),
    ],
)
def test_the_attempt_cap_is_a_total_across_the_mix(
    history: list[AttemptRecord], case: str
) -> None:
    assert next_action(history, DEFAULTS) is NextAction.DEBUGGER, case


def test_a_custom_attempt_cap_is_honored() -> None:
    single = VerificationConfig(max_attempts=1)
    generous = VerificationConfig(max_attempts=5)

    assert next_action(failures(1), single) is NextAction.DEBUGGER
    assert next_action(failures(4), generous) is NextAction.RETRY
    assert next_action(failures(5), generous) is NextAction.DEBUGGER


# --- judge retries, bounded inside the total --------------------------------


def test_the_default_caps_let_the_judge_ask_for_two_rewrites() -> None:
    # Two judge-driven retries fit inside the default three attempts, and the
    # third failure hits both caps at once — which is why the judge cap needs a
    # config where the two do not coincide to be observable at all.
    one = failures(1, judge=JudgeOutcome.RETRY)
    two = failures(2, judge=JudgeOutcome.RETRY)
    three = failures(3, judge=JudgeOutcome.RETRY)

    assert next_action(one, DEFAULTS) is NextAction.RETRY
    assert next_action(two, DEFAULTS) is NextAction.RETRY
    assert next_action(three, DEFAULTS) is NextAction.DEBUGGER


def test_judge_retries_stop_granting_attempts_before_the_budget_runs_out() -> None:
    # max_attempts=5 leaves the budget half unspent; max_judge_retries=1 means the
    # judge has already had its rewrite. Bounded judge spend wins (SC-003).
    config = VerificationConfig(max_attempts=5, max_judge_retries=1)
    history = [
        attempt(1),
        attempt(2, judge=JudgeOutcome.RETRY),
        attempt(3, judge=JudgeOutcome.RETRY),
    ]

    assert next_action(history[:2], config) is NextAction.RETRY
    assert next_action(history, config) is NextAction.DEBUGGER


def test_the_judge_cap_binds_only_on_judge_driven_failures() -> None:
    # The other half of "exhausted judge retries consume attempts as failures":
    # a gate failure is not judge spend, so the ordinary budget still applies.
    config = VerificationConfig(max_attempts=5, max_judge_retries=1)
    history = [attempt(1, judge=JudgeOutcome.RETRY), attempt(2), attempt(3)]

    assert next_action(history, config) is NextAction.RETRY


@pytest.mark.parametrize(
    "judge",
    [JudgeOutcome.FAIL, JudgeOutcome.UNAVAILABLE, None],
    ids=["judge failed it", "judge unreachable", "judge never ran"],
)
def test_only_a_judge_retry_counts_against_the_judge_cap(
    judge: JudgeOutcome | None,
) -> None:
    # A judge that failed the attempt outright asked for nothing; charging it to
    # the rewrite budget would cut the node's attempts for someone else's verdict.
    config = VerificationConfig(max_attempts=3, max_judge_retries=0)

    assert next_action(failures(1, judge=judge), config) is NextAction.RETRY


def test_judge_retries_can_be_switched_off() -> None:
    config = VerificationConfig(max_attempts=3, max_judge_retries=0)

    assert next_action(failures(1, judge=JudgeOutcome.RETRY), config) is (
        NextAction.DEBUGGER
    )


# --- the debugger rung ------------------------------------------------------


def test_the_debugger_takes_over_when_the_attempts_are_spent() -> None:
    assert next_action(spent(), DEFAULTS) is NextAction.DEBUGGER


def test_a_failed_debugger_cycle_escalates() -> None:
    assert next_action(escalated(), DEFAULTS) is NextAction.ESCALATE


def test_the_debugger_runs_exactly_once() -> None:
    # Every state reachable after the cycle has been spent — including the extra
    # attempt an escalation grants — escalates rather than calling it back.
    granted = [*escalated(), attempt(5)]

    assert next_action(escalated(), DEFAULTS) is NextAction.ESCALATE
    assert (
        next_action(granted, DEFAULTS, escalations=(EscalationChoice.RETRY,))
        is NextAction.ESCALATE
    )


def test_the_debugger_cycle_does_not_spend_the_attempt_budget() -> None:
    # Its attempt joins the history (contracts/verification-flow.md) but it is a
    # rung of its own: `debugger_cycles` limits it, `max_attempts` does not.
    config = VerificationConfig(max_attempts=3, debugger_cycles=2)
    history = [*spent(config), debugger_cycle(4)]

    assert next_action(history, config) is NextAction.DEBUGGER
    assert next_action([*history, debugger_cycle(5)], config) is NextAction.ESCALATE


def test_a_zero_debugger_budget_escalates_directly() -> None:
    config = VerificationConfig(debugger_cycles=0)

    assert next_action(spent(config), config) is NextAction.ESCALATE


# --- escalation resolutions -------------------------------------------------


def test_an_escalation_retry_grants_exactly_one_more_attempt() -> None:
    history = escalated()
    granted = (EscalationChoice.RETRY,)

    assert next_action(history, DEFAULTS, escalations=granted) is NextAction.RETRY
    assert (
        next_action([*history, attempt(5)], DEFAULTS, escalations=granted)
        is NextAction.ESCALATE
    )


def test_each_escalation_grants_its_own_attempt() -> None:
    # Two escalations, two grants: the operator can keep saying "try again", and
    # each answer buys exactly one attempt (contracts/verification-flow.md).
    twice = (EscalationChoice.RETRY, EscalationChoice.RETRY)
    history = [*escalated(), attempt(5)]

    assert next_action(history, DEFAULTS, escalations=twice) is NextAction.RETRY
    assert (
        next_action([*history, attempt(6)], DEFAULTS, escalations=twice)
        is NextAction.ESCALATE
    )


def test_a_granted_attempt_that_passes_ends_the_ladder() -> None:
    history = [*escalated(), attempt(5, verdict=PASS)]

    assert (
        next_action(history, DEFAULTS, escalations=(EscalationChoice.RETRY,))
        is NextAction.PASSED
    )


@pytest.mark.parametrize(
    ("resolution", "case"),
    [
        (EscalationChoice.KILL, "the operator killed it"),
        (EXPIRED, "an hour of silence (FR-008 default)"),
        (EscalationChoice.PAUSE_EPIC, "the epic is paused; this node parks"),
        ("resolved", "a resolution the ladder has never heard of"),
    ],
)
def test_anything_but_a_grant_ends_the_node(
    resolution: EscalationChoice | str, case: str
) -> None:
    assert (
        next_action(escalated(), DEFAULTS, escalations=(resolution,))
        is NextAction.KILLED
    ), case


def test_a_kill_after_a_grant_is_still_terminal() -> None:
    history = [*escalated(), attempt(5)]
    resolutions = (EscalationChoice.RETRY, EscalationChoice.KILL)

    assert next_action(history, DEFAULTS, escalations=resolutions) is NextAction.KILLED


def test_a_kill_outranks_a_passing_attempt() -> None:
    # The deliberate asymmetry: a node killed by its operator must not unlock a
    # downstream edge, even if the work it was killed over turned out green.
    history = [*escalated(), attempt(5, verdict=PASS)]

    assert (
        next_action(history, DEFAULTS, escalations=(EscalationChoice.KILL,))
        is NextAction.KILLED
    )


# --- the module stays pure --------------------------------------------------


LADDER = Path(__file__).resolve().parents[1] / "factory" / "verify" / "ladder.py"
PACKAGE = "factory.verify"

#: Nothing that can act on the world, and nothing that can read a clock — a
#: decision that varies with wall time is not one a workflow may replay.
FORBIDDEN_IMPORTS = {
    "temporalio",
    "httpx",
    "sqlite3",
    "subprocess",
    "os",
    "sys",
    "pathlib",
    "shutil",
    "socket",
    "logging",
    "yaml",
    "telegram",
    "time",
    "datetime",
    "random",
}


def imported_modules(tree: ast.Module) -> set[str]:
    """Every module the file imports, relative imports resolved to absolute."""
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = PACKAGE if node.level else ""
            modules.add(".".join(part for part in (prefix, node.module) if part))
    return modules


def test_the_ladder_imports_nothing_that_could_do_anything() -> None:
    modules = imported_modules(ast.parse(LADDER.read_text(encoding="utf-8")))
    reachable = {module.split(".")[0] for module in modules} & FORBIDDEN_IMPORTS

    assert not reachable, (
        f"factory/verify/ladder.py imports {sorted(reachable)} — the retry policy "
        "is a pure decision over history (constitution IV), and a module that can "
        "run a command or read a clock is a policy nobody can replay or unit-test"
    )


def test_the_ladder_depends_on_nothing_but_the_shared_types() -> None:
    modules = imported_modules(ast.parse(LADDER.read_text(encoding="utf-8")))
    factory_imports = {m for m in modules if m.split(".")[0] == "factory"}

    assert factory_imports <= {f"{PACKAGE}.models"}, (
        f"factory/verify/ladder.py reaches into {sorted(factory_imports)} — the "
        "ladder decides from an attempt history and its caps, nothing else"
    )


def test_the_debugger_persona_is_one_the_registry_defines() -> None:
    # The ladder names exactly one persona; constitution VII means that name has
    # to resolve through the operator's registry, not just look plausible here.
    assert DEBUGGER_PERSONA in load_personas()
