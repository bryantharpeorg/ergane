"""US1 of 159: only structurally eligible managed ChatGPT state is admitted.

Every fixture below is synthetic and every result is redacted. The parser may
read credential bytes, but no token, credential JSON, or operator home path is
allowed to leave that file-copy boundary.
"""

from __future__ import annotations

import base64
import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from factory.workgraph.codex_credential import (
    CredentialDeclaration,
    CredentialFailure,
    CredentialMode,
    CredentialProviderResult,
    CredentialReadinessState,
    credential_provenance_json,
    validate_codex_credential,
)

NOW = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)
OWNER_ID = "codex-factory"
GENERATION = 17


def _encode_expiry(expires_at: datetime) -> str:
    """Encode an expiry the way Codex records it, without a real token."""
    payload = base64.urlsafe_b64encode(
        json.dumps({"exp": int(expires_at.timestamp())}).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return f"synthetic-id-token.{payload}.synthetic-signature"


def managed_payload(
    *,
    refresh_token: str = "synthetic-refresh-token",
    expires_at: datetime | None = None,
) -> dict[str, object]:
    id_token = _encode_expiry(expires_at or NOW + timedelta(hours=1))
    tokens = {
        "id_token": id_token,
        "access_token": "synthetic-access-token",
        "refresh_token": refresh_token,
        "account_id": "synthetic-account-id",
    }
    return {
        "auth_mode": "chatgpt",
        "OPENAI_API_KEY": None,
        "tokens": tokens,
        "last_refresh": (NOW - timedelta(days=1)).isoformat(),
    }


def declaration(tmp_path: Path, payload: dict[str, object] | bytes | str) -> CredentialDeclaration:
    path = tmp_path / "auth.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, bytes):
        path.write_bytes(payload)
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")
    return CredentialDeclaration(
        owner_id=OWNER_ID,
        source_path=path,
        generation=GENERATION,
    )


def assert_no_secret_or_home(
    values: object,
    *,
    path: Path,
    forbidden: tuple[str, ...],
) -> None:
    flattened = json.dumps(asdict(values) if isinstance(values, tuple) else str(values))
    assert str(path) not in flattened
    assert str(path.parent) not in flattened
    for value in forbidden:
        assert value not in flattened


def test_managed_chatgpt_shape_is_admitted_locally(tmp_path: Path) -> None:
    source = declaration(tmp_path, managed_payload())
    credential = validate_codex_credential(source, now=NOW)

    assert credential.admitted is True
    assert credential.failure is None
    assert credential.mode == CredentialMode.MANAGED_CHATGPT
    assert credential.readiness.state == CredentialReadinessState.ELIGIBLE
    assert credential.readiness.reason == "managed auth structure is locally refresh-capable"
    assert credential.readiness.access_expires_at is not None


def test_api_key_mode_is_refused_by_name_without_exposing_the_key(
    tmp_path: Path,
) -> None:
    source = declaration(
        tmp_path,
        {"auth_mode": "apikey", "OPENAI_API_KEY": "synthetic-api-key-value"},
    )
    credential = validate_codex_credential(source, now=NOW)

    assert credential.admitted is False
    assert credential.mode == CredentialMode.API_KEY
    assert credential.failure == CredentialFailure.UNSUPPORTED_MODE
    assert "API-key" in credential.refusal
    assert_no_secret_or_home(
        credential,
        path=source.source_path,
        forbidden=("synthetic-api-key-value",),
    )


def test_external_token_mode_is_refused_by_name(tmp_path: Path) -> None:
    source = declaration(
        tmp_path,
        {
            "auth_mode": "external-token",
            "CODEX_ACCESS_TOKEN": "synthetic-external-token-value",
        },
    )
    credential = validate_codex_credential(source, now=NOW)

    assert credential.admitted is False
    assert credential.mode == CredentialMode.EXTERNAL_TOKEN
    assert credential.failure == CredentialFailure.UNSUPPORTED_MODE
    assert "external-token" in credential.refusal
    assert_no_secret_or_home(
        credential,
        path=source.source_path,
        forbidden=("synthetic-external-token-value",),
    )


def test_malformed_json_is_refused_by_name(tmp_path: Path) -> None:
    source = declaration(tmp_path, b"{not-json")
    credential = validate_codex_credential(source, now=NOW)

    assert credential.admitted is False
    assert credential.mode == CredentialMode.UNKNOWN
    assert credential.failure == CredentialFailure.MALFORMED_JSON
    assert "malformed JSON" in credential.refusal


def test_missing_refresh_data_is_refused_locally(tmp_path: Path) -> None:
    payload = managed_payload()
    del payload["tokens"]  # type: ignore[misc]
    source = declaration(tmp_path, payload)
    credential = validate_codex_credential(source, now=NOW)

    assert credential.admitted is False
    assert credential.mode == CredentialMode.MANAGED_CHATGPT
    assert credential.failure == CredentialFailure.MISSING_REFRESH
    assert "refresh" in credential.refusal


def test_inaccessible_storage_is_refused_by_name(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    path.write_text(json.dumps(managed_payload()), encoding="utf-8")
    path.chmod(0o000)
    source = CredentialDeclaration(
        owner_id=OWNER_ID, source_path=path, generation=GENERATION
    )

    credential = validate_codex_credential(source, now=NOW)

    assert credential.admitted is False
    assert credential.failure == CredentialFailure.INACCESSIBLE_SOURCE
    assert "inaccessible storage" in credential.refusal
