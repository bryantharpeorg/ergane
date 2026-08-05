"""The one test that runs a whole epic: real server, real proxy, real agent.

Every other test of this component runs the interpreter against something that
agrees with it by construction — `WorkflowEnvironment.start_time_skipping()` with
scripted activities, the adapter against `tests/stub_agent.py`, worktrees against
`tmp_path` git repos. That proves the orchestration is right and proves nothing
at all about whether the *outside world* is shaped the way this component
believes. Four beliefs in particular have no other test:

- `claude -p --model <alias> --session-id <uuid>` with a prompt on stdin is a
  real invocation of a real binary, and `ANTHROPIC_BASE_URL` +
  `ANTHROPIC_AUTH_TOKEN` are the two variables that make it authenticate as this
  attempt's virtual key against the operator's proxy (R6).
- Claude Code still writes its session transcript to
  `$HOME/.claude/projects/<munged-cwd>/<session-id>.jsonl`, which is the rule
  `adapter.project_dir_name` reproduces in order to archive it. That rule belongs
  to the CLI, not to this factory; the adapter's docstring says this smoke is
  what proves the two still agree, and this is that assertion (FR-007).
- A registered worker really does serve every activity the interpreter schedules
  — `tests/test_worker.py` reads the names out of the workflow's syntax tree, but
  only a live run proves an epic gets through them all rather than waiting on one
  nobody is polling.
- The three records an epic leaves behind — ledger row, verification row,
  salvage commit — really do agree, attempt for attempt, when the numbers come
  from a proxy rather than from a fake (SC-003, SC-004).

This is the SC-005 rehearsal, per quickstart §4: the 003 crossover is this same
shape pointed at `specs/003-merge-queue/` and a clone of this repository, so
anything that would derail the bootstrap epic should derail this first, at the
cost of one small node instead of a feature's worth of model time.

**The epic.** A scratch git repo containing one failing check, and a one-story
spec that asks for the module which makes it pass:

    check_greet.py   `greet("Ergane") == "Hello, Ergane!"` — red until the node works
    factory.yaml     one gate, `unittest check_greet`; `standards: STANDARDS.md`
    <specs>/<epic>/  spec.md (US1 → FR-001, `## Work Graph`), plan.md, tasks.md

Nothing about it is stubbed: the node's worktree is a real `git worktree`, the
gate is a real subprocess, the key is a real LiteLLM key, and the agent is
whatever `claude` does with the prompt this factory assembled.

Five deliberate choices:

- **One run, many assertions.** A live epic costs an operator real minutes and
  real model spend, so the module-scoped `live_epic` fixture runs it exactly
  once and every test below reads a different facet of that one run.

- **The worker is this process, on a task queue scoped to the run.** The
  registration is production's — `factory.worker.WORKFLOWS` and `ACTIVITIES`,
  imported, not re-listed — but the queue name is not, because quickstart §4 also
  tells the operator to run `python -m factory.worker` on the `workgraph` queue.
  Two workers on one queue would split this epic's activities between them, and
  the operator's worker resolves `.factory/` against *its* working directory —
  so half the evidence this test asserts on would land somewhere it never looks.
  Scoping the queue makes the smoke immune to whatever else the host is running;
  that the CLI, the worker and the workflow agree on the production queue string
  is `tests/test_epic_cli.py`'s and `tests/test_worker.py`'s assertion, not this
  one's.

- **`derive` and `status` run through the real CLI**, because they are the
  operator's actual commands (FR-009) and neither of them cares which queue the
  epic runs on. Only `start` is done through the client, for the reason above.

- **The ladder is capped to one attempt and no debugger cycle.** That is the
  smoke's blast radius, not an opinion about production defaults: a broken
  deployment should report in minutes rather than spend three attempts plus a
  debugger cycle discovering the same thing. The ladder's own behaviour is
  proven exhaustively under time skipping, where an hour costs nothing.

- **It skips, it does not fail, when Tier 1 is not there.** No proxy, no `claude`
  on `PATH`, a persona registry still carrying the shipped `CHANGEME` aliases, or
  no dev server answering means nobody asked for a live run: `uv run pytest -q`
  stays a pure-unit suite and `-m live_epic` selects this.

**A known risk this smoke exists to surface.** The dispatch prompt's inner loop
tells the agent to commit once per task (contracts/prompt-assembly.md), while
002's output check reads "did this node do work?" as *worktree versus HEAD* — so
an agent that commits everything it wrote leaves a clean tree and fails the check
that exists to catch agents which wrote nothing (`factory/verify/diffcheck.py`
states that reading explicitly). If this test fails with `us1` FAILED, a green
`test` gate and `output_check.has_diff` false, that contradiction is what it
caught, and the fix is a decision about the two contracts rather than about this
file — which is why the failure message below prints the recorded evidence
instead of just a state name.

Optional knobs, on top of the Tier 1 environment quickstart §4 lists:

    LIVE_EPIC_TIMEOUT_S   the node's attempt deadline, seconds (default 900).
                          Declared as the story's `## Work Graph` override, so
                          it is the operator's dial exactly the way FR-010 says.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import shlex
import shutil
import sqlite3
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import pytest
from temporalio.client import Client
from temporalio.service import RPCError, RPCStatusCode
from temporalio.worker import Worker

from factory import worker as factory_worker
from factory.activities.agent_activities import FACTORY_ROOT_ENV
from factory.activities.usage_activities import LEDGER_PATH_ENV
from factory.activities.verify_activities import VERIFICATION_DB_PATH_ENV
from factory.config import load_personas
from factory.notify.service import (
    DEFAULT_TEMPORAL_ADDRESS,
    DEFAULT_TEMPORAL_NAMESPACE,
    TEMPORAL_ADDRESS_ENV,
    TEMPORAL_NAMESPACE_ENV,
)
from factory.usage.litellm_client import MASTER_KEY_ENV, PROXY_URL_ENV
from factory.usage.models import Termination
from factory.verify.models import VerificationConfig
from factory.workgraph import cli
from factory.workgraph.adapter import (
    DEFAULT_EXECUTABLE,
    STDOUT_LOG_NAME,
    transcript_dir,
)
from factory.workgraph.models import EpicState, NodeState
from factory.workgraph.workflow import EpicInput, EpicWorkflow
from factory.workgraph.worktree import branch_name, salvage_message, worktree_path
from tests.target_repo import git

#: Selected with `-m live_epic`, deselected with `-m "not live_epic"`; skipped
#: outright without Tier 1 infrastructure (see `live_config`).
pytestmark = pytest.mark.live_epic

#: The one node. `us1` is what the deriver mints from story `US1`, and it names
#: the branch, the worktree and the transcript directory alike.
NODE_ID = "us1"
STORY_KEY = "US1"
ATTEMPT = 1

#: The persona the deriver routes every story to, and therefore the registry
#: entry whose alias and `timeout` this run reads (constitution VII).
PERSONA = "implementer"

#: The placeholder the shipped `personas.yaml` carries. An epic dispatched with
#: it would ask the proxy to route a model nobody configured, so it is a skip
#: (quickstart §4: "personas.yaml aliases set to real proxy aliases").
PLACEHOLDER_ALIAS = "CHANGEME"

#: The node's attempt deadline, declared as the story's `## Work Graph`
#: override so it wins over the registry's four production hours (FR-010).
TIMEOUT_ENV = "LIVE_EPIC_TIMEOUT_S"
DEFAULT_TIMEOUT_S = 900

#: Room on top of the attempt deadline for everything around it: the first
#: checkout of the scratch repo, the gate run, key teardown, salvage and sweep.
RUN_GRACE_S = 600

#: Short enough that a minutes-long attempt is polled several times (R3), so the
#: live run exercises the loop rather than skipping straight to teardown.
POLL_INTERVAL_S = 15

#: The smoke's blast radius (see the module docstring): one attempt, no debugger
#: cycle, and an escalation nobody has to answer for an hour.
SMOKE_LADDER = VerificationConfig(
    max_attempts=1,
    debugger_cycles=0,
    gate_timeout_s=300,
    escalation_timeout_s=60,
)

#: What the node has to produce, and the check that decides whether it did.
WORK_FILE = "greet.py"
CHECK_MODULE = "check_greet"
GREETED = "Ergane"
GREETING = f"Hello, {GREETED}!"

STANDARDS_FILE = "STANDARDS.md"
GATE_NAME = "test"

# --- the scratch repository ---------------------------------------------------

CHECK_SOURCE = f'''"""The gate this epic's node has to turn green (see factory.yaml)."""

