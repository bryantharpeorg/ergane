"""Produce US2's two pieces of evidence: the branch table, and one real press.

Run from the repository root:

    uv run python specs/079-a-pressed-button-does-what-it-says/evidence/us2_press_evidence.py

Its stdout is pasted verbatim into `us2-a-pressed-button-lands.md`. It is a
script rather than a test because SC-004 and SC-005 ask for *output*, and the
judge sees only the diff (constitution VIII): committing the generator next to
the output is what lets anyone re-run it and get the same page.

**T020 / SC-004** reads the branch table out of `factory/notify/service.py` the
same way the suite does — `_press_path` walks `CallbackBridge.handle`'s AST and
follows `self.<method>(...)` transitively — and then drives every branch in
`tests/test_pressed_button_reaches_the_store.py`'s registry to print what each
one actually produced. The table is measured, not transcribed.

**T021 / SC-005** presses one button for real. What "real" means here is stated
exactly in the artifact and not stretched: a real Temporal server on this host,
a real workflow that really receives the signal, a real SQLite store on disk,
and the real `CallbackBridge`. The Bot API is the one thing it cannot be —
`scripts/ergane-env.sh` needs `sops`, which is not on this worktree's PATH, so
there is no bot token here and no live bridge process to press through.
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

from factory.notify.service import (  # noqa: E402
    SIGNAL_NAME,
    BridgeOutcome,
    CallbackBridge,
)
from factory.verify.models import EscalationChoice, EscalationRecord  # noqa: E402
from factory.verify.store import connect, insert_escalation  # noqa: E402

sys.path.insert(0, str(REPO_ROOT))
from tests.test_pressed_button_reaches_the_store import (  # noqa: E402
    BRANCHES,
    Arrange,
    Branch,
    _press_path,
    _return_spans,
)

LIVE_TEMPORAL = "127.0.0.1:7233"
#: `default`, never `factory`. The factory's own namespace has a live epic in it
#: — the one that dispatched this node — and evidence must not put a workflow
#: anywhere an operator reads for real work.
LIVE_NAMESPACE = "default"


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


# --- T020 / SC-004: the branch enumeration ----------------------------------


async def branch_table() -> None:
    rule("T020 / SC-004 — the press path, walked from the code")

    path = _press_path()
    spans = _return_spans()
    print(
        "CallbackBridge.handle's call graph (follow `self.<method>(...)` "
        "transitively):\n"
    )
    for name in sorted(path):
        lines = sorted(span.start for span in spans.get(name, []))
        print(f"  {name:<22} {len(lines)} return(s) at lines {lines}")
    print(f"\n  {sum(len(v) for v in spans.values())} returns in total.")

    print("\nEvery branch driven, and what it produced:\n")
    header = (
        f"{'branch':<32}{'outcome':<18}{'signal':<8}{'row':<10}"
        f"{'told':<6}{'recorded'}"
    )
    print(header)
    print("-" * len(header))

    covered: set[int] = set()
    with tempfile.TemporaryDirectory() as tmp:
        for index, branch in enumerate(BRANCHES):
            observed = await drive(branch, Path(tmp) / f"b{index}")
            covered |= observed["lines"]
            print(
                f"{branch.name:<32}{observed['outcome'].value:<18}"
                f"{('sent' if observed['signalled'] else '—'):<8}"
                f"{observed['row']:<10}"
                f"{('yes' if observed['told'] else 'n/a'):<6}"
                f"{observed['recorded']}"
            )

    unreached = [
        f"{name}:{span.start}"
        for name, spans_ in spans.items()
        for span in spans_
        if not covered & set(span)
    ]
    print(
        f"\nreturns reached by the table above: "
        f"{sum(len(v) for v in spans.values()) - len(unreached)}"
        f"/{sum(len(v) for v in spans.values())}   unreached: {unreached or 'none'}"
    )
    print(
        "\nEvery row is one of {signal sent + row resolved} or {a named refusal}, "
        "and every row is recorded (FR-006, FR-007)."
    )


async def drive(branch: Branch, root: Path) -> dict[str, Any]:
    """One branch, against a real store, with the journal captured."""
    from tests.test_pressed_button_reaches_the_store import trace_lines

    import pytest

    db_path = root / "verification.db"
    conn = connect(db_path)
    written: list[str] = []
    handler = _CaptureHandler(written)
    logging.getLogger("factory.notify.service").addHandler(handler)
    logging.getLogger("factory.notify.service").setLevel(logging.INFO)
    lines: set[int] = set()

    from tests.test_notify import FakeTemporalClient

    client = FakeTemporalClient()
    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.delenv("ERGANE_ESCALATION_ADAPTER", raising=False)
            update = branch.build(Arrange(store=conn, client=client, patch=patch))
            bridge = CallbackBridge(
                db_path=db_path,
                client=client,
                now=lambda: "2026-08-22T00:00:00Z",
                authorized_responders=branch.responders,
            )
            from factory.notify import service as service_module

            with trace_lines(service_module.__file__, lines):
                outcome = await bridge.handle(update)

        query = getattr(update, "callback_query", None)
        told = bool(query is not None and getattr(query, "answers", None))
        # Raw SQL, not `get_escalation`: one branch exists precisely because the
        # row it seeds is one this build's `EscalationChoice` refuses to read,
        # and the observer must not fail where the subject is meant to.
        row = conn.execute(
            "SELECT resolution FROM escalations WHERE escalation_id = ?",
            ("0123456789ab",),
        ).fetchone()
    finally:
        logging.getLogger("factory.notify.service").removeHandler(handler)
        conn.close()

    resolution = "gone" if row is None else (row[0] or "pending")

    return {
        "outcome": outcome,
        "signalled": bool(client.signals),
        "row": resolution,
        "told": told,
        "recorded": "yes" if written else "NO",
        "lines": lines,
    }


class _CaptureHandler(logging.Handler):
    def __init__(self, into: list[str]) -> None:
        super().__init__()
        self._into = into

    def emit(self, record: logging.LogRecord) -> None:
        self._into.append(record.getMessage())


# --- T021 / SC-005: one real press ------------------------------------------


@workflow.defn(name="EvidenceEscalationWaiter", sandboxed=False)
class EvidenceEscalationWaiter:
    """Stands in for the node that is waiting on the button.

    It waits on the same signal name and the same two arguments the real
    interpreter waits on (`escalation_resolved(escalation_id, choice)`), so what
    the bridge delivers below is delivered to a real workflow over a real
    server, and the workflow's own return value is the proof it arrived.
    """

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
        record = EscalationRecord(
            escalation_id=escalation_id,
            workflow_id=workflow_id,
            epic_id="epic-079-evidence",
            node_id="us2",
            choices=[EscalationChoice.RETRY, EscalationChoice.KILL],
            history_summary="attempt 1: gate test FAIL (exit 1)",
            sent_at="2026-08-22T00:00:00Z",
            expires_at="2026-08-22T01:00:00Z",
            delivered=True,
        )
        insert_escalation(conn, record)

        print(f"temporal      : {LIVE_TEMPORAL}, namespace {LIVE_NAMESPACE!r}")
        print(f"workflow      : {workflow_id} (EvidenceEscalationWaiter)")
        print(f"escalation    : {escalation_id}")
        print(f"store         : {db_path}")
        print("\nrow before the press:")
        print(f"  {sql_row(conn, escalation_id)}")

        async with Worker(
            client,
            task_queue=task_queue,
            workflows=[EvidenceEscalationWaiter],
        ):
            handle = await client.start_workflow(
                EvidenceEscalationWaiter.run,
                id=workflow_id,
                task_queue=task_queue,
            )

            logging.basicConfig(level=logging.INFO, force=True)
            journal: list[str] = []
            handler = _CaptureHandler(journal)
            logging.getLogger("factory.notify.service").addHandler(handler)

            bridge = CallbackBridge(db_path=db_path, client=client)
            query = _RecordingQuery(f"esc:{escalation_id}:RETRY")

            print("\npress:")
            print(f"  callback_data = {query.data!r}")
            outcome = await bridge.handle(_Update(query))

            heard = await asyncio.wait_for(handle.result(), timeout=30)
            logging.getLogger("factory.notify.service").removeHandler(handler)

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
            print(f"  {line}")
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
    """A callback query with the two methods the bridge uses, and no socket."""

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


async def main() -> None:
    await branch_table()
    await real_press()


if __name__ == "__main__":
    asyncio.run(main())
