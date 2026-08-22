"""083-US2: `worker uninstall` names what it removed, and leaves nothing loaded.

The exact-inverse-of-install contract held in the field; what failed was the
audit. `removed 6 file(s)` says that six things went away without saying which
six, and folds deletion and deactivation into one word when they are different
acts — `ergane.slice` was found still loaded and active after an uninstall that
had already deleted its file, and had to be stopped by hand.

Everything here is asserted against a recording fake. `no_real_commands` is
autouse and makes `units._run_command` raise, because the units this module
generates are the units this host is running: a test that forgot its fake would
stop the worker running this attempt rather than fail.

Written before the code, and failing on the two claims this story adds — the
report's shape and the slice's stop:

    $ PYTHONDONTWRITEBYTECODE=1 uv run pytest -q \
        tests/test_worker_uninstall_prints_its_manifest.py --no-header
    E   AssertionError: ergane.slice is not on exactly one line of 'removed 6 file(s)'
    E   AssertionError: assert 'file(s)' not in 'removed 6 file(s)'
    E   KeyError: 'ergane-worker.service'
    E   AssertionError: uninstall never issued stop for ergane.slice: [...]
    E   AttributeError: 'UninstallReport' object has no attribute 'stopped'
    6 failed, 5 passed in 0.09s

The five that passed from the first run are the controls and the two lines this
story must *not* change: `ENABLE_TARGETS`, install's own command sequence, the
open-epic refusal, and the `kept` line that already named its files.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator, Sequence

import pytest

from factory.cli.errors import OperatorError
from factory.supervision.units import (
    BRIDGE_UNIT,
    ENABLE_TARGETS,
    PROBE_TIMER,
    PROBE_UNIT,
    SLICE_UNIT,
    TEMPORAL_UNIT,
    WORKER_UNIT,
    WRAPPER_NAME,
    CommandResult,
    InstallLayout,
    install,
    uninstall,
)


class FakeSystemctl:
    """Every command the engine would have run, in the order it ran them.

    A recorder rather than a mock: three assertions below are about *which*
    commands were issued and in what order — the slice's stop comes after the
    disables — and an order is only visible in a list.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, argv: Sequence[str]) -> CommandResult:
        self.calls.append(tuple(argv))
        return CommandResult(0)

    def index_of(self, verb: str, name: str) -> int:
        """Where `systemctl --user <verb> [--now] <name>` was issued."""
        for position, call in enumerate(self.calls):
            if verb in call and call[-1] == name:
                return position
        raise AssertionError(f"uninstall never issued {verb} for {name}: {self.calls}")


