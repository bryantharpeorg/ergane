"""US2 of epic 056-the-factory-ships-as-a-package: a stranger installs it and it works.

The suite until now could pass while an installed wheel failed, because every test
ran from a checkout and `_resolve_default_registry_path` falls back to walking to
`parents[1]` (the repo root). An install test must leave the checkout behind:
place the temporary environment where no parent directory holds `personas.yaml`,
so the fallback cannot rescue a packaging break.

These tests build the wheel, install it into a clean virtual environment, and
exercise the CLI as an end user would. They are intentionally in a separate file
from `test_distribution_rename.py` because they are slow (one wheel build, one
install per test class) and because they depend on the wheel being installable
rather than on its metadata alone.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FACTORY_DIR = REPO_ROOT / "factory"
PYPROJECT = REPO_ROOT / "pyproject.toml"


#: A deliberately unusual version used to prove `--version` reads from metadata.
#: Must not appear as a literal in the source.
TEST_VERSION = "99.88.77"


def _build_wheel(tmp_path: Path, *, version: str | None = None) -> Path:
    """Build a wheel in an isolated temporary copy of the repo.

    Mutating `pyproject.toml` in the real worktree would disturb other tests and
    leave tracked changes behind, so we copy the repo into `tmp_path`, edit the
    version there, and build from the copy. The returned path is the wheel
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

    if version is not None:
        pyproject_text = (copy_root / "pyproject.toml").read_text(encoding="utf-8")
        # Replace the `version = "..."` line while keeping the file valid TOML.
        new_text = []
        for line in pyproject_text.splitlines(keepends=True):
            if line.startswith('version = "'):
                line = f'version = "{version}"\n'
            new_text.append(line)
        (copy_root / "pyproject.toml").write_text("".join(new_text), encoding="utf-8")

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


