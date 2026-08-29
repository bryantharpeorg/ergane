"""What a target repo's `factory.yaml` must say, and what happens when it doesn't.

The manifest is the only place the factory learns what "green" means for a repo
(D-009: declared, never auto-detected), so this module's failure mode matters more
than its success one. A verifier that shrugged at a malformed manifest — no gates
found, therefore nothing failed, therefore PASS — would hand out passing verdicts
for repos it never tested. That is why every rule in contracts/factory-yaml.md is
asserted twice here: once as "the load refuses it", and once as "the refusal
becomes a `CONFIG_ERROR` gate result", which is the shape the verdict truth table
reads and fails on (data-model.md). There is deliberately no third path.

Three properties carry the weight:

- **Rejection is total and never silent.** Every row of the contract's validation
  table gets at least one fixture (`test_rejection_table_covers_every_contract_rule`
  enforces that), each fixture is well-formed except for the one defect under
  test, and `config_error_result` maps all of them to the same single-result shape
  — `name="config"`, `status=CONFIG_ERROR`, no exit code to read.
- **Messages are for an operator holding a broken file.** `.rule` is the stable
  slug tests and code branch on; the rendered message must name the source file,
  that slug, and the offending value or key verbatim (`repr`, so `'1'` the string
  is distinguishable from `1` the integer — precisely the mistake YAML invites).
  A message that said only "invalid manifest" would be a support ticket.
- **Declaration order is the operator's.** `gates` keeps the order the file wrote,
  because the runner executes gates in that order (T014) and cheapest-first is a
  choice the repo makes. Normalising to the canonical `test`/`lint`/`typecheck`
  order would quietly spend 600s on a type check the linter would have caught.

Two boundaries are drawn here on purpose:

- Bools are not integers. YAML's `true` is Python's `True`, and `True == 1`, so
  `version: true` would sail through a naive `== 1` check; likewise a timeout of
  `true` is not a positive int. Both are fixtures.
- Nothing in this module executes anything. Timeout *defaults* (600s for a gate
  with no entry) belong to the runner, not the parser: `timeouts` stays sparse
  exactly as written, so the runner can tell "declared 600" from "not declared".

Amended by 005 (research R11): an optional top-level `standards` key naming the
repo's coding-standards document, so an agent attempt can be told to read and
obey it (spec 005 FR-006) without relying on any one agent's auto-loaded context
file. It is additive and optional, so the schema stays `version: 1` — a version
bump for one optional key would force every target repo to migrate for nothing.
The key follows this module's existing rule for optional keys: declared means
declared, so a blank, null, or non-string value is a defect rather than a
shrug. Only the *shape* is checked here; whether the file exists is checked at
dispatch, in `prepare_worktree`, because that is where a worktree exists to look
in — the parser stays pure.

Written before `factory/verify/factory_yaml.py` exists (T012 precedes T017):
until the module lands, every test here fails at import.
"""

from __future__ import annotations

import textwrap
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from factory.verify.factory_yaml import (
    MANIFEST_NAME,
    FactoryConfigError,
    config_error_result,
    load_factory_config,
    load_factory_config_with_name,
    parse_factory_config,
    resolve_manifest_path,
)
import json
import subprocess
import sys

from factory.verify.models import FactoryConfig, GateResult, GateStatus, VerificationConfig


def _yaml(text: str) -> str:
    """Left-align an indented literal so a fixture reads like the file it is."""
    return textwrap.dedent(text).lstrip("\n")


#: The schema-v1 example from contracts/factory-yaml.md, comments and all — the
#: manifest an operator copies out of the contract must parse as written.
CONTRACT_EXAMPLE = _yaml(
    """
    version: 1                      # REQUIRED — integer literal 1
    runtime: bwrap                  # REQUIRED — supported sandbox backend name.
    gates:                          # REQUIRED — at least one key
      test: "uv run pytest -q"      # each value: non-empty string, run via `bash -c`
      lint: "uv run ruff check ."   #   with cwd = the node worktree
      typecheck: "uv run mypy ."
    timeouts:                       # OPTIONAL — seconds, per gate name
      test: 600                     # any gate not listed defaults to 600
    """
)

#: One slug per row of the contract's validation table. The slugs are the stable
#: identity of a rule — the message wording may improve, `.rule` may not drift.
CONTRACT_RULES = frozenset(
    {
        "missing_manifest",  # file exists at <worktree>/factory.yaml
        "malformed_yaml",  # YAML parses to a mapping
        "version",  # version present and == 1
        "runtime",  # runtime non-empty string
        "gates",  # gates mapping, known keys, >= 1 entry
        "gate_command",  # each gate command a non-empty string
        "timeouts",  # timeouts keys declared, values positive int
        "unknown_key",  # no unknown top-level keys
        "standards",  # optional; when declared, a non-empty string path (005 R11)
        "landing_branch",  # optional; when declared, a non-empty string branch (020 US1)
    }
)


# Acceptance ------------------------------------------------------------------


def test_contract_example_parses_to_the_declared_config() -> None:
    """The example in the contract is the acceptance case, field for field."""
    config = parse_factory_config(CONTRACT_EXAMPLE)

    assert config == FactoryConfig(
        version=1,
        runtime="bwrap",
        gates={
            "test": "uv run pytest -q",
            "lint": "uv run ruff check .",
            "typecheck": "uv run mypy .",
        },
        timeouts={"test": 600},
        landing_branch="main",
    )


def test_gate_declaration_order_is_preserved() -> None:
    """Gates run in declaration order, so the parser may not normalise it.

    A repo that puts `lint` first is buying fast failure; sorting the mapping into
    the canonical order would spend a full test run before the lint that would
    have failed in two seconds.
    """
    config = parse_factory_config(
        _yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              lint: "uv run ruff check ."
              typecheck: "uv run mypy ."
              test: "uv run pytest -q"
            """
        )
    )

    assert list(config.gates) == ["lint", "typecheck", "test"]


def test_timeouts_are_optional_and_stay_sparse() -> None:
    """No `timeouts` block is not "every gate is 600" — it is "nothing declared".

    The 600s default is the runner's (`VerificationConfig.gate_timeout_s`), and
    keeping the mapping sparse is what lets it stay one knob instead of a value
    baked into every parsed manifest.
    """
    config = parse_factory_config(
        _yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
            """
        )
    )

    assert config.timeouts == {}


