"""The `build` noun: start an epic, watch it, and send its signals.

`ergane build start|status|pause|resume|kill|answer|resolve` is the operator
surface over `EpicWorkflow`.  Almost every behaviour is a port from
`factory/workgraph/cli.py`, with two deliberate changes:

- Exit codes follow the `ergane` contract: transport/service failures are 3,
  user errors are 1.
- The signal verbs (`pause`, `resume`, `kill`, `answer`, `resolve`) give the
  five signals the workflow already declared a typed CLI instead of a hand-typed
  `temporal workflow signal` invocation.

One argument convention holds across the noun (068 FR-010): **every verb that
acts on an epic already started takes `epic_id` as its first positional** —
`status`, `pause`, `resume`, `kill`, `answer`, `resolve`, `reset`,
`complete-node-externally`.  The id is what Temporal's own output prints and
what an operator has to hand when something has gone wrong, and `reset` was the
one verb that asked for something else, at exactly the moment it was hardest to
produce.  Three verbs are declared exceptions, for reasons that are about what
they *are* rather than about consistency: `start` is keyed by the compiled
artifact because it creates the epic, `salvage` is keyed by it because it must
work with no Temporal at all, and `external-completion-count` takes no
positional because it reports a store-wide count.  The family is pinned by
`tests/test_build_verbs_take_an_epic_id.py`, which fails if a new subcommand
appears in neither list.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import sqlite3
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from temporalio.client import Client, WorkflowQueryFailedError, WorkflowQueryRejectedError
from temporalio.api.enums.v1.workflow_pb2 import PendingActivityState
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode
from datetime import timezone

#: The server answered but the workflow would not answer this query. A read that
#: is refused degrades: the command reports the cause and still exits 0.
#: Distinct from a transport failure because the connection is fine.
QUERY_REFUSED: tuple[type[BaseException], ...] = (
    WorkflowQueryFailedError,
    WorkflowQueryRejectedError,
)

#: The server did not answer at all. Nothing this command wanted to read is
#: readable, so the read fails with the transport exit code.
TRANSPORT_FAILED: tuple[type[BaseException], ...] = (RPCError,)

from factory.activities.verify_activities import (
    DEFAULT_VERIFICATION_DB_PATH,
    VERIFICATION_DB_PATH_ENV,
)
# `EXIT_TRANSPORT` hoisted: `_reset_epic` has named it since it was written
# without importing it, so a non-NOT_FOUND RPC failure on `describe` raised
# `NameError` instead of the operator error it meant to.
from factory.cli.errors import (
    EXIT_OK,
    EXIT_TRANSPORT,
    EXIT_USAGE,
    EXIT_USER,
    OperatorError,
)
from factory.env import (
    ERGANE_ROOT_ENV,
    ERGANE_VERIFICATION_DB_PATH_ENV,
    FACTORY_ROOT_ENV,
    FACTORY_VERIFICATION_DB_PATH_ENV,
    resolve_env_path,
)
from factory.cli.landing import (
    LANDING_DIAL_FLAGS,
    add_landing_dial_flags,
    halt_after_pass_from_args,
    landing_config_from_args,
    landing_overrides_from_args,
)
from factory.cli.nouns import Noun, _open_preflight_client
from factory.cli.promotion import (
    add_promotion_persona_flag,
    checked_promotion_persona,
    with_promotion_persona,
)
from factory.config import ConfigError, Persona, WriteScope, load_personas
from factory.verify.diffbounds import DIFF_REFUSAL_THRESHOLD
from factory.verify.factory_yaml import FactoryConfigError, load_loop_config
from factory.notify.service import (
    DEFAULT_TEMPORAL_ADDRESS,
    DEFAULT_TEMPORAL_NAMESPACE,
    EXTERNAL_COMPLETION_SIGNAL,
    QUESTION_SIGNAL_NAME,
    SIGNAL_NAME,
    TEMPORAL_ADDRESS_ENV,
    TEMPORAL_NAMESPACE_ENV,
)
# 127-US3 (FR-009): the gate tail is clipped through the escalation pages' own
# clipper rather than a second one. The clipper is promoted to this public name
# in that module, behaviour and bound unchanged; before this story no production
# module imported a private name from `factory.notify.messages`.
from factory.notify.messages import EVIDENCE_TAIL_LINES, tail
from factory.usage.litellm_client import LiteLLMClient
from factory.usage.models import UsageSnapshot
from factory.verify.models import (
    UNKNOWN_BASE_REF,
    EscalationChoice,
    EscalationRecord,
    GateStatus,
    OutputCheck,
    QuestionRecord,
    VerificationConfig,
    VerificationResult,
)
from factory.verify.store import (
    EXPIRED,
    ExternalCompletionCount,
    connect as verify_connect,
    connect_readonly as verify_connect_readonly,
    dispatch_groups,
    epic_history,
    external_completion_count,
    get_escalation,
    get_question,
    node_history,
    pending_escalations,
    pending_questions,
)
from factory.activities.agent_activities import (
    DEFAULT_FACTORY_ROOT as DEFAULT_FACTORY_ROOT_PATH,
    FACTORY_ROOT_ENV,
)
from factory.workgraph.adapter import transcript_dir
from factory.workgraph.worktree import resolve_factory_root
from factory.workgraph.models import (
    NodeState,
    WorkGraph,
    WorkGraphError,
    WorkNode,
    validate_workgraph,
)
from factory.workgraph.preflight import (
    PreflightFinding,
    check_aliases,
    engine_skew_findings,
    landing_readiness_preflight,
    prompt_assembly_preflight,
)
from factory.workgraph.cli import DEFAULT_SPECS_ROOT
from factory.workgraph.credential_status import (
    credential_status,
    render_credential_status,
)
from factory.workgraph.workflow import TASK_QUEUE, EpicInput, EpicWorkflow
from factory.mergequeue.forge import (
    ForgeError,
    UnknownForgeError,
    resolve_forge_for_repo,
)
from factory.mergequeue.models import LandingConfig
from factory.mergequeue.reset import reset_node_on_forge, reset_note
from factory.workgraph.worktree import (
    NodeSalvage,
    branch_name,
    landing_branch,
    read_node_salvage,
    reset as reset_worktree,
    _has_remote as has_remote,
)
from factory.workgraph.landed import _resolve_default_head

#: Compiled artifact naming convention, shared with `spec derive`.
ARTIFACT_NAME = "workgraph.json"

#: Structural timeout used by the CLI's vacuous persona registry.
_STRUCTURAL_TIMEOUT_S = 1

#: Signal names the workflow already declares.
PAUSE_SIGNAL = "pause_epic"
RESUME_SIGNAL = "resume_epic"
KILL_SIGNAL = "kill_epic"


# --- ports from factory/workgraph/cli.py --------------------------------------


#: The one prefix that turns a spec directory's name into a workflow id.
#: Written once, on purpose: every build verb must inherit normalization from
#: the seam below rather than re-deriving it (046 plan, trap 7).
EPIC_ID_PREFIX = "epic-"

#: 156 US1: the command that clears a worker running code the tree has moved
#: past, on this host (systemd user units, `ergane worker install`). Named once:
#: the refusal at `_start_epic` and every message it composes must spell the
#: same remedy, so an operator never diagnoses a skew they could have restarted.
RESTART_REMEDY = "systemctl --user restart ergane-worker"


def workflow_id(epic_id: str) -> str:
    """The one id convention: predictable from the spec directory's name.

    Also the one place the prefix is applied, which is why the normalization
    lives here.  Temporal's own output prints the workflow id
    (`epic-011-agent-sandbox`), the operator pastes that into a build verb, and
    before 046-US3 the verb dialled `epic-epic-011-agent-sandbox`.  An id that
    already carries the prefix is returned unchanged, so both forms name one
    workflow and every verb gets the fix without being edited.

    This narrows nothing and widens nothing: exactly one id comes back, so
    exactly one workflow is dialled.  An id that names no running epic still
    fails, with the refusal `looked_for` composes.
    """
    if epic_id.startswith(EPIC_ID_PREFIX):
        return epic_id
    return f"{EPIC_ID_PREFIX}{epic_id}"


def workflow_id_candidates(epic_id: str) -> tuple[str, ...]:
    """Every workflow id this argument could name, the dialled one first.

    One entry for the ordinary spec-directory form.  Two when the argument
    already carries the prefix: the id `workflow_id` dials, and the doubled id
    that a spec directory *literally* named `epic-…` produced before ids were
    normalized.  The second entry exists so a refusal can name the collision —
    it is never dialled.  Chasing it would widen what counts as found, which is
    a worse defect than the double prefix this replaces.
    """
    dialled = workflow_id(epic_id)
    doubled = f"{EPIC_ID_PREFIX}{epic_id}"
    if doubled == dialled:
        return (dialled,)
    return (dialled, doubled)


def looked_for(epic_id: str) -> str:
    """The parenthetical every not-found refusal shares.

    Unchanged for the ordinary form — an id that matches nothing fails today's
    way, naming the one workflow id it dialled.  For an already-prefixed id it
    names both candidates, so a collision with a spec directory literally named
    `epic-…` is legible rather than silent.
    """
    candidates = workflow_id_candidates(epic_id)
    if len(candidates) == 1:
        return f"looked for workflow id {candidates[0]}"
    return (
        f"looked for workflow id {candidates[0]}, not {candidates[1]} "
        f"(a spec directory literally named '{epic_id}' would be the latter)"
    )


def _positive_int(value: str) -> int:
    """An argparse type: a positive integer, or a usage error."""
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"max-concurrent-nodes must be a positive integer, got {value!r}"
        )
    if parsed < 1:
        raise argparse.ArgumentTypeError(
            f"max-concurrent-nodes must be a positive integer, got {value!r}"
        )
    return parsed


def load_workgraph(path: str | Path) -> WorkGraph:
    """Read a compiled artifact back into the graph the workflow dispatches."""
    location = Path(path)
    try:
        document = json.loads(location.read_text(encoding="utf-8"))
    except OSError as error:
        raise WorkGraphError(f"cannot read {location}: {error}") from error
    except json.JSONDecodeError as error:
        raise WorkGraphError(f"{location} is not valid JSON: {error}") from error

    if not isinstance(document, dict) or not isinstance(document.get("nodes"), list):
        raise WorkGraphError(
            f"{location} is not a compiled workgraph: expected an object with a "
            "'nodes' list (write one with `ergane spec derive`)"
        )

    for field in ("specs_root", "target_repo"):
        value = document.get(field)
        if value is None:
            continue
        try:
            resolved = Path(value).resolve()
        except (OSError, ValueError) as error:
            raise WorkGraphError(
                f"{location} is not dispatchable: {field} is not a resolvable "
                f"path: {value!r} ({error})"
            ) from error
        if not resolved.is_absolute() or str(resolved) != str(value):
            raise WorkGraphError(
                f"{location} is not dispatchable: {field} must be an absolute "
                f"path, got {value!r} (resolved to {resolved})"
            )

    try:
        return WorkGraph(
            epic_id=document["epic_id"],
            feature=document["feature"],
            specs_root=document["specs_root"],
            target_repo=document["target_repo"],
            nodes=[WorkNode(**node) for node in document["nodes"]],
        )
    except (KeyError, TypeError) as error:
        raise WorkGraphError(
            f"{location} is not a compiled workgraph: {error}"
        ) from error


def _persona_registry(graph: WorkGraph) -> Mapping[str, Persona]:
    """A registry that answers for every persona the graph names, and no more.

    `skills` is reserved and unused (062-US3 FR-009): structural personas pass an
    empty tuple only to satisfy the dataclass.
    """
    return {
        node.persona: Persona(
            name=node.persona,
            agent="",
            model=None,
            fallback=None,
            # skills is reserved and unused; the empty tuple keeps the dataclass happy.
            skills=(),
            write_scope=WriteScope.WORKTREE,
            needs_worktree=True,
            timeout_s=_STRUCTURAL_TIMEOUT_S,
        )
        for node in graph.nodes
    }


def _preflight_registry() -> dict[str, Persona]:
    """The CLI's own view of the registry, read from its `personas.yaml`."""
    return load_personas()


async def _run_preflight(graph: WorkGraph) -> list[PreflightFinding]:
    """Check that every prompt assembles and the landing can happen, then the proxy.

    The same checks the roadmap's pre-dispatch activity runs, in the same order
    and from the same module (044 FR-004, 107 FR-011): an epic started by hand
    dies of an unassemblable `tasks.md` exactly the way a scheduled one does, so
    it is refused here rather than one tick after `ergane build start` printed a
    workflow id. Assembly reads `specs_root/feature` — where the graph itself
    says its authored trio lives, and where dispatch will read it.

    107 adds the two facts the landing turns on, and they go second because they
    are the same bargain one step later: a node worktree registered to another
    clone, and a landing branch that would be inferred rather than declared, both
    cost a full build before they announce themselves. This arm resolves *this*
    host's runtime root, the way `_reset_epic` does; the worker resolves its own,
    and on a split host the finding names which root it read (plan R5).

    All three collected, none short-circuited: an operator fixing one refusal per
    run is the failure mode, and here each round trip is a dispatch that has to
    be started again.
    """
    findings = engine_skew_findings()
    findings += prompt_assembly_preflight(
        graph, Path(graph.specs_root) / graph.feature
    )
    findings += landing_readiness_preflight(graph, _preflight_factory_root())
    findings += await check_aliases(
        graph, _preflight_registry(), _open_preflight_client()
    )
    # Informational findings (`passed=True`) are reported by the module but must not
    # stop dispatch (126 US1 FR-005: an unreachable remote is not a refusal).
    return [f for f in findings if not isinstance(f, PreflightFinding) or not f.passed]


