"""The one place the factory touches an agent (D-018).

Launch a headless coding agent in the node's worktree, watch it, end it when its
deadline passes, classify how it ended, keep what it produced. That is the whole
seam: no diff is read here, no usage is counted here, and nothing the agent
*says* is inspected anywhere (FR-012). A second agent is a second class in this
module — `adapter_for` resolves the persona registry's `agent` field to one — and
the orchestration above it does not change. Since 154-US4 the attempt policy that
policy's name implies — pid file, orphan reap, archive, monitor loop, deadline,
operator-question ferry, backend resolution, standards path — is written once, in
`SharedAttemptPolicy`; an adapter class supplies only the per-CLI surface (argv,
prompt delivery, provider env, home seeding, credential discovery, the
turn-happened probe, refusal markers) and delegates.

Four properties are the reason this file is longer than a `subprocess.run`:

- **The child environment is built, not filtered** (US2-S1). `attempt_env`
  returns exactly the proxy URL, the attempt's virtual key, and a four-name
  passthrough. A denylist would protect the credentials we thought of and leak
  the one the worker host acquires next quarter; by constructing the environment
  the master key and the bot token are absent because nothing put them there
  (constitution V). The virtual key is the only credential that crosses into the
  child, which is exactly what makes the attempt's spend attributable.

- **A deadline ends the process tree.** An agent spawns `git`, `uv`, test
  runners; killing its root leaves grandchildren holding the worktree. So the
  agent gets its own session, the deadline is enforced against the whole process
  *group*, and SIGTERM is followed by SIGKILL once the grace expires — 002's gate
  runner pattern, for the same reason. The bound is enforced here rather than by
  Temporal's `start_to_close_timeout` because a Temporal timeout kills the
  activity and leaves the agent running, forfeiting both the classification and
  the salvage the node's terminal path depends on (R2).

- **The previous attempt is reaped before this one launches** (R4). A worker that
  died mid-attempt leaves an agent alive against the same worktree, and Temporal
  will happily retry the activity into it. Two agents in one worktree is
  corruption, so a pgid file per node is the next run's handle on the last one.
  Reaping is a precaution, not a gate: garbage in that file costs the node
  nothing.

- **Evidence survives every path** (FR-007). `stdout.log` is streamed straight
  into the attempt's archive directory rather than collected at exit, so a killed
  agent leaves what it had printed by the time it died, and the session
  transcript is copied in afterwards on the completed, failed, timed-out and
  killed paths alike. The archive lives under the worker host's `.factory/`,
  never inside a worktree, where salvage would commit the agent's own transcript
  to the node branch and the diff check would read it as work.

Classification is exit status and one structural fact: zero → `COMPLETED`,
non-zero → `AGENT_ERROR`, a non-zero exit with no agent turn behind it →
`PRE_AGENT_FAILURE` (095-US1), deadline → `TIMEOUT`, cancellation → `KILLED`.
`COMPLETED` is a statement about a process, never a claim that the work is done —
the verdict belongs to component 2, later, from the worktree.

The one addition to "exit status and nothing else" is still not a reading of
what the agent *said* (FR-012). The agent CLI writes its session transcript on
its first turn, so the absence of that file is the structural tell that the
process produced no token, prepared no worktree, and attempted nothing of the
story — the fact that separates a credential that expired from a build that
broke. The dying process's own words are quoted for the operator one layer up,
in the activity, and decide nothing here.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import pwd
import re
import shutil
import signal
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Protocol, Sequence

from factory.config import ROUTE_SUBSCRIPTION, SUBSCRIPTION_AGENT, effective_route
from factory.usage.models import Termination, UsageSnapshot
from factory.verify.factory_yaml import FactoryConfigError, MANIFEST_NAME, load_factory_config, resolve_manifest_path
from factory.verify.gates import BwrapGateExecutor, ordered_binds
from factory.verify.toolchain import (
    CODEX_RUNNER,
    GIT,
    NODE,
    UV,
    ResolvedTool,
    ToolchainError,
    container_path,
    npm_install_root,
    resolve_toolchain,
    system_tree_argv,
)
from factory.workgraph.detector import compare_and_report, capture_start
from factory.workgraph.codex_credential import (
    CredentialDeclaration,
    CredentialFinalization,
    CredentialFenceFailure,
    credential_provenance_json,
    finalize_current_candidate,
    validate_codex_credential,
)
from factory.workgraph.codex_events import INVALID_JSON, decode_codex_events
from factory.workgraph.models import AdapterResult, AttemptContext
from factory.workgraph.worktree import SALVAGE_AUTHOR_EMAIL, SALVAGE_AUTHOR_NAME

#: The agent's combined stdout and stderr, streamed live into the attempt's
#: archive directory. Interleaved as the agent wrote it: two files would put the
#: burden of reconstructing the order on whoever reads the evidence.
STDOUT_LOG_NAME = "stdout.log"

CODEX_EVENTS_NAME = "codex-events.jsonl"
CODEX_STDERR_NAME = "codex-stderr.log"
CODEX_RAW_STATUS_NAME = "codex-raw-status.json"

CODEX_RAW_MAX_BYTES = 1_048_576
CODEX_RAW_RETENTION_FILES = 1


class InvocationOutputPolicy(StrEnum):
    """How a backend routes the two process output streams."""

    COMBINED = "combined"
    SEPARATE = "separate"

#: Environment variable names the agent inherits from the worker, on top of the
#: two the attempt itself supplies. `PATH` is what finds the agent binary and the
#: tools it shells out to; `LANG`/`TERM` keep its output decodable and unadorned.
#: `HOME` is intentionally absent: it is the factory's per-node home, written from
#: `AttemptContext` rather than inherited (US1). A name absent from the worker's
#: environment stays absent from the child's — passthrough is passthrough, not
#: invention.
PASSTHROUGH_ENV: tuple[str, ...] = ("PATH", "LANG", "TERM")

#: The agent CLI, resolved from the child's `PATH` (R6). Not configurable: which
#: binary a persona runs is the registry's `agent` field, which selects a class.
DEFAULT_EXECUTABLE = "claude"

#: The environment variable that carries the operator's long-lived subscription
#: bearer token. `claude setup-token` mints it and tells the operator to export it
#: under this name; the factory carries it into subscription-routed attempts and
#: nowhere else (US1 FR-001/FR-003/FR-006).
CLAUDE_CODE_OAUTH_TOKEN = "CLAUDE_CODE_OAUTH_TOKEN"

#: A subscription-routed attempt used the long-lived token from the worker
#: environment (US1 FR-005).
CREDENTIAL_SOURCE_OAUTH_TOKEN = "oauth_token"

#: A subscription-routed attempt fell back to the copied operator credential
#: seeded into the per-node HOME (US1 FR-004/FR-005).
CREDENTIAL_SOURCE_COPIED_CREDENTIALS = "copied_credentials"

#: Seconds between SIGTERM and SIGKILL at the deadline. Long enough for an agent
#: to flush the session transcript that is about to become the only account of
#: what it was doing, short enough that ignoring TERM buys nothing.
DEFAULT_GRACE_S = 10.0

#: How long a failing process may have run and still be read as pre-agent
#: (095-US1). It is not the discriminator — the absence of a session transcript
#: is — it is the guard on the discriminator. The transcript's location is a
#: convention of the agent CLI, and the day that convention moves, every failing
#: attempt would look tokenless; a run that held the worktree for a minute
#: plainly did more than fail to start, so it stays an `AGENT_ERROR` whatever the
#: transcript path says. Generous in the other direction on purpose: the failure
#: this bound exists for ran four attempts in thirteen seconds, and a credential
#: refusal is a local check, not a round trip.
PRE_AGENT_WINDOW_S = 60.0

#: How often the adapter beats while waiting (R2) — the interval that makes a
#: multi-hour attempt cancellable in seconds rather than at its deadline.
#:
#: One second, not the leisurely half-minute a liveness signal would need,
#: because the beat is also the *only* channel a kill travels down: Temporal
#: delivers activity cancellation in a heartbeat's response, and its client
#: batches beats to one round trip per 80% of the activity's heartbeat timeout.
#: The interval and that timeout therefore bound how long an agent keeps
#: spending after an operator says stop (`workflow._AGENT_HEARTBEAT_TIMEOUT`
#: derives from this constant for exactly that reason). Beating this often costs
#: nothing — it is an in-process call whose round trips are batched away, and the
#: monitor loop is already awake to check the deadline.
DEFAULT_HEARTBEAT_INTERVAL_S = 1.0

#: Seconds between usage reads while the agent works (R3, plan US1). Much slower
#: than the beat: the read is a proxy round trip, throttled to its own cadence so
#: an hours-long attempt issues a bounded number of `/key/info` calls. The same
#: value the old loop polled at, so moving the read inside the activity does not
#: change how often the proxy is queried — it only stops charging the workflow's
#: history for it (FR-001, FR-002).
DEFAULT_POLL_INTERVAL_S = 30

#: Seconds between ferry answer polls while a question is in flight (008-US3).
#: The answer read is a store round trip the bridge fills, throttled to its own
#: cadence the way the usage read is — a question waiting hours for an operator
#: issues a bounded number of polls, and the beat (which carries liveness) is
#: never gated on it. The question ships up the moment its file appears (no
#: throttle: it ships once); only the answer poll is cadenced.
DEFAULT_FERRY_INTERVAL_S = 5.0

#: The env var that hands the agent its archive directory (008-US3). The ferry
#: channel is the filesystem the agent already owns: `question` and `answer`
#: files in the archive directory, never the worktree (where salvage would
#: commit them — FR-007). The agent learns the directory from the environment
#: the adapter builds, not from a worker path in the prompt (the prompt carries
#: no worker path).
ATTEMPT_ARCHIVE_ENV = "ATTEMPT_ARCHIVE"


#: The name and email the factory attributes to agent commits and salvage (FR-005,
#: constitution VI). Imported from `worktree.py` so the two surfaces never drift.
_SALVAGE_AUTHOR_NAME = SALVAGE_AUTHOR_NAME
_SALVAGE_AUTHOR_EMAIL = SALVAGE_AUTHOR_EMAIL

#: The ferry file names — the contract the adapter's monitor loop and the agent
#: share, lived in `$ATTEMPT_ARCHIVE`. The agent writes `question`, polls for
#: `answer`; the adapter ferries question up and answer down (FR-009).
FERRY_QUESTION_FILE = "question"
FERRY_ANSWER_FILE = "answer"

#: The stdout marker that means a subscription-routed attempt reached the
#: sandbox but the CLI refused the credential (US3-S5/FR-013). Measured
#: 2026-08-19: printed on stdout, not stderr, with exit status 1.
SUBSCRIPTION_REFUSAL_MARKER = "Not logged in · Please run /login"

#: The stdout marker that means the runner refused the launch because the
#: session id was already in use (107 FR-014). Measured: printed on stdout with
#: exit status 1, `Error: Session ID <36-char uuid> is already in use.` The id
#: varies per refusal, so the marker is the stable substring, not the whole
#: line — a classifier that matched the literal 74-byte refusal would rot on the
#: next CLI bump (trap 11).
SESSION_ID_REFUSAL_MARKER = "is already in use."

_NON_ALNUM = re.compile(r"[^a-zA-Z0-9]")


async def _invoke_heartbeat(
    heartbeat: Callable[[UsageSnapshot | None], Awaitable[None] | None],
    snapshot: UsageSnapshot | None,
) -> None:
    """Fire the beat, tolerating a sync or async callback.

    Temporal's `activity.heartbeat` is sync; a test's spy may be `async def`.
    The snapshot is the beat's details — the only reason a callback is ever
    interesting is what it carries, so a callback that raises is a real defect
    (unlike a spend read failing) and propagates.
    """
    result = heartbeat(snapshot)
    if result is not None:
        await result


class _FerryState:
    """The in-attempt ferry's per-attempt state, kept across beats (008-US3).

    The monitor loop is beat-sized, so the ferry has to remember three things
    between beats: whether the question has shipped (``question_id`` is set the
    moment the send succeeds, so the question ships up exactly once), whether
    the answer has been delivered (``answer_written`` stops the answer poll the
    beat after it lands), and the archive directory both files live in. A plain
    object rather than a dataclass because the two booleans mutate every beat
    and a frozen dataclass would rebuild one each time for no gain.

    The agent, not this state, bounds the ferry window: when its own wait
    elapses it proceeds to the US1 final-message path, so the state never holds
    a timer and the adapter never decides a question is over (FR-009).
    """

    def __init__(self, archive: Path) -> None:
        self.archive = archive
        self.question_id: str | None = None
        self.answer_written: bool = False

    def read_question(self) -> str | None:
        """The question file's text, or None if the agent has not written one yet.

        A filesystem read that fails is treated as "no question yet": a
        transient I/O error must not convert a question into a hang (FR-009),
        and the next beat will try again. An empty file is None too — a question
        with no body parks nothing, the same rule the US1 detector applies.
        """
        path = self.archive / FERRY_QUESTION_FILE
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        return text or None

    def write_answer(self, answer: str) -> None:
        """Deliver the answer down to the polling agent.

        Best-effort like the archive step: a write that fails leaves the agent
        polling, and the agent degrades to the US1 path when its window elapses.
        Marked written before the bytes are observed so a second beat does not
        double-deliver; the file is written in one call so the agent never reads
        a half-written answer.
        """
        if self.answer_written:
            return
        path = self.archive / FERRY_ANSWER_FILE
        self.answer_written = True
        try:
            path.write_text(answer, encoding="utf-8")
        except OSError:
            # A failed write is not a hang: the next beat polls again and the
            # agent degrades to the US1 path if the window elapses first.
            pass


class AdapterError(RuntimeError):
    """The agent could not be run at all — infrastructure, never a verdict.

    Distinct from a non-zero exit, which is an `AGENT_ERROR` termination and
    ordinary ladder input. This is "there is no such adapter" or "the binary is
    not on the worker host": a config error the operator has to fix, and one the
    ladder must not spend an attempt on.
    """


# The launch seam (US2) --------------------------------------------------------


@dataclass(frozen=True)
class AgentInvocation:
    """Everything one launch backend receives: the argv, prompt, env, cwd, and the
    persona routing the prompt was assembled for.

    This is the seam's payload, not the adapter's policy. The monitor, the
    deadline, the archive, and the detector all stay in the adapter; only the
    moment of spawning the agent process moves behind this boundary.
    """

    argv: list[str]
    prompt: str
    worktree: Path
    env: dict[str, str]
    log: Any
    standards_path: str | None
    model_alias: str
    #: The adapter's policy, not a backend's guess. Combined is the default so
    #: every existing invocation keeps today's contract; a separate invocation
    #: must also supply the second sink before it can launch.
    output_policy: InvocationOutputPolicy = InvocationOutputPolicy.COMBINED
    stderr_log: Any | None = None


class AgentBackend(Protocol):
    """How one agent runtime turns an invocation into a running process.

    Following the `GateExecutor` precedent: the adapter owns the policy
    (deadline, signals, archive), and the backend owns only the spawn. Two
    implementations exist in US2: the host launch (today's direct spawn, kept
    but selectable only explicitly) and the fake the tests drive. The bwrap
    implementation plugs into the same socket in US3.
    """

    name: str

    async def launch(
        self,
        invocation: AgentInvocation,
    ) -> asyncio.subprocess.Process: ...


#: Absolute path the bwrap backend is pinned to. The pin is required because
#: AppArmor attaches a profile by executable path on exec, so a copied or vendored
#: binary does not carry the host's grant and fails with EPERM. The grant comes
#: from the profile this repository ships at container/ergane-bwrap.apparmor,
#: which no OS package installs; loading it is the operator's deliberate act.
BWRAP_BACKEND_BINARY = Path("/usr/bin/bwrap")


def _inside_system_tree(path: Path, system_root: Path) -> bool:
    """Whether the system-tree bind already carries `path`.

    `system_tree_argv` ro-binds `<root>/usr` wholesale, so anything under it
    needs no entry of its own — and a `--symlink` at a path the bound tree
    already carries makes bwrap refuse to start (measured for claude in the
    demo container, 2026-08-26; the gate executor keeps the same rule in
    `_toolchain_binds`). `system_root` is the seam tests supply a fake tree
    through.
    """
    return str(path).startswith(str(system_root / "usr") + "/")


class AgentBackendBase:
    def _stderr_sink(self, invocation: AgentInvocation) -> Any:
        if invocation.output_policy is InvocationOutputPolicy.COMBINED:
            return asyncio.subprocess.STDOUT
        if invocation.stderr_log is None:
            raise AdapterError("separate output policy requires an stderr sink")
        return invocation.stderr_log


class HostAgentBackend(AgentBackendBase):
    """Today's direct host launch, now one implementation behind the seam.

    Selectable only explicitly — the default path resolves the backend from the
    manifest's `runtime:` key. This implementation exists so US4 can run a
    control with the boundary disabled, and for no other production path.
    """

    name = "host"

    def __init__(self, *, executable: str = DEFAULT_EXECUTABLE) -> None:
        self.executable = executable

    async def launch(self, invocation: AgentInvocation) -> asyncio.subprocess.Process:
        try:
            stderr = self._stderr_sink(invocation)
            return await asyncio.create_subprocess_exec(
                *invocation.argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=invocation.log,
                stderr=stderr,
                cwd=str(invocation.worktree),
                env=invocation.env,
                start_new_session=True,
            )
        except OSError as error:
            raise AdapterError(
                f"could not launch agent '{self.executable}' for "
                f"{invocation.argv}: {error}"
            ) from error

class BwrapBackend(AgentBackendBase):
    """Bubblewrap containment: the agent's filesystem is its worktree, not the host.

    The mount set is deliberately minimal (US3). `/usr` is read-only, and each
    of `/bin`, `/lib`, `/lib64` and `/sbin` is mirrored exactly where the host
    keeps a symlink there — derived per host by `system_tree_argv`, because the
    set differs by architecture and a written-down one starts no agent on a host
    that disagrees with it. `/proc`, `/dev`, and a tmpfs `/tmp` give the shell
    and toolchain enough of a runtime to function. The node worktree is bound writable at the same absolute
    path, and only the leaf worktree — never the runtime root that contains it.

    Git worktrees keep their metadata in the parent repository's `.git` tree:
    the worktree's `.git` file points back to `.git/worktrees/<name>`. The
    minimal set (shared object store + worktree metadata) proved brittle: git
    needs to write `index.lock`, refs and objects during commit/diff. Binding the
    parent repo's whole `.git` directory writable is therefore the chosen route;
    the working tree remains outside the boundary (trap 1).

    The toolchain is *discovered*, not declared: `uv`, `node`, `git` and the
    agent runner are resolved on the host at dispatch time and bound read-only
    at the paths discovery returned, with `claude`'s symlink target mounted at
    the symlink's own path so it is not dangling inside the container. `PATH`
    inside the container is derived from those same resolutions, so it can only
    name directories the mount set actually put there. The literals this used to
    carry named one operator's home and two toolchain version numbers; both
    failed as `bwrap: Can't find source path` after the fork, reaching the
    operator as a diffless `agent_error`. See `factory.verify.toolchain`. No
    operator home directory is exposed (trap 13); the factory-owned per-node
    home is the only writable location beyond the worktree (trap 3).

    The process gets its own PID namespace (`--unshare-pid`) and bwrap dies with
    its parent (`--die-with-parent`) so the existing process-group kill reaches
    the whole namespaced tree (trap 2). Network is intentionally not unshared so
    the agent can reach the proxy.
    """

    name = "bwrap"

    def __init__(
        self,
        *,
        executable: str = DEFAULT_EXECUTABLE,
        system_root: Path | str = Path("/"),
    ) -> None:
        self.executable = executable
        #: The host whose system layout the mount set is read from. The real
        #: root in production; a supplied tree in a test, which is the only way
        #: to assert both the `/lib64` and the no-`/lib64` branch on one machine.
        self.system_root = Path(system_root)

    def _binary(self) -> Path:
        return BWRAP_BACKEND_BINARY

    def _platform(self) -> str:
        return "linux"

    def _toolchain(self) -> list[ResolvedTool]:
        """Discover the agent's toolchain on this host, refusing by name on a miss.

        All four are required: the previous version of this method bound all
        four unguarded, so a host missing one already could not launch — the
        difference is that it failed as ``bwrap: Can't find source path`` from a
        forked process, reaching the operator as a diffless `agent_error`
        instead of as the name of the tool that is not installed.

        Nothing here is a literal. What used to sit in this method was one
        operator's home and two version numbers, and both rotted: the agent
        runner's store held `2.1.222`, `2.1.223` and `2.1.224` while this list
        pinned the middle one, so the installer's next prune would have turned
        every dispatch into that same mount error.

        The order is load-bearing twice: it is the order the binds are listed
        in, and `container_path` derives the container's `PATH` from it. It
        matches the literal list this replaced, so on the host that ran the
        literals the assembled argv is unchanged — proven by diffing the two.
        """
        return resolve_toolchain(
            (self.executable, UV, NODE, GIT),
            purpose="the agent sandbox",
        )

    def _toolchain_binds(
        self, tools: Sequence[ResolvedTool] | None = None
    ) -> list[tuple[str, str, str]]:
        """Read-only binds for the agent's toolchain (trap 13).

        Each tuple is (bwrap flag, host source, container destination). Source
        and destination differ where the tool is a symlink: the agent runner is
        a link in the operator's home pointing into a versioned install, and
        binding the *resolved* file at the *link's* path is what keeps it from
        dangling inside the boundary while the container's `PATH` still finds
        it where it expects to.

        The second runner breaks that shape in one way (155-US4, measured on
        the real 0.153.4 tarball): an npm-installed `codex` is a JS launcher
        whose payload lives *beside it in the package tree*, which it resolves
        through `node_modules` at run time. Binding the lone launcher leaf
        leaves every payload lookup outside the namespace, and the node dies
        before writing anything — the diffless-start failure shape. The npm
        case therefore binds the whole `node_modules` tree the resolution
        walks and recreates the launcher inside it as the symlink `PATH`
        names, rather than flattening the link into a leaf.

        A runner that lives inside the system tree gets *nothing* here —
        `/usr` is already bound whole, launcher, payload and link included,
        and any entry at that path makes bwrap refuse to start (measured for
        claude in the demo container, 2026-08-26).
        """
        resolved = self._toolchain() if tools is None else tools
        binds: list[tuple[str, str, str]] = []
        for tool in resolved:
            if tool.name == CODEX_RUNNER:
                if _inside_system_tree(tool.found_at, self.system_root):
                    # npm installed it under /usr, which `system_tree_argv`
                    # binds whole: launcher, payload and PATH symlink are all
                    # already inside the namespace. Any entry at that path —
                    # above all a `--symlink` where the bound tree already
                    # carries one — makes bwrap refuse to start. Emit nothing.
                    continue
                root = npm_install_root(tool)
                if root is None:
                    # Not npm-packaged (a wrapper script, a lone binary): the
                    # leaf bind is the whole truth about that layout, so the
                    # general rule applies unchanged.
                    binds.append(("--ro-bind", *tool.bind))
                    continue
                binds.append(("--ro-bind", str(root), str(root)))
                launcher_real = tool.real_path
                if tool.found_at != launcher_real:
                    binds.append(("--symlink", str(launcher_real), str(tool.found_at)))
                continue
            binds.append(("--ro-bind", *tool.bind))
        return binds

    def _build_argv(self, invocation: AgentInvocation) -> list[str]:
        """Assemble the bwrap command from the proven mount set."""
        binary = str(self._binary())
        worktree = invocation.worktree.resolve()
        env = invocation.env
        home = Path(env.get("HOME") or worktree)
        home = home.resolve()

        # Find the target repository root from the worktree's .git file so the
        # whole parent .git directory can be bound writable for git plumbing.
        target_git_dir = self._resolve_target_git_dir(worktree)

        argv: list[str] = [
            binary,
            # The environment the child gets is BUILT, never inherited. bwrap
            # passes its own environment through by default, and this backend
            # is launched without an `env=` argument, so without this flag the
            # sandboxed agent receives the *worker's* entire environment —
            # `attempt_env`'s allowlist notwithstanding, because that dict is
            # only read for the `--setenv` values below, never applied as the
            # base. Measured 2026-08-17 on a live implementer: its `pytest`
            # child held `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` and the
            # worker unit's own systemd variables, and the live-notify smoke
            # test — which skips only on *absent* credentials — paged the
            # operator once per suite run all night. `--clearenv` must precede
            # every `--setenv`: bwrap keeps what is set after it, and clears
            # what came before.
            "--clearenv",
        ]

        # The system tree is read off the host, never declared: `/usr` bound
        # read-only, plus a symlink for each of `/bin`, `/lib`, `/lib64` and
        # `/sbin` that this host itself keeps as one, with that link's own
        # target. What stood here was a hand-written pair of entries under a
        # comment asserting which of them exist — a fact about one machine,
        # which is why the sandbox could not start on a host whose loader lives
        # in `/lib64`. Emitted before `binds`: a symlink after a bind covering
        # its path is a different bug. See `factory.verify.toolchain`.
        argv.extend(system_tree_argv(self.system_root))

        argv.extend([
            # Runtime pseudo-filesystems. Genuinely host-independent, unlike
            # the tree above.
            "--proc", "/proc",
            "--dev", "/dev",
            "--tmpfs", "/tmp",
        ])

        # Every filesystem bind is collected here and emitted by `ordered_binds`,
        # shallowest destination first, so a containing path can never overlay
        # the more specific bind inside it. Listing order below is for the
        # reader; the mount order is the helper's. See `ordered_binds` for the
        # 2026-08-15 failure that made this ordering explicit rather than
        # incidental.
        binds: list[tuple[str, str, str]] = []

        # The node worktree: only the leaf, at the same absolute path. Its
        # parent is read-only so bwrap does not create a writable intermediate
        # directory that exposes sibling worktrees (trap 9).
        binds.append(("--ro-bind", str(worktree.parent), str(worktree.parent)))
        binds.append(("--bind", str(worktree), str(worktree)))

        # The factory-owned per-node home is the only writable home. The runtime
        # root that contains it is read-only so stores and sibling worktrees
        # cannot be altered, and the home leaf is writable inside it (trap 9,
        # US3-S4). The runtime root is the parent of the `homes/` directory,
        # i.e. three levels above the node home.
        runtime_root_candidates = [home.parent, home.parent.parent, home.parent.parent.parent]
        runtime_root = next(
            (candidate for candidate in reversed(runtime_root_candidates)
             if candidate.is_dir() and candidate.name == "homes"),
            home.parent.parent.parent,
        ).parent
        if runtime_root.is_dir() and runtime_root not in (Path("/"), worktree.parent):
            binds.append(("--ro-bind", str(runtime_root), str(runtime_root)))
        binds.append(("--bind", str(home), str(home)))

        # Git plumbing: whole parent .git writable. The working tree root is
        # read-only, and depth ordering is what makes the writable `.git` and
        # the writable worktree survive inside it (trap 1, US3-S1).
        if target_git_dir is not None:
            target_worktree = target_git_dir.parent
            if target_worktree not in (worktree.parent, home):
                binds.append(("--ro-bind", str(target_worktree), str(target_worktree)))
            binds.append(("--bind", str(target_git_dir), str(target_git_dir)))

        # Read-only toolchain leaves (trap 13), plus the three things any
        # attempt that runs the repo's own suite needs. The agent runs the gate
        # command itself during its inner loop, so its mount set must carry
        # everything the gate executor's does — proven on 2026-08-15 by giving
        # the agent the boundary without them: `uv run` inside the namespace
        # died with `Temporary failure in name resolution` before a single test
        # ran. The gate executor owns the definitions; reusing them is what
        # keeps the two mount sets from drifting apart again.
        # Resolved once and used twice — for these binds and for the container
        # `PATH` below — so the mount set and the search path cannot name
        # different directories.
        tools = self._toolchain()
        binds.extend(self._toolchain_binds(tools))
        gate_boundary = BwrapGateExecutor()
        for source, dest in gate_boundary._interpreter_binds(worktree):
            binds.append(("--ro-bind", source, dest))
        for source, dest in gate_boundary._resolver_binds():
            binds.append(("--ro-bind", source, dest))
        # No declared caches are passed: this boundary is built from an agent
        # invocation, which carries no manifest, so it gets what it has always
        # got — the uv cache the gate executor's default composes (101 FR-006).
        cache_binds = gate_boundary._cache_binds()
        for cache in cache_binds:
            binds.append(("--bind", cache.source, cache.dest))

        # The executable itself, when it is an absolute path not already mounted.
        executable_bind = self._bind_executable(invocation)
        if executable_bind:
            binds.append(
                (executable_bind[0], executable_bind[1], executable_bind[2])
            )

        argv.extend(ordered_binds(binds))
        argv.extend(["--chdir", str(worktree)])
        argv.extend(["--setenv", "HOME", str(home)])
        for cache in cache_binds:
            if cache.env is not None:
                argv.extend(["--setenv", cache.env, cache.dest])

        # PATH must name the bind points inside the container; inherited PATH
        # points at host paths that may not be mounted. Derived from the same
        # resolutions the toolchain binds came from — a second list of literals
        # here was the other half of the defect, because it could name a
        # directory nothing had mounted.
        argv.extend(["--setenv", "PATH", container_path(tools)])

        # Pass through the remaining allowlisted env vars from the invocation.
        for name in PASSTHROUGH_ENV:
            if name in env and name != "PATH":
                argv.extend(["--setenv", name, env[name]])
        for name in (
            "ANTHROPIC_BASE_URL",
            "ANTHROPIC_AUTH_TOKEN",
            CLAUDE_CODE_OAUTH_TOKEN,
            "CLAUDE_CODE_MAX_CONTEXT_TOKENS",
            # 155-US1 (FR-003): Codex's two names — the key the generated
            # config.toml names as its env_key, and the per-node CODEX_HOME the
            # adapter seeds. Added to this list only because `--clearenv` makes
            # it the whole of the child env; a name absent here never reaches a
            # sandboxed Codex child (trap 6: only what the launch requires).
            CODEX_GATEWAY_KEY,
            CODEX_HOME_ENV,
            ATTEMPT_ARCHIVE_ENV,
            # Git identity and configuration are intentionally suppressed in the
            # allowlist, but the seeded `.gitconfig` in the per-node home is not
            # always enough for linked worktrees; pass the variables through
            # when the worker provides them so commit/diff succeed (US3-S2).
            "GIT_AUTHOR_NAME",
            "GIT_AUTHOR_EMAIL",
            "GIT_COMMITTER_NAME",
            "GIT_COMMITTER_EMAIL",
            "GIT_CONFIG_GLOBAL",
            "GIT_CONFIG_SYSTEM",
        ):
            if name in env:
                argv.extend(["--setenv", name, env[name]])

        # Process/signal boundary (trap 2).
        argv.extend(["--unshare-pid", "--die-with-parent"])

        # Finally the agent itself.
        argv.append("--")
        argv.extend(invocation.argv)
        return argv

    def _resolve_target_git_dir(self, worktree: Path) -> Path | None:
        """Return the parent repository's `.git` directory if this is a worktree.

        A normal git repository has `.git` as a directory. A linked worktree
        has `.git` as a file pointing at the real metadata under the parent
        repo's `.git/worktrees/<name>`. Either way the parent `.git` directory
        must be mounted writable for commit/diff to work (trap 1).
        """
        git_file = worktree / ".git"
        if not git_file.exists():
            return None
        if git_file.is_dir():
            return git_file.resolve()
        # Linked worktree: parse `gitdir: <path>`.
        try:
            text = git_file.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        prefix = "gitdir:"
        if not text.startswith(prefix):
            return None
        gitdir = Path(text[len(prefix):].strip()).resolve()
        # The worktree metadata lives under <repo>/.git/worktrees/<name>; the
        # parent repo root is the directory containing .git.
        return gitdir.parent.parent.resolve()

    def _bind_executable(self, invocation: AgentInvocation) -> list[str]:
        """Bind the agent executable itself so it is resolvable inside the namespace.

        The executable argv may be an absolute path to a script (the test stub) or
        a name found on PATH (the real `claude` CLI). An absolute path that is not
        under `/usr` or another already-mounted tree must be bound explicitly, or
        bwrap's execvp sees `No such file or directory`. A bare name is left to
        the container PATH.
        """
        argv0 = invocation.argv[0]
        if not argv0.startswith("/"):
            return []
        path = Path(argv0).resolve()
        # Already covered by a previous mount (e.g. /usr/bin/claude).
        for mounted in ("/usr",):
            if str(path).startswith(mounted):
                return []
        return ["--ro-bind", str(path), str(path)]

    async def launch(self, invocation: AgentInvocation) -> asyncio.subprocess.Process:
        binary = self._binary()
        if not binary.is_file():
            raise AdapterError(
                f"sandbox backend 'bwrap' not available: {binary} missing on "
                f"{self._platform()}"
            )

        # Toolchain discovery and system-tree derivation both happen inside
        # `_build_argv`, so a host missing a tool — or holding something at a
        # system path that can be neither mirrored nor bound — refuses here, by
        # name, before anything forks. `SystemTreeError` is a `ToolchainError`
        # so that one `except` covers both. `AdapterError` is
        # the right class for it: infrastructure the operator has to fix, never
        # a verdict, and never an attempt the ladder should spend.
        try:
            argv = self._build_argv(invocation)
        except ToolchainError as error:
            raise AdapterError(str(error)) from error

        stderr = self._stderr_sink(invocation)
        try:
            return await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=invocation.log,
                stderr=stderr,
                # cwd is still the worktree on the host side; the real chdir is
                # the `--chdir` inside the mount namespace.
                cwd=str(invocation.worktree),
                start_new_session=True,
            )
        except OSError as error:
            raise AdapterError(
                f"could not launch sandbox backend 'bwrap' for "
                f"{invocation.argv}: {error}"
            ) from error


_BACKENDS: dict[str, type[AgentBackend]] = {
    HostAgentBackend.name: HostAgentBackend,
    BwrapBackend.name: BwrapBackend,
}


# The seam (D-018) ------------------------------------------------------------


class AgentAdapter(Protocol):
    """What the factory needs from an agent runner, entire.

    One method, not the five-step decomposition contracts/adapter.md sketches
    (launch/monitor/terminate/classify/transcript): those steps are real, but
    they are steps of *one policy* — the deadline, the process-group termination,
    the reap, the archive — and a protocol that exposed them would make every new
    adapter re-implement that policy, with the FR-007 and US2-S3 guarantees
    riding on each one getting it right. Since 154-US4 that policy has one
    shared implementation (`SharedAttemptPolicy`, below); what genuinely differs
    between agents is the narrow per-CLI surface it calls into, so that is what
    a second class supplies. The outer protocol stays one method either way.
    """

    #: The persona registry's `agent` value that selects this adapter.
    name: str

    async def run_attempt(
        self,
        context: AttemptContext,
        *,
        factory_root: Path | str,
        heartbeat: Callable[[UsageSnapshot | None], Awaitable[None] | None] | None = ...,
        heartbeat_interval_s: float = ...,
        read_usage: Callable[[], Awaitable[UsageSnapshot]] | None = ...,
        poll_interval_s: float = ...,
        send_ferry_question: Callable[[str], Awaitable[str]] | None = ...,
        read_ferry_answer: Callable[[str], Awaitable[str | None]] | None = ...,
        ferry_interval_s: float = ...,
    ) -> AdapterResult: ...


def adapter_for(agent: str, **options: Any) -> AgentAdapter:
    """The adapter a persona's `agent` field names (constitution VII).

    Unknown names raise rather than falling back to Claude Code: a persona
    naming an agent the factory cannot run is a registry error, and silently
    dispatching to a different agent would produce work nobody asked for under
    a model nobody chose.
    """
    implementation = _ADAPTERS.get(agent)
    if implementation is None:
        known = ", ".join(sorted(_ADAPTERS)) or "<none>"
        raise AdapterError(
            f"no adapter for agent '{agent}' (known: {known}) — a second agent is "
            "a second class in factory/workgraph/adapter.py (D-018)"
        )
    return implementation(**options)


# Paths on the worker host (plan.md § Storage) --------------------------------


def transcript_dir(
    factory_root: Path | str, epic_id: str, node_id: str, attempt: int
) -> Path:
    """`.factory/transcripts/<epic>/<node>/attempt-<n>/` — this attempt's evidence.

    Keyed by the same `(epic, node, attempt)` identity as the virtual key and the
    ledger row, so an archived run is attributable without a lookup, and retries
    of one node never overwrite the record a retry prompt quotes (FR-006).
    """
    return Path(factory_root) / "transcripts" / epic_id / node_id / f"attempt-{attempt}"


def _preserve_previous_stdout(archive: Path, context: AttemptContext) -> None:
    """Move a previous execution's `stdout.log` aside before this one truncates it.

    The truncating open at the top of `run_attempt` destroys the one file that
    would name the cause of a repeated identifier (107 FR-013): the earlier
    execution's own refusal, sitting in the same archive directory. Before the
    open, if a non-empty `stdout.log` is already there, move it to a name that
    states which execution wrote it. The name carries the *current* execution's
    derived session id — the per-execution discriminator, since the ladder attempt
    is identical across an activity retry (trap 9) — so two executions of one
    activity never overwrite each other's preserved log. The live file keeps its
    name and meaning: `_read_stdout` and the subscription classifier read exactly
    the file they read today (plan R10).
    """
    live = archive / STDOUT_LOG_NAME
    if not live.is_file() or live.stat().st_size == 0:
        return
    preserved = archive / f"stdout-{context.session_id}.log"
    with contextlib.suppress(OSError):
        live.replace(preserved)


def pid_file(factory_root: Path | str, epic_id: str, node_id: str) -> Path:
    """`.factory/run/<epic>/<node>.pid` — the next run's handle on this one (R4).

    Keyed by node rather than attempt because the worktree is the resource being
    protected and there is exactly one per node (FR-013): whichever attempt left
    a process behind, it is *this* node's worktree it is still writing to.
    """
    return Path(factory_root) / "run" / epic_id / f"{node_id}.pid"


def home_path(factory_root: Path | str, epic_id: str, node_id: str) -> Path:
    """`.factory/homes/<epic>/<node>` — this node's own `HOME`.

    Keyed by `(factory_root, epic_id, node_id)`, the same identity as the
    worktree and the pid file, so a node's retries share one home the same way
    they share one worktree (FR-003). Per-node, not per-attempt: two concurrent
    nodes of one epic must not write one configuration file.
    """
    return Path(factory_root) / "homes" / epic_id / node_id


def _operator_home() -> Path:
    """The operator's real home directory, even when this process's HOME is synthetic.

    The adapter runs with a per-node HOME, so ``Path.home()`` would return that
    synthetic directory. The passwd entry names the operator's home, which is
    where Claude Code stored the credential. Falls back to ``Path.home()`` when
    the passwd entry is unavailable.
    """
    try:
        return Path(pwd.getpwuid(os.getuid()).pw_dir)
    except (KeyError, OSError):
        return Path.home()


def discover_subscription_credential(
    *,
    operator_home: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path | None:
    """Find the operator's Claude Code subscription credential on this host.

    The credential's location is a host fact, not a code constant. Searches, in
    order:

    1. ``$XDG_CONFIG_HOME/claude/.credentials.json``
    2. ``~/.config/claude/.credentials.json``
    3. ``~/.claude/.credentials.json`` (the path used in the 2026-08-19
       feasibility run)

    Returns ``None`` when none of those paths exist. The search is exposed with
    an optional ``operator_home`` so tests can drive discovery without touching
    the host's real home.
    """
    if operator_home is None:
        operator_home = _operator_home()
    source = os.environ if environ is None else environ

    candidates: list[Path] = []
    xdg_config = source.get("XDG_CONFIG_HOME")
    if xdg_config:
        candidates.append(Path(xdg_config) / "claude" / ".credentials.json")
    candidates.append(operator_home / ".config" / "claude" / ".credentials.json")
    candidates.append(operator_home / ".claude" / ".credentials.json")

    for path in candidates:
        if path.is_file():
            return path
    return None


def discover_codex_credential(
    *,
    operator_home: Path | None = None,
    environ: Mapping[str, str] | None = None,
    declaration: CredentialDeclaration | None = None,
) -> Path | None:
    """Find the operator's Codex subscription credential on this host.

    The location is MEASURED, not assumed (155 trap 3, 2026-09-08 on
    `codex-cli 0.153.4`): `codex login` writes `auth.json` under the CLI's
    home — `$CODEX_HOME` when the host declares one, else `~/.codex/` — and
    `codex doctor` reads the same file back as `auth storage mode: File`,
    mode 0600. The search is therefore the CLI's own resolution, in order:

    1. ``$CODEX_HOME/auth.json`` — relocation moves the whole tree (measured),
       so a worker host that declares it keeps its credential there
    2. ``~/.codex/auth.json`` — the default, the path the 2026-09-08 probe
       found the operator's ChatGPT sign-in at

    An explicit declaration disables that fallback entirely: the declared path
    is either returned or missing, never replaced by an interactive login.

    Returns ``None`` when neither exists; the caller owns the refusal, the way
    Claude's discovery's caller does.

    INHERITED HAZARD (155-US3-S3), UNMEASURED FOR CODEX: a subscription
    credential that rotates on use would rotate the operator's own sign-in,
    not this node's copy. The per-node copy prevents concurrent nodes from
    invalidating each other the way Claude's copy does, but it cannot say
    whether the first node's use refreshes — and invalidates — the operator's
    host login. That behaviour is measured for neither CLI (Claude's
    `discover_subscription_credential` carries the same caveat, and this route
    inherits it rather than claiming a measurement Codex never had).
    """
    if operator_home is None:
        operator_home = _operator_home()
    source = os.environ if environ is None else environ

    if declaration is not None:
        return declaration.source_path if declaration.source_path.is_file() else None
    candidates: list[Path] = []
    codex_home = source.get(CODEX_HOME_ENV)
    if codex_home:
        candidates.append(Path(codex_home) / "auth.json")
    candidates.append(operator_home / ".codex" / "auth.json")

    for path in candidates:
        if path.is_file():
            return path
    return None


def _credential_expiry(path: Path) -> datetime | None:
    """The recorded expiry of a copied credential, or `None` when it cannot be read.

    Reads the local file only (US2-S7 / FR-009). Returns `None` for a missing
    file, unreadable JSON, an absent `expiresAt` key, or a value that does not
    parse as an ISO timestamp — an unknown expiry is not evidence of a dead
    credential (US2-S4 / FR-008, trap 7).
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        expires_at = data.get("expiresAt")
        if not isinstance(expires_at, str):
            return None
        # Accept ISO 8601 timestamps with or without a trailing `Z`.
        normalized = expires_at.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except (OSError, ValueError, TypeError):
        return None


