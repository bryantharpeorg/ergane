"""The `escalations` noun: what is waiting on the operator, across every epic.

041-US2, FR-008. `ergane build resolve <epic>` already lists one epic's pending
*rows*; this is the other question — "what is waiting on me" — and it is
deliberately not the same read. It asks Temporal which `EscalationWorkflow`s are
running and asks each one what it wants, because an escalation is a workflow now
and a row is only its evidence.

The difference is not academic. A store scrape gets it wrong in both directions
against the live store: it lists fourteen rows whose nodes finished over a week
ago, and it hides an escalation a human is still waiting on whenever some
channel settled its row out of band.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
from typing import Any, Sequence

from factory.cli.errors import EXIT_OK
from factory.cli.nouns import Noun
from factory.escalation import client as escalation_reader
from factory.escalation.workflow import OpenEscalation


def render(open_now: Sequence[OpenEscalation]) -> str:
    """One line per escalation: what to answer, about what, and until when."""
    if not open_now:
        return "no open escalations"

    id_width = max(len(item.escalation_id) for item in open_now)
    where_width = max(len(f"{item.epic_id}/{item.node_id}") for item in open_now)
    return "\n".join(
        f"{item.escalation_id.ljust(id_width)}  "
        f"{f'{item.epic_id}/{item.node_id}'.ljust(where_width)}  "
        f"expires {item.expires_at}  {item.question}"
        for item in open_now
    )


def list_command(args: argparse.Namespace) -> int:
    """Read every open escalation from the workflows that are holding them."""
    return asyncio.run(_list(as_json=args.as_json))


async def _list(*, as_json: bool) -> int:
    # Resolved through the package seam rather than an import of its own: the
    # dispatcher `exec_module`s this file on every invocation, so a patch on the
    # module a test imported would never reach the function argparse calls.
    from factory.cli.nouns import _open_client

    client = await _open_client()
    open_now = await escalation_reader.open_escalations(client)

    if as_json:
        print(json.dumps([dataclasses.asdict(item) for item in open_now], indent=2))
    else:
        print(render(open_now))
    return EXIT_OK


def add_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "escalations",
        help="what is waiting on you",
        description=(
            "Read the escalations a human still has to answer, sourced from "
            "the workflows holding them open rather than from the store."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    listing = commands.add_parser(
        "list", help="every open escalation, with its question and its deadline"
    )
    listing.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="print the escalations as JSON instead of the human view",
    )
    listing.set_defaults(run=list_command)


NOUN = Noun(
    name="escalations",
    summary="what is waiting on you",
    order=35,
    add_parser=add_parser,
)
