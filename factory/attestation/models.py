"""Typed identities for one audit-packet execution."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RungSelection:
    """One resolved rung, frozen at dispatch."""

    persona: str = ""
    runner: str = ""
    route: str = ""
    model_aliases: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class LaunchRecord:
    """The durable identity and lifecycle of one launch."""

    target: str
    spec_revision: str
    spec_fingerprint: str
    epic_id: str
    epic_workflow_id: str
    epic_run_id: str
    node_id: str
    invocation_id: str
    ladder_ordinal: int
    launch_ordinal: int
    phase: str
    form: str
    scoring_job_id: str | None
    scoring_call_ordinal: int | None
    delivery_id: str | None
    key_alias: str
    usage_id: int | None
    actual_rung: RungSelection
    ladder: tuple[RungSelection, ...]
    transition_reason: str
    outcome: str | None = None
    outcome_reason: str | None = None
