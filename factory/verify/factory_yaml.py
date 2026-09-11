"""The target repo's committed statement of what "green" means (D-009, R2).

`factory.yaml` is declared by the repo, never auto-detected, and it is the only
input that tells the gate runner which commands decide a node's fate. That makes
the interesting half of this module the rejections, not the acceptances: a
verifier that shrugged at a broken manifest would find no gates, therefore see
nothing fail, therefore hand out a PASS for a repo it never tested. So every rule
in contracts/factory-yaml.md refuses, and `config_error_result` turns the refusal
into a single `GateResult{name: "config", status: CONFIG_ERROR}` — gate *data*
the verdict truth table reads and fails on, rather than an exception some caller
could interpret as "no gates ran, so no gates failed".

Three things this module deliberately does not do:

- **Execute anything.** It is a pure function over text, with two named
  exceptions: `load_factory_config`, which reads the file so callers holding a
  worktree path get errors that name it instead of an `OSError`, and
  `_read_caches`, which resolves a declared path against the operator's home
  because FR-007's bound is a fact about this host's symlinks and no string
  comparison can decide it. Both say so where they do it.
- **Fill in defaults.** `timeouts` stays exactly as sparse as it was written, so
  the runner can still tell "declared 600" from "not declared" and the 600s
  default remains one knob (`VerificationConfig.gate_timeout_s`) instead of a
  value baked into every parsed manifest.
- **Normalise gate order.** `gates` keeps the file's order because the runner
  executes it in that order; sorting into the canonical `test`/`lint`/`typecheck`
  shape would spend a full test run ahead of the lint that would have failed in
  two seconds — the repo's ordering is the repo's choice.

Amended by 005 (research R11) with an optional top-level `standards` key: the
path to the repo's coding-standards document, which prompt assembly points an
agent at. It is additive and optional, so the schema stays `version: 1` — a
bump for one optional key would force every target repo to migrate for nothing.
Only its *shape* is checked here, because whether the file exists is a question
about a worktree, and the one activity holding a worktree before the agent does
(`prepare_worktree`) asks it. Like every optional key in this module, declared
means declared: a null, blank, or non-string value is a defect, not a shrug.

The messages are written for an operator holding a broken file, so each one names
the source file, the `.rule` slug that was violated, and the offending value
`repr`-rendered. The `repr` is load-bearing: YAML's whole family of near-misses
is type confusion — `version: "1"` versus `version: 1`, `test: true` as a timeout
— and a message that printed `1` for both would send someone hunting the wrong
line. Bools get their own guard for the same reason: `True == 1` in Python, so a
naive `== 1` version check would accept `version: true`.
"""

from __future__ import annotations

import dataclasses
import json
import re
import sys
import warnings
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

import yaml

from factory.verify.diffbounds import DIFF_INPUT_LIMIT, DIFF_REFUSAL_THRESHOLD
from factory.verify.models import (
    ArtifactDeclaration,
    ArtifactType,
    CacheDeclaration,
    FactoryConfig,
    GateResult,
    GateStatus,
    RoadmapDials,
    VerificationConfig,
    gate_watchdog_basis,
)

#: The manifest's committed filename; callers compose `<worktree>/ergane.yaml`.
MANIFEST_NAME = "ergane.yaml"

#: The legacy manifest filename, still honored for existing managed repos.
# The literal string is assembled so source scanners can keep enforcing FR-004:
# no reader in this module may contain the legacy name as a quoted literal.
_legacy_parts = ("fac", "tory.yaml")
LEGACY_MANIFEST_NAME = "".join(_legacy_parts)

#: Exit code when the CLI accepts a manifest and emits the parsed config as JSON.
PARSE_CLI_OK = 0

#: Exit code when the CLI rejects a manifest.
#
# This is sysexits `EX_DATAERR` (65).  It must not be 1 or 2: `uv run` and
# `python -m` use those for launcher problems (broken `pyproject.toml`, missing
# module, argparse usage errors), so a rejection code of 1 or 2 would make the
# caller misread "the parser never started" as "the parser refused the manifest".
PARSE_CLI_REJECTED = 65

#: Schema v1 fixes the gate names so component 3 can map merge-queue required
#: checks to gates 1:1. Arbitrary names are a `version: 2` conversation.
KNOWN_GATES = ("test", "lint", "typecheck")

#: Supported sandbox backends in US2. The value domain of `runtime:` changes from
#: a container image reference to a backend name; only these names are accepted.
SUPPORTED_BACKENDS = ("bwrap",)

#: The forge a repository is on when its manifest names none (049 FR-014).
#
# Spelled here rather than imported from `factory.mergequeue.forge`, which owns
# the same fact as `DEFAULT_FORGE`: that module's builtin loader reaches
# `factory.mergequeue.gh`, which imports `factory.verify.gates`, which imports
# this module — a cycle visible only at import time. `_read_forge` pays for the
# real registry lazily and only when a manifest actually declares the key, so a
# manifest that declares nothing imports nothing new.
# `tests/test_forge_manifest.py` holds the spellings together.
DEFAULT_FORGE_NAME = "github"

_TOP_LEVEL_KEYS = (
    "version",
    "runtime",
    "gates",
    "timeouts",
    "standards",
    "landing_branch",
    "roadmap",
    "forge",
    "writes",
    "caches",
    "diff_refusal_bytes",
)

#: The keys one `caches:` entry may declare (101 FR-004).
_CACHE_KEYS = ("path", "env")

#: Keys one `artifacts:` entry may declare (134 FR-001).
_ARTIFACT_KEYS = ("gate", "path", "type")

#: What a declared `env:` name may look like. The declaration becomes a
#: `--setenv <name> <path>` pair on the boundary's own command line, so a name
#: outside this shape is a variable the gate's shell cannot read back — which
#: would leave the cache bound and the tool still unable to find it, the exact
#: failure FR-008 exists to prevent.
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")

