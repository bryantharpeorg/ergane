"""Running the target repo's declared gates, and surviving the ones that misbehave.

Gates are the deterministic half of verification (FR-002): the commands the repo
committed in its `factory.yaml`, run in the node's worktree, in the order the
repo declared them. The happy path is four lines; everything else in this module
is about the three ways a gate refuses to be simple.

**A gate that fails is data.** Non-zero exit, deadline, unusable manifest — each
becomes a `GateResult` the verdict truth table reads. Nothing here raises past
its caller, because an exception would cost the attempt its evidence and an
empty gate list is exactly the shape a naive verdict mistakes for "nothing
failed" (SC-002). A broken manifest is one `CONFIG_ERROR` result, never zero
results.

**A gate that hangs owns children.** `bash -c "make test"` is a process tree, and
killing only its root leaves the grandchildren holding the output pipe: the
runner would still return, thirty seconds later, having waited for a `sleep` it
thought it had killed. So each gate gets its own session (`start_new_session`),
the deadline is enforced against the whole process *group*, and SIGTERM is
followed by SIGKILL once the grace period expires (R3) — a gate that traps TERM
does not get to outlive its timeout.

**A gate that fails still leaves evidence.** Output is drained by a thread rather
than collected at exit, so a killed gate's output is what it printed before it
died — which is where the explanation is. That drain keeps only a bounded window:
the last `OUTPUT_TAIL_LIMIT` bytes, because this text is copied into workflow
state, an escalation message and the evidence store, and one verbose test suite
should not be able to fill all three.

Execution sits behind the narrow `GateExecutor` seam (R3) so `ContainerExecutor`
can replace `SubprocessGateExecutor` later without touching verdict logic — and
so tests can assert the timeout the runner *resolved* without waiting out a
ten-minute default to prove it is ten minutes.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Mapping, Protocol, Sequence

from factory.verify.factory_yaml import (
    MANIFEST_NAME,
    PARSE_CLI_OK,
    PARSE_CLI_REJECTED,
    FactoryConfigError,
    config_error_result,
    load_factory_config,
)
from factory.verify.models import GateResult, GateStatus, VerificationConfig
from factory.verify.toolchain import (
    DEFAULT_AGENT_RUNNER,
    GIT,
    NODE,
    UV,
    ResolvedTool,
    ToolchainError,
    container_path,
    find_install_root,
    resolve_toolchain,
)

#: Deadline for a gate the manifest gives no `timeouts` entry. Sourced from
#: `VerificationConfig` rather than restated: that field is the knob an operator
#: edits, and a second literal here would let tuning it silently do nothing.
DEFAULT_GATE_TIMEOUT_S: int = VerificationConfig().gate_timeout_s

#: How many gate subprocesses may run at once across the whole host (007 FR-005).
#:
#: The hazard fan-out introduces: N nodes' gates on one host contend for CPU, so
#: the same suite takes longer purely because neighbours exist, and a fixed
#: wall-clock timeout converts that stretch into a spurious FAIL — a verdict
#: that is not a fact about the node's code. Bounding gate concurrency *below*
#: node concurrency fixes the property rather than tolerating it: a node's
#: agent runs in parallel while its gates take a turn, and a gate's wall-clock
#: measures its own work, never the queue it waited in. The default of one is
#: the strongest form — gates serialize across the host — and is below any
#: `max_concurrent_nodes` above one. It is a process-level bound because gates
#: already run through the worker's thread path (`asyncio.to_thread`), so a
#: semaphore here is the one limiter all of them cross.
DEFAULT_GATE_CONCURRENCY: int = 1

#: How much of a gate's combined output is kept as evidence (R3).
OUTPUT_TAIL_LIMIT = 32 * 1024

#: Environment variable names a gate subprocess may inherit — an allowlist, not
#: a denylist, because a denylist protects the credentials we thought of and
#: leaks the ones invented next quarter (constitution V, R3). Anything a gate
#: genuinely needs belongs in the repo's own command, where it is reviewable.
SCRUBBED_ENV_ALLOWLIST: tuple[str, ...] = (
    "PATH",
    "HOME",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "TERM",
    "USER",
    "LOGNAME",
    "SHELL",
)

#: Used when the parent has no usable `PATH`. Without one, every gate fails with
#: "bash: command not found" — a config error wearing a gate failure's clothes.
FALLBACK_PATH = "/usr/local/bin:/usr/bin:/bin"

#: Seconds between SIGTERM and SIGKILL. Long enough for a test runner to flush
#: its report, short enough that a process ignoring TERM does not become the
#: verification's deadline.
DEFAULT_KILL_GRACE_S = 10.0

#: Absolute path the bwrap backend is pinned to. Ubuntu 24.04's AppArmor profile
#: permits unprivileged user namespaces only for the system binary at this path
#: (trap 6); a copied or vendored binary has no profile and fails with EPERM.
BWRAP_BACKEND_BINARY = Path("/usr/bin/bwrap")


def ordered_binds(binds: Sequence[tuple[str, str, str]]) -> list[str]:
    """Flatten filesystem binds into argv, shallowest path first.

    bwrap applies mounts in argv order, so a bind whose destination *contains*
    an earlier one silently replaces it. Every path in this factory has that
    shape: a node worktree lives at
    ``<target_repo>/.factory/worktrees/<epic>/<node>``, inside both the runtime
    root and the target repository, so emitting the worktree writable and the
    repository read-only afterwards made the worktree read-only.

    That is not hypothetical — it shipped. `011-agent-sandbox/US5` put gates
    behind the boundary and the first real epic to run under it
    (`033-ergane-install/us2`, 2026-08-15) failed its gate with
    ``failed to remove directory .venv/bin: Read-only file system``, because
    ``--ro-bind <target_repo>`` was emitted after ``--bind <worktree>``.

    Sorting by depth makes the most specific bind win regardless of the order
    callers happen to list them in, which is the property the mount set needs
    and the one an ad-hoc "is this the immediate parent?" guard cannot provide.
    Ties keep the caller's order, so two binds at the same depth stay as
    written.
    """
    ordered = sorted(binds, key=lambda bind: len(Path(bind[2]).parts))
    argv: list[str] = []
    for flag, source, dest in ordered:
        argv.extend([flag, source, dest])
    return argv


_READ_CHUNK = 64 * 1024

#: The drain trims back to the tail once it holds this multiple of the limit —
#: bounded memory without a slice on every chunk.
_TRIM_FACTOR = 4

#: How long to wait for the drain thread after the gate's group is gone. It ends
#: at EOF, which the SIGKILL guarantees; the bound is only so a process that
#: escaped its group cannot hang the verification.
_DRAIN_JOIN_S = 5.0


# Candidate parser protocol --------------------------------------------------


@dataclass(frozen=True)
class CandidateOutcome:
    """Raw result from a candidate parser subprocess."""

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


@dataclass(frozen=True)
class _AcceptedConfig:
    """A candidate acceptance: the subset of the protocol the runner consumes."""

    kind: str = "accepted"
    gates: dict[str, str] | None = None
    timeouts: dict[str, int] | None = None


@dataclass(frozen=True)
class _RejectedConfig:
    """A candidate rejection: the worker uses this message as the CONFIG_ERROR."""

    kind: str = "rejected"
    message: str = ""


@dataclass(frozen=True)
class _CannotRun:
    """A candidate that could not run: reason is appended to fallback tail."""

    kind: str = "cannot-run"
    reason: str = ""


class CandidateRunner(Protocol):
    """A callable seam for candidate parser subprocesses.

    Tests pass a plain callable `(worktree, manifest) -> CandidateOutcome`;
    the real implementation is an object with a `run` method. Both shapes
    are accepted so the public API matches the existing `executor` keyword.
    """

    def __call__(self, worktree: Path, manifest: Path) -> CandidateOutcome: ...


_CandidateResult = _AcceptedConfig | _RejectedConfig | _CannotRun


# Invocation seam ------------------------------------------------------------


@dataclass(frozen=True)
class GateInvocation:
    """Everything decided before a gate runs — the resolved plan for one gate.

    Timeout resolution (declared, overridden, defaulted), the worktree to run
    in, and the scrubbed environment are all settled here, so an executor has no
    policy left to get wrong and a test can assert the policy without running a
    process.
    """

    name: str
    command: str
    cwd: Path
    timeout_s: int
    env: dict[str, str]


@dataclass(frozen=True)
class ExecutionOutcome:
    """What an executor observed: still raw, not yet a verdict.

    `exit_code` is None exactly when there was no exit status to read, which is
    the timeout case; `timed_out` says so explicitly rather than leaving the
    mapping to infer it, because a gate killed by an unrelated signal reports a
    negative code and is an ordinary failure, not a deadline.
    """

    exit_code: int | None
    output: str
    duration_s: float
    timed_out: bool


class GateExecutor(Protocol):
    """The one thing a gate backend does (R3): run an invocation, report back."""

    def run(self, invocation: GateInvocation) -> ExecutionOutcome: ...


# Gate concurrency (007 FR-005) ------------------------------------------------


class GateConcurrencyLimiter:
    """A process-level bound on how many gates run at once (007 FR-005).

    `run_gates` calls live in worker threads (`asyncio.to_thread` in the
    activity), so a `threading.Semaphore` is the one limiter every gate crosses
    regardless of which node dispatched it. A gate acquires a slot before its
    process starts and releases it when the process is done; the wall-clock
    bound is enforced inside that window, so a gate that waits for its turn
    measures only its own work, never the queue. That is what makes the verdict
    load-*independent* rather than load-*tolerant*.

    `acquire()` returns how many *other* gates were in flight when this one got
    its slot — the contention marker recorded on the `GateResult`, so a slow
    verdict is auditable afterwards. Zero means the gate had the budget to
    itself.
    """

    def __init__(self, bound: int = DEFAULT_GATE_CONCURRENCY) -> None:
        if bound < 1:
            raise ValueError(
                f"gate concurrency bound must be >= 1, not {bound}"
            )
        self._bound = bound
        self._slots = threading.BoundedSemaphore(bound)
        self._in_flight = 0
        self._lock = threading.Lock()

    @property
    def bound(self) -> int:
        return self._bound

    def acquire(self) -> int:
        """Take a slot; return the count of *other* gates now in flight."""
        self._slots.acquire()
        with self._lock:
            peers = self._in_flight
            self._in_flight += 1
        return peers

    def release(self) -> None:
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)
        self._slots.release()


#: The limiter `run_gates` uses when a caller does not supply one. Module-level
#: so two `run_gates` calls in two worker threads — the shape fan-out produces
#: — share the same bound rather than each racing unbounded.
_default_limiter = GateConcurrencyLimiter(DEFAULT_GATE_CONCURRENCY)


# Environment ----------------------------------------------------------------


def scrubbed_env(source: Mapping[str, str] | None = None) -> dict[str, str]:
    """The environment a gate is allowed to see, drawn from `source` (default: this process').

    Names outside `SCRUBBED_ENV_ALLOWLIST` are dropped, so `LITELLM_MASTER_KEY`
    and `TELEGRAM_BOT_TOKEN` never reach a repo-declared command — nor does the
    next credential the worker host acquires, which is the whole reason this is
    an allowlist. Variables exported empty are treated as absent so `PATH=` gets
    the fallback rather than breaking every gate.
    """
    environ = os.environ if source is None else source
    env = {name: environ[name] for name in SCRUBBED_ENV_ALLOWLIST if environ.get(name)}
    env.setdefault("PATH", FALLBACK_PATH)
    return env


# Output tails ---------------------------------------------------------------


def tail_output(text: str, limit: int = OUTPUT_TAIL_LIMIT) -> str:
    """The last `limit` bytes of `text`, verbatim and still decodable.

    A suffix, with nothing inserted: this text is quoted into retry prompts
    (FR-006, SC-004), so a truncation marker here would put the factory's own
    voice inside what is supposed to be the tool's output. Marking truncation is
    judge-input assembly's job (R6), where the model has to be told not to read
    a cut as missing implementation.

    The cap is bytes because that is what the store and the message budgets are
    denominated in, but the cut lands on a character boundary — a tail sliced
    mid-character would not decode.
    """
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text
    return _tail_bytes(encoded, limit).decode("utf-8")


def _tail_bytes(data: bytes, limit: int) -> bytes:
    if len(data) <= limit:
        return data
    window = data[-limit:]
    # Continuation bytes (0b10xxxxxx) at the front are the second half of a
    # character the cut went through; dropping them is what keeps the rest valid.
    start = 0
    while start < len(window) and window[start] & 0xC0 == 0x80:
        start += 1
    return window[start:]


class _TailBuffer:
    """A stream's last `limit` bytes, accumulated from another thread.

    Bounded on purpose: a gate is free to print gigabytes, and holding them to
    keep 32 KiB would make an over-chatty test suite an out-of-memory failure.
    """

    def __init__(self, limit: int = OUTPUT_TAIL_LIMIT) -> None:
        self._limit = limit
        self._lock = threading.Lock()
        self._data = bytearray()

    def feed(self, chunk: bytes) -> None:
        with self._lock:
            self._data += chunk
            if len(self._data) > self._limit * _TRIM_FACTOR:
                del self._data[: -self._limit]

    def text(self) -> str:
        with self._lock:
            data = _tail_bytes(bytes(self._data), self._limit)
        # `replace` rather than `strict`: a gate killed mid-write leaves a partial
        # character, and losing the whole tail to one broken byte would lose the
        # failure's explanation with it.
        return data.decode("utf-8", errors="replace")


# Subprocess executor --------------------------------------------------------


class SubprocessGateExecutor:
    """Runs a gate as `bash -c <command>` in the worktree, on the worker host.

    `bash -c` rather than an argv split because repo gate commands legitimately
    use shell features (`&&`, globs, variables) and `factory.yaml` is
    operator-committed config at the same trust level as CI config (R3). The
    container-isolated executor belongs to the component that owns node
    sandboxing; this one deliberately relies on the node's worktree already
    being sandboxed.
    """

    def __init__(self, *, grace_s: float = DEFAULT_KILL_GRACE_S) -> None:
        self.grace_s = grace_s

    def run(self, invocation: GateInvocation) -> ExecutionOutcome:
        started = time.monotonic()
        process = subprocess.Popen(
            ["bash", "-c", invocation.command],
            cwd=str(invocation.cwd),
            env=dict(invocation.env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            # Its own session, so the deadline can be enforced against the whole
            # process tree instead of just the shell at its root.
            start_new_session=True,
        )

        buffer = _TailBuffer()
        drain = threading.Thread(
            target=_drain,
            args=(process.stdout, buffer),
            name=f"gate-{invocation.name}-output",
            daemon=True,
        )
        drain.start()

        timed_out = False
        try:
            process.wait(timeout=invocation.timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._reclaim(process)

        drain.join(timeout=_DRAIN_JOIN_S)
        duration_s = time.monotonic() - started

        return ExecutionOutcome(
            exit_code=None if timed_out else process.returncode,
            output=buffer.text(),
            duration_s=duration_s,
            timed_out=timed_out,
        )

    def _reclaim(self, process: subprocess.Popen[bytes]) -> None:
        """SIGTERM the gate's process group, then SIGKILL what survives (R3)."""
        _signal_group(process, signal.SIGTERM)
        try:
            process.wait(timeout=self.grace_s)
        except subprocess.TimeoutExpired:
            pass
        # Sent even when the shell died politely: its children are in the same
        # group, outlive it, and keep the output pipe open until they are gone.
        _signal_group(process, signal.SIGKILL)
        process.wait()


def _signal_group(process: subprocess.Popen[bytes], sig: int) -> None:
    # `start_new_session` makes the child its own group leader, so its pid is the
    # group id. An already-empty group is the expected outcome of the second
    # signal, not an error.
    try:
        os.killpg(process.pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _drain(stream: IO[bytes] | None, buffer: _TailBuffer) -> None:
    if stream is None:
        return
    try:
        while chunk := stream.read(_READ_CHUNK):
            buffer.feed(chunk)
    except (OSError, ValueError):
        # The pipe went away with the process; whatever was read is the evidence.
        pass
    finally:
        stream.close()


# Bubblewrap executor --------------------------------------------------------


class BwrapGateExecutor:
    """Runs a gate inside the same bubblewrap boundary as the agent (US5).

    The mount set is deliberately minimal: a read-only system tree, a tmpfs
    for the gate's scratch state, the node worktree writable, the parent repo's
    `.git` writable for git plumbing, and read-only toolchain leaves. Network
    is intentionally not unshared — egress is out of scope — and the gate runs
    in its own PID namespace with `--die-with-parent` so the existing group-kill
    path reaches the whole tree.
    """

    def __init__(self, *, grace_s: float = DEFAULT_KILL_GRACE_S) -> None:
        self.grace_s = grace_s

    def run(self, invocation: GateInvocation) -> ExecutionOutcome:
        started = time.monotonic()
        binary = BWRAP_BACKEND_BINARY
        if not binary.is_file():
            return ExecutionOutcome(
                exit_code=127,
                output=(
                    f"sandbox backend 'bwrap' not available: {binary} "
                    "missing on this host"
                ),
                duration_s=0.0,
                timed_out=False,
            )

        # Discovery happens while the argv is assembled, so a host missing a
        # tool is refused by name here — before the fork — instead of reaching
        # the operator as bwrap's own `Can't find source path` from a process
        # that has already started. Same shape as the missing-binary refusal
        # above: a 127 outcome carrying the reason, not an exception the gate
        # runner has no place to put.
        try:
            argv = self._build_argv(invocation)
        except ToolchainError as error:
            return ExecutionOutcome(
                exit_code=127,
                output=str(error),
                duration_s=time.monotonic() - started,
                timed_out=False,
            )

        process = subprocess.Popen(
            argv,
            cwd=str(invocation.cwd),
            env=dict(invocation.env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

        buffer = _TailBuffer()
        drain = threading.Thread(
            target=_drain,
            args=(process.stdout, buffer),
            name=f"gate-{invocation.name}-output",
            daemon=True,
        )
        drain.start()

        timed_out = False
        try:
            process.wait(timeout=invocation.timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._reclaim(process)

        drain.join(timeout=_DRAIN_JOIN_S)
        duration_s = time.monotonic() - started

        return ExecutionOutcome(
            exit_code=None if timed_out else process.returncode,
            output=buffer.text(),
            duration_s=duration_s,
            timed_out=timed_out,
        )

    def _reclaim(self, process: subprocess.Popen[bytes]) -> None:
        """SIGTERM the gate's process group, then SIGKILL what survives (R3)."""
        _signal_group(process, signal.SIGTERM)
        try:
            process.wait(timeout=self.grace_s)
        except subprocess.TimeoutExpired:
            pass
        _signal_group(process, signal.SIGKILL)
        process.wait()

    def _build_argv(self, invocation: GateInvocation) -> list[str]:
        """Assemble the bwrap command from the proven mount set."""
        worktree = invocation.cwd.resolve()
        home = Path("/tmp/ergane-gate-home")

        argv: list[str] = [
            str(BWRAP_BACKEND_BINARY),
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
        # reader; the mount order is the helper's.
        binds: list[tuple[str, str, str]] = []

        # The parent read-only so bwrap does not create a writable intermediate
        # directory exposing sibling worktrees (trap 9); the node worktree
        # writable — only the leaf, at the same absolute path.
        if worktree.parent not in (Path("/"),):
            binds.append(("--ro-bind", str(worktree.parent), str(worktree.parent)))
        binds.append(("--bind", str(worktree), str(worktree)))

        # Git plumbing: a linked worktree's `.git` file points back to the
        # parent repo's `.git/worktrees/<name>`. Bind the whole parent `.git`
        # writable so commit/diff work; the working tree is read-only.
        target_git_dir = _resolve_target_git_dir(worktree)
        if target_git_dir is not None:
            target_worktree = target_git_dir.parent
            if target_worktree not in (worktree.parent, Path("/")):
                binds.append(
                    ("--ro-bind", str(target_worktree), str(target_worktree))
                )
            binds.append(("--bind", str(target_git_dir), str(target_git_dir)))

        # Read-only toolchain leaves (trap 13), collected with the rest so a
        # leaf inside the worktree could not be overlaid by it either, plus the
        # interpreter the worktree's venv points at. The toolchain is resolved
        # once and used twice — for these binds and for the container `PATH`
        # below — so the two cannot name different directories.
        tools = self._toolchain()
        binds.extend(self._toolchain_binds(tools))
        for source, dest in self._interpreter_binds(worktree):
            binds.append(("--ro-bind", source, dest))
        for source, dest in self._resolver_binds():
            binds.append(("--ro-bind", source, dest))

        # The package cache is writable, and is the one bind outside the
        # worktree that is: see `_cache_binds`.
        cache_binds = self._cache_binds()
        for source, dest in cache_binds:
            binds.append(("--bind", source, dest))

        argv.extend(ordered_binds(binds))
        argv.extend(["--chdir", str(worktree)])

        # A factory-owned home for the gate, writable but not the operator's.
        argv.extend(["--tmpfs", str(home)])
        argv.extend(["--setenv", "HOME", str(home)])
        for _, dest in cache_binds:
            argv.extend(["--setenv", "UV_CACHE_DIR", dest])

        # PATH must name the bind points inside the container — derived from
        # the same resolutions the binds came from, never from a literal.
        argv.extend(["--setenv", "PATH", container_path(tools)])

        # A commit identity, so a gate that commits is not asked who it is.
        for name, value in self._identity_env().items():
            argv.extend(["--setenv", name, value])

        # Process/signal boundary (trap 2).
        argv.extend(["--unshare-pid", "--die-with-parent"])

        # Finally the gate itself, as `bash -c <command>`.
        argv.extend(["--", "bash", "-c", invocation.command])
        return argv

    def _toolchain(self) -> list[ResolvedTool]:
        """Discover the toolchain the gate may invoke, in `PATH` order.

        `uv` and `git` are required — every gate command in this factory runs
        through one and the verification store reads the other — so a host
        without them is refused by name rather than handed to bwrap, which
        would fail on the source path after the fork.

        `node` and the agent runner are optional, and were already guarded
        before discovery replaced the literals: a repository whose gates need
        neither still has gates that run, and degrading quietly is the
        behaviour this boundary shipped with.

        The order is load-bearing: `container_path` derives the container's
        `PATH` from it, and the resulting string must keep naming the package
        manager's directory ahead of the system one.
        """
        return resolve_toolchain(
            (UV, NODE, GIT, DEFAULT_AGENT_RUNNER),
            purpose="the gate boundary",
            optional=(NODE, DEFAULT_AGENT_RUNNER),
        )

    def _toolchain_binds(
        self, tools: Sequence[ResolvedTool] | None = None
    ) -> list[tuple[str, str, str]]:
        """Mounts for the toolchain the gate may invoke, as (flag, source, dest).

        "May invoke" includes the agent runner: a repository whose suite
        exercises its own dispatch path launches the agent *inside* the gate,
        and that inner launch binds the runner by source path. Without it here
        the inner boundary refuses to start at all —
        ``bwrap: Can't find source path .../share/claude/versions/2.1.223`` —
        which surfaced as an `agent_error` termination in a test that was
        actually asking a question about signals or deadlines. The whole
        install directory is bound rather than the version the outer launch
        happened to resolve, because the installer keeps several versions and
        prunes them on its own schedule; the inner launch may resolve a
        different one than this one did.

        The runner's `PATH` entry is *recreated as a symlink* rather than bound,
        and that is not decoration. A bind would flatten it: inside the
        namespace `~/.local/bin/claude` would be a regular file, its
        `<install>/versions/<version>` ancestry gone, and the next boundary in
        (this repository's suite runs its own gates, so there is always a next
        one) would resolve it to itself and bind a lone binary instead of the
        install directory. Measured, before the symlink went in: the full suite
        run inside its own gate failed with ``ls: cannot access
        '/home/admin/.local/share/claude/versions': No such file or directory``.
        Reproducing the layout instead of the file makes discovery give the same
        answer at every depth.

        Every path here comes from `_toolchain`, never from a literal: the
        version numbers that used to sit in this method rotted out from under
        it on the operator's own machine.
        """
        resolved = self._toolchain() if tools is None else tools
        binds: list[tuple[str, str, str]] = [
            ("--ro-bind", *tool.bind)
            for tool in resolved
            if tool.name != DEFAULT_AGENT_RUNNER
        ]

        # The runner, if this host has one. The installation is looked up
        # independently of the launcher (`find_install_root`) rather than read
        # off it, because the two are absent independently: a boundary built by
        # a factory predating this module mounts the payload and not the
        # launcher, and deriving one from the other lost the payload there.
        runner = next((t for t in resolved if t.name == DEFAULT_AGENT_RUNNER), None)
        root = find_install_root(DEFAULT_AGENT_RUNNER, tool=runner)
        if root is not None:
            binds.append(("--ro-bind", str(root), str(root)))
        if runner is not None:
            if runner.found_at != runner.real_path:
                binds.append(
                    ("--symlink", str(runner.real_path), str(runner.found_at))
                )
            elif runner.found_at != root:
                binds.append(("--ro-bind", *runner.bind))
        return binds

    def _identity_env(self) -> dict[str, str]:
        """A commit identity for the gate, owned by the factory.

        `HOME` inside the boundary is a tmpfs, so git finds no global config
        and refuses to commit: ``unable to auto-detect email address``. Tests
        that build a throwaway repository and commit to it fail on that alone,
        with a message about identity rather than about what they were
        checking.

        The operator's `~/.gitconfig` is deliberately *not* bound in to supply
        it. On this host that file carries GitHub credential helpers, and
        mounting it would hand every gate run the operator's push credentials
        — the precise authority a verification boundary exists to withhold.
        Naming the identity in the environment costs one mount less and leaks
        nothing.
        """
        name = "Ergane Gate"
        email = "gate@ergane.local"
        return {
            "GIT_AUTHOR_NAME": name,
            "GIT_AUTHOR_EMAIL": email,
            "GIT_COMMITTER_NAME": name,
            "GIT_COMMITTER_EMAIL": email,
        }

    def _resolver_binds(self) -> list[tuple[str, str]]:
        """Name resolution and trust roots, so a gate's network works at all.

        The boundary deliberately does not unshare the network (egress is out
        of scope), but a namespace with no `/etc/resolv.conf` cannot resolve a
        hostname, and one with no trust store cannot complete a TLS handshake.
        The result is not "no network" — it is `Temporary failure in name
        resolution` in the middle of a package install, which reads like a
        broken dependency rather than a missing mount.

        Only these two paths are exposed, never `/etc` wholesale: the rest of
        it is host configuration the gate has no business reading.
        """
        binds: list[tuple[str, str]] = []
        for path in ("/etc/resolv.conf", "/etc/ssl"):
            if Path(path).exists():
                binds.append((path, path))
        return binds

    def _cache_binds(self) -> list[tuple[str, str]]:
        """The package cache, writable, so a gate resolves as it does on the host.

        `HOME` inside the boundary is a tmpfs, so a package manager finds an
        empty cache and re-downloads everything a sync touches — on a host
        whose cache is already warm, that turns a two-second gate into a
        network-bound one, and on a host without egress it turns a passing
        gate into a failing one. Binding the real cache makes the boundary's
        behaviour match the host's, which is the property a verification
        boundary needs: it changes *where a gate may write*, not *whether the
        gate can run*.

        Writable on purpose — a read-only cache is worse than none, because
        the manager treats it as a corrupt one. `UV_CACHE_DIR` is set beside
        this bind (the tmpfs HOME would otherwise send uv looking elsewhere).
        """
        cache = Path.home() / ".cache" / "uv"
        return [(str(cache), str(cache))] if cache.is_dir() else []

    def _interpreter_binds(self, worktree: Path) -> list[tuple[str, str]]:
        """Bind the interpreter the worktree's virtualenv points at, if any.

        A `uv` virtualenv's `bin/python` is a symlink to an interpreter outside
        the worktree — on this host, under `~/.local/share/uv/python/`. Inside
        a boundary that does not carry it the symlink dangles, `uv` reports
        "Ignoring existing virtual environment linked to non-existent Python
        interpreter" and tries to *rebuild* the venv, which is how
        `033-ergane-install/us2` turned a read-only worktree into
        ``failed to remove directory .venv/bin`` rather than a clean error.

        The path is read from the venv rather than hardcoded: a Python version
        bump moves it, and a stale literal here would reintroduce the same
        failure with a new version number in it. Nothing is bound when there is
        no venv — a repo whose gates need no interpreter is not this method's
        business.
        """
        binds: list[tuple[str, str]] = []

        # The managed-interpreter store, whole. Binding only the one version a
        # venv currently points at is not enough: when the manager decides to
        # rebuild the environment it re-runs interpreter *discovery*, and a
        # store holding a single version reads as a store missing the one it
        # wants — it then falls back to the system python, and the gate silently
        # runs on a different interpreter than the host. Measured on
        # 2026-08-15: the boundary reported 3.12.3 where the host reported
        # 3.13.12. A verification boundary that changes the interpreter changes
        # what verification measures, so the whole read-only store is bound.
        store = Path.home() / ".local" / "share" / "uv" / "python"
        if store.is_dir():
            binds.append((str(store), str(store)))

        # And the interpreter the venv actually points at, wherever it lives —
        # a system or pyenv interpreter is outside the store above.
        link = worktree / ".venv" / "bin" / "python"
        try:
            target = link.resolve(strict=True)
        except (OSError, RuntimeError):
            return binds
        if not target.is_file():
            return binds
        # The interpreter's own installation tree — its stdlib sits beside the
        # binary, so binding the executable alone yields an interpreter that
        # cannot import anything.
        root = target.parent.parent
        if not str(root).startswith(str(store)):
            binds.append((str(root), str(root)))
        return binds

    def _container_path(self) -> str:
        """The container's `PATH`, derived from the discovered toolchain.

        Kept as a method because it is the one line of `_build_argv` a reader
        looks for; the derivation itself belongs beside the discovery, in
        `factory.verify.toolchain`, so the agent boundary shares it.
        """
        return container_path(self._toolchain())


def _resolve_target_git_dir(worktree: Path) -> Path | None:
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
    try:
        text = git_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    prefix = "gitdir:"
    if not text.startswith(prefix):
        return None
    gitdir = Path(text[len(prefix):].strip()).resolve()
    return gitdir.parent.parent.resolve()


# Candidate parser implementation --------------------------------------------


def _interpret_candidate(
    exit_code: int, stdout: str, stderr: str, timed_out: bool
) -> _CandidateResult:
    """Map a candidate parser subprocess result to accepted/rejected/cannot-run.

    Exit 0 alone is not acceptance (spec US2-S5, plan trap 2): a pre-CLI
    worktree's `factory.verify.factory_yaml` runs its module body, prints
    nothing, and exits 0. Only exit 0 **and** stdout that parses as a valid
    protocol JSON document means accepted. Any other exit code that is not the
    documented rejection code is cannot-run, including exit 2 from `uv run`
    over a worktree whose `pyproject.toml` an agent broke (plan trap 9).
    """
    if timed_out:
        return _CannotRun(reason="candidate parse timed out")

    if exit_code == PARSE_CLI_REJECTED:
        return _RejectedConfig(message=stderr.rstrip())

    if exit_code != PARSE_CLI_OK:
        return _CannotRun(reason=f"non-rejection exit code {exit_code}")

    try:
        document = json.loads(stdout)
    except json.JSONDecodeError:
        return _CannotRun(
            reason="exit 0 but stdout did not parse as protocol JSON"
        )

    if not isinstance(document, dict):
        return _CannotRun(reason="exit 0 but stdout did not parse as protocol JSON")

    gates_view = document.get("gates")
    timeouts_view = document.get("timeouts", {})

    if not isinstance(gates_view, dict) or not gates_view:
        return _CannotRun(reason="protocol gates mapping is empty")
    if not all(isinstance(name, str) and isinstance(cmd, str) and cmd.strip()
               for name, cmd in gates_view.items()):
        return _CannotRun(
            reason="protocol gates mapping is not a non-empty str-to-str mapping"
        )

    if not isinstance(timeouts_view, dict) or not all(
        isinstance(name, str) and isinstance(seconds, int) and seconds > 0
        for name, seconds in timeouts_view.items()
    ):
        return _CannotRun(
            reason="protocol timeouts are not str-to-positive-int"
        )

    return _AcceptedConfig(
        gates=dict(gates_view),
        timeouts=dict(timeouts_view),
    )


class SubprocessCandidateRunner:
    """Runs the worktree's candidate parser as `uv run -q python -m ...`.

    The protocol needs **separated** stdout/stderr streams, so this runner has
    its own small subprocess plumbing rather than reusing `SubprocessGateExecutor`,
    which merges stderr into stdout. stdout is parsed as protocol JSON; stderr is
    kept for rejection and cannot-run messages.

    The same environment discipline and group-kill timeout discipline as gate
    commands apply here (FR-007): the subprocess gets `scrubbed_env()`, its own
    session, a TERM-then-KILL reclaim on timeout, and the same default deadline.
    The concurrency limiter is acquired around the whole run because a cold
    `uv run` may build a venv (plan trap 5).
    """

    def __init__(
        self,
        *,
        timeout_s: int = DEFAULT_GATE_TIMEOUT_S,
        grace_s: float = DEFAULT_KILL_GRACE_S,
        limiter: GateConcurrencyLimiter | None = None,
    ) -> None:
        self.timeout_s = timeout_s
        self.grace_s = grace_s
        self.limiter = limiter if limiter is not None else _default_limiter

    def run(self, worktree: Path, manifest: Path) -> CandidateOutcome:
        peers = self.limiter.acquire()
        try:
            return self._run_in_slot(worktree, manifest)
        finally:
            self.limiter.release()

    def _run_in_slot(self, worktree: Path, manifest: Path) -> CandidateOutcome:
        candidate_path = worktree / "factory" / "verify" / "factory_yaml.py"
        if not candidate_path.exists():
            return CandidateOutcome(
                exit_code=-1,
                stdout="",
                stderr="",
                timed_out=False,
            )

        started = time.monotonic()
        process = subprocess.Popen(
            [
                "uv",
                "run",
                "-q",
                "python",
                "-m",
                "factory.verify.factory_yaml",
                str(manifest),
            ],
            cwd=str(worktree),
            env=scrubbed_env(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )

        stdout_buffer = _TailBuffer()
        stderr_buffer = _TailBuffer()
        stdout_drain = threading.Thread(
            target=_drain,
            args=(process.stdout, stdout_buffer),
            name="candidate-parser-stdout",
            daemon=True,
        )
        stderr_drain = threading.Thread(
            target=_drain,
            args=(process.stderr, stderr_buffer),
            name="candidate-parser-stderr",
            daemon=True,
        )
        stdout_drain.start()
        stderr_drain.start()

        timed_out = False
        try:
            process.wait(timeout=self.timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._reclaim(process)

        stdout_drain.join(timeout=_DRAIN_JOIN_S)
        stderr_drain.join(timeout=_DRAIN_JOIN_S)

        return CandidateOutcome(
            exit_code=None if timed_out else process.returncode,
            stdout=stdout_buffer.text(),
            stderr=stderr_buffer.text(),
            timed_out=timed_out,
        )

    def _reclaim(self, process: subprocess.Popen[bytes]) -> None:
        """SIGTERM the candidate's process group, then SIGKILL what survives."""
        _signal_group(process, signal.SIGTERM)
        try:
            process.wait(timeout=self.grace_s)
        except subprocess.TimeoutExpired:
            pass
        _signal_group(process, signal.SIGKILL)
        process.wait()


_default_candidate_runner = SubprocessCandidateRunner()


# The runner -----------------------------------------------------------------


def run_gates(
    worktree: Path | str,
    *,
    manifest_path: Path | str | None = None,
    executor: GateExecutor | None = None,
    timeout_overrides: Mapping[str, int] | None = None,
    concurrency_limiter: GateConcurrencyLimiter | None = None,
    candidate_runner: CandidateRunner | None = None,
) -> list[GateResult]:
    """Run every gate the manifest declares, in declaration order, and report each.

    One result per declared gate — a failure or a timeout never cancels the
    gates after it, because the contract promises the caller a complete picture
    (contracts/activities.md) and a half-run suite understates what is broken.

    `manifest_path` defaults to `<worktree>/factory.yaml` but is separately
    settable: the activity receives both paths, and conflating them would make
    the manifest unreadable from anywhere but the worktree. An unusable manifest
    — absent, unparseable, or schema-invalid — returns exactly one
    `CONFIG_ERROR` result and runs nothing at all.

    `concurrency_limiter` bounds how many gates run at once across the host
    (007 FR-005): a gate acquires its slot before its process starts, so its
    wall-clock bound measures the gate's own work and never the queue it waited
    in — which is what keeps a neighbour's load from moving this node's verdict.
    Defaults to the process-level limiter, so two `run_gates` calls in two
    worker threads (the shape fan-out produces) share one bound.

    `candidate_runner` resolves the manifest: when the worktree carries a
    candidate parser it is consulted first, via a subprocess inside the
    worktree, with the worker's imported parser as fallback. A candidate
    rejection is one `CONFIG_ERROR` carrying the candidate's message; a
    candidate that cannot run falls back to today's in-process behaviour.
    """
    worktree = Path(worktree)
    manifest = (
        worktree / MANIFEST_NAME if manifest_path is None else Path(manifest_path)
    )

    # Resolve the backend early so a broken manifest still produces a CONFIG_ERROR
    # from the same code path, and so an explicit executor wins over runtime.
    backend = _resolve_gate_executor(
        executor, _read_runtime_from_manifest(manifest)
    )

    candidate_path = worktree / "factory" / "verify" / "factory_yaml.py"
    if candidate_runner is None:
        run_candidate = _default_candidate_runner.run
    else:
        run_candidate = candidate_runner
    if candidate_path.exists():
        candidate = run_candidate(worktree, manifest)
        interpreted = _interpret_candidate(
            candidate.exit_code, candidate.stdout, candidate.stderr, candidate.timed_out
        )
    else:
        interpreted = _CannotRun(reason="no candidate parser in worktree")

    if isinstance(interpreted, _AcceptedConfig):
        gates_view = interpreted.gates or {}
        timeouts_view = interpreted.timeouts or {}
        return _run_gate_list(
            worktree,
            manifest,
            gates_view,
            timeouts_view,
            executor=backend,
            timeout_overrides=timeout_overrides,
            concurrency_limiter=concurrency_limiter,
        )

    if isinstance(interpreted, _RejectedConfig):
        return [
            GateResult(
                name="config",
                command="",
                status=GateStatus.CONFIG_ERROR,
                exit_code=None,
                duration_s=0.0,
                output_tail=interpreted.message,
            )
        ]

    # cannot-run -> fallback to the worker's imported parser, byte-for-byte
    # today's behaviour, but record the candidate's failure if the worker also
    # refuses.
    try:
        config = load_factory_config(manifest)
    except FactoryConfigError as error:
        fallback = config_error_result(error)
        reason = getattr(interpreted, "reason", "")
        if reason:
            return [
                GateResult(
                    name=fallback.name,
                    command=fallback.command,
                    status=fallback.status,
                    exit_code=fallback.exit_code,
                    duration_s=fallback.duration_s,
                    output_tail=f"{fallback.output_tail}\n[candidate parser could not run: {reason}]",
                )
            ]
        return [fallback]

    return _run_gate_list_from_config(
        worktree,
        config,
        executor=backend,
        timeout_overrides=timeout_overrides,
        concurrency_limiter=concurrency_limiter,
    )


def _resolve_gate_executor(
    executor: GateExecutor | None, runtime: str | None
) -> GateExecutor:
    """Choose the gate backend from the manifest's `runtime:` when not overridden.

    An explicit `executor` is used verbatim -- tests and callers that want a
    specific backend keep control. When the manifest declares `runtime: bwrap`
    and the system binary is present, the gate runs inside the same boundary as
    the agent (US5, FR-009). Otherwise the host subprocess executor is used,
    which keeps the suite green on hosts where bwrap is not installed (trap 5).
    """
    if executor is not None:
        return executor
    if runtime == "bwrap" and BWRAP_BACKEND_BINARY.is_file():
        return BwrapGateExecutor()
    return SubprocessGateExecutor()


def _read_runtime_from_manifest(manifest: Path) -> str | None:
    """Return the manifest's `runtime:` value, or None if the manifest is unusable."""
    try:
        return load_factory_config(manifest).runtime
    except FactoryConfigError:
        return None


def resolve_gate_executor(
    worktree: Path | str,
    *,
    manifest_path: Path | str | None = None,
    executor: GateExecutor | None = None,
) -> GateExecutor:
    """Public helper for callers that need the runtime-selected backend.

    The verify activity uses this so its heartbeating wrapper wraps the same
    backend `run_gates` would have chosen (US5).
    """
    worktree = Path(worktree)
    manifest = (
        worktree / MANIFEST_NAME if manifest_path is None else Path(manifest_path)
    )
    return _resolve_gate_executor(
        executor, _read_runtime_from_manifest(manifest)
    )


def _run_gate_list(
    worktree: Path,
    manifest: Path,
    gates_view: Mapping[str, str],
    timeouts_view: Mapping[str, int],
    *,
    executor: GateExecutor,
    timeout_overrides: Mapping[str, int] | None,
    concurrency_limiter: GateConcurrencyLimiter | None,
) -> list[GateResult]:
    """Run gates from a JSON view (candidate acceptance or fallback)."""
    backend = executor
    overrides = dict(timeout_overrides or {})
    env = scrubbed_env()
    limiter = (
        concurrency_limiter
        if concurrency_limiter is not None
        else _default_limiter
    )

    results: list[GateResult] = []
    for name, command in gates_view.items():
        invocation = GateInvocation(
            name=name,
            command=command,
            cwd=worktree,
            timeout_s=_resolve_timeout(name, timeouts_view, overrides),
            env=env,
        )
        peers = limiter.acquire()
        try:
            outcome = backend.run(invocation)
        finally:
            limiter.release()
        results.append(_to_result(invocation, outcome, peers))
    return results


def _run_gate_list_from_config(
    worktree: Path,
    config,
    *,
    executor: GateExecutor,
    timeout_overrides: Mapping[str, int] | None,
    concurrency_limiter: GateConcurrencyLimiter | None,
) -> list[GateResult]:
    """Run gates from an in-process FactoryConfig (today's fallback path)."""
    backend = executor
    overrides = dict(timeout_overrides or {})
    env = scrubbed_env()
    limiter = (
        concurrency_limiter
        if concurrency_limiter is not None
        else _default_limiter
    )

    results: list[GateResult] = []
    for name, command in config.gates.items():
        invocation = GateInvocation(
            name=name,
            command=command,
            cwd=worktree,
            timeout_s=_resolve_timeout(name, config.timeouts, overrides),
            env=env,
        )
        peers = limiter.acquire()
        try:
            outcome = backend.run(invocation)
        finally:
            limiter.release()
        results.append(_to_result(invocation, outcome, peers))
    return results


def _resolve_timeout(
    name: str, declared: Mapping[str, int], overrides: Mapping[str, int]
) -> int:
    """Caller's override, else the manifest's declaration, else the default.

    The caller wins because overrides come from the verification config an
    operator is holding right now; the manifest wins over the default because
    the repo knows which of its suites is the slow one.
    """
    if name in overrides:
        return overrides[name]
    return declared.get(name, DEFAULT_GATE_TIMEOUT_S)


def _to_result(
    invocation: GateInvocation,
    outcome: ExecutionOutcome,
    concurrent_gates: int = 0,
) -> GateResult:
    """Turn one execution into the evidence the verdict truth table reads.

    `tail_output` is applied here as well as in the executor: the cap is a
    property of a `GateResult`, and a future executor across the `GateExecutor`
    seam should not be able to widen it by forgetting.

    `concurrent_gates` is the contention marker (007 FR-005): how many *other*
    gates were in flight when this one got its turn. Zero for a gate that ran
    alone; a count for one that ran alongside peers, so a slow verdict is
    auditable rather than mysterious.
    """
    if outcome.timed_out:
        status, exit_code = GateStatus.TIMEOUT, None
    elif outcome.exit_code == 0:
        status, exit_code = GateStatus.PASS, 0
    else:
        status, exit_code = GateStatus.FAIL, outcome.exit_code

    return GateResult(
        name=invocation.name,
        command=invocation.command,
        status=status,
        exit_code=exit_code,
        duration_s=outcome.duration_s,
        output_tail=tail_output(outcome.output),
        concurrent_gates=concurrent_gates,
    )
