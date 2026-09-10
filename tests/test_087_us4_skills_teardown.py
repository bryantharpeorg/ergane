"""US4: skill teardown removes only digest-owned installation entries."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from factory.cli.skills import (
    CANONICAL_SKILLS_ROOT,
    COMPATIBILITY_SKILLS_ROOT,
    MANIFEST_REL,
    install,
    skills_teardown,
)


@dataclass(frozen=True)
class Home:
    root: Path
    state: Path


def make_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Home:
    root = tmp_path / "home"
    state = tmp_path / "state"
    root.mkdir()
    state.mkdir()
    monkeypatch.setenv("HOME", str(root))
    monkeypatch.setenv("ERGANE_STATE_HOME", str(state))
    monkeypatch.delenv("FACTORY_STATE_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    return Home(root, state)


def manifest_path(home: Home) -> Path:
    return home.state / MANIFEST_REL


def read_manifest(home: Home) -> dict[str, Any]:
    return json.loads(manifest_path(home).read_text(encoding="utf-8"))


def snapshot(root: Path) -> dict[str, tuple[str, bytes]]:
    result: dict[str, tuple[str, bytes]] = {}
    if not root.exists():
        return result
    for path in sorted(root.rglob("*")):
        relative = str(path.relative_to(root))
        if path.is_symlink():
            result[relative] = ("symlink", os.readlink(path).encode("utf-8"))
        elif path.is_file():
            result[relative] = ("file", path.read_bytes())
        elif path.is_dir():
            result[relative] = ("directory", b"")
        else:
            result[relative] = ("other", path.lstat().st_dev.to_bytes(8, "big"))
    return result


def test_unchanged_owned_entries_are_removed_without_unrelated_loss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = make_home(tmp_path, monkeypatch)
    install()
    unrelated_file = home.root / "operator-note.txt"
    unrelated_file.write_text("operator data\n", encoding="utf-8")
    unrelated_empty = home.root / "operator-empty-dir"
    unrelated_empty.mkdir()
    before = snapshot(home.root)
    result = skills_teardown()

    after = snapshot(home.root)
    assert after.keys() == {
        key for key in before if not key.startswith((".agents", ".claude"))
    }
    assert not manifest_path(home).exists()
    assert unrelated_file.read_text(encoding="utf-8") == "operator data\n"
    assert unrelated_empty.exists()
