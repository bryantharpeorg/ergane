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
from typing import TYPE_CHECKING, Callable, Mapping, Sequence

from factory.cli.errors import OperatorError
from factory.controlplane.config import (
    KNOWN_TEMPORAL_MODES,
    ControlPlaneConfigError,
    load_controlplane_config,
    resolve_config_path,
)
from factory.registry import resolve_state_home

if TYPE_CHECKING:  # pragma: no cover - `factory.versioning` imports temporalio,
    # and this module is imported by the probe, which is the process that runs
    # when Temporal is the thing that died. The name is needed for a signature;
    # the import is not needed at runtime.
    from factory.versioning import OpenEpic

SLICE_UNIT = "ergane.slice"

#: The unversioned worker, retired by 082-US4 (FR-006). The engine no longer
#: generates it: an in-place restart is how an epic finished on code it did not
#: start with. The name survives for the two things still owed to a host that
#: has one — teardown removes it under the same provenance rule as everything
#: else, and `ergane worker migrate` retires it on its own once nothing that
#: predates versioning is still open (FR-007).
LEGACY_WORKER_UNIT = "ergane-worker.service"

#: 082-US2: the versioned worker, one instance per deployed build id — a
#: template because the only thing two versions differ in is the checkout they
#: run from, which `%i` already spells. Since US4 this is the only worker the
#: engine writes; `ergane worker deploy` is what puts an instance of it on the
#: floor, and every attempt is pinned to the version that started it.
WORKER_TEMPLATE_UNIT = "ergane-worker@.service"

BRIDGE_UNIT = "ergane-bridge.service"
TEMPORAL_UNIT = "ergane-temporal.service"
PROBE_UNIT = "ergane-probe.service"
PROBE_TIMER = "ergane-probe.timer"

#: The mode that installs and supervises a Temporal server of its own; the other
#: mode, external, connects to one the operator runs. Which spellings are *legal*
#: is `KNOWN_TEMPORAL_MODES`, taken from the parser that owns the declaration
#: rather than listed a second time here, so a mode `temporal.mode` admits and a
#: mode this module acts on cannot drift apart.
MANAGED_TEMPORAL_MODE = "managed"

#: What a layout carries when nobody told it (119-US1, FR-003). Not a mode: it
#: is refused wherever the mode decides an outcome. The value it replaced was
#: `"external"`, and that default is the whole reason this spec exists — an
#: installation that declared `managed` was read as external, and external mode
#: fails by not finding a server, which is indistinguishable from the operator's
#: own Temporal being down. Three patches went past it.
UNDECLARED_TEMPORAL_MODE = "undeclared"

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
#: TEMPORAL_UNIT is in the tuple and is still not enabled on an external
#: installation, because `install` enables only the names it actually *wrote*
#: — and generation is what the mode decides (`_temporal_managed`). The comment
#: that stood here said the opposite, that the name was "deliberately not in
#: this tuple"; it was, and correcting the prose beside the code it describes is
#: the same lesson 119 learned one function below (FR-004).
#:
#: 082-US4: no worker is among them any more. A template cannot be enabled —
#: only instances of it can — so the worker leaves this tuple and
#: `ergane worker deploy` enables the instance that serves a version. An install
#: therefore brings up no worker at all, which is why `InstallReport` says so.
ENABLE_TARGETS = (BRIDGE_UNIT, TEMPORAL_UNIT, PROBE_TIMER)

#: Names this engine wrote once and no longer generates. Their provenance is
#: carried forward across an install (`_carried_provenance`) so teardown and the
#: migration can still prove a file on disk is the engine's rather than the
#: operator's own.
RETIRED_UNITS = (LEGACY_WORKER_UNIT,)

_MODULES = {
    WORKER_TEMPLATE_UNIT: "factory.worker",
    BRIDGE_UNIT: "factory.notify.service",
    PROBE_UNIT: "factory.supervision.probe",
}

#: Where a deployed version's frozen checkout goes, under the supervision home
#: and therefore outside the operator's own checkout (082 plan trap 2).
DEPLOYMENTS_DIRNAME = "deployments"

#: The subdirectory of a deployment that git owns — the checkout is *inside*
#: the deployment directory rather than being it, so `git worktree remove` has
#: one path and the reaper never `rm`s a tree git still tracks (trap 3).
DEPLOYMENT_TREE_DIRNAME = "tree"


