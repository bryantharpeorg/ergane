"""Proving the node did something, before anyone is allowed to believe it did.

Gates and the judge both answer "is this work good?". Neither answers "is there
any work?" — a suite that passes over an untouched worktree passes just as
loudly, and an agent that burned its budget and produced nothing would otherwise
collect a PASS and unlock the whole downstream graph. That is what this check
exists to stop (FR-004), so it is the one part of verification that must not be
rescuable by any other part.

The rule is persona-derived (spec § Clarifications), and the two halves are
deliberately asymmetric:

- **Write scopes (`worktree`, `docs`) are judged on their diff, and only on it.**
  A declared artifact does not substitute for a diff, and a missing one does not
  veto it — completeness is the judge's job, the floor is "something changed".
- **The read scope is judged on its declared artifact, and only on it.** A
  researcher's output is a report, not a diff, so the diff is recorded as
  evidence and ignored as a criterion. A read node that declared no artifact has
  nothing that could prove work, and so cannot pass — "no node passes with
  neither diff nor artifact" (FR-004) is enforced in that direction too.

Three properties carry the weight:

- **Nothing here fails open.** A scope the registry never heard of does not pass;
  an empty file is not an artifact; a directory is not an artifact; a path that
  escapes the worktree is not this node's artifact. Every unknown answers "not
  proved", because the only thing worse than a false FAIL here is the false PASS
  it exists to prevent.
- **"No diff" must be a fact about the worktree, never a failure to look.** A
  vanished worktree and a directory git refuses to read are infrastructure
  failures — they raise `WorktreeMissingError` rather than returning the clean
  worktree they superficially resemble (contracts/activities.md maps it to
  `WORKTREE_MISSING`). The exception is the read scope, whose personas may run
  with `needs_worktree: false`: git's absence cannot change a verdict that never
  consulted git.
- **Untracked work is work.** New files are the normal shape of agent output and
  are counted whether or not the agent staged or committed them — including when
  the repo's own config hides them from `git status`, which is why the untracked
  flag has to be explicit rather than inherited.

Two boundaries are drawn on purpose:

- `.gitignore` decides. The fixture repo ignores `.factory-gate-order.log` so
  running gates leaves a clean worktree; the factory's own leavings must never
  read as the agent's work.
- "Diff" means worktree-vs-HEAD (R7), so an agent that *committed* inside its
  worktree reads as clean. That is the contract's definition, not an oversight:
  in the node lifecycle the commit happens at salvage, after verification. If
  agents start self-committing mid-node, this definition — not this test — is
  what has to change.

Real git throughout, on the `tests/fixtures/target_repo/` skeleton: the whole
subject is what `git status` says about a real worktree, and a fake of it would
only prove the fake agrees with itself.

Written before `factory/verify/diffcheck.py` exists (T015 precedes T019): until
the module lands, every test here fails at import.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pytest

from factory.config import WriteScope, load_personas
from factory.verify.diffcheck import (
    ARTIFACT_SCOPES,
    DIFF_SCOPES,
    WorktreeMissingError,
    check_output,
    decide_passed,
)
from factory.verify.models import OutputCheck
from tests.target_repo import GATE_ORDER_LOG, git

#: A tracked file in the fixture repo, for "the agent edited something" cases.
TRACKED_FILE = "src/calc.py"

#: A tracked file under `docs/`, so the `docs` write scope is exercised on the
#: kind of file it is actually scoped to.
TRACKED_DOC = "docs/notes.md"

#: The artifact a read-scoped node (researcher) would declare.
REPORT = "reports/findings.md"


def write(worktree: Path, relative: str, text: str = "new content\n") -> Path:
    """Create or overwrite a file in the worktree, parents and all."""
    path = worktree / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def status(worktree: Path) -> str:
    """What git itself says about the worktree — the assertions' second opinion."""
    return git(worktree, "status", "--porcelain", "--untracked-files=all")


# --- the pure decision ------------------------------------------------------


@dataclass(frozen=True)
class Decision:
    """One (scope, diff, artifacts) input and the `passed` it must produce."""

    id: str
    write_scope: str
    has_diff: bool
    artifacts_present: bool | None
    passed: bool


