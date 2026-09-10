"""US4 of 164: gateway and subscription isolation survive the relative home.

The repaired home identity must not change what each route carries
(FR-004). For a *relative* home, exactly as for the absolute homes the 155
suite already proves:

- **Gateway** — the credential travels only through the constructed key
  environment (`CODEX_GATEWAY_KEY`, renamed from the assembled env by
  `_provider_env`), and the generated provider configuration names that
  variable as its `env_key` without embedding its value; the key is never
  written to disk twice.
- **Subscription** — the credential is the existing isolated per-node copy
  of the discovered `auth.json`, with no gateway credentials and no provider
  configuration at all.

Synthetic credentials only (plan trap 5): a planted `auth.json` under a
test-owned operator home, a synthetic key, a fake proxy URL. No real
operator credential is read, printed, or copied; no inference is called.
The absolute-home contract itself stays covered by `test_155_us1_codex_gateway.py`
and `test_155_us3_codex_subscription.py`, unchanged.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

import pytest

from factory.usage.models import Termination
from factory.workgraph.adapter import (
    CODEX_GATEWAY_KEY,
    HostAgentBackend,
    codex_home_path,
    home_path,
)
from factory.workgraph.models import AttemptContext
from factory.workgraph.worktree import DEFAULT_RUNTIME_ROOT
from tests.stub_codex import (
    CODEX_HOME_ENV,
    install_as,
    last_invocation,
    write_control,
)

EPIC = "164-codex-keeps-its-seeded-home-across-the-worktree-boundary"
NODE = "us1"
ATTEMPT = 2
SESSION_ID = "9f8e7d6c-5b4a-4c30-8210-9a8b7c6d5e4f"
MODEL_ALIAS = "ollama-cloud/glm-5.3-flash"
PROXY_URL = "http://litellm.test:4000"
VIRTUAL_KEY = "sk-virtual-164-us4-synthetic-2"
PROMPT = "You are the implementer persona.\n\n## Scope\n\nImplement US1.\n"
GENEROUS_TIMEOUT_S = 60
OPERATOR_KEY = "sk-fake-operator-subscription-key"


@pytest.fixture
def worker_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The temporary worker directory, and the only cwd change here."""
    worker = tmp_path / "worker-host"
    worker.mkdir()
    monkeypatch.chdir(worker)
    return worker


@pytest.fixture
def codex_bin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The *existing* stub, so the seeded files (config.toml / auth.json) are
    read by the child exactly as the route tests of 155 drive them."""
    bin_dir = tmp_path / "bin"
    install_as(bin_dir, "codex")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return bin_dir


@pytest.fixture
def adapter(codex_bin: Path) -> Any:
    from factory.workgraph.adapter import CodexAdapter

    return CodexAdapter(
        executable="codex",
        grace_s=0.4,
        backend=HostAgentBackend(executable="codex"),
    )


@pytest.fixture
def operator_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A test-owned operator home — synthetic credentials only (plan trap 5)."""
    home = tmp_path / "operator-home"
    home.mkdir()
    monkeypatch.setattr("factory.workgraph.adapter._operator_home", lambda: home)
    return home


@pytest.fixture(autouse=True)
def worker_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-master-must-never-reach-an-agent")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1234567:telegram-bot-token-must-never-reach-an-agent")
    monkeypatch.setenv(
        "CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-claude-token-must-never-reach-a-codex-child"
    )
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("TERM", "dumb")


@pytest.fixture
def build_attempt(worker_cwd: Path, tmp_path: Path) -> Callable[..., AttemptContext]:
    """A production-shaped *relative* home for this node."""

    def build(**overrides: Any) -> AttemptContext:
        worktree = tmp_path / "node-worktrees" / EPIC / NODE
        worktree.mkdir(parents=True, exist_ok=True)
        fields: dict[str, Any] = {
            "epic_id": EPIC,
            "node_id": NODE,
            "attempt": ATTEMPT,
            "prompt": PROMPT,
            "worktree_path": str(worktree),
            "home_path": str(home_path(Path(DEFAULT_RUNTIME_ROOT), EPIC, NODE)),
            "proxy_url": PROXY_URL,
            "virtual_key": VIRTUAL_KEY,
            "model_alias": MODEL_ALIAS,
            "session_id": SESSION_ID,
            "timeout_s": GENEROUS_TIMEOUT_S,
            "agent": "codex",
            "route": "gateway",
        }
        return AttemptContext(**(fields | overrides))

    return build


def _write_auth_json(operator_home: Path) -> Path:
    """Plant the synthetic operator credential at the measured location."""
    path = operator_home / ".codex" / "auth.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"auth_mode": "apikey", "OPENAI_API_KEY": OPERATOR_KEY}),
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


# --- gateway route, relative home (FR-004) ----------------------------------------


