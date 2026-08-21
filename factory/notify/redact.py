"""Credentials do not reach the journal — and the request line still does.

064-US1. `factory/supervision/units.py:425` is where this repository already
states the commitment: an operator's environment command runs from a script
rather than from `Environment=` lines, because the latter "would write their
credentials to disk in a file the journal echoes back". The journal got them
anyway, from the one direction no factory module owns — `httpx` logs every
request at INFO with the full URL, and a Telegram URL *is*
`https://api.telegram.org/bot<TOKEN>/sendMessage`. Every escalation and every
long-poll iteration printed the bot token into `journalctl --user -u
ergane-worker`, which is the first thing an operator pastes into a chat window
when delivery misbehaves.

Three shapes of fix were available, and this module is the third:

- **Raise the `httpx` logger to WARNING.** One line, and it deletes the request
  line entirely — including the one an operator debugging a failed delivery
  needs. It trades a security problem for an operability one (plan trap 1).
- **A redacting `httpx` event hook.** The obvious answer, and it does not work.
  httpx emits its own `HTTP Request:` line inside `_send_single_request`, so a
  request/response hook runs *after* the line is already in the journal and
  cannot alter it. Worse, for Telegram there is no client to hook: PTB builds
  its `httpx.AsyncClient` internally (plan trap 12), so a fix that attaches to
  clients factory code constructs covers the webhook and leaves the reported
  leak exactly where it was.
- **Redact the log record itself, at the moment it is created.** A
  `logging.setLogRecordFactory` wrapper sees every record from every logger in
  the process — the ones `httpx` emits, the ones a library nobody here imports
  emits, the ones written before any handler exists. That is what makes FR-003
  true rather than aspirational: it depends on no logger name, no handler, no
  propagation, and no caller remembering to configure logging.

What is redacted is the union of two rules, deliberately overlapping:

1. **Registered values.** `register_secret` is called at the seams a credential
   passes through — `open_bot`, `run_bridge`, and each adapter's `deliver` — so
   the exact token is removed wherever it surfaces, in any spelling of any
   message. `register_url_secret` does the same for a webhook whose secret is
   its path or its query, which is how most incoming-webhook endpoints are
   configured (FR-004), keeping the origin so the destination is still legible.
2. **A shape.** `<digits>:<secret>` is the Bot API's token format, redacted
   whether or not anything registered it. Registration cannot cover a token this
   process never handled — one quoted by a subprocess, or by a library reading
   the environment for itself — and the shape can.

Both renderings are covered, because a traceback is a rendering too and httpx
puts the failing URL in the exception's own message (plan trap 4): records carry
their redacted traceback in `exc_text`, and the interpreter's own last-resort
printer is wrapped so an uncaught error prints the same way.

This is a redaction, not a vault. It keeps a credential out of a file that is
routinely shared; it does not make the process that holds the credential
trustworthy, and nothing here is a substitute for the standing rule that secrets
live in the worker environment and never enter payloads or orchestration state
(constitution V).
"""

from __future__ import annotations

import logging
import re
import sys
import traceback
from types import TracebackType
from typing import Any, Callable
from urllib.parse import urlsplit

#: What a secret becomes. Distinctive rather than a run of asterisks, so a
#: reader of the journal can tell "this was removed on purpose" from "the URL
#: was always like that", and so a test can assert the line survived redaction
#: rather than merely failing to contain a token.
REDACTED = "<redacted>"

#: Exact values to remove, mapped to what replaces each. Process-global because
#: the thing it protects is process-global: a record created anywhere in this
#: interpreter can carry a credential, including from libraries this package
#: never imports.
_SECRETS: dict[str, str] = {}

#: Nothing shorter is a credential, and a short string registered by accident
#: would corrupt unrelated messages wherever it happened to appear.
_MIN_SECRET = 4

#: The Bot API's token format — `<bot id>:<secret>` — matched wherever it
#: appears, so a token nothing registered is still removed. The lengths are
#: chosen to bracket real tokens (a 9-10 digit id, a 35-character secret)
#: without matching a timestamp, a `key: value` line, or an `HH:MM:SS` clock.
_TOKEN_SHAPED = re.compile(r"\d{5,}:[A-Za-z0-9_-]{20,}")


def register_secret(value: str | None, *, replacement: str = REDACTED) -> None:
    """Remove `value` from every log record and traceback from now on.

    Idempotent and cheap, so the seams that handle a credential can call it on
    every send rather than reasoning about whether an earlier call happened.
    An absent or implausibly short value is ignored: a missing credential is
    reported by name elsewhere, and registering `""` would be a substring of
    everything.
    """
    if not value or len(value) < _MIN_SECRET:
        return
    _SECRETS[value] = replacement


