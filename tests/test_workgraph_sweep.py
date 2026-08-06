"""The four guarantees no single module of this component can prove alone.

Every other test file here asks whether one module of the interpreter does its
job. This one asks whether the interpreter, taken whole, still has the four
properties tasks.md picked as the ones an operator has to be able to trust blind
— the ones whose failure mode is silence:

- **The two credentials exist in the worker environment and nowhere else.**
  `LITELLM_MASTER_KEY` (001's) and `TELEGRAM_BOT_TOKEN` (002's) sit in the same
  process that launches agents, and this component is the one that spawns a
  child, writes to disk, and puts payloads into workflow history — three
  channels the other two components do not have. So both are set, to canaries
  unlike anything else in this repository, for the whole of a real agent attempt
  against the stub, and then every way either could have escaped is searched:
  the child's own environment as the child recorded it, every byte the attempt
  persisted, every Temporal payload the workflow hands an activity, and the
  whole raised chain of every failure path the component can take. The
  per-attempt virtual key is the one credential allowed to travel, and it is
  allowed exactly one home: `AttemptContext`, from which the adapter writes it
  into `ANTHROPIC_AUTH_TOKEN` and nowhere else.

- **FR-012: nothing the agent says or returns decides a node.** The adapter
  classifies a *process* — exit zero, exit non-zero, deadline, cancellation —
  and that classification travels to teardown and to the salvage subject. It is
  checked structurally (the workflow reads one field off an attempt's result,
  and a node's state is written from the ladder's action alone) and then
  exhaustively over the whole product of terminations and gate outcomes: every
  termination the adapter can report passes a node whose gates are green and
  fails one whose gates are not, which is the claim in both directions at once.

- **SC-002: no dispatch path with unmet dependencies.** Structurally, because
  there is exactly one place a node is picked and one place an agent is started;
  and behaviourally from *inside* each running attempt, over a set of epics that
  pass, fail, escalate and get killed — a terminal snapshot cannot tell an edge
  that unlocked on a PASS from one that unlocked on a hope.

- **FR-007: no transcript path under any repo worktree.** An archive inside the
  worktree would be committed by the salvage that follows it (constitution VI)
  and read as agent work by 002's diff check (FR-004) — a leak into the target
  repository's history, not just a misplaced file. Asserted over the real path
  helpers and then against a real git worktree: the attempt archives, the
  worktree is salvaged, and the commit's file list is searched for the evidence.

Written last (T034), against the finished component: unlike most test files
here, this one is expected to pass on arrival. A failure means something that
was true when it was written has since stopped being true.

The scripted world comes from `tests/test_interpreter.py` rather than from a
second harness built here. A sweep asserts things about the component the
component's own tests already exercise; a private set of fakes would be a second
definition of what the interpreter talks to, and the two would drift.
"""

from __future__ import annotations

import ast
import asyncio
import json
import logging
import os
import re
import traceback
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterator

import pytest
from temporalio.converter import DataConverter
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment, WorkflowEnvironment

from factory.activities.agent_activities import (
    FACTORY_ROOT_ENV,
    LoadPromptSourcesInput,
    PrepareWorktreeInput,
    PromptSources,
    RemoveWorktreeInput,
    SalvageWorktreeInput,
    load_prompt_sources,
    prepare_worktree,
    remove_worktree,
    resolve_graph,
    run_agent_attempt,
    salvage_worktree,
)
from factory.config import load_personas
from factory.usage.models import Termination
from factory.verify.models import OverallVerdict
from factory.workgraph import cli, derive, worktree as worktrees
from factory.workgraph.adapter import (
    STDOUT_LOG_NAME,
    ClaudeCodeAdapter,
    adapter_for,
    attempt_env,
    pid_file,
    transcript_dir,
)
from factory.workgraph.models import (
    AdapterResult,
    AttemptContext,
    NodeState,
    WorkGraph,
    WorkNode,
)
from factory.workgraph.prompt import build_attempt_prompt
from factory.workgraph.worktree import branch_name, worktree_path
from tests.stub_agent import STUB_AGENT_PATH, install_as, write_control
from tests.target_repo import git
from tests.test_interpreter import (
    EPIC_ID,
    PLAN_TEXT,
    SPEC_TEXT,
    TASKS_TEXT,
    Attempt,
    ScriptedWorld,
    all_passing,
    failing,
    gate_fail,
    gate_pass,
    make_graph,
    make_node,
    passing,
    run_epic,
    states,
)

#: The proxy credential the worker host holds — component 1's, still in the
#: environment of the process that launches an agent. No substring of it occurs
#: anywhere else in this repository, so "this string appears here" is never a
#: coincidence.
MASTER_KEY = "sk-canary-2e7a0c96b41df385-workgraph-master"

#: The notifier's credential, shaped like a real Bot API token (`<id>:<secret>`)
#: because that shape is what a failing call quotes back inside a URL.
BOT_TOKEN = "7742118903:CANARY3f8b1d6ea94c0527bd31f8ea60c94d17"

#: The one credential this component is *supposed* to carry: minted per attempt,
#: model-constrained, and revoked at teardown (constitution V). It travels in
#: `AttemptContext` and reaches the child as `ANTHROPIC_AUTH_TOKEN`.
VIRTUAL_KEY = "sk-canary-virtual-4b7d1c0a-attempt"

EPIC = "005-workgraph-interpreter"
NODE = "us1"
ATTEMPT = 2
SESSION_ID = "3d9f27a1-0c64-4b58-9e12-8a5f6d3c2b70"
MODEL_ALIAS = "anthropic/CHANGEME"
PROXY_URL = "http://litellm.test:4000"
PROMPT = "You are the implementer persona.\n\n## Scope\n\nImplement US1.\n"

#: Long enough that no test here races its own deadline; the production value is
#: the persona registry's (FR-010).
TIMEOUT_S = 60

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPONENT_ROOT = REPO_ROOT / "factory"
WORKGRAPH_PACKAGE = COMPONENT_ROOT / "workgraph"

#: Every module this component ships (plan.md § Source Code). The two earlier
#: components have their own sweeps — `tests/test_final_sweep.py` and
#: `tests/test_verification_sweep.py` — and this list is what extends that
#: discipline to the interpreter.
COMPONENT_MODULES = sorted(
    [
        *WORKGRAPH_PACKAGE.rglob("*.py"),
        COMPONENT_ROOT / "activities" / "agent_activities.py",
        COMPONENT_ROOT / "worker.py",
    ]
)

WORKFLOW_MODULE = WORKGRAPH_PACKAGE / "workflow.py"
ADAPTER_MODULE = WORKGRAPH_PACKAGE / "adapter.py"

#: The one dataclass allowed to carry the attempt's virtual key, and the one
#: function allowed to read it out (contracts/adapter.md § Environment).
KEY_HOLDER = WORKGRAPH_PACKAGE / "models.py"
KEY_READER = ADAPTER_MODULE


