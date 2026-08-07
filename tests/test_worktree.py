"""The node's one worktree: created once, reused across attempts, salvaged, removed.

This is where constitution VI ("no work is ever lost") stops being a principle and
becomes five git commands. Four properties are what these tests actually defend:

- **One worktree per node, reused** (FR-013). 002's retry semantics — and the
  debugger persona in particular — assume the next attempt opens the *same* tree
  the last one left behind. So `ensure` is idempotent by construction: a second
  call returns the same prepared worktree and touches nothing inside it, including
  when the target repo's default branch has moved on in the meantime. A worktree
  rebuilt or rebased between attempts would move the goalposts mid-node, which is
  the same failure 002's criteria snapshot exists to prevent (R5).

- **Every terminal attempt is observable from the ref alone** (SC-004). `salvage`
  commits a dirty tree, and commits an *empty* one when the agent produced nothing
  — the marker is what makes "this attempt ended, here is its termination" a fact
  about the branch rather than a fact about a log file someone still has. Being
  idempotent per attempt is the other half: an activity retry after an unrecorded
  success must not stack a second marker for the same attempt, or the branch stops
  being a readable account of what happened.

- **Removal is cleanup, never deletion of the record.** `remove` takes the
  directory away; the branch and its salvage commits survive, because they are the
  only thing left of the attempt once `.factory/` is swept.

- **Reading the diff is a read.** `diff` is what 002's judge scores, so it has to
  include the untracked files that are the normal shape of agent output — and it
  has to leave the tree exactly as the agent left it, because the output check
  (FR-004) and the salvage after it both read the same directory. Staging to get
  the untracked half would change what those two see.

Two deliberate choices in the setup:

- **The worktree lives under the worker host's `.factory/`, never inside the target
  clone.** The tests pass an explicit `factory_root` under `tmp_path` and assert the
  resulting path is outside the repo — factory state that landed inside a target
  worktree would show up as agent work in the diff check (002 FR-004) and could be
  committed by salvage itself.

- **`HOME` is an empty directory and the global/system git config is silenced for
  every test here.** Without that, salvage's commits would quietly borrow whichever
  `user.name` the machine running the suite happens to have configured — passing on
  the author's laptop, failing in CI, and attributing factory commits to a person
  who did not make them. Salvage has to carry its own identity, and this is the
  setup that proves it does.

Real git throughout, on the `tests/fixtures/target_repo/` skeleton: the subject is
what git does with a worktree, and a fake would only prove the fake agrees with
itself.

Written before `factory/workgraph/worktree.py` exists (T010 precedes T011): until
the module lands, every test here fails at import.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

import pytest

from factory.usage.models import Termination
from factory.workgraph.worktree import (
    DIFF_CLIP_NOTICE,
    PreparedWorktree,
    SyncResult,
    WorktreeError,
    capture_base_ref,
    diff,
    ensure,
    push_branch,
    remove,
    salvage,
    sync_with_target,
)
from tests.target_repo import git, git_env

EPIC = "003-merge-queue"
NODE = "us1"

#: Branch and worktree naming (R5) — machine-attributable from the ref alone.
BRANCH = f"factory/{EPIC}/{NODE}"

#: Salvage commits are the factory's, not the worker host operator's: an identity
#: read from whatever git config the host carries would make the same attempt
#: produce differently-attributed history on two machines, and would sign the
#: factory's automated commits with a human's name.
SALVAGE_AUTHOR_NAME = "Ergane Factory"
SALVAGE_AUTHOR_EMAIL = "factory@ergane.invalid"

#: A tracked file in the fixture repo, for "the agent edited something".
TRACKED_FILE = "src/calc.py"

#: An untracked one — the normal shape of agent output, which `git add -A` must
#: pick up or salvage would lose exactly the work it exists to keep.
NEW_FILE = "src/added_by_agent.py"


# --- setup -------------------------------------------------------------------


@pytest.fixture(autouse=True)
def no_operator_git_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every identity git could fall back on (see the module docstring)."""
    empty_home = tmp_path / "empty-home"
    empty_home.mkdir()
    monkeypatch.setenv("HOME", str(empty_home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    monkeypatch.delenv("GIT_AUTHOR_NAME", raising=False)
    monkeypatch.delenv("GIT_AUTHOR_EMAIL", raising=False)
    monkeypatch.delenv("GIT_COMMITTER_NAME", raising=False)
    monkeypatch.delenv("GIT_COMMITTER_EMAIL", raising=False)


@pytest.fixture
def factory_root(tmp_path: Path) -> Path:
    """The worker host's state directory — outside every target clone (plan.md)."""
    return tmp_path / ".factory"


@pytest.fixture
def repo(target_repo: Callable[..., Path]) -> Path:
    """A real target repo with one commit on `main`."""
    return target_repo("passing")


# --- helpers -----------------------------------------------------------------


def head(path: Path, ref: str = "HEAD") -> str:
    return git(path, "rev-parse", ref).strip()


def subject(path: Path, ref: str = "HEAD") -> str:
    return git(path, "log", "-1", "--format=%s", ref).strip()


def commit_count(path: Path, ref: str = "HEAD") -> int:
    return int(git(path, "rev-list", "--count", ref).strip())


def status(worktree: Path) -> str:
    """Porcelain status including untracked files — "what has the agent left here"."""
    return git(worktree, "status", "--porcelain", "--untracked-files=all")


def changed_files(path: Path, ref: str = "HEAD") -> list[str]:
    """Paths one commit touched; empty for the `--allow-empty` marker commits."""
    out = git(path, "diff-tree", "--no-commit-id", "--name-only", "-r", ref)
    return out.split()


def ref_exists(repo: Path, ref: str) -> bool:
    completed = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", ref],
        capture_output=True,
        text=True,
        env=git_env(),
    )
    return completed.returncode == 0


def registered_worktrees(repo: Path) -> list[str]:
    """Paths git considers attached worktrees of `repo` (its own checkout aside)."""
    lines = git(repo, "worktree", "list", "--porcelain").splitlines()
    paths = [Path(line.split(" ", 1)[1]) for line in lines if line.startswith("worktree ")]
    return [str(path.resolve()) for path in paths if path.resolve() != repo.resolve()]


def dirty(worktree: Path) -> None:
    """Leave the shape of an agent's work: one edit, one new file."""
    (worktree / TRACKED_FILE).write_text("# edited by the agent\n", encoding="utf-8")
    (worktree / NEW_FILE).write_text("VALUE = 1\n", encoding="utf-8")


def advance_default_branch(repo: Path) -> str:
    """Land a commit on `main` — the world moving on under an in-flight node."""
    (repo / "README.md").write_text("moved on\n", encoding="utf-8")
    git(repo, "commit", "--quiet", "-a", "-m", "someone else landed work")
    return head(repo)


# --- ensure ------------------------------------------------------------------


def test_ensure_creates_the_nodes_worktree_on_its_own_branch(
    repo: Path, factory_root: Path
) -> None:
    """`.factory/worktrees/<epic>/<node>` on `factory/<epic>/<node>` (R5)."""
    prepared = ensure(repo, EPIC, NODE, factory_root=factory_root)

    expected = factory_root / "worktrees" / EPIC / NODE
    assert isinstance(prepared, PreparedWorktree)
    assert Path(prepared.path) == expected
    assert expected.is_dir()

    # A real checkout of the repo, not an empty directory.
    assert (expected / TRACKED_FILE).is_file()
    assert (expected / "factory.yaml").is_file()

    assert prepared.branch == BRANCH
    assert git(expected, "rev-parse", "--abbrev-ref", "HEAD").strip() == BRANCH
    assert head(expected) == prepared.base_ref
    assert prepared.base_ref == head(repo)
    assert registered_worktrees(repo) == [str(expected.resolve())]


def test_ensure_keeps_factory_state_outside_the_target_clone(
    repo: Path, factory_root: Path
) -> None:
    """Anything under the clone would read as agent work in 002's diff check."""
    prepared = ensure(repo, EPIC, NODE, factory_root=factory_root)

    assert not Path(prepared.path).resolve().is_relative_to(repo.resolve())


def test_ensure_uses_the_captured_base_ref_not_a_moving_default_branch(
    repo: Path, factory_root: Path
) -> None:
    """Capture at first dispatch pins the node; retries never rebase mid-node (R5)."""
    base = capture_base_ref(repo)
    assert base == head(repo)

    moved = advance_default_branch(repo)
    assert moved != base

    prepared = ensure(repo, EPIC, NODE, base_ref=base, factory_root=factory_root)

    assert prepared.base_ref == base
    assert head(Path(prepared.path)) == base


def test_second_ensure_reuses_the_worktree_unchanged(
    repo: Path, factory_root: Path
) -> None:
    """FR-013's one worktree: the next attempt opens what the last one left."""
    first = ensure(repo, EPIC, NODE, factory_root=factory_root)
    worktree = Path(first.path)

    dirty(worktree)
    before_status = status(worktree)
    before_head = head(worktree)
    advance_default_branch(repo)

    second = ensure(repo, EPIC, NODE, factory_root=factory_root)

    # Same answer, including the base ref: the default branch moving must not
    # retroactively change what this node was branched from.
    assert second == first
    assert head(worktree) == before_head
    assert status(worktree) == before_status
    assert (worktree / NEW_FILE).read_text(encoding="utf-8") == "VALUE = 1\n"
    assert registered_worktrees(repo) == [str(worktree.resolve())]


def test_ensure_names_the_path_when_the_target_repo_is_not_a_repository(
    tmp_path: Path, factory_root: Path
) -> None:
    """An infrastructure failure raises; nothing here fails open."""
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()

    with pytest.raises(WorktreeError) as raised:
        ensure(not_a_repo, EPIC, NODE, factory_root=factory_root)

    assert str(not_a_repo) in str(raised.value)


def _land_on_origin_only(repo: Path) -> str:
    """Land a commit on origin while the local clone's default branch stays put.

    The shape GitHub's merge queue produces: the squash-merge exists on the
    remote the moment the landing poll sees MERGED, and the worker host's clone
    has not pulled since.
    """
    (repo / "README.md").write_text("landed by the queue\n", encoding="utf-8")
    git(repo, "commit", "--quiet", "-a", "-m", "queue merged the predecessor")
    git(repo, "push", "--quiet", "origin", "main")
    landed = head(repo)
    git(repo, "reset", "--quiet", "--hard", "HEAD~1")
    return landed


def test_ensure_pins_the_remote_head_not_the_stale_local_clone(
    origin_repo: tuple[Path, Path], factory_root: Path
) -> None:
    """First dispatch fetches origin and branches from *its* default-branch head.

    The merge-edge regression (FR-009, found live 2026-08-07 on PR #10): a node
    dispatched after its predecessor MERGED must open a worktree containing the
    predecessor's landed work. The queue merges on the remote and nothing pulls
    the clone in between, so a pin captured from the clone's own HEAD is stale
    exactly when the merge-edge matters — the dependent builds without the code
    its edge waited for, and collides with it at the PR.
    """
    repo, _bare = origin_repo
    remote_head = _land_on_origin_only(repo)
    assert head(repo) != remote_head

    prepared = ensure(repo, EPIC, NODE, factory_root=factory_root)

    assert prepared.base_ref == remote_head
    assert head(Path(prepared.path)) == remote_head
    # The predecessor's landed work is actually in the tree the agent opens.
    readme = Path(prepared.path) / "README.md"
    assert readme.read_text(encoding="utf-8") == "landed by the queue\n"


def test_capture_base_ref_without_an_origin_reads_the_local_head(
    repo: Path,
) -> None:
    """A clone with no remote has nothing to be stale against."""
    assert capture_base_ref(repo) == head(repo)


def test_capture_base_ref_raises_when_origin_is_unreachable(
    repo: Path, tmp_path: Path
) -> None:
    """A failed fetch is infrastructure, never a quiet stale pin (fail closed)."""
    git(repo, "remote", "add", "origin", str(tmp_path / "gone.git"))

    with pytest.raises(WorktreeError):
        capture_base_ref(repo)


# --- salvage -----------------------------------------------------------------


def test_salvage_commits_the_agents_work_to_the_node_branch(
    repo: Path, factory_root: Path
) -> None:
    """Constitution VI: the tree is committed before any cleanup touches it."""
    prepared = ensure(repo, EPIC, NODE, factory_root=factory_root)
    worktree = Path(prepared.path)
    dirty(worktree)

    sha = salvage(
        EPIC,
        NODE,
        termination=Termination.AGENT_ERROR,
        attempt=1,
        factory_root=factory_root,
    )

    assert sha == head(worktree)
    assert head(repo, BRANCH) == sha
    assert subject(worktree) == f"salvage({EPIC}/{NODE}): agent_error attempt 1"
    # Untracked work is work: `git add -A`, not `git commit -a`.
    assert sorted(changed_files(worktree)) == sorted([NEW_FILE, TRACKED_FILE])
    assert status(worktree) == ""


def test_salvage_marks_a_clean_tree_so_every_attempt_is_ref_observable(
    repo: Path, factory_root: Path
) -> None:
    """SC-004: an attempt that produced nothing still ends visibly on the branch."""
    prepared = ensure(repo, EPIC, NODE, factory_root=factory_root)
    worktree = Path(prepared.path)
    before = commit_count(worktree)

    sha = salvage(
        EPIC,
        NODE,
        termination=Termination.TIMEOUT,
        attempt=2,
        factory_root=factory_root,
    )

    assert commit_count(worktree) == before + 1
    assert sha == head(worktree)
    assert subject(worktree) == f"salvage({EPIC}/{NODE}): timeout attempt 2"
    assert changed_files(worktree) == []


def test_salvage_is_idempotent_per_attempt(repo: Path, factory_root: Path) -> None:
    """An activity retry re-runs salvage; the branch must not gain a second marker."""
    prepared = ensure(repo, EPIC, NODE, factory_root=factory_root)
    worktree = Path(prepared.path)
    dirty(worktree)

    first = salvage(
        EPIC,
        NODE,
        termination=Termination.COMPLETED,
        attempt=1,
        factory_root=factory_root,
    )
    after_first = commit_count(worktree)

    again = salvage(
        EPIC,
        NODE,
        termination=Termination.COMPLETED,
        attempt=1,
        factory_root=factory_root,
    )

    assert again == first
    assert commit_count(worktree) == after_first

    # The *next* attempt is a different fact about the branch, clean tree or not.
    second = salvage(
        EPIC,
        NODE,
        termination=Termination.COMPLETED,
        attempt=2,
        factory_root=factory_root,
    )

    assert second != first
    assert commit_count(worktree) == after_first + 1
    assert subject(worktree) == f"salvage({EPIC}/{NODE}): completed attempt 2"


def test_salvage_accepts_the_termination_as_the_string_it_arrives_as(
    repo: Path, factory_root: Path
) -> None:
    """Termination crosses the activity boundary as JSON — a plain str is the enum."""
    prepared = ensure(repo, EPIC, NODE, factory_root=factory_root)
    worktree = Path(prepared.path)

    salvage(EPIC, NODE, termination="killed", attempt=3, factory_root=factory_root)

    assert subject(worktree) == f"salvage({EPIC}/{NODE}): killed attempt 3"


def test_salvage_commits_as_the_factory_not_as_the_host_operator(
    repo: Path, factory_root: Path
) -> None:
    """No git identity is configured anywhere (see `no_operator_git_identity`)."""
    prepared = ensure(repo, EPIC, NODE, factory_root=factory_root)
    worktree = Path(prepared.path)
    dirty(worktree)

    salvage(
        EPIC,
        NODE,
        termination=Termination.COMPLETED,
        attempt=1,
        factory_root=factory_root,
    )

    author = git(worktree, "log", "-1", "--format=%an%n%ae%n%cn%n%ce").split("\n")
    assert author[:4] == [
        SALVAGE_AUTHOR_NAME,
        SALVAGE_AUTHOR_EMAIL,
        SALVAGE_AUTHOR_NAME,
        SALVAGE_AUTHOR_EMAIL,
    ]


def test_salvage_raises_when_the_worktree_is_gone(
    repo: Path, factory_root: Path
) -> None:
    """A missing worktree is an infrastructure failure, not "nothing to salvage"."""
    with pytest.raises(WorktreeError) as raised:
        salvage(
            EPIC,
            NODE,
            termination=Termination.COMPLETED,
            attempt=1,
            factory_root=factory_root,
        )

    assert str(factory_root / "worktrees" / EPIC / NODE) in str(raised.value)


# --- remove ------------------------------------------------------------------


def test_remove_deletes_the_worktree_and_leaves_the_branch(
    repo: Path, factory_root: Path
) -> None:
    """Cleanup takes the directory; the salvaged history is the surviving record."""
    prepared = ensure(repo, EPIC, NODE, factory_root=factory_root)
    worktree = Path(prepared.path)
    dirty(worktree)
    sha = salvage(
        EPIC,
        NODE,
        termination=Termination.COMPLETED,
        attempt=1,
        factory_root=factory_root,
    )

    remove(repo, EPIC, NODE, factory_root=factory_root)

    assert not worktree.exists()
    assert registered_worktrees(repo) == []
    assert ref_exists(repo, f"refs/heads/{BRANCH}")
    assert head(repo, BRANCH) == sha
    assert sorted(changed_files(repo, BRANCH)) == sorted([NEW_FILE, TRACKED_FILE])


def test_remove_is_idempotent(repo: Path, factory_root: Path) -> None:
    """Terminal paths re-run on activity retry; already-removed is success (R5)."""
    ensure(repo, EPIC, NODE, factory_root=factory_root)

    remove(repo, EPIC, NODE, factory_root=factory_root)
    remove(repo, EPIC, NODE, factory_root=factory_root)

    assert not (factory_root / "worktrees" / EPIC / NODE).exists()


def test_remove_of_a_worktree_that_never_existed_is_success(
    repo: Path, factory_root: Path
) -> None:
    """A node killed before dispatch still runs the terminal cleanup sequence."""
    remove(repo, EPIC, NODE, factory_root=factory_root)

    assert not (factory_root / "worktrees" / EPIC / NODE).exists()


# --- diff --------------------------------------------------------------------


def test_diff_reports_edits_and_new_files_as_one_patch(
    repo: Path, factory_root: Path
) -> None:
    """What the judge is given to score: everything the attempt changed (R7).

    Untracked files are the normal shape of agent output — a new module, a new
    test — so a diff that only showed tracked edits would hand the judge the
    smaller half of the work and let it fail a scenario the agent satisfied.
    """
    prepared = ensure(repo, EPIC, NODE, factory_root=factory_root)
    dirty(Path(prepared.path))

    patch = diff(prepared.path, base_ref=prepared.base_ref)

    assert f"b/{TRACKED_FILE}" in patch
    assert "+# edited by the agent" in patch
    assert f"b/{NEW_FILE}" in patch
    assert "+VALUE = 1" in patch


def test_diff_survives_the_agent_committing_its_work(
    repo: Path, factory_root: Path
) -> None:
    """The live failure of 2026-08-05, pinned (D-027).

    005's prompt hands the agent the inner ralph contract, which says commit as
    you go — and Claude Code does. A diff read against HEAD hands the judge
    everything EXCEPT that committed work: in the live smoke the judge was
    shown only the gates' `__pycache__` leavings and, reasonably, failed the
    node for work the agent had done. "The attempt's work" is
    worktree-vs-base-ref: committed, staged and untracked alike, in one patch.
    """
    prepared = ensure(repo, EPIC, NODE, factory_root=factory_root)
    worktree = Path(prepared.path)
    dirty(worktree)
    git(worktree, "add", "-A")
    git(worktree, "commit", "-m", "us1: implement, as the inner contract says")
    (worktree / "notes.txt").write_text("uncommitted leftover\n", encoding="utf-8")

    patch = diff(worktree, base_ref=prepared.base_ref)

    assert f"b/{TRACKED_FILE}" in patch
    assert "+# edited by the agent" in patch
    assert f"b/{NEW_FILE}" in patch
    assert "b/notes.txt" in patch


def test_diff_reads_the_worktree_without_staging_anything(
    repo: Path, factory_root: Path
) -> None:
    """A read that changed the tree would change the verdict after it.

    002's output check and this component's salvage both read the same worktree
    afterwards, and both would read differently against a staged index. So the
    patch is assembled in a scratch index outside the worktree: the tree is
    exactly as the agent left it, and a second read answers the same thing.
    """
    prepared = ensure(repo, EPIC, NODE, factory_root=factory_root)
    worktree = Path(prepared.path)
    dirty(worktree)
    before = status(worktree)

    patch = diff(worktree, base_ref=prepared.base_ref)

    assert status(worktree) == before
    assert git(worktree, "diff", "--cached", "--name-only").strip() == ""
    assert diff(worktree, base_ref=prepared.base_ref) == patch


def test_a_clean_worktree_diffs_to_nothing(repo: Path, factory_root: Path) -> None:
    """An attempt that produced nothing produces no patch — and that is a fact,
    not a failure to look. The empty-diff verdict is the output check's (FR-004),
    which has already run by the time the judge is asked."""
    prepared = ensure(repo, EPIC, NODE, factory_root=factory_root)

    assert diff(prepared.path, base_ref=prepared.base_ref) == ""


def test_diff_is_clipped_at_its_limit_and_says_where(
    repo: Path, factory_root: Path
) -> None:
    """A runaway diff is bounded before it becomes a workflow-history payload.

    The judge abridges further and discloses it (002 R6); this bound is the one
    underneath — an agent that committed a vendored tree must not wedge the epic
    with a payload Temporal refuses. Clipping is disclosed for the same reason
    the judge's is: an elision nobody is told about reads as work nobody did.
    """
    prepared = ensure(repo, EPIC, NODE, factory_root=factory_root)
    (Path(prepared.path) / "generated.txt").write_text("x" * 10_000, encoding="utf-8")

    patch = diff(prepared.path, base_ref=prepared.base_ref, limit=2_000)

    assert len(patch.encode("utf-8")) <= 2_000 + len(DIFF_CLIP_NOTICE)
    assert patch.endswith(DIFF_CLIP_NOTICE)
    assert "generated.txt" in patch


def test_diff_raises_when_the_worktree_is_gone(
    repo: Path, factory_root: Path
) -> None:
    """A worktree that vanished is infrastructure, never an empty diff — the same
    line `check_output` draws, for the same reason."""
    with pytest.raises(WorktreeError) as raised:
        diff(factory_root / "worktrees" / EPIC / NODE, base_ref="HEAD")

    assert str(factory_root / "worktrees" / EPIC / NODE) in str(raised.value)


# --- push_branch (US1 landing, plan.md § US1) ----------------------------------


@pytest.fixture
def origin_repo(repo: Path, tmp_path: Path) -> tuple[Path, Path]:
    """A target repo with a bare `origin` remote it can push to.

    The landing path pushes the node branch to the target clone's `origin`
    (FR-001: `gh pr merge --auto` runs there, so the branch has to exist there).
    This fixture gives the target clone a bare remote and keeps a handle on the
    remote's own path so tests can assert the branch arrived.
    """
    bare = tmp_path / "origin.git"
    git(repo, "init", "--bare", str(bare))
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "--quiet", "-u", "origin", "main")
    return repo, bare


