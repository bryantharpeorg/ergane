"""042-US2: the systemd user units the engine generates, installs and removes.

The design input is not in this repository. Five unit files and a probe script
were hand-written on the operator's host after a 2026-08-11 outage and live in
another repo entirely; they work, and every path in them is that one host's.
This module is those lessons made portable: the containment, the kill
semantics and the restart bound are carried over verbatim in meaning, and every
literal path is resolved from the operator's own installation instead
(SC-006).

Four things here are load-bearing, and each was paid for:

- **`KillMode=control-group`.** Agents, gate subprocesses and anything they
  spawned live in the unit's cgroup, and stopping the unit must take the whole
  tree. A bare kill of the worker pid is what leaves 66 MiB orphans on PID 1. A
  unit missing this starts, restarts and supervises perfectly while leaking.
- **The slice.** Orphans reparent to PID 1 but do *not* leave their cgroup, so
  a leak stays inside `MemoryMax` and the kernel reclaims within the slice
  rather than taking the host down. `TasksMax` is the other half: 8,131
  processes is far past anything a healthy floor needs.
- **The probe is outside the slice.** Every other generated unit goes in it;
  the probe's does not, and that is the whole point — a supervisor inside the
  contained slice is reclaimed alongside the leak it exists to report.
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

#: 082-US2: the versioned worker, one instance per deployed build id. A template
#: rather than five copies of a unit file because the only thing that differs
#: between two versions is the checkout they run from, and `%i` already spells
#: that. US4 retires `WORKER_UNIT` in favour of this one; until it does, both are
#: generated and only the legacy one is enabled, so this story lands beside the
#: running worker instead of underneath it.
WORKER_TEMPLATE_UNIT = "ergane-worker@.service"

BRIDGE_UNIT = "ergane-bridge.service"
TEMPORAL_UNIT = "ergane-temporal.service"
PROBE_UNIT = "ergane-probe.service"
PROBE_TIMER = "ergane-probe.timer"

#: One wrapper, shared by every unit, taking the module to run as its argument.
WRAPPER_NAME = "ergane-run.sh"

#: Where the provenance record lives, beside the wrapper rather than beside the
#: units: a state file under a config directory is what makes `~/.config`
#: un-copyable between hosts.
MANIFEST_NAME = "installed.json"

#: What an agent's stray-cleanup sweep matched on 2026-08-12.
PKILL_PATTERN = "python -"

#: The units `install` enables. Neither the slice nor the probe *service* is
#: among them — the slice is pulled in by the `Slice=` lines that reference it
#: and the probe service by its timer, so enabling either would be declaring a
#: `WantedBy` that systemd then has to reconcile.
#: Units enabled for every installation.  TEMPORAL_UNIT is added when the
#: layout's `temporal_mode` is `managed`; it is deliberately not in this tuple
#: because external mode must not enable a unit that was not generated.
ENABLE_TARGETS = (WORKER_UNIT, BRIDGE_UNIT, TEMPORAL_UNIT, PROBE_TIMER)

_MODULES = {
    WORKER_UNIT: "factory.worker",
    WORKER_TEMPLATE_UNIT: "factory.worker",
    BRIDGE_UNIT: "factory.notify.service",
    PROBE_UNIT: "factory.supervision.probe",
}

#: Where a deployed version's frozen checkout goes, under the supervision home
#: and therefore outside the operator's own checkout (082 plan trap 2).
DEPLOYMENTS_DIRNAME = "deployments"

#: The subdirectory of a deployment that git owns. The checkout is *inside* the
#: deployment directory rather than being it, so `git worktree remove` has one
#: path to take and the reaper's `rm` of what is left never reaches a tree git
#: still has state about (plan trap 3).
DEPLOYMENT_TREE_DIRNAME = "tree"


def worker_instance(build_id: str) -> str:
    """The unit name serving one deployed build id."""
    return f"ergane-worker@{build_id}.service"


def instance_build_id(unit: str) -> str:
    """The build id `unit` serves — the inverse of `worker_instance`."""
    return unit.removeprefix("ergane-worker@").removesuffix(".service")


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
    probe_interval: str = "2min"
    temporal_mode: str = "external"

    @property
    def roots(self) -> tuple[Path, ...]:
        # The Temporal db lives under the state home, one directory above the
        # supervision subdirectory (SC-004).  Including that parent in roots lets
        # the path scan treat it as inside the operator's own installation.
        return (
            self.install_root,
            self.unit_dir,
            self.generated_dir,
            self.generated_dir.parent,
            self.deployments_dir,
            self.interpreter,
        )

    @property
    def wrapper(self) -> Path:
        return self.generated_dir / WRAPPER_NAME

    @property
    def deployments_dir(self) -> Path:
        """Where deployed versions keep their frozen checkouts (082-US2).

        Named in `roots` even though it is under `generated_dir`, because the
        template unit points at it by name and the scan that keeps generated
        text portable reads this tuple rather than the directory hierarchy.
        """
        return self.generated_dir / DEPLOYMENTS_DIRNAME

    def deployment_tree(self, build_id: str) -> Path:
        """The frozen checkout one deployed version runs from."""
        return self.deployments_dir / build_id / DEPLOYMENT_TREE_DIRNAME

    def deployment_interpreter(self, build_id: str) -> Path:
        """That checkout's own venv python — the one `uv sync` built in it.

        Spelled `python3` for the same reason `_python3_spelling` exists: a
        deployment whose command line reads `python -m factory.worker` is one
        an agent's stray sweep can kill (2026-08-12).
        """
        return self.deployment_tree(build_id) / ".venv/bin/python3"

    @property
    def temporal_db_path(self) -> Path:
        """Where the managed Temporal server keeps its SQLite history."""
        return self.generated_dir.parent / "temporal" / "dev.db"


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


def _temporal_managed(layout: InstallLayout) -> bool:
    """Whether this installation generates the managed Temporal server unit.

    `ergane worker install` is the supervised path and defaults to managed.  The
    `ergane install` walkthrough sets `temporal_mode="external"` when the
    operator chose external Temporal, and that layout is what `resolve_layout`
    will produce for the same host.
    """
    return layout.temporal_mode == "managed"


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
    generated = layout.generated_dir
    files: list[GeneratedFile] = [
        GeneratedFile(SLICE_UNIT, _slice_text(layout), units),
        GeneratedFile(WORKER_UNIT, _worker_text(layout), units),
        GeneratedFile(WORKER_TEMPLATE_UNIT, _worker_template_text(layout), units),
        GeneratedFile(BRIDGE_UNIT, _bridge_text(layout), units),
        GeneratedFile(PROBE_UNIT, _probe_text(layout), units),
        GeneratedFile(PROBE_TIMER, _timer_text(layout), units),
        GeneratedFile(WRAPPER_NAME, _wrapper_text(layout), generated, 0o755),
    ]
    if _temporal_managed(layout):
        files.insert(
            4, GeneratedFile(TEMPORAL_UNIT, _temporal_text(layout), units)
        )
    return tuple(files)


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
    working_directory: Path | None = None,
    exec_arguments: str = "",
    environment: Sequence[str] = (),
) -> str:
    """One service body, with the three things a versioned instance changes.

    `working_directory` and `exec_arguments` exist because 082-US2's template
    runs the *deployment's* code rather than this installation's, and
    `environment` because that instance has to tell the worker which build id it
    is. Everything else — the slice, the kill semantics, the restart bound — is
    identical by construction rather than by two texts agreeing.
    """
    settings = "".join(f"Environment={value}\n" for value in environment)
    return f"""\
