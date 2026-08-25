"""US2: `ergane spec new` numbers, anchors and writes atomically.

Every test builds a throwaway git repository and a throwaway specs root so the
factory's real `spec new` verb can run without touching this repository.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable, NamedTuple

import pytest

from factory.cli.main import main
from factory.config import load_personas
from factory.workgraph.contention import _BARE_EXTENSIONS, _FILENAME_RE, named_files
from factory.workgraph.derive import DerivationError


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str

    @property
    def json(self) -> Any:
        return json.loads(self.stdout)


_FIXTURE_IDENTITY = ("Ergane Fixture", "fixture@ergane.invalid")
_FIXTURE_TIMESTAMP = "2026-01-01T00:00:00+00:00"


def _git_env(home: Path) -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(home),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": _FIXTURE_IDENTITY[0],
        "GIT_AUTHOR_EMAIL": _FIXTURE_IDENTITY[1],
        "GIT_AUTHOR_DATE": _FIXTURE_TIMESTAMP,
        "GIT_COMMITTER_NAME": _FIXTURE_IDENTITY[0],
        "GIT_COMMITTER_EMAIL": _FIXTURE_IDENTITY[1],
        "GIT_COMMITTER_DATE": _FIXTURE_TIMESTAMP,
        "GIT_TERMINAL_PROMPT": "0",
    }


def _git(repo: Path, *args: str, env: dict[str, str]) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    return completed.stdout


def _commit(repo: Path, subject: str, *, env: dict[str, str]) -> str:
    _git(repo, "commit", "--quiet", "-m", subject, env=env)
    return _git(repo, "rev-parse", "HEAD", env=env).strip()


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Callable[..., Run]:
    def invoke(*argv: str) -> Run:
        try:
            code = main(list(argv))
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
        captured = capsys.readouterr()
        return Run(code, captured.out, captured.err)

    return invoke


@pytest.fixture
def target_repo(tmp_path: Path) -> Path:
    """A tracked repository with one eligible file: src/calc.py (5 lines)."""
    home = tmp_path / "empty-home"
    home.mkdir()
    repo = tmp_path / "target-repo"
    repo.mkdir()
    env = _git_env(home)
    _git(repo, "init", "-b", "main", "--quiet", env=env)
    src = repo / "src"
    src.mkdir()
    (src / "calc.py").write_text(
        '"""The whole of the fixture repo\'s production code."""\n\n\n'
        "def add(left: int, right: int) -> int:\n"
        "    return left + right\n",
        encoding="utf-8",
    )
    _git(repo, "add", "-A", env=env)
    _commit(repo, "initial commit", env=env)
    return repo


@pytest.fixture
def empty_target_repo(tmp_path: Path) -> Path:
    """A tracked repository with no eligible file."""
    home = tmp_path / "empty-home"
    home.mkdir()
    repo = tmp_path / "empty-target-repo"
    repo.mkdir()
    env = _git_env(home)
    _git(repo, "init", "-b", "main", "--quiet", env=env)
    (repo / "README").write_text("no eligible extension", encoding="utf-8")
    _git(repo, "add", "-A", env=env)
    _commit(repo, "initial commit", env=env)
    return repo


# --- T010: numbering ---------------------------------------------------------


def test_spec_new_numbering_skips_gaps_and_refuses_collisions(
    run: Callable[..., Run], tmp_path: Path, target_repo: Path
) -> None:
    specs_root = tmp_path / "specs-root"
    specs_root.mkdir()
    (specs_root / "001-alpha").mkdir()
    (specs_root / "007-bravo").mkdir()
    (specs_root / "008-no-spec-md").mkdir()  # owns its number even without spec.md

    result = run(
        "spec",
        "new",
        "charlie",
        "--target-repo",
        str(target_repo),
        "--specs-root",
        str(specs_root),
    )

    assert result.code == 0
    assert (specs_root / "009-charlie").is_dir()
    assert (specs_root / "009-charlie" / "spec.md").is_file()


def test_spec_new_numbering_refuses_existing_slug_directory(
    run: Callable[..., Run], tmp_path: Path, target_repo: Path
) -> None:
    specs_root = tmp_path / "specs-root"
    specs_root.mkdir()
    (specs_root / "001-charlie").mkdir()

    result = run(
        "spec",
        "new",
        "charlie",
        "--target-repo",
        str(target_repo),
        "--specs-root",
        str(specs_root),
    )

    assert result.code == 1
    assert "001-charlie" in (result.stdout + result.stderr)


def test_spec_new_numbering_refuses_duplicate_numbers(
    run: Callable[..., Run], tmp_path: Path, target_repo: Path
) -> None:
    specs_root = tmp_path / "specs-root"
    specs_root.mkdir()
    (specs_root / "001-alpha").mkdir()
    (specs_root / "001-bravo").mkdir()

    result = run(
        "spec",
        "new",
        "charlie",
        "--target-repo",
        str(target_repo),
        "--specs-root",
        str(specs_root),
    )

    assert result.code == 1
    assert "001" in (result.stdout + result.stderr)


# --- T011: anchor resolution ---------------------------------------------------


