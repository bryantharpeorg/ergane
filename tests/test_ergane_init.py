"""Tests for `ergane init` (US1).

The scaffold writes the repo's declarations and commits nothing. Every test
uses a fresh git repository under `tmp_path` and a scripted prompter so the
interview is deterministic and the output is reproducible.

Pasted evidence (plan trap 7):

T004 history-untouched transcript (captured from this test file):

    BEFORE git log:
    commit 38fa10b033 + 034: ready, re-refined against the tree 040 actually built
    Author: Ergane Factory <factory@ergane.invalid>
    Date:   ...

    BEFORE git status --porcelain:
    ?? .ergane/

    AFTER git log:
    commit 38fa10b033 + 034: ready, re-refined against the tree 040 actually built
    Author: Ergane Factory <factory@ergane.invalid>
    Date:   ...

    AFTER git status --porcelain:
    ?? .ergane/
    ?? tests/test_ergane_init.py

Note: the worktree under test already contains `.ergane/` (a factory runtime
root) and the new test file itself, so the status delta is only the test file.
The target repo created by `make_bare_repo` is independent and is the one whose
history is asserted byte-identical.

T005 re-run byte-identity transcript (captured from `test_init_rerun_changes_only_one_key`):

    First manifest (pretty-printed YAML):
    version: 1
    runtime: bwrap
    gates:
      test: uv run pytest -q
    landing_branch: main

    Second manifest after changing only standards:
    version: 1
    runtime: bwrap
    gates:
      test: uv run pytest -q
    standards: docs/STANDARDS.md
    landing_branch: main

    The diff touches exactly `standards`; `.gitignore` is unchanged.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pytest
import yaml

import factory.cli.init as init_module
import factory.cli.main as main_module
from factory.cli.errors import EXIT_OK, EXIT_USER
from factory.verify.factory_yaml import _SUPPORTED_VERSION, parse_factory_config

from tests.target_repo import add_worktree, git_env


@dataclass
class Run:
    """One captured CLI invocation."""

    code: int
    stdout: str
    stderr: str


def _invoke(argv: list[str], monkeypatch: pytest.MonkeyPatch | None = None) -> Run:
    """Run `main_module.main(argv)` and capture stdout/stderr via pytest."""
    old_stdout, old_stderr = sys.stdout, sys.stderr
    buf_out, buf_err = io.StringIO(), io.StringIO()
    try:
        sys.stdout, sys.stderr = buf_out, buf_err
        try:
            code = main_module.main(argv)
        except SystemExit as exit_request:
            code = 0 if exit_request.code is None else int(exit_request.code)
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
    return Run(code, buf_out.getvalue(), buf_err.getvalue())


# -----------------------------------------------------------------------------
# Scripted prompter seam
# -----------------------------------------------------------------------------


class ScriptedPrompter:
    """A prompter that returns answers from a list, in order.

    The init interview calls `ask` for each question and again if an answer
    fails validation. Provide enough answers for every prompt the test will
    see, including any re-ask cycles.
    """

    def __init__(self, answers: list[str]) -> None:
        self.answers = list(answers)
        self.calls: list[tuple[str, str | None]] = []

    def ask(self, prompt: str, *, default: str | None = None, error: str | None = None) -> str:
        self.calls.append((prompt, default))
        if not self.answers:
            raise AssertionError(f"prompter ran out of answers for: {prompt!r}")
        return self.answers.pop(0)


@pytest.fixture
def scripted(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Run]:
    """Factory that runs init with a scripted prompter and captures output.

    US4 made the check init's automatic last act (FR-010), so a completed init
    now reaches `gh` and 033's probes. Both seams are bound to scripted doubles:
    a unit test must never spawn real `gh`, nor deliver a real escalation.
    """

    def runner(*argv: str, answers: list[str]) -> Run:
        # Imported here, not at module scope: the check module imports this
        # one's helpers, and a module-level import either way would cycle.
        from tests.test_ergane_init_check import bind_offline_seams

        prompter = ScriptedPrompter(answers)
        monkeypatch.setattr(init_module, "_prompter_factory", lambda: prompter)
        bind_offline_seams(monkeypatch)
        return _invoke(list(argv), monkeypatch)

    return runner


# -----------------------------------------------------------------------------
# Git fixture helpers
# -----------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=git_env(),
        check=True,
    )
    return completed.stdout


def make_bare_repo(tmp_path: Path, files: dict[str, str] | None = None) -> Path:
    """Create a git repo with one commit containing `files`."""
    repo = tmp_path / "app"
    repo.mkdir()
    _git(repo, "init", "-b", "main", "--quiet")
    for name, content in (files or {}).items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "initial commit")
    return repo


# Default answers for the interview over the schema keys plus slug. Order
# follows `_TOP_LEVEL_KEYS`: version, runtime, gates, timeouts, standards,
# landing_branch, roadmap, forge, then slug.  A key added to the parser adds a
# question here, which is the point of deriving the interview from the parser
# (034/US6 added `roadmap`; 049/US5 added `forge`).
DEFAULT_ANSWERS: list[str] = [
    str(_SUPPORTED_VERSION),  # version
    "bwrap",  # runtime
    'test: "uv run pytest -q"',  # gates
    "",  # timeouts (empty -> omitted)
    "",  # standards (empty -> omitted)
    "main",  # landing_branch
    "",  # roadmap (empty -> omitted)
    "",  # forge (empty -> omitted, and absent means github)
    "myapp",  # slug
]


# -----------------------------------------------------------------------------
# T001 / T001a: refusals and bare invocation
# -----------------------------------------------------------------------------


def test_init_refuses_non_git_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """S5: a directory with no `.git` is refused, naming `git init`."""
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()

    result = _invoke(["init", str(not_a_repo)], monkeypatch)

    assert result.code == EXIT_USER
    assert "git init" in result.stderr.lower()
    assert (not_a_repo / "ergane.yaml").exists() is False


def test_init_refuses_linked_worktree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """S6: a linked git worktree is refused, naming the primary checkout."""
    primary = make_bare_repo(tmp_path, {"README.md": "# app\n"})
    worktree = tmp_path / "wt"
    add_worktree(primary, worktree)

    result = _invoke(["init", str(worktree)], monkeypatch)

    assert result.code == EXIT_USER
    assert "worktree" in result.stderr.lower()
    assert str(primary.resolve()) in result.stderr
    assert (worktree / "ergane.yaml").exists() is False


def test_bare_init_resolves_repo_root_and_matches_dot(
    scripted: Callable[..., Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S7: bare `ergane init` behaves exactly like `ergane init .` and names the root."""
    repo = make_bare_repo(tmp_path, {"src/main.py": "pass\n"})

    old_cwd = Path.cwd()
    try:
        monkeypatch.chdir(repo)
        result_bare = scripted("init", answers=list(DEFAULT_ANSWERS))
        result_dot = scripted("init", ".", answers=list(DEFAULT_ANSWERS))
    finally:
        monkeypatch.chdir(old_cwd)

    assert result_bare.code == EXIT_OK
    assert str(repo.resolve()) in result_bare.stdout
    assert (repo / "ergane.yaml").exists()

    assert result_dot.code == EXIT_OK
    assert str(repo.resolve()) in result_dot.stdout


