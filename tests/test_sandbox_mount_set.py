"""The sandbox's system tree must be read off the host, not declared.

Both bubblewrap boundaries — the agent's in `factory.workgraph.adapter` and the
gate's in `factory.verify.gates` — opened their argv with the same four literal
tokens and the same comment above them:

    # Minimal system tree: read-only /usr plus the symlinks Ubuntu uses
    # on aarch64. No /lib64 on this host.
    "--ro-bind", "/usr", "/usr",
    "--symlink", "usr/bin", "/bin",
    "--symlink", "usr/lib", "/lib",

Every word of that comment is a fact about one machine on one afternoon, and
the code under it was the same fact compiled in. On any host that *does* have
`/lib64` — which is every x86_64 Linux — a process inside the namespace finds
no dynamic loader at the path its own binaries name, and the agent cannot
start. The comment is the defect's documentation, which is why this story
deletes it rather than correcting it.

**Why every test here supplies its own root.** This machine is aarch64 and has
no `/lib64` at all (measured 2026-08-20: `/bin -> usr/bin`, `/lib -> usr/lib`,
`/sbin -> usr/sbin`, no `/lib64`). A test asserting the argv carries `/lib64`
fails here; a test asserting it does not would fail on the machine the defect
was reported from. Either one is a test of the machine it runs on rather than
of the code — which is exactly how the literal shipped. So every test below
hands the derivation a **fake root** built in `tmp_path` and asserts the argv
*followed what it was given*. Both branches are then exercised on any
architecture, including one that cannot reproduce the bug, which makes these
assertions stronger than a real-root test could be rather than a substitute
for one.

**The expected new entry on this host.** Walking all four paths adds
`--symlink usr/sbin /sbin` to every sandbox here, because `/sbin` is a symlink
the two-entry literal never mounted. That is a second latent gap closed, not a
regression; a reviewer diffing the assembled argv before and after on this
machine sees it and should. Measured with the real root, agent boundary:

    $ python -c "from factory.verify.toolchain import system_tree_argv; \
                 print(system_tree_argv())"
    ['--ro-bind', '/usr', '/usr', '--symlink', 'usr/bin', '/bin',
     '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/sbin', '/sbin']

**Mutation ledger.** "What would make this file pass if the production code
did nothing?" — answered by breaking the production code four ways and running
this file against each. Verbatim:

    M1  the literal system tree restored in both boundaries
        (`--ro-bind /usr /usr`, `--symlink usr/bin /bin`, `--symlink usr/lib /lib`)
        6 failed, 2 passed
          test_a_host_with_lib64_gets_a_lib64_symlink_with_its_own_target
          test_the_four_paths_are_each_read_rather_than_assumed
          test_both_boundaries_derive_the_same_system_tree
          test_a_system_path_that_can_be_neither_linked_nor_bound_refuses
          test_the_gate_refuses_a_broken_system_tree_before_it_forks
          test_the_agent_refuses_a_broken_system_tree_before_it_forks
        — only the two negative tests survive, which is the point of M2.

    M2  the four paths hardcoded as symlinks whenever `/usr` exists
        (the over-correction: emit all four unconditionally)
        3 failed, 5 passed
          test_a_host_without_lib64_gets_no_lib64_entry
          test_the_four_paths_are_each_read_rather_than_assumed
          test_both_boundaries_derive_the_same_system_tree
        — `bwrap: Can't find source path` is what this mutation ships.

    M3  the refusal dropped: a regular file at a mirrored path is skipped
        3 failed, 5 passed
          test_a_system_path_that_can_be_neither_linked_nor_bound_refuses
          test_the_gate_refuses_a_broken_system_tree_before_it_forks
          test_the_agent_refuses_a_broken_system_tree_before_it_forks

    M4  the gate boundary given its own private copy of the derivation
        (one entry dropped from the copy — how the two drifted the first time)
        1 failed, 7 passed
          test_both_boundaries_derive_the_same_system_tree

The three refusal tests are the ones that would otherwise be theatre: two of
them replace the spawn with a detonator, so "before any subprocess is created"
is measured rather than asserted.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

import pytest

from factory.verify import gates as gates_module
from factory.verify.gates import BwrapGateExecutor, GateInvocation
from factory.verify.toolchain import SystemTreeError, ToolchainError, system_tree_argv
from factory.workgraph import adapter as adapter_module
from factory.workgraph.adapter import AdapterError, AgentInvocation, BwrapBackend
from tests.test_toolchain_discovery import PlantedHost

#: The paths a sandbox mirrors from the host, and the one it binds. Named here
#: so a test can say "no entry for `/lib64`" without knowing where in the argv
#: an entry would sit.
SYSTEM_TREE_PATHS = ("/usr", "/bin", "/lib", "/lib64", "/sbin")

#: What a supplied layout can put at one of the four mirrored paths, besides a
#: symlink (which is written as its target string) or nothing at all.
A_DIRECTORY = object()
A_FILE = object()


def _fake_root(tmp_path: Path, name: str, layout: dict[str, object], *, usr: object = A_DIRECTORY) -> Path:
    """A host's system layout, supplied rather than read from the real root.

    `layout` maps a mirrored path (`/bin`, `/lib`, `/lib64`, `/sbin`) to what
    this host has there: a `str` means a symlink with that exact target,
    `A_DIRECTORY` a real directory, `A_FILE` a regular file. A path the mapping
    omits is not there at all — the aarch64 `/lib64` case, and the one an
    over-correcting fix breaks.
    """
    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    if usr is A_DIRECTORY:
        for child in ("bin", "lib", "lib64", "sbin"):
            (root / "usr" / child).mkdir(parents=True, exist_ok=True)
    elif usr is A_FILE:
        (root / "usr").write_text("not a directory\n", encoding="utf-8")
    for path, kind in layout.items():
        planted = root / path.lstrip("/")
        if kind is A_DIRECTORY:
            planted.mkdir(parents=True, exist_ok=True)
        elif kind is A_FILE:
            planted.write_text("not a directory\n", encoding="utf-8")
        else:
            planted.symlink_to(str(kind))
    return root


def _system_tree(argv: list[str]) -> list[tuple[str, str, str]]:
    """Every `(flag, source, destination)` the argv devotes to the system tree.

    Read out of the *assembled* argv by destination rather than by position, so
    the assertion is about what the sandbox mounts and not about where in the
    command line it happens to say so.
    """
    entries: list[tuple[str, str, str]] = []
    for index, token in enumerate(argv[:-2]):
        if token in ("--symlink", "--ro-bind", "--bind") and argv[index + 2] in SYSTEM_TREE_PATHS:
            entries.append((token, argv[index + 1], argv[index + 2]))
    return entries


def _agent_argv(host: PlantedHost, root: Path) -> list[str]:
    """The agent boundary's real argv, built against a supplied system root."""
    return BwrapBackend(system_root=root)._build_argv(
        AgentInvocation(
            argv=["claude", "-p"],
            prompt="implement the story",
            worktree=host.worktree,
            env={"PATH": os.environ["PATH"], "HOME": str(host.home)},
            log=None,
            standards_path=None,
            model_alias="anthropic/CHANGEME",
        )
    )


