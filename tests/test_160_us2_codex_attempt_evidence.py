"""US2: a Codex attempt archives only its own current execution."""

from __future__ import annotations

import asyncio
from dataclasses import fields
import shutil
import json
from pathlib import Path
from typing import Callable

import pytest

from factory.usage.models import Termination
from factory.verify.factory_yaml import parse_factory_config
from factory.workgraph.models import AdapterResult
from factory.workgraph.adapter import (
    ATTEMPT_ARCHIVE_ENV,
    CODEX_EVENTS_NAME,
    CODEX_STDERR_NAME,
    HostAgentBackend,
    home_path,
    SharedAttemptPolicy,
    STDOUT_LOG_NAME,
    CODEX_RAW_STATUS_NAME,
    transcript_dir,
)
from factory.workgraph.models import AttemptContext
from tests.stub_codex import install_as, write_control
from tests.stub_agent import write_control as write_agent_control
from tests.stub_codex import rollout_path

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


def _bwrap_present() -> bool:
    import shutil

    return shutil.which("bwrap") is not None


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
        exit_code=1,
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


async def test_host_backend_separates_codex_stdout_from_stderr(
    codex_bin: None,
    adapter: object,
    attempt: Callable[..., AttemptContext],
    factory_root: Path,
    node_home: Path,
) -> None:
    """The host launch keeps JSONL and diagnostics in their declared sinks."""
    write_control(
        node_home,
        exit_code=1,
        write_rollout=False,
        stdout='{"type":"thread.started","thread_id":"thread-current"}\n',
        stderr="ordinary diagnostic\n",
        interleave_stderr=True,
    )

    result = await adapter.run_attempt(attempt(), factory_root=factory_root)
    archive = transcript_dir(factory_root, EPIC, NODE, ATTEMPT)

    assert result.termination == Termination.PRE_AGENT_FAILURE
    assert b"thread-current" in (archive / CODEX_EVENTS_NAME).read_bytes()
    assert (archive / CODEX_STDERR_NAME).read_bytes() == b"ordinary diagnostic\n"
    assert b"ordinary diagnostic" not in (archive / CODEX_EVENTS_NAME).read_bytes()


async def test_claude_retains_combined_logging(
    claude_adapter: object,
    attempt: Callable[..., AttemptContext],
    factory_root: Path,
    node_home: Path,
) -> None:
    """The control CLI's combined-log contract does not move with Codex."""
    write_agent_control(node_home, stdout="model says done\n", stderr="claude diagnostic\n")

    result = await claude_adapter.run_attempt(attempt(), factory_root=factory_root)
    combined = (
        transcript_dir(factory_root, EPIC, NODE, ATTEMPT) / STDOUT_LOG_NAME
    ).read_bytes()

    assert result.termination == Termination.COMPLETED
    assert b"model says done" in combined
    assert b"claude diagnostic" in combined


async def test_raw_codex_files_are_private_current_attempt_files(
    codex_bin: None,
    adapter: object,
    attempt: Callable[..., AttemptContext],
    factory_root: Path,
    node_home: Path,
) -> None:
    """Both raw files stay private and host-local, never in the worktree."""
    stream = [{"type": "thread.started", "thread_id": "thread-current"}]
    write_control(
        node_home,
        exit_code=1,
        write_rollout=False,
        stdout="".join(f"{json.dumps(event)}\n" for event in stream),
        stderr="ordinary diagnostic\n",
    )

    result = await adapter.run_attempt(attempt(), factory_root=factory_root)
    archive = transcript_dir(factory_root, EPIC, NODE, ATTEMPT).resolve()

    assert result.termination == Termination.PRE_AGENT_FAILURE
    for name in (CODEX_EVENTS_NAME, CODEX_STDERR_NAME):
        path = archive / name
        assert (path.stat().st_mode & 0o777) == 0o600
        assert path.is_relative_to(archive)
        assert not path.is_relative_to(Path(attempt().worktree_path).resolve())
    status = archive / CODEX_RAW_STATUS_NAME
    assert status.is_file()
    assert (status.stat().st_mode & 0o777) == 0o600


