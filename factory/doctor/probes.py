"""Deterministic probes for the factory's known incident classes.

Each probe is a thin gather (impure: may touch proxy, Temporal, git, fs) and a
pure evaluation (snapshot dataclass in, findings out). The module-level
`REGISTRY` is what the `check` driver iterates: adding a probe is appending to
this list; no driver code changes.

Probes are read-only detectors. They never delete proxy keys, prune worktrees,
restart workers, or otherwise mutate factory state (FR-011). Snapshots carry
aliases and hashes only; key values never enter a probe's judgment or evidence.
"""

from __future__ import annotations

import asyncio
import os
import re
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence

from factory.doctor.models import Finding, Severity, Status
from factory.usage.litellm_client import LiteLLMClient, LiteLLMError
from factory.workgraph.cli import workflow_id
from factory.workgraph.worktree import worktree_path


class ServiceNotAnswering(Exception):
    """A probe's dependency would not answer — the probe is skipped, not silent."""

    def __init__(self, service: str, *, reason: str | None = None) -> None:
        super().__init__(f"{service} is not answering" + (f": {reason}" if reason else ""))
        self.service = service


@dataclass(frozen=True)
class FindingReport:
    """What a probe's pure evaluation emits before it becomes a store Finding."""

    key: str
    category: str
    severity: Severity
    summary: str
    refs: list[str]
    notes: str | None = None

    def to_finding(self, *, source: str) -> Finding:
        """Materialise as an open finding with source set by the caller."""
        return Finding(
            key=self.key,
            category=self.category,
            severity=self.severity,
            status=Status.OPEN,
            summary=self.summary,
            refs=list(self.refs),
            notes=self.notes,
            source=source,
            occurrences=1,
            first_seen="",
            last_seen="",
            promoted_spec=None,
            resolved_at=None,
            resolution=None,
        )


class Probe(Protocol):
    """One detector: a name, a thin gather, and a pure evaluation."""

    name: str

    def gather(self) -> Any: ...
    def evaluate(self, snapshot: Any) -> list[FindingReport]: ...


# --- snapshot dataclasses ------------------------------------------------------


@dataclass(frozen=True)
class KeyListSnapshot:
    """The orphaned-key probe's snapshot."""

    aliases: set[str]
    closed_epic_ids: set[str]


@dataclass(frozen=True)
class WorkerSnapshot:
    """The stale-worker probe's snapshot."""

    worker_pid: int | None
    worker_start_timestamp: int | None
    newest_factory_commit_timestamp: int | None
    newest_factory_commit_sha: str | None


@dataclass(frozen=True)
class WorktreeSnapshot:
    """The stale-worktree probe's snapshot."""

    worktrees: list[Path]
    closed_epic_ids: set[str]


@dataclass(frozen=True)
class StoreIntegritySnapshot:
    """The store-integrity probe's snapshot."""

    stores: list[tuple[Path, str]]


# --- helpers ------------------------------------------------------------------


#: Epic ids are dotted slugs like `015-factory-doctor`. We look for an alias
#: whose first colon-separated segment names a closed epic.
_ALIAS_EPIC_RE = re.compile(r"^([^:]+):")

#: Evidence stores the factory depends on.
_EVIDENCE_STORES = (
    Path(".factory") / "doctor.db",
    Path(".factory") / "ledger.db",
    Path(".factory") / "verification.db",
)


def _alias_epic_id(alias: str) -> str | None:
    match = _ALIAS_EPIC_RE.match(alias)
    return match.group(1) if match else None