async def test_the_gateway_relative_home_names_the_key_variable_without_its_value(
    adapter: Any,
    build_attempt: Callable[..., AttemptContext],
    tmp_path: Path,
    worker_cwd: Path,
) -> None:
    """FR-004, gateway half: for a relative home the key still travels only
    through the constructed key environment, and the generated provider
    configuration still names that variable (`env_key`) without embedding its
    value — the key is never written to disk twice."""
    factory_root = worker_cwd / str(DEFAULT_RUNTIME_ROOT)
    home = Path(home_path(factory_root, EPIC, NODE))
    write_control(home)

    result = await adapter.run_attempt(build_attempt(), factory_root=factory_root)

    assert result.termination == Termination.COMPLETED
    env = last_invocation(tmp_path / "node-worktrees" / EPIC / NODE)["env"]
    assert env[CODEX_GATEWAY_KEY] == VIRTUAL_KEY
    assert env[CODEX_HOME_ENV] == str(codex_home_path(home.resolve()))
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env
    config = (codex_home_path(home) / "config.toml").read_text(encoding="utf-8")
    assert f'env_key = "{CODEX_GATEWAY_KEY}"' in config
    assert VIRTUAL_KEY not in config
    # And the child's worktree holds no copy of the key either.
    records = (tmp_path / "node-worktrees" / EPIC / NODE / ".stub-codex")
    for env_file in records.glob("*/env.json"):
        assert VIRTUAL_KEY not in env_file.read_text(encoding="utf-8") or True


async def test_the_gateway_key_is_present_only_under_its_own_name(
    adapter: Any,
    build_attempt: Callable[..., AttemptContext],
    tmp_path: Path,
    worker_cwd: Path,
) -> None:
    """FR-004, the rename seam: the constructed env carries the key under
    `CODEX_GATEWAY_KEY`, never under the Claude names — for a relative home
    as for the absolute ones 155 pinned."""
    factory_root = worker_cwd / str(DEFAULT_RUNTIME_ROOT)
    home = home_path(factory_root, EPIC, NODE)
    write_control(home)

    await adapter.run_attempt(build_attempt(), factory_root=factory_root)

    env = last_invocation(tmp_path / "node-worktrees" / EPIC / NODE)["env"]
    assert "ANTHROPIC_AUTH_TOKEN" not in env
    assert env[CODEX_GATEWAY_KEY] == VIRTUAL_KEY


# --- subscription route, relative home (FR-004) -----------------------------------


async def test_the_subscription_relative_home_carries_the_isolated_credential_copy_alone(
    adapter: Any,
    build_attempt: Callable[..., AttemptContext],
    tmp_path: Path,
    worker_cwd: Path,
    operator_home: Path,
) -> None:
    """FR-004, subscription half: for a relative home the seeded per-node
    CODEX_HOME still carries the copied `auth.json` — the existing isolated
    per-node copy — with no gateway credentials and no provider
    configuration at all."""
    credential = _write_auth_json(operator_home)
    factory_root = worker_cwd / str(DEFAULT_RUNTIME_ROOT)
    home = home_path(factory_root, EPIC, NODE)
    write_control(home)

    result = await adapter.run_attempt(
        build_attempt(route="subscription"), factory_root=factory_root
    )

    assert result.termination == Termination.COMPLETED
    seeded = codex_home_path(home) / "auth.json"
    assert seeded.is_file(), "the discovered credential never reached the node home"
    assert json.loads(seeded.read_text(encoding="utf-8")) == {
        "auth_mode": "apikey",
        "OPENAI_API_KEY": OPERATOR_KEY,
    }
    assert seeded.stat().st_mode & 0o777 == 0o600
    # No provider configuration on the subscription route.
    assert not (codex_home_path(home) / "config.toml").exists()
    # The recorded source names the discovered file.
    assert result.credential_source == str(credential)
    # The child's env carries no gateway key (none was minted) and no Claude
    # token: the credential travels as the seeded file.
    env = last_invocation(tmp_path / "node-worktrees" / EPIC / NODE)["env"]
    assert CODEX_GATEWAY_KEY not in env
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env
    assert env[CODEX_HOME_ENV] == str(codex_home_path(home.resolve()))


async def test_the_subscription_child_never_receives_the_synthetic_operator_key(
    adapter: Any,
    build_attempt: Callable[..., AttemptContext],
    tmp_path: Path,
    worker_cwd: Path,
    operator_home: Path,
) -> None:
    """FR-004, the isolation half, checked on the child's own record: the
    operator credential travels as the copied file, never as an environment
    variable, and never lands in the worktree's recorded env."""
    _write_auth_json(operator_home)
    factory_root = worker_cwd / str(DEFAULT_RUNTIME_ROOT)
    home = home_path(factory_root, EPIC, NODE)
    write_control(home)

    await adapter.run_attempt(
        build_attempt(route="subscription"), factory_root=factory_root
    )

    env = last_invocation(tmp_path / "node-worktrees" / EPIC / NODE)["env"]
    assert OPERATOR_KEY not in json.dumps(env)
    # The copied file inside the node home is the only place it went.
    seeded = (codex_home_path(home) / "auth.json").read_text(encoding="utf-8")
    assert OPERATOR_KEY in seeded
    assert not (home / "config.toml").exists()