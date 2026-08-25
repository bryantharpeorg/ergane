"""Bring the engine container up, wait for it, and verify through it (104-US5).

*The engine container* is the Docker container `ergane install` brings up —
never bwrap's sandbox, never "a container of specs".

This is the host side of the onramp: the project has already been rendered
(`container_project.py`) and written (`container_manifest.py`), and what remains
is four acts, in this order and for these reasons.

1. **Preflight the published port** (trap 6). The reference floor's
   `127.0.0.1:7233` is held by the *native* managed Temporal, and
   `temporal.address` defaults to exactly that. Bringing the engine up onto a
   taken port leaves the host CLI talking to one Temporal and the engine to
   another, and everything looks fine. So: probe first, and refuse unless the
   thing answering is this project's own service. That same check is what makes
   a re-run against a half-up stack converge instead of erroring (US5-S3).
2. **`docker compose up -d`.** Convergent by construction — compose reconciles
   rather than duplicating, which is the other half of idempotent re-entry.
3. **Wait, bounded.** `deploy._await_registration`'s contract with a port in
   place of a registration: an injected clock, a deadline, and a refusal that
   names the address and the bound. A wait that can hang is worse than one that
   gives up, because the operator has nothing to read either way.
4. **Verify through the engine** (R8). `ergane install --verify` is run *inside*
   the container and its stdout is passed through unaltered; the child's exit
   code is the verdict. The findings renderer emits free text with no
   machine-readable form, so a host that read those words back into a verdict
   would be holding a string-parsing contract between two versions of the same
   program — which is how a version skew becomes a silent pass.

**Nothing here ever takes the engine down.** A readiness timeout and a failing
verify both end the install nonzero with the container still running, because
the running engine is the only place either failure can be reproduced. `docker
compose down` is `ergane uninstall`'s verb (104-US7), never this module's.

Every process goes through the `run` seam and every port through `probe`, so the
whole of this file is exercised with no Docker daemon present (trap 11).
"""

from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path
from typing import Callable, Sequence

from factory.cli.errors import EXIT_USER, OperatorError
from factory.supervision.container_project import (
    COMPOSE_NAME,
    SERVICE_NAME,
    ContainerProject,
)
from factory.supervision.units import CommandResult

#: One compose command: `(argv) -> CommandResult`. The same shape
#: `units._run_command` already has, so a caller with a runner has both.
Runner = Callable[[Sequence[str]], CommandResult]

#: One TCP question: `(address, timeout_s) -> answered`.
Probe = Callable[[str, float], bool]

#: `docker compose`, two words. The hyphenated `docker-compose` is a different
#: program (v1) and cannot bring this project up; US1's refusal says so by name.
COMPOSE_COMMAND: tuple[str, ...] = ("docker", "compose")

#: What install runs inside the engine. `-T` because there is no terminal on
#: the far side of an install script, and `exec` rather than `run` because the
#: point is to ask *the running engine*, not a fresh copy of the image.
ENGINE_VERIFY_ARGV: tuple[str, ...] = ("ergane", "install", "--verify")

#: How long the engine gets to answer on its published port. Generous on
#: purpose: the first bring-up on a host may be building the image.
DEFAULT_READINESS_WAIT_S = 180.0
DEFAULT_POLL_S = 1.0

#: One TCP attempt's own bound. Short: a poll that blocks is a wait that is not
#: really bounded by `wait_s` at all.
DEFAULT_PROBE_TIMEOUT_S = 1.0

#: The preflight's bound. Shorter still — this one runs before anything has
#: started, and a slow answer is an answer.
PREFLIGHT_PROBE_TIMEOUT_S = 0.5


def compose_argv(compose_path: Path, *arguments: str) -> tuple[str, ...]:
    """`docker compose -f <project>/compose.yaml <arguments…>`.

    Fixed argv, never a shell string: every element here is a resolved path or a
    literal, and the day one of them holds a space is not the day to discover
    that this was interpolated into `sh -c`.
    """
    return (*COMPOSE_COMMAND, "-f", str(compose_path), *arguments)


