"""042-US3: managed Temporal dev-server entry point for systemd.

The unit runs this module rather than invoking a Temporal CLI binary directly
because the CLI is not guaranteed to be on `PATH`; the temporalio SDK downloads the
server binary on first use and caches it.  The wrapper (`ergane-run.sh`) sets
`PATH` and the working directory, then calls the venv's python3 with this module
as an argument.

The command line intentionally avoids `python -`: a 2026-08-12 cleanup sweep ran
`pkill -f "python -"` and matched the worker's `python -m factory.worker`
command line.  Using the wrapper plus `factory.supervision.temporal_server` keeps
the visible argv free of that substring.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import socket
import sys
from typing import Sequence

from temporalio.runtime import Runtime
from temporalio.testing import WorkflowEnvironment

DEFAULT_NAMESPACE = "ergane"
DEFAULT_LOG_LEVEL = "warn"


async def _run(
    *,
    db_filename: str,
    namespace: str,
    ip: str,
    port: int,
    log_level: str,
) -> int:
    """Start the dev server and block until it is shut down."""
    # Ensure a runtime exists before the server starts; the default is created
    # on demand, but referencing it here makes shutdown deterministic.
    _runtime = Runtime.default()
    environment = await WorkflowEnvironment.start_local(
        namespace=namespace,
        ip=ip,
        port=port,
        dev_server_database_filename=db_filename,
        dev_server_log_level=log_level,
    )
    try:
        # Keep the process alive.  The server child handles signals; this main
        # thread just waits.  WorkflowEnvironment does not expose a wait, so we
        # sleep forever and let systemd's SIGTERM propagate through the wrapper.
        while True:
            await asyncio.sleep(3600)
    finally:
        await environment.shutdown()
    return 0


def _free_port(ip: str) -> int:
    """Bind a free TCP port on `ip` and return it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((ip, 0))
        return probe.getsockname()[1]


def main(argv: Sequence[str] | None = None) -> int:
    """`python3 -m factory.supervision.temporal_server` — what the unit runs."""
    parser = argparse.ArgumentParser(
        description="Run the managed Temporal dev server under systemd supervision."
    )
    parser.add_argument(
        "--db-filename",
        required=True,
        help="SQLite database file for persistent workflow history",
    )
    parser.add_argument(
        "--namespace",
        default=DEFAULT_NAMESPACE,
        help=f"Temporal namespace (default: {DEFAULT_NAMESPACE})",
    )
    parser.add_argument(
        "--ip",
        default="127.0.0.1",
        help="IP address to bind the frontend to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=7233,
        help="Frontend port; 0 means bind a free port (default: 7233)",
    )
    parser.add_argument(
        "--log-level",
        default=DEFAULT_LOG_LEVEL,
        help=f"Dev-server log level (default: {DEFAULT_LOG_LEVEL})",
    )
    args = parser.parse_args(argv)

    port = _free_port(args.ip) if args.port == 0 else args.port
    logging.basicConfig(level=logging.INFO)
    logging.info(
        "starting managed Temporal dev server on %s:%d (db=%s)",
        args.ip,
        port,
        args.db_filename,
    )
    return asyncio.run(
        _run(
            db_filename=args.db_filename,
            namespace=args.namespace,
            ip=args.ip,
            port=port,
            log_level=args.log_level,
        )
    )


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
