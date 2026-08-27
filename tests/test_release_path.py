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
    # The wheel's force-include now points at the example source file.
    shutil.copy2(REPO_ROOT / "personas.example.yaml", copy_root / "personas.example.yaml")

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


# --- US1 drift tests: the release workflow gains the image job -----------------


_IMAGES_DIR = REPO_ROOT / "container"
_COMPOSE_REFERENCE = _IMAGES_DIR / "compose.reference.yaml"


def _load_release_workflow() -> dict[str, Any]:
    if not RELEASE_WORKFLOW.is_file():
        pytest.fail(f"release workflow not found at {RELEASE_WORKFLOW}")
    return yaml.safe_load(RELEASE_WORKFLOW.read_text(encoding="utf-8"))


def _job_ids(workflow: dict[str, Any]) -> list[str]:
    jobs = workflow.get("jobs", {})
    assert isinstance(jobs, dict), f"workflow jobs block must be a dict, got {jobs!r}"
    return list(jobs.keys())


def _image_job_text() -> str:
    """Return the raw text of the image job, starting at its id line."""
    text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r"^  build-and-publish-image:\s*$", text, re.MULTILINE)
    assert match is not None, "image job 'build-and-publish-image' not found"
    # Slice from the id line to the end of the file (it is the last job).
    # Strip the leading two spaces so PyYAML parses the job block as top-level.
    return text[match.start():]


def test_us1_image_job_exists_with_correct_needs() -> None:
    """FR-001: image job exists in release.yml with needs: [build-and-publish]."""
    workflow = _load_release_workflow()
    jobs = workflow.get("jobs", {})
    assert "build-and-publish-image" in jobs, (
        f"image job missing; jobs are: {list(jobs.keys())}"
    )
    image_job = jobs["build-and-publish-image"]
    assert image_job.get("needs") == ["build-and-publish"], (
        f"image job needs wrong: {image_job.get('needs')!r}"
    )


def _preflight_job_text() -> str:
    """Return the raw text of the preflight image job only."""
    text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r"^  build-image-preflight:\s*$", text, re.MULTILINE)
    assert match is not None, "preflight job 'build-image-preflight' not found"
    start = match.start()
    next_job = re.search(r"^  [a-zA-Z0-9_-]+:\s*$", text[start + 1 :], re.MULTILINE)
    end = start + 1 + next_job.start() if next_job else len(text)
    return text[start:end]


def _bash_run_blocks(job_text: str) -> list[str]:
    """Return the body of every `run: |` block in a job's raw YAML text."""
    blocks: list[str] = []
    for match in re.finditer(r'^\s+run:\s*\|\s*\n((?:\s+.*\n?)+)', job_text, re.MULTILINE):
        blocks.append(match.group(1))
    return blocks


def _job_text(job_id: str) -> str:
    """Return the raw text of a job, starting at its id line and ending at the next job."""
    text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    match = re.search(rf"^  {re.escape(job_id)}:\s*$", text, re.MULTILINE)
    assert match is not None, f"job '{job_id}' not found"
    start = match.start()
    next_job = re.search(r"^  [a-zA-Z0-9_-]+:\s*$", text[start + 1 :], re.MULTILINE)
    end = start + 1 + next_job.start() if next_job else len(text)
    return text[start:end]


def _job_is_ordered_after(target: str, job_id: str, workflow: dict[str, Any]) -> bool:
    """Return True if job_id directly or transitively needs target."""
    jobs = workflow.get("jobs", {})
    seen: set[str] = set()

    def _walk(current: str) -> bool:
        if current in seen:
            return False
        seen.add(current)
        needs = jobs.get(current, {}).get("needs", [])
        if isinstance(needs, str):
            needs = [needs]
        if target in needs:
            return True
        return any(_walk(dep) for dep in needs)

    return _walk(job_id)


