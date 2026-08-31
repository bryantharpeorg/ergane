"""119-US3: the managed server can start, and verification proves it by asking.

Written before the implementation (T013-T018), against the shape T019-T023 add.
Six scenarios, each of which the current tree fails or answers vacuously:

- **S1** the database directory. The dev server stats the *parent* of its
  `--db-filename` and refuses to create it, so a cold state volume kills the
  unit on its first start.
- **S2** the ordering dependency. Neither the worker nor the bridge waits for
  the Temporal unit, so on a managed host both burn their `StartLimitBurst`
  before the server is listening (plan trap 5: `After=` orders without
  requiring, `Wants=` requires without ordering, and one alone still flaps).
- **S3/S4** `--verify`. `TemporalProbe.gather` short-circuits managed mode with
  `namespace_exists=True` hardcoded, so it passed three times over a host with
  no server on it. The fix has to *fail closed* (plan trap 7): the tests below
  run the same config against a live server and against a port nothing is
  listening on, and the second one must fail.
- **S5** what install says. The report named the units it found up; the ones
  that enabled and died were absent from it entirely, which is how three failing
  services hid behind a green-looking probe timer (plan trap 8).
- **S6** uninstall. The verb that removes the units read open epics off Temporal
  first, so a host whose Temporal never started — the state this whole spec is
  about — could not be cleaned up (plan trap 6).

Every path any test here touches is under `tmp_path`, and the two config
variables are unset per test: `scripts/ergane-env.sh` exports a config path and
an address on this host, and a test that inherited either would measure the
operator's own installation instead of its fixture.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import Any, Sequence

import pytest

from factory.cli.errors import OperatorError
from factory.controlplane.config import load_controlplane_config
from factory.controlplane.verify import TemporalProbe
from factory.env import ERGANE_CONFIG_PATH_ENV, FACTORY_CONFIG_PATH_ENV
from factory.notify.service import TEMPORAL_ADDRESS_ENV, TEMPORAL_NAMESPACE_ENV
from factory.supervision import temporal_server
from factory.supervision.units import (
    BRIDGE_UNIT,
    PROBE_TIMER,
    TEMPORAL_UNIT,
    WORKER_TEMPLATE_UNIT,
    CommandResult,
    InstallLayout,
    install,
    uninstall,
)
from tests.test_supervision_units import FakeSystemctl, texts

#: The namespace the generated Temporal unit passes the server (`--namespace
#: ergane`) and the one the resolver falls back to when nothing is declared.
#: Managed mode declares neither address nor namespace, so both halves of the
#: dial come from that fallback — which is exactly why the dial has to be tested
#: against a real server rather than asserted about.
MANAGED_NAMESPACE = "ergane"


# --- fixtures ----------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_inherited_declaration(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test here reads a config, or dials an address, it did not choose."""
    for name in (
        ERGANE_CONFIG_PATH_ENV,
        FACTORY_CONFIG_PATH_ENV,
        TEMPORAL_ADDRESS_ENV,
        TEMPORAL_NAMESPACE_ENV,
    ):
        monkeypatch.delenv(name, raising=False)


def _layout(tmp_path: Path, *, mode: str) -> InstallLayout:
    """An installation whose every root is under `tmp_path`.

    `python3` rather than `python`, because the interpreter's spelling is
    load-bearing (`PKILL_PATTERN`) and generation refuses the other one.
    """
    home = tmp_path / "home"
    interpreter = home / "code/ergane/.venv/bin/python3"
    interpreter.parent.mkdir(parents=True)
    interpreter.touch()
    return InstallLayout(
        install_root=home / "code/ergane",
        interpreter=interpreter,
        unit_dir=home / ".config/systemd/user",
        generated_dir=home / ".local/state/ergane/supervision",
        temporal_mode=mode,
    )


@pytest.fixture
def managed(tmp_path: Path) -> InstallLayout:
    return _layout(tmp_path, mode="managed")


@pytest.fixture
def external(tmp_path: Path) -> InstallLayout:
    return _layout(tmp_path, mode="external")


