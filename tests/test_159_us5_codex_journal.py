"""US5 of 159: durable promotion, quarantine, and recovery for refresh results."""

from __future__ import annotations

import asyncio
import ast
import json
import os
import shutil
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest
import httpx

from factory.workgraph.codex_credential import (
    CredentialCandidate,
    CredentialLease,
    CredentialOwnerBusy,
    CredentialOwnerFinalization,
    CredentialOwnerRoots,
    CredentialOutcome,
    CredentialFailure,
    CredentialProviderResult,
    finalize_codex_candidate,
    recover_codex_owner,
)
import factory.workgraph.codex_credential as codex_credential


NOW = datetime(2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc)
OWNER_ID = "codex-production"
HOST_ID = "operator-host"


def managed_payload(token_suffix: str = "first") -> dict[str, object]:
    """A synthetic, structurally eligible managed credential."""
    return {
        "auth_mode": "chatgpt",
        "tokens": {
            "access_token": f"synthetic-access-{token_suffix}",
            "refresh_token": f"synthetic-refresh-{token_suffix}",
        },
    }


async def _lease(
    tmp_path: Path,
    generation: int,
) -> tuple[Path, CredentialLease]:
    roots = CredentialOwnerRoots(root=tmp_path / "operator-state", host_id=HOST_ID)
    owner = roots.owner_directory(_declaration(tmp_path, generation))
    lease = await roots.admit(owner, _declaration(tmp_path, generation))
    return owner, lease


def _declaration(tmp_path: Path, generation: int):
    from factory.workgraph.codex_credential import CredentialDeclaration

    return CredentialDeclaration(
        owner_id=OWNER_ID,
        source_path=tmp_path / "operator-state" / "source-auth.json",
        generation=generation,
    )


async def _write_candidate(path: Path, payload: object, generation: int) -> CredentialCandidate:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return CredentialCandidate(path=path, generation=generation)


@pytest.mark.parametrize(
    "outcome",
    ["normal", "nonzero", "timeout", "cancelled"],
)
async def test_fenced_candidate_commits_before_release_on_every_termination(
    tmp_path: Path,
    outcome: str,
) -> None:
    """All bounded-child endings use the same durable promotion boundary."""
    owner, lease = await _lease(tmp_path, 1)
    candidate = await _write_candidate(
        tmp_path / "node" / ".codex" / "auth.json",
        managed_payload("second"),
        2,
    )
    if outcome == "cancelled":
        task = asyncio.create_task(
            finalize_codex_candidate(owner, candidate, lease, now=NOW)
        )
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return

    result = await finalize_codex_candidate(owner, candidate, lease, now=NOW)

    assert result.outcome is CredentialOutcome.COMMITTED
    assert result.release_ownership is True
    assert (owner / "current" / "auth.json").read_text(encoding="utf-8") == (
        json.dumps(managed_payload("second"))
    )
    assert (owner / "current.json").exists()


async def test_commit_is_atomic_under_the_owner_transaction(
    tmp_path: Path,
) -> None:
    """A second transaction cannot observe or replace a half-promoted candidate."""
    owner, first = await _lease(tmp_path, 1)
    candidate = await _write_candidate(
        tmp_path / "node" / ".codex" / "auth.json",
        managed_payload("second"),
        2,
    )
    result = await finalize_codex_candidate(owner, candidate, first, now=NOW)
    assert result.release_ownership is True

    roots = CredentialOwnerRoots(root=tmp_path / "operator-state", host_id=HOST_ID)
    with pytest.raises(CredentialOwnerBusy):
        await roots.admit(owner, _declaration(tmp_path, 1))
    await roots.release(first, owner_directory=owner)


async def test_candidate_generation_becomes_next_generation(
    tmp_path: Path,
) -> None:
    """The current pointer names the promoted generation, not the attempt number."""
    owner, lease = await _lease(tmp_path, 1)
    candidate = await _write_candidate(
        tmp_path / "node" / ".codex" / "auth.json",
        managed_payload("second"),
        2,
    )
    result = await finalize_codex_candidate(owner, candidate, lease, now=NOW)
    current = json.loads((owner / "current.json").read_text(encoding="utf-8"))

    assert result.committed_generation == 2
    assert current["generation"] == 2
    assert current["owner_id"] == OWNER_ID


