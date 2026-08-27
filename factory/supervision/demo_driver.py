"""110-US1: the one-shot demo driver the engine container spawns on first boot.

The demo compose project (`container/compose.demo.yaml`) hands a stranger a
running factory and nothing to build. This module is what fills that gap: with
`ERGANE_DEMO=1` the container supervisor spawns it as a plain subprocess once
the worker and the bridge are up, and it prepares a throwaway project the
factory can be pointed at — control plane installed from the bundled answers, a
git repository with a manifest and one demonstration spec, a commit, and a
proof that the agent sandbox can actually start on this host.

Three properties are deliberate and each one has a scar behind it:

- **It is not a supervised child.** The supervisor treats any child dying
  unprompted as a fault and stops the container naming it
  (`container_supervisor.py:418-426`), so a one-shot in the supervised set would
  kill the stack at the moment of success. It is spawned beside that set and
  merely reaped.
- **It is a subprocess, never an in-process call.** It blocks on an install, on
  git, and on a watch loop that outlives the epic it is watching; running that
  on the supervisor's event loop is the shape that starved a Temporal heartbeat
  for 5m12s on 2026-08-24.
- **Its command line carries no `python -`.** Same reason the supervisor's does
  not: a cleanup sweep once ran `pkill -f "python -"` and matched a factory
  process (`container_supervisor.py:8-12`).

First boot is bounded by two sentinels under `$ERGANE_STATE_HOME/demo/`, and
they carry two different promises. `prepared` is written only *after* the
sandbox probe succeeds, so a probe refusal leaves nothing behind and a stranger
who fixes their host and restarts gets the demo rather than a permanent sulk.
`dispatch-attempted` is written *before* the dispatch verb, so a crash between
spending the stranger's key and recording that fact cannot re-spend it. Merging
them would collapse "retryable host problem" into "money was spent".

110-US2 adds the second phase: one `ergane build ship … --yes
--halt-after-pass`, then a poll of `ergane build status` that narrates each node
state as it changes and closes on the render the CLI itself produces — which in
halting mode carries the statement that landing was not attempted. The driver
never writes that statement itself; it prints what `build status` printed, so
the demo's last words and an operator's own reading of the epic are the same
words.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import time
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from factory.cli import init as init_module
from factory.cli.install import (
    _demo_anchor,
    _demo_manifest_text,
    _git_init,
    _run_cli,
)
from factory.controlplane.config import resolve_config_path
from factory.doctor.scaffold import scaffold_spec
from factory.registry import resolve_state_home
from factory.verify.toolchain import (
    GIT,
    NODE,
    UV,
    SystemTreeError,
    ToolchainError,
    resolve_toolchain,
    system_tree_argv,
)
from factory.workgraph.adapter import BWRAP_BACKEND_BINARY

#: The environment flag that opts a container into the demo (FR-001).
DEMO_ENV_VAR = "ERGANE_DEMO"

#: The bundled answers file, at the path the image copies the repository to.
DEFAULT_ANSWERS_PATH = Path("/opt/ergane/container/ergane-install-answer.demo.toml")

#: The throwaway repository's path, declared here because the compose file
#: declares it: `ergane_repo:/home/ergane/repo` (`compose.demo.yaml:89`). Read
#: from a constant rather than derived from `HOME`, so the path the volume is
#: mounted at and the path the driver writes to cannot drift apart.
DEFAULT_REPO_PATH = Path("/home/ergane/repo")

#: The demonstration spec, as `scaffold_spec` names it and `build status` will.
DEMO_SPEC_SLUG = "demo"
DEMO_SPEC_TITLE = "Demonstration"
DEMO_SPEC_DIRNAME = "001-demo"

#: The commit identity, explicit because the container user has none. Deriving
#: it from the environment is what makes the first commit fail with "Please tell
#: me who you are" on a host that never ran `git config --global`.
DEMO_GIT_NAME = "Ergane Demo"
DEMO_GIT_EMAIL = "demo@ergane.invalid"

#: Sentinel directory and the two sentinel names (FR-006).
DEMO_STATE_DIRNAME = "demo"
PREPARED_SENTINEL = "prepared"
DISPATCH_SENTINEL = "dispatch-attempted"

#: How often the watch loop asks the epic what changed, and how long it keeps
#: asking. The interval is a compromise between a narration that feels live and
#: a query the worker answers thousands of times for nothing; the ceiling exists
#: because the demo runs unattended in a stranger's terminal, and a node parked
#: on an operator who is not there would otherwise poll until the container is
#: killed. Expiry prints the last reading and leaves, rather than pretending the
#: epic ended.
DEFAULT_POLL_INTERVAL_S = 5.0
DEFAULT_WATCH_TIMEOUT_S = 7200.0

#: How many `build status` reads in a row may fail before the watch gives up.
#: A dispatch races its own workflow's first moments and a Temporal blip is not
#: news, so single failures are absorbed; a wall of them is reported with the
#: CLI's own words and ends the watch.
MAX_CONSECUTIVE_POLL_FAILURES = 10

#: Node states no further transition follows, whatever the mode. `PASSED` is
#: deliberately absent: a verified node normally still owes its landing a
#: terminal (`factory/workgraph/workflow.py:284-294`), and it is the *dispatch*
#: that makes PASSED terminal, not the state's name. The watch reads which of
#: the two it is watching off the status document's own `halt_after_pass`, so a
#: driver run without the flag would keep watching through the landing rather
#: than declaring victory one state early.
_TERMINAL_NODE_STATES = frozenset({"MERGED", "FAILED", "KILLED"})
_HALTED_TERMINAL_NODE_STATE = "PASSED"

#: Epic states that end the epic whatever its nodes say — a killed epic's nodes
#: are rewritten to KILLED on the way out, but the epic says so first.
_TERMINAL_EPIC_STATES = frozenset({"COMPLETED", "KILLED"})

#: Node states that mean the node got where it was going. Read only for the
#: driver's exit status, which the supervisor logs and nothing else consults;
#: what the *stream* says about a failure is `build status`'s render and not a
#: word more (FR-010).
_SUCCEEDED_NODE_STATES = frozenset({"PASSED", "MERGED"})

#: The one remedy line a sandbox refusal prints under the probe's own stderr.
#: Docker masks parts of `/proc`, and the kernel refuses a fresh procfs mount in
#: a user namespace unless the existing one is fully visible (bubblewrap#284),
#: which is exactly what the agent sandbox does on every dispatch.
SANDBOX_REMEDY = (
    "remedy: the agent sandbox needs an unmasked /proc. Run this project with "
    "`security_opt: [systempaths=unconfined]` on the engine service — it is "
    "already set in container/compose.demo.yaml — and make sure unprivileged "
    "user namespaces are enabled on the host "
    "(`sysctl kernel.unprivileged_userns_clone=1`)."
)

#: Prefix on every line the driver prints, so its narration is legible in the
#: interleaved `docker compose up` stream.
_PREFIX = "ergane demo:"


def _emit(line: str) -> None:
    """Print one narration line, flushed: the container log is a pipe."""
    print(f"{_PREFIX} {line}", flush=True)


@dataclass(frozen=True)
class ProbeOutcome:
    """What the sandbox probe found: whether it started, and what it said."""

    ok: bool
    stderr: str


def demo_state_dir(state_home: Path | str) -> Path:
    """The directory both sentinels live in."""
    return Path(state_home) / DEMO_STATE_DIRNAME


def sentinel_path(state_home: Path | str, name: str) -> Path:
    """The path of one named sentinel under the state home."""
    return demo_state_dir(state_home) / name


def write_sentinel(state_home: Path | str, name: str) -> Path:
    """Write one sentinel, creating the demo state directory if it is absent."""
    path = sentinel_path(state_home, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    return path


def sandbox_probe_argv(
    *,
    system_root: Path | str = Path("/"),
    binary: Path | str = BWRAP_BACKEND_BINARY,
) -> list[str]:
    """Assemble an adapter-shaped `bwrap` invocation that runs `true` and exits.

    The shape mirrors `factory/workgraph/adapter.py:427-580`: the environment is
    built rather than inherited, the system tree is read off this host, `/proc`
    and `/dev` are mounted fresh, the toolchain is bound read-only, and the
    process gets its own PID namespace and dies with its parent.

    `--proc` is the load-bearing token. The measured failure on 2026-08-26 —
    `bwrap: Can't mount proc on /newroot/proc` — fires at the fresh procfs mount
    and *nowhere earlier*, so a probe of `bwrap true` without `--unshare-pid
    --proc` passes cheerfully on a host where no agent can start.

    The toolchain is resolved as optional here, unlike in the adapter, because
    this probe answers one question — can bwrap build a namespace on this host —
    and a missing `node` is a different refusal that the adapter already makes
    by name at dispatch. Binding what is present keeps the mount set honest
    without inventing a second toolchain gate.
    """
    tools = resolve_toolchain(
        (UV, NODE, GIT),
        purpose="the demo sandbox probe",
        optional=(UV, NODE, GIT),
    )

    argv: list[str] = [str(binary), "--clearenv"]
    argv.extend(system_tree_argv(system_root))
    argv.extend(["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"])
    for tool in tools:
        source, dest = tool.bind
        argv.extend(["--ro-bind", source, dest])
    argv.extend(["--unshare-pid", "--die-with-parent"])
    argv.extend(["--", "/usr/bin/true"])
    return argv


def run_sandbox_probe(argv: Sequence[str]) -> ProbeOutcome:
    """Run the assembled probe, returning its verdict and its own stderr."""
    try:
        completed = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except OSError as error:
        return ProbeOutcome(ok=False, stderr=f"{argv[0]}: {error}")
    except subprocess.TimeoutExpired:
        return ProbeOutcome(
            ok=False, stderr=f"{argv[0]}: probe did not finish within 60s"
        )
    return ProbeOutcome(ok=completed.returncode == 0, stderr=completed.stderr.strip())


def _commit_demo_project(repo_root: Path) -> str:
    """Stage everything and commit it under the repo's own declared identity.

    The identity is written into the repository's config and used from there:
    the container user has no global one, and every later git operation on this
    repository — the worktrees a dispatch creates, the salvage commit a
    terminated node makes — needs one too.
    """
    subprocess.run(
        ["git", "-C", str(repo_root), "config", "user.name", DEMO_GIT_NAME],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_root), "config", "user.email", DEMO_GIT_EMAIL],
        check=True,
    )
    subprocess.run(["git", "-C", str(repo_root), "add", "-A"], check=True)

    staged = subprocess.run(
        ["git", "-C", str(repo_root), "diff", "--cached", "--quiet"],
    )
    if staged.returncode == 0:
        return "nothing to commit; the demonstration project is already committed"

    subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "commit",
            "--quiet",
            "-m",
            "The demonstration project, prepared on first boot",
        ],
        check=True,
    )
    return f"committed the demonstration project as {DEMO_GIT_NAME} <{DEMO_GIT_EMAIL}>"


def _write_demo_spec(repo_root: Path) -> Path:
    """Write the demonstration spec trio under `specs/001-demo/`."""
    spec_text, plan_text, tasks_text = scaffold_spec(
        slug=DEMO_SPEC_SLUG,
        title=DEMO_SPEC_TITLE,
        anchor=_demo_anchor(repo_root),
        demonstration=True,
    )
    spec_dir = repo_root / "specs" / DEMO_SPEC_DIRNAME
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "spec.md").write_text(spec_text, encoding="utf-8")
    (spec_dir / "plan.md").write_text(plan_text, encoding="utf-8")
    (spec_dir / "tasks.md").write_text(tasks_text, encoding="utf-8")
    return spec_dir


def run_prepare_phase(
    *,
    state_home: Path | str,
    repo_root: Path | str,
    answers_path: Path | str = DEFAULT_ANSWERS_PATH,
    run_cli: Callable[[Sequence[str]], int] = _run_cli,
    probe: Callable[[Sequence[str]], ProbeOutcome] = run_sandbox_probe,
    emit: Callable[[str], None] = _emit,
) -> int:
    """Install, scaffold, commit, and prove the sandbox — once (FR-002…FR-006).

    Returns 0 when the demonstration project is dispatchable and the sandbox
    started, and nonzero on a refusal. Nothing here dispatches: a nonzero return
    means the caller must stop *before* any spend, which is why the probe runs
    at the end of this phase rather than at the start of the next one.
    """
    state_home = Path(state_home)
    repo_root = Path(repo_root)
    answers_path = Path(answers_path)

    prepared = sentinel_path(state_home, PREPARED_SENTINEL)
    if prepared.is_file():
        emit(f"first boot already happened ({prepared}); nothing to prepare")
        return 0

    emit("first boot preparing the demonstration project")

    # 1. The control plane, from the bundled answers, through the CLI verb.
    config_path = resolve_config_path()
    emit(f"step 1/5 ergane install --from-file {answers_path}")
    install_status = run_cli(["install", "--from-file", str(answers_path)])
    if not config_path.is_file():
        emit(
            f"refusing: `ergane install` wrote no configuration at {config_path} "
            f"(exit {install_status}); the transcript above says why"
        )
        return 1
    if install_status != 0:
        # Install's exit code is control-plane *verification*, not whether the
        # config was written: an unauthenticated `gh` is a FAIL and is also the
        # normal state of a demo container. The configuration is what the rest
        # of this phase needs, and it exists.
        emit(
            f"control-plane verification reported findings (exit {install_status}); "
            f"the configuration was written, so preparation continues"
        )

    # 2. The throwaway repository.
    repo_root.mkdir(parents=True, exist_ok=True)
    _git_init(repo_root)
    emit(f"step 2/5 git init -b main {repo_root}")

    # 3. The manifest, from the same text the install demonstration writes.
    init_module._write_scaffold(repo_root, _demo_manifest_text())
    emit(f"step 3/5 wrote {repo_root / init_module.MANIFEST_NAME}")

    # 4. The demonstration spec trio.
    spec_dir = _write_demo_spec(repo_root)
    emit(f"step 4/5 wrote {spec_dir}")

    # 5. The commit, under an identity this container declares for itself.
    emit(f"step 5/5 {_commit_demo_project(repo_root)}")

    # The sandbox, before anything can be dispatched into it.
    try:
        argv = sandbox_probe_argv()
    except (ToolchainError, SystemTreeError) as refusal:
        emit(f"refusing: the agent sandbox cannot be assembled on this host\n{refusal}")
        emit(SANDBOX_REMEDY)
        return 1

    outcome = probe(argv)
    if not outcome.ok:
        emit("refusing: the agent sandbox could not start on this host")
        if outcome.stderr:
            print(outcome.stderr, flush=True)
        emit(SANDBOX_REMEDY)
        return 1
    emit("agent sandbox probe succeeded")

    sentinel = write_sentinel(state_home, PREPARED_SENTINEL)
    emit(f"first boot complete; {sentinel}")
    return 0


@dataclass(frozen=True)
class CliRun:
    """One `ergane` invocation's status and the two streams it wrote.

    The prepare phase's seam returns a bare status and lets the CLI's output go
    straight to the container log, because an install transcript is something a
    stranger should watch arrive. This phase needs the text itself: it decides
    what to print (a refusal, verbatim), and it parses one answer (`build status
    --json`) rather than showing it. The streams stay apart because the JSON is
    on one of them and a skew notice is on the other.
    """

    status: int
    stdout: str
    stderr: str


def _run_cli_captured(argv: Sequence[str]) -> CliRun:
    """Run one `ergane` invocation in-process, capturing what it wrote.

    In-process for the same reason `_run_cli` is: this *is* the ergane CLI, and
    spawning a second interpreter to reach it would double the import cost and
    lose the exit code's meaning behind a shell. `SystemExit` is caught because
    `argparse` raises it for a malformed argv, and a driver that died of a
    traceback here would take the demo's narration with it.

    Capturing costs the dispatch its live stream: `build ship`'s validate,
    derive and preflight output arrives in one block when the verb returns
    rather than line by line while it works. That is the price of the phase
    being able to decide what to print, and it buys the thing FR-009 is about —
    a refusal printed as the driver's last words rather than as a line the watch
    loop then talks over. The polls are captured for the opposite reason: a
    status document every few seconds would bury the narration it is there to
    produce.
    """
    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            status = _run_cli(list(argv))
    except SystemExit as exit_request:
        status = int(exit_request.code or 0)
    return CliRun(status=status, stdout=out.getvalue(), stderr=err.getvalue())


def ship_argv(
    repo_root: Path | str, *, spec_dirname: str = DEMO_SPEC_DIRNAME
) -> list[str]:
    """The dispatch, whole: one verb, `--yes`, and halting mode (FR-007).

    `build ship` already chains validate → derive → summary → confirm → dispatch
    (`factory/cli/nouns/build.py:838-893`), so the driver assembles this argv and
    nothing else. A driver that ran `spec validate`, then `spec derive`, then
    `build start` would be a second implementation of that chain, drifting from
    the one an operator types the first time either of them changed.

    The spec directory is absolute. The driver's working directory is whatever
    the supervisor was started in, which is nobody's declaration of where the
    demonstration project lives — the repository root it was handed is
    (constitution IX).
    """
    repo_root = Path(repo_root)
    return [
        "build",
        "ship",
        str(repo_root / "specs" / spec_dirname),
        "--target-repo",
        str(repo_root),
        "--yes",
        "--halt-after-pass",
    ]


def status_argv(epic_id: str, *, as_json: bool = False) -> list[str]:
    """`ergane build status <epic>`, in either of the two forms this phase reads."""
    argv = ["build", "status", epic_id]
    if as_json:
        argv.append("--json")
    return argv


def _print_transcript(run: CliRun) -> None:
    """Print what a CLI invocation wrote, unprefixed and unedited.

    Both streams, stdout first, because a refusal is often a finding on one and
    an `ergane:` line on the other and the reader needs both halves. Nothing is
    added, reflowed or summarised: this is the CLI's own voice, and the whole
    point of FR-010 is that the driver does not acquire one of its own for it.
    """
    for stream in (run.stdout, run.stderr):
        text = stream.rstrip("\n")
        if text:
            print(text, flush=True)


def _transition_line(node_id: str, previous: str | None, state: str) -> str:
    """One node's change of state, as the compose stream will read it.

    The first sighting of a node has no arrow: there is no state it came from,
    and `PENDING -> PENDING` would read as a transition that did not happen.
    ASCII, because this line goes to whatever encoding a stranger's terminal
    turned out to have.
    """
    if previous is None:
        return f"{node_id}  {state}"
    return f"{node_id}  {previous} -> {state}"


def _node_states(document: Mapping[str, Any]) -> dict[str, str]:
    """Each node's state, by node id, in the order the query reported them."""
    nodes = document.get("nodes")
    if not isinstance(nodes, Mapping):
        return {}
    states: dict[str, str] = {}
    for node_id, node in nodes.items():
        if isinstance(node, Mapping) and node.get("state") is not None:
            states[str(node_id)] = str(node["state"])
    return states


