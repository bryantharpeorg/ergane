"""US3 of 155: a Codex node runs on a ChatGPT subscription.

A persona names `agent: codex` and `route: subscription`; the attempt runs
against the operator's own ChatGPT sign-in with no virtual key minted and no
metered spend — the same shape Claude's subscription route has today. Like
`test_155_us1_codex_gateway.py`, these tests launch a real child —
`tests/stub_codex.py` standing in for the CLI — and read back what it
recorded. Scenarios: US3-S1/FR-006 (no key minted; the node home seeded from
the discovered `auth.json`, whose location is the measured trap-3 fact —
`$CODEX_HOME/auth.json`, default `~/.codex/auth.json`); US3-S2 (the recorded
`credential_source` names the file it came from, so a subscription run is
distinguishable from a gateway run in the evidence); US3-S3 (the rotation
hazard is named as inherited and unmeasured, never pretended measured).

Written before the implementation (constitution II): on the tree as received,
`CodexAdapter._credential` refuses the subscription route by name, no Codex
discovery exists, and `CredentialStage` carries no source to record — the
subscription tests here fail at that refusal, and the discovery tests at the
missing import.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

import pytest
from temporalio.testing import ActivityEnvironment

from factory.activities.usage_activities import (
    IssueKeyInput,
    issue_attempt_key,
    key_alias_for,
)
from factory.usage.models import Termination
from factory.workgraph.adapter import (
    ATTEMPT_ARCHIVE_ENV,
    AdapterError,
    CODEX_GATEWAY_KEY,
    HostAgentBackend,
    discover_codex_credential,
    home_path,
    transcript_dir,
)
from factory.workgraph.models import AttemptContext
from tests.conftest import FakeLiteLLM
from tests.stub_codex import (
    CODEX_HOME_ENV,
    codex_home,
    install_as,
    last_invocation,
    write_control,
)

EPIC = "155-codex-runs-as-a-second-runner"
NODE = "us3"

#: Not 1: the attempt number names the archive directory, and an off-by-one
#: that always wrote `attempt-1` would pass every test that ran one attempt.
ATTEMPT = 2

SESSION_ID = "7d3f6a91-2b4e-4c55-8a19-3e7c5d6b4a32"
PROXY_URL = "http://litellm.test:4000"
VIRTUAL_KEY = "sk-virtual-155-codex-runs-as-a-second-runner-us3-2"
MODEL_ALIAS = "ollama-cloud/glm-5.3-flash"
PROMPT = "You are the implementer persona.\n\n## Scope\n\nImplement US3.\n"
PERSONA = "codex-subscription-CHANGEME"
SPEC_REF = "155-codex-runs-as-a-second-runner/us3"

#: Long enough that no test races its deadline; the production value is the
#: persona registry's (FR-010).
GENEROUS_TIMEOUT_S = 60

FAKE_AUTH_JSON = {
    "auth_mode": "chatgpt",
    "OPENAI_API_KEY": None,
    "tokens": {
        "id_token": (
            "synthetic-id-token.eyJleHAiOjk5OTk5OTk5OTl9.synthetic-signature"
        ),
        "access_token": "synthetic-access-token",
        "refresh_token": "synthetic-refresh-token",
        "account_id": "synthetic-account-id",
    },
    "last_refresh": "2026-01-01T00:00:00+00:00",
}


# --- setup -------------------------------------------------------------------


@pytest.fixture
def codex_bin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """`tests/stub_codex.py` where `codex` would be found (R6); nothing
    configures the binary in production, so the tests do not either."""
    bin_dir = tmp_path / "bin"
    install_as(bin_dir, "codex")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return bin_dir


@pytest.fixture
def worktree(tmp_path: Path) -> Path:
    """Where the agent runs. A directory, not a repository — the adapter's
    contract is "cwd is the path you were handed"."""
    path = tmp_path / "worktrees" / EPIC / NODE
    path.mkdir(parents=True)
    return path


@pytest.fixture
def factory_root(tmp_path: Path) -> Path:
    """The worker host's state directory."""
    return tmp_path / ".factory"


@pytest.fixture
def node_home(factory_root: Path) -> Path:
    """The per-node home — the parent of the seeded CODEX_HOME."""
    return home_path(factory_root, EPIC, NODE)


@pytest.fixture
def operator_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A writable stand-in for the operator's real home directory, wired the
    way the discovery tests drive it — no test here touches the host's real
    home (constitution II)."""
    home = tmp_path / "operator-home"
    home.mkdir()
    monkeypatch.setattr("factory.workgraph.adapter._operator_home", lambda: home)
    return home


@pytest.fixture
def attempt(worktree: Path, node_home: Path) -> Callable[..., AttemptContext]:
    """A subscription-routed Codex attempt; `attempt(route="gateway")`
    overrides one field."""

    def build(**overrides: Any) -> AttemptContext:
        fields: dict[str, Any] = {
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
            "timeout_s": GENEROUS_TIMEOUT_S,
            "agent": "codex",
            "route": "subscription",
        }
        return AttemptContext(**(fields | overrides))

    return build


@pytest.fixture
def adapter(codex_bin: Path, node_home: Path) -> Any:
    """The Codex adapter; the shim is `tests/stub_codex.py` where `codex`
    would be found (R6) — the class names no path, production resolves
    `codex` off the child's `PATH`."""
    from factory.workgraph.adapter import CodexAdapter

    return CodexAdapter(
        executable="codex",
        grace_s=0.4,
        backend=HostAgentBackend(executable="codex"),
    )


