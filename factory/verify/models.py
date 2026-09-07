"""The types every other module in this component speaks.

One dataclass per entity in data-model.md, frozen so a value that crossed an
activity boundary can never be edited in place, and plain enough that Temporal's
default JSON converter round-trips them without help. Enums are `StrEnum`
specifically, not the older `class X(str, Enum)` spelling: both serialize as
their value and both bind as a SQLite TEXT parameter, but only `StrEnum` is
recognised by the converter's *deserializer*, which rebuilds a field annotated
with any other str-subclass enum as a list of one-character strings — a `PASS`
that silently arrives as `['P', 'A', 'S', 'S']` and compares equal to nothing.
The values are UPPERCASE because that is what the evidence store's CHECK
constraints accept (contracts/verification-store.sql).

Three invariants show up here as types rather than as checks:

- There is no third overall verdict. `OverallVerdict` has exactly PASS and FAIL
  because those are the only two values edge unlocking can read (FR-005) — a
  judge that was unreachable is a PASS carrying `judge_unavailable`, not a
  separate "unknown" that downstream code could accidentally treat as passing.
- `None` on `VerificationResult.judge` means *the judge never ran* — gates failed
  (cheapest-first) or the node has no scenarios — never "ran and said nothing".
  A judge that ran and failed to be parsed is a `JudgeVerdict` with outcome FAIL.
- Config errors are a `GateStatus`, not an exception. A missing or malformed
  `factory.yaml` comes back as gate data so the verdict truth table sees it and
  fails; there is no path where the absence of gates means "nothing to check".

Validation lives where the decision is made, not here: the criteria parser raises
on grammar violations, `factory_yaml` rejects bad manifests, the store's CHECK
constraints backstop the persisted shape, and these stay dumb carriers.

The one behaviour that does live here is composition. `compose_result` is where
those three invariants stop being prose and become the single `OverallVerdict`
that edge unlocking reads, and `judge_required` is most of the same rule asked one
step earlier — before the judge has been paid for. Both are pure, and both live
beside the types rather than in the activity that calls them, because a verdict
assembled two different ways by two different callers is a verdict with two
definitions.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from functools import lru_cache
from typing import Sequence

# Imported for real, not named in a string. `EscalationRecord.check_evidence`
# used to annotate `tuple["factory.mergequeue.models.CheckFailure", ...]` in a
# module that imported no `factory` name at all: `from __future__ import
# annotations` deferred the lookup, so the mistake was invisible until something
# called `typing.get_type_hints(EscalationRecord)` and got `NameError` (041
# FR-014, `verify/escalation-record-annotation-cannot-resolve`). The import is
# safe in both directions — `factory.mergequeue.models` imports nothing from
# `factory` — and an annotation that resolves is the only kind worth writing.
from factory.config import DETERMINISTIC_AGENT, SUBSCRIPTION_AGENT
from factory.mergequeue.models import CheckFailure


class RequirementKind(StrEnum):
    """What a parsed requirement is (D-023).

    STORY carries acceptance scenarios and is what the judge scores; FUNCTIONAL
    is a declarative `- **FR-###**:` bullet with no scenarios of its own.
    """

    STORY = "STORY"
    FUNCTIONAL = "FUNCTIONAL"


class GateStatus(StrEnum):
    """Outcome of one deterministic gate command.

    `CONFIG_ERROR` covers a missing or malformed `factory.yaml`: it is a status
    rather than a raised error so it flows through the verdict truth table and
    fails the verification — never pass-by-default.

    `DIRTIED_WORKTREE` is the same argument one step further in (084 FR-004):
    the command exited 0, but running it changed the worktree the judge's patch
    is assembled from, so the gate edited the evidence it was scored on. It is a
    status rather than a quiet boolean on a PASS row for two reasons that both
    bite. `gates_passed` refuses anything that is not PASS, so the deterministic
    half fails with no edit to the decider that owns it; and the retry prompt
    `continue`s past every PASS gate (`factory/workgraph/prompt.py:693-695`), so
    a marker on a PASS row would be invisible to the next attempt — the failure
    shape recorded at `factory/workgraph/prompt.py:722-724`. A worktree whose
    snapshot git refused takes this status too: a tree the check could not read
    is a tree it cannot report as clean (084 FR-006).
    """

    PASS = "PASS"
    FAIL = "FAIL"
    TIMEOUT = "TIMEOUT"
    CONFIG_ERROR = "CONFIG_ERROR"
    DIRTIED_WORKTREE = "DIRTIED_WORKTREE"


class JudgeOutcome(StrEnum):
    """The judge's bounded contribution (FR-003).

    RETRY and FAIL both compose to an overall FAIL; they differ only in what the
    ladder does next. UNAVAILABLE means the model or backend stayed down through
    the in-activity retries — the one outcome that does not block a PASS.
    """

    PASS = "PASS"
    RETRY = "RETRY"
    FAIL = "FAIL"
    UNAVAILABLE = "UNAVAILABLE"


class OverallVerdict(StrEnum):
    """The composed verdict — the only thing edge unlocking may read (FR-005)."""

    PASS = "PASS"
    FAIL = "FAIL"


class VerificationForm(StrEnum):
    """Whether verification ran as a node's built-in phase or as an explicit
    verifier node (FR-002). Part of the evidence store's upsert key, so one
    attempt can carry both without collision."""

    PHASE = "PHASE"
    NODE = "NODE"


class NextAction(StrEnum):
    """Output of the pure retry ladder — a decision, not a side effect."""

    PASSED = "PASSED"
    RETRY = "RETRY"
    PROMOTE = "PROMOTE"
    DEBUGGER = "DEBUGGER"
    ESCALATE = "ESCALATE"
    KILLED = "KILLED"


class EscalationChoice(StrEnum):
    """Operator options on an escalation, 1:1 with the inline buttons (FR-008).

    Values stay short because they ride inside `callback_data`
    (`esc:<12-hex>:<choice>`), which Telegram caps at 64 bytes.

    Three of the four end the node — everything that is not `RETRY` does, see
    `ladder._ends_the_node` — and they differ in what they do to the *epic*,
    which is the distinction 068 FR-008 exists to make. `KILL` leaves the epic
    running its other nodes; `KILL_EPIC` ends it, which before now meant
    pressing `KILL` on every node's page and reaching for `temporal workflow
    terminate` anyway; `PAUSE_EPIC` is neither, parking the epic resumably with
    its undispatched nodes still ahead of it (spec § Edge Cases).
    """

    RETRY = "RETRY"
    KILL = "KILL"
    PAUSE_EPIC = "PAUSE_EPIC"
    KILL_EPIC = "KILL_EPIC"


# Criteria entities (parser output — pure, snapshot-able) --------------------


@dataclass(frozen=True)
class Scenario:
    """One numbered acceptance scenario of a user story.

    `scenario_id` (`US<n>-S<k>`) is an identity the judge must echo back exactly,
    which is how per-scenario scoring is enforced instead of a holistic verdict.
    `steps` holds the bold Given/When/Then/And segments in order; `raw_text` keeps
    the whole list item verbatim so the prompt can quote the source, not a
    reconstruction of it.
    """

    scenario_id: str
    steps: list[str]
    raw_text: str


@dataclass(frozen=True)
class Requirement:
    """A requirement extracted from a Spec Kit feature spec.

    `key` is the identity (`US<n>` or `FR-###`) that a node requests by name.
    `title` and `priority` come from the story header and are None for
    FUNCTIONAL; `scenarios` is empty for FUNCTIONAL and — per the parser's
    validation rules — non-empty for STORY.
    """

    key: str
    kind: RequirementKind
    title: str | None
    priority: str | None
    body: str
    scenarios: list[Scenario] = field(default_factory=list)


@dataclass(frozen=True)
class CriteriaSet:
    """The dispatch-time snapshot a node is verified against (FR-010).

    `requirements` is already filtered to the keys the node requested, so the
    judge prompt is built from exactly what this node owes. `source_sha256` is
    the hash of the spec file's raw bytes at snapshot time: re-hashing at verify
    time is how drift is detected, and drift only ever flags a result — it never
    re-snapshots mid-node and never changes a verdict.
    """

    feature: str
    spec_ref: str
    requirements: list[Requirement]
    source_path: str
    source_sha256: str
    snapshotted_at: str


# Gate entities --------------------------------------------------------------


@dataclass(frozen=True)
class RoadmapDials:
    """What the repo declares about its own scheduler (034 FR-015).

    These are the values `ergane init` writes onto the repo's Temporal schedule
    and reconciles on every re-run. They live in the committed manifest because
    the alternative is where they lived before: inside a base64-encoded workflow
    payload on the schedule, changeable only by hand-editing it — which is why
    `max_concurrent_epics` on the one hand-made roadmap was never changed.

    `cadence_s` is how often a tick starts a roadmap run; the two concurrency
    bounds pass through to `RoadmapInput` unaltered.
    """

    cadence_s: int = 300
    max_concurrent_epics: int = 1
    max_concurrent_nodes: int = 1


@dataclass(frozen=True)
class CacheDeclaration:
    """One cache a repository declares its gates need carried (101 FR-004).

    `HOME` inside the gate boundary is a tmpfs, which is the property that makes
    a gate's writes visible and its environment reproducible — and the property
    that empties every package manager's cache. The factory has carried one cache
    across that boundary since `_cache_binds` was written, and carried exactly
    one: `~/.cache/uv`, a literal path in factory code. A repository with a
    JavaScript world got a boundary that re-downloads on every gate run, or
    failed where the host would have passed. This is that literal, made
    declarable.

    `path` is absolute and already resolved, symlinks included, because the check
    that bounds it to the operator's home is only meaningful against the path the
    kernel will actually mount (101 trap 3): a boundary that validated the
    declared spelling and mounted the resolved one would be validating something
    it does not mount.

    `env` is the variable the tool reads to find its cache, or `None` when the
    tool needs no telling. It exists for the reason `UV_CACHE_DIR` exists and is
    set beside its own bind for the same one — a tool that derives its cache
    location from `HOME` looks inside the tmpfs no matter what is mounted next to
    it, so binding without naming buys nothing (FR-008).
    """

    path: str
    env: str | None = None


def _default_ladder() -> "VerificationConfig":
    """Deferred default so `VerificationConfig` need not move above `FactoryConfig`."""
    return VerificationConfig()


def _default_diff_refusal_bytes() -> int:
    """The refusal threshold a manifest that declares none resolves to (092 FR-004).

    Deferred, and imported here rather than restated: `factory.verify.diffbounds`
    owns the number and imports *this* module for its own record types, so a
    module-level import would close the cycle. A literal would close nothing and
    cost more — it would be the second copy of the threshold that 092's trap 2
    exists to prevent, and tuning `DIFF_REFUSAL_THRESHOLD` would then move every
    declared manifest while leaving every silent one where it was.
    """
    from factory.verify.diffbounds import DIFF_REFUSAL_THRESHOLD

    return DIFF_REFUSAL_THRESHOLD


@dataclass(frozen=True)
class FactoryConfig:
    """The target repo's committed `factory.yaml`, schema v1 or v2.

    `runtime` is recorded but execution-reserved — gates run as `bash -c` on the
    worker for now (R3), and keeping the field means the manifest does not have
    to change when containerized execution lands. `timeouts` is sparse: a gate
    with no entry uses `VerificationConfig.gate_timeout_s`.

    `standards` (added by 005, research R11) names the repo's coding-standards
    document, relative to the repo root, for prompt assembly to point an agent
    at. It stays a path rather than the document's text because the agent reads
    it in-worktree — the same committed file the gates see. `None` means the
    repo declared none, which is why it is nullable rather than empty-string
    defaulted: prompt assembly emits the read-and-obey directive iff it was
    declared, and existence is checked at dispatch, not here.
    """

    version: int
    runtime: str
    gates: dict[str, str]
    timeouts: dict[str, int] = field(default_factory=dict)
    #: 084 FR-009. The gates this repo declares as legitimate writers, sparse
    #: the way `timeouts` is: a gate with no entry, and a gate whose entry is
    #: `false`, are both undeclared. A declared gate keeps PASS when it writes
    #: (FR-010) — the declaration moves the verdict, never the recording, so the
    #: paths it wrote stay on its `GateResult` either way.
    writes: dict[str, bool] = field(default_factory=dict)
    standards: str | None = None
    landing_branch: str = "main"
    #: 034 FR-015. `None` means the repo declared no `roadmap:` block, which is
    #: not the same as declaring the defaults: `ergane init` re-runs must be
    #: able to tell "the operator left this alone" from "the operator chose
    #: 300", or an untouched manifest grows a key it never asked for and FR-005's
    #: byte-identity claim stops holding.
    roadmap: "RoadmapDials | None" = None
    #: 049 FR-014. The forge this repository is on. Resolved rather than
    #: nullable — absent means `github`, which is what every repository that
    #: exists is on, so a reader asking "which forge?" always gets an answer and
    #: never has to know the default itself. The literal repeats
    #: `factory.verify.factory_yaml.DEFAULT_FORGE_NAME` because importing it
    #: here would close a cycle through `factory.verify.gates`; the two
    #: spellings are pinned together by `tests/test_forge_manifest.py`.
    forge: str = "github"
    #: 023 FR-002. Retry-ladder caps declared by the repo. Absent means today's
    #: defaults, which is why the default reproduces `VerificationConfig()`.
    ladder: "VerificationConfig" = field(default_factory=_default_ladder)
    #: 023 FR-003. The order in which verification steps run. Absent on v2 means
    #: today's order; v1 always gets this default. Includes `judge` because that
    #: is today's default loop.
    verify_order: tuple[str, ...] = ("gates", "diff_check", "judge")
    #: 092 FR-004. The diff size above which this repository refuses to build a
    #: story, declared as `diff_refusal_bytes:`. Resolved rather than nullable —
    #: the way `forge` is, and for a sharper reason: `None` is how the check's
    #: own seam spells *disabled* (`diffcheck.check_output`), so a config that
    #: reported "the operator declared nothing" as `None` would be one careless
    #: hand-off away from a repository with no ceiling at all, and principle VIII
    #: is non-negotiable. Absent means the default, and every reader downstream
    #: gets a number.
    diff_refusal_bytes: int = field(default_factory=_default_diff_refusal_bytes)
    #: 101 FR-004. The caches this repository's gates need carried across the
    #: gate boundary, in declaration order. Empty is not a shrug and not a
    #: default to fill in — it is what every manifest that exists says, and it
    #: means today's behaviour exactly: the uv cache, and nothing else (FR-006).
    #: Every entry here was refused at parse time unless its path resolves under
    #: the operator's home, because a declared bind is a hole in a verification
    #: boundary and the manifest declaring it belongs to whoever controls the
    #: target repository (FR-007).
    caches: tuple[CacheDeclaration, ...] = ()
    #: 128 FR-001. The gates this repo declares as binding the verification
    #: boundary alone — deliberately absent from the forge's merge queue. Sparse
    #: the way `writes` is, in declaration order: an empty tuple is not a
    #: default to fill in, it is what every manifest that exists says, and a
    #: reader that cannot distinguish "declared empty" from "never declared"
    #: would invent an exemption the operator never wrote. Entries are refused
    #: at parse time unless the manifest declares them as gates (FR-002), the
    #: same cross-check `_read_writes` makes — a declaration that silently
    #: applied to nothing would be worse than no declaration. Nothing downstream
    #: reads this field yet; 128 US2 threads it into onboarding, and this field
    #: is the key that story consults.
    boundary_only_gates: tuple[str, ...] = ()


@dataclass(frozen=True)
class GateResult:
    """One gate command's outcome — evidence, not an exception.

    `exit_code` is None exactly when there was no exit to read: the command hit
    its deadline (TIMEOUT) or never ran (CONFIG_ERROR, where `name` is `config`).
    `output_tail` is the last ≤32 KiB of combined stdout+stderr, and it is
    load-bearing: the retry prompt quotes it verbatim (FR-006, SC-004).

    `concurrent_gates` is the contention marker (007 FR-005): how many *other*
    gate executions were in flight when this one ran. Zero means the gate had
    the host's gate budget to itself — its verdict cannot have moved with
    neighbour load. A non-zero count means it ran alongside peers, so a slow
    verdict is auditable: an operator reading the evidence sees whether load
    was a fact about this run rather than having to guess. The default of zero
    keeps every caller that predates fan-out honest — an uncontended gate is
    the only kind a sequential loop ever produced.

    `worktree_writes` names the paths *this* gate changed in the node worktree
    while it ran (084 FR-003), attributed to it by the name it was declared
    under: a gate that changed nothing carries an empty tuple, which is what
    every gate did before the check existed and is why the field is defaulted,
    the way `concurrent_gates` is. Tracked content and unignored new paths only
    — the same set `worktree.diff` puts in front of the judge — because a gate
    that wrote an ignored path cannot have moved what the judge scores. A tuple
    rather than a list because this dataclass is frozen.

    `writes_declared` says the target repo's manifest named this gate in its
    `writes:` block (084 FR-010), and it is on the result rather than only in
    the config because that is the difference between an opt-out and an audited
    one. A declared writer keeps PASS and still carries its `worktree_writes`,
    so the evidence reads "this gate wrote these paths, and somebody signed for
    it" — never "this gate wrote nothing". It tracks the declaration and not the
    run: true beside an empty `worktree_writes` is a gate that was allowed to
    write and did not, which is a declaration an operator can now retire.
    """

    name: str
    command: str
    status: GateStatus
    exit_code: int | None
    duration_s: float
    output_tail: str
    concurrent_gates: int = 0
    worktree_writes: tuple[str, ...] = ()
    writes_declared: bool = False


# Diff/artifact entities -----------------------------------------------------


@dataclass(frozen=True)
class HygieneViolation:
    """One changed path a diff may not carry, and the rule that refused it.

    `rule` is quotable evidence rather than a category, because the next attempt
    is shown it verbatim and "which rule refused this?" is the question it has to
    answer before it can shrink its diff. Two shapes occur: git's own
    `<source>:<line>:<pattern>` when the target repository's ignore rules matched
    the path, and `runtime root: <name>/` when the path sits under a directory
    that belongs to the factory rather than to the node.
    """

    path: str
    rule: str


@dataclass(frozen=True)
class DiffFileSize:
    """One file's contribution to a diff, in the unit both caps are in.

    Bytes rather than lines, because bytes are what `DIFF_REFUSAL_THRESHOLD`
    bounds — as `DIFF_INPUT_LIMIT` does, the two being separate settings on the
    same measurement since 092 — a file of 40 very long lines can cost more of
    the budget than one of 400 short ones, and a record in the wrong unit sends
    the next attempt after the wrong file.
    """

    path: str
    size_bytes: int


@dataclass(frozen=True)
class DiffSizeRefusal:
    """Why a diff was refused unread, in the terms its two readers need.

    `total_bytes` beside `limit_bytes` answers *how far over am I* — the
    question that decides between splitting the story and raising the ceiling,
    and the reason the limit travels in the record instead of being looked up
    later against a constant that may have moved. `largest_files` answers *what
    spent it*, biggest first and bounded: a session home names itself in one
    line, where a total on its own sends the next attempt hunting through the
    whole diff for the file this list already names.

    `total_bytes` is measured on the patch as the judge would have received it,
    which the worktree read limit itself bounds (`worktree.DIFF_READ_LIMIT`);
    past that bound the total is a floor, and a floor already an order of
    magnitude over the cap answers the only question being asked of it.
    """

    total_bytes: int
    limit_bytes: int
    largest_files: list[DiffFileSize]


@dataclass(frozen=True)
class DiffAbridgement:
    """How much of the diff the judge was shown — said out loud either way.

    The sibling of `DiffSizeRefusal`, and deliberately its shape: two numbers on
    the same measurement, one taken from the diff and one carried from the
    setting that bounded it. Between the attention budget and the refusal
    threshold a diff is now judged rather than thrown away (092 FR-003), and a
    PASS reached that way is only safe under Principle VIII if the record admits
    what the judge could not see. This is that admission, and it is a *record*
    rather than a flag because "was it abridged" and "by how much" are one
    question asked twice: an operator deciding whether to trust a large story's
    PASS needs the second answer to act on the first.

    `limit_bytes` travels in the record instead of being looked up later
    against `DIFF_INPUT_LIMIT`, for the reason `DiffSizeRefusal.limit_bytes`
    does: the budget is a tuned value that has moved once already, and a verdict
    has to be re-read under the budget it was actually formed under.

    `abridged` and `over_limit_bytes` are derived rather than stored, so the
    record cannot disagree with itself. The comparison is `prepare_diff`'s own —
    a diff whose assembly fits the budget is passed through untouched — and
    `over_limit_bytes` is exactly the excess, never a claim about how much text
    the abridger elided: it spends part of the budget on its truncation notice
    and its per-file markers, so the bytes missing from the prompt are at least
    this many and the honest number to record is the one that was measured.
    """

    total_bytes: int
    limit_bytes: int

    @property
    def abridged(self) -> bool:
        """Whether the judge's copy of this diff had to lose anything."""
        return self.total_bytes > self.limit_bytes

    @property
    def over_limit_bytes(self) -> int:
        """How far past the budget the whole diff ran; 0 when it fit."""
        return max(self.total_bytes - self.limit_bytes, 0)


