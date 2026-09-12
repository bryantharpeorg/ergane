"""Typed classification controls for Codex refusals and operator questions."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from factory.usage.models import Termination
from factory.workgraph.adapter import CODEX_REFUSAL_MARKER
from factory.workgraph.codex_events import decode_codex_events
from factory.workgraph.models import AdapterResult, UsageSnapshot
from factory.activities.agent_activities import (
    _classify_auth_failure,
    _typed_auth_failure,
)
from factory.activities.verify_activities import DetectQuestionInput, detect_operator_question_activity
from factory.verify.question import final_message_from_archive
from factory.verify.ladder import _attempts_spent
from factory.verify.models import AttemptRecord, OverallVerdict, VerificationConfig
from factory.verify.question import detect_operator_question_text


def line(value: dict[str, Any]) -> str:
    return json.dumps(value, separators=(",", ":"))


def fatal_auth_lines(message: str = CODEX_REFUSAL_MARKER) -> list[str]:
    return [
        line({"type": "thread.started", "thread_id": "thread-current"}),
        line({"type": "turn.started"}),
        line(
            {
                "type": "item.completed",
                "item": {"id": "item-reason", "type": "reasoning", "text": "diagnostics"},
            }
        ),
        line(
            {
                "type": "item.completed",
                "item": {
                    "id": "item-diagnostic",
                    "type": "error",
                    "message": "provider diagnostic",
                },
            }
        ),
        line({"type": "error", "message": message}),
        line({"type": "turn.failed", "error": {"message": message}}),
    ]


def write_typed_fixture(archive: Path, lines: list[str], stdout: str = "") -> None:
    archive.mkdir(parents=True, exist_ok=True)
    (archive / "codex-events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if stdout:
        (archive / "stdout.log").write_text(stdout, encoding="utf-8")


def test_typed_auth_refusal_is_pre_agent_and_not_charged() -> None:
    evidence = decode_codex_events(fatal_auth_lines())

    assert [event.source.value for event in evidence.fatal_events] == [
        "error",
        "turn.failed",
    ]
    assert len({event.message for event in evidence.fatal_events}) == 1
    assert evidence.diagnostic_items[0].message == "provider diagnostic"
    assert _typed_auth_failure(evidence, (CODEX_REFUSAL_MARKER,)) is True
    assert evidence.agent_took_a_turn is False


def test_auth_classification_requires_one_matching_error_and_failed_pair() -> None:
    mismatched = fatal_auth_lines()
    mismatched[-1] = line({"type": "turn.failed", "error": {"message": "401 token expired"}})

    extra_fatal = fatal_auth_lines() + [line({"type": "error", "message": CODEX_REFUSAL_MARKER})]
    reversed_pair = [
        line({"type": "thread.started", "thread_id": "thread-current"}),
        line({"type": "turn.failed", "error": {"message": CODEX_REFUSAL_MARKER}}),
        line({"type": "error", "message": CODEX_REFUSAL_MARKER}),
    ]

    assert _typed_auth_failure(decode_codex_events(mismatched), (CODEX_REFUSAL_MARKER,)) is False
    assert _typed_auth_failure(decode_codex_events(extra_fatal), (CODEX_REFUSAL_MARKER,)) is False
    assert _typed_auth_failure(decode_codex_events(reversed_pair), (CODEX_REFUSAL_MARKER,)) is False


def test_non_auth_fatal_body_quoting_401_stays_ordinary() -> None:
    message = "400 Bad Request: upstream once said unexpected status 401 Unauthorized"
    evidence = decode_codex_events(fatal_auth_lines(message))

    assert _typed_auth_failure(evidence, (CODEX_REFUSAL_MARKER,)) is False


def test_combined_output_quoting_a_historical_401_is_not_typed_evidence(
    tmp_path: Path,
) -> None:
    message = "400 Bad Request: upstream once said unexpected status 401 Unauthorized"
    lines = fatal_auth_lines(message)
    lines.insert(2, line({"type": "item.started", "item": {"id": "item-reason", "type": "reasoning", "text": message}}))
    lines.insert(3, line({"type": "item.completed", "item": {"id": "item-tool", "type": "command_execution", "command": "curl", "aggregated_output": message, "exit_code": 1}}))
    archive = tmp_path / "archive"
    write_typed_fixture(archive, lines, stdout=message)
    result = AdapterResult(termination=Termination.AGENT_ERROR, transcript_path=str(archive))

    reclassified = _classify_auth_failure(
        object(), result, evidence=decode_codex_events(lines), markers=(CODEX_REFUSAL_MARKER,)
    )

    assert reclassified.termination is Termination.AGENT_ERROR


def test_quoted_auth_markers_in_items_are_not_fatal_evidence() -> None:
    lines = [
        line({"type": "thread.started", "thread_id": "thread-current"}),
        line(
            {
                "type": "item.completed",
                "item": {"id": "item-reason", "type": "reasoning", "text": CODEX_REFUSAL_MARKER},
            }
        ),
        line(
            {
                "type": "item.completed",
                "item": {
                    "id": "item-tool",
                    "type": "command_execution",
                    "command": "cat",
                    "aggregated_output": CODEX_REFUSAL_MARKER,
                    "exit_code": 1,
                },
            }
        ),
        line(
            {
                "type": "item.completed",
                "item": {
                    "id": "item-error",
                    "type": "error",
                    "message": CODEX_REFUSAL_MARKER,
                },
            }
        ),
        line(
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 1, "output_tokens": 2},
            }
        ),
    ]
    evidence = decode_codex_events(lines)

    assert _typed_auth_failure(evidence, (CODEX_REFUSAL_MARKER,)) is False


def test_typed_reclassification_preserves_every_current_field() -> None:
    result = AdapterResult(
        termination=Termination.AGENT_ERROR,
        transcript_path="/archive/current",
        last_snapshot=UsageSnapshot(spend_usd=0.25, captured_at="2026-09-12T00:00:00Z"),
        detail="preserved",
        credential_source="/credential",
    )
    expected = {field.name: getattr(result, field.name) for field in dataclasses.fields(result)}

    reclassified = _classify_auth_failure(
        object(),
        result,
        evidence=decode_codex_events(fatal_auth_lines()),
        markers=(CODEX_REFUSAL_MARKER,),
    )

    assert reclassified.termination is Termination.PRE_AGENT_FAILURE
    assert {
        field.name: getattr(reclassified, field.name) for field in dataclasses.fields(result)
    } == expected | {"termination": Termination.PRE_AGENT_FAILURE}


def test_typed_pre_agent_refusal_charges_no_attempt() -> None:
    history = [
        AttemptRecord(
            attempt=1,
            persona="implementer",
            verdict=OverallVerdict.FAIL,
            pre_agent=True,
        )
    ]

    assert _attempts_spent(history, VerificationConfig()) == 0


def test_only_final_agent_message_can_ask_the_operator() -> None:
    marker = "## OPERATOR QUESTION\nWhich declaration owns this value?"
    lines = [
        line({"type": "thread.started", "thread_id": "thread-current"}),
        line({"type": "item.started", "item": {"id": "item-0", "type": "reasoning", "text": marker}}),
        line(
            {
                "type": "item.completed",
                "item": {
                    "id": "item-1",
                    "type": "command_execution",
                    "command": "echo",
                    "aggregated_output": marker,
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
                    "path": "fixture",
                    "kind": "update",
                },
            }
        ),
        line({"type": "item.completed", "item": {"id": "item-3", "type": "error", "message": marker}}),
        line({"type": "item.completed", "item": {"id": "item-4", "type": "agent_message", "text": "working"}}),
        line({"type": "item.completed", "item": {"id": "item-5", "type": "agent_message", "text": marker}}),
    ]
    evidence = decode_codex_events(lines)

    assert evidence.agent_messages[0].text != evidence.final_message.text
    assert detect_operator_question_text("working") is None
    assert detect_operator_question_text(marker) is not None
    assert evidence.final_message is not None
    assert evidence.final_message.text == marker


def test_question_controls_cover_every_non_agent_item_and_non_final_message() -> None:
    marker = "## OPERATOR QUESTION\nWhich declaration owns this value?"
    items = [
        {"id": "item-0", "type": "reasoning", "text": marker},
        {"id": "item-1", "type": "command_execution", "command": "echo", "aggregated_output": marker, "exit_code": 0},
        {"id": "item-2", "type": "file_change", "path": "fixture", "kind": "update"},
        {"id": "item-3", "type": "error", "message": marker},
    ]
    lines = [
        line({"type": "thread.started", "thread_id": "thread-current"}),
        *[line({"type": "item.started", "item": item}) for item in items],
        *[line({"type": "item.completed", "item": item}) for item in items],
        line({"type": "item.completed", "item": {"id": "item-4", "type": "agent_message", "text": marker}}),
        line({"type": "item.completed", "item": {"id": "item-5", "type": "agent_message", "text": "done"}}),
    ]
    evidence = decode_codex_events(lines)

    assert [message.text for message in evidence.agent_messages] == [marker, "done"]
    assert evidence.final_message is not None
    assert detect_operator_question_text(evidence.final_message.text) is None


async def test_marker_in_a_fixture_file_is_not_an_agent_message(
    tmp_path: Path,
) -> None:
    marker = "## OPERATOR QUESTION\nWhich declaration owns this value?"
    archive = tmp_path / "archive"
    write_typed_fixture(
        archive,
        [
            line(
                {
                    "type": "item.completed",
                    "item": {"id": "item-final", "type": "agent_message", "text": "done"},
                }
            )
        ],
    )
    (archive / "fixture.txt").write_text(marker, encoding="utf-8")

    marker_result = await detect_operator_question_activity(
        DetectQuestionInput(transcript_path=str(archive))
    )

    assert marker_result.is_question is False


def test_typed_pre_agent_detail_preserves_every_unrelated_field(
    tmp_path: Path,
) -> None:
    from factory.activities.agent_activities import _attach_pre_agent_detail

    result = AdapterResult(
        termination=Termination.PRE_AGENT_FAILURE,
        transcript_path=str(tmp_path / "archive"),
        last_snapshot=UsageSnapshot(spend_usd=0.25, captured_at="2026-09-12T00:00:00Z"),
        detail="old",
        credential_source="/credential",
    )
    expected = {field.name: getattr(result, field.name) for field in dataclasses.fields(result)}

    write_typed_fixture(Path(result.transcript_path), fatal_auth_lines())

    enriched = _attach_pre_agent_detail(result)

    assert enriched.detail != "old"
    assert {
        field.name: getattr(enriched, field.name) for field in dataclasses.fields(result)
    } == expected | {"detail": enriched.detail}


def test_question_detection_consumes_one_final_message() -> None:
    marker = "## OPERATOR QUESTION\nWhich declaration owns this value?"

    marker_result = detect_operator_question_text(marker)
    none_result = detect_operator_question_text("working")

    assert marker_result.is_question is True
    assert marker_result.text == "Which declaration owns this value?"
    assert none_result is None


async def test_archived_typed_question_reads_only_the_current_final_message(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "transcript"
    archive.mkdir()
    (archive / "codex-events.jsonl").write_text(
        "\n".join(
            [
                line(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "item-reason",
                            "type": "reasoning",
                            "text": "## OPERATOR QUESTION\nearly",
                        },
                    }
                ),
                line(
                    {
                        "type": "item.completed",
                        "item": {"id": "item-final", "type": "agent_message", "text": "done"},
                    }
                ),
            ]
        )
        + "\n"
    )

    marker = await detect_operator_question_activity(
        DetectQuestionInput(transcript_path=str(archive))
    )
    final_message = final_message_from_archive(archive)

    assert marker.is_question is False
    assert final_message == "done"