def register_url_secret(url: str | None) -> None:
    """Remove the secret-bearing part of `url`, keeping its origin.

    A webhook's credential is normally its path or its query string, and the
    whole URL is therefore unsafe to log while the origin is exactly what an
    operator needs in order to see where an escalation went (FR-002, FR-004).
    Everything after `scheme://host` is registered; a URL that is only an origin
    carries no secret and registers nothing.
    """
    if not url:
        return

    split = urlsplit(url)
    if not split.scheme or not split.netloc:
        return

    if split.password:
        register_secret(split.password)

    tail = url[len(f"{split.scheme}://{split.netloc}") :]
    if len(tail.strip("/")) >= 1:
        register_secret(tail, replacement=f"/{REDACTED}")


def redact(text: str) -> str:
    """`text` with every known credential and every token-shaped run removed."""
    for secret, replacement in _SECRETS.items():
        if secret in text:
            text = text.replace(secret, replacement)
    return _TOKEN_SHAPED.sub(REDACTED, text)


def install_redaction() -> None:
    """Make this process incapable of writing a credential down. Idempotent.

    Called from the construction seams rather than from call sites (FR-003), so
    an adapter that exists at all is an adapter that is protected, and the next
    transport someone writes inherits it by building on the same seams instead
    of by remembering this page.

    It reads like noise at a call site — a bare call returning nothing, in a
    constructor that otherwise only stores a seam — so before deleting one, read
    `factory/supervision/units.py:425`. The commitment it upholds is stated
    there: credentials are not written "to disk in a file the journal echoes
    back". This is the other half of that promise, on the side the journal is
    written from rather than the side it is generated by.

    It *wraps* whatever record factory is already installed rather than
    replacing it, so a caller who put their own fields on every record keeps
    them, and installing twice is installing once.
    """
    previous = logging.getLogRecordFactory()
    if not getattr(previous, "__ergane_redacting__", False):
        logging.setLogRecordFactory(_redacting_factory(previous))

    # Only the interpreter's default is replaced. A caller who installed their
    # own hook chose what happens to an uncaught traceback, and silently
    # discarding that choice would be a worse surprise than the one leak it
    # closes; the logging path above still covers everything they log.
    if sys.excepthook is sys.__excepthook__:
        sys.excepthook = _redacting_excepthook


def configure_logging(level: int = logging.INFO) -> None:
    """The logging setup a factory process starts with — protection included.

    Both entry points call exactly this instead of `logging.basicConfig`
    (FR-003): the worker and the operator bridge write to two different
    journals, and a fix applied to one leaks from the other. Redaction is
    installed *before* the handlers exist, so there is no window in which a
    record is emitted unprotected.
    """
    install_redaction()
    logging.basicConfig(level=level)


def _redacting_factory(
    previous: Callable[..., logging.LogRecord],
) -> Callable[..., logging.LogRecord]:
    """Wrap a record factory so every record it makes is already redacted."""

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        return _redact_record(previous(*args, **kwargs))

    factory.__ergane_redacting__ = True  # type: ignore[attr-defined]
    factory.__ergane_wrapped__ = previous  # type: ignore[attr-defined]
    return factory


def _redact_record(record: logging.LogRecord) -> logging.LogRecord:
    """Remove credentials from one record, in every form it can be rendered.

    The message is redacted *after* interpolation and the arguments are then
    dropped, because a credential usually arrives as an argument (httpx logs the
    URL as one) and a handler that re-interpolated would put it back.
    """
    try:
        message = record.getMessage()
    except Exception:  # pragma: no cover - a broken format string is not ours
        return record

    redacted = redact(message)
    if redacted != message:
        record.msg = redacted
        record.args = None

    if record.exc_info and record.exc_text is None:
        # Pre-rendered here, and only when it differs, so `Formatter` reuses
        # this text instead of formatting the exception itself. That is the only
        # place the traceback — which quotes the URL httpx failed on — is
        # written out (trap 4).
        rendered = _format_exception(record.exc_info)
        if rendered is not None:
            cleaned = redact(rendered)
            if cleaned != rendered:
                record.exc_text = cleaned.rstrip("\n")

    if record.stack_info:
        record.stack_info = redact(record.stack_info)

    return record


def _format_exception(exc_info: Any) -> str | None:
    """The traceback as a formatter would write it, or None if it cannot be."""
    try:
        return "".join(traceback.format_exception(*exc_info))
    except Exception:  # pragma: no cover - defensive: never break logging
        return None


def _redacting_excepthook(
    exc_type: type[BaseException],
    exc: BaseException,
    tb: TracebackType | None,
) -> None:
    """Print an uncaught traceback the way Python does, minus the credentials.

    The last rendering path: a worker that dies on an httpx error prints the
    failing URL to stderr, and stderr is the journal. `sys.stderr` is looked up
    at call time rather than captured, so redirection still works.
    """
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    sys.stderr.write(redact(text))


_redacting_excepthook.__ergane_redacting__ = True  # type: ignore[attr-defined]
