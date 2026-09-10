"""US1 of 164: a Codex child reads the same home the activity seeded.

The incident (spec.md § Incident): the workflow passes a *relative* per-node
home — `home_path(DEFAULT_RUNTIME_ROOT, epic, node)` is `.ergane/homes/<epic>/
<node>` — the activity seeds it there, and the child changes directory into
the node worktree while retaining relative `CODEX_HOME`. The directory DID
exist beneath the worker's frozen checkout; the child's cwd change is what
broke it. Tests and the earlier live smoke used absolute homes and missed
this boundary (the same gap `test_155_us1_codex_gateway.py:node_home` has:
it builds its home from an absolute tmp root).

These tests reproduce that boundary with production pieces (plan § Verified
seams, trap 1): the real `home_path` helper with the production relative
runtime root, cwd changed only inside a test-owned temporary worker
directory, the child's worktree somewhere entirely different, and the real
`CodexAdapter.run_attempt` policy — with `tests/strict_codex_child.py`
standing in for installed Codex. The strict child refuses a missing home or
configuration rather than manufacturing one, so the incident's own refusal
is observable in the archived log rather than papered over by a fake turn.

Written against the tree as received (constitution II): the S1 launch test
observes red on the original implementation — the child's env carries
`.ergane/homes/…` verbatim — and green after the T005 repair.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

import pytest

from factory.usage.models import Termination
from factory.workgraph.adapter import (
    ATTEMPT_ARCHIVE_ENV,
    HostAgentBackend,
    _ADAPTERS,
    adapter_for,
    codex_home_path,
    home_path,
    transcript_dir,
)
from factory.workgraph.models import AttemptContext
from factory.workgraph.worktree import DEFAULT_RUNTIME_ROOT
from tests.strict_codex_child import (
    BANNER,
    CODEX_HOME_ENV,
    install_as,
    last_record,
)

EPIC = "164-codex-keeps-its-seeded-home-across-the-worktree-boundary"

#: Two separate nodes, so the two-node control (US1-S3) can prove homes stay
#: distinct and each child reads only its own node's seeding.
NODE_A = "us1"
NODE_B = "us2"
ATTEMPT = 2

SESSION_ID = "1a2b3c4d-5e6f-4a70-8b90-1c2d3e4f5a6b"
MODEL_ALIAS = "ollama-cloud/glm-5.3-flash"
PROXY_URL = "http://litellm.test:4000"
VIRTUAL_KEY = "sk-virtual-164-us1-2"
PROMPT = "You are the implementer persona.\n\n## Scope\n\nImplement US1.\n"
GENEROUS_TIMEOUT_S = 60

#: The synthetic rollout date the strict child writes under (its own tree),
#: so a test can read the file back without parsing the record.
ROLLOUT_SUBTREE = "sessions/2026/09/10"


def _relative_home(factory_root: Path, epic: str, node: str) -> str:
    """The production shape: `home_path` on the relative runtime root.

    This is the helper and the argument the workflow passes today
    (`workflow.py` builds `str(home_path(DEFAULT_FACTORY_ROOT, …))` with
    `DEFAULT_FACTORY_ROOT = DEFAULT_RUNTIME_ROOT = Path(".ergane")`). The
    string is deliberately relative — that is the incident's boundary, not a
    fixture convenience.
    """
    return str(home_path(Path(DEFAULT_RUNTIME_ROOT), epic, node))


# --- setup -------------------------------------------------------------------


@pytest.fixture
def worker_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The temporary worker directory, and the only cwd change here (trap 1).

    The production activity resolves the relative runtime root against the
    worker's working directory, so the test *is* the worker: it chdirs into a
    test-owned directory and lets the relative home resolve beneath it. The
    node worktrees live outside this directory — elsewhere on the same
    filesystem — which is exactly the two-locations boundary the incident
    crossed.
    """
    worker = tmp_path / "worker-host"
    worker.mkdir()
    monkeypatch.chdir(worker)
    return worker


@pytest.fixture
def codex_bin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The strict child where `codex` would be found (R6)."""
    bin_dir = tmp_path / "bin"
    install_as(bin_dir, "codex")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return bin_dir


@pytest.fixture
def worktree(tmp_path: Path) -> Path:
    """Node A's worktree: absolute, and NOT under the worker directory."""
    path = tmp_path / "node-worktrees" / EPIC / NODE_A
    path.mkdir(parents=True)
    return path


@pytest.fixture
def worktree_b(tmp_path: Path) -> Path:
    """Node B's worktree, distinct from node A's."""
    path = tmp_path / "node-worktrees" / EPIC / NODE_B
    path.mkdir(parents=True)
    return path


@pytest.fixture
def factory_root(worker_cwd: Path) -> Path:
    """The worker host's state directory, as the production default spells
    it: the *relative* `.ergane`, resolved against the worker directory."""
    return worker_cwd / str(DEFAULT_RUNTIME_ROOT)


@pytest.fixture
def node_home(factory_root: Path) -> Path:
    """Node A's per-node home — the parent of the seeded CODEX_HOME."""
    return home_path(factory_root, EPIC, NODE_A)


