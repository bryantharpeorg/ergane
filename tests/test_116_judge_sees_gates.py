"""The judge is shown what the factory measured, and nothing else changes.

116-US1. `judge_required(gate_results, output_check, criteria)` is the guard the
workflow puts immediately in front of the judge: it takes the gate results, uses
them to decide whether a verdict is still open, and then the caller assembles a
prompt that has no room for them. The gate results are in the caller's hand on
the line before, and they are thrown away — so a scenario whose Then-clause is a
runtime outcome ("Then the suite passes") is handed to a model told that if the
evidence is not in the diff, the scenario does not pass. It fails, correctly,
forever: no patch can contain a test run.

Five claims are asserted here, and four of them are about restraint rather than
about the new section:

- **The section carries the measurement** (US1-S1, FR-001): every gate's name,
  its recorded status and its exit code, because those three are what a
  Then-clause can name.
- **A failing gate carries its output tail, bounded** (US1-S2, FR-002). No
  failing gate can reach the judge today — `judge_required` returns True only
  when every gate passed — but the assembler may not be written as though that
  guarantee were load-bearing, and an unbounded 32 KiB tail would spend on one
  gate what the diff needs.
- **Absent gate results mean today's prompt, byte for byte** (US1-S3, FR-003,
  plan trap 3). The whole existing judge corpus compares assembled prompts; a
  section rendered unconditionally would rewrite all of it and bury the change.
  The control below is a golden assembly, so "identical" is a fact about bytes
  rather than about the absence of a heading.
- **The section is spent from the same allowance the diff is** (US1-S4, FR-004,
  plan trap 4). `prepare_diff` fits the diff under `DIFF_INPUT_LIMIT`; a section
  added outside that accounting would silently take the diff's share and
  truncate evidence nobody disclosed.
- **Order is not cosmetic** (US1-S5, FR-005): the standard is established before
  the evidence measured against it, so the gate results sit after the scenarios
  and before the diff.

And one claim about the instruction, which is the difference between this story
working and this story being mechanical (plan trap 1): a prompt that carries the
gate results while still saying "if the evidence is not in the diff, the
scenario does not pass" produces a judge that reads the measurement and then
explains why it may not use it. The widening is to *named measurements* and to
nothing else — the looks-reasonable prohibition stays (plan trap 2).
"""

from __future__ import annotations

from typing import Any

import pytest

from factory.verify.diffbounds import assembled
from factory.verify.judge import (
    DIFF_INPUT_LIMIT,
    GATE_OUTPUT_TAIL_LIMIT,
    GATE_SECTION_HEADING,
    SYSTEM_PROMPT,
    build_prompt,
)
from factory.verify.models import (
    CriteriaSet,
    GateResult,
    GateStatus,
    Requirement,
    RequirementKind,
    Scenario,
)

# --- the criteria under judgment ---------------------------------------------
#
# Deliberately small, and hand-built: the control below quotes the whole
# assembled user message literally, and a golden nobody can read is a golden
# nobody maintains.

SCENARIO = Scenario(
    scenario_id="US1-S1",
    steps=[
        "**Given** a set of gate results and a criteria set",
        "**When** the judge prompt is assembled",
        "**Then** the prompt carries each gate's name, status and exit code",
    ],
    raw_text=(
        "1. **Given** a set of gate results and a criteria set, **When** the "
        "judge prompt is assembled, **Then** the prompt carries each gate's "
        "name, status and exit code."
    ),
)

STORY = Requirement(
    key="US1",
    kind=RequirementKind.STORY,
    title="The judge is shown the gate results",
    priority="P1",
    body=(
        "As an operator, the judge scores a scenario whose Then-clause is a "
        "runtime outcome using the factory's own measurement of that outcome."
    ),
    scenarios=[SCENARIO],
)

FUNCTIONAL = Requirement(
    key="FR-001",
    kind=RequirementKind.FUNCTIONAL,
    title=None,
    priority=None,
    body=(
        "The judge prompt MUST carry each gate's name, status and exit code for "
        "the attempt being scored."
    ),
    scenarios=[],
)

