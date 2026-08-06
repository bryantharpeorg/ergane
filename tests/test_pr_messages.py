"""The PR body renderer: what a landed node says about itself (plan.md § US1).

A node that reached ladder PASS opens a PR that anyone can read. The title and
body are the only thing that surfaces outside the factory — into a public
repository the operator may later make public (architecture §10) — so what they
may *contain* is a security constraint, not a style choice:

- **No credential, proxy URL, or transcript path may appear.** The inputs carry
  the values (the same environs the rest of the factory runs under) and the
  renderer must drop them; a body that leaked `LITELLM_MASTER_KEY` or the
  proxy's URL into a public repo is a credential published, whatever the
  repository's visibility is today.
- **Deterministic.** Same inputs → identical bytes, every call. The body travels
  through workflow state (Temporal), so a renderer that reached for a clock or
  a random id would break replay (SC-001).

What the body *carries* is the node's public account of why it landed: the spec
reference (feature + requirement keys), the branch, the attempt count, the
per-gate results of the passing attempt, the judge's outcome (or the
`judge_unavailable` flag), and a provenance line naming who and when.

Written before `factory/mergequeue/messages.py` exists (T011 precedes T012):
until the module lands, every test here fails at import.
"""

from __future__ import annotations

import pytest

from factory.mergequeue.messages import pr_title, render_pr_body
from factory.verify.models import (
    GateResult,
    GateStatus,
    JudgeOutcome,
    JudgeVerdict,
    OutputCheck,
    OverallVerdict,
    VerificationForm,
    VerificationResult,
)

EPIC = "003-merge-queue"
NODE = "us1"
STORY_KEY = "US1"
FEATURE = "003-merge-queue"
REQUIREMENT_KEYS = ("US1", "FR-001", "FR-002")
BRANCH = f"factory/{EPIC}/{NODE}"
ATTEMPT = 1

PROXY_URL = "http://litellm.internal.example"
LITELLM_MASTER_KEY = "sk-master-top-secret"
TELEGRAM_TOKEN = "12345:AAF-secret-token"
TRANSCRIPT = f".factory/transcripts/{EPIC}/{NODE}/attempt-1"


def _passing_result() -> VerificationResult:
    return VerificationResult(
        epic_id=EPIC,
        node_id=NODE,
        attempt=ATTEMPT,
        form=VerificationForm.PHASE,
        gate_results=[
            GateResult(
                name="test",
                command="pytest -q",
                status=GateStatus.PASS,
                exit_code=0,
                duration_s=1.25,
                output_tail="1 passed",
            ),
            GateResult(
                name="lint",
                command="ruff check",
                status=GateStatus.PASS,
                exit_code=0,
                duration_s=0.5,
                output_tail="ok",
            ),
        ],
        output_check=OutputCheck(
            write_scope="target",
            has_diff=True,
            expected_artifacts=[],
            artifacts_present=None,
            passed=True,
        ),
        judge=JudgeVerdict(
            outcome=JudgeOutcome.PASS,
            findings=[],
            feedback="Meets the scenarios.",
            judge_attempt=1,
            truncated_input=False,
            model_alias="implementer",
        ),
        verdict=OverallVerdict.PASS,
        judge_unavailable=False,
        criteria_drift=False,
        criteria_sha256="a" * 64,
        spec_ref=f"{FEATURE}:{STORY_KEY}",
        started_at="2026-08-06T09:00:00Z",
        finished_at="2026-08-06T09:05:00Z",
    )


# --- the title ----------------------------------------------------------------


def test_pr_title_is_epic_node_colon_story_title() -> None:
    assert pr_title(epic_id=EPIC, node_id=NODE, story_title="Land verified work") == (
        "003-merge-queue/us1: Land verified work"
    )


# --- the body's content -------------------------------------------------------


def test_body_carries_the_spec_reference() -> None:
    body = render_pr_body(
        epic_id=EPIC,
        node_id=NODE,
        branch=BRANCH,
        attempt=ATTEMPT,
        feature=FEATURE,
        requirement_keys=REQUIREMENT_KEYS,
        result=_passing_result(),
        proxy_url=PROXY_URL,
        master_key=LITELLM_MASTER_KEY,
        telegram_token=TELEGRAM_TOKEN,
        transcript_path=TRANSCRIPT,
    )

    assert FEATURE in body
    for key in REQUIREMENT_KEYS:
        assert key in body


