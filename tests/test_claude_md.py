"""`CLAUDE.md` cannot be allowed to lie, so it is asserted rather than trusted.

An orientation file is the worst kind of documentation to let rot, because it is
read by an agent that has no other picture of the repository yet and therefore no
way to notice that what it just read stopped being true. A stale sentence in
`docs/architecture.md` gets caught by the next person who knows better; a stale
command in `CLAUDE.md` gets *acted on*, and the discovery arrives hours later as a
burned attempt.

So the three claims the file makes about the world are checked against the world:

- **Every command it names still exists.** Each backticked `factory-*` invocation
  is run for real, with `--help`, through the installed console script — the exact
  thing it tells a reader to type. Rename a verb and the page that recommended it
  fails on the same commit.
- **Every path it cites still exists.** Move a document and the pointer to it
  fails, rather than being followed into a missing file.
- **It states no status a live source already answers.** The file's own rule is
  that spec states, story counts and spend figures have live sources and belong
  nowhere else; without a test that rule is a good intention, and good intentions
  are exactly what rots. A status word beside a spec id is the shape that
  violation takes, so that shape is what is banned.

The last of the three is the only one that is a judgement call rather than a fact,
and it is deliberately strict: it would rather refuse a defensible sentence than
let the file start keeping a second copy of the roadmap.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
BIN_DIR = Path(sys.executable).parent

TEXT = CLAUDE_MD.read_text(encoding="utf-8")
LINES = TEXT.splitlines()

#: Everything the file sets in backticks. One pass, three readers below.
CODE_SPANS = re.findall(r"`([^`\n]+)`", TEXT)


# --- every command it names still exists -------------------------------------


def _commands() -> list[tuple[str, ...]]:
    """Each distinct `factory-*` invocation the file recommends, as argv.

    Flags are kept — a renamed `--by` is as broken a recommendation as a renamed
    verb — but placeholders are not, because `<spec-dir>` is the reader's to
    fill in and `--help` does not want it.
    """
    found: list[tuple[str, ...]] = []
    for span in CODE_SPANS:
        words = span.split()
        if not words or not words[0].startswith("factory-"):
            continue
        argv = tuple(w for w in words if not w.startswith("<") and not w.endswith(">"))
        if argv not in found:
            found.append(argv)
    return found


COMMANDS = _commands()

#: How argparse renders a subcommand set. Read only out of the positional
#: section: an option with a choice list renders the same way, and `--by
#: {persona,epic,…}` is not a set of verbs.
_CHOICES = re.compile(r"\{([A-Za-z0-9_,\-]+)\}")
_POSITIONALS = re.compile(r"positional arguments:\n(.*?)(?:\n\n|\noptions:)", re.S)


def _verbs_of(help_text: str) -> set[str]:
    section = _POSITIONALS.search(help_text)
    if section is None:
        return set()
    listed = _CHOICES.search(section.group(1))
    return set(listed.group(1).split(",")) if listed else set()


def _split(argv: tuple[str, ...]) -> tuple[list[str], list[tuple[str, str | None]]]:
    """Positional words, and flags with the value each was given.

    A bare word after a flag is that flag's value, not a positional — `--by
    epic` names a rollup dimension, and asking the parser for a verb called
    `epic` would be asking the wrong question.
    """
    positionals: list[str] = []
    flags: list[tuple[str, str | None]] = []
    index = 1
    while index < len(argv):
        word = argv[index]
        if word.startswith("-"):
            following = argv[index + 1] if index + 1 < len(argv) else None
            value = following if following and not following.startswith("-") else None
            flags.append((word, value))
            index += 2 if value else 1
        else:
            positionals.append(word)
            index += 1
    return positionals, flags


def _help(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command + ["--help"], capture_output=True, text=True, timeout=120)


@pytest.mark.parametrize("argv", COMMANDS, ids=lambda argv: " ".join(argv))
def test_every_command_the_file_names_resolves(argv: tuple[str, ...]) -> None:
    executable = BIN_DIR / argv[0]
    assert executable.exists(), (
        f"CLAUDE.md tells the reader to run `{' '.join(argv)}`, but there is no "
        f"{argv[0]} entry point installed — check [project.scripts] in pyproject.toml"
    )

    positionals, flags = _split(argv)
    command = [str(executable)]
    result = _help(command)
    assert result.returncode == 0, f"{argv[0]} --help does not parse:\n{result.stderr.strip()}"

    # Descend the real parser one verb at a time. Falling back to a shorter
    # prefix would be the wrong kindness: `factory-doctor lyst` would then be
    # checked as `factory-doctor`, and pass.
    for word in positionals:
        verbs = _verbs_of(result.stdout)
        if not verbs:
            # No subcommands left to take: everything remaining is an argument
            # the reader supplies, not a name this file is claiming exists.
            break
        assert word in verbs, (
            f"CLAUDE.md tells the reader to run `{' '.join(argv)}`, but "
            f"`{' '.join([argv[0], *positionals[: positionals.index(word)]])}` has no "
            f"`{word}` verb — it has {sorted(verbs)}"
        )
        command.append(word)
        result = _help(command)
        assert result.returncode == 0, (
            f"`{' '.join(command)} --help` does not parse:\n{result.stderr.strip()}"
        )

    named = " ".join(Path(command[0]).name if part == command[0] else part for part in command)
    for flag, value in flags:
        assert flag in result.stdout, (
            f"CLAUDE.md recommends `{' '.join(argv)}`, but `{flag}` is not in the help "
            f"for `{named}` — the option was renamed or removed"
        )
        if value is not None:
            assert value in result.stdout, (
                f"CLAUDE.md recommends `{' '.join(argv)}`, but `{named}` no longer "
                f"accepts {value!r} for `{flag}`"
            )


def test_the_command_sweep_actually_read_the_file() -> None:
    # A parametrized sweep over an empty list passes without asserting anything,
    # which is how this file would go quiet if the backtick convention changed.
    named = {argv[0] for argv in COMMANDS}
    assert named == {"factory-roadmap", "factory-epic", "factory-doctor", "factory-usage"}, (
        f"the sweep found {sorted(named)} — CLAUDE.md is meant to point at all four "
        "operator entry points, and the sweep is meant to find all four"
    )


# --- every path it cites still exists ----------------------------------------

#: What counts as a claim about the tree: something with a directory separator,
#: or a bare filename with an extension this repository actually uses.
_SUFFIXES = (".md", ".py", ".yaml", ".yml", ".sh", ".json", ".toml", ".sql", ".db")


def _paths() -> list[str]:
    found: list[str] = []
    for span in CODE_SPANS:
        if " " in span or span.startswith("-") or "<" in span or span.startswith(":"):
            continue
        if "/" not in span and not span.endswith(_SUFFIXES):
            continue
        if span not in found:
            found.append(span)
    return found


PATHS = _paths()


@pytest.mark.parametrize("cited", PATHS, ids=lambda path: path)
def test_every_path_the_file_cites_exists(cited: str) -> None:
    # `.factory/…` is runtime state, created on first use rather than committed,
    # so its absence in a clean checkout is not a broken pointer.
    if cited.startswith(".factory/"):
        pytest.skip(f"{cited} is runtime state, not a committed path")
    assert (REPO_ROOT / cited).exists(), (
        f"CLAUDE.md points at {cited}, which is not in the tree — it moved, or it "
        "was never there"
    )


def test_the_path_sweep_actually_read_the_file() -> None:
    assert {
        ".specify/memory/constitution.md",
        "docs/architecture.md",
        "docs/decisions.md",
        "CONTEXT.md",
        "factory.yaml",
        "scripts/ergane-env.sh",
    } <= set(PATHS), (
        f"the sweep found {sorted(PATHS)} — CLAUDE.md is meant to point at the "
        "documents that bind, and the sweep is meant to find them"
    )


# --- it states no status a live source already answers -----------------------

#: How a spec is referred to: a numbered feature directory, or the bare number.
_SPEC_ID = re.compile(r"\b\d{3}-[a-z][a-z0-9-]*|\b0\d\d\b")

#: Words that assert where a spec has got to. Every one of them has a live
#: source — `factory-roadmap render` for the first four, `factory-epic landed`
#: and `factory-epic status` for the rest — so every one of them is a copy.
_STATUS_WORD = re.compile(
    r"\b(draft|ready|deferred|landed|shipped|blocked|in[- ]flight|dispatched"
    r"|running|done|complete|completed|passing|failing|merged)\b",
    re.IGNORECASE,
)

#: Near enough to read as a claim about that spec. Wider than a table cell,
#: narrower than a paragraph.
_WINDOW = 80


def _status_claims(lines: list[str] | None = None) -> list[tuple[int, str, str]]:
    """Every (line number, spec id, status word) that sit close enough to be read
    as one statement."""
    claims: list[tuple[int, str, str]] = []
    for number, line in enumerate(LINES if lines is None else lines, start=1):
        for spec in _SPEC_ID.finditer(line):
            window = line[max(0, spec.start() - _WINDOW) : spec.end() + _WINDOW]
            for status in _STATUS_WORD.finditer(window):
                claims.append((number, spec.group(0), status.group(0)))
    return claims


def test_the_file_names_no_spec_status() -> None:
    claims = _status_claims()
    assert not claims, (
        "CLAUDE.md states a spec's status, which has a live source and will rot:\n"
        + "\n".join(
            f"  line {number}: {spec!r} beside {status!r}" for number, spec, status in claims
        )
        + "\n\nAsk `factory-roadmap render specs` or `factory-epic landed <spec-dir>` "
        "instead of recording the answer here."
    )


# --- and it does not invent definitions ---------------------------------------

#: A glossary entry, as `CONTEXT.md` writes one: the term in bold, then a colon.
_DEFINED = re.compile(r"^\*\*(.+?)\*\*:", re.MULTILINE)

CONTEXT_TERMS = {
    term.lower() for term in _DEFINED.findall((REPO_ROOT / "CONTEXT.md").read_text("utf-8"))
}


def _terms_attributed_to_the_glossary() -> list[str]:
    """Terms `CLAUDE.md` bolds in a paragraph that sends the reader to the glossary.

    Pointing at a definition is a claim like any other, and a cheaper one to get
    wrong: this test exists because the first draft of the page sent a reader to
    `CONTEXT.md` for a term `CONTEXT.md` had never heard of.
    """
    cited: list[str] = []
    for paragraph in TEXT.split("\n\n"):
        if "CONTEXT.md" not in paragraph or "defines" not in paragraph:
            continue
        cited.extend(term.lower() for term in re.findall(r"\*\*(.+?)\*\*", paragraph))
    return cited


def test_every_term_the_file_sends_you_to_the_glossary_for_is_in_it() -> None:
    cited = _terms_attributed_to_the_glossary()
    assert cited, "CLAUDE.md no longer points at CONTEXT.md for any term"
    missing = [term for term in cited if term not in CONTEXT_TERMS]
    assert not missing, (
        f"CLAUDE.md says CONTEXT.md defines {missing}, and it does not. Either define "
        f"the term there or stop promising it here — CONTEXT.md defines "
        f"{sorted(CONTEXT_TERMS)}"
    )


def test_the_status_sweep_can_actually_see_a_status() -> None:
    # The one test here that asserts an absence, so it is the one that could
    # quietly stop testing anything. This proves the detector still fires — and
    # that it does not fire on prose making no claim about a spec.
    assert _status_claims(["The delta work in 016-delta-derivation is landed as of today."])
    assert _status_claims(["Story 3 of 006 is still blocked."])
    assert not _status_claims(["`docs/architecture.md` describes how an epic is judged."])
    assert not _status_claims(["Landed story numbers are immutable; new work takes new ones."])
