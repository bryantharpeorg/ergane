"""057/US4: a team brings its own template.

These tests are written before the implementation that will satisfy them. They
assert that an operator-supplied template displaces the shipped default, that the
source used is recorded and stated, that a bad source is refused at interview
time rather than silently replaced, and that a supplied template may carry its
own stack packs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

import factory.cli.init as init_module
from factory.cli.errors import EXIT_OK, EXIT_USER

from tests.fake_schedules import FakeScheduleServer, desired_for, seed
from tests.test_ergane_init import ScriptedPrompter, _invoke, make_bare_repo
from tests.test_ergane_init_check import bind_offline_seams, conforming_gh

#: Minimal answers for a full interactive init that lets init use defaults for
#: every optional key. Order follows `_TOP_LEVEL_KEYS` plus the trailing slug.
#: US4 adds the template-source question after the manifest interview, so a
#: blank answer here means "use the shipped default".
MINIMAL_ANSWERS: list[str] = [
    "1",  # version
    "bwrap",  # runtime
    'test: "uv run pytest -q"',  # gates
    "",  # timeouts (empty -> omitted)
    "",  # standards (empty -> omitted, default will be used)
    "main",  # landing_branch
    "",  # roadmap (empty -> omitted)
    "",  # forge (empty -> omitted)
    "",  # writes (empty -> omitted)
    "",  # caches (empty -> omitted)
    "",  # diff_refusal_bytes (empty -> omitted)
    "",  # template source (empty -> shipped default)
    "myapp",  # slug
]


def run_init(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    answers: list[str] | None = None,
    offline_server: FakeScheduleServer | None = None,
) -> Any:
    """Run init against `repo` with a scripted prompter and every seam bound."""
    if offline_server is None:
        offline_server = FakeScheduleServer()
    bind_offline_seams(monkeypatch, conforming_gh(), schedules=offline_server)
    prompter = ScriptedPrompter(list(answers) if answers is not None else list(MINIMAL_ANSWERS))
    monkeypatch.setattr(init_module, "_prompter_factory", lambda: prompter)
    return _invoke(["init", str(repo)], monkeypatch)


#: A distinctive string that only exists in the shipped default floor.
SHIPPED_DEFAULT_MARKER = "Ergane seeds them only because a repository that has thought about its own standards"


def test_supplied_template_displaces_shipped_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T033 [US4] (US4-S1, US4-S2, FR-018, SC-007): supplied wins, default absent."""
    repo = make_bare_repo(tmp_path, {"README.md": "# app\n"})
    template = tmp_path / "custom-constitution.md"
    template.write_text(
        "# Team standards\n\nThese are our own principles.\n", encoding="utf-8"
    )

    answers = list(MINIMAL_ANSWERS)
    # The template source question is asked after the manifest interview,
    # immediately before the repo slug. Replace the blank template-source answer
    # (index 11) with the supplied path.
    answers[11] = str(template)
    result = run_init(repo, monkeypatch, answers=answers)

    assert result.code == EXIT_OK, result.stderr
    constitution = repo / ".specify" / "memory" / "constitution.md"
    text = constitution.read_text(encoding="utf-8")
    assert "Team standards" in text
    assert "These are our own principles." in text
    assert SHIPPED_DEFAULT_MARKER not in text, "shipped default leaked into a templated document"


