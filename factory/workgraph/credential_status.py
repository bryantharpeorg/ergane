"""Operator surface: how long the subscription credential runway is.

US3 (FR-011). This module reads the same precedence US2 established inside the
adapter rather than re-deriving it (trap 10):

1. If `CLAUDE_CODE_OAUTH_TOKEN` is present in the worker environment, the long-
   lived token is the credential source and no copied-credential expiry matters.
2. If the token is absent but a copied credential is discoverable, its recorded
   `expiresAt` is read locally (no network call) and reported as remaining
   validity.
3. If neither is present, the answer says so and names both remedies.

The renderer never emits a credential value (trap 4). It prints source, validity
and remedies only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from factory.workgraph.adapter import (
    CLAUDE_CODE_OAUTH_TOKEN,
    CREDENTIAL_SOURCE_COPIED_CREDENTIALS,
    CREDENTIAL_SOURCE_OAUTH_TOKEN,
    _credential_expiry,
    _operator_home,
    discover_subscription_credential,
)


@dataclass(frozen=True)
class CredentialStatus:
    """The answer the operator surface prints."""

    source: str | None
    expires_at: datetime | None
    remedies: tuple[str, ...] = ()


def _credential_runway(
    *,
    operator_home: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> CredentialStatus:
    """Pure determination of credential source and remaining validity.

    Reads the precedence US2 established in the adapter: the long-lived token wins
    when present; otherwise a discoverable copied credential is inspected.
    """
    source = os.environ if environ is None else environ
    token = source.get(CLAUDE_CODE_OAUTH_TOKEN)
    if token:
        return CredentialStatus(source=CREDENTIAL_SOURCE_OAUTH_TOKEN, expires_at=None)

    if operator_home is None:
        operator_home = _operator_home()
    credential_path = discover_subscription_credential(operator_home=operator_home)
    if credential_path is not None:
        expires_at = _credential_expiry(credential_path)
        return CredentialStatus(
            source=CREDENTIAL_SOURCE_COPIED_CREDENTIALS,
            expires_at=expires_at,
        )

    return CredentialStatus(
        source=None,
        expires_at=None,
        remedies=(
            "run `claude auth login` on the worker host",
            f"set {CLAUDE_CODE_OAUTH_TOKEN} to a long-lived token from `claude setup-token`",
        ),
    )


def credential_status(
    *,
    operator_home: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> CredentialStatus:
    """Public seam: the operator-facing credential runway answer."""
    return _credential_runway(operator_home=operator_home, environ=environ)


def _format_expiry(expires_at: datetime) -> str:
    """Human-readable remaining validity, never a credential value."""
    now = datetime.now(timezone.utc)
    remaining = expires_at - now
    total_seconds = int(remaining.total_seconds())
    if total_seconds <= 0:
        return "expired"
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)


def render_credential_status(status: CredentialStatus) -> str:
    """Render the answer the operator reads. No credential value may appear."""
    if status.source == CREDENTIAL_SOURCE_OAUTH_TOKEN:
        return "credential source: long-lived OAuth token (no expiry)"
    if status.source == CREDENTIAL_SOURCE_COPIED_CREDENTIALS:
        validity = (
            f"expires in {_format_expiry(status.expires_at)}"
            if status.expires_at is not None
            else "remaining validity unknown"
        )
        return f"credential source: copied interactive credential ({validity})"
    remedies = "; ".join(status.remedies)
    return f"credential source: none found. Remedies: {remedies}"
