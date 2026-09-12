"""US2 of 155: a Codex refusal is classified, not read as a silent success.

Spec 070's lesson, one runner over: a CLI that dies on a bad credential and
reads as a diffless success is the failure the factory has already paid for.
US1 landed the adapter and the measured marker (`CODEX_REFUSAL_MARKER` —
stderr + exit 1, the inverse of Claude Code, whose refusal is stdout); this
story wires it into the classification path the activity layer owns, so a
refused run ends NAMED (`auth_failure`), never silent.

These tests drive `run_agent_attempt` — the function production calls — with
`tests/stub_codex.py` standing in for the CLI, and script the typed fatal
shapes 160 measured on 2026-09-10 (top-level `error` plus the matching
`turn.failed`). The stderr-only fixture remains the no-event compatibility
control. Scenarios: US2-S1/FR-005 (a refusal is classified, from typed
evidence); US2-S2 (the measured string replays both ways — named refusal, and
the ordinary-failure control); US2-S3/FR-007 (cleartext reasoning neither
satisfies nor defeats typed detection).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

import pytest
from temporalio.testing import ActivityEnvironment

from factory.activities.agent_activities import run_agent_attempt
from factory.usage.models import Termination
from factory.workgraph.adapter import (
    CODEX_EVENTS_NAME,
    CODEX_REFUSAL_MARKER,
    STDOUT_LOG_NAME,
    home_path,
    transcript_dir,
)
from factory.workgraph.models import AttemptContext
from tests.stub_codex import install_as, write_control

EPIC = "155-codex-runs-as-a-second-runner"
NODE = "us2"

#: Not 1: the attempt number names the archive directory (the same deliberate
#: off-by-one the US1 tests carry).
ATTEMPT = 2

SESSION_ID = "4c2e6f80-9a1b-4c33-8d27-5e9f0a1b2c3d"
PROXY_URL = "http://litellm.test:4000"
VIRTUAL_KEY = "sk-virtual-155-codex-runs-as-a-second-runner-us2-2"
MODEL_ALIAS = "ollama-cloud/glm-5.3-flash"
PROMPT = "You are the implementer persona.\n\n## Scope\n\nImplement US2.\n"

GENEROUS_TIMEOUT_S = 60


# --- setup -------------------------------------------------------------------


@pytest.fixture(autouse=True)
def codex_bin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """`tests/stub_codex.py` where `codex` would be found (R6). Autouse: the
    worker host must never launch a real CLI against a real proxy, whatever a
    test means to script."""
    bin_dir = tmp_path / "bin"
    install_as(bin_dir, "codex")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return bin_dir


@pytest.fixture
def factory_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The worker host's state directory, exported the way production reads it."""
    root = tmp_path / ".ergane"
    monkeypatch.setenv("ERGANE_ROOT", str(root))
    return root


@pytest.fixture(autouse=True)
def worker_host(
    tmp_path: Path, factory_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A worker host: a scratch HOME and planted credentials the allowlist keeps
    from every launch — planted here so no test in this file can quietly launch
    a real CLI against a real proxy."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-master-must-never-reach-an-agent")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1234567:telegram-bot-token-must-never-reach-an-agent")
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("TERM", "dumb")


@pytest.fixture
def worktree(tmp_path: Path) -> Path:
    """Where the agent runs. A directory, not a repository — the adapter's
    contract is "cwd is the path you were handed"."""
    path = tmp_path / "worktrees" / EPIC / NODE
    path.mkdir(parents=True)
    return path


@pytest.fixture
def context(
    worktree: Path, factory_root: Path, target_repo: Callable[..., Path]
) -> Callable[..., AttemptContext]:
    """A Codex gateway attempt's context; `context(attempt=3)` overrides one."""

    def build(**overrides: Any) -> AttemptContext:
        fields: dict[str, Any] = {
            "epic_id": EPIC,
            "node_id": NODE,
            "attempt": ATTEMPT,
            "prompt": PROMPT,
            "worktree_path": str(worktree),
            "home_path": str(home_path(factory_root, EPIC, NODE)),
            "proxy_url": PROXY_URL,
            "virtual_key": VIRTUAL_KEY,
            "model_alias": MODEL_ALIAS,
            "session_id": SESSION_ID,
            "timeout_s": GENEROUS_TIMEOUT_S,
            "target_repo": str(target_repo("passing")),
            "agent": "codex",
            "route": "gateway",
        }
        return AttemptContext(**(fields | overrides))

    return build


@pytest.fixture
def node_home(factory_root: Path) -> Path:
    """The per-node home — where the stub reads its control file."""
    return home_path(factory_root, EPIC, NODE)


def archive_dir(factory_root: Path) -> Path:
    return transcript_dir(factory_root, EPIC, NODE, ATTEMPT)


def stdout_log(factory_root: Path) -> str:
    return (archive_dir(factory_root) / STDOUT_LOG_NAME).read_text(encoding="utf-8")


