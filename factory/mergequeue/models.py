"""The merge-queue component's data model: enums, records, and the gh payload shape.

US1's whole distinction between *verified* and *merged* — FR-004 — lives in two
`StrEnum`s and one record. `QueueOutcome` is the closed vocabulary of what a
landing's queue history can say; `LandingState` is the machine the workflow
drives across a landing's life; `Landing` is that life as workflow state on a
`NodeRecord`; `PrSnapshot` is what one poll of GitHub's queue yields, and the
classifier's only input from the world.

All of it crosses a Temporal boundary through the default JSON converter, so the
discipline is the 005 models' (models.py docstring): `StrEnum`, not
`class X(str, Enum)` — only `StrEnum` survives the converter's *deserializer*,
which rebuilds a field annotated with any other str-subclass enum as a list of
one-character strings. And every record is frozen so a value that crossed an
activity boundary can never be edited in place.

`PrSnapshot.from_gh_json` is the one place the raw `gh pr view --json` payload
becomes a decision input, so it has to survive what GitHub actually sends: an
absent `autoMergeRequest` (a PR nobody enqueued is *not* queue-requested), and a
`statusCheckRollup` that mixes `CheckRun` entries (named checks with a
`conclusion`) and legacy `StatusCheckRollup` entries (named contexts with a
`state`). Failing required checks are what the classifier reads to distinguish
`CHECKS_FAILED` from `DEQUEUED_BY_HUMAN` and a pending `CLEAN` wait, so a run
whose conclusion or state is a failure must surface here by name.

`TargetRepoProfile` and `Finding` are US3's preflight surface (plan.md § US1,
T035's slice-containment note): they live in this module because they are part
of the merge-queue component's model, whether or not US1's slice exercises them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

#: 049-US3: GitHub's spelling of "the target moved under this proposal". It is
#: spelled once, here, at the boundary where a stored record is rebuilt — never
#: in the classifier, which is the whole of FR-010.
_LEGACY_CONFLICT = "DIRTY"


# US2: one failing check's evidence as the recovery prompt and escalation page
# receive it. Lives here rather than in gh.py so the model's own dataclasses can
# annotate tuples of it without creating a circular import (gh.py already imports
# PrSnapshot from this module).
@dataclass(frozen=True)
class CheckFailure:
    """US2: one failing check's evidence.

    `log_tail` is the last of `gh run view --log-failed` for the run id parsed
    from `url`; `note` is empty when the tail was fetched, and states why it was
    not fetched when `log_tail` is empty.
    """

    name: str
    url: str
    log_tail: str
    note: str


# FR-004's closed vocabulary ---------------------------------------------------


class QueueOutcome(StrEnum):
    """What one landing's queue history can say (plan.md § Data Model).

    The interpreter's distinction between verified and merged is made with these
    exact five members; a new member would change what a PASS means, so the set
    is closed on purpose.
    """

    MERGED = "MERGED"
    CHECKS_FAILED = "CHECKS_FAILED"
    CONFLICT = "CONFLICT"
    DEQUEUED_BY_HUMAN = "DEQUEUED_BY_HUMAN"
    STALLED = "STALLED"


class RejectionCause(StrEnum):
    """Why a landing was rejected — the fact the recovery routing turns on (069-US1).

    Two members, because there are only two answers that change what the node
    owes: either the world moved under a tree that was never wrong, or the tree
    itself is what the queue refused. `factory.mergequeue.rejection` decides
    which from structural facts; nothing here reads a forge's wording or a retry
    count (FR-005).

    `BASE_MOVED` is what a rebase answers, and it is charged to neither budget.
    `NODE_CODE` is charged exactly as it always was — it is the reason a budget
    exists.
    """

    BASE_MOVED = "BASE_MOVED"
    NODE_CODE = "NODE_CODE"


class LandingState(StrEnum):
    """Where one landing stands: `PR_OPEN → ENQUEUED → MERGED | REJECTED | KILLED`.

    `REJECTED` is the recovery-eligible rejection (checks_failed / conflict): it
    may return to `ENQUEUED` after a successful recovery cycle (FR-006's bounded
    cycle). `KILLED` is terminal — operator kill, dequeue-by-human, escalation
    default, epic kill, and (078-US3) a landing poll that stopped, which is the
    same fact stated from the factory's side: nothing is driving this landing
    any more. Nothing leaves it, and the branch outlives it in every case.
    """

    PR_OPEN = "PR_OPEN"
    ENQUEUED = "ENQUEUED"
    MERGED = "MERGED"
    REJECTED = "REJECTED"
    KILLED = "KILLED"


# The records ------------------------------------------------------------------


@dataclass(frozen=True)
class ObservedOutcome:
    """One entry in a landing's queue history — what the escalation quotes.

    US2: `failing_checks` carries the names of the required checks the
    classifier saw failing when the outcome is `CHECKS_FAILED`. It defaults to
    `()` so pre-spec histories deserialize and replay without change.
    """

    at: str
    outcome: QueueOutcome
    failing_checks: tuple[str, ...] = ()


@dataclass(frozen=True)
class Landing:
    """One node's landing, as workflow state on its `NodeRecord`.

    `outcomes` is the queue history — every time the poll classified a terminal
    (or stall) outcome, in order, so a human being paged can see the sequence
    that led here. `enqueued_at` and the PR identity are set by the landing
    phase; `recovery_cycles` counts how many times `REJECTED` has gone back to
    `ENQUEUED` (bounded by `LandingConfig.max_recovery_cycles`, FR-006).

    US2: `check_evidence` is the fetched (name, URL, log tail, note) record for
    the latest `CHECKS_FAILED` outcome, used by the recovery prompt and the
    escalation page. Default `()` keeps CONFLICT and pre-spec histories intact.
    """

    node_id: str
    branch: str
    pr_number: int | None = None
    pr_url: str | None = None
    enqueued_at: str | None = None
    outcomes: tuple[ObservedOutcome, ...] = ()
    recovery_cycles: int = 0
    state: LandingState = LandingState.PR_OPEN
    check_evidence: tuple[CheckFailure, ...] = ()
    #: US3: the commit the branch was pushed with when it was last enqueued.
    #: Default `None` keeps pre-spec histories replayable (FR-009).
    enqueued_tip: str | None = None
    #: 069-US1: the target head the enqueued tree was built on — the *base* half
    #: of what the queue tested, where `enqueued_tip` is the tree half. Compared
    #: against the base the forge reports at the poll, it is the structural fact
    #: that tells "a sibling landed under me" from "my tree is wrong" (FR-005).
    #: `None` — a pre-069 history, or a forge that reports no base — reads as
    #: "unknown", and an unknown cause is charged exactly as it was before.
    enqueued_base: str | None = None
    #: 069-US1: the cause the poll classified for the latest rejection, `None`
    #: until one is classified. Recorded at the moment of observation because
    #: that is the only moment the snapshot exists; the recovery routing reads it
    #: rather than re-deriving it from a world that has moved again since.
    rejection_cause: RejectionCause | None = None
    #: 069-US1: how many times this landing has been rebased and requeued
    #: without spending either budget. Bounded by
    #: `LandingConfig.max_free_rebases` (FR-004): a node whose siblings land
    #: forever must still eventually stop, and a free path with no bound turns a
    #: bounded expensive failure into an unbounded cheap one.
    free_rebases: int = 0


@dataclass(frozen=True)
class PrSnapshot:
    """What one poll of GitHub's queue saw — the classifier's only input from the world.

    `state` is GitHub's PR state (`OPEN|CLOSED|MERGED`), kept as the string GitHub
    sent rather than re-derived, because the classifier reads it verbatim (a
    merged PR is GitHub's word, never inferred). `failing_required_checks` is the
    subset of the rollup whose conclusion/state was a failure, by name; an empty
    tuple is a rollup with nothing failing. `observed_at` is the workflow's clock
    at the poll, so a stall is measured on the interpreter's time, not the
    subprocess's.
    """

    state: str
    is_draft: bool
    auto_merge_requested: bool
    merge_state_status: str
    merged_at: str | None
    closed_at: str | None
    failing_required_checks: tuple[str, ...]
    observed_at: str
    #: 049-US3: the conflict fact in the *factory's* vocabulary — the target has
    #: moved under this proposal and it no longer applies as it stands.
    #: `merge_state_status` stays as GitHub's spelling of the same observation,
    #: kept as evidence an operator can read; nothing decides from it any more
    #: (FR-010). Defaulted so a pre-spec history deserializes — `__post_init__`.
    in_conflict: bool = False
    #: 069-US1: the head of the branch this proposal is offered against, as the
    #: forge reports it at this poll. Compared with `Landing.enqueued_base` it
    #: says whether the world moved under the tree the queue was testing. `None`
    #: is "this forge did not say", never "it did not move": an unknown base is
    #: classified as the node's own fault and charged as it always was.
    base_sha: str | None = None

    def __post_init__(self) -> None:
        """Carry a pre-049 history's conflict across, once, at the boundary.

        A record written before this spec recorded the conflict in the only
        spelling there was, and histories holding one are replayed: a replay
        reaching "keep polling" where the original run reached `CONFLICT` would
        diverge from its own history — the defect class 032, 038 and 039 each
        shipped. So the legacy spelling is read here, in the constructor, which
        is also where `from_gh_json` lands every GitHub observation. The
        classifier never sees it, and a forge that never heard of `DIRTY` is
        unaffected.
        """
        if not self.in_conflict and self.merge_state_status == _LEGACY_CONFLICT:
            object.__setattr__(self, "in_conflict", True)

    @classmethod
    def from_gh_json(cls, payload: Mapping[str, Any], *, observed_at: str) -> "PrSnapshot":
        """One `gh pr view --json` payload, turned into a decision input.

        `autoMergeRequest` is null for a PR nobody enqueued, and that must read as
        "not requested", not as an error or as an unreadable field. The rollup
        mixes named check runs and legacy status contexts; a failing one surfaces
        by name, a passing or absent one does not. No value that is missing is
        invented — a PR with no `mergedAt` simply has `merged_at=None`.
        """
        auto_merge = payload.get("autoMergeRequest")
        failing = tuple(
            name
            for name in _failing_check_names(payload.get("statusCheckRollup") or [])
        )
        return cls(
            state=str(payload.get("state") or ""),
            is_draft=bool(payload.get("isDraft")),
            auto_merge_requested=auto_merge is not None,
            merge_state_status=str(payload.get("mergeStateStatus") or ""),
            merged_at=_nullable_str(payload.get("mergedAt")),
            closed_at=_nullable_str(payload.get("closedAt")),
            failing_required_checks=failing,
            observed_at=observed_at,
            # 069-US1: `baseRefOid` is GitHub's spelling of "the head this PR is
            # offered against, right now". Read here rather than derived, because
            # the whole point is to compare the base the queue is testing with the
            # base the node built on, and a value we computed ourselves would be
            # our opinion of the world rather than the forge's report of it.
            base_sha=_nullable_str(payload.get("baseRefOid")),
        )


@dataclass(frozen=True)
class TargetRepoProfile:
    """US3's preflight read of the target repo (plan.md § US1, T035).

    `repo` is the slug exactly as `gh` reports it; `required_checks` is what the
    queue will demand of a PR, `declared_gates` what the repo's own `factory.yaml`
    names — the preflight compares them to decide whether a landing can ever be
    enqueued. `findings` is the actionable list, and `passed` is the conjunction
    over `Finding.blocking`: a profile carrying any blocking finding cannot
    land. A finding may be non-passing without being blocking — see `Severity`.
    """

    repo: str
    default_branch: str
    visibility: str
    queue_enabled: bool
    required_checks: tuple[str, ...]
    declared_gates: tuple[str, ...]
    findings: tuple["Finding", ...]
    passed: bool

    @classmethod
    def from_readiness(
        cls,
        *,
        repo: str,
        reading: Any,
        policy: Any,
        declared_gates: tuple[str, ...],
        findings: tuple["Finding", ...],
        passed: bool,
    ) -> "TargetRepoProfile":
        """Build the report from a forge's two readings and a decided verdict.

        The three descriptive fields above keep this record's own spelling — an
        operator's report and every stored payload already read that way — so
        the mapping onto them belongs with the record that owns them, not in a
        judgment that may never spell them (049 US2, FR-006). `reading` and
        `policy` are structural: `forge.py` imports `Finding` from here.
        """
        return cls(
            repo=repo,
            default_branch=reading.default_branch,
            visibility=reading.visibility,
            queue_enabled=policy.gates_on_named_checks,
            required_checks=tuple(policy.required_checks),
            declared_gates=declared_gates,
            findings=findings,
            passed=passed,
        )


class Severity(StrEnum):
    """What a finding that did not pass does to the run it is part of (061 US3).

    Two members, because a report has exactly two useful answers to "and now
    what?": either this refuses the repository, or it is something the operator
    must see and may decide to keep. It is meaningful only when `passed` is
    False — a passing finding carries the default and nothing reads it.

    `WARNING` exists for one shape of fact: a configuration that is *legal and
    dangerous*, where the danger is a choice an operator is entitled to make.
    Making such a finding fail closed is not the safe direction it looks like:
    a wall in front of a deliberate choice is edited around, and what replaces
    it is a configuration nothing recognises at all (061 FR-009, plan trap 6).
    """

    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass(frozen=True)
class Finding:
    """One preflight finding (US3): which check, whether it passed, and how to fix it.

    `detail` is actionable — it names what to change, not just what is wrong — so
    the operator reading a preflight report can go and change it without re-deriving
    the problem from a slug.

    `severity` (061 US3) separates "this did not pass" from "this refuses the
    repository", which were the same claim until a condition arrived that is
    neither a pass nor a refusal. It defaults to `ERROR`, so every finding
    written before it existed means exactly what it always meant, and an older
    history decodes at the same value (`tests/test_temporal_payload_shape.py`).
    """

    check: str
    passed: bool
    detail: str
    severity: Severity = Severity.ERROR

    @property
    def blocking(self) -> bool:
        """Whether this finding refuses the repository it is about.

        The predicate every verdict is now the conjunction over — `passed`
        alone would read a warning as a refusal, which is the one thing FR-009
        forbids. Compared by value rather than identity because a finding that
        crossed a payload boundary carries the converter's reconstruction of the
        member, not this module's.
        """
        return not self.passed and self.severity == Severity.ERROR

    @property
    def mark(self) -> str:
        """`PASS`, `WARN` or `FAIL` — the three-way label every report prints.

        Spelled once, here, rather than as a conditional in each of the four
        renderers over these findings: a warning rendered as `FAIL` in one of
        them is the report contradicting the exit code beside it.
        """
        if self.passed:
            return "PASS"
        return "FAIL" if self.blocking else "WARN"


@dataclass(frozen=True)
class LandingConfig:
    """The operator's landing knobs — `EpicInput`'s new field (plan.md § US1).

    Defaults are code defaults the operator overrides per epic; none of these is
    a constant buried in the workflow. `merge_method` is passed verbatim to
    `gh pr merge --auto --<method>` and must match a method the repo allows.
    `stall_after_s` bounds how long a landing may sit queue-requested but
    unanswered before the classifier calls it `STALLED`; `max_recovery_cycles` is
    FR-006's "one bounded cycle".
    """

    merge_method: str = "squash"
    poll_interval_s: int = 60
    stall_after_s: int = 7200
    max_recovery_cycles: int = 1
    #: 069-US1: how many times one landing may be rebased and requeued for a
    #: moved base without spending an attempt, a debugger cycle or a recovery
    #: cycle (FR-004). Three, because that is what survives an ordinary fan-out
    #: — every sibling that lands ahead of a node bumps it once — while still
    #: being a number a node reaches. Past it the rejection is charged like any
    #: other, so the node ends at the bounds it always had rather than never.
    max_free_rebases: int = 3


# Helpers ----------------------------------------------------------------------


def _nullable_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _failing_check_names(rollup: list[Any]) -> list[str]:
    """Names of rollup entries whose outcome is a failure, whatever their shape.

    `gh pr view --json statusCheckRollup` returns a heterogeneous list: `CheckRun`
    entries carry a `conclusion` (and `name`); legacy `StatusCheckRollup` entries
    carry a `state` (and `context`). A run that is still in progress is not a
    failure, and an entry with no failing signal is not named.
    """
    names: list[str] = []
    for entry in rollup:
        if not isinstance(entry, dict):
            continue
        typename = entry.get("__typename")
        if typename == "CheckRun":
            if entry.get("conclusion") == "FAILURE":
                names.append(str(entry.get("name") or ""))
        elif typename in ("StatusCheckRollup", "StatusContext"):
            if entry.get("state") == "FAILURE":
                names.append(str(entry.get("context") or ""))
    # A run whose name came back empty carries nothing the classifier can quote.
    return [name for name in names if name]
