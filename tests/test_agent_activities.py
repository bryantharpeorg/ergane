"""The activity surface of dispatch: resolve, prepare, run, salvage, remove.

`factory/workgraph/` is a library — a validator, a git wrapper, an adapter; this
module is where those become things a workflow can call, which means it owns
exactly what the library deliberately does not: reading the world at a known
moment, and turning a library exception into an error the interpreter can branch
on without reading prose. These tests are about that seam, so they run the real
activities in `ActivityEnvironment` against a real git repository and a real
child process, and assert what an activity leaves behind.

Five properties are what this file defends:

- **The registry is read once, per epic, and snapshotted onto the nodes**
  (data-model.md § ResolvedNode). `resolve_graph` is the only place
  `personas.yaml` is consulted, so an operator editing it mid-epic changes the
  *next* epic — the same discipline 002 applies to criteria. Every expectation
  below is computed from the shipped registry rather than written as a literal:
  the timeouts in that file are the operator's dial (FR-010), and a test that
  hardcoded 14400 would turn tuning it into a broken suite.

- **A graph that must not dispatch fails here, before anything is issued**
  (FR-002). An unknown persona, a persona resolving no timeout, a dangling
  dependency — all of them are `GRAPH_INVALID` and all of them are
  non-retryable, because re-running the same graph against the same registry
  reproduces the failure exactly. The message names the node, which is the
  whole diagnosis when an operator is holding a ten-node epic.

- **A dispatch with no standards to obey is a config error, not an attempt**
  (research R11). `prepare_worktree` is the one activity holding the worktree
  before the agent does, so it is where a declared-but-absent standards
  document is caught — before a key is issued, before a prompt tells an agent to
  read a file that is not there.

- **A killed attempt still ends with evidence and a classification** (FR-007,
  constitution VI). Cancellation is the workflow's kill path: the agent's
  process group dies, `stdout.log` and whatever transcript existed are archived,
  and the KILLED classification travels back *with* the cancellation rather than
  being inferred by the caller. Temporal still records the activity as
  cancelled, which is what makes the kill visible in the epic's history.

- **Terminal paths are re-runnable.** Temporal runs an activity at least once,
  so `prepare_worktree`, `salvage_worktree` and `remove_worktree` are each
  exercised twice in a row: the second run must be a no-op that returns the
  first run's answer, never a second salvage marker on the branch or an error
  over a worktree that is already gone.

Three deliberate choices in the setup:

- **The agent is the stub, shimmed onto `PATH` as `claude`.** Nothing configures
  the binary in production (R6), so the tests do not configure it either — they
  put `tests/stub_agent.py` where `claude` would be found. The shim is autouse
  precisely so a worker host with a real `claude` installed cannot have this
  suite launch it.

- **The worktree the agent runs in is a plain directory.** The adapter's
  contract is "cwd is the path you were handed"; the git half belongs to
  `prepare_worktree`, which has its own repository fixture here.

- **Credentials are planted in the worker environment for every test.** The
  allowlist's promise is that no launch anywhere carries them (US2-S1), and a
  fixture that only appeared in the leak test would leave every other path
  unwatched.

Written before `factory/activities/agent_activities.py` exists (T014 precedes
T015): until the module lands, every test here fails at import.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

import pytest
from temporalio import activity
from temporalio.exceptions import ApplicationError, CancelledError
from temporalio.testing import ActivityEnvironment

from factory.activities import agent_activities
from factory.activities.agent_activities import (
    FACTORY_ROOT_ENV,
    GRAPH_INVALID,
    PROMPT_SOURCE_MISSING,
    STANDARDS_MISSING,
    LoadPromptSourcesInput,
    PrepareWorktreeInput,
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
from factory.workgraph.adapter import STDOUT_LOG_NAME, pid_file, transcript_dir
from factory.workgraph.models import (
    AdapterResult,
    AttemptContext,
    ResolvedNode,
    WorkGraph,
    WorkNode,
)
from factory.workgraph.worktree import (
    DEFAULT_FACTORY_ROOT,
    PreparedWorktree,
    branch_name,
)
from tests.stub_agent import TRANSCRIPT_START, install_as, last_invocation, write_control
from tests.target_repo import git, git_env

EPIC = "003-merge-queue"
NODE = "us1"
FEATURE = "003-merge-queue"
BRANCH = branch_name(EPIC, NODE)

#: Not 1: the attempt number names the archive directory, and an off-by-one that
#: always wrote `attempt-1` would pass every test that ran a single attempt.
ATTEMPT = 2

#: Generated by the workflow with `workflow.uuid4()` (R6); the adapter passes it
#: through and finds the session transcript by it.
SESSION_ID = "0f2c9a71-5d48-4c3b-8a6e-2b7c1d0e9f43"

#: A LiteLLM alias as `personas.yaml` writes them — travels from the registry to
#: argv untouched; no code here names a model (constitution VII).
MODEL_ALIAS = "anthropic/CHANGEME"

PROXY_URL = "http://litellm.test:4000"
VIRTUAL_KEY = "sk-virtual-003-merge-queue-us1-2"

#: Planted in the worker environment by `worker_host`, and absent from every
#: child this file launches. Distinctive strings so a leak is greppable.
MASTER_KEY = "sk-master-must-never-reach-an-agent"
BOT_TOKEN = "1234567:telegram-bot-token-must-never-reach-an-agent"

PROMPT = "You are the implementer persona.\n\n## Scope\n\nImplement US1.\n"

#: The context's own bound. Long enough that no test races its deadline; the
#: production value is the persona registry's (FR-010).
TIMEOUT_S = 60

#: A per-story override, deliberately unlike anything an operator would set in
#: the registry, so "the override won" is not a coincidence.
OVERRIDE_TIMEOUT_S = 917

#: `resolve_graph` reads the registry and nothing else — no filesystem, no git —
#: so the graph's target repo is a path that does not exist on this host.
UNTOUCHED_TARGET_REPO = "/srv/factory/targets/ergane"

#: A document the fixture repo really commits, and one it does not: the two
#: halves of R11's existence check.
PRESENT_STANDARDS = "docs/notes.md"
ABSENT_STANDARDS = "docs/STANDARDS.md"

#: A tracked file in the fixture repo, and an untracked one — the normal shape
#: of agent output, which salvage must pick up.
TRACKED_FILE = "src/calc.py"
NEW_FILE = "src/added_by_agent.py"

#: Ceiling for "the activity is not wedged" assertions.
PATIENCE_S = 20.0

#: The epic's authored text, as `load_prompt_sources` finds it under
#: `<specs_root>/<feature>/`. Deliberately awkward — trailing whitespace, a
#: fenced block, no final newline on one of them — because "verbatim" is the
#: whole contract and a reader that stripped or normalised would pass against
#: tidy fixtures.
SOURCE_TEXTS = {
    "spec.md": "# Spec\n\n## User Story 1 - Do the thing (Priority: P1)\n\nBody.  \n",
    "plan.md": "# Plan\n\n```yaml\nruntime: python\n```\n",
    "tasks.md": "# Tasks\n\n## Phase 3: User Story 1\n\n- [ ] T001 Do it",
}


# --- setup -------------------------------------------------------------------


@pytest.fixture
def env() -> ActivityEnvironment:
    return ActivityEnvironment()


@pytest.fixture
def factory_root(tmp_path: Path) -> Path:
    """The worker host's state directory: worktrees, transcripts, pid files."""
    return tmp_path / ".factory"


