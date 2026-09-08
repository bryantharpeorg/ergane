"""US4 of 155: the toolchain and image carry the Codex binary, confined.

"Presence" is the whole story (FR-008): `codex` resolves on the node's PATH,
the standing bwrap boundary carries it well enough to *start* it, the launch
disables Codex's own read-only default because the factory's boundary is the
confinement, and the bwrap-nesting question stays recorded as an OPEN hazard.
Nothing here hardens the mount set beyond what a launch requires (plan trap 6)
— the operator is weighing moving away from bwrap entirely.

Written before the implementation (constitution II). What these tests are
written to resist:

- **The leaf bind.** Every tool the boundaries carry today is bound as a single
  resolved leaf, which is correct for `claude` — a self-contained ELF — and
  broken for Codex: `@openai/codex` installs as an npm package whose
  `bin/codex` is a JS launcher that resolves its platform payload *beside
  itself* through the package tree (`realpathSync(__dirname/..)` and
  `require.resolve` up `node_modules`, measured on the real 0.153.4 tarball).
  A boundary that binds the lone launcher file leaves the launcher unable to
  find its payload: the exact "starts nothing, diffless" failure shape this
  repository's boundaries exist to refuse early. The tests plant an npm-global
  layout with a launcher that resolves its payload the same way and assert the
  boundary mounts the tree, not the leaf.

- **The image case silently breaking the argv.** In the demo container npm
  installs `codex` under `/usr`, which the system tree already ro-binds —
  emitting a `--symlink` for a path the bound tree already carries makes bwrap
  refuse to start (`Can't make symlink at /usr/bin/codex: existing
  destination`), the measured defect of test_gate_runner_inside_system_tree.
  The system-tree case must emit nothing.

- **A hazard answered by silence.** US4-S3: the nesting of Codex's
  Landlock/seccomp sandbox inside bwrap is UNANSWERED — tied to the operator's
  sandbox-boundary decision, neither assumed to work nor assumed to fail. The
  record is asserted over the committed source text, where a reader of the
  launch meets it.

Every launch-shaped test plants its own toolchain in `tmp_path` (constitution
II): no assertion here can be satisfied by the host the literals used to name.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from factory.verify.toolchain import (
    CODEX_RUNNER,
    CODEX_RUNNER_PACKAGE,
    CODEX_RUNNER_VERSION,
    ResolvedTool,
)
from factory.workgraph.adapter import (
    CODEX_BYPASS_FLAG,
    CODEX_SKIP_GIT_CHECK_FLAG,
    BwrapBackend,
)
from tests.test_toolchain_discovery import PlantedHost, _binds, _setenv

#: The npm distribution the image must pin, assembled from the toolchain
#: module's own constants so the Dockerfile and this test cannot disagree.
CODEX_NPM_SPEC = f"{CODEX_RUNNER_PACKAGE}@{CODEX_RUNNER_VERSION}"

REPO_ROOT = Path(__file__).resolve().parent.parent

BWRAP_PRESENT = shutil.which("bwrap") is not None

#: A triple that exists on no real host, so a test naming it cannot be
#: satisfied by a real Codex install that happens to sit on the machine.
FAKE_PLATFORM_PACKAGE = "@openai/codex-ergane-fake-platform"

#: Long enough that no test races its deadline; a real bwrap launch of a
#: script that only writes one file is sub-second.
LAUNCH_TIMEOUT_S = 60


# --- the planted npm layout ---------------------------------------------------


def _plant_npm_codex(prefix: Path) -> tuple[Path, Path]:
    """Install a Codex-shaped npm distribution under `prefix`, from tarballs.

    The layout is the npm-global one the real package installs (`npm i -g`
    measured 2026-09-06): the launcher at `<prefix>/bin/codex` as a symlink
    into `<prefix>/lib/node_modules/@openai/codex/bin/codex.js`, the payload
    under the package's own `vendor/`. The launcher is a shell script, not JS —
    what it must reproduce is the *resolution*, and the real launcher resolves
    its payload beside itself through the package root either way.
    """
    package = prefix / "lib" / "node_modules" / "@openai" / "codex"
    launcher_dir = package / "bin"
    launcher_dir.mkdir(parents=True)
    launcher = launcher_dir / "codex.js"
    launcher.write_text(
        "#!/bin/bash\n"
        "# Stands where `@openai/codex`'s `bin/codex.js` stands. Like the real\n"
        "# launcher, it resolves its payload beside itself through the package\n"
        "# root and refuses, by name, when the payload is not mounted with it —\n"
        "# which is what a boundary that binds a lone launcher leaf produces.\n"
        'self="$(readlink -f "$0")"\n'
        'root="$(dirname "$(dirname "$self")")"\n'
        'payload="$root/vendor/bin/payload"\n'
        'if [ ! -x "$payload" ]; then\n'
        '  echo "Missing optional dependency codex-platform-package." >&2\n'
        "  exit 3\n"
        "fi\n"
        'printf \'%s\\n\' "$@" > codex-launch-argv.txt\n'
        'exec "$payload" "$@"\n',
        encoding="utf-8",
    )
    launcher.chmod(0o755)

    payload_dir = package / "vendor" / "bin"
    payload_dir.mkdir(parents=True)
    payload = payload_dir / "payload"
    payload.write_text(
        "#!/bin/bash\n"
        "# The turn: write into the node's worktree — US4's own proof that the\n"
        "# node started at all.\n"
        "printf 'codex-node-ran\\n' > codex-ran-here.txt\n",
        encoding="utf-8",
    )
    payload.chmod(0o755)

    entry_bin = prefix / "bin"
    entry_bin.mkdir(parents=True, exist_ok=True)
    entry = entry_bin / "codex"
    entry.symlink_to(os.path.relpath(launcher, entry_bin))
    return package, entry


# --- US4-S1 / FR-008: the toolchain and the image -------------------------------


def test_the_toolchain_names_the_second_runner_and_its_pin() -> None:
    """FR-008: `codex` is a named runner of the toolchain, not a literal.

    The name lives beside `DEFAULT_AGENT_RUNNER` where the boundaries resolve
    runners from, and the npm distribution's pin lives there too — the
    Dockerfile cannot import this module, so the container drift test is what
    keeps the two in step. This assertion pins that seam: the constants exist,
    and the image installs exactly the distribution they name.
    """
    assert CODEX_RUNNER == "codex"
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert CODEX_NPM_SPEC in dockerfile, (
        f"the image must install the pinned {CODEX_NPM_SPEC} the toolchain "
        f"module names; the Dockerfile does not carry it"
    )


def test_the_agent_boundary_binds_the_codex_package_tree_not_a_lone_leaf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US4-S1: the boundary must carry what a Codex launch *resolves*.

    The launcher is a symlink into the package tree, and the npm launcher
    resolves its payload beside itself (`realpathSync(__dirname/..)` up
    through `node_modules`). Binding only the launcher file — the treatment
    every self-contained tool gets today — leaves the payload outside the
    namespace, and the first attempt dies as a diffless launch failure. The
    package tree must be mounted at its own path and the launcher recreated
    inside it at the PATH location.
    """
    host = PlantedHost(tmp_path)
    prefix = tmp_path / "npm-prefix"
    package, entry = _plant_npm_codex(prefix)
    for name in ("uv", "node", "git", "claude"):
        host.plant(name)
    host.activate(monkeypatch, host.bin_dir, entry.parent)

    argv = BwrapBackend(executable="codex")._build_argv(
        _codex_invocation(host, entry.parent)
    )
    pairs = _binds(argv)
    links = _symlinks(argv)

    node_modules = prefix / "lib" / "node_modules"
    assert ("--ro-bind", str(node_modules), str(node_modules)) in pairs, (
        f"the boundary must carry the npm package tree the launcher resolves "
        f"its payload through; binds were {pairs}"
    )
    launcher_real = package / "bin" / "codex.js"
    assert ("--symlink", str(launcher_real), str(entry)) in links, (
        f"the launcher must be recreated as the symlink PATH names, never "
        f"bound as a leaf that lost its ancestry; symlinks were {links}"
    )
    # And the leaf-bind of the launcher alone must be gone: it is the defect.
    assert ("--ro-bind", str(launcher_real), str(entry)) not in pairs, (
        "binding the launcher file at the link's path is the lone-leaf shape "
        "that leaves the payload unresolvable inside the namespace"
    )


