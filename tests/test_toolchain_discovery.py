"""The sandboxes must find the toolchain, not declare it.

Both bubblewrap boundaries used to name absolute paths under one operator's home
carrying literal version numbers — `/home/admin/.local/share/claude/versions/
2.1.223`, `/home/admin/.nvm/versions/node/v22.22.2/bin/node` — and several were
bound with no existence check at all. Two failures follow, and both were real:

- a host whose `HOME` is not `/home/admin` cannot run an attempt or a gate, which
  is what stopped the second install;
- the version numbers rot. When this was written the runner's store held
  `2.1.222`, `2.1.223` and `2.1.224` while the adapter pinned the middle one, so
  the installer's next prune would have turned every dispatch into
  `bwrap: Can't find source path` — an `agent_error` with no diff, from a
  process that had already forked.

**Why every test here plants its own executables.** These tests run on the very
machine whose paths the literals named, so an assertion like "the bind list
contains `/home/admin/.local/bin/uv`" passes whether or not anything was fixed —
the defect pattern that has cost this repository more than any other. So each
test builds a toolchain in `tmp_path`, points `PATH` and `HOME` at it, and
asserts the sandbox bound *those* paths. No planted path can coincide with a
host path, so no test here can pass on a code path that ignores discovery.

The negative direction is asserted too, and separately: a tool that cannot be
found must refuse *by name*, before bwrap forks. The old comment above the
literal list promised exactly that ("a named refusal rather than silently
widening the mount set") and delivered bwrap's own mount error instead. Both
refusal tests replace the spawn with a detonator, so "before it forks" is
measured rather than assumed.

**Mutation ledger.** "What would make this pass if the production code did
nothing?" was answered by breaking the production code eight ways and running
this file against each. Verbatim failure lists:

    M1  the adapter's literal bind list and literal container PATH restored
        3 failed, 12 passed
          test_the_agent_sandbox_binds_the_discovered_toolchain
          test_the_agent_sandbox_mounts_no_toolchain_from_another_home
          test_the_agent_sandbox_follows_a_repointed_runner_symlink

    M2  the gate's literal bind list and literal container PATH restored
        4 failed, 11 passed
          test_the_installation_is_found_with_no_launcher_on_the_path
          test_the_gate_sandbox_binds_the_discovered_toolchain
          test_the_gate_reproduces_the_runners_layout_rather_than_flattening_it
          test_the_gates_optional_tools_still_degrade_quietly

    M3  require_tool guesses `~/.local/bin/<name>` instead of refusing
        3 failed, 12 passed
          test_a_missing_tool_is_absent_rather_than_guessed
          test_a_missing_runner_refuses_by_name_before_anything_forks
          test_a_gate_on_a_host_without_uv_refuses_by_name_before_it_forks
        — the gate case failed as `AssertionError: a gate forked despite an
          unresolvable toolchain`, which is the detonator doing its job.

    M4  nvm version directories sorted as text rather than numerically
        1 failed, 14 passed
          test_node_is_found_under_nvm_when_path_alone_does_not_have_it
        — picked v9.11.2 over v22.22.2, which is the whole reason for the two
          planted versions.

    M5  install_root returns the literal `/home/admin/.local/share/claude`
        2 failed, 13 passed
          test_install_root_is_read_from_the_layout_not_assumed
          test_the_gate_reproduces_the_runners_layout_rather_than_flattening_it

    M6  find_tool declares `~/.local/bin/<name>` and never consults PATH
        14 failed, 1 passed
        — the survivor is
          test_a_missing_runner_refuses_by_name_before_anything_forks, which
          still fires because the declared path does not resolve.

    M7  a symlinked tool binds the link at its own path, not its target
        2 failed, 13 passed
          test_a_symlinked_tool_binds_its_target_at_the_links_own_path
          test_the_agent_sandbox_follows_a_repointed_runner_symlink

    M8  find_install_root loses its no-launcher route
        1 failed, 14 passed
          test_the_installation_is_found_with_no_launcher_on_the_path
        — and, run outside this file, reproduces the nested failure that made
          the route necessary: the full-suite gate's
          test_a_gate_can_launch_the_agent_runner_inside_the_boundary goes red
          in 0.06s with `ls: cannot access
          '/home/admin/.local/share/claude/versions': No such file or directory`.

Every test in this file dies under at least one mutation — M1/M2 cover the two
sandboxes, M3 the refusals, M4 the version ordering, M5 the install layout, M6
discovery itself, M7 symlink resolution and M8 the launcher-independent route.
None of them can pass on a factory that only pretends to discover its toolchain.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

import pytest

from factory.verify import gates as gates_module
from factory.verify import toolchain as toolchain_module
from factory.verify.gates import BwrapGateExecutor, GateInvocation
from factory.verify.toolchain import (
    ToolchainError,
    container_path,
    find_install_root,
    find_tool,
    install_root,
    require_tool,
    resolve_toolchain,
)
from factory.workgraph import adapter as adapter_module
from factory.workgraph.adapter import AdapterError, AgentInvocation, BwrapBackend

#: A version string that exists on no real host, so a test using it cannot be
#: satisfied by the operator's actual agent-runner install.
FAKE_RUNNER_VERSION = "97.3.1"


def _plant(directory: Path, name: str) -> Path:
    """Create an executable at `directory/name` and return its path."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


