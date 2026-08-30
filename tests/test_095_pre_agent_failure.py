"""US1 — a pre-agent failure says what it was.

An expired subscription OAuth session produced four attempts in thirteen
seconds, each with a 73-byte stdout and no agent process behind it, and every
one of them reached the operator as a diffless `agent_error` beside a typecheck
that failed with exit 127 on a binary nobody had installed. Nothing on that
screen said "credential".

These tests pin the distinction end to end: the adapter classifies the shape
(T001, T003, T005), the activity enriches it with the process's own dying words,
the note carries the reason, the remedy and the fact that the gates ran against
a worktree no agent prepared (T004), and the CLI prints it (T002).

Two of them are about what the detection must *not* be. T003 is the control — an
agent that started and then failed is exactly what it was yesterday — and T005
drives a message the code has never seen, because keying on the measured string
would key on one adapter and one release of it (plan trap 1).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from temporalio.testing import WorkflowEnvironment

from factory.activities.agent_activities import _attach_pre_agent_detail
from factory.cli.nouns.build import render_status
from factory.usage.models import Termination
from factory.verify.models import GateResult, GateStatus
from factory.workgraph.adapter import (
    ClaudeCodeAdapter,
    HostAgentBackend,
    STDOUT_LOG_NAME,
)
from factory.workgraph.models import AttemptContext, NodeState, pre_agent_note
from tests.stub_agent import STUB_AGENT_PATH, install_as, write_control

# The interpreter suite's Temporal wiring, rather than a second copy of it.
from tests.test_interpreter import (
    Attempt,
    ScriptedWorld,
    env,  # noqa: F401  — pytest fixture, re-exported for this module
    make_graph,
    make_node,
    run_epic,
)

EPIC = "095-the-ladder-charges-only-the-story"
NODE = "us1"
ATTEMPT = 1
SESSION_ID = "0f3c9a71-2b4d-4e18-9a06-5c7d8e2f1b03"

#: The measured stdout of the failure this story is about (2026-08-28): 73 bytes,
#: one line, no agent behind it. It appears here as a *fixture*, never as a
#: matcher — the code under test may not contain this string.
OAUTH_REFUSAL = "Failed to authenticate: OAuth session expired and could not be refreshed"

#: A refusal from some future release of some other agent. Nothing in the tree
#: has seen it, which is the point of T005.
UNSEEN_REFUSAL = "fatal: identity broker returned 0x8007 (no mapping for the requested principal)"


# --- fixtures -----------------------------------------------------------------


@pytest.fixture(autouse=True)
def _stub_on_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bin_dir = tmp_path / "bin"
    install_as(bin_dir, "claude")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return bin_dir


@pytest.fixture
def factory_root(tmp_path: Path) -> Path:
    return tmp_path / ".factory"


@pytest.fixture
def worktree(factory_root: Path) -> Path:
    path = factory_root / "worktrees" / EPIC / NODE
    path.mkdir(parents=True)
    return path


@pytest.fixture
def stub_home(factory_root: Path) -> Path:
    path = factory_root / "homes" / EPIC / NODE
    path.mkdir(parents=True)
    return path


@pytest.fixture
def adapter(stub_home: Path) -> ClaudeCodeAdapter:
    return ClaudeCodeAdapter(
        executable=str(STUB_AGENT_PATH),
        grace_s=0.4,
        backend=HostAgentBackend(executable=str(STUB_AGENT_PATH)),
    )


def _context(*, factory_root: Path, worktree: Path) -> AttemptContext:
    return AttemptContext(
        epic_id=EPIC,
        node_id=NODE,
        attempt=ATTEMPT,
        prompt="US1 pre-agent failure test prompt",
        worktree_path=str(worktree),
        home_path=str(factory_root / "homes" / EPIC / NODE),
        proxy_url="http://litellm.test:4000",
        virtual_key="sk-virtual-095-us1-1",
        model_alias="anthropic/claude-opus-5",
        session_id=SESSION_ID,
        timeout_s=3600,
        agent="claude-code",
    )


def _archive(factory_root: Path) -> Path:
    return factory_root / "transcripts" / EPIC / NODE / f"attempt-{ATTEMPT}"


# --- T001 [US1-S1] the terminal reason names authentication -------------------


async def test_a_session_that_never_authenticated_is_not_a_generic_agent_error(
    adapter: ClaudeCodeAdapter,
    factory_root: Path,
    worktree: Path,
    stub_home: Path,
) -> None:
    """An agent process that never produced a token is its own termination, and
    the reason recorded for it names authentication rather than a generic error.

    `write_transcript=False` is the whole fixture: the agent CLI writes its
    session file on its first turn, so the absence of one is the structural fact
    that no turn ever ran.
    """
    write_control(
        stub_home, exit_code=1, write_transcript=False, stdout=OAUTH_REFUSAL
    )
    context = _context(factory_root=factory_root, worktree=worktree)

    result = await adapter.run_attempt(context, factory_root=factory_root)

    assert result.termination == Termination.PRE_AGENT_FAILURE, (
        "an attempt with no agent turn behind it is not an ordinary agent error"
    )
    assert result.termination != Termination.AGENT_ERROR

    # The activity is where the process's own words are read (D-018/FR-012 keeps
    # them out of the adapter), and they are enrichment only — never the
    # classification, which has already happened above.
    described = _attach_pre_agent_detail(result)
    assert OAUTH_REFUSAL in described.detail

    reason = pre_agent_note(described.detail)
    assert "authenticat" in reason.lower(), (
        "the recorded reason must name authentication, not a generic agent error"
    )
    assert OAUTH_REFUSAL in reason


# --- T002 [US1-S2] the reason and the remedy are on screen --------------------


def test_the_cli_shows_the_reason_and_the_remedy() -> None:
    """`ergane build status` prints both, so nobody opens a transcript to learn
    that a credential expired."""
    note = pre_agent_note(OAUTH_REFUSAL)
    document: dict[str, Any] = {
        "epic_state": "RUNNING",
        "nodes": {
            "us1": {
                "state": "VERIFYING",
                "attempt": 1,
                "branch": f"factory/{EPIC}/us1",
                "attempt_note": note,
            }
        },
    }

    screen = render_status(EPIC, document, "RUNNING")

    assert "authenticat" in screen.lower(), "the reason is not on screen"
    assert "remedy" in screen.lower(), "the remedy is not on screen"
    assert OAUTH_REFUSAL in screen, "the process's own words are not on screen"
    # Nothing on screen asks the operator to go and read something else.
    assert ".jsonl" not in screen
    assert STDOUT_LOG_NAME not in screen


# --- T003 [US1-S3] the control: an agent that started is unchanged ------------


async def test_an_agent_that_started_and_then_failed_is_unchanged(
    adapter: ClaudeCodeAdapter,
    factory_root: Path,
    worktree: Path,
    stub_home: Path,
) -> None:
    """The new termination is for the pre-agent case only.

    Same non-zero exit, same refusal on stdout — but the agent took a turn and
    wrote its session file, so this is the `AGENT_ERROR` it has always been and
    the ladder is charged for it exactly as it is today.
    """
    write_control(stub_home, exit_code=1, write_transcript=True, stdout=OAUTH_REFUSAL)
    context = _context(factory_root=factory_root, worktree=worktree)

    result = await adapter.run_attempt(context, factory_root=factory_root)

    assert result.termination == Termination.AGENT_ERROR
    # And nothing enriches it: the pre-agent note belongs to the pre-agent class.
    assert _attach_pre_agent_detail(result).detail == ""


# --- T004 [US1-S4, trap 3] the gates ran against an unprepared worktree -------


async def test_the_record_says_no_agent_prepared_this_worktree(
    env: WorkflowEnvironment,
) -> None:
    """The gate results are still recorded, and the record says what they ran on.

    After a pre-agent failure the worktree has no dependencies, so a typecheck
    genuinely fails with a missing binary. Suppressing that would make the
    attempt unreadable in the other direction (trap 3); what the record owes is
    the context, so exit 127 reads as a fact about the environment rather than
    as the story's failure.
    """
    missing_binary = GateResult(
        name="typecheck",
        command="uv run mypy .",
        status=GateStatus.FAIL,
        exit_code=127,
        duration_s=0.0,
        output_tail="error: /bin/sh: 1: mypy: not found",
    )
    pre_agent = Attempt(
        gates=[missing_binary],
        termination=Termination.PRE_AGENT_FAILURE,
    )
    script = ScriptedWorld({"us1": [pre_agent] * 8}, client=env.client)

    status = await run_epic(env, script, graph=make_graph([make_node("us1", "US1")]))

    note = status.nodes["us1"].attempt_note
    assert note is not None, "a pre-agent failure left no note on the record"
    assert "no agent" in note.lower() and "worktree" in note.lower(), (
        "the record must say the gates ran against a worktree no agent prepared"
    )

    # Trap 3: the evidence is contextualised, never suppressed.
    recorded = [record for record in script.records if record.node_id == "us1"]
    assert recorded, "a pre-agent failure recorded no verification at all"
    assert all(
        gate.exit_code == 127
        for record in recorded
        for gate in record.gate_results
    ), "the gate results were suppressed rather than explained"
    assert status.nodes["us1"].state == NodeState.KILLED


# --- T005 [FR-001, trap 1] the detection is structural ------------------------


async def test_detection_is_structural_not_a_string_match(
    adapter: ClaudeCodeAdapter,
    factory_root: Path,
    worktree: Path,
    stub_home: Path,
) -> None:
    """A message the code has never seen is classified all the same.

    The durable fact is the shape — no turn, no token, an untouched worktree —
    and a matcher on the measured 73-byte string would key the whole feature to
    one adapter and one release of it (trap 1). Only the *remedy* degrades when
    the message is unrecognised: the class, the note and the context survive.
    """
    write_control(
        stub_home, exit_code=1, write_transcript=False, stdout=UNSEEN_REFUSAL
    )
    context = _context(factory_root=factory_root, worktree=worktree)

    result = await adapter.run_attempt(context, factory_root=factory_root)

    assert result.termination == Termination.PRE_AGENT_FAILURE
    described = _attach_pre_agent_detail(result)
    assert UNSEEN_REFUSAL in described.detail

    note = pre_agent_note(described.detail)
    assert UNSEEN_REFUSAL in note, "the unseen message must still be quoted"
    assert "worktree" in note.lower(), "the context must not depend on the message"
    assert "remedy" in note.lower(), "a remedy is owed even for an unseen cause"
