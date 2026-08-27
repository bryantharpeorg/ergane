"""Every volume mount point in a compose project must exist in the image.

Docker seeds a fresh named volume from whatever the image holds at the mount
path, ownership included. When the path is ABSENT from the image it creates the
mount point root-owned instead — and the engine container runs as uid 1000. All
four demo volumes landed root-owned for that reason, and the engine died on its
first write:

    PermissionError: [Errno 13] Permission denied:
      '/home/ergane/.local/state/ergane/temporal'

Nothing else connects the Dockerfile to the compose file, and the failure is
cold-volume-only: once a volume exists with usable ownership it keeps it, so a
second `up` succeeds and the defect goes quiet. Every stranger boots cold.

Found 2026-08-26 by running the demo stack, as the fourth of four defects in one
rehearsal — each hidden behind the one before it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "Dockerfile"
DEMO_COMPOSE = REPO_ROOT / "container" / "compose.demo.yaml"

CONTAINER_UID = "1000"


ENGINE_SERVICE = "ergane"


def _demo_volume_mount_points() -> set[str]:
    """Container-side paths where compose.demo.yaml mounts a NAMED volume.

    Scoped to the `ergane` service on purpose. The gateway and postgres services
    run third-party images this Dockerfile does not build, and their mount points
    (`/app/config`, `/var/lib/postgresql/data`) are seeded by those images — a
    first draft of this test checked them too and failed on the engine's own
    Dockerfile for directories that were never its to create.

    Bind mounts are excluded: their ownership comes from the host, not an image.
    """
    document = yaml.safe_load(DEMO_COMPOSE.read_text(encoding="utf-8"))
    declared = set(document.get("volumes") or {})
    service = (document.get("services") or {}).get(ENGINE_SERVICE) or {}
    mount_points: set[str] = set()
    for entry in service.get("volumes") or []:
        if not isinstance(entry, str) or ":" not in entry:
            continue
        source, target = entry.split(":")[:2]
        if source in declared:
            mount_points.add(target)
    return mount_points


def _paths_created_for_the_container_user() -> set[str]:
    """Absolute paths the Dockerfile creates owned by the container uid.

    Reads `install -d ... -o 1000 ...` invocations, including line-continued
    ones, which is how the image declares a directory AND its ownership in a
    single step.
    """
    text = DOCKERFILE.read_text(encoding="utf-8")
    joined = re.sub(r"\\\s*\n\s*", " ", text)
    created: set[str] = set()
    for line in joined.splitlines():
        stripped = line.strip()
        if not stripped.startswith("RUN "):
            continue
        if "install -d" not in stripped or f"-o {CONTAINER_UID}" not in stripped:
            continue
        created.update(re.findall(r"(/[^\s]+)", stripped))
    return created


def test_the_demo_declares_volume_mount_points_at_all() -> None:
    """Guard the parser: an empty set would make the real assertion vacuous."""
    mount_points = _demo_volume_mount_points()
    assert mount_points, "parsed no named-volume mount points out of compose.demo.yaml"
    assert "/home/ergane/.local/state/ergane" in mount_points


def test_the_dockerfile_creates_directories_owned_by_the_container_user() -> None:
    """Guard the other parser for the same reason."""
    created = _paths_created_for_the_container_user()
    assert created, "parsed no `install -d -o 1000` paths out of the Dockerfile"


@pytest.mark.parametrize("mount_point", sorted(_demo_volume_mount_points()))
def test_every_demo_volume_mount_point_exists_in_the_image(mount_point: str) -> None:
    """Absent from the image means root-owned at runtime, which means EACCES."""
    created = _paths_created_for_the_container_user()
    assert mount_point in created, (
        f"compose.demo.yaml mounts a named volume at {mount_point!r}, but the Dockerfile "
        f"never creates it owned by uid {CONTAINER_UID}. Docker will create the mount "
        f"point root-owned and the engine, running as {CONTAINER_UID}, cannot write to it."
    )