class PlantedHost:
    """A toolchain that exists only inside one test's `tmp_path`."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.bin_dir = root / "toolchain"
        self.home = root / "home"
        self.home.mkdir(parents=True, exist_ok=True)
        self.worktree = root / "worktree"
        self.worktree.mkdir(parents=True, exist_ok=True)

    def plant(self, name: str, *, directory: Path | None = None) -> Path:
        return _plant(directory or self.bin_dir, name)

    def plant_versioned_runner(self, version: str) -> tuple[Path, Path]:
        """Install a runner the way the real one installs: versions + a symlink.

        Returns `(install_root, symlink_on_path)`. The symlink is what `PATH`
        finds; the version file underneath is what a bind mount must take as
        its source, or the link dangles inside the namespace.
        """
        install = self.home / ".local" / "share" / "claude"
        versions = install / "versions"
        binary = _plant(versions, version)
        link_dir = self.home / ".local" / "bin"
        link_dir.mkdir(parents=True, exist_ok=True)
        link = link_dir / "claude"
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(binary)
        return install, link

    def activate(self, monkeypatch: pytest.MonkeyPatch, *dirs: Path) -> None:
        """Make this the only toolchain discovery can see."""
        search = list(dirs) or [self.bin_dir]
        monkeypatch.setenv("PATH", os.pathsep.join(str(entry) for entry in search))
        monkeypatch.setenv("HOME", str(self.home))


@pytest.fixture
def planted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PlantedHost:
    """A complete planted toolchain, on `PATH`, with a `HOME` of its own."""
    host = PlantedHost(tmp_path)
    for name in ("uv", "node", "git", "claude"):
        host.plant(name)
    host.activate(monkeypatch)
    return host


def _agent_invocation(host: PlantedHost, executable: str = "claude") -> AgentInvocation:
    return AgentInvocation(
        argv=[executable, "-p"],
        prompt="implement the story",
        worktree=host.worktree,
        env={"PATH": os.environ["PATH"], "HOME": str(host.home)},
        log=None,
        standards_path=None,
        model_alias="anthropic/CHANGEME",
    )


def _binds(argv: list[str]) -> list[tuple[str, str]]:
    """Every `(source, destination)` pair the assembled argv mounts."""
    pairs: list[tuple[str, str]] = []
    for index, token in enumerate(argv):
        if token in ("--ro-bind", "--bind"):
            pairs.append((argv[index + 1], argv[index + 2]))
    return pairs


def _symlinks(argv: list[str]) -> list[tuple[str, str]]:
    """Every `(target, link)` pair the assembled argv creates inside the namespace."""
    pairs: list[tuple[str, str]] = []
    for index, token in enumerate(argv):
        if token == "--symlink":
            pairs.append((argv[index + 1], argv[index + 2]))
    return pairs


def _setenv(argv: list[str], name: str) -> str | None:
    for index, token in enumerate(argv):
        if token == "--setenv" and argv[index + 1] == name:
            return argv[index + 2]
    return None


# --- discovery itself --------------------------------------------------------


def test_discovery_returns_the_planted_tools_not_the_hosts(planted: PlantedHost) -> None:
    """`find_tool` resolves from the environment, so a fake `PATH` wins.

    The whole fix rests on this: what the sandbox binds is whatever discovery
    returned. Planting the four somewhere no host would keep them is what makes
    the assertion mean something on the machine the old literals described.
    """
    for name in ("uv", "node", "git", "claude"):
        tool = find_tool(name)
        assert tool is not None, f"{name} was planted on PATH and must be found"
        assert tool.found_at == planted.bin_dir / name, (
            f"{name} resolved to {tool.found_at}, not the planted "
            f"{planted.bin_dir / name} — discovery is not reading PATH"
        )


def test_a_symlinked_tool_binds_its_target_at_the_links_own_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The runner is a symlink; source and destination must therefore differ.

    Binding the link at its own path would leave it dangling inside the
    namespace, and binding the target at the target's path would leave the
    container's `PATH` pointing at nothing.
    """
    host = PlantedHost(tmp_path)
    install, link = host.plant_versioned_runner(FAKE_RUNNER_VERSION)
    host.activate(monkeypatch, link.parent)

    tool = find_tool("claude")

    assert tool is not None
    assert tool.bind == (
        str(install / "versions" / FAKE_RUNNER_VERSION),
        str(link),
    ), f"the runner must bind its resolved target at the link's path: {tool.bind}"