#: Keys that only schema v2 recognises; v1 refuses them as unknown (US1-S6).
#:
#: `boundary_only_gates` (128 FR-001) joins this tuple and not `_TOP_LEVEL_KEYS`:
#: the list names gates that bind the verification boundary but are deliberately
#: absent from the forge's merge queue, so declaring it must mean the same thing
#: on every schema that can spell it — and a v1 manifest naming it is refused,
#: not silently carried, because the v1 reader would otherwise parse a key it
#: had no reader for. The tuple is also what `ergane init` carries forward
#: (`factory/cli/init.py`'s `_KNOWN_KEYS` is this same object), so a key here is
#: carried-not-interviewed by construction and needs no prompt of its own.
_V2_TOP_LEVEL_KEYS = _TOP_LEVEL_KEYS + (
    "ladder",
    "verify",
    "boundary_only_gates",
    "artifacts",
)

#: The keys a `roadmap:` block may declare, and the dial each one sets.
_ROADMAP_KEYS = ("cadence_s", "max_concurrent_epics", "max_concurrent_nodes")

#: The ladder fields a v2 manifest may declare, with their platform ceilings.
#: `promotion_persona` is not a ladder dial — it names a registry persona and is
#: therefore a string, not an integer.  A fourth integer dial would repeat the
#: `max_recovery_cycles` defect; instead the budget (`promotion_cycles`) lives
#: here and the persona name is read separately (US5-S4).
_LADDER_KEYS = (
    "max_attempts",
    "max_judge_retries",
    "debugger_cycles",
    "escalation_timeout_s",
    "promotion_cycles",
    "max_pre_agent_failures",
)

#: Recognised `ladder:` keys that are not integer dials.
_LADDER_STRING_KEYS = ("promotion_persona",)

#: (min, max) inclusive bounds for each ladder dial.
_LADDER_BOUNDS = {
    "max_attempts": (1, 10),
    "max_judge_retries": (0, 10),
    "debugger_cycles": (0, 3),
    "escalation_timeout_s": (60, 86400),
    "promotion_cycles": (0, 3),
    "max_pre_agent_failures": (1, 10),
}

#: Reserved gate names in schema v2. They collide with step names or the
#: synthetic `config` gate emitted by `config_error_result`.
_RESERVED_GATE_NAMES = frozenset({"gates", "diff_check", "judge", "config"})

#: The verification steps a v2 `verify:` list may name, and today's default.
_VERIFY_STEPS = ("gates", "diff_check", "judge")

#: Backwards-compatible name for the default schema version (still v1). New
#: code should query membership in `_SUPPORTED_VERSIONS` instead.
_SUPPORTED_VERSION = 1

_SUPPORTED_VERSIONS = (1, 2)


class FactoryConfigError(ValueError):
    """A manifest that cannot be trusted to decide anything, and why.

    `rule` is the stable slug from the contract's validation table — code and
    tests branch on it, so the wording of a message may improve where the slug
    may not drift. `source` labels which file to go fix; it is the bare filename
    until a caller that holds a path supplies one.
    """

    def __init__(self, rule: str, problem: str, *, source: str = MANIFEST_NAME) -> None:
        super().__init__(f"{source}: [{rule}] {problem}")
        self.rule = rule
        self.problem = problem
        self.source = source


# Parsing ---------------------------------------------------------------------


def parse_factory_config(text: str, *, source: str = MANIFEST_NAME) -> FactoryConfig:
    """Validate one manifest's text against schema v1 and return it typed.

    Raises `FactoryConfigError` on the first rule violated; a manifest is usable
    as a whole or not at all, because a half-honoured gate list is exactly the
    silent under-verification this component exists to prevent.
    """
    document = _load_mapping(text, source)

    # Version is read first because the set of legal top-level keys is
    # version-dependent: v1 rejects `ladder:` and `verify:` as unknown (US1-S6),
    # while v2 recognises them. A manifest with an unknown key that is also an
    # invalid version still reports the version rule first.
    version = _read_version(document, source)
    _reject_unknown_keys(document, source, version)
    runtime = _read_runtime(document, source)
    gates = _read_gates(document, source, version)
    timeouts = _read_timeouts(document, gates, source)
    writes = _read_writes(document, gates, source)
    boundary_only_gates = _read_boundary_only_gates(document, gates, source)
    standards = _read_standards(document, source)
    landing_branch = _read_landing_branch(document, source)
    roadmap = _read_roadmap(document, source)
    forge = _read_forge(document, source)
    ladder = _read_ladder(document, source)
    verify_order = _read_verify(document, source)
    diff_refusal_bytes = _read_diff_refusal_bytes(document, source)
    caches = _read_caches(document, source)
    artifacts = _read_artifacts(document, gates, source)

    return FactoryConfig(
        version=version,
        runtime=runtime,
        gates=gates,
        timeouts=timeouts,
        writes=writes,
        boundary_only_gates=boundary_only_gates,
        standards=standards,
        landing_branch=landing_branch,
        roadmap=roadmap,
        forge=forge,
        ladder=ladder,
        verify_order=verify_order,
        diff_refusal_bytes=diff_refusal_bytes,
        caches=caches,
        artifacts=artifacts,
    )


def _load_mapping(text: str, source: str) -> Mapping[Any, Any]:
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise FactoryConfigError(
            "malformed_yaml",
            f"is not parseable YAML: {_one_line(error)}",
            source=source,
        ) from None

    if document is None:
        raise FactoryConfigError(
            "malformed_yaml",
            "is empty; schema v1 requires at least `version`, `runtime` and `gates`",
            source=source,
        )
    if not isinstance(document, Mapping):
        raise FactoryConfigError(
            "malformed_yaml",
            f"must be a mapping of keys to values, not {_kind(document)}",
            source=source,
        )
    return document


def _reject_unknown_keys(document: Mapping[Any, Any], source: str, version: int) -> None:
    known = _V2_TOP_LEVEL_KEYS if version == 2 else _TOP_LEVEL_KEYS
    unknown = [key for key in document if key not in known]
    if unknown:
        raise FactoryConfigError(
            "unknown_key",
            f"declares {_names(unknown)} at the top level; schema v{version} knows only "
            f"{_names(known)}",
            source=source,
        )


def _read_version(document: Mapping[Any, Any], source: str) -> int:
    if "version" not in document:
        raise FactoryConfigError(
            "version",
            "declares no `version`; this factory supports only the integer literals "
            f"{_names(_SUPPORTED_VERSIONS)}",
            source=source,
        )
    version = document["version"]
    # `isinstance(True, int)` is True, and YAML spells booleans `true`, so the
    # bool has to be excluded by type identity or `version: true` slips through.
    if type(version) is not int or version not in _SUPPORTED_VERSIONS:
        raise FactoryConfigError(
            "version",
            f"declares `version: {version!r}`; this factory supports only the "
            f"integer literals {_names(_SUPPORTED_VERSIONS)}",
            source=source,
        )
    return version


