"""Implementation of `ergane uninstall` — teardown as one verb that owns its order.

Taking Ergane off a host was four hand-ordered steps, discoverable only by
`--help` spelunking: pause dispatch, forget every repository, stop and remove the
units, and only then clear what is left. The ordering is knowledge the tool has
and the operator had to reconstruct, so this module holds it once, as data.

**The step table is the whole design** (FR-009). `STEPS` is an ordered tuple of
`Step` records, each carrying a **survey** half that only reads and a **perform**
half that acts. `--check` calls surveys and never reaches a perform; a real run
calls survey then perform. Both read the same tuple, which is what stops the
printed plan and the performed sequence from diverging — and it is what makes
`--check` conclusive: the acting half is unreachable on that path, so a
substituted recording table that stays empty is the whole proof, with no Temporal
fake, no systemd fake and no filesystem fake needed to believe it (FR-010).

**The three steps are called as they stand** (083 plan, "The ruling on
composition"). Each `perform` builds the `argparse.Namespace` that step's command
already expects and calls the existing entry point — `roadmap_pause_command`
through `asyncio.run`, in the shape `factory/cli/roadmap.py` already uses for
argparse; `repo_forget_command`; `uninstall()` with the `run` and `open_epics`
parameters it already has. Nothing beneath teardown is reshaped to suit it, and
no seam is added to `factory/cli/roadmap.py`: teardown's own table is the seam,
so this story and 085's rewrite of that file cannot collide at landing.

**104-US7 added a sixth, and it is called as it stands too.** The engine
container comes down through `container_engine.compose_argv` and teardown's own
`run` seam, and its generated project is removed through
`container_manifest.remove_project` — provenance by digest, so what goes is
exactly what `ergane install` wrote and nothing beside it. Neither module gains
a function for this. The step sits third (104 plan, R9), which renumbers every
step after it in the printed plan and in `_stop`'s "step N of M": the names are
constants precisely so that the numbers can move.

**What teardown keeps is a judgement it does not make for the operator** (US4).
State is cheap to recreate and credentials are not, so the last two steps have
opposite defaults: `--purge` empties Ergane's state home and the lock siblings
`factory/locking.py` never unlinks, while the control-plane config and the
secrets beside it are kept on every path there is. Both facts are reported the
same way — one labelled line per path, kept and removed together in one block,
so the two are told apart by their label rather than by one of them being
absent (FR-013). The git refs an epic leaves behind are counted and named but
never removed without `--scrub-refs`, and teardown prints the two `for-each-ref`
incantations it used rather than pointing at `ergane build salvage`, which loads
a compiled graph and answers a different question (FR-015).

Two refusals are teardown's own, taken before the commands are:

- **Dispatch that cannot be paused because no owner can be named is a refusal,
  not a skipped step** (FR-012). `roadmap_pause_command` reports success when it
  signalled a run whose schedule it could not establish — its own docstring says
  so, with the caveat on stderr rather than in the output the operator asked for.
  Reading that as a paused floor is how a schedule goes on dispatching into a
  host being dismantled, so the survey resolves the owner first and stops here
  rather than signalling.
- **No step may remove the installation this process is running from** (FR-018).
  `resolve_layout()` already derives both paths that *are* this installation, by
  construction rather than by literal: the install root and the interpreter. One
  containment test against them, before any step acts, with no flag to override
  it. This *bounds* teardown; it does not close
  `install/restarting-the-worker-deletes-the-operator-cli`.

**Skills have one narrow state-purge exception.** Their ownership manifest is read
before the skill step acts. Exact digest matches and declared aliases are removed;
modified files and retargeted aliases are kept, and the manifest is rewritten to
explain only those kept paths. When that record survives, the later state step
removes its sibling state but not the manifest or its parent directories. A
missing manifest, an empty one, or one whose kept entries are all gone returns
the step to the ordinary purge contract.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import os
import shutil
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterable, NoReturn, Sequence

from temporalio.service import RPCError

from factory import registry
from factory.cli.skills import (
    ManifestError,
    perform_skills_teardown,
    survey_skills_teardown,
)
from factory.cli.errors import EXIT_OK, EXIT_TRANSPORT, EXIT_USER, OperatorError
from factory.cli.nouns import _open_client
from factory.cli.repo import repo_forget_command
from factory.cli.roadmap import roadmap_pause_command
from factory.controlplane.config import resolve_config_path
from factory.env import ERGANE_STATE_HOME_ENV, FACTORY_STATE_HOME_ENV
from factory.locking import lock_path_for
from factory.roadmap.discovery import RoadmapLocation, RoadmapOwner, resolve_roadmap
from factory.roadmap.schedule import SPECS_DIR_NAME

# `compose_argv` builds the argv; `_run_compose` is the default runner behind
# teardown's own `run` seam. Imported rather than re-implemented, and imported
# rather than *added to*: `container_engine`'s docstring says plainly that
# nothing in it ever takes the engine down, because bring-up deliberately leaves
# a failed engine running to be diagnosed and `down` is this verb's. The
# underscore is privacy by convention, the way `container_manifest.py` imports
# `units._digest` — one implementation of one act beats two that can disagree.
from factory.supervision.container_engine import _run_compose, compose_argv
from factory.supervision.container_manifest import (
    RemovalReport,
    installed_project,
    remove_project,
)
from factory.supervision.container_project import project_dir
from factory.supervision.units import (
    CommandResult,
    InstallLayout,
    generated_files,
    removal_layout,
    uninstall as uninstall_units,
)
from factory.verify.gates import scrubbed_env
from factory.workgraph.worktree import GIT_TIMEOUT_S, SALVAGE_REF_ROOT, branch_name

#: The six step names, in the order the spec declares them. Named constants
#: because the report, the refusals and the tests all say them.
#:
#: 104-US7 inserted the engine container at position three (R9), which renumbers
#: every step after it in the printed plan and in `_stop`'s "step N of M". That
#: is the whole reason the names are constants: the numbers move, the names do
#: not, and an operator reads a step by its name.
PAUSE_DISPATCH = "pause dispatch"
FORGET_REPOSITORIES = "forget repositories"
STOP_ENGINE_CONTAINER = "stop the engine container"
STOP_AND_REMOVE_UNITS = "stop and remove units"
SKILL_TEARDOWN = "skill teardown"
CLEAR_STATE = "clear state"
ACCOUNT_FOR_REFS = "account for git refs"

#: What `--check` promises, in the same voice as `ergane init --check`'s
#: `writes nothing`.
CHECK_PERFORMED_NOTHING = (
    "--check performed none of it: nothing was written, removed, stopped or signalled"
)


@dataclass(frozen=True)
class TeardownRequest:
    """One teardown, and every seam the steps beneath it already had.

    `run` and `open_epics` are passed straight through to `uninstall()`
    (FR-017): they are that function's own parameters, not new ones, and
    carrying them here is how a test drives a real teardown without reaching the
    systemd session this suite runs inside.
    """

    layout: InstallLayout
    check: bool = False
    purge: bool = False
    scrub_refs: bool = False
    lock_timeout: float = registry.DEFAULT_LOCK_TIMEOUT_S
    run: Callable[[Sequence[str]], CommandResult] | None = None
    open_epics: Callable[[], Sequence[str]] | None = None
    #: Every registered repository, read once before step two forgets the
    #: registry that answers the question — step five still has to account for
    #: the refs those repositories carry. `None` means "not read yet";
    #: `run_teardown` fills it in before the loop starts.
    repositories: tuple[Path, ...] | None = None
    #: The skill manifest a prior step kept because modified entries remain.
    #: `None` means no such exception is in force.
    retained_skill_manifest: Path | None = None


@dataclass(frozen=True)
class StepSurvey:
    """What one step would do, answered by reading and nothing else.

    Exactly one of three things: a plan with subjects to act on, a
    `nothing_to_do` that says so by name (FR-011), or a `refusal` that stops the
    verb before the next step acts (FR-012).

    `notes` is what the survey *established* rather than what the step will do,
    and it prints on every path — `--check`, a real run, and a step with nothing
    to do alike. It exists because two of FR-013/FR-015's obligations are facts
    about what teardown is *not* going to touch: a path it keeps, and a ref it
    counts and leaves. Those have no acting half to print them, and a report
    that only speaks when it deletes is the defect this spec closes.
    """

    plan: str
    subjects: tuple[str, ...] = ()
    nothing_to_do: bool = False
    refusal: str | None = None
    notes: tuple[str, ...] = ()
    retained_skill_manifest: Path | None = None


def _removes_nothing(_request: TeardownRequest) -> tuple[Path, ...]:
    """A step that deletes no path of its own — the default."""
    return ()


@dataclass(frozen=True)
class Step:
    """One teardown step: its name, its read-only half, and its acting half.

    `removal_targets` is read by the FR-018 guard *before* the loop starts, so a
    step that would delete this installation is refused before an earlier step
    has acted on anything.
    """

    name: str
    survey: Callable[[TeardownRequest], StepSurvey]
    perform: Callable[[TeardownRequest, StepSurvey], tuple[str, ...]]
    removal_targets: Callable[[TeardownRequest], tuple[Path, ...]] = _removes_nothing


# --- step one: pause dispatch -------------------------------------------------


def _dispatch_roots() -> tuple[Path, ...]:
    """The specs corpora this host dispatches, one per registered repository.

    Derived the same way `factory/roadmap/schedule.py` derives the specs root it
    puts in a schedule, so teardown asks about the roadmap the engine actually
    created rather than one it guessed at.
    """
    try:
        entries = registry.load_registry().entries
    except registry.RegistryError as error:
        raise OperatorError(str(error), code=EXIT_USER) from None
    return tuple(Path(entry.path) / SPECS_DIR_NAME for entry in entries)


def _locate_dispatch(specs_root: Path) -> RoadmapLocation:
    """Who owns dispatch for `specs_root` — a read, and this module's one seam.

    The ladder is `factory.roadmap.discovery`'s own, so teardown and
    `ergane roadmap pause` are answering from the same resolution rather than
    from two.
    """

    async def _read_dispatch() -> RoadmapLocation:
        client = await _open_client()
        try:
            return await resolve_roadmap(client, str(specs_root))
        except RPCError as error:
            raise OperatorError(
                f"cannot read what owns dispatch for {specs_root}: {error}",
                EXIT_TRANSPORT,
            ) from error

    return asyncio.run(_read_dispatch())


def _unowned_refusal(specs_root: Path, location: RoadmapLocation) -> str:
    """FR-012 for the case `roadmap pause` reports as a success (plan trap 7)."""
    return (
        f"dispatch for {specs_root} is run {location.workflow_id}, and no schedule "
        "this client can name owns it. Pausing that run would report success while "
        "the next tick started a fresh one, so teardown will not read it as a "
        "stopped floor: stop whatever schedules that run, then re-run "
        "`ergane uninstall`"
    )


def _survey_pause(_request: TeardownRequest) -> StepSurvey:
    roots = _dispatch_roots()
    if not roots:
        return StepSurvey(
            plan="nothing to do: no repository is registered on this host, so "
            "nothing here dispatches",
            nothing_to_do=True,
        )

    described: list[str] = []
    subjects: list[str] = []
    idle: list[str] = []
    for root in roots:
        location = _locate_dispatch(root)
        if location.owner is RoadmapOwner.RUN:
            return StepSurvey(plan="", refusal=_unowned_refusal(root, location))
        if location.owner is RoadmapOwner.NONE:
            idle.append(f"no roadmap is running for {root}")
            continue
        if location.owner is RoadmapOwner.SCHEDULE and location.schedule_paused:
            idle.append(f"schedule {location.schedule_id} is already paused")
            continue
        owner = (
            f"schedule {location.schedule_id}"
            if location.owner is RoadmapOwner.SCHEDULE
            else f"run {location.workflow_id}"
        )
        described.append(f"{root} ({owner})")
        subjects.append(str(root))

    if not subjects:
        return StepSurvey(plan=f"nothing to do: {'; '.join(idle)}", nothing_to_do=True)
    return StepSurvey(
        plan=f"pause dispatch for {', '.join(described)}", subjects=tuple(subjects)
    )


def _perform_pause(_request: TeardownRequest, survey: StepSurvey) -> tuple[str, ...]:
    """`ergane roadmap pause`, as it stands, once per corpus still dispatching."""
    said: list[str] = []
    for specs_root in survey.subjects:
        said += _capture(
            lambda root=specs_root: asyncio.run(
                roadmap_pause_command(argparse.Namespace(specs_root=root))
            )
        )
    return tuple(said)


# --- step two: forget repositories --------------------------------------------


def _registered_slugs() -> tuple[str, ...]:
    try:
        return tuple(entry.slug for entry in registry.load_registry().entries)
    except registry.RegistryError as error:
        raise OperatorError(str(error), code=EXIT_USER) from None


def _registered_repositories() -> tuple[Path, ...]:
    """Where every registered repository is, for the step that reads their refs."""
    try:
        entries = registry.load_registry().entries
    except registry.RegistryError as error:
        raise OperatorError(str(error), code=EXIT_USER) from None
    return tuple(Path(entry.path) for entry in entries if Path(entry.path).is_dir())


def _survey_forget(_request: TeardownRequest) -> StepSurvey:
    slugs = _registered_slugs()
    if not slugs:
        return StepSurvey(
            plan="nothing to do: no repository is registered", nothing_to_do=True
        )
    return StepSurvey(
        plan=f"forget {len(slugs)} registered "
        f"{'repository' if len(slugs) == 1 else 'repositories'}: {', '.join(slugs)}",
        subjects=slugs,
    )


def _perform_forget(request: TeardownRequest, survey: StepSurvey) -> tuple[str, ...]:
    """`ergane repo forget <slug>`, as it stands, once per registered repository.

    Without `--clean-runtime`: a repository's own runtime root belongs to the
    repository, and emptying it is a decision its operator makes with that flag
    on that repo — not something a host-level teardown does to every entry it
    finds.
    """
    said: list[str] = []
    for slug in survey.subjects:
        said += _capture(
            lambda name=slug: repo_forget_command(
                argparse.Namespace(
                    slug=name,
                    clean_runtime=False,
                    export=None,
                    lock_timeout=request.lock_timeout,
                )
            )
        )
    return tuple(said)


# --- step three: take the engine container down (104-US7) ---------------------
#
# *The engine container* is the Docker container `ergane install` brings up —
# never bwrap's sandbox, never "a container of specs".
#
# Third, not last (R9): dispatch is paused first and the repositories forgotten
# second, and the engine must be down before `clear state` could remove anything
# it is writing. `_kept`, `_removed` and `_state_home` are step five's, read from
# here on purpose — one labelled grammar for every path this verb keeps or
# removes, whichever step produced the line.

#: `docker compose down` and nothing else: it stops the containers this project
#: declares and removes them and their network. Not `down -v`, which would take
#: named volumes — the project declares none, and a flag that would delete data
#: if one were ever added is not a flag to carry speculatively.
ENGINE_DOWN = "down"

_WHY_ENGINE_KEPT_STATE = (
    "the state root; this step removes nothing outside the engine container's "
    "own project directory"
)
_WHY_ENGINE_KEPT_DIR = "it still holds files ergane did not write; --purge takes them"


def _engine_notes() -> tuple[str, ...]:
    """The two paths US7-S1 promises survive this step, named on every path.

    They print whether or not this host has an engine container, for the reason
    `StepSurvey.notes` exists: a report that only speaks when it deletes is the
    defect 083 closed, and "the config is kept" is worth as much on the host that
    never ran a container as on the one being unplugged.
    """
    return (
        _kept(_state_home(), _WHY_ENGINE_KEPT_STATE),
        _kept(resolve_config_path(), _WHY_CONFIG),
    )


def _survey_engine(request: TeardownRequest) -> StepSurvey:
    """What this host has, read from the manifest and nothing else.

    `installed_project` is R1's record: a generated project on disk *is* the fact
    that this installation runs the container tier, so the question is never put
    to `config.toml`, to a daemon, or to the renderer.
    """
    directory = project_dir(request.layout)
    installed = installed_project(request.layout)
    if installed is None:
        return StepSurvey(
            plan=f"nothing to do: no engine container project at {directory}, so "
            "this host runs no engine container",
            notes=_engine_notes(),
            nothing_to_do=True,
        )
    extension = (
        "; --purge takes whatever else that directory holds"
        if request.purge
        else ""
    )
    return StepSurvey(
        plan=f"take the engine container down from {installed.compose_path} and "
        f"remove the {len(installed.files)} file(s) this engine wrote under "
        f"{directory}: {', '.join(installed.files)}{extension}",
        subjects=installed.files,
        notes=_engine_notes(),
    )


def _engine_down(request: TeardownRequest, compose_path: Path) -> tuple[str, ...]:
    """`docker compose down` — reported when it cannot happen, never raised.

    **Bring-down may not require what bring-up requires** (plan trap 13).
    `factory/cli/nouns/worker.py:30` refuses three verbs without a systemd user
    session and `_uninstall` (`:49`) deliberately does not call it, because
    removal has to work everywhere; this is the same asymmetry against a Docker
    daemon that has been stopped, uninstalled, or was never there. The recorded
    manifest still says what to remove, and raising here would strand those files
    on the host to spite a container that a host-level teardown was going to
    outlive anyway.
    """
    if not compose_path.is_file():
        return (
            f"the engine container was not addressed: {compose_path} is gone, so "
            "compose has no project to act on; removing what the manifest records",
        )
    argv = compose_argv(compose_path, ENGINE_DOWN)
    runner = _run_compose if request.run is None else request.run
    spelled = " ".join(argv)
    try:
        result = runner(argv)
    except (OSError, subprocess.SubprocessError) as failure:
        # The shape `_git` above uses, for the same reason: a host being
        # dismantled is exactly where the tool is already gone.
        return _engine_unreachable(f"`{spelled}` could not be run: {failure}")
    if result.code != 0:
        # One line: teardown's report is one indented line per fact, and compose
        # says most of what matters across several.
        said = " ".join(result.out.split())
        return _engine_unreachable(f"`{spelled}` exited {result.code}: {said}")
    return (f"took the engine container down: {spelled}",)


def _engine_unreachable(reason: str) -> tuple[str, ...]:
    """One report, two ways of not reaching the daemon, one remedy.

    Deliberately not a remedy naming this compose file: the removal below is
    about to delete it, so pointing an operator back at it would be pointing at
    a path that no longer exists by the time they read the line.
    """
    return (
        f"could not take the engine container down — {reason}",
        "  the files below were removed from what the manifest records anyway; "
        "if that container is still running, `docker ps` names it",
    )


def _engine_removed(report: RemovalReport, *, purge: bool) -> tuple[str, ...]:
    """US3's removal, re-labelled into 083's grammar (FR-013).

    Rendered here rather than through `RemovalReport.render()` so every path this
    verb removes or keeps wears the same label at the same width of claim,
    whichever step produced the line — which is what makes the report readable
    for what survived as easily as for what did not.

    Under `--purge` the kept lines are dropped rather than printed: the sweep
    below is about to remove those same paths and name them, and one path
    labelled both `kept` and `removed` in one block is worse than either.
    """
    said = [_removed(report.directory / name) for name in report.removed]
    said += [f"already gone: {report.directory / name}" for name in report.missing]
    if not purge:
        said += [
            _kept(report.directory / kept.name, kept.reason) for kept in report.kept
        ]
    if report.directory_removed:
        said.append(_removed(report.directory))
    elif not purge:
        # The directory wears a label too, for the same reason its contents do:
        # a project directory that survives is a fact about this host, and one
        # the operator learns from silence otherwise.
        said.append(_kept(report.directory, _WHY_ENGINE_KEPT_DIR))
    return tuple(said)


def _purge_project_directory(directory: Path) -> tuple[str, ...]:
    """US7-S2: `--purge` extends to the generated artifacts, each removal named.

    The bare run's rule is provenance by digest: a file this engine cannot prove
    it wrote stays, because the operator's edit was probably a response to
    something. `--purge` is the operator asking for the host to be emptied — and
    in the default layout `project_dir` is under `supervision_home()`, which is
    under the state home step five empties, so those bytes were going regardless,
    in one `shutil.rmtree` that names nothing. The extension is therefore less
    "remove more" than *name* it: one labelled line per path, here, where the
    step that owns the engine container can say which paths were its.
    """
    if not directory.is_dir():
        return ()
    said: list[str] = []
    for path in sorted(directory.iterdir()):
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
        said.append(_removed(path))
    directory.rmdir()
    said.append(_removed(directory))
    return tuple(said)


def _perform_engine(request: TeardownRequest, _survey: StepSurvey) -> tuple[str, ...]:
    """Down first, then remove exactly what the manifest claims (US7-S1).

    Read again here rather than threaded through `subjects`, for the reason
    `_perform_refs` gives for its own second read: the name removed and the name
    reported should come from the same read.
    """
    installed = installed_project(request.layout)
    if installed is None:  # pragma: no cover - the survey found one a moment ago
        return ()
    said = list(_engine_down(request, installed.compose_path))
    said += _engine_removed(remove_project(request.layout), purge=request.purge)
    if request.purge:
        said += _purge_project_directory(installed.directory)
    return tuple(said)


def _engine_removal_targets(request: TeardownRequest) -> tuple[Path, ...]:
    """The one directory this step deletes out of, for the FR-018 guard.

    Offered on every path, not only under `--purge`: unlike `clear state`, this
    step removes the files it generated whether or not purge was asked for, so
    the guard has something to test on every run.
    """
    return (project_dir(request.layout),)


# --- step four: stop and remove units ------------------------------------------


def _installed_units(request: TeardownRequest) -> tuple[str, ...]:
    return tuple(
        generated.name
        for generated in generated_files(request.layout)
        if generated.path.exists()
    )


def _survey_units(request: TeardownRequest) -> StepSurvey:
    present = _installed_units(request)
    if not present:
        return StepSurvey(
            plan="nothing to do: no file this engine wrote is still here",
            nothing_to_do=True,
        )
    return StepSurvey(
        plan=f"stop and remove {len(present)} file(s) this engine wrote, under "
        f"{request.layout.unit_dir} and {request.layout.generated_dir}",
        subjects=present,
    )


def _perform_units(request: TeardownRequest, _survey: StepSurvey) -> tuple[str, ...]:
    """`uninstall()`, through the two parameters it already has (FR-017)."""
    report = uninstall_units(
        request.layout, run=request.run, open_epics=request.open_epics
    )
    return tuple(report.render().splitlines())


def _unit_removal_targets(request: TeardownRequest) -> tuple[Path, ...]:
    """The two directories this step deletes out of."""
    return (request.layout.unit_dir, request.layout.generated_dir)


# --- step five: clear state, keep config --------------------------------------

#: Everything the engine keeps under the state home lives in this one child:
#: `factory/registry.py`'s `ergane/repos.json` and `supervision_home()`'s
#: `ergane/supervision`. Taken from the registry's own relative path rather than
#: spelled a second time here.
ERGANE_STATE_DIR = registry.DEFAULT_REGISTRY_REL.parts[0]

#: The label every kept and every removed path wears. One word at the start of
#: the line, the same width of claim on both sides, so a report can be read for
#: what survived as easily as for what did not (FR-013).
KEPT = "kept"
REMOVED = "removed"

_WHY_CONFIG = "the control-plane config; teardown never removes it"
_WHY_SECRET = "beside the config, so treated as a secret"
_WHY_STATE = "state; --purge removes it"
_WHY_SKILL_OWNERSHIP = (
    "modified skill entries remain; this is the retained ownership evidence"
)


def _kept(path: Path | str, why: str) -> str:
    return f"{KEPT}: {path} ({why})"


def _removed(subject: Path | str) -> str:
    return f"{REMOVED}: {subject}"


def _state_home() -> Path:
    """Ergane's own state directory — the one tree `--purge` empties.

    **Which root is emptied when an override is in force** (FR-014, 083 plan
    trap 9, applying US1's ruling here). `--clean-runtime` derives its target
    from a registry entry, so the environment offers it a *second* candidate and
    the right answer is to refuse to retarget. The state home is not that shape:
    there is one resolver, `resolve_state_home()`, and everything the engine ever
    wrote is under whatever it returns *because that resolver is what put it
    there*. So `--purge` empties the resolved root, override included; there is
    no other root holding Ergane's state for it to empty instead. What an
    override does create is a default root that is now not emptied, and
    `_state_home_disclosure` names it.

    The second half of the resolution is the safety one. `resolve_state_home()`
    returns the *shared* XDG root — `~/.local/state` — and Ergane occupies one
    child of it. The contents `--purge` removes are that child's and never its
    parent's: emptying `~/.local/state` would take every other application on
    the host with it.
    """
    return registry.resolve_state_home() / ERGANE_STATE_DIR


def _state_home_disclosure(state_home: Path) -> str | None:
    """Name the default state root when an override moved the emptied one.

    In the voice of the legacy-root line at `factory/cli/repo.py`, and
    conditional for the same reason (083 plan, trap 6): no override, no line, so
    the line still means something the day it prints. The default comes from the
    resolver's own helper rather than from a second reading of `XDG_STATE_HOME`
    here — re-deriving it is exactly the drift `resolve_state_home`'s docstring
    exists to prevent.
    """
    for name in (ERGANE_STATE_HOME_ENV, FACTORY_STATE_HOME_ENV):
        if not os.environ.get(name):
            continue
        default = registry._xdg_state_home() / ERGANE_STATE_DIR
        if default == state_home:
            return None
        return (
            f"{name} is set, so the emptied root would be {state_home}; {default} "
            "is the root this host would use without it, and teardown does not "
            "empty it"
        )
    return None


def _state_contents(state_home: Path) -> tuple[Path, ...]:
    """The top-level entries `--purge` removes, and a bare run keeps and names."""
    if not state_home.is_dir():
        return ()
    return tuple(sorted(state_home.iterdir()))


def _config_paths() -> tuple[Path, ...]:
    """The control-plane config and the secrets beside it — kept on every path.

    `resolve_config_path()` (FR-013) names the file; what sits beside it in that
    directory is what install put there, and credentials are the one thing an
    operator cannot cheaply recreate. Lock files are excluded: they are not
    secrets, they are the litter `factory/locking.py` leaves behind, and
    `_config_locks` sweeps them.
    """
    config = resolve_config_path()
    beside: tuple[Path, ...] = ()
    if config.parent.is_dir():
        beside = tuple(
            sorted(
                path
                for path in config.parent.iterdir()
                if path.is_file() and path != config and path.suffix != ".lock"
            )
        )
    return ((config,) if config.is_file() else ()) + beside


def _config_locks() -> tuple[Path, ...]:
    """The lock files beside the config — `config.toml.lock` and its kin.

    `factory/locking.py:46-49` names a lock `<target>.lock`, `:68` creates it
    with `O_CREAT`, and `:83`/`:85` unlock and close without ever unlinking, so
    every lock this engine has taken is still on disk. That is why
    `config.toml.lock` outlived the field teardown. It is swept here rather than
    by making `exclusive_lock` unlink on exit, which would race two processes
    that both hold the path open (083 plan, trap 10).

    The naming rule finds the locks whose target is still there; the glob finds
    the orphans whose target has already gone, which the rule alone cannot reach.
    """
    directory = resolve_config_path().parent
    if not directory.is_dir():
        return ()
    by_rule = _lock_siblings((resolve_config_path(), *directory.iterdir()))
    return tuple(sorted(set(by_rule) | {p for p in directory.glob("*.lock") if p.is_file()}))


def _lock_siblings(paths: Iterable[Path]) -> tuple[Path, ...]:
    """The locks guarding `paths` that actually exist, by `factory/locking.py`'s rule."""
    return tuple(
        sorted({lock for lock in map(lock_path_for, paths) if lock.is_file()})
    )


def _survey_state(request: TeardownRequest) -> StepSurvey:
    state_home = _state_home()
    contents = _state_contents(state_home)
    retained_manifest = request.retained_skill_manifest
    if retained_manifest is not None and not retained_manifest.is_file():
        retained_manifest = None
    config = resolve_config_path()

    # Only what is actually there: a kept line for a file nobody has is the same
    # unauditable claim as a removed line for a file nothing deleted.
    kept = [
        _kept(path, _WHY_CONFIG if path == config else _WHY_SECRET)
        for path in _config_paths()
    ]
    disclosure = _state_home_disclosure(state_home)

    if not request.purge:
        # The same paths the purge run removes, wearing the other label. That
        # symmetry is FR-013: told apart by the label, not by absence.
        notes = [_kept(path, _WHY_STATE) for path in contents] + kept
        if retained_manifest is not None:
            notes.append(_kept(retained_manifest, _WHY_SKILL_OWNERSHIP))
        return StepSurvey(
            plan=(
                f"nothing to do: --purge was not given, so nothing under "
                f"{state_home} is removed; the config at {config} is kept either way"
            ),
            notes=tuple(notes + ([disclosure] if disclosure else [])),
            nothing_to_do=True,
        )

    locks = _config_locks()
    subjects = _state_removal_subjects(state_home, retained_manifest)
    notes = kept + ([disclosure] if disclosure else [])
    if retained_manifest is not None:
        notes.append(_kept(retained_manifest, _WHY_SKILL_OWNERSHIP))
    if not subjects and not locks:
        return StepSurvey(
            plan=f"nothing to do: {state_home} holds nothing to remove",
            notes=tuple(notes),
            nothing_to_do=True,
        )
    return StepSurvey(
        plan=(
            f"remove {len(subjects)} entr{'y' if len(subjects) == 1 else 'ies'} under "
            f"{state_home} and {len(locks)} lock "
            f"file{'' if len(locks) == 1 else 's'} beside {config}; "
            "the config itself is kept"
        ),
        subjects=tuple(str(path) for path in subjects + locks),
        notes=tuple(notes),
    )


def _state_removal_subjects(
    state_home: Path,
    retained: Path | None,
) -> tuple[Path, ...]:
    """Every purge subject, with the retained manifest subtree pruned around it."""

    def collect(path: Path) -> tuple[Path, ...]:
        if (
            not path.is_dir()
            or path.is_symlink()
            or (
                retained is not None
                and retained not in path.parents
                and not retained.is_relative_to(path)
            )
        ):
            return (path,)
        result: list[Path] = []
        for child in sorted(path.iterdir()):
            if child == retained:
                continue
            result.extend(collect(child))
        if retained is None or (
            retained not in path.parents and not retained.is_relative_to(path)
        ):
            result.append(path)
        return result

    subjects: list[Path] = []
    for path in _state_contents(state_home):
        subjects.extend(collect(path))
    return tuple(subjects)


def _perform_state(request: TeardownRequest, survey: StepSurvey) -> tuple[str, ...]:
    """Empty the state home and sweep the locks; name every path as it goes.

    The state home itself survives its contents: FR-014 removes what is *in* it,
    and a directory an operator's `XDG_STATE_HOME` points at is not this verb's
    to delete.
    """
    said: list[str] = []
    for subject in survey.subjects:
        path = Path(subject)
        retained = request.retained_skill_manifest
        if retained is not None and path in retained.parents:
            if path.is_dir() and not path.is_symlink():
                path.rmdir()
            else:
                path.unlink(missing_ok=True)
        elif path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
        said.append(_removed(path))
    return tuple(said)


def _state_removal_targets(request: TeardownRequest) -> tuple[Path, ...]:
    """What `--purge` deletes out of, for the FR-018 guard to test before any act.

    This is the step most able to trip that guard (083 plan, trap 8): a state
    home an operator has pointed somewhere unfortunate is one `--purge` away
    from the field report happening again, and `supervision_home()` puts
    everything supervision generates under it. Without `--purge` the step deletes
    nothing, so it offers the guard nothing to test.
    """
    return (_state_home(),) if request.purge else ()


# --- step five: skill teardown --------------------------------------------------


def _survey_skills(_request: TeardownRequest) -> StepSurvey:
    """Read ownership and classify every declared skill entry."""

    try:
        plan = survey_skills_teardown()
    except ManifestError as refusal:
        from factory.cli.errors import EXIT_USER

        raise OperatorError(str(refusal), code=EXIT_USER) from None
    return StepSurvey(
        plan=plan.plan,
        subjects=plan.subjects,
        notes=plan.notes,
        nothing_to_do=plan.nothing_to_do,
        retained_skill_manifest=plan.retained_manifest,
    )


def _perform_skills(
    _request: TeardownRequest,
    _survey: StepSurvey,
) -> tuple[str, ...]:
    return perform_skills_teardown()


# --- step six: account for the git refs ----------------------------------------

#: `branch_name(epic, node)` is `factory/<epic>/<node>`, so every node branch
#: this host ever made is under one prefix. Derived from that function rather
#: than spelled out, so a rename moves both together.
FACTORY_BRANCH_ROOT = f"refs/heads/{branch_name('epic', 'node').split('/')[0]}"

#: The two incantations teardown prints verbatim (FR-015), and the two it runs
#: to produce its counts — the same string on both sides, so an operator who
#: pastes one gets the set that was counted. Deliberately *not*
#: `ergane build salvage`: that verb loads a compiled graph
#: (`factory/cli/nouns/build.py:1392`) and reports one epic's nodes, so it cannot
#: answer what is on the host. Pointing at a command that will not list them is
#: worse than leaving them unmentioned.
LIST_BRANCHES_COMMAND = f"git for-each-ref {FACTORY_BRANCH_ROOT}/"
LIST_SALVAGE_COMMAND = f"git for-each-ref {SALVAGE_REF_ROOT}/"


def _git(repo: Path, *args: str) -> tuple[int, str]:
    """One git command in `repo` — its code and its stdout, never an exception.

    The shape `factory/workgraph/worktree.py:823` already uses for the engine's
    own `for-each-ref`, with the same scrubbed environment: git spawned by the
    factory carries no factory credentials. Teardown *reports* on refs, so a
    registered path that is not a repository is zero refs rather than a failed
    teardown — a host being dismantled is exactly where a stale entry lives.
    """
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            env=scrubbed_env() | {"GIT_TERMINAL_PROMPT": "0"},
            timeout=GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return completed.returncode, completed.stdout


def _for_each_ref(repo: Path, namespace: str) -> tuple[str, ...]:
    """Every ref under `namespace` in `repo`, by name."""
    code, listing = _git(repo, "for-each-ref", "--format=%(refname)", namespace)
    if code != 0:
        return ()
    return tuple(line for line in listing.splitlines() if line)


def _count_refs(repositories: Sequence[Path]) -> tuple[tuple[Path, int, int], ...]:
    """Per repository, how many node branches and how many salvage refs it holds."""
    counted: list[tuple[Path, int, int]] = []
    for repo in repositories:
        branches = len(_for_each_ref(repo, f"{FACTORY_BRANCH_ROOT}/"))
        salvage = len(_for_each_ref(repo, f"{SALVAGE_REF_ROOT}/"))
        if branches or salvage:
            counted.append((repo, branches, salvage))
    return tuple(counted)


def _survey_refs(request: TeardownRequest) -> StepSurvey:
    repositories = request.repositories or ()
    counted = _count_refs(repositories)
    branches = sum(found for _, found, _ in counted)
    salvage = sum(found for _, _, found in counted)
    tally = (
        f"{branches} branch(es) under {FACTORY_BRANCH_ROOT}/ and "
        f"{salvage} ref(s) under {SALVAGE_REF_ROOT}/"
    )
    # The commands print on every path, including the empty host: FR-015 asks
    # for the count and the incantation unconditionally, because "none here" is
    # an answer an operator can only trust if they can reproduce it.
    notes = tuple(
        f"{repo}: {found_branches} under {FACTORY_BRANCH_ROOT}/, "
        f"{found_salvage} under {SALVAGE_REF_ROOT}/"
        for repo, found_branches, found_salvage in counted
    ) + (
        "list them yourself, one namespace each:",
        LIST_BRANCHES_COMMAND,
        LIST_SALVAGE_COMMAND,
    )
    spread = (
        f"across {len(counted)} "
        f"{'repository' if len(counted) == 1 else 'repositories'}"
    )

    if not repositories:
        return StepSurvey(
            plan=f"nothing to do: {tally}, because no repository is registered "
            "on this host",
            notes=notes,
            nothing_to_do=True,
        )
    if not request.scrub_refs or not counted:
        return StepSurvey(
            plan=f"nothing to do: {tally} stay, {spread}; --scrub-refs removes them",
            notes=notes,
            nothing_to_do=True,
        )
    return StepSurvey(
        plan=f"remove {tally}, {spread}",
        subjects=tuple(str(repo) for repo, _, _ in counted),
        notes=notes,
    )


def _perform_refs(_request: TeardownRequest, survey: StepSurvey) -> tuple[str, ...]:
    """`--scrub-refs`: delete each ref by name, and name each one (FR-016).

    Read again here rather than threaded through `subjects` so the name deleted
    and the name reported come from the same read, for the reason
    `_read_salvage_refs` gives for its own single `for-each-ref`.
    """
    said: list[str] = []
    for subject in survey.subjects:
        repo = Path(subject)
        for namespace in (f"{FACTORY_BRANCH_ROOT}/", f"{SALVAGE_REF_ROOT}/"):
            for ref in _for_each_ref(repo, namespace):
                code, _ = _git(repo, "update-ref", "-d", ref)
                said.append(
                    _removed(f"{ref} (in {repo})")
                    if code == 0
                    else f"could not remove {ref} in {repo}; it is still there"
                )
    return tuple(said)


#: The order teardown performs, and the order `--check` prints. One tuple, read
#: by both (FR-009); tests replace it wholesale, which is the only seam this
#: module adds.
#:
#: State comes after the units because `supervision_home()` puts what supervision
#: generated *inside* the state home, and the refs come last because they are
#: the only thing here teardown reports on without owning.
#:
#: The engine container is third (104-US7, R9), for the same family of reason:
#: dispatch is paused first and the repositories forgotten second, and the engine
#: has to be down before `clear state` could empty a directory it is writing to.
STEPS: tuple[Step, ...] = (
    Step(name=PAUSE_DISPATCH, survey=_survey_pause, perform=_perform_pause),
    Step(name=FORGET_REPOSITORIES, survey=_survey_forget, perform=_perform_forget),
    Step(
        name=STOP_ENGINE_CONTAINER,
        survey=_survey_engine,
        perform=_perform_engine,
        removal_targets=_engine_removal_targets,
    ),
    Step(
        name=STOP_AND_REMOVE_UNITS,
        survey=_survey_units,
        perform=_perform_units,
        removal_targets=_unit_removal_targets,
    ),
    Step(name=SKILL_TEARDOWN, survey=_survey_skills, perform=_perform_skills),
    Step(
        name=CLEAR_STATE,
        survey=_survey_state,
        perform=_perform_state,
        removal_targets=_state_removal_targets,
    ),
    Step(name=ACCOUNT_FOR_REFS, survey=_survey_refs, perform=_perform_refs),
)


# --- the refusal that precedes every step (FR-018) ----------------------------


def _this_installation(layout: InstallLayout) -> tuple[tuple[str, Path], ...]:
    """The two paths that *are* this installation, as `resolve_layout()` derives them.

    The interpreter's directory is taken before resolving symlinks: a venv's
    `bin/python3` points at the system interpreter, and following it would name
    `/usr/bin` — a directory this process is emphatically not installed in.
    """
    return (
        ("the install root", layout.install_root.resolve()),
        ("the directory holding the interpreter", layout.interpreter.parent.resolve()),
    )


def _contains(target: Path, path: Path) -> bool:
    """Is `path` inside `target`, or `target` itself?"""
    resolved = target.resolve()
    return path == resolved or resolved in path.parents


def _refuse_removing_this_installation(
    request: TeardownRequest, steps: Sequence[Step]
) -> None:
    """Refuse, before any step acts, a removal target containing this installation.

    In the shape of `_refuse_while_epics_run` (`factory/cli/repo.py`): computed
    from reads, taken ahead of every act, and with no acknowledgment flag — for
    the reason `_refuse_unsafe_removal` argues in that same file, that a door
    with no user is only a way in. The remedy costs nothing: point the state home
    or the unit directory somewhere that does not contain the code being run.
    """
    for step in steps:
        for target in step.removal_targets(request):
            for name, path in _this_installation(request.layout):
                if _contains(target, path):
                    raise OperatorError(
                        f"refusing to run teardown: step {step.name!r} would remove "
                        f"{target}, which contains {name} {path} — the installation "
                        "this process is running from. Teardown would delete itself "
                        "mid-run and leave a host no report describes; there is no "
                        "flag for this",
                        code=EXIT_USER,
                    )


# --- the run ------------------------------------------------------------------


def _capture(call: Callable[[], Any]) -> list[str]:
    """Run one composed command and fold what it printed into teardown's report."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        call()
    return buffer.getvalue().splitlines()


def _stop(
    steps: Sequence[Step],
    index: int,
    reason: str,
    done: Sequence[str],
    *,
    code: int = EXIT_USER,
) -> NoReturn:
    """FR-012: name the step that refused, and what has already been done.

    The refusing step's own exit code is carried through rather than flattened,
    so a control plane that would not answer still exits 3 the way every other
    verb's transport failure does.
    """
    step = steps[index - 1]
    remaining = [other.name for other in steps[index:]]
    raise OperatorError(
        f"teardown stopped at step {index} of {len(steps)}, {step.name}: {reason}\n"
        f"  already done: {', '.join(done) if done else 'nothing'}\n"
        f"  not attempted: {', '.join(remaining) if remaining else 'none'}",
        code=code,
    )


def run_teardown(
    request: TeardownRequest, steps: Sequence[Step] | None = None
) -> int:
    """Perform teardown, or print the plan a real run would follow.

    One loop over one table serves both: `check` decides whether `perform` is
    reached, and nothing else differs, so the sequence printed is the sequence
    performed.
    """
    table = STEPS if steps is None else tuple(steps)
    _refuse_removing_this_installation(request, table)
    if request.repositories is None:
        # Read once, before step two forgets the registry that answers it: step
        # five still has to account for the refs those repositories carry, and
        # `repo forget` leaves the repository itself untouched, so the paths
        # stay valid long after the entries naming them are gone.
        request = replace(request, repositories=_registered_repositories())

    total = len(table)
    print(
        f"teardown plan, {total} steps in the order the table declares; "
        "--check performs none of them:"
        if request.check
        else f"teardown, {total} steps in the order the table declares:"
    )

    done: list[str] = []
    for index, step in enumerate(table, start=1):
        try:
            survey = step.survey(request)
        except OperatorError as refusal:
            _stop(table, index, str(refusal), done, code=refusal.code)
        if survey.refusal is not None:
            _stop(table, index, survey.refusal, done)

        if survey.retained_skill_manifest is not None:
            request = replace(
                request,
                retained_skill_manifest=survey.retained_skill_manifest,
            )

        print(f"{index}/{total} {step.name}: {survey.plan}")
        for note in survey.notes:
            print(f"    {note}")
        if survey.nothing_to_do:
            done.append(f"{step.name} (nothing to do)")
            continue
        if request.check:
            continue

        try:
            said = step.perform(request, survey)
        except OperatorError as refusal:
            _stop(table, index, str(refusal), done, code=refusal.code)
        for line in said:
            print(f"    {line}")
        done.append(step.name)

    print(CHECK_PERFORMED_NOTHING if request.check else f"teardown done: {', '.join(done)}")
    return EXIT_OK


def _request_for(args: argparse.Namespace) -> TeardownRequest:
    """How the command builds its request, and the seam the suite replaces.

    `removal_layout()`'s defaults derive `~/.config/systemd/user` from the real
    HOME, and on this host that systemd session *is* the factory
    (`factory/supervision/units.py`'s `_run_command` says so). Binding this
    instead of the layout keeps every test's teardown inside its own tmp tree.

    `removal_layout` rather than `resolve_layout` (119-US1): teardown offers
    candidates and removes only what its digest proves this engine wrote, so it
    names the managed unit when the declaration cannot be read instead of
    refusing to clean up a broken installation.
    """
    return TeardownRequest(
        layout=removal_layout(),
        check=bool(args.check),
        purge=bool(args.purge),
        scrub_refs=bool(args.scrub_refs),
    )


def uninstall_command(args: argparse.Namespace) -> int:
    """`ergane uninstall` — the whole verb is the table and the loop above."""
    return run_teardown(_request_for(args))


def add_uninstall_parser(subparsers: Any) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "uninstall",
        help="take Ergane off this host, in the order that is safe",
        description=(
            "Perform teardown in the declared order — pause dispatch, forget "
            "repositories, stop the engine container, stop and remove units, "
            "clear state, account for the "
            "git refs — naming each step as it completes. A step with nothing to "
            "do says so; a step that refuses stops the verb before the next one "
            "acts. The control-plane config and the secrets beside it are kept "
            "on every path, and every surviving path is named as plainly as "
            "every removed one."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="print the plan a real run would follow and exit; writes, removes, "
        "stops and signals nothing",
    )
    parser.add_argument(
        "--purge",
        action="store_true",
        help="also empty Ergane's state home, lock-file siblings included, and "
        "whatever else the engine container's project directory holds; the "
        "control-plane config and the secrets beside it are kept either way",
    )
    parser.add_argument(
        "--scrub-refs",
        action="store_true",
        help="also remove the factory/<epic>/<node> branches and the refs under "
        "refs/salvage/ that teardown otherwise only counts and names",
    )
    parser.set_defaults(run=uninstall_command)
    return parser
