"""US1: an operator may hand finished work back, and it is recorded as theirs.

Every store in this file is created under `tmp_path`; the suite never touches the
operator's live `.factory/` (plan.md trap 7, FR-009).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from factory.activities.agent_activities import (
    LoadPromptSourcesInput,
    PrepareWorktreeInput,
    PromptSources,
    RemoveWorktreeInput,
    ResolvePersonaInput,
    SalvageWorktreeInput,
)
from factory.activities.merge_activities import (
    DisableAutoMergeInput,
    EnqueueLandingInput,
    EnqueueResult,
    OpenLandingPrInput,
    OpenLandingPrResult,
    PollLandingInput,
    PrepareLandingPrInput,
    PrepareLandingPrResult,
    ValidateTargetRepoInput,
)
from factory.activities.notify_activities import SendEscalationInput, SentEscalation
from factory.activities.usage_activities import IssueKeyInput, TeardownInput
from factory.activities.verify_activities import (
    CheckOutputInput,
    DetectQuestionInput,
    RecordVerificationInput,
    RunGatesInput,
    SnapshotCriteriaInput,
    record_external_completion,
    record_verification as _real_record_verification,
)
from factory.config import Persona, WriteScope
from factory.mergequeue.models import Finding, PrSnapshot, TargetRepoProfile
from factory.notify.service import EXTERNAL_COMPLETION_SIGNAL, TEMPORAL_ADDRESS_ENV
from factory.usage.litellm_client import PROXY_URL_ENV
from factory.usage.models import KeyLease, Termination, UsageRecord, UsageSnapshot
from factory.verify.models import CriteriaSet, GateResult, GateStatus, OutputCheck, Requirement, RequirementKind, VerificationConfig
from factory.verify.store import connect as verify_connect
from factory.workgraph.derive import derive_workgraph
from factory.workgraph.models import (
    AdapterResult,
    AttemptContext,
    EpicState,
    ResolvedNode,
    ResolvedPersona,
    WorkGraph,
    WorkNode,
    validate_workgraph,
)
from factory.workgraph.workflow import TASK_QUEUE, EpicInput, EpicStatus, EpicWorkflow, NodeStatus
from factory.workgraph.worktree import branch_name
from factory.escalation.workflow import EscalationWorkflow
from tests.test_ergane_build import Run, _invoke, env, run, temporal_env

EPIC_ID = "external_completion"
WORKFLOW_ID = f"epic-{EPIC_ID}"
TARGET_REPO = "/srv/factory/targets/external-completion"
PROXY_URL = "http://litellm.test"
MODEL_ALIAS = "implementer-alias"
JUDGE_ALIAS = "judge-alias"
LANDING_POLL_INTERVAL_S = 60

PERSONAS = {
    "implementer": Persona(
        name="implementer",
        agent="claude-code",
        model=MODEL_ALIAS,
        fallback=None,
        skills=(),
        write_scope=WriteScope.WORKTREE,
        needs_worktree=True,
        timeout_s=5400,
    )
}

PLAN_TEXT = "# Plan\n\nDo the thing.\n"
TASKS_TEXT = """# Tasks

## Phase 1: User Story 1 - The operator hands finished work back

- [ ] T001 Accept the external completion signal

## Phase 2: User Story 2 - A later node

- [ ] T002 Run after US1
"""


def _make_spec_text() -> str:
    return """# Epic: external completion

## User Scenarios & Testing

### User Story 1 - The operator hands finished work back (Priority: P1)

**Independent Test**: Signal complete_node_externally for an exhausted node.

**Acceptance Scenarios**:

1. **Given** a stuck node, **When** the operator signals completion, **Then** the node verifies and lands.

### User Story 2 - A later node (Priority: P1)

**Independent Test**: It runs after US1.

**Acceptance Scenarios**:

1. **Given** US1 completed, **When** US2 runs, **Then** it passes.

## Requirements

- **FR-001**: The system MUST accept an external completion signal.
- **FR-002**: The system MUST run US2 after US1.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001]
US2:
  depends_on: [US1]
  implements: [FR-002]
