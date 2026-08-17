"""Failing tests for US2 of 023-composable-verification: the manifest reaches the loop.

The three task blocks (T007-T009) live in one file because they share the same
fixtures: a tiny target-repo layout with an `ergane.yaml`, and a way to read the
manifest at dispatch time.  The implementation (T010) does not exist yet, so every
test here is expected to fail until that diff lands.
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path, PurePosixPath
from typing import Any, AsyncIterator, Callable

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from factory.activities.agent_activities import (
    AdapterResult,
    AttemptContext,
    LoadPromptSourcesInput,
    PrepareWorktreeInput,
    PromptSources,
    RemoveWorktreeInput,
    ResolvePersonaInput,
    SalvageWorktreeInput,
    read_worktree_diff,
    resolve_graph,
    resolve_persona,
)
from factory.activities.merge_activities import (
    CompareTreesInput,
    DisableAutoMergeInput,
    EnqueueLandingInput,
    FetchCheckFailureInput,
    OpenLandingPrInput,
    PollLandingInput,
    PrepareLandingPrInput,
    SyncLandingBranchInput,
    ValidateTargetRepoInput,
    compare_trees,
    disable_auto_merge,
    enqueue_landing,
    fetch_check_failure,
    open_landing_pr,
    poll_landing,
    prepare_landing_pr,
    sync_landing_branch,
    validate_target_repo,
)
from factory.activities.notify_activities import (
    ExpiredEscalation,
    ExpireEscalationInput,
    FindFerriedQuestion,
    FindFerriedQuestionInput,
    SendEscalationInput,
    SentEscalation,
    SettledEscalation,
    SettleEscalationInput,
    expire_escalation,
    find_ferried_question,
    send_escalation,
    settle_escalation,
)
from factory.activities.usage_activities import (
    IssueKeyInput,
    TeardownInput,
    issue_attempt_key,
    poll_usage,
    teardown_attempt,
)
from factory.activities.verify_activities import (
    CheckOutputInput,
    DetectQuestionInput,
    RecordVerificationInput,
    RecordedVerification,
    RunGatesInput,
    RunJudgeInput,
    SnapshotCriteriaInput,
    check_output,
    detect_operator_question_activity,
    record_verification,
    run_gates,
    run_judge,
    snapshot_criteria,
)
from factory.cli.nouns.build import load_workgraph
from factory.config import Persona, WriteScope
from factory.escalation.question import QuestionWorkflow
from factory.escalation.workflow import EscalationWorkflow
from factory.mergequeue.models import Finding, PrSnapshot, TargetRepoProfile
from factory.notify.service import QUESTION_SIGNAL_NAME, SIGNAL_NAME
from factory.usage.models import KeyLease, Termination, UsageRecord, UsageSnapshot
from factory.verify.factory_yaml import FactoryConfigError
from factory.verify.ladder import DEBUGGER_PERSONA
from temporalio.exceptions import ApplicationError
from factory.verify.models import (
    CriteriaSet,
    EscalationChoice,
    GateResult,
    GateStatus,
    JudgeOutcome,
    JudgeScenarioFinding,
    JudgeVerdict,
    NextAction,
    OutputCheck,
    OverallVerdict,
    Requirement,
    RequirementKind,
    Scenario,
    VerificationConfig,
    VerificationResult,
    compose_result,
    judge_required,
)
from factory.verify.store import EXPIRED
from factory.verify.question import QuestionMarker
from factory.workgraph.derive import derive_workgraph
from factory.workgraph.models import (
    AdapterResult,
    AttemptContext,
    EpicState,
    NodeState,
    ResolvedNode,
    ResolvedPersona,
    WorkGraph,
    WorkNode,
    validate_workgraph,
)
from factory.workgraph.prompt import AttemptEvidence
from factory.workgraph.worktree import PreparedWorktree, branch_name
from factory.workgraph.workflow import EpicInput, EpicWorkflow, JUDGE_PERSONA, TASK_QUEUE
from tests.conftest import FAKE_MASTER_KEY
from tests.roadmap_script import ScriptedEpicWorkflow, _SCRIPT, failed_status, landed_status
from tests.test_ergane_build import MODEL_ALIAS, PROXY_URL, TARGET_REPO, TIMEOUT_S
from tests.test_interpreter import gate_fail, gate_pass, wrote_something
from tests.test_roadmap_scheduler import ChildStartRecord, _RecordingInterceptor


#: The v2 manifest used for S1/S4/S5.  It declares non-default caps and an order
#: that differs from the default so the test can distinguish "declared" from
#: "happens to match default".
V2_MANIFEST = """\
version: 2
runtime: bwrap
gates:
  test: uv run pytest -q
