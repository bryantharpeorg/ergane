"""105-US4: `ergane engine upgrade` — drain, replace, verify through, reclaim old images.

All docker interaction is behind one injectable seam.  The default runner uses
`docker compose` against the generated project directory; tests pass a fake.
"""

from __future__ import annotations

import dataclasses
import os
import subprocess
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence

from factory.cli.errors import EXIT_USER, OperatorError
from factory.controlplane.verify import verify_controlplane
from factory.mergequeue.models import Finding
from factory.registry import resolve_state_home
from factory.supervision.container_manifest import retarget_project
from factory.supervision.engine_identity import (
    IMAGE_REPOSITORY,
    cli_version,
    image_reference,
    read_identity,
)
from factory.supervision.units import CommandResult, supervision_home
from factory.versioning import OpenEpic


#: Directory name under the supervision home where `ergane install` (spec 104)
#: writes the engine container project.  Ruling R1 in 104's plan.
CONTAINER_PROJECT_DIRNAME = "container"

#: The compose file the project is required to contain.
COMPOSE_NAME = "compose.yaml"


class DockerSeam(Protocol):
    """One injectable seam for every docker interaction (FR-020)."""

    def stop(self) -> None: ...
    def start(self, image_reference: str, *, env: dict[str, str] | None = None) -> None: ...
    def verify(self) -> tuple[list[Finding], int]: ...
    def list_images(self) -> list[str]: ...
    def remove_image(self, ref: str) -> None: ...


@dataclasses.dataclass(frozen=True)
class UpgradeReport:
    """What the upgrade did, and whether the new engine is degraded."""

    degraded: bool
    forced: bool
    findings: tuple[Finding, ...]
    notes: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class _RetentionDecision:
    """Pure decision: which images to remove and what to tell the operator."""

    remove: tuple[str, ...]
    keep: tuple[str, ...]
    notes: tuple[str, ...]


# ---------------------------------------------------------------------------
# Default production runner
# ---------------------------------------------------------------------------


