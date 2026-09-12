"""Read-only packet projections of source-specific usage evidence."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MetricEvidence:
    """One dimension with its availability, never a fabricated zero."""

    value: int | float | None
    complete: bool
    unavailable_reason: str | None = None


@dataclass(frozen=True)
class UsageEvidence:
    """A single source's view of one invocation's usage."""

    usage_id: int | None
    invocation_id: str | None
    builder_or_judge: str
    usage_source: str
    usage_status: str
    cost_basis: str
    final_usage_confirmed: bool
    metrics: dict[str, MetricEvidence]

    @property
    def complete_token_total(self) -> int | None:
        prompt = self.metrics["prompt_tokens"]
        completion = self.metrics["completion_tokens"]
        if prompt.value is None or completion.value is None:
            return None
        return int(prompt.value) + int(completion.value)

    @property
    def complete_total(self) -> float | None:
        spend = self.metrics["spend_usd"]
        if (
            spend.value is None
            or self.metrics["prompt_tokens"].value is None
            or self.metrics["completion_tokens"].value is None
            or self.usage_status != "complete"
        ):
            return None
        return float(spend.value)


@dataclass(frozen=True)
class UsageObservation:
    """A copied authoritative source row, not an accounting aggregate."""

    invocation_id: str
    source: str
    source_id: str
    serving_model: str | None
    model_alias: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    request_count: int | None = None
    spend_usd: float | None = None
    id: int | None = None


METRICS = (
    "prompt_tokens",
    "completion_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "request_count",
    "spend_usd",
)


def read_usage_evidence(path: str | Path) -> tuple[UsageEvidence, ...]:
    """Read a ledger without migration, rewriting, or guessing a legacy join."""
    location = Path(path)
    if not location.is_file():
        return ()
    connection = sqlite3.connect(f"file:{location}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(usage_records)")
        }
        rows = connection.execute("SELECT * FROM usage_records").fetchall()
        codex = _codex_by_alias(connection)
    finally:
        connection.close()

    evidence: list[UsageEvidence] = []
    for row in rows:
        source = row["usage_source"] if "usage_source" in columns else "legacy"
        status = row["usage_status"] if "usage_status" in columns else "legacy"
        basis = row["cost_basis"] if "cost_basis" in columns else "unknown"
        evidence.append(
            UsageEvidence(
                usage_id=row["id"],
                invocation_id=None,
                builder_or_judge=(
                    "judge" if str(row["persona"]).startswith("judge") else "builder"
                ),
                usage_source=source,
                usage_status=status,
                cost_basis=basis,
                final_usage_confirmed=bool(row["final_usage_confirmed"]),
                metrics=_metrics(row, status=status),
            )
        )
    if codex:
        evidence.extend(codex)
    return tuple(evidence)


def _codex_by_alias(connection: sqlite3.Connection) -> list[UsageEvidence]:
    tables = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    if "codex_usage_evidence" not in tables:
        return []
    result: list[UsageEvidence] = []
    for row in connection.execute("SELECT * FROM codex_usage_evidence").fetchall():
        metrics = {
            "prompt_tokens": MetricEvidence(row["input_tokens"], row["input_tokens"] is not None),
            "completion_tokens": MetricEvidence(row["output_tokens"], row["output_tokens"] is not None),
            "cache_read_tokens": MetricEvidence(
                row["cached_input_tokens"], row["cached_input_tokens"] is not None
            ),
            "cache_write_tokens": MetricEvidence(None, False, "unavailable"),
            "request_count": MetricEvidence(None, False, "unavailable"),
            "spend_usd": MetricEvidence(None, False, "unavailable"),
        }
        result.append(
            UsageEvidence(
                usage_id=row["id"],
                invocation_id=None,
                builder_or_judge="builder",
                usage_source=row["source"],
                usage_status="complete" if row["complete"] else "partial",
                cost_basis="unknown",
                final_usage_confirmed=bool(row["complete"]),
                metrics=metrics,
            )
        )
    return result


def _metrics(row: sqlite3.Row, *, status: str) -> dict[str, MetricEvidence]:
    values: dict[str, MetricEvidence] = {}
    for name in METRICS:
        value = row[name]
        values[name] = MetricEvidence(
            value,
            value is not None,
            None if value is not None else "unavailable",
        )
    return values
