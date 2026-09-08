"""The judge-evidence vocabulary and refusal grammar (102-US1).

US6 of 133 moves the vocabulary half of the evidence family out of
`factory/cli/nouns/spec.py`: the closed marker vocabulary, the diff-evidence
grammar, the clause readers, the manifest-declaration reader and the function
that composes a refusal. US8 moves the report half in to join them —
`_JudgeEvidenceReport`, `_StoryCriteria`, `_BorderlineClause`,
`_borderline_warning`, `_story_criteria` and `_check_evidence` — so the whole
sixteen-name evidence family now lives in this module and no name of it remains
defined in the CLI module (FR-017). The two halves are one module because the
report half reads the vocabulary half and the vocabulary half calls nothing
back: the one seam the family had was the story boundary, not the module
boundary.

Nothing here imports from `factory.cli.nouns.spec` (plan trap 17): the CLI
module imports from `factory.spec` at module scope, so an import back re-enters
a half-initialised module before its names exist. A moved body that needs a
CLI-module name means that name moves too — which is why `_RUNTIME_MARKERS`
travels with `_runtime_markers`, the reader that is its only consumer, rather
than staying behind as a constant of the layer in the CLI module.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

import yaml

from factory.verify.criteria import parse_spec
from factory.verify.diffbounds import DIFF_INPUT_LIMIT
from factory.verify.factory_yaml import (
    FactoryConfigError,
    load_factory_config,
    resolve_manifest_path,
)
from factory.verify.models import Requirement, RequirementKind, Scenario

from factory.spec import SpecFinding as _ValidateFinding

# --- criterion evidence (102-US1) ---------------------------------------------
#
# The whole rule, because a refusal has to be able to state it (FR-005): the
# judge is shown the story's diff and the results of the gates the target
# repository declares, and nothing else. A Then-clause is refused when it
# asserts an outcome only a running system shows *and* names neither a declared
# gate nor anything the diff itself carries.
#
# What this deliberately is not is a classifier for "runtime outcome" in English
# (plan trap 3). `_RUNTIME_MARKERS` is a closed list of the ways an author has
# actually written one, and every entry names something a diff cannot contain.
# Everything else about the rule is anchored on declarations: which gates this
# repository declares, and whether the scenario points at its own evidence.
#
# It errs towards admitting. A false refusal teaches an author to phrase around
# the checker rather than to improve the spec (trap 2), and a clause naming a
# gate outcome is exactly what spec 116 makes scoreable (trap 1) — refusing
# those would leave the pair a net loss. Run across every spec in this
# repository, the vocabulary marks thirteen clauses and refuses none of them.

#: Phrase (as the refusal quotes it) → the pattern that finds it.
_RUNTIME_MARKERS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (phrase, re.compile(pattern, re.IGNORECASE))
    for phrase, pattern in (
        ("in the browser", r"in the browser"),
        ("on screen", r"on(?: the)? screen"),
        ("on the page", r"on the (?:page|site)"),
        ("in the UI", r"in the (?:UI|user interface)"),
        ("the user sees", r"(?:the|a) (?:user|visitor|reader) (?:sees|can see|will see)"),
        ("looks correct", r"looks? (?:correct|right|fine|good)"),
        (
            "renders correctly",
            r"(?:renders?|displays?|appears?|behaves?|works?) "
            r"(?:correctly|properly|as expected)",
        ),
        ("visually", r"visually"),
        ("in production", r"in production"),
        (
            "when deployed",
            r"(?:once|when|after) (?:it is |they are )?deployed|after deployment",
        ),
        ("at runtime", r"at runtime|in the running system|on the live \w+"),
        ("in CI", r"in CI\b"),
        (
            "manually verified",
            r"manual(?:ly)? (?:verif|check|confirm|observ|inspect|test)\w*"
            r"|manual (?:verification|inspection|check)",
        ),
        ("by hand", r"by (?:hand|eye|inspection)"),
        (
            "a measured duration",
            r"within \d+\s*(?:ms|milliseconds?|seconds?|minutes?)\b"
            r"|in under \d+|faster than|no slower than|takes less than",
        ),
    )
)

#: What a scenario can point at that the diff itself carries. Scanned over the
#: whole scenario, not just the clause: evidence named in a neighbouring step is
#: still evidence, and this layer's job is to catch the criterion that has none.
#: `gate` is deliberately absent — a clause is admitted by the gates a manifest
#: *declares*, never by the word.
_DIFF_EVIDENCE_RE = re.compile(
    r"proven by|committed test|\btests?\b|\bthe diff\b|paste[ds]?|artefacts?"
    r"|artifacts?|fixture|assert(?:s|ed|ing|ion|ions)?\b|\bcommitted\b",
    re.IGNORECASE,
)

#: The phrasing the refusal offers as the diff-carried alternative.
_PROVABLE_EXAMPLE = '"… — proven by a committed test"'


def _then_clauses(scenario: Scenario) -> list[str]:
    """Every `**Then**` step of one scenario, keyword stripped, lines rejoined.

    Only `**Then**` steps: a Then-clause is what the judge scores a diff against
    and what FR-001 speaks about, and widening this to the `**And**` steps that
    follow one would grow the refusal surface without an author having asked.
    """
    clauses: list[str] = []
    for step in scenario.steps:
        if not step.startswith("**Then**"):
            continue
        clause = " ".join(step[len("**Then**") :].split())
        if clause:
            clauses.append(clause)
    return clauses


def _runtime_markers(clause: str) -> list[str]:
    """The phrases in `clause` that name an outcome only a running system shows."""
    return [phrase for phrase, pattern in _RUNTIME_MARKERS if pattern.search(clause)]


def _names_a_declared_gate(clause: str, gates: frozenset[str]) -> bool:
    """True when the clause names a gate this repository actually declares."""
    return any(
        re.search(rf"\b{re.escape(gate)}\b", clause, re.IGNORECASE) for gate in gates
    )


def _manifest_declares_no_gates(path: Path) -> bool:
    """True when a readable manifest names no gate at all.

    The loader refuses such a manifest outright — schema v1 and v2 both require
    at least one gate — so this re-reads the document to tell "nothing to
    measure with" apart from "a manifest this layer could not read". They earn
    different refusals (FR-004) because they have different remedies.
    """
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return False
    if not isinstance(document, dict):
        return False
    gates = document.get("gates")
    return gates is None or (isinstance(gates, dict) and not gates)


@dataclass(frozen=True)
class _Declarations:
    """What the target repository's manifest says about verifying a node.

    One read of one manifest, answering both questions this module asks of it:
    which gates a clause may name (102-US1) and how large a diff may be before
    the story is refused unjudged (102-US2's report). Read from the declaration
    that owns them, never inferred (constitution IX).
    """

    #: The declared gate names, or None when the manifest could not be read.
    gates: frozenset[str] | None
    #: The manifest path, quoted in every refusal and in the report.
    manifest: str
    #: The size above which a story never reaches the judge, or None when the
    #: manifest could not be read — never the default in disguise.
    refusal_bytes: int | None
    #: Why the gates are unknown; empty exactly when `gates` is not None.
    reason: str


def _declared_gates(target_repo: str) -> _Declarations:
    """What the target repository declares about verification.

    `gates` is None exactly when `reason` is set, and that pair means *skip*:
    the gates are read from the manifest that owns them (constitution IX), and a
    manifest this layer cannot read has proven no clause wrong. `validate` runs
    against a `--target-repo` that need not exist on this host at all, so this
    is the ordinary case, not the exotic one (plan trap 4).

    An empty set is not that case: it is a repository whose committed manifest
    declares nothing to measure with, which is a fact worth refusing on.
    """
    path, _name = resolve_manifest_path(target_repo)
    try:
        config = load_factory_config(path)
    except FactoryConfigError as error:
        if error.rule == "gates" and _manifest_declares_no_gates(path):
            return _Declarations(frozenset(), str(path), None, "")
        return _Declarations(
            None,
            str(path),
            None,
            f"cannot read the gates {target_repo} declares: {error}",
        )
    return _Declarations(
        frozenset(config.gates), str(path), config.diff_refusal_bytes, ""
    )


def _evidence_refusal(
    scenario_id: str,
    clause: str,
    markers: list[str],
    gates: frozenset[str],
    manifest: str,
) -> str:
    """The refusal for one clause: what it says, why nothing can show it, what to do."""
    phrases = ", ".join(f'"{phrase}"' for phrase in markers)
    if gates:
        declared = ", ".join(sorted(gates))
        reason = (
            "the judge is shown the diff and the results of the gates this "
            f"repository declares ({declared}), and the clause names neither — no "
            "declared gate, and nothing the diff itself carries"
        )
        suggestion = (
            f"name a declared gate ({declared}) whose result will reach the judge "
            f"with the diff, or restate the clause as something the diff carries — "
            f"e.g. {_PROVABLE_EXAMPLE}"
        )
    else:
        reason = (
            f"{manifest} declares no gates, so no gate result will reach the judge "
            "with the diff, and the clause names nothing the diff itself carries"
        )
        suggestion = (
            f"declare in {manifest} a gate that measures this and name that gate in "
            f"the clause, or restate the clause as something the diff carries — "
            f"e.g. {_PROVABLE_EXAMPLE}"
        )
    return (
        f'{scenario_id}: "{clause}" asserts an outcome only a running system shows '
        f"({phrases}); {reason}. To make it provable: {suggestion}"
    )

# --- what the judge will be shown (102-US2) -----------------------------------
#
# FR-006 asks validate to answer, for any spec, the question US1 answers only for
# the clauses it refuses: what evidence will this spec's judge actually have?
# Three things and no fourth — the node's diff, its own story's criteria, and the
# results of the gates the target repository declares — and an author who has
# read that sentence once needs the refusal less often.
#
# It is assembled from what the layer above already computed (FR-006, plan
# sizing): the same parse, the same manifest read, the same clause
# classification. A report that re-derived its answers could disagree with the
# check printed beside it, and the disagreement would be invisible until an epic
# was spent on whichever half was wrong.
#
# The warning form (FR-007) lives here for the same reason. A clause asserting a
# runtime outcome that rests on the committed evidence its own scenario promises
# is not unprovable — the diff will carry that test — but it is the shape the
# deadlock was made of, and an author is better served by seeing it named than by
# a false refusal that teaches them to phrase around the checker (trap 2).


@dataclass(frozen=True)
class _StoryCriteria:
    """One story's scenarios: exactly what its node's judge is given to score."""

    story: str
    title: str | None
    scenarios: list[str]


@dataclass(frozen=True)
class _BorderlineClause:
    """A clause named rather than refused (FR-007)."""

    scenario_id: str
    clause: str
    phrases: list[str]
    message: str


@dataclass(frozen=True)
class _JudgeEvidenceReport:
    """What the judge will be shown for this spec (FR-006)."""

    criteria: list[_StoryCriteria]
    declarations: _Declarations
    warnings: list[_BorderlineClause]
    refused: int
    #: True when every Then-clause names evidence one of the three can produce,
    #: False when one does not, and None when the clauses were not checked at
    #: all — an unread manifest has proven nothing either way.
    all_provable: bool | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "diff": {
                "abridged_above_bytes": DIFF_INPUT_LIMIT,
                "refused_above_bytes": self.declarations.refusal_bytes,
            },
            "criteria": [asdict(story) for story in self.criteria],
            "gates": {
                "manifest": self.declarations.manifest,
                "declared": (
                    None
                    if self.declarations.gates is None
                    else sorted(self.declarations.gates)
                ),
                "reason": self.declarations.reason,
            },
            "warnings": [asdict(warning) for warning in self.warnings],
            "all_provable": self.all_provable,
        }

    def lines(self, spec_path: Path) -> list[str]:
        """The human transcript: the three answers, then anything borderline."""
        declared = self.declarations
        diff = (
            "the diff — the node's own worktree diff and nothing else: not the "
            "tree it changed, not a terminal, not the running system. Abridged "
            f"for the judge above {DIFF_INPUT_LIMIT} bytes"
        )
        if declared.refusal_bytes is not None:
            diff += (
                f", and refused unjudged above {declared.refusal_bytes} "
                f"(`diff_refusal_bytes` in {declared.manifest})"
            )
        rendered = [f"{spec_path}: what the judge will be shown for each node", f"  {diff}."]

        rendered.append(
            "  the criteria — each node is shown its own story's scenarios, "
            "snapshotted at dispatch:"
        )
        if self.criteria:
            for story in self.criteria:
                title = f" ({story.title})" if story.title else ""
                rendered.append(
                    f"    {story.story}{title} — {', '.join(story.scenarios)}"
                )
        else:
            rendered.append("    none: this spec declares no acceptance scenario")

        if declared.gates is None:
            rendered.append(f"  the gates — not known: {declared.reason}")
        elif declared.gates:
            rendered.append(
                "  the gates — the results of the gates "
                f"{declared.manifest} declares: {', '.join(sorted(declared.gates))}"
            )
        else:
            rendered.append(
                f"  the gates — none: {declared.manifest} declares nothing to "
                "measure with"
            )

        for warning in self.warnings:
            rendered.append(f"  a warning, not a refusal: {warning.message}")
        if self.all_provable:
            rendered.append(
                "  every Then-clause names evidence one of those three can produce."
            )
        return rendered


def _borderline_warning(
    scenario_id: str, clause: str, markers: list[str], gates: frozenset[str]
) -> str:
    """Name a clause that rests entirely on the evidence its scenario promises."""
    phrases = ", ".join(f'"{phrase}"' for phrase in markers)
    if gates:
        uncovered = (
            f"no gate this repository declares ({', '.join(sorted(gates))}) measures it"
        )
    else:
        uncovered = "this repository declares no gate that could measure it"
    return (
        f'{scenario_id}: "{clause}" asserts an outcome only a running system shows '
        f"({phrases}), and {uncovered}. It is not refused — its scenario names "
        "evidence the diff will carry — but the judge will score it on that "
        "evidence and on nothing else, so the committed test has to assert what "
        "the clause claims."
    )


def _story_criteria(requirements: Sequence[Requirement]) -> list[_StoryCriteria]:
    """The scenarios each story's node will be judged against."""
    return [
        _StoryCriteria(
            story=requirement.key,
            title=requirement.title,
            scenarios=[scenario.scenario_id for scenario in requirement.scenarios],
        )
        for requirement in requirements
        if requirement.kind is RequirementKind.STORY
    ]


def _check_evidence(
    spec_text: str,
    target_repo: str,
    findings: list[_ValidateFinding],
    skipped: list[dict[str, str]],
    checked: list[str],
) -> _JudgeEvidenceReport:
    """Refuse what nothing can evidence, name what is borderline, report the rest.

    102-US1's refusal (FR-001) and 102-US2's report (FR-006) are one pass over
    one parse: the scenarios the report lists are the scenarios the clauses were
    read from, and the gates it names are the gates they were measured against.
    """
    declared = _declared_gates(target_repo)

    try:
        requirements = parse_spec(spec_text)
    except Exception:
        # A spec that does not parse is already reported by the work-graph
        # layer; it declares no scenario this layer could have read. Reported
        # ahead of an unreadable manifest, as it was before the report existed:
        # a spec with no scenarios is the nearer cause.
        skipped.append(
            {
                "layer": "evidence",
                "reason": (
                    "spec.md does not parse, so it declares no acceptance scenario "
                    "to check"
                ),
            }
        )
        return _JudgeEvidenceReport([], declared, [], 0, None)

    criteria = _story_criteria(requirements)
    if declared.gates is None:
        skipped.append({"layer": "evidence", "reason": declared.reason})
        return _JudgeEvidenceReport(criteria, declared, [], 0, None)

    gates = declared.gates
    warnings: list[_BorderlineClause] = []
    refused = 0

    for requirement in requirements:
        if requirement.kind is not RequirementKind.STORY:
            continue
        for scenario in requirement.scenarios:
            carries_evidence = _DIFF_EVIDENCE_RE.search(scenario.raw_text) is not None
            for clause in _then_clauses(scenario):
                markers = _runtime_markers(clause)
                if not markers:
                    continue
                if _names_a_declared_gate(clause, gates):
                    # A declared gate can produce the evidence, and its result
                    # reaches the judge with the diff. Nothing to say (trap 1).
                    continue
                if carries_evidence:
                    warnings.append(
                        _BorderlineClause(
                            scenario_id=scenario.scenario_id,
                            clause=clause,
                            phrases=markers,
                            message=_borderline_warning(
                                scenario.scenario_id, clause, markers, gates
                            ),
                        )
                    )
                    continue
                refused += 1
                findings.append(
                    _ValidateFinding(
                        "evidence",
                        _evidence_refusal(
                            scenario.scenario_id,
                            clause,
                            markers,
                            gates,
                            declared.manifest,
                        ),
                    )
                )

    checked.append("evidence")
    return _JudgeEvidenceReport(
        criteria, declared, warnings, refused, not warnings and not refused
    )
