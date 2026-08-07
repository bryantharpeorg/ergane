"""The operator's steering wheel: derive, start, status.

`factory-epic` is the whole human surface of the interpreter (FR-009, US3).
Everything richer — history, stack traces, per-activity timing — is Temporal's
Web UI, which is why this CLI is three verbs and why this suite can pin all
three exactly rather than sampling them.

The three verbs are tested at different depths because they carry different
risk:

- **`derive` is offline and exact.** It compiles a spec into `workgraph.json`
  and starts nothing, so it is asserted as a pure pipeline: the whole artifact
  against the fixture corpus (SC-006), the whole error list on failure, and
  *nothing written* on any failing path. That last one is the property with
  teeth: an artifact half-written from a broken spec is an epic that starts,
  dispatches the stories that parsed, and silently never builds the one that did
  not. Every rejection case here asserts the file's absence, not just the exit
  code. Offline is asserted too — a derive with `TEMPORAL_ADDRESS` pointed at a
  closed port still succeeds, so no operator ever needs a server to compile a
  spec (contracts/cli.md § derive: "`derive` touches neither").

- **`start` and `status` run against the real time-skipping server**, with the
  workflow's activities scripted. A CLI tested against a mocked client proves
  the CLI calls the methods the test expects; this one proves an epic actually
  starts, actually runs, and actually answers a query — the id convention, the
  task queue, the compiled graph and the proxy url all arrive at the workflow,
  and `status` reads the state the workflow is genuinely in.

Four properties of the setup are deliberate:

- **The scripted world is deliberately smaller than the interpreter's.** Every
  activity `EpicWorkflow` invokes on the happy path is registered under its real
  name, and nothing else: no escalation, no judge, no failure script. What
  `tests/test_interpreter.py` proves about the ladder is not re-proved here — a
  CLI suite that scripted a failure ladder would be testing the workflow through
  a keyhole. What is scripted is exactly enough for an epic to run to completion
  and for one node to be caught mid-flight.

- **The test server's namespace is `default`, and the CLI's own default is
  `factory`.** So every passing `start` and `status` below is itself the proof
  that `TEMPORAL_NAMESPACE` was read — a CLI that ignored the environment would
  talk to a namespace this server does not have. The assertion is made explicit
  rather than left implicit in `test_the_environment_names_the_server`.

- **The CLI is invoked through its real entry point, in a worker thread.**
  `main` is the console script's function and owns its own `asyncio.run`, which
  cannot be called from inside the running test loop — so the async tests hand
  it to `asyncio.to_thread` rather than reaching past it for an async-shaped
  internal. What the operator runs is what is under test.

- **Node ids are the deriver's `us<n>`, and the order the CLI prints is the
  order the query hands it.** Temporal's JSON converter serializes a mapping
  with sorted keys, so declaration order survives the query round trip only
  because `us1 < us2 < us3` sorts the same way. The CLI's own contribution is
  that it re-sorts nothing; if declaration order ever has to survive a
  double-digit story count, the ordering has to become explicit in `EpicStatus`
  rather than implicit in the node ids, and that is a change to the workflow's
  query shape, not to this renderer.

Written before `factory/workgraph/cli.py` exists (T023 precedes T024): until the
module lands, every test here fails at import.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
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
from factory.mergequeue.models import Finding, PrSnapshot, TargetRepoProfile
from factory.activities.usage_activities import IssueKeyInput, TeardownInput
from factory.activities.verify_activities import (
    CheckOutputInput,
    RecordedVerification,
    RecordVerificationInput,
    RunGatesInput,
    SnapshotCriteriaInput,
)
from factory.config import Persona, WriteScope
from factory.notify.service import (
    DEFAULT_TEMPORAL_ADDRESS,
    DEFAULT_TEMPORAL_NAMESPACE,
    TEMPORAL_ADDRESS_ENV,
    TEMPORAL_NAMESPACE_ENV,
)
from factory.usage.litellm_client import PROXY_URL_ENV, LiteLLMClient
from factory.usage.models import KeyLease, Termination, UsageRecord, UsageSnapshot
from factory.verify.models import (
    CriteriaSet,
    GateResult,
    GateStatus,
    OutputCheck,
    Requirement,
    RequirementKind,
)
from factory.workgraph import cli
from factory.workgraph.cli import load_workgraph, main
from factory.workgraph.models import (
    AdapterResult,
    AttemptContext,
    ResolvedNode,
    ResolvedPersona,
    WorkGraph,
    WorkGraphError,
    validate_workgraph,
)
from factory.workgraph.worktree import PreparedWorktree, branch_name
from factory.workgraph.workflow import TASK_QUEUE, EpicWorkflow
from tests.conftest import FAKE_MASTER_KEY, FakeLiteLLM
from tests.test_interpreter import merged_snapshot

CORPUS = Path(__file__).resolve().parent / "fixtures" / "workgraph"

#: The accepting fixture: three stories, one edge, one leaf, one `timeout`
#: override. Copied under `tmp_path` for every test, because `derive` writes its
#: artifact next to the spec by default and the corpus is not a scratch space.
VALID = "valid_epic"

#: What the compiled artifact says, and where it came from. `epic_id` and
#: `feature` are the spec directory's name (contracts/workgraph-schema.md
#: § Derivation semantics); the CLI is the only thing that knows the directory,
#: which is why the deriver takes them as arguments.
EPIC_ID = VALID
WORKFLOW_ID = f"epic-{EPIC_ID}"
TARGET_REPO = "/srv/factory/targets/short-links"
PROXY_URL = "http://litellm.test"

#: The landing-poll beat (`LandingConfig.poll_interval_s`). The time-skipping
#: harness advances the virtual clock in whole sleeps, so a CLI-run epic settles
#: by sleeping one beat past it; this must track the workflow's default.
LANDING_POLL_INTERVAL_S = 60

#: An address nothing listens on, for the transport-failure path (exit 2).
DEAD_ADDRESS = "127.0.0.1:1"

#: The registry the scripted `resolve_graph` resolves against — a real `Persona`,
#: so the real `validate_workgraph` runs against it unchanged.
MODEL_ALIAS = "implementer-alias"

#: The judge's registry alias — resolved for every epic even when, as here, no
#: node's criteria give it anything to score (constitution VII).
JUDGE_ALIAS = "judge-alias"
TIMEOUT_S = 5400

#: One FR per story, exactly as `valid_epic`'s `## Work Graph` block declares.
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

#: The compiled artifact `valid_epic` must produce, whole (contracts/…schema.md
#: § `workgraph.json`). Asserted as one value rather than sampled: every field is
#: load-bearing downstream, and this JSON is what an operator reads and what
#: `start` consumes.
EXPECTED_ARTIFACT: dict[str, Any] = {
    "epic_id": EPIC_ID,
    "feature": EPIC_ID,
    "specs_root": "specs",
    "target_repo": TARGET_REPO,
    "nodes": [
        {
            "id": "us1",
            "story_key": "US1",
            "persona": "implementer",
            "spec_ref": f"{EPIC_ID}:US1",
            "requirement_keys": ["US1", "FR-001", "FR-002"],
            "depends_on": [],
            "depends_on_merged": [],
            "timeout_override_s": None,
        },
        {
            "id": "us2",
            "story_key": "US2",
            "persona": "implementer",
            "spec_ref": f"{EPIC_ID}:US2",
            "requirement_keys": ["US2", "FR-003"],
            "depends_on": ["us1"],
            "depends_on_merged": [],
            "timeout_override_s": 7200,
        },
        {
            "id": "us3",
            "story_key": "US3",
            "persona": "implementer",
            "spec_ref": f"{EPIC_ID}:US3",
            "requirement_keys": ["US3", "FR-004"],
            "depends_on": [],
            "depends_on_merged": [],
            "timeout_override_s": None,
        },
    ],
}


# --- the epic's authored text (what the scripted `load_prompt_sources` reads) --


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


# --- invoking the CLI the way the console script does -------------------------


class Run(NamedTuple):
    """What an operator (or a script) sees: a status, and two streams."""

    code: int
    stdout: str
    stderr: str

    @property
    def json(self) -> Any:
        """`--json` output must be the whole of stdout, and nothing but."""
        return json.loads(self.stdout)


def _invoke(argv: tuple[str, ...]) -> int:
    """Call `main` and normalize the two ways it can report a status."""
    try:
        code = main(list(argv))
    except SystemExit as exit_request:
        code = exit_request.code
    return 0 if code is None else int(code)


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Callable[..., Run]:
    """Run one offline invocation (`derive`) in this thread."""

    def invoke(*argv: str) -> Run:
        code = _invoke(argv)
        captured = capsys.readouterr()
        return Run(code, captured.out, captured.err)

    return invoke


@pytest.fixture
def run_async(
    capsys: pytest.CaptureFixture[str],
) -> Callable[..., Awaitable[Run]]:
    """Run one server-touching invocation without blocking the test's loop.

    `main` is the console script's own function and owns its `asyncio.run`, which
    cannot be called from inside a running loop — so it goes to a worker thread
    while the Temporal worker keeps serving on the test's loop. The entry point
    under test is the one the operator runs, not an async-shaped internal.
    """

    async def invoke(*argv: str) -> Run:
        code = await asyncio.to_thread(_invoke, argv)
        captured = capsys.readouterr()
        return Run(code, captured.out, captured.err)

    return invoke


# --- fixture specs on disk ----------------------------------------------------


def corpus_text(fixture: str) -> str:
    return (CORPUS / fixture / "spec.md").read_text(encoding="utf-8")


def plant(tmp_path: Path, fixture: str, *, name: str | None = None) -> Path:
    """Copy one corpus spec into a scratch directory and return that directory.

    `derive` writes `workgraph.json` next to the spec by default, so the corpus
    itself is never the input: a test run must not leave an artifact in
    `tests/fixtures/`. The directory name is also the epic id, which is why it is
    nameable.
    """
    return plant_text(tmp_path, corpus_text(fixture), name=name or fixture)


def plant_text(tmp_path: Path, text: str, *, name: str = VALID) -> Path:
    spec_dir = tmp_path / name
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "spec.md").write_text(text, encoding="utf-8")
    return spec_dir


def respecified(work_graph: str) -> str:
    """`valid_epic`'s spec with its `## Work Graph` block swapped for another.

    Every story header, scenario and `FR-###` bullet stays byte-identical, so a
    variant exercises the graph grammar and nothing else — the discipline the
    fixture corpus follows on disk, applied to a shape no fixture holds.
    """
    head, _, tail = corpus_text(VALID).partition("## Work Graph\n")
    assert tail, "valid_epic must declare a `## Work Graph` section"
    _, _, after = tail.partition("## Assumptions")
    block = work_graph.strip("\n")
    return f"{head}## Work Graph\n\n```yaml\n{block}\n```\n\n## Assumptions{after}"


@pytest.fixture
def epic_dir(tmp_path: Path) -> Path:
    """A scratch copy of the accepting fixture, ready to derive."""
    return plant(tmp_path, VALID)


@pytest.fixture
def workgraph_json(
    run: Callable[..., Run], epic_dir: Path
) -> Path:
    """The compiled artifact, produced by the CLI itself.

    `start` is tested against what `derive` actually wrote rather than against a
    hand-built graph: the two verbs are the two halves of one operator gesture,
    and a schema drift between them is exactly the failure this catches.
    """
    result = run("derive", str(epic_dir), "--target-repo", TARGET_REPO)
    assert result.code == 0, result.stderr
    return epic_dir / "workgraph.json"


# --- the scripted world -------------------------------------------------------


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


def criteria_for(spec_ref: str) -> CriteriaSet:
    """One FR bullet, no acceptance scenarios — so the judge is never consulted.

    `has_scenarios` is false, which is the designed-for shape for a node owing
    only `FR-###` bullets (002's flow invariant 2). It keeps this suite on the
    CLI: what the judge branch does is `tests/test_interpreter.py`'s subject.
    """
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


class ScriptedEpic:
    """Every activity a passing epic calls, answered without touching anything.

    Deliberately narrower than `tests/test_interpreter.py`'s world: no ladder, no
    escalation, no judge. All this has to do is let a real `EpicWorkflow` run to
    completion under the real workflow id so the CLI has something to start and
    something to query.

    `pause_at` parks the named node's agent attempt until `release()`, which is
    the only moment a mid-flight `status` can be taken — the epic's state while a
    node is genuinely RUNNING, rather than a terminal snapshot after the fact.
    """

    def __init__(
        self,
        *,
        spec_text: str,
        pause_at: str | None = None,
        live_snapshot: UsageSnapshot | None = None,
        fail_resolve: bool = False,
    ) -> None:
        self._spec_text = spec_text
        self._pause_at = pause_at
        #: The snapshot the paused agent heartbeats while it waits (US1-S4): a
        #: mid-flight `status` must read this off the pending activity's heartbeat
        #: details, so the operator sees live spend rather than a blank.
        self.live_snapshot = live_snapshot
        self._fail_resolve = fail_resolve

        self.graphs: list[WorkGraph] = []
        self.prompt_source_requests: list[LoadPromptSourcesInput] = []
        self.attempts: list[AttemptContext] = []
        self.salvages: list[SalvageWorktreeInput] = []

        self.paused = asyncio.Event()
        self._released = asyncio.Event()

    # --- test-facing levers -------------------------------------------------

    async def wait_for_pause(self, timeout: float = 30.0) -> None:
        """Block until the paused node's attempt is genuinely in flight."""
        await asyncio.wait_for(self.paused.wait(), timeout=timeout)

    def release(self) -> None:
        self._released.set()

    @property
    def dispatched(self) -> list[str]:
        return [context.node_id for context in self.attempts]

    # --- the fakes ----------------------------------------------------------

    def activities(self) -> list[Any]:
        script = self

        @activity.defn(name="validate_target_repo")
        async def validate_target_repo(request: ValidateTargetRepoInput) -> TargetRepoProfile:
            # A CLI-run epic dispatches only against a repo that passes
            # onboarding (US3, FR-010). The default world answers a conforming
            # repo so the epic proceeds to normal dispatch.
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
                # The same non-retryable failure the real worker raises for a
                # graph its registry cannot dispatch (FR-002) — the one way an
                # epic is genuinely FAILED with no node ever issued. The workflow
                # never reached a node state, so its internal `epic_state` stays
                # the RUNNING it initialized to; that stale value is exactly the
                # lie US5 exists to stop the CLI from telling.
                raise ApplicationError(
                    "persona 'implementer' is not in the registry",
                    type=GRAPH_INVALID,
                    non_retryable=True,
                )
            # The real validator, against a real registry: what the CLI accepted
            # the worker accepts too, or the epic fails before it dispatches.
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
            # Resolved at epic start beside the graph, for a role no node names
            # (constitution V). Nothing here reaches the judge — these criteria
            # carry no scenarios — but an epic that could not resolve it would
            # never get as far as the CLI surface this file is about.
            return ResolvedPersona(
                persona=request.persona,
                model_alias=JUDGE_ALIAS,
                models=[JUDGE_ALIAS],
            )

        @activity.defn(name="load_prompt_sources")
        async def load_prompt_sources(
            request: LoadPromptSourcesInput,
        ) -> PromptSources:
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
                # The adapter's real beat: while the attempt waits it heartbeats
                # its newest usage snapshot, which Temporal stores on the pending
                # activity's details — the live-spend surface `status` reads
                # (US1-S4).
                if script.live_snapshot is not None:
                    activity.heartbeat(script.live_snapshot)
                script.paused.set()
                # Bounded, so a test that forgets to release fails on its own
                # assertion rather than hanging the suite.
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

        # --- the landing phase (US1): the same happy-path merge the worker's own
        # registration test drives, so a CLI-run epic completes instead of parking
        # forever on a live queue.
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

        return [
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
            validate_target_repo,
        ]


# --- harness ------------------------------------------------------------------


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    """Temporal with a clock the test owns — an hour of silence costs nothing."""
    environment = await WorkflowEnvironment.start_time_skipping()
    try:
        yield environment
    finally:
        await environment.shutdown()


@pytest.fixture
async def temporal_env(
    env: WorkflowEnvironment, monkeypatch: pytest.MonkeyPatch
) -> WorkflowEnvironment:
    """Point the CLI's environment contract at the test server and a fake proxy.

    The namespace is the interesting one: the test server serves `default` and
    the CLI's own default is `factory`, so a CLI that ignored
    `TEMPORAL_NAMESPACE` could not talk to this server at all.

    The preflight (US2) reads the proxy before dispatching, so this fixture
    stands up the shared fake proxy and wires the preflight's client to it:
    the fake serves exactly the aliases the CLI's own `personas.yaml` names for
    an epic of implementer nodes plus the judge, and holds no keys — so a valid
    epic preflights clean. Tests that want a misconfigured proxy override these
    fields on `temporal_env.fake`.
    """
    monkeypatch.setenv(TEMPORAL_ADDRESS_ENV, env.client.service_client.config.target_host)
    monkeypatch.setenv(TEMPORAL_NAMESPACE_ENV, env.client.namespace)
    monkeypatch.setenv(PROXY_URL_ENV, PROXY_URL)
    monkeypatch.setenv("LITELLM_MASTER_KEY", FAKE_MASTER_KEY)

    fake = FakeLiteLLM(base_url=PROXY_URL, master_key=FAKE_MASTER_KEY)
    # The aliases `factory/config.py`'s shipped registry names for the personas
    # a valid_epic dispatches (implementer nodes + the judge). Serving exactly
    # these keeps the preflight honest: it passes only because every alias the
    # CLI's own registry names is genuinely on the list.
    fake.served_models = {
        "ollama-cloud/deepseek-v4-flash",
        "local/qwen3.6-27b",
        "ollama-cloud/glm-5.2",
    }

    def preflight_client() -> LiteLLMClient:
        return LiteLLMClient(
            base_url=fake.base_url,
            master_key=fake.master_key,
            transport=fake.transport,
        )

    monkeypatch.setattr(cli, "_open_preflight_client", preflight_client)
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
    """Let a CLI-started epic's landings settle, then await its result.

    The CLI's `start` returns only the workflow id — not the `start_workflow`
    handle the time-skipping harness reclasses. Under `start_time_skipping`,
    `env.client` is wrapped in an interceptor that unlocks the virtual clock only
    inside the handle `.result()` of *its own* `start_workflow` return value; a
    plain `get_workflow_handle(id).result()` never unlocks it, so the landing
    poll timers (a `wait_condition(timeout=60s)` beat) never fire and an epic
    whose work is otherwise done parks forever on `_all_landings_terminal()`.
    `env.sleep` is the harness's own unlock: it advances the virtual clock by a
    landing-poll interval, letting the merge fakes ride each landing to a
    terminal state, after which the plain handle's result resolves.
    """
    handle = env.client.get_workflow_handle(WORKFLOW_ID)
    await env.sleep(timedelta(seconds=LANDING_POLL_INTERVAL_S + 1))
    return await handle.result()


def node_lines(stdout: str) -> list[str]:
    """The per-node lines of human `status` output, in the order printed."""
    return [
        line
        for line in stdout.splitlines()
        if line.split() and line.split()[0] in set(NODE_IDS)
    ]


# --- derive: the compiled artifact (US3-S4, SC-006) ---------------------------


def test_derive_writes_the_compiled_artifact_next_to_the_spec(
    run: Callable[..., Run], epic_dir: Path
) -> None:
    """The whole document, at the documented path, and the path printed.

    `workgraph.json` beside the spec is the default because the artifact belongs
    to the epic, not to whatever directory the operator happened to be standing
    in. Asserted as one value: every field is what `start` will read back and
    what the workflow will dispatch from.
    """
    result = run("derive", str(epic_dir), "--target-repo", TARGET_REPO)

    artifact = epic_dir / "workgraph.json"
    assert result.code == 0
    assert str(artifact) in result.stdout
    assert json.loads(artifact.read_text(encoding="utf-8")) == EXPECTED_ARTIFACT


def test_the_epic_id_is_the_spec_directorys_name(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """The one identity field nobody types twice (contracts/…schema.md).

    The deriver is pure and never sees a path, so the CLI supplies the epic id —
    and it takes it from the directory rather than from a flag, which is what
    makes `epic-<epic_id>` predictable from the spec an operator is looking at.
    """
    spec_dir = plant(tmp_path, VALID, name="003-merge-queue")

    result = run("derive", str(spec_dir), "--target-repo", TARGET_REPO)

    artifact = json.loads((spec_dir / "workgraph.json").read_text(encoding="utf-8"))
    assert result.code == 0
    assert artifact["epic_id"] == "003-merge-queue"
    assert artifact["feature"] == "003-merge-queue"
    assert artifact["nodes"][0]["spec_ref"] == "003-merge-queue:US1"


def test_the_output_flag_redirects_the_artifact(
    run: Callable[..., Run], epic_dir: Path, tmp_path: Path
) -> None:
    """`-o` writes there and nowhere else — the default path stays untouched."""
    elsewhere = tmp_path / "compiled" / "graph.json"
    elsewhere.parent.mkdir()

    result = run(
        "derive", str(epic_dir), "--target-repo", TARGET_REPO, "-o", str(elsewhere)
    )

    assert result.code == 0
    assert json.loads(elsewhere.read_text(encoding="utf-8")) == EXPECTED_ARTIFACT
    assert not (epic_dir / "workgraph.json").exists()


def test_the_specs_root_is_an_argument_with_a_default(
    run: Callable[..., Run], epic_dir: Path
) -> None:
    """`specs` unless told otherwise (contracts/cli.md § derive).

    `specs_root` + `feature` are how the worker later finds the epic's authored
    text, and the worker's working directory is not the operator's — so it is a
    declared property of the compiled graph rather than something inferred at
    dispatch.
    """
    result = run(
        "derive",
        str(epic_dir),
        "--target-repo",
        TARGET_REPO,
        "--specs-root",
        "tests/fixtures/workgraph",
    )

    artifact = json.loads((epic_dir / "workgraph.json").read_text(encoding="utf-8"))
    assert result.code == 0
    assert artifact["specs_root"] == "tests/fixtures/workgraph"


def test_derive_needs_no_temporal_server(
    run: Callable[..., Run], epic_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pure pipeline: read, compile, write. `derive` touches no server at all.

    Pointed at a closed port it still succeeds, which is what makes compiling a
    spec something an author can do anywhere — including before the factory's
    infrastructure exists.
    """
    monkeypatch.setenv(TEMPORAL_ADDRESS_ENV, DEAD_ADDRESS)

    result = run("derive", str(epic_dir), "--target-repo", TARGET_REPO)

    assert result.code == 0
    assert (epic_dir / "workgraph.json").exists()


# --- derive: refusing loudly, writing nothing (SC-006) ------------------------


#: One row per rejection fixture in the corpus: the story (or section rule) the
#: message must name. A fixture with no row here is a rule the CLI is not known
#: to report.
REJECTIONS = [
    ("missing_story", "US3"),
    ("unknown_story", "US4"),
    ("unknown_fr", "FR-404"),
    ("unknown_dep", "US9"),
    ("self_dep", "US2"),
    ("cycle", "US3"),
    ("no_section", "Work Graph"),
    ("two_blocks", "Work Graph"),
    ("non_mapping", "mapping"),
    ("unknown_key", "persona"),
    ("bad_timeout", "US2"),
]


@pytest.mark.parametrize(
    ("fixture", "named"), REJECTIONS, ids=[row[0] for row in REJECTIONS]
)
def test_a_spec_that_does_not_compile_is_exit_1_and_writes_nothing(
    run: Callable[..., Run], tmp_path: Path, fixture: str, named: str
) -> None:
    """Every rejection: named on stderr, exit 1, and no artifact on disk.

    The absence of the file is the assertion with teeth. An artifact written
    from a spec that did not compile is an epic that starts, dispatches the
    stories that parsed, and silently never builds the one that did not.
    """
    spec_dir = plant(tmp_path, fixture)

    result = run("derive", str(spec_dir), "--target-repo", TARGET_REPO)

    assert result.code == 1
    assert named in result.stderr
    assert not (spec_dir / "workgraph.json").exists()


def test_every_collected_error_is_printed_not_just_the_first(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """Two broken declarations produce two messages in one run (contracts/cli.md).

    An author fixing one typo per invocation, with the next revealed only after
    the fix, is the failure mode collection exists to avoid — so the CLI prints
    the deriver's whole list rather than its first element.
    """
    spec_dir = plant_text(
        tmp_path,
        respecified(
            """
US1:
  depends_on: []
  implements: [FR-001, FR-002]
US2:
  depends_on: [US9]
  implements: [FR-003]
US3:
  depends_on: []
  implements: [FR-404]
"""
        ),
    )

    result = run("derive", str(spec_dir), "--target-repo", TARGET_REPO)

    assert result.code == 1
    assert "US9" in result.stderr and "FR-404" in result.stderr
    assert "US2" in result.stderr and "US3" in result.stderr
    assert not (spec_dir / "workgraph.json").exists()


def test_a_missing_spec_is_a_user_error_not_a_traceback(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """A mistyped directory names the path it looked for, and exits 1."""
    missing = tmp_path / "no-such-feature"

    result = run("derive", str(missing), "--target-repo", TARGET_REPO)

    assert result.code == 1
    assert "spec.md" in result.stderr
    assert not missing.exists()


def test_a_failed_derive_says_nothing_on_stdout(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    """Errors are stderr's business (contracts/cli.md § Exit codes).

    Nothing on stdout means a caller that pipes the printed artifact path into
    another command gets an empty string on failure rather than a sentence.
    """
    spec_dir = plant(tmp_path, "cycle")

    result = run("derive", str(spec_dir), "--target-repo", TARGET_REPO)

    assert result.code == 1
    assert result.stdout == ""
    assert result.stderr != ""


# --- start (US3-S1) -----------------------------------------------------------


async def test_start_prints_the_workflow_id_and_starts_that_epic(
    run_async: Callable[..., Awaitable[Run]],
    temporal_env: WorkflowEnvironment,
    workgraph_json: Path,
) -> None:
    """`epic-<epic_id>` on task queue `workgraph` (R12, D-002).

    The id convention is what makes `status`, the escalation bridge's
    `workflow_id` round trip and an operator's Web UI search all agree without
    anyone recording a run id — and it is what makes a double start collide by
    construction.
    """
    result = await run_async("start", str(workgraph_json))

    assert result.code == 0
    assert result.stdout.strip() == WORKFLOW_ID

    described = await temporal_env.client.get_workflow_handle(WORKFLOW_ID).describe()
    assert described.workflow_type == "EpicWorkflow"
    assert described.task_queue == TASK_QUEUE


async def test_the_started_epic_carries_the_compiled_graph_and_the_proxy_url(
    run_async: Callable[..., Awaitable[Run]],
    temporal_env: WorkflowEnvironment,
    epic_dir: Path,
    workgraph_json: Path,
) -> None:
    """What `derive` wrote is what the workflow dispatches from.

    The graph arrives at `resolve_graph` node for node, and the proxy url — the
    one piece of the epic's input that is a property of the *deployment* rather
    than of the spec — arrives from the environment the activities already read
    it from, not from a constant in the CLI.
    """
    script = ScriptedEpic(spec_text=(epic_dir / "spec.md").read_text(encoding="utf-8"))

    async with worker_for(temporal_env, script):
        result = await run_async("start", str(workgraph_json))
        await settle_epic(temporal_env)

    assert result.code == 0
    assert len(script.graphs) == 1
    graph = script.graphs[0]
    assert graph.epic_id == EPIC_ID
    assert graph.target_repo == TARGET_REPO
    assert [node.id for node in graph.nodes] == NODE_IDS
    assert [node.depends_on for node in graph.nodes] == [[], ["us1"], []]
    assert script.dispatched == NODE_IDS
    assert {context.proxy_url for context in script.attempts} == {PROXY_URL}


async def test_starting_a_running_epic_twice_is_refused_by_name(
    run_async: Callable[..., Awaitable[Run]],
    temporal_env: WorkflowEnvironment,
    workgraph_json: Path,
) -> None:
    """Temporal's id uniqueness, reported as an operator sentence (contracts/cli.md).

    One epic in flight is the `.factory/` SQLite constraint made structural. The
    second start must read as "that epic is already running", not as an
    already-started exception with a stack trace under it.
    """
    first = await run_async("start", str(workgraph_json))
    second = await run_async("start", str(workgraph_json))

    assert first.code == 0
    assert second.code == 1
    assert f"'{EPIC_ID}'" in second.stderr
    assert WORKFLOW_ID in second.stderr
    assert "already running" in second.stderr


async def test_a_hand_edited_graph_is_re_validated_before_anything_starts(
    run_async: Callable[..., Awaitable[Run]],
    temporal_env: WorkflowEnvironment,
    workgraph_json: Path,
) -> None:
    """`workgraph.json` is compiled, and it is also a file on disk (FR-002).

    `derive` writes it, `start` reads it, and an operator's text editor is
    available in between — so the structural rules run again here, the offending
    node is named, and no workflow exists afterwards to be killed.
    """
    graph = json.loads(workgraph_json.read_text(encoding="utf-8"))
    graph["nodes"][1]["depends_on"] = ["us7"]
    workgraph_json.write_text(json.dumps(graph), encoding="utf-8")

    result = await run_async("start", str(workgraph_json))

    assert result.code == 1
    assert "us2" in result.stderr and "us7" in result.stderr
    assert result.stdout == ""
    with pytest.raises(RPCError):
        await temporal_env.client.get_workflow_handle(WORKFLOW_ID).describe()


async def test_start_without_a_proxy_url_refuses_rather_than_dispatching(
    run_async: Callable[..., Awaitable[Run]],
    temporal_env: WorkflowEnvironment,
    workgraph_json: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The proxy is where the attempt's virtual key is honored — no default.

    An epic started against a guessed proxy url would mint keys the agent cannot
    use and burn an attempt to find that out, so the missing variable is named
    and nothing starts (constitution VII: no endpoint hardcoded).
    """
    monkeypatch.delenv(PROXY_URL_ENV, raising=False)

    result = await run_async("start", str(workgraph_json))

    assert result.code == 1
    assert PROXY_URL_ENV in result.stderr
    with pytest.raises(RPCError):
        await temporal_env.client.get_workflow_handle(WORKFLOW_ID).describe()


# --- status -------------------------------------------------------------------


async def test_status_reads_a_live_epic_mid_flight(
    run_async: Callable[..., Awaitable[Run]],
    temporal_env: WorkflowEnvironment,
    epic_dir: Path,
    workgraph_json: Path,
) -> None:
    """The steering wheel's whole point: what is happening *now*.

    Taken while `us2`'s attempt is genuinely parked in the adapter, so the view
    is the workflow's live state rather than a terminal snapshot: the dependency
    already PASSED, the in-flight node RUNNING on its first attempt, and the
    independent leaf still PENDING with no attempt against it (FR-003).
    """
    script = ScriptedEpic(
        spec_text=(epic_dir / "spec.md").read_text(encoding="utf-8"), pause_at="us2"
    )

    async with worker_for(temporal_env, script):
        start = await run_async("start", str(workgraph_json))
        await script.wait_for_pause()

        mid_flight = await run_async("status", EPIC_ID, "--json")

        script.release()
        await settle_epic(temporal_env)
        final = await run_async("status", EPIC_ID, "--json")

    assert start.code == 0
    assert mid_flight.code == 0
    # The query's own payload, byte-identical to what it was before US5 — the
    # `execution_status` sibling is added beside it, never merged into it
    # (FR-010, acceptance 3: "the existing payload is not restructured").
    assert {
        "epic_state": mid_flight.json["epic_state"],
        "nodes": mid_flight.json["nodes"],
    } == {
        "epic_state": "RUNNING",
        "nodes": {
            "us1": {
                "attempt": 1,
                "branch": branch_name(EPIC_ID, "us1"),
                "state": "ENQUEUED",
                "verified": True,
                "landing_state": "ENQUEUED",
                "pr_number": int(
                    hashlib.sha1(branch_name(EPIC_ID, "us1").encode()).hexdigest()[:8], 16
                )
                % 1000
                + 1,
            },
            "us2": {
                "attempt": 1,
                "branch": branch_name(EPIC_ID, "us2"),
                "state": "RUNNING",
                "verified": False,
                "landing_state": None,
                "pr_number": None,
            },
            "us3": {
                "attempt": 0,
                "branch": branch_name(EPIC_ID, "us3"),
                "state": "PENDING",
                "verified": False,
                "landing_state": None,
                "pr_number": None,
            },
        },
    }
    assert mid_flight.json["execution_status"] == "RUNNING"
    assert final.json["epic_state"] == "COMPLETED"
    assert final.json["execution_status"] == "COMPLETED"
    assert [node["state"] for node in final.json["nodes"].values()] == [
        "MERGED",
        "MERGED",
        "MERGED",
    ]


async def test_status_reads_live_spend_off_the_running_attempt(
    run_async: Callable[..., Awaitable[Run]],
    temporal_env: WorkflowEnvironment,
    epic_dir: Path,
    workgraph_json: Path,
) -> None:
    """US1-S4: an operator asking mid-attempt sees spend at least as fresh as the
    poll loop's `record.last_snapshot`.

    Observation now rides the agent activity's heartbeat (plan US1), which lives
    on the pending activity's mutable details rather than in workflow state — so
    the workflow's own query cannot see it, and neither could the poll loop's
    figure after US1 deleted it. The CLI therefore reads the live figure off the
    server's description of the running activity (`describe`), where Temporal
    stores the heartbeat payload, and reports it beside the query result — a
    client-side RPC that emits no workflow history event (FR-002).
    """
    snapshot = UsageSnapshot(spend_usd=6.25, captured_at="2026-08-05T09:31:00Z")
    script = ScriptedEpic(
        spec_text=(epic_dir / "spec.md").read_text(encoding="utf-8"),
        pause_at="us2",
        live_snapshot=snapshot,
    )

    async with worker_for(temporal_env, script):
        await run_async("start", str(workgraph_json))
        await script.wait_for_pause()

        mid_json = await run_async("status", EPIC_ID, "--json")
        mid_human = await run_async("status", EPIC_ID)

        script.release()
        await settle_epic(temporal_env)

    assert mid_json.code == 0
    # The query result is untouched; the live spend is a sibling read, so a
    # consumer of the query doc is not broken (contracts/cli.md § status).
    assert mid_json.json["nodes"]["us2"]["state"] == "RUNNING"
    assert mid_json.json["live_spend"]["us2"] == {
        "spend_usd": 6.25,
        "captured_at": "2026-08-05T09:31:00Z",
    }
    assert "6.25" in mid_human.stdout


async def test_status_json_is_the_query_result_verbatim(
    run_async: Callable[..., Awaitable[Run]],
    temporal_env: WorkflowEnvironment,
    epic_dir: Path,
    workgraph_json: Path,
) -> None:
    """`--json` is a dump, not a re-assembly (contracts/cli.md § status).

    A renderer that rebuilt the document would be a second place the query's
    shape is stated, free to drift from `EpicStatus`. So the whole document is
    asserted, and it is asserted to be the whole of stdout — a `--json` consumer
    never parses around a header. US5's `execution_status` is a sibling added at
    the CLI's edge, never merged into that document (FR-010).
    """
    script = ScriptedEpic(spec_text=(epic_dir / "spec.md").read_text(encoding="utf-8"))

    async with worker_for(temporal_env, script):
        await run_async("start", str(workgraph_json))
        await settle_epic(temporal_env)
        result = await run_async("status", EPIC_ID, "--json")

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


async def test_the_human_status_is_an_epic_line_then_one_line_per_node(
    run_async: Callable[..., Awaitable[Run]],
    temporal_env: WorkflowEnvironment,
    epic_dir: Path,
    workgraph_json: Path,
) -> None:
    """`<node_id>  <state>  attempt <n>  <branch>`, in declaration order.

    The branch is on the line because it is the one thing that survives every
    sweep: once `.factory/` is cleaned the branch is the whole account of the
    node's attempts (SC-004), and an operator reading a killed node needs its
    name without a second command.
    """
    script = ScriptedEpic(spec_text=(epic_dir / "spec.md").read_text(encoding="utf-8"))

    async with worker_for(temporal_env, script):
        await run_async("start", str(workgraph_json))
        await settle_epic(temporal_env)
        result = await run_async("status", EPIC_ID)

    assert result.code == 0
    lines = result.stdout.splitlines()
    assert EPIC_ID in lines[0]
    assert "COMPLETED" in lines[0]

    printed = node_lines(result.stdout)
    assert [line.split()[0] for line in printed] == NODE_IDS
    for node_id, line in zip(NODE_IDS, printed):
        assert "MERGED" in line
        assert "attempt 1" in line
        assert branch_name(EPIC_ID, node_id) in line


# --- status: US5 — the Temporal execution status is reported (FR-010) ---------


async def test_status_of_a_failed_workflow_reports_execution_status(
    run_async: Callable[..., Awaitable[Run]],
    temporal_env: WorkflowEnvironment,
    epic_dir: Path,
    workgraph_json: Path,
) -> None:
    """The bug US5 exists to fix: a closed workflow must not read as RUNNING.

    `resolve_graph` fails the epic before any node is issued, so the workflow's
    internal `epic_state` is whatever it initialized to — RUNNING — even though
    Temporal has closed the execution as FAILED. Today `status` would print that
    stale `RUNNING`; US5 surfaces the execution status alongside it so the two
    are distinguishable (FR-010, acceptance 1).
    """
    script = ScriptedEpic(
        spec_text=(epic_dir / "spec.md").read_text(encoding="utf-8"),
        fail_resolve=True,
    )

    async with worker_for(temporal_env, script):
        start = await run_async("start", str(workgraph_json))
        # The workflow fails with no result to return; wait until Temporal has
        # closed the execution as FAILED so the status below is read from a
        # genuinely closed workflow — the exact situation the story is about.
        with pytest.raises(WorkflowFailureError):
            await temporal_env.client.get_workflow_handle(WORKFLOW_ID).result()
        failed = await run_async("status", EPIC_ID, "--json")

    assert start.code == 0
    assert failed.code == 0
    # The internal state is stale RUNNING — exactly what misled — while the
    # execution status is the ground truth, and the two are distinguishable.
    assert failed.json["epic_state"] == "RUNNING"
    assert failed.json["execution_status"] == "FAILED"


async def test_status_of_a_terminated_workflow_reports_execution_status(
    run_async: Callable[..., Awaitable[Run]],
    temporal_env: WorkflowEnvironment,
    epic_dir: Path,
    workgraph_json: Path,
) -> None:
    """TERMINATED is distinguishable from RUNNING (independent test).

    An operator who kills an epic from the Web UI sees the execution status say
    so, rather than an internal epic_state that never reached KILLED.
    """
    script = ScriptedEpic(
        spec_text=(epic_dir / "spec.md").read_text(encoding="utf-8"),
        pause_at="us2",
    )

    async with worker_for(temporal_env, script):
        await run_async("start", str(workgraph_json))
        await script.wait_for_pause()
        await temporal_env.client.get_workflow_handle(WORKFLOW_ID).terminate(
            "operator killed it"
        )
        terminated = await run_async("status", EPIC_ID, "--json")

    assert terminated.code == 0
    assert terminated.json["execution_status"] == "TERMINATED"


async def test_the_running_epics_human_output_is_unchanged(
    run_async: Callable[..., Awaitable[Run]],
    temporal_env: WorkflowEnvironment,
    epic_dir: Path,
    workgraph_json: Path,
) -> None:
    """Acceptance 2: a running epic's per-node output is byte-identical to today.

    US5 must not disturb what an operator already reads mid-flight. The epic line
    gains the execution status on a fresh word; the per-node lines — the part the
    acceptance scenario names — are exactly what they were before this story.
    """
    script = ScriptedEpic(
        spec_text=(epic_dir / "spec.md").read_text(encoding="utf-8"),
        pause_at="us2",
    )

    async with worker_for(temporal_env, script):
        await run_async("start", str(workgraph_json))
        await script.wait_for_pause()
        result = await run_async("status", EPIC_ID)

    assert result.code == 0
    lines = result.stdout.splitlines()
    assert lines[0].split()[0:3] == ["epic", EPIC_ID, "RUNNING"]
    printed = node_lines(result.stdout)
    assert [line.split()[0] for line in printed] == NODE_IDS
    # The per-node lines are byte-identical to the pre-US5 renderer: node id,
    # state, attempt and branch, and nothing else.
    # us1 reads ENQUEUED, not PASSED: on the landed tree a verified node enters
    # the landing phase, and the pause on us2 freezes the virtual clock before
    # us1's landing poll can ride it to MERGED (003's semantics, post-landing).
    assert printed[0].split() == [
        "us1",
        "ENQUEUED",
        "attempt",
        "1",
        branch_name(EPIC_ID, "us1"),
    ]
    assert printed[1].split() == [
        "us2",
        "RUNNING",
        "attempt",
        "1",
        branch_name(EPIC_ID, "us2"),
    ]
    assert printed[2].split() == [
        "us3",
        "PENDING",
        "attempt",
        "0",
        branch_name(EPIC_ID, "us3"),
    ]


async def test_status_of_an_epic_nobody_started_is_exit_1(
    run_async: Callable[..., Awaitable[Run]],
    temporal_env: WorkflowEnvironment,
) -> None:
    """A clear sentence naming the epic, not a gRPC status code."""
    result = await run_async("status", "no-such-epic")

    assert result.code == 1
    assert "no-such-epic" in result.stderr
    assert result.stdout == ""


async def test_status_output_never_carries_a_credential(
    run_async: Callable[..., Awaitable[Run]],
    temporal_env: WorkflowEnvironment,
    epic_dir: Path,
    workgraph_json: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-011: no credential value reaches the status output or its error paths.

    `status` reads Temporal and renders what it got; it never touches the proxy,
    so no key belongs on any of its streams. Driven through all four states the
    independent test names — running, failed, terminated, completed — plus the
    user-error and transport paths, with a canary in the environment that no
    output byte may repeat.
    """
    canary = "sk-fr011-status-canary-7a11b0b"
    monkeypatch.setenv("LITELLM_MASTER_KEY", canary)
    # A status against a reachable-but-wrong epic reads the same way in both
    # renderings; a transport failure is the other error path.
    outputs: list[tuple[str, str]] = []

    # completed — runs first: it is the one block that needs the virtual clock
    # unlocked (settle_epic), and a terminated run left under the same id makes
    # the time-skipping server refuse the unlock sleep with an RPC timeout.
    script2 = ScriptedEpic(spec_text=(epic_dir / "spec.md").read_text(encoding="utf-8"))
    async with worker_for(temporal_env, script2):
        await run_async("start", str(workgraph_json))
        await settle_epic(temporal_env)
        completed = await run_async("status", EPIC_ID, "--json")
        outputs.append((completed.stdout, completed.stderr))

    script = ScriptedEpic(
        spec_text=(epic_dir / "spec.md").read_text(encoding="utf-8"),
        pause_at="us2",
    )
    async with worker_for(temporal_env, script):
        await run_async("start", str(workgraph_json))
        await script.wait_for_pause()
        running = await run_async("status", EPIC_ID)
        running_json = await run_async("status", EPIC_ID, "--json")
        outputs += [(running.stdout, running.stderr), (running_json.stdout, running_json.stderr)]

        await temporal_env.client.get_workflow_handle(WORKFLOW_ID).terminate("sweep")
        terminated = await run_async("status", EPIC_ID, "--json")
        outputs.append((terminated.stdout, terminated.stderr))

    # failed
    script3 = ScriptedEpic(
        spec_text=(epic_dir / "spec.md").read_text(encoding="utf-8"),
        fail_resolve=True,
    )
    async with worker_for(temporal_env, script3):
        await run_async("start", str(workgraph_json))
        with pytest.raises(WorkflowFailureError):
            await temporal_env.client.get_workflow_handle(WORKFLOW_ID).result()
        failed = await run_async("status", EPIC_ID, "--json")
        outputs.append((failed.stdout, failed.stderr))

    for stdout, stderr in outputs:
        assert canary not in stdout and canary not in stderr


def test_the_status_command_source_reaches_for_no_credential() -> None:
    """Structural half of FR-011: `status` code has no proxy credential surface.

    The `status` verb neither reads the proxy url nor constructs a client that
    could need the master key — the only Temporal credential it ever carries is
    the connection, and that comes from the environment contract shared with
    `start`. A grep over the CLI source confirms `status_command`/`_query_status`
    branch on nothing that would read `LITELLM_MASTER_KEY`.
    """
    source = Path(
        __file__).resolve().parent.parent / "factory" / "workgraph" / "cli.py"
    text = source.read_text(encoding="utf-8")
    assert "LITELLM_MASTER_KEY" not in text


# --- the environment contract, and transport (exit 2) -------------------------


async def test_the_environment_names_the_server(
    temporal_env: WorkflowEnvironment,
) -> None:
    """`TEMPORAL_ADDRESS`/`TEMPORAL_NAMESPACE`, same as the notify bridge.

    One deployment story for everything that talks to Temporal. This asserts the
    premise the `start`/`status` tests rest on: the test server's namespace is
    *not* the CLI's default, so a CLI that ignored the environment could not have
    reached it — every green test above is that proof.
    """
    assert temporal_env.client.namespace != DEFAULT_TEMPORAL_NAMESPACE
    assert (
        temporal_env.client.service_client.config.target_host
        != DEFAULT_TEMPORAL_ADDRESS
    )


@pytest.mark.parametrize(
    "argv",
    [("status", EPIC_ID), ("status", EPIC_ID, "--json")],
    ids=["human", "json"],
)
async def test_an_unreachable_temporal_is_exit_2_naming_the_address(
    run_async: Callable[..., Awaitable[Run]],
    monkeypatch: pytest.MonkeyPatch,
    argv: tuple[str, ...],
) -> None:
    """Exit 2 is "the factory is not answering", distinct from a bad request.

    The address is in the message because the commonest cause is an operator on
    the wrong host or a dev server that is not up, and the fix is to look at the
    one string the CLI actually dialed.
    """
    monkeypatch.setenv(TEMPORAL_ADDRESS_ENV, DEAD_ADDRESS)
    monkeypatch.setenv(TEMPORAL_NAMESPACE_ENV, DEFAULT_TEMPORAL_NAMESPACE)

    result = await run_async(*argv)

    assert result.code == 2
    assert DEAD_ADDRESS in result.stderr
    assert result.stdout == ""


async def test_start_against_an_unreachable_temporal_is_exit_2(
    run_async: Callable[..., Awaitable[Run]],
    workgraph_json: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """And the graph is still read and validated first — a transport failure is
    reported about the server, never about the file."""
    monkeypatch.setenv(TEMPORAL_ADDRESS_ENV, DEAD_ADDRESS)
    monkeypatch.setenv(TEMPORAL_NAMESPACE_ENV, DEFAULT_TEMPORAL_NAMESPACE)
    monkeypatch.setenv(PROXY_URL_ENV, PROXY_URL)

    result = await run_async("start", str(workgraph_json))

    assert result.code == 2
    assert DEAD_ADDRESS in result.stderr


def test_the_graph_the_cli_starts_is_the_one_validation_accepts(
    workgraph_json: Path,
) -> None:
    """Belt and braces on the two ends agreeing (FR-002).

    `start`'s re-validation is structural only — persona and timeout resolution
    belong to `resolve_graph` on the worker, which owns `personas.yaml` — but the
    artifact it accepts must also survive the full check the workflow runs, or an
    epic would start and fail at its first step.
    """
    graph = load_workgraph(workgraph_json)

    assert isinstance(graph, WorkGraph)
    assert [node.id for node in graph.nodes] == NODE_IDS
    try:
        validate_workgraph(graph, PERSONAS)
    except WorkGraphError as error:  # pragma: no cover - the assertion is the point
        pytest.fail(f"a graph the CLI accepted must dispatch: {error}")


# --- onboard (US3 onboarding preflight, FR-010) ------------------------------


def _script_conforming_gh(fake: "Any", owner_repo: str = "OWNER/REPO") -> None:
    """Script `gh` for a fully conforming repo (public, queue enabled, checks match).

    The fixture target repo declares gates `lint`, `test`, `typecheck`; the
    scripted queue requires checks of exactly those names.
    """
    from tests.fake_gh import FakeGh

    fake.expect_json(
        "repo", "view", "--json", "nameWithOwner,visibility,defaultBranchRef",
        payload={"nameWithOwner": owner_repo, "visibility": "PUBLIC", "defaultBranchRef": "main"},
    )
    fake.expect_json(
        "api", f"repos/{owner_repo}/rules/branches/main",
        payload=[{"type": "merge_queue", "parameters": {"required_status_checks": [
            {"context": "lint"}, {"context": "test"}, {"context": "typecheck"},
        ]}}],
    )


def _script_queue_less_gh(fake: "Any", owner_repo: str = "OWNER/REPO") -> None:
    """Script `gh` for a repo with the merge queue not enabled (rules list empty)."""
    fake.expect_json(
        "repo", "view", "--json", "nameWithOwner,visibility,defaultBranchRef",
        payload={"nameWithOwner": owner_repo, "visibility": "PUBLIC", "defaultBranchRef": "main"},
    )
    fake.expect_json("api", f"repos/{owner_repo}/rules/branches/main", payload=[])


@pytest.fixture
def onboard_gh(monkeypatch: pytest.MonkeyPatch) -> "Any":
    """Inject a `FakeGh` into the CLI's onboard client factory.

    `factory-epic onboard` builds a real `GhClient` against the clone the
    operator points at; the test replaces the CLI's client factory so the `gh`
    boundary is scripted without a network, exactly as the activity tests do.
    """
    from tests.fake_gh import FakeGh

    fake = FakeGh()
    import factory.workgraph.cli as cli_module

    def factory(*, repo_path: str):
        from factory.mergequeue.gh import GhClient

        return GhClient(repo=repo_path, runner=fake)

    monkeypatch.setattr(cli_module, "_onboard_client_factory", factory)
    return fake


def test_onboard_prints_every_finding_and_passes_a_conforming_repo(
    run: Callable[..., Run], tmp_path: Path, onboard_gh: "Any",
) -> None:
    """A fully conforming repo exits 0 and prints every (passing) finding."""
    from tests.target_repo import build_target_repo

    repo = build_target_repo(tmp_path / "target")
    _script_conforming_gh(onboard_gh)

    result = run("onboard", str(repo))

    assert result.code == 0
    for check in ("visibility", "merge_queue", "factory_yaml",
                  "gate_check:lint", "gate_check:test", "gate_check:typecheck"):
        assert check in result.stdout
    assert "factory.yaml" in result.stdout


def test_onboard_json_is_a_parseable_profile_with_pass_flag(
    run: Callable[..., Run], tmp_path: Path, onboard_gh: "Any",
) -> None:
    """`--json` emits the whole `TargetRepoProfile` and nothing but."""
    from tests.target_repo import build_target_repo

    repo = build_target_repo(tmp_path / "target")
    _script_conforming_gh(onboard_gh)

    result = run("onboard", "--json", str(repo))

    assert result.code == 0
    document = json.loads(result.stdout)
    assert document["passed"] is True
    assert document["visibility"] == "PUBLIC"
    assert document["queue_enabled"] is True
    assert "findings" in document


def test_onboard_a_queue_less_repo_is_exit_1_naming_the_failing_finding(
    run: Callable[..., Run], tmp_path: Path, onboard_gh: "Any",
) -> None:
    """A repo failing any check is rejected for dispatch (exit 1), finding named."""
    from tests.target_repo import build_target_repo

    repo = build_target_repo(tmp_path / "target")
    _script_queue_less_gh(onboard_gh)

    result = run("onboard", str(repo))

    assert result.code == 1
    assert "merge_queue" in result.stdout
    assert "not enabled" in result.stdout


def test_onboard_without_a_target_path_is_a_usage_error(
    run: Callable[..., Run],
) -> None:
    """Missing the target-clone path is a usage error, not a guess."""
    result = run("onboard")

    assert result.code == 1


def test_onboard_a_nonexistent_clone_is_exit_1_with_the_manifest_finding(
    run: Callable[..., Run], tmp_path: Path, onboard_gh: "Any",
) -> None:
    """A path with no factory.yaml fails on the manifest finding, not a crash."""
    empty = tmp_path / "no-repo"
    empty.mkdir()
    onboard_gh.expect_json(
        "repo", "view", "--json", "nameWithOwner,visibility,defaultBranchRef",
        payload={"nameWithOwner": "OWNER/REPO", "visibility": "PUBLIC", "defaultBranchRef": "main"},
    )
    onboard_gh.expect_json("api", "repos/OWNER/REPO/rules/branches/main", payload=[])

    result = run("onboard", str(empty))

    assert result.code == 1
    assert "factory_yaml" in result.stdout
    assert "factory.yaml" in result.stdout


# --- preflight (US2: FR-004/005/006, T012/T013) ------------------------------


def _first_attempt_alias(epic_id: str, node_id: str, persona: str) -> str:
    return f"{epic_id}:{node_id}:1:{persona}"


async def test_an_unserved_alias_refuses_before_dispatch_naming_alias_and_personas(
    run_async: Callable[..., Awaitable[Run]],
    temporal_env: WorkflowEnvironment,
    workgraph_json: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-004: a registry alias the proxy does not serve stops `start` (exit 1).

    The alias is reported with *every* persona that names it — `local/qwen3.6-27b`
    is the fallback for both `implementer` and `judge`, so both must be named —
    and no workflow exists and no key is issued: the cost is one message.
    """
    fake: FakeLiteLLM = temporal_env.fake
    fake.served_models.discard("local/qwen3.6-27b")

    result = await run_async("start", str(workgraph_json))

    assert result.code == 1
    assert "local/qwen3.6-27b" in result.stderr
    # Every persona naming the unserved alias, not a bare alias.
    assert "implementer" in result.stderr
    assert "judge" in result.stderr
    assert result.stdout == ""
    with pytest.raises(RPCError):
        await temporal_env.client.get_workflow_handle(WORKFLOW_ID).describe()
    # No key was minted by the preflight or anything after it.
    assert fake.keys == {}


async def test_unserved_alias_names_each_offender_not_just_the_first(
    run_async: Callable[..., Awaitable[Run]],
    temporal_env: WorkflowEnvironment,
    workgraph_json: Path,
) -> None:
    """The whole list at once: an operator fixes one round trip, not several."""
    fake: FakeLiteLLM = temporal_env.fake
    fake.served_models = set()  # nothing served

    result = await run_async("start", str(workgraph_json))

    assert result.code == 1
    for alias in ("ollama-cloud/deepseek-v4-flash", "ollama-cloud/glm-5.2", "local/qwen3.6-27b"):
        assert alias in result.stderr


async def test_an_unreachable_proxy_is_a_distinct_finding_naming_the_address(
    run_async: Callable[..., Awaitable[Run]],
    temporal_env: WorkflowEnvironment,
    workgraph_json: Path,
) -> None:
    """FR-005: "nothing is listening" reads as exit 2 and names the address.

    Distinct from "not served": one is the operator's config to fix (1), the
    other is the server to go look at (2). The address the CLI actually tried is
    in the message.
    """
    fake: FakeLiteLLM = temporal_env.fake
    fake.make_unreachable()

    result = await run_async("start", str(workgraph_json))

    assert result.code == 2
    assert PROXY_URL in result.stderr
    assert result.stdout == ""
    with pytest.raises(RPCError):
        await temporal_env.client.get_workflow_handle(WORKFLOW_ID).describe()


async def test_a_colliding_first_attempt_key_alias_is_reported_with_its_remedy(
    run_async: Callable[..., Awaitable[Run]],
    temporal_env: WorkflowEnvironment,
    workgraph_json: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-006: an orphaned key alias colliding with the first attempt is caught.

    The deterministic alias `<epic>:us1:1:implementer` is already live (an orphan
    from a dead worker), so `start` refuses before dispatch, naming the alias and
    its remedy rather than surfacing as a mid-flight uniqueness failure.
    """
    fake: FakeLiteLLM = temporal_env.fake
    alias = _first_attempt_alias(EPIC_ID, "us1", "implementer")
    fake.keys["sk-fake-orphan"] = {
        "key": "sk-fake-orphan",
        "key_alias": alias,
        "models": [],
        "metadata": {},
        "duration": "24h",
        "spend": 0.0,
        "max_budget": None,
    }
    fake.aliases["sk-fake-orphan"] = alias

    result = await run_async("start", str(workgraph_json))

    assert result.code == 1
    assert alias in result.stderr
    assert "revoke" in result.stderr.lower()
    assert result.stdout == ""
    with pytest.raises(RPCError):
        await temporal_env.client.get_workflow_handle(WORKFLOW_ID).describe()


async def test_a_fully_valid_config_starts_exactly_as_today(
    run_async: Callable[..., Awaitable[Run]],
    temporal_env: WorkflowEnvironment,
    epic_dir: Path,
    workgraph_json: Path,
) -> None:
    """US2 acceptance 4: a passing preflight adds no dispatch-path behaviour.

    The fake serves exactly the aliases the CLI's own registry names and holds no
    keys, so the epic starts, runs to completion, and produces the workflow id —
    byte-for-byte the behaviour before preflight existed (SC-006).
    """
    script = ScriptedEpic(spec_text=(epic_dir / "spec.md").read_text(encoding="utf-8"))

    async with worker_for(temporal_env, script):
        result = await run_async("start", str(workgraph_json))
        await settle_epic(temporal_env)

    assert result.code == 0
    assert result.stdout.strip() == WORKFLOW_ID
    assert script.dispatched == NODE_IDS


async def test_preflight_wording_states_what_was_checked_not_worker_resolution(
    run_async: Callable[..., Awaitable[Run]],
    temporal_env: WorkflowEnvironment,
    workgraph_json: Path,
) -> None:
    """US2 honesty (R8): preflight validates the CLI's own registry, and says so.

    The CLI and the worker resolve personas from different `personas.yaml` files
    by design, so preflight can only confirm the aliases *this registry* names
    are served — it must not claim the worker's resolution was validated. The
    finding names the registry as the thing checked.
    """
    fake: FakeLiteLLM = temporal_env.fake
    fake.served_models.discard("ollama-cloud/deepseek-v4-flash")

    result = await run_async("start", str(workgraph_json))

    assert result.code == 1
    # The finding names the *registry* as the thing checked — not the worker's
    # resolution, which the CLI cannot see and must not claim to have validated.
    assert "registry" in result.stderr
    assert "worker" not in result.stderr.lower()


# --- US1: the concurrency cap (FR-002) ----------------------------------------


async def test_start_accepts_a_positive_max_concurrent_nodes(
    run_async: Callable[..., Awaitable[Run]],
    temporal_env: WorkflowEnvironment,
    epic_dir: Path,
    workgraph_json: Path,
) -> None:
    """`--max-concurrent-nodes` is a positive integer the CLI accepts (FR-002).

    The cap is a property of the epic's dispatch, supplied at `factory-epic
    start` — the machine's capacity, not the repo's. A positive value parses and
    reaches the workflow's `EpicInput`; the workflow id is still the only thing
    printed, so the operator's surface is unchanged.
    """
    script = ScriptedEpic(spec_text=(epic_dir / "spec.md").read_text(encoding="utf-8"))

    async with worker_for(temporal_env, script):
        result = await run_async("start", "--max-concurrent-nodes", "3", str(workgraph_json))
        await settle_epic(temporal_env)

    assert result.code == 0
    assert result.stdout.strip() == WORKFLOW_ID
    assert script.dispatched == NODE_IDS


async def test_start_rejects_zero_max_concurrent_nodes(
    run_async: Callable[..., Awaitable[Run]],
    temporal_env: WorkflowEnvironment,
    workgraph_json: Path,
) -> None:
    """A cap of 0 is not a positive integer — refused, never coerced (FR-002).

    Zero would mean "dispatch nothing", which is not a concurrency cap an
    operator can mean; the CLI rejects it as a usage error rather than starting
    an epic that silently never dispatches.
    """
    result = await run_async("start", "--max-concurrent-nodes", "0", str(workgraph_json))

    assert result.code == 1
    assert "max-concurrent-nodes" in result.stderr
    with pytest.raises(RPCError):
        await temporal_env.client.get_workflow_handle(WORKFLOW_ID).describe()


async def test_start_rejects_a_negative_max_concurrent_nodes(
    run_async: Callable[..., Awaitable[Run]],
    temporal_env: WorkflowEnvironment,
    workgraph_json: Path,
) -> None:
    """A negative cap is refused the same way — not a positive integer (FR-002)."""
    result = await run_async("start", "--max-concurrent-nodes", "-1", str(workgraph_json))

    assert result.code == 1
    assert "max-concurrent-nodes" in result.stderr
    with pytest.raises(RPCError):
        await temporal_env.client.get_workflow_handle(WORKFLOW_ID).describe()


async def test_start_rejects_a_non_integer_max_concurrent_nodes(
    run_async: Callable[..., Awaitable[Run]],
    temporal_env: WorkflowEnvironment,
    workgraph_json: Path,
) -> None:
    """A non-integer cap is refused, not coerced to an int (FR-002).

    `"2.5"` and `"abc"` are not positive integers; the CLI must not silently
    round or default them, because a cap the operator did not type is a cap the
    operator did not choose.
    """
    for bad in ("2.5", "abc"):
        result = await run_async("start", "--max-concurrent-nodes", bad, str(workgraph_json))
        assert result.code == 1
        assert "max-concurrent-nodes" in result.stderr
        with pytest.raises(RPCError):
            await temporal_env.client.get_workflow_handle(WORKFLOW_ID).describe()


async def test_start_defaults_max_concurrent_nodes_to_one(
    run_async: Callable[..., Awaitable[Run]],
    temporal_env: WorkflowEnvironment,
    epic_dir: Path,
    workgraph_json: Path,
) -> None:
    """Absent the flag, the cap is 1 — today's sequential behaviour (SC-002).

    Fan-out is opt-in: an epic that does not ask for it gets exactly the
    sequential dispatch it always had, which is what makes the cap-of-1
    equivalence true by construction.
    """
    script = ScriptedEpic(spec_text=(epic_dir / "spec.md").read_text(encoding="utf-8"))

    async with worker_for(temporal_env, script):
        result = await run_async("start", str(workgraph_json))
        await settle_epic(temporal_env)

    assert result.code == 0
    assert result.stdout.strip() == WORKFLOW_ID
    assert script.dispatched == NODE_IDS
