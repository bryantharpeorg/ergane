"""US4 of epic 130: a finding names the repository, and the operator's own work is not it.

The detector's start snapshot used to be the *committed* tree while its teardown
snapshot was the *working* tree, so any working-tree content present when the
attempt began — the operator's uncommitted work, by the documented recovery the
operator was told to perform — showed up at teardown as a difference and was
filed as the attempt's escape. The channel fired on the exact action the
operator was told to take.

After this story the two snapshots are the same kind (both working-tree state),
so content already present at start is recorded as seen and files nothing. A
commit that moves the target's HEAD during the attempt is distinguished from a
write the same way: the paths the commit carried are charged only if the working
tree no longer matches what the commit left. And every finding the detector
files names the target repository it is about, from the value the start snapshot
already captured and the teardown comparison used to drop.

These tests drive the detector directly through `capture_start` and
`compare_and_report` against a `tmp_path` runtime root, the pattern
`tests/test_us2_own_worktree_only.py` established. The adapter-surface controls
this story overrides live in `tests/test_us1_detector.py` (011-US1 scenario 3's
two committed controls, edited openly there).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

from factory.doctor.models import Severity
from factory.workgraph.detector import capture_start, compare_and_report
from factory.workgraph.models import AttemptContext

EPIC = "130-the-boundary-detector-charges-an-attempt-only-for-what-it-wrote"
NODE = "us4"
ATTEMPT = 1

#: A tracked file in the fixture target repo; changing it is a boundary escape.
TRACKED_FILE = "src/calc.py"

STORE_NAMES = ("doctor.db", "ledger.db", "verification.db")


@pytest.fixture
def runtime_root(tmp_path: Path) -> Path:
    """A supplied runtime root with all three evidence stores populated."""
    root = tmp_path / ".ergane"
    root.mkdir()
    for name in STORE_NAMES:
        (root / name).write_text(f"initial {name} content\n", encoding="utf-8")
    return root


@pytest.fixture
def own_worktree(tmp_path: Path) -> Path:
    """Where this attempt's agent runs; it is allowed to write here."""
    path = tmp_path / "own-worktree"
    path.mkdir()
    return path


@pytest.fixture
def repo(target_repo: Callable[..., Path]) -> Path:
    """A real target repository, clean at attempt start."""
    return target_repo("passing")


@pytest.fixture
def context(repo: Path, own_worktree: Path) -> AttemptContext:
    return AttemptContext(
        epic_id=EPIC,
        node_id=NODE,
        attempt=ATTEMPT,
        prompt="Implement US4.\n",
        worktree_path=str(own_worktree),
        home_path=str(own_worktree / "home"),
        proxy_url="http://litellm.test:4000",
        virtual_key="sk-virtual-130-us4-1",
        model_alias="anthropic/CHANGEME",
        session_id="0f2c9a71-5d48-4c3b-8a6e-2b7c1d0e9f43",
        timeout_s=60,
        target_repo=str(repo),
    )


@pytest.fixture
def attempt(
    runtime_root: Path, repo: Path, context: AttemptContext
) -> Callable[[Callable[[], None]], object]:
    """Run one attempt: capture, let `during` happen, compare.

    Returns whatever `compare_and_report` returns — the finding, or `None` for
    silence.
    """

    def run(during: Callable[[], None]):
        capture_start(runtime_root, repo, context)
        during()
        return compare_and_report(runtime_root, repo, context)

    return run


def named(finding, needle: str) -> bool:
    """Whether a finding names `needle` anywhere an operator would read it."""
    return (
        needle in finding.summary
        or any(needle in ref for ref in finding.refs)
        or (finding.notes is not None and needle in finding.notes)
    )


# --- T020 / US4-S1 (detector half): pre-existing working-tree content is silence ---