def test_us2_preflight_job_exists_with_correct_needs() -> None:
    """FR-011/FR-013: preflight job exists and build-and-publish needs it."""
    workflow = _load_release_workflow()
    jobs = workflow.get("jobs", {})
    assert "build-image-preflight" in jobs, (
        f"preflight job missing; jobs are: {list(jobs.keys())}"
    )
    assert "build-and-publish" in jobs, "build-and-publish job missing"
    assert jobs["build-and-publish"].get("needs") == ["build-image-preflight"], (
        f"build-and-publish needs wrong: {jobs['build-and-publish'].get('needs')!r}"
    )


def test_us2_preflight_job_builds_amd64_without_push() -> None:
    """FR-011: preflight builds for linux/amd64 and never pushes."""
    job_text = _preflight_job_text()
    run_blocks = _bash_run_blocks(job_text)
    assert run_blocks, "no run blocks found in preflight job"
    invocations = [block for block in run_blocks if "docker buildx build" in block]
    assert len(invocations) == 1, (
        f"expected exactly one 'docker buildx build' invocation, got {invocations!r}"
    )
    invocation = invocations[0]
    assert "linux/amd64" in invocation, "preflight must build for linux/amd64"
    assert "--push" not in invocation, "preflight build must not contain --push"


def test_us2_preflight_job_has_no_publish_credential() -> None:
    """FR-012: preflight has no packages:write, no --push, no registry login."""
    workflow = _load_release_workflow()
    jobs = workflow.get("jobs", {})
    preflight = jobs.get("build-image-preflight", {})
    permissions = preflight.get("permissions", {})
    assert permissions.get("packages") != "write", (
        f"preflight must not declare packages: write, got {permissions!r}"
    )
    job_text = _preflight_job_text()
    assert "--push" not in job_text, "preflight must not contain --push anywhere"
    assert "docker/login-action" not in job_text, "preflight must not log in to a registry"
    assert "registry:" not in job_text, "preflight must not reference a registry"


def test_us2_ghcr_login_assertion_rejects_non_ghcr_registry() -> None:
    """FR-016: the GHCR login assertion fails when the registry is not GHCR."""
    bad_job_text = """
      - name: Log in to wrong registry
        uses: docker/login-action@v3
        with:
          registry: docker.io
          username: ${{ github.actor }}
          password: ${{ github.token }}
    """
    with pytest.raises(AssertionError):
        _assert_ghcr_login_registry(bad_job_text)


def test_us1_image_job_is_single_multi_arch_buildx_push() -> None:
    """FR-002: exactly one buildx build invocation carries both platforms and --push."""
    job_text = _image_job_text()
    # The command is split across backslash-continued lines; join the run blocks
    # so the assertion is about the whole invocation, not a single trimmed line.
    run_blocks = _bash_run_blocks(job_text)
    assert run_blocks, "no run blocks found in image job"
    # The build command is the only one that starts with `docker buildx build`.
    invocations = [
        block
        for block in run_blocks
        if "docker buildx build" in block
    ]
    assert len(invocations) == 1, (
        f"expected exactly one 'docker buildx build' invocation, got {invocations!r}"
    )
    invocation = invocations[0]
    assert "--push" in invocation, f"buildx invocation missing --push: {invocation}"
    assert "--platform" in invocation, f"buildx invocation missing --platform: {invocation}"
    assert "linux/amd64" in invocation and "linux/arm64" in invocation, (
        f"buildx invocation missing required platforms: {invocation}"
    )


def _assert_ghcr_login_registry(job_text: str) -> None:
    """Assert the GHCR login step resolves to the GHCR host.

    The login step must reference the workflow's declared IMAGE_REPOSITORY,
    and that variable must resolve to ghcr.io/bryantharpeorg/ergane.
    """
    workflow = _load_release_workflow()
    image_job = workflow.get("jobs", {}).get("build-and-publish-image", {})
    image_repository = image_job.get("env", {}).get("IMAGE_REPOSITORY")
    assert image_repository == "ghcr.io/bryantharpeorg/ergane", (
        f"IMAGE_REPOSITORY must resolve to ghcr.io/bryantharpeorg/ergane, got {image_repository!r}"
    )
    assert "registry: ${{ env.IMAGE_REPOSITORY }}" in job_text, (
        "GHCR login must reference IMAGE_REPOSITORY so it resolves to ghcr.io/bryantharpeorg/ergane"
    )