def _seed_node_home(home: Path, credential_path: Path | None = None) -> None:
    """Write the minimum the CLI needs to start non-interactively on this home.

    T001 found the answer is almost nothing: the CLI writes its own
    `.claude.json`, `plugins/`, `projects/`, `sessions/` and `backups/` from
    fresh defaults when given a bare writable home. The factory therefore
    writes only git identity, and it writes it from constants already owned by
    the factory's salvage path (FR-005).

    For subscription-routed personas the operator's credential is also copied
    into this home (US3 FR-007). The placement is a file copy: per-node HOMEs
    are isolated by ``(epic, node)`` so concurrent nodes do not share the same
    credential file, and the operator's stored credential is never written to
    by the agent. The refresh-token rotation behaviour of the provider has not
    been measured; if rotation-on-use is the provider's behaviour, a copy still
    prevents concurrent nodes from invalidating each other, but the operator's
    own host login may be invalidated when the first node refreshes. That
    trade-off is documented here and in the diff (US3-S6/FR-015).

    The function takes no path into the operator's home and no argument that
    could carry one: every value it writes is imported from this module or
    `factory.workgraph.worktree`, except the credential copy which arrives
    through the discovered ``credential_path``.
    """
    config = (
        "[user]\n"
        f"\tname = {_SALVAGE_AUTHOR_NAME}\n"
        f"\temail = {_SALVAGE_AUTHOR_EMAIL}\n"
    )
    (home / ".gitconfig").write_text(config, encoding="utf-8")
    if credential_path is not None:
        target = home / ".claude" / ".credentials.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(credential_path, target)
        target.chmod(0o600)


