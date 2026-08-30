"""100-US1: teardown clears the remote ref it left behind, and only that one.

The mine this story defuses is self-sealing. Answering `KILL_EPIC` salvages the
node's work and pushes `factory/<epic>/<node>` to origin; teardown archives the
*local* branch and stops at the edge of the clone; the next dispatch branches
fresh from the landing branch, so its first push shares no ancestor with the
surviving remote ref and git refuses it non-fast-forward — after the node has
already passed verification.

Every claim here is asserted against **real git with a real bare origin**, never
a model. The refusal in scenario 2 is git's own non-fast-forward rule, and no
fake can make that rule true or false; the reachability in scenarios 1 and 3 is
`merge-base --is-ancestor` over objects that actually exist.

The two that carry the story are these, and they are a matched pair:

- `test_a_rebuilt_node_pushes_after_teardown` (US1-S2) is the mine, defused. Its
  control is `test_the_unarchived_remote_ref_still_refuses_a_rebuild` directly
  below it, which does the same rebuild against a ref teardown *declined* to
  remove and asserts the push is still refused — so a teardown that deleted
  every remote ref unconditionally could not pass both, and neither could one
  that deleted none.
- `test_a_remote_tip_no_archive_holds_is_kept` (US1-S3, plan trap 1) is the
  safety proof. Deleting on the strength of "teardown ran, so an archive
  exists" is a different claim from "an archive ref holds this commit", and the
  gap between them is a data-loss bug. The remote tip here is one no archive
  ref reaches, and teardown must leave it and say so.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

import pytest

from factory.workgraph.worktree import (
    archive_branch_prefix,
    branch_name,
    ensure,
    push_branch,
    reset,
    WorktreeError,
)
from tests.target_repo import git, git_env

EPIC_ID = "100-a-reset-leaves-nothing-behind"
NODE_ID = "us1"

#: The local action list teardown returned before this story — the "unchanged"
#: US1-S4 is measured against, rather than a substring check that would pass on
#: a report that had quietly gained a remote line.
LOCAL_ACTIONS = ["committed dirty state", "removed worktree", "archived branch"]


# --- scaffolding ---------------------------------------------------------------


class Epic:
    """One dispatched node, its target clone, and the bare origin behind it."""

    def __init__(self, repo: Path, origin: Path, factory_root: Path) -> None:
        self.repo = repo
        self.origin = origin
        self.factory_root = factory_root
        self.branch = branch_name(EPIC_ID, NODE_ID)

    def dispatch(self, value: str = "1") -> Path:
        """Prepare the node's worktree and leave a commit on its branch.

        `value` is written into the committed file *and* the message because the
        fixture pins author and committer dates: two dispatches producing the
        same tree would produce the same sha, and a rebuild test comparing tips
        would then be comparing a commit with itself.
        """
        prepared = ensure(self.repo, EPIC_ID, NODE_ID, factory_root=self.factory_root)
        worktree = Path(prepared.path)
        (worktree / f"added_by_{NODE_ID}.py").write_text(f"VALUE = {value}\n", "utf-8")
        git(worktree, "add", "-A")
        git(worktree, "commit", "--quiet", "-m", f"work by {NODE_ID} ({value})")
        return worktree

    def push(self) -> str:
        return push_branch(self.repo, EPIC_ID, NODE_ID, factory_root=self.factory_root)

    def teardown(self) -> list[str]:
        return reset(self.repo, EPIC_ID, NODE_ID, factory_root=self.factory_root)

    def remote_tip(self, branch: str | None = None) -> str:
        """What origin holds for `branch`, or "" when it holds nothing."""
        ref = f"refs/heads/{branch or self.branch}"
        listing = git(self.origin, "for-each-ref", "--format=%(objectname)", ref)
        return listing.strip()

    def archive_refs(self) -> tuple[str, ...]:
        """Every archive ref this node's teardown has written, by full name."""
        namespace = f"refs/heads/{archive_branch_prefix(EPIC_ID, NODE_ID)}"
        listing = git(self.repo, "for-each-ref", "--format=%(refname)", namespace)
        return tuple(line for line in listing.splitlines() if line)


