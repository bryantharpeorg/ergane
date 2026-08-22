"""082-US4: install writes the template only, and the legacy unit is retired.

Three claims, and the third is the one with teeth. **Install no longer writes
`ergane-worker.service`** (US4-S1/FR-006) — one deployment story, because two is
how skew comes back. **Uninstall still removes it** under the provenance rule it
applies to everything else (US4-S3/FR-006), which means an install that stopped
writing the file must go on remembering the digest of the one it wrote before,
or the operator's own teardown can never prove the file is the engine's.
**Migration off it is refused while an epic that predates versioning is open**
(US4-S2/FR-007), and what "predates versioning" means is T002's measurement
rather than a guess (`evidence/us1-t001-t002-probes.md`): such a run is *not*
stalled when a versioned worker becomes current —

    [pre-versioning run right after set-current]  behavior=UNSPECIFIED version='.'
    [part B final]  status=2 behavior=PINNED version='probe-082-mig2.mig-v1'

— it is adopted onto whatever is current at its next workflow task and pins
there. So the danger is not a stall: it is an epic finishing on code it did not
start with, plus the agents its attempts run inside the legacy unit's own
cgroup, which `disable --now` takes with it.

Nothing here reaches the host's session: `no_real_commands` is autouse, because
the unit this story retires is the unit this attempt is running under.

Written before the code, and failing on every claim it makes:

    $ PYTHONDONTWRITEBYTECODE=1 uv run pytest -q \
        tests/test_the_unversioned_unit_retires.py --no-header
    tests/test_the_unversioned_unit_retires.py:59: in <module>
        from factory.supervision.units import (
    E   ImportError: cannot import name 'LEGACY_WORKER_UNIT' from
    E   'factory.supervision.units'
    1 error in 0.09s
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Iterator, Sequence

import pytest

from factory.cli.errors import OperatorError
from factory.supervision.units import (
    BRIDGE_UNIT,
    ENABLE_TARGETS,
    LEGACY_WORKER_UNIT,
    PROBE_TIMER,
    SLICE_UNIT,
    WORKER_TEMPLATE_UNIT,
    CommandResult,
    InstallLayout,
    _digest,
    _read_manifest,
    _write_manifest,
    deployed_instances,
    generated_files,
    install,
    migrate_off_legacy_unit,
    uninstall,
    worker_instance,
)
from factory.versioning import OpenEpic, open_epic_from, strandable_epics

#: What a pre-082 install wrote to `ergane-worker.service`. Never compared
#: against anything the engine can still generate — provenance is the digest
#: recorded at install time — so all that matters is that an older engine wrote
#: this text and the manifest agrees.
LEGACY_TEXT = "[Unit]\nDescription=ergane — factory worker\n"

#: The build ids of two versions this host has deployed.
DEPLOYED = ("a1b2c3d", "9f8e7d6")


# --- fakes ------------------------------------------------------------------


class FakeSystemctl:
    """Every command the engine would have run, in the order it ran them."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, argv: Sequence[str]) -> CommandResult:
        self.calls.append(tuple(argv))
        return CommandResult(0)

    def issued(self, verb: str) -> list[str]:
        return [call[-1] for call in self.calls if verb in call]

    def index_of(self, verb: str, name: str) -> int:
        for position, call in enumerate(self.calls):
            if verb in call and call[-1] == name:
                return position
        raise AssertionError(f"never issued {verb} for {name}: {self.calls}")


@pytest.fixture(autouse=True)
def no_real_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    """The unit this story retires is the unit this attempt runs under."""

    def refuse(argv: Sequence[str]) -> CommandResult:
        raise AssertionError(f"a test reached the host's own session: {list(argv)}")

    monkeypatch.setattr("factory.supervision.units._run_command", refuse)


@pytest.fixture
def layout(tmp_path: Path) -> Iterator[InstallLayout]:
    """An installation whose every root is under `tmp_path`."""
    home = tmp_path / "home"
    interpreter = home / "code/ergane/.venv/bin/python3"
    interpreter.parent.mkdir(parents=True)
    interpreter.touch()
    yield InstallLayout(
        install_root=home / "code/ergane",
        interpreter=interpreter,
        unit_dir=home / ".config/systemd/user",
        generated_dir=home / ".local/state/ergane/supervision",
    )


def legacy_unit(layout: InstallLayout, *, text: str = LEGACY_TEXT, ours: bool = True) -> Path:
    """The state a pre-082 host is in: the unversioned unit on disk, and the
    manifest entry the install that wrote it left behind proving it is ours.

    `ours=False` is the operator's own unit of a colliding name — on disk with
    no provenance, which is the case teardown may not delete.
    """
    layout.unit_dir.mkdir(parents=True, exist_ok=True)
    layout.generated_dir.mkdir(parents=True, exist_ok=True)
    path = layout.unit_dir / LEGACY_WORKER_UNIT
    path.write_text(text, encoding="utf-8")
    if ours:
        recorded = _read_manifest(layout)
        recorded[LEGACY_WORKER_UNIT] = _digest(text)
        _write_manifest(layout, recorded)
    return path