def project_dir_name(cwd: Path | str) -> str:
    """Claude Code's per-cwd transcript directory: `/home/a/b` → `-home-a-b`.

    Every non-alphanumeric character of the absolute path becomes `-`. The rule
    belongs to the CLI, not to the factory, so the factory reproduces it to find
    the file it archives (R6) and the Tier 1 smoke is what proves the two still
    agree.
    """
    return _NON_ALNUM.sub("-", str(Path(cwd).resolve()))


# The environment (US2-S1) ----------------------------------------------------


def attempt_env(
    context: AttemptContext,
    environ: Mapping[str, str] | None = None,
    *,
    routes_through_gateway: bool = True,
) -> dict[str, str]:
    """The agent's entire environment: gateway variables and the passthrough.

    An allowlist, so `LITELLM_MASTER_KEY` and `TELEGRAM_BOT_TOKEN` are absent by
    omission rather than by redaction (constitution V) — as is every other
    variable the worker happens to carry, credential or not. `ANTHROPIC_AUTH_TOKEN`
    rather than `ANTHROPIC_API_KEY`: it is the bearer-token path the LiteLLM proxy
    expects (R6).

    `HOME` is a constructed value, not a passthrough: it is the factory's
    per-node home under `factory_root` (US1), and the child receives it even when
    the worker environment carries no `HOME` at all (FR-002).

    Subscription-routed personas run against the operator's own credential via
    the CLI's normal login, so they receive neither the proxy URL nor a virtual
    key (US2 FR-006). The caller decides this with `routes_through_gateway`.
    """
    source = os.environ if environ is None else environ
    env: dict[str, str] = {
        "HOME": str(context.home_path),
    }
    if routes_through_gateway:
        env["ANTHROPIC_BASE_URL"] = context.proxy_url
        env["ANTHROPIC_AUTH_TOKEN"] = context.virtual_key
    else:
        # US1: subscription-routed personas authenticate with the operator's
        # longest-lived credential. Carry the token only in the subscription
        # branch; adding it to PASSTHROUGH_ENV would hand it to gateway personas
        # too (trap 1).
        #
        # 155-US3: the branch serves both adapters now, and the token is
        # Claude's credential. Codex subscription personas authenticate through
        # the `auth.json` their home seeding copied, so a Codex child receives
        # neither the token nor any gateway variable — the CLI would read a
        # Claude token as its own and the credential's provenance would read
        # wrong in the evidence.
        oauth_token = source.get(CLAUDE_CODE_OAUTH_TOKEN)
        if oauth_token and context.agent != CodexAdapter.name:
            env[CLAUDE_CODE_OAUTH_TOKEN] = oauth_token
    if context.context_window is not None:
        env["CLAUDE_CODE_MAX_CONTEXT_TOKENS"] = str(context.context_window)
    env.update({name: source[name] for name in PASSTHROUGH_ENV if source.get(name)})
    return env