DECISIONS = [
    # Write scopes: the diff is the proof, and nothing else is (FR-004).
    Decision(
        "a-worktree-node-with-a-diff-passes", WriteScope.WORKTREE, True, None, True
    ),
    Decision(
        "a-worktree-node-without-one-fails", WriteScope.WORKTREE, False, None, False
    ),
    Decision("docs-is-a-write-scope-too", WriteScope.DOCS, True, None, True),
    Decision("and-fails-the-same-way", WriteScope.DOCS, False, None, False),
    Decision(
        "an-artifact-does-not-substitute-for-a-diff",
        WriteScope.WORKTREE,
        False,
        True,
        False,
    ),
    Decision(
        "a-missing-artifact-does-not-veto-a-diff",
        WriteScope.WORKTREE,
        True,
        False,
        True,
    ),
    # Read scope: the declared artifact is the proof, and the diff is not.
    Decision(
        "a-read-node-with-its-artifact-passes", WriteScope.READ, False, True, True
    ),
    Decision("a-read-node-missing-it-fails", WriteScope.READ, False, False, False),
    Decision(
        "a-diff-does-not-substitute-for-an-artifact",
        WriteScope.READ,
        True,
        False,
        False,
    ),
    Decision(
        "a-read-node-that-declared-nothing-has-proved-nothing",
        WriteScope.READ,
        True,
        None,
        False,
    ),
    # A scope the registry never defined is a wiring bug, not a licence.
    Decision("an-unknown-scope-never-passes", "worktre", True, True, False),
    Decision("an-empty-scope-never-passes", "", True, True, False),
]


@pytest.mark.parametrize("case", DECISIONS, ids=[case.id for case in DECISIONS])
def test_the_decision_is_a_truth_table(case: Decision) -> None:
    """The whole anti-rubber-stamp rule, with no filesystem in the way."""
    passed = decide_passed(
        case.write_scope,
        has_diff=case.has_diff,
        artifacts_present=case.artifacts_present,
    )

    assert passed is case.passed


def test_the_scope_may_arrive_as_a_plain_string() -> None:
    """It crosses an activity boundary as JSON, so it comes back as `str`."""
    assert decide_passed("worktree", has_diff=True, artifacts_present=None) is True
    assert decide_passed("read", has_diff=True, artifacts_present=True) is True


def test_every_write_scope_the_registry_can_produce_has_a_rule() -> None:
    """A fourth scope must not default into the diff rule — or into passing.

    `WriteScope` is closed (factory/config.py) precisely so this component can
    partition it. Adding a member without deciding what proves that node's work
    fails here rather than in production.
    """
    assert DIFF_SCOPES | ARTIFACT_SCOPES == set(WriteScope)
    assert not DIFF_SCOPES & ARTIFACT_SCOPES
    assert DIFF_SCOPES == {WriteScope.WORKTREE, WriteScope.DOCS}
    assert ARTIFACT_SCOPES == {WriteScope.READ}


def test_the_shipped_personas_are_all_covered() -> None:
    """The rule is persona-derived, so it is checked against the real registry."""
    scopes = {persona.write_scope for persona in load_personas().values()}

    assert scopes <= DIFF_SCOPES | ARTIFACT_SCOPES


# --- what counts as a diff --------------------------------------------------


def test_a_clean_worktree_fails_a_write_scoped_node(
    node_worktree: Callable[..., Path],
) -> None:
    """Passing gates over an untouched worktree is the failure this catches."""
    worktree = node_worktree()

    result = check_output(worktree, WriteScope.WORKTREE)

    assert isinstance(result, OutputCheck)
    assert result.has_diff is False
    assert result.passed is False
    assert result.expected_artifacts == []
    assert result.artifacts_present is None, "nothing was declared to check"
    assert status(worktree) == "", "the check itself may not dirty the worktree"


def test_a_modified_tracked_file_is_a_diff(
    node_worktree: Callable[..., Path],
) -> None:
    worktree = node_worktree()
    write(worktree, TRACKED_FILE, "def add(a, b):\n    return a + b + 0\n")

    result = check_output(worktree, WriteScope.WORKTREE)

    assert result.has_diff is True
    assert result.passed is True


def test_an_untracked_file_alone_is_a_diff(
    node_worktree: Callable[..., Path],
) -> None:
    """New files are the normal shape of agent work, staged or not (R7)."""
    worktree = node_worktree()
    write(worktree, "src/new_module.py", "VALUE = 1\n")

    result = check_output(worktree, WriteScope.WORKTREE)

    assert result.has_diff is True
    assert result.passed is True


def test_a_staged_file_is_a_diff(node_worktree: Callable[..., Path]) -> None:
    """An agent that ran `git add` has not thereby erased its own work."""
    worktree = node_worktree()
    write(worktree, "src/new_module.py", "VALUE = 1\n")
    git(worktree, "add", "src/new_module.py")

    assert check_output(worktree, WriteScope.WORKTREE).has_diff is True


