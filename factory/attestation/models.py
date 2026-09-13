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


@dataclass(frozen=True)
class JudgeDelivery:
    delivery_ordinal: int
    status: str
    error: str | None = None
    response_id: str | None = None


@dataclass(frozen=True)
class JudgeEvaluationRecord:
    evaluation_id: str
    scoring_job_id: str
    scoring_call_ordinal: int
    invocation_id: str
    key_alias: str
    criteria_fingerprint: str
    tested_revision: str
    status: str
    model_alias: str
    route: str = "gateway"
    backend: str = "litellm-chat-completions"
    scenario_results: tuple[tuple[str, bool, str], ...] = ()
    feedback: str = ""
    parse_error: str | None = None
    deliveries: tuple[JudgeDelivery, ...] = ()
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    usage_status: str = "unknown"
    truncated_input: bool = False
    gates_shown: bool = False


@dataclass(frozen=True)
class GitFileChange:
    path: str
    status: str
    old_path: str | None = None
    binary: bool = False


@dataclass(frozen=True)
class AttemptGitEvidence:
    evidence_id: str
    epic_id: str
    node_id: str
    attempt: int
    dispatch: str
    base_commit: str
    attempted_commit: str
    verified_commit: str
    files: tuple[GitFileChange, ...]
    log_tail: str
    log_truncated: bool
    tests_executed: tuple[str, ...]
    coverage_status: str