def test_pre_existing_working_tree_content_files_no_finding(
    runtime_root: Path,
    repo: Path,
    context: AttemptContext,
    attempt: Callable[[Callable[[], None]], object],
) -> None:
    """US4-S1 / FR-007: what was already in the tree when the attempt began is not charged.

    The adapter-surface control for this scenario is
    `tests/test_us1_detector.py::test_operator_work_is_reported_and_untouched`
    (011-US1 scenario 3's first committed control, edited by this story); this
    is the same class driven at the detector surface, including the subtler
    shape: a *tracked* path already modified but uncommitted at start must also
    stay silent, not just an untracked one.
    """
    tracked = repo / TRACKED_FILE
    original = tracked.read_text(encoding="utf-8")
    tracked.write_text(original + "\n# operator uncommitted edit\n", encoding="utf-8")
    (repo / "operator_untracked.txt").write_text("operator work\n", encoding="utf-8")

    # Nothing happens during the attempt at all.
    finding = attempt(lambda: None)

    assert finding is None, (
        "working-tree content present before capture_start must not be filed "
        "as this attempt's escape (FR-007)"
    )


def test_attempt_writing_on_top_of_pre_existing_dirt_still_files(
    runtime_root: Path,
    repo: Path,
    context: AttemptContext,
    attempt: Callable[[Callable[[], None]], object],
) -> None:
    """US4-S1's boundary: pre-existing dirt is a baseline, not a blind spot.

    The exclusion reads the start snapshot as a baseline; a path the attempt
    changes *on top of* pre-existing dirt differs from that baseline and files.
    Without this half the exclusion would be a hole an escape could hide in:
    write once before the attempt, and the detector would never look again.
    """
    tracked = repo / TRACKED_FILE
    original = tracked.read_text(encoding="utf-8")
    tracked.write_text(original + "\n# operator uncommitted edit\n", encoding="utf-8")

    def escape_on_top() -> None:
        tracked.write_text(original + "\n# operator edit\n# agent edit\n", encoding="utf-8")

    finding = attempt(escape_on_top)

    assert finding is not None, "a write on top of pre-existing dirt is still a finding"
    assert finding.severity is Severity.CRITICAL
    assert f"target:{TRACKED_FILE}" in finding.refs


# --- T021 / US4-S2: a commit during the attempt carries its own paths ---------


def test_operator_commit_is_silent_but_attempt_write_on_top_files(
    runtime_root: Path,
    repo: Path,
    context: AttemptContext,
    attempt: Callable[[Callable[[], None]], object],
) -> None:
    """US4-S2 / FR-007: HEAD moved by an operator commit is not a write by the attempt.

    One test, both halves. The operator commits during the attempt — a new file
    and a modification to a tracked path — and the attempt then writes on top of
    that commit. The paths the commit carried file nothing; the path the attempt
    changed on top of the commit still files, which is what stops the commit
    exclusion becoming a hole.
    """
    readme = repo / "README.md"
    readme_original = readme.read_text(encoding="utf-8")
    target = repo / TRACKED_FILE
    target_original = target.read_text(encoding="utf-8")

    def operator_commit_then_escape() -> None:
        # The operator commits during the attempt: one new file, one edit to a
        # tracked path — both carried by the commit, neither written by the
        # attempt.
        (repo / "operator_notes.md").write_text("committed mid-attempt\n", encoding="utf-8")
        readme.write_text(readme_original + "\n# operator commit\n", encoding="utf-8")
        import subprocess

        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "--quiet", "-m", "operator commit"],
            check=True,
        )
        # The attempt writes on top of that commit.
        target.write_text(target_original + "\n# agent edit on top\n", encoding="utf-8")

    finding = attempt(operator_commit_then_escape)

    assert finding is not None, "the write on top of the commit must still file"
    assert finding.severity is Severity.CRITICAL
    # The commit-carried paths are charged to no one.
    assert not named(finding, "operator_notes.md"), finding.summary
    assert not named(finding, "README.md"), finding.summary
    # The path the attempt changed on top of the commit is.
    assert f"target:{TRACKED_FILE}" in finding.refs


# --- T022 / US4-S3: a filed finding names the target repository ---------------


