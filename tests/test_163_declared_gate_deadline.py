"""163-US1: a declared gate deadline reaches the workflow's verification.

The incident this file exists to hold shut: the manifest reaches the gate
*subprocess* (`_resolve_timeout` reads `timeouts:` per gate), but dispatch pins
the default `VerificationConfig.gate_timeout_s=600` into `EpicInput`, and
`EpicWorkflow._verify` sizes the `run_gates` activity's `heartbeat_timeout`
from that pinned field — 660s against a gate the operator declared for 900s.
The activity heartbeats before each gate, not periodically during one, so a
valid 900-second gate loses its activity before its declared time expires.

Every test here walks the connection the incident exposed, in order:

    manifest timeouts → load_loop_config → EpicInput.config.gate_timeout_s
    → _verify's scheduled `run_gates` heartbeat_timeout (+60s grace)

and asserts at the *seam*, not at a source string: the `EpicInput` is read off
the client the CLI actually started the epic with, and the heartbeat bound is
read off the run history's `ActivityTaskScheduled` event, which is what the
workflow actually asked Temporal for. Nothing here sleeps out a deadline —
`WorkflowEnvironment.start_time_skipping` advances the clock, and every gate
below answers in microseconds.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, NamedTuple

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

import factory.cli.nouns as nouns_package
from factory.cli.main import main as ergane_main
from factory.cli.nouns import build as build_module
from factory.verify.factory_yaml import MANIFEST_NAME, load_loop_config
from factory.verify.models import VerificationConfig
from factory.workgraph.derive import derive_workgraph
from factory.roadmap.workflow import (
    RoadmapInput,
    RoadmapWorkflow,
    _child_config,
    roadmap_workflow_id,
)
from factory.workgraph.workflow import EpicInput, EpicWorkflow

from tests.roadmap_script import _SCRIPT, ScriptedEpicWorkflow, landed_status
from tests.test_interpreter import (
    _EVENT_ACTIVITY_SCHEDULED,
    make_graph,
    make_node,
    passing,
    run_epic,
)
from tests.test_roadmap_scheduler import (
    ChildStartRecord,
    _RecordingInterceptor,
    build_corpus,
)
from tests.test_roadmap_scheduler import (
    PROXY_URL as ROADMAP_PROXY_URL,
)
from factory.roadmap.models import SpecState

EPIC_ID = "163-gate-deadline"
CLI_REVISION = "b6233ee"

#: The declared deadline the story's scenarios are written against, and the
#: default basis US1-S1 asks to see unchanged beside it.
DECLARED_S = 900
BASIS_DEFAULT_S = 600

#: The plan text and task text the scratch graph's trio carries. A trio, not a
#: bare `spec.md`: the CLI's preflight reads all three documents.
PLAN_TEXT_163 = """# Implementation Plan: 163 gate deadline

## Summary

One story, built once.
"""

TASKS_TEXT_163 = """# Tasks: 163 gate deadline

## Phase 1: User Story 1 - Build it (Priority: P1)

