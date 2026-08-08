"""The findings grammar: types and batch parser.

Types are frozen carriers. Severity and status are closed sets; the store's
CHECK constraints backstop the enum, but the parser refuses unknown values
before any SQL runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class Status(StrEnum):
    OPEN = "open"
    PROMOTED = "promoted"
    RESOLVED = "resolved"
    REGRESSED = "regressed"


@dataclass(frozen=True)
class Finding:
    key: str
    category: str
    severity: Severity
    status: Status
    summary: str
    refs: list[str]
    notes: str | None
    source: str
    occurrences: int
    first_seen: str
    last_seen: str
    promoted_spec: str | None
    resolved_at: str | None
    resolution: str | None


@dataclass(frozen=True)
class FindingEvent:
    id: int | None
    finding_key: str
    seen_at: str
    source: str
    severity: Severity
    kind: str


class _Rejections:
    """Staged rejections: collect every defect, then raise one readable error."""

    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, rule: str, offender: str, problem: str) -> None:
        self.items.append(f"[{rule}] {offender}: {problem}")

    def raise_if_any(self) -> None:
        if self.items:
            raise ValueError("batch refused:\n" + "\n".join(self.items))


_REQUIRED_ENTRY_FIELDS = (
    "key",
    "category",
    "severity",
    "summary",
    "refs",
    "notes",
)


def parse_findings_batch(text: str) -> list[Finding]:
    """Parse the findings JSON grammar with staged rejection.

    The envelope must carry a top-level ``source`` string applied to every
    entry. Entries may not carry their own ``source`` or ``status`` override;
    the file is one provenance, and the store owns the status machine.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"batch is not valid JSON: {exc}") from exc

    rejections = _Rejections()

    if not isinstance(data, dict):
        raise ValueError("batch must be a JSON object")

    source = data.get("source")
    if not isinstance(source, str) or not source:
        rejections.add("missing_source", "<envelope>", "top-level 'source' is required")

    findings_list = data.get("findings")
    if not isinstance(findings_list, list):
        rejections.add("missing_findings", "<envelope>", "top-level 'findings' list is required")
        rejections.raise_if_any()

    seen_keys: set[str] = set()

    for idx, entry in enumerate(findings_list):
        if not isinstance(entry, dict):
            rejections.add("entry_type", f"findings[{idx}]", "entry must be an object")
            continue

        key = entry.get("key")
        label = key if isinstance(key, str) else f"findings[{idx}]"

        if "source" in entry:
            rejections.add(
                "source_override", label, "entries may not carry a per-entry 'source'"
            )
        if "status" in entry:
            rejections.add(
                "status_override", label, "entries may not carry a per-entry 'status'"
            )

        for field in _REQUIRED_ENTRY_FIELDS:
            if field not in entry:
                rejections.add("missing_field", label, f"missing '{field}'")

        raw_severity = entry.get("severity")
        try:
            Severity(raw_severity) if raw_severity is not None else None
        except ValueError:
            rejections.add("unknown_severity", label, f"severity {raw_severity!r} is not allowed")

        raw_key = entry.get("key")
        if isinstance(raw_key, str):
            if raw_key in seen_keys:
                rejections.add("duplicate_key", raw_key, "key appears more than once in batch")
            seen_keys.add(raw_key)

    rejections.raise_if_any()

    results: list[Finding] = []
    for entry in findings_list:
        results.append(
            Finding(
                key=entry["key"],
                category=entry["category"],
                severity=Severity(entry["severity"]),
                status=Status.OPEN,
                summary=entry["summary"],
                refs=list(entry["refs"]),
                notes=entry.get("notes"),
                source=source,
                occurrences=1,
                first_seen="",
                last_seen="",
                promoted_spec=None,
                resolved_at=None,
                resolution=None,
            )
        )

    return results
