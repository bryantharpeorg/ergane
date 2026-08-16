"""Implementation of `ergane env`.

Two modes, deliberately separate.

**Bare `ergane env`** lists every environment variable the CLI reads, reporting
whether it is set and where its default comes from, without ever printing a
credential value. Its rendering is pinned byte-for-byte by
`tests/test_env_sources.py` (FR-017): an operator may already be reading this
listing on an unfamiliar machine, and 048 is the spec whose whole point is that
diagnostics were lying, so rewriting a diagnostic's default output here would
be the wrong trade.

The one deliberate exception is the word `required` on `LITELLM_PROXY_URL` and
`LITELLM_MASTER_KEY`. Until 048-US1 they were the only routes to the endpoint
and the credential; they are now *overrides* of what `ergane install` declared,
and a report that calls an override required sends an operator to export a
variable they do not need. Correcting a word that has become untrue is not the
same act as restructuring the report, and the byte-parity assertion around it
is what keeps the distinction enforced rather than promised.

**`ergane env --sources`** answers the question US1 created: two sources can
now supply the same value, so "`LITELLM_PROXY_URL` is not set" stopped meaning
"the build cannot start". Per value it names the source that won, and the route
that did not — which is the report a human standing at a second machine needs
in order to believe the declaration reached the build.

Three properties of that report are worth stating because the code below is
their consequence:

- **It prints variable *names*, never credential values.** `_SECRET_VARS` is
  why the bare listing redacts `LITELLM_MASTER_KEY`; the sources report never
  reads a credential at all, because a `CredentialRef` carries the name of the
  variable and not what is in it. A config-declared variable name is not a
  secret — the parser refuses a credential-shaped value where a name belongs —
  and it is precisely what the operator needs to know.
- **It never opens the config file for a value an override supplied** (FR-002).
  That is why "other route" names the config path without saying what it
  declares: finding out would mean reading a file the resolver deliberately did
  not touch.
- **It exits zero even when nothing resolves, and even when the config is
  broken.** A report is not a gate (US3-S4). Refusing is the job of the command
  that is about to dispatch, and it already does it through the same resolver.
"""

from __future__ import annotations

import argparse
import os
from typing import Callable

from factory.cli.errors import EXIT_OK
from factory.controlplane.config import resolve_config_path
from factory.controlplane.resolve import (
    DEFAULT_SOURCE,
    ControlPlaneResolutionError,
    resolve_master_key_env,
    resolve_proxy_url,
    resolve_temporal_target,
)
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

#: What the two legacy variables became when 048-US1 taught the dispatch path to
#: read the declaration: not requirements, overrides. `required` was true when
#: they were the only route and is false now, and an operator reading it exports
#: a variable they do not need (FR-017).
_OVERRIDE_SOURCE = "override of the control-plane config"

#: Environment variables the CLI reads, with their default/fallback source.
_ENTRIES: list[tuple[str, str | None, str]] = [
    (TEMPORAL_ADDRESS_ENV, DEFAULT_TEMPORAL_ADDRESS, "default"),
    (TEMPORAL_NAMESPACE_ENV, DEFAULT_TEMPORAL_NAMESPACE, "default"),
    (PROXY_URL_ENV, None, _OVERRIDE_SOURCE),
    (MASTER_KEY_ENV, None, _OVERRIDE_SOURCE),
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
    parser.add_argument(
        "--sources",
        action="store_true",
        help="report which source won for each resolved value, and the route not taken",
    )
    parser.set_defaults(run=env_command)
    return parser


def env_command(args: argparse.Namespace) -> int:
    if getattr(args, "sources", False):
        return _sources_command()
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


# --- `--sources`: which source won, and what the other route was --------------


def _sources_command() -> int:
    """Report the resolution of every value 048 resolves (FR-011).

    Each value is resolved on its own rather than as a pair, so that a host
    which declares one and exports the other reports the truth about both. The
    resolver's own refusal text is rendered verbatim when nothing resolves: it
    already names both routes (FR-004), and a second copy of that sentence here
    would be a second place for it to drift.
    """
    config_label = str(resolve_config_path())
    lines: list[str] = []
    lines += _describe_value(
        "LLM gateway endpoint",
        _endpoint,
        override_env=PROXY_URL_ENV,
        config_label=config_label,
    )
    lines += _describe_value(
        "LLM gateway credential variable",
        _credential,
        override_env=MASTER_KEY_ENV,
        config_label=config_label,
    )
    # 048-US4: the same two questions about the second subsystem. FR-011 says
    # "every value this spec resolves"; until now that was two of four.
    lines += _describe_value(
        "Temporal address",
        _temporal_address,
        override_env=TEMPORAL_ADDRESS_ENV,
        config_label=config_label,
    )
    lines += _describe_value(
        "Temporal namespace",
        _temporal_namespace,
        override_env=TEMPORAL_NAMESPACE_ENV,
        config_label=config_label,
    )
    for line in lines:
        print(line)
    # A report is not a gate: an unresolved value is news, not a failure
    # (US3-S4). The commands that are about to dispatch refuse on their own.
    return EXIT_OK


def _endpoint() -> tuple[str, str]:
    """The resolved endpoint and the source that supplied it."""
    resolved = resolve_proxy_url()
    return resolved.url, resolved.source


def _credential() -> tuple[str, str]:
    """The *name* of the credential variable, and the source that named it.

    Never the credential. `CredentialRef.read` is the only thing that fetches a
    value and this report does not call it (FR-003, SC-005).
    """
    resolved = resolve_master_key_env()
    return resolved.env_name, resolved.source


def _temporal_address() -> tuple[str, str]:
    """The resolved Temporal address and the source that supplied it."""
    target = resolve_temporal_target()
    return target.address, target.address_source


def _temporal_namespace() -> tuple[str, str]:
    """The resolved Temporal namespace and the source that supplied it.

    Resolved separately from the address: a host exporting `TEMPORAL_ADDRESS`
    and declaring its namespace is the host this report exists for.
    """
    target = resolve_temporal_target()
    return target.namespace, target.namespace_source


def _describe_value(
    title: str,
    resolve: Callable[[], tuple[str, str]],
    *,
    override_env: str,
    config_label: str,
) -> list[str]:
    """Render one value's block: what it is, who won, and the route not taken.

    Three lines when it resolved, two when it did not. US4 adds Temporal's two
    values by calling this twice more; nothing here knows what an LLM is.
    """
    try:
        value, source = resolve()
    except ControlPlaneResolutionError as refusal:
        # Both the nothing-declared refusal and the parser's own refusal land
        # here, and both are already written for an operator to act on: one
        # names the two routes, the other names the file and the rule it broke.
        return [f"{title}: unresolved", f"  {refusal}"]

    if source == DEFAULT_SOURCE:
        # Only Temporal reaches here: it has a built-in default, so "nothing
        # declared it" is a working host rather than a refusal (048-US4). Both
        # routes are still named — the operator is deciding which to use.
        won = "the built-in default"
        other = (
            f"{override_env} (environment override, not set), or declare it in "
            f"the control-plane config at {config_label}"
        )
    elif source == override_env:
        won = f"{override_env} (environment override)"
        # Deliberately does not say whether the config declares one: FR-002
        # forbids reading it for a value the environment supplied, and US1-S3
        # pins that a bound-but-unparseable config is never opened when the
        # override speaks.
        other = (
            f"the control-plane config at {config_label} "
            "(not consulted: the override won)"
        )
    else:
        won = f"the control-plane config at {source}"
        other = f"{override_env} (environment override, not set)"

    return [f"{title}: {value}", f"  source: {won}", f"  other route: {other}"]