@pytest.fixture(autouse=True)
def _no_real_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test here may run a command against the host's own session.

    On this host that session *is* the factory, and a stray `disable --now`
    would take the running worker's whole cgroup with it.
    """

    def refuse(argv: Sequence[str]) -> CommandResult:
        raise AssertionError(f"a test reached the host's own session: {list(argv)}")

    monkeypatch.setattr("factory.supervision.units._run_command", refuse)


class FailingSystemctl(FakeSystemctl):
    """A session where some units enable, start and then fail.

    The shape of the reported defect: three services in `failed` behind a probe
    timer that is genuinely `active`. `FakeSystemctl.dead_on_start` already
    models a unit that does not come up; this names the *state* systemd would
    print for it, because a report that says only "not active" cannot tell an
    operator whether to look at the journal.
    """

    def __init__(self) -> None:
        super().__init__()
        self.failed: set[str] = set()

    def __call__(self, argv: Sequence[str]) -> CommandResult:
        args = tuple(argv)
        if len(args) > 2 and args[2] == "is-active" and args[-1] in self.failed:
            self.calls.append(args)
            return CommandResult(3, "failed")
        return super().__call__(argv)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _managed_config(tmp_path: Path) -> Any:
    """A parsed control-plane config declaring managed Temporal.

    Managed mode takes no address and no namespace — the parser returns on the
    mode alone — so this is the whole `[temporal]` block, and the dial the probe
    makes is built from the resolver's defaults.
    """
    path = tmp_path / "config.toml"
    path.write_text(
        """\
version = 1

[llm]
mode = "gateway"
base_url = "http://declared.gateway.test/v1"
master_key_env = "DECLARED_KEY_VAR"

[memory]
backend = "none"

[temporal]
mode = "managed"

[telemetry]

[escalation]
adapter = "none"
""",
        encoding="utf-8",
    )
    return load_controlplane_config(path)


# --- T013 [US3-S1 / FR-007] the database directory ---------------------------


def test_the_server_creates_its_database_directory_before_it_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US3-S1: a managed installation whose db directory is absent gets one.

    The server is not started — `_run` is replaced — because the subject is the
    order: the directory must exist *by the time* the server is asked to open
    the file. The dev server stats the parent and refuses to create it, so a
    mkdir that happened afterwards would be a mkdir that never mattered.
    """
    db = tmp_path / "state/ergane/temporal/dev.db"
    assert not db.parent.exists()
    seen: dict[str, bool] = {}

    async def _fake_run(**kwargs: Any) -> int:
        seen["directory existed at start"] = db.parent.is_dir()
        seen["db was the one passed"] = kwargs["db_filename"] == str(db)
        return 0

    monkeypatch.setattr(temporal_server, "_run", _fake_run)

    code = temporal_server.main(["--db-filename", str(db)])

    assert code == 0
    assert seen == {"directory existed at start": True, "db was the one passed": True}
    assert db.parent.is_dir()


def test_a_managed_install_leaves_the_database_directory_in_place(
    managed: InstallLayout,
) -> None:
    """US3-S1 at the other end of the path: the installation has somewhere to put it.

    `layout.temporal_db_path` is inside `roots` already; what was missing is
    anything that creates it. Install is the verb that knows this host declared
    managed mode, and it runs before the unit it just enabled starts.
    """
    assert not managed.temporal_db_path.parent.exists()

    install(managed, run=FakeSystemctl())

    assert managed.temporal_db_path.parent.is_dir()


def test_an_external_install_creates_no_temporal_directory(
    external: InstallLayout,
) -> None:
    """The control: external mode runs no server, so it needs no database."""
    install(external, run=FakeSystemctl())

    assert not external.temporal_db_path.parent.exists()


# --- T014 [US3-S2 / FR-008, plan trap 5] the ordering dependency -------------


@pytest.mark.parametrize("unit", [WORKER_TEMPLATE_UNIT, BRIDGE_UNIT])
def test_the_managed_units_order_themselves_after_temporal(
    managed: InstallLayout, unit: str
) -> None:
    """US3-S2: worker and bridge each declare the dependency, both directions.

    Plan trap 5 in one assertion: `After=` alone orders without pulling the
    server in, `Wants=` alone pulls it in without waiting for it, and a unit
    carrying only one still spends its `StartLimitBurst` on every boot — which
    is the failure this scenario names.
    """
    text = texts(managed)[unit]

    assert f"After={TEMPORAL_UNIT}" in text
    assert f"Wants={TEMPORAL_UNIT}" in text


@pytest.mark.parametrize("unit", [WORKER_TEMPLATE_UNIT, BRIDGE_UNIT])
def test_the_unit_says_which_pair_it_used_and_why(
    managed: InstallLayout, unit: str
) -> None:
    """US3-S2, plan trap 5: the reasoning is in the generated unit's own comment.

    An operator reading the installed file is the person who needs to know why
    it is `Wants=` and not `Requires=`; a comment in the generator reaches them
    only if they have the checkout.
    """
    comments = "\n".join(
        line for line in texts(managed)[unit].splitlines() if line.startswith("#")
    )

    assert "Wants=" in comments
    assert "After=" in comments
    assert "Requires=" in comments
    assert "start limit" in comments.lower()