# The shared attempt policy and its per-CLI seam (154-US4, FR-007) --------------
#
# `run_attempt` is mostly not about Claude. Pid file, orphan reap, archive
# directory, monitor loop, wall-clock deadline, operator-question ferry, backend
# resolution, standards path — none of that names a CLI, and a second adapter
# must not copy it. So the policy has exactly one implementation,
# `SharedAttemptPolicy`, and what an adapter supplies is the narrow per-CLI
# surface: argv, prompt delivery, provider env, home seeding, credential
# discovery, the turn-happened probe, refusal markers.
#
# This is an inner seam, deliberately NOT a widening of the outer protocol. The
# outer `AgentAdapter` protocol keeps its one `run_attempt` method — the
# five-method decomposition (launch/monitor/terminate/classify/transcript) that
# specs/005-workgraph-interpreter/contracts/adapter.md sketched was collapsed on
# purpose, because those steps are steps of *one policy* and a protocol that
# exposed them would make every new adapter re-implement it. The inner seam runs
# the other way: the shared policy calls *into* the adapter for the few things
# that genuinely differ, and nothing above `run_attempt` changes.


@dataclass(frozen=True)
class CredentialStage:
    """What one adapter's credential discovery found (154-US4 FR-007).

    Per-CLI because the *location* of a credential, and the format that says
    whether it is still valid, are conventions of the CLI; the *consequences* —
    seeding the home, refusing before the sandbox forks — are shared policy and
    live in `SharedAttemptPolicy`. A gateway-routed attempt discovers nothing:
    its credential is the attempt's virtual key, already carried on the context
    (constitution V).
    """

    #: True when the persona's route needs no discovered credential.
    gateway: bool
    #: The credential file this CLI reads, discovered on the worker host.
    path: Path | None = None
    #: The missing-credential refusal: infrastructure the operator fixes, so
    #: the policy raises it as an `AdapterError` — never an attempt the ladder
    #: should spend.
    error: str | None = None
    #: The no-longer-valid-credential refusal: a recorded `PRE_AGENT_FAILURE`,
    #: not an exception, because the process outcome is the classification.
    failure: str | None = None
    #: Whether the discovered credential is still valid, as the CLI's own
    #: format records validity. The policy refuses an expired one.
    expired: bool = False
    #: Where the credential came from, as the adapter's record states it
    #: (155-US3-S2). Free text by design — "which file" is a per-CLI fact, and
    #: Claude's precedence names a channel while Codex's names a path — so the
    #: policy records what the discovery declared instead of re-deriving it
    #: from a variable name only one CLI uses. `None` for a gateway attempt,
    #: whose credential is the attempt's virtual key (constitution V).
    source: str | None = None


