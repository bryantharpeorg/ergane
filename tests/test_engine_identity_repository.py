"""105-US3: one repository string, three artifacts (T025).

The refusal tells an operator which image to pull; that image must be the one CI
actually publishes.  Derive the repository from all three places, never restate
it as a literal.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from factory.supervision.engine_identity import IMAGE_REPOSITORY


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _image_repository_from_compose(compose_path: Path) -> str:
    document = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    image = document["services"]["ergane"]["image"]
    return image.rsplit(":", 1)[0]


def _image_repository_from_workflow(workflow_path: Path) -> str:
    document = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    for job in document["jobs"].values():
        if "IMAGE_REPOSITORY" in job.get("env", {}):
            return job["env"]["IMAGE_REPOSITORY"]
    raise AssertionError("no IMAGE_REPOSITORY env in workflow jobs")


def test_repository_string_is_derived_from_all_three_artifacts(repo_root: Path) -> None:
    """T025 / US3-S1 / FR-012: workflow, compose reference, and constant agree."""
    workflow_repo = _image_repository_from_workflow(
        repo_root / ".github" / "workflows" / "release.yml"
    )
    compose_repo = _image_repository_from_compose(
        repo_root / "container" / "compose.reference.yaml"
    )

    assert workflow_repo == compose_repo
    assert workflow_repo == IMAGE_REPOSITORY
    assert compose_repo == IMAGE_REPOSITORY
    assert IMAGE_REPOSITORY == "ghcr.io/bryantharpeorg/ergane"
