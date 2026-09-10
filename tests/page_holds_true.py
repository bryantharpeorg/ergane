"""Shared machinery for asserting that a page still describes the tree.

`tests/test_claude_md.py`, `tests/test_readme.py` and `tests/test_onramp_html.py`
all need the same three checks:

- every command the page names still parses,
- every path the page cites still exists,
- the page states no status a live source already answers.

The extractors live here so there is only one parser for each convention; a
second parser in a second file is how two pages drift apart while both suites
stay green.
"""

from __future__ import annotations

import argparse
import functools
import html
import io
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

from factory.cli.main import _build_parser

REPO_ROOT = Path(__file__).resolve().parents[1]
BIN_DIR = Path(sys.executable).parent


class UnrecognizedCommandError(Exception):
    """A code span starts with a word close to, but not equal to, a known Ergane entrypoint."""


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


class _HTMLCodeExtractor(HTMLParser):
    """Collect text inside `<code>` spans and `<pre class="well">` blocks.

    HTML entities are unescaped, and `<span class="cmt">` subtrees are dropped
    so shell comments in code wells do not look like commands.  Fenced bash
    blocks are split line-by-line; inline `<code>` spans are returned whole.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.spans: list[str] = []
        self._in_code = False
        self._in_well = False
        self._buf: list[str] = []
        self._cmt_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k: v for k, v in attrs}
        if self._cmt_depth:
            self._cmt_depth += 1
            return
        if attr_map.get("class") == "cmt":
            self._cmt_depth = 1
            return
        if tag == "pre" and attr_map.get("class") == "well":
            self._in_well = True
            self._buf = []
        elif tag == "code" and not self._in_well:
            self._in_code = True
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if self._cmt_depth:
            self._cmt_depth -= 1
            return
        if tag == "pre" and self._in_well:
            text = html.unescape("".join(self._buf))
            for line in text.splitlines():
                stripped = line.strip()
                if stripped:
                    self.spans.append(stripped)
            self._in_well = False
            self._buf = []
        elif tag == "code" and self._in_code:
            text = html.unescape("".join(self._buf)).strip()
            if text:
                self.spans.append(text)
            self._in_code = False
            self._buf = []

    def _append(self, data: str) -> None:
        if (self._in_code or self._in_well) and not self._cmt_depth:
            self._buf.append(data)

    def handle_data(self, data: str) -> None:
        self._append(data)

    def handle_entityref(self, name: str) -> None:
        self._append(html.unescape(f"&{name};"))

    def handle_charref(self, name: str) -> None:
        self._append(html.unescape(f"&#{name};"))


def html_code_spans(text: str) -> list[str]:
    """Everything the page sets in `<code>`, plus each line of a `<pre class="well">`."""
    parser = _HTMLCodeExtractor()
    parser.feed(text)
    return parser.spans


# --- every command the file names still parses -------------------------------


@functools.lru_cache(maxsize=None)
def _parser() -> argparse.ArgumentParser:
    """The real `ergane` parser, built once per session.

    Reusing the parser avoids importing every noun module once per command on
    the page. `argparse.parse_args` validates the invocation without dispatching
    the handler, so no verb runs and no subprocess spawns.
    """
    return _build_parser()


def _help_text(argv: tuple[str, ...]) -> str:
    """Capture the help output the parser would print for `argv`.

    `argv` includes the program name ("ergane") at index 0; the parser expects
    arguments after the program name, so we strip it before asking for `--help`.
    """
    parser = _parser()
    old_stderr = sys.stderr
    old_stdout = sys.stdout
    err_buffer = io.StringIO()
    out_buffer = io.StringIO()
    sys.stderr = err_buffer
    sys.stdout = out_buffer
    try:
        try:
            parser.parse_args(list(argv[1:]) + ["--help"])
        except SystemExit:
            pass
        return out_buffer.getvalue()
    finally:
        sys.stderr = old_stderr
        sys.stdout = old_stdout


#: Placeholders that appear on the swept pages, mapped to a value of the right
#: shape. Shape is what matters: `<spec-dir>` is a path, `<epic-id>` is an
#: identifier, `<repo-slug>` is a slug, and `<target-repo-path>` is a path.
_PLACEHOLDER_VALUES: dict[str, str] = {
    "<spec-dir>": "specs/001",
    "<target-repo-path>": "factory/target_repo",
    "<epic-id>": "001",
    "<repo-slug>": "ergane-cli",
    "<workgraph.json>": "specs/001/workgraph.json",
    "<repository-root>": "factory/target_repo",
    "<dir>": "001",
    "<branch>": "main",
}


def _substitute_placeholders(argv: tuple[str, ...]) -> tuple[str, ...]:
    """Replace angle-bracket placeholders with values that argparse will accept."""
    return tuple(_PLACEHOLDER_VALUES.get(word, word) for word in argv)


def parse_argv(argv: tuple[str, ...]) -> argparse.Namespace | None:
    """Parse one Ergane argv using the real CLI parser.

    Placeholders are substituted before parsing. On success the returned
    namespace proves the invocation is syntactically valid; a successful help
    request returns None. On failure an `AssertionError` is raised carrying
    argparse's own message. No verb handler is called and no subprocess is spawned.
    """
    parser = _parser()
    substituted = _substitute_placeholders(argv)
    command = list(substituted[1:])  # argparse expects argv without the program name
    old_stderr = sys.stderr
    try:
        buffer = io.StringIO()
        sys.stderr = buffer
        try:
            return parser.parse_args(command)
        except SystemExit as exc:
            if exc.code == 0 and any(word in {"--help", "-h"} for word in command):
                return None
            message = buffer.getvalue().strip() or f"invalid arguments: {argv}"
            raise AssertionError(f"parse failed for `{' '.join(argv)}`: {message}") from exc
    finally:
        sys.stderr = old_stderr


def _damerau_levenshtein(a: str, b: str) -> int:
    """Damerau–Levenshtein distance between two strings.

    Adjacent transpositions count as a single edit, so a transposed character
    is caught with the same small threshold as an insertion or deletion.
    """
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    prev_prev = list(range(len(b) + 1))
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and ca == b[j - 2] and cb == a[i - 2]:
                curr[j] = min(curr[j], prev_prev[j - 2] + 1)
        prev_prev, prev = prev, curr
    return prev[-1]


def _near_entrypoints(word: str, entrypoints: set[str], threshold: int = 1) -> set[str]:
    """Every known entrypoint within `threshold` edits of `word`.

    An exact match is not a near-miss, so it is excluded.
    """
    word = word.lower()
    near: set[str] = set()
    for entrypoint in entrypoints:
        if word == entrypoint:
            continue
        if _damerau_levenshtein(word, entrypoint) <= threshold:
            near.add(entrypoint)
    return near


def root_name() -> str:
    """The console script name the page should use as a command."""
    return _parser().prog


def root_entrypoints() -> set[str]:
    """The root command plus every noun the CLI advertises.

    This is the set a near-miss detector compares against. It is derived from
    the configured argparse parser so it cannot drift behind the implementation
    and never needs to spawn a subprocess.
    """
    root = root_name()
    return {root} | verbs_of([root])


def _is_command_shaped(span: str) -> bool:
    """True when a code span looks like a command line rather than a path, alias, or key.

    Command-shaped means: at least two whitespace-separated words, no directory
    separators, no `=`, and no `/`. This is the same rule the anti-vacuity guard
    uses, so the extractor and the guard cannot disagree about what was available
    to be found.
    """
    if not span:
        return False
    # A leading flag on its own is not a command; it names an option, not an
    # invocation the reader is being told to type.
    if span.startswith("-"):
        return False
    words = span.split()
    if len(words) < 2:
        return False
    joined = "".join(words)
    # Path, model alias, and config-key shapes all carry separators that a command
    # line with a leading entrypoint does not.
    if "/" in joined or "=" in joined or "." in joined:
        return False
    return True


def _command_shaped_spans(text: str) -> list[str]:
    """Every code span that matches the command-shaped rule."""
    if text.strip().startswith("<"):
        spans = html_code_spans(text)
    else:
        spans = code_spans(text)
    return [span for span in spans if _is_command_shaped(span)]


def assert_commands_not_dropped(text: str) -> int:
    """Anti-vacuity guard: count the command-shaped spans the extractor could have found.

    The page suites assert this count against a baseline derived from the same
    rule the extractor uses, so the guard proves nothing was silently skipped.
    """
    return len(_command_shaped_spans(text))


def extract_commands(text: str) -> list[tuple[str, ...]]:
    """Each distinct `ergane` invocation the file recommends, as argv.

    Flags are kept — a renamed `--by` is as broken a recommendation as a
    renamed verb — but placeholders are not stripped, because the parse check
    substitutes each placeholder by shape before asking argparse to validate
    the invocation.

    A span that is command-shaped but does not resolve raises
    `UnrecognizedCommandError` rather than being skipped. A span that is not
    command-shaped (a path, config key, environment variable, alias, or bare
    flag) is ignored.
    """
    root = root_name()
    entrypoints = root_entrypoints()
    found: list[tuple[str, ...]] = []
    for span in _command_shaped_spans(text):
        words = span.split()
        if not words:
            continue
        first = words[0]
        if first != root:
            near = _near_entrypoints(first, entrypoints)
            if near:
                raise UnrecognizedCommandError(
                    f"unrecognised command {first!r} in `{span}` — "
                    f"did you mean {sorted(near)}?"
                )
            continue
        argv = tuple(words)
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


def verbs_of(command: list[str]) -> set[str]:
    help_text = _help_text(tuple(command))
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


# --- every path it cites still exists -----------------------------------------

#: What counts as a claim about the tree: something with a directory separator,
#: or a bare filename with an extension this repository actually uses.
SUFFIXES = (".md", ".py", ".yaml", ".yml", ".sh", ".json", ".toml", ".sql", ".db")


def extract_paths(
    text: str, *, suffixes: tuple[str, ...] = SUFFIXES
) -> list[str]:
    found: list[str] = []
    if text.strip().startswith("<"):
        spans = html_code_spans(text)
    else:
        spans = code_spans(text)
    for span in spans:
        if " " in span or span.startswith("-") or "<" in span or span.startswith(":"):
            continue
        if span.startswith("/"):
            # Host-absolute paths (/usr/bin/bwrap, /etc/apparmor.d/bwrap) are
            # deliberately cited by procedure text, but they are not paths inside
            # this repository and cannot be checked with REPO_ROOT / span.
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
