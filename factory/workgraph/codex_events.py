"""Typed, redacted evidence from one Codex ``--json`` execution."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import BinaryIO


class TurnOutcome(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class EvidenceStatus(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class CodexUsage:
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_output_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class CodexItem:
    item_type: str
    item_id: str
    status: str = ""
    text: str = ""


@dataclass(frozen=True, slots=True)
class CodexAgentMessage:
    item_id: str
    text: str


@dataclass(frozen=True, slots=True)
class CodexFatalEvent:
    message: str
    event_types: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CodexExecutionEvidence:
    thread_id: str | None
    current_turn_started: bool
    turn_outcome: TurnOutcome
    items: tuple[CodexItem, ...] = ()
    agent_messages: tuple[CodexAgentMessage, ...] = ()
    fatal_events: tuple[CodexFatalEvent, ...] = ()
    usage: CodexUsage | None = None
    final_message: str | None = None
    status: EvidenceStatus = EvidenceStatus.INCOMPLETE
    reasons: tuple[str, ...] = ()


class CodexEventDecoder:
    """Incremental decoder for stdout emitted by ``codex exec --json``."""

    def __init__(self, raw_sink: BinaryIO | None = None) -> None:
        self._raw_sink = raw_sink
        self._pending = bytearray()
        self._thread_id: str | None = None
        self._turn_started = False
        self._turn_outcome = TurnOutcome.PENDING
        self._items: list[CodexItem] = []
        self._agent_messages: list[CodexAgentMessage] = []
        self._fatal_events: list[CodexFatalEvent] = []
        self._fatal_types: dict[str, list[str]] = {}
        self._usage: CodexUsage | None = None
        self._reasons: list[str] = []

    def feed(self, data: bytes | str) -> None:
        if isinstance(data, str):
            data = data.encode("utf-8")
        if self._raw_sink is not None:
            self._raw_sink.write(data)
        self._pending.extend(data)
        while b"\n" in self._pending:
            raw, self._pending = self._pending.split(b"\n", 1)
            self._decode_line(raw.decode("utf-8", errors="replace"))

    def finish(self) -> CodexExecutionEvidence:
        if self._pending:
            pending = bytes(self._pending)
            self._pending.clear()
            self._decode_line(pending.decode("utf-8", errors="replace"))
        complete = self._turn_outcome is not TurnOutcome.PENDING
        status = EvidenceStatus.INVALID if self._reasons else (
            EvidenceStatus.COMPLETE if complete else EvidenceStatus.INCOMPLETE
        )
        return CodexExecutionEvidence(
            thread_id=self._thread_id,
            current_turn_started=self._turn_started,
            turn_outcome=self._turn_outcome,
            items=tuple(self._items),
            agent_messages=tuple(self._agent_messages),
            fatal_events=tuple(
                CodexFatalEvent(
                    event.message,
                    tuple(self._fatal_types.get(event.message, event.event_types)),
                )
                for event in self._fatal_events
            ),
            usage=self._usage,
            final_message=(
                self._agent_messages[-1].text if self._agent_messages else None
            ),
            status=status,
            reasons=tuple(self._reasons),
        )

    def _decode_line(self, line: str) -> None:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return
        event_type = event.get("type")
        if event_type == "thread.started":
            self._thread_id = event.get("thread_id")
            return
        if event_type == "turn.started":
            self._turn_started = True
            return
        if event_type == "turn.completed":
            self._turn_outcome = TurnOutcome.COMPLETED
            self._read_usage(event.get("usage"))
            return
        if event_type == "turn.failed":
            self._turn_outcome = TurnOutcome.FAILED
            self._read_fatal(event.get("error"), "turn.failed")
            return
        if event_type == "error":
            self._read_fatal(event, "error")
            return
        if event_type == "item.started" or event_type == "item.completed":
            item = event.get("item")
            if isinstance(item, dict):
                self._read_item(item)

    def _read_usage(self, usage: object) -> None:
        if not isinstance(usage, dict):
            return
        self._usage = CodexUsage(
            input_tokens=self._token_count(usage.get("input_tokens")),
            cached_input_tokens=self._token_count(
                usage.get("cached_input_tokens")
            ),
            output_tokens=self._token_count(usage.get("output_tokens")),
            reasoning_output_tokens=self._token_count(
                usage.get("reasoning_output_tokens")
            ),
        )

    @staticmethod
    def _token_count(value: object) -> int | None:
        return value if isinstance(value, int) and value >= 0 else None

    def _read_fatal(self, event: dict[str, object], event_type: str) -> None:
        error = event.get("error", event)
        message = error.get("message") if isinstance(error, dict) else None
        if isinstance(message, str):
            for fatal in self._fatal_events:
                if fatal.message == message:
                    if event_type not in fatal.event_types:
                        self._fatal_types[message].append(event_type)
                    return
            self._fatal_events.append(CodexFatalEvent(message, (event_type,)))
            self._fatal_types[message] = [event_type]

    def _read_item(self, item: dict[str, object]) -> None:
        item_type = item.get("type")
        if not isinstance(item_type, str):
            return
        item_id = item.get("id")
        if not isinstance(item_id, str):
            item_id = ""
        text = item.get("text")
        if not isinstance(text, str):
            message = item.get("message")
            text = message if isinstance(message, str) else ""
        status = item.get("status")
        if not isinstance(status, str):
            status = ""
        if item_type == "agent_message":
            self._agent_messages.append(CodexAgentMessage(item_id, text))
            return
        self._items.append(CodexItem(item_type, item_id, status, text))
