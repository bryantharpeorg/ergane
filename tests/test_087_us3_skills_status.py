"""US3: skills status distinguishes filesystem states without mutation."""

from __future__ import annotations

import importlib.metadata
import json
import os
import subprocess
import urllib.request
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest
from factory.cli.main import _build_parser

from factory.cli.skills import (
    CANONICAL_SKILLS_ROOT,
    COMPATIBILITY_SKILLS_ROOT,
    install,
    skills_status,
    render_status,
)


RUNBOOK = "docs/codex-primary-operator-migration-runbook-2026-09-09.md"


def manifest_path(home: Path) -> Path:
    return home.parent / "state" / "ergane" / "skills" / "manifest.json"


def make_status_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    home = tmp_path / "home"
    state = tmp_path / "state"
    home.mkdir()
    state.mkdir()
    monkeypatch.delenv("ERGANE_STATE_HOME", raising=False)
    monkeypatch.delenv("FACTORY_STATE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    return home, state


def entry(home: Path, client: str, skill: str):
    status = skills_status()
    matches = [
        item
        for item in status.entries
        if item.client == client and item.skill == skill
    ]
    assert len(matches) == 1
    return matches[0]


def status_cases(home: Path, monkeypatch: pytest.MonkeyPatch):
    def absent():
        for root in (CANONICAL_SKILLS_ROOT, COMPATIBILITY_SKILLS_ROOT):
            for path in (home / root).glob("*"):
                if path.is_symlink():
                    path.unlink()
                else:
                    for child in sorted(path.rglob("*"), reverse=True):
                        if child.is_dir():
                            child.rmdir()
                        else:
                            child.unlink()
                    path.rmdir()

    def stale():
        manifest = json.loads(manifest_path(home).read_text(encoding="utf-8"))
        manifest["source_version"] = "0.0.1"
        manifest["package_version"] = "0.0.1"
        manifest_path(home).write_text(json.dumps(manifest), encoding="utf-8")

    def modified():
        skill = home / CANONICAL_SKILLS_ROOT / "floor-status" / "SKILL.md"
        skill.write_bytes(skill.read_bytes() + b"\n# operator change\n")

    def collided():
        path = home / CANONICAL_SKILLS_ROOT / "build-metrics" / "SKILL.md"
        path.write_bytes(b"operator-owned bytes\n")
        manifest = json.loads(manifest_path(home).read_text(encoding="utf-8"))
        manifest["entries"].pop(path.relative_to(home).as_posix())
        manifest["entries"].pop(".claude/skills/build-metrics")
        manifest_path(home).write_text(json.dumps(manifest), encoding="utf-8")

    def broken_alias():
        path = home / COMPATIBILITY_SKILLS_ROOT / "spec-html"
        path.unlink()
        path.symlink_to("/nowhere/that/does/not/exist")

    def unavailable_version():
        def refuse(name: str):
            raise importlib.metadata.PackageNotFoundError(name)

        monkeypatch.setattr(importlib.metadata, "version", refuse)

    def unsupported_manifest():
        manifest = json.loads(manifest_path(home).read_text(encoding="utf-8"))
        manifest["schema"] = 999
        manifest_path(home).write_text(json.dumps(manifest), encoding="utf-8")

    return (
        ("absent", absent, "absent", "Run `ergane skills install`."),
        (
            "current-filesystem",
        lambda: manifest_path(home).unlink(),
            "current-filesystem",
            (
                "No repair needed; fresh client loading remains unqualified. "
                f"Authorize fresh evidence through the {RUNBOOK} shared-discovery gate."
            ),
        ),
        (
            "stale",
            stale,
            "stale",
            "Run `ergane skills install` after preserving desired local changes.",
        ),
        (
            "modified",
            modified,
            "modified",
            "Preserve the local bytes; run install for any unmodified paths.",
        ),
        (
            "collided",
            collided,
            "collided",
            "Preserve the conflicting path; resolve it deliberately before install.",
        ),
        (
            "broken-alias",
            broken_alias,
            "broken-alias",
            "Run `ergane skills install` to replace the broken compatibility alias.",
        ),
        (
            "unavailable-version",
            unavailable_version,
            "unavailable-version",
            "Install the packaged CLI to provide skill version metadata.",
        ),
        (
            "unsupported-manifest",
            unsupported_manifest,
            "unsupported-manifest",
            "Back up and explicitly migrate or remove the unsupported manifest.",
        ),
    )


@pytest.mark.parametrize(
    "name",
    (
        "absent",
        "current-filesystem",
        "stale",
        "modified",
        "collided",
        "broken-alias",
        "unavailable-version",
        "unsupported-manifest",
    ),
)
def test_status_truth_table_reports_state_and_remedy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    home, _ = make_status_home(tmp_path, monkeypatch)
    install()

    cases = dict(
        (name, value)
        for name, *value in status_cases(home, monkeypatch)
    )
    mutate, expected_state, expected_remedy = cases[name]
    mutate()

    status = skills_status()
    if name in {"absent", "stale", "modified", "collided", "broken-alias"}:
        if name == "collided":
            observed = entry(home, "claude", "build-metrics")
        elif name == "broken-alias":
            observed = entry(home, "claude", "spec-html")
        else:
            observed = entry(home, "codex", "floor-status")
        assert observed.state == expected_state
        assert observed.remedy == expected_remedy
        assert observed.package_version == "0.5.0"
        if name == "stale":
            assert observed.installed_version == "0.0.1"
    elif name == "current-filesystem":
        observed = entry(home, "codex", "floor-status")
        assert observed.state == expected_state
        assert observed.remedy == expected_remedy
        assert observed.installed_version is None
    elif name == "unavailable-version":
        observed = entry(home, "codex", "floor-status")
        assert observed.state == expected_state
        assert observed.remedy == expected_remedy
        assert status.package_version is None
    else:
        assert all(
            item.state == expected_state for item in status.entries
        )
        assert all(
            item.remedy == expected_remedy for item in status.entries
        )
    assert "modification time" not in status.rendered.lower()


def test_checkout_without_package_metadata_or_manifest_is_explicitly_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    state = tmp_path / "state"
    home.mkdir()
    state.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))

    def refuse(name: str):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", refuse)
    status = skills_status()

    assert status.manifest_status == "unavailable-version"
    assert status.package_version is None
    assert all(item.installed_version is None for item in status.entries)
    assert all(item.state == "unavailable-version" for item in status.entries)
    assert all(
        "timestamp" not in item.remedy.lower() for item in status.entries
    )


