"""The questions the ledger exists to answer (FR-006), asked in SQL.

US1 makes every attempt's spend attributable; these rollups are what that
attribution is *for* — what did each persona cost this epic, what did this
requirement cost across every node and retry that touched it (SC-006), what did
the retries alone cost. All six shapes are one function over one table, so the
tests here are mostly arithmetic against a small hand-computed fixture: six rows,
two epics, three personas, one node with a retry, one spec ref that crosses
epics, and one unconfirmed fallback row.

Three properties are load-bearing beyond the sums:

- **A metric nobody reported stays `None`.** SQLite's `SUM` already returns NULL
  when every input is NULL, and that behaviour is the contract, not an accident:
  an epic whose backend does not report cache tokens must roll up to `null`, not
  to `0` (FR-004/FR-005 pass through to the rollup and on to the CLI's JSON).
  A group where *some* rows reported the metric sums the ones that did — a
  partial answer, with `unconfirmed_rows` there to say the picture is partial.
- **Unconfirmed rows are counted, not dropped.** A fallback row's spend belongs
  in the total; the flag is what stops an operator reading an estimate as a
  measurement (US2 scenario 3).
- **The return value is the CLI's JSON.** `contracts/cli.md` is a stable output
  contract, so `rollup` returns its shape — `by`, echoed `filters`, `groups`,
  `totals` — and `factory/usage/cli.py` renders rather than recomputes. The
  never-fabricate rule then has exactly one implementation, in SQL.

Row counts are the one thing that is always known: an empty scope has `rows: 0`
and `unconfirmed_rows: 0`, while its token metrics stay `None`.

Written before `rollup` exists in `factory/usage/ledger.py` (T019 precedes
T021): until it lands, every test here fails at import.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterator

import pytest

from factory.usage.ledger import ROLLUP_DIMENSIONS, connect, rollup, upsert_record
from factory.usage.models import Termination, UsageRecord

#: Attribution fields are the point of the fixture; issue time is not a rollup
#: dimension, so every seeded attempt shares one.
ISSUED_AT = "2026-07-20T09:00:00Z"

#: Six teardowns, chosen so every FR-006 dimension has something to say:
#:
#: epic    node        att persona     spec ref           prompt  cache  conf
#: epic-a  node-plan   1   architect   add-usage/spec      1000    yes   yes
#: epic-a  node-impl   1   implementer add-usage/ledger    2000    yes   yes
#: epic-a  node-impl   2   implementer add-usage/ledger    3000    yes   yes  <- retry
#: epic-a  node-debug  1   debugger    add-usage/ledger    NULL    -     no   <- fallback
#: epic-b  node-impl   1   implementer add-usage/ledger    4000    no    yes  <- crosses epics
#: epic-b  node-doc    1   architect   add-usage/docs       500    no    yes
#:
#: Both epic-b rows lack cache counters, so "epic-b" is a group whose cache
#: metric is absent from every row — the case that must report `None`.
SEEDED_ROWS: list[dict[str, Any]] = [
    dict(
        epic_id="epic-a", node_id="node-plan", attempt=1, persona="architect",
        spec_ref="add-usage/spec",
        prompt_tokens=1000, completion_tokens=100,
        cache_read_tokens=500, cache_write_tokens=50,
        request_count=4, spend_usd=0.10,
        final_usage_confirmed=True, termination=Termination.COMPLETED,
        torn_down_at="2026-07-20T10:00:00Z",
    ),
    dict(
        epic_id="epic-a", node_id="node-impl", attempt=1, persona="implementer",
        spec_ref="add-usage/ledger",
        prompt_tokens=2000, completion_tokens=200,
        cache_read_tokens=800, cache_write_tokens=80,
        request_count=6, spend_usd=0.20,
        final_usage_confirmed=True, termination=Termination.AGENT_ERROR,
        torn_down_at="2026-07-21T10:00:00Z",
    ),
    dict(
        epic_id="epic-a", node_id="node-impl", attempt=2, persona="implementer",
        spec_ref="add-usage/ledger",
        prompt_tokens=3000, completion_tokens=300,
        cache_read_tokens=900, cache_write_tokens=90,
        request_count=9, spend_usd=0.30,
        final_usage_confirmed=True, termination=Termination.COMPLETED,
        torn_down_at="2026-07-22T10:00:00Z",
    ),
    dict(
        epic_id="epic-a", node_id="node-debug", attempt=1, persona="debugger",
        spec_ref="add-usage/ledger",
        prompt_tokens=None, completion_tokens=None,
        cache_read_tokens=None, cache_write_tokens=None,
        request_count=None, spend_usd=0.05,
        final_usage_confirmed=False, termination=Termination.KILLED,
        torn_down_at="2026-07-23T10:00:00Z",
    ),
    dict(
        epic_id="epic-b", node_id="node-impl", attempt=1, persona="implementer",
        spec_ref="add-usage/ledger",
        prompt_tokens=4000, completion_tokens=400,
        cache_read_tokens=None, cache_write_tokens=None,
        request_count=5, spend_usd=0.40,
        final_usage_confirmed=True, termination=Termination.COMPLETED,
        torn_down_at="2026-07-24T10:00:00Z",
    ),
    dict(
        epic_id="epic-b", node_id="node-doc", attempt=1, persona="architect",
        spec_ref="add-usage/docs",
        prompt_tokens=500, completion_tokens=50,
        cache_read_tokens=None, cache_write_tokens=None,
        request_count=2, spend_usd=0.05,
        final_usage_confirmed=True, termination=Termination.COMPLETED,
        torn_down_at="2026-07-25T10:00:00Z",
    ),
]


def metrics(
    *,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    cache_read_tokens: int | None,
    cache_write_tokens: int | None,
    requests: int | None,
    spend_usd: float | None,
    rows: int,
    unconfirmed_rows: int,
) -> dict[str, Any]:
    """One group's (or the totals') metric block, per `contracts/cli.md`."""
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_write_tokens": cache_write_tokens,
        "requests": requests,
        "spend_usd": None if spend_usd is None else pytest.approx(spend_usd),
        "rows": rows,
        "unconfirmed_rows": unconfirmed_rows,
    }


def group(key: Any, **expected: Any) -> dict[str, Any]:
    """A whole expected group: its key plus the full metric block."""
    return {"key": key, **metrics(**expected)}


def keys_of(result: dict[str, Any]) -> list[Any]:
    return [entry["key"] for entry in result["groups"]]


def by_key(result: dict[str, Any]) -> dict[Any, dict[str, Any]]:
    return {entry["key"]: entry for entry in result["groups"]}


@pytest.fixture
def ledger(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(tmp_path / "ledger.db")
    try:
        for row in SEEDED_ROWS:
            upsert_record(
                conn,
                UsageRecord(
                    key_alias=f"{row['epic_id']}:{row['node_id']}:{row['attempt']}",
                    issued_at=ISSUED_AT,
                    **row,
                ),
            )
        yield conn
    finally:
        conn.close()


@pytest.fixture
def empty_ledger(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(tmp_path / "empty.db")
    try:
        yield conn
    finally:
        conn.close()


# --- the six dimensions ----------------------------------------------------


def test_by_persona_totals_every_epic(ledger: sqlite3.Connection) -> None:
    result = rollup(ledger, by="persona")

    # Global persona view (US2 scenario 1): implementer's cache read is the sum
    # of the two epic-a attempts — epic-b reported no cache and contributes
    # nothing rather than dragging the sum to a fabricated 0.
    assert keys_of(result) == ["architect", "debugger", "implementer"]
    assert by_key(result)["implementer"] == group(
        "implementer",
        prompt_tokens=9000, completion_tokens=900,
        cache_read_tokens=1700, cache_write_tokens=170,
        requests=20, spend_usd=0.90, rows=3, unconfirmed_rows=0,
    )
    assert by_key(result)["architect"] == group(
        "architect",
        prompt_tokens=1500, completion_tokens=150,
        cache_read_tokens=500, cache_write_tokens=50,
        requests=6, spend_usd=0.15, rows=2, unconfirmed_rows=0,
    )


def test_by_persona_within_one_epic(ledger: sqlite3.Connection) -> None:
    result = rollup(ledger, by="persona", epic="epic-a")

    # The same dimension, scoped: epic-b's implementer attempt is out, and the
    # debugger's fallback row is in — flagged, not dropped.
    assert keys_of(result) == ["architect", "debugger", "implementer"]
    assert by_key(result)["implementer"] == group(
        "implementer",
        prompt_tokens=5000, completion_tokens=500,
        cache_read_tokens=1700, cache_write_tokens=170,
        requests=15, spend_usd=0.50, rows=2, unconfirmed_rows=0,
    )
    assert by_key(result)["debugger"] == group(
        "debugger",
        prompt_tokens=None, completion_tokens=None,
        cache_read_tokens=None, cache_write_tokens=None,
        requests=None, spend_usd=0.05, rows=1, unconfirmed_rows=1,
    )


def test_by_epic(ledger: sqlite3.Connection) -> None:
    result = rollup(ledger, by="epic")

    assert keys_of(result) == ["epic-a", "epic-b"]
    assert by_key(result)["epic-a"] == group(
        "epic-a",
        prompt_tokens=6000, completion_tokens=600,
        cache_read_tokens=2200, cache_write_tokens=220,
        requests=19, spend_usd=0.65, rows=4, unconfirmed_rows=1,
    )


def test_by_spec_ref_crosses_epics(ledger: sqlite3.Connection) -> None:
    result = rollup(ledger, by="spec-ref")

    # SC-006 in one query: `add-usage/ledger` was worked in both epics, by three
    # personas, over two attempts of one node plus a killed debugger — and the
    # rollup answers "what did this requirement cost?" without a filter.
    assert keys_of(result) == [
        "add-usage/docs",
        "add-usage/ledger",
        "add-usage/spec",
    ]
    assert by_key(result)["add-usage/ledger"] == group(
        "add-usage/ledger",
        prompt_tokens=9000, completion_tokens=900,
        cache_read_tokens=1700, cache_write_tokens=170,
        requests=20, spend_usd=0.95, rows=4, unconfirmed_rows=1,
    )


def test_by_attempt_isolates_the_cost_of_retries(ledger: sqlite3.Connection) -> None:
    result = rollup(ledger, by="attempt")

    # FR-006's retry view: everything under ordinal >= 2 is what re-running cost.
    assert keys_of(result) == [1, 2]
    assert by_key(result)[2] == group(
        2,
        prompt_tokens=3000, completion_tokens=300,
        cache_read_tokens=900, cache_write_tokens=90,
        requests=9, spend_usd=0.30, rows=1, unconfirmed_rows=0,
    )
    assert by_key(result)[1] == group(
        1,
        prompt_tokens=7500, completion_tokens=750,
        cache_read_tokens=1300, cache_write_tokens=130,
        requests=17, spend_usd=0.80, rows=5, unconfirmed_rows=1,
    )


def test_by_node_aggregates_a_nodes_attempts(ledger: sqlite3.Connection) -> None:
    result = rollup(ledger, by="node")

    # Nodes are identified per epic (cli.md: grouped by `(epic_id, node_id)`),
    # so the two epics' `node-impl` stay apart while one node's attempts merge.
    assert keys_of(result) == [
        "epic-a:node-debug",
        "epic-a:node-impl",
        "epic-a:node-plan",
        "epic-b:node-doc",
        "epic-b:node-impl",
    ]
    assert by_key(result)["epic-a:node-impl"] == group(
        "epic-a:node-impl",
        prompt_tokens=5000, completion_tokens=500,
        cache_read_tokens=1700, cache_write_tokens=170,
        requests=15, spend_usd=0.50, rows=2, unconfirmed_rows=0,
    )


# --- totals ----------------------------------------------------------------


def test_grand_totals_cover_every_row(ledger: sqlite3.Connection) -> None:
    result = rollup(ledger, by="persona")

    assert result["totals"] == metrics(
        prompt_tokens=10500, completion_tokens=1050,
        cache_read_tokens=2200, cache_write_tokens=220,
        requests=26, spend_usd=1.10, rows=6, unconfirmed_rows=1,
    )


def test_totals_are_the_same_whatever_the_dimension(
    ledger: sqlite3.Connection,
) -> None:
    totals = [rollup(ledger, by=dimension)["totals"] for dimension in ROLLUP_DIMENSIONS]

    # Grouping slices the same rows; it must never change what they add up to.
    assert all(total == totals[0] for total in totals)


def test_totals_respect_the_filters(ledger: sqlite3.Connection) -> None:
    result = rollup(ledger, by="persona", epic="epic-b")

    # US2 scenario 3: an epic's total, over its nodes.
    assert result["totals"] == metrics(
        prompt_tokens=4500, completion_tokens=450,
        cache_read_tokens=None, cache_write_tokens=None,
        requests=7, spend_usd=0.45, rows=2, unconfirmed_rows=0,
    )


# --- never fabricate a zero ------------------------------------------------


def test_a_group_whose_rows_never_reported_cache_stays_null(
    ledger: sqlite3.Connection,
) -> None:
    result = rollup(ledger, by="epic")
    epic_b = by_key(result)["epic-b"]

    # FR-004/FR-005: no row in epic-b carried a cache metric, so the rollup
    # reports "not measured", not "measured as none". `is None` rather than
    # falsiness — 0 would pass a truthiness check and mean the opposite thing.
    assert epic_b["cache_read_tokens"] is None
    assert epic_b["cache_write_tokens"] is None
    assert epic_b["prompt_tokens"] == 4500


def test_a_partially_reported_metric_sums_the_rows_that_reported(
    ledger: sqlite3.Connection,
) -> None:
    implementer = by_key(rollup(ledger, by="persona"))["implementer"]

    # Rows that reported cache: 800 + 900. The epic-b attempt that did not is
    # simply absent from the sum — the alternative, refusing to answer at all
    # because one row was silent, would make the metric useless in practice.
    assert implementer["cache_read_tokens"] == 1700
    assert implementer["rows"] == 3


def test_an_unconfirmed_row_contributes_its_spend_and_its_flag(
    ledger: sqlite3.Connection,
) -> None:
    result = rollup(ledger, by="spec-ref")
    ledger_work = by_key(result)["add-usage/ledger"]

    # The killed debugger's snapshot spend (0.05) is inside the 0.95, and its
    # NULL token counts are not: `unconfirmed_rows` is what tells the operator
    # the token side of this group is an undercount (US2 scenario 3).
    assert ledger_work["spend_usd"] == pytest.approx(0.95)
    assert ledger_work["unconfirmed_rows"] == 1
    assert ledger_work["rows"] == 4
    assert result["totals"]["unconfirmed_rows"] == 1


def test_an_empty_scope_reports_no_rows_and_no_numbers(
    ledger: sqlite3.Connection,
) -> None:
    result = rollup(ledger, by="persona", epic="epic-nonexistent")

    # Row counts are always knowable, so they are 0; nothing else is measured,
    # so nothing else is a number.
    assert result["groups"] == []
    assert result["totals"] == metrics(
        prompt_tokens=None, completion_tokens=None,
        cache_read_tokens=None, cache_write_tokens=None,
        requests=None, spend_usd=None, rows=0, unconfirmed_rows=0,
    )


def test_an_empty_ledger_rolls_up_without_error(
    empty_ledger: sqlite3.Connection,
) -> None:
    # A ledger before its first teardown is not an error condition (CLI exit 0
    # on an empty result, cli.md).
    for dimension in ROLLUP_DIMENSIONS:
        result = rollup(empty_ledger, by=dimension)
        assert result["groups"] == []
        assert result["totals"]["rows"] == 0


# --- filters and echoed shape ----------------------------------------------


def test_the_since_filter_includes_the_named_day(ledger: sqlite3.Connection) -> None:
    result = rollup(ledger, by="epic", since="2026-07-23")

    # `--since YYYY-MM-DD` filters on `torn_down_at`; the boundary day is in.
    # Kept: the debugger row (07-23) and both epic-b rows. Dropped: 07-20..22.
    assert by_key(result)["epic-a"] == group(
        "epic-a",
        prompt_tokens=None, completion_tokens=None,
        cache_read_tokens=None, cache_write_tokens=None,
        requests=None, spend_usd=0.05, rows=1, unconfirmed_rows=1,
    )
    assert result["totals"]["rows"] == 3


def test_filters_compose(ledger: sqlite3.Connection) -> None:
    result = rollup(ledger, by="persona", epic="epic-b", since="2026-07-25")

    assert keys_of(result) == ["architect"]
    assert result["totals"]["rows"] == 1


def test_the_result_echoes_the_dimension_and_filters(
    ledger: sqlite3.Connection,
) -> None:
    # cli.md's JSON contract is the return shape, so `--json` is a dump rather
    # than a re-assembly: the keys, and the null-when-unfiltered echo, live here.
    unfiltered = rollup(ledger, by="spec-ref")
    assert unfiltered["by"] == "spec-ref"
    assert unfiltered["filters"] == {"epic": None, "since": None}
    assert set(unfiltered) == {"by", "filters", "groups", "totals"}

    filtered = rollup(ledger, by="node", epic="epic-a", since="2026-07-21")
    assert filtered["by"] == "node"
    assert filtered["filters"] == {"epic": "epic-a", "since": "2026-07-21"}


def test_the_dimensions_are_the_ones_the_cli_offers() -> None:
    # One vocabulary: argparse's `--by` choices come from this tuple, so a new
    # dimension cannot be reachable in SQL but unreachable from the CLI.
    assert tuple(ROLLUP_DIMENSIONS) == ("persona", "epic", "spec-ref", "attempt", "node")


@pytest.mark.parametrize("dimension", ["", "spec_ref", "persona; DROP TABLE", "cost"])
def test_an_unknown_dimension_is_refused(
    ledger: sqlite3.Connection, dimension: str
) -> None:
    # The dimension names a column in generated SQL, so it is validated against
    # the allowed set rather than interpolated on trust.
    with pytest.raises(ValueError):
        rollup(ledger, by=dimension)