def worker_instance(build_id: str) -> str:
    """The unit name serving one deployed build id."""
    return f"ergane-worker@{build_id}.service"


def instance_build_id(unit: str) -> str:
    """The build id `unit` serves — the inverse of `worker_instance`."""
    return unit.removeprefix("ergane-worker@").removesuffix(".service")


def deployed_instances(layout: InstallLayout) -> tuple[str, ...]:
    """Every versioned worker unit this host has on the floor (082-US4).

    Read from the frozen checkouts rather than from systemd, because those are
    what the engine created and therefore what its provenance rules can speak
    about: deploy makes the directory before it enables the instance, and a reap
    removes both. An instance has no file of its own, so the disable is the
    whole of what teardown owes it. No deployments directory is a floor before
    its first deploy — a state, not an error.
    """
    try:
        return tuple(
            worker_instance(entry.name)
            for entry in sorted(layout.deployments_dir.iterdir())
            if entry.is_dir()
        )
    except OSError:
        return ()


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

    #: Which Temporal the installation runs against, and therefore whether the
    #: server unit is generated. It has no usable default — a layout built
    #: without one carries `UNDECLARED_TEMPORAL_MODE` and is refused at
    #: generation rather than read as external (FR-003).
    temporal_mode: str = UNDECLARED_TEMPORAL_MODE

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

        Named in `roots` though it is under `generated_dir`: the portability
        scan reads that tuple, not the directory hierarchy."""
        return self.generated_dir / DEPLOYMENTS_DIRNAME

    def deployment_tree(self, build_id: str) -> Path:
        """The frozen checkout one deployed version runs from."""
        return self.deployments_dir / build_id / DEPLOYMENT_TREE_DIRNAME

    def deployment_interpreter(self, build_id: str) -> Path:
        """That checkout's own venv python — spelled `python3` for the reason
        `_python3_spelling` exists: a deployment whose command line reads
        `python -m factory.worker` is one an agent's sweep can kill."""
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
    temporal_mode: str | None = None,
) -> InstallLayout:
    """Resolve where this installation actually is.

    `install_root` defaults to the directory holding the `factory` package,
    which is the repository root in a checkout and `site-packages` in a wheel —
    either way it is *this* installation and never a literal.

    `temporal_mode` arrives the way every other parameter here does: passed in
    by the caller that read the declaration (`declared_temporal_mode`). This
    function resolves from the filesystem and its arguments and reads no
    configuration, which is what keeps it testable without a config loader and
    keeps supervision uncoupled from the control plane. Omitting it does not
    mean external — it means undeclared, and an undeclared layout is refused
    where the mode decides an outcome (`_temporal_managed`).
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
        temporal_mode=_checked_temporal_mode(temporal_mode),
    )


def _checked_temporal_mode(mode: str | None) -> str:
    """The mode a layout may carry: one this engine installs, or undeclared.

    A value that is neither is refused here, where it was passed, rather than
    carried into generation and read as "not managed" — the failure of a
    mis-spelled mode should name the spelling, not present as a missing server.
    """
    if mode is None:
        return UNDECLARED_TEMPORAL_MODE
    if mode not in KNOWN_TEMPORAL_MODES:
        raise OperatorError(
            f"{mode!r} is not a Temporal mode this engine can install; "
            f"`temporal.mode` is one of {', '.join(KNOWN_TEMPORAL_MODES)}"
        )
    return mode


def declared_temporal_mode(config_path: Path | str | None = None) -> str:
    """The Temporal mode this installation declares, or a refusal naming the file.

    The other half of `resolve_layout`'s `temporal_mode`: the resolver takes the
    mode, and this is the caller's read of where the mode is declared. Kept out
    of the resolver deliberately (plan trap 2) — a config read in there would
    couple supervision to the control-plane parser and make the resolver
    untestable without one.

    An installation whose declaration cannot be read is refused, naming the file
    and the key, and never quietly treated as external (FR-003): the operator
    who mis-declares a mode learns at install time rather than after three
    patches. Constitution IX — the value that decides whether a server is
    installed is read from the declaration that owns it, or refused by name.
    """
    path = Path(config_path) if config_path is not None else resolve_config_path()
    try:
        return load_controlplane_config(path).temporal.mode
    except ControlPlaneConfigError as error:
        raise OperatorError(
            f"the Temporal mode this installation declares could not be read "
            f"from {path}: {error.problem}. `temporal.mode` decides whether the "
            "engine installs and supervises a Temporal server of its own, so "
            "this verb refuses rather than guessing a mode for you"
        ) from error


def declared_layout(
    *, config_path: Path | str | None = None, **overrides: Path | str | None
) -> InstallLayout:
    """The layout of the installation as declared — what every generating verb uses.

    The one composition of the two halves above, so that "read the declaration,
    then resolve" is spelled once and every verb that writes units gets the same
    refusal. `overrides` are `resolve_layout`'s own parameters, forwarded.
    """
    return resolve_layout(
        temporal_mode=declared_temporal_mode(config_path), **overrides
    )


def removal_layout(
    *, config_path: Path | str | None = None, **overrides: Path | str | None
) -> InstallLayout:
    """The layout a verb that only *removes* files resolves.

    Removal is the one verb that has to keep working on the installation whose
    declaration is broken — that installation is the reason this spec exists —
    so an unreadable declaration widens the candidate list to managed here
    instead of refusing. Widening is safe where a silent default is not: these
    verbs only ever *offer* names, and a name leaves only if the file is on disk
    and its recorded digest is this engine's (`_is_someone_elses`), so naming a
    unit that was never written removes nothing. Nothing is generated from this
    layout, and nothing is dialled to build it.
    """
    try:
        mode = declared_temporal_mode(config_path)
    except OperatorError:
        mode = MANAGED_TEMPORAL_MODE
    return resolve_layout(temporal_mode=mode, **overrides)


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

    True exactly when the layout carries `temporal_mode == "managed"`, and a
    layout carries the mode it was resolved with: `declared_temporal_mode` reads
    `temporal.mode` out of the operator's control-plane config and the verb
    hands it to `resolve_layout`, which never reads it itself.

    A layout nobody declared a mode for is refused here rather than read as
    external. That refusal is the story of 119: the predicate this docstring
    used to describe did not exist — no caller passed a mode, so every
    installation took the dataclass default and a declared `managed` produced no
    server, while external mode's failure looked like the operator's own
    Temporal being down. Three patches went past it, one of them past this
    docstring. `tests/test_119_declared_mode.py` asserts each claim above as
    behaviour, so the two cannot drift again (FR-004).
    """
    if layout.temporal_mode not in KNOWN_TEMPORAL_MODES:
        raise OperatorError(
            "this layout carries no declared Temporal mode "
            f"({layout.temporal_mode!r}), so whether the managed server unit "
            "belongs in it has no answer: resolve it with the mode the "
            "installation declares at `temporal.mode` in its control-plane "
            "config (`declared_temporal_mode`). Reading an undeclared mode as "
            "external is the silent default this refusal replaces — it hides a "
            "missing server behind what looks like the operator's Temporal "
            "being down"
        )
    return layout.temporal_mode == MANAGED_TEMPORAL_MODE


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
        GeneratedFile(WORKER_TEMPLATE_UNIT, _worker_template_text(layout), units),
        GeneratedFile(BRIDGE_UNIT, _bridge_text(layout), units),
        GeneratedFile(PROBE_UNIT, _probe_text(layout), units),
        GeneratedFile(PROBE_TIMER, _timer_text(layout), units),
        GeneratedFile(WRAPPER_NAME, _wrapper_text(layout), generated, 0o755),
    ]
    if _temporal_managed(layout):
        files.insert(
            3, GeneratedFile(TEMPORAL_UNIT, _temporal_text(layout), units)
        )
    return tuple(files)


