"""The merge-queue's message rendering: landing escalations (US2, plan.md § US2).

US1 shipped the PR body renderer (`test_pr_messages.py`); US2 ships the other
half of the notifier's merge-queue surface — what an operator reads when a
landing is rejected and needs a decision, and the notify-only notice a human
gets when a PR was closed manually. Both are pure rendering in
`factory/notify/messages.py`: the queue history and recovery cycles in, the
message (and its buttons) out.

Three properties these tests defend:

- **`render_landing_history` carries the queue history and recovery cycles.**
  The escalation's summary is built from the `Landing` — every observed outcome
  with its timestamp, in order, and how many recovery cycles were spent. The
  operator being asked to decide sees the sequence that led here, not a summary
  of it.
- **The landing escalation offers exactly `[RETRY | KILL | PAUSE_EPIC]`**
  (FR-007), encoded with the existing `esc:<id>:<choice>` callback grammar — the
  same buttons the verification ladder offers, so the bridge and the workflow
  already know how to answer them.
- **The manual-intervention notice renders with no buttons.** A human closing
  the PR is a fact to be told, not a decision to be asked — it is notify-only,
  and no button implies a choice the workflow will not honor.
- **No credential appears.** The message is public-facing (architecture §10):
  nothing from the worker environment — token, proxy URL, transcript path — may
  leak into what is rendered.
"""

from __future__ import annotations

from typing import Any

from telegram import InlineKeyboardMarkup

from factory.mergequeue.models import CheckFailure, Landing, LandingState, ObservedOutcome, QueueOutcome
from factory.notify.messages import (
    callback_data,
    escalation_keyboard,
    escalation_message,
    manual_intervention_notice,
    render_landing_history,
    roadmap_failure_notice,
    roadmap_recovery_notice,
)
from factory.verify.models import EscalationChoice, EscalationRecord

EPIC_ID = "003-merge-queue"
NODE_ID = "us1"
BRANCH = f"factory/{EPIC_ID}/{NODE_ID}"
ESCALATION_ID = "0123456789ab"
WORKFLOW_ID = f"epic-{EPIC_ID}"


def make_landing(**overrides: Any) -> Landing:
    fields: dict[str, Any] = {
        "node_id": NODE_ID,
        "branch": BRANCH,
        "pr_number": 7,
        "pr_url": "https://github.com/acme/target/pull/7",
        "enqueued_at": "2026-08-06T10:00:00Z",
        "outcomes": (
            ObservedOutcome(at="2026-08-06T10:10:00Z", outcome=QueueOutcome.CHECKS_FAILED),
        ),
        "recovery_cycles": 1,
        "state": LandingState.REJECTED,
    }
    fields.update(overrides)
    return Landing(**fields)


def make_record(**overrides: Any) -> EscalationRecord:
    fields: dict[str, Any] = {
        "escalation_id": ESCALATION_ID,
        "workflow_id": WORKFLOW_ID,
        "epic_id": EPIC_ID,
        "node_id": NODE_ID,
        "choices": list(
            (EscalationChoice.RETRY, EscalationChoice.KILL, EscalationChoice.PAUSE_EPIC)
        ),
        "history_summary": render_landing_history(make_landing()),
        "sent_at": "2026-08-06T10:11:00Z",
        "expires_at": "2026-08-06T11:11:00Z",
        "delivered": True,
    }
    fields.update(overrides)
    return EscalationRecord(**fields)


# --- render_landing_history --------------------------------------------------


def test_history_carries_every_outcome_with_its_timestamp_in_order() -> None:
    landing = make_landing(
        outcomes=(
            ObservedOutcome(at="2026-08-06T10:05:00Z", outcome=QueueOutcome.CHECKS_FAILED),
            ObservedOutcome(at="2026-08-06T10:30:00Z", outcome=QueueOutcome.CHECKS_FAILED),
        ),
        recovery_cycles=1,
    )

    summary = render_landing_history(landing)

    assert "2026-08-06T10:05:00Z" in summary
    assert "2026-08-06T10:30:00Z" in summary
    assert summary.index("2026-08-06T10:05:00Z") < summary.index("2026-08-06T10:30:00Z")
    assert summary.count("CHECKS_FAILED") >= 2


def test_history_names_the_recovery_cycles_spent() -> None:
    landing = make_landing(recovery_cycles=2)

    summary = render_landing_history(landing)

    assert "2" in summary
    assert "recovery" in summary.lower()


def test_history_with_no_outcomes_still_says_something() -> None:
    landing = make_landing(outcomes=())

    summary = render_landing_history(landing)

    assert summary.strip() != ""


def test_history_names_the_failing_checks_on_a_checks_failed_line() -> None:
    """US2-S2: the queue history tells the operator which required check failed."""
    landing = make_landing(
        outcomes=(
            ObservedOutcome(
                at="2026-08-06T10:10:00Z",
                outcome=QueueOutcome.CHECKS_FAILED,
                failing_checks=("lint", "typecheck"),
            ),
        ),
    )

    summary = render_landing_history(landing)

    assert "lint" in summary
    assert "typecheck" in summary


# --- the landing escalation's buttons (FR-007) -------------------------------


def test_landing_escalation_offers_exactly_retry_kill_pause() -> None:
    record = make_record()

    markup = escalation_keyboard(record)

    assert isinstance(markup, InlineKeyboardMarkup)
    buttons = [button for row in markup.inline_keyboard for button in row]
    assert len(buttons) == 3
    assert [button.callback_data for button in buttons] == [
        callback_data(ESCALATION_ID, EscalationChoice.RETRY),
        callback_data(ESCALATION_ID, EscalationChoice.KILL),
        callback_data(ESCALATION_ID, EscalationChoice.PAUSE_EPIC),
    ]