def test_a_single_gate_is_enough() -> None:
    """`gates` needs one entry, not all three — most repos have no typecheck."""
    config = parse_factory_config(
        _yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              test: "npm test"
            timeouts:
              test: 90
            """
        )
    )

    assert config.gates == {"test": "npm test"}
    assert config.timeouts == {"test": 90}


def test_load_reads_the_manifest_from_disk(tmp_path: Path) -> None:
    path = tmp_path / MANIFEST_NAME
    path.write_text(CONTRACT_EXAMPLE, encoding="utf-8")

    assert load_factory_config(path) == parse_factory_config(CONTRACT_EXAMPLE)


def test_manifest_name_is_the_committed_filename() -> None:
    """The runner composes `<worktree>/ergane.yaml` from this constant (040/US1)."""
    assert MANIFEST_NAME == "ergane.yaml"


# Standards (005 research R11) -------------------------------------------------


def test_standards_is_optional_and_absent_reads_as_none() -> None:
    """Most repos declare no standards document, and that is not a defect.

    Absent has to be distinguishable from declared, because prompt assembly
    emits the read-and-obey directive *iff* the key was declared — `None` is the
    signal that there is nothing to point the agent at.
    """
    config = parse_factory_config(CONTRACT_EXAMPLE)

    assert config.standards is None


def test_standards_records_the_declared_path() -> None:
    """The path is recorded verbatim: it is resolved against the worktree later.

    Nothing here touches a filesystem — a declared file that is missing fails
    the dispatch in `prepare_worktree`, where a worktree exists to look in.
    """
    config = parse_factory_config(
        _yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
            standards: .specify/memory/constitution.md
            """
        )
    )

    assert config.standards == ".specify/memory/constitution.md"


def test_standards_does_not_bump_the_schema_version() -> None:
    """Additive and optional, so a repo already on v1 adopts it by adding a line.

    A `version: 2` for one optional key would force every target repo to migrate
    for nothing — so the manifest that declares `standards` is still a v1
    manifest, and every other field parses exactly as it did without it.
    """
    with_standards = parse_factory_config(
        CONTRACT_EXAMPLE + "standards: docs/STANDARDS.md\n"
    )
    without = parse_factory_config(CONTRACT_EXAMPLE)

    assert with_standards.version == 1
    assert with_standards.standards == "docs/STANDARDS.md"
    assert with_standards == FactoryConfig(
        version=without.version,
        runtime=without.runtime,
        gates=without.gates,
        timeouts=without.timeouts,
        standards="docs/STANDARDS.md",
    )


def test_standards_survives_a_round_trip_from_disk(tmp_path: Path) -> None:
    """Ergane's own manifest is this shape (T029), and it is loaded, not parsed."""
    path = tmp_path / MANIFEST_NAME
    path.write_text(
        _yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
            standards: .specify/memory/constitution.md
            """
        ),
        encoding="utf-8",
    )

    assert load_factory_config(path).standards == ".specify/memory/constitution.md"


# Landing branch (020 US1) ----------------------------------------------------


def test_landing_branch_is_optional_and_absent_defaults_to_main() -> None:
    """A manifest that does not declare a landing branch keeps today's behaviour.

    Absent means 'main', so no existing target repository is required to change.
    """
    config = parse_factory_config(CONTRACT_EXAMPLE)

    assert config.landing_branch == "main"


def test_landing_branch_records_the_declared_name() -> None:
    """The declared branch is recorded verbatim; readers resolve it later."""
    config = parse_factory_config(
        _yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
            landing_branch: ergane-buildout
            """
        )
    )

    assert config.landing_branch == "ergane-buildout"


def test_landing_branch_does_not_bump_the_schema_version() -> None:
    """Additive and optional, so a repo already on v1 adopts it by adding a line."""
    with_branch = parse_factory_config(
        CONTRACT_EXAMPLE + "landing_branch: ergane-buildout\n"
    )
    without = parse_factory_config(CONTRACT_EXAMPLE)

    assert with_branch.version == 1
    assert with_branch.landing_branch == "ergane-buildout"
    assert with_branch == FactoryConfig(
        version=without.version,
        runtime=without.runtime,
        gates=without.gates,
        timeouts=without.timeouts,
        landing_branch="ergane-buildout",
    )


def test_landing_branch_rejects_empty_string() -> None:
    """Declared means declared: an empty string is not a default request."""
    text = _yaml(
        """
        version: 1
        runtime: bwrap
        gates:
          test: "uv run pytest -q"
        landing_branch: ""
        """
    )

    with pytest.raises(FactoryConfigError) as excinfo:
        parse_factory_config(text)

    assert excinfo.value.rule == "landing_branch"
    assert "''" in str(excinfo.value)


def test_landing_branch_rejects_whitespace_only() -> None:
    """A whitespace-only branch name is the same mistake as an empty one."""
    text = _yaml(
        """
        version: 1
        runtime: bwrap
        gates:
          test: "uv run pytest -q"
        landing_branch: "   "
        """
    )

    with pytest.raises(FactoryConfigError) as excinfo:
        parse_factory_config(text)

    assert excinfo.value.rule == "landing_branch"


def test_landing_branch_rejects_null() -> None:
    """`landing_branch:` with no value parses to None and must fail loudly."""
    text = _yaml(
        """
        version: 1
        runtime: bwrap
        gates:
          test: "uv run pytest -q"
        landing_branch:
        """
    )

    with pytest.raises(FactoryConfigError) as excinfo:
        parse_factory_config(text)

    assert excinfo.value.rule == "landing_branch"
    assert "None" in str(excinfo.value)


