"""The universal glue: an outbound POST, and a reply the operator hands back.

041-US4. `telegram` is the reference transport; this is the extension point
that makes the seam worth having — one URL and one JSON body, so Signal, Slack,
email or a wall display is a bridge the operator writes in a few lines. Three
things it deliberately is not:

- **A decider.** Two operations, like every adapter (FR-001). Whether the
  sender may *answer* is checked factory-side, in `CallbackBridge`, because an
  adapter that filtered replies would make the one decision the seam keeps out
  of the transport. There is no store, client or handle here to decide with.
- **A listener.** An inbound HTTP server would put a socket on the factory's
  side of a boundary whose purpose is that the operator's side is theirs.
  Replies arrive through `ergane answer`, which is `relay`'s caller.
- **Temporal-aware (FR-002).** No import, at module scope or in a function:
  042's probe says the orchestrator is down, and that alert cannot be hosted by
  the orchestrator.

`delivered=False` is the whole vocabulary for "nobody was paged" — an unset
URL, a refused connection, a 500 — because the factory's move is identical for
all three (002 R11), and nothing here raises for the same reason. There is no
`message_id`: a webhook mints no handle a reply could quote, which is why the
correlation id travels in the body.
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

#: The name 033's config admits and the name this is registered under — one
#: spelling, so a config the parser accepted always resolves.
WEBHOOK_ADAPTER = "webhook"

#: Where the POST goes. Worker configuration rather than a credential, read from
#: the environment the way the Telegram transport reads its chat id — legitimate
#: here and in an activity, since this module defines no workflow.
WEBHOOK_URL_ENV = "ERGANE_WEBHOOK_URL"

#: Short on purpose: a delivery that hangs delays the escalation's *start*, and
#: its own timer — the authority on expiry — has not begun.
WEBHOOK_TIMEOUT_S = 10.0

Poster = Callable[[str, dict[str, Any]], Awaitable[int]]


class WebhookAdapter:
    """A transport that is one URL. It delivers, and it translates.

    `post` is the seam a test substitutes for the socket, mirroring
    `TelegramAdapter`'s `open_bot`.
    """

    def __init__(self, *, post: Poster | None = None) -> None:
        self._post = post or _post_json

    async def deliver(
        self, message: RenderedMessage, correlation_id: str
    ) -> DeliveryReceipt:
        """POST the rendered message and the correlation id. Never raises.

        Actions travel as `{label, payload}` pairs, so a bridge renders buttons
        if its messenger has them and ignores them if it does not; the payload
        is the same ≤64-byte token Telegram's `callback_data` carries (R11).
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

        The one shape this transport documents: a mapping of the correlation id
        the delivery quoted, the reply text, and who sent it. `None` is "not one
        of ours", and what to *say* about that is the factory's call. An absent
        sender becomes `UNKNOWN_SENDER` rather than an error, because the
        authorized-responders check needs something a list can fail to contain.
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
    """Build the transport. It recognises `post` and ignores the rest, because a
    caller resolving by name cannot know which transport it got."""
    return WebhookAdapter(post=seams.get("post"))


register_adapter(WEBHOOK_ADAPTER, _build_webhook)