import unittest


class GreetTest(unittest.TestCase):
    def test_greets_by_name(self) -> None:
        # Imported inside the test so a missing module fails this check rather
        # than breaking collection: red before the node runs is the point.
        from {WORK_FILE.removesuffix(".py")} import greet

        self.assertEqual(greet({GREETED!r}), {GREETING!r})


if __name__ == "__main__":
    unittest.main()
'''

STANDARDS_SOURCE = f"""# Standards for this repository

- The standard library only. Add no dependency and no network call.
- Do not edit `{CHECK_MODULE}.py`: it is the acceptance check, not your work.
- Keep the change to what the task slice asks for.
"""

#: `<TIMEOUT>` is replaced with the resolved deadline; nothing else interpolates,
#: so the documents below read exactly as an author would have written them.
SPEC_SOURCE = f"""# Feature Specification: Greeting

**Feature Branch**: `live-epic`

**Created**: 2026-08-05

**Status**: Draft

**Input**: The Tier 1 smoke's scratch epic — one story, one requirement, one node.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Greet by name (Priority: P1)

As this repository's caller, I can ask for a greeting by name and get one back,
so that the committed acceptance check passes.

**Why this priority**: It is the only story in this epic.

**Independent Test**: Run the repository's `{GATE_NAME}` gate and see it pass.

**Acceptance Scenarios**:

1. **Given** this repository, **When** `greet({GREETED!r})` is called, **Then** it returns `{GREETING}`.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The repository MUST provide `{WORK_FILE}` at its root, exposing a
  function `greet(name)` that returns the string `Hello, <name>!`, so that the
  committed `{CHECK_MODULE}.py` passes unchanged.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The repository's `{GATE_NAME}` gate exits zero in the node's worktree.

## Work Graph

```yaml
{STORY_KEY}:
  depends_on: []
  implements: [FR-001]
  timeout: <TIMEOUT>
```
"""

PLAN_SOURCE = f"""# Implementation Plan: Greeting

**Summary**: One module at the repository root, standard library only, no new
files beyond `{WORK_FILE}`.

**Testing**: `{CHECK_MODULE}.py` is already committed and is the whole of this
epic's acceptance check. It is not to be edited.

**Constraints**: No dependency may be added; nothing outside this worktree is
touched.
"""

TASKS_SOURCE = f"""# Tasks: Greeting

## Phase 3: User Story 1 - Greet by name (Priority: P1)

- [ ] T001 Create `{WORK_FILE}` at the repository root with a `greet(name)`
  function returning the string `Hello, ` followed by the name and `!`.
- [ ] T002 Run the repository's `{GATE_NAME}` gate (the command its
  `factory.yaml` declares) and leave it green. Do not edit `{CHECK_MODULE}.py`.
"""


def manifest_source(gate_command: str) -> str:
    """The scratch repo's `factory.yaml`, declaring its gate and its standards."""
    return f"""# What "green" means for this scratch repository (schema v1).

version: 1
runtime: python:3.11-bookworm

gates:
  {GATE_NAME}: {json.dumps(gate_command)}

timeouts:
  {GATE_NAME}: {SMOKE_LADDER.gate_timeout_s}

standards: {STANDARDS_FILE}
"""


# --- environment --------------------------------------------------------------


@dataclass(frozen=True)
class LiveConfig:
    """Tier 1, as the operator's environment and registry describe it."""

    proxy_url: str
    #: Never asserted against by value — only its absence from evidence is.
    master_key: str
    model_alias: str
    address: str
    namespace: str
    timeout_s: int


@dataclass(frozen=True)
class Workspace:
    """The scratch epic: where its repo, its spec and its state directory live."""

    epic_id: str
    target_repo: Path
    specs_root: Path
    spec_dir: Path
    factory_root: Path
    ledger_path: Path
    verification_db: Path
    task_queue: str

    @property
    def branch(self) -> str:
        return branch_name(self.epic_id, NODE_ID)

    @property
    def worktree(self) -> Path:
        return worktree_path(self.factory_root, self.epic_id, NODE_ID)

    @property
    def archive(self) -> Path:
        return transcript_dir(self.factory_root, self.epic_id, NODE_ID, ATTEMPT)


@dataclass(frozen=True)
class LiveEpic:
    """One real epic, and everything the assertions below read it through."""

    config: LiveConfig
    workspace: Workspace
    #: The workflow's own result — the `EpicStatus` an operator would query.
    status: Any


@pytest.fixture(scope="module")
def live_config() -> LiveConfig:
    """Tier 1 infrastructure, or a skip naming what is missing."""
    proxy_url = os.environ.get(PROXY_URL_ENV)
    master_key = os.environ.get(MASTER_KEY_ENV)
    if not proxy_url or not master_key:
        pytest.skip(
            f"live-epic smoke needs {PROXY_URL_ENV} and {MASTER_KEY_ENV} in the "
            "environment (quickstart §4)"
        )

    if shutil.which(DEFAULT_EXECUTABLE) is None:
        pytest.skip(
            f"live-epic smoke needs the '{DEFAULT_EXECUTABLE}' CLI on PATH — it "
            "is the agent this factory dispatches (D-018, spec § Assumptions)"
        )

    # The registry, not a constant: which model an implementer node runs is
    # `personas.yaml`'s answer and nothing else's (constitution VII).
    alias = load_personas()[PERSONA].model
    if not alias or PLACEHOLDER_ALIAS in alias:
        pytest.skip(
            f"persona '{PERSONA}' still names the shipped placeholder alias "
            f"{alias!r}; set personas.yaml to real proxy aliases (quickstart §4)"
        )

    return LiveConfig(
        proxy_url=proxy_url,
        master_key=master_key,
        model_alias=alias,
        address=os.environ.get(TEMPORAL_ADDRESS_ENV) or DEFAULT_TEMPORAL_ADDRESS,
        namespace=os.environ.get(TEMPORAL_NAMESPACE_ENV) or DEFAULT_TEMPORAL_NAMESPACE,
        timeout_s=_positive_int(os.environ.get(TIMEOUT_ENV), DEFAULT_TIMEOUT_S),
    )


@pytest.fixture(scope="module")
def live_epic(
    live_config: LiveConfig, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[LiveEpic]:
    """Run one whole epic, once, against scratch state the tests can read.

    Only the three worker-host state paths are patched — the state directory, the
    ledger and the evidence store — so a smoke run never writes into the
    operator's real `.factory/`. The proxy credentials, the Temporal address and
    the persona registry stay exactly as the operator set them, because reading
    *those* from the deployment is the behaviour under test.
    """
    workspace = build_workspace(tmp_path_factory.mktemp("live-epic"), live_config)

    with pytest.MonkeyPatch.context() as patch:
        patch.setenv(FACTORY_ROOT_ENV, str(workspace.factory_root))
        patch.setenv(LEDGER_PATH_ENV, str(workspace.ledger_path))
        patch.setenv(VERIFICATION_DB_PATH_ENV, str(workspace.verification_db))

        # The worker runs on its own loop in its own thread and STAYS UP while
        # the tests below read the epic's leavings, because that is the shape
        # of production: an operator's `python -m factory.worker` outlives any
        # one epic, and `factory-epic status` serves its query through a live
        # poller — a worker torn down with the workflow would make the status
        # test fail with "no poller seen", found live 2026-08-05.
        loop = asyncio.new_event_loop()
        thread = threading.Thread(
            target=loop.run_forever, name="live-epic-worker", daemon=True
        )
        thread.start()
        stop = asyncio.Event()
        ready: concurrent.futures.Future[Any] = concurrent.futures.Future()
        serving = asyncio.run_coroutine_threadsafe(
            serve_epic(live_config, workspace, ready, stop), loop
        )
        try:
            # `pytest.skip`/`pytest.fail` raised inside the worker thread land
            # here and do their job in this one.
            status = ready.result(timeout=live_config.timeout_s + RUN_GRACE_S + 60)
            yield LiveEpic(config=live_config, workspace=workspace, status=status)
        finally:
            loop.call_soon_threadsafe(stop.set)
            try:
                serving.result(timeout=30)
            except (concurrent.futures.TimeoutError, Exception):
                pass  # the epic's own outcome was already delivered via `ready`
            loop.call_soon_threadsafe(loop.stop)
            thread.join(timeout=10)
            loop.close()


# --- building the scratch epic -------------------------------------------------


def build_workspace(root: Path, config: LiveConfig) -> Workspace:
    """Write the target repo and the epic's spec, then compile the graph.

    The epic id is minted per run because three different stores key on it and
    all three outlive the test: LiteLLM refuses a duplicate `key_alias`, Temporal
    a duplicate running workflow id, and git a branch that already exists.
    """
    epic_id = f"live-epic-{int(time.time())}"
    specs_root = root / "specs"
    spec_dir = specs_root / epic_id
    workspace = Workspace(
        epic_id=epic_id,
        target_repo=build_scratch_repo(root / "target-repo"),
        specs_root=specs_root,
        spec_dir=spec_dir,
        factory_root=root / ".factory",
        ledger_path=root / ".factory" / "ledger.db",
        verification_db=root / ".factory" / "verification.db",
        # Scoped to this run: see the module docstring.
        task_queue=f"workgraph-{epic_id}",
    )

    spec_dir.mkdir(parents=True)
    (spec_dir / "spec.md").write_text(
        SPEC_SOURCE.replace("<TIMEOUT>", str(config.timeout_s)), encoding="utf-8"
    )
    (spec_dir / "plan.md").write_text(PLAN_SOURCE, encoding="utf-8")
    (spec_dir / "tasks.md").write_text(TASKS_SOURCE, encoding="utf-8")

    # The operator's own command (contracts/cli.md), not a call into the deriver:
    # `derive` is half of what quickstart §4 exercises, and it needs no server.
    status = cli.main(
        [
            "derive",
            str(spec_dir),
            "--target-repo",
            str(workspace.target_repo),
            "--specs-root",
            str(specs_root),
        ]
    )
    assert status == cli.EXIT_OK, "factory-epic derive refused the smoke's own spec"
    return workspace


def build_scratch_repo(path: Path) -> Path:
    """A one-commit git repo holding a red check, its gate, and its standards.

    Deliberately not `tests/fixtures/target_repo/`: that fixture's gates exist to
    be scripted (they pass, hang, or defy SIGTERM on command), and this one needs
    a gate that is red now and green only if a real agent writes real code.
    """
    path.mkdir(parents=True)
    (path / f"{CHECK_MODULE}.py").write_text(CHECK_SOURCE, encoding="utf-8")
    (path / STANDARDS_FILE).write_text(STANDARDS_SOURCE, encoding="utf-8")
    # Like any real target repo: generated noise is ignored, and ignored files
    # stay out of the diff the judge scores. Without this the gate run's
    # `__pycache__` reached the judge as if it were the attempt's work.
    (path / ".gitignore").write_text("__pycache__/\n*.pyc\n", encoding="utf-8")
    # `sys.executable` rather than `python3`: the gate must fail because the node
    # failed, never because the worker host spells its interpreter differently.
    (path / "factory.yaml").write_text(
        manifest_source(f"{shlex.quote(sys.executable)} -m unittest {CHECK_MODULE}"),
        encoding="utf-8",
    )

    git(path, "init", "-b", "main", "--quiet")
    git(path, "add", "-A")
    git(path, "commit", "--quiet", "-m", "Scratch target repo for the live-epic smoke")
    return path


# --- the live run --------------------------------------------------------------


async def serve_epic(
    config: LiveConfig,
    workspace: Workspace,
    ready: concurrent.futures.Future[Any],
    stop: asyncio.Event,
) -> None:
    """Run the epic, deliver its outcome through `ready`, and keep serving.

    The registration handed to the worker is `factory/worker.py`'s, imported
    rather than restated: a live run that registered its own convenient subset
    would prove nothing about the process an operator actually starts. The
    worker outlives the workflow — until `stop` — so the queries the tests
    make (`factory-epic status` above all) have the live poller they would
    have in production.
    """
    try:
        client = await connect(config)
        graph = cli.load_workgraph(workspace.spec_dir / cli.ARTIFACT_NAME)

        async with Worker(
            client,
            task_queue=workspace.task_queue,
            workflows=factory_worker.WORKFLOWS,
            activities=factory_worker.ACTIVITIES,
        ):
            handle = await start(client, config, workspace, graph)
            try:
                ready.set_result(
                    await asyncio.wait_for(
                        handle.result(), timeout=config.timeout_s + RUN_GRACE_S
                    )
                )
            except (asyncio.TimeoutError, TimeoutError):
                # Leaving it running would go on spending against the
                # operator's proxy long after this terminal has closed.
                await handle.terminate("live-epic smoke exceeded its own deadline")
                ready.set_exception(
                    pytest.fail.Exception(
                        f"the epic did not finish within "
                        f"{config.timeout_s + RUN_GRACE_S}s and was terminated; "
                        f"the attempt deadline is {config.timeout_s}s (raise it "
                        f"with {TIMEOUT_ENV})"
                    )
                )
                return
            await stop.wait()
    except BaseException as error:  # noqa: BLE001 — the fixture re-raises it
        if not ready.done():
            ready.set_exception(error)
        raise


async def connect(config: LiveConfig) -> Client:
    """The operator's dev server, or a skip naming the address that did not answer."""
    try:
        return await Client.connect(config.address, namespace=config.namespace)
    except (RPCError, RuntimeError, OSError) as error:
        pytest.skip(
            f"live-epic smoke needs a Temporal server at {config.address} "
            f"(namespace '{config.namespace}'): {error}"
        )


async def start(
    client: Client, config: LiveConfig, workspace: Workspace, graph: Any
) -> Any:
    """Dispatch the compiled graph under the id `factory-epic status` reads."""
    try:
        return await client.start_workflow(
            EpicWorkflow.run,
            EpicInput(
                graph=graph,
                proxy_url=config.proxy_url,
                config=SMOKE_LADDER,
                poll_interval_s=POLL_INTERVAL_S,
            ),
            id=cli.workflow_id(workspace.epic_id),
            task_queue=workspace.task_queue,
        )
    except RPCError as error:
        if error.status is RPCStatusCode.NOT_FOUND:
            pytest.skip(
                f"the Temporal server at {config.address} has no namespace "
                f"'{config.namespace}' (quickstart §4 creates it): {error}"
            )
        raise


# --- reading what the run left behind ------------------------------------------


def node(live: LiveEpic) -> Any:
    """The one node's status, off the workflow's own result."""
    return live.status.nodes[NODE_ID]


def ledger_row(
    live: LiveEpic, persona: str = PERSONA
) -> dict[str, Any] | None:
    """One persona's usage row, read the way quickstart §5 reads it: plain SQL.

    Persona is part of the selector because it is part of the key's identity
    (D-026): a scored attempt leaves TWO rows for the same epic/node/attempt —
    the implementer's and the judge's — and a query without the persona picks
    one of them by accident.
    """
    return _row(
        live.workspace.ledger_path,
        "SELECT * FROM usage_records WHERE epic_id = ? AND node_id = ? "
        "AND attempt = ? AND persona = ?",
        (live.workspace.epic_id, NODE_ID, ATTEMPT, persona),
    )


def verification_row(live: LiveEpic) -> dict[str, Any] | None:
    """The attempt's evidence row (002's store), likewise raw."""
    return _row(
        live.workspace.verification_db,
        "SELECT * FROM verification_results WHERE epic_id = ? AND node_id = ? "
        "AND attempt = ?",
        (live.workspace.epic_id, NODE_ID, ATTEMPT),
    )


def _row(path: Path, sql: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
    if not path.exists():
        return None
    connection = sqlite3.connect(path)
    try:
        cursor = connection.execute(sql, params)
        row = cursor.fetchone()
        if row is None:
            return None
        return {column[0]: value for column, value in zip(cursor.description, row)}
    finally:
        connection.close()


def evidence(live: LiveEpic) -> str:
    """What actually happened, rendered for a failing assertion.

    A node that did not pass is the interesting failure and the expensive one to
    reproduce, so the message carries the recorded verdict, every gate's status
    and tail, and the output check — the same three things an operator would open
    the evidence store to read (and the three that distinguish the contradiction
    named in the module docstring from an agent that simply could not do it).
    """
    record = verification_row(live)
    if record is None:
        return "no verification row was recorded for this attempt"

    gates = json.loads(record["gate_results"])
    lines = [f"verdict {record['verdict']}, output_check {record['output_check']}"]
    lines += [
        f"gate {gate['name']}: {gate['status']} (exit {gate['exit_code']})\n"
        f"{gate['output_tail']}"
        for gate in gates
    ]
    return "\n".join(lines)


def _positive_int(raw: str | None, default: int) -> int:
    try:
        value = int(raw) if raw else default
    except ValueError:
        return default
    return value if value > 0 else default


# --- the node passed, and the epic finished (SC-005 rehearsal) -----------------


def test_the_node_passed_and_the_epic_completed(live_epic: LiveEpic) -> None:
    """A real agent, on a real key, produced work a real gate accepted.

    The whole point of the run: no fake anywhere in the path from the prompt this
    factory assembled to the verdict 002's gates returned.
    """
    assert node(live_epic).state == NodeState.PASSED, evidence(live_epic)
    assert live_epic.status.epic_state == EpicState.COMPLETED
    assert set(live_epic.status.nodes) == {NODE_ID}


def test_the_node_passed_on_its_first_attempt(live_epic: LiveEpic) -> None:
    # Not a fact about agent quality — the ladder is capped at one attempt here,
    # so a second would have been an escalation. It is the assertion that the
    # attempt counter an operator reads matches the attempt the stores recorded.
    assert node(live_epic).attempt == ATTEMPT


# --- the work survived (constitution VI, SC-004) -------------------------------


def test_the_branch_holds_the_salvage_commit_for_the_attempt(
    live_epic: LiveEpic,
) -> None:
    """The branch alone accounts for how the node ended, once `.factory/` is gone.

    Subject compared against `salvage_message`, because that string is the
    per-attempt idempotency key as well as the account: a live run that spelled
    it differently would salvage twice on an activity retry.
    """
    workspace = live_epic.workspace
    subject = git(
        workspace.target_repo, "log", "-1", "--format=%s", workspace.branch
    ).strip()

    assert node(live_epic).branch == workspace.branch
    assert subject == salvage_message(
        workspace.epic_id, NODE_ID, Termination.COMPLETED, ATTEMPT
    )


def test_the_branch_carries_the_agent_s_work(live_epic: LiveEpic) -> None:
    """FR-013: the node's output is on its branch, reachable after the sweep.

    Read out of the ref rather than off the disk — the worktree is deliberately
    gone by now, and the branch is what the merge queue will later be handed.
    """
    workspace = live_epic.workspace
    tracked = git(
        workspace.target_repo, "ls-tree", "-r", "--name-only", workspace.branch
    ).split()

    assert WORK_FILE in tracked, f"the branch has no {WORK_FILE}: {tracked}"
    committed = git(workspace.target_repo, "show", f"{workspace.branch}:{WORK_FILE}")
    assert "def greet" in committed


def test_the_worktree_was_swept_and_the_branch_outlived_it(
    live_epic: LiveEpic,
) -> None:
    # Removal takes the directory and never the record (worktree.py): the branch
    # asserted above is what remains, and a worktree left behind would hold the
    # next epic's checkout of the same node.
    assert not live_epic.workspace.worktree.exists()


# --- the two stores agree with the run (SC-003) --------------------------------


def test_the_attempt_has_its_ledger_row(live_epic: LiveEpic) -> None:
    """Component 1's half of SC-003, against a real proxy's numbers.

    The row's *amounts* are `tests/test_live_proxy.py`'s subject — it reconciles
    them against the proxy's own spend logs. What matters here is that the epic
    produced an attributed row at all, keyed the way every other record keys it,
    and carrying the termination the adapter classified rather than one the
    agent claimed (FR-012).
    """
    row = ledger_row(live_epic)
    assert row is not None, "the attempt left no ledger row (constitution V)"

    assert row["persona"] == PERSONA
    assert row["spec_ref"] == f"{live_epic.workspace.epic_id}:{STORY_KEY}"
    epic_id = live_epic.workspace.epic_id
    assert row["key_alias"] == f"{epic_id}:{NODE_ID}:{ATTEMPT}:{PERSONA}"
    assert row["termination"] == Termination.COMPLETED.value
    # None would mean no snapshot was ever taken — a poll loop that never read
    # the proxy, or a teardown that could not (R3).
    assert row["spend_usd"] is not None

    # The judge scored this attempt (the spec declares a scenario and the gates
    # were green), so its spend sits in its OWN row beside the implementer's —
    # same attempt, its own persona-qualified alias. One alias for both was
    # D-026's live failure mode: the second mint refused, or one row upserted
    # over the other.
    judge = ledger_row(live_epic, persona="judge")
    assert judge is not None, "the judge's scoring left no ledger row (D-026)"
    assert judge["key_alias"] == f"{epic_id}:{NODE_ID}:{ATTEMPT}:judge"
    assert judge["key_alias"] != row["key_alias"]


def test_the_attempt_has_its_verification_row(live_epic: LiveEpic) -> None:
    """Component 2's half of SC-003: the verdict, from the evidence, in the store.

    Recorded before anything acted on it (FR-004), so the row is what the epic
    decided on and not a retelling of it.
    """
    row = verification_row(live_epic)
    assert row is not None, "the attempt left no verification row"

    assert row["verdict"] == "PASS", evidence(live_epic)
    assert row["form"] == "PHASE"
    assert row["spec_ref"] == f"{live_epic.workspace.epic_id}:{STORY_KEY}"
    assert row["criteria_sha256"]
    # The spec was written by this test and nobody edited it mid-run; drift here
    # would mean the criteria snapshot and the recorded file disagree (002 R8).
    assert row["criteria_drift"] == 0


def test_the_gate_the_repository_declared_is_the_gate_that_ran(
    live_epic: LiveEpic,
) -> None:
    """D-009: what "green" means came from the target repo's `factory.yaml`.

    A real subprocess, in the node's worktree, running the command the scratch
    repo committed — red before the node existed, green because of what it wrote.
    """
    row = verification_row(live_epic)
    assert row is not None
    gates = json.loads(row["gate_results"])

    assert [gate["name"] for gate in gates] == [GATE_NAME]
    assert gates[0]["status"] == "PASS", gates[0]["output_tail"]
    assert gates[0]["exit_code"] == 0
    assert CHECK_MODULE in gates[0]["command"]

    output = json.loads(row["output_check"])
    assert output["passed"] is True, output
    assert output["has_diff"] is True, output


# --- the evidence was archived off the worktree (FR-007) -----------------------


def test_the_attempt_s_stdout_was_archived(live_epic: LiveEpic) -> None:
    """The log is streamed into the archive, so it survives every ending.

    Under the worker host's `.factory/`, never inside a worktree: a transcript
    committed to the node branch would be read as agent work by the diff check
    the assertion above depends on.
    """
    log = live_epic.workspace.archive / STDOUT_LOG_NAME

    assert log.is_file(), f"no {STDOUT_LOG_NAME} under {live_epic.workspace.archive}"
    assert log.stat().st_size > 0
    assert live_epic.workspace.archive.is_relative_to(live_epic.workspace.factory_root)


def test_the_agent_s_session_transcript_was_found_and_archived(
    live_epic: LiveEpic,
) -> None:
    """The one assertion that checks Claude Code's own path rule (R6).

    `adapter.project_dir_name` reproduces a convention that belongs to the CLI —
    absolute cwd, every non-alphanumeric character replaced by `-`, the file
    named for the session id the workflow minted with `workflow.uuid4()`. The
    factory has no way to be told when that changes; an archive with no `.jsonl`
    beside its log is how it finds out.
    """
    archived = sorted(live_epic.workspace.archive.glob("*.jsonl"))

    assert len(archived) == 1, (
        "expected exactly one archived session transcript in "
        f"{live_epic.workspace.archive}, found {[path.name for path in archived]} — "
        "if the log is there and this is not, the agent CLI no longer writes its "
        "transcript where adapter.project_dir_name looks (R6)"
    )
    # The name is the session id, which is the workflow's uuid4 and nothing else.
    uuid.UUID(archived[0].stem)
    assert archived[0].stat().st_size > 0


# --- the operator's view (FR-009, quickstart §4) -------------------------------


def test_factory_epic_status_reports_what_the_workflow_reported(
    live_epic: LiveEpic, capsys: pytest.CaptureFixture[str]
) -> None:
    """The operator's third verb, against the epic that just ran.

    Queried out of the finished workflow rather than rebuilt from anything this
    test knows, which is the property that makes `status` trustworthy while an
    epic is still running.
    """
    status = cli.main(["status", live_epic.workspace.epic_id])
    printed = capsys.readouterr().out

    assert status == cli.EXIT_OK
    assert f"epic {live_epic.workspace.epic_id}  {EpicState.COMPLETED}" in printed
    assert NODE_ID in printed
    assert str(NodeState.PASSED) in printed
    assert live_epic.workspace.branch in printed


# --- credentials (constitution V) ----------------------------------------------


def test_no_stored_byte_of_the_epic_repeats_the_master_key(
    live_epic: LiveEpic,
) -> None:
    """The proxy's master key never left the worker's environment.

    Asserted over the bytes the run actually wrote — the archived transcript and
    stdout the agent produced, the two databases, and the node's branch — because
    the environment the adapter builds is an allowlist and this is the live proof
    that nothing else put the credential somewhere on the way past. The virtual
    key is the only credential allowed to travel, and it travels inside
    `AttemptContext` alone.
    """
    secret = live_epic.config.master_key.encode("utf-8")
    workspace = live_epic.workspace

    artifacts = [
        path
        for path in workspace.factory_root.rglob("*")
        if path.is_file() and not path.is_symlink()
    ]
    assert artifacts, "the epic wrote no state to inspect"

    for artifact in artifacts:
        assert secret not in artifact.read_bytes(), (
            f"the proxy master key is stored in {artifact}"
        )

    history = git(workspace.target_repo, "log", "-p", workspace.branch)
    assert live_epic.config.master_key not in history