@dataclass(frozen=True)
class OutputCheck:
    """The anti-rubber-stamp check: did the node actually produce something?

    A write-scope node with a clean worktree fails on `has_diff` alone (FR-004) —
    no gate suite and no judge can rescue it, because passing tests over an empty
    diff is precisely the failure this exists to catch. Read scopes have nothing
    to diff, so they are judged on `expected_artifacts` existing and being
    non-empty instead; `artifacts_present` is None when artifacts do not apply.

    `hygiene_violations` is the second way a write-scope node fails here (045
    FR-001): a diff can be present and still be unjudgeable, because it carries
    paths that are nobody's work — a session home under the runtime root, or
    anything the target repository's own ignore rules already refuse. It is a
    list of evidence rather than a flag so the refusal can name what to remove,
    and it defaults to empty so every row written before 045 loads unchanged.

    `size_refusal` is the third way (045 FR-003): a diff can be present, clean
    of both those classes, and still be more than the judge can be shown whole.
    Truncating it and ruling anyway is what produced the 2026-08-15 verdict that
    reasoned about an elided midsection in the same voice it used for what it
    had read, so size decides here instead — before a completion is bought, on
    this record, through the same `passed=False` the other two ways use. `None`
    is the ordinary case, and it is also what keeps a passing row identical to
    the rows written before this story (FR-004): the field is evidence of a
    refusal, not a measurement taken on every attempt.

    `abridgement` is not a fourth way to fail — it decides nothing, and
    `decide_passed` never reads it. It is the measurement this check already
    takes, kept instead of discarded (092 FR-007): the same assembly the refusal
    weighs, weighed against the judge's attention budget as well as against the
    threshold. Unlike `size_refusal` it is recorded whichever way it came out,
    because "the judge read this whole" is the claim a PASS on a large story
    rests on and a claim nobody wrote down is not one. `None` is the third
    state and it means *nobody measured*: a row written before this story, a
    read-scoped node whose verdict never consulted git, an attempt with no diff
    to weigh. It is never "the judge saw it whole" — that reading would certify
    every historical PASS as whole-diff on the authority of code that could not
    tell.
    """

    write_scope: str
    has_diff: bool
    expected_artifacts: list[str]
    artifacts_present: bool | None
    passed: bool
    hygiene_violations: list[HygieneViolation] = field(default_factory=list)
    size_refusal: DiffSizeRefusal | None = None
    abridgement: DiffAbridgement | None = None