ladder:
  max_attempts: 2
  max_judge_retries: 1
  debugger_cycles: 1
  escalation_timeout_s: 7200
verify:
  - gates
  - diff_check
  - judge
"""

#: A malformed manifest used for S6: a ladder value above its ceiling.
BAD_MANIFEST = """\
version: 2
runtime: bwrap
gates:
  test: uv run pytest -q
ladder:
  max_attempts: 99
"""

#: The v1 manifest used for S2: same as Ergane's own root manifest.
V1_MANIFEST = """\
version: 1
runtime: bwrap
gates:
  test: uv run pytest -q
standards: .specify/memory/constitution.md
landing_branch: ergane-buildout
"""

EPIC_ID = "023-composable"
FEATURE = "023-composable"
WORKFLOW_ID = f"epic-{EPIC_ID}"

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
        model="judge-alias",
        fallback=None,
        skills=(),
        write_scope=WriteScope.READ,
        needs_worktree=False,
        timeout_s=3600,
    ),
    DEBUGGER_PERSONA: Persona(
        name=DEBUGGER_PERSONA,
        agent="claude-code",
        model="debugger-alias",
        fallback=None,
        skills=(),
        write_scope=WriteScope.WORKTREE,
        needs_worktree=True,
        timeout_s=7200,
    ),
}


def _make_graph(target_repo: str, specs_root: str = "specs") -> WorkGraph:
    return derive_workgraph(
        _SPEC_TEXT,
        epic_id=EPIC_ID,
        feature=FEATURE,
        specs_root=specs_root,
        target_repo=target_repo,
    )


_SPEC_TEXT = """# Feature Specification: Composable

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Build it (Priority: P1)

