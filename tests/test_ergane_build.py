"""Tests for `ergane build` (US3: FR-010…FR-014).

Mirrors the `start` and `status` assertions from `tests/test_epic_cli.py` but
exercises them through the new `ergane` dispatcher and the `build` noun.  The
two command surfaces must not diverge in behaviour: this file is the contract
that the ported handlers and the new exit-code values keep the old promises.

All server-touching tests use the time-skipping harness and the same scripted
activity set as `test_epic_cli.py` so that an epic actually runs and `status`
reads a real workflow state.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import timedelta
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, NamedTuple

import pytest
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.exceptions import ApplicationError
from temporalio.service import RPCError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from factory.activities.agent_activities import (
    GRAPH_INVALID,
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
from factory.activities.usage_activities import IssueKeyInput, TeardownInput
from factory.activities.verify_activities import (
    CheckOutputInput,
    DetectQuestionInput,
    RecordedVerification,
    RecordVerificationInput,
    RunGatesInput,
    SnapshotCriteriaInput,
)
from factory.cli.main import main as ergane_main
from factory.config import Persona, WriteScope
from factory.mergequeue.models import Finding, PrSnapshot, TargetRepoProfile
from factory.notify.service import (
    DEFAULT_TEMPORAL_ADDRESS,
    DEFAULT_TEMPORAL_NAMESPACE,
    QUESTION_SIGNAL_NAME,
    SIGNAL_NAME,
    TEMPORAL_ADDRESS_ENV,
    TEMPORAL_NAMESPACE_ENV,
)
from factory.usage.litellm_client import PROXY_URL_ENV, LiteLLMClient
from factory.usage.models import KeyLease, Termination, UsageRecord, UsageSnapshot
from factory.verify.models import (
    CriteriaSet,
    EscalationChoice,
    EscalationRecord,
    GateResult,
    GateStatus,
    OutputCheck,
    QuestionRecord,
    Requirement,
    RequirementKind,
)
from factory.workgraph.cli import main as legacy_epic_main
from factory.workgraph.derive import derive_workgraph
from factory.verify.store import (
    EXPIRED,
    connect as verify_connect,
    insert_escalation,
    insert_question,
    resolve_escalation,
    resolve_question,
)
from factory.workgraph.models import (
    AdapterResult,
    AttemptContext,
    ResolvedNode,
    ResolvedPersona,
    WorkGraph,
    validate_workgraph,
)
from factory.workgraph.worktree import PreparedWorktree, branch_name
from factory.verify.question import QuestionMarker
from factory.workgraph.workflow import JUDGE_PERSONA, TASK_QUEUE, EpicWorkflow
from tests.conftest import FAKE_MASTER_KEY, FakeLiteLLM
from tests.test_interpreter import merged_snapshot

CORPUS = Path(__file__).resolve().parent / "fixtures" / "workgraph"

VALID = "valid_epic"
EPIC_ID = VALID
WORKFLOW_ID = f"epic-{EPIC_ID}"
TARGET_REPO = "/srv/factory/targets/short-links"
PROXY_URL = "http://litellm.test"
LANDING_POLL_INTERVAL_S = 60
DEAD_ADDRESS = "127.0.0.1:1"
MODEL_ALIAS = "implementer-alias"
JUDGE_ALIAS = "judge-alias"
TIMEOUT_S = 5400

FR_FOR = {"US1": "FR-001", "US2": "FR-003", "US3": "FR-004"}
NODE_IDS = ["us1", "us2", "us3"]

PERSONAS = {
    "implementer": Persona(
        name="implementer",
        agent="claude-code",
        model=MODEL_ALIAS,
        fallback=None,
        skills=(),
        write_scope=WriteScope.WORKTREE,
        needs_worktree=True,
        timeout_s=TIMEOUT_S,
    )
}


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str

    @property
    def json(self) -> Any:
        return json.loads(self.stdout)


def _invoke(argv: tuple[str, ...]) -> int:
    try:
        code = ergane_main(list(argv))
    except SystemExit as exit_request:
        code = exit_request.code
    return 0 if code is None else int(code)


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Callable[..., Run]:
    def invoke(*argv: str) -> Run:
        code = _invoke(argv)
        captured = capsys.readouterr()
        return Run(code, captured.out, captured.err)

    return invoke


@pytest.fixture
def run_async(
    capsys: pytest.CaptureFixture[str],
) -> Callable[..., Awaitable[Run]]:
    async def invoke(*argv: str) -> Run:
        code = await asyncio.to_thread(_invoke, argv)
        captured = capsys.readouterr()
        return Run(code, captured.out, captured.err)

    return invoke


def corpus_text(fixture: str) -> str:
    return (CORPUS / fixture / "spec.md").read_text(encoding="utf-8")


def plant_text(tmp_path: Path, text: str, *, name: str = VALID) -> Path:
    spec_dir = tmp_path / name
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "spec.md").write_text(text, encoding="utf-8")
    return spec_dir


def plant(tmp_path: Path, fixture: str, *, name: str | None = None) -> Path:
    return plant_text(tmp_path, corpus_text(fixture), name=name or fixture)


@pytest.fixture
def epic_dir(tmp_path: Path) -> Path:
    return plant(tmp_path, VALID)


PLAN_TEXT = """# Implementation Plan: Short Links

