"""US2: a persona can declare that it bills to a subscription.

This story is the routing decision only — no credential is involved, so every
assertion here is over constructed values (environment, argv, key issuance,
preflight alias sets) rather than over a live subscription call. The control
cases are what keep the story from being satisfiable by removing gateway billing
for everyone.

The sentinel on the `agent` field is the established pattern from
`DETERMINISTIC_AGENT`: a second named value that the registry can declare.
Splitting `is_llm` is the heart of the change: it used to mean both "spends
tokens" and "needs a gateway virtual key". A subscription persona spends tokens
but needs no key, so the two questions must be asked separately.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pytest
import httpx

from factory.config import (
    DETERMINISTIC_AGENT,
    SUBSCRIPTION_AGENT,
    ConfigError,
    Persona,
    WriteScope,
    load_personas,
)
from factory.controlplane.verify import LLMProbe
from factory.usage.models import Termination
from factory.workgraph.adapter import (
    ATTEMPT_ARCHIVE_ENV,
    ClaudeCodeAdapter,
    HostAgentBackend,
    attempt_env,
)
from factory.workgraph.models import (
    AttemptContext,
    WorkGraph,
    WorkNode,
)
from factory.workgraph.preflight import aliases_to_check
from tests.stub_agent import (
    STUB_AGENT_PATH,
    install_as,
    last_invocation,
    write_control,
)
from tests.conftest import FakeLiteLLM


#: Minimal synthetic credential for US3-aware tests. US2 does not assert the
#: credential itself, but the adapter now refuses to fork a subscription-routed
#: node without one (US3-S3), so the routing tests must provide it.
_FAKE_CREDENTIAL = {
    "accessToken": "fake-access-token",
    "refreshToken": "fake-refresh-token",
    "expiresAt": "2099-08-20T12:00:00.000Z",
    "refreshTokenExpiresAt": "2099-08-21T12:00:00.000Z",
    "scopes": ["claude_code"],
    "subscriptionType": "pro",
    "rateLimitTier": "default",
}


def _write_credential(home: Path) -> Path:
    path = home / ".claude" / ".credentials.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_FAKE_CREDENTIAL, indent=2), encoding="utf-8")
    path.chmod(0o600)
    return path


def _stub_operator_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Provide a fake operator home with a credential so US3's pre-fork refusal
    does not block US2's routing assertions."""
    home = tmp_path / "operator-home"
    home.mkdir(parents=True)
    _write_credential(home)
    monkeypatch.setattr("factory.workgraph.adapter._operator_home", lambda: home)
    return home

EPIC = "070-subscription-routing"
NODE = "us2"
ATTEMPT = 1
SESSION_ID = "6b1f5d4e-3a2c-4f80-9c1a-7e6d5b4a3c21"
PROXY_URL = "http://litellm.test:4000"
VIRTUAL_KEY = "sk-virtual-070-subscription-routing-us2-1"

#: A proxy alias — the kind of name `personas.yaml` already carries for gateway
#: personas. A subscription persona must *not* pass this through to `--model`.
GATEWAY_ALIAS = "anthropic/claude-opus-5"

#: A name the Claude Code CLI itself accepts, measured 2026-08-19. This is what
#: a subscription-routed node must end up with on argv.
CLI_ALIAS = "opus"


# --- persona fixtures --------------------------------------------------------


def _persona(
    name: str,
    *,
    agent: str = "claude-code",
    model: str | None = GATEWAY_ALIAS,
    fallback: str | None = None,
) -> Persona:
    """A registry entry for one test persona."""
    return Persona(
        name=name,
        agent=agent,
        model=model,
        fallback=fallback,
        skills=(),
        write_scope=WriteScope.WORKTREE,
        needs_worktree=True,
        timeout_s=3600,
    )


#: A deterministic persona — the existing control for the `is_llm` split.
DETERMINISTIC = _persona("verifier", agent=DETERMINISTIC_AGENT, model=None)

#: A gateway persona — the existing path, must stay unchanged.
GATEWAY = _persona("gateway", agent="claude-code", model=GATEWAY_ALIAS)