@pytest.fixture(autouse=True)
def no_real_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test here may run a command against the real user session."""

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


def acts_by_name(rendered: str) -> dict[str, list[str]]:
    """The report read back the way an operator reads it: one name per line.

    Parsed rather than asserted whole, so a test says which *name* is missing
    its acts instead of diffing two paragraphs.
    """
    found: dict[str, list[str]] = {}
    for line in rendered.splitlines():
        if ":" not in line:
            continue
        name, _, acts = line.partition(":")
        found[name.strip()] = [act.strip() for act in acts.split(",") if act.strip()]
    return found


# ============================================================================
# T014 / US2-S1 / FR-005 — every removed file is named, and no bare count
# ============================================================================


def test_the_report_names_every_removed_file_by_name(layout: InstallLayout) -> None:
    """A count is not an audit: it cannot be checked against a host."""
    install(layout, run=FakeSystemctl())

    report = uninstall(layout, run=FakeSystemctl(), open_epics=lambda: ())
    rendered = report.render()

    assert sorted(report.removed) == sorted(
        [BRIDGE_UNIT, PROBE_TIMER, PROBE_UNIT, SLICE_UNIT, WORKER_UNIT, WRAPPER_NAME]
    )
    for name in report.removed:
        naming = [line for line in rendered.splitlines() if name in line]
        assert len(naming) == 1, f"{name} is not on exactly one line of {rendered!r}"
        assert "removed" in naming[0]


def test_the_report_carries_no_bare_count(layout: InstallLayout) -> None:
    """`removed 6 file(s)` is the whole defect; it may not survive beside the
    names, because a reader who sees a count stops reading for names."""
    install(layout, run=FakeSystemctl())

    rendered = uninstall(layout, run=FakeSystemctl(), open_epics=lambda: ()).render()

    assert "file(s)" not in rendered
    assert re.search(r"\d", rendered) is None, rendered


# ============================================================================
# T015 / US2-S2 / FR-006 — per unit, which of stop, disable and remove
# ============================================================================


def test_the_report_says_which_acts_each_unit_received(layout: InstallLayout) -> None:
    """Deletion and deactivation are different acts with different failure
    modes: a unit file can be gone while systemd still holds the unit loaded,
    and one line reporting both is what hid the slice."""
    install(layout, run=FakeSystemctl())

    rendered = uninstall(layout, run=FakeSystemctl(), open_epics=lambda: ()).render()
    acts = acts_by_name(rendered)

    # Enabled units: `disable --now` is two acts in one command, and both are
    # named, followed by the deletion of the file.
    assert acts[WORKER_UNIT] == ["stopped", "disabled", "removed"]
    assert acts[BRIDGE_UNIT] == ["stopped", "disabled", "removed"]
    assert acts[PROBE_TIMER] == ["stopped", "disabled", "removed"]
    # The slice is never enabled (ENABLE_TARGETS), so it is stopped, not
    # disabled — the distinction this story exists to make visible.
    assert acts[SLICE_UNIT] == ["stopped", "removed"]
    # Neither enabled nor loaded: the probe service is pulled in by its timer,
    # and the wrapper is a shell script.
    assert acts[PROBE_UNIT] == ["removed"]
    assert acts[WRAPPER_NAME] == ["removed"]


def test_a_unit_the_engine_did_not_write_is_still_reported_as_kept(
    layout: InstallLayout,
) -> None:
    """The one line this story does not touch. An operator's hand-written unit
    of a colliding name may be the one keeping their host alive."""
    layout.unit_dir.mkdir(parents=True)
    theirs = layout.unit_dir / BRIDGE_UNIT
    theirs.write_text("[Service]\nExecStart=/usr/bin/true\n", encoding="utf-8")
    install(layout, run=FakeSystemctl())

    report = uninstall(layout, run=FakeSystemctl(), open_epics=lambda: ())

    assert report.kept == (BRIDGE_UNIT,)
    assert "left in place (not written by ergane): " + BRIDGE_UNIT in report.render()
    assert theirs.read_text(encoding="utf-8") == "[Service]\nExecStart=/usr/bin/true\n"


# ============================================================================
# T016 / US2-S3 / FR-007 — the slice is stopped, after the disables
# ============================================================================


def test_the_slice_is_stopped_after_the_enabled_units_are_disabled(
    layout: InstallLayout,
) -> None:
    """The slice survives its members as loaded/active because nothing is
    `WantedBy` it — it is pulled in by the `Slice=` lines of the units just
    stopped. That is what forced the hand-run stop. It goes after the disables
    because a slice cannot be stopped out from under a running member."""
    install(layout, run=FakeSystemctl())
    fake = FakeSystemctl()

    uninstall(layout, run=fake, open_epics=lambda: ())

    assert ("systemctl", "--user", "stop", SLICE_UNIT) in fake.calls
    stopped_at = fake.index_of("stop", SLICE_UNIT)
    disables = [i for i, call in enumerate(fake.calls) if "disable" in call]
    assert disables, f"nothing was disabled at all: {fake.calls}"
    assert stopped_at > max(disables)
    # And before the files go: systemd holds the parsed unit in memory, so a
    # file removed first leaves the unit up and invisible until reboot.
    assert fake.calls[-1] == ("systemctl", "--user", "daemon-reload")


def test_the_stop_of_the_slice_is_named_in_the_report(layout: InstallLayout) -> None:
    """A stop nobody can read is the state before this story: the operator ran
    `systemctl --user list-units 'ergane*'` to find out."""
    install(layout, run=FakeSystemctl())

    report = uninstall(layout, run=FakeSystemctl(), open_epics=lambda: ())

    assert SLICE_UNIT in report.stopped
    assert "stopped" in acts_by_name(report.render())[SLICE_UNIT]


def test_the_slice_is_not_stopped_when_install_never_wrote_it(
    layout: InstallLayout,
) -> None:
    """Provenance governs the stop exactly as it governs the deletion: an
    `ergane.slice` this engine did not write is not this engine's to stop."""
    layout.unit_dir.mkdir(parents=True)
    (layout.unit_dir / SLICE_UNIT).write_text("[Slice]\n", encoding="utf-8")
    install(layout, run=FakeSystemctl())
    fake = FakeSystemctl()

    report = uninstall(layout, run=fake, open_epics=lambda: ())

    assert ("systemctl", "--user", "stop", SLICE_UNIT) not in fake.calls
    assert SLICE_UNIT not in report.stopped
    assert SLICE_UNIT in report.kept


