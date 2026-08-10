"""US5 cutover sweep: the four `factory-*` scripts are gone and `ergane` is the only front door.

This test is the independent verification named by the story: it reads the same
tree the operator will run against and refuses any state in which two front doors
exist or in which a removed script is still named outside the historical record.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
OLD_NAMES = ("factory-epic", "factory-roadmap", "factory-doctor", "factory-usage")
# Commands that the new `ergane` front door exposes for every old script.
OLD_TO_NEW = {
    "factory-epic": "ergane build",
    "factory-roadmap": "ergane spec",
    "factory-doctor": "ergane doctor",
    "factory-usage": "ergane usage",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_pyproject_toml_names_only_ergane() -> None:
    """[project.scripts] registers `ergane` and none of the four old scripts."""
    text = _read(PYPROJECT)
    match = re.search(r"\[project\.scripts\]\n(.*?)(?:\n\[|\Z)", text, re.S)
    assert match, "[project.scripts] section not found in pyproject.toml"
    section = match.group(1)
    scripts = {line.split("=")[0].strip() for line in section.splitlines() if "=" in line}
    assert "ergane" in scripts, "[project.scripts] must register `ergane`"
    assert not any(name in scripts for name in OLD_NAMES), (
        f"[project.scripts] still registers legacy scripts: {sorted(scripts & set(OLD_NAMES))}"
    )
    assert scripts == {"ergane"}, f"[project.scripts] must contain exactly `ergane`, got {sorted(scripts)}"


@pytest.mark.parametrize("old_name", OLD_NAMES)
def test_old_script_names_are_only_historical(old_name: str) -> None:
    """A repository-wide search finds each old name only under specs/ or docs/decisions.md."""
    result = subprocess.run(
        ["git", "grep", "-In", old_name],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    hits = [line for line in result.stdout.splitlines() if old_name in line]
    allowed_prefixes = ("specs/", "docs/decisions.md:")
    bad = [
        line
        for line in hits
        if not any(line.startswith(prefix) for prefix in allowed_prefixes)
    ]
    assert not bad, (
        f"`{old_name}` found outside the historical record:\n" + "\n".join(bad)
    )


@pytest.mark.parametrize("old_name", OLD_NAMES)
def test_operator_facing_strings_name_a_command_that_resolves(old_name: str) -> None:
    """Every operator-facing string under factory/ that recommends an old script names a real `ergane` command."""
    new_command = OLD_TO_NEW[old_name]
    result = subprocess.run(
        ["git", "grep", "-In", old_name, "--", "factory/"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    hits = result.stdout.splitlines()
    if not hits:
        return
    bad = []
    for line in hits:
        if new_command not in line:
            bad.append(line)
    assert not bad, (
        f"operator-facing strings under factory/ mention `{old_name}` without the new "
        f"command `{new_command}`:\n" + "\n".join(bad)
    )


def test_ergane_entry_point_is_installed() -> None:
    """`ergane --help` parses and the binary is on PATH."""
    executable = Path(sys.executable).parent / "ergane"
    result = subprocess.run(
        [str(executable), "--help"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert executable.exists(), "`ergane` console script is not installed"
    assert result.returncode == 0, f"`ergane --help` failed:\n{result.stderr.strip()}"
    assert "ergane" in result.stdout, "`ergane --help` does not name the program"