def _run_compose(argv: Sequence[str]) -> CommandResult:
    """Run one compose command. **The seam every test in this story closes.**

    stdout and stderr are merged, the way `deploy._run_command` merges them:
    compose says most of what matters on stderr, and a refusal that quoted only
    stdout would quote the empty string.
    """
    finished = subprocess.run(  # noqa: S603 - fixed argv, no shell
        list(argv), capture_output=True, text=True, check=False
    )
    return CommandResult(finished.returncode, finished.stdout + finished.stderr)


def _probe_address(address: str, timeout_s: float) -> bool:
    """Whether anything answers TCP at `address`. The port seam.

    The engine-side twin of this lives at `container_supervisor._probe_temporal_
    address`; this one is sync because the installer is, and it asks once
    because the polling belongs to `await_address`.
    """
    host, _, port = address.rpartition(":")
    try:
        with socket.create_connection((host, int(port)), timeout=timeout_s):
            return True
    except (OSError, ValueError):
        return False


def published_address(project: ContainerProject) -> str:
    """The host-side address the project's published port makes reachable.

    Derived from `project.ports` rather than from `temporal.address` a second
    time: the port compose binds and the port install dials are then one fact,
    and a generator change cannot leave the installer dialling the old one.
    """
    for port in project.ports:
        fields = port.split(":")
        if len(fields) == 3:
            return ":".join(fields[:2])
    raise OperatorError(
        "the engine container's project publishes no port, so nothing on this "
        "host could reach the engine once it is up — not `ergane build`, not "
        "`ergane spec list`, not this install's own verify. That comes from "
        "`temporal.address`, which names no port; re-run `ergane install` and "
        "give it one (the default is 127.0.0.1:7233).",
        code=EXIT_USER,
    )


def service_running(compose_path: Path, *, run: Runner) -> bool:
    """Whether *this project's* engine service is up, as compose sees it.

    `--services --status running` prints service names one per line, which is
    the narrowest answer compose will give and the one least likely to change
    shape under us. The question is deliberately scoped to this project: "is
    something listening" and "is our engine listening" have opposite meanings
    at a preflight.
    """
    result = run(compose_argv(compose_path, "ps", "--services", "--status", "running"))
    return SERVICE_NAME in result.out.split()


def preflight_published_port(
    compose_path: Path,
    address: str,
    *,
    run: Runner,
    probe: Probe,
    timeout_s: float = PREFLIGHT_PROBE_TIMEOUT_S,
) -> None:
    """Refuse before `up` if the published port is somebody else's (trap 6).

    A silent port is ours to take. A port answering from this project's own
    service is a half-up stack, and re-entry converges through it (US5-S3). A
    port answering from anything else is the collision that is worth the whole
    of this function: on the reference floor it is the native managed Temporal,
    and the failure it produces is not a crash — it is an install that looks
    like it worked.
    """
    if not probe(address, timeout_s):
        return
    if service_running(compose_path, run=run):
        return
    raise OperatorError(
        f"something is already listening on {address}, and `docker compose ps` "
        f"reports this project's `{SERVICE_NAME}` service is not running — so "
        "that port belongs to something else, most likely this host's own "
        "native Temporal tier. Publishing the engine onto it would leave the "
        "host CLI talking to one Temporal and the engine to another, and both "
        "would look healthy.\n"
        "  remedies, either one: drain the native tier (stop its managed "
        "Temporal unit, or `ergane worker uninstall`) and re-run `ergane "
        "install`; or re-run `ergane install` and set `temporal.address` to a "
        "free port, which is safe because the engine keeps its own Temporal "
        "database and the two tiers share no SQLite file.",
        code=EXIT_USER,
    )


def bring_up(compose_path: Path, *, run: Runner) -> None:
    """`docker compose up -d`, which reconciles rather than duplicates.

    Detached on purpose: the installer has a readiness wait and a verify still
    to run, and an attached compose would own the terminal until the operator
    interrupted it — which would also stop the engine.
    """
    result = run(compose_argv(compose_path, "up", "-d"))
    if result.code != 0:
        raise OperatorError(
            f"`docker compose up -d` failed for the engine container project at "
            f"{compose_path} (exit {result.code}). Compose said:\n"
            f"{result.out.strip()}\n"
            "  nothing was stopped or removed; fix what it names and re-run "
            "`ergane install`, which converges.",
            code=EXIT_USER,
        )


