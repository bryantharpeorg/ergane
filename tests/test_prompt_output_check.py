"""What a failed output check tells the next attempt (045 US3, FR-005).

`033-ergane-install/us2` burned four attempts on 2026-08-15 against a
byte-identical `has_diff: false`, and not one of the four retry prompts said
so. The mechanism is not subtle: `_attempt_block` renders failing gates and
judge feedback, an output-check failure produces neither — the judge is
correctly skipped when the check fails (`models.judge_required`) — so the block
fell through to `_NOTHING_FAILED_LOUDLY` and the next attempt was told, in as
many words, that nothing failed loudly. US1 and US2 have since added two more
ways for the check to fail (`hygiene_violations`, `size_refusal`) and both were
invisible for exactly the same reason.

So these tests are mostly about a defect class rather than about a string: a
rendering test that only asserts "some sentence appears somewhere in the
prompt" passes for a renderer that hardcodes the sentence, and a renderer that
hardcodes the sentence is the same blind retry with more words. Four properties
are asserted against that:

- **The evidence rendered is this attempt's.** Two prior attempts carrying
  *different* failure shapes must render their own and only their own, which no
  hardcoded block can do.
- **The values rendered are the record's, not the module's.** The size case
  pins a `limit_bytes` deliberately different from `diffbounds.DIFF_INPUT_LIMIT`
  and asserts the constant's own value is absent: a refusal stored by a
  deployment whose cap has since moved has to render the cap it was refused
  under, which is why `DiffSizeRefusal` carries the limit at all.
- **Nothing is invented.** The empty-diff sentence must not appear for an
  attempt whose diff was present, and no output-check block may appear for an
  attempt whose check passed — asserted byte-for-byte against
  `EVIDENCE_SECTION_GOLDEN`, captured from the corpus in `tests/test_prompt.py`
  before this story changed anything (FR-004, US3-S4).
- **`_NOTHING_FAILED_LOUDLY` is gone from this path.** It is the sentence the
  four attempts were shown, and its continued presence over a failed output
  check would mean the block is still silent whatever else was added around it.

The corpus is `tests/test_prompt.py`'s — the same fixture spec, plan, tasks and
prior attempts — so the parity assertion is against the assembly the rest of the
suite already pins, not against a second one written for this story.

## Proved by mutation, not by assertion count

The failure this repository pays most for is a test that cannot fail, and a
prompt-rendering test is the shape most prone to it. So each property above was
checked by breaking the production code five ways and watching which tests
noticed. Verbatim, run against `05ffc3f`, reverting `factory/workgraph/prompt.py`
between each:

    === M1: the block ignores the record and always says 'no diff' ===
    FAILED tests/test_prompt_output_check.py::test_a_failed_check_does_not_borrow_another_shape_s_words
    FAILED tests/test_prompt_output_check.py::test_every_offending_path_and_its_rule_are_listed_verbatim
    FAILED tests/test_prompt_output_check.py::test_each_attempt_renders_its_own_output_check_and_no_other_s
    FAILED tests/test_prompt_output_check.py::test_a_size_refusal_names_the_total_the_limit_and_the_files
    FAILED tests/test_prompt_output_check.py::test_the_limit_rendered_is_the_one_the_record_carries
    FAILED tests/test_prompt_output_check.py::test_hygiene_and_size_render_together_when_both_were_recorded
    FAILED tests/test_prompt_output_check.py::test_missing_artifacts_are_named - ...
    FAILED tests/test_prompt_output_check.py::test_a_failure_with_no_rendered_reason_still_says_the_check_refused_it
    8 failed, 4 passed in 0.05s

    === M2: the module's constant is rendered instead of the record's limit ===
    FAILED tests/test_prompt_output_check.py::test_a_size_refusal_names_the_total_the_limit_and_the_files
    FAILED tests/test_prompt_output_check.py::test_the_limit_rendered_is_the_one_the_record_carries
    2 failed, 10 passed in 0.04s

    === M3: the block is emitted unconditionally ===
    FAILED tests/test_prompt_output_check.py::test_a_passing_output_check_renders_byte_identically_to_today
    1 failed, 39 passed in 0.05s

    === M4: the hygiene branch is dropped ===
    FAILED tests/test_prompt_output_check.py::test_every_offending_path_and_its_rule_are_listed_verbatim
    FAILED tests/test_prompt_output_check.py::test_each_attempt_renders_its_own_output_check_and_no_other_s
    FAILED tests/test_prompt_output_check.py::test_hygiene_and_size_render_together_when_both_were_recorded
    3 failed, 9 passed in 0.04s

    === M5: the block is appended after the judge instead of before it ===
    FAILED tests/test_prompt_output_check.py::test_the_output_check_evidence_sits_between_the_gates_and_the_judge
    1 failed, 11 passed in 0.03s

M1 is the important one. It is the renderer this story could most plausibly have
shipped — one honest-looking sentence for every failed check — and it satisfies
"the prompt says something about the output check" completely. Eight tests
refuse it, because a sentence is not evidence: the paths, the rules and the byte
counts an attempt needs are in the record or they are nowhere. M3 is the parity
half: the golden is what notices a block that renders over a check that passed.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Sequence

from factory.usage.models import Termination
from factory.verify.diffbounds import DIFF_INPUT_LIMIT
from factory.verify.models import (
    DiffFileSize,
    DiffSizeRefusal,
    GateStatus,
    HygieneViolation,
    OutputCheck,
)
from factory.workgraph.prompt import AttemptEvidence
from tests.test_prompt import (
    ATTEMPT_ONE_TAIL,
    EVIDENCE_SECTION,
    build,
    make_gate,
    make_judge,
    make_result,
    prior_two_attempts,
)

#: The sentence a failed output check rendered as before this story: the four
#: `has_diff: false` attempts of 2026-08-15 were each handed exactly this.
NOTHING_FAILED_LOUDLY = "No failing gate output and no judge feedback were recorded"

#: The evidence section the corpus in `tests/test_prompt.py` renders when every
#: output check passed, captured from the tree at `5e38c19` — before this story
#: touched `_attempt_block` — by rendering `build(prior_attempts=
#: prior_two_attempts())` and slicing from `EVIDENCE_SECTION`. It is inline
#: rather than a file for the reason that module already states about its own
#: fixtures: read from disk, this suite would be testing the reader.
EVIDENCE_SECTION_GOLDEN = """\
## Prior attempt evidence