@pytest.fixture(autouse=True)
def worker_host(
    tmp_path: Path, factory_root: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """A worker host: a scratch factory root, a fake home, and credentials.

    Autouse, because each half protects something a per-test fixture would leave
    exposed. The fake `HOME` is where the stub reads its control file and writes
    its session transcript, and it is also the only identity git could otherwise
    fall back on — salvage carries its own (`tests/test_worktree.py`), and an
    empty home is what proves it. The credentials are planted everywhere so no
    launch in this file can quietly carry them.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    for name in (
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
    ):
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setenv(FACTORY_ROOT_ENV, str(factory_root))
    monkeypatch.setenv("LITELLM_MASTER_KEY", MASTER_KEY)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("TERM", "dumb")
    # Not a credential, and still not the agent's business: the allowlist is
    # closed, so an ordinary variable is dropped exactly like a secret.
    monkeypatch.setenv("EDITOR", "vim")
    return home


@pytest.fixture(autouse=True)
def agent_on_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """`tests/stub_agent.py` where `claude` would be found (R6).

    Nothing configures the agent binary in production — the persona registry's
    `agent` field selects a *class*, and that class runs `claude` off the
    passed-through `PATH` — so the tests do not configure it either. Autouse so
    a worker host with a real `claude` installed cannot have this suite launch
    it against a real proxy.
    """
    bin_dir = tmp_path / "bin"
    install_as(bin_dir, "claude")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return bin_dir


@pytest.fixture
def repo(target_repo: Callable[..., Path]) -> Path:
    """A real target repo with one commit on `main` (tests/target_repo.py)."""
    return target_repo("passing")


@pytest.fixture
def worktree(tmp_path: Path) -> Path:
    """Where the agent runs: a directory, not a repository — see the docstring."""
    path = tmp_path / "agent-worktree"
    path.mkdir()
    return path


@pytest.fixture
def context(worktree: Path) -> Callable[..., AttemptContext]:
    """Build the attempt's context; `context(attempt=3)` overrides one field."""

    def build(**overrides: Any) -> AttemptContext:
        fields: dict[str, Any] = {
            "epic_id": EPIC,
            "node_id": NODE,
            "attempt": ATTEMPT,
            "prompt": PROMPT,
            "worktree_path": str(worktree),
            "proxy_url": PROXY_URL,
            "virtual_key": VIRTUAL_KEY,
            "model_alias": MODEL_ALIAS,
            "session_id": SESSION_ID,
            "timeout_s": TIMEOUT_S,
        }
        return AttemptContext(**(fields | overrides))

    return build


# --- helpers -----------------------------------------------------------------


def work_node(**overrides: Any) -> WorkNode:
    """One compiled story node; override only what a test is about."""
    fields: dict[str, Any] = {
        "id": NODE,
        "story_key": "US1",
        "persona": "implementer",
        "spec_ref": f"{FEATURE}:US1",
        "requirement_keys": ["US1", "FR-001"],
        "depends_on": [],
    }
    return WorkNode(**(fields | overrides))


def work_graph(*nodes: WorkNode, **overrides: Any) -> WorkGraph:
    """A graph of the given nodes, in declaration order (R10)."""
    fields: dict[str, Any] = {
        "epic_id": EPIC,
        "feature": FEATURE,
        "specs_root": "specs",
        "target_repo": UNTOUCHED_TARGET_REPO,
        "nodes": list(nodes) or [work_node()],
    }
    return WorkGraph(**(fields | overrides))


async def prepare(
    env: ActivityEnvironment, repo: Path, **overrides: Any
) -> PreparedWorktree:
    """Prepare the standard node's worktree against `repo`."""
    fields: dict[str, Any] = {
        "epic_id": EPIC,
        "node_id": NODE,
        "target_repo": str(repo),
        "standards": None,
    }
    return await env.run(prepare_worktree, PrepareWorktreeInput(**(fields | overrides)))


async def wait_until(
    predicate: Callable[[], bool], *, what: str, timeout_s: float = PATIENCE_S
) -> None:
    """Poll `predicate` until it holds, or fail naming what never happened."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"timed out after {timeout_s}s waiting for {what}")


def stub_is_up(worktree: Path) -> bool:
    """Whether a launched stub has finished recording itself.

    Keyed on the stdin record because the stub writes it last, once the prompt
    is drained: by then argv, env, cwd and the process ids are all on disk.
    """
    return bool(list(worktree.glob(".stub-agent/*/stdin.txt")))


def pid_alive(pid: int) -> bool:
    """Whether signal 0 still finds `pid` (a zombie counts — it exists)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def archive_dir(factory_root: Path, attempt: int = ATTEMPT) -> Path:
    return transcript_dir(factory_root, EPIC, NODE, attempt)


def stdout_log(factory_root: Path, attempt: int = ATTEMPT) -> str:
    return (archive_dir(factory_root, attempt) / STDOUT_LOG_NAME).read_text(
        encoding="utf-8"
    )


def archived_transcript_events(factory_root: Path, attempt: int = ATTEMPT) -> list[str]:
    """The `event` field of each record in the archived session transcript.

    `["start"]` alone is a run killed between the two writes — the partial
    evidence FR-007 exists to keep.
    """
    path = archive_dir(factory_root, attempt) / f"{SESSION_ID}.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line)["event"] for line in lines if line.strip()]


def head(path: Path, ref: str = "HEAD") -> str:
    return git(path, "rev-parse", ref).strip()


def subject(path: Path, ref: str = "HEAD") -> str:
    return git(path, "log", "-1", "--format=%s", ref).strip()


def commit_count(path: Path, ref: str = "HEAD") -> int:
    return int(git(path, "rev-list", "--count", ref).strip())


def ref_exists(repo: Path, ref: str) -> bool:
    completed = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", ref],
        capture_output=True,
        text=True,
        env=git_env(),
    )
    return completed.returncode == 0


