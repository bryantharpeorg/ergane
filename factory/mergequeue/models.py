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


class LandingState(StrEnum):
    """Where one landing stands: `PR_OPEN → ENQUEUED → MERGED | REJECTED | KILLED`.

    `REJECTED` is the recovery-eligible rejection (checks_failed / conflict): it
    may return to `ENQUEUED` after a successful recovery cycle (FR-006's bounded
    cycle). `KILLED` is terminal — operator kill, dequeue-by-human, escalation
    default, epic kill — and nothing leaves it.
    """

    PR_OPEN = "PR_OPEN"
    ENQUEUED = "ENQUEUED"
    MERGED = "MERGED"
    REJECTED = "REJECTED"
    KILLED = "KILLED"


# The records ------------------------------------------------------------------


@dataclass(frozen=True)
class ObservedOutcome:
    """One entry in a landing's queue history — what the escalation quotes."""

    at: str
    outcome: QueueOutcome


@dataclass(frozen=True)
class Landing:
    """One node's landing, as workflow state on its `NodeRecord`.

    `outcomes` is the queue history — every time the poll classified a terminal
    (or stall) outcome, in order, so a human being paged can see the sequence
    that led here. `enqueued_at` and the PR identity are set by the landing
    phase; `recovery_cycles` counts how many times `REJECTED` has gone back to
    `ENQUEUED` (bounded by `LandingConfig.max_recovery_cycles`, FR-006).
    """

    node_id: str
    branch: str
    pr_number: int | None = None
    pr_url: str | None = None
    enqueued_at: str | None = None
    outcomes: tuple[ObservedOutcome, ...] = ()
    recovery_cycles: int = 0
    state: LandingState = LandingState.PR_OPEN


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
        )


@dataclass(frozen=True)
class TargetRepoProfile:
    """US3's preflight read of the target repo (plan.md § US1, T035).

    `repo` is the slug exactly as `gh` reports it; `required_checks` is what the
    queue will demand of a PR, `declared_gates` what the repo's own `factory.yaml`
    names — the preflight compares them to decide whether a landing can ever be
    enqueued. `findings` is the actionable list, and `passed` is their
    conjunction: a profile that fails any finding cannot land.
    """

    repo: str
    default_branch: str
    visibility: str
    queue_enabled: bool
    required_checks: tuple[str, ...]
    declared_gates: tuple[str, ...]
    findings: tuple["Finding", ...]
    passed: bool


@dataclass(frozen=True)
class Finding:
    """One preflight finding (US3): which check, whether it passed, and how to fix it.

    `detail` is actionable — it names what to change, not just what is wrong — so
    the operator reading a preflight report can go and change it without re-deriving
    the problem from a slug.
    """

    check: str
    passed: bool
    detail: str


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