#: A subscription persona — the new path. Its `model` holds a CLI-side name,
#: because that name never reaches the proxy.
SUBSCRIPTION = _persona("subscription", agent=SUBSCRIPTION_AGENT, model=CLI_ALIAS)


# --- adapter context helpers --------------------------------------------------


def _attempt_context(
    *,
    factory_root: Path,
    persona: Persona,
    model_alias: str = GATEWAY_ALIAS,
) -> AttemptContext:
    worktree = factory_root / "worktrees" / EPIC / NODE
    home = factory_root / "homes" / EPIC / NODE
    return AttemptContext(
        epic_id=EPIC,
        node_id=NODE,
        attempt=ATTEMPT,
        prompt="US2 routing test prompt",
        worktree_path=str(worktree),
        home_path=str(home),
        proxy_url=PROXY_URL,
        virtual_key=VIRTUAL_KEY,
        model_alias=model_alias,
        session_id=SESSION_ID,
        timeout_s=3600,
        agent=persona.agent,
    )


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


# --- T011 [US2-S1] subscription environment omits gateway variables ----------


async def test_subscription_environment_omits_gateway_variables(
    adapter: ClaudeCodeAdapter,
    factory_root: Path,
    worktree: Path,
    stub_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A subscription-routed node gets neither ANTHROPIC_BASE_URL nor
    ANTHROPIC_AUTH_TOKEN in its environment."""
    _stub_operator_home(tmp_path, monkeypatch)
    monkeypatch.setenv("PATH", os.environ["PATH"])
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("TERM", "dumb")
    write_control(stub_home)

    context = _attempt_context(
        factory_root=factory_root,
        persona=SUBSCRIPTION,
        model_alias=CLI_ALIAS,
    )
    await adapter.run_attempt(context, factory_root=factory_root)

    env = last_invocation(worktree).env
    assert "ANTHROPIC_BASE_URL" not in env
    assert "ANTHROPIC_AUTH_TOKEN" not in env
    assert env["HOME"] == str(stub_home)


# --- T012 [US2-S2] no virtual key is minted for a subscription node ----------


@pytest.mark.asyncio
async def test_subscription_node_mints_no_virtual_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`issue_attempt_key` returns an empty key for a subscription persona,
    and does not call the proxy's /key/generate endpoint."""
    from factory.activities import usage_activities
    from factory.activities.usage_activities import issue_attempt_key, IssueKeyInput

    fake = FakeLiteLLM()
    from factory.usage.litellm_client import LiteLLMClient

    monkeypatch.setattr(
        usage_activities,
        "open_client",
        lambda: LiteLLMClient.from_env(transport=fake.transport),
    )
    monkeypatch.setenv("LITELLM_MASTER_KEY", fake.master_key)
    monkeypatch.setenv("LITELLM_PROXY_URL", fake.base_url)

    request = IssueKeyInput(
        node_id=NODE,
        epic_id=EPIC,
        attempt=ATTEMPT,
        persona=SUBSCRIPTION.name,
        spec_ref="070:US2",
        models=[CLI_ALIAS],
        agent=SUBSCRIPTION_AGENT,
    )

    lease = await issue_attempt_key(request)

    assert lease.key == ""
    assert lease.key_alias == f"{EPIC}:{NODE}:{ATTEMPT}:{SUBSCRIPTION.name}"
    assert not [call for call in fake.calls if call.path == "/key/generate"]


# --- T013 [US2-S3] gateway control still gets both variables -----------------


async def test_gateway_environment_still_gets_both_variables(
    adapter: ClaudeCodeAdapter,
    factory_root: Path,
    worktree: Path,
    stub_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control: a gateway persona still receives the proxy URL, the
    virtual key, and the full allowlist exactly as today."""
    monkeypatch.setenv("PATH", os.environ["PATH"])
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("TERM", "dumb")
    write_control(stub_home)

    context = _attempt_context(
        factory_root=factory_root,
        persona=GATEWAY,
        model_alias=GATEWAY_ALIAS,
    )
    await adapter.run_attempt(context, factory_root=factory_root)

    env = last_invocation(worktree).env
    assert env["ANTHROPIC_BASE_URL"] == PROXY_URL
    assert env["ANTHROPIC_AUTH_TOKEN"] == VIRTUAL_KEY
    assert env["HOME"] == str(stub_home)
    assert env["PATH"] == os.environ["PATH"]
    assert env["LANG"] == "en_US.UTF-8"
    assert env["TERM"] == "dumb"
    assert env[ATTEMPT_ARCHIVE_ENV]


# --- T014 [US2-S4] the two `is_llm` callers behave as today ------------------


def test_preflight_alias_check_still_includes_gateway_excludes_deterministic() -> None:
    """`aliases_to_check` keeps including gateway personas and keeps excluding
    deterministic personas after the `is_llm` split."""
    graph = WorkGraph(
        epic_id=EPIC,
        feature="070",
        specs_root="specs",
        target_repo="/tmp/target",
        nodes=[
            WorkNode(
                id="us1",
                story_key="US1",
                persona="gateway",
                spec_ref="070:US1",
                requirement_keys=["US1"],
                depends_on=[],
            ),
            WorkNode(
                id="us2",
                story_key="US2",
                persona="verifier",
                spec_ref="070:US2",
                requirement_keys=["US2"],
                depends_on=[],
            ),
        ],
    )
    registry = {
        "gateway": GATEWAY,
        "verifier": DETERMINISTIC,
        "judge": GATEWAY,
    }

    aliases = aliases_to_check(graph, registry)

    assert GATEWAY_ALIAS in aliases
    assert "verifier" not in aliases.get(GATEWAY_ALIAS, set())


@pytest.mark.asyncio
async def test_llm_probe_still_probes_gateway_skips_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`LLMProbe` keeps probing gateway personas and keeps skipping
    deterministic personas after the `is_llm` split."""
    import factory.controlplane.verify as verify_module
    from factory.controlplane.config import parse_controlplane_config

    registry = {
        "gateway": GATEWAY,
        "verifier": DETERMINISTIC,
    }
    monkeypatch.setattr(verify_module, "_load_personas_for_probe", lambda: registry)
    monkeypatch.setenv("ERGANE_LLM_MASTER_KEY", "sk-fake")

    toml = (
        "version = 1\n"
        "\n"
        "[llm]\n"
        'mode = "gateway"\n'
        'base_url = "http://llm.test/v1"\n'
        'master_key_env = "ERGANE_LLM_MASTER_KEY"\n'
        "\n"
        "[memory]\n"
        'backend = "none"\n'
        "\n"
        "[temporal]\n"
        'mode = "managed"\n'
        "\n"
        "[telemetry]\n"
        "\n"
        "[escalation]\n"
        'adapter = "telegram"\n'
    )
    config = parse_controlplane_config(toml, source="test-config")

    class _CountingClient:
        def __init__(self) -> None:
            self.issued_models: list[list[str]] = []
            self.calls: list[str] = []

        async def chat_completion(self, request: dict[str, Any]) -> dict[str, Any]:
            return {"choices": [{"message": {"content": "pong"}}]}

        async def issue_key(
            self,
            *,
            key_alias: str,
            models: list[str],
            metadata: dict[str, Any] | None = None,
            ttl: str | None = None,
        ) -> str:
            self.issued_models.append(models)
            return "sk-fake-verify-key"

        async def get_key_info(self, key: str) -> dict[str, Any]:
            return {
                "key": key,
                "info": {
                    "key_alias": "verify-probe",
                    "models": self.issued_models[-1] if self.issued_models else [],
                    "metadata": {},
                    "spend": 0.0,
                },
            }

        async def fetch_spend_log_rows(
            self, key: str, *, issued_at: str
        ) -> list[dict[str, Any]]:
            return []

        async def revoke_key_by_tokens(self, keys: list[str]) -> bool:
            return True

        async def aclose(self) -> None:
            pass

    client = _CountingClient()
    monkeypatch.setattr(verify_module, "_llm_client_factory", lambda cfg: client)
    monkeypatch.setattr(
        verify_module, "_host_seam_factory", lambda: {
            "bwrap": {"present": True, "usable": True},
            "git": {"present": True, "usable": True},
            "gh": {"present": True, "usable": True},
        }
    )
    monkeypatch.setattr(
        verify_module, "_telegram_bot_factory",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            verify_module.ServiceNotAnswering("escalation", reason="not configured")
        ),
    )
    monkeypatch.setattr(
        verify_module, "_temporal_client_factory",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            verify_module.ServiceNotAnswering("temporal", reason="not configured")
        ),
    )

    probe = LLMProbe()
    snapshot = await probe.gather(config)
    finding = probe.evaluate(snapshot)

    assert finding.passed is True, finding.detail
    assert GATEWAY_ALIAS in snapshot.aliases
    assert "verifier" not in {
        name for names in snapshot.persona_by_alias.values() for name in names
    }


