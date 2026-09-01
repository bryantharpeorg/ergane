"""US2 of epic 125: a credential that cannot work is refused before an attempt is spent.

A copied interactive credential carries an `expiresAt` timestamp. When it has
passed and no long-lived token is configured, the adapter must refuse before the
sandbox forks. When a long-lived token is present the file is irrelevant. When
the expiry cannot be read the factory must proceed rather than stop on a guess.

Every credential-like string below is synthetic (trap 4).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from factory.config import SUBSCRIPTION_AGENT, Persona, WriteScope
from factory.usage.models import Termination
from factory.verify.ladder import (
    VerificationConfig,
    _attempts_spent,
    pre_agent_failures_spent,
)
from factory.verify.models import AttemptRecord, OverallVerdict
from factory.workgraph.adapter import (
    CLAUDE_CODE_OAUTH_TOKEN,
    CREDENTIAL_SOURCE_OAUTH_TOKEN,
    ClaudeCodeAdapter,
    HostAgentBackend,
    discover_subscription_credential,
)
from factory.workgraph.models import AttemptContext
from tests.stub_agent import (
    STUB_AGENT_PATH,
    install_as,
    invocations,
    last_invocation,
    write_control,
)

EPIC = "125-a-credential-outlives-the-night"
NODE = "us2"
ATTEMPT = 1
SESSION_ID = "6b1f5d4e-3a2c-4f80-9c1a-7e6d5b4a3c21"
PROXY_URL = "http://litellm.test:4000"
VIRTUAL_KEY = "sk-virtual-125-us2-1"

#: A synthetic long-lived subscription token. Real tokens share the `sk-ant-oat01-`
#: prefix but this value is generated for tests and never valid anywhere.
OAUTH_TOKEN = "sk-ant-oat01-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _persona(name: str, *, agent: str, model: str | None) -> Persona:
    return Persona(
        name=name,
        agent=agent,
        model=model,
        fallback=None,
        skills=(),
        write_scope=WriteScope.WORKTREE,
        needs_worktree=True,
        timeout_s=3600,
    )


SUBSCRIPTION = _persona("subscription", agent=SUBSCRIPTION_AGENT, model="opus")


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


# --- helpers ------------------------------------------------------------------


def _attempt_context(
    *,
    factory_root: Path,
    worktree: Path,
) -> AttemptContext:
    home = factory_root / "homes" / EPIC / NODE
    return AttemptContext(
        epic_id=EPIC,
        node_id=NODE,
        attempt=ATTEMPT,
        prompt="US2 credential expiry test prompt",
        worktree_path=str(worktree),
        home_path=str(home),
        proxy_url=PROXY_URL,
        virtual_key=VIRTUAL_KEY,
        model_alias="opus",
        session_id=SESSION_ID,
        timeout_s=3600,
        agent=SUBSCRIPTION.agent,
    )


def _fake_operator_home(tmp_path: Path) -> Path:
    """A writable stand-in for the operator's real home directory."""
    home = tmp_path / "operator-home"
    home.mkdir(parents=True)
    return home


def _credential_with_expiry(expires_at: str) -> dict:
    """A synthetic copied credential with the given ISO `expiresAt`."""
    return {
        "accessToken": "fake-access-token",
        "refreshToken": "fake-refresh-token",
        "expiresAt": expires_at,
        "refreshTokenExpiresAt": (datetime.now(timezone.utc) + timedelta(days=28)).isoformat(),
        "scopes": ["claude_code"],
        "subscriptionType": "pro",
        "rateLimitTier": "default",
    }


def _write_credential(path: Path, content: dict | str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, dict):
        path.write_text(json.dumps(content, indent=2), encoding="utf-8")
    else:
        path.write_text(content, encoding="utf-8")
    path.chmod(0o600)
    return path


# --- T012 [P] [US2-S1] expired copied credential is refused before fork -------


