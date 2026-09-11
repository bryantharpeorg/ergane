from __future__ import annotations

import io

import pytest

from factory.workgraph.codex_events import (
    EVIDENCE_JSON_LIMIT,
    ORCHESTRATION_TEXT_LIMIT,
    CodexEventDecoder,
    EvidenceStatus,
    TurnOutcome,
)


VALID_STREAM = "\n".join(
    [
        '{"type":"thread.started","thread_id":"0199a213-81c0-7800-8aa1-bbab2a035a53"}',
        '{"type":"turn.started"}',
        '{"type":"item.started","item":{"id":"item_1","type":"reasoning","text":"checking the repository"}}',
        '{"type":"item.completed","item":{"id":"item_1","type":"reasoning","text":"checked the repository"}}',
        '{"type":"item.completed","item":{"id":"item_2","type":"command_execution","command":"bash -lc ls","status":"completed"}}',
        '{"type":"item.completed","item":{"id":"item_3","type":"file_change","path":"README.md","status":"completed"}}',
        '{"type":"item.completed","item":{"id":"item_4","type":"agent_message","text":"The repository is ready."}}',
        '{"type":"turn.completed","usage":{"input_tokens":24763,"cached_input_tokens":24448,"output_tokens":122,"reasoning_output_tokens":0}}',
    ]
)

TOKEN_STREAM = "\n".join(
    [
        '{"type":"thread.started","thread_id":"0199a213-81c0-7800-8aa1-bbab2a035a53"}',
        '{"type":"item.started","item":{"id":"item_1","type":"reasoning","text":"sk-proj-000000000000000000000000"}}',
        '{"type":"item.completed","item":{"id":"item_2","type":"command_execution","text":"ghp_0000000000000000000000000000"}}',
        '{"type":"item.completed","item":{"id":"item_3","type":"agent_message","text":"Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.0000000000000000000000000000000000"}}',
        '{"type":"item.completed","item":{"id":"item_4","type":"error","message":"AKIAAAAAAAAAAAAAAAAA"}}',
        '{"type":"turn.started"}',
        '{"type":"error","message":"Bearer AKIAAAAAAAAAAAAAAAAA"}',
        '{"type":"turn.failed","error":{"message":"Bearer AKIAAAAAAAAAAAAAAAAA"}}',
    ]
)

DIAGNOSTIC_AND_FATAL_STREAM = "\n".join(
    [
        '{"type":"thread.started","thread_id":"0199a213-81c0-7800-8aa1-bbab2a035a53"}',
        '{"type":"item.completed","item":{"id":"item_1","type":"error","message":"configuration warning"}}',
        '{"type":"turn.started"}',
        '{"type":"error","message":"unexpected status 401: Unauthorized"}',
        '{"type":"turn.failed","error":{"message":"unexpected status 401: Unauthorized"}}',
    ]
)

UNKNOWN_FUTURE_STREAM = "\n".join(
    [
        '{"type":"thread.started","thread_id":"0199a213-81c0-7800-8aa1-bbab2a035a53"}',
        '{"type":"turn.started"}',
        '{"type":"protocol.update","schema_version":"future"}',
        '{"type":"item.completed","item":{"id":"item_1","type":"agent_message","text":"known evidence"}}',
        '{"type":"turn.completed"}',
    ]
)


def decode(data: str, raw: io.BytesIO | None = None):
    return decode_chunks([data], raw)


def decode_chunks(chunks: list[str], raw: io.BytesIO | None = None):
    decoder = CodexEventDecoder(raw_sink=raw)
    for chunk in chunks:
        decoder.feed(chunk)
    return decoder.finish()


def test_valid_stream_separates_identity_turn_items_messages_and_usage() -> None:
    evidence = decode(VALID_STREAM)

    assert evidence.thread_id == "0199a213-81c0-7800-8aa1-bbab2a035a53"
    assert evidence.current_turn_started is True
    assert evidence.turn_outcome is TurnOutcome.COMPLETED
    assert [item.item_type for item in evidence.items] == [
        "reasoning",
        "reasoning",
        "command_execution",
        "file_change",
    ]
    assert [item.item_id for item in evidence.items] == [
        "item_1",
        "item_1",
        "item_2",
        "item_3",
    ]
    assert [item.command for item in evidence.items] == [
        "",
        "",
        "bash -lc ls",
        "",
    ]
    assert [item.path for item in evidence.items] == ["", "", "", "README.md"]
    assert [message.text for message in evidence.agent_messages] == [
        "The repository is ready."
    ]
    assert evidence.final_message == "The repository is ready."
    assert [event.message for event in evidence.fatal_events] == []
    assert evidence.usage is not None
    assert evidence.usage.input_tokens == 24763
    assert evidence.usage.cached_input_tokens == 24448
    assert evidence.usage.output_tokens == 122
    assert evidence.usage.reasoning_output_tokens == 0
    assert evidence.status is EvidenceStatus.COMPLETE
    assert evidence.reasons == ()


def test_measured_error_shape_keeps_diagnostic_separate_from_fatal_failure() -> None:
    evidence = decode(DIAGNOSTIC_AND_FATAL_STREAM)

    assert [item.item_type for item in evidence.items] == ["error"]
    assert [item.text for item in evidence.items] == ["configuration warning"]
    assert evidence.turn_outcome is TurnOutcome.FAILED
    assert evidence.agent_messages == ()
    assert evidence.final_message is None
    assert [event.message for event in evidence.fatal_events] == [
        "unexpected status 401: Unauthorized"
    ]
    assert [event.event_types for event in evidence.fatal_events] == [
        ("error", "turn.failed")
    ]
    assert evidence.status is EvidenceStatus.COMPLETE


