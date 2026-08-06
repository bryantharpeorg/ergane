"""The classifier: a polled `PrSnapshot` into a `QueueOutcome`, purely (plan.md § US1).

This is the reconciliation answer to FR-004 — the interpreter telling *verified*
apart from *merged* — and it is the only place a poll becomes a decision. It is
deliberately pure: `(PrSnapshot, Landing, LandingConfig, now)` in,
`QueueOutcome | None` out. No filesystem, no `gh`, no clock but the `now` the
caller passes in (constitution IV). That is what makes it unit-testable without
a network and replay-identical under Temporal (SC-001).

The table is the plan's verbatim:

| observation | outcome |
|---|---|
| `merged_at` set | `MERGED` — however it merged |
| `state == CLOSED`, not merged | `DEQUEUED_BY_HUMAN` |
| OPEN, auto-merge gone, failing required checks | `CHECKS_FAILED` |
| OPEN, `merge_state_status == DIRTY` | `CONFLICT` |
| OPEN, auto-merge gone, no failing checks, not dirty | `DEQUEUED_BY_HUMAN` |
| OPEN, auto-merge still requested | pending (`None`) |
| pending beyond `stall_after_s` | `STALLED` |

The order is the plan's order, and the order is load-bearing: `merged_at` is
checked first so a late-landing PR is reconciled as MERGED rather than re-read
as closed or dequeued, and the stall check is *last*, so a PR that merged
(before or after the window) is never reported as STALLED.

`None` is the one non-terminal answer: "keep polling". The stall guard is
SC-002 — a landing that has sat queue-requested and unanswered past
`stall_after_s` is worth escalating, never a silent wait.
"""

from __future__ import annotations

from datetime import datetime

from factory.mergequeue.models import (
    Landing,
    LandingConfig,
    PrSnapshot,
    QueueOutcome,
)


def classify(
    snapshot: PrSnapshot,
    landing: Landing,
    config: LandingConfig,
    *,
    now: str,
) -> QueueOutcome | None:
    """One polled snapshot → one outcome, or `None` for "keep polling".

    Pure: nothing is read or written, and the only clock is `now`, an ISO-8601
    string in the workflow's `Z` spelling. `landing` is read for the stall
    window (its `enqueued_at` is the moment the wait began) and mutated nowhere.
    """
    # Merged wins over everything, however it merged (plan.md row 1).
    if snapshot.merged_at is not None:
        return QueueOutcome.MERGED

    # Closed and unmerged: the operator took it out of the queue (row 2).
    if snapshot.state == "CLOSED":
        return QueueOutcome.DEQUEUED_BY_HUMAN

    if not snapshot.auto_merge_requested:
        # The queue is no longer holding it. Distinguish the *why* the plan can
        # see from a poll: a dirty branch is a conflict the node can recover
        # from; failing required checks are a rejection worth a recovery cycle;
        # clean-and-open with auto-merge gone is the remaining known dequeuer.
        if snapshot.merge_state_status == "DIRTY":
            return QueueOutcome.CONFLICT
        if snapshot.failing_required_checks:
            return QueueOutcome.CHECKS_FAILED
        return QueueOutcome.DEQUEUED_BY_HUMAN

    # The queue is still on it. The stall guard runs last so a PR that merged
    # inside the window (or a moment after it) is MERGED, not STALLED.
    if _pending_past_stall(snapshot, landing, config):
        return QueueOutcome.STALLED

    return None


def _pending_past_stall(
    snapshot: PrSnapshot,
    landing: Landing,
    config: LandingConfig,
) -> bool:
    """Whether the wait for the queue has exceeded `stall_after_s`.

    The wait is measured from `enqueued_at` — the moment the landing entered the
    queue — to the poll's `observed_at`. A landing with no `enqueued_at` (never
    actually enqueued) is not waiting and cannot stall. A landing whose last
    outcome was already STALLED and is polled again has already been escalated;
    it stays STALLED rather than reverting to pending.
    """
    if landing.enqueued_at is None:
        return False
    if landing.outcomes and landing.outcomes[-1].outcome == QueueOutcome.STALLED:
        return True
    started = _parse(landing.enqueued_at)
    observed = _parse(snapshot.observed_at)
    if started is None or observed is None:
        return False
    return (observed - started).total_seconds() >= config.stall_after_s


def _parse(instant: str) -> datetime | None:
    """Parse the factory's ISO-8601 `Z` spelling; None if unreadable.

    The workflow stamps `…Z`; a value that will not parse is not a clock a stall
    can be measured against, and reading it as a stall would escalate a landing
    whose wait was never recorded.
    """
    try:
        return datetime.fromisoformat(instant.replace("Z", "+00:00"))
    except ValueError:
        return None
