"""The gate boundary must not symlink a runner the system tree already carries.

`BwrapGateExecutor._runner_binds` recreates the agent runner's `PATH` entry as
a `--symlink` so nested gates resolve the versioned install — correct on the
floor, where the runner is `~/.local/bin/claude` and no bind covers it. In the
demo container npm installs the runner as `/usr/bin/claude`, `system_tree_argv`
ro-binds `/usr` wholesale, and bwrap refuses to create a symlink where the
bound tree already has one:

    bwrap: Can't make symlink at /usr/bin/claude: existing destination is
      ../lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe

Measured 2026-08-26: all four attempts of the demo's story gate-FAILED in ~8ms
each on this line — the ninth defect of the demo rehearsal — while the agent
boundary, which ro-binds over the same path instead of symlinking, ran fine.
"""

from __future__ import annotations

from pathlib import Path

from factory.verify.gates import BwrapGateExecutor
from factory.verify.toolchain import ResolvedTool


def _tool(name: str, found_at: str, real_path: str | None = None) -> ResolvedTool:
    return ResolvedTool(
        name=name,
        found_at=Path(found_at),
        real_path=Path(real_path or found_at),
    )


def _flags(binds: list[tuple[str, str, str]], flag: str) -> list[tuple[str, str, str]]:
    return [b for b in binds if b[0] == flag]


def test_a_system_tree_runner_gets_no_symlink_at_all() -> None:
    """The container's shape: npm put the launcher in /usr/bin."""
    executor = BwrapGateExecutor()
    runner = _tool(
        "claude",
        "/usr/bin/claude",
        "/usr/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe",
    )

    binds = executor._toolchain_binds(tools=[runner])

    assert not _flags(binds, "--symlink"), (
        "a --symlink at a path inside the ro-bound /usr makes bwrap refuse to start; "
        "the /usr bind already carries the launcher and its target"
    )
    assert not any("/usr/bin/claude" in b for bind in binds for b in bind[1:]), (
        "nothing should be emitted for a runner the system tree bind already provides"
    )


def test_a_home_installed_runner_still_gets_its_symlink() -> None:
    """The floor's shape, which the fix must not change: versioned install in HOME."""
    executor = BwrapGateExecutor()
    runner = _tool(
        "claude",
        "/home/admin/.local/bin/claude",
        "/home/admin/.local/share/claude/versions/2.1.223",
    )

    binds = executor._toolchain_binds(tools=[runner])

    assert (
        "--symlink",
        "/home/admin/.local/share/claude/versions/2.1.223",
        "/home/admin/.local/bin/claude",
    ) in binds, "the nested-gate resolution contract for home installs must survive"


def test_the_system_root_seam_is_honored() -> None:
    """A test-supplied root moves the boundary of 'inside the system tree' with it."""
    executor = BwrapGateExecutor(system_root="/fake-root")
    runner = _tool(
        "claude",
        "/usr/bin/claude",
        "/usr/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe",
    )

    binds = executor._toolchain_binds(tools=[runner])

    # Under a fake system root, /usr/bin is NOT the bound tree, so the symlink
    # is legitimate again.
    assert _flags(binds, "--symlink"), (
        "with system_root=/fake-root the host /usr is not ro-bound, and the runner "
        "needs its symlink exactly as a home install does"
    )
