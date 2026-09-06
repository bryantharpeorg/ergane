"""A manifest may say a gate binds the boundary alone (128 US1).

A target repo declares its gates in `ergane.yaml`, and every one of them runs
at the boundary — `factory/verify/gates.py`'s `_run_gate_list_from_config`
iterates every entry in `gates` before a node opens a pull request. Whether the
forge's merge queue *also* requires a check of that name is the operator's
separate decision, and today the two are conflated: onboarding refuses a
repository whose landing branch requires no check for a declared gate, with a
blocking finding — which is how an operator who deliberately kept a gate off
the merge queue spent an 11h40m outage being told their repository was broken.

US1 is the schema half of the fix: a v2 manifest may declare
`boundary_only_gates:` — the gates that are meant to bind the boundary alone.
A sibling story (128 US2, not this module) threads the list into onboarding;
nothing downstream reads it yet, and this module holds the declaration to four
properties, one per acceptance scenario:

- **Declared means carried** (FR-001): the parsed config keeps the list, in the
  order the manifest wrote it — the same operator-owns-order rule the gate list
  itself follows.
- **A misspelled entry is a refusal, deliberately** (FR-002): an entry naming a
  gate the manifest does not declare exempts nothing while reading as though it
  exempts something, which is the exact failure mode this key exists to
  prevent. `_read_writes` already made this argument for its own keys; this
  reader reuses its wording rather than inventing a softer one. It is new
  strictness: no manifest could be refused for this before, because no reader
  knew the key at all.
- **Absence is today, exactly** (FR-003): a manifest that does not declare the
  key parses to what it parsed to before this story, field for field. Every
  manifest that exists is this manifest — both the v2 bodies and the v1 ones.
- **The key is v2-only, proven as a pair** (FR-004): one body, loaded twice.
  Under `version: 2` it parses and carries the list; under `version: 1` it is
  refused as an unknown top-level key, on the same path every other v2-only key
  is refused. The v1 half alone is true on today's tree, so only the pair can
  fail a diff that registered the key in the wrong tuple.

The remaining refusals are shape ones: a value that is not a list, and an entry
that is not a string, are refused at the same seam rather than iterated into
nonsense — a bare `boundary_only_gates: audit` would otherwise be read as the
letters of one word and refused for reasons that name none of them.
"""

from __future__ import annotations

import textwrap

import pytest

from factory.verify.factory_yaml import (
    MANIFEST_NAME,
    FactoryConfigError,
    parse_factory_config,
)
from factory.verify.models import FactoryConfig


def _yaml(text: str) -> str:
    """Left-align an indented literal so a fixture reads like the file it is."""
    return textwrap.dedent(text).lstrip("\n")


# --- T001 [US1-S1] declared means carried ------------------------------------


def test_a_v2_manifest_declaring_the_key_parses_and_carries_the_list() -> None:
    """US1-S1 / FR-001: beside a `gates:` block that declares `audit`, it parses."""
    text = _yaml(
        """
        version: 2
        runtime: bwrap
        gates:
          audit: "uv run pytest tests/audit -q"
          test: "uv run pytest -q"
        boundary_only_gates: [audit]
        """
    )

    config = parse_factory_config(text)

    assert config.boundary_only_gates == ("audit",)
    # The declaration sits beside the gates it names; the gates are untouched.
    assert list(config.gates) == ["audit", "test"]


def test_the_list_is_carried_in_the_order_the_manifest_wrote_it() -> None:
    """The operator's order is the evidence's order, as with `gates` itself."""
    text = _yaml(
        """
        version: 2
        runtime: bwrap
        gates:
          audit: "echo audit"
          lint: "echo lint"
          test: "echo test"
        boundary_only_gates: [test, audit]
        """
    )

    config = parse_factory_config(text)

    assert config.boundary_only_gates == ("test", "audit")


# --- T002 [US1-S2] an undeclared entry is a refusal --------------------------


