"""What a gate did to the tree it was measuring (084 FR-002).

The judge scores a patch assembled from the node worktree *after* the gates have
run in it, so a gate that writes into that worktree has edited its own evidence.
Catching it needs a measurement with three properties, and only one mechanism in
this repository has all three:

- **Content, not status.** `git status --porcelain` prints ` M src.py` both
  before and after a gate rewrites a file the agent had already modified — the
  same bytes, for two different trees. Hashing the content sees the difference
  a porcelain line cannot carry.
- **Exactly what the judge's patch can carry.** `worktree.diff`
  (`factory/workgraph/worktree.py:996-1029`) stages the worktree into a scratch
  index and diffs that; ignored paths never enter it, "so a target repo's
  `.gitignore` is what keeps generated noise from reaching the judge" (`:1006`).
  A gate that writes only ignored paths cannot have changed what the judge sees,
  and counting those paths would fail every gate run Ergane has ever made:
  `uv run pytest -q` writes `__pycache__/` and `.pytest_cache/` every time.
- **Read-only where it matters.** `git add -A` runs against an index in a
  temporary directory that is thrown away with it, so nothing is staged and the
  tree a salvage commits afterwards is untouched.

**This module copies that mechanism and may not import it.**
`factory/workgraph/worktree.py:88` is `from factory.verify.gates import
scrubbed_env`, so a gate-runner import of `factory.workgraph.worktree` closes a
cycle that bites at import time rather than at test time (084 trap 4). For the
same reason the environment arrives as an argument instead of being fetched from
`factory.verify.gates`, which imports this module: the caller already computed
`scrubbed_env()` for the gate itself, and passing it means the snapshot runs
git under exactly the environment the gate ran under.

Nothing here raises past its caller for a git refusal. `run_gates` promises one
result per declared gate and never raises (`factory/verify/gates.py:1094-1098`),
so a snapshot git will not take comes back as a message on the result — an
unreadable tree fails closed and is never reported as a clean one (FR-006).
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

#: How long a snapshot's git invocation may take. Matched to
#: `factory.workgraph.worktree.GIT_TIMEOUT_S`, which bounds the same plumbing
#: over the same trees: generous enough for a large worktree, bounded so a
#: wedged git cannot become the verification's deadline.
SNAPSHOT_TIMEOUT_S = 300


@dataclass(frozen=True)
class TreeSnapshot:
    """A worktree's content, reduced to one git tree id.

    `error` is non-empty exactly when there is no id to compare — git refused
    the read. The two fields are never both filled, and an empty `tree_id` with
    an empty `error` is not a state this module produces.
    """

    tree_id: str = ""
    error: str = ""


@dataclass(frozen=True)
class WorktreeChange:
    """What happened to the worktree between two snapshots.

    `paths` is repo-relative and sorted, so a result's record is stable across
    runs and diffable. `error` carries git's own message when the comparison
    could not be made; a caller that finds it set may not report a clean tree.
    """

    paths: tuple[str, ...] = ()
    error: str = ""


class _GitRefused(Exception):
    """Git would not answer — carried as data, never raised past this module."""


def snapshot_tree(worktree: Path | str, *, env: Mapping[str, str]) -> TreeSnapshot:
    """Hash the worktree's content into a throwaway index, ignored paths out.

    Safe to call repeatedly and safe to call around a gate: the index lives in a
    temporary directory and the worktree's own index is never touched.
    """
    path = Path(worktree)
    with tempfile.TemporaryDirectory(prefix="ergane-gate-snapshot-") as scratch:
        index = {"GIT_INDEX_FILE": str(Path(scratch) / "index")}
        try:
            _git(path, "add", "-A", env=env, index=index)
            tree_id = _git(path, "write-tree", env=env, index=index).strip()
        except _GitRefused as refusal:
            return TreeSnapshot(error=str(refusal))
    return TreeSnapshot(tree_id=tree_id)


def changes_between(
    worktree: Path | str,
    before: TreeSnapshot,
    after: TreeSnapshot,
    *,
    env: Mapping[str, str],
) -> WorktreeChange:
    """Name the paths that differ between two snapshots of one worktree.

    An unreadable snapshot on either side is reported as an error rather than as
    "nothing changed": the whole point of the check is that a tree it cannot
    read is a tree it cannot vouch for.
    """
    refusal = before.error or after.error
    if refusal:
        return WorktreeChange(error=refusal)
    if before.tree_id == after.tree_id:
        return WorktreeChange()

    try:
        # `-z` because git quotes unusual path names otherwise, and a recorded
        # path is only useful to the next attempt if it is the path on disk.
        listing = _git(
            worktree,
            "diff-tree",
            "-r",
            "--no-commit-id",
            "--name-only",
            "-z",
            before.tree_id,
            after.tree_id,
            env=env,
        )
    except _GitRefused as refusal_detail:
        return WorktreeChange(error=str(refusal_detail))

    return WorktreeChange(
        paths=tuple(sorted(entry for entry in listing.split("\0") if entry))
    )


def _git(
    cwd: Path | str,
    *args: str,
    env: Mapping[str, str],
    index: Mapping[str, str] | None = None,
) -> str:
    """Run one git command, returning stdout; raise `_GitRefused` on any failure.

    `GIT_TERMINAL_PROMPT=0` for the same reason `factory.workgraph.worktree`
    sets it: a repository that wants a password becomes an error rather than a
    subprocess waiting on a terminal nobody is watching.
    """
    environment = dict(env) | {"GIT_TERMINAL_PROMPT": "0"} | dict(index or {})
    try:
        completed = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            env=environment,
            timeout=SNAPSHOT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise _GitRefused(f"git {' '.join(args)} failed in {cwd}: {error}") from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise _GitRefused(f"git {' '.join(args)} failed in {cwd}: {detail}")
    return completed.stdout
