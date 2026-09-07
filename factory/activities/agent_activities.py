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
import logging
import os
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable

from temporalio import activity
from temporalio.exceptions import ApplicationError, CancelledError

from factory.activities.usage_activities import open_client
from factory.activities.notify_activities import ferry_read_answer, ferry_send_question
from factory.config import ConfigError, Persona, load_personas
from factory.config import (
    ROUTE_SUBSCRIPTION,
    SUBSCRIPTION_AGENT,
    effective_route,
)
from factory.usage.models import Termination, UsageSnapshot
from factory.verify.factory_yaml import (
    MANIFEST_NAME,
    FactoryConfigError,
    load_factory_config,
    resolve_manifest_path,
)
from factory.workgraph import worktree as worktrees
from factory.workgraph.adapter import (
    DEFAULT_HEARTBEAT_INTERVAL_S,
    SESSION_ID_REFUSAL_MARKER,
    STDOUT_LOG_NAME,
    SUBSCRIPTION_REFUSAL_MARKER,
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
    STANDARDS_SOURCE_LANDING,
    STANDARDS_SOURCE_PINNED,
    StandardsResolution,
    WorkGraph,
    WorkGraphError,
    WorkNode,
    resolve_timeout_s,
    validate_workgraph,
)
from factory.env import (
    ERGANE_ROOT_ENV,
    FACTORY_ROOT_ENV,
    resolve_env_path,
)
from factory.workgraph.worktree import (
    DEFAULT_FACTORY_ROOT,
    PreparedWorktree,
    WorktreeError,
    WorktreeOwnershipError,
)
from factory.verify.models import RefConflictInfo

#: Where the salvage mirror's outcome goes. A mirror failure is reported rather
#: than raised (047 FR-002), so this log line is the only place an operator
#: learns that a terminated node's work is still on one disk.
logger = logging.getLogger(__name__)

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

