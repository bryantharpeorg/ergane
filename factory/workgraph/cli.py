"""The operator's steering wheel: compile a spec, start an epic, read its state.

`factory-epic` is the entire human surface of the interpreter (FR-009, R12).
Three verbs, deliberately — Temporal's Web UI already shows history, per-activity
timing and stack traces far better than a terminal could, so everything richer
than "compile it / run it / what is it doing" is out of scope by contract
(contracts/cli.md), and the signals an operator sends are sendable with
`temporal workflow signal` and from the escalation buttons.

The three verbs split cleanly in two, and the split is the design:

- **`derive` is offline and total.** It reads one spec, compiles it, and writes
  `workgraph.json` next to it — no client, no server, no environment. An author
  can compile a spec on a laptop with no factory anywhere near it. Its whole
  discipline is that a spec which does not compile writes *nothing* and prints
  *every* rejection: an artifact half-built from a broken spec is an epic that
  starts, dispatches the stories that parsed, and silently never builds the one
  that did not, and an author who is handed one error per invocation fixes typos
  one round trip at a time.

- **`start` and `status` talk to Temporal**, through the notify bridge's exact
  environment contract (`TEMPORAL_ADDRESS`/`TEMPORAL_NAMESPACE`) so the factory
  has one deployment story rather than one per process. The workflow id is
  `epic-<epic_id>`, which is what makes an epic findable without anyone writing
  down a run id — by `status`, by the escalation bridge's `workflow_id` round
  trip, by an operator searching the Web UI — and what makes a double start
  collide by construction instead of running two epics over one `.factory/`.

Two boundaries are worth stating out loud, because both are places this module
could plausibly have done more and deliberately does not:

**`start` re-validates structurally, and resolves no personas.** `workgraph.json`
is a compiled artifact, but between `derive` writing it and `start` reading it
there is a text editor, so the structural rules run again here and a graph that
fails them never becomes a workflow that has to be killed. What does *not* run
here is persona and timeout resolution: `personas.yaml` belongs to the worker,
whose `resolve_graph` reads it once per epic and validates against that snapshot
(R8). A CLI that resolved personas from its own working directory could accept a
graph the worker then rejects, or reject one the worker would have run — so it
supplies a registry that answers for every persona the graph names, leaving the
registry rules vacuous and every structural rule in force.

**`--json` is a dump, never a re-assembly.** The query's payload is decoded
untyped and printed as it arrived, so `EpicStatus` is stated in exactly one place
(the workflow) and a consumer of `--json` cannot be broken by this renderer. The
human view is the only thing here that formats, and it formats nothing it did not
read from that same document.

Exit codes are the scripting contract: `0` success, `1` a spec or a graph or an
epic id the operator has to fix, `2` a Temporal that is not answering — a
distinction worth having, because the first means edit something and the second
means go look at the server, whose address the message names.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from factory.activities.merge_activities import onboard_target_repo
from factory.config import ConfigError, Persona, WriteScope, load_personas
from factory.mergequeue.gh import GhClient
from factory.notify.service import (
    DEFAULT_TEMPORAL_ADDRESS,
    DEFAULT_TEMPORAL_NAMESPACE,
    TEMPORAL_ADDRESS_ENV,
    TEMPORAL_NAMESPACE_ENV,
)
from factory.usage.litellm_client import PROXY_URL_ENV, LiteLLMClient
from factory.usage.models import UsageSnapshot
from factory.workgraph.derive import DerivationError, derive_workgraph
from factory.workgraph.models import (
    WorkGraph,
    WorkGraphError,
    WorkNode,
    validate_workgraph,
)
from factory.workgraph.workflow import TASK_QUEUE, EpicInput, EpicWorkflow

#: The spec file every epic is compiled from, and the artifact it compiles to.
#: Both are conventions rather than flags because the pair is what makes
#: `derive <spec-dir>` unambiguous: the epic owns its compiled graph, and it
#: lives with the spec rather than in whatever directory the operator stood in.
SPEC_NAME = "spec.md"
ARTIFACT_NAME = "workgraph.json"

#: Where the worker looks for feature specs unless the graph says otherwise.
DEFAULT_SPECS_ROOT = "specs"

EXIT_OK = 0
EXIT_USER = 1
EXIT_TRANSPORT = 2

#: The registry values `validate_workgraph` never reads (see `_persona_registry`).
#: Only `timeout_s` is consulted, and only to prove a bound is resolvable — which
#: on the worker it will be, from the real `personas.yaml`.
_STRUCTURAL_TIMEOUT_S = 1

#: The seam US3's `onboard` command builds its `GhClient` through — production
#: builds a real client against the clone the operator points at; tests replace
#: this with one wired to a `FakeGh`, the same discipline as the activity seam.
_onboard_client_factory = lambda *, repo_path: GhClient(repo=repo_path)


class _OperatorError(Exception):
    """Something an operator can act on, and the status that says which kind.

    Carrying the exit code on the exception keeps every message in one printer:
    a transport failure and a broken spec take the same path out of a command and
    differ only in the number, so no command has to remember to print before it
    returns.
    """

    def __init__(self, message: str, code: int = EXIT_USER) -> None:
        super().__init__(message)
        self.code = code


from factory.workgraph.preflight import (
    PreflightFinding,
    check_aliases,
)


def _preflight_registry() -> dict[str, Persona]:
    """The CLI's own view of the registry, read from its `personas.yaml`.

    Deliberately the CLI's file, not a copy the worker must match: R8 lets the
    CLI and the worker resolve personas from different hosts, and preflight can
    only validate the aliases it can see. That is why every finding is worded
    about "this registry" rather than about what the worker will resolve — the
    honesty constraint (US2 Edge Cases) is that preflight states what it checked
    and never claims the worker's resolution was validated.
    """
    return load_personas()


def _open_preflight_client() -> LiteLLMClient:
    """The preflight's one route to the proxy, credentials from the environment.

    A seam, not a factory: tests replace it to inject a fake transport the way
    `usage_activities.open_client` is replaced, so the CLI's preflight is tested
    against the same fake proxy the activities are.
    """
    return LiteLLMClient.from_env()


async def _run_preflight(graph: WorkGraph) -> list[PreflightFinding]:
    """Check what the proxy serves before anything dispatches (US2).

    The pure checks live in `factory/workgraph/preflight.py` so the roadmap
    workflow (US2) runs the same preflight as an activity before starting each
    dispatchable spec's child epic — the two surfaces share one finding
    vocabulary and cannot drift. The CLI owns its own client and registry (it
    reads `personas.yaml` from its host and dials the proxy from the
    environment); the preflight module owns the alias math and the wording.

    Returns `[]` when every check passes.
    """
    return await check_aliases(graph, _preflight_registry(), _open_preflight_client())


async def _preflight_exit_code(findings: list[PreflightFinding]) -> int:
    """Map the preflight findings to the scripting contract.

    `EXIT_TRANSPORT` when the proxy would not answer a preflight read — the
    "go look at the server" case (FR-005). `EXIT_USER` when the proxy answered
    and something the operator can fix is wrong — unserved aliases, or a
    first-attempt alias collision. `EXIT_OK` when nothing failed.
    """
    if not findings:
        return EXIT_OK
    if any(finding.transport for finding in findings):
        return EXIT_TRANSPORT
    return EXIT_USER


def main(argv: Sequence[str] | None = None) -> int:
    """Run one invocation. Returns the process status; prints errors to stderr.

    Nothing but the requested output ever reaches stdout, so a caller that pipes
    the printed artifact path or the `--json` document into another command gets
    an empty string on failure rather than a sentence to parse around.
    """
    args = _parse_args(argv)
    try:
        return int(args.run(args))
    except _OperatorError as error:
        print(f"factory-epic: {error}", file=sys.stderr)
        return error.code


def workflow_id(epic_id: str) -> str:
    """The one id convention (R12): predictable from the spec directory's name."""
    return f"epic-{epic_id}"


