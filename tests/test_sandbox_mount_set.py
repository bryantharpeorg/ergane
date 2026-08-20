"""The sandbox system tree is derived from the host layout, not declared.

Every assertion here supplies its own fake root so the test holds on every
architecture. Reading the real ``/`` would test only the machine the test runs
on, which is exactly how the original bug shipped: the literal list matched
one aarch64 host and failed on the x86_64 host that has ``/lib64``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from factory.verify.gates import BwrapGateExecutor, GateInvocation
from factory.verify.toolchain import ToolchainError, derive_system_tree_mounts
from factory.workgraph.adapter import AgentInvocation, BwrapBackend


_REQUIRED_SYMLINK_PATHS = ("/bin", "/lib", "/lib64", "/sbin")


def _make_layout(
    root: Path,
    *,
    usr: bool = True,
    bin_target: str | None = None,
    lib_target: str | None = None,
    lib64_target: str | None = None,
    sbin_target: str | None = None,
) -> Path:
    """Create a fake host root with the given symlinks.

    ``None`` means the path is absent.  ``usr=True`` creates ``/usr`` as a
    directory so the shared derivation has something to bind read-only.
    """
    if usr:
        (root / "usr").mkdir(parents=True, exist_ok=True)
    for name, target in (
        ("bin", bin_target),
        ("lib", lib_target),
        ("lib64", lib64_target),
        ("sbin", sbin_target),
    ):
        if target is not None:
            (root / name).symlink_to(target)
    return root


def _agent_invocation(worktree: Path) -> AgentInvocation:
    return AgentInvocation(
        argv=["claude", "-p"],
        prompt="test",
        worktree=worktree,
        env={"HOME": str(worktree)},
        log=None,
        standards_path=None,
        model_alias="anthropic/CHANGEME",
    )


def _gate_invocation(worktree: Path) -> GateInvocation:
    return GateInvocation(
        name="test", command="true", cwd=worktree, timeout_s=30, env={}
    )


def _system_tree_entries(argv: list[str]) -> list[str]:
    """The system-tree portion of a bwrap argv, from first bind to pseudo-fs."""
    start = next(
        i
        for i, token in enumerate(argv)
        if token in ("--ro-bind", "--symlink")
    )
    end = next(
        (i for i, token in enumerate(argv) if token in ("--proc", "--dev", "--tmpfs")),
        len(argv),
    )
    return argv[start:end]


def test_lib64_symlink_is_emitted_when_host_has_it(tmp_path: Path) -> None:
    """US1-S1: a host with ``/lib64`` as a symlink gets that symlink in the argv."""
    layout = _make_layout(tmp_path / "host", lib64_target="usr/lib64")
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    argv = BwrapBackend(host_root=layout)._build_argv(_agent_invocation(worktree))
    entries = _system_tree_entries(argv)

    assert ["--symlink", "usr/lib64", "/lib64"] in [
        entries[i : i + 3] for i in range(0, len(entries), 3)
    ], f"expected /lib64 symlink in system-tree entries: {entries}"


def test_lib64_is_absent_when_host_has_no_lib64(tmp_path: Path) -> None:
    """US1-S2: a host without ``/lib64`` must not have a ``/lib64`` entry."""
    layout = _make_layout(tmp_path / "host")
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    argv = BwrapBackend(host_root=layout)._build_argv(_agent_invocation(worktree))
    entries = _system_tree_entries(argv)

    assert "/lib64" not in entries, f"/lib64 must not appear when absent on host: {entries}"


def test_each_system_path_is_emitted_iff_it_is_a_symlink(tmp_path: Path) -> None:
    """US1-S3: the four paths are emitted only where the host has a symlink.

    The layout deliberately varies across all four so a fixed set cannot pass:
    ``/bin`` and ``/lib64`` are symlinks, ``/lib`` is a directory, ``/sbin`` is
    absent.
    """
    layout = _make_layout(
        tmp_path / "host",
        bin_target="usr/bin",
        lib_target=None,  # created as a real directory below
        lib64_target="usr/lib64",
        sbin_target=None,
    )
    (layout / "lib").mkdir()
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    argv = BwrapBackend(host_root=layout)._build_argv(_agent_invocation(worktree))
    entries = _system_tree_entries(argv)

    assert ["--symlink", "usr/bin", "/bin"] in [
        entries[i : i + 3] for i in range(0, len(entries), 3)
    ], f"/bin symlink missing: {entries}"
    assert ["--symlink", "usr/lib64", "/lib64"] in [
        entries[i : i + 3] for i in range(0, len(entries), 3)
    ], f"/lib64 symlink missing: {entries}"
    assert "/lib" not in entries, f"/lib must not appear as a directory: {entries}"
    assert "/sbin" not in entries, f"/sbin must not appear when absent: {entries}"


def test_agent_and_gate_boundaries_share_system_tree_entries(tmp_path: Path) -> None:
    """US1-S4: both boundaries derive the same system-tree entries from one helper."""
    layout = _make_layout(
        tmp_path / "host",
        bin_target="usr/bin",
        lib_target="usr/lib",
        lib64_target="usr/lib64",
        sbin_target="usr/sbin",
    )
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    agent_argv = BwrapBackend(host_root=layout)._build_argv(_agent_invocation(worktree))
    gate_argv = BwrapGateExecutor(host_root=layout)._build_argv(_gate_invocation(worktree))

    assert _system_tree_entries(agent_argv) == _system_tree_entries(gate_argv)


def test_non_symlink_non_directory_required_path_refuses_by_name(tmp_path: Path) -> None:
    """US1-S6: an existing but unmountable required path raises before any fork."""
    layout = _make_layout(tmp_path / "host", bin_target="usr/bin")
    (layout / "lib").write_text("not a directory or symlink")

    with pytest.raises(ToolchainError) as excinfo:
        derive_system_tree_mounts(layout)

    message = str(excinfo.value)
    assert "/lib" in message, f"refusal must name the path: {message}"


def test_missing_required_path_is_not_a_refusal(tmp_path: Path) -> None:
    """US1-S6 (corollary): absence of a required path is allowed, not refused."""
    layout = _make_layout(tmp_path / "host", bin_target="usr/bin", lib_target="usr/lib")
    # /lib64 and /sbin are absent on purpose.

    entries = derive_system_tree_mounts(layout)

    assert "/lib64" not in entries
    assert "/sbin" not in entries


def test_missing_usr_is_a_refusal(tmp_path: Path) -> None:
    """US1-S6 (corollary): ``/usr`` must exist and be bindable."""
    layout = _make_layout(tmp_path / "host", usr=False)

    with pytest.raises(ToolchainError) as excinfo:
        derive_system_tree_mounts(layout)

    assert "/usr" in str(excinfo.value)