def _retired_candidates(layout: InstallLayout) -> tuple[GeneratedFile, ...]:
    """The files the engine no longer writes but may still have to remove.

    Their text is deliberately empty and never read: provenance is the recorded
    digest compared against the file on disk (`_is_someone_elses`), which is the
    only rule that can speak about a name whose text is no longer generated.
    """
    return tuple(
        GeneratedFile(name, "", layout.unit_dir) for name in RETIRED_UNITS
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


def _temporal_ordering(layout: InstallLayout) -> str:
    """The ordering dependency a managed installation's services carry (119-US3).

    Empty in external mode, where `ergane-temporal.service` is not written and a
    unit ordering itself after a name systemd cannot resolve would be a defect on
    the path this spec does not touch.

    Which pair, and why, is stated in the generated unit itself rather than only
    here (FR-008, plan trap 5): the operator reading the installed file is the
    person who needs it, and a comment in the generator reaches only someone who
    has the checkout.
    """
    if not _temporal_managed(layout):
        return ""
    return f"""\
# 119-US3 (FR-008): this installation runs its own Temporal server, and this
# unit talks to it. Both directives, because each alone leaves the failure they
# were added for — `After=` orders without pulling the server in, `Wants=` pulls
# it in without waiting for it, and either way this unit starts against a socket
# nobody is listening on yet and burns its start limit (StartLimitBurst above)
# before the server is up. `Requires=` is deliberately not the pair used: it
# would stop this unit whenever the server stops, and a worker that dies with
# its dependency is worse than one that reconnects to it.
Wants={TEMPORAL_UNIT}
After={TEMPORAL_UNIT}
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

    082-US2's template runs the *deployment's* code rather than this
    installation's and must tell the worker which build id it is; everything
    else — slice, kill semantics, restart bound — stays identical by
    construction rather than by two texts agreeing.

    119-US3 adds the fourth thing both services share: on a managed
    installation each is ordered after the Temporal unit
    (`_temporal_ordering`), because the server they connect to is one this
    engine starts.
    """
    settings = "".join(f"Environment={value}\n" for value in environment)
    return f"""\
[Unit]
Description={description}
# Give up rather than flap: a restart loop during a memory storm deepens it.
StartLimitIntervalSec={layout.restart_window_s}
StartLimitBurst={layout.restart_burst}
{_temporal_ordering(layout)}
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


def _worker_template_text(layout: InstallLayout) -> str:
    """082-US2 (FR-003): one instance per deployed version, `%i` = the build id.

    Three deliberate things, each a trap the plan numbers. **The instance runs
    the deployment's code, not this installation's** (trap 4): working directory
    and interpreter both come out of the frozen checkout, and a template that
    versioned the unit *name* while still executing `install_root` would have
    versioned nothing. The wrapper is still what is exec'd, so the operator's
    environment command keeps being evaluated from a script rather than resolved
    into `Environment=` lines the journal echoes back. **The build id is passed,
    not derived** — `%i` is the directory deploy created, so a restart in place
    re-registers the same version rather than minting one (trap 8). **The
    instance is in the slice**, because a deploy that escaped the containment
    would reintroduce the 2026-08-11 leak one version at a time.
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
    #
    # 119-US3: this is the one unit that passes arguments, so it is the one that
    # has to spell out the wrapper's other two positionals — the working
    # directory and the interpreter — before its own flags. Without them `cd`
    # receives `--db-filename` and the unit dies with
    # `ergane-run.sh: cd: Illegal option --` before the server opens a socket.
    # They are the values the wrapper would have defaulted to; naming them is
    # the price of the contract that lets a deployment override them
    # (`_wrapper_text`, 082-US2).
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
ExecStart={layout.wrapper} factory.supervision.temporal_server {layout.install_root} {layout.interpreter} --db-filename {db_path} --namespace ergane --log-level warn

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
    checkout's own interpreter, and everything else — the `PATH` composition and
    the environment command above all — stays in the one script the operator
    installed. A per-deployment copy would have forked the credential path five
    ways, which is the shape this indirection exists to prevent.

    119-US2 (FR-005): everything after those three is the module's own argument
    list. It used to be discarded — the script ended in `-m "$1"` — so the
    Temporal unit's `--db-filename`, `--namespace` and `--log-level` reached the
    server as nothing at all. The fix is not `-m "$@"`, which would hand the
    module the working directory and the interpreter as its first two flags
    (plan trap 1): the three positionals are captured and *consumed*, and `"$@"`
    is what is left. A unit that passes arguments therefore passes all three
    positionals first, spelling out the defaults it does not mean to override —
    the contract the usage line below states.

    The two `if` blocks are load-bearing under `set -eu`. `shift 3` fails when
    fewer than three arguments were given, and the compact `[ "$#" -gt 0 ] &&
    shift` is a statement whose own exit status is the test's, so the shell exits
    on the run where there is nothing left to shift — the module-name-alone path
    every unit but one takes.
    """
    environment = (
        f'eval "$({layout.env_command})"\n' if layout.env_command else ""
    )
    return f"""\
#!/bin/sh
# Generated by `ergane worker install`. Edit the engine, not this file:
# uninstall removes it only while it still matches what install wrote.
#
# Usage: {WRAPPER_NAME} <module> [<root> [<interpreter> [<argument>...]]]
# The two optional positionals are 082-US2's versioned instances: they run a
# frozen checkout with that checkout's own venv. Absent, this is exactly the
# installation the wrapper was written for. Everything after them is the
# module's own argument list, so a unit that passes arguments passes the root
# and the interpreter first, even where it means the defaults.
set -eu
module="$1"
shift
root="${{1:-{layout.install_root}}}"
if [ "$#" -gt 0 ]; then shift; fi
interpreter="${{1:-{layout.interpreter}}}"
if [ "$#" -gt 0 ]; then shift; fi

cd "$root"
PATH="$HOME/.local/bin:$PATH"
export PATH
{environment}exec "$interpreter" -m "$module" "$@"
"""


@dataclasses.dataclass(frozen=True)
class InstallReport:
    """What was written, what was left alone, and what came up."""

    written: tuple[str, ...]
    kept: tuple[str, ...]
    active: tuple[str, ...]
    enabled: tuple[str, ...]
    linger: bool
    #: 082-US4: units an earlier install wrote and this one no longer does,
    #: still on disk. Named because an operator who is never told the retired
    #: worker is still there never runs the verb that removes it.
    retired: tuple[str, ...] = ()
    #: 119-US3 (FR-010): every service this install started, paired with the
    #: state systemd reports for it — `active`, `failed`, `activating`, or
    #: whatever else the session says. Pairs rather than a set of names, because
    #: the report this replaced listed only the units that were up: three
    #: services enabled, died, and were absent from the report entirely, leaving
    #: an operator reading a green-looking probe timer over a broken stack.
    states: tuple[tuple[str, str], ...] = ()

    def render(self) -> str:
        lines = [f"wrote {len(self.written)} file(s) to the unit directory"]
        # Every started service, whatever its state — a report that named only
        # what came up is the one this replaced (FR-010, plan trap 8).
        lines += [
            f"  {name}: {state or 'unknown'}"
            f"{'' if name in self.enabled else ', not enabled'}"
            for name, state in self.states
        ]
        if not self.linger:
            lines.append("  WARN: linger is off; user units stop at logout")
        lines += [f"  left alone (not written by ergane): {n}" for n in self.kept]
        # No worker is enabled here any more (ENABLE_TARGETS): the floor gets
        # one when a version is deployed onto it, and an install that said
        # nothing would read as a supervised host with no worker on it.
        lines.append(
            "  the worker is versioned: `ergane worker deploy` puts one on the floor"
        )
        lines += [
            f"  retired, still installed: {name} — `ergane worker migrate` removes it"
            for name in self.retired
        ]
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
    #: 119-US3 (FR-011): why the in-flight-epic check could not be made, when it
    #: could not. Empty on the ordinary path. The removal proceeds either way —
    #: the verb that removes the units may not depend on the service those units
    #: run — but an operator told nothing would read an all-clear into a check
    #: that never happened.
    epics_unknown: str = ""

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
        if self.epics_unknown:
            lines.append(
                "  WARN: could not ask Temporal which epics are open "
                f"({self.epics_unknown}); removed the units anyway — an epic in "
                "flight was not ruled out"
            )
        lines += [f"  left in place (not written by ergane): {n}" for n in self.kept]
        return "\n".join(lines)


@dataclasses.dataclass(frozen=True)
class RetirementReport(UninstallReport):
    """What `ergane worker migrate` retired (082-US4, FR-007).

    Teardown's report shape exactly — the same acts, read the same way — with
    its own headline, because "uninstalled" is what this verb is careful *not*
    to do: everything else install wrote stays where it is.
    """

    def render(self) -> str:
        lines = [f"  {name}: {', '.join(self.acts(name))}" for name in self.acted_on]
        lines.insert(
            0,
            "retired the unversioned worker unit:"
            if lines
            else "nothing to retire: no unversioned worker unit is installed here",
        )
        lines += [f"  left in place (not written by ergane): {n}" for n in self.kept]
        return "\n".join(lines)


def install(
    layout: InstallLayout,
    *,
    run: Callable[[Sequence[str]], CommandResult] | None = None,
) -> InstallReport:
    """Write the units, enable them, enable linger, and report every service.

    A file the engine did not write is never overwritten — that is the half of
    the collision that cannot be undone.

    119-US3: the report names each service it started and the state systemd
    gives it, and a managed installation gets the directory its server's
    database lives in before the unit that needs it is enabled.
    """
    runner = _run_command if run is None else run
    layout.unit_dir.mkdir(parents=True, exist_ok=True)
    layout.generated_dir.mkdir(parents=True, exist_ok=True)
    if _temporal_managed(layout):
        # FR-007. The dev server stats its database file's *parent* and refuses
        # to create it — `failed checking dir for database file` — so on a host
        # whose state directory is fresh the unit dies on its first start. The
        # server module makes it too, for the path where the file is named
        # without this verb; making it here means the directory exists before
        # the enable below starts anything.
        layout.temporal_db_path.parent.mkdir(parents=True, exist_ok=True)

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
    carried = _carried_provenance(layout, recorded)
    _write_manifest(layout, {**carried, **fresh})

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
        retired=tuple(carried),
        states=_states(runner, tuple(n for n in ENABLE_TARGETS if n in written)),
    )


def _states(
    runner: Callable[[Sequence[str]], CommandResult], names: Sequence[str]
) -> tuple[tuple[str, str], ...]:
    """What systemd says each of `names` is, in `names`' order (FR-010).

    The word, not the exit code: `is-active` answers 3 for both `inactive` and
    `failed`, and those send an operator to two different places. A unit the
    session has never heard of prints nothing at all, and that name is still
    reported — a service started and unaccounted for is the defect, not the
    remedy.
    """
    return tuple(
        (name, runner(("systemctl", "--user", "is-active", name)).out)
        for name in names
    )


def _carried_provenance(
    layout: InstallLayout, recorded: Mapping[str, str]
) -> dict[str, str]:
    """The provenance of what this engine wrote once and writes no longer.

    The trap in retiring a generated file (082-US4): install rewrites the
    manifest from what it just wrote, so a retired name falls out of it on the
    next install — and the file is still on the host with nothing left to prove
    it is the engine's, which teardown and the migration must then keep forever.
    """
    return {
        name: recorded[name]
        for name in RETIRED_UNITS
        if name in recorded and (layout.unit_dir / name).exists()
    }


def uninstall(
    layout: InstallLayout,
    *,
    run: Callable[[Sequence[str]], CommandResult] | None = None,
    open_epics: Callable[[], Sequence[str]] | None = None,
) -> UninstallReport:
    """Remove exactly the files install wrote, and report the rest (FR-008).

    The epic read comes first and touches nothing: a disable issued before the
    refusal is a half-uninstall, which is worse than either outcome.

    119-US3 (FR-011, plan trap 6): that read no longer decides whether the
    removal happens. It dialled Temporal, so a host whose Temporal never came up
    could not be cleaned up — and a host whose Temporal never came up is exactly
    the state this spec exists to describe, so the one verb an operator needed
    there was the one that depended on the service its own units run. The check
    is kept where it can be made, because an open epic is a real thing to strand
    (082's FR-012); where it cannot, the failure is reported and the units come
    off. Nothing below this line reaches the network.
    """
    epics: tuple[str, ...] = ()
    epics_unknown = ""
    try:
        epics = tuple((_open_epic_ids if open_epics is None else open_epics)())
    except OperatorError:
        # A refusal the read itself decided on — not an unreachable server —
        # stays a refusal: it is an answer, and this branch is for the absence
        # of one.
        raise
    except Exception as unreachable:
        epics_unknown = f"{type(unreachable).__name__}: {unreachable}"
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

    # 082-US4/US4-S3: the versioned instances, which are the workers on this
    # floor. They are in the slice, so they are disabled here — before the stop
    # below, for the same reason every other member is.
    for instance in deployed_instances(layout):
        runner(("systemctl", "--user", "disable", "--now", instance))
        stopped.append(instance)
        disabled.append(instance)

    if LEGACY_WORKER_UNIT in recorded:
        # The unit this engine wrote before 082-US4 retired it. Recorded means
        # an install of ours put it there; the same `in recorded` guard the
        # loop above uses, on a name that loop no longer names.
        runner(("systemctl", "--user", "disable", "--now", LEGACY_WORKER_UNIT))
        stopped.append(LEGACY_WORKER_UNIT)
        disabled.append(LEGACY_WORKER_UNIT)

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
    for generated in generated_files(layout) + _retired_candidates(layout):
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
        epics_unknown=epics_unknown,
    )


def migrate_off_legacy_unit(
    layout: InstallLayout,
    *,
    run: Callable[[Sequence[str]], CommandResult] | None = None,
    open_epics: Callable[[], Sequence["OpenEpic"]] | None = None,
) -> RetirementReport:
    """Retire the unversioned worker unit, once nothing predates versioning.

    FR-007, and the refusal is the story. `disable --now` on that unit takes its
    whole cgroup with it — `KillMode=control-group`, which is the point — so an
    epic still being served by it loses the attempt and the agent inside it. And
    what survives is not stranded but *adopted*: T002's probe measured an
    unversioned run being served by the versioned worker that became current and
    pinning there, which is an epic finishing on code it did not start with. So
    while one is open the removal is refused, by name.

    The other three properties are teardown's, deliberately: the epics are read
    before anything is touched (a half-migration has no inverse verb), the file
    is removed only while it matches what install once wrote, and re-running is
    free — with nothing left to retire the server is never asked.
    """
    recorded = _read_manifest(layout)
    on_disk = (layout.unit_dir / LEGACY_WORKER_UNIT).exists()
    if not on_disk and LEGACY_WORKER_UNIT not in recorded:
        return RetirementReport(removed=(), kept=())

    # Imported here, like every other name that reaches Temporal from this
    # module: the probe imports it, and runs when Temporal is what died.
    from factory.versioning import strandable_epics

    stranded = strandable_epics(
        tuple((_open_epics if open_epics is None else open_epics)())
    )
    if stranded:
        raise OperatorError(
            f"refusing to remove {LEGACY_WORKER_UNIT} while {', '.join(stranded)} "
            "predates versioning: it carries no deployment version, so stopping "
            "that unit takes the agents it is running down with its cgroup, and "
            "whatever survives is adopted onto whichever version is current at "
            "its next workflow task — an epic finishing on code it did not start "
            "with. Let it land, or kill it, then run this again"
        )

    runner = _run_command if run is None else run
    stopped: list[str] = []
    disabled: list[str] = []
    if LEGACY_WORKER_UNIT in recorded:
        # Before deleting, always: systemd holds the parsed unit in memory, and
        # a file removed out from under a running unit leaves it up and
        # invisible to `disable` until the next boot.
        runner(("systemctl", "--user", "disable", "--now", LEGACY_WORKER_UNIT))
        stopped.append(LEGACY_WORKER_UNIT)
        disabled.append(LEGACY_WORKER_UNIT)

    removed: list[str] = []
    kept: list[str] = []
    for candidate in _retired_candidates(layout):
        if not candidate.path.exists():
            continue
        if _is_someone_elses(candidate, recorded):
            kept.append(candidate.name)
            continue
        candidate.path.unlink()
        removed.append(candidate.name)

    _write_manifest(
        layout,
        {
            name: digest
            for name, digest in recorded.items()
            if name not in RETIRED_UNITS or (layout.unit_dir / name).exists()
        },
    )
    runner(("systemctl", "--user", "daemon-reload"))
    return RetirementReport(
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


def _open_epics() -> tuple["OpenEpic", ...]:
    """Every open epic, with what the server says it is versioned as.

    Imported inside the function on purpose, and it stays that way: the probe
    imports this module for the unit names, and it is the process that runs when
    Temporal is the thing that died. A module-scope Temporal import here would
    put a client on that path for the sake of a read the probe never performs.
    The query is the roadmap's own, so a closed epic is narrowed away on the
    server rather than here. One query serves both refusals — teardown's
    (FR-012, ids only) and the migration's (which needs the versioning info) —
    because two reads of one fact are two answers waiting to disagree.
    """
    import asyncio

    from factory.activities.roadmap_activities import _OPEN_EPIC_STATUS
    from factory.cli.nouns import _open_client
    from factory.cli.status import EPIC_ID_PREFIX
    from factory.versioning import open_epic_from

    async def listed() -> tuple["OpenEpic", ...]:
        client = await _open_client()
        found = [
            open_epic_from(execution)
            async for execution in client.list_workflows(
                f'ExecutionStatus = "{_OPEN_EPIC_STATUS}"'
            )
            if str(execution.id).startswith(EPIC_ID_PREFIX)
        ]
        return tuple(sorted(found, key=lambda epic: epic.epic_id))

    return asyncio.run(listed())


def _open_epic_ids() -> tuple[str, ...]:
    """Which epics are open right now — FR-012's refusal, as a read."""
    return tuple(epic.epic_id for epic in _open_epics())
