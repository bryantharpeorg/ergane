"""The roadmap's types, the frontmatter reader, and readiness computation.

US1's grammar is the deriver's discipline applied one level up. Every spec
declares its intent — `draft`, `ready`, `deferred`, or attested `landed` — in a
frontmatter block on the spec itself, and the reader turns a `specs/` corpus
into a graph of `SpecEntry`s with `depends_on_landed` edges. Three properties
carry the weight, and each is a rule the existing workgraph deriver already
enforces one level down:

- **The field is additive (FR-002).** A spec with no frontmatter reads `draft`,
  so adopting the grammar never invalidates or alters the meaning of any
  existing spec. Frontmatter is the new field only; the `**Status**:` prose lines
  that specs already carry are dead text the reader never consults (plan § US1
  trap — 006's is a four-sentence paragraph that *looks* like state and is not).
- **Rejection names the offender and the file (FR-001).** Unknown keys and
  unknown state values are refused rather than silently dropped — silently
  dropping a key an author wrote is how a roadmap comes to mean something other
  than it says. Every finding names the offending key or value *and* the file
  it came from, the `unknown_key` rule one level up.
- **The reader is pure over the corpus.** `read_roadmap` walks the `specs/`
  root it is handed and reads each `spec.md`, and nothing else — no registry,
  no `personas.yaml`, no Temporal. Purity is what makes the grammar unit-testable
  without infrastructure, the `test_derivation_opens_no_file` pattern.

Readiness (FR-003) is computed, never declared: a spec is dispatchable only when
`state: ready` *and* every `depends_on_landed` edge is satisfied. Satisfaction
has two kinds, and they MUST be distinguishable in reporting:

- **attested** — the dependency's own frontmatter carries `state: landed`, the
  operator's attestation for work that predates the roadmap (001/002/005 were
  never epics; nothing will ever observe them landing).
- **observed** — a child epic returned COMPLETED with every landing MERGED,
  derived from Temporal and git. This kind arrives in US2; the seam for it (the
  `landed_for` resolver) exists now so US2 does not have to restructure the graph
  to add it.

The states are `StrEnum` for the same reason `workgraph/models.py` spells them
that way: Temporal's JSON converter's *deserializer* rebuilds a field annotated
with any other str-subclass enum as a list of one-character strings. The
roadmap workflow (US2/US3) will carry these across activity boundaries, so the
spelling that round-trips is the one to start with.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Callable, Mapping, Sequence

import yaml

from factory.workgraph.models import find_cycle

#: The spec file every epic is compiled from — the same convention as
#: `factory/workgraph/cli.py`'s `SPEC_NAME`. The roadmap reads `specs/<dir>/spec.md`.
SPEC_NAME = "spec.md"

#: The frontmatter fence: a leading pair of `---` lines, YAML between. This is
#: the Spec Kit / Jekyll frontmatter convention, distinct from the fenced code
#: blocks the criteria parser masks (`mask_fences` treats only backtick/tilde
#: as fences, so `---` is inert to that scanner — verified in T002).
_FRONTMATTER_FENCE = "---"


class SpecState(StrEnum):
    """The intent a spec's frontmatter declares (FR-001).

    `draft` is the default for a spec with no frontmatter (FR-002) — the field
    is additive. `ready` is the operator's declaration that the spec may
    dispatch once its edges are satisfied. `deferred` parks a spec out of the
    build order by operator choice. `landed` is an *attestation* for work that
    predates the roadmap: 001/002/005 were never epics, so nothing will ever
    observe them landing, and the operator may write `state: landed` to close
    their edges (the one deliberate exception the story calls out).

    `building` is deliberately absent: only the system may say `building`, and
    an author who writes `state: building` is rejected (`unknown_state`) rather
    than honoured — intent is declared, progress is observed.
    """

    DRAFT = "draft"
    READY = "ready"
    DEFERRED = "deferred"
    LANDED = "landed"


#: Read-only computed state rendered by `compute_readiness` and the roadmap CLI.
#: Not a writable `SpecState` value — an author who writes `state: amended`
#: is rejected (`unknown_state`), because intent is declared and drift is observed.
RENDERED_AMENDED = "amended"


class LandedKind(StrEnum):
    """The two kinds of dependency satisfaction (FR-003), distinguishable in reporting.

    `ATTESTED` is a frontmatter `state: landed` — the operator's word. `OBSERVED`
    is a child epic that returned COMPLETED with every landing MERGED — derived
    from Temporal and git (US2's input). The two travel in `LandedStatus.kind` so
    a report can say *why* an edge is satisfied, not just that it is.
    """

    ATTESTED = "attested"
    OBSERVED = "observed"


#: Every key a spec's frontmatter may carry. Closed by design (FR-001): the
#: frontmatter rides `PromptSources.spec_text` whole into agent payloads, so a
#: closed key set is what keeps payload-borne text provably inert (FR-009, US2).
#: `state` is required-in-spirit (a spec with no frontmatter reads `draft`, but
#: a frontmatter block that is a mapping yet omits `state` is rejected rather
#: than guessed at — an author who wrote a block meant to say something).
_KNOWN_KEYS = ("state", "depends_on_landed")

#: The values `state` may take — the members of `SpecState`, spelled out so a
#: rejection can name the offender without a runtime enum walk producing
#: member names an operator never typed.
_STATE_VALUES = frozenset(member.value for member in SpecState)


@dataclass(frozen=True)
class SpecEntry:
    """One spec's declared intent, parsed from its frontmatter (FR-001).

    `spec_dir` is the directory name under `specs/` — the roadmap's identity
    for a spec, and the value `depends_on_landed` names. `state` is the declared
    intent (defaulting to `draft` when no frontmatter is present, FR-002).
    `depends_on_landed` is the list of spec dirs this spec waits on as *landed*;
    it is the spec-level analogue of the workgraph's node-level
    `depends_on_merged`, the vocabulary precedent the plan names.
    """

    spec_dir: str
    state: SpecState
    depends_on_landed: list[str]
    #: The file the entry was read from, for findings that name it. Empty for a
    #: synthesized entry (none in US1; the reader always has a file).
    source: str = ""


@dataclass(frozen=True)
class Roadmap:
    """The whole corpus parsed: every spec, in sorted order of spec dir.

    Sorted order is the deterministic order the render prints and the operator
    reads — the same order a directory listing gives, so two operators see the
    same roadmap. `entries` is the whole graph; `findings` is empty when every
    spec's frontmatter is well-formed, and `read_roadmap` raises before
    returning a roadmap that carries any finding (a broken corpus yields no
    partial roadmap — the deriver's "emits nothing on failure" discipline).
    """

    specs_root: str
    entries: list[SpecEntry]


@dataclass(frozen=True)
class RoadmapFinding:
    """One refused spec: which rule, which spec, and what is wrong.

    `rule` is the slug (`unknown_key`, `unknown_state`, `non_mapping`,
    `dangling_dep`, `cycle`), `spec_dir` names the offending spec's directory,
    and `problem` is the sentence an operator reads. Both `spec_dir` and the
    offender appear in `str(finding)` so the render can name the file *and* the
    key/value the author has to fix — never a bare "rejected".
    """

    rule: str
    spec_dir: str
    problem: str

    def __str__(self) -> str:
        return f"{self.spec_dir}: [{self.rule}] {self.problem}"


class RoadmapError(ValueError):
    """A corpus that does not parse, and every reason why (FR-001).

    Carries the whole list: emitting the well-formed specs of a broken corpus
    would be the worst outcome available — a roadmap that looks usable while the
    one broken spec is silent. The render refuses to print a partial roadmap
    and reports every finding at once, so an author fixing one typo per run is
    the failure mode collection exists to avoid.
    """

    def __init__(self, findings: Sequence[RoadmapFinding]) -> None:
        self.findings = list(findings)
        count = len(self.findings)
        noun = "spec" if count == 1 else "specs"
        detail = "\n".join(f"  - {finding}" for finding in self.findings)
        super().__init__(
            f"the roadmap corpus does not parse ({count} {noun} rejected):\n{detail}"
        )


# --- the staged collector (the deriver's `_Rejections` discipline) ------------


@dataclass
class _Findings:
    """The collector, staged so a defect upstream is not reported twice.

    A frontmatter block that is not a mapping has no `state` to type-check, and
    a `depends_on_landed` naming no spec directory has no edge to cycle-check,
    so each defect yields exactly one finding: shape before cross-validation,
    cross-validation before the acyclic check — the same staging the deriver's
    `_Rejections` makes readable.
    """

    collected: list[RoadmapFinding] = field(default_factory=list)

    def add(self, rule: str, spec_dir: str, problem: str) -> None:
        self.collected.append(
            RoadmapFinding(rule=rule, spec_dir=spec_dir, problem=problem)
        )

    def raise_if_any(self) -> None:
        if self.collected:
            raise RoadmapError(self.collected)


# --- the pure frontmatter reader ----------------------------------------------


def _split_frontmatter(text: str) -> tuple[str | None, str]:
    """The leading frontmatter block (YAML text, fences stripped), or None.

    Frontmatter is a leading `---` fence pair at the very top of the file: the
    first line must be exactly `---`, and the block closes at the next line
    that is exactly `---`. Anything else — no leading fence, or a file that
    starts with prose — means no frontmatter, and the spec reads `draft`
    (FR-002). A single `---` with no closing fence is also no frontmatter:
    the conservative direction is `draft`, not a parse error.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FRONTMATTER_FENCE:
        return None, text
    for index in range(1, len(lines)):
        if lines[index].strip() == _FRONTMATTER_FENCE:
            return "\n".join(lines[1:index]), "\n".join(lines[index + 1 :])
    # Unclosed fence: treat as no frontmatter (FR-002's conservative direction).
    return None, text


def _parse_frontmatter(
    text: str, spec_dir: str, findings: _Findings
) -> dict | None:
    """Load one frontmatter block as a mapping, or record why it is not one.

    Returns the loaded mapping on success, `None` on a shape failure (so the
    caller knows there is nothing to cross-validate). YAML parse errors and
    non-mapping values are rejected naming the file — the audience is an
    author who has to go edit one block of one spec.
    """
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as error:
        findings.add(
            "non_mapping",
            spec_dir,
            f"frontmatter is not valid YAML: {error}",
        )
        return None

    if loaded is None:
        # An empty frontmatter block (`---\n---`) is a mapping with no keys —
        # treated as no declaration, which reads `draft` (FR-002). An author
        # who wrote the fences but nothing inside meant nothing by it.
        return {}
    if not isinstance(loaded, dict):
        findings.add(
            "non_mapping",
            spec_dir,
            f"frontmatter must be a mapping of {', '.join(_KNOWN_KEYS)}, "
            f"got {type(loaded).__name__}",
        )
        return None
    return loaded


def _shape_entry(
    block: Mapping[str, object], spec_dir: str, findings: _Findings
) -> SpecEntry | None:
    """Shape one frontmatter mapping into a `SpecEntry`, or record why it has none.

    Shape errors stop this spec from being cross-validated at all: a block with
    an unknown key has no grammar to honour, and reporting both "unknown key"
    and "unknown state" for one typo would send the author to two lines to fix
    one. The closed key set is `_KNOWN_KEYS`; `state` is required when a block
    is present (an empty block reads `draft`, but a non-empty block that omits
    `state` is rejected — an author who wrote something meant to say something).
    """
    unknown = [key for key in block if key not in _KNOWN_KEYS]
    if unknown:
        findings.add(
            "unknown_key",
            spec_dir,
            f"frontmatter carries unknown key(s) {_quoted(unknown)}; "
            f"the grammar is {_quoted(list(_KNOWN_KEYS))}",
        )
        return None

    state_value = block.get("state")
    if state_value is None:
        findings.add(
            "unknown_state",
            spec_dir,
            f"frontmatter omits 'state'; it is one of "
            f"{_quoted(sorted(_STATE_VALUES))} (a spec with no frontmatter "
            "reads 'draft', but a block that says nothing else is not a "
            "declaration)",
        )
        return None

    if not isinstance(state_value, str) or state_value not in _STATE_VALUES:
        findings.add(
            "unknown_state",
            spec_dir,
            f"'state' must be one of {_quoted(sorted(_STATE_VALUES))}, "
            f"got {state_value!r} — only the system may say 'building'; the "
            "author's vocabulary is the four intent states",
        )
        return None

    deps = block.get("depends_on_landed", [])
    if deps is None:
        deps = []
    if not isinstance(deps, list) or not all(isinstance(item, str) for item in deps):
        findings.add(
            "unknown_key",
            spec_dir,
            f"'depends_on_landed' must be a list of spec dirs, got {deps!r}",
        )
        return None

    return SpecEntry(
        spec_dir=spec_dir,
        state=SpecState(state_value),
        depends_on_landed=list(deps),
    )


def _cross_validate(
    entries: Mapping[str, SpecEntry], findings: _Findings
) -> None:
    """Every rule that needs the whole corpus: dangling edges, then cycles.

    A `depends_on_landed` entry naming no spec directory in the corpus is
    rejected — an edge to nothing can never be satisfied, and silently ignoring
    it would let a typo pass as "blocked" forever (the deriver's discipline,
    one level up). The acyclic check runs only against a graph whose edges all
    resolve, so a dangling edge is not also reported as a cycle it cannot be on.
    """
    declared = set(entries)
    for entry in entries.values():
        unknown = [dep for dep in entry.depends_on_landed if dep not in declared]
        if unknown:
            findings.add(
                "dangling_dep",
                entry.spec_dir,
                f"depends on {_quoted(unknown)}, which no spec directory in "
                "this corpus names — an edge to nothing can never be satisfied",
            )
    findings.raise_if_any()

    adjacency = {
        entry.spec_dir: list(entry.depends_on_landed) for entry in entries.values()
    }
    cycle = find_cycle(adjacency)
    if cycle is not None:
        findings.add(
            "cycle",
            cycle[0],
            "these specs wait on each other and none can ever dispatch: "
            + " -> ".join(cycle),
        )
    findings.raise_if_any()


def read_roadmap(specs_root: str | Path) -> Roadmap:
    """Read a `specs/` corpus into a roadmap graph, or raise naming every fault.

    Walks `<specs_root>/<spec-dir>/spec.md` for every direct child directory,
    parses each spec's leading frontmatter (or reads `draft` when none is
    present, FR-002), shapes every entry, then cross-validates the corpus
    (dangling edges, then cycles). A corpus with any finding raises
    `RoadmapError` and yields no partial roadmap — the same "emits nothing on
    failure" discipline as the deriver.

    Entries are returned in sorted order of `spec_dir`, the deterministic order
    the render prints.
    """
    root = Path(specs_root)
    findings = _Findings()
    entries: dict[str, SpecEntry] = {}

    spec_dirs = sorted(
        path for path in root.iterdir() if path.is_dir() and not path.name.startswith(".")
    )
    for spec_dir_path in spec_dirs:
        spec_dir = spec_dir_path.name
        spec_path = spec_dir_path / SPEC_NAME
        if not spec_path.is_file():
            # A directory with no spec.md is not a spec the roadmap tracks;
            # skip it rather than rejecting — the corpus is what has specs.
            continue
        text = spec_path.read_text(encoding="utf-8")
        block_text, _body = _split_frontmatter(text)
        if block_text is None:
            # No frontmatter: reads `draft` (FR-002). No edges to wait on.
            entries[spec_dir] = SpecEntry(
                spec_dir=spec_dir,
                state=SpecState.DRAFT,
                depends_on_landed=[],
                source=str(spec_path),
            )
            continue

        block = _parse_frontmatter(block_text, spec_dir, findings)
        if block is None:
            continue
        entry = _shape_entry(block, spec_dir, findings)
        if entry is not None:
            entries[spec_dir] = SpecEntry(
                spec_dir=entry.spec_dir,
                state=entry.state,
                depends_on_landed=entry.depends_on_landed,
                source=str(spec_path),
            )

    findings.raise_if_any()
    _cross_validate(entries, findings)

    return Roadmap(
        specs_root=str(root),
        entries=[entries[name] for name in sorted(entries)],
    )


# --- readiness computation (FR-003) ------------------------------------------


@dataclass(frozen=True)
class LandedStatus:
    """Whether a spec is landed, and how it is known to be (FR-003).

    The seam US2 fills: `landed_for` returns a `LandedStatus` for a spec dir the
    live record (Temporal + git) reports as landed, and `None` when it does not.
    US1's default resolver consults only the frontmatter (attestation), so this
    type's `observed` path is exercised by the resolver US2 injects — the seam
    exists now so US2 does not restructure the graph to add it.
    """

    landed: bool
    kind: LandedKind


#: The default resolver: a spec is landed iff its own frontmatter attests it.
#: Observed-landed (US2) is supplied by overriding `landed_for` in
#: `compute_readiness`; at US1 the frontmatter is the only source of truth.
def _attested_resolver(roadmap: Roadmap) -> Callable[[str], LandedStatus | None]:
    states = {entry.spec_dir: entry.state for entry in roadmap.entries}

    def resolve(spec_dir: str) -> LandedStatus | None:
        if states.get(spec_dir) is SpecState.LANDED:
            return LandedStatus(landed=True, kind=LandedKind.ATTESTED)
        return None

    return resolve


@dataclass(frozen=True)
class SpecReadiness:
    """One spec's computed readiness: dispatchable, blockers, drift, and why satisfied.

    `dispatchable` is `True` only when `state == ready` and every
    `depends_on_landed` edge is satisfied (FR-003). `blockers` names the
    unsatisfied edges — never a bare "blocked" (acceptance scenario 5).
    `satisfied_as` maps each satisfied dependency to its `LandedKind`, so a
    report can say *why* an edge is satisfied (attested vs observed), the two
    kinds FR-003 requires to be distinguishable. `blockers` and
    `satisfied_as` are disjoint: an edge is either satisfied (named in
    `satisfied_as`) or a blocker (named in `blockers`), never both.

    `drifted` is US4's read-only signal: the frontmatter says `landed` but the
    injected resolver reports the spec's fingerprints differ from their landing
    baseline. An amended spec is not dispatchable until the operator flips it to
    `ready`, and the render shows `amended` rather than `landed` (FR-009).
    `rendered_state` is the state an operator sees: `amended` when `drifted` and
    the declared state is `landed`, otherwise the declared `state` value.
    """

    spec_dir: str
    state: SpecState
    dispatchable: bool
    blockers: list[str]
    satisfied_as: dict[str, LandedKind]
    drifted: bool = False

    @property
    def rendered_state(self) -> str:
        """The state the render prints: `amended` overrides a drifted `landed`."""
        if self.drifted and self.state is SpecState.LANDED:
            return RENDERED_AMENDED
        return self.state.value


@dataclass(frozen=True)
class Readiness:
    """The whole roadmap's computed readiness, indexed by spec dir.

    `compute_readiness` is pure over the roadmap and the `landed_for` resolver:
    same roadmap + same resolver → same readiness, the determinism the render
    relies on. `spec` looks up one entry; `specs` iterates the whole corpus in
    sorted order.
    """

    specs: list[SpecReadiness]

    def spec(self, spec_dir: str) -> SpecReadiness:
        for readiness in self.specs:
            if readiness.spec_dir == spec_dir:
                return readiness
        raise KeyError(spec_dir)


def compute_readiness(
    roadmap: Roadmap,
    *,
    landed_for: Callable[[str], LandedStatus | None] | None = None,
    drifted_for: Callable[[str], bool] | None = None,
) -> Readiness:
    """Compute dispatchability and drift for every spec (FR-003, FR-009).

    A spec is dispatchable iff `state == ready` and every `depends_on_landed`
    entry is satisfied — satisfied means observed-landed (US2's resolver) or
    attested (`state: landed` in that spec's own frontmatter). The two kinds are
    reported distinctly in `SpecReadiness.satisfied_as`.

    `landed_for` is the seam for dependency satisfaction. `drifted_for` is the
    US4 seam for drift: it returns `True` when the frontmatter says `landed` but
    the spec's current fingerprints differ from their landing baseline. Drift is
    read-only: a drifted spec renders as `amended` and is not dispatchable until
    the operator flips `state` to `ready`. Both resolvers are injected so git
    reads stay out of workflow code (constitution IV).
    """
    attested = _attested_resolver(roadmap)
    observed = landed_for if landed_for is not None else (lambda spec_dir: None)
    drift_resolver = drifted_for if drifted_for is not None else (lambda spec_dir: False)

    specs: list[SpecReadiness] = []
    for entry in roadmap.entries:
        blockers: list[str] = []
        satisfied_as: dict[str, LandedKind] = {}
        for dependency in entry.depends_on_landed:
            status = observed(dependency)
            if status is None or not status.landed:
                status = attested(dependency)
            if status is not None and status.landed:
                satisfied_as[dependency] = status.kind
            else:
                blockers.append(dependency)

        dispatchable = entry.state is SpecState.READY and not blockers
        drifted = drift_resolver(entry.spec_dir) if entry.state is SpecState.LANDED else False
        specs.append(
            SpecReadiness(
                spec_dir=entry.spec_dir,
                state=entry.state,
                dispatchable=dispatchable,
                blockers=blockers,
                satisfied_as=satisfied_as,
                drifted=drifted,
            )
        )
    return Readiness(specs=specs)


# --- helpers -----------------------------------------------------------------


def _quoted(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)