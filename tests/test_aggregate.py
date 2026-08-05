"""Spend-log rows summed into one attempt's usage — the FR-004/FR-005 seam.

Aggregation is the only place the factory decides what an attempt *cost*, and
it is where a plausible-looking zero would do the most damage: a ledger row
claiming 0 cache-read tokens is indistinguishable from a measurement, so a
backend that simply does not report the metric must produce `None` instead
(FR-004). The distinction is asserted from both sides here — absent everywhere
is `None`, genuinely zero everywhere is `0`.

The other half of the contract is completeness. Sums cover every row the client
drained, cache counters are read out of each row's
`metadata.additional_usage_values` (research R2), and the two cache metrics are
independent of each other — a proxy reporting writes but not reads yields a
number and a `None`, not two `None`s.

`aggregate_rows` is pure: rows in, dataclass out, no proxy, no clock, no
mutation of the caller's rows (constitution IV).

Written before `factory/usage/aggregate.py` exists (T014 precedes T016): until
the module lands, every test here fails at import.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

import pytest

from factory.usage.aggregate import aggregate_rows
from factory.usage.litellm_client import LiteLLMClient
from factory.usage.models import AggregatedUsage
from tests.conftest import CACHE_READ_FIELD, CACHE_WRITE_FIELD, FakeLiteLLM


def make_row(
    *,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    spend: float = 0.0,
    cache_read_tokens: int | None = None,
    cache_write_tokens: int | None = None,
) -> dict[str, Any]:
    """One `/spend/logs/v2` row, shaped exactly as the proxy reports it.

    Cache counters are omitted from `additional_usage_values` when left `None`,
    and the whole `additional_usage_values` block disappears when neither is
    given — the backend-does-not-report case, which is the one that must not
    become a zero.
    """
    additional: dict[str, int] = {}
    if cache_read_tokens is not None:
        additional[CACHE_READ_FIELD] = cache_read_tokens
    if cache_write_tokens is not None:
        additional[CACHE_WRITE_FIELD] = cache_write_tokens

    metadata: dict[str, Any] = {"user_api_key_alias": "epic-7:node-3:1"}
    if additional:
        metadata["additional_usage_values"] = additional

    return {
        "request_id": "req-1",
        "call_type": "acompletion",
        "api_key": "sk-fake-1",
        "model": "fake-provider/CHANGEME",
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "spend": spend,
        "metadata": metadata,
    }


# --- sums ------------------------------------------------------------------


def test_sums_tokens_spend_and_counts_requests() -> None:
    """The ordinary path: every row's columns add up, row count is the requests."""
    rows = [
        make_row(prompt_tokens=100, completion_tokens=20, spend=0.001),
        make_row(prompt_tokens=250, completion_tokens=75, spend=0.0025),
        make_row(prompt_tokens=1, completion_tokens=2, spend=0.0001),
    ]

    usage = aggregate_rows(rows)

    assert isinstance(usage, AggregatedUsage)
    assert usage.prompt_tokens == 351
    assert usage.completion_tokens == 97
    assert usage.request_count == 3
    assert usage.spend_usd == pytest.approx(0.0036)


def test_unpriced_model_rows_aggregate_to_zero_spend_with_real_tokens() -> None:
    """A local model the proxy has no price for spent tokens but no dollars.

    Zero here is a measurement, so it stays 0.0 — the never-fabricate rule
    (FR-005) forbids inventing usage, not reporting a real zero.
    """
    rows = [make_row(prompt_tokens=40, completion_tokens=8, spend=0.0)]

    usage = aggregate_rows(rows)

    assert usage.spend_usd == 0.0
    assert usage.prompt_tokens == 40
    assert usage.completion_tokens == 8
    assert usage.request_count == 1


# --- cache: absent versus zero ---------------------------------------------