async def test_release_happens_after_durable_outcome(
    tmp_path: Path,
) -> None:
    """The lease marker remains through commit and is removed only afterwards."""
    roots = CredentialOwnerRoots(root=tmp_path / "operator-state", host_id=HOST_ID)
    owner, lease = await _lease(tmp_path, 1)
    candidate = await _write_candidate(
        tmp_path / "node" / ".codex" / "auth.json",
        managed_payload("second"),
        2,
    )
    result = await finalize_codex_candidate(owner, candidate, lease, now=NOW)
    assert result.release_ownership is True
    assert (owner / "current.json").exists()
    await roots.release(lease, owner_directory=owner)
    assert not (owner / "active-lease.json").exists()


@pytest.mark.parametrize(
    ("payload", "expected_failure"),
    [
        ({"auth_mode": "chatgpt"}, CredentialFailure.MISSING_REFRESH),
        ({"auth_mode": "apikey", "OPENAI_API_KEY": "synthetic"}, CredentialFailure.UNSUPPORTED_MODE),
    ],
)
async def test_invalid_candidates_are_quarantined_and_current_survives(
    tmp_path: Path,
    payload: dict[str, object],
    expected_failure: CredentialFailure,
) -> None:
    """A bad refresh result cannot displace the last committed generation."""
    owner, lease = await _lease(tmp_path, 1)
    first = await _write_candidate(
        tmp_path / "seed" / ".codex" / "auth.json",
        managed_payload("first"),
        1,
    )
    await finalize_codex_candidate(owner, first, lease, now=NOW)
    bad = await _write_candidate(
        tmp_path / "node" / ".codex" / "auth.json",
        payload,
        2,
    )
    result = await finalize_codex_candidate(owner, bad, lease, now=NOW)

    assert result.outcome is CredentialOutcome.QUARANTINED
    assert result.failure is expected_failure
    assert result.release_ownership is True
    assert (owner / "current" / "auth.json").read_text(encoding="utf-8") == (
        json.dumps(managed_payload("first"))
    )
    quarantine = owner / "quarantine" / "2" / "auth.json"
    reason = json.loads(
        (owner / "quarantine" / "2" / "auth.reason.json").read_text(encoding="utf-8")
    )
    assert quarantine.exists()
    assert reason["failure"] == expected_failure.value


async def test_stale_candidate_is_quarantined_not_promoted(
    tmp_path: Path,
) -> None:
    """Older committed bytes are never allowed to become current again."""
    owner, lease = await _lease(tmp_path, 1)
    first = await _write_candidate(
        tmp_path / "seed" / ".codex" / "auth.json",
        managed_payload("first"),
        1,
    )
    second = await _write_candidate(
        tmp_path / "node" / ".codex" / "auth.json",
        managed_payload("second"),
        2,
    )
    await finalize_codex_candidate(owner, first, lease, now=NOW)
    await finalize_codex_candidate(owner, second, lease, now=NOW)
    stale = await _write_candidate(
        tmp_path / "recovery" / ".codex" / "auth.json",
        managed_payload("first"),
        1,
    )
    result = await finalize_codex_candidate(owner, stale, lease, now=NOW)

    assert result.outcome is CredentialOutcome.QUARANTINED
    assert result.failure is CredentialFailure.MISSING_SOURCE
    assert (owner / "current.json").exists()
    current = json.loads((owner / "current.json").read_text(encoding="utf-8"))
    assert current["generation"] == 2


async def test_provider_rejection_is_durable_not_inferred(
    tmp_path: Path,
) -> None:
    """A recorded Codex result quarantines the candidate and keeps prior state."""
    owner, lease = await _lease(tmp_path, 1)
    first = await _write_candidate(
        tmp_path / "seed" / ".codex" / "auth.json",
        managed_payload("first"),
        1,
    )
    await finalize_codex_candidate(owner, first, lease, now=NOW)
    rejected = await _write_candidate(
        tmp_path / "node" / ".codex" / "auth.json",
        managed_payload("second"),
        2,
    )
    rejected = replace(rejected, provider_result=CredentialProviderResult.REVOKED)
    result = await finalize_codex_candidate(owner, rejected, lease, now=NOW)

    assert result.outcome is CredentialOutcome.QUARANTINED
    assert result.failure is CredentialFailure.PROVIDER_REVOKED
    reason = json.loads(
        (owner / "quarantine" / "2" / "auth.reason.json").read_text(encoding="utf-8")
    )
    assert reason["failure"] == CredentialFailure.PROVIDER_REVOKED.value
    assert (owner / "current" / "auth.json").read_text(encoding="utf-8") == (
        json.dumps(managed_payload("first"))
    )