@pytest.mark.parametrize("unit", [WORKER_TEMPLATE_UNIT, BRIDGE_UNIT])
def test_an_external_installation_names_no_temporal_unit(
    external: InstallLayout, unit: str
) -> None:
    """The control, and it is not cosmetic: an ordering dependency on a unit
    that was never written is a name systemd cannot resolve, on the path this
    spec is careful not to touch."""
    assert TEMPORAL_UNIT not in texts(external)[unit]


# --- T015 [US3-S3 / FR-009, plan trap 7] --verify fails when nobody answers ---


async def test_verify_fails_naming_the_unreachable_managed_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US3-S3: no server, no pass — and the failure names what it dialled.

    A real refused port rather than a patched-out dial: the defect being fixed
    is precisely a check that never reached the network, so a test that stubbed
    the network would be unable to tell the fix from the defect.
    """
    dead = _free_port()
    monkeypatch.setenv(TEMPORAL_ADDRESS_ENV, f"127.0.0.1:{dead}")
    config = _managed_config(tmp_path)

    probe = TemporalProbe()
    snapshot = await probe.gather(config)
    finding = probe.evaluate(snapshot)

    assert finding.passed is False
    assert f"127.0.0.1:{dead}" in finding.detail


async def test_an_unreachable_managed_server_is_not_called_inconclusive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US3-S3, plan trap 7: failing to reach the server is a failure.

    A dial that treats "connection refused" as unknown and passes anyway has
    reproduced the defect with more code, so this asserts the snapshot's own
    field rather than only the verdict, and asserts the old vacuous sentence is
    gone from the detail it would otherwise still be carrying.
    """
    dead = _free_port()
    monkeypatch.setenv(TEMPORAL_ADDRESS_ENV, f"127.0.0.1:{dead}")

    snapshot = await TemporalProbe().gather(_managed_config(tmp_path))

    assert snapshot.namespace_exists is False
    assert "uptime is verified by the supervision probe" not in snapshot.detail


# --- T016 [US3-S4 / FR-009] --verify passes only after dialling ---------------