@pytest.fixture
def epic(tmp_path: Path, target_repo: Callable[..., Path]) -> Epic:
    """A target clone with a real bare `origin`, ready to dispatch a node into."""
    repo = target_repo("passing", name="target")
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "clone", "--bare", "--quiet", str(repo), str(origin)],
        check=True,
        capture_output=True,
        env=git_env(),
    )
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "fetch", "--quiet", "origin")
    return Epic(repo, origin, tmp_path / ".factory")


def _report(actions: list[str]) -> str:
    """The report as an operator reads it — one string, for naming assertions."""
    return "; ".join(actions)


# --- T001 / US1-S1: the ref is gone and the content is not --------------------


def test_teardown_removes_the_pushed_branch_and_keeps_its_archive(epic: Epic) -> None:
    """FR-001. Both halves in one test on purpose: a teardown that deleted the
    remote ref *and* dropped the archive would satisfy either assertion alone,
    and that is the trade this story explicitly refuses to make."""
    epic.dispatch()
    pushed = epic.push()
    assert epic.remote_tip() == pushed

    actions = epic.teardown()

    assert epic.remote_tip() == "", "the remote ref that blocks the next push survived"
    archives = epic.archive_refs()
    assert len(archives) == 1
    assert git(epic.repo, "rev-parse", archives[0]).strip() == pushed
    assert epic.branch in _report(actions)


# --- T002 / US1-S2: the mine, defused, and its control ------------------------


def test_a_rebuilt_node_pushes_after_teardown(epic: Epic) -> None:
    """US1-S2. The push is not asserted "not to be refused" by reading a
    message — it is run, and a refusal raises `WorktreeError` out of this test.
    """
    epic.dispatch("1")
    dead_tip = epic.push()
    epic.teardown()

    epic.dispatch("2")
    rebuilt = epic.push()

    assert rebuilt != dead_tip
    assert epic.remote_tip() == rebuilt


def test_the_unarchived_remote_ref_still_refuses_a_rebuild(epic: Epic) -> None:
    """The control for the test above, and the reported failure itself.

    Without it, `test_a_rebuilt_node_pushes_after_teardown` would also pass on a
    teardown that cleared nothing at all — because the divergence it survives is
    only visible when the ref is still there. Here teardown *declines* to remove
    the ref (US1-S3's shape), so the rebuild meets exactly what an operator met
    before this story: a verified node, refused non-fast-forward.
    """
    worktree = epic.dispatch("1")
    kept_tip = _push_a_tip_no_archive_will_hold(epic, worktree)
    epic.teardown()
    assert epic.remote_tip() == kept_tip

    epic.dispatch("2")
    with pytest.raises(WorktreeError) as refused:
        epic.push()

    assert "fast-forward" in str(refused.value) or "rejected" in str(refused.value)


def _push_a_tip_no_archive_will_hold(epic: Epic, worktree: Path) -> str:
    """Leave origin holding a commit the node's branch no longer reaches.

    The shape plan trap 1 is about, built the way it actually happens: a salvage
    pushes a tip, and a later local operation moves the branch somewhere else,
    so the archive teardown writes carries a *different* commit. Here the branch
    is rewound to its first commit after the second is pushed — the pushed tip
    is then reachable from nothing local except itself.
    """
    first = epic.push()
    (worktree / "second.py").write_text("VALUE = 2\n", "utf-8")
    git(worktree, "add", "-A")
    git(worktree, "commit", "--quiet", "-m", "a second commit, pushed then rewound")
    pushed = epic.push()
    git(worktree, "reset", "--quiet", "--hard", first)
    assert pushed != first
    return pushed


# --- T003 / US1-S3: the safety proof ------------------------------------------


