"""Probe evaluation: pure snapshot in, findings out.

Written before `factory/doctor/probes.py` exists (T010 precedes T013): until the
module lands, tests here fail at import. Every probe's judgment must be
deterministic and its finding keys stable across evaluations of the same
snapshot — recurrence, not duplication.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from temporalio.client import WorkflowExecutionStatus
from temporalio.service import RPCError, RPCStatusCode

import factory.doctor.probes as probes
from factory.doctor.models import Severity
from factory.doctor.probes import (
    KeyListSnapshot,
    OrphanedKeyProbe,
    ServiceNotAnswering,
    StoreIntegritySnapshot,
    StoreIntegrityProbe,
    StaleWorktreeProbe,
    StaleWorkerProbe,
    WorktreeSnapshot,
    WorkerSnapshot,
    _closed_epics_from_temporal,
    _discover_worker_pid,
)
from factory.workgraph.cli import workflow_id
from factory.workgraph.worktree import ERGANE_ROOT_ENV, FACTORY_ROOT_ENV


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


# --- gather paths -------------------------------------------------------------
#
# Everything above this line evaluates a hand-built snapshot, which is why the
# suite was fully green while `ergane doctor` could not complete a single run:
# no test had ever called a `gather()`. These do. Temporal is faked at
# `Client.connect` and the proxy at `LiteLLMClient.from_env`, so nothing here
# touches a live service.


class _FakeHandle:
    """One workflow's describe result, or the error it raises instead."""

    def __init__(self, *, status: Any = None, error: Exception | None = None) -> None:
        self._status = status
        self._error = error

    async def describe(self) -> Any:
        if self._error is not None:
            raise self._error
        return SimpleNamespace(status=self._status)


class _FakeTemporalClient:
    def __init__(self, handles: dict[str, _FakeHandle]) -> None:
        self._handles = handles
        self.asked: list[str] = []

    def get_workflow_handle(self, wf_id: str) -> _FakeHandle:
        self.asked.append(wf_id)
        return self._handles.get(wf_id, _FakeHandle(status=None))


@pytest.fixture
def fake_temporal(monkeypatch: pytest.MonkeyPatch):
    """Install a fake `Client.connect`; returns a `setup(...)` for the test to call."""
    import temporalio.client

    def setup(
        handles: dict[str, _FakeHandle] | None = None,
        *,
        connect_error: Exception | None = None,
    ) -> _FakeTemporalClient:
        client = _FakeTemporalClient(handles or {})

        async def _connect(target_host: str, **kwargs: Any) -> _FakeTemporalClient:
            if connect_error is not None:
                raise connect_error
            return client

        monkeypatch.setattr(temporalio.client.Client, "connect", _connect)
        return client

    return setup


class TestClosedEpicsFromTemporal:
    """Closed-ness is read from the execution status, and it is a coroutine.

    The function used to call `asyncio.run` itself, which raised RuntimeError the
    moment a caller already owned a loop, and it tested `status.is_completed` —
    an attribute `WorkflowExecutionStatus` (an IntEnum) has never had.
    """

    async def test_running_epic_is_not_closed(self, fake_temporal: Any) -> None:
        fake_temporal(
            {workflow_id("006-x"): _FakeHandle(status=WorkflowExecutionStatus.RUNNING)}
        )

        assert await _closed_epics_from_temporal({"006-x"}) == set()

    @pytest.mark.parametrize(
        "status",
        [
            WorkflowExecutionStatus.COMPLETED,
            WorkflowExecutionStatus.FAILED,
            WorkflowExecutionStatus.CANCELED,
            WorkflowExecutionStatus.TERMINATED,
            WorkflowExecutionStatus.TIMED_OUT,
        ],
    )
    async def test_every_terminal_status_reads_as_closed(
        self, fake_temporal: Any, status: WorkflowExecutionStatus
    ) -> None:
        fake_temporal({workflow_id("006-x"): _FakeHandle(status=status)})

        assert await _closed_epics_from_temporal({"006-x"}) == {"006-x"}

    async def test_continued_as_new_is_still_open(self, fake_temporal: Any) -> None:
        """A continued run is the same logical epic; calling it closed would
        invite an operator to prune a live epic's worktree."""
        fake_temporal(
            {
                workflow_id("006-x"): _FakeHandle(
                    status=WorkflowExecutionStatus.CONTINUED_AS_NEW
                )
            }
        )

        assert await _closed_epics_from_temporal({"006-x"}) == set()

    async def test_absent_workflow_reads_as_closed(self, fake_temporal: Any) -> None:
        fake_temporal(
            {
                workflow_id("006-x"): _FakeHandle(
                    error=RPCError("no such workflow", RPCStatusCode.NOT_FOUND, b"")
                )
            }
        )

        assert await _closed_epics_from_temporal({"006-x"}) == {"006-x"}

    async def test_unreachable_temporal_is_a_skip_not_a_finding(
        self, fake_temporal: Any
    ) -> None:
        """A dead port surfaces as RuntimeError from temporalio, not OSError."""
        fake_temporal(connect_error=RuntimeError("connection refused"))

        with pytest.raises(ServiceNotAnswering) as caught:
            await _closed_epics_from_temporal({"006-x"})
        assert caught.value.service == "temporal"

    async def test_describe_failure_other_than_not_found_is_a_skip(
        self, fake_temporal: Any
    ) -> None:
        fake_temporal(
            {
                workflow_id("006-x"): _FakeHandle(
                    error=RPCError("unavailable", RPCStatusCode.UNAVAILABLE, b"")
                )
            }
        )

        with pytest.raises(ServiceNotAnswering):
            await _closed_epics_from_temporal({"006-x"})


