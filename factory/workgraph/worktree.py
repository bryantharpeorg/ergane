"""The node's one worktree: created once, reused across attempts, salvaged, removed.

Five git operations, and the whole of constitution VI's "no work is ever lost"
rests on the middle two. Every node gets exactly one worktree at
`.factory/worktrees/<epic>/<node>` on branch `factory/<epic>/<node>` (FR-013),
and every attempt of that node opens the same tree the last attempt left behind —
002's retry semantics, and the debugger persona in particular, are written against
that continuity. Rebuilding or rebasing between attempts would move the goalposts
mid-node, which is the failure 002's criteria snapshot exists to prevent (R5).

Three decisions here are load-bearing:

- **The base ref is pinned at creation and never recomputed.** The target clone's
  default branch moves whenever anyone else lands work; a node branched from it at
  first dispatch stays branched from *that* commit for its whole life. Since the
  workflow calls `ensure` again on every attempt (and on every activity re-run),
  the pin has to survive outside workflow memory: it is written beside the
  worktree as `<node>.json` and read back on reuse. Recapturing HEAD instead would
  quietly re-parent a node whose attempt 3 started after someone else's merge.
  What is captured is the *remote's* current default-branch head, fetched at that
  moment — not the clone's own HEAD, which is stale exactly when a merge-edge
  (003 FR-009) matters (see `capture_base_ref`).

- **Salvage commits an empty tree as readily as a dirty one.** SC-004 asks that
  every terminal attempt be observable from the ref alone, and an attempt that
  produced nothing is exactly the case where a log file is the only other record —
  so `--allow-empty` makes "this attempt ended, and here is how" a fact about the
  branch. It is idempotent per attempt for the mirror-image reason: an activity
  retry after an unrecorded success must not stack a second marker for the same
  attempt, or the branch stops being a readable account of what happened. What it
  will not do is skip a *dirty* tree because the marker is already there — the
  cheap duplicate commit is the better error than the discarded work.

- **Removal takes the directory and the base-ref sidecar; the branch survives.**
  `git worktree remove` is cleanup; the branch and its salvage commits survive,
  because once `.factory/` is swept they are the only thing left of the attempt.
  The `<node>.json` sidecar is swept with the directory so a later `ensure()` does
  not trust a stale pin for a removed node.

- **Reading the diff changes nothing.** `diff` is what 002's judge scores, and it
  has to include untracked files — a new module and a new test are the normal
  shape of agent output, and a patch showing only tracked edits would hand the
  judge the smaller half of the work. Git's usual way of doing that stages them;
  this one assembles the patch in a scratch index outside the worktree instead,
  so the tree the output check reads and the salvage commits is exactly the tree
  the agent left.

Salvage carries its own identity rather than borrowing the host's. Reading
`user.name` from whatever the worker host has configured would attribute the
factory's automated commits to a person who did not make them, and would produce
differently-attributed history for the same attempt on two machines. For the same
reason the subprocess environment is 002's gate allowlist: git spawned by the
factory sees no factory credentials (constitution V).

Every failure here raises `WorktreeError` naming the path involved. None of it
fails open: a worktree that cannot be created, committed to, or removed is an
infrastructure failure the caller must classify as one, never a quiet "nothing to
do" that would let a node advance on an empty record.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import warnings
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

from factory.usage.models import Termination
from factory.env import (
    ERGANE_ROOT_ENV,
    FACTORY_ROOT_ENV,
    resolve_env_path,
)
from factory.verify.factory_yaml import FactoryConfigError, load_factory_config, resolve_manifest_path
from factory.verify.gates import scrubbed_env

#: Modern worker-host state directory (US2).  `.ergane/` is the new default.
DEFAULT_RUNTIME_ROOT = Path(".ergane")

#: Legacy worker-host state directory name, still honored during the rename.
LEGACY_FACTORY_ROOT = Path(".factory")

#: Backward-compatible alias kept for callers that import the old constant.
DEFAULT_FACTORY_ROOT = DEFAULT_RUNTIME_ROOT

#: Who the factory's salvage commits are by. Deliberately a `.invalid` address:
#: these commits are machine-made and there is no mailbox behind them.
SALVAGE_AUTHOR_NAME = "Ergane Factory"
SALVAGE_AUTHOR_EMAIL = "factory@ergane.invalid"

#: Generous enough for a checkout of a large repository, bounded so a wedged git
#: cannot hold a node's terminal path open forever.
GIT_TIMEOUT_S = 300

#: How much of a worktree's patch may cross an activity boundary. The judge
#: abridges to its own, much smaller, input limit and says so (002 R6); this is
#: the bound underneath it, and it exists because the diff travels through
#: workflow history — an agent that committed a vendored tree would otherwise
#: wedge its epic with a payload Temporal refuses, after its key was spent.
DIFF_READ_LIMIT = 1024 * 1024

#: Appended when the ceiling above was reached. Disclosed for the same reason the
#: judge discloses its own elisions: a patch that was quietly cut off reads as
#: work the agent did not do.
DIFF_CLIP_NOTICE = (
    f"\n[... diff truncated at the {DIFF_READ_LIMIT}-byte worktree read limit; "
    "the remaining files are on the node's branch ...]\n"
)


class WorktreeError(RuntimeError):
    """A worktree operation failed — infrastructure, never a verdict.

    The message names the path (worktree or target clone) the operation was
    against: by the time this surfaces the operator is looking at a node id and
    needs to know which directory git refused.
    """


class RuntimeRootChoice(StrEnum):
    """Which runtime root name `resolve_factory_root` chose."""

    NEW = "new"
    LEGACY = "legacy"
    OVERRIDE = "override"


#: Module-level sentinel so the deprecation warning fires once per command/process.
_DEPRECATED_LEGACY_ROOT: str | None = None


def resolve_factory_root(
    env_name: str = "FACTORY_ROOT",
) -> tuple[Path, RuntimeRootChoice, str | None]:
    """Return the runtime root to use, which name was chosen, and the env source.

    Preferred directory name is `.ergane/`; legacy `.factory/` is honored with a
    one-time deprecation warning naming the migration command.  When both exist,
    `.ergane/` wins and the ignored legacy directory is named in the warning.

    An explicit environment override wins over both directory names.  The
    override itself is read through `factory.env.resolve_env_path` so both
    `ERGANE_ROOT` and `FACTORY_ROOT` are honored; using the legacy env name emits
    a one-time deprecation about the variable name (US3, trap 7).  When an
    override is present, the returned source is the variable name that won
    according to `resolve_env_path`'s precedence (US4).

    The directory warning is gated by a module-level flag because this resolver
    is invoked many times per epic and a per-read warning trains the operator to
    ignore it (trap 7).
    """
    override = resolve_env_path(
        ERGANE_ROOT_ENV, FACTORY_ROOT_ENV, default=""
    )
    if override != Path(""):
        source = _env_source(ERGANE_ROOT_ENV, FACTORY_ROOT_ENV)
        return override, RuntimeRootChoice.OVERRIDE, source

    new = DEFAULT_RUNTIME_ROOT
    legacy = LEGACY_FACTORY_ROOT

    new_exists = new.is_dir()
    legacy_exists = legacy.is_dir()

    if new_exists:
        if legacy_exists:
            _warn_legacy_root_once(
                f"{legacy} is ignored in favor of {new}; "
                f"run `ergane repo migrate-runtime-root` to remove the legacy directory"
            )
        return new, RuntimeRootChoice.NEW, None

    if legacy_exists:
        _warn_legacy_root_once(
            f"{legacy} is deprecated; run `ergane repo migrate-runtime-root` "
            f"to move it to {new}"
        )
        return legacy, RuntimeRootChoice.LEGACY, None

    new.mkdir(parents=True, exist_ok=True)
    return new, RuntimeRootChoice.NEW, None


def _env_source(new_name: str, old_name: str) -> str:
    """Return the variable name that supplied an override, per resolve_env_path precedence."""
    if os.environ.get(new_name) is not None:
        return new_name
    if os.environ.get(old_name) is not None:
        return old_name
    raise RuntimeError(
        f"_env_source called when neither {new_name} nor {old_name} is set"
    )


def _warn_legacy_root_once(message: str) -> None:
    """Emit a `DeprecationWarning` for the legacy root once per Python process."""
    global _DEPRECATED_LEGACY_ROOT
    if _DEPRECATED_LEGACY_ROOT is not None:
        return
    _DEPRECATED_LEGACY_ROOT = message
    warnings.warn(message, DeprecationWarning, stacklevel=2)


@dataclass(frozen=True)
class PreparedWorktree:
    """Where a node's attempts run, and what they were branched from.

    Crosses the activity boundary as JSON, so `path` is a string rather than a
    `Path`. `base_ref` is the pin described in the module docstring — the same
    value on the tenth call as on the first. `default_branch` is the target
    clone's default branch at prepare time — the `gh pr create --base` a landing
    needs (FR-001), captured here because the workflow cannot run git itself
    (constitution IV) and this is the same git fact the branch was pinned against.
    """

    path: str
    branch: str
    base_ref: str
    default_branch: str = "main"


# Naming (R5) -----------------------------------------------------------------


def branch_name(epic_id: str, node_id: str) -> str:
    """`factory/<epic>/<node>` — attributable to a node from the ref alone."""
    return f"factory/{epic_id}/{node_id}"


def worktree_path(factory_root: Path | str, epic_id: str, node_id: str) -> Path:
    """The node's one worktree, under the worker host's state directory.

    Never inside the target clone: factory state there would read as agent work
    in 002's diff check (FR-004), and salvage would commit it.
    """
    return Path(factory_root) / "worktrees" / epic_id / node_id


def salvage_message(
    epic_id: str, node_id: str, termination: Termination | str, attempt: int
) -> str:
    """The salvage commit subject (R5) — and the per-attempt idempotency key."""
    return (
        f"salvage({epic_id}/{node_id}): "
        f"{Termination(termination).value} attempt {attempt}"
    )


def archive_message(epic_id: str, node_id: str, old_tip: str) -> str:
    """Marker for a commit that captures uncommitted state before archiving a branch."""
    return f"archive({epic_id}/{node_id}): superseded at {old_tip[:12]}"


# The four operations ---------------------------------------------------------


def capture_base_ref(target_repo: Path | str) -> str:
    """The target's current *remote* head — what a node dispatched now branches from.

    Read once, at first dispatch, and then carried: this is the moment the epic's
    view of the target repo is fixed, and every later call reads the recorded
    value rather than re-asking git.

    Fetched, never read from the clone: the queue merges on the remote, and
    nothing pulls the worker host's clone in between, so the clone's own HEAD is
    stale exactly when a merge-edge (003 FR-009) matters. Found live 2026-08-07:
    us3, dispatched 21 seconds after us2's squash-merge, was pinned to the
    clone's HEAD, built without us2's code, and collided with it at PR #10. A
    clone with no `origin` pins its own HEAD — there is nothing to be stale
    against — but a fetch that *fails* raises: a quiet stale pin is the defect
    this exists to prevent.
    """
    repo = Path(target_repo)
    return _remote_head(repo)


def _remote_head(repo: Path) -> str:
    """The landing branch's current head, fetched from origin if one exists.

    Shared by `capture_base_ref` and the ancestry check: they must read the same
    head, with the same no-origin fallback and the same raise-on-fetch-failure.
    """
    branch = landing_branch(repo)
    if not _has_remote(repo, "origin"):
        return _git(repo, "rev-parse", "HEAD").strip()
    _git(repo, "fetch", "--quiet", "origin")
    return _git(repo, "rev-parse", f"origin/{branch}").strip()


def ensure(
    target_repo: Path | str,
    epic_id: str,
    node_id: str,
    *,
    base_ref: str | None = None,
    factory_root: Path | str = DEFAULT_FACTORY_ROOT,
) -> PreparedWorktree:
    """Prepare the node's worktree, or hand back the one already prepared.

    Idempotent by construction (FR-013): an existing directory is returned as-is,
    untouched — no fetch, no rebase, no reset — so an attempt opens the tree the
    previous attempt left, whatever the default branch has done since.

    `base_ref` pins the branch point when given; otherwise the recorded pin is
    reused, and only a node that has never been prepared captures a fresh one.
    A recorded pin is reused only when it is still an ancestor of the target's
    current landing-branch head (US1 FR-001); otherwise the worktree is rebuilt
    and the old branch is archived, never deleted (FR-004).
    """
    repo = Path(target_repo)
    path = worktree_path(factory_root, epic_id, node_id)
    branch = branch_name(epic_id, node_id)
    record_file = _record_file(factory_root, epic_id, node_id)
    recorded = _read_record(record_file)

    if path.is_dir():
        if recorded is not None:
            # FR-002: the directory, branch, pin and sidecar are untouched if
            # the recorded base_ref still belongs to the target's history.
            if _is_ancestor(repo, recorded.base_ref):
                return recorded
            # FR-003: the pin has diverged; archive and rebuild everything.
            _archive_node(repo, factory_root, epic_id, node_id, branch, path)
            recorded = None
        else:
            # A worktree from an older run whose record was swept: adopt it rather
            # than rebuild it, pinning to where it stands. Wrong is impossible here —
            # the tree is the node's real state either way — and rebuilding would
            # discard exactly the in-progress work the reuse rule protects.
            return _record(
                record_file,
                PreparedWorktree(
                    str(path), branch, _head(path), _default_branch(repo)
                ),
            )

    pinned = base_ref or (recorded.base_ref if recorded else None)
    if pinned is None:
        pinned = _remote_head(repo)
    elif base_ref is None:
        # Only recorded pins are ancestry-checked; an explicit caller instruction
        # remains the caller's authority. (spec Edge Cases)
        if not _is_ancestor(repo, pinned):
            _archive_node(repo, factory_root, epic_id, node_id, branch, path)
            pinned = _remote_head(repo)

    path.parent.mkdir(parents=True, exist_ok=True)
    if _branch_exists(repo, branch):
        # FR-005: a surviving branch with no recorded pin is checked out only
        # when it still descends from the freshly captured pin.
        branch_tip = _rev_parse(repo, f"refs/heads/{branch}")
        if not _is_ancestor(repo, pinned, branch_tip):
            _archive_node(repo, factory_root, epic_id, node_id, branch, path)
        else:
            _git(repo, "worktree", "add", "--quiet", str(path), branch)
            return _record(
                record_file,
                PreparedWorktree(str(path), branch, pinned, _default_branch(repo)),
            )

    _git(repo, "worktree", "add", "--quiet", "-b", branch, str(path), pinned)
    return _record(
        record_file,
        PreparedWorktree(str(path), branch, pinned, _default_branch(repo)),
    )


def salvage(
    epic_id: str,
    node_id: str,
    *,
    termination: Termination | str,
    attempt: int,
    factory_root: Path | str = DEFAULT_FACTORY_ROOT,
) -> str:
    """Commit whatever the attempt left to the node branch; return the commit sha.

    Runs on every termination path before any cleanup (constitution VI). `git add
    -A` because new files are the normal shape of agent output, and `--allow-empty`
    because an attempt that produced nothing still ended, and SC-004 wants that
    visible on the branch.

    Idempotent per attempt: a clean tree already carrying this attempt's marker
    returns the existing commit. A dirty one is committed regardless — the same
    attempt gaining a second commit is a cosmetic defect, losing the work is not.
    """
    path = worktree_path(factory_root, epic_id, node_id)
    if not path.is_dir():
        raise WorktreeError(f"node worktree does not exist: {path}")

    message = salvage_message(epic_id, node_id, termination, attempt)
    if _head_subject(path) == message and not _is_dirty(path):
        return _head(path)

    _git(path, "add", "-A")
    _git(
        path,
        # The factory's automated commits never wait on a passphrase, whatever
        # the host has configured globally.
        "-c",
        "commit.gpgsign=false",
        "commit",
        "--quiet",
        "--allow-empty",
        "-m",
        message,
        env_extra=_SALVAGE_IDENTITY,
    )
    return _head(path)


def push_branch(
    target_repo: Path | str,
    epic_id: str,
    node_id: str,
    *,
    factory_root: Path | str = DEFAULT_FACTORY_ROOT,
    remote: str = "origin",
) -> str:
    """Push the node's branch to `remote`, returning the pushed commit sha.

    US1's landing path calls this after salvage, before opening the PR: the PR's
    head branch has to exist on the remote the queue operates against (FR-001 —
    `gh pr merge --auto` runs in the target clone, whose `origin` is that
    remote). The push is plain and fast-forward, never forced: recovery syncs the
    merge target-head *into* the branch, which keeps pushes fast-forward, so
    force is never needed and would overwrite history the queue is still deciding
    on (plan.md § US1).

    Structural guard (FR-001): pushing a branch named the target repo's default
    branch is refused with an error naming it. The node branch is always
    `factory/<epic>/<node>`; a node id that collided with the trunk's name would
    clobber the repo's main line, which is not a node's to push over.
    """
    repo = Path(target_repo)
    path = worktree_path(factory_root, epic_id, node_id)
    branch = branch_name(epic_id, node_id)
    default = landing_branch(repo)

    if branch == default:
        raise WorktreeError(
            f"refusing to push branch '{branch}' to origin: it is the target "
            f"repo's landing branch '{default}' (FR-001) — a node never pushes "
            "over the trunk"
        )

    if not path.is_dir():
        raise WorktreeError(f"node worktree does not exist: {path}")

    _git(repo, "push", "--quiet", remote, branch)
    return _head(path)


@dataclass(frozen=True)
class MirrorOutcome:
    """What the salvage mirror did with the node branch — data, never an exception.

    `pushed` is the only field a caller routes on. `detail` is for whoever reads
    the record afterwards, and on a failure it carries git's own words rather
    than a paraphrase of them (047 FR-002): an operator re-driven on a summary
    debugs the summary.
    """

    branch: str
    remote: str
    pushed: bool
    detail: str


#: Reported when the mirror is switched off at its seam. Explicitly a parameter
#: rather than an environment read: the control that proves the mirror changed
#: an outcome (047 SC-004) has to be a committed test, and a test that reached
#: for an env var would be measuring the process it runs in.
MIRROR_DISABLED = "mirror disabled by its caller"


def mirror_node_branch(
    epic_id: str,
    node_id: str,
    *,
    factory_root: Path | str = DEFAULT_FACTORY_ROOT,
    remote: str = "origin",
    enabled: bool = True,
) -> MirrorOutcome:
    """Copy the node's branch to the target's remote; report the outcome, never raise.

    Salvage already makes the durable artifact. What it did not do until 047 was
    put a copy anywhere else: the only push in the tree belonged to the landing
    path, which is precisely the path a killed, timed-out or failed node never
    takes, so four terminated nodes' work existed on exactly one disk — the same
    disk an agent has already run `rm -rf` at once.

    **Nothing here may raise.** Constitution VI is unconditional: salvage happens
    on every termination path, so a target with no remote, an unreachable remote
    and a remote that refuses must each leave the salvage commit made and the
    caller none the wiser except for what this returns. `_git` raises
    `WorktreeError` on any non-zero exit and `salvage_worktree` converts that
    into a failed terminal activity; a mirror failure that reached that
    conversion would turn a successful salvage into a failed one, which is the
    exact inversion of the principle this exists to defend.

    It runs *after* salvage rather than inside it, and unconditionally: the
    per-attempt idempotency short-circuit returns before the commit, and that is
    the activity-retry path — which is exactly the path a retry after a failed
    push takes. A mirror reachable only through the commit branch would never
    run again for the attempt that most needs it.

    The push itself is `push_branch`, unchanged and uncopied: its landing-branch
    guard is the rule, and restating that rule in a second place is how two
    places start disagreeing. That also means the mirror inherits the landing
    push's whole credential story — `scrubbed_env()` plus `HOME` — and adds no
    new credential surface (constitution V).
    """
    branch = branch_name(epic_id, node_id)
    path = worktree_path(factory_root, epic_id, node_id)

    if not enabled:
        return MirrorOutcome(branch, remote, False, MIRROR_DISABLED)

    try:
        repo = _main_worktree(path)
        if not _has_remote(repo, remote):
            # A target that declares no remote is a normal target, not a broken
            # one — the posture `_remote_head` already takes when it pins a base
            # ref in a clone with no origin. The factory mirrors to what the
            # target says; it never invents a destination.
            return MirrorOutcome(
                branch,
                remote,
                False,
                f"no '{remote}' remote is configured in {repo}: nothing to mirror to",
            )
        sha = push_branch(
            repo, epic_id, node_id, factory_root=factory_root, remote=remote
        )
    except (WorktreeError, OSError, subprocess.SubprocessError) as exc:
        return MirrorOutcome(branch, remote, False, str(exc))

    return MirrorOutcome(branch, remote, True, f"pushed {branch} to {remote} at {sha}")


def _main_worktree(path: Path) -> Path:
    """The target clone a linked worktree belongs to; git lists it first.

    A linked worktree shares the repository's config, object database and ref
    store, so the mirror needs no `target_repo` handed down from the workflow —
    which is why `SalvageWorktreeInput` gains no field and the workflow schedules
    no new activity (047 FR-005). What it does need is the main worktree's
    directory, because the landing-branch guard reads the manifest committed
    there.
    """
    for line in _git(path, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            return Path(line.split(" ", 1)[1])
    raise WorktreeError(f"git named no main worktree for {path}")


@dataclass(frozen=True)
class SyncResult:
    """The outcome of a sync-with-target, as data the workflow can route.

    `clean` is True when the target head merged into the node branch without a
    conflict. `base_ref` is the merged-in target head — the new branch point the
    next diff is measured from, so re-verification sees only the node's own work
    (D-027 extended: recovery moves the branch point). `conflicted_files` names
    the paths whose merge conflicted; on a clean sync it is empty, and on a
    conflict the markers are left in the tree for the debugger persona to resolve
    (FR-006).
    """

    clean: bool
    base_ref: str
    conflicted_files: tuple[str, ...]


def sync_with_target(
    target_repo: Path | str,
    epic_id: str,
    node_id: str,
    *,
    factory_root: Path | str = DEFAULT_FACTORY_ROOT,
    remote: str = "origin",
) -> SyncResult:
    """Merge the target's new head into the node branch inside its worktree (US2).

    US2's first recovery move: a `CHECKS_FAILED` rejection means the target branch
    moved under the node and the rebased tree went red. The branch is synced by
    fetching `remote` and merging `remote/<default>` *into* the node branch — a
    merge, never a rebase — because the branch is pushed and history stays
    fast-forward so the re-push (after the node's fix) is plain.

    A clean merge reports `clean=True` and returns the merged-in target head as
    the new `base_ref`, so re-verification's diff and judge see only the node's
    own work (D-027 extended). A conflict reports `clean=False` with the
    conflicted file list and leaves the conflict markers in the tree — the
    debugger persona's work surface (FR-006).

    The node branch is never rewritten: no rebase, no force, no reset. The commit
    the queue may still be deciding on stays reachable (FR-008).
    """
    repo = Path(target_repo)
    path = worktree_path(factory_root, epic_id, node_id)
    default = landing_branch(repo)

    if not path.is_dir():
        raise WorktreeError(f"node worktree does not exist: {path}")

    # Bring the remote's refs up to date against the target clone, so
    # `remote/<default>` names the head the queue just moved under the node.
    _git(repo, "fetch", "--quiet", remote)

    target_ref = f"{remote}/{default}"
    try:
        # Merge, in the node's worktree, onto the node branch. The merge commit
        # is the factory's (the `_SALVAGE_IDENTITY` salvage already uses), and
        # never waits on a passphrase.
        _git(
            path,
            "-c",
            "commit.gpgsign=false",
            "merge",
            "--quiet",
            target_ref,
            env_extra=_SALVAGE_IDENTITY,
        )
    except WorktreeError:
        # The merge conflicted: git exited non-zero and left the markers in the
        # tree. Report the conflicted paths as data, with the merged-in target
        # head as the base the debugger resolves against.
        return SyncResult(
            clean=False,
            base_ref=_target_head(repo, target_ref),
            conflicted_files=_conflicted_files(path),
        )

    return SyncResult(
        clean=True,
        base_ref=_target_head(repo, target_ref),
        conflicted_files=(),
    )


def _target_head(repo: Path, ref: str) -> str:
    """What `ref` names right now — the merged-in target head."""
    return _git(repo, "rev-parse", ref).strip()


def _conflicted_files(path: Path) -> tuple[str, ...]:
    """Paths git reports as unmerged after a conflicted merge (FR-006)."""
    try:
        out = _git(path, "diff", "--name-only", "--diff-filter=U")
    except WorktreeError:
        return ()
    return tuple(line for line in out.splitlines() if line)


def landing_branch(repo: Path | str) -> str:
    """The branch the target repo declares the factory lands on, or today's path.

    Reads the manifest first; absent or malformed manifest falls back to the
    clone's currently checked-out branch via `_default_branch`. This is a
    *decision* about which branch matters for landing, and it replaces the three
    separate guesses the factory used to make.
    """
    try:
        manifest_path, _ = resolve_manifest_path(repo)
        return load_factory_config(manifest_path).landing_branch
    except (FactoryConfigError, OSError):
        # Missing manifest or one the schema refuses: preserve today's behaviour.
        # The gate run will report the bad manifest as a CONFIG_ERROR; a branch
        # reader should not pre-empt that with a less informative exception.
        return _default_branch(Path(repo))


def _default_branch(repo: Path) -> str:
    """The target clone's default branch (its current `HEAD`'s symbolic ref).

    Read live at push time so a repo that renames its trunk mid-epic is refused
    against the current name, not the one pinned when the worktree was created.
    """
    try:
        return _git(repo, "symbolic-ref", "--short", "HEAD").strip()
    except WorktreeError:
        # A detached HEAD has no symbolic ref; fall back to what git calls the
        # default so the guard still has *a* name to compare against.
        return _git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()


def diff(worktree: Path | str, *, base_ref: str, limit: int = DIFF_READ_LIMIT) -> str:
    """Everything the attempt changed, as one patch — what 002's judge scores.

    Worktree-vs-`base_ref` — the ref the node branched from, not HEAD (D-027).
    R7's original worktree-vs-HEAD definition assumed the agent leaves its work
    uncommitted for salvage, but 005's prompt hands the agent the inner ralph
    contract, which says commit as you go — and against a moved HEAD the
    committed work is exactly what disappears from the patch. Found live
    2026-08-05: the judge was shown only the gates' leavings and failed a node
    whose work was green. Against the base, committed, staged and untracked
    changes are one patch; ignored files stay out, so a target repo's
    `.gitignore` is what keeps generated noise from reaching the judge.

    Read-only where it matters: `git add -A` runs against a scratch index in a
    temporary directory, never the worktree's own, so nothing is staged and the
    tree the salvage commits afterwards is untouched. Safe to call twice.

    Raises `WorktreeError` when the worktree is absent or git refuses it — the
    empty diff an absent directory resembles would read as "the agent produced
    nothing", which is a verdict rather than the infrastructure failure it is.
    """
    path = Path(worktree)
    if not path.is_dir():
        raise WorktreeError(f"node worktree does not exist: {path}")

    with tempfile.TemporaryDirectory(prefix="ergane-diff-") as scratch:
        # An index git creates from scratch here and throws away with the
        # directory: `add -A` fills it from the worktree, and the comparison
        # against the base ref is then the whole patch, new files included.
        index = {"GIT_INDEX_FILE": str(Path(scratch) / "index")}
        _git(path, "add", "-A", env_extra=index)
        patch = _git(path, "diff", "--cached", base_ref, env_extra=index)

    return _clip(patch, limit)


def _clip(patch: str, limit: int) -> str:
    """Bound the patch at `limit` bytes, saying so when there was more."""
    encoded = patch.encode("utf-8")
    if len(encoded) <= limit:
        return patch
    # Decoded leniently: the cut can land mid-character, and a patch that is one
    # byte too long is not worth an exception on the judge's only input.
    return encoded[:limit].decode("utf-8", errors="ignore") + DIFF_CLIP_NOTICE


def trees_identical(repo: Path | str, ref_a: str, ref_b: str) -> bool:
    """Compare two refs by their tree ids, never by commit sha (US3-S5).

    A recovery may add salvage or merge commits on top of the rejected tip while
    leaving every byte of content unchanged. A commit-sha comparison would miss
    the futility and silently spend a second CI run; this compares
    `git rev-parse <ref>^{tree}` for both refs.

    Raises `WorktreeError` when a ref cannot be resolved or git refuses it — an
    unknown ref is infrastructure, never a quiet mismatch.
    """
    repo = Path(repo)
    tree_a = _git(repo, "rev-parse", f"{ref_a}^{{tree}}").strip()
    tree_b = _git(repo, "rev-parse", f"{ref_b}^{{tree}}").strip()
    return tree_a == tree_b


def reset(
    target_repo: Path | str,
    epic_id: str,
    node_id: str,
    *,
    factory_root: Path | str = DEFAULT_FACTORY_ROOT,
) -> list[str]:
    """Archive a terminated node's survivors and return a human action report.

    The supported path after `temporal workflow terminate` (which bypasses the
    workflow's kill sequence — see `interpreter/cancel-bypasses-kill-sequence`,
    deliberately not fixed here).  Commits any dirty worktree state, removes the
    directory, archives the node branch, and deletes the sidecar.  Idempotent:
    a second call finds nothing to do and returns `["nothing to do"]`.

    The branch is renamed, never deleted; every commit reachable from the old
    node branch remains reachable from an archive ref.
    """
    repo = Path(target_repo)
    path = worktree_path(factory_root, epic_id, node_id)
    branch = branch_name(epic_id, node_id)

    actions: list[str] = []
    had_directory = path.is_dir()
    had_branch = _branch_exists(repo, branch)

    if had_directory or had_branch:
        _archive_node(repo, factory_root, epic_id, node_id, branch, path)

    if had_directory:
        actions.append("committed dirty state")
        actions.append("removed worktree")
    if had_branch:
        actions.append("archived branch")
    sidecar = _record_file(factory_root, epic_id, node_id)
    if sidecar.exists():
        sidecar.unlink()
        actions.append("deleted sidecar")

    if not actions:
        return ["nothing to do"]
    return actions


def remove(
    target_repo: Path | str,
    epic_id: str,
    node_id: str,
    *,
    factory_root: Path | str = DEFAULT_FACTORY_ROOT,
) -> None:
    """Delete the node's worktree directory and its sidecar, leaving the branch.

    Idempotent: an already-removed worktree — or one that never existed, for a
    node killed before dispatch — is success, because terminal paths re-run on
    activity retry. The sidecar is removed with the directory, and missing either
    is success. The prune afterwards clears any admin entry left behind by a
    directory that went missing some other way.
    """
    repo = Path(target_repo)
    path = worktree_path(factory_root, epic_id, node_id)
    record_file = _record_file(factory_root, epic_id, node_id)
    if path.is_dir():
        _git(repo, "worktree", "remove", "--force", str(path))
    _git(repo, "worktree", "prune")
    record_file.unlink(missing_ok=True)


# The base-ref record ---------------------------------------------------------


def _record_file(factory_root: Path | str, epic_id: str, node_id: str) -> Path:
    """Where the base-ref pin lives: beside the worktree, outside every checkout.

    This sidecar is a *directory* record, not a branch record; it is created with
    the worktree, read while the worktree is reused, and deleted by `remove()`
    when the worktree is swept. Inside the worktree it would be agent work in the
    diff check; inside the target clone's `.git` it would vanish with the
    worktree it outlives.
    """
    return Path(factory_root) / "worktrees" / epic_id / f"{node_id}.json"


def _record(record_file: Path, prepared: PreparedWorktree) -> PreparedWorktree:
    record_file.parent.mkdir(parents=True, exist_ok=True)
    record_file.write_text(json.dumps(asdict(prepared), indent=2) + "\n", "utf-8")
    return prepared


def _read_record(record_file: Path) -> PreparedWorktree | None:
    """The recorded preparation, or None if there is nothing readable to trust."""
    try:
        payload = json.loads(record_file.read_text(encoding="utf-8"))
        return PreparedWorktree(
            path=str(payload["path"]),
            branch=str(payload["branch"]),
            base_ref=str(payload["base_ref"]),
            # A record written before the default-branch capture has no value;
            # "main" is the universal git default and the landing's base for any
            # repo that never renamed its trunk.
            default_branch=str(payload.get("default_branch") or "main"),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


# git -------------------------------------------------------------------------

#: Identity for salvage commits, as environment rather than config so it wins
#: over anything the worker host has set.
_SALVAGE_IDENTITY = {
    "GIT_AUTHOR_NAME": SALVAGE_AUTHOR_NAME,
    "GIT_AUTHOR_EMAIL": SALVAGE_AUTHOR_EMAIL,
    "GIT_COMMITTER_NAME": SALVAGE_AUTHOR_NAME,
    "GIT_COMMITTER_EMAIL": SALVAGE_AUTHOR_EMAIL,
}


def _rev_parse(repo: Path, ref: str) -> str:
    """Resolve `ref` to a full sha; raise on failure."""
    return _git(repo, "rev-parse", ref).strip()


def _archive_node(
    repo: Path,
    factory_root: Path | str,
    epic_id: str,
    node_id: str,
    branch: str,
    path: Path,
) -> None:
    """Archive a node branch, removing any worktree first and deleting the sidecar.

    Constitution VI: any uncommitted state in an abandoned tree is committed to
    its branch before the branch is renamed. The branch is moved into the archive
    namespace with a per-tip suffix so the name is unique and idempotent on retry
    (trap 5). No existing ref is ever overwritten or deleted.
    """
    record_file = _record_file(factory_root, epic_id, node_id)
    if path.is_dir():
        if _is_dirty(path):
            _git(path, "add", "-A")
            _git(
                path,
                "-c",
                "commit.gpgsign=false",
                "commit",
                "--quiet",
                "--allow-empty",
                "-m",
                archive_message(epic_id, node_id, _head(path)),
                env_extra=_SALVAGE_IDENTITY,
            )
        _git(repo, "worktree", "remove", "--force", str(path))
    _git(repo, "worktree", "prune")

    if _branch_exists(repo, branch):
        # Resolve the tip after any dirty-state commit so the archive name embeds
        # the actual archived tip (trap 5).
        branch_tip = _rev_parse(repo, f"refs/heads/{branch}")
        archive = f"archive/factory/{epic_id}/{node_id}/{branch_tip[:12]}"
        if _branch_exists(repo, archive):
            existing = _rev_parse(repo, f"refs/heads/{archive}")
            if existing != branch_tip:
                raise WorktreeError(
                    f"archive ref {archive} exists at a different commit "
                    f"({existing[:12]}); refusing to overwrite (FR-004)"
                )
            # Same tip already archived: nothing to do for this ref.
        else:
            _git(repo, "branch", "-m", branch, archive)

    record_file.unlink(missing_ok=True)


def _git(cwd: Path, *args: str, env_extra: dict[str, str] | None = None) -> str:
    """Run one git command in `cwd`, returning stdout; raise `WorktreeError` on failure.

    The environment is 002's gate allowlist (constitution V) plus whatever this
    call needs: git spawned by the factory carries no factory credentials, and
    `GIT_TERMINAL_PROMPT=0` turns a repository that wants a password into an
    error rather than a subprocess waiting on a terminal nobody is watching.
    """
    env = scrubbed_env() | {"GIT_TERMINAL_PROMPT": "0"} | (env_extra or {})
    try:
        completed = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            env=env,
            timeout=GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise WorktreeError(f"git {' '.join(args)} failed in {cwd}: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise WorktreeError(f"git {' '.join(args)} failed in {cwd}: {detail}")
    return completed.stdout


def _head(path: Path) -> str:
    return _git(path, "rev-parse", "HEAD").strip()


def _head_subject(path: Path) -> str | None:
    """The subject of the worktree's last commit, or None if there is not one."""
    try:
        return _git(path, "log", "-1", "--format=%s").strip()
    except WorktreeError:
        return None


