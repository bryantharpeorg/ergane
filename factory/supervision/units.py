"""042-US2: the systemd user units the engine generates, installs and removes.

The design input is not in this repository. Five unit files and a probe script
were hand-written on the operator's host after a 2026-08-11 outage and live in
another repo entirely; they work, and every path in them is that one host's.
This module is those lessons made portable: the containment, the kill
semantics and the restart bound are carried over verbatim in meaning, and every
literal path is resolved from the operator's own installation instead
(SC-006).

Three things here are load-bearing, and each was paid for:

- **`KillMode=control-group`.** Agents, gate subprocesses and anything they
  spawned live in the unit's cgroup, and stopping the unit must take the whole
  tree. A bare kill of the worker pid is what leaves 66 MiB orphans on PID 1. A
  unit missing this starts, restarts and supervises perfectly while leaking.
- **The slice.** Orphans reparent to PID 1 but do *not* leave their cgroup, so
  a leak stays inside `MemoryMax` and the kernel reclaims within the slice
  rather than taking the host down. `TasksMax` is the other half: 8,131
  processes is far past anything a healthy floor needs.
- **The command line may not contain `python -`.** On 2026-08-12 an agent ran
  `pkill -f "python -"` to clean up its own strays; that matched the worker's
  and the bridge's `uv run python -m factory.worker` command lines and killed
  both. 011/US4's pid namespace fixes the root defect for dispatched agents;
  the spelling still protects the callers it does not cover, and it costs
  nothing.

Provenance is recorded at install time — a digest of what was written — so
`uninstall` *knows* which files are the engine's rather than guessing from
their names. The operator's own unit of a colliding name may be the one keeping
their host alive, and it is reported rather than deleted (FR-008).

The probe's own unit and timer belong to 042-US4 with the probe itself, and
could not have shipped ahead of it: a unit whose `ExecStart` names a module
that does not exist yet exits 1 on `ModuleNotFoundError`, and 1 is inside the
`SuccessExitStatus=0 1` such a unit declares — the timer would read green while
supervising nothing.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable, Mapping, Sequence

from factory.cli.errors import OperatorError
from factory.registry import resolve_state_home

SLICE_UNIT = "ergane.slice"
WORKER_UNIT = "ergane-worker.service"
BRIDGE_UNIT = "ergane-bridge.service"

#: One wrapper, shared by every unit, taking the module to run as its argument.
WRAPPER_NAME = "ergane-run.sh"

#: Where the provenance record lives, beside the wrapper rather than beside the
#: units: a state file under a config directory is what makes `~/.config`
#: un-copyable between hosts.
MANIFEST_NAME = "installed.json"

#: What an agent's stray-cleanup sweep matched on 2026-08-12.
PKILL_PATTERN = "python -"

#: The units `install` enables. The slice is not among them: it is pulled in by
#: the `Slice=` lines that reference it, so enabling it would be declaring a
#: `WantedBy` that systemd then has to reconcile.
ENABLE_TARGETS = (WORKER_UNIT, BRIDGE_UNIT)

_MODULES = {
    WORKER_UNIT: "factory.worker",
    BRIDGE_UNIT: "factory.notify.service",
}


@dataclasses.dataclass(frozen=True)
class CommandResult:
    """What a command said, in the two terms any caller here needs."""

    code: int
    out: str = ""


def _run_command(argv: Sequence[str]) -> CommandResult:
    """Run one command. The seam every test in this story closes.

    Tests pass their own; nothing in the suite may reach the systemd session
    running the factory, because on this host that session *is* the factory.
    """
    finished = subprocess.run(  # noqa: S603 - fixed argv, no shell
        list(argv), capture_output=True, text=True, check=False
    )
    return CommandResult(finished.returncode, finished.stdout.strip())


@dataclasses.dataclass(frozen=True)
class InstallLayout:
    """Every path a generated file may name, and nothing else (SC-006).

    `roots` is what the scan is against: a generated unit that references a
    path outside these starts, restarts and supervises perfectly on the one
    host where that path happens to exist.
    """

    install_root: Path
    interpreter: Path
    unit_dir: Path
    generated_dir: Path
    env_command: str | None = None
    memory_high: str = "32G"
    memory_max: str = "48G"
    tasks_max: int = 2000
    restart_window_s: int = 300
    restart_burst: int = 5

    @property
    def roots(self) -> tuple[Path, ...]:
        return (
            self.install_root,
            self.unit_dir,
            self.generated_dir,
            self.interpreter,
        )

    @property
    def wrapper(self) -> Path:
        return self.generated_dir / WRAPPER_NAME


def supervision_home() -> Path:
    """Where the engine keeps what supervision generates and remembers.

    Under 034/us2's `resolve_state_home`, which honors `ERGANE_STATE_HOME` and
    the legacy name ahead of XDG. Deriving a second answer from
    `XDG_STATE_HOME` here is exactly the drift that resolver exists to prevent.
    """
    return resolve_state_home() / "ergane" / "supervision"


def resolve_layout(
    *,
    home: Path | str | None = None,
    install_root: Path | str | None = None,
    interpreter: Path | str | None = None,
    unit_dir: Path | str | None = None,
    generated_dir: Path | str | None = None,
    env_command: str | None = None,
) -> InstallLayout:
    """Resolve where this installation actually is.

    `install_root` defaults to the directory holding the `factory` package,
    which is the repository root in a checkout and `site-packages` in a wheel —
    either way it is *this* installation and never a literal.
    """
    base = Path.home() if home is None else Path(home)
    root = (
        Path(__file__).resolve().parent.parent.parent
        if install_root is None
        else Path(install_root)
    )
    exe = Path(sys.executable if interpreter is None else interpreter)
    return InstallLayout(
        install_root=root,
        interpreter=_python3_spelling(exe),
        unit_dir=base / ".config/systemd/user" if unit_dir is None else Path(unit_dir),
        generated_dir=(
            supervision_home() if generated_dir is None else Path(generated_dir)
        ),
        env_command=env_command,
    )


def _python3_spelling(exe: Path) -> Path:
    """Prefer the `python3` a venv always carries beside its `python`.

    Not cosmetic: `…/bin/python -m factory.worker` is the command line the
    2026-08-12 sweep matched, and `…/bin/python3 -m` is the one it did not.
    """
    sibling = exe.with_name("python3")
    if exe.name != "python3" and sibling.exists():
        return sibling
    return exe


def command_line(layout: InstallLayout, module: str) -> str:
    """The argv the kernel will show for a unit running `module`.

    Distinct from the file's text on purpose: the wrapper quotes the
    interpreter, so a bare `python` reads as `python" -m` on disk and as
    `python -m` in `/proc/<pid>/cmdline`. `pkill -f` reads the second one.
    """
    return f"{layout.interpreter} -m {module}"


@dataclasses.dataclass(frozen=True)
class GeneratedFile:
    """One file the engine writes, and where it goes."""

    name: str
    text: str
    directory: Path
    mode: int = 0o644

    @property
    def path(self) -> Path:
        return self.directory / self.name


def generated_files(layout: InstallLayout) -> tuple[GeneratedFile, ...]:
    """Every file `install` writes, rendered from `layout` and nothing else."""
    for module in _MODULES.values():
        if PKILL_PATTERN in command_line(layout, module):
            raise OperatorError(
                f"the interpreter at {layout.interpreter} would give this unit a "
                f"command line containing {PKILL_PATTERN!r}, which an agent's "
                "stray-cleanup sweep matched on 2026-08-12, killing the worker "
                "it was running under; point at the venv's python3 instead"
            )

    units = layout.unit_dir
    return (
        GeneratedFile(SLICE_UNIT, _slice_text(layout), units),
        GeneratedFile(WORKER_UNIT, _worker_text(layout), units),
        GeneratedFile(BRIDGE_UNIT, _bridge_text(layout), units),
        GeneratedFile(WRAPPER_NAME, _wrapper_text(layout), layout.generated_dir, 0o755),
    )


def _slice_text(layout: InstallLayout) -> str:
    return f"""\