def _preflight_factory_root() -> Path:
    """The runtime root this host keeps node worktrees under (107 FR-009).

    Read the way the worker's `factory_root()` reads it, so the directories this
    checks are the directories a dispatch on this host would reuse — the env
    override first, then `.ergane/`, then the legacy `.factory/`.
    """
    root, _choice, _source = resolve_factory_root(FACTORY_ROOT_ENV)
    return root


async def _preflight_exit_code(findings: list[PreflightFinding]) -> int:
    """Map preflight findings to the `ergane` scripting contract.

    A proxy that would not answer is a service failure (exit 3).  A proxy that
    answered and reported an operator-fixable problem is a user error (exit 1).
    """
    if not findings:
        return EXIT_OK
    if any(finding.transport for finding in findings):
        from factory.cli.errors import EXIT_TRANSPORT

        return EXIT_TRANSPORT
    return EXIT_USER


async def _connect() -> Client:
    """One client, from the notify bridge's exact environment contract.

    Implemented as a wrapper around the package-level seam so tests can
    substitute a fake client: `factory.cli.main` reloads this file on every
    invocation, so a patch on the imported `build` module is lost, but the
    package object is stable and a patch on `factory.cli.nouns._open_client`
    survives.
    """
    from factory.cli.nouns import _open_client

    return await _open_client()