Earlier attempts at this node did not pass. Their evidence is reproduced
verbatim, oldest first — the last block is the attempt just made. Read it
as what actually happened, not as a summary of it:

### Attempt 1 — terminated `completed`, verdict FAIL

Gate `test` (`uv run pytest -q`) — FAIL, exit 1:

```text
ATTEMPT-1-GATE-TAIL
  E   assert loans == 1
```

### Attempt 2 — terminated `timeout`, verdict FAIL

Gate `test` (`uv run pytest -q`) — FAIL, exit 1:

```text
ATTEMPT-2-GATE-TAIL
  E   IndexError: list index out of range
```

Judge — RETRY:

```text
ATTEMPT-2-JUDGE-FEEDBACK: scenario US1-S2 is not covered — nothing refuses
a second loan of the same book.
```
"""

# --- planted evidence ---------------------------------------------------------
#
# Every value below is distinctive on purpose: an assertion that a *planted*
# path, rule or byte count reached the prompt cannot be satisfied by a renderer
# that writes a plausible sentence of its own.

#: The 2026-08-14 incident's shape: a session home, committed, refused by the
#: target's own ignore rules — git's `<source>:<line>:<pattern>` evidence.
HOMES_PATH = ".ergane/homes/PLANTED-SESSION-01/chat.json"
HOMES_RULE = ".gitignore:1:.ergane/"

#: The other half of US1's check: a path under a runtime root no ignore rule
#: mentions, refused by prefix.
LEGACY_PATH = ".factory/homes/PLANTED-LEGACY-02/transcript.jsonl"
LEGACY_RULE = "runtime root: .factory/"

#: A second attempt's violation, so cross-attempt bleed is observable.
OTHER_PATH = "docs/PLANTED-OTHER-03/generated.html"
OTHER_RULE = ".gitignore:7:docs/*/generated.html"

#: The measured 2026-08-15 diff that scored a truncated PASS on five scenarios.
OVERSIZE_TOTAL = 226778

#: Deliberately *not* `DIFF_INPUT_LIMIT`. A refusal is rendered under the cap it
#: was refused by, which is the whole reason the record carries one.
OVERSIZE_LIMIT = DIFF_INPUT_LIMIT // 2

OVERSIZE_FILES = (
    DiffFileSize(path=".ergane/homes/PLANTED-BIG-04/chat.json", size_bytes=148880),
    DiffFileSize(path="tests/PLANTED-BIG-05/test_install.py", size_bytes=39117),
)

MISSING_ARTIFACT = "reports/PLANTED-ARTIFACT-06/summary.md"


def failed_check(**overrides: object) -> OutputCheck:
    """An output check that refused the attempt, in one of its recorded shapes."""
    fields: dict[str, object] = {
        "write_scope": "worktree",
        "has_diff": True,
        "expected_artifacts": [],
        "artifacts_present": None,
        "passed": False,
    }
    fields.update(overrides)
    return OutputCheck(**fields)  # type: ignore[arg-type]


def passing_check() -> OutputCheck:
    """The check `tests/test_prompt.py`'s corpus carries: nothing to report."""
    return OutputCheck(
        write_scope="worktree",
        has_diff=True,
        expected_artifacts=[],
        artifacts_present=None,
        passed=True,
    )


