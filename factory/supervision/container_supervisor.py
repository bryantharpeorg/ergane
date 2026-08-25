"""US2: container entrypoint that supervises the three engine children.

This is the init process inside the Ergane container.  It starts the Temporal
dev server, waits for the configured address to answer, starts the worker and
the notify bridge, forwards signals to all children, and exits loudly naming
the first child that died.

The command lines assembled here intentionally avoid `python -`: a 2026-08-12
cleanup sweep ran `pkill -f "python -"` and matched the worker's own command
line (`factory/supervision/temporal_server.py:9-12`).  Using `python3 -m`
keeps the visible argv free of that substring.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Awaitable, Callable, Mapping, Protocol, Sequence

from factory.registry import DEFAULT_REGISTRY_REL, load_registry, resolve_state_home

logger = logging.getLogger(__name__)

#: The three children supervised inside the container, declared in one place.
#: This mirrors `factory/supervision/units.py:115-119` but is a separate fact:
#: systemd's module mapping and the container's are allowed to agree today while
#: remaining independently changeable.
_CHILDREN: dict[str, str] = {
    "temporal": "factory.supervision.temporal_server",
    "worker": "factory.worker",
    "bridge": "factory.notify.service",
}

DEFAULT_TEMPORAL_PORT = 7233

#: The *host* alone, used only when a resolved address names no port. Spelled
#: apart from the address below because the two are different facts: 104-US5
#: found this constant standing in for both, which is how `f"{address}:{port}"`
#: came to build `127.0.0.1:7233:7233`.
DEFAULT_TEMPORAL_HOST = "127.0.0.1"

#: The whole endpoint, `host:port` — this tree's one convention
#: (`factory/notify/service.py`, `factory/cli/env.py`, `scripts/ergane-env.sh`)
#: and the spelling the generated `.env` writes. The supervisor's children read
#: that same variable and need the port, so it has one meaning on both sides.
DEFAULT_TEMPORAL_ADDRESS = f"{DEFAULT_TEMPORAL_HOST}:{DEFAULT_TEMPORAL_PORT}"
DEFAULT_READINESS_TIMEOUT_S = 30.0
DEFAULT_GRACE_PERIOD_S = 10.0
DEFAULT_DB_FILENAME = "/var/lib/ergane/temporal.sqlite"


class ChildController(Protocol):
    """Handle to one supervised child: wait for it, stop it, or kill it."""

    async def wait(self) -> int:
        """Block until the child exits and return its status."""
        ...

    def stop(self) -> None:
        """Send the child its graceful-stop signal (SIGTERM equivalent)."""
        ...

    def kill(self) -> None:
        """Force the child to exit (SIGKILL equivalent)."""
        ...


class SupervisorRefusal(Exception):
    """A configuration problem that prevents the supervisor from starting."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class _ProcessController:
    """Controller for a real subprocess child."""

    def __init__(self, proc: asyncio.subprocess.Process, name: str) -> None:
        self.proc = proc
        self.name = name

    async def wait(self) -> int:
        return await self.proc.wait()

    def stop(self) -> None:
        _stop_process(self.proc, self.name)

    def kill(self) -> None:
        _kill_process(self.proc, self.name)


def _split_address(address: str) -> tuple[str, int]:
    """Split one `host:port` value **once**, tolerating a host-only spelling.

    The convention is `host:port` (bracket a bare IPv6 literal; this tree uses
    none). A value with no port means the default port, never a `ValueError` out
    of `int()` — 088's probe would have raised on exactly that input, because it
    was only ever handed an address a port had just been appended to.
    """
    host, separator, tail = address.rpartition(":")
    if separator and tail.isdigit():
        return (host or DEFAULT_TEMPORAL_HOST), int(tail)
    return (address or DEFAULT_TEMPORAL_HOST), DEFAULT_TEMPORAL_PORT