# ============================================================================
# T017 / US2-S4 / FR-007 — THE CONTROL: install did not move
# ============================================================================


def test_enable_targets_is_unchanged(layout: InstallLayout) -> None:
    """Fixing uninstall by changing install is the wrong repair.

    Neither the slice nor the probe *service* is enabled: the slice is pulled
    in by the `Slice=` lines that reference it and the probe service by its
    timer, so enabling either would declare a `WantedBy` systemd then has to
    reconcile. US2 stops the slice during *uninstall* and leaves that tuple
    exactly as it found it.
    """
    assert ENABLE_TARGETS == (WORKER_UNIT, BRIDGE_UNIT, TEMPORAL_UNIT, PROBE_TIMER)
    assert ENABLE_TARGETS == (
        "ergane-worker.service",
        "ergane-bridge.service",
        "ergane-temporal.service",
        "ergane-probe.timer",
    )
    assert SLICE_UNIT not in ENABLE_TARGETS
    assert PROBE_UNIT not in ENABLE_TARGETS


def test_install_enables_the_four_and_stops_nothing(layout: InstallLayout) -> None:
    """The control as a behaviour, not just a tuple: the slice's stop belongs
    to uninstall, and install may not have grown one."""
    fake = FakeSystemctl()

    install(layout, run=fake)

    assert fake.index_of("enable", WORKER_UNIT) >= 0
    assert [call for call in fake.calls if "stop" in call] == []
    assert [call for call in fake.calls if "disable" in call] == []


# ============================================================================
# T018 / US2-S5 / FR-008 — the refusal still precedes every systemd command
# ============================================================================


def test_an_epic_in_flight_refuses_and_stops_nothing(layout: InstallLayout) -> None:
    """A story that reorders the stops must not move the refusal off the front:
    a half-uninstall cannot be told from a whole one afterwards."""
    install(layout, run=FakeSystemctl())
    fake = FakeSystemctl()

    with pytest.raises(OperatorError) as raised:
        uninstall(layout, run=fake, open_epics=lambda: ("epic-083-teardown",))

    assert "epic-083-teardown" in str(raised.value)
    assert fake.calls == []
    assert (layout.unit_dir / SLICE_UNIT).is_file()
    assert (layout.unit_dir / WORKER_UNIT).is_file()


def test_the_epics_are_read_before_any_command_is_issued(
    layout: InstallLayout,
) -> None:
    """The read comes first and touches nothing, so the refusal costs nothing
    to take."""
    install(layout, run=FakeSystemctl())
    order: list[str] = []
    fake = FakeSystemctl()

    def epics() -> tuple[str, ...]:
        order.append("read the open epics")
        return ("epic-083-teardown",)

    def watched(argv: Sequence[str]) -> CommandResult:
        order.append(f"issued {' '.join(argv)}")
        return fake(argv)

    with pytest.raises(OperatorError):
        uninstall(layout, run=watched, open_epics=epics)

    assert order == ["read the open epics"]
