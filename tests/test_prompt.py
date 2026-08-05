"""What an attempt is told, and what it is never told (FR-006, R9).

`factory/workgraph/prompt.py` is the one place the factory writes to an agent.
It is pure by construction — text in, prompt out, no filesystem and no registry
(contracts/prompt-assembly.md) — so this file is a plain unit test over string
fixtures: a small spec, a small plan, a small tasks file, and the prompt they
compose into.

Five properties are what these tests defend:

- **The prompt is lossless.** Nothing here summarizes, paraphrases, or truncates
  its inputs: the story's section, the whole plan, and the task slice arrive in
  the prompt exactly as they were authored. Bounding prompt size is the
  operator's concern (story-sized slices), not a silent transform — and because
  the assembler is deterministic and lossless, SC-001's replay determinism
  extends to prompts.

- **The slice is the scope fence.** A node gets its own story's tasks and no
  others. Carrying the whole tasks file would invite the attempt to work a
  sibling's slice in a worktree that is not the sibling's, which is precisely
  the failure edge unlocking exists to prevent.

- **A missing input is a loud failure, never an omitted section.** The assembler
  never invents context. A story with no findable task slice fails assembly by
  name, which fails the dispatch before a key is issued — the one input the
  grammar cannot make structural, hence the one explicit rule.

- **The two loops are stated as what they are** (FR-012). The inner ralph
  contract is advisory fast feedback; the outer 002 ladder is the verdict.
  An agent that reads its own green gates as a pass is reading the prompt wrong,
  so the prompt says so in as many words.

- **Prior evidence travels verbatim, newest last** (002 FR-006). A retry that
  paraphrased its predecessor's traceback would hand the agent a summary of a
  bug instead of the bug, and the tails are the whole reason a second attempt
  is worth spending.

Two deliberate choices in the setup:

- **The fixtures are inline strings, not files.** Reading them from disk would
  make this suite test the reader; the module under test takes text, so the
  tests hand it text. The fixture spec/plan/tasks are composed from the same
  constants the assertions quote, so a golden expectation cannot drift from the
  input it was cut out of.

- **The tasks fixture hides a phase heading inside a fenced block.** Header
  scanning is fence-masked (R9), and the decoy proves it twice over: it does not
  end the slice it sits inside, and it does not become a slice for the story it
  names.

Written before `factory/workgraph/prompt.py` exists (T016 precedes T017): until
the module lands, every test here fails at import.
"""

from __future__ import annotations

from typing import Any

import pytest

from factory.usage.models import Termination
from factory.verify.models import (
    GateResult,
    GateStatus,
    JudgeOutcome,
    JudgeScenarioFinding,
    JudgeVerdict,
    OutputCheck,
    OverallVerdict,
    VerificationForm,
    VerificationResult,
)
from factory.workgraph.models import WorkNode
from factory.workgraph.prompt import (
    AttemptEvidence,
    PromptAssemblyError,
    build_attempt_prompt,
)
from factory.workgraph.worktree import branch_name

EPIC_ID = "demo-loans"

# --- fixture spec / plan / tasks ---------------------------------------------

STORY_ONE = """### User Story 1 - Borrow a book (Priority: P1)

A member borrows an available book and the catalogue records the loan against
them.

**Why this priority**: nothing else in the catalogue matters if a loan cannot be
recorded.

**Acceptance Scenarios**:

1. **Given** a member with no loans, **When** they borrow an available book, **Then** the catalogue records the loan against that member.
2. **Given** a book already on loan, **When** a second member borrows it, **Then** the request is refused naming the holder.
"""

STORY_TWO = """### User Story 2 - Return a book (Priority: P2)

A member returns a book and the catalogue clears the loan.

**Acceptance Scenarios**:

1. **Given** a member holding a loan, **When** they return the book, **Then** the loan is cleared.
"""

STORY_THREE = """### User Story 3 - Reserve a book (Priority: P3)

A member reserves a book that is currently on loan.

**Acceptance Scenarios**:

1. **Given** a book on loan, **When** a member reserves it, **Then** the reservation is queued.
"""

FR_ONE = "- **FR-001**: The catalogue MUST record every loan against the borrowing member."

FR_TWO = """- **FR-002**: The catalogue MUST refuse a loan for a book that is already on
  loan, naming the member who holds it."""

FR_THREE = "- **FR-003**: The catalogue MUST clear a loan when the book is returned."