def _is_terminal(document: Mapping[str, Any]) -> bool:
    """Whether this reading is the epic's last one.

    Two independent answers, because they become true at different moments: the
    epic declares itself COMPLETED only once its workflow returns, while a
    single-node graph in halting mode is *done* the instant its node reaches
    PASSED. Waiting for the first alone would leave the demo's closing render a
    teardown behind the thing it describes.
    """
    if str(document.get("epic_state", "")) in _TERMINAL_EPIC_STATES:
        return True
    states = _node_states(document)
    if not states:
        return False
    terminal = set(_TERMINAL_NODE_STATES)
    if document.get("halt_after_pass"):
        terminal.add(_HALTED_TERMINAL_NODE_STATE)
    return all(state in terminal for state in states.values())


def _succeeded(document: Mapping[str, Any]) -> bool:
    """Whether every node in that last reading got where it was going."""
    states = _node_states(document)
    return bool(states) and all(
        state in _SUCCEEDED_NODE_STATES for state in states.values()
    )


def _decode_status(run: CliRun) -> Mapping[str, Any] | None:
    """The status document a `--json` read returned, or `None` if it did not.

    A poll that failed and a poll that answered something this driver cannot
    read are the same event to the loop above: no new reading. Distinguishing
    them would buy a second error message for one retry budget.

    `epic_state` is what makes an answer a reading. A workflow that refuses to
    describe itself is reported by `build status` as a successful command with a
    document of `{"nodes": {}, "refusal": …}` (`build.py:900-909`) — exit 0, no
    epic state, no nodes. Taken at face value that is a run that never moves and
    never ends, and the watch would poll it until its ceiling. Counted as an
    unreadable answer instead, it spends the retry budget and then leaves,
    printing the refusal the CLI put in the document.
    """
    if run.status != 0:
        return None
    try:
        document = json.loads(run.stdout)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(document, Mapping) or "epic_state" not in document:
        return None
    return document