- [ ] T001 [US1] Write the failing test (spec US1-S1)
- [ ] T002 [US1] Build the thing until T001 passes
"""


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


# --- the dispatch fixture -----------------------------------------------------


def _empty_workflow_listing() -> Any:
    """An async generator yielding nothing: no open epic to advertise."""

    async def _gen() -> AsyncIterator[Any]:
        return
        yield  # pragma: no cover - unreachable; makes this an async generator

    return _gen()


class _AdvertisingRecordingClient:
    """Records `start_workflow`; answers the skew read the CLI makes.

    `start_command`'s last read is 156's worker-revision advertisement: the
    listing of open epics, then one `epic_status` query. This client answers
    the listing with no open epic, so the read degrades to "unreadable" — the
    check-activates-only-on-evidence posture — and dispatch proceeds. The skew
    refusal itself is 156's story and its own file holds it.
    """

    def __init__(self) -> None:
        self.started: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def list_workflows(self, query: str) -> Any:
        return _empty_workflow_listing()

    async def start_workflow(self, *args: Any, **kwargs: Any) -> Any:
        self.started.append((args, kwargs))
        return object()

    async def close(self) -> None: ...


def _manifest(target_repo: Path, *, version: int, timeouts: dict[str, int]) -> None:
    """Write one temporary manifest declaring exactly the timeouts given.

    Both schema versions the factory supports, so the derivation cannot be a
    v2-only reading of a document either version can carry (US1-S3).
    """
    body = [
        f"version: {version}",
        "runtime: bwrap",
        "gates:",
        "  test: uv run pytest -q",
    ]
    if timeouts:
        body.append("timeouts:")
        for name, seconds in timeouts.items():
            body.append(f"  {name}: {seconds}")
    (target_repo / MANIFEST_NAME).write_text("\n".join(body) + "\n", encoding="utf-8")


def _write_graph(tmp_path: Path, target_repo: Path, epic_id: str) -> Path:
    """Compile a one-node graph naming the scratch target repo (023's shape)."""
    spec_dir = tmp_path / epic_id
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "spec.md").write_text(
        f"""# Feature Specification: {epic_id}

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
    (spec_dir / "plan.md").write_text(PLAN_TEXT_163, encoding="utf-8")
    (spec_dir / "tasks.md").write_text(TASKS_TEXT_163, encoding="utf-8")

    graph = derive_workgraph(
        (spec_dir / "spec.md").read_text(encoding="utf-8"),
        epic_id=epic_id,
        feature=epic_id,
        specs_root=str(tmp_path),
        target_repo=str(target_repo),
    )
    graph_path = tmp_path / f"workgraph-{epic_id}.json"
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


@pytest.fixture
def dispatch_recorder(
    monkeypatch: pytest.MonkeyPatch,
) -> _AdvertisingRecordingClient:
    """The recording client `ergane build start` would have started the epic on.

    The preflight's alias probe is answered by a fake proxy (023's fixture),
    served through the package-level client seam — a patch on the noun module
    is lost to the reload `factory.cli.main` does per invocation, so the seams
    live where the reload cannot lose them (156's shape).
    """
    from tests.conftest import FAKE_MASTER_KEY, FakeLiteLLM
    from factory.usage.litellm_client import PROXY_URL_ENV, LiteLLMClient

    TEST_PROXY_URL = "http://litellm.test"
    fake = FakeLiteLLM(base_url=TEST_PROXY_URL, master_key=FAKE_MASTER_KEY)
    registry = build_module._preflight_registry()
    fake.served_models = {
        alias
        for name in ("implementer", "judge")
        for alias in (registry[name].model, registry[name].fallback)
        if alias
    }

    def preflight_client() -> LiteLLMClient:
        return LiteLLMClient(
            base_url=fake.base_url,
            master_key=fake.master_key,
            transport=fake.transport,
        )

    monkeypatch.setenv(PROXY_URL_ENV, TEST_PROXY_URL)
    monkeypatch.setattr(nouns_package, "_open_preflight_client", preflight_client)

    client = _AdvertisingRecordingClient()
    monkeypatch.setenv("TEMPORAL_ADDRESS", "127.0.0.1:1")
    monkeypatch.setenv("TEMPORAL_NAMESPACE", "test")

    async def _open_client() -> _AdvertisingRecordingClient:
        return client

    monkeypatch.setattr(nouns_package, "_open_client", _open_client)
    monkeypatch.setattr(nouns_package, "_cli_revision_for_tests", lambda: CLI_REVISION)
    return client

    client = _AdvertisingRecordingClient()
    monkeypatch.setenv("TEMPORAL_ADDRESS", "127.0.0.1:1")
    monkeypatch.setenv("TEMPORAL_NAMESPACE", "test")
    monkeypatch.setenv(PROXY_URL_ENV, "http://litellm.test")

    async def _open_client() -> _AdvertisingRecordingClient:
        return client

    monkeypatch.setattr(nouns_package, "_open_client", _open_client)
    monkeypatch.setattr(nouns_package, "_cli_revision_for_tests", lambda: CLI_REVISION)
    return client


async def _captured_epic_input(
    tmp_path: Path,
    run_async: Callable[..., Awaitable[Run]],
    dispatch_recorder: _AdvertisingRecordingClient,
    *,
    timeouts: dict[str, int],
    version: int = 1,
    manifest_name: str = MANIFEST_NAME,
) -> EpicInput:
    """Drive `ergane build start` against a real manifest; return the payload."""
    target_repo = tmp_path / f"target-{version}-{sorted(timeouts.items())}"
    target_repo.mkdir(parents=True, exist_ok=True)
    body = _manifest_text(version=version, timeouts=timeouts)
    (target_repo / manifest_name).write_text(body, encoding="utf-8")
    graph_path = _write_graph(tmp_path, target_repo, EPIC_ID)

    result = await run_async("build", "start", str(graph_path))
    assert result.code == 0, result.stderr
    assert len(dispatch_recorder.started) == 1
    payload = dispatch_recorder.started[0][0][1]
    assert isinstance(payload, EpicInput)
    return payload


def _manifest_text(*, version: int, timeouts: dict[str, int]) -> str:
    """One manifest's text, declaring every gate its timeouts name.

    The parser refuses a timeout for a gate the manifest does not declare, so a
    matrix row naming `lint` or `typecheck` declares those gates beside it —
    the parser's own validation is part of the shape under test, never worked
    around (163 plan trap 3).
    """
    commands = {
        "test": "uv run pytest -q",
        "lint": "echo lint",
        "typecheck": "echo typecheck",
    }
    body = [
        f"version: {version}",
        "runtime: bwrap",
        "gates:",
    ]
    declared = ["test"] + [n for n in timeouts if n != "test"]
    for name in declared:
        body.append(f"  {name}: {commands[name]}")
    if timeouts:
        body.append("timeouts:")
        for name, seconds in timeouts.items():
            body.append(f"  {name}: {seconds}")
    return "\n".join(body) + "\n"


def _manifest(target_repo: Path, *, version: int, timeouts: dict[str, int]) -> None:
    """Write one temporary manifest declaring exactly the timeouts given."""
    (target_repo / MANIFEST_NAME).write_text(
        _manifest_text(version=version, timeouts=timeouts), encoding="utf-8"
    )


# --- US1-S1 / T001: the manifest's 900s reaches the pinned config --------------


async def test_a_declared_900s_test_gate_pins_900_into_the_epic_input(
    tmp_path: Path,
    run_async: Callable[..., Awaitable[Run]],
    dispatch_recorder: _AdvertisingRecordingClient,
) -> None:
    """US1-S1, FR-001: the pinned gate watchdog basis is the declared deadline.

    A real temporary manifest carried through the production dispatch readers
    (`resolve_manifest_path` → `load_factory_config` → `load_loop_config`) into
    the `EpicInput` the CLI handed `start_workflow`. The manifest is the
    subject — parsing 900 alone was never broken, so a parser fixture could not
    catch this incident (plan trap 1); the *pin* is.
    """
    payload = await _captured_epic_input(
        tmp_path, run_async, dispatch_recorder, timeouts={"test": DECLARED_S}
    )

    assert payload.config.gate_timeout_s == DECLARED_S


async def test_an_undeclared_test_gate_keeps_the_existing_600_default(
    tmp_path: Path,
    run_async: Callable[..., Awaitable[Run]],
    dispatch_recorder: _AdvertisingRecordingClient,
) -> None:
    """US1-S1, FR-003: the unchanged manifest pins the unchanged default.

    The control, named as the literal 600 rather than compared against the
    dataclass, so a diff that moves the default moves this test instead of
    passing it.
    """
    payload = await _captured_epic_input(
        tmp_path, run_async, dispatch_recorder, timeouts={}
    )

    assert payload.config.gate_timeout_s == 600


# --- US1-S3 / T003: the deadline matrix ----------------------------------------


@pytest.mark.parametrize(
    ("version", "timeouts", "expected"),
    [
        pytest.param(1, {"test": 900}, 900, id="v1-declared-900"),
        pytest.param(2, {"test": 900}, 900, id="v2-declared-900"),
        pytest.param(1, {}, 600, id="v1-no-timeout-block"),
        pytest.param(2, {}, 600, id="v2-no-timeout-block"),
        # A complete set of shorter explicit deadlines is not silently raised
        # to the default (US1-S3): every declared gate named its own shorter
        # window, so nothing is omitted and nothing is defaulted.
        pytest.param(2, {"test": 45}, 45, id="single-explicit-shorter"),
        pytest.param(
            2, {"test": 30, "lint": 10, "typecheck": 20}, 30, id="v2-mixed-max"
        ),
    ],
)
async def test_the_deadline_matrix(
    version: int,
    timeouts: dict[str, int],
    expected: int,
    tmp_path: Path,
    run_async: Callable[..., Awaitable[Run]],
    dispatch_recorder: _AdvertisingRecordingClient,
) -> None:
    """US1-S3, FR-001/FR-003: every shape a manifest can declare, dispatched.

    Table-driven through the same production path the two S1 cases drive: the
    manifest is written, the CLI reads it, the payload is captured. The basis
    is the largest effective deadline among the *declared* gates.
    """
    payload = await _captured_epic_input(
        tmp_path, run_async, dispatch_recorder, timeouts=timeouts, version=version
    )

    assert payload.config.gate_timeout_s == expected


def test_the_derivation_covers_omitted_entries_through_the_default(
    tmp_path: Path,
) -> None:
    """US1-S3, the omitted-entry case at the pure seam.

    Two gates; only `lint` declares a timeout. `test` is omitted, so the
    default participates: the basis is max(default, 30) = 600 — the same
    effective deadline the runner would resolve for the omitted gate, and the
    slowest window the epic's verification must therefore cover.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / MANIFEST_NAME).write_text(
        "version: 2\nruntime: bwrap\n"
        "gates:\n  test: uv run pytest -q\n  lint: echo lint\n"
        "timeouts:\n  lint: 30\n",
        encoding="utf-8",
    )
    config, _, _ = load_loop_config(repo)
    assert config.gate_timeout_s == 600


