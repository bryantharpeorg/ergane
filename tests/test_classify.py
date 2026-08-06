"""The classifier: a polled `PrSnapshot` into a `QueueOutcome`, purely (plan.md § US1).

This is the reconciliation answer to FR-004 — the interpreter telling *verified*
apart from *merged* — and it is deliberately pure: `(PrSnapshot, Landing,
LandingConfig, now)` in, `QueueOutcome | None` out, no filesystem, no `gh`, no
clock but the one passed in (constitution IV). That is what makes it unit-tested
without a network and replay-identical under Temporal (SC-001).

The table under test is the plan's verbatim:

| observation | outcome |
|---|---|
| `merged_at` set | `MERGED` — however it merged; a human merging manually is reconciled, not fought |
| `state == CLOSED`, not merged | `DEQUEUED_BY_HUMAN` — treated as operator kill |
| OPEN, auto-merge gone, failing required checks | `CHECKS_FAILED` |
| OPEN, `merge_state_status == DIRTY` | `CONFLICT` |
| OPEN, auto-merge gone, no failing checks, not dirty | `DEQUEUED_BY_HUMAN` |
| OPEN, auto-merge still requested | pending (`None`) — keep polling |
| pending beyond `stall_after_s` with no state change | `STALLED` |

`None` means "keep polling" — the only non-terminal answer, and the one that
lets a background poll task decide when to stop. `STALLED` is the guard against
a silent stall (SC-002): a landing that has sat queue-requested and unanswered
past `stall_after_s` is a landing worth escalating, not one to wait on forever.

Written before `factory/mergequeue/classify.py` exists (T009 precedes T010):
until the module lands, every test here fails at import.
"""

from __future__ import annotations

import pytest

from factory.mergequeue.classify import classify
from factory.mergequeue.models import (
    Landing,
    LandingConfig,
    LandingState,
    PrSnapshot,
    QueueOutcome,
)
from tests.fake_gh import FakeGh

#: A landed (MERGED) PR, and the landing record the classifier reconciles.
BRANCH = "factory/003-merge-queue/us1"


def _landing(**overrides) -> Landing:  # type: ignore[no-untyped-def]
    fields = dict(
        node_id="us1",
        branch=BRANCH,
        pr_number=7,
        pr_url="https://x/pull/7",
        enqueued_at="2026-08-06T10:00:00Z",
        outcomes=(),
        recovery_cycles=0,
        state=LandingState.ENQUEUED,
    )
    fields.update(overrides)
    return Landing(**fields)  # type: ignore[arg-type]


def _snapshot(**overrides) -> PrSnapshot:  # type: ignore[no-untyped-def]
    fields = dict(
        state="OPEN",
        is_draft=False,
        auto_merge_requested=True,
        merge_state_status="CLEAN",
        merged_at=None,
        closed_at=None,
        failing_required_checks=(),
        observed_at="2026-08-06T10:05:00Z",
    )
    fields.update(overrides)
    return PrSnapshot(**fields)  # type: ignore[arg-type]


# --- the classification table -------------------------------------------------


def test_merged_at_set_is_merged_however_it_merged() -> None:
    """A manually-merged PR is reconciled as MERGED, not fought (plan.md)."""
    snapshot = _snapshot(
        state="MERGED", merged_at="2026-08-06T10:04:00Z", auto_merge_requested=False
    )

    assert classify(snapshot, _landing(), LandingConfig(), now="2026-08-06T10:05:00Z") == (
        QueueOutcome.MERGED
    )


def test_merged_while_enqueued_is_merged() -> None:
    """Auto-merge still requested but `mergedAt` set: GitHub merged it, period."""
    snapshot = _snapshot(state="MERGED", merged_at="2026-08-06T10:04:00Z")

    assert classify(snapshot, _landing(), LandingConfig(), now="2026-08-06T10:05:00Z") == (
        QueueOutcome.MERGED
    )


def test_closed_unmerged_is_dequeued_by_human() -> None:
    """A closed, unmerged PR is an operator's intervention (kill)."""
    snapshot = _snapshot(
        state="CLOSED", closed_at="2026-08-06T10:03:00Z", auto_merge_requested=False
    )

    assert classify(snapshot, _landing(), LandingConfig(), now="2026-08-06T10:05:00Z") == (
        QueueOutcome.DEQUEUED_BY_HUMAN
    )