def _closed_epic_ids() -> set[str]:
    """Read closed-ness from Temporal via the same describe path `status` uses.

    The workflow id convention is `epic-<epic_id>`. We enumerate candidate epic
    ids from the live aliases and worktree directories, then ask Temporal whether
    each workflow is closed. Any failure to talk to Temporal is a skip, not a
    finding or silence.
    """
    from temporalio.client import Client
    from temporalio.service import RPCError, RPCStatusCode

    address = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
    namespace = os.environ.get("TEMPORAL_NAMESPACE", "factory")

    candidate_epics: set[str] = set()
    # Seed with everything that looks like an epic id from live key aliases.
    # The actual gather will supply aliases; this helper is reusable for both.
    # We also scan worktree directories below.
    factory_root = Path(".factory")
    worktrees_root = factory_root / "worktrees"
    if worktrees_root.exists():
        candidate_epics.update(
            p.name for p in worktrees_root.iterdir() if p.is_dir()
        )

    async def _describe() -> set[str]:
        try:
            client = await Client.connect(address, namespace=namespace)
        except (RPCError, RuntimeError, OSError) as exc:
            raise ServiceNotAnswering(
                "temporal", reason=f"cannot connect to {address}: {exc}"
            ) from exc

        closed: set[str] = set()
        for epic_id in sorted(candidate_epics):
            handle = client.get_workflow_handle(workflow_id(epic_id))
            try:
                described = await handle.describe()
            except RPCError as exc:
                if exc.status is RPCStatusCode.NOT_FOUND:
                    # No workflow at all means the epic never started; its key is
                    # still orphaned if it exists.
                    closed.add(epic_id)
                    continue
                raise ServiceNotAnswering(
                    "temporal", reason=f"describe failed for {epic_id}: {exc}"
                ) from exc
            # A closed workflow has a terminal execution status.
            if described.status is not None and described.status.is_completed:
                closed.add(epic_id)
        return closed

    return asyncio.run(_describe())


def _newest_factory_commit() -> tuple[int, str]:
    """Timestamp and sha of the newest commit touching `factory/`."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ct %H", "--", "factory/"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise ServiceNotAnswering("git", reason=str(exc)) from exc
    line = result.stdout.strip()
    if not line:
        raise ServiceNotAnswering("git", reason="no commits touched factory/")
    timestamp_str, sha = line.split(" ", 1)
    return int(timestamp_str), sha


def _worker_start_time(pid: int) -> int:
    """Start time of `pid` as a UNIX timestamp.

    Prefer `/proc/<pid>/stat` for a thin read; fall back to `ps -o lstart=`.
    """
    stat_path = Path(f"/proc/{pid}/stat")
    if stat_path.exists():
        # field 22 is starttime in clock ticks since boot; converting requires
        # btime from /proc/stat. The simpler portable path is ps(1).
        pass
    try:
        result = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise ServiceNotAnswering("ps", reason=str(exc)) from exc
    text = result.stdout.strip()
    if not text:
        raise ServiceNotAnswering("ps", reason=f"no start time for pid {pid}")
    try:
        from datetime import datetime, timezone

        dt = datetime.strptime(text, "%a %b %d %H:%M:%S %Y")
        return int(dt.replace(tzinfo=timezone.utc).timestamp())
    except ValueError as exc:
        raise ServiceNotAnswering("ps", reason=f"unparseable lstart '{text}': {exc}") from exc


def _discover_worker_pid() -> int | None:
    """Find a `factory.worker` process. Returns None if none is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "python -m factory.worker"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    for line in result.stdout.strip().splitlines():
        try:
            return int(line.strip())
        except ValueError:
            continue
    return None


def _quick_check(path: Path) -> str:
    """Run `PRAGMA quick_check` on one SQLite store."""
    if not path.exists():
        return "missing"
    try:
        conn = sqlite3.connect(path)
        try:
            rows = conn.execute("PRAGMA quick_check").fetchall()
            if len(rows) == 1 and rows[0][0] == "ok":
                return "ok"
            return "; ".join(r[0] for r in rows)
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        return f"corrupt: {exc}"


# --- probes -------------------------------------------------------------------


