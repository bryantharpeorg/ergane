"""US2: one declared Codex credential has one host-global owner."""

from __future__ import annotations

import stat
import os
from pathlib import Path

import pytest

from factory.workgraph.codex_credential import (
    CredentialDeclaration,
    CredentialOwnerKey,
    CredentialOwnerRoots,
)


HOST = "operator-host"
OWNER_ID = "codex-production"
OPERATOR_UID = os.getuid()


def declaration(root: Path, generation: int = 1) -> CredentialDeclaration:
    return CredentialDeclaration(
        owner_id=OWNER_ID,
        source_path=root / "source-auth.json",
        generation=generation,
    )


async def test_two_epics_targets_and_shapes_resolve_one_host_owner(
    tmp_path: Path,
) -> None:
    """Different runtime callers collapse to the declared host owner path."""
    operator_root = tmp_path / "operator-state"
    targets = ["sample-a", "sample-b"]
    roots = CredentialOwnerRoots(root=operator_root, host_id=HOST)

    resolved = [
        roots.owner_directory(
            declaration(operator_root),
            epic_id=epic,
            target_repo=target,
            deployment_shape=shape,
        )
        for epic, target, shape in [
            ("epic-a", targets[0], "bwrap"),
            ("epic-b", targets[1], "host"),
        ]
    ]

    assert len({path.resolve() for path in resolved}) == 1
    owner = resolved[0]
    assert owner.parent == operator_root / HOST
    assert owner.name == OWNER_ID


async def test_owner_admission_admits_exactly_one_concurrent_waiter(
    tmp_path: Path,
) -> None:
    """A short owner transaction returns one lease and BUSY to the other."""
    operator_root = tmp_path / "operator-state"
    roots = CredentialOwnerRoots(
        root=operator_root, host_id=HOST, operator_uid=OPERATOR_UID
    )
    first = roots.owner_directory(declaration(operator_root))
    second = roots.owner_directory(declaration(operator_root))
    source = declaration(operator_root)
    lease, busy = await roots.admit_concurrently(first, second, source)

    assert lease is not None
    assert lease.owner_id == OWNER_ID
    assert busy is not None
    assert busy.retry_after_s > 0
    assert stat.S_IMODE(operator_root.stat().st_mode) == 0o700
