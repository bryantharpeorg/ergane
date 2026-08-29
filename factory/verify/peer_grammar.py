"""The addressee line: ``To: <name>`` at the head of a question's body (017-US1).

One parser, two surfaces. The 008 marker (``## OPERATOR QUESTION`` in a final
message) and the 008 ferry file (``$ATTEMPT_ARCHIVE/question``) both deliver a
*body*; this module decides what first line means. ``To: us2`` names a peer;
its absence means the body is the question, addressed to the operator —
byte-identical to 008, which is the compatibility contract (FR-001, SC-006):
the parser returns ``None`` for a body with no header and the caller hands the
original text to the 008 path without inspection.

The reply direction uses the same discipline: ``In-Reply-To: <message id>``
names the message a reply threads to (FR-003).

Line-anchored by conviction, not taste: prose that *discusses* a ``To:`` is
prose, not an address — the same rule `factory/verify/question.py` applies to
the marker heading, and for the same reason. A body that is only the header is
malformed (a question with no content parks nothing), the empty-body rule 008
already applies.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The header that names a peer. One word, a colon, the addressee.
TO_PREFIX = "To: "

#: The header a reply carries. A message id the sender was told.
IN_REPLY_TO_PREFIX = "In-Reply-To: "


@dataclass(frozen=True)
class AddressedMessage:
    """A body with its header split off.

    `body` is everything after the header line and its following newline,
    stripped of leading blank lines that were separators. `addressee` and
    `in_reply_to` are the header values stripped of surrounding whitespace.
    Exactly one of the two is normally present; both together are legal (a
    reply to a peer message is itself addressed).
    """

    addressee: str | None
    body: str
    in_reply_to: str | None = None


def parse_addressee(text: str) -> AddressedMessage | None:
    """Split an optional ``To:``/``In-Reply-To:`` header off a question body.

    ``None`` means "no header — this is an operator question": the caller uses
    the original text unchanged, and no new branch runs (the short-circuit the
    compatibility contract requires). A header line with nothing after it — or
    a body that is only the header — is malformed (the empty-body rule): the
    message is not deliverable, and ``None`` is what a question with no content
    has always meant.

    The header must sit at column 0 of the *first* line, so a body discussing
    the grammar never reads as one. Repeated headers are not a second parse —
    only the first line is examined, and a second ``To:`` inside the body is
    prose the recipient reads.
    """
    if not text:
        return None

    lines = text.split("\n")
    first = lines[0].rstrip("\r")
    in_reply_to: str | None = None
    addressee: str | None = None

    if first.startswith(IN_REPLY_TO_PREFIX):
        in_reply_to = first[len(IN_REPLY_TO_PREFIX) :].strip()
        lines = lines[1:]
    elif first.startswith(TO_PREFIX):
        addressee = first[len(TO_PREFIX) :].strip()
        lines = lines[1:]
        # A reply may be addressed and threaded in the same body; an operator
        # question may not. ``To:`` first, ``In-Reply-To:`` second.
        if lines and lines[0].startswith(IN_REPLY_TO_PREFIX):
            in_reply_to = lines[0][len(IN_REPLY_TO_PREFIX) :].strip()
            lines = lines[1:]

    if in_reply_to is None and addressee is None:
        # No header at all: the common case, and the 008 contract — the body
        # *is* the text, unmodified.
        return None

    body = "\n".join(lines).strip()
    if not body:
        # A header with no body routes nothing: the same malformed question the
        # marker detector declines (FR-010's own rule, applied one line later).
        return None
    return AddressedMessage(
        addressee=addressee, body=body, in_reply_to=in_reply_to
    )