"""083 US3: `ergane uninstall` owns the ordering, and `--check` performs none of it.

Four hand-ordered steps discoverable only by `--help` spelunking was the finding:
the ordering is knowledge the tool has and the operator had to reconstruct. So
teardown is one verb reading one ordered step table — pause dispatch, forget
repositories, stop and remove units — and both `--check` and a real run read that
same table, which is what stops the printed plan and the performed sequence from
diverging (FR-009).

Three things here are easy to build vacuously, so each is written with the thing
that proves it is not:

- **`--check` performs none of it.** The seam is teardown's own step table, not a
  fake for any of the three commands it composes: a substituted recording table
  that never records a `perform` is the whole evidence, and it needs no Temporal
  fake to be believed (`test_check_reaches_no_acting_half`). Beside it, the same
  `--check` run against the real table on a fully populated host, asserting the
  schedule, the registry entry and every unit file survive it, and that not one
  systemd command or Temporal signal was issued.
- **The order is the table's, and the acts are real.** The ordering test drives
  all three real steps against one shared event log, so `pause` before `forget`
  before `stop` is asserted on the acts themselves — a schedule handle's
  `pause()`, a schedule delete, a `systemctl --user disable --now` — and not on
  the sentences teardown printed about them.
- **The three commands beneath teardown did not move** (FR-017). `repo_forget_command`
  still takes one `argparse.Namespace` and still reaches Temporal through
  `factory/cli/repo.py`'s `_temporal_client_factory`; `uninstall()` still honours
  `run` and `open_epics`; `roadmap_pause_command` still pauses the schedule when
  the roadmap is schedule-owned. A teardown that worked because those three were
  reshaped would break every operator who never runs teardown.

`factory/cli/roadmap.py` is not edited by this story (plan trap 14): teardown
imports `roadmap_pause_command` as it stands and puts the seam in its own table.

Pasted evidence (constitution VIII / D-037) is at the bottom.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import io
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, NamedTuple, Sequence

import pytest
import temporalio.client

import factory.cli.repo as repo_module
import factory.cli.uninstall as teardown
from factory import registry
from factory.cli.errors import EXIT_OK, EXIT_USER, OperatorError
from factory.cli.repo import repo_forget_command
from factory.cli.roadmap import roadmap_pause_command
from factory.cli.uninstall import (
    FORGET_REPOSITORIES,
    PAUSE_DISPATCH,
    STEPS,
    STOP_AND_REMOVE_UNITS,
    Step,
    StepSurvey,
    TeardownRequest,
    run_teardown,
)
from factory.roadmap.schedule import schedule_id_for
from factory.supervision.units import (
    CommandResult,
    InstallLayout,
    generated_files,
    install,
    resolve_layout,
    uninstall,
)

from tests.fake_schedules import FakeScheduleServer, desired_for, seed
from tests.test_ergane_init_check import bind_offline_seams, make_repo
from tests.test_roadmap_schedule_discovery import (
    FakeSchedule,
    FakeTemporalClient,
    FakeWorkflow,
)

SLUG = "widgets"
#: `roadmap_workflow_id` derives this from the specs root's *basename*, so every
#: repo scaffolded here shares it; the schedule id carries the slug instead.
BARE_ID = "roadmap-specs"
UNOWNED_RUN = "roadmap-specs-2026-08-15T15:00:00Z"


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str


def invoke(argv: list[str]) -> Run:
    """Run one `ergane` invocation through the real dispatcher."""
    from factory.cli import main as main_module

    old_out, old_err = sys.stdout, sys.stderr
    out, err = io.StringIO(), io.StringIO()
    try:
        sys.stdout, sys.stderr = out, err
        try:
            code = main_module.main(argv)
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
    finally:
        sys.stdout, sys.stderr = old_out, old_err
    return Run(code, out.getvalue(), err.getvalue())


def drive(request: TeardownRequest, steps: Sequence[Step] | None = None) -> Run:
    """Run teardown directly, rendering an `OperatorError` the way the CLI does."""
    old_out = sys.stdout
    out = io.StringIO()
    try:
        sys.stdout = out
        code = run_teardown(request, steps=steps)
    except OperatorError as refusal:
        sys.stdout = old_out
        return Run(refusal.code, out.getvalue(), f"ergane: {refusal}\n")
    finally:
        sys.stdout = old_out
    return Run(code, out.getvalue(), "")


def plan_lines(stdout: str) -> list[str]:
    """The `N/3 <step>: <plan>` lines — what `--check` prints and a run repeats."""
    return [line for line in stdout.splitlines() if line[:1].isdigit() and "/" in line[:4]]


# -----------------------------------------------------------------------------
# The host
# -----------------------------------------------------------------------------


@dataclass
class Host:
    """One host with dispatch running, a registered repo and installed units."""

    repo: Path
    layout: InstallLayout
    client: FakeTemporalClient
    schedules: FakeScheduleServer
    events: list[Any]

    @property
    def schedule_id(self) -> str:
        return schedule_id_for(SLUG)

    def runner(self) -> Callable[[Sequence[str]], CommandResult]:
        def run(argv: Sequence[str]) -> CommandResult:
            self.events.append(tuple(argv))
            return CommandResult(0, "")

        return run

    def request(self, **overrides: Any) -> TeardownRequest:
        base = TeardownRequest(
            layout=self.layout,
            run=self.runner(),
            open_epics=lambda: (),
        )
        return replace(base, **overrides) if overrides else base

    @property
    def unit_files(self) -> list[Path]:
        return [f.path for f in generated_files(self.layout) if f.path.exists()]


def _host(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    schedules: list[FakeSchedule] | None = None,
    workflows: dict[str, FakeWorkflow] | None = None,
) -> Host:
    """Register a repo, seed its schedule, install its units — all in `tmp_path`.

    The layout is built here rather than by `resolve_layout()`'s defaults on
    purpose: those derive `~/.config/systemd/user` from the real HOME, and this
    suite runs on the host the factory itself is installed on.
    """
    repo = make_repo(tmp_path, name=SLUG)
    (repo / ".ergane").mkdir(exist_ok=True)
    (repo / ".ergane" / "doctor.db").write_text("seeded\n", encoding="utf-8")
    registry.register(SLUG, repo)

    control_plane = FakeScheduleServer()
    seed(control_plane, desired_for(repo, slug=SLUG))
    bind_offline_seams(monkeypatch, schedules=control_plane)

    client = FakeTemporalClient(
        workflows=workflows or {},
        schedules=(
            schedules
            if schedules is not None
            else [FakeSchedule(id=schedule_id_for(SLUG), action_workflow_id=BARE_ID)]
        ),
    )

    async def connect(target_host: str, **kwargs: Any) -> FakeTemporalClient:
        return client

    monkeypatch.setattr(temporalio.client.Client, "connect", connect)

    layout = resolve_layout(
        home=tmp_path / "home",
        generated_dir=tmp_path / "state" / "supervision",
    )
    events: list[Any] = []
    install(layout, run=lambda argv: CommandResult(0, ""))

    # One log for three fakes: the schedule handle's `pause`, the schedule
    # server's `delete` and every systemd command land in the same list, in the
    # order they actually happened. Assigned after `seed`, which clears `calls`.
    client.schedule_calls = events
    control_plane.calls = events
    return Host(repo=repo, layout=layout, client=client, schedules=control_plane, events=events)


@pytest.fixture
def host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Host:
    return _host(tmp_path, monkeypatch)


def _index(events: list[Any], *prefix: str) -> int:
    for position, event in enumerate(events):
        if tuple(event)[: len(prefix)] == prefix:
            return position
    raise AssertionError(f"{prefix} never happened; log was {events}")


# -----------------------------------------------------------------------------
# T025 / US3-S1, FR-009 — the declared order, from the one table
# -----------------------------------------------------------------------------


def test_the_step_table_declares_the_order_the_spec_does() -> None:
    """US3-S1: the order is a property of the table, readable without running it."""
    assert [step.name for step in STEPS] == [
        PAUSE_DISPATCH,
        FORGET_REPOSITORIES,
        STOP_AND_REMOVE_UNITS,
    ]


def test_teardown_performs_its_steps_in_the_declared_order(host: Host) -> None:
    """US3-S1: pause, then forget, then stop and remove — asserted on the acts.

    Every step runs for real against its own seam: the pause reaches a schedule
    handle through `roadmap_pause_command`, the forget reaches the schedule
    server through `repo_forget_command`, and the units go through
    `uninstall()`'s `run`. The three fakes share one event log, so the ordering
    assertion is about what happened rather than about what was printed.
    """
    result = drive(host.request())

    assert result.code == EXIT_OK, result.stderr
    paused = _index(host.events, "pause", host.schedule_id)
    forgotten = _index(host.events, "delete", host.schedule_id)
    stopped = _index(host.events, "systemctl", "--user", "disable")
    assert paused < forgotten < stopped

    # …and each step named as it completes, in the same order.
    assert plan_lines(result.stdout) == [
        line for line in result.stdout.splitlines() if line.startswith(("1/3", "2/3", "3/3"))
    ]
    assert f"1/3 {PAUSE_DISPATCH}" in result.stdout
    assert f"2/3 {FORGET_REPOSITORIES}" in result.stdout
    assert f"3/3 {STOP_AND_REMOVE_UNITS}" in result.stdout

    # The acts themselves landed: no schedule, no entry, no unit files.
    assert host.schedules.schedules == {}
    assert registry.load_registry().get(SLUG) is None
    assert host.unit_files == []


# -----------------------------------------------------------------------------
# T026 / US3-S2, FR-010 — `--check` performs none of it
# -----------------------------------------------------------------------------


def test_check_reaches_no_acting_half(host: Host) -> None:
    """US3-S2: the recording table stays empty, and that is the whole evidence.

    The seam is teardown's own step table. `--check` is conclusive because the
    acting half is unreachable on that path, which needs no Temporal client
    fake and could not get one: `factory/cli/roadmap.py` connects inline.
    """
    surveyed: list[str] = []
    acted: list[str] = []

    def recording(name: str) -> Step:
        def survey(_request: TeardownRequest) -> StepSurvey:
            surveyed.append(name)
            return StepSurvey(plan=f"would {name}", subjects=("something",))

        def perform(_request: TeardownRequest, _survey: StepSurvey) -> tuple[str, ...]:
            acted.append(name)
            return (f"{name}: acted",)

        return Step(name=name, survey=survey, perform=perform)

    table = [recording(name) for name in (PAUSE_DISPATCH, FORGET_REPOSITORIES, STOP_AND_REMOVE_UNITS)]

    result = drive(host.request(check=True), steps=table)

    assert result.code == EXIT_OK, result.stderr
    assert acted == [], "a --check run reached a step's acting half"
    assert surveyed == [PAUSE_DISPATCH, FORGET_REPOSITORIES, STOP_AND_REMOVE_UNITS]
    assert plan_lines(result.stdout) == [
        f"1/3 {PAUSE_DISPATCH}: would {PAUSE_DISPATCH}",
        f"2/3 {FORGET_REPOSITORIES}: would {FORGET_REPOSITORIES}",
        f"3/3 {STOP_AND_REMOVE_UNITS}: would {STOP_AND_REMOVE_UNITS}",
    ]


def test_check_writes_removes_stops_and_signals_nothing(host: Host) -> None:
    """US3-S2, the direct half: the real table, and a host that did not move.

    The plan lines are then compared against the ones the real run prints on the
    same host — one table, so `--check` cannot describe a sequence teardown does
    not perform (FR-009).
    """
    before = sorted(host.unit_files)

    checked = drive(host.request(check=True))

    assert checked.code == EXIT_OK, checked.stderr
    assert host.events == [], f"--check issued commands: {host.events}"
    assert host.client.signals == []
    assert host.schedules.schedules != {}
    assert registry.load_registry().get(SLUG) is not None
    assert sorted(host.unit_files) == before
    assert "nothing was written, removed, stopped or signalled" in checked.stdout

    performed = drive(host.request())

    assert performed.code == EXIT_OK, performed.stderr
    assert plan_lines(checked.stdout) == plan_lines(performed.stdout)


# -----------------------------------------------------------------------------
# T027 / US3-S3, FR-011 — a step with nothing to do says so by name
# -----------------------------------------------------------------------------


def test_a_step_with_nothing_to_do_says_so_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US3-S3: no repositories, no units — three steps, three sentences.

    A skipped step and a step that ran are indistinguishable from silence, which
    is the defect US1 closes on the other verb.
    """
    bind_offline_seams(monkeypatch, schedules=FakeScheduleServer())
    layout = resolve_layout(
        home=tmp_path / "home", generated_dir=tmp_path / "state" / "supervision"
    )
    events: list[Any] = []

    result = drive(
        TeardownRequest(
            layout=layout,
            run=lambda argv: events.append(tuple(argv)) or CommandResult(0, ""),
            open_epics=lambda: (),
        )
    )

    assert result.code == EXIT_OK, result.stderr
    for index, name in enumerate(
        (PAUSE_DISPATCH, FORGET_REPOSITORIES, STOP_AND_REMOVE_UNITS), start=1
    ):
        assert f"{index}/3 {name}: nothing to do:" in result.stdout
    assert "no repository is registered" in result.stdout
    assert "no file this engine wrote is still here" in result.stdout
    assert events == []


