"""US2 of 023-composable-verification: the ladder is pinned at dispatch.

Two dispatch paths must read the operator clone's committed manifest at the
moment of dispatch and pin the loop into `EpicInput`:

- `ergane build start` (CLI) reads `graph.target_repo` and refuses a malformed
  manifest at preflight.
- `RoadmapWorkflow._dispatch` reads the target repo per child through a new
  activity so manifest edits reach the next scheduled epic.

The test suite also proves the tamper boundary: a node worktree that rewrites
its own `ladder:` changes nothing, and the configured escalation deadline is what
both the workflow timer and the stored row advertise.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager, closing
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, NamedTuple

import pytest
from temporalio import activity
from temporalio.client import Client
from temporalio.service import RPCError, RPCStatusCode
from temporalio.testing import ActivityEnvironment, WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker
from temporalio.worker._interceptor import (
    Interceptor,
    WorkflowInboundInterceptor,
    WorkflowOutboundInterceptor,
)

from factory.activities.agent_activities import (
    LoadPromptSourcesInput,
    PrepareWorktreeInput,
    PreparedWorktree,
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
from factory.activities.notify_activities import (
    ExpiredEscalation,
    ExpireEscalationInput,
    SendEscalationInput,
    SentEscalation,
    SettledEscalation,
    SettleEscalationInput,
    send_escalation,
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
from factory.cli.nouns import build as build_module
import factory.cli.nouns as nouns_package
from factory.config import Persona, WriteScope
from factory.mergequeue.models import Finding, PrSnapshot, TargetRepoProfile
from factory.usage.litellm_client import PROXY_URL_ENV, LiteLLMClient
from factory.usage.models import KeyLease, Termination, UsageRecord, UsageSnapshot
from factory.verify import store
from factory.verify.factory_yaml import (
    FactoryConfigError,
    MANIFEST_NAME,
    load_factory_config,
    load_loop_config,
    resolve_manifest_path,
)
from factory.verify.models import (
    AttemptRecord,
    CriteriaSet,
    EscalationChoice,
    GateResult,
    GateStatus,
    JudgeOutcome,
    JudgeScenarioFinding,
    JudgeVerdict,
    NextAction,
    OutputCheck,
    QuestionRecord,
    Requirement,
    RequirementKind,
    VerificationConfig,
)
from factory.workgraph.derive import derive_workgraph
from factory.workgraph.models import (
    AdapterResult,
    AttemptContext,
    EpicState,
    NodeState,
    ResolvedNode,
    ResolvedPersona,
    WorkGraph,
    validate_workgraph,
)
from factory.workgraph.workflow import JUDGE_PERSONA, TASK_QUEUE, EpicInput, EpicWorkflow
from factory.workgraph.worktree import branch_name
from factory.escalation.workflow import EscalationWorkflow
from factory.escalation.question import QuestionWorkflow
from factory.roadmap.models import SpecState
from tests.conftest import FAKE_MASTER_KEY, FakeLiteLLM
from tests.roadmap_script import (
    _SCRIPT,
    ScriptedEpicWorkflow,
    landed_status,
)
from tests.test_roadmap_scheduler import HARNESS_REVISION, _BootRevisionInterceptor
from tests.test_interpreter import (
    EPIC_ID as TEST_EPIC_ID,
    TARGET_REPO as TEST_TARGET_REPO,
    PROXY_URL as TEST_PROXY_URL,
    WORKFLOW_ID as TEST_WORKFLOW_ID,
    MODEL_ALIAS,
    JUDGE_ALIAS,
    TIMEOUT_S,
    PLAN_TEXT,
    TASKS_TEXT,
    ScriptedWorld,
    criteria_for,
    failing,
    gate_fail,
    gate_pass,
    judge_retry,
    make_graph,
    make_node,
    wrote_something,
)

EPIC_ID = "023-us2-demo"
WORKFLOW_ID = f"epic-{EPIC_ID}"
TARGET_REPO = "/srv/factory/targets/023-us2"

ROADMAP_TARGET_REPO = "/srv/factory/targets/roadmap-023-us2"

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
    ),
    JUDGE_PERSONA: Persona(
        name=JUDGE_PERSONA,
        agent="claude-code",
        model=JUDGE_ALIAS,
        fallback=None,
        skills=(),
        write_scope=WriteScope.READ,
        needs_worktree=False,
        timeout_s=3600,
    ),
}


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str


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


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    environment = await WorkflowEnvironment.start_time_skipping()
    try:
        yield environment
    finally:
        await environment.shutdown()


def _graph_fixture(tmp_path: Path, target_repo: Path) -> Path:
    """Write a compiled workgraph naming `target_repo`."""
    spec_dir = tmp_path / EPIC_ID
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "spec.md").write_text(
        f"""# Feature Specification: {EPIC_ID}

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Build it (Priority: P1)

