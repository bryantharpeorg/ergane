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
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Sequence

# Imported for real, not named in a string. `EscalationRecord.check_evidence`
# used to annotate `tuple["factory.mergequeue.models.CheckFailure", ...]` in a
# module that imported no `factory` name at all: `from __future__ import
# annotations` deferred the lookup, so the mistake was invisible until something
# called `typing.get_type_hints(EscalationRecord)` and got `NameError` (041
# FR-014, `verify/escalation-record-annotation-cannot-resolve`). The import is
# safe in both directions — `factory.mergequeue.models` imports nothing from
# `factory` — and an annotation that resolves is the only kind worth writing.
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


def _default_ladder() -> "VerificationConfig":
    """Deferred default so `VerificationConfig` need not move above `FactoryConfig`."""
    return VerificationConfig()


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
    """One file's contribution to a diff, in the unit the judge's cap is in.

    Bytes rather than lines, because bytes are what `DIFF_INPUT_LIMIT` bounds —
    a file of 40 very long lines can cost more of the budget than one of 400
    short ones, and a record in the wrong unit sends the next attempt after the
    wrong file.
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
    """

    write_scope: str
    has_diff: bool
    expected_artifacts: list[str]
    artifacts_present: bool | None
    passed: bool
    hygiene_violations: list[HygieneViolation] = field(default_factory=list)
    size_refusal: DiffSizeRefusal | None = None


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
    """

    outcome: JudgeOutcome
    findings: list[JudgeScenarioFinding]
    feedback: str
    judge_attempt: int
    truncated_input: bool
    model_alias: str


# Composition ----------------------------------------------------------------


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
) -> VerificationResult:
    """Turn one attempt's evidence into the verdict downstream edges read.

    The truth table is data-model.md's, and it is stated once, here, because this
    function is the only thing standing between a green-looking attempt and an
    unlocked downstream edge (FR-005): PASS requires that gates ran and all
    passed, that the node proved it produced something (FR-004), and that the
    judge either agreed or never ran. Every other combination is FAIL — a judge
    RETRY included, since RETRY says what the ladder should do next, not that the
    attempt was acceptable.

    An unreachable judge is the single asymmetry: it does not block a PASS, but
    the PASS is flagged `judge_unavailable` so nobody reads it later as judged
    work. Drift is carried through untouched — it flags a result whose spec moved
    under it (R8) and never moves the verdict, or the flag would silently become
    a second, quieter gate.

    `loop_digest` and `loop_summary` default to the unconfigured loop so a v1
    repo records the explicit default rather than an absent field (US4-S3).
    Callers that know the resolved loop override them; None is intentionally not
    the default here. Pre-023 replay safety is preserved because the row fields
    are additive and read back as None when missing from the store.
    """
    judge_unavailable = judge is not None and judge.outcome == JudgeOutcome.UNAVAILABLE
    judge_accepts = (
        judge is None or judge.outcome == JudgeOutcome.PASS or judge_unavailable
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


# Escalation entities --------------------------------------------------------


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
    #: 025-US2: the failing check evidence rendered into the escalation message,
    #: and — since 041-US2 — persisted with the row rather than lost on read.
    #: A workflow that writes this row at every terminal transition (041 FR-013)
    #: must not be writing rows that lose fields (FR-014).
    check_evidence: tuple[CheckFailure, ...] = ()


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
