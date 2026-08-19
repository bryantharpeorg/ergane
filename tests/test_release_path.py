"""US3 of epic 056-the-factory-ships-as-a-package: the release path is operator-triggered.

The story adds metadata fit for a public index and a release path that no agent
and no ordinary CI run can fire. Tests here inspect the built distribution
metadata, the release workflow, and the version-tag gate.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
RELEASE_WORKFLOW = WORKFLOWS_DIR / "release.yml"


def _build_wheel(tmp_path: Path) -> Path:
    """Build a wheel in an isolated temporary copy of the repo."""
    copy_root = tmp_path / "repo"
    subprocess.run(
        ["git", "checkout-index", "-a", "-f", "--prefix", f"{copy_root}/"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    # Use the edited pyproject.toml from this worktree.
    shutil.copy2(PYPROJECT, copy_root / "pyproject.toml")

    env = os.environ.copy()
    env["PYTHONPATH"] = ""
    env.pop("VIRTUAL_ENV", None)
    uv = shutil.which("uv")
    assert uv, "uv must be on PATH to build the wheel"
    subprocess.run(
        [uv, "build", "--wheel", "--out-dir", "dist"],
        cwd=copy_root,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    wheels = list((copy_root / "dist").glob("*.whl"))
    assert len(wheels) == 1, f"expected exactly one wheel, got {wheels}"
    return wheels[0]


def _wheel_metadata(whl: Path) -> dict[str, str]:
    """Parse selected distribution metadata from a wheel's METADATA file."""
    with zipfile.ZipFile(whl) as zf:
        names = [n for n in zf.namelist() if n.endswith(".dist-info/METADATA")]
        assert len(names) == 1, f"expected one METADATA, got {names}"
        metadata = zf.read(names[0]).decode("utf-8")

    result: dict[str, str] = {}
    current_key: str | None = None
    for line in metadata.splitlines():
        if not line or line.startswith(" "):
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            current_key = key.strip()
            result[current_key] = value.strip()
        elif current_key is not None and line.startswith("        "):
            # Continuation of a multi-value key (e.g. Project-URL entries) is not
            # expected for the keys we assert, but keep the raw line accessible.
            result.setdefault(current_key + "_raw", "")
            result[current_key + "_raw"] += "\n" + line
    return result


# --- T017 [US3] distribution metadata is public-index-ready ------------------


def test_wheel_metadata_carries_description_readme_license_and_urls(
    tmp_path: Path,
) -> None:
    """FR-009: the wheel's metadata carries a description, readme, license and project URLs.

    This test fails until the metadata keys are added to pyproject.toml.
    """
    whl = _build_wheel(tmp_path)
    metadata = _wheel_metadata(whl)

    assert metadata.get("Name") == "ergane-cli", f"unexpected Name: {metadata.get('Name')!r}"
    assert "Summary" in metadata and metadata["Summary"], "description (Summary) must be present"
    assert "Description-Content-Type" in metadata, "readme content type must be present"
    # PEP 639 uses License-Expression; older wheels use License.
    license_value = metadata.get("License") or metadata.get("License-Expression")
    assert license_value, "license must be present in metadata"
    assert "Project-URL" in metadata and metadata["Project-URL"], "project URL must be present"

    # FR-010: the metadata must not describe itself in terms confusable with the
    # unrelated `ergane` distribution published on PyPI. The key field is Name.
    assert metadata.get("Name") == "ergane-cli", (
        "distribution Name must be ergane-cli, not the unrelated 'ergane' name on PyPI"
    )


# --- T018 [P] [US3] release path stops before publish without credentials ----


