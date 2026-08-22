"""T021 / SC-005: press one button against this host's real Temporal.

    uv run python specs/079-a-pressed-button-does-what-it-says/evidence/us2_press_evidence.py

Its stdout is pasted verbatim into `us2-a-pressed-button-lands.md`. A script and
not a test because SC-005 asks for *output*, and the judge sees only the diff
(constitution VIII): committing it beside the output is what lets anyone re-run
it and get the same page.

Real Temporal, a real workflow that receives the signal, a real SQLite store,
and the shipped `CallbackBridge`. The Bot API is the one part it cannot be:
`scripts/ergane-env.sh` needs `sops`, absent from this worktree's PATH.

SC-004's branch table is the suite's, not this script's — printed by
`tests/test_pressed_button_reaches_the_store.py` as it asserts it.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from temporalio import workflow  # noqa: E402

from factory.notify import service  # noqa: E402
from factory.notify.service import SIGNAL_NAME, CallbackBridge  # noqa: E402
from factory.verify.models import EscalationChoice, EscalationRecord  # noqa: E402
from factory.verify.store import connect, insert_escalation  # noqa: E402

LIVE_TEMPORAL = "127.0.0.1:7233"
#: `default`, never `factory`: that namespace holds the epic that dispatched
#: this node, and evidence must not appear where an operator reads for real.
LIVE_NAMESPACE = "default"


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


class _Capture(logging.Handler):
    """Collects `LogRecord`s, which is what both callers below want."""

    def __init__(self, into: list[Any]) -> None:
        super().__init__()
        self._into = into

    def emit(self, record: logging.LogRecord) -> None:
        self._into.append(record)


# --- T021 / SC-005: one real press ------------------------------------------


@workflow.defn(name="EvidenceEscalationWaiter", sandboxed=False)
class EvidenceEscalationWaiter:
    """Stands in for the node waiting on the button, on the same signal name and
    arity the real interpreter waits on — so the workflow's own return value is
    the proof the decision arrived over a real server."""

    def __init__(self) -> None:
        self._heard: list[Any] = []

    @workflow.run
    async def run(self) -> list[Any]:
        await workflow.wait_condition(lambda: bool(self._heard))
        return self._heard

    @workflow.signal(name=SIGNAL_NAME)
    def escalation_resolved(self, escalation_id: str, choice: str) -> None:
        self._heard.append([escalation_id, choice])


async def real_press() -> None:
    rule("T021 / SC-005 — one press, against this host's Temporal and a real store")

    from temporalio.client import Client
    from temporalio.worker import Worker

    try:
        client = await Client.connect(LIVE_TEMPORAL, namespace=LIVE_NAMESPACE)
    except Exception as exc:
        print(
            f"no Temporal at {LIVE_TEMPORAL} ({type(exc).__name__}: {exc}); "
            "no press could be driven against a live server."
        )
        return

    task_queue = f"us2-evidence-{uuid.uuid4().hex[:8]}"
    workflow_id = f"us2-evidence-{uuid.uuid4().hex[:8]}"
    escalation_id = uuid.uuid4().hex[:12]

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / ".factory" / "verification.db"
        conn = connect(db_path)
        insert_escalation(
            conn,
            EscalationRecord(
                escalation_id=escalation_id,
                workflow_id=workflow_id,
                epic_id="epic-079-evidence",
                node_id="us2",
                choices=[EscalationChoice.RETRY, EscalationChoice.KILL],
                history_summary="attempt 1: gate test FAIL (exit 1)",
                sent_at="2026-08-22T00:00:00Z",
                expires_at="2026-08-22T01:00:00Z",
                delivered=True,
            ),
        )

        print(f"temporal      : {LIVE_TEMPORAL}, namespace {LIVE_NAMESPACE!r}")
        print(f"workflow      : {workflow_id} (EvidenceEscalationWaiter)")
        print(f"escalation    : {escalation_id}")
        print(f"store         : {db_path}")
        print("\nrow before the press:")
        print(f"  {sql_row(conn, escalation_id)}")

        async with Worker(
            client, task_queue=task_queue, workflows=[EvidenceEscalationWaiter]
        ):
            handle = await client.start_workflow(
                EvidenceEscalationWaiter.run, id=workflow_id, task_queue=task_queue
            )

            logging.basicConfig(level=logging.INFO, force=True)
            journal: list[Any] = []
            handler = _Capture(journal)
            logging.getLogger(service.__name__).addHandler(handler)

            bridge = CallbackBridge(db_path=db_path, client=client)
            query = _RecordingQuery(f"esc:{escalation_id}:RETRY")

            print("\npress:")
            print(f"  callback_data = {query.data!r}")
            outcome = await bridge.handle(_Update(query))

            heard = await asyncio.wait_for(handle.result(), timeout=30)
            logging.getLogger(service.__name__).removeHandler(handler)

        print(f"\noutcome       : {outcome.value}")
        print("\nsignal, as the workflow itself returned it:")
        print(f"  {SIGNAL_NAME}{tuple(heard[0])}")
        print("\nrow after the press:")
        print(f"  {sql_row(conn, escalation_id)}")
        print("\nwhat the operator was told:")
        for text in query.answers:
            print(f"  toast: {text}")
        for text in query.edits:
            print(f"  message now reads: {text.splitlines()[0]} …")
        print("\nwhat the journal recorded (FR-007):")
        for line in journal:
            print(f"  {line.getMessage()}")
        conn.close()

    print(
        "\nThe workflow completed on the signal, so the decision reached it: the "
        "`heard` list above is the workflow's own return value, not a recorder's."
    )


def sql_row(conn: sqlite3.Connection, escalation_id: str) -> str:
    cursor = conn.execute(
        "SELECT escalation_id, workflow_id, choices, resolution, resolved_at, "
        "resolved_via FROM escalations WHERE escalation_id = ?",
        (escalation_id,),
    )
    row = cursor.fetchone()
    names = [column[0] for column in cursor.description]
    return " | ".join(f"{name}={value!r}" for name, value in zip(names, row))


class _RecordingQuery:
    """A callback query with the two methods the bridge uses, and no socket.

    The one substituted part of SC-005: there is no bot token on this worktree.
    """

    def __init__(self, data: str) -> None:
        self.data = data
        self.from_user = None
        self.answers: list[str] = []
        self.edits: list[str] = []

    async def answer(self, text: str | None = None, **_kwargs: Any) -> None:
        self.answers.append(str(text))

    async def edit_message_text(self, text: str | None = None, **_kwargs: Any) -> None:
        self.edits.append(str(text))


class _Update:
    def __init__(self, query: _RecordingQuery) -> None:
        self.callback_query = query


if __name__ == "__main__":
    asyncio.run(real_press())