def _gate_argv(host: PlantedHost, root: Path) -> list[str]:
    """The gate boundary's real argv, built against the same supplied root."""
    return BwrapGateExecutor(system_root=root)._build_argv(
        GateInvocation(
            name="test", command="true", cwd=host.worktree, timeout_s=30, env={}
        )
    )


@pytest.fixture
def planted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PlantedHost:
    """A toolchain of this test's own, so argv assembly gets that far.

    The system tree is what this file is about; the toolchain binds beside it
    still have to resolve for `_build_argv` to return, and planting them keeps
    the test independent of what the operator happens to have installed.
    """
    host = PlantedHost(tmp_path)
    for name in ("uv", "node", "git", "claude"):
        host.plant(name)
    host.activate(monkeypatch)
    return host


# --- the four paths, read off the supplied host ------------------------------


def test_a_host_with_lib64_gets_a_lib64_symlink_with_its_own_target(
    tmp_path: Path, planted: PlantedHost
) -> None:
    """US1-S1. The x86_64 layout, which this machine cannot supply for itself.

    The target asserted is the one the fake root actually holds, so a fix that
    emitted a plausible `usr/lib64` constant rather than reading the link would
    still fail here.
    """
    root = _fake_root(
        tmp_path,
        "x86_64-host",
        {"/bin": "usr/bin", "/lib": "usr/lib", "/lib64": "usr/lib64", "/sbin": "usr/sbin"},
    )

    entries = _system_tree(_agent_argv(planted, root))

    assert ("--symlink", "usr/lib64", "/lib64") in entries, (
        f"a host whose /lib64 is a symlink must get that symlink, with its own "
        f"target: {entries}"
    )
    assert ("--ro-bind", str(root / "usr"), "/usr") in entries, (
        f"/usr must still be bound read-only from the supplied host: {entries}"
    )


