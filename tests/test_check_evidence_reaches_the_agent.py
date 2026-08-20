"""US1: a recovery agent is told which test failed.

These tests exercise the path from `gh` through the forge to the assembled
recovery prompt. The defect they guard is that the old `gh pr checks --json`
command is not accepted by the real `gh` binary, so the prompt never carried an
actual log. A permissive fake answered every scripted argv and hid that; the
strict fake below refuses any argv the real `gh` would refuse.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Sequence

import pytest
from temporalio.testing import ActivityEnvironment

from factory.activities import merge_activities
from factory.mergequeue.gh import GhClient
from factory.mergequeue.github_forge import GithubForge, degraded_path_records
from factory.mergequeue.models import (
    CheckFailure,
    ObservedOutcome,
    QueueOutcome,
)
from factory.workgraph.models import WorkNode
from factory.workgraph.prompt import LandingEvidence, build_attempt_prompt
from tests.fake_gh import FakeGh, FakeGhResult, RecordedInvocation

EPIC = "071-a-red-check-tells-the-agent-what-broke"
NODE = "us1"
PR_NUMBER = 226
TARGET = "/srv/target"


@pytest.fixture
def env() -> ActivityEnvironment:
    return ActivityEnvironment()


class StrictFakeGh(FakeGh):
    """A scripted `gh` that also refuses argv the real binary would refuse.

    The real `gh` rejects unknown flags during argument parsing, before it
    authenticates or resolves a repository. By running the same argv with no
    token in a directory that is not a repository, we can distinguish "flag
    accepted, needs auth" (exit 4 / auth message) from "flag refused" (usage
    or unknown-flag error). Only the latter is raised here.
    """

    def __call__(self, argv: Sequence[str], cwd: str) -> FakeGhResult:
        self._assert_gh_would_accept(argv)
        return super().__call__(argv, cwd)

    def _assert_gh_would_accept(self, argv: Sequence[str]) -> None:
        env = os.environ.copy()
        env.update({"GH_TOKEN": "", "GIT_TERMINAL_PROMPT": "0"})
        try:
            completed = subprocess.run(
                ["gh", *argv],
                cwd="/tmp",
                capture_output=True,
                text=True,
                env=env,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            # No `gh` binary to validate against: fail loudly rather than
            # silently accept a possibly-invalid argv.
            raise AssertionError(f"could not run gh to validate {argv!r}: {exc}") from exc

        stderr = (completed.stderr or completed.stdout or "").lower()
        if (
            "unknown flag" in stderr
            or "unknown command" in stderr
            or ("usage:" in stderr and completed.returncode != 0)
        ):
            raise AssertionError(
                f"real gh would refuse argv {argv!r}: "
                f"{completed.stderr or completed.stdout}"
            )


# --- helpers -----------------------------------------------------------------


def _github_forge(fake: FakeGh) -> GithubForge:
    return GithubForge(GhClient(repo=TARGET, runner=fake))


def _pr_view_payload(*checks: dict[str, Any]) -> dict[str, Any]:
    return {"statusCheckRollup": list(checks)}


def _check_run(
    name: str,
    conclusion: str,
    details_url: str,
) -> dict[str, Any]:
    return {
        "__typename": "CheckRun",
        "name": name,
        "conclusion": conclusion,
        "detailsUrl": details_url,
    }


def _status_context(
    context: str,
    state: str,
    target_url: str,
) -> dict[str, Any]:
    return {
        "__typename": "StatusContext",
        "context": context,
        "state": state,
        "targetUrl": target_url,
    }




def test_gather_evidence_through_strict_fake_returns_name_url_and_log() -> None:
    """S1: a strict fake refuses the old argv and the new one returns a log."""
    fake = StrictFakeGh()
    fake.expect_json(
        "pr",
        "view",
        str(PR_NUMBER),
        "--json",
        "statusCheckRollup",
        payload=_pr_view_payload(
            _check_run(
                name="test",
                conclusion="FAILURE",
                details_url="https://github.com/acme/target/actions/runs/101/job/202",
            )
        ),
    )
    fake.expect(
        "run",
        "view",
        "101",
        "--log-failed",
        stdout="FAILED tests/test_calc.py::test_add\nmore\n",
    )
    forge = _github_forge(fake)

    evidence = forge.failing_check_evidence(PR_NUMBER, ("test",))

    assert len(evidence) == 1
    assert evidence[0] == CheckFailure(
        name="test",
        url="https://github.com/acme/target/actions/runs/101/job/202",
        log_tail="FAILED tests/test_calc.py::test_add\nmore\n",
        note="",
    )
    assert all(
        c.args[:4] != ("pr", "checks", str(PR_NUMBER), "--json")
        for c in fake.calls
    )


# --- T002: the assembled prompt string contains the log text -------------------


def test_recovery_prompt_contains_the_log_tail() -> None:
    """S2: the prompt the agent receives quotes the failing log verbatim."""
    log_tail = "FAILED tests/test_calc.py::test_add\nmore\n"
    evidence = LandingEvidence(
        outcome=QueueOutcome.CHECKS_FAILED,
        queue_history=(
            ObservedOutcome(
                at="2026-08-19T10:00:00Z",
                outcome=QueueOutcome.CHECKS_FAILED,
                failing_checks=("test",),
            ),
        ),
        failing_checks=(
            CheckFailure(
                name="test",
                url="https://github.com/acme/target/actions/runs/101/job/202",
                log_tail=log_tail,
                note="",
            ),
        ),
    )
    node = WorkNode(
        id="us1",
        story_key="US1",
        persona="implementer",
        spec_ref="specs/071-a-red-check-tells-the-agent-what-broke/spec.md",
        requirement_keys=["US1"],
        depends_on=[],
    )

    prompt = build_attempt_prompt(
        node=node,
        epic_id=EPIC,
        spec_text="### User Story 1 - A recovery agent is told which test failed\nStory body.\n",
        plan_text="## Plan\nImplementation plan.\n",
        tasks_text="## Phase 1: User Story 1 - A recovery agent is told which test failed\nTasks.\n",
        landing_evidence=evidence,
    )

    assert "Failing required checks" in prompt
    assert "FAILED tests/test_calc.py::test_add" in prompt
    assert "more" in prompt
    assert "log unavailable" not in prompt.lower()


# --- T003: genuine forge failure still degrades -------------------------------


def test_genuine_forge_failure_returns_degraded_note() -> None:
    """S3: a network/auth/delete failure degrades with a named reason."""
    fake = StrictFakeGh()
    fake.expect(
        "pr",
        "view",
        str(PR_NUMBER),
        "--json",
        "statusCheckRollup",
        stderr="gh: HTTP 503 Service Unavailable",
        returncode=1,
    )
    forge = _github_forge(fake)

    evidence = forge.failing_check_evidence(PR_NUMBER, ("test",))

    assert len(evidence) == 1
    assert evidence[0].name == "test"
    assert evidence[0].log_tail == ""
    assert "unavailable" in evidence[0].note.lower()
    assert "GH_REFUSED" in evidence[0].note


# --- T004: per-check degradation stays per-check ------------------------------


def test_per_check_degradation_is_isolated() -> None:
    """S5: one unparseable link degrades; the other check still returns its log."""
    fake = StrictFakeGh()
    fake.expect_json(
        "pr",
        "view",
        str(PR_NUMBER),
        "--json",
        "statusCheckRollup",
        payload=_pr_view_payload(
            _check_run(
                name="test",
                conclusion="FAILURE",
                details_url="https://github.com/acme/target/actions/runs/101/job/202",
            ),
            _status_context(
                context="lint",
                state="FAILURE",
                target_url="https://github.com/acme/target/checks",
            ),
        ),
    )
    fake.expect(
        "run",
        "view",
        "101",
        "--log-failed",
        stdout="FAILED tests/test_lint.py::test_lint\n",
    )
    forge = _github_forge(fake)

    evidence = forge.failing_check_evidence(PR_NUMBER, ("test", "lint"))

    assert len(evidence) == 2
    by_name = {e.name: e for e in evidence}
    assert by_name["test"].log_tail == "FAILED tests/test_lint.py::test_lint\n"
    assert by_name["test"].note == ""
    assert by_name["lint"].log_tail == ""
    assert by_name["lint"].url == "https://github.com/acme/target/checks"
    assert "run id" in by_name["lint"].note.lower()


# --- T005: degraded path is recorded without reading a transcript ------------


def test_degraded_path_is_recorded() -> None:
    """S4: a degraded fetch leaves a record an operator can read."""
    fake = StrictFakeGh()
    fake.expect(
        "pr",
        "view",
        str(PR_NUMBER),
        "--json",
        "statusCheckRollup",
        stderr="gh: HTTP 503 Service Unavailable",
        returncode=1,
    )
    forge = _github_forge(fake)

    before = len(degraded_path_records())
    forge.failing_check_evidence(PR_NUMBER, ("test",))
    records = degraded_path_records()[before:]

    assert len(records) == 1
    assert records[0][0] == "test"
    assert "GH_REFUSED" in records[0][1]


# --- T006: rollup shape mapping degrades unknown entries per-check -------------


def test_pr_checks_maps_check_runs_and_status_contexts_and_skips_unknowns() -> None:
    """S6/Assumptions: handle the shapes that occur and degrade unknowns."""
    fake = FakeGh()
    fake.expect_json(
        "pr",
        "view",
        str(PR_NUMBER),
        "--json",
        "statusCheckRollup",
        payload=_pr_view_payload(
            _check_run(
                name="test",
                conclusion="FAILURE",
                details_url="https://github.com/acme/target/actions/runs/101/job/202",
            ),
            _status_context(
                context="lint",
                state="FAILURE",
                target_url="https://github.com/acme/target/checks/lint",
            ),
            {"__typename": "UnknownShape"},
        ),
    )
    client = GhClient(repo=TARGET, runner=fake)

    checks = client.pr_checks(PR_NUMBER)

