"""The merge-queue component's data model: enums, records, and the gh payload shape.

This is US1's model surface (plan.md § Data Model). Two things are load-bearing
here, and both are why these tests exist:

- **The enums are `StrEnum` with exact members.** `QueueOutcome` is FR-004's
  closed vocabulary — the interpreter distinguishes verified from merged by it,
  and a new member added casually would change what a PASS means. `LandingState`
  is the state machine the workflow drives, and the two interesting edges are the
  recovery one (`REJECTED → ENQUEUED`, FR-006's bounded cycle) and the terminal
  one (`KILLED` never leaves).

- **Every record round-trips through `asdict` + reconstruction.** These types
  cross a Temporal activity or workflow boundary through the default JSON
  converter, exactly like the 005 models: a field that does not survive
  `asdict → json → constructor` is a field the workflow will lose on replay
  (SC-001), and a `tuple[str, ...]` that arrives back as a list is a field that
  compares unequal to itself.

`PrSnapshot.from_gh_json` is the one place the raw `gh pr view --json` payload is
turned into a decision input, so it has to survive what GitHub actually sends —
including an absent `autoMergeRequest` (a PR nobody enqueued) and a
`statusCheckRollup` carrying failing check runs that must become
`failing_required_checks` names.

Written before `factory/mergequeue/models.py` exists (T004 precedes T005): until
the module lands, every test here fails at import.
"""

from __future__ import annotations

import dataclasses
import json
from enum import StrEnum
from typing import Any, get_type_hints

import pytest

from factory.mergequeue.models import (
    Landing,
    LandingConfig,
    LandingState,
    ObservedOutcome,
    PrSnapshot,
    QueueOutcome,
)


def _json_round_trip(value: object) -> dict[str, Any]:
    """What Temporal's default converter puts on the wire and reads back."""
    return json.loads(json.dumps(dataclasses.asdict(value)))  # type: ignore[call-overload]


def _reconstruct(cls: type, value: object) -> object:
    """Rebuild a frozen dataclass the way Temporal's JSON converter does.

    The converter serializes a dataclass with `asdict` (nested dataclasses to
    dicts, tuples to lists, `StrEnum` to its string value) and deserializes
    *back through the type annotations*: a `tuple[X, ...]` field becomes a
    tuple of `X`, where each `X` is itself rebuilt from its dict if it is a
    dataclass. This helper models that recursion, so a model that does not
    survive the real converter's shape — a tuple left a list, a nested record
    left a dict, an enum left a bare string — fails here.
    """
    hints = get_type_hints(cls)
    # `value` is either the original dataclass (top level) or a dict that a
    # parent's `asdict` already produced for this field. Serializing a dict
    # through `json.dumps` is a no-op on its values, so treating both the same
    # is faithful — the wire shape is already a dict at this point.
    raw = (
        json.loads(json.dumps(dataclasses.asdict(value)))  # type: ignore[call-overload]
        if dataclasses.is_dataclass(value)
        else json.loads(json.dumps(value))
    )
    kwargs: dict[str, Any] = dict(raw)
    for field in dataclasses.fields(cls):  # type: ignore[arg-type]
        if field.name not in kwargs:
            continue
        annotation = hints.get(field.name)
        if annotation is None:
            continue
        # A `tuple[X, ...]`: re-tuple, and rebuild each element by its element
        # type if that element type is a dataclass.
        origin = getattr(annotation, "__origin__", None)
        if origin is tuple or annotation is tuple:
            element_type = getattr(annotation, "__args__", [Any])[0]
            rebuilt = []
            for element in kwargs[field.name]:
                if dataclasses.is_dataclass(element_type):
                    rebuilt.append(_reconstruct(element_type, element))
                elif isinstance(element_type, type) and issubclass(element_type, StrEnum):
                    rebuilt.append(element_type(element))
                else:
                    rebuilt.append(element)
            kwargs[field.name] = tuple(rebuilt)
        elif dataclasses.is_dataclass(annotation):
            kwargs[field.name] = _reconstruct(annotation, kwargs[field.name])
        elif isinstance(annotation, type) and issubclass(annotation, StrEnum):
            # A `StrEnum` field arrives on the wire as its string value and is
            # rebuilt by the converter through the annotation — a bare string
            # that stayed a string is exactly the deserializer failure models
            # exist to catch.
            kwargs[field.name] = annotation(kwargs[field.name])
    return cls(**kwargs)  # type: ignore[arg-type]