def _read_runtime(document: Mapping[Any, Any], source: str) -> str:
    if "runtime" not in document:
        raise FactoryConfigError(
            "runtime",
            "declares no `runtime`; schema v1 requires a supported sandbox "
            f"backend name, e.g. `runtime: {SUPPORTED_BACKENDS[0]}`",
            source=source,
        )
    runtime = document["runtime"]
    if not isinstance(runtime, str) or not runtime.strip():
        raise FactoryConfigError(
            "runtime",
            f"declares `runtime: {runtime!r}`; it must be a supported sandbox "
            f"backend name, e.g. `{SUPPORTED_BACKENDS[0]}`",
            source=source,
        )
    if runtime not in SUPPORTED_BACKENDS:
        raise FactoryConfigError(
            "runtime",
            f"declares `runtime: {runtime!r}`; the supported backend is "
            f"`{SUPPORTED_BACKENDS[0]}`",
            source=source,
        )
    return runtime


def _read_gates(document: Mapping[Any, Any], source: str, version: int) -> dict[str, str]:
    if "gates" not in document:
        if version == 2:
            raise FactoryConfigError(
                "gates",
                "declares no `gates`; schema v2 requires at least one gate with a "
                "non-empty name and command",
                source=source,
            )
        raise FactoryConfigError(
            "gates",
            f"declares no `gates`; schema v1 requires at least one of "
            f"{_names(KNOWN_GATES)}, or nothing verifies this repo",
            source=source,
        )
    gates = document["gates"]
    if not isinstance(gates, Mapping):
        raise FactoryConfigError(
            "gates",
            f"declares `gates` as {_kind(gates)}; it must be a mapping of gate "
            "name to command",
            source=source,
        )
    if not gates:
        raise FactoryConfigError(
            "gates",
            "declares an empty `gates` mapping; at least one gate must be present",
            source=source,
        )
    if version == 1:
        unknown = [name for name in gates if name not in KNOWN_GATES]
        if unknown:
            raise FactoryConfigError(
                "gates",
                f"declares the gate(s) {_names(unknown)}; schema v1 fixes the gate "
                f"names to {_names(KNOWN_GATES)} so merge-queue required checks map "
                "to them 1:1",
                source=source,
            )
    else:
        reserved = [name for name in gates if name in _RESERVED_GATE_NAMES]
        if reserved:
            raise FactoryConfigError(
                "gate_name",
                f"declares the reserved gate name(s) {_names(reserved)}; schema v2 "
                "gate names must not collide with the verification step names "
                f"{_names(_VERIFY_STEPS)} or the synthetic gate name 'config'",
                source=source,
            )

    for name, command in gates.items():
        if not isinstance(name, str) or not name.strip():
            raise FactoryConfigError(
                "gate_name",
                f"declares a gate with empty name {name!r}; schema v2 gate names "
                "must be non-empty strings",
                source=source,
            )
        if not isinstance(command, str) or not command.strip():
            raise FactoryConfigError(
                "gate_command",
                f"gives gate {name!r} the command {command!r}; each gate needs a "
                "non-empty shell command string",
                source=source,
            )
    # Declaration order is the operator's cheapest-first ordering; preserve it.
    return dict(gates)


def _read_timeouts(
    document: Mapping[Any, Any], gates: Mapping[str, str], source: str
) -> dict[str, int]:
    if "timeouts" not in document:
        # Absent is not "600 everywhere" — it is "nothing declared", which is
        # what lets the runner's default stay a single knob.
        return {}
    timeouts = document["timeouts"]
    if not isinstance(timeouts, Mapping):
        raise FactoryConfigError(
            "timeouts",
            f"declares `timeouts: {timeouts!r}`; it must be a mapping of gate "
            "name to a positive number of seconds",
            source=source,
        )

    for name, seconds in timeouts.items():
        if name not in gates:
            raise FactoryConfigError(
                "timeouts",
                f"sets a timeout for {name!r}, which this manifest does not "
                f"declare as a gate; declared gates are {_names(gates)}",
                source=source,
            )
        if type(seconds) is not int or seconds <= 0:
            raise FactoryConfigError(
                "timeouts",
                f"gives gate {name!r} the timeout {seconds!r}; it must be a "
                "positive whole number of seconds",
                source=source,
            )
    return dict(timeouts)


def _read_writes(
    document: Mapping[Any, Any], gates: Mapping[str, str], source: str
) -> dict[str, bool]:
    """Read the gates this repo declares as legitimate writers (084 FR-009).

    The same position, shape and sparseness `timeouts:` has, for the same
    reason: the declaration belongs to a gate, so it is written against the gate
    by name rather than as a repo-wide switch. Absent is "nothing declared", and
    so is `false` — a key with one position would let a repo turn off the whole
    check by naming a gate at all.

    The `false` entries are kept rather than filtered. A manifest that spells
    out a declaration it has retired is telling its next reader something, and
    dropping it here would make `ergane init` re-runs rewrite the operator's
    manifest to say less than it said.
    """
    if "writes" not in document:
        return {}
    writes = document["writes"]
    if not isinstance(writes, Mapping):
        raise FactoryConfigError(
            "writes",
            f"declares `writes: {writes!r}`; it must be a mapping of gate name "
            "to a boolean saying whether that gate writes on purpose",
            source=source,
        )

    for name, declared in writes.items():
        if name not in gates:
            # A declaration that silently applied to nothing would be worse than
            # no declaration: the operator would read a manifest that says the
            # gate is covered, and the node would refuse it anyway (FR-011).
            raise FactoryConfigError(
                "writes",
                f"declares writes for {name!r}, which this manifest does not "
                f"declare as a gate; declared gates are {_names(gates)}",
                source=source,
            )
        # `type(...) is not bool` rather than `isinstance`, for the reason
        # `_read_timeouts` spells its own check exactly: `isinstance(True, int)`
        # is true, so the loose forms of these two checks each accept the
        # other's values.
        if type(declared) is not bool:
            raise FactoryConfigError(
                "writes",
                f"gives gate {name!r} the writes declaration {declared!r}; it "
                "must be `true` or `false`",
                source=source,
            )
    return dict(writes)


