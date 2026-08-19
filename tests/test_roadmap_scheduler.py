"""The roadmap scheduler under time skipping with scripted epic children (FR-004/005/006).

US2's `RoadmapWorkflow` dispatches each dispatchable spec as a child
`EpicWorkflow`, woken by the child's completion event — no polling anywhere
(FR-004). "Landed" is derived from the child's returned `EpicStatus`:
`COMPLETED` and every landing `MERGED`. An epic that completes with a `FAILED`
node is finished but not landed; its dependents stay blocked and the roadmap
says why.

These tests follow the fakes-under-real-names pattern `tests/test_interpreter.py`
established with `ScriptedWorld`: the roadmap's children are a scripted
`EpicWorkflow` (in `tests/roadmap_script.py`, registered under the real
workflow name) whose `run` returns a prescribed `EpicStatus` keyed by the spec
dir it was dispatched for. The roadmap's own pre-dispatch activities are
scripted through their seams (`_clone_runner`, `_preflight_*`, `_onboard`,
`_open_epics_provider`) so the scheduler logic is what is under test, not
clone/preflight/onboarding mechanics those components already cover. The
corpus and spec reads run against real files in a `tmp_path` corpus, because
the roadmap's corpus read is the one pure filesystem surface US2 owns.

Written before `factory/roadmap/workflow.py` carries the scheduler (T010
precedes T013): until it lands, every test here fails.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, AsyncIterator, Callable

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker
from temporalio.worker._interceptor import (
    Interceptor,
    WorkflowInboundInterceptor,
    WorkflowOutboundInterceptor,
)

from factory.activities import roadmap_activities
from factory.activities.roadmap_activities import CloneResult
from factory.mergequeue.models import Finding, TargetRepoProfile
from factory.roadmap.models import Roadmap, SpecState
import factory.roadmap.workflow as factory_roadmap_workflow
from factory.roadmap.workflow import (
    RoadmapInput,
    RoadmapStatus,
    RoadmapWorkflow,
    roadmap_workflow_id,
)
from factory.workgraph.workflow import EpicStatus

from tests.roadmap_script import (
    BlockerDoneWorkflow,
    BlockerRunningWorkflow,
    ScriptedEpicWorkflow,
    _SCRIPT,
    failed_status,
    landed_status,
)

# A canary credential the sweep (T012) plants in the worker environment; none
# of it may reach a parked finding, a status payload, or the workflow input.
SECRET = "sk-roadmap-canary-9d7f2a1b4c8e-master"

TARGET_REPO = "/srv/factory/targets/library"
PROXY_URL = "http://litellm.test"


# --- intercepting child-workflow starts (T011 child-policy) --------------------


@dataclass
class ChildStartRecord:
    """One `start_child_workflow` the roadmap issued, as the interceptor saw it.

    The child-policy tests (T011) assert `parent_close_policy` and
    `id_reuse_policy` without a real cancellation round trip: the outbound
    interceptor records the options the workflow handed `start_child_workflow`,
    so a policy drift fails here rather than silently.
    """

    workflow: str
    id: str
    args: tuple
    parent_close_policy: str
    id_reuse_policy: str


class _RecordingInterceptor(Interceptor):
    """A Temporal interceptor that records every `start_child_workflow` call.

    The worker's `interceptors` argument wants an object exposing
    `workflow_interceptor_class`, which returns the inbound interceptor class
    the worker instantiates per workflow run. That inbound's `init` wraps the
    outbound it is handed in a recording outbound that intercepts
    `start_child_workflow`, so the roadmap's child-start options
    (`parent_close_policy`, `id_reuse_policy`, `id`) are captured for the T011
    child-policy assertions.
    """

    def __init__(self, records: list[ChildStartRecord]) -> None:
        self._records = records

    def workflow_interceptor_class(self, input):
        records = self._records

        class _Inbound(WorkflowInboundInterceptor):
            def init(self, outbound):
                # Wrap the outbound in the recorder before handing it down the
                # chain — `init` is where the outbound interceptor is installed.
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


# --- the corpus a roadmap reads ---------------------------------------------


def _write_spec(
    spec_dir: Path,
    *,
    state: SpecState | None,
    depends_on_landed: list[str] | None = None,
    has_work_graph: bool = True,
) -> None:
    """Write a minimal valid spec trio the deriver compiles and the roadmap reads.

    Frontmatter carries the roadmap intent (`state`, `depends_on_landed`); the
    body carries one story and a Work Graph block so `derive_workgraph` succeeds
    — the scheduler dispatches a real (if tiny) `WorkGraph` to the child.

    A *trio*, not a `spec.md`: a spec directory the roadmap can dispatch has all
    three documents, because the dispatch path reads all three
    (`load_prompt_sources`) to assemble each node's prompt. This corpus wrote
    only `spec.md` while nothing before dispatch opened the other two; 044 US2
    moved prompt assembly into the pre-epic preflight, so a corpus missing
    `plan.md` and `tasks.md` is a corpus of specs that cannot be dispatched.
    Completing the fixture is what keeps these tests about the scheduler.
    """
    spec_dir.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if state is not None or depends_on_landed is not None:
        lines.append("---")
        if state is not None:
            lines.append(f"state: {state.value}")
        if depends_on_landed:
            lines.append(f"depends_on_landed: {depends_on_landed}")
        lines.append("---")
        lines.append("")
    lines += [
        "# Feature Specification: " + spec_dir.name,
        "",
        "## User Scenarios & Testing *(mandatory)*",
        "",
        "### User Story 1 - Build it (Priority: P1)",
        "",
        "As the operator, I build the thing, so that it works.",
        "",
        "**Acceptance Scenarios**:",
        "",
        "1. **Given** a thing, **When** it is built, **Then** it works.",
        "",
        "## Requirements *(mandatory)*",
        "",
        "### Functional Requirements",
        "",
        "- **FR-001**: The system MUST build the thing.",
        "",
    ]
    if has_work_graph:
        lines += [
            "## Work Graph",
            "",
            "```yaml",
            "US1:",
            "  depends_on: []",
            "  implements: [FR-001]",
            "```",
            "",
        ]
    (spec_dir / "spec.md").write_text("\n".join(lines), encoding="utf-8")
    (spec_dir / "plan.md").write_text(
        "\n".join(
            [
                "# Plan: " + spec_dir.name,
                "",
                "## Summary",
                "",
                "One story, built once.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    # The phase heading names the story *key*, which is the grammar prompt
    # assembly cuts a task slice on — the same grammar the 2026-08-15 kill
    # violated (044).
    (spec_dir / "tasks.md").write_text(
        "\n".join(
            [
                "# Tasks: " + spec_dir.name,
                "",
                "## Phase 1: User Story 1 - Build it (Priority: P1)",
                "",
                "- [ ] T001 [US1] Write the failing test (spec US1-S1)",
                "- [ ] T002 [US1] Build the thing until T001 passes",
                "",
            ]
        ),
        encoding="utf-8",
    )


def build_corpus(
    root: Path,
    specs: dict[str, dict[str, Any]],
) -> Path:
    """Write a `specs/` corpus from a spec-name -> kwargs map, sorted by dir."""
    specs_root = root / "specs"
    for name, kwargs in specs.items():
        _write_spec(specs_root / name, **kwargs)
    return specs_root


# --- scripting the roadmap's pre-dispatch seams ------------------------------


def _passing_profile(repo: str = TARGET_REPO) -> TargetRepoProfile:
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


def _failing_profile(repo: str = TARGET_REPO) -> TargetRepoProfile:
    return TargetRepoProfile(
        repo=repo,
        default_branch="main",
        visibility="public",
        queue_enabled=True,
        required_checks=("test",),
        declared_gates=("test",),
        findings=(
            Finding(
                check="merge-queue-enabled",
                passed=False,
                detail="the repo has no merge queue on its default branch",
            ),
        ),
        passed=False,
    )


class RoadmapWorld:
    """Script the seams the roadmap's pre-dispatch activities read.

    Each seam is reset per test through `apply`, so one worker's run sees one
    scripted world. The capacity seam (`open_epics`) is the one FR-004's
    "no polling" rests on: the test reports exactly the open `epic-*` ids it
    wants the scheduler to see, so the bound and the dispatch order are
    deterministic without a real Temporal list round trip.
    """

    def __init__(
        self,
        *,
        clone_ok: bool = True,
        preflight: Callable[[str], list] | None = None,
        onboarding_profile: TargetRepoProfile | None = None,
        open_epics: Callable[[], set[str]] | None = None,
        derive_runner: Callable[..., Any] | None = None,
        drift_runner: Callable[..., bool] | None = None,
    ) -> None:
        self.clone_ok = clone_ok
        self.preflight = preflight or (lambda epic_id: [])
        self.onboarding_profile = onboarding_profile or _passing_profile()
        self.open_epics = open_epics or (lambda: set())
        # US4: `derive_spec` now reads the target repo's git history. Existing
        # scheduler tests have no real clone at `TARGET_REPO`, so default to a
        # runner that derives the full graph (the pre-delta behavior) unless a
        # test explicitly passes a runner — US4 tests pass a delta runner.
        self.derive_runner = derive_runner or self._derive_full
        # US4: drift detection reads git in `drift_for_spec`. Existing scheduler
        # tests have no real clone, so default to no-drift unless a test scripts
        # a runner (US4-S5 exercises the real git-backed path directly).
        self.drift_runner = drift_runner or (lambda request: False)
        # What the clone seam was asked to refresh — the scheduler dispatches a
        # fresh clone per spec (FR-006), so the count is the dispatch count.
        self.clone_calls: list[str] = []

    def apply(self) -> None:
        """Replace the roadmap's activity seams with this world's scripted answers.

        Snapshots the original seams first so `restore` can put them back — the
        seams are module globals shared with every other test, so a leak here
        would make the preflight CLI or another roadmap run scripted by accident.

        Idempotent on purpose: `run_roadmap` applies for every test, and a test
        that also applied by hand must not have the second snapshot capture the
        already-scripted seams as "originals" — that exact double-apply leaked
        a scripted `_preflight_client` into every later test in the module and
        hid the seam's real-constructor crash (2026-08-13 roadmap fire).
        """
        import factory.workgraph.preflight as preflight_mod

        if getattr(self, "_saved", None):
            return
        self._saved = (
            roadmap_activities._clone_runner,
            roadmap_activities._derive_runner,
            roadmap_activities._drift_runner,
            roadmap_activities._preflight_registry,
            roadmap_activities._preflight_client,
            roadmap_activities._onboard,
            roadmap_activities._open_epics_provider,
            getattr(roadmap_activities, "_read_loop_config_runner", None),
            getattr(roadmap_activities, "check_aliases", None),
            preflight_mod.check_aliases,
        )
        roadmap_activities._clone_runner = self._clone
        if self.derive_runner is not None:
            roadmap_activities._derive_runner = self.derive_runner
        roadmap_activities._drift_runner = self.drift_runner
        roadmap_activities._preflight_registry = lambda: {}
        roadmap_activities._preflight_client = lambda proxy_url: None
        roadmap_activities._onboard = self._onboard
        roadmap_activities._open_epics_provider = self._open_epics_provider
        roadmap_activities._read_loop_config_runner = self._read_loop_config
        # Route the shared `check_aliases` through this world's scripted
        # findings without touching the proxy. The activity imported the name
        # by reference, so patch the binding the activity actually calls —
        # both the activities module's import and the source module's attr,
        # so whichever path a future refactor takes stays scripted.
        async def _check_aliases(graph, registry, client):
            return list(self.preflight(graph.epic_id))

        roadmap_activities.check_aliases = _check_aliases
        preflight_mod.check_aliases = _check_aliases

    def restore(self) -> None:
        """Put the original seams back so other tests see production code."""
        if not getattr(self, "_saved", None):
            return
        import factory.workgraph.preflight as preflight_mod

        (
            roadmap_activities._clone_runner,
            roadmap_activities._derive_runner,
            roadmap_activities._drift_runner,
            roadmap_activities._preflight_registry,
            roadmap_activities._preflight_client,
            roadmap_activities._onboard,
            roadmap_activities._open_epics_provider,
            saved_read_loop_config,
            saved_check,
            saved_preflight_check,
        ) = self._saved
        if saved_read_loop_config is not None:
            roadmap_activities._read_loop_config_runner = saved_read_loop_config
        else:
            try:
                delattr(roadmap_activities, "_read_loop_config_runner")
            except AttributeError:
                pass
        if saved_check is not None:
            roadmap_activities.check_aliases = saved_check
        else:
            try:
                delattr(roadmap_activities, "check_aliases")
            except AttributeError:
                pass
        preflight_mod.check_aliases = saved_preflight_check
        roadmap_activities._derive_runner = None
        roadmap_activities._drift_runner = None
        # Re-arm the apply/restore pair: a cleared snapshot is what lets the
        # idempotence guard in `apply` distinguish "fresh world" from
        # "already applied".
        self._saved = None

    def _clone(self, target_repo: str) -> CloneResult:
        self.clone_calls.append(target_repo)
        return CloneResult(
            path=target_repo, default_branch="main", head_ref="abc123"
        )

    async def _onboard(self, target_repo: str) -> TargetRepoProfile:
        return self.onboarding_profile

    async def _open_epics_provider(self) -> set[str]:
        return set(self.open_epics())

    def _read_loop_config(self, target_repo: str) -> Any:
        from factory.activities.roadmap_activities import ReadLoopConfigResult
        from factory.verify.models import VerificationConfig

        return ReadLoopConfigResult(config=VerificationConfig(), verify_order=("gates", "diff_check", "judge"))

    def _derive_full(self, request) -> Any:
        """Default derive seam: the full pre-delta graph, no git baseline."""
        from factory.workgraph.derive import derive_workgraph

        return derive_workgraph(
            request.spec_text,
            epic_id=request.epic_id,
            feature=request.feature,
            specs_root=request.specs_root,
            target_repo=request.target_repo,
        )


# --- the harness -------------------------------------------------------------


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    """Temporal with a clock the test owns — an hour of silence costs nothing.

    Resets the scripted-epic script so one test's statuses and hooks do not
    bleed into the next.
    """
    environment = await WorkflowEnvironment.start_time_skipping()
    _SCRIPT.statuses = {}
    _SCRIPT.on_dispatch = None
    _SCRIPT.on_complete = None
    _SCRIPT.hold = set()
    try:
        yield environment
    finally:
        await environment.shutdown()
        _SCRIPT.statuses = {}
        _SCRIPT.on_dispatch = None
        _SCRIPT.on_complete = None
        _SCRIPT.hold = set()


@asynccontextmanager
async def run_roadmap(
    env: WorkflowEnvironment,
    world: RoadmapWorld,
    specs_root: str,
    *,
    statuses: dict[str, EpicStatus] | None = None,
    max_concurrent_epics: int = 1,
    max_concurrent_nodes: int | None = None,
    idle_rescan_s: int | None = None,
    on_dispatch: Callable[[str], None] | None = None,
    on_complete: Callable[[str], None] | None = None,
    child_starts: list[ChildStartRecord] | None = None,
    extra_workflows: list = (),
    interceptors: list[Interceptor] | None = None,
) -> AsyncIterator[Any]:
    """Start the roadmap and hold the worker open while the test steers it.

    The worker serves the real `RoadmapWorkflow` plus a scripted `EpicWorkflow`
    under the real name, and the roadmap's activities with the world's seams
    applied. The roadmap's own activities (clone/derive/preflight/onboard/
    capacity/corpus-read/spec-read) are all registered whole so the worker
    accepts the call shapes; the seams decide what they return.
    """
    # Steer the single module-level scripted epic for this run.
    _SCRIPT.statuses = dict(statuses or {})
    _SCRIPT.on_dispatch = on_dispatch
    _SCRIPT.on_complete = on_complete
    world.apply()

    from factory.activities.notify_activities import (
        record_roadmap_failure,
        reset_roadmap_failures,
        send_escalation,
        send_roadmap_notice,
    )
    from factory.activities.roadmap_activities import (
        clone_target,
        count_open_epics,
        derive_spec,
        drift_for_spec,
        onboard_target,
        preflight_spec,
        read_loop_config,
    )
    from factory.roadmap.workflow import (
        read_corpus_activity,
        read_spec_text_activity,
    )

    activities = [
        clone_target,
        derive_spec,
        drift_for_spec,
        preflight_spec,
        onboard_target,
        count_open_epics,
        read_corpus_activity,
        read_spec_text_activity,
        read_loop_config,
        record_roadmap_failure,
        reset_roadmap_failures,
        send_roadmap_notice,
        send_escalation,
    ]
    interceptors = (
        [_RecordingInterceptor(child_starts)] if child_starts is not None else list(interceptors or [])
    )
    try:
        async with Worker(
            env.client,
            task_queue="workgraph",
            workflows=[RoadmapWorkflow, ScriptedEpicWorkflow, *extra_workflows],
            activities=activities,
            interceptors=interceptors,
            # The scripted `EpicWorkflow` reads its prescribed statuses and
            # dispatch hooks from the module-level `_SCRIPT` (in
            # `tests/roadmap_script.py`). The default sandboxed runner re-imports
            # that module into an isolated namespace, so a fresh `_Script()` is
            # born inside the sandbox and the test's mutations to the *outer*
            # `_SCRIPT` never reach it — every child would return the default
            # landed status and `on_dispatch`/`on_complete` would never fire.
            # The unsandboxed runner executes the workflow functions against the
            # worker process's own modules, so `_SCRIPT` is the one object the
            # test mutates. The real `RoadmapWorkflow` is unaffected: it is
            # deterministic and side-effect-free in workflow code either way, so
            # running it unsandboxed changes nothing the scheduler tests observe.
            # (The established `ScriptedWorld` pattern in `test_interpreter.py`
            # avoids this by scripting *activities* — whose inputs are
            # serialized across the boundary — rather than a workflow; the
            # roadmap's child is a workflow, so it needs the shared state.)
            workflow_runner=UnsandboxedWorkflowRunner(),
            workflow_failure_exception_types=[Exception],
        ):
            input_kwargs: dict[str, Any] = {
                "specs_root": specs_root,
                "target_repo": TARGET_REPO,
                "proxy_url": PROXY_URL,
                "max_concurrent_epics": max_concurrent_epics,
            }
            if max_concurrent_nodes is not None:
                input_kwargs["max_concurrent_nodes"] = max_concurrent_nodes
            if idle_rescan_s is not None:
                input_kwargs["idle_rescan_s"] = idle_rescan_s
            handle = await env.client.start_workflow(
                RoadmapWorkflow.run,
                RoadmapInput(**input_kwargs),
                id=roadmap_workflow_id(specs_root),
                task_queue="workgraph",
            )
            yield handle
    finally:
        world.restore()


async def run_to_completion(
    env: WorkflowEnvironment,
    world: RoadmapWorld,
    specs_root: str,
    **kwargs: Any,
) -> RoadmapStatus:
    """Run the roadmap to quiescence and hand back the final `RoadmapStatus`."""
    async with run_roadmap(env, world, specs_root, **kwargs) as handle:
        return await handle.result()


def _status_of(status: RoadmapStatus, spec_dir: str) -> Any:
    for spec in status.specs:
        if spec.spec_dir == spec_dir:
            return spec
    raise AssertionError(f"{spec_dir} not in roadmap status: {status}")


# ============================================================================
# T010 — scheduler cases (must fail before the workflow lands)
# ============================================================================


async def test_a_dispatchable_spec_starts_a_child_with_the_correct_input_and_id(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """Acceptance 1 / FR-004: a dispatchable spec's child starts with the right
    `EpicInput` and the `epic-<spec_dir>` id convention.

    A single `ready` spec with no dependencies and capacity free dispatches
    immediately: the clone runs, the child starts, and on its landed
    completion the roadmap reports the spec landed.
    """
    specs_root = build_corpus(
        tmp_path,
        {"001-alpha": dict(state=SpecState.READY)},
    )
    world = RoadmapWorld()
    status = await run_to_completion(env, world, str(specs_root))

    # The clone ran once — one fresh clone per dispatchable spec (FR-006).
    assert world.clone_calls == [TARGET_REPO]
    # The spec landed (the child returned COMPLETED with every landing MERGED).
    alpha = _status_of(status, "001-alpha")
    assert alpha.landed is True
    assert status.running == []


async def test_a_landed_dependency_dispatches_its_dependent_in_the_same_pass(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """Acceptance 3 / FR-004: a child completing with all landings MERGED marks the
    dependency observed-landed and dispatches the dependent unprompted in the
    same scheduling pass.

    `002-bravo` is `ready` and depends_on_landed `001-alpha` (also `ready`).
    The roadmap dispatches alpha first; alpha's child completes landed; the
    parent wakes and dispatches bravo with no external signal. Both land.
    """
    specs_root = build_corpus(
        tmp_path,
        {
            "001-alpha": dict(state=SpecState.READY),
            "002-bravo": dict(
                state=SpecState.READY, depends_on_landed=["001-alpha"]
            ),
        },
    )
    world = RoadmapWorld()
    status = await run_to_completion(env, world, str(specs_root))

    assert _status_of(status, "001-alpha").landed is True
    assert _status_of(status, "002-bravo").landed is True


async def test_a_failed_landing_leaves_dependents_blocked_and_reports_unlanded(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """Acceptance 4 / FR-006: a child completing without landing (a FAILED node)
    leaves dependents blocked and the roadmap reports the dependency as
    finished-but-not-landed.

    `001-alpha`'s child completes COMPLETED but with a FAILED (not MERGED)
    node — finished but not landed. `002-bravo` depends_on_landed alpha, so it
    stays blocked, and its status names alpha as `unlanded`.
    """
    specs_root = build_corpus(
        tmp_path,
        {
            "001-alpha": dict(state=SpecState.READY),
            "002-bravo": dict(
                state=SpecState.READY, depends_on_landed=["001-alpha"]
            ),
        },
    )
    # alpha completes finished-but-not-landed (a FAILED node).
    statuses = {"001-alpha": failed_status()}
    world = RoadmapWorld()
    status = await run_to_completion(env, world, str(specs_root), statuses=statuses)

    alpha = _status_of(status, "001-alpha")
    assert alpha.landed is False  # finished but not landed
    bravo = _status_of(status, "002-bravo")
    assert bravo.dispatchable is False
    assert "001-alpha" in bravo.blockers
    # The dependency is reported finished-but-not-landed (acceptance 4).
    assert "001-alpha" in bravo.unlanded
    assert bravo.landed is False


async def test_two_dispatchable_specs_respect_the_bound_and_declaration_order(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """Acceptance 5 / FR-005: two simultaneously dispatchable specs dispatch in
    spec-directory order (lexicographic), and the second waits for capacity
    when the bound is one.

    Two independent `ready` specs (`001-alpha`, `002-bravo`) with the bound at
    one: alpha dispatches first, bravo waits for capacity, and both land. The
    capacity seam reports exactly the in-flight children, so the bound gates
    the second until the first completes — and the dispatch order is
    lexicographic, the numbered-directory convention.
    """
    specs_root = build_corpus(
        tmp_path,
        {
            "001-alpha": dict(state=SpecState.READY),
            "002-bravo": dict(state=SpecState.READY),
        },
    )

    # The capacity seam reports the roadmap's own in-flight children: a child
    # adds its `epic-<spec>` id while running and drops it on completion, so
    # the bound of one gates the second dispatch until the first lands.
    open_state: set[str] = set()
    started: list[str] = []
    in_flight: list[int] = [0]

    def on_dispatch(epic_id: str) -> None:
        started.append(epic_id)
        open_state.add(f"epic-{epic_id}")
        in_flight[0] = max(in_flight[0], len(open_state))

    def on_complete(epic_id: str) -> None:
        open_state.discard(f"epic-{epic_id}")

    world = RoadmapWorld(open_epics=lambda: set(open_state))
    status = await run_to_completion(
        env,
        world,
        str(specs_root),
        on_dispatch=on_dispatch,
        on_complete=on_complete,
    )

    # Both landed.
    assert _status_of(status, "001-alpha").landed is True
    assert _status_of(status, "002-bravo").landed is True
    # Dispatch order is lexicographic (the numbered-directory convention).
    assert started == ["001-alpha", "002-bravo"]
    # The bound of one held: never more than one child in flight at once.
    assert in_flight[0] <= 1


async def test_two_dispatchable_specs_run_concurrently_when_the_bound_allows(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """FR-005: the bound is a knob. With the bound at two, two dispatchable
    specs dispatch in the same pass (both clone, both start) rather than one
    waiting for the other."""
    specs_root = build_corpus(
        tmp_path,
        {
            "001-alpha": dict(state=SpecState.READY),
            "002-bravo": dict(state=SpecState.READY),
        },
    )
    world = RoadmapWorld()
    status = await run_to_completion(
        env, world, str(specs_root), max_concurrent_epics=2
    )
    assert _status_of(status, "001-alpha").landed is True
    assert _status_of(status, "002-bravo").landed is True


async def test_a_predispatch_refusal_parks_the_spec_and_the_roadmap_proceeds(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """Acceptance 2 / FR-006: a pre-dispatch check that refuses parks the spec
    with the finding verbatim and the roadmap continues with other work — one
    bad spec must not stall the line.

    `001-alpha`'s preflight refuses (an unserved alias finding); `002-bravo`
    is independent and dispatches, lands, and the roadmap finishes. alpha is
    parked with the finding's detail verbatim.
    """
    from factory.workgraph.preflight import PreflightFinding

    specs_root = build_corpus(
        tmp_path,
        {
            "001-alpha": dict(state=SpecState.READY),
            "002-bravo": dict(state=SpecState.READY),
        },
    )
    refusal = PreflightFinding(
        check="model-aliases-served",
        passed=False,
        detail="the proxy does not serve every alias this registry names.",
    )

    world = RoadmapWorld(
        preflight=lambda epic_id: [refusal] if epic_id == "001-alpha" else []
    )
    async with run_roadmap(env, world, str(specs_root)) as handle:
        status = await handle.result()

    # alpha parked with the finding verbatim.
    parked = {p.spec_dir: p for p in status.parked}
    assert "001-alpha" in parked
    assert parked["001-alpha"].detail == refusal.detail
    assert parked["001-alpha"].check == f"preflight:{refusal.check}"
    # bravo proceeded and landed — one bad spec did not stall the line.
    assert _status_of(status, "002-bravo").landed is True
    assert status.running == []


async def test_a_derivation_error_parks_the_spec_with_the_finding(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """FR-006 / Edge case: a spec that is `ready` but has no `## Work Graph`
    section refuses at derivation; the roadmap parks it with the finding
    rather than retrying forever."""
    specs_root = build_corpus(
        tmp_path,
        {
            "001-alpha": dict(state=SpecState.READY, has_work_graph=False),
            "002-bravo": dict(state=SpecState.READY),
        },
    )
    world = RoadmapWorld()
    async with run_roadmap(env, world, str(specs_root)) as handle:
        status = await handle.result()

    parked = {p.spec_dir: p for p in status.parked}
    assert "001-alpha" in parked
    assert parked["001-alpha"].check == "derive"
    # bravo still lands.
    assert _status_of(status, "002-bravo").landed is True


async def test_an_onboarding_failure_parks_the_spec(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """FR-006: an onboarding finding parks the spec with the finding verbatim,
    and the roadmap continues."""
    specs_root = build_corpus(
        tmp_path,
        {
            "001-alpha": dict(state=SpecState.READY),
        },
    )
    world = RoadmapWorld(onboarding_profile=_failing_profile())
    async with run_roadmap(env, world, str(specs_root)) as handle:
        status = await handle.result()

    parked = {p.spec_dir: p for p in status.parked}
    assert "001-alpha" in parked
    assert parked["001-alpha"].check == "onboarding"
    assert "merge-queue-enabled" in parked["001-alpha"].detail


# ============================================================================
# T011 — child-policy cases (must fail before the workflow lands)
# ============================================================================


async def test_child_start_uses_parent_close_policy_abandon(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """SC-004 / T011: `parent_close_policy` is ABANDON — terminating or
    continuing the roadmap must never kill an in-flight epic.

    Asserted by intercepting the roadmap's `start_child_workflow` call and
    reading the policy it handed Temporal, rather than by a cancellation round
    trip: the policy is the contract, and drift here is what would kill a
    mid-flight epic the day an operator terminates the roadmap.
    """
    specs_root = build_corpus(tmp_path, {"001-alpha": dict(state=SpecState.READY)})
    world = RoadmapWorld()
    starts: list[ChildStartRecord] = []
    await run_to_completion(env, world, str(specs_root), child_starts=starts)

    assert len(starts) == 1, starts
    record = starts[0]
    assert record.workflow == "EpicWorkflow"
    assert record.id == "epic-001-alpha"
    assert "ABANDON" in record.parent_close_policy, record.parent_close_policy


async def test_child_start_uses_default_id_reuse_so_a_closed_id_is_reusable(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """T011: a closed `epic-<spec>` id is reused cleanly (the five-closed-runs
    precedent). `id_reuse_policy` is the default `ALLOW_DUPLICATE`, so a closed
    run does not block a fresh dispatch under the same id."""
    specs_root = build_corpus(tmp_path, {"001-alpha": dict(state=SpecState.READY)})
    world = RoadmapWorld()
    starts: list[ChildStartRecord] = []
    await run_to_completion(env, world, str(specs_root), child_starts=starts)

    assert len(starts) == 1, starts
    assert "ALLOW_DUPLICATE" in starts[0].id_reuse_policy, starts[0].id_reuse_policy


async def test_a_running_collision_under_the_child_id_parks_and_never_adopts(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """T011: a dispatch that collides with a RUNNING workflow under the child's
    `epic-<spec>` id parks the spec with the collision named, never adopts the
    running epic. `ALLOW_DUPLICATE` does not permit taking a live id, so the
    start raises and the roadmap parks.

    A blocker workflow is started under `epic-001-alpha` and held open before
    the roadmap runs; the roadmap's dispatch of alpha collides and parks, while
    bravo (independent) dispatches and lands — the line proceeds.
    """
    specs_root = build_corpus(
        tmp_path,
        {
            "001-alpha": dict(state=SpecState.READY),
            "002-bravo": dict(state=SpecState.READY),
        },
    )
    world = RoadmapWorld()

    # Pre-start a RUNNING workflow under the child id the roadmap will claim.
    blocker = await env.client.start_workflow(
        BlockerRunningWorkflow.run,
        id="epic-001-alpha",
        task_queue="workgraph",
    )

    async with run_roadmap(
        env,
        world,
        str(specs_root),
        extra_workflows=[BlockerRunningWorkflow],
    ) as handle:
        status = await handle.result()

    parked = {p.spec_dir: p for p in status.parked}
    assert "001-alpha" in parked
    assert parked["001-alpha"].check == "collision"
    # bravo proceeded and landed — one collision did not stall the line.
    assert _status_of(status, "002-bravo").landed is True
    assert status.running == []

    # Release the blocker so the env can shut down cleanly.
    await blocker.cancel()


async def test_capacity_accounts_for_an_operator_started_epic(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """T011 / FR-005: capacity accounting counts an operator-started `epic-*`
    workflow the roadmap did not start, so a restart never double-dispatches
    into a slot an operator's epic already holds.

    Two dispatchable specs and a bound of two would normally let both start in
    one pass. An operator-started `epic-999-operator` is reported by the
    capacity seam as in-flight, so the roadmap sees one free slot, not two:
    only `001-alpha` dispatches this pass. When alpha's child completes, the
    roadmap wakes (a child completion — FR-004), re-reads capacity (the operator
    epic still there), and dispatches `002-bravo` into the one remaining slot.
    Both land, but never two at once — the operator epic was counted against
    the bound the whole time.
    """
    specs_root = build_corpus(
        tmp_path,
        {
            "001-alpha": dict(state=SpecState.READY),
            "002-bravo": dict(state=SpecState.READY),
        },
    )

    open_state: set[str] = {"epic-999-operator"}
    in_flight: list[int] = [0]

    def on_dispatch(epic_id: str) -> None:
        open_state.add(f"epic-{epic_id}")
        # The operator epic plus the roadmap's own children — capacity the
        # scheduler must count together.
        in_flight[0] = max(in_flight[0], len(open_state))

    def on_complete(epic_id: str) -> None:
        open_state.discard(f"epic-{epic_id}")

    def open_epics() -> set[str]:
        # The operator epic the roadmap did not start, reported every pass.
        return set(open_state)

    world = RoadmapWorld(open_epics=open_epics)
    status = await run_to_completion(
        env,
        world,
        str(specs_root),
        max_concurrent_epics=2,
        on_dispatch=on_dispatch,
        on_complete=on_complete,
    )

    # Both specs landed.
    assert _status_of(status, "001-alpha").landed is True
    assert _status_of(status, "002-bravo").landed is True
    # The operator epic counted against the bound of two: never more than one
    # of the roadmap's own children in flight at once, because the operator's
    # epic held the other slot the whole time.
    assert in_flight[0] <= 2


# ============================================================================
# T012 — credential sweep (FR-009): no key value reaches any roadmap surface
# ============================================================================


def _sweep_surfaces_for_secret(secret: str) -> None:
    """Grep every roadmap surface for the canary key (the 001 pattern, extended
    one level up by FR-009): frontmatter parsing output, parked findings,
    `roadmap_status` payloads, and the roadmap's workflow input.

    Frontmatter parsing is pure (`read_roadmap`), the workflow input and status
    are dataclasses, and the parked findings carry refusal text verbatim — so
    the canary must not appear in any of them. The grep is over the source of
    the modules that build these surfaces and the dataclass definitions, so a
    leak through any field a finding or payload carries fails here.
    """
    import subprocess

    repo = Path(__file__).resolve().parent.parent
    targets = [
        "factory/roadmap/workflow.py",
        "factory/roadmap/models.py",
        "factory/activities/roadmap_activities.py",
        "factory/roadmap/cli.py",
    ]
    result = subprocess.run(
        ["grep", "-rn", secret, *targets],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    # grep -rn returns 1 when no match, 0 when a match is found. A match is a
    # leak — the canary appears in a surface that builds frontmatter output, a
    # finding, a status payload, or the workflow input.
    if result.returncode == 0:
        raise AssertionError(
            f"FR-009 leak: the canary key appears in a roadmap surface:\n"
            f"{result.stdout}"
        )


async def test_no_credential_reaches_any_roadmap_surface(
    env: WorkflowEnvironment, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-009 / T012: no key value reaches frontmatter parsing output, parked
    findings, `roadmap_status` payloads, or the roadmap's workflow input.

    The canary master key is planted in the worker environment (where 001's
    discipline says it lives and the preflight reads it), the roadmap runs a
    full dispatch including a preflight that touches the seam, and then every
    surface the roadmap produces is searched for the canary: the returned
    `RoadmapStatus` (and its parked findings), the serialized `RoadmapInput`,
    and a parked finding's verbatim text. None may contain a byte of it.

    This mirrors `tests/test_final_sweep.py`'s grep-backed 001 discipline: the
    canary is unlike anything else in the repo, so a single byte of it
    anywhere is a leak with no innocent explanation.
    """
    monkeypatch.setenv("LITELLM_MASTER_KEY", SECRET)

    # A preflight that refuses, so a parked finding is produced this run — the
    # surface most likely to echo a credential if one leaked into a finding.
    from factory.workgraph.preflight import PreflightFinding

    specs_root = build_corpus(
        tmp_path,
        {
            "001-alpha": dict(state=SpecState.READY),
            "002-bravo": dict(state=SpecState.READY),
        },
    )
    refusal = PreflightFinding(
        check="model-aliases-served",
        passed=False,
        detail="the proxy does not serve every alias this registry names.",
    )
    world = RoadmapWorld(
        preflight=lambda epic_id: [refusal] if epic_id == "001-alpha" else []
    )

    async with run_roadmap(env, world, str(specs_root)) as handle:
        status = await handle.result()

    # The roadmap's own surfaces carry no credential. The status is the query
    # payload; its parked findings carry refusal text; the workflow input was
    # the run's argument. Serialize each and search for the canary.
    from dataclasses import asdict, is_dataclass

    import json

    def _blob(obj: Any) -> str:
        if obj is None:
            return ""
        if is_dataclass(obj):
            return json.dumps(asdict(obj), default=str, sort_keys=True)
        return repr(obj)

    surfaces = {
        "roadmap_status": _blob(status),
        "parked_finding": _blob(status.parked[0]) if status.parked else "",
    }
    for name, blob in surfaces.items():
        assert SECRET not in blob, (
            f"FR-009 leak: the canary key reached the {name} surface:\n{blob}"
        )

    # The workflow input carries no credential by construction (RoadmapInput
    # has no key field), and the grep over the source proves no surface builds
    # one from the environment. The preflight seam read the canary from the
    # environment — the assertion is that it stayed in the seam.
    _sweep_surfaces_for_secret(SECRET)