def test_cache_absent_from_every_row_is_none_never_zero() -> None:
    """No row carried the metric → the attempt has no cache figure at all."""
    rows = [
        make_row(prompt_tokens=10, completion_tokens=1, spend=0.01),
        make_row(prompt_tokens=20, completion_tokens=2, spend=0.02),
    ]

    usage = aggregate_rows(rows)

    assert usage.cache_read_tokens is None
    assert usage.cache_write_tokens is None
    # The rest of the aggregate is unaffected by the missing metric.
    assert usage.prompt_tokens == 30
    assert usage.request_count == 2


def test_cache_zero_on_every_row_is_zero_not_none() -> None:
    """The backend reported the metric and it was zero — that is data."""
    rows = [
        make_row(prompt_tokens=10, completion_tokens=1, cache_read_tokens=0, cache_write_tokens=0),
        make_row(prompt_tokens=20, completion_tokens=2, cache_read_tokens=0, cache_write_tokens=0),
    ]

    usage = aggregate_rows(rows)

    assert usage.cache_read_tokens == 0
    assert usage.cache_write_tokens == 0


def test_cache_present_on_some_rows_sums_only_the_present_values() -> None:
    """Mixed reporting sums what exists; absent rows contribute nothing."""
    rows = [
        make_row(prompt_tokens=10, completion_tokens=1, cache_read_tokens=512),
        make_row(prompt_tokens=20, completion_tokens=2),
        make_row(prompt_tokens=30, completion_tokens=3, cache_read_tokens=64),
    ]

    usage = aggregate_rows(rows)

    assert usage.cache_read_tokens == 576
    # No row reported a write, so the write metric is still absent entirely.
    assert usage.cache_write_tokens is None


def test_cache_read_and_write_are_tracked_independently() -> None:
    """A backend reporting one cache metric must not null out the other."""
    rows = [
        make_row(prompt_tokens=10, completion_tokens=1, cache_write_tokens=2048),
        make_row(prompt_tokens=20, completion_tokens=2, cache_write_tokens=1024),
    ]

    usage = aggregate_rows(rows)

    assert usage.cache_write_tokens == 3072
    assert usage.cache_read_tokens is None


@pytest.mark.parametrize(
    "metadata",
    [
        pytest.param({}, id="no-additional-usage-values"),
        pytest.param({"additional_usage_values": {}}, id="empty-additional-usage-values"),
        pytest.param({"additional_usage_values": None}, id="null-additional-usage-values"),
        pytest.param({"additional_usage_values": "n/a"}, id="non-dict-additional-usage-values"),
    ],
)
def test_unusable_cache_metadata_reads_as_absent(metadata: dict[str, Any]) -> None:
    """Metadata the proxy shaped differently is absence, not zero, and not a crash."""
    row = make_row(prompt_tokens=5, completion_tokens=1, spend=0.5)
    row["metadata"] = metadata

    usage = aggregate_rows([row])

    assert usage.cache_read_tokens is None
    assert usage.cache_write_tokens is None
    assert usage.prompt_tokens == 5
    assert usage.request_count == 1


@pytest.mark.parametrize("metadata", [None, "not-a-dict"], ids=["null", "non-dict"])
def test_unusable_row_metadata_reads_as_absent(metadata: Any) -> None:
    """Same tolerance one level up: a row whose whole metadata block is unusable."""
    row = make_row(prompt_tokens=5, completion_tokens=1, spend=0.5)
    row["metadata"] = metadata

    usage = aggregate_rows([row])

    assert usage.cache_read_tokens is None
    assert usage.cache_write_tokens is None
    assert usage.request_count == 1


def test_row_missing_token_columns_still_counts_as_a_request() -> None:
    """A malformed row contributes no tokens but is not silently dropped.

    Dropping it would under-report the request count; guessing its tokens would
    fabricate them. Counting it and adding nothing does neither.
    """
    rows = [
        make_row(prompt_tokens=10, completion_tokens=1, spend=0.01),
        {"request_id": "req-2", "api_key": "sk-fake-1", "metadata": {}},
    ]

    usage = aggregate_rows(rows)

    assert usage.prompt_tokens == 10
    assert usage.completion_tokens == 1
    assert usage.request_count == 2
    assert usage.spend_usd == pytest.approx(0.01)


