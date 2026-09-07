"""US1 detector: an attempt that writes outside its worktree is caught and named.

The detector captures the state of the *target repository* and the factory's own
runtime root at attempt start, and compares again at teardown.  Any tracked path
that changed in the target repo, or any evidence store / ledger that was removed
or truncated under the runtime root, becomes a critical finding.  Node worktrees
under the runtime root — own or sibling — are not watched (epic 130 US2): a
sibling worktree is another node's workplace, and the factory removes sibling
worktrees as ordinary housekeeping, which is not an escape an attempt should be
charged for.

Key design points:

- Read-only with respect to the target repository.  We never stash, checkout,
  clean or reset it (FR-002).
- The start-state snapshot is kept *outside* the runtime root, so deleting the
  runtime root does not destroy the thing we compare against (FR-013).
- Under the runtime root, only *loss* is a finding: a path created during the
  attempt, or a store that merely grew, is silent (FR-020, FR-021).  What is
  snapshotted is the three named evidence stores at the root and nothing else —
  the detector writes ``doctor.db`` itself, so a growth rule would report the
  detector.  Sibling worktrees left the snapshot entirely in epic 130 US2
  (FR-004, FR-005); generated paths (``__pycache__``, ``.pytest_cache``,
  ``*.pyc``) left it in 073 (FR-022).
- The finding key is the *class* — ``hardening/agent-worktree-boundary``, with no
  epic or node suffix (FR-024) — so a boundary that four attempts trip is one row
  with four occurrences rather than four rows with one each.  The attribution the
  suffix used to carry moves into the refs, which name the epic and node of the
  attempt that filed the observation (FR-025), and the evidence is bounded so one
  pathological attempt cannot write a finding of unbounded size (FR-026).
- Findings are filed by writing a JSON batch to a path the operator can inspect,
  and by upserting into ``doctor.db`` when that store is still reachable.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

from factory.doctor.models import Finding, Severity, Status, parse_findings_batch
from factory.doctor.store import connect, report
from factory.workgraph.models import AttemptContext


class DetectorError(RuntimeError):
    """The detector could not read state it needed; the finding may still be filed."""


#: The category used for all detector findings.
CATEGORY = "hardening"

#: The key every detector finding is filed under: one defect class, one row
#: (FR-024).  It carries no epic or node suffix, because the ledger's job is to
#: count how often a class recurs and a key split by the thing that recurs can
#: never count it — the same four escapes arrived as forty rows of one.
FINDING_KEY = f"{CATEGORY}/agent-worktree-boundary"

#: How many changed paths one finding may name, across both halves of the
#: comparison, before the rest become a count (FR-026).  Twenty is enough to see
#: the shape of an escape and read it in a terminal; the finding that motivated a
#: bound named 3,860 paths, and evidence that large is not evidence anyone reads.
MAX_EVIDENCE_PATHS = 20

#: Directories whose contents are generated, never authored, and are therefore
#: left out of the runtime-root snapshot entirely (FR-022).  A sibling node
#: running its own suite creates and destroys these constantly, and attributing
#: that to *this* attempt is how one finding came to list 3,859 paths.
EXCLUDED_DIR_NAMES = frozenset({"__pycache__", ".pytest_cache"})

#: File suffixes excluded for the same reason.
EXCLUDED_SUFFIXES = (".pyc",)


@dataclass(frozen=True)
class TrackedState:
    """A snapshot of tracked paths in a git repository.

    Maps path (relative to repo root) to the blob sha at start, so a rename or
    mode change still shows up as a difference.
    """

    repo: Path
    blobs: dict[str, str]

    def changed(self, other: "TrackedState") -> set[str]:
        """Paths that differ between two snapshots."""
        return set(self.blobs.keys()).symmetric_difference(set(other.blobs.keys())) | {
            path
            for path in self.blobs.keys() & other.blobs.keys()
            if self.blobs[path] != other.blobs[path]
        }


@dataclass(frozen=True)
class RuntimeRootState:
    """A snapshot of critical runtime-root files.

    Records size and existence for the evidence stores at the root, so removal
    or truncation is detectable even when the runtime root itself is deleted at
    teardown.  Node worktrees are not snapshotted (epic 130 US2): a sibling's
    contents are not this attempt's escape.
    """

    root: Path | None
    entries: dict[str, dict[str, Any]]

    def changes_since(self, previous: "RuntimeRootState") -> dict[str, dict[str, Any]]:
        """Map of relative path -> {before, after} for every path *lost*.

        Only removal and truncation are reported, which is the contract this
        module's docstring has always stated (FR-020).  Two kinds of change are
        deliberately silent:

        - **Creation.** Sibling nodes run concurrently under one runtime root, so
          a path that appeared during the attempt is far more likely to be a
          sibling's output than this attempt's escape, and the snapshot cannot
          tell them apart.
        - **Growth.** The detector writes ``doctor.db`` itself, at teardown,
          after this comparison is taken (FR-021).  A rule that fired on growth
          would fire on every attempt forever, and would be reporting itself.

        Only paths present in ``previous`` can be lost, so that is the set we
        walk.
        """
        changes: dict[str, dict[str, Any]] = {}
        for path, before in previous.entries.items():
            after = self.entries.get(path)
            if _is_loss(before, after):
                changes[path] = {"before": before, "after": after}
        return changes


def _is_loss(before: Mapping[str, Any] | None, after: Mapping[str, Any] | None) -> bool:
    """Whether a path went from present to removed or truncated.

    Sizes are only meaningful for files.  A directory's ``st_size`` is its entry
    bookkeeping, which shrinks when a file is deleted from it — and that deletion
    is already reported under its own path, so comparing directory sizes would
    only double-count it and add noise from entries the detector never watched.
    """
    if before is None or not before.get("exists"):
        return False
    if after is None or not after.get("exists"):
        return True
    if before.get("kind") != "file":
        return False
    if after.get("kind") != "file":
        # Whatever replaced it, the file that was there is gone.
        return True
    before_size = before.get("size")
    after_size = after.get("size")
    if before_size is None or after_size is None:
        # ``_describe_path`` could not stat one end; do not guess a loss.
        return False
    return after_size < before_size


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _git_env() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": os.devnull,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
    }


def _git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        env=_git_env(),
        check=False,
    )
    if completed.stdout is None:
        stdout = ""
    else:
        stdout = completed.stdout
    if completed.stderr is None:
        stderr = ""
    else:
        stderr = completed.stderr
    if not completed.stdout:
        raise DetectorError(f"git {' '.join(args)} failed in {cwd}: {(stderr or stdout).strip()}")
    return stdout


def _tracked_state(repo: Path) -> TrackedState:
    """Read-only snapshot of the repository's working tree (FR-002).

    Tracks every committed path, plus any unstaged or staged changes, plus
    untracked files that are not ignored.  The detector reports what happened
    during the attempt regardless of whether the change was to a tracked path or
    a new file the operator (or agent) created; it never tries to attribute
    intent.
    """
    try:
        # ``HEAD^{tree}`` is read-only and names the tree we want; we avoid
        # ``git status`` because status mutates the index in some git versions.
        head = _git(repo, "rev-parse", "HEAD").strip()
        if not head:
            return TrackedState(repo=repo, blobs={})
        out = _git(repo, "ls-tree", "-r", "-z", head)
    except DetectorError:
        return TrackedState(repo=repo, blobs={})

    blobs: dict[str, str] = {}
    if not out:
        return TrackedState(repo=repo, blobs=blobs)

    # ls-tree -z output: "<mode> <type> <sha>\t<path>\0"
    for entry in out.split("\0"):
        if not entry:
            continue
        meta, _, path = entry.partition("\t")
        parts = meta.split()
        if len(parts) >= 3:
            blobs[path] = parts[2]

    # Overlay any unstaged or staged changes so tracked files modified in the
    # working tree during the attempt show up as changed.  ``diff-index`` is
    # read-only and compares the index against ``HEAD``; ``git diff HEAD`` covers
    # both unstaged and staged changes in one read.
    try:
        working = _git(repo, "diff-index", "--raw", "--no-abbrev", "-z", "HEAD")
    except DetectorError:
        working = ""
    # Raw diff -z lines look like:
    #   :<oldmode> <newmode> <oldsha> <newsha> <status>\t<path>\0[<newpath>\0]
    if working:
        pieces = working.split("\0")
        index = 0
        while index < len(pieces):
            piece = pieces[index]
            if not piece.startswith(":"):
                index += 1
                continue
            meta = piece[1:]
            path_piece = pieces[index + 1] if index + 1 < len(pieces) else ""
            meta_parts = meta.split()
            if len(meta_parts) >= 5 and path_piece:
                new_sha = meta_parts[3]
                status = meta_parts[4]
                if status.startswith("D"):
                    blobs.pop(path_piece, None)
                else:
                    blobs[path_piece] = new_sha
                # Rename pairs carry the new path in the next piece; skip it.
                if status.startswith("R") and index + 2 < len(pieces):
                    index += 1
            index += 2

    # Untracked (but not ignored) files are part of the working-tree state the
    # detector must report on, because operator work often arrives as new files.
    try:
        untracked = _git(repo, "ls-files", "--others", "--exclude-standard", "-z")
    except DetectorError:
        untracked = ""
    for path in untracked.split("\0"):
        if not path:
            continue
        try:
            blobs[path] = _git(repo, "hash-object", path).strip()
        except DetectorError:
            blobs[path] = ""

    return TrackedState(repo=repo, blobs=blobs)


def _committed_state(repo: Path) -> TrackedState:
    """Read-only snapshot of the committed tracked tree (HEAD).

    Used for the *start* snapshot so that any working-tree changes present when
    the attempt begins — operator work or lingering agent output — show up as a
    difference at teardown.  The teardown snapshot is the full working-tree
    state (``_tracked_state``), so modifications during the attempt are caught
    too, and the detector never attributes a change to a particular actor.
    """
    try:
        head = _git(repo, "rev-parse", "HEAD").strip()
        if not head:
            return TrackedState(repo=repo, blobs={})
        out = _git(repo, "ls-tree", "-r", "-z", head)
    except DetectorError:
        return TrackedState(repo=repo, blobs={})

    blobs: dict[str, str] = {}
    if not out:
        return TrackedState(repo=repo, blobs=blobs)

    for entry in out.split("\0"):
        if not entry:
            continue
        meta, _, path = entry.partition("\t")
        parts = meta.split()
        if len(parts) >= 3:
            blobs[path] = parts[2]

    return TrackedState(repo=repo, blobs=blobs)


def _runtime_root_state(root: Path | None, own_worktree: Path) -> RuntimeRootState:
    """Snapshot the evidence stores at the root of ``root`` — and nothing else.

    Node worktrees are not snapshotted at all, own or sibling (epic 130 US2,
    FR-004/FR-005), so ``own_worktree`` is carried in the signature only to keep
    the two call sites stable for the stories that share this file; it selects
    nothing.  A sibling worktree is where another node legitimately works, and
    the factory removes sibling worktrees as ordinary housekeeping —
    ``factory/workgraph/workflow.py`` ``_remove_worktree`` — so watching one
    charged that housekeeping to whichever attempt happened to be tearing down,
    which is the false-positive count this story exists to delete.  What can
    still be lost here, and what is still reported, is the three named stores
    below: deleting or truncating those is the 2026-08-14 destruction, and it
    stays loud.
    """
    entries: dict[str, dict[str, Any]] = {}
    if root is None or not root.exists():
        return RuntimeRootState(root=None, entries=entries)

    # Evidence stores and ledgers at the root.
    for name in ("doctor.db", "ledger.db", "verification.db"):
        path = root / name
        entries[name] = _describe_path(path)

    return RuntimeRootState(root=root, entries=entries)


def _snapshot_paths(node_dir: Path) -> Iterator[Path]:
    """Every path under ``node_dir`` worth comparing, generated output pruned.

    ``os.walk`` rather than ``rglob`` because the pruning has to happen *before*
    the descent (FR-022).  A concurrent sibling's test run fills its worktree
    with ``__pycache__`` trees, and those are the bulk of what the old snapshot
    held: excluding them at comparison time would still pay to stat, store and
    re-read thousands of entries the detector has no opinion about.
    """
    for dirpath, dirnames, filenames in os.walk(node_dir):
        dirnames[:] = [name for name in dirnames if name not in EXCLUDED_DIR_NAMES]
        directory = Path(dirpath)
        for name in dirnames:
            yield directory / name
        for name in filenames:
            if name.endswith(EXCLUDED_SUFFIXES):
                continue
            yield directory / name


def _describe_path(path: Path) -> dict[str, Any]:
    """A JSON-serializable description of a path: exists, size, type."""
    if not path.exists():
        return {"exists": False}
    try:
        size = path.stat().st_size
    except OSError:
        size = None
    kind = "dir" if path.is_dir() else "file"
    return {"exists": True, "size": size, "kind": kind}


def _snapshot_dir(factory_root: Path) -> Path:
    """A directory outside the runtime root to hold the start snapshot.

    Kept beside the runtime root, under the same parent, with a suffix that makes
    it obviously not the runtime root itself.  This satisfies FR-013: deleting
    ``.ergane`` does not delete ``.ergane-detector``.
    """
    return factory_root.parent / f"{factory_root.name}-detector"


def _write_snapshot(
    factory_root: Path,
    tracked: TrackedState | None,
    runtime: RuntimeRootState,
    context: AttemptContext,
) -> Path:
    """Persist the start snapshot outside the runtime root and return its path."""
    directory = _snapshot_dir(factory_root)
    directory.mkdir(parents=True, exist_ok=True)
    snapshot = directory / f"{context.epic_id}-{context.node_id}-{context.attempt}.json"
    data = {
        "epic_id": context.epic_id,
        "node_id": context.node_id,
        "attempt": context.attempt,
        "target_repo": str(tracked.repo) if tracked else None,
        "tracked": tracked.blobs if tracked else {},
        "runtime_root": str(runtime.root) if runtime.root else None,
        "runtime": runtime.entries,
        "captured_at": _now_iso(),
    }
    snapshot.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return snapshot


def _read_snapshot(snapshot_path: Path) -> dict[str, Any]:
    return json.loads(snapshot_path.read_text(encoding="utf-8"))


def _finding_key() -> str:
    """The class this detector files under — the same key for every attempt."""
    return FINDING_KEY


def _bounded(paths: list[str], room: int) -> tuple[list[str], int]:
    """The first ``room`` paths, and how many were left out.

    The room is shared across both halves of the finding rather than granted per
    half, so ``MAX_EVIDENCE_PATHS`` is the bound on the finding and not on each
    of its sections.
    """
    kept = paths[:room] if room > 0 else []
    return kept, len(paths) - len(kept)


def _remainder_note(dropped: int) -> str:
    """The one line that stands in for the paths the bound left out."""
    return f"  ... and {dropped} more path(s) not listed"


def _build_finding(
    context: AttemptContext,
    tracked_changes: set[str],
    runtime_changes: dict[str, dict[str, Any]],
    seen_at: str,
) -> Finding | None:
    """One critical finding naming the changed paths, or None if nothing changed.

    The counts are always exact; the *lists* are bounded (FR-026).  A finding may
    name at most ``MAX_EVIDENCE_PATHS`` paths in total, with whatever is left over
    stated as a count in the notes and in the summary, so an attempt that changed
    four thousand paths still produces a row an operator can read.  The refs are
    bounded with them, because they are the same evidence in another column.
    """
    if not tracked_changes and not runtime_changes:
        return None

    # One shared allowance, tracked half first: the tracked-path check is the half
    # that caught the real escapes, so it is the half that keeps its evidence
    # when the two compete for room.
    kept_tracked, dropped_tracked = _bounded(sorted(tracked_changes), MAX_EVIDENCE_PATHS)
    kept_runtime, dropped_runtime = _bounded(
        sorted(runtime_changes), MAX_EVIDENCE_PATHS - len(kept_tracked)
    )

    # The attempt that filed this observation.  With the key reduced to the class
    # (FR-024), these refs are the only thing naming who tripped it (FR-025).
    refs: list[str] = [f"epic:{context.epic_id}", f"node:{context.node_id}"]
    notes_parts: list[str] = []

    if tracked_changes:
        notes_parts.append("Tracked paths changed in target repository:")
        for path in kept_tracked:
            refs.append(f"target:{path}")
        if kept_tracked:
            notes_parts.append(", ".join(kept_tracked))
        if dropped_tracked:
            notes_parts.append(_remainder_note(dropped_tracked))

    if runtime_changes:
        if notes_parts:
            notes_parts.append("")
        notes_parts.append("Runtime-root paths removed or truncated:")
        for path in kept_runtime:
            refs.append(f"runtime:{path}")
            before = runtime_changes[path]["before"]
            after = runtime_changes[path]["after"]
            notes_parts.append(f"  {path}: {before} -> {after}")
        if dropped_runtime:
            notes_parts.append(_remainder_note(dropped_runtime))

    listed = kept_tracked + kept_runtime
    dropped = dropped_tracked + dropped_runtime
    evidence = ", ".join(listed) if listed else "none"
    if dropped:
        evidence = f"{evidence}, and {dropped} more"
    summary = (
        f"attempt {context.attempt} of {context.epic_id}/{context.node_id} "
        f"modified {len(tracked_changes)} tracked path(s) and "
        f"removed or truncated {len(runtime_changes)} runtime-root path(s): "
        f"{evidence}"
    )

    return Finding(
        key=_finding_key(),
        category=CATEGORY,
        severity=Severity.CRITICAL,
        status=Status.OPEN,
        summary=summary,
        refs=refs,
        notes="\n".join(notes_parts) if notes_parts else None,
        source="agent-worktree-detector",
        occurrences=1,
        first_seen=seen_at,
        last_seen=seen_at,
        promoted_spec=None,
        resolved_at=None,
        resolution=None,
    )


def capture_start(
    factory_root: Path,
    target_repo: Path,
    context: AttemptContext,
) -> Path:
    """Capture and persist the start snapshot.

    Called once at attempt start, before the agent runs.  The target-repo
    snapshot is the *committed* tree only, so any working-tree changes present
    at the beginning of the attempt are reported alongside changes made during
    the attempt.
    """
    tracked = _committed_state(target_repo)
    runtime = _runtime_root_state(factory_root, Path(context.worktree_path))
    return _write_snapshot(factory_root, tracked, runtime, context)


def compare_and_report(
    factory_root: Path,
    target_repo: Path,
    context: AttemptContext,
) -> Finding | None:
    """Compare teardown state to the start snapshot and file a finding if needed.

    Returns the finding that was filed, or None if nothing changed.  Writes the
    finding both to ``doctor.db`` (when reachable) and to a JSON batch file under
    the outside-runtime-root snapshot directory, so FR-013 holds even when the
    runtime root was deleted.
    """
    seen_at = _now_iso()
    snapshot_dir = _snapshot_dir(factory_root)
    snapshot_path = snapshot_dir / f"{context.epic_id}-{context.node_id}-{context.attempt}.json"

    if not snapshot_path.exists():
        # We cannot compare; record that the snapshot is missing as a finding.
        finding = Finding(
            key=_finding_key(),
            category=CATEGORY,
            severity=Severity.CRITICAL,
            status=Status.OPEN,
            summary=(
                f"attempt {context.attempt} of {context.epic_id}/{context.node_id}: "
                "detector start snapshot missing at teardown"
            ),
            refs=[
                f"epic:{context.epic_id}",
                f"node:{context.node_id}",
                "detector:snapshot_missing",
            ],
            notes=f"expected snapshot at {snapshot_path}",
            source="agent-worktree-detector",
            occurrences=1,
            first_seen=seen_at,
            last_seen=seen_at,
            promoted_spec=None,
            resolved_at=None,
            resolution=None,
        )
        _persist_finding(snapshot_dir, finding, factory_root)
        return finding

    start = _read_snapshot(snapshot_path)
    start_tracked = TrackedState(
        repo=Path(start["target_repo"]) if start.get("target_repo") else target_repo,
        blobs=dict(start.get("tracked", {})),
    )
    start_runtime = RuntimeRootState(
        root=Path(start["runtime_root"]) if start.get("runtime_root") else factory_root,
        entries=dict(start.get("runtime", {})),
    )

    end_tracked = _tracked_state(target_repo)
    end_runtime = _runtime_root_state(factory_root, Path(context.worktree_path))

    tracked_changes = start_tracked.changed(end_tracked)
    runtime_changes = end_runtime.changes_since(start_runtime)

    finding = _build_finding(context, tracked_changes, runtime_changes, seen_at)
    if finding is not None:
        _persist_finding(snapshot_dir, finding, factory_root)
    # Clean up the per-attempt snapshot now that comparison is done.
    with contextlib.suppress(OSError):
        snapshot_path.unlink(missing_ok=True)
    return finding


def _persist_finding(
    snapshot_dir: Path,
    finding: Finding,
    factory_root: Path,
) -> None:
    """Write the finding to the out-of-band batch and, if reachable, to doctor.db."""
    batch_path = snapshot_dir / "findings.json"
    batch = {"source": "agent-worktree-detector", "findings": []}
    if batch_path.exists():
        try:
            batch = json.loads(batch_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            batch = {"source": "agent-worktree-detector", "findings": []}

    existing = [entry for entry in batch["findings"] if entry.get("key") != finding.key]
    existing.append({
        "key": finding.key,
        "category": finding.category,
        "severity": finding.severity.value,
        "summary": finding.summary,
        "refs": finding.refs,
        "notes": finding.notes,
    })
    batch["findings"] = existing
    batch_path.write_text(json.dumps(batch, indent=2, sort_keys=True), encoding="utf-8")

    # Also write to doctor.db when the store path exists and is readable.
    db_path = factory_root / "doctor.db"
    try:
        conn = connect(db_path)
        try:
            report(conn, finding, seen_at=finding.last_seen)
        finally:
            conn.close()
    except (OSError, sqlite3.Error):
        # The runtime root may be gone; the batch file is the surviving record.
        pass


import contextlib  # noqa: E402 - imported at the end to avoid disrupting module docstring order
