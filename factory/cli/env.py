"""Implementation of `ergane env`.

Lists every environment variable the CLI reads, reporting whether it is set and
where its default comes from, without ever printing a credential value.
"""

from __future__ import annotations

import argparse
import os

from factory.cli.errors import EXIT_OK
from factory.env import (
    ERGANE_LEDGER_PATH_ENV,
    ERGANE_VERIFICATION_DB_PATH_ENV,
)
from factory.notify.service import (
    BOT_TOKEN_ENV,
    DEFAULT_TEMPORAL_ADDRESS,
    DEFAULT_TEMPORAL_NAMESPACE,
    TEMPORAL_ADDRESS_ENV,
    TEMPORAL_NAMESPACE_ENV,
)
from factory.usage.litellm_client import MASTER_KEY_ENV, PROXY_URL_ENV

#: Credential-like variables whose values must never be printed.
_SECRET_VARS = {MASTER_KEY_ENV, BOT_TOKEN_ENV}

#: Environment variables the CLI reads, with their default/fallback source.
_ENTRIES: list[tuple[str, str | None, str]] = [
    (TEMPORAL_ADDRESS_ENV, DEFAULT_TEMPORAL_ADDRESS, "default"),
    (TEMPORAL_NAMESPACE_ENV, DEFAULT_TEMPORAL_NAMESPACE, "default"),
    (PROXY_URL_ENV, None, "required"),
    (MASTER_KEY_ENV, None, "required"),
    (BOT_TOKEN_ENV, None, "required"),
    (ERGANE_LEDGER_PATH_ENV, None, "default .factory/ledger.db"),
    (ERGANE_VERIFICATION_DB_PATH_ENV, None, "default .factory/verification.db"),
]


def add_env_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "env",
        help="show environment variables the CLI reads",
        description="List every environment variable Ergane reads, whether it is set, and its source.",
    )
    parser.set_defaults(run=env_command)
    return parser


def env_command(_args: argparse.Namespace) -> int:
    for name, default, source in _ENTRIES:
        value = os.environ.get(name)
        if value is None:
            state = "not set"
            printed = ""
        else:
            state = "set"
            printed = "[REDACTED]" if name in _SECRET_VARS else ""
        default_note = f" (default: {default})" if default else ""
        print(f"{name}={printed}{default_note}  [{state}, {source}]")
    return EXIT_OK
