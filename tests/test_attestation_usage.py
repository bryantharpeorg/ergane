"""US1-S4/S5: source-specific usage completeness and legacy refusal."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from factory.attestation import (
    UsageObservation,
    read_usage_evidence,
    read_usage_observations,
    record_usage_observation,
)
from factory.usage.models import CodexUsageRecord, Termination, UsageRecord
from factory.usage.ledger import connect, upsert_codex_usage, upsert_record


SCHEMA_V2_DDL = """
CREATE TABLE schema_version (version INTEGER NOT NULL);
CREATE TABLE usage_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    epic_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    persona TEXT NOT NULL,
    spec_ref TEXT NOT NULL,
    key_alias TEXT NOT NULL UNIQUE,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    cache_read_tokens INTEGER,
    cache_write_tokens INTEGER,
    request_count INTEGER,
    spend_usd REAL,
    final_usage_confirmed INTEGER NOT NULL,
    termination TEXT NOT NULL,
    issued_at TEXT NOT NULL,
    torn_down_at TEXT NOT NULL
);
"""


def record(**overrides: Any) -> UsageRecord:
    fields = {
        "epic_id": "epic-1",
        "node_id": "us1",
        "attempt": 1,
        "persona": "implementer",
        "spec_ref": "167:US1",
        "key_alias": "epic-1:us1:1:implementer",
        "prompt_tokens": None,
        "completion_tokens": None,
        "cache_read_tokens": None,
        "cache_write_tokens": None,
        "request_count": None,
        "spend_usd": None,
        "final_usage_confirmed": False,
        "termination": Termination.COMPLETED,
        "issued_at": "2026-09-12T00:00:00Z",
        "torn_down_at": "2026-09-12T01:00:00Z",
    }
    fields.update(overrides)
    return UsageRecord(**fields)


def create_v2(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_V2_DDL)
    conn.execute(
        "INSERT INTO usage_records (epic_id,node_id,attempt,persona,spec_ref,key_alias,"
        "prompt_tokens,completion_tokens,request_count,spend_usd,final_usage_confirmed,"
        "termination,issued_at,torn_down_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "epic-1",
            "us1",
            1,
            "implementer",
            "167:US1",
            "legacy-ambiguous",
            None,
            12,
            3,
            0.25,
            1,
            "completed",
            "2026-09-12T00:00:00Z",
            "2026-09-12T01:00:00Z",
        ),
    )
    conn.commit()
    conn.close()


def test_schema_v2_reads_without_migration_or_guessed_join(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    create_v2(path)
    before = path.read_bytes()

    evidence = read_usage_evidence(path)

    assert len(evidence) == 1
    assert evidence[0].invocation_id is None
    assert evidence[0].usage_source == "legacy"
    assert evidence[0].usage_status == "legacy"
    assert evidence[0].builder_or_judge == "builder"
    assert evidence[0].metrics["completion_tokens"].value == 12
    assert evidence[0].metrics["completion_tokens"].complete is True
    assert evidence[0].metrics["prompt_tokens"].complete is False
    assert evidence[0].complete_total is None
    assert path.read_bytes() == before


def test_gateway_and_codex_stay_source_separate(tmp_path: Path) -> None:
    path = tmp_path / "mixed.db"
    gateway = record(
        prompt_tokens=100,
        completion_tokens=50,
        request_count=2,
        spend_usd=0.20,
        usage_source="gateway",
        usage_status="complete",
        cost_basis="proxy_estimate",
    )
    cli = record(
        prompt_tokens=100,
        completion_tokens=50,
        usage_source="codex_cli",
        usage_status="partial",
        cost_basis="unknown",
    )
    with connect(path) as conn:
        gateway = upsert_record(conn, gateway)
        upsert_codex_usage(
            conn,
            CodexUsageRecord(
                key_alias=gateway.key_alias,
                input_tokens=100,
                cached_input_tokens=None,
                output_tokens=50,
                reasoning_output_tokens=None,
                source="codex_cli",
                complete=False,
            ),
        )

    evidence = read_usage_evidence(path)

    sources = {item.usage_source for item in evidence}
    assert sources == {"gateway", "codex_cli"}
    gateway_row = next(item for item in evidence if item.usage_source == "gateway")
    assert gateway_row.metrics["request_count"].value == 2
    assert gateway_row.metrics["spend_usd"].value == pytest.approx(0.20)
    assert gateway_row.complete_token_total == 150
    assert gateway_row.complete_total == pytest.approx(0.20)


def test_confirmed_flag_does_not_complete_missing_tokens(tmp_path: Path) -> None:
    path = tmp_path / "confirmed-partial.db"
    with connect(path) as conn:
        upsert_record(
            conn,
            record(
                request_count=1,
                final_usage_confirmed=True,
                usage_source="gateway",
                usage_status="complete",
            ),
        )

    evidence = read_usage_evidence(path)

    assert evidence[0].metrics["prompt_tokens"].complete is False
    assert evidence[0].metrics["prompt_tokens"].value is None
    assert evidence[0].complete_token_total is None
    assert evidence[0].metrics["request_count"].complete is True
    assert evidence[0].complete_total is None


def test_subscription_dollars_are_unknown_not_zero(tmp_path: Path) -> None:
    path = tmp_path / "subscription.db"
    with connect(path) as conn:
        upsert_record(
            conn,
            record(
                persona="subscription",
                request_count=2,
                completion_tokens=40,
                usage_source="subscription",
                usage_status="partial",
                cost_basis="unknown",
            ),
        )

    evidence = read_usage_evidence(path)

    assert evidence[0].builder_or_judge == "builder"
    assert evidence[0].metrics["spend_usd"].value is None
    assert evidence[0].metrics["spend_usd"].unavailable_reason == "unavailable"
    assert evidence[0].metrics["request_count"].value == 2


def test_observations_keep_repeated_amounts_and_serving_identity(tmp_path: Path) -> None:
    journal = tmp_path / "journal.db"
    first = UsageObservation(
        invocation_id="run:launch:1",
        source="gateway",
        source_id="request-a",
        serving_model="served-a",
        model_alias="builder-a",
        prompt_tokens=10,
        completion_tokens=1,
        spend_usd=0.01,
    )
    second = UsageObservation(
        invocation_id="run:launch:1",
        source="gateway",
        source_id="request-b",
        serving_model="served-b",
        model_alias="builder-a",
        prompt_tokens=10,
        completion_tokens=1,
        spend_usd=0.01,
    )

    record_usage_observation(journal, first)
    record_usage_observation(journal, second)
    observations = read_usage_observations(journal)

    assert [item.source_id for item in observations] == ["request-a", "request-b"]
    assert [item.serving_model for item in observations] == ["served-a", "served-b"]
    assert [item.prompt_tokens for item in observations] == [10, 10]