SPEC_TEXT = f"""# Feature Specification: Library Loans

## User Scenarios & Testing

{STORY_ONE}
{STORY_TWO}
{STORY_THREE}
## Requirements

### Functional Requirements

{FR_ONE}
{FR_TWO}
{FR_THREE}
"""

PLAN_TEXT = """# Implementation Plan: Library Loans

## Summary

One `loans` table is the system of record; the catalogue reads it and never
caches it.

## Technical Context

**Language/Version**: Python 3.11+

**Storage**: one SQLite file, `loans.db`.
"""

#: A phase heading inside a fenced block: masked, so it neither ends the slice
#: it sits in nor becomes User Story 3's slice.
FENCED_DECOY = """```text
## Phase 9: User Story 3 - Reserve a book (Priority: P3)
```"""

TASKS_US1_SLICE = f"""## Phase 2: User Story 1 - Borrow a book (Priority: P1)

**Goal**: a loan is recorded against the member who borrowed the book.

- [ ] T002 [US1] Write tests/test_loans.py FIRST — records a loan, refuses a double loan
- [ ] T003 [US1] Implement library/loans.py until T002 passes

The tasks template renders phase headings like this one:

{FENCED_DECOY}
"""

TASKS_TEXT = f"""# Tasks: Library Loans

## Phase 1: Setup

- [ ] T001 Create the package skeleton

{TASKS_US1_SLICE}
## Phase 3: User Story 2 - Return a book (Priority: P2)

- [ ] T004 [US2] Write tests/test_returns.py FIRST
- [ ] T005 [US2] Implement the return path until T004 passes
"""

#: The prompt's own sections, in contracts/prompt-assembly.md order. `Standards`
#: and `Prior attempt evidence` are conditional and asserted separately.
SECTIONS = (
    "## Role and scope",
    "## The inner loop (advisory)",
    "## The outer loop (authoritative)",
    "## Story",
    "## Plan",
    "## Your task slice",
)

STANDARDS_SECTION = "## Standards"
EVIDENCE_SECTION = "## Prior attempt evidence"


# --- helpers ------------------------------------------------------------------


def make_node(**overrides: Any) -> WorkNode:
    """The node under assembly; override only what a test is about."""
    fields: dict[str, Any] = {
        "id": "us1",
        "story_key": "US1",
        "persona": "implementer",
        "spec_ref": "demo-loans/US1",
        "requirement_keys": ["US1", "FR-001", "FR-002"],
        "depends_on": [],
    }
    fields.update(overrides)
    return WorkNode(**fields)


def build(**overrides: Any) -> str:
    """A first attempt's prompt over the fixture texts."""
    kwargs: dict[str, Any] = {
        "node": make_node(),
        "epic_id": EPIC_ID,
        "spec_text": SPEC_TEXT,
        "plan_text": PLAN_TEXT,
        "tasks_text": TASKS_TEXT,
    }
    kwargs.update(overrides)
    return build_attempt_prompt(**kwargs)


def section_of(prompt: str, heading: str) -> str:
    """One section's text: its heading through the next section heading."""
    start = prompt.index(heading)
    rest = prompt[start + len(heading) :]
    end = rest.find("\n## ")
    return heading + (rest if end == -1 else rest[:end])


def make_gate(**overrides: Any) -> GateResult:
    fields: dict[str, Any] = {
        "name": "test",
        "command": "uv run pytest -q",
        "status": GateStatus.FAIL,
        "exit_code": 1,
        "duration_s": 12.5,
        "output_tail": "gate output",
    }
    fields.update(overrides)
    return GateResult(**fields)


def make_judge(feedback: str) -> JudgeVerdict:
    return JudgeVerdict(
        outcome=JudgeOutcome.RETRY,
        findings=[
            JudgeScenarioFinding(
                scenario="US1-S2", passed=False, reasoning="no refusal path"
            )
        ],
        feedback=feedback,
        judge_attempt=1,
        truncated_input=False,
        model_alias="judge",
    )


def make_result(
    attempt: int, gates: list[GateResult], judge: JudgeVerdict | None
) -> VerificationResult:
    return VerificationResult(
        epic_id=EPIC_ID,
        node_id="us1",
        attempt=attempt,
        form=VerificationForm.PHASE,
        gate_results=gates,
        output_check=OutputCheck(
            write_scope="worktree",
            has_diff=True,
            expected_artifacts=[],
            artifacts_present=None,
            passed=True,
        ),
        judge=judge,
        verdict=OverallVerdict.FAIL,
        judge_unavailable=False,
        criteria_drift=False,
        criteria_sha256="c" * 64,
        spec_ref="demo-loans/US1",
        started_at="2026-08-05T10:00:00Z",
        finished_at="2026-08-05T10:20:00Z",
    )