def dirty(worktree: Path) -> None:
    """Leave the shape of an agent's work: one edit, one new file."""
    (worktree / TRACKED_FILE).write_text("# edited by the agent\n", encoding="utf-8")
    (worktree / NEW_FILE).write_text("VALUE = 1\n", encoding="utf-8")


# --- registration -------------------------------------------------------------


def test_the_activities_are_registered_under_their_contract_names() -> None:
    """A worker can only register decorated callables, and the names are what
    contracts/adapter.md tells the workflow side to call — a rename here is a
    workflow that dispatches into nothing."""
    for fn, name in (
        (resolve_graph, "resolve_graph"),
        (prepare_worktree, "prepare_worktree"),
        (run_agent_attempt, "run_agent_attempt"),
        (salvage_worktree, "salvage_worktree"),
        (remove_worktree, "remove_worktree"),
    ):
        definition = activity._Definition.from_callable(fn)
        assert definition is not None, f"{name} must carry @activity.defn"
        assert definition.name == name


# --- resolve_graph (the registry snapshot) ------------------------------------


async def test_resolve_graph_snapshots_the_registry_onto_every_node(
    env: ActivityEnvironment,
) -> None:
    """Model alias, models list, write scope and timeout, per node, in order.

    Expectations come from the shipped registry rather than from literals: those
    values are the operator's to edit (FR-010, constitution VII), and what this
    asserts is that the activity *reads* them — not that they hold particular
    numbers today.
    """
    registry = load_personas()
    nodes = (work_node(id="us1"), work_node(id="us2", persona="architect"))

    resolved = await env.run(resolve_graph, work_graph(*nodes))

    assert [item.node.id for item in resolved] == ["us1", "us2"]
    assert all(isinstance(item, ResolvedNode) for item in resolved)
    # The node travels through untouched: what was validated is what dispatches.
    assert [item.node for item in resolved] == list(nodes)

    for item, node in zip(resolved, nodes):
        persona = registry[node.persona]
        assert item.model_alias == persona.model
        # The issued key's constraint list (001): primary first, fallback after,
        # and nothing invented for a persona that declares none.
        assert item.models == [
            alias for alias in (persona.model, persona.fallback) if alias
        ]
        assert item.write_scope == persona.write_scope.value
        assert item.timeout_s == persona.timeout_s