# Judge entities -------------------------------------------------------------


@dataclass(frozen=True)
class JudgeScenarioFinding:
    """The judge's call on one scenario, keyed by the id it was dispatched under.

    `scenario` must match a dispatched `Scenario.scenario_id` exactly — a
    response that renames, drops, or invents one is malformed, not lenient.
    """

    scenario: str
    passed: bool
    reasoning: str


@dataclass(frozen=True)
class JudgeVerdict:
    """One bounded judge invocation's result.

    `outcome` is post-cross-check: any finding with `passed=False` forces
    RETRY/FAIL even when the raw response claimed an overall pass, because the
    stricter interpretation always wins (R5). `feedback` travels verbatim into
    the next attempt's prompt, and `model_alias` records the persona registry
    alias that was used — code never names a model (constitution VII).

    `gates_shown` says whether the prompt this verdict answers carried the
    factory's own gate measurements (116 FR-008). It rides here for the reason
    `truncated_input` does: the assembler is the only thing that knows what went
    into the prompt, and it knows at assembly time, so the fact is carried
    forward rather than re-derived later by a reader who would have to guess.
    Without it two rows written a fortnight apart — one judged blind, one judged
    with the measurements in hand — read identically, and a regression that
    dropped the section would be invisible.

    It is a plain bool written in both directions, never an absent field
    (plan trap 8): a record that carried it only when the answer was yes would,
    when the answer was no, be indistinguishable from one written before this
    spec existed. `False` on a verdict decoded from an older payload is a fact
    about the writer rather than a guess about the run — no prompt assembled
    before 116 US1 had a parameter to carry gate results through, so no judge
    that produced such a payload can have been shown any.
    """

    outcome: JudgeOutcome
    findings: list[JudgeScenarioFinding]
    feedback: str
    judge_attempt: int
    truncated_input: bool
    model_alias: str
    gates_shown: bool = False


