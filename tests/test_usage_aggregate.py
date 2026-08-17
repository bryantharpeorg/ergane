"""US1: an unmeasured metric is recorded as unknown, not as zero.

These tests live in their own file because the story is one distinct defect:
when a usage snapshot yields no rows to aggregate, the ledger must record
`NULL` for the three token/request metrics and the CLI must render that as
`UNMEASURED`. A genuine zero — rows present and reporting zero — stays `0`.

Every test here is written before the implementation changes that make it
pass, so the first run is expected to fail.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from dataclasses import replace

from factory.usage.aggregate import aggregate_rows
from factory.usage.cli import UNMEASURED, render_table
from factory.usage.ledger import connect, rollup, upsert_record
from factory.usage.models import AggregatedUsage, Termination, UsageRecord


def make_row(
    *,
    prompt_tokens: int | None = 0,
    completion_tokens: int | None = 0,
    spend: float = 0.0,
) -> dict[str, Any]:
    """One `/spend/logs/v2` row, minimal but shaped like the proxy's output."""
    return {
        "request_id": "req-1",
        "call_type": "acompletion",
        "api_key": "sk-fake-1",
        "model": "fake-provider/CHANGEME",
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "spend": spend,
        "metadata": {"user_api_key_alias": "epic-7:node-3:1"},
    }


# --- T001: aggregate cases --------------------------------------------------


def test_empty_row_set_records_unmeasured_not_zero() -> None:
    """An empty snapshot has nothing to aggregate; the metrics are unknown."""
    usage = aggregate_rows([])

    assert isinstance(usage, AggregatedUsage)
    assert usage.prompt_tokens is None
    assert usage.completion_tokens is None
    assert usage.request_count is None


def test_non_empty_row_set_records_sums() -> None:
    """Rows present and reporting counts still sum as they always have."""
    rows = [
        make_row(prompt_tokens=100, completion_tokens=10, spend=0.001),
        make_row(prompt_tokens=250, completion_tokens=75, spend=0.0025),
    ]

    usage = aggregate_rows(rows)

    assert usage.prompt_tokens == 350
    assert usage.completion_tokens == 85
    assert usage.request_count == 2
    assert usage.spend_usd == pytest.approx(0.0035)


def test_present_zero_rows_record_zero_not_unmeasured() -> None:
    """The trap case: rows exist and say zero. Zero is data; None is not."""
    rows = [
        make_row(prompt_tokens=0, completion_tokens=0, spend=0.0),
        make_row(prompt_tokens=0, completion_tokens=0, spend=0.0),
    ]

    usage = aggregate_rows(rows)

    assert usage.prompt_tokens == 0
    assert usage.completion_tokens == 0
    assert usage.request_count == 2


# --- T002: ledger round-trip ------------------------------------------------


def _unmeasured_record(spend_usd: float = 1.23) -> UsageRecord:
    """A record whose token/request metrics are unknown, with non-zero spend."""
    return UsageRecord(
        epic_id="epic-us1",
        node_id="node-us1",
        attempt=1,
        persona="implementer",
        spec_ref="us1/ledger",
        key_alias="epic-us1:node-us1:1:implementer",
        prompt_tokens=None,
        completion_tokens=None,
        cache_read_tokens=None,
        cache_write_tokens=None,
        request_count=None,
        spend_usd=spend_usd,
        final_usage_confirmed=False,
        termination=Termination.KILLED,
        issued_at="2026-08-17T00:00:00Z",
        torn_down_at="2026-08-17T01:00:00Z",
    )


def test_unmeasured_aggregate_writes_null_and_reads_back_none(tmp_path: Path) -> None:
    """The ledger stores NULL for unknown metrics and returns None on read."""
    path = tmp_path / "ledger.db"
    record = _unmeasured_record(spend_usd=4.56)

    with connect(path) as conn:
        stored = upsert_record(conn, record)

    assert stored.id is not None

    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT prompt_tokens, completion_tokens, request_count, spend_usd "
            "FROM usage_records WHERE id = ?",
            (stored.id,),
        ).fetchone()

    assert row is not None
    assert row[0] is None
    assert row[1] is None
    assert row[2] is None
    assert row[3] == pytest.approx(4.56)


# --- T003: rendering --------------------------------------------------------


def test_unmeasured_cells_render_as_unmeasured_and_zero_cells_render_as_zero() -> None:
    """A NULL metric prints UNMEASURED; a zero metric prints 0."""
    document = {
        "by": "epic",
        "filters": {"epic": None, "since": None},
        "groups": [
            {
                "key": "unmeasured",
                "prompt_tokens": None,
                "completion_tokens": None,
                "cache_read_tokens": None,
                "cache_write_tokens": None,
                "requests": None,
                "spend_usd": 1.23,
                "rows": 1,
                "unconfirmed_rows": 1,
            },
            {
                "key": "zero",
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "requests": 0,
                "spend_usd": 0.0,
                "rows": 1,
                "unconfirmed_rows": 0,
            },
        ],
        "totals": {
            "prompt_tokens": None,
            "completion_tokens": None,
            "cache_read_tokens": None,
            "cache_write_tokens": None,
            "requests": None,
            "spend_usd": 1.23,
            "rows": 2,
            "unconfirmed_rows": 1,
        },
    }

    table = render_table(document)
    unmeasured_row = next(
        line for line in table.splitlines() if line.startswith("unmeasured")
    )
    zero_row = next(line for line in table.splitlines() if line.startswith("zero"))

    assert UNMEASURED in unmeasured_row
    # Every token cell in the unmeasured row is UNMEASURED, never 0.
    for cell in ("PROMPT", "COMPLETION", "CACHE_READ", "CACHE_WRITE", "REQUESTS"):
        assert cell in table
    assert " 0 " not in unmeasured_row

    # The zero row shows real zeros.
    assert "0" in zero_row


# --- T004: totals -----------------------------------------------------------


def test_totals_over_mixed_known_and_unknown_do_not_coerce_or_drop(tmp_path: Path) -> None:
    """A total spanning a NULL row stays NULL and keeps the row in the count."""
    path = tmp_path / "ledger.db"

    known = UsageRecord(
        epic_id="epic-us1",
        node_id="node-known",
        attempt=1,
        persona="implementer",
        spec_ref="us1/ledger",
        key_alias="epic-us1:node-known:1:implementer",
        prompt_tokens=100,
        completion_tokens=10,
        cache_read_tokens=None,
        cache_write_tokens=None,
        request_count=1,
        spend_usd=0.01,
        final_usage_confirmed=True,
        termination=Termination.COMPLETED,
        issued_at="2026-08-17T00:00:00Z",
        torn_down_at="2026-08-17T01:00:00Z",
    )
    unknown = replace(
        _unmeasured_record(spend_usd=0.05),
        node_id="node-unknown",
        key_alias="epic-us1:node-unknown:1:implementer",
    )

    with connect(path) as conn:
        upsert_record(conn, known)
        upsert_record(conn, unknown)
        document = rollup(conn, by="epic")

    totals = document["totals"]
    # The known row's 100 plus the unknown row must not collapse to 100.
    assert totals["prompt_tokens"] is None
    assert totals["completion_tokens"] is None
    assert totals["requests"] is None
    # Spend is still summed; rows still counted.
    assert totals["spend_usd"] == pytest.approx(0.06)
    assert totals["rows"] == 2