def await_address(
    address: str,
    *,
    wait_s: float,
    poll_s: float,
    now: Callable[[], float],
    sleep: Callable[[float], None],
    probe: Probe,
    probe_timeout_s: float = DEFAULT_PROBE_TIMEOUT_S,
) -> bool:
    """Wait, bounded, for `address` to answer — `_await_registration`'s contract.

    A predicate, not a refusal: it returns the last observation either way and
    lets the caller word what a `False` means, exactly as
    `deploy._await_registration` returns its last snapshot on the timeout path.
    The final sleep is clipped to the deadline, so `wait_s` is the real bound
    and not `wait_s + poll_s`.
    """
    deadline = now() + wait_s
    while True:
        if probe(address, probe_timeout_s):
            return True
        remaining = deadline - now()
        if remaining <= 0:
            return False
        sleep(min(poll_s, remaining))


def verify_through_engine(
    compose_path: Path,
    *,
    run: Runner,
    emit: Callable[[str], None] = print,
) -> int:
    """Run the verify battery *inside* the engine and pass its output through.

    R8, and the whole of it: the child's stdout is emitted unaltered under a
    header naming where it came from, and the child's **exit code** is returned
    as the verdict. Nothing here reads the child's words. The renderer on the
    other side emits free text with no machine-readable form, so parsing it
    would be a string contract between two versions of the same program — and
    the failure mode of such a contract is not an error, it is a version skew
    that reports success. Unreadable output is the correct symptom.
    """
    result = run(compose_argv(compose_path, "exec", "-T", SERVICE_NAME, *ENGINE_VERIFY_ARGV))
    emit("")
    emit(
        f"verifying the control plane inside the engine container "
        f"(`{SERVICE_NAME}`), which is where the factory will actually run:"
    )
    emit(result.out)
    return result.code


def bring_up_and_verify(
    project: ContainerProject,
    *,
    run: Runner | None = None,
    probe: Probe | None = None,
    now: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    emit: Callable[[str], None] = print,
    wait_s: float = DEFAULT_READINESS_WAIT_S,
    poll_s: float = DEFAULT_POLL_S,
) -> None:
    """Preflight, up, wait, verify — and leave the engine up whatever happens.

    Raises `OperatorError` on every failure path, each naming a remedy, and
    returns `None` on the one path where the engine is up and its own verify
    agreed. The seams default here rather than at each step so a caller wires
    one set of them, and a test drives all four with no daemon present.
    """
    runner = _run_compose if run is None else run
    port_probe = _probe_address if probe is None else probe
    clock = time.monotonic if now is None else now
    wait = time.sleep if sleep is None else sleep

    compose_path = project.directory / COMPOSE_NAME
    address = published_address(project)

    preflight_published_port(compose_path, address, run=runner, probe=port_probe)

    emit(f"bringing the engine container up from {compose_path}...")
    bring_up(compose_path, run=runner)

    emit(f"waiting up to {wait_s:g}s for the engine to answer on {address}...")
    if not await_address(
        address,
        wait_s=wait_s,
        poll_s=poll_s,
        now=clock,
        sleep=wait,
        probe=port_probe,
    ):
        raise OperatorError(
            f"the engine container did not answer on {address} within {wait_s:g}s. "
            "It has been left running so it can be diagnosed — nothing was "
            "stopped or removed.\n"
            f"  remedy: read what it said with `docker compose -f {compose_path} "
            f"logs {SERVICE_NAME}`, then re-run `ergane install`, which converges. "
            "`ergane uninstall` takes it down when you are done.",
            code=EXIT_USER,
        )

    if verify_through_engine(compose_path, run=runner, emit=emit) != 0:
        raise OperatorError(
            "the engine container came up, and its own verify reported failures. "
            "It is still running, deliberately, so those failures can be "
            "reproduced against it — nothing was stopped or removed.\n"
            "  remedy: the findings above name what did not answer; re-run "
            "`ergane install` to change the answers behind them (it converges), "
            f"or read `docker compose -f {compose_path} logs {SERVICE_NAME}` for "
            "what the engine itself said. `ergane uninstall` takes it down when "
            "you are done.",
            code=EXIT_USER,
        )