class SharedAttemptPolicy:
    """The one implementation of the agent-agnostic attempt policy (FR-007).

    Every adapter's `run_attempt` is this class, parameterised by the per-CLI
    surface its adapter supplies. Owning it here is what makes the second
    adapter's correctness structural rather than aspirational: the pid file,
    the orphan reap, the archive, the monitor loop, the deadline, the ferry,
    the backend resolution and the standards path are written once, and an
    adapter that gets them wrong is an adapter that did not call this.

    The surface is typed loosely on purpose: what an adapter supplies is data
    and small callables — `_argv`, `_deliver_prompt`, `_provider_env`,
    `_credential`, `_seed_home`, `_turn_happened` — not orchestration steps. A
    Protocol spelling that surface would be the five-method protocol the
    implementation deliberately collapsed, wearing a different name.
    """

    def __init__(self, cli: Any) -> None:
        self._cli = cli

    async def run_attempt(
        self,
        context: AttemptContext,
        *,
        factory_root: Path | str,
        heartbeat: Callable[[UsageSnapshot | None], Awaitable[None] | None] | None = None,
        heartbeat_interval_s: float = DEFAULT_HEARTBEAT_INTERVAL_S,
        read_usage: Callable[[], Awaitable[UsageSnapshot]] | None = None,
        poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
        send_ferry_question: Callable[[str], Awaitable[str]] | None = None,
        read_ferry_answer: Callable[[str], Awaitable[str | None]] | None = None,
        ferry_interval_s: float = DEFAULT_FERRY_INTERVAL_S,
    ) -> AdapterResult:
        """Run one attempt to its end, whatever that end is.

        Returns the termination class and the archive directory, and nothing else
        (D-018). Raises `asyncio.CancelledError` on the kill path *after* the
        group is dead and the evidence is archived, so Temporal records the
        cancellation and the workflow still salvages the worktree.

        The ferry (008-US3) is two optional callables the activity wires to the
        question store: ``send_ferry_question`` ships an in-flight question up
        (the same ``send_question`` row + Telegram send the US1 path uses), and
        ``read_ferry_answer`` polls for the operator's reply. Neither is the
        adapter's concern to provide — they are the seam the monitor loop ferries
        across, the way ``read_usage`` is the seam for spend. Both are
        failure-isolated: a ferry call that raises leaves the beat and the
        deadline intact, so a question can never become a hang (FR-009).
        Absent both, no ferry runs — the US1 final-message path is the whole
        question channel, unchanged.
        """
        archive = transcript_dir(
            factory_root, context.epic_id, context.node_id, context.attempt
        )
        archive.mkdir(parents=True, exist_ok=True)
        pids = pid_file(factory_root, context.epic_id, context.node_id)
        home = Path(context.home_path)
        try:
            home.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise AdapterError(
                f"could not create per-node home for {context.epic_id}/"
                f"{context.node_id}: {home}"
            ) from error

        # 154-US4 (FR-007): credential *discovery* is the adapter's — where a
        # CLI keeps its credential is the CLI's convention — but the *decision*
        # is the shared policy's. A subscription-routed attempt needs a
        # discovered credential seeded into its per-node HOME, and a missing or
        # expired one is a named refusal before the sandbox forks. 154-US1
        # (FR-006): the route is read from the route axis; a payload that
        # predates the field is answered from the legacy `agent` sentinel by
        # `effective_route`.
        stage = self._cli._credential(context)
        credential_path = stage.path
        if not stage.gateway:
            if credential_path is None:
                raise AdapterError(stage.error or "subscription credential not found")
            if stage.expired:
                return AdapterResult(
                    termination=Termination.PRE_AGENT_FAILURE,
                    transcript_path=str(archive),
                    detail=stage.failure,
                )
        candidate_path = self._candidate_path(context, {})
        try:
            await self._reap(pids)
        except CredentialFenceFailure as error:
            return AdapterResult(
                termination=Termination.PRE_AGENT_FAILURE,
                transcript_path=str(archive),
                detail=str(error),
                owner_retained=True,
            )
        # 155-US1 (FR-003): the seed is per-CLI and may need the whole context —
        # Codex's generated `config.toml` is parameterised by the attempt's
        # proxy URL, which only the context carries. The two-argument call is
        # the seam; a CLI that seeds from the credential alone ignores it.
        self._cli._seed_home(home, credential_path, context)
        worktree = Path(context.worktree_path).resolve()
        target_repo = Path(context.target_repo) if context.target_repo else None
        # `ATTEMPT_ARCHIVE` is the one constructed env var beyond the gateway
        # variables and the four passthroughs: the agent's ferry files live in the
        # archive directory (never the worktree, where salvage would commit them —
        # FR-007), so the agent has to know where it is. Built here rather than in
        # `attempt_env` because the archive path is the adapter's knowledge,
        # derived from the same identity the transcript directory is.
        routes_through_gateway = (
            effective_route(context.route, context.agent) != ROUTE_SUBSCRIPTION
        )
        env = attempt_env(context, routes_through_gateway=routes_through_gateway)
        env = self._cli._provider_env(env, context)
        env[ATTEMPT_ARCHIVE_ENV] = str(archive)

        # US1: decide which credential source this subscription-routed attempt
        # will use, so the record can state the precedence rather than leaving it
        # to be inferred (FR-005, trap 10). Gateway personas have no credential
        # source to record here. 155-US3-S2: which strings name a source is the
        # adapter's declaration, made on the `CredentialStage` its `_credential`
        # returned — a gateway attempt discovers nothing and carries none.
        credential_source: str | None = None
        if not routes_through_gateway:
            credential_source = stage.source

        # US1: capture the target repository's tracked-file state before the agent runs.
        if target_repo is not None:
            capture_start(Path(factory_root), target_repo, context)

        _preserve_previous_stdout(archive, context)

        with self._open_invocation(
            context, worktree, target_repo, env, archive
        ) as invocation:
            backend = self._resolve_backend(worktree, target_repo)
            process = await backend.launch(invocation)
            _write_pid_file(pids, process.pid)
            feeder = asyncio.ensure_future(
                self._cli._deliver_prompt(process, context.prompt)
            )
            try:
                termination, last_snapshot = await self._monitor(
                    process,
                    timeout_s=context.timeout_s,
                    heartbeat=heartbeat,
                    interval_s=heartbeat_interval_s,
                    read_usage=read_usage,
                    poll_interval_s=poll_interval_s,
                    archive=archive,
                    send_ferry_question=send_ferry_question,
                    read_ferry_answer=read_ferry_answer,
                    ferry_interval_s=ferry_interval_s,
                    # The JSONL stream is the structural tell; startup bookkeeping
                    # and diagnostic errors never become a model turn (US2).
                    agent_took_a_turn=lambda: self._cli._turn_happened(
                        context, worktree, env
                    ),
                )
            except BaseException:
                # Cancellation (the workflow's kill) and any failure of the
                # monitor itself end identically: the process group dies and the
                # attempt keeps its evidence. Only the classification differs,
                # and on this path the workflow supplies it.
                finalization = await self._finalize_current(process, context, env)
                if finalization.retained_ownership:
                    return AdapterResult(
                        termination=Termination.AGENT_ERROR,
                        transcript_path=str(archive),
                        detail=finalization.fence_error,
                        owner_retained=True,
                    )
                self._archive_session(context, worktree, env, archive)
                _clear_pid_file(pids)
                self._archive_plain_final(env, archive)
                self._finish_raw_files(context, archive)
                if target_repo is not None:
                    compare_and_report(Path(factory_root), target_repo, context)
                raise
            finally:
                await _stop_feeding(feeder)

        try:
            finalization = await self._finalize_current(process, context, env)
        except CredentialFenceFailure as error:
            return AdapterResult(
                termination=termination,
                transcript_path=str(archive),
                detail=str(error),
                owner_retained=True,
            )
        if finalization.retained_ownership:
            return AdapterResult(
                termination=termination,
                transcript_path=str(archive),
                detail=finalization.fence_error,
                owner_retained=True,
            )
        self._archive_session(context, worktree, env, archive)
        _clear_pid_file(pids)
        self._archive_plain_final(env, archive)
        self._finish_raw_files(context, archive)
        if target_repo is not None:
            compare_and_report(Path(factory_root), target_repo, context)
        return AdapterResult(
            termination=termination,
            transcript_path=str(archive),
            last_snapshot=last_snapshot,
            credential_source=credential_source,
        )

    # -- backend resolution (011-US2), standards path, monitor, deadline,
    # reap, archive: the agent-agnostic policy, owned here alone (FR-007)

    def _resolve_backend(
        self,
        worktree: Path,
        target_repo: Path | None,
    ) -> AgentBackend:
        """Resolve the launch backend from the manifest's `runtime:` key.

        An explicitly supplied backend overrides the manifest (US4's control
        path). Otherwise the manifest is read from the worktree — the same
        committed file the gates will read — and `runtime` names the backend.
        A backend that cannot be provided is a refusal naming the backend and
        the platform, never a silent fallback to the host launch (FR-008).
        """
        if self._cli._backend is not None:
            return self._cli._backend

        manifest_dir = worktree if target_repo is None else target_repo
        try:
            manifest_path, _ = resolve_manifest_path(manifest_dir)
            runtime = load_factory_config(manifest_path).runtime
        except FactoryConfigError as error:
            raise AdapterError(str(error)) from error

        backend_class = _BACKENDS.get(runtime)
        if backend_class is None:
            known = ", ".join(sorted(_BACKENDS)) or "<none>"
            raise AdapterError(
                f"sandbox backend {runtime!r} is not supported on this platform "
                f"(known: {known})"
            )
        return backend_class(executable=self._cli.executable)

    def _archive_plain_final(self, env: Mapping[str, str], archive: Path) -> None:
        """Let per-CLI evidence provide the plain compatibility value."""
        archive_final = getattr(self._cli, "_archive_final_message", None)
        if archive_final is not None:
            archive_final(env, archive)

    def _finish_raw_files(self, context: AttemptContext, archive: Path) -> None:
        """Apply declared raw-file bounds and record their provenance."""
        if getattr(self._cli, "output_policy", None) is not InvocationOutputPolicy.SEPARATE:
            return
        status: dict[str, object] = {}
        for name in (CODEX_EVENTS_NAME, CODEX_STDERR_NAME):
            path = archive / name
            original = path.stat().st_size if path.is_file() else 0
            if original > CODEX_RAW_MAX_BYTES:
                path.write_bytes(path.read_bytes()[:CODEX_RAW_MAX_BYTES])
            retained = path.stat().st_size if path.is_file() else 0
            truncated = original > CODEX_RAW_MAX_BYTES
            status[name] = {
                "original_bytes": original,
                "retained_bytes": retained,
                "limit_bytes": CODEX_RAW_MAX_BYTES,
                "truncated": truncated,
                "completeness": "incomplete" if truncated else "complete",
            }
            os.chmod(path, 0o600)
        status_path = archive / CODEX_RAW_STATUS_NAME
        status_path.write_text(json.dumps(status), encoding="utf-8")
        os.chmod(status_path, 0o600)

    def _rotate_raw_files(self, archive: Path, context: AttemptContext) -> None:
        """Retain declared raw history for one archive without losing identity."""
        for name in (CODEX_EVENTS_NAME, CODEX_STDERR_NAME):
            path = archive / name
            if path.is_file() and path.stat().st_size > 0:
                preserved = archive / f"{Path(name).stem}-{context.session_id}{path.suffix}"
                with contextlib.suppress(OSError):
                    path.replace(preserved)
        for prefix in ("codex-events-", "codex-stderr-"):
            candidates = sorted(
                archive.glob(f"{prefix}*"),
                key=lambda path: path.stat().st_mtime_ns,
                reverse=True,
            )
            for path in candidates[CODEX_RAW_RETENTION_FILES:]:
                with contextlib.suppress(OSError):
                    path.unlink()

    @contextlib.contextmanager
    def _open_invocation(
        self,
        context: AttemptContext,
        worktree: Path,
        target_repo: Path | None,
        env: dict[str, str],
        archive: Path,
    ):
        """Open the sinks for one launch and close them after it is reaped."""
        if getattr(self._cli, "output_policy", None) is InvocationOutputPolicy.SEPARATE:
            self._rotate_raw_files(archive, context)
        with (archive / STDOUT_LOG_NAME).open("wb") as log:
            if getattr(self._cli, "output_policy", None) is InvocationOutputPolicy.SEPARATE:
                with (archive / CODEX_EVENTS_NAME).open("wb") as event_log, (
                    archive / CODEX_STDERR_NAME
                ).open("wb") as stderr_log:
                    os.chmod(archive / CODEX_EVENTS_NAME, 0o600)
                    os.chmod(archive / CODEX_STDERR_NAME, 0o600)
                    yield self._invocation(
                        context, worktree, target_repo, env, log,
                        event_log, stderr_log, InvocationOutputPolicy.SEPARATE,
                    )
                return
            yield self._invocation(
                context, worktree, target_repo, env, log,
                None, None, InvocationOutputPolicy.COMBINED,
            )

    def _invocation(
        self,
        context: AttemptContext,
        worktree: Path,
        target_repo: Path | None,
        env: dict[str, str],
        log: Any,
        event_log: Any,
        stderr_log: Any,
        output_policy: InvocationOutputPolicy,
    ) -> AgentInvocation:
        if output_policy is InvocationOutputPolicy.SEPARATE:
            return AgentInvocation(
                argv=self._cli._argv(context),
                prompt=context.prompt,
                worktree=worktree,
                env=env,
                log=event_log,
                stderr_log=stderr_log,
                output_policy=output_policy,
                standards_path=self._standards_path(worktree, target_repo),
                model_alias=context.model_alias,
            )
        return AgentInvocation(
            argv=self._cli._argv(context),
            prompt=context.prompt,
            worktree=worktree,
            env=env,
            log=log,
            output_policy=output_policy,
            standards_path=self._standards_path(worktree, target_repo),
            model_alias=context.model_alias,
        )

    def _standards_path(
        self,
        worktree: Path,
        target_repo: Path | None,
    ) -> str | None:
        """The standards document the target repo declared, if any.

        Read from the same manifest the backend is resolved from, so the fake
        backend in the parity test receives the same path prompt assembly will
        point the agent at. A broken manifest is treated as "no standards" here;
        the gate runner will surface it as a CONFIG_ERROR separately.
        """
        manifest_dir = worktree if target_repo is None else target_repo
        try:
            manifest_path, _ = resolve_manifest_path(manifest_dir)
            return load_factory_config(manifest_path).standards
        except FactoryConfigError:
            return None

    # -- monitor and terminate (R2) -------------------------------------------

    async def _monitor(
        self,
        process: asyncio.subprocess.Process,
        *,
        timeout_s: int,
        heartbeat: Callable[[UsageSnapshot | None], Awaitable[None] | None] | None,
        interval_s: float,
        read_usage: Callable[[], Awaitable[UsageSnapshot]] | None,
        poll_interval_s: float,
        archive: Path,
        send_ferry_question: Callable[[str], Awaitable[str]] | None,
        read_ferry_answer: Callable[[str], Awaitable[str | None]] | None,
        ferry_interval_s: float,
        agent_took_a_turn: Callable[[], bool] | None = None,
    ) -> tuple[Termination, UsageSnapshot | None]:
        """Wait for the agent, beating as it goes, and end it at its deadline.

        The wait is chopped into heartbeat-sized pieces rather than one long
        `wait_for`: the beat is what keeps the activity alive in Temporal's eyes
        and what lets a cancellation land within a beat instead of at the
        deadline.

        Observation rides the beat (plan US1): every `poll_interval_s` the proxy
        is read once for the attempt's spend so far, and the newest snapshot (or
        `None` before any reading succeeded) is carried as the beat's details. A
        read that raises leaves the previous snapshot in place and the beat still
        fires — liveness and spend share one channel, and spend must never be
        able to kill liveness (constitution V).

        The ferry rides the beat too (008-US3): the monitor loop watches the
        archive directory for a `question` file the in-flight agent writes, ships
        it up once through ``send_ferry_question``, and then polls
        ``read_ferry_answer`` on its own (slower) cadence, writing the answer back
        to an `answer` file the agent polls. The ferry is the same isolation the
        usage read is: a raising send or poll leaves the beat and the deadline
        intact, so a question can never become a hang or a timeout burn (FR-009).
        The agent, not the adapter, bounds the ferry window — it proceeds to the
        US1 final-message path when its own wait elapses, so the adapter's only
        ferry duty is to carry the question up and the answer down, never to
        decide when a question is over.
        """
        loop = asyncio.get_running_loop()
        started = loop.time()
        deadline = started + timeout_s
        exited = asyncio.ensure_future(process.wait())

        snapshot: UsageSnapshot | None = None
    # The first read waits one full poll interval, so the first beat (one
    # heartbeat interval in) necessarily carries `None` — the attempt has
    # not been measured yet (constitution V: unknown, not zero).
        next_read = loop.time() + poll_interval_s

        ferry = _FerryState(archive=archive)
    # The first answer poll is eligible the beat a question ships: the
    # cadence starts when the question is in flight, not at attempt start,
    # so a fast answer does not wait a full interval it would never need.
        next_ferry_read = 0.0

        try:
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                try:
                    await asyncio.wait_for(
                        asyncio.shield(exited), timeout=min(interval_s, remaining)
                    )
                except (asyncio.TimeoutError, TimeoutError):
                    now = loop.time()
                    if read_usage is not None and now >= next_read:
                        # A dead spend read must not kill liveness: keep the
                        # previous snapshot and let the beat fire anyway.
                        try:
                            snapshot = await read_usage()
                        except BaseException:
                            pass
                        next_read = now + poll_interval_s
                    # The ferry: a dead ferry call must not kill liveness either
                    # (FR-009). A question ships up once; an answer polls on its
                    # own cadence. Both are isolated the way the usage read is.
                    polled = await self._ferry_once(
                        ferry,
                        send_ferry_question=send_ferry_question,
                        read_ferry_answer=read_ferry_answer,
                        now=now,
                        next_read=next_ferry_read,
                    )
                    if polled:
                        next_ferry_read = now + ferry_interval_s
                    if heartbeat is not None:
                        await _invoke_heartbeat(heartbeat, snapshot)
                    continue
                return (
                    (
                        Termination.COMPLETED
                        if process.returncode == 0
                        else _failure_class(
                            elapsed_s=loop.time() - started,
                            agent_took_a_turn=agent_took_a_turn,
                        )
                    ),
                    snapshot,
                )
        except BaseException:
            exited.cancel()
            raise

        return Termination.TIMEOUT, snapshot

    async def _ferry_once(
        self,
        state: _FerryState,
        *,
        send_ferry_question: Callable[[str], Awaitable[str]] | None,
        read_ferry_answer: Callable[[str], Awaitable[str | None]] | None,
        now: float,
        next_read: float,
    ) -> bool:
        """One beat's worth of the ferry, fully isolated from liveness.

        Ships the question up the first time its file appears (and only then),
        and polls for the answer on the ferry cadence once a question is in
        flight. Every callable is wrapped: a raise leaves the state where it was
        and the beat still fires — the ferry can improve the round trip or
        degrade to the US1 path, but it can never hang the attempt (FR-009).

        Returns whether an answer poll ran this beat, so the caller throttles the
        next poll to ``ferry_interval_s`` only when a poll actually happened (a
        beat that shipped a question but did not poll keeps the cadence at
        "eligible now"). The two callables are independent: a question ships if a
        sender is wired, an answer polls if a reader is wired — either half may
        be absent (the US1-only path wires neither, and a sender-only path is a
        question that ferries up with no round trip back through the store).
        """
    # Ship the question up the moment its file appears, once.
        if send_ferry_question is not None and state.question_id is None:
            question = state.read_question()
            if question is not None:
                try:
                    state.question_id = await send_ferry_question(question)
                except BaseException:
                    # A failed send is not a hang: the agent keeps polling and
                    # degrades to the US1 path when its window elapses. Leave
                    # `question_id` unset so the next beat tries the send again.
                    pass

    # Poll for the answer on the ferry's own cadence, once a question is up.
        if (
            read_ferry_answer is None
            or state.question_id is None
            or state.answer_written
            or now < next_read
        ):
            return False
        try:
            answer = await read_ferry_answer(state.question_id)
        except BaseException:
            # A failed read is not a hang either: keep polling, keep beating.
            return True
        if answer is not None:
            state.write_answer(answer)
        return True

    async def _reclaim(self, process: asyncio.subprocess.Process) -> None:
        """SIGTERM the agent's process group, then SIGKILL what survives.

        The KILL is sent even when the agent exited politely on TERM: its
        children share the group, outlive it, and go on writing into the node's
        worktree until they are gone (002's gate runner, same reasoning).
        """
        _signal_group(process.pid, signal.SIGTERM)
        with contextlib.suppress(asyncio.TimeoutError, TimeoutError):
            await asyncio.wait_for(process.wait(), timeout=self._cli.grace_s)
        _signal_group(process.pid, signal.SIGKILL)
        await process.wait()

    async def _prove_group_dead(self, pgid: int) -> bool:
        """Return whether the whole group is gone after its final signal."""
        deadline = asyncio.get_running_loop().time() + self._cli.grace_s
        while _group_alive(pgid) and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.01)
        return not _group_alive(pgid)

    async def _finalize_current(
        self,
        process: asyncio.subprocess.Process,
        context: AttemptContext,
        env: Mapping[str, str],
    ) -> CredentialFinalization:
        """Terminate the current group and prove it dead before a final read."""
        candidate_path = self._candidate_path(context, env)

        async def terminate() -> None:
            await self._reclaim(process)

        async def prove() -> None:
            if not await self._prove_group_dead(process.pid):
                raise CredentialFenceFailure(
                    f"could not prove current process group {process.pid} died"
                )

        return await finalize_current_candidate(
            terminate,
            prove,
            lambda candidate: candidate,
            candidate_path,
            generation=context.attempt,
            quarantine=getattr(self._cli, "_quarantine_candidate", None),
        )

    def _candidate_path(self, context: AttemptContext, env: Mapping[str, str]) -> Path:
        resolver = getattr(self._cli, "_credential_candidate", None)
        if resolver is None:
            return Path(env.get(ATTEMPT_ARCHIVE_ENV, "."))
        resolved = resolver(context, env)
        return resolved if resolved is not None else Path(env.get(ATTEMPT_ARCHIVE_ENV, "."))

    # -- reap an orphan (R4) --------------------------------------------------

    async def _reap(self, pids: Path) -> None:
        """End the process group a previous run left behind, if it is still there.

        A precaution, not a gate: an unreadable, empty or nonsensical pid file is
        exactly what a worker killed mid-write leaves, and it must not cost the
        node its attempt. `0` is refused explicitly — `killpg(0, …)` means *this*
        process group, which is the worker's own.
        """
        pgid = _read_pgid(pids)
        if pgid is None or not _group_alive(pgid):
            return

        _signal_group(pgid, signal.SIGKILL)
        await asyncio.sleep(0.01)
        if _group_alive(pgid):
            raise CredentialFenceFailure(
                f"could not prove previous process group {pgid} died"
            )
        with contextlib.suppress(OSError):
            pids.unlink()

    # -- archive (FR-007) -----------------------------------------------------

    def _archive_session(
        self,
        context: AttemptContext,
        worktree: Path,
        env: Mapping[str, str],
        archive: Path,
    ) -> None:
        """Copy the agent's session transcript in beside `stdout.log`.

        A copy, not a move: the agent's own history stays where it put it. From
        the *child's* `HOME`, because that is the home the transcript was written
        under. An agent that wrote no transcript is not an error — the log is
        still evidence — and neither is a copy that fails: losing the archive
        step to an unwritable disk would cost a finished attempt its
        classification and buy a re-run of the agent.

        Where the transcript lives is per-CLI (`_transcripts`): Claude names one
        file after the session id it was given; Codex names its rollouts after
        ids it generated itself, under a date-keyed tree in `CODEX_HOME` — so
        the archive copies every file the adapter's list names, and invents
        none.
        """
        for source in self._cli._transcripts(context, worktree, env):
            if not source.is_file():
                continue
            with contextlib.suppress(OSError):
                shutil.copy2(source, archive / source.name)