@pytest.fixture
def node_home_b(factory_root: Path) -> Path:
    """Node B's per-node home."""
    return home_path(factory_root, EPIC, NODE_B)


@pytest.fixture
def attempt(
    worktree: Path,
    node_home: Path,
    worker_cwd: Path,
) -> Callable[..., AttemptContext]:
    """Build the production-shaped relative-home context; `attempt(...)`
    overrides a field. `home_path` is the *string* `home_path()` produced from
    the relative root — never re-absolutised here."""

    def build(node: str = NODE_A, **overrides: Any) -> AttemptContext:
        fields: dict[str, Any] = {
            "epic_id": EPIC,
            "node_id": node,
            "attempt": ATTEMPT,
            "prompt": PROMPT,
            "worktree_path": str(worktree),
            "home_path": _relative_home(worker_cwd, EPIC, node),
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


@pytest.fixture
def adapter(codex_bin: Path) -> Any:
    """The real `CodexAdapter` policy through the host backend."""
    from factory.workgraph.adapter import CodexAdapter

    return CodexAdapter(
        executable="codex",
        grace_s=0.4,
        backend=HostAgentBackend(executable="codex"),
    )


@pytest.fixture(autouse=True)
def worker_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """A worker host's environment, credentials planted — the allowlist's
    promise is that no launch anywhere can carry them."""
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-master-must-never-reach-an-agent")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1234567:telegram-bot-token-must-never-reach-an-agent")
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("TERM", "dumb")


def archive_dir(worker_cwd: Path, node: str = NODE_A, attempt_number: int = ATTEMPT) -> Path:
    return transcript_dir(worker_cwd / str(DEFAULT_RUNTIME_ROOT), EPIC, node, attempt_number)


def stdout_log(worker_cwd: Path, node: str = NODE_A) -> str:
    return (archive_dir(worker_cwd, node) / "stdout.log").read_text(encoding="utf-8")


# --- US1-S1: the seeded home survives the cwd change (FR-001, FR-003) -----------


async def test_the_child_receives_the_absolute_seeded_home_across_the_cwd_change(
    adapter: Any,
    attempt: Callable[..., AttemptContext],
    worktree: Path,
    worker_cwd: Path,
    node_home: Path,
) -> None:
    """US1-S1 / FR-001: given the production relative home and a worktree
    elsewhere on the filesystem, the child's `CODEX_HOME` names the already-
    seeded directory *absolutely*, the child's cwd is the worktree, and the
    child completes — its reads of the seeded configuration succeeded.

    The seeding is done by the adapter's own policy (the activity-side seam),
    so the test seeds nothing itself: the assertion is that the home the child
    reads is the one that seeding created, after the cwd change.
    """
    result = await adapter.run_attempt(attempt(), factory_root=worker_cwd / str(DEFAULT_RUNTIME_ROOT))

    assert result.termination == Termination.COMPLETED
    record = last_record(worktree)
    assert record["cwd"] == str(worktree), "the child's cwd is the node worktree"
    assert record["codex_home_is_absolute"] is True, (
        f"the child received the relative home {record['codex_home']!r} verbatim; "
        f"the worktree boundary resolved it against the worktree, not the worker"
    )
    assert record["codex_home"] == str(codex_home_path(node_home)), (
        "the absolute CODEX_HOME must name the already-seeded per-node home"
    )
    assert record["read"] == "config.toml", "the child read the seeded gateway configuration"
    assert "ergane-gateway" in record["config"]
    assert record["stdin"] == PROMPT
    assert BANNER in stdout_log(worker_cwd)


def test_the_production_seam_canonicalises_the_relative_home(
    attempt: Callable[..., AttemptContext],
    worker_cwd: Path,
) -> None:
    """The S1 seam, pinned after the repair (T005): `_provider_env` spells
    CODEX_HOME as the *absolute* location the relative declaration already
    named — resolved against the worker's own cwd, never re-rooted anywhere
    else. The production helper itself still produces the relative string;
    the canonicalisation is the seam's, and this is what keeps it there."""
    from factory.workgraph.adapter import CodexAdapter

    codex = CodexAdapter(executable="codex")
    env: dict[str, str] = {}
    prepared = codex._provider_env(env, attempt())
    assert prepared[CODEX_HOME_ENV] == str(
        (worker_cwd / _relative_home(worker_cwd, EPIC, NODE_A) / ".codex").resolve()
    )


# --- US1-S3: two nodes, two homes, each rollout found at home (FR-003) -----------


