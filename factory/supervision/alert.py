"""The one alert that cannot be a workflow. 042-US1, FR-001 and FR-002.

041 made escalation a Temporal workflow, which is right for every escalation
except one: the alert that says Temporal is down cannot be hosted by the thing
it reports dead. So the supervision probe calls the messenger seam **directly**
— a plain library call, out of band, with a local log as its only record. This
module is the caller 041 FR-002 exists for, and it runs when Temporal is gone.

Four properties carry the weight, and each is asserted rather than intended by
`tests/test_supervision_alert.py`:

- **No Temporal, at all.** Not a client, not an import, not a lazy one inside a
  function body. The test that proves it runs in a subprocess whose import
  system refuses `temporalio` outright, because a test that merely happens not
  to reach Temporal passes identically either way.
- **Fire and forget.** Nothing is started, nothing requiring an answer is
  written, and no reply is expected: the rendered message carries no actions,
  so there is no button to press, and the outcome carries no handle to wait on.
  *Silence from the operator is not a state this path tracks.* 041's
  record-and-await semantics are the wrong shape here, and reusing them would
  make this a second escalation system rather than the one visible exception.
- **Nothing raises.** A transport that explodes, one that reports it did not
  send, and a name nothing is registered under are all *data*: a supervisor
  that crashes on a failed send has stopped supervising, and the host it was
  watching is usually the reason the send failed.
- **Loud when it cannot escalate.** An undelivered alert goes to the log and to
  stderr, and `AlertOutcome.exit_code` is non-zero, because a probe that cannot
  escalate is otherwise indistinguishable from a healthy floor (FR-015). That
  is the exact failure this whole path exists to end.

What is deliberately *not* here: measuring anything, deciding whether to send,
and remembering what was sent last time. This module renders one alert and
hands it over. Liveness, memory headroom, orphan counts, the edge-trigger table
and the heartbeat interval are the probe's (US2), which keeps this module
callable from a process that has no state directory and no configuration.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import sys

from factory.notify.adapter import (
    RenderedMessage,
    UnknownAdapterError,
    configured_adapter_name,
    resolve_adapter,
)

logger = logging.getLogger(__name__)

#: What this path hands the transport in place of a correlation id.
#:
#: A constant, and a name rather than an identifier: there is nothing to
#: correlate. A minted id would imply a row somewhere that a reply could be
#: matched against, and this path writes none — the transport logs it, and no
#: press can carry it back because the message has no buttons.
SUPERVISION_CORRELATION_ID = "supervision"

#: The prefix every out-of-band alert reads under, so an operator can tell a
#: page from the supervisor apart from a page from an epic at a glance.
ALERT_PREFIX = "ergane supervision"


@dataclasses.dataclass(frozen=True)
class StackAlert:
    """One thing the supervisor observed, in the three terms FR-002 requires.

    `duration_s` arrives as data rather than being measured here: how long a
    condition has held is the probe's reading (it owns the state files US2
    adds), and a clock in this module would be a second answer to a question
    that already has one.
    """

    service: str
    condition: str
    duration_s: float


@dataclasses.dataclass(frozen=True)
class AlertOutcome:
    """What was said, and whether anybody got it.

    Three fields and no fourth. A message handle or an escalation id here would
    be the first half of a reply this path then has to wait for, which is the
    property US1-S3 forbids.
    """

    text: str
    delivered: bool
    failure: str | None = None

    @property
    def exit_code(self) -> int:
        """`0` iff the operator was paged — FR-015, in the shape a probe exits.

        The probe's unit declares `SuccessExitStatus=0 1` in the prior art
        precisely so a degraded verdict stays a report; what must never be
        silent is an alert nobody received.
        """
        return 0 if self.delivered else 1


def format_duration(seconds: float) -> str:
    """How long, in the units an operator reads on a phone at 3am.

    Two terms at most, largest first: `45s`, `1m 35s`, `2h 3m`. A negative
    reading — a probe subtracting a status file's mtime across a clock
    correction — reads as `0s` rather than backwards, because an alert about
    the supervisor's own arithmetic is not the alert that was sent.
    """
    total = int(max(0.0, seconds))
    if total >= 3600:
        return f"{total // 3600}h {(total % 3600) // 60}m"
    if total >= 60:
        return f"{total // 60}m {total % 60}s"
    return f"{total}s"


def render_alert(alert: StackAlert) -> RenderedMessage:
    """The service, the observed condition and the duration — FR-002.

    A page that says only "degraded" sends the operator to a terminal to find
    out what this code already knew, and the terminal is on the host that is
    already failing.

    No actions, deliberately: what a transport turns into buttons is what an
    operator can answer, and this path expects no answer (US1-S3).
    """
    return RenderedMessage(
        text=(
            f"{ALERT_PREFIX}: {alert.service} — {alert.condition} "
            f"(for {format_duration(alert.duration_s)})"
        )
    )


async def deliver_alert(
    alert: StackAlert, *, adapter_name: str | None = None
) -> AlertOutcome:
    """Page the operator about `alert` through the configured transport.

    The awaitable door, for a caller that already has a loop. `send_alert` is
    the one a probe calls.

    `adapter_name` names the transport; the default reads the same
    configuration every other sender reads, so the supervisor and the factory
    page the same place without a second setting to keep in step.
    """
    message = render_alert(alert)
    transport = adapter_name or ""
    try:
        transport = transport or configured_adapter_name()
        adapter = resolve_adapter(transport)
    except Exception as exc:
        # Broad on purpose. An unknown transport name, a builder that cannot
        # construct, an unreadable config: the move is identical, and it is
        # never "raise on the host that is already failing".
        return _undelivered(
            message.text,
            f"no transport resolved for {transport or 'the configured transport'}"
            f" ({type(exc).__name__}{_safe_reason(exc)})",
        )

    try:
        receipt = await adapter.deliver(message, SUPERVISION_CORRELATION_ID)
    except Exception as exc:
        # The class, never the message: an unauthorized Bot API error quotes
        # the bot token back at us, because the token is in the URL it failed
        # on. `TelegramAdapter.deliver` logs the same way for the same reason.
        return _undelivered(
            message.text, f"{transport} raised {type(exc).__name__}"
        )

    if not receipt.delivered:
        return _undelivered(
            message.text, f"{transport} reported the alert was not delivered"
        )

    logger.info("supervision alert delivered: %s", message.text)
    return AlertOutcome(text=message.text, delivered=True)


def send_alert(
    alert: StackAlert, *, adapter_name: str | None = None
) -> AlertOutcome:
    """`deliver_alert` for a caller with no event loop — the probe's door.

    A probe is a script run by a timer, and the messenger seam is async, so
    something has to own the loop. `asyncio.run` refuses to be called from
    inside a running one, and refusing is an exception; that is caught here
    like every other failure, because "the supervision alert never raises" is
    a claim about every caller and not only about the transport.
    """
    pending = deliver_alert(alert, adapter_name=adapter_name)
    try:
        return asyncio.run(pending)
    except Exception as exc:
        # A coroutine `asyncio.run` refused to start is still an unstarted
        # coroutine, and leaving it unclosed warns on collection — noise in
        # the output of the one process whose output is the alert of last
        # resort.
        pending.close()
        return _undelivered(
            render_alert(alert).text,
            f"the alert could not be run ({type(exc).__name__}); a caller with "
            "a running event loop must await deliver_alert",
        )


def _undelivered(text: str, failure: str) -> AlertOutcome:
    """Record an alert nobody received — twice, and never quietly.

    Twice because the two readers are different: the log is what an operator
    reading the journal after the fact finds, and stderr is the probe's own
    output, which is the only thing a timer's failure mail carries. Trap 6 of
    the plan is the prior art's line for this — *never fail silently here: a
    probe that cannot escalate is indistinguishable from a healthy floor*.
    """
    logger.error("supervision alert NOT delivered (%s): %s", failure, text)
    print(f"WARN: cannot escalate ({failure}): {text}", file=sys.stderr, flush=True)
    return AlertOutcome(text=text, delivered=False, failure=failure)


def _safe_reason(exc: Exception) -> str:
    """The part of a resolution failure that is safe to write down.

    `UnknownAdapterError` names the transport and the registry, which is the
    whole diagnosis and is not a credential — a deployment that asked for one
    messenger and silently got another would page the wrong place and look
    configured, so that name is the one thing worth quoting. Every other
    exception may be quoting whatever it was handed, and only its class
    survives.
    """
    if isinstance(exc, UnknownAdapterError):
        return f": {exc}"
    return ""