def _positive_int(value: str) -> int:
    """An argparse type: a positive integer, or a usage error (FR-002).

    `0`, negatives and non-integers are rejected rather than coerced — a cap the
    operator did not type is a cap the operator did not choose, and a cap of 0
    would mean "dispatch nothing". `argparse` turns the raised `ArgumentTypeError`
    into a usage error on stderr with exit status 1.
    """
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


# --- derive: text in, artifact out, nothing on failure (US3-S4, SC-006) -------


def derive_command(args: argparse.Namespace) -> int:
    """Compile one spec into `workgraph.json`, or name every reason it does not.

    The identity fields are the CLI's contribution: the deriver is pure and is
    handed text, so it cannot know which directory the spec came from, and the
    directory name is the epic id — which is what makes `epic-<epic_id>`
    predictable from the spec an operator is looking at.
    """
    spec_dir = Path(args.spec_dir)
    spec_path = spec_dir / SPEC_NAME
    try:
        spec_text = spec_path.read_text(encoding="utf-8")
    except OSError as error:
        raise _OperatorError(f"cannot read {spec_path}: {error}") from error

    epic_id = spec_dir.resolve().name
    try:
        graph = derive_workgraph(
            spec_text,
            epic_id=epic_id,
            feature=epic_id,
            specs_root=args.specs_root,
            target_repo=args.target_repo,
        )
    except DerivationError as error:
        # The whole list, at the point the author can act on all of it at once.
        raise _OperatorError(f"{spec_path}: {error}") from error

    destination = Path(args.output) if args.output else spec_dir / ARTIFACT_NAME
    try:
        destination.write_text(
            json.dumps(asdict(graph), indent=2) + "\n", encoding="utf-8"
        )
    except OSError as error:
        raise _OperatorError(f"cannot write {destination}: {error}") from error

    print(destination)
    return EXIT_OK