class TestGatherOwnsExactlyOneEventLoop:
    """Each probe's sync `gather()` opens the one loop; nothing under it opens another.

    These are the regression pins for the crash that made `ergane doctor` unable
    to complete a run. Both call `gather()` from sync context, which is how the
    CLI calls it.
    """

    def test_stale_worktree_gather_from_sync_context(
        self, fake_temporal: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # The session fixture pins the runtime-root env vars so tests cannot reach
        # the operator's checkout.  This gather path now routes through the resolver,
        # so drop the override and let it read the cwd (US2).
        monkeypatch.delenv(ERGANE_ROOT_ENV, raising=False)
        monkeypatch.delenv(FACTORY_ROOT_ENV, raising=False)
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".factory" / "worktrees" / "closed-epic" / "us1").mkdir(parents=True)
        fake_temporal(
            {
                workflow_id("closed-epic"): _FakeHandle(
                    status=WorkflowExecutionStatus.COMPLETED
                )
            }
        )

        snapshot = StaleWorktreeProbe().gather()

        assert "closed-epic" in snapshot.closed_epic_ids
        assert snapshot.worktrees == [Path(".factory/worktrees/closed-epic/us1")]

    def test_orphaned_key_gather_from_sync_context(
        self, fake_temporal: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.chdir(tmp_path)
        alias = "closed-epic:us1:1:implementer"

        class _StubProxy:
            async def list_key_aliases(self) -> set[str]:
                return {alias}

            async def aclose(self) -> None:
                return None

        monkeypatch.setattr(
            probes.LiteLLMClient, "from_env", classmethod(lambda cls: _StubProxy())
        )
        fake_temporal(
            {
                workflow_id("closed-epic"): _FakeHandle(
                    status=WorkflowExecutionStatus.COMPLETED
                )
            }
        )

        snapshot = OrphanedKeyProbe().gather()

        assert snapshot.aliases == {alias}
        assert snapshot.closed_epic_ids == {"closed-epic"}
        # And the whole probe still reaches its verdict from sync context.
        assert [f.key for f in OrphanedKeyProbe().evaluate(snapshot)] == [
            f"ops/orphaned-proxy-key/{alias}"
        ]


class TestWorkerDiscovery:
    """The worker is the module invocation, not a literal interpreter name.

    The old pattern was `pgrep -f "python -m factory.worker"`, which never
    matched the real `…/python3 -m factory.worker`, so `ops/stale-worker`
    — the finding this probe exists for — could not fire.
    """

    @staticmethod
    def _ps(monkeypatch: pytest.MonkeyPatch, lines: list[str]) -> None:
        def fake_run(cmd: list[str], **kwargs: Any) -> Any:
            assert cmd[0] == "ps"
            return SimpleNamespace(stdout="\n".join(lines) + "\n", returncode=0)

        monkeypatch.setattr(probes.subprocess, "run", fake_run)

    def test_finds_a_venv_python3_worker(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._ps(monkeypatch, ["4242 /repo/.venv/bin/python3 -m factory.worker"])

        assert _discover_worker_pid() == 4242

    def test_finds_a_worker_started_with_interpreter_flags(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._ps(monkeypatch, ["4242 /usr/bin/python3.12 -X dev -m factory.worker"])

        assert _discover_worker_pid() == 4242

    def test_launcher_shell_is_not_the_worker(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The shell that started the worker carries the whole invocation in its
        own `-c` argument; a substring match returns its pid and then times a
        process that is not the worker."""
        self._ps(
            monkeypatch,
            [
                "111 /bin/bash -c nohup /repo/.venv/bin/python3 -m factory.worker >> log",
                "222 /repo/.venv/bin/python3 -m factory.worker",
            ],
        )

        assert _discover_worker_pid() == 222

    def test_no_worker_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._ps(
            monkeypatch,
            [
                "111 /bin/bash -c pgrep -f 'python -m factory.worker'",
                "222 python -m factory.roadmap",
                "333 vim factory/worker.py",
            ],
        )

        assert _discover_worker_pid() is None