```
"""


@pytest.fixture
def verification_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "verification.db"
    monkeypatch.setenv("ERGANE_VERIFICATION_DB_PATH", str(path))
    monkeypatch.delenv("FACTORY_VERIFICATION_DB_PATH", raising=False)
    return path


@pytest.fixture
def epic_dir(tmp_path: Path) -> Path:
    spec_dir = tmp_path / EPIC_ID
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "spec.md").write_text(_make_spec_text(), encoding="utf-8")
    (spec_dir / "plan.md").write_text(PLAN_TEXT, encoding="utf-8")
    (spec_dir / "tasks.md").write_text(TASKS_TEXT, encoding="utf-8")
    return spec_dir


@pytest.fixture
def workgraph_json(epic_dir: Path, tmp_path: Path) -> Path:
    graph = derive_workgraph(
        (epic_dir / "spec.md").read_text(encoding="utf-8"),
        epic_id=EPIC_ID,
        feature=EPIC_ID,
        specs_root=str(epic_dir.parent),
        target_repo=TARGET_REPO,
    )
    graph_path = epic_dir / "workgraph.json"
    graph_path.write_text(
        json.dumps({
            "epic_id": graph.epic_id,
            "feature": graph.feature,
            "specs_root": graph.specs_root,
            "target_repo": graph.target_repo,
            "nodes": [{
                "id": node.id,
                "story_key": node.story_key,
                "persona": node.persona,
                "spec_ref": node.spec_ref,
                "requirement_keys": list(node.requirement_keys),
                "depends_on": list(node.depends_on),
                "depends_on_merged": list(node.depends_on_merged),
                "timeout_override_s": node.timeout_override_s,
            } for node in graph.nodes],
        }) + "\n",
        encoding="utf-8",
    )
    return graph_path


class ConfigurableScript:
    """Scripted activity world with per-attempt gate/judge control."""

    def __init__(
        self,
        *,
        spec_text: str,
        gate_results: list[list[GateResult]],
        output_check: OutputCheck,
        pause_at: str | None = None,
        live_snapshot: UsageSnapshot | None = None,
        hold_verification_at: tuple[str, int] | None = None,
    ) -> None:
        self._spec_text = spec_text
        self._gate_results = gate_results
        self._output_check = output_check
        self._pause_at = pause_at
        self.live_snapshot = live_snapshot
        self._hold_verification_at = hold_verification_at
        self.attempts: list[AttemptContext] = []
        self.paused = asyncio.Event()
        self._released = asyncio.Event()
        self._verification_released = asyncio.Event()
        self.verification_holding = asyncio.Event()
        self._gate_index = 0

    async def wait_for_pause(self, timeout: float = 30.0) -> None:
        await asyncio.wait_for(self.paused.wait(), timeout=timeout)

    def release(self) -> None:
        self._released.set()

    def release_verification(self) -> None:
        self._verification_released.set()

    async def wait_for_verification_hold(self, timeout: float = 30.0) -> None:
        await asyncio.wait_for(self.verification_holding.wait(), timeout=timeout)

    def gate_result(self) -> list[GateResult]:
        if self._gate_index < len(self._gate_results):
            result = self._gate_results[self._gate_index]
        else:
            result = [self._pass_gate()]
        self._gate_index += 1
        return result

    @staticmethod
    def _pass_gate() -> GateResult:
        return GateResult(
            name="test", command="uv run pytest -q", status=GateStatus.PASS,
            exit_code=0, duration_s=8.0, output_tail="12 passed in 8.01s",
        )

    @staticmethod
    def _fail_gate() -> GateResult:
        return GateResult(
            name="test", command="uv run pytest -q", status=GateStatus.FAIL,
            exit_code=1, duration_s=8.0, output_tail="1 failed in 8.01s",
        )

    def activities(self) -> list[Any]:
        script = self

        @activity.defn(name="validate_target_repo")
        async def validate_target_repo(request: ValidateTargetRepoInput) -> TargetRepoProfile:
            return TargetRepoProfile(
                repo=request.target_repo, default_branch="main", visibility="PUBLIC",
                queue_enabled=True, required_checks=("test",), declared_gates=("test",),
                findings=(
                    Finding("visibility", True, "repo is public"),
                    Finding("merge_queue", True, "merge queue enabled on main"),
                    Finding("factory_yaml", True, "factory.yaml is valid"),
                    Finding("gate_check:test", True, "required check 'test' exists"),
                ),
                passed=True,
            )

        @activity.defn(name="resolve_graph")
        async def resolve_graph(graph: WorkGraph) -> list[ResolvedNode]:
            validate_workgraph(graph, PERSONAS)
            persona = PERSONAS["implementer"]
            return [
                ResolvedNode(
                    node=node, model_alias=MODEL_ALIAS, models=[MODEL_ALIAS],
                    write_scope=persona.write_scope.value,
                    timeout_s=node.timeout_override_s or 5400,
                )
                for node in graph.nodes
            ]

        @activity.defn(name="resolve_persona")
        async def resolve_persona(request: ResolvePersonaInput) -> ResolvedPersona:
            return ResolvedPersona(persona=request.persona, model_alias=JUDGE_ALIAS, models=[JUDGE_ALIAS])

        @activity.defn(name="load_prompt_sources")
        async def load_prompt_sources(request: LoadPromptSourcesInput) -> PromptSources:
            return PromptSources(
                spec_text=script._spec_text, plan_text=PLAN_TEXT,
                tasks_text=TASKS_TEXT, standards=None,
            )

        @activity.defn(name="resolve_standards")
        async def resolve_standards(request: Any) -> None:
            # 118 US3: this world's fixture repo declares no standards, so the
            # resolution is None — the control shape.
            return None

        @activity.defn(name="snapshot_criteria")
        async def snapshot_criteria(request: SnapshotCriteriaInput) -> CriteriaSet:
            return _criteria_for(request.spec_ref)

        @activity.defn(name="prepare_worktree")
        async def prepare_worktree(request: PrepareWorktreeInput) -> Any:
            from factory.workgraph.worktree import PreparedWorktree
            return PreparedWorktree(
                path=f"/srv/factory/.factory/worktrees/{request.epic_id}/{request.node_id}",
                branch=branch_name(request.epic_id, request.node_id),
                base_ref="9" * 40,
            )

        @activity.defn(name="issue_attempt_key")
        async def issue_attempt_key(request: IssueKeyInput) -> KeyLease:
            return KeyLease(
                key=f"sk-{request.node_id}-{request.attempt}",
                key_alias=f"{request.epic_id}:{request.node_id}:{request.attempt}:{request.persona}",
                node_id=request.node_id, epic_id=request.epic_id, attempt=request.attempt,
                persona=request.persona, spec_ref=request.spec_ref,
                issued_at="2026-08-17T00:00:00Z",
            )

        @activity.defn(name="run_agent_attempt")
        async def run_agent_attempt(context: AttemptContext) -> AdapterResult:
            script.attempts.append(context)
            if script._pause_at == context.node_id:
                if script.live_snapshot is not None:
                    activity.heartbeat(script.live_snapshot)
                script.paused.set()
                try:
                    await asyncio.wait_for(script._released.wait(), timeout=30)
                except asyncio.TimeoutError:
                    pass
            return AdapterResult(
                termination=Termination.COMPLETED,
                transcript_path=f"/srv/factory/.factory/transcripts/{context.epic_id}/{context.node_id}/attempt-{context.attempt}",
            )

        @activity.defn(name="poll_usage")
        async def poll_usage(lease: KeyLease) -> UsageSnapshot:
            return UsageSnapshot(spend_usd=0.01, captured_at="2026-08-17T00:00:01Z")

        @activity.defn(name="run_gates")
        async def run_gates(request: RunGatesInput) -> list[GateResult]:
            return script.gate_result()

        @activity.defn(name="check_output")
        async def check_output(request: CheckOutputInput) -> OutputCheck:
            return script._output_check

        @activity.defn(name="record_verification")
        async def record_verification(request: RecordVerificationInput) -> Any:
            if script._hold_verification_at is not None:
                node_id, attempt = script._hold_verification_at
                if (
                    request.result.epic_id == EPIC_ID
                    and request.result.node_id == node_id
                    and request.result.attempt == attempt
                ):
                    script.verification_holding.set()
                    await asyncio.wait_for(script._verification_released.wait(), timeout=30)
            return await _real_record_verification(request)

        @activity.defn(name="teardown_attempt")
        async def teardown_attempt(request: TeardownInput) -> UsageRecord:
            lease = request.lease
            return UsageRecord(
                epic_id=lease.epic_id, node_id=lease.node_id, attempt=lease.attempt,
                persona=lease.persona, spec_ref=lease.spec_ref, key_alias=lease.key_alias,
                prompt_tokens=900, completion_tokens=120, cache_read_tokens=None,
                cache_write_tokens=None, request_count=1, spend_usd=0.003,
                final_usage_confirmed=True, termination=request.termination,
                issued_at=lease.issued_at, torn_down_at="2026-08-17T00:00:02Z",
            )

        @activity.defn(name="salvage_worktree")
        async def salvage_worktree(request: SalvageWorktreeInput) -> str:
            return "0" * 40

        @activity.defn(name="remove_worktree")
        async def remove_worktree(request: RemoveWorktreeInput) -> None:
            return None

        @activity.defn(name="prepare_landing_pr")
        async def prepare_landing_pr(request: PrepareLandingPrInput) -> PrepareLandingPrResult:
            return PrepareLandingPrResult(
                body_file=f"/srv/factory/.factory/landing/{request.epic_id}/{request.node_id}/attempt-{request.attempt}.md",
                title=f"{request.story_title}: {request.feature}",
            )

        @activity.defn(name="open_landing_pr")
        async def open_landing_pr(request: OpenLandingPrInput) -> OpenLandingPrResult:
            return OpenLandingPrResult(
                number=int(hashlib.sha1(request.branch.encode()).hexdigest()[:8], 16) % 1000 + 1,
                url=f"https://github.com/ergane/{request.target_repo}/pull/1",
            )

        @activity.defn(name="enqueue_landing")
        async def enqueue_landing(request: EnqueueLandingInput) -> EnqueueResult:
            return EnqueueResult(rejected=False, reason="")

        @activity.defn(name="poll_landing")
        async def poll_landing(request: PollLandingInput) -> PrSnapshot:
            return PrSnapshot(
                state="MERGED", is_draft=False, auto_merge_requested=False,
                merge_state_status="CLEAN", merged_at="2026-08-17T00:00:00Z",
                closed_at=None, failing_required_checks=(),
                observed_at="2026-08-17T00:00:01Z",
            )

        @activity.defn(name="disable_auto_merge")
        async def disable_auto_merge(request: DisableAutoMergeInput) -> None:
            return None

        @activity.defn(name="detect_operator_question_activity")
        async def detect_operator_question_activity(request: DetectQuestionInput) -> Any:
            from factory.verify.question import QuestionMarker
            return QuestionMarker(is_question=False)

        @activity.defn(name="send_escalation")
        async def send_escalation(request: SendEscalationInput) -> SentEscalation:
            return SentEscalation(
                escalation_id="esc-000000000000", delivered=False,
                expires_at="2026-08-17T01:00:00Z",
            )

        @activity.defn(name="expire_escalation")
        async def expire_escalation(request: Any) -> Any:
            from factory.activities.notify_activities import ExpiredEscalation
            return ExpiredEscalation(final_state="EXPIRED")

        return [
            validate_target_repo, resolve_graph, resolve_persona, load_prompt_sources,
            resolve_standards, snapshot_criteria, prepare_worktree, issue_attempt_key,
            run_agent_attempt, poll_usage, run_gates, check_output, record_verification,
            record_external_completion, teardown_attempt, salvage_worktree,
            remove_worktree, prepare_landing_pr, open_landing_pr, enqueue_landing,
            poll_landing, disable_auto_merge, detect_operator_question_activity,
            send_escalation, expire_escalation,
        ]


def worker_for(env: WorkflowEnvironment, script: ConfigurableScript) -> Worker:
    return Worker(
        env.client, task_queue=TASK_QUEUE,
        workflows=[EpicWorkflow, EscalationWorkflow],
        activities=script.activities(),
    )


def _criteria_for(spec_ref: str) -> CriteriaSet:
    return CriteriaSet(
        feature=EPIC_ID,
        spec_ref=spec_ref,
        requirements=[
            Requirement(
                key="FR-001", kind=RequirementKind.FUNCTIONAL,
                title=None, priority=None,
                body="The system MUST satisfy FR-001.",
                scenarios=[],
            )
        ],
        source_path=f"specs/{EPIC_ID}/spec.md",
        source_sha256="0" * 64,
        snapshotted_at="2026-08-17T00:00:00Z",
    )


def _output_check() -> OutputCheck:
    return OutputCheck(
        write_scope=WriteScope.WORKTREE.value,
        has_diff=True,
        expected_artifacts=[],
        artifacts_present=None,
        passed=True,
    )


def _start_epic_input(graph: WorkGraph, **overrides: Any) -> EpicInput:
    return EpicInput(
        graph=graph, proxy_url=PROXY_URL,
        config=VerificationConfig(max_attempts=1, debugger_cycles=0),
        **overrides,
    )


async def _settle_epic(env: WorkflowEnvironment) -> EpicStatus:
    handle = env.client.get_workflow_handle(WORKFLOW_ID)
    await env.sleep(timedelta(seconds=LANDING_POLL_INTERVAL_S + 1))
    raw = await handle.result()
    if isinstance(raw, EpicStatus):
        return raw
    nodes = {k: NodeStatus(**v) for k, v in raw["nodes"].items()}
    return EpicStatus(epic_state=EpicState(raw["epic_state"]), nodes=nodes)


def _external_rows(conn: sqlite3.Connection, epic_id: str, node_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT accepted, reason FROM external_completion_signals "
        "WHERE epic_id = ? AND node_id = ? ORDER BY id",
        (epic_id, node_id),
    ).fetchall()
    return [{"accepted": bool(row[0]), "reason": row[1]} for row in rows]


def _verification_row(conn: sqlite3.Connection, epic_id: str, node_id: str, attempt: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT verdict, provenance FROM verification_results "
        "WHERE epic_id = ? AND node_id = ? AND attempt = ? AND form = 'PHASE'",
        (epic_id, node_id, attempt),
    ).fetchone()
    assert row is not None
    return {"verdict": row[0], "provenance": row[1]}


async def _signal(env: WorkflowEnvironment, node_id: str, branch: str, provenance: str) -> None:
    handle = env.client.get_workflow_handle(WORKFLOW_ID)
    await handle.signal(EXTERNAL_COMPLETION_SIGNAL, args=[node_id, branch, provenance])


def load_workgraph(path: Path) -> WorkGraph:
    document = json.loads(path.read_text(encoding="utf-8"))
    return WorkGraph(
        epic_id=document["epic_id"],
        feature=document["feature"],
        specs_root=document["specs_root"],
        target_repo=document["target_repo"],
        nodes=[WorkNode(**node) for node in document["nodes"]],
    )


@pytest.mark.asyncio
async def test_external_completion_signal_refused_for_pending_node(
    env: WorkflowEnvironment,
    temporal_env: WorkflowEnvironment,
    epic_dir: Path,
    workgraph_json: Path,
    verification_db: Path,
) -> None:
    """A signal aimed at a PENDING node is recorded as refused; the node is untouched."""
    script = ConfigurableScript(
        spec_text=(epic_dir / "spec.md").read_text(encoding="utf-8"),
        gate_results=[[ConfigurableScript._pass_gate()]],
        output_check=_output_check(),
        pause_at="us1",
    )
    async with worker_for(env, script):
        await env.client.start_workflow(
            EpicWorkflow.run, _start_epic_input(load_workgraph(workgraph_json)),
            id=WORKFLOW_ID, task_queue=TASK_QUEUE,
        )
        await script.wait_for_pause()
        await _signal(env, "us2", "factory/external_completion/us2", "operator:finished-us2")
        script.release()
        result = await _settle_epic(env)

    assert result.nodes["us2"].state == "MERGED"
    conn = verify_connect(verification_db)
    rows = _external_rows(conn, EPIC_ID, "us2")
    conn.close()
    assert rows == [{"accepted": False, "reason": "node ladder has not run"}]


@pytest.mark.asyncio
async def test_external_completion_signal_refused_for_running_node(
    env: WorkflowEnvironment,
    temporal_env: WorkflowEnvironment,
    epic_dir: Path,
    workgraph_json: Path,
    verification_db: Path,
) -> None:
    """A signal aimed at a RUNNING node is recorded as refused; the node is untouched."""
    script = ConfigurableScript(
        spec_text=(epic_dir / "spec.md").read_text(encoding="utf-8"),
        gate_results=[[ConfigurableScript._pass_gate()]],
        output_check=_output_check(),
        pause_at="us1",
    )
    async with worker_for(env, script):
        await env.client.start_workflow(
            EpicWorkflow.run, _start_epic_input(load_workgraph(workgraph_json)),
            id=WORKFLOW_ID, task_queue=TASK_QUEUE,
        )
        await script.wait_for_pause()
        await _signal(env, "us1", "factory/external_completion/us1", "operator:finished-us1")
        script.release()
        result = await _settle_epic(env)

    assert result.nodes["us1"].state == "MERGED"
    conn = verify_connect(verification_db)
    rows = _external_rows(conn, EPIC_ID, "us1")
    conn.close()
    assert len(rows) == 1
    assert rows[0]["accepted"] is False
    assert rows[0]["reason"] is not None


@pytest.mark.asyncio
async def test_external_completion_signal_refused_when_attempts_remain(
    env: WorkflowEnvironment,
    temporal_env: WorkflowEnvironment,
    epic_dir: Path,
    workgraph_json: Path,
    verification_db: Path,
) -> None:
    """A signal aimed at a node that still has ladder budget is refused."""
    script = ConfigurableScript(
        spec_text=(epic_dir / "spec.md").read_text(encoding="utf-8"),
        gate_results=[[ConfigurableScript._fail_gate()], [ConfigurableScript._pass_gate()]],
        output_check=_output_check(),
        hold_verification_at=("us1", 1),
    )
    async with worker_for(env, script):
        await env.client.start_workflow(
            EpicWorkflow.run,
            EpicInput(
                graph=load_workgraph(workgraph_json),
                proxy_url=PROXY_URL,
                config=VerificationConfig(max_attempts=2, debugger_cycles=0),
            ),
            id=WORKFLOW_ID, task_queue=TASK_QUEUE,
        )
        await script.wait_for_verification_hold()
        await _signal(env, "us1", "factory/external_completion/us1", "operator:finished-us1")
        script.release_verification()
        result = await _settle_epic(env)

    assert result.nodes["us1"].state == "MERGED"
    conn = verify_connect(verification_db)
    rows = _external_rows(conn, EPIC_ID, "us1")
    conn.close()
    assert rows == [{"accepted": False, "reason": "node ladder not exhausted"}]


@pytest.mark.asyncio
async def test_external_completion_accepts_exhausted_node_and_lands(
    env: WorkflowEnvironment,
    temporal_env: WorkflowEnvironment,
    epic_dir: Path,
    workgraph_json: Path,
    verification_db: Path,
) -> None:
    """An exhausted node accepts external work, verifies it, and lands normally."""
    script = ConfigurableScript(
        spec_text=(epic_dir / "spec.md").read_text(encoding="utf-8"),
        gate_results=[[ConfigurableScript._fail_gate()]],
        output_check=_output_check(),
        hold_verification_at=("us1", 1),
    )
    async with worker_for(env, script):
        await env.client.start_workflow(
            EpicWorkflow.run, _start_epic_input(load_workgraph(workgraph_json)),
            id=WORKFLOW_ID, task_queue=TASK_QUEUE,
        )
        await script.wait_for_verification_hold()
        await _signal(env, "us1", "factory/external_completion/us1", "operator:completed-us1-after-exhaustion")
        script.release_verification()
        result = await _settle_epic(env)

    assert result.nodes["us1"].state == "MERGED"
    conn = verify_connect(verification_db)
    row = _verification_row(conn, EPIC_ID, "us1", attempt=2)
    conn.close()
    assert row["verdict"] == "PASS"
    assert row["provenance"] == "operator:completed-us1-after-exhaustion"


@pytest.mark.asyncio
async def test_external_completion_records_provenance_and_is_non_nullable_on_path(
    env: WorkflowEnvironment,
    temporal_env: WorkflowEnvironment,
    epic_dir: Path,
    workgraph_json: Path,
    verification_db: Path,
) -> None:
    """The verification row for an external completion carries its provenance."""
    script = ConfigurableScript(
        spec_text=(epic_dir / "spec.md").read_text(encoding="utf-8"),
        gate_results=[[ConfigurableScript._fail_gate()]],
        output_check=_output_check(),
        hold_verification_at=("us1", 1),
    )
    async with worker_for(env, script):
        await env.client.start_workflow(
            EpicWorkflow.run, _start_epic_input(load_workgraph(workgraph_json)),
            id=WORKFLOW_ID, task_queue=TASK_QUEUE,
        )
        await script.wait_for_verification_hold()
        await _signal(env, "us1", "factory/external_completion/us1", "operator:provenance-required")
        script.release_verification()
        await _settle_epic(env)

    conn = verify_connect(verification_db)
    row = _verification_row(conn, EPIC_ID, "us1", attempt=2)
    conn.close()
    assert row["provenance"] == "operator:provenance-required"


@pytest.mark.asyncio
async def test_external_completion_fails_when_work_breaks_gates(
    env: WorkflowEnvironment,
    temporal_env: WorkflowEnvironment,
    epic_dir: Path,
    workgraph_json: Path,
    verification_db: Path,
) -> None:
    """Externally-supplied work that breaks the gates fails the node like agent work."""
    script = ConfigurableScript(
        spec_text=(epic_dir / "spec.md").read_text(encoding="utf-8"),
        gate_results=[[ConfigurableScript._fail_gate()]],
        output_check=_output_check(),
        hold_verification_at=("us1", 1),
    )
    async with worker_for(env, script):
        await env.client.start_workflow(
            EpicWorkflow.run, _start_epic_input(load_workgraph(workgraph_json)),
            id=WORKFLOW_ID, task_queue=TASK_QUEUE,
        )
        await script.wait_for_verification_hold()
        script._gate_results = [[ConfigurableScript._fail_gate()], [ConfigurableScript._fail_gate()]]
        await _signal(env, "us1", "factory/external_completion/us1", "operator:bad-work")
        script.release_verification()
        result = await _settle_epic(env)

    assert result.nodes["us1"].state in ("KILLED", "FAILED")
    conn = verify_connect(verification_db)
    row = _verification_row(conn, EPIC_ID, "us1", attempt=2)
    conn.close()
    assert row["verdict"] == "FAIL"
    assert row["provenance"] == "operator:bad-work"


def test_complete_node_externally_cli_requires_provenance(
    run: Callable[..., Run],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CLI verb refuses to send without an explicit provenance string."""
    monkeypatch.setenv(TEMPORAL_ADDRESS_ENV, "127.0.0.1:1")
    monkeypatch.setenv(PROXY_URL_ENV, PROXY_URL)
    result = run("build", "complete-node-externally", EPIC_ID, "us1", "factory/external_completion/us1")
    assert result.code != 0