async def test_a_per_story_timeout_override_wins_over_the_registry(
    env: ActivityEnvironment,
) -> None:
    """R8: the `## Work Graph` override is the per-story dial, the registry the
    default — a node that declares one is bounded by it and by nothing else."""
    registry_default = load_personas()["implementer"].timeout_s
    assert OVERRIDE_TIMEOUT_S != registry_default

    resolved = await env.run(
        resolve_graph, work_graph(work_node(timeout_override_s=OVERRIDE_TIMEOUT_S))
    )

    assert resolved[0].timeout_s == OVERRIDE_TIMEOUT_S


async def test_resolve_graph_reads_the_registry_and_nothing_else(
    env: ActivityEnvironment, factory_root: Path
) -> None:
    """Read-only and idempotent (contracts/adapter.md): Temporal may run it
    twice, and both runs must agree without having touched the host."""
    first = await env.run(resolve_graph, work_graph())
    second = await env.run(resolve_graph, work_graph())

    assert first == second
    assert not factory_root.exists()
    assert not Path(UNTOUCHED_TARGET_REPO).exists()


async def test_an_unknown_persona_fails_the_graph_naming_the_node(
    env: ActivityEnvironment,
) -> None:
    """A node routed to a persona the registry does not carry can never
    dispatch: no model, no key, no timeout. It fails here, at epic start, with
    the node named — an operator holding a ten-node epic needs the offender, not
    "invalid workgraph"."""
    graph = work_graph(work_node(id="us1"), work_node(id="us2", persona="scribe"))

    with pytest.raises(ApplicationError) as raised:
        await env.run(resolve_graph, graph)

    assert raised.value.type == GRAPH_INVALID
    assert "us2" in str(raised.value)
    assert "scribe" in str(raised.value)
    # The registry is config an operator edits; re-reading it a second later
    # produces the same answer, so the retry budget must not be spent on it.
    assert raised.value.non_retryable is True