One user story with one scenario.

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
"""


# --- fixtures ----------------------------------------------------------------


@pytest.fixture
def target_repo(tmp_path: Path) -> Path:
    """A minimal target repo root.  Tests write the manifest they need into it."""
    repo = tmp_path / "target-repo"
    repo.mkdir()
    return repo


def write_manifest(target_repo: Path, text: str) -> None:
    (target_repo / "ergane.yaml").write_text(text, encoding="utf-8")


def graph_json(target_repo: Path, tmp_path: Path, *, specs_root: str | None = None) -> Path:
    specs_root = specs_root if specs_root is not None else str(tmp_path / "specs")
    graph = _make_graph(str(target_repo), specs_root=specs_root)
    path = tmp_path / "workgraph.json"
    path.write_text(
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
    return path


# --- T007: CLI dispatch cases ------------------------------------------------


class CapturingClient:
    """A fake Temporal client that records the workflow input passed to start_workflow."""

    def __init__(self) -> None:
        self.started: list[tuple[str, Any, dict[str, Any]]] = []

    async def start_workflow(
        self,
        workflow: Any,
        arg: Any,
        *,
        id: str,
        task_queue: str,
    ) -> Any:
        self.started.append((id, arg, {"task_queue": task_queue}))
        return None

    def get_workflow_handle(self, workflow_id: str) -> Any:
        return self


async def _run_start_epic_with_fake_client(
    graph: WorkGraph,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> CapturingClient:
    """Call `_start_epic` and return the capturing client it used."""
    from factory.cli import nouns as nouns_package
    from factory.cli.nouns import build as build_module
    from factory.workgraph.prompt import build_attempt_prompt

    fake = CapturingClient()
    monkeypatch.setattr(nouns_package, "_open_client", lambda: asyncio.sleep(0, result=fake))
    monkeypatch.setenv("LITELLM_PROXY_URL", PROXY_URL)
    monkeypatch.setenv("LITELLM_MASTER_KEY", FAKE_MASTER_KEY)

    # Avoid any alias preflight call that would need a proxy by stubbing the registry.
    def fake_preflight_registry() -> dict[str, Persona]:
        return {}

    monkeypatch.setattr(build_module, "_preflight_registry", fake_preflight_registry)

    # Patch alias check to return empty findings.
    async def fake_check_aliases(graph: WorkGraph, registry: Any, client: Any) -> list:
        return []

    import factory.workgraph.preflight as preflight_mod

    monkeypatch.setattr(build_module, "check_aliases", fake_check_aliases)
    monkeypatch.setattr(preflight_mod, "check_aliases", fake_check_aliases)

    # Plant the spec trio where prompt assembly expects it.
    feature_dir = Path(graph.specs_root) / graph.feature
    feature_dir.mkdir(parents=True, exist_ok=True)
    (feature_dir / "spec.md").write_text(_SPEC_TEXT, encoding="utf-8")
    (feature_dir / "plan.md").write_text("# Plan\n\nOne thing.\n", encoding="utf-8")
    (feature_dir / "tasks.md").write_text(
        "# Tasks\n\n## Phase 1: User Story 1 - Build it (Priority: P1)\n\n- [ ] T001 Write it\n",
        encoding="utf-8",
    )

    await build_module._start_epic(graph, PROXY_URL)
    return fake


def test_cli_preflight_refuses_malformed_manifest_with_rule_named(
    target_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T007 / S6: a malformed manifest refuses dispatch at CLI preflight."""
    write_manifest(target_repo, BAD_MANIFEST)
    graph_path = graph_json(target_repo, tmp_path)
    graph = load_workgraph(graph_path)

    with pytest.raises(Exception) as excinfo:
        asyncio.run(_run_start_epic_with_fake_client(graph, monkeypatch, tmp_path))

    message = str(excinfo.value)
    assert "ladder_max_attempts_max" in message or "max_attempts" in message