# --- onboard: validate a target repo before anything dispatches (US3, FR-010) --


def onboard_command(args: argparse.Namespace) -> int:
    """Validate a target repo against the factory's assumptions (FR-010, SC-005).

    The operator's preflight surface for US3: `factory-epic onboard
    <target-clone-path>` reads the repo's facts (visibility, merge-queue rule,
    required checks) and its committed `factory.yaml`, and prints every finding —
    pass and fail — so an operator can see the repo was checked, not just whether
    it passed. `--json` emits the whole `TargetRepoProfile` and nothing but, so a
    script can read the verdict without parsing prose.

    Exit codes are the CLI's contract: `0` all checks pass, `1` any check fails
    (the repo is rejected for dispatch) or the path is unusable. The command is
    offline — no Temporal, no proxy — because onboarding is a property of a repo,
    not of a running epic; it blocks dispatch at epic start precisely because the
    operator can run it first.
    """
    from factory.activities.merge_activities import onboard_target_repo

    client = _onboard_client_factory(repo_path=args.target_repo)
    try:
        profile = onboard_target_repo(client, args.target_repo)
    except _OperatorError:
        raise
    except Exception as error:  # pragma: no cover - defensive; onboard is data-safe
        raise _OperatorError(f"onboarding {args.target_repo} failed: {error}") from error

    if args.as_json:
        print(json.dumps(asdict(profile), indent=2))
    else:
        print(_render_onboard(profile))
    return EXIT_OK if profile.passed else EXIT_USER


def _render_onboard(profile: Any) -> str:
    """The human view: the repo's verdict line, then one line per finding.

    Each finding is `[pass|fail] <check>: <detail>`, ordered as the profile
    carries them, so an operator reading a rejected repo sees the first failing
    check at the top of the failures without hunting.
    """
    lines = [
        f"target repo {profile.repo} "
        f"{'PASSES' if profile.passed else 'FAILS'} onboarding",
        f"default branch: {profile.default_branch}",
        f"visibility: {profile.visibility}",
        f"merge queue enabled: {profile.queue_enabled}",
        f"declared gates: {', '.join(profile.declared_gates)}",
        f"required checks: {', '.join(profile.required_checks)}",
        "findings:",
    ]
    for finding in profile.findings:
        mark = "PASS" if finding.passed else "FAIL"
        lines.append(f"  [{mark}] {finding.check}: {finding.detail}")
    return "\n".join(lines)


# --- start: the graph, re-validated, dispatched under its own id (US3-S1) -----