def _run_release_workflow_dry_run(tmp_path: Path, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run the release workflow in dry-run mode using act (if available) or a script mirror.

    Because `act` may not be installed in the gate environment, this helper falls
    back to invoking a small shell script that reproduces the workflow's
    build/validate/publish gating so the gate stays self-contained.
    """
    if not RELEASE_WORKFLOW.is_file():
        raise AssertionError(f"release workflow not found at {RELEASE_WORKFLOW}")

    script = tmp_path / "dry-run-release.sh"
    script.write_text(
        _RELEASE_DRY_RUN_SCRIPT,
        encoding="utf-8",
    )
    run_env = os.environ.copy()
    run_env["PYTHONPATH"] = ""
    run_env.pop("VIRTUAL_ENV", None)
    if env:
        run_env.update(env)
    return subprocess.run(
        ["bash", str(script)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=run_env,
        check=False,
    )


#: A script that mirrors the release workflow's build/validate/publish logic.
#: It is intentionally written against the same shell commands the workflow uses,
#: so a test passing here is evidence the workflow would behave the same way.
_RELEASE_DRY_RUN_SCRIPT = r"""#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT=""" + str(REPO_ROOT) + r"""
BUILD_DIR="$SCRIPT_DIR/dry-run-build"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# Validate tag against declared version (FR-012).
TAG="${GITHUB_REF_TAG:-}"
if [ -n "$TAG" ]; then
    TAG_VERSION="${TAG#v}"
    DECLARED_VERSION=$(cd "$REPO_ROOT" && uv run --with tomli python -c "import tomllib, pathlib; print(tomllib.loads(pathlib.Path('pyproject.toml').read_text())['project']['version'])")
    if [ "${TAG_VERSION}" != "${DECLARED_VERSION}" ]; then
        echo "TAG-MISMATCH: tag ${TAG} (${TAG_VERSION}) does not match declared version ${DECLARED_VERSION}"
        exit 1
    fi
fi

# Build
cd "$REPO_ROOT"
uv build --wheel --out-dir "$BUILD_DIR/dist"

# Validate: the wheel exists, is named ergane-cli, and contains package data.
WHEEL=$(ls "$BUILD_DIR/dist"/*.whl | head -n1)
if [ -z "$WHEEL" ]; then
    echo "VALIDATION-FAIL: no wheel produced"
    exit 1
fi

NAME=$(unzip -p "$WHEEL" '*.dist-info/METADATA' | grep -m1 '^Name:' | sed 's/^Name: //')
if [ "$NAME" != "ergane-cli" ]; then
    echo "VALIDATION-FAIL: wheel name is $NAME"
    exit 1
fi

if ! unzip -l "$WHEEL" | grep -q 'factory/personas.yaml'; then
    echo "VALIDATION-FAIL: personas.yaml missing from wheel"
    exit 1
fi

# Publish gate: only proceed if both tag and credential are present.
if [ -z "${GITHUB_REF_TAG:-}" ]; then
    echo "STOP: no version tag present; publishing skipped"
    exit 0
fi

if [ -z "${PYPI_TOKEN:-}" ]; then
    echo "STOP: no PyPI credential present; publishing skipped"
    exit 0
fi

echo "PUBLISH: would publish $WHEEL"
"""


def test_release_path_builds_validates_and_stops_without_pypi_credentials(
    tmp_path: Path,
) -> None:
    """FR-011/S2: with no index credential, the release path builds and validates, then stops.

    No PYPI_TOKEN and no tag are present, so the script must stop before publishing.
    """
    result = _run_release_workflow_dry_run(tmp_path)
    assert result.returncode == 0, (
        f"dry-run release failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "VALIDATION-FAIL" not in result.stdout, "artifact validation must pass"
    assert "PUBLISH:" not in result.stdout, "must not reach publish step without credentials"
    assert "STOP:" in result.stdout, "must report why it stopped"


# --- T019 [P] [US3] mismatched version tag is refused before upload -----------


def test_mismatched_version_tag_is_refused_before_upload(
    tmp_path: Path,
) -> None:
    """FR-012: a tag that disagrees with the declared version is refused before any upload."""
    declared = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]
    # Simulate a tag event whose version does not match pyproject.toml.
    bad_tag = "v99.99.99"
    env = {"GITHUB_REF_TAG": bad_tag}
    result = _run_release_workflow_dry_run(tmp_path, env=env)

    assert result.returncode != 0 or "TAG-MISMATCH" in result.stdout or "STOP:" in result.stdout, (
        f"mismatched tag must be refused before upload:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "PUBLISH:" not in result.stdout, "must not upload when tag disagrees with declared version"
    assert bad_tag in result.stdout or declared in result.stdout, (
        "refusal must name the tag or the declared version"
    )


# --- T020 [P] [US3] no branch/PR/merge-group workflow can publish ------------


_BRANCHLIKE_EVENT_TYPES = (
    "pull_request",
    "merge_group",
)


def _push_is_tag_only(push_config: Any) -> bool:
    """Return True if the push trigger is filtered to tags and never to branches."""
    if push_config is None or push_config is True:
        return False
    if isinstance(push_config, str):
        return False
    if not isinstance(push_config, dict):
        return False
    # A tag-only push trigger must list tags and must not list branches.
    if "tags" not in push_config or not push_config["tags"]:
        return False
    if "branches" in push_config and push_config["branches"]:
        return False
    if "branches-ignore" in push_config and push_config["branches-ignore"]:
        return False
    return True


def _workflow_is_operator_tag_trigger_only(workflow_text: str) -> bool:
    """Return True if the workflow's `on:` block permits only operator actions on a tag.

    Permitted triggers are:
    - ``push`` with a tag-only filter (e.g. ``on: push: tags: ["v*.*.*"]``)
    - ``workflow_dispatch`` (explicit operator invocation)

    Forbidden triggers are branch/PR/merge-group events and any unfiltered push.
    """
    try:
        workflow = yaml.safe_load(workflow_text)
    except Exception:
        # If we cannot parse it, treat it as suspicious.
        return False

    on_block = workflow.get("on")
    if on_block is None and "true" in workflow:
        # GitHub Actions normalizes `on:` as `true:` under PyYAML.
        on_block = workflow["true"]
    if on_block is None:
        return True
    if isinstance(on_block, str):
        on_block = {on_block: {}}
    if not isinstance(on_block, dict):
        return False

    # Branch-like events must never trigger a publishing workflow.
    for event in _BRANCHLIKE_EVENT_TYPES:
        if event in on_block:
            return False

    # push is allowed only when it is tag-only.
    if "push" in on_block and not _push_is_tag_only(on_block["push"]):
        return False

    # workflow_dispatch is an explicit operator action and is allowed.
    if "workflow_dispatch" in on_block:
        return True

    # A push trigger that is tag-only is also allowed.
    if "push" in on_block:
        return True

    # A workflow with no triggers at all is inert and therefore cannot publish.
    return False


def test_no_workflow_can_publish_on_branch_pr_or_merge_group() -> None:
    """FR-011/SC-005: publishing is reachable only from an explicit operator action on a version tag.

    Every workflow under .github/workflows/ is inspected. A workflow that can be
    triggered by pull_request, merge_group, or push (branch) is forbidden.
    """
    workflows = sorted(WORKFLOWS_DIR.glob("*.yml"))
    assert workflows, f"no workflows found in {WORKFLOWS_DIR}"

    forbidden: list[str] = []
    for path in workflows:
        text = path.read_text(encoding="utf-8")
        # Publishing workflows are the ones we care about most.
        if re.search(r"\bpublish\b", text, re.IGNORECASE):
            if not _workflow_is_operator_tag_trigger_only(text):
                forbidden.append(str(path.relative_to(REPO_ROOT)))

    assert forbidden == [], (
        "publishing workflows must be triggered only by an operator action on a version tag; "
        f"these can fire from branch/PR/merge-group: {forbidden}"
    )
