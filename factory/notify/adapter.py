"""The messenger seam: two operations, and nothing that decides anything.

041-US1. Everything that makes an escalation *escalation* — the workflow
lifecycle, expiry, answer-once, and the standing rule that nothing ever presses
an escalation button on the operator's behalf — is factory-side and
messenger-agnostic. What crosses this seam is exactly two operations:

- **outbound** `deliver(rendered message, correlation id)`, and
- **inbound** `relay(transport event)` → correlation id, reply text, sender
  identity.

There is deliberately no third. An adapter that could acknowledge, answer or
expire would be deciding something, and the seam exists to keep those decisions
on the factory side of it (FR-001). The identity check US4 adds is factory-side
for the same reason: an adapter that filtered replies would be making an
answer-or-not decision.

Three decisions carry the weight:

- **The message arrives already rendered.** `factory/notify/messages.py` owns
  what an operator reads, including the button faces and the ≤64-byte payload
  behind each one (R11). An adapter that composed text would make what the
  operator is asked a property of the transport, so switching transports would
  silently change the question.
- **This module is a plain library (FR-002).** No Temporal import, no client,
  no workflow context — not at module scope and not lazily inside a function.
  042's supervision probe calls an adapter directly to report that Temporal is
  down, and an alert about a dead orchestrator cannot be hosted by the
  orchestrator.
- **A transport that could not send is data, not an error.** `DeliveryReceipt`
  reports it; nothing raises. The factory's answer to "nobody was paged" is to
  apply its own default now (R11), and an exception would hand that decision to
  a retry policy instead.

Adapters are registered under the names 033's config declares
(`factory/controlplane/config.py`, `KNOWN_ESC_ADAPTERS`), so a name the parser
already refused never reaches the registry.
"""

from __future__ import annotations

import dataclasses
import logging
import os
from importlib import import_module
from typing import Any, Callable, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

#: Which transport this process pages over, when the caller does not name one.
#: A worker-local override that beats the control-plane file: 042's probe and a
#: test both need to select a transport without editing an operator's config,
#: and the config's closed set cannot admit a name that is not shipped.
ESCALATION_ADAPTER_ENV = "ERGANE_ESCALATION_ADAPTER"

#: 008's transport, and the one every deployment has until it says otherwise.
DEFAULT_ADAPTER = "telegram"

#: What a relay reports when the transport's event names no sender at all.
#: A value rather than an exception on purpose: US4 checks identity against a
#: configured list, and "unknown" has to be something that list can fail to
#: contain rather than something that never reaches it.
UNKNOWN_SENDER = "unknown"

#: Adapters that ship with the factory, and the module that registers each on
#: import. Imported lazily at resolve time so this module stays free of the
#: transports' own dependencies.
#:
#: Keyed by the same names 033's `KNOWN_ESC_ADAPTERS` admits, and held to it by
#: `tests/test_messenger_adapter.py::test_the_conformance_suite_covers_every_adapter_that_ships`:
#: a name the parser accepts with nothing registered under it pages nobody, and
#: a name registered here that the parser refuses is not selectable.
_BUILTIN_ADAPTER_MODULES = {
    DEFAULT_ADAPTER: "factory.notify.service",
    "webhook": "factory.notify.webhook",
}


@dataclasses.dataclass(frozen=True)
class MessageAction:
    """One thing the operator can press, rendered but not yet transported.

    `label` is the face they read; `payload` is what a press carries back and
    becomes an `InboundRelay.correlation_id`. Both are composed factory-side —
    for Telegram, `payload` is the ≤64-byte `callback_data` R11 designed.
    """

    label: str
    payload: str


@dataclasses.dataclass(frozen=True)
class RenderedMessage:
    """What the operator reads, composed before any transport sees it.

    `actions` is empty for anything the operator answers by typing: a question
    carries no buttons (008 FR-008), and a notice offers no choice at all.
    """

    text: str
    actions: tuple[MessageAction, ...] = ()


@dataclasses.dataclass(frozen=True)
class DeliveryReceipt:
    """What the transport did with one message — never what it means.

    `delivered=False` is the whole vocabulary for "nobody was paged": an unset
    credential, a refused connection and an API that said no are deliberately
    not distinguished, because the factory's move is identical for all three.
    `message_id` is the handle the transport minted, when it has one; it is the
    routing key a free-text reply threads back to (008 FR-008), and ``None``
    when the transport has no such notion.
    """

    delivered: bool
    message_id: int | None = None


