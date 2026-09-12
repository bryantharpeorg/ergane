"""Pure redacted records for file-backed managed ChatGPT credentials.

This module reads credential bytes and returns only structural facts. It never
carries a token value, never contacts a provider, and never invents an account
qualification: offline readiness is either local eligibility or a recorded
provider result.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any


class CredentialMode(StrEnum):
    """The login shape observed in an ``auth.json`` document."""

    MANAGED_CHATGPT = "managed-chatgpt"
    API_KEY = "api-key"
    EXTERNAL_TOKEN = "external-token"
    UNKNOWN = "unknown"


class CredentialFailure(StrEnum):
    """Stable, redacted reasons a source is not structurally eligible."""

    MISSING_SOURCE = "missing-source"
    INACCESSIBLE_SOURCE = "inaccessible-source"
    MALFORMED_JSON = "malformed-json"
    UNSUPPORTED_MODE = "unsupported-mode"
    MISSING_REFRESH = "missing-refresh"
    PROVIDER_REVOKED = "provider-revoked"


class CredentialReadinessState(StrEnum):
    """Offline state, separate from account qualification."""

    ELIGIBLE = "eligible"
    ELIGIBLE_TO_ATTEMPT_REFRESH = "eligible-to-attempt-refresh"
    LOCALLY_INELIGIBLE = "locally-ineligible"
    REVOKED = "revoked"


class CredentialProviderResult(StrEnum):
    """Only a durable provider response may establish revocation."""

    REVOKED = "revoked"


@dataclass(frozen=True)
class CredentialDeclaration:
    """An explicit file source and its durable owner identity."""

    owner_id: str
    source_path: Path
    generation: int
    provider_result: CredentialProviderResult | None = None


@dataclass(frozen=True)
class CredentialProvenance:
    """The only credential facts allowed into workflow state or logs."""

    owner_id: str
    source_kind: str
    credential_mode: CredentialMode
    path_identity: str
    generation: int


@dataclass(frozen=True)
class CredentialReadiness:
    """The offline answer about the observed structure."""

    state: CredentialReadinessState
    reason: str
    access_expires_at: datetime | None = None


@dataclass(frozen=True)
class CodexCredential:
    """A redacted validation result."""

    admitted: bool
    mode: CredentialMode
    readiness: CredentialReadiness
    failure: CredentialFailure | None = None
    refusal: str = ""
    provenance: CredentialProvenance | None = None


def credential_provenance_json(provenance: CredentialProvenance) -> str:
    """Serialize the frozen redacted record without adding credential data."""
    return json.dumps(asdict(provenance), sort_keys=True, separators=(",", ":"))


def _readiness_for_managed(
    data: dict[str, Any], now: datetime
) -> tuple[CredentialFailure | None, CredentialReadiness]:
    tokens = data.get("tokens")
    if not isinstance(tokens, dict):
        return (
            CredentialFailure.MISSING_REFRESH,
            CredentialReadiness(
                state=CredentialReadinessState.LOCALLY_INELIGIBLE,
                reason="missing refresh data",
            ),
        )
    refresh_token = tokens.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token.strip():
        return (
            CredentialFailure.MISSING_REFRESH,
            CredentialReadiness(
                state=CredentialReadinessState.LOCALLY_INELIGIBLE,
                reason="missing or malformed refresh token",
            ),
        )

    id_token = tokens.get("id_token")
    expires_at = _id_token_expiry(id_token)
    if expires_at is not None and expires_at <= now:
        return (
            None,
            CredentialReadiness(
                state=CredentialReadinessState.ELIGIBLE_TO_ATTEMPT_REFRESH,
                reason="expired access with structurally present refresh data",
                access_expires_at=expires_at,
            ),
        )
    return (
        None,
        CredentialReadiness(
            state=CredentialReadinessState.ELIGIBLE,
            reason="managed auth structure is locally refresh-capable",
            access_expires_at=expires_at,
        ),
    )


def _id_token_expiry(id_token: object) -> datetime | None:
    """Read an unverified expiry without retaining or exposing token bytes."""
    if not isinstance(id_token, str):
        return None
    try:
        _, encoded_payload, _ = id_token.split(".", 2)
        encoded_payload += "=" * (-len(encoded_payload) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded_payload.encode("ascii")))
        timestamp = int(payload["exp"])
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except (KeyError, TypeError, ValueError, UnicodeError):
        return None


def _failure(
    mode: CredentialMode,
    failure: CredentialFailure,
    reason: str,
) -> CodexCredential:
    return CodexCredential(
        admitted=False,
        mode=mode,
        readiness=CredentialReadiness(
            state=CredentialReadinessState.LOCALLY_INELIGIBLE, reason=reason
        ),
        failure=failure,
        refusal=reason,
    )


def _unsupported(data: dict[str, Any]) -> CodexCredential:
    mode_value = data.get("auth_mode")
    if mode_value in {"apikey", "api_key"}:
        return _failure(
            CredentialMode.API_KEY,
            CredentialFailure.UNSUPPORTED_MODE,
            "API-key mode is not a managed ChatGPT subscription credential",
        )
    if mode_value in {"external-token", "external_token"}:
        return _failure(
            CredentialMode.EXTERNAL_TOKEN,
            CredentialFailure.UNSUPPORTED_MODE,
            "external-token mode is not a managed ChatGPT subscription credential",
        )
    return _failure(
        CredentialMode.UNKNOWN,
        CredentialFailure.UNSUPPORTED_MODE,
        "unsupported auth mode for a managed ChatGPT subscription credential",
    )


def validate_codex_credential(
    declaration: CredentialDeclaration, *, now: datetime
) -> CodexCredential:
    """Validate one declared file and return only redacted records."""
    if not declaration.owner_id.strip():
        raise ValueError("credential declaration requires a non-empty owner id")
    if declaration.generation < 1:
        raise ValueError("credential declaration requires a generation of at least 1")

    path = declaration.source_path
    try:
        if not path.is_file():
            return _failure(
                CredentialMode.UNKNOWN,
                CredentialFailure.MISSING_SOURCE,
                "credential source is missing",
            )
        try:
            raw = path.read_bytes()
        except PermissionError:
            return _failure(
                CredentialMode.UNKNOWN,
                CredentialFailure.INACCESSIBLE_SOURCE,
                "credential source has inaccessible storage",
            )
    except OSError:
        return _failure(
            CredentialMode.UNKNOWN,
            CredentialFailure.INACCESSIBLE_SOURCE,
            "credential source has inaccessible storage",
        )

    try:
        data = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _failure(
            CredentialMode.UNKNOWN,
            CredentialFailure.MALFORMED_JSON,
            "credential source contains malformed JSON",
        )
    if not isinstance(data, dict):
        return _unsupported({})

    mode = (
        CredentialMode.MANAGED_CHATGPT
        if data.get("auth_mode") == "chatgpt"
        else CredentialMode.UNKNOWN
    )
    if mode is not CredentialMode.MANAGED_CHATGPT:
        return _unsupported(data)

    if declaration.provider_result is CredentialProviderResult.REVOKED:
        return CodexCredential(
            admitted=False,
            mode=mode,
            readiness=CredentialReadiness(
                state=CredentialReadinessState.REVOKED,
                reason="recorded Codex provider result revoked this generation",
            ),
            failure=CredentialFailure.PROVIDER_REVOKED,
            refusal="recorded Codex provider result revoked this generation",
        )

    failure, readiness = _readiness_for_managed(data, now)
    if failure is not None:
        return _failure(mode, failure, readiness.reason)

    path_identity = hashlib.sha256(str(path.absolute()).encode("utf-8")).hexdigest()
    provenance = CredentialProvenance(
        owner_id=declaration.owner_id,
        source_kind="codex-file",
        credential_mode=mode,
        path_identity=path_identity,
        generation=declaration.generation,
    )
    return CodexCredential(
        admitted=True,
        mode=mode,
        readiness=readiness,
        provenance=provenance,
    )

