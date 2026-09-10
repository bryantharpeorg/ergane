"""US4: skill teardown removes only digest-owned installation entries."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Sequence
from pathlib import Path
from typing import Any

import pytest

from factory.cli.skills import (
    CANONICAL_SKILLS_ROOT,
    COMPATIBILITY_SKILLS_ROOT,
    MANIFEST_REL,
    SkillTeardownResult,
    install,
    skills_teardown,
)
from factory.cli.uninstall import CLEAR_STATE, STEPS, TeardownRequest, run_teardown
from factory.supervision.units import resolve_layout


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


def test_modified_canonical_and_retargeted_alias_entries_are_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = make_home(tmp_path, monkeypatch)
    install()
    canonical = home.root / CANONICAL_SKILLS_ROOT / "floor-status" / "SKILL.md"
    alias = home.root / COMPATIBILITY_SKILLS_ROOT / "away-mode"
    canonical.write_text("operator changed this\n", encoding="utf-8")
    alias.unlink()
    alias.symlink_to("../../operator/away-mode")
    before = snapshot(home.root)
    expected_manifest_digest = read_manifest(home)["entries"][str(
        canonical.relative_to(home.root)
    )]["digest"]

    result = skills_teardown()

    assert result.preserved == (
        ".agents/skills/floor-status/SKILL.md",
        ".claude/skills/away-mode",
    )
    after = snapshot(home.root)
    canonical_relative = str(canonical.relative_to(home.root))
    alias_relative = str(alias.relative_to(home.root))
    assert after[canonical_relative] == before[canonical_relative]
    assert after[alias_relative] == before[alias_relative]
    assert after.keys() == {
        canonical_relative,
        alias_relative,
        ".agents",
        ".claude",
        ".agents/skills",
        ".agents/skills/floor-status",
        ".claude/skills",
    }
    manifest = read_manifest(home)
    assert set(manifest["entries"]) == {
        ".agents/skills/floor-status/SKILL.md",
        ".claude/skills/away-mode",
    }
    assert manifest["entries"][".agents/skills/floor-status/SKILL.md"]["digest"] == expected_manifest_digest
    assert os.readlink(alias) == "../../operator/away-mode"


def test_repeated_partial_teardown_is_idempotent_and_states_are_distinct(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = make_home(tmp_path, monkeypatch)
    install()
    modified = home.root / CANONICAL_SKILLS_ROOT / "build-metrics" / "SKILL.md"
    missing = home.root / CANONICAL_SKILLS_ROOT / "floor-status" / "SKILL.md"
    modified.write_text("operator data\n", encoding="utf-8")
    missing.unlink()
    unrelated = home.root / "unrelated"
    unrelated.mkdir()
    first = skills_teardown()

    assert first.preserved == (".agents/skills/build-metrics/SKILL.md",)
    assert first.already_absent == (".agents/skills/floor-status/SKILL.md",)
    assert set(read_manifest(home)["entries"]) == {".agents/skills/build-metrics/SKILL.md"}
    assert first.removed

    before = snapshot(home.root)
    second = skills_teardown()
    after = snapshot(home.root)

    assert second == SkillTeardownResult(
        manifest_path=manifest_path(home),
        removed=(),
        preserved=(".agents/skills/build-metrics/SKILL.md",),
        already_absent=(),
    )
    assert before == after
    assert unrelated.exists()


class TeardownRun:
    def __init__(self, code: int, stdout: str, stderr: str) -> None:
        self.code = code
        self.stdout = stdout
        self.stderr = stderr


def drive(request: TeardownRequest, steps: Sequence = STEPS) -> TeardownRun:
    import io
    import sys

    from factory.cli.errors import OperatorError

    output = io.StringIO()
    old_stdout = sys.stdout
    try:
        sys.stdout = output
        code = run_teardown(request, steps=steps)
    except OperatorError as refusal:
        sys.stdout = old_stdout
        return TeardownRun(refusal.code, output.getvalue(), str(refusal))
    finally:
        sys.stdout = old_stdout
    return TeardownRun(code, output.getvalue(), "")


def plan_lines(stdout: str) -> list[str]:
    return [line for line in stdout.splitlines() if line[:1].isdigit() and "/" in line[:4]]


def test_wide_uninstall_purge_preserves_only_needed_skill_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = make_home(tmp_path, monkeypatch)
    install()
    modified = home.root / CANONICAL_SKILLS_ROOT / "build-metrics" / "SKILL.md"
    modified.write_text("operator changed this\n", encoding="utf-8")
    unrelated_state = home.state / "ergane" / "operator-state.json"
    unrelated_state.write_text("{}\n", encoding="utf-8")
    (home.state / "ergane" / "unrelated").mkdir(parents=True)
    (home.state / "ergane" / "unrelated" / "state").write_text("old\n", encoding="utf-8")
    external: list[tuple] = []
    layout = resolve_layout(
        home=home.root,
        generated_dir=home.state / "supervision",
        temporal_mode="external",
    )
    request = TeardownRequest(
        layout=layout,
        purge=True,
        run=lambda argv: external.append(tuple(argv)) or None,
        open_epics=lambda: (),
    )

    first = drive(request)

    assert first.code == 0, first.stderr
    assert first.stdout.index("5/7 skill teardown") < first.stdout.index("6/7 clear state")
    manifest = read_manifest(home)
    assert set(manifest["entries"]) == {".agents/skills/build-metrics/SKILL.md"}
    assert modified.read_text(encoding="utf-8") == "operator changed this\n"
    assert not unrelated_state.exists()
    assert not (home.state / "ergane" / "unrelated").exists()
    assert manifest_path(home).is_file()
    assert not (home.state / "ergane" / "repos.json").exists()

    second = drive(request)

    assert second.code == 0, second.stderr
    assert "skill teardown" in second.stdout
    assert "already absent: nothing to do" not in second.stdout
    assert set(read_manifest(home)["entries"]) == {".agents/skills/build-metrics/SKILL.md"}


def test_check_drives_real_skill_and_state_surveys_without_performs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = make_home(tmp_path, monkeypatch)
    install()
    modified = home.root / CANONICAL_SKILLS_ROOT / "build-metrics" / "SKILL.md"
    modified.write_text("operator changed this\n", encoding="utf-8")
    before = snapshot(home.root)
    before_manifest = manifest_path(home).read_bytes()
    performed: list[str] = []

    def recording(step):
        def perform(_request, _survey):
            performed.append(step.name)
            return ()

        return perform

    table = tuple(
        type(step)(name=step.name, survey=step.survey, perform=recording(step))
        for step in STEPS
    )
    layout = resolve_layout(
        home=home.root,
        generated_dir=home.state / "supervision",
        temporal_mode="external",
    )
    result = drive(
        TeardownRequest(layout=layout, check=True, open_epics=lambda: ()),
        steps=table,
    )

    assert result.code == 0, result.stderr
    assert performed == []
    assert snapshot(home.root) == before
    assert manifest_path(home).read_bytes() == before_manifest
    assert result.stdout.index("5/7 skill teardown") < result.stdout.index("6/7 clear state")


def test_malformed_manifest_refuses_before_the_wider_teardown_acts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = make_home(tmp_path, monkeypatch)
    install()
    manifest = read_manifest(home)
    manifest["entries"]["../../escape"] = {"kind": "file", "digest": "0" * 64}
    manifest_path(home).write_text(json.dumps(manifest), encoding="utf-8")
    before = snapshot(home.root)

    layout = resolve_layout(
        home=home.root,
        generated_dir=home.state / "supervision",
        temporal_mode="external",
    )
    result = drive(TeardownRequest(layout=layout, open_epics=lambda: ()))

    assert result.code == 1
    assert "MANIFEST-PATH-OUT-OF-ROOT" in result.stderr
    assert snapshot(home.root) == before