def attempt(
    check: OutputCheck,
    *,
    number: int = 1,
    gates: Sequence[object] = (),
    judge: object = None,
    termination: Termination = Termination.COMPLETED,
) -> AttemptEvidence:
    """One prior attempt whose verification carried `check`."""
    result = replace(
        make_result(number, list(gates), judge),  # type: ignore[arg-type]
        output_check=check,
    )
    return AttemptEvidence(termination=termination, result=result)


def evidence_section(*attempts: AttemptEvidence) -> str:
    """The `## Prior attempt evidence` section of the assembled prompt."""
    prompt = build(prior_attempts=attempts)
    return prompt[prompt.index(EVIDENCE_SECTION) :]


def attempt_blocks(section: str) -> list[str]:
    """One string per `### Attempt` block, in the order they render."""
    parts = section.split("### Attempt ")
    return [f"### Attempt {part}" for part in parts[1:]]


# --- US3-S1: an empty diff is stated as an empty diff -------------------------


def test_an_empty_diff_is_stated_as_no_diff_against_the_base() -> None:
    """US3-S1: the four-attempt burn, named in the prompt that used to be silent.

    `has_diff: false` is the whole verdict — no gate failed and the judge was
    never asked — so if this block says nothing, the retry is a re-roll.
    """
    section = evidence_section(attempt(failed_check(has_diff=False)))

    assert "no diff against the base" in section.lower()
    assert "nothing was committed" in section.lower()
    # The write scope the check was applied under: `worktree` and `docs` are
    # judged on their diff, and an agent that does not know which it is cannot
    # know what would satisfy this.
    assert "worktree" in section

    # The sentence the four attempts were actually shown must be gone: an
    # output-check failure is a loud failure, and it now has words of its own.
    assert NOTHING_FAILED_LOUDLY not in section


def test_a_failed_check_does_not_borrow_another_shape_s_words() -> None:
    """Nothing is invented: a present diff is never described as an absent one."""
    section = evidence_section(
        attempt(failed_check(hygiene_violations=[HygieneViolation(HOMES_PATH, HOMES_RULE)]))
    )

    assert "no diff against the base" not in section.lower()


# --- US3-S2: hygiene violations, verbatim -------------------------------------


def test_every_offending_path_and_its_rule_are_listed_verbatim() -> None:
    """US3-S2: US1's refusal names what to remove, and so must the prompt.

    Both shapes of `HygieneViolation.rule` travel: git's own
    `<source>:<line>:<pattern>` and the runtime-root prefix that no ignore rule
    ever carried. The rule is half the actionable content — "which rule refused
    this?" is the question the next attempt has to answer before it can shrink
    its diff.
    """
    check = failed_check(
        hygiene_violations=[
            HygieneViolation(path=HOMES_PATH, rule=HOMES_RULE),
            HygieneViolation(path=LEGACY_PATH, rule=LEGACY_RULE),
        ]
    )
    section = evidence_section(attempt(check))

    assert HOMES_PATH in section
    assert HOMES_RULE in section
    assert LEGACY_PATH in section
    assert LEGACY_RULE in section
    assert NOTHING_FAILED_LOUDLY not in section


def test_each_attempt_renders_its_own_output_check_and_no_other_s() -> None:
    """The evidence is *this* attempt's — the property a hardcoded block fails.

    Two prior attempts, two different failure shapes. A renderer that emits a
    fixed sentence, or that reaches for the wrong attempt's record, cannot put
    the empty-diff statement in the first block only and `OTHER_PATH` in the
    second block only.
    """
    first = attempt(failed_check(has_diff=False), number=1)
    second = attempt(
        failed_check(hygiene_violations=[HygieneViolation(OTHER_PATH, OTHER_RULE)]),
        number=2,
        termination=Termination.TIMEOUT,
    )

    blocks = attempt_blocks(evidence_section(first, second))
    assert len(blocks) == 2, blocks

    assert "no diff against the base" in blocks[0].lower()
    assert OTHER_PATH not in blocks[0]

    assert OTHER_PATH in blocks[1]
    assert OTHER_RULE in blocks[1]
    assert "no diff against the base" not in blocks[1].lower()


# --- US3-S3: the size refusal, with its numbers --------------------------------


def test_a_size_refusal_names_the_total_the_limit_and_the_files() -> None:
    """US3-S3: "too big" starts a hunt; the file that spent the budget ends it."""
    check = failed_check(
        size_refusal=DiffSizeRefusal(
            total_bytes=OVERSIZE_TOTAL,
            limit_bytes=OVERSIZE_LIMIT,
            largest_files=list(OVERSIZE_FILES),
        )
    )
    section = evidence_section(attempt(check))

    assert str(OVERSIZE_TOTAL) in section
    assert str(OVERSIZE_LIMIT) in section
    for entry in OVERSIZE_FILES:
        assert entry.path in section
        assert str(entry.size_bytes) in section
    assert NOTHING_FAILED_LOUDLY not in section


