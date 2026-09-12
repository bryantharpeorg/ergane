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

**A gate that writes is measured, not stopped.** The judge's patch is assembled
from the same worktree the gates just ran in, so a gate that writes into it has
edited its own evidence. Every execution is bracketed by a content snapshot
(`factory/verify/worktree_snapshot.py`); a gate that changed tracked content or
added an unignored path is reported `DIRTIED_WORKTREE` with the paths on its
result, and one that wrote only ignored paths is untouched, because a path the
judge never sees is not a path the gate can have moved. The worktree stays bound
writable throughout — this observes, and preventing it would break every gate
that legitimately needs a scratch file.

Execution sits behind the narrow `GateExecutor` seam (R3) so `ContainerExecutor`
can replace `SubprocessGateExecutor` later without touching verdict logic — and
so tests can assert the timeout the runner *resolved* without waiting out a
ten-minute default to prove it is ten minutes.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import IO, Mapping, Protocol, Sequence

from factory.verify.artifact_capture import (
    CaptureProvenance,
    SourceStatus,
    capture_source,
    observe_source,
)
from factory.verify.factory_yaml import (
    MANIFEST_NAME,
    PARSE_CLI_OK,
    PARSE_CLI_REJECTED,
    FactoryConfigError,
    config_error_result,
    load_factory_config,
)
from factory.verify.gate_annotation import annotate_install_advice
from factory.verify.models import (
    ArtifactDeclaration,
    ArtifactType,
    CacheDeclaration,
    GateArtifact,
    GateResult,
    GateStatus,
    VerificationConfig,
)
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
    system_tree_argv,
)
from factory.verify.worktree_snapshot import (
    TreeSnapshot,
    changes_between,
    snapshot_tree,
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

#: The largest artifact the gate boundary will copy (134 FR-015).
ARTIFACT_STORED_BYTES_LIMIT = 1024 * 1024

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

logger = logging.getLogger(__name__)

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
    """A candidate acceptance: the subset of the protocol the runner consumes.

    "The subset the runner consumes" is the whole hazard: a field the manifest
    parser reads and the parser CLI emits still arrives here as nothing unless
    it is named. `writes` is carried for that reason (084 FR-012) — the runner
    this shape feeds is the one a worktree carrying its own parser selects,
    which is every Ergane node, so a declaration that stopped at
    `FactoryConfig` would be parsed, stored, emitted and never read.
    """

    kind: str = "accepted"
    gates: dict[str, str] | None = None
    timeouts: dict[str, int] | None = None
    writes: dict[str, bool] | None = None
    artifacts: tuple[ArtifactDeclaration, ...] | None = None


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


@dataclass(frozen=True)
class CacheBind:
    """One cache mount the boundary carries, and the variable that names it.

    A pair of paths was enough while there was exactly one cache: the uv one,
    with `UV_CACHE_DIR` set for it unconditionally beside the loop that emitted
    it. It stops being enough the moment a second cache exists, because the
    variable is a property of the *bind* and not of the boundary — the loop that
    said `--setenv UV_CACHE_DIR <dest>` for every entry would, with two entries,
    point uv at the second one. Carrying the name here is what makes that
    unspellable rather than merely avoided (101 FR-008).

    `env` is `None` for a cache whose tool finds it without being told.
    """

    source: str
    dest: str
    env: str | None = None


class BwrapGateExecutor:
    """Runs a gate inside the same bubblewrap boundary as the agent (US5).

    The mount set is deliberately minimal: a read-only system tree, a tmpfs
    for the gate's scratch state, the node worktree writable, the parent repo's
    `.git` writable for git plumbing, and read-only toolchain leaves. Network
    is intentionally not unshared — egress is out of scope — and the gate runs
    in its own PID namespace with `--die-with-parent` so the existing group-kill
    path reaches the whole tree.

    "A read-only system tree" is derived per host, not declared: see
    `system_tree_argv`, which this boundary and the agent's share.
    """

    def __init__(
        self,
        *,
        grace_s: float = DEFAULT_KILL_GRACE_S,
        system_root: Path | str = Path("/"),
        caches: Sequence[CacheDeclaration] = (),
    ) -> None:
        self.grace_s = grace_s
        #: The host whose system layout the mount set is read from — the real
        #: root in production, a supplied tree in a test. Same seam, same
        #: default, as the agent boundary's.
        self.system_root = Path(system_root)
        #: The caches the target repository declared (101 FR-004), already
        #: bounded to the operator's home by the parser that read them. Empty by
        #: default, which is what every caller that predates the key passes and
        #: what every manifest that exists declares: the uv bind, alone, exactly
        #: as before (FR-006). Read from the manifest by `run_gates` rather than
        #: from the process environment — which repository's caches these are is
        #: a governing value, and it comes from the declaration that owns it.
        self.caches = tuple(caches)

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

        # Discovery happens while the argv is assembled — of the toolchain and
        # of the system tree alike, `SystemTreeError` being a `ToolchainError`
        # for exactly this reason — so a host missing a tool, or holding
        # something unmountable at a system path, is refused by name here,
        # before the fork, instead of reaching
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

        argv: list[str] = [str(BWRAP_BACKEND_BINARY)]

        # The system tree, read off the host by the same derivation the agent
        # boundary uses (`system_tree_argv`) rather than written out here a
        # second time. The two copies this replaces were byte-identical,
        # including a comment claiming which system symlinks exist "on this
        # host" — which is how both boundaries came to be wrong about the same
        # machine at the same time. Emitted before `binds`, so no bind can
        # cover a symlink's path first.
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

        # The package caches are writable, and are the only binds outside the
        # worktree that are: see `_cache_binds`.
        cache_binds = self._cache_binds()
        for cache in cache_binds:
            binds.append(("--bind", cache.source, cache.dest))

        argv.extend(ordered_binds(binds))
        argv.extend(["--chdir", str(worktree)])

        # A factory-owned home for the gate, writable but not the operator's.
        argv.extend(["--tmpfs", str(home)])
        argv.extend(["--setenv", "HOME", str(home)])
        # Each cache's own variable, beside its own bind and pointing at its own
        # destination — the same `--setenv` path `HOME` above takes. This loop
        # used to say `UV_CACHE_DIR` outright, which was correct only while the
        # list could hold one entry; a second entry would have sent uv to it.
        for cache in cache_binds:
            if cache.env is not None:
                argv.extend(["--setenv", cache.env, cache.dest])

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

        # A runner that lives inside the system tree needs NOTHING from this
        # method: `system_tree_argv` ro-binds `/usr` wholesale, and that bind
        # already carries the launcher symlink, its target and its whole
        # ancestry. Emitting the `--symlink` anyway is not merely redundant —
        # bwrap refuses to create a symlink where the bound tree already has
        # one, and the gate dies before running anything:
        #
        #   bwrap: Can't make symlink at /usr/bin/claude: existing destination
        #     is ../lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe
        #
        # Measured 2026-08-26 in the demo container, where npm installed the
        # runner as `/usr/bin/claude`: all four attempts of the demo's story
        # gate-FAILED in ~8ms each on this line while the agent boundary —
        # which ro-binds over the same path instead of symlinking — ran fine.
        # On the floor the runner is `~/.local/bin/claude`, no bind covers it,
        # and the symlink is what keeps nested gates resolving the versioned
        # install; that path is unchanged.
        def _inside_system_tree(path: Path) -> bool:
            return str(path).startswith(str(self.system_root / "usr") + "/")

        if runner is not None and _inside_system_tree(runner.found_at):
            if root is not None and not _inside_system_tree(root):
                binds.append(("--ro-bind", str(root), str(root)))
            return binds

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

    def _cache_binds(self) -> list[CacheBind]:
        """The package caches, writable, so a gate resolves as it does on the host.

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

        **Every word above was true of npm, of a browser download cache, of any
        package world, and the implementation was one literal path.** 101 FR-004
        makes the set declarable, and the three properties the paragraphs above
        argue for are properties of *each* bind rather than of the uv one:

        - **writable**, so `--bind` and never `--ro-bind`, for every entry;
        - **conditional on existence**, because a host that has never run this
          gate has no cache to bind and refusing there would turn a cold host
          into a failing one (FR-005). A declared absence is logged rather than
          swallowed: the uv path is the factory's own guess, while a declared one
          is something an operator asked for, and silently not doing it would
          present later as a gate that is merely slow;
        - **paired with its variable**, carried on the `CacheBind` itself so the
          pairing cannot drift to whichever entry the emitting loop ends on.

        The uv default is emitted first and unconditionally, from the same
        expression it always was — not merged into the declared list, not
        re-derived from it. A repository that declares nothing gets a list
        identical to the one it got before this key existed, which is FR-006 and
        is the regression the whole fleet would otherwise pay for.
        """
        binds: list[CacheBind] = []

        cache = Path.home() / ".cache" / "uv"
        if cache.is_dir():
            binds.append(CacheBind(str(cache), str(cache), "UV_CACHE_DIR"))

        for declared in self.caches:
            if not Path(declared.path).is_dir():
                logger.warning(
                    "declared cache %s is not a directory on this host; the "
                    "gate runs without it",
                    declared.path,
                )
                continue
            binds.append(CacheBind(declared.path, declared.path, declared.env))

        return binds

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
    writes_view = document.get("writes", {})
    artifacts_view = document.get("artifacts", [])

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

    # `type(...) is not bool` for the reason the manifest parser spells the same
    # check that way: `isinstance(True, int)` is true, so a loose check here
    # would read a candidate's `writes: {test: 1}` as a declaration.
    if not isinstance(writes_view, dict) or not all(
        isinstance(name, str) and type(declared) is bool
        for name, declared in writes_view.items()
    ):
        return _CannotRun(reason="protocol writes are not str-to-bool")

    if not isinstance(artifacts_view, list) or not all(
        isinstance(artifact, dict)
        and isinstance(artifact.get("gate"), str)
        and isinstance(artifact.get("path"), str)
        and isinstance(artifact.get("type"), str)
        for artifact in artifacts_view
    ):
        return _CannotRun(reason="protocol artifacts are not valid declarations")

    try:
        declarations = tuple(
            ArtifactDeclaration(
                gate=artifact["gate"],
                path=artifact["path"],
                type=ArtifactType(artifact["type"]),
            )
            for artifact in artifacts_view
        )
    except ValueError:
        return _CannotRun(reason="protocol artifacts contain an unknown type")

    return _AcceptedConfig(
        gates=dict(gates_view),
        timeouts=dict(timeouts_view),
        writes=dict(writes_view),
        artifacts=declarations,
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
    artifact_destination: Path | str | None = None,
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

    Every gate is watched for what it did to the worktree (084 FR-001): a gate
    whose command succeeded but whose execution changed tracked content or added
    an unignored path is reported `DIRTIED_WORKTREE`, carrying those paths on
    `worktree_writes`, and a gate that failed or timed out keeps that status and
    records them anyway. A snapshot git refuses is never read as a clean tree.

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
        executor, _read_boundary_from_manifest(manifest)
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
        writes_view = interpreted.writes or {}
        artifacts_view = interpreted.artifacts or {}
        return _run_gate_list(
            worktree,
            manifest,
            gates_view,
            timeouts_view,
            writes_view,
            artifacts_view,
            executor=backend,
            timeout_overrides=timeout_overrides,
            concurrency_limiter=concurrency_limiter,
            artifact_destination=artifact_destination,
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
        artifact_destination=artifact_destination,
    )


def _resolve_gate_executor(
    executor: GateExecutor | None, boundary: "_BoundaryDeclarations"
) -> GateExecutor:
    """Choose the gate backend from the manifest's `runtime:` when not overridden.

    An explicit `executor` is used verbatim -- tests and callers that want a
    specific backend keep control. When the manifest declares `runtime: bwrap`
    and the system binary is present, the gate runs inside the same boundary as
    the agent (US5, FR-009). Otherwise the host subprocess executor is used,
    which keeps the suite green on hosts where bwrap is not installed (trap 5).

    The declared caches ride with the choice rather than beside it (101 FR-004),
    because they are only meaningful to the backend that has a mount set: the
    subprocess executor runs on the host, where the operator's caches are already
    where the tools expect them, and there is no boundary for anything to cross.
    """
    if executor is not None:
        return executor
    if boundary.runtime == "bwrap" and BWRAP_BACKEND_BINARY.is_file():
        return BwrapGateExecutor(caches=boundary.caches)
    return SubprocessGateExecutor()


@dataclass(frozen=True)
class _BoundaryDeclarations:
    """The manifest facts the gate boundary is assembled from."""

    runtime: str | None = None
    caches: tuple[CacheDeclaration, ...] = ()


def _read_boundary_from_manifest(manifest: Path) -> _BoundaryDeclarations:
    """Read `runtime:` and `caches:` — which boundary, and what it carries.

    One parse for both, because they are two halves of one decision and two
    reads could disagree about a manifest edited between them. An unusable
    manifest yields no declarations at all rather than invented ones: the caller
    is about to turn the very same `FactoryConfigError` into the `CONFIG_ERROR`
    result that fails the node, so nothing here is deciding more than which
    backend gets to print it.
    """
    try:
        config = load_factory_config(manifest)
    except FactoryConfigError:
        return _BoundaryDeclarations()
    return _BoundaryDeclarations(runtime=config.runtime, caches=config.caches)


def resolve_gate_executor(
    worktree: Path | str,
    *,
    manifest_path: Path | str | None = None,
    executor: GateExecutor | None = None,
) -> GateExecutor:
    """Public helper for callers that need the runtime-selected backend.

    The verify activity uses this so its heartbeating wrapper wraps the same
    backend `run_gates` would have chosen (US5) — which now includes the caches
    that backend carries, so the wrapped boundary and the one `run_gates` builds
    cannot mount different things.
    """
    worktree = Path(worktree)
    manifest = (
        worktree / MANIFEST_NAME if manifest_path is None else Path(manifest_path)
    )
    return _resolve_gate_executor(
        executor, _read_boundary_from_manifest(manifest)
    )


def _run_gate_list(
    worktree: Path,
    manifest: Path,
    gates_view: Mapping[str, str],
    timeouts_view: Mapping[str, int],
    writes_view: Mapping[str, bool] | None = None,
    artifacts_view: Sequence[ArtifactDeclaration]
    | Mapping[str, Sequence[ArtifactDeclaration]]
    | None = None,
    *,
    executor: GateExecutor,
    timeout_overrides: Mapping[str, int] | None,
    concurrency_limiter: GateConcurrencyLimiter | None,
    artifact_destination: Path | str | None = None,
) -> list[GateResult]:
    """Run gates from a JSON view (candidate acceptance or fallback).

    `writes_view` is the third view lifted off the candidate acceptance (084
    FR-012): which gates the manifest declared as legitimate writers. It is
    defaulted rather than required because a caller holding only gates and
    timeouts is holding a manifest that declared nothing, which is what an
    absent `writes:` block means everywhere else.
    """
    backend = executor
    declared = dict(writes_view or {})
    if isinstance(artifacts_view, Mapping):
        artifacts = dict(artifacts_view)
    else:
        artifacts = {
            artifact.gate: tuple(
                entry for entry in (artifacts_view or ()) if entry.gate == artifact.gate
            )
            for artifact in (artifacts_view or ())
        }
    overrides = dict(timeout_overrides or {})
    env = scrubbed_env()
    limiter = (
        concurrency_limiter
        if concurrency_limiter is not None
        else _default_limiter
    )

    results: list[GateResult] = []
    before = snapshot_tree(worktree, env=env)
    for name, command in gates_view.items():
        invocation = GateInvocation(
            name=name,
            command=command,
            cwd=worktree,
            timeout_s=_resolve_timeout(name, timeouts_view, overrides),
            env=env,
        )
        result, before = _run_watched(
            invocation,
            backend=backend,
            limiter=limiter,
            before=before,
            env=env,
            writes_declared=declared.get(name, False),
            artifacts=artifacts.get(name, ()),
            artifact_destination=artifact_destination,
        )
        results.append(result)
    return results


def _run_gate_list_from_config(
    worktree: Path,
    config,
    *,
    executor: GateExecutor,
    timeout_overrides: Mapping[str, int] | None,
    concurrency_limiter: GateConcurrencyLimiter | None,
    artifact_destination: Path | str | None = None,
) -> list[GateResult]:
    """Run gates from an in-process FactoryConfig (today's fallback path)."""
    backend = executor
    # `getattr` rather than an attribute read: this runner is also handed
    # config objects a caller built, and a shape that predates 084 declares
    # nothing rather than failing here.
    declared = dict(getattr(config, "writes", None) or {})
    artifacts = {
        artifact.gate: tuple(
            entry for entry in (getattr(config, "artifacts", None) or ())
            if entry.gate == artifact.gate
        )
        for artifact in (getattr(config, "artifacts", None) or ())
    }
    overrides = dict(timeout_overrides or {})
    env = scrubbed_env()
    limiter = (
        concurrency_limiter
        if concurrency_limiter is not None
        else _default_limiter
    )

    results: list[GateResult] = []
    before = snapshot_tree(worktree, env=env)
    for name, command in config.gates.items():
        invocation = GateInvocation(
            name=name,
            command=command,
            cwd=worktree,
            timeout_s=_resolve_timeout(name, config.timeouts, overrides),
            env=env,
        )
        result, before = _run_watched(
            invocation,
            backend=backend,
            limiter=limiter,
            before=before,
            env=env,
            writes_declared=declared.get(name, False),
            artifacts=artifacts.get(name, ()),
            artifact_destination=artifact_destination,
        )
        results.append(result)
    return results


def _run_watched(
    invocation: GateInvocation,
    *,
    backend: GateExecutor,
    limiter: GateConcurrencyLimiter,
    before: TreeSnapshot,
    env: Mapping[str, str],
    writes_declared: bool = False,
    artifacts: Sequence[ArtifactDeclaration] = (),
    artifact_destination: Path | str | None = None,
) -> tuple[GateResult, TreeSnapshot]:
    """Run one gate and report what running it did to the worktree (084 FR-001).

    The two gate-list runners above are near-identical twins, and which one a
    repo takes is decided by whether its worktree carries a candidate parser —
    so the snapshotting lives here, in the one body both of them call, rather
    than being written out twice and drifting. It wraps
    `backend.run(invocation)` for the same reason at the other axis: that is the
    single line `SubprocessGateExecutor`, `BwrapGateExecutor` and production's
    `_HeartbeatingExecutor` (`factory/activities/verify_activities.py:231-258`)
    all pass through, and a check inside any one of them is bypassed by the
    other two. This observes; it does not prevent — the worktree stays bound
    writable on purpose (`:640-645`), because gates that write scratch files are
    legitimate and only their effect on the judge's patch is not.

    Two things are deliberately outside the measurement. The limiter slot is
    released before the second snapshot, because holding a host-wide slot for a
    tree walk would make a gate's queue somebody else's wall clock; and
    `duration_s` stays the executor's, because it measures the gate's command
    and not the factory's bookkeeping. The "after" snapshot is returned so it
    becomes the next gate's "before": N gates cost N+1 snapshots, not 2N, and
    every path is attributed to exactly one gate.

    `writes_declared` says the manifest named this gate as a legitimate writer
    (084 FR-010). It is decided by the two runners, which is where the manifest
    is, and passed down rather than looked up here: the snapshot is taken and
    the paths are recorded identically either way, and only the verdict moves.
    """
    baselines: Mapping[str, object] = {}
    if artifact_destination is not None:
        baselines = {
            declaration.path: observe_source(
                invocation.cwd,
                declaration.path,
                byte_limit=ARTIFACT_STORED_BYTES_LIMIT,
            )
            for declaration in artifacts
        }
    peers = limiter.acquire()
    try:
        outcome = backend.run(invocation)
    finally:
        limiter.release()

    after = snapshot_tree(invocation.cwd, env=env)
    change = changes_between(invocation.cwd, before, after, env=env)
    result = _to_result(
        invocation,
        outcome,
        peers,
        worktree_writes=change.paths,
        snapshot_error=change.error,
        writes_declared=writes_declared,
        artifacts=artifacts,
    )
    artifacts_record = _collect_artifacts(
        invocation,
        artifacts,
        destination=artifact_destination,
        baselines=baselines,
    )
    result = replace(result, artifacts=artifacts_record)
    # Carried forward even when it is an error: a gate that ran while the check
    # had no readable baseline cannot be vouched for either, and fail-closed is
    # this module's rule everywhere else.
    return result, after


def _resolve_artifact_destination(
    destination: Path | str | None, worktree: Path
) -> Path | None:
    """Validate the explicit destination the caller handed this collector."""
    if destination is None:
        return None
    candidate = Path(destination)
    if not candidate.is_absolute():
        raise ValueError("artifact destination must be absolute")
    resolved = candidate.resolve(strict=False)
    if resolved == worktree or worktree in resolved.parents:
        raise ValueError("artifact destination must be outside the watched worktree")
    return resolved


def _write_stored_artifact(stored_path: Path, payload: bytes) -> None:
    """Publish one capture without exposing a partial file."""
    temporary = stored_path.with_name(f".{stored_path.name}.tmp")
    descriptor = -1
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
        )
        with os.fdopen(descriptor, "wb") as stored:
            descriptor = -1
            stored.write(payload)
        os.replace(temporary, stored_path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _collect_artifacts(
    invocation: GateInvocation,
    declarations: Sequence[ArtifactDeclaration],
    *,
    destination: Path | str | None,
    baselines: Mapping[str, object],
) -> tuple[GateArtifact, ...]:
    """Collect declared sources through the bounded capture boundary.

    Collection happens after the gate's closing snapshot: a destination write
    belongs to the platform, not to the next gate's `worktree_writes`. Only a
    stable permitted capture is copied; every absent, oversized, unsafe or
    unstable source remains a record with its own refusal reason.
    """
    try:
        resolved = _resolve_artifact_destination(destination, invocation.cwd)
    except ValueError as error:
        return tuple(
            GateArtifact(
                gate=declaration.gate,
                path=declaration.path,
                type=declaration.type,
                present=False,
                capture_status=SourceStatus.UNAVAILABLE,
                provenance=CaptureProvenance.UNKNOWN,
                reason=str(error),
            )
            for declaration in declarations
        )
    if resolved is None:
        return ()

    records: list[GateArtifact] = []
    for declaration in declarations:
        baseline = baselines.get(declaration.path)
        capture = capture_source(
            invocation.cwd,
            declaration.path,
            byte_limit=ARTIFACT_STORED_BYTES_LIMIT,
            baseline=baseline,
        )
        stored_path: Path | None = None
        if capture.status is SourceStatus.PERMITTED and capture.bytes is not None:
            stored_path = resolved / invocation.name / declaration.path
            stored_path.parent.mkdir(parents=True, exist_ok=True)
            _write_stored_artifact(stored_path, capture.bytes)

        records.append(
            GateArtifact(
                gate=declaration.gate,
                path=declaration.path,
                type=declaration.type,
                present=capture.status is not SourceStatus.ABSENT,
                capture_status=capture.status,
                provenance=capture.provenance,
                size=capture.size,
                stored_path=str(stored_path) if stored_path is not None else None,
                digest=capture.digest,
                reason=capture.reason,
            )
        )
    return tuple(records)


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
    *,
    worktree_writes: tuple[str, ...] = (),
    snapshot_error: str = "",
    writes_declared: bool = False,
    artifacts: Sequence[ArtifactDeclaration] = (),
) -> GateResult:
    """Turn one execution into the evidence the verdict truth table reads.

    `tail_output` is applied here as well as in the executor: the cap is a
    property of a `GateResult`, and a future executor across the `GateExecutor`
    seam should not be able to widen it by forgetting.

    `concurrent_gates` is the contention marker (007 FR-005): how many *other*
    gates were in flight when this one got its turn. Zero for a gate that ran
    alone; a count for one that ran alongside peers, so a slow verdict is
    auditable rather than mysterious.

    `worktree_writes` and `snapshot_error` are what the worktree watch observed
    (084). The status ladder puts the *command's* verdict first: a gate that
    timed out or exited non-zero keeps that status and that exit code, because
    it is the more actionable headline, and it still records what it wrote so
    the picture stays complete (FR-005). Only a gate that succeeded can be
    demoted to `DIRTIED_WORKTREE`, and it is demoted for either finding — paths
    written, or a snapshot git refused — because a tree the check could not read
    is a tree it may not report as clean (FR-006). Git's own message joins the
    output tail rather than replacing it: the gate's output is where the gate's
    explanation is.

    `writes_declared` is the target repo's manifest saying this gate writes on
    purpose (084 FR-010), and it moves exactly one thing: a gate that succeeded
    and wrote keeps PASS instead of being demoted. It does not move the
    recording — the paths are still on the result, flagged declared, because an
    opt-out that omitted them would be an opt-out nobody could see. It does not
    cover a snapshot the check could not read either: declaring what a gate
    writes is not a claim about a tree git refused, and fail-closed is this
    module's rule wherever the evidence is missing rather than merely expected.
    """
    if outcome.timed_out:
        status, exit_code = GateStatus.TIMEOUT, None
    elif outcome.exit_code != 0:
        status, exit_code = GateStatus.FAIL, outcome.exit_code
    elif snapshot_error:
        status, exit_code = GateStatus.DIRTIED_WORKTREE, 0
    elif not writes_declared and tuple(
        path
        for path in worktree_writes
        if path not in {artifact.path for artifact in artifacts}
    ):
        status, exit_code = GateStatus.DIRTIED_WORKTREE, 0
    else:
        status, exit_code = GateStatus.PASS, 0

    tail = tail_output(outcome.output)
    if snapshot_error:
        note = f"[worktree snapshot failed: {snapshot_error}]"
        tail = tail_output(f"{tail}\n{note}" if tail else note)

    # 101 FR-009. A gate that failed while a tool told the agent to install a
    # toolchain is the one failure whose own advice sends the next attempt
    # backwards: the install already ran, in a `HOME` the boundary replaced with
    # a tmpfs. The correction is appended here rather than in an executor
    # because this is the single line every backend's outcome passes through —
    # `SubprocessGateExecutor`, `BwrapGateExecutor` and the activity's
    # `_HeartbeatingExecutor` alike — and it is re-tailed rather than appended
    # blind so the cap stays a property of a `GateResult`. Re-tailing keeps the
    # note: it is at the end, so the cut lands on the noise ahead of it. Only a
    # command that failed is annotated — a green suite whose output happens to
    # quote the advice is not a toolchain failure, and a `HOME` lecture on a
    # PASS row is the noise this signature set is kept small to avoid.
    if status in (GateStatus.FAIL, GateStatus.TIMEOUT):
        tail = tail_output(annotate_install_advice(tail))

    return GateResult(
        name=invocation.name,
        command=invocation.command,
        status=status,
        exit_code=exit_code,
        duration_s=outcome.duration_s,
        output_tail=tail,
        concurrent_gates=concurrent_gates,
        worktree_writes=worktree_writes,
        writes_declared=writes_declared,
    )