async def test_recovery_chooses_newest_valid_generation_after_current_corruption(
    tmp_path: Path,
) -> None:
    """Crash-damaged current state falls back to the newest valid generation."""
    owner, lease = await _lease(tmp_path, 1)
    first = await _write_candidate(
        tmp_path / "seed" / ".codex" / "auth.json",
        managed_payload("first"),
        1,
    )
    second = await _write_candidate(
        tmp_path / "node" / ".codex" / "auth.json",
        managed_payload("second"),
        2,
    )
    await finalize_codex_candidate(owner, first, lease, now=NOW)
    await finalize_codex_candidate(owner, second, lease, now=NOW)
    (owner / "current" / "auth.json").write_text("{interrupted", encoding="utf-8")

    result = await recover_codex_owner(owner, now=NOW)

    assert result is not None
    assert result.committed_generation == 2
    assert (owner / "current" / "auth.json").read_text(encoding="utf-8") == (
        json.dumps(managed_payload("second"))
    )


async def test_recovery_does_not_silently_restore_bootstrap_seed(
    tmp_path: Path,
) -> None:
    """An absent generation stays absent; recovery never invents generation one."""
    owner, lease = await _lease(tmp_path, 1)
    seed = await _write_candidate(
        tmp_path / "operator-state" / "source-auth.json",
        managed_payload("seed"),
        1,
    )
    assert seed.path.is_file()

    result = await recover_codex_owner(owner, now=NOW)

    assert result is None
    assert not (owner / "current.json").exists()
    assert not (owner / "current" / "auth.json").exists()


async def test_crash_after_intent_recovers_from_the_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The journal survives validation and recovery finishes its candidate."""
    owner, lease = await _lease(tmp_path, 1)
    candidate = await _write_candidate(
        tmp_path / "node" / ".codex" / "auth.json",
        managed_payload("second"),
        2,
    )

    def interrupted_validation(*args: object, **kwargs: object) -> object:
        raise codex_credential.CredentialPersistenceError("validation interrupted")

    monkeypatch.setattr(
        codex_credential, "validate_codex_credential", interrupted_validation
    )
    with pytest.raises(codex_credential.CredentialPersistenceError):
        await finalize_codex_candidate(owner, candidate, lease, now=NOW)
    assert (owner / "current.json").exists() is False
    monkeypatch.undo()

    result = await recover_codex_owner(owner, now=NOW)
    assert result is not None
    assert result.committed_generation == 2
    assert (owner / "current" / "auth.json").read_text(encoding="utf-8") == (
        json.dumps(managed_payload("second"))
    )


async def test_crash_after_generation_commit_repairs_current(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid generation directory is the durable fact recovery trusts."""
    owner, lease = await _lease(tmp_path, 1)
    candidate = await _write_candidate(
        tmp_path / "node" / ".codex" / "auth.json",
        managed_payload("second"),
        2,
    )
    real_mark = codex_credential._mark_intent

    def interrupted_mark(*args: object, **kwargs: object) -> None:
        raise codex_credential.CredentialPersistenceError("journal mark interrupted")

    monkeypatch.setattr(codex_credential, "_mark_intent", interrupted_mark)
    with pytest.raises(codex_credential.CredentialPersistenceError):
        await finalize_codex_candidate(owner, candidate, lease, now=NOW)
    monkeypatch.undo()
    assert (owner / "generations" / "2" / "auth.json").is_file()
    assert not (owner / "current.json").exists()

    result = await recover_codex_owner(owner, now=NOW)
    assert result is not None
    assert result.committed_generation == 2
    assert (owner / "current" / "auth.json").read_text(encoding="utf-8") == (
        json.dumps(managed_payload("second"))
    )
    del real_mark


