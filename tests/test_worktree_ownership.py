"""A worktree says which repository owns it, and a foreign one is refused (107 US1).

`worktree_path()` is a pure function of `(factory_root, epic_id, node_id)` — the
target repository is deliberately not one of its inputs, because factory state
inside a target clone reads as agent work in 002's diff check. The consequence
nobody had checked until this spec: two clones of one GitHub repository, both
dispatched under one factory root, resolve the *same* directory for the same
node id, and `ensure()` handed the second dispatch the first clone's worktree.

Both of `ensure()`'s existing-directory branches passed it through:

- The recorded-sidecar branch checks only that the recorded `base_ref` is an
  ancestor of the dispatched repo's landing head — which **both clones of one
  repository pass**, since every sha resolves in both. The fixtures here are
  byte-identical repositories with identical commit shas for exactly that
  reason: the ancestry check is not merely weak against this, it is blind to it.
- The adopt branch is the worse half, and the reason a `target_repo` field on
  `PreparedWorktree` would not have been the fix: it fires *precisely when the
  sidecar is gone*, reads `_head()` out of the foreign tree and
  `_default_branch()` out of the new repo, and writes both into one fresh
  sidecar that then looks authoritative.

The check has to assert two things, not one. `ERGANE_ROOT` normally sits inside
a clone, and git walks *up*: a bare `mkdir` directory nested in a repository
answers that repository's `--show-toplevel` and `--git-common-dir` with exit 0.
So "whose repository is this directory in" passes a directory that is not a
worktree at all, and the top-level assertion is the one that catches it
(`test_a_bare_directory_inside_a_clone_is_not_that_clones_worktree`).

The refusal's remedy is an acceptance criterion rather than polish: nothing in
the tree sweeps the stale worktrees this refuses on (`remove`, `reset` and
`_archive_node` all shell `git -C <target_repo> worktree remove`, which answers
`fatal: not a working tree` from a repo that does not own the path), so an
operator meets this message with hand-cleaning ahead of them. The test asserts
the printed command works when run against the owning clone *and* that the same
command against the dispatched repo does not — which is why the message names
the owning clone rather than the one the epic was started against.

Real git throughout, and two real repositories: the subject is what git says
about a directory, and a fake would only prove the fake agrees with itself.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable

import pytest
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from factory.activities.agent_activities import (
    ERGANE_ROOT_ENV,
    FACTORY_ROOT_ENV,
    WORKTREE_FAILED,
    WORKTREE_OWNERSHIP_MISMATCH,
    PrepareWorktreeInput,
    prepare_worktree,
)
from factory.workgraph.worktree import (
    PreparedWorktree,
    WorktreeError,
    WorktreeOwnershipError,
    _worktree_ownership,
    ensure,
)
from tests.target_repo import git, git_env

EPIC = "107-a-landing-refuses"
NODE = "us1"
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
    """One worker-host state directory, shared by both clones — the whole point.

    Two dispatchers of one epic id on one host resolve the same node directory
    under this root, because `worktree_path` takes no repository.
    """
    return tmp_path / ".ergane"


@pytest.fixture
def repo_a(target_repo: Callable[..., Path]) -> Path:
    """The clone that gets there first, and ends up owning the directory."""
    return target_repo("passing", name="clone-a")


@pytest.fixture
def repo_b(target_repo: Callable[..., Path]) -> Path:
    """A second clone of the same repository: same files, same commit sha.

    Identical on purpose. This is the pair the ancestry check cannot tell apart,
    because a `base_ref` captured in one resolves perfectly well in the other.
    """
    return target_repo("passing", name="clone-b")


# --- helpers -----------------------------------------------------------------


def node_dir(factory_root: Path) -> Path:
    return factory_root / "worktrees" / EPIC / NODE


def sidecar(factory_root: Path) -> Path:
    return factory_root / "worktrees" / EPIC / f"{NODE}.json"


def head(path: Path, ref: str = "HEAD") -> str:
    return git(path, "rev-parse", ref).strip()


def registered_worktrees(repo: Path) -> list[str]:
    """Paths git considers attached worktrees of `repo` (its own checkout aside)."""
    lines = git(repo, "worktree", "list", "--porcelain").splitlines()
    paths = [
        Path(line.split(" ", 1)[1]) for line in lines if line.startswith("worktree ")
    ]
    return [str(p.resolve()) for p in paths if p.resolve() != repo.resolve()]


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run git without raising, so a test can assert on what it refused."""
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=git_env(),
    )


