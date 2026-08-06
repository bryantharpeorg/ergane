"""What an operator sees when the ladder gives up, and what one button press does.

This is the seam between a workflow that has run out of ideas and a human with a
phone. Two modules meet here: `factory/notify/messages.py` renders the escalation
(pure — text and an inline keyboard, no I/O), and `factory/notify/service.py`
turns a button press back into a Temporal signal. Neither is tested against the
real Bot API; the update, the Temporal client and the store are fakes, and the
one thing that is real is the evidence store, because the store is what decides
who wins a race.

Six decisions are pinned here:

- **`callback_data` carries the escalation id, never the workflow id** (R11).
  Telegram caps callback payloads at 64 bytes, and workflow ids are arbitrarily
  long — encoding one would work in tests and fail on a real epic. `esc:<12-hex>:
  <CHOICE>` is 27 bytes at its longest, and the id is a store key rather than
  anything meaningful on its own.
- **Parsing validates shape, not authority.** `parse_callback_data` accepts any
  choice spelling that fits the grammar and hands back a raw string; whether the
  choice was ever *offered* is a question about the stored row, which only the
  bridge can answer. A press for `PAUSE_EPIC` on an escalation that offered
  RETRY and KILL is refused, not crashed on.
- **The message carries the full failure history (SC-005), clipped only by
  Telegram.** `render_history` walks every attempt in order and quotes gate
  output and judge feedback verbatim; oversized evidence keeps its *tail*,
  because the last lines are the failure and the first lines are the banner. The
  store keeps the summary in full — `escalation_message` is the only place a
  4096-character cap applies, and when it bites it says so.
- **State is checked before the signal, and the store decides after it.** The
  bridge reads the row to answer well ("already resolved as KILL" beats a silent
  no-op), then signals, then makes the guarded transition. The read can go stale
  between those steps; the guarded UPDATE cannot, so a press that loses the race
  to the hour expiring leaves EXPIRED standing and is told so.
- **A signal that never landed leaves the row pending.** If Temporal is
  unreachable the press is not recorded — the operator can press again, and if
  nobody does, the workflow's own timer applies the fail-safe kill. Resolving a
  row we failed to signal would strand the workflow for the full hour and then
  kill it anyway, which is the same outcome reached by pretending to have acted.
- **The bridge holds no state and does not own the clock.** A restarted bridge
  answers exactly as the one that resolved the press would have, and a row that
  is past `expires_at` but still pending is honored — the workflow's timer is the
  authority on expiry (R12), and a bridge with a skewed clock must not refuse a
  press the workflow is still waiting for.

Written before `factory/notify/messages.py` and `factory/notify/service.py` exist
(T024 precedes T027): until they land, every test here fails at import.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Sequence

import pytest
from telegram import InlineKeyboardMarkup

from factory.notify.messages import (
    CALLBACK_DATA_LIMIT,
    CALLBACK_PREFIX,
    EVIDENCE_TAIL_LINES,
    MESSAGE_LIMIT,
    CallbackPress,
    callback_data,
    escalation_keyboard,
    escalation_message,
    parse_callback_data,
    render_history,
    resolution_notice,
)
from factory.notify.service import SIGNAL_NAME, BridgeOutcome, CallbackBridge
from factory.verify.models import (
    EscalationChoice,
    EscalationRecord,
    GateResult,
    GateStatus,
    JudgeOutcome,
    JudgeScenarioFinding,
    JudgeVerdict,
    OutputCheck,
    OverallVerdict,
    VerificationForm,
    VerificationResult,
)
from factory.verify.store import (
    EXPIRED,
    connect,
    expire_escalation,
    get_escalation,
    insert_escalation,
)

#: The id every test presses on unless it is about ids: 12 lowercase hex, the
#: shape `secrets.token_hex(6)` produces.
ESCALATION_ID = "0123456789ab"

#: Deliberately longer than 64 bytes on its own — nothing derived from it may
#: reach `callback_data` (R11).
WORKFLOW_ID = "ergane-epic-002-verification-gating-interpreter-run-0000000001"

ALL_CHOICES = [
    EscalationChoice.RETRY,
    EscalationChoice.KILL,
    EscalationChoice.PAUSE_EPIC,
]

#: `[... N lines truncated ...]`, the same marker the judge's diff truncation
#: uses — one spelling for "evidence was elided here" across the component.
TRUNCATION_MARKER_RE = re.compile(r"\[\.\.\. (\d+) lines truncated \.\.\.\]")

#: `2026-08-04T12:34:56Z` — what `_now_iso` writes everywhere else (001).
ISO_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

RESOLVED_AT = "2026-08-04T12:34:56Z"


# --- evidence builders ------------------------------------------------------


def make_gate(**overrides: Any) -> GateResult:
    fields: dict[str, Any] = {
        "name": "test",
        "command": "uv run pytest -q",
        "status": GateStatus.PASS,
        "exit_code": 0,
        "duration_s": 12.5,
        "output_tail": "42 passed in 12.5s",
    }
    fields.update(overrides)
    return GateResult(**fields)


def make_judge(**overrides: Any) -> JudgeVerdict:
    fields: dict[str, Any] = {
        "outcome": JudgeOutcome.RETRY,
        "findings": [
            JudgeScenarioFinding(
                scenario="US1-S1", passed=False, reasoning="no ledger row asserted"
            )
        ],
        "feedback": "US1-S1 fails: the test never asserts a ledger row exists",
        "judge_attempt": 1,
        "truncated_input": False,
        "model_alias": "judge",
    }
    fields.update(overrides)
    return JudgeVerdict(**fields)


def make_result(**overrides: Any) -> VerificationResult:
    """One failing attempt — escalations only ever summarize these."""
    fields: dict[str, Any] = {
        "epic_id": "epic-7",
        "node_id": "node-3",
        "attempt": 1,
        "form": VerificationForm.PHASE,
        "gate_results": [make_gate()],
        "output_check": OutputCheck(
            write_scope="worktree",
            has_diff=True,
            expected_artifacts=[],
            artifacts_present=None,
            passed=True,
        ),
        "judge": None,
        "verdict": OverallVerdict.FAIL,
        "judge_unavailable": False,
        "criteria_drift": False,
        "criteria_sha256": "a" * 64,
        "spec_ref": "002-verification-gating/US1",
        "started_at": "2026-08-04T10:00:00Z",
        "finished_at": "2026-08-04T10:03:00Z",
    }
    fields.update(overrides)
    return VerificationResult(**fields)


def make_escalation(**overrides: Any) -> EscalationRecord:
    fields: dict[str, Any] = {
        "escalation_id": ESCALATION_ID,
        "workflow_id": WORKFLOW_ID,
        "epic_id": "epic-7",
        "node_id": "node-3",
        "choices": list(ALL_CHOICES),
        "history_summary": "attempt 1: gate test FAIL (exit 1)",
        "sent_at": "2026-08-04T11:00:00Z",
        "expires_at": "2026-08-04T12:00:00Z",
        "delivered": True,
    }
    fields.update(overrides)
    return EscalationRecord(**fields)


def long_evidence(lines: int = 400) -> tuple[str, str, str]:
    """A gate tail at roughly the 32 KiB cap, plus its first and last lines."""
    first = "FIRST-LINE-SENTINEL: collecting tests"
    last = "LAST-LINE-SENTINEL: AssertionError at the end of the run"
    filler = [f"filler {index:03d} " + "x" * 64 for index in range(1, lines - 1)]
    return "\n".join([first, *filler, last]), first, last


# --- fakes ------------------------------------------------------------------


class _Unset:
    """Sentinel: `temporalio` uses one to tell "no arg" from "arg is None"."""


_UNSET = _Unset()


@dataclass(frozen=True)
class SentSignal:
    """One signal the bridge sent, as the workflow would receive it."""

    workflow_id: str
    name: str
    args: list[Any]


class FakeWorkflowHandle:
    def __init__(self, client: FakeTemporalClient, workflow_id: str) -> None:
        self._client = client
        self._workflow_id = workflow_id

    async def signal(
        self,
        name: str,
        arg: Any = _UNSET,
        *,
        args: Sequence[Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Accept either of `temporalio`'s call shapes; record what was sent."""
        payload = list(args) if args is not None else ([] if arg is _UNSET else [arg])
        self._client.record(SentSignal(self._workflow_id, name, payload))