# --- T049 [US2-S5] argv carries a CLI-accepted name ---------------------------


async def test_subscription_argv_carries_cli_accepted_model_name(
    adapter: ClaudeCodeAdapter,
    factory_root: Path,
    worktree: Path,
    stub_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A subscription-routed node's argv carries the CLI name `opus`, not the
    proxy alias `anthropic/claude-opus-5`."""
    _stub_operator_home(tmp_path, monkeypatch)
    monkeypatch.setenv("PATH", os.environ["PATH"])
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("TERM", "dumb")
    write_control(stub_home)

    context = _attempt_context(
        factory_root=factory_root,
        persona=SUBSCRIPTION,
        model_alias=CLI_ALIAS,
    )
    await adapter.run_attempt(context, factory_root=factory_root)

    invocation = last_invocation(worktree)
    assert invocation.flag("--model") == CLI_ALIAS


async def test_gateway_argv_still_carries_proxy_alias(
    adapter: ClaudeCodeAdapter,
    factory_root: Path,
    worktree: Path,
    stub_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control: a gateway node's argv still passes the registry alias
    through unchanged."""
    monkeypatch.setenv("PATH", os.environ["PATH"])
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("TERM", "dumb")
    write_control(stub_home)

    context = _attempt_context(
        factory_root=factory_root,
        persona=GATEWAY,
        model_alias=GATEWAY_ALIAS,
    )
    await adapter.run_attempt(context, factory_root=factory_root)

    invocation = last_invocation(worktree)
    assert invocation.flag("--model") == GATEWAY_ALIAS


# --- T053 [US2-S6] alias preflight excludes subscription models ----------------


def test_preflight_alias_check_excludes_subscription_models() -> None:
    """For a graph containing a subscription-routed node, the set of aliases
    the preflight checks against the gateway does not include that persona's
    model."""
    graph = WorkGraph(
        epic_id=EPIC,
        feature="070",
        specs_root="specs",
        target_repo="/tmp/target",
        nodes=[
            WorkNode(
                id="us1",
                story_key="US1",
                persona="subscription",
                spec_ref="070:US1",
                requirement_keys=["US1"],
                depends_on=[],
            ),
            WorkNode(
                id="us2",
                story_key="US2",
                persona="gateway",
                spec_ref="070:US2",
                requirement_keys=["US2"],
                depends_on=[],
            ),
        ],
    )
    registry = {
        "subscription": SUBSCRIPTION,
        "gateway": GATEWAY,
        "judge": GATEWAY,
    }

    aliases = aliases_to_check(graph, registry)

    assert CLI_ALIAS not in aliases
    assert GATEWAY_ALIAS in aliases


def test_subscription_persona_is_still_an_llm_for_attribution() -> None:
    """A subscription persona still spends tokens (it is an LLM), but it does
    not route through the gateway and needs no virtual key."""
    assert SUBSCRIPTION.is_llm is True
    assert SUBSCRIPTION.routes_through_gateway is False
    assert SUBSCRIPTION.needs_virtual_key is False

    assert GATEWAY.is_llm is True
    assert GATEWAY.routes_through_gateway is True
    assert GATEWAY.needs_virtual_key is True

    assert DETERMINISTIC.is_llm is False
    assert DETERMINISTIC.routes_through_gateway is False
    assert DETERMINISTIC.needs_virtual_key is False
