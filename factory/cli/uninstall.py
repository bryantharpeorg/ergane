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
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, NoReturn, Sequence

from temporalio.service import RPCError

from factory import registry
from factory.cli.errors import EXIT_OK, EXIT_TRANSPORT, EXIT_USER, OperatorError
from factory.cli.nouns import _open_client
from factory.cli.repo import repo_forget_command
from factory.cli.roadmap import roadmap_pause_command
from factory.roadmap.discovery import RoadmapLocation, RoadmapOwner, resolve_roadmap
from factory.roadmap.schedule import SPECS_DIR_NAME
from factory.supervision.units import (
    CommandResult,
    InstallLayout,
    generated_files,
    resolve_layout,
    uninstall as uninstall_units,
)

#: The three step names, in the order the spec declares them. Named constants
#: because the report, the refusals and the tests all say them.
PAUSE_DISPATCH = "pause dispatch"
FORGET_REPOSITORIES = "forget repositories"
STOP_AND_REMOVE_UNITS = "stop and remove units"

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
    lock_timeout: float = registry.DEFAULT_LOCK_TIMEOUT_S
    run: Callable[[Sequence[str]], CommandResult] | None = None
    open_epics: Callable[[], Sequence[str]] | None = None


@dataclass(frozen=True)
class StepSurvey:
    """What one step would do, answered by reading and nothing else.

    Exactly one of three things: a plan with subjects to act on, a
    `nothing_to_do` that says so by name (FR-011), or a `refusal` that stops the
    verb before the next step acts (FR-012).
    """

    plan: str
    subjects: tuple[str, ...] = ()
    nothing_to_do: bool = False
    refusal: str | None = None


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


# --- step three: stop and remove units ----------------------------------------


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


#: The order teardown performs, and the order `--check` prints. One tuple, read
#: by both (FR-009); tests replace it wholesale, which is the only seam this
#: module adds.
STEPS: tuple[Step, ...] = (
    Step(name=PAUSE_DISPATCH, survey=_survey_pause, perform=_perform_pause),
    Step(name=FORGET_REPOSITORIES, survey=_survey_forget, perform=_perform_forget),
    Step(
        name=STOP_AND_REMOVE_UNITS,
        survey=_survey_units,
        perform=_perform_units,
        removal_targets=_unit_removal_targets,
    ),
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

        print(f"{index}/{total} {step.name}: {survey.plan}")
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

    `resolve_layout()`'s defaults derive `~/.config/systemd/user` from the real
    HOME, and on this host that systemd session *is* the factory
    (`factory/supervision/units.py`'s `_run_command` says so). Binding this
    instead of the layout keeps every test's teardown inside its own tmp tree.
    """
    return TeardownRequest(layout=resolve_layout(), check=bool(args.check))


def uninstall_command(args: argparse.Namespace) -> int:
    """`ergane uninstall` — the whole verb is the table and the loop above."""
    return run_teardown(_request_for(args))


def add_uninstall_parser(subparsers: Any) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "uninstall",
        help="take Ergane off this host, in the order that is safe",
        description=(
            "Perform teardown in the declared order — pause dispatch, forget "
            "repositories, stop and remove units — naming each step as it "
            "completes. A step with nothing to do says so; a step that refuses "
            "stops the verb before the next one acts."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="print the plan a real run would follow and exit; writes, removes, "
        "stops and signals nothing",
    )
    parser.set_defaults(run=uninstall_command)
    return parser
