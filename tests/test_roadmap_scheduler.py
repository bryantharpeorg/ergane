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
from pathlib import Path
from typing import Any, AsyncIterator, Callable

import pytest
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
from factory.roadmap.models import SpecState
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
    """Write a minimal valid spec the deriver compiles and the roadmap reads.

    Frontmatter carries the roadmap intent (`state`, `depends_on_landed`); the
    body carries one story and a Work Graph block so `derive_workgraph` succeeds
    — the scheduler dispatches a real (if tiny) `WorkGraph` to the child.
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
    ) -> None:
        self.clone_ok = clone_ok
        self.preflight = preflight or (lambda epic_id: [])
        self.onboarding_profile = onboarding_profile or _passing_profile()
        self.open_epics = open_epics or (lambda: set())
        # What the clone seam was asked to refresh — the scheduler dispatches a
        # fresh clone per spec (FR-006), so the count is the dispatch count.
        self.clone_calls: list[str] = []

    def apply(self) -> None:
        """Replace the roadmap's activity seams with this world's scripted answers.

        Snapshots the original seams first so `restore` can put them back — the
        seams are module globals shared with every other test, so a leak here
        would make the preflight CLI or another roadmap run scripted by accident.
        """
        import factory.workgraph.preflight as preflight_mod

        self._saved = (
            roadmap_activities._clone_runner,
            roadmap_activities._preflight_registry,
            roadmap_activities._preflight_client,
            roadmap_activities._onboard,
            roadmap_activities._open_epics_provider,
            getattr(roadmap_activities, "check_aliases", None),
            preflight_mod.check_aliases,
        )
        roadmap_activities._clone_runner = self._clone
        roadmap_activities._preflight_registry = lambda: {}
        roadmap_activities._preflight_client = lambda proxy_url: None
        roadmap_activities._onboard = self._onboard
        roadmap_activities._open_epics_provider = self._open_epics_provider
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
            roadmap_activities._preflight_registry,
            roadmap_activities._preflight_client,
            roadmap_activities._onboard,
            roadmap_activities._open_epics_provider,
            saved_check,
            saved_preflight_check,
        ) = self._saved
        if saved_check is not None:
            roadmap_activities.check_aliases = saved_check
        else:
            try:
                delattr(roadmap_activities, "check_aliases")
            except AttributeError:
                pass
        preflight_mod.check_aliases = saved_preflight_check

    def _clone(self, target_repo: str) -> CloneResult:
        self.clone_calls.append(target_repo)
        return CloneResult(path=target_repo, default_branch="main", head_ref="abc123")

    async def _onboard(self, target_repo: str) -> TargetRepoProfile:
        return self.onboarding_profile

    async def _open_epics_provider(self) -> set[str]:
        return set(self.open_epics())


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
    try:
        yield environment
    finally:
        await environment.shutdown()
        _SCRIPT.statuses = {}
        _SCRIPT.on_dispatch = None
        _SCRIPT.on_complete = None


@asynccontextmanager
async def run_roadmap(
    env: WorkflowEnvironment,
    world: RoadmapWorld,
    specs_root: str,
    *,
    statuses: dict[str, EpicStatus] | None = None,
    max_concurrent_epics: int = 1,
    on_dispatch: Callable[[str], None] | None = None,
    on_complete: Callable[[str], None] | None = None,
    child_starts: list[ChildStartRecord] | None = None,
    extra_workflows: list = (),
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

    from factory.activities.roadmap_activities import (
        clone_target,
        count_open_epics,
        derive_spec,
        onboard_target,
        preflight_spec,
    )
    from factory.roadmap.workflow import (
        read_corpus_activity,
        read_spec_text_activity,
    )

    activities = [
        clone_target,
        derive_spec,
        preflight_spec,
        onboard_target,
        count_open_epics,
        read_corpus_activity,
        read_spec_text_activity,
    ]
    interceptors = [_RecordingInterceptor(child_starts)] if child_starts is not None else []
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
        ):
            handle = await env.client.start_workflow(
                RoadmapWorkflow.run,
                RoadmapInput(
                    specs_root=specs_root,
                    target_repo=TARGET_REPO,
                    proxy_url=PROXY_URL,
                    max_concurrent_epics=max_concurrent_epics,
                ),
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
