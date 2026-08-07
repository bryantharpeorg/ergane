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

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Sequence


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
    """

    PASS = "PASS"
    FAIL = "FAIL"
    TIMEOUT = "TIMEOUT"
    CONFIG_ERROR = "CONFIG_ERROR"


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
    DEBUGGER = "DEBUGGER"
    ESCALATE = "ESCALATE"
    KILLED = "KILLED"


class EscalationChoice(StrEnum):
    """Operator options on an escalation, 1:1 with the inline buttons (FR-008).

    Values stay short because they ride inside `callback_data`
    (`esc:<12-hex>:<choice>`), which Telegram caps at 64 bytes.
    """

    RETRY = "RETRY"
    KILL = "KILL"
    PAUSE_EPIC = "PAUSE_EPIC"


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
class FactoryConfig:
    """The target repo's committed `factory.yaml`, schema v1.

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
    standards: str | None = None


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
    """

    name: str
    command: str
    status: GateStatus
    exit_code: int | None
    duration_s: float
    output_tail: str
    concurrent_gates: int = 0


# Diff/artifact entities -----------------------------------------------------


@dataclass(frozen=True)
class OutputCheck:
    """The anti-rubber-stamp check: did the node actually produce something?

    A write-scope node with a clean worktree fails on `has_diff` alone (FR-004) —
    no gate suite and no judge can rescue it, because passing tests over an empty
    diff is precisely the failure this exists to catch. Read scopes have nothing
    to diff, so they are judged on `expected_artifacts` existing and being
    non-empty instead; `artifacts_present` is None when artifacts do not apply.
    """

    write_scope: str
    has_diff: bool
    expected_artifacts: list[str]
    artifacts_present: bool | None
    passed: bool


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

    Everything else is copied verbatim. The retry prompt and the escalation
    summary are built from the same evidence this writes to the store (FR-006,
    SC-004, SC-005), so a bundle edited on its way through would make the record
    disagree with the prompt.
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
    )


# Ladder entities (pure) -----------------------------------------------------


@dataclass(frozen=True)
class VerificationConfig:
    """Per-deployment caps for the retry ladder.

    `max_judge_retries` is bounded *inside* `max_attempts`, not on top of it:
    exhausted judge retries consume attempts as ordinary failures (SC-003).
    """

    max_attempts: int = 3
    max_judge_retries: int = 2
    debugger_cycles: int = 1
    gate_timeout_s: int = 600
    escalation_timeout_s: int = 3600


@dataclass(frozen=True)
class AttemptRecord:
    """One entry of the ladder's input history.

    `persona` is what distinguishes a debugger cycle from an ordinary retry, and
    `judge_outcome` is None when the judge never ran — the ladder needs both to
    tell "failed the gates three times" from "the judge asked for two rewrites".
    """

    attempt: int
    persona: str
    verdict: OverallVerdict
    judge_outcome: JudgeOutcome | None = None


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