def test_body_carries_the_branch_and_attempt() -> None:
    body = render_pr_body(
        epic_id=EPIC,
        node_id=NODE,
        branch=BRANCH,
        attempt=ATTEMPT,
        feature=FEATURE,
        requirement_keys=REQUIREMENT_KEYS,
        result=_passing_result(),
        proxy_url=PROXY_URL,
        master_key=LITELLM_MASTER_KEY,
        telegram_token=TELEGRAM_TOKEN,
        transcript_path=TRANSCRIPT,
    )

    assert BRANCH in body
    assert f"attempt {ATTEMPT}" in body


def test_body_carries_per_gate_results_of_the_passing_attempt() -> None:
    body = render_pr_body(
        epic_id=EPIC,
        node_id=NODE,
        branch=BRANCH,
        attempt=ATTEMPT,
        feature=FEATURE,
        requirement_keys=REQUIREMENT_KEYS,
        result=_passing_result(),
        proxy_url=PROXY_URL,
        master_key=LITELLM_MASTER_KEY,
        telegram_token=TELEGRAM_TOKEN,
        transcript_path=TRANSCRIPT,
    )

    for gate in _passing_result().gate_results:
        assert gate.name in body
    assert "test" in body
    assert "lint" in body


def test_body_carries_the_judge_outcome() -> None:
    body = render_pr_body(
        epic_id=EPIC,
        node_id=NODE,
        branch=BRANCH,
        attempt=ATTEMPT,
        feature=FEATURE,
        requirement_keys=REQUIREMENT_KEYS,
        result=_passing_result(),
        proxy_url=PROXY_URL,
        master_key=LITELLM_MASTER_KEY,
        telegram_token=TELEGRAM_TOKEN,
        transcript_path=TRANSCRIPT,
    )

    assert "judge: PASS" in body


def test_body_flags_judge_unavailable() -> None:
    """A PASS reached without judge agreement must say so in the public record."""
    result = _passing_result()
    result = VerificationResult(
        epic_id=result.epic_id,
        node_id=result.node_id,
        attempt=result.attempt,
        form=result.form,
        gate_results=result.gate_results,
        output_check=result.output_check,
        judge=None,
        verdict=result.verdict,
        judge_unavailable=True,
        criteria_drift=result.criteria_drift,
        criteria_sha256=result.criteria_sha256,
        spec_ref=result.spec_ref,
        started_at=result.started_at,
        finished_at=result.finished_at,
    )
    body = render_pr_body(
        epic_id=EPIC,
        node_id=NODE,
        branch=BRANCH,
        attempt=ATTEMPT,
        feature=FEATURE,
        requirement_keys=REQUIREMENT_KEYS,
        result=result,
        proxy_url=PROXY_URL,
        master_key=LITELLM_MASTER_KEY,
        telegram_token=TELEGRAM_TOKEN,
        transcript_path=TRANSCRIPT,
    )

    assert "judge_unavailable" in body


# --- the security constraint (architecture §10) -------------------------------


def test_no_credential_proxy_url_or_transcript_path_appears() -> None:
    """A public repo's PR must not publish the factory's secrets."""
    body = render_pr_body(
        epic_id=EPIC,
        node_id=NODE,
        branch=BRANCH,
        attempt=ATTEMPT,
        feature=FEATURE,
        requirement_keys=REQUIREMENT_KEYS,
        result=_passing_result(),
        proxy_url=PROXY_URL,
        master_key=LITELLM_MASTER_KEY,
        telegram_token=TELEGRAM_TOKEN,
        transcript_path=TRANSCRIPT,
    )

    assert PROXY_URL not in body
    assert LITELLM_MASTER_KEY not in body
    assert TELEGRAM_TOKEN not in body
    assert TRANSCRIPT not in body
    assert "sk-" not in body


# --- determinism --------------------------------------------------------------


def test_same_inputs_produce_identical_bytes() -> None:
    """The body is workflow state; a clock or a random id would break replay."""
    kwargs = dict(
        epic_id=EPIC,
        node_id=NODE,
        branch=BRANCH,
        attempt=ATTEMPT,
        feature=FEATURE,
        requirement_keys=REQUIREMENT_KEYS,
        result=_passing_result(),
        proxy_url=PROXY_URL,
        master_key=LITELLM_MASTER_KEY,
        telegram_token=TELEGRAM_TOKEN,
        transcript_path=TRANSCRIPT,
    )

    first = render_pr_body(**kwargs)
    second = render_pr_body(**kwargs)

    assert first == second
