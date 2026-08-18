"""`README.md` cannot be allowed to lie, so it is asserted rather than trusted.

This is the same three-claim sweep `tests/test_claude_md.py` runs on
`CLAUDE.md`, applied to the repository's front door. A new operator follows the
README before they have any other picture of Ergane, so every command it names
must resolve, every path it cites must exist, and it must not keep a second
copy of any figure that has a live source.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from factory.controlplane.config import _SECRET_PATTERNS
from tests.page_holds_true import (
    BIN_DIR,
    REPO_ROOT,
    extract_commands,
    extract_paths,
    run_help,
    split_argv,
    status_claims,
    verbs_of,
)

README_MD = REPO_ROOT / "README.md"

TEXT = README_MD.read_text(encoding="utf-8")
LINES = TEXT.splitlines()


# --- every command it names still exists ---------------------------------------


COMMANDS = extract_commands(TEXT)


@pytest.mark.parametrize("argv", COMMANDS, ids=lambda argv: " ".join(argv))
def test_every_command_the_file_names_resolves(argv: tuple[str, ...]) -> None:
    executable = BIN_DIR / argv[0]
    assert executable.exists(), (
        f"README.md tells the reader to run `{' '.join(argv)}`, but there is no "
        f"{argv[0]} entry point installed — check [project.scripts] in pyproject.toml"
    )

    positionals, flags = split_argv(argv)
    command = [str(executable)]
    result = run_help(command)
    assert result.returncode == 0, f"{argv[0]} --help does not parse:\n{result.stderr.strip()}"

    for word in positionals:
        verbs = verbs_of(result.stdout)
        if not verbs:
            break
        assert word in verbs, (
            f"README.md tells the reader to run `{' '.join(argv)}`, but "
            f"`{' '.join([argv[0], *positionals[: positionals.index(word)]])}` has no "
            f"`{word}` verb — it has {sorted(verbs)}"
        )
        command.append(word)
        result = run_help(command)
        assert result.returncode == 0, (
            f"`{' '.join(command)} --help` does not parse:\n{result.stderr.strip()}"
        )

    named = " ".join(Path(command[0]).name if part == command[0] else part for part in command)
    for flag, value in flags:
        assert flag in result.stdout, (
            f"README.md recommends `{' '.join(argv)}`, but `{flag}` is not in the help "
            f"for `{named}` — the option was renamed or removed"
        )
        if value is not None:
            assert value in result.stdout, (
                f"README.md recommends `{' '.join(argv)}`, but `{named}` no longer "
                f"accepts {value!r} for `{flag}`"
            )


def test_the_command_sweep_actually_read_the_file() -> None:
    # A parametrized sweep over an empty list passes without asserting anything,
    # which is how this file would go quiet if the backtick convention changed.
    flat = {" ".join(argv) for argv in COMMANDS}
    assert "ergane install" in flat, (
        f"the sweep found {sorted(flat)} — README.md is meant to start with "
        "`ergane install`, and the sweep is meant to find it"
    )
    assert "ergane init" in flat, (
        f"the sweep found {sorted(flat)} — README.md is meant to name "
        "`ergane init`, and the sweep is meant to find it"
    )


# --- every path it cites still exists -----------------------------------------


PATHS = extract_paths(TEXT)


@pytest.mark.parametrize("cited", PATHS, ids=lambda path: path)
def test_every_path_the_file_cites_exists(cited: str) -> None:
    if cited.startswith(".factory/"):
        pytest.skip(f"{cited} is runtime state, not a committed path")
    assert (REPO_ROOT / cited).exists(), (
        f"README.md points at {cited}, which is not in the tree — it moved, or it "
        "was never there"
    )


def test_the_path_sweep_actually_read_the_file() -> None:
    assert PATHS, "the path sweep found nothing — README.md is meant to cite files"


# --- it states no secret value ------------------------------------------------


def test_the_file_contains_no_secret_value() -> None:
    # The config parser already knows the two secret shapes it refuses. A page
    # that names an env-var is fine; a page that pastes the value is not.
    matches: list[tuple[int, str, str]] = []
    for number, line in enumerate(LINES, start=1):
        for pattern in _SECRET_PATTERNS:
            for match in pattern.finditer(line):
                matches.append((number, match.group(0), pattern.pattern))
    assert not matches, (
        "README.md contains a value that matches a shipped secret shape:\n"
        + "\n".join(f"  line {number}: {value!r} (pattern {pattern!r})" for number, value, pattern in matches)
    )


# --- it states no status a live source already answers -------------------------


def test_the_file_names_no_spec_status() -> None:
    claims = status_claims(TEXT)
    assert not claims, (
        "README.md states a spec's status, which has a live source and will rot:\n"
        + "\n".join(
            f"  line {number}: {spec!r} beside {status!r}" for number, spec, status in claims
        )
        + "\n\nAsk `ergane spec list specs` or `ergane build status` instead of "
        "recording the answer here."
    )


#: A spend figure: a literal dollar amount, which `ergane usage` already answers.
_SPEND_FIGURE = re.compile(r"\$\d")


def test_the_file_names_no_spend_figure() -> None:
    hits = [
        (number, line.strip())
        for number, line in enumerate(LINES, start=1)
        if _SPEND_FIGURE.search(line)
    ]
    assert not hits, (
        "README.md states a spend figure, which `ergane usage` already answers:\n"
        + "\n".join(f"  line {number}: {line}" for number, line in hits)
    )