def test_push_branch_pushes_the_node_branch_to_origin(
    origin_repo: tuple[Path, Path], factory_root: Path
) -> None:
    """`factory/<epic>/<node>` reaches origin as a fast-forward push (FR-001)."""
    repo, bare = origin_repo
    prepared = ensure(repo, EPIC, NODE, factory_root=factory_root)
    # The node's work holds a commit the branch is at, so the push has content.
    (Path(prepared.path) / "landed.txt").write_text("work\n", encoding="utf-8")
    git(prepared.path, "add", "-A")
    git(prepared.path, "commit", "--quiet", "-m", "node work")
    branch = prepared.branch

    push_branch(repo, EPIC, NODE, factory_root=factory_root)

    # The branch exists on the bare origin, pointing at the same commit.
    assert ref_exists(bare, f"refs/heads/{branch}")
    assert head(bare, f"refs/heads/{branch}") == head(prepared.path)


def test_push_branch_never_forces() -> None:
    """`push` is plain and fast-forward; no `--force` ever (plan.md § US1).

    Recovery syncs the merge target-head into the branch, which keeps pushes
    fast-forward, so force is never needed — and a `push_branch` that reached for
    `--force` would overwrite history the queue is still deciding on. (The
    module's `remove` uses `git worktree remove --force` legitimately; the guard
    is scoped to the push command itself.)
    """
    import inspect

    from factory.workgraph import worktree as worktree_module

    source = inspect.getsource(worktree_module.push_branch)
    assert "--force" not in source


