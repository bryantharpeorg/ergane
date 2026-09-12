"""Usage corroboration: current Codex counts stay separate from gateway spend."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from temporalio.testing import ActivityEnvironment

from factory.usage.ledger import (
    connect,
    rollup,
    upsert_codex_usage,
    upsert_record,
)
from factory.usage.codex_evidence import normalize_codex_usage
from factory.usage.models import CodexUsageEvidence, CodexUsageRecord
from factory.workgraph.codex_events import decode_codex_events
from factory.activities.usage_activities import (
    IssueKeyInput,
    TeardownInput,
    issue_attempt_key,
    teardown_attempt,
)
from factory.usage.models import KeyLease, Termination
from factory.workgraph.adapter import CODEX_EVENTS_NAME, transcript_dir
from factory.usage.litellm_client import LiteLLMClient
from factory.env import ERGANE_ROOT_ENV
from tests.conftest import FakeLiteLLM
from tests.test_usage_activities import (
    ATTEMPT,
    EPIC,
    NODE,
    SPEC_REF,
    spend_rows_for,
)
from tests.test_ledger_schema import make_record


GATEWAY_PERSONA = "gateway-CHANGEME"
SUBSCRIPTION_PERSONA = "subscription-CHANGEME"


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
    assert usage.input_tokens == (17 if reason == "partial-usage" else None)
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
            "SELECT input_tokens, cached_input_tokens, output_tokens,"
            " reasoning_output_tokens, complete FROM codex_usage_evidence"
            " WHERE key_alias = ?",
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


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        (
            [
                '{"type":"thread.started","thread_id":"thread-current"}',
                '{"type":"turn.started"}',
            ],
            (None, None, None, None, 0, None),
        ),
        (
            [
                '{"type":"thread.started","thread_id":"thread-current"}',
                '{"type":"turn.started"}',
                '{"type":"turn.completed","usage":{"input_tokens":17}}',
            ],
            (17, None, None, None, 0, "partial-usage"),
        ),
        (
            [
                '{"type":"thread.started","thread_id":"thread-current"}',
                '{"type":"turn.started"}',
                '{"type":"turn.failed","error":{"message":"provider error"}}',
            ],
            (None, None, None, None, 0, "turn-failed"),
        ),
        (
            [
                '{"type":"thread.started","thread_id":"thread-current"}',
                '{"type":"turn.started"}',
                '{"type":"turn.failed","error":{"message":"provider error"}}',
                '{"type":"turn.completed","usage":{"input_tokens":17,'
                '"output_tokens":23}}',
            ],
            (None, None, None, None, 0, "duplicate-terminal"),
        ),
    ],
)
def test_codex_usage_ledger_keeps_unknowns_not_complete(
    lines: list[str], expected: tuple[int | None, int | None, int | None, int | None, int, str | None]
) -> None:
    usage = normalize_codex_usage(decode(lines))
    record = CodexUsageRecord(
        key_alias="epic-7:node-3:2:codex",
        input_tokens=usage.input_tokens,
        cached_input_tokens=usage.cached_input_tokens,
        output_tokens=usage.output_tokens,
        reasoning_output_tokens=usage.reasoning_output_tokens,
        source=usage.source,
        complete=usage.complete,
        reason=usage.reason,
    )

    with connect(":memory:") as ledger:
        stored = upsert_codex_usage(ledger, record)
        row = ledger.execute(
            "SELECT input_tokens, cached_input_tokens, output_tokens,"
            " reasoning_output_tokens, complete, reason"
            " FROM codex_usage_evidence WHERE key_alias = ?",
            (record.key_alias,),
        ).fetchone()

    assert stored.id is not None
    assert row == expected


def test_a_repeated_incomplete_codex_write_preserves_complete_evidence() -> None:
    with connect(":memory:") as ledger:
        complete = upsert_codex_usage(
            ledger,
            CodexUsageRecord(
                key_alias="epic-7:node-3:2:codex",
                input_tokens=17,
                cached_input_tokens=5,
                output_tokens=23,
                reasoning_output_tokens=7,
                source="codex_cli",
                complete=True,
                reason=None,
            ),
        )
        later = upsert_codex_usage(
            ledger,
            CodexUsageRecord(
                key_alias="epic-7:node-3:2:codex",
                input_tokens=None,
                cached_input_tokens=None,
                output_tokens=None,
                reasoning_output_tokens=None,
                source="codex_cli",
                complete=False,
                reason="partial-usage",
            ),
        )
        stored = ledger.execute(
            "SELECT input_tokens, cached_input_tokens, output_tokens,"
            " reasoning_output_tokens, complete, reason FROM codex_usage_evidence"
            " WHERE key_alias = ?",
            (complete.key_alias,),
        ).fetchone()

    assert stored == (17, 5, 23, 7, 1, None)
    assert type(later.complete) is bool
    assert later.complete is True
    assert later.id == complete.id
    assert (later.input_tokens, later.cached_input_tokens) == (17, 5)
    assert (later.output_tokens, later.reasoning_output_tokens) == (23, 7)
    assert later.reason is None


@pytest.fixture
def ledger_path(tmp_path: Path) -> Path:
    return tmp_path / "ledger.db"


@pytest.fixture
def proxy(
    litellm_env: FakeLiteLLM, ledger_path: Path, monkeypatch: pytest.MonkeyPatch
) -> FakeLiteLLM:
    monkeypatch.setenv("ERGANE_LEDGER_PATH", str(ledger_path))
    monkeypatch.setattr(
        "factory.activities.usage_activities.open_client",
        lambda: LiteLLMClient.from_env(transport=litellm_env.transport),
    )
    return litellm_env


@pytest.fixture
def activity_env() -> ActivityEnvironment:
    return ActivityEnvironment()


@pytest.fixture
def archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    monkeypatch.setenv("FACTORY_ROOT", str(tmp_path))
    monkeypatch.setenv(ERGANE_ROOT_ENV, str(tmp_path))
    path = transcript_dir(tmp_path, EPIC, NODE, ATTEMPT)
    path.mkdir(parents=True)
    yield path


def write_usage(archive: Path) -> None:
    raw = ("\n".join(completed_stream()) + "\n").encode()
    (archive / CODEX_EVENTS_NAME).write_bytes(raw)
    (archive / CODEX_EVENTS_NAME).chmod(0o600)


async def issue(env: ActivityEnvironment, persona: str, route: str) -> KeyLease:
    return await env.run(
        issue_attempt_key,
        IssueKeyInput(
            node_id=NODE,
            epic_id=EPIC,
            attempt=ATTEMPT,
            persona=persona,
            spec_ref=SPEC_REF,
            route=route,
        ),
    )


async def test_gateway_keeps_litellm_authoritative_and_stores_codex_separately(
    activity_env: ActivityEnvironment,
    proxy: FakeLiteLLM,
    ledger_path: Path,
    archive: Path,
) -> None:
    lease = await issue(activity_env, GATEWAY_PERSONA, "gateway")
    spend_rows_for(proxy, lease.key)
    write_usage(archive)

    record = await activity_env.run(
        teardown_attempt,
        TeardownInput(lease=lease, termination=Termination.COMPLETED),
    )

    ledger = connect(ledger_path)
    try:
        main = ledger.execute("SELECT * FROM usage_records").fetchone()
        corroboration = ledger.execute(
            "SELECT input_tokens, cached_input_tokens, output_tokens,"
            " reasoning_output_tokens, complete FROM codex_usage_evidence"
            " WHERE key_alias = ?",
            (lease.key_alias,),
        ).fetchone()
    finally:
        ledger.close()

    assert record.prompt_tokens == 600
    assert record.completion_tokens == 60
    assert record.spend_usd == pytest.approx(0.06)
    assert record.usage_source == "gateway"
    assert record.final_usage_confirmed is True
    assert main is not None
    assert corroboration == (17, 5, 23, 7, 1)


async def test_subscription_records_codex_cli_and_no_spend(
    activity_env: ActivityEnvironment,
    ledger_path: Path,
    archive: Path,
) -> None:
    lease = await issue(activity_env, SUBSCRIPTION_PERSONA, "subscription")
    write_usage(archive)

    record = await activity_env.run(
        teardown_attempt,
        TeardownInput(lease=lease, termination=Termination.COMPLETED),
    )

    assert record.prompt_tokens == 17
    assert record.completion_tokens == 23
    assert record.cache_read_tokens == 5
    assert record.request_count is None
    assert record.spend_usd is None
    assert record.usage_source == "codex_cli"
    assert record.final_usage_confirmed is True