def module_id(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


# --- source-reading helpers ---------------------------------------------------


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def docstring_ids(tree: ast.Module) -> set[int]:
    """Every string constant that *is* a docstring, by identity.

    This component is required to explain at length which credentials it does
    not touch and which signals it does not read, and saying so is not doing so.
    """
    return {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        )
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }


def code_strings(tree: ast.Module) -> set[str]:
    """Every string constant the module's *code* spells, docstrings excluded."""
    docstrings = docstring_ids(tree)
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


def identifiers(tree: ast.AST) -> set[str]:
    """Every name, attribute, argument and keyword the code spells."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.arg):
            found.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            found.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name)
    return found


def enclosing_functions(tree: ast.Module) -> dict[int, Any]:
    """Map every AST node to the innermost function it sits inside."""
    owner: dict[int, Any] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                owner.setdefault(id(child), node)
    return owner


def owner_name(owner: dict[int, Any], node: ast.AST) -> str:
    enclosing = owner.get(id(node))
    return enclosing.name if enclosing else "<module>"


def function_named(tree: ast.Module, name: str) -> Any:
    """One function definition by name; raises if the module no longer has it."""
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    )


def calls_to(tree: ast.Module, name: str) -> list[ast.Call]:
    """Every call of `name`, however it is spelled (bare or attribute)."""
    found: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        spelled = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if spelled == name:
            found.append(node)
    return found


# --- the world one attempt runs in --------------------------------------------


@pytest.fixture
def factory_root(tmp_path: Path) -> Path:
    """The worker host's state directory: worktrees, transcripts, pid files."""
    return tmp_path / ".factory"


