"""Local attestation packet reads, exports, and offline verification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from factory.attestation.archive import (
    ArchiveLimits,
    PacketError,
    export_packet,
    show_subject,
    verify_packet,
)
from factory.cli.errors import EXIT_OK, OperatorError
from factory.cli.nouns import Noun


def add_attestation_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "attestation",
        help="inspect and verify local audit packets",
        description="Read retained evidence without starting a factory or opening the network.",
    )
    verbs = parser.add_subparsers(dest="verb", required=True)

    show = verbs.add_parser("show", help="show one explicit subject")
    show.add_argument("--root", type=Path, required=True)
    show.add_argument("--subject", required=True)
    show.add_argument("--revision")
    show.set_defaults(run=_show_command)

    export = verbs.add_parser("export", help="export one subject as a ZIP packet")
    export.add_argument("--root", type=Path, required=True)
    export.add_argument("--subject", required=True)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--selector", action="append", default=[], metavar="GATE:PATH:DISPATCH:CAPTURE")
    export.add_argument("--strict", action="store_true")
    export.set_defaults(run=_export_command)

    verify = verbs.add_parser("verify", help="verify an archive without extracting it")
    verify.add_argument("archive", type=Path)
    verify.add_argument("--strict", action="store_true")
    verify.set_defaults(run=_verify_command)
    return parser


def _show_command(args: argparse.Namespace) -> int:
    try:
        document = show_subject(args.root, args.subject, args.revision)
    except PacketError as error:
        raise OperatorError(str(error)) from error
    print(json.dumps(document, indent=2, sort_keys=True))
    return EXIT_OK


def _parse_selector(value: str) -> tuple[str, str, str, str]:
    fields = value.split(":", 3)
    if len(fields) != 4 or any(not field for field in fields):
        raise argparse.ArgumentTypeError("selector must be GATE:PATH:DISPATCH:CAPTURE")
    return tuple(fields)


def _export_command(args: argparse.Namespace) -> int:
    selectors = [
        value if isinstance(value, tuple) else _parse_selector(value)
        for value in args.selector
    ]
    try:
        result = export_packet(
            args.root,
            args.subject,
            output=args.output,
            selectors=selectors,
            strict=args.strict,
    )
    except PacketError as error:
        raise OperatorError(str(error)) from error
    print(json.dumps(result._asdict(), indent=2, sort_keys=True, default=lambda value: getattr(value, "_asdict", lambda: str(value))()))
    return EXIT_OK


def _verify_command(args: argparse.Namespace) -> int:
    try:
        manifest = verify_packet(args.archive)
    except PacketError as error:
        raise OperatorError(str(error)) from error
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return EXIT_OK


NOUN = Noun(
    name="attestation",
    summary="read and verify audit packets",
    order=44,
    add_parser=add_attestation_parser,
)