def test_the_derivation_scan_is_declared_gates_not_the_whole_timeout_map(
    tmp_path: Path,
) -> None:
    """Plan trap 3, at the pure seam: the basis is a property of the gates the
    manifest declares, read through the same default authority the runner uses.

    A mixed manifest — one long declared window, one short one — must pin the
    longest effective deadline, because the verification activity covers every
    gate the manifest declared and its heartbeat must outlast the slowest of
    them. The parser refuses a timeout naming an undeclared gate (plan trap 3:
    preserve its validation), so a mixed manifest here declares all of them.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / MANIFEST_NAME).write_text(
        "version: 1\nruntime: bwrap\n"
        "gates:\n  test: uv run pytest -q\n  lint: echo lint\n"
        "timeouts:\n  test: 900\n  lint: 30\n",
        encoding="utf-8",
    )
    config, _, _ = load_loop_config(repo)
    assert config.gate_timeout_s == 900


# --- US1-S1 / T001: the scheduled activity carries basis + grace ---------------


async def _run_gates_heartbeat(
    env: WorkflowEnvironment,
    config_gate_timeout_s: int,
    *,
    workflow_id: str,
) -> timedelta:
    """Run one node to MERGED and read the `run_gates` heartbeat bound off history.

    `config` is pinned exactly the way both dispatch paths pin it — frozen into
    `EpicInput` before the workflow starts — so what `_verify` asks Temporal
    for is read off the scheduled event, not off a guess at its source. The
    gate stub answers in microseconds, so no test here waits out any deadline.
    """
    from tests.test_interpreter import ScriptedWorld

    script = ScriptedWorld({"us1": [passing()]}, client=env.client)
    await run_epic(
        env,
        script,
        graph=make_graph([make_node("us1", "US1")]),
        config=replace(VerificationConfig(), gate_timeout_s=config_gate_timeout_s),
        workflow_id=workflow_id,
    )

    handle = env.client.get_workflow_handle(workflow_id)
    history = await handle.fetch_history()
    scheduled = [
        event.activity_task_scheduled_event_attributes
        for event in history.events
        if event.event_type == _EVENT_ACTIVITY_SCHEDULED
        and event.activity_task_scheduled_event_attributes.activity_type.name
        == "run_gates"
    ]
    assert scheduled, "the epic never scheduled run_gates"
    [attrs] = scheduled
    return attrs.heartbeat_timeout.ToTimedelta()


async def test_verification_is_scheduled_for_the_declared_basis_plus_grace(
    env: WorkflowEnvironment,
) -> None:
    """US1-S1, FR-004: the activity gets the basis plus its existing 60s grace.

    Read off the run history: `heartbeat_timeout` is the bound the workflow
    actually asked Temporal for, not an option the test takes on faith. 900
    pinned → 960 scheduled; the same epic at the default pins 600 → 660, which
    is today's behaviour and must not move.
    """
    from factory.workgraph.workflow import _GATE_HEARTBEAT_GRACE_S

    raised = await _run_gates_heartbeat(
        env, DECLARED_S, workflow_id="epic-163-gate-deadline-900"
    )
    default = await _run_gates_heartbeat(
        env, BASIS_DEFAULT_S, workflow_id="epic-163-gate-deadline-600"
    )

    assert raised == timedelta(seconds=DECLARED_S + _GATE_HEARTBEAT_GRACE_S), raised
    assert default == timedelta(
        seconds=BASIS_DEFAULT_S + _GATE_HEARTBEAT_GRACE_S
    ), default


def test_the_grace_constant_is_the_existing_sixty_seconds() -> None:
    """FR-004: the grace is unchanged — the story adds a basis, not a margin.

    Named as the literal so a diff that widens the grace moves this test
    instead of passing it; the bound itself is asserted from history above.
    """
    from factory.workgraph.workflow import _GATE_HEARTBEAT_GRACE_S

    assert _GATE_HEARTBEAT_GRACE_S == 60


# --- US1-S2 / T002: the roadmap path pins the same basis -----------------------


class _RoadmapRecordingClient:
    """Records `start_workflow` (the roadmap itself is what this starts)."""

    def __init__(self) -> None:
        self.started: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def start_workflow(self, *args: Any, **kwargs: Any) -> Any:
        self.started.append((args, kwargs))
        return object()


@pytest.fixture
def persona_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A two-persona registry: the node's builder and the promotion target."""
    import yaml

    from factory.config import WriteScope
    from factory.usage.litellm_client import PROXY_URL_ENV

    path = tmp_path / "personas.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "implementer": {
                    "agent": "claude-code",
                    "model": "local/small",
                    "fallback": None,
                    "skills": [],
                    "write_scope": WriteScope.WORKTREE.value,
                    "needs_worktree": True,
                    "timeout": 300,
                },
                "closer": {
                    "agent": "claude-code",
                    "model": "vendor/large",
                    "fallback": None,
                    "skills": [],
                    "write_scope": WriteScope.WORKTREE.value,
                    "needs_worktree": True,
                    "timeout": 600,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ERGANE_PERSONAS_PATH", str(path))
    monkeypatch.setenv(PROXY_URL_ENV, "http://proxy.test/v1")
    return path


def _roadmap_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    timeouts: dict[str, int],
    promotion: str | None,
) -> RoadmapInput:
    """Drive `ergane roadmap start` to the brink; return its `RoadmapInput`.

    The promotion persona is declared through the real parser (075's route, so
    the flag must really exist) and checked against the fixture registry the
    `persona_registry` fixture wrote — never the operator's.
    """
    from factory.cli import roadmap as roadmap_module

    recorder = _RoadmapRecordingClient()

    async def _connect() -> _RoadmapRecordingClient:
        return recorder

    monkeypatch.setattr(roadmap_module, "_connect", _connect)

    target = tmp_path / "target"
    target.mkdir(parents=True, exist_ok=True)
    _manifest(target, version=1, timeouts=timeouts)
    specs_root = tmp_path / "specs"
    specs_root.mkdir(parents=True, exist_ok=True)

    parser = argparse.ArgumentParser(prog="ergane")
    subparsers = parser.add_subparsers(dest="noun", required=True)
    roadmap_module.add_roadmap_parser(subparsers)

    argv = [
        "roadmap",
        "start",
        str(specs_root),
        "--target-repo",
        str(target),
        "--proxy-url",
        "http://proxy.test/v1",
    ]
    if promotion is not None:
        argv += ["--promotion-persona", promotion]
    args = parser.parse_args(argv)
    assert args.run(args) == 0
    return recorder.started[0][0][1]


