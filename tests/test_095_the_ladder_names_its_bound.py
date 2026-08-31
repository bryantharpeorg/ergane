"""US3 — an exhausted ladder names the rung that ended it.

The ladder has three bounds and, until this story, one voice: `ESCALATE`. A node
that spent six attempts on a deterministic refusal and one that was stopped by
`max_judge_retries` with three attempts unspent reached the operator as the same
sentence, so the reading that tells them apart was the source. That is the whole
defect — nine attempts producing one bit of information — and this story is the
rendering that turns it into a diagnosis.

What these tests are written to resist:

- **A second derivation.** The tempting implementation reads the history in the
  renderer and works out which bound must have bound; it is a copy of
  `next_action`'s precedence living where nothing keeps it honest, and it starts
  lying the day a bound moves (plan trap 5). `exhausted_bound` is asked of the
  ladder, beside the decision, and every reading below is *that* answer —
  `test_the_line_the_operator_reads_is_the_ladders_own_sentence` asserts the
  escalation text carries it verbatim, and
  `test_the_renderer_derives_no_bound_of_its_own` asserts the renderer invents
  nothing when the ladder handed it nothing.
- **A reading that is not the operator's reading.** T020-T022 drive a real epic
  to a real escalation and assert on the message
  `factory/notify/messages.py:escalation_message` composes from the record the
  send activity builds — the Telegram body, not an intermediate. T023 renders
  the page `ergane build status` prints, from a live query put through the
  payload converter, because a field that survives the dataclass and not the
  wire is a field no operator can read.
- **A ladder change smuggled in as a rendering.** FR-010 forbids touching
  `_judge_vetoes_a_retry` or `next_action`'s precedence, and this story is
  reporting only. `test_the_bound_is_reported_exactly_when_the_ladder_escalates`
  holds the new function to agreeing with the decision rather than replacing it.

The three histories are the three regimes the spec names: the judge's rewrite
budget spent with attempts left over (the shadowing that cost the epic this spec
was written for), the ordinary attempt budget spent on deterministic refusals,
and the debugger rung spent after both.
"""

from __future__ import annotations

from typing import Any

import pytest
from temporalio.testing import WorkflowEnvironment

from factory.activities.notify_activities import SendEscalationInput, _pending_record
from factory.cli.nouns.build import render_status
from factory.notify.messages import escalation_message
from factory.verify.ladder import exhausted_bound, next_action
from factory.verify.models import (
    AttemptRecord,
    EscalationChoice,
    JudgeOutcome,
    NextAction,
    OverallVerdict,
    VerificationConfig,
)

from tests.test_interpreter import (
    EPIC_ID,
    ScriptedWorld,
    env,  # noqa: F401  — pytest fixture, re-exported for this module
    failing,
    judge_retry,
    one_node,
    passing,
    run_epic,
    scored,
    scored_world,
    start_epic,
    wait_for_status,
)
from tests.test_status_shows_the_dials_in_force import (
    HEADER as LANDING_DIALS_HEADER,
    as_json_document,
    bounded,
)

NODE = "us1"

#: The header the ladder's dials print under, and the word a reading that could
#: not be taken prints instead. Spelled once so the tests and the renderer agree
#: on what is being looked for.
LADDER_HEADER = "ladder dials"
LADDER_UNAVAILABLE = f"{LADDER_HEADER}  unavailable"


def operator_message(request: SendEscalationInput) -> str:
    """The Telegram body an operator is paged with, from what the workflow sent.

    Built through the send activity's own `_pending_record` rather than from a
    hand-made record: the question these tests ask is whether the *escalation*
    names the bound, and a record assembled here would prove only that the
    renderer can print a string it was handed.
    """
    return escalation_message(_pending_record(request))


def attempt(
    number: int,
    *,
    persona: str = "implementer",
    judge_outcome: JudgeOutcome | None = None,
    pre_agent: bool = False,
) -> AttemptRecord:
    """One failed history entry — the case the ladder exists for."""
    return AttemptRecord(
        attempt=number,
        persona=persona,
        verdict=OverallVerdict.FAIL,
        judge_outcome=judge_outcome,
        pre_agent=pre_agent,
    )


# --- T020 [US3-S1] the judge's rewrite budget names itself --------------------


async def test_an_escalation_on_the_judge_bound_names_it_and_its_value(
    env: WorkflowEnvironment,
) -> None:
    """US3-S1: the rewrite cap stopped the node, and the page says so.

    The regime the spec was written for: `max_attempts` is 6, three of them are
    unspent, and the node stops anyway because the judge has asked for one
    rewrite past its cap. Before this story the escalation named neither number,
    and an operator raising `max_attempts` — the only dial with an obvious name —
    would have bought nothing at all.
    """
    script = scored_world(
        scored(judge_retry()),
        scored(judge_retry()),
        scored(judge_retry()),
        client=env.client,
    )

    await run_epic(
        env,
        script,
        graph=one_node(),
        config=VerificationConfig(
            max_attempts=6, max_judge_retries=2, debugger_cycles=0
        ),
    )

    [escalation] = script.escalation_requests
    message = operator_message(escalation)

    assert "max_judge_retries" in message, (
        f"the escalation does not name the bound that ended the node:\n{message}"
    )
    assert "max_judge_retries = 2" in message, (
        f"the escalation does not name the bound's configured value:\n{message}"
    )