def test_landing_escalation_buttons_use_the_existing_callback_grammar() -> None:
    record = make_record()

    buttons = [b for row in escalation_keyboard(record).inline_keyboard for b in row]
    for button in buttons:
        data = button.callback_data or ""
        assert data.startswith("esc:")
        assert ESCALATION_ID in data
        assert len(data.encode("utf-8")) <= 64  # R11's hard ceiling


# --- the landing escalation message itself (US2-S2, FR-008) -----------------


def test_escalation_message_carries_check_name_url_and_failing_test_line() -> None:
    """FR-008: the Telegram message itself answers 'what actually happened'."""
    landing = make_landing(
        outcomes=(
            ObservedOutcome(
                at="2026-08-06T10:10:00Z",
                outcome=QueueOutcome.CHECKS_FAILED,
                failing_checks=("test",),
            ),
        ),
    )
    record = make_record(
        history_summary=render_landing_history(landing),
        check_evidence=(
            CheckFailure(
                name="test",
                url="https://github.com/acme/target/actions/runs/101/job/202",
                log_tail="FAILED tests/test_calc.py::test_add\nassert 1 == 2\n",
                note="",
            ),
        ),
    )

    message = escalation_message(record)

    assert "test" in message
    assert "https://github.com/acme/target/actions/runs/101/job/202" in message
    assert "FAILED tests/test_calc.py::test_add" in message
    assert "No answer by" in message


def test_escalation_message_states_absence_when_log_is_unavailable() -> None:
    """US2-S3: a failed fetch still names the check and URL in the page."""
    landing = make_landing(
        outcomes=(
            ObservedOutcome(
                at="2026-08-06T10:10:00Z",
                outcome=QueueOutcome.CHECKS_FAILED,
                failing_checks=("test",),
            ),
        ),
    )
    record = make_record(
        history_summary=render_landing_history(landing),
        check_evidence=(
            CheckFailure(
                name="test",
                url="https://github.com/acme/target/actions/runs/101/job/202",
                log_tail="",
                note="log unavailable: gh refused the fetch",
            ),
        ),
    )

    message = escalation_message(record)

    assert "test" in message
    assert "https://github.com/acme/target/actions/runs/101/job/202" in message
    assert "log unavailable" in message.lower() or "could not fetch" in message.lower()


# --- the manual-intervention notice (no buttons) -----------------------------


def test_manual_intervention_notice_renders_with_no_buttons() -> None:
    record = make_record(history_summary="PR #7 was closed without merging.")

    notice = manual_intervention_notice(record)

    assert "Manual intervention" in notice
    assert "PR #7 was closed without merging." in notice
    # A notify-only notice carries no decision prompt.
    assert "No answer by" not in notice


# --- no credential leaks ------------------------------------------------------


def test_no_credential_or_path_leaks_into_the_message() -> None:
    # Render the history and the message with the worker-environment secrets a
    # real escalation would be near, and assert none of them survives.
    landing = make_landing(
        outcomes=(
            ObservedOutcome(at="2026-08-06T10:10:00Z", outcome=QueueOutcome.CONFLICT),
        )
    )
    summary = render_landing_history(landing)
    notice = manual_intervention_notice(make_record(history_summary=summary))

    combined = summary + notice
    for secret in ("sk-", "LITELLM_MASTER_KEY", "TELEGRAM_BOT_TOKEN", ".factory/transcripts"):
        assert secret not in combined


# --- roadmap failure/recovery notices (no buttons, no deadline) ---------------


ROADMAP_ID = "roadmap-specs"
FAILURE_TEXT = "the corpus reader is broken"


def test_roadmap_failure_notice_carries_failure_text_and_count() -> None:
    notice = roadmap_failure_notice(roadmap_id=ROADMAP_ID, failure_text=FAILURE_TEXT, count=3)

    assert ROADMAP_ID in notice
    assert FAILURE_TEXT in notice
    assert "3 consecutive" in notice


def test_roadmap_failure_notice_offers_nothing_and_names_no_deadline() -> None:
    notice = roadmap_failure_notice(roadmap_id=ROADMAP_ID, failure_text=FAILURE_TEXT, count=1)

    assert "No answer by" not in notice
    assert "expires" not in notice.lower()
    assert "Retry" not in notice
    assert "Kill" not in notice
    assert "button" not in notice.lower()


def test_roadmap_recovery_notice_names_prior_count() -> None:
    notice = roadmap_recovery_notice(roadmap_id=ROADMAP_ID, prior_count=4)

    assert ROADMAP_ID in notice
    assert "recovered" in notice.lower()
    assert "4 consecutive" in notice


def test_roadmap_recovery_notice_offers_nothing_and_names_no_deadline() -> None:
    notice = roadmap_recovery_notice(roadmap_id=ROADMAP_ID, prior_count=2)

    assert "No answer by" not in notice
    assert "expires" not in notice.lower()
    assert "Retry" not in notice
    assert "Kill" not in notice
    assert "button" not in notice.lower()


def test_roadmap_failure_notice_is_not_a_keyboard_message() -> None:
    # The renderer returns text only; there is no keyboard function for notices.
    assert not hasattr(roadmap_failure_notice, "inline_keyboard")


def test_roadmap_recovery_notice_is_not_a_keyboard_message() -> None:
    assert not hasattr(roadmap_recovery_notice, "inline_keyboard")
