"""Tests for the shared page-sweep helper itself.

The page suites in `test_readme.py` and `test_claude_md.py` prove that the
committed pages are clean. This file proves that the shared helper would fail
on a deliberately bad page, so the guard cannot be quietly removed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.page_holds_true import (
    BIN_DIR,
    REPO_ROOT,
    UnrecognizedCommandError,
    extract_commands,
    parse_argv,
)

NEAR_MISS_PAGE = REPO_ROOT / "tests" / "fixtures" / "near_miss_page.md"
NON_ERGANE_PAGE = REPO_ROOT / "tests" / "fixtures" / "non_ergane_commands.md"
EDGE_CASE_PAGE = REPO_ROOT / "tests" / "fixtures" / "edge_case_commands.md"


# --- T001: the detector fires on a near-miss ---------------------------------


def test_extract_commands_fails_on_near_miss_command() -> None:
    """A misspelled root command is named, not skipped."""
    text = NEAR_MISS_PAGE.read_text(encoding="utf-8")
    with pytest.raises(UnrecognizedCommandError) as exc_info:
        extract_commands(text)
    assert "nergane" in str(exc_info.value), (
        "the sweep should name the unrecognised word, not swallow it"
    )


# --- T002: legitimate non-Ergane commands are not flagged --------------------


def test_extract_commands_passes_on_non_ergane_commands() -> None:
    """`git clone`, `uv venv`, `gh auth login` and friends are not typos."""
    text = NON_ERGANE_PAGE.read_text(encoding="utf-8")
    commands = extract_commands(text)
    assert commands == [], (
        "legitimate non-Ergane commands must not be flagged as near-misses"
    )


# --- T003: both page suites exercise the same shared code path ---------------


def test_both_page_suites_use_the_same_extract_commands() -> None:
    """The two page suites must not grow separate extractors (054 trap 3)."""
    import tests.test_claude_md as tc
    import tests.test_readme as tr

    assert tr.extract_commands is tc.extract_commands is extract_commands, (
        "the README and CLAUDE.md suites must share the same extractor"
    )


# --- T004: the committed pages are clean under the fixed sweep ---------------


def test_readme_and_claude_md_have_no_near_misses() -> None:
    """Both real pages already pass; this only proves no false positives."""
    import tests.test_claude_md as tc
    import tests.test_readme as tr

    for text in (tr.TEXT, tc.TEXT):
        # If this raises, the page contains a near-miss the detector caught.
        extract_commands(text)


# --- US1 T001: parse check rejects a missing required argument ---------------


def test_parse_argv_rejects_missing_required_argument() -> None:
    """`ergane usage` without --by fails, naming the missing argument."""
    with pytest.raises(AssertionError) as exc_info:
        parse_argv(("ergane", "usage"))
    assert "--by" in str(exc_info.value), (
        "the parse failure must name the missing `--by` argument"
    )


# --- US1 T002: parse check accepts the corrected form -----------------------


def test_parse_argv_accepts_usage_by_epic() -> None:
    """`ergane usage --by epic` parses cleanly."""
    parse_argv(("ergane", "usage", "--by", "epic"))


# --- US1 T003: placeholder substitution by shape ------------------------------


def test_parse_argv_substitutes_path_placeholder() -> None:
    """A path-shaped placeholder is replaced and the command parses."""
    # README.md and docs/onramp.html both print `ergane repo onboard <target-repo-path>`.
    parse_argv(("ergane", "repo", "onboard", "<target-repo-path>"))


def test_parse_argv_substitutes_spec_dir_placeholder() -> None:
    """The spec-dir placeholder is replaced and the command parses."""
    # README.md and CLAUDE.md both print `ergane spec landed <spec-dir>`.
    parse_argv(("ergane", "spec", "landed", "<spec-dir>"))


def test_parse_argv_substitutes_epic_id_placeholder() -> None:
    """An id-shaped placeholder is replaced and the command parses."""
    # README.md and CLAUDE.md both print `ergane build status <epic-id>`.
    parse_argv(("ergane", "build", "status", "<epic-id>"))


def test_parse_argv_substitutes_repo_slug_placeholder() -> None:
    """A slug-shaped placeholder is replaced and the command parses."""
    # README.md prints `ergane repo forget <repo-slug>`.
    parse_argv(("ergane", "repo", "forget", "<repo-slug>"))


# --- US1 T004: parse check never spawns a subprocess ------------------------


def test_parse_argv_never_spawns_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    """The parse check drives argparse directly and never calls a verb."""
    import subprocess

    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fail_if_called(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))
        raise AssertionError("parse_argv must not spawn subprocesses")

    monkeypatch.setattr(subprocess, "run", fail_if_called)

    parse_argv(("ergane", "build", "start", "<workgraph.json>"))
    parse_argv(("ergane", "repo", "forget", "<repo-slug>"))
    parse_argv(("ergane", "uninstall"))
    parse_argv(("ergane", "usage", "--by", "epic"))

    assert not calls, "subprocess.run was called during parse_argv"


# --- T005: pipelines and correctly-spelled nonexistent commands --------------


def test_edge_cases_do_not_mask_real_failures() -> None:
    """Pipelines are not Ergane commands, and a real typo still reaches --help."""
    text = EDGE_CASE_PAGE.read_text(encoding="utf-8")
    commands = extract_commands(text)
    # `cat file | grep thing` is a pipeline; it must not trip the detector.
    assert ("cat", "file", "|", "grep", "thing") not in commands
    # `ergane nonexistent` is correctly spelled as a root command, so the
    # near-miss detector lets it through and the parse check fails.
    assert ("ergane", "nonexistent") in commands
    executable = BIN_DIR / "ergane"
    assert executable.exists(), "the ergane console script must be installed"
    with pytest.raises(AssertionError):
        parse_argv(("ergane", "nonexistent"))