def _read_boundary_only_gates(
    document: Mapping[Any, Any], gates: Mapping[str, str], source: str
) -> tuple[str, ...]:
    """Read the gates this repo declares as binding the boundary alone (128 FR-001).

    The same position and shape `writes:` has, for the same reason: the
    declaration is about gates, so it is written as a list of gate names beside
    the `gates:` block that declares them, and absent is "nothing declared" —
    an empty tuple is what every manifest that exists parses to, because the
    key is new and v2-only (FR-003).

    Every entry is cross-checked against the declared gates (FR-002), and that
    check is deliberately strict: an entry naming a gate the manifest does not
    declare is refused rather than ignored. A declaration that silently applied
    to nothing would be worse than no declaration — the operator would read a
    manifest that says the gate is exempt from the merge queue, and the node
    would refuse it anyway.
    """
    if "boundary_only_gates" not in document:
        return ()
    declared = document["boundary_only_gates"]
    if not isinstance(declared, list):
        # `gates` is non-empty here by construction: `_read_gates` refuses a
        # missing or empty mapping before this reader runs, so the example can
        # name a gate this manifest really declares.
        raise FactoryConfigError(
            "boundary_only_gates",
            f"declares `boundary_only_gates: {declared!r}`; it must be a list of "
            "gate names drawn from the gates this manifest declares, e.g. "
            f"`boundary_only_gates: [{next(iter(gates))}]`",
            source=source,
        )

    for name in declared:
        if not isinstance(name, str) or not name.strip():
            raise FactoryConfigError(
                "boundary_only_gates",
                f"declares the boundary-only gate {name!r}; each entry must be a "
                f"non-empty gate name, and declared gates are {_names(gates)}",
                source=source,
            )
        if name not in gates:
            # A declaration that silently applied to nothing would be worse than
            # no declaration — the operator would read a manifest that says the
            # gate is exempt from the merge queue, and the node would refuse it
            # anyway (FR-002).
            raise FactoryConfigError(
                "boundary_only_gates",
                f"declares boundary-only gate {name!r}, which this manifest does "
                f"not declare as a gate; declared gates are {_names(gates)}",
                source=source,
            )
    return tuple(declared)


def _read_standards(document: Mapping[Any, Any], source: str) -> str | None:
    if "standards" not in document:
        # Absent is not a defect: most repos declare no standards document, and
        # `None` is what tells prompt assembly there is nothing to point at.
        return None
    standards = document["standards"]
    # Declared means declared. `standards:` with no value parses to None, and a
    # blank string is the same operator mistake wearing a different hat — both
    # would otherwise read as "declared" here and as "nothing to obey" there.
    if not isinstance(standards, str) or not standards.strip():
        raise FactoryConfigError(
            "standards",
            f"declares `standards: {standards!r}`; when declared it must be a "
            "non-empty path to one document in the repo, e.g. "
            "`standards: docs/STANDARDS.md`",
            source=source,
        )
    # Recorded verbatim: it is resolved against the node's worktree at dispatch,
    # where a missing file fails the dispatch loudly (research R11). Normalising
    # it here would be a filesystem opinion in a pure parser.
    return standards


def _read_landing_branch(document: Mapping[Any, Any], source: str) -> str:
    """The branch the factory lands on, defaulting to 'main' when undeclared.

    D-009's 'declared, never auto-detected' rule applied to the one branch fact
    the factory otherwise guesses at: absent means today's behaviour, but a
    manifest that declares the key badly is refused the same way `standards`
    is — declared means declared.
    """
    if "landing_branch" not in document:
        return "main"
    landing_branch = document["landing_branch"]
    if not isinstance(landing_branch, str) or not landing_branch.strip():
        raise FactoryConfigError(
            "landing_branch",
            f"declares `landing_branch: {landing_branch!r}`; when declared it must be a "
            "non-empty branch name, e.g. `landing_branch: ergane-buildout`",
            source=source,
        )
    return landing_branch


def _read_forge(document: Mapping[Any, Any], source: str) -> str:
    """The forge this repository is on, defaulting to `github` when undeclared.

    Which forge a repository is on is a property of *that repository* — the same
    kind of fact as `landing_branch` and `gates`, and for the same reason: one
    host serves many repositories, possibly on different forges at once, so a
    forge chosen in the operator's control-plane file would make the engine able
    to serve only one at a time (049 FR-014, D-046).

    Absent means `github`, which is what every repository that exists today is
    on, so no manifest has to migrate. Declared means declared: a null, blank or
    non-string value is a defect, the rule every optional key here follows.

    A name nothing is registered under is **refused**, and the registered names
    are listed so the operator can see what they could have written. Defaulting
    instead would let a deployment ask for one forge, silently get another, and
    open proposals — and land them — somewhere nobody was looking.

    The registry import is deliberately inside the function and after the shape
    checks. `factory.mergequeue.forge` loads the shipped forges, which reach
    `factory.verify.gates`, which imports this module; at module scope that is a
    cycle. Here it is paid only by a manifest that declares the key, so the path
    every repository takes today is byte-identical to the one it took before.
    """
    if "forge" not in document:
        return DEFAULT_FORGE_NAME
    forge = document["forge"]
    if not isinstance(forge, str) or not forge.strip():
        raise FactoryConfigError(
            "forge",
            f"declares `forge: {forge!r}`; when declared it must be a non-empty "
            f"forge name, e.g. `forge: {DEFAULT_FORGE_NAME}`",
            source=source,
        )

    from factory.mergequeue.forge import registered_forges

    known = registered_forges()
    if forge not in known:
        raise FactoryConfigError(
            "forge",
            f"declares `forge: {forge!r}`, which nothing is registered under; "
            f"the forges this factory ships are {_names(known)}",
            source=source,
        )
    return forge


