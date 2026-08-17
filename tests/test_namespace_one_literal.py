"""051-US2: the default Temporal namespace is one fact, spelled once.

Before this story the product carried two answers to one question. The install
interview seeded `namespace = "ergane"`; the code fallback every unconfigured
command reached said `factory`. An operator who pressed enter through
`ergane install` declared one namespace and an unconfigured command used the
other, and on 2026-08-16 that created a live schedule in a namespace nobody had
named.

Three properties shape the tests below, and each exists because the obvious
version of the test would have passed on the broken tree:

- **Equality is not single-sourcing.** CPython interns identifier-like string
  constants, so two independently-written `"ergane"` literals in two modules are
  the *same object* — measured on this interpreter, not assumed. `assert seed is
  default` and `assert seed == default` therefore both pass on exactly the tree
  this story exists to fix. The only assertions that can tell the two apart are
  structural: what the source *spells*, and what it *imports*. That is why the
  sweep reads ASTs rather than values.

- **The sweep is held by path, and says so.** `ergane` is also this product's
  program name (`factory/cli/main.py`) and its config directory
  (`factory/controlplane/config.py`), so a package-wide scan for the value would
  report four sites with nothing to do with Temporal. The cost of holding it by
  path is that a namespace default introduced in a module nobody listed is not
  seen; `NAMESPACE_SITES` is the list, and adding a site is the maintenance this
  buys.

- **The sweep must be able to fail.** A parametrized sweep over an empty file
  list passes forever without asserting anything
  (`tests/test_final_sweep.py:644` is the precedent). Every path is asserted to
  be a file before it is parsed, so a stale path is a failure rather than a
  silent skip, and the anti-vacuity test below asserts the list is non-empty and
  names both modules the story is about (FR-009).

`scripts/ergane-env.sh` is deliberately untouched by this story (FR-012). It
exports `TEMPORAL_NAMESPACE=factory` for this repository's own worker, the
environment beats the default under 048's precedence, and that export is why
changing the constant moves nothing that is running. Every test here passes an
explicit `environ` mapping rather than reading the process environment, so none
of them measures that shell.
"""

from __future__ import annotations

import ast
from pathlib import Path

from factory.cli.install import BLANK_DOCUMENT
from factory.controlplane.resolve import DEFAULT_SOURCE, resolve_temporal_target
from factory.notify.service import (
    DEFAULT_TEMPORAL_NAMESPACE,
    TEMPORAL_NAMESPACE_ENV,
)

#: The shipped package. FR-006 is a claim about what ships, not about `tests/`.
PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "factory"

#: The one module allowed to spell the value. Every other site derives from it.
DEFINITION_SITE = "notify/service.py"

#: The same module as an importable name, for the derives-by-import assertion.
DEFINITION_MODULE = "factory.notify.service"

#: Every module that participates in the default Temporal namespace: the one
#: that defines it, the interview that seeds a config with it, and the three
#: that consume it. Paths are relative to `PACKAGE_ROOT`.
NAMESPACE_SITES = (
    "notify/service.py",
    "cli/install.py",
    "controlplane/resolve.py",
    "cli/env.py",
    "cli/nouns/build.py",
)

#: A declared namespace, distinct from every default so a crossed wire is
#: visible rather than accidentally correct.
DECLARED_NAMESPACE = "declared-namespace"
DECLARED_ADDRESS = "declared.temporal.test:7233"
OVERRIDE_NAMESPACE = "override-namespace"


def _site(relative: str) -> Path:
    """The absolute path of a swept site, asserted to exist before it is read.

    A path that has moved fails here. Without this, pointing the sweep at
    nothing would parse nothing, find nothing, and report green — the exact
    vacuity FR-009 is written against.
    """
    path = PACKAGE_ROOT / relative
    assert path.is_file(), f"{relative} moved; this sweep is pinned to a stale path"
    return path


def _parse(relative: str) -> ast.AST:
    path = _site(relative)
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _non_docstring_strings(tree: ast.AST) -> list[ast.Constant]:
    """Every string constant in `tree` that is not a docstring.

    Docstrings are excluded because prose that *names* the default — this
    module's own neighbours do — is documentation of the contract, not a second
    copy of it. Same exclusion, and same reason, as 048's connect-site guard.
    """
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body:
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                if isinstance(first.value.value, str):
                    docstrings.add(id(first.value))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def _write_config(tmp_path: Path, *, namespace: str) -> Path:
    """A complete, parseable config declaring `namespace`.

    All five blocks, since the parser requires all five, and both `address` and
    `namespace` under `temporal.mode = "external"`.
    """
    path = tmp_path / "config.toml"
    path.write_text(
        f"""\
version = 1

[llm]
mode = "gateway"
base_url = "http://declared.gateway.test/v1"
master_key_env = "DECLARED_KEY_VAR"

[memory]
backend = "none"

[temporal]
mode = "external"
address = "{DECLARED_ADDRESS}"
namespace = "{namespace}"

[telemetry]

[escalation]
adapter = "telegram"
chat_id_env = "DECLARED_CHAT_ID"
bot_token_env = "DECLARED_BOT_TOKEN"
""",
        encoding="utf-8",
    )
    return path


# --- T009 / US2-S1, US2-S4 — the sweep, and the assertion that it swept ------


def test_the_sweep_read_a_non_empty_file_list_naming_both_modules() -> None:
    """FR-009's anti-vacuity clause, as its own named test.

    Folded into the sweep it would be one `assert` among several and could be
    deleted without anything going red; standing alone, deleting it is visible
    in the diff. The two modules FR-006 is about are named literally, so a
    `NAMESPACE_SITES` that quietly loses one fails here.
    """
    assert NAMESPACE_SITES, "an empty site list asserts nothing"

    swept = {f"factory/{relative}" for relative in NAMESPACE_SITES}
    assert "factory/cli/install.py" in swept
    assert "factory/notify/service.py" in swept

    for relative in NAMESPACE_SITES:
        assert _site(relative).is_file()