def test_node_is_found_under_nvm_when_path_alone_does_not_have_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The worker's `PATH` has no node at all, and dispatch must still work.

    The factory worker runs as a systemd user unit whose `PATH` is
    `/home/admin/.local/bin:/home/admin/.temporalio/bin:/usr/local/bin:/usr/bin:
    /bin` — nvm's per-version directory is prepended by an interactive shell's
    `nvm use` and by nothing else. A discovery that consulted `PATH` alone
    would refuse every dispatch on the host it was written to keep working.

    The two planted versions are `v9.11.2` and `v22.22.2` on purpose: sorted as
    text the nine wins, so this also pins that the newest is chosen
    numerically. Neither version exists on the host.
    """
    host = PlantedHost(tmp_path)
    host.plant("uv")
    for version in ("v9.11.2", "v22.22.2"):
        _plant(host.home / ".nvm" / "versions" / "node" / version / "bin", "node")
    host.activate(monkeypatch)

    tool = find_tool("node")

    assert tool is not None, "node must be discoverable under nvm without PATH help"
    assert tool.found_at == (
        host.home / ".nvm" / "versions" / "node" / "v22.22.2" / "bin" / "node"
    ), f"nvm versions must be ordered numerically, newest first; got {tool.found_at}"


def test_a_missing_tool_is_absent_rather_than_guessed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing falls back to a path that was never found."""
    host = PlantedHost(tmp_path)
    host.activate(monkeypatch)
    monkeypatch.setattr(
        toolchain_module, "_SYSTEM_FALLBACK_DIRS", (str(tmp_path / "empty"),)
    )

    assert find_tool("uv") is None
    with pytest.raises(ToolchainError) as excinfo:
        require_tool("uv", purpose="the gate boundary")
    assert "'uv'" in str(excinfo.value)


def test_the_container_path_is_derived_from_what_was_resolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`PATH` inside the namespace names bind points, in resolution order.

    node is planted in a *second* directory so the derived string has to carry
    two distinct planted directories in the right order. No literal can produce
    that, which is the point.
    """
    host = PlantedHost(tmp_path)
    for name in ("uv", "git", "claude"):
        host.plant(name)
    node_dir = tmp_path / "node-elsewhere" / "bin"
    _plant(node_dir, "node")
    host.activate(monkeypatch, host.bin_dir, node_dir)

    tools = resolve_toolchain(("claude", "uv", "node", "git"), purpose="a test")

    assert container_path(tools) == f"{host.bin_dir}:{node_dir}:/usr/bin", (
        f"the container PATH must be derived, got {container_path(tools)}"
    )


def test_install_root_is_read_from_the_layout_not_assumed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A versioned runner yields its install directory; a plain one yields itself.

    The gate boundary binds the whole install directory because a gate may
    launch an inner agent that resolves a *different* version than the outer
    launch did — the installer prunes and repoints on its own schedule. That is
    only safe if the directory is derived from the layout that is really there,
    so a runner installed as a bare binary widens nothing.
    """
    host = PlantedHost(tmp_path)
    install, link = host.plant_versioned_runner(FAKE_RUNNER_VERSION)
    host.activate(monkeypatch, link.parent)
    assert install_root(find_tool("claude")) == install

    plain = PlantedHost(tmp_path / "plain")
    binary = plain.plant("claude")
    plain.activate(monkeypatch, plain.bin_dir)
    assert install_root(find_tool("claude")) == binary, (
        "a runner that is just a binary must not widen to its parent directory"
    )