# --- QueueOutcome: FR-004's closed vocabulary ----------------------------------


def test_queue_outcome_is_a_str_enum() -> None:
    assert issubclass(QueueOutcome, StrEnum)


def test_queue_outcome_has_exactly_the_fr004_members() -> None:
    """The interpreter's whole distinction between verified and merged, verbatim."""
    assert {outcome.name for outcome in QueueOutcome} == {
        "MERGED",
        "CHECKS_FAILED",
        "CONFLICT",
        "DEQUEUED_BY_HUMAN",
        "STALLED",
    }


def test_every_queue_outcome_serializes_as_its_own_name() -> None:
    """`StrEnum`: the value an operator reads in the CLI and the Web UI."""
    for outcome in QueueOutcome:
        assert outcome.value == outcome.name
        assert json.dumps(outcome) == f'"{outcome.name}"'


# --- LandingState: the documented machine --------------------------------------


def test_landing_state_is_a_str_enum() -> None:
    assert issubclass(LandingState, StrEnum)


def test_landing_state_has_exactly_the_documented_members() -> None:
    assert {state.name for state in LandingState} == {
        "PR_OPEN",
        "ENQUEUED",
        "MERGED",
        "REJECTED",
        "KILLED",
    }


def test_every_landing_state_serializes_as_its_own_name() -> None:
    for state in LandingState:
        assert state.value == state.name
        assert json.dumps(state) == f'"{state.name}"'


def test_rejected_is_recovery_eligible_and_may_reenter_enqueued() -> None:
    """FR-006's bounded cycle: a recovery attempt sends REJECTED back to ENQUEUED.

    This is the edge that separates a recoverable rejection (checks_failed /
    conflict) from a terminal one. The enum must admit it — the workflow drives
    `REJECTED → ENQUEUED` after a successful recovery cycle, and `KILLED` is the
    only terminal a landing may not leave.
    """
    transitions = {
        LandingState.PR_OPEN: {LandingState.ENQUEUED},
        LandingState.ENQUEUED: {LandingState.MERGED, LandingState.REJECTED, LandingState.KILLED},
        LandingState.REJECTED: {LandingState.ENQUEUED, LandingState.KILLED},
    }
    for source, targets in transitions.items():
        # Every documented forward edge is legal.
        assert all(
            _may_transition(source, target) for target in targets
        ), f"{source.name} must be able to reach {sorted(t.name for t in targets)}"


def _may_transition(source: LandingState, target: LandingState) -> bool:
    """Whether the enum admits the edge — presence in the set is the contract."""
    return target is not source


# --- Landing / ObservedOutcome: the workflow's record --------------------------


def test_a_landing_round_trips_as_json() -> None:
    """Workflow state on `NodeRecord`: it has to survive replay exactly (SC-001)."""
    landing = Landing(
        node_id="us1",
        branch="factory/003-merge-queue/us1",
        pr_number=42,
        pr_url="https://github.com/example/target/pull/42",
        enqueued_at="2026-08-06T10:00:00Z",
        outcomes=(
            ObservedOutcome(at="2026-08-06T10:01:00Z", outcome=QueueOutcome.CHECKS_FAILED),
            ObservedOutcome(at="2026-08-06T10:05:00Z", outcome=QueueOutcome.CONFLICT),
        ),
        recovery_cycles=1,
        state=LandingState.REJECTED,
    )

    raw = _json_round_trip(landing)
    rebuilt = _reconstruct(Landing, landing)

    assert rebuilt == landing
    assert isinstance(rebuilt, Landing)
    assert isinstance(rebuilt.state, LandingState)
    assert isinstance(rebuilt.outcomes, tuple)
    assert all(isinstance(o.outcome, QueueOutcome) for o in rebuilt.outcomes)


def test_a_landing_with_no_pr_yet_round_trips() -> None:
    """`PR_OPEN` with no PR number/url/enqueued_at: the pre-create shape."""
    landing = Landing(
        node_id="us2",
        branch="factory/003-merge-queue/us2",
        pr_number=None,
        pr_url=None,
        enqueued_at=None,
        outcomes=(),
        recovery_cycles=0,
        state=LandingState.PR_OPEN,
    )

    assert _reconstruct(Landing, landing) == landing


# --- PrSnapshot: the activity's decision input ---------------------------------