#: The activity error type for a node directory that belongs to a different
#: clone than the dispatch names (107 FR-003). Never retryable, and that is the
#: whole reason it is not `WORKTREE_FAILED`: two repositories disagreeing about
#: who owns a directory is deterministic, so the retry budget above would spend
#: three attempts arriving at the same refusal, interleaved with Temporal's own
#: retry noise, over a fault only an operator can clear.
WORKTREE_OWNERSHIP_MISMATCH = "WORKTREE_OWNERSHIP_MISMATCH"

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
FACTORY_ROOT_ENV = FACTORY_ROOT_ENV  # re-export for existing callers
ERGANE_ROOT_ENV = ERGANE_ROOT_ENV  # re-export for tests and callers

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
    exactly the way 001's ledger and 002's evidence store do.  Honors the legacy
    `FACTORY_ROOT` env name and reports it once per process.
    """
    root, _choice, _source = worktrees.resolve_factory_root(FACTORY_ROOT_ENV)
    return root


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
        context_window=persona.context_window,
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

    The entry carries the persona's `agent` beside its alias (075-US1): whatever
    is routed by a `ResolvedPersona` runs an agent *and* a model, and an entry
    that answered only one of those questions is how an attempt came to be billed
    to the debugger while running the implementer's model (FR-002).

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
        agent=persona.agent,
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
    standards document the worktree does not have, non-retryable
    `WORKTREE_OWNERSHIP_MISMATCH` when the node's directory is a worktree of a
    different clone, and retryable `WORKTREE_FAILED` when git itself refused.

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
    except WorktreeOwnershipError as exc:
        # Before the ordinary handler, because it is a `WorktreeError` too: the
        # discrimination is the type, so this clause has to see it first.
        raise ApplicationError(
            str(exc), type=WORKTREE_OWNERSHIP_MISMATCH, non_retryable=True
        ) from exc
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


def derive_session_id(issued_id: str, attempt: int) -> str:
    """The runner-visible session id for one execution of the agent activity.

    A pure function of the workflow-issued id and the activity execution attempt
    (107 FR-012): attempt 1 returns the issued id unchanged, so every existing
    archive name, transcript path and status reading is untouched for the runs
    that never retry; any later attempt returns a different, deterministically
    derived, syntactically valid UUID. `uuid5` is deterministic and derives from
    values already in the frame, and the runner rejects a malformed id before it
    rejects a duplicate one (plan R8). The workflow computes nothing new, so the
    replay property is preserved by construction (traps 9 and 10).
    """
    if attempt <= 1:
        return issued_id
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{issued_id}:{attempt}"))


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
        # 107 FR-012: the runner-visible session id is derived once, here, from
        # the workflow-issued id and this execution's attempt number. The first
        # execution keeps the issued id; a retry gets a different, deterministic
        # UUID, so the one relaunch the retry policy exists to provide can start
        # instead of colliding with the id the first execution already used. The
        # frozen context is replaced once and passed down, so the invocation
        # argument and the transcript archive lookup read the same derived id
        # and cannot disagree (plan R9). The workflow's two issuance sites are
        # untouched — the replay property is preserved because the workflow
        # computes nothing new (traps 9 and 10).
        execution_attempt = activity.info().attempt if activity.in_activity() else 1
        derived = derive_session_id(context.session_id, execution_attempt)
        if derived != context.session_id:
            context = replace(context, session_id=derived)
        # The launch backend is resolved from the target repo's `runtime:` key
        # by the adapter itself (011-US2). Nothing overrides it here: an
        # unconditional assignment on this line pinned every production attempt
        # to the host launch for the whole of 011, while US3/US4/US5 proved a
        # boundary no dispatch could reach. Tests that need the host launch
        # declare `runtime: host` in their fixture manifest and get it through
        # the same resolution production uses.
        adapter = adapter_for(DEFAULT_AGENT)
        result = await adapter.run_attempt(
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
        # US3 FR-013: the adapter classifies only by process outcome (FR-012).
        # A subscription-routed attempt whose credential is present but refused by
        # the CLI prints the measured refusal on stdout and exits 1. Reclassify
        # that specific marker as an authentication failure so it is recorded as
        # a named auth failure instead of a diffless AGENT_ERROR.
        result = _classify_subscription_auth_failure(context, result)
        # 107 FR-014: a launch the runner refused because the identifier was
        # already in use arrives as an ordinary AGENT_ERROR with the refusal on
        # stdout. Classify that marker as a named launch refusal — the existing
        # non-retryable launch-failure error type, quoting the runner's own line
        # — never as a missing transcript, and never as a new `Termination`
        # member (plan R13). The subscription classifier *returns* a reclassified
        # result; this one *raises*.
        _raise_if_launch_refused(context, result)
        # 095-US1 FR-001: an attempt the adapter classified structurally as
        # pre-agent gets the dying process's own line attached to it, for the
        # operator and for nothing else. Enrichment, strictly after
        # classification: the termination above was decided without reading a
        # byte of this, so a message no release has printed yet changes what an
        # operator is told and never what the attempt *is* (plan trap 1).
        result = _attach_pre_agent_detail(result)
        return result
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


def _classify_subscription_auth_failure(
    context: AttemptContext, result: AdapterResult
) -> AdapterResult:
    """Reclassify a subscription AGENT_ERROR that carried the CLI auth refusal.

    The adapter itself classifies only by exit status (FR-012). The CLI's
    subscription auth failure is the one exception: it exits 1 and prints the
    refusal on stdout (measured 2026-08-19), which a caller watching stderr
    would read as a silent success. Detecting that specific marker here, in the
    activity that owns interpreting the adapter's output, turns the attempt into
    a named authentication failure (US3-S5/FR-013) instead of a diffless error.
    """
    if result.termination != Termination.AGENT_ERROR:
        return result
    # 154-US1 (FR-006): the route axis decides; a payload that predates the
    # field is answered from the legacy `agent` sentinel.
    if effective_route(context.route, context.agent) != ROUTE_SUBSCRIPTION:
        return result
    if not result.transcript_path:
        return result

    log_path = Path(result.transcript_path) / STDOUT_LOG_NAME
    try:
        log_text = log_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return result
    if SUBSCRIPTION_REFUSAL_MARKER not in log_text:
        return result

    return AdapterResult(
        termination=Termination.AUTH_FAILURE,
        transcript_path=result.transcript_path,
        last_snapshot=result.last_snapshot,
    )


def _raise_if_launch_refused(context: AttemptContext, result: AdapterResult) -> None:
    """Raise a named launch refusal when the runner refused the session id.

    The runner's already-in-use refusal (107 FR-014) arrives as an ordinary
    `AGENT_ERROR` — the binary exists, it started, and it exited 1 — with the
    refusal on stdout. Detecting that marker here, on the success path beside the
    existing `except AdapterError`, turns the attempt into the existing
    non-retryable `AGENT_LAUNCH_FAILED` error type, quoting the runner's own
    line, rather than a missing transcript. It is not a new `Termination` member:
    a launch the runner refused before the first token wrote no diff, so there is
    nothing to grade and no ladder attempt to spend (plan R13). An ordinary
    non-zero exit carrying no marker is left untouched — ordinary ladder input.
    """
    if result.termination != Termination.AGENT_ERROR:
        return
    if not result.transcript_path:
        return

    log_path = Path(result.transcript_path) / STDOUT_LOG_NAME
    try:
        log_text = log_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    if SESSION_ID_REFUSAL_MARKER not in log_text:
        return

    line = next(
        (ln for ln in log_text.splitlines() if SESSION_ID_REFUSAL_MARKER in ln),
        SESSION_ID_REFUSAL_MARKER,
    )
    raise ApplicationError(
        f"runner refused the launch for {context.epic_id}/{context.node_id}: "
        f"{line.strip()}",
        type=AGENT_LAUNCH_FAILED,
        non_retryable=True,
    )


#: How much of the dead process's own line is carried up to the operator. A
#: pre-agent failure's whole stdout was 73 bytes on the day this was measured;
#: the bound is here so that a process which died mid-flood puts a line on a
#: status screen rather than a screenful.
PRE_AGENT_DETAIL_LIMIT = 240


def _attach_pre_agent_detail(result: AdapterResult) -> AdapterResult:
    """Quote the dying process's last words on a pre-agent failure (FR-001).

    The adapter has already classified this attempt from its shape, so nothing
    read here can change what it is — which is exactly why reading it is safe.
    What the operator gets is the one line that names the cause: on 2026-08-28
    "Failed to authenticate: OAuth session expired and could not be refreshed",
    a sentence no classification could have produced and no summary would have
    preserved.

    The *last* non-empty line, because a CLI's banner comes first and its
    complaint comes last. An unreadable log is not an error: the note degrades to
    its context and its general remedy, which is still more than the diffless
    `agent_error` this replaces.
    """
    if result.termination != Termination.PRE_AGENT_FAILURE:
        return result
    if not result.transcript_path:
        return result

    log_path = Path(result.transcript_path) / STDOUT_LOG_NAME
    try:
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return result

    lines = [line.strip() for line in log_text.splitlines() if line.strip()]
    if not lines:
        return result
    return replace(result, detail=lines[-1][:PRE_AGENT_DETAIL_LIMIT])


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
    """Commit whatever the attempt left to the node's branch, mirror it, return the sha.

    Runs on every termination path before any cleanup (constitution VI), and
    commits an empty tree as readily as a dirty one so every terminal attempt is
    observable from the ref alone (SC-004). Idempotent per attempt: a re-run
    after an unrecorded success lands on the same commit.

    The commit is the durable artifact; the mirror is what gets it off this
    machine (047 US1), and the per-attempt ref is what keeps the sha this
    activity returns resolvable after the branch has moved on (047 US2). Both
    run after the commit and outside the conversion below, unconditionally —
    including on the retry path where `salvage` short-circuits, because a retry
    after a failed push is exactly when a mirror is worth running, and a record
    written only inside the commit branch would be skipped on the very path
    Temporal takes to re-make it. Their failures are returned as data and
    logged, never raised: an unreachable remote that failed this activity would
    turn a successful salvage into a failed one.

    The ref is written before the mirror so the mirror can carry it (FR-008).

    The return value stays a plain `str` (047 FR-005). Three call sites in
    `EpicWorkflow` already schedule this activity and discard what it answers;
    widening the payload or adding a fourth command would be a replay hazard for
    every in-flight epic, and nothing here needs one — a linked worktree already
    knows its own remote.
    """
    try:
        sha = await asyncio.to_thread(
            worktrees.salvage,
            request.epic_id,
            request.node_id,
            termination=request.termination,
            attempt=request.attempt,
            factory_root=factory_root(),
        )
    except WorktreeError as exc:
        raise ApplicationError(str(exc), type=WORKTREE_FAILED) from exc

    recorded = await asyncio.to_thread(
        worktrees.record_salvage_ref,
        request.epic_id,
        request.node_id,
        attempt=request.attempt,
        sha=sha,
        factory_root=factory_root(),
    )
    logger.info(
        "salvage ref for %s/%s attempt %s: written=%s %s",
        request.epic_id,
        request.node_id,
        request.attempt,
        recorded.written,
        recorded.detail,
    )

    outcome = await asyncio.to_thread(
        worktrees.mirror_node_branch,
        request.epic_id,
        request.node_id,
        factory_root=factory_root(),
    )
    logger.info(
        "salvage mirror for %s/%s attempt %s: pushed=%s %s; refs pushed=%s %s",
        request.epic_id,
        request.node_id,
        request.attempt,
        outcome.pushed,
        outcome.detail,
        outcome.refs_pushed,
        outcome.refs_detail,
    )
    return sha


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


@dataclass(frozen=True)
class ArchiveAndClearRemoteBranchInput:
    """Which node's live remote branch to archive and clear."""

    epic_id: str
    node_id: str
    target_repo: str


