"""Usage corroboration: current Codex counts stay separate from gateway spend."""

from __future__ import annotations

from pathlib import Path

import pytest

from factory.usage.ledger import (
    connect,
    rollup,
    upsert_codex_usage,
    upsert_record,
)
from factory.usage.models import CodexUsageEvidence, CodexUsageRecord
from factory.workgraph.codex_events import decode_codex_events
from tests.test_ledger_schema import make_record


def completed_stream() -> list[str]:
    return [
        '{"type":"thread.started","thread_id":"thread-current"}',
        '{"type":"turn.started"}',
        '{"type":"turn.completed","usage":{"input_tokens":17,'
        '"cached_input_tokens":5,"output_tokens":23,'
        '"reasoning_output_tokens":7}}',
    ]


def decode(lines: list[str]):
    raw = ("\n".join(lines) + "\n").encode()
    return decode_codex_events(raw.splitlines(keepends=True))


def normalize(lines: list[str]):
    return normalize_codex_usage(decode(lines))


def test_completed_turn_maps_each_supported_count() -> None:
    evidence = decode(completed_stream())

    usage = normalize_codex_usage(evidence)

    assert usage.source == "codex_cli"
    assert usage.complete is True
    assert usage.input_tokens == 17
    assert usage.cached_input_tokens == 5
    assert usage.output_tokens == 23
    assert usage.reasoning_output_tokens == 7


def test_boolean_is_not_a_token_count() -> None:
    lines = completed_stream()
    lines[-1] = lines[-1].replace('"input_tokens":17', '"input_tokens":true')

    usage = normalize(lines)

    assert usage.input_tokens is None
    assert usage.cached_input_tokens == 5
    assert usage.output_tokens == 23
    assert usage.reasoning_output_tokens == 7
    assert usage.complete is False
    assert usage.reason == "malformed-usage"


@pytest.mark.parametrize(
    ("lines", "reason"),
    [
        (
            [
                '{"type":"thread.started","thread_id":"thread-current"}',
                '{"type":"turn.started"}',
            ],
            None,
        ),
        (
            [
                '{"type":"thread.started","thread_id":"thread-current"}',
                '{"type":"turn.started"}',
                '{"type":"turn.completed","usage":{"input_tokens":17}}',
            ],
            "partial-usage",
        ),
        (
            [
                '{"type":"thread.started","thread_id":"thread-current"}',
                '{"type":"turn.started"}',
                '{"type":"turn.failed","error":{"message":"provider error"}}',
            ],
            "turn-failed",
        ),
        (
            [
                '{"type":"thread.started","thread_id":"thread-current"}',
                '{"type":"turn.started"}',
                '{"type":"turn.failed","error":{"message":"provider error"}}',
                '{"type":"turn.completed","usage":{"input_tokens":17,'
                '"output_tokens":23}}',
            ],
            "duplicate-terminal",
        ),
    ],
)
def test_unobserved_usage_stays_unknown_and_not_complete(
    lines: list[str], reason: str | None
) -> None:
    usage = normalize(lines)

    assert usage.complete is False
    assert usage.source == "codex_cli"
    assert usage.input_tokens is None
    assert usage.cached_input_tokens is None
    assert usage.output_tokens is None
    assert usage.reasoning_output_tokens is None
    assert usage.reason == reason


def test_gateway_rollup_does_not_add_codex_corroboration(
    tmp_path: Path,
) -> None:
    ledger = connect(tmp_path / "ledger.db")
    try:
        gateway = upsert_record(
            ledger,
            make_record(
                prompt_tokens=120,
                completion_tokens=34,
                spend_usd=0.4212,
                usage_source="gateway",
                usage_status="complete",
            ),
        )
        cli = upsert_codex_usage(
            ledger,
            CodexUsageRecord(
                key_alias=gateway.key_alias,
                input_tokens=17,
                cached_input_tokens=5,
                output_tokens=23,
                reasoning_output_tokens=7,
                source="codex_cli",
                complete=True,
            ),
        )

        totals = rollup(ledger, by="persona")["totals"]
        stored = ledger.execute(
            "SELECT * FROM codex_usage_evidence WHERE key_alias = ?",
            (gateway.key_alias,),
        ).fetchone()

        assert cli.id is not None
        assert stored is not None
        assert stored[-5:] == (17, 5, 23, 7, 1)
        assert totals["prompt_tokens"] == 120
        assert totals["completion_tokens"] == 34
        assert totals["spend_usd"] == pytest.approx(0.4212)
    finally:
        ledger.close()
