"""US2: a Codex attempt archives only its own current execution."""

from __future__ import annotations

import asyncio
from dataclasses import fields
import json
from pathlib import Path
from typing import Callable

import pytest

from factory.usage.models import Termination
from factory.workgraph.models import AdapterResult
from factory.workgraph.adapter import (
    ATTEMPT_ARCHIVE_ENV,
    CODEX_EVENTS_NAME,
    CODEX_STDERR_NAME,
    HostAgentBackend,
    home_path,
    SharedAttemptPolicy,
    STDOUT_LOG_NAME,
    transcript_dir,
)
from factory.workgraph.models import AttemptContext
from tests.stub_codex import install_as, write_control
from tests.stub_agent import write_control as write_agent_control

EPIC = "160-each-codex-attempt-owns-its-evidence"
NODE = "us2"
ATTEMPT = 2
SESSION_ID = "f8e3d2c1-b4a5-4f80-9c1a-7e6d5b4a3c99"
MODEL_ALIAS = "ollama-cloud/glm-5.3-flash"
PROXY_URL = "http://litellm.test:4000"
VIRTUAL_KEY = "sk-virtual-160-each-codex-attempt-owns-its-evidence-us2-2"
PROMPT = "You are the implementer persona.\n\n## Scope\n\nImplement US2.\n"


@pytest.fixture
def codex_bin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_as(tmp_path / "bin", "codex")
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}:{_path()}")


def _path() -> str:
    import os

    return os.environ["PATH"]


async def _wait_for_stub(worktree: Path) -> None:
    marker = worktree / ".stub-codex" / "1" / "stdin.txt"
    for _ in range(200):
        if marker.is_file():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("stub codex did not launch")


@pytest.fixture
def worktree(tmp_path: Path) -> Path:
    path = tmp_path / "worktrees" / EPIC / NODE
    path.mkdir(parents=True)
    return path


@pytest.fixture
def factory_root(tmp_path: Path) -> Path:
    return tmp_path / ".factory"


@pytest.fixture
def node_home(factory_root: Path) -> Path:
    return home_path(factory_root, EPIC, NODE)


@pytest.fixture
def attempt(worktree: Path, node_home: Path) -> Callable[..., AttemptContext]:
    def build(**overrides: object) -> AttemptContext:
        fields: dict[str, object] = {
            "epic_id": EPIC,
            "node_id": NODE,
            "attempt": ATTEMPT,
            "prompt": PROMPT,
            "worktree_path": str(worktree),
            "home_path": str(node_home),
            "proxy_url": PROXY_URL,
            "virtual_key": VIRTUAL_KEY,
            "model_alias": MODEL_ALIAS,
            "session_id": SESSION_ID,
            "timeout_s": 60,
            "agent": "codex",
            "route": "gateway",
        }
        return AttemptContext(**(fields | overrides))

    return build


@pytest.fixture
def adapter(node_home: Path) -> object:
    from factory.workgraph.adapter import CodexAdapter

    return CodexAdapter(
        executable="codex",
        grace_s=0.4,
        backend=HostAgentBackend(executable="codex"),
    )


@pytest.fixture
def claude_adapter(node_home: Path) -> object:
    from factory.workgraph.adapter import ClaudeCodeAdapter
    from tests.stub_agent import STUB_AGENT_PATH

    return ClaudeCodeAdapter(
        executable=str(STUB_AGENT_PATH),
        grace_s=0.4,
        backend=HostAgentBackend(executable=str(STUB_AGENT_PATH)),
    )