@pytest.fixture(autouse=True)
def worker_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """A worker host's environment: credentials planted for every test — the
    allowlist's promise is that no launch anywhere can carry them. Claude's
    long-lived token is planted too: a worker that runs Claude subscription
    personas carries it, and a Codex child must receive none of it."""
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-master-must-never-reach-an-agent")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1234567:telegram-bot-token-must-never-reach-an-agent")
    monkeypatch.setenv(
        "CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-claude-token-must-never-reach-a-codex-child"
    )
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("TERM", "dumb")


def _write_auth_json(operator_home: Path) -> Path:
    """Plant the operator credential at the measured default location."""
    path = operator_home / ".codex" / "auth.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(FAKE_AUTH_JSON, indent=2), encoding="utf-8")
    path.chmod(0o600)
    return path


# --- US3-S1: no virtual key is minted (the dispatch half) -----------------------


async def test_a_subscription_codex_dispatch_leases_no_virtual_key(
    litellm_env: FakeLiteLLM,
) -> None:
    """US3-S1, the dispatch half / FR-006: a persona declaring `agent: codex`
    and `route: subscription` mints no virtual key. The route logic 154 wired
    is generic and already answers this combination — this pins it for the
    agent it now names, because a mint here would be a live credential with
    nothing to use it and an attribution row that reads zero."""
    lease = await ActivityEnvironment().run(
        issue_attempt_key,
        IssueKeyInput(
            node_id=NODE,
            epic_id=EPIC,
            attempt=ATTEMPT,
            persona=PERSONA,
            spec_ref=SPEC_REF,
            models=[MODEL_ALIAS],
            agent="codex",
            route="subscription",
        ),
    )

    assert lease.key == ""
    assert "POST /key/generate" not in litellm_env.routes
    # The attempt still has an identity — a subscription attempt gets its
    # ledger row like any other (001 US2 FR-007).
    assert lease.key_alias == key_alias_for(EPIC, NODE, ATTEMPT, PERSONA)


# --- US3-S1: the node home is seeded from the discovered auth.json --------------


async def test_a_subscription_attempt_seeds_the_node_home_from_the_discovered_auth_json(
    adapter: Any,
    attempt: Callable[..., AttemptContext],
    worktree: Path,
    factory_root: Path,
    node_home: Path,
    operator_home: Path,
) -> None:
    """US3-S1 / FR-006: the discovered `auth.json` is copied into the per-node
    CODEX_HOME, whole and private — and no provider config is written, because
    the CLI's own default provider reads that file, while a gateway declaration
    whose `env_key` names a variable the subscription never sets would refuse
    the launch (measured, US2 evidence shape 2)."""
    _write_auth_json(operator_home)
    write_control(node_home)

    result = await adapter.run_attempt(attempt(), factory_root=factory_root)

    assert result.termination == Termination.COMPLETED
    seeded = codex_home(node_home) / "auth.json"
    assert seeded.is_file(), "the discovered credential never reached the node home"
    assert json.loads(seeded.read_text(encoding="utf-8")) == FAKE_AUTH_JSON
    assert seeded.stat().st_mode & 0o777 == 0o600
    assert not (codex_home(node_home) / "config.toml").exists()


async def test_a_subscription_child_env_carries_no_credential_at_all(
    adapter: Any,
    attempt: Callable[..., AttemptContext],
    worktree: Path,
    factory_root: Path,
    node_home: Path,
    operator_home: Path,
) -> None:
    """US3-S1, the env half: the subscription credential travels as the seeded
    file, never as an environment variable — no gateway key (none was minted),
    no Claude token (that credential is Claude's), and the allowlist stays
    closed to the worker's planted credentials by omission."""
    _write_auth_json(operator_home)
    write_control(node_home)

    await adapter.run_attempt(attempt(), factory_root=factory_root)

    env = last_invocation(worktree)["env"]
    assert set(env) == {
        "HOME",
        "PATH",
        "LANG",
        "TERM",
        CODEX_HOME_ENV,
        ATTEMPT_ARCHIVE_ENV,
    }
    assert env[CODEX_HOME_ENV] == str(codex_home(node_home))
    assert env["HOME"] == str(node_home)
    # Named out of the set above because they are the two credentials a
    # mixed-worker host could leak here: the gateway key and Claude's token.
    assert CODEX_GATEWAY_KEY not in env
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env


# --- US3-S2: credential_source names the file it came from ----------------------