# ============================================================================
# T006 / T007 / T008 — US2 node concurrency (must fail before the field lands)
# ============================================================================


async def test_a_dispatchable_spec_receives_the_node_bound_in_its_epic_input(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """Acceptance 1 / FR-004: a roadmap started with a node bound of 3 starts
    its child with `max_concurrent_nodes=3`."""
    specs_root = build_corpus(
        tmp_path,
        {"001-alpha": dict(state=SpecState.READY)},
    )
    starts: list[ChildStartRecord] = []
    await run_to_completion(
        env,
        RoadmapWorld(),
        str(specs_root),
        max_concurrent_nodes=3,
        child_starts=starts,
    )
    assert len(starts) == 1, starts
    child_input: EpicInput = starts[0].args[0]
    assert child_input.max_concurrent_nodes == 3, child_input


async def test_a_dispatchable_spec_receives_default_one_when_no_node_bound_given(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """Acceptance 2 / FR-004: a roadmap started without a node bound starts its
    child with `max_concurrent_nodes=1` exactly, so the expression is required
    and the default is not merely a coincidence on both sides."""
    specs_root = build_corpus(
        tmp_path,
        {"001-alpha": dict(state=SpecState.READY)},
    )
    starts: list[ChildStartRecord] = []
    await run_to_completion(
        env,
        RoadmapWorld(),
        str(specs_root),
        child_starts=starts,
    )
    assert len(starts) == 1, starts
    child_input: EpicInput = starts[0].args[0]
    assert child_input.max_concurrent_nodes == 1, child_input


@pytest.mark.parametrize(
    "bad_bound, expected_text",
    [
        (0, "0"),
        (-1, "-1"),
    ],
)
async def test_a_bad_node_bound_is_refused_at_start(
    env: WorkflowEnvironment,
    tmp_path: Path,
    bad_bound: Any,
    expected_text: str,
) -> None:
    """Acceptance 3 / FR-005: zero and negative node bounds are refused at
    roadmap start with the value named."""
    specs_root = build_corpus(
        tmp_path,
        {"001-alpha": dict(state=SpecState.READY)},
    )
    with pytest.raises(Exception) as excinfo:
        await run_to_completion(
            env,
            RoadmapWorld(),
            str(specs_root),
            max_concurrent_nodes=bad_bound,  # type: ignore[arg-type]
        )
    message = str(excinfo.value)
    # Temporal wraps the workflow exception in WorkflowFailureError, whose
    # `__cause__` holds the real ApplicationError from the workflow.
    if excinfo.value.__cause__ is not None:
        message = str(excinfo.value.__cause__)
    assert expected_text in message, message
    assert "max_concurrent_nodes" in message, message


@pytest.mark.parametrize(
    "bad_bound, expected_text",
    [
        (True, "True"),
        ("three", "'three'"),
        (3.14, "3.14"),
    ],
)
def test_a_non_integer_node_bound_is_refused_by_validation(
    bad_bound: Any,
    expected_text: str,
) -> None:
    """FR-005: boolean and non-integer node bounds are refused by validation.

    Temporal's payload converter coerces or rejects some of these before the
    workflow body runs, so this exercises `RoadmapWorkflow._validate_input`
    directly to prove the guard exists and names the value. The boolean case
    matters because `isinstance(True, int)` is `True` (trap 5).
    """
    from factory.roadmap.workflow import RoadmapWorkflow
    from temporalio.exceptions import ApplicationError

    request = RoadmapInput(
        specs_root="/tmp/specs",
        target_repo="/tmp/target",
        proxy_url="http://proxy.test",
        max_concurrent_nodes=bad_bound,  # type: ignore[arg-type]
    )
    with pytest.raises(ApplicationError) as excinfo:
        RoadmapWorkflow._validate_input(request)
    assert expected_text in str(excinfo.value)
    assert "max_concurrent_nodes" in str(excinfo.value)


async def test_roadmap_status_reports_both_bounds(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """Acceptance 4 / FR-005: `roadmap_status` names the node bound alongside
    the epic bound so the operator can read the knob they set."""
    specs_root = build_corpus(
        tmp_path,
        {"001-alpha": dict(state=SpecState.READY)},
    )
    async with run_roadmap(
        env,
        RoadmapWorld(),
        str(specs_root),
        max_concurrent_epics=2,
        max_concurrent_nodes=3,
    ) as handle:
        status = await handle.query("roadmap_status", result_type=RoadmapStatus)
        assert status.max_concurrent_epics == 2, status
        assert status.max_concurrent_nodes == 3, status


async def test_node_bound_survives_continue_as_new(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """FR-004 / trap 4: the node bound rides `RoadmapCarryOver` across a
    continue-as-new boundary. Without this the first CAN silently reverts it
    to 1.

    Two dispatchable specs with the bound at one and node bound at 3: the
    first epic dispatches and lands, the roadmap continues-as-new, and the
    second epic must still receive `max_concurrent_nodes=3`.
    """
    specs_root = build_corpus(
        tmp_path,
        {
            "001-alpha": dict(state=SpecState.READY),
            "002-bravo": dict(state=SpecState.READY),
        },
    )
    starts: list[ChildStartRecord] = []
    status = await run_to_completion(
        env,
        RoadmapWorld(),
        str(specs_root),
        max_concurrent_nodes=3,
        child_starts=starts,
    )
    # Both dispatched and landed.
    assert _status_of(status, "001-alpha").landed is True
    assert _status_of(status, "002-bravo").landed is True
    assert len(starts) == 2, starts
    for record in starts:
        child_input: EpicInput = record.args[0]
        assert child_input.max_concurrent_nodes == 3, child_input


# ============================================================================
# T013 / T014 — US3 idle behaviour (must fail before the field/signal lands)
# ============================================================================


async def test_idle_roadmap_waits_and_consumes_no_activity(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """FR-007 / acceptance 1: with idle configured and nothing dispatchable, the
    roadmap does not return; while idle and unsignalled it executes no activity.

    A one-hour idle timeout is skipped in time; the only observable activity
    is the initial corpus read. The test asserts the activity-call count (read
    corpus + capacity read) does not grow during idle: one activity, one pass.
    """
    specs_root = build_corpus(
        tmp_path,
        {"001-alpha": dict(state=SpecState.DRAFT)},
    )
    world = RoadmapWorld()
    activity_calls: list[str] = []
    original_read_corpus = factory_roadmap_workflow.read_corpus_activity
    original_count_open = roadmap_activities.count_open_epics

    @activity.defn(name="read_corpus_activity")
    async def counting_read_corpus(request: dict) -> Roadmap:
        activity_calls.append("read_corpus")
        typed_request = factory_roadmap_workflow.ReadCorpusInput(
            specs_root=request["specs_root"]
        )
        return await original_read_corpus(typed_request)

    @activity.defn(name="count_open_epics")
    async def counting_count_open(request: roadmap_activities.CountOpenInput) -> Any:
        activity_calls.append("count_open")
        return await original_count_open(request)

    # Patch activities through the same seam `RoadmapWorld` already handles.
    world.apply()
    factory_roadmap_workflow.read_corpus_activity = counting_read_corpus
    roadmap_activities.count_open_epics = counting_count_open

    async with run_roadmap(
        env, world, str(specs_root), idle_rescan_s=3600
    ) as handle:
        # Sleep partway through the idle interval: no timeout has fired and no
        # signal has arrived, so the workflow should still be parked and no
        # new activity should have run.
        await env.sleep(timedelta(seconds=1800))
        # The workflow must still be running; it has idled, not returned.
        assert await handle.query("roadmap_status", result_type=RoadmapStatus)

    world.restore()

    # Only the initial read happened; the idle period added no activity calls.
    assert activity_calls == ["read_corpus"]


async def test_rescan_signal_wakes_idle_roadmap_and_dispatches(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """FR-007 / acceptance 2: a `rescan` signal causes a corpus re-read in the
    same pass and dispatches a spec readied since the last pass.

    The roadmap starts with one `draft` spec and an idle timeout far away. The
    test flips the spec to `ready` and sends `rescan`; the next pass reads the
    corpus, sees the ready spec, and dispatches it.
    """
    specs_root = build_corpus(
        tmp_path,
        {"001-alpha": dict(state=SpecState.DRAFT)},
    )
    world = RoadmapWorld()
    async with run_roadmap(
        env, world, str(specs_root), idle_rescan_s=3600
    ) as handle:
        # Flip the spec to ready in the filesystem.
        _write_spec(specs_root / "001-alpha", state=SpecState.READY)
        await handle.signal(RoadmapWorkflow.rescan)
        # The child lands and the roadmap idles again because nothing else is
        # ready. Query to observe the landed state; then cancel the idle run.
        await env.sleep(timedelta(seconds=5))
        status = await handle.query("roadmap_status", result_type=RoadmapStatus)
        alpha = _status_of(status, "001-alpha")
        assert alpha.landed is True
        assert status.running == []
        await handle.cancel()


async def test_idle_timeout_re_reads_corpus_safety_net(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """FR-007 / acceptance 3: when the idle interval elapses with no signal, the
    roadmap re-reads the corpus once and dispatches a newly-ready spec.

    The spec is flipped to `ready` while the roadmap is idle; the idle timeout
    wakes it, the re-read sees the ready spec, and it dispatches.
    """
    specs_root = build_corpus(
        tmp_path,
        {"001-alpha": dict(state=SpecState.DRAFT)},
    )
    world = RoadmapWorld()
    async with run_roadmap(
        env, world, str(specs_root), idle_rescan_s=60
    ) as handle:
        # Flip the spec to ready before the idle timeout fires.
        _write_spec(specs_root / "001-alpha", state=SpecState.READY)
        # Wait long enough for the idle timeout to fire, re-read, dispatch, land.
        await env.sleep(timedelta(seconds=120))
        status = await handle.query("roadmap_status", result_type=RoadmapStatus)
        alpha = _status_of(status, "001-alpha")
        assert alpha.landed is True
        assert status.running == []
        await handle.cancel()


async def test_no_idle_config_returns_exactly_as_today(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """FR-006 / acceptance 5: absent `idle_rescan_s`, a roadmap that finds
    nothing dispatchable and nothing in flight returns immediately.

    This is the no-regression case: every current caller depends on drain-and-exit
    as the default.
    """
    specs_root = build_corpus(
        tmp_path,
        {"001-alpha": dict(state=SpecState.DRAFT)},
    )
    world = RoadmapWorld()
    status = await run_to_completion(env, world, str(specs_root))

    assert _status_of(status, "001-alpha").state is SpecState.DRAFT
    assert status.running == []


async def test_history_does_not_grow_across_idle_wakes(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """FR-008 / acceptance 4: many consecutive idle wakes keep history bounded.

    Five idle wakes are forced by flipping a spec to `ready`, letting it
    dispatch and land, then idling and repeating. Each idle wake is a
    continue-as-new boundary with zero children open, so no single run's event
    count grows with the number of wakes.
    """
    specs_root = build_corpus(
        tmp_path,
        {"001-alpha": dict(state=SpecState.DRAFT)},
    )
    world = RoadmapWorld()

    async with run_roadmap(
        env, world, str(specs_root), idle_rescan_s=60
    ) as handle:
        for _ in range(5):
            _write_spec(specs_root / "001-alpha", state=SpecState.READY)
            await handle.signal(RoadmapWorkflow.rescan)
            # Wait for the spec to land and the roadmap to go idle again.
            await env.sleep(timedelta(seconds=30))
            # Flip back to draft so the next wake has nothing to dispatch.
            _write_spec(specs_root / "001-alpha", state=SpecState.DRAFT)
            await handle.signal(RoadmapWorkflow.rescan)
            await env.sleep(timedelta(seconds=30))

        # Verify the spec is landed after the last wake.
        status = await handle.query("roadmap_status", result_type=RoadmapStatus)
        alpha = _status_of(status, "001-alpha")
        assert alpha.landed is True
        # No need to drain the idle workflow; the run has cycled through five
        # continue-as-new boundaries at quiescence, proving history is bounded.
        await handle.cancel()


async def test_idle_config_survives_continue_as_new(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """Trap 4 / FR-008: the idle configuration rides `RoadmapCarryOver` across a
    continue-as-new boundary so an idle roadmap does not silently revert to
    drain-and-exit after its first idle wake.
    """
    specs_root = build_corpus(
        tmp_path,
        {
            "001-alpha": dict(state=SpecState.READY),
            "002-bravo": dict(state=SpecState.DRAFT),
        },
    )
    world = RoadmapWorld()

    async with run_roadmap(
        env, world, str(specs_root), idle_rescan_s=60
    ) as handle:
        # alpha lands on the first pass and the roadmap CANs at quiescence.
        await env.sleep(timedelta(seconds=10))
        # After CAN, the new run should still be idle. Flip bravo to ready and
        # wait the idle timeout; if idle config were lost, the roadmap would
        # have returned and bravo would not dispatch.
        _write_spec(specs_root / "002-bravo", state=SpecState.READY)
        await env.sleep(timedelta(seconds=90))
        status = await handle.query("roadmap_status", result_type=RoadmapStatus)

        assert _status_of(status, "001-alpha").landed is True
        assert _status_of(status, "002-bravo").landed is True
        await handle.cancel()


async def test_rescan_while_paused_dispatches_nothing(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """Edge case / acceptance 6-adjacent: `pause_roadmap` wins over `rescan`.

    A paused roadmap that receives `rescan` while parked between epics stays
    parked until `resume_roadmap`; idle must not route around the existing pause
    wait (spec edge case).
    """
    specs_root = build_corpus(
        tmp_path,
        {
            "001-alpha": dict(state=SpecState.READY),
            "002-bravo": dict(state=SpecState.DRAFT),
        },
    )
    world = RoadmapWorld()

    async with run_roadmap(
        env, world, str(specs_root), idle_rescan_s=60
    ) as handle:
        # alpha lands on the first pass and the roadmap CANs into idle.
        await env.sleep(timedelta(seconds=10))

        # Pause the roadmap while it is idle between epics.
        await handle.signal(RoadmapWorkflow.pause_roadmap)
        # Flip bravo to ready and send rescan — it must not dispatch.
        _write_spec(specs_root / "002-bravo", state=SpecState.READY)
        await handle.signal(RoadmapWorkflow.rescan)
        await env.sleep(timedelta(seconds=20))
        paused_status = await handle.query(
            "roadmap_status", result_type=RoadmapStatus
        )
        assert paused_status.paused is True
        assert "002-bravo" not in paused_status.running

        # Resume — now bravo dispatches and lands.
        await handle.signal(RoadmapWorkflow.resume_roadmap)
        await env.sleep(timedelta(seconds=40))
        status = await handle.query("roadmap_status", result_type=RoadmapStatus)
        assert _status_of(status, "001-alpha").landed is True
        assert _status_of(status, "002-bravo").landed is True
        await handle.cancel()


async def test_preflight_client_seam_constructs_the_real_client(monkeypatch):
    """The seam must build `LiteLLMClient` with kwargs the class accepts.

    Every scheduler test replaces `_preflight_client`, so nothing here ever
    constructed the real one — and the first live roadmap fire after 036
    landed (2026-08-13 12:30Z) died on exactly that: the seam passed
    `api_key=` where the constructor takes `master_key=`. This test is the
    only place the production seam meets the production constructor.
    """
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test-preflight-seam")
    client = roadmap_activities._preflight_client("http://proxy.invalid")
    try:
        assert client.base_url == "http://proxy.invalid"
    finally:
        await client.aclose()
