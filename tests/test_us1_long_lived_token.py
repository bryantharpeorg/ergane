"""US1 of epic 125: a long-lived subscription token reaches the agent.

The token is a subscription OAuth credential, `sk-ant-oat01-` prefixed, scope
`user:inference`, minted by `claude setup-token`. It arrives as an environment
variable `CLAUDE_CODE_OAUTH_TOKEN` and must be carried into the subscription-
routed agent boundary while staying out of gateway-routed attempts and the gate
boundary.

Every credential-like string below is synthetic (trap 4).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from factory.config import SUBSCRIPTION_AGENT, Persona, WriteScope
from factory.usage.models import Termination
from factory.verify.gates import scrubbed_env
from factory.verify.models import ROUTE_SUBSCRIPTION
from factory.verify.toolchain import ResolvedTool
from factory.workgraph.adapter import (
    ATTEMPT_ARCHIVE_ENV,
    CLAUDE_CODE_OAUTH_TOKEN,
    CREDENTIAL_SOURCE_COPIED_CREDENTIALS,
    CREDENTIAL_SOURCE_OAUTH_TOKEN,
    PASSTHROUGH_ENV,
    BwrapBackend,
    ClaudeCodeAdapter,
    HostAgentBackend,
    attempt_env,
    discover_subscription_credential,
)
from factory.workgraph.models import AttemptContext
from tests.stub_agent import (
    STUB_AGENT_PATH,
    install_as,
    last_invocation,
    write_control,
)

EPIC = "125-a-credential-outlives-the-night"
NODE = "us1"
ATTEMPT = 1
SESSION_ID = "6b1f5d4e-3a2c-4f80-9c1a-7e6d5b4a3c21"
PROXY_URL = "http://litellm.test:4000"
VIRTUAL_KEY = "sk-virtual-125-us1-1"

#: A synthetic long-lived subscription token. Real tokens share the `sk-ant-oat01-`
#: prefix but this value is generated for tests and never valid anywhere.
OAUTH_TOKEN = "sk-ant-oat01-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

#: A minimal synthetic copied credential file. Its shape matches the measured field
#: set; the adapter copies bytes and never parses the credential (US3).
_FAKE_CREDENTIAL = {
    "accessToken": "fake-access-token",
    "refreshToken": "fake-refresh-token",
    "expiresAt": "2026-08-20T12:00:00.000Z",
    "refreshTokenExpiresAt": "2026-08-21T12:00:00.000Z",
    "scopes": ["claude_code"],
    "subscriptionType": "pro",
    "rateLimitTier": "default",
}


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


GATEWAY = _persona("gateway", agent="claude-code", model="anthropic/claude-opus-5")
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
    persona: Persona,
    model_alias: str = "opus",
) -> AttemptContext:
    home = factory_root / "homes" / EPIC / NODE
    return AttemptContext(
        epic_id=EPIC,
        node_id=NODE,
        attempt=ATTEMPT,
        prompt="US1 token routing test prompt",
        worktree_path=str(worktree),
        home_path=str(home),
        proxy_url=PROXY_URL,
        virtual_key=VIRTUAL_KEY,
        model_alias=model_alias,
        session_id=SESSION_ID,
        timeout_s=3600,
        agent=persona.agent,
    )


def _fake_operator_home(tmp_path: Path) -> Path:
    """A writable stand-in for the operator's real home directory."""
    home = tmp_path / "operator-home"
    home.mkdir(parents=True)
    return home