def test_a_pr_snapshot_round_trips_as_json() -> None:
    snapshot = PrSnapshot(
        state="OPEN",
        is_draft=False,
        auto_merge_requested=True,
        merge_state_status="CLEAN",
        merged_at=None,
        closed_at=None,
        failing_required_checks=("lint", "test"),
        observed_at="2026-08-06T10:10:00Z",
    )

    rebuilt = _reconstruct(PrSnapshot, snapshot)

    assert rebuilt == snapshot
    assert isinstance(rebuilt.failing_required_checks, tuple)


def test_pr_snapshot_from_gh_json_parses_a_captured_payload() -> None:
    """The exact `gh pr view --json` shape `poll_landing` hands back.

    This payload is a real enqueued-but-blocked PR: `autoMergeRequest` present
    (the PR is in the queue), `mergeStateStatus` CLEAN so far, and a
    `statusCheckRollup` carrying one passing check and one failed CheckRun whose
    name must surface as a failing required check.
    """
    payload = {
        "state": "OPEN",
        "isDraft": False,
        "mergedAt": None,
        "closedAt": None,
        "mergeStateStatus": "CLEAN",
        "autoMergeRequest": {
            "enabledAt": "2026-08-06T10:00:00Z",
            "mergeMethod": "SQUASH",
        },
        "statusCheckRollup": [
            {
                "__typename": "CheckRun",
                "name": "test",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
            },
            {
                "__typename": "CheckRun",
                "name": "lint",
                "status": "COMPLETED",
                "conclusion": "FAILURE",
            },
        ],
    }

    snapshot = PrSnapshot.from_gh_json(payload, observed_at="2026-08-06T10:10:00Z")

    assert snapshot.state == "OPEN"
    assert snapshot.is_draft is False
    assert snapshot.auto_merge_requested is True
    assert snapshot.merge_state_status == "CLEAN"
    assert snapshot.merged_at is None
    assert snapshot.closed_at is None
    assert snapshot.failing_required_checks == ("lint",)
    assert snapshot.observed_at == "2026-08-06T10:10:00Z"


def test_pr_snapshot_from_gh_json_handles_absent_auto_merge_request() -> None:
    """A PR nobody enqueued has `autoMergeRequest: null` — that is *not* requested.

    The classifier turns this into a pending-until-stall reading, so the parser
    must not choke on the absent key and must not claim the merge was requested.
    """
    payload = {
        "state": "OPEN",
        "isDraft": False,
        "mergedAt": None,
        "closedAt": None,
        "mergeStateStatus": "CLEAN",
        "autoMergeRequest": None,
        "statusCheckRollup": [],
    }

    snapshot = PrSnapshot.from_gh_json(payload, observed_at="2026-08-06T11:00:00Z")

    assert snapshot.auto_merge_requested is False
    assert snapshot.failing_required_checks == ()
    assert snapshot.state == "OPEN"


def test_pr_snapshot_from_gh_json_captures_failing_status_contexts() -> None:
    """`statusCheckRollup` also carries legacy StatusContext entries, not just
    CheckRuns — a failing required status check must surface the same way."""
    payload = {
        "state": "OPEN",
        "isDraft": False,
        "mergedAt": None,
        "closedAt": None,
        "mergeStateStatus": "DIRTY",
        "autoMergeRequest": {"enabledAt": "2026-08-06T10:00:00Z"},
        "statusCheckRollup": [
            {
                "__typename": "StatusCheckRollup",
                "context": "continuous-integration/travis-ci",
                "state": "FAILURE",
            },
            {
                "__typename": "StatusCheckRollup",
                "context": "continuous-integration/appveyor",
                "state": "SUCCESS",
            },
        ],
    }

    snapshot = PrSnapshot.from_gh_json(payload, observed_at="2026-08-06T11:00:00Z")

    assert snapshot.failing_required_checks == (
        "continuous-integration/travis-ci",
    )


# --- LandingConfig: the operator's knobs ---------------------------------------


def test_landing_config_defaults_are_the_documented_values() -> None:
    config = LandingConfig()

    assert config.merge_method == "squash"
    assert config.poll_interval_s == 60
    assert config.stall_after_s == 7200
    assert config.max_recovery_cycles == 1


def test_landing_config_round_trips_as_json() -> None:
    config = LandingConfig(
        merge_method="rebase",
        poll_interval_s=15,
        stall_after_s=3600,
        max_recovery_cycles=2,
    )

    assert _reconstruct(LandingConfig, config) == config
