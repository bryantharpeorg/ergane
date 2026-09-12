"""Pure redacted records for file-backed managed ChatGPT credentials.

This module reads credential bytes and returns only structural facts. It never
carries a token value, never contacts a provider, and never invents an account
qualification: offline readiness is either local eligibility or a recorded
provider result.
"""

from __future__ import annotations

import base64
import asyncio
import hashlib
import json
import os
import stat
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

from factory.locking import LockUnavailable, exclusive_lock


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
class CredentialOwnerKey:
    """The redacted durable identity that names one owner on one host."""

    owner_id: str
    host_id: str


@dataclass(frozen=True)
class CredentialOwnerRoots:
    """Resolution and admission for one host's operator-owned owner state."""

    root: Path
    host_id: str
    operator_uid: int | None = None

    def owner_directory(
        self,
        declaration: CredentialDeclaration,
        *,
        epic_id: str = "",
        target_repo: str = "",
        deployment_shape: str = "",
    ) -> Path:
        """Resolve one caller to the credential's host-global owner directory."""
        del epic_id, target_repo, deployment_shape
        if not declaration.owner_id.strip():
            raise ValueError("credential declaration requires a non-empty owner id")
        if not self.host_id.strip():
            raise ValueError("credential owner requires a non-empty host id")
        for name in (self.host_id, declaration.owner_id):
            if Path(name).name != name or name in {".", ".."}:
                raise ValueError("credential owner names must be simple directory names")
        return self.root / self.host_id / declaration.owner_id

    async def admit_concurrently(
        self,
        first: Path,
        second: Path,
        declaration: CredentialDeclaration | None = None,
    ) -> tuple[CredentialLease | None, CredentialBusy | None]:
        """Try two callers in one host-global owner and return exactly one lease."""
        try:
            lease = await self.admit(first, declaration)
        except CredentialOwnerBusy:
            return None, CredentialBusy(retry_after_s=1.0)
        try:
            await self.admit(second, declaration)
        except CredentialOwnerBusy as busy:
            await self.release(lease, owner_directory=first)
            return lease, busy
        await self.release(lease, owner_directory=first)
        return None, CredentialBusy(retry_after_s=1.0)

    async def admit(
        self,
        owner_directory: Path,
        declaration: CredentialDeclaration | None = None,
    ) -> CredentialLease:
        """Acquire a short transaction lease or report BUSY immediately."""
        _prepare_private_owner_root(self.root, self.operator_uid)
        owner_directory.parent.mkdir(parents=True, exist_ok=True)
        owner_directory.mkdir(mode=0o700, exist_ok=True)
        _validate_private_root(owner_directory, self.operator_uid)
        manifest = {
            "owner_id": declaration.owner_id if declaration else "",
            "host_id": self.host_id,
            "generation": declaration.generation if declaration else 1,
        }
        manifest_path = owner_directory / "owner-manifest.json"
        if not manifest_path.exists():
            temporary = manifest_path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(manifest), encoding="utf-8")
            temporary.chmod(0o600)
            temporary.replace(manifest_path)
        else:
            observed = json.loads(manifest_path.read_text(encoding="utf-8"))
            if observed != manifest:
                raise ValueError("credential owner manifest does not match declaration")
        try:
            with exclusive_lock(owner_directory / "transaction", timeout_s=0):
                active_path = owner_directory / "active-lease.json"
                if active_path.exists():
                    raise CredentialOwnerBusy(retry_after_s=1.0)
                lease = CredentialLease(
                    owner_id=declaration.owner_id if declaration else "",
                    host_id=self.host_id,
                    token=str(uuid.uuid4()),
                )
                lease_path = active_path.with_suffix(".json.tmp")
                lease_path.write_text(json.dumps(asdict(lease)), encoding="utf-8")
                lease_path.chmod(0o600)
                lease_path.replace(active_path)
                return lease
        except LockUnavailable as unavailable:
            raise CredentialOwnerBusy(retry_after_s=1.0) from unavailable

    async def release(self, lease: CredentialLease, *, owner_directory: Path) -> None:
        """Remove the durable active-use marker exactly once."""
        path = owner_directory / "active-lease.json"
        if not path.exists():
            return
        active = json.loads(path.read_text(encoding="utf-8"))
        if active.get("token") != lease.token:
            raise ValueError("credential lease does not own this active use")
        path.unlink()


@dataclass(frozen=True)
class CredentialProvenance:
    """The only credential facts allowed into workflow state or logs."""

    owner_id: str
    source_kind: str
    credential_mode: CredentialMode
    path_identity: str
    generation: int


@dataclass(frozen=True)
class CredentialLease:
    """The redacted handle returned while one caller owns admission."""

    owner_id: str
    host_id: str
    token: str


@dataclass(frozen=True)
class CredentialBusy:
    """BUSY as data: workflow time, not a blocking activity wait."""

    retry_after_s: float


@dataclass
class CredentialOwnerBusy(Exception):
    """The short owner transaction found another active use."""

    retry_after_s: float


def _prepare_private_owner_root(root: Path, operator_uid: int | None) -> None:
    if root.exists() and root.is_symlink():
        raise ValueError("credential owner root must not be a symlink")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    _validate_private_root(root, operator_uid)


def _validate_private_root(root: Path, operator_uid: int | None) -> None:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("credential owner root must be a private directory")
    mode = stat.S_IMODE(root.stat().st_mode)
    if mode != 0o700:
        raise ValueError("credential owner root must have 0700 permissions")
    if operator_uid is not None and root.stat().st_uid != operator_uid:
        raise ValueError("credential owner root must be owned by the declared operator identity")




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
