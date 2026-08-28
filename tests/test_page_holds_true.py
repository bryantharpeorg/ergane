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
    assert_commands_not_dropped,
    extract_commands,
    parse_argv,
)

NEAR_MISS_PAGE = REPO_ROOT / "tests" / "fixtures" / "near_miss_page.md"
NON_ERGANE_PAGE = REPO_ROOT / "tests" / "fixtures" / "non_ergane_commands.md"
EDGE_CASE_PAGE = REPO_ROOT / "tests" / "fixtures" / "edge_case_commands.md"
GUARD_COUNT_BASELINE = REPO_ROOT / "tests" / "fixtures" / "guard_count_baseline.md"
GUARD_COUNT_PLUS_ONE = REPO_ROOT / "tests" / "fixtures" / "guard_count_plus_one.md"


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


def test_page_sweep_never_spawns_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    """Extracting and parsing every command on the swept pages never runs a subprocess."""
    import subprocess

    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fail_if_called(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))
        raise AssertionError("the page sweep must not spawn subprocesses")

    monkeypatch.setattr(subprocess, "run", fail_if_called)

    import tests.test_claude_md as tc
    import tests.test_readme as tr

    for text in (tr.TEXT, tc.TEXT):
        for argv in extract_commands(text):
            parse_argv(argv)

    assert not calls, "subprocess.run was called while sweeping the committed pages"


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


# --- US2 T007: near-miss detector raises on the shipped typo -----------------


def test_extract_commands_fails_on_nergane_repo_forget() -> None:
    """The exact near-miss that shipped in README.md on 2026-08-18 is named."""
    text = "Run `nergane repo forget` to remove a repository."
    with pytest.raises(UnrecognizedCommandError) as exc_info:
        extract_commands(text)
    message = str(exc_info.value)
    assert "nergane" in message, "the sweep should name the unrecognised word"
    assert "`nergane repo forget`" in message, (
        "the message should name the span as printed"
    )


# --- US2 T008: nonexistent verb fails naming the verb ------------------------


def test_extract_commands_fails_on_nonexistent_verb() -> None:
    """`ergane build landed` is command-shaped; the sweep fails naming the verb."""
    text = "Check `ergane build landed` to see which stories are in git."
    commands = extract_commands(text)
    assert ("ergane", "build", "landed") in commands, (
        "the extractor must not skip command-shaped text"
    )
    with pytest.raises(AssertionError) as exc_info:
        parse_argv(("ergane", "build", "landed"))
    message = str(exc_info.value)
    assert "landed" in message, "the failure must name the verb that does not exist"


# --- US2 T009: anti-vacuity guard counts, not samples --------------------------


def test_anti_vacuity_guard_counts_command_shaped_spans() -> None:
    """The guard returns a count derived from the same rule the extractor uses."""
    baseline_text = GUARD_COUNT_BASELINE.read_text(encoding="utf-8")
    plus_one_text = GUARD_COUNT_PLUS_ONE.read_text(encoding="utf-8")

    baseline_count = assert_commands_not_dropped(baseline_text)
    plus_one_count = assert_commands_not_dropped(plus_one_text)

    assert plus_one_count == baseline_count + 1, (
        f"adding one command-shaped span should increase the guard count by 1, "
        f"got {baseline_count} then {plus_one_count}"
    )


# --- US2 T010: not-a-command spans are ignored -------------------------------


@pytest.mark.parametrize(
    "span",
    [
        ".specify/memory/constitution.md",
        "llm.mode",
        "UPSTREAM_MODEL_API_KEY",
        "demo/implementer",
        "--default-branch",
    ],
    ids=["path", "config_key", "env_var", "model_alias", "bare_flag"],
)
def test_non_command_spans_are_ignored(span: str) -> None:
    """Spans that look like subjects other than commands do not fail the sweep."""
    text = f"See `{span}` for the value."
    commands = extract_commands(text)
    assert commands == [], f"`{span}` should not be treated as a command, got {commands}"