As the operator, I build the thing, so that it works.

**Acceptance Scenarios**:

1. **Given** a thing, **When** it is built, **Then** it works.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST build the thing.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001]
```
""",
        encoding="utf-8",
    )
    (spec_dir / "plan.md").write_text(PLAN_TEXT, encoding="utf-8")
    (spec_dir / "tasks.md").write_text(TASKS_TEXT, encoding="utf-8")

    graph = derive_workgraph(
        (spec_dir / "spec.md").read_text(encoding="utf-8"),
        epic_id=EPIC_ID,
        feature=EPIC_ID,
        specs_root=str(tmp_path),
        target_repo=str(target_repo),
    )
    graph_path = tmp_path / "workgraph.json"
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


def _v1_manifest(target_repo: Path) -> None:
    (target_repo / MANIFEST_NAME).write_text(
        "version: 1\nruntime: bwrap\ngates:\n  test: uv run pytest -q\n",
        encoding="utf-8",
    )


def _v2_manifest(target_repo: Path, *, max_attempts: int = 2) -> None:
    (target_repo / MANIFEST_NAME).write_text(
        f"""version: 2
runtime: bwrap
gates:
  test: uv run pytest -q
ladder:
  max_attempts: {max_attempts}
  escalation_timeout_s: 7200
""",
        encoding="utf-8",
    )


def _malformed_manifest(target_repo: Path) -> None:
    (target_repo / MANIFEST_NAME).write_text(
        "version: 2\nruntime: bwrap\ngates:\n  test: uv run pytest -q\nladder:\n  max_attempts: true\n",
        encoding="utf-8",
    )


@dataclass
class RecordingClient:
    """A Temporal client stand-in that records the EpicInput passed to start_workflow.

    156-US1 gave `build start` one read before dispatch — the worker's
    advertisement, queried off the id it is about to take. When no real client
    is attached there is no epic to read, which on a server is `NOT_FOUND`: the
    shape the refusal's own read degrades on, so this fake answers it the same
    way instead of failing the dispatch these tests measure.
    """

    real_client: Client | None = None
    inputs: list[EpicInput] = field(default_factory=list)
    workflow_ids: list[str] = field(default_factory=list)

    def get_workflow_handle(self, workflow_id: str):
        if self.real_client is not None:
            return self.real_client.get_workflow_handle(workflow_id)
        raise RPCError("workflow not found", RPCStatusCode.NOT_FOUND, b"")

    async def start_workflow(
        self,
        workflow,
        arg: Any,
        *,
        id: str,
        task_queue: str,
    ) -> Any:
        self.inputs.append(arg)
        self.workflow_ids.append(id)
        return None

    async def describe(self):
        raise AssertionError("not used")


@pytest.fixture
def fake_lite_llm_and_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> FakeLiteLLM:
    fake = FakeLiteLLM(base_url=TEST_PROXY_URL, master_key=FAKE_MASTER_KEY)
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
    return fake


# --- T007: CLI dispatch ------------------------------------------------------


async def test_cli_dispatch_v2_manifest_pins_declared_caps_and_order(
    run_async: Callable[..., Awaitable[Run]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_lite_llm_and_preflight: FakeLiteLLM,
) -> None:
    """T007 [US2-S1/S2/S5]: v2 caps and order ride `EpicInput`."""
    target_repo = tmp_path / "target-repo"
    target_repo.mkdir(parents=True)
    _v2_manifest(target_repo, max_attempts=2)
    graph_path = _graph_fixture(tmp_path, target_repo)

    monkeypatch.setenv(PROXY_URL_ENV, TEST_PROXY_URL)
    monkeypatch.setenv("TEMPORAL_ADDRESS", "127.0.0.1:1")
    monkeypatch.setenv("TEMPORAL_NAMESPACE", "test")
    client = RecordingClient()

    async def fake_open_client() -> RecordingClient:
        return client

    monkeypatch.setattr(nouns_package, "_open_client", fake_open_client)

    result = await run_async("build", "start", str(graph_path))
    assert result.code == 0, result.stderr
    assert result.stdout.strip() == WORKFLOW_ID
    assert len(client.inputs) == 1
    epic_input = client.inputs[0]
    assert isinstance(epic_input, EpicInput)
    assert epic_input.config.max_attempts == 2
    assert epic_input.config.escalation_timeout_s == 7200
    assert epic_input.verify_order == ("gates", "diff_check", "judge")


async def test_cli_dispatch_v1_manifest_uses_todays_defaults(
    run_async: Callable[..., Awaitable[Run]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_lite_llm_and_preflight: FakeLiteLLM,
) -> None:
    """T007 [US2-S2]: absent ladder means today's defaults exactly."""
    target_repo = tmp_path / "target-repo"
    target_repo.mkdir(parents=True)
    _v1_manifest(target_repo)
    graph_path = _graph_fixture(tmp_path, target_repo)

    monkeypatch.setenv(PROXY_URL_ENV, TEST_PROXY_URL)
    monkeypatch.setenv("TEMPORAL_ADDRESS", "127.0.0.1:1")
    monkeypatch.setenv("TEMPORAL_NAMESPACE", "test")
    client = RecordingClient()

    async def fake_open_client() -> RecordingClient:
        return client

    monkeypatch.setattr(nouns_package, "_open_client", fake_open_client)

    result = await run_async("build", "start", str(graph_path))
    assert result.code == 0, result.stderr
    assert len(client.inputs) == 1
    epic_input = client.inputs[0]
    assert isinstance(epic_input, EpicInput)
    assert epic_input.config == VerificationConfig()
    assert epic_input.verify_order == ("gates", "diff_check", "judge")


async def test_cli_dispatch_malformed_manifest_refused_at_preflight(
    run_async: Callable[..., Awaitable[Run]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_lite_llm_and_preflight: FakeLiteLLM,
) -> None:
    """T007 [US2-S5]: malformed manifest refuses dispatch, rule named, exit non-zero."""
    target_repo = tmp_path / "target-repo"
    target_repo.mkdir(parents=True)
    _malformed_manifest(target_repo)
    graph_path = _graph_fixture(tmp_path, target_repo)

    monkeypatch.setenv(PROXY_URL_ENV, TEST_PROXY_URL)
    monkeypatch.setenv("TEMPORAL_ADDRESS", "127.0.0.1:1")
    monkeypatch.setenv("TEMPORAL_NAMESPACE", "test")
    client = RecordingClient()

    async def fake_open_client() -> RecordingClient:
        return client

    monkeypatch.setattr(nouns_package, "_open_client", fake_open_client)

    result = await run_async("build", "start", str(graph_path))
    assert result.code != 0, result.stderr
    assert "ladder_max_attempts_type" in result.stderr
    assert "max_attempts" in result.stderr
    assert not client.inputs


# --- T008: roadmap dispatch --------------------------------------------------


@dataclass
class ChildStartRecord:
    """One `start_child_workflow` the roadmap issued, captured for T008."""

    workflow: str
    id: str
    args: tuple
    parent_close_policy: str
    id_reuse_policy: str


class _RecordingInterceptor(Interceptor):
    """Record every child workflow start so the EpicInput can be asserted."""

    def __init__(self, records: list[ChildStartRecord]) -> None:
        self._records = records

    def workflow_interceptor_class(self, _input):
        records = self._records

        class _Inbound(WorkflowInboundInterceptor):
            def init(self, outbound):
                self.next.init(_Outbound(outbound, records))

        return _Inbound


class _Outbound(WorkflowOutboundInterceptor):
    def __init__(self, next_outbound, records: list[ChildStartRecord]) -> None:
        super().__init__(next_outbound)
        self._records = records

    async def start_child_workflow(self, input):
        self._records.append(
            ChildStartRecord(
                workflow=str(input.workflow),
                id=input.id,
                args=tuple(input.args),
                parent_close_policy=input.parent_close_policy.name,
                id_reuse_policy=input.id_reuse_policy.name,
            )
        )
        return await self.next.start_child_workflow(input)


def _write_roadmap_spec(spec_dir: Path, *, state: str = "ready") -> None:
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "spec.md").write_text(
        f"""---
state: {state}
---
# Feature Specification: {spec_dir.name}

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Build it (Priority: P1)

As the operator, I build the thing, so that it works.

**Acceptance Scenarios**:

1. **Given** a thing, **When** it is built, **Then** it works.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST build the thing.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001]
```
""",
        encoding="utf-8",
    )
    (spec_dir / "plan.md").write_text(PLAN_TEXT, encoding="utf-8")
    (spec_dir / "tasks.md").write_text(TASKS_TEXT, encoding="utf-8")


def _build_roadmap_corpus(root: Path, specs: dict[str, str]) -> Path:
    specs_root = root / "specs"
    for name, state in specs.items():
        _write_roadmap_spec(specs_root / name, state=state)
    return specs_root


def _passing_profile(repo: str) -> TargetRepoProfile:
    return TargetRepoProfile(
        repo=repo,
        default_branch="main",
        visibility="public",
        queue_enabled=True,
        required_checks=("test",),
        declared_gates=("test",),
        findings=(Finding(check="repo-exists", passed=True, detail="ok"),),
        passed=True,
    )


@asynccontextmanager
async def _run_roadmap(
    env: WorkflowEnvironment,
    tmp_path: Path,
    specs: dict[str, str],
    target_repo: Path,
    *,
    child_starts: list[ChildStartRecord] | None = None,
    on_complete: Callable[[str], None] | None = None,
    script_statuses: dict[str, Any] | None = None,
) -> AsyncIterator[Any]:
    """Run `RoadmapWorkflow` against a fresh corpus and a scripted child."""
    from factory.activities import roadmap_activities
    from factory.activities.notify_activities import (
        record_roadmap_failure,
        reset_roadmap_failures,
        send_roadmap_notice,
    )
    from factory.roadmap.workflow import (
        RoadmapInput,
        RoadmapWorkflow,
        read_corpus_activity,
        read_spec_text_activity,
        roadmap_workflow_id,
    )
    from factory.activities.roadmap_activities import CloneResult, DeriveInput

    specs_root = _build_roadmap_corpus(tmp_path, specs)

    def _derive_runner(request: DeriveInput) -> WorkGraph:
        return derive_workgraph(
            request.spec_text,
            epic_id=request.epic_id,
            feature=request.feature,
            specs_root=request.specs_root,
            target_repo=request.target_repo,
        )

    import factory.workgraph.preflight as preflight_mod

    saved: dict[str, Any] = {}
    try:
        saved["_clone_runner"] = roadmap_activities._clone_runner
        saved["_derive_runner"] = roadmap_activities._derive_runner
        saved["_preflight_registry"] = roadmap_activities._preflight_registry
        saved["_preflight_client"] = roadmap_activities._preflight_client
        saved["_onboard"] = roadmap_activities._onboard
        saved["_open_epics_provider"] = roadmap_activities._open_epics_provider
        saved["_read_loop_config_runner"] = getattr(
            roadmap_activities, "_read_loop_config_runner", None
        )
        saved["_tree_revision_runner"] = getattr(
            roadmap_activities, "_tree_revision_runner", None
        )
        saved["roadmap_check_aliases"] = getattr(
            roadmap_activities, "check_aliases", None
        )
        saved["preflight_check_aliases"] = preflight_mod.check_aliases

        roadmap_activities._clone_runner = lambda _: CloneResult(
            path=str(target_repo), default_branch="main", head_ref="abc123"
        )
        roadmap_activities._derive_runner = _derive_runner
        # 156-US2: the tree seam answers the harness revision, so the skew
        # check is aligned here and the dispatch pins below still fire.
        roadmap_activities._tree_revision_runner = lambda _: HARNESS_REVISION
        roadmap_activities._preflight_registry = lambda: {}
        roadmap_activities._preflight_client = lambda proxy_url: None

        async def _fake_check_aliases(graph, registry, client):
            return []

        roadmap_activities.check_aliases = _fake_check_aliases
        preflight_mod.check_aliases = _fake_check_aliases
        async def _fake_onboard(target_repo: str) -> TargetRepoProfile:
            return _passing_profile(str(target_repo))

        roadmap_activities._onboard = _fake_onboard

        async def _empty_open_epics() -> set[str]:
            return set()

        roadmap_activities._open_epics_provider = _empty_open_epics
        roadmap_activities._read_loop_config_runner = None

        _SCRIPT.statuses = dict(script_statuses or {})
        _SCRIPT.on_dispatch = None
        _SCRIPT.on_complete = on_complete
        _SCRIPT.hold = set()

        activities = [
            roadmap_activities.clone_target,
            roadmap_activities.derive_spec,
            roadmap_activities.drift_for_spec,
            roadmap_activities.preflight_spec,
            roadmap_activities.onboard_target,
            roadmap_activities.count_open_epics,
            roadmap_activities.read_loop_config,
            # 156-US2: the tree-revision read, served so the skew check's
            # activity call lands on the (aligned) scripted seam.
            roadmap_activities.tree_revision_activity,
            read_corpus_activity,
            read_spec_text_activity,
            record_roadmap_failure,
            reset_roadmap_failures,
            send_roadmap_notice,
        ]
        interceptors = (
            [_BootRevisionInterceptor(HARNESS_REVISION)]
            + (
                [_RecordingInterceptor(child_starts)]
                if child_starts is not None
                else []
            )
        )
        async with Worker(
            env.client,
            task_queue="workgraph",
            workflows=[RoadmapWorkflow, ScriptedEpicWorkflow],
            activities=activities,
            interceptors=interceptors,
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            handle = await env.client.start_workflow(
                RoadmapWorkflow.run,
                RoadmapInput(
                    specs_root=str(specs_root),
                    target_repo=str(target_repo),
                    proxy_url=TEST_PROXY_URL,
                    max_concurrent_epics=1,
                ),
                id=roadmap_workflow_id(str(specs_root)),
                task_queue="workgraph",
            )
            yield handle
    finally:
        for key, value in saved.items():
            if key == "_clone_runner":
                roadmap_activities._clone_runner = value
            elif key == "_derive_runner":
                roadmap_activities._derive_runner = value
            elif key == "_preflight_registry":
                roadmap_activities._preflight_registry = value
            elif key == "_preflight_client":
                roadmap_activities._preflight_client = value
            elif key == "_onboard":
                roadmap_activities._onboard = value
            elif key == "_open_epics_provider":
                roadmap_activities._open_epics_provider = value
            elif key == "_read_loop_config_runner":
                roadmap_activities._read_loop_config_runner = value
            elif key == "_tree_revision_runner":
                roadmap_activities._tree_revision_runner = value
            elif key == "roadmap_check_aliases":
                if value is not None:
                    roadmap_activities.check_aliases = value
                else:
                    try:
                        delattr(roadmap_activities, "check_aliases")
                    except AttributeError:
                        pass
            elif key == "preflight_check_aliases":
                preflight_mod.check_aliases = value
        _SCRIPT.statuses = {}
        _SCRIPT.on_complete = None
        _SCRIPT.hold = set()


async def test_roadmap_dispatch_reads_config_per_child(
    env: WorkflowEnvironment,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T008 [US2-S3/S6]: `_dispatch` sources child config from `read_loop_config`."""
    target_repo = tmp_path / "target-repo"
    target_repo.mkdir(parents=True)
    _v1_manifest(target_repo)

    child_starts: list[ChildStartRecord] = []

    def on_complete(epic_id: str) -> None:
        if epic_id == "001-first":
            # Between the two dispatches, the operator updates the manifest to v2.
            _v2_manifest(target_repo, max_attempts=4)

    async with _run_roadmap(
        env,
        tmp_path,
        {"001-first": "ready", "002-second": "ready"},
        target_repo,
        child_starts=child_starts,
        on_complete=on_complete,
        script_statuses={"001-first": landed_status(), "002-second": landed_status()},
    ) as handle:
        await handle.result()

    assert len(child_starts) == 2
    [first, second] = child_starts
    first_input = first.args[0]
    second_input = second.args[0]
    assert isinstance(first_input, EpicInput)
    assert isinstance(second_input, EpicInput)
    # First child saw the committed v1 manifest: today's defaults exactly.
    assert first_input.config == VerificationConfig()
    assert first_input.verify_order == ("gates", "diff_check", "judge")
    # Second child saw the updated v2 manifest.
    assert second_input.config.max_attempts == 4
    assert second_input.config.escalation_timeout_s == 7200
    assert second_input.verify_order == ("gates", "diff_check", "judge")