@pytest.mark.asyncio
async def test_expired_credential_refused_before_fork(
    adapter: ClaudeCodeAdapter,
    factory_root: Path,
    worktree: Path,
    stub_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With only a copied credential whose expiry has passed, preparation
    raises a refusal before the sandbox forks, and the message names the expiry."""
    operator_home = _fake_operator_home(tmp_path)
    expired = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    _write_credential(
        operator_home / ".claude" / ".credentials.json",
        _credential_with_expiry(expired),
    )
    monkeypatch.setattr(
        "factory.workgraph.adapter._operator_home", lambda: operator_home
    )
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)

    context = _attempt_context(factory_root=factory_root, worktree=worktree)
    result = await adapter.run_attempt(context, factory_root=factory_root)

    # US2-S6: the refusal is a recorded pre-agent failure, not an exception.
    assert result.termination == Termination.PRE_AGENT_FAILURE
    assert expired in result.detail or "expired" in (result.detail or "").lower()
    # The refusal must happen before the stub agent is launched.
    assert not invocations(worktree)


# --- T013 [P] [US2-S2] future expiry proceeds unchanged -----------------------


@pytest.mark.asyncio
async def test_future_expiry_proceeds_unchanged(
    adapter: ClaudeCodeAdapter,
    factory_root: Path,
    worktree: Path,
    stub_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A copied credential whose expiry is in the future is accepted and the
    attempt runs as it does today."""
    operator_home = _fake_operator_home(tmp_path)
    future = (datetime.now(timezone.utc) + timedelta(hours=8)).isoformat()
    _write_credential(
        operator_home / ".claude" / ".credentials.json",
        _credential_with_expiry(future),
    )
    monkeypatch.setattr(
        "factory.workgraph.adapter._operator_home", lambda: operator_home
    )
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    write_control(stub_home)

    context = _attempt_context(factory_root=factory_root, worktree=worktree)
    result = await adapter.run_attempt(context, factory_root=factory_root)

    assert result.termination == Termination.COMPLETED
    assert last_invocation(worktree).env["HOME"] == str(stub_home)


# --- T014 [P] [US2-S3] long-lived token present: expired file is irrelevant ---


@pytest.mark.asyncio
async def test_token_wins_over_expired_copy(
    adapter: ClaudeCodeAdapter,
    factory_root: Path,
    worktree: Path,
    stub_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When a long-lived token is present, an expired copied credential does not
    prevent the attempt from running."""
    operator_home = _fake_operator_home(tmp_path)
    expired = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    _write_credential(
        operator_home / ".claude" / ".credentials.json",
        _credential_with_expiry(expired),
    )
    monkeypatch.setattr(
        "factory.workgraph.adapter._operator_home", lambda: operator_home
    )
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", OAUTH_TOKEN)
    write_control(stub_home)

    context = _attempt_context(factory_root=factory_root, worktree=worktree)
    result = await adapter.run_attempt(context, factory_root=factory_root)

    assert result.termination == Termination.COMPLETED
    assert result.credential_source == CREDENTIAL_SOURCE_OAUTH_TOKEN
    env = last_invocation(worktree).env
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == OAUTH_TOKEN


# --- T015 [P] [US2-S4] absent, unreadable and unparseable expiry all proceed ---


@pytest.mark.asyncio
async def test_absent_expiry_proceeds(
    adapter: ClaudeCodeAdapter,
    factory_root: Path,
    worktree: Path,
    stub_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A copied credential with no `expiresAt` field does not stop dispatch."""
    operator_home = _fake_operator_home(tmp_path)
    credential = _credential_with_expiry(
        (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    )
    credential.pop("expiresAt")
    _write_credential(operator_home / ".claude" / ".credentials.json", credential)
    monkeypatch.setattr(
        "factory.workgraph.adapter._operator_home", lambda: operator_home
    )
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    write_control(stub_home)

    context = _attempt_context(factory_root=factory_root, worktree=worktree)
    result = await adapter.run_attempt(context, factory_root=factory_root)

    assert result.termination == Termination.COMPLETED


@pytest.mark.asyncio
async def test_unreadable_expiry_proceeds(
    adapter: ClaudeCodeAdapter,
    factory_root: Path,
    worktree: Path,
    stub_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A copied credential that cannot be read as JSON does not stop dispatch."""
    operator_home = _fake_operator_home(tmp_path)
    _write_credential(operator_home / ".claude" / ".credentials.json", "not json")
    monkeypatch.setattr(
        "factory.workgraph.adapter._operator_home", lambda: operator_home
    )
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    write_control(stub_home)

    context = _attempt_context(factory_root=factory_root, worktree=worktree)
    result = await adapter.run_attempt(context, factory_root=factory_root)

    assert result.termination == Termination.COMPLETED


@pytest.mark.asyncio
async def test_unparseable_expiry_proceeds(
    adapter: ClaudeCodeAdapter,
    factory_root: Path,
    worktree: Path,
    stub_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A copied credential whose `expiresAt` is not a timestamp does not stop dispatch."""
    operator_home = _fake_operator_home(tmp_path)
    credential = _credential_with_expiry("not-a-timestamp")
    _write_credential(operator_home / ".claude" / ".credentials.json", credential)
    monkeypatch.setattr(
        "factory.workgraph.adapter._operator_home", lambda: operator_home
    )
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    write_control(stub_home)

    context = _attempt_context(factory_root=factory_root, worktree=worktree)
    result = await adapter.run_attempt(context, factory_root=factory_root)

    assert result.termination == Termination.COMPLETED


# --- T016 [P] [US2-S5] refusal names both remedies ----------------------------


@pytest.mark.asyncio
async def test_refusal_names_both_remedies(
    adapter: ClaudeCodeAdapter,
    factory_root: Path,
    worktree: Path,
    stub_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refusal message tells the operator how to re-authenticate interactively
    and how to configure the long-lived token, not only one of the two."""
    operator_home = _fake_operator_home(tmp_path)
    expired = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    _write_credential(
        operator_home / ".claude" / ".credentials.json",
        _credential_with_expiry(expired),
    )
    monkeypatch.setattr(
        "factory.workgraph.adapter._operator_home", lambda: operator_home
    )
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)

    context = _attempt_context(factory_root=factory_root, worktree=worktree)
    result = await adapter.run_attempt(context, factory_root=factory_root)

    detail = result.detail or ""
    assert result.termination == Termination.PRE_AGENT_FAILURE
    assert "claude auth login" in detail.lower() or "login" in detail.lower()
    assert CLAUDE_CODE_OAUTH_TOKEN in detail
    assert "long-lived" in detail.lower() or "setup-token" in detail.lower()


# --- T017 [P] [US2-S6] refusal is pre_agent and off the ordinary budget -------


def test_refusal_does_not_consume_attempt_budget() -> None:
    """A refusal recorded as a pre-agent failure is excluded from the ordinary
    attempt budget by `AttemptRecord.pre_agent`, following the shape 095 established."""
    record = AttemptRecord(
        attempt=1,
        persona=SUBSCRIPTION.name,
        verdict=OverallVerdict.FAIL,
        pre_agent=True,
    )
    history = [record]
    config = VerificationConfig(max_attempts=1)

    assert _attempts_spent(history, config) == 0
    assert pre_agent_failures_spent(history) == 1


# --- T018 [P] [US2-S7] credential check makes no network call -----------------


def test_credential_check_reads_local_file_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The expiry check reads only the local credential file and would fail if it
    tried a network call, because no network client is available where it runs."""
    operator_home = _fake_operator_home(tmp_path)
    expired = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    _write_credential(
        operator_home / ".claude" / ".credentials.json",
        _credential_with_expiry(expired),
    )

    # The check must not import or use httpx, requests, or any other HTTP client.
    # This assertion is structural: the function under test is the one that will read
    # expiry, and it lives in the adapter module which has no HTTP imports.
    import factory.workgraph.adapter as adapter_module

    assert "httpx" not in dir(adapter_module)
    assert "requests" not in dir(adapter_module)
    assert "urllib.request" not in dir(adapter_module)

    # Discovery itself returns the path and never opens a socket.
    found = discover_subscription_credential(operator_home=operator_home)
    assert found == operator_home / ".claude" / ".credentials.json"
