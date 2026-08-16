"""The `answer` verb: the inbound half of a transport that cannot ferry replies.

041-US4, FR-003. `webhook` delivers outbound and stops there — a factory that
ran an inbound HTTP listener would put a socket on its own side of a boundary
whose whole point is that the operator's side is theirs. So the reply comes back
through the operator: `ergane answer <correlation-id> "ship it"`.

Two things this verb deliberately is not.

**It is not a second settling core.** It builds the three terms an adapter
relays and hands them to `CallbackBridge.handle_relay` — the same function a
Telegram reply reaches. There is exactly one place in this factory that looks a
question up, signals the workflow waiting on it and settles its row, and a verb
that re-implemented any of that would be the third writer the store's channel
asymmetry was made of (`interpreter/resolved-escalation-never-clears-in-the-store`).

**It is not the escalation verb.** An escalation carries a choice from a closed
enum and `ergane build resolve` sends it; this one carries the free text a
question is answered with, which is why 008 has two signals and two tables at
all. Both names read the same to an operator and the difference is real, so the
help text says which is which.

The correlation id is the factory's own — the id the delivery body quoted —
because a webhook mints no message handle for a reply to thread back to. Whether
the sender may answer is not decided here either: the relay carries an identity
and `CallbackBridge` checks it against `escalation.authorized_responders`, so
one rule covers every channel (FR-011).
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any

from factory.activities.verify_activities import (
    DEFAULT_VERIFICATION_DB_PATH,
    ERGANE_VERIFICATION_DB_PATH_ENV,
    FACTORY_VERIFICATION_DB_PATH_ENV,
)
from factory.cli.errors import EXIT_OK, EXIT_TRANSPORT, OperatorError
from factory.cli.nouns import Noun
from factory.env import resolve_env_path
from factory.notify.adapter import UNKNOWN_SENDER, resolve_adapter
from factory.notify.service import BridgeOutcome, CallbackBridge
from factory.notify.webhook import WEBHOOK_ADAPTER

#: What each outcome means to the operator standing at the terminal.
#:
#: The three cases an id with nothing waiting on it can be — answered, expired,
#: or never asked — are told apart rather than collapsed into one failure,
#: because they call for three different next moves and the settling core
#: already distinguishes them. `None` is the exit code for "this worked".
_REPORT: dict[BridgeOutcome, tuple[int | None, str]] = {
    BridgeOutcome.RESOLVED: (
        None,
        "{id}: answer recorded; the workflow waiting on it has been signalled",
    ),
    BridgeOutcome.UNKNOWN: (
        1,
        "{id} names no question this factory ever asked; nothing was signalled",
    ),
    BridgeOutcome.ALREADY_RESOLVED: (
        1,
        "{id} is already answered; the first answer stands and nothing was signalled",
    ),
    BridgeOutcome.EXPIRED: (
        1,
        "{id} expired before this answer arrived; nothing was signalled",
    ),
    BridgeOutcome.UNAUTHORIZED: (
        1,
        "{id}: '{identity}' is not in escalation.authorized_responders; "
        "nothing was signalled — pass --as with the identity the list carries",
    ),
    BridgeOutcome.SIGNAL_FAILED: (
        EXIT_TRANSPORT,
        "{id}: the orchestrator could not be reached; nothing was recorded, "
        "so the answer can be sent again",
    ),
}


def answer_command(args: argparse.Namespace) -> int:
    return asyncio.run(_answer(args.correlation_id, args.text, args.identity))


async def _answer(correlation_id: str, text: str, identity: str) -> int:
    # Resolved through the package seam rather than an import of its own: the
    # dispatcher `exec_module`s this file on every invocation, so a patch on the
    # module a test imported would never reach the function argparse calls.
    from factory.cli.nouns import _open_client

    relay = resolve_adapter(WEBHOOK_ADAPTER).relay(
        {
            "correlation_id": correlation_id,
            "reply_text": text,
            "sender_identity": identity,
        }
    )
    if relay is None:
        # The one shape the adapter refuses that an operator can type: an empty
        # answer. Recording it would park the node on nothing.
        raise OperatorError(
            f"{correlation_id}: an empty answer carries nothing; nothing was signalled"
        )

    client = await _open_client()
    bridge = CallbackBridge(db_path=_store_path(), client=client)
    outcome = await bridge.handle_relay(relay)

    code, template = _REPORT[outcome]
    message = template.format(id=correlation_id, identity=identity)
    if code is None:
        print(message)
        return EXIT_OK
    raise OperatorError(message, code)


def _store_path() -> Path:
    return resolve_env_path(
        ERGANE_VERIFICATION_DB_PATH_ENV,
        FACTORY_VERIFICATION_DB_PATH_ENV,
        DEFAULT_VERIFICATION_DB_PATH,
    )


def add_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "answer",
        help="answer an operator question by its correlation id",
        description=(
            "Answer a question the factory asked, over any transport. The "
            "correlation id is the one the delivery carried. To resolve an "
            "escalation — a choice from a fixed set rather than free text — "
            "use `ergane build resolve` instead."
        ),
    )
    parser.add_argument("correlation_id", help="the id the delivery quoted")
    parser.add_argument("text", help="the answer, carried into the next attempt verbatim")
    parser.add_argument(
        "--as",
        dest="identity",
        default=UNKNOWN_SENDER,
        help=(
            "who is answering, spelled as escalation.authorized_responders "
            "spells them; only needed where that list is configured"
        ),
    )
    parser.set_defaults(run=answer_command)


NOUN = Noun(
    name="answer",
    summary="answer an operator question by its correlation id",
    order=36,
    add_parser=add_parser,
)