# -----------------------------------------------------------------------------
# T002: scaffold case
# -----------------------------------------------------------------------------


def test_init_writes_scaffold_and_manifest_parses(
    scripted: Callable[..., Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S1: the written manifest parses and declares exactly the confirmed values."""
    repo = make_bare_repo(tmp_path, {"README.md": "# app\n"})
    monkeypatch.chdir(repo)

    result = scripted("init", answers=list(DEFAULT_ANSWERS))

    assert result.code == EXIT_OK
    manifest = repo / "ergane.yaml"
    assert manifest.exists()
    config = parse_factory_config(manifest.read_text(encoding="utf-8"), source=str(manifest))
    assert config.version == 1
    assert config.runtime == "bwrap"
    assert config.gates == {"test": "uv run pytest -q"}
    assert config.timeouts == {}
    assert config.standards is None
    assert config.landing_branch == "main"

    gitignore = repo / ".gitignore"
    assert gitignore.exists()
    assert any(".ergane/" in line for line in gitignore.read_text(encoding="utf-8").splitlines())

    ergane_root = repo / ".ergane"
    assert ergane_root.is_dir()
    assert list(ergane_root.iterdir()) == []


# -----------------------------------------------------------------------------
# T003: D-009 proposal case
# -----------------------------------------------------------------------------


def test_init_proposal_is_confirmed_and_leaves_no_trace(
    scripted: Callable[..., Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S2: a proposed gate default, when corrected, writes only the correction."""
    repo = make_bare_repo(
        tmp_path,
        {
            "README.md": "# app\n",
            "pyproject.toml": "[project]\nname = 'app'\n",
        },
    )
    monkeypatch.chdir(repo)

    # Operator accepts version, runtime, then *corrects* the proposed gate.
    answers = [
        str(_SUPPORTED_VERSION),
        "bwrap",
        'lint: "uv run ruff check ."',  # corrected from proposed test gate
        "",
        "",
        "main",
        "",
        "",
        "myapp",
    ]
    result = scripted("init", answers=answers)

    assert result.code == EXIT_OK
    config = parse_factory_config((repo / "ergane.yaml").read_text(encoding="utf-8"))
    assert config.gates == {"lint": "uv run ruff check ."}
    assert "test" not in config.gates
    # No trace of the proposal in the file.
    raw = (repo / "ergane.yaml").read_text(encoding="utf-8")
    assert "pyproject.toml" not in raw
    assert "proposal" not in raw.lower()


# -----------------------------------------------------------------------------
# T004: history untouched
# -----------------------------------------------------------------------------


def test_init_leaves_git_history_and_status_unchanged(
    scripted: Callable[..., Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S3: `git log` is byte-identical and status shows exactly the declared paths."""
    repo = make_bare_repo(tmp_path, {"README.md": "# app\n"})
    monkeypatch.chdir(repo)

    log_before = _git(repo, "log", "--format=%H %s")
    status_before = _git(repo, "status", "--porcelain")

    result = scripted("init", answers=list(DEFAULT_ANSWERS))

    assert result.code == EXIT_OK
    log_after = _git(repo, "log", "--format=%H %s")
    status_after = _git(repo, "status", "--porcelain")

    assert log_before == log_after
    assert status_before == ""
    status_lines = [line for line in status_after.splitlines() if line.strip()]
    paths = {line.split()[-1] for line in status_lines}
    assert paths == {".gitignore", "ergane.yaml"}
    assert (repo / ".ergane").is_dir()
    assert list((repo / ".ergane").iterdir()) == []


# -----------------------------------------------------------------------------
# T005: re-run case
# -----------------------------------------------------------------------------


def test_init_rerun_changes_only_one_key(
    scripted: Callable[..., Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S4: changing only standards on re-run touches exactly that key."""
    repo = make_bare_repo(tmp_path, {"README.md": "# app\n"})
    monkeypatch.chdir(repo)

    first = scripted("init", answers=list(DEFAULT_ANSWERS))
    assert first.code == EXIT_OK
    manifest_before = (repo / "ergane.yaml").read_bytes()
    gitignore_before = (repo / ".gitignore").read_bytes()

    # Re-run changing only the standards answer.
    answers = list(DEFAULT_ANSWERS)
    answers[4] = "docs/STANDARDS.md"
    second = scripted("init", answers=answers)
    assert second.code == EXIT_OK

    manifest_after = (repo / "ergane.yaml").read_bytes()
    gitignore_after = (repo / ".gitignore").read_bytes()

    assert gitignore_before == gitignore_after
    assert manifest_before != manifest_after

    before_doc = yaml.safe_load(manifest_before)
    after_doc = yaml.safe_load(manifest_after)
    assert "standards" not in before_doc
    assert after_doc["standards"] == "docs/STANDARDS.md"
    before_doc.pop("standards", None)
    after_doc.pop("standards", None)
    assert before_doc == after_doc


def test_init_rerun_unchanged_is_byte_identical(
    scripted: Callable[..., Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-005: an unchanged interview yields a byte-identical manifest."""
    repo = make_bare_repo(tmp_path, {"README.md": "# app\n"})
    monkeypatch.chdir(repo)

    first = scripted("init", answers=list(DEFAULT_ANSWERS))
    assert first.code == EXIT_OK
    manifest_before = (repo / "ergane.yaml").read_bytes()

    second = scripted("init", answers=list(DEFAULT_ANSWERS))
    assert second.code == EXIT_OK
    manifest_after = (repo / "ergane.yaml").read_bytes()

    assert manifest_before == manifest_after


# -----------------------------------------------------------------------------
# Offered defaults: what the operator actually reads
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        1,
        "main",
        "bwrap",
        "docs/STANDARDS.md",
        {"test": "uv run pytest -q"},
        {"test": 900},
    ],
)
def test_offered_defaults_round_trip_and_scalars_stay_on_one_line(value: Any) -> None:
    """`_yaml_repr` renders a default the operator can read *and* re-submit.

    `yaml.safe_dump` closes a scalar document with an explicit `...` end marker,
    which collections never get. That marker was reaching the terminal inside
    the bracketed default, so the first two questions of `ergane init` read

        schema version [1
        ...]:
        landing branch [main
        ...]:

    The round-trip half of this assertion is the guard on the fix: pressing
    Enter feeds the offered text straight back through `yaml.safe_load`, so a
    default that is merely *prettier* is not enough — it has to still load to
    the value it was rendered from.
    """
    text = init_module._yaml_repr(value)
    assert yaml.safe_load(text) == value
    if not isinstance(value, (dict, list)):
        assert "\n" not in text, f"scalar default rendered across lines: {text!r}"


def test_the_interview_offers_no_multi_line_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end: no question in a default `ergane init` shows a wrapped default."""
    repo = make_bare_repo(tmp_path, {"README.md": "# app\n"})
    monkeypatch.chdir(repo)

    prompter = ScriptedPrompter(list(DEFAULT_ANSWERS))
    monkeypatch.setattr(init_module, "_prompter_factory", lambda: prompter)
    result = _invoke(["init"], monkeypatch)

    assert result.code == EXIT_OK
    wrapped = [
        (prompt, default)
        for prompt, default in prompter.calls
        if default is not None and "\n" in default
    ]
    assert wrapped == [], f"multi-line defaults offered to the operator: {wrapped}"
    # The two the operator meets first, spelled out.
    assert ("schema version", "1") in prompter.calls
    assert ("landing branch", "main") in prompter.calls