#: Planted evidence, quoted byte-for-byte by the assertions below.
ATTEMPT_ONE_TAIL = "ATTEMPT-1-GATE-TAIL\n  E   assert loans == 1\n"
ATTEMPT_TWO_TAIL = "ATTEMPT-2-GATE-TAIL\n  E   IndexError: list index out of range\n"
PASSING_TAIL = "PASSING-GATE-TAIL-MUST-NOT-APPEAR"
JUDGE_FEEDBACK = (
    "ATTEMPT-2-JUDGE-FEEDBACK: scenario US1-S2 is not covered — nothing refuses\n"
    "a second loan of the same book."
)


def prior_two_attempts() -> tuple[AttemptEvidence, AttemptEvidence]:
    """Two failed attempts, oldest first, each with distinguishable evidence."""
    first = AttemptEvidence(
        termination=Termination.COMPLETED,
        result=make_result(
            attempt=1,
            gates=[make_gate(output_tail=ATTEMPT_ONE_TAIL)],
            judge=None,
        ),
    )
    second = AttemptEvidence(
        termination=Termination.TIMEOUT,
        result=make_result(
            attempt=2,
            gates=[
                make_gate(
                    name="lint",
                    command="ruff check .",
                    status=GateStatus.PASS,
                    exit_code=0,
                    output_tail=PASSING_TAIL,
                ),
                make_gate(output_tail=ATTEMPT_TWO_TAIL),
            ],
            judge=make_judge(JUDGE_FEEDBACK),
        ),
    )
    return first, second


# --- golden assembly ----------------------------------------------------------


def test_sections_appear_once_each_in_contract_order() -> None:
    """The shape of contracts/prompt-assembly.md § Prompt shape, in that order."""
    prompt = build()

    for heading in SECTIONS:
        assert prompt.count(heading) == 1, f"{heading} appears {prompt.count(heading)}x"

    positions = [prompt.index(heading) for heading in SECTIONS]
    assert positions == sorted(positions), "sections are out of contract order"


def test_role_section_names_the_epic_the_node_and_its_branch() -> None:
    """The slice contract is parameterized by story/epic ids, not generic prose."""
    role = section_of(build(), "## Role and scope")

    assert EPIC_ID in role
    assert "us1" in role
    assert branch_name(EPIC_ID, "us1") in role


def test_story_sections_are_verbatim_and_scoped_to_this_node() -> None:
    """The node's story and its `implements` FRs, whole; nobody else's."""
    prompt = build()

    assert STORY_ONE.strip() in prompt
    assert FR_ONE in prompt
    assert FR_TWO in prompt

    # A sibling story and an FR this node does not implement are not this node's
    # business: requirement_keys is the fence, and it was fixed at derivation.
    assert STORY_TWO.strip() not in prompt
    assert STORY_THREE.strip() not in prompt
    assert FR_THREE not in prompt


def test_plan_is_carried_whole() -> None:
    """The full plan is the clarified context set — no summary, no excerpt."""
    assert PLAN_TEXT.strip() in build()


def test_task_slice_is_this_story_phase_and_nothing_else() -> None:
    """Fence-masked header scan: the slice ends at the next real heading."""
    prompt = build()

    assert TASKS_US1_SLICE.strip() in prompt
    assert FENCED_DECOY in prompt, "a fenced heading does not end the slice"

    assert "T001" not in prompt, "the setup phase is not this node's slice"
    assert "T004" not in prompt, "a sibling story's slice never travels"
    assert "T005" not in prompt


def test_assembly_is_deterministic() -> None:
    """Same inputs, same bytes — SC-001's replay determinism extends to prompts."""
    first = build()
    second = build()
    assert first == second

    # Equal-valued but distinct inputs must also agree: nothing in assembly may
    # depend on object identity, clock, or iteration order.
    evidence = prior_two_attempts()
    assert build(prior_attempts=list(evidence)) == build(
        prior_attempts=list(prior_two_attempts())
    )


# --- the two loops (FR-012) ---------------------------------------------------


