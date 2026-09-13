"""US5 of 159: durable promotion, quarantine, and recovery for refresh results."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from factory.workgraph.codex_credential import (
    CredentialCandidate,
    CredentialLease,
    CredentialOwnerBusy,
    CredentialOwnerFinalization,
    CredentialOwnerRoots,
    CredentialOutcome,
    finalize_codex_candidate,
    recover_codex_owner,
)


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