## Summary

One `links` table is the system of record; the redirect path reads it and never
caches it.
"""

TASKS_TEXT = """# Tasks: Short Links

## Phase 1: Setup

- [ ] T001 Create the package skeleton

## Phase 2: User Story 1 - Save a link (Priority: P1)

- [ ] T002 [US1] Write tests/test_save.py FIRST
- [ ] T003 [US1] Implement links/save.py until T002 passes

## Phase 3: User Story 2 - Follow a short link (Priority: P1)

- [ ] T004 [US2] Write tests/test_follow.py FIRST
- [ ] T005 [US2] Implement the redirect path until T004 passes

## Phase 4: User Story 3 - List my links (Priority: P2)

- [ ] T006 [US3] Write tests/test_list.py FIRST
- [ ] T007 [US3] Implement the listing until T006 passes
"""


def criteria_for(spec_ref: str) -> CriteriaSet:
    story_key = spec_ref.rsplit(":", 1)[-1]
    key = FR_FOR[story_key]
    return CriteriaSet(
        feature=EPIC_ID,
        spec_ref=spec_ref,
        requirements=[
            Requirement(
                key=key,
                kind=RequirementKind.FUNCTIONAL,
                title=None,
                priority=None,
                body=f"The system MUST satisfy {key}.",
                scenarios=[],
            )
        ],
        source_path=f"specs/{EPIC_ID}/spec.md",
        source_sha256="0" * 64,
        snapshotted_at="2026-08-05T09:00:00Z",
    )


def gate_pass() -> GateResult:
    return GateResult(
        name="test",
        command="uv run pytest -q",
        status=GateStatus.PASS,
        exit_code=0,
        duration_s=8.0,
        output_tail="12 passed in 8.01s",
    )


def wrote_something() -> OutputCheck:
    return OutputCheck(
        write_scope=WriteScope.WORKTREE.value,
        has_diff=True,
        expected_artifacts=[],
        artifacts_present=None,
        passed=True,
    )


class ScriptedEpic:
    """Same scripted world as test_epic_cli.py, narrowed to the happy path."""

    def __init__(
        self,
        *,
        spec_text: str,
        pause_at: str | None = None,
        live_snapshot: UsageSnapshot | None = None,
        fail_resolve: bool = False,
        question_at: tuple[str, int] | None = None,
    ) -> None:
        self._spec_text = spec_text
        self._pause_at = pause_at
        self.live_snapshot = live_snapshot
        self._fail_resolve = fail_resolve
        self._question_at = question_at

        self.graphs: list[WorkGraph] = []
        self.prompt_source_requests: list[LoadPromptSourcesInput] = []
        self.attempts: list[AttemptContext] = []
        self.salvages: list[SalvageWorktreeInput] = []

        self.paused = asyncio.Event()
        self._released = asyncio.Event()

    async def wait_for_pause(self, timeout: float = 30.0) -> None:
        await asyncio.wait_for(self.paused.wait(), timeout=timeout)

    def release(self) -> None:
        self._released.set()

    @property
    def dispatched(self) -> list[str]:
        return [context.node_id for context in self.attempts]

    def activities(self) -> list[Any]:
        script = self

        @activity.defn(name="validate_target_repo")
        async def validate_target_repo(
            request: ValidateTargetRepoInput,
        ) -> TargetRepoProfile:
            return TargetRepoProfile(
                repo=request.target_repo,
                default_branch="main",
                visibility="PUBLIC",
                queue_enabled=True,
                required_checks=("test",),
                declared_gates=("test",),
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
            script.graphs.append(graph)
            if script._fail_resolve:
                raise ApplicationError(
                    "persona 'implementer' is not in the registry",
                    type=GRAPH_INVALID,
                    non_retryable=True,
                )
            validate_workgraph(graph, PERSONAS)
            persona = PERSONAS["implementer"]
            return [
                ResolvedNode(
                    node=node,
                    model_alias=MODEL_ALIAS,
                    models=[MODEL_ALIAS],
                    write_scope=persona.write_scope.value,
                    timeout_s=node.timeout_override_s or TIMEOUT_S,
                )
                for node in graph.nodes
            ]

        @activity.defn(name="resolve_persona")
        async def resolve_persona(request: ResolvePersonaInput) -> ResolvedPersona:
            return ResolvedPersona(
                persona=request.persona,
                model_alias=JUDGE_ALIAS,
                models=[JUDGE_ALIAS],
            )

        @activity.defn(name="load_prompt_sources")
        async def load_prompt_sources(request: LoadPromptSourcesInput) -> PromptSources:
            script.prompt_source_requests.append(request)
            return PromptSources(
                spec_text=script._spec_text,
                plan_text=PLAN_TEXT,
                tasks_text=TASKS_TEXT,
                standards=None,
            )

        @activity.defn(name="snapshot_criteria")
        async def snapshot_criteria(request: SnapshotCriteriaInput) -> CriteriaSet:
            return criteria_for(request.spec_ref)

        @activity.defn(name="prepare_worktree")
        async def prepare_worktree(request: PrepareWorktreeInput) -> PreparedWorktree:
            return PreparedWorktree(
                path=f"/srv/factory/.factory/worktrees/{request.epic_id}/{request.node_id}",
                branch=branch_name(request.epic_id, request.node_id),
                base_ref="9" * 40,
            )

        @activity.defn(name="issue_attempt_key")
        async def issue_attempt_key(request: IssueKeyInput) -> KeyLease:
            return KeyLease(
                key=f"sk-{request.node_id}-{request.attempt}",
                key_alias=(
                    f"{request.epic_id}:{request.node_id}"
                    f":{request.attempt}:{request.persona}"
                ),
                node_id=request.node_id,
                epic_id=request.epic_id,
                attempt=request.attempt,
                persona=request.persona,
                spec_ref=request.spec_ref,
                issued_at="2026-08-05T09:30:00Z",
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
                transcript_path=(
                    f"/srv/factory/.factory/transcripts/{context.epic_id}/"
                    f"{context.node_id}/attempt-{context.attempt}"
                ),
            )

        @activity.defn(name="poll_usage")
        async def poll_usage(lease: KeyLease) -> UsageSnapshot:
            return UsageSnapshot(spend_usd=0.01, captured_at="2026-08-05T09:31:00Z")

        @activity.defn(name="run_gates")
        async def run_gates(request: RunGatesInput) -> list[GateResult]:
            return [gate_pass()]

        @activity.defn(name="check_output")
        async def check_output(request: CheckOutputInput) -> OutputCheck:
            return wrote_something()

        @activity.defn(name="record_verification")
        async def record_verification(
            request: RecordVerificationInput,
        ) -> RecordedVerification:
            return RecordedVerification(row_id=1, criteria_drift=False)

        @activity.defn(name="teardown_attempt")
        async def teardown_attempt(request: TeardownInput) -> UsageRecord:
            lease = request.lease
            return UsageRecord(
                epic_id=lease.epic_id,
                node_id=lease.node_id,
                attempt=lease.attempt,
                persona=lease.persona,
                spec_ref=lease.spec_ref,
                key_alias=lease.key_alias,
                prompt_tokens=900,
                completion_tokens=120,
                cache_read_tokens=None,
                cache_write_tokens=None,
                request_count=1,
                spend_usd=0.003,
                final_usage_confirmed=True,
                termination=request.termination,
                issued_at=lease.issued_at,
                torn_down_at="2026-08-05T09:32:00Z",
            )

        @activity.defn(name="salvage_worktree")
        async def salvage_worktree(request: SalvageWorktreeInput) -> str:
            script.salvages.append(request)
            return f"{len(script.salvages):040x}"

        @activity.defn(name="remove_worktree")
        async def remove_worktree(request: RemoveWorktreeInput) -> None:
            return None

        @activity.defn(name="prepare_landing_pr")
        async def prepare_landing_pr(
            request: PrepareLandingPrInput,
        ) -> PrepareLandingPrResult:
            return PrepareLandingPrResult(
                body_file=f"/srv/factory/.factory/landing/{request.epic_id}/"
                f"{request.node_id}/attempt-{request.attempt}.md",
                title=f"{request.story_title}: {request.feature}",
            )

        @activity.defn(name="open_landing_pr")
        async def open_landing_pr(request: OpenLandingPrInput) -> OpenLandingPrResult:
            return OpenLandingPrResult(
                number=int(hashlib.sha1(request.branch.encode()).hexdigest()[:8], 16)
                % 1000
                + 1,
                url=f"https://github.com/ergane/{request.target_repo}/pull/1",
            )

        @activity.defn(name="enqueue_landing")
        async def enqueue_landing(request: EnqueueLandingInput) -> EnqueueResult:
            return EnqueueResult(rejected=False, reason="")

        @activity.defn(name="poll_landing")
        async def poll_landing(request: PollLandingInput) -> PrSnapshot:
            return merged_snapshot()

        @activity.defn(name="disable_auto_merge")
        async def disable_auto_merge(request: DisableAutoMergeInput) -> None:
            return None

        @activity.defn(name="detect_operator_question_activity")
        async def detect_operator_question_activity(
            request: DetectQuestionInput,
        ) -> QuestionMarker:
            if (
                script._question_at
                and request.node_id == script._question_at[0]
                and request.attempt == script._question_at[1]
            ):
                return QuestionMarker(
                    is_question=True,
                    text="Is this the question you expected?",
                )
            return QuestionMarker(is_question=False)

        return [
            validate_target_repo,
            resolve_graph,
            resolve_persona,
            load_prompt_sources,
            snapshot_criteria,
            prepare_worktree,
            issue_attempt_key,
            run_agent_attempt,
            poll_usage,
            run_gates,
            check_output,
            record_verification,
            teardown_attempt,
            salvage_worktree,
            remove_worktree,
            prepare_landing_pr,
            open_landing_pr,
            enqueue_landing,
            poll_landing,
            disable_auto_merge,
            detect_operator_question_activity,
        ]


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    environment = await WorkflowEnvironment.start_time_skipping()
    try:
        yield environment
    finally:
        await environment.shutdown()


@pytest.fixture
async def temporal_env(
    env: WorkflowEnvironment, monkeypatch: pytest.MonkeyPatch
) -> WorkflowEnvironment:
    monkeypatch.setenv(TEMPORAL_ADDRESS_ENV, env.client.service_client.config.target_host)
    monkeypatch.setenv(TEMPORAL_NAMESPACE_ENV, env.client.namespace)
    monkeypatch.setenv(PROXY_URL_ENV, PROXY_URL)
    monkeypatch.setenv("LITELLM_MASTER_KEY", FAKE_MASTER_KEY)

    fake = FakeLiteLLM(base_url=PROXY_URL, master_key=FAKE_MASTER_KEY)
    import factory.cli.nouns as nouns_package
    import factory.cli.nouns.build as build_module
    import factory.workgraph.cli as legacy_cli_module

    registry = build_module._preflight_registry()
    fake.served_models = {
        alias
        for name in ("implementer", JUDGE_PERSONA)
        for alias in (registry[name].model, registry[name].fallback)
        if alias
    }

    def preflight_client() -> LiteLLMClient:
        return LiteLLMClient(
            base_url=fake.base_url,
            master_key=fake.master_key,
            transport=fake.transport,
        )

    monkeypatch.setattr(nouns_package, "_open_preflight_client", preflight_client)
    monkeypatch.setattr(legacy_cli_module, "_open_preflight_client", preflight_client)
    env.fake = fake  # type: ignore[attr-defined]
    return env


def worker_for(env: WorkflowEnvironment, script: ScriptedEpic) -> Worker:
    return Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[EpicWorkflow],
        activities=script.activities(),
    )


async def settle_epic(env: WorkflowEnvironment) -> Any:
    handle = env.client.get_workflow_handle(WORKFLOW_ID)
    await env.sleep(timedelta(seconds=LANDING_POLL_INTERVAL_S + 1))
    return await handle.result()


@pytest.fixture
def workgraph_json(epic_dir: Path) -> Path:
    """Compile the fixture graph directly; this test is about `build`, not `derive`."""
    spec_text = (epic_dir / "spec.md").read_text(encoding="utf-8")
    graph = derive_workgraph(
        spec_text,
        epic_id=EPIC_ID,
        feature=EPIC_ID,
        specs_root="specs",
        target_repo=TARGET_REPO,
    )
    graph_path = epic_dir / "workgraph.json"
    graph_path.write_text(
        json.dumps(
            {
                "epic_id": graph.epic_id,
                "feature": graph.feature,
                "specs_root": graph.specs_root,
                "target_repo": graph.target_repo,
                "nodes": [
                    {
                        "id": node.id,
                        "story_key": node.story_key,
                        "persona": node.persona,
                        "spec_ref": node.spec_ref,
                        "requirement_keys": list(node.requirement_keys),
                        "depends_on": list(node.depends_on),
                        "depends_on_merged": list(node.depends_on_merged),
                        "timeout_override_s": node.timeout_override_s,
                    }
                    for node in graph.nodes
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return graph_path


# --- T016: start/status port -------------------------------------------------


def test_start_refuses_zero_node_graph_before_temporal(
    run: Callable[..., Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A zero-node graph is refused before any server contact, through `ergane build`."""
    monkeypatch.setenv(TEMPORAL_ADDRESS_ENV, DEAD_ADDRESS)
    monkeypatch.setenv(PROXY_URL_ENV, PROXY_URL)

    empty_graph = {
        "epic_id": "empty-feature",
        "feature": "empty-feature",
        "specs_root": "specs",
        "target_repo": TARGET_REPO,
        "nodes": [],
    }
    graph_path = tmp_path / "workgraph.json"
    graph_path.write_text(json.dumps(empty_graph), encoding="utf-8")

    result = run("build", "start", str(graph_path))

    assert result.code == 1
    assert "zero" in result.stderr.lower() or "empty" in result.stderr.lower()
    assert "node" in result.stderr.lower()


