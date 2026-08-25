"""105-US3: `ergane status` surfaces engine skew in `FloorStatus.notes` (T024)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import factory.cli.nouns as nouns
from factory.cli.errors import OperatorError
from factory.cli.status import collect_floor
from factory.supervision.engine_identity import (
    EngineIdentity,
    identity_path,
    image_reference,
    write_identity,
)


@pytest.fixture
def isolated_state_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "state"
    monkeypatch.setenv("ERGANE_STATE_HOME", str(state))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("FACTORY_STATE_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    return state


async def _raise_operator_error() -> None:
    raise OperatorError("no Temporal for status test")


def test_status_appends_engine_skew_note_above_temporal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolated_state_home: Path,
) -> None:
    """T024 / US3-S2 / FR-015: a mismatch appends one note before `_open_client`."""
    from factory.supervision import engine_identity as identity_module

    monkeypatch.setattr(identity_module, "cli_version", lambda: "0.4.0")

    identity = EngineIdentity(
        version="0.3.0",
        started_at="2026-08-25T12:00:00+00:00",
        image_reference=image_reference("0.3.0"),
        image_digest=None,
    )
    write_identity(isolated_state_home, identity)

    monkeypatch.setattr(nouns, "_open_client", _raise_operator_error)

    specs_root = tmp_path / "specs"
    specs_root.mkdir()
    (specs_root / "README.md").write_text("# specs\n", encoding="utf-8")

    floor = asyncio.run(collect_floor(specs_root))

    assert len(floor.notes) == 2
    assert "engine is running ergane 0.3.0" in floor.notes[0]
    assert "this CLI is 0.4.0" in floor.notes[0]
    assert str(identity_path(isolated_state_home)) in floor.notes[0]
    assert floor.degraded is True


def test_status_no_note_when_identity_matches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolated_state_home: Path,
) -> None:
    """A matching engine version produces no skew note."""
    from factory.supervision import engine_identity as identity_module

    monkeypatch.setattr(identity_module, "cli_version", lambda: "0.4.0")

    identity = EngineIdentity(
        version="0.4.0",
        started_at="2026-08-25T12:00:00+00:00",
        image_reference=image_reference("0.4.0"),
        image_digest=None,
    )
    write_identity(isolated_state_home, identity)

    monkeypatch.setattr(nouns, "_open_client", _raise_operator_error)

    specs_root = tmp_path / "specs"
    specs_root.mkdir()
    (specs_root / "README.md").write_text("# specs\n", encoding="utf-8")

    floor = asyncio.run(collect_floor(specs_root))

    assert all("engine is running" not in note for note in floor.notes)


def test_status_no_note_when_identity_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolated_state_home: Path,
) -> None:
    """No identity file is the native path: no skew note, only the outage note."""
    monkeypatch.setattr(nouns, "_open_client", _raise_operator_error)

    specs_root = tmp_path / "specs"
    specs_root.mkdir()
    (specs_root / "README.md").write_text("# specs\n", encoding="utf-8")

    floor = asyncio.run(collect_floor(specs_root))

    assert all("engine is running" not in note for note in floor.notes)
