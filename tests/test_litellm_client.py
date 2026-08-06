"""The LiteLLM admin client's contract, pinned against the fake proxy.

This is the only module that talks to the proxy, so the invariants that would
otherwise be spread across the component are asserted here, once:

- **No cap is ever sent.** Budget enforcement is deferred (D-021), so
  `/key/generate` carries an alias, a model list and a TTL — and nothing that
  could stop an agent mid-run (FR-004). The fake 400s on `max_budget`, but the
  request body is inspected directly too: a cap must be absent, not rejected.
- **The master key stays out of everything the caller can see.** A failed call
  raises `LiteLLMError` carrying the HTTP status and no credential, on the
  authentication path especially — where the wrong key is right there in the
  request (FR-009, SC-004).
- **Reads are complete and writes are tolerant.** Teardown aggregates from spend
  logs, so pagination must drain every page or usage silently under-reports;
  revocation runs last and may find the key already gone, so 404 is success
  (R2, R3, FR-002).

Written before `factory/usage/litellm_client.py` exists (T010 precedes T011):
until the client lands, every test here fails at import.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

import httpx
import pytest

from factory.usage.litellm_client import (
    DEFAULT_KEY_TTL,
    LiteLLMClient,
    LiteLLMError,
    hashed_token,
)
from tests.conftest import FakeLiteLLM

ALIAS = "epic-7:node-3:2:implementer"
MODELS = ["anthropic/CHANGEME", "local/CHANGEME"]

#: When the standard attempt's key was minted — the spend-log window's anchor.
ISSUED_AT = "2026-08-05T09:30:00Z"

#: The attribution dimensions mirrored into key metadata (R1). LiteLLM does not
#: copy these into spend rows — teardown re-supplies them — but they make the
#: key self-describing on the proxy side.
DIMENSIONS: dict[str, Any] = {
    "node_id": "node-3",
    "epic_id": "epic-7",
    "attempt": 2,
    "persona": "implementer",
    "spec_ref": "add-usage-tracking/ledger-row",
}


@pytest.fixture
async def client(fake_litellm: FakeLiteLLM) -> AsyncIterator[LiteLLMClient]:
    """A client wired to the fake proxy with the correct master key.

    Every call in this module authenticates through it, so the fake's blanket
    401 means the `Authorization` header is asserted by every passing test.
    """
    async with LiteLLMClient(
        base_url=fake_litellm.base_url,
        master_key=fake_litellm.master_key,
        transport=fake_litellm.transport,
    ) as instance:
        yield instance


async def _issue(client: LiteLLMClient, *, alias: str = ALIAS) -> str:
    """Mint a key with the standard attempt shape."""
    return await client.issue_key(key_alias=alias, models=MODELS, metadata=DIMENSIONS)


def _assert_credential_free(error: BaseException, *secrets: str) -> None:
    """No secret may appear anywhere in the raised chain (FR-009, SC-004)."""
    seen: BaseException | None = error
    depth = 0
    while seen is not None and depth < 10:
        for rendering in (str(seen), repr(seen), str(seen.args)):
            for secret in secrets:
                assert secret not in rendering, f"{secret!r} leaked into {type(seen).__name__}"
        seen = seen.__cause__ or seen.__context__
        depth += 1


# --- issuance --------------------------------------------------------------


async def test_issue_key_sends_the_attempt_alias_models_and_dimensions(
    client: LiteLLMClient, fake_litellm: FakeLiteLLM
) -> None:
    key = await client.issue_key(
        key_alias=ALIAS, models=MODELS, metadata=DIMENSIONS, ttl="12h"
    )

    assert key in fake_litellm.keys
    assert fake_litellm.key_for_alias(ALIAS) == key

    (call,) = fake_litellm.calls_to("/key/generate")
    assert call.method == "POST"
    assert call.body is not None
    assert call.body["key_alias"] == ALIAS
    assert call.body["models"] == MODELS
    assert call.body["metadata"] == DIMENSIONS
    assert call.body["duration"] == "12h"


async def test_issue_key_never_sends_a_budget_cap(
    client: LiteLLMClient, fake_litellm: FakeLiteLLM
) -> None:
    await _issue(client)

    (call,) = fake_litellm.calls_to("/key/generate")
    assert call.body is not None
    assert "max_budget" not in call.body, "budget caps are deferred to spec 004 (D-021)"
    assert "soft_budget" not in call.body
    assert fake_litellm.keys[fake_litellm.key_for_alias(ALIAS)]["max_budget"] is None


async def test_issue_key_defaults_to_the_backstop_ttl(
    client: LiteLLMClient, fake_litellm: FakeLiteLLM
) -> None:
    await _issue(client)

    (call,) = fake_litellm.calls_to("/key/generate")
    assert call.body is not None
    # R5: TTL is the backstop against teardown never running, not a run limit.
    assert DEFAULT_KEY_TTL == "24h"
    assert call.body["duration"] == DEFAULT_KEY_TTL


async def test_issue_key_surfaces_proxy_failures_without_retrying(
    client: LiteLLMClient, fake_litellm: FakeLiteLLM
) -> None:
    fake_litellm.fail_next("/key/generate", status=500)

    with pytest.raises(LiteLLMError) as excinfo:
        await _issue(client)

    assert excinfo.value.status == 500
    # Retries are the workflow's retry policy (R4), not a hidden client loop.
    assert len(fake_litellm.calls_to("/key/generate")) == 1
    _assert_credential_free(excinfo.value, fake_litellm.master_key)


# --- spend reads -----------------------------------------------------------


async def test_get_spend_reads_the_proxy_computed_total(
    client: LiteLLMClient, fake_litellm: FakeLiteLLM
) -> None:
    key = await _issue(client)
    fake_litellm.add_spend_row(key, prompt_tokens=10, completion_tokens=5, spend=0.25)
    fake_litellm.add_spend_row(key, prompt_tokens=20, completion_tokens=7, spend=0.75)

    assert await client.get_spend(key) == pytest.approx(1.0)

    (call,) = fake_litellm.calls_to("/key/info")
    assert call.method == "GET"
    assert call.params["key"] == key


async def test_get_spend_reports_zero_for_an_unpriced_model(
    client: LiteLLMClient, fake_litellm: FakeLiteLLM
) -> None:
    key = await _issue(client)
    fake_litellm.set_spend(key, 0.0)

    # 0.0 is a measurement the proxy made; "unknown" is a raise, never a zero
    # (FR-005). The distinction is the whole reason this returns a float.
    assert await client.get_spend(key) == 0.0


async def test_get_spend_raises_with_a_404_status_when_the_key_is_gone(
    client: LiteLLMClient, fake_litellm: FakeLiteLLM
) -> None:
    key = await _issue(client)
    await client.revoke_key(key)

    with pytest.raises(LiteLLMError) as excinfo:
        await client.get_spend(key)

    # Teardown branches to its snapshot fallback on exactly this (R3).
    assert excinfo.value.status == 404
    _assert_credential_free(excinfo.value, fake_litellm.master_key)


# --- spend logs ------------------------------------------------------------


async def test_fetch_spend_log_rows_filters_to_the_attempts_key(
    client: LiteLLMClient, fake_litellm: FakeLiteLLM
) -> None:
    key = await _issue(client)
    other = await _issue(client, alias="epic-7:node-9:1")
    fake_litellm.add_spend_row(key, prompt_tokens=10, completion_tokens=5, spend=0.25)
    fake_litellm.add_spend_row(other, prompt_tokens=99, completion_tokens=99, spend=9.99)

    rows = await client.fetch_spend_log_rows(key, issued_at=ISSUED_AT)

    # Rows come back for OUR key only, and the filter went over the wire as
    # the token's sha256 — the store matches nothing for a raw `sk-` value
    # (probed live 2026-08-05), and the fake enforces the same convention.
    assert [row["api_key"] for row in rows] == [hashed_token(key)]
    (call,) = fake_litellm.calls_to("/spend/logs/v2")
    assert call.method == "GET"
    assert call.params["api_key"] == hashed_token(key)
    # The proxy demands a date window (the fake 400s without one, as the real
    # one does); the client anchors it a full day before the lease's mint so
    # no clock skew or midnight boundary can hide a row.
    assert call.params["start_date"] == "2026-08-04"
    assert call.params["end_date"] >= "2026-08-05"


async def test_fetch_spend_log_rows_pass_cache_metadata_through_untouched(
    client: LiteLLMClient, fake_litellm: FakeLiteLLM
) -> None:
    key = await _issue(client)
    cached = fake_litellm.add_spend_row(
        key,
        prompt_tokens=100,
        completion_tokens=20,
        spend=0.5,
        cache_read_tokens=64,
        cache_write_tokens=8,
    )
    plain = fake_litellm.add_spend_row(
        key, prompt_tokens=3, completion_tokens=1, spend=0.01
    )

    rows = await client.fetch_spend_log_rows(key, issued_at=ISSUED_AT)

    # The client transports rows verbatim; interpreting them — including the
    # absent-vs-zero cache rule — is `aggregate.py`'s job (R2, FR-004).
    assert rows == [cached, plain]
    assert rows[0]["metadata"]["additional_usage_values"] == {
        "cache_read_input_tokens": 64,
        "cache_creation_input_tokens": 8,
    }
    assert "additional_usage_values" not in rows[1]["metadata"]


async def test_fetch_spend_log_rows_drains_every_page(
    client: LiteLLMClient, fake_litellm: FakeLiteLLM
) -> None:
    key = await _issue(client)
    for index in range(250):
        fake_litellm.add_spend_row(
            key,
            prompt_tokens=1,
            completion_tokens=1,
            spend=0.001,
            request_id=f"req-{index:03d}",
        )
    fake_litellm.max_page_size = 100

    rows = await client.fetch_spend_log_rows(key, issued_at=ISSUED_AT)

    # A client that stops after page one under-reports usage silently — the
    # exact failure FR-005 forbids.
    assert [row["request_id"] for row in rows] == [f"req-{i:03d}" for i in range(250)]

    pages = [call.params["page"] for call in fake_litellm.calls_to("/spend/logs/v2")]
    assert len(pages) > 1, "the fake's page cap should have forced pagination"
    assert pages == [str(n) for n in range(1, len(pages) + 1)]


async def test_fetch_spend_log_rows_is_empty_for_a_key_that_never_spent(
    client: LiteLLMClient, fake_litellm: FakeLiteLLM
) -> None:
    key = await _issue(client)

    assert await client.fetch_spend_log_rows(key, issued_at=ISSUED_AT) == []
    assert len(fake_litellm.calls_to("/spend/logs/v2")) == 1


# --- revocation ------------------------------------------------------------


async def test_revoke_key_deletes_the_key(
    client: LiteLLMClient, fake_litellm: FakeLiteLLM
) -> None:
    key = await _issue(client)

    assert await client.revoke_key(key) is True
    assert key not in fake_litellm.keys

    (call,) = fake_litellm.calls_to("/key/delete")
    assert call.method == "POST"
    assert call.body is not None
    assert call.body["keys"] == [key]


async def test_revoke_key_is_idempotent_when_the_key_is_already_gone(
    client: LiteLLMClient, fake_litellm: FakeLiteLLM
) -> None:
    key = await _issue(client)
    await client.revoke_key(key)

    # Temporal runs teardown at least once; a second revocation is normal, not
    # an error (FR-002, contracts/activities.md § teardown_attempt).
    assert await client.revoke_key(key) is False
    assert len(fake_litellm.calls_to("/key/delete")) == 2


# --- credentials -----------------------------------------------------------


async def test_a_wrong_master_key_raises_401_without_echoing_the_credential(
    fake_litellm: FakeLiteLLM,
) -> None:
    wrong = "sk-wrong-master-key"

    async with LiteLLMClient(
        base_url=fake_litellm.base_url,
        master_key=wrong,
        transport=fake_litellm.transport,
    ) as client:
        with pytest.raises(LiteLLMError) as excinfo:
            await _issue(client)

    assert excinfo.value.status == 401
    _assert_credential_free(excinfo.value, wrong, fake_litellm.master_key)


async def test_transport_failures_raise_a_credential_free_error(
    fake_litellm: FakeLiteLLM,
) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    async with LiteLLMClient(
        base_url=fake_litellm.base_url,
        master_key=fake_litellm.master_key,
        transport=httpx.MockTransport(refuse),
    ) as client:
        with pytest.raises(LiteLLMError) as excinfo:
            await client.get_spend("sk-fake-1")

    assert excinfo.value.status is None
    _assert_credential_free(excinfo.value, fake_litellm.master_key)


async def test_from_env_reads_the_worker_host_credentials(
    litellm_env: FakeLiteLLM,
) -> None:
    # The master key reaches the client from process env only — never from an
    # activity input or workflow payload (contracts/activities.md, FR-009).
    async with LiteLLMClient.from_env(transport=litellm_env.transport) as client:
        key = await _issue(client)

    assert key in litellm_env.keys


@pytest.mark.parametrize("missing", ["LITELLM_PROXY_URL", "LITELLM_MASTER_KEY"])
async def test_from_env_without_credentials_raises(
    litellm_env: FakeLiteLLM, monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    monkeypatch.delenv(missing)

    with pytest.raises(LiteLLMError) as excinfo:
        LiteLLMClient.from_env(transport=litellm_env.transport)

    assert missing in str(excinfo.value)
    _assert_credential_free(excinfo.value, litellm_env.master_key)