@activity.defn
async def archive_and_clear_remote_branch(
    request: ArchiveAndClearRemoteBranchInput,
) -> list[str]:
    """Archive the node's branch and remove its live name from origin.

    Runs on terminal (non-parked) paths after salvage: the local branch is
    renamed into the archive namespace, the archive is pushed to origin, and
    the live ref is deleted only when an archive ref already holds its tip.
    Returns report lines and never raises: an unreachable remote or a tip no
    archive holds is reported and left alone.
    """
    return await asyncio.to_thread(
        worktrees.archive_and_clear_remote_branch,
        request.target_repo,
        request.epic_id,
        request.node_id,
        factory_root=factory_root(),
    )


@dataclass(frozen=True)
class RefConflictFactsInput:
    """Which node ref to inspect locally for the escalation message (126-US3)."""

    epic_id: str
    node_id: str
    target_repo: str


@activity.defn
async def ref_conflict_facts(
    request: RefConflictFactsInput,
) -> RefConflictInfo | None:
    """Local-only facts about the ref blocking this node.

    The remote tip is read from the local remote-tracking ref, and reachability
    is checked against local archive refs. No remote read is performed.
    Returns None when the local clone has never seen the remote ref.
    """
    return await asyncio.to_thread(
        worktrees.ref_conflict_info,
        request.target_repo,
        request.epic_id,
        request.node_id,
    )


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
        manifest_path, _ = resolve_manifest_path(target_repo)
        return load_factory_config(manifest_path).standards
    except FactoryConfigError:
        return None