def run_watch_phase(
    *,
    epic_id: str = DEMO_SPEC_DIRNAME,
    run_cli_captured: Callable[[Sequence[str]], CliRun] = _run_cli_captured,
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
    timeout_s: float = DEFAULT_WATCH_TIMEOUT_S,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    emit: Callable[[str], None] = _emit,
) -> int:
    """Narrate one epic to its terminal state, then print the render (FR-008).

    Every line this loop writes is one of two things: a node whose state is not
    what it was last time, or — once — the text `ergane build status` prints.
    That division is the story. The transitions exist because a stranger reading
    `docker compose up` needs to see the epic moving; the render exists because
    the closing statement about landing has to be the CLI's sentence and not a
    rephrasing of it, and the only way to guarantee that is to not write it.

    Returns 0 when the epic ended with every node where it was going, nonzero
    otherwise. Nothing in the stream reports that distinction a second time: a
    failure's account is the render, verbatim (FR-010).
    """
    seen: dict[str, str] = {}
    failures = 0
    deadline = clock() + timeout_s

    while True:
        run = run_cli_captured(status_argv(epic_id, as_json=True))
        document = _decode_status(run)
        if document is None:
            failures += 1
            if failures >= MAX_CONSECUTIVE_POLL_FAILURES:
                emit(
                    f"refusing: `ergane build status {epic_id}` has not given a "
                    f"readable reading {failures} times running; the last answer "
                    "follows and the demo stops watching"
                )
                _print_transcript(run)
                return 1
            sleep(poll_interval_s)
            continue
        failures = 0

        for node_id, state in _node_states(document).items():
            previous = seen.get(node_id)
            if previous == state:
                continue
            emit(_transition_line(node_id, previous, state))
            seen[node_id] = state

        if _is_terminal(document):
            _print_transcript(run_cli_captured(status_argv(epic_id)))
            return 0 if _succeeded(document) else 1

        if clock() >= deadline:
            emit(
                f"the epic has not reached a terminal state in {timeout_s:.0f}s; "
                "the last reading follows and the demo stops watching"
            )
            _print_transcript(run_cli_captured(status_argv(epic_id)))
            return 1

        sleep(poll_interval_s)