# The first adapter (R6) ------------------------------------------------------


class ClaudeCodeAdapter:
    """`claude -p --dangerously-skip-permissions --model <alias> --session-id <uuid>`.

    The prompt arrives on **stdin**: assembled prompts run to hundreds of
    kilobytes and argv has a limit. The model alias travels from the persona
    registry through argv untouched — this class names no model (constitution
    VII) — and the session id, generated by the workflow with `workflow.uuid4()`,
    is what makes the transcript discoverable afterwards, since Claude Code names
    the file after it.

    `executable` and `grace_s` are constructor arguments for the tests' benefit
    (a stub agent, and a grace short enough to observe): in production nothing
    configures them, and the deadline itself is always the persona registry's
    (FR-010).
    """

    name = "claude-code"

    def __init__(
        self,
        *,
        executable: str = DEFAULT_EXECUTABLE,
        grace_s: float = DEFAULT_GRACE_S,
        backend: AgentBackend | None = None,
    ) -> None:
        self.executable = executable
        self.grace_s = grace_s
        self._backend = backend

    async def run_attempt(
        self,
        context: AttemptContext,
        *,
        factory_root: Path | str,
        heartbeat: Callable[[UsageSnapshot | None], Awaitable[None] | None] | None = None,
        heartbeat_interval_s: float = DEFAULT_HEARTBEAT_INTERVAL_S,
        read_usage: Callable[[], Awaitable[UsageSnapshot]] | None = None,
        poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
        send_ferry_question: Callable[[str], Awaitable[str]] | None = None,
        read_ferry_answer: Callable[[str], Awaitable[str | None]] | None = None,
        ferry_interval_s: float = DEFAULT_FERRY_INTERVAL_S,
    ) -> AdapterResult:
        """Run one attempt to its end, whatever that end is.

        The whole body is the shared policy (FR-007): this delegate supplies
        the per-CLI surface to it and answers for nothing else. Returns the
        termination class and the archive directory, and nothing else (D-018).
        Raises `asyncio.CancelledError` on the kill path *after* the group is
        dead and the evidence is archived, so Temporal records the cancellation
        and the workflow still salvages the worktree.
        """
        return await SharedAttemptPolicy(self).run_attempt(
            context,
            factory_root=factory_root,
            heartbeat=heartbeat,
            heartbeat_interval_s=heartbeat_interval_s,
            read_usage=read_usage,
            poll_interval_s=poll_interval_s,
            send_ferry_question=send_ferry_question,
            read_ferry_answer=read_ferry_answer,
            ferry_interval_s=ferry_interval_s,
        )
    # -- the per-CLI surface (FR-007) -----------------------------------------

    def _argv(self, context: AttemptContext) -> list[str]:
        """The invocation, as the child receives it (R6)."""
        return [
            self.executable,
            "-p",
            "--dangerously-skip-permissions",
            "--model",
            context.model_alias,
            "--session-id",
            context.session_id,
        ]

    def _provider_env(self, env: dict[str, str], context: AttemptContext) -> dict[str, str]:
        """The CLI's own variable name, on top of the constructed environment.

        `attempt_env` (shared policy) builds the proxy URL, the virtual key, the
        per-node `HOME` and the passthrough; the context-window declaration is
        Claude Code's own spelling of the idea (FR-010)."""
        if context.context_window is not None:
            env["CLAUDE_CODE_MAX_CONTEXT_TOKENS"] = str(context.context_window)
        return env

    async def _deliver_prompt(self, process: asyncio.subprocess.Process, prompt: str) -> None:
        """Claude Code reads its prompt on stdin: write it and close the pipe."""
        await _feed_prompt(process, prompt)

    def _credential(self, context: AttemptContext) -> CredentialStage:
        """Discover this CLI's credential for the attempt's route.

        Gateway personas need nothing discovered — the attempt's virtual key is
        the credential (constitution V). A subscription-routed attempt runs on
        the operator's own login, whose location is this CLI's convention: the
        search is `discover_subscription_credential`, and whether a found
        credential is still valid is read from the CLI's own expiry format."""
        if effective_route(context.route, context.agent) != ROUTE_SUBSCRIPTION:
            return CredentialStage(gateway=True)
        credential_path = discover_subscription_credential()
        if credential_path is None:
            operator_home = _operator_home()
            return CredentialStage(
                gateway=False,
                path=None,
                error=(
                    "subscription credential not found: no .claude/.credentials.json "
                    f"under {operator_home / '.claude'} or XDG_CONFIG_HOME. "
                    "Run `claude auth login` on the worker host."
                ),
            )
        # US2 FR-007/FR-009: a copied credential whose recorded expiry has
        # passed and that is the only credential available is refused before
        # the sandbox forks. The long-lived token is checked first in
        # `attempt_env`, so if one is configured the file expiry is irrelevant.
        expires_at = _credential_expiry(credential_path)
        expired = (
            expires_at is not None
            and expires_at <= datetime.now(timezone.utc)
            and not os.environ.get(CLAUDE_CODE_OAUTH_TOKEN)
        )
        # The precedence the env carries is the source the record names:
        # `attempt_env` delivers the token when the worker has one (US1
        # FR-005), else the copy this stage seeds (US3 FR-007).
        token_configured = os.environ.get(CLAUDE_CODE_OAUTH_TOKEN) is not None
        return CredentialStage(
            gateway=False,
            path=credential_path,
            expired=expired,
            source=(
                CREDENTIAL_SOURCE_OAUTH_TOKEN
                if token_configured
                else CREDENTIAL_SOURCE_COPIED_CREDENTIALS
            ),
            failure=(
                f"subscription credential expired at {expires_at.isoformat()}: "
                "the copied interactive credential is no longer valid. "
                "Remedies: run `claude auth login` on the worker host, or "
                f"set {CLAUDE_CODE_OAUTH_TOKEN} to a long-lived token from "
                "`claude setup-token`."
            ) if expires_at is not None else None,
        )

    def _seed_home(self, home: Path, credential_path: Path | None, context: AttemptContext | None = None) -> None:
        """Seed the per-node home with what this CLI needs to start (US3 FR-007).

        The context is part of the seam since 155 (FR-003): a CLI whose
        configuration is generated from the attempt's routing needs it; Claude's
        seeding needs only the credential and takes none.
        """
        _seed_node_home(home, credential_path)

    def _transcripts(
        self, context: AttemptContext, worktree: Path, env: Mapping[str, str]
    ) -> list[Path]:
        """The session files this CLI writes, as this CLI spells the location."""
        transcript = session_transcript(context, worktree, env)
        return [transcript] if transcript is not None else []

    def _turn_happened(self, context: AttemptContext, worktree: Path, env: Mapping[str, str]) -> bool:
        """The structural tell that a turn ran (095-US1), as this CLI writes it."""
        return _wrote_session_transcript(context, worktree, env)

    def _refusal_markers(self) -> tuple[str, ...]:
        """stdout markers that mean this CLI refused rather than merely failed.

        Read by the activity layer, which owns interpreting them (FR-012): the
        adapter classifies by process outcome, and these name *why* a non-zero
        exit was a refusal. Measured strings — see each constant."""
        return (SUBSCRIPTION_REFUSAL_MARKER, SESSION_ID_REFUSAL_MARKER)


