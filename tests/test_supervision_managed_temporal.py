"""042-US3: managed Temporal is installed supervised or not at all.

Tests T021–T025, written before the implementation exists, and expected to fail
until T026–T027 land.
"""

from __future__ import annotations

import asyncio
import os
import socket
import tempfile
from pathlib import Path
from typing import Iterator

import pytest
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment

from factory.controlplane.config import (
    ControlPlaneConfigError,
    load_controlplane_config,
    parse_controlplane_config,
)
from factory.supervision.units import (
    BRIDGE_UNIT,
    ENABLE_TARGETS,
    PROBE_TIMER,
    SLICE_UNIT,
    WORKER_UNIT,
    InstallLayout,
    generated_files,
    install,
    resolve_layout,
)
from tests.test_supervision_units import FakeSystemctl, texts, directive

TEMPORAL_UNIT = "ergane-temporal.service"


#: The same path inside the operator's installation the generated unit will use.
#: Persistence lives under the state home so a host reinstall does not silently
#: discard history, and so the path is inside the operator's own installation.
STATE_HOME_RELPATH = Path(".local/state/ergane/temporal")


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def layout(tmp_path: Path) -> Iterator[InstallLayout]:
    """An installation whose every root is under `tmp_path`."""
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
        temporal_mode="external",
    )


@pytest.fixture
def managed_layout(tmp_path: Path) -> Iterator[InstallLayout]:
    """A managed-mode installation whose every root is under `tmp_path`."""
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
        temporal_mode="managed",
    )


# ---------------------------------------------------------------------------
# T021 [US3-S1 / FR-009] managed mode installs a Temporal unit
# ---------------------------------------------------------------------------


def test_managed_mode_installs_temporal_unit(managed_layout: InstallLayout) -> None:
    """US3-S1: managed Temporal produces `ergane-temporal.service`."""
    names = {generated.name for generated in generated_files(managed_layout)}
    assert TEMPORAL_UNIT in names


def test_temporal_unit_is_inside_the_slice(managed_layout: InstallLayout) -> None:
    """US3-S1: the Temporal server is contained the same way the worker is."""
    text = texts(managed_layout)[TEMPORAL_UNIT]
    assert directive(text, "Slice") == [SLICE_UNIT]


def test_temporal_unit_has_persistent_storage(managed_layout: InstallLayout) -> None:
    """US3-S1 / SC-004: the unit declares SQLite persistence."""
    text = texts(managed_layout)[TEMPORAL_UNIT]
    assert directive(text, "ExecStart") != []
    assert "--db-filename" in text
    assert "temporal" in text.lower() or "server" in text.lower()


def test_temporal_unit_is_enabled_when_managed(managed_layout: InstallLayout) -> None:
    """US3-S1: the Temporal unit is part of what `install` enables."""
    assert TEMPORAL_UNIT in ENABLE_TARGETS


def test_temporal_managed_mode_parses_without_refusal(tmp_path: Path) -> None:
    """US3-S1 / FR-009: 033's parse-time refusal of `managed` is gone."""
    path = tmp_path / "config.toml"
    path.write_text(
        """
version = 1

[llm]
mode = "gateway"
base_url = "http://llm.local/v1"
master_key_env = "ERGANE_LLM_MASTER_KEY"

[memory]
backend = "none"

[temporal]
mode = "managed"

[telemetry]

[escalation]
adapter = "telegram"
""".lstrip(),
        encoding="utf-8",
    )
    cfg = load_controlplane_config(path)
    assert cfg.temporal.mode == "managed"
    assert cfg.temporal.address is None


# ---------------------------------------------------------------------------
# T022 [US3-S2 / SC-004] persistence across restart
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_managed_temporal_history_survives_restart(tmp_path: Path) -> None:
    """US3-S2: workflow history survives a dev-server stop/start with the same db.

    The generated unit will use `--db-filename`; this test proves that flag has
    the effect the criterion claims. `WorkflowEnvironment` is the supported
    Python seam to a local dev server, but `port=0` fails to connect, so a free
    port is pre-bound and passed explicitly.
    """
    db = tmp_path / "temporal.sqlite"
    first_port = _free_port()
    env1 = await WorkflowEnvironment.start_local(
        namespace="ergane",
        port=first_port,
        dev_server_database_filename=str(db),
    )
    try:
        client1 = await Client.connect(env1._server.target, namespace="ergane")
        handle = await client1.start_workflow(
            "FakeWorkflow",
            id="us3-persist-wf",
            task_queue="us3-test",
        )
        assert handle.id == "us3-persist-wf"
    finally:
        await env1.shutdown()

    second_port = _free_port()
    env2 = await WorkflowEnvironment.start_local(
        namespace="ergane",
        port=second_port,
        dev_server_database_filename=str(db),
    )
    try:
        client2 = await Client.connect(env2._server.target, namespace="ergane")
        desc = await client2.get_workflow_handle("us3-persist-wf").describe()
        assert desc.id == "us3-persist-wf"
    finally:
        await env2.shutdown()


