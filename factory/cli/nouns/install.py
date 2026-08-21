"""The `install` noun: `ergane install` and `ergane install --verify`.

This noun is intentionally small.  Bare `ergane install` runs the walkthrough
(`factory.cli.install`), which interviews the operator, writes the control-plane
config and ends by verifying it; `--verify` runs that verification alone.  The
heavy lifting lives outside this module — in `factory.cli.install` and
`factory.controlplane.verify` — so both can be tested without the CLI boundary
and so noun discovery, which re-executes this file, holds no state.
"""

from __future__ import annotations

import argparse
from typing import Any

from factory.cli.errors import EXIT_OK, EXIT_USER, OperatorError
from factory.cli.install import add_install_arguments, install_command
from factory.cli.nouns import Noun
from factory.config import is_example_alias
from factory.controlplane.config import ControlPlaneConfigError
from factory.controlplane.verify import render_findings, verify_controlplane
from factory.discovery.llm_scanner import render_scan_results, scan_endpoints


def _verify_command(_args: argparse.Namespace) -> int:
    """Run every verify probe, print findings, and return 0 only if all pass.

    A config the parser refuses — most often one that is simply not there yet —
    is an *expected* condition on a first run, not a bug. Left uncaught it
    reached `run_cli`'s defensive boundary and came back as `ergane: unexpected
    error (…); re-run with --debug for the traceback`, which tells a new user
    the tool is broken when in fact they have not run `ergane install` yet. The
    guidance was already inside the message; only the wrapper was wrong.
    """
    try:
        findings, exit_code = verify_controlplane()
    except ControlPlaneConfigError as error:
        raise OperatorError(str(error), code=EXIT_USER) from None
    print(render_findings(findings))
    return EXIT_OK if exit_code == 0 else EXIT_USER


def _scan_command(args: argparse.Namespace) -> int:
    """Probe candidate LLM endpoints and report what they advertise.

    Read-only: writes no config and does not start the interview. The scanner
    is unauthenticated by design; any address the operator wants to use is
    confirmed in the interview, not here.
    """
    addresses = None
    if getattr(args, "address", None):
        addresses = [args.address]
    results = scan_endpoints(addresses=addresses)
    print(render_scan_results(results))
    return EXIT_OK


def _requirements_command(_args: argparse.Namespace) -> int:
    """Print what the gateway must serve, derived from the persona registry.

    Read-only: mints no key and issues no completion. A registry that is
    entirely example aliases is reported as unconfigured, naming the path and
    the resolution order.
    """
    from factory.config import (
        DEFAULT_REGISTRY_REL,
        DETERMINISTIC_AGENT,
        ERGANE_PERSONAS_PATH_ENV,
        FACTORY_PERSONAS_PATH_ENV,
        load_personas,
        resolve_default_registry_path,
    )
    from factory.controlplane.verify import gather_gateway_aliases

    try:
        registry = load_personas()
    except Exception as exc:
        raise OperatorError(
            f"cannot load persona registry: {type(exc).__name__}: {exc}",
            code=EXIT_USER,
        ) from None

    alias_to_personas = gather_gateway_aliases(registry)
    if not alias_to_personas:
        registry_path = resolve_default_registry_path()
        raise OperatorError(
            f"persona registry has not been configured yet: "
            f"edit {registry_path} and declare at least one persona with a gateway model alias; "
            f"the registry is resolved from "
            f"{ERGANE_PERSONAS_PATH_ENV}, then {FACTORY_PERSONAS_PATH_ENV}, then "
            f"$XDG_CONFIG_HOME/{DEFAULT_REGISTRY_REL} (or ~/.config/ergane/{DEFAULT_REGISTRY_REL}), then the packaged default",
            code=EXIT_USER,
        ) from None

    if all(is_example_alias(alias) for alias in alias_to_personas):
        registry_path = resolve_default_registry_path()
        raise OperatorError(
            f"persona registry has not been configured yet: "
            f"edit {registry_path} and replace the example/ placeholder aliases; "
            f"the registry is resolved from "
            f"{ERGANE_PERSONAS_PATH_ENV}, then {FACTORY_PERSONAS_PATH_ENV}, then "
            f"$XDG_CONFIG_HOME/{DEFAULT_REGISTRY_REL} (or ~/.config/ergane/{DEFAULT_REGISTRY_REL}), then the packaged default",
            code=EXIT_USER,
        ) from None

    aliases = sorted(alias_to_personas)
    print("The gateway must serve every distinct model and fallback alias:")
    for alias in aliases:
        personas = ", ".join(sorted(alias_to_personas[alias]))
        print(f"  {alias}  (personas: {personas})")
    print("")
    print("The gateway must answer these key-management endpoints:")
    print("  POST /key/generate")
    print("  GET /key/info")
    print("  GET /spend/logs/v2")
    return EXIT_OK


def add_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "install",
        help="configure and verify the Ergane control plane",
        description=(
            "Interview the operator for the five control-plane subsystems, "
            "write ~/.config/ergane/config.toml, and verify what was written. "
            "Re-running loads the existing file as defaults."
        ),
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="skip the interview: probe the declared subsystems and report one finding per check",
    )
    parser.add_argument(
        "--requirements",
        action="store_true",
        help="print the model aliases and key-management endpoints the gateway must serve",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="read-only discovery: list reachable LLM endpoints and their capabilities",
    )
    parser.add_argument(
        "--address",
        metavar="URL",
        help="probe this address instead of the default loopback candidates",
    )
    add_install_arguments(parser)
    parser.set_defaults(run=_run)


def _run(args: argparse.Namespace) -> int:
    if args.scan:
        return _scan_command(args)
    if args.verify:
        return _verify_command(args)
    if args.requirements:
        return _requirements_command(args)
    return install_command(args)


NOUN = Noun(
    name="install",
    summary="configure and verify the control plane",
    order=5,
    add_parser=add_parser,
)