def test_a_deleted_tracked_file_is_a_diff(
    node_worktree: Callable[..., Path],
) -> None:
    """Removing code is work; a check that only saw additions would miss it."""
    worktree = node_worktree()
    (worktree / TRACKED_FILE).unlink()

    assert check_output(worktree, WriteScope.WORKTREE).has_diff is True


def test_untracked_files_count_even_when_the_repo_hides_them(
    node_worktree: Callable[..., Path],
) -> None:
    """`status.showUntrackedFiles = no` must not turn agent work invisible.

    A target repo is free to configure git however it likes; the factory's
    verdict may not depend on it. Only an explicit untracked flag survives this.
    """
    worktree = node_worktree()
    git(worktree, "config", "status.showUntrackedFiles", "no")
    write(worktree, "src/new_module.py", "VALUE = 1\n")

    result = check_output(worktree, WriteScope.WORKTREE)

    assert result.has_diff is True
    assert result.passed is True


def test_ignored_files_are_not_agent_work(
    node_worktree: Callable[..., Path],
) -> None:
    """The factory's own leavings must never read as the node's output.

    `.factory-gate-order.log` is what the fixture's gate scripts append to, and
    it is gitignored for exactly this reason: running the gates must not be able
    to manufacture the diff that FR-004 demands.
    """
    worktree = node_worktree()
    write(worktree, GATE_ORDER_LOG, "lint test typecheck\n")

    result = check_output(worktree, WriteScope.WORKTREE)

    assert result.has_diff is False
    assert result.passed is False


def test_the_docs_scope_is_judged_on_its_diff_like_any_other_write_scope(
    node_worktree: Callable[..., Path],
) -> None:
    worktree = node_worktree()
    write(worktree, TRACKED_DOC, "# Notes\n\nA decision was recorded.\n")

    result = check_output(worktree, WriteScope.DOCS)

    assert result.write_scope == WriteScope.DOCS
    assert result.has_diff is True
    assert result.passed is True


# --- declared artifacts -----------------------------------------------------


def test_a_read_node_passes_on_its_declared_artifact(
    node_worktree: Callable[..., Path],
) -> None:
    """A researcher's proof of work is the report, and its worktree stays clean."""
    worktree = node_worktree()
    write(worktree, REPORT, "# Findings\n\nThe proxy paginates at 100.\n")

    result = check_output(worktree, WriteScope.READ, expected_artifacts=(REPORT,))

    assert result.has_diff is True, "an untracked report is still a diff, factually"
    assert result.artifacts_present is True
    assert result.passed is True
    assert result.expected_artifacts == [REPORT], "echoed as a list, in order"


def test_an_empty_artifact_is_not_an_artifact(
    node_worktree: Callable[..., Path],
) -> None:
    """A node that created the file and wrote nothing to it produced nothing."""
    worktree = node_worktree()
    write(worktree, REPORT, "")

    result = check_output(worktree, WriteScope.READ, expected_artifacts=[REPORT])

    assert result.artifacts_present is False
    assert result.passed is False


def test_a_missing_artifact_fails(node_worktree: Callable[..., Path]) -> None:
    worktree = node_worktree()

    result = check_output(worktree, WriteScope.READ, expected_artifacts=[REPORT])

    assert result.artifacts_present is False
    assert result.passed is False


def test_every_declared_artifact_has_to_be_there(
    node_worktree: Callable[..., Path],
) -> None:
    """All, not any — a node that delivered half its output delivered a failure."""
    worktree = node_worktree()
    write(worktree, REPORT, "# Findings\n")

    result = check_output(
        worktree,
        WriteScope.READ,
        expected_artifacts=[REPORT, "reports/summary.md"],
    )

    assert result.artifacts_present is False
    assert result.passed is False


def test_a_directory_is_not_an_artifact(node_worktree: Callable[..., Path]) -> None:
    """`stat` reports a nonzero size for a directory; "non-empty" means content."""
    worktree = node_worktree()
    (worktree / "reports").mkdir()

    result = check_output(worktree, WriteScope.READ, expected_artifacts=["reports"])

    assert result.artifacts_present is False
    assert result.passed is False