# Gate contradictions (116-US2) ----------------------------------------------


@dataclass(frozen=True)
class GateContradiction:
    """One finding that asserts a gate would fail, on a gate recorded PASS.

    The evidence behind a neutralisation, and it is a record rather than a flag
    for the same reason `DiffAbridgement` is: "the judge contradicted a
    measurement" and "which one, and what did it say" are one question asked
    twice, and an operator deciding whether the judge persona needs re-routing
    cannot act on the first answer without the second.

    `claim` quotes the judge's own words — the matched span, whitespace
    normalised — because a record that only asserted a disagreement would send
    its reader back to the reasoning to find out what was disagreed with.
    `recorded_status` is always `PASS` today, since that is the only status a
    contradiction is defined against, and it is carried rather than implied so
    the row states what was measured instead of leaving it to be inferred from
    the fact that a row exists.
    """

    scenario: str
    gate: str
    recorded_status: GateStatus
    claim: str


#: The nouns that mark a word as being used as *this factory's gate* rather than
#: as an ordinary English word that a gate happens to be named after. Requiring
#: one is what keeps "the diff adds no test for the new branch" out of a check
#: that would otherwise read it as a claim about the gate named `test`.
_GATE_NOUNS = r"gates?|checks?|commands?|suites?|steps?|jobs?|runs?"

#: Words allowed between the gate and the claim about it. Bounded to three, and
#: to *these* words, because the alternative — any three words — makes the match
#: "a sentence containing both" rather than "a claim about the gate", and a
#: false positive here turns a real node FAIL into a PASS.
_HEDGES = (
    r"would|will|shall|does|do|did|is|are|was|were|be|been|has|have|had|must|"
    r"should|can|could|may|might|still|already|therefore|then|thus|also|now|"
    r"currently|likely|probably|certainly|clearly|actually|obviously"
)

_FAIL_VERBS = r"fail(?:s|ed|ing|ure)?|break(?:s|ing)?|broke|broken|error(?:s|ed|ing)?"

_PASS_VERBS = r"pass(?:es|ed|ing)?|succeed(?:s|ed|ing)?"

_NEGATIONS = r"not|never|n't|cannot|can't|won't|wouldn't|doesn't|didn't|isn't"

#: The assertion itself, in the two shapes it comes in: the gate fails, or the
#: gate does not pass. Negation is handled explicitly rather than swallowed by
#: the hedges, because "the test gate would **not** fail" asserts the opposite
#: of "the test gate would fail" and a check that read them the same way would
#: neutralise a finding that agreed with the measurement.
#:
#: `fail(s) to <verb>` is excluded: "the diff fails to add the helper" is the
#: English idiom for "does not", and it is the sentence a judge writes when it
#: is objecting to the work rather than to a gate.
_CLAIM = (
    rf"(?:\s+(?:{_HEDGES})\b){{0,3}}"
    rf"(?:\s+(?:{_FAIL_VERBS})\b(?!\s+to\b)|\s+(?:{_NEGATIONS})\s+(?:{_PASS_VERBS})\b)"
)

#: Quote characters a judge wraps a gate name in when it is quoting the section
#: it was shown. Optional on both sides, so `` `test` gate `` and `test gate`
#: are the same claim.
_QUOTE = "[`'\"‘’“”]?"


