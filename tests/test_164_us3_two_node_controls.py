"""US3 of 164: relative and already-absolute homes for two separate nodes.

Two controls over the repaired identity (FR-003):

- **Relative case** — the incident's shape: the workflow-produced relative
  home, seeded by the adapter's own policy, canonicalised before the child
  cwd changes.
- **Already-absolute case** — a worker host that resolved its runtime root
  early presents an absolute home; the repair must preserve its location
  untouched (plan § Repair shape: "preserve already-absolute inputs").

The controls observe behaviour, not helper strings (plan trap 6): each
strict child's own record of what it received, production turn
classification (`_turn_happened` through the shared policy's monitor), and
the archive directory's contents. The two children emit distinct synthetic
rollouts, and the assertions prove each node's own rollout is found in its
own home and archived beside its own log — with no assertion that scans an
ambient location (constitution II).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

import pytest

from factory.usage.models import Termination
from factory.workgraph.adapter import (
    CODEX_EVENTS_NAME,
    CODEX_STDERR_NAME,
    HostAgentBackend,
    codex_home_path,
    home_path,
    transcript_dir,
)
from factory.workgraph.models import AttemptContext
from factory.workgraph.worktree import DEFAULT_RUNTIME_ROOT
from tests.strict_codex_child import CODEX_HOME_ENV, install_as, last_record

EPIC = "164-codex-keeps-its-seeded-home-across-the-worktree-boundary"
NODE_A = "us1"
NODE_B = "us2"
ATTEMPT = 2
SESSION_ID = "1a2b3c4d-5e6f-4a70-8b90-1c2d3e4f5a6b"
MODEL_ALIAS = "ollama-cloud/glm-5.3-flash"
PROXY_URL = "http://litellm.test:4000"
VIRTUAL_KEY = "sk-virtual-164-us3-2"
PROMPT = "You are the implementer persona.\n\n## Scope\n\nImplement US1.\n"
GENEROUS_TIMEOUT_S = 60


@pytest.fixture
def worker_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The temporary worker directory, and the only cwd change here."""
    worker = tmp_path / "worker-host"
    worker.mkdir()
    monkeypatch.chdir(worker)
    return worker


@pytest.fixture
def codex_bin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
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


@pytest.fixture(autouse=True)
def worker_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-master-must-never-reach-an-agent")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1234567:telegram-bot-token-must-never-reach-an-agent")
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("TERM", "dumb")


