"""`CLAUDE.md` cannot be allowed to lie, so it is asserted rather than trusted.

An orientation file is the worst kind of documentation to let rot, because it is
read by an agent that has no other picture of the repository yet and therefore no
way to notice that what it just read stopped being true. A stale sentence in
`docs/architecture.md` gets caught by the next person who knows better; a stale
command in `CLAUDE.md` gets *acted on*, and the discovery arrives hours later as a
burned attempt.

So the three claims the file makes about the world are checked against the world:

- **Every command it names still exists.** Each backticked `ergane` invocation
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
from pathlib import Path

import pytest

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

CLAUDE_MD = REPO_ROOT / "CLAUDE.md"

TEXT = CLAUDE_MD.read_text(encoding="utf-8")
LINES = TEXT.splitlines()


# --- every command it names still exists -------------------------------------


COMMANDS = extract_commands(TEXT)


@pytest.mark.parametrize("argv", COMMANDS, ids=lambda argv: " ".join(argv))
def test_every_command_the_file_names_resolves(argv: tuple[str, ...]) -> None:
    executable = BIN_DIR / argv[0]
    assert executable.exists(), (
        f"CLAUDE.md tells the reader to run `{' '.join(argv)}`, but there is no "
        f"{argv[0]} entry point installed — check [project.scripts] in pyproject.toml"
    )

    positionals, flags = split_argv(argv)
    command = [str(executable)]
    result = run_help(command)
    assert result.returncode == 0, f"{argv[0]} --help does not parse:\n{result.stderr.strip()}"

    # Descend the real parser one verb at a time. Falling back to a shorter
    # prefix would be the wrong kindness: `ergane doctor lyst` would then be
    # checked as `ergane doctor`, and pass.
    for word in positionals:
        verbs = verbs_of(result.stdout)
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
        result = run_help(command)
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
    assert named == {"ergane"}, (
        f"the sweep found {sorted(named)} — CLAUDE.md is meant to point at the single "
        "operator entry point, and the sweep is meant to find it"
    )


# --- every path it cites still exists ----------------------------------------

PATHS = extract_paths(TEXT)


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


def test_the_file_names_no_spec_status() -> None:
    claims = status_claims(TEXT)
    assert not claims, (
        "CLAUDE.md states a spec's status, which has a live source and will rot:\n"
        + "\n".join(
            f"  line {number}: {spec!r} beside {status!r}" for number, spec, status in claims
        )
        + "\n\nAsk `ergane roadmap render specs` or `ergane build landed <spec-dir>` "
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
    assert status_claims("The delta work in 016-delta-derivation is landed as of today.".splitlines())
    assert status_claims("Story 3 of 006 is still blocked.".splitlines())
    assert not status_claims("`docs/architecture.md` describes how an epic is judged.".splitlines())
    assert not status_claims("Landed story numbers are immutable; new work takes new ones.".splitlines())
