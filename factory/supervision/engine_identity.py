"""Engine identity vocabulary: version, image reference, and on-disk record.

This module is intentionally standard-library-only: the host CLI imports it on
the `build start` path, and heavier dependencies must not slow or complicate
that import.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from factory.registry import resolve_state_home

#: The filename of the engine identity record inside the supervision home.
IDENTITY_FILENAME = "engine-identity.json"

#: The image repository that CI pushes to and the compose reference consumes.
#: Pinned by US3 tests against `container/compose.reference.yaml:10`.
IMAGE_REPOSITORY = "ghcr.io/bryantharpeorg/ergane"


@dataclass(frozen=True)
class EngineIdentity:
    """What the running engine advertises about itself."""

    version: str
    started_at: str
    image_reference: str | None
    image_digest: str | None


def cli_version() -> str:
    """Single answer to "what version is this CLI".

    Falls back to ``"unknown"`` when the distribution is not installed, which
    keeps the banner and the handshake from raising.
    """
    try:
        from importlib.metadata import version

        return version("ergane-cli")
    except Exception:
        return "unknown"


def image_reference(version: str) -> str:
    """Fully-qualified image reference for a pinned CLI version."""
    return f"{IMAGE_REPOSITORY}:{version}"


def engine_skew(identity: EngineIdentity | None, cli: str) -> str | None:
    """Refusal sentence when the running engine's version differs from the CLI.

    Returns ``None`` when the versions match or when no identity file was found,
    preserving today's "check activates only on evidence" behaviour for native
    engines and pre-105 containers.

    The sentence names both versions, the two remedies (`ergane engine upgrade`
    and `docker pull <repo>:<cli>`), and the absolute path of the identity record
    so an operator whose engine is gone can clear a stale record that a killed
    container never removed.
    """
    if identity is None:
        return None
    if identity.version == cli:
        return None
    path = identity_path(resolve_state_home()).resolve()
    return (
        f"engine is running ergane {identity.version}; this CLI is {cli} — they must match. "
        f"Upgrade with `ergane engine upgrade`, or pull the pinned image directly: "
        f"docker pull {image_reference(cli)}. "
        f"If that engine is gone, this record is stale — remove {path}."
    )


def identity_path(state_home: str | Path) -> Path:
    """Absolute path to the identity record under a state home.

    This performs the same join as ``supervision_home()`` so the host and the
    container converge on one path, but it takes the resolved state home as an
    argument rather than re-resolving from environment variables.  Inside the
    supervisor, ``state_home`` comes from the injected ``config``; on the host,
    callers pass ``resolve_state_home()``.
    """
    return Path(state_home) / "ergane" / "supervision" / IDENTITY_FILENAME


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_identity(state_home: str | Path, identity: EngineIdentity) -> Path:
    """Write the identity record atomically: temp file, then rename.

    Atomic rename means a restart replaces the file whole and a concurrent
    reader never sees a partial JSON document.
    """
    path = identity_path(state_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    document: dict[str, Any] = {
        "version": identity.version,
        "started_at": identity.started_at,
        "image_reference": identity.image_reference,
        "image_digest": identity.image_digest,
    }
    with tempfile.NamedTemporaryFile(
        mode="w",
        prefix=f".{IDENTITY_FILENAME}.",
        suffix=".tmp",
        dir=str(path.parent),
        delete=False,
    ) as tmp:
        tmp.write(json.dumps(document, indent=2))
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)
    return path


def read_identity(state_home: str | Path) -> EngineIdentity | None:
    """Read and parse the identity record, or return None when absent/unparseable."""
    path = identity_path(state_home)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    try:
        return EngineIdentity(
            version=document["version"],
            started_at=document["started_at"],
            image_reference=document.get("image_reference"),
            image_digest=document.get("image_digest"),
        )
    except Exception:
        return None


def remove_identity(state_home: str | Path) -> None:
    """Best-effort removal of the identity record.

    A missing file is not an error; no exception escapes.  This is the second
    half of the lifetime contract: an engine that has stopped advertises
    nothing.
    """
    try:
        identity_path(state_home).unlink(missing_ok=True)
    except Exception:
        pass