CRITERIA = CriteriaSet(
    feature="116-the-judge-scores-against-what-the-factory-measured",
    spec_ref="judge-sees-gates/shown-the-measurement",
    requirements=[STORY, FUNCTIONAL],
    source_path="specs/116-the-judge-scores-against-what-the-factory-measured/spec.md",
    source_sha256="c0ffee" + "0" * 58,
    snapshotted_at="2026-08-28T10:00:00Z",
)

SMALL_DIFF = (
    "diff --git a/factory/verify/judge.py b/factory/verify/judge.py\n"
    "index 1111111..2222222 100644\n"
    "--- a/factory/verify/judge.py\n"
    "+++ b/factory/verify/judge.py\n"
    "@@ -248,1 +248,1 @@ def build_prompt(\n"
    "-def build_prompt(criteria, diff_text, *, prior_feedback=None):\n"
    "+def build_prompt(criteria, diff_text, *, prior_feedback=None, gate_results=None):\n"
)

#: What `prepare_diff` puts in front of the judge for `SMALL_DIFF`: under the
#: limit the diff is passed through untouched behind its always-complete file
#: listing, so the golden can state it exactly.
SMALL_DIFF_PREPARED = (
    "Changed files (1):\n  factory/verify/judge.py | +1 -1\n\n" + SMALL_DIFF
)

SCENARIOS_HEADING = "# Acceptance scenarios"
DIFF_HEADING = "# Diff produced by the node"


# --- gate fixtures ------------------------------------------------------------


def gate(
    name: str,
    status: GateStatus = GateStatus.PASS,
    *,
    exit_code: int | None = 0,
    command: str | None = None,
    output_tail: str = "",
) -> GateResult:
    return GateResult(
        name=name,
        command=command if command is not None else f"uv run {name}",
        status=status,
        exit_code=exit_code,
        duration_s=1.5,
        output_tail=output_tail,
    )


GREEN_GATES = [
    gate("test", command="uv run pytest -q", output_tail="12 passed in 0.14s\n"),
    gate("lint", command="uv run ruff check", output_tail="All checks passed!\n"),
]


def user_message(**kwargs: Any) -> str:
    return build_prompt(CRITERIA, SMALL_DIFF, **kwargs).messages[1]["content"]


# --- T001 (US1-S1, FR-001) ----------------------------------------------------


def test_the_prompt_carries_each_gates_name_status_and_exit_code() -> None:
    """The three facts a Then-clause can name, for every gate that ran."""
    content = user_message(gate_results=GREEN_GATES)

    assert GATE_SECTION_HEADING in content, (
        "the assembled prompt has no gate-results section; the judge is still "
        "guessing at outcomes this factory already measured (FR-001)"
    )
    for measured in GREEN_GATES:
        assert measured.name in content, f"gate {measured.name!r} is not named"
        assert measured.command in content, (
            f"gate {measured.name!r} is named without the command it ran; a "
            "gate name alone does not say what was measured"
        )

    section = content[content.index(GATE_SECTION_HEADING) :]
    for measured in GREEN_GATES:
        heading = next(
            line
            for line in section.splitlines()
            if line.startswith("## ") and measured.name in line
        )
        assert "PASS" in heading, (
            f"gate {measured.name!r} is carried without its recorded status: {heading!r}"
        )
        assert "0" in heading, (
            f"gate {measured.name!r} is carried without its exit code: {heading!r}"
        )


def test_a_gate_that_never_exited_says_so_rather_than_reading_as_zero() -> None:
    """`exit_code` is None exactly when there was no exit to read — a timeout, or
    a `factory.yaml` the config gate could not use. Rendering that as `0` would
    put the one word a judge reads as success next to a gate that never ran."""
    content = user_message(
        gate_results=[gate("test", GateStatus.TIMEOUT, exit_code=None)]
    )

    section = content[content.index(GATE_SECTION_HEADING) :]
    heading = next(
        line for line in section.splitlines() if line.startswith("## ") and "test" in line
    )
    assert "TIMEOUT" in heading
    assert "0" not in heading, (
        f"a gate with no exit code reads as having exited 0: {heading!r}"
    )