# --- T021 [US3-S2] the ordinary attempt budget names itself -------------------


async def test_an_escalation_on_the_attempt_budget_names_that_bound_instead(
    env: WorkflowEnvironment,
) -> None:
    """US3-S2: three deterministic refusals, and the page names `max_attempts`.

    The control for the test above, and the half of the pair that matters: the
    two escalations were indistinguishable, so a line that named a bound would
    be worth nothing if it named the same one both times. No judge is in this
    picture at all — the gates refused — so the rewrite cap has no standing and
    must not be what the operator reads.
    """
    script = ScriptedWorld(
        {NODE: [failing(1), failing(2), failing(3)]}, client=env.client
    )

    await run_epic(
        env,
        script,
        graph=one_node(),
        config=VerificationConfig(max_attempts=3, debugger_cycles=0),
    )

    [escalation] = script.escalation_requests
    message = operator_message(escalation)

    assert "max_attempts = 3" in message, (
        f"the escalation does not name the attempt budget it spent:\n{message}"
    )
    assert "max_judge_retries" not in message, (
        "the escalation names the judge's cap for a node the judge never saw:\n"
        f"{message}"
    )


# --- T022 [US3-S3] the debugger rung names itself -----------------------------


async def test_an_escalation_after_the_debugger_names_the_debugger_bound(
    env: WorkflowEnvironment,
) -> None:
    """US3-S3: the last rung the ladder has, spent, and named as the ending.

    The debugger runs after the ordinary attempts are gone, so both bounds are
    spent when this page goes out. The one that *ended* the node is the rung it
    stopped on, which is the one an operator deciding whether to grant another
    attempt needs: more attempts do not buy another debugger cycle.
    """
    script = ScriptedWorld(
        {NODE: [failing(1), failing(2), failing(3), failing(4)]}, client=env.client
    )

    await run_epic(
        env,
        script,
        graph=one_node(),
        config=VerificationConfig(max_attempts=3, debugger_cycles=1),
    )

    [escalation] = script.escalation_requests
    message = operator_message(escalation)

    assert "debugger_cycles = 1" in message, (
        f"the escalation does not name the debugger rung that ended it:\n{message}"
    )


# --- T023 [US3-S4] the ladder's dials are readable beside the landing's -------


async def test_a_running_epic_shows_the_ladder_dials_beside_the_landing_dials(
    env: WorkflowEnvironment,
) -> None:
    """US3-S4: `ergane build status` prints the three bounds in force.

    081-US3 made the landing dials readable and argued why: a setting that
    parses, persists and can never be observed is the shape of this repository's
    most-filed defect. The ladder's dials were exactly that — an operator who set
    `ladder: {max_attempts: 6, debugger_cycles: 3}` had no reading anywhere that
    said so, which is how a node spent six attempts under a cap of two without
    anybody being able to see the two.

    Read from a live query put through the payload converter, because the CLI
    holds JSON decoded off the wire rather than the dataclass the workflow built.
    """
    config = VerificationConfig(max_attempts=6, max_judge_retries=2, debugger_cycles=3)

    async with start_epic(
        env,
        ScriptedWorld({NODE: [passing()]}, client=env.client),
        graph=one_node(),
        config=config,
    ) as handle:
        status = await wait_for_status(
            handle,
            lambda answer: bool(answer.nodes),
            what="the epic to resolve its graph",
        )
        rendered = render_status(EPIC_ID, as_json_document(status), "RUNNING")

        assert ladder_dials(rendered) == {
            "max_attempts": "6",
            "max_judge_retries": "2",
            "debugger_cycles": "3",
        }
        # Beside, not instead of: the landing dials are still on the page, and
        # so is every line the operator came for (081 FR-010).
        assert LANDING_DIALS_HEADER in rendered.splitlines()
        assert any(line.startswith(f"epic {EPIC_ID}") for line in rendered.splitlines())
        assert any(line.startswith(NODE) for line in rendered.splitlines())

        await bounded(handle.result())


def ladder_dials(rendered: str) -> dict[str, str]:
    """The rendered ladder block, as `dial -> value`.

    Parsed off the printed page rather than read from the document, because the
    printed page is the artifact FR-009 is about.
    """
    lines = rendered.splitlines()
    assert LADDER_HEADER in lines, f"no '{LADDER_HEADER}' block in:\n{rendered}"
    block: dict[str, str] = {}
    for line in lines[lines.index(LADDER_HEADER) + 1 :]:
        if not line.startswith("  "):
            break
        dial, value = line.split()
        block[dial] = value
    return block