# The second adapter (155-US1, D-018's promise kept) ----------------------------


#: The env var that carries the attempt's virtual key into a Codex launch: the
#: generated `config.toml` names it as the gateway provider's `env_key`, so
#: the key never lands on disk and the CLI reads it from its own env (measured
#: 2026-09-08: unset, the CLI refuses naming it). Every new env name goes on
#: the standing boundary's `--setenv` contract — under bwrap that is the whole
#: env after `--clearenv` — or it never reaches the child.
CODEX_GATEWAY_KEY = "CODEX_GATEWAY_KEY"

#: The env var naming the per-node CODEX_HOME the adapter seeds. The CLI reads
#: it directly (measured: with it set, session files land under it and NOT
#: under `$HOME/.codex`), which is what keeps concurrent nodes' session trees
#: isolated per node the way per-node `HOME`s already are.
CODEX_HOME_ENV = "CODEX_HOME"

#: The provider id the generated `config.toml` declares. A stable local name —
#: the persona's alias names the model, this names the route.
CODEX_GATEWAY_PROVIDER = "ergane-gateway"

#: The provider label the generated `config.toml` carries. Cosmetic to the CLI;
#: named once so the generated file has one spelling.
CODEX_GATEWAY_PROVIDER_NAME = "Ergane LiteLLM gateway"

#: The wire format Codex speaks to the gateway (plan trap 5): P1 proved the
#: proxy serves `/v1/responses`, and the US1 probe then proved the CLI
#: end-to-end on it (2026-09-08, real usage through 0.153.4). `chat`
#: acceptance is unresolved; probe before relying on it.
CODEX_WIRE_API = "responses"

#: The marker that means a Codex run refused the credential — the measured
#: analogue of `SUBSCRIPTION_REFUSAL_MARKER` (155-US2; measured 2026-09-08).
#: Codex prints its refusals on **stderr** with exit 1 — the inverse of Claude
#: Code — and this substring is the stable part across the measured shapes
#: (no credential, invalid gateway key; an unset key yields a different line
#: the key-mint path prevents by construction). The adapter's log is
#: stdout+stderr interleaved, so the marker matches that combined stream.
CODEX_REFUSAL_MARKER = "unexpected status 401 Unauthorized"

#: The argv flag that disables Codex's own sandbox and approval prompts. The
#: factory's boundary (bwrap, US4) is what confines the node; a Codex CLI told
#: to enforce its read-only default inside it would refuse every write the
#: story needs. "Intended solely for running in environments that are
#: externally sandboxed" — this is that environment.
#:
#: UNANSWERED HAZARD (155-US4-S3, tied to the operator's sandbox-boundary
#: decision, recorded 2026-09-06): whether Codex's own Landlock/seccomp
#: sandbox nests inside the factory's bwrap jail is neither assumed to work
#: nor assumed to fail — deliberately unprobed, because the operator is
#: weighing moving away from bwrap entirely and P4 was deferred rather than
#: answered. What this story relies on is only the outer confinement plus the
#: bypass flag; if the operator replaces bwrap, this record moves with the
#: boundary that supersedes it, and the nesting question must be re-opened
#: there, not silently closed.
CODEX_BYPASS_FLAG = "--dangerously-bypass-approvals-and-sandbox"

#: Codex refuses to run outside a git repository without this flag (measured:
#: "Not inside a trusted directory…", exit 1, stderr). A node worktree is a
#: real git worktree, but a test's fixture is a plain directory; the launch
#: does not depend on which one it is handed.
CODEX_SKIP_GIT_CHECK_FLAG = "--skip-git-repo-check"


class CodexAdapter:
    """`codex exec --model <alias> --dangerously-bypass-approvals-and-sandbox
    --skip-git-repo-check --cd <worktree> -`, prompt on stdin.

    The second CLI behind 154's seam, and the first non-Claude value the
    registry's `agent` axis takes. Everything agent-agnostic is the shared
    policy's; this class supplies only the per-CLI surface, selected by the
    persona's `agent: codex` (154-US3).

    Three measured facts shape it (US1's probe, 2026-09-08, 0.153.4): the
    trailing `-` puts the prompt on stdin (the same delivery Claude's `-p`
    uses, closed by the same `_feed_prompt`); provider routing lives in a
    generated `config.toml` in the per-node `CODEX_HOME` (FR-003, D-048 — no
    control-plane config), declaring the gateway parameterised by the attempt's
    proxy URL with `CODEX_GATEWAY_KEY` as its `env_key`, so the key travels in
    the environment, never on disk; and there is no `--session-id` analogue
    (trap 4, measured) — Codex generates its own id, the workflow's id names
    the archive and nothing the CLI receives, and the turn probe is the
    rollout tree's existence, not one known filename.
    """

    name = "codex"

    output_policy = InvocationOutputPolicy.SEPARATE

    def __init__(
        self,
        *,
        executable: str = "codex",
        grace_s: float = DEFAULT_GRACE_S,
        backend: AgentBackend | None = None,
    ) -> None:
        self.executable = executable
        self.grace_s = grace_s
        self._backend = backend

    async def run_attempt(
        self,
        context: AttemptContext,
        *,
        factory_root: Path | str,
        heartbeat: Callable[[UsageSnapshot | None], Awaitable[None] | None] | None = None,
        heartbeat_interval_s: float = DEFAULT_HEARTBEAT_INTERVAL_S,
        read_usage: Callable[[], Awaitable[UsageSnapshot]] | None = None,
        poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
        send_ferry_question: Callable[[str], Awaitable[str]] | None = None,
        read_ferry_answer: Callable[[str], Awaitable[str | None]] | None = None,
        ferry_interval_s: float = DEFAULT_FERRY_INTERVAL_S,
    ) -> AdapterResult:
        """Run one attempt to its end, whatever that end is.

        The whole body is the shared policy (FR-007): this delegate supplies
        the per-CLI surface to it and answers for nothing else.
        """
        return await SharedAttemptPolicy(self).run_attempt(
            context,
            factory_root=factory_root,
            heartbeat=heartbeat,
            heartbeat_interval_s=heartbeat_interval_s,
            read_usage=read_usage,
            poll_interval_s=poll_interval_s,
            send_ferry_question=send_ferry_question,
            read_ferry_answer=read_ferry_answer,
            ferry_interval_s=ferry_interval_s,
        )

    # -- the per-CLI surface (FR-007) -----------------------------------------

    def _argv(self, context: AttemptContext) -> list[str]:
        """The invocation, as the child receives it (FR-004).

        `exec` for non-interactive, `--json` for the machine-readable stream,
        `-` for the stdin prompt, `--model` for
        the persona's alias, the bypass flag because the factory's boundary is
        the confinement, `--skip-git-repo-check` because repository shape is
        not the factory's contract, and `--cd` for the node worktree."""
        return [
            self.executable,
            "exec",
            "--json",
            "--model",
            context.model_alias,
            CODEX_BYPASS_FLAG,
            CODEX_SKIP_GIT_CHECK_FLAG,
            "--cd",
            str(Path(context.worktree_path).resolve()),
            "-",
        ]

    def _provider_env(self, env: dict[str, str], context: AttemptContext) -> dict[str, str]:
        """The CLI's own variable names, on top of the constructed environment.

        The gateway key `attempt_env` already built is *renamed* here, not
        re-read from the context: the credential's one assembly site stays
        `attempt_env`, and this seam only re-spells it the way the generated
        `config.toml` names it. `CODEX_HOME` points at the seeded per-node
        home — canonicalised to the absolute location the declaration already
        names, because the child is about to change directory into the node
        worktree and a relative value would re-resolve there (164 FR-001);
        Claude's variables are dropped — a Codex child has no use for a
        credential pair its config never consults.
        """
        key = env.pop("ANTHROPIC_AUTH_TOKEN", None)
        if key is not None:
            env[CODEX_GATEWAY_KEY] = key
        env.pop("ANTHROPIC_BASE_URL", None)
        env.pop("CLAUDE_CODE_MAX_CONTEXT_TOKENS", None)
        env[CODEX_HOME_ENV] = str(resolve_codex_home(context.home_path))
        return env

    async def _deliver_prompt(self, process: asyncio.subprocess.Process, prompt: str) -> None:
        """`codex exec -` reads its prompt on stdin: write it and close the pipe."""
        await _feed_prompt(process, prompt)

    def _credential(self, context: AttemptContext) -> CredentialStage:
        """Discover this CLI's credential for the attempt's route.

        Gateway personas need nothing discovered — the attempt's virtual key is
        the credential (constitution V), travelling in the env the generated
        config names. A subscription persona runs on the operator's own ChatGPT
        sign-in (155-US3, FR-006): `auth.json` at the location the CLI itself
        resolves (measured, trap 3), discovered by
        `discover_codex_credential` and missing-credential refused by name —
        the seam Claude's discovery refuses at, never a fallback to the
        gateway no persona asked for."""
        if effective_route(context.route, context.agent) != ROUTE_SUBSCRIPTION:
            return CredentialStage(gateway=True)
        credential_path = discover_codex_credential()
        if credential_path is None:
            operator_home = _operator_home()
            return CredentialStage(
                gateway=False,
                path=None,
                error=(
                    "codex subscription credential not found: no auth.json under "
                    f"{codex_home_path(operator_home)} or $CODEX_HOME. "
                    "Run `codex login` on the worker host."
                ),
            )
        validation = validate_codex_credential(
            CredentialDeclaration(
                owner_id="codex-factory",
                source_path=credential_path,
                generation=1,
            ),
            now=datetime.now(timezone.utc),
        )
        if not validation.admitted:
            return CredentialStage(
                gateway=False,
                path=None,
                error=validation.refusal,
            )
        return CredentialStage(
            gateway=False,
            path=credential_path,
            source=(
                credential_provenance_json(validation.provenance)
                if validation.provenance is not None
                else None
            ),
        )

    def _seed_home(
        self, home: Path, credential_path: Path | None, context: AttemptContext | None = None
    ) -> None:
        """Seed the per-node home: git identity plus the route's own config.

        The git identity is seeded the way Claude's is (FR-005). The route
        decides the rest (FR-003 vs FR-006): a gateway attempt gets the
        generated `config.toml` declaring the gateway provider, parameterised
        by the proxy URL with the key left to `env_key`; a subscription attempt
        gets the discovered `auth.json` copied into the per-node CODEX_HOME and
        no provider config at all — the CLI's own default provider reads that
        file, and a gateway declaration whose `env_key` names a variable the
        subscription never sets would refuse the launch (measured, US2
        evidence shape 2)."""
        # The git identity is seeded on both routes (FR-005): salvage owns
        # every Codex commit, whichever credential produced it. `None` for the
        # credential — `_seed_node_home`'s copy is Claude's placement, and an
        # auth.json under `.claude/` is a file no Codex CLI reads.
        _seed_node_home(home, None)
        # 164 FR-003: seeding, child execution, turn detection and archiving
        # agree on one identity — the absolute child-facing home, at this
        # seeding boundary before any cwd change. Seeding at the canonical
        # location is what makes the directory the child's canonicalised
        # CODEX_HOME names already exist.
        seed_target = resolve_codex_home(home)
        if context is not None and (
            effective_route(context.route, context.agent) != ROUTE_SUBSCRIPTION
        ):
            _seed_codex_config(seed_target, context)
            return
        elif credential_path is not None:
            with contextlib.suppress(FileNotFoundError):
                (seed_target / "config.toml").unlink()
            target = seed_target / "auth.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(credential_path, target)
            target.chmod(0o600)

    def _transcripts(
        self, context: AttemptContext, worktree: Path, env: Mapping[str, str]
    ) -> list[Path]:
        """The session files this CLI writes, as this CLI spells the location.

        Codex names its rollouts after ids it generated itself (trap 4,
        measured), under a date-keyed tree in `CODEX_HOME`. Only a rollout whose
        decoded identity matches the current attempt's stream may be archived."""
        current = self._current_thread(env)
        if current is None:
            return []
        return [
            path
            for path in _codex_rollouts(env)
            if self._rollout_thread(path) == current
        ]

    def _credential_candidate(
        self, context: AttemptContext, env: Mapping[str, str] | None = None
    ) -> Path:
        """The route-specific file whose bytes may only be read after fencing."""
        codex_home = codex_home_path(context.home_path)
        if effective_route(context.route, context.agent) != ROUTE_SUBSCRIPTION:
            return codex_home / "config.toml"
        return codex_home / "auth.json"

    def _quarantine_candidate(self, candidate: object) -> None:
        path = getattr(candidate, "path")
        quarantine = path.parent / "quarantine" / str(getattr(candidate, "generation"))
        quarantine.mkdir(mode=0o700, parents=True, exist_ok=True)
        target = quarantine / path.name
        suffix = 1
        while target.exists():
            target = quarantine / f"{path.name}.{suffix}"
            suffix += 1
        path.replace(target)

    def _archive_final_message(
        self, env: Mapping[str, str], archive: Path
    ) -> None:
        """Keep neutral consumers on plain text: the last agent message only.

        A stream that never decoded as JSONL can still carry the legacy plain
        CLI output; preserving that value keeps the older adapter contracts
        readable without publishing a valid raw Codex event stream.
        """
        try:
            evidence = self._current_evidence(env)
            plain_log = archive / STDOUT_LOG_NAME
            legacy_raw = (archive / CODEX_EVENTS_NAME).read_bytes()
            if evidence.final_message is not None:
                plain_log.write_text(f"{evidence.final_message.text}\n", encoding="utf-8")
            elif any(reason.code == INVALID_JSON for reason in evidence.reasons) and (
                evidence.thread_id is None and b'"type"' not in legacy_raw
            ):
                plain_log.write_bytes(legacy_raw)
        except (AttributeError, OSError):
            pass

    def _turn_happened(self, context: AttemptContext, worktree: Path, env: Mapping[str, str]) -> bool:
        """The structural tell that a turn ran (095-US1), as Codex writes it.

        The current JSONL stream, not the rollout tree, decides whether model-
        authored activity occurred. Startup bookkeeping and diagnostic errors
        do not become evidence of a turn (US2 FR-006)."""
        return self._current_evidence(env).agent_took_a_turn

    def _current_evidence(self, env: Mapping[str, str]):
        archive = env.get(ATTEMPT_ARCHIVE_ENV)
        if not archive:
            return decode_codex_events(())
        try:
            raw = (Path(archive) / CODEX_EVENTS_NAME).read_bytes()
        except OSError:
            return decode_codex_events(())
        return decode_codex_events(raw.splitlines(keepends=True))

    def _current_thread(self, env: Mapping[str, str]) -> str | None:
        return self._current_evidence(env).thread_id

    def _rollout_thread(self, path: Path) -> str | None:
        try:
            return decode_codex_events(path.read_bytes().splitlines(keepends=True)).thread_id
        except OSError:
            return None

    def _refusal_markers(self) -> tuple[str, ...]:
        """Markers that mean this CLI refused rather than merely failed.

        Measured on stderr with exit 1 (the inverse of Claude Code); the
        adapter's log is stdout+stderr interleaved, so the marker is matched on
        the combined stream. See `CODEX_REFUSAL_MARKER`."""
        return (CODEX_REFUSAL_MARKER,)


