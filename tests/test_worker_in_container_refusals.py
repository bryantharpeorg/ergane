"""088-US4: `ergane worker install`, `deploy` and `migrate` refuse in a container.

The three systemd verbs touch the user D-Bus bus. In a container there is no
user session, so instead of a half-page D-Bus error they tell the operator the
likely cause and what replaces the verb.

T015 — stub the session predicate absent and assert the refusal text.
T016 — wire the real predicate from `factory.cli.install` into the noun.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from factory.cli.errors import EXIT_USER
from factory.cli.main import main as ergane_main
from factory.supervision.units import InstallLayout


@pytest.fixture
def layout(tmp_path: Path) -> Iterator[InstallLayout]:
    """An installation whose every root is under `tmp_path`."""
    home = tmp_path / "home"
    interpreter = home / "code/ergane/.venv/bin/python3"
    interpreter.parent.mkdir(parents=True)
    interpreter.touch()
    unit_dir = home / ".config/systemd/user"
    unit_dir.mkdir(parents=True)
    yield InstallLayout(
        install_root=home / "code/ergane",
        interpreter=interpreter,
        unit_dir=unit_dir,
        generated_dir=home / ".local/state/ergane/supervision",
    )


def _assert_refusal(code: int, stderr: str) -> None:
    message = stderr.lower()
    assert code == EXIT_USER, f"expected exit {EXIT_USER}, got {code}: {stderr!r}"
    assert "systemd user session" in message
    assert "container" in message
    assert "supervisor" in message


def test_worker_install_refuses_without_systemd_user_session(
    layout: InstallLayout,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.setattr(
        "factory.cli.install._systemd_user_session_available", lambda: False
    )

    code = ergane_main(["worker", "install"])
    _assert_refusal(code, capsys.readouterr().err)


def test_worker_deploy_refuses_without_systemd_user_session(
    layout: InstallLayout,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.setattr(
        "factory.cli.install._systemd_user_session_available", lambda: False
    )

    code = ergane_main(["worker", "deploy"])
    _assert_refusal(code, capsys.readouterr().err)


def test_worker_migrate_refuses_without_systemd_user_session(
    layout: InstallLayout,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.setattr(
        "factory.cli.install._systemd_user_session_available", lambda: False
    )

    code = ergane_main(["worker", "migrate"])
    _assert_refusal(code, capsys.readouterr().err)
