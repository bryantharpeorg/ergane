"""US2: a new spec can name its finding when it is created.

Every test builds a throwaway git repository and a throwaway specs root so the
factory's real `spec new` verb can run without touching this repository.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Callable, NamedTuple

import pytest

from factory.cli.main import main


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str


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


def _scaffold_frontmatter(run: Callable[..., Run], tmp_path: Path, target_repo: Path, slug: str, *extra_argv: str) -> str:
    """Run `ergane spec new <slug> <extra_argv>` and return the frontmatter block."""
    specs_root = tmp_path / "specs-root"
    specs_root.mkdir()

    result = run(
        "spec",
        "new",
        slug,
        "--target-repo",
        str(target_repo),
        "--specs-root",
        str(specs_root),
        *extra_argv,
    )

    assert result.code == 0, (result.stdout, result.stderr)
    spec_path = specs_root / f"001-{slug}" / "spec.md"
    text = spec_path.read_text(encoding="utf-8")
    fence_start = text.index("---")
    fence_end = text.index("---", fence_start + 3)
    return text[fence_start : fence_end + 3]


# --- T010 [P] [US2] (spec US2-S1): single --fixes key --------------------------


def test_spec_new_fixes_single_key(run: Callable[..., Run], tmp_path: Path, target_repo: Path) -> None:
    """`ergane spec new <slug> --fixes a/one` declares the finding in frontmatter."""
    frontmatter = _scaffold_frontmatter(run, tmp_path, target_repo, "charlie", "--fixes", "a/one")

    assert "fixes:" in frontmatter
    assert frontmatter.split("fixes:")[1].split("---")[0].strip() == "- a/one"


# --- T011 [P] [US2] (spec US2-S2): two --fixes keys in order -------------------


def test_spec_new_fixes_two_keys_in_order(run: Callable[..., Run], tmp_path: Path, target_repo: Path) -> None:
    """Two --fixes occurrences produce both keys in the order given."""
    frontmatter = _scaffold_frontmatter(
        run, tmp_path, target_repo, "charlie", "--fixes", "a/one", "--fixes", "b/two"
    )

    fixes_block = frontmatter.split("fixes:")[1].split("---")[0].strip()
    assert fixes_block == "- a/one\n  - b/two"


# --- T012 [P] [US2] (spec US2-S3): no --fixes keeps the current frontmatter ----


def test_spec_new_no_fixes_preserves_frontmatter(run: Callable[..., Run], tmp_path: Path, target_repo: Path) -> None:
    """Without --fixes the scaffolded frontmatter is byte-identical to today's output."""
    frontmatter = _scaffold_frontmatter(run, tmp_path, target_repo, "charlie")

    expected = "---\nstate: draft\n---"
    assert frontmatter == expected