def test_push_branch_refuses_the_default_branch(
    origin_repo: tuple[Path, Path], factory_root: Path
) -> None:
    """Pushing a branch named the target's default branch is refused (FR-001).

    The node branch is always `factory/<epic>/<node>`; if a node id collided with
    the default branch's name, pushing it would clobber the repo's trunk. The
    helper refuses with an error naming the default branch.
    """
    repo, _ = origin_repo
    default = git(repo, "symbolic-ref", "--short", "HEAD").strip()
    with pytest.raises(WorktreeError) as raised:
        push_branch(repo, EPIC, default, factory_root=factory_root)

    assert default in str(raised.value)


def test_repush_after_new_commits_succeeds(
    origin_repo: tuple[Path, Path], factory_root: Path
) -> None:
    """A second push after the branch gains commits is a normal fast-forward.

    This is the recovery case: the branch is re-pushed after a sync, and git
    must accept it because it is strictly ahead of what origin holds.
    """
    repo, bare = origin_repo
    prepared = ensure(repo, EPIC, NODE, factory_root=factory_root)
    (Path(prepared.path) / "one.txt").write_text("1\n", encoding="utf-8")
    git(prepared.path, "add", "-A")
    git(prepared.path, "commit", "--quiet", "-m", "first")
    push_branch(repo, EPIC, NODE, factory_root=factory_root)

    # A second commit lands on the branch, then the re-push.
    (Path(prepared.path) / "two.txt").write_text("2\n", encoding="utf-8")
    git(prepared.path, "add", "-A")
    git(prepared.path, "commit", "--quiet", "-m", "second")
    push_branch(repo, EPIC, NODE, factory_root=factory_root)

    assert head(bare, f"refs/heads/{prepared.branch}") == head(prepared.path)


