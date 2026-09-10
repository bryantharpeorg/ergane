"""Assert that the README and its setup guide describe the tree accurately.

This is the same three-claim sweep `tests/test_claude_md.py` runs on
`CLAUDE.md`, applied to the repository's front door. A new operator follows the
README and linked setup guide before operating Ergane, so every command it names
must resolve, every path it cites must exist, and it must not keep a second
copy of any figure that has a live source.

US2 adds a fourth claim: the setup guide must still state the prerequisites and install
differences that live under "What you must already have" and "Installing Ergane".
Each guard is a mutation test: a copy of the page text is edited to remove one
protected concept, and the suite is required to fail on that copy. A test that
only asserts the sentence is present today would pass forever on a page nobody
edits, so the guard is exercised against a deliberately broken page.
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
    extract_commands,
    extract_paths,
    parse_argv,
    split_argv,
    status_claims,
    verbs_of,
)

README_MD = REPO_ROOT / "README.md"

SETUP_MD = REPO_ROOT / "docs" / "getting-started.md"
README_TEXT = README_MD.read_text(encoding="utf-8")
SETUP_TEXT = SETUP_MD.read_text(encoding="utf-8")
# Sweep both pages so moving operating instructions out of the overview does
# not drop their command, path, secret, or live-status checks.
TEXT = README_TEXT + "\n" + SETUP_TEXT
LINES = TEXT.splitlines()


# --- every command it names still exists ---------------------------------------


COMMANDS = extract_commands(TEXT)


@pytest.mark.parametrize("argv", COMMANDS, ids=lambda argv: " ".join(argv))
def test_every_command_the_file_names_parses(argv: tuple[str, ...]) -> None:
    executable = BIN_DIR / argv[0]
    assert executable.exists(), (
        f"README.md or docs/getting-started.md tells the reader to run `{' '.join(argv)}`, but there is no "
        f"{argv[0]} entry point installed — check [project.scripts] in pyproject.toml"
    )

    parse_argv(argv)

    positionals, flags = split_argv(argv)
    command: list[str] = [argv[0]]
    # Walk the subparser chain so we can validate flags against the leaf help.
    for word in positionals:
        verbs = verbs_of(command)
        if not verbs:
            break
        assert word in verbs, (
            f"README.md or docs/getting-started.md tells the reader to run `{' '.join(argv)}`, but "
            f"`{' '.join(command)}` has no "
            f"`{word}` verb — it has {sorted(verbs)}"
        )
        command.append(word)

    help_text = _help_text(tuple(command))
    for flag, _value in flags:
        assert flag in help_text, (
            f"README.md or docs/getting-started.md recommends `{' '.join(argv)}`, but `{flag}` is not in the help "
            f"for `{' '.join(command)}` — the option was renamed or removed"
        )
        # parse_argv already validates choices and argument types. Free-form
        # paths and identifiers need not appear literally in argparse's help.


def test_the_command_sweep_actually_read_the_file() -> None:
    # A parametrized sweep over an empty list passes without asserting anything,
    # which is how this file would go quiet if the backtick convention changed.
    flat = {" ".join(argv) for argv in COMMANDS}
    assert ("ergane", "--help") in extract_commands(README_TEXT)
    assert "(docs/getting-started.md)" in README_TEXT
    assert "ergane install" in flat, (
        f"the sweep found {sorted(flat)} — the setup guide is meant to name "
        "`ergane install`, and the sweep is meant to find it"
    )
    assert "ergane init" in flat, (
        f"the sweep found {sorted(flat)} — the setup guide is meant to name "
        "`ergane init`, and the sweep is meant to find it"
    )


# --- every path it cites still exists -----------------------------------------


PATHS = extract_paths(TEXT)


@pytest.mark.parametrize("cited", PATHS, ids=lambda path: path)
def test_every_path_the_file_cites_exists(cited: str) -> None:
    if cited.startswith(".factory/"):
        pytest.skip(f"{cited} is runtime state, not a committed path")
    assert (REPO_ROOT / cited).exists(), (
        f"README.md or docs/getting-started.md points at {cited}, which is not in the tree — it moved, or it "
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
        "README.md or docs/getting-started.md contains a value that matches a shipped secret shape:\n"
        + "\n".join(f"  line {number}: {value!r} (pattern {pattern!r})" for number, value, pattern in matches)
    )


# --- it states no status a live source already answers -------------------------


def test_the_file_names_no_spec_status() -> None:
    claims = status_claims(TEXT)
    assert not claims, (
        "README.md or docs/getting-started.md states a spec's status, which has a live source and will rot:\n"
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
        "README.md or docs/getting-started.md states a spend figure, which `ergane usage` already answers:\n"
        + "\n".join(f"  line {number}: {line}" for number, line in hits)
    )


# --- US2: the prerequisites and install differences cannot be silently removed --


def _section_between(
    text: str, start_heading: str, end_headings: tuple[str, ...]
) -> str:
    """Return the slice of `text` from `start_heading` up to any of `end_headings`."""
    lines = text.splitlines()
    start_idx: int | None = None
    end_idx = len(lines)
    for i, line in enumerate(lines):
        if line.strip() == start_heading:
            start_idx = i
        elif start_idx is not None and any(line.strip() == h for h in end_headings):
            end_idx = i
            break
    if start_idx is None:
        return ""
    return "\n".join(lines[start_idx:end_idx])


def _lower_words(s: str) -> set[str]:
    """Lower-cased tokens: keep compound words like `ergane-cli` and `/key/generate`."""
    return set(re.findall(r"[a-z0-9]+(?:[/-][a-z0-9]+)*", s.lower()))


def _any_subset_present(words: set[str], options: list[set[str]]) -> bool:
    """True when at least one required token set is fully contained in `words`."""
    return any(option <= words for option in options)


_MISSING_CONCEPT_NAMES: dict[str, str] = {
    "database": "database requirement",
    "endpoints": "dependent key-management endpoints",
    "config_only_warning": "config-only proxy warning",
    "aliases": "model and fallback alias requirement",
    "published_install": "published-package install as primary path",
    "checkout_install": "checkout install distinguished from published install",
    "resolve_differently": "install paths resolve persona registry differently",
}


def missing_readme_concepts(page_text: str) -> list[str]:
    """Return the protected concepts from the setup guide that `page_text` fails to state.

    The check is meaning-based, not literal-string based: a reworded page that
    still expresses the same fact passes, and a page that removes the fact fails.
    """
    missing: list[str] = []
    what_have = _section_between(
        page_text, "## What you must already have", ("## Installing Ergane",)
    )
    what_low = _lower_words(what_have)
    install = _section_between(
        page_text, "## Installing Ergane", ("## Configuring the control plane",)
    )
    install_low = _lower_words(install)

    if not _any_subset_present(
        what_low,
        [
            {"database", "backed"},
            {"database", "url"},
            {"database_url"},
        ],
    ):
        missing.append(_MISSING_CONCEPT_NAMES["database"])

    if not _any_subset_present(
        what_low,
        [
            {"key/generate", "key/info"},
            {"key/generate", "spend/logs/v2"},
            {"key/info", "spend/logs/v2"},
        ],
    ):
        missing.append(_MISSING_CONCEPT_NAMES["endpoints"])

    if not (
        ({"config-only", "config", "only"} & what_low)
        and ({"404", "rest"} & what_low)
        and "v1/models" in what_low
    ):
        missing.append(_MISSING_CONCEPT_NAMES["config_only_warning"])

    if not _any_subset_present(what_low, [{"model", "fallback", "personas"}]):
        missing.append(_MISSING_CONCEPT_NAMES["aliases"])

    if not _any_subset_present(
        install_low,
        [
            {"published", "distribution", "ergane-cli"},
            {"pypi", "ergane-cli"},
        ],
    ):
        missing.append(_MISSING_CONCEPT_NAMES["published_install"])

    if not _any_subset_present(
        install_low,
        [
            {"checkout", "editable"},
            {"git", "clone", "editable"},
            {"checkout", "pip", "install"},
        ],
    ):
        missing.append(_MISSING_CONCEPT_NAMES["checkout_install"])

    if not _any_subset_present(
        install_low,
        [
            {"resolve", "different", "personas"},
            {"resolve", "different", "registry"},
            {"resolve", "different", "places"},
            {"different", "personas", "locations"},
            {"different", "personas", "registry"},
            {"different", "personas", "places"},
        ],
    ):
        missing.append(_MISSING_CONCEPT_NAMES["resolve_differently"])

    return missing


def test_the_setup_guide_states_all_required_concepts() -> None:
    missing = missing_readme_concepts(SETUP_TEXT)
    assert not missing, (
        "docs/getting-started.md is missing required concepts:\n"
        + "\n".join(f"  - {concept}" for concept in missing)
    )


#: Mutations that remove a single protected concept from a copy of the page.
#: Each value is a (concept key, mutated text) pair used by the parametrized test.
def _mutations() -> list[tuple[str, str]]:
    return [
        (
            "database",
            SETUP_TEXT.replace("**The proxy must be database-backed.**", "**The proxy must exist.**")
            .replace("`DATABASE_URL`", "`POSTGRES_URL`")
            .replace("database-backed", "operational")
            .replace("database", "service"),
        ),
        (
            "endpoints",
            SETUP_TEXT.replace("`POST /key/generate`", "`POST /key/create`")
            .replace("`GET /key/info`", "`GET /key/status`")
            .replace("`GET /spend/logs/v2`", "`GET /spend/total`"),
        ),
        (
            "config_only_warning",
            SETUP_TEXT.replace("config-only proxy", "minimal proxy")
            .replace("returns 404", "returns 200")
            .replace("all of the rest", "everything")
            .replace("`GET /v1/models`", "`GET /v1/health`"),
        ),
        (
            "aliases",
            SETUP_TEXT.replace(
                "**The proxy must serve every model alias the persona registry names.**",
                "**The proxy must be up.**",
            )
            .replace("`model`", "`alias`")
            .replace("`fallback`", "`backup`"),
        ),
        (
            "published_install",
            (
                lambda t: re.sub(
                    r"### To run Ergane against your own repositories\n\n.*?(?=### To work on Ergane itself)",
                    "",
                    t,
                    flags=re.S,
                )
                .replace(
                    "A published install reads the copy packaged inside the\n"
                    "distribution — so editing a `personas.yaml` in some directory you happen to be\n"
                    "standing in changes nothing, and the file you want to edit is not obviously\n"
                    "anywhere.",
                    "",
                )
                .replace(
                    "If you installed the published package and want your own registry, put it where\n"
                    "the resolver looks rather than where you happen to be; `ergane install` reports\n"
                    "the path it resolved, and that path is the answer.",
                    "",
                )
            )(SETUP_TEXT),
        ),
        (
            "checkout_install",
            (
                lambda t: re.sub(
                    r"### To work on Ergane itself\n\n.*?(?=### The difference that will bite you)",
                    "",
                    t,
                    flags=re.S,
                ).replace(
                    "An editable\n"
                    "checkout reads the `personas.yaml` at the root of that checkout, so editing it\n"
                    "takes effect immediately.",
                    "",
                )
            )(SETUP_TEXT),
        ),
        (
            "resolve_differently",
            SETUP_TEXT.replace(
                "The two paths resolve the persona registry from different places.",
                "Both paths use the same personas.yaml.",
            ),
        ),
    ]


@pytest.mark.parametrize(
    "concept,mutated_text",
    _mutations(),
    ids=lambda item: item[0],
)
def test_missing_concept_is_detected(concept: str, mutated_text: str) -> None:
    expected = _MISSING_CONCEPT_NAMES[concept]
    missing = missing_readme_concepts(mutated_text)
    assert expected in missing, (
        f"the `{concept}` mutation should have been reported as missing "
        f"`{expected}`, but the guard reported {missing}"
    )


def test_reworded_equivalent_page_passes() -> None:
    """A page that rewords the protected facts, without removing them, passes.

    This keeps the guards anchored to meaning rather than to one literal string.
    """
    reworded = (
        SETUP_TEXT.replace(
            "**The proxy must be database-backed.**",
            "**Ergane needs a database-backed LiteLLM proxy.**",
        )
        .replace(
            "Ergane mints one with `POST /key/generate`, reads what it spent through `GET /key/info` and `GET /spend/logs/v2`, and revokes it when the attempt ends.",
            "It creates a virtual key via `POST /key/generate`, inspects spend with `GET /key/info` and `GET /spend/logs/v2`, and deletes the key when the attempt ends.",
        )
        .replace(
            "A config-only proxy answers `GET /v1/models` and `POST /v1/chat/completions` perfectly and returns 404 for all of the rest — so it passes a casual smoke test and then fails at the first dispatch.",
            "A proxy without a database will still serve `GET /v1/models` and `POST /v1/chat/completions`, but every key-management route returns 404 — enough to look healthy until the first epic starts.",
        )
        .replace(
            "**The proxy must serve every model alias the persona registry names.**",
            "**Every model alias named in the persona registry must be reachable through the proxy.**",
        )
        .replace(
            "Install the published distribution. The PyPI name is `ergane-cli`; the command it puts on your `PATH` is `ergane`.",
            "For normal use, install the package from PyPI (`ergane-cli`), which installs the `ergane` command.",
        )
        .replace(
            "Install from a checkout, in editable mode.",
            "For development, clone the repository and install in editable mode.",
        )
        .replace(
            "The two paths resolve the persona registry from different places.",
            "The two install paths use different personas.yaml locations.",
        )
    )
    missing = missing_readme_concepts(reworded)
    assert not missing, (
        "a reworded but equivalent setup guide was rejected; the guards are too "
        f"literal-string keyed: {missing}"
    )