def test_the_limit_rendered_is_the_one_the_record_carries() -> None:
    """The record's cap, never the module's — the reason the record carries one.

    A refusal stored before the cap moved has to render the cap it was refused
    under. A renderer reaching for `diffbounds.DIFF_INPUT_LIMIT` would print
    today's number over yesterday's refusal and send the next attempt after a
    budget it never had.
    """
    check = failed_check(
        size_refusal=DiffSizeRefusal(
            total_bytes=OVERSIZE_TOTAL,
            limit_bytes=OVERSIZE_LIMIT,
            largest_files=list(OVERSIZE_FILES),
        )
    )
    section = evidence_section(attempt(check))

    assert str(OVERSIZE_LIMIT) in section
    assert str(DIFF_INPUT_LIMIT) not in section


def test_hygiene_and_size_render_together_when_both_were_recorded() -> None:
    """Neither branch shadows the other: `check_output` can record both."""
    check = failed_check(
        hygiene_violations=[HygieneViolation(HOMES_PATH, HOMES_RULE)],
        size_refusal=DiffSizeRefusal(
            total_bytes=OVERSIZE_TOTAL,
            limit_bytes=OVERSIZE_LIMIT,
            largest_files=list(OVERSIZE_FILES),
        ),
    )
    section = evidence_section(attempt(check))

    assert HOMES_PATH in section
    assert str(OVERSIZE_TOTAL) in section


# --- the other recorded shapes -------------------------------------------------


def test_missing_artifacts_are_named() -> None:
    """FR-005 is "whatever the check records": the read scope's failure too."""
    check = failed_check(
        write_scope="read",
        has_diff=False,
        expected_artifacts=[MISSING_ARTIFACT],
        artifacts_present=False,
    )
    section = evidence_section(attempt(check))

    assert MISSING_ARTIFACT in section
    assert NOTHING_FAILED_LOUDLY not in section


def test_a_failure_with_no_rendered_reason_still_says_the_check_refused_it() -> None:
    """The reachable residue: a write scope the registry never defined.

    `decide_passed` refuses an unrecognised scope with nothing else recorded —
    no empty diff, no violation, no refusal. Silence there would be the same
    defect this story closes, one branch further in, so the block still names
    the check as the decider.
    """
    section = evidence_section(attempt(failed_check(write_scope="nonesuch")))

    assert "output check" in section.lower()
    assert "nonesuch" in section
    assert NOTHING_FAILED_LOUDLY not in section


# --- placement -----------------------------------------------------------------


def test_the_output_check_evidence_sits_between_the_gates_and_the_judge() -> None:
    """Verification order, rendered in verification order.

    The judge in this fixture is a rendering fixture, not a claim about the
    pipeline: `judge_required` skips the judge whenever the output check fails,
    which is exactly why the block had no words before this story. Its position
    is still pinned, so a block appended after everything cannot drift from the
    order the evidence was produced in.
    """
    check = failed_check(has_diff=False)
    section = evidence_section(
        attempt(
            check,
            gates=[make_gate(output_tail=ATTEMPT_ONE_TAIL)],
            judge=make_judge("PLANTED-JUDGE-FEEDBACK-07"),
        )
    )

    assert (
        section.index(ATTEMPT_ONE_TAIL)
        < section.lower().index("no diff against the base")
        < section.index("PLANTED-JUDGE-FEEDBACK-07")
    )


def test_a_passing_gate_is_still_not_quoted_beside_a_failed_output_check() -> None:
    """The gate filter is untouched: green output is noise in either case."""
    section = evidence_section(
        attempt(
            failed_check(has_diff=False),
            gates=[
                make_gate(
                    name="lint",
                    status=GateStatus.PASS,
                    exit_code=0,
                    output_tail="PASSING-TAIL-MUST-NOT-APPEAR-08",
                )
            ],
        )
    )

    assert "PASSING-TAIL-MUST-NOT-APPEAR-08" not in section


# --- US3-S4: byte parity for a passing check ------------------------------------


def test_a_passing_output_check_renders_byte_identically_to_today() -> None:
    """US3-S4 / FR-004: the corpus's own evidence section, byte for byte.

    `EVIDENCE_SECTION_GOLDEN` was captured before `_attempt_block` was touched.
    Prompt stability is what makes an untouched graph assemble identical
    prompts, so this is an equality assertion rather than a spot check: an
    output-check block emitted unconditionally, an extra blank line, a changed
    heading — each moves these bytes.
    """
    section = evidence_section(*prior_two_attempts())

    assert section == EVIDENCE_SECTION_GOLDEN
    assert "output check" not in section.lower()