def _resolve_temporal_address(address: str, port: int) -> str:
    """The one endpoint, from whichever spelling arrived (104-US5, plan R12).

    As 088 landed, `_run_supervisor` built `f"{address}:{port}"` unconditionally
    while `TEMPORAL_ADDRESS` carries `host:port` everywhere else in this tree,
    so the generated `.env`'s `127.0.0.1:7233` became `127.0.0.1:7233:7233`, the
    probe dialled host `127.0.0.1:7233`, readiness timed out and the engine
    never came up. An address that already carries a port **is** the address.

    The host-only spelling still resolves, deliberately: a host-only value would
    break `factory.worker` and `factory.notify.service`, which read the same
    variable out of the same environment and need the port.
    """
    _host, _, tail = address.rpartition(":")
    if _host and tail.isdigit():
        return address
    return f"{address}:{port}"


async def _probe_temporal_address(address: str, timeout_s: float) -> bool:
    """Return True once the Temporal frontend answers TCP."""
    deadline = asyncio.get_event_loop().time() + timeout_s
    host, port = _split_address(address)
    while asyncio.get_event_loop().time() < deadline:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=1.0
            )
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            await asyncio.sleep(0.2)
    return False


def _check_same_path_registry(state_home: str | Path | None = None) -> None:
    """Verify every registered repo is a directory at its own recorded path.

    An empty or absent registry is a fresh container and starts normally
    (trap 7a).  Paths are resolved before comparing (trap 7b).  The refusal
    names both remedies: wrong mount or stale cache.
    """
    if state_home is not None:
        registry_path = Path(state_home) / DEFAULT_REGISTRY_REL
        registry = load_registry(registry_path)
    else:
        registry = load_registry()

    missing: list[tuple[str, Path]] = []
    for entry in registry.entries:
        resolved = entry.path.resolve()
        if not resolved.is_dir():
            missing.append((entry.slug, resolved))

    if missing:
        lines = [
            f"repo '{slug}' is registered at {path}, which is not a directory"
            for slug, path in missing
        ]
        lines.append(
            "remedies: ensure the repo is mounted at the recorded path, "
            "or rebuild the registry with `ergane repo rebuild <repo path> ...`"
        )
        raise SupervisorRefusal("\n".join(lines))


def _child_argv(
    *,
    temporal_address: str,
    db_filename: str,
    temporal_namespace: str = "ergane",
    log_level: str = "warn",
) -> dict[str, list[str]]:
    """Return argv for each child.  No assembled value may contain `python -`."""
    return {
        "temporal": [
            "factory.supervision.temporal_server",
            "--db-filename", db_filename,
            "--namespace", temporal_namespace,
            "--ip", "0.0.0.0",
            "--port", str(DEFAULT_TEMPORAL_PORT),
            "--log-level", log_level,
        ],
        "worker": [
            "factory.worker",
        ],
        "bridge": [
            "factory.notify.service",
        ],
    }


async def _start_real_child(name: str, argv: Sequence[str]) -> ChildController:
    """Spawn one child with `python3 -m <module> ...` and return a controller."""
    interpreter = sys.executable
    cmd = [interpreter, "-m", *argv]
    logger.info("starting child %s: %s", name, " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.DEVNULL,
    )
    return _ProcessController(proc, name)


def _stop_process(proc: asyncio.subprocess.Process, name: str) -> None:
    """Signal a child with SIGTERM if it is still running."""
    if proc.returncode is not None:
        return
    try:
        proc.send_signal(signal.SIGTERM)
    except ProcessLookupError:
        return
    logger.info("sent SIGTERM to child %s (pid=%s)", name, proc.pid)


def _kill_process(proc: asyncio.subprocess.Process, name: str) -> None:
    """SIGKILL a child that ignored SIGTERM."""
    if proc.returncode is not None:
        return
    try:
        proc.kill()
    except ProcessLookupError:
        return
    logger.info("sent SIGKILL to child %s (pid=%s)", name, proc.pid)


