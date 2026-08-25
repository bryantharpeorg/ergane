"""The image is built, not just read.

Every other container test in this tree parses the Dockerfile as text.  That is
how the release image reached 25 landed stories without ever being built: on
2026-08-25 `docker build` failed at `useradd -m -u 1000 ergane` with `UID 1000
is not unique`, because ubuntu:24.04 ships an account at that uid, while
`test_dockerfile_runs_as_non_root` read the `USER 1000:1000` line two lines
below and passed.  Text agreement is not a working artifact
(`container/the-release-image-has-never-been-built-and-does-not-build`).

These tests build it.  They are guarded on the daemon rather than marked, so a
host without docker skips them and a host with docker never silently opts out.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

#: The uid the whole confinement story is written against: compose declares
#: `user: 1000:1000`, and the AppArmor and seccomp artifacts are written for
#: it.  The account NAME is deliberately not asserted — ubuntu:24.04 already
#: owns uid 1000 as `ubuntu`, and the image binds the number, not the name.
RUNTIME_UID = 1000

REPO_ROOT = Path(__file__).resolve().parents[1]

#: One built image serves every test in this module.  A build is ~20s warm and
#: several minutes cold; per-test builds would put this file beyond any
#: reasonable suite budget.
IMAGE_TAG = "ergane-buildtest:pytest"


def _docker() -> str | None:
    """The docker binary, if a daemon is actually reachable.

    Presence of the client is not enough: CI images ship `docker` with no
    daemon behind it, and `docker build` there fails for a reason that has
    nothing to do with this repository.
    """
    binary = shutil.which("docker")
    if binary is None:
        return None
    probe = subprocess.run(
        [binary, "version", "--format", "{{.Server.Version}}"],
        capture_output=True,
        text=True,
    )
    return binary if probe.returncode == 0 else None


DOCKER = _docker()

pytestmark = pytest.mark.skipif(
    DOCKER is None, reason="docker daemon is not reachable"
)


@pytest.fixture(scope="module")
def built_image() -> str:
    """Build the committed Dockerfile, and fail loudly with the build log."""
    build = subprocess.run(
        [DOCKER, "build", "-t", IMAGE_TAG, str(REPO_ROOT)],
        capture_output=True,
        text=True,
    )
    if build.returncode != 0:
        # The tail carries the failing layer; the whole log is too long to read
        # in a failure report and the last lines are where the error is.
        tail = "\n".join(build.stderr.strip().splitlines()[-25:])
        pytest.fail(f"docker build failed:\n{tail}")
    yield IMAGE_TAG
    subprocess.run([DOCKER, "rmi", "-f", IMAGE_TAG], capture_output=True)


def _in_image(image: str, script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [DOCKER, "run", "--rm", "--entrypoint", "sh", image, "-c", script],
        capture_output=True,
        text=True,
    )


def test_the_committed_dockerfile_builds(built_image: str) -> None:
    """The whole point: the artifact the release workflow pushes must exist."""
    assert built_image == IMAGE_TAG


def test_the_image_runs_as_the_confinement_uid(built_image: str) -> None:
    """`USER` is numeric, so assert the number the profiles are written for."""
    result = _in_image(built_image, "id -u")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(RUNTIME_UID)


def test_home_exists_and_is_writable(built_image: str) -> None:
    """The regression that the first attempt at the uid fix introduced.

    Dropping `useradd` alone builds cleanly and leaves `ENV HOME` pointing at a
    directory nothing creates.  The adapter writes a per-node home under $HOME,
    so an unwritable one is a runtime failure with a build-time cause.
    """
    result = _in_image(built_image, 'touch "$HOME/.probe" && echo ok')
    assert result.returncode == 0, f"$HOME is not writable: {result.stderr}"
    assert result.stdout.strip() == "ok"


def test_the_installed_cli_starts_and_reports_the_package_version(
    built_image: str,
) -> None:
    """A venv that imports is not a CLI that runs — start it and read it back.

    The version is compared against `cli_version()`, the same answer 105/US2
    stamps into the engine identity record, so an image whose banner disagreed
    with the identity it writes would fail here.
    """
    from factory.supervision.engine_identity import cli_version

    expected = cli_version()
    result = _in_image(built_image, "ergane --version")
    assert result.returncode == 0, result.stderr
    first = result.stdout.strip().splitlines()[0]
    assert re.match(r"^ergane \S+", first), first
    if expected != "unknown":
        assert expected in first, f"{first!r} does not carry {expected!r}"