def deployed(layout: InstallLayout, *build_ids: str) -> None:
    """The frozen checkouts `ergane worker deploy` left, one per live version."""
    for build_id in build_ids:
        layout.deployment_tree(build_id).mkdir(parents=True, exist_ok=True)


# ============================================================================
# T024 / US4-S1 / FR-006 — the generated set: the template, and not the unit
# ============================================================================


def test_install_writes_the_versioned_template_and_not_the_unversioned_unit(
    layout: InstallLayout,
) -> None:
    """US4-S1. Two deployment stories is how skew comes back, so there is one:
    every worker is an instance of the template, put there by deploy."""
    generated = [one.name for one in generated_files(layout)]

    assert WORKER_TEMPLATE_UNIT in generated
    assert LEGACY_WORKER_UNIT not in generated

    report = install(layout, run=FakeSystemctl())

    assert WORKER_TEMPLATE_UNIT in report.written
    assert LEGACY_WORKER_UNIT not in report.written
    assert (layout.unit_dir / WORKER_TEMPLATE_UNIT).is_file()
    assert not (layout.unit_dir / LEGACY_WORKER_UNIT).exists()


def test_install_never_enables_the_unversioned_worker(layout: InstallLayout) -> None:
    """The other half of not writing it: a unit that is not written must not be
    enabled either, and `ENABLE_TARGETS` is where that sneaks back in. A
    template cannot be enabled — its instances are, by deploy — so the worker
    leaves that tuple rather than being replaced in it."""
    fake = FakeSystemctl()

    install(layout, run=fake)

    assert LEGACY_WORKER_UNIT not in ENABLE_TARGETS
    assert WORKER_TEMPLATE_UNIT not in ENABLE_TARGETS
    assert LEGACY_WORKER_UNIT not in fake.issued("enable")
    assert sorted(fake.issued("enable")) == sorted([BRIDGE_UNIT, PROBE_TIMER])


def test_an_install_over_a_legacy_host_leaves_the_old_unit_alone_and_says_so(
    layout: InstallLayout,
) -> None:
    """Install is not the migration: it writes what it writes and touches
    nothing else. But an operator who is never told the retired unit is still
    there never runs the verb that removes it, so the report names it."""
    path = legacy_unit(layout)

    report = install(layout, run=FakeSystemctl())

    assert path.read_text(encoding="utf-8") == LEGACY_TEXT
    assert report.retired == (LEGACY_WORKER_UNIT,)
    assert LEGACY_WORKER_UNIT in report.render()
    assert "ergane worker migrate" in report.render()


# ============================================================================
# T025 / US4-S3 / FR-006 — uninstall removes exactly what install wrote, and
# what an install before this story wrote
# ============================================================================


def test_uninstall_removes_the_unversioned_unit_an_earlier_install_wrote(
    layout: InstallLayout,
) -> None:
    """US4-S3. The provenance rule extended to a name the engine no longer
    generates: the digest an older install recorded is what proves the file is
    the engine's, and it is still in the manifest to be read."""
    path = legacy_unit(layout)
    install(layout, run=FakeSystemctl())
    fake = FakeSystemctl()

    report = uninstall(layout, run=fake, open_epics=lambda: ())

    assert LEGACY_WORKER_UNIT in report.removed
    assert not path.exists()
    assert LEGACY_WORKER_UNIT in fake.issued("disable")
    assert fake.index_of("disable", LEGACY_WORKER_UNIT) < fake.index_of(
        "stop", SLICE_UNIT
    ), "the legacy unit is in the slice: it must be disabled before the slice stops"


def test_an_unversioned_unit_the_engine_did_not_write_is_kept(
    layout: InstallLayout,
) -> None:
    """The operator's own unit of a colliding name may be the one keeping their
    host alive, and it is reported rather than deleted — the same rule, on the
    one name for which the engine can no longer regenerate the text."""
    path = legacy_unit(layout, text="[Service]\nExecStart=/usr/bin/true\n", ours=False)
    install(layout, run=FakeSystemctl())
    fake = FakeSystemctl()

    report = uninstall(layout, run=fake, open_epics=lambda: ())

    assert LEGACY_WORKER_UNIT in report.kept
    assert LEGACY_WORKER_UNIT not in report.removed
    assert path.read_text(encoding="utf-8") == "[Service]\nExecStart=/usr/bin/true\n"
    assert LEGACY_WORKER_UNIT not in fake.issued("disable")


