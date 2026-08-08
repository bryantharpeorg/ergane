"""Probe evaluation: pure snapshot in, findings out.

Written before `factory/doctor/probes.py` exists (T010 precedes T013): until the
module lands, tests here fail at import. Every probe's judgment must be
deterministic and its finding keys stable across evaluations of the same
snapshot — recurrence, not duplication.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from factory.doctor.models import Severity
from factory.doctor.probes import (
    KeyListSnapshot,
    OrphanedKeyProbe,
    StoreIntegritySnapshot,
    StoreIntegrityProbe,
    StaleWorktreeProbe,
    StaleWorkerProbe,
    WorktreeSnapshot,
    WorkerSnapshot,
)


class TestOrphanedKeyProbe:
    """A proxy key whose alias names a closed epic is an orphaned-key incident."""

    def test_alias_for_closed_epic_files_finding_naming_alias(self) -> None:
        snapshot = KeyListSnapshot(
            aliases={"015-factory-doctor:us2:1:implementer"},
            closed_epic_ids={"015-factory-doctor"},
        )

        findings = OrphanedKeyProbe().evaluate(snapshot)

        assert len(findings) == 1
        f = findings[0]
        assert f.key == "ops/orphaned-proxy-key/015-factory-doctor:us2:1:implementer"
        assert f.category == "ops"
        assert f.severity == Severity.WARNING
        assert "015-factory-doctor:us2:1:implementer" in f.summary
        assert "015-factory-doctor:us2:1:implementer" in f.refs[0]

    def test_alias_for_open_epic_is_silent(self) -> None:
        snapshot = KeyListSnapshot(
            aliases={"015-factory-doctor:us2:1:implementer"},
            closed_epic_ids={"some-other-epic"},
        )

        assert OrphanedKeyProbe().evaluate(snapshot) == []

    def test_non_epic_alias_is_silent(self) -> None:
        snapshot = KeyListSnapshot(
            aliases={"manual-operator-key"},
            closed_epic_ids={"015-factory-doctor"},
        )

        assert OrphanedKeyProbe().evaluate(snapshot) == []

    def test_key_is_stable_across_evaluations(self) -> None:
        snapshot = KeyListSnapshot(
            aliases={"015-factory-doctor:us2:1:implementer"},
            closed_epic_ids={"015-factory-doctor"},
        )
        probe = OrphanedKeyProbe()

        first = {f.key for f in probe.evaluate(snapshot)}
        second = {f.key for f in probe.evaluate(snapshot)}
        assert first == second
        assert len(first) == 1


class TestStaleWorkerProbe:
    """A worker older than the newest `factory/` commit is a stale-worker incident."""

    def test_worker_started_before_newest_factory_commit_files_finding(self) -> None:
        snapshot = WorkerSnapshot(
            worker_pid=1234,
            worker_start_timestamp=1_000_000,
            newest_factory_commit_timestamp=2_000_000,
            newest_factory_commit_sha="abc1234",
        )

        findings = StaleWorkerProbe().evaluate(snapshot)

        assert len(findings) == 1
        f = findings[0]
        assert f.key == "ops/stale-worker"
        assert f.category == "ops"
        assert f.severity == Severity.CRITICAL
        assert "abc1234" in f.summary
        assert str(1_000_000) in f.refs[0]
        assert str(2_000_000) in f.refs[1]

    def test_worker_started_after_newest_factory_commit_is_silent(self) -> None:
        snapshot = WorkerSnapshot(
            worker_pid=1234,
            worker_start_timestamp=2_000_001,
            newest_factory_commit_timestamp=2_000_000,
            newest_factory_commit_sha="abc1234",
        )

        assert StaleWorkerProbe().evaluate(snapshot) == []

    def test_no_worker_running_files_info_finding(self) -> None:
        snapshot = WorkerSnapshot(
            worker_pid=None,
            worker_start_timestamp=None,
            newest_factory_commit_timestamp=2_000_000,
            newest_factory_commit_sha="abc1234",
        )

        findings = StaleWorkerProbe().evaluate(snapshot)

        assert len(findings) == 1
        f = findings[0]
        assert f.key == "ops/no-worker-running"
        assert f.category == "ops"
        assert f.severity == Severity.INFO

    def test_key_is_stable_across_evaluations(self) -> None:
        snapshot = WorkerSnapshot(
            worker_pid=1234,
            worker_start_timestamp=1_000_000,
            newest_factory_commit_timestamp=2_000_000,
            newest_factory_commit_sha="abc1234",
        )
        probe = StaleWorkerProbe()

        first = {f.key for f in probe.evaluate(snapshot)}
        second = {f.key for f in probe.evaluate(snapshot)}
        assert first == second
        assert len(first) == 1


class TestStaleWorktreeProbe:
    """Worktrees under `.factory/worktrees/` for closed epics are stale."""

    def test_closed_epic_worktree_files_finding_naming_paths(self) -> None:
        snapshot = WorktreeSnapshot(
            worktrees=[
                Path(".factory/worktrees/015-factory-doctor/us2"),
                Path(".factory/worktrees/closed-epic/old-node"),
            ],
            closed_epic_ids={"closed-epic"},
        )

        findings = StaleWorktreeProbe().evaluate(snapshot)

        assert len(findings) == 1
        f = findings[0]
        assert f.key == "ops/stale-worktrees"
        assert f.category == "ops"
        assert f.severity == Severity.WARNING
        assert str(Path(".factory/worktrees/closed-epic/old-node")) in f.summary
        assert str(Path(".factory/worktrees/closed-epic/old-node")) in f.refs[0]

    def test_only_open_epic_worktrees_are_silent(self) -> None:
        snapshot = WorktreeSnapshot(
            worktrees=[Path(".factory/worktrees/015-factory-doctor/us2")],
            closed_epic_ids={"closed-epic"},
        )

        assert StaleWorktreeProbe().evaluate(snapshot) == []

    def test_no_worktrees_is_silent(self) -> None:
        snapshot = WorktreeSnapshot(
            worktrees=[],
            closed_epic_ids={"closed-epic"},
        )

        assert StaleWorktreeProbe().evaluate(snapshot) == []

    def test_key_is_stable_across_evaluations(self) -> None:
        snapshot = WorktreeSnapshot(
            worktrees=[Path(".factory/worktrees/closed-epic/old-node")],
            closed_epic_ids={"closed-epic"},
        )
        probe = StaleWorktreeProbe()

        first = {f.key for f in probe.evaluate(snapshot)}
        second = {f.key for f in probe.evaluate(snapshot)}
        assert first == second
        assert len(first) == 1


class TestStoreIntegrityProbe:
    """Evidence-store corruption is a critical finding."""

    def test_failed_quick_check_files_critical_finding_naming_store(self) -> None:
        snapshot = StoreIntegritySnapshot(
            stores=[
                (Path(".factory/doctor.db"), "ok"),
                (Path(".factory/verification.db"), "corrupt: missing page"),
            ],
        )

        findings = StoreIntegrityProbe().evaluate(snapshot)

        assert len(findings) == 1
        f = findings[0]
        assert f.key == "ops/evidence-store-corruption/verification"
        assert f.category == "ops"
        assert f.severity == Severity.CRITICAL
        assert "verification.db" in f.summary
        assert any("corrupt: missing page" in ref for ref in f.refs)

    def test_all_stores_clean_is_silent(self) -> None:
        snapshot = StoreIntegritySnapshot(
            stores=[
                (Path(".factory/doctor.db"), "ok"),
                (Path(".factory/verification.db"), "ok"),
            ],
        )

        assert StoreIntegrityProbe().evaluate(snapshot) == []

    def test_key_is_stable_across_evaluations(self) -> None:
        snapshot = StoreIntegritySnapshot(
            stores=[
                (Path(".factory/doctor.db"), "ok"),
                (Path(".factory/verification.db"), "corrupt"),
            ],
        )
        probe = StoreIntegrityProbe()

        first = {f.key for f in probe.evaluate(snapshot)}
        second = {f.key for f in probe.evaluate(snapshot)}
        assert first == second
        assert len(first) == 1