class FakeTemporalClient:
    """Stand-in for `temporalio.client.Client` — records signals, never connects."""

    def __init__(self) -> None:
        self.signals: list[SentSignal] = []
        #: Fires with the signal *before* it is recorded, so a test can raise
        #: (Temporal unreachable) or move the store underneath the bridge.
        self.on_signal: Any = None

    def get_workflow_handle(self, workflow_id: str, **kwargs: Any) -> FakeWorkflowHandle:
        return FakeWorkflowHandle(self, workflow_id)

    def record(self, signal: SentSignal) -> None:
        if self.on_signal is not None:
            self.on_signal(signal)
        self.signals.append(signal)


@dataclass
class RecordedCall:
    text: str | None
    kwargs: dict[str, Any] = field(default_factory=dict)


class FakeCallbackQuery:
    def __init__(self, data: str) -> None:
        self.data = data
        self.answers: list[RecordedCall] = []
        self.edits: list[RecordedCall] = []

    async def answer(self, text: str | None = None, **kwargs: Any) -> None:
        self.answers.append(RecordedCall(text, kwargs))

    async def edit_message_text(self, text: str | None = None, **kwargs: Any) -> None:
        self.edits.append(RecordedCall(text, kwargs))


class FakeUpdate:
    """Only the attribute a `CallbackQueryHandler` callback reads."""

    def __init__(self, data: str) -> None:
        self.callback_query = FakeCallbackQuery(data)