def test_landing_branch_rejects_non_string() -> None:
    """A non-string value is a type confusion the same rule must refuse."""
    text = _yaml(
        """
        version: 1
        runtime: bwrap
        gates:
          test: "uv run pytest -q"
        landing_branch: true
        """
    )

    with pytest.raises(FactoryConfigError) as excinfo:
        parse_factory_config(text)

    assert excinfo.value.rule == "landing_branch"
    assert "True" in str(excinfo.value)


def test_landing_branch_survives_a_round_trip_from_disk(tmp_path: Path) -> None:
    """A declared landing branch is loadable from disk as well as from a string."""
    path = tmp_path / MANIFEST_NAME
    path.write_text(
        _yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
            landing_branch: some-branch
            """
        ),
        encoding="utf-8",
    )

    assert load_factory_config(path).landing_branch == "some-branch"


# Ergane's own manifest (005 T029) --------------------------------------------


#: The repository root: `tests/` sits directly beneath it.
REPO_ROOT = Path(__file__).resolve().parents[1]

#: The module path used by the CLI: `sys.executable -m factory.verify.factory_yaml`.
CLI_MODULE = "factory.verify.factory_yaml"

#: The rejection exit code US1 exposes as `PARSE_CLI_REJECTED`.
CLI_REJECTED = 65


def _run_cli(*args: str, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    """Run the parser CLI as a real subprocess and return its completed process."""
    return subprocess.run(
        [sys.executable, "-m", CLI_MODULE, *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def test_erganes_own_manifest_loads() -> None:
    """This repo is the factory's first target (D-024), so it declares its gates.

    The crossover epic dispatches nodes against Ergane itself, and every one of
    them asks this file what "green" means and what to obey. A manifest that
    only *looked* right would surface as a `CONFIG_ERROR` verdict on the first
    live node, hours in — so the file is loaded here, from disk, exactly as the
    gate runner will load it out of a worktree.

    This test asserts validity and documented operator fact, never the
    operator's choices (121 FR-001/FR-002): the `version` assertion this test
    once carried named a schema version, which is a value the operator is
    entitled to choose, and its presence refused an operator-declared v2
    manifest on every node's gate (the fourth-and-fifth recurrence of
    `ci/test-suite-pins-the-operator-dial`). The load itself stays — trap 1:
    this is the seconds-fast catch of a stale `standards` path before a live
    dispatch spends hours finding it.
    """
    config = load_factory_config(REPO_ROOT / MANIFEST_NAME)

    assert config.runtime
    assert config.gates["test"] == "uv run pytest -q"
    assert config.standards == ".specify/memory/constitution.md"
    # 020-US1 landed the key; the operator declared it afterwards, which is the
    # only order that works — the config gate parses a node's manifest with the
    # worker's installed parser, so a story declaring this key in its own
    # worktree is refused at CONFIG_ERROR before any gate command runs (020's
    # T012, and the four attempts that proved it). This line therefore asserts
    # an operator action, not a node's: it moved from "main" to the declared
    # branch on 2026-08-09, after US1 merged at 438cfd0 and the worker restarted.
    assert config.landing_branch == "ergane-buildout"


def test_erganes_declared_standards_document_exists() -> None:
    """`prepare_worktree` refuses to dispatch when the declared file is absent.

    The parser checks shape only (R11); existence is a question about a worktree.
    This repo *is* the worktree the crossover clones, so the one place that can
    catch a stale path before a live dispatch does is here.
    """
    config = load_factory_config(REPO_ROOT / MANIFEST_NAME)
    assert config.standards is not None

    assert (REPO_ROOT / config.standards).is_file()


# Rejection table (contracts/factory-yaml.md) ---------------------------------


@dataclass(frozen=True)
class Rejection:
    """One malformed manifest: well-formed everywhere except the defect named."""

    id: str
    text: str
    rule: str
    #: Substrings the message must contain — the offending value or key as the
    #: operator will see it, `repr`-rendered so `'1'` != `1`.
    names: tuple[str, ...] = field(default=())


REJECTIONS: list[Rejection] = [
    Rejection(
        id="unparseable-yaml",
        text=_yaml(
            """
            version: 1
            runtime: bwrap
            gates: [unclosed
            """
        ),
        rule="malformed_yaml",
    ),
    Rejection(
        id="document-is-a-sequence",
        text=_yaml(
            """
            - version: 1
            - runtime: bwrap
            """
        ),
        rule="malformed_yaml",
    ),
    Rejection(
        id="document-is-a-scalar",
        text="this repo has no factory manifest yet\n",
        rule="malformed_yaml",
    ),
    Rejection(
        id="document-is-empty",
        text="",
        rule="malformed_yaml",
    ),
    Rejection(
        id="document-is-comments-only",
        text="# TODO: fill this in\n",
        rule="malformed_yaml",
    ),
    Rejection(
        id="version-missing",
        text=_yaml(
            """
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
            """
        ),
        rule="version",
    ),
    Rejection(
        id="version-unsupported",
        text=_yaml(
            """
            version: 3
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
            """
        ),
        rule="version",
        names=("3",),
    ),
    Rejection(
        id="version-is-a-string",
        text=_yaml(
            """
            version: "1"
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
            """
        ),
        rule="version",
        names=("'1'",),
    ),
    Rejection(
        id="version-is-a-bool",
        text=_yaml(
            """
            version: true
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
            """
        ),
        rule="version",
        names=("True",),
    ),
    Rejection(
        id="runtime-missing",
        text=_yaml(
            """
            version: 1
            gates:
              test: "uv run pytest -q"
            """
        ),
        rule="runtime",
    ),
    Rejection(
        id="runtime-empty",
        text=_yaml(
            """
            version: 1
            runtime: ""
            gates:
              test: "uv run pytest -q"
            """
        ),
        rule="runtime",
        names=("''",),
    ),
    Rejection(
        id="runtime-not-a-string",
        text=_yaml(
            """
            version: 1
            runtime: 311
            gates:
              test: "uv run pytest -q"
            """
        ),
        rule="runtime",
        names=("311",),
    ),
    Rejection(
        id="gates-missing",
        text=_yaml(
            """
            version: 1
            runtime: bwrap
            """
        ),
        rule="gates",
    ),
    Rejection(
        id="gates-empty",
        text=_yaml(
            """
            version: 1
            runtime: bwrap
            gates: {}
            """
        ),
        rule="gates",
    ),
    Rejection(
        id="gates-not-a-mapping",
        text=_yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              - "uv run pytest -q"
            """
        ),
        rule="gates",
    ),
    Rejection(
        id="gates-unknown-name",
        text=_yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
              build: "make all"
            """
        ),
        rule="gates",
        names=("'build'", "test", "lint", "typecheck"),
    ),
    Rejection(
        id="gate-command-empty",
        text=_yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
              lint: ""
            """
        ),
        rule="gate_command",
        names=("'lint'", "''"),
    ),
    Rejection(
        id="gate-command-whitespace-only",
        text=_yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              lint: "   "
            """
        ),
        rule="gate_command",
        names=("'lint'",),
    ),
    Rejection(
        id="gate-command-not-a-string",
        text=_yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              test: 7
            """
        ),
        rule="gate_command",
        names=("'test'", "7"),
    ),
    Rejection(
        id="gate-command-null",
        text=_yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              test:
            """
        ),
        rule="gate_command",
        names=("'test'", "None"),
    ),
    Rejection(
        id="unknown-top-level-key",
        text=_yaml(
            """
            version: 1
            runtime: bwrap
            image: python:3.11-bookworm
            gates:
              test: "uv run pytest -q"
            """
        ),
        rule="unknown_key",
        names=("'image'",),
    ),
    Rejection(
        id="timeouts-not-a-mapping",
        text=_yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
            timeouts: 900
            """
        ),
        rule="timeouts",
        names=("900",),
    ),
    Rejection(
        id="timeouts-for-undeclared-gate",
        text=_yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
            timeouts:
              lint: 60
            """
        ),
        rule="timeouts",
        names=("'lint'",),
    ),
    Rejection(
        id="timeout-zero",
        text=_yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
            timeouts:
              test: 0
            """
        ),
        rule="timeouts",
        names=("'test'", "0"),
    ),
    Rejection(
        id="timeout-negative",
        text=_yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
            timeouts:
              test: -5
            """
        ),
        rule="timeouts",
        names=("'test'", "-5"),
    ),
    Rejection(
        id="timeout-is-a-string",
        text=_yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
            timeouts:
              test: "600"
            """
        ),
        rule="timeouts",
        names=("'test'", "'600'"),
    ),
    Rejection(
        id="timeout-is-a-bool",
        text=_yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
            timeouts:
              test: true
            """
        ),
        rule="timeouts",
        names=("'test'", "True"),
    ),
    Rejection(
        id="timeout-is-a-float",
        text=_yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
            timeouts:
              test: 1.5
            """
        ),
        rule="timeouts",
        names=("'test'", "1.5"),
    ),
    Rejection(
        id="standards-empty",
        text=_yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
            standards: ""
            """
        ),
        rule="standards",
        names=("''",),
    ),
    Rejection(
        id="standards-whitespace-only",
        text=_yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
            standards: "   "
            """
        ),
        rule="standards",
    ),
    Rejection(
        id="standards-null",
        text=_yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
            standards:
            """
        ),
        rule="standards",
        names=("None",),
    ),
    Rejection(
        id="standards-not-a-string",
        text=_yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
            standards: 42
            """
        ),
        rule="standards",
        names=("42",),
    ),
    Rejection(
        id="standards-is-a-sequence",
        text=_yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
            standards:
              - docs/STANDARDS.md
              - CONTRIBUTING.md
            """
        ),
        rule="standards",
        names=("docs/STANDARDS.md",),
    ),
    Rejection(
        id="landing-branch-empty",
        text=_yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
            landing_branch: ""
            """
        ),
        rule="landing_branch",
        names=("''",),
    ),
    Rejection(
        id="landing-branch-whitespace-only",
        text=_yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
            landing_branch: "   "
            """
        ),
        rule="landing_branch",
    ),
    Rejection(
        id="landing-branch-null",
        text=_yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
            landing_branch:
            """
        ),
        rule="landing_branch",
        names=("None",),
    ),
    Rejection(
        id="landing-branch-not-a-string",
        text=_yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
            landing_branch: true
            """
        ),
        rule="landing_branch",
        names=("True",),
    ),
]

REJECTION_IDS = [case.id for case in REJECTIONS]


def test_rejection_table_covers_every_contract_rule() -> None:
    """The table below is the contract's table; a new rule needs a new fixture.

    `missing_manifest` is the one rule with no text fixture — it is about a file
    that isn't there — and is asserted in its own test.
    """
    covered = {case.rule for case in REJECTIONS} | {"missing_manifest"}

    assert covered == CONTRACT_RULES


@pytest.mark.parametrize("case", REJECTIONS, ids=REJECTION_IDS)
def test_rejects_and_names_the_violated_rule(case: Rejection) -> None:
    with pytest.raises(FactoryConfigError) as excinfo:
        parse_factory_config(case.text)

    error = excinfo.value
    assert error.rule == case.rule
    message = str(error)
    assert MANIFEST_NAME in message, "the message must say which file to go fix"
    assert case.rule in message, "the message must name the rule that was violated"
    for token in case.names:
        assert token in message, f"message must name {token!r}: {message!r}"


@pytest.mark.parametrize("case", REJECTIONS, ids=REJECTION_IDS)
def test_every_rejection_becomes_one_config_error_gate(case: Rejection) -> None:
    """The refusal has to arrive as gate *data*, or the verdict never sees it.

    `CONFIG_ERROR` is a `GateStatus` rather than an escaping exception precisely
    so the truth table fails the verification (data-model.md) instead of some
    caller treating "no gates ran" as "no gates failed".
    """
    with pytest.raises(FactoryConfigError) as excinfo:
        parse_factory_config(case.text)

    result = config_error_result(excinfo.value)

    assert isinstance(result, GateResult)
    assert result.name == "config"
    assert result.status is GateStatus.CONFIG_ERROR
    assert result.exit_code is None
    assert result.command == ""
    assert result.duration_s == 0.0
    assert str(excinfo.value) in result.output_tail


def test_source_label_appears_in_messages() -> None:
    """Callers holding a path label the parse with it, so the error names it."""
    with pytest.raises(FactoryConfigError) as excinfo:
        parse_factory_config("version: 3\n", source="/repos/target/factory.yaml")

    assert "/repos/target/factory.yaml" in str(excinfo.value)


# Missing / unreadable manifest -----------------------------------------------


def test_missing_manifest_is_a_config_error_naming_the_path(tmp_path: Path) -> None:
    path = tmp_path / MANIFEST_NAME

    with pytest.raises(FactoryConfigError) as excinfo:
        load_factory_config(path)

    assert excinfo.value.rule == "missing_manifest"
    assert str(path) in str(excinfo.value)
    assert config_error_result(excinfo.value).status is GateStatus.CONFIG_ERROR


def test_unreadable_manifest_is_a_config_error_not_an_oserror(tmp_path: Path) -> None:
    """A directory where the manifest should be must not raise `IsADirectoryError`.

    Anything that escapes as a bare OS error crosses the activity boundary as an
    unexpected failure instead of a recorded FAIL, and the attempt loses its
    evidence.
    """
    path = tmp_path / MANIFEST_NAME
    path.mkdir()

    with pytest.raises(FactoryConfigError) as excinfo:
        load_factory_config(path)

    assert excinfo.value.rule == "missing_manifest"


def test_undecodable_manifest_is_malformed(tmp_path: Path) -> None:
    path = tmp_path / MANIFEST_NAME
    path.write_bytes(b"version: 1\nruntime: \xff\xfe\n")

    with pytest.raises(FactoryConfigError) as excinfo:
        load_factory_config(path)

    assert excinfo.value.rule == "malformed_yaml"


def test_load_errors_name_the_file_they_came_from(tmp_path: Path) -> None:
    path = tmp_path / MANIFEST_NAME
    path.write_text(
        _yaml(
            """
            version: 3
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
            """
        ),
        encoding="utf-8",
    )

    with pytest.raises(FactoryConfigError) as excinfo:
        load_factory_config(path)

    assert excinfo.value.rule == "version"
    assert str(path) in str(excinfo.value)


# CLI (026 US1) ---------------------------------------------------------------


def test_cli_accepts_a_valid_manifest_and_emits_config_json(tmp_path: Path) -> None:
    """The parser can be asked from a subprocess: accepted means exit 0 + JSON.

    Spec US1-S1.  Must fail until `factory.verify.factory_yaml` gains a `__main__`
    block; today the module runs, prints nothing, and exits 0.
    """
    path = tmp_path / MANIFEST_NAME
    path.write_text(CONTRACT_EXAMPLE, encoding="utf-8")

    expected = parse_factory_config(CONTRACT_EXAMPLE)

    result = _run_cli(str(path))

    assert result.returncode == 0, f"unexpected failure: {result.stderr}"
    parsed = json.loads(result.stdout)
    assert parsed["gates"] == expected.gates
    assert parsed["timeouts"] == expected.timeouts


def test_cli_rejects_unknown_top_level_key_with_distinguished_code(tmp_path: Path) -> None:
    """Rejection uses the documented exit code and carries the error on stderr.

    Spec US1-S2.  The message must name the rule (`unknown_key`) and the source
    file, and stdout must carry no JSON.
    """
    path = tmp_path / MANIFEST_NAME
    path.write_text(
        _yaml(
            """
            version: 1
            runtime: bwrap
            image: python:3.11-bookworm
            gates:
              test: "uv run pytest -q"
            """
        ),
        encoding="utf-8",
    )

    result = _run_cli(str(path))

    assert result.returncode == CLI_REJECTED
    with pytest.raises(json.JSONDecodeError):
        json.loads(result.stdout)
    assert "unknown_key" in result.stderr
    assert str(path) in result.stderr


def test_cli_rejects_missing_manifest_path_with_no_traceback(tmp_path: Path) -> None:
    """A missing path is an ordinary rejection: no traceback, no JSON on stdout.

    Spec US1-S3.  The `load_factory_config` wrapper already turns an absent
    file into a `FactoryConfigError(rule="missing_manifest")`, so the CLI gets
    the right shape for free.
    """
    missing = tmp_path / MANIFEST_NAME

    result = _run_cli(str(missing))

    assert result.returncode == CLI_REJECTED
    with pytest.raises(json.JSONDecodeError):
        json.loads(result.stdout)
    assert "missing_manifest" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_additivity_and_constants_preserve_library_behavior() -> None:
    """The CLI entry point adds behaviour; it does not change the library API.

    Regression guard for spec US1-S4.  Fails only if the implementation over-
    reaches into `parse_factory_config`, `load_factory_config`, or the module's
    public constants.
    """
    import factory.verify.factory_yaml as factory_yaml

    assert factory_yaml.PARSE_CLI_OK == 0
    assert factory_yaml.PARSE_CLI_REJECTED == CLI_REJECTED

    # Existing library entry points keep their signatures.
    import inspect

    assert "source" in inspect.signature(parse_factory_config).parameters
    assert "source" in inspect.signature(load_factory_config).parameters


# 040/US1 manifest rename: resolution, deprecation, and no literal readers -------


MANIFEST_CONTENT = _yaml(
    """
    version: 1
    runtime: bwrap
    gates:
      test: "uv run pytest -q"
    """
)


def test_ergane_yaml_only_loads(tmp_path: Path) -> None:
    """US1-S1: a repo with only `ergane.yaml` parses like `factory.yaml` does today."""
    repo = tmp_path / "ergane-only"
    repo.mkdir()
    (repo / "ergane.yaml").write_text(MANIFEST_CONTENT, encoding="utf-8")

    config, resolved_name = load_factory_config_with_name(repo)

    assert resolved_name == "ergane.yaml"
    assert config == parse_factory_config(MANIFEST_CONTENT, source="ergane.yaml")


def test_factory_yaml_only_loads_and_deprecates(tmp_path: Path) -> None:
    """US1-S2: a repo with only `factory.yaml` still loads and warns once by name."""
    repo = tmp_path / "factory-only"
    repo.mkdir()
    (repo / "factory.yaml").write_text(MANIFEST_CONTENT, encoding="utf-8")

    with warnings.catch_warnings(record=True) as warning_list:
        warnings.simplefilter("always", DeprecationWarning)
        import factory.verify.factory_yaml as factory_yaml

        factory_yaml._DEPRECATED_LEGACY_NAME = None
        config, resolved_name = load_factory_config_with_name(repo)

    assert resolved_name == "factory.yaml"
    assert config == parse_factory_config(MANIFEST_CONTENT, source="factory.yaml")
    deprecation_warnings = [w for w in warning_list if issubclass(w.category, DeprecationWarning)]
    assert len(deprecation_warnings) == 1, "deprecation must be emitted exactly once"
    message = str(deprecation_warnings[0].message)
    assert "factory.yaml" in message
    assert "rename" in message.lower() or "deprecated" in message.lower()
    assert "ergane.yaml" in message


def test_both_manifests_ergane_wins_and_ignored_file_is_named(tmp_path: Path) -> None:
    """US1-S3: when both exist, `ergane.yaml` wins and the ignored file is named."""
    repo = tmp_path / "both"
    repo.mkdir()
    (repo / "ergane.yaml").write_text(MANIFEST_CONTENT, encoding="utf-8")
    (repo / "factory.yaml").write_text(
        MANIFEST_CONTENT.replace("bwrap", "unsupported-backend"),
        encoding="utf-8",
    )

    with warnings.catch_warnings(record=True) as warning_list:
        warnings.simplefilter("always", DeprecationWarning)
        # Reset the module-level deprecation latch so this test observes the
        # warning regardless of test order, while still asserting the resolver
        # only warns once for a single repo.
        import factory.verify.factory_yaml as factory_yaml

        factory_yaml._DEPRECATED_LEGACY_NAME = None
        config, resolved_name = load_factory_config_with_name(repo)

    assert resolved_name == "ergane.yaml"
    assert config.runtime == "bwrap"
    deprecation_warnings = [w for w in warning_list if issubclass(w.category, DeprecationWarning)]
    assert len(deprecation_warnings) == 1
    message = str(deprecation_warnings[0].message)
    assert "factory.yaml" in message
    assert "ergane.yaml" in message
    assert "ignored" in message.lower()


def test_resolve_manifest_path_returns_legacy_for_factory_yaml(tmp_path: Path) -> None:
    """The resolver reports which name it chose so callers can act on it."""
    repo = tmp_path / "legacy"
    repo.mkdir()
    (repo / "factory.yaml").write_text(MANIFEST_CONTENT, encoding="utf-8")

    path, name = resolve_manifest_path(repo)

    assert name == "factory.yaml"
    assert path.name == "factory.yaml"


def test_resolve_manifest_path_returns_ergane_for_ergane_yaml(tmp_path: Path) -> None:
    repo = tmp_path / "preferred"
    repo.mkdir()
    (repo / "ergane.yaml").write_text(MANIFEST_CONTENT, encoding="utf-8")

    path, name = resolve_manifest_path(repo)

    assert name == "ergane.yaml"
    assert path.name == "ergane.yaml"


def test_resolve_manifest_path_prefers_ergane_yaml(tmp_path: Path) -> None:
    repo = tmp_path / "both-resolve"
    repo.mkdir()
    (repo / "ergane.yaml").write_text(MANIFEST_CONTENT, encoding="utf-8")
    (repo / "factory.yaml").write_text(MANIFEST_CONTENT, encoding="utf-8")

    path, name = resolve_manifest_path(repo)

    assert name == "ergane.yaml"
    assert path.name == "ergane.yaml"


def test_no_literal_factory_yaml_in_manifest_readers() -> None:
    """US1-S4/FR-004: every reader goes through the resolver, not a literal string.

    This is the same structural guard `test_gh_client.py` uses for
    `--delete-branch`: inspect the source of the modules that read the manifest
    and assert the forbidden literal is absent.
    """
    import inspect

    from factory.activities import agent_activities
    from factory.activities import merge_activities
    from factory.mergequeue import onboard
    from factory.verify import factory_yaml

    modules = (agent_activities, merge_activities, onboard, factory_yaml)
    forbidden = '"factory.yaml"'
    found = [
        f"{module.__name__}:{lineno}"
        for module in modules
        for lineno, line in enumerate(inspect.getsourcelines(module)[0], start=1)
        if forbidden in line
    ]
    assert not found, f"literal {forbidden!r} found in manifest readers: {found}"


# Schema v2 (023-composable-verification US1) ---------------------------------

#: The slugs that refuse a malformed v2 manifest. Each gets at least one fixture
#: below, and `test_v2_rejection_table_covers_every_rule` enforces that.
V2_CONTRACT_RULES = frozenset(
    {
        "unknown_key",  # v1 manifests that declare ladder:/verify:
        "unknown_ladder_key",
        "ladder_max_attempts_type",
        "ladder_max_attempts_min",
        "ladder_max_attempts_max",
        "ladder_max_judge_retries_type",
        "ladder_max_judge_retries_min",
        "ladder_max_judge_retries_max",
        "ladder_debugger_cycles_type",
        "ladder_debugger_cycles_min",
        "ladder_debugger_cycles_max",
        "ladder_escalation_timeout_s_type",
        "ladder_escalation_timeout_s_min",
        "ladder_escalation_timeout_s_max",
        "verify",
        "gate_name",
    }
)

#: A minimal v2 manifest that can be bent for refusal fixtures.
V2_MINIMAL = _yaml(
    """
    version: 2
    runtime: bwrap
    gates:
      unit: "uv run pytest -q"
    """
)


def test_v2_manifest_with_full_declaration_parses() -> None:
    """US1-S1: gates keep order, verify order is recorded, ladder caps parsed."""
    text = _yaml(
        """
        version: 2
        runtime: bwrap
        gates:
          unit: "uv run pytest -q"
          contract: "uv run pytest tests/contract -q"
        verify: [diff_check, gates, judge]
        ladder:
          max_attempts: 2
        """
    )

    config = parse_factory_config(text)

    assert config.version == 2
    assert list(config.gates) == ["unit", "contract"]
    assert config.verify_order == ("diff_check", "gates", "judge")
    assert config.ladder == VerificationConfig(max_attempts=2)


def test_v2_manifest_defaults_ladder_and_verify_order() -> None:
    """Absent `ladder:` and `verify:` mean today's defaults, including judge."""
    text = _yaml(
        """
        version: 2
        runtime: bwrap
        gates:
          unit: "uv run pytest -q"
        """
    )

    config = parse_factory_config(text)

    assert config.version == 2
    assert config.ladder == VerificationConfig()
    assert config.verify_order == ("gates", "diff_check", "judge")


@dataclass(frozen=True)
class V2Rejection:
    """One malformed v2 manifest: well-formed everywhere except the defect named."""

    id: str
    text: str
    rule: str
    names: tuple[str, ...] = field(default=())


V2_REJECTIONS: list[V2Rejection] = [
    V2Rejection(
        id="ladder-unknown-key",
        text=V2_MINIMAL + "ladder:\n  max_attempts: 3\n  retries: 1\n",
        rule="unknown_ladder_key",
        names=("'retries'",),
    ),
    V2Rejection(
        id="ladder-max-attempts-is-bool",
        text=V2_MINIMAL + "ladder:\n  max_attempts: true\n",
        rule="ladder_max_attempts_type",
        names=("'max_attempts'", "True"),
    ),
    V2Rejection(
        id="ladder-max-attempts-is-string",
        text=V2_MINIMAL + "ladder:\n  max_attempts: \"2\"\n",
        rule="ladder_max_attempts_type",
        names=("'max_attempts'", "'2'"),
    ),
    V2Rejection(
        id="ladder-max-attempts-below-floor",
        text=V2_MINIMAL + "ladder:\n  max_attempts: 0\n",
        rule="ladder_max_attempts_min",
        names=("'max_attempts'", "0"),
    ),
    V2Rejection(
        id="ladder-max-attempts-above-ceiling",
        text=V2_MINIMAL + "ladder:\n  max_attempts: 11\n",
        rule="ladder_max_attempts_max",
        names=("'max_attempts'", "11"),
    ),
    V2Rejection(
        id="ladder-max-judge-retries-is-bool",
        text=V2_MINIMAL + "ladder:\n  max_judge_retries: true\n",
        rule="ladder_max_judge_retries_type",
        names=("'max_judge_retries'", "True"),
    ),
    V2Rejection(
        id="ladder-max-judge-retries-below-floor",
        text=V2_MINIMAL + "ladder:\n  max_judge_retries: -1\n",
        rule="ladder_max_judge_retries_min",
        names=("'max_judge_retries'", "-1"),
    ),
    V2Rejection(
        id="ladder-max-judge-retries-above-ceiling",
        text=V2_MINIMAL + "ladder:\n  max_judge_retries: 11\n",
        rule="ladder_max_judge_retries_max",
        names=("'max_judge_retries'", "11"),
    ),
    V2Rejection(
        id="ladder-debugger-cycles-is-string",
        text=V2_MINIMAL + "ladder:\n  debugger_cycles: \"1\"\n",
        rule="ladder_debugger_cycles_type",
        names=("'debugger_cycles'", "'1'"),
    ),
    V2Rejection(
        id="ladder-debugger-cycles-below-floor",
        text=V2_MINIMAL + "ladder:\n  debugger_cycles: -1\n",
        rule="ladder_debugger_cycles_min",
        names=("'debugger_cycles'", "-1"),
    ),
    V2Rejection(
        id="ladder-debugger-cycles-above-ceiling",
        text=V2_MINIMAL + "ladder:\n  debugger_cycles: 4\n",
        rule="ladder_debugger_cycles_max",
        names=("'debugger_cycles'", "4"),
    ),
    V2Rejection(
        id="ladder-escalation-timeout-is-bool",
        text=V2_MINIMAL + "ladder:\n  escalation_timeout_s: true\n",
        rule="ladder_escalation_timeout_s_type",
        names=("'escalation_timeout_s'", "True"),
    ),
    V2Rejection(
        id="ladder-escalation-timeout-below-floor",
        text=V2_MINIMAL + "ladder:\n  escalation_timeout_s: 30\n",
        rule="ladder_escalation_timeout_s_min",
        names=("'escalation_timeout_s'", "30"),
    ),
    V2Rejection(
        id="ladder-escalation-timeout-above-ceiling",
        text=V2_MINIMAL + "ladder:\n  escalation_timeout_s: 90000\n",
        rule="ladder_escalation_timeout_s_max",
        names=("'escalation_timeout_s'", "90000"),
    ),
    V2Rejection(
        id="verify-empty",
        text=V2_MINIMAL + "verify: []\n",
        rule="verify",
        names=("empty",),
    ),
    V2Rejection(
        id="verify-duplicated",
        text=V2_MINIMAL + "verify: [gates, diff_check, gates]\n",
        rule="verify",
        names=("duplicate", "'gates'"),
    ),
    V2Rejection(
        id="verify-unknown-step",
        text=V2_MINIMAL + "verify: [gates, diff_check, smoke]\n",
        rule="verify",
        names=("unknown", "'smoke'"),
    ),
    V2Rejection(
        id="verify-missing-gates",
        text=V2_MINIMAL + "verify: [diff_check, judge]\n",
        rule="verify",
        names=("missing", "'gates'"),
    ),
    V2Rejection(
        id="verify-missing-diff-check",
        text=V2_MINIMAL + "verify: [gates, judge]\n",
        rule="verify",
        names=("missing", "'diff_check'"),
    ),
    V2Rejection(
        id="verify-judge-before-gates",
        text=V2_MINIMAL + "verify: [judge, diff_check, gates]\n",
        rule="verify",
        names=("before", "'judge'", "'gates'"),
    ),
    V2Rejection(
        id="verify-judge-before-diff-check",
        text=V2_MINIMAL + "verify: [gates, judge, diff_check]\n",
        rule="verify",
        names=("before", "'judge'", "'diff_check'"),
    ),
    V2Rejection(
        id="gate-name-is-judge",
        text=_yaml(
            """
            version: 2
            runtime: bwrap
            gates:
              judge: "uv run pytest -q"
            """
        ),
        rule="gate_name",
        names=("'judge'",),
    ),
    V2Rejection(
        id="gate-name-is-diff-check",
        text=_yaml(
            """
            version: 2
            runtime: bwrap
            gates:
              diff_check: "uv run pytest -q"
            """
        ),
        rule="gate_name",
        names=("'diff_check'",),
    ),
    V2Rejection(
        id="gate-name-is-gates",
        text=_yaml(
            """
            version: 2
            runtime: bwrap
            gates:
              gates: "uv run pytest -q"
            """
        ),
        rule="gate_name",
        names=("'gates'",),
    ),
    V2Rejection(
        id="gate-name-is-config",
        text=_yaml(
            """
            version: 2
            runtime: bwrap
            gates:
              config: "uv run pytest -q"
            """
        ),
        rule="gate_name",
        names=("'config'",),
    ),
    V2Rejection(
        id="v1-rejects-ladder",
        text=_yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
            ladder:
              max_attempts: 2
            """
        ),
        rule="unknown_key",
        names=("'ladder'",),
    ),
    V2Rejection(
        id="v1-rejects-verify",
        text=_yaml(
            """
            version: 1
            runtime: bwrap
            gates:
              test: "uv run pytest -q"
            verify: [gates, diff_check, judge]
            """
        ),
        rule="unknown_key",
        names=("'verify'",),
    ),
]

V2_REJECTION_IDS = [case.id for case in V2_REJECTIONS]


def test_v2_rejection_table_covers_every_rule() -> None:
    covered = {case.rule for case in V2_REJECTIONS}
    assert covered == V2_CONTRACT_RULES


@pytest.mark.parametrize("case", V2_REJECTIONS, ids=V2_REJECTION_IDS)
def test_v2_rejects_and_names_the_violated_rule(case: V2Rejection) -> None:
    with pytest.raises(FactoryConfigError) as excinfo:
        parse_factory_config(case.text)

    error = excinfo.value
    assert error.rule == case.rule
    message = str(error)
    assert MANIFEST_NAME in message
    assert case.rule in message
    for token in case.names:
        assert token in message, f"message must name {token!r}: {message!r}"


@pytest.mark.parametrize("case", V2_REJECTIONS, ids=V2_REJECTION_IDS)
def test_v2_every_rejection_becomes_one_config_error_gate(case: V2Rejection) -> None:
    with pytest.raises(FactoryConfigError) as excinfo:
        parse_factory_config(case.text)

    result = config_error_result(excinfo.value)

    assert isinstance(result, GateResult)
    assert result.name == "config"
    assert result.status is GateStatus.CONFIG_ERROR
    assert result.exit_code is None
    assert result.command == ""
    assert result.duration_s == 0.0
    assert str(excinfo.value) in result.output_tail


# v1 identity (023 US1-S2/S6; repointed by 121-US1) ---------------------------


#: The committed sample the v1 identity is frozen against (121 T007): the file
#: whose bytes are the parser regression fixture, named for the one condition it
#: demonstrates as its neighbours are. The operator's live manifest is *not*
#: assertable content — spec 121 FR-001/FR-002 — because the manifest is the
#: operator's file and freezing its parsed value reddens the gate every node
#: runs whenever the operator turns a dial. A sample nobody has a reason to
#: change can be frozen honestly.
V1_IDENTITY_SAMPLE = (
    REPO_ROOT / "tests" / "fixtures" / "target_repo" / "manifests" / "v1-sample.yaml"
)


def test_v1_identity_against_the_committed_sample() -> None:
    """The v1 parse-shape regression: the committed sample parses field for
    field to exactly the frozen shape.

    This was `test_v1_identity_against_erganes_own_manifest` and read this
    repository's live `ergane.yaml`; 121-US1 moved it onto the sample. The
    comparison is deliberately unchanged — the whole `FactoryConfig`, field for
    field (FR-007) — because it is the parser regression fixture spec 023's
    US1-S2/S6 put there, and a rewrite into spot assertions would let a v1
    default drift while every spot assert stayed green. What moved is the
    fixture: v1 semantics are frozen on committed bytes (FR-005) instead of on
    the operator's file, which no test may pin (FR-001/FR-002) and every node's
    gate runs against.

    `tests/test_121_manifest_is_not_a_fixture.py` holds the other half: the
    sample stays v1, and this test never points back at the operator's file.
    """
    config = load_factory_config(V1_IDENTITY_SAMPLE)

    assert config == FactoryConfig(
        version=1,
        runtime="bwrap",
        gates={
            "lint": "bash gates/lint.sh",
            "test": "bash gates/test.sh",
            "typecheck": "bash gates/typecheck.sh",
        },
        timeouts={"lint": 30},
        standards="docs/STANDARDS.md",
        ladder=VerificationConfig(),
        verify_order=("gates", "diff_check", "judge"),
    )
