"""US3: typed Codex current events decide refusals, not quoted text."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from dataclasses import fields as dataclass_fields
from pathlib import Path

from factory.usage.models import Termination
from factory.workgraph.adapter import CODEX_EVENTS_NAME, ATTEMPT_ARCHIVE_ENV, CodexAdapter
from factory.workgraph.adapter import ClaudeCodeAdapter, HostAgentBackend, SUBSCRIPTION_REFUSAL_MARKER
from factory.workgraph.codex_events import decode_codex_events
from factory.activities.agent_activities import _classify_auth_failure
from factory.workgraph.models import AdapterResult, AttemptContext
from tests.stub_agent import STUB_AGENT_PATH, write_control
from factory.verify.question import detect_codex_question
import pytest
from temporalio.testing import ActivityEnvironment


AUTH_MARKERS = ("unexpected status 401 Unauthorized",)
QUOTED_AUTH_TEXT = (
    'the previous attempt saw "unexpected status 401 Unauthorized" and recovered'
)


def _codex_events_file(tmp_path: Path, events: list[dict[str, object]]) -> Path:
    archive = tmp_path / "attempt"
    archive.mkdir()
    raw = "".join(f"{json.dumps(event)}\n" for event in events).encode()
    (archive / CODEX_EVENTS_NAME).write_bytes(raw)
    (archive / "stdout.log").write_text(f"{QUOTED_AUTH_TEXT}\n{QUOTED_AUTH_TEXT}\n")
    return archive


def _evidence(tmp_path: Path, events: list[dict[str, object]]):
    adapter = CodexAdapter()
    archive = _codex_events_file(tmp_path, events)
    return adapter._current_evidence({ATTEMPT_ARCHIVE_ENV: str(archive)})


def _decode(events: list[dict[str, object]]):
    return decode_codex_events(
        [f"{json.dumps(event)}\n" for event in events]
    )


@dataclass
class EvidenceAdapter:
    evidence: object

    def _current_evidence(self, _env: dict[str, str]):
        return self.evidence

    def _refusal_markers(self):
        return AUTH_MARKERS


def test_classification_does_not_fall_back_to_quoted_combined_text(
    tmp_path: Path,
) -> None:
    """A complete typed non-auth pair ends the legacy substring fallback."""

    fatal_message = (
        '{"error":{"code":"invalid_request",'
        '"message":"unexpected status 401 Unauthorized from history"}}'
    )
    events = [
        {"type": "thread.started", "thread_id": "thread-current"},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {
                "id": "changed-fixture",
                "type": "file_change",
                "path": "tests/quoted-401.txt",
                "change_kind": "add",
            },
        },
        {"type": "error", "message": fatal_message},
        {"type": "turn.failed", "error": {"message": fatal_message}},
    ]
    evidence = _evidence(tmp_path, events)
    result = Termination.PRE_AGENT_FAILURE

    result = _classify_auth_failure(
        EvidenceAdapter(evidence),
        AdapterResult(
            termination=Termination.PRE_AGENT_FAILURE,
            transcript_path=str(tmp_path / "attempt"),
            credential_source="gateway",
        ),
    )

    assert result.termination == Termination.PRE_AGENT_FAILURE


def test_a_matching_typed_auth_pair_is_one_pre_agent_refusal(tmp_path: Path) -> None:
    """The exact measured error/terminal pair, with diagnostics, is one refusal."""

    fatal_message = "unexpected status 401 Unauthorized"
    events = [
        {"type": "thread.started", "thread_id": "thread-current"},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {
                "id": "diagnostic",
                "type": "error",
                "message": "provider request started",
            },
        },
        {"type": "error", "message": fatal_message},
        {"type": "turn.failed", "error": {"message": fatal_message}},
    ]
    evidence = _evidence(tmp_path, events)

    from factory.activities.agent_activities import (
        _attach_pre_agent_detail,
        _typed_codex_auth_outcome,
    )
    from factory.workgraph.models import AdapterResult

    assert evidence.fatal_events[-1].source.value == "turn.failed"
    assert _typed_codex_auth_outcome(
        evidence, AUTH_MARKERS, Termination.PRE_AGENT_FAILURE
    ) == Termination.AUTH_FAILURE
    described = _attach_pre_agent_detail(
        AdapterResult(
            termination=Termination.AUTH_FAILURE,
            transcript_path=str(tmp_path / "attempt"),
        )
    )
    assert described.detail == fatal_message


def test_an_auth_error_and_unrelated_terminal_stay_ordinary(tmp_path: Path) -> None:
    """Two nearby failures are not one matching authentication pair."""

    auth_message = "unexpected status 401 Unauthorized"
    unrelated = "the response failed schema validation"
    events = [
        {"type": "thread.started", "thread_id": "thread-current"},
        {"type": "turn.started"},
        {"type": "error", "message": auth_message},
        {"type": "turn.failed", "error": {"message": unrelated}},
    ]
    evidence = _evidence(tmp_path, events)

    from factory.activities.agent_activities import _typed_codex_auth_outcome

    assert _typed_codex_auth_outcome(
        evidence, AUTH_MARKERS, Termination.PRE_AGENT_FAILURE
    ) == Termination.PRE_AGENT_FAILURE


def test_only_the_final_agent_message_can_ask() -> None:

    marker = "## OPERATOR QUESTION\nWhich option should we take?"
    for event in [
        {"id": "thought", "type": "reasoning", "text": marker},
        {
            "id": "command",
            "type": "command_execution",
            "command": "cat",
            "output": marker,
            "exit_code": 0,
        },
        {
            "id": "fixture",
            "type": "file_change",
            "path": "tests/quoted-## OPERATOR QUESTION.txt",
            "change_kind": "add",
        },
        {
            "id": "diagnostic",
            "type": "error",
            "message": marker,
        },
    ]:
        events = [
            {"type": "thread.started", "thread_id": "thread-question"},
            {"type": "turn.started"},
            {"type": "item.completed", "item": event},
            {
                "type": "item.completed",
                "item": {"id": "final", "type": "agent_message", "text": "Done."},
            },
            {"type": "turn.completed", "usage": {}},
        ]
        assert detect_codex_question(_decode(events)) is None

    events = [
        {"type": "thread.started", "thread_id": "thread-question"},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {"id": "earlier", "type": "agent_message", "text": marker},
        },
        {
            "type": "item.completed",
            "item": {"id": "final", "type": "agent_message", "text": "Done."},
        },
        {"type": "turn.completed", "usage": {}},
    ]
    assert detect_codex_question(_decode(events)) is None


def test_the_final_agent_message_satisfying_the_marker_asks() -> None:
    marker = "## OPERATOR QUESTION\nThe fork: A or B. I lean A."
    events = [
        {"type": "thread.started", "thread_id": "thread-question"},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {"id": "thought", "type": "reasoning", "text": marker},
        },
        {
            "type": "item.completed",
            "item": {"id": "final", "type": "agent_message", "text": marker},
        },
        {"type": "turn.completed", "usage": {}},
    ]

    detected = detect_codex_question(_decode(events))
    assert detected is not None
    assert detected.is_question is True
    assert detected.text == "The fork: A or B. I lean A."


def test_reclassification_preserves_every_current_result_field(
    tmp_path: Path,
) -> None:
    """A class change is an immutable replacement, not a rebuild."""

    fatal_message = "unexpected status 401 Unauthorized"
    evidence = _evidence(
        tmp_path,
        [
            {"type": "thread.started", "thread_id": "thread-current"},
            {"type": "turn.started"},
            {"type": "error", "message": fatal_message},
            {"type": "turn.failed", "error": {"message": fatal_message}},
        ],
    )
    baseline = AdapterResult(
        termination=Termination.AGENT_ERROR,
        transcript_path=str(tmp_path / "attempt"),
        last_snapshot=None,
        detail="the process said this",
        credential_source="gateway",
    )
    before = {
        field.name: getattr(baseline, field.name)
        for field in dataclass_fields(AdapterResult)
    }
    raw_before = (tmp_path / "attempt" / CODEX_EVENTS_NAME).read_bytes()
    stdout_before = (tmp_path / "attempt" / "stdout.log").read_bytes()

    classified = _classify_auth_failure(EvidenceAdapter(evidence), baseline)

    assert dataclass_fields(classified) == dataclass_fields(baseline)
    for field in dataclass_fields(AdapterResult):
        expected = (
            Termination.AUTH_FAILURE
            if field.name == "termination"
            else before[field.name]
        )
        assert getattr(classified, field.name) == expected
    assert (tmp_path / "attempt" / CODEX_EVENTS_NAME).read_bytes() == raw_before
    assert (tmp_path / "attempt" / "stdout.log").read_bytes() == stdout_before


async def test_landed_claude_auth_control_keeps_combined_log_behavior(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production Claude still classifies its real combined-log refusal."""

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    factory_root = tmp_path / "factory"
    home_path = factory_root / "homes" / "160" / "claude"
    worktree = factory_root / "worktrees" / "claude"
    worktree.mkdir(parents=True)
    home_path.mkdir(parents=True)
    write_control(
        home_path,
        exit_code=1,
        write_transcript=False,
        stdout=SUBSCRIPTION_REFUSAL_MARKER,
    )
    adapter = ClaudeCodeAdapter(
        executable=str(STUB_AGENT_PATH),
        backend=HostAgentBackend(executable=str(STUB_AGENT_PATH)),
    )
    context = AttemptContext(
        epic_id="160",
        node_id="claude",
        attempt=1,
        prompt="Claude conformance control.",
        worktree_path=str(worktree),
        home_path=str(home_path),
        proxy_url="http://litellm.test:4000",
        virtual_key="virtual-key-160-claude-1",
        model_alias="claude-control",
        session_id="d0a2fbb0-fb9f-5df1-8d4f-d8f37f7ad5b5",
        timeout_s=60,
        agent="claude-code",
        route="gateway",
    )

    adapter_result = await adapter.run_attempt(context, factory_root=factory_root)
    result = _classify_auth_failure(adapter, adapter_result)

    assert result.termination == Termination.AUTH_FAILURE
    assert not (Path(result.transcript_path) / CODEX_EVENTS_NAME).exists()


def test_a_typed_400_body_with_quoted_401_text_stays_non_auth(
    tmp_path: Path,
) -> None:
    """The non-auth fatal body is terminal even when it quotes the 401 marker."""

    quoted_401 = (
        '{"error":{"code":"invalid_request","message":"retry context included '
        'unexpected status 401 Unauthorized"}}'
    )
    events = [
        {"type": "thread.started", "thread_id": "thread-current"},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {"id": "thought", "type": "reasoning", "text": QUOTED_AUTH_TEXT},
        },
        {
            "type": "item.completed",
            "item": {
                "id": "command",
                "type": "command_execution",
                "command": "pytest -q",
                "output": QUOTED_AUTH_TEXT,
                "exit_code": 1,
            },
        },
        {"type": "error", "message": quoted_401},
        {"type": "turn.failed", "error": {"message": quoted_401}},
    ]
    evidence = _evidence(tmp_path, events)

    from factory.activities.agent_activities import _typed_codex_auth_outcome

    outcome = _typed_codex_auth_outcome(
        evidence, AUTH_MARKERS, Termination.PRE_AGENT_FAILURE
    )

    assert outcome == Termination.PRE_AGENT_FAILURE
