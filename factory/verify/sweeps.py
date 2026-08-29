"""Credential sweeps over the peer channel's new surfaces (017-US1, FR-007).

The final sweep (`tests/test_final_sweep.py`) already proves no *shipped file*
carries a credential literal and no failure path renders one. A message body is
a surface none of those covers: the agent writes it, the workflow buffers it,
the store persists it, and (US3) an outbox file carries it outside the
factory's trust boundary entirely. So the rule the suite applies to shipped
files is applied to the channel's *runtime* surfaces here — one assertion,
importable by every test that drives a message through the channel.

The pattern is the one `_CREDENTIAL_LITERAL` in the final sweep matches:
``sk-`` followed by 8+ key-character bytes. A shape that walks like a key is
treated as a key: no innocent explanation for it in a message body exists.
"""

from __future__ import annotations

import re

#: The same shape the final sweep holds shipped files to, named once and
#: imported by every message-surface sweep — the day the shape tightens, the
#: channel tightens with it.
CREDENTIAL_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-]{8,}")


def credential_values_in(text: str) -> list[str]:
    """Every credential-shaped value `text` carries, or an empty list.

    Runs the one pattern the shipped-file sweep runs, so a body that would fail
    the file sweep fails here too.
    """
    return CREDENTIAL_PATTERN.findall(text)


def assert_no_credential_in_message(
    *, message_id: str, body: str, reply: str | None = None
) -> None:
    """Assert one message's stored surfaces carry no credential value (FR-007).

    The body and the reply are the two free-text columns a message row holds;
    the id is checked too because a minted id is text an agent influenced.
    Raises `AssertionError` naming the shape found, which is what a test
    driving a credential-shaped payload through the channel expects to see.
    """
    for surface_name, surface in (
        ("message body", body),
        ("reply", reply or ""),
        ("message id", message_id),
    ):
        found = credential_values_in(surface)
        assert not found, (
            f"{surface_name} carries a credential-shaped value: {found!r} — "
            "message text must never carry a credential (017-US1 FR-007)"
        )
