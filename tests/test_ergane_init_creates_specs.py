"""US2-S4: `ergane init` creates `specs/` on a fresh repository."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest

import factory.cli.init as init_module
import factory.cli.main as main_module
from factory.cli.errors import EXIT_OK

from tests.test_ergane_init import DEFAULT_ANSWERS, ScriptedPrompter, _invoke
from tests.test_ergane_init_check import bind_offline_seams


@pytest.fixture
def init(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Any]:
    """Run a full `ergane init` with scripted seams."""

    def runner(*argv: str, answers: list[str] | None = None) -> Any:
        prompter = ScriptedPrompter(list(answers or DEFAULT_ANSWERS))
        monkeypatch.setattr(init_module, "_prompter_factory", lambda: prompter)
        bind_offline_seams(monkeypatch)
        return _invoke(list(argv), monkeypatch)

    return runner


def _git(repo: Path, *args: str) -> str:
    import subprocess

    from tests.target_repo import git_env

    # `env=git_env()` is not optional. Without it this inherits the caller's
    # environment, and `git commit` needs an identity: the sandbox HOME carries a
    # seeded `.gitconfig` so it passes on this host, while a CI runner has none
    # and the commit exits 128. That is the split that killed 061's epic. The
    # helper exists precisely to "ignore whatever the host operator has
    # configured" (`tests/target_repo.py`), which is the same host-dependence
    # rule 067 applies to the sandbox mount set.
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=git_env(),
        check=True,
    ).stdout


def test_init_creates_specs_directory(init: Callable[..., Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """US2-S4 / FR-007: `ergane init` creates `specs/` alongside the runtime root."""
    repo = tmp_path / "app"
    repo.mkdir()
    _git(repo, "init", "-b", "main", "--quiet")
    (repo / "README.md").write_text("# app\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "initial commit")
    monkeypatch.chdir(repo)

    result = init("init", answers=list(DEFAULT_ANSWERS))

    assert result.code == EXIT_OK
    assert (repo / ".ergane").is_dir()
    assert (repo / "specs").is_dir()
    assert list((repo / "specs").iterdir()) == []
