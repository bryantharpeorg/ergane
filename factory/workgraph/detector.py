"""US1 detector: an attempt that writes outside its worktree is caught and named.

The detector captures the state of the *target repository* and the factory's own
runtime root at attempt start, and compares again at teardown.  Any tracked path
that changed in the target repo, or any evidence store / ledger / sibling worktree
that was removed or truncated under the runtime root, becomes a critical finding.

Key design points:

- Read-only with respect to the target repository.  We never stash, checkout,
  clean or reset it (FR-002).
- The start-state snapshot is kept *outside* the runtime root, so deleting the
  runtime root does not destroy the thing we compare against (FR-013).
- The finding key is keyed by ``epic_id`` and ``node_id`` so recurrence is
  countable per node.
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
from typing import Any, Mapping

from factory.doctor.models import Finding, Severity, Status, parse_findings_batch
from factory.doctor.store import connect, report
from factory.workgraph.models import AttemptContext


class DetectorError(RuntimeError):
    """The detector could not read state it needed; the finding may still be filed."""


#: The category used for all detector findings.
CATEGORY = "hardening"


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
    """A snapshot of critical runtime-root files and directories.

    Records size and existence for stores, ledgers and every sibling worktree,
    so removal or truncation is detectable even when the runtime root itself is
    deleted at teardown.
    """

    root: Path | None
    entries: dict[str, dict[str, Any]]

    def changes_since(self, previous: "RuntimeRootState") -> dict[str, dict[str, Any]]:
        """Map of relative path -> {before, after} for any change."""
        changes: dict[str, dict[str, Any]] = {}
        all_paths = set(self.entries.keys()) | set(previous.entries.keys())
        for path in all_paths:
            before = previous.entries.get(path)
            after = self.entries.get(path)
            if before != after:
                changes[path] = {"before": before, "after": after}
        return changes


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
    """Snapshot the stores and every sibling worktree under ``root``.

    ``own_worktree`` is excluded: the agent is allowed to write there.
    """
    entries: dict[str, dict[str, Any]] = {}
    if root is None or not root.exists():
        return RuntimeRootState(root=None, entries=entries)

    own_resolved = own_worktree.resolve()

    # Evidence stores and ledgers at the root.
    for name in ("doctor.db", "ledger.db", "verification.db"):
        path = root / name
        entries[name] = _describe_path(path)

    # Every node worktree under root/worktrees/<epic>/<node>.
    worktrees_root = root / "worktrees"
    if worktrees_root.is_dir():
        for epic_dir in worktrees_root.iterdir():
            if not epic_dir.is_dir():
                continue
            for node_dir in epic_dir.iterdir():
                if not node_dir.is_dir():
                    continue
                if node_dir.resolve() == own_resolved:
                    continue
                rel = str(node_dir.relative_to(root))
                entries[rel] = _describe_path(node_dir)
                # Snapshot the worktree's contents so file changes inside it are
                # detectable, not just the directory's own metadata.
                for path in node_dir.rglob("*"):
                    entry_rel = str(path.relative_to(root))
                    entries[entry_rel] = _describe_path(path)

    return RuntimeRootState(root=root, entries=entries)


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


def _finding_key(epic_id: str, node_id: str) -> str:
    return f"hardening/agent-worktree-boundary/{epic_id}/{node_id}"


def _build_finding(
    context: AttemptContext,
    tracked_changes: set[str],
    runtime_changes: dict[str, dict[str, Any]],
    seen_at: str,
) -> Finding | None:
    """One critical finding naming every changed path, or None if nothing changed."""
    if not tracked_changes and not runtime_changes:
        return None

    refs: list[str] = []
    notes_parts: list[str] = []

    if tracked_changes:
        notes_parts.append("Tracked paths changed in target repository:")
        for path in sorted(tracked_changes):
            refs.append(f"target:{path}")
        notes_parts.append(", ".join(sorted(tracked_changes)))

    if runtime_changes:
        if notes_parts:
            notes_parts.append("")
        notes_parts.append("Runtime-root paths removed or truncated:")
        for path in sorted(runtime_changes):
            refs.append(f"runtime:{path}")
            before = runtime_changes[path]["before"]
            after = runtime_changes[path]["after"]
            notes_parts.append(f"  {path}: {before} -> {after}")

    all_changed = sorted(tracked_changes) + sorted(runtime_changes)
    summary = (
        f"attempt {context.attempt} of {context.epic_id}/{context.node_id} "
        f"modified {len(tracked_changes)} tracked path(s) and "
        f"{len(runtime_changes)} runtime-root path(s): "
        f"{', '.join(all_changed) if all_changed else 'none'}"
    )

    return Finding(
        key=_finding_key(context.epic_id, context.node_id),
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
            key=_finding_key(context.epic_id, context.node_id),
            category=CATEGORY,
            severity=Severity.CRITICAL,
            status=Status.OPEN,
            summary=(
                f"attempt {context.attempt} of {context.epic_id}/{context.node_id}: "
                "detector start snapshot missing at teardown"
            ),
            refs=["detector:snapshot_missing"],
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
