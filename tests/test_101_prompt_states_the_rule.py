"""US1 of 101: the attempt prompt carries the tmpfs-`HOME` rule as a runnable line.

The gate boundary gives a gate a `HOME` that is a fresh tmpfs
(`factory/verify/gates.py`), so anything a toolchain installed under `HOME`
during the attempt is gone by the time the gate runs and only the worktree
crosses. Nothing told the agent that, and the failure it produces reads as a
bad install: the tool says "just run the install", the agent runs it again,
harder.

What these tests defend is narrower and more specific than "the prompt mentions
the tmpfs", because the measurement behind this story says the obvious version
of that is *worse than silence*. An agent given no guidance at all found the
complete fix in three attempts. An agent given the mechanism stated correctly
but incompletely put the variable where the text said, stopped searching, and
failed 3/3 with the browser physically present in its worktree — because the
tool re-reads that variable from the environment on every invocation, and the
gate's environment is not the attempt's. So:

- T001 asserts the rule is *stated* — tmpfs, distinct from the attempt's `HOME`,
  and only the worktree persisting.
- T002 asserts it is *executable*, structurally rather than by quoting prose: a
  fenced shell block that carries a `VAR=path command` line, and the same
  variable named again in front of the gate command. Both halves, because either
  one alone is the failure that already happened.
- T003 asserts it is unconditional and short: present in every assembly variant
  (the assembler is handed no manifest, so no repository can declare it away),
  and under a stated length bound so it reads as an instruction rather than as
  background.

Plain unit tests over string fixtures, the way `test_prompt.py` is: the
assembler is pure, so the fixtures are text and nothing is read from disk.
"""

from __future__ import annotations

import inspect
import re
from typing import Any

from factory.usage.models import Termination
from factory.verify.models import (
    GateResult,
    GateStatus,
    OutputCheck,
    OverallVerdict,
    VerificationForm,
    VerificationResult,
)
from factory.workgraph.models import (
    STANDARDS_SOURCE_LANDING,
    StandardsResolution,
    WorkNode,
)
from factory.workgraph.prompt import (
    AttemptEvidence,
    build_attempt_prompt,
)

EPIC_ID = "demo-loans"

#: The heading the guidance renders under.
BOUNDARY_HEADING = "## What does not survive to gate time"

#: The bound T003 holds the guidance to, in characters. Stated here rather than
#: inline so the number is arguable in one place: it is a little under the
#: length of the prompt's own operator-question section, which is the longest
#: section the assembler writes itself. A guidance block that grows past this is
#: no longer an instruction an agent reads on the way past — it is background,
#: and background is what failed 3/3.
GUIDANCE_MAX_CHARS = 1600

# --- fixtures -----------------------------------------------------------------

SPEC_TEXT = """# Feature Specification: Library Loans

## User Scenarios & Testing

### User Story 1 - Borrow a book (Priority: P1)

A member borrows an available book and the catalogue records the loan.

**Acceptance Scenarios**:

1. **Given** a member with no loans, **When** they borrow, **Then** the loan is recorded.

## Requirements

### Functional Requirements

- **FR-001**: The catalogue MUST record every loan against the borrowing member.
"""

PLAN_TEXT = """# Implementation Plan: Library Loans

## Summary

One `loans` table is the system of record.
"""

TASKS_TEXT = """# Tasks: Library Loans

## Phase 1: Setup

- [ ] T001 Create the package skeleton

## Phase 2: User Story 1 - Borrow a book (Priority: P1)

- [ ] T002 [US1] Write tests/test_loans.py FIRST
- [ ] T003 [US1] Implement library/loans.py until T002 passes
"""


def make_node(**overrides: Any) -> WorkNode:
    fields: dict[str, Any] = {
        "id": "us1",
        "story_key": "US1",
        "persona": "implementer",
        "spec_ref": "demo-loans/US1",
        "requirement_keys": ["US1", "FR-001"],
        "depends_on": [],
    }
    fields.update(overrides)
    return WorkNode(**fields)


def build(**overrides: Any) -> str:
    kwargs: dict[str, Any] = {
        "node": make_node(),
        "epic_id": EPIC_ID,
        "spec_text": SPEC_TEXT,
        "plan_text": PLAN_TEXT,
        "tasks_text": TASKS_TEXT,
    }
    kwargs.update(overrides)
    return build_attempt_prompt(**kwargs)


def guidance_of(prompt: str) -> str:
    """The boundary section: its heading through the next section heading."""
    assert BOUNDARY_HEADING in prompt, "the prompt carries no gate-boundary section"
    start = prompt.index(BOUNDARY_HEADING)
    rest = prompt[start + len(BOUNDARY_HEADING) :]
    end = rest.find("\n## ")
    return BOUNDARY_HEADING + (rest if end == -1 else rest[:end])


def fenced_blocks(text: str) -> list[str]:
    """Every fenced block's body, in order."""
    return re.findall(r"^```[^\n]*\n(.*?)^```", text, flags=re.MULTILINE | re.DOTALL)