# --- T002 (US1-S2, FR-002) ----------------------------------------------------


def test_a_failing_gate_carries_its_output_tail_bounded_to_a_stated_length() -> None:
    """A failing gate cannot reach the judge today — `judge_required` returns
    True only when every gate passed — and the assembler must not be written as
    though that guarantee were load-bearing (US1-S2). `output_tail` is up to
    32 KiB, so it is carried bounded and the bound is said out loud."""
    ending = "E   assert 1 == 2\nFAILED tests/test_thing.py::test_it\n"
    long_tail = "noise that scrolled past\n" * 4_000 + ending
    assert len(long_tail) > GATE_OUTPUT_TAIL_LIMIT

    content = user_message(
        gate_results=[
            gate("test", GateStatus.FAIL, exit_code=1, output_tail=long_tail)
        ]
    )
    section = content[content.index(GATE_SECTION_HEADING) :]

    assert ending in section, (
        "the bound kept the head of the recorded output; a failure is at the "
        "end, which is why this is a tail"
    )
    assert long_tail not in section, "the 32 KiB tail was carried whole"
    assert str(GATE_OUTPUT_TAIL_LIMIT) in section, (
        "the tail is bounded without stating the length it was bounded to "
        "(FR-002); an unstated elision reads as an agent that produced nothing"
    )

    noise = "noise that scrolled past\n"
    assert content.count(noise) * len(noise) <= GATE_OUTPUT_TAIL_LIMIT, (
        "more of the recorded output reached the prompt than the stated bound "
        "allows"
    )


def test_the_bound_is_enforced_on_a_tail_longer_than_it() -> None:
    """The carried tail is never longer than the stated length, and the elision
    is marked — an unmarked cut is indistinguishable from output that stopped."""
    long_tail = "x" * (GATE_OUTPUT_TAIL_LIMIT * 3)
    content = user_message(
        gate_results=[
            gate("test", GateStatus.FAIL, exit_code=1, output_tail=long_tail)
        ]
    )

    assert "x" * (GATE_OUTPUT_TAIL_LIMIT + 1) not in content, (
        f"more than {GATE_OUTPUT_TAIL_LIMIT} characters of the recorded tail "
        "reached the prompt; the bound does not hold"
    )
    assert "x" * GATE_OUTPUT_TAIL_LIMIT in content, (
        "the bound cut more than it was declared to"
    )
    assert "elided" in content or "truncated" in content, (
        "the tail was cut without a marker saying so"
    )


def test_a_passing_gate_carries_no_output_tail() -> None:
    """FR-002 bounds the tail to gates that did not pass. A green suite's
    output proves nothing a recorded PASS does not already prove, and every
    byte of it is a byte the diff does not get."""
    content = user_message(gate_results=GREEN_GATES)

    assert "12 passed in 0.14s" not in content, (
        "a passing gate's output tail is carried; PASS is the measurement, and "
        "the transcript behind it is not"
    )


# --- T003 (US1-S3, FR-003) — the control, plan trap 3 -------------------------


def golden_user_message() -> str:
    """Today's assembled user message, stated rather than computed.

    This is the control FR-003 asks for: byte-identity with the prompt the
    current code path produces, written out so that a section rendered
    unconditionally — or a stray blank line — fails here instead of quietly
    rewriting every prompt comparison in the judge's existing test corpus.
    """
    return (
        "# Requirements under verification\n"
        "\n"
        f"Feature: {CRITERIA.feature}\n"
        f"Spec ref: {CRITERIA.spec_ref}\n"
        "\n"
        f"## {STORY.key} — {STORY.title} (Priority: {STORY.priority})\n"
        "\n"
        f"{STORY.body}\n"
        "\n"
        f"## {FUNCTIONAL.key}\n"
        "\n"
        f"{FUNCTIONAL.body}\n"
        "\n"
        f"{SCENARIOS_HEADING}\n"
        "\n"
        "Score each of these on its own and echo its id exactly as written here.\n"
        "\n"
        f"## {SCENARIO.scenario_id}\n"
        "\n"
        f"{SCENARIO.raw_text}\n"
        "\n"
        f"{DIFF_HEADING}\n"
        "\n"
        f"{SMALL_DIFF_PREPARED}"
    )