class OrphanedKeyProbe:
    """Keys minted for closed epics outlive their epic and become orphaned."""

    name = "orphaned-key"

    async def _gather_async(self) -> KeyListSnapshot:
        try:
            client = LiteLLMClient.from_env()
        except LiteLLMError as exc:
            raise ServiceNotAnswering("proxy", reason=str(exc)) from exc
        try:
            aliases = await client.list_key_aliases()
        except LiteLLMError as exc:
            raise ServiceNotAnswering("proxy", reason=str(exc)) from exc
        finally:
            await client.aclose()

        # Build candidate epic ids from aliases so we can ask Temporal about them.
        candidate_epics: set[str] = set()
        for alias in aliases:
            epic = _alias_epic_id(alias)
            if epic is not None:
                candidate_epics.add(epic)

        # Also include worktree directories as candidates for closed-ness.
        worktrees_root = Path(".factory") / "worktrees"
        if worktrees_root.exists():
            candidate_epics.update(
                p.name for p in worktrees_root.iterdir() if p.is_dir()
            )

        closed = _closed_epics_from_temporal(candidate_epics)
        return KeyListSnapshot(aliases=aliases, closed_epic_ids=closed)

    def gather(self) -> KeyListSnapshot:
        return asyncio.run(self._gather_async())

    def evaluate(self, snapshot: KeyListSnapshot) -> list[FindingReport]:
        findings: list[FindingReport] = []
        for alias in sorted(snapshot.aliases):
            epic = _alias_epic_id(alias)
            if epic is None:
                continue
            if epic not in snapshot.closed_epic_ids:
                continue
            findings.append(
                FindingReport(
                    key=f"ops/orphaned-proxy-key/{alias}",
                    category="ops",
                    severity=Severity.WARNING,
                    summary=f"proxy key alias `{alias}` names closed epic `{epic}`",
                    refs=[f"proxy/alias:{alias}"],
                    notes=(
                        "A virtual key minted for an epic has outlived the epic's "
                        "workflow and should be revoked once its findings are reviewed."
                    ),
                )
            )
        return findings


class StaleWorkerProbe:
    """A worker process older than the newest `factory/` commit is stale."""

    name = "stale-worker"

    def gather(self) -> WorkerSnapshot:
        newest_ts, newest_sha = _newest_factory_commit()
        pid = _discover_worker_pid()
        if pid is None:
            return WorkerSnapshot(
                worker_pid=None,
                worker_start_timestamp=None,
                newest_factory_commit_timestamp=newest_ts,
                newest_factory_commit_sha=newest_sha,
            )
        start_ts = _worker_start_time(pid)
        return WorkerSnapshot(
            worker_pid=pid,
            worker_start_timestamp=start_ts,
            newest_factory_commit_timestamp=newest_ts,
            newest_factory_commit_sha=newest_sha,
        )

    def evaluate(self, snapshot: WorkerSnapshot) -> list[FindingReport]:
        if snapshot.worker_pid is None:
            return [
                FindingReport(
                    key="ops/no-worker-running",
                    category="ops",
                    severity=Severity.INFO,
                    summary="no factory worker process is running",
                    refs=["process/factory.worker"],
                    notes="A laptop run is not an incident; this is informational only.",
                )
            ]
        assert snapshot.worker_start_timestamp is not None
        assert snapshot.newest_factory_commit_timestamp is not None
        if snapshot.worker_start_timestamp >= snapshot.newest_factory_commit_timestamp:
            return []
        return [
            FindingReport(
                key="ops/stale-worker",
                category="ops",
                severity=Severity.CRITICAL,
                summary=(
                    f"factory worker pid {snapshot.worker_pid} started at "
                    f"{snapshot.worker_start_timestamp}, before newest `factory/` commit "
                    f"{snapshot.newest_factory_commit_sha} at "
                    f"{snapshot.newest_factory_commit_timestamp}"
                ),
                refs=[
                    f"process/start:{snapshot.worker_start_timestamp}",
                    f"git/timestamp:{snapshot.newest_factory_commit_timestamp}",
                    f"process/pid:{snapshot.worker_pid}",
                    f"git/commit:{snapshot.newest_factory_commit_sha}",
                ],
                notes=(
                    "The e5c5569 incident class: an activity-code fix dispatched by a "
                    "worker still running old code. Restart the worker before trusting "
                    "verification results."
                ),
            )
        ]