def run_dispatch_phase(
    *,
    state_home: Path | str,
    repo_root: Path | str,
    spec_dirname: str = DEMO_SPEC_DIRNAME,
    run_cli_captured: Callable[[Sequence[str]], CliRun] = _run_cli_captured,
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
    timeout_s: float = DEFAULT_WATCH_TIMEOUT_S,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    emit: Callable[[str], None] = _emit,
) -> int:
    """Dispatch the demonstration epic once, then watch it (FR-007…FR-010).

    The sentinel goes down *before* `build ship`, and that order is the design
    rather than an oversight (plan T4). This is the moment the stranger's key
    starts being spent; a driver that recorded the fact afterwards would, in the
    window between the dispatch and the record, answer a container restart by
    spending it again. Writing it first can at worst cost a demo that never ran
    — recoverable by deleting one file — where the other order costs money.

    A refusal from `build ship` is printed as it was written and is the last
    thing this process says. There is nothing to stop and nothing to roll back:
    the driver is not a supervised child (FR-001), so the services it never
    touched go on running and the container stays up for the stranger to look
    around in.
    """
    state_home = Path(state_home)
    repo_root = Path(repo_root)

    attempted = sentinel_path(state_home, DISPATCH_SENTINEL)
    if attempted.is_file():
        emit(
            f"the demonstration epic was already dispatched ({attempted}); "
            f"read it with `ergane build status {spec_dirname}`"
        )
        return 0

    argv = ship_argv(repo_root, spec_dirname=spec_dirname)
    write_sentinel(state_home, DISPATCH_SENTINEL)
    emit("dispatching: ergane " + " ".join(argv))

    run = run_cli_captured(argv)
    _print_transcript(run)
    if run.status != 0:
        return run.status

    return run_watch_phase(
        epic_id=spec_dirname,
        run_cli_captured=run_cli_captured,
        poll_interval_s=poll_interval_s,
        timeout_s=timeout_s,
        sleep=sleep,
        clock=clock,
        emit=emit,
    )


