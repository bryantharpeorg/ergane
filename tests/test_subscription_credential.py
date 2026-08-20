"""US3: the subscription credential reaches the sandbox, and only where it should.

This story is about the operator's credential, not the gateway's virtual key. The
credential must be discovered (not hardcoded), seeded only into subscription-
routed node homes, refused by name when absent, and classified as an
authentication failure when present-but-refused.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from factory.config import SUBSCRIPTION_AGENT, Persona, WriteScope
from factory.usage.models import Termination
from factory.workgraph.adapter import (
    ATTEMPT_ARCHIVE_ENV,
    ClaudeCodeAdapter,
    HostAgentBackend,
    STDOUT_LOG_NAME,
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

EPIC = "070-subscription-credential"
NODE = "us3"
ATTEMPT = 1
SESSION_ID = "6b1f5d4e-3a2c-4f80-9c1a-7e6d5b4a3c21"
PROXY_URL = "http://litellm.test:4000"
VIRTUAL_KEY = "sk-virtual-070-subscription-credential-us3-1"
CLI_ALIAS = "opus"

#: The exact refusal the Claude Code CLI prints on stdout when the subscription
#: credential is present but not usable (measured 2026-08-19).
SUBSCRIPTION_REFUSAL = "Not logged in · Please run /login"

#: A minimal synthetic credential file. Its shape matches the measured field set
#: but the adapter only copies bytes; it never parses the credential.
FAKE_CREDENTIAL = {
    "accessToken": "fake-access-token",
    "refreshToken": "fake-refresh-token",
    "expiresAt": "2026-08-20T12:00:00.000Z",
    "refreshTokenExpiresAt": "2026-08-21T12:00:00.000Z",
    "scopes": ["claude_code"],
    "subscriptionType": "pro",
    "rateLimitTier": "default",
}


# --- persona fixtures --------------------------------------------------------


def _persona(
    name: str,
    *,
    agent: str,
    model: str | None,
) -> Persona:
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


GATEWAY = _persona("gateway", agent="claude-code", model="anthropic/claude-opus-5")
SUBSCRIPTION = _persona("subscription", agent=SUBSCRIPTION_AGENT, model=CLI_ALIAS)


# --- helpers ------------------------------------------------------------------


def _attempt_context(
    *,
    factory_root: Path,
    worktree: Path,
    persona: Persona,
    model_alias: str = CLI_ALIAS,
) -> AttemptContext:
    home = factory_root / "homes" / EPIC / NODE
    return AttemptContext(
        epic_id=EPIC,
        node_id=NODE,
        attempt=ATTEMPT,
        prompt="US3 credential test prompt",
        worktree_path=str(worktree),
        home_path=str(home),
        proxy_url=PROXY_URL,
        virtual_key=VIRTUAL_KEY,
        model_alias=model_alias,
        session_id=SESSION_ID,
        timeout_s=3600,
        agent=persona.agent,
    )


def _install_stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bin_dir = tmp_path / "bin"
    install_as(bin_dir, "claude")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return bin_dir


def _fake_operator_home(tmp_path: Path) -> Path:
    """A writable stand-in for the operator's real home directory."""
    home = tmp_path / "operator-home"
    home.mkdir(parents=True)
    return home


