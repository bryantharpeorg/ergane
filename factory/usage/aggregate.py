"""Spend-log rows for one key, summed into what the attempt cost.

This is the component's only interpretation step: the client returns rows
verbatim, the ledger stores whatever it is handed, and everything in between —
including the decision that a number is unknown rather than zero — happens here.

Two rules carry the weight:

- **Absent is not zero.** Cache counters live only in each row's
  `metadata.additional_usage_values` (research R2), and a backend that does not
  report them leaves the block missing, empty, or shaped some other way. All of
  those mean *no measurement*, so the metric aggregates to `None`; a row that
  reports the field as 0 is a measurement and aggregates to 0 (FR-004, FR-005).
  Read and write are decided independently — one reported metric never implies
  the other.
- **Every row the client drained is a request.** A row missing its token columns
  contributes nothing but is still counted: dropping it would under-report the
  request count, and guessing its tokens would fabricate usage.

Pure by construction (constitution IV): rows in, dataclass out — no proxy, no
clock, no mutation of the caller's rows. Any iterable works, including a
generator, so callers may stream.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from factory.usage.models import AggregatedUsage

#: Where the proxy hides per-request cache detail (research R2); the column set
#: on the row itself has no equivalent.
ADDITIONAL_USAGE_VALUES = "additional_usage_values"

CACHE_READ_FIELD = "cache_read_input_tokens"
CACHE_WRITE_FIELD = "cache_creation_input_tokens"


def aggregate_rows(rows: Iterable[Mapping[str, Any]]) -> AggregatedUsage:
    """Sum `/spend/logs/v2` rows for a single key into one attempt's usage.

    An empty row set is a genuine zero-request aggregate: the proxy answered,
    and it answered "no rows". Its cache metrics are still `None` — vacuously,
    no row reported them.
    """
    prompt_tokens = 0
    completion_tokens = 0
    request_count = 0
    spend_usd = 0.0
    # `None` until some row actually reports the metric; then a running sum.
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None

    for row in rows:
        request_count += 1
        prompt_tokens += _as_int(row.get("prompt_tokens"))
        completion_tokens += _as_int(row.get("completion_tokens"))
        spend_usd += _as_float(row.get("spend"))

        additional = _additional_usage_values(row)
        cache_read_tokens = _accumulate(cache_read_tokens, additional.get(CACHE_READ_FIELD))
        cache_write_tokens = _accumulate(cache_write_tokens, additional.get(CACHE_WRITE_FIELD))

    return AggregatedUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        request_count=request_count,
        spend_usd=spend_usd,
    )


def _additional_usage_values(row: Mapping[str, Any]) -> Mapping[str, Any]:
    """The row's cache block, or an empty mapping if it is unusable.

    Missing, null, or differently-shaped metadata at either level is absence,
    which the caller maps to `None` — never a crash, and never a zero.
    """
    metadata = row.get("metadata")
    if not isinstance(metadata, Mapping):
        return {}
    additional = metadata.get(ADDITIONAL_USAGE_VALUES)
    if not isinstance(additional, Mapping):
        return {}
    return additional


def _accumulate(total: int | None, value: Any) -> int | None:
    """Fold one row's cache counter into the running total.

    A value the proxy did not report — or reported unusably — leaves the total
    exactly as it was, so a metric absent from every row stays `None`.
    """
    if not _is_number(value):
        return total
    return int(value) + (total or 0)


def _as_int(value: Any) -> int:
    """A token column, or 0 when the row omitted it — a row-level absence, not
    an attempt-level one, so it adds nothing rather than nulling the sum."""
    return int(value) if _is_number(value) else 0


def _as_float(value: Any) -> float:
    return float(value) if _is_number(value) else 0.0


def _is_number(value: Any) -> bool:
    """`bool` is an `int` in Python and is never a token count here."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)
