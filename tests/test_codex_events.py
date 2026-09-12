"""Official-shape fixtures for the current-execution Codex JSONL decoder."""

from __future__ import annotations

import json
from typing import Any

import pytest

from factory.workgraph.codex_events import (
    MALFORMED_KNOWN_EVENT,
    MALFORMED_USAGE,
    MISSING_THREAD_START,
    TurnOutcome,
    decode_codex_events,
)


TOKEN = "sk-0123456789abcdef0123456789abcdef"


def line(value: dict[str, Any]) -> str:
    return json.dumps(value, separators=(",", ":"))


def successful_stream(*, token: str | None = None) -> list[str]:
    message = "The answer is ready."
    if token is not None:
        message = f"The token is {token} and it must not reach orchestration."
    return [
        line({"type": "thread.started", "thread_id": "thread-current"}),
        line({"type": "turn.started"}),
        line(
            {
                "type": "item.started",
                "item": {"id": "item-0", "type": "reasoning", "text": "thinking"},
            }
        ),
        line(
            {
                "type": "item.completed",
                "item": {
                    "id": "item-1",
                    "type": "command_execution",
                    "command": "pytest -q",
                    "aggregated_output": "all green",
                    "exit_code": 0,
                },
            }
        ),
        line(
            {
                "type": "item.completed",
                "item": {
                    "id": "item-2",
                    "type": "file_change",
                    "path": "src/example.py",
                    "kind": "update",
                },
            }
        ),
        line(
            {
                "type": "item.completed",
                "item": {
                    "id": "item-3",
                    "type": "agent_message",
                    "text": message,
                },
            }
        ),
        line({"type": "item.completed", "item": {"id": "item-4", "type": "error", "message": "diagnostic"}}),
        line(
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 17, "output_tokens": 83},
            }
        ),
    ]


def fatal_stream() -> list[str]:
    return [
        *successful_stream()[:6],
        line({"type": "item.completed", "item": {"id": "item-4", "type": "error", "message": "diagnostic"}}),
        line({"type": "error", "message": "unexpected status 401 Unauthorized"}),
        line({"type": "turn.failed", "error": {"message": "unexpected status 401 Unauthorized"}}),
    ]


def decode(lines: list[str], *, raw_bytes: bytes | None = None):
    raw = raw_bytes if raw_bytes is not None else "\n".join(lines).encode()
    return decode_codex_events(raw.splitlines(keepends=True))


def test_official_shape_decodes_identity_activity_and_fatal_evidence() -> None:
    evidence = decode(successful_stream())

    assert evidence.thread_id == "thread-current"
    assert evidence.turn_started is True
    assert evidence.turn_outcome is TurnOutcome.COMPLETED
    assert [message.text for message in evidence.agent_messages] == ["The answer is ready."]
    assert evidence.final_message is not None and evidence.final_message.text == "The answer is ready."
    assert [item.kind.value for item in evidence.items] == [
        "reasoning",
        "command_execution",
        "file_change",
        "agent_message",
    ]
    assert evidence.command_outputs[0].output == "all green"
    assert evidence.file_changes[0].path == "src/example.py"
    assert evidence.fatal_events == ()
    assert evidence.diagnostic_items[0].message == "diagnostic"
    assert evidence.usage is not None
    assert evidence.usage.input_tokens == 17
    assert evidence.usage.output_tokens == 83
    assert evidence.usage.invalid_fields == ()
    assert evidence.usage.reason is None
    assert evidence.completeness.value == "complete"
    assert evidence.reasons == ()


def test_normal_items_do_not_require_a_repeated_thread_identifier() -> None:
    lines = successful_stream()
    assert "thread-current" not in lines[2]

    evidence = decode(lines)

    assert evidence.thread_id == "thread-current"
    assert evidence.completeness.value == "complete"


def test_measured_fatal_error_pair_is_one_failure_not_two_turns() -> None:
    evidence = decode(fatal_stream())

    assert evidence.turn_outcome is TurnOutcome.FAILED
    assert len(evidence.fatal_events) == 2
    assert evidence.reasons == ()


def test_malformed_json_is_archived_and_diagnosed() -> None:
    raw = b'{"type":"thread.started","thread_id":"thread-current"}\nnot-json\n'

    evidence = decode_codex_events(raw.splitlines(keepends=True))

    assert evidence.thread_id == "thread-current"
    assert any(reason.code == "invalid-json" for reason in evidence.reasons)
    assert evidence.completeness.value == "invalid"
    assert raw not in evidence.redacted_json().encode()