async def test_two_nodes_each_find_their_own_rollout_and_their_homes_stay_distinct(
    adapter: Any,
    attempt: Callable[..., AttemptContext],
    worktree: Path,
    worktree_b: Path,
    worker_cwd: Path,
    node_home: Path,
    node_home_b: Path,
) -> None:
    """US1-S3 / FR-003: relative and already-absolute homes for two separate
    nodes. Each strict child emits a distinct synthetic rollout in its own
    seeded home; production turn detection answers per node, the archive
    carries each node's own file, the two homes stay distinct — and the
    already-absolute case keeps its location untouched (FR-003's second
    half, plan § Repair shape: "preserve already-absolute inputs").

    Observed through the child, classification and archived files, not by
    comparing helper strings."""
    from factory.workgraph.models import AttemptContext as Context

    # Node A: the incident's relative home. Node B: an already-absolute home,
    # built by the same helper from an absolute root, as a worker host that
    # resolved its root early receives it.
    relative = attempt(node=NODE_A)
    absolute = attempt(
        node=NODE_B,
        home_path=str(node_home_b.resolve()),
        worktree_path=str(worktree_b),
    )

    first = await adapter.run_attempt(relative, factory_root=worker_cwd / str(DEFAULT_RUNTIME_ROOT))
    assert first.termination == Termination.COMPLETED
    second = await adapter.run_attempt(absolute, factory_root=worker_cwd / str(DEFAULT_RUNTIME_ROOT))
    assert second.termination == Termination.COMPLETED

    record_a = last_record(worktree)
    record_b = last_record(worktree_b)

    # Each child read the seeded configuration of its own node.
    assert record_a["codex_home"] == str(codex_home_path(node_home))
    assert record_b["codex_home"] == str(codex_home_path(node_home_b))
    assert Path(record_a["codex_home"]) != Path(record_b["codex_home"])
    assert record_a["read"] == record_b["read"] == "config.toml"
    assert record_b["codex_home_is_absolute"] is True
    # The relative case was canonicalised; the absolute case retained its own
    # location (the same resolve() an absolute path is its own answer under).
    assert record_a["codex_home"] == str(codex_home_path(node_home.resolve()))
    assert record_b["codex_home"] == str(codex_home_path(node_home_b))

    # Production turn detection answers per node, from each child's env.
    from factory.workgraph.adapter import CodexAdapter

    codex = CodexAdapter(executable="codex")
    env_a = {"HOME": str(node_home), CODEX_HOME_ENV: str(codex_home_path(node_home))}
    env_b = {"HOME": str(node_home_b), CODEX_HOME_ENV: str(codex_home_path(node_home_b))}
    assert codex._turn_happened(relative, worktree, env_a)
    assert codex._turn_happened(absolute, worktree_b, env_b)
    # The control: a node whose own home holds no rollout tree answers no —
    # the probe reads the env's own tree, never a sibling's (the env the
    # launch built names this node's home; that is what record_a/b asserted).
    fresh_home = home_path(node_home.parent.parent, EPIC, "us9")
    fresh_home.mkdir(parents=True, exist_ok=True)
    env_fresh = {"HOME": str(fresh_home), CODEX_HOME_ENV: str(codex_home_path(fresh_home))}
    assert not codex._turn_happened(relative, worktree, env_fresh)

    # The archive carries each node's own rollout, and only that node's.
    for node, record in ((NODE_A, record_a), (NODE_B, record_b)):
        archived = archive_dir(worker_cwd, node)
        archived_rollouts = sorted(p.name for p in archived.glob("rollout-*.jsonl"))
        assert archived_rollouts == [Path(str(record["rollout"])).name], (
            f"node {node}: the archive did not carry exactly its own rollout "
            f"(archived {archived_rollouts})"
        )
    # And the two rollout files are distinct files in distinct homes.
    assert Path(record_a["rollout"]) != Path(record_b["rollout"])
    assert Path(record_a["rollout"]).is_relative_to(codex_home_path(node_home))
    assert Path(record_b["rollout"]).is_relative_to(codex_home_path(node_home_b))


# --- the environment is still the built allowlist (FR-002, FR-004) --------------


async def test_the_relative_home_launch_still_carries_no_worker_credential(
    adapter: Any,
    attempt: Callable[..., AttemptContext],
    worktree: Path,
    worker_cwd: Path,
    node_home: Path,
) -> None:
    """FR-002: the repair changes where CODEX_HOME points, nothing else —
    the allowlist stays closed by omission, read off the child's own env
    record, with the values checked and not just their names."""
    result = await adapter.run_attempt(attempt(), factory_root=worker_cwd / str(DEFAULT_RUNTIME_ROOT))

    assert result.termination == Termination.COMPLETED
    env = last_record(worktree)["env"]
    assert "LITELLM_MASTER_KEY" not in env
    assert "TELEGRAM_BOT_TOKEN" not in env
    assert "sk-master-must-never-reach-an-agent" not in json.dumps(env)
    assert "telegram-bot-token-must-never-reach-an-agent" not in json.dumps(env)
    # The ferry channel is still constructed, and CODEX_HOME still names the
    # seeded home.
    assert env[ATTEMPT_ARCHIVE_ENV] == str(archive_dir(worker_cwd))
    assert env[CODEX_HOME_ENV] == str(codex_home_path(node_home.resolve()))


# --- the registry still resolves codex by its own name (FR-005) -----------------


def test_a_persona_naming_codex_still_resolves_the_registered_adapter() -> None:
    assert "codex" in _ADAPTERS
    resolved = adapter_for("codex")
    assert type(resolved).__name__ == "CodexAdapter"
    assert resolved.name == "codex"