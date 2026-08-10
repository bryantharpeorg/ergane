"""The `ergane` root parser and noun discovery.

`ergane` with no arguments lists every discovered noun. `ergane <noun>`
dispatches to that noun's subparser. Nouns are discovered from
`factory/cli/nouns/`; adding one is adding a file, removing one is deleting it,
and the dispatcher holds no literal list of names.

The exit-code contract is implemented by `factory.cli.errors.run_cli`, which
wraps every handler. argparse itself supplies exit code 2 for usage errors; no
subclass of `argparse.ArgumentParser` exists here.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import os
import pkgutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

import factory.cli.nouns as _nouns_package
from factory.cli.errors import (
    EXIT_OK,
    EXIT_USER,
    EXIT_USAGE,
    OperatorError,
    run_cli,
)
from factory.cli.nouns import Noun
from factory.notify.service import (
    BOT_TOKEN_ENV,
    DEFAULT_TEMPORAL_ADDRESS,
    DEFAULT_TEMPORAL_NAMESPACE,
    TEMPORAL_ADDRESS_ENV,
    TEMPORAL_NAMESPACE_ENV,
)
from factory.usage.litellm_client import MASTER_KEY_ENV, PROXY_URL_ENV


#: Package name used by discovery. Tests patch these two values to point at a
#: fixture noun package.
_NOUN_PACKAGE_NAME = "factory.cli.nouns"
_NOUN_PACKAGE_PATH: str | None = None


def _noun_package_path() -> str:
    if _NOUN_PACKAGE_PATH is not None:
        return _NOUN_PACKAGE_PATH
    return str(Path(_nouns_package.__file__).resolve().parent)


def _discover_nouns_with_failures() -> tuple[list[Noun], list[str]]:
    """Load every `NOUN` from the noun package, returning healthy nouns and failures separately.

    A module that fails to import is reported by name and does not prevent the
    other nouns from loading. The caller decides how to render the failures: the
    parser builder raises, the bare listing prints the healthy nouns first and
    then the failure lines.
    """
    package_path = _noun_package_path()
    found: list[Noun] = []
    failures: list[str] = []

    for module_info in pkgutil.iter_modules([package_path]):
        name = module_info.name
        full_name = f"{_NOUN_PACKAGE_NAME}.{name}"
        try:
            spec = importlib.util.spec_from_file_location(full_name, Path(package_path) / f"{name}.py")
            if spec is None or spec.loader is None:
                failures.append(f"noun '{name}' failed to load: could not create module spec")
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[full_name] = module
            spec.loader.exec_module(module)
        except Exception as exc:  # pragma: no cover - defensive boundary
            failures.append(f"noun '{name}' failed to load: {exc}")
            continue
        noun = getattr(module, "NOUN", None)
        if isinstance(noun, Noun):
            found.append(noun)

    found.sort(key=lambda noun: (noun.order, noun.name))
    return found, failures


def _discover_nouns() -> list[Noun]:
    """Load every `NOUN`; raise OperatorError if any module failed to load.

    Used while building the parser: a broken noun prevents argparse from
    presenting an incomplete tree, because the operator must fix the install.
    """
    nouns, failures = _discover_nouns_with_failures()
    if failures:
        raise OperatorError("\n".join(failures))
    return nouns


def _build_parser() -> argparse.ArgumentParser:
    """Build the root `ergane` parser with discovered nouns attached.

    Import failures are attached to the parser object rather than raised here,
    so the bare `ergane` invocation can still list the healthy nouns before
    reporting the broken ones. Commands that need a complete tree report the
    failures on stderr and exit 1.
    """
    parser = argparse.ArgumentParser(
        prog="ergane",
        description="The operator's front door to the Ergane factory.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="print full tracebacks for unexpected errors",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="print version, revision and endpoints without dialing them",
    )
    subparsers = parser.add_subparsers(dest="noun", metavar="NOUN")

    nouns, failures = _discover_nouns_with_failures()
    for noun in nouns:
        noun.add_parser(subparsers)
    parser._discovery_failures = failures  # type: ignore[attr-defined]

    return parser


def _version_text() -> str:
    """What `ergane --version` prints: version, revision, endpoints."""
    try:
        from importlib.metadata import version
        pkg_version = version("ergane")
    except Exception:
        pkg_version = "0.1.0"

    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        revision = "unknown"

    temporal_address = os.environ.get(TEMPORAL_ADDRESS_ENV) or DEFAULT_TEMPORAL_ADDRESS
    temporal_namespace = os.environ.get(TEMPORAL_NAMESPACE_ENV) or DEFAULT_TEMPORAL_NAMESPACE
    proxy_url = os.environ.get(PROXY_URL_ENV) or "not configured"

    return (
        f"ergane {pkg_version} ({revision})\n"
        f"Temporal: {temporal_address} (namespace {temporal_namespace})\n"
        f"Proxy: {proxy_url}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run one `ergane` invocation and return the process status."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    failures = getattr(parser, "_discovery_failures", [])

    if args.version:
        print(_version_text())
        return EXIT_OK

    debug = args.debug

    if args.noun is None:
        # Bare invocation: list the nouns and exit 0, unless some nouns failed
        # to load; then still list the healthy ones and report the failures.
        nouns, _ = _discover_nouns_with_failures()
        for noun in nouns:
            print(f"{noun.name:<12} {noun.summary}")
        if failures:
            for failure in failures:
                print(f"ergane: {failure}", file=sys.stderr)
            return EXIT_USER
        return EXIT_OK

    if failures:
        for failure in failures:
            print(f"ergane: {failure}", file=sys.stderr)
        return EXIT_USER

    run = getattr(args, "run", None)
    if run is None:
        # A noun with no verbs: argparse already printed usage and exited 2.
        return EXIT_USAGE

    return run_cli(lambda: int(run(args)), debug=debug)


if __name__ == "__main__":  # pragma: no cover - console script uses `main`
    sys.exit(main())