# -----------------------------------------------------------------------------
# T028 / US3-S4, FR-012 — a refused step stops the verb
# -----------------------------------------------------------------------------


def test_a_refused_step_stops_the_verb_and_names_what_was_done(host: Host) -> None:
    """US3-S4: an epic in flight refuses step three, after steps one and two ran.

    The refusal names which step refused and what has already been done, because
    a half-teardown the operator cannot bound is worse than one that was refused.
    """
    result = drive(host.request(open_epics=lambda: ("epic-011-agent-sandbox",)))

    assert result.code == EXIT_USER
    assert f"teardown stopped at step 3 of 3, {STOP_AND_REMOVE_UNITS}" in result.stderr
    assert "epic-011-agent-sandbox is in flight" in result.stderr
    assert f"already done: {PAUSE_DISPATCH}, {FORGET_REPOSITORIES}" in result.stderr

    # Stopped *before* the step acted: every unit file is still there.
    assert host.unit_files != []
    assert not any(
        tuple(event)[:2] == ("systemctl", "--user") for event in host.events
    ), host.events


# -----------------------------------------------------------------------------
# T029 / US3-S5, FR-012 — dispatch with no owner is a refusal, not a skip
# -----------------------------------------------------------------------------


def test_dispatch_with_no_owner_is_a_refusal_not_a_skipped_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US3-S5 (plan trap 7): `roadmap pause` reports success for a run it only signalled.

    `factory/cli/roadmap.py:343-351` says so itself — a run with no schedule the
    client can name is signalled, with the caveat on stderr rather than in the
    output the operator asked for. Continuing past that is how a schedule goes on
    dispatching into a host being dismantled, so teardown refuses instead, and
    never reaches the signal at all.
    """
    host = _host(
        tmp_path,
        monkeypatch,
        schedules=[],
        workflows={UNOWNED_RUN: FakeWorkflow(None, datetime(2026, 8, 15, 15, tzinfo=timezone.utc))},
    )

    result = drive(host.request())

    assert result.code == EXIT_USER
    assert f"teardown stopped at step 1 of 3, {PAUSE_DISPATCH}" in result.stderr
    assert UNOWNED_RUN in result.stderr
    assert "no schedule" in result.stderr
    assert "already done: nothing" in result.stderr

    # Not a skipped step: nothing was signalled, and the next step never acted.
    assert host.client.signals == []
    assert registry.load_registry().get(SLUG) is not None
    assert host.unit_files != []


# -----------------------------------------------------------------------------
# T030 / US3-S6, FR-017 — the control: the three commands did not move
# -----------------------------------------------------------------------------


def test_repo_forget_command_still_takes_one_namespace_and_uses_its_client_seam(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US3-S6: driven exactly as `tests/test_ergane_repo_forget.py` drives it.

    The `--clean-runtime` path is the one that reads capacity, so it is the one
    that proves `factory/cli/repo.py`'s `_temporal_client_factory` is still how
    this command reaches Temporal — the seam the committed tests replace.
    """
    signature = inspect.signature(repo_forget_command)
    assert list(signature.parameters) == ["args"]
    assert signature.parameters["args"].annotation == "argparse.Namespace"

    repo = make_repo(tmp_path, name=SLUG)
    (repo / ".ergane").mkdir(exist_ok=True)
    (repo / ".ergane" / "doctor.db").write_text("seeded\n", encoding="utf-8")
    registry.register(SLUG, repo)
    control_plane = FakeScheduleServer()
    seed(control_plane, desired_for(repo, slug=SLUG))
    bind_offline_seams(monkeypatch, schedules=control_plane)

    opened: list[str] = []

    class _IdleFloor:
        """Just enough client for the capacity read `_running_epic_ids` makes."""

        def list_workflows(self, query: str | None = None, **kwargs: Any) -> Any:
            async def none() -> Any:
                return
                yield  # pragma: no cover - an empty async iterator

            return none()

    async def factory() -> Any:
        opened.append("client")
        return _IdleFloor()

    # Only the seam at `factory/cli/repo.py:94` is replaced: `_running_epic_ids`
    # itself runs for real, so this asserts the path and not just the attribute.
    monkeypatch.setattr(repo_module, "_temporal_client_factory", factory)

    code = repo_forget_command(
        argparse.Namespace(
            slug=SLUG,
            clean_runtime=True,
            export=None,
            lock_timeout=registry.DEFAULT_LOCK_TIMEOUT_S,
        )
    )

    assert code == EXIT_OK
    assert opened == ["client"], "the capacity read did not go through the module seam"
    assert registry.load_registry().get(SLUG) is None