async def run_prepare(
    env: ActivityEnvironment, repo: Path, **overrides: Any
) -> PreparedWorktree:
    fields: dict[str, Any] = {
        "epic_id": EPIC,
        "node_id": NODE,
        "target_repo": str(repo),
        "standards": None,
    }
    return await env.run(prepare_worktree, PrepareWorktreeInput(**(fields | overrides)))


# --- the recorded-sidecar branch (US1-S1) -------------------------------------


def test_ensure_refuses_a_directory_registered_to_another_clone(
    repo_a: Path, repo_b: Path, factory_root: Path
) -> None:
    """US1-S1: the sidecar is present, the pin resolves, and it is still refused.

    Two clones, one node directory. `ensure(repo_b, ...)` reaches the
    recorded-sidecar branch, finds `base_ref` is an ancestor of B's landing head
    — it is, they are the same commit — and before this spec returned A's
    worktree to B's dispatch. An agent would then have built B's story in A's
    tree, on a branch only A knows about, and the failure would not have
    surfaced until the push found no such ref.
    """
    prepared = ensure(repo_a, EPIC, NODE, factory_root=factory_root)
    path = Path(prepared.path).resolve()
    assert head(repo_a) == head(repo_b), "the two clones must be indistinguishable"

    with pytest.raises(WorktreeOwnershipError) as raised:
        ensure(repo_b, EPIC, NODE, factory_root=factory_root)

    message = str(raised.value)
    assert str(path) in message
    assert str(repo_a.resolve()) in message
    assert str(repo_b.resolve()) in message

    # The refusal is not merely a different message: US2's landing activity and
    # this dispatch both discriminate on the type (plan R14), and a substring
    # check would not survive a reworded message.
    assert isinstance(raised.value, WorktreeError)
    assert type(raised.value) is WorktreeOwnershipError

    # Nothing was repaired, removed or rebuilt in the clone that owns it (R3).
    assert registered_worktrees(repo_a) == [str(path)]
    assert registered_worktrees(repo_b) == []
    assert path.is_dir()


def test_the_refusal_prints_the_command_that_actually_clears_it(
    repo_a: Path, repo_b: Path, factory_root: Path
) -> None:
    """US1-S1/trap 6: the remedy is issued against the owning clone, and works.

    Nothing sweeps these directories — `remove`, `reset` and `_archive_node` all
    run `git -C <target_repo> worktree remove`, which is the *dispatched* repo
    and therefore the one that cannot do it. So the operator's next move is the
    only thing between this refusal and a hard stop, and the exact command is
    part of the contract rather than decoration.
    """
    prepared = ensure(repo_a, EPIC, NODE, factory_root=factory_root)
    path = Path(prepared.path).resolve()

    with pytest.raises(WorktreeOwnershipError) as raised:
        ensure(repo_b, EPIC, NODE, factory_root=factory_root)

    remedy = f"git -C {repo_a.resolve()} worktree remove --force {path}"
    assert remedy in str(raised.value)

    # The same command against the dispatched repo is the one an operator would
    # reach for, and git refuses it — which is why the message names A.
    wrong = run_git(repo_b, "worktree", "remove", "--force", str(path))
    assert wrong.returncode != 0
    assert "is not a working tree" in (wrong.stderr + wrong.stdout)

    # Pasted as printed, it clears the landmine.
    cleared = run_git(repo_a, "worktree", "remove", "--force", str(path))
    assert cleared.returncode == 0, cleared.stderr
    assert not path.exists()

    # And the dispatch that was refused now succeeds against its own clone.
    sidecar(factory_root).unlink()
    recovered = ensure(repo_b, EPIC, NODE, factory_root=factory_root)
    assert registered_worktrees(repo_b) == [str(Path(recovered.path).resolve())]


