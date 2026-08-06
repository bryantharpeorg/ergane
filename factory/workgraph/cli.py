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
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from factory.activities.merge_activities import onboard_target_repo
from factory.config import Persona, WriteScope
from factory.mergequeue.gh import GhClient
from factory.notify.service import (
    DEFAULT_TEMPORAL_ADDRESS,
    DEFAULT_TEMPORAL_NAMESPACE,
    TEMPORAL_ADDRESS_ENV,
    TEMPORAL_NAMESPACE_ENV,
)
from factory.usage.litellm_client import PROXY_URL_ENV
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

    return asyncio.run(_start_epic(graph, proxy_url))


async def _start_epic(graph: WorkGraph, proxy_url: str) -> int:
    client = await _connect()
    epic_workflow_id = workflow_id(graph.epic_id)
    try:
        await client.start_workflow(
            EpicWorkflow.run,
            EpicInput(graph=graph, proxy_url=proxy_url),
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

    print(json.dumps(document, indent=2) if as_json else render_status(epic_id, document))
    return EXIT_OK


def render_status(epic_id: str, document: Mapping[str, Any]) -> str:
    """The human view: the epic's line, then one line per node, in query order.

    `<node_id>  <state>  attempt <n>  <branch>`. The branch is on the line
    because it is the one thing that outlives everything else: once `.factory/`
    is swept the branch is the whole account of the node's attempts (SC-004), and
    an operator reading a killed node should not need a second command to learn
    where its work went.
    """
    nodes: Mapping[str, Mapping[str, Any]] = document["nodes"]
    id_width = max((len(node_id) for node_id in nodes), default=0)
    state_width = max((len(str(node["state"])) for node in nodes.values()), default=0)

    lines = [f"epic {epic_id}  {document['epic_state']}"]
    lines += [
        f"{node_id.ljust(id_width)}  {str(node['state']).ljust(state_width)}  "
        f"attempt {node['attempt']}  {node['branch']}"
        for node_id, node in nodes.items()
    ]
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
