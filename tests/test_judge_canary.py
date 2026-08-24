"""Tests for the judge canary (spec 103 US3, FR-005).

The canary asks a single alias "can this model judge?" with a committed toy
diff, acceptance criteria and a required JSON verdict schema.  A well-formed FAIL
verdict on the known-bad diff passes; prose, schema violation, or a PASS
verdict each fail with a distinct reason.

Suite output after implementation:

.. code-block:: text

    placeholder — will be updated after the first run.
"""

from __future__ import annotations

from typing import Any

import pytest

from factory.controlplane.canary import probe as canary_probe
from factory.controlplane.canary.diff import (
    CANARY_CRITERIA,
    KNOWN_BAD_DIFF,
    VERDICT_SCHEMA,
)
from factory.controlplane.canary.probe import (
    CanaryResult,
    judge_canary,
    probe_judge_canary,
)
from factory.usage.litellm_client import LiteLLMClient


class _RecordingLiteLLMClient:
    """LiteLLM seam that records requests and returns canned responses.

    This is the same shape the production ``LLMProbe`` client seam expects
    (``factory/controlplane/verify.py:340``): a client with
    ``chat_completion`` and ``aclose``.
    """

    def __init__(self, response_content: str | dict[str, Any] | None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._response_content = response_content

    async def chat_completion(self, request: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(request)
        if isinstance(self._response_content, dict):
            return self._response_content
        return {"choices": [{"message": {"content": self._response_content}}]}

    async def aclose(self) -> None:
        pass


# ---------------------------------------------------------------------------
# T009 [US3-S1] canned schema-valid FAIL verdict on known-bad diff: pass
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_judge_canary_passes_on_valid_fail_verdict() -> None:
    """US3-S1: a canned schema-valid FAIL verdict on the known-bad diff passes."""
    content = '{"verdict": "FAIL", "reason": "beat() no longer returns a string"}'
    client = _RecordingLiteLLMClient(content)

    result = await judge_canary("judge-alias", client)

    assert result.passed is True, result.detail
    assert result.alias == "judge-alias"
    assert "passed" in result.detail.lower()
    assert "schema-valid" in result.detail.lower() or "fail" in result.detail.lower()


# ---------------------------------------------------------------------------
# T010 [US3-S2] prose, schema violation, PASS-on-bad: three distinct reasons
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_judge_canary_fails_on_prose() -> None:
    """US3-S2a: a prose answer fails with a reason naming the JSON check."""
    client = _RecordingLiteLLMClient("I think this change is bad because it returns False.")

    result = await judge_canary("judge-alias", client)

    assert result.passed is False
    assert result.alias == "judge-alias"
    lowered = result.detail.lower()
    assert "json" in lowered or "not valid json" in lowered


@pytest.mark.asyncio
async def test_judge_canary_fails_on_schema_violation() -> None:
    """US3-S2b: a schema-invalid object fails with a reason naming the schema."""
    # Missing required `reason` and has an extra field.
    content = '{"verdict": "FAIL", "extra": "surprise"}'
    client = _RecordingLiteLLMClient(content)

    result = await judge_canary("judge-alias", client)

    assert result.passed is False
    lowered = result.detail.lower()
    assert "reason" in lowered or "missing" in lowered or "required" in lowered


@pytest.mark.asyncio
async def test_judge_canary_fails_on_pass_verdict_for_known_bad_diff() -> None:
    """US3-S2c: a PASS verdict on the known-bad diff fails naming the verdict."""
    content = '{"verdict": "PASS", "reason": "looks fine"}'
    client = _RecordingLiteLLMClient(content)

    result = await judge_canary("judge-alias", client)

    assert result.passed is False
    lowered = result.detail.lower()
    assert "verdict" in lowered
    assert "pass" in lowered or "expected 'fail'" in lowered


@pytest.mark.asyncio
async def test_judge_canary_failure_reasons_are_distinct() -> None:
    """US3-S2: prose, schema violation and PASS-on-bad produce three distinct reasons."""
    prose_client = _RecordingLiteLLMClient("This is prose, not JSON.")
    schema_client = _RecordingLiteLLMClient('{"verdict": "PASS", "unknown": 1}')
    pass_client = _RecordingLiteLLMClient('{"verdict": "PASS", "reason": "nope"}')

    prose_result = await judge_canary("judge-alias", prose_client)
    schema_result = await judge_canary("judge-alias", schema_client)
    pass_result = await judge_canary("judge-alias", pass_client)

    reasons = {prose_result.detail, schema_result.detail, pass_result.detail}
    assert len(reasons) == 3, f"expected 3 distinct reasons, got {reasons}"


# ---------------------------------------------------------------------------
# T011 [US3-S3] injected client's observed calls show key discipline + max_tokens
# ---------------------------------------------------------------------------


class _KeyDisciplineRecordingClient:
    """Fake LiteLLM admin client that records every key-management call.

    The canary's key-discipline wrapper (``probe_judge_canary``) must mint,
    confirm the model constraint, read spend logs, and revoke in a ``finally``.
    This client lets the test observe all of those calls and assert on the
    request shape.
    """

    def __init__(self, *, chat_response_content: str | dict[str, Any] | None = None) -> None:
        self.chat_completion_calls: list[dict[str, Any]] = []
        self.issue_key_calls: list[dict[str, Any]] = []
        self.get_key_info_calls: list[str] = []
        self.fetch_spend_log_rows_calls: list[tuple[str, str]] = []
        self.revoke_key_by_tokens_calls: list[list[str]] = []
        self.aclose_calls: list[None] = []
        self._chat_response_content = chat_response_content

    async def chat_completion(self, request: dict[str, Any]) -> dict[str, Any]:
        self.chat_completion_calls.append(request)
        if isinstance(self._chat_response_content, dict):
            return self._chat_response_content
        return {"choices": [{"message": {"content": self._chat_response_content}}]}

    async def issue_key(
        self,
        *,
        key_alias: str,
        models: list[str],
        metadata: dict[str, Any] | None = None,
        ttl: str | None = None,
    ) -> str:
        self.issue_key_calls.append(
            {"key_alias": key_alias, "models": list(models), "metadata": metadata, "ttl": ttl}
        )
        return "sk-canary-minted"

    async def get_key_info(self, key: str) -> dict[str, Any]:
        self.get_key_info_calls.append(key)
        return {
            "key": key,
            "info": {
                "key_alias": "judge-canary-probe",
                "models": ["judge-alias"],
                "metadata": {},
                "spend": 0.0,
            },
        }

    async def fetch_spend_log_rows(self, key: str, *, issued_at: str) -> list[dict[str, Any]]:
        self.fetch_spend_log_rows_calls.append((key, issued_at))
        return []

    async def revoke_key_by_tokens(self, keys: list[str]) -> bool:
        self.revoke_key_by_tokens_calls.append(list(keys))
        return True

    async def aclose(self) -> None:
        self.aclose_calls.append(None)


@pytest.mark.asyncio
async def test_probe_judge_canary_mints_constrained_key_and_revokes_in_finally() -> None:
    """US3-S3: the canary wrapper applies the LLMProbe key discipline (verify.py:420-460).

    Asserts: a short-TTL key is minted constrained to the alias, /key/info is
    read, spend logs are fetched, the canary chat runs, and the key is revoked
    in a ``finally`` block even if the canary fails.
    """
    failing_client = _KeyDisciplineRecordingClient(
        chat_response_content=" prose answer that is not JSON ",
    )

    async def _factory() -> _KeyDisciplineRecordingClient:
        return failing_client

    result = await probe_judge_canary("judge-alias", client_factory=_factory)

    # The key-management proof should still pass even though the canary itself
    # fails; the failure must come from the judge, not from key discipline.
    assert len(failing_client.issue_key_calls) == 1
    issue_call = failing_client.issue_key_calls[0]
    assert issue_call["key_alias"] == "ergane-judge-canary-probe"
    assert issue_call["models"] == ["judge-alias"]
    assert issue_call["ttl"] == "5m"

    assert len(failing_client.get_key_info_calls) == 1
    assert failing_client.get_key_info_calls[0] == "sk-canary-minted"

    assert len(failing_client.fetch_spend_log_rows_calls) == 1
    assert failing_client.fetch_spend_log_rows_calls[0][0] == "sk-canary-minted"

    assert len(failing_client.revoke_key_by_tokens_calls) == 1
    assert failing_client.revoke_key_by_tokens_calls[0] == ["sk-canary-minted"]

    assert len(failing_client.aclose_calls) == 1

    # The overall result is a canary failure, but the detail names the verdict
    # check, not a key-management error.
    assert result.passed is False
    assert result.alias == "judge-alias"
    assert "judge canary passed under key discipline" not in result.detail.lower()
    assert "json" in result.detail.lower()


@pytest.mark.asyncio
async def test_probe_judge_canary_passes_when_canary_and_key_discipline_succeed() -> None:
    """US3-S1/S3: when both key discipline and the canary verdict pass, the wrapper passes."""
    passing_client = _KeyDisciplineRecordingClient(
        chat_response_content='{"verdict": "FAIL", "reason": "beat() returns a boolean"}',
    )

    async def _factory() -> _KeyDisciplineRecordingClient:
        return passing_client

    result = await probe_judge_canary("judge-alias", client_factory=_factory)

    assert result.passed is True
    assert result.alias == "judge-alias"
    assert "judge canary passed under key discipline" in result.detail.lower()

    assert len(passing_client.issue_key_calls) == 1
    assert passing_client.issue_key_calls[0]["models"] == ["judge-alias"]
    assert len(passing_client.revoke_key_by_tokens_calls) == 1
    assert passing_client.revoke_key_by_tokens_calls[0] == ["sk-canary-minted"]
    assert len(passing_client.aclose_calls) == 1


@pytest.mark.asyncio
async def test_judge_canary_uses_generous_max_tokens() -> None:
    """US3-S3: the canary requests a generous explicit max_tokens (trap 5)."""
    content = '{"verdict": "FAIL", "reason": "broken"}'
    client = _RecordingLiteLLMClient(content)

    await judge_canary("judge-alias", client)

    assert len(client.calls) == 1
    request = client.calls[0]
    assert request.get("max_tokens") == canary_probe.CANARY_MAX_TOKENS
    assert canary_probe.CANARY_MAX_TOKENS >= 100


@pytest.mark.asyncio
async def test_judge_canary_request_contains_diff_and_criteria() -> None:
    """US3-S3: the canary prompt carries the committed diff, criteria and schema."""
    content = '{"verdict": "FAIL", "reason": "broken"}'
    client = _RecordingLiteLLMClient(content)

    await judge_canary("judge-alias", client)

    assert len(client.calls) == 1
    request = client.calls[0]
    message = request["messages"][0]["content"]
    assert KNOWN_BAD_DIFF in message
    for criterion in CANARY_CRITERIA:
        assert criterion in message
    assert '"verdict"' in message
    assert '"FAIL"' in message


@pytest.mark.asyncio
async def test_judge_canary_does_not_reissue_keys_itself() -> None:
    """US3-S3: the canary entry point makes exactly one chat completion; the caller
    (the install interview via the existing probe seam) owns minting and
    revocation.
    """
    content = '{"verdict": "FAIL", "reason": "broken"}'
    client = _RecordingLiteLLMClient(content)

    await judge_canary("judge-alias", client)

    assert len(client.calls) == 1
    assert client.calls[0].get("model") == "judge-alias"