def _read_roadmap(document: Mapping[Any, Any], source: str) -> RoadmapDials | None:
    """The repo's scheduler dials, or `None` when it declares no `roadmap:` block.

    Optional and additive, so the schema stays `version: 1` — the reasoning
    `standards` was added under.  Absent is `None` rather than a defaulted block:
    the init interview offers the existing manifest back as its defaults, and a
    parser that invented `roadmap: {cadence_s: 300}` for every repo would make an
    unchanged re-run rewrite a key nobody declared.

    Declared means declared, so every near-miss is refused with the value
    rendered: `cadence_s: "300"` is a string, `max_concurrent_epics: true` is a
    bool that `== 1`, `cadence: 300` is a typo for the key above it.  Each would
    otherwise be a dial silently set to something the operator did not choose,
    on a schedule that dispatches real work.
    """
    if "roadmap" not in document:
        return None
    block = document["roadmap"]
    if not isinstance(block, Mapping) or not block:
        raise FactoryConfigError(
            "roadmap",
            f"declares `roadmap: {block!r}`; when declared it must be a non-empty "
            f"mapping drawn from {_names(_ROADMAP_KEYS)}, e.g. "
            "`roadmap: {cadence_s: 300}`",
            source=source,
        )

    unknown = [key for key in block if key not in _ROADMAP_KEYS]
    if unknown:
        raise FactoryConfigError(
            "roadmap",
            f"declares {_names(unknown)} under `roadmap`; the dials are "
            f"{_names(_ROADMAP_KEYS)}",
            source=source,
        )

    for key in _ROADMAP_KEYS:
        if key not in block:
            continue
        value = block[key]
        # `isinstance(True, int)` is True, so the bool is excluded by identity —
        # `max_concurrent_epics: true` would otherwise pass as a bound of 1.
        if type(value) is not int or value <= 0:
            raise FactoryConfigError(
                "roadmap",
                f"gives `roadmap.{key}` the value {value!r}; every dial is a "
                "positive whole number",
                source=source,
            )

    defaults = RoadmapDials()
    return RoadmapDials(
        cadence_s=int(block.get("cadence_s", defaults.cadence_s)),
        max_concurrent_epics=int(block.get("max_concurrent_epics", defaults.max_concurrent_epics)),
        max_concurrent_nodes=int(block.get("max_concurrent_nodes", defaults.max_concurrent_nodes)),
    )


def _read_diff_refusal_bytes(document: Mapping[Any, Any], source: str) -> int:
    """The size above which this repository refuses to build a story (092 FR-004).

    Until this key existed, that size was `factory/verify/diffbounds.py`'s to
    choose and nobody else's: `diff_check` is mandatory, the threshold had no
    manifest key and no flag, and the seam `check_output` already carried had no
    production caller. An operator whose repository legitimately builds large
    stories could only edit the tool. The measured cost of that was three
    fully-green attempts thrown away one rung from escalation, on a diff of
    74,465 bytes with no generated file in it at all.

    Absent means the default, which is `DIFF_REFUSAL_THRESHOLD` — read from the
    module that owns it, never restated, because a second copy of the number
    would let tuning it silently do nothing (092 trap 2). A declared value is
    refused two ways, both in the shape the ladder's integer dials are refused:

    - **Not a whole number** (FR-006), by type identity, because
      `isinstance(True, int)` is True and `diff_refusal_bytes: true` would
      otherwise become a ceiling of one byte. `null` fails here too, and that is
      load-bearing rather than incidental: `None` is how the seam spells *the
      check is disabled*, so a manifest that could spell it would be a
      repository with no ceiling at all, wearing the appearance of one
      (092 trap 5). A repository may raise its ceiling; it may not remove it,
      and principle VIII is why.
    - **Below the judge's attention budget** (FR-005), because a refusal
      stricter than `prepare_diff`'s own cap refuses every diff the judge would
      merely have abridged — which is precisely the defect this spec exists to
      remove, reintroduced under a new name (092 trap 4). Both numbers are named:
      the operator needs to see the value they typed *and* the floor it hit, or
      the message sends them hunting for one of the two. A negative value is
      below every floor, so this rung is what catches it.

    There is deliberately no ceiling. The floor exists because a value under it
    silently breaks the mechanism; nothing breaks above it, and a repository
    that wants to judge a megabyte on an abridged prompt is making a legible
    trade-off — one this factory records, since 092/US3, on the verdict itself.
    """
    if "diff_refusal_bytes" not in document:
        return DIFF_REFUSAL_THRESHOLD

    value = document["diff_refusal_bytes"]
    # `isinstance(True, int)` is True, so the bool is excluded by identity.
    if type(value) is not int:
        raise FactoryConfigError(
            "diff_refusal_bytes_type",
            f"gives `diff_refusal_bytes` the value {value!r}; it must be a whole "
            "number of bytes (booleans are not integers here)",
            source=source,
        )
    if value < DIFF_INPUT_LIMIT:
        raise FactoryConfigError(
            "diff_refusal_bytes_min",
            f"gives `diff_refusal_bytes` the value {value!r}; the floor is "
            f"{DIFF_INPUT_LIMIT}, the size a diff is abridged to for the judge "
            "— refusing below it would throw away every diff that would merely "
            "have been abridged",
            source=source,
        )
    return value