def test_exactly_one_site_spells_the_default_temporal_namespace() -> None:
    """FR-006, US2-S1: one literal, and it is the definition.

    The value is imported rather than restated, so this counts occurrences of
    whatever the constant currently says. A future change of the value that
    forgot a derived site re-leaks here rather than passing because both copies
    moved together.
    """
    spelled: list[str] = []
    for relative in NAMESPACE_SITES:
        for node in _non_docstring_strings(_parse(relative)):
            if node.value == DEFAULT_TEMPORAL_NAMESPACE:
                spelled.append(f"factory/{relative}:{node.lineno}")

    assert len(spelled) == 1, spelled
    assert spelled[0].startswith(f"factory/{DEFINITION_SITE}:"), spelled


def test_no_site_binds_a_temporal_namespace_to_its_own_string_literal() -> None:
    """FR-006, US2-S4: the shape the defect actually had.

    `factory/cli/install.py` did not restate the *constant's* value — it
    restated the *seed's*, a different string, which is why a test counting
    occurrences of `DEFAULT_TEMPORAL_NAMESPACE` alone would have reported one
    literal on the broken tree and passed. What was wrong was a namespace bound
    to a constant in a module that is not the definition, whatever that constant
    reads, so that is what is asserted.
    """
    offenders: list[str] = []
    for relative in NAMESPACE_SITES:
        if relative == DEFINITION_SITE:
            continue
        for node in ast.walk(_parse(relative)):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values):
                if not (isinstance(key, ast.Constant) and key.value == "namespace"):
                    continue
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    offenders.append(f"factory/{relative}:{value.lineno}: {value.value!r}")

    assert offenders == []


def test_the_install_interview_imports_the_default_rather_than_restating_it() -> None:
    """FR-007's structural half: one source, asserted as an import.

    Value equality cannot carry this. `"ergane"` is identifier-like, so CPython
    interns it and two separate literals in two modules are one object — both
    `==` and `is` pass on the broken tree. An import is the only thing a
    re-introduced duplicate cannot fake.
    """
    imported = [
        alias.name
        for node in ast.walk(_parse("cli/install.py"))
        if isinstance(node, ast.ImportFrom)
        and (node.module or "") == DEFINITION_MODULE
        for alias in node.names
    ]

    assert "DEFAULT_TEMPORAL_NAMESPACE" in imported, imported
    # The two spellings of the definition site are kept honest against each
    # other, so a moved module cannot leave one of them silently stale.
    assert DEFINITION_MODULE.replace(".", "/") + ".py" == f"factory/{DEFINITION_SITE}"


# --- T010 / US2-S2 — the seed and an unconfigured resolution are one value ---


def test_an_unconfigured_resolution_yields_the_value_the_interview_seeds(
    tmp_path: Path,
) -> None:
    """FR-007: nothing declared, nothing exported, and the two agree.

    `environ={}` rather than `monkeypatch.delenv`: this repository's own shell
    exports `TEMPORAL_NAMESPACE=factory`, and a test that inherited it would
    read the export and be unable to tell `ergane` from `factory` — the
    mutation would be invisible to it.
    """
    missing = tmp_path / "config.toml"

    target = resolve_temporal_target(environ={}, config_path=missing)

    assert target.namespace == BLANK_DOCUMENT["temporal"]["namespace"]
    assert target.namespace == DEFAULT_TEMPORAL_NAMESPACE
    assert target.namespace_source == DEFAULT_SOURCE


def test_the_single_default_reads_ergane() -> None:
    """FR-011, decided by the operator on 2026-08-16.

    `factory` is this repository's own deployment name — the namespace its
    worker runs in and the one `scripts/ergane-env.sh` exports. A product
    default may not be one installation's proper noun, so the value is pinned
    here rather than left to whichever of the two literals survived the merge.
    """
    assert DEFAULT_TEMPORAL_NAMESPACE == "ergane"
    assert BLANK_DOCUMENT["temporal"]["namespace"] == "ergane"


# --- T011 / US2-S3 — 048's precedence, unchanged --------------------------


def test_a_declared_namespace_still_wins_over_the_single_default(
    tmp_path: Path,
) -> None:
    """FR-008: unifying the defaults must not disturb declaration-over-default.

    This pins behaviour that is already correct — a red-first version of it
    would mean 048's precedence was broken before this story started. Its teeth
    come from the mutation battery, where inverting `_one_of` turns it red.
    """
    config_path = _write_config(tmp_path, namespace=DECLARED_NAMESPACE)

    target = resolve_temporal_target(environ={}, config_path=config_path)

    assert target.namespace == DECLARED_NAMESPACE
    assert target.namespace_source == str(config_path)
    assert target.namespace != DEFAULT_TEMPORAL_NAMESPACE


def test_the_environment_still_wins_over_a_declared_namespace(
    tmp_path: Path,
) -> None:
    """FR-008's other half, and the reason FR-012 forbids touching the shell.

    The export beating the declaration is the same rule that makes the export
    beat the default, which is why this repository's worker keeps connecting to
    `factory` after the constant changes.
    """
    config_path = _write_config(tmp_path, namespace=DECLARED_NAMESPACE)

    target = resolve_temporal_target(
        environ={TEMPORAL_NAMESPACE_ENV: OVERRIDE_NAMESPACE},
        config_path=config_path,
    )

    assert target.namespace == OVERRIDE_NAMESPACE
    assert target.namespace_source == TEMPORAL_NAMESPACE_ENV
