"""US2: a Codex attempt archives only its own current execution."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

from factory.usage.models import Termination
from factory.workgraph.adapter import (
    HostAgentBackend,
    home_path,
    transcript_dir,
)
from factory.workgraph.models import AttemptContext
from tests.stub_codex import install_as, write_control

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