# --- sync_with_target (US2 recovery, plan.md § US2) ---------------------------


def _advance_and_push(repo: Path, bare: Path) -> str:
    """Land a commit on the target clone's `main` and push it to origin.

    US2's recovery syncs the merge target-head *into* the node branch, so the
    world that rejected the node has to move on its branch and reach origin for
    the sync to have anything to merge. This is the "someone else landed work"
    half of the story.
    """
    (repo / "README.md").write_text("moved on\n", encoding="utf-8")
    git(repo, "commit", "--quiet", "-a", "-m", "someone else landed work")
    git(repo, "push", "--quiet", "origin", "main")
    return head(repo)


def test_sync_with_target_merges_origin_head_and_reports_a_clean_base(
    origin_repo: tuple[Path, Path], factory_root: Path
) -> None:
    """A clean sync folds `origin/<default>` into the node branch (US2-S1).

    The node branch is based on the old main; the target has moved on. Sync must
    fetch origin, merge the new head into the branch, report `clean`, and return
    the merged-in target head as the new `base_ref` — so the next diff shows only
    the node's own work (D-027 extended: recovery moves the branch point).
    """
    repo, bare = origin_repo
    prepared = ensure(repo, EPIC, NODE, factory_root=factory_root)
    worktree = Path(prepared.path)
    # The node's work touches a file the target's advance will not.
    (worktree / "node_only.txt").write_text("node work\n", encoding="utf-8")
    git(worktree, "add", "-A")
    git(worktree, "commit", "--quiet", "-m", "node work")
    push_branch(repo, EPIC, NODE, factory_root=factory_root)

    target_head = _advance_and_push(repo, bare)
    assert target_head != prepared.base_ref

    result = sync_with_target(repo, EPIC, NODE, factory_root=factory_root)

    assert result.clean is True
    assert result.conflicted_files == ()
    # The merged-in target head is the new branch point (D-027 extended).
    assert result.base_ref == target_head