async def test_raw_files_declare_and_record_size_and_retention(
    codex_bin: None,
    adapter: object,
    attempt: Callable[..., AttemptContext],
    factory_root: Path,
    node_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Declared limits are the limits; crossing one is explicit incompleteness."""
    from factory.workgraph import adapter as adapter_module

    monkeypatch.setattr(adapter_module, "CODEX_RAW_MAX_BYTES", 32)
    stream = [{"type": "thread.started", "thread_id": "thread-current"}]
    write_control(
        node_home,
        exit_code=1,
        write_rollout=False,
        stdout="".join(f"{json.dumps(event)}\n" for event in stream),
        stderr="d" * 64,
    )

    result = await adapter.run_attempt(attempt(), factory_root=factory_root)
    archive = transcript_dir(factory_root, EPIC, NODE, ATTEMPT)
    status = json.loads((archive / CODEX_RAW_STATUS_NAME).read_text())

    assert result.termination == Termination.PRE_AGENT_FAILURE
    assert adapter_module.CODEX_RAW_MAX_BYTES == 32
    assert adapter_module.CODEX_RAW_RETENTION_FILES == 1
    assert len((archive / CODEX_EVENTS_NAME).read_bytes()) <= 32
    assert len((archive / CODEX_STDERR_NAME).read_bytes()) <= 32
    assert status["codex-events.jsonl"]["truncated"] is True
    assert status["codex-events.jsonl"]["completeness"] == "incomplete"
    assert status["codex-stderr.log"]["truncated"] is True
    assert status["codex-stderr.log"]["completeness"] == "incomplete"


async def test_raw_files_honor_the_declared_retention_count(
    adapter: object,
    attempt: Callable[..., AttemptContext],
    factory_root: Path,
) -> None:
    """Retention keeps one raw history file per sink, never silently all of it."""
    from factory.workgraph.adapter import SharedAttemptPolicy

    archive = transcript_dir(factory_root, EPIC, NODE, ATTEMPT)
    archive.mkdir(parents=True)
    for index in range(3):
        (archive / f"codex-events-{index}.jsonl").write_text(str(index))
        (archive / f"codex-stderr-{index}.log").write_text(str(index))

    SharedAttemptPolicy(adapter)._rotate_raw_files(archive, attempt())

    assert len(list(archive.glob("codex-events-*.jsonl"))) == 1
    assert len(list(archive.glob("codex-stderr-*.log"))) == 1


async def test_raw_codex_files_stay_out_of_git_workflows_and_public_artifacts(
    codex_bin: None,
    adapter: object,
    attempt: Callable[..., AttemptContext],
    factory_root: Path,
    node_home: Path,
    worktree: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raw provenance does not become a payload or a public artifact."""
    from dataclasses import asdict
    from subprocess import run as run_process

    write_control(node_home, write_rollout=False)
    result = await adapter.run_attempt(attempt(), factory_root=factory_root)
    archive = transcript_dir(factory_root, EPIC, NODE, ATTEMPT)
    paths = [
        archive / name
        for name in (CODEX_EVENTS_NAME, CODEX_STDERR_NAME, CODEX_RAW_STATUS_NAME)
    ]

    repo = tmp_path / "repo"
    repo.mkdir()
    run_process(["git", "init", "-q"], cwd=repo, check=True)
    (repo / ".gitignore").write_text(".factory/\nworktrees/\n")
    for path in paths:
        ignored = run_process(
            ["git", "check-ignore", "--quiet", path.relative_to(tmp_path)],
            cwd=repo,
        ).returncode
        assert ignored == 0
    payload = json.dumps(asdict(result))
    for path in paths:
        assert str(path) not in payload and str(path.resolve()) not in payload
    public_paths = tuple(
        artifact.path for artifact in parse_factory_config(
            (Path.cwd() / "factory.yaml").read_text()
        ).artifacts
    )
    assert not any(path.name in public_paths for path in paths)


def attempt_env_public_artifacts() -> tuple[str, ...]:
    return tuple(path.path for path in parse_factory_config((Path.cwd() / "factory.yaml").read_text()).artifacts)


@pytest.mark.skipif(not _bwrap_present(), reason="bwrap not installed on this host")
async def test_bwrap_backend_separates_codex_stdout_from_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    worktree: Path,
    node_home: Path,
) -> None:
    """The sandbox launch honors the same selected two-sink policy."""
    from factory.workgraph.adapter import AgentInvocation, BwrapBackend, InvocationOutputPolicy
    from tests.test_toolchain_discovery import PlantedHost

    host = PlantedHost(tmp_path / "host")
    for name in ("uv", "node", "git", "claude"):
        host.plant(name)
    bin_dir = tmp_path / "bin"
    install_as(bin_dir, "codex")
    host.activate(monkeypatch, host.bin_dir, bin_dir)
    events_path = transcript_dir(tmp_path, EPIC, NODE, ATTEMPT) / CODEX_EVENTS_NAME
    stderr_path = events_path.parent / CODEX_STDERR_NAME
    events_path.parent.mkdir(parents=True, exist_ok=True)
    write_control(
        node_home,
        write_rollout=False,
        stdout='{"type":"thread.started","thread_id":"thread-current"}\n',
        stderr="ordinary diagnostic\n",
        interleave_stderr=True,
    )

    with events_path.open("wb") as events, stderr_path.open("wb") as stderr:
        invocation = AgentInvocation(
            argv=[str(bin_dir / "codex"), "exec", "-"],
            prompt=PROMPT,
            worktree=worktree,
            env={
                "PATH": str(host.bin_dir),
                "HOME": str(node_home),
            },
            log=events,
            stderr_log=stderr,
            output_policy=InvocationOutputPolicy.SEPARATE,
            standards_path=None,
            model_alias=MODEL_ALIAS,
        )
        process = await BwrapBackend(executable=str(bin_dir / "codex")).launch(invocation)
        process.stdin.close()
        await asyncio.wait_for(process.wait(), 20)

    assert b"thread-current" in events_path.read_bytes()
    assert stderr_path.read_bytes() == b"ordinary diagnostic\n"
    SharedAttemptPolicy,
