"""The `build` noun: start an epic, watch it, and send its signals.

`ergane build start|status|pause|resume|kill|answer|resolve` is the operator
surface over `EpicWorkflow`.  Almost every behaviour is a port from
`factory/workgraph/cli.py`, with two deliberate changes:

- Exit codes follow the `ergane` contract: transport/service failures are 3,
  user errors are 1.
- The signal verbs (`pause`, `resume`, `kill`, `answer`, `resolve`) give the
  five signals the workflow already declared a typed CLI instead of a hand-typed
  `temporal workflow signal` invocation.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from factory.activities.verify_activities import (
    DEFAULT_VERIFICATION_DB_PATH,
    VERIFICATION_DB_PATH_ENV,
)
from factory.cli.errors import EXIT_OK, EXIT_USER, EXIT_USAGE, OperatorError
from factory.env import (
    ERGANE_ROOT_ENV,
    ERGANE_VERIFICATION_DB_PATH_ENV,
    FACTORY_ROOT_ENV,
    FACTORY_VERIFICATION_DB_PATH_ENV,
    resolve_env_path,
)
from factory.cli.nouns import Noun, _open_preflight_client
from factory.config import ConfigError, Persona, WriteScope, load_personas
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
from factory.usage.litellm_client import LiteLLMClient
from factory.usage.models import UsageSnapshot
from factory.verify.models import (
    EscalationChoice,
    EscalationRecord,
    QuestionRecord,
    VerificationConfig,
)
from factory.verify.store import (
    EXPIRED,
    ExternalCompletionCount,
    connect as verify_connect,
    connect_readonly as verify_connect_readonly,
    external_completion_count,
    get_escalation,
    get_question,
    pending_escalations,
    pending_questions,
)
from factory.activities.agent_activities import (
    DEFAULT_FACTORY_ROOT as DEFAULT_FACTORY_ROOT_PATH,
    FACTORY_ROOT_ENV,
)
from factory.workgraph.worktree import resolve_factory_root
from factory.workgraph.models import (
    WorkGraph,
    WorkGraphError,
    WorkNode,
    validate_workgraph,
)
from factory.workgraph.preflight import (
    PreflightFinding,
    check_aliases,
    prompt_assembly_preflight,
)
from factory.workgraph.workflow import TASK_QUEUE, EpicInput, EpicWorkflow
from factory.workgraph.worktree import (
    NodeSalvage,
    read_node_salvage,
    reset as reset_worktree,
)

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
    """A registry that answers for every persona the graph names, and no more."""
    return {
        node.persona: Persona(
            name=node.persona,
            agent="",
            model=None,
            fallback=None,
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
    """Check that every prompt assembles, then what the proxy serves.

    The same two checks the roadmap's pre-dispatch activity runs, in the same
    order and from the same module (044 FR-004): an epic started by hand dies of
    an unassemblable `tasks.md` exactly the way a scheduled one does, so it is
    refused here rather than one tick after `ergane build start` printed a
    workflow id. Assembly reads `specs_root/feature` — where the graph itself
    says its authored trio lives, and where dispatch will read it.
    """
    findings = prompt_assembly_preflight(
        graph, Path(graph.specs_root) / graph.feature
    )
    findings += await check_aliases(
        graph, _preflight_registry(), _open_preflight_client()
    )
    return findings


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
    """Each running attempt's newest heartbeat snapshot, per node."""
    try:
        description = await handle.describe()
    except RPCError:
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
        if converter is None or not activity_info.HasField("heartbeat_details"):
            continue
        node_id = activity_info.activity_id
        if node_id not in nodes:
            continue
        try:
            decoded = await converter.decode(
                list(activity_info.heartbeat_details.payloads),
                [UsageSnapshot | None],
            )
        except Exception:
            continue
        snapshot = decoded[0]
        if snapshot is None:
            continue
        live[node_id] = {
            "spend_usd": snapshot.spend_usd,
            "captured_at": snapshot.captured_at,
        }
    return live


