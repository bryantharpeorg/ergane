"""The landing path refuses before the push, and names both repositories (107 US2).

US1 established the ownership predicate: two clones of one repository dispatched
under one factory root resolve the *same* node directory, and `ensure()` refuses
the second clone instead of handing it the first clone's worktree. US2 extends
that refusal to the two places the landing path leaves the safe zone it built:

- `push_branch` pushes through the *dispatched* target repo's ref store, so a
  directory owned by another clone would push a branch that lives nowhere in that
  store — git's `src refspec ... does not match any`, sent to a day of diagnosis
  elsewhere. The refusal must name the branch, the worktree, the repository that
  actually holds the ref and the one that was asked to push, and it must arrive
  *before* a single `git push` subprocess runs (T011).
- `sync_with_target` fetches in the dispatched repo and merges `remote/<default>`
  inside the node directory — the recovery path. When the directory belongs to
  another clone, that merge would fold one repository's ref into another's tree.
  Same assertion, before the fetch (T012, FR-005).

The tests are written against the same two-clone fixture US1 built, because the
two clones of one repository are byte-identical and the ancestry check cannot
tell them apart — which is the whole reason a check reading a sidecar would fail
(T016's comment). Real git throughout; a fake would only prove the fake agrees
with itself.

T011–T014 live here, mirroring the acceptance scenarios US2-S1..US2-S4:

- **US2-S1** (T011, T012): a node worktree owned by A, pushed/merged against B,
  is refused by name with no push subprocess having run.
- **US2-S3** (T013): a directory that exists but is not a git worktree at all is
  refused by name rather than raising through from the probe, and does not pass
  by inheriting the enclosing clone (trap 1).
- **US2-S4** (T014): a correctly owned worktree is unchanged — the push happens,
  the trunk guard still fires on its own terms, and the returned sha is the
  worktree's head.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

import pytest

from factory.workgraph.worktree import (
    WorktreeError,
    WorktreeOwnershipError,
    branch_name,
    ensure,
    push_branch,
    sync_with_target,
)
from tests.target_repo import git, git_env

EPIC = "107-a-landing-refuses"
NODE = "us2"
BRANCH = f"factory/{EPIC}/{NODE}"


# --- setup -------------------------------------------------------------------


@pytest.fixture(autouse=True)
def no_operator_git_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every identity git could fall back on (tests/test_worktree.py)."""
    empty_home = tmp_path / "empty-home"
    empty_home.mkdir()
    monkeypatch.setenv("HOME", str(empty_home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    for name in (
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def factory_root(tmp_path: Path) -> Path:
    """One worker-host state directory, shared by both clones — the whole point."""
    return tmp_path / ".ergane"


@pytest.fixture
def repo_a(target_repo: Callable[..., Path]) -> Path:
    """The clone that gets there first, and ends up owning the directory."""
    return target_repo("passing", name="clone-a")


@pytest.fixture
def repo_b(target_repo: Callable[..., Path]) -> Path:
    """A second clone of the same repository: same files, same commit sha."""
    return target_repo("passing", name="clone-b")


def node_dir(factory_root: Path) -> Path:
    return factory_root / "worktrees" / EPIC / NODE


def head(path: Path, ref: str = "HEAD") -> str:
    return git(path, "rev-parse", ref).strip()


def _prepare(repo: Path, factory_root: Path) -> Path:
    """Create the node worktree and put a pushed branch's worth of work on it."""
    prepared = ensure(repo, EPIC, NODE, factory_root=factory_root)
    worktree = Path(prepared.path)
    (worktree / "landed.txt").write_text("work\n", encoding="utf-8")
    git(worktree, "add", "-A")
    git(worktree, "commit", "--quiet", "-m", "node work")
    return worktree


# --- US2-S1: a push against the non-owning repository is refused (T011) -------


def _recorded_push_calls(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """A handle on every `git … push` subprocess issued during the test body.

    The refusal has to land *before* the push subprocess — asserting only the
    exception would pass if the code pushed (or even tried to push) and then
    raised for some other reason. So we record every `subprocess.run` whose argv
    names a `push`, and assert the count stayed zero.
    """
    push_calls: list[list[str]] = []

    real_run = subprocess.run

    def spy(args: list[str] | str, *a: object, **k: object):
        if isinstance(args, list) and len(args) >= 2 and "push" in args:
            push_calls.append(list(args))
        return real_run(args, *a, **k)

    monkeypatch.setattr(subprocess, "run", spy)
    return push_calls


def test_push_branch_refuses_a_foreign_worktree_before_any_push_subprocess(
    repo_a: Path, repo_b: Path, factory_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US2-S1/T011: the refusal names everything and no `git push` ever ran."""
    worktree = _prepare(repo_a, factory_root)
    assert head(repo_a) == head(repo_b), "the two clones must be indistinguishable"

    push_calls = _recorded_push_calls(monkeypatch)

    with pytest.raises(WorktreeOwnershipError) as raised:
        push_branch(repo_b, EPIC, NODE, factory_root=factory_root)

    # The refusal names the worktree, the repository that actually holds the ref
    # and the one that was asked to push. (The branch is the node's own name,
    # factory/<epic>/us2, and the directory the message names is that branch's
    # home — both halves of US2-S1.)
    message = str(raised.value)
    assert str(worktree.resolve()) in message
    assert str(repo_a.resolve()) in message  # the repository that holds the ref
    assert str(repo_b.resolve()) in message  # the one that was asked to push

    # No `git push` subprocess ran — the refusal is what precedes the push.
    assert push_calls == []


# --- US2-S1/FR-005: the recovery sync refuses the same way (T012) -------------


def test_sync_with_target_refuses_a_foreign_worktree(
    repo_a: Path, repo_b: Path, factory_root: Path
) -> None:
    """US2-S1 via `sync_with_target`: refused, not merged into the wrong tree.

    The sync fetches in `repo_b` and would merge `origin/<default>` inside the
    node directory owned by `repo_a`. It must refuse on the same terms as the
    push — the merge is the recovery path's `git push` — rather than folding one
    repository's ref into another's worktree.
    """
    worktree = _prepare(repo_a, factory_root)
    before = head(worktree)
    with pytest.raises(WorktreeOwnershipError) as raised:
        sync_with_target(repo_b, EPIC, NODE, factory_root=factory_root)

    message = str(raised.value)
    assert str(worktree.resolve()) in message
    assert str(repo_a.resolve()) in message
    assert str(repo_b.resolve()) in message

    # The owning clone's tree is untouched: still on the node branch, head intact.
    assert git(worktree, "rev-parse", "--abbrev-ref", "HEAD").strip() == BRANCH
    assert head(worktree) == before


# --- US2-S3: not a worktree at all is refused by name (T013) ------------------


def test_a_non_worktree_directory_is_refused_by_name(
    repo_a: Path, factory_root: Path
) -> None:
    """US2-S3/trap 1: a directory under the root that is not a worktree at all.

    `ERGANE_ROOT` sits inside a clone, and git walks up: a bare `mkdir`
    directory answers that enclosing clone's `--show-toplevel` with exit 0. The
    only guard before this story was `is_dir()`, which passes it. The ownership
    probe must refuse it by name rather than let an exception raise through, and
    must not let the push pass by inheriting the enclosing clone (trap 1).
    """
    # A directory nested inside the owning clone, but not registered to it.
    root = repo_a / ".factory"
    path = root / "worktrees" / EPIC / NODE
    path.mkdir(parents=True)

    with pytest.raises(WorktreeOwnershipError) as raised:
        push_branch(repo_a, EPIC, NODE, factory_root=root)

    message = str(raised.value)
    assert str(path.resolve()) in message
    assert str(repo_a.resolve()) in message
    assert "not a git worktree" in message


# --- US2-S4: a correctly owned worktree is unchanged (T014) -------------------


def test_push_branch_still_pushes_a_correctly_owned_worktree(
    repo_a: Path, factory_root: Path, tmp_path: Path
) -> None:
    """US2-S4: the push still happens, and returns the worktree's head.

    With ownership matching, the honest path is byte-for-byte today's: the trunk
    guard fires on its own terms, the push reaches origin, and the returned sha
    is the worktree's head.
    """
    bare = tmp_path / "origin.git"
    git(repo_a, "init", "--bare", str(bare))
    git(repo_a, "remote", "add", "origin", str(bare))
    git(repo_a, "push", "--quiet", "-u", "origin", "main")

    worktree = _prepare(repo_a, factory_root)

    # The trunk guard still fires on its own terms — a branch named the landing
    # branch is refused even in an owned worktree.
    default = git(repo_a, "symbolic-ref", "--short", "HEAD").strip()
    with pytest.raises(WorktreeError) as trunk:
        push_branch(repo_a, EPIC, default, factory_root=factory_root)
    assert default in str(trunk.value)

    # The push itself succeeds and returns the worktree's head.
    pushed = push_branch(repo_a, EPIC, NODE, factory_root=factory_root)
    assert pushed == head(worktree)
