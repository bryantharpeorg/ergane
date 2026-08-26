"""US1 of epic 108-the-image-rehearses-before-it-ships: a throwaway GHCR image rehearsal.

These drift tests inspect ``.github/workflows/test-release.yml``. They are kept
separate from ``tests/test_release_path.py`` because US2 owns that file; US1
extends only the test-release workflow and adds a new test file here.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
TEST_RELEASE_WORKFLOW = WORKFLOWS_DIR / "test-release.yml"


def _load_test_release_workflow() -> dict[str, Any]:
    if not TEST_RELEASE_WORKFLOW.is_file():
        pytest.fail(f"test-release workflow not found at {TEST_RELEASE_WORKFLOW}")
    return yaml.safe_load(TEST_RELEASE_WORKFLOW.read_text(encoding="utf-8"))


def _job_ids(workflow: dict[str, Any]) -> list[str]:
    jobs = workflow.get("jobs", {})
    assert isinstance(jobs, dict), f"workflow jobs block must be a dict, got {jobs!r}"
    return list(jobs.keys())


def _rehearsal_job_text() -> str:
    """Return the raw text of the rehearsal job, starting at its id line."""
    text = TEST_RELEASE_WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r"^  build-and-publish-image-rehearsal:\s*$", text, re.MULTILINE)
    assert match is not None, "rehearsal job 'build-and-publish-image-rehearsal' not found"
    return text[match.start():]


def _bash_run_blocks(job_text: str) -> list[str]:
    """Return the body of every `run: |` block in a job's raw YAML text."""
    blocks: list[str] = []
    for match in re.finditer(r'^\s+run:\s*\|\s*\n((?:\s+.*\n?)+)', job_text, re.MULTILINE):
        blocks.append(match.group(1))
    return blocks


# --- T001 [US1] drift test over the new rehearsal job ----------------------------


def test_us1_rehearsal_job_exists_with_one_multi_arch_buildx_push() -> None:
    """FR-001, FR-002: exactly one buildx build with both platforms and --push."""
    workflow = _load_test_release_workflow()
    jobs = workflow.get("jobs", {})
    assert "build-and-publish-image-rehearsal" in jobs, (
        f"rehearsal job missing; jobs are: {list(jobs.keys())}"
    )
    job = jobs["build-and-publish-image-rehearsal"]
    assert job.get("needs") is None, (
        f"rehearsal job must not declare needs, got {job.get('needs')!r}"
    )

    job_text = _rehearsal_job_text()
    run_blocks = _bash_run_blocks(job_text)
    assert run_blocks, "no run blocks found in rehearsal job"
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


def test_us1_rehearsal_job_uses_github_token_for_ghcr_login() -> None:
    """FR-004: GHCR login resolves to the GHCR host and uses github.token."""
    job_text = _rehearsal_job_text()
    assert ("registry: ghcr.io" in job_text or "registry: ${{ env.IMAGE_REPOSITORY }}" in job_text), (
        "GHCR registry missing"
    )
    assert "password: ${{ github.token }}" in job_text, (
        "GHCR login must use github.token"
    )


def test_us1_rehearsal_job_has_own_packages_write_permission() -> None:
    """FR-004: packages: write only on the rehearsal job's own permissions block."""
    workflow = _load_test_release_workflow()
    jobs = workflow.get("jobs", {})
    assert "build-and-publish-test" in jobs, "original wheel job missing"
    assert "build-and-publish-image-rehearsal" in jobs, "rehearsal image job missing"

    original = jobs["build-and-publish-test"].get("permissions", {})
    assert original == {"contents": "read", "id-token": "write"}, (
        f"wheel job permissions must remain exactly {{contents: read, id-token: write}}, got {original!r}"
    )

    image = jobs["build-and-publish-image-rehearsal"].get("permissions", {})
    assert image.get("packages") == "write", (
        f"rehearsal image job must declare packages: write, got {image!r}"
    )
    assert image.get("contents") == "read" and image.get("id-token") == "write", (
        f"rehearsal image job permissions must include contents: read and id-token: write, got {image!r}"
    )


def test_us1_rehearsal_job_signs_pushed_digest_with_cosign() -> None:
    """FR-005: cosign signs the pushed digest, not a tag."""
    job_text = _rehearsal_job_text()
    assert "uses: sigstore/cosign-installer@v3" in job_text, "cosign-installer missing"
    cosign_lines = [
        line.strip()
        for line in job_text.splitlines()
        if line.strip().startswith("cosign sign")
    ]
    assert len(cosign_lines) == 1, f"expected exactly one cosign sign line, got {cosign_lines}"
    sign_line = cosign_lines[0]
    assert "--yes" in sign_line, f"cosign sign must be non-interactive: {sign_line}"
    assert "${DIGEST}" in sign_line or "@" in sign_line, (
        f"cosign must sign digest, got: {sign_line}"
    )
    assert ":" not in sign_line.split("@")[0] or "${IMAGE_REPOSITORY}" in sign_line, (
        f"cosign target must be repo@digest form: {sign_line}"
    )


def test_us1_rehearsal_job_inserts_platform_assertion() -> None:
    """FR-006: imagetools inspect exits non-zero unless both platforms appear."""
    job_text = _rehearsal_job_text()
    assert "docker buildx imagetools inspect" in job_text, "imagetools inspect step missing"
    assert "linux/amd64" in job_text and "linux/arm64" in job_text, (
        "platform assertion must name both linux/amd64 and linux/arm64"
    )
    assert "exit 1" in job_text, "platform assertion must be able to exit 1"