[Unit]
Description={description}
# Give up rather than flap: a restart loop during a memory storm deepens it.
StartLimitIntervalSec={layout.restart_window_s}
StartLimitBurst={layout.restart_burst}

[Service]
Type=simple
Slice={SLICE_UNIT}
WorkingDirectory={layout.install_root if working_directory is None else working_directory}
{settings}ExecStart={layout.wrapper} {module}{exec_arguments}

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


def _worker_template_text(layout: InstallLayout) -> str:
    """082-US2 (FR-003): one instance per deployed version, `%i` = the build id.

    Three things are deliberate here, and each is a trap the plan numbers.

    **The instance runs the deployment's code, not this installation's** (trap
    4). `WorkingDirectory` and the interpreter both come out of the frozen
    checkout; a template that versioned the unit *name* while still executing
    `install_root` would have versioned nothing at all. The wrapper is still the
    thing exec'd, so the operator's environment command keeps being evaluated at
    start time from a script rather than resolved into `Environment=` lines the
    journal echoes back.

    **The build id is passed, not derived** — `%i` is the directory name deploy
    created, so a restart in place re-registers the same version rather than
    minting a new one (trap 8). Whatever `Restart=on-failure` brings back finds
    the same checkout at the same revision and declares the same thing.

    **The instance is in the slice.** A versioned worker's agents and gate
    subprocesses live in its cgroup exactly like the legacy unit's, and a
    deploy that escaped the containment would reintroduce the 2026-08-11 leak
    one version at a time.
    """
    # Imported inside the function for the same reason `_open_epic_ids` is:
    # `factory.versioning` imports `temporalio.common` at module scope, and
    # `factory/supervision/probe.py` imports this module for the unit names
    # while being the process that runs when Temporal is what died. The name
    # is read from there rather than respelled here because a unit that sets a
    # variable the worker does not read is a version that never registers.
    from factory.versioning import WORKER_BUILD_ID_ENV

    tree = layout.deployment_tree("%i")
    return _service_text(
        layout,
        description="ergane — factory worker, version %i (workgraph task queue)",
        module=_MODULES[WORKER_TEMPLATE_UNIT],
        restart="on-failure",
        # The drain the whole spec is about: stopping an instance must give the
        # attempts pinned to it the same 120s the legacy unit gives its own.
        stop_timeout_s=120,
        working_directory=tree,
        exec_arguments=f" {tree} {layout.deployment_interpreter('%i')}",
        environment=(f"{WORKER_BUILD_ID_ENV}=%i",),
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


def _temporal_text(layout: InstallLayout) -> str:
    """The managed Temporal server unit: persistence, containment, restart bound.

    The Go dev server is downloaded on demand by the temporalio package and cached
    under the state home.  Persistence lives there too: a host reinstall that
    preserves the state directory keeps history, while a fresh install starts
    clean — which is the contract SC-004 defends.
    """
    db_path = layout.temporal_db_path
    # Use a tiny Python shim so the command line does not contain `python -`.
    # The shim starts the local dev server on the bound frontend port and blocks
    # until the process exits; systemd receives the server's stdout and the
    # usual signals.
    return f"""\
[Unit]
Description=ergane — managed Temporal server (SQLite persistence)
# Give up rather than flap: a restart loop during a memory storm deepens it.
StartLimitIntervalSec={layout.restart_window_s}
StartLimitBurst={layout.restart_burst}

[Service]
Type=simple
Slice={SLICE_UNIT}
WorkingDirectory={layout.install_root}
ExecStart={layout.wrapper} factory.supervision.temporal_server --db-filename {db_path} --namespace ergane --log-level warn

# The point, not a default worth losing: the dev server spawns child processes,
# and stopping the unit must take the whole tree. A bare kill of the main pid is
# what leaves orphans on PID 1.
KillMode=control-group
KillSignal=SIGTERM
TimeoutStopSec=60

Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
"""


def _probe_text(layout: InstallLayout) -> str:
    return f"""\
[Unit]
Description=ergane — stack liveness, memory and orphan-leak probe

[Service]
Type=oneshot
# Deliberately NOT in {SLICE_UNIT}: the supervisor must outlive what it watches.
# A probe inside the contained slice is reclaimed alongside the leak it exists
# to report.
ExecStart={layout.wrapper} {_MODULES[PROBE_UNIT]}
# A degraded verdict exits 1 by design; that is a report, not a unit failure.
# Exit 2 — an alert nobody received — is a failure, and must stay one.
SuccessExitStatus=0 1
"""


def _timer_text(layout: InstallLayout) -> str:
    return f"""\
[Unit]
Description=ergane — run the stack probe on its interval

[Timer]
OnBootSec=90s
OnUnitActiveSec={layout.probe_interval}
AccuracySec=15s
Unit={PROBE_UNIT}

[Install]
WantedBy=timers.target
"""


def _wrapper_text(layout: InstallLayout) -> str:
    """The one indirection, and the two reasons it is not resolved into units.

    systemd cannot evaluate a command substitution, so an operator's
    environment command can only run from a script; resolving it into
    `Environment=` lines instead would write their credentials to disk in a
    file the journal echoes back. And `PATH` is composed at *start* time rather
    than frozen at install time, because a unit whose `PATH` predates the
    toolchain installed after it is a real defect this repository has already
    paid for (`factory/verify/toolchain.py`).

    082-US2 gives it two optional arguments rather than a second wrapper per
    deployment: a versioned instance passes the frozen checkout and that
    checkout's own interpreter, and everything else — the `PATH` composition
    and the environment command above all — stays in the one script the
    operator installed. A per-deployment copy would have forked the credential
    path five ways, which is the shape this indirection exists to prevent.
    """
    environment = (
        f'eval "$({layout.env_command})"\n' if layout.env_command else ""
    )
    return f"""\
#!/bin/sh
# Generated by `ergane worker install`. Edit the engine, not this file:
# uninstall removes it only while it still matches what install wrote.
#
# Usage: {WRAPPER_NAME} <module> [<root> <interpreter>]
# The two optional arguments are 082-US2's versioned instances: they run a
# frozen checkout with that checkout's own venv. Absent, this is exactly the
# installation the wrapper was written for.
set -eu
cd "${{2:-{layout.install_root}}}"
PATH="$HOME/.local/bin:$PATH"
export PATH
{environment}exec "${{3:-{layout.interpreter}}}" -m "$1"
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
    """What was removed, what was deactivated, and what was deliberately not.

    Deletion and deactivation are different acts with different failure modes:
    systemd holds the parsed unit in memory, so a unit file can be gone while
    the unit itself is still loaded and active. `removed 6 file(s)` reported
    both as one word and neither by name, which is why the surviving
    `ergane.slice` was found by `systemctl --user list-units 'ergane*'` rather
    than by reading the report (FR-005, FR-006).

    The three tuples are per-act rather than per-name because that is how the
    acts happen — a loop over the enabled units, one stop of the slice, a loop
    over the generated files — and `render` recombines them by name for the
    operator, who reads by name.
    """

    removed: tuple[str, ...]
    kept: tuple[str, ...]
    stopped: tuple[str, ...] = ()
    disabled: tuple[str, ...] = ()

    @property
    def acted_on(self) -> tuple[str, ...]:
        """Every name teardown touched, in the order it first touched it."""
        ordered: list[str] = []
        for name in self.stopped + self.disabled + self.removed:
            if name not in ordered:
                ordered.append(name)
        return tuple(ordered)

    def acts(self, name: str) -> tuple[str, ...]:
        """Which of stop, disable and remove `name` received, in that order."""
        return tuple(
            act
            for act, names in (
                ("stopped", self.stopped),
                ("disabled", self.disabled),
                ("removed", self.removed),
            )
            if name in names
        )

    def render(self) -> str:
        lines = [f"  {name}: {', '.join(self.acts(name))}" for name in self.acted_on]
        # An empty teardown still has to say so. `removed 0 file(s)` at least
        # printed something, and replacing it with a blank line would trade one
        # unreadable report for a silent one.
        lines.insert(
            0,
            "uninstalled:"
            if lines
            else "uninstalled nothing: no file this engine wrote is still here",
        )
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
    stopped: list[str] = []
    disabled: list[str] = []
    for name in ENABLE_TARGETS:
        if name in recorded:
            # Before deleting: systemd holds the parsed unit in memory, and a
            # file removed out from under a running unit leaves it up and
            # invisible to `disable` until the next reboot.
            runner(("systemctl", "--user", "disable", "--now", name))
            # `--now` is two acts in one command, and the report names both:
            # a unit can be disabled and still loaded, and the operator who
            # has to tell those apart is the one this verb is for (FR-006).
            stopped.append(name)
            disabled.append(name)

    if SLICE_UNIT in recorded:
        # Nothing is `WantedBy` the slice — it is pulled in by the `Slice=`
        # lines of the units just stopped, which is why it is deliberately not
        # in ENABLE_TARGETS and why the disable loop above never reaches it.
        # So it survives its own members as loaded and active, holding the
        # cgroup open, until it is stopped by name. That hand-run stop is this
        # line (FR-007). It goes after the disables because a slice cannot be
        # stopped out from under a running member, and before the removals for
        # the same reason the disables are.
        runner(("systemctl", "--user", "stop", SLICE_UNIT))
        stopped.append(SLICE_UNIT)

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
    return UninstallReport(
        removed=tuple(removed),
        kept=tuple(kept),
        stopped=tuple(stopped),
        disabled=tuple(disabled),
    )


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