async def test_verify_passes_having_dialled_the_running_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US3-S4: with a server up the check passes, and it passed by asking.

    Both halves of the scenario in one test, against one config: the server is
    started, the check passes, the server is stopped, and the *same* config
    fails. A check whose answer is decided by `mode = "managed"` cannot produce
    both, which is precisely what the reported defect could not do.

    The dial is witnessed rather than inferred — the real describe-namespace
    round trip is wrapped in a recorder — because "passes" and "passes having
    dialled" are the two outcomes this story exists to tell apart.

    `WorkflowEnvironment.start_local` is the seam
    `tests/test_supervision_managed_temporal.py` already uses for the
    persistence scenario; `port=0` does not work through it, so a free port is
    bound and passed explicitly.
    """
    import factory.controlplane.verify as verify
    from temporalio.testing import WorkflowEnvironment

    if not os.environ.get("USER"):
        # The downloaded dev server calls os/user.Current, which needs cgo or
        # $USER; in a minimal sandbox the variable is unset and the server exits
        # during startup. The value is not used for permissions.
        monkeypatch.setenv("USER", "ergane-test")

    port = _free_port()
    address = f"127.0.0.1:{port}"
    monkeypatch.setenv(TEMPORAL_ADDRESS_ENV, address)
    dialled: list[str] = []
    real = verify._describe_temporal_namespace

    async def _witnessed(config: Any, namespace: str) -> str:
        dialled.append(namespace)
        return await real(config, namespace)

    monkeypatch.setattr(verify, "_describe_temporal_namespace", _witnessed)
    config = _managed_config(tmp_path)
    probe = TemporalProbe()

    environment = await WorkflowEnvironment.start_local(
        namespace=MANAGED_NAMESPACE, port=port
    )
    try:
        up = probe.evaluate(await probe.gather(config))
    finally:
        await environment.shutdown()
    down = probe.evaluate(await probe.gather(config))

    assert dialled == [MANAGED_NAMESPACE, MANAGED_NAMESPACE]
    assert up.passed is True
    assert address in up.detail
    assert down.passed is False


# --- T017 [US3-S5 / FR-010, plan trap 8] what install reports ----------------


def test_install_reports_every_service_it_started_and_its_state(
    managed: InstallLayout,
) -> None:
    """US3-S5: the three services that failed behind the probe timer are named.

    The reported defect exactly: bridge and Temporal enable and die, the timer
    is genuinely active, and the operator reads a report that mentions only the
    timer. Every service install enabled must appear, with the state systemd
    printed for it.
    """
    fake = FailingSystemctl()
    fake.dead_on_start.update({BRIDGE_UNIT, TEMPORAL_UNIT})
    fake.failed.update({BRIDGE_UNIT, TEMPORAL_UNIT})

    report = install(managed, run=fake)
    rendered = report.render()

    assert dict(report.states) == {
        BRIDGE_UNIT: "failed",
        TEMPORAL_UNIT: "failed",
        PROBE_TIMER: "active",
    }
    for name in (BRIDGE_UNIT, TEMPORAL_UNIT, PROBE_TIMER):
        assert name in rendered
    assert rendered.count("failed") >= 2


def test_a_state_the_session_would_not_name_is_still_reported(
    managed: InstallLayout,
) -> None:
    """FR-010: the report says what it was told, including nothing.

    `systemctl is-active` on a unit systemd has never heard of prints nothing
    at all, and a report that silently dropped those names would be the defect
    again — a service started and unaccounted for.
    """

    class Mute(FakeSystemctl):
        def __call__(self, argv: Sequence[str]) -> CommandResult:
            args = tuple(argv)
            if len(args) > 2 and args[2] == "is-active":
                self.calls.append(args)
                return CommandResult(4, "")
            return super().__call__(argv)

    report = install(managed, run=Mute())

    assert {name for name, _ in report.states} == {
        BRIDGE_UNIT,
        TEMPORAL_UNIT,
        PROBE_TIMER,
    }
    for name in (BRIDGE_UNIT, TEMPORAL_UNIT, PROBE_TIMER):
        assert name in report.render()


def test_an_external_install_reports_the_services_it_has(
    external: InstallLayout,
) -> None:
    """The control: no Temporal unit is written, so none is claimed."""
    report = install(external, run=FakeSystemctl())

    assert {name for name, _ in report.states} == {BRIDGE_UNIT, PROBE_TIMER}
    assert TEMPORAL_UNIT not in report.render()


# --- T018 [US3-S6 / FR-011, plan trap 6] uninstall does not need Temporal -----


def _unreachable_epics() -> Sequence[str]:
    """What the epic read does on the host this spec is about: it cannot dial."""
    raise ConnectionError("failed to connect to Temporal at localhost:7233")


def test_uninstall_removes_the_units_with_temporal_unreachable(
    managed: InstallLayout,
) -> None:
    """US3-S6, plan trap 6: the verb that removes units may not need the service.

    The installation that cannot reach Temporal is the one this spec exists to
    describe, and it is exactly the installation an operator most needs to be
    able to clean up.
    """
    install(managed, run=FakeSystemctl())

    report = uninstall(managed, run=FakeSystemctl(), open_epics=_unreachable_epics)

    assert TEMPORAL_UNIT in report.removed
    assert WORKER_TEMPLATE_UNIT in report.removed
    assert not (managed.unit_dir / BRIDGE_UNIT).exists()


def test_uninstall_says_it_could_not_rule_out_an_epic_in_flight(
    managed: InstallLayout,
) -> None:
    """FR-011 without losing FR-012's protection: the skipped check is reported.

    Proceeding is right — the units come off — but an operator who is never told
    the in-flight check could not be made would read an unconditional all-clear
    into a removal that did not perform one.
    """
    install(managed, run=FakeSystemctl())

    rendered = uninstall(
        managed, run=FakeSystemctl(), open_epics=_unreachable_epics
    ).render()

    assert "localhost:7233" in rendered
    assert "epic" in rendered.lower()


def test_uninstall_still_refuses_while_an_epic_is_in_flight(
    managed: InstallLayout,
) -> None:
    """The refusal FR-011 must not take with it (082's FR-012).

    "Do not depend on the service" is not "do not check": when the read answers,
    an open epic still stops the removal, because stopping the worker mid-epic
    strands the attempt it is running.
    """
    install(managed, run=FakeSystemctl())

    with pytest.raises(OperatorError) as refused:
        uninstall(managed, run=FakeSystemctl(), open_epics=lambda: ("epic-119-x",))

    assert "epic-119-x" in str(refused.value)
    assert (managed.unit_dir / WORKER_TEMPLATE_UNIT).is_file()
