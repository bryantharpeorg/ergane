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

- **Execute anything.** It is a pure function over text; `load_factory_config`
  is the only line that touches a filesystem, and it exists so callers holding a
  worktree path get errors that name the file instead of an `OSError`.
- **Fill in defaults.** `timeouts` stays exactly as sparse as it was written, so
  the runner can still tell "declared 600" from "not declared" and the 600s
  default remains one knob (`VerificationConfig.gate_timeout_s`) instead of a
  value baked into every parsed manifest.
- **Normalise gate order.** `gates` keeps the file's order because the runner
  executes it in that order; sorting into the canonical `test`/`lint`/`typecheck`
  shape would spend a full test run ahead of the lint that would have failed in
  two seconds — the repo's ordering is the repo's choice.

The messages are written for an operator holding a broken file, so each one names
the source file, the `.rule` slug that was violated, and the offending value
`repr`-rendered. The `repr` is load-bearing: YAML's whole family of near-misses
is type confusion — `version: "1"` versus `version: 1`, `test: true` as a timeout
— and a message that printed `1` for both would send someone hunting the wrong
line. Bools get their own guard for the same reason: `True == 1` in Python, so a
naive `== 1` version check would accept `version: true`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from factory.verify.models import FactoryConfig, GateResult, GateStatus

#: The manifest's committed filename; callers compose `<worktree>/factory.yaml`.
MANIFEST_NAME = "factory.yaml"

#: Schema v1 fixes the gate names so component 3 can map merge-queue required
#: checks to gates 1:1. Arbitrary names are a `version: 2` conversation.
KNOWN_GATES = ("test", "lint", "typecheck")

_TOP_LEVEL_KEYS = ("version", "runtime", "gates", "timeouts")

_SUPPORTED_VERSION = 1


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

    # Unknown keys are checked before the required ones: a manifest that says
    # `image:` where it means `runtime:` has two defects, and naming the typo
    # points at the line that is actually wrong.
    _reject_unknown_keys(document, source)
    version = _read_version(document, source)
    runtime = _read_runtime(document, source)
    gates = _read_gates(document, source)
    timeouts = _read_timeouts(document, gates, source)

    return FactoryConfig(
        version=version, runtime=runtime, gates=gates, timeouts=timeouts
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


def _reject_unknown_keys(document: Mapping[Any, Any], source: str) -> None:
    unknown = [key for key in document if key not in _TOP_LEVEL_KEYS]
    if unknown:
        raise FactoryConfigError(
            "unknown_key",
            f"declares {_names(unknown)} at the top level; schema v1 knows only "
            f"{_names(_TOP_LEVEL_KEYS)}",
            source=source,
        )


def _read_version(document: Mapping[Any, Any], source: str) -> int:
    if "version" not in document:
        raise FactoryConfigError(
            "version",
            "declares no `version`; schema v1 requires the integer literal "
            f"`version: {_SUPPORTED_VERSION}`",
            source=source,
        )
    version = document["version"]
    # `isinstance(True, int)` is True, and YAML spells booleans `true`, so the
    # bool has to be excluded by type identity or `version: true` slips through.
    if type(version) is not int or version != _SUPPORTED_VERSION:
        raise FactoryConfigError(
            "version",
            f"declares `version: {version!r}`; this factory supports only the "
            f"integer literal {_SUPPORTED_VERSION}",
            source=source,
        )
    return version


def _read_runtime(document: Mapping[Any, Any], source: str) -> str:
    if "runtime" not in document:
        raise FactoryConfigError(
            "runtime",
            "declares no `runtime`; schema v1 requires a container image "
            "reference, e.g. `runtime: python:3.11-bookworm`",
            source=source,
        )
    runtime = document["runtime"]
    if not isinstance(runtime, str) or not runtime.strip():
        raise FactoryConfigError(
            "runtime",
            f"declares `runtime: {runtime!r}`; it must be a non-empty container "
            "image reference, e.g. `python:3.11-bookworm`",
            source=source,
        )
    return runtime


def _read_gates(document: Mapping[Any, Any], source: str) -> dict[str, str]:
    if "gates" not in document:
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
            f"name to command, with names drawn from {_names(KNOWN_GATES)}",
            source=source,
        )
    if not gates:
        raise FactoryConfigError(
            "gates",
            f"declares an empty `gates` mapping; at least one of "
            f"{_names(KNOWN_GATES)} must be present",
            source=source,
        )
    unknown = [name for name in gates if name not in KNOWN_GATES]
    if unknown:
        raise FactoryConfigError(
            "gates",
            f"declares the gate(s) {_names(unknown)}; schema v1 fixes the gate "
            f"names to {_names(KNOWN_GATES)} so merge-queue required checks map "
            "to them 1:1",
            source=source,
        )

    for name, command in gates.items():
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
