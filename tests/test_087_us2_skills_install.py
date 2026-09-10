"""US2: one explicit skill install is isolated, owned and collision-safe."""

from __future__ import annotations

import json
import hashlib
import os
import shutil
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest
from factory.cli.main import _build_parser

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


def make_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Home:
    root = tmp_path / "home"
    state = tmp_path / "state"
    root.mkdir()
    state.mkdir()
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    monkeypatch.delenv("ERGANE_STATE_HOME", raising=False)
    monkeypatch.delenv("FACTORY_STATE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(root))
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    return Home(root, state)


def manifest_path(home: Home) -> Path:
    return home.state / MANIFEST_PATH_REL


def read_manifest(home: Home) -> dict[str, Any]:
    return json.loads(manifest_path(home).read_text(encoding="utf-8"))


def full_snapshot(home: Home) -> dict[str, tuple[int, int, bytes]]:
    """Capture paths and times under both declared client roots."""

    result: dict[str, tuple[int, int, bytes]] = {}
    for root in (home.root / ".agents", home.root / ".claude"):
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() and not path.is_symlink():
                continue
            stat = path.lstat()
            content = path.read_bytes() if path.is_file() else os.readlink(path).encode()
            result[str(path.relative_to(home.root))] = (stat.st_mtime_ns, stat.st_size, content)
    return result


def test_clean_home_install_writes_canonical_skills_and_schema_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = make_home(tmp_path, monkeypatch)
    result = install()

    assert result.manifest_path == manifest_path(home)
    assert result.unavailable_clients == ("codex", "claude")
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
    before_manifest = (manifest_path(home).lstat().st_mtime_ns, manifest_path(home).read_bytes())
    assert before

    result = install()
    after = full_snapshot(home)
    after_manifest = (manifest_path(home).lstat().st_mtime_ns, manifest_path(home).read_bytes())

    assert result.created == ()
    assert result.upgraded == ()
    assert result.collisions == ()
    assert before == after
    assert before_manifest == after_manifest


def test_collision_truth_table_preserves_exact_paths_and_installs_siblings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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
    assert os.readlink(compatibility_root / "floor-status") == "/nowhere/skills/floor-status"
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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = make_home(tmp_path, monkeypatch)
    canonical = home.root / CANONICAL_SKILLS_ROOT / "floor-status"
    canonical.mkdir(parents=True)
    target = canonical / "SKILL.md"
    source = Path(__file__).parents[1] / ".agents" / "skills" / "floor-status" / "SKILL.md"
    shutil.copyfile(source, target)
    before = (target.lstat().st_mtime_ns, target.read_bytes())

    result = install()

    assert not any(
        path.name == "SKILL.md" and path.parent.name == "floor-status"
        for path in result.created
    )
    assert any(entry.path == ".agents/skills/floor-status/SKILL.md" for entry in result.collisions)
    assert ".agents/skills/floor-status/SKILL.md" not in read_manifest(home)["entries"]
    after = (target.lstat().st_mtime_ns, target.read_bytes())
    assert after == before


def test_owned_stale_path_upgrades_and_modified_owned_path_is_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = make_home(tmp_path, monkeypatch)
    install()
    from factory.cli.skills import _digest

    canonical = home.root / CANONICAL_SKILLS_ROOT / "floor-status" / "SKILL.md"
    stale = home.root / CANONICAL_SKILLS_ROOT / "build-metrics" / "SKILL.md"
    original = canonical.read_bytes()
    canonical.write_bytes(original + b"\n# locally modified\n")
    stale.write_bytes(stale.read_bytes() + b"\n# stale owned bytes\n")
    stale_manifest = read_manifest(home)
    stale_manifest["entries"][".agents/skills/build-metrics/SKILL.md"]["digest"] = _digest(
        stale.read_bytes()
    )
    manifest_path(home).write_text(
        json.dumps(stale_manifest, sort_keys=True), encoding="utf-8"
    )

    result = install()

    assert canonical.read_bytes().endswith(b"\n# locally modified\n")
    assert any(entry.path == ".agents/skills/floor-status/SKILL.md" for entry in result.collisions)
    assert not stale.read_bytes().endswith(b"\n# stale owned bytes\n")
    assert any(
        path.name == "SKILL.md" and path.parent.name == "build-metrics"
        for path in result.upgraded
    )
    manifest = read_manifest(home)
    assert manifest["entries"][".agents/skills/floor-status/SKILL.md"]
    assert manifest["entries"][".agents/skills/build-metrics/SKILL.md"]


def test_parent_symlink_cannot_redirect_the_declared_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = make_home(tmp_path, monkeypatch)
    escape = tmp_path / "outside"
    escape.mkdir()
    (home.root / ".agents").symlink_to(escape)
    (home.root / ".claude").mkdir()

    result = install()

    assert list(escape.iterdir()) == []
    assert any(entry.path == ".agents" for entry in result.collisions)
    assert not (home.root / ".claude" / "skills" / "floor-status").exists()
    assert any(
        entry.path == ".claude/skills/floor-status" for entry in result.collisions
    )


def test_invalid_manifest_path_refuses_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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

    with pytest.raises(ManifestError, match="OUT-OF-ROOT"):
        install()

    assert full_snapshot(home) == before


def test_interrupted_file_write_does_not_replace_or_claim_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = make_home(tmp_path, monkeypatch)
    real_write = Path.write_bytes

    def failing_write(self: Path, data: bytes) -> int:
        if ".SKILL.md.ergane-install-" in self.name:
            raise OSError("interrupted")
        return real_write(self, data)

    monkeypatch.setattr(Path, "write_bytes", failing_write)
    result = install()
    monkeypatch.undo()

    assert result.collisions
    assert any(entry.state == "write-failed" for entry in result.collisions)
    assert ".agents/skills/away-mode/SKILL.md" not in read_manifest(home)["entries"]
    assert not any(
        path.name == "SKILL.md" and path.parent.name == "floor-status"
        for path in result.created
    )


def test_failed_manifest_replacement_leaves_prior_ownership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = make_home(tmp_path, monkeypatch)
    first = install()
    old_manifest = read_manifest(home)
    canonical = home.root / CANONICAL_SKILLS_ROOT / "floor-status" / "SKILL.md"
    canonical.write_bytes(canonical.read_bytes() + b"\n# new release\n")
    stale_manifest = read_manifest(home)
    stale_manifest["entries"][".agents/skills/floor-status/SKILL.md"]["digest"] = hashlib.sha256(
        canonical.read_bytes()
    ).hexdigest()
    manifest_path(home).write_text(
        json.dumps(stale_manifest, sort_keys=True), encoding="utf-8"
    )
    old_manifest = read_manifest(home)

    real_replace = os.replace

    def failing_replace(source_path: Path, destination_path: Path) -> None:
        if "manifest.json" in source_path.name:
            raise OSError("manifest replace failed")
        return real_replace(source_path, destination_path)

    monkeypatch.setattr(os, "replace", failing_replace)
    result = install()
    monkeypatch.undo()

    assert result.collisions
    assert read_manifest(home) == old_manifest
    assert ".agents/skills/floor-status/SKILL.md" in read_manifest(home)["entries"]
    assert first.manifest_path.read_bytes()


def test_manifest_follows_declared_state_while_client_roots_stay_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = make_home(tmp_path, monkeypatch)
    monkeypatch.delenv("ERGANE_STATE_HOME", raising=False)
    state = home.state / "xdg"
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    home = replace(home, state=state)
    client_root = tmp_path / "bin"
    client_root.mkdir()
    (client_root / "codex").write_text("#!/bin/sh\ntrue\n", encoding="utf-8")
    (client_root / "codex").chmod(0o755)
    monkeypatch.setenv("PATH", str(client_root))

    result = install()

    assert manifest_path(home).parent == home.state / "ergane" / "skills"
    assert result.destination_for("codex") == home.root / ".agents" / "skills"
    assert result.destination_for("claude") == home.root / ".claude" / "skills"
    assert result.client_available("codex") is True
    assert result.client_available("claude") is False
    assert result.unavailable_clients == ("claude",)


def test_cli_exposes_the_explicit_install_verb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    make_home(tmp_path, monkeypatch)
    args = _build_parser().parse_args(["skills", "install"])

    assert args.run(args) == 0
    assert (tmp_path / "home" / ".agents" / "skills" / "floor-status").is_dir()
