"""The one place the factory touches an agent (D-018).

Launch a headless coding agent in the node's worktree, watch it, end it when its
deadline passes, classify how it ended, keep what it produced. That is the whole
seam: no diff is read here, no usage is counted here, and nothing the agent
*says* is inspected anywhere (FR-012). A second agent is a second class in this
module — `adapter_for` resolves the persona registry's `agent` field to one — and
the orchestration above it does not change.

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

Classification is exit status and nothing else: zero → `COMPLETED`, non-zero →
`AGENT_ERROR`, deadline → `TIMEOUT`, cancellation → `KILLED`. `COMPLETED` is a
statement about a process, never a claim that the work is done — the verdict
belongs to component 2, later, from the worktree.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import shutil
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Protocol, Sequence

from factory.usage.models import Termination, UsageSnapshot
from factory.verify.factory_yaml import FactoryConfigError, MANIFEST_NAME, load_factory_config, resolve_manifest_path
from factory.verify.gates import BwrapGateExecutor, ordered_binds
from factory.verify.toolchain import (
    GIT,
    NODE,
    UV,
    ResolvedTool,
    ToolchainError,
    container_path,
    resolve_toolchain,
)
from factory.workgraph.detector import compare_and_report, capture_start
from factory.workgraph.models import AdapterResult, AttemptContext
from factory.workgraph.worktree import SALVAGE_AUTHOR_EMAIL, SALVAGE_AUTHOR_NAME

#: The agent's combined stdout and stderr, streamed live into the attempt's
#: archive directory. Interleaved as the agent wrote it: two files would put the
#: burden of reconstructing the order on whoever reads the evidence.
STDOUT_LOG_NAME = "stdout.log"

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

#: Seconds between SIGTERM and SIGKILL at the deadline. Long enough for an agent
#: to flush the session transcript that is about to become the only account of
#: what it was doing, short enough that ignoring TERM buys nothing.
DEFAULT_GRACE_S = 10.0

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


#: Absolute path the bwrap backend is pinned to. Ubuntu 24.04's AppArmor profile
#: permits unprivileged user namespaces only for the system binary at this path
#: (trap 6); a copied or vendored binary has no profile and fails with EPERM.
BWRAP_BACKEND_BINARY = Path("/usr/bin/bwrap")


class HostAgentBackend:
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
            return await asyncio.create_subprocess_exec(
                *invocation.argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=invocation.log,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(invocation.worktree),
                env=invocation.env,
                start_new_session=True,
            )
        except OSError as error:
            raise AdapterError(
                f"could not launch agent '{self.executable}' for "
                f"{invocation.argv}: {error}"
            ) from error


class BwrapBackend:
    """Bubblewrap containment: the agent's filesystem is its worktree, not the host.

    The mount set is deliberately minimal (US3). `/usr` is read-only with the
    usual `/bin` and `/lib` symlinks; there is no `/lib64` on this aarch64 host.
    `/proc`, `/dev`, and a tmpfs `/tmp` give the shell and toolchain enough of a
    runtime to function. The node worktree is bound writable at the same absolute
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

    def __init__(self, *, executable: str = DEFAULT_EXECUTABLE) -> None:
        self.executable = executable

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
        """Read-only leaf binds for the agent's toolchain (trap 13).

        Each tuple is (bwrap flag, host source, container destination). Source
        and destination differ where the tool is a symlink: the agent runner is
        a link in the operator's home pointing into a versioned install, and
        binding the *resolved* file at the *link's* path is what keeps it from
        dangling inside the boundary while the container's `PATH` still finds
        it where it expects to.
        """
        resolved = self._toolchain() if tools is None else tools
        return [("--ro-bind", source, dest) for source, dest in (tool.bind for tool in resolved)]

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
            # Minimal system tree: read-only /usr plus the symlinks Ubuntu uses
            # on aarch64. No /lib64 on this host.
            "--ro-bind", "/usr", "/usr",
            "--symlink", "usr/bin", "/bin",
            "--symlink", "usr/lib", "/lib",
            # Runtime pseudo-filesystems.
            "--proc", "/proc",
            "--dev", "/dev",
            "--tmpfs", "/tmp",
        ]

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
        cache_binds = gate_boundary._cache_binds()
        for source, dest in cache_binds:
            binds.append(("--bind", source, dest))

        # The executable itself, when it is an absolute path not already mounted.
        executable_bind = self._bind_executable(invocation)
        if executable_bind:
            binds.append(
                (executable_bind[0], executable_bind[1], executable_bind[2])
            )

        argv.extend(ordered_binds(binds))
        argv.extend(["--chdir", str(worktree)])
        argv.extend(["--setenv", "HOME", str(home)])
        for _, dest in cache_binds:
            argv.extend(["--setenv", "UV_CACHE_DIR", dest])

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
            "CLAUDE_CODE_MAX_CONTEXT_TOKENS",
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

        # Toolchain discovery happens inside `_build_argv`, so a host missing a
        # tool refuses here — by name, before anything forks. `AdapterError` is
        # the right class for it: infrastructure the operator has to fix, never
        # a verdict, and never an attempt the ladder should spend.
        try:
            argv = self._build_argv(invocation)
        except ToolchainError as error:
            raise AdapterError(str(error)) from error

        try:
            return await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=invocation.log,
                stderr=asyncio.subprocess.STDOUT,
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
    riding on each one getting it right. What genuinely differs between agents is
    how a prompt becomes a process, so that is what a second class overrides.
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