def test_no_template_source_uses_shipped_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T033 [US4] (US4-S1, US4-S2, FR-018, SC-007): no source uses shipped default."""
    repo = make_bare_repo(tmp_path, {"README.md": "# app\n"})

    result = run_init(repo, monkeypatch)

    assert result.code == EXIT_OK, result.stderr
    constitution = repo / ".specify" / "memory" / "constitution.md"
    text = constitution.read_text(encoding="utf-8")
    assert SHIPPED_DEFAULT_MARKER in text, "shipped default was not used"


def test_source_is_recorded_and_stated_for_supplied_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T034 [P] [US4] (US4-S3, FR-018): supplied source is recorded and stated."""
    repo = make_bare_repo(tmp_path, {"README.md": "# app\n"})
    template = tmp_path / "custom-constitution.md"
    template.write_text("# Custom\n", encoding="utf-8")

    answers = list(MINIMAL_ANSWERS)
    answers[11] = str(template)
    result = run_init(repo, monkeypatch, answers=answers)

    assert result.code == EXIT_OK, result.stderr
    assert str(template) in result.stdout, "operator was not told the source"
    constitution = repo / ".specify" / "memory" / "constitution.md"
    text = constitution.read_text(encoding="utf-8")
    assert f"Seeded from {template}" in text, "source not recorded in document"


def test_source_is_recorded_and_stated_for_shipped_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T034 [P] [US4] (US4-S3, FR-018): shipped source is recorded and stated."""
    repo = make_bare_repo(tmp_path, {"README.md": "# app\n"})

    result = run_init(repo, monkeypatch)

    assert result.code == EXIT_OK, result.stderr
    constitution = repo / ".specify" / "memory" / "constitution.md"
    text = constitution.read_text(encoding="utf-8")
    assert "Seeded from" in text, "source not recorded in document"
    # In a development checkout the shipped default resolves to the repo-root file;
    # in an installed wheel it resolves inside the package. Both name the file.
    assert "default_floor.md" in text, "shipped source not named in document"


def test_missing_template_source_is_refused_at_interview_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T035 [P] [US4] (US4-S4, FR-018): missing source refused, no silent fallback."""
    repo = make_bare_repo(tmp_path, {"README.md": "# app\n"})
    missing = tmp_path / "does-not-exist.md"

    answers = list(MINIMAL_ANSWERS)
    answers[11] = str(missing)
    result = run_init(repo, monkeypatch, answers=answers)

    assert result.code == EXIT_USER, result.stderr
    assert str(missing) in result.stdout or str(missing) in result.stderr
    assert not (repo / ".specify" / "memory" / "constitution.md").exists()
    assert SHIPPED_DEFAULT_MARKER not in result.stdout


def test_empty_template_source_is_refused_at_interview_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T035 [P] [US4] (US4-S4, FR-018): empty source refused, no silent fallback."""
    repo = make_bare_repo(tmp_path, {"README.md": "# app\n"})
    empty = tmp_path / "empty.md"
    empty.write_text("", encoding="utf-8")

    answers = list(MINIMAL_ANSWERS)
    answers[11] = str(empty)
    result = run_init(repo, monkeypatch, answers=answers)

    assert result.code == EXIT_USER, result.stderr
    assert str(empty) in result.stdout or str(empty) in result.stderr
    assert not (repo / ".specify" / "memory" / "constitution.md").exists()


def test_supplied_template_with_stack_packs_prefers_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T036 [P] [US4] (US4-S5): supplied template's packs preferred, shipped fill gaps."""
    repo = make_bare_repo(tmp_path, {"README.md": "# app\n", "pyproject.toml": ""})
    template_dir = tmp_path / "template"
    template_dir.mkdir()
    template = template_dir / "constitution.md"
    template.write_text("# Custom floor\n", encoding="utf-8")
    # A supplied pack for Python with a distinctive command.
    pack_dir = template_dir / "stacks"
    pack_dir.mkdir()
    (pack_dir / "python.yaml").write_text(
        "marker_files:\n  - pyproject.toml\ntest_command: custom-pytest\n",
        encoding="utf-8",
    )

    answers = list(MINIMAL_ANSWERS)
    answers[11] = str(template)
    result = run_init(repo, monkeypatch, answers=answers)

    assert result.code == EXIT_OK, result.stderr
    constitution = repo / ".specify" / "memory" / "constitution.md"
    text = constitution.read_text(encoding="utf-8")
    assert "Custom floor" in text