def _symlinks(argv: list[str]) -> list[tuple[str, str]]:
    """Every `(target, link)` pair the assembled argv creates."""
    pairs: list[tuple[str, str]] = []
    for index, token in enumerate(argv):
        if token == "--symlink":
            pairs.append((argv[index + 1], argv[index + 2]))
    return pairs


def test_the_agent_boundary_emits_nothing_for_a_system_tree_codex() -> None:
    """The image's shape: npm installed codex under /usr, which the system
    tree bind already carries whole — launcher, payload, and the symlink.

    Emitting a `--symlink` for a path the bound `/usr` already carries makes
    bwrap refuse to start (`Can't make symlink at /usr/bin/codex: existing
    destination is ...`), the exact measured defect that killed the demo's
    story gates for claude. The system-tree runner is therefore the one case
    that gets no entry at all from the toolchain binds.
    """
    codex = ResolvedTool(
        name=CODEX_RUNNER,
        found_at=Path("/usr/bin/codex"),
        real_path=Path("/usr/lib/node_modules/@openai/codex/bin/codex.js"),
    )

    binds = BwrapBackend()._toolchain_binds(tools=[codex])

    assert binds == [], (
        f"a runner the system tree already provides must get no entry at all; "
        f"got {binds}"
    )


# --- US4-S2: the launch under the standing boundary -----------------------------


