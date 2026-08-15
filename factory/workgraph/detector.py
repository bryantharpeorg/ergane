"""US1 detector: an attempt that writes outside its worktree is caught and named.

The detector captures the state of the *target repository* at attempt start,
and compares again at teardown. Any tracked path that changed becomes a
critical finding.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from factory.doctor.models import Finding, Severity, Status, parse_findings_batch
from factory.doctor.store import connect, report
from factory.workgraph.models import AttemptContext


class DetectorError(RuntimeError):
    """The detector could not read state it needed."""


@dataclass(frozen=True)
class TrackedState:
    """A snapshot of tracked paths in a git repository."""

    repo: Path
    blobs: dict[str, str]

    def changed(self, other: "TrackedState") -> set[str]:
        return set(self.blobs.keys()).symmetric_difference(set(other.blobs.keys())) | {
            path
            for path in self.blobs.keys() & other.blobs.keys()
            if self.blobs[path] != other.blobs[path]
        }


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
    stdout = completed.stdout if completed.stdout is not None else ""
    stderr = completed.stderr if completed.stderr is not None else ""
    if not completed.stdout:
        raise DetectorError(f"git {' '.join(args)} failed in {cwd}: {(stderr or stdout).strip()}")
    return stdout


def _tracked_state(repo: Path) -> TrackedState:
    """Read-only snapshot of the repository's working tree."""
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

    try:
        working = _git(repo, "diff-index", "--raw", "--no-abbrev", "-z", "HEAD")
    except DetectorError:
        working = ""
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
                if status.startswith("R") and index + 2 < len(pieces):
                    index += 1
            index += 2

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
    the attempt begins are reported alongside changes made during the attempt.
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


def _snapshot_path(factory_root: Path, context: AttemptContext) -> Path:
    snapshot_dir = factory_root / "detector-snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    return snapshot_dir / f"{context.epic_id}-{context.node_id}-{context.attempt}.json"


def capture_start(
    factory_root: Path,
    target_repo: Path,
    context: AttemptContext,
) -> Path:
    """Capture and persist the start snapshot."""
    tracked = _committed_state(target_repo)
    snapshot = _snapshot_path(factory_root, context)
    data = {
        "epic_id": context.epic_id,
        "node_id": context.node_id,
        "attempt": context.attempt,
        "target_repo": str(tracked.repo),
        "tracked": tracked.blobs,
        "captured_at": _now_iso(),
    }
    snapshot.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return snapshot


def compare_and_report(
    factory_root: Path,
    target_repo: Path,
    context: AttemptContext,
) -> Finding | None:
    """Compare teardown state to the start snapshot and file a finding if needed."""
    seen_at = _now_iso()
    snapshot_path = _snapshot_path(factory_root, context)
    if not snapshot_path.exists():
        finding = Finding(
            key=f"hardening/{context.epic_id}/{context.node_id}",
            category="hardening",
            severity=Severity.CRITICAL,
            status=Status.OPEN,
            summary=f"attempt {context.attempt} of {context.epic_id}/{context.node_id}: detector start snapshot missing",
            refs=[],
            notes=f"expected snapshot at {snapshot_path}",
            source="agent-worktree-detector",
            occurrences=1,
            first_seen=seen_at,
            last_seen=seen_at,
            promoted_spec=None,
            resolved_at=None,
            resolution=None,
        )
        _persist_finding(factory_root, finding)
        return finding

    start = json.loads(snapshot_path.read_text(encoding="utf-8"))
    start_tracked = TrackedState(
        repo=Path(start["target_repo"]),
        blobs=dict(start.get("tracked", {})),
    )
    end_tracked = _tracked_state(target_repo)
    changes = start_tracked.changed(end_tracked)
    if not changes:
        return None

    finding = Finding(
        key=f"hardening/{context.epic_id}/{context.node_id}",
        category="hardening",
        severity=Severity.CRITICAL,
        status=Status.OPEN,
        summary=f"attempt {context.attempt} of {context.epic_id}/{context.node_id} modified {len(changes)} tracked path(s)",
        refs=[f"target:{p}" for p in sorted(changes)],
        notes="Tracked paths changed in target repository: " + ", ".join(sorted(changes)),
        source="agent-worktree-detector",
        occurrences=1,
        first_seen=seen_at,
        last_seen=seen_at,
        promoted_spec=None,
        resolved_at=None,
        resolution=None,
    )
    _persist_finding(factory_root, finding)
    snapshot_path.unlink(missing_ok=True)
    return finding


def _persist_finding(factory_root: Path, finding: Finding) -> None:
    db_path = factory_root / "doctor.db"
    try:
        conn = connect(db_path)
        try:
            report(conn, finding, seen_at=finding.last_seen)
        finally:
            conn.close()
    except (OSError, sqlite3.Error):
        pass