def test_non_object_item_body_is_a_stable_malformed_known_event() -> None:
    lines = successful_stream()[:2]
    lines.append('{"type":"item.completed","item":"bad"}')
    lines.extend(successful_stream()[4:])

    evidence = decode(lines)

    assert [message.text for message in evidence.agent_messages] == ["The answer is ready."]
    assert any(
        reason.code == MALFORMED_KNOWN_EVENT and reason.line_number == 3
        for reason in evidence.reasons
    )
    assert evidence.completeness.value == "invalid"


@pytest.mark.parametrize(
    ("event", "expected_code"),
    [
        ('{"type":"thread.started"}', "malformed-known-event"),
        ('{"type":"unknown.future"}', "unknown-event"),
        ('{"type":"turn.started","thread_id":"thread-other"}', "cross-thread-event"),
    ],
)
def test_forward_compatibility_and_identity_failures_stay_incomplete(
    event: str, expected_code: str
) -> None:
    before = decode(successful_stream()[:2])
    evidence = decode([*successful_stream()[:2], event, *successful_stream()[2:]])

    assert evidence.thread_id == before.thread_id
    assert [message.text for message in evidence.agent_messages] == ["The answer is ready."]
    assert any(reason.code == expected_code for reason in evidence.reasons)
    assert evidence.completeness.value in {"incomplete", "invalid"}


def test_missing_thread_start_does_not_fabricate_identity_or_success() -> None:
    lines = fatal_stream()[1:]

    evidence = decode(lines)

    assert evidence.thread_id is None
    assert any(reason.code == MISSING_THREAD_START for reason in evidence.reasons)
    assert evidence.completeness.value == "incomplete"
    assert evidence.turn_outcome is TurnOutcome.FAILED


def test_duplicate_terminal_events_make_evidence_invalid() -> None:
    lines = successful_stream()
    duplicate = lines[-1]

    evidence = decode([*lines, duplicate])

    assert any(reason.code == "duplicate-terminal" for reason in evidence.reasons)
    assert evidence.completeness.value == "invalid"


def test_cross_thread_event_is_refused_without_discarding_current_evidence() -> None:
    lines = successful_stream()
    lines.insert(3, line({"type": "item.started", "item": {"id": "other"}, "thread_id": "thread-other"}))

    evidence = decode(lines)

    assert evidence.thread_id == "thread-current"
    assert evidence.agent_messages
    assert any(reason.code == "cross-thread-event" for reason in evidence.reasons)
    assert evidence.completeness.value == "invalid"


def test_orchestration_evidence_redacts_tokens_and_stays_bounded() -> None:
    lines = successful_stream(token=TOKEN)
    huge = "A" * 2_000
    lines.append(line({"type": "error", "message": f"Bearer {TOKEN} {huge}"}))

    evidence = decode(lines)
    serialized = evidence.redacted_json()

    assert TOKEN not in serialized
    assert huge not in serialized
    assert "[REDACTED]" in serialized
    assert len(serialized) <= 8_192


def test_decoder_does_not_own_or_duplicate_the_raw_spool() -> None:
    raw = "\n".join(successful_stream(token=TOKEN)).encode()
    before = raw

    evidence = decode_codex_events(raw.splitlines(keepends=True))

    assert raw == before
    assert TOKEN not in evidence.redacted_json()
    assert not hasattr(evidence, "raw_events")


def test_boolean_usage_is_never_coerced_into_a_count() -> None:
    lines = successful_stream()
    lines[-1] = line({"type": "turn.completed", "usage": {"input_tokens": True, "output_tokens": 2}})

    evidence = decode(lines)

    assert evidence.usage is not None
    assert evidence.usage.input_tokens is None
    assert evidence.usage.output_tokens == 2
    assert evidence.usage.invalid_fields == ("input_tokens",)
    assert evidence.usage.reason == MALFORMED_USAGE
    assert any(reason.code == MALFORMED_USAGE for reason in evidence.reasons)
    assert evidence.completeness.value == "invalid"


@pytest.mark.parametrize("bad_value", [-1, 1.5, "2", {"input_tokens": 2}, [2]])
def test_invalid_usage_shapes_are_rejected_with_stable_provenance(bad_value: Any) -> None:
    lines = successful_stream()
    lines[-1] = line({"type": "turn.completed", "usage": {"input_tokens": bad_value}})

    evidence = decode(lines)

    assert evidence.usage is not None
    assert evidence.usage.input_tokens is None
    assert evidence.usage.invalid_fields == ("input_tokens",)
    assert any(reason.code == MALFORMED_USAGE for reason in evidence.reasons)
    assert evidence.completeness.value == "invalid"