def test_an_artifact_path_may_not_escape_the_worktree(
    node_worktree: Callable[..., Path], tmp_path: Path
) -> None:
    """Declared paths are repo-relative; something outside is not this node's work."""
    worktree = node_worktree()
    (tmp_path / "outside.md").write_text("# Not the node's\n", encoding="utf-8")

    result = check_output(
        worktree, WriteScope.READ, expected_artifacts=["../outside.md"]
    )

    assert result.artifacts_present is False
    assert result.passed is False


def test_a_read_node_that_declared_nothing_cannot_pass(
    node_worktree: Callable[..., Path],
) -> None:
    """No diff criterion and no artifact leaves nothing that could prove work.

    Verifier nodes are the case that looks like an exception — their artifact is
    the recorded `VerificationResult` rather than a worktree path — and that is
    the dispatcher's to declare (contracts/verification-flow.md), not something
    this check may assume on a node's behalf.
    """
    worktree = node_worktree()
    write(worktree, "src/new_module.py", "VALUE = 1\n")

    result = check_output(worktree, WriteScope.READ)

    assert result.has_diff is True
    assert result.artifacts_present is None
    assert result.passed is False


def test_a_read_nodes_diff_is_recorded_but_never_decides(
    node_worktree: Callable[..., Path],
) -> None:
    """Evidence, not a criterion: a big diff does not excuse a missing report."""
    worktree = node_worktree()
    write(worktree, TRACKED_FILE, "def add(a, b):\n    return a + b + 0\n")

    result = check_output(worktree, WriteScope.READ, expected_artifacts=[REPORT])

    assert result.has_diff is True
    assert result.artifacts_present is False
    assert result.passed is False


def test_a_write_nodes_artifacts_are_recorded_but_never_decide(
    node_worktree: Callable[..., Path],
) -> None:
    """The mirror image: FR-004 makes the diff the write scope's floor.

    Whether the node produced everything it promised is a question for the
    scenarios and the judge; this check owns the floor, and widening it here
    would put a second, quieter verdict in front of them.
    """
    worktree = node_worktree()
    write(worktree, TRACKED_FILE, "def add(a, b):\n    return a + b + 0\n")

    result = check_output(
        worktree, WriteScope.WORKTREE, expected_artifacts=[REPORT]
    )

    assert result.has_diff is True
    assert result.artifacts_present is False, "recorded as evidence"
    assert result.passed is True


# --- the worktree that is not there -----------------------------------------


def test_a_vanished_worktree_is_an_error_not_a_verdict(tmp_path: Path) -> None:
    """It resembles a clean worktree exactly, and it is nothing of the kind.

    Returning `passed=False` here would charge an infrastructure failure to the
    agent's attempt budget and route a healthy node toward escalation; the
    activity turns this into `WORKTREE_MISSING` instead (contracts/activities.md).
    """
    missing = tmp_path / "gone"

    with pytest.raises(WorktreeMissingError) as excinfo:
        check_output(missing, WriteScope.WORKTREE)

    assert str(missing) in str(excinfo.value)


def test_a_vanished_worktree_is_an_error_for_read_nodes_too(tmp_path: Path) -> None:
    """Their artifacts are under it, so its absence is unreadable either way."""
    missing = tmp_path / "gone"

    with pytest.raises(WorktreeMissingError):
        check_output(missing, WriteScope.READ, expected_artifacts=[REPORT])


def test_a_directory_git_cannot_read_is_not_a_clean_worktree(tmp_path: Path) -> None:
    """A failed `git status` must never be mistaken for an empty one.

    Silently reading git's exit 128 as "no changes" is the pass-by-default this
    component refuses everywhere else (`CONFIG_ERROR` gates, missing manifests);
    for a write-scoped node it would instead be a fabricated FAIL, which is the
    same lie pointed the other way.
    """
    not_a_repo = tmp_path / "scratch"
    not_a_repo.mkdir()

    with pytest.raises(WorktreeMissingError):
        check_output(not_a_repo, WriteScope.WORKTREE)


def test_a_read_node_needs_no_git_at_all(tmp_path: Path) -> None:
    """`judge` and `researcher` are `needs_worktree: false` in the registry.

    Their verdict never consulted the diff, so the absence of a repository
    cannot change it — the directory holding the artifact is enough.
    """
    workdir = tmp_path / "scratch"
    workdir.mkdir()
    (workdir / "findings.md").write_text("# Findings\n", encoding="utf-8")

    result = check_output(
        workdir, WriteScope.READ, expected_artifacts=["findings.md"]
    )

    assert result.has_diff is False, "no repository, so no diff to record"
    assert result.artifacts_present is True
    assert result.passed is True