def codex_home_path(home_path: Path | str) -> Path:
    """The per-node CODEX_HOME: `<node home>/.codex` (FR-003)."""
    return Path(home_path) / ".codex"


def resolve_codex_home(home_path: Path | str) -> Path:
    """The child-facing CODEX_HOME: the declared per-node home, absolute.

    The workflow declares the per-node home with the *relative* runtime root
    it resolves against the worker's working directory (`home_path(
    DEFAULT_RUNTIME_ROOT, …)` is `.ergane/homes/<epic>/<node>`), and the
    activity seeds that directory there. The child then changes directory
    into the node worktree — a relative CODEX_HOME would re-resolve against
    the worktree and name a directory that does not exist (the 164 incident:
    four 131/147 launches refused with `CODEX_HOME points to
    ".ergane/homes/…", but that path does not exist`).

    This is the one canonicalisation point, on the adapter's activity-side
    preparation path (FR-001): the seeded directory is *identified*, not
    relocated — the absolute location is the one the relative declaration
    already named. It derives nothing from the child worktree, the operator's
    HOME, the checkout branch, an environment override or any other fallback
    (constitution IX): an already-absolute home resolves to itself, and an
    absent base is refused by name rather than guessed at.

    Kept beside `codex_home_path` and used by every consumer of the
    identity — `_provider_env`, `_seed_home`, and through the constructed
    env `_codex_rollouts` (FR-003) — so seeding, child execution, turn
    detection and archiving agree on one identity.
    """
    declared = Path(home_path)
    if declared.is_absolute():
        return codex_home_path(declared)
    root = Path.cwd() / declared
    return codex_home_path(root.resolve())


def _seed_codex_config(codex_home: Path, context: AttemptContext) -> None:
    """Write the generated `config.toml` declaring the gateway (FR-003).

    Provider routing belongs in this file — never in any `[[llm.persona]]`-style
    control-plane config (D-048) — and it is parameterised by the attempt's
    proxy URL alone: the key is named by `env_key` and travels in the
    environment, so no credential is written to disk twice.
    """
    codex_home.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(FileNotFoundError):
        (codex_home / "auth.json").unlink()
    config = (
        f'model_provider = "{CODEX_GATEWAY_PROVIDER}"\n'
        "\n"
        f"[model_providers.{CODEX_GATEWAY_PROVIDER}]\n"
        f'name = "{CODEX_GATEWAY_PROVIDER_NAME}"\n'
        f'base_url = "{context.proxy_url}/v1"\n'
        f'env_key = "{CODEX_GATEWAY_KEY}"\n'
        f'wire_api = "{CODEX_WIRE_API}"\n'
    )
    (codex_home / "config.toml").write_text(config, encoding="utf-8")


def _codex_rollouts(env: Mapping[str, str]) -> list[Path]:
    """Every rollout file this attempt's CODEX_HOME could hold.

    The tree is date-keyed (`sessions/<YYYY>/<MM>/<DD>/rollout-*.jsonl`) and
    the file names carry ids Codex generated itself, so the probe is the tree,
    not one known name. Sorted for a deterministic archive order.
    """
    codex_home = env.get(CODEX_HOME_ENV)
    if not codex_home:
        return []
    sessions = Path(codex_home) / "sessions"
    if not sessions.is_dir():
        return []
    try:
        return sorted(sessions.rglob("rollout-*.jsonl"))
    except OSError:
        # An unreadable tree answers "nothing found": the archive step then
        # copies nothing (the log is still evidence) and the turn probe
        # answers no — an unreadable CODEX_HOME means the launch itself failed
        # to write anything, which is the fact being reported.
        return []


_ADAPTERS: dict[str, type[Any]] = {
    ClaudeCodeAdapter.name: ClaudeCodeAdapter,
    CodexAdapter.name: CodexAdapter,
}

# the pre-agent failure, classified structurally (095-US1) ---------------------


def session_transcript(
    context: AttemptContext, worktree: Path, env: Mapping[str, str]
) -> Path | None:
    """Where Claude Code writes this attempt's session transcript, or `None`.

    One definition, two readers (the archive step copies it, the classifier
    asks whether it exists). Since 155 this is one CLI's convention among
    several: where a session transcript lives is per-CLI (`CodexAdapter` names
    its own through `_transcripts`), and the shared policy never spells a
    per-CLI path itself.
    """
    home = env.get("HOME")
    if not home:
        return None
    return (
        Path(home)
        / ".claude"
        / "projects"
        / project_dir_name(worktree)
        / f"{context.session_id}.jsonl"
    )


def _wrote_session_transcript(
    context: AttemptContext, worktree: Path, env: Mapping[str, str]
) -> bool:
    """Whether the agent took a turn — the structural fact, read at exit.

    The CLI writes its session file on the first turn, so this is "did a token
    ever exist", asked without reading a word the agent said. A path that cannot
    be read answers *yes*: an unreadable disk is not evidence that no agent ran,
    and `AGENT_ERROR` is the classification that changes nothing.
    """
    try:
        transcript = session_transcript(context, worktree, env)
        return transcript is None or transcript.is_file()
    except OSError:
        return True


def _failure_class(
    *, elapsed_s: float, agent_took_a_turn: Callable[[], bool] | None
) -> Termination:
    """Which failure a non-zero exit was: the story's, or the environment's.

    Two structural facts and no message (plan trap 1). A process that ran longer
    than `PRE_AGENT_WINDOW_S` did more than fail to start, whatever the
    transcript convention says today; a process that wrote no session transcript
    produced no token, prepared no worktree, and attempted nothing of the story.
    Only both together are the pre-agent class.

    `agent_took_a_turn` is optional so a caller that cannot answer the question
    gets exactly today's behaviour rather than a guess, and a probe that raises
    is the caller's to isolate — this function is total by construction.
    """
    if agent_took_a_turn is None or elapsed_s >= PRE_AGENT_WINDOW_S:
        return Termination.AGENT_ERROR
    return (
        Termination.AGENT_ERROR
        if agent_took_a_turn()
        else Termination.PRE_AGENT_FAILURE
    )


# stdin, pids, signals --------------------------------------------------------


async def _feed_prompt(process: asyncio.subprocess.Process, prompt: str) -> None:
    """Write the prompt and close the pipe — the close is what ends the agent's read.

    Its own task because a child that never drains stdin would otherwise block
    the launch itself, and the deadline exists precisely for agents that
    misbehave. A pipe that breaks first (an agent that exited early) is that
    agent's exit status to report, not an exception to raise over it.
    """
    stdin = process.stdin
    if stdin is None:  # pragma: no cover - stdin is always a pipe here
        return
    try:
        stdin.write(prompt.encode("utf-8"))
        await stdin.drain()
    except (BrokenPipeError, ConnectionResetError):
        pass
    finally:
        with contextlib.suppress(BrokenPipeError, ConnectionResetError, OSError):
            stdin.close()


async def _stop_feeding(feeder: asyncio.Future[None]) -> None:
    """Let the writer finish, or cancel it if the agent is already gone."""
    feeder.cancel()
    with contextlib.suppress(asyncio.CancelledError, BrokenPipeError, OSError):
        await feeder


def _write_pid_file(pids: Path, pgid: int) -> None:
    """Record this attempt's process group, for whoever runs next (R4).

    The child is a session leader (`start_new_session`), so its pid *is* its
    group id — and the group is what has to die, since the agent's children are
    the half that outlives it.
    """
    pids.parent.mkdir(parents=True, exist_ok=True)
    pids.write_text(f"{pgid}\n", encoding="utf-8")


def _clear_pid_file(pids: Path) -> None:
    """Drop the file on the way out: a stale pid is a reap of somebody else."""
    with contextlib.suppress(OSError):
        pids.unlink(missing_ok=True)


def _read_pgid(pids: Path) -> int | None:
    """The process group a previous run recorded, or None if there is not a usable one."""
    try:
        recorded = int(pids.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    if recorded <= 0 or recorded == os.getpgid(0):
        return None
    return recorded


def _group_alive(pgid: int) -> bool:
    """Whether a non-zombie member of the process group remains."""
    if pgid <= 0:
        return False
    for process_directory in Path("/proc").glob("[0-9]*"):
        try:
            fields = (process_directory / "stat").read_text(encoding="utf-8").rsplit(")", 1)
            if len(fields) != 2:
                continue
            numbers = fields[1].split()
            if len(numbers) < 4 or int(numbers[3]) != pgid:
                continue
            state = numbers[0]
            if state != "Z":
                return True
        except (OSError, ValueError):
            continue
    return False


def _signal_group(pgid: int, sig: int) -> None:
    """Signal a whole process group, tolerating one that has already gone.

    An empty group is the expected outcome of the second signal, not an error.
    """
    if pgid <= 0:
        return
    with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
        os.killpg(pgid, sig)