async def test_roadmap_dispatch_malformed_manifest_parks_spec(
    env: WorkflowEnvironment,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T008 [US2-S6]: a malformed manifest at dispatch parks the spec."""
    target_repo = tmp_path / "target-repo"
    target_repo.mkdir(parents=True)
    _malformed_manifest(target_repo)

    child_starts: list[ChildStartRecord] = []

    async with _run_roadmap(
        env,
        tmp_path,
        {"001-alpha": "ready"},
        target_repo,
        child_starts=child_starts,
    ) as handle:
        status = await handle.result()

    assert not child_starts, "malformed manifest must not start a child"
    parked = [p for p in status.parked if p.spec_dir == "001-alpha"]
    assert len(parked) == 1
    finding = parked[0]
    assert finding.check == "manifest"
    assert "ladder_max_attempts_type" in finding.detail
    assert "max_attempts" in finding.detail


# --- T009: tamper and parity -------------------------------------------------


async def test_worktree_manifest_ladder_rewrite_has_no_effect(
    env: WorkflowEnvironment,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T009 [US2-S4]: pinned budget survives a worktree ladder rewrite."""
    from factory.verify.ladder import next_action
    from factory.verify.models import OverallVerdict

    target_repo = tmp_path / "target-repo"
    target_repo.mkdir(parents=True)
    _v2_manifest(target_repo, max_attempts=2)

    # Pin dispatch-time config from the committed manifest. The third value is
    # 092's diff refusal threshold, pinned by the same read and not this test's
    # subject.
    config, verify_order, _ = load_loop_config(target_repo)
    assert config.max_attempts == 2

    graph = make_graph([make_node("us1", "US1")])

    # Four failing attempts scripted so that a budget of 99 would not escalate.
    script = ScriptedWorld(
        {"us1": [failing(1), failing(2), failing(3), failing(4)]},
        client=env.client,
        delivered=False,
    )

    # Replace the fake prepare_worktree with one that creates a real directory and
    # writes a manifest that claims max_attempts=99. The loop must ignore it.
    original_activities = script.activities()

    @activity.defn(name="prepare_worktree")
    async def prepare_worktree_with_rewrite(request: PrepareWorktreeInput) -> PreparedWorktree:
        script._log("prepare_worktree", request.node_id)
        script.prepare_requests.append(request)
        path = tmp_path / "worktrees" / request.epic_id / request.node_id
        path.mkdir(parents=True, exist_ok=True)
        # The node rewrites its own manifest to ask for 8 attempts.
        _v2_manifest(path, max_attempts=8)
        return PreparedWorktree(
            path=str(path),
            branch=branch_name(request.epic_id, request.node_id),
            base_ref="9" * 40,
        )

    activities = [
        a
        for a in original_activities
        if activity._Definition.must_from_callable(a).name != "prepare_worktree"
    ] + [prepare_worktree_with_rewrite]

    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[EpicWorkflow, EscalationWorkflow, QuestionWorkflow],
        activities=activities,
        workflow_runner=UnsandboxedWorkflowRunner(),
    ):
        handle = await env.client.start_workflow(
            EpicWorkflow.run,
            EpicInput(
                graph=graph,
                proxy_url=TEST_PROXY_URL,
                config=config,
                verify_order=verify_order,
            ),
            id=WORKFLOW_ID,
            task_queue=TASK_QUEUE,
        )
        status = await handle.result()

    # The worktree manifest really was rewritten; if read, it would grant 8.
    first_request = script.prepare_requests[0]
    worktree_path = tmp_path / "worktrees" / first_request.epic_id / first_request.node_id
    manifest_path, _ = resolve_manifest_path(worktree_path)
    assert load_factory_config(manifest_path).ladder.max_attempts == 8

    # The pinned budget produced at most three gate attempts before escalation
    # (two ordinary + one debugger cycle). It is far below the 8 the worktree tried
    # to claim, which is the whole point of the tamper boundary.
    gate_calls = [name for _, name in script.node_calls if name == "run_gates"]
    assert 2 <= len(gate_calls) <= 3
    assert len(script.escalation_requests) == 1
    assert status.nodes["us1"].state == NodeState.KILLED

    # Pure-ladder cross-check: two failures + one debugger cycle against
    # max_attempts=2 and debugger_cycles=1 is ESCALATE.
    history = [
        AttemptRecord(
            attempt=1,
            persona="implementer",
            verdict=OverallVerdict.FAIL,
            judge_outcome=None,
        ),
        AttemptRecord(
            attempt=2,
            persona="implementer",
            verdict=OverallVerdict.FAIL,
            judge_outcome=None,
        ),
        AttemptRecord(
            attempt=3,
            persona="debugger",
            verdict=OverallVerdict.FAIL,
            judge_outcome=None,
        ),
    ]
    assert next_action(history, config) == NextAction.ESCALATE