async def test_a_persona_that_resolves_no_timeout_fails_the_graph(
    env: ActivityEnvironment,
) -> None:
    """FR-010: an attempt the factory cannot bound is not dispatched.

    `verifier` is the shipped deterministic persona — it runs no agent and
    therefore declares no timeout (R8) — so routing a producing node to it is
    exactly the mistake this rule catches, before a key is issued rather than at
    the moment the adapter needs a deadline it does not have.
    """
    graph = work_graph(work_node(id="us3", persona="verifier"))

    with pytest.raises(ApplicationError) as raised:
        await env.run(resolve_graph, graph)

    assert raised.value.type == GRAPH_INVALID
    assert "us3" in str(raised.value)
    assert raised.value.non_retryable is True


async def test_a_structural_defect_is_caught_again_at_epic_start(
    env: ActivityEnvironment,
) -> None:
    """FR-002: `workgraph.json` is a compiled artifact *and* a file on disk
    between two commands, so the graph is re-validated against the registry it
    will actually dispatch from — an edit made in between is irrelevant."""
    graph = work_graph(work_node(id="us1", depends_on=["us9"]))

    with pytest.raises(ApplicationError) as raised:
        await env.run(resolve_graph, graph)

    assert raised.value.type == GRAPH_INVALID
    assert "us9" in str(raised.value)
    assert raised.value.non_retryable is True


# --- prepare_worktree (FR-013, R11) -------------------------------------------


async def test_prepare_worktree_creates_the_nodes_one_worktree(
    env: ActivityEnvironment, repo: Path, factory_root: Path
) -> None:
    """`.factory/worktrees/<epic>/<node>` on `factory/<epic>/<node>`, branched
    from the target repo's head at first dispatch (R5)."""
    prepared = await prepare(env, repo)

    assert isinstance(prepared, PreparedWorktree)
    assert Path(prepared.path) == factory_root / "worktrees" / EPIC / NODE
    assert prepared.branch == BRANCH
    assert prepared.base_ref == head(repo)

    worktree = Path(prepared.path)
    assert (worktree / TRACKED_FILE).is_file()
    assert git(worktree, "rev-parse", "--abbrev-ref", "HEAD").strip() == BRANCH
    # Factory state under the target clone would read as agent work in 002's
    # diff check, and salvage would commit it.
    assert not worktree.resolve().is_relative_to(repo.resolve())


async def test_prepare_worktree_is_idempotent_across_re_runs(
    env: ActivityEnvironment, repo: Path
) -> None:
    """Temporal runs an activity at least once, and every attempt of a node
    calls this again (FR-013's one worktree). The second call returns the first
    call's answer and leaves what the last attempt left — 002's retry semantics,
    and the debugger persona in particular, are written against that
    continuity."""
    first = await prepare(env, repo)
    worktree = Path(first.path)
    dirty(worktree)
    before = head(worktree)

    second = await prepare(env, repo)

    assert second == first
    assert head(worktree) == before
    assert (worktree / NEW_FILE).read_text(encoding="utf-8") == "VALUE = 1\n"


async def test_a_declared_standards_document_is_verified_in_the_worktree(
    env: ActivityEnvironment, repo: Path
) -> None:
    """R11: when `factory.yaml` declares `standards`, the file the prompt will
    point the agent at has to be there — checked in the worktree the agent will
    actually see, not in the clone it was branched from."""
    prepared = await prepare(env, repo, standards=PRESENT_STANDARDS)

    assert (Path(prepared.path) / PRESENT_STANDARDS).is_file()