def test_a_status_that_cannot_read_the_ladder_still_renders_the_epic() -> None:
    """FR-009 degrades rather than breaking (052, and 081's plan trap 9).

    A worker that predates this story sends no ladder config at all, and one
    queried before `run` records it sends `null`. Neither may cost the operator
    the epic and node lines they came for, and neither may be answered with the
    code defaults — printing `max_attempts 3` for an epic whose dials could not
    be read invents the exact answer this reading exists to stop inventing.
    """
    node = {
        "state": "VERIFYING",
        "attempt": 1,
        "branch": "factory/095/us1",
    }
    unreadable: list[dict[str, Any]] = [
        {"epic_state": "RUNNING", "nodes": {NODE: node}},  # a pre-US3 worker
        {"epic_state": "RUNNING", "nodes": {NODE: node}, "ladder_config": None},
        {"epic_state": "RUNNING", "nodes": {NODE: node}, "ladder_config": 6},
        {
            "epic_state": "RUNNING",
            "nodes": {NODE: node},
            "ladder_config": {"max_attempts": 6},  # truncated
        },
    ]

    for document in unreadable:
        rendered = render_status(EPIC_ID, document, "RUNNING")
        lines = rendered.splitlines()

        assert LADDER_UNAVAILABLE in lines, (
            f"a ladder reading that could not be taken is not admitted:\n{rendered}"
        )
        assert any(line.startswith(f"epic {EPIC_ID}") for line in lines)
        assert any(line.startswith(NODE) for line in lines)
        assert "max_attempts 3" not in rendered, (
            "the code defaults were printed for an epic whose dials were unreadable"
        )


# --- T024 [FR-008, trap 5] the line comes from the ladder, not from a copy ----


def test_the_bound_is_reported_exactly_when_the_ladder_escalates() -> None:
    """`exhausted_bound` answers the decision `next_action` made, or nothing.

    Trap 5's first half. The function is a sibling of the decision rather than a
    second reading of the history: it names a bound for exactly the histories
    that escalate, and `None` for every history that still has somewhere to go.
    A copy of the precedence would drift from this the day an order changed.
    """
    config = VerificationConfig(max_attempts=3, max_judge_retries=2, debugger_cycles=1)
    histories: list[list[AttemptRecord]] = [
        [],
        [attempt(1)],
        [attempt(1), attempt(2)],
        [attempt(1), attempt(2), attempt(3)],
        [attempt(1), attempt(2), attempt(3), attempt(4, persona="debugger")],
        [attempt(1, judge_outcome=JudgeOutcome.RETRY)],
        [attempt(n, pre_agent=True) for n in range(1, 6)],
        [AttemptRecord(attempt=1, persona="implementer", verdict=OverallVerdict.PASS)],
    ]

    for history in histories:
        escalates = next_action(history, config) is NextAction.ESCALATE
        bound = exhausted_bound(history, config)
        assert (bound is not None) == escalates, (
            f"the reported bound disagrees with the ladder for {history!r}: "
            f"escalates={escalates}, bound={bound!r}"
        )


def test_the_line_the_operator_reads_is_the_ladders_own_sentence() -> None:
    """Trap 5's second half: the escalation carries the ladder's answer verbatim.

    The message is not asked to describe the bound — it is asked to print the
    sentence the ladder wrote. A renderer that formatted `dial` and `value` for
    itself would be a second place that has to be changed when a bound changes,
    and the two would disagree quietly.
    """
    config = VerificationConfig(max_attempts=3, max_judge_retries=2, debugger_cycles=0)
    history = [attempt(1), attempt(2), attempt(3)]

    bound = exhausted_bound(history, config)
    assert bound is not None

    message = operator_message(
        SendEscalationInput(
            workflow_id="w",
            epic_id=EPIC_ID,
            node_id=NODE,
            history_summary="three deterministic refusals",
            choices=[EscalationChoice.RETRY, EscalationChoice.KILL],
            timeout_s=3600,
            exhausted_bound=bound.describe(),
        )
    )

    assert bound.describe() in message, (
        f"the escalation does not carry the ladder's sentence:\n{message}"
    )


def test_the_renderer_derives_no_bound_of_its_own() -> None:
    """An escalation the ladder did not exhaust names no bound (trap 5).

    The falsifiable half of "renders, does not recompute": handed no sentence,
    the message prints none. A renderer that reached for the history — or for a
    default — would name a bound here, and a landing escalation, which has no
    ladder behind it at all, would start advertising one.
    """
    message = operator_message(
        SendEscalationInput(
            workflow_id="w",
            epic_id=EPIC_ID,
            node_id=NODE,
            history_summary="the landing queue rejected the PR twice",
            choices=[EscalationChoice.RETRY, EscalationChoice.KILL],
            timeout_s=3600,
        )
    )

    assert "ladder exhausted" not in message, (
        f"the renderer invented a bound nobody handed it:\n{message}"
    )
    for dial in ("max_attempts", "max_judge_retries", "debugger_cycles"):
        assert dial not in message, f"the renderer named {dial} unbidden:\n{message}"