def test_with_no_gate_results_the_prompt_is_byte_identical_to_todays() -> None:
    """The section is additive, and its absence is the current behaviour."""
    assert user_message() == golden_user_message()


@pytest.mark.parametrize("absent", [None, [], ()])
def test_every_spelling_of_no_gate_results_assembles_todays_prompt(
    absent: object,
) -> None:
    """`None` and an empty sequence are the same fact — nothing was measured to
    show — and neither may grow a heading over an empty list."""
    assert user_message(gate_results=absent) == golden_user_message()
    assert GATE_SECTION_HEADING not in user_message(gate_results=absent)


def test_the_system_message_is_unchanged_by_the_presence_of_gate_results() -> None:
    """The instruction is one constant, sent every time. A system prompt that
    varied with the gate results would be a second place the judge's standard is
    decided."""
    with_gates = build_prompt(CRITERIA, SMALL_DIFF, gate_results=GREEN_GATES)
    without = build_prompt(CRITERIA, SMALL_DIFF)

    assert with_gates.messages[0] == without.messages[0]
    assert with_gates.messages[0] == {"role": "system", "content": SYSTEM_PROMPT}


# --- T004 (US1-S4, FR-004, plan trap 4) ---------------------------------------


def diff_assembling_to(target: int) -> str:
    """A one-file diff whose assembly measures exactly `target` bytes.

    Measured with `diffbounds.assembled` — the same measurement `prepare_diff`
    compares against the limit — so a test about the accounting does not invent
    a second way of counting.
    """
    header = (
        "diff --git a/big.py b/big.py\n"
        "index 1111111..2222222 100644\n"
        "--- a/big.py\n"
        "+++ b/big.py\n"
        "@@ -0,0 +1,2001 @@\n"
    )
    body = "".join(f"+line {index:06d}\n" for index in range(2_000))
    stem = header + body + "+\n"

    pad = target - assembled(stem)[0]
    assert pad >= 0, f"the stem alone already measures more than {target}"
    # Padding an existing line changes no line count, so the file listing — and
    # therefore the assembly — grows by exactly `pad` bytes.
    return header + body + "+" + "x" * pad + "\n"


def test_the_gate_section_is_spent_from_the_diffs_own_allowance() -> None:
    """A diff that fits alone must be abridged once a gate section rides beside
    it — the section is counted by the same measurement, against the same limit
    (FR-004). A section outside that accounting would take the diff's share and
    truncate evidence nobody disclosed."""
    at_the_limit = diff_assembling_to(DIFF_INPUT_LIMIT)
    assert assembled(at_the_limit)[0] == DIFF_INPUT_LIMIT

    alone = build_prompt(CRITERIA, at_the_limit)
    assert alone.truncated_input is False, (
        "the control diff was already over the limit; this test proves nothing"
    )

    beside_gates = build_prompt(CRITERIA, at_the_limit, gate_results=GREEN_GATES)
    assert beside_gates.truncated_input is True, (
        "the gate section was added without being counted: the same diff fits "
        "whether or not a section was placed beside it, so the section is being "
        "spent from somewhere nobody is measuring (FR-004)"
    )


def test_the_gate_section_and_the_diff_together_stay_under_the_input_limit() -> None:
    """The accounting stated as the inequality it is. `prepare_diff` fits the
    diff under `DIFF_INPUT_LIMIT`; with a section beside it, the two together
    are what must fit — read through the limit's existing name, never restated
    as a number here."""
    content = build_prompt(
        CRITERIA, diff_assembling_to(DIFF_INPUT_LIMIT), gate_results=GREEN_GATES
    ).messages[1]["content"]

    evidence = content[content.index(GATE_SECTION_HEADING) :]
    assert len(evidence.encode("utf-8")) <= DIFF_INPUT_LIMIT, (
        "the gate section plus the diff run past the judge's input limit; the "
        "section escaped the accounting the diff is held to (FR-004)"
    )


