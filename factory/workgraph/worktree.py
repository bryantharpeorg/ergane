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

- **Salvage commits an empty tree as readily as a dirty one.** SC-004 asks that
  every terminal attempt be observable from the ref alone, and an attempt that
  produced nothing is exactly the case where a log file is the only other record —
  so `--allow-empty` makes "this attempt ended, and here is how" a fact about the
  branch. It is idempotent per attempt for the mirror-image reason: an activity
  retry after an unrecorded success must not stack a second marker for the same
  attempt, or the branch stops being a readable account of what happened. What it
  will not do is skip a *dirty* tree because the marker is already there — the
  cheap duplicate commit is the better error than the discarded work.

- **Removal takes the directory, never the record.** `git worktree remove` is
  cleanup; the branch and its salvage commits survive, because once `.factory/` is
  swept they are the only thing left of the attempt.

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
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from factory.usage.models import Termination
from factory.verify.gates import scrubbed_env

#: Worker-host state directory (plan.md); relative so it resolves against the
#: worker's working directory the same way 001's ledger path does.
DEFAULT_FACTORY_ROOT = Path(".factory")

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


# The four operations ---------------------------------------------------------


def capture_base_ref(target_repo: Path | str) -> str:
    """The target clone's current commit — what a node dispatched now branches from.

    Read once, at first dispatch, and then carried: this is the moment the epic's
    view of the target repo is fixed, and every later call reads the recorded
    value rather than re-asking git.
    """
    return _git(Path(target_repo), "rev-parse", "HEAD").strip()


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
    """
    repo = Path(target_repo)
    path = worktree_path(factory_root, epic_id, node_id)
    branch = branch_name(epic_id, node_id)
    record_file = _record_file(factory_root, epic_id, node_id)
    recorded = _read_record(record_file)

    if path.is_dir():
        if recorded is not None:
            return recorded
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

    pinned = base_ref or (recorded.base_ref if recorded else capture_base_ref(repo))
    path.parent.mkdir(parents=True, exist_ok=True)
    if _branch_exists(repo, branch):
        # The branch outlives its worktree (see `remove`), so a node prepared
        # again after cleanup checks the branch out instead of re-creating it —
        # its salvaged history is the node's record and must stay reachable.
        _git(repo, "worktree", "add", "--quiet", str(path), branch)
    else:
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
    default = _default_branch(repo)

    if branch == default:
        raise WorktreeError(
            f"refusing to push branch '{branch}' to origin: it is the target "
            f"repo's default branch '{default}' (FR-001) — a node never pushes "
            "over the trunk"
        )

    if not path.is_dir():
        raise WorktreeError(f"node worktree does not exist: {path}")

    _git(repo, "push", "--quiet", remote, branch)
    return _head(path)


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


def remove(
    target_repo: Path | str,
    epic_id: str,
    node_id: str,
    *,
    factory_root: Path | str = DEFAULT_FACTORY_ROOT,
) -> None:
    """Delete the node's worktree directory, leaving the branch and its history.

    Idempotent: an already-removed worktree — or one that never existed, for a
    node killed before dispatch — is success, because terminal paths re-run on
    activity retry. The prune afterwards clears any admin entry left behind by a
    directory that went missing some other way.
    """
    repo = Path(target_repo)
    path = worktree_path(factory_root, epic_id, node_id)
    if path.is_dir():
        _git(repo, "worktree", "remove", "--force", str(path))
    _git(repo, "worktree", "prune")


# The base-ref record ---------------------------------------------------------


def _record_file(factory_root: Path | str, epic_id: str, node_id: str) -> Path:
    """Where the pin lives: beside the worktree, outside every checkout.

    Inside the worktree it would be agent work in the diff check; inside the
    target clone's `.git` it would vanish with the worktree it outlives.
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