def _run_in_venv(
    venv_bin: Path,
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    capture: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a command inside the temporary virtual environment.

    PATH is limited to the venv bin directory plus `/usr/bin:/bin`, so the
    installed wheel's console script is found and the development checkout is not.
    """
    base_env = {
        "PATH": f"{venv_bin}:/usr/bin:/bin",
        "HOME": os.environ.get("HOME", str(cwd)),
        "PYTHONPATH": "",
        "VIRTUAL_ENV": str(venv_bin.parent),
    }
    if env is not None:
        base_env.update(env)
    result = subprocess.run(
        args,
        cwd=cwd,
        env=base_env,
        capture_output=capture,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed with {result.returncode}: {args!r}\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )
    return result


def _install_wheel(venv_bin: Path, wheel: Path, *, cwd: Path) -> None:
    """Install the wheel into the temporary venv using uv pip."""
    uv = shutil.which("uv")
    assert uv, "uv must be on PATH"
    _run_in_venv(
        venv_bin,
        [uv, "pip", "install", str(wheel)],
        cwd=cwd,
    )


class _InstallFixture:
    """Shared setup for US2 install tests: build wheel + create clean venv."""

    def __init__(self, tmp_path: Path, *, version: str | None = None) -> None:
        self.tmp_path = tmp_path
        # Place the install root under tmp_path, which lives outside this repository.
        # A root inside REPO_ROOT would let the checkout-walk fallback rescue a
        # broken package, because parents[1] of factory/config.py would be the repo
        # root and would hold personas.yaml.
        self.install_root = tmp_path / "install"
        self.install_root.mkdir(parents=True)
        self.wheel = _build_wheel(tmp_path, version=version)

        # Create a venv in the isolated temp directory.
        subprocess.run(
            [sys.executable, "-m", "venv", str(self.install_root / "venv")],
            check=True,
            capture_output=True,
            text=True,
        )
        self.venv_bin = (self.install_root / "venv" / "bin").resolve()

        # Confirm there is no personas.yaml on any parent path of the install root.
        parent = self.install_root.resolve().parent
        while parent != parent.parent:
            assert not (parent / "personas.yaml").exists(), (
                f"parent {parent} holds personas.yaml; install test would not "
                "exercise the package-data path"
            )
            parent = parent.parent

        _install_wheel(self.venv_bin, self.wheel, cwd=self.install_root)

    @property
    def python(self) -> Path:
        return self.venv_bin / "python"

    def run(self, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return _run_in_venv(self.venv_bin, args, cwd=self.install_root, **kwargs)


# --- T012 [US2] `ergane --version` works from a clean install ------------------


def test_clean_install_version_reports_built_version(tmp_path: Path) -> None:
    """FR-008 / US2-S1: in a clean environment, `ergane --version` exits zero
    and prints the version the wheel was built with.

    The test version is deliberately not `0.1.0`, because `0.1.0` is the historical
    fallback literal and a test that asserts it would pass against a broken install
    that prints the fallback.
    """
    fixture = _InstallFixture(tmp_path, version=TEST_VERSION)
    result = fixture.run(["ergane", "--version"])
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert f"ergane {TEST_VERSION}" in result.stdout, (
        f"expected 'ergane {TEST_VERSION}' in output, got:\n{result.stdout}"
    )


# --- T013 [US2] persona registry resolves from inside the package --------------


def test_clean_install_registry_resolves_inside_package(tmp_path: Path) -> None:
    """FR-008 / US2-S2: in the same clean environment, a registry read succeeds
    and resolves to a path inside the installed package, not to a repository root.
    """
    fixture = _InstallFixture(tmp_path)

    probe = '''
import sys
from pathlib import Path
import factory.config as cfg

# Prove the fallback is not rescuing us: no personas.yaml above the install root.
root = Path(sys.argv[1]).resolve()
parent = root.parent
while parent != parent.parent:
    if (parent / "personas.yaml").exists():
        print(f"FALLBACK-AVAILABLE {parent / 'personas.yaml'}")
        raise SystemExit(2)
    parent = parent.parent

resolved = cfg.DEFAULT_REGISTRY_PATH
print(f"RESOLVED {resolved}")
if not str(resolved).startswith(str(root)):
    print(f"OUTSIDE-PACKAGE {resolved}")
    raise SystemExit(3)

personas = cfg.load_personas()
print(f"OK {len(personas)} personas")
'''
    result = fixture.run(
        ["python", "-c", probe, str(fixture.install_root)],
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert result.stdout.startswith("RESOLVED ")
    resolved_line = result.stdout.splitlines()[0]
    assert "personas.yaml" in resolved_line
    assert "OUTSIDE-PACKAGE" not in result.stdout


# --- T014 [P] [US2] distinct from the unrelated `ergane` distribution --------


def test_installs_alongside_unrelated_ergane_distribution(tmp_path: Path) -> None:
    """US2-S4: `ergane-cli` can be installed into an environment that already has
    an unrelated distribution named `ergane` because the two distribution names
    are distinct.

    The real unrelated distribution (`pjams/ergane` 0.7.3, an async web scraper) is
    not on the approved dependency roster and must not be fetched during tests,
    so we synthesize a minimal `ergane` distribution in the same temp environment
    and assert that installing our wheel succeeds alongside it.
    """
    fixture = _InstallFixture(tmp_path)

    # Build a minimal `ergane` distribution: no console script, just a module.
    fake_root = fixture.tmp_path / "fake-ergane"
    fake_root.mkdir()
    (fake_root / "ergane_shim.py").write_text("__version__ = '0.7.3'\n", encoding="utf-8")
    (fake_root / "pyproject.toml").write_text(
        '[project]\n'
        'name = "ergane"\n'
        'version = "0.7.3"\n'
        'requires-python = ">=3.11"\n'
        '[build-system]\n'
        'requires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n'
        '[tool.hatch.build.targets.wheel]\n'
        'packages = ["ergane_shim"]\n',
        encoding="utf-8",
    )
    subprocess.run(
        [shutil.which("uv"), "build", "--wheel", "--out-dir", "dist"],
        cwd=fake_root,
        check=True,
        capture_output=True,
        text=True,
    )
    fake_wheels = list((fake_root / "dist").glob("*.whl"))
    assert len(fake_wheels) == 1, f"expected one fake wheel, got {fake_wheels}"

    # Install the fake `ergane` wheel first.
    fixture.run([shutil.which("uv"), "pip", "install", str(fake_wheels[0])])

    # Re-install our wheel (it was already installed, but this asserts it still
    # succeeds when `ergane` is present). uv will treat the two as distinct.
    fixture.run([shutil.which("uv"), "pip", "install", str(fixture.wheel)])

    # Both distributions are importable via metadata.
    result = fixture.run(
        ["python", "-c", "from importlib.metadata import version; "
         "print('ergane', version('ergane')); "
         "print('ergane-cli', version('ergane-cli'))"],
    )
    assert "ergane 0.7.3" in result.stdout
    assert "ergane-cli" in result.stdout

    # Our console script still resolves to our package.
    version_result = fixture.run(["ergane", "--version"])
    assert version_result.returncode == 0
