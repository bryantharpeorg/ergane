"""A pure decoder for the JSONL stream emitted by ``codex exec --json``."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable


MALFORMED_KNOWN_EVENT = "malformed-known-event"
UNKNOWN_EVENT = "unknown-event"
CROSS_THREAD_EVENT = "cross-thread-event"
MISSING_THREAD_START = "missing-thread-start"
DUPLICATE_TERMINAL = "duplicate-terminal"
INVALID_JSON = "invalid-json"
MALFORMED_USAGE = "malformed-usage"
UNTERMINATED_LINE = "unterminated-line"

_MAX_TEXT_LENGTH = 512
_MAX_SERIALIZED_LENGTH = 8_192
_TOKEN_PATTERN = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9_]{8,}|Bearer\s+\S+)",
    re.IGNORECASE,
)


class TurnOutcome(StrEnum):
    """The one terminal fact a turn may carry."""

    NO_TURN = "no_turn"
    COMPLETED = "completed"
    FAILED = "failed"


class EvidenceCompleteness(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    INVALID = "invalid"


class ItemKind(StrEnum):
    REASONING = "reasoning"
    COMMAND_EXECUTION = "command_execution"
    FILE_CHANGE = "file_change"
    AGENT_MESSAGE = "agent_message"
    ERROR = "error"


class FatalSource(StrEnum):
    ERROR_EVENT = "error"
    TURN_FAILED = "turn.failed"


@dataclass(frozen=True)
class DecoderDiagnostic:
    code: str
    line_number: int | None = None
    detail: str = ""


@dataclass(frozen=True)
class Reason(DecoderDiagnostic):
    """A stable decoder reason, without any raw input."""


@dataclass(frozen=True)
class CodexItem:
    item_id: str
    kind: ItemKind


@dataclass(frozen=True)
class ReasoningItem(CodexItem):
    text: str = ""


@dataclass(frozen=True)
class CommandOutputItem(CodexItem):
    command: str = ""
    output: str = ""
    exit_code: int | None = None


@dataclass(frozen=True)
class FileChangeItem(CodexItem):
    path: str = ""
    change_kind: str = ""


@dataclass(frozen=True)
class AgentMessage(CodexItem):
    text: str

@dataclass(frozen=True)
class DiagnosticItem:
    item_id: str
    message: str


@dataclass(frozen=True)
class CodexFatalEvent:
    source: FatalSource
    message: str


@dataclass(frozen=True)
class UsageEvidence:
    input_tokens: int | None
    output_tokens: int | None
    invalid_fields: tuple[str, ...]
    reason: str | None = None


@dataclass(frozen=True)
class CodexExecutionEvidence:
    """Typed current-run evidence; raw events stay in the caller's spool."""

    thread_id: str | None
    turn_started: bool
    turn_outcome: TurnOutcome
    agent_messages: tuple[AgentMessage, ...]
    items: tuple[CodexItem, ...]
    reasoning: tuple[ReasoningItem, ...]
    command_outputs: tuple[CommandOutputItem, ...]
    file_changes: tuple[FileChangeItem, ...]
    diagnostic_items: tuple[DiagnosticItem, ...]
    fatal_events: tuple[CodexFatalEvent, ...]
    usage: UsageEvidence | None
    completeness: EvidenceCompleteness
    reasons: tuple[Reason, ...]

    @property
    def final_message(self) -> AgentMessage | None:
        return self.agent_messages[-1] if self.agent_messages else None

    @property
    def agent_took_a_turn(self) -> bool:
        """Whether model-authored output exists, independent of protocol startup."""

        return bool(self.agent_messages)

    def _redacted(self) -> dict[str, object]:
        """Build a bounded orchestration rendering; internal by design."""

        usage = None
        if self.usage is not None:
            usage = {
                "input_tokens": self.usage.input_tokens,
                "output_tokens": self.usage.output_tokens,
                "invalid_fields": list(self.usage.invalid_fields),
                "reason": self.usage.reason,
            }
        return {
            "thread_id": _redact(self.thread_id),
            "turn_started": self.turn_started,
            "turn_outcome": self.turn_outcome.value,
            "agent_took_a_turn": self.agent_took_a_turn,
            "final_message": _redact(self.final_message.text) if self.final_message else None,
            "agent_message_count": len(self.agent_messages),
            "agent_messages": [_redact(message.text) for message in self.agent_messages],
            "item_counts": {
                "reasoning": len(self.reasoning),
                "command_execution": len(self.command_outputs),
                "file_change": len(self.file_changes),
                "error": len(self.diagnostic_items),
            },
            "fatal_event_count": len(self.fatal_events),
            "fatal_events": [
                {"source": event.source.value, "message": _redact(event.message)}
                for event in self.fatal_events
            ],
            "diagnostic_messages": [_redact(item.message) for item in self.diagnostic_items],
            "usage": usage,
            "completeness": self.completeness.value,
            "reasons": [
                {"code": reason.code, "line_number": reason.line_number, "detail": _redact(reason.detail)}
                for reason in self.reasons
            ],
        }

    def redacted_json(self) -> str:
        """Serialize orchestration evidence with secrets removed and bounded."""

        rendered = json.dumps(self._redacted(), separators=(",", ":"), sort_keys=True)
        if len(rendered) > _MAX_SERIALIZED_LENGTH:
            rendered = json.dumps(
                {
                    "completeness": self.completeness.value,
                    "redacted_json_truncated": True,
                    "reasons": [reason.code for reason in self.reasons],
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        return rendered


def _redact(value: str | None) -> str | None:
    if value is None:
        return None
    redacted = _TOKEN_PATTERN.sub("[REDACTED]", value)
    return redacted[:_MAX_TEXT_LENGTH]


class CodexEventDecoder:
    """Incrementally parse JSONL; no filesystem or process access."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._line_number = 0
        self._thread_id: str | None = None
        self._thread_seen = False
        self._turn_started = False
        self._turn_outcome = TurnOutcome.NO_TURN
        self._agent_messages: list[AgentMessage] = []
        self._reasoning: list[ReasoningItem] = []
        self._command_outputs: list[CommandOutputItem] = []
        self._file_changes: list[FileChangeItem] = []
        self._diagnostic_items: list[DiagnosticItem] = []
        self._fatal_events: list[CodexFatalEvent] = []
        self._usage: UsageEvidence | None = None
        self._reasons: list[Reason] = []

    def feed(self, chunk: bytes | str) -> None:
        data = chunk.encode() if isinstance(chunk, str) else chunk
        self._buffer.extend(data)
        while True:
            newline = self._buffer.find(b"\n")
            if newline < 0:
                return
            line = self._buffer[:newline]
            del self._buffer[: newline + 1]
            self._line_number += 1
            self._decode_line(line)

    def finish(self) -> CodexExecutionEvidence:
        if self._buffer:
            self._line_number += 1
            self._reason(UNTERMINATED_LINE, line_number=self._line_number, detail="partial line retained by caller")
            self._buffer.clear()
        if not self._thread_seen:
            self._reason(MISSING_THREAD_START)
        return self._evidence()

    def _decode_line(self, line: bytes) -> None:
        try:
            value = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._reason(INVALID_JSON, line_number=self._line_number)
            return
        if not isinstance(value, dict):
            self._reason(MALFORMED_KNOWN_EVENT, line_number=self._line_number)
            return

        event_type = value.get("type")
        explicit_thread = value.get("thread_id")
        if explicit_thread is not None:
            if not isinstance(explicit_thread, str) or not explicit_thread:
                self._reason(MALFORMED_KNOWN_EVENT, line_number=self._line_number)
                return
            if self._thread_seen and self._thread_id != explicit_thread:
                self._reason(CROSS_THREAD_EVENT, line_number=self._line_number)
                return

        if event_type == "thread.started":
            if explicit_thread is None:
                self._reason(MALFORMED_KNOWN_EVENT, line_number=self._line_number)
                return
            self._thread_seen = True
            self._thread_id = explicit_thread
            return
            return

        if event_type == "turn.started":
            self._turn_started = True
            return

        if event_type in {"item.started", "item.completed"}:
            self._decode_item(value.get("item"), completed=event_type == "item.completed")
            return

        if event_type == "error":
            message = value.get("message")
            if not isinstance(message, str):
                self._reason(MALFORMED_KNOWN_EVENT, line_number=self._line_number)
                return
            self._fatal_events.append(CodexFatalEvent(FatalSource.ERROR_EVENT, message))
            return

        if event_type == "turn.failed":
            error = value.get("error")
            message = error.get("message") if isinstance(error, dict) else None
            if not isinstance(message, str):
                self._reason(MALFORMED_KNOWN_EVENT, line_number=self._line_number)
                return
            self._record_terminal(TurnOutcome.FAILED)
            self._fatal_events.append(CodexFatalEvent(FatalSource.TURN_FAILED, message))
            return

        if event_type == "turn.completed":
            if self._turn_outcome is not TurnOutcome.NO_TURN:
                self._reason(DUPLICATE_TERMINAL, line_number=self._line_number)
                return
            self._turn_outcome = TurnOutcome.COMPLETED
            usage = value.get("usage")
            if not isinstance(usage, dict):
                self._reason(MALFORMED_KNOWN_EVENT, line_number=self._line_number)
                return
            self._decode_usage(usage)
            return

        self._reason(UNKNOWN_EVENT, line_number=self._line_number)

    def _decode_item(self, body: object, *, completed: bool) -> None:
        if not isinstance(body, dict):
            self._reason(MALFORMED_KNOWN_EVENT, line_number=self._line_number)
            return
        explicit_thread = body.get("thread_id")
        if explicit_thread is not None and (self._thread_id is None or explicit_thread != self._thread_id):
            self._reason(CROSS_THREAD_EVENT, line_number=self._line_number)
            return
        item_id = body.get("id")
        kind_value = body.get("type")
        if not isinstance(item_id, str) or not isinstance(kind_value, str):
            self._reason(MALFORMED_KNOWN_EVENT, line_number=self._line_number)
            return
        try:
            kind = ItemKind(kind_value)
        except ValueError:
            self._reason(UNKNOWN_EVENT, line_number=self._line_number)
            return

        if kind is ItemKind.REASONING:
            text = body.get("text") if isinstance(body.get("text"), str) else ""
            self._reasoning.append(ReasoningItem(item_id, kind, text))
            return
        if kind is ItemKind.COMMAND_EXECUTION:
            command = body.get("command") if isinstance(body.get("command"), str) else ""
            output = body.get("aggregated_output") if isinstance(body.get("aggregated_output"), str) else ""
            exit_code = body.get("exit_code") if type(body.get("exit_code")) is int else None
            self._command_outputs.append(CommandOutputItem(item_id, kind, command, output, exit_code))
            return
        if kind is ItemKind.FILE_CHANGE:
            path = body.get("path") if isinstance(body.get("path"), str) else ""
            change_kind = body.get("kind") if isinstance(body.get("kind"), str) else ""
            self._file_changes.append(FileChangeItem(item_id, kind, path, change_kind))
            return
        if kind is ItemKind.AGENT_MESSAGE:
            text = body.get("text")
            if not completed:
                return
            if not isinstance(text, str):
                self._reason(MALFORMED_KNOWN_EVENT, line_number=self._line_number)
                return
            self._agent_messages.append(AgentMessage(item_id=item_id, kind=kind, text=text))
            return
        message = body.get("message")
        if completed and not isinstance(message, str):
            self._reason(MALFORMED_KNOWN_EVENT, line_number=self._line_number)
            return
        if completed:
            self._diagnostic_items.append(DiagnosticItem(item_id, message))

    def _decode_usage(self, usage: dict[str, object]) -> None:
        fields: dict[str, int | None] = {}
        invalid: list[str] = []
        for field in ("input_tokens", "output_tokens"):
            value = usage.get(field)
            if value is None:
                fields[field] = value
            elif type(value) is int and value >= 0:
                fields[field] = value
            else:
                fields[field] = None
                invalid.append(field)
        self._usage = UsageEvidence(fields["input_tokens"], fields["output_tokens"], tuple(invalid))
        if invalid:
            self._usage = UsageEvidence(
                fields["input_tokens"], fields["output_tokens"], tuple(invalid), MALFORMED_USAGE
            )
            self._reason(MALFORMED_USAGE, line_number=self._line_number)

    def _record_terminal(self, outcome: TurnOutcome) -> None:
        if self._turn_outcome is not TurnOutcome.NO_TURN:
            self._reason(DUPLICATE_TERMINAL, line_number=self._line_number)
            return
        self._turn_outcome = outcome

    def _reason(self, code: str, *, line_number: int | None = None, detail: str = "") -> None:
        self._reasons.append(Reason(code, line_number, detail))

    def _evidence(self) -> CodexExecutionEvidence:
        invalid_codes = {
            MALFORMED_KNOWN_EVENT,
            CROSS_THREAD_EVENT,
            DUPLICATE_TERMINAL,
            INVALID_JSON,
            MALFORMED_USAGE,
        }
        if any(reason.code in invalid_codes for reason in self._reasons):
            completeness = EvidenceCompleteness.INVALID
        elif self._reasons:
            completeness = EvidenceCompleteness.INCOMPLETE
        else:
            completeness = EvidenceCompleteness.COMPLETE
        return CodexExecutionEvidence(
            thread_id=self._thread_id,
            turn_started=self._turn_started,
            turn_outcome=self._turn_outcome,
            agent_messages=tuple(self._agent_messages),
            items=(
                *self._reasoning,
                *self._command_outputs,
                *self._file_changes,
                *self._agent_messages,
            ),
            reasoning=tuple(self._reasoning),
            command_outputs=tuple(self._command_outputs),
            file_changes=tuple(self._file_changes),
            diagnostic_items=tuple(self._diagnostic_items),
            fatal_events=tuple(self._fatal_events),
            usage=self._usage,
            completeness=completeness,
            reasons=tuple(self._reasons),
        )


def decode_codex_events(lines: Iterable[bytes | str]) -> CodexExecutionEvidence:
    """Decode complete JSONL bytes; raw input remains owned by the caller."""

    decoder = CodexEventDecoder()
    for line in lines:
        decoder.feed(line)
        if not (isinstance(line, str) and line.endswith("\n")) and not (
            isinstance(line, bytes) and line.endswith(b"\n")
        ):
            decoder.feed(b"\n")
    return decoder.finish()
