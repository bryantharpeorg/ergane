"""The findings grammar and batch parser.

Written before `factory/doctor/models.py` exists (T005 precedes T007): until the
module lands, tests here fail at import. Fixtures live under
`tests/fixtures/doctor/` with one directory per corpus case.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory.doctor.models import (
    Finding,
    Severity,
    Status,
    parse_findings_batch,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "doctor"


def test_seed_corpus_parses_to_27_findings_with_audit_source() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "specs"
        / "015-factory-doctor"
        / "seed-findings.json"
    )
    findings = parse_findings_batch(path.read_text())

    assert len(findings) == 27
    assert all(f.source == "audit-2026-08-07" for f in findings)
    assert {f.severity for f in findings} <= set(Severity)
    assert all(f.status == Status.OPEN for f in findings)
    assert all(f.occurrences == 1 for f in findings)


def test_valid_batch_parses_two_findings() -> None:
    text = (FIXTURES / "batch-valid" / "findings.json").read_text()
    findings = parse_findings_batch(text)

    assert len(findings) == 2
    assert findings[0].key == "ops/test-one"
    assert findings[0].source == "operator-test"
    assert findings[1].key == "ops/test-two"
    assert findings[1].severity == Severity.WARNING


def test_batch_without_comment_parses() -> None:
    text = (FIXTURES / "batch-no-comment" / "findings.json").read_text()
    findings = parse_findings_batch(text)

    assert len(findings) == 1
    assert findings[0].source == "operator-test"


def test_batch_missing_source_refuses() -> None:
    text = (FIXTURES / "batch-missing-source" / "findings.json").read_text()

    with pytest.raises(ValueError) as exc:
        parse_findings_batch(text)

    assert "source" in str(exc.value).lower()


def test_batch_missing_field_refuses_naming_entry() -> None:
    text = (FIXTURES / "batch-missing-field" / "findings.json").read_text()

    with pytest.raises(ValueError) as exc:
        parse_findings_batch(text)

    message = str(exc.value)
    assert "ops/test-two" in message
    assert "summary" in message.lower()


def test_batch_unknown_severity_refuses_naming_entry_and_rule() -> None:
    text = (FIXTURES / "batch-unknown-severity" / "findings.json").read_text()

    with pytest.raises(ValueError) as exc:
        parse_findings_batch(text)

    assert "ops/test-one" in str(exc.value)
    assert "severity" in str(exc.value).lower()


def test_batch_duplicate_key_refuses_naming_key() -> None:
    text = (FIXTURES / "batch-duplicate-key" / "findings.json").read_text()

    with pytest.raises(ValueError) as exc:
        parse_findings_batch(text)

    assert "ops/test-one" in str(exc.value)
    assert "duplicate" in str(exc.value).lower()


def test_batch_with_extra_per_entry_source_is_refused() -> None:
    text = json.dumps(
        {
            "source": "file-source",
            "findings": [
                {
                    "key": "ops/a",
                    "category": "ops",
                    "severity": "warning",
                    "summary": "s",
                    "refs": ["a:1"],
                    "notes": "n",
                    "source": "entry-source",
                }
            ],
        }
    )

    with pytest.raises(ValueError) as exc:
        parse_findings_batch(text)

    assert "source" in str(exc.value).lower()


def test_batch_unknown_status_is_refused() -> None:
    text = json.dumps(
        {
            "source": "file-source",
            "findings": [
                {
                    "key": "ops/a",
                    "category": "ops",
                    "severity": "warning",
                    "summary": "s",
                    "refs": ["a:1"],
                    "notes": "n",
                    "status": "closed",
                }
            ],
        }
    )

    with pytest.raises(ValueError) as exc:
        parse_findings_batch(text)

    assert "status" in str(exc.value).lower()