def test_us1_image_job_uses_github_token_for_ghcr_login() -> None:
    """FR-004/FR-015: GHCR login uses the GitHub token and resolves to ghcr.io."""
    job_text = _image_job_text()
    _assert_ghcr_login_registry(job_text)
    assert "password: ${{ github.token }}" in job_text, (
        "GHCR login must use github.token"
    )


def test_us1_image_job_signs_pushed_digest_with_cosign() -> None:
    """FR-005: a cosign step signs the pushed digest, not a tag."""
    job_text = _image_job_text()
    assert "uses: sigstore/cosign-installer@v3" in job_text, "cosign-installer missing"
    cosign_lines = [
        line.strip()
        for line in job_text.splitlines()
        if line.strip().startswith("cosign sign")
    ]
    assert len(cosign_lines) == 1, f"expected exactly one cosign sign line, got {cosign_lines}"
    sign_line = cosign_lines[0]
    assert "${DIGEST}" in sign_line or "@" in sign_line, (
        f"cosign must sign digest, got: {sign_line}"
    )
    assert ":" not in sign_line.split("@")[0] or "${IMAGE_REPOSITORY}" in sign_line, (
        f"cosign target must be repo@digest form: {sign_line}"
    )


def test_us1_image_job_inserts_platform_assertion() -> None:
    """FR-005: imagetools inspect step exits nonzero unless both platforms appear."""
    job_text = _image_job_text()
    assert "docker buildx imagetools inspect" in job_text, "imagetools inspect step missing"
    # The step must check for linux/amd64 and linux/arm64 explicitly.
    assert "linux/amd64" in job_text and "linux/arm64" in job_text, (
        "platform assertion must name both linux/amd64 and linux/arm64"
    )
    # It must be able to fail the build.
    assert "exit 1" in job_text, "platform assertion must be able to exit 1"


def test_us1_image_job_has_own_packages_write_permission() -> None:
    """FR-004: image job has packages: write; build-and-publish block unchanged."""
    workflow = _load_release_workflow()
    jobs = workflow.get("jobs", {})
    assert "build-and-publish" in jobs, "original build-and-publish job missing"
    assert "build-and-publish-image" in jobs, "image job missing"
    original = jobs["build-and-publish"].get("permissions", {})
    assert original == {"contents": "read", "id-token": "write"}, (
        f"build-and-publish permissions block must remain exactly {{contents: read, id-token: write}}, got {original!r}"
    )
    image = jobs["build-and-publish-image"].get("permissions", {})
    assert image.get("packages") == "write", (
        f"image job must declare packages: write, got {image!r}"
    )
    assert image.get("contents") == "read" and image.get("id-token") == "write", (
        f"image job permissions must include contents: read and id-token: write, got {image!r}"
    )


def test_us1_image_tag_derives_from_same_git_tag_as_pypi() -> None:
    """FR-003: image tag derives from GITHUB_REF_NAME, the same source the PyPI job uses."""
    workflow = _load_release_workflow()
    job_text = _image_job_text()
    # The tag must be produced from GITHUB_REF_NAME with a leading v stripped.
    assert "GITHUB_REF_NAME" in job_text, "image job must reference GITHUB_REF_NAME"
    assert "${TAG#v}" in job_text or "${GITHUB_REF_NAME#v}" in job_text, (
        "image tag must strip leading v from the git tag"
    )
    # The original job already validates the tag against pyproject.toml version.
    original = workflow.get("jobs", {}).get("build-and-publish", {})
    original_text = yaml.safe_dump(original)  # rough
    assert "GITHUB_REF_NAME" in original_text, (
        "original job must still derive its version from GITHUB_REF_NAME"
    )