def _write_credential(path: Path, content: dict | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(content if content is not None else FAKE_CREDENTIAL, indent=2),
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


@pytest.fixture(autouse=True)
def _stub_on_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return _install_stub(tmp_path, monkeypatch)


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


# --- T018 [US3-S1] subscription home carries the credential ------------------


@pytest.mark.asyncio
async def test_subscription_home_carries_credential(
    adapter: ClaudeCodeAdapter,
    factory_root: Path,
    worktree: Path,
    stub_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A subscription-routed node gets the operator's credential seeded into
    its per-node HOME beside the .gitconfig it already receives."""
    operator_home = _fake_operator_home(tmp_path)
    credential_path = _write_credential(operator_home / ".claude" / ".credentials.json")
    monkeypatch.setattr(
        "factory.workgraph.adapter._operator_home", lambda: operator_home
    )
    write_control(stub_home)

    context = _attempt_context(factory_root=factory_root, worktree=worktree, persona=SUBSCRIPTION)
    result = await adapter.run_attempt(context, factory_root=factory_root)

    assert result.termination == Termination.COMPLETED
    seeded = stub_home / ".claude" / ".credentials.json"
    assert seeded.is_file()
    assert json.loads(seeded.read_text(encoding="utf-8")) == FAKE_CREDENTIAL
    # The gitconfig the adapter already wrote must still be present.
    assert (stub_home / ".gitconfig").is_file()
    # The credential came from the discovered file, not from thin air.
    assert last_invocation(worktree).env["HOME"] == str(stub_home)


# --- T019 [US3-S2] gateway home has no credential ---------------------------


@pytest.mark.asyncio
async def test_gateway_home_has_no_subscription_credential(
    adapter: ClaudeCodeAdapter,
    factory_root: Path,
    worktree: Path,
    stub_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A gateway-routed node's HOME keeps the .gitconfig and nothing else;
    the operator's subscription credential is never seeded there."""
    operator_home = _fake_operator_home(tmp_path)
    _write_credential(operator_home / ".claude" / ".credentials.json")
    monkeypatch.setattr(
        "factory.workgraph.adapter._operator_home", lambda: operator_home
    )
    write_control(stub_home)

    context = _attempt_context(factory_root=factory_root, worktree=worktree, persona=GATEWAY)
    result = await adapter.run_attempt(context, factory_root=factory_root)

    assert result.termination == Termination.COMPLETED
    assert (stub_home / ".gitconfig").is_file()
    assert not (stub_home / ".claude" / ".credentials.json").exists()


# --- T020 [US3-S3] missing credential is a named refusal before the fork ----


@pytest.mark.asyncio
async def test_missing_subscription_credential_refused_before_fork(
    adapter: ClaudeCodeAdapter,
    factory_root: Path,
    worktree: Path,
    stub_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no credential on the host, a subscription node is refused by name
    before the sandbox forks, leaving no stub invocation behind."""
    operator_home = _fake_operator_home(tmp_path)
    monkeypatch.setattr(
        "factory.workgraph.adapter._operator_home", lambda: operator_home
    )

    context = _attempt_context(factory_root=factory_root, worktree=worktree, persona=SUBSCRIPTION)
    with pytest.raises(Exception) as excinfo:
        await adapter.run_attempt(context, factory_root=factory_root)

    message = str(excinfo.value)
    assert "subscription credential" in message.lower() or "credential" in message.lower()
    # The refusal must happen before the stub agent is launched.
    assert not invocations(worktree)


# --- T021 [US3-S4] credential location is discovered, not hardcoded -----------


def test_credential_discovery_checks_xdg_and_default_paths(tmp_path: Path) -> None:
    """Moving the credential to the XDG config path still lets discovery find it;
    removing it from every known path returns None."""
    operator_home = _fake_operator_home(tmp_path)

    # No credential anywhere: discovery returns None.
    assert discover_subscription_credential(operator_home=operator_home) is None

    # Credential in XDG_CONFIG_HOME location.
    xdg_config = tmp_path / "xdg-config"
    xdg_credential = _write_credential(xdg_config / "claude" / ".credentials.json")
    monkeypatch_env = {"XDG_CONFIG_HOME": str(xdg_config)}
    # The function consults the environment; set it explicitly for this assertion.
    assert discover_subscription_credential(
        operator_home=operator_home, environ=monkeypatch_env
    ) == xdg_credential

    # When the XDG location is absent but the default ~/.claude location exists,
    # discovery falls back to it.
    xdg_credential.unlink()
    default_credential = _write_credential(
        operator_home / ".claude" / ".credentials.json"
    )
    assert discover_subscription_credential(operator_home=operator_home) == default_credential


@pytest.mark.asyncio
async def test_moved_credential_is_still_seeded(
    adapter: ClaudeCodeAdapter,
    factory_root: Path,
    worktree: Path,
    stub_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A credential placed under XDG_CONFIG_HOME instead of ~/.claude is still
    discovered and copied into the per-node HOME."""
    operator_home = _fake_operator_home(tmp_path)
    xdg_config = tmp_path / "xdg-config"
    credential_path = _write_credential(xdg_config / "claude" / ".credentials.json")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_config))
    monkeypatch.setattr(
        "factory.workgraph.adapter._operator_home", lambda: operator_home
    )
    write_control(stub_home)

    context = _attempt_context(factory_root=factory_root, worktree=worktree, persona=SUBSCRIPTION)
    result = await adapter.run_attempt(context, factory_root=factory_root)

    assert result.termination == Termination.COMPLETED
    seeded = stub_home / ".claude" / ".credentials.json"
    assert seeded.is_file()
    assert json.loads(seeded.read_text(encoding="utf-8")) == FAKE_CREDENTIAL


# --- T022 [US3-S5 / FR-013] present-but-refused is an auth failure -----------


@pytest.mark.asyncio
async def test_present_but_refused_credential_is_auth_failure(
    adapter: ClaudeCodeAdapter,
    factory_root: Path,
    worktree: Path,
    stub_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A credential that is seeded but rejected by the CLI must be classified as
    an authentication failure, not as a diffless AGENT_ERROR. The measured CLI
    behaviour (2026-08-19) is exit 1 with the refusal on stdout."""
    operator_home = _fake_operator_home(tmp_path)
    _write_credential(operator_home / ".claude" / ".credentials.json")
    monkeypatch.setattr(
        "factory.workgraph.adapter._operator_home", lambda: operator_home
    )
    write_control(stub_home, exit_code=1, stdout=SUBSCRIPTION_REFUSAL)

    context = _attempt_context(factory_root=factory_root, worktree=worktree, persona=SUBSCRIPTION)
    adapter_result = await adapter.run_attempt(context, factory_root=factory_root)

    # The adapter itself classifies by exit status only (FR-012).
    assert adapter_result.termination == Termination.AGENT_ERROR
    # The activity layer reclassifies the specific subscription refusal marker.
    from factory.activities.agent_activities import _classify_subscription_auth_failure
    result = _classify_subscription_auth_failure(context, adapter_result)
    assert result.termination == Termination.AUTH_FAILURE
    log = (factory_root / "transcripts" / EPIC / NODE / f"attempt-{ATTEMPT}" / STDOUT_LOG_NAME).read_text(encoding="utf-8")
    assert SUBSCRIPTION_REFUSAL in log


# --- T051 [US3-S6] placement test: the credential is a distinct copy ---------


@pytest.mark.asyncio
async def test_credential_placement_is_a_distinct_copy(
    adapter: ClaudeCodeAdapter,
    factory_root: Path,
    worktree: Path,
    stub_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The diff commits to a file copy into the per-node HOME. This test asserts
    the placement made is that copy: a regular file, not a symlink or bind, with
    the same bytes and restrictive mode as the source."""
    operator_home = _fake_operator_home(tmp_path)
    source = _write_credential(operator_home / ".claude" / ".credentials.json")
    original_stat = source.stat()
    monkeypatch.setattr(
        "factory.workgraph.adapter._operator_home", lambda: operator_home
    )
    write_control(stub_home)

    context = _attempt_context(factory_root=factory_root, worktree=worktree, persona=SUBSCRIPTION)
    await adapter.run_attempt(context, factory_root=factory_root)

    seeded = stub_home / ".claude" / ".credentials.json"
    assert seeded.is_file()
    assert not seeded.is_symlink()
    # Mode is tightened to 0o600 regardless of source permissions.
    assert (seeded.stat().st_mode & 0o777) == 0o600
    # The bytes are identical to the source, but the inode is different (copy).
    assert seeded.read_bytes() == source.read_bytes()
    assert seeded.stat().st_ino != original_stat.st_ino


# --- discover_subscription_credential unit tests ------------------------------


def test_discover_subscription_credential_prefers_xdg_config(tmp_path: Path) -> None:
    operator_home = _fake_operator_home(tmp_path)
    xdg_config = tmp_path / "xdg-config"
    xdg_path = _write_credential(xdg_config / "claude" / ".credentials.json")
    _write_credential(operator_home / ".claude" / ".credentials.json")

    found = discover_subscription_credential(
        operator_home=operator_home, environ={"XDG_CONFIG_HOME": str(xdg_config)}
    )
    assert found == xdg_path


def test_discover_subscription_credential_falls_back_to_home(tmp_path: Path) -> None:
    operator_home = _fake_operator_home(tmp_path)
    default_path = _write_credential(operator_home / ".claude" / ".credentials.json")

    found = discover_subscription_credential(operator_home=operator_home)
    assert found == default_path


def test_discover_subscription_credential_returns_none_when_missing(
    tmp_path: Path,
) -> None:
    operator_home = _fake_operator_home(tmp_path)
    assert discover_subscription_credential(operator_home=operator_home) is None