def _default_state_home() -> Path:
    """The state home this container declares, or the resolver's default."""
    declared = os.environ.get("ERGANE_STATE_HOME")
    return Path(declared) if declared else Path(resolve_state_home())


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare and drive the Ergane demonstration project."
    )
    parser.add_argument(
        "--state-home",
        default=None,
        help="Where the first-boot sentinels live; defaults to ERGANE_STATE_HOME",
    )
    parser.add_argument(
        "--repo",
        default=str(DEFAULT_REPO_PATH),
        help=f"The demonstration repository (default: {DEFAULT_REPO_PATH})",
    )
    parser.add_argument(
        "--answers-file",
        default=str(DEFAULT_ANSWERS_PATH),
        help=f"Install answer file (default: {DEFAULT_ANSWERS_PATH})",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for `python3 -m factory.supervision.demo_driver`.

    Every failure leaves as a named line and a nonzero status rather than as a
    traceback: this process's stdout is the `docker compose up` stream a
    stranger is reading, and the supervisor beside it only logs what it reaped.

    The two phases are strictly ordered and the gate between them is absolute: a
    nonzero prepare — a control plane that wrote no config, a sandbox that could
    not start — stops the driver *before* any spend, which is the whole reason
    the probe lives at the end of prepare rather than the start of dispatch. On
    a second boot both phases are one-line no-ops, each for its own sentinel's
    own reason.
    """
    args = _build_parser().parse_args(argv)
    state_home = Path(args.state_home) if args.state_home else _default_state_home()
    repo_root = Path(args.repo)
    try:
        prepared = run_prepare_phase(
            state_home=state_home,
            repo_root=repo_root,
            answers_path=Path(args.answers_file),
        )
        if prepared != 0:
            return prepared
        return run_dispatch_phase(state_home=state_home, repo_root=repo_root)
    except Exception as error:
        _emit(f"first boot failed: {type(error).__name__}: {error}")
        return 1


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