def render_status(
    epic_id: str,
    document: Mapping[str, Any],
    execution_status: str,
    *,
    live_spend: Mapping[str, Mapping[str, Any]] | None = None,
) -> str:
    """The human view: the epic's line, then one line per node, in query order."""
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
    for node_id, node in nodes.items():
        figure = live.get(node_id)
        spend_token = (
            f"  spend ${figure['spend_usd']:.2f}" if figure is not None else ""
        )
        provenance = node.get("provenance")
        external_token = (
            f"  external completion: {provenance}" if provenance else ""
        )
        lines.append(
            f"{node_id.ljust(id_width)}  {str(node['state']).ljust(state_width)}  "
            f"attempt {node['attempt']}  {node['branch']}{spend_token}{external_token}"
        )
    return "\n".join(lines)


# --- commands -----------------------------------------------------------------


def start_command(args: argparse.Namespace) -> int:
    """Start one epic from a compiled graph.

    Everything that can be checked without a server is checked without one:
    file parse, structural validation, and proxy-url presence.  Only then is a
    client built.
    """
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
        config, verify_order = load_loop_config(graph.target_repo)
    except FactoryConfigError as exc:
        raise OperatorError(
            f"preflight: manifest: [{exc.rule}] {exc.problem}"
        ) from exc

    return asyncio.run(
        _start_epic(
            graph,
            proxy_url,
            args.max_concurrent_nodes,
            config=config,
            verify_order=verify_order,
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


def status_command(args: argparse.Namespace) -> int:
    """Read one epic's live state."""
    return asyncio.run(_query_status(args.epic_id, as_json=args.as_json))


async def _query_status(epic_id: str, *, as_json: bool) -> int:
    client = await _connect()
    handle = client.get_workflow_handle(workflow_id(epic_id))
    try:
        document = await handle.query("epic_status")
    except RPCError as error:
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
    except RPCError as error:
        from factory.cli.errors import EXIT_TRANSPORT

        raise OperatorError(
            f"cannot read epic '{epic_id}': {error}", EXIT_TRANSPORT
        ) from error

    live_spend = await _live_spend(client, handle, document)
    if as_json:
        rendered: Any = dict(document)
        rendered["execution_status"] = execution_status
        if live_spend:
            rendered["live_spend"] = live_spend
        print(json.dumps(rendered, indent=2))
    else:
        print(
            render_status(
                epic_id, document, execution_status, live_spend=live_spend
            )
        )
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


def reset_command(args: argparse.Namespace) -> int:
    """Archive the survivors of a terminated epic so it can be relaunched safely."""
    try:
        graph = load_workgraph(args.graph)
    except WorkGraphError as error:
        raise OperatorError(str(error)) from error

    return asyncio.run(_reset_epic(graph))


async def _reset_epic(graph: WorkGraph) -> int:
    """Reset every node the graph names, after one Temporal read proves it is safe."""
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

    if described is not None and described.status is not None:
        if described.status.name == "RUNNING":
            raise OperatorError(
                f"epic '{graph.epic_id}' is running "
                f"(workflow id {workflow_id(graph.epic_id)}); "
                "refusing to reset while the workflow is active"
            )

    factory_root = resolve_env_path(
        ERGANE_ROOT_ENV, FACTORY_ROOT_ENV, DEFAULT_FACTORY_ROOT_PATH
    )

    for node in graph.nodes:
        actions = reset_worktree(
            graph.target_repo,
            graph.epic_id,
            node.id,
            factory_root=factory_root,
        )
        print(f"{node.id}: {', '.join(actions)}")

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
    start.set_defaults(run=start_command)

    status = commands.add_parser("status", help="what one epic is doing right now")
    status.add_argument("epic_id", help="the epic id (the spec directory's name)")
    status.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="print the query result verbatim instead of the human view",
    )
    status.set_defaults(run=status_command)

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
    )
    reset.add_argument("graph", help=f"path to a compiled {ARTIFACT_NAME}")
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