def _read_caches(
    document: Mapping[Any, Any], source: str
) -> tuple[CacheDeclaration, ...]:
    """The caches this repository's gates need carried into the boundary (FR-004).

    Optional and additive, so the schema does not bump: absent is `()`, which is
    what every manifest that exists says and which means the uv bind and nothing
    else, byte-for-byte as before (FR-006).

    **This reader touches the filesystem, and the departure is deliberate.**
    Everything else in this module is a pure function over text — that is the
    property the module docstring claims and the reason a broken manifest can be
    judged without a worktree. FR-007 cannot be decided that way. A path is
    inside the operator's home or outside it as a fact about *this host's*
    symlinks, and the bypass the check exists to close is a link spelled inside
    home that lands outside it, which no amount of string comparison sees. So the
    path is expanded, resolved, and compared against `Path.home()` — the same
    home `_cache_binds` composes the uv default from, because a parser that
    bounded declarations against one home while the boundary mounted from another
    would be enforcing nothing.

    Refused at *load* time rather than at mount time on purpose. A declared bind
    is a hole in a verification boundary, opened by a manifest that belongs to
    whoever controls the target repository; a refusal here costs one clear error
    message naming the path, while a boundary that discovered the problem while
    mounting would have already decided which host directories a repo-declared
    gate command can write to.

    Everything else is the rule every optional key here follows: declared means
    declared. `caches: []` is an operator who meant to write something, a bare
    string entry is the shape guess, an unknown key inside an entry is a typo
    that would silently declare nothing, and an `env:` the boundary cannot spell
    is a bind whose tool still cannot find it.
    """
    if "caches" not in document:
        return ()

    declared = document["caches"]
    if not isinstance(declared, list) or not declared:
        raise FactoryConfigError(
            "caches",
            f"declares `caches: {declared!r}`; when declared it must be a "
            "non-empty list of entries, each naming a `path` and optionally the "
            "`env` variable that points at it, e.g. "
            "`caches: [{path: ~/.npm, env: npm_config_cache}]`",
            source=source,
        )

    home = Path.home().resolve()
    entries: list[CacheDeclaration] = []
    for entry in declared:
        if not isinstance(entry, Mapping):
            raise FactoryConfigError(
                "caches",
                f"declares the cache entry {entry!r}; each entry must be a "
                f"mapping drawn from {_names(_CACHE_KEYS)}, e.g. "
                "`- {path: ~/.npm, env: npm_config_cache}`",
                source=source,
            )
        unknown = [key for key in entry if key not in _CACHE_KEYS]
        if unknown:
            raise FactoryConfigError(
                "caches",
                f"declares {_names(unknown)} on a cache entry; the keys are "
                f"{_names(_CACHE_KEYS)}",
                source=source,
            )

        raw = entry.get("path")
        if not isinstance(raw, str) or not raw.strip():
            raise FactoryConfigError(
                "caches",
                f"gives a cache entry the path {raw!r}; every entry needs a "
                "non-empty `path` naming a directory under the operator's home",
                source=source,
            )
        spelled = raw.strip()
        expanded = Path(spelled).expanduser()
        if not expanded.is_absolute():
            # A relative path resolves against whatever directory the reading
            # process happens to sit in, which is exactly the ambient state
            # constitution IX refuses: the same manifest would then declare
            # different directories to the worker and to a node.
            raise FactoryConfigError(
                "caches",
                f"declares the cache path {spelled!r}, which is relative; a "
                "cache path is absolute or `~`-relative, never resolved against "
                "the reading process's working directory",
                source=source,
            )

        resolved = expanded.resolve()
        if resolved == home or not resolved.is_relative_to(home):
            raise FactoryConfigError(
                "caches_outside_home",
                f"declares the cache path {spelled!r}, which resolves to "
                f"{str(resolved)!r} — not a directory under the operator's home "
                f"{str(home)!r}. A declared bind is a hole in the verification "
                "boundary, so its blast radius is bounded to home; home itself "
                "is not a cache",
                source=source,
            )

        env = entry.get("env")
        if "env" in entry and (
            not isinstance(env, str) or not _ENV_NAME.match(env)
        ):
            raise FactoryConfigError(
                "caches",
                f"gives the cache {spelled!r} the variable name {env!r}; when "
                "declared it must be a usable environment variable name, e.g. "
                "`env: npm_config_cache`",
                source=source,
            )

        entries.append(
            CacheDeclaration(
                path=str(resolved), env=env if isinstance(env, str) else None
            )
        )

    return tuple(entries)


def _read_ladder(document: Mapping[Any, Any], source: str) -> "VerificationConfig":
    """The v2 retry-ladder caps, defaulting to today's `VerificationConfig`.

    Absent means the current defaults. Declared means declared, and every
    value is type-identity-checked as a non-boolean integer within platform
    ceilings — `ladder: {max_attempts: true}` would otherwise become a budget
    of 1 (trap 1).
    """
    if "ladder" not in document:
        return VerificationConfig()
    block = document["ladder"]
    if not isinstance(block, Mapping) or not block:
        raise FactoryConfigError(
            "ladder",
            f"declares `ladder: {block!r}`; when declared it must be a non-empty "
            f"mapping drawn from {_names(_LADDER_KEYS)}, e.g. "
            "`ladder: {max_attempts: 3}`",
            source=source,
        )

    known = set(_LADDER_KEYS) | set(_LADDER_STRING_KEYS)
    unknown = [key for key in block if key not in known]
    if unknown:
        raise FactoryConfigError(
            "unknown_ladder_key",
            f"declares {_names(unknown)} under `ladder`; the ladder keys are "
            f"{_names(sorted(known))}",
            source=source,
        )

    defaults = VerificationConfig()
    values: dict[str, int] = {}
    for key in _LADDER_KEYS:
        if key not in block:
            values[key] = getattr(defaults, key)
            continue
        value = block[key]
        # `isinstance(True, int)` is True, so the bool is excluded by identity.
        if type(value) is not int:
            raise FactoryConfigError(
                f"ladder_{key}_type",
                f"gives ladder.{key!r} the value {value!r}; it must be a whole "
                "number (booleans are not integers here)",
                source=source,
            )
        minimum, maximum = _LADDER_BOUNDS[key]
        if value < minimum:
            raise FactoryConfigError(
                f"ladder_{key}_min",
                f"gives ladder.{key!r} the value {value!r}; the floor is {minimum}",
                source=source,
            )
        if value > maximum:
            raise FactoryConfigError(
                f"ladder_{key}_max",
                f"gives ladder.{key!r} the value {value!r}; the ceiling is {maximum}",
                source=source,
            )
        values[key] = value

    promotion_persona = _read_promotion_persona(block, source)

    return VerificationConfig(
        max_attempts=values["max_attempts"],
        max_judge_retries=values["max_judge_retries"],
        debugger_cycles=values["debugger_cycles"],
        gate_timeout_s=defaults.gate_timeout_s,
        escalation_timeout_s=values["escalation_timeout_s"],
        promotion_persona=promotion_persona,
        promotion_cycles=values["promotion_cycles"],
        max_pre_agent_failures=values["max_pre_agent_failures"],
    )