def start_command(args: argparse.Namespace) -> int:
    """Start one epic from a compiled graph.

    Everything that can be checked without a server is checked without one: the
    file parses, the graph is structurally sound, and the proxy url the attempt's
    virtual key will be honored at is present. Only then is a client built — so a
    transport failure is always about the server, never about the file.

    The proxy is also where the preflight happens (US2): the model aliases this
    registry names and the first-attempt key aliases this epic will mint are
    checked against it *before* the workflow starts, so a misconfigured epic
    costs one message instead of attempts, issued credentials and a burned node.
    """
    try:
        graph = load_workgraph(args.graph)
        validate_workgraph(graph, _persona_registry(graph))
    except WorkGraphError as error:
        raise _OperatorError(str(error)) from error

    proxy_url = os.environ.get(PROXY_URL_ENV)
    if not proxy_url:
        # No default is available and none would be honest: an epic started
        # against a guessed proxy mints keys the agent cannot use and burns an
        # attempt to discover it (constitution VII).
        raise _OperatorError(
            f"{PROXY_URL_ENV} is not set; the agent's virtual key is only "
            "honored at the proxy, so no epic can be started without it"
        )

    return asyncio.run(_start_epic(graph, proxy_url, args.max_concurrent_nodes))


async def _start_epic(
    graph: WorkGraph, proxy_url: str, max_concurrent_nodes: int = 1
) -> int:
    client = await _connect()

    try:
        findings = await _run_preflight(graph)
    except ConfigError as error:
        # The CLI's own registry would not load: an operator-fixable config
        # error, reported before any dispatch (US2 honesty — we can only check
        # the aliases we can resolve).
        raise _OperatorError(f"preflight: {error}") from error

    exit_code = await _preflight_exit_code(findings)
    if findings:
        # Everything the operator must act on, at once, and nothing started.
        for finding in findings:
            print(f"factory-epic: preflight [{finding.check}]: {finding.detail}", file=sys.stderr)
        return exit_code

    epic_workflow_id = workflow_id(graph.epic_id)
    try:
        await client.start_workflow(
            EpicWorkflow.run,
            EpicInput(
                graph=graph,
                proxy_url=proxy_url,
                max_concurrent_nodes=max_concurrent_nodes,
            ),
            id=epic_workflow_id,
            task_queue=TASK_QUEUE,
        )
    except WorkflowAlreadyStartedError as error:
        # Temporal's id uniqueness *is* the one-epic-at-a-time rule the
        # `.factory/` stores need; an operator reads it as a sentence.
        raise _OperatorError(
            f"epic '{graph.epic_id}' is already running "
            f"(workflow id {epic_workflow_id})"
        ) from error

    print(epic_workflow_id)
    return EXIT_OK


def load_workgraph(path: str | Path) -> WorkGraph:
    """Read a compiled artifact back into the graph the workflow dispatches.

    Shape only: this rebuilds the dataclasses and refuses a document that is not
    a workgraph at all. Whether the graph *may run* is `validate_workgraph`'s
    question, asked separately by every caller, because the two failures read
    differently to an operator — "this is not a workgraph" versus "node 'us2'
    depends on 'us7'".
    """
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
            "'nodes' list (write one with `factory-epic derive`)"
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

    `validate_workgraph` takes the registry as an argument precisely so its
    caller decides which one applies (FR-002, R8). On the worker that is the real
    `personas.yaml`, read once per epic by `resolve_graph`. Here it must not be:
    the CLI runs in an operator's shell, which is not the worker's host, and a
    registry read there could accept a graph the worker rejects or reject one it
    would have run — a disagreement discovered at dispatch, after keys.

    So the CLI answers every lookup, which makes the two registry rules vacuous
    and leaves every structural rule — identity fields, duplicate ids, dangling
    edges, cycles, malformed overrides — in full force. Only `timeout_s` is read
    off these values, and only to prove a bound resolves.
    """
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


# --- status: the query, verbatim or rendered ---------------------------------


def status_command(args: argparse.Namespace) -> int:
    """Read one epic's live state (contracts/cli.md § status)."""
    return asyncio.run(_query_status(args.epic_id, as_json=args.as_json))