def test_an_entry_naming_an_undeclared_gate_is_refused_naming_it() -> None:
    """US1-S2 / FR-002 — new strictness, deliberately.

    `typecheck` is spelled here the way the spec spells it: a gate the manifest
    does not declare, next to one it does. A misspelled entry must not read as
    an exemption while exempting nothing, so the refusal names the entry and
    says what *is* declared.
    """
    text = _yaml(
        """
        version: 2
        runtime: bwrap
        gates:
          test: "uv run pytest -q"
        boundary_only_gates: [typecheck]
        """
    )

    with pytest.raises(FactoryConfigError) as excinfo:
        parse_factory_config(text)

    error = excinfo.value
    assert error.rule == "boundary_only_gates"
    message = str(error)
    assert MANIFEST_NAME in message, "the message must say which file to go fix"
    assert "'typecheck'" in message, f"must name the entry: {message!r}"
    assert "does not declare as a gate" in message, f"must state the rule: {message!r}"
    assert "'test'" in message, f"must name what is declared: {message!r}"


@pytest.mark.parametrize(
    "declared",
    [
        "audit",
        "{audit: true}",
        "[audit, [audit]]",
    ],
    ids=["bare-string", "mapping", "unhashable-entry"],
)
def test_a_boundary_only_declaration_that_is_not_a_name_list_is_refused(
    declared: str,
) -> None:
    """A non-list value, or an entry that is not a string, is refused outright.

    Iterating a bare string would refuse the letters of one word — a refusal
    that names none of them — and an unhashable entry would escape as a
    `TypeError` instead of a `FactoryConfigError`. Both are refused at the same
    seam, under the same rule slug.
    """
    text = _yaml(
        f"""
        version: 2
        runtime: bwrap
        gates:
          audit: "echo audit"
        boundary_only_gates: {declared}
        """
    )

    with pytest.raises(FactoryConfigError) as excinfo:
        parse_factory_config(text)

    assert excinfo.value.rule == "boundary_only_gates"


# --- T003 [US1-S3] the control: absence is today -----------------------------


def test_a_manifest_that_does_not_declare_the_key_parses_exactly_as_today() -> None:
    """US1-S3 / FR-003 — the control, green before and after the key lands.

    Compared field for field against a `FactoryConfig` built without the key,
    in both schemas, because every manifest that exists is this manifest: the
    v2 bodies with no `boundary_only_gates:` line, and every v1 body, where the
    key is unknown anyway. The whole-`FactoryConfig` identity is the same form
    `tests/test_121_manifest_is_not_a_fixture.py` holds the parser's v1
    defaults to, so a reader that gained a non-empty default for the absent key
    fails here naming the difference — which is what keeps FR-003 holding by
    construction rather than by inspection.
    """
    v2_text = _yaml(
        """
        version: 2
        runtime: bwrap
        gates:
          test: "uv run pytest -q"
        """
    )

    v2 = parse_factory_config(v2_text)

    assert v2 == FactoryConfig(version=2, runtime="bwrap", gates={"test": "uv run pytest -q"})

    v1_text = _yaml(
        """
        version: 1
        runtime: bwrap
        gates:
          test: "uv run pytest -q"
        """
    )

    v1 = parse_factory_config(v1_text)

    assert v1 == FactoryConfig(version=1, runtime="bwrap", gates={"test": "uv run pytest -q"})


# --- T004 [US1-S4] one body, two versions ------------------------------------


def test_the_key_is_real_in_v2_and_refused_on_v1() -> None:
    """US1-S4 / FR-004: the differential pair, both halves in one test.

    The v1 half is true on today's tree — v1 refuses every v2-only key — so a
    diff that registered `boundary_only_gates` in the v1 tuple instead of the
    v2 one would leave this test's second assertion failing and its first
    passing; only the pair pins the tuple.
    """
    body = _yaml(
        """
        version: {version}
        runtime: bwrap
        gates:
          audit: "uv run pytest tests/audit -q"
        boundary_only_gates: [audit]
        """
    )

    v2 = parse_factory_config(body.format(version=2))

    assert v2.boundary_only_gates == ("audit",)

    with pytest.raises(FactoryConfigError) as excinfo:
        parse_factory_config(body.format(version=1))

    error = excinfo.value
    assert error.rule == "unknown_key"
    message = str(error)
    assert "'boundary_only_gates'" in message, f"must name the key: {message!r}"
    assert "schema v1" in message, f"must say which schema refused it: {message!r}"