# --- T002 [P] tag grammar --------------------------------------------------------


def test_us1_rehearsal_tag_uses_run_id_with_rehearsal_prefix() -> None:
    """FR-003 positive: tag derives from github.run_id and starts with 'rehearsal-'."""
    job_text = _rehearsal_job_text()
    assert "rehearsal-${{ github.run_id }}" in job_text, (
        "rehearsal tag must be rehearsal-${{ github.run_id }}"
    )


def test_us1_rehearsal_job_emits_no_semver_tag_and_no_latest() -> None:
    """FR-003 negative: no emitted tag matches semver, and no 'latest' reference."""
    job_text = _rehearsal_job_text()
    assert "latest" not in job_text, "rehearsal job must not reference 'latest'"
    # Tags emitted to docker/buildx must not look like a release version.
    for match in re.finditer(r'--tag\s+["\']?(?:\$\{[^}]+\}|\$\{\{[^}]+\}|[^\s"\']+)', job_text):
        tag_arg = match.group(0)
        # Strip leading --tag and whitespace/quotes.
        emitted = re.sub(r'^--tag\s+["\']?', "", tag_arg)
        assert not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", emitted), (
            f"rehearsal job emits a semver-looking tag: {emitted!r}"
        )
    # Also reject GITHUB_REF_NAME-derived tags (the release job form) in this job.
    assert "GITHUB_REF_NAME" not in job_text, (
        "rehearsal job must not derive tag from a version tag source"
    )


# --- T003 [P] permissions containment ---------------------------------------------


def test_us1_wheel_job_permissions_unchanged() -> None:
    """FR-004: wheel job still holds only contents:read + id-token:write."""
    workflow = _load_test_release_workflow()
    original = workflow.get("jobs", {}).get("build-and-publish-test", {}).get("permissions", {})
    assert original == {"contents": "read", "id-token": "write"}, (
        f"wheel job permissions must be exactly {{contents: read, id-token: write}}, got {original!r}"
    )


# --- T004 [P] trigger non-widening ----------------------------------------------


def test_us1_test_release_trigger_is_workflow_dispatch_only() -> None:
    """FR-008: on: block is workflow_dispatch and nothing else."""
    workflow = _load_test_release_workflow()
    on_block = workflow.get("on")
    assert on_block == {"workflow_dispatch": None}, (
        f"test-release.yml on: block must be exactly workflow_dispatch, got {on_block!r}"
    )


# --- T005 [P] credential documentation ------------------------------------------


def test_us1_rehearsal_job_documents_credential_source() -> None:
    """FR-010: comment names github.token and denies a stored registry secret."""
    job_text = _rehearsal_job_text()
    # Collect the comment block immediately before the rehearsal job's permissions.
    lines_before = job_text[:job_text.find("permissions:")].splitlines()
    comments = [line.strip() for line in lines_before if line.strip().startswith("#")]
    comment_block = " ".join(comments)
    assert "github.token" in comment_block, (
        "rehearsal job comment must mention github.token"
    )
    assert "no registry secret" in comment_block.lower() or "none is stored" in comment_block.lower(), (
        "rehearsal job comment must state that no registry secret is stored in this repository"
    )


# --- T006 [P] package read-back: linkage, visibility, and no second literal ------


def test_us1_rehearsal_job_reads_back_package_linkage() -> None:
    """FR-018: job reads the package from GitHub API and asserts linked repository."""
    job_text = _rehearsal_job_text()
    assert "gh api" in job_text, "job must call gh api to read the package"
    assert "github.repository" in job_text, (
        "linkage assertion must compare against github.repository"
    )
    assert "LINKED" in job_text or "repository.full_name" in job_text, (
        "linkage assertion must expose the observed linked repository"
    )
    assert "exit 1" in job_text, "linkage assertion must be able to fail the job"


def test_us1_rehearsal_job_reads_back_package_visibility() -> None:
    """FR-019: job asserts the package visibility is public and names the remedy."""
    job_text = _rehearsal_job_text()
    assert "visibility" in job_text, "visibility assertion must read .visibility"
    assert '"public"' in job_text or "'public'" in job_text, (
        "visibility assertion must compare against the literal public"
    )
    assert "settings" in job_text.lower(), (
        "visibility failure must name the package settings page"
    )
    assert "exit 1" in job_text, "visibility assertion must be able to fail the job"


def test_us1_rehearsal_job_uses_no_hardcoded_owner_or_package_name() -> None:
    """FR-020: org/package come from IMAGE_REPOSITORY and github.repository_owner."""
    job_text = _rehearsal_job_text()
    # The single IMAGE_REPOSITORY declaration is allowed; every other reference must
    # go through the env variable or github.repository_owner / github.repository.
    repo_lines = [
        line
        for line in job_text.splitlines()
        if ("bryantharpeorg" in line or "ergane" in line)
    ]
    allowed = [
        line
        for line in repo_lines
        if "IMAGE_REPOSITORY:" in line and "ghcr.io/bryantharpeorg/ergane" in line
    ]
    non_declarations = [line for line in repo_lines if line not in allowed]
    assert not non_declarations, (
        f"rehearsal job must not hardcode owner/package outside IMAGE_REPOSITORY: {non_declarations}"
    )