class _ComposeDockerSeam:
    """Default docker seam: `docker compose` against the project directory."""

    def __init__(self, project_dir: Path) -> None:
        self._project_dir = project_dir

    def _compose(
        self, *arguments: str, env: dict[str, str] | None = None
    ) -> CommandResult:
        argv = ["docker", "compose", "-f", str(self._project_dir / COMPOSE_NAME), *arguments]
        finished = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            cwd=str(self._project_dir),
            env={**os.environ, **env} if env else None,
        )
        return CommandResult(finished.returncode, finished.stdout + finished.stderr)

    def stop(self) -> None:
        result = self._compose("down")
        if result.code != 0:
            raise OperatorError(
                f"`docker compose down` failed for the engine container project "
                f"at {self._project_dir} (exit {result.code}). Compose said:\n"
                f"{result.out.strip()}"
            )

    def start(self, image_reference: str, *, env: dict[str, str] | None = None) -> None:
        env = dict(env) if env else {}
        env.setdefault("ERGANE_VERSION", image_reference.rsplit(":", 1)[-1])
        result = self._compose("up", "-d", "--no-build", env=env)
        if result.code != 0:
            raise OperatorError(
                f"`docker compose up -d` failed for the engine container project "
                f"at {self._project_dir} (exit {result.code}). Compose said:\n"
                f"{result.out.strip()}"
            )

    def verify(self) -> tuple[list[Finding], int]:
        # Verify through the engine: run the host's install --verify battery
        # inside the container and take its exit code as the verdict.
        return verify_controlplane()

    def list_images(self) -> list[str]:
        result = subprocess.run(
            ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise OperatorError(
                f"`docker images` failed (exit {result.returncode}). Docker said:\n"
                f"{result.stdout.strip()}{result.stderr.strip()}"
            )
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def remove_image(self, ref: str) -> None:
        result = subprocess.run(
            ["docker", "rmi", ref],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise OperatorError(
                f"`docker rmi {ref}` failed (exit {result.returncode}). Docker said:\n"
                f"{result.stdout.strip()}{result.stderr.strip()}"
            )


# ---------------------------------------------------------------------------
# Project resolution
# ---------------------------------------------------------------------------


def _project_directory() -> Path:
    """Where the generated compose project is expected to live.

    Derived from `supervision_home() / "container"` per 104 plan ruling R1.
    `ERGANE_COMPOSE_PROJECT` is honoured only as an operator override; nothing
    sets it and the refusal does not ask the operator to set it (trap 25).
    When 104 lands, this can delegate to `container_project.installed_project()`.
    """
    env_override = os.environ.get("ERGANE_COMPOSE_PROJECT")
    if env_override:
        return Path(env_override)
    return supervision_home() / CONTAINER_PROJECT_DIRNAME


def _require_project(directory: Path) -> None:
    """Refuse with the directory and the right remedy when the project is absent."""
    if not directory.is_dir():
        raise OperatorError(
            f"no engine container project at {directory}: "
            "run `ergane install` to generate it before upgrading the engine."
        )
    compose = directory / COMPOSE_NAME
    if not compose.is_file():
        raise OperatorError(
            f"engine container project at {directory} has no {COMPOSE_NAME}: "
            "run `ergane install` to generate it before upgrading the engine."
        )


# ---------------------------------------------------------------------------
# Drain decision
# ---------------------------------------------------------------------------


def _drain_refusal(open_epics: Sequence[OpenEpic]) -> str:
    """The refusal sentence for in-flight work, shaped like units.py:791-797."""
    ids = sorted(epic.epic_id for epic in open_epics)
    return (
        f"refusing to upgrade the engine while {', '.join(ids)} is in flight: "
        "stopping the engine mid-epic strands the attempt it is running; "
        "let it land, or kill it first, or pass `--force` to proceed anyway"
    )


# ---------------------------------------------------------------------------
# Retention decision (pure)
# ---------------------------------------------------------------------------


def _numeric_release_tag(image: str) -> tuple[int, int, int] | None:
    """Parse an exact-repository numeric major.minor.patch release tag."""
    prefix = f"{IMAGE_REPOSITORY}:"
    if not image.startswith(prefix):
        return None

    tag = image.rsplit(":", 1)[-1]
    components = tag.split(".")
    if len(components) != 3 or not all(component.isdigit() for component in components):
        return None
    return tuple(int(component) for component in components)


def _retention_decision(
    images: Sequence[str],
    *,
    target_image: str,
    previous_image: str | None,
) -> _RetentionDecision:
    """Which images to remove, purely (deploy.py:168-202 pattern).

    Never the target (newly-started) version.  Never the immediately previous
    version.  Unknown is not zero: if the running version cannot be read from the
    identity record, nothing is removed.
    """
    if previous_image is None:
        return _RetentionDecision(
            remove=(),
            keep=tuple(images),
            notes=(
                "could not read the running engine version from the identity record; "
                "keeping every local image",
            ),
        )

    target_release = _numeric_release_tag(target_image)
    previous_release = _numeric_release_tag(previous_image)
    if target_release is None or previous_release is None:
        return _RetentionDecision(
            remove=(),
            keep=tuple(images),
            notes=(
                "target or previous image is not a recognized numeric release; "
                "keeping every local image",
            ),
        )

    remove: list[str] = []
    keep: list[str] = []
    for image in images:
        if image in {target_image, previous_image}:
            keep.append(image)
            continue

        release = _numeric_release_tag(image)
        if release is None or release >= previous_release:
            keep.append(image)
            continue

        remove.append(image)

    notes: list[str] = [
        f"keeping target image {target_image}",
        f"keeping previous image {previous_image}",
    ]
    if remove:
        notes.append(f"removing {len(remove)} older image(s): {', '.join(remove)}")

    return _RetentionDecision(
        remove=tuple(remove),
        keep=tuple(keep),
        notes=tuple(notes),
    )


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------


def upgrade(
    *,
    force: bool = False,
    open_epics: Callable[[], Sequence[OpenEpic]] | None = None,
    docker: DockerSeam | None = None,
    _state_home: Path | str | None = None,
) -> UpgradeReport:
    """Upgrade the engine container to the CLI's pinned image version.

    Refuses while work is in flight unless ``force`` is true.  Stops the running
    engine, starts the new pinned image, verifies through it, and reaps images
    older than the previous version.  Before anything disruptive it validates
    the generated project's ownership and retargets the persisted image and
    version declarations, so a refusal or persistence failure leaves the prior
    project untouched (spec 174 US2).
    """
    if open_epics is None:
        from factory.supervision.units import _open_epics

        open_epics = _open_epics

    epics = tuple(open_epics())
    if epics and not force:
        raise OperatorError(_drain_refusal(epics))

    project_dir = _project_directory()
    _require_project(project_dir)

    if docker is None:
        docker = _ComposeDockerSeam(project_dir)

    target_version = cli_version()
    target_image = image_reference(target_version)

    state_home = _state_home or resolve_state_home()
    identity = read_identity(state_home)
    previous_image = identity.image_reference if identity is not None else None

    notes: list[str] = []
    if force and epics:
        notes.append(
            f"proceeding with upgrade despite {', '.join(epic.epic_id for epic in epics)} in flight"
        )

    # Ownership is not bypassable: `force` reaches the in-flight-work refusal
    # only, so no force is passed here.  Refusals and persistence failures
    # leave the project bytes untouched and stop before docker.stop (FR-007,
    # FR-008).
    retargeted = retarget_project(
        project_dir, image=target_image, version=target_version
    )
    if retargeted.retargeted:
        notes.append(
            f"retargeted {', '.join(retargeted.retargeted)} to {target_image}"
        )
    else:
        notes.append(f"project at {project_dir} already selects {target_image}")

    docker.stop()

    # The new engine needs ERGANE_VERSION set so compose.reference.yaml:10 resolves
    # the image tag it was pinned to (trap 9).
    docker.start(target_image, env={"ERGANE_VERSION": target_version})

    findings, _verify_exit = docker.verify()
    findings = list(findings)

    # `degraded` is keyed on the engine finding alone (FR-019).
    engine_finding = next((f for f in findings if f.check == "engine"), None)
    degraded = False if engine_finding is None else not engine_finding.passed
    engine_verified = engine_finding is not None and engine_finding.passed

    local_images = docker.list_images() if engine_verified else ()
    retention = _retention_decision(
        local_images,
        target_image=target_image,
        previous_image=previous_image,
    )

    for note in retention.notes:
        notes.append(note)

    for image in retention.remove:
        docker.remove_image(image)

    return UpgradeReport(
        degraded=degraded,
        forced=force,
        findings=tuple(findings),
        notes=tuple(notes),
    )