async def test_a_missing_standards_document_fails_the_dispatch_loudly(
    env: ActivityEnvironment, repo: Path
) -> None:
    """A declared standards file that is absent is a config error, not a hint an
    agent can work around: no attempt runs, the ladder applies as it would to
    any dispatch failure, and the message names the path and the node so the
    operator knows which of the two is wrong."""
    with pytest.raises(ApplicationError) as raised:
        await prepare(env, repo, standards=ABSENT_STANDARDS)

    assert raised.value.type == STANDARDS_MISSING
    assert ABSENT_STANDARDS in str(raised.value)
    assert NODE in str(raised.value)
    # The manifest is committed to the target repo; a re-run reads the same
    # bytes and finds the same absence. Retrying only delays the diagnosis.
    assert raised.value.non_retryable is True


async def test_a_repo_that_declares_no_standards_is_not_asked_for_one(
    env: ActivityEnvironment, repo: Path
) -> None:
    """Most target repos declare nothing (R11): absent means "nothing to obey",
    never "check for a file called None"."""
    prepared = await prepare(env, repo, standards=None)

    assert Path(prepared.path).is_dir()


# --- run_agent_attempt (the one place an agent runs) --------------------------


async def test_run_agent_attempt_returns_the_termination_and_the_archive(
    env: ActivityEnvironment,
    context: Callable[..., AttemptContext],
    worktree: Path,
    factory_root: Path,
    worker_host: Path,
) -> None:
    """D-018's narrow output, and the evidence beside it (FR-007).

    Nothing else crosses back: no diff, no usage, nothing the agent said. The
    archive is keyed by the same `(epic, node, attempt)` identity as the virtual
    key and the ledger row, so an attempt is attributable without a lookup.
    """
    write_control(worker_host, stdout="I have completed the task.")

    result = await env.run(run_agent_attempt, context())

    assert result == AdapterResult(
        termination=Termination.COMPLETED,
        transcript_path=str(archive_dir(factory_root)),
    )
    assert "I have completed the task." in stdout_log(factory_root)
    assert (archive_dir(factory_root) / f"{SESSION_ID}.jsonl").is_file()
    # Production runs `claude` off the passed-through PATH; nothing configures
    # the binary, which is the only reason passing PATH through matters at all.
    assert Path(last_invocation(worktree).argv[0]).name == "claude"


async def test_no_worker_credential_reaches_the_agent_the_activity_launched(
    env: ActivityEnvironment,
    context: Callable[..., AttemptContext],
    worktree: Path,
    worker_host: Path,
) -> None:
    """US2-S1 through the activity, which is what production actually calls.

    The child environment is *built*, not filtered: the master key and the bot
    token are absent because nothing put them there, as is every other variable
    the worker happens to carry. The per-attempt virtual key is the one
    credential allowed through (constitution V).
    """
    write_control(worker_host)

    await env.run(run_agent_attempt, context())

    child_env = last_invocation(worktree).env
    assert set(child_env) == {
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_AUTH_TOKEN",
        "PATH",
        "HOME",
        "LANG",
        "TERM",
    }
    assert child_env["ANTHROPIC_AUTH_TOKEN"] == VIRTUAL_KEY
    assert MASTER_KEY not in child_env.values()
    assert BOT_TOKEN not in child_env.values()


