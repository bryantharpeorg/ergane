"""US3 of epic 126 — a ref-conflict escalation names the ref that blocks it.

The message composer is pure: EscalationRecord in, string out. These tests
exercise that seam directly, because the operator's reading is what the story
verifies (FR-011, FR-012).
"""

from __future__ import annotations

from factory.notify.messages import escalation_message
from factory.verify.models import (
    EscalationChoice,
    EscalationRecord,
    RefConflictInfo,
)

EPIC_ID = "126-a-killed-node-leaves-no-ref-to-collide-with"
NODE = "us3"
REF = f"factory/{EPIC_ID}/{NODE}"
TIP = "deadbeef1234"
CLEARING_COMMAND = f"git push --delete origin {REF}"


def a_record(**overrides: object) -> EscalationRecord:
    fields: dict[str, object] = {
        "escalation_id": "0123456789ab",
        "workflow_id": "fedcba987654",
        "epic_id": EPIC_ID,
        "node_id": NODE,
        "choices": [EscalationChoice.RETRY, EscalationChoice.KILL],
        "history_summary": "attempt 3 PASS; landing push refused",
        "sent_at": "2026-09-02T09:00:00Z",
        "expires_at": "2026-09-02T10:00:00Z",
        "delivered": True,
    }
    fields.update(overrides)
    return EscalationRecord(**fields)  # type: ignore[arg-type]


def _ref_conflict_record(archived: bool) -> EscalationRecord:
    """A ref-conflict escalation with the facts the workflow would supply."""
    return a_record(
        history_summary=(
            "push of 'factory/126-a-killed-node-leaves-no-ref-to-collide-with/us3' "
            "to origin failed (repo /tmp/clone): "
            "! [rejected] factory/126-a-killed-node-leaves-no-ref-to-collide-with/us3 -> "
            "factory/126-a-killed-node-leaves-no-ref-to-collide-with/us3 (non-fast-forward)\n"
            "git said:\n"
            "hint: Updates were rejected because the tip of your current branch is behind\n"
            "error: failed to push some refs to '/tmp/clone.git'"
        ),
        ref_conflict=RefConflictInfo(
            ref=REF,
            tip=TIP,
            archived=archived,
            clearing_command=CLEARING_COMMAND,
        ),
    )


# --- T022 [US3] (spec US3-S1, FR-011) -----------------------------------------


def test_ref_conflict_escalation_names_ref_tip_and_archive_status() -> None:
    """The message names the full ref, the short tip, and whether it is archived."""
    message = escalation_message(_ref_conflict_record(archived=True))

    assert f"ref: {REF}" in message, message
    assert f"tip: {TIP}" in message, message
    assert "archived: yes" in message, message


# --- T023 [US3] (spec US3-S2, FR-011) -----------------------------------------


def test_archived_tip_carries_clearing_command() -> None:
    """When the tip is archived, the message carries the exact clearing command."""
    message = escalation_message(_ref_conflict_record(archived=True))

    assert CLEARING_COMMAND in message, message
    assert "--force" not in message, message


# --- T024 [US3] (spec US3-S3, FR-011) — the control --------------------------


def test_unarchived_tip_carries_no_clearing_command() -> None:
    """An unarchived tip is a data-loss risk: no command is offered."""
    message = escalation_message(_ref_conflict_record(archived=False))

    assert "archived: no" in message, message
    assert CLEARING_COMMAND not in message, message
    assert "not held by any archive ref" in message, message


# --- T025 [US3] (spec US3-S4, FR-012, trap 12) — the control ------------------


def test_unrelated_escalation_is_unchanged() -> None:
    """Escalations whose terminal cause is not a ref conflict stay byte-identical."""
    record = a_record(
        history_summary="attempt 3 FAIL (merge-queue checks)",
        check_evidence=(),
    )

    message = escalation_message(record)

    expected = (
        "⚠️ Verification escalation\n"
        f"epic: {EPIC_ID}\n"
        f"node: {NODE}\n\n"
        "attempt 3 FAIL (merge-queue checks)\n\n"
        "What each button does:\n"
        "RETRY (🔁 Retry the node) — node: one more attempt, on the tree this one left behind. "
        "epic: unchanged — it keeps dispatching.\n"
        "KILL (🛑 Kill the node) — node: ends KILLED, its branch preserved. "
        "epic: keeps dispatching, but every node waiting on this one is locked out and ends "
        "KILLED with it, undispatched.\n\n"
        "No answer by 2026-09-02T10:00:00Z applies the default: KILL the node."
    )
    assert message == expected, message