class StaleWorktreeProbe:
    """Worktrees under `.factory/worktrees/` for closed epics accumulate."""

    name = "stale-worktree"

    def gather(self) -> WorktreeSnapshot:
        worktrees_root = Path(".factory") / "worktrees"
        worktrees: list[Path] = []
        if worktrees_root.exists():
            for epic_dir in worktrees_root.iterdir():
                if not epic_dir.is_dir():
                    continue
                for node_dir in epic_dir.iterdir():
                    if node_dir.is_dir():
                        worktrees.append(node_dir)

        candidate_epics = {p.name for p in worktrees}
        if worktrees_root.exists():
            candidate_epics.update(
                p.name for p in worktrees_root.iterdir() if p.is_dir()
            )
        closed = _closed_epics_from_temporal(candidate_epics)
        return WorktreeSnapshot(worktrees=worktrees, closed_epic_ids=closed)

    def evaluate(self, snapshot: WorktreeSnapshot) -> list[FindingReport]:
        stale = sorted(
            wt
            for wt in snapshot.worktrees
            if wt.parent.name in snapshot.closed_epic_ids
        )
        if not stale:
            return []
        paths = [str(p) for p in stale]
        return [
            FindingReport(
                key="ops/stale-worktrees",
                category="ops",
                severity=Severity.WARNING,
                summary=(
                    f"{len(stale)} worktree(s) belong to closed epics: "
                    + ", ".join(paths)
                ),
                refs=[f"worktree:{p}" for p in paths],
                notes="Closed epics' worktrees are accumulating under `.factory/worktrees/`.",
            )
        ]


class StoreIntegrityProbe:
    """Evidence stores are the factory's memory; silent corruption is fatal."""

    name = "store-integrity"

    def gather(self) -> StoreIntegritySnapshot:
        results: list[tuple[Path, str]] = []
        for path in _EVIDENCE_STORES:
            results.append((path, _quick_check(path)))
        return StoreIntegritySnapshot(stores=results)

    def evaluate(self, snapshot: StoreIntegritySnapshot) -> list[FindingReport]:
        bad = sorted(
            (path, outcome)
            for path, outcome in snapshot.stores
            if outcome != "ok"
        )
        if not bad:
            return []
        # One finding per store, stable key keyed on store stem.
        findings: list[FindingReport] = []
        for path, outcome in bad:
            findings.append(
                FindingReport(
                    key=f"ops/evidence-store-corruption/{path.stem}",
                    category="ops",
                    severity=Severity.CRITICAL,
                    summary=f"evidence store `{path}` failed integrity check: {outcome}",
                    refs=[f"store:{path}", f"integrity:{outcome}", f"outcome:{outcome}"],
                    notes="Silent corruption in an evidence store is found at restore time.",
                )
            )
        return findings


# --- registry -----------------------------------------------------------------


def _closed_epics_from_temporal(candidate_epics: set[str]) -> set[str]:
    """Closure reused by probes that need closed-ness; skips become probe skips."""
    from temporalio.client import Client
    from temporalio.service import RPCError, RPCStatusCode

    address = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
    namespace = os.environ.get("TEMPORAL_NAMESPACE", "factory")

    async def _describe() -> set[str]:
        try:
            client = await Client.connect(address, namespace=namespace)
        except (RPCError, RuntimeError, OSError) as exc:
            raise ServiceNotAnswering(
                "temporal", reason=f"cannot connect to {address}: {exc}"
            ) from exc

        closed: set[str] = set()
        for epic_id in sorted(candidate_epics):
            handle = client.get_workflow_handle(workflow_id(epic_id))
            try:
                described = await handle.describe()
            except RPCError as exc:
                if exc.status is RPCStatusCode.NOT_FOUND:
                    closed.add(epic_id)
                    continue
                raise ServiceNotAnswering(
                    "temporal", reason=f"describe failed for {epic_id}: {exc}"
                ) from exc
            if described.status is not None and described.status.is_completed:
                closed.add(epic_id)
        return closed

    return asyncio.run(_describe())


REGISTRY: list[Probe] = [
    OrphanedKeyProbe(),
    StaleWorkerProbe(),
    StaleWorktreeProbe(),
    StoreIntegrityProbe(),
]