def test_install_keeps_the_provenance_of_the_unit_it_no_longer_writes(
    layout: InstallLayout,
) -> None:
    """The trap in retiring a generated file: install rewrites the manifest from
    what it just wrote, and a name it no longer writes falls out of it. The file
    stays on disk with nothing left to prove it by, and teardown has to keep
    somebody else's unit forever. Two installs, because one is the state the
    operator's host is actually in the day this lands."""
    legacy_unit(layout)

    install(layout, run=FakeSystemctl())
    install(layout, run=FakeSystemctl())

    assert _read_manifest(layout)[LEGACY_WORKER_UNIT] == _digest(LEGACY_TEXT)
    assert LEGACY_WORKER_UNIT in uninstall(
        layout, run=FakeSystemctl(), open_epics=lambda: ()
    ).removed


def test_uninstall_stops_and_disables_every_versioned_instance(
    layout: InstallLayout,
) -> None:
    """US4-S3: template, instances, and the legacy unit. An instance has no file
    of its own, so what teardown owes it is the disable; the checkouts deploy
    froze are how it knows which instances exist."""
    install(layout, run=FakeSystemctl())
    deployed(layout, *DEPLOYED)
    fake = FakeSystemctl()

    report = uninstall(layout, run=fake, open_epics=lambda: ())

    for build_id in DEPLOYED:
        unit = worker_instance(build_id)
        assert unit in fake.issued("disable")
        assert unit in report.stopped and unit in report.disabled
        assert fake.index_of("disable", unit) < fake.index_of("stop", SLICE_UNIT)
    assert deployed_instances(layout) == tuple(
        worker_instance(build_id) for build_id in sorted(DEPLOYED)
    )


def test_a_host_that_never_deployed_has_no_instances_to_stop(
    layout: InstallLayout,
) -> None:
    """The control: an absent deployments directory is a floor before its first
    deploy, not an error, and teardown issues nothing for it."""
    install(layout, run=FakeSystemctl())
    fake = FakeSystemctl()

    uninstall(layout, run=fake, open_epics=lambda: ())

    assert deployed_instances(layout) == ()
    assert [call for call in fake.calls if "ergane-worker@" in call[-1]] == []


# ============================================================================
# T026 / US4-S2 / FR-007 — the migration refusal, and what it is a refusal about
# ============================================================================


def test_an_epic_that_predates_versioning_is_the_one_that_can_be_stranded() -> None:
    """The decision, pure, as T002's transcript measured it.

    `behavior=UNSPECIFIED` is the server saying this run carries no versioning
    information at all — it was started by a worker that declared none. A run
    already pinned to a version is served by that version until it closes, and
    an auto-upgrading one has adopted the current version and says so; neither
    is what removing the unversioned worker would strand.
    """
    epics = (
        OpenEpic("epic-082-old"),
        OpenEpic("epic-083-pinned", behavior=1, build_id="a1b2c3d"),
        OpenEpic("epic-084-auto", behavior=2, build_id="a1b2c3d"),
        OpenEpic("epic-081-older"),
    )

    assert strandable_epics(epics) == ("epic-081-older", "epic-082-old")
    assert strandable_epics(()) == ()


def test_the_classification_reads_the_versioning_info_the_server_reports() -> None:
    """The read, against the shape `list_workflows` actually hands back.

    `raw_info.versioning_info` is where the server puts it; a classifier that
    read the workflow *type* or the task queue would call every epic
    pre-versioning and refuse every migration forever.
    """



    def execution(epic_id: str, behavior: int, build_id: str) -> SimpleNamespace:
        return SimpleNamespace(
            id=epic_id,
            raw_info=SimpleNamespace(
                versioning_info=SimpleNamespace(
                    behavior=behavior,
                    deployment_version=SimpleNamespace(build_id=build_id),
                )
            ),
        )

    pinned = open_epic_from(execution("epic-082-pinned", 1, "a1b2c3d"))
    old = open_epic_from(execution("epic-082-old", 0, ""))

    assert pinned == OpenEpic("epic-082-pinned", behavior=1, build_id="a1b2c3d")
    assert old == OpenEpic("epic-082-old")
    assert strandable_epics([pinned, old]) == ("epic-082-old",)


def test_migration_is_refused_by_name_while_a_pre_versioning_epic_is_open(
    layout: InstallLayout,
) -> None:
    """US4-S2/FR-007. `disable --now` takes the unit's cgroup with it — the
    attempts and the agents inside them — and what survives is adopted onto
    whatever version is current next. So the epic is named, nothing is touched."""
    path = legacy_unit(layout)
    install(layout, run=FakeSystemctl())
    fake = FakeSystemctl()

    with pytest.raises(OperatorError) as raised:
        migrate_off_legacy_unit(
            layout,
            run=fake,
            open_epics=lambda: (
                OpenEpic("epic-053-skew"),
                OpenEpic("epic-082-pinned", behavior=1, build_id="a1b2c3d"),
            ),
        )

    assert "epic-053-skew" in str(raised.value)
    assert "epic-082-pinned" not in str(raised.value)
    assert LEGACY_WORKER_UNIT in str(raised.value)
    assert fake.calls == []
    assert path.is_file()


