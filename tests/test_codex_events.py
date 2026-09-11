from __future__ import annotations

import io
import json
import re

import pytest

from factory.workgraph.codex_events import (
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

DIAGNOSTIC_AND_FATAL_STREAM = "\n".join(
    [
        '{"type":"thread.started","thread_id":"0199a213-81c0-7800-8aa1-bbab2a035a53"}',
        '{"type":"item.completed","item":{"id":"item_1","type":"error","message":"configuration warning"}}',
        '{"type":"turn.started"}',
        '{"type":"error","message":"unexpected status 401: Unauthorized"}',
        '{"type":"turn.failed","error":{"message":"unexpected status 401: Unauthorized"}}',
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


def test_partial_jsonl_chunk_is_archived_and_reassembled() -> None:
    raw = io.BytesIO()
    evidence = decode(VALID_STREAM + "\n", raw=raw)

    assert raw.getvalue().decode() == VALID_STREAM + "\n"
    assert evidence.turn_outcome is TurnOutcome.COMPLETED
    assert evidence.status is EvidenceStatus.COMPLETE