def _fatal_stream(fatal_message: str) -> str:
    events = [
        {"type": "thread.started", "thread_id": "thread-typed"},
        {"type": "turn.started"},
        {"type": "error", "message": fatal_message},
        {"type": "turn.failed", "error": {"message": fatal_message}},
    ]
    return "".join(f"{json.dumps(event)}\n" for event in events)


# --- US2-S1: the refusal is classified, from the measured text (FR-005) --------


async def test_a_codex_auth_refusal_is_named_not_silent(
    context: Callable[..., AttemptContext],
    node_home: Path,
    factory_root: Path,
) -> None:
    """US2-S1/FR-005: Codex's typed 401 pair ends `auth_failure`, never silent."""
    write_control(
        node_home,
        exit_code=1,
        write_rollout=False,
        stdout=_fatal_stream(CODEX_REFUSAL_MARKER),
    )

    result = await ActivityEnvironment().run(run_agent_attempt, context())

    assert result.termination == Termination.AUTH_FAILURE
    # The evidence beside the classification is the measured stream: the fatal
    # line reached the separate diagnostic spool the scanner reads.
    assert CODEX_REFUSAL_MARKER in (
        archive_dir(factory_root) / CODEX_EVENTS_NAME
    ).read_text(encoding="utf-8")


# --- US2-S2: the measured string replays both ways ------------------------------


async def test_the_measured_string_replays_as_a_named_refusal(
    context: Callable[..., AttemptContext],
    node_home: Path,
    factory_root: Path,
) -> None:
    """US2-S2, the refusal way: the exact measured substring, replayed through
    the production classifier, is a refusal — the control half asserting the
    thing 070's probe taught (a refused run must not read as silent success)."""
    write_control(
        node_home,
        exit_code=1,
        write_rollout=False,
        stdout=_fatal_stream(f"ERROR: {CODEX_REFUSAL_MARKER}: no bearer"),
    )

    result = await ActivityEnvironment().run(run_agent_attempt, context())

    assert result.termination == Termination.AUTH_FAILURE


async def test_a_codex_failure_without_the_marker_stays_an_ordinary_agent_error(
    context: Callable[..., AttemptContext],
    node_home: Path,
    factory_root: Path,
) -> None:
    """US2-S2, the other way: the same run shape — exit 1, no model activity —
    with the marker absent is a pre-agent failure, not a refusal. The
    classification is marker-driven, so a story's own failure keeps its class."""
    write_control(
        node_home,
        exit_code=1,
        write_rollout=False,
        stdout=_fatal_stream("the gate failed: 3 assertions"),
    )

    result = await ActivityEnvironment().run(run_agent_attempt, context())

    assert result.termination == Termination.PRE_AGENT_FAILURE
    assert "the gate failed" in (
        archive_dir(factory_root) / CODEX_EVENTS_NAME
    ).read_text(encoding="utf-8")


# --- US2-S3: cleartext reasoning neither satisfies nor defeats (FR-007) ---------


async def test_reasoning_text_alone_satisfies_no_refusal(
    context: Callable[..., AttemptContext],
    node_home: Path,
    factory_root: Path,
) -> None:
    """US2-S3, the satisfies half: a successful run whose cleartext chain-of-
    thought mentions the refusal text stays COMPLETED — reasoning text is never
    a refusal, whatever it quotes (trap 1)."""
    reasoning = (
        "reasoning: the upstream returned "
        f'"{CODEX_REFUSAL_MARKER}" in an earlier turn; retrying worked.'
    )
    stdout = "".join(
        f"{json.dumps(event)}\n"
        for event in [
            {"type": "thread.started", "thread_id": "thread-reasoning"},
            {"type": "turn.started"},
            {
                "type": "item.completed",
                "item": {"id": "thought", "type": "reasoning", "text": reasoning},
            },
            {
                "type": "item.completed",
                "item": {"id": "final", "type": "agent_message", "text": "Final: ok"},
            },
            {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 2}},
        ]
    )
    write_control(node_home, stdout=stdout)

    result = await ActivityEnvironment().run(run_agent_attempt, context())

    assert result.termination == Termination.COMPLETED


async def test_reasoning_text_defeats_no_refusal(
    context: Callable[..., AttemptContext],
    node_home: Path,
    factory_root: Path,
) -> None:
    """US2-S3, the defeats half: quoted reasoning beside a typed fatal pair
    still ends `auth_failure` — reasoning text is not the fatal source."""
    reasoning = "reasoning: I should check whether the key expired before blaming the proxy."
    stream = [
        {"type": "thread.started", "thread_id": "thread-typed"},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {"id": "thought", "type": "reasoning", "text": reasoning},
        },
        {"type": "error", "message": CODEX_REFUSAL_MARKER},
        {"type": "turn.failed", "error": {"message": CODEX_REFUSAL_MARKER}},
    ]
    write_control(
        node_home,
        exit_code=1,
        write_rollout=False,
        stdout="".join(f"{json.dumps(event)}\n" for event in stream),
    )

    result = await ActivityEnvironment().run(run_agent_attempt, context())

    assert result.termination == Termination.AUTH_FAILURE