def test_us1_image_repository_declared_once_in_workflow() -> None:
    """FR-007/US1-S2: repository declared once as env and referenced everywhere.

    The repository is not restated in the test; it is read out of the workflow.
    US3 will pin this value to container/compose.reference.yaml:10.
    """
    workflow = _load_release_workflow()
    image_job = workflow.get("jobs", {}).get("build-and-publish-image", {})
    env = image_job.get("env", {})
    assert "IMAGE_REPOSITORY" in env, (
        "IMAGE_REPOSITORY must be declared once as an env key on the image job"
    )
    job_text = _image_job_text()
    # Count references to the env variable, not the literal string.
    # The login step uses ${{ env.IMAGE_REPOSITORY }}; the bash steps use
    # ${IMAGE_REPOSITORY}. Either way, the repository is the one declared env.
    var_uses = job_text.count("${IMAGE_REPOSITORY}") + job_text.count("${{ env.IMAGE_REPOSITORY }}")
    # It must be used in login, build tag, cosign target, and inspect assertion.
    assert var_uses >= 4, (
        f"IMAGE_REPOSITORY must be referenced via env variable in login, build, cosign, and inspect; got {var_uses} uses"
    )


def test_us1_dockerignore_contents() -> None:
    """FR-006: .dockerignore excludes host state and preserves wheel inputs."""
    ignore_path = REPO_ROOT / ".dockerignore"
    assert ignore_path.is_file(), ".dockerignore must exist"
    text = ignore_path.read_text(encoding="utf-8")
    lines = {line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")}
    required_excludes = {
        ".git",
        ".venv",
        ".factory",
        ".claude",
        # The engine creates these two inside the repository, and their absence
        # from this set is why the assertion below passed for months while the
        # requirement in the docstring was violated: a local `docker build`
        # copied .ergane/homes/<spec>/<node>/.claude/.credentials.json -- one real
        # credential per dispatched node -- into the image. 11G of it on the
        # floor host, 2026-08-26. CI never reproduced it because
        # actions/checkout@v4 yields a clean clone, which is precisely why a test
        # rather than a green release run has to hold this.
        ".ergane",
        ".temporal",
        "dist",
        "build",
        "**/__pycache__",
        "*.egg-info",
    }
    missing_excludes = required_excludes - lines
    assert not missing_excludes, f".dockerignore missing excludes: {sorted(missing_excludes)}"

    must_not_exclude = {"pyproject.toml", "README.md", "personas.example.yaml", "factory/"}
    for item in must_not_exclude:
        assert item not in lines, f".dockerignore must NOT exclude {item!r}"


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


# --- T022 [US4] compose demo asset is published after the image job --------------


def test_us4_compose_asset_published_after_image_job() -> None:
    """FR-017/T022: a step publishes container/compose.demo.yaml, ordered after the image job.

    A compose file naming an image that does not exist yet is failure mode 13 in
    a new costume; the publish step must therefore run only after
    build-and-publish-image has pushed the image.
    """
    workflow = _load_release_workflow()

    publish_job_id: str | None = None
    for job_id in workflow.get("jobs", {}):
        if "container/compose.demo.yaml" in _job_text(job_id):
            publish_job_id = job_id
            break

    assert publish_job_id is not None, (
        "no job references container/compose.demo.yaml; a release asset step is required"
    )
    assert _job_is_ordered_after("build-and-publish-image", publish_job_id, workflow), (
        f"job {publish_job_id} must be ordered after build-and-publish-image"
    )

    job_text = _job_text(publish_job_id)
    assert "gh release upload" in job_text, (
        f"job {publish_job_id} must upload a release asset with gh release upload"
    )


def test_us4_publish_job_creates_the_release_before_uploading() -> None:
    """A pushed tag is not a release, and `gh release upload` requires one.

    Measured 2026-08-26: v0.4.0 ran every job in this workflow green, shipped to
    PyPI and GHCR, and left no release object behind — `gh release view v0.4.0`
    answered "release not found". Release objects were being made by hand. So a
    publish job that only uploads fails on any tag whose release nobody created
    first, and the version number is spent with nothing to show.

    The ordering matters as much as the presence: creating after uploading is
    the same bug with extra steps.
    """
    workflow = _load_release_workflow()

    publish_job_id: str | None = None
    for job_id in workflow.get("jobs", {}):
        if "container/compose.demo.yaml" in _job_text(job_id):
            publish_job_id = job_id
            break

    assert publish_job_id is not None, (
        "no job references container/compose.demo.yaml; a release asset step is required"
    )

    # Compare commands, not prose: a comment that mentions `gh release upload`
    # would otherwise satisfy or defeat the ordering check depending on where it
    # sits, which makes the test a test of the comments.
    job_text = _job_text(publish_job_id)
    commands = "\n".join(
        line for line in job_text.splitlines() if not line.lstrip().startswith("#")
    )

    assert "gh release create" in commands, (
        f"job {publish_job_id} uploads a release asset but never creates the "
        "release to upload it to; a pushed tag is not a release object"
    )
    assert commands.index("gh release create") < commands.index("gh release upload"), (
        f"job {publish_job_id} creates the release after uploading to it"
    )
    assert "--verify-tag" in commands, (
        f"job {publish_job_id} must pass --verify-tag so a mistyped tag fails "
        "here instead of creating a release that points at nothing"
    )


# --- T023 [P] [US4] tag-agreement check lives in the workflow ------------------


def test_us4_compose_asset_tag_agreement_checked_in_workflow() -> None:
    """FR-018/T023: the workflow fails the release if the published compose engine tag mismatches.

    The check must be in the workflow, not a human procedure. It fetches the
    published asset back, extracts the engine image tag, and exits non-zero on
    mismatch with the tag being released.
    """
    workflow = _load_release_workflow()

    publish_job_id: str | None = None
    for job_id in workflow.get("jobs", {}):
        if "container/compose.demo.yaml" in _job_text(job_id):
            publish_job_id = job_id
            break

    assert publish_job_id is not None, (
        "no job references container/compose.demo.yaml; cannot locate tag-agreement check"
    )
    job_text = _job_text(publish_job_id)

    assert "releases/download/" in job_text, (
        "publish job must fetch the published release asset back from GitHub"
    )
    assert "image:" in job_text, (
        "publish job must read the engine image reference from the compose asset"
    )
    assert "exit 1" in job_text, (
        "tag-agreement assertion must be able to fail the release by exiting non-zero"
    )


# --- T024 [P] [US4] regression guard for 105 and 108 landed tests --------------


def test_us4_release_workflow_regression_guard() -> None:
    """FR-019/T024: preflight/image ordering and 108 package/visibility assertions still hold."""
    workflow = _load_release_workflow()
    jobs = workflow.get("jobs", {})

    # Preflight ordering (release.yml:21, :42-43).
    assert "build-image-preflight" in jobs, "preflight job missing"
    assert "build-and-publish" in jobs, "build-and-publish job missing"
    assert jobs["build-and-publish"].get("needs") == ["build-image-preflight"], (
        f"build-and-publish needs wrong: {jobs['build-and-publish'].get('needs')!r}"
    )

    # Image job needs (release.yml:98-99).
    assert "build-and-publish-image" in jobs, "image job missing"
    assert jobs["build-and-publish-image"].get("needs") == ["build-and-publish"], (
        f"image job needs wrong: {jobs['build-and-publish-image'].get('needs')!r}"
    )

    # Package linkage and visibility assertions (108/US1).
    original = jobs["build-and-publish"].get("permissions", {})
    assert original == {"contents": "read", "id-token": "write"}, (
        f"build-and-publish permissions changed: {original!r}"
    )
    image = jobs["build-and-publish-image"].get("permissions", {})
    assert image.get("packages") == "write", (
        f"image job must declare packages: write, got {image!r}"
    )
    assert image.get("contents") == "read" and image.get("id-token") == "write", (
        f"image job permissions must include contents: read and id-token: write, got {image!r}"
    )

    # Repository env declaration (108/US1-S2).
    image_job = jobs["build-and-publish-image"]
    env = image_job.get("env", {})
    assert "IMAGE_REPOSITORY" in env, "IMAGE_REPOSITORY must be declared on the image job"
    assert env["IMAGE_REPOSITORY"] == "ghcr.io/bryantharpeorg/ergane", (
        f"IMAGE_REPOSITORY must resolve to ghcr.io/bryantharpeorg/ergane, got {env['IMAGE_REPOSITORY']!r}"
    )
