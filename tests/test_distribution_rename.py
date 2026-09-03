"""US1 of epic 056-the-factory-ships-as-a-package: the distribution is named what it can be published as.

The rename to `ergane-cli` is forced by PyPI occupancy (FR-001). Every other
name must stay exactly where it is: the import package stays `factory` (FR-002),
the console script stays `ergane` pointing at `factory.cli.main` (FR-003), and
the data files (`personas.yaml`, `merge_queue_ruleset.json`) stay inside the
import package (FR-007). The version is read from installed metadata (FR-004),
with a single declared source in `pyproject.toml` (FR-005), and a broken install
must report "unknown" rather than a plausible-looking literal (FR-006).

Tests here are written to fail against the pre-rename tree and to catch the
specific failure modes the plan calls out as traps:

- The version fallback must not be a version-shaped literal, because that would
  let the test comparing `--version` output to the metadata value pass by
  coincidence while the code actually printed a hardcoded number.
- The wheel-content assertions must inspect the built wheel, not the config,
  because hatchling ships only `.py` files unless explicitly told otherwise.
- The branch namespace and Temporal namespace must be asserted literally; value
  equality alone is not enough when one of the values is also a common word.
"""

from __future__ import annotations

import importlib.metadata
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path
from typing import Any

import pytest

from factory.cli import main as main_module
from factory.workgraph.worktree import branch_name
from factory.notify.service import DEFAULT_TEMPORAL_NAMESPACE

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
FACTORY_DIR = REPO_ROOT / "factory"
WHEEL_DIR = REPO_ROOT / "dist"

#: A deliberately unusual version that no literal in the source is allowed to use.
#: Used to prove `--version` reads from metadata rather than shadowing it.
TEST_VERSION = "99.88.77"