[Unit]
Description=ergane — memory-contained slice

[Slice]
# Orphaned processes reparent to PID 1 but do NOT leave their cgroup, so a leak
# stays inside these limits and the kernel reclaims within the slice instead of
# taking the host down with it. MemoryHigh applies pressure first; MemoryMax is
# the wall.
MemoryHigh={layout.memory_high}
MemoryMax={layout.memory_max}

# A runaway spawn is the other half of the same failure.
TasksMax={layout.tasks_max}
"""


def _service_text(
    layout: InstallLayout,
    *,
    description: str,
    module: str,
    restart: str,
    stop_timeout_s: int,
) -> str:
    return f"""\
[Unit]
Description={description}
# Give up rather than flap: a restart loop during a memory storm deepens it.
StartLimitIntervalSec={layout.restart_window_s}
StartLimitBurst={layout.restart_burst}

[Service]
Type=simple
Slice={SLICE_UNIT}
WorkingDirectory={layout.install_root}
ExecStart={layout.wrapper} {module}

# The point, not a default worth losing: agents, gate subprocesses and anything
# they spawned are in this unit's cgroup, and stopping the unit must take the
# whole tree. A bare kill of the main pid is what leaves orphans on PID 1.
KillMode=control-group
KillSignal=SIGTERM
TimeoutStopSec={stop_timeout_s}

