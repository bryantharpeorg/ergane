"""US2 of 164 (the S2 half of the story): the sandbox launch preserves the
seeded home's identity.

The host launch's repair is `CodexAdapter._provider_env`'s (T005); the
bubblewrap backend is the second consumer the same identity has to reach —
`BwrapBackend._build_argv` passes `CODEX_HOME` through its `--setenv`
allowlist unchanged, so the value it passes is whatever the invocation's env
carries. After the T005 repair that value is the absolute seeded home built
in the adapter, and these tests prove the two halves the acceptance scenario
names:

1. Construction, on every host: the argv carries `--setenv CODEX_HOME`
   naming the same seeded location the host launch would name (FR-002's
   identity preserved across both backends), the worktree is still the
   `--chdir` destination, and the mount set is not widened for the home —
   the runtime root that contains it stays read-only and the home leaf stays
   the one writable location (the existing trap-9 shape).
2. Execution, where supported: the constructed launch actually runs a
   credential-free strict child, which reads the seeded configuration and
   writes its synthetic rollout into the per-node home through the existing
   bind. Where `bwrap` is absent the skip is explicit and named
   (`@pytest.mark.skipif` with its own reason), never a catch-all success
   (plan trap 7).

Existing bubblewrap test conventions are followed: the toolchain is planted
in `tmp_path` (`PlantedHost`), the launcher is a real executable discovery
resolves on the planted `PATH`, and the strict child and its interpreter are
visible through the current binds — nothing here widens the mount set to
make a test pass.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from factory.workgraph.adapter import (
    CODEX_HOME_ENV,
    AgentInvocation,
    BwrapBackend,
    home_path,
)
from factory.workgraph.worktree import DEFAULT_RUNTIME_ROOT
from tests.strict_codex_child import install_as, last_record
from tests.test_toolchain_discovery import PlantedHost, _binds, _setenv

EPIC = "164-codex-keeps-its-seeded-home-across-the-worktree-boundary"
NODE = "us1"
BWRAP_PRESENT = shutil.which("bwrap") is not None
LAUNCH_TIMEOUT_S = 60
PROMPT = "You are the implementer persona.\n\n## Scope\n\nImplement US1.\n"


# --- the planted host --------------------------------------------------------


@pytest.fixture
def seeded_home(tmp_path: Path) -> Path:
    """The per-node home with its `.codex` configuration already seeded — the
    state the adapter's seeding leaves before any launch. The runtime root is
    absolute here, as a worker host that resolved it early presents it."""
    factory_root = tmp_path / "worker-host" / str(DEFAULT_RUNTIME_ROOT)
    home = home_path(factory_root, EPIC, NODE)
    codex_home = home / ".codex"
    codex_home.mkdir(parents=True)
    (codex_home / "config.toml").write_text(
        'model_provider = "ergane-gateway"\n', encoding="utf-8"
    )
    return home


def _plant_toolchain(host: PlantedHost) -> None:
    for name in ("uv", "node", "git", "claude"):
        host.plant(name)


def _invocation(
    *,
    worktree: Path,
    codex_bin: Path,
    search_dirs: tuple[Path, ...],
    env_home: Path,
    log: Any = None,
) -> AgentInvocation:
    """A codex-shaped invocation, built only from planted paths, whose env
    names the seeded home the way the repaired adapter does."""
    search = os.pathsep.join(str(directory) for directory in search_dirs if str(directory))
    return AgentInvocation(
        argv=[str(codex_bin / "codex"), "exec", "-"],
        prompt=PROMPT,
        worktree=worktree,
        env={
            "PATH": search,
            "HOME": str(env_home),
            CODEX_HOME_ENV: str(env_home / ".codex"),
        },
        log=log,
        standards_path=None,
        model_alias="ollama-cloud/glm-5.3-flash",
    )


# --- construction: the identity reaches the argv (FR-002) ------------------------


def test_the_sandbox_argv_sets_codex_home_to_the_seeded_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    seeded_home: Path,
) -> None:
    """US1-S2, construction (FR-002): the assembled bwrap argv carries
    `--setenv CODEX_HOME` naming the seeded per-node home, absolutely — the
    same identity the host launch names. The backend is a pass-through of the
    identity the adapter canonicalised, not a second resolver."""
    host = PlantedHost(tmp_path / "host")
    _plant_toolchain(host)
    codex_bin = tmp_path / "bin"
    install_as(codex_bin, "codex")
    host.activate(monkeypatch, host.bin_dir, codex_bin)

    worktree = tmp_path / "node-worktrees" / EPIC / NODE
    worktree.mkdir(parents=True)

    invocation = _invocation(
        worktree=worktree,
        codex_bin=codex_bin,
        search_dirs=(codex_bin, host.bin_dir),
        env_home=seeded_home,
    )
    assert invocation.env[CODEX_HOME_ENV] == str(seeded_home / ".codex")

    argv = BwrapBackend(executable="codex")._build_argv(invocation)

    assert _setenv(argv, CODEX_HOME_ENV) == str(seeded_home / ".codex"), (
        f"the sandbox launch must name the already-seeded CODEX_HOME; "
        f"the argv carried {_setenv(argv, CODEX_HOME_ENV)!r}"
    )
    # The worktree is still the child cwd: the repair changes where the home
    # points, never where the child works.
    assert _setenv(argv, "HOME") == str(seeded_home)
    chdir = [token for token in argv if token == "--chdir"]
    assert chdir == ["--chdir"]
    assert argv[argv.index("--chdir") + 1] == str(worktree.resolve())


def test_the_sandbox_mount_set_is_not_widened_for_the_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    seeded_home: Path,
) -> None:
    """FR-002's confinement half: the existing per-node home bind and the
    environment allowlist suffice — the runtime root that contains the home
    stays read-only, the home leaf stays writable, and no writable bind
    reaches anywhere else beneath the worker directory."""
    host = PlantedHost(tmp_path / "host")
    _plant_toolchain(host)
    codex_bin = tmp_path / "bin"
    install_as(codex_bin, "codex")
    host.activate(monkeypatch, host.bin_dir, codex_bin)

    worktree = tmp_path / "node-worktrees" / EPIC / NODE
    worktree.mkdir(parents=True)

    invocation = _invocation(
        worktree=worktree,
        codex_bin=codex_bin,
        search_dirs=(codex_bin, host.bin_dir),
        env_home=seeded_home,
    )
    argv = BwrapBackend(executable="codex")._build_argv(invocation)

    writable = _writable_binds(argv)
    worker_host = str(tmp_path / "worker-host")
    writable_in_worker = [
        (src, dst) for src, dst in writable if dst.startswith(worker_host)
    ]
    assert (str(seeded_home), str(seeded_home)) in writable_in_worker, (
        f"the per-node home leaf must stay the writable home inside the "
        f"runtime root; writable binds were {writable}"
    )
    # Nothing else under the worker directory is writable: no wider mount
    # appeared for the home's sake. (Writable binds outside the worker
    # directory are the declared package caches, as always.)
    assert writable_in_worker == [(str(seeded_home), str(seeded_home))], (
        f"a writable bind reached beyond the per-node home: {writable_in_worker}"
    )


def _writable_binds(argv: list[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for index, token in enumerate(argv):
        if token == "--bind":
            pairs.append((argv[index + 1], argv[index + 2]))
    return pairs


# --- execution where supported (FR-002) ------------------------------------------


@pytest.mark.skipif(
    not BWRAP_PRESENT,
    reason=(
        "bwrap not installed on this host — the sandbox execution half of "
        "US1-S2 is unavailable here and is skipped explicitly, not passed "
        "by a catch-all"
    ),
)
async def test_the_sandbox_launch_executes_a_credential_free_strict_child_in_the_seeded_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    seeded_home: Path,
) -> None:
    """US1-S2, execution: the real `BwrapBackend.launch` starts the strict
    child inside the boundary; the child reads the seeded configuration and
    writes its synthetic rollout into the per-node home through the existing
    bind, and its cwd is the worktree across the `--chdir`. The child carries
    no credential: the env is the allowlist plus the home's two names."""
    host = PlantedHost(tmp_path / "host")
    bin_dir = tmp_path / "bin"
    _plant_toolchain(host)
    install_as(bin_dir, "codex")
    # The strict child's interpreter is reachable through the binds the
    # boundary already makes: `/usr` is bound whole, and the launcher's
    # shebang (`/usr/bin/env python3`) resolves inside it. The launcher is
    # bound at its own path by `_bind_executable`.
    host.activate(monkeypatch, host.bin_dir, bin_dir)

    worktree = tmp_path / "node-worktrees" / EPIC / NODE
    worktree.mkdir(parents=True, exist_ok=True)
    invocation = _invocation(
        worktree=worktree,
        codex_bin=bin_dir,
        search_dirs=(bin_dir, host.bin_dir),
        env_home=seeded_home,
    )

    log_path = host.root / "stdout.log"
    with log_path.open("wb") as log:
        invocation = _invocation(
            worktree=worktree,
            codex_bin=bin_dir,
            search_dirs=(bin_dir, host.bin_dir),
            env_home=seeded_home,
            log=log,
        )
        process = await BwrapBackend(
            executable=str(bin_dir / "codex")
        ).launch(invocation)
        if process.stdin is not None:
            process.stdin.close()
        await asyncio.wait_for(process.wait(), LAUNCH_TIMEOUT_S)

    assert process.returncode == 0, (
        f"the sandboxed strict child failed (rc={process.returncode}); "
        f"log: {log_path.read_text(encoding='utf-8', errors='replace')}"
    )
    record = last_record(worktree)
    assert record["read"] == "config.toml", "the child read the seeded gateway configuration"
    assert record["codex_home"] == str(seeded_home / ".codex")
    assert record["cwd"] == str(worktree), "the worktree remains the child cwd"
    rollout = Path(str(record["rollout"]))
    assert rollout.is_file(), "the synthetic rollout was not written into the seeded home"
    assert rollout.is_relative_to(seeded_home), (
        f"the rollout landed outside the per-node home: {rollout}"
    )