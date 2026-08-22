"""What the operator reads, and what one button press encodes.

Pure rendering: text in, text out, no I/O and no clock. The activity that sends
the escalation and the bridge service that receives the press both build their
Telegram payloads from here, so the message an operator answers and the message
they see after answering are assembled by the same code.

Five decisions carry the weight:

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
- **A message names what every offered press will do, before it is pressed**
  (079-US4, FR-015). `render_blast_radius` spells out both halves — the node and
  the epic — for each choice on the keyboard, and it rides in the footer so the
  clip takes evidence rather than consequence. The button faces cannot carry it:
  "⏸️ Pause the epic" was the gentlest label on the keyboard and the widest
  press, ending the node and every node waiting on it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Sequence

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from factory.mergequeue.models import CheckFailure, Landing, ObservedOutcome, QueueOutcome
from factory.notify.adapter import MessageAction
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
#:
#: 068 FR-008: `KILL` and `KILL_EPIC` are the pair the story separates, so they
#: get different verbs as well as different emoji. Two faces differing only in
#: their last word would satisfy the enum and still be one button to a thumb.
_CHOICE_LABELS = {
    EscalationChoice.RETRY: "🔁 Retry the node",
    EscalationChoice.KILL: "🛑 Kill the node",
    EscalationChoice.PAUSE_EPIC: "⏸️ Pause the epic",
    EscalationChoice.KILL_EPIC: "💥 End the whole epic",
}

#: What one press does — to this node, and to the epic's other work (079-US4,
#: FR-015). One line per offered choice, rendered into the message *before* the
#: press rather than discovered after it.
#:
#: A label is four words on a phone, and four words cannot carry a blast radius.
#: "⏸️ Pause the epic" read as the gentlest button on the keyboard and was the
#: widest: it ended the node and, until US4, every node waiting on it — three at
#: once on 2026-08-19. Both halves are named for every choice because the halves
#: are what distinguish the buttons from each other: `KILL` and `PAUSE_EPIC` do
#: the same thing to the node and opposite things to everything else, and an
#: operator reading only the node half cannot tell them apart.
#:
#: Written as literal prose rather than derived from the interpreter, because a
#: message that computed its own promises could only ever agree with itself.
#: `tests/test_pause_is_not_a_kill.py` asserts the effects against the epic these
#: sentences describe; if a press stops doing what its line says, that is where
#: it fails.
_CHOICE_EFFECTS = {
    EscalationChoice.RETRY: (
        "node: one more attempt, on the tree this one left behind. "
        "epic: unchanged — it keeps dispatching."
    ),
    EscalationChoice.KILL: (
        "node: ends KILLED, its branch preserved. "
        "epic: keeps dispatching, but every node waiting on this one is "
        "locked out and ends KILLED with it, undispatched."
    ),
    EscalationChoice.PAUSE_EPIC: (
        "node: ends parked, not killed — nothing waiting on it is locked out. "
        "epic: stops dispatching until you resume it; the undispatched nodes "
        "keep their place and run then."
    ),
    EscalationChoice.KILL_EPIC: (
        "node: ends KILLED, its branch preserved. "
        "epic: ends with it — nothing else dispatches, and any other node's "
        "open page is cancelled unanswered."
    ),
}

#: The heading the effect block renders under. Spelled once so the message and
#: the test that reads it back cannot disagree about where the block starts.
_BLAST_RADIUS_HEADING = "What each button does:"


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


def escalation_actions(record: EscalationRecord) -> tuple[MessageAction, ...]:
    """One offered choice per action, in the order the workflow offered them.

    The transport-neutral half of `escalation_keyboard` (041 FR-001): a face
    the operator reads and the payload a press carries back. Rendering stays
    here rather than moving into an adapter, because an adapter that composed
    the button faces would make what the operator is asked a property of the
    transport — swap the messenger and the question quietly changes.

    Actions map 1:1 onto `record.choices` (FR-008): a button the workflow would
    refuse to honor is a button that should never have been rendered.
    """
    return tuple(
        MessageAction(
            label=_CHOICE_LABELS.get(EscalationChoice(choice), _value(choice)),
            payload=callback_data(record.escalation_id, choice),
        )
        for choice in record.choices
    )


def actions_keyboard(
    actions: Sequence[MessageAction],
) -> InlineKeyboardMarkup | None:
    """Telegram's view of `actions` — and ``None`` when there are none.

    ``None`` rather than an empty markup, because a question sends with no
    `reply_markup` at all (008 FR-008) and an empty `InlineKeyboardMarkup` is a
    different payload on the wire from no keyboard.
    """
    if not actions:
        return None

    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(action.label, callback_data=action.payload)]
            for action in actions
        ]
    )


def escalation_keyboard(record: EscalationRecord) -> InlineKeyboardMarkup:
    """One button per offered choice, in the order the workflow offered them.

    Buttons map 1:1 onto `record.choices` (FR-008): a button the workflow would
    refuse to honor is a button that should never have been rendered.

    Kept as the Telegram spelling of `escalation_actions` so the two cannot
    drift: the adapter transports the actions, and this renders the same list.
    """
    return actions_keyboard(escalation_actions(record)) or InlineKeyboardMarkup([])


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

    lines: list[str] = []
    for outcome in landing.outcomes:
        line = f"{_value(outcome.outcome)} at {outcome.at}"
        if outcome.failing_checks:
            names = ", ".join(outcome.failing_checks)
            line += f" (failing checks: {names})"
        lines.append(line)
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


def roadmap_failure_notice(roadmap_id: str, failure_text: str, count: int) -> str:
    """The notify-only message when a roadmap pass fails.

    A scheduler pass failure is a fact to be told, not a decision to be asked:
    there is no inline keyboard, no offered choice, no response deadline, and
    no pending escalation row. The message carries the failure text verbatim
    and the consecutive count; the durable fact lives in the `roadmap_failures`
    record written before any send.
    """
    header = f"⚠️ Roadmap failure\nroadmap: {roadmap_id}\n\n"
    count_word = "run" if count == 1 else "runs"
    body = f"Roadmap {roadmap_id} failed ({count} consecutive {count_word}): {failure_text}"
    return _compose(header, body, "")


def roadmap_recovery_notice(roadmap_id: str, prior_count: int) -> str:
    """The notify-only message when a roadmap pass succeeds after prior failures.

    Recovery is a fact to be told, not a decision to be asked: there is no
    inline keyboard, no offered choice, and no response deadline. The message
    names the prior consecutive-failure count so the operator knows the
    scheduler is healthy again.
    """
    header = f"✅ Roadmap recovery\nroadmap: {roadmap_id}\n\n"
    count_word = "failure" if prior_count == 1 else "failures"
    body = f"Roadmap {roadmap_id} recovered after {prior_count} consecutive {count_word}."
    return _compose(header, body, "")


def render_blast_radius(choices: Sequence[EscalationChoice | str]) -> str:
    """What each *offered* choice will do, to the node and to the epic (FR-015).

    Driven by `choices` rather than by the enum, for the reason 079-US1 landed:
    what an escalation offers is computed per node, and a block rendered from the
    vocabulary would describe a retry button that is not on the keyboard.

    A choice this module has no sentence for still gets its line — the name and
    an admission — because an offer whose effect nobody wrote down is precisely
    the case an operator must not read as "no effect".
    """
    lines = [_effect_line(choice) for choice in choices]
    return "\n".join([_BLAST_RADIUS_HEADING, *lines])


def _effect_line(choice: EscalationChoice | str) -> str:
    """One offered choice: its name, its face, and what pressing it does."""
    value = _value(choice)
    try:
        member = EscalationChoice(value)
    except ValueError:
        return f"{value} — effect not documented; do not press."
    label = _CHOICE_LABELS.get(member, value)
    effect = _CHOICE_EFFECTS.get(member, "effect not documented; do not press.")
    return f"{value} ({label}) — {effect}"


def escalation_message(record: EscalationRecord) -> str:
    """The message an operator is paged with: what failed, and what each press does.

    The blast radius rides in the *footer*, not the body (079-US4, FR-015).
    `_compose` reserves header and footer and lets the history absorb the clip,
    so the thing the operator is deciding *from* survives a gate that dumped 32
    KiB — a consequence pushed off the end of the message by evidence would be
    missing exactly when the epic is in the most trouble. It costs the history a
    few hundred characters of the 4096, which is the trade this story makes
    knowingly: the evidence is kept whole in the store, and the effect of a press
    is not recorded anywhere the operator's thumb can reach.
    """
    body = record.history_summary
    if record.check_evidence:
        body += "\n\n" + _render_check_evidence(record.check_evidence)
    return _compose(
        _header("⚠️ Verification escalation", record),
        body,
        f"\n\n{render_blast_radius(record.choices)}"
        f"\n\nNo answer by {record.expires_at} applies the default: KILL the node.",
    )


def _render_check_evidence(evidence: tuple[CheckFailure, ...]) -> str:
    """US2: one line per failing check, with URL and failing test line when known."""
    lines: list[str] = []
    for check in evidence:
        lines.append(f"- {check.name}: {check.url}")
        if check.log_tail:
            # Quote the last line that names a failing test identifier, when present;
            # otherwise quote the last non-empty line of the tail.
            failing_line = _last_failing_test_line(check.log_tail)
            lines.append(f"  failing line: {failing_line}")
        if check.note:
            lines.append(f"  {check.note}")
    return "Failing check evidence:\n" + "\n".join(lines)


def _last_failing_test_line(tail: str) -> str:
    """The last line of `tail` that names a failing test, or the last line."""
    for line in reversed(tail.splitlines()):
        if "FAILED" in line or "failed" in line.lower():
            return line
    return tail.splitlines()[-1] if tail else ""


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
    # The writes marker (084 FR-008), for the same reason one line up: a
    # `DIRTIED_WORKTREE` gate exited 0, so the output tail quoted below this
    # line reads as a clean run and answers none of the operator's question.
    # The paths are the answer, and they are named here or nowhere the operator
    # looks. Both markers render when both were recorded — a gate can be
    # contended and dirty, and neither fact substitutes for the other.
    if gate.worktree_writes:
        written = gate.worktree_writes
        line += f" [wrote {len(written)} path(s): {_writes_marker(written)}]"
    return line


#: How many written paths the operator's gate line names before it counts the
#: rest. A `compileall` gate over a repository writes hundreds, and this line
#: shares `MESSAGE_LIMIT` with every attempt's evidence — the history the
#: RETRY/KILL decision actually turns on. Three is enough to recognise the
#: shape of what was written, which is what the operator reads the line for;
#: the full set is in the evidence store and in the next attempt's prompt.
GATE_WRITES_NAMED = 3


def _writes_marker(paths: Sequence[str]) -> str:
    """The first few written paths, with the remainder counted rather than cut.

    Silent truncation would read as "that is all of them", which is the one
    thing a marker may not say — so the clip names itself, the way `_tail`
    names the lines it dropped.
    """
    named = ", ".join(paths[:GATE_WRITES_NAMED])
    remaining = len(paths) - GATE_WRITES_NAMED
    return f"{named}, +{remaining} more" if remaining > 0 else named


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