# --- the adopt branch (US1-S2) ------------------------------------------------


def test_ensure_refuses_to_adopt_a_foreign_tree_when_the_sidecar_is_gone(
    repo_a: Path, repo_b: Path, factory_root: Path
) -> None:
    """US1-S2: the branch a `target_repo` field on the sidecar could never guard.

    The adopt path exists for a worktree whose record was swept, and it fires
    *because* there is no sidecar to consult. Before this spec it minted a fresh
    one from two repositories' answers — `_head()` from A's tree,
    `_default_branch()` from B — and the result carried no trace of the
    disagreement it was made from.
    """
    prepared = ensure(repo_a, EPIC, NODE, factory_root=factory_root)
    path = Path(prepared.path).resolve()
    before = head(path)
    sidecar(factory_root).unlink()
    assert not sidecar(factory_root).exists()

    with pytest.raises(WorktreeOwnershipError) as raised:
        ensure(repo_b, EPIC, NODE, factory_root=factory_root)

    assert str(repo_a.resolve()) in str(raised.value)
    assert str(repo_b.resolve()) in str(raised.value)

    # No sidecar minted from two repositories' answers, and the foreign tree is
    # untouched: same HEAD, same owner, still on A's branch.
    assert not sidecar(factory_root).exists()
    assert head(path) == before
    assert git(path, "rev-parse", "--abbrev-ref", "HEAD").strip() == BRANCH
    assert registered_worktrees(repo_a) == [str(path)]
    assert registered_worktrees(repo_b) == []


# --- not a worktree at all (US1-S3) -------------------------------------------


def test_a_bare_directory_inside_a_clone_is_not_that_clones_worktree(
    repo_a: Path,
) -> None:
    """US1-S3/trap 1: the measured false pass, and the assertion that catches it.

    `ERGANE_ROOT` normally lives inside a clone, so the node directory really is
    nested in a legitimate repository. Git walks up: this directory has no
    `.git` of any kind and still answers `--show-toplevel <clone>` and
    `--git-common-dir <clone>/.git` with exit 0. A check built on the common
    directory alone — including one built on the existing `_main_worktree` —
    calls that owned, and would ship green while proving nothing.
    """
    root = repo_a / ".ergane"
    path = root / "worktrees" / EPIC / NODE
    path.mkdir(parents=True)

    ownership = _worktree_ownership(repo_a, path)

    # The dispatched repo *is* the enclosing clone, so the common-directory half
    # of the question answers yes. The top-level half is what refuses.
    assert git(path, "rev-parse", "--git-common-dir").strip()
    assert ownership.is_worktree is False
    assert ownership.owned is False
    assert ownership.toplevel == repo_a.resolve()

    with pytest.raises(WorktreeOwnershipError) as raised:
        ensure(repo_a, EPIC, NODE, factory_root=root)

    assert str(path.resolve()) in str(raised.value)
    assert str(repo_a.resolve()) in str(raised.value)


def test_a_directory_outside_every_repository_is_an_answer_not_an_exception(
    repo_a: Path, factory_root: Path
) -> None:
    """FR-001: "not a worktree" is a value the helper returns, never a raise.

    A refusal the caller can phrase is the point; a `WorktreeError` escaping
    from the check would be classified as retryable infrastructure and retried
    three times over a directory that will answer the same way forever.
    """
    path = node_dir(factory_root)
    path.mkdir(parents=True)

    ownership = _worktree_ownership(repo_a, path)

    assert ownership.is_worktree is False
    assert ownership.owned is False
    assert ownership.toplevel is None
    assert ownership.owner is None

    with pytest.raises(WorktreeOwnershipError) as raised:
        ensure(repo_a, EPIC, NODE, factory_root=factory_root)

    assert str(path.resolve()) in str(raised.value)


# --- the honest case is untouched (US1-S4) ------------------------------------