def test_the_installation_is_found_with_no_launcher_on_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The payload is reachable even when nothing links it onto `PATH`.

    Reading the installation off the launcher's resolution is the obvious
    route and it is not sufficient, because the two are absent independently.
    The case that proved it: inside a gate boundary built by a factory that
    predates this module, `~/.local/share/claude` is mounted and
    `~/.local/bin/claude` is not — the old code bound the payload by literal and
    never needed a launcher to find it. Discovery that could only arrive
    *through* `PATH` therefore found nothing where the literal found the
    directory, and the gate one level in failed with

        ls: cannot access '/home/admin/.local/share/claude/versions':
        No such file or directory

    So `<prefix>/share/<name>` is checked for every `<prefix>/bin` on the search
    path — the layout the installer really uses, and the reason the candidate
    has to sit beside a directory actually named `bin` rather than beside any
    directory at all. Here the launcher is deliberately never planted, and the
    install directory sits beside a `bin` that is, in a `tmp_path` that cannot
    be the operator's.
    """
    host = PlantedHost(tmp_path)
    prefix = tmp_path / "prefix"
    bin_dir = prefix / "bin"
    for name in ("uv", "node", "git"):
        host.plant(name, directory=bin_dir)
    install = prefix / "share" / "claude"
    _plant(install / "versions", FAKE_RUNNER_VERSION)
    host.activate(monkeypatch, bin_dir)

    assert find_tool("claude") is None, (
        "the launcher must be absent for this test to be about anything"
    )
    assert find_install_root("claude") == install, (
        f"the installation beside a searched bin directory must be found: "
        f"{find_install_root('claude')}"
    )

    binds = _binds(
        BwrapGateExecutor()._build_argv(
            GateInvocation(
                name="test", command="true", cwd=host.worktree, timeout_s=30, env={}
            )
        )
    )

    assert (str(install), str(install)) in binds, (
        f"the gate must bind the installation it discovered: {binds}"
    )
    for source, destination in binds:
        assert not source.startswith("/home/admin"), (
            f"the gate reached for the operator's own installation at {source} "
            f"instead of the one discovery found"
        )


# --- the agent sandbox -------------------------------------------------------


def test_the_agent_sandbox_binds_the_discovered_toolchain(planted: PlantedHost) -> None:
    """Every toolchain bind in the agent boundary names a planted path.

    Reverting `BwrapBackend._toolchain_binds` to its literal list fails this on
    the first assertion: the planted `uv` is not in the argv at all.
    """
    argv = BwrapBackend()._build_argv(_agent_invocation(planted))
    binds = _binds(argv)

    for name in ("uv", "node", "git", "claude"):
        expected = (str(planted.bin_dir / name), str(planted.bin_dir / name))
        assert expected in binds, (
            f"the agent boundary must bind the discovered {name} at "
            f"{expected[0]}; binds were {binds}"
        )


def test_the_agent_sandbox_mounts_no_toolchain_from_another_home(
    planted: PlantedHost,
) -> None:
    """No path under an unrelated home reaches the mount set or the `PATH`.

    The complement of the test above, and the one that would still be red if
    discovery were added *beside* the literals rather than in place of them.
    Only the two directories the boundary is entitled to — the planted
    toolchain and the system tree — may appear.
    """
    argv = BwrapBackend()._build_argv(_agent_invocation(planted))
    allowed = (str(planted.root), "/usr", "/etc", "/proc", "/dev", "/tmp", "/bin", "/lib")

    for source, destination in _binds(argv):
        for path in (source, destination):
            assert path.startswith(allowed), (
                f"the boundary mounted {path}, which no discovery on this "
                f"planted host could have returned"
            )

    assert _setenv(argv, "PATH") == f"{planted.bin_dir}:/usr/bin", (
        f"the container PATH must name only discovered directories: "
        f"{_setenv(argv, 'PATH')}"
    )


def test_the_agent_sandbox_follows_a_repointed_runner_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The version pin cannot rot, because there is no version pin.

    This is the failure that was one prune away on the operator's own machine:
    the runner's store held three versions and the adapter named the middle
    one. Here the symlink is repointed between two launches with no code change
    in between, and the bind must follow it.
    """
    host = PlantedHost(tmp_path)
    for name in ("uv", "node", "git"):
        host.plant(name)
    _, link = host.plant_versioned_runner("1.0.0")
    host.activate(monkeypatch, host.bin_dir, link.parent)
    versions = host.home / ".local" / "share" / "claude" / "versions"

    first = _binds(BwrapBackend()._build_argv(_agent_invocation(host)))
    assert (str(versions / "1.0.0"), str(link)) in first, first

    _plant(versions, "2.0.0")
    link.unlink()
    link.symlink_to(versions / "2.0.0")

    second = _binds(BwrapBackend()._build_argv(_agent_invocation(host)))
    assert (str(versions / "2.0.0"), str(link)) in second, (
        f"the bind must follow the installer's repointed symlink: {second}"
    )
    assert (str(versions / "1.0.0"), str(link)) not in second, (
        "the superseded version must not still be bound"
    )