def test_uninstall_still_honours_run_and_open_epics(tmp_path: Path) -> None:
    """US3-S6: `uninstall()`'s two injection parameters are where they were."""
    parameters = inspect.signature(uninstall).parameters
    assert list(parameters) == ["layout", "run", "open_epics"]

    layout = resolve_layout(
        home=tmp_path / "home", generated_dir=tmp_path / "state" / "supervision"
    )
    install(layout, run=lambda argv: CommandResult(0, ""))

    with pytest.raises(OperatorError, match="epic-042"):
        uninstall(layout, run=lambda argv: CommandResult(0, ""), open_epics=lambda: ("epic-042",))

    issued: list[tuple[str, ...]] = []
    report = uninstall(
        layout,
        run=lambda argv: issued.append(tuple(argv)) or CommandResult(0, ""),
        open_epics=lambda: (),
    )

    assert ("systemctl", "--user", "daemon-reload") in issued
    assert "ergane-worker.service" in report.removed


def test_roadmap_pause_command_still_pauses_the_schedule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US3-S6: invoked directly, on a schedule-owned roadmap, it is unchanged.

    Byte-for-byte the sentence `tests/test_roadmap_schedule_discovery.py` pasted
    when 046 landed it.
    """
    bind_offline_seams(monkeypatch, schedules=FakeScheduleServer())
    client = FakeTemporalClient(
        schedules=[FakeSchedule(id="ergane-roadmap", action_workflow_id=BARE_ID)]
    )

    async def connect(target_host: str, **kwargs: Any) -> FakeTemporalClient:
        return client

    monkeypatch.setattr(temporalio.client.Client, "connect", connect)

    old_out, out = sys.stdout, io.StringIO()
    try:
        sys.stdout = out
        code = asyncio.run(
            roadmap_pause_command(argparse.Namespace(specs_root=str(tmp_path / "specs")))
        )
    finally:
        sys.stdout = old_out

    assert code == EXIT_OK
    assert client.schedule_calls == [("pause", "ergane-roadmap")]
    assert out.getvalue() == (
        "paused schedule ergane-roadmap: the schedule owns dispatch, so no "
        "further run will start\n"
    )


def test_roadmap_py_is_not_edited_by_this_story() -> None:
    """Plan trap 14: 085's US3 is rewriting that file in the same landing window.

    Teardown imports `roadmap_pause_command` and adds no seam to the module it
    lives in, so the two stories cannot collide at landing.
    """
    source = Path(inspect.getsourcefile(teardown) or "").read_text(encoding="utf-8")
    assert "roadmap_pause_command" in source
    roadmap_source = Path(
        inspect.getsourcefile(sys.modules["factory.cli.roadmap"]) or ""
    ).read_text(encoding="utf-8")
    assert "Client.connect" in roadmap_source
    assert roadmap_source.count("Client.connect") == 1
    assert "_pause_command_factory" not in roadmap_source


# -----------------------------------------------------------------------------
# T031 / US3-S7, FR-018 — teardown will not remove the installation it runs from
# -----------------------------------------------------------------------------


def test_a_removal_target_containing_this_installation_is_refused(host: Host) -> None:
    """US3-S7 (plan trap 8): refused before any step acts, naming the path.

    `resolve_layout()` already derives the two paths that *are* this
    installation, by construction rather than by literal. The refusal is one
    containment test against them, in the shape of `_refuse_while_epics_run`, and
    no flag overrides it.
    """
    containing = host.layout.install_root.parent
    request = host.request(layout=replace(host.layout, generated_dir=containing))

    result = drive(request)

    assert result.code == EXIT_USER
    assert str(containing) in result.stderr
    assert str(host.layout.install_root) in result.stderr
    assert "the installation this process is running from" in result.stderr

    # Refused before any step acted: nothing paused, nothing forgotten, nothing gone.
    assert host.events == []
    assert registry.load_registry().get(SLUG) is not None
    assert host.unit_files != []
    assert host.schedules.schedules != {}


def test_the_interpreters_directory_is_the_other_half_of_the_refusal(host: Host) -> None:
    """US3-S7: `factory/supervision/units.py:186`'s half, asserted separately.

    Two derived paths, two ways to delete the process that is running — the
    control that the guard is not passing on the install root alone.
    """
    containing = host.layout.interpreter.parent.parent
    request = host.request(layout=replace(host.layout, generated_dir=containing))

    result = drive(request)

    assert result.code == EXIT_USER
    assert str(containing) in result.stderr
    assert host.events == []


def test_the_refusal_has_no_escape_flag() -> None:
    """US3-S7 / FR-018: no flag may override it, so none is offered."""
    parser = argparse.ArgumentParser()
    teardown.add_uninstall_parser(parser.add_subparsers(dest="noun"))
    flags = {
        option
        for action in parser._subparsers._group_actions[0].choices["uninstall"]._actions
        for option in action.option_strings
    }
    assert "--check" in flags
    assert not {"--force", "--anyway", "--yes", "--i-know-what-im-doing"} & flags


# -----------------------------------------------------------------------------
# The noun is discovered, not registered (FR-009)
# -----------------------------------------------------------------------------


def test_the_bare_listing_finds_the_noun_with_no_registration_anywhere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-009: `factory/cli/main.py:65` walks the package; adding one is adding a file."""
    listing = invoke([])
    assert listing.code == EXIT_OK, listing.stderr
    assert "uninstall" in listing.stdout

    helped = invoke(["uninstall", "--help"])
    assert helped.code == EXIT_OK
    assert "--check" in helped.stdout