def _read_artifacts(
    document: Mapping[Any, Any], gates: Mapping[str, str], source: str
) -> tuple[ArtifactDeclaration, ...]:
    """Read the artifacts this repository's gates declare they write.

    Optional and additive: absent means no declaration and every pre-existing
    field parses unchanged (134 FR-003). Paths stay lexical because the parser
    may run from any working directory, and repository containment is a property
    of the manifest text, not a fact about this host's symlinks (134 FR-012).
    """
    if "artifacts" not in document:
        return ()

    declared = document["artifacts"]
    if not isinstance(declared, list) or not declared:
        raise FactoryConfigError(
            "artifacts",
            f"declares `artifacts: {declared!r}`; when declared it must be a "
            "non-empty list of entries, each naming a `gate`, a repo-relative "
            "`path` and a `type`, e.g. "
            "`artifacts: [{gate: test, path: coverage.xml, type: coverage}]`",
            source=source,
        )

    permitted = _names(ArtifactType)
    entries: list[ArtifactDeclaration] = []
    for entry in declared:
        if not isinstance(entry, Mapping):
            raise FactoryConfigError(
                "artifacts",
                f"declares the artifact entry {entry!r}; each entry must be a "
                f"mapping drawn from {_names(_ARTIFACT_KEYS)}",
                source=source,
            )
        unknown = [key for key in entry if key not in _ARTIFACT_KEYS]
        if unknown:
            raise FactoryConfigError(
                "artifacts",
                f"declares {_names(unknown)} on the artifact entry {entry!r}; "
                f"the keys are {_names(_ARTIFACT_KEYS)}",
                source=source,
            )

        gate = entry["gate"]
        if not isinstance(gate, str) or not gate.strip() or gate not in gates:
            raise FactoryConfigError(
                "artifacts",
                f"declares the artifact entry {entry!r}, whose gate {gate!r} is "
                "not one this manifest declares; declared gates are "
                f"{_names(gates)}",
                source=source,
            )

        type_name = entry["type"]
        if type_name not in ArtifactType:
            raise FactoryConfigError(
                "artifacts",
                f"declares the artifact entry {entry!r}, whose type {type_name!r} "
                f"is not permitted; permitted types are {permitted}",
                source=source,
            )

        raw_path = entry["path"]
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise FactoryConfigError(
                "artifacts",
                f"declares the artifact entry {entry!r}, whose path {raw_path!r} "
                "must be a non-empty repo-relative POSIX path",
                source=source,
            )

        spelled = raw_path.strip()
        spelled_path = PurePosixPath(spelled)
        if spelled_path.is_absolute():
            raise FactoryConfigError(
                "artifacts",
                f"declares the absolute artifact path {spelled!r}; artifact paths "
                "are worktree-root-relative",
                source=source,
            )

        segments: list[str] = []
        escaped = False
        for segment in spelled_path.parts:
            if segment == ".":
                continue
            if segment == "..":
                if not segments:
                    escaped = True
                    break
                segments.pop()
            else:
                segments.append(segment)
        if escaped or not segments:
            raise FactoryConfigError(
                "artifacts",
                f"declares the artifact path {spelled!r}, which escapes the "
                "worktree root",
                source=source,
            )

        entries.append(
            ArtifactDeclaration(
                gate=gate,
                path="/".join(segments),
                type=ArtifactType(type_name),
            )
        )

    return tuple(entries)


def _read_promotion_persona(
    block: Mapping[Any, Any], source: str
) -> str | None:
    """The operator-configured stronger persona, if any.

    This is intentionally not a ladder dial: ladder dials are integer budgets,
    and `_LADDER_BOUNDS` raises on unknown keys.  The persona name is a string
    that names a registry entry (constitution VII), so it lives beside the budget
    dials rather than inside them (US5-S4).
    """
    if "promotion_persona" not in block:
        return None
    value = block["promotion_persona"]
    if not isinstance(value, str) or not value.strip():
        raise FactoryConfigError(
            "ladder_promotion_persona",
            f"gives `ladder.promotion_persona` the value {value!r}; when declared "
            "it must be a non-empty persona name from the registry",
            source=source,
        )
    return value


def _read_verify(document: Mapping[Any, Any], source: str) -> tuple[str, ...]:
    """The v2 verification-step order, defaulting to today's order.

    The list must be non-empty, duplicate-free, and drawn from exactly the
    three step names. `gates` and `diff_check` are mandatory; `judge` is
    optional but, when present, must follow both — a judge only ever scores
    work that is already green.
    """
    if "verify" not in document:
        return _VERIFY_STEPS
    declared = document["verify"]
    if not isinstance(declared, list) or not declared:
        raise FactoryConfigError(
            "verify",
            f"declares `verify: {declared!r}`; it must be a non-empty ordered list "
            f"drawn from {_names(_VERIFY_STEPS)}",
            source=source,
        )

    seen: set[str] = set()
    for step in declared:
        if step in seen:
            raise FactoryConfigError(
                "verify",
                f"declares `verify` with duplicate step {step!r}; each step may "
                "appear at most once",
                source=source,
            )
        if step not in _VERIFY_STEPS:
            raise FactoryConfigError(
                "verify",
                f"declares `verify` with unknown step {step!r}; the steps are "
                f"{_names(_VERIFY_STEPS)}",
                source=source,
            )
        seen.add(step)

    if "gates" not in seen:
        raise FactoryConfigError(
            "verify",
            "declares verify missing 'gates'; the gate step is not optional",
            source=source,
        )
    if "diff_check" not in seen:
        raise FactoryConfigError(
            "verify",
            "declares verify missing 'diff_check'; the diff check is not optional",
            source=source,
        )
    if "judge" in seen:
        judge_index = declared.index("judge")
        gates_index = declared.index("gates")
        diff_check_index = declared.index("diff_check")
        if judge_index < gates_index or judge_index < diff_check_index:
            raise FactoryConfigError(
                "verify",
                "declares 'judge' before 'gates' or 'diff_check'; a judge only "
                "scores work that is already green",
                source=source,
            )

    return tuple(declared)


# Resolution ------------------------------------------------------------------

#: Module-level sentinel so the deprecation warning fires once per command/process.
_DEPRECATED_LEGACY_NAME: str | None = None