@pytest.mark.asyncio
async def test_a_missing_runner_refuses_by_name_before_anything_forks(
    planted: PlantedHost, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal the old comment promised and never delivered.

    What the operator got instead was bwrap's own
    `bwrap: Can't find source path ...`, written by a process that had already
    forked and surfacing as a diffless `agent_error`. The spawn is replaced by a
    detonator so "before anything forks" is asserted rather than assumed: if the
    argv were still assembled from literals, `_build_argv` would succeed and the
    detonator would fire.

    `bwrap` itself is redirected at a planted file so the refusal under test is
    the toolchain's and not the backend binary's, on any host.
    """
    monkeypatch.setattr(
        adapter_module, "BWRAP_BACKEND_BINARY", planted.bin_dir / "uv"
    )

    async def _detonate(*args: object, **kwargs: object) -> None:
        raise AssertionError("a process was spawned despite an unresolvable toolchain")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _detonate)

    missing = "ergane-runner-that-is-not-installed"
    backend = BwrapBackend(executable=missing)

    with pytest.raises(AdapterError) as excinfo:
        await backend.launch(_agent_invocation(planted, executable=missing))

    message = str(excinfo.value)
    assert missing in message, f"the refusal must name the tool: {message}"
    assert "not found" in message, f"the refusal must say what went wrong: {message}"


# --- the gate sandbox --------------------------------------------------------


def test_the_gate_sandbox_binds_the_discovered_toolchain(planted: PlantedHost) -> None:
    """The gate boundary has the same disease and must not be fixed alone."""
    invocation = GateInvocation(
        name="test", command="true", cwd=planted.worktree, timeout_s=30, env={}
    )

    argv = BwrapGateExecutor()._build_argv(invocation)
    binds = _binds(argv)

    for name in ("uv", "node", "git"):
        expected = (str(planted.bin_dir / name), str(planted.bin_dir / name))
        assert expected in binds, (
            f"the gate boundary must bind the discovered {name}; binds were {binds}"
        )
    assert _setenv(argv, "PATH") == f"{planted.bin_dir}:/usr/bin", (
        f"the gate's container PATH must be derived: {_setenv(argv, 'PATH')}"
    )


def test_the_gate_reproduces_the_runners_layout_rather_than_flattening_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A gate that launches an inner agent needs the whole install, discovered.

    This repository's own suite exercises its dispatch path inside a gate, and
    the inner launch resolves the runner for itself — possibly a different
    version, because the installer can prune between the two. So the gate binds
    the install directory, discovered rather than named: a version literal here
    rotted into `bwrap: Can't find source path .../versions/2.1.223` once
    already.

    The runner's `PATH` entry is recreated as a *symlink* and not bound, which
    is the half that only a nested run reveals. Binding it would put a regular
    file at `~/.local/bin/claude` inside the namespace, with its
    `<install>/versions/<version>` ancestry erased — and the next boundary in
    would resolve that file to itself and bind a lone binary where the install
    directory belongs. That is not theory: it is what the full suite did when
    run inside its own gate, failing with

        ls: cannot access '/home/admin/.local/share/claude/versions':
        No such file or directory

    The symlink keeps the layout intact, so discovery gives the same answer at
    every depth.
    """
    host = PlantedHost(tmp_path)
    for name in ("uv", "node", "git"):
        host.plant(name)
    install, link = host.plant_versioned_runner(FAKE_RUNNER_VERSION)
    host.activate(monkeypatch, host.bin_dir, link.parent)

    argv = BwrapGateExecutor()._build_argv(
        GateInvocation(
            name="test", command="true", cwd=host.worktree, timeout_s=30, env={}
        )
    )
    version_file = install / "versions" / FAKE_RUNNER_VERSION

    assert (str(install), str(install)) in _binds(argv), (
        f"the whole discovered install directory must be bound: {_binds(argv)}"
    )
    assert (str(version_file), str(link)) in _symlinks(argv), (
        f"the runner's PATH entry must be recreated as a symlink: {_symlinks(argv)}"
    )
    assert (str(version_file), str(link)) not in _binds(argv), (
        "binding the runner over its own PATH entry flattens the layout the "
        "next boundary in has to read"
    )


def test_the_gates_optional_tools_still_degrade_quietly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """node and the runner were guarded before discovery, and stay guarded.

    A repository whose gates need neither still has gates that run, so absence
    is not a refusal here — unlike the agent boundary, where all four were
    bound unguarded and a miss already meant no launch.
    """
    host = PlantedHost(tmp_path)
    host.plant("uv")
    host.plant("git")
    host.activate(monkeypatch)
    monkeypatch.setattr(
        toolchain_module, "_SYSTEM_FALLBACK_DIRS", (str(tmp_path / "empty"),)
    )

    binds = BwrapGateExecutor()._toolchain_binds()

    assert binds == [
        ("--ro-bind", str(host.bin_dir / "uv"), str(host.bin_dir / "uv")),
        ("--ro-bind", str(host.bin_dir / "git"), str(host.bin_dir / "git")),
    ], f"absent optional tools must be skipped, not invented: {binds}"


def test_a_gate_on_a_host_without_uv_refuses_by_name_before_it_forks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate's refusal, in the shape the gate runner already understands.

    Exit 127 carrying the reason, like the missing-bwrap refusal beside it —
    not an exception the gate runner has nowhere to put. `Popen` is replaced by
    a detonator so the "before it forks" half is asserted: code still assembling
    a literal argv would reach it.

    The system fallback directories are redirected at an empty one so the case
    under test is "a host without uv" everywhere, rather than only on a host
    whose `/usr/bin` happens not to have it.
    """
    host = PlantedHost(tmp_path)
    host.plant("git")
    host.activate(monkeypatch)
    monkeypatch.setattr(
        toolchain_module, "_SYSTEM_FALLBACK_DIRS", (str(tmp_path / "empty"),)
    )
    monkeypatch.setattr(gates_module, "BWRAP_BACKEND_BINARY", host.bin_dir / "git")

    def _detonate(*args: object, **kwargs: object) -> None:
        raise AssertionError("a gate forked despite an unresolvable toolchain")

    monkeypatch.setattr(subprocess, "Popen", _detonate)

    outcome = BwrapGateExecutor().run(
        GateInvocation(
            name="test", command="true", cwd=host.worktree, timeout_s=30, env={}
        )
    )

    assert outcome.exit_code == 127, f"a refusal is a 127, got {outcome.exit_code}"
    assert "'uv'" in outcome.output, f"the refusal must name the tool: {outcome.output}"
    assert not outcome.timed_out


# --- the sandbox environment is built, not inherited -------------------------


def test_the_agent_sandbox_clears_the_inherited_environment(
    planted: PlantedHost, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sandbox must start from an empty environment, not the worker's.

    `attempt_env` builds an allowlist so a credential is absent by omission, and
    the host backend applies it by passing `env=`. The bwrap backend does not:
    it launches without `env=`, and bwrap forwards its own environment unless
    told otherwise, so the allowlist decided nothing about what the child could
    read. Measured 2026-08-17 on a live implementer node — its `pytest` child
    held `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`, and `tests/test_live_notify.py`
    (which skips only when those are absent) sent a real escalation to the
    operator's chat on every suite run the agent performed.

    Reverting the `--clearenv` fails this test.
    """
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1234567:must-never-reach-an-agent")
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-master-must-never-reach-an-agent")

    argv = BwrapBackend()._build_argv(_agent_invocation(planted))

    assert "--clearenv" in argv, (
        "the agent sandbox inherits the worker's environment: bwrap forwards its "
        f"own env unless --clearenv is passed, and it is absent from {argv}"
    )

    # Order is load-bearing: bwrap keeps what --setenv sets *after* the clear,
    # and drops everything before it. A --clearenv trailing the --setenv flags
    # would erase HOME and PATH and break every attempt.
    cleared_at = argv.index("--clearenv")
    set_positions = [i for i, token in enumerate(argv) if token == "--setenv"]
    assert set_positions, "the sandbox sets no environment at all"
    assert cleared_at < min(set_positions), (
        f"--clearenv at {cleared_at} must precede every --setenv {set_positions}, "
        "or the values the agent needs are cleared along with the ones it must not see"
    )

    # Nothing the allowlist excludes may be handed over explicitly either.
    set_names = {argv[i + 1] for i in set_positions}
    assert "TELEGRAM_BOT_TOKEN" not in set_names
    assert "LITELLM_MASTER_KEY" not in set_names