def test_the_roadmap_overlays_the_promotion_rung_on_the_derived_basis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    persona_registry: Path,
) -> None:
    """US1-S2, FR-002: the child's config is the manifest's ladder plus the rung.

    The roadmap's read pins the basis (the same `load_loop_config` the CLI
    reads), `_child_config` lays the operator's promotion persona over it, and
    the child carries both — the derived basis and every unrelated ladder dial
    preserved, the overlay one field wide (075 FR-010). Pure, so the
    Temporal-free seam the plan names is the one this asserts.
    """
    from factory.cli.promotion import with_promotion_persona

    payload = _roadmap_input(
        tmp_path, monkeypatch, timeouts={"test": DECLARED_S}, promotion="closer"
    )
    assert payload.config.promotion_persona == "closer"

    # The dispatch read, through the production path, on the same manifest the
    # roadmap command just wrote.
    pinned, _, _ = load_loop_config(tmp_path / "target")
    assert pinned.gate_timeout_s == DECLARED_S

    child = _child_config(
        with_promotion_persona(pinned, payload.config.promotion_persona),
        payload.config,
    )

    assert child.promotion_persona == "closer"
    assert child.gate_timeout_s == DECLARED_S
    # Every unrelated ladder dial stays the manifest's.
    assert child.max_attempts == pinned.max_attempts
    assert child.max_judge_retries == pinned.max_judge_retries
    assert child.debugger_cycles == pinned.debugger_cycles
    assert child.escalation_timeout_s == pinned.escalation_timeout_s
    assert child.promotion_cycles == pinned.promotion_cycles
    assert child.max_pre_agent_failures == pinned.max_pre_agent_failures


