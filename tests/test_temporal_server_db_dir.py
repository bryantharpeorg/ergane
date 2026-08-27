"""The managed Temporal dev server must create its database directory.

Found by running the demo stack rather than by reading it. On a cold state
volume the container died on first boot with

    Error: failed starting server: failed checking dir for database file:
    stat /home/ergane/.local/state/ergane/temporal: no such file or directory

because the dev server stats the database file's parent and refuses to create
it, and nothing along the path made the directory. `container/compose.demo.yaml`
points ERGANE_TEMPORAL_DB_FILENAME at
`.../state/ergane/temporal/engine.db`; the `temporal/` component exists in no
image layer and in no volume. The sibling `supervision/` component exists only
by the accident of being a mount point, which is what made the omission easy to
miss.

The whole container exits when this child dies, so the failure is total: no
install, no scaffold, no dispatch.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from factory.supervision import temporal_server


@pytest.fixture
def captured_run(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace the server coroutine so main() stops short of starting one."""
    seen: dict[str, Any] = {}

    async def fake_run(**kwargs: Any) -> int:
        seen.update(kwargs)
        return 0

    monkeypatch.setattr(temporal_server, "_run", fake_run)
    return seen


def test_main_creates_a_missing_database_directory(
    tmp_path: Path, captured_run: dict[str, Any]
) -> None:
    """The demo's exact shape: a db file one level below an empty state root."""
    state_root = tmp_path / "state" / "ergane"
    state_root.mkdir(parents=True)
    db_filename = state_root / "temporal" / "engine.db"
    assert not db_filename.parent.exists()

    code = temporal_server.main(["--db-filename", str(db_filename)])

    assert code == 0
    assert db_filename.parent.is_dir(), (
        "the dev server stats this directory and refuses to create it, so main() must"
    )
    assert captured_run["db_filename"] == str(db_filename)


def test_main_creates_every_missing_component_not_just_the_last(
    tmp_path: Path, captured_run: dict[str, Any]
) -> None:
    """A `mkdir` without `parents=True` would pass the test above and fail here."""
    db_filename = tmp_path / "a" / "b" / "c" / "engine.db"

    assert temporal_server.main(["--db-filename", str(db_filename)]) == 0

    assert db_filename.parent.is_dir()


def test_an_existing_database_directory_is_left_alone(
    tmp_path: Path, captured_run: dict[str, Any]
) -> None:
    """The warm-boot path: the directory and its database survive a restart."""
    db_dir = tmp_path / "temporal"
    db_dir.mkdir(parents=True)
    db_filename = db_dir / "engine.db"
    db_filename.write_bytes(b"existing history")

    assert temporal_server.main(["--db-filename", str(db_filename)]) == 0

    assert db_filename.read_bytes() == b"existing history"
