"""Pure redacted records for file-backed managed ChatGPT credentials.

This module reads credential bytes and returns only structural facts. It never
carries a token value, never contacts a provider, and never invents an account
qualification: offline readiness is either local eligibility or a recorded
provider result.
"""

from __future__ import annotations

import base64
import shutil
import contextlib
import hashlib
import json
import os
import stat
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

from factory.locking import LockUnavailable, exclusive_lock
from temporalio import activity, workflow
from temporalio.exceptions import ApplicationError


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


class CredentialOutcome(StrEnum):
    """A durable owner outcome, safe to release ownership after."""

    COMMITTED = "committed"
    QUARANTINED = "quarantined"


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
class CredentialOwnerTopology:
    """The declared operator-state roots that serve one credential identity."""

    roots: tuple[CredentialOwnerRoots, ...]

    def readiness_refusal(
        self, declaration: CredentialDeclaration
    ) -> str | None:
        """Refuse multi-host or multi-root declarations before any admission."""
        if not self.roots:
            return "credential owner topology declares no operator state root"
        hosts = {roots.host_id for roots in self.roots}
        if len(hosts) != 1:
            return "credential owner topology must declare one host"
        fingerprints = {
            (str(roots.root.resolve(strict=False)), roots.host_id)
            for roots in self.roots
        }
        if len(fingerprints) != 1:
            return (
                "credential owner topology must declare one operator state root "
                "on that host"
            )
        for roots in self.roots:
            path = roots.owner_directory(declaration)
            manifest_path = path / "owner-manifest.json"
            if not manifest_path.exists():
                continue
            try:
                observed = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return "credential owner manifest is unreadable"
            if observed.get("host_id") != roots.host_id:
                return "credential owner manifest declares another host"
            if observed.get("owner_id") != declaration.owner_id:
                return "credential owner manifest declares another credential"
        return None


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

    def source_identity(self, declaration: CredentialDeclaration) -> str:
        """The redacted identity of the declared source, never its bytes."""
        return hashlib.sha256(
            str(declaration.source_path.resolve(strict=False)).encode("utf-8")
        ).hexdigest()

    async def admit_concurrently(
        self,
        first: Path,
        second: Path,
        declaration: CredentialDeclaration | None = None,
    ) -> tuple[CredentialLease | None, CredentialBusy | None]:
        """Return the holder's lease and the second caller's BUSY result.

        The returned lease remains active; the caller owns its release.
        """
        try:
            lease = await self.admit(first, declaration)
        except CredentialOwnerBusy:
            return None, CredentialBusy(retry_after_s=1.0)
        try:
            await self.admit(second, declaration)
        except CredentialOwnerBusy as busy:
            return lease, busy
        raise ValueError("credential owner admitted two concurrent callers")

    async def admit(
        self,
        owner_directory: Path,
        declaration: CredentialDeclaration | None = None,
    ) -> CredentialLease:
        """Acquire a short transaction lease or report BUSY immediately."""
        if declaration is None:
            raise ValueError("credential owner admission requires a declaration")
        _prepare_private_owner_root(self.root, self.operator_uid)
        owner_directory.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        _validate_private_root(owner_directory.parent, self.operator_uid)
        owner_directory.mkdir(mode=0o700, exist_ok=True)
        if owner_directory.is_symlink():
            raise ValueError("credential owner directory must not be a symlink")
        _validate_private_root(owner_directory, self.operator_uid)
        root_stat = self.root.stat()
        manifest = {
            "owner_id": declaration.owner_id,
            "host_id": self.host_id,
            "generation": declaration.generation,
            "source_identity": self.source_identity(declaration),
            "root_device": root_stat.st_dev,
            "root_inode": root_stat.st_ino,
        }
        manifest_path = owner_directory / "owner-manifest.json"
        try:
            with exclusive_lock(owner_directory / "transaction", timeout_s=0):
                if not manifest_path.exists():
                    temporary = manifest_path.with_suffix(".json.tmp")
                    temporary.write_text(json.dumps(manifest), encoding="utf-8")
                    temporary.chmod(0o600)
                    temporary.replace(manifest_path)
                else:
                    observed = json.loads(manifest_path.read_text(encoding="utf-8"))
                    if observed != manifest:
                        if observed.get("host_id") != self.host_id:
                            raise ValueError(
                                "credential owner manifest declares another host"
                            )
                        if observed.get("owner_id") != declaration.owner_id:
                            raise ValueError(
                                "credential owner manifest declares another credential"
                            )
                        if (
                            observed.get("root_device") != root_stat.st_dev
                            or observed.get("root_inode") != root_stat.st_ino
                        ):
                            raise ValueError(
                                "credential owner root was replaced after declaration"
                            )
                        raise ValueError(
                            "credential owner manifest does not match declaration"
                        )
                active_path = owner_directory / "active-lease.json"
                if active_path.exists():
                    raise CredentialOwnerBusy(retry_after_s=1.0)
                lease = CredentialLease(
                    owner_id=declaration.owner_id,
                    host_id=self.host_id,
                    lease_id=str(uuid.uuid4()),
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
        _validate_private_root(self.root, self.operator_uid)
        _validate_private_root(owner_directory, self.operator_uid)
        path = owner_directory / "active-lease.json"
        if not path.exists():
            return
        with exclusive_lock(owner_directory / "transaction", timeout_s=0):
            if not path.exists():
                return
            active = json.loads(path.read_text(encoding="utf-8"))
            if active.get("lease_id") != lease.lease_id:
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
    lease_id: str


@dataclass(frozen=True)
class CredentialCandidate:
    """A candidate path plus redacted generation; its bytes never enter here."""

    path: Path
    generation: int
    provider_result: CredentialProviderResult | None = None


@dataclass(frozen=True)
class CredentialFinalization:
    """What happened after the current child was fenced."""

    candidate: CredentialCandidate
    result: Any = None
    retained_ownership: bool = False
    fence_error: str = ""


class CredentialPersistenceError(Exception):
    """Owner storage could not be completed without an ambiguous state change."""


@dataclass(frozen=True)
class CredentialOwnerFinalization:
    """The durable result of one fenced candidate, without candidate bytes."""

    candidate: CredentialCandidate
    outcome: CredentialOutcome
    committed_generation: int | None = None
    quarantine_path: Path | None = None
    failure: CredentialFailure | None = None
    replayed: bool = False
    release_ownership: bool = False


class CredentialFenceFailure(Exception):
    """A process group could not be proved reaped before credential reads."""


async def fence_prior_child_before_candidate(
    reap: Callable[[object], Awaitable[None] | None],
    inspect_candidate: Callable[[CredentialCandidate], Any],
    pid_file: object,
    candidate_path: Path,
    *,
    generation: int,
) -> Any:
    """Run a prior child's fence, and only then inspect its candidate."""
    candidate = CredentialCandidate(path=candidate_path, generation=generation)
    await _invoke_reap(reap, pid_file)
    return await inspect_candidate(candidate)


async def finalize_current_candidate(
    terminate: Callable[[], Awaitable[None] | None],
    prove: Callable[[], Awaitable[None] | None],
    inspect_candidate: Callable[[CredentialCandidate], Any],
    candidate_path: Path,
    *,
    generation: int,
    quarantine: Callable[[CredentialCandidate], None] | None = None,
) -> CredentialFinalization:
    """Terminate, prove death, and only then read the candidate."""
    candidate = CredentialCandidate(path=candidate_path, generation=generation)
    await _invoke_termination(terminate)
    try:
        await _invoke_termination(prove)
    except CredentialFenceFailure as error:
        if quarantine is None:
            raise
        quarantine(candidate)
        return CredentialFinalization(
            candidate=candidate,
            retained_ownership=True,
            fence_error=str(error),
        )
    result = inspect_candidate(candidate)
    if result is not None and hasattr(result, "__await__"):
        result = await result
    return CredentialFinalization(
        candidate=candidate,
        result=result,
    )


def quarantine_candidate(
    owner_directory: Path,
    candidate_path: Path,
    *,
    generation: int,
) -> Path:
    """Move an unread candidate out of staging without changing its bytes."""
    quarantine_directory = owner_directory / "quarantine" / str(generation)
    quarantine_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = quarantine_directory / candidate_path.name
    suffix = 1
    while target.exists():
        target = quarantine_directory / f"{candidate_path.name}.{suffix}"
        suffix += 1
    candidate_path.replace(target)
    return target


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    """Replace a durable owner document without leaving partial JSON."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid.uuid4()}.tmp")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def _journal_path(owner_directory: Path, candidate: CredentialCandidate) -> Path:
    intent_id = hashlib.sha256(
        f"{candidate.generation}:{candidate.path.absolute()}".encode("utf-8")
    ).hexdigest()[:16]
    return owner_directory / "journal" / f"generation-{candidate.generation}-{intent_id}.json"


def _atomic_copy(source: Path, target: Path) -> None:
    """Move one credential document inside the owner without exposing it."""
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.{uuid.uuid4()}.tmp")
    shutil.copy2(source, temporary)
    temporary.chmod(0o600)
    temporary.replace(target)


def _read_owner_manifest(owner_directory: Path) -> dict[str, Any]:
    try:
        manifest = json.loads((owner_directory / "owner-manifest.json").read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise CredentialPersistenceError(
            "credential owner manifest is unreadable"
        ) from error
    if not isinstance(manifest, dict) or not manifest.get("owner_id"):
        raise CredentialPersistenceError("credential owner manifest is malformed")
    return manifest


def read_codex_owner_manifest(owner_directory: Path) -> dict[str, Any]:
    """Read the redacted manifest for adapter-side lease reconstruction."""
    return _read_owner_manifest(owner_directory)


def next_codex_generation(owner_directory: Path) -> int:
    """The next durable generation, independent of attempt numbering."""
    return _committed_generation(owner_directory) + 1


def codex_candidate_provider_result(candidate_path: Path) -> CredentialProviderResult | None:
    """Read a redacted provider-result sidecar, never credential bytes."""
    try:
        value = json.loads(
            candidate_path.with_name("provider-result.json").read_text(encoding="utf-8")
        ).get("result")
    except (OSError, json.JSONDecodeError, AttributeError):
        return None
    if value == CredentialProviderResult.REVOKED.value:
        return CredentialProviderResult.REVOKED
    return None


def current_codex_source(owner_directory: Path) -> Path | None:
    """Return the current durable source, or None when no generation exists."""
    manifest = read_codex_owner_manifest(owner_directory)
    generation = _committed_generation(owner_directory)
    if generation == 0:
        return None
    if not _repair_current(owner_directory, generation, manifest):
        raise CredentialPersistenceError(
            "current credential generation is not locally valid"
        )
    return owner_directory / "current" / "auth.json"


@dataclass(frozen=True)
class CredentialOwnerRecoveryInput:
    """The redacted owner placement needing journal reconciliation."""

    owner_directory: str = ""
    operator_uid: int | None = None


@dataclass(frozen=True)
class CredentialOwnerRecoveryResult:
    """A redacted recovery outcome; no candidate bytes cross the boundary."""

    committed_generation: int | None = None
    quarantine_path: str | None = None
    refusal: str | None = None


def _committed_generation(owner_directory: Path) -> int:
    try:
        current = json.loads((owner_directory / "current.json").read_bytes())
        generation = current.get("generation")
        if isinstance(generation, int) and generation >= 1:
            return generation
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    generations = owner_directory / "generations"
    numbers = []
    if generations.is_dir():
        for path in generations.iterdir():
            try:
                numbers.append(int(path.name))
            except ValueError:
                continue
    return max(numbers, default=0)


def _write_intent(
    owner_directory: Path,
    candidate: CredentialCandidate,
    staging_path: Path | None,
) -> None:
    _atomic_json(
        _journal_path(owner_directory, candidate),
        {
            "generation": candidate.generation,
            "state": "journaled",
            "candidate_path": str(candidate.path),
            "staging_path": str(staging_path) if staging_path is not None else None,
            "provider_result": (
                candidate.provider_result.value
                if candidate.provider_result is not None
                else None
            ),
        },
    )


def _mark_intent(
    intent_path: Path,
    state: CredentialOutcome,
    *,
    quarantine_path: Path | None = None,
) -> None:
    try:
        intent = json.loads(intent_path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise CredentialPersistenceError(
            "credential owner journal is unreadable"
        ) from error
    intent["state"] = state.value
    if quarantine_path is not None:
        intent["quarantine_path"] = str(quarantine_path)
    _atomic_json(intent_path, intent)


def _claim_active_lease(
    owner_directory: Path,
    lease: CredentialLease,
    manifest: dict[str, Any],
) -> None:
    try:
        active = json.loads((owner_directory / "active-lease.json").read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise CredentialPersistenceError(
            "credential owner lease is unreadable"
        ) from error
    if (
        active.get("lease_id") != lease.lease_id
        or active.get("owner_id") != lease.owner_id
        or lease.owner_id != manifest.get("owner_id")
        or lease.host_id != manifest.get("host_id")
    ):
        raise ValueError("credential lease does not own this active use")


def _quarantine_staged_candidate(
    owner_directory: Path,
    candidate: CredentialCandidate,
    staging_path: Path,
    failure: CredentialFailure,
) -> Path:
    quarantine_directory = (
        owner_directory / "quarantine" / str(candidate.generation)
    )
    quarantine_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = quarantine_directory / staging_path.name
    suffix = 1
    while target.exists():
        target = quarantine_directory / f"{staging_path.name}.{suffix}"
        suffix += 1
    staging_path.replace(target)
    _atomic_json(
        target.with_suffix(".reason.json"),
        {
            "generation": candidate.generation,
            "failure": failure.value,
        },
    )
    return target


def _repair_current(
    owner_directory: Path,
    generation: int,
    manifest: dict[str, Any],
) -> bool:
    generation_path = owner_directory / "generations" / str(generation) / "auth.json"
    if not generation_path.is_file():
        return False
    declaration = CredentialDeclaration(
        owner_id=str(manifest["owner_id"]),
        source_path=generation_path,
        generation=generation,
    )
    if not validate_codex_credential(declaration, now=datetime.now(timezone.utc)).admitted:
        return False
    _atomic_copy(generation_path, owner_directory / "current" / "auth.json")
    _atomic_json(
        owner_directory / "current.json",
        {"owner_id": manifest["owner_id"], "generation": generation},
    )
    return True


async def finalize_codex_candidate(
    owner_directory: Path,
    candidate: CredentialCandidate,
    lease: CredentialLease,
    *,
    now: datetime,
) -> CredentialOwnerFinalization:
    """Journal, validate, and durably resolve one fenced candidate."""
    if candidate.generation < 1:
        raise ValueError("credential candidate requires a generation of at least 1")
    _validate_private_root(owner_directory, None)
    manifest = _read_owner_manifest(owner_directory)
    with exclusive_lock(owner_directory / "transaction", timeout_s=0):
        _claim_active_lease(owner_directory, lease, manifest)
        intent_path = _journal_path(owner_directory, candidate)
        replayed = intent_path.exists()
        if replayed:
            try:
                intent = json.loads(intent_path.read_bytes())
            except (OSError, json.JSONDecodeError) as error:
                raise CredentialPersistenceError(
                    "credential owner journal is unreadable"
                ) from error
            state = intent.get("state")
            if state == CredentialOutcome.COMMITTED.value:
                outcome = CredentialOutcome.COMMITTED
            elif state == CredentialOutcome.QUARANTINED.value:
                outcome = CredentialOutcome.QUARANTINED
            elif state != "journaled":
                raise CredentialPersistenceError(
                    "credential owner journal contains an unknown state"
                )
            else:
                outcome = None
        else:
            _write_intent(owner_directory, candidate, None)
            outcome = None

        if outcome is not None:
            if outcome is CredentialOutcome.COMMITTED:
                generation = intent.get("generation", candidate.generation)
                if isinstance(generation, int):
                    _repair_current(owner_directory, generation, manifest)
                return CredentialOwnerFinalization(
                    candidate=candidate,
                    outcome=outcome,
                    committed_generation=generation
                    if isinstance(generation, int)
                    else None,
                    replayed=True,
                    release_ownership=True,
                )
            quarantine_path = intent.get("quarantine_path")
            return CredentialOwnerFinalization(
                candidate=candidate,
                outcome=outcome,
                quarantine_path=Path(quarantine_path) if quarantine_path else None,
                replayed=True,
                release_ownership=True,
            )

        staging_path = owner_directory / "staging" / str(candidate.generation) / "auth.json"
        if not staging_path.is_file():
            if not candidate.path.is_file():
                source = None
            else:
                _atomic_copy(candidate.path, staging_path)
                source = staging_path
                _write_intent(owner_directory, candidate, staging_path)
        else:
            source = staging_path
            if not replayed:
                _write_intent(owner_directory, candidate, staging_path)
        if source is None:
            validation = _failure(
                CredentialMode.UNKNOWN,
                CredentialFailure.MISSING_SOURCE,
                "fenced credential candidate is missing",
            )
        else:
            declaration = CredentialDeclaration(
                owner_id=str(manifest["owner_id"]),
                source_path=source,
                generation=candidate.generation,
                provider_result=candidate.provider_result,
            )
            validation = validate_codex_credential(declaration, now=now)
        current_generation = _committed_generation(owner_directory)
        stale = candidate.generation <= current_generation
        if validation.admitted and stale:
            validation = _failure(
                CredentialMode.MANAGED_CHATGPT,
                CredentialFailure.MISSING_SOURCE,
                "fenced credential candidate is older than the committed generation",
            )
        if not validation.admitted:
            if source is None:
                quarantine_path = None
            else:
                quarantine_path = _quarantine_staged_candidate(
                    owner_directory,
                    candidate,
                    staging_path,
                    validation.failure or CredentialFailure.MALFORMED_JSON,
                )
                _mark_intent(
                    intent_path,
                    CredentialOutcome.QUARANTINED,
                    quarantine_path=quarantine_path,
                )
            return CredentialOwnerFinalization(
                candidate=candidate,
                outcome=CredentialOutcome.QUARANTINED,
                quarantine_path=quarantine_path,
                failure=validation.failure,
                release_ownership=True,
            )

        generation_path = (
            owner_directory / "generations" / str(candidate.generation) / "auth.json"
        )
        _atomic_copy(staging_path, generation_path)
        _mark_intent(intent_path, CredentialOutcome.COMMITTED)
        _atomic_json(
            owner_directory / "current.json",
            {"owner_id": manifest["owner_id"], "generation": candidate.generation},
        )
        _atomic_copy(generation_path, owner_directory / "current" / "auth.json")
        with contextlib.suppress(OSError):
            staging_path.unlink()
        return CredentialOwnerFinalization(
            candidate=candidate,
            outcome=CredentialOutcome.COMMITTED,
            committed_generation=candidate.generation,
            release_ownership=True,
        )


async def recover_codex_owner(
    owner_directory: Path,
    *,
    now: datetime,
) -> CredentialOwnerFinalization | None:
    """Repair the newest committed generation without touching the seed."""
    _validate_private_root(owner_directory, None)
    manifest = _read_owner_manifest(owner_directory)
    journal = owner_directory / "journal"
    if journal.is_dir():
        intents = sorted(journal.glob("generation-*.json"))
        for intent_path in intents:
            try:
                intent = json.loads(intent_path.read_bytes())
                generation = int(intent["generation"])
                state = intent.get("state")
            except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
            if state != "journaled" or generation < 1:
                continue
            generation_path = (
                owner_directory / "generations" / str(generation) / "auth.json"
            )
            if generation_path.is_file():
                _mark_intent(intent_path, CredentialOutcome.COMMITTED)
                continue
            quarantine_directory = owner_directory / "quarantine" / str(generation)
            quarantined = list(quarantine_directory.glob("auth.json*")) if quarantine_directory.is_dir() else []
            if quarantined:
                _mark_intent(
                    intent_path,
                    CredentialOutcome.QUARANTINED,
                    quarantine_path=quarantined[0],
                )
                continue
            try:
                active = json.loads((owner_directory / "active-lease.json").read_bytes())
                lease = CredentialLease(
                    owner_id=str(manifest["owner_id"]),
                    host_id=str(manifest["host_id"]),
                    lease_id=str(active["lease_id"]),
                )
                provider_value = intent.get("provider_result")
                provider_result = (
                    CredentialProviderResult(provider_value)
                    if provider_value is not None
                    else None
                )
                candidate = CredentialCandidate(
                    path=Path(intent["candidate_path"]),
                    generation=generation,
                    provider_result=provider_result,
                )
            except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
            with contextlib.suppress(
                CredentialOwnerBusy,
                CredentialPersistenceError,
                ValueError,
                OSError,
            ):
                await finalize_codex_candidate(
                    owner_directory, candidate, lease, now=now
                )
    generations = owner_directory / "generations"
    candidates: list[int] = []
    if generations.is_dir():
        for path in generations.iterdir():
            try:
                generation = int(path.name)
            except ValueError:
                continue
            if generation > 0:
                candidates.append(generation)
    for generation in sorted(candidates, reverse=True):
        if _repair_current(owner_directory, generation, manifest):
            return CredentialOwnerFinalization(
                candidate=CredentialCandidate(
                    path=owner_directory / "current" / "auth.json",
                    generation=generation,
                ),
                outcome=CredentialOutcome.COMMITTED,
                committed_generation=generation,
                release_ownership=False,
            )
    return None


@dataclass(frozen=True)
class CredentialBusy:
    """BUSY as data: workflow time, not a blocking activity wait."""

    retry_after_s: float = 1.0


@dataclass(frozen=True)
class CredentialOwnerAdmissionInput:
    """The redacted declaration and host placement needed to resolve one owner."""

    epic_id: str
    node_id: str
    target_repo: str
    deployment_shape: str
    owner_id: str
    source_path: str
    generation: int = 1
    host_id: str = ""
    operator_state_root: str = ""
    operator_uid: int | None = None


@dataclass(frozen=True)
class CredentialOwnerAdmissionResult:
    """BUSY as data; a lease only when admission was granted."""

    lease: CredentialLease | None = None
    busy: CredentialBusy | None = None
    refusal: str | None = None
    owner_directory: str | None = None
    operator_uid: int | None = None


@dataclass(frozen=True)
class CodexOwnerDeclaration:
    """The operator-declared owner placement pinned at epic start."""

    owner_id: str
    source_path: str
    host_id: str
    operator_state_root: str
    operator_uid: int
    generation: int = 1


@dataclass(frozen=True)
class GatewayProgressInput:
    """The redacted identity of one gateway attempt that may keep running."""

    epic_id: str
    node_id: str
    attempt: int
    route: str = "gateway"


@dataclass(frozen=True)
class MixedGatewayInput:
    """One subscription admission and one unrelated gateway attempt."""

    owner: CredentialOwnerAdmissionInput
    gateway: GatewayProgressInput


@dataclass
class CredentialOwnerBusy(Exception):
    """The short owner transaction found another active use."""

    retry_after_s: float = 1.0


def _prepare_private_owner_root(root: Path, operator_uid: int | None) -> None:
    if root.exists() and root.is_symlink():
        raise ValueError("credential owner root must not be a symlink")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    _validate_private_root(root, operator_uid)


async def _invoke_reap(
    reap: Callable[[object], Awaitable[None] | None], pid_file: object
) -> None:
    """Run one reap/fence callback and preserve its named fence refusal."""
    result = reap(pid_file)
    if result is not None:
        await result


async def _invoke_termination(
    operation: Callable[[], Awaitable[None] | None],
) -> None:
    """Await either an async or an immediate termination/proof step."""
    result = operation()
    if result is not None:
        await result


def _validate_private_root(root: Path, operator_uid: int | None) -> None:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("credential owner root must be a private directory")
    mode = stat.S_IMODE(root.stat().st_mode)
    if mode != 0o700:
        raise ValueError("credential owner root must have 0700 permissions")
    if operator_uid is not None and root.stat().st_uid != operator_uid:
        raise ValueError("credential owner root must be owned by the declared operator identity")


def _validate_admission_request(
    request: CredentialOwnerAdmissionInput,
) -> CredentialDeclaration:
    """Refuse an incomplete owner declaration before touching the filesystem."""
    if request.host_id.strip() == "":
        raise ValueError("credential owner admission requires a host id")
    if request.operator_state_root.strip() == "":
        raise ValueError("credential owner admission requires an operator state root")
    if request.source_path.strip() == "":
        raise ValueError("credential owner admission requires a credential source path")
    if request.operator_uid is None:
        raise ValueError("credential owner admission requires an operator uid")
    if request.generation < 1:
        raise ValueError("credential owner admission requires a generation of at least 1")
    root = Path(request.operator_state_root)
    source = Path(request.source_path)
    if not root.is_absolute() or not source.is_absolute():
        raise ValueError(
            "credential owner admission requires absolute declared paths"
        )
    return CredentialDeclaration(
        owner_id=request.owner_id,
        source_path=source,
        generation=request.generation,
    )


@activity.defn(name="admit_codex_owner")
async def admit_codex_owner(
    request: CredentialOwnerAdmissionInput,
) -> CredentialOwnerAdmissionResult:
    """Resolve and try one declared owner in a short activity transaction."""
    try:
        declaration = _validate_admission_request(request)
    except ValueError as error:
        return CredentialOwnerAdmissionResult(refusal=str(error))
    roots = CredentialOwnerRoots(
        root=Path(request.operator_state_root),
        host_id=request.host_id,
        operator_uid=request.operator_uid,
    )
    declaration = CredentialDeclaration(
        owner_id=request.owner_id,
        source_path=Path(request.source_path),
        generation=request.generation,
    )
    owner = roots.owner_directory(
        declaration,
        epic_id=request.epic_id,
        target_repo=request.target_repo,
        deployment_shape=request.deployment_shape,
    )
    try:
        lease = await roots.admit(owner, declaration)
        return CredentialOwnerAdmissionResult(
            lease=lease,
            owner_directory=str(owner),
            operator_uid=request.operator_uid,
        )
    except CredentialOwnerBusy as busy:
        return CredentialOwnerAdmissionResult(busy=CredentialBusy(busy.retry_after_s))
    except ValueError as error:
        return CredentialOwnerAdmissionResult(refusal=str(error))


@activity.defn(name="release_codex_owner")
async def release_codex_owner(
    request: CredentialOwnerAdmissionResult,
) -> None:
    """Release the durable active-use marker returned by admission."""
    if request.lease is None or request.owner_directory is None:
        return
    owner = Path(request.owner_directory)
    await CredentialOwnerRoots(
        root=owner.parent.parent,
        host_id=request.lease.host_id,
        operator_uid=request.operator_uid,
    ).release(request.lease, owner_directory=owner)


@activity.defn(name="recover_codex_owner")
async def recover_codex_owner_activity(
    request: CredentialOwnerRecoveryInput,
) -> CredentialOwnerRecoveryResult:
    """Reconcile interrupted journal work before the attempt is charged."""
    owner_directory = Path(request.owner_directory)
    try:
        _validate_private_root(owner_directory, request.operator_uid)
        outcome = await recover_codex_owner(
            owner_directory,
            now=datetime.now(timezone.utc),
        )
    except (CredentialPersistenceError, ValueError, OSError) as error:
        return CredentialOwnerRecoveryResult(refusal=str(error))
    if outcome is None:
        return CredentialOwnerRecoveryResult()
    return CredentialOwnerRecoveryResult(
        committed_generation=outcome.committed_generation,
        quarantine_path=(
            str(outcome.quarantine_path)
            if outcome.quarantine_path is not None
            else None
        ),
    )


@activity.defn(name="gateway_credential_tick")
async def gateway_credential_tick(request: GatewayProgressInput) -> str:
    """Return the ordinary gateway attempt identity without a credential value."""
    return f"{request.epic_id}:{request.node_id}:{request.attempt}:{request.route}"


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


@workflow.defn
class CredentialAdmissionWorkflow:
    """Wait in workflow time for BUSY; never hold an activity open to wait."""

    @workflow.run
    async def run(
        self, request: CredentialOwnerAdmissionInput
    ) -> CredentialOwnerAdmissionResult:
        while True:
            result = await workflow.execute_activity(
                admit_codex_owner,
                request,
                start_to_close_timeout=timedelta(seconds=10),
            )
            if result.lease is not None or result.refusal is not None:
                return result
            await workflow.sleep(timedelta(seconds=result.busy.retry_after_s))


@workflow.defn
class MixedGatewayWorkflow:
    """Progress unrelated gateway work while admission repeats in workflow time."""

    @workflow.run
    async def run(self, request: MixedGatewayInput) -> int:
        admission = await workflow.execute_activity(
            admit_codex_owner,
            request.owner,
            start_to_close_timeout=timedelta(seconds=10),
        )
        if admission.busy is not None:
            gateway_ticks: list[str] = []
            for _ in range(3):
                gateway_ticks.append(
                    await workflow.execute_activity(
                        gateway_credential_tick,
                        request.gateway,
                        start_to_close_timeout=timedelta(seconds=1),
                    )
                )
            return len(gateway_ticks)
        gateway_ticks = []
        while True:
            gateway_ticks.append(
                await workflow.execute_activity(
                    gateway_credential_tick,
                    request.gateway,
                    start_to_close_timeout=timedelta(seconds=1),
                )
            )
            result = await workflow.execute_activity(
                admit_codex_owner,
                request.owner,
                start_to_close_timeout=timedelta(seconds=10),
            )
            if result.lease is not None:
                return len(gateway_ticks)
            if result.refusal is not None:
                raise ApplicationError(result.refusal, type="CREDENTIAL_OWNER_REFUSED")
            await workflow.sleep(timedelta(seconds=result.busy.retry_after_s))