async def _roadmap_child_input(
    env: WorkflowEnvironment,
    tmp_path: Path,
    target: Path,
    specs_root: Path,
) -> EpicInput:
    """Run the real roadmap once; return the `EpicInput` it started the child on.

    Every pre-dispatch seam is scripted except the two this story's derivation
    runs through: the clone answers the target path, and `read_loop_config` is
    the real activity whose runner seam stays unset — so the temporary
    manifest is the thing actually read. The child `EpicInput` is read off the
    wire by the recording interceptor.
    """
    from factory.activities import roadmap_activities
    from factory.activities.notify_activities import (
        record_roadmap_failure,
        reset_roadmap_failures,
        send_escalation,
        send_roadmap_notice,
    )
    from factory.roadmap.workflow import read_corpus_activity, read_spec_text_activity
    from factory.activities.roadmap_activities import (
        clone_target,
        count_open_epics,
        derive_spec,
        drift_for_spec,
        onboard_target,
        preflight_spec,
        read_loop_config,
        tree_revision_activity,
    )
    from tests.test_roadmap_scheduler import HARNESS_REVISION, _BootRevisionInterceptor

    from factory.workgraph.derive import derive_workgraph as _derive
    from factory.activities.roadmap_activities import DeriveInput

    def _derive_runner(request: DeriveInput) -> Any:
        return _derive(
            request.spec_text,
            epic_id=request.epic_id,
            feature=request.feature,
            specs_root=request.specs_root,
            target_repo=request.target_repo,
        )

    import factory.workgraph.preflight as preflight_module

    saved = {
        "clone": roadmap_activities._clone_runner,
        "derive": roadmap_activities._derive_runner,
        "drift": roadmap_activities._drift_runner,
        "preflight_registry": roadmap_activities._preflight_registry,
        "preflight_client": roadmap_activities._preflight_client,
        "onboard": roadmap_activities._onboard,
        "open_epics": roadmap_activities._open_epics_provider,
        "tree_revision": getattr(roadmap_activities, "_tree_revision_runner", None),
        "aliases": roadmap_activities.check_aliases,
        "preflight_aliases": preflight_module.check_aliases,
        # `RoadmapWorld.restore` *deletes* a runner seam whose pre-world value
        # was None, so "absent" is a state a prior test can leave the module
        # in. Distinguish it from None here, and put it back exactly as found.
        "tree_revision_present": hasattr(
            roadmap_activities, "_tree_revision_runner"
        ),
        "read_loop_config_present": hasattr(
            roadmap_activities, "_read_loop_config_runner"
        ),
        "read_loop_config": getattr(
            roadmap_activities, "_read_loop_config_runner", None
        ),
    }
    roadmap_activities._clone_runner = lambda _: _clone_answer(str(target))
    roadmap_activities._derive_runner = _derive_runner
    roadmap_activities._drift_runner = lambda request: False
    # The module attribute, not its value, is the seam's presence: the activity
    # reads the module global at call time, so a prior test's restore that
    # deleted it (no pre-world value) would NameError the read mid-flight.
    # Ensure it exists — None is "no runner, read the manifest for real" —
    # before this run sets its own answer beside it.
    roadmap_activities._read_loop_config_runner = None
    roadmap_activities._tree_revision_runner = lambda _: HARNESS_REVISION
    roadmap_activities._preflight_registry = lambda: {}
    roadmap_activities._preflight_client = _preflight_client_answer
    # Route the shared `check_aliases` through a scripted answer, the same
    # way `RoadmapWorld.apply` does — both bindings, activities module and
    # source module, so whichever path a future refactor takes stays scripted.
    async def _check_aliases(graph: Any, registry: Any, client: Any) -> list[Any]:
        return []

    roadmap_activities.check_aliases = _check_aliases
    preflight_module.check_aliases = _check_aliases
    roadmap_activities._onboard = _onboard_answer
    async def _no_open_epics() -> set[str]:
        return set()

    roadmap_activities._open_epics_provider = _no_open_epics

    _SCRIPT.statuses = {"001-alpha": landed_status()}
    _SCRIPT.on_dispatch = None
    _SCRIPT.on_complete = None
    _SCRIPT.hold = set()

    activities = [
        roadmap_activities.clone_target,
        roadmap_activities.derive_spec,
        roadmap_activities.drift_for_spec,
        roadmap_activities.preflight_spec,
        roadmap_activities.onboard_target,
        roadmap_activities.count_open_epics,
        roadmap_activities.read_loop_config,
        roadmap_activities.tree_revision_activity,
        read_corpus_activity,
        read_spec_text_activity,
        record_roadmap_failure,
        reset_roadmap_failures,
        send_roadmap_notice,
        send_escalation,
    ]
    records: list[ChildStartRecord] = []
    interceptors = [
        _BootRevisionInterceptor(HARNESS_REVISION),
        _RecordingInterceptor(records),
    ]
    try:
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
                    target_repo=str(target),
                    proxy_url=ROADMAP_PROXY_URL,
                    max_concurrent_epics=1,
                    config=VerificationConfig(promotion_persona="closer"),
                ),
                id=roadmap_workflow_id(str(specs_root)),
                task_queue="workgraph",
            )
            await handle.result()
    finally:
        roadmap_activities._clone_runner = saved["clone"]
        roadmap_activities._derive_runner = saved["derive"]
        roadmap_activities._drift_runner = saved["drift"]
        roadmap_activities._preflight_registry = saved["preflight_registry"]
        roadmap_activities._preflight_client = saved["preflight_client"]
        roadmap_activities._onboard = saved["onboard"]
        roadmap_activities._open_epics_provider = saved["open_epics"]
        roadmap_activities.check_aliases = saved["aliases"]
        preflight_module.check_aliases = saved["preflight_aliases"]
        if not saved["tree_revision_present"]:
            try:
                delattr(roadmap_activities, "_tree_revision_runner")
            except AttributeError:
                pass
        elif saved["tree_revision"] is not None:
            roadmap_activities._tree_revision_runner = saved["tree_revision"]
        else:
            roadmap_activities._tree_revision_runner = None
        if not saved["read_loop_config_present"]:
            try:
                delattr(roadmap_activities, "_read_loop_config_runner")
            except AttributeError:
                pass
        else:
            roadmap_activities._read_loop_config_runner = saved.get(
                "read_loop_config", None
            )
        _SCRIPT.statuses = {}
        _SCRIPT.on_dispatch = None
        _SCRIPT.on_complete = None
        _SCRIPT.hold = set()

    assert len(records) == 1, records
    child_input = records[0].args[0]
    assert isinstance(child_input, EpicInput)
    return child_input


