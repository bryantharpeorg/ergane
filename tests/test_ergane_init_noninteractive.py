"""Tests for `ergane init --non-interactive` (060 US2).

These tests exercise the second half of the spec: `init` can be driven without
a terminal, and a closed stdin is *not* consent without the explicit flag. The
interactive seam and the offline seams are reused from `tests.test_ergane_init`
and `tests.test_ergane_init_check`.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import Any, Callable

import pytest

import factory.cli.init as init_module
import factory.cli.main as main_module
from factory.cli.errors import EXIT_OK, EXIT_USER
from factory.verify.factory_yaml import MANIFEST_NAME, parse_factory_config

from tests.test_ergane_init import DEFAULT_ANSWERS, ScriptedPrompter, _invoke, make_bare_repo
from tests.test_ergane_init_check import bind_offline_seams


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bind every outward seam so a full init can complete without GitHub/Temporal."""
    bind_offline_seams(monkeypatch)


@pytest.fixture
def scripted_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[..., Any]:
    """Run `ergane init` with a scripted prompter, offline seams already bound."""

    def runner(*argv: str, answers: list[str]) -> Any:
        prompter = ScriptedPrompter(answers)
        monkeypatch.setattr(init_module, "_prompter_factory", lambda: prompter)
        bind_offline_seams(monkeypatch)
        return _invoke(list(argv), monkeypatch)

    return runner


# ---------------------------------------------------------------------------
# T013 [US2-S1] closed stdin without the flag is a refusal, not consent
# ---------------------------------------------------------------------------


def test_init_with_closed_stdin_and_no_flag_refuses_and_writes_no_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline: None
) -> None:
    """US2-S1: EOF is not consent; the first unanswerable question is named."""
    repo = make_bare_repo(tmp_path, {"README.md": "# app\n"})
    monkeypatch.chdir(repo)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    sys.stdin.close()

    result = _invoke(["init"], monkeypatch)

    assert result.code == EXIT_USER
    assert (repo / MANIFEST_NAME).exists() is False
    # The refusal names the unanswerable question rather than a generic EOF error.
    output = result.stdout + result.stderr
    assert "schema version" in output.lower()


# ---------------------------------------------------------------------------
# T014 [US2-S2] --non-interactive with closed stdin completes and reports defaults
# ---------------------------------------------------------------------------


def test_init_noninteractive_with_closed_stdin_completes_and_reports_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline: None
) -> None:
    """US2-S2: the flag is consent to documented defaults, and each is printed."""
    repo = make_bare_repo(tmp_path, {"README.md": "# app\n"})
    monkeypatch.chdir(repo)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    sys.stdin.close()

    result = _invoke(["init", "--non-interactive"], monkeypatch)

    assert result.code == EXIT_OK
    manifest = repo / MANIFEST_NAME
    assert manifest.exists()
    config = parse_factory_config(manifest.read_text(encoding="utf-8"))
    assert config.version == 1
    assert config.runtime == "bwrap"
    assert config.landing_branch == "main"

    # Every applied default is reported.
    assert "applied default: version" in result.stdout
    assert "applied default: runtime" in result.stdout
    assert "applied default: gates" in result.stdout
    assert "applied default: landing_branch" in result.stdout
    assert "applied default: template source" in result.stdout


# ---------------------------------------------------------------------------
# T015 [US2-S3] a field with no safe default is refused
# ---------------------------------------------------------------------------


def test_init_noninteractive_refuses_when_field_has_no_safe_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline: None
) -> None:
    """US2-S3: a required field the shared source cannot fill is named and nothing is written."""
    repo = make_bare_repo(tmp_path, {"README.md": "# app\n"})
    monkeypatch.chdir(repo)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    sys.stdin.close()

    original_build_defaults = init_module._build_defaults

    def _defaults_without_runtime(repo_root: Path) -> dict[str, Any]:
        defaults = original_build_defaults(repo_root)
        defaults.pop("runtime")
        return defaults

    monkeypatch.setattr(init_module, "_build_defaults", _defaults_without_runtime)

    result = _invoke(["init", "--non-interactive"], monkeypatch)

    assert result.code == EXIT_USER
    assert (repo / MANIFEST_NAME).exists() is False
    assert "runtime" in (result.stdout + result.stderr)


# ---------------------------------------------------------------------------
# T016 [US2-S4] an explicit value from an existing manifest beats the default
# ---------------------------------------------------------------------------


def test_init_noninteractive_keeps_explicit_existing_values_over_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline: None
) -> None:
    """US2-S4: an existing manifest's explicit gates and landing_branch win."""
    repo = make_bare_repo(tmp_path, {"README.md": "# app\n"})
    monkeypatch.chdir(repo)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    sys.stdin.close()

    # Seed an existing manifest with values that differ from the generated defaults.
    (repo / MANIFEST_NAME).write_text(
        "version: 1\n"
        "runtime: bwrap\n"
        "gates:\n"
        "  test: make check\n"
        "landing_branch: develop\n",
        encoding="utf-8",
    )

    result = _invoke(["init", "--non-interactive"], monkeypatch)

    assert result.code == EXIT_OK
    config = parse_factory_config((repo / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert config.gates == {"test": "make check"}
    assert config.landing_branch == "develop"


# ---------------------------------------------------------------------------
# T017 [US2-S5] interactive and non-interactive defaults agree field by field
# ---------------------------------------------------------------------------


def test_init_noninteractive_defaults_match_interactive_offered_defaults(
    scripted_offline: Callable[..., Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    offline: None,
) -> None:
    """US2-S5: both paths resolve defaults from one shared source.

    An interactive run that accepts every offered default should produce the same
    manifest as a `--non-interactive` run on an identical fresh repo.
    """
    repo = make_bare_repo(tmp_path, {"README.md": "# app\n"})
    monkeypatch.chdir(repo)

    # Interactive run: accept every default by answering empty strings.
    interactive = scripted_offline("init", answers=[""] * len(DEFAULT_ANSWERS))
    assert interactive.code == EXIT_OK
    interactive_config = parse_factory_config(
        (repo / MANIFEST_NAME).read_text(encoding="utf-8")
    )

    # Start a fresh identical repo for the non-interactive run.
    repo2 = tmp_path / "app2"
    repo2.mkdir()
    import subprocess

    completed = subprocess.run(
        ["git", "-C", str(repo2), "init", "-b", "main", "--quiet"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    (repo2 / "README.md").write_text("# app\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo2), "add", "-A"], check=False)
    subprocess.run(
        ["git", "-C", str(repo2), "commit", "--quiet", "-m", "initial commit"],
        check=False,
    )
    monkeypatch.chdir(repo2)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    sys.stdin.close()

    noninteractive = _invoke(["init", "--non-interactive"], monkeypatch)
    assert noninteractive.code == EXIT_OK
    noninteractive_config = parse_factory_config(
        (repo2 / MANIFEST_NAME).read_text(encoding="utf-8")
    )

    # Field-by-field agreement from the shared source.
    assert noninteractive_config.version == interactive_config.version
    assert noninteractive_config.runtime == interactive_config.runtime
    assert noninteractive_config.gates == interactive_config.gates
    assert noninteractive_config.landing_branch == interactive_config.landing_branch
    assert noninteractive_config.timeouts == interactive_config.timeouts
    assert noninteractive_config.standards == interactive_config.standards
    assert noninteractive_config.roadmap == interactive_config.roadmap
