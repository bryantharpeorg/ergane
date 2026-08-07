"""The activity surface of dispatch: resolve, prepare, run, salvage, remove.

`factory/workgraph/` is a library — a validator, a git wrapper, an adapter. This
module is where those become things a workflow can call, which means it owns the
two concerns the library deliberately does not: reading the world at a known
moment, and turning a library exception into an error the interpreter can branch
on without reading prose.

The activities are one node's life, in order. `resolve_graph` reads
`personas.yaml` once per epic and hands back a snapshot, so an operator editing
the registry mid-epic changes the *next* epic — the same discipline 002 applies
to criteria; `resolve_persona` is that read for the one role no node names, the
judge, which needs an alias and a key of its own without being routed to.
`prepare_worktree` opens (or re-opens) the node's one worktree.
`run_agent_attempt` is the only place an agent runs. `read_worktree_diff` is the
one place the resulting patch is read, because the workflow that hands it to the
judge may touch nothing itself. `salvage_worktree` and `remove_worktree` are the
terminal pair constitution VI requires on every path out, in that order.

Four things decided here rather than in the library:

- **Where `.factory/` is.** The library takes a root; the activities resolve one,
  from `FACTORY_ROOT` or the documented default. Everything that reads this state
  — the operator, the next worker, the sweep — has to agree with the writer about
  the location, so there is exactly one function that answers the question.

- **Which failures are worth a retry.** A graph the registry cannot resolve, a
  declared standards document that is not in the worktree, an agent binary that
  is not on the host: all non-retryable, because re-running reproduces them
  exactly and the ladder's budget exists for proxies and worktrees, not for
  typos. A git command that failed stays retryable — a lock, a full disk and a
  slow filesystem are all things a second attempt fixes.

- **What a rejection says.** `GRAPH_INVALID` carries the validator's message
  verbatim, and that message names the offending node. An operator holding a
  ten-node epic needs the offender, not "invalid workgraph". There is one error
  type for every way a graph can fail to resolve, including an unreadable
  registry, because the workflow's response to all of them is identical — the
  epic does not start — and the message already says which file to go and edit.

- **How a kill reports itself.** Cancellation is how `kill_epic` reaches a
  running agent. The adapter kills the process group and archives the evidence
  before it re-raises; this module turns that into a `CancelledError` carrying
  the `AdapterResult` in its details, so the workflow's kill sequence records the
  KILLED classification the adapter *observed* rather than inferring it from the
  fact that it asked. Temporal still sees a cancelled activity, which is what
  makes the kill visible in the epic's history.

`load_prompt_sources` is the odd one out: a pure read, no worktree, no agent. It
exists so `factory/workgraph/prompt.py` can stay pure (FR-006, R9) — text in,
prompt out — with every file read on this side of the activity boundary.

No credential is read here. The per-attempt virtual key arrives inside the
`AttemptContext` the workflow assembled and goes no further than the child
environment the adapter builds; `LITELLM_MASTER_KEY` and `TELEGRAM_BOT_TOKEN`
sit in the same worker environment and have no path into any of these calls
(constitution V).
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable

from temporalio import activity
from temporalio.exceptions import ApplicationError, CancelledError

from factory.activities.usage_activities import open_client
from factory.activities.notify_activities import ferry_read_answer, ferry_send_question
from factory.config import ConfigError, Persona, load_personas
from factory.usage.models import Termination, UsageSnapshot
from factory.verify.factory_yaml import (
    MANIFEST_NAME,
    FactoryConfigError,
    load_factory_config,
)
from factory.workgraph import worktree as worktrees
from factory.workgraph.adapter import (
    DEFAULT_HEARTBEAT_INTERVAL_S,
    AdapterError,
    ClaudeCodeAdapter,
    adapter_for,
    transcript_dir,
)
from factory.workgraph.models import (
    AdapterResult,
    AttemptContext,
    ResolvedNode,
    ResolvedPersona,
    WorkGraph,
    WorkGraphError,
    WorkNode,
    resolve_timeout_s,
    validate_workgraph,
)
from factory.workgraph.worktree import (
    DEFAULT_FACTORY_ROOT,
    PreparedWorktree,
    WorktreeError,
)

#: The activity error type for a graph that must not dispatch (FR-002): an
#: unknown persona, a persona resolving no timeout, a dangling dependency, a
#: cycle, or a registry the loader refuses. Always non-retryable — the graph and
#: the registry are both files, and reading them again a second later gives the
#: same answer.
GRAPH_INVALID = "GRAPH_INVALID"

#: The activity error type for a `factory.yaml` that declares a standards
#: document the worktree does not have (R11). A config error, caught before a key
#: is issued rather than by an agent told to read a file that is not there.
STANDARDS_MISSING = "STANDARDS_MISSING"

#: The activity error type for a git operation that failed. Retryable: a lock, a
#: full disk and a slow filesystem are all things a second attempt fixes, and a
#: worktree the worker could not reach this second is the workflow's retry budget
#: to spend, not the ladder's.
WORKTREE_FAILED = "WORKTREE_FAILED"

#: The activity error type for an agent that could not be started at all — no
#: such adapter, or no such binary on the worker host. Distinct from a non-zero
#: exit, which is an `AGENT_ERROR` termination and ordinary ladder input.
AGENT_LAUNCH_FAILED = "AGENT_LAUNCH_FAILED"

#: The activity error type for authored text the prompt cannot be assembled
#: without (contracts/prompt-assembly.md): a missing input is a loud dispatch
#: failure, never an omitted section.
PROMPT_SOURCE_MISSING = "PROMPT_SOURCE_MISSING"

#: Where the worker host keeps worktrees, transcripts and pid files when it does
#: not say otherwise. One override, one default, one resolver (`factory_root`).
FACTORY_ROOT_ENV = "FACTORY_ROOT"

#: How often a running attempt tells Temporal it is alive. At module scope so a
#: test can shrink it without waiting out a production-sized interval, and read
#: at call time so shrinking it works at all.
HEARTBEAT_INTERVAL_S = DEFAULT_HEARTBEAT_INTERVAL_S

#: The adapter every producing persona in the shipped registry names (D-018).
#: `AttemptContext` carries no `agent` field, so the seam is exercised here
#: rather than per attempt; a second agent adds a class and a lookup, not an
#: orchestration change.
DEFAULT_AGENT = ClaudeCodeAdapter.name

#: The epic's authored text, under `<specs_root>/<feature>/`. `spec.md` is the
#: system of record for intent (D-023); the other two are the clarified context
#: set and the node's task slice.
SPEC_FILENAME = "spec.md"
PLAN_FILENAME = "plan.md"
TASKS_FILENAME = "tasks.md"


def factory_root() -> Path:
    """The worker host's state directory (plan.md § Storage).

    Relative by default, so it resolves against the worker's working directory
    exactly the way 001's ledger and 002's evidence store do.
    """
    return Path(os.environ.get(FACTORY_ROOT_ENV) or DEFAULT_FACTORY_ROOT)


def _usage_reader(key: str) -> Callable[[], Awaitable[UsageSnapshot]]:
    """A spend read for `key`, one client per call (plan US1, R9).

    The adapter's monitor reads usage on its own `poll_interval_s` cadence and
    carries the newest snapshot as heartbeat details; this is the production
    closure the workflow's poll activity used to be. It reads the attempt's
    virtual key through the proxy's master-key client, opens and closes a client
    per read so a long attempt does not hold a connection open, and stamps the
    snapshot with the moment it was true — a value teardown may record hours
    later is only honest if its staleness is visible.

    A failure raises the client's own `LiteLLMError`; the adapter isolates it so
    a dead spend read never kills the beat.
    """
    async def read() -> UsageSnapshot:
        client = open_client()
        try:
            spend_usd = await client.get_spend(key)
        finally:
            await client.aclose()
        return UsageSnapshot(
            spend_usd=spend_usd,
            captured_at=datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
        )

    return read


def _ferry_sender(
    context: AttemptContext,
) -> Callable[[str], Awaitable[str]] | None:
    """The ferry's send callable, bound to this attempt's identity (008-US3).

    Closes over the workflow id (the activity's own info), the epic/node/attempt
    the question is attributed to (FR-002), and the question text the agent
    writes — so the monitor loop calls one argument (the text) and the rest is
    already pinned. Returns ``None`` when the workflow id is unavailable (a
    bare-`ActivityEnvironment` test with no info), so the ferry degrades to the
    US1-only path rather than raising: a sender that cannot attribute a question
    ships nothing, and the agent degrades to the marker path if the window
    elapses (FR-009).
    """
    workflow_id = activity.info().workflow_id if activity.in_activity() else None
    if workflow_id is None:
        return None

    async def send(question_text: str) -> str:
        return await ferry_send_question(
            workflow_id,
            context.epic_id,
            context.node_id,
            context.attempt,
            question_text,
        )

    return send


# --- resolve_graph (the registry snapshot) ------------------------------------


@activity.defn
async def resolve_graph(graph: WorkGraph) -> list[ResolvedNode]:
    """Read the persona registry against the graph, once, at epic start.

    Returns one `ResolvedNode` per node in declaration order (R10), each carrying
    the model alias, the issued key's model list, the write scope and the
    resolved timeout. The node travels through untouched: what was validated is
    what dispatches.

    Read-only and idempotent — no filesystem beyond `personas.yaml`, no git, no
    target repo — so Temporal may run it twice and both runs agree.

    Raises non-retryable `GRAPH_INVALID`, naming the offending node, for anything
    that would leave a node undispatchable.
    """
    try:
        registry = load_personas()
    except ConfigError as exc:
        # The loader's message already names the registry file and the persona;
        # a graph whose registry will not load is as undispatchable as one with
        # a dangling edge, and the workflow's response to both is the same.
        raise _graph_invalid(str(exc)) from exc

    try:
        validate_workgraph(graph, registry)
    except WorkGraphError as exc:
        raise _graph_invalid(str(exc)) from exc

    return [_resolve_node(node, registry[node.persona]) for node in graph.nodes]


def _resolve_node(node: WorkNode, persona: Persona) -> ResolvedNode:
    """One node with the registry read against it (data-model.md § ResolvedNode).

    `models` is primary-then-fallback with nothing invented for a persona that
    declares neither: it becomes the issued key's constraint list (001), so an
    alias appearing here that the persona did not name would widen what the
    attempt may call.
    """
    timeout_s = resolve_timeout_s(node, persona)
    if persona.model is None or timeout_s is None:
        # `validate_workgraph` has already rejected an unresolvable timeout, so
        # reaching here means a deterministic persona carrying a per-story
        # override: routable on paper, and with no model to dispatch under.
        raise _graph_invalid(
            f"node '{node.id}': persona '{node.persona}' runs no agent and names "
            "no model — a producing node cannot be routed to it (constitution VII)"
        )

    return ResolvedNode(
        node=node,
        model_alias=persona.model,
        models=[alias for alias in (persona.model, persona.fallback) if alias],
        write_scope=persona.write_scope.value,
        timeout_s=timeout_s,
    )


def _graph_invalid(message: str) -> ApplicationError:
    return ApplicationError(message, type=GRAPH_INVALID, non_retryable=True)


# --- resolve_persona (the roles no node names) --------------------------------


@dataclass(frozen=True)
class ResolvePersonaInput:
    """One registry entry to resolve, by name."""

    persona: str


@activity.defn
async def resolve_persona(request: ResolvePersonaInput) -> ResolvedPersona:
    """Read one persona the graph does not name — the judge (constitution V).

    `resolve_graph` answers for nodes, and no node is routed to the judge: it
    scores what an implementer produced, on its own key and under its own alias.
    Called once at epic start for the same reason the graph is resolved there —
    an epic that cannot score its stories should fail before a key is spent
    discovering it, not four attempts in.

    Read-only and idempotent. Raises non-retryable `GRAPH_INVALID`, naming the
    persona, when the registry has no such entry or the entry names no model.
    """
    try:
        registry = load_personas()
    except ConfigError as exc:
        raise _graph_invalid(str(exc)) from exc

    persona = registry.get(request.persona)
    if persona is None:
        raise _graph_invalid(
            f"persona '{request.persona}' is not in the registry, so the work "
            "that needs it cannot be dispatched"
        )
    if persona.model is None:
        raise _graph_invalid(
            f"persona '{request.persona}' runs no agent and names no model — "
            "nothing can be dispatched to it (constitution VII)"
        )

    return ResolvedPersona(
        persona=request.persona,
        model_alias=persona.model,
        models=[alias for alias in (persona.model, persona.fallback) if alias],
    )


# --- prepare_worktree (FR-013, R11) -------------------------------------------


@dataclass(frozen=True)
class PrepareWorktreeInput:
    """Which node's worktree to open, and what the target repo demands be in it.

    `standards` is the `factory.yaml` path (R11) rather than its contents: the
    prompt points the agent at the document, and the agent reads it in the
    worktree. `None` means the repo declares nothing to obey, which is the
    ordinary case.
    """

    epic_id: str
    node_id: str
    target_repo: str
    standards: str | None = None


@activity.defn
async def prepare_worktree(request: PrepareWorktreeInput) -> PreparedWorktree:
    """Open the node's one worktree, creating it on first dispatch (FR-013).

    Idempotent across attempts and across activity re-runs: an existing worktree
    is returned untouched, with the base ref it was pinned to at creation, so an
    attempt opens the tree the previous attempt left behind.

    Raises non-retryable `STANDARDS_MISSING` when the target repo declares a
    standards document the worktree does not have, and retryable
    `WORKTREE_FAILED` when git itself refused.

    Runs in a worker thread: a first checkout of a large repository owns the wall
    clock for as long as it takes, and blocking the event loop would stall every
    other activity this worker is running.
    """
    try:
        prepared = await asyncio.to_thread(
            worktrees.ensure,
            request.target_repo,
            request.epic_id,
            request.node_id,
            factory_root=factory_root(),
        )
    except WorktreeError as exc:
        raise ApplicationError(str(exc), type=WORKTREE_FAILED) from exc

    _require_standards(request, prepared)
    return prepared


def _require_standards(
    request: PrepareWorktreeInput, prepared: PreparedWorktree
) -> None:
    """Refuse a dispatch whose declared standards document is not there (R11).

    Checked in the worktree the agent will actually see rather than in the clone
    it was branched from: those differ the moment a node's own attempt touches
    the file. The message names both the path and the node, because either one of
    them may be the thing that is wrong.
    """
    if not request.standards:
        return

    document = Path(prepared.path) / request.standards
    if document.is_file():
        return

    raise ApplicationError(
        f"node '{request.node_id}': {MANIFEST_NAME} declares "
        f"standards '{request.standards}', which is not in the node's worktree "
        f"(looked for {document})",
        type=STANDARDS_MISSING,
        non_retryable=True,
    )


# --- run_agent_attempt (the one place an agent runs) --------------------------


@activity.defn
async def run_agent_attempt(context: AttemptContext) -> AdapterResult:
    """Run one agent attempt to its end, whatever that end is (D-018, FR-005).

    Returns the termination class and the archived transcript directory, and
    nothing else: the diff is read from the worktree and usage from the ledger,
    and nothing the agent *said* reaches node state (FR-012).

    Beats roughly every `HEARTBEAT_INTERVAL_S` while the agent works, which is
    what keeps a multi-hour attempt alive in Temporal's eyes and what makes a
    cancellation land within one interval instead of at the deadline.

    On cancellation the adapter has already ended the process group and archived
    the evidence; this re-raises as `CancelledError` carrying the `AdapterResult`
    so the kill sequence records the classification the adapter observed. Raises
    non-retryable `AGENT_LAUNCH_FAILED` when there was no agent to run.
    """
    root = factory_root()
    try:
        adapter = adapter_for(DEFAULT_AGENT)
        return await adapter.run_attempt(
            context,
            factory_root=root,
            heartbeat=activity.heartbeat,
            heartbeat_interval_s=HEARTBEAT_INTERVAL_S,
            read_usage=_usage_reader(context.virtual_key),
            # 008-US3: the in-attempt ferry. An agent that asks mid-flight writes
            # a `question` file to its archive directory; these callables ship it
            # up (record + page, the same `send_question` path US1 takes) and
            # poll the store for the operator's reply. Both are isolated by the
            # adapter so a dead ferry call never kills the liveness beat (FR-009).
            # The workflow id is the activity's own info — the same id the US1
            # terminal path puts on the `SendQuestionInput` — so a ferried
            # question is attributed to the same workflow that would have asked
            # it at the end.
            send_ferry_question=_ferry_sender(context),
            read_ferry_answer=ferry_read_answer,
        )
    except asyncio.CancelledError:
        raise CancelledError(
            f"attempt {context.attempt} of {context.epic_id}/{context.node_id} "
            "was cancelled; the agent's process group is dead and its evidence "
            "is archived",
            AdapterResult(
                termination=Termination.KILLED,
                transcript_path=str(
                    transcript_dir(
                        root, context.epic_id, context.node_id, context.attempt
                    )
                ),
            ),
        ) from None
    except AdapterError as exc:
        # No adapter, or no binary: the worker host is misconfigured, and the
        # ladder must not spend one of the node's attempts discovering that.
        raise ApplicationError(
            str(exc), type=AGENT_LAUNCH_FAILED, non_retryable=True
        ) from exc


# --- read_worktree_diff (what the judge scores) -------------------------------


@dataclass(frozen=True)
class ReadWorktreeDiffInput:
    """Which worktree to read the attempt's patch out of, and against what.

    The path rather than the epic/node pair, because the two callers that read
    this worktree in the same breath — 002's `run_gates` and `check_output` —
    take the path the workflow is already holding, and a second way of naming the
    same directory is a second thing that can disagree.

    `base_ref` is the prepared worktree's branch point (D-027): the judge scores
    everything the attempt changed since the node began, which an agent
    following the inner ralph contract has partly *committed* by now — a diff
    against HEAD would hand the judge everything except that work.
    """

    worktree_path: str
    base_ref: str


@activity.defn
async def read_worktree_diff(request: ReadWorktreeDiffInput) -> str:
    """Read what the attempt changed, for the judge to score (FR-001).

    The workflow decides and touches nothing, so this is the one place a
    worktree's patch is read. Read-only — the patch is assembled against a
    scratch index, never the worktree's own — and safe to retry.

    Raises retryable `WORKTREE_FAILED` when git could not read the worktree: an
    unreachable directory resembles an empty diff exactly, and handing the judge
    "the agent produced nothing" over a lost mount charges an infrastructure
    failure to the attempt.

    Runs in a worker thread: a patch over a large repository owns the wall clock
    for as long as git takes.
    """
    try:
        return await asyncio.to_thread(
            worktrees.diff, request.worktree_path, base_ref=request.base_ref
        )
    except WorktreeError as exc:
        raise ApplicationError(str(exc), type=WORKTREE_FAILED) from exc


# --- salvage_worktree / remove_worktree (constitution VI) ---------------------


@dataclass(frozen=True)
class SalvageWorktreeInput:
    """One terminal attempt, in the terms the salvage commit's subject needs.

    `termination` is the adapter's classification, travelling from the workflow
    to the one commit subject that will outlive `.factory/` (SC-004). It arrives
    as a `Termination` member rather than as a list of one-character strings
    because the enum is a `StrEnum` — see `factory/usage/models.py` for why that
    spelling is load-bearing on any field a workflow hands to an activity.
    """

    epic_id: str
    node_id: str
    termination: Termination
    attempt: int


@activity.defn
async def salvage_worktree(request: SalvageWorktreeInput) -> str:
    """Commit whatever the attempt left to the node's branch; return the sha.

    Runs on every termination path before any cleanup (constitution VI), and
    commits an empty tree as readily as a dirty one so every terminal attempt is
    observable from the ref alone (SC-004). Idempotent per attempt: a re-run
    after an unrecorded success lands on the same commit.
    """
    try:
        return await asyncio.to_thread(
            worktrees.salvage,
            request.epic_id,
            request.node_id,
            termination=request.termination,
            attempt=request.attempt,
            factory_root=factory_root(),
        )
    except WorktreeError as exc:
        raise ApplicationError(str(exc), type=WORKTREE_FAILED) from exc


@dataclass(frozen=True)
class RemoveWorktreeInput:
    """Which node's worktree to sweep, and the clone that administers it."""

    epic_id: str
    node_id: str
    target_repo: str


@activity.defn
async def remove_worktree(request: RemoveWorktreeInput) -> None:
    """Delete the node's worktree directory, leaving the branch and its history.

    Cleanup, never deletion of the record: once `.factory/` is swept, the branch
    and its salvage commits are the only thing left of the attempt. Idempotent —
    an already-removed worktree, or one a node killed before dispatch never had,
    is success.
    """
    try:
        await asyncio.to_thread(
            worktrees.remove,
            request.target_repo,
            request.epic_id,
            request.node_id,
            factory_root=factory_root(),
        )
    except WorktreeError as exc:
        raise ApplicationError(str(exc), type=WORKTREE_FAILED) from exc


# --- load_prompt_sources (contracts/prompt-assembly.md) -----------------------


@dataclass(frozen=True)
class LoadPromptSourcesInput:
    """Where the epic's authored text lives, and which repo declares standards."""

    specs_root: str
    feature: str
    target_repo: str


@dataclass(frozen=True)
class PromptSources:
    """Everything on disk that a dispatch prompt is assembled from (R9).

    Text, verbatim and whole — the story sections and the task slice are cut out
    of it by pure functions in `factory/workgraph/prompt.py`, which is what keeps
    assembly deterministic and unit-testable. `standards` is the declared *path*,
    not the document: the prompt points the agent at it and the agent reads it in
    its own worktree, where `prepare_worktree` has already confirmed it exists.
    """

    spec_text: str
    plan_text: str
    tasks_text: str
    standards: str | None = None


@activity.defn
async def load_prompt_sources(request: LoadPromptSourcesInput) -> PromptSources:
    """Read the epic's spec, plan and tasks, plus the target repo's standards path.

    The one read-only activity in the dispatch path, and the reason prompt
    assembly itself touches no filesystem (FR-006). Raises non-retryable
    `PROMPT_SOURCE_MISSING` naming the path when any of the three documents is
    absent — the assembler never invents context, so a missing input is a loud
    dispatch failure rather than an omitted section.
    """
    feature_dir = Path(request.specs_root) / request.feature
    return PromptSources(
        spec_text=_read_source(feature_dir / SPEC_FILENAME),
        plan_text=_read_source(feature_dir / PLAN_FILENAME),
        tasks_text=_read_source(feature_dir / TASKS_FILENAME),
        standards=_declared_standards(request.target_repo),
    )


def _read_source(path: Path) -> str:
    """One authored document, verbatim; absent or unreadable is a dispatch failure."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ApplicationError(
            f"cannot read prompt source {path}: {exc}",
            type=PROMPT_SOURCE_MISSING,
            non_retryable=True,
        ) from exc


def _declared_standards(target_repo: str) -> str | None:
    """The standards document the target repo's manifest declares, if any (R11).

    A manifest that is absent or that the schema refuses reads as "declares no
    standards" rather than failing the dispatch. That is not a swallowed error:
    002's gate run reads the same manifest and reports an unusable one as a
    `CONFIG_ERROR` gate result, which fails the attempt with the parser's own
    diagnosis attached. Raising here would pre-empt that with strictly less.
    """
    try:
        return load_factory_config(Path(target_repo) / MANIFEST_NAME).standards
    except FactoryConfigError:
        return None