def test_cli_dispatch_pins_v2_config_and_order(
    target_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T007 / S1: a v2 manifest's ladder and order reach `EpicInput`."""
    write_manifest(target_repo, V2_MANIFEST)
    graph_path = graph_json(target_repo, tmp_path)
    graph = load_workgraph(graph_path)

    fake = asyncio.run(_run_start_epic_with_fake_client(graph, monkeypatch, tmp_path))

    assert len(fake.started) == 1, fake.started
    _, arg, _ = fake.started[0]
    assert isinstance(arg, EpicInput)
    assert arg.config.max_attempts == 2
    assert arg.config.max_judge_retries == 1
    assert arg.config.escalation_timeout_s == 7200
    assert arg.verify_order == ("gates", "diff_check", "judge")


def test_cli_dispatch_defaults_for_v1_manifest(
    target_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T007 / S2: a v1 manifest produces today's defaults exactly."""
    write_manifest(target_repo, V1_MANIFEST)
    graph_path = graph_json(target_repo, tmp_path)
    graph = load_workgraph(graph_path)

    fake = asyncio.run(_run_start_epic_with_fake_client(graph, monkeypatch, tmp_path))

    assert len(fake.started) == 1
    _, arg, _ = fake.started[0]
    assert isinstance(arg, EpicInput)
    assert arg.config == VerificationConfig()
    assert arg.verify_order == ("gates", "diff_check", "judge")


# --- T008: roadmap dispatch cases --------------------------------------------


@dataclass
class LoopConfigCapture:
    """What a fake `read_loop_config` activity was asked and answered."""

    target_repo: str | None = None
    returned: tuple[VerificationConfig, tuple[str, ...]] | None = None


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    environment = await WorkflowEnvironment.start_time_skipping()
    try:
        yield environment
    finally:
        await environment.shutdown()


def _passing_profile() -> TargetRepoProfile:
    return TargetRepoProfile(
        repo=TARGET_REPO,
        default_branch="main",
        visibility="public",
        queue_enabled=True,
        required_checks=("test",),
        declared_gates=("test",),
        findings=(Finding("repo-exists", True, "ok"),),
        passed=True,
    )


def _scripted_roadmap_activities(
    env: WorkflowEnvironment,
    config_capture: LoopConfigCapture,
) -> list[Any]:
    """Return the activities the roadmap needs, with a fake read_loop_config."""
    from factory.activities import roadmap_activities
    from factory.activities.notify_activities import (
        record_roadmap_failure,
        reset_roadmap_failures,
        send_roadmap_notice,
    )

    @activity.defn(name="clone_target")
    async def clone_target(request: dict):
        from factory.activities.roadmap_activities import CloneResult
        return CloneResult(path=request["target_repo"], default_branch="main", head_ref="abc123")

    @activity.defn(name="derive_spec")
    async def derive_spec(request: dict):
        return derive_workgraph(
            request["spec_text"],
            epic_id=request["epic_id"],
            feature=request["feature"],
            specs_root=request["specs_root"],
            target_repo=request["target_repo"],
        )

    @activity.defn(name="drift_for_spec")
    async def drift_for_spec(request: dict):
        return False

    @activity.defn(name="preflight_spec")
    async def preflight_spec(request: dict):
        return []

    @activity.defn(name="onboard_target")
    async def onboard_target(request: dict):
        return _passing_profile()

    @activity.defn(name="count_open_epics")
    async def count_open_epics(request: dict):
        from factory.activities.roadmap_activities import CountOpenResult
        return CountOpenResult(open_ids=())

    @activity.defn(name="read_corpus_activity")
    async def read_corpus_activity(request: dict):
        from factory.roadmap.models import Roadmap, SpecEntry, SpecState

        return Roadmap(
            specs_root=request["specs_root"],
            entries=[
                SpecEntry(
                    spec_dir="001-alpha",
                    state=SpecState.READY,
                    depends_on_landed=[],
                    source="",
                )
            ],
        )

    @activity.defn(name="read_spec_text_activity")
    async def read_spec_text_activity(request: dict):
        return (Path(request["specs_root"]) / request["spec_dir"] / "spec.md").read_text(encoding="utf-8")

    @activity.defn(name="read_loop_config")
    async def read_loop_config(request):
        config_capture.target_repo = request.get("target_repo") if isinstance(request, dict) else getattr(request, "target_repo", None)
        if config_capture.returned is None:
            raise RuntimeError("read_loop_config called but no return scripted")
        return config_capture.returned

    return [
        clone_target,
        derive_spec,
        drift_for_spec,
        preflight_spec,
        onboard_target,
        count_open_epics,
        read_corpus_activity,
        read_spec_text_activity,
        record_roadmap_failure,
        reset_roadmap_failures,
        send_roadmap_notice,
        read_loop_config,
    ]


def _make_spec_trio(specs_root: Path) -> None:
    spec_dir = specs_root / "001-alpha"
    spec_dir.mkdir(parents=True)
    (spec_dir / "spec.md").write_text(_SPEC_TEXT, encoding="utf-8")
    (spec_dir / "plan.md").write_text("# Plan\n\nOne thing.\n", encoding="utf-8")
    (spec_dir / "tasks.md").write_text(
        "# Tasks\n\n## Phase 1: User Story 1 - Build it (Priority: P1)\n\n- [ ] T001 Write it\n",
        encoding="utf-8",
    )


async def test_roadmap_dispatch_reads_loop_config_per_dispatch(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """T008 / S3: `_dispatch` sources child config from a per-dispatch activity."""
    from factory.roadmap.workflow import RoadmapInput, RoadmapWorkflow, roadmap_workflow_id

    specs_root = tmp_path / "specs"
    _make_spec_trio(specs_root)

    capture = LoopConfigCapture()
    capture.returned = (
        VerificationConfig(max_attempts=2, escalation_timeout_s=7200),
        ("gates", "diff_check", "judge"),
    )

    starts: list[ChildStartRecord] = []
    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[RoadmapWorkflow, ScriptedEpicWorkflow],
        activities=_scripted_roadmap_activities(env, capture),
        interceptors=[_RecordingInterceptor(starts)],
        workflow_runner=UnsandboxedWorkflowRunner(),
    ):
        handle = await env.client.start_workflow(
            RoadmapWorkflow.run,
            RoadmapInput(
                specs_root=str(specs_root),
                target_repo=TARGET_REPO,
                proxy_url=PROXY_URL,
            ),
            id=roadmap_workflow_id(str(specs_root)),
            task_queue=TASK_QUEUE,
        )
        await handle.result()

    assert len(starts) == 1
    assert starts[0].workflow == "EpicWorkflow"
    child_input: EpicInput = starts[0].args[0]
    assert child_input.config.max_attempts == 2
    assert child_input.verify_order == ("gates", "diff_check", "judge")
    assert capture.target_repo == TARGET_REPO


async def test_roadmap_parse_failure_parks_spec_and_run_continues(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """T008 / S6: a manifest parse failure parks the spec and the run continues."""
    from factory.roadmap.workflow import RoadmapInput, RoadmapStatus, RoadmapWorkflow, roadmap_workflow_id

    specs_root = tmp_path / "specs"
    _make_spec_trio(specs_root)

    capture = LoopConfigCapture()

    class FakeReadLoopConfig:
        async def __call__(self, request):
            raise ApplicationError(
                "ergane.yaml: [ladder_max_attempts_max] max_attempts too high",
                type="ladder_max_attempts_max",
                non_retryable=True,
            )

    fake = FakeReadLoopConfig()

    activities = _scripted_roadmap_activities(env, capture)
    # Replace the scripted read_loop_config with one that fails the first time.
    for i, fn in enumerate(activities):
        if getattr(fn, "__name__", None) == "read_loop_config":
            activities[i] = activity.defn(name="read_loop_config")(fake)
            break

    starts: list[ChildStartRecord] = []
    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[RoadmapWorkflow, ScriptedEpicWorkflow],
        activities=activities,
        interceptors=[_RecordingInterceptor(starts)],
        workflow_runner=UnsandboxedWorkflowRunner(),
    ):
        handle = await env.client.start_workflow(
            RoadmapWorkflow.run,
            RoadmapInput(
                specs_root=str(specs_root),
                target_repo=TARGET_REPO,
                proxy_url=PROXY_URL,
            ),
            id=roadmap_workflow_id(str(specs_root)),
            task_queue=TASK_QUEUE,
        )
        status = await handle.result()

    assert isinstance(status, RoadmapStatus)
    assert len(status.parked) == 1
    assert status.parked[0].spec_dir == "001-alpha"
    assert "ladder_max_attempts_max" in status.parked[0].check
    assert len(starts) == 0


# --- T009: tamper and parity cases -------------------------------------------


def _node_criteria(node_id: str = "us1", story_key: str = "US1") -> CriteriaSet:
    key = "FR-001"
    return CriteriaSet(
        feature=FEATURE,
        spec_ref=f"{FEATURE}:{story_key}",
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
        source_path=f"specs/{FEATURE}/spec.md",
        source_sha256="0" * 64,
        snapshotted_at="2026-08-05T09:00:00Z",
    )


class TamperWorld:
    """A scripted world that lets a node rewrite its worktree manifest between attempts."""

    def __init__(
        self,
        target_repo: Path,
        *,
        pinned_config: VerificationConfig,
        tamper_node: str = "us1",
    ) -> None:
        self.target_repo = target_repo
        self.pinned_config = pinned_config
        self.tamper_node = tamper_node
        self.calls: list[str] = []
        self.gate_requests: list[RunGatesInput] = []
        self.escalation_requests: list[SendEscalationInput] = []
        self.expirations: list[str] = []
        self.records: list[VerificationResult] = []

    def activities(self) -> list[Any]:
        script = self

        @activity.defn(name="resolve_graph")
        async def resolve_graph(graph: WorkGraph) -> list[ResolvedNode]:
            validate_workgraph(graph, PERSONAS)
            return [
                ResolvedNode(
                    node=node,
                    model_alias=MODEL_ALIAS,
                    models=[MODEL_ALIAS],
                    write_scope=PERSONAS["implementer"].write_scope.value,
                    timeout_s=node.timeout_override_s or TIMEOUT_S,
                )
                for node in graph.nodes
            ]

        @activity.defn(name="resolve_persona")
        async def resolve_persona(request: ResolvePersonaInput) -> ResolvedPersona:
            return ResolvedPersona(
                persona=request.persona,
                model_alias="judge-alias",
                models=["judge-alias"],
            )

        @activity.defn(name="load_prompt_sources")
        async def load_prompt_sources(request: LoadPromptSourcesInput) -> PromptSources:
            return PromptSources(
                spec_text=_SPEC_TEXT,
                plan_text="# Plan\n\nOne thing.\n",
                tasks_text="""# Tasks\n\n## Phase 1: User Story 1 - Build it (Priority: P1)\n\n- [ ] T001 Write it\n""",
                standards=None,
            )

        @activity.defn(name="snapshot_criteria")
        async def snapshot_criteria(request: SnapshotCriteriaInput) -> CriteriaSet:
            return _node_criteria(request.spec_ref.rsplit(":", 1)[-1])

        @activity.defn(name="detect_operator_question_activity")
        async def detect_operator_question_activity(request: DetectQuestionInput) -> QuestionMarker:
            return QuestionMarker(is_question=False)

        @activity.defn(name="prepare_worktree")
        async def prepare_worktree(request: PrepareWorktreeInput) -> PreparedWorktree:
            return PreparedWorktree(
                path=f"{script.target_repo}/.worktrees/{request.epic_id}/{request.node_id}",
                branch=branch_name(request.epic_id, request.node_id),
                base_ref="9" * 40,
            )

        @activity.defn(name="run_agent_attempt")
        async def run_agent_attempt(context: AttemptContext) -> AdapterResult:
            if context.node_id == script.tamper_node and context.attempt == 2:
                # The agent rewrites the worktree manifest to ask for 99 attempts.
                worktree = f"{script.target_repo}/.worktrees/{context.epic_id}/{context.node_id}"
                Path(worktree).mkdir(parents=True, exist_ok=True)
                Path(worktree, "ergane.yaml").write_text(
                    """\
version: 2
runtime: bwrap
gates:
  test: uv run pytest -q
ladder:
  max_attempts: 99
""",
                    encoding="utf-8",
                )
            return AdapterResult(
                termination=Termination.COMPLETED,
                transcript_path=f"/srv/factory/transcripts/{context.epic_id}/{context.node_id}/{context.attempt}",
            )

        @activity.defn(name="run_gates")
        async def run_gates(request: RunGatesInput) -> list[GateResult]:
            script.gate_requests.append(request)
            node = PurePosixPath(request.worktree_path).name
            if node == script.tamper_node:
                return [gate_fail(1)]
            return [gate_pass()]

        @activity.defn(name="check_output")
        async def check_output(request: CheckOutputInput) -> OutputCheck:
            return wrote_something()

        @activity.defn(name="record_verification")
        async def record_verification(request: RecordVerificationInput) -> RecordedVerification:
            script.records.append(request.result)
            return RecordedVerification(row_id=1, criteria_drift=False)

        @activity.defn(name="send_escalation")
        async def send_escalation(request: SendEscalationInput) -> SentEscalation:
            script.escalation_requests.append(request)
            return SentEscalation(
                escalation_id="esc-001",
                delivered=False,
                expires_at="2026-08-05T10:30:00Z",
            )

        @activity.defn(name="expire_escalation")
        async def expire_escalation(request: ExpireEscalationInput) -> ExpiredEscalation:
            script.expirations.append(request.escalation_id)
            return ExpiredEscalation(final_state=EXPIRED)

        @activity.defn(name="salvage_worktree")
        async def salvage_worktree(request: SalvageWorktreeInput) -> str:
            return "0" * 40

        @activity.defn(name="remove_worktree")
        async def remove_worktree(request: RemoveWorktreeInput) -> None:
            return None

        @activity.defn(name="issue_attempt_key")
        async def issue_attempt_key(request: IssueKeyInput) -> KeyLease:
            return KeyLease(
                key=f"sk-{request.node_id}-{request.attempt}",
                key_alias=f"{request.epic_id}:{request.node_id}:{request.attempt}:{request.persona}",
                node_id=request.node_id,
                epic_id=request.epic_id,
                attempt=request.attempt,
                persona=request.persona,
                spec_ref=request.spec_ref,
                issued_at="2026-08-05T09:30:00Z",
            )

        @activity.defn(name="teardown_attempt")
        async def teardown_attempt(request: TeardownInput) -> UsageRecord:
            return UsageRecord(
                epic_id=request.lease.epic_id,
                node_id=request.lease.node_id,
                attempt=request.lease.attempt,
                persona=request.lease.persona,
                spec_ref=request.lease.spec_ref,
                key_alias=request.lease.key_alias,
                prompt_tokens=0,
                completion_tokens=0,
                cache_read_tokens=None,
                cache_write_tokens=None,
                request_count=1,
                spend_usd=0.0,
                final_usage_confirmed=True,
                termination=request.termination,
                issued_at=request.lease.issued_at,
                torn_down_at="2026-08-05T09:32:00Z",
            )

        @activity.defn(name="validate_target_repo")
        async def validate_target_repo(request: ValidateTargetRepoInput) -> TargetRepoProfile:
            return TargetRepoProfile(
                repo=request.target_repo,
                default_branch="main",
                visibility="public",
                queue_enabled=True,
                required_checks=("test",),
                declared_gates=("test",),
                findings=(Finding("repo-exists", True, "ok"),),
                passed=True,
            )

        return [
            resolve_graph,
            resolve_persona,
            load_prompt_sources,
            snapshot_criteria,
            prepare_worktree,
            run_agent_attempt,
            run_gates,
            check_output,
            record_verification,
            send_escalation,
            expire_escalation,
            detect_operator_question_activity,
            salvage_worktree,
            remove_worktree,
            issue_attempt_key,
            teardown_attempt,
            validate_target_repo,
        ]


async def test_worktree_manifest_tamper_does_not_affect_ladder(
    env: WorkflowEnvironment, target_repo: Path
) -> None:
    """T009 / S4: a worktree ladder rewrite does not grant extra attempts."""
    write_manifest(target_repo, V2_MANIFEST)
    graph = _make_graph(str(target_repo))

    pinned = VerificationConfig(max_attempts=2, escalation_timeout_s=7200)
    script = TamperWorld(target_repo, pinned_config=pinned)

    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[EpicWorkflow, EscalationWorkflow],
        activities=script.activities(),
        workflow_runner=UnsandboxedWorkflowRunner(),
    ):
        handle = await env.client.start_workflow(
            EpicWorkflow.run,
            EpicInput(
                graph=graph,
                proxy_url=PROXY_URL,
                config=pinned,
                verify_order=("gates", "diff_check", "judge"),
            ),
            id=WORKFLOW_ID,
            task_queue=TASK_QUEUE,
        )
        status = await handle.result()

    # The node escalates after the pinned budget, not the tampered 99.
    assert status.nodes["us1"].state == NodeState.KILLED
    assert len(script.escalation_requests) == 1


async def test_escalation_timeout_parity_at_7200(
    env: WorkflowEnvironment, target_repo: Path
) -> None:
    """T009 / S5: the timer and the row both advertise 7200 seconds."""
    from factory.escalation.workflow import EscalationWorkflow

    write_manifest(target_repo, V2_MANIFEST)
    graph = _make_graph(str(target_repo))

    pinned = VerificationConfig(max_attempts=2, escalation_timeout_s=7200)
    script = TamperWorld(target_repo, pinned_config=pinned)

    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[EpicWorkflow, EscalationWorkflow],
        activities=script.activities(),
        workflow_runner=UnsandboxedWorkflowRunner(),
    ):
        handle = await env.client.start_workflow(
            EpicWorkflow.run,
            EpicInput(
                graph=graph,
                proxy_url=PROXY_URL,
                config=pinned,
                verify_order=("gates", "diff_check", "judge"),
            ),
            id=WORKFLOW_ID,
            task_queue=TASK_QUEUE,
        )
        await handle.result()

    assert len(script.escalation_requests) == 1
    escalation = script.escalation_requests[0]
    assert escalation.timeout_s == 7200
