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
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from factory.verify.factory_yaml import (
    MANIFEST_NAME,
    FactoryConfigError,
    config_error_result,
    load_factory_config,
    parse_factory_config,
)
from factory.verify.models import FactoryConfig, GateResult, GateStatus


def _yaml(text: str) -> str:
    """Left-align an indented literal so a fixture reads like the file it is."""
    return textwrap.dedent(text).lstrip("\n")


#: The schema-v1 example from contracts/factory-yaml.md, comments and all — the
#: manifest an operator copies out of the contract must parse as written.
CONTRACT_EXAMPLE = _yaml(
    """
    version: 1                      # REQUIRED — integer literal 1
    runtime: python:3.11-bookworm   # REQUIRED — container image reference (string).
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
    }
)


# Acceptance ------------------------------------------------------------------


def test_contract_example_parses_to_the_declared_config() -> None:
    """The example in the contract is the acceptance case, field for field."""
    config = parse_factory_config(CONTRACT_EXAMPLE)

    assert config == FactoryConfig(
        version=1,
        runtime="python:3.11-bookworm",
        gates={
            "test": "uv run pytest -q",
            "lint": "uv run ruff check .",
            "typecheck": "uv run mypy .",
        },
        timeouts={"test": 600},
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
            runtime: python:3.11-bookworm
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
            runtime: python:3.11-bookworm
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
            runtime: node:22-bookworm
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
    """The runner composes `<worktree>/factory.yaml` from this constant."""
    assert MANIFEST_NAME == "factory.yaml"


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
            runtime: python:3.11-bookworm
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
            runtime: python:3.11-bookworm
            gates:
              test: "uv run pytest -q"
            standards: .specify/memory/constitution.md
            """
        ),
        encoding="utf-8",
    )

    assert load_factory_config(path).standards == ".specify/memory/constitution.md"


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
            runtime: python:3.11-bookworm
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
            - runtime: python:3.11-bookworm
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
            runtime: python:3.11-bookworm
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
            version: 2
            runtime: python:3.11-bookworm
            gates:
              test: "uv run pytest -q"
            """
        ),
        rule="version",
        names=("2",),
    ),
    Rejection(
        id="version-is-a-string",
        text=_yaml(
            """
            version: "1"
            runtime: python:3.11-bookworm
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
            runtime: python:3.11-bookworm
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
            runtime: python:3.11-bookworm
            """
        ),
        rule="gates",
    ),
    Rejection(
        id="gates-empty",
        text=_yaml(
            """
            version: 1
            runtime: python:3.11-bookworm
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
            runtime: python:3.11-bookworm
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
            runtime: python:3.11-bookworm
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
            runtime: python:3.11-bookworm
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
            runtime: python:3.11-bookworm
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
            runtime: python:3.11-bookworm
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
            runtime: python:3.11-bookworm
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
            runtime: python:3.11-bookworm
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
            runtime: python:3.11-bookworm
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
            runtime: python:3.11-bookworm
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
            runtime: python:3.11-bookworm
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
            runtime: python:3.11-bookworm
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
            runtime: python:3.11-bookworm
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
            runtime: python:3.11-bookworm
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
            runtime: python:3.11-bookworm
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
            runtime: python:3.11-bookworm
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
            runtime: python:3.11-bookworm
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
            runtime: python:3.11-bookworm
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
            runtime: python:3.11-bookworm
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
            runtime: python:3.11-bookworm
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
        parse_factory_config("version: 2\n", source="/repos/target/factory.yaml")

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
            version: 2
            runtime: python:3.11-bookworm
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