@dataclasses.dataclass(frozen=True)
class InboundRelay:
    """One inbound reply, in the only three terms the factory needs.

    `correlation_id` is the handle the transport can actually carry back: the
    id the factory minted when the transport can hold one (a Telegram press
    carries the escalation id in its `callback_data`), and the transport's own
    message handle when it cannot (a free-text reply quotes a message id, which
    is the key the factory stored at send time). Resolving either to a factory
    row is the factory's job and never the adapter's.

    `sender_identity` is reported, never judged. US4's authorized-responders
    check reads it factory-side (FR-011); an adapter that decided whether a
    sender may answer would be making the one decision this seam exists to keep
    out of the transport.
    """

    correlation_id: str
    reply_text: str
    sender_identity: str


@runtime_checkable
class MessengerAdapter(Protocol):
    """The transport seam. Two operations, and no third."""

    async def deliver(
        self, message: RenderedMessage, correlation_id: str
    ) -> DeliveryReceipt:
        """Put one already-rendered message in front of the operator.

        Reports what happened and decides nothing. A transport that is down,
        unconfigured or refusing returns `delivered=False`; it does not raise,
        because the factory applies its own fail-safe default rather than
        waiting out a deadline for a message nobody received (R11).
        """
        ...

    def relay(self, event: Any) -> InboundRelay | None:
        """Translate one transport-native inbound event into the three terms.

        Pure translation: it looks nothing up, answers nobody, and touches no
        row. ``None`` means "not one of ours" — a button from another handler,
        a message quoting nothing, an event from another feature entirely — and
        what to *say* about that is the factory's call, not the transport's.
        """
        ...


class UnknownAdapterError(ValueError):
    """A transport name nothing is registered under.

    Raised rather than defaulted: a deployment that asked for one messenger and
    silently got another would page the wrong place and look configured.
    """


AdapterBuilder = Callable[..., MessengerAdapter]

_REGISTRY: dict[str, AdapterBuilder] = {}


def register_adapter(name: str, build: AdapterBuilder) -> None:
    """Register `build` under `name` — one of the names 033's config admits.

    The builder takes keyword *seams* (see `resolve_adapter`) and returns an
    adapter. Registering is how a transport becomes selectable; nothing else
    in the factory knows the transports by name.
    """
    _REGISTRY[name] = build


def unregister_adapter(name: str) -> None:
    """Forget `name`. Exists so a test registration cannot outlive its test."""
    _REGISTRY.pop(name, None)


def registered_adapters() -> tuple[str, ...]:
    """Every selectable transport name, built-ins included."""
    _load_builtins()
    return tuple(sorted(_REGISTRY))


def configured_adapter_name() -> str:
    """Which transport this process pages over.

    The worker-local override wins, then the control-plane file's
    `escalation.adapter`, then 008's reference transport. Read from the process
    environment, which is legitimate here and in an activity — this module
    defines no workflow, so 039's guard neither covers it nor needs to.
    """
    override = os.environ.get(ESCALATION_ADAPTER_ENV)
    if override:
        return override
    return _control_plane_adapter() or DEFAULT_ADAPTER


def resolve_adapter(name: str | None = None, **seams: Any) -> MessengerAdapter:
    """Build the transport named by `name`, or the configured one.

    `seams` are transport-specific handles the *caller's own process* owns —
    the send activity's patchable bot opener, for instance. A builder takes
    what it recognises and ignores the rest, because a caller resolving a
    transport by name cannot know which one it got.
    """
    chosen = name or configured_adapter_name()
    build = _REGISTRY.get(chosen)
    if build is None:
        _load_builtins()
        build = _REGISTRY.get(chosen)
    if build is None:
        raise UnknownAdapterError(
            f"no messenger adapter is registered under {chosen!r}; "
            f"registered adapters are {', '.join(sorted(_REGISTRY)) or '(none)'}"
        )
    return build(**seams)


def _load_builtins() -> None:
    """Import the modules that register the shipped transports, once each."""
    for name, module in _BUILTIN_ADAPTER_MODULES.items():
        if name not in _REGISTRY:
            import_module(module)


def _control_plane_adapter() -> str | None:
    """`escalation.adapter` from the control-plane file, or ``None``.

    ``None`` covers a deployment with no control-plane file and one whose file
    this process cannot parse. The reference transport is the answer either
    way: refusing to page an operator because a config file is malformed would
    make the config parser the thing that silences the channel, and 033 already
    refuses a bad file at every command that reads it deliberately.
    """
    try:
        from factory.controlplane.config import (
            ControlPlaneConfigError,
            load_controlplane_config,
        )
    except ImportError:  # pragma: no cover - the control plane is always shipped
        return None

    try:
        return load_controlplane_config().escalation.adapter
    except (ControlPlaneConfigError, OSError) as exc:
        logger.debug("no control-plane escalation adapter (%s)", type(exc).__name__)
        return None
