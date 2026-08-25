"""Bring the engine container up, wait for it, and verify through it (104-US5).

*The engine container* is the Docker container `ergane install` brings up —
never bwrap's sandbox, never "a container of specs".

The host side of the onramp. The project is already rendered
(`container_project.py`) and written (`container_manifest.py`); four acts remain.

1. **Preflight the published port** (trap 6): the reference floor's
   `127.0.0.1:7233` is the *native* managed Temporal's and `temporal.address`
   defaults to it, so taking it leaves the host CLI on one Temporal and the
   engine on another, both looking fine. Refuse unless the thing answering is
   this project's own service — the check that also makes re-entry converge.
2. **`docker compose up -d`**, which reconciles rather than duplicating.
3. **Wait, bounded** — `deploy._await_registration`'s contract with a port in
   place of a registration, and a refusal naming the address and the bound.
4. **Verify through the engine** (R8): the child's stdout passed through
   unaltered and its exit code taken as the verdict, because reading its words
   would be a string contract between two versions of one program.

**Nothing here ever takes the engine down.** A readiness timeout and a failing
verify both end nonzero with the container running, because that container is
the only place either failure reproduces. `down` is `ergane uninstall`'s verb.
Every process goes through `run` and every port through `probe` (trap 11).
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

#: One compose command, `units._run_command`'s own shape.
Runner = Callable[[Sequence[str]], CommandResult]

#: One TCP question: `(address, timeout_s) -> answered`.
Probe = Callable[[str, float], bool]

#: `docker compose`, two words: hyphenated `docker-compose` is v1, a different
#: program that cannot bring this project up. US1's refusal says so by name.
COMPOSE_COMMAND: tuple[str, ...] = ("docker", "compose")

#: What install runs inside the engine. `-T` because an install script has no
#: terminal, `exec` rather than `run` because the point is the *running* engine.
ENGINE_VERIFY_ARGV: tuple[str, ...] = ("ergane", "install", "--verify")

#: Generous on purpose: the first bring-up on a host may build the image.
DEFAULT_READINESS_WAIT_S = 180.0
DEFAULT_POLL_S = 1.0

#: One attempt's own bound: a poll that blocks is not bounded by `wait_s`.
DEFAULT_PROBE_TIMEOUT_S = 1.0

#: The preflight's, shorter still — nothing has started, and a slow answer is
#: still an answer.
PREFLIGHT_PROBE_TIMEOUT_S = 0.5


def compose_argv(compose_path: Path, *arguments: str) -> tuple[str, ...]:
    """`docker compose -f <project>/compose.yaml <arguments…>`, fixed argv —
    never a shell string, so an element holding a space stays one element."""
    return (*COMPOSE_COMMAND, "-f", str(compose_path), *arguments)


def _run_compose(argv: Sequence[str]) -> CommandResult:
    """Run one compose command. **The seam every test in this story closes.**

    stdout and stderr merged, as `deploy._run_command` merges them: compose says
    most of what matters on stderr.
    """
    finished = subprocess.run(  # noqa: S603 - fixed argv, no shell
        list(argv), capture_output=True, text=True, check=False
    )
    return CommandResult(finished.returncode, finished.stdout + finished.stderr)


def _probe_address(address: str, timeout_s: float) -> bool:
    """Whether anything answers TCP at `address`. The port seam — sync because
    the installer is, and asking once because the polling is `await_address`'s.
    """
    host, _, port = address.rpartition(":")
    try:
        with socket.create_connection((host, int(port)), timeout=timeout_s):
            return True
    except (OSError, ValueError):
        return False


def published_address(project: ContainerProject) -> str:
    """The host-side address the project's published port makes reachable.

    Derived from `project.ports`, not from `temporal.address` a second time, so
    the port compose binds and the port install dials are one fact.
    """
    for port in project.ports:
        fields = port.split(":")
        if len(fields) == 3:
            return ":".join(fields[:2])
    raise OperatorError(
        "the engine container's project publishes no port, so nothing on this "
        "host could reach the engine once it is up — not `ergane build`, not "
        "this install's own verify. The port comes from `temporal.address`, "
        "which names none; re-run `ergane install` and give it one "
        "(the default is 127.0.0.1:7233).",
        code=EXIT_USER,
    )


def service_running(compose_path: Path, *, run: Runner) -> bool:
    """Whether *this project's* engine service is up, as compose sees it.

    Scoped to this project deliberately: "is something listening" and "is *our*
    engine listening" have opposite meanings at a preflight.
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

    A silent port is ours to take; one answering from our own service is a
    half-up stack re-entry converges through (US5-S3); one answering from
    anything else produces not a crash but an install that looks like it worked.
    """
    if not probe(address, timeout_s):
        return
    if service_running(compose_path, run=run):
        return
    raise OperatorError(
        f"something is already listening on {address}, and `docker compose ps` "
        f"reports this project's `{SERVICE_NAME}` service is not running — so "
        "that port belongs to something else, most likely this host's own "
        "native Temporal tier. Publishing onto it would leave the host CLI on "
        "one Temporal and the engine on another, both looking healthy.\n"
        "  remedies, either one: drain the native tier (stop its managed "
        "Temporal unit, or `ergane worker uninstall`); or set "
        "`temporal.address` to a free port, which is safe because the engine "
        "keeps its own Temporal database. Then re-run `ergane install`.",
        code=EXIT_USER,
    )


def bring_up(compose_path: Path, *, run: Runner) -> None:
    """`docker compose up -d`, which reconciles rather than duplicates.

    Detached on purpose: a wait and a verify still have to run, and an attached
    compose would own the terminal until interrupted — stopping the engine.
    """
    result = run(compose_argv(compose_path, "up", "-d"))
    if result.code != 0:
        raise OperatorError(
            f"`docker compose up -d` failed for the engine container project "
            f"at {compose_path} (exit {result.code}). Compose said:\n"
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

    A predicate, not a refusal: the last observation either way, and the caller
    words what `False` means. The final sleep is clipped to the deadline, so
    `wait_s` is the real bound and not `wait_s + poll_s`.
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

    R8, whole: stdout emitted unaltered under a header naming where it came
    from, the exit code returned as the verdict, nothing here reading the words.
    The renderer on the other side emits free text, so parsing it would be a
    contract whose failure mode is not an error but a skew that reports success.
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
    returns `None` only when the engine is up and its own verify agreed.
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
            f"the engine container did not answer on {address} within "
            f"{wait_s:g}s. It is still running so it can be diagnosed — "
            "nothing was stopped or removed.\n"
            f"  remedy: `docker compose -f {compose_path} logs {SERVICE_NAME}`, "
            "then re-run `ergane install`, which converges. `ergane uninstall` "
            "takes it down when you are done.",
            code=EXIT_USER,
        )

    if verify_through_engine(compose_path, run=runner, emit=emit) != 0:
        raise OperatorError(
            "the engine container came up, and its own verify reported "
            "failures. It is still running, deliberately, so they can be "
            "reproduced against it — nothing was stopped or removed.\n"
            "  remedy: the findings above name what did not answer; re-run "
            "`ergane install` to change the answers behind them (it "
            f"converges), or `docker compose -f {compose_path} logs "
            f"{SERVICE_NAME}` for what the engine said. `ergane uninstall` "
            "takes it down when you are done.",
            code=EXIT_USER,
        )