async def test_the_recorded_credential_source_is_redacted_provenance(
    adapter: Any,
    attempt: Callable[..., AttemptContext],
    worktree: Path,
    factory_root: Path,
    node_home: Path,
    operator_home: Path,
) -> None:
    """US3-S2 / FR-006, narrowed by 159: the attempt records redacted
    provenance, so a subscription run is distinguishable from a gateway run
    without an operator home path in the workflow record."""
    credential_path = _write_auth_json(operator_home)
    write_control(node_home)

    result = await adapter.run_attempt(attempt(), factory_root=factory_root)

    assert result.termination == Termination.COMPLETED
    assert result.credential_source is not None
    provenance = json.loads(result.credential_source)
    assert provenance == {
        "credential_mode": "managed-chatgpt",
        "generation": 1,
        "owner_id": "codex-factory",
        "path_identity": provenance["path_identity"],
        "source_kind": "codex-file",
    }
    assert str(credential_path) not in result.credential_source


async def test_a_gateway_run_records_no_credential_source(
    adapter: Any,
    attempt: Callable[..., AttemptContext],
    worktree: Path,
    factory_root: Path,
    node_home: Path,
    operator_home: Path,
) -> None:
    """US3-S2, the control half: a gateway run's credential is the attempt's
    virtual key (constitution V) — there is no discovered file, and the record
    says so by carrying none. The absence is what makes the two routes
    distinguishable in the evidence."""
    write_control(node_home)

    result = await adapter.run_attempt(attempt(route="gateway"), factory_root=factory_root)

    assert result.termination == Termination.COMPLETED
    assert result.credential_source is None


# --- the discovery (FR-006, the analogue of discover_subscription_credential) ---


def test_discovery_finds_the_measured_default_under_the_operator_home(
    operator_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-006 / trap 3: the measured default is `~/.codex/auth.json` — the
    operator's real home, resolved the way Claude's discovery resolves it,
    never this process's (per-node) HOME. `CODEX_HOME` is cleared because the
    relocated-home case is the next test's: a host that happens to export one
    must not decide this answer."""
    monkeypatch.delenv("CODEX_HOME", raising=False)
    credential = _write_auth_json(operator_home)
    assert discover_codex_credential() == credential


def test_discovery_prefers_the_codex_home_the_worker_declares(
    tmp_path: Path, operator_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CODEX_HOME relocates the whole tree (measured, trap 3): a worker host
    that sets it keeps its credential there, and discovery follows the
    variable the CLI itself would read — before the default."""
    relocated = tmp_path / "relocated-codex-home"
    planted = relocated / "auth.json"
    planted.parent.mkdir(parents=True)
    planted.write_text(json.dumps(FAKE_AUTH_JSON), encoding="utf-8")
    _write_auth_json(operator_home)  # the default location carries one too
    monkeypatch.setenv("CODEX_HOME", str(relocated))

    assert discover_codex_credential() == planted


def test_discovery_answers_none_when_no_credential_exists(
    operator_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An absent credential is `None`, never an invented path — the caller
    owns the refusal, the way Claude's discovery's caller does."""
    monkeypatch.delenv("CODEX_HOME", raising=False)
    assert discover_codex_credential() is None


# --- the missing-credential refusal (the analogue of Claude's) ------------------


async def test_a_subscription_attempt_without_a_credential_refuses_at_the_seam(
    adapter: Any,
    attempt: Callable[..., AttemptContext],
    worktree: Path,
    factory_root: Path,
    node_home: Path,
    operator_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No discovered `auth.json`, no gateway fallback: the attempt refuses by
    name before the sandbox forks — the seam Claude's missing credential
    refuses at, naming the remedy instead of spending an attempt discovering
    it."""
    monkeypatch.delenv("CODEX_HOME", raising=False)

    with pytest.raises(AdapterError) as excinfo:
        await adapter.run_attempt(attempt(), factory_root=factory_root)

    assert "auth.json" in str(excinfo.value)
    assert "codex login" in str(excinfo.value)


# --- US3-S3: the rotation hazard, named not solved -------------------------------


def test_the_rotation_hazard_is_recorded_inherited_and_unmeasured() -> None:
    """US3-S3: a subscription credential that rotates on use is an INHERITED
    hazard, UNMEASURED FOR CODEX — the same caveat Claude's discovery carries,
    recorded in the committed source beside the discovery that copies the
    file, where a reader meets it.

    Asserted over the source text because that is where the record lives: the
    spec's wording (inherited, not measured) is a property of the discovery's
    own docstring, not of any runtime behaviour this story could measure —
    measuring rotation would take a live ChatGPT credential and an epic of
    its own."""
    from factory.workgraph import adapter as adapter_module

    source = Path(adapter_module.__file__).read_text(encoding="utf-8")
    normalized = " ".join(source.split())
    for fragment in (
        "INHERITED HAZARD",
        "UNMEASURED FOR CODEX",
        "rotates on use",
        "The per-node copy prevents concurrent nodes",
    ):
        assert fragment in normalized, (
            f"the rotation-hazard record must name {fragment!r} beside the "
            f"discovery that copies the credential"
        )