def test_a_remote_tip_no_archive_holds_is_kept(epic: Epic) -> None:
    """FR-002, plan trap 1. Content nothing else holds is not teardown's to
    discard, so the ref stays and the report names it and why."""
    worktree = epic.dispatch()
    kept_tip = _push_a_tip_no_archive_will_hold(epic, worktree)

    actions = epic.teardown()

    assert epic.remote_tip() == kept_tip
    report = _report(actions)
    assert epic.branch in report
    assert kept_tip[:12] in report
    assert "archive" in report

    # And the archive teardown did write is intact (FR-010): kept means kept on
    # both sides, not "the remote ref survived because nothing was archived".
    archives = epic.archive_refs()
    assert len(archives) == 1
    assert git(epic.repo, "rev-parse", archives[0]).strip() != kept_tip


# --- T004 / US1-S4: a branch that was never pushed -----------------------------


def test_a_never_pushed_node_tears_down_unchanged(epic: Epic) -> None:
    """FR-003. Asserted as equality against `LOCAL_ACTIONS`, not as "no error":
    a report that had gained a line about a remote it never touched would be a
    teardown reporting work it did not do."""
    epic.dispatch()
    assert epic.remote_tip() == ""

    actions = epic.teardown()

    assert actions == LOCAL_ACTIONS
    assert epic.remote_tip() == ""
    assert len(epic.archive_refs()) == 1


# --- T005 / US1-S5: idempotence ------------------------------------------------


def test_teardown_run_twice_succeeds(epic: Epic) -> None:
    """US1-S5. The second run finds the remote ref already gone — which is the
    same read the first run makes, so an implementation that raised on a missing
    remote branch would fail here rather than in production."""
    epic.dispatch()
    epic.push()

    first = epic.teardown()
    second = epic.teardown()

    assert epic.branch in _report(first)
    assert second == ["nothing to do"]
    assert epic.remote_tip() == ""


def test_teardown_run_twice_over_a_kept_ref_succeeds(epic: Epic) -> None:
    """Idempotence on the *other* branch of FR-002: a ref teardown declines to
    remove is still there on the second run, and is still declined rather than
    reconsidered."""
    worktree = epic.dispatch()
    kept_tip = _push_a_tip_no_archive_will_hold(epic, worktree)

    first = epic.teardown()
    second = epic.teardown()

    assert kept_tip[:12] in _report(first)
    assert kept_tip[:12] in _report(second)
    assert epic.remote_tip() == kept_tip


# --- T006 / FR-003, plan trap 2: origin is not always reachable ----------------


def test_an_unreachable_origin_does_not_fail_teardown(epic: Epic) -> None:
    """Plan trap 2. Teardown runs on paths where the network may not be, and a
    local cleanup that starts failing because a remote is unreachable is a worse
    defect than the ref it was cleaning up. It reports what it could not reach
    and completes."""
    epic.dispatch()
    epic.push()
    # An origin that is gone: the URL still resolves as a path, and there is no
    # repository at the end of it. Offline by construction, so this test can
    # never hang on a network that is merely slow.
    git(epic.repo, "remote", "set-url", "origin", str(epic.repo.parent / "gone.git"))

    actions = epic.teardown()

    report = _report(actions)
    assert "origin" in report
    for local in LOCAL_ACTIONS:
        assert local in actions, "the local half of teardown did not complete"
    assert len(epic.archive_refs()) == 1


def test_a_target_with_no_origin_tears_down_unchanged(
    tmp_path: Path, target_repo: Callable[..., Path]
) -> None:
    """The other half of trap 2: a clone with no `origin` at all has no remote
    work to do or to report, and teardown must not invent either."""
    repo = target_repo("passing", name="no-origin")
    solo = Epic(repo, repo, tmp_path / ".factory-solo")
    solo.dispatch()

    assert solo.teardown() == LOCAL_ACTIONS