def _is_dirty(path: Path) -> bool:
    """Whether the tree holds anything to commit, untracked files included."""
    return bool(_git(path, "status", "--porcelain", "--untracked-files=all").strip())


def _is_ancestor(repo: Path, ancestor: str, descendant: str | None = None) -> bool:
    """True if `ancestor` is an ancestor of `descendant` (or of the current landing head).

    Modelled on `_branch_exists` (trap 3): `merge-base --is-ancestor` answers "no"
    with exit status 1, which `_git` would treat as a failure. A real git failure
    (exit > 1, timeout, missing repo) is raised as `WorktreeError`.
    """
    if descendant is None:
        descendant = _remote_head(repo)
    completed = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", ancestor, descendant],
        capture_output=True,
        text=True,
        env=scrubbed_env() | {"GIT_TERMINAL_PROMPT": "0"},
        timeout=GIT_TIMEOUT_S,
    )
    if completed.returncode == 0:
        return True
    if completed.returncode == 1:
        return False
    detail = (completed.stderr or completed.stdout).strip()
    raise WorktreeError(
        f"git merge-base --is-ancestor {ancestor} {descendant} failed in {repo}: {detail}"
    )


def _branch_exists(repo: Path, branch: str) -> bool:
    ref = f"refs/heads/{branch}"
    completed = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", ref],
        capture_output=True,
        text=True,
        env=scrubbed_env() | {"GIT_TERMINAL_PROMPT": "0"},
        timeout=GIT_TIMEOUT_S,
    )
    return completed.returncode == 0


def _has_remote(repo: Path, remote: str) -> bool:
    completed = subprocess.run(
        ["git", "-C", str(repo), "remote", "get-url", remote],
        capture_output=True,
        text=True,
        env=scrubbed_env() | {"GIT_TERMINAL_PROMPT": "0"},
        timeout=GIT_TIMEOUT_S,
    )
    return completed.returncode == 0