Restart={restart}
RestartSec=10

[Install]
WantedBy=default.target
"""


def _worker_text(layout: InstallLayout) -> str:
    return _service_text(
        layout,
        description="ergane — factory worker (workgraph task queue)",
        module=_MODULES[WORKER_UNIT],
        restart="on-failure",
        stop_timeout_s=120,
    )


def _bridge_text(layout: InstallLayout) -> str:
    return _service_text(
        layout,
        # The listening half of the operator channel. Its death is invisible
        # from inside the factory: the sending half is a workflow activity that
        # needs no bridge, so questions keep flowing outward while every inbound
        # answer falls on the floor. This unit is the only watcher it has.
        description="ergane — operator channel bridge (replies to signals)",
        module=_MODULES[BRIDGE_UNIT],
        restart="always",
        stop_timeout_s=30,
    )


def _wrapper_text(layout: InstallLayout) -> str:
    """The one indirection, and the two reasons it is not resolved into units.

    systemd cannot evaluate a command substitution, so an operator's
    environment command can only run from a script; resolving it into
    `Environment=` lines instead would write their credentials to disk in a
    file the journal echoes back. And `PATH` is composed at *start* time rather
    than frozen at install time, because a unit whose `PATH` predates the
    toolchain installed after it is a real defect this repository has already
    paid for (`factory/verify/toolchain.py`).
    """
    environment = (
        f'eval "$({layout.env_command})"\n' if layout.env_command else ""
    )
    return f"""\