def failed_attempt() -> AttemptEvidence:
    """One prior attempt's wreckage, so the retry shape is covered too."""
    return AttemptEvidence(
        termination=Termination.COMPLETED,
        result=VerificationResult(
            epic_id=EPIC_ID,
            node_id="us1",
            attempt=1,
            form=VerificationForm.PHASE,
            verdict=OverallVerdict.FAIL,
            gate_results=[
                GateResult(
                    name="smoke",
                    command="npx playwright test",
                    status=GateStatus.FAIL,
                    exit_code=1,
                    duration_s=3.0,
                    output_tail="Looks like Playwright was just installed",
                )
            ],
            output_check=OutputCheck(
                write_scope="worktree",
                has_diff=True,
                expected_artifacts=[],
                artifacts_present=None,
                passed=True,
            ),
            judge=None,
            judge_unavailable=False,
            criteria_drift=False,
            criteria_sha256="c" * 64,
            spec_ref="demo-loans/US1",
            started_at="2026-08-05T10:00:00Z",
            finished_at="2026-08-05T10:20:00Z",
        ),
    )


# --- T001 (spec US1-S1, FR-001) -----------------------------------------------


def test_prompt_states_that_gate_home_is_a_tmpfs_and_only_the_worktree_persists() -> None:
    """The rule itself: a fresh tmpfs `HOME`, not the attempt's, and the worktree."""
    guidance = guidance_of(build())

    assert "tmpfs" in guidance
    assert "HOME" in guidance
    # Distinct from the attempt's own HOME — the fact that makes a warmed cache
    # irrelevant, and the one an agent cannot observe from inside its attempt.
    assert re.search(
        r"(different|not the same|distinct|separate)[^.]*`?HOME`?", guidance
    ), "the guidance does not say the gate's HOME differs from the attempt's"
    assert re.search(
        r"[Oo]nly the worktree[^.]*(persists|crosses|survives)", guidance
    ), "the guidance does not say only the worktree persists into the gate"


# --- T002 (spec US1-S2, FR-002, trap 1) ---------------------------------------


def test_guidance_carries_a_runnable_line_not_a_description_of_the_mechanism() -> None:
    """The story's whole point: an executable instruction, asserted structurally.

    Not "the prose mentions an environment variable" — that is exactly the
    half-documented shape that failed 3/3. The assertion is on a shell block
    carrying a `VAR=<path> <command>` invocation, which is a line an agent can
    paste.
    """
    guidance = guidance_of(build())

    blocks = fenced_blocks(guidance)
    assert blocks, "the guidance carries no fenced command block to run"

    assignment = re.compile(r"^([A-Z][A-Z0-9_]*)=(\S+)\s+(\S+)")
    runnable = [
        assignment.match(line.strip())
        for block in blocks
        for line in block.splitlines()
        if not line.strip().startswith("#")
    ]
    matched = [match for match in runnable if match is not None]
    assert matched, (
        "no line in the guidance is of the runnable form `VAR=path command`; "
        "a described mechanism is worse than no guidance at all"
    )

    variable, path, command = matched[0].groups()
    assert command, "the runnable line names no command to run"
    # The install goes under the worktree, which is the half that persists.
    assert "$PWD" in path or path.startswith((".", "./")), (
        f"{variable} points at {path!r}, which is not inside the worktree"
    )


def test_guidance_names_the_same_variable_in_front_of_the_gate_command() -> None:
    """Both halves. Installing into the worktree without carrying the variable
    into the gate command is the failure that already burned three attempts with
    the dependency physically present."""
    guidance = guidance_of(build())

    blocks = fenced_blocks(guidance)
    assignment = re.compile(r"^([A-Z][A-Z0-9_]*)=(\S+)\s+(\S+)")
    variables = {
        match.group(1)
        for block in blocks
        for line in block.splitlines()
        for match in [assignment.match(line.strip().lstrip("# "))]
        if match is not None
    }
    assert variables, "the guidance names no environment variable to carry"

    # The same variable appears twice: once installing, once in front of the
    # gate command the manifest declares.
    for variable in variables:
        occurrences = guidance.count(f"{variable}=")
        assert occurrences >= 2, (
            f"{variable} is set once only; the guidance must also show it in "
            "front of the gate command, because the tool re-reads it there"
        )
    assert "factory.yaml" in guidance, (
        "the guidance does not say where the gate command lives"
    )


# --- T003 (spec US1-S3, FR-003) -----------------------------------------------


def test_guidance_is_present_whatever_the_repository_declares() -> None:
    """A property of the boundary, not of the repo: no input can remove it.

    The assembler is handed no manifest at all — the strongest available form of
    "the repository declaring no caches changes nothing" — so this asserts both
    that the section survives every optional-input shape and that the signature
    carries no repository declaration it could be made conditional on.
    """
    variants = {
        "no standards declared": build(),
        "standards declared": build(standards=".specify/memory/constitution.md"),
        "standards resolved from the landing branch": build(
            standards=".specify/memory/constitution.md",
            standards_resolution=StandardsResolution(
                source=STANDARDS_SOURCE_LANDING, text="# Constitution\n"
            ),
        ),
        "a retry with prior evidence": build(prior_attempts=[failed_attempt()]),
    }
    for name, prompt in variants.items():
        assert prompt.count(BOUNDARY_HEADING) == 1, (
            f"the boundary guidance is missing or duplicated for {name}"
        )

    parameters = set(inspect.signature(build_attempt_prompt).parameters)
    assert not parameters & {"manifest", "gates", "config", "caches"}, (
        "the assembler takes a repository declaration, so the guidance could be "
        "made conditional on one"
    )


def test_guidance_stays_short_enough_to_read_as_an_instruction() -> None:
    """Under the stated bound. Length is the failure mode this story guards."""
    guidance = guidance_of(build())

    assert len(guidance) <= GUIDANCE_MAX_CHARS, (
        f"the guidance is {len(guidance)} characters, over the "
        f"{GUIDANCE_MAX_CHARS}-character bound; it has become background"
    )