def _seed_node_home(home: Path) -> None:
    """Write the minimum the CLI needs to start non-interactively on this home.

    T001 found the answer is almost nothing: the CLI writes its own
    `.claude.json`, `plugins/`, `projects/`, `sessions/` and `backups/` from
    fresh defaults when given a bare writable home. The factory therefore
    writes only git identity, and it writes it from constants already owned by
    the factory's salvage path (FR-005).

    The function takes no path into the operator's home and no argument that
    could carry one: every value it writes is imported from this module or
    `factory.workgraph.worktree`.
    """
    config = (
        "[user]\n"
        f"\tname = {_SALVAGE_AUTHOR_NAME}\n"
        f"\temail = {_SALVAGE_AUTHOR_EMAIL}\n"
    )
    (home / ".gitconfig").write_text(config, encoding="utf-8")


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
    if context.context_window is not None:
        env["CLAUDE_CODE_MAX_CONTEXT_TOKENS"] = str(context.context_window)
    env.update({name: source[name] for name in PASSTHROUGH_ENV if source.get(name)})
    return env


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
        _seed_node_home(home)
        await self._reap(pids)

        worktree = Path(context.worktree_path).resolve()
        target_repo = Path(context.target_repo) if context.target_repo else None
        # `ATTEMPT_ARCHIVE` is the one constructed env var beyond the gateway
        # variables and the four passthroughs: the agent's ferry files live in the
        # archive directory (never the worktree, where salvage would commit them —
        # FR-007), so the agent has to know where it is. Built here rather than in
        # `attempt_env` because the archive path is the adapter's knowledge,
        # derived from the same identity the transcript directory is.
        routes_through_gateway = context.agent != "subscription"
        env = attempt_env(context, routes_through_gateway=routes_through_gateway)
        env[ATTEMPT_ARCHIVE_ENV] = str(archive)

        # US1: capture the target repository's tracked-file state before the agent runs.
        if target_repo is not None:
            capture_start(Path(factory_root), target_repo, context)

        with (archive / STDOUT_LOG_NAME).open("wb") as log:
            backend = self._resolve_backend(worktree, target_repo)
            invocation = AgentInvocation(
                argv=self.argv(context),
                prompt=context.prompt,
                worktree=worktree,
                env=env,
                log=log,
                standards_path=self._standards_path(worktree, target_repo),
                model_alias=context.model_alias,
            )
            process = await backend.launch(invocation)
            _write_pid_file(pids, process.pid)
            feeder = asyncio.ensure_future(_feed_prompt(process, context.prompt))
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
                )
            except BaseException:
                # Cancellation (the workflow's kill) and any failure of the
                # monitor itself end identically: the process group dies and the
                # attempt keeps its evidence. Only the classification differs,
                # and on this path the workflow supplies it.
                await self._reclaim(process)
                self._archive_session(context, worktree, env, archive)
                _clear_pid_file(pids)
                if target_repo is not None:
                    compare_and_report(Path(factory_root), target_repo, context)
                raise
            finally:
                await _stop_feeding(feeder)

        self._archive_session(context, worktree, env, archive)
        _clear_pid_file(pids)
        if target_repo is not None:
            compare_and_report(Path(factory_root), target_repo, context)
        return AdapterResult(
            termination=termination,
            transcript_path=str(archive),
            last_snapshot=last_snapshot,
        )

    # -- launch ---------------------------------------------------------------

    def argv(self, context: AttemptContext) -> list[str]:
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
        if self._backend is not None:
            return self._backend

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
        return backend_class(executable=self.executable)

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

    async def _launch(
        self,
        context: AttemptContext,
        *,
        worktree: Path,
        env: dict[str, str],
        log: Any,
    ) -> asyncio.subprocess.Process:
        """Spawn the agent in its own session, writing into the archived log.

        `start_new_session=True` is what makes the agent and everything it spawns
        one process group, so the deadline can be enforced against the tree
        rather than against the root of it. stderr is merged into stdout because
        the log is read by a human looking for what went wrong, in order.

        Kept as the explicit host-launch implementation; the default path in
        `run_attempt` routes through the seam.
        """
        backend = HostAgentBackend(executable=self.executable)
        invocation = AgentInvocation(
            argv=self.argv(context),
            prompt=context.prompt,
            worktree=worktree,
            env=env,
            log=log,
            standards_path=self._standards_path(worktree, None),
            model_alias=context.model_alias,
        )
        return await backend.launch(invocation)

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
        deadline = loop.time() + timeout_s
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
                        else Termination.AGENT_ERROR
                    ),
                    snapshot,
                )
        except BaseException:
            exited.cancel()
            raise

        await self._reclaim(process)
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
            await asyncio.wait_for(process.wait(), timeout=self.grace_s)
        _signal_group(process.pid, signal.SIGKILL)
        await process.wait()

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

        _signal_group(pgid, signal.SIGTERM)
        deadline = asyncio.get_running_loop().time() + self.grace_s
        while _group_alive(pgid) and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.05)
        _signal_group(pgid, signal.SIGKILL)

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
        """
        home = env.get("HOME")
        if not home:
            return
        source = (
            Path(home)
            / ".claude"
            / "projects"
            / project_dir_name(worktree)
            / f"{context.session_id}.jsonl"
        )
        if not source.is_file():
            return
        with contextlib.suppress(OSError):
            shutil.copy2(source, archive / source.name)


_ADAPTERS: dict[str, type[Any]] = {ClaudeCodeAdapter.name: ClaudeCodeAdapter}


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
    """Whether signal 0 still finds the group (a zombie counts — it exists)."""
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _signal_group(pgid: int, sig: int) -> None:
    """Signal a whole process group, tolerating one that has already gone.

    An empty group is the expected outcome of the second signal, not an error.
    """
    if pgid <= 0:
        return
    with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
        os.killpg(pgid, sig)