#!/bin/sh
# Generated by `ergane worker install`. Edit the engine, not this file:
# uninstall removes it only while it still matches what install wrote.
set -eu
cd "{layout.install_root}"
PATH="$HOME/.local/bin:$PATH"
export PATH
{environment}exec "{layout.interpreter}" -m "$1"
"""


@dataclasses.dataclass(frozen=True)
class InstallReport:
    """What was written, what was left alone, and what came up."""

    written: tuple[str, ...]
    kept: tuple[str, ...]
    active: tuple[str, ...]
    enabled: tuple[str, ...]
    linger: bool

    def render(self) -> str:
        lines = [f"wrote {len(self.written)} file(s) to the unit directory"]
        lines += [f"  active+enabled: {name}" for name in sorted(self.active)]
        if not self.linger:
            lines.append("  WARN: linger is off; user units stop at logout")
        lines += [f"  left alone (not written by ergane): {n}" for n in self.kept]
        return "\n".join(lines)


@dataclasses.dataclass(frozen=True)
class UninstallReport:
    """What was removed, and what was deliberately not."""

    removed: tuple[str, ...]
    kept: tuple[str, ...]

    def render(self) -> str:
        lines = [f"removed {len(self.removed)} file(s)"]
        lines += [f"  left in place (not written by ergane): {n}" for n in self.kept]
        return "\n".join(lines)


def install(
    layout: InstallLayout,
    *,
    run: Callable[[Sequence[str]], CommandResult] | None = None,
) -> InstallReport:
    """Write the units, enable them, enable linger, and report what came up.

    A file the engine did not write is never overwritten — that is the half of
    the collision that cannot be undone.
    """
    runner = _run_command if run is None else run
    layout.unit_dir.mkdir(parents=True, exist_ok=True)
    layout.generated_dir.mkdir(parents=True, exist_ok=True)

    recorded = _read_manifest(layout)
    written: list[str] = []
    kept: list[str] = []
    fresh: dict[str, str] = {}
    for generated in generated_files(layout):
        if _is_someone_elses(generated, recorded):
            kept.append(generated.name)
            continue
        generated.path.write_text(generated.text, encoding="utf-8")
        generated.path.chmod(generated.mode)
        written.append(generated.name)
        fresh[generated.name] = _digest(generated.text)
    _write_manifest(layout, fresh)

    runner(("systemctl", "--user", "daemon-reload"))
    # Without linger a user unit is stopped when the last session ends, which
    # turns "supervised" into "supervised until the operator closes their laptop".
    linger = runner(("loginctl", "enable-linger")).code == 0
    for name in ENABLE_TARGETS:
        if name in written:
            runner(("systemctl", "--user", "enable", "--now", name))

    return InstallReport(
        written=tuple(written),
        kept=tuple(kept),
        active=_reading(runner, "is-active"),
        enabled=_reading(runner, "is-enabled"),
        linger=linger,
    )


def uninstall(
    layout: InstallLayout,
    *,
    run: Callable[[Sequence[str]], CommandResult] | None = None,
    open_epics: Callable[[], Sequence[str]] | None = None,
) -> UninstallReport:
    """Remove exactly the files install wrote, and report the rest (FR-008).

    The epic read comes first and touches nothing: a disable issued before the
    refusal is a half-uninstall, which is worse than either outcome.
    """
    epics = tuple((_open_epic_ids if open_epics is None else open_epics)())
    if epics:
        raise OperatorError(
            f"refusing to uninstall while {', '.join(epics)} is in flight: "
            "removing the worker mid-epic strands the attempt it is running; "
            "let it land, or kill it first"
        )

    runner = _run_command if run is None else run
    recorded = _read_manifest(layout)
    for name in ENABLE_TARGETS:
        if name in recorded:
            # Before deleting: systemd holds the parsed unit in memory, and a
            # file removed out from under a running unit leaves it up and
            # invisible to `disable` until the next reboot.
            runner(("systemctl", "--user", "disable", "--now", name))

    removed: list[str] = []
    kept: list[str] = []
    for generated in generated_files(layout):
        if not generated.path.exists():
            continue
        if _is_someone_elses(generated, recorded):
            kept.append(generated.name)
            continue
        generated.path.unlink()
        removed.append(generated.name)
    (layout.generated_dir / MANIFEST_NAME).unlink(missing_ok=True)

    runner(("systemctl", "--user", "daemon-reload"))
    return UninstallReport(tuple(removed), tuple(kept))


def _reading(
    runner: Callable[[Sequence[str]], CommandResult], question: str
) -> tuple[str, ...]:
    """Which of the enable targets answer `question` affirmatively.

    Read back rather than inferred: `enable --now` returning 0 is not the same
    claim as the unit being up, and the difference is what an operator wants
    from an install that says it succeeded.
    """
    return tuple(
        name
        for name in ENABLE_TARGETS
        if runner(("systemctl", "--user", question, name)).code == 0
    )


def _is_someone_elses(generated: GeneratedFile, recorded: Mapping[str, str]) -> bool:
    """Whether this file on disk is one the engine did not write.

    Provenance is a digest, not a filename: an operator who tuned `MemoryMax`
    by hand has made the file theirs, and the tuning was probably a response to
    something.
    """
    if not generated.path.exists():
        return False
    return recorded.get(generated.name) != _digest(
        generated.path.read_text(encoding="utf-8")
    )


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_manifest(layout: InstallLayout) -> dict[str, str]:
    try:
        document = json.loads(
            (layout.generated_dir / MANIFEST_NAME).read_text(encoding="utf-8")
        )
        return {str(k): str(v) for k, v in document["units"].items()}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def _write_manifest(layout: InstallLayout, units: Mapping[str, str]) -> None:
    (layout.generated_dir / MANIFEST_NAME).write_text(
        json.dumps({"units": dict(units)}, indent=2, sort_keys=True), encoding="utf-8"
    )


def _open_epic_ids() -> tuple[str, ...]:
    """Which epics are open right now — FR-012's refusal, as a read.

    Imported inside the function on purpose, and it stays that way when 042-US4
    lands: the probe imports this module for the unit names, and it is the
    process that runs when Temporal is the thing that died. A module-scope
    Temporal import here would put a client on that path for the sake of a
    capacity read the probe never performs. The query is the roadmap's own, so
    a closed epic is narrowed away on the server rather than here.
    """
    import asyncio

    from factory.activities.roadmap_activities import _OPEN_EPIC_STATUS
    from factory.cli.nouns import _open_client
    from factory.cli.status import EPIC_ID_PREFIX

    async def listed() -> tuple[str, ...]:
        client = await _open_client()
        found = [
            str(execution.id)
            async for execution in client.list_workflows(
                f'ExecutionStatus = "{_OPEN_EPIC_STATUS}"'
            )
            if str(execution.id).startswith(EPIC_ID_PREFIX)
        ]
        return tuple(sorted(found))

    return asyncio.run(listed())
