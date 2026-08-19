"""The null escalation adapter.

060-US3. When an operator declares `escalation.adapter = "none"`, the factory
has no channel on which to page a human. The adapter exists so the name is
selectable and the registry contract at `factory/controlplane/config.py:48`
holds in both directions. It delivers nothing and relays nothing, which is
the whole point: a node that would have asked a question has no messenger and
fails instead of waiting.

Like every adapter, it is a plain library (041 FR-002): no Temporal import, no
store, no client. The decision to treat silence as failure stays factory-side.
"""

from __future__ import annotations

from typing import Any

from factory.notify.adapter import (
    DeliveryReceipt,
    InboundRelay,
    MessengerAdapter,
    RenderedMessage,
    register_adapter,
)


class NullAdapter(MessengerAdapter):
    """An adapter that pages nobody and answers nothing.

    This is the explicit transport for `escalation.adapter = "none"`. Every
    delivery reports `delivered=False` without raising, and every inbound event
    is reported as "not one of ours", so the factory applies its fail-safe
    default rather than waiting on a channel that does not exist.
    """

    async def deliver(self, message: RenderedMessage, correlation_id: str) -> DeliveryReceipt:
        """No messenger is configured; the message is not delivered."""
        return DeliveryReceipt(delivered=False)

    def relay(self, event: Any) -> InboundRelay | None:
        """No messenger is configured; nothing is one of ours."""
        return None


def _build_null(**_seams: Any) -> NullAdapter:
    """Build the null transport. It recognises no seams, because it has none."""
    return NullAdapter()


register_adapter("none", _build_null)