@lru_cache(maxsize=64)
def _gate_claim_pattern(name: str) -> re.Pattern[str]:
    """The pattern that reads "this gate would fail" for one gate's name.

    The name is matched on a boundary that excludes `-`, `_`, `.` and `/` as
    well as word characters (plan trap 5). A bare `\\b` is not enough: it keeps
    `test` out of `smoketest`, but a hyphen *is* a word boundary, so `\\btest\\b`
    matches inside `test-fixtures` — and a repository declaring both would have
    one gate's name silently answering for the other's. This repository has been
    bitten by an unanchored match once already (`factory/cli/doctor.py:58`).

    The gate must be the *subject* of the claim, and the claim must follow it.
    Reading the reverse order too ("US2-S1 fails because the test gate output is
    not shown") would match a finding that objects to the work, which is the one
    class of finding this check may never touch.
    """
    token = rf"(?<![\w./-]){re.escape(name)}(?![\w./-])"
    subject = (
        rf"(?:the\s+)?{_QUOTE}{token}{_QUOTE}\s+(?:{_GATE_NOUNS})\b"
        rf"|\b(?:{_GATE_NOUNS})\s+{_QUOTE}{token}{_QUOTE}"
    )
    return re.compile(rf"(?:{subject}){_CLAIM}", re.IGNORECASE)


def detect_gate_contradictions(
    judge: JudgeVerdict | None,
    gate_results: Sequence[GateResult],
) -> tuple[GateContradiction, ...]:
    """Findings that assert a gate would fail which this attempt recorded PASS.

    The unwinnable case (116 FR-006). `judge_required` consults the judge only
    when every gate passed, so a finding asserting one of them would fail is
    disagreeing with a measurement the factory took after the diff was produced
    and wrote into the same row. The only remedy such a finding admits is
    re-adding or touching files that are already committed — padding the diff to
    please the grader, the behaviour this factory teaches its agents to refuse.

    Deliberately conservative, in one direction. A missed contradiction leaves
    today's behaviour, which is the deadlock this spec exists to end; a false
    one turns a real node FAIL into a PASS, which is worse than the deadlock. So
    the gate must be named as a gate, must be the subject, and the assertion
    must be a failure claim about it — a finding that merely mentions a green
    gate, or says it would *not* fail, is the judge's ordinary business.

    Only failing findings are read: a scenario the judge passed is not being
    charged to anyone. Statuses are compared by value, the way `gates_passed`
    compares them, because a `GateResult` that crossed a payload boundary
    carries the enum's string.
    """
    if judge is None:
        return ()

    measured = [gate for gate in gate_results if gate.status == GateStatus.PASS]
    if not measured:
        return ()

    found: list[GateContradiction] = []
    for finding in judge.findings:
        if finding.passed:
            continue
        for gate in measured:
            match = _gate_claim_pattern(gate.name).search(finding.reasoning)
            if match is None:
                continue
            found.append(
                GateContradiction(
                    scenario=finding.scenario,
                    gate=gate.name,
                    recorded_status=GateStatus(gate.status),
                    claim=" ".join(match.group(0).split()),
                )
            )

    return tuple(found)


def judge_should_be_reasked(
    verdict: JudgeVerdict, gate_results: Sequence[GateResult]
) -> bool:
    """Whether asking the judge again can still change this verdict (FR-007).

    The re-ask rule, stated here rather than inline in the scoring loop, for the
    reason every other decision in this module is: a rule spelled out at its
    call site is a rule the next caller re-derives slightly differently. Two
    things are worth re-asking and nothing else is:

    - **A response the parser could not read.** It comes back as a RETRY with no
      findings, and asking again is the only way to tell a broken model turn
      from a real objection.
    - **A verdict that contradicts a recorded gate** (116 FR-007). A judge fault
      is the one failure a judge retry is actually for, and the re-ask carries
      the measurement back to the judge that contradicted it.

    A RETRY that names scenarios and contradicts nothing is an answer: re-asking
    it about an unchanged diff buys the same verdict at twice the price, so it
    ends the scoring and the ladder takes over. This function decides re-asks
    and nothing else — whether the *node* fails is `compose_result`'s, and one
    decider is the point.
    """
    if verdict.outcome != JudgeOutcome.RETRY:
        return False
    return not verdict.findings or bool(
        detect_gate_contradictions(verdict, gate_results)
    )


# Composition ----------------------------------------------------------------


#: What a `base_ref` reads as when nothing measured one for the attempt it
#: describes: a row written before 118 US2 existed, or a caller that composed a
#: result without a prepared worktree behind it. Decided once, here, so no
#: reader has to invent its own word for it (FR-006). Never an empty string and
#: never a plausible sha — angle brackets are not legal in a git ref, so this
#: cannot be mistaken for a base a verdict was actually measured against, which
#: is the whole point: a wrong value is worse than an admitted gap.
UNKNOWN_BASE_REF = "<unknown>"

#: The one dispatch that has no name (117 US1, FR-004). Two kinds of row read as
#: this: every row written before dispatches were distinguished, which the
#: migration stamps with it, and any result composed without a dispatch behind
#: it. Both mean "nobody recorded which run produced this", which is a different
#: fact from every named run and must not merge with one.
#:
#: Unlike `UNKNOWN_BASE_REF` this is stored literally rather than as NULL, and
#: that is the point (plan trap 3): SQLite treats NULLs as *distinct* in a UNIQUE
#: index, so a NULL dispatch would give every unnamed row a key of its own and
#: silently disable the at-least-once idempotence the upsert exists for. Angle
#: brackets keep it outside the space of workflow run ids, so no dispatch can
#: ever collide with it.
UNKNOWN_DISPATCH = "<unknown>"

#: What the persona, the model alias and the route read as when nobody recorded
#: them for the attempt they describe (117 US2, FR-007): a row written before the
#: columns existed, or a result composed with no routing behind it. One constant
#: for all three, decided here and nowhere else (plan trap 6), because the thing
#: being ruled out is a reader inventing its own spelling.
#:
#: Unknown is a **value**, not a silence. NULL renders as nothing and `""`
#: renders like a persona whose name is empty, and both are read by a human as a
#: fact about the build rather than as an admitted gap. Angle brackets are legal
#: in no persona name, no registry alias and no route, so this cannot collide
#: with a real one.
UNKNOWN_BUILDER = "<unknown>"

#: The routes an attempt can run through — how it was authenticated, which is
#: the fact that survives when the registry has moved on. `gateway` is the
#: LiteLLM proxy under a model-constrained virtual key; `subscription` is the
#: operator's own Claude Code login, which mints no key and spends no metered
#: tokens; `deterministic` is a persona that runs no LLM at all.
ROUTE_GATEWAY = "gateway"
ROUTE_SUBSCRIPTION = "subscription"
ROUTE_DETERMINISTIC = "deterministic"


def route_of(route: str | None) -> str:
    """The route an attempt's evidence row records, from the persona's own.

    Reads the `route` field (154-US1 FR-006, trap 3) rather than deriving one
    from the agent name — the field is the one source of truth for how an
    attempt authenticates, and a second derivation beside it is a fork that
    will disagree with it.

    An empty or absent route is an entry the registry could not resolve, and it
    reads as `UNKNOWN_BUILDER` rather than as the gateway — guessing the common
    route for an attempt nobody could route is exactly the plausible-wrong-answer
    this column exists to end.
    """
    if not route:
        return UNKNOWN_BUILDER
    return route


