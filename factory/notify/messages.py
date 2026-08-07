"""What the operator reads, and what one button press encodes.

Pure rendering: text in, text out, no I/O and no clock. The activity that sends
the escalation and the bridge service that receives the press both build their
Telegram payloads from here, so the message an operator answers and the message
they see after answering are assembled by the same code.

Four decisions carry the weight:

- **`callback_data` carries the escalation id, never the workflow id** (R11).
  Telegram rejects a callback payload over 64 bytes outright, and workflow ids
  are arbitrarily long — encoding one would work on a toy epic and make the
  button undeliverable on a real one. `esc:<12-hex>:<CHOICE>` is 49 bytes at its
  widest, so the limit is honored by construction rather than by hoping. That is
  also why `callback_data` raises on a malformed id: the failure belongs at
  construction, not at send time against the Bot API.
- **Parsing validates shape, not authority.** `parse_callback_data` accepts any
  choice spelling that fits the grammar and hands back a plain string; whether
  that choice was ever *offered* is a fact about the stored row, which only the
  bridge can look up. A press for `PAUSE_EPIC` on an escalation that offered only
  RETRY and KILL has to be refused with a notice, and a button from another
  feature — or another deployment — has to be answered rather than raised on,
  because the bridge is one long-lived process.
- **The history is every attempt, clipped only where evidence is huge (SC-005).**
  `render_history` walks the attempts in order and quotes gate output and judge
  feedback *verbatim* — no per-line prefixes, no reflowing — because the operator
  is being asked to judge the same evidence the retry prompts carried (FR-006).
  When a gate dumps a 32 KiB tail, the *last* `EVIDENCE_TAIL_LINES` lines are
  kept: the last lines are the failure, the first lines are the banner.
- **Only `escalation_message` and `resolution_notice` know about Telegram's
  4096-character cap**, and when it bites they say so. The store keeps the
  summary in full; a message silently clipped would read as a complete history
  that happens to end early, which is worse than one that admits it was cut.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Sequence

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from factory.mergequeue.models import Landing, ObservedOutcome, QueueOutcome
from factory.verify.models import (
    EscalationChoice,
    EscalationRecord,
    GateResult,
    GateStatus,
    OutputCheck,
    QuestionRecord,
    VerificationResult,
)
from factory.verify.store import EXPIRED

#: The Bot API's hard ceiling on `callback_data`, in bytes.
CALLBACK_DATA_LIMIT = 64

#: The Bot API's ceiling on a message body, in characters.
MESSAGE_LIMIT = 4096

#: What this component's buttons are stamped with, so the bridge can tell a press
#: it owns from a press belonging to some other handler on the same bot.
CALLBACK_PREFIX = "esc"

#: How many lines of one evidence block survive. Enough to carry a stack trace
#: and the assertion above it; short enough that three attempts of gate output
#: still leave room for the rest of the message.
EVIDENCE_TAIL_LINES = 20

#: The store's token shape (`secrets.token_hex(6)`): 12 lowercase hex digits. One
#: spelling only — the id is a primary key, and `0123456789AB` is a different
#: string from `0123456789ab` to SQLite.
_ESCALATION_ID_RE = re.compile(r"^[0-9a-f]{12}$")

#: Every `EscalationChoice` value is uppercase with underscores; anything else in
#: that position was not written by `callback_data`.
_CHOICE_RE = re.compile(r"^[A-Z_]{1,32}$")

#: One spelling of "evidence was elided here" across the component — the judge's
#: diff truncation writes the same marker.
_TRUNCATION_MARKER = "[... {dropped} lines truncated ...]"

#: One spelling of "the queue history was empty" across the component.
_NO_LANDING_HISTORY = "The node's PR never left the queue; no landing outcome was recorded."

_HISTORY_TRUNCATED = (
    "[... earlier history truncated for Telegram; "
    "the verification store keeps it in full ...]\n"
)

_NO_HISTORY = "No verification attempts were recorded for this node."

#: Button faces, one per choice. Distinct on sight, because the operator is
#: usually reading them on a phone with a failing build in the message above.
_CHOICE_LABELS = {
    EscalationChoice.RETRY: "🔁 Retry the node",
    EscalationChoice.KILL: "🛑 Kill the node",
    EscalationChoice.PAUSE_EPIC: "⏸️ Pause the epic",
}


@dataclass(frozen=True)
class CallbackPress:
    """One decoded button press: which escalation, and what was pressed.

    `choice` is a raw string rather than an `EscalationChoice` on purpose — it is
    whatever came back over the wire, and promoting it to a member here would
    make an unoffered choice look like an offered one.
    """

    escalation_id: str
    choice: str


def callback_data(escalation_id: str, choice: EscalationChoice | str) -> str:
    """Encode one button's payload: `esc:<12-hex>:<CHOICE>`.

    Raises `ValueError` on an id or choice that would not round-trip through
    `parse_callback_data`, which is the only way the ≤64-byte guarantee can be
    kept by construction (R11).
    """
    if not _ESCALATION_ID_RE.match(escalation_id):
        raise ValueError(
            f"escalation id must be 12 lowercase hex digits, got {escalation_id!r}"
        )

    value = _value(choice)
    if not _CHOICE_RE.match(value):
        raise ValueError(f"escalation choice must be UPPER_SNAKE, got {value!r}")

    return f"{CALLBACK_PREFIX}:{escalation_id}:{value}"


def parse_callback_data(data: str | None) -> CallbackPress | None:
    """Decode a press this component wrote, or None for anything else.

    None covers a button from another handler, a payload from a deployment whose
    format has moved on, and outright garbage. The caller answers the callback
    and moves on; a long-polling bridge that raised here would stop serving every
    other escalation.
    """
    if not data or len(data.encode("utf-8")) > CALLBACK_DATA_LIMIT:
        return None

    parts = data.split(":")
    if len(parts) != 3:
        return None

    prefix, escalation_id, choice = parts
    if prefix != CALLBACK_PREFIX:
        return None
    if not _ESCALATION_ID_RE.match(escalation_id) or not _CHOICE_RE.match(choice):
        return None

    return CallbackPress(escalation_id, choice)


def escalation_keyboard(record: EscalationRecord) -> InlineKeyboardMarkup:
    """One button per offered choice, in the order the workflow offered them.

    Buttons map 1:1 onto `record.choices` (FR-008): a button the workflow would
    refuse to honor is a button that should never have been rendered.
    """
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    _CHOICE_LABELS.get(EscalationChoice(choice), _value(choice)),
                    callback_data=callback_data(record.escalation_id, choice),
                )
            ]
            for choice in record.choices
        ]
    )


def render_history(results: Sequence[VerificationResult]) -> str:
    """Every attempt, oldest first, with its evidence quoted verbatim (SC-005).

    This is what `send_escalation` stores as `history_summary` and what the
    message body is built from. Gate output and judge feedback are reproduced
    unmodified — no indentation, no prefixes — because the operator is checking
    the same text the retry prompts fed back to the agent (FR-006, SC-004); only
    an oversized block is clipped, and then it keeps its tail and says how much
    it dropped.
    """
    if not results:
        # Blank reads as "no failures". An escalation with an empty body is the
        # one message shape that actively misleads.
        return _NO_HISTORY

    return "\n\n".join(_render_attempt(result) for result in results)


def render_landing_history(landing: Landing) -> str:
    """The queue history a rejected landing carries, oldest first, with recovery.

    This is what the landing escalation stores as `history_summary` and what its
    message body is built from. Every `ObservedOutcome` is reproduced in order
    with its timestamp, because the operator deciding whether to retry, kill, or
    pause is asking "how many times did the queue kick this PR, and why" — and
    `recovery_cycles` is named so the cost of the recovery ladder (FR-006) is
    visible rather than implied by counting the outcomes themselves.
    """
    if not landing.outcomes:
        return _NO_LANDING_HISTORY

    lines = [f"{_value(o.outcome)} at {o.at}" for o in landing.outcomes]
    if landing.recovery_cycles:
        lines.append(f"Recovery cycles: {landing.recovery_cycles}")
    return "\n".join(lines)


def manual_intervention_notice(record: EscalationRecord) -> str:
    """The notify-only message when a PR is closed by a human, no buttons.

    A human closing the PR is a fact to be told, not a decision to be asked: the
    workflow will not honor a choice it did not offer, so a notice that rendered
    buttons would present options the bridge would have to refuse. FR-007's
    escalation stays the only message shape with a keyboard.
    """
    return _compose(
        _header("⚠️ Manual intervention", record),
        record.history_summary,
        "\n\nThe PR was closed without the factory merging it. "
        "The node branch is preserved and reachable (FR-008).",
    )


def escalation_message(record: EscalationRecord) -> str:
    """The message an operator is paged with: what failed, and what silence does."""
    return _compose(
        _header("⚠️ Verification escalation", record),
        record.history_summary,
        f"\n\nNo answer by {record.expires_at} applies the default: KILL the node.",
    )


def question_message(record: QuestionRecord) -> str:
    """The message an operator is paged with when an agent asks (008-US1, FR-002).

    The mirror of `escalation_message` with the two deltas that make a question a
    question: no keyboard (the operator types a reply rather than pressing a
    button — `send_question` sends with no `reply_markup`), and the body is the
    marker text the detector extracted, shipped verbatim (FR-002). The header
    attributes the question to its epic and node the same way an escalation's
    does, so the operator knows which node is parked and waiting.
    """
    header = f"❓ Operator question\nepic: {record.epic_id}\nnode: {record.node_id}\n\n"
    footer = (
        f"\n\nReply to this message with your answer (attempt {record.attempt}). "
        f"No answer by {record.expires_at} lets the node proceed as a FAIL."
    )
    return _compose(header, record.question_text, footer)


def resolution_notice(
    record: EscalationRecord, resolution: EscalationChoice | str
) -> str:
    """The message text once the decision is in — the same body, a new footer.

    The evidence stays on screen after the buttons are gone: an operator
    scrolling back a day later is asking "what did I decide, and why", and a
    replacement message that answered only the first half would send them to the
    database for the second.
    """
    value = _value(resolution)
    if value == EXPIRED:
        title = "⏱️ Escalation expired"
        footer = (
            f"\n\nNo answer within the hour ({EXPIRED}) — "
            "applying the default: KILL the node."
        )
    else:
        title = "✅ Escalation resolved"
        footer = f"\n\nResolved by button: {value}."

    return _compose(_header(title, record), record.history_summary, footer)


# --- rendering internals ----------------------------------------------------


def _render_attempt(result: VerificationResult) -> str:
    """One attempt: a verdict line, a line per gate, then the failing evidence."""
    lines = [f"Attempt {result.attempt} — {_value(result.verdict)}"]
    blocks: list[str] = []

    for gate in result.gate_results:
        lines.append(_gate_line(gate))
        if _value(gate.status) != GateStatus.PASS.value and gate.output_tail:
            # Only a gate that failed gets its output quoted: nobody was paged
            # over a passing suite's log, and the message has a length budget.
            blocks.append(f"── {gate.name} output ──\n{_tail(gate.output_tail)}")

    if not result.output_check.passed:
        lines.append(_output_check_line(result.output_check))

    if result.judge is not None:
        lines.append(f"  judge: {_value(result.judge.outcome)}")
        if result.judge.feedback:
            blocks.append(f"── judge feedback ──\n{_tail(result.judge.feedback)}")

    return "\n".join([*lines, *blocks])


def _gate_line(gate: GateResult) -> str:
    status = _value(gate.status)
    exit_code = "no exit" if gate.exit_code is None else f"exit {gate.exit_code}"
    line = f"  gate {gate.name}: {status} ({exit_code}, {gate.duration_s:.1f}s)"
    # The contention marker (007 FR-005): a non-zero count says this gate ran
    # alongside neighbours, so a slow verdict is auditable in the escalation
    # message an operator actually reads — not only in the evidence store.
    if gate.concurrent_gates:
        line += f" [contended: {gate.concurrent_gates} peer(s)]"
    return line


def _output_check_line(check: OutputCheck) -> str:
    """Name an empty diff for what it is.

    FR-004's failure reads as "everything passed" in gate output alone — the node
    produced nothing and the suite was green about it. The operator has to be
    told, or the history looks like an inexplicable escalation.
    """
    if not check.has_diff:
        return (
            f"  output check: FAILED — no diff in the {check.write_scope} "
            "write scope; the node produced nothing"
        )
    if check.artifacts_present is False:
        expected = ", ".join(check.expected_artifacts) or "(none declared)"
        return f"  output check: FAILED — expected artifacts missing or empty: {expected}"
    return "  output check: FAILED"


def _tail(text: str) -> str:
    """The last `EVIDENCE_TAIL_LINES` lines, verbatim, with what was dropped named."""
    lines = text.splitlines()
    if len(lines) <= EVIDENCE_TAIL_LINES:
        return text

    dropped = len(lines) - EVIDENCE_TAIL_LINES
    marker = _TRUNCATION_MARKER.format(dropped=dropped)
    return "\n".join([marker, *lines[-EVIDENCE_TAIL_LINES:]])


def _header(title: str, record: EscalationRecord) -> str:
    return f"{title}\nepic: {record.epic_id}\nnode: {record.node_id}\n\n"


def _compose(header: str, body: str, footer: str) -> str:
    """Header + history + footer, clipped to what Telegram will accept.

    The header names the node and the footer states the consequence, so both
    survive intact and the history absorbs the clip — from the front, keeping the
    most recent attempts, which are the ones the decision turns on.
    """
    room = MESSAGE_LIMIT - len(header) - len(footer)
    if len(body) > room:
        keep = max(room - len(_HISTORY_TRUNCATED), 0)
        body = _HISTORY_TRUNCATED + (body[-keep:] if keep else "")

    # Last resort for a pathologically long id in the header: a rejected send is
    # an escalation nobody sees, and the truncated tail still names the node.
    return (header + body + footer)[:MESSAGE_LIMIT]


def _value(item: Any) -> str:
    """The wire spelling of an enum member — or of the string it arrived as.

    A value that crossed a Temporal payload boundary comes back as a plain
    string, and `f"{GateStatus.FAIL}"` renders as `GateStatus.FAIL` since 3.11.
    Both roads lead here.
    """
    return item.value if isinstance(item, Enum) else str(item)