def test_sync_with_target_reports_a_conflict_and_leaves_the_markers(
    origin_repo: tuple[Path, Path], factory_root: Path
) -> None:
    """A conflicting sync reports `conflict` with the file list, markers in tree.

    The conflict markers are the debugger's work surface (FR-006): the sync must
    leave them in the tree for the persona to resolve, and name the files so the
    prompt can hand the debugger the conflicted list.
    """
    repo, bare = origin_repo
    prepared = ensure(repo, EPIC, NODE, factory_root=factory_root)
    worktree = Path(prepared.path)
    # The node edits the same tracked file the target's advance will edit.
    (worktree / "src/calc.py").write_text(
        "def add(left, right):\n    return left + right + 1\n", encoding="utf-8"
    )
    git(worktree, "add", "-A")
    git(worktree, "commit", "--quiet", "-m", "node edits calc")
    push_branch(repo, EPIC, NODE, factory_root=factory_root)

    (repo / "src/calc.py").write_text(
        "def add(left, right):\n    return left + right + 2\n", encoding="utf-8"
    )
    git(repo, "commit", "--quiet", "-a", "-m", "target edits calc")
    git(repo, "push", "--quiet", "origin", "main")

    result = sync_with_target(repo, EPIC, NODE, factory_root=factory_root)

    assert result.clean is False
    assert "src/calc.py" in result.conflicted_files
    # The conflict markers are still in the tree for the debugger to resolve.
    assert "<<<<<<<" in (worktree / "src/calc.py").read_text(encoding="utf-8")