async def _live_spend(
    client: Client,
    handle: Any,
    document: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    """Each running attempt's newest heartbeat snapshot, per node.

    A read: if the describe call fails we degrade to no live spend rather than
    killing the status report. The two `Exception` catches below are not around
    Temporal calls — they guard decoding a heartbeat payload and reading the
    client data converter, both of which can raise for local reasons.
    """
    try:
        description = await handle.describe()
    except TRANSPORT_FAILED:
        # Degrade: live spend is optional extra detail.
        return {}
    except QUERY_REFUSED:
        # A workflow that refuses a status query will also refuse describe.
        # Degrade rather than report the same refusal twice.
        return {}

    pending = description.raw_description.pending_activities
    try:
        converter = client.data_converter
    except Exception:
        converter = None

    nodes: Mapping[str, Mapping[str, Any]] = document["nodes"]
    live: dict[str, Mapping[str, Any]] = {}
    for activity_info in pending:
        if not activity_info.HasField("activity_type"):
            continue
        if activity_info.activity_type.name != "run_agent_attempt":
            continue
        if converter is None:
            continue
        node_id = activity_info.activity_id
        if node_id not in nodes:
            continue
        entry: dict[str, Any] = {
            "state": PendingActivityState.Name(
                activity_info.state
            ).removeprefix("PENDING_ACTIVITY_STATE_"),
            "activity_attempt": activity_info.attempt,
        }
        if activity_info.HasField("last_heartbeat_time"):
            entry["last_heartbeat_at"] = (
                activity_info.last_heartbeat_time.ToDatetime(tzinfo=timezone.utc)
            ).isoformat()
        if activity_info.HasField("heartbeat_details"):
            try:
                decoded = await converter.decode(
                    list(activity_info.heartbeat_details.payloads),
                    [UsageSnapshot | None],
                )
            except Exception:
                continue
            snapshot = decoded[0]
            if snapshot is not None:
                entry["spend_usd"] = snapshot.spend_usd
                entry["cost_basis"] = "proxy_estimate"
                entry["captured_at"] = snapshot.captured_at
        live[node_id] = entry
    return live


def render_status(
    epic_id: str,
    document: Mapping[str, Any],
    execution_status: str,
    *,
    live_spend: Mapping[str, Mapping[str, Any]] | None = None,
    landing_head: tuple[str, str] | None = None,
) -> str:
    """The human view: the epic's line, then one line per node, in query order.

    `landing_head` is `(branch, sha)` read live by the caller, or `None` when it
    could not be read (118-US2, FR-007). It is a parameter rather than something
    resolved here because this function is a renderer and reads no git.
    """
    nodes: Mapping[str, Mapping[str, Any]] = document["nodes"]
    id_width = max((len(node_id) for node_id in nodes), default=0)
    state_width = max(
        (len(str(node["state"])) for node in nodes.values()), default=0
    )
    live = live_spend or {}

    lines = [
        f"epic {epic_id}  {document['epic_state']}  "
        f"execution {execution_status}"
    ]
    lines.extend(_ladder_dial_lines(document))
    lines.extend(_landing_dial_lines(document))
    lines.extend(_halt_after_pass_lines(document))
    for node_id, node in nodes.items():
        figure = live.get(node_id)
        live_token = _live_agent_token(figure)
        provenance = node.get("provenance")
        external_token = (
            f"  external completion: {provenance}" if provenance else ""
        )
        lines.append(
            f"{node_id.ljust(id_width)}  {str(node['state']).ljust(state_width)}  "
            f"attempt {node['attempt']}  {node['branch']}"
            f"{_routing_token(node)}{_base_token(node, landing_head)}"
            f"{live_token}{external_token}{_reason_token(node)}"
            f"{_housekeeping_token(node)}"
        )
        lines.extend(_attempt_note_lines(node))
    return "\n".join(lines)


#: What the landing half of the base token says when no head was read. It names
#: the *reading* rather than the landing, because "landing unavailable" beside a
#: node with an open PR would read as a claim about the landing. A degraded
#: reading, never a guessed number: a head inferred from the base would read as
#: "current" for every node in the epic.
_LANDING_HEAD_UNAVAILABLE = "landing head unavailable"

#: How much of a sha the comparison needs. Twelve hex digits is what the rest of
#: this repository's operator surfaces print, and the full value stays on the
#: verification row for anyone auditing rather than diagnosing.
_SHA_WIDTH = 12


def _base_token(
    node: Mapping[str, Any], landing_head: tuple[str, str] | None
) -> str:
    """The node's pinned base beside the landing branch's current head (FR-007).

    The whole value of this story's reading is that the two numbers sit on one
    line for one node, because the question an operator is asking is a
    comparison: a base three landings behind the landing branch is valid history
    and unmergeable in practice, and until now that fact was an investigation.

    Absent for a node that has prepared nothing — there is no pin, and printing
    the sentinel beside a landing head would invite a comparison with nothing on
    one side of it. Absent, too, for an older worker's answer, which carries no
    such key: this reading degrades rather than inventing one (052).

    `landing_head` is `None` in two cases that read the same way on purpose: the
    caller tried and could not resolve a head, and the caller never had a
    repository to try — `ergane status`'s floor table reuses this renderer for
    epics whose target repos it does not resolve. Both are "no head was read
    here", which is what the token says.
    """
    base = node.get("base_ref")
    if not base or base == UNKNOWN_BASE_REF:
        return ""
    pinned = f"  base {str(base)[:_SHA_WIDTH]}"
    if landing_head is None:
        return f"{pinned}  {_LANDING_HEAD_UNAVAILABLE}"
    branch, head = landing_head
    return f"{pinned}  landing head {branch} {head[:_SHA_WIDTH]}"


#: What the dial block is headed with, and what a reading that could not be
#: taken prints instead. Spelled once: the degraded line has to be recognisable
#: as the same block's absence rather than as a new kind of message.
_DIALS_HEADER = "landing dials"
_DIALS_UNAVAILABLE = f"{_DIALS_HEADER}  unavailable"


def _landing_dial_lines(document: Mapping[str, Any]) -> list[str]:
    """The landing dials in force, one per line, each said to be set or defaulted.

    081-US3, FR-008/FR-009. US1 made these settable and US2 carried them to a
    scheduled epic's children; neither is falsifiable from outside the process
    that typed the flag, which is the shape of the last five readiness defects.
    This is the reading that makes them falsifiable — printed under the epic's
    own line, before the nodes, because it is a property of the epic rather than
    of any node.

    The provenance is read from the epic's `landing_overrides` — the field names
    its operator actually typed, carried from the command that typed them —
    never by comparing a value against `LandingConfig()`. That comparison is the
    obvious implementation and it is wrong in precisely the case the operator is
    checking: an operator who typed `--landing-poll-interval-s 60` is asking
    whether their flag arrived, and "60, same as the default" does not answer it.

    Flags rather than field names, because the flag is what the operator typed
    and what they would retype; `LANDING_DIAL_FLAGS` is the CLI's own map, so a
    dial added to the model with a flag behind it appears here for free and one
    added without a flag is US1's failing test, not a silently missing line.

    FR-010 governs everything below: this is a *reading*, and no shape of it may
    cost the operator the epic and node lines they came for. The document is
    whatever the worker sent — a worker that predates this story sends no dials
    at all, and one queried before `run` recorded them sends `null` — so a
    reading that cannot be taken degrades to one honest line. It is never
    guessed: printing the code defaults for an epic whose dials could not be
    read would invent the exact answer this story exists to stop inventing.
    """
    try:
        config = document.get("landing_config")
        if not isinstance(config, Mapping):
            return [_DIALS_UNAVAILABLE]
        overrides = document.get("landing_overrides") or ()
        if isinstance(overrides, (str, bytes)) or not isinstance(overrides, Iterable):
            return [_DIALS_UNAVAILABLE]
        typed = set(overrides)

        dials: list[tuple[str, str, str]] = []
        for flag, field in LANDING_DIAL_FLAGS.items():
            if field not in config:
                # A dial the worker did not report is a dial this CLI cannot
                # read. Half a block would read as a complete one.
                return [_DIALS_UNAVAILABLE]
            dials.append(
                (flag, str(config[field]), "set" if field in typed else "default")
            )
    except Exception:
        # The last resort, and the reason it is broad: every branch above reads
        # a decoded payload built by a worker this CLI does not control, and
        # spec 052's rule is that `ergane build status` degrades rather than
        # breaks. A malformed dial costs its own line and nothing else.
        return [_DIALS_UNAVAILABLE]

    flag_width = max(len(flag) for flag, _, _ in dials)
    value_width = max(len(value) for _, value, _ in dials)
    return [_DIALS_HEADER] + [
        f"  {flag.ljust(flag_width)}  {value.rjust(value_width)}  {provenance}"
        for flag, value, provenance in dials
    ]


#: What the ladder's dial block is headed with, and what a reading that could
#: not be taken prints instead — the landing block's two constants, one rung
#: earlier in the epic's life.
_LADDER_HEADER = "ladder dials"
_LADDER_UNAVAILABLE = f"{_LADDER_HEADER}  unavailable"

#: The three bounds the ladder can stop on, named as they are *declared*: the
#: keys of a target repo's `factory.yaml` `ladder:` block, which are also the
#: fields of `VerificationConfig` and the words an escalation uses when one of
#: them runs out (095-US3, FR-008). One vocabulary, so an operator who reads
#: "ladder exhausted: max_judge_retries = 2" on Telegram can find that number on
#: this page without translating.
#:
#: Flags would be the landing block's spelling and would be wrong here: nobody
#: types these on `ergane build start`. They are declared per target repo, which
#: is why the block carries no set-or-defaulted column — the CLI never sees the
#: manifest and would have to guess the provenance, and 081-US3's whole argument
#: is that a guessed provenance answers the wrong question.
#:
#: `max_pre_agent_failures` is deliberately not here. It bounds the refusals
#: that never reach a rung (095-US2), so it is not one of the three the story is
#: about, and the escalation names it in full when it is the bound that fired.
_LADDER_DIALS = ("max_attempts", "max_judge_retries", "debugger_cycles")


def _ladder_dial_lines(document: Mapping[str, Any]) -> list[str]:
    """The ladder's bounds in force, one per line (095-US3, FR-009).

    The reading 081-US3 gave the landing half, for the half that decides how
    many chances a story gets. The dials were settable and unobservable: an epic
    dispatched with `ladder: {max_attempts: 6, debugger_cycles: 3}` printed
    neither number anywhere, so the six attempts it spent under a rewrite cap of
    two could only be explained by reading `factory/verify/ladder.py`. That is
    the same defect class 081 was written for, one rung earlier.

    Printed beside the landing dials because they are the same kind of fact — a
    property of the epic rather than of any node — and because the two together
    are what an operator diagnosing a stuck build compares.

    Degraded rather than guessed, and 052's rule again: a worker that predates
    this story sends no ladder config at all, and one queried before `run`
    recorded it sends `null`. Neither may cost the operator the epic and node
    lines they came for, and neither may be answered with the code defaults —
    printing `max_attempts 3` for an epic nobody can read the dials of invents
    the exact answer this block exists to stop inventing.
    """
    try:
        config = document.get("ladder_config")
        if not isinstance(config, Mapping):
            return [_LADDER_UNAVAILABLE]

        dials: list[tuple[str, str]] = []
        for dial in _LADDER_DIALS:
            if dial not in config:
                # A bound the worker did not report is a bound this CLI cannot
                # read. Half a block would read as a complete one.
                return [_LADDER_UNAVAILABLE]
            dials.append((dial, str(config[dial])))
    except Exception:
        # The landing block's last resort, for the landing block's reason: this
        # reads a decoded payload built by a worker the CLI does not control,
        # and a malformed dial costs its own line and nothing else.
        return [_LADDER_UNAVAILABLE]

    name_width = max(len(name) for name, _ in dials)
    value_width = max(len(value) for _, value in dials)
    return [_LADDER_HEADER] + [
        f"  {name.ljust(name_width)}  {value.rjust(value_width)}"
        for name, value in dials
    ]


#: What the halting-mode block says, and what it says when the reading cannot be
#: taken. The wording distinguishes an absent landing from a failed one (FR-014).
_HALT_HEADER = "halting mode"
_HALT_UNAVAILABLE = f"{_HALT_HEADER}  unavailable"
_LANDING_NOT_ATTEMPTED = (
    "landing not attempted: the epic was dispatched with --halt-after-pass; "
    "to land, start the epic without that flag and ensure the target repo has "
    "a forge configured"
)


def _halt_after_pass_lines(document: Mapping[str, Any]) -> list[str]:
    """One line when halting mode is in force, otherwise nothing."""
    try:
        if not document.get("halt_after_pass"):
            return []
    except Exception:
        return []
    return ["", _LANDING_NOT_ATTEMPTED]


def _reason_token(node: Mapping[str, Any]) -> str:
    """Why a node ended, when the ladder did not produce the ending (078-US3).

    `terminal_reason` has been on the record and in the query since 025; what it
    has never been is *printed*. The case that made the gap cost an evening is a
    landing poller that stopped — the record knew the poll had died and the
    status still read `ENQUEUED` — so the reason now ends the node's line
    (FR-009). Absent for every node that ended the way the ladder said it would,
    which is nearly all of them.

    Whitespace is flattened because the line is the unit an operator reads. The
    text is never truncated: the tail of a forge's refusal is usually the half
    that names the cause.
    """
    reason = node.get("terminal_reason")
    if not reason:
        return ""
    return "  reason: " + " ".join(str(reason).split())


def _housekeeping_token(node: Mapping[str, Any]) -> str:
    """What the factory tidied up after the node ended (127-US2 FR-007).

    The sibling `_reason_token` wanted: US1 split the terminal record's one
    overloaded field in two — why the node *ended*, and what the archive-and-
    clear did *after* it ended — and the overwrite happened because the second
    was printed as the first. The two therefore reach the operator as two
    labelled tokens on the same line, `reason:` and `housekeeping:`, and a line
    that reads one for the other is as wrong as the overwrite was.

    A sibling rather than a second flattener (trap 6): whitespace is flattened
    exactly the way `_reason_token` flattens it, for the same reason — the line
    is the unit an operator reads, and a multi-line git report is still one
    status line. The text is never truncated for the same reason too: the half
    that names what was kept is usually at the end.

    Absent for nearly every node: a report exists only when the archive-and-
    clear activity had something to say, and most endings have nothing to
    tidy. A node with a report and no cause prints the report alone, which is
    the truth US1's truth table row two already kept — neither token may claim
    the other's fact.
    """
    report = node.get("housekeeping_report")
    if not report:
        return ""
    return "  housekeeping: " + " ".join(str(report).split())


def _attempt_note_lines(node: Mapping[str, Any]) -> list[str]:
    """What the node's latest attempt was, when the line above cannot say it.

    Its own line rather than a token, because it is a sentence and it carries a
    remedy: 095-US1's whole point is that the operator learns "the session could
    not authenticate, run `claude login`" from the status screen instead of from
    a transcript nobody opens (FR-002). Absent for every attempt that reached the
    agent, and for an older worker's answer, which carries no such key.

    Whitespace is flattened for the same reason `_reason_token` flattens it — the
    line is the unit an operator reads — and the text is never truncated: the
    half that names the remedy is the half at the end.
    """
    note = node.get("attempt_note")
    if not note:
        return []
    return ["  " + " ".join(str(note).split())]


def _routing_token(node: Mapping[str, Any]) -> str:
    """What the node's current attempt is running, or nothing (075-US3 FR-012).

    The line already says which attempt a node is on; this says what that
    attempt *is*, which is the reading nothing offered while a rung ran the
    wrong model for eight days. The alias is printed verbatim, sentinel
    included: an attempt whose persona the epic's snapshot could not resolve
    reads `<unresolved>` rather than borrowing the node's own model (US3-S3).

    Absent for a node that has dispatched nothing — a persona with no attempt
    behind it is not a reading — and absent for an older worker's answer, which
    carries neither key.
    """
    persona = node.get("persona")
    if not persona:
        return ""
    return f"  persona {persona}  model {node.get('model_alias', '')}"


def _live_agent_token(figure: Mapping[str, Any] | None) -> str:
    """What the pending agent attempt is doing, and when spend was measured.

    The state is the pending activity's, not the node's own state: the workflow
    cannot see an activity's acceptance, so `describe()` is the only reading
    that answers it. Spend stays optional; when it is present, the capture time
    travels beside it so a value retained across a retry cannot read as fresh.
    """
    if figure is None:
        return ""
    token = f"  agent {figure['state']}"
    if "spend_usd" in figure:
        token += (
            f"  spend ${figure['spend_usd']:.2f} (proxy estimate; live cost only) "
            f"captured {figure['captured_at']}"
        )
    return token


# --- commands -----------------------------------------------------------------


def start_command(args: argparse.Namespace) -> int:
    """Start one epic from a compiled graph.

    Everything that can be checked without a server is checked without one:
    file parse, structural validation, promotion persona, and proxy-url
    presence.  Only then is a client built.

    The promotion persona is checked first of all, before the graph is even
    read, because it is the one input that is wholly about what the operator
    typed: a typo in it is answerable without opening a file, and answering it
    last would mean an operator with both a stale graph and a mistyped persona
    fixes them one round trip at a time (FR-009).

    081-US1: the landing dials ride the same principle one step earlier still.
    They are refused by `argparse` at parse time (`factory/cli/landing.py`), so
    by the time this function runs a dial is either absent or usable, and what
    is left here is assembly.
    """
    promotion_persona = checked_promotion_persona(args.promotion_persona)
    landing_config = landing_config_from_args(args)
    # 081-US3 (FR-009): the names beside the values. Read here, from the same
    # namespace and in the same breath, because this is the only place in the
    # system that still knows the difference between a dial the operator typed
    # and a dial that happens to equal its default.
    landing_overrides = landing_overrides_from_args(args)
    # 109-US3: whether to halt at PASSED rather than attempting to land.
    halt_after_pass = halt_after_pass_from_args(args)

    try:
        graph = load_workgraph(args.graph)
    except WorkGraphError as error:
        raise OperatorError(str(error)) from error

    if not graph.nodes:
        raise OperatorError(
            f"workgraph '{graph.epic_id}' has zero nodes — nothing to build; "
            "use `ergane spec derive` to compile a non-empty graph"
        )

    try:
        validate_workgraph(graph, _persona_registry(graph))
    except WorkGraphError as error:
        raise OperatorError(str(error)) from error

    proxy_url = _resolved_proxy_url()

    try:
        config, verify_order, diff_refusal_bytes = load_loop_config(graph.target_repo)
    except FactoryConfigError as exc:
        raise OperatorError(
            f"preflight: manifest: [{exc.rule}] {exc.problem}"
        ) from exc

    # The flag overlays the manifest rather than replacing it: the ladder the
    # epic runs is the target repo's, with the one rung the operator declared
    # on this invocation switched on (FR-007).  Omitted, it changes nothing —
    # including a rung the manifest itself declared (FR-010).
    config = with_promotion_persona(config, promotion_persona)

    return asyncio.run(
        _start_epic(
            graph,
            proxy_url,
            args.max_concurrent_nodes,
            config=config,
            verify_order=verify_order,
            diff_refusal_bytes=diff_refusal_bytes,
            landing_config=landing_config,
            landing_overrides=landing_overrides,
            halt_after_pass=halt_after_pass,
        )
    )


def _resolved_proxy_url() -> str:
    """Where this host's gateway is, environment first, declaration second.

    A CLI boundary is where this belongs: the endpoint is already a declared
    workflow input threaded from here (`EpicInput.proxy_url`), so the workflow
    reads neither the environment nor the disk (048 FR-007, constitution IV).
    The endpoint and not the credential: the master key is read on the worker
    host by the activity that mints the key, so demanding it here would refuse
    an epic on a host well able to run it.

    No default is available and none would be honest: an epic started against a
    guessed proxy mints keys the agent cannot use and burns an attempt to
    discover it (constitution VII). What changed in 048 is only that the
    refusal names *both* ways to satisfy it — the resolver supplies the routes,
    this site supplies the reason.
    """
    from factory.controlplane.resolve import (
        ControlPlaneResolutionError,
        resolve_proxy_url,
    )

    try:
        return resolve_proxy_url().url
    except ControlPlaneResolutionError as error:
        raise OperatorError(
            f"{error}; the agent's virtual key is only honored at the proxy, "
            "so no epic can be started without it"
        ) from error


async def _start_epic(
    graph: WorkGraph,
    proxy_url: str,
    max_concurrent_nodes: int = 1,
    *,
    config: VerificationConfig | None = None,
    verify_order: tuple[str, ...] | None = None,
    diff_refusal_bytes: int | None = None,
    landing_config: LandingConfig | None = None,
    landing_overrides: tuple[str, ...] = (),
    halt_after_pass: bool = False,
) -> int:
    client = await _connect()

    try:
        findings = await _run_preflight(graph)
    except ConfigError as error:
        raise OperatorError(f"preflight: {error}") from error

    exit_code = await _preflight_exit_code(findings)
    if findings:
        for finding in findings:
            print(
                f"ergane: preflight [{finding.check}]: {finding.detail}",
                file=sys.stderr,
            )
        return exit_code

    if config is None:
        config = VerificationConfig()
    if verify_order is None:
        verify_order = ("gates", "diff_check", "judge")
    if diff_refusal_bytes is None:
        # 092 FR-004. `None` here is "this caller read no manifest", never "no
        # ceiling": the seam's own `None` disables the check, and that spelling
        # must not be reachable by omission. A caller that named nothing gets
        # today's threshold, which is what it got before the key existed.
        diff_refusal_bytes = DIFF_REFUSAL_THRESHOLD
    if landing_config is None:
        # A caller that named no dials, not an operator who lowered one to
        # nothing: the model's own defaults decide, spelled in exactly one place
        # (`factory/mergequeue/models.py:390-400`).
        landing_config = LandingConfig()

    # 156 US1 (FR-001): the refusal stands between preflight and dispatch. A
    # worker running code the tree has moved past wedges the epic's first
    # workflow task in retry, so the epic is not started — the CLI says which
    # code each side runs and which command clears it, and exits non-zero
    # before `start_workflow` is reached.
    #
    # An advertisement of `None` refuses: an unknown revision cannot be
    # compared, and the conservative direction is the same refusal an unequal
    # one earns (US1-S3). An *unreadable* advertisement refuses nothing: no
    # open epic, an unanswered read — absence of evidence is not skew, and a
    # refusal there would lock an operator out of their own factory on the day
    # they most need it (US1-S4's direction, applied to the read itself).
    cli_revision = _cli_revision()
    advertisement = await _worker_advertisement(client)
    refusal = (
        skew_refusal(advertisement, cli_revision)
        if advertisement is not _UNREADABLE
        else None
    )
    if refusal is not None:
        print(f"ergane: {refusal}", file=sys.stderr)
        return EXIT_USER

    epic_workflow_id = workflow_id(graph.epic_id)
    try:
        await client.start_workflow(
            EpicWorkflow.run,
            EpicInput(
                graph=graph,
                proxy_url=proxy_url,
                config=config,
                verify_order=verify_order,
                max_concurrent_nodes=max_concurrent_nodes,
                landing_config=landing_config,
                # 081-US1 (FR-005). Until this story the argument list stopped
                # one line above, so a hand-started epic ran the merge queue's
                # code defaults whatever its operator wanted.
                #
                # 081-US3 (FR-009): and the line below is why the epic can say
                # which of those dials were its operator's doing. A caller that
                # names none — the default — dispatches an epic that reports
                # every dial as defaulted, which is what it is.
                landing_overrides=landing_overrides,
                # 109-US3: halting mode stops at PASSED and never attempts to land.
                halt_after_pass=halt_after_pass,
                # 092-US2 (FR-004): the target repo's declared diff ceiling,
                # pinned from the manifest this command just read.
                diff_refusal_bytes=diff_refusal_bytes,
            ),
            id=epic_workflow_id,
            task_queue=TASK_QUEUE,
        )
    except WorkflowAlreadyStartedError as error:
        raise OperatorError(
            f"epic '{graph.epic_id}' is already running "
            f"(workflow id {epic_workflow_id})"
        ) from error

    print(epic_workflow_id)
    return EXIT_OK


def _cli_revision() -> str | None:
    """The revision of the CLI code that is running this command."""
    # Tests patch the package-level seam; when present, use it so a reload does
    # not rebind to the real `git rev-parse`.
    from factory.cli.nouns import _cli_revision_for_tests

    seam = _cli_revision_for_tests()
    if seam is not None:
        return seam
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip() or None
    except Exception:
        return None


#: What `_worker_advertisement` returns when no advertisement can be read: no
#: open epic, an unanswered listing, a refused query. Deliberately distinct from
#: `None`, which is an *advertisement* — a worker that answered "I have no
#: revision" (pre-053, or not a git checkout) and is refused for it (US1-S3).
#: Unreadable is not unknown; the two `None`s must never meet, or every first
#: `build start` on an empty floor would refuse and lock the operator out.
_UNREADABLE = object()

#: The type of `_worker_advertisement`'s answer, spelled out once.
Advertisement = str | None | object


async def _worker_advertisement(client: Client) -> Advertisement:
    """What the serving worker advertises about its revision, or `_UNREADABLE`.

    156 US1 (FR-002): the comparison must use the values the existing seam
    already produces — `EpicStatus.worker_revision`, the field 053's interceptor
    stamps into every `EpicInput` and `epic_status` answers with. The epic this
    command would start does not exist yet, so the advertisement is read off an
    epic that is already open: the interceptor re-stamps every activation, so
    any open epic's answer advertises the revision of the worker serving it
    *now* — exactly the comparison the refusal needs, whatever the epic is.

    The listing is the roadmap capacity read's own production shape
    (`factory/activities/roadmap_activities.py`, `ExecutionStatus = "Running"`),
    narrowed server-side the way `_running_epics` narrows it; the first open
    epic's query is taken rather than the whole floor's, because one
    advertisement is the fact and every open epic answers the same worker.

    Everything the read can hit — an empty floor, a server that will not answer
    the listing, an epic that refuses the query, one that closed between the
    two, a client that cannot be asked at all — degrades to `_UNREADABLE`, the
    same posture `engine_skew_findings` takes: the check activates only on
    evidence.
    """
    try:
        listed: str | None = None
        async for execution in client.list_workflows('ExecutionStatus = "Running"'):
            execution_id = str(execution.id)
            # Epic-shaped without re-reading the prefix constant: `workflow_id`
            # is idempotent, so it returns an already-prefixed id unchanged and
            # prefixes anything else (046's seam; the AST pin holds).
            if workflow_id(execution_id) == execution_id:
                listed = execution_id
                break
    except TRANSPORT_FAILED:
        return _UNREADABLE
    except AttributeError:
        # A client without the listing seam cannot be asked. That is a shape
        # this module never dials for, not a skew: refuse nothing on it.
        return _UNREADABLE
    if listed is None:
        return _UNREADABLE
    try:
        document = await client.get_workflow_handle(listed).query("epic_status")
    except TRANSPORT_FAILED:
        return _UNREADABLE
    except QUERY_REFUSED:
        return _UNREADABLE
    except AttributeError:
        return _UNREADABLE
    if not isinstance(document, Mapping):
        return _UNREADABLE
    revision = document.get("worker_revision")
    if revision is None or isinstance(revision, str):
        return revision
    return _UNREADABLE


def _skew_notice(worker_revision: str | None, cli_revision: str | None) -> str | None:
    """A human-readable notice when the worker and CLI disagree, or None."""
    if worker_revision is None:
        return (
            f"worker revision is unknown (CLI revision {cli_revision or 'unknown'}); "
            "the worker predates this check or is not a git checkout"
        )
    if cli_revision is None:
        return None
    if worker_revision == cli_revision:
        return None
    return (
        f"worker is running different code: worker revision {worker_revision}, "
        f"CLI revision {cli_revision}"
    )


def skew_refusal(worker_revision: str | None, cli_revision: str | None) -> str | None:
    """The dispatch refusal for a skewed worker, or None when dispatch may proceed.

    156 US1 (FR-001): at dispatch the notice is not enough — an epic started
    under skew wedges its first workflow task in retry. Same `None` arms as
    `_skew_notice`, verbatim: worker-`None` is an unknown revision, which cannot
    be compared and refuses (the conservative direction, US1-S3); CLI-`None` is
    this CLI's own blindness, which must not lock the operator out (US1-S4);
    equality is the aligned case, which composes nothing (FR-006).

    The difference is the third fact: a refusal the operator reads at a terminal
    carries its remedy in the same line — worker revision, tree revision,
    restart command (US1-S5). One line, so scrollback is a record (US3).

    A separate function, not a flag on the notice: the notice renders in status
    output for every epic past and present, and the refusal must fire only where
    an epic would be created (plan trap 1).
    """
    if worker_revision is None:
        return (
            f"worker revision is unknown (CLI revision {cli_revision or 'unknown'}); "
            f"refusing to start an epic the worker would wedge. "
            f"Remedy: {RESTART_REMEDY}."
        )
    if cli_revision is None:
        return None
    if worker_revision == cli_revision:
        return None
    return (
        f"worker is running different code: worker revision {worker_revision}, "
        f"CLI revision {cli_revision} — refusing to start an epic the worker "
        f"would wedge in workflow-task retry. Remedy: {RESTART_REMEDY}."
    )


def status_command(args: argparse.Namespace) -> int:
    """Read one epic's live state."""
    return asyncio.run(_query_status(args.epic_id, as_json=args.as_json))


def credential_status_command(args: argparse.Namespace) -> int:
    """Show which subscription credential the factory will use."""
    status = credential_status()
    if args.as_json:
        print(
            json.dumps(
                {
                    "source": status.source,
                    "expires_at": (
                        status.expires_at.isoformat() if status.expires_at else None
                    ),
                    "remedies": list(status.remedies),
                },
                indent=2,
            )
        )
    else:
        print(render_credential_status(status))
    return EXIT_OK


def ship_command(args: argparse.Namespace) -> int:
    """Validate, derive, summarise and — with confirmation — dispatch one spec."""
    from factory.cli.nouns.spec import derive_spec_command, validate_spec_command
    from factory.config import ConfigError, load_personas

    spec_dir = Path(args.spec_dir)
    epic_id = spec_dir.resolve().name

    # Stage 1: validate.  Stream the full labeled output and stop on refusal.
    print(f"ship: validating {spec_dir / ARTIFACT_NAME}")
    validate_code = validate_spec_command(args)
    if validate_code != EXIT_OK:
        return validate_code

    # Stage 2: derive.  Stream the full labeled output and stop on failure.
    print(f"ship: deriving {spec_dir / ARTIFACT_NAME}")
    # Ship requires the artifact on disk at stage 3, and derive no longer
    # writes one for a `--json` call with no output path (130-US1 FR-001).
    # Ship's own `--json` is a presentation flag and says nothing about where
    # the graph goes, so ship asks for the write the way FR-002 defines a
    # request: by path, on a copy of the namespace — the flag the operator
    # passed must not decide whether the file ship needs exists.
    derive_args = argparse.Namespace(**vars(args))
    if derive_args.output is None:
        derive_args.output = str(spec_dir / ARTIFACT_NAME)
    derive_code = derive_spec_command(derive_args)
    if derive_code != EXIT_OK:
        return derive_code

    # Resolve the artifact path exactly the way derive does.
    artifact_path = Path(args.output) if args.output else spec_dir / ARTIFACT_NAME
    if not artifact_path.is_file():
        raise OperatorError(
            f"ship expected compiled graph at {artifact_path}; "
            "derive reported success but wrote no artifact"
        )

    # Stage 3: load the graph and print the summary.
    graph = load_workgraph(artifact_path)
    print(f"ship: compiled graph '{graph.epic_id}' has {len(graph.nodes)} node(s)")

    try:
        personas = load_personas()
    except ConfigError as error:
        raise OperatorError(
            f"ship cannot resolve personas for the summary: {error}"
        ) from error

    # Declaration order is scheduling order (R10); the summary says both.
    order = [node.id for node in graph.nodes]
    print(f"dispatch order: {' '.join(order)}")
    for node in graph.nodes:
        persona = personas.get(node.persona)
        alias = persona.model if persona is not None and persona.model is not None else "<registry default>"
        print(f"  {node.id}  persona {node.persona}  model {alias}")

    # Stage 4: confirm unless --yes, then dispatch.
    if not args.yes:
        refused = _confirm_dispatch(epic_id)
        if refused is not None:
            return refused

    # Ship sets exactly one attribute on its namespace: the compiled graph path.
    args.graph = str(artifact_path)
    return start_command(args)


def _landing_head(document: Mapping[str, Any]) -> tuple[str, str] | None:
    """The landing branch and its head *now*, or None if it cannot be read.

    118-US2, FR-007. Read at status time rather than carried from dispatch,
    because a head captured when the worktree was pinned is precisely the number
    that cannot show staleness — it is the base.

    The repository comes from the epic's own `target_repo` and the branch from
    that repository's declared `landing_branch`, never from the directory the
    operator's shell is in (constitution IX): a status read against whatever
    clone happened to be nearby would answer with a head that governs nothing.
    An answer that omits `target_repo` — an older worker's — gets no reading.

    Without a fetch, the same choice `factory/cli/status.py` makes for the same
    kind of reading: a status command may not hang on a network, and every
    dispatch fetches, so a clone the factory runs against carries a recent
    `origin/<branch>`. The broad catch is 052's rule — this reading costs its
    own token and never the report.
    """
    try:
        target_repo = document.get("target_repo")
        if not target_repo:
            return None
        repo = Path(str(target_repo))
        if not repo.is_dir():
            return None
        branch = landing_branch(repo)
        return branch, _resolve_default_head(repo, branch, fetch=False)
    except Exception:
        return None


async def _query_status(epic_id: str, *, as_json: bool) -> int:
    client = await _connect()
    handle = client.get_workflow_handle(workflow_id(epic_id))

    refusal: str | None = None
    try:
        document = await handle.query("epic_status")
    except QUERY_REFUSED as error:
        # A workflow-side refusal is a degraded *reading*, not a failed command.
        # The epic exists (the server reached it) but will not describe itself,
        # most often because its history predates a field the query result now
        # declares. Report the cause in place and exit 0.
        refusal = str(error) or type(error).__name__
        document: Mapping[str, Any] = {"nodes": {}}
    except TRANSPORT_FAILED as error:
        if error.status is RPCStatusCode.NOT_FOUND:
            raise OperatorError(
                f"no epic '{epic_id}' is running here "
                f"({looked_for(epic_id)})"
            ) from error
        from factory.cli.errors import EXIT_TRANSPORT

        raise OperatorError(
            f"cannot read epic '{epic_id}': {error}", EXIT_TRANSPORT
        ) from error

    try:
        described = await handle.describe()
        status = described.status
        if status is None:
            from factory.cli.errors import EXIT_TRANSPORT

            raise OperatorError(
                f"cannot read epic '{epic_id}': no execution status reported",
                EXIT_TRANSPORT,
            )
        execution_status = status.name
    except TRANSPORT_FAILED as error:
        from factory.cli.errors import EXIT_TRANSPORT

        raise OperatorError(
            f"cannot read epic '{epic_id}': {error}", EXIT_TRANSPORT
        ) from error
    except QUERY_REFUSED as error:
        # The epic is reachable but would not describe itself. Degrade the
        # execution-status reading in place rather than kill the report.
        if refusal is None:
            refusal = str(error) or type(error).__name__
        execution_status = "unavailable"

    live_spend = await _live_spend(client, handle, document)
    landing_head = _landing_head(document)
    cli_revision = _cli_revision()
    worker_revision = document.get("worker_revision")
    skew_notice = _skew_notice(worker_revision, cli_revision)
    if as_json:
        rendered: Any = dict(document)
        rendered["execution_status"] = execution_status
        if live_spend:
            rendered["live_spend"] = live_spend
        if landing_head is not None:
            rendered["landing_head"] = {
                "branch": landing_head[0],
                "head": landing_head[1],
            }
        if refusal is not None:
            rendered["refusal"] = refusal
        if skew_notice is not None:
            rendered["skew_notice"] = skew_notice
        print(json.dumps(rendered, indent=2))
    else:
        if refusal is not None:
            print(f"epic {epic_id}  unavailable  ({refusal})")
        else:
            print(
                render_status(
                    epic_id,
                    document,
                    execution_status,
                    live_spend=live_spend,
                    landing_head=landing_head,
                )
            )
        if skew_notice is not None:
            print(f"ergane: {skew_notice}", file=sys.stderr)
    return EXIT_OK


def pause_command(args: argparse.Namespace) -> int:
    """Send `pause_epic`."""
    return asyncio.run(_send_signal(args.epic_id, PAUSE_SIGNAL))


def resume_command(args: argparse.Namespace) -> int:
    """Send `resume_epic`."""
    return asyncio.run(_send_signal(args.epic_id, RESUME_SIGNAL))


def kill_command(args: argparse.Namespace) -> int:
    """Send `kill_epic`, confirming first unless --yes."""
    if not args.yes:
        try:
            confirmed = input(f"Kill epic '{args.epic_id}'? [y/N] ")
        except EOFError:
            confirmed = ""
        if confirmed.lower() not in ("y", "yes"):
            print("ergane: kill cancelled", file=sys.stderr)
            return EXIT_USER
    return asyncio.run(_send_signal(args.epic_id, KILL_SIGNAL))


def _confirm_dispatch(epic_id: str) -> int | None:
    """Reusable confirmation primitive: ask once, return EXIT_USER on decline.

    Same shape as `kill_command`'s confirmation: one `input`, `EOFError` as a
    decline, the same cancelled-message shape, and `EXIT_USER` on decline.
    Returns `None` when confirmed so callers can keep returning their own code.
    """
    try:
        confirmed = input(f"Dispatch epic '{epic_id}'? [y/N] ")
    except EOFError:
        confirmed = ""
    if confirmed.lower() not in ("y", "yes"):
        print("ergane: ship cancelled", file=sys.stderr)
        return EXIT_USER
    return None


def complete_node_externally_command(args: argparse.Namespace) -> int:
    """Send `complete_node_externally` with provenance."""
    return asyncio.run(
        _send_signal_with_args(
            args.epic_id,
            EXTERNAL_COMPLETION_SIGNAL,
            [args.node_id, args.branch, args.provenance],
        )
    )


def external_completion_count_command(args: argparse.Namespace) -> int:
    """Report the durable count of externally-completed nodes."""
    path = _verification_store_path()
    if not path.exists():
        # No store means no use of the hatch: the count is 0, explicitly
        # measured by the absence of a counter (035-US3, FR-008).
        result = ExternalCompletionCount(total=0, by_spec={})
        _print_external_completion_count(result, args.as_json)
        return EXIT_OK

    try:
        conn = verify_connect_readonly(path)
    except sqlite3.Error as error:
        raise OperatorError(
            f"cannot read external-completion count from {path}: {error}",
            EXIT_TRANSPORT,
        ) from error
    try:
        result = external_completion_count(conn)
    finally:
        conn.close()

    _print_external_completion_count(result, args.as_json)
    return EXIT_OK


def attempts_command(args: argparse.Namespace) -> int:
    """Report what each of an epic's attempts was verified on. Reads, never writes.

    Shaped like `salvage` and for the same reason: no Temporal client. The row
    outlives the workflow, and the moment an operator asks what a verdict rested
    on is usually the moment the execution has aged out of Temporal — a reading
    that dialled the server would be unavailable exactly when it is wanted.

    The reading exists because of 092 (FR-007, US3-S3). Since US1 and US2 the
    judge may rule on a diff it was shown only part of: between the attention
    budget and the repository's refusal threshold, `prepare_diff` abridges and
    the verdict is formed over an abridgement. That is the outcome those stories
    exist to make reachable, and it is safe under Principle VIII only if a PASS
    taken that way can be told from one taken on a diff the judge read whole.
    Nothing else printed anywhere could tell them apart: `ergane build status`
    reports the workflow's own state and never the evidence row, so the fact was
    on the record and in nobody's hands.

    Every answer is exit 0. An epic nothing was recorded for, and a store that
    does not exist yet, are honest answers to "what was verified" rather than
    errors — the only refusal is a store this process cannot read, which is a
    transport failure and says so.
    """
    as_json = getattr(args, "as_json", False)
    path = _verification_store_path()
    if not path.exists():
        # Absent is "nothing has been recorded here", the same answer
        # `external-completion-count` gives — and, as there, a read never
        # creates the store it is reading.
        print(_no_attempts_line(args.epic_id, path))
        return EXIT_OK

    try:
        conn = verify_connect_readonly(path)
    except sqlite3.Error as error:
        raise OperatorError(
            f"cannot read verification attempts from {path}: {error}",
            EXIT_TRANSPORT,
        ) from error
    try:
        results = epic_history(conn, args.epic_id)
    except sqlite3.Error as error:
        raise OperatorError(
            f"cannot read verification attempts from {path}: {error}",
            EXIT_TRANSPORT,
        ) from error
    finally:
        conn.close()

    if as_json:
        print(
            json.dumps(
                {
                    "epic_id": args.epic_id,
                    "attempts": [
                        dataclasses.asdict(result) for result in results
                    ],
                    "evidence_store": {"state": "available", "path": str(path)},
                },
                indent=2,
            )
        )
        return EXIT_OK

    if not results:
        print(_no_attempts_line(args.epic_id, path))
        return EXIT_OK

    print(render_attempts(args.epic_id, results))
    return EXIT_OK


def _no_attempts_line(epic_id: str, path: Path) -> str:
    """The empty answer, naming what was read so it can be disbelieved."""
    return f"no verification has been recorded for epic '{epic_id}' (read {path})"


#: What the judge-input token says when the row predates 092-US3, or when the
#: check never weighed a diff at all — a read-scoped node, an empty worktree.
#: Spelled out rather than left blank, because the one reading this verb must
#: never offer is silence that looks like "the judge saw it whole".
_JUDGE_INPUT_UNRECORDED = "judge input: not recorded"


def render_attempts(epic_id: str, results: Sequence[VerificationResult]) -> str:
    """The human view: the epic's line, then one line per recorded attempt.

    A renderer, so it reads no store and no clock: the caller holds the rows.
    Columns are padded from the widest value present rather than from a fixed
    width, the way `render_status` does it, so one long node id does not push
    every other line out of alignment with itself.

    A node built more than once gets a heading over each of its builds, naming
    which of how many it is and the dispatch that ran it (117 US3-S2). Without
    it a re-dispatched node printed as one long run of attempts — five lines
    that read exactly like a node that took five attempts once, which is the
    thing the operator most needs to be able to tell apart and the one thing
    nothing printed. A node dispatched once, which is nearly all of them, gets
    no heading at all: the count answers a question it does not raise, and a
    line over every node would push the readings this verb exists for one row
    further down for every attempt in the store (FR-009).
    """
    id_width = max((len(result.node_id) for result in results), default=0)
    form_width = max((len(str(result.form.value)) for result in results), default=0)

    counted = f"{len(results)} verification" + ("" if len(results) == 1 else "s")
    lines = [f"epic {epic_id}  {counted}"]
    groups = dispatch_groups(results)
    # The grouping is the store's, taken as handed back rather than recomputed:
    # a renderer that re-sorted would be a second opinion about the order.
    totals = Counter(group.results[0].node_id for group in groups)
    seen: Counter[str] = Counter()
    for group in groups:
        node_id = group.results[0].node_id
        seen[node_id] += 1
        if totals[node_id] > 1:
            lines.append(
                f"{node_id.ljust(id_width)}  "
                f"dispatch {seen[node_id]} of {totals[node_id]}  {group.dispatch}"
            )
        for result in group.results:
            lines.append(
                f"{result.node_id.ljust(id_width)}  attempt {result.attempt}  "
                f"{str(result.form.value).ljust(form_width)}  "
                f"{result.verdict.value}  {_judge_input_token(result.output_check)}"
            )
            lines += _contradiction_lines(result)
    return "\n".join(lines)


def _contradiction_lines(result: VerificationResult) -> list[str]:
    """What this attempt did not charge the node for, indented under its line.

    116 US3-S3. A PASS composed over a judge that returned FAIL is the shape
    that needs explaining, and until this reading existed the explanation lived
    only in a JSON column — so the operator best placed to notice that the judge
    persona keeps contradicting green gates was the one least likely to look.

    Extra lines rather than another token on the attempt line, because there can
    be more than one and each carries a quotation. Nothing is printed for the
    ordinary attempt: silence here is the record saying the judge contradicted
    no measurement, which is what every row but a handful will say, and a line
    announcing that on every attempt would bury the ones that matter.

    Each line names the four things the record holds — the scenario the finding
    was neutralised on, the gate, the status that was actually measured, and the
    judge's own words. The claim is quoted rather than summarised for the reason
    `GateContradiction` keeps it: a reading that dropped it would send its
    reader back to the stored reasoning to find out what was disagreed with,
    which is the trip this whole verb exists to save.
    """
    return [
        f"    contradicted the {contradiction.gate} gate "
        f"(recorded {GateStatus(contradiction.recorded_status).value}) "
        f"on {contradiction.scenario}: {contradiction.claim!r}"
        for contradiction in result.gate_contradictions
    ]


def _judge_input_token(check: OutputCheck) -> str:
    """How much of this attempt's diff the judge was shown (092 FR-007).

    Three readings, never two. *Abridged* carries the numbers, because "part of
    it" is not actionable and "100206 bytes against a 65536-byte limit" is: an
    operator deciding whether to trust the PASS is deciding whether a third of
    a diff could have hidden the criterion. *Whole* is a
    claim the row makes, not an inference from a missing field. And a row that
    recorded neither says so, because reading it as "whole" would certify every
    verdict taken before this story existed on the authority of code that could
    not tell.

    The numbers come out of the record, never out of this module's constants:
    an attempt judged under an attention budget that has since moved has to be
    read under the one it was actually judged under, which is why the record
    carries it. The rendering says "limit" rather than naming that budget for
    the reason `tests/test_final_sweep.py` enforces on this whole component —
    it may not spell enforcement vocabulary in code (D-021).
    """
    record = check.abridgement
    if record is None:
        return _JUDGE_INPUT_UNRECORDED
    measured = f"{record.total_bytes} bytes against a {record.limit_bytes}-byte limit"
    if not record.abridged:
        return f"judge input: whole, {measured}"
    return (
        f"judge input: abridged, {measured} "
        f"({record.over_limit_bytes} bytes over)"
    )


# --- why: one verb assembles the causal chain (127-US3, FR-009) ---------------


def why_command(args: argparse.Namespace) -> int:
    """Assemble the causal chain behind a dead node — one command, two sources.

    The evidence is spread across two places, and nothing joined them: the
    verification store holds the verdicts, the gate results and the judge's
    feedback and outlives the workflow; the ending — the terminal reason, the
    landing's queue outcomes and their rejection cause — is in workflow memory
    and reaches a reader only through the `epic_status` query. Answering "why
    did this die" was a filesystem walk and a `journalctl` read, which is the
    cost this verb exists to end.

    The store half is read the way `attempts_command` reads it, with no Temporal
    client — the transcript path is composed, never opened, because the walk is
    the work being removed (127 plan trap 11). The query half is read the way
    `_query_status` reads it, but its `NOT_FOUND` is *not* refused on the
    status code alone (127-US5, FR-010): both "no such epic" and "the execution
    aged out" arrive as that one status, and the store rows are the only fact
    that separates them — no rows refuse, rows degrade to the store half of
    the chain with the ending named absent.
    """
    path = _verification_store_path()
    try:
        conn = verify_connect_readonly(path)
    except sqlite3.Error as error:
        raise OperatorError(
            f"cannot read verification evidence from {path}: {error}",
            EXIT_TRANSPORT,
        ) from error
    try:
        if args.node_id is not None:
            history = node_history(conn, args.epic_id, args.node_id)
        else:
            history = epic_history(conn, args.epic_id)
    except sqlite3.Error as error:
        raise OperatorError(
            f"cannot read verification evidence from {path}: {error}",
            EXIT_TRANSPORT,
        ) from error
    finally:
        conn.close()

    document: Mapping[str, Any] | None = None
    ending_note: str | None = None
    try:
        document = _query_why_document(args.epic_id)
    except _ExecutionAgedOut:
        # NOT_FOUND on the query — the same status a never-started epic
        # produces, so the store rows read above are the only fact that
        # separates the two absences (127-US5, FR-010).
        if not history:
            raise OperatorError(
                f"no epic '{args.epic_id}' is running here and the "
                f"verification store at {path} holds no rows for it "
                f"({looked_for(args.epic_id)})"
            ) from None
        # Rows outlived their execution: the store half above is the answer,
        # the ending is named absent rather than the whole reading refused
        # (US5-S2).
        ending_note = (
            "the execution has aged out of the server; the ending "
            "(terminal reason, queue outcomes) died with it"
        )

    print(
        render_why(
            args.epic_id,
            args.node_id,
            history,
            document,
            path,
            ending_note=ending_note,
        )
    )
    return EXIT_OK


def _query_why_document(epic_id: str) -> Mapping[str, Any] | None:
    """The `epic_status` answer, or None when the query is refused.

    A query the workflow will not answer is a degraded reading, not a failed
    command: the store half of the chain is still real, and the ending is
    reported as unavailable rather than as absent. `NOT_FOUND` is not decided
    here — it reaches this verb indistinguishable from "no such epic", and
    the caller holds the store rows that separate them (127-US5, FR-010), so
    it surfaces as `_ExecutionAgedOut` for `why_command` to branch on.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_query_why(epic_id))
    finally:
        loop.close()


class _ExecutionAgedOut(Exception):
    """`epic_status` answered NOT_FOUND while the store held rows (127-US5).

    Raised past the dial because only `why_command` holds the rows already
    read — the discriminator is the store, not the status code, so the dial
    cannot decide alone (FR-010).
    """


async def _query_why(epic_id: str) -> Mapping[str, Any] | None:
    """The async half of `why_command`'s query read."""
    client = await _connect()
    handle = client.get_workflow_handle(workflow_id(epic_id))
    try:
        return await handle.query("epic_status")
    except QUERY_REFUSED:
        # The epic exists but will not describe itself. The store half of the
        # chain is still real; the ending is what is unavailable.
        return None
    except TRANSPORT_FAILED as error:
        if error.status is RPCStatusCode.NOT_FOUND:
            raise _ExecutionAgedOut from error
        raise OperatorError(
            f"cannot read epic '{epic_id}': {error}", EXIT_TRANSPORT
        ) from error


#: How a landing's queue outcome reaches the chain line — the `_value` shape
#: the escalation renderer uses, inlined for one enum read off a query answer.
def _queue_outcome_token(outcome: Any) -> str:
    return outcome.value if isinstance(outcome, Enum) else str(outcome)


def _why_queue_lines(status: Mapping[str, Any]) -> list[str]:
    """The landing's queue history, oldest first, with the rejection cause."""
    history = status.get("landing_history") or ()
    lines: list[str] = []
    for entry in history:
        if isinstance(entry, Mapping):
            outcome = _queue_outcome_token(entry.get("outcome"))
            at = entry.get("at") or ""
        else:
            outcome = _queue_outcome_token(getattr(entry, "outcome", entry))
            at = getattr(entry, "at", "")
        lines.append(f"  queue: {outcome}" + (f" at {at}" if at else ""))
    rejection = status.get("rejection_cause")
    if rejection:
        lines.append(f"  rejection cause: {_queue_outcome_token(rejection)}")
    return lines


def _why_failing_gate(result: VerificationResult) -> list[str]:
    """The failing gate and a bounded tail of its output.

    Clipped through the escalation pages' own clipper, promoted to a public
    name for this import (FR-009): `output_tail` is up to 32 KiB, and one
    unclipped print of it is half this story's diff bound (127 plan trap 15).
    A gate that passed is named without its output, the way the escalation
    pages already print one.
    """
    lines: list[str] = []
    for gate in result.gate_results:
        status = gate.status.value if isinstance(gate.status, Enum) else str(gate.status)
        suffix = "" if status == GateStatus.PASS.value else f" — exit {gate.exit_code}"
        lines.append(f"  gate {gate.name}: {status}{suffix}")
        if status != GateStatus.PASS.value and gate.output_tail:
            lines.append(f"    gate output (last {EVIDENCE_TAIL_LINES} lines):")
            for tail_line in tail(gate.output_tail).splitlines():
                lines.append(f"      {tail_line}")
    return lines


def _why_attempt_lines(result: VerificationResult) -> list[str]:
    """One attempt's half of the chain: verdict, gates, judge."""
    lines = [
        f"  attempt {result.attempt}: {result.verdict.value} "
        f"({result.form.value}, verified at {result.finished_at})"
    ]
    lines += [f"    {line}" for line in _why_failing_gate(result)]
    if result.judge is not None:
        lines.append(f"    judge: {result.judge.outcome.value}")
        if result.judge.feedback:
            lines.append("    judge feedback:")
            for tail_line in tail(result.judge.feedback).splitlines():
                lines.append(f"      {tail_line}")
    return lines


def _why_ending_for_node(node: Mapping[str, Any]) -> list[str]:
    """One node's ending, read off its `NodeStatus` document."""
    lines: list[str] = []
    reason = node.get("terminal_reason")
    if reason:
        lines.append(f"  ending: {reason}")
    housekeeping = node.get("housekeeping_report")
    if housekeeping:
        lines.append(f"  housekeeping: {housekeeping}")
    lines += _why_queue_lines(node)
    return lines


def render_why(
    epic_id: str,
    node_id: str | None,
    history: Sequence[VerificationResult],
    document: Mapping[str, Any] | None,
    store_path: Path,
    *,
    ending_note: str | None = None,
) -> str:
    """The human view of the chain: per node, latest attempt first.

    A renderer, so it reads no store and no clock: the caller holds the rows
    and the query answer. The transcript directory is *composed* from the
    factory root this process already resolves through `resolve_env_path` —
    the declared root, never the working directory (constitution IX) — and
    printed without being opened, listed or tailed (127 plan trap 11).

    What counts as a failure worth explaining is the node's own state read off
    the query answer — KILLED, FAILED, or a landing that did not end MERGED —
    not whether a node argument was passed: US3-S3 names a passed node
    explicitly and must still be told it has no failure to explain rather than
    be shown an empty chain. A node the query knows nothing about (no rows yet,
    a store half only) falls back to its verification record alone.
    """
    factory_root = resolve_env_path(
        ERGANE_ROOT_ENV, FACTORY_ROOT_ENV, DEFAULT_FACTORY_ROOT_PATH
    )

    statuses: Mapping[str, Mapping[str, Any]] = (
        {} if document is None else document.get("nodes", {})
    )
    if node_id is not None and document is not None and node_id not in statuses:
        raise OperatorError(
            f"epic '{epic_id}' is running but holds no node '{node_id}' "
            f"(nodes: {', '.join(statuses) or 'none'})"
        )

    # The node ids this run is asked about: the one named, or every node
    # either source holds, store order first.
    all_ids: list[str] = []
    for result in history:
        if result.node_id not in all_ids:
            all_ids.append(result.node_id)
    for id_of_node in statuses:
        if id_of_node not in all_ids:
            all_ids.append(id_of_node)
    if node_id is not None:
        all_ids = [node_id]

    by_node: dict[str, list[VerificationResult]] = {}
    for result in history:
        by_node.setdefault(result.node_id, []).append(result)

    lines = [f"epic {epic_id} — why"]
    for id_of_node in all_ids:
        if node_id is not None and id_of_node != node_id:
            continue
        node_status = statuses.get(id_of_node)
        results = by_node.get(id_of_node, [])
        if not _is_failure_to_explain(node_status, results):
            # US3-S3, the control: a node that passed and landed has no
            # failure to explain. Say so, once, rather than print an empty
            # chain for it.
            lines.append(f"{id_of_node}: no failure to explain")
            continue
        lines.append(f"{id_of_node}:")
        for result in reversed(results):
            lines += _why_attempt_lines(result)
        if results:
            latest = results[-1]
            transcript = transcript_dir(
                factory_root, epic_id, id_of_node, latest.attempt
            )
            lines.append(f"  transcript: {transcript}")
        elif node_status is not None:
            transcript = transcript_dir(
                factory_root, epic_id, id_of_node,
                int(node_status.get("attempt") or 1),
            )
            lines.append(f"  transcript: {transcript}")
        if node_status is not None:
            lines += _why_ending_for_node(node_status)
        elif ending_note is not None:
            # 127-US5: the execution aged out — the rows above outlived it,
            # so the answer is real and only the ending is named absent.
            lines.append(f"  ending: unavailable — {ending_note}")
        elif document is None:
            # The query was refused (the epic is there but would not answer):
            # the store half above is real, and its absence is said rather
            # than left to be inferred from what did not print.
            lines.append(
                "  ending: unavailable — the epic is running but would not "
                "answer the epic_status query"
            )
        else:
            lines.append(
                f"  ending: unavailable — the epic_status query holds no node "
                f"{id_of_node} and the store holds no verdict"
            )

    return "\n".join(lines)


def _is_failure_to_explain(
    status: Mapping[str, Any] | None,
    results: Sequence[VerificationResult],
) -> bool:
    """Whether a node's chain has anything to explain (US3-S3).

    A node the query holds is read by its own state: terminal-and-failed or a
    landing that ended anywhere but MERGED is a failure; MERGED or still
    running is not. A node the query knows nothing about falls back to its
    verification record — a FAIL verdict is a failure wherever the execution
    went afterwards.
    """
    if status is not None:
        state = status.get("state")
        if state in ("KILLED", "FAILED"):
            return True
        landing_state = status.get("landing_state")
        if landing_state is not None and landing_state != "MERGED":
            return True
        if state == "MERGED":
            return False
        # Still running: nothing terminal yet, so nothing to explain — the
        # operator asked why a node died, and this one has not.
        return False
    return any(result.verdict.value == "FAIL" for result in results)


def _print_external_completion_count(result: ExternalCompletionCount, as_json: bool) -> None:
    """Render the count, total and per-spec, with the target stated."""
    if as_json:
        print(
            json.dumps(
                {
                    "total": result.total,
                    "by_spec": result.by_spec,
                    "measured": result.measured,
                    "target": result.target,
                },
                indent=2,
            )
        )
        return

    lines = [f"external completions: {result.total} (target: {result.target})"]
    if result.by_spec:
        width = max(len(spec) for spec in result.by_spec)
        for spec, count in sorted(result.by_spec.items()):
            lines.append(f"  {spec.ljust(width)}  {count}")
    else:
        lines.append("  no spec has used the external-completion hatch")
    print("\n".join(lines))


def _verification_store_path() -> Path:
    return resolve_env_path(
        ERGANE_VERIFICATION_DB_PATH_ENV,
        FACTORY_VERIFICATION_DB_PATH_ENV,
        DEFAULT_VERIFICATION_DB_PATH,
    )


async def _send_signal_with_args(
    epic_id: str, signal_name: str, signal_args: list[Any]
) -> int:
    client = await _connect()
    handle = client.get_workflow_handle(workflow_id(epic_id))
    try:
        await handle.signal(signal_name, args=signal_args)
    except RPCError as error:
        if error.status is RPCStatusCode.NOT_FOUND:
            raise OperatorError(
                f"no epic '{epic_id}' is running here "
                f"({looked_for(epic_id)})"
            ) from error
        from factory.cli.errors import EXIT_TRANSPORT

        raise OperatorError(
            f"cannot signal epic '{epic_id}': {error}", EXIT_TRANSPORT
        ) from error
    print(f"sent {signal_name} to {workflow_id(epic_id)}")
    return EXIT_OK


async def _send_signal(epic_id: str, signal_name: str) -> int:
    client = await _connect()
    handle = client.get_workflow_handle(workflow_id(epic_id))
    try:
        await handle.signal(signal_name)
    except RPCError as error:
        if error.status is RPCStatusCode.NOT_FOUND:
            raise OperatorError(
                f"no epic '{epic_id}' is running here "
                f"({looked_for(epic_id)})"
            ) from error
        from factory.cli.errors import EXIT_TRANSPORT

        raise OperatorError(
            f"cannot signal epic '{epic_id}': {error}", EXIT_TRANSPORT
        ) from error
    print(f"sent {signal_name} to {workflow_id(epic_id)}")
    return EXIT_OK


def _verification_store_path() -> Path:
    return resolve_env_path(
        ERGANE_VERIFICATION_DB_PATH_ENV,
        FACTORY_VERIFICATION_DB_PATH_ENV,
        DEFAULT_VERIFICATION_DB_PATH,
    )


def answer_command(args: argparse.Namespace) -> int:
    """List pending questions or send `question_answered`."""
    return asyncio.run(_answer(args.epic_id, args.question_id, args.text))


async def _answer(epic_id: str, question_id: str | None, text: str | None) -> int:
    store_path = _verification_store_path()
    conn = verify_connect(store_path)
    try:
        if question_id is None:
            questions = [q for q in pending_questions(conn) if q.epic_id == epic_id]
            if not questions:
                print(f"no pending questions for epic '{epic_id}'")
                return EXIT_OK
            for q in questions:
                print(
                    f"{q.question_id}  {q.node_id}  expires {q.expires_at}\n"
                    f"  {q.question_text}"
                )
            return EXIT_OK

        record = get_question(conn, question_id)
        if record is None:
            raise OperatorError(
                f"question '{question_id}' is not on record; nothing was signalled"
            )
        # Compared through the seam, not against the raw argument: `answer`
        # checks ownership before it dials, so a pasted workflow id would be
        # refused here and never reach the normalization at all.  This is the
        # same function every verb resolves with, not a second one.
        if workflow_id(record.epic_id) != workflow_id(epic_id):
            raise OperatorError(
                f"question '{question_id}' belongs to epic '{record.epic_id}', "
                f"not '{epic_id}'; nothing was signalled"
            )
        if record.resolution is not None:
            if record.resolution == EXPIRED:
                raise OperatorError(
                    f"question '{question_id}' has expired; nothing was signalled"
                )
            raise OperatorError(
                f"question '{question_id}' is already "
                f"{record.resolution.lower()}; nothing was signalled"
            )
        if text is None or text == "":
            raise OperatorError(
                f"question '{question_id}' needs an answer text; "
                "nothing was signalled"
            )

        client = await _connect()
        # 041-US3: the row's `workflow_id` names whatever is waiting — a
        # `QuestionWorkflow` since the park migrated. Read rather than derived,
        # exactly as `CallbackBridge` has always done, so the verb cannot drift
        # from the button.
        handle = client.get_workflow_handle(record.workflow_id)
        try:
            await handle.signal(QUESTION_SIGNAL_NAME, args=[question_id, text])
        except RPCError as error:
            if error.status is RPCStatusCode.NOT_FOUND:
                raise OperatorError(
                    f"no epic '{epic_id}' is running here "
                    f"({looked_for(epic_id)})"
                ) from error
            from factory.cli.errors import EXIT_TRANSPORT

            raise OperatorError(
                f"cannot signal epic '{epic_id}': {error}", EXIT_TRANSPORT
            ) from error
        print(
            f"sent question_answered to {workflow_id(epic_id)} "
            f"for question {question_id}"
        )
        return EXIT_OK
    finally:
        conn.close()


def resolve_command(args: argparse.Namespace) -> int:
    """List pending escalations or send `escalation_resolved`."""
    return asyncio.run(_resolve(args.epic_id, args.escalation_id, args.choice))


def names_a_compiled_artifact(argument: str) -> bool:
    """Does this argument name a file on disk rather than an epic?

    Structural, and deliberately not a filesystem probe.  A spec directory's
    name is a single path component and no epic id ends in `.json`, so an
    argument carrying a separator or that suffix is a path the operator typed
    on purpose.  Deciding by "does this file exist?" instead is the one rule
    that could silently reinterpret a mistyped path as an epic id (068 trap 8):
    the path would miss, fall through to the epic-id branch, and be refused
    against a specs root the operator never mentioned, with the typo invisible.

    The two forms are therefore disjoint by construction, not by precedence.
    """
    return Path(argument).name != argument or argument.endswith(".json")


def resolve_reset_graph(argument: str, specs_root: str) -> WorkGraph:
    """The compiled graph `reset` acts on, from an epic id or an artifact path.

    An epic id resolves `<specs_root>/<epic_id>/workgraph.json` off disk, and
    nothing else: there is no Temporal read that could supply the graph
    instead.  `describe()` exposes memo and static details only — no input —
    `ergane build start` sets no memo, and `fetch_history()` is gone past
    retention, which is precisely the state `reset` exists for.  `_reset_epic`
    needs `graph.nodes` and `graph.target_repo`, not only the id, so the
    artifact is the only source there has ever been.

    An artifact path is still accepted, unchanged in meaning (US3-S4).
    """
    if names_a_compiled_artifact(argument):
        location: Path = Path(argument)
    else:
        location = (Path(specs_root) / argument / ARTIFACT_NAME).resolve()
        if not location.is_file():
            raise OperatorError(
                f"no epic '{argument}' is compiled here "
                f"(looked for {location}); compile it with "
                f"`ergane spec derive`, pass --specs-root, or give the path to "
                f"a compiled {ARTIFACT_NAME} instead of an epic id"
            )

    try:
        return load_workgraph(location)
    except WorkGraphError as error:
        raise OperatorError(str(error)) from error


def reset_command(args: argparse.Namespace) -> int:
    """Archive the survivors of a terminated epic so it can be relaunched safely."""
    return asyncio.run(_reset_epic(resolve_reset_graph(args.epic_id, args.specs_root)))


#: States in which something is actually being done — a key issued, an agent
#: writing, gates running, a PR riding the queue — and so work `reset` must not
#: archive out from under. `WAITING_OPERATOR`, `PENDING` and the terminals are
#: absent on purpose: a parked question is a wait, and an undispatched node has
#: nothing in flight to interrupt.
_NODE_STATES_AT_WORK = frozenset(
    {
        NodeState.KEY_ISSUED,
        NodeState.RUNNING,
        NodeState.VERIFYING,
        NodeState.PASSED,
        NodeState.PR_OPEN,
        NodeState.ENQUEUED,
    }
)


def nodes_at_work(document: Mapping[str, Any]) -> tuple[str, ...]:
    """Which of an epic's nodes are in flight, as opposed to waiting on a human.

    A node parked on a page reads `VERIFYING`, exactly as one whose gates run
    does, so `state` alone cannot tell work from waiting and `awaiting_operator`
    is what does — the distinction 068 trap 7 insists on. Read off the query's
    raw document, so an epic whose history predates the field still answers: no
    field counts as working, the safe direction, because the other one archives
    a worktree an agent is writing to.
    """
    nodes = document.get("nodes") or {}
    return tuple(
        node_id
        for node_id, node in sorted(nodes.items())
        if node.get("state") in _NODE_STATES_AT_WORK
        and not node.get("awaiting_operator")
    )


def nodes_awaiting_operator(document: Mapping[str, Any]) -> tuple[str, ...]:
    """Which of an epic's nodes are parked on a human — a page, or a question."""
    nodes = document.get("nodes") or {}
    return tuple(
        node_id
        for node_id, node in sorted(nodes.items())
        if node.get("awaiting_operator")
    )


def reset_refusal(epic_id: str, document: Mapping[str, Any]) -> str | None:
    """Why a *running* epic may not be reset, or `None` when it may (FR-007).

    `reset` used to refuse every epic whose workflow was RUNNING, and a stalled
    escalation is precisely what keeps one running. What replaces that is
    narrower than "no node is working": a running epic is reset **only** when
    somebody is being waited on *and* nothing is in flight behind them.

    Without the first half, an epic that started and has not yet dispatched (all
    `PENDING`, or nothing reported) would pass, and reset would archive the
    worktrees it is about to prepare — `PENDING` is not itself work, so the
    guard against that race is the *presence of a waiter*. Without the second,
    US2-S4's control is gone: an epic paging about one node while another builds
    would be reset out from under the live one. The fall-through message is the
    one this verb has always printed, so a refusal reads the same as before.
    """
    refusal = (
        f"epic '{epic_id}' is running (workflow id {workflow_id(epic_id)}); "
        "refusing to reset "
    )
    working = nodes_at_work(document)
    if working:
        return refusal + (
            f"while {', '.join(working)} "
            f"{'is' if len(working) == 1 else 'are'} still working"
        )
    if not nodes_awaiting_operator(document):
        return refusal + "while the workflow is active"
    return None


@dataclass(frozen=True)
class NoForge:
    """Why a reset resolved no forge, and whether that leaves work undone.

    The distinction is the whole of it, and getting it wrong costs the operator
    real time either way: a clone with no remote never pushed a node branch, so
    there is *nothing to do* and saying "not done" would send them looking for a
    pull request that was never opened. A forge that could not be built is work
    genuinely *undone*, and saying "nothing to do" would hide it (FR-011).
    """

    reason: str
    undone: bool


def _reset_forge(target_repo: Path | str) -> tuple[Any | None, NoForge | None]:
    """The forge whose state this reset must clear, or why there is none.

    Never raises, and never spawns anything to find out (069-US3, FR-011): a
    clone with no `origin` never pushed a node branch, so there is no forge state
    to clear and building a forge would be a subprocess asked a question already
    answered — which is also what keeps every offline reset test in this
    repository offline. A forge that cannot be *resolved* — an unknown name in
    the manifest, an unreadable manifest — is reported the same way a forge that
    cannot be reached is, because the operator's position is identical: the local
    reset is done and the forge work is theirs to finish.
    """
    repo = Path(target_repo)
    if not repo.is_dir():
        return None, NoForge(
            f"the target repository is not on this machine: {repo}", undone=True
        )
    if not has_remote(repo, "origin"):
        return None, NoForge(
            f"{repo} has no 'origin' remote, so no node branch was ever pushed",
            undone=False,
        )
    try:
        return resolve_forge_for_repo(repo_path=str(repo)), None
    except (UnknownForgeError, FactoryConfigError, ForgeError, OSError) as error:
        return None, NoForge(
            f"no forge could be resolved for {repo}: {error}", undone=True
        )


def _forge_reset_lines(
    forge: Any | None,
    absent: NoForge | None,
    epic_id: str,
    node_id: str,
) -> list[str]:
    """One node's forge cleanup, as the operator reads it.

    Every line is prefixed `forge:`, and an undone one says `not done` and names
    the head, so FR-011's report is a remedy rather than a complaint: what is
    printed is enough to finish the job by hand.
    """
    head = branch_name(epic_id, node_id)
    if forge is None:
        stated = absent or NoForge("no forge was resolved", undone=True)
        if not stated.undone:
            return [f"forge: nothing to do — {stated.reason}"]
        return [f"forge: not done for {head} — {stated.reason}"]

    result = reset_node_on_forge(
        forge, head=head, note=reset_note(epic_id, node_id)
    )
    lines = [f"forge: {action}" for action in result.done]
    lines += [f"forge: not done — {undone}" for undone in result.not_done]
    return lines


async def _reset_epic(graph: WorkGraph, *, forge: Any | None = None) -> int:
    """Reset every node the graph names, after one Temporal read proves it is safe.

    Two halves, in this order and never the other one (069-US3). The local half
    archives the survivors; the forge half closes the node's open pull request
    and retires the head it pushed, which is what a rebuilt node collides with.
    Local first because its archive is the part that must always happen: the
    rename needs nothing off this machine, and it is what the operator is
    recovering with.

    Since 100-US1 the local half also retires that head, and the reason is that
    the forge half is the one that can be *absent*. `_reset_forge` answers "no
    forge" for a manifest it cannot read, a forge name it does not know and a
    forge that will not build; each of those reports the head as `not done` and
    leaves it on the remote, which is the mine 100 is about — a rebuilt node
    refused non-fast-forward after it has already passed verification. The local
    half reaches that ref over plain git on `origin`, the same channel the push
    used, so it is available wherever the head got there in the first place, and
    it degrades to a report when that channel is not (100 FR-003).

    The forge half is not thereby redundant: it closes the proposal, which no
    amount of git can do, and `retire_head` reports "no head on the forge" for
    one the local half has already removed.

    `forge` is the seam tests put a repository behind. Left unset — every
    operator invocation — the forge is the one the target repository declares,
    resolved once for the whole graph rather than per node.
    """
    client = await _connect()
    handle = client.get_workflow_handle(workflow_id(graph.epic_id))
    try:
        described = await handle.describe()
    except RPCError as error:
        if error.status is RPCStatusCode.NOT_FOUND:
            # Absence of workflow history is not an error for a cleanup verb.
            described = None
        else:
            raise OperatorError(
                f"cannot verify epic '{graph.epic_id}': {error}", EXIT_TRANSPORT
            ) from error

    waiting: tuple[str, ...] = ()
    if described is not None and described.status is not None:
        if described.status.name == "RUNNING":
            try:
                document = await handle.query("epic_status")
            except QUERY_REFUSED:
                document = None
            # A query refused, or answered unreadably, is never read as
            # "nothing is running": the alternative is archiving the worktree of
            # an epic that could not be asked what it was doing.
            if not isinstance(document, Mapping):
                raise OperatorError(
                    f"epic '{graph.epic_id}' is running (workflow id "
                    f"{workflow_id(graph.epic_id)}) and would not say what it "
                    "is doing; refusing to reset while the workflow is active"
                )
            refusal = reset_refusal(graph.epic_id, document)
            if refusal is not None:
                raise OperatorError(refusal)
            waiting = nodes_awaiting_operator(document)

    factory_root = resolve_env_path(
        ERGANE_ROOT_ENV, FACTORY_ROOT_ENV, DEFAULT_FACTORY_ROOT_PATH
    )

    resolved, absent = (
        (forge, None) if forge is not None else _reset_forge(graph.target_repo)
    )

    for node in graph.nodes:
        actions = reset_worktree(
            graph.target_repo,
            graph.epic_id,
            node.id,
            factory_root=factory_root,
        )
        print(f"{node.id}: {', '.join(actions)}")
        for line in _forge_reset_lines(
            resolved, absent, graph.epic_id, node.id
        ):
            print(f"  {line}")

    if waiting:
        # Archived, and the epic is still alive holding an unanswered page. Name
        # the verb that ends it rather than ending it here: FR-008 makes that
        # the operator's own choice, and a reset that quietly killed would press
        # the button for them.
        print(
            f"note: epic '{graph.epic_id}' is still running, waiting on an "
            f"operator for {', '.join(waiting)}; "
            f"end it with `ergane build kill {graph.epic_id}`",
            file=sys.stderr,
        )

    return EXIT_OK



def salvage_command(args: argparse.Namespace) -> int:
    """Report what every node of a compiled graph left behind. Reads, never writes.

    Shaped like `reset_command` — a compiled graph in, one block per node out —
    and deliberately unlike it in the one respect that matters: no Temporal
    client. `reset` reads the workflow because it is about to *change* the
    repository and must not do that under a running epic. This verb changes
    nothing, and the moment it is most needed is the moment a terminated epic's
    workflow has already aged out of Temporal (047 FR-010, SC-005). A read that
    required the server would be unavailable exactly when the question is asked.

    Every answer is exit 0. A node that never dispatched, a target with no
    remote and a remote that cannot be reached are all normal answers to "is my
    work anywhere?", not errors — the only refusal is a target repository that
    is not on this machine, because reporting a mistyped path as a graph's
    worth of nodes that left nothing is the one wrong answer this verb could
    give that an operator would believe.
    """
    try:
        graph = load_workgraph(args.graph)
    except WorkGraphError as error:
        raise OperatorError(str(error)) from error

    repo = Path(graph.target_repo)
    if not repo.is_dir():
        raise OperatorError(
            f"the graph's target repository is not on this machine: {repo} "
            f"(the graph is {args.graph})"
        )

    for node in graph.nodes:
        print(_salvage_block(read_node_salvage(repo, graph.epic_id, node.id)))
    return EXIT_OK


def _salvage_block(report: NodeSalvage) -> str:
    """One node's answer, as the operator reads it.

    The per-attempt refs are printed under their full names rather than as an
    attempt number, which is the second thing this verb is for: the convention
    `refs/salvage/<epic>/<node>/attempt-<n>-<sha12>` was documented only in
    `worktree.py`'s module docstring, and an operator who has seen the ref
    printed once can go back to plain git without reading the source.
    """
    lines = [f"{report.node_id}  {report.branch}"]
    if report.tip:
        lines.append(f"  tip          {report.tip}  {report.tip_subject}")
    else:
        lines.append("  tip          none: this node's branch is not in this clone")
    lines.append(
        f"  off-machine  {report.off_machine.value} ({report.off_machine_detail})"
    )
    if report.attempts:
        lines += [
            f"  {attempt.ref}  {attempt.sha}  {attempt.subject}"
            for attempt in report.attempts
        ]
    else:
        lines.append("  salvage refs none")
    return "\n".join(lines)


async def _resolve(
    epic_id: str, escalation_id: str | None, choice: str | None
) -> int:
    store_path = _verification_store_path()
    conn = verify_connect(store_path)
    try:
        if escalation_id is None:
            escalations = [
                e for e in pending_escalations(conn) if e.epic_id == epic_id
            ]
            if not escalations:
                print(f"no pending escalations for epic '{epic_id}'")
                return EXIT_OK
            for e in escalations:
                choices = ", ".join(sorted(c.value for c in e.choices))
                print(
                    f"{e.escalation_id}  {e.node_id}  expires {e.expires_at}\n"
                    f"  choices: {choices}"
                )
            return EXIT_OK

        record = get_escalation(conn, escalation_id)
        if record is None:
            raise OperatorError(
                f"escalation '{escalation_id}' is not on record; "
                "nothing was signalled"
            )
        # Through the seam, for the reason `_answer` records above.
        if workflow_id(record.epic_id) != workflow_id(epic_id):
            raise OperatorError(
                f"escalation '{escalation_id}' belongs to epic "
                f"'{record.epic_id}', not '{epic_id}'; nothing was signalled"
            )
        if record.resolution is not None:
            if record.resolution == EXPIRED:
                raise OperatorError(
                    f"escalation '{escalation_id}' has expired; "
                    "nothing was signalled"
                )
            raise OperatorError(
                f"escalation '{escalation_id}' is already "
                f"{str(record.resolution).lower()}; nothing was signalled"
            )

        allowed = {c.value for c in record.choices}
        if choice is None:
            choices_text = ", ".join(sorted(allowed))
            print(
                f"escalation '{escalation_id}' offers: {choices_text}\n"
                "no choice given; nothing was signalled"
            )
            return EXIT_USER
        if choice not in allowed:
            choices_text = ", ".join(sorted(allowed))
            raise OperatorError(
                f"choice '{choice}' is not one of {choices_text}; "
                "nothing was signalled"
            )

        client = await _connect()
        # Through the row's routing column, for the reason `_answer` records.
        handle = client.get_workflow_handle(record.workflow_id)
        try:
            await handle.signal(SIGNAL_NAME, args=[escalation_id, choice])
        except RPCError as error:
            if error.status is RPCStatusCode.NOT_FOUND:
                raise OperatorError(
                    f"no epic '{epic_id}' is running here "
                    f"({looked_for(epic_id)})"
                ) from error
            from factory.cli.errors import EXIT_TRANSPORT

            raise OperatorError(
                f"cannot signal epic '{epic_id}': {error}", EXIT_TRANSPORT
            ) from error
        print(
            f"sent escalation_resolved to {workflow_id(epic_id)} "
            f"for escalation {escalation_id}: {choice}"
        )
        return EXIT_OK
    finally:
        conn.close()


# --- parser -------------------------------------------------------------------


def add_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "build",
        help="start, watch and signal an epic",
        description="Start an epic, read its state, and send workflow signals.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    start = commands.add_parser(
        "start", help="start the epic a compiled graph declares"
    )
    start.add_argument("graph", help=f"path to a compiled {ARTIFACT_NAME}")
    start.add_argument(
        "--max-concurrent-nodes",
        type=_positive_int,
        default=1,
        help=(
            "how many ready nodes the scheduler may have in flight at once "
            "(default: 1)"
        ),
    )
    add_promotion_persona_flag(start)
    # 081-US1 (FR-001): the merge queue's knobs, on the verb that starts the
    # epic they govern. Declared through the shared module so `ergane roadmap
    # start` offers the same five flags with the same spellings and refusals.
    add_landing_dial_flags(start)
    start.set_defaults(run=start_command)

    ship = commands.add_parser(
        "ship",
        help="validate, derive and start one epic with a confirmation pause",
        description=(
            "Run `spec validate` and `spec derive` for one spec, print a summary "
            "of the compiled graph, then pause for confirmation before dispatching "
            "the epic.  With --yes the pause is skipped."
        ),
    )
    ship.add_argument("spec_dir", help="the feature directory holding spec.md")
    ship.add_argument(
        "--target-repo",
        required=True,
        help="worker-host path to the repository the epic builds in",
    )
    ship.add_argument(
        "--specs-root",
        dest="specs_root",
        default=DEFAULT_SPECS_ROOT,
        help=f"where the worker finds feature specs (default: {DEFAULT_SPECS_ROOT})",
    )
    ship.add_argument(
        "-o",
        "--output",
        default=None,
        help="write the artifact here instead of <spec-dir>/workgraph.json",
    )
    ship.add_argument(
        "--delta",
        action="store_true",
        help="derive only the work that remains against the landed baseline",
    )
    ship.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="emit validate/derive output as JSON instead of human prose",
    )
    ship.add_argument(
        "--max-concurrent-nodes",
        type=_positive_int,
        default=1,
        help=(
            "how many ready nodes the scheduler may have in flight at once "
            "(default: 1)"
        ),
    )
    add_promotion_persona_flag(ship)
    add_landing_dial_flags(ship)
    ship.add_argument(
        "--yes",
        action="store_true",
        help="skip the interactive confirmation",
    )
    ship.set_defaults(run=ship_command)

    status = commands.add_parser("status", help="what one epic is doing right now")
    status.add_argument("epic_id", help="the epic id (the spec directory's name)")
    status.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="print the query result verbatim instead of the human view",
    )
    status.set_defaults(run=status_command)

    credential_status_parser = commands.add_parser(
        "credential-status",
        help="show which subscription credential the factory will use",
    )
    credential_status_parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="emit the status as JSON instead of the human view",
    )
    credential_status_parser.set_defaults(run=credential_status_command)

    for name, signal_help in (
        ("pause", "pause dispatching; the in-flight node finishes"),
        ("resume", "release the scheduler after a pause"),
        ("kill", "stop the epic, in-flight attempt included"),
    ):
        sub = commands.add_parser(name, help=signal_help)
        sub.add_argument("epic_id", help="the epic id (the spec directory's name)")
        if name == "kill":
            sub.add_argument(
                "--yes",
                action="store_true",
                help="skip the interactive confirmation",
            )
        if name == "pause":
            sub.set_defaults(run=pause_command)
        elif name == "resume":
            sub.set_defaults(run=resume_command)
        else:
            sub.set_defaults(run=kill_command)

    answer = commands.add_parser(
        "answer",
        help="list pending questions or answer one",
    )
    answer.add_argument("epic_id", help="the epic id (the spec directory's name)")
    answer.add_argument(
        "question_id",
        nargs="?",
        help="the question id to answer; omit to list pending questions",
    )
    answer.add_argument(
        "text",
        nargs="?",
        help="the answer text; required when question_id is given",
    )
    answer.set_defaults(run=answer_command)

    resolve = commands.add_parser(
        "resolve",
        help="list pending escalations or resolve one",
    )
    resolve.add_argument("epic_id", help="the epic id (the spec directory's name)")
    resolve.add_argument(
        "escalation_id",
        nargs="?",
        help="the escalation id to resolve; omit to list pending escalations",
    )
    resolve.add_argument(
        "choice",
        nargs="?",
        help="the choice to record; required when escalation_id is given",
    )
    resolve.set_defaults(run=resolve_command)

    reset = commands.add_parser(
        "reset",
        help="archive a terminated epic's survivors so it can be relaunched",
        description=(
            "Keyed by the epic id, like every other verb that acts on an epic "
            f"already started. The compiled {ARTIFACT_NAME} is resolved from "
            f"<specs-root>/<epic-id>/{ARTIFACT_NAME} rather than read off the "
            "workflow, because it cannot be read off the workflow: describe() "
            "exposes no input, start sets no memo, and history is gone past "
            "retention by the time a reset is wanted. A path to a compiled "
            f"{ARTIFACT_NAME} is still accepted and still means what it did."
        ),
    )
    reset.add_argument(
        "epic_id",
        help=(
            "the epic id (the spec directory's name); a path to a compiled "
            f"{ARTIFACT_NAME} is still accepted"
        ),
    )
    reset.add_argument(
        "--specs-root",
        dest="specs_root",
        default=DEFAULT_SPECS_ROOT,
        help=(
            "where this epic's compiled graph lives "
            f"(default: {DEFAULT_SPECS_ROOT})"
        ),
    )
    reset.set_defaults(run=reset_command)

    salvage = commands.add_parser(
        "salvage",
        help="what each of an epic's nodes left behind in the target repo",
        description=(
            "Read-only. For every node of a compiled graph, report the node's "
            "branch and tip, every per-attempt salvage ref "
            "(refs/salvage/<epic>/<node>/attempt-<n>-<sha12>), and whether the "
            "branch exists off this machine. Needs no Temporal server, which is "
            "the point: a terminated epic's workflow is usually gone by the time "
            "anyone asks."
        ),
    )
    salvage.add_argument("graph", help=f"path to a compiled {ARTIFACT_NAME}")
    salvage.set_defaults(run=salvage_command)

    attempts = commands.add_parser(
        "attempts",
        help="what each of an epic's attempts was verified on",
        description=(
            "Read-only. One line per recorded verification: the node, the "
            "attempt, the verdict, and how much of the diff the judge was "
            "actually shown — abridged with its numbers, whole, or not "
            "recorded for rows written before the factory measured it. Reads "
            "the evidence store, so it needs no Temporal server: the row "
            "outlives the workflow, and the question is usually asked after "
            "the execution has aged out."
        ),
    )
    attempts.add_argument("epic_id", help="the epic id (the spec directory's name)")
    attempts.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="print the typed verification rows as JSON",
    )
    attempts.set_defaults(run=attempts_command)

    why = commands.add_parser(
        "why",
        help="assemble the causal chain behind a node's death",
        description=(
            "Read-only. For one node — or every terminal node of the epic — "
            "print the last verdict, the failing gate with a bounded tail of "
            "its output, the judge's feedback where one exists, the queue "
            "outcomes the landing recorded, the transcript directory of the "
            "latest attempt (composed, never read), and the terminal reason. "
            "Joins the verification store with the live epic_status query; the "
            "ending is available only while the execution is."
        ),
    )
    why.add_argument("epic_id", help="the epic id (the spec directory's name)")
    why.add_argument(
        "node_id",
        nargs="?",
        help=(
            "the node to explain; omit to report every terminal node of "
            "the epic"
        ),
    )
    why.set_defaults(run=why_command)

    complete_node_externally = commands.add_parser(
        "complete-node-externally",
        help="tell the epic a node was finished by the operator",
        description=(
            "Signal that the operator has finished a stuck node by hand. "
            "The branch becomes the node's result; the provenance string is "
            "recorded in the verification store."
        ),
    )
    complete_node_externally.add_argument(
        "epic_id", help="the epic id (the spec directory's name)"
    )
    complete_node_externally.add_argument(
        "node_id", help="the user-story id the signal is for"
    )
    complete_node_externally.add_argument(
        "branch", help="the branch the operator's work is on"
    )
    complete_node_externally.add_argument(
        "--provenance",
        required=True,
        help="who completed the work and how (e.g. 'operator:manual-2026-08-17')",
    )
    complete_node_externally.set_defaults(run=complete_node_externally_command)

    external_completion_count_parser = commands.add_parser(
        "external-completion-count",
        help="how many times the operator hand-back hatch has been used",
        description=(
            "Read the durable count of accepted external completions. "
            "Reports the total, the per-spec breakdown, and states that "
            "the target is zero. A store that has never recorded a use "
            "answers 0 explicitly, not as an empty table."
        ),
    )
    external_completion_count_parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="emit the count as JSON",
    )
    external_completion_count_parser.set_defaults(
        run=external_completion_count_command
    )


NOUN = Noun(
    name="build",
    summary="start, watch and signal an epic",
    order=30,
    add_parser=add_parser,
)