async def _query_status(epic_id: str, *, as_json: bool) -> int:
    client = await _connect()
    handle = client.get_workflow_handle(workflow_id(epic_id))
    try:
        # Untyped on purpose: the payload is printed as it arrived, so
        # `EpicStatus` has exactly one definition and `--json` cannot drift from
        # it. The workflow's mapping arrives with its keys in sorted order, which
        # for `us<n>` ids is declaration order — the order it was authored to run.
        document = await handle.query("epic_status")
    except RPCError as error:
        if error.status is RPCStatusCode.NOT_FOUND:
            raise _OperatorError(
                f"no epic '{epic_id}' is running here "
                f"(looked for workflow id {workflow_id(epic_id)})"
            ) from error
        raise _OperatorError(
            f"cannot read epic '{epic_id}': {error}", EXIT_TRANSPORT
        ) from error

    try:
        # FR-010: the Temporal execution status. A query against a closed
        # workflow succeeds and returns its final internal state — which is why
        # today's `status` could print RUNNING for a workflow already FAILED —
        # so the truth has to come from `describe()`, not from the query. It is
        # a sibling to the query's document, never merged into it (acceptance 3).
        described = await handle.describe()
        status = described.status
        if status is None:
            raise _OperatorError(
                f"cannot read epic '{epic_id}': no execution status reported",
                EXIT_TRANSPORT,
            )
        execution_status = status.name
    except RPCError as error:
        raise _OperatorError(
            f"cannot read epic '{epic_id}': {error}", EXIT_TRANSPORT
        ) from error

    # US1-S4: the query cannot carry live spend (observation rides the agent
    # heartbeat, which Temporal stores on the pending activity's mutable details,
    # not in workflow state), so the CLI reads it as a sibling from the server's
    # description of the running workflow. A client-side `describe` is an RPC over
    # server state — it emits no workflow history event, so FR-001/FR-002 are
    # untouched. Read before the human render so both formats see the same figure.
    live_spend = await _live_spend(client, handle, document)
    if as_json:
        # The query result stays byte-identical under its own keys; execution
        # status and live spend are *sibling* keys, never merged into the query's
        # document (contracts/cli.md § status, and plan US5's sibling-key rule).
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


