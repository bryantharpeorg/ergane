"""057/US1: a repository with no standards document gets one.

These tests are written before the implementation that will satisfy them, so they
are expected to fail on a clean tree. They assert the boundary between "a file
exists" and "init may overwrite": existence, not content, is the guard (plan
trap 4). They also assert that `ergane init --check` reports a missing document
as a readiness finding and writes nothing, and that `forget` leaves a seeded
standards document in place.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest
import yaml

import factory.cli.init as init_module
import factory.cli.main as main_module
import factory.cli.repo as repo_module
from factory import registry
from factory.cli.errors import EXIT_OK, EXIT_USER

from tests.fake_schedules import FakeScheduleServer, desired_for, seed
from tests.test_ergane_init import ScriptedPrompter, _git, _invoke, make_bare_repo
from tests.test_ergane_init_check import bind_offline_seams, conforming_gh

#: Minimal answers for a full interactive init that lets init use defaults for
#: every optional key. Order follows `_TOP_LEVEL_KEYS` plus the trailing slug.
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
    "myapp",  # slug
]


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch) -> FakeScheduleServer:
    """Bind every outward seam; return the fake schedule server for inspection."""
    control_plane = FakeScheduleServer()
    bind_offline_seams(monkeypatch, conforming_gh(), schedules=control_plane)
    return control_plane


def run_init(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    answers: list[str] | None = None,
    argv: list[str] | None = None,
    offline_server: FakeScheduleServer | None = None,
) -> Any:
    """Run init against `repo` with a scripted prompter and every seam bound."""
    if offline_server is None:
        offline_server = FakeScheduleServer()
    bind_offline_seams(monkeypatch, conforming_gh(), schedules=offline_server)
    prompter = ScriptedPrompter(list(answers) if answers is not None else list(MINIMAL_ANSWERS))
    monkeypatch.setattr(init_module, "_prompter_factory", lambda: prompter)
    return _invoke(list(argv) if argv is not None else ["init", str(repo)], monkeypatch)


def test_init_leaves_an_existing_standards_document_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline: FakeScheduleServer
) -> None:
    """US1-S3/FR-002: an existing file is returned unchanged, byte for byte."""
    constitution = "# Project constitution\n\nThis is the user's own text.\n"
    repo = make_bare_repo(
        tmp_path,
        {
            "README.md": "# app\n",
            "ergane.yaml": """\
version: 1
runtime: bwrap
gates:
  test: "uv run pytest -q"
standards: docs/STANDARDS.md
landing_branch: main
""",
            "docs/STANDARDS.md": constitution,
        },
    )

    before = (repo / "docs/STANDARDS.md").read_bytes()
    result = run_init(repo, monkeypatch, offline_server=offline)
    after = (repo / "docs/STANDARDS.md").read_bytes()

    assert result.code == EXIT_OK, result.stderr
    assert before == after, "init changed an existing standards document"
    assert "exists" in result.stdout.lower() or "kept" in result.stdout.lower()


def test_init_leaves_an_empty_standards_file_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline: FakeScheduleServer
) -> None:
    """Edge case: an empty file exists, so it is the repository's choice."""
    repo = make_bare_repo(
        tmp_path,
        {
            "README.md": "# app\n",
            "ergane.yaml": """\
version: 1
runtime: bwrap
gates:
  test: "uv run pytest -q"
standards: docs/STANDARDS.md
landing_branch: main
""",
            "docs/STANDARDS.md": "",
        },
    )

    before = (repo / "docs/STANDARDS.md").read_bytes()
    result = run_init(repo, monkeypatch, offline_server=offline)
    after = (repo / "docs/STANDARDS.md").read_bytes()

    assert result.code == EXIT_OK, result.stderr
    assert before == after, "init filled an empty standards file"


def test_init_writes_a_constitution_when_none_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline: FakeScheduleServer
) -> None:
    """US1-S1/FR-001/FR-003: a repo with no standards document gets one."""
    repo = make_bare_repo(tmp_path, {"README.md": "# app\n"})

    result = run_init(repo, monkeypatch, offline_server=offline)

    assert result.code == EXIT_OK, result.stderr
    manifest = repo / "ergane.yaml"
    assert manifest.exists()
    config = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    assert config["standards"] == ".specify/memory/constitution.md"
    constitution = repo / ".specify" / "memory" / "constitution.md"
    assert constitution.exists(), "constitution was not written at the default path"
    text = constitution.read_text(encoding="utf-8")
    assert text, "constitution is empty"


def test_init_default_standards_path_is_used_when_no_answer_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline: FakeScheduleServer
) -> None:
    """US1-S2/FR-003: empty answer keeps a default, not omission."""
    repo = make_bare_repo(tmp_path, {"README.md": "# app\n"})

    result = run_init(repo, monkeypatch, answers=list(MINIMAL_ANSWERS), offline_server=offline)

    assert result.code == EXIT_OK, result.stderr
    manifest = repo / "ergane.yaml"
    document = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    assert document["standards"] == ".specify/memory/constitution.md"
    constitution = repo / ".specify" / "memory" / "constitution.md"
    assert constitution.exists()
    assert constitution.parent.is_dir()


def test_init_check_reports_missing_standards_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline: FakeScheduleServer
) -> None:
    """US1-S5/FR-013: `--check` names the absence and creates no file or directory."""
    repo = make_bare_repo(
        tmp_path,
        {
            "README.md": "# app\n",
            "ergane.yaml": """\
version: 1
runtime: bwrap
gates:
  test: "uv run pytest -q"
landing_branch: main
""",
        },
    )
    registry.register("myapp", repo)
    seed(offline, desired_for(repo, slug="myapp"))

    result = _invoke(["init", "--check", str(repo)], monkeypatch)

    assert result.code == EXIT_USER
    assert "standards" in result.stdout.lower()
    assert not (repo / ".specify").exists()
    assert not any(p for p in repo.iterdir() if p.name.startswith(".specify"))


def test_forget_leaves_seeded_constitution_and_removes_ergane_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline: FakeScheduleServer
) -> None:
    """FR-015: `forget` leaves the user's standards document in place."""
    repo = make_bare_repo(tmp_path, {"README.md": "# app\n"})
    result = run_init(repo, monkeypatch, offline_server=offline)
    assert result.code == EXIT_OK, result.stderr

    constitution = repo / ".specify" / "memory" / "constitution.md"
    assert constitution.exists()
    constitution_bytes = constitution.read_bytes()
    manifest = repo / "ergane.yaml"
    manifest_bytes = manifest.read_bytes()
    gitignore = repo / ".gitignore"
    gitignore_bytes = gitignore.read_bytes()

    async def no_epics() -> set[str]:
        return set()

    monkeypatch.setattr(repo_module, "_running_epic_ids", no_epics)
    # The test session sets ERGANE_ROOT/FACTORY_ROOT to a shared directory that
    # disagrees with the repo's entry-derived root; drop the override so
    # `--clean-runtime` is allowed to empty this temporary repo's root.
    monkeypatch.delenv("ERGANE_ROOT", raising=False)
    monkeypatch.delenv("FACTORY_ROOT", raising=False)
    forget_result = _invoke(["repo", "forget", "myapp", "--clean-runtime"], monkeypatch)

    assert forget_result.code == EXIT_OK, forget_result.stderr
    assert constitution.read_bytes() == constitution_bytes, "forget removed the seeded constitution"
    assert manifest.read_bytes() == manifest_bytes, "forget changed the manifest"
    assert gitignore.read_bytes() == gitignore_bytes, "forget changed .gitignore"
    assert not (repo / ".ergane").exists() or list((repo / ".ergane").iterdir()) == []