def test_start_without_a_proxy_url_refuses_rather_than_dispatching(
    run: Callable[..., Run],
    temporal_env: WorkflowEnvironment,
    workgraph_json: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The proxy url is required before anything starts."""
    monkeypatch.delenv(PROXY_URL_ENV, raising=False)

    result = run("build", "start", str(workgraph_json))

    assert result.code == 1
    assert PROXY_URL_ENV in result.stderr


def test_start_refuses_hand_edited_graph_with_structural_errors(
    run: Callable[..., Run],
    temporal_env: WorkflowEnvironment,
    workgraph_json: Path,
) -> None:
    """A graph edited after `derive` is re-validated before dispatch."""
    graph = json.loads(workgraph_json.read_text(encoding="utf-8"))
    graph["nodes"][1]["depends_on"] = ["us7"]
    workgraph_json.write_text(json.dumps(graph), encoding="utf-8")

    result = run("build", "start", str(workgraph_json))

    assert result.code == 1
    assert "us2" in result.stderr and "us7" in result.stderr
    assert result.stdout == ""


async def test_start_against_an_unreachable_temporal_is_exit_3(
    run_async: Callable[..., Awaitable[Run]],
    workgraph_json: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-010 / trap 3: a dead proxy/server is exit 3, not 2, under the new contract."""
    monkeypatch.setenv(TEMPORAL_ADDRESS_ENV, DEAD_ADDRESS)
    monkeypatch.setenv(TEMPORAL_NAMESPACE_ENV, DEFAULT_TEMPORAL_NAMESPACE)
    monkeypatch.setenv(PROXY_URL_ENV, PROXY_URL)

    result = await run_async("build", "start", str(workgraph_json))

    assert result.code == 3
    assert DEAD_ADDRESS in result.stderr


async def test_start_prints_the_workflow_id_and_starts_that_epic(
    run_async: Callable[..., Awaitable[Run]],
    temporal_env: WorkflowEnvironment,
    workgraph_json: Path,
) -> None:
    result = await run_async("build", "start", str(workgraph_json))

    assert result.code == 0
    assert result.stdout.strip() == WORKFLOW_ID

    described = await temporal_env.client.get_workflow_handle(WORKFLOW_ID).describe()
    assert described.workflow_type == "EpicWorkflow"
    assert described.task_queue == TASK_QUEUE


async def test_status_json_is_the_query_result_verbatim(
    run_async: Callable[..., Awaitable[Run]],
    temporal_env: WorkflowEnvironment,
    epic_dir: Path,
    workgraph_json: Path,
) -> None:
    """`ergane build status <epic> --json` dumps the query document unchanged."""
    script = ScriptedEpic(spec_text=(epic_dir / "spec.md").read_text(encoding="utf-8"))

    async with worker_for(temporal_env, script):
        await run_async("build", "start", str(workgraph_json))
        await settle_epic(temporal_env)
        result = await run_async("build", "status", EPIC_ID, "--json")

    assert result.code == 0
    assert result.json == {
        "epic_state": "COMPLETED",
        "nodes": {
            node_id: {
                "attempt": 1,
                "branch": branch_name(EPIC_ID, node_id),
                "state": "MERGED",
                "verified": True,
                "landing_state": "MERGED",
                "pr_number": int(
                    hashlib.sha1(branch_name(EPIC_ID, node_id).encode()).hexdigest()[:8], 16
                )
                % 1000
                + 1,
            }
            for node_id in NODE_IDS
        },
        "execution_status": "COMPLETED",
    }


async def test_status_reads_live_spend_off_the_running_attempt(
    run_async: Callable[..., Awaitable[Run]],
    temporal_env: WorkflowEnvironment,
    epic_dir: Path,
    workgraph_json: Path,
) -> None:
    """Live spend is a sibling key, never merged into a node."""
    snapshot = UsageSnapshot(spend_usd=6.25, captured_at="2026-08-05T09:31:00Z")
    script = ScriptedEpic(
        spec_text=(epic_dir / "spec.md").read_text(encoding="utf-8"),
        pause_at="us2",
        live_snapshot=snapshot,
    )

    async with worker_for(temporal_env, script):
        await run_async("build", "start", str(workgraph_json))
        await script.wait_for_pause()

        mid_json = await run_async("build", "status", EPIC_ID, "--json")
        mid_human = await run_async("build", "status", EPIC_ID)

        script.release()
        await settle_epic(temporal_env)

    assert mid_json.code == 0
    assert mid_json.json["nodes"]["us2"]["state"] == "RUNNING"
    assert mid_json.json["live_spend"]["us2"] == {
        "spend_usd": 6.25,
        "captured_at": "2026-08-05T09:31:00Z",
    }
    assert "6.25" in mid_human.stdout