async def _live_spend(
    client: Client,
    handle: Any,
    document: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    """Each running attempt's newest heartbeat snapshot, per node (US1-S4, US5).

    Observation rides the agent activity's heartbeat (plan US1), and Temporal
    stores heartbeat *details* on the pending activity's mutable state — visible
    to a client's `describe`, never on the workflow's event log. So the one
    mid-attempt spend surface is this read: decode each pending
    `run_agent_attempt`'s heartbeat payload and hand the figure to the renderer.

    Attribution is by the activity's own id, not by "the running node". The
    workflow stamps `activity_id` with the node id when it starts the attempt
    (US5), so a wide epic with N nodes in flight has N pending
    `run_agent_attempt` activities each carrying its own node — and each node's
    spend is charged to it alone (FR-011). The earlier single-node assumption —
    resolve "the" RUNNING node and charge every pending attempt to it — collapsed
    a fan-out onto one line, which is the failure mode US5 exists to stop; the
    RUNNING states in the query document are now a cross-check, never the key.

    A pending activity whose `activity_id` names no node in the document is
    skipped rather than guessed at: an `activity_id` this renderer does not
    recognize is either an attempt from before US5 stamped ids (a workflow still
    running from before the change) or something this CLI does not model, and
    either way charging it to an arbitrary node would be the bug revisited. A
    missing figure is not an error — the attempt has not measured spend yet
    (constitution V: unknown, not zero) or the workflow is not in an attempt. A
    `describe` that fails is likewise surfaced as no figure rather than a crashed
    status: the query already answered, and this is a sibling read.
    """
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
        # The node id is stamped on the activity when it is started (US5), so a
        # pending attempt is attributed to its own node even when several run at
        # once. An id that names no node in the query is not charged to a guess.
        node_id = activity_info.activity_id
        if node_id not in nodes:
            continue
        try:
            decoded = await converter.decode(
                list(activity_info.heartbeat_details.payloads),
                [Optional[UsageSnapshot]],
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
    """The human view: the epic's line, then one line per node, in query order.

    `<node_id>  <state>  attempt <n>  <branch>`. The branch is on the line
    because it is the one thing that outlives everything else: once `.factory/`
    is swept the branch is the whole account of the node's attempts (SC-004), and
    an operator reading a killed node should not need a second command to learn
    where its work went.

    The epic's line reports both the internal state and the Temporal execution
    status (FR-010), so a closed workflow never reads as a bare `RUNNING`: the
    execution status is the ground truth and the internal state is what the epic
    had in memory when the run last advanced. A node whose attempt is running
    shows its live spend (US1-S4) after the branch, so an operator mid-epic sees
    dollars move instead of a blank line.
    """
    nodes: Mapping[str, Mapping[str, Any]] = document["nodes"]
    id_width = max((len(node_id) for node_id in nodes), default=0)
    state_width = max((len(str(node["state"])) for node in nodes.values()), default=0)
    live = live_spend or {}

    lines = [
        f"epic {epic_id}  {document['epic_state']}  "
        f"execution {execution_status}"
    ]
    for node_id, node in nodes.items():
        # An existence check, never a magnitude check: whether the running
        # attempt has measured anything yet, not how much (SC-005).
        figure = live.get(node_id)
        spend_token = (
            f"  spend ${figure['spend_usd']:.2f}" if figure is not None else ""
        )
        lines.append(
            f"{node_id.ljust(id_width)}  {str(node['state']).ljust(state_width)}  "
            f"attempt {node['attempt']}  {node['branch']}{spend_token}"
        )
    return "\n".join(lines)


# --- the environment contract ------------------------------------------------


async def _connect() -> Client:
    """One client, from the notify bridge's exact environment contract (R12)."""
    address = os.environ.get(TEMPORAL_ADDRESS_ENV) or DEFAULT_TEMPORAL_ADDRESS
    namespace = os.environ.get(TEMPORAL_NAMESPACE_ENV) or DEFAULT_TEMPORAL_NAMESPACE
    try:
        return await Client.connect(address, namespace=namespace)
    except (RPCError, RuntimeError, OSError) as error:
        # The address is in the message because the commonest cause is a dev
        # server that is not up or an operator on the wrong host, and the fix
        # starts with the one string the CLI actually dialed.
        raise _OperatorError(
            f"cannot reach Temporal at {address} (namespace '{namespace}'): {error}",
            EXIT_TRANSPORT,
        ) from error


# --- arguments ----------------------------------------------------------------


class _Parser(argparse.ArgumentParser):
    """An `ArgumentParser` that exits 1, because a bad invocation is a user error.

    argparse's own status for that is 2, which this CLI's contract reserves for
    a Temporal that is not answering — a distinction a script would otherwise
    lose the moment someone mistyped a flag.
    """

    def error(self, message: str) -> Any:  # pragma: no cover - argparse's path
        self.print_usage(sys.stderr)
        self.exit(EXIT_USER, f"{self.prog}: error: {message}\n")


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = _Parser(
        prog="factory-epic",
        description="Compile, start and watch one epic (contracts/cli.md).",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    derive = commands.add_parser(
        "derive", help=f"compile <spec-dir>/{SPEC_NAME} into {ARTIFACT_NAME}"
    )
    derive.add_argument("spec_dir", help="the feature directory holding spec.md")
    derive.add_argument(
        "--target-repo",
        required=True,
        help="worker-host path to the repository the epic builds in",
    )
    derive.add_argument(
        "--specs-root",
        default=DEFAULT_SPECS_ROOT,
        help=f"where the worker finds feature specs (default: {DEFAULT_SPECS_ROOT})",
    )
    derive.add_argument(
        "-o",
        "--output",
        default=None,
        help=f"write the artifact here instead of <spec-dir>/{ARTIFACT_NAME}",
    )
    derive.set_defaults(run=derive_command)

    onboard = commands.add_parser(
        "onboard",
        help="validate a target repo for dispatch (merge queue + required checks, US3)",
    )
    onboard.add_argument(
        "target_repo",
        help="worker-host path to the target repo clone to validate",
    )
    onboard.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="print the TargetRepoProfile verbatim instead of the human view",
    )
    onboard.set_defaults(run=onboard_command)

    start = commands.add_parser("start", help="start the epic a compiled graph declares")
    start.add_argument("graph", help=f"path to a compiled {ARTIFACT_NAME}")
    start.add_argument(
        "--max-concurrent-nodes",
        type=_positive_int,
        default=1,
        help=(
            "how many ready nodes the scheduler may have in flight at once "
            "(default: 1 — today's sequential dispatch)"
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

    return parser.parse_args(argv)


if __name__ == "__main__":  # pragma: no cover - console script uses `main`
    sys.exit(main())
