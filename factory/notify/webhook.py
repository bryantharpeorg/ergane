"""The universal glue: an outbound POST, and a reply the operator hands back.

041-US4. `telegram` is the reference transport; this is the extension point that
makes the seam worth having. It knows one URL and one JSON body, so Signal,
Slack, email or a wall display is a bridge the operator writes in a few lines
rather than a messenger ergane has to grow support for.

Three things it deliberately is not:

- **It is not a decider.** Two operations, like every adapter (FR-001): it puts
  a rendered message somewhere and it translates an inbound reply into three
  terms. Whether the sender may *answer* is checked factory-side, in
  `factory.notify.service.CallbackBridge`, because an adapter that filtered
  replies would be making the one decision the seam exists to keep out of the
  transport. This module holds no store, no client and no workflow handle, so
  there is nothing here to decide with.

- **It is not a listener.** A webhook adapter that ran an inbound HTTP server
  would put a socket on the factory's side of a boundary whose whole purpose is
  that the operator's side is theirs. Replies come back through
  `ergane answer <correlation-id> <text>`, which is `relay`'s caller — the
  operator's bridge either invokes that verb or POSTs to something that does.

- **It is not Temporal-aware (FR-002).** No import, not at module scope and not
  inside a function. 042's supervision probe pages a human to say the
  orchestrator is down, and an alert about a dead orchestrator cannot be hosted
  by the orchestrator.

`delivered=False` is the whole vocabulary for "nobody was paged" — an unset URL,
a refused connection, a 500 — because the factory's move is identical for all
three: apply its own default now rather than wait out a deadline of silence that
means nothing (002 R11). Nothing here raises, for the same reason.

There is no `message_id`: a webhook mints no handle the factory could route by,
which is exactly why the correlation id travels in the body and why
`ergane answer` names the factory's own id rather than a quoted message.
"""

from __future__ import annotations

import dataclasses
import logging
import os
from typing import Any, Awaitable, Callable, Mapping

from factory.notify.adapter import (
    UNKNOWN_SENDER,
    DeliveryReceipt,
    InboundRelay,
    RenderedMessage,
    register_adapter,
)

logger = logging.getLogger(__name__)

#: The name 033's config admits for this transport, and the name it is
#: registered under. One spelling, so a config the parser accepted always
#: resolves.
WEBHOOK_ADAPTER = "webhook"

#: Where the POST goes. Worker configuration rather than a credential, and read
#: from the process environment the way the Telegram transport reads its chat
#: id — legitimate here and in an activity, since this module defines no
#: workflow.
WEBHOOK_URL_ENV = "ERGANE_WEBHOOK_URL"

#: How long the factory waits on the operator's own endpoint. Short on purpose:
#: a delivery that hangs delays the escalation's *start*, and the escalation's
#: own timer — which is the authority on expiry — has not begun.
WEBHOOK_TIMEOUT_S = 10.0

Poster = Callable[[str, dict[str, Any]], Awaitable[int]]


class WebhookAdapter:
    """A transport that is one URL. It delivers, and it translates.

    `post` is the seam a test substitutes for the socket, mirroring
    `TelegramAdapter`'s `open_bot`: the caller's own process owns the handle,
    and the adapter still has to find its endpoint in the worker environment.
    """

    def __init__(self, *, post: Poster | None = None) -> None:
        self._post = post or _post_json

    async def deliver(
        self, message: RenderedMessage, correlation_id: str
    ) -> DeliveryReceipt:
        """POST the rendered message and the correlation id. Never raises.

        The body carries the message as the factory composed it and the actions
        as `{label, payload}` pairs, so a bridge can render buttons if its
        messenger has them and ignore them if it does not. The payload is the
        same ≤64-byte token Telegram's `callback_data` carries (002 R11), which
        is what lets one operator bridge two transports without translating.
        """
        endpoint = os.environ.get(WEBHOOK_URL_ENV)
        if not endpoint:
            logger.warning(
                "%s: not sent — %s is not set on this worker",
                correlation_id,
                WEBHOOK_URL_ENV,
            )
            return DeliveryReceipt(delivered=False)

        body = {
            "correlation_id": correlation_id,
            "text": message.text,
            "actions": [dataclasses.asdict(action) for action in message.actions],
        }

        try:
            status = await self._post(endpoint, body)
        except Exception as exc:
            # Broad on purpose: a refused connection, a DNS failure and a
            # timeout leave the factory with the same move. The exception's
            # class is logged and its message is not — an operator's endpoint
            # may carry a token in its path.
            logger.warning(
                "%s: not delivered (%s)", correlation_id, type(exc).__name__
            )
            return DeliveryReceipt(delivered=False)

        if not 200 <= status < 300:
            logger.warning("%s: not delivered (HTTP %s)", correlation_id, status)
            return DeliveryReceipt(delivered=False)

        # No message handle: a webhook mints none, so a reply cannot quote one
        # and `ergane answer` routes by the factory's own correlation id.
        return DeliveryReceipt(delivered=True)

    def relay(self, event: Any) -> InboundRelay | None:
        """Translate one inbound reply into the factory's three terms.

        The event is whatever the operator's bridge produced, in the one shape
        this transport documents: a mapping carrying the correlation id the
        delivery quoted, the reply text, and who sent it. `None` means "not one
        of ours" — a body missing either of the two terms that make a reply a
        reply — and what to *say* about that is the factory's call.

        An absent sender becomes `UNKNOWN_SENDER` rather than an error, because
        the authorized-responders check needs something a list can fail to
        contain rather than something that never reaches it.
        """
        if not isinstance(event, Mapping):
            return None

        correlation_id = event.get("correlation_id")
        reply_text = event.get("reply_text")
        if not correlation_id or not reply_text:
            return None

        return InboundRelay(
            correlation_id=str(correlation_id),
            reply_text=str(reply_text),
            sender_identity=str(event.get("sender_identity") or UNKNOWN_SENDER),
        )


async def _post_json(endpoint: str, body: dict[str, Any]) -> int:
    """One POST, and the status it came back with. The only socket in this file."""
    import httpx

    async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT_S) as http:
        response = await http.post(endpoint, json=body)
    return int(response.status_code)


def _build_webhook(**seams: Any) -> WebhookAdapter:
    """Build the transport from whatever seams the caller owns.

    The only one it recognises is `post`; a caller resolving a transport by name
    cannot know which one it got, so the rest are ignored (see `resolve_adapter`).
    """
    return WebhookAdapter(post=seams.get("post"))


register_adapter(WEBHOOK_ADAPTER, _build_webhook)