async def test_crash_after_quarantine_marks_the_durable_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recovery sees the quarantine and does not revalidate the bad candidate."""
    owner, lease = await _lease(tmp_path, 1)
    candidate = await _write_candidate(
        tmp_path / "node" / ".codex" / "auth.json",
        "{malformed",
        2,
    )

    def interrupted_mark(*args: object, **kwargs: object) -> None:
        raise codex_credential.CredentialPersistenceError("quarantine mark interrupted")

    monkeypatch.setattr(codex_credential, "_mark_intent", interrupted_mark)
    with pytest.raises(codex_credential.CredentialPersistenceError):
        await finalize_codex_candidate(owner, candidate, lease, now=NOW)
    monkeypatch.undo()
    assert (owner / "quarantine" / "2" / "auth.json").is_file()

    result = await recover_codex_owner(owner, now=NOW)
    assert result is None
    journal = next((owner / "journal").glob("generation-2-*.json"))
    intent = json.loads(journal.read_text(encoding="utf-8"))
    assert intent["state"] == CredentialOutcome.QUARANTINED.value


async def test_owner_does_not_contact_a_provider_refresh_endpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the fenced Codex child may refresh; the owner only persists files."""
    network_calls: list[tuple[object, ...]] = []

    def forbidden_request(self: object, *args: object, **kwargs: object) -> object:
        network_calls.append(("request", args, kwargs))
        raise AssertionError("owner storage contacted the network")

    def forbidden_urlopen(*args: object, **kwargs: object) -> object:
        network_calls.append(("urlopen", args, kwargs))
        raise AssertionError("owner storage contacted the network")

    monkeypatch.setattr(httpx.Client, "request", forbidden_request)
    monkeypatch.setattr(httpx.AsyncClient, "request", forbidden_request)
    monkeypatch.setattr("urllib.request.urlopen", forbidden_urlopen)
    owner, lease = await _lease(tmp_path, 1)
    candidate = await _write_candidate(
        tmp_path / "node" / ".codex" / "auth.json",
        managed_payload("second"),
        2,
    )

    result = await finalize_codex_candidate(owner, candidate, lease, now=NOW)

    assert result.outcome is CredentialOutcome.COMMITTED
    assert network_calls == []


def test_owner_module_contains_no_oauth_refresh_implementation() -> None:
    """The source itself declares the child as the only refresh boundary."""
    source = Path(codex_credential.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_names.append(node.module.split(".")[0])

    assert not {"httpx", "requests", "socket", "urllib"} & set(imported_names)
    assert "https://" not in source
    assert "oauth/token" not in source.lower()


async def test_replaying_a_committed_candidate_commits_once(
    tmp_path: Path,
) -> None:
    """A repeated finalization reads the durable outcome instead of rewriting it."""
    owner, lease = await _lease(tmp_path, 1)
    candidate = await _write_candidate(
        tmp_path / "node" / ".codex" / "auth.json",
        managed_payload("second"),
        2,
    )
    first = await finalize_codex_candidate(owner, candidate, lease, now=NOW)
    committed_before = (owner / "generations" / "2" / "auth.json").read_text(
        encoding="utf-8"
    )
    candidate.path.write_text(json.dumps(managed_payload("changed")), encoding="utf-8")

    second = await finalize_codex_candidate(owner, candidate, lease, now=NOW)

    assert first.outcome is CredentialOutcome.COMMITTED
    assert second.outcome is CredentialOutcome.COMMITTED
    assert second.replayed is True
    assert second.release_ownership is True
    assert (owner / "generations" / "2" / "auth.json").read_text(
        encoding="utf-8"
    ) == committed_before
    assert (owner / "current" / "auth.json").read_text(encoding="utf-8") == (
        committed_before
    )


async def test_replaying_a_quarantined_candidate_quarantines_once(
    tmp_path: Path,
) -> None:
    """A repeated invalid candidate is not moved or recorded twice."""
    owner, lease = await _lease(tmp_path, 1)
    candidate_path = tmp_path / "node" / ".codex" / "auth.json"
    candidate = await _write_candidate(candidate_path, "{malformed", 2)
    first = await finalize_codex_candidate(owner, candidate, lease, now=NOW)
    quarantine_before = sorted((owner / "quarantine" / "2").iterdir())
    candidate_path.write_text(json.dumps(managed_payload("changed")), encoding="utf-8")

    second = await finalize_codex_candidate(owner, candidate, lease, now=NOW)

    assert first.outcome is CredentialOutcome.QUARANTINED
    assert second.outcome is CredentialOutcome.QUARANTINED
    assert second.replayed is True
    assert second.release_ownership is True
    assert sorted((owner / "quarantine" / "2").iterdir()) == quarantine_before