# --- T005 (US1-S5, FR-005) ----------------------------------------------------


def test_the_gate_results_appear_after_the_scenarios_and_before_the_diff() -> None:
    """The order is not cosmetic: the standard is established before the
    evidence measured against it, and the diff stays last because it is the only
    part that may have been cut."""
    content = user_message(gate_results=GREEN_GATES)

    scenarios = content.index(SCENARIOS_HEADING)
    gates = content.index(GATE_SECTION_HEADING)
    diff = content.index(DIFF_HEADING)

    assert scenarios < gates < diff, (
        "the assembled sections run scenarios/gates/diff in the wrong order: "
        f"{scenarios}, {gates}, {diff} (FR-005)"
    )


def test_prior_feedback_still_precedes_the_diff_when_gates_are_carried() -> None:
    """FR-006 of 002 put the previous attempt's feedback ahead of the diff, and
    US1 may not reorder it out from under that claim."""
    content = build_prompt(
        CRITERIA,
        SMALL_DIFF,
        prior_feedback="US1-S1 fails: the section is never rendered.",
        gate_results=GREEN_GATES,
    ).messages[1]["content"]

    feedback = content.index("# Feedback on the previous attempt")
    assert content.index(SCENARIOS_HEADING) < feedback < content.index(DIFF_HEADING)
    assert content.index(GATE_SECTION_HEADING) < content.index(DIFF_HEADING)


# --- T006 (FR-001, plan traps 1 and 2) ----------------------------------------


def flattened_prompt() -> str:
    """`SYSTEM_PROMPT` with its line wrapping removed, so an assertion about a
    phrase is not an assertion about where the author broke the line."""
    return " ".join(SYSTEM_PROMPT.split())


def test_the_instruction_names_the_gate_results_as_this_factorys_measurement() -> None:
    """Plan trap 1. A section added while the instruction still says "if the
    evidence is not in the diff, the scenario does not pass" produces a judge
    that reads the measurement and then explains why it may not use it."""
    flat = flattened_prompt().lower()

    assert "gate result" in flat, (
        "the judge's instructions never mention the gate results; a section the "
        "instruction does not authorise is a section the judge will discount"
    )
    assert "measurement" in flat, (
        "the instructions do not say what the gate results are — this factory's "
        "own measurement of this attempt, not a summary of the diff"
    )
    assert "predict" in flat or "speculat" in flat or "guess" in flat, (
        "the instructions never forbid scoring a gate against what the judge "
        "predicts that gate would do, which is the failure this story exists for"
    )


def test_the_instruction_scores_a_then_clause_naming_a_gate_against_the_record() -> None:
    """The widening stated as the rule it is: a scenario whose Then-clause names
    a gate outcome is scored against the recorded result for that gate."""
    flat = flattened_prompt().lower()

    assert "then-clause" in flat or "then clause" in flat, (
        "the instructions never say what to do with a Then-clause that names a "
        "runtime outcome — the scenario shape this story exists to make scoreable"
    )
    assert "recorded" in flat, (
        "the instructions do not point the judge at the recorded result"
    )


def test_the_instruction_still_refuses_to_pass_on_a_general_impression() -> None:
    """Plan trap 2. The sentence being widened exists to stop the judge
    rubber-stamping; the widening is to named measurements, not to impressions."""
    assert "Never pass a scenario because the change looks reasonable overall." in (
        SYSTEM_PROMPT
    ), (
        "the looks-reasonable prohibition was weakened or removed while widening "
        "what counts as evidence; that trade is how this fix becomes a false PASS"
    )
    assert "individually" in SYSTEM_PROMPT, (
        "per-scenario scoring is no longer demanded; holistic passing is what "
        "the strict parser exists to refuse"
    )