async def _run_supervisor(
    config: Mapping[str, object],
    *,
    start_child: Callable[[str, list[str]], Awaitable[ChildController]] | None = None,
    probe_address: Callable[[str, float], Awaitable[bool]] | None = None,
) -> int:
    """Run all three children to completion.

    `start_child` and `probe_address` are injectable so tests can drive the
    supervisor with stubs.
    """
    start_child = start_child or _start_real_child
    probe_address = probe_address or _probe_temporal_address

    state_home = config.get("state_home") or os.environ.get("ERGANE_STATE_HOME")
    if state_home is None:
        state_home = str(resolve_state_home())
    _check_same_path_registry(state_home)

    temporal_address = str(
        config.get("temporal_address") or os.environ.get("TEMPORAL_ADDRESS") or DEFAULT_TEMPORAL_ADDRESS
    )
    temporal_port = int(config.get("temporal_port") or DEFAULT_TEMPORAL_PORT)
    # Never `f"{address}:{port}"`: the value in `TEMPORAL_ADDRESS` usually
    # already carries its port, and appending a second one is 088's defect.
    full_address = _resolve_temporal_address(temporal_address, temporal_port)
    readiness_timeout_s = float(config.get("readiness_timeout_s") or DEFAULT_READINESS_TIMEOUT_S)
    grace_period_s = float(config.get("grace_period_s") or DEFAULT_GRACE_PERIOD_S)
    db_filename = str(config.get("db_filename") or DEFAULT_DB_FILENAME)
    temporal_namespace = str(
        config.get("temporal_namespace") or os.environ.get("TEMPORAL_NAMESPACE") or "ergane"
    )

    argv_map = _child_argv(
        temporal_address=full_address,
        db_filename=db_filename,
        temporal_namespace=temporal_namespace,
    )

    # Start Temporal first and begin waiting on it so readiness probes can
    # observe its startup.
    temporal = await start_child("temporal", argv_map["temporal"])
    temporal_task = asyncio.create_task(temporal.wait(), name="temporal")

    # Wait for the address before starting dependents.
    if not await probe_address(full_address, readiness_timeout_s):
        logger.error(
            "temporal frontend at %s did not become ready within %ss",
            full_address,
            readiness_timeout_s,
        )
        temporal_task.cancel()
        try:
            await temporal_task
        except asyncio.CancelledError:
            pass
        temporal.stop()
        try:
            await temporal.wait()
        except Exception:
            pass
        return 1

    # Start worker and bridge.
    worker = await start_child("worker", argv_map["worker"])
    bridge = await start_child("bridge", argv_map["bridge"])

    controllers: dict[str, ChildController] = {
        "temporal": temporal,
        "worker": worker,
        "bridge": bridge,
    }
    tasks: dict[str, asyncio.Task[int]] = {
        "temporal": temporal_task,
        "worker": asyncio.create_task(worker.wait(), name="worker"),
        "bridge": asyncio.create_task(bridge.wait(), name="bridge"),
    }

    shutdown_requested = asyncio.Event()
    first_dead: str | None = None
    first_status: int | None = None
    first_dead_before_shutdown: str | None = None

    def _stop_all_except(victim: str | None) -> None:
        for name, controller in controllers.items():
            if name != victim:
                controller.stop()

    def on_signal(sig: int) -> None:
        logger.info("received signal %s, shutting down children", sig)
        shutdown_requested.set()
        _stop_all_except(None)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, on_signal, sig)

    def _record_first_dead(name: str, status: int) -> None:
        nonlocal first_dead, first_status
        if first_dead is None:
            first_dead = name
            first_status = status

    try:
        pending = set(tasks.values())
        while pending:
            done, pending = await asyncio.wait(
                pending, return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                name = task.get_name()
                try:
                    status = task.result()
                except asyncio.CancelledError:
                    status = -signal.SIGTERM
                except Exception as exc:
                    logger.exception("child %s raised %s", name, exc)
                    status = 1

                _record_first_dead(name, status)

                if not shutdown_requested.is_set():
                    first_dead_before_shutdown = name
                    shutdown_requested.set()
                    _stop_all_except(name)

        # Grace period, then kill stragglers.
        if shutdown_requested.is_set() and pending:
            try:
                await asyncio.wait_for(asyncio.gather(*pending), timeout=grace_period_s)
            except asyncio.TimeoutError:
                for name, task in tasks.items():
                    if not task.done():
                        logger.warning("child %s ignored SIGTERM, sending SIGKILL", name)
                        controllers[name].kill()
                        task.cancel()

        await asyncio.gather(*tasks.values(), return_exceptions=True)
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(sig)

    # A child exiting on its own (not during a requested shutdown) is a fault:
    # the container exits nonzero naming the first victim and its status.
    if first_dead_before_shutdown is not None:
        logger.error(
            "child %s exited first with status %s; stopping container",
            first_dead_before_shutdown,
            first_status,
        )
        return 1

    if first_dead is not None:
        # SIGTERM/SIGINT-driven shutdown is the normal way the container stops.
        logger.info(
            "shutdown complete; child %s exited first with status %s",
            first_dead,
            first_status,
        )

    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Supervise the Ergane engine children inside a container."
    )
    parser.add_argument(
        "--temporal-address",
        default=os.environ.get("TEMPORAL_ADDRESS") or DEFAULT_TEMPORAL_ADDRESS,
        help=(
            "Temporal frontend endpoint as host:port; a host on its own takes "
            f"--temporal-port (default: {DEFAULT_TEMPORAL_ADDRESS})"
        ),
    )
    parser.add_argument(
        "--temporal-port",
        type=int,
        default=int(os.environ.get("TEMPORAL_PORT") or DEFAULT_TEMPORAL_PORT),
        help="Temporal frontend port (default: 7233)",
    )
    parser.add_argument(
        "--readiness-timeout-s",
        type=float,
        default=float(
            os.environ.get("ERGANE_READINESS_TIMEOUT_S") or DEFAULT_READINESS_TIMEOUT_S
        ),
        help="Seconds to wait for Temporal to answer (default: 30)",
    )
    parser.add_argument(
        "--grace-period-s",
        type=float,
        default=float(
            os.environ.get("ERGANE_GRACE_PERIOD_S") or DEFAULT_GRACE_PERIOD_S
        ),
        help="Seconds between SIGTERM and SIGKILL (default: 10)",
    )
    parser.add_argument(
        "--db-filename",
        default=os.environ.get("ERGANE_TEMPORAL_DB_FILENAME") or DEFAULT_DB_FILENAME,
        help="SQLite database file for Temporal persistence",
    )
    parser.add_argument(
        "--state-home",
        default=os.environ.get("ERGANE_STATE_HOME"),
        help="Override the registry state home; defaults to the resolver",
    )
    parser.add_argument(
        "--temporal-namespace",
        default=os.environ.get("TEMPORAL_NAMESPACE") or "ergane",
        help="Temporal namespace (default: ergane)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Container entrypoint."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = _build_parser()
    args = parser.parse_args(argv)

    config = {
        "temporal_address": args.temporal_address,
        "temporal_port": args.temporal_port,
        "readiness_timeout_s": args.readiness_timeout_s,
        "grace_period_s": args.grace_period_s,
        "db_filename": args.db_filename,
        "state_home": args.state_home,
        "temporal_namespace": args.temporal_namespace,
    }
    try:
        return asyncio.run(_run_supervisor(config))
    except SupervisorRefusal as refusal:
        logger.error("supervisor refused to start: %s", refusal)
        return 1
    except SystemExit as exit_request:
        code = exit_request.code if exit_request.code is not None else 1
        logger.error("supervisor refused to start: %s", exit_request)
        return int(code)


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
