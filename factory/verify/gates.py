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

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Mapping, Protocol

from factory.verify.factory_yaml import (
    MANIFEST_NAME,
    FactoryConfigError,
    config_error_result,
    load_factory_config,
)
from factory.verify.models import GateResult, GateStatus, VerificationConfig

#: Deadline for a gate the manifest gives no `timeouts` entry. Sourced from
#: `VerificationConfig` rather than restated: that field is the knob an operator
#: edits, and a second literal here would let tuning it silently do nothing.
DEFAULT_GATE_TIMEOUT_S: int = VerificationConfig().gate_timeout_s

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

_READ_CHUNK = 64 * 1024

#: The drain trims back to the tail once it holds this multiple of the limit —
#: bounded memory without a slice on every chunk.
_TRIM_FACTOR = 4

#: How long to wait for the drain thread after the gate's group is gone. It ends
#: at EOF, which the SIGKILL guarantees; the bound is only so a process that
#: escaped its group cannot hang the verification.
_DRAIN_JOIN_S = 5.0


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


# The runner -----------------------------------------------------------------


def run_gates(
    worktree: Path | str,
    *,
    manifest_path: Path | str | None = None,
    executor: GateExecutor | None = None,
    timeout_overrides: Mapping[str, int] | None = None,
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
    """
    worktree = Path(worktree)
    manifest = (
        worktree / MANIFEST_NAME if manifest_path is None else Path(manifest_path)
    )

    try:
        config = load_factory_config(manifest)
    except FactoryConfigError as error:
        return [config_error_result(error)]

    backend = executor if executor is not None else SubprocessGateExecutor()
    overrides = dict(timeout_overrides or {})
    env = scrubbed_env()

    results: list[GateResult] = []
    for name, command in config.gates.items():
        invocation = GateInvocation(
            name=name,
            command=command,
            cwd=worktree,
            timeout_s=_resolve_timeout(name, config.timeouts, overrides),
            env=env,
        )
        results.append(_to_result(invocation, backend.run(invocation)))
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


def _to_result(invocation: GateInvocation, outcome: ExecutionOutcome) -> GateResult:
    """Turn one execution into the evidence the verdict truth table reads.

    `tail_output` is applied here as well as in the executor: the cap is a
    property of a `GateResult`, and a future executor across the `GateExecutor`
    seam should not be able to widen it by forgetting.
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
    )