# --- resolve_standards (118 US3: FR-008, FR-009) -------------------------------


@dataclass(frozen=True)
class ResolveStandardsInput:
    """Which document to resolve for which node's attempt, and against which trees.

    `standards` is the declared *path* (R11) exactly as `load_prompt_sources`
    read it; `worktree_path` is the tree the attempt will actually run in, whose
    copy is the pinned tree's fallback — the same path the adapter already
    holds, never a second way of naming it. `node_id` makes the activity's own
    log attributable the way every other per-node activity's is.
    """

    epic_id: str
    node_id: str
    target_repo: str
    worktree_path: str
    standards: str | None = None


@activity.defn
async def resolve_standards(request: ResolveStandardsInput) -> StandardsResolution | None:
    """Resolve one attempt's standards text from the landing branch (118 FR-008).

    `load_prompt_sources` reads the declared *path* once per epic; the tree the
    prompt points at, though, is the worktree's — pinned at first dispatch — so
    a correction the operator lands mid-epic reaches no attempt of a running
    node. This closes that gap per attempt, where it is cheap: the document is
    by construction not the node's work product, so reading a fresh copy for
    every attempt moves no goalpost the reuse rule protects.

    The resolution lives in this module — the caller that already reads the
    repository — because the prompt builder is pure by construction and must
    stay so (118 trap 6): it takes a path and now an already-resolved text, and
    reads no repository of its own.

    The fallback is not politeness (trap 7): the landing branch may be
    unreachable, the path may not exist there yet, and the pinned tree's copy is
    what every attempt before this spec read. Any read failure — no `origin`,
    a fetch that fails, a path absent at the landing head, a decode error —
    falls back and is *reported* in `detail`, so the archived prompt says what
    the attempt received and why (FR-009, trap 8). Nothing here raises for a
    document that could not be fetched: a transient network condition must not
    become a dead node.

    Runs in a worker thread: the landing head is a fetch, and a fetch owns the
    wall clock for as long as the remote takes.
    """
    if not request.standards:
        return None
    return await asyncio.to_thread(
        _resolve_standards_sync,
        Path(request.target_repo),
        Path(request.worktree_path),
        request.standards,
    )


