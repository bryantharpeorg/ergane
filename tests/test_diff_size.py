"""A diff the judge cannot read whole is refused before a completion is bought.

Measured on this factory the night of 2026-08-15, judging
`033-ergane-install/US2` after its follow-up fix: the diff was **226,778 bytes**
against a `DIFF_INPUT_LIMIT` of 60 KiB. `run_judge` returned
`truncated_input=True` and a verdict of PASS on all five scenarios, and one line
of that verdict's own reasoning reads:

    the elided midsection contains the remaining probe tests rather than
    omitting them

It happened to be right. But that sentence is an *inference* about a region the
judge could not read, delivered in the same voice as its observations, and
nothing in the verdict marks which findings rest on read text and which on
elided text. `truncated_input` was recorded and gated nothing: in the evidence
store a truncated PASS and a whole PASS are the same value.

So size joins hygiene on the floor `factory/verify/diffcheck.py` owns. Two
properties of the refusal are what this file is mostly about, because a refusal
without either of them is worse than none:

- **It fires before the completion is requested.** The check lives inside
  `check_output`, which runs before `judge_required` — the guard the workflow
  already asks before it mints a judge key (`workflow.py:1783`). A refusal that
  still paid for the call would have bought exactly the verdict it distrusts.
- **It names the size, the limit and the files.** An operator whose story is
  legitimately large has to choose between splitting the story and raising the
  ceiling, and "too big" tells them neither. `.ergane/homes/chat.json is 1.4 MB`
  ends the hunt in one line; a total on its own starts one.

The fixtures are sized from `DIFF_INPUT_LIMIT` rather than from 61440 (plan
trap 8): the constant is a tuned value that has moved once already, and a test
pinning the number would turn the next tuning into a false failure.

`test_with_the_size_check_disabled_the_diff_reaches_the_judge_truncated` is the
control SC-004 asks for. It drives the same oversized worktree through the same
call with the check disabled at its seam and watches the judge's prompt come
back truncated — the measurement that says this check changed an outcome, rather
than the outcome having been impossible all along.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import pytest

from factory.config import WriteScope
from factory.verify.diffcheck import WorktreeMissingError, check_output
from factory.verify.diffbounds import (
    DIFF_INPUT_LIMIT,
    OVERSIZE_FILES_NAMED,
    size_refusal,
)
from factory.verify.judge import build_prompt, prepare_diff
from factory.verify.models import (
    CriteriaSet,
    DiffAbridgement,
    DiffFileSize,
    DiffSizeRefusal,
    GateResult,
    GateStatus,
    OutputCheck,
    OverallVerdict,
    Requirement,
    RequirementKind,
    Scenario,
    VerificationForm,
    VerificationResult,
    compose_result,
    judge_required,
)
from factory.verify.store import connect, node_history, upsert_result
from factory.workgraph.worktree import diff as worktree_diff
from tests.target_repo import git

#: A tracked source file, for the "the agent did ordinary work" half of a diff.
TRACKED_FILE = "src/calc.py"

#: The file that makes the diff unjudgeable. Named like real work on purpose:
#: the class this closes is not only session homes — a vendored tree, a captured
#: fixture corpus or an oversized story produce the same unreadable diff.
BULK_FILE = "src/bulk_module.py"

WORK = "def add(a, b):\n    return a + b\n"


CRITERIA = CriteriaSet(
    feature="045-judge-diff-hygiene",
    spec_ref="specs/045-judge-diff-hygiene/spec.md",
    requirements=[
        Requirement(
            key="US2",
            kind=RequirementKind.STORY,
            title="An oversized diff is refused deterministically",
            priority="P1",
            body="An unjudgeable attempt must fail deterministically.",
            scenarios=[
                Scenario(
                    scenario_id="US2-S1",
                    steps=["Given", "When", "Then"],
                    raw_text="Given a worktree whose diff exceeds the limit …",
                )
            ],
        )
    ],
    source_path="specs/045-judge-diff-hygiene/spec.md",
    source_sha256="0" * 64,
    snapshotted_at="2026-08-15T00:00:00+00:00",
)


def write(worktree: Path, relative: str, text: str) -> Path:
    """Create or overwrite a file in the worktree, parents and all."""
    path = worktree / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def base_of(worktree: Path) -> str:
    """The commit the node branched from — `base_ref` as dispatch supplies it."""
    return git(worktree, "rev-parse", "HEAD").strip()


def commit(worktree: Path, message: str) -> None:
    """Commit everything, the way an agent following the ralph contract does."""
    git(worktree, "add", "-A")
    git(worktree, "commit", "--quiet", "-m", message)


def payload(nbytes: int, *, tag: str = "CONSTANT") -> str:
    """At least `nbytes` of deterministic, diff-shaped source text.

    Sized by its caller from `DIFF_INPUT_LIMIT`, never from a literal (trap 8).
    """
    lines: list[str] = []
    total = 0
    index = 0
    while total < nbytes:
        line = f'{tag}_{index:05d} = "{"x" * 48}"\n'
        lines.append(line)
        total += len(line)
        index += 1
    return "".join(lines)


def oversized_worktree(node_worktree: Callable[..., Path]) -> tuple[Path, str]:
    """A worktree carrying real work and far too much of it, committed.

    The small file is there so the refusal has something to rank the big one
    against: "which file spent the budget" is only an answer if more than one
    file could have.
    """
    worktree = node_worktree()
    base = base_of(worktree)
    write(worktree, TRACKED_FILE, WORK)
    write(worktree, BULK_FILE, payload(DIFF_INPUT_LIMIT * 2))
    commit(worktree, "us2: the work, and a great deal of it")
    return worktree, base


def green_gates() -> list[GateResult]:
    """One passing gate: the whole point is that only size stops this attempt."""
    return [
        GateResult(
            name="test",
            command="uv run pytest -q",
            status=GateStatus.PASS,
            exit_code=0,
            duration_s=1.0,
            output_tail="1 passed\n",
        )
    ]


def stored_result(output_check: OutputCheck) -> VerificationResult:
    """The smallest complete evidence bundle carrying one output check."""
    return compose_result(
        epic_id="045-judge-diff-hygiene",
        node_id="us2",
        attempt=1,
        form=VerificationForm.PHASE,
        gate_results=green_gates(),
        output_check=output_check,
        judge=None,
        criteria_sha256="a" * 64,
        spec_ref="045-judge-diff-hygiene/US2",
        started_at="2026-08-15T10:00:00Z",
        finished_at="2026-08-15T10:03:00Z",
    )


# --- US2-S1: the oversized diff fails, deterministically --------------------


def test_a_diff_over_the_judges_input_limit_fails_the_output_check(
    node_worktree: Callable[..., Path],
) -> None:
    """US2-S1. `has_diff` is a fact about the worktree; `passed` is a verdict.

    The files are really there, so the first stays True. The second is False
    because a diff nobody can read whole is not a diff anyone can judge — the
    same shape hygiene takes, on the same record, for the same reason.
    """
    worktree, base = oversized_worktree(node_worktree)

    result = check_output(worktree, WriteScope.WORKTREE, base_ref=base)

    assert result.has_diff is True, "the work is there; that much is factual"
    assert result.passed is False
    assert result.size_refusal is not None


def test_the_refusal_names_the_total_the_limit_and_the_biggest_files(
    node_worktree: Callable[..., Path],
) -> None:
    """FR-003 and trap 9 — the two questions the next reader actually has.

    *How far over am I?* is answered by the total beside the limit, which is
    what tells an operator whether to split the story or raise the ceiling.
    *What spent it?* is answered by the file list, which is what stops the next
    attempt from hunting. A refusal carrying only the first sends someone
    looking through the whole diff for the file this line already names.
    """
    worktree, base = oversized_worktree(node_worktree)
    patch = worktree_diff(worktree, base_ref=base)

    refusal = check_output(worktree, WriteScope.WORKTREE, base_ref=base).size_refusal

    assert refusal is not None
    assert refusal.limit_bytes == DIFF_INPUT_LIMIT, "the constant, never a copy of it"
    assert refusal.total_bytes > DIFF_INPUT_LIMIT
    # The measurement is of the patch the judge would have been handed, not of
    # some other reading of the worktree: within the file listing's own bytes.
    assert refusal.total_bytes >= len(patch.encode("utf-8"))
    # Biggest first, and the small file is not what spent the budget.
    assert [named.path for named in refusal.largest_files] == [BULK_FILE, TRACKED_FILE]
    assert refusal.largest_files[0].size_bytes > DIFF_INPUT_LIMIT
    assert refusal.largest_files[0].size_bytes > refusal.largest_files[1].size_bytes


def test_an_oversized_diff_is_refused_before_the_judge_is_asked(
    node_worktree: Callable[..., Path],
) -> None:
    """US2-S1, second half: no completion is requested, and none is recorded.

    The mechanism is the one 002 already built — `judge_required` refuses to
    spend a completion once the output check has decided a FAIL no judge could
    lift — so size rides it rather than adding a second place a FAIL is decided
    (plan trap 4). The last assertion is the counterfactual that makes this
    worth doing: the completion that was not bought would have been made on an
    elided diff, which is exactly the 226,778-byte verdict this file opens with.
    """
    worktree, base = oversized_worktree(node_worktree)

    output = check_output(worktree, WriteScope.WORKTREE, base_ref=base)

    assert judge_required(green_gates(), output, CRITERIA) is False, (
        "green gates and a real diff, so only size stops this attempt"
    )

    result = compose_result(
        epic_id="045-judge-diff-hygiene",
        node_id="us2",
        attempt=1,
        form=VerificationForm.PHASE,
        gate_results=green_gates(),
        output_check=output,
        judge=None,
        criteria_sha256="0" * 64,
        spec_ref="specs/045-judge-diff-hygiene/spec.md",
        started_at="2026-08-15T00:00:00+00:00",
        finished_at="2026-08-15T00:01:00+00:00",
    )

    assert result.verdict == OverallVerdict.FAIL
    assert result.judge is None, "never ran is a different fact from ran and agreed"
    assert build_prompt(CRITERIA, worktree_diff(worktree, base_ref=base)).truncated_input


# --- US2-S2: under the limit, nothing moved ---------------------------------


def test_a_diff_under_the_limit_produces_todays_output_check_exactly(
    node_worktree: Callable[..., Path],
) -> None:
    """US2-S2 and FR-004, asserted as byte parity rather than as equivalence.

    `OutputCheck` is a frozen dataclass, so equality compares every field: a
    *size refusal* that appeared on a passing check — even a truthful one —
    would change the stored row and the retry prompt assembled from it, and
    fails here rather than in a prompt three days later. `size_refusal` is still
    `None`, which is the assertion this test was written for.

    092-US3 added the one field that is populated on a passing check on purpose:
    how much of the diff the judge was shown, stated whichever way it came out,
    because an unstated "whole" is indistinguishable from a row written before
    anybody recorded either. It changes no verdict and reaches no prompt —
    `_output_check_block` renders only a failed check's refusals — so the parity
    this test guards is intact and now names one more field.
    """
    worktree = node_worktree()
    base = base_of(worktree)
    write(worktree, TRACKED_FILE, WORK)
    commit(worktree, "us2: ordinary work, committed as it goes")

    result = check_output(worktree, WriteScope.WORKTREE, base_ref=base)
    whole = size_refusal(worktree_diff(worktree, base_ref=base), limit=0)

    assert whole is not None, "a limit of zero refuses every non-empty diff"
    assert result == OutputCheck(
        write_scope=WriteScope.WORKTREE.value,
        has_diff=True,
        expected_artifacts=[],
        artifacts_present=None,
        passed=True,
        abridgement=DiffAbridgement(
            total_bytes=whole.total_bytes, budget_bytes=DIFF_INPUT_LIMIT
        ),
    )
    assert result.size_refusal is None
    # And the judge path is what it was: asked, and asked with the whole diff.
    assert judge_required(green_gates(), result, CRITERIA) is True
    assert build_prompt(CRITERIA, worktree_diff(worktree, base_ref=base)).truncated_input is False


# --- US2-S3 / SC-004: the control ------------------------------------------


def test_with_the_size_check_disabled_the_diff_reaches_the_judge_truncated(
    node_worktree: Callable[..., Path],
) -> None:
    """SC-004. The same worktree, the same call, the seam off.

    Without this the suite could not tell a check that changed an outcome from
    a case that was never possible. With the check disabled the attempt passes
    the output check, `judge_required` says yes, and the prompt the judge would
    receive comes back flagged `truncated_input` — the elided-diff verdict, on
    demand.
    """
    worktree, base = oversized_worktree(node_worktree)

    disabled = check_output(
        worktree, WriteScope.WORKTREE, base_ref=base, diff_size_limit=None
    )

    assert disabled.passed is True
    assert disabled.size_refusal is None
    assert judge_required(green_gates(), disabled, CRITERIA) is True

    prompt = build_prompt(CRITERIA, worktree_diff(worktree, base_ref=base))

    assert prompt.truncated_input is True
    assert "lines truncated" in prompt.messages[-1]["content"]


# --- US2-S4: the judge's own truncation stays, as defense in depth ----------


def test_the_judges_own_truncation_survives_behind_the_new_check(
    node_worktree: Callable[..., Path],
) -> None:
    """US2-S4. `prepare_diff` is untouched by this story and still abridges.

    The new check is a floor in front of it, not a replacement for it: every
    other caller of `build_prompt` — the live-judge tier, a future verifier
    node, anything handed a diff it did not read from a node worktree — still
    gets a bounded prompt with its elisions marked.
    """
    worktree, base = oversized_worktree(node_worktree)
    patch = worktree_diff(worktree, base_ref=base)

    prepared = prepare_diff(patch)

    assert prepared.truncated is True
    assert len(prepared.text.encode("utf-8")) <= DIFF_INPUT_LIMIT
    assert "lines truncated" in prepared.text
    # The file list is never abridged, so a file cut to a stub is still visible.
    assert BULK_FILE in prepared.text and TRACKED_FILE in prepared.text


# --- the pure measurement ---------------------------------------------------


def test_a_diff_under_the_limit_earns_no_refusal() -> None:
    """The function answers None for the case that is fine, not a zeroed record."""
    small = (
        "diff --git a/src/calc.py b/src/calc.py\n"
        "--- a/src/calc.py\n+++ b/src/calc.py\n@@ -1 +1 @@\n-old\n+new\n"
    )

    assert size_refusal(small) is None
    assert size_refusal("") is None


def test_the_refusal_names_the_biggest_files_and_stops(
    node_worktree: Callable[..., Path],
) -> None:
    """Bounded, because this list is quoted into the next attempt's prompt.

    Twelve oversized files is what a committed session home looks like. Naming
    every one of them turns the actionable half of the feedback into a wall the
    next attempt has to read past; naming the biggest few ends the hunt.
    """
    files = {
        f"src/pack_{index:02d}.py": payload(
            DIFF_INPUT_LIMIT // 4 + index * 1024, tag=f"P{index:02d}"
        )
        for index in range(12)
    }
    patch = "".join(
        f"diff --git a/{path} b/{path}\n--- /dev/null\n+++ b/{path}\n"
        + "".join(f"+{line}\n" for line in text.splitlines())
        for path, text in files.items()
    )

    refusal = size_refusal(patch)

    assert refusal is not None
    assert len(refusal.largest_files) == OVERSIZE_FILES_NAMED
    # The biggest ones, in order — `pack_11` is the largest by construction.
    assert [named.path for named in refusal.largest_files] == [
        f"src/pack_{index:02d}.py" for index in (11, 10, 9, 8, 7)
    ]


# --- the record outlives the run --------------------------------------------


def test_a_size_refusal_round_trips_through_the_evidence_store(
    tmp_path: Path,
) -> None:
    """US3 renders this from the stored row, so the row has to still have it.

    A refusal that did not survive the store would be a FAIL nobody could
    explain a day later — and, worse, one the next attempt could not be told
    about, which is the `has_diff: false` burn generalized.
    """
    conn = connect(tmp_path / "verification.db")
    refused = OutputCheck(
        write_scope=WriteScope.WORKTREE.value,
        has_diff=True,
        expected_artifacts=[],
        artifacts_present=None,
        passed=False,
        size_refusal=DiffSizeRefusal(
            total_bytes=226_778,
            limit_bytes=DIFF_INPUT_LIMIT,
            largest_files=[
                DiffFileSize(path="tests/test_install_probe.py", size_bytes=180_402),
                DiffFileSize(path="factory/install/probe.py", size_bytes=31_004),
            ],
        ),
    )

    upsert_result(conn, stored_result(refused))
    [loaded] = node_history(conn, "045-judge-diff-hygiene", "us2")

    assert loaded.output_check == refused
    assert loaded.verdict == OverallVerdict.FAIL


def test_an_output_check_written_before_this_story_still_loads(tmp_path: Path) -> None:
    """Trap 5, for US2's field this time.

    Rows written between US1 and US2 carry the hygiene key and no size key.
    They are the population `verification.db` is filling with right now, and a
    field without a default — or a reader that demanded the key — would break
    every one of them at once.
    """
    conn = connect(tmp_path / "verification.db")
    passing = OutputCheck(
        write_scope=WriteScope.WORKTREE.value,
        has_diff=True,
        expected_artifacts=[],
        artifacts_present=None,
        passed=True,
    )
    row_id = upsert_result(conn, stored_result(passing))
    conn.execute(
        "UPDATE verification_results SET output_check = ? WHERE id = ?",
        (
            json.dumps(
                {
                    "write_scope": "worktree",
                    "has_diff": True,
                    "expected_artifacts": [],
                    "artifacts_present": None,
                    "passed": True,
                    "hygiene_violations": [],
                }
            ),
            row_id,
        ),
    )
    conn.commit()

    [loaded] = node_history(conn, "045-judge-diff-hygiene", "us2")

    assert loaded.output_check == passing


# --- FR-006: nothing fails open ---------------------------------------------


def test_a_diff_git_cannot_read_is_not_a_pass(
    node_worktree: Callable[..., Path],
) -> None:
    """FR-006. A base git cannot resolve leaves the judge's input unknown.

    `git status` still answers, so the worktree looks fine and `has_diff` would
    have been True — which is precisely the shape a pass-by-default takes here.
    An unknown diff size is not a small one, and `WorktreeMissingError` is what
    the activity maps to `WORKTREE_MISSING`, so the attempt budget is not
    charged for a git the worker could not get an answer out of.
    """
    worktree = node_worktree()
    write(worktree, TRACKED_FILE, WORK)

    with pytest.raises(WorktreeMissingError) as excinfo:
        check_output(worktree, WriteScope.WORKTREE, base_ref="0" * 40)

    assert str(worktree) in str(excinfo.value)