@dataclass(frozen=True)
class VerificationResult:
    """One attempt's complete evidence bundle — the evidence-store row.

    Mirrors `verification_results` in contracts/verification-store.sql:
    `(epic_id, node_id, attempt, form)` is the upsert key, so re-recording an
    attempt updates rather than duplicates. `spec_ref` and `criteria_sha256` are
    NOT NULL columns there and so are carried here alongside the fields listed in
    data-model.md's table.

    `judge` is None when the judge never ran (a gate failed, or the node has no
    scenarios). `judge_unavailable` marks the one PASS that was reached without
    judge agreement; `criteria_drift` marks a spec that changed under the node
    and flags the row without touching `verdict`.

    `provenance` is None for agent-completed work and a non-empty string for
    externally-completed work (035-US1, FR-005). It is stored in the evidence
    row so the record of *who* completed the work travels with the verdict.

    `loop_digest` and `loop_summary` are None for rows written before 023 and
    non-None afterwards; they record the resolved loop configuration so a PASS is
    a claim relative to a named definition of verified (FR-010, SC-006).

    `base_ref` is the base the node's worktree was pinned to — what the verdict
    was measured against (118 US2, FR-006). Without it a PASS records *that* a
    node passed and never *what it passed against*, so a verdict that could
    never have landed reads identically to one that could. It comes from
    `PreparedWorktree.base_ref` and from nowhere else: re-reading git at
    record-writing time gives an answer that can differ from the one the attempt
    ran against, which is the class of defect this whole spec is about.
    `UNKNOWN_BASE_REF` for rows written before the field existed.

    `gate_contradictions` names every finding this attempt did *not* charge the
    node for, and why (116 FR-006). It is the evidence behind an asymmetry the
    verdict alone cannot show: a PASS composed over a judge that returned FAIL
    reads, without it, as a composer that ignored the judge. Empty is the
    ordinary case and means the judge contradicted no measurement — never "not
    checked", because the check runs on every composition. Since US3 it is
    persisted with the row and rendered by `ergane build attempts`, so the
    asymmetry is legible from the record an operator actually reads rather than
    only from the object the composer returned.

    `dispatch` names the run of the interpreter that produced this attempt (117
    US1, FR-001), and it joins the upsert key. Without it a node dispatched a
    second time started again at attempt 1 and overwrote the first dispatch's
    row for every attempt number it reached, so a post-mortem of a killed build
    became impossible at the moment it mattered most. It is the workflow run
    id and nothing else: a Temporal retry carries the same one — which is what
    keeps a redelivered recording landing on the row it already wrote — and a
    re-dispatch carries a different one. `UNKNOWN_DISPATCH` for rows written
    before the column existed.

    `persona`, `model_alias` and `route` say who built this attempt (117 US2,
    FR-005): the persona the rung selected, the alias it was dispatched under,
    and the credential path it ran through. They are here because the only other
    authority expires — the epic's Temporal start payload dies with the workflow,
    and `workgraph.json` lies for anything the roadmap dispatched — so thirty
    days later the row is the last thing that can answer "which model built this
    story". All three are carried in from the resolution that dispatched the
    attempt and never re-derived at write time: the debugger rung relabels the
    persona without re-resolving the alias, so a row that looked the persona up
    here would record the implementer's model for the one attempt the
    implementer did not run (FR-006). `UNKNOWN_BUILDER` for a row written before
    the columns existed, and for a result composed with no routing behind it.
    """

    epic_id: str
    node_id: str
    attempt: int
    form: VerificationForm
    gate_results: list[GateResult]
    output_check: OutputCheck
    judge: JudgeVerdict | None
    verdict: OverallVerdict
    judge_unavailable: bool
    criteria_drift: bool
    criteria_sha256: str
    spec_ref: str
    started_at: str
    finished_at: str
    provenance: str | None = None
    loop_digest: str | None = None
    loop_summary: str | None = None
    base_ref: str = UNKNOWN_BASE_REF
    gate_contradictions: tuple[GateContradiction, ...] = ()
    dispatch: str = UNKNOWN_DISPATCH
    persona: str = UNKNOWN_BUILDER
    model_alias: str = UNKNOWN_BUILDER
    route: str = UNKNOWN_BUILDER


def gates_passed(gate_results: Sequence[GateResult]) -> bool:
    """Whether the deterministic half of verification is green.

    An empty list is not green. No gates ran means nothing was checked, and
    "nothing failed" is the exact shape a naive verdict mistakes for a pass
    (SC-002) — which is also why an unusable `factory.yaml` arrives here as one
    `CONFIG_ERROR` result rather than as zero results.

    Statuses are compared by value, not by identity: a `GateResult` that crossed
    a Temporal payload boundary carries the enum's string, and a comparison that
    only recognised the member would read a serialized PASS as a failure.
    """
    return bool(gate_results) and all(
        gate.status == GateStatus.PASS for gate in gate_results
    )


def has_scenarios(criteria: CriteriaSet) -> bool:
    """Whether this node was dispatched anything the judge could score.

    A node owing only `FR-###` bullets has no acceptance scenarios, and an empty
    scenario list would parse back from any response as a unanimous pass — so it
    is verified on its gates and its output check alone, by design.
    """
    return any(requirement.scenarios for requirement in criteria.requirements)


def judge_required(
    gate_results: Sequence[GateResult],
    output_check: OutputCheck,
    criteria: CriteriaSet,
) -> bool:
    """Whether asking the judge can still change the outcome (flow invariant 2).

    Cheapest-first: the gates and the output check have already decided a FAIL
    that no judge verdict could lift, so consulting one would cost a completion
    to learn nothing (FR-003). This is the guard the reference flow puts in front
    of `run_judge`, and it is the reason `VerificationResult.judge` is None on
    every failing-gate row — "the judge never ran" is a different fact from "the
    judge ran and disagreed".
    """
    return (
        gates_passed(gate_results)
        and output_check.passed
        and has_scenarios(criteria)
    )