@pytest.fixture(autouse=True)
def worker_host(
    tmp_path: Path, factory_root: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """A worker host with both credentials in the environment, and a fake home.

    Autouse, and both credentials set for every test in this file including the
    ones that never launch a child: a credential escapes through whichever path
    nobody was thinking about at the time, so it has to be available to escape on
    all of them.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")

    monkeypatch.setenv(FACTORY_ROOT_ENV, str(factory_root))
    monkeypatch.setenv("LITELLM_MASTER_KEY", MASTER_KEY)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setenv("LITELLM_PROXY_URL", PROXY_URL)
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("TERM", "dumb")
    return home


@pytest.fixture(autouse=True)
def agent_on_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """`tests/stub_agent.py` where `claude` would be found (R6).

    Autouse so a worker host with a real `claude` installed cannot have this
    file launch it against a real proxy.
    """
    bin_dir = tmp_path / "bin"
    install_as(bin_dir, "claude")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return bin_dir


@pytest.fixture
def agent_worktree(tmp_path: Path) -> Path:
    """Where the agent runs. A plain directory — the git half is FR-007's test."""
    path = tmp_path / "agent-worktree"
    path.mkdir()
    return path


@pytest.fixture
def context(agent_worktree: Path) -> Callable[..., AttemptContext]:
    """Build the attempt's context; `context(attempt=3)` overrides one field."""

    def build(**overrides: Any) -> AttemptContext:
        fields: dict[str, Any] = {
            "epic_id": EPIC,
            "node_id": NODE,
            "attempt": ATTEMPT,
            "prompt": PROMPT,
            "worktree_path": str(agent_worktree),
            "proxy_url": PROXY_URL,
            "virtual_key": VIRTUAL_KEY,
            "model_alias": MODEL_ALIAS,
            "session_id": SESSION_ID,
            "timeout_s": TIMEOUT_S,
        }
        return AttemptContext(**(fields | overrides))

    return build


@pytest.fixture
def env() -> ActivityEnvironment:
    return ActivityEnvironment()


@pytest.fixture
async def temporal() -> Any:
    """Temporal with a clock the test owns — an hour of silence costs nothing."""
    environment = await WorkflowEnvironment.start_time_skipping()
    try:
        yield environment
    finally:
        await environment.shutdown()


def work_node(**overrides: Any) -> WorkNode:
    fields: dict[str, Any] = {
        "id": NODE,
        "story_key": "US1",
        "persona": "implementer",
        "spec_ref": f"{EPIC}:US1",
        "requirement_keys": ["US1", "FR-001"],
        "depends_on": [],
    }
    return WorkNode(**(fields | overrides))


def work_graph(*nodes: WorkNode, **overrides: Any) -> WorkGraph:
    fields: dict[str, Any] = {
        "epic_id": EPIC,
        "feature": EPIC,
        "specs_root": "specs",
        "target_repo": "/srv/factory/targets/ergane",
        "nodes": list(nodes) or [work_node()],
    }
    return WorkGraph(**(fields | overrides))


# ============================================================================
# 1. The two credentials
# ============================================================================


async def test_no_byte_a_real_attempt_persists_carries_either_credential(
    env: ActivityEnvironment,
    context: Callable[..., AttemptContext],
    agent_worktree: Path,
    factory_root: Path,
    worker_host: Path,
    tmp_path: Path,
) -> None:
    """One whole agent attempt, then sweep everything it touched.

    The child records its own environment (`tests/stub_agent.py`), so a leak into
    the agent is not a subtle failure here: it is the master key, written by the
    agent itself into a file inside the node's worktree, which the next salvage
    commits to the node's branch.
    """
    write_control(worker_host, stdout="agent: wrote src/loans.py and ran the gates")

    result = await env.run(run_agent_attempt, context())
    assert result.termination is Termination.COMPLETED

    archive = transcript_dir(factory_root, EPIC, NODE, ATTEMPT)
    assert (archive / STDOUT_LOG_NAME).is_file(), "the attempt archived no log to sweep"
    assert (archive / f"{SESSION_ID}.jsonl").is_file()

    # Everything the attempt left on disk: the archive, the worktree the agent
    # wrote in, the pid file, and the fake home the session transcript lives in.
    written = [path for path in sorted(tmp_path.rglob("*")) if path.is_file()]
    assert archive / STDOUT_LOG_NAME in written
    for path in written:
        blob = path.read_bytes()
        for secret, name in ((MASTER_KEY, "master key"), (BOT_TOKEN, "bot token")):
            assert secret.encode() not in blob, (
                f"{name} found in {path.relative_to(tmp_path)}"
            )

    # The child's environment, as the child itself recorded it: the allowlist is
    # a construction, so the two credentials are absent because nothing put them
    # there rather than because something removed them (US2-S1).
    recorded = json.loads(
        (next(agent_worktree.glob(".stub-agent/*/env.json"))).read_text(encoding="utf-8")
    )
    assert set(recorded) <= {
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_AUTH_TOKEN",
        "PATH",
        "HOME",
        "LANG",
        "TERM",
    }
    assert MASTER_KEY not in recorded.values()
    assert BOT_TOKEN not in recorded.values()

    # And the one credential that is allowed through, in the one variable the
    # proxy reads it from (R6).
    assert recorded["ANTHROPIC_AUTH_TOKEN"] == VIRTUAL_KEY


async def test_no_payload_this_component_hands_an_activity_carries_either_credential(
    context: Callable[..., AttemptContext],
) -> None:
    """Activity inputs and outputs are persisted verbatim in workflow history.

    Every payload the interpreter constructs is encoded exactly as Temporal would
    encode it and searched. The attempt's own context is the interesting one: it
    is *supposed* to carry the virtual key, which is what makes the attempt's
    spend attributable (constitution V), and it must carry nothing else.
    """
    payloads = await DataConverter.default.encode(
        [
            work_graph(),
            context(),
            AdapterResult(termination=Termination.COMPLETED, transcript_path="/x"),
            PrepareWorktreeInput(
                epic_id=EPIC, node_id=NODE, target_repo="/srv/repo", standards="S.md"
            ),
            SalvageWorktreeInput(
                epic_id=EPIC,
                node_id=NODE,
                termination=Termination.KILLED,
                attempt=ATTEMPT,
            ),
            RemoveWorktreeInput(epic_id=EPIC, node_id=NODE, target_repo="/srv/repo"),
            LoadPromptSourcesInput(
                specs_root="specs", feature=EPIC, target_repo="/srv/repo"
            ),
            PromptSources(
                spec_text=SPEC_TEXT,
                plan_text=PLAN_TEXT,
                tasks_text=TASKS_TEXT,
                standards="S.md",
            ),
        ]
    )
    for payload in payloads:
        for blob in (bytes(payload.data), *payload.metadata.values()):
            for secret, name in ((MASTER_KEY, "master key"), (BOT_TOKEN, "bot token")):
                assert secret.encode() not in blob, f"{name} found in a payload"

    # The virtual key rides on the attempt's context and on nothing else the
    # component sends: a `transcript_path` or a salvage subject that carried it
    # would put a credential in an archive directory name and in a commit message.
    [context_payload] = [
        bytes(payload.data)
        for payload in payloads
        if VIRTUAL_KEY.encode() in bytes(payload.data)
    ]
    assert b'"virtual_key"' in context_payload


def test_the_attempt_prompt_never_carries_a_credential() -> None:
    """The largest payload in the component, and the one an agent reads aloud.

    A prompt is assembled from authored text (FR-006) and travels inside the
    attempt's context beside the virtual key. Nothing in the assembler's inputs
    is a credential, and nothing in its output may be one — not even the key the
    same context legitimately carries, which would then reach `stdout.log`, the
    archived transcript, and any repository the agent chose to paste it into.
    """
    prompt = build_attempt_prompt(
        node=make_node("us1", "US1"),
        epic_id=EPIC_ID,
        spec_text=SPEC_TEXT,
        plan_text=PLAN_TEXT,
        tasks_text=TASKS_TEXT,
        standards=".specify/memory/constitution.md",
    )

    for secret in (MASTER_KEY, BOT_TOKEN, VIRTUAL_KEY):
        assert secret not in prompt
    assert "ANTHROPIC_AUTH_TOKEN" not in prompt


# --- every way this component fails -------------------------------------------


async def a_graph_with_a_cycle(component: dict[str, Any]) -> object:
    nodes = [
        work_node(id="us1", depends_on=["us2"]),
        work_node(id="us2", story_key="US2", depends_on=["us1"]),
    ]
    return await component["env"].run(resolve_graph, work_graph(*nodes))


async def a_graph_naming_a_persona_that_is_not_in_the_registry(
    component: dict[str, Any],
) -> object:
    return await component["env"].run(
        resolve_graph, work_graph(work_node(persona="archaeologist"))
    )


async def a_registry_that_will_not_load(component: dict[str, Any]) -> object:
    broken = component["workspace"] / "personas.yaml"
    broken.write_text("implementer: [not, a, mapping]\n", encoding="utf-8")
    component["monkeypatch"].setattr(
        "factory.activities.agent_activities.load_personas",
        lambda: load_personas(broken),
    )
    return await component["env"].run(resolve_graph, work_graph())


async def a_target_repo_that_is_not_a_repository(component: dict[str, Any]) -> object:
    empty = component["workspace"] / "not-a-repo"
    empty.mkdir()
    return await component["env"].run(
        prepare_worktree,
        PrepareWorktreeInput(epic_id=EPIC, node_id=NODE, target_repo=str(empty)),
    )


async def a_standards_document_that_is_not_in_the_worktree(
    component: dict[str, Any],
) -> object:
    return await component["env"].run(
        prepare_worktree,
        PrepareWorktreeInput(
            epic_id=EPIC,
            node_id=NODE,
            target_repo=str(component["repo"]),
            standards="docs/STANDARDS.md",
        ),
    )


async def an_agent_binary_that_is_not_on_the_worker_host(
    component: dict[str, Any],
) -> object:
    component["monkeypatch"].setenv("PATH", str(component["workspace"] / "empty-bin"))
    return await component["env"].run(run_agent_attempt, component["context"]())


async def an_adapter_for_an_agent_nobody_wrote(component: dict[str, Any]) -> object:
    return adapter_for("opencode")


async def a_salvage_against_a_worktree_that_vanished(
    component: dict[str, Any],
) -> object:
    return await component["env"].run(
        salvage_worktree,
        SalvageWorktreeInput(
            epic_id=EPIC,
            node_id="never-prepared",
            termination=Termination.KILLED,
            attempt=1,
        ),
    )


async def a_removal_against_a_repo_that_vanished(component: dict[str, Any]) -> object:
    return await component["env"].run(
        remove_worktree,
        RemoveWorktreeInput(
            epic_id=EPIC, node_id=NODE, target_repo=str(component["workspace"] / "gone")
        ),
    )


async def a_prompt_source_that_is_not_there(component: dict[str, Any]) -> object:
    return await component["env"].run(
        load_prompt_sources,
        LoadPromptSourcesInput(
            specs_root=str(component["workspace"] / "no-specs"),
            feature=EPIC,
            target_repo=str(component["repo"]),
        ),
    )


async def a_story_with_no_slice_in_tasks_md(component: dict[str, Any]) -> object:
    return build_attempt_prompt(
        node=make_node("us1", "US1"),
        epic_id=EPIC_ID,
        spec_text=SPEC_TEXT,
        plan_text=PLAN_TEXT,
        tasks_text="# Tasks\n\n## Phase 1: Setup\n\n- [ ] T001 Nothing for US1\n",
    )


async def a_spec_the_deriver_refuses(component: dict[str, Any]) -> object:
    spec = REPO_ROOT / "tests" / "fixtures" / "workgraph" / "unknown_dep" / "spec.md"
    return derive.derive_workgraph(
        spec.read_text(encoding="utf-8"),
        epic_id=EPIC,
        feature=EPIC,
        specs_root="specs",
        target_repo=str(component["repo"]),
    )


async def a_workgraph_json_that_is_not_json(component: dict[str, Any]) -> object:
    broken = component["workspace"] / "workgraph.json"
    broken.write_text("{not json at all", encoding="utf-8")
    return cli.load_workgraph(broken)


async def a_workgraph_json_that_is_not_there(component: dict[str, Any]) -> object:
    return cli.load_workgraph(component["workspace"] / "absent" / "workgraph.json")


async def an_operator_deriving_a_spec_that_is_not_there(
    component: dict[str, Any],
) -> object:
    return cli.main(
        [
            "derive",
            str(component["workspace"] / "specs" / "no-such-feature"),
            "--target-repo",
            str(component["repo"]),
        ]
    )


async def an_operator_starting_an_epic_with_no_proxy_url(
    component: dict[str, Any],
) -> object:
    """The check that runs before any client is built: without the proxy url the
    attempt's virtual key is honored nowhere, so the epic never starts.

    Deliberately the *last* thing `start` refuses without a server, because it is
    the one whose message is built beside the environment holding both worker
    credentials.
    """
    graph = component["workspace"] / "workgraph.json"
    graph.write_text(
        json.dumps(
            {
                "epic_id": EPIC,
                "feature": EPIC,
                "specs_root": "specs",
                "target_repo": str(component["repo"]),
                "nodes": [
                    {
                        "id": NODE,
                        "story_key": "US1",
                        "persona": "implementer",
                        "spec_ref": f"{EPIC}:US1",
                        "requirement_keys": ["US1"],
                        "depends_on": [],
                        "timeout_override_s": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    component["monkeypatch"].delenv("LITELLM_PROXY_URL")
    return cli.main(["start", str(graph)])


#: Every way this component can fail or refuse. Some raise and some report — a
#: graph with a cycle raises, a CLI command returns an exit code — and the sweep
#: does not care which: it searches the exception chain, the returned value, the
#: log lines and whatever reached the operator's terminal, because all four reach
#: a human. A path added to the component without a line here is a path whose
#: output nobody has read.
FAILURE_PATHS: list[Callable[[dict[str, Any]], Awaitable[object]]] = [
    a_graph_with_a_cycle,
    a_graph_naming_a_persona_that_is_not_in_the_registry,
    a_registry_that_will_not_load,
    a_target_repo_that_is_not_a_repository,
    a_standards_document_that_is_not_in_the_worktree,
    an_agent_binary_that_is_not_on_the_worker_host,
    an_adapter_for_an_agent_nobody_wrote,
    a_salvage_against_a_worktree_that_vanished,
    a_removal_against_a_repo_that_vanished,
    a_prompt_source_that_is_not_there,
    a_story_with_no_slice_in_tasks_md,
    a_spec_the_deriver_refuses,
    a_workgraph_json_that_is_not_json,
    a_workgraph_json_that_is_not_there,
    an_operator_deriving_a_spec_that_is_not_there,
    an_operator_starting_an_epic_with_no_proxy_url,
]


def renderings_of(error: BaseException) -> Iterator[str]:
    """Every way this failure could reach a human: the formatted traceback of the
    whole chain, plus each link's own message, args and repr."""
    yield "".join(traceback.format_exception(type(error), error, error.__traceback__))

    seen: BaseException | None = error
    depth = 0
    while seen is not None and depth < 10:
        yield str(seen)
        yield repr(seen)
        yield str(seen.args)
        seen = seen.__cause__ or seen.__context__
        depth += 1


@pytest.mark.parametrize("failure", FAILURE_PATHS, ids=lambda fn: fn.__name__)
async def test_no_failure_path_renders_either_credential(
    failure: Callable[[dict[str, Any]], Awaitable[object]],
    env: ActivityEnvironment,
    context: Callable[..., AttemptContext],
    target_repo: Callable[..., Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    component: dict[str, Any] = {
        "env": env,
        "context": context,
        "repo": target_repo("passing"),
        "workspace": tmp_path,
        "monkeypatch": monkeypatch,
    }
    observed: list[str] = []

    with caplog.at_level(logging.DEBUG):
        raised, value = await _drive(failure, component)

    if raised is not None:
        observed.extend(renderings_of(raised))
    else:
        observed.append(repr(value))
        assert value not in (None, 0), (
            f"{failure.__name__} succeeded; the sweep read a path that does not "
            "fail, and proved nothing about the ones that do"
        )

    # An error path, a log line and a printed diagnostic are the three places a
    # credential travels by accident: each is built from whatever was in hand and
    # read by someone who is not thinking about secrets at the time.
    observed.append(caplog.text)
    observed.extend(repr(record.args) for record in caplog.records)
    printed = capsys.readouterr()
    observed.extend((printed.out, printed.err))
    assert any(observed), f"{failure.__name__} produced nothing to sweep"

    for rendering in observed:
        for secret, name in ((MASTER_KEY, "master key"), (BOT_TOKEN, "bot token")):
            assert secret not in rendering, f"{failure.__name__} leaked the {name}"


async def _drive(
    failure: Callable[[dict[str, Any]], Awaitable[object]], component: dict[str, Any]
) -> tuple[BaseException | None, object]:
    """Run one failure path; hand back whatever fell out of it, exception or value."""
    try:
        return None, await failure(component)
    except BaseException as exc:  # noqa: BLE001 — the sweep reads what fell out
        return exc, None


def _error_name(error: BaseException) -> str:
    """How the failure names itself to a caller: an activity's error `type` when
    it has one, its exception class otherwise."""
    if isinstance(error, ApplicationError) and error.type:
        return error.type
    return type(error).__name__


async def test_the_failure_sweep_reaches_every_error_this_component_raises(
    env: ActivityEnvironment,
    context: Callable[..., AttemptContext],
    target_repo: Callable[..., Path],
    tmp_path: Path,
) -> None:
    """A parametrized sweep is only as good as the paths someone listed.

    So the paths are run once more, together, and what they raised is compared
    against every way this component says it can refuse: the five activity error
    types the workflow branches on, and the four library exceptions underneath
    them. A failure mode added without a line in `FAILURE_PATHS` fails here,
    which is what stops the sweep going quiet as the component grows.

    Each path gets its own monkeypatch scope: two of them break the world on
    purpose — an empty `PATH`, an unloadable registry — and a sweep whose
    fourteenth path ran in the wreckage of its sixth would report the wrong
    error for every one after it.
    """
    from factory.activities.agent_activities import (
        AGENT_LAUNCH_FAILED,
        GRAPH_INVALID,
        PROMPT_SOURCE_MISSING,
        STANDARDS_MISSING,
        WORKTREE_FAILED,
    )

    observed: set[str] = set()
    for failure in FAILURE_PATHS:
        with pytest.MonkeyPatch.context() as patched:
            component: dict[str, Any] = {
                "env": env,
                "context": context,
                "repo": target_repo("passing", name=f"repo-{failure.__name__}"),
                "workspace": tmp_path / failure.__name__,
                "monkeypatch": patched,
            }
            component["workspace"].mkdir(parents=True, exist_ok=True)
            raised, _ = await _drive(failure, component)
        if raised is not None:
            observed.add(_error_name(raised))

    assert observed >= {
        GRAPH_INVALID,
        STANDARDS_MISSING,
        WORKTREE_FAILED,
        AGENT_LAUNCH_FAILED,
        PROMPT_SOURCE_MISSING,
        "AdapterError",
        "DerivationError",
        "PromptAssemblyError",
        "WorkGraphError",
    }, f"the sweep only reached {sorted(observed)}"


#: A credential in a committed file is a leak no runtime test can catch, because
#: nothing has to run for it to be published.
_LITELLM_KEY_RE = re.compile(r"sk-[A-Za-z0-9_\-]{8,}")

#: `<bot-id>:<secret>` — the Bot API's token shape.
_BOT_TOKEN_RE = re.compile(r"\b\d{6,}:[A-Za-z0-9_\-]{30,}\b")


@pytest.mark.parametrize("path", COMPONENT_MODULES, ids=module_id)
def test_no_shipped_module_carries_a_credential_literal(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    found = _LITELLM_KEY_RE.findall(text) + _BOT_TOKEN_RE.findall(text)
    assert not found, f"{module_id(path)} contains what looks like a credential: {found}"


@pytest.mark.parametrize("path", COMPONENT_MODULES, ids=module_id)
def test_this_component_never_names_either_credential(path: Path) -> None:
    """Neither variable is read anywhere in the interpreter.

    001 reads the master key inside its own activities and 002 reads the bot
    token inside its own; this component authenticates with the per-attempt
    virtual key that arrives in its dispatch (constitution V). A module here that
    could even *spell* either name would be a module that could read it, and the
    distance from "can read" to "wrote it into a child's environment" is one
    refactor.
    """
    spelled = code_strings(parse(path)) & {"LITELLM_MASTER_KEY", "TELEGRAM_BOT_TOKEN"}
    assert not spelled, (
        f"{module_id(path)} names {sorted(spelled)} outside its docstrings; the "
        "interpreter has no business reading either credential (constitution V)"
    )


@pytest.mark.parametrize("path", COMPONENT_MODULES, ids=module_id)
def test_the_virtual_key_is_spelled_only_where_it_is_carried_and_read(
    path: Path,
) -> None:
    """One field, one assembly site, one read — and no fourth spelling.

    `AttemptContext.virtual_key` is declared in `models.py`, filled from the
    attempt's `KeyLease` in `workflow.py`, and read by `attempt_env` in
    `adapter.py`. Any other module naming it would be a second thing holding a
    credential, which is how a credential ends up in an error message.
    """
    names_it = "virtual_key" in identifiers(parse(path))
    allowed = {KEY_HOLDER, KEY_READER, WORKFLOW_MODULE}
    if path in allowed:
        assert names_it, (
            f"{module_id(path)} is one of the three modules that carry the "
            "attempt's virtual key and no longer names it — has it moved?"
        )
    else:
        assert not names_it, (
            f"{module_id(path)} names the attempt's virtual key; it lives in "
            "AttemptContext and is read only where the child env is built"
        )


def test_the_virtual_key_is_read_into_exactly_one_environment_variable() -> None:
    """`attempt_env` is the whole of the credential's exit from the component.

    The allowlist is a construction rather than a filter (US2-S1), so what the
    child receives is exactly what this function writes: the proxy URL, the
    attempt's key as `ANTHROPIC_AUTH_TOKEN`, and a passthrough of four names that
    are not credentials.
    """
    tree = parse(ADAPTER_MODULE)
    owner = enclosing_functions(tree)
    readers = {
        owner_name(owner, node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "virtual_key"
    }
    assert readers == {"attempt_env"}, f"the virtual key is read in {sorted(readers)}"

    built = attempt_env(
        AttemptContext(
            epic_id=EPIC,
            node_id=NODE,
            attempt=ATTEMPT,
            prompt=PROMPT,
            worktree_path="/tmp/worktree",
            proxy_url=PROXY_URL,
            virtual_key=VIRTUAL_KEY,
            model_alias=MODEL_ALIAS,
            session_id=SESSION_ID,
            timeout_s=TIMEOUT_S,
        ),
        {
            "PATH": "/usr/bin",
            "HOME": "/home/factory",
            "LITELLM_MASTER_KEY": MASTER_KEY,
            "TELEGRAM_BOT_TOKEN": BOT_TOKEN,
            "SOME_FUTURE_CREDENTIAL": "sk-not-invented-yet",
        },
    )
    assert built == {
        "ANTHROPIC_BASE_URL": PROXY_URL,
        "ANTHROPIC_AUTH_TOKEN": VIRTUAL_KEY,
        "PATH": "/usr/bin",
        "HOME": "/home/factory",
    }


def test_the_credential_sweep_actually_read_the_component() -> None:
    """A parametrized sweep over an empty file list passes without asserting."""
    swept = {module_id(path) for path in COMPONENT_MODULES}
    assert {
        "factory/workgraph/models.py",
        "factory/workgraph/derive.py",
        "factory/workgraph/prompt.py",
        "factory/workgraph/worktree.py",
        "factory/workgraph/adapter.py",
        "factory/workgraph/workflow.py",
        "factory/workgraph/cli.py",
        "factory/activities/agent_activities.py",
        "factory/worker.py",
    } <= swept


# ============================================================================
# 2. FR-012 — nothing the agent reports decides a node
# ============================================================================


def test_the_adapter_returns_a_classification_and_evidence_and_nothing_else() -> None:
    """D-018's narrow output, asserted as the field set.

    No diff, no usage figure, no parsed verdict, no "the agent says it is done":
    a field added here is a new thing the workflow could branch on, and FR-012
    is the rule that it must not.
    """
    assert {field.name for field in AdapterResult.__dataclass_fields__.values()} == {
        "termination",
        "transcript_path",
    }


def test_the_workflow_reads_nothing_off_an_attempt_but_its_termination() -> None:
    """The interpreter's whole use of the adapter's answer is one field.

    `transcript_path` is evidence for a human, so the workflow may carry it into
    history but must never read it — a path is a string an agent can influence,
    and a workflow that inspected one would have a second input to node state.
    """
    tree = parse(WORKFLOW_MODULE)
    read = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "adapter_result"
    }
    assert read == {"termination"}, (
        f"the workflow reads {sorted(read)} off the adapter's result; only the "
        "process classification may reach node state (FR-012)"
    )

    # Every name by which the agent's own output could be reached. `output` on
    # its own is deliberately absent: 002's `check_output` is the write-scope
    # diff check, which reads the *worktree* — what the attempt produced, not
    # what it claimed (FR-004).
    spoken = identifiers(tree) | code_strings(tree)
    for forbidden in ("transcript_path", "stdout", "stderr", "returncode", "exit_code"):
        assert forbidden not in spoken, (
            f"factory/workgraph/workflow.py spells {forbidden!r}; nothing the "
            "agent produced is an input to a scheduling or state decision (FR-012)"
        )


def test_the_exit_status_is_read_in_one_place_and_becomes_a_termination() -> None:
    """Classification is exit status and nothing else (contracts/adapter.md).

    The adapter streams the agent's output straight to a file rather than
    collecting it, so there is no buffer to inspect even by accident — and the
    one place a return code is read produces a `Termination` member on the spot.
    """
    tree = parse(ADAPTER_MODULE)
    owner = enclosing_functions(tree)

    readers = {
        owner_name(owner, node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "returncode"
    }
    assert readers == {"_monitor"}, f"the exit status is read in {sorted(readers)}"

    # Nothing reads what the agent wrote: `communicate()` and `read()` would each
    # put the agent's own words in a variable this module could branch on.
    for forbidden in ("communicate", "readline", "readlines"):
        assert not calls_to(tree, forbidden), (
            f"factory/workgraph/adapter.py calls {forbidden}(); the agent's "
            "output is evidence, never an input to a decision (FR-012)"
        )

    classified = {
        ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "Termination"
    }
    assert classified == {
        "Termination.COMPLETED",
        "Termination.AGENT_ERROR",
        "Termination.TIMEOUT",
    }, f"the adapter classifies {sorted(classified)}"


#: The two modules allowed to read a process's exit status, and what each one is
#: reading: the adapter classifies the *agent* (into a `Termination`, above), and
#: the worktree runner reads *git*, whose failures are infrastructure. A third
#: reader would be a third opinion about how something ended.
_EXIT_STATUS_READERS = frozenset({ADAPTER_MODULE, WORKGRAPH_PACKAGE / "worktree.py"})


@pytest.mark.parametrize("path", COMPONENT_MODULES, ids=module_id)
def test_nothing_else_in_the_component_reads_a_process_at_all(path: Path) -> None:
    """FR-012 as a property of the whole component, not of the adapter alone.

    The activity that wraps the adapter, the workflow that calls the activity,
    the deriver, the prompt assembler and the CLI never touch a return code and
    never collect a child's output. Everything the agent produced reaches a
    human as evidence and reaches the factory as one enum member.
    """
    spoken = identifiers(parse(path))
    forbidden = spoken & {"returncode", "communicate", "check_returncode"}
    if path in _EXIT_STATUS_READERS:
        assert forbidden, (
            f"{module_id(path)} is one of the two modules that read a process's "
            "exit status and no longer does — has the classification moved?"
        )
    else:
        assert not forbidden, (
            f"{module_id(path)} reads {sorted(forbidden)}; only the adapter "
            "classifies the agent, and only the worktree runner reads git (FR-012)"
        )


def test_a_node_state_is_written_from_the_ladders_action_alone() -> None:
    """`NodeState.PASSED` is assigned in one place, under one condition.

    An edge opens on a PASS and on nothing else (FR-003, SC-002), so the
    assignment that produces one has to be reachable only from the ladder's own
    terminal grant. Every other mention of `PASSED` in the workflow is a
    comparison, which is reading state rather than deciding it.
    """
    tree = parse(WORKFLOW_MODULE)
    owner = enclosing_functions(tree)

    granting: list[ast.If] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        assigned = [
            statement
            for statement in node.body
            if isinstance(statement, ast.Assign)
            and "NodeState.PASSED" in ast.unparse(statement.value)
        ]
        if assigned:
            granting.append(node)

    assert len(granting) == 1, (
        f"a node is marked PASSED in {len(granting)} places; the ladder's grant "
        "is the only thing that may open an edge (FR-003)"
    )
    [grant] = granting
    assert ast.unparse(grant.test) == "action == NextAction.PASSED"
    assert owner_name(owner, grant) == "_run_node"


#: Every way an attempt can end, as the adapter classifies it — including the
#: two the workflow supplies when it is the one that ended the attempt.
_TERMINATIONS = list(Termination)


@pytest.mark.parametrize("termination", _TERMINATIONS, ids=lambda t: t.value)
async def test_every_termination_passes_a_green_node_and_fails_a_red_one(
    temporal: Any, termination: Termination
) -> None:
    """FR-012 over the whole product, rather than over one example.

    The claim is symmetric and both halves matter: an agent that crashed, timed
    out, or was killed still passes a node whose gates are green — because the
    worktree may hold work worth keeping and the process's fate is not the
    work's — and an agent that exited zero still fails a node whose gates are
    not. What the agent *said* is nowhere in either sentence.
    """
    green = ScriptedWorld(
        {
            "us1": [Attempt(gates=[gate_pass()], termination=termination)],
            "us2": [passing()],
            "us3": [passing()],
        },
        client=temporal.client,
    )
    status = await run_epic(temporal, green)

    assert states(status)["us1"] == NodeState.PASSED, (
        f"a {termination.value} attempt with green gates did not pass the node"
    )
    assert "run_gates" in green.sequence("us1"), (
        f"a {termination.value} attempt skipped verification (FR-012)"
    )
    # The classification travels to teardown and to the salvage subject, and
    # nowhere else — that is the whole of what it is allowed to influence.
    assert green.teardown_for("us1", 1).termination == termination
    assert [s.termination for s in green.salvages if s.node_id == "us1"] == [termination]

    red = ScriptedWorld(
        {
            "us1": [
                Attempt(gates=[gate_fail(n)], termination=termination)
                for n in (1, 2, 3, 4)
            ],
            "us3": [passing()],
        },
        client=temporal.client,
        press="KILL",
    )
    status = await run_epic(temporal, red)

    assert states(status)["us1"] == NodeState.KILLED, (
        f"a {termination.value} attempt with failing gates reached a terminal "
        "state other than the ladder's"
    )
    assert [r.verdict for r in red.records if r.node_id == "us1"] == [
        OverallVerdict.FAIL
    ] * 4


async def test_an_agent_that_claims_success_over_a_failing_gate_still_fails(
    temporal: Any,
) -> None:
    """The rubber stamp FR-012 exists to catch, in the shape it would arrive in.

    The agent exits zero having "run the gates and committed per task" — its
    inner loop is advisory (FR-006) — and the node's own gate suite disagrees.
    The verdict is 002's, the state is the ladder's, and the dependent edge
    stays shut (SC-002).
    """
    script = ScriptedWorld(
        {"us1": [failing(n) for n in (1, 2, 3, 4)], "us3": [passing()]},
        client=temporal.client,
        press="KILL",
    )

    status = await run_epic(temporal, script)

    assert states(status) == {
        "us1": NodeState.KILLED,
        "us2": NodeState.KILLED,
        "us3": NodeState.PASSED,
    }
    # Every attempt reported COMPLETED — the default script's termination — and
    # not one of them advanced the node.
    assert [t.termination for t in script.teardowns if t.lease.node_id == "us1"] == [
        Termination.COMPLETED
    ] * 4
    assert not [record for record in script.records if record.node_id == "us2"]


# ============================================================================
# 3. SC-002 — no dispatch path with unmet dependencies
# ============================================================================


def test_a_node_is_picked_in_one_place_and_an_agent_started_in_one_place() -> None:
    """SC-002 as a property of the call graph.

    A second scheduler is how "dispatches only when dependencies passed" becomes
    true of one path and false of another, so the claim is first that there is
    only one path: `_next_ready` is the only thing that selects a node,
    `_run_node` is the only thing that runs one, and `run_agent_attempt` is
    started in exactly one function.
    """
    tree = parse(WORKFLOW_MODULE)
    owner = enclosing_functions(tree)

    def callers(name: str) -> set[str]:
        return {owner_name(owner, node) for node in calls_to(tree, name)}

    assert callers("_next_ready") == {"run"}
    assert callers("_run_node") == {"run"}
    assert callers("run_agent_attempt") == set(), (
        "the activity is referenced, never called, inside workflow code"
    )

    started = {
        owner_name(owner, node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and any(
            isinstance(argument, ast.Name) and argument.id == "run_agent_attempt"
            for argument in node.args
        )
    }
    assert started == {"_attempt"}, f"an agent is started in {sorted(started)}"


def test_readiness_is_every_dependency_in_the_passed_state() -> None:
    """The predicate itself, read out of the source (FR-003).

    Not "no dependency failed" and not "the dependency is terminal": a node is
    ready when every dependency holds `NodeState.PASSED`, which is the one state
    an edge may open on.
    """
    ready = function_named(parse(WORKFLOW_MODULE), "_next_ready")
    [predicate] = [
        node
        for node in ast.walk(ready)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "all"
    ]
    source = ast.unparse(predicate)
    assert "NodeState.PASSED" in source
    assert "depends_on" in source
    assert not any(
        weaker in source
        for weaker in ("_TERMINAL_STATES", "_UNREACHABLE", "!=", "not in")
    ), f"readiness is decided by {source}"


def _diamond() -> list[WorkNode]:
    """`us1 → us2 → us3`, with `us3` also depending directly on `us1`.

    Two edges into the last node, so a scheduler that checked only the first
    dependency it found — or only the most recent one — dispatches something it
    should not.
    """
    return [
        make_node("us1", "US1"),
        make_node("us2", "US2", depends_on=["us1"]),
        make_node("us3", "US3", depends_on=["us1", "us2"]),
    ]


#: One epic per way an epic can go: the shape it runs, the world that answers
#: it, and the outcome it has to reach. The expected states are what keeps the
#: sweep from passing vacuously — an epic that died at its first node dispatches
#: nothing on a locked edge for the least interesting reason there is.
_PASSED_ALL = {"us1": NodeState.PASSED, "us2": NodeState.PASSED, "us3": NodeState.PASSED}
_KILLED_ALL = {"us1": NodeState.KILLED, "us2": NodeState.KILLED, "us3": NodeState.KILLED}


#: `(label, world, epic overrides, the states it has to end in)`.
_Epic = tuple[str, ScriptedWorld, dict[str, Any], dict[str, NodeState]]


def _epics(client: Any) -> list[_Epic]:
    return [
        (
            "every node passes",
            ScriptedWorld(all_passing(), client=client),
            {},
            _PASSED_ALL,
        ),
        (
            "the first node of a diamond fails to exhaustion",
            ScriptedWorld(
                {"us1": [failing(n) for n in (1, 2, 3, 4)]},
                client=client,
                press="KILL",
            ),
            {"graph": make_graph(_diamond())},
            _KILLED_ALL,
        ),
        (
            "the middle node of a diamond fails to exhaustion",
            ScriptedWorld(
                {"us1": [passing()], "us2": [failing(n) for n in (1, 2, 3, 4)]},
                client=client,
                press="KILL",
            ),
            {"graph": make_graph(_diamond())},
            {
                "us1": NodeState.PASSED,
                "us2": NodeState.KILLED,
                "us3": NodeState.KILLED,
            },
        ),
        (
            "an operator kills the epic mid-attempt",
            ScriptedWorld(
                all_passing(),
                client=client,
                signal_during={"us1": "kill_epic"},
                await_cancel=True,
            ),
            {},
            _KILLED_ALL,
        ),
        (
            "an escalation grants one more attempt, which passes",
            ScriptedWorld(
                {
                    "us1": [failing(1), failing(2), failing(3), failing(4), passing()],
                    "us2": [passing()],
                    "us3": [passing()],
                },
                client=client,
                press="RETRY",
            ),
            {},
            _PASSED_ALL,
        ),
    ]


async def test_no_epic_ever_dispatches_a_node_with_an_unmet_dependency(
    temporal: Any,
) -> None:
    """SC-002 over every shape an epic can end in, asserted from mid-flight.

    The scripted agent queries `epic_status` while it is the in-flight node, so
    each dispatch is checked against the epic's state at the moment it happened
    rather than against the snapshot left at the end — a terminal snapshot cannot
    tell an edge that unlocked on a PASS from one that unlocked on a hope.

    Five epics: one that passes, two whose diamond loses a node at a different
    depth, one an operator kills mid-attempt, and one where a human grants an
    attempt that then succeeds. Between them every way a node stops being
    dispatchable is exercised, and no run may dispatch anything on a locked edge.
    """
    for label, script, overrides, expected in _epics(temporal.client):
        graph = overrides.get("graph") or make_graph()
        depends_on = {node.id: node.depends_on for node in graph.nodes}

        status = await run_epic(temporal, script, **overrides)

        # The epic went where its script sends it: an epic that ended somewhere
        # else dispatches nothing on a locked edge for reasons of its own.
        assert states(status) == expected, f"{label}: ended {states(status)}"
        assert script.observed, f"{label}: nothing was ever dispatched"
        for node_id, seen in script.observed.items():
            during = states(seen)
            for dependency in depends_on[node_id]:
                assert during[dependency] == NodeState.PASSED, (
                    f"{label}: {node_id} was dispatched while {dependency} was "
                    f"{during[dependency]} (SC-002)"
                )

        # And the converse, from the outside: nothing that never became PASSED
        # has a dependent among the nodes that ran.
        final = states(status)
        dispatched = set(script.dispatched)
        for node_id, dependencies in depends_on.items():
            if node_id not in dispatched:
                continue
            for dependency in dependencies:
                assert final[dependency] == NodeState.PASSED, (
                    f"{label}: {node_id} ran although {dependency} ended "
                    f"{final[dependency]}"
                )

        assert "overrun" not in script.calls, f"{label}: the script ran out"
        assert "unscripted" not in script.calls, f"{label}: an unscripted node ran"


# ============================================================================
# 4. FR-007 — no transcript path under any repo worktree
# ============================================================================


def test_transcripts_and_worktrees_are_siblings_under_the_factory_root() -> None:
    """The two paths, side by side: neither can ever contain the other.

    Both are computed from the same root by the same two helpers, so the claim
    is checkable directly rather than by inspection — and it holds for the
    awkward case where the factory root sits *inside* the target clone, which is
    what an operator who cloned into the wrong directory produces.
    """
    for root in (Path("/srv/factory/.factory"), Path("/srv/repo/.factory")):
        archive = transcript_dir(root, EPIC, NODE, ATTEMPT)
        tree = worktree_path(root, EPIC, NODE)
        pids = pid_file(root, EPIC, NODE)

        assert not archive.is_relative_to(tree), (
            f"the attempt archive {archive} is inside the node's worktree; the "
            "salvage that follows it would commit the agent's own transcript"
        )
        assert not tree.is_relative_to(archive)
        assert not pids.is_relative_to(tree)
        assert archive.is_relative_to(root) and tree.is_relative_to(root)
        assert archive.parts[len(root.parts)] == "transcripts"
        assert tree.parts[len(root.parts)] == "worktrees"


def test_the_archive_is_located_from_the_factory_root_and_never_from_a_worktree() -> None:
    """Every call site of `transcript_dir`, and what it is handed.

    The path is built from the worker host's state directory in both places it
    is built at all — the adapter and the activity that wraps it. A call passing
    a worktree, a target repo, or the attempt's own `worktree_path` would put the
    evidence inside a checkout, which is the failure FR-007 names.
    """
    roots: dict[str, set[str]] = {}
    for path in COMPONENT_MODULES:
        for call in calls_to(parse(path), "transcript_dir"):
            if call.args:
                roots.setdefault(module_id(path), set()).add(ast.unparse(call.args[0]))

    assert roots == {
        "factory/workgraph/adapter.py": {"factory_root"},
        "factory/activities/agent_activities.py": {"root"},
    }, f"transcript_dir is called with {roots}"

    # And the name the activity binds is the resolver's answer, not a path that
    # arrived in the request.
    tree = parse(COMPONENT_ROOT / "activities" / "agent_activities.py")
    [assignment] = [
        node
        for node in ast.walk(function_named(tree, "run_agent_attempt"))
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "root"
            for target in node.targets
        )
    ]
    assert ast.unparse(assignment.value) == "factory_root()"


async def test_a_real_attempt_archives_outside_every_checkout_and_salvage_keeps_it_out(
    context: Callable[..., AttemptContext],
    target_repo: Callable[..., Path],
    factory_root: Path,
    worker_host: Path,
) -> None:
    """The whole of FR-007 against a real repository, not against path algebra.

    A node's real worktree is prepared with `worktrees.ensure`, the real adapter
    runs the stub agent in it, and then the terminal pair constitution VI
    requires runs: salvage, then remove. Three things then have to be true at
    once — the archive is outside every checkout, the salvage commit contains no
    part of it, and the evidence survives the sweep that deletes the worktree.
    """
    repo = target_repo("passing")
    prepared = worktrees.ensure(repo, EPIC, NODE, factory_root=factory_root)
    tree = Path(prepared.path)
    assert tree == worktree_path(factory_root, EPIC, NODE)

    write_control(worker_host, stdout="agent: implemented US1")
    adapter = ClaudeCodeAdapter(executable=str(STUB_AGENT_PATH))
    result = await adapter.run_attempt(
        context(worktree_path=str(tree)), factory_root=factory_root
    )
    assert result.termination is Termination.COMPLETED

    archive = Path(result.transcript_path)
    assert archive.is_dir() and (archive / STDOUT_LOG_NAME).is_file()
    assert (archive / f"{SESSION_ID}.jsonl").is_file()
    assert not archive.is_relative_to(tree), "the transcript archived into the worktree"
    assert not archive.is_relative_to(repo), "the transcript archived into the clone"

    # The two filenames the archive is made of. Neither may appear anywhere
    # inside a checkout, whatever else the agent left behind there.
    evidence = {STDOUT_LOG_NAME, f"{SESSION_ID}.jsonl"}
    for checkout in (tree, repo):
        found = {path.name for path in checkout.rglob("*") if path.is_file()} & evidence
        assert not found, f"{sorted(found)} was written inside {checkout}"

    sha = worktrees.salvage(
        EPIC,
        NODE,
        termination=result.termination,
        attempt=ATTEMPT,
        factory_root=factory_root,
    )
    committed = _committed_files(repo, sha)
    assert committed, "the salvage commit recorded nothing at all"
    for name in evidence:
        assert not any(Path(entry).name == name for entry in committed), (
            f"the salvage commit carries {name} — the agent's own transcript is "
            "now in the target repository's history (FR-007)"
        )
    assert not any(entry.startswith("transcripts/") for entry in committed)

    # And the sweep takes the worktree, never the evidence: once `.factory/` is
    # the only account of the attempt, the archive has to still be in it.
    worktrees.remove(repo, EPIC, NODE, factory_root=factory_root)
    assert not tree.exists()
    assert (archive / STDOUT_LOG_NAME).is_file()
    assert _branch_subject(repo, branch_name(EPIC, NODE)).endswith(f"attempt {ATTEMPT}")


def _committed_files(repo: Path, sha: str) -> list[str]:
    """The paths one commit touched, relative to the repository root."""
    listing = git(repo, "show", "--name-only", "--format=", sha)
    return [line.strip() for line in listing.splitlines() if line.strip()]


def _branch_subject(repo: Path, branch: str) -> str:
    return git(repo, "log", "-1", "--format=%s", branch).strip()


async def test_a_killed_attempt_archives_outside_the_worktree_too(
    context: Callable[..., AttemptContext],
    target_repo: Callable[..., Path],
    factory_root: Path,
    worker_host: Path,
) -> None:
    """The path FR-007 is really about: the one where the agent did not finish.

    A killed attempt is where evidence matters most and where an archive step
    is most easily skipped, so the kill path is swept as well as the clean one —
    the archive lands under `.factory/`, and the worktree the operator is about
    to salvage holds none of it.
    """
    repo = target_repo("passing")
    prepared = worktrees.ensure(repo, EPIC, NODE, factory_root=factory_root)
    tree = Path(prepared.path)

    write_control(worker_host, sleep_s=30.0)
    adapter = ClaudeCodeAdapter(executable=str(STUB_AGENT_PATH), grace_s=0.4)
    attempt = asyncio.ensure_future(
        adapter.run_attempt(context(worktree_path=str(tree)), factory_root=factory_root)
    )

    deadline = asyncio.get_running_loop().time() + 20.0
    while not list(tree.glob(".stub-agent/*/stdin.txt")):
        assert asyncio.get_running_loop().time() < deadline, "the stub never launched"
        await asyncio.sleep(0.02)

    attempt.cancel()
    with pytest.raises(asyncio.CancelledError):
        await attempt

    archive = transcript_dir(factory_root, EPIC, NODE, ATTEMPT)
    assert (archive / STDOUT_LOG_NAME).is_file()
    assert not archive.is_relative_to(tree)
    for name in (STDOUT_LOG_NAME, f"{SESSION_ID}.jsonl"):
        assert not any(path.name == name for path in tree.rglob("*")), (
            f"{name} was written inside the worktree on the kill path"
        )