@pytest.fixture
def build_attempt(worker_cwd: Path, tmp_path: Path) -> Callable[..., AttemptContext]:
    """Build a context for either node; the home is production-shaped:
    relative for node A, already-absolute for node B."""

    def build(node: str, *, relative: bool, **overrides: Any) -> AttemptContext:
        if relative:
            home = str(home_path(Path(DEFAULT_RUNTIME_ROOT), EPIC, node))
        else:
            home = str(
                home_path(
                    (worker_cwd / str(DEFAULT_RUNTIME_ROOT)).resolve(), EPIC, node
                )
            )
        worktree = tmp_path / "node-worktrees" / EPIC / node
        worktree.mkdir(parents=True, exist_ok=True)
        fields: dict[str, Any] = {
            "epic_id": EPIC,
            "node_id": node,
            "attempt": ATTEMPT,
            "prompt": PROMPT,
            "worktree_path": str(worktree),
            "home_path": home,
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


async def test_two_nodes_keep_distinct_homes_and_current_evidence(
    adapter: Any,
    build_attempt: Callable[..., AttemptContext],
    worker_cwd: Path,
    tmp_path: Path,
) -> None:
    """US1-S3: two successful strict children — one on the relative home, one
    on an already-absolute home — write distinct synthetic rollouts; current
    JSONL evidence decides turn detection, so a session-meta rollout is not
    promoted. The two homes stay distinct, and the already-absolute case
    retains its location.
    """
    from factory.workgraph.adapter import CodexAdapter

    factory_root = worker_cwd / str(DEFAULT_RUNTIME_ROOT)
    relative_context = build_attempt(NODE_A, relative=True)
    absolute_context = build_attempt(NODE_B, relative=False)
    # The seeded homes as the *worker* resolves them — the relative
    # declaration against the worker directory, the absolute one as itself.
    relative_home = (worker_cwd / relative_context.home_path).resolve()
    absolute_home = Path(absolute_context.home_path)

    first = await adapter.run_attempt(relative_context, factory_root=factory_root)
    assert first.termination == Termination.COMPLETED
    second = await adapter.run_attempt(absolute_context, factory_root=factory_root)
    assert second.termination == Termination.COMPLETED

    record_a = last_record(tmp_path / "node-worktrees" / EPIC / NODE_A)
    record_b = last_record(tmp_path / "node-worktrees" / EPIC / NODE_B)

    # Each child received its own node's home, absolutely, and read its own
    # seeded configuration.
    assert record_a["codex_home_is_absolute"] is True
    assert record_b["codex_home_is_absolute"] is True
    assert record_a["codex_home"] == str(codex_home_path(relative_home))
    assert record_b["codex_home"] == str(codex_home_path(absolute_home))
    assert record_a["codex_home"] != record_b["codex_home"]
    assert record_a["read"] == record_b["read"] == "config.toml"

    # Production turn detection answers per node, from the current stream
    # each launch built — not from the rollout tree or a sibling's home.
    codex = CodexAdapter(executable="codex")
    env_a = {
        "HOME": str(relative_home),
        CODEX_HOME_ENV: record_a["codex_home"],
    }
    env_b = {
        "HOME": str(absolute_home),
        CODEX_HOME_ENV: record_b["codex_home"],
    }
    assert not codex._turn_happened(relative_context, Path(relative_context.worktree_path), env_a)
    assert not codex._turn_happened(absolute_context, Path(absolute_context.worktree_path), env_b)

    # The archive carries the current stream, but not an unproven rollout.
    for node, record in ((NODE_A, record_a), (NODE_B, record_b)):
        archived = transcript_dir(factory_root, EPIC, node, ATTEMPT)
        archived_rollouts = sorted(p.name for p in archived.glob("rollout-*.jsonl"))
        assert archived_rollouts == [], f"node {node} archived an unproven rollout"
        assert (archived / CODEX_EVENTS_NAME).is_file()
        assert (archived / CODEX_STDERR_NAME).is_file()
        source = Path(str(record["rollout"]))
        assert source.is_file() and source.is_relative_to(
            codex_home_path(relative_home if node == NODE_A else absolute_home)
        )

    # The two homes remain distinct directories, each holding its own rollout.
    assert relative_home != absolute_home
    assert Path(str(record_a["rollout"])).parent != Path(str(record_b["rollout"])).parent


async def test_the_already_absolute_home_retains_its_location(
    adapter: Any,
    build_attempt: Callable[..., AttemptContext],
    worker_cwd: Path,
    tmp_path: Path,
) -> None:
    """FR-003's preserve-half: an already-absolute home is canonicalised to
    itself — the child receives the same location the workflow declared, and
    seeding, child execution and archiving all agree on it. The control is
    the child's own record plus the archive, not a helper comparison."""
    factory_root = worker_cwd / str(DEFAULT_RUNTIME_ROOT)
    context = build_attempt(NODE_B, relative=False)
    declared = Path(context.home_path)
    assert declared.is_absolute()

    result = await adapter.run_attempt(context, factory_root=factory_root)

    assert result.termination == Termination.COMPLETED
    record = last_record(tmp_path / "node-worktrees" / EPIC / NODE_B)
    assert record["codex_home"] == str(codex_home_path(declared))
    # The seeding happened at the declared location, not beside it.
    assert (codex_home_path(declared) / "config.toml").is_file()
    archived = transcript_dir(factory_root, EPIC, NODE_B, ATTEMPT)
    assert (archived / CODEX_EVENTS_NAME).is_file()