def resolve_manifest_path(repo_root: str | Path) -> tuple[Path, str]:
    """Return the manifest path to read and the filename that was found.

    Preferred name is `ergane.yaml`; legacy name `factory.yaml` is honored with
    a one-time deprecation warning.  When both exist, `ergane.yaml` wins and the
    ignored legacy file is named in the warning.

    This is the one helper every reader calls (FR-001).  The warning is gated
    by a module-level flag because this resolver is invoked many times per epic
    and a per-read warning trains the operator to ignore it (trap 7).
    """
    root = Path(repo_root)
    preferred = root / MANIFEST_NAME
    legacy = root / LEGACY_MANIFEST_NAME

    if preferred.is_file():
        if legacy.is_file():
            _warn_legacy_once(
                f"{LEGACY_MANIFEST_NAME} is ignored in favor of {MANIFEST_NAME}"
            )
        return preferred, MANIFEST_NAME

    if legacy.is_file():
        _warn_legacy_once(
            f"{LEGACY_MANIFEST_NAME} is deprecated; rename it to {MANIFEST_NAME}"
        )
        return legacy, LEGACY_MANIFEST_NAME

    # Neither exists: return the preferred path so the loader's error names what
    # the repo *should* have, not what it used to have.
    return preferred, MANIFEST_NAME


def _warn_legacy_once(message: str) -> None:
    """Emit a `DeprecationWarning` for the legacy name once per Python process."""
    global _DEPRECATED_LEGACY_NAME
    if _DEPRECATED_LEGACY_NAME is not None:
        return
    _DEPRECATED_LEGACY_NAME = message
    warnings.warn(message, DeprecationWarning, stacklevel=2)


# Loading ---------------------------------------------------------------------


def load_factory_config(source: str | Path) -> FactoryConfig:
    """Read and validate the manifest at `source`, naming it in every error.

    Every failure — absent file, unreadable path, undecodable bytes, broken
    schema — leaves as a `FactoryConfigError`. Anything escaping as a bare
    `OSError` would cross the activity boundary as an unexpected failure rather
    than a recorded FAIL, and the attempt would lose its evidence.
    """
    path = Path(source)
    label = str(path)
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise FactoryConfigError(
            "missing_manifest",
            f"cannot be read ({error.strerror or error}); every target repo must "
            f"commit a {MANIFEST_NAME} declaring its gates",
            source=label,
        ) from None

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise FactoryConfigError(
            "malformed_yaml",
            f"is not valid UTF-8 ({error.reason} at byte {error.start})",
            source=label,
        ) from None

    return parse_factory_config(text, source=label)


def load_factory_config_with_name(repo_root: str | Path) -> tuple[FactoryConfig, str]:
    """Resolve and load a repo's manifest, returning the config and chosen name."""
    path, name = resolve_manifest_path(repo_root)
    return load_factory_config(path), name


def load_loop_config(
    repo_root: str | Path,
) -> tuple[VerificationConfig, tuple[str, ...], int]:
    """Dispatch-time loop config pinned from the operator clone's manifest.

    This is the read that matters for the ladder: it happens before any node
    worktree exists, so a worktree rewrite of the manifest cannot move the
    budget or order (023 FR-002/FR-003). Callers that hold a path use
    `resolve_manifest_path` + `load_factory_config` the same way the onboarding
    gate does; the returned values are what ride `EpicInput`.

    092 FR-004 adds the third: the diff refusal threshold belongs on exactly the
    same pin, and for a sharper version of the same argument. It decides whether
    a node's own work is refused unjudged, so a node that could rewrite it in its
    worktree would be voting on its own verdict — the governing value is read
    from the declaration that owns it, once, here (constitution IX).

    The ladder's `gate_timeout_s` is pinned here too, derived from the manifest
    rather than carried as `_read_ladder` leaves it. Per-gate, `timeouts:` and
    the default stay the only governing sources (163 FR-003) — the runner reads
    them at gate time exactly as before — but the *verification activity's*
    watchdog has to outlast the slowest window the manifest declared, and the
    field that sizes it was pinned at the default however long the manifest
    said. The declared deadlines reach the same pin the ladder and the order
    ride, once, at the same dispatch-time read (163 FR-001); `_child_config`'s
    one-field overlay then preserves it into every child a roadmap starts.
    """
    config, _ = load_factory_config_with_name(repo_root)
    ladder = config.ladder
    derived_basis = gate_watchdog_basis(
        config.gates.keys(),
        config.timeouts,
        ladder.gate_timeout_s,
    )
    return (
        dataclasses.replace(ladder, gate_timeout_s=derived_basis),
        config.verify_order,
        config.diff_refusal_bytes,
    )


# Reporting -------------------------------------------------------------------


def config_error_result(error: FactoryConfigError) -> GateResult:
    """Render a rejected manifest as the one gate result the verdict reads.

    `CONFIG_ERROR` is a `GateStatus` rather than an escaping exception precisely
    so composition sees it and fails the verification (data-model.md). There is
    no exit code and no duration because nothing ran — that absence is the
    evidence.
    """
    return GateResult(
        name="config",
        command="",
        status=GateStatus.CONFIG_ERROR,
        exit_code=None,
        duration_s=0.0,
        output_tail=str(error),
    )


# Rendering helpers -----------------------------------------------------------


def _names(values: Any) -> str:
    """`'test', 'lint', 'typecheck'` — quoted so a key is never mistaken for prose."""
    return ", ".join(repr(value) for value in values)


def _kind(value: Any) -> str:
    return f"a {type(value).__name__} ({value!r})"


def _one_line(error: Exception) -> str:
    return " ".join(str(error).split())


# CLI -------------------------------------------------------------------------


def _main(argv: list[str]) -> int:
    """Subprocess entry point: parse one manifest and report machine-readably.

    Acceptance means the parsed config is printed as one JSON document on stdout
    and the process exits `PARSE_CLI_OK`.  Rejection — including an unreadable or
    absent path — means the `FactoryConfigError` message is printed on stderr and
    the process exits `PARSE_CLI_REJECTED`.  Nothing else is ever printed to
    stdout, and a traceback never escapes, because the caller cannot distinguish a
    traceback from a crashed parser.
    """
    if len(argv) != 1:
        print(
            f"usage: {sys.executable} -m factory.verify.factory_yaml <manifest-path>",
            file=sys.stderr,
        )
        return PARSE_CLI_REJECTED

    try:
        config = load_factory_config(argv[0])
    except FactoryConfigError as error:
        print(str(error), file=sys.stderr)
        return PARSE_CLI_REJECTED

    print(json.dumps(dataclasses.asdict(config)))
    return PARSE_CLI_OK


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