def test_normal_items_without_repeated_thread_id_are_accepted() -> None:
    evidence = decode(VALID_STREAM)

    assert evidence.status is EvidenceStatus.COMPLETE
    assert not any("thread" in reason for reason in evidence.reasons)


@pytest.mark.parametrize(
    ("raw_lines", "reason", "expected_status"),
    [
        ('{"type":"thread.started"', "malformed-json", EvidenceStatus.INVALID),
            ('{"type":"turn.started"}', "missing-thread-start", EvidenceStatus.INVALID),
    ],
)
def test_degraded_streams_report_stable_reasons_without_fabricating_turns(
    raw_lines: str,
    reason: str,
    expected_status: EvidenceStatus,
) -> None:
    evidence = decode(raw_lines)

    assert reason in evidence.reasons
    assert evidence.status is expected_status
    assert evidence.turn_outcome is TurnOutcome.PENDING
    assert evidence.agent_messages == ()
    assert evidence.final_message is None
    assert evidence.usage is None


def test_duplicate_terminal_is_invalid_and_retains_the_first_terminal() -> None:
    raw = io.BytesIO()
    first = "\n".join(
        [
            '{"type":"thread.started","thread_id":"thread-a"}',
            '{"type":"turn.started"}',
            '{"type":"turn.completed","usage":{"output_tokens":7}}',
        ]
    ) + "\n"
    duplicate = '{"type":"turn.completed","usage":{"output_tokens":99}}\n'

    evidence = decode_chunks([first, duplicate], raw=raw)

    assert "duplicate-terminal-event" in evidence.reasons
    assert evidence.status is EvidenceStatus.INVALID
    assert evidence.turn_outcome is TurnOutcome.COMPLETED
    assert evidence.usage is not None
    assert evidence.usage.output_tokens == 7


def test_event_for_a_different_thread_is_invalid_and_keeps_current_evidence() -> None:
    raw = io.BytesIO()
    current = (
        '{"type":"thread.started","thread_id":"thread-a"}\n'
        '{"type":"turn.started"}\n'
        '{"type":"item.completed","item":{"id":"item_1","type":"agent_message","text":"before"}}\n'
    )
    other = '{"type":"thread.started","thread_id":"thread-b"}\n'

    evidence = decode_chunks([current, other], raw=raw)

    assert evidence.thread_id == "thread-a"
    assert [message.text for message in evidence.agent_messages] == ["before"]
    assert "conflicting-thread-id:thread-b" in evidence.reasons
    assert evidence.status is EvidenceStatus.INVALID


def test_unknown_future_event_is_archived_and_keeps_known_evidence_incomplete() -> None:
    raw = io.BytesIO()

    evidence = decode(UNKNOWN_FUTURE_STREAM, raw=raw)

    assert raw.getvalue().decode() == UNKNOWN_FUTURE_STREAM
    assert "unknown-event:protocol.update" in evidence.reasons
    assert evidence.turn_outcome is TurnOutcome.COMPLETED
    assert [message.text for message in evidence.agent_messages] == ["known evidence"]
    assert evidence.final_message == "known evidence"
    assert evidence.status is EvidenceStatus.INCOMPLETE


def test_truncated_final_line_is_archived_and_marked_incomplete() -> None:
    raw = io.BytesIO()

    evidence = decode('{"type":"turn.started"}\n{"type":"turn', raw=raw)

    assert raw.getvalue().decode() == '{"type":"turn.started"}\n{"type":"turn'
    assert "truncated-line" in evidence.reasons
    assert evidence.current_turn_started is True
    assert evidence.turn_outcome is TurnOutcome.PENDING
    assert evidence.agent_messages == ()


def test_orchestration_evidence_redacts_token_shapes_but_keeps_raw_archive() -> None:
    raw = io.BytesIO()

    evidence = decode(TOKEN_STREAM + "\n", raw=raw)
    payload = evidence.redacted_json()

    assert raw.getvalue().decode() == TOKEN_STREAM + "\n"
    assert "sk-proj-000000000000000000000000" not in payload
    assert "ghp_0000000000000000000000000000" not in payload
    assert "eyJhbGciOiJIUzI1NiJ9" not in payload
    assert "AKIAAAAAAAAAAAAAAAAA" not in payload
    assert "[REDACTED]" in payload
    assert evidence.agent_messages[0].text == "Bearer [REDACTED]"
    assert evidence.fatal_events[0].message == "Bearer [REDACTED]"
    assert evidence.redacted_json() == payload


def test_orchestration_fields_and_serialization_are_bounded() -> None:
    decoder = CodexEventDecoder()
    for index in range(64):
        decoder.feed(
            '{"type":"item.completed","item":{"id":"'
            + f"item_{index}"
            + '","type":"agent_message","text":"'
            + "A" * (ORCHESTRATION_TEXT_LIMIT * 4)
            + '"}}\n'
        )
    evidence = decoder.finish()
    payload = evidence.redacted_json()

    assert len(evidence.agent_messages) == 16
    assert all(
        len(message.text) <= ORCHESTRATION_TEXT_LIMIT
        for message in evidence.agent_messages
    )
    assert len(payload) <= EVIDENCE_JSON_LIMIT


def test_partial_jsonl_chunk_is_archived_and_reassembled() -> None:
    raw = io.BytesIO()
    evidence = decode(VALID_STREAM + "\n", raw=raw)

    assert raw.getvalue().decode() == VALID_STREAM + "\n"
    assert evidence.turn_outcome is TurnOutcome.COMPLETED
    assert evidence.status is EvidenceStatus.COMPLETE