async def test_a_prior_rollout_is_not_this_attempts_turn_evidence(
    codex_bin: None,
    adapter: object,
    attempt: Callable[..., AttemptContext],
    worktree: Path,
    factory_root: Path,
    node_home: Path,
) -> None:
    """A rollout from a prior attempt cannot make a pre-thread failure current."""
    rollout = node_home / ".codex" / "sessions" / "2026" / "09" / "10"
    rollout.mkdir(parents=True)
    prior_rollout = rollout / "rollout-prior-attempt.jsonl"
    prior_rollout.write_text('{"type":"thread.started","thread_id":"thread-old"}\n')
    write_control(
        node_home,
        exit_code=1,
        write_rollout=False,
        stdout="codex: provider configuration is invalid\n",
    )

    result = await adapter.run_attempt(attempt(), factory_root=factory_root)
    evidence = adapter._turn_happened(attempt(), worktree, {})

    assert result.termination == Termination.PRE_AGENT_FAILURE
    assert evidence is False
    current_archive = transcript_dir(factory_root, EPIC, NODE, ATTEMPT)
    assert list(current_archive.glob("rollout-*.jsonl")) == []


@pytest.mark.parametrize(
    "fatal_message",
    [
        "unexpected status 401 Unauthorized",
        "missing CODEX_GATEWAY_KEY provider configuration",
    ],
)
async def test_startup_and_errors_are_not_a_model_turn(
    codex_bin: None,
    adapter: object,
    attempt: Callable[..., AttemptContext],
    factory_root: Path,
    node_home: Path,
    fatal_message: str,
) -> None:
    """Protocol startup plus errors never becomes model-authored evidence."""
    from factory.workgraph.codex_events import decode_codex_events

    stream = [
        {"type": "thread.started", "thread_id": "thread-current"},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {"id": "item-error", "type": "error", "message": "diagnostic"},
        },
        {"type": "error", "message": fatal_message},
        {"type": "turn.failed", "error": {"message": fatal_message}},
    ]
    write_control(
        node_home,
        exit_code=1,
        write_rollout=False,
        stdout="".join(f"{json.dumps(event)}\n" for event in stream),
        stderr="provider diagnostic\n",
    )

    result = await adapter.run_attempt(attempt(), factory_root=factory_root)
    archive = transcript_dir(factory_root, EPIC, NODE, ATTEMPT)
    raw_events = (archive / CODEX_EVENTS_NAME).read_bytes()
    raw_stderr = (archive / CODEX_STDERR_NAME).read_bytes()
    evidence = decode_codex_events(raw_events.splitlines(keepends=True))

    assert result.termination == Termination.PRE_AGENT_FAILURE
    assert evidence.thread_id == "thread-current"
    assert evidence.turn_started is True
    assert evidence.agent_took_a_turn is False
    assert evidence.final_message is None
    assert any(
        fatal_message in event.message for event in evidence.fatal_events
    )
    assert b"provider diagnostic" in raw_stderr


@pytest.mark.parametrize(
    ("timeout_s", "expected"),
    [(60, Termination.COMPLETED), (1, Termination.TIMEOUT)],
)
async def test_current_thread_archives_one_identity_across_endings(
    codex_bin: None,
    adapter: object,
    attempt: Callable[..., AttemptContext],
    worktree: Path,
    factory_root: Path,
    node_home: Path,
    timeout_s: int,
    expected: Termination,
) -> None:
    """Normal and timed-out runs keep one current thread in one archive."""
    stream = [
        {"type": "thread.started", "thread_id": "thread-current"},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {
                "id": "item-message",
                "type": "agent_message",
                "text": "The answer is ready.",
            },
        },
        {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 2}},
    ]
    prior = node_home / ".codex" / "sessions" / "prior"
    prior.mkdir(parents=True)
    (prior / "rollout-prior.jsonl").write_text('{"type":"thread.started","thread_id":"old"}\n')
    write_control(
        node_home,
        sleep_s=2.0 if timeout_s == 1 else 0.0,
        write_rollout=True,
        rollout_text='{"type":"thread.started","thread_id":"thread-current"}\n',
        stdout="".join(f"{json.dumps(event)}\n" for event in stream),
    )

    result = await adapter.run_attempt(
        attempt(timeout_s=timeout_s), factory_root=factory_root
    )
    archive = transcript_dir(factory_root, EPIC, NODE, ATTEMPT)

    assert result.termination == expected
    raw_events = (archive / CODEX_EVENTS_NAME).read_bytes()
    assert b"thread-current" in raw_events
    assert b"old" not in raw_events
    rollouts = list(archive.glob("rollout-*.jsonl"))
    assert len(rollouts) == 1
    assert b"thread-current" in rollouts[0].read_bytes()


