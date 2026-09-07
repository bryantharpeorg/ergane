"""US2 of epic 011-agent-sandbox: the agent launch sits behind a seam.

The backend is resolved from the manifest's `runtime:` key. Two implementations
exist when this story lands: the host launch (today's direct spawn, kept but
selectable only explicitly) and the fake the tests drive. The bwrap
implementation arrives in US3; this story only wires the socket and proves the
refusal path.

Every test here is about the seam, not about a real sandbox: the suite must stay
green on a host with no bwrap installed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from factory.verify.factory_yaml import FactoryConfigError, parse_factory_config
from factory.workgraph.adapter import (
    DEFAULT_EXECUTABLE,
    ClaudeCodeAdapter,
    HostAgentBackend,
)
from factory.workgraph.models import AttemptContext
from tests.stub_agent import STUB_AGENT_PATH, install_as, last_invocation

EPIC = "011-agent-sandbox"
NODE = "us2"
ATTEMPT = 1
SESSION_ID = "6b1f5d4e-3a2c-4f80-9c1a-7e6d5b4a3c21"
MODEL_ALIAS = "anthropic/CHANGEME"
PROXY_URL = "http://litellm.test:4000"
VIRTUAL_KEY = "sk-virtual-011-agent-sandbox-us2-1"
PROMPT = "You are the implementer persona.\n\n## Scope\n\nImplement US2.\n"
TIMEOUT_S = 60


def _context(
    *,
    worktree_path: str,
    target_repo: str,
    prompt: str = PROMPT,
    model_alias: str = MODEL_ALIAS,
    standards: str = ".specify/memory/constitution.md",
) -> AttemptContext:
    return AttemptContext(
        epic_id=EPIC,
        node_id=NODE,
        attempt=ATTEMPT,
        prompt=prompt,
        worktree_path=worktree_path,
        home_path=str(Path(worktree_path).parent / "home"),
        proxy_url=PROXY_URL,
        virtual_key=VIRTUAL_KEY,
        model_alias=model_alias,
        session_id=SESSION_ID,
        timeout_s=TIMEOUT_S,
        target_repo=target_repo,
    )


def _build_target_repo(tmp_path: Path, runtime: str, standards: str | None = None) -> Path:
    repo = tmp_path / "target-repo"
    repo.mkdir(parents=True)
    lines = [
        "version: 1",
        f"runtime: {runtime}",
        "gates:",
        '  test: "uv run pytest -q"',
    ]
    if standards is not None:
        lines.append(f"standards: {standards}")
    (repo / "ergane.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return repo


# --- the fake backend used by the parity test ---------------------------------


@dataclass
class FakeAgentBackend:
    """Records the invocation and delegates to the host so the adapter can finish."""

    name: str = "fake"
    executable: str = str(STUB_AGENT_PATH)
    invocations: list[Any] = field(default_factory=list)

    async def launch(self, invocation: Any) -> Any:
        self.invocations.append(invocation)
        return await HostAgentBackend(executable=self.executable).launch(invocation)


# --- T010 [US2] parity case: fake receives exactly what the direct launch builds


@pytest.mark.asyncio
async def test_fake_backend_receives_parity_invocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fake backend substituted through the seam sees the same argv, prompt,
    standards path and persona routing that today's direct host launch builds.
    """
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    standards = "docs/STANDARDS.md"
    repo = _build_target_repo(tmp_path, runtime="bwrap", standards=standards)

    # Put the stub where the host launch can find it.
    bin_dir = tmp_path / "bin"
    install_as(bin_dir, "claude")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    context = _context(worktree_path=str(worktree), target_repo=str(repo))

    # What today's direct launch builds. 154-US4: the per-CLI surface is
    # private (`_argv`), so the expectation is read from the same seam the
    # shared policy calls — the parity claim is unchanged.
    direct = ClaudeCodeAdapter(executable=str(STUB_AGENT_PATH))
    expected_argv = direct._argv(context)

    fake = FakeAgentBackend()
    adapter = ClaudeCodeAdapter(executable=str(STUB_AGENT_PATH), backend=fake)

    result = await adapter.run_attempt(context, factory_root=tmp_path / ".factory")

    assert result.termination == "completed"
    assert len(fake.invocations) == 1
    invocation = fake.invocations[0]

    assert invocation.argv == expected_argv
    assert invocation.prompt == PROMPT
    assert invocation.standards_path == standards
    assert invocation.model_alias == MODEL_ALIAS
    # The fake actually launched the stub; the stub records the same argv.
    assert last_invocation(worktree).argv == expected_argv


# --- T011 [P] [US2] refusal case: absent backend is a named refusal


@pytest.mark.asyncio
async def test_absent_bwrap_backend_refuses_before_spawn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A manifest naming bwrap on a host without it refuses before any agent process
    runs, naming the backend and the platform."""
    from factory.workgraph import adapter as adapter_module

    worktree = tmp_path / "worktree"
    worktree.mkdir()
    repo = _build_target_repo(tmp_path, runtime="bwrap")
    context = _context(worktree_path=str(worktree), target_repo=str(repo))

    # Simulate a host with no bwrap binary.
    missing_binary = tmp_path / "missing" / "bwrap"
    monkeypatch.setattr(
        adapter_module,
        "BWRAP_BACKEND_BINARY",
        missing_binary,
    )

    adapter = ClaudeCodeAdapter(executable=str(STUB_AGENT_PATH))

    with pytest.raises(Exception) as excinfo:
        await adapter.run_attempt(context, factory_root=tmp_path / ".factory")

    message = str(excinfo.value)
    assert "bwrap" in message
    assert str(missing_binary) in message
    assert "missing" in message.lower() or "not available" in message.lower()

    # No agent process ran: the worktree has no stub record.
    assert not list(worktree.glob(".stub-agent/*"))


# --- T012 [P] [US2] manifest case: old container-image runtime is refused


def test_old_container_image_runtime_is_refused_naming_bwrap() -> None:
    """A `runtime:` value in the old container-image form is a validation refusal
    that names `bwrap` as the supported backend."""
    text = """
version: 1
runtime: ghcr.io/astral-sh/uv:python3.11-bookworm
gates:
  test: "uv run pytest -q"
"""

    with pytest.raises(FactoryConfigError) as excinfo:
        parse_factory_config(text)

    assert excinfo.value.rule == "runtime"
    message = str(excinfo.value)
    assert "bwrap" in message