def test_inner_loop_is_stated_as_advisory_fast_feedback() -> None:
    """The ralph contract, generalized to the slice and demoted to advice."""
    inner = section_of(build(), "## The inner loop (advisory)")

    assert "test first" in inner.lower()
    assert "commit" in inner.lower()
    assert "gate" in inner.lower()
    assert "fast feedback" in inner.lower()


def test_outer_loop_is_stated_as_the_authoritative_verdict() -> None:
    """FR-012 in the prompt's own words: self-reported success carries no weight."""
    outer = section_of(build(), "## The outer loop (authoritative)")

    assert "carries no weight" in outer
    assert "Do not weaken tests" in outer


# --- standards directive (R11) ------------------------------------------------


def test_standards_directive_is_absent_when_the_repo_declares_none() -> None:
    prompt = build()

    assert STANDARDS_SECTION not in prompt
    assert "STANDARDS.md" not in prompt


def test_standards_directive_names_the_declared_path_and_says_obey_it() -> None:
    prompt = build(standards="docs/STANDARDS.md")

    section = section_of(prompt, STANDARDS_SECTION)
    assert "docs/STANDARDS.md" in section
    assert "obey" in section.lower()

    # Before the story: the agent reads the standards before it writes code.
    assert (
        prompt.index("## The outer loop (authoritative)")
        < prompt.index(STANDARDS_SECTION)
        < prompt.index("## Story")
    )


# --- retry evidence (002 FR-006) ----------------------------------------------


def test_first_attempt_carries_no_evidence_section() -> None:
    """Nothing failed yet; an empty evidence section would be invented context."""
    assert EVIDENCE_SECTION not in build()


def test_retry_carries_failed_gate_tails_and_judge_feedback_verbatim() -> None:
    prompt = build(prior_attempts=prior_two_attempts())

    assert prompt.index(EVIDENCE_SECTION) > prompt.index("## Your task slice")
    evidence = prompt[prompt.index(EVIDENCE_SECTION) :]

    assert ATTEMPT_ONE_TAIL in evidence
    assert ATTEMPT_TWO_TAIL in evidence
    assert JUDGE_FEEDBACK in evidence

    # The termination class is part of the evidence: an attempt that timed out
    # left different wreckage than one that ran to the end.
    assert Termination.COMPLETED.value in evidence
    assert Termination.TIMEOUT.value in evidence


def test_retry_evidence_is_ordered_oldest_first() -> None:
    """Newest last — the attempt just made is the one nearest the instruction."""
    prompt = build(prior_attempts=prior_two_attempts())

    assert prompt.index(ATTEMPT_ONE_TAIL) < prompt.index(ATTEMPT_TWO_TAIL)
    assert prompt.index(ATTEMPT_TWO_TAIL) < prompt.index(JUDGE_FEEDBACK)


def test_passing_gate_output_is_not_carried() -> None:
    """Failure evidence is the point; a green gate's output is noise."""
    assert PASSING_TAIL not in build(prior_attempts=prior_two_attempts())


# --- loud failures ------------------------------------------------------------


def test_story_without_a_task_slice_fails_naming_the_story() -> None:
    """FR-006's one authored-missing input: no slice, no dispatch."""
    node = make_node(id="us3", story_key="US3", requirement_keys=["US3"])

    with pytest.raises(PromptAssemblyError) as excinfo:
        build(node=node)

    message = str(excinfo.value)
    assert "US3" in message
    assert "task" in message.lower()


def test_missing_story_section_fails_naming_the_story() -> None:
    """The assembler never invents context, structural guarantees notwithstanding."""
    node = make_node(id="us9", story_key="US9", requirement_keys=["US9"])
    tasks = TASKS_TEXT + (
        "\n## Phase 4: User Story 9 - Audit the catalogue (Priority: P3)\n\n"
        "- [ ] T006 [US9] Write tests/test_audit.py FIRST\n"
    )

    with pytest.raises(PromptAssemblyError) as excinfo:
        build(node=node, tasks_text=tasks)

    assert "US9" in str(excinfo.value)


def test_unknown_requirement_key_fails_naming_the_requirement() -> None:
    """A node cannot be told to implement an FR the spec does not declare."""
    node = make_node(requirement_keys=["US1", "FR-404"])

    with pytest.raises(PromptAssemblyError) as excinfo:
        build(node=node)

    assert "FR-404" in str(excinfo.value)