def test_sync_with_target_never_rebases_so_push_stays_fast_forward(
    origin_repo: tuple[Path, Path], factory_root: Path
) -> None:
    """Sync merges the target head in; the node branch is never rewritten (US2).

    The node's pushed branch must stay reachable and the node branch ref on
    origin must advance by fast-forward (no forced push, no rebase): a rewrite
    would overwrite history the queue is still deciding on.
    """
    repo, bare = origin_repo
    prepared = ensure(repo, EPIC, NODE, factory_root=factory_root)
    worktree = Path(prepared.path)
    (worktree / "node_only.txt").write_text("node work\n", encoding="utf-8")
    git(worktree, "add", "-A")
    git(worktree, "commit", "--quiet", "-m", "node work")
    push_branch(repo, EPIC, NODE, factory_root=factory_root)
    before = head(bare, f"refs/heads/{prepared.branch}")

    _advance_and_push(repo, bare)
    result = sync_with_target(repo, EPIC, NODE, factory_root=factory_root)
    assert result.clean is True

    # The node branch's original commit is still an ancestor — nothing rewritten.
    completed = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", before, prepared.branch],
        capture_output=True,
        text=True,
        env=git_env(),
    )
    assert completed.returncode == 0, "sync rewrote the node branch (not an ancestor)"
    # And the pushed ref advances by fast-forward, so a plain push succeeds.
    push_branch(repo, EPIC, NODE, factory_root=factory_root)
    assert head(bare, f"refs/heads/{prepared.branch}") == head(prepared.path)


def test_sync_with_target_raises_when_the_worktree_is_gone(
    repo: Path, factory_root: Path
) -> None:
    """A missing worktree is infrastructure, never a silent no-op."""
    with pytest.raises(WorktreeError) as raised:
        sync_with_target(repo, EPIC, NODE, factory_root=factory_root)

    assert str(factory_root / "worktrees" / EPIC / NODE) in str(raised.value)
