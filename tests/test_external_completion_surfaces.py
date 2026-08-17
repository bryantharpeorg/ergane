"""US2: every surface says a node was built externally.

Tests for the four surfaces named in FR-006:
1. `ergane build status` shows provenance beside the node's state.
2. The PR body — and therefore a squash-merge landing commit — carries a
   `Provenance-by:` trailer naming the external author.
3. The PR body states the work was completed externally and that the ladder was
   exhausted.
4. A `state: landed` spec attestation can state the spec contains
   externally-completed work.

Plus the negative case: an agent-completed node carries none of these markings.

Every store is created under `tmp_path` (trap 7).
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

import pytest

from factory.cli.nouns.build import render_status
from factory.mergequeue.messages import render_pr_body
from factory.verify.models import (
    GateResult,
    GateStatus,
    OutputCheck,
    OverallVerdict,
    VerificationForm,
    VerificationResult,
)
from factory.workgraph.cli import landed_command
from factory.workgraph.landed import LandedFact, LandedKind, landed_facts
from factory.workgraph.workflow import NodeState

EPIC = "external-completion"
NODE = "us1"
BRANCH = f"factory/{EPIC}/{NODE}"
PROVENANCE = "operator:manual-2026-08-17"


def _passing_result(*, provenance: str | None = None) -> VerificationResult:
    return VerificationResult(
        epic_id=EPIC,
        node_id=NODE,
        attempt=2,
        form=VerificationForm.PHASE,
        gate_results=[
            GateResult(
                name="test",
                command="uv run pytest -q",
                status=GateStatus.PASS,
                exit_code=0,
                duration_s=8.0,
                output_tail="12 passed",
            )
        ],
        output_check=OutputCheck(
            write_scope="worktree",
            has_diff=True,
            expected_artifacts=[],
            artifacts_present=None,
            passed=True,
        ),
        judge=None,
        verdict=OverallVerdict.PASS,
        judge_unavailable=False,
        criteria_drift=False,
        criteria_sha256="a" * 64,
        spec_ref=f"{EPIC}:US1",
        started_at="2026-08-17T00:00:00Z",
        finished_at="2026-08-17T00:05:00Z",
        provenance=provenance,
    )


def test_status_row_states_external_completion() -> None:
    """An externally-completed node says so in `ergane build status`."""
    document: dict[str, Any] = {
        "epic_state": "COMPLETED",
        "nodes": {
            NODE: {
                "state": NodeState.MERGED,
                "attempt": 2,
                "branch": BRANCH,
                "provenance": PROVENANCE,
            }
        },
    }
    rendered = render_status(EPIC, document, "COMPLETED")
    assert PROVENANCE in rendered
    assert "external completion" in rendered.lower()


def test_pr_body_states_external_completion_and_exhausted_ladder() -> None:
    """The PR body names the external author and says the ladder was exhausted."""
    body = render_pr_body(
        epic_id=EPIC,
        node_id=NODE,
        branch=BRANCH,
        attempt=2,
        feature=EPIC,
        requirement_keys=("US1",),
        result=_passing_result(provenance=PROVENANCE),
        proxy_url="http://proxy.test",
        master_key="sk-secret",
        telegram_token="123:secret",
        transcript_path="/tmp/transcript",
    )
    assert f"Provenance-by: {PROVENANCE}" in body
    assert "completed externally" in body.lower()
    assert "node's ladder was exhausted" in body.lower()


def test_landing_commit_carries_provenance_trailer(tmp_path: Path) -> None:
    """A squash-merge commit built from the PR body carries the trailer."""
    body = render_pr_body(
        epic_id=EPIC,
        node_id=NODE,
        branch=BRANCH,
        attempt=2,
        feature=EPIC,
        requirement_keys=("US1",),
        result=_passing_result(provenance=PROVENANCE),
        proxy_url="http://proxy.test",
        master_key="sk-secret",
        telegram_token="123:secret",
        transcript_path="/tmp/transcript",
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(tmp_path / "home"),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": "Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@ergane.invalid",
        "GIT_COMMITTER_NAME": "Fixture",
        "GIT_COMMITTER_EMAIL": "fixture@ergane.invalid",
        "GIT_TERMINAL_PROMPT": "0",
    }
    home = tmp_path / "home"
    home.mkdir()
    env["HOME"] = str(home)
    subprocess.run(["git", "-C", str(repo), "init", "-b", "main", "--quiet"], env=env, check=True)
    (repo / "file.txt").write_text("hello", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], env=env, check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "--quiet", "-F", "-"],
        input=body,
        env=env,
        check=True,
        text=True,
    )
    log = subprocess.run(
        ["git", "-C", str(repo), "log", "-1", "--format=%B"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert f"Provenance-by: {PROVENANCE}" in log
    # interpret-trailers sees it as a trailer
    trailers = subprocess.run(
        ["git", "-C", str(repo), "log", "-1", "--format=%(trailers)"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "Provenance-by:" in trailers


def _build_spec_repo(tmp_path: Path, *, external_completion: bool | None = None) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(tmp_path / "home"),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": "Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@ergane.invalid",
        "GIT_COMMITTER_NAME": "Fixture",
        "GIT_COMMITTER_EMAIL": "fixture@ergane.invalid",
        "GIT_TERMINAL_PROMPT": "0",
    }
    home = tmp_path / "home"
    home.mkdir()
    env["HOME"] = str(home)
    subprocess.run(["git", "-C", str(repo), "init", "-b", "main", "--quiet"], env=env, check=True)
    spec_dir = repo / "specs" / EPIC
    spec_dir.mkdir(parents=True)
    front = "---\nstate: landed\n"
    if external_completion is not None:
        front += f"external_completion: {str(external_completion).lower()}\n"
    front += "---\n"
    body = "# Feature\n\n## Requirements\n\n- **FR-001**: The system MUST do one thing.\n\n### User Story 1 - Title (Priority: P1)\n\nAs the operator, I want this.\n\n**Acceptance Scenarios**:\n1. **Given** a thing, **When** I act, **Then** it works.\n\n## Work Graph\n\n```yaml\nUS1:\n  depends_on: []\n  implements: [FR-001]\n```\n"
    (spec_dir / "spec.md").write_text(front + body, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], env=env, check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "--quiet", "-m", "landed attestation"], env=env, check=True)
    return repo


def test_attestation_states_external_completion(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    """A `state: landed` attestation can say the spec contains externally-completed work."""
    repo = _build_spec_repo(tmp_path, external_completion=True)
    facts = landed_facts(repo, EPIC, default_branch="main")
    assert facts == {
        "US1": LandedFact(
            story_key="US1",
            commit=facts["US1"].commit,
            kind=LandedKind.ATTESTED,
            external_completion=True,
        )
    }
    class Args:
        spec_dir = str(repo / "specs" / EPIC)
        default_branch = "main"
        as_json = False
    landed_command(Args())
    out = capsys.readouterr().out
    assert "external completion" in out.lower()


# --- T012: negative case ------------------------------------------------------


def test_agent_completed_status_row_omits_external_marking() -> None:
    """An agent-completed node does not mention external completion in status."""
    document: dict[str, Any] = {
        "epic_state": "COMPLETED",
        "nodes": {
            NODE: {
                "state": NodeState.MERGED,
                "attempt": 1,
                "branch": BRANCH,
                "provenance": None,
            }
        },
    }
    rendered = render_status(EPIC, document, "COMPLETED")
    assert "external completion" not in rendered.lower()
    assert "Provenance-by" not in rendered


def test_agent_completed_pr_body_omits_provenance_trailer() -> None:
    """An agent-completed PR body has no provenance trailer."""
    body = render_pr_body(
        epic_id=EPIC,
        node_id=NODE,
        branch=BRANCH,
        attempt=1,
        feature=EPIC,
        requirement_keys=("US1",),
        result=_passing_result(provenance=None),
        proxy_url="http://proxy.test",
        master_key="sk-secret",
        telegram_token="123:secret",
        transcript_path="/tmp/transcript",
    )
    assert "Provenance-by" not in body
    assert "completed externally" not in body.lower()


def test_agent_completed_landing_commit_has_no_provenance_trailer(tmp_path: Path) -> None:
    """A squash-merge commit from an agent-completed PR body has no provenance trailer."""
    body = render_pr_body(
        epic_id=EPIC,
        node_id=NODE,
        branch=BRANCH,
        attempt=1,
        feature=EPIC,
        requirement_keys=("US1",),
        result=_passing_result(provenance=None),
        proxy_url="http://proxy.test",
        master_key="sk-secret",
        telegram_token="123:secret",
        transcript_path="/tmp/transcript",
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(tmp_path / "home"),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": "Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@ergane.invalid",
        "GIT_COMMITTER_NAME": "Fixture",
        "GIT_COMMITTER_EMAIL": "fixture@ergane.invalid",
        "GIT_TERMINAL_PROMPT": "0",
    }
    home = tmp_path / "home"
    home.mkdir()
    env["HOME"] = str(home)
    subprocess.run(["git", "-C", str(repo), "init", "-b", "main", "--quiet"], env=env, check=True)
    (repo / "file.txt").write_text("hello", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], env=env, check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "--quiet", "-F", "-"],
        input=body,
        env=env,
        check=True,
        text=True,
    )
    trailers = subprocess.run(
        ["git", "-C", str(repo), "log", "-1", "--format=%(trailers)"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "Provenance-by" not in trailers


def test_attestation_without_external_completion_is_silent(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    """A plain `state: landed` attestation does not claim external completion."""
    repo = _build_spec_repo(tmp_path, external_completion=None)
    facts = landed_facts(repo, EPIC, default_branch="main")
    assert facts["US1"].external_completion is None
    class Args:
        spec_dir = str(repo / "specs" / EPIC)
        default_branch = "main"
        as_json = False
    landed_command(Args())
    out = capsys.readouterr().out
    assert "external completion" not in out.lower()