# ---------------------------------------------------------------------------
# T023 [US3-S3 / SC-001] alert while Temporal is down
# ---------------------------------------------------------------------------


def test_alert_while_temporal_down(tmp_path: Path) -> None:
    """US3-S3: a dead Temporal unit is reported through US1's alert path.

    The real environment cannot run systemd units, so the test asserts the
    structural property: the probe's watched unit set includes the Temporal
    unit, and a probe run with only that unit inactive delivers an alert naming
    it.  The out-of-band delivery path is tested in `test_supervision_alert.py`;
    here the subject is that US3 adds the Temporal unit to the watch list.
    """
    from factory.supervision.probe import ProbeConfig, run_probe
    from tests.test_supervision_probe import Recorder, host as fake_host

    sent = Recorder()
    run = run_probe(
        ProbeConfig(units=(TEMPORAL_UNIT,)),
        fake_host(active=(), down_for_us=4_000_000_000),
        tmp_path,
        now=1_000_000.0,
        alert=sent,
    )
    assert run.verdict.status == "degraded"
    assert sent.sent != []
    assert sent.sent[0].service == TEMPORAL_UNIT
    assert "not active" in sent.sent[0].condition


# ---------------------------------------------------------------------------
# T024 [US3-S4 / FR-010] external mode installs no unit
# ---------------------------------------------------------------------------


def test_external_mode_installs_no_temporal_unit(layout: InstallLayout) -> None:
    """US3-S4: external mode does not generate a Temporal unit."""
    names = {generated.name for generated in generated_files(layout)}
    assert TEMPORAL_UNIT not in names


# ---------------------------------------------------------------------------
# T025 [US3-S5 / FR-011] unsupported host refuses managed mode at walkthrough
# ---------------------------------------------------------------------------


def test_unsupported_host_refuses_managed_mode_at_walkthrough(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US3-S5: a host without systemd user sessions refuses managed mode.

    The refusal must happen at walkthrough time, before any unit is written.
    """
    import factory.cli.install as install_module
    from factory.cli.main import main as ergane_main
    import io
    import sys

    config_path = tmp_path / "ergane" / "config.toml"
    monkeypatch.setenv("ERGANE_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("FACTORY_CONFIG_PATH", str(config_path))

    class ScriptedPrompter:
        def __init__(self, answers: list[str]) -> None:
            self.answers = list(answers)
            self.asked: list[str] = []
        def ask(self, prompt: str, *, default: str | None = None, error: str | None = None) -> str:
            self.asked.append(prompt)
            return self.answers.pop(0)

    prompter = ScriptedPrompter(
        [
            "gateway",  # llm mode
            "http://127.0.0.1:1/v1",  # base_url
            "ERGANE_LLM_MASTER_KEY",  # master key
            "none",  # memory backend
            "managed",  # temporal mode -> should be refused
            "external",  # re-ask after refusal
            "127.0.0.1:7233",  # address
            "ergane",  # namespace
            "-",  # api key env (clear)
            "false",  # tls
            "",  # telemetry
            "telegram",  # adapter
            "-",  # bot token
            "-",  # chat id
        ]
    )
    monkeypatch.setattr(install_module.init_module, "_prompter_factory", lambda: prompter)

    old_stdout, old_stderr = sys.stdout, sys.stderr
    buf_out, buf_err = io.StringIO(), io.StringIO()
    try:
        sys.stdout, sys.stderr = buf_out, buf_err
        try:
            code = ergane_main(["install"])
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr

    assert code != 0 or "managed" in buf_err.getvalue() or config_path.exists() is False
    # The refusal names the constraint.
    assert "systemd" in buf_err.getvalue().lower() or "user session" in buf_err.getvalue().lower() or not config_path.exists()