def press(
    choice: EscalationChoice | str, escalation_id: str = ESCALATION_ID
) -> FakeUpdate:
    """A button press for `choice`, encoded the way the keyboard encodes it."""
    value = choice.value if isinstance(choice, EscalationChoice) else choice
    return FakeUpdate(f"{CALLBACK_PREFIX}:{escalation_id}:{value}")


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / ".factory" / "verification.db"


@pytest.fixture
def store(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def client() -> FakeTemporalClient:
    return FakeTemporalClient()


@pytest.fixture
def bridge(db_path: Path, client: FakeTemporalClient) -> CallbackBridge:
    """The bridge under test, with a frozen clock so timestamps are assertable."""
    return CallbackBridge(db_path=db_path, client=client, now=lambda: RESOLVED_AT)


def escalation_row(conn: sqlite3.Connection, escalation_id: str) -> dict[str, Any]:
    cursor = conn.execute(
        "SELECT * FROM escalations WHERE escalation_id = ?", (escalation_id,)
    )
    row = cursor.fetchone()
    assert row is not None, f"no escalation row for {escalation_id!r}"
    return {column[0]: value for column, value in zip(cursor.description, row)}


# --- callback_data: the 64-byte contract ------------------------------------


@pytest.mark.parametrize("choice", ALL_CHOICES)
def test_callback_data_round_trips_every_choice(choice: EscalationChoice) -> None:
    data = callback_data(ESCALATION_ID, choice)

    assert data == f"{CALLBACK_PREFIX}:{ESCALATION_ID}:{choice.value}"
    assert parse_callback_data(data) == CallbackPress(ESCALATION_ID, choice.value)


@pytest.mark.parametrize("choice", ALL_CHOICES)
def test_callback_data_fits_telegrams_sixty_four_byte_limit(
    choice: EscalationChoice,
) -> None:
    # The Bot API rejects a longer payload outright, which would make the button
    # undeliverable rather than merely ugly.
    assert CALLBACK_DATA_LIMIT == 64
    assert len(callback_data(ESCALATION_ID, choice).encode("utf-8")) <= (
        CALLBACK_DATA_LIMIT
    )


@pytest.mark.parametrize("choice", ALL_CHOICES)
def test_callback_data_never_carries_the_workflow_id(choice: EscalationChoice) -> None:
    # R11: routing lives in the store row, keyed by the id. A workflow id in the
    # payload is exactly the design the 64-byte limit rules out.
    record = make_escalation()
    data = callback_data(record.escalation_id, choice)

    assert record.workflow_id not in data
    assert record.epic_id not in data


@pytest.mark.parametrize(
    "escalation_id",
    [
        "",
        "0123456789a",  # 11
        "0123456789abc",  # 13
        "0123456789ag",  # not hex
        "0123456789AB",  # the store holds one spelling; uppercase is not it
        "0123 456789a",
    ],
)
def test_an_id_that_is_not_twelve_lowercase_hex_is_refused(escalation_id: str) -> None:
    # The ≤64-byte guarantee is by construction, so construction is where a
    # malformed id has to fail — not at send time, against Telegram.
    with pytest.raises(ValueError):
        callback_data(escalation_id, EscalationChoice.RETRY)


@pytest.mark.parametrize(
    "data",
    [
        "",
        "esc",
        f"esc:{ESCALATION_ID}",
        f"esc:{ESCALATION_ID}:RETRY:extra",
        f"other:{ESCALATION_ID}:RETRY",
        "esc:nothex000000:RETRY",
        "esc::RETRY",
    ],
)
def test_parsing_refuses_callback_data_this_bridge_did_not_write(data: str) -> None:
    # A button from another feature — or another deployment — must be answered,
    # not raised on: the bridge is one long-lived process.
    assert parse_callback_data(data) is None


def test_a_choice_nobody_offered_still_parses() -> None:
    # Shape is all parsing knows. Whether `NUKE` was on the keyboard is a fact
    # about the stored row, and only the bridge can look that up.
    assert parse_callback_data(f"esc:{ESCALATION_ID}:NUKE") == CallbackPress(
        ESCALATION_ID, "NUKE"
    )


# --- the inline keyboard ----------------------------------------------------


def test_the_keyboard_offers_one_button_per_choice_in_order() -> None:
    record = make_escalation()

    markup = escalation_keyboard(record)

    assert isinstance(markup, InlineKeyboardMarkup)
    buttons = [button for row in markup.inline_keyboard for button in row]
    assert [button.callback_data for button in buttons] == [
        callback_data(record.escalation_id, choice) for choice in record.choices
    ]
    labels = [button.text for button in buttons]
    assert all(labels) and len(set(labels)) == len(labels)


def test_a_narrowed_choice_set_renders_only_what_was_offered() -> None:
    # FR-008 maps buttons 1:1 to choices; a button the workflow will refuse to
    # honor is a button that should never have been rendered.
    record = make_escalation(choices=[EscalationChoice.RETRY, EscalationChoice.KILL])

    markup = escalation_keyboard(record)

    buttons = [button for row in markup.inline_keyboard for button in row]
    assert len(buttons) == 2
    assert not any(
        EscalationChoice.PAUSE_EPIC.value in (button.callback_data or "")
        for button in buttons
    )


# --- the failure history (SC-005) -------------------------------------------


def test_the_history_carries_every_attempt_in_the_order_it_happened() -> None:
    results = [
        make_result(attempt=1),
        make_result(attempt=2, gate_results=[make_gate(name="lint")]),
        make_result(attempt=3, judge=make_judge()),
    ]

    summary = render_history(results)

    positions = [summary.find(f"{attempt}") for attempt in (1, 2, 3)]
    assert all(position >= 0 for position in positions)
    assert "attempt" in summary.lower()
    # "Full failure history" is every attempt, not the last one (SC-005).
    assert summary.count("ttempt") >= 3


def test_the_history_quotes_gate_evidence_verbatim() -> None:
    gate = make_gate(
        name="test",
        command="uv run pytest -q",
        status=GateStatus.FAIL,
        exit_code=1,
        output_tail="E   AssertionError: expected a ledger row, found none",
    )

    summary = render_history([make_result(gate_results=[gate])])

    assert gate.name in summary
    assert GateStatus.FAIL.value in summary
    assert "1" in summary  # the exit code the operator will ask about first
    assert gate.output_tail in summary


def test_the_history_quotes_the_judges_feedback_verbatim() -> None:
    judge = make_judge()

    summary = render_history([make_result(judge=judge)])

    assert JudgeOutcome.RETRY.value in summary
    assert judge.feedback in summary


def test_the_history_names_an_empty_diff_for_what_it_is() -> None:
    # FR-004's failure reads as "everything passed" in gate output alone; the
    # operator needs to be told the node produced nothing.
    empty = OutputCheck(
        write_scope="worktree",
        has_diff=False,
        expected_artifacts=[],
        artifacts_present=None,
        passed=False,
    )

    summary = render_history([make_result(output_check=empty)]).lower()

    assert "diff" in summary
    assert "worktree" in summary


def test_oversized_evidence_keeps_its_tail_and_says_what_it_dropped() -> None:
    # The last lines are the failure; the first lines are the banner. Head-only
    # clipping would drop precisely the reason the operator was paged.
    tail, first_line, last_line = long_evidence(lines=400)

    summary = render_history(
        [make_result(gate_results=[make_gate(status=GateStatus.FAIL, output_tail=tail)])]
    )

    assert last_line in summary
    assert first_line not in summary
    marker = TRUNCATION_MARKER_RE.search(summary)
    assert marker is not None
    assert int(marker.group(1)) == 400 - EVIDENCE_TAIL_LINES


def test_a_history_with_no_attempts_still_says_something() -> None:
    # An escalation whose message body is empty is worse than one that admits it
    # has nothing recorded — the operator would read blank as "no failures".
    summary = render_history([])

    assert summary.strip()


# --- the escalation message -------------------------------------------------


def test_the_message_carries_the_history_and_names_the_node() -> None:
    record = make_escalation(
        history_summary="attempt 1: gate test FAIL (exit 1)\n  E AssertionError"
    )

    text = escalation_message(record)

    assert record.history_summary in text
    assert record.epic_id in text
    assert record.node_id in text


def test_the_message_states_the_default_and_when_it_applies() -> None:
    # FR-008: silence is not neutral — it kills the node in an hour, and the
    # message is the only place the operator learns that.
    record = make_escalation()

    text = escalation_message(record).lower()

    assert "kill" in text
    assert record.expires_at.lower() in text


def test_the_message_stays_inside_telegrams_length_limit() -> None:
    # The store keeps the summary in full; the message is what Telegram will
    # accept, and a send rejected for length is an escalation nobody sees.
    record = make_escalation(history_summary="\n".join(["evidence line"] * 2000))

    text = escalation_message(record)

    assert MESSAGE_LIMIT == 4096
    assert len(text) <= MESSAGE_LIMIT
    assert record.node_id in text  # the header survives the clip
    assert "truncated" in text.lower()


@pytest.mark.parametrize("resolution", [*ALL_CHOICES, EXPIRED])
def test_the_resolution_notice_names_what_happened(
    resolution: EscalationChoice | str,
) -> None:
    record = make_escalation()

    notice = resolution_notice(record, resolution)

    value = (
        resolution.value if isinstance(resolution, EscalationChoice) else resolution
    )
    assert value in notice
    assert record.node_id in notice


def test_an_expired_notice_says_the_default_was_applied() -> None:
    notice = resolution_notice(make_escalation(), EXPIRED).lower()

    assert "kill" in notice


# --- the bridge: a press that lands -----------------------------------------


@pytest.mark.parametrize("choice", ALL_CHOICES)
async def test_a_press_signals_the_workflow_and_resolves_the_row(
    bridge: CallbackBridge,
    client: FakeTemporalClient,
    store: sqlite3.Connection,
    choice: EscalationChoice,
) -> None:
    insert_escalation(store, make_escalation())
    update = press(choice)

    outcome = await bridge.handle(update)

    assert outcome == BridgeOutcome.RESOLVED
    assert client.signals == [
        SentSignal(WORKFLOW_ID, SIGNAL_NAME, [ESCALATION_ID, choice.value])
    ]
    assert SIGNAL_NAME == "escalation_resolved"

    row = escalation_row(store, ESCALATION_ID)
    assert row["resolution"] == choice.value
    assert row["resolved_at"] == RESOLVED_AT
    assert row["resolved_via"] == "BUTTON"


async def test_a_press_is_answered_and_the_buttons_are_taken_away(
    bridge: CallbackBridge, store: sqlite3.Connection
) -> None:
    # Telegram spins the button until the callback is answered, and a keyboard
    # left in place invites a second press on a decision already made.
    insert_escalation(store, make_escalation())
    update = press(EscalationChoice.RETRY)

    await bridge.handle(update)

    query = update.callback_query
    assert len(query.answers) == 1
    assert query.answers[0].text
    assert len(query.edits) == 1
    assert EscalationChoice.RETRY.value in (query.edits[0].text or "")
    assert query.edits[0].kwargs.get("reply_markup") is None


async def test_the_workflow_is_signalled_before_the_row_is_resolved(
    bridge: CallbackBridge, client: FakeTemporalClient, store: sqlite3.Connection
) -> None:
    # The guarded UPDATE is the authority on who won, so it goes last: a row
    # marked resolved before the signal is sent is a workflow that waits out the
    # hour on a decision the store says was already made.
    insert_escalation(store, make_escalation())
    seen: list[Any] = []
    client.on_signal = lambda signal: seen.append(
        get_escalation(store, ESCALATION_ID).resolution
    )

    await bridge.handle(press(EscalationChoice.KILL))

    assert seen == [None]
    assert escalation_row(store, ESCALATION_ID)["resolution"] == (
        EscalationChoice.KILL.value
    )


async def test_the_default_clock_stamps_iso_8601_utc(
    db_path: Path, client: FakeTemporalClient, store: sqlite3.Connection
) -> None:
    insert_escalation(store, make_escalation())

    await CallbackBridge(db_path=db_path, client=client).handle(
        press(EscalationChoice.RETRY)
    )

    assert ISO_UTC_RE.match(escalation_row(store, ESCALATION_ID)["resolved_at"])


async def test_a_pending_escalation_past_its_hour_is_still_honoured(
    bridge: CallbackBridge, client: FakeTemporalClient, store: sqlite3.Connection
) -> None:
    # R12 puts the timer in the workflow. If the row is still pending, the
    # workflow is still waiting — a bridge second-guessing that with its own
    # clock would silently drop presses under clock skew.
    insert_escalation(store, make_escalation(expires_at="2020-01-01T00:00:00Z"))

    outcome = await bridge.handle(press(EscalationChoice.RETRY))

    assert outcome == BridgeOutcome.RESOLVED
    assert len(client.signals) == 1


# --- the bridge: presses that must not signal -------------------------------


async def test_callback_data_from_elsewhere_is_answered_and_dropped(
    bridge: CallbackBridge, client: FakeTemporalClient, store: sqlite3.Connection
) -> None:
    insert_escalation(store, make_escalation())
    update = FakeUpdate("someoneelse:whatever")

    outcome = await bridge.handle(update)

    assert outcome == BridgeOutcome.MALFORMED
    assert client.signals == []
    assert len(update.callback_query.answers) == 1
    assert update.callback_query.edits == []
    assert escalation_row(store, ESCALATION_ID)["resolution"] is None


async def test_a_press_on_an_unknown_escalation_is_answered_and_dropped(
    bridge: CallbackBridge, client: FakeTemporalClient, store: sqlite3.Connection
) -> None:
    # A button from before the store was rebuilt, or from a deployment whose
    # database is gone. Answered with a notice, never a crashed poll loop.
    insert_escalation(store, make_escalation())
    update = press(EscalationChoice.RETRY, escalation_id="ffffffffffff")

    outcome = await bridge.handle(update)

    assert outcome == BridgeOutcome.UNKNOWN
    assert client.signals == []
    assert update.callback_query.answers[0].text
    assert escalation_row(store, ESCALATION_ID)["resolution"] is None


@pytest.mark.parametrize("choice", [EscalationChoice.PAUSE_EPIC.value, "NUKE"])
async def test_a_choice_that_was_never_offered_is_refused(
    bridge: CallbackBridge,
    client: FakeTemporalClient,
    store: sqlite3.Connection,
    choice: str,
) -> None:
    # The row's `choices` are the offer; anything else is a forged or stale
    # payload, and signalling it would hand the workflow a decision it never
    # asked for.
    insert_escalation(
        store,
        make_escalation(choices=[EscalationChoice.RETRY, EscalationChoice.KILL]),
    )
    update = press(choice)

    outcome = await bridge.handle(update)

    assert outcome == BridgeOutcome.INVALID_CHOICE
    assert client.signals == []
    assert len(update.callback_query.answers) == 1
    assert escalation_row(store, ESCALATION_ID)["resolution"] is None


async def test_a_press_after_the_hour_expired_changes_nothing(
    bridge: CallbackBridge, client: FakeTemporalClient, store: sqlite3.Connection
) -> None:
    insert_escalation(store, make_escalation())
    expire_escalation(store, ESCALATION_ID, resolved_at="2026-08-04T12:00:00Z")

    outcome = await bridge.handle(press(EscalationChoice.RETRY))

    assert outcome == BridgeOutcome.EXPIRED
    assert client.signals == []
    row = escalation_row(store, ESCALATION_ID)
    assert row["resolution"] == EXPIRED
    assert row["resolved_at"] == "2026-08-04T12:00:00Z"
    assert row["resolved_via"] == "TIMEOUT"


async def test_a_second_press_is_answered_without_a_second_signal(
    bridge: CallbackBridge, client: FakeTemporalClient, store: sqlite3.Connection
) -> None:
    # A double tap, or Telegram redelivering the callback. The first decision
    # stands and the workflow hears about it exactly once.
    insert_escalation(store, make_escalation())
    await bridge.handle(press(EscalationChoice.RETRY))

    update = press(EscalationChoice.KILL)
    outcome = await bridge.handle(update)

    assert outcome == BridgeOutcome.ALREADY_RESOLVED
    assert len(client.signals) == 1
    assert client.signals[0].args == [ESCALATION_ID, EscalationChoice.RETRY.value]
    assert update.callback_query.answers[0].text
    row = escalation_row(store, ESCALATION_ID)
    assert row["resolution"] == EscalationChoice.RETRY.value
    assert row["resolved_at"] == RESOLVED_AT


async def test_a_restarted_bridge_refuses_a_press_it_never_saw(
    db_path: Path, client: FakeTemporalClient, store: sqlite3.Connection
) -> None:
    # The service holds no state outside the store (R11), so a restart mid-hour
    # must answer exactly as the process that resolved the press would have.
    insert_escalation(store, make_escalation())
    first = CallbackBridge(db_path=db_path, client=client, now=lambda: RESOLVED_AT)
    await first.handle(press(EscalationChoice.KILL))

    restarted = CallbackBridge(db_path=db_path, client=client, now=lambda: RESOLVED_AT)
    outcome = await restarted.handle(press(EscalationChoice.KILL))

    assert outcome == BridgeOutcome.ALREADY_RESOLVED
    assert len(client.signals) == 1


async def test_a_signal_that_never_landed_leaves_the_row_pending(
    bridge: CallbackBridge, client: FakeTemporalClient, store: sqlite3.Connection
) -> None:
    # Temporal unreachable. Recording the press anyway would strand the workflow
    # for the full hour and then kill it — the same outcome as never pressing,
    # but with the operator told it worked.
    insert_escalation(store, make_escalation())

    def unreachable(signal: SentSignal) -> None:
        raise RuntimeError("temporal unreachable")

    client.on_signal = unreachable
    update = press(EscalationChoice.RETRY)

    outcome = await bridge.handle(update)

    assert outcome == BridgeOutcome.SIGNAL_FAILED
    assert escalation_row(store, ESCALATION_ID)["resolution"] is None
    assert len(update.callback_query.answers) == 1
    assert update.callback_query.answers[0].text


async def test_a_press_that_loses_the_race_to_expiry_cannot_overwrite_it(
    bridge: CallbackBridge, client: FakeTemporalClient, store: sqlite3.Connection
) -> None:
    # The state read happens before the signal, so it can go stale; the guarded
    # UPDATE is what actually decides. Here the hour expires while the signal is
    # in flight, and the timeout's decision has to stand (R11/R12).
    insert_escalation(store, make_escalation())
    client.on_signal = lambda signal: expire_escalation(
        store, ESCALATION_ID, resolved_at="2026-08-04T12:00:00Z"
    )
    update = press(EscalationChoice.RETRY)

    outcome = await bridge.handle(update)

    assert outcome == BridgeOutcome.EXPIRED
    row = escalation_row(store, ESCALATION_ID)
    assert row["resolution"] == EXPIRED
    assert row["resolved_via"] == "TIMEOUT"
    assert update.callback_query.answers[0].text