async def test_escalation_timer_and_row_agree_at_non_default_deadline(
    env: WorkflowEnvironment,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T009 [US2-S5]: timer half — workflow waits 7200s under scripted send."""
    from factory.escalation.workflow import (
        OUTCOME_EXPIRED,
        EscalationRequest,
        EscalationWorkflow,
    )

    recorded_timeouts: list[int] = []

    @activity.defn(name="send_escalation")
    async def fake_send_escalation(request: SendEscalationInput) -> SentEscalation:
        recorded_timeouts.append(request.timeout_s)
        return SentEscalation(
            escalation_id=request.escalation_id or "abc123",
            delivered=True,
            expires_at="2026-08-17T12:00:00Z",
        )

    @activity.defn(name="expire_escalation")
    async def fake_expire_escalation(request: ExpireEscalationInput) -> ExpiredEscalation:
        return ExpiredEscalation(final_state="EXPIRED")

    @activity.defn(name="settle_escalation")
    async def fake_settle_escalation(request: SettleEscalationInput) -> SettledEscalation:
        return SettledEscalation(final_state=None, settled_here=False)

    async with Worker(
        env.client,
        task_queue="workgraph",
        workflows=[EscalationWorkflow],
        activities=[fake_send_escalation, fake_expire_escalation, fake_settle_escalation],
        workflow_runner=UnsandboxedWorkflowRunner(),
    ):
        handle = await env.client.start_workflow(
            EscalationWorkflow.run,
            EscalationRequest(
                epic_id=EPIC_ID,
                node_id="us1",
                history_summary="x",
                timeout_s=7200,
            ),
            id="test-escalation-7200",
            task_queue="workgraph",
        )
        outcome = await handle.result()

    assert recorded_timeouts == [7200]
    assert outcome.outcome == OUTCOME_EXPIRED


def test_send_escalation_row_expires_at_configured_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T009 [US2-S5]: row half — real activity, 7200s derived from record."""
    from factory.activities.verify_activities import ERGANE_VERIFICATION_DB_PATH_ENV

    db_path = tmp_path / ".factory" / "verification.db"
    db_path.parent.mkdir(parents=True)
    monkeypatch.setenv(ERGANE_VERIFICATION_DB_PATH_ENV, str(db_path))
    monkeypatch.delenv("FACTORY_VERIFICATION_DB_PATH", raising=False)

    env = ActivityEnvironment()
    request = SendEscalationInput(
        workflow_id="w",
        epic_id=EPIC_ID,
        node_id="us1",
        history_summary="x",
        timeout_s=7200,
    )
    result = asyncio.run(env.run(send_escalation, request))

    with closing(store.connect(db_path)) as conn:
        row = store.get_escalation(conn, result.escalation_id)

    assert row is not None
    sent = datetime.fromisoformat(row.sent_at.replace("Z", "+00:00"))
    expires = datetime.fromisoformat(row.expires_at.replace("Z", "+00:00"))
    assert expires == sent + timedelta(seconds=7200)