def test_a_correctly_registered_worktree_is_returned_exactly_as_before(
    repo_a: Path, factory_root: Path
) -> None:
    """US1-S4: the reuse rule is unchanged; only a foreign directory is refused.

    Both existing-directory branches are exercised — the create path first, then
    the recorded-sidecar path — because the guard sits ahead of both and a guard
    that answered wrong would take the whole dispatch path with it.
    """
    first = ensure(repo_a, EPIC, NODE, factory_root=factory_root)
    path = Path(first.path)

    ownership = _worktree_ownership(repo_a, path)
    assert ownership.owned is True
    assert ownership.is_worktree is True
    assert ownership.toplevel == path.resolve()
    assert ownership.owner == repo_a.resolve()

    (path / "node.txt").write_text("agent work\n", encoding="utf-8")
    second = ensure(repo_a, EPIC, NODE, factory_root=factory_root)

    assert second == first
    assert isinstance(second, PreparedWorktree)
    assert (path / "node.txt").read_text(encoding="utf-8") == "agent work\n"
    assert registered_worktrees(repo_a) == [str(path.resolve())]


def test_the_adopt_path_still_adopts_the_dispatched_repos_own_tree(
    repo_a: Path, factory_root: Path
) -> None:
    """US1-S4: a swept sidecar over a correctly-owned tree still adopts it.

    The guard must not turn the adopt branch into a refusal for everyone: a
    worktree from an older run whose record was swept is the node's real state,
    and rebuilding it would discard exactly the in-progress work the reuse rule
    protects.
    """
    first = ensure(repo_a, EPIC, NODE, factory_root=factory_root)
    path = Path(first.path)
    sidecar(factory_root).unlink()

    adopted = ensure(repo_a, EPIC, NODE, factory_root=factory_root)

    assert adopted.path == first.path
    assert adopted.branch == first.branch
    assert adopted.base_ref == head(path)
    assert sidecar(factory_root).is_file()


# --- the activity boundary (US1-S5) -------------------------------------------


async def test_prepare_worktree_refuses_a_foreign_worktree_non_retryably(
    repo_a: Path,
    repo_b: Path,
    factory_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US1-S5: a repository mismatch never resolves by retrying, so it must not.

    `WORKTREE_FAILED` is documented retryable — a lock or a slow filesystem is
    what a second attempt fixes — and the workflow's git retry policy spends
    three attempts on it. A directory owned by another clone answers the same
    way on all three, so it gets its own type, non-retryable, in the shape
    `STANDARDS_MISSING` already established in this module.
    """
    monkeypatch.setenv(ERGANE_ROOT_ENV, str(factory_root))
    monkeypatch.delenv(FACTORY_ROOT_ENV, raising=False)
    env = ActivityEnvironment()

    await run_prepare(env, repo_a)

    with pytest.raises(ApplicationError) as raised:
        await run_prepare(env, repo_b)

    assert raised.value.type == WORKTREE_OWNERSHIP_MISMATCH
    assert raised.value.type != WORKTREE_FAILED
    assert raised.value.non_retryable is True
    assert str(repo_a.resolve()) in str(raised.value)
    assert "worktree remove --force" in str(raised.value)


async def test_prepare_worktree_still_retries_an_ordinary_worktree_failure(
    tmp_path: Path, factory_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US1-S5, the other direction: the discrimination has to cut both ways.

    A target repo that is not a repository is git refusing, not a mismatch, and
    it stays on today's retryable `WORKTREE_FAILED` path. Asserting only the
    refusal would pass just as happily if every worktree failure had been
    reclassified.
    """
    monkeypatch.setenv(ERGANE_ROOT_ENV, str(factory_root))
    monkeypatch.delenv(FACTORY_ROOT_ENV, raising=False)
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    env = ActivityEnvironment()

    with pytest.raises(ApplicationError) as raised:
        await run_prepare(env, not_a_repo)

    assert raised.value.type == WORKTREE_FAILED
    assert not raised.value.non_retryable
    assert str(not_a_repo) in str(raised.value)