def _build_wheel(tmp_path: Path, *, version: str | None = None) -> Path:
    """Build a wheel in an isolated temporary copy of the repo.

    Mutating `pyproject.toml` in the real worktree would disturb other tests and
    leave tracked changes behind, so we copy the repo into `tmp_path`, edit the
    name/version there, and build from the copy. The returned path is the wheel
    file inside `tmp_path`.
    """
    copy_root = tmp_path / "repo"
    subprocess.run(
        ["git", "checkout-index", "-a", "-f", "--prefix", f"{copy_root}/"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    # `git checkout-index` copies the staged/tracked tree. To test the wheel
    # produced by the code in this worktree, copy the edited tracked files over.
    shutil.copy2(PYPROJECT, copy_root / "pyproject.toml")
    shutil.copy2(FACTORY_DIR / "cli" / "main.py", copy_root / "factory" / "cli" / "main.py")
    shutil.copy2(REPO_ROOT / "personas.example.yaml", copy_root / "personas.example.yaml")
    # 057/US1: the default floor ships as package data and must be in the copy.
    shutil.copy2(REPO_ROOT / "default_floor.md", copy_root / "default_floor.md")

    env = os.environ.copy()
    env["PYTHONPATH"] = ""
    env.pop("VIRTUAL_ENV", None)
    uv = shutil.which("uv")
    assert uv, "uv must be on PATH to build the wheel"
    try:
        subprocess.run(
            [uv, "build", "--wheel", "--out-dir", "dist"],
            cwd=copy_root,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
    except subprocess.CalledProcessError as exc:
        raise AssertionError(
            f"wheel build failed: stdout={exc.stdout!r} stderr={exc.stderr!r}"
        ) from None
    wheels = list((copy_root / "dist").glob("*.whl"))
    assert len(wheels) == 1, f"expected exactly one wheel, got {wheels}"
    return wheels[0]


def _wheel_metadata(whl: Path) -> dict[str, str]:
    """Parse the distribution metadata from a wheel."""
    with zipfile.ZipFile(whl) as zf:
        names = [n for n in zf.namelist() if n.endswith(".dist-info/METADATA")]
        assert len(names) == 1, f"expected one METADATA, got {names}"
        metadata = zf.read(names[0]).decode("utf-8")

    result: dict[str, str] = {}
    for line in metadata.splitlines():
        if line.startswith("Name: "):
            result["name"] = line[len("Name: "):].strip()
        elif line.startswith("Version: "):
            result["version"] = line[len("Version: "):].strip()
    return result


def _wheel_contents(whl: Path) -> list[str]:
    with zipfile.ZipFile(whl) as zf:
        return list(zf.namelist())


def _wheel_entry_points(whl: Path) -> dict[str, str]:
    with zipfile.ZipFile(whl) as zf:
        names = [n for n in zf.namelist() if n.endswith(".dist-info/entry_points.txt")]
        assert len(names) == 1, f"expected one entry_points.txt, got {names}"
        text = zf.read(names[0]).decode("utf-8")

    result: dict[str, str] = {}
    section: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if section == "console_scripts" and "=" in line:
            name, target = line.split("=", 1)
            result[name.strip()] = target.strip()
    return result


# --- T003 [US1] wheel distribution name and version ----------------------------


def test_wheel_distribution_name_is_ergane_cli_and_version_matches_declared(
    tmp_path: Path,
) -> None:
    """FR-001: a built wheel reports the distribution name `ergane-cli` and the
    version declared in `pyproject.toml`.
    """
    declared = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]
    whl = _build_wheel(tmp_path)
    metadata = _wheel_metadata(whl)
    assert metadata["name"] == "ergane-cli"
    assert metadata["version"] == declared


# --- T004 [P] [US1] wheel contents unchanged ----------------------------------


def test_wheel_still_contains_factory_package_with_data_files_and_ergane_script(
    tmp_path: Path,
) -> None:
    """FR-002, FR-003, FR-007: the wheel's import package is still `factory`,
    the data files live inside it, and the console script is still `ergane`.
    """
    whl = _build_wheel(tmp_path)
    contents = _wheel_contents(whl)
    entries = _wheel_entry_points(whl)

    assert any(p.startswith("factory/") and p.endswith("/__init__.py") for p in contents), (
        "wheel must still ship the `factory` import package"
    )
    assert "factory/personas.yaml" in contents, "wheel must ship personas.yaml inside factory/"
    assert "factory/mergequeue/merge_queue_ruleset.json" in contents, (
        "wheel must ship merge_queue_ruleset.json inside factory/"
    )
    assert entries.get("ergane") == "factory.cli.main:main", (
        "console script must still be `ergane` pointing at factory.cli.main:main"
    )


# --- T005 [US1] version from metadata wins ------------------------------------


def test_version_text_reports_metadata_version_for_ergane_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-004: `_version_text` reads `ergane-cli` metadata, not a literal.

    The only way to prove metadata wins is to make the metadata version differ
    from every literal in the source and assert the metadata value is printed.
    """
    # The function does a local `from importlib.metadata import version`, so
    # patching `importlib.metadata.version` is enough to redirect the lookup.
    real_version = importlib.metadata.version

    def _fake_version(distribution: str) -> str:
        if distribution in ("ergane", "ergane-cli"):
            return TEST_VERSION
        return real_version(distribution)

    monkeypatch.setattr("importlib.metadata.version", _fake_version)

    banner = main_module._version_text()
    assert f"ergane {TEST_VERSION}" in banner, (
        f"expected metadata version {TEST_VERSION!r} in banner, got:\n{banner}"
    )
    # Guard against a literal that happens to match our test version.
    source = (FACTORY_DIR / "cli" / "main.py").read_text(encoding="utf-8")
    assert TEST_VERSION not in source, (
        "TEST_VERSION must not appear as a literal in the source, or the test proves nothing"
    )


# --- T006 [US1] unknown version when metadata lookup fails --------------------


def test_version_reports_unknown_when_metadata_lookup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-006: a broken install reports the version as unknown.

    No version-shaped literal may be substituted, so we assert that the output
    contains "unknown" and that no plausible `X.Y.Z` pattern is emitted.
    """

    def _fake_version(distribution: str) -> str:
        # The current code calls version("ergane"); after the rename it calls
        # version("ergane-cli"). Make the fake fail for either so the test
        # exercises the unknown-fallback path regardless of implementation state.
        if distribution in ("ergane", "ergane-cli"):
            raise importlib.metadata.PackageNotFoundError(distribution)
        return importlib.metadata.version(distribution)

    monkeypatch.setattr("importlib.metadata.version", _fake_version)

    banner = main_module._version_text()
    # The first line is "ergane <version> (<revision>)".
    first_line = banner.splitlines()[0]
    assert "unknown" in first_line.lower(), (
        f"expected 'unknown' in version line, got: {first_line!r}"
    )
    assert not re.search(r"\d+\.\d+\.\d+", first_line), (
        f"a version-shaped literal must not appear when metadata is missing: {first_line!r}"
    )


# --- T007 [P] [US1] branch and Temporal namespaces unchanged ------------------


def test_branch_namespace_remains_factory_epic_node() -> None:
    """FR-013: the branch namespace that lands are attributed to is unchanged."""
    assert branch_name("056-the-factory-ships-as-a-package", "us1") == (
        "factory/056-the-factory-ships-as-a-package/us1"
    )


def test_default_temporal_namespace_is_unchanged() -> None:
    """FR-013: the default Temporal namespace is still `ergane`.

    The spec's FR-013 says the Temporal namespace must be unchanged. It was
    changed to `ergane` in 051-US2 and must not revert to `factory` under this
    rename. `scripts/ergane-env.sh` still exports `factory` for this specific
    repository's worker, but the product default stays `ergane`.
    """
    assert DEFAULT_TEMPORAL_NAMESPACE == "ergane"


def test_no_directory_or_import_renamed_to_ergane_cli() -> None:
    """FR-002 structural guard: no directory, module, or import statement was
    renamed by the distribution rename.

    The one allowed occurrence is the distribution-name argument to
    `importlib.metadata.version` in `_version_text`, because that names the
    distribution, not the import package.
    """
    for path in sorted(FACTORY_DIR.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if path == FACTORY_DIR / "supervision" / "engine_identity.py":
            # FR-009: the distribution name is allowed to appear exactly once, as the
            # argument to `version(...)` inside `cli_version()`.
            occurrences = list(re.finditer(r"\bergane[-_]cli\b", text))
            assert len(occurrences) == 1, (
                f"{path.relative_to(REPO_ROOT)} must reference `ergane-cli` only as the "
                f"distribution name passed to version(); found {len(occurrences)} occurrences"
            )
            assert 'version("ergane-cli")' in text, (
                "the single `ergane-cli` reference must be `version(\"ergane-cli\")`"
            )
            continue
        assert not re.search(r"\bergane[-_]cli\b", text), (
            f"{path.relative_to(REPO_ROOT)} imports or names `ergane_cli`/`ergane-cli`; "
            "the import package must stay `factory`"
        )