async def test_run_agent_attempt_beats_while_the_agent_works(
    env: ActivityEnvironment,
    context: Callable[..., AttemptContext],
    worker_host: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An attempt may run for hours (FR-010), so the activity has to say it is
    alive: the beat is what makes a cancellation land within one interval
    instead of at the deadline, and a dead worker detectable in minutes (R2).
    The interval is module scope so a test can shrink it without waiting out a
    production-sized one."""
    beats: list[tuple[Any, ...]] = []
    env.on_heartbeat = lambda *args: beats.append(args)
    monkeypatch.setattr(agent_activities, "HEARTBEAT_INTERVAL_S", 0.05)
    write_control(worker_host, sleep_s=1.0)

    result = await env.run(run_agent_attempt, context())

    assert result.termination == Termination.COMPLETED
    assert len(beats) >= 3, f"expected repeated beats over a 1s attempt, got {len(beats)}"


async def test_a_cancelled_attempt_dies_keeps_its_evidence_and_reports_killed(
    env: ActivityEnvironment,
    context: Callable[..., AttemptContext],
    worktree: Path,
    factory_root: Path,
    worker_host: Path,
) -> None:
    """The kill path (US3-S3), end to end through the activity.

    Cancellation is how `kill_epic` reaches a running agent, and three things
    have to be true when it lands. The agent is gone — a process left holding
    the worktree would corrupt the salvage the workflow does next. The evidence
    survives: `stdout.log` and whatever the agent had written to its session
    transcript by the moment it died, which on this path is the only account of
    what it was doing (FR-007). And the KILLED classification travels back
    *with* the cancellation, so the workflow's kill sequence records what the
    adapter observed rather than inferring it — while Temporal still sees a
    cancelled activity, which is what makes the kill visible in the history.
    """
    write_control(worker_host, sleep_s=300.0, stdout="working on it")

    running = asyncio.create_task(env.run(run_agent_attempt, context()))
    await wait_until(lambda: stub_is_up(worktree), what="the agent to launch")
    agent = last_invocation(worktree)

    env.cancel()
    with pytest.raises(CancelledError) as raised:
        await running

    killed = [detail for detail in raised.value.details if isinstance(detail, AdapterResult)]
    assert killed, f"the cancellation carried no AdapterResult: {raised.value.details!r}"
    assert killed[0].termination == Termination.KILLED
    assert Path(killed[0].transcript_path) == archive_dir(factory_root)

    await wait_until(lambda: not pid_alive(agent.pid), what="the agent to die")
    assert "working on it" in stdout_log(factory_root)
    # The stub writes `start` before sleeping and `end` after: `start` alone is
    # proof that what existed at the moment of death was kept, rather than a
    # tidy run being copied afterwards.
    assert archived_transcript_events(factory_root) == [TRANSCRIPT_START]
    # A stale pid is a reap of somebody else on the next attempt (R4).
    assert not pid_file(factory_root, EPIC, NODE).exists()


async def test_the_factory_root_defaults_to_the_documented_location(
    env: ActivityEnvironment,
    context: Callable[..., AttemptContext],
    worker_host: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Everything that reads this state — the operator, the sweep, the next
    worker — has to agree with the writer about where `.factory/` is, so the
    default is the documented one and the env var is the only override."""
    monkeypatch.delenv(FACTORY_ROOT_ENV)
    monkeypatch.chdir(tmp_path)
    write_control(worker_host)

    result = await env.run(run_agent_attempt, context())

    assert str(DEFAULT_FACTORY_ROOT) == ".factory"
    expected = Path(DEFAULT_FACTORY_ROOT) / "transcripts" / EPIC / NODE / f"attempt-{ATTEMPT}"
    assert result.transcript_path == str(expected)
    assert (tmp_path / expected / STDOUT_LOG_NAME).is_file()


# --- salvage_worktree / remove_worktree (constitution VI) ---------------------


async def test_salvage_worktree_commits_the_attempt_and_re_running_adds_nothing(
    env: ActivityEnvironment, repo: Path
) -> None:
    """SC-004: every terminal attempt is observable from the ref alone — and
    exactly once. Temporal re-running a terminal path after an unrecorded
    success must land on the same commit, or the branch stops being a readable
    account of what happened."""
    prepared = await prepare(env, repo)
    worktree = Path(prepared.path)
    dirty(worktree)
    before = commit_count(worktree)
    request = SalvageWorktreeInput(
        epic_id=EPIC, node_id=NODE, termination=Termination.AGENT_ERROR, attempt=ATTEMPT
    )

    sha = await env.run(salvage_worktree, request)
    again = await env.run(salvage_worktree, request)

    assert sha == head(worktree)
    assert again == sha
    assert commit_count(worktree) == before + 1
    assert subject(worktree) == f"salvage({EPIC}/{NODE}): agent_error attempt {ATTEMPT}"
    # Untracked work is work: `git add -A`, not `git commit -a`.
    assert (worktree / NEW_FILE).is_file()
    assert git(worktree, "status", "--porcelain", "--untracked-files=all") == ""


async def test_remove_worktree_is_idempotent_and_leaves_the_salvaged_branch(
    env: ActivityEnvironment, repo: Path
) -> None:
    """Removal is cleanup, never deletion of the record: once `.factory/` is
    swept the branch and its salvage commits are the only thing left of the
    attempt. Already-removed is success, because terminal paths re-run."""
    prepared = await prepare(env, repo)
    worktree = Path(prepared.path)
    dirty(worktree)
    sha = await env.run(
        salvage_worktree,
        SalvageWorktreeInput(
            epic_id=EPIC,
            node_id=NODE,
            termination=Termination.KILLED,
            attempt=ATTEMPT,
        ),
    )
    request = RemoveWorktreeInput(epic_id=EPIC, node_id=NODE, target_repo=str(repo))

    await env.run(remove_worktree, request)
    await env.run(remove_worktree, request)

    assert not worktree.exists()
    assert ref_exists(repo, f"refs/heads/{BRANCH}")
    assert head(repo, BRANCH) == sha


async def test_removing_a_worktree_that_was_never_prepared_is_success(
    env: ActivityEnvironment, repo: Path, factory_root: Path
) -> None:
    """A node killed before it ever dispatched still runs the terminal cleanup
    sequence, and an activity that raised there would fail an epic over a
    directory that was correctly never created."""
    await env.run(
        remove_worktree,
        RemoveWorktreeInput(epic_id=EPIC, node_id=NODE, target_repo=str(repo)),
    )

    assert not (factory_root / "worktrees" / EPIC / NODE).exists()


# --- load_prompt_sources (contracts/prompt-assembly.md) -----------------------


def write_feature(specs_root: Path, feature: str = FEATURE) -> Path:
    """An epic's authored text on disk: the three documents a prompt is built from."""
    directory = specs_root / feature
    directory.mkdir(parents=True)
    for name, text in SOURCE_TEXTS.items():
        (directory / name).write_text(text, encoding="utf-8")
    return directory


async def test_load_prompt_sources_reads_the_epics_text_verbatim(
    env: ActivityEnvironment, repo: Path, tmp_path: Path
) -> None:
    """The read half of FR-006, so assembly itself can be pure (R9).

    Whole files, byte for byte: the story sections and the task slice are cut out
    of these by pure functions, and an activity that trimmed or normalised
    anything would put a silent transform underneath a prompt SC-001 requires to
    be reproducible.
    """
    specs_root = tmp_path / "specs"
    write_feature(specs_root)

    sources = await env.run(
        load_prompt_sources,
        LoadPromptSourcesInput(
            specs_root=str(specs_root), feature=FEATURE, target_repo=str(repo)
        ),
    )

    assert sources.spec_text == SOURCE_TEXTS["spec.md"]
    assert sources.plan_text == SOURCE_TEXTS["plan.md"]
    assert sources.tasks_text == SOURCE_TEXTS["tasks.md"]


async def test_load_prompt_sources_carries_the_repos_declared_standards_path(
    env: ActivityEnvironment, repo: Path, tmp_path: Path
) -> None:
    """R11: the path, not the document — the prompt points the agent at it and
    the agent reads it in its own worktree, where `prepare_worktree` has already
    confirmed it exists. Absent from the manifest means nothing to obey, which is
    what most target repos declare."""
    specs_root = tmp_path / "specs"
    write_feature(specs_root)
    request = LoadPromptSourcesInput(
        specs_root=str(specs_root), feature=FEATURE, target_repo=str(repo)
    )

    assert (await env.run(load_prompt_sources, request)).standards is None

    manifest = repo / "factory.yaml"
    manifest.write_text(
        f"{manifest.read_text(encoding='utf-8')}\nstandards: {PRESENT_STANDARDS}\n",
        encoding="utf-8",
    )

    assert (await env.run(load_prompt_sources, request)).standards == PRESENT_STANDARDS


async def test_an_absent_prompt_source_fails_the_dispatch_naming_the_path(
    env: ActivityEnvironment, repo: Path, tmp_path: Path
) -> None:
    """The assembler never invents context (contracts/prompt-assembly.md): an
    epic missing its plan is a dispatch that fails loudly here, before a key is
    issued, rather than an agent handed a prompt with a section quietly gone."""
    specs_root = tmp_path / "specs"
    (write_feature(specs_root) / "plan.md").unlink()

    with pytest.raises(ApplicationError) as raised:
        await env.run(
            load_prompt_sources,
            LoadPromptSourcesInput(
                specs_root=str(specs_root), feature=FEATURE, target_repo=str(repo)
            ),
        )

    assert raised.value.type == PROMPT_SOURCE_MISSING
    assert "plan.md" in str(raised.value)
    # An epic's documents are committed files; a re-run finds the same absence.
    assert raised.value.non_retryable is True
