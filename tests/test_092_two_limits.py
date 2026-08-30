"""Two questions, two names: what the judge may be shown, and what is refused.

One constant answered both until this story. `DIFF_INPUT_LIMIT` is documented as
"an attention budget, not a context limit" — a property of the model — and was
also the size above which a story was refused unjudged, which is a property of
the work and of the operator's tolerance. Sharing one name meant the two could
not be tuned apart: raising the judge's budget for a bigger model also raised
the size at which honest work was thrown away, and the measured cost was a story
that no attempt could pass — four gates green, judge never reached, every ladder
rung failing identically at 74,465 bytes with no generated file in the diff at
all.

So the tests here are mostly about the *gap* between the two names, because the
gap is the thing that did not exist before:

- `test_a_diff_between_the_two_limits_is_not_refused` (US1-S1) and
  `test_a_diff_between_the_two_limits_reaches_the_judge_abridged` (US1-S2) drive
  one worktree — the same bytes, the same call — with the refusal raised above
  the attention budget, and watch it pass the output check and arrive at the
  judge abridged instead of not arriving.
- `test_the_same_diff_at_the_default_threshold_is_still_refused` (US1-S3) is that
  worktree again at the default, and it is the one that says the ceiling was
  separated rather than removed. It reads the refusal through the *retry
  prompt's* rendering rather than through the record, because that rendering is
  what the next attempt is actually told (plan trap 7).
- `test_at_default_configuration_nothing_moved` (US1-S4) is the control this
  story is judged on: a rename and a split, not a behaviour change.
- `test_the_refusal_and_the_abridger_agree_at_the_margin` (FR-002, plan trap 3)
  is the one that would catch the wrong implementation. Both limits weigh the
  *assembly* the judge's prompt carries — the always-complete file listing, plus
  the preamble, plus every file's section — and if the split let one of them
  start weighing the raw patch instead, the pair would disagree exactly where a
  disagreement matters: where one elides and the other calls the diff whole. It
  is asserted by making each function state its own measurement of the same
  bytes and comparing them, never by recomputing the assembly here — a test that
  reimplemented it would agree with itself rather than with the code.

Sizes are derived from the two constants, never from 65536 (the same reason
`tests/test_diff_size.py` gives): both are tuned values, one has moved already,
and a test pinning the number turns the next tuning into a false failure.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Callable

from pathlib import Path

from factory.config import WriteScope
from factory.usage.models import Termination
from factory.verify.diffbounds import (
    DIFF_INPUT_LIMIT,
    DIFF_REFUSAL_THRESHOLD,
    size_refusal,
)
from factory.verify.diffcheck import check_output
from factory.verify.judge import build_prompt, prepare_diff
from factory.verify.models import OutputCheck
from factory.workgraph.prompt import AttemptEvidence
from factory.workgraph.worktree import diff as worktree_diff
from tests.test_diff_size import (
    BULK_FILE,
    CRITERIA,
    TRACKED_FILE,
    WORK,
    base_of,
    commit,
    payload,
    write,
)
from tests.test_prompt import build, make_gate, make_result

#: An operator who has decided their repository may build stories the judge can
#: only be shown part of. Four times the attention budget is not a proposal for
#: a default — it is far enough above it that "between the two" is unambiguous.
RAISED_THRESHOLD = DIFF_INPUT_LIMIT * 4

#: Comfortably over the attention budget, comfortably under the raised
#: threshold: the size that had no outcome before this story except refusal.
BETWEEN_PAYLOAD = DIFF_INPUT_LIMIT + DIFF_INPUT_LIMIT // 2


def between_the_limits(node_worktree: Callable[..., Path]) -> tuple[Path, str]:
    """A worktree of honest work, larger than the judge's budget and no more.

    Two files, because the refusal ranks them and a ranking of one file is not
    one. Committed, because an agent following the ralph contract commits as it
    goes and the diff this story is about is the committed one (D-027).
    """
    worktree = node_worktree()
    base = base_of(worktree)
    write(worktree, TRACKED_FILE, WORK)
    write(worktree, BULK_FILE, payload(BETWEEN_PAYLOAD))
    commit(worktree, "us1: more work than the judge can read whole")
    return worktree, base


def measured(diff_text: str) -> int:
    """The refusal's own count of what this diff would cost the judge.

    A limit of zero refuses everything, which is what makes the refusal state
    its measurement out loud for a diff of any size. Asking the function is the
    point: a helper that assembled the listing and the sections itself would be
    a second implementation of the thing under test.
    """
    refusal = size_refusal(diff_text, limit=0)
    assert refusal is not None, "a limit of zero refuses every non-empty diff"
    return refusal.total_bytes


def sized_diff(total: int, *, path: str = "src/margin.py") -> str:
    """A one-file diff whose assembly is exactly `total` bytes.

    Padding goes inside a single added line, so the file listing — which counts
    lines, not bytes — is identical whatever `total` is, and every byte of the
    padding lands in the section. The skeleton is measured rather than counted,
    so this stays exact if the listing's own rendering ever changes.
    """
    head = (
        f"diff --git a/{path} b/{path}\n"
        f"--- /dev/null\n+++ b/{path}\n@@ -0,0 +1 @@\n"
    )
    padding = total - measured(head + "+\n")
    assert padding >= 0, f"{total} bytes is smaller than an empty one-file diff"
    return head + "+" + "x" * padding + "\n"


def refused_prompt(check: OutputCheck) -> str:
    """The next attempt's prompt, carrying one failed output check verbatim.

    The retry prompt is where a refusal is actually read — by the agent that has
    to act on it — so this is the rendering US1-S3 asserts against rather than
    the stored row. `_output_check_block` is reached through the public
    assembler on purpose: the block is quoted into a prompt or it is quoted
    nowhere.
    """
    result = make_result(attempt=1, gates=[make_gate()], judge=None)
    evidence = AttemptEvidence(
        termination=Termination.COMPLETED,
        result=replace(result, output_check=check),
    )
    return build(prior_attempts=[evidence])


# --- US1-S1: the gap exists, and work lands in it ---------------------------


def test_a_diff_between_the_two_limits_is_not_refused(
    node_worktree: Callable[..., Path],
) -> None:
    """US1-S1. Larger than the judge's budget is no longer larger than allowed.

    Before this story the two conditions were one condition, so this worktree
    had exactly one possible outcome and it was FAIL. The preconditions are
    asserted rather than assumed: a fixture that drifted under the attention
    budget would make this test pass for the reason the story is not about.
    """
    worktree, base = between_the_limits(node_worktree)
    patch = worktree_diff(worktree, base_ref=base)

    assert DIFF_INPUT_LIMIT < measured(patch) < RAISED_THRESHOLD

    result = check_output(
        worktree,
        WriteScope.WORKTREE,
        base_ref=base,
        diff_size_limit=RAISED_THRESHOLD,
    )

    assert result.size_refusal is None, "between the two limits is not over one"
    assert result.has_diff is True
    assert result.passed is True


# --- US1-S2: and the judge is shown as much of it as it may be --------------


def test_a_diff_between_the_two_limits_reaches_the_judge_abridged(
    node_worktree: Callable[..., Path],
) -> None:
    """US1-S2. The gentler mechanism, which existed all along and never ran.

    `prepare_diff` abridges to the *attention* budget — the raised threshold
    changes what is refused and must not change what the model is shown — and
    discloses the truncation both in the prompt text and on the flag the record
    is written from. The file listing survives whole, which is what keeps a file
    cut to a stub visible as a file that changed.
    """
    worktree, base = between_the_limits(node_worktree)
    patch = worktree_diff(worktree, base_ref=base)

    prepared = prepare_diff(patch)

    assert prepared.truncated is True
    assert len(prepared.text.encode("utf-8")) <= DIFF_INPUT_LIMIT
    assert "lines truncated" in prepared.text
    assert BULK_FILE in prepared.text and TRACKED_FILE in prepared.text

    prompt = build_prompt(CRITERIA, patch)

    assert prompt.truncated_input is True, "an abridged verdict says it is one"
    assert "lines truncated" in prompt.messages[-1]["content"]


# --- US1-S3: the ceiling was separated, not removed -------------------------


def test_the_same_diff_at_the_default_threshold_is_still_refused(
    node_worktree: Callable[..., Path],
) -> None:
    """US1-S3. The same bytes and the same call, at the threshold's default.

    Read through the retry prompt (plan trap 7): `factory/workgraph/prompt.py`
    quotes the refusal's total, the limit it ran past and the biggest files
    verbatim into the next attempt, and that text is what an agent acts on. A
    rename that left the record intact but moved this rendering would change
    what every future attempt is told, which no gate here would otherwise see.
    """
    worktree, base = between_the_limits(node_worktree)

    result = check_output(worktree, WriteScope.WORKTREE, base_ref=base)
    refusal = result.size_refusal

    assert result.passed is False
    assert refusal is not None
    assert refusal.limit_bytes == DIFF_REFUSAL_THRESHOLD, "the name, not a copy"
    assert refusal.total_bytes > DIFF_REFUSAL_THRESHOLD
    assert [named.path for named in refusal.largest_files] == [BULK_FILE, TRACKED_FILE]

    prompt = refused_prompt(result)

    assert f"total: {refusal.total_bytes} bytes" in prompt
    assert f"limit: {refusal.limit_bytes} bytes" in prompt
    assert "largest files:" in prompt
    assert f"  {BULK_FILE}: {refusal.largest_files[0].size_bytes} bytes" in prompt


# --- US1-S4: the control ----------------------------------------------------


def test_at_default_configuration_nothing_moved(
    node_worktree: Callable[..., Path],
) -> None:
    """US1-S4. Either side of the current constant, today's outcome exactly.

    Two names that resolve to one number is what "preserves today's behaviour"
    means here, and the pure measurement is checked across the boundary — one
    byte under, exactly on, one byte over, and far over — because a split that
    moved the comparison from `<=` to `<` would refuse a diff that fits and pass
    every test that only looked at the extremes.

    The worktree half is asserted as byte parity against the record today's code
    writes: `OutputCheck` is a frozen dataclass, so any field this story added
    or quietly populated on a passing check fails here rather than in a stored
    row someone reads next week.
    """
    assert DIFF_REFUSAL_THRESHOLD == DIFF_INPUT_LIMIT, "the default is today"

    for size in (DIFF_INPUT_LIMIT - 1, DIFF_INPUT_LIMIT):
        assert size_refusal(sized_diff(size)) is None, f"{size} bytes fits"
    for size in (DIFF_INPUT_LIMIT + 1, DIFF_INPUT_LIMIT * 2):
        refusal = size_refusal(sized_diff(size))
        assert refusal is not None, f"{size} bytes does not"
        assert (refusal.total_bytes, refusal.limit_bytes) == (size, DIFF_INPUT_LIMIT)

    worktree = node_worktree()
    base = base_of(worktree)
    write(worktree, TRACKED_FILE, WORK)
    commit(worktree, "us1: ordinary work, well under either limit")

    assert check_output(worktree, WriteScope.WORKTREE, base_ref=base) == OutputCheck(
        write_scope=WriteScope.WORKTREE.value,
        has_diff=True,
        expected_artifacts=[],
        artifacts_present=None,
        passed=True,
    )


# --- FR-002 and plan trap 3: one measurement, two limits --------------------


def test_the_refusal_and_the_abridger_agree_at_the_margin() -> None:
    """FR-002. The split is of the limits, never of what they measure.

    Both functions weigh the assembly the judge's prompt carries, and each is
    made to state that number in its own voice: the abridger by passing a diff
    through a limit nothing can exceed, the refusal by failing one nothing can
    satisfy. Equal numbers are the whole assertion — if the refusal started
    weighing the raw patch while the abridger kept weighing the assembly, they
    would part company at the file listing's own bytes, which is precisely the
    margin.

    Then the margin itself, in both directions. Exactly at the attention budget
    is neither abridged nor refused. One byte over is abridged — and, at the
    default, refused by the same byte, which is today's behaviour — while with
    the threshold raised that byte moves the abridger alone. That last line is
    the story in one assertion: the two limits are now free to disagree.
    """
    exact = sized_diff(DIFF_INPUT_LIMIT)

    assert measured(exact) == len(prepare_diff(exact, limit=DIFF_INPUT_LIMIT * 64).text.encode("utf-8"))
    assert measured(exact) == DIFF_INPUT_LIMIT

    prepared = prepare_diff(exact)

    assert prepared.truncated is False
    assert size_refusal(exact) is None

    over = sized_diff(DIFF_INPUT_LIMIT + 1)

    assert prepare_diff(over).truncated is True
    assert size_refusal(over) is not None
    assert size_refusal(over, limit=RAISED_THRESHOLD) is None
