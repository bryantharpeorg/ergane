"""Shared machinery for asserting that a markdown page still describes the tree.

`tests/test_claude_md.py` and `tests/test_readme.py` both need the same three
checks:

- every command the page names still resolves,
- every path the page cites still exists,
- the page states no status a live source already answers.

The extractors live here so there is only one parser for each convention; a
second parser in a second file is how two pages drift apart while both suites
stay green.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BIN_DIR = Path(sys.executable).parent


#: Everything the page sets in backticks, plus each command line inside a
#: fenced `bash` block. One pass, three readers below.
_FENCED_BASH = re.compile(r"^```bash\n(.*?)\n```", re.MULTILINE | re.S)


def code_spans(text: str) -> list[str]:
    spans = re.findall(r"`([^`\n]+)`", text)
    for block in _FENCED_BASH.findall(text):
        for line in block.splitlines():
            stripped = line.strip()
            if stripped:
                spans.append(stripped)
    return spans


# --- every command the file names still exists ---------------------------------


def extract_commands(text: str) -> list[tuple[str, ...]]:
    """Each distinct `ergane` invocation the file recommends, as argv.

    Flags are kept — a renamed `--by` is as broken a recommendation as a
    renamed verb — but placeholders are not, because `<spec-dir>` is the
    reader's to fill in and `--help` does not want it.
    """
    found: list[tuple[str, ...]] = []
    for span in code_spans(text):
        words = span.split()
        if not words or words[0] != "ergane":
            continue
        argv = tuple(w for w in words if not w.startswith("<") and not w.endswith(">"))
        if argv not in found:
            found.append(argv)
    return found


#: How argparse renders a subcommand set. Read only out of the positional
#: section: an option with a choice list renders the same way, and `--by
#: {persona,epic,…}` is not a set of verbs.
_CHOICES = re.compile(r"\{([A-Za-z0-9_,\-]+)\}")
_POSITIONALS = re.compile(r"positional arguments:\n(.*?)(?:\n\n|\noptions:)", re.S)
#: When argparse lists a positional with a fixed width, each choice sits on its
#: own indented line rather than inside a brace list — the root `NOUN` listing.
_INDENTED_VERB = re.compile(r"^    ([A-Za-z0-9_-]+)", re.MULTILINE)


def verbs_of(help_text: str) -> set[str]:
    section = _POSITIONALS.search(help_text)
    if section is None:
        return set()
    body = section.group(1)
    listed = _CHOICES.search(body)
    if listed:
        return set(listed.group(1).split(","))
    return set(_INDENTED_VERB.findall(body))


def split_argv(argv: tuple[str, ...]) -> tuple[list[str], list[tuple[str, str | None]]]:
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


def run_help(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command + ["--help"], capture_output=True, text=True, timeout=120)


# --- every path it cites still exists -----------------------------------------

#: What counts as a claim about the tree: something with a directory separator,
#: or a bare filename with an extension this repository actually uses.
SUFFIXES = (".md", ".py", ".yaml", ".yml", ".sh", ".json", ".toml", ".sql", ".db")


def extract_paths(
    text: str, *, suffixes: tuple[str, ...] = SUFFIXES
) -> list[str]:
    found: list[str] = []
    for span in code_spans(text):
        if " " in span or span.startswith("-") or "<" in span or span.startswith(":"):
            continue
        if "/" not in span and not span.endswith(suffixes):
            continue
        if span not in found:
            found.append(span)
    return found


# --- it states no status a live source already answers -------------------------

#: How a spec is referred to: a numbered feature directory, or the bare number.
_SPEC_ID = re.compile(r"\b\d{3}-[a-z][a-z0-9-]*|\b0\d\d\b")

#: Words that assert where a spec has got to. Every one of them has a live
#: source — `ergane spec list` for the first four, `ergane build landed`
#: and `ergane build status` for the rest — so every one of them is a copy.
_STATUS_WORD = re.compile(
    r"\b(draft|ready|deferred|landed|shipped|blocked|in[- ]flight|dispatched"
    r"|running|done|complete|completed|passing|failing|merged)\b",
    re.IGNORECASE,
)

#: Near enough to read as a claim about that spec. Wider than a table cell,
#: narrower than a paragraph.
_WINDOW = 80


def status_claims(
    text: str | list[str], lines: list[str] | None = None
) -> list[tuple[int, str, str]]:
    """Every (line number, spec id, status word) that sit close enough to be read
    as one statement."""
    claims: list[tuple[int, str, str]] = []
    if lines is not None:
        source_lines = lines
    elif isinstance(text, list):
        source_lines = text
    else:
        source_lines = text.splitlines()
    for number, line in enumerate(source_lines, start=1):
        for spec in _SPEC_ID.finditer(line):
            window = line[max(0, spec.start() - _WINDOW) : spec.end() + _WINDOW]
            for status in _STATUS_WORD.finditer(window):
                claims.append((number, spec.group(0), status.group(0)))
    return claims
