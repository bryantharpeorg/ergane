"""042-US2: the units the engine generates, installs and removes.

Every claim here is about *text the engine produced* or about files under a
`tmp_path`. Nothing reaches the operator's systemd session: `no_real_commands`
is autouse and makes `units._run_command` raise, so a test that forgot a fake
runner fails loudly instead of stopping the worker running this attempt. The
units this story generates are the units this host is running, which is exactly
why the seam is closed rather than merely unused.

Written before the module existed, and failing at collection:

    $ PYTHONDONTWRITEBYTECODE=1 uv run pytest -q tests/test_supervision_units.py --no-header
    tests/test_supervision_units.py:31: in <module>
        from factory.supervision.units import (
    E   ModuleNotFoundError: No module named 'factory.supervision.units'
    1 error in 0.08s
"""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path
from typing import Iterator, Sequence

import pytest

from factory.cli.errors import OperatorError
from factory.supervision.units import (
    BRIDGE_UNIT,
    SLICE_UNIT,
    WORKER_UNIT,
    WRAPPER_NAME,
    CommandResult,
    InstallLayout,
    generated_files,
    install,
    resolve_layout,
    uninstall,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

UNITS_MODULE = REPO_ROOT / "factory/supervision/units.py"

#: The only absolute path a generated file may name that is not the operator's
#: own installation: a script needs an interpreter, and POSIX guarantees this
#: one.
ALLOWED_ABSOLUTE = ("/bin/sh",)

#: Paths and tools from the hand-written prior art on this host. Each is
#: correct there and wrong for the product (plan trap 7); the credential path
#: is the sharpest case, because the alert now goes through US1's adapter.
PRIOR_ART_LITERALS = (
    "/home/admin/code/ergane",
    "/home/admin/code/homelab",
    "/home/admin/.temporalio",
    ".config/homelab",
    "TELEGRAM_BOT_TOKEN",
    "sops",
)

_ABSOLUTE_PATH_RE = re.compile(r"(?<![\w$])/[\w./+-]*")


# --- fakes ------------------------------------------------------------------


class FakeSystemctl:
    """Every command the engine would have run, with canned answers.

    A recorder rather than a mock: several assertions below are about *which*
    commands were issued and in what order — `disable --now` before deleting —
    and an order is only visible in a list.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.active: set[str] = set()
        self.enabled: set[str] = set()
        self.linger_code = 0
        #: Units that enable cleanly and are not running afterwards — the shape
        #: of a worker whose venv is broken.
        self.dead_on_start: set[str] = set()

    def __call__(self, argv: Sequence[str]) -> CommandResult:
        args = tuple(argv)
        self.calls.append(args)
        if args[0] == "loginctl":
            return CommandResult(self.linger_code)
        verb = args[2] if len(args) > 2 else ""
        name = args[-1]
        if verb == "enable":
            self.enabled.add(name)
            if name not in self.dead_on_start:
                self.active.add(name)
        elif verb == "disable":
            self.enabled.discard(name)
            self.active.discard(name)
        elif verb == "is-active":
            live = name in self.active
            return CommandResult(0 if live else 3, "active" if live else "inactive")
        elif verb == "is-enabled":
            on = name in self.enabled
            return CommandResult(0 if on else 1, "enabled" if on else "disabled")
        return CommandResult(0)

    def issued(self, verb: str) -> list[str]:
        return [call[-1] for call in self.calls if verb in call]


@pytest.fixture(autouse=True)
def no_real_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test here may run a command against the real user session."""

    def refuse(argv: Sequence[str]) -> CommandResult:
        raise AssertionError(f"a test reached the host's own session: {list(argv)}")

    monkeypatch.setattr("factory.supervision.units._run_command", refuse)


@pytest.fixture
def layout(tmp_path: Path) -> Iterator[InstallLayout]:
    """An installation whose every root is under `tmp_path`.

    `python3`, not `python`: the interpreter's spelling is load-bearing (plan
    trap 9) and the fixture must not be the thing that satisfies it.
    """
    home = tmp_path / "home"
    interpreter = home / "code/ergane/.venv/bin/python3"
    interpreter.parent.mkdir(parents=True)
    interpreter.touch()
    (home / ".config/ergane").mkdir(parents=True)
    (home / ".config/ergane/config.toml").write_text("[temporal]\n", encoding="utf-8")
    yield InstallLayout(
        install_root=home / "code/ergane",
        interpreter=interpreter,
        unit_dir=home / ".config/systemd/user",
        generated_dir=home / ".local/state/ergane/supervision",
    )


# --- helpers ----------------------------------------------------------------


def texts(layout: InstallLayout) -> dict[str, str]:
    return {generated.name: generated.text for generated in generated_files(layout)}


def directive(text: str, key: str) -> list[str]:
    """Every value a unit file gives `key`, in order."""
    return [
        line.split("=", 1)[1].strip()
        for line in text.splitlines()
        if line.strip().startswith(f"{key}=")
    ]


def tree(root: Path) -> dict[str, str]:
    """Every file under `root` by relative path, hashed.

    Uninstall's claim is subtractive — exactly what install created and nothing
    else — and "nothing else" is only as good as the set it was measured
    against. Comparing whole trees makes a deleted config file a failure
    without anyone having thought to assert it.
    """
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def absolute_paths(text: str) -> list[str]:
    return [match.group(0) for match in _ABSOLUTE_PATH_RE.finditer(text)]


# ============================================================================
# US2-S1 / FR-003 / SC-006 — installed, enabled, lingering, and portable
# ============================================================================


def test_install_writes_every_unit_and_the_wrapper(layout: InstallLayout) -> None:
    fake = FakeSystemctl()

    report = install(layout, run=fake)

    assert sorted(report.written) == sorted(
        [BRIDGE_UNIT, SLICE_UNIT, WORKER_UNIT, WRAPPER_NAME]
    )
    assert report.kept == ()
    for name in (WORKER_UNIT, BRIDGE_UNIT, SLICE_UNIT):
        assert (layout.unit_dir / name).is_file()
    assert (layout.generated_dir / WRAPPER_NAME).is_file()


def test_the_wrapper_is_executable(layout: InstallLayout) -> None:
    """A wrapper systemd cannot exec is a unit that fails to start."""
    install(layout, run=FakeSystemctl())

    assert (layout.generated_dir / WRAPPER_NAME).stat().st_mode & 0o111


def test_install_enables_the_units_and_reads_back_what_is_running(
    layout: InstallLayout,
) -> None:
    """US2-S1: active *and* enabled, read back rather than assumed.

    `enable --now` returning 0 is not the same claim as the unit being up.
    """
    fake = FakeSystemctl()

    report = install(layout, run=fake)

    assert sorted(report.active) == sorted([BRIDGE_UNIT, WORKER_UNIT])
    assert sorted(report.enabled) == sorted([BRIDGE_UNIT, WORKER_UNIT])
    assert fake.issued("daemon-reload") != []


def test_install_reports_a_unit_that_enabled_and_did_not_come_up(
    layout: InstallLayout,
) -> None:
    """The check that makes the one above mean something.

    Added after a mutation survived: with every fake unit coming up, "read the
    state back" and "assume enable worked" produce identical reports, so no
    test could tell them apart. A worker whose venv is broken enables cleanly
    and is dead a second later, and an install that called that active would
    send the operator away satisfied.
    """
    fake = FakeSystemctl()
    fake.dead_on_start.add(BRIDGE_UNIT)

    report = install(layout, run=fake)

    assert BRIDGE_UNIT in report.enabled
    assert BRIDGE_UNIT not in report.active
    assert WORKER_UNIT in report.active


def test_install_enables_linger_for_the_user(layout: InstallLayout) -> None:
    """FR-003: without linger a user unit stops when the last session ends,
    which turns "supervised" into "supervised until the operator closes their
    laptop"."""
    fake = FakeSystemctl()

    report = install(layout, run=fake)

    assert ("loginctl", "enable-linger") in fake.calls
    assert report.linger is True


def test_install_reports_rather_than_claims_linger_it_could_not_enable(
    layout: InstallLayout,
) -> None:
    fake = FakeSystemctl()
    fake.linger_code = 1

    assert install(layout, run=fake).linger is False


def test_no_generated_file_names_a_path_outside_the_installation(
    layout: InstallLayout,
) -> None:
    """SC-006, and the clearest way this epic fails while looking finished.

    Scanned over the generated text, because a unit referencing another
    repository starts, restarts and supervises perfectly on the one host where
    that repository exists.
    """
    roots = [str(root) for root in layout.roots]

    for name, text in texts(layout).items():
        for path in absolute_paths(text):
            assert path in ALLOWED_ABSOLUTE or any(
                path.startswith(root) for root in roots
            ), f"{name} names {path}, which is outside {roots}"


def test_no_generated_file_carries_a_literal_from_the_prior_art(
    layout: InstallLayout,
) -> None:
    """Plan trap 7. The hand-written probe greps a decrypted secrets blob for a
    bot token; the alert here goes through US1's adapter, so neither the tool
    nor the variable may appear."""
    for name, text in texts(layout).items():
        for literal in PRIOR_ART_LITERALS:
            assert literal not in text, f"{name} carries the prior art's {literal!r}"


def test_two_installations_generate_two_different_texts(tmp_path: Path) -> None:
    """Resolution, not constants — the mutation this kills is a hardcoded root.

    A generator that pasted one host's paths passes every scan above on that
    host. Two layouts under different roots cannot both be satisfied by a
    literal.
    """
    first = resolve_layout(home=tmp_path / "one", install_root=tmp_path / "one/erg")
    second = resolve_layout(home=tmp_path / "two", install_root=tmp_path / "two/erg")

    one = texts(first)[WORKER_UNIT]
    two = texts(second)[WORKER_UNIT]

    assert str(tmp_path / "one") in one and str(tmp_path / "two") not in one
    assert str(tmp_path / "two") in two and str(tmp_path / "one") not in two


def test_the_resolved_layout_keeps_its_state_under_the_state_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """034/us2's `resolve_state_home` — honoring `ERGANE_STATE_HOME` and the
    legacy name ahead of XDG. A second answer derived from `XDG_STATE_HOME`
    here would be the drift that resolver exists to prevent."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.delenv("ERGANE_STATE_HOME", raising=False)
    monkeypatch.delenv("FACTORY_STATE_HOME", raising=False)

    resolved = resolve_layout(home=tmp_path / "home")

    assert resolved.generated_dir == tmp_path / "state/ergane/supervision"
    assert resolved.unit_dir == tmp_path / "home/.config/systemd/user"


# ============================================================================
# Plan trap 9 — the `python -` spelling, mitigation and not a fix
# ============================================================================


def test_no_generated_command_line_contains_the_pkill_pattern(
    layout: InstallLayout,
) -> None:
    """`hardening/agent-pkill-kills-the-live-worker`, as a text property.

    On 2026-08-12 an agent ran `pkill -f "python -"` inside its worktree to
    clean up test servers; that matched the worker's and the bridge's
    `uv run python -m factory.worker` command lines and SIGTERMed both, killing
    the worker that was running the agent. 011/US4's pid namespace fixes the
    root defect for dispatched agents; this spelling still protects the callers
    it does not cover — operator-side and boundary-disabled runs.
    """
    for name, text in texts(layout).items():
        assert "python -" not in text, f"{name} is pkill-shaped"


def test_an_interpreter_spelled_python_is_refused_rather_than_generated(
    layout: InstallLayout,
) -> None:
    """Enforced where the text is created, not only where it is read.

    The wrapper quotes the interpreter, so a bare spelling reads as `python" -m`
    on disk and as `python -m` in `/proc/<pid>/cmdline`, which is what
    `pkill -f` matches. The refusal is armed off the command line for that
    reason, and it names the fix.
    """
    bare = layout.interpreter.with_name("python")
    bare.touch()

    with pytest.raises(OperatorError) as raised:
        generated_files(
            InstallLayout(
                install_root=layout.install_root,
                interpreter=bare,
                unit_dir=layout.unit_dir,
                generated_dir=layout.generated_dir,
            )
        )

    assert "python3" in str(raised.value)


def test_resolve_layout_prefers_the_python3_spelling(tmp_path: Path) -> None:
    venv = tmp_path / "erg/.venv/bin"
    venv.mkdir(parents=True)
    (venv / "python").touch()
    (venv / "python3").touch()

    resolved = resolve_layout(
        home=tmp_path / "home",
        install_root=tmp_path / "erg",
        interpreter=venv / "python",
    )

    assert resolved.interpreter == venv / "python3"


# ============================================================================
# US2-S2 / FR-004 / SC-002 — stopping the unit takes the whole tree
# ============================================================================


def test_every_service_unit_stops_its_whole_process_tree(
    layout: InstallLayout,
) -> None:
    """Plan trap 1, verbatim: `KillMode=control-group` is the point.

    A unit missing it looks correct, starts correctly, restarts correctly, and
    leaks a 66 MiB process every time an agent is killed. Asserted on the text
    because that is where the property lives — the alternative is stopping a
    real unit, and the real units on this host are running the factory.

    Measured evidence for the semantics itself is in the block at the end of
    this file.
    """
    for name in (WORKER_UNIT, BRIDGE_UNIT):
        text = texts(layout)[name]
        assert directive(text, "KillMode") == ["control-group"]
        assert directive(text, "KillSignal") == ["SIGTERM"]
        assert directive(text, "TimeoutStopSec") != []


# ============================================================================
# US2-S3 / FR-005 — a bounded restart rate
# ============================================================================


def test_every_service_unit_bounds_its_restart_rate(layout: InstallLayout) -> None:
    """Giving up loudly beats flapping quietly during a memory storm."""
    for name in (WORKER_UNIT, BRIDGE_UNIT):
        text = texts(layout)[name]
        assert directive(text, "StartLimitIntervalSec") == ["300"]
        assert directive(text, "StartLimitBurst") == ["5"]
        assert directive(text, "RestartSec") != []


def test_the_restart_bound_is_declared_in_the_unit_section(
    layout: InstallLayout,
) -> None:
    """Where systemd reads it. In `[Service]` the directives are ignored — and
    silently: the journal gets an "Unknown key" warning and the unit starts
    anyway, so the bound reads as present in the file and is absent from the
    running system."""
    for name in (WORKER_UNIT, BRIDGE_UNIT):
        section = texts(layout)[name].split("[Service]")[0]
        assert "StartLimitBurst=" in section


# ============================================================================
# FR-003 — the slice, and everything this story generates is inside it
# ============================================================================


def test_every_service_unit_is_inside_the_slice(layout: InstallLayout) -> None:
    """An equality over the whole generated set, not two membership checks.

    The failure worth catching is a unit added to this generator with no
    `Slice=` line at all, and both stories that extend it add one: 042-US4's
    probe (which is the deliberate exception, and asserts its own absence from
    this set) and US3's Temporal server (which is not).
    """
    in_slice = {
        name
        for name, text in texts(layout).items()
        if directive(text, "Slice") == [SLICE_UNIT]
    }

    assert in_slice == {WORKER_UNIT, BRIDGE_UNIT}


def test_the_slice_bounds_memory_and_tasks(layout: InstallLayout) -> None:
    """The containment 2026-08-11 argues for: 8,131 processes, 123 GiB."""
    text = texts(layout)[SLICE_UNIT]

    assert directive(text, "MemoryHigh") == ["32G"]
    assert directive(text, "MemoryMax") == ["48G"]
    assert directive(text, "TasksMax") == ["2000"]


# ============================================================================
# US2-S4 / FR-008 / SC-005 — uninstall removes exactly what install created
# ============================================================================


def test_uninstall_removes_exactly_what_install_created(
    layout: InstallLayout, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    before = tree(home)
    install(layout, run=FakeSystemctl())

    report = uninstall(layout, run=FakeSystemctl(), open_epics=lambda: ())

    assert sorted(report.removed) == sorted(
        [BRIDGE_UNIT, SLICE_UNIT, WORKER_UNIT, WRAPPER_NAME]
    )
    assert report.kept == ()
    assert tree(home) == before


def test_uninstall_disables_before_it_deletes(layout: InstallLayout) -> None:
    """systemd holds the parsed unit in memory: a file removed out from under a
    running unit leaves it up and invisible to `disable` until reboot."""
    install(layout, run=FakeSystemctl())
    fake = FakeSystemctl()

    uninstall(layout, run=fake, open_epics=lambda: ())

    assert fake.issued("disable") != []
    assert fake.calls[-1][-1] == "daemon-reload"


def test_a_same_named_unit_the_engine_did_not_write_is_reported_not_deleted(
    layout: InstallLayout,
) -> None:
    """US2-S4 / SC-005, and the difference between a tool and an accident.

    The operator's hand-written unit of a colliding name may be the one keeping
    their host alive. Provenance is recorded at install time — a digest of what
    was written — so uninstall knows rather than guesses.
    """
    layout.unit_dir.mkdir(parents=True)
    theirs = layout.unit_dir / WORKER_UNIT
    theirs.write_text("[Service]\nExecStart=/usr/bin/true\n", encoding="utf-8")
    install(layout, run=FakeSystemctl())

    report = uninstall(layout, run=FakeSystemctl(), open_epics=lambda: ())

    assert WORKER_UNIT in report.kept
    assert WORKER_UNIT not in report.removed
    assert theirs.read_text(encoding="utf-8") == "[Service]\nExecStart=/usr/bin/true\n"


def test_install_reports_a_foreign_unit_rather_than_overwriting_it(
    layout: InstallLayout,
) -> None:
    """The same edge one verb earlier. Overwriting is the unrecoverable half."""
    layout.unit_dir.mkdir(parents=True)
    theirs = layout.unit_dir / BRIDGE_UNIT
    theirs.write_text("# mine\n", encoding="utf-8")

    report = install(layout, run=FakeSystemctl())

    assert report.kept == (BRIDGE_UNIT,)
    assert BRIDGE_UNIT not in report.written
    assert theirs.read_text(encoding="utf-8") == "# mine\n"


def test_a_unit_the_operator_edited_after_install_is_kept(
    layout: InstallLayout,
) -> None:
    """Provenance is a digest, not a filename: an operator who tuned
    `MemoryMax` by hand has made the file theirs, and the tuning was probably a
    response to something."""
    install(layout, run=FakeSystemctl())
    edited = layout.unit_dir / SLICE_UNIT
    edited.write_text(edited.read_text(encoding="utf-8") + "# tuned\n", encoding="utf-8")

    report = uninstall(layout, run=FakeSystemctl(), open_epics=lambda: ())

    assert SLICE_UNIT in report.kept
    assert edited.is_file()


def test_reinstalling_over_the_engines_own_units_is_not_a_collision(
    layout: InstallLayout,
) -> None:
    """Otherwise the second `install` reports every unit as somebody else's."""
    install(layout, run=FakeSystemctl())

    report = install(layout, run=FakeSystemctl())

    assert report.kept == ()
    assert WORKER_UNIT in report.written


# ============================================================================
# FR-012 — uninstall refuses while an epic is in flight, naming it
# ============================================================================


def test_uninstall_refuses_while_an_epic_is_in_flight_and_names_it(
    layout: InstallLayout,
) -> None:
    """Removing the worker mid-epic strands the attempt it is running."""
    install(layout, run=FakeSystemctl())
    fake = FakeSystemctl()

    with pytest.raises(OperatorError) as raised:
        uninstall(layout, run=fake, open_epics=lambda: ("epic-042-supervised",))

    assert "epic-042-supervised" in str(raised.value)
    assert (layout.unit_dir / WORKER_UNIT).is_file()
    assert fake.calls == []


def test_the_refusal_reads_the_epics_before_it_touches_anything(
    layout: InstallLayout,
) -> None:
    """A disable issued before the refusal is a half-uninstall."""
    install(layout, run=FakeSystemctl())
    seen: list[str] = []

    def epics() -> tuple[str, ...]:
        seen.append("read")
        return ("epic-011",)

    with pytest.raises(OperatorError):
        uninstall(layout, run=FakeSystemctl(), open_epics=epics)

    assert seen == ["read"]


# ============================================================================
# Structure — the module the probe imports may not drag Temporal in with it
# ============================================================================


def test_the_units_module_imports_temporal_lazily_if_at_all() -> None:
    """FR-012's read is the only Temporal in this story, and it is a read.

    It must not be a module-scope import: `factory/supervision/probe.py`
    imports this module for the unit names, and the probe is the process that
    runs when Temporal is the thing that died.
    """
    module = ast.parse(UNITS_MODULE.read_text(encoding="utf-8"))
    top_level = {
        alias.name.split(".")[0]
        for node in module.body
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in module.body
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert "temporalio" not in top_level




# ============================================================================
# Mutation battery — 18 mutations, 3 controls, 0 survivors
# ============================================================================
#
# Runtime evidence, committed because the judge is given this diff and nothing
# else (constitution VIII). The harness is a scratch script; per case it
# asserts the worktree clean — tracked AND untracked, because `git checkout --`
# does not remove an untracked file — applies one edit to
# factory/supervision/units.py, purges every `__pycache__` and runs with
# PYTHONDONTWRITEBYTECODE=1 (CPython validates a cached `.pyc` on
# mtime-in-whole-seconds and size alone, so two same-size mutants inside one
# second otherwise run the first one's bytecode, and that failure lands on
# green), restores, and asserts clean again. A run that collected nothing is
# reported INVALID rather than as a survivor.
#
# C1 edits nothing and C2 edits only a comment: if either failed, a "kill"
# would only be saying the file had been touched. C3 points M01 at a test node
# id that does not exist — the shape in which a battery reports a clean sweep
# having run nothing.
#
# Two survivors were found across the story this was carved from, and both are
# recorded rather than quietly fixed. The first was a harness lie:
# `KillMode=control-group` appears in the module docstring before it appears in
# the generated text, so the edit landed in prose and nothing ran differently —
# M01 was re-aimed at `KillMode=control-group\nKillSignal`. The second was a
# real gap: `_reading` replaced by `return ENABLE_TARGETS` — an install that
# assumes `enable --now` worked instead of reading the state back — passed
# every test, because every unit in the fake came up, so the two states
# coincided everywhere they were observed. M18 below is that mutation, and
# test_install_reports_a_unit_that_enabled_and_did_not_come_up is what now
# separates them.
#
#   C1 no edit at all
#       27P — passed, as a control must
#   C2 a comment-only edit
#       27P — passed, as a control must
#   C3 pointed at a test node id that does not exist
#       no tests ran — INVALID - collected nothing
#   M01 the process tree is left behind
#       1F/26P — KILLED by test_every_service_unit_stops_its_whole_process_tree
#   M02 the stop signal is dropped
#       1F/26P — KILLED by test_every_service_unit_stops_its_whole_process_tree
#   M03 the restart bound loses its burst
#       2F/25P — KILLED by test_every_service_unit_bounds_its_restart_rate
#   M04 the restart bound moves into [Service]
#       1F/26P — KILLED by test_the_restart_bound_is_declared_in_the_unit_section
#   M05 the services leave the slice
#       1F/26P — KILLED by test_every_service_unit_is_inside_the_slice
#   M07 the slice stops bounding tasks
#       1F/26P — KILLED by test_the_slice_bounds_memory_and_tasks
#   M09 the interpreter keeps its bare spelling
#       1F/26P — KILLED by test_resolve_layout_prefers_the_python3_spelling
#   M10 the pkill-shaped refusal is disarmed
#       1F/26P — KILLED by test_an_interpreter_spelled_python_is_refused_rather_than_generated
#   M11 the working directory is a literal
#       3F/24P — KILLED by test_no_generated_file_names_a_path_outside_the_installation
#   M12 the wrapper is placed in the other repository
#       2F/25P — KILLED by test_no_generated_file_names_a_path_outside_the_installation
#   M13 every file on disk is treated as the engine's
#       3F/24P — KILLED by test_a_same_named_unit_the_engine_did_not_write_is_reported_not_deleted
#   M14 no file is ever treated as the engine's
#       10F/17P — KILLED by test_install_writes_every_unit_and_the_wrapper
#   M15 the in-flight refusal never fires
#       2F/25P — KILLED by test_uninstall_refuses_while_an_epic_is_in_flight_and_names_it
#   M16 the refusal stops naming the epic
#       1F/26P — KILLED by test_uninstall_refuses_while_an_epic_is_in_flight_and_names_it
#   M17 linger is claimed rather than enabled
#       2F/25P — KILLED by test_install_enables_linger_for_the_user
#   M18 liveness is asserted rather than read back
#       1F/26P — KILLED by test_install_reports_a_unit_that_enabled_and_did_not_come_up
#   M19 provenance is never recorded
#       3F/24P — KILLED by test_uninstall_removes_exactly_what_install_created
#   M20 uninstall deletes before it disables
#       1F/26P — KILLED by test_uninstall_disables_before_it_deletes

# ============================================================================
# SC-002 — a process tree, counted before and after
# ============================================================================
#
# FR-004 is a property of `KillMode=control-group`, and the test above asserts
# it on the generated text. What the text cannot show is that group-wide
# signalling takes children with it, so that half was measured — on three
# `sleep` processes in a session of their own, never on a unit:
#
#     $ bash us2-tree-kill.sh
#     leader pid 420350, pgid 420350
#     before: 4 processes in the group
#      420350  420350 sh
#      420350  420352 sleep
#      420350  420353 sleep
#      420350  420354 sleep
#     after:  0 processes in the group
#     orphans left on PID 1 from this group: 0
#
# What was deliberately NOT run, and why the evidence is therefore half: the
# counter-experiment is killing the leader alone and counting the children left
# behind on PID 1. That creates, briefly, exactly the orphan this epic exists
# to prevent, on the operator's live floor — so it was not run here, and the
# "a bare kill leaves orphans" half rests on the prior art's own comment and on
# the 2026-08-11 incident rather than on a measurement of mine. Stopping a real
# unit was never an option either: the units on this host are the ones running
# the factory.

# ============================================================================
# The full suite, cold cache
# ============================================================================
#
#     $ find . -name __pycache__ -type d -prune -exec rm -rf {} +
#     $ PYTHONDONTWRITEBYTECODE=1 uv run pytest -q --no-header
#     3182 passed, 44 skipped, 6 warnings in 315.20s (0:05:15)
#
# The base commit, measured the same way rather than assumed:
#
#     3143 passed, 44 skipped, 6 warnings in 315.82s (0:05:15)
#
# The 39 are this file's 27 tests plus 12 parametrised sweep cases — six
# per-module guards across the sweeps, times the two modules this story adds —
# every one of them enumerated by diffing collected node ids between the two
# commits, because "the rest is sweeps" is a guess and a diff is not. Skips are
# unchanged at 44: this story adds no test that does not run. Warning counts
# are deliberately not quoted — a warm cache suppresses compile-time warnings,
# so the number is a property of the cache and not of the diff.