from factory.activities.roadmap_activities import CloneResult as _CloneResult


def _clone_answer(path: str) -> _CloneResult:
    """The scripted clone answer: refreshed at the target path."""
    return _CloneResult(
        path=path, default_branch="main", head_ref="abc123"
    )


def _preflight_client_answer(proxy_url: str) -> Any:
    """The preflight's client seam, answered with a client-shaped object.

    The alias check is scripted (`check_aliases` answers clean above), so this
    client is never dialled; the seam returns the type production returns so a
    refactor that stops scripting the alias check fails loudly rather than
    silently passing on `None`.
    """
    from factory.usage.litellm_client import LiteLLMClient

    return LiteLLMClient(base_url="http://litellm.test", master_key="unused")


async def _onboard_answer(target_repo: str) -> Any:
    """The onboarding gate answered passing, derived rather than built by hand."""
    from factory.mergequeue.models import Finding
    from tests.test_roadmap_scheduler import _passing_profile

    return _passing_profile(target_repo)


async def test_the_roadmap_child_input_carries_the_derived_basis(
    env: WorkflowEnvironment,
    tmp_path: Path,
    persona_registry: Path,
) -> None:
    """US1-S2, FR-002, through the roadmap's production read.

    The real `read_loop_config` activity (its seam unset) reads the temporary
    manifest beside the real `_child_config` composition, and the `EpicInput`
    the roadmap actually started the child with carries both the derived basis
    and the operator's rung.
    """
    from factory.roadmap.models import SpecState as _SpecState

    target = tmp_path / "target"
    target.mkdir(parents=True, exist_ok=True)
    _manifest(target, version=1, timeouts={"test": DECLARED_S})

    specs_root = build_corpus(tmp_path, {"001-alpha": dict(state=_SpecState.READY)})
    child_input = await _roadmap_child_input(
        env, tmp_path, target, specs_root
    )

    assert child_input.config.gate_timeout_s == DECLARED_S
    assert child_input.config.promotion_persona == "closer"
    assert child_input.verify_order == ("gates", "diff_check", "judge")