def _codex_invocation(host: PlantedHost, codex_bin: Path) -> Any:
    """A codex-shaped invocation, built only from planted paths."""
    from factory.workgraph.adapter import AgentInvocation

    home = host.root / "factory" / "homes" / "155-codex-runs-as-a-second-runner" / "us4"
    home.mkdir(parents=True, exist_ok=True)
    search = os.pathsep.join(str(host.bin_dir), str(codex_bin))
    return AgentInvocation(
        argv=[
            "codex",
            "exec",
            "--model",
            "ollama-cloud/glm-5.3-flash",
            CODEX_BYPASS_FLAG,
            CODEX_SKIP_GIT_CHECK_FLAG,
            "--cd",
            str(host.worktree),
            "-",
        ],
        prompt="write the marker",
        worktree=host.worktree,
        env={"PATH": search, "HOME": str(home)},
        log=None,
        standards_path=None,
        model_alias="ollama-cloud/glm-5.3-flash",
    )


@pytest.mark.skipif(not BWRAP_PRESENT, reason="bwrap not installed")
async def test_a_codex_node_launches_under_the_standing_boundary_and_writes_its_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US4-S1/S2: the standing boundary starts a Codex node, and the node
    writes its worktree — with Codex's own read-only default disabled.

    The launch is the real `BwrapBackend.launch`: real bwrap, the planted npm
    layout as `codex` on the container `PATH`, the launcher resolving its
    payload inside the namespace. The bypass flag must survive into the child
    (the factory's boundary is the confinement; a Codex CLI told to enforce
    its own sandbox inside it refuses every write the story needs), and the
    payload's write must land in the worktree.
    """
    host = PlantedHost(tmp_path)
    prefix = tmp_path / "npm-prefix"
    _package, entry = _plant_npm_codex(prefix)
    for name in ("uv", "node", "git", "claude"):
        host.plant(name)
    host.activate(monkeypatch, host.bin_dir, entry.parent)

    log_path = host.root / "stdout.log"
    invocation = _codex_invocation(host, entry.parent)
    with log_path.open("wb") as log:
        invocation.log = log
        process = await BwrapBackend(executable="codex").launch(invocation)
        if process.stdin is not None:
            process.stdin.close()
        await asyncio.wait_for(process.wait(), LAUNCH_TIMEOUT_S)

    assert process.returncode == 0, (
        f"the codex launch inside the boundary failed (rc={process.returncode}); "
        f"log: {log_path.read_text(encoding='utf-8', errors='replace')}"
    )
    marker = host.worktree / "codex-ran-here.txt"
    assert marker.is_file(), (
        "the Codex node started but never wrote its worktree"
    )
    assert marker.read_text(encoding="utf-8") == "codex-node-ran\n"
    argv_recorded = (
        host.worktree / "codex-launch-argv.txt"
    ).read_text(encoding="utf-8").splitlines()
    assert CODEX_BYPASS_FLAG in argv_recorded, (
        f"the standing launch must carry the bypass flag into the child; "
        f"argv was {argv_recorded}"
    )
    assert CODEX_SKIP_GIT_CHECK_FLAG in argv_recorded


# --- US4-S3: the nesting hazard stays open --------------------------------------


def test_the_bwrap_nesting_hazard_is_recorded_open_not_answered() -> None:
    """US4-S3: the nesting question is recorded as an UNANSWERED hazard tied
    to the operator's sandbox-boundary decision — in the committed source,
    where a reader of the bypass flag meets it.

    Asserted over the source text because that is where the record lives: the
    spec's wording (neither silently assumed to work nor silently assumed to
    fail) is a property of the comment above the flag the launch passes, not
    of any runtime behaviour this story could measure.
    """
    from factory.workgraph import adapter as adapter_module

    source = Path(adapter_module.__file__).read_text(encoding="utf-8")
    for fragment in (
        "UNANSWERED HAZARD",
        "Landlock/seccomp",
        "the operator's sandbox-boundary decision",
        "neither assumed to work nor assumed to fail",
    ):
        assert fragment in source, (
            f"the open-hazard record must name {fragment!r} beside the "
            f"bypass flag it qualifies"
        )


def _setenv_path(argv: list[str]) -> str | None:
    """The container `PATH`, for the assertion that codex is on it."""
    return _setenv(argv, "PATH")