def test_auto_merge_gone_with_failing_required_checks_is_checks_failed() -> None:
    snapshot = _snapshot(
        auto_merge_requested=False,
        failing_required_checks=("lint", "test"),
    )

    assert classify(snapshot, _landing(), LandingConfig(), now="2026-08-06T10:05:00Z") == (
        QueueOutcome.CHECKS_FAILED
    )


def test_dirty_merge_state_status_is_conflict() -> None:
    """`mergeStateStatus == DIRTY` means the branch is unmergeable as-is."""
    snapshot = _snapshot(auto_merge_requested=False, merge_state_status="DIRTY")

    assert classify(snapshot, _landing(), LandingConfig(), now="2026-08-06T10:05:00Z") == (
        QueueOutcome.CONFLICT
    )


def test_auto_merge_gone_clean_and_open_is_dequeued_by_human() -> None:
    """The remaining known dequeuer: nobody pulled auto-merge, nothing failed.

    A heuristic, flagged in the plan — but the queue is no longer going to land
    it, so it is not worth waiting on as pending.
    """
    snapshot = _snapshot(
        auto_merge_requested=False,
        failing_required_checks=(),
        merge_state_status="CLEAN",
    )

    assert classify(snapshot, _landing(), LandingConfig(), now="2026-08-06T10:05:00Z") == (
        QueueOutcome.DEQUEUED_BY_HUMAN
    )


def test_auto_merge_still_requested_is_pending() -> None:
    """The queue is still on it — `None` means keep polling."""
    snapshot = _snapshot(auto_merge_requested=True)

    assert classify(snapshot, _landing(), LandingConfig(), now="2026-08-06T10:05:00Z") is None


# --- the stall guard (SC-002) -------------------------------------------------


def test_pending_past_stall_after_is_stalled() -> None:
    """A queue-requested PR still unanswered after `stall_after_s` is a stall."""
    config = LandingConfig(stall_after_s=3600)
    # Enqueued at 10:00, polled at 11:05 — 65 minutes, past the hour stall.
    landing = _landing(enqueued_at="2026-08-06T10:00:00Z")
    snapshot = _snapshot(
        auto_merge_requested=True,
        observed_at="2026-08-06T11:05:00Z",
    )

    assert classify(snapshot, landing, config, now="2026-08-06T11:05:00Z") == (
        QueueOutcome.STALLED
    )


def test_pending_within_stall_window_is_still_pending() -> None:
    config = LandingConfig(stall_after_s=3600)
    landing = _landing(enqueued_at="2026-08-06T10:00:00Z")
    snapshot = _snapshot(auto_merge_requested=True, observed_at="2026-08-06T10:30:00Z")

    assert classify(snapshot, landing, config, now="2026-08-06T10:30:00Z") is None


def test_merged_is_not_stalled_even_past_the_window() -> None:
    """A merge that landed late is MERGED, never STALLED — the outcome wins."""
    snapshot = _snapshot(
        state="MERGED",
        merged_at="2026-08-06T12:00:00Z",
        auto_merge_requested=True,
    )
    landing = _landing(enqueued_at="2026-08-06T10:00:00Z")
    config = LandingConfig(stall_after_s=3600)

    assert classify(snapshot, landing, config, now="2026-08-06T12:05:00Z") == (
        QueueOutcome.MERGED
    )


# --- purity -------------------------------------------------------------------


def test_classification_is_a_pure_function_of_its_arguments() -> None:
    """Same (snapshot, landing, config, now) → same outcome, every call.

    Nothing is read, nothing is mutated, no clock is consulted except `now`.
    """
    config = LandingConfig()
    landing = _landing()
    snapshot = _snapshot(
        state="CLOSED", closed_at="2026-08-06T10:03:00Z", auto_merge_requested=False
    )

    first = classify(snapshot, landing, config, now="2026-08-06T10:05:00Z")
    second = classify(snapshot, landing, config, now="2026-08-06T10:05:00Z")

    assert first == second == QueueOutcome.DEQUEUED_BY_HUMAN
    assert landing.outcomes == ()  # not mutated