def test_the_command_refuses_before_acting_through_the_cli(
    host: Host, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US3-S7 end to end: a non-zero exit from `ergane uninstall`, on stderr.

    Driven through the dispatcher with the request seam bound, because
    `resolve_layout()`'s defaults name the operator's own `~/.config/systemd/user`
    and this suite runs on the host the factory is installed on.
    """
    request = host.request(layout=replace(host.layout, generated_dir=host.layout.install_root))
    monkeypatch.setattr(teardown, "_request_for", lambda args: replace(request, check=bool(args.check)))

    result = invoke(["uninstall"])

    assert result.code == EXIT_USER
    assert str(host.layout.install_root) in result.stderr
    assert host.events == []


# =============================================================================
# Pasted evidence — constitution VIII / D-037. Every block below is verbatim
# from this worktree, captured by the test named beside it; `/tmp/…/` elides one
# pytest tmp path prefix and nothing else.
# =============================================================================
#
# T038 (SC-006), first the real verb through the real dispatcher, in this
# worktree — no fixture, no fake, one noun module the discovery loop found with
# no registration anywhere (FR-009):
#
#     $ uv run ergane
#     install      configure and verify the control plane
#     worker       supervise the worker and the operator bridge with systemd
#     uninstall    take Ergane off this host, in the order that is safe
#     init         join a git repository to Ergane
#     …
#     $ uv run ergane uninstall --check
#     teardown plan, 3 steps in the order the table declares; --check performs none of them:
#     1/3 pause dispatch: nothing to do: no repository is registered on this host, so nothing here dispatches
#     2/3 forget repositories: nothing to do: no repository is registered
#     3/3 stop and remove units: nothing to do: no file this engine wrote is still here
#     --check performed none of it: nothing was written, removed, stopped or signalled
#     exit=0
#
# T038 (SC-006) — `ergane uninstall --check` on a host with dispatch running, a
# registered repository and installed units
# (test_check_writes_removes_stops_and_signals_nothing):
#
#     teardown plan, 3 steps in the order the table declares; --check performs none of them:
#     1/3 pause dispatch: pause dispatch for /tmp/…/widgets/specs (schedule ergane-roadmap-widgets)
#     2/3 forget repositories: forget 1 registered repository: widgets
#     3/3 stop and remove units: stop and remove 6 file(s) this engine wrote, under /tmp/…/home/.config/systemd/user and /tmp/…/state/supervision
#     --check performed none of it: nothing was written, removed, stopped or signalled
#
# and, beside it, the substituted recording step table showing it empty
# (test_check_reaches_no_acting_half): `acted == []` while
# `surveyed == ["pause dispatch", "forget repositories", "stop and remove units"]`
# — every survey ran, no acting half was reached. The direct assertions on the
# same host, in the same run as the plan above:
#
#     host.events == []          # the shared log of every schedule pause,
#                                # schedule delete and systemctl command: empty
#     host.client.signals == []  # nothing signalled
#     host.schedules.schedules != {}                  # the schedule survives
#     registry.load_registry().get("widgets") is not None
#     sorted(host.unit_files) == before               # every unit file survives
#
# The same host then torn down for real, from the same table — note the `N/3`
# lines are identical to the plan above, which is what
# `plan_lines(checked.stdout) == plan_lines(performed.stdout)` asserts:
#
#     teardown, 3 steps in the order the table declares:
#     1/3 pause dispatch: pause dispatch for /tmp/…/widgets/specs (schedule ergane-roadmap-widgets)
#         paused schedule ergane-roadmap-widgets: the schedule owns dispatch, so no further run will start
#     2/3 forget repositories: forget 1 registered repository: widgets
#         deleted roadmap schedule ergane-roadmap-widgets
#         forgot widgets (/tmp/…/widgets); the repository itself is untouched
#     3/3 stop and remove units: stop and remove 6 file(s) this engine wrote, under /tmp/…/home/.config/systemd/user and /tmp/…/state/supervision
#         uninstalled:
#           ergane-worker.service: stopped, disabled, removed
#           ergane-bridge.service: stopped, disabled, removed
#           ergane-probe.timer: stopped, disabled, removed
#           ergane.slice: stopped, removed
#           ergane-probe.service: removed
#           ergane-run.sh: removed
#     teardown done: pause dispatch, forget repositories, stop and remove units
#
# and the one event log the three fakes share, in the order it was written
# (test_teardown_performs_its_steps_in_the_declared_order) — the ordering
# assertion is against these acts, not against the sentences above:
#
#     ('pause', 'ergane-roadmap-widgets')
#     ('delete', 'ergane-roadmap-widgets')
#     ('systemctl', '--user', 'disable', '--now', 'ergane-worker.service')
#     ('systemctl', '--user', 'disable', '--now', 'ergane-bridge.service')
#     ('systemctl', '--user', 'disable', '--now', 'ergane-probe.timer')
#     ('systemctl', '--user', 'stop', 'ergane.slice')
#     ('systemctl', '--user', 'daemon-reload')
#
# FR-011, a step with nothing to do (test_a_step_with_nothing_to_do_says_so_by_name):
#
#     teardown, 3 steps in the order the table declares:
#     1/3 pause dispatch: nothing to do: no repository is registered on this host, so nothing here dispatches
#     2/3 forget repositories: nothing to do: no repository is registered
#     3/3 stop and remove units: nothing to do: no file this engine wrote is still here
#     teardown done: pause dispatch (nothing to do), forget repositories (nothing to do), stop and remove units (nothing to do)
#
# T039 (SC-007) — teardown stopped by a refused step, stderr
# (test_a_refused_step_stops_the_verb_and_names_what_was_done):
#
#     ergane: teardown stopped at step 3 of 3, stop and remove units: refusing to uninstall while epic-011-agent-sandbox is in flight: removing the worker mid-epic strands the attempt it is running; let it land, or kill it first
#       already done: pause dispatch, forget repositories
#       not attempted: none
#
# and the refusal US3-S5 exists for — dispatch whose owner cannot be named, which
# `ergane roadmap pause` would have reported as a success
# (test_dispatch_with_no_owner_is_a_refusal_not_a_skipped_step). Note that step
# one is named and the stdout above it stops at the header: no step acted.
#
#     teardown, 3 steps in the order the table declares:
#     ergane: teardown stopped at step 1 of 3, pause dispatch: dispatch for /tmp/…/widgets/specs is run roadmap-specs-2026-08-15T15:00:00Z, and no schedule this client can name owns it. Pausing that run would report success while the next tick started a fresh one, so teardown will not read it as a stopped floor: stop whatever schedules that run, then re-run `ergane uninstall`
#       already done: nothing
#       not attempted: forget repositories, stop and remove units
#
# T040 (SC-008) — the control, both ways, in one command each: the base commit
# this story branched from (701bc0d) and its tip, printed side by side. Two
# identical lines is the evidence; a sentence saying they match is not
# (plan trap 12).
#
#     $ for r in 701bc0d HEAD; do git show $r:factory/cli/repo.py | sed -n '94p;308p'; done
#     _temporal_client_factory: Callable[[], Awaitable[Client]] = _open_client
#     def repo_forget_command(args: argparse.Namespace) -> int:
#     _temporal_client_factory: Callable[[], Awaitable[Client]] = _open_client
#     def repo_forget_command(args: argparse.Namespace) -> int:
#
#     $ for r in 701bc0d HEAD; do git show $r:factory/supervision/units.py | sed -n '573,578p'; done
#     def uninstall(
#         layout: InstallLayout,
#         *,
#         run: Callable[[Sequence[str]], CommandResult] | None = None,
#         open_epics: Callable[[], Sequence[str]] | None = None,
#     ) -> UninstallReport:
#     def uninstall(
#         layout: InstallLayout,
#         *,
#         run: Callable[[Sequence[str]], CommandResult] | None = None,
#         open_epics: Callable[[], Sequence[str]] | None = None,
#     ) -> UninstallReport:
#
#     $ git diff --stat 701bc0d HEAD -- factory/cli/roadmap.py
#     (no output — the file this story may not touch, plan trap 14)
#     $ git diff --stat 701bc0d HEAD
#      factory/cli/nouns/uninstall.py           |  13 +
#      factory/cli/uninstall.py                 | 491 ++++++++++++++++++
#      tests/test_ergane_status.py              |  13 +
#      tests/test_teardown_owns_the_ordering.py | 835 +++++++++++++++++++++++++++
#      4 files changed, 1352 insertions(+)
#
# and the three behaviours themselves, invoked directly rather than through
# teardown (test_repo_forget_command_still_takes_one_namespace_and_uses_its_client_seam,
# test_uninstall_still_honours_run_and_open_epics,
# test_roadmap_pause_command_still_pauses_the_schedule):
#
#     inspect.signature(repo_forget_command)        -> (args: 'argparse.Namespace') -> int
#     opened                                        -> ['client']   # through repo.py:94
#     list(inspect.signature(uninstall).parameters) -> ['layout', 'run', 'open_epics']
#     roadmap_pause_command(ns) stdout              -> paused schedule ergane-roadmap: the schedule owns dispatch, so no further run will start
#     client.schedule_calls                         -> [('pause', 'ergane-roadmap')]
#
# T041 (SC-009) — the self-removal refusal, stderr, with the containing path in
# it (test_a_removal_target_containing_this_installation_is_refused). Exit code
# is EXIT_USER (1), and the paths are this worktree's real ones:
#
#     ergane: refusing to run teardown: step 'stop and remove units' would remove /home/admin/code/ergane/.factory/worktrees/083-teardown-is-a-verb-that-names-what-it-removed, which contains the install root /home/admin/code/ergane/.factory/worktrees/083-teardown-is-a-verb-that-names-what-it-removed/us3 — the installation this process is running from. Teardown would delete itself mid-run and leave a host no report describes; there is no flag for this
#
# with `host.events == []`, the registry entry present, the schedule present and
# every unit file still on disk: nothing was paused, forgotten or removed.
#
# The gate `factory.yaml` declares, in this worktree, with this file and the two
# modules it drives in place:
#
#     $ uv run pytest -q
#     4320 passed, 52 skipped, 6 warnings in 338.67s (0:05:38)