def test_a_host_without_lib64_gets_no_lib64_entry(
    tmp_path: Path, planted: PlantedHost
) -> None:
    """US1-S2. The over-correction guard, and the layout this machine has.

    Widening the literal to name all four would bind a path that is not there,
    which is `bwrap: Can't find source path` from a process that has already
    forked — the same failure class, pointing the other way.
    """
    root = _fake_root(
        tmp_path,
        "aarch64-host",
        {"/bin": "usr/bin", "/lib": "usr/lib", "/sbin": "usr/sbin"},
    )

    argv = _agent_argv(planted, root)

    assert not [entry for entry in _system_tree(argv) if entry[2] == "/lib64"], (
        f"a host without /lib64 must get no /lib64 entry: {_system_tree(argv)}"
    )
    assert "/lib64" not in argv, (
        "no token anywhere in the argv may name /lib64 on a host that lacks it"
    )


def test_the_four_paths_are_each_read_rather_than_assumed(
    tmp_path: Path, planted: PlantedHost
) -> None:
    """US1-S3. All four differ in kind, so no fixed set can satisfy this.

    `/bin` is a symlink to an unusual target, `/lib` to a different one,
    `/lib64` is absent and `/sbin` is a real directory. A derivation treating
    the four alike — in either direction — gets a different list than this.
    """
    root = _fake_root(
        tmp_path,
        "mixed-host",
        {
            "/bin": "usr/altbin",
            "/lib": "usr/lib/aarch64-linux-gnu",
            "/sbin": A_DIRECTORY,
        },
    )

    entries = _system_tree(_agent_argv(planted, root))
    mirrored = [entry for entry in entries if entry[2] != "/usr"]

    assert mirrored == [
        ("--symlink", "usr/altbin", "/bin"),
        ("--symlink", "usr/lib/aarch64-linux-gnu", "/lib"),
    ], (
        f"each of /bin, /lib, /lib64, /sbin must be emitted if and only if the "
        f"supplied host has it as a symlink, with that link's own target: {mirrored}"
    )


def test_both_boundaries_derive_the_same_system_tree(
    tmp_path: Path, planted: PlantedHost
) -> None:
    """US1-S4, FR-003. Two copies is how they came to be wrong the same way.

    The assertion is on the *assembled* argvs, not on the shared helper: a
    boundary that called the helper and then appended a literal of its own
    would pass a test of the helper alone.
    """
    root = _fake_root(
        tmp_path,
        "shared-host",
        {"/bin": "usr/bin", "/lib64": "usr/lib64", "/sbin": "usr/sbin"},
    )

    agent = _system_tree(_agent_argv(planted, root))
    gate = _system_tree(_gate_argv(planted, root))

    assert agent == gate, (
        f"the agent and gate boundaries must derive one system tree, not two: "
        f"agent={agent} gate={gate}"
    )
    assert agent == [
        ("--ro-bind", str(root / "usr"), "/usr"),
        ("--symlink", "usr/bin", "/bin"),
        ("--symlink", "usr/lib64", "/lib64"),
        ("--symlink", "usr/sbin", "/sbin"),
    ], f"and it must be the supplied host's tree, in mount order: {agent}"


# --- refusal, by name, before anything forks ---------------------------------


def test_a_system_path_that_can_be_neither_linked_nor_bound_refuses(
    tmp_path: Path,
) -> None:
    """US1-S6, FR-004. The derivation called directly, so nothing can fork.

    A regular file at `/sbin` is neither a symlink to mirror nor a directory to
    bind. bwrap's own diagnostic for that arrives after the fork, as a diffless
    `agent_error`; `ToolchainError`'s precedent is a refusal that names the
    path and what was found there while the argv is still being assembled.
    """
    root = _fake_root(tmp_path, "file-at-sbin", {"/bin": "usr/bin", "/sbin": A_FILE})

    with pytest.raises(SystemTreeError) as raised:
        system_tree_argv(root)

    message = str(raised.value)
    assert "/sbin" in message, f"the refusal must name the path: {message}"
    assert "regular file" in message, (
        f"the refusal must say what was found there: {message}"
    )
    assert isinstance(raised.value, ToolchainError), (
        "the refusal must be catchable where a toolchain refusal already is"
    )