def compose_result(
    *,
    epic_id: str,
    node_id: str,
    attempt: int,
    form: VerificationForm,
    gate_results: list[GateResult],
    output_check: OutputCheck,
    judge: JudgeVerdict | None,
    criteria_sha256: str,
    spec_ref: str,
    started_at: str,
    finished_at: str,
    criteria_drift: bool = False,
    loop_digest: str | None = None,
    loop_summary: str | None = None,
    base_ref: str = UNKNOWN_BASE_REF,
    dispatch: str = UNKNOWN_DISPATCH,
    persona: str = UNKNOWN_BUILDER,
    model_alias: str = UNKNOWN_BUILDER,
    route: str = UNKNOWN_BUILDER,
) -> VerificationResult:
    """Turn one attempt's evidence into the verdict downstream edges read.

    The truth table is data-model.md's, and it is stated once, here, because this
    function is the only thing standing between a green-looking attempt and an
    unlocked downstream edge (FR-005): PASS requires that gates ran and all
    passed, that the node proved it produced something (FR-004), and that the
    judge either agreed or never ran. Every other combination is FAIL — a judge
    RETRY included, since RETRY says what the ladder should do next, not that the
    attempt was acceptable.

    One class of judge disagreement is not the node's to answer for (116
    FR-006): a finding asserting that a gate would fail, about a gate this same
    attempt recorded PASS. It contradicts a measurement the factory took after
    the diff was produced, and the only remedy it admits is padding the diff
    with files that are already committed. Such a finding is neutralised — not
    the verdict — and recorded on the row as a `GateContradiction`, so a PASS
    reached over a FAIL verdict says why it was.

    An unreachable judge is the other asymmetry: it does not block a PASS, but
    the PASS is flagged `judge_unavailable` so nobody reads it later as judged
    work. Drift is carried through untouched — it flags a result whose spec moved
    under it (R8) and never moves the verdict, or the flag would silently become
    a second, quieter gate.

    `loop_digest` and `loop_summary` default to the unconfigured loop so a v1
    repo records the explicit default rather than an absent field (US4-S3).
    Callers that know the resolved loop override them; None is intentionally not
    the default here. Pre-023 replay safety is preserved because the row fields
    are additive and read back as None when missing from the store.

    `base_ref` is passed by the caller that holds the prepared worktree and
    defaults to `UNKNOWN_BASE_REF` (118 US2, FR-006). It is *not* defaulted to
    a reading taken here: this function is pure and a base it re-derived would
    be a different moment from the one the attempt ran against.

    `dispatch` is passed by the caller that holds the run (117 US1, FR-001) and
    for the same reason: the identity of a dispatch is declared by the workflow
    that is running, never inferred here from a clock or a fresh uuid — either
    of which would change under a Temporal retry and turn one attempt into a row
    per delivery. It defaults to `UNKNOWN_DISPATCH`, which is the one dispatch
    that has no name rather than a guess at a real one.

    `persona`, `model_alias` and `route` are passed by the caller that holds the
    attempt's routing (117 US2, FR-005/FR-006), and for the third time for the
    same reason: they are facts about what ran, resolved at the moment the rung
    chose it, and this function is not entitled to re-derive them. Re-reading the
    persona's registry entry here would record the *node's* model for a debugger
    rung, which is the defect US2-S3 exists to catch. They default to
    `UNKNOWN_BUILDER` — an admitted gap rather than a plausible wrong answer.
    """
    judge_unavailable = judge is not None and judge.outcome == JudgeOutcome.UNAVAILABLE

    # 116 FR-006, plan traps 6 and 7. The neutralisation happens *here*, where
    # `judge_accepts` is derived, and not in a fourth place that could disagree
    # with this one — the comment below has always said that the moment two
    # places can decide a FAIL, the stored row and the retry prompt can differ.
    # And it neutralises findings, not the attempt: the gates still stand, the
    # output check still stands, and any failing finding that contradicted
    # nothing still fails the node. A contradiction buys the node exactly the
    # one finding it was not responsible for.
    contradictions = detect_gate_contradictions(judge, gate_results)
    contradicted = {contradiction.scenario for contradiction in contradictions}
    standing = [
        finding
        for finding in (judge.findings if judge is not None else ())
        if not finding.passed and finding.scenario not in contradicted
    ]

    judge_accepts = (
        judge is None
        or judge.outcome == JudgeOutcome.PASS
        or judge_unavailable
        or (bool(contradictions) and not standing)
    )
    passed = gates_passed(gate_results) and output_check.passed and judge_accepts

    return VerificationResult(
        epic_id=epic_id,
        node_id=node_id,
        attempt=attempt,
        form=form,
        gate_results=list(gate_results),
        output_check=output_check,
        judge=judge,
        verdict=OverallVerdict.PASS if passed else OverallVerdict.FAIL,
        judge_unavailable=judge_unavailable,
        criteria_drift=criteria_drift,
        criteria_sha256=criteria_sha256,
        spec_ref=spec_ref,
        started_at=started_at,
        finished_at=finished_at,
        loop_digest=loop_digest if loop_digest is not None else DEFAULT_LOOP_DIGEST,
        loop_summary=loop_summary if loop_summary is not None else DEFAULT_LOOP_SUMMARY,
        base_ref=base_ref,
        gate_contradictions=contradictions,
        dispatch=dispatch,
        persona=persona,
        model_alias=model_alias,
        route=route,
    )


#: Ladder fields that participate in the loop digest (FR-010).
_LOOP_DIGEST_LADDER_FIELDS = (
    "max_attempts",
    "max_judge_retries",
    "debugger_cycles",
    "escalation_timeout_s",
    "promotion_cycles",
)


def loop_digest(
    config: VerificationConfig,
    verify_order: tuple[str, ...],
    gate_names: tuple[str, ...],
    *,
    schema_version: int = 1,
) -> str:
    """Stable SHA-256 identifier of a resolved loop configuration (FR-010).

    Covers schema version, gate names in declared order, verify order, ladder
    caps, and whether the judge is present. Same declared loop -> same digest,
    regardless of epic or attempt.
    """
    data = {
        "schema_version": schema_version,
        "gate_names": list(gate_names),
        "verify_order": list(verify_order),
        "ladder": {
            field: getattr(config, field) for field in _LOOP_DIGEST_LADDER_FIELDS
        },
        "judge_present": "judge" in verify_order,
    }
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def loop_summary(
    config: VerificationConfig,
    verify_order: tuple[str, ...],
    gate_names: tuple[str, ...],
    *,
    schema_version: int = 1,
) -> str:
    """Human-readable one-line summary of the resolved loop (FR-010)."""
    steps = ", ".join(verify_order)
    ladder = (
        f"attempts={config.max_attempts}, judge_retries={config.max_judge_retries}, "
        f"promotion={config.promotion_cycles}, debugger={config.debugger_cycles}, "
        f"deadline={config.escalation_timeout_s}s"
    )
    judge = "judge present" if "judge" in verify_order else "no judge"
    gates = ", ".join(gate_names) if gate_names else "no gates"
    return f"schema v{schema_version}; gates [{gates}]; order [{steps}]; {ladder}; {judge}"


# Ladder entities (pure) -----------------------------------------------------


@dataclass(frozen=True)
class VerificationConfig:
    """Per-deployment caps for the retry ladder.

    `max_judge_retries` is bounded *inside* `max_attempts`, not on top of it:
    exhausted judge retries consume attempts as ordinary failures (SC-003).

    `promotion_persona` is the operator-configured stronger persona a node is
    retried on after ordinary attempts are spent; `None` means no promotion
    rung is configured and the ladder behaves exactly as today (US5-S3).
    `promotion_cycles` bounds the rung like `debugger_cycles`.

    `max_launch_retries` bounds how many times a pre-first-token launch fault may
    be retried independently of the attempt budget (US2 FR-007).  A launch that
    never reached the agent is not an attempt, so it must not consume the ladder
    budget, but it also must not loop forever.
    """

    max_attempts: int = 3
    max_judge_retries: int = 2
    debugger_cycles: int = 1
    gate_timeout_s: int = 600
    escalation_timeout_s: int = 3600
    promotion_persona: str | None = None
    promotion_cycles: int = 1
    max_launch_retries: int = 2
    #: 095-US2 (FR-006): how many *consecutive* pre-agent failures may run before
    #: the ladder escalates on a bound of its own. A pre-agent failure is not a
    #: rung, so it does not consume `max_attempts`; without a bound of its own a
    #: permanently dead credential would retry forever, spending a worker slot at
    #: cap 1 and starving every other spec (plan trap 2). Defaulted to 4 — the
    #: measured cost of the incident this spec exists for ("four rungs in
    #: thirteen seconds") — and above the default `max_attempts` of 3, so the
    #: exclusion is observable: three pre-agent failures still grant (US2-S1),
    #: while a longer unbroken run escalates on this dial (US2-S4).
    max_pre_agent_failures: int = 4


