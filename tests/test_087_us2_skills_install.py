"""US2: one explicit skill install is isolated, owned and collision-safe."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from factory.cli.skills import (
    CANONICAL_SKILLS_ROOT,
    COMPATIBILITY_SKILLS_ROOT,
    MANIFEST_REL,
    ManifestError,
    install,
)


MANIFEST_PATH_REL = Path("ergane") / "skills" / "manifest.json"


@dataclass(frozen=True)
class Home:
    root: Path
    state: Path


def make_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, xdg: str = "ERGANE_STATE_HOME"
) -> Home:
    root = tmp_path / "home"
    state = tmp_path / "state"
    root.mkdir()
    state.mkdir()
    if xdg == "XDG_STATE_HOME":
        monkeypatch.setenv("XDG_STATE_HOME", str(state))
    else:
        monkeypatch.setenv("ERGANE_STATE_HOME", str(state))
    monkeypatch.setenv("HOME", str(root))
    return Home(root, state)


def manifest_path(home: Home) -> Path:
    return home.state / MANIFEST_PATH_REL


def read_manifest(home: Home) -> dict[str, Any]:
    return json.loads(manifest_path(home).read_text(encoding="utf-8"))


def snapshot(home: Home) -> dict[str, tuple[int, int, bytes]]:
    """Capture kinds and bytes; timestamps are captured separately by callers."""

    result: dict[str, tuple[int, int, bytes]] = {}
    for root_name in (".agents", ".claude"):
        root = home.root / root_name
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            stat = path.lstat()
            content = path.read_bytes() if path.is_file() else b"<non-file>"
            result[str(path.relative_to(home.root))] = (stat.st_mtime_ns, stat.st_size, content)
    return result


def full_snapshot(home: Home) -> dict[str, tuple[int, int, bytes]]:
    """Capture paths and times under both declared client roots."""

    result: dict[str, tuple[int, int, bytes]] = {}
    for root in (home.root / ".agents", home.root / ".claude"):
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            stat = path.lstat()
            content = path.read_bytes() if path.is_file() else path.readlink().encode()
            result[str(path.relative_to(home.root))] = (stat.st_mtime_ns, stat.st_size, content)
    return result


def test_clean_home_install_writes_canonical_skills_and_schema_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = make_home(tmp_path, monkeypatch)
    result = install()

    assert result.manifest_path == manifest_path(home)
    assert result.unavailable_clients == ()
    for skill in ("floor-status", "build-metrics", "spec-html"):
        canonical = home.root / CANONICAL_SKILLS_ROOT / skill
        compatibility = home.root / COMPATIBILITY_SKILLS_ROOT / skill
        assert canonical.is_dir()
        assert compatibility.is_symlink()
        assert compatibility.resolve(strict=True) == canonical.resolve(strict=True)

    manifest = read_manifest(home)
    assert manifest["schema"] == 1
    assert manifest["source_version"]
    assert manifest["package_version"] == manifest["source_version"]
    assert manifest["canonical_destination"] == ".agents/skills"
    assert manifest["compatibility_destination"] == ".claude/skills"
    assert manifest["entries"][".agents/skills/floor-status/SKILL.md"]["digest"]
    alias = manifest["entries"][".claude/skills/floor-status"]
    assert alias["kind"] == "alias"
    assert alias["target"] == "../../.agents/skills/floor-status"
    assert alias["digest"]


def test_identical_install_is_byte_and_timestamp_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = make_home(tmp_path, monkeypatch)
    install()
    before = full_snapshot(home)
    assert before

    result = install()
    after = full_snapshot(home)

    assert result.created == ()
    assert result.upgraded == ()
    assert result.collisions == ()
    assert before == after


def test_collision_truth_table_preserves_exact_paths_and_installs_siblings(
    tmp_path: Path,
) -> None:
    home = make_home(tmp_path, monkeypatch)
    canonical_root = home.root / CANONICAL_SKILLS_ROOT
    compatibility_root = home.root / COMPATIBILITY_SKILLS_ROOT
    (canonical_root / "floor-status").mkdir(parents=True)
    (canonical_root / "floor-status" / "SKILL.md").write_text("operator data\n", encoding="utf-8")
    (canonical_root / "build-metrics" / "SKILL.md").parent.mkdir(parents=True)
    (canonical_root / "build-metrics" / "SKILL.md").write_text("identical\n", encoding="utf-8")
    compatibility_root.mkdir(parents=True)
    (compatibility_root / "floor-status").symlink_to("/nowhere/skills/floor-status")
    (compatibility_root / "build-metrics").mkdir()
    (compatibility_root / "spec-html").write_bytes(b"operator bytes\n")

    result = install()

    assert (canonical_root / "floor-status" / "SKILL.md").read_text(encoding="utf-8") == "operator data\n"
    assert (compatibility_root / "floor-status").readlink() == "/nowhere/skills/floor-status"
    assert (compatibility_root / "build-metrics").is_dir()
    assert (compatibility_root / "spec-html").read_bytes() == b"operator bytes\n"
    assert {entry.path for entry in result.collisions} >= {
        ".agents/skills/floor-status/SKILL.md",
        ".claude/skills/floor-status",
        ".claude/skills/build-metrics",
        ".claude/skills/spec-html",
    }
    assert ".agents/skills/away-mode/SKILL.md" not in {
        entry.path for entry in result.collisions
    }
    assert (home.root / ".agents" / "skills" / "away-mode" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    manifest = read_manifest(home)
    assert ".agents/skills/floor-status/SKILL.md" not in manifest["entries"]
    assert ".claude/skills/spec-html" not in manifest["entries"]


def test_identical_unowned_entries_are_reusable_but_never_adopted(
    tmp_path: Path,
) -> None:
    home = make_home(tmp_path, monkeypatch)
    canonical = home.root / CANONICAL_SKILLS_ROOT / "floor-status"
    canonical.mkdir(parents=True)
    from factory.cli.skills import packaged_inventory

    payload = next(record for record in packaged_inventory() if record.path == "floor-status/SKILL.md")
    source = None
    for candidate in Path(__file__).parents[1].glob(".agents/skills/floor-status/SKILL.md"):
        source = candidate
    assert source is not None
    shutil.copyfile(source, canonical / "SKILL.md")
    before = full_snapshot(home)

    result = install()

    assert result.created == ()
    assert any(entry.path == ".agents/skills/floor-status/SKILL.md" for entry in result.collisions)
    assert read_manifest(home)["entries"] == {}
    assert full_snapshot(home) == before


def test_owned_stale_path_upgrades_and_modified_owned_path_is_preserved(
    tmp_path: Path,
) -> None:
    home = make_home(tmp_path, monkeypatch)
    first = install()
    canonical = home.root / CANONICAL_SKILLS_ROOT / "floor-status" / "SKILL.md"
    stale = home.root / CANONICAL_SKILLS_ROOT / "build-metrics" / "SKILL.md"
    original = canonical.read_bytes()
    canonical.write_bytes(original + b"\n# locally modified\n")
    stale.write_bytes(stale.read_bytes() + b"\n# stale owned bytes\n")

    result = install()

    assert canonical.read_bytes() == original
    assert any(entry.path == ".agents/skills/floor-status/SKILL.md" for entry in result.collisions)
    assert stale.read_text(encoding="utf-8") != first.source_version
    assert any(entry.path == ".agents/skills/build-metrics/SKILL.md" for entry in result.upgraded)
    manifest = read_manifest(home)
    assert ".agents/skills/floor-status/SKILL.md" not in manifest["entries"]
    assert manifest["entries"][".agents/skills/build-metrics/SKILL.md"]


def test_parent_symlink_cannot_redirect_the_declared_destination(
    tmp_path: Path,
) -> None:
    home = make_home(tmp_path, monkeypatch)
    escape = tmp_path / "outside"
    escape.mkdir()
    (home.root / ".agents").symlink_to(escape)
    (home.root / ".claude").mkdir()

    result = install()

    assert list(escape.iterdir()) == []
    assert any(entry.path == ".agents" for entry in result.collisions)
    assert (home.root / ".claude" / "skills" / "floor-status").is_symlink()


def test_invalid_manifest_path_refuses_without_writing(
    tmp_path: Path,
) -> None:
    home = make_home(tmp_path, monkeypatch)
    path = manifest_path(home)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schema": 1,
                "source_version": "0.5.0",
                "package_version": "0.5.0",
                "canonical_destination": ".agents/skills",
                "compatibility_destination": ".claude/skills",
                "entries": {"../../evil": {"kind": "file", "digest": "0" * 64}},
            }
        ),
        encoding="utf-8",
    )
    before = full_snapshot(home)

    with pytest.raises(ManifestError, match="out-of-root"):
        install()

    assert full_snapshot(home) == before


def test_interrupted_file_write_does_not_replace_or_claim_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = make_home(tmp_path, monkeypatch)
    real_write = Path.write_bytes

    def failing_write(self: Path, data: bytes) -> int:
        if self.name == "SKILL.md":
            raise OSError("interrupted")
        return real_write(self, data)

    monkeypatch.setattr(Path, "write_bytes", failing_write)
    result = install()
    monkeypatch.undo()

    assert result.collisions
    assert read_manifest(home)["entries"] == {}
    assert not any(
        entry.path.endswith("SKILL.md")
        for entry in result.created
    )


def test_failed_manifest_replacement_leaves_prior_ownership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = make_home(tmp_path, monkeypatch)
    first = install()
    old_manifest = read_manifest(home)
    canonical = home.root / CANONICAL_SKILLS_ROOT / "floor-status" / "SKILL.md"
    canonical.write_bytes(canonical.read_bytes() + b"\n# new release\n")

    def failing_replace(self: Path, target: Path) -> None:
        if self.name == "manifest.json":
            raise OSError("manifest replace failed")
        return Path.replace(self, target)

    monkeypatch.setattr(Path, "replace", failing_replace)
    result = install()
    monkeypatch.undo()

    assert result.collisions
    assert read_manifest(home) == old_manifest
    assert ".agents/skills/floor-status/SKILL.md" not in read_manifest(home)["entries"]
    assert first.manifest_path.read_bytes()


def test_manifest_follows_declared_state_while_client_roots_stay_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = make_home(tmp_path, monkeypatch)
    monkeypatch.delenv("ERGANE_STATE_HOME", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(home.state / "xdg"))
    client_root = tmp_path / "bin"
    client_root.mkdir()
    (client_root / "codex").write_text("#!/bin/sh\ntrue\n", encoding="utf-8")
    (client_root / "codex").chmod(0o755)
    old_path = os.environ["PATH"]
    monkeypatch.setenv("PATH", str(client_root) + os.pathsep + old_path)

    result = install()

    assert manifest_path(home).parent == home.state / "xdg" / "ergane" / "skills"
    assert result.destination_for("codex") == home.root / ".agents" / "skills"
    assert result.destination_for("claude") == home.root / ".claude" / "skills"
    assert result.client_available("codex") is True
    assert result.client_available("claude") is False
    assert result.unavailable_clients == ("claude",)