def test_a_host_with_no_usr_refuses_by_name(tmp_path: Path) -> None:
    """US1-S6. `/usr` is the one path that must exist; absence there is fatal.

    Absence among the other four is never a refusal — that is US1-S2 — so the
    two cases are asserted apart rather than folded into one check.
    """
    root = _fake_root(tmp_path, "no-usr", {"/bin": "usr/bin"}, usr=None)

    with pytest.raises(SystemTreeError) as raised:
        system_tree_argv(root)

    assert "/usr" in str(raised.value), (
        f"the refusal must name /usr: {raised.value}"
    )

    absent_lib64 = _fake_root(tmp_path, "no-lib64", {"/bin": "usr/bin"})
    assert system_tree_argv(absent_lib64) == [
        "--ro-bind",
        str(absent_lib64 / "usr"),
        "/usr",
        "--symlink",
        "usr/bin",
        "/bin",
    ], "an absent mirrored path is not a refusal, it is simply not emitted"


def test_the_gate_refuses_a_broken_system_tree_before_it_forks(
    tmp_path: Path, planted: PlantedHost, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US1-S6. "Before any subprocess is created", measured with a detonator."""
    root = _fake_root(tmp_path, "gate-file-at-lib", {"/lib": A_FILE})

    def detonate(*args: object, **kwargs: object) -> None:
        raise AssertionError("a gate forked despite an underivable system tree")

    monkeypatch.setattr(gates_module.subprocess, "Popen", detonate)

    outcome = BwrapGateExecutor(system_root=root).run(
        GateInvocation(
            name="test", command="true", cwd=planted.worktree, timeout_s=30, env={}
        )
    )

    assert outcome.exit_code == 127, (
        f"an underivable system tree is infrastructure, reported as the gate "
        f"runner's own 127 outcome: {outcome}"
    )
    assert "/lib" in outcome.output, (
        f"and the outcome carries the path that could not be mirrored: "
        f"{outcome.output}"
    )


def test_the_agent_refuses_a_broken_system_tree_before_it_forks(
    tmp_path: Path, planted: PlantedHost, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US1-S6. The same, on the boundary whose failure costs an attempt."""
    root = _fake_root(tmp_path, "agent-file-at-lib", {"/lib": A_FILE})

    async def detonate(*args: object, **kwargs: object) -> None:
        raise AssertionError("an agent forked despite an underivable system tree")

    monkeypatch.setattr(adapter_module.asyncio, "create_subprocess_exec", detonate)

    invocation = AgentInvocation(
        argv=["claude", "-p"],
        prompt="implement the story",
        worktree=planted.worktree,
        env={"PATH": os.environ["PATH"], "HOME": str(planted.home)},
        log=None,
        standards_path=None,
        model_alias="anthropic/CHANGEME",
    )

    with pytest.raises(AdapterError) as raised:
        asyncio.run(BwrapBackend(system_root=root).launch(invocation))

    assert "/lib" in str(raised.value), (
        f"the adapter must refuse by name, not hand the path to bwrap: "
        f"{raised.value}"
    )


def test_the_stale_host_claim_is_gone_from_both_boundaries() -> None:
    """US1-S5. The comment is the defect's documentation; it must not survive.

    Asserted over the source text because that is where the defect lived: a
    comment stating a fact about one machine, above code that was the same fact
    compiled in. Leaving it above corrected code is worse than leaving it above
    broken code, since the next reader trusts it twice.
    """
    stale = "No /lib64 on this host"
    prose = "there is no `/lib64` on this aarch64 host"
    for module in (adapter_module, gates_module):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert stale not in source, (
            f"{module.__name__} still asserts a fact about one host's /lib64"
        )
        assert prose not in source, (
            f"{module.__name__} still carries the stale claim in prose"
        )