# --- boundaries ------------------------------------------------------------


def test_empty_row_set_is_a_zero_request_aggregate() -> None:
    """An attempt that made no calls really did spend nothing.

    Zeros are correct here — the proxy answered, and it answered "no rows". The
    cache metrics stay `None`: no row reported them, vacuously (FR-004).
    """
    usage = aggregate_rows([])

    assert usage == AggregatedUsage(
        prompt_tokens=0,
        completion_tokens=0,
        cache_read_tokens=None,
        cache_write_tokens=None,
        request_count=0,
        spend_usd=0.0,
    )


def test_aggregation_does_not_mutate_the_caller_rows() -> None:
    """Pure function: teardown reuses the rows it passed in (constitution IV)."""
    rows = [
        make_row(prompt_tokens=10, completion_tokens=1, spend=0.01, cache_read_tokens=8),
        make_row(prompt_tokens=20, completion_tokens=2, spend=0.02),
    ]
    before = [dict(row) for row in rows]

    aggregate_rows(rows)

    assert rows == before
    assert len(rows) == 2


def test_accepts_any_iterable_of_rows() -> None:
    """Callers may stream rows; consuming a generator must still work."""
    rows = (
        make_row(prompt_tokens=n * 10, completion_tokens=n, spend=n / 1000)
        for n in (1, 2, 3)
    )

    usage = aggregate_rows(rows)

    assert usage.prompt_tokens == 60
    assert usage.completion_tokens == 6
    assert usage.request_count == 3
    assert usage.spend_usd == pytest.approx(0.006)


# --- the shape the client actually returns ---------------------------------


@pytest.fixture
async def client(fake_litellm: FakeLiteLLM) -> AsyncIterator[LiteLLMClient]:
    async with LiteLLMClient(
        base_url=fake_litellm.base_url,
        master_key=fake_litellm.master_key,
        transport=fake_litellm.transport,
    ) as instance:
        yield instance


async def test_aggregates_rows_exactly_as_the_client_returns_them(
    fake_litellm: FakeLiteLLM, client: LiteLLMClient
) -> None:
    """End-to-end over the seam: fake proxy → client pagination → aggregate.

    `make_row` above mirrors the proxy's row shape by hand; this pins that
    mirror to the real one, so a field rename on either side fails here rather
    than quietly zeroing a ledger column.
    """
    key = await client.issue_key(key_alias="epic-7:node-3:1", models=["fake-provider/CHANGEME"])
    fake_litellm.max_page_size = 2  # force pagination

    fake_litellm.add_spend_row(key, prompt_tokens=100, completion_tokens=10, spend=0.01)
    fake_litellm.add_spend_row(
        key, prompt_tokens=200, completion_tokens=20, spend=0.02, cache_read_tokens=128
    )
    fake_litellm.add_spend_row(key, prompt_tokens=300, completion_tokens=30, spend=0.03)

    usage = aggregate_rows(await client.fetch_spend_log_rows(key, issued_at="2026-08-05T00:00:00Z"))

    assert usage.prompt_tokens == 600
    assert usage.completion_tokens == 60
    assert usage.request_count == 3
    assert usage.spend_usd == pytest.approx(0.06)
    assert usage.cache_read_tokens == 128
    assert usage.cache_write_tokens is None


async def test_attempt_that_never_called_the_proxy_aggregates_to_zero_requests(
    fake_litellm: FakeLiteLLM, client: LiteLLMClient
) -> None:
    """A key that was issued and never used: no rows, no invented usage."""
    key = await client.issue_key(key_alias="epic-7:node-9:1", models=["fake-provider/CHANGEME"])

    usage = aggregate_rows(await client.fetch_spend_log_rows(key, issued_at="2026-08-05T00:00:00Z"))

    assert usage.request_count == 0
    assert usage.prompt_tokens == 0
    assert usage.spend_usd == 0.0
    assert usage.cache_read_tokens is None