def test_the_open_epics_are_read_before_anything_is_touched(
    layout: InstallLayout,
) -> None:
    """A disable issued before the refusal is a half-migration, and there is no
    verb that puts the unversioned worker back."""
    legacy_unit(layout)
    install(layout, run=FakeSystemctl())
    order: list[str] = []

    def epics() -> tuple[OpenEpic, ...]:
        order.append("read the open epics")
        return (OpenEpic("epic-053-skew"),)

    def watched(argv: Sequence[str]) -> CommandResult:
        order.append(f"issued {' '.join(argv)}")
        return CommandResult(0)

    with pytest.raises(OperatorError):
        migrate_off_legacy_unit(layout, run=watched, open_epics=epics)

    assert order == ["read the open epics"]


def test_migration_removes_the_unversioned_unit_once_nothing_predates_versioning(
    layout: InstallLayout,
) -> None:
    """The happy path (SC-004): stopped and disabled first, because systemd
    holds the parsed unit in memory and a file deleted out from under a running
    one leaves it up and invisible to `disable` until the next boot."""
    path = legacy_unit(layout)
    install(layout, run=FakeSystemctl())
    fake = FakeSystemctl()

    report = migrate_off_legacy_unit(
        layout,
        run=fake,
        open_epics=lambda: (OpenEpic("epic-082-pinned", behavior=1, build_id="a1b2c3d"),),
    )

    assert not path.exists()
    assert report.removed == (LEGACY_WORKER_UNIT,)
    assert report.acts(LEGACY_WORKER_UNIT) == ("stopped", "disabled", "removed")
    assert fake.calls[0] == (
        "systemctl", "--user", "disable", "--now", LEGACY_WORKER_UNIT,
    )
    assert fake.calls[-1] == ("systemctl", "--user", "daemon-reload")
    assert LEGACY_WORKER_UNIT in report.render()
    # The template and everything else install wrote are untouched: this verb
    # retires one unit, it does not tear the floor down.
    assert (layout.unit_dir / WORKER_TEMPLATE_UNIT).is_file()
    assert (layout.unit_dir / BRIDGE_UNIT).is_file()


def test_migration_leaves_an_unversioned_unit_the_engine_did_not_write(
    layout: InstallLayout,
) -> None:
    """Provenance governs the removal here exactly as it governs teardown's."""
    path = legacy_unit(layout, text="[Service]\nExecStart=/usr/bin/true\n", ours=False)
    install(layout, run=FakeSystemctl())
    fake = FakeSystemctl()

    report = migrate_off_legacy_unit(layout, run=fake, open_epics=lambda: ())

    assert report.removed == ()
    assert report.kept == (LEGACY_WORKER_UNIT,)
    assert path.is_file()
    assert "left in place" in report.render()


def test_a_migrated_host_converges_and_never_asks_temporal_again(
    layout: InstallLayout,
) -> None:
    """Re-running the verb is the recovery, so it has to be free: with nothing
    left to retire there is nothing to decide, and a refusal about an epic
    nobody is going to strand is noise."""
    legacy_unit(layout)
    install(layout, run=FakeSystemctl())
    migrate_off_legacy_unit(layout, run=FakeSystemctl(), open_epics=lambda: ())

    def refuse() -> tuple[OpenEpic, ...]:
        raise AssertionError("asked Temporal with nothing to retire")

    again = migrate_off_legacy_unit(layout, run=FakeSystemctl(), open_epics=refuse)

    assert again.removed == () and again.kept == ()
    assert "nothing to retire" in again.render()
    assert LEGACY_WORKER_UNIT not in _read_manifest(layout)


def test_the_verb_prints_the_report(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """`ergane worker migrate`, thin like every other verb of this noun."""
    from factory.cli.main import main as ergane_main
    from factory.supervision.units import RetirementReport

    def fake_migration(layout: InstallLayout) -> RetirementReport:
        return RetirementReport(
            removed=(LEGACY_WORKER_UNIT,),
            kept=(),
            stopped=(LEGACY_WORKER_UNIT,),
            disabled=(LEGACY_WORKER_UNIT,),
        )

    monkeypatch.setattr(
        "factory.supervision.units.migrate_off_legacy_unit", fake_migration
    )

    assert ergane_main(["worker", "migrate"]) == 0
    assert LEGACY_WORKER_UNIT in capsys.readouterr().out
