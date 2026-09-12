"""Normalize Codex CLI token evidence for the current attempt."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from factory.usage.models import CodexUsageEvidence, KeyLease


_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
)


def normalize_codex_usage(evidence: Any) -> CodexUsageEvidence:
    """Map a decoder's usage object into typed, honest CLI evidence."""

    usage = getattr(evidence, "usage", None)
    fields = {
        field: getattr(usage, field, None) if usage is not None else None
        for field in _FIELDS
    }
    invalid_fields = tuple(getattr(usage, "invalid_fields", ()) or ())
    reason = getattr(usage, "reason", None)

    if usage is None:
        reasons = tuple(getattr(evidence, "reasons", ()) or ())
        if any(getattr(reason, "code", None) == "duplicate-terminal" for reason in reasons):
            reason = "duplicate-terminal"
        elif getattr(evidence, "turn_outcome", None) is not None and evidence.turn_outcome.value == "failed":
            reason = "turn-failed"
        elif reasons:
            reason = reasons[0].code

    measured = any(value is not None for value in fields.values())
    complete = bool(
        usage is not None
        and all(value is not None for value in fields.values())
        and not invalid_fields
        and getattr(evidence, "completeness", None) is not None
        and evidence.completeness.value == "complete"
    )
    if usage is not None and not complete:
        reasons = tuple(getattr(evidence, "reasons", ()) or ())
        if invalid_fields:
            reason = getattr(usage, "reason", None) or "malformed-usage"
        elif reasons:
            reason = reasons[0].code
        else:
            reason = "partial-usage"

    return CodexUsageEvidence(
        **fields,
        source="codex_cli",
        complete=complete,
        invalid_fields=invalid_fields,
        reason=reason,
    )


def read_codex_usage_evidence(
    factory_root: Path | str, lease: KeyLease
) -> CodexUsageEvidence | None:
    """Read this attempt's own JSONL archive, never a rollout directory."""

    from factory.workgraph.adapter import CODEX_EVENTS_NAME, decode_codex_events, transcript_dir

    archive = transcript_dir(factory_root, lease.epic_id, lease.node_id, lease.attempt)
    path = archive / CODEX_EVENTS_NAME
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    return normalize_codex_usage(decode_codex_events(raw.splitlines(keepends=True)))