#: The digest of the unconfigured default loop: v1, default gate names, default
#: order, default ladder, judge present. Stored explicitly for v1 repos (US4-S3).
#: US2 adds `max_launch_retries` but it is not part of the loop digest: a
#: launch retry is infrastructure recovery, not a verdict-shaping loop parameter.
DEFAULT_LOOP_DIGEST = loop_digest(
    VerificationConfig(), ("gates", "diff_check", "judge"), ("test", "lint", "typecheck")
)


#: The summary that goes with `DEFAULT_LOOP_DIGEST`: v1, default gate names,
#: default order, default ladder, judge present.
DEFAULT_LOOP_SUMMARY = loop_summary(
    VerificationConfig(), ("gates", "diff_check", "judge"), ("test", "lint", "typecheck")
)


#: What a `model_alias` reads as when no alias can be named for the attempt it
#: describes: a rung naming a persona the epic's snapshot never resolved, an
#: attempt an operator completed by hand (no model ran at all), or a record
#: written before the field existed. Never a model name, and never the *node's*
#: — reporting the node's alias for an attempt that did not run it is exactly
#: the misattribution 075 exists to end (US3-S3). Angle brackets are not legal
#: in a registry alias, so this can never collide with a real one.
UNRESOLVED_MODEL_ALIAS = "<unresolved>"


@dataclass(frozen=True)
class AttemptRecord:
    """One entry of the ladder's input history.

    `persona` is what distinguishes a debugger cycle from an ordinary retry, and
    `judge_outcome` is None when the judge never ran — the ladder needs both to
    tell "failed the gates three times" from "the judge asked for two rewrites".

    `model_alias` is 075-US3's addition (FR-011): the alias the attempt actually
    ran under, recorded beside the persona that selected it. The pair is the
    whole point — a rung reaches the ledger by its persona (D-026), so a record
    naming the persona alone is what let a rung run the wrong model for eight
    days without any surface disagreeing. It defaults to `UNRESOLVED_MODEL_ALIAS`
    rather than to the node's alias because a history recorded before this field
    existed genuinely does not know, and a default that guessed would be
    indistinguishable from a reading.
    """

    attempt: int
    persona: str
    verdict: OverallVerdict
    judge_outcome: JudgeOutcome | None = None
    model_alias: str = UNRESOLVED_MODEL_ALIAS
    #: 095-US2 (FR-005): whether this attempt was a pre-agent failure — the agent
    #: process never produced a token (US1's `Termination.PRE_AGENT_FAILURE`). A
    #: pre-agent failure is not a rung of the ladder, so `_attempts_spent` excludes
    #: it; the flag is a property of the record rather than of the config, so the
    #: exclusion applies at every call site, including one that passes no config
    #: (plan trap 4).
    pre_agent: bool = False
    #: US1: which credential source a subscription-routed attempt used. Recorded
    #: on the ladder history so the operator can read the precedence from
    #: `ergane build status` (FR-005, trap 10). `None` when the attempt was not
    #: subscription-routed or when the adapter produced no source information.
    credential_source: str | None = None


# Escalation entities --------------------------------------------------------


@dataclass(frozen=True)
class RefConflictInfo:
    """126-US3: the ref that blocks a node, and whether clearing it is safe.

    The facts are computed from the node record and the local clone: the remote
    tip is read from `refs/remotes/origin/<branch>` (the last push's tracking
    ref), and reachability is checked against local archive refs. No new remote
    read is performed on the escalation path (FR-011).
    """

    ref: str
    tip: str
    archived: bool
    clearing_command: str


@dataclass(frozen=True)
class EscalationRecord:
    """A pending operator decision — a store row before it is ever a message.

    The row is written before the send, so a crash in between leaves something
    expirable rather than an untracked message. `delivered=False` is not a
    failure to record: it tells the workflow the notifier is down and the
    fail-safe default (KILL) applies immediately, without waiting out the hour.

    `resolution` is None while pending and terminal once set — `RETRY`/`KILL`/
    `PAUSE_EPIC` from a button press, or the string `EXPIRED` from the timeout
    path, which is why the annotation is not just `EscalationChoice | None`.
    """

    escalation_id: str
    workflow_id: str
    epic_id: str
    node_id: str
    choices: list[EscalationChoice]
    history_summary: str
    sent_at: str
    expires_at: str
    delivered: bool = False
    resolution: EscalationChoice | str | None = None
    resolved_at: str | None = None
    #: 095-US2 (FR-007): the fail-safe default applied on silence, which varies
    #: with the escalation's cause. An authentication escalation defaults to
    #: `PAUSE_EPIC` rather than `KILL` — a dead credential is fixed by
    #: re-authenticating, not by killing the node — and the message says so
    #: rather than leaving the operator to notice the button moved (plan trap 6).
    #: `None` means the ordinary default (`KILL`), which is what every escalation
    #: raised before this field existed applies.
    default_choice: EscalationChoice | None = None
    #: 025-US2: the failing check evidence rendered into the escalation message,
    #: and — since 041-US2 — persisted with the row rather than lost on read.
    #: A workflow that writes this row at every terminal transition (041 FR-013)
    #: must not be writing rows that lose fields (FR-014).
    check_evidence: tuple[CheckFailure, ...] = ()
    #: 095-US3 (FR-008): which of the ladder's bounds ended this node, already
    #: written out as the sentence the operator reads — `ExhaustedBound.describe`
    #: in `factory/verify/ladder.py`, composed beside the decision that produced
    #: it. A string rather than the record, because this field is a *reading*:
    #: the renderer prints what the ladder said and derives nothing of its own
    #: (095 plan trap 5). `None` for every escalation with no exhausted ladder
    #: behind it — a landing escalation, a launch failure, a row written before
    #: this field existed — and the message then names no bound at all, which is
    #: the honest reading of "nobody said".
    exhausted_bound: str | None = None
    #: 126-US3 (FR-011): the stale ref blocking this node, when the escalation's
    #: terminal cause is a non-fast-forward push refusal. `None` for every other
    #: escalation, which must render exactly as it did before this field existed
    #: (FR-012, trap 12).
    ref_conflict: RefConflictInfo | None = None


@dataclass(frozen=True)
class QuestionRecord:
    """A pending operator question — a store row before it is ever a message.

    The sibling of `EscalationRecord` for the operator-question channel
    (008-US1). The row is written before the send (R11, the escalation
    precedent), so a crash in between leaves something the expiry path (US2) can
    close rather than an untracked message. `message_id` is the Telegram message
    id the send returned — the reply-routing key a free-text answer threads back
    to (FR-008) — and is ``None`` until the message is delivered.

    `resolution` is ``None`` while the node is parked WAITING_OPERATOR,
    ``ANSWERED`` once the operator replies (US2), or ``EXPIRED`` when the
    question's own window runs out (FR-004). `answer_text` is the operator's
    reply, filled in by US2; the store's CHECK constraint keeps it ``None``
    unless the resolution is ``ANSWERED``.
    """

    question_id: str
    workflow_id: str
    epic_id: str
    node_id: str
    attempt: int
    question_text: str
    sent_at: str
    expires_at: str
    message_id: int | None = None
    resolution: str | None = None
    answer_text: str | None = None
    resolved_at: str | None = None
