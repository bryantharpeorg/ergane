"""What breaks when Ergane is installed from a wheel rather than run from git.

Every test in this repository until now ran from a checkout, where the repo root
sits one directory above `factory/` and holds `personas.yaml`. That is exactly
the configuration in which the packaging defect could not be seen: an installed
wheel has `site-packages/` there instead, and nothing ever put a registry in it.
`ergane install` on a fresh host therefore ended with

    [FAIL] llm: probe failed unexpectedly: ConfigError: cannot read persona
    registry .../site-packages/personas.yaml: [Errno 2] No such file or directory

while `tests/test_config.py` — which reads `REPO_ROOT / "personas.yaml"` — stayed
green throughout. A test anchored on the repo root is the one test that cannot
fail here, so these are anchored on the *package* instead.

Two things have to hold, and they are tested separately because they fail
separately:

1. **Resolution.** `factory.config` must find the registry with nothing but the
   package directory — no repo root above it, no useful cwd.
   `test_registry_resolves_from_package_data_alone` builds that layout on disk
   and imports into it in a subprocess.
2. **Packaging.** The wheel build must actually put a registry in the package
   directory for (1) to find. `test_wheel_build_ships_the_registry_inside_the_package`
   asserts the build configuration that does it.

Why not build a wheel in the suite: it needs `hatchling`, which is not a
dependency of this project's test environment, and fetching it would put a
network round trip inside a four-minute gate. The build was instead verified by
hand against a real wheel; the before/after transcript is in the commit that
introduced this file. What the suite pins is the two halves that a future edit
could plausibly break — a `pyproject.toml` reformat dropping the force-include,
and someone "simplifying" the resolver back to a `__file__` walk.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FACTORY_DIR = REPO_ROOT / "factory"
REGISTRY = REPO_ROOT / "personas.yaml"

#: Run inside the synthetic install. It proves *which* `factory` it imported
#: before it proves anything else: if the real checkout leaked onto `sys.path`,
#: `parents[1]` would be the repo root, the registry would be found for the
#: wrong reason, and this test would pass with the bug live.
_PROBE = """
import sys
import factory.config as cfg

expected_pkg = sys.argv[1]
actual_pkg = str(__import__("pathlib").Path(cfg.__file__).resolve().parent)
if actual_pkg != expected_pkg:
    print(f"WRONG-PACKAGE {actual_pkg}")
    raise SystemExit(2)

try:
    registry = cfg.load_personas()
except cfg.ConfigError as error:
    print(f"CONFIG-ERROR {error}")
    raise SystemExit(3)

print(f"OK {len(registry)} personas from {cfg.DEFAULT_REGISTRY_PATH}")
"""


def _installed_layout(root: Path, *, with_registry: bool) -> Path:
    """Build `<root>/site-packages/factory/` the way a wheel install does.

    Only the modules `factory.config` actually needs are copied — it imports
    nothing from its own package — so this stays a file copy rather than a
    build. The point of the layout is what it *omits*: there is no
    `site-packages/personas.yaml`, because no wheel has ever installed one.
    """
    site = root / "site-packages"
    package = site / "factory"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    shutil.copy(FACTORY_DIR / "config.py", package / "config.py")
    if with_registry:
        # What `[tool.hatch.build.targets.wheel.force-include]` does at build time.
        shutil.copy(REGISTRY, package / "personas.yaml")
    assert not (site / "personas.yaml").exists()
    return site


def _run_probe(site: Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    package = site / "factory"
    return subprocess.run(
        [sys.executable, "-c", _PROBE, str(package)],
        cwd=cwd,
        env={
            "PYTHONPATH": str(site),
            "PATH": "/usr/bin:/bin",
            "HOME": str(cwd),
        },
        capture_output=True,
        text=True,
        check=False,
    )


def test_registry_resolves_from_package_data_alone(tmp_path: Path) -> None:
    """The registry is found with only the package on disk — no repo above it.

    The positive case and its own control run in one test on purpose: the
    control (same layout, registry left out of the package) is the evidence
    that the assertion is reading the packaged file rather than passing for
    some ambient reason. If resolution silently fell back to a checkout, both
    halves would pass and the control would catch it.
    """
    installed = _installed_layout(tmp_path / "with", with_registry=True)
    result = _run_probe(installed, tmp_path / "with")
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert result.stdout.startswith("OK "), result.stdout
    # Resolved to the copy inside the package, not to anything above it.
    assert str(installed / "factory" / "personas.yaml") in result.stdout

    # Control: identical layout, registry not packaged. This is the tree as it
    # stood before this commit, and it must still fail — loudly and by name.
    bare = _installed_layout(tmp_path / "without", with_registry=False)
    control = _run_probe(bare, tmp_path / "without")
    assert control.returncode == 3, f"stdout={control.stdout!r} stderr={control.stderr!r}"
    assert "cannot read persona registry" in control.stdout


def test_wheel_build_ships_the_registry_inside_the_package() -> None:
    """Packaging puts `personas.yaml` where the resolver looks for it.

    Resolution and packaging are one fix in two files. This half is what was
    missing outright: `pyproject.toml` declared no build data at all, so the
    wheel's only non-Python entries were three stray `.py.base` files.
    """
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    wheel = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]

    force_include = wheel.get("force-include", {})
    assert force_include.get("personas.yaml") == "factory/personas.yaml", (
        "the wheel must carry the persona registry inside `factory/`; without it "
        "an installed Ergane resolves no persona and cannot dispatch"
    )
    # The source it copies from has to exist for the build to copy it.
    assert REGISTRY.is_file()


def test_no_build_residue_is_left_in_the_package() -> None:
    """No `.py.base` files in the tree, and the wheel excludes them anyway.

    Three of them were committed by 011/us1 (ed8f24c) and nothing reads them.
    They are deleted here; the exclude pattern is the guard against the next
    ones, which would otherwise ship to every user.
    """
    strays = sorted(p.relative_to(REPO_ROOT) for p in FACTORY_DIR.rglob("*.py.base"))
    assert strays == [], f"build residue committed into the package: {strays}"

    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    wheel = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]
    assert "**/*.py.base" in wheel.get("exclude", [])