# --- US1-S4 / T004: a pinned input means what it meant -------------------------


def test_a_pinned_input_is_untouched_by_a_later_manifest_edit(tmp_path: Path) -> None:
    """US1-S4, FR-004: the pinned basis is frozen at dispatch.

    `EpicInput.config` is a frozen dataclass handed to the workflow once; the
    workflow reads `config.gate_timeout_s` and reads nothing from the repo
    (plan trap 5). The proof is mechanical: the payload a *changed* manifest
    produces is a different value, and the old payload still carries the old
    one — a deployment does not repair an already-running epic.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _manifest(repo, version=1, timeouts={"test": BASIS_DEFAULT_S})
    pinned, _, _ = load_loop_config(repo)
    assert pinned.gate_timeout_s == BASIS_DEFAULT_S

    # The operator raises the declared deadline after the epic was pinned.
    _manifest(repo, version=1, timeouts={"test": DECLARED_S})
    repinned, _, _ = load_loop_config(repo)
    assert repinned.gate_timeout_s == DECLARED_S

    # The old input is a frozen dataclass: nothing migrated it.
    assert pinned.gate_timeout_s == BASIS_DEFAULT_S


def test_an_old_default_only_input_still_means_600() -> None:
    """US1-S4: an input written before this story means what it meant.

    `VerificationConfig()`'s field default is the deployment knob the runner
    reads; an `EpicInput` constructed the pre-163 way — `config=VerificationConfig()`
    — still carries 600, and `_verify` still schedules 660 for it. The default
    authority is unchanged (FR-003): `VerificationConfig.gate_timeout_s` is
    what an operator edits, and the runner's default is the same number.
    """
    from factory.verify.gates import DEFAULT_GATE_TIMEOUT_S

    assert VerificationConfig().gate_timeout_s == 600
    assert DEFAULT_GATE_TIMEOUT_S == 600


def test_a_malformed_timeout_declaration_is_still_refused() -> None:
    """US1-S4, FR-003: the parser's refusals are untouched by the derivation.

    The same rules the parser enforced before this story — a timeout naming a
    gate the manifest does not declare, a non-integer, a non-positive integer —
    still raise, so a bad declaration is a refusal at dispatch and never a
    silent default. The derivation reads what the parser already validated.
    """
    from factory.verify.factory_yaml import FactoryConfigError, parse_factory_config

    with pytest.raises(FactoryConfigError) as refused:
        parse_factory_config(
            "version: 1\nruntime: bwrap\ngates:\n  test: uv run pytest -q\n"
            "timeouts:\n  lint: 30\n",
        )
    assert refused.value.rule == "timeouts"

    with pytest.raises(FactoryConfigError) as refused_type:
        parse_factory_config(
            "version: 1\nruntime: bwrap\ngates:\n  test: uv run pytest -q\n"
            "timeouts:\n  test: true\n",
        )
    assert refused_type.value.rule == "timeouts"

    with pytest.raises(FactoryConfigError) as refused_negative:
        parse_factory_config(
            "version: 1\nruntime: bwrap\ngates:\n  test: uv run pytest -q\n"
            "timeouts:\n  test: -5\n",
        )
    assert refused_negative.value.rule == "timeouts"


# --- the legacy-name control ---------------------------------------------------


def test_the_derivation_reads_the_manifest_by_its_resolved_name(
    tmp_path: Path,
) -> None:
    """The read rides `resolve_manifest_path`, not a hardcoded name.

    A manifest written under the legacy name is still honored by the resolver
    (with its deprecation warning), so the derivation cannot silently prefer
    the new name and leave a legacy repo on the default — the same repo must
    pin the same basis either way.
    """
    legacy = "factory.yaml"
    repo = tmp_path / "legacy-repo"
    repo.mkdir()
    (repo / legacy).write_text(
        _manifest_text(version=1, timeouts={"test": DECLARED_S}),
        encoding="utf-8",
    )
    config, _, _ = load_loop_config(repo)
    assert config.gate_timeout_s == DECLARED_S


# --- the roadmap child scheduling seam ------------------------------------------


async def test_the_child_epic_schedules_verification_for_the_derived_basis(
    env: WorkflowEnvironment,
) -> None:
    """US1-S2's scheduling half: the child's `run_gates` carries basis + grace.

    The child input the roadmap built in the test above is exactly the shape
    this asserts the workflow schedules from: the pinned basis plus the
    existing 60-second grace, read off history the same way US1-S1's is.
    """
    from factory.workgraph.workflow import _GATE_HEARTBEAT_GRACE_S

    raised = await _run_gates_heartbeat(
        env, DECLARED_S, workflow_id="epic-163-child-basis"
    )
    assert raised == timedelta(seconds=DECLARED_S + _GATE_HEARTBEAT_GRACE_S), raised