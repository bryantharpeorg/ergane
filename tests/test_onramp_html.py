"""`docs/onramp.html` cannot be allowed to lie, so it is asserted rather than trusted.

This is the same three-claim sweep `tests/test_readme.py` and
`tests/test_claude_md.py` run on their pages, applied to the operator onramp.
Every command it names must parse, every path it cites must exist, and it must
not keep a second copy of any figure that has a live source.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from factory.controlplane.config import _SECRET_PATTERNS
from tests.page_holds_true import (
    BIN_DIR,
    REPO_ROOT,
    _help_text,
    assert_commands_not_dropped,
    extract_commands,
    extract_paths,
    html_code_spans,
    parse_argv,
    split_argv,
    status_claims,
    verbs_of,
)

ONRAMP_HTML = REPO_ROOT / "docs" / "onramp.html"

TEXT = ONRAMP_HTML.read_text(encoding="utf-8")
LINES = TEXT.splitlines()


# --- every command it names still parses ---------------------------------------


COMMANDS = extract_commands(TEXT)


@pytest.mark.parametrize("argv", COMMANDS, ids=lambda argv: " ".join(argv))
def test_every_command_the_file_names_parses(argv: tuple[str, ...]) -> None:
    executable = BIN_DIR / argv[0]
    assert executable.exists(), (
        f"docs/onramp.html tells the reader to run `{' '.join(argv)}`, but there is no "
        f"{argv[0]} entry point installed — check [project.scripts] in pyproject.toml"
    )

    parse_argv(argv)

    positionals, flags = split_argv(argv)
    command: list[str] = [argv[0]]
    for word in positionals:
        verbs = verbs_of(command)
        if not verbs:
            break
        assert word in verbs, (
            f"docs/onramp.html tells the reader to run `{' '.join(argv)}`, but "
            f"`{' '.join(command)}` has no "
            f"`{word}` verb — it has {sorted(verbs)}"
        )
        command.append(word)

    help_text = _help_text(tuple(command))
    for flag, value in flags:
        assert flag in help_text, (
            f"docs/onramp.html recommends `{' '.join(argv)}`, but `{flag}` is not in the help "
            f"for `{' '.join(command)}` — the option was renamed or removed"
        )
        if value is not None:
            assert value in help_text, (
                f"docs/onramp.html recommends `{' '.join(argv)}`, but `{' '.join(command)}` no longer "
                f"accepts {value!r} for `{flag}`"
            )


def test_the_command_sweep_actually_read_the_file() -> None:
    # A parametrized sweep over an empty list passes without asserting anything.
    # The onramp is meant to name the install command in its first code well.
    flat = {" ".join(argv) for argv in COMMANDS}
    assert "ergane install" in flat, (
        f"the sweep found {sorted(flat)} — docs/onramp.html is meant to name "
        "`ergane install`, and the sweep is meant to find it"
    )
    assert "ergane init" in flat, (
        f"the sweep found {sorted(flat)} — docs/onramp.html is meant to name "
        "`ergane init`, and the sweep is meant to find it"
    )


# --- the HTML extractor is honest: it did not drop command-shaped spans -------


def test_the_command_sweep_found_every_command_shaped_span() -> None:
    count = assert_commands_not_dropped(TEXT)
    assert count >= len(COMMANDS), (
        f"the anti-vacuity guard saw {count} command-shaped spans but only extracted "
        f"{len(COMMANDS)} commands — something was silently dropped"
    )


# --- every path it cites still exists -----------------------------------------


PATHS = extract_paths(TEXT)


@pytest.mark.parametrize("cited", PATHS, ids=lambda path: path)
def test_every_path_the_file_cites_exists(cited: str) -> None:
    if cited.startswith(".factory/"):
        pytest.skip(f"{cited} is runtime state, not a committed path")
    assert (REPO_ROOT / cited).exists(), (
        f"docs/onramp.html points at {cited}, which is not in the tree — it moved, or it "
        "was never there"
    )


def test_the_path_sweep_actually_read_the_file() -> None:
    assert {
        ".specify/memory/constitution.md",
        "docs/architecture.md",
        "docs/decisions.md",
        "CONTEXT.md",
    } <= set(PATHS), (
        f"the sweep found {sorted(PATHS)} — docs/onramp.html is meant to point at the "
        "documents that bind, and the sweep is meant to find them"
    )


# --- it states no secret value -------------------------------------------------


def test_the_file_contains_no_secret_value() -> None:
    matches: list[tuple[int, str, str]] = []
    for number, line in enumerate(LINES, start=1):
        for pattern in _SECRET_PATTERNS:
            for match in pattern.finditer(line):
                matches.append((number, match.group(0), pattern.pattern))
    assert not matches, (
        "docs/onramp.html contains a value that matches a shipped secret shape:\n"
        + "\n".join(f"  line {number}: {value!r} (pattern {pattern!r})" for number, value, pattern in matches)
    )


# --- it states no status a live source already answers -------------------------


def test_the_file_names_no_spec_status() -> None:
    claims = status_claims(TEXT)
    assert not claims, (
        "docs/onramp.html states a spec's status, which has a live source and will rot:\n"
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
        "docs/onramp.html states a spend figure, which `ergane usage` already answers:\n"
        + "\n".join(f"  line {number}: {line}" for number, line in hits)
    )


# --- HTML-specific extraction tests ------------------------------------------


def test_html_extractor_finds_code_spans_and_wells() -> None:
    """The HTML reader sees both inline <code> and <pre class="well"> content."""
    sample = """\
<p>Run <code>ergane install</code> first.</p>
<pre class="well"><code>ergane init
ergane worker install</code></pre>
"""
    spans = html_code_spans(sample)
    assert "ergane install" in spans
    assert "ergane init" in spans
    assert "ergane worker install" in spans


def test_html_extractor_unescapes_entities_before_parsing() -> None:
    """<code>ergane repo onboard &lt;target-repo-path&gt;</code> becomes parseable."""
    sample = "<code>ergane repo onboard &lt;target-repo-path&gt;</code>"
    spans = html_code_spans(sample)
    assert spans == ["ergane repo onboard <target-repo-path>"]
    argv = tuple(spans[0].split())
    parse_argv(argv)


def test_html_extractor_strips_comment_spans_from_wells() -> None:
    """<span class="cmt"> content is dropped so shell comments are not parsed."""
    sample = """\
<pre class="well"><code><span class="cmt"># the interview</span>
ergane install
<span class="cmt"># verify only</span>
ergane install --verify</code></pre>
"""
    spans = html_code_spans(sample)
    assert "# the interview" not in spans
    assert "# verify only" not in spans
    assert "ergane install" in spans
    assert "ergane install --verify" in spans