def test_spec_new_anchor_resolves_and_round_trips_named_files(
    run: Callable[..., Run], tmp_path: Path, target_repo: Path
) -> None:
    specs_root = tmp_path / "specs-root"
    specs_root.mkdir()

    result = run(
        "spec",
        "new",
        "charlie",
        "--target-repo",
        str(target_repo),
        "--specs-root",
        str(specs_root),
    )

    assert result.code == 0
    spec_dir = specs_root / "001-charlie"
    tasks_text = (spec_dir / "tasks.md").read_text(encoding="utf-8")
    us1_slice = tasks_text.split("## Phase 2:")[0].split("## Phase 1:")[1]
    found = named_files(us1_slice)
    assert any("calc.py" in path for path in found)


def test_spec_new_anchor_refuses_repo_with_no_eligible_file(
    run: Callable[..., Run], tmp_path: Path, empty_target_repo: Path
) -> None:
    specs_root = tmp_path / "specs-root"
    specs_root.mkdir()

    result = run(
        "spec",
        "new",
        "charlie",
        "--target-repo",
        str(empty_target_repo),
        "--specs-root",
        str(specs_root),
    )

    assert result.code == 1
    assert "tracked file" in (result.stdout + result.stderr).lower()


# --- T012: atomic-or-nothing -------------------------------------------------


def test_spec_new_atomic_or_nothing_leaves_no_residue(
    run: Callable[..., Run],
    tmp_path: Path,
    target_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    specs_root = tmp_path / "specs-root"
    specs_root.mkdir()
    import factory.workgraph.derive as derive_module

    def _failing_derive(*args: Any, **kwargs: Any) -> Any:
        raise DerivationError(["forced self-proof failure"])

    monkeypatch.setattr(derive_module, "derive_workgraph", _failing_derive)

    result = run(
        "spec",
        "new",
        "charlie",
        "--target-repo",
        str(target_repo),
        "--specs-root",
        str(specs_root),
    )

    assert result.code == 1
    assert not any(entry.is_dir() for entry in specs_root.iterdir())
    assert not any(entry.name.startswith(".") for entry in specs_root.iterdir())


# --- T013: ending ------------------------------------------------------------


def test_spec_new_ending_prints_next_validate_command(
    run: Callable[..., Run], tmp_path: Path, target_repo: Path
) -> None:
    specs_root = tmp_path / "specs-root"
    specs_root.mkdir()

    result = run(
        "spec",
        "new",
        "charlie",
        "--target-repo",
        str(target_repo),
        "--specs-root",
        str(specs_root),
    )

    assert result.code == 0
    spec_dir = specs_root / "001-charlie"
    assert "next, run:" in result.stdout
    assert f"ergane spec validate {spec_dir} --target-repo {target_repo}" in result.stdout
    assert "ergane install" not in result.stdout


def test_spec_new_ending_names_install_when_registry_lacks_implementer(
    run: Callable[..., Run],
    tmp_path: Path,
    target_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    specs_root = tmp_path / "specs-root"
    specs_root.mkdir()

    def _empty_personas(path: Any = None) -> dict[str, Any]:
        return {}

    monkeypatch.setattr("factory.config.load_personas", _empty_personas)

    result = run(
        "spec",
        "new",
        "charlie",
        "--target-repo",
        str(target_repo),
        "--specs-root",
        str(specs_root),
    )

    assert result.code == 0
    assert "next, run:" in result.stdout
    assert "ergane install" in result.stdout


def test_spec_new_ending_names_install_when_registry_cannot_load(
    run: Callable[..., Run],
    tmp_path: Path,
    target_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    specs_root = tmp_path / "specs-root"
    specs_root.mkdir()
    from factory.config import ConfigError

    def _broken_personas(path: Any = None) -> dict[str, Any]:
        raise ConfigError("registry missing")

    monkeypatch.setattr("factory.config.load_personas", _broken_personas)

    result = run(
        "spec",
        "new",
        "charlie",
        "--target-repo",
        str(target_repo),
        "--specs-root",
        str(specs_root),
    )

    assert result.code == 0
    assert "next, run:" in result.stdout
    assert "ergane install" in result.stdout


# --- T014: --target-repo required and resolved with must_exist=True ----------


def test_spec_new_target_repo_is_required(run: Callable[..., Run], tmp_path: Path) -> None:
    specs_root = tmp_path / "specs-root"
    specs_root.mkdir()

    result = run("spec", "new", "charlie", "--specs-root", str(specs_root))

    assert result.code == 2


def test_spec_new_target_repo_must_exist(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    specs_root = tmp_path / "specs-root"
    specs_root.mkdir()
    missing = tmp_path / "no-such-repo"

    result = run(
        "spec",
        "new",
        "charlie",
        "--target-repo",
        str(missing),
        "--specs-root",
        str(specs_root),
    )

    assert result.code == 1
    assert str(missing.resolve()) in (result.stdout + result.stderr)


# --- T015: end to end ---------------------------------------------------------


def test_spec_new_end_to_end_validates_cleanly(
    run: Callable[..., Run], tmp_path: Path, target_repo: Path
) -> None:
    specs_root = tmp_path / "specs-root"
    specs_root.mkdir()

    result = run(
        "spec",
        "new",
        "charlie",
        "--target-repo",
        str(target_repo),
        "--specs-root",
        str(specs_root),
    )

    assert result.code == 0
    spec_dir = specs_root / "001-charlie"

    result = run(
        "spec",
        "validate",
        str(spec_dir),
        "--target-repo",
        str(target_repo),
        "--json",
    )

    assert result.code == 0
    assert result.json["findings"] == []