async def test_cancellation_still_archives_the_current_partial_stream(
    codex_bin: None,
    adapter: object,
    attempt: Callable[..., AttemptContext],
    worktree: Path,
    factory_root: Path,
    node_home: Path,
) -> None:
    """A kill after the current thread started cannot lose the stream."""
    stream = [
        {"type": "thread.started", "thread_id": "thread-current"},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"id": "reason", "type": "reasoning", "text": "working"}},
    ]
    write_control(
        node_home,
        sleep_s=5.0,
        write_rollout=False,
        stdout="".join(f"{json.dumps(event)}\n" for event in stream),
    )
    run = asyncio.create_task(adapter.run_attempt(attempt(), factory_root=factory_root))
    await _wait_for_stub(worktree)
    run.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run

    raw = transcript_dir(factory_root, EPIC, NODE, ATTEMPT) / CODEX_EVENTS_NAME
    assert b"thread-current" in raw.read_bytes()


async def test_finalization_retry_does_not_duplicate_the_current_rollout(
    codex_bin: None,
    adapter: object,
    attempt: Callable[..., AttemptContext],
    worktree: Path,
    factory_root: Path,
    node_home: Path,
) -> None:
    """A redelivered archival call is idempotent, not a second attempt."""
    stream = [{"type": "thread.started", "thread_id": "thread-current"}]
    write_control(
        node_home,
        write_rollout=True,
        rollout_text='{"type":"thread.started","thread_id":"thread-current"}\n',
        stdout="".join(f"{json.dumps(event)}\n" for event in stream),
    )
    result = await adapter.run_attempt(attempt(), factory_root=factory_root)
    archive = transcript_dir(factory_root, EPIC, NODE, ATTEMPT)

    SharedAttemptPolicy(adapter)._archive_session(
        attempt(), worktree, {ATTEMPT_ARCHIVE_ENV: str(archive)}, archive
    )

    assert len(list(archive.glob("rollout-*.jsonl"))) == 1


async def test_codex_and_claude_keep_the_same_plain_adapter_contract(
    codex_bin: None,
    adapter: object,
    claude_adapter: object,
    attempt: Callable[..., AttemptContext],
    worktree: Path,
    factory_root: Path,
    node_home: Path,
) -> None:
    """Codex's JSONL stays behind the neutral evidence; consumers see plain text."""
    stream = [
        {"type": "thread.started", "thread_id": "thread-current"},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {"id": "item-message", "type": "agent_message", "text": "Done."},
        },
        {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 2}},
    ]
    write_control(
        node_home,
        write_rollout=False,
        stdout="".join(f"{json.dumps(event)}\n" for event in stream),
    )
    codex_result = await adapter.run_attempt(attempt(), factory_root=factory_root)
    codex_plain_log = (
        transcript_dir(factory_root, EPIC, NODE, ATTEMPT) / STDOUT_LOG_NAME
    ).read_text()
    write_agent_control(node_home, stdout="Done.")
    claude_result = await claude_adapter.run_attempt(
        attempt(agent="claude-code", route="gateway"), factory_root=factory_root
    )

    codex_fields = tuple(field.name for field in fields(AdapterResult))
    assert tuple(field.name for field in fields(type(codex_result))) == codex_fields
    assert tuple(field.name for field in fields(type(claude_result))) == codex_fields
    assert codex_plain_log == "Done.\n"
    assert '"type": "agent_message"' not in codex_plain_log
    SharedAttemptPolicy,