def _resolve_standards_sync(
    repo: Path, worktree: Path, standards: str
) -> StandardsResolution:
    """The blocking half: fetch the landing head, read the document at it.

    Pinned-copy fallback on any failure, with the failure carried in `detail`.
    The landing head is read the same way `capture_base_ref` reads it — remote
    first, clone's head when there is no remote — so the document resolved here
    is the one on the branch the factory actually lands on.
    """
    try:
        head = worktrees.capture_base_ref(repo)
        document = _git_show(repo, head, standards)
    except Exception as exc:  # noqa: BLE001 - the fallback *is* the contract
        # Trap 7: no failure mode here may fail the node. A document the
        # landing branch cannot produce falls back to the pinned copy, with
        # the reason carried for the archived prompt to quote.
        pinned = worktree / standards
        try:
            text = pinned.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as fallback_exc:
            # No standing copy either. Still not a raise: the attempt runs,
            # and the report says what the agent will not be told.
            return StandardsResolution(
                text="",
                source=STANDARDS_SOURCE_PINNED,
                detail=(
                    f"standards '{standards}' could not be read from either "
                    f"the landing branch ({exc}) or the pinned tree "
                    f"({fallback_exc}); no standards section can be resolved "
                    "for this attempt"
                ),
            )
        return StandardsResolution(
            text=text,
            source=STANDARDS_SOURCE_PINNED,
            detail=f"landing branch unreadable ({exc}); using the pinned tree's copy",
        )

    return StandardsResolution(
        text=document, source=STANDARDS_SOURCE_LANDING
    )


def _git_show(repo: Path, rev: str, path: str) -> str:
    """One document's text at `rev`, via `git show`; raises on any failure.

    The worktree module's `_git` is the one git wrapper here — allowlisted
    environment, bounded timeout, `WorktreeError` on refusal — and `landed.py`
    already reads documents out of a revision the same way. A failure is
    exactly what the fallback arm wants to see, so it propagates as-is.
    """
    return worktrees._git(repo, "show", f"{rev}:{path}")