def _write_credential(path: Path, content: dict | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(content if content is not None else _FAKE_CREDENTIAL, indent=2),
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


# --- T001 [P] [US1-S1] subscription env carries the token ---------------------


def test_subscription_env_carries_oauth_token(factory_root: Path) -> None:
    """When the worker environment carries the long-lived token, a subscription-
    routed `attempt_env` includes it."""
    home = factory_root / "homes" / EPIC / NODE
    context = _attempt_context(
        factory_root=factory_root,
        worktree=factory_root / "worktrees" / EPIC / NODE,
        persona=SUBSCRIPTION,
    )
    environ = {"CLAUDE_CODE_OAUTH_TOKEN": OAUTH_TOKEN}

    env = attempt_env(context, environ=environ, routes_through_gateway=False)

    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == OAUTH_TOKEN


# --- T002 [P] [US1-S2] token survives into the sandbox argv ---------------------


def test_token_survives_into_bwrap_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The token is set in the bwrap argument vector after `--clearenv`, not
    only in the environment dict the adapter records."""
    backend = BwrapBackend(executable="/bin/claude")

    # Suppress host-derived parts of `_build_argv` so the test does not depend on
    # the machine's system layout or toolchain installation.
    monkeypatch.setattr(
        backend, "_toolchain", lambda: [
            ResolvedTool(name="claude", found_at=Path("/bin/claude"), real_path=Path("/bin/claude"))
        ]
    )
    monkeypatch.setattr(
        backend, "_toolchain_binds", lambda _tools=None: [
            ("--ro-bind", "/bin/claude", "/bin/claude")
        ]
    )
    monkeypatch.setattr(
        "factory.verify.toolchain.system_tree_argv", lambda _root: []
    )
    monkeypatch.setattr(
        "factory.workgraph.adapter.ordered_binds", lambda binds: [item for bind in binds for item in bind]
    )

    # The gate-boundary helper is instantiated inside `_build_argv`; stub its
    # host-dependent methods so no real interpreter/cache discovery runs.
    monkeypatch.setattr(
        "factory.verify.gates.BwrapGateExecutor._interpreter_binds", lambda _self, _worktree: []
    )
    monkeypatch.setattr(
        "factory.verify.gates.BwrapGateExecutor._resolver_binds", lambda _self: []
    )
    monkeypatch.setattr(
        "factory.verify.gates.BwrapGateExecutor._cache_binds", lambda _self: []
    )

    worktree = tmp_path / "worktree"
    worktree.mkdir(parents=True)
    home = tmp_path / "home"
    home.mkdir(parents=True)

    from factory.workgraph.adapter import AgentInvocation
    invocation = AgentInvocation(
        argv=["claude", "-p"],
        prompt="test",
        worktree=worktree,
        env={
            "HOME": str(home),
            "PATH": "/bin",
            "CLAUDE_CODE_OAUTH_TOKEN": OAUTH_TOKEN,
        },
        log=None,
        standards_path=None,
        model_alias="opus",
    )

    argv = backend._build_argv(invocation)

    # `--clearenv` must precede the `--setenv` that carries the token.
    clearenv_index = argv.index("--clearenv")
    setenv_indices = [
        i for i, token in enumerate(argv) if token == "--setenv" and i + 1 < len(argv)
    ]
    token_entry = next(
        (i for i in setenv_indices if argv[i + 1] == "CLAUDE_CODE_OAUTH_TOKEN"),
        None,
    )
    assert token_entry is not None, "no --setenv for CLAUDE_CODE_OAUTH_TOKEN in argv"
    assert argv[token_entry + 2] == OAUTH_TOKEN
    assert token_entry > clearenv_index


# --- T003 [P] [US1-S3] gateway env omits the token ----------------------------


def test_gateway_env_omits_oauth_token(factory_root: Path) -> None:
    """A gateway-routed attempt receives neither the subscription token nor a
    subscription credential; it keeps the proxy variables exactly as today."""
    worktree = factory_root / "worktrees" / EPIC / NODE
    context = _attempt_context(
        factory_root=factory_root,
        worktree=worktree,
        persona=GATEWAY,
        model_alias="anthropic/claude-opus-5",
    )
    environ = {
        "PATH": "/usr/bin",
        "LANG": "en_US.UTF-8",
        "TERM": "dumb",
        "CLAUDE_CODE_OAUTH_TOKEN": OAUTH_TOKEN,
    }

    env = attempt_env(context, environ=environ, routes_through_gateway=True)

    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env
    assert env["ANTHROPIC_BASE_URL"] == PROXY_URL
    assert env["ANTHROPIC_AUTH_TOKEN"] == VIRTUAL_KEY
    assert env["PATH"] == "/usr/bin"
    assert env["LANG"] == "en_US.UTF-8"
    assert env["TERM"] == "dumb"


# --- T004 [P] [US1-S4] no token: byte-identical backward path -----------------


@pytest.mark.asyncio
async def test_no_token_subscription_still_seeds_copied_credential(
    adapter: ClaudeCodeAdapter,
    factory_root: Path,
    worktree: Path,
    stub_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a long-lived token, a subscription-routed attempt behaves exactly
    as today: the copied credential is seeded into the per-node HOME and the
    environment is the same shape as before US1."""
    operator_home = _fake_operator_home(tmp_path)
    credential_path = _write_credential(operator_home / ".claude" / ".credentials.json")
    monkeypatch.setattr(
        "factory.workgraph.adapter._operator_home", lambda: operator_home
    )
    # Ensure the token is absent from the worker environment.
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    write_control(stub_home)

    context = _attempt_context(
        factory_root=factory_root,
        worktree=worktree,
        persona=SUBSCRIPTION,
    )
    result = await adapter.run_attempt(context, factory_root=factory_root)

    assert result.termination == Termination.COMPLETED
    assert result.credential_source == CREDENTIAL_SOURCE_COPIED_CREDENTIALS
    env = last_invocation(worktree).env
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env
    assert "ANTHROPIC_BASE_URL" not in env
    assert "ANTHROPIC_AUTH_TOKEN" not in env
    seeded = stub_home / ".claude" / ".credentials.json"
    assert seeded.is_file()
    assert json.loads(seeded.read_text(encoding="utf-8")) == _FAKE_CREDENTIAL


# --- T005 [P] [US1-S5] token wins; record states the source ---------------------


@pytest.mark.asyncio
async def test_token_wins_and_record_states_source(
    adapter: ClaudeCodeAdapter,
    factory_root: Path,
    worktree: Path,
    stub_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When both a long-lived token and a copied credential are present, the
    token is the credential delivered to the agent, and the adapter's result
    records that source so the precedence is legible rather than inferred."""
    operator_home = _fake_operator_home(tmp_path)
    _write_credential(operator_home / ".claude" / ".credentials.json")
    monkeypatch.setattr(
        "factory.workgraph.adapter._operator_home", lambda: operator_home
    )
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", OAUTH_TOKEN)
    write_control(stub_home)

    context = _attempt_context(
        factory_root=factory_root,
        worktree=worktree,
        persona=SUBSCRIPTION,
    )
    result = await adapter.run_attempt(context, factory_root=factory_root)

    assert result.termination == Termination.COMPLETED
    assert result.credential_source == CREDENTIAL_SOURCE_OAUTH_TOKEN
    env = last_invocation(worktree).env
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == OAUTH_TOKEN
    assert "ANTHROPIC_BASE_URL" not in env
    assert "ANTHROPIC_AUTH_TOKEN" not in env


# --- T006 [P] [US1-S6] gate boundary omits the token --------------------------


def test_gate_boundary_omits_oauth_token() -> None:
    """The gate boundary constructs its own environment from an allowlist and
    does not inherit `CLAUDE_CODE_OAUTH_TOKEN` even when the worker carries it."""
    source = {
        "PATH": "/usr/bin",
        "HOME": "/home/operator",
        "CLAUDE_CODE_OAUTH_TOKEN": OAUTH_TOKEN,
    }

    env = scrubbed_env(source)

    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env
    assert "PATH" in env


# --- T007 [P] [FR-012] regression pins ----------------------------------------


def test_passthrough_env_is_unchanged() -> None:
    """The global allowlist keeps exactly its three members; the token was added
    to the subscription branch, not here."""
    assert PASSTHROUGH_ENV == ("PATH", "LANG", "TERM")


def test_no_anthropic_api_key_introduced() -> None:
    """No story introduces `ANTHROPIC_API_KEY` as an env-var mechanism in
    `factory/` (trap 3). The string may appear in docstrings and comments
    explaining the bearer-token path, but never as a variable or string the
    factory sets or reads."""
    import ast

    repo_root = Path(__file__).resolve().parents[1]
    factory_dir = repo_root / "factory"

    def _collect_docstrings(tree: ast.AST) -> set[int]:
        """Return ids of the AST Constant nodes that are module/class/function
        docstrings."""
        ids: set[int] = set()
        for node in ast.walk(tree):
            body: list[ast.AST] | None = None
            if isinstance(node, (ast.Module, ast.ClassDef)):
                body = node.body
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(
                body[0].value, ast.Constant
            ) and isinstance(body[0].value.value, str):
                ids.add(id(body[0].value))
        return ids

    def _check_file(path: Path) -> str | None:
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return None

        docstring_nodes = _collect_docstrings(tree)

        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "ANTHROPIC_API_KEY":
                return f"{path}:{node.lineno}: used as identifier"
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstring_nodes
                and "ANTHROPIC_API_KEY" in node.value
            ):
                return f"{path}:{node.lineno}: used in non-docstring string"

        return None

    found: str | None = None
    for path in factory_dir.rglob("*.py"):
        if not path.is_file():
            continue
        found = _check_file(path)
        if found:
            break

    assert not found, f"ANTHROPIC_API_KEY must not appear as code in factory/: {found}"