def test_finding_names_the_target_repository(
    runtime_root: Path,
    repo: Path,
    context: AttemptContext,
    attempt: Callable[[Callable[[], None]], object],
) -> None:
    """US4-S3 / FR-008: the finding carries the repo the start snapshot captured.

    `_write_snapshot` already wrote `target_repo` into the start snapshot and
    `compare_and_report` read it back only to drop it; the finding an operator
    reads must say *which* repository it is about — several targets share one
    worker host.
    """

    def escape() -> None:
        tracked = repo / TRACKED_FILE
        tracked.write_text(
            tracked.read_text(encoding="utf-8") + "\n# written outside the worktree\n",
            encoding="utf-8",
        )

    finding = attempt(escape)

    assert finding is not None
    assert f"repo:{repo}" in finding.refs, finding.refs
    assert str(repo) in finding.summary, finding.summary


# --- T023 / US4-S4: the control — a genuine escape files exactly as today ------


def test_genuine_escape_files_with_evidence_intact(
    runtime_root: Path,
    repo: Path,
    context: AttemptContext,
    attempt: Callable[[Callable[[], None]], object],
) -> None:
    """US4-S4 / FR-007 (control): a real escape is as loud as it was, evidence intact.

    Both halves in one finding: the tracked path changed in the target repo and
    the truncated evidence store. US4 narrows what is *attributed*; it must not
    narrow what is *detected*.
    """

    def escape_and_truncate() -> None:
        tracked = repo / TRACKED_FILE
        tracked.write_text(
            tracked.read_text(encoding="utf-8") + "\n# written outside the worktree\n",
            encoding="utf-8",
        )
        (runtime_root / "ledger.db").write_text("", encoding="utf-8")

    finding = attempt(escape_and_truncate)

    assert finding is not None, "a genuine escape must still file"
    assert finding.severity is Severity.CRITICAL
    assert f"target:{TRACKED_FILE}" in finding.refs
    assert "ledger.db" in finding.refs or "ledger.db" in (finding.notes or "")
    assert finding.notes is not None
    assert "Tracked paths changed in target repository:" in finding.notes
    # The bounded-evidence contract is untouched: the listed paths and the
    # exact counts both survive.
    assert "1 tracked path(s)" in finding.summary
    assert "1 runtime-root path(s)" in finding.summary


# --- T024 / US4-S5: the detector still only reads -----------------------------


def test_detector_leaves_the_operators_tree_byte_identical(
    runtime_root: Path,
    repo: Path,
    context: AttemptContext,
    attempt: Callable[[Callable[[], None]], object],
) -> None:
    """US4-S5 / FR-007: read-only with respect to the target repository (trap 9's survivor).

    The half of 011-US1 scenario 3 that survives this story's reversal: whatever
    the detector decides to file, it never stashes, checks out, cleans or
    otherwise mutates the operator's tree. The operator's uncommitted file is
    byte-identical after the attempt, and the working tree's state — untracked
    file still untracked, HEAD where it was — is what it was.
    """
    import subprocess

    operator_file = repo / "operator_work.txt"
    operator_file.write_text("operator uncommitted work\n", encoding="utf-8")
    head_before = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    original_bytes = operator_file.read_bytes()

    def escape() -> None:
        tracked = repo / TRACKED_FILE
        tracked.write_text(
            tracked.read_text(encoding="utf-8") + "\n# written outside the worktree\n",
            encoding="utf-8",
        )

    finding = attempt(escape)

    assert finding is not None, "the escape files; the tree is merely read"
    assert operator_file.read_bytes() == original_bytes, (
        "the detector must leave the operator's file byte-identical"
    )
    # Nothing stashed, checked out, cleaned or reset: HEAD is where it was, the
    # stash is empty, and the operator's file is still untracked, not swept.
    head_after = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert head_after == head_before
    stash = subprocess.run(
        ["git", "-C", str(repo), "stash", "list"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert stash == ""
    porcelain = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "operator_work.txt" in porcelain, (
        "the operator's untracked file must still be there, untracked"
    )