def test_newer_incompatible_manifest_is_explicitly_unsupported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home, _ = make_status_home(tmp_path, monkeypatch)
    manifest_path(home).parent.mkdir(parents=True)
    manifest_path(home).write_text(
        json.dumps(
            {
                "schema": 2,
                "package_version": "0.6.0",
                "canonical_destination": ".agents/skills",
                "compatibility_destination": ".claude/skills",
                "entries": {},
            }
        ),
        encoding="utf-8",
    )
    status = skills_status()

    assert status.manifest_status == "unsupported-manifest"
    assert status.package_version == "0.5.0"
    assert all(item.installed_version == "0.6.0" for item in status.entries)
    assert all(item.state == "unsupported-manifest" for item in status.entries)
    assert status.manifest_schema == 2


def filesystem_snapshot(root: Path) -> dict[str, tuple[str, bytes | str]]:
    snapshot: dict[str, tuple[str, bytes | str]] = {}
    for path in sorted((root, *root.rglob("*")), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            snapshot[relative] = ("symlink", os.readlink(path))
        elif path.is_dir():
            snapshot[relative] = ("directory", b"")
        elif path.is_file():
            snapshot[relative] = ("file", path.read_bytes())
    return snapshot


def deny_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    real_open = Path.open

    def read_only_open(self: Path, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if any(character in mode for character in ("+", "a", "w", "x")):
            raise AssertionError(f"status opened {self} for writing ({mode})")
        return real_open(self, mode, *args, **kwargs)

    def refuse(operation: str) -> Callable[..., Any]:
        def denied(*_args: Any, **_kwargs: Any) -> Any:
            raise AssertionError(f"status attempted {operation}")

        return denied

    monkeypatch.setattr(Path, "open", read_only_open)
    for operation in ("mkdir", "replace", "symlink_to", "touch", "unlink", "write_bytes", "write_text"):
        monkeypatch.setattr(Path, operation, refuse(operation))
    for operation in ("replace", "symlink"):
        monkeypatch.setattr(os, operation, refuse(operation))
    for name in ("Popen", "run", "check_call", "check_output", "getoutput", "getstatusoutput"):
        monkeypatch.setattr(subprocess, name, refuse(name))
    monkeypatch.setattr(urllib.request, "urlopen", refuse("urlopen"))
    monkeypatch.setattr(httpx, "request", refuse("httpx.request"))
    monkeypatch.setattr(httpx, "Client", refuse("httpx.Client"))


def test_status_command_is_read_only_without_client_or_network_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home, _ = make_status_home(tmp_path, monkeypatch)
    install()
    before = (
        filesystem_snapshot(home),
        filesystem_snapshot(home.parent / "state"),
    )
    deny_mutation(monkeypatch)

    arguments = _build_parser().parse_args(["skills", "status"])
    exit_code = arguments.run(arguments)

    assert exit_code == 0
    assert (
        filesystem_snapshot(home),
        filesystem_snapshot(home.parent / "state"),
    ) == before


def test_current_filesystem_presentation_does_not_claim_client_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home, _ = make_status_home(tmp_path, monkeypatch)
    install()
    manifest_path(home).unlink()

    status = skills_status()
    rendered = render_status(status)

    assert "current-filesystem" in rendered
    assert "fresh client loading remains unqualified" in rendered
    assert RUNBOOK in rendered
    assert "shared-discovery gate" in rendered
    assert "client loaded" not in rendered
