"""US3: the escape hatch counts itself, and the target is zero.

Every store in this file is created under `tmp_path`; the suite never touches the
operator's live `.factory/` (plan.md trap 7, FR-009).
"""

from __future__ import annotations

import pytest
from pathlib import Path

from factory.verify.store import connect as verify_connect


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "verification.db"


def test_external_completion_count_is_zero_for_an_empty_corpus(
    db_path: Path,
) -> None:
    """A corpus that has never used the hatch reports 0, explicitly measured."""
    conn = verify_connect(db_path)
    try:
        # Import inside the test to ensure we are testing the implemented surface.
        from factory.verify.store import external_completion_count

        result = external_completion_count(conn)
    finally:
        conn.close()

    assert result.total == 0
    assert result.by_spec == {}
    assert result.measured is True
    assert result.target == 0


def test_external_completion_count_increments_once_per_accepted_completion(
    db_path: Path,
) -> None:
    """Each accepted external completion increments the durable count."""
    conn = verify_connect(db_path)
    try:
        from factory.verify.store import (
            record_external_completion_signal,
            external_completion_count,
        )

        record_external_completion_signal(
            conn,
            epic_id="epic-spec-a",
            node_id="us1",
            branch="factory/spec-a/us1",
            provenance="operator:manual-2026-08-17",
            accepted=True,
            reason=None,
            recorded_at="2026-08-17T10:00:00Z",
        )
        record_external_completion_signal(
            conn,
            epic_id="epic-spec-b",
            node_id="us1",
            branch="factory/spec-b/us1",
            provenance="operator:manual-2026-08-17",
            accepted=True,
            reason=None,
            recorded_at="2026-08-17T10:05:00Z",
        )

        result = external_completion_count(conn)
    finally:
        conn.close()

    assert result.total == 2
    assert result.by_spec == {
        "epic-spec-a": 1,
        "epic-spec-b": 1,
    }


def test_external_completion_count_is_idempotent_per_completion(
    db_path: Path,
) -> None:
    """Recording the same accepted completion twice counts once (trap 5)."""
    conn = verify_connect(db_path)
    try:
        from factory.verify.store import (
            record_external_completion_signal,
            external_completion_count,
        )

        for _ in range(2):
            record_external_completion_signal(
                conn,
                epic_id="epic-spec-a",
                node_id="us1",
                branch="factory/spec-a/us1",
                provenance="operator:manual-2026-08-17",
                accepted=True,
                reason=None,
                recorded_at="2026-08-17T10:00:00Z",
            )

        result = external_completion_count(conn)
    finally:
        conn.close()

    assert result.total == 1
    assert result.by_spec == {"epic-spec-a": 1}


def test_external_completion_count_rejected_signals_do_not_count(
    db_path: Path,
) -> None:
    """Refused completions do not increment the count."""
    conn = verify_connect(db_path)
    try:
        from factory.verify.store import (
            record_external_completion_signal,
            external_completion_count,
        )

        record_external_completion_signal(
            conn,
            epic_id="epic-spec-a",
            node_id="us1",
            branch="factory/spec-a/us1",
            provenance="operator:manual-2026-08-17",
            accepted=False,
            reason="node already terminal",
            recorded_at="2026-08-17T10:00:00Z",
        )
        record_external_completion_signal(
            conn,
            epic_id="epic-spec-a",
            node_id="us1",
            branch="factory/spec-a/us1",
            provenance="operator:manual-2026-08-17",
            accepted=True,
            reason=None,
            recorded_at="2026-08-17T10:01:00Z",
        )

        result = external_completion_count(conn)
    finally:
        conn.close()

    assert result.total == 1
    assert result.by_spec == {"epic-spec-a": 1}


def test_external_completion_count_breaks_down_by_spec(
    db_path: Path,
) -> None:
    """The read surface reports total and per-spec breakdown."""
    conn = verify_connect(db_path)
    try:
        from factory.verify.store import (
            record_external_completion_signal,
            external_completion_count,
        )

        record_external_completion_signal(
            conn,
            epic_id="epic-spec-a",
            node_id="us1",
            branch="factory/spec-a/us1",
            provenance="operator:manual",
            accepted=True,
            reason=None,
            recorded_at="2026-08-17T10:00:00Z",
        )
        record_external_completion_signal(
            conn,
            epic_id="epic-spec-a",
            node_id="us2",
            branch="factory/spec-a/us2",
            provenance="operator:manual",
            accepted=True,
            reason=None,
            recorded_at="2026-08-17T10:01:00Z",
        )
        record_external_completion_signal(
            conn,
            epic_id="epic-spec-b",
            node_id="us1",
            branch="factory/spec-b/us1",
            provenance="operator:manual",
            accepted=True,
            reason=None,
            recorded_at="2026-08-17T10:02:00Z",
        )

        result = external_completion_count(conn)
    finally:
        conn.close()

    assert result.total == 3
    assert result.by_spec == {
        "epic-spec-a": 2,
        "epic-spec-b": 1,
    }
