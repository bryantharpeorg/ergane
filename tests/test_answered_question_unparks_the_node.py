"""US3 — an answered question un-parks the node, and the epic behind it.

079-US3. The question channel's first live exercise failed end to end, in the
most expensive shape available: `073/us3` parked on a question, the operator
answered, the `QuestionWorkflow` child ran to COMPLETED — and the node stayed
`WAITING_OPERATOR` with the epic PAUSED and two undispatched siblings behind it.
The park replayed identically across a worker restart with zero pending
activities.

**The reproduction named the line, and it was not in the answered branch.** The
plan (trap 6) warned that the branch reads correctly and told the implementer to
reproduce before editing it. It does read correctly, and it is correct:
`test_an_answer_that_arrives_long_after_the_park_un_parks_the_node` below drives
the *live* timing the existing 008-US2 tests never did — the operator's reply
signalled to the child minutes after the park rather than during `send_question`
— and it passed against the unfixed tree.

What wedges the epic is the teardown *at* the park (`workflow.py`, the
`await self._teardown(...)` between `record.state = WAITING_OPERATOR` and the
`wait_condition` that waits for the answer). A parked question is the one
termination that writes `termination='question'` to the ledger, and
`factory/usage/ledger.py` has never had a migration: `'question'` entered the
`usage_records` CHECK in 008 (e652c1c, 2026-08-07) and `'auth_failure'` in 070
(357d227), both behind `CREATE TABLE IF NOT EXISTS`, which is a no-op on a table
that already exists. An installed ledger older than its `_SCHEMA_DDL` refuses the
row, `teardown_attempt` exhausts its retries, and `_run_node` raises **holding
the park**: `self._paused` stays True with nobody alive to clear it, and
`_drain_in_flight` — which deliberately never waits on a `WAITING_OPERATOR` node,
because a parked one is alive by design — never reaps the corpse. The epic is
stopped, forever, and the symptom is indistinguishable from a bug in the question
branch (trap 7 called this exactly).

So the fix is two: the ledger migrates (the cause), and the park is released on
the raising path as well as the returning one (the blast radius — *any* raise
between the park and the un-park costs the whole epic, not just this one).

Trap 3's discipline applies to the control: US3-S4's expiry test is here to catch
a "fix" that un-parks by never parking.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest
from temporalio import activity
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment

from factory.notify.service import QUESTION_SIGNAL_NAME
from factory.usage import ledger
from factory.usage.models import Termination, UsageRecord
from factory.workgraph.models import EpicState, NodeState, WorkNode
from factory.workgraph.prompt import OperatorAnswer, build_attempt_prompt
from factory.workgraph.workflow import EpicWorkflow

from tests.test_interpreter import (
    ANSWER_HEADING,
    ANSWER_TEXT,
    EPIC_ID,
    PLAN_TEXT,
    QUESTION_BODY,
    SPEC_TEXT,
    TASKS_TEXT,
    ScriptedWorld,
    TeardownInput,
    env,  # noqa: F401  — pytest fixture, re-exported for this module
    failing,
    make_graph,
    make_node,
    passing,
    run_epic,
    start_epic,
    states,
    wait_for,
    wait_for_status,
)

#: Real seconds a wedged epic is given to prove it is wedged. Long enough that a
#: slow un-park is not mistaken for a park, short enough that the reproduction is
#: a test rather than a coffee break.
WEDGE_TIMEOUT_S = 30.0


def _named(fn: Any) -> str:
    """The scripted activity's own function name — how one is swapped for another."""
    return getattr(fn, "__name__", "")


# --- the store half: a ledger older than the value the park writes -------------


#: `usage_records` exactly as `factory/usage/ledger.py` wrote it before 008 —
#: `git show e915296:factory/usage/ledger.py`. This is the DDL SQLite recorded in
#: `sqlite_master` on every ledger created before 2026-08-07, and it is the text
#: the migration has to recognise and rewrite. Pasted verbatim rather than
#: generated: the point of the test is that the *recorded* text is what the
#: installed store carries, and a paraphrase would test the paraphrase.
_PRE_008_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS usage_records (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    epic_id                TEXT    NOT NULL,
    node_id                TEXT    NOT NULL,
    attempt                INTEGER NOT NULL CHECK (attempt >= 1),
    persona                TEXT    NOT NULL,
    spec_ref               TEXT    NOT NULL,
    key_alias              TEXT    NOT NULL UNIQUE,          -- "{epic}:{node}:{attempt}:{persona}"; idempotency guard
    prompt_tokens          INTEGER,                          -- NULL = unknown (never fabricated 0)
    completion_tokens      INTEGER,
    cache_read_tokens      INTEGER,                          -- NULL = metric absent from backend
    cache_write_tokens     INTEGER,
    request_count          INTEGER,
    spend_usd              REAL,                             -- NULL only if no snapshot ever taken
    final_usage_confirmed  INTEGER NOT NULL CHECK (final_usage_confirmed IN (0, 1)),
    termination            TEXT    NOT NULL CHECK (termination IN
                               ('completed', 'agent_error', 'timeout', 'killed')),
    issued_at              TEXT    NOT NULL,                 -- ISO 8601 UTC
    torn_down_at           TEXT    NOT NULL                  -- ISO 8601 UTC
);

CREATE INDEX IF NOT EXISTS idx_usage_epic     ON usage_records (epic_id);
CREATE INDEX IF NOT EXISTS idx_usage_persona  ON usage_records (persona);
CREATE INDEX IF NOT EXISTS idx_usage_spec_ref ON usage_records (spec_ref);
CREATE INDEX IF NOT EXISTS idx_usage_attempt  ON usage_records (epic_id, node_id, attempt);
"""


def _record(**overrides: Any) -> UsageRecord:
    """One teardown's row, defaulting to the one a completed attempt writes."""
    fields: dict[str, Any] = {
        "epic_id": EPIC_ID,
        "node_id": "us1",
        "attempt": 1,
        "persona": "implementer",
        "spec_ref": f"{EPIC_ID}:US1",
        "key_alias": f"{EPIC_ID}:us1:1:implementer",
        "prompt_tokens": 1200,
        "completion_tokens": 180,
        "cache_read_tokens": None,
        "cache_write_tokens": None,
        "request_count": 1,
        "spend_usd": 0.004,
        "final_usage_confirmed": True,
        "termination": Termination.COMPLETED,
        "issued_at": "2026-08-21T09:30:00Z",
        "torn_down_at": "2026-08-21T09:32:00Z",
    }
    fields.update(overrides)
    return UsageRecord(**fields)


def _install_pre_008_ledger(path: Path) -> None:
    """Write a ledger with the pre-008 DDL and one row already in it."""
    conn = sqlite3.connect(path)
    try:
        conn.executescript(_PRE_008_DDL)
        conn.execute("INSERT INTO schema_version (version) VALUES (1)")
        conn.execute(
            "INSERT INTO usage_records (epic_id, node_id, attempt, persona, "
            "spec_ref, key_alias, final_usage_confirmed, termination, issued_at, "
            "torn_down_at) VALUES "
            "('older', 'us9', 1, 'implementer', 'older:US9', 'older:us9:1:implementer',"
            " 1, 'completed', '2026-08-01T00:00:00Z', '2026-08-01T00:01:00Z')"
        )
        conn.commit()
    finally:
        conn.close()


def test_a_pre_008_ledger_refuses_the_row_a_parked_question_owes(
    tmp_path: Path,
) -> None:
    """US3-S6's premise, asserted rather than assumed (trap 7).

    Before anything claims the migration fixes something, this pins what an
    installed ledger older than `'question'` actually does with the row the park
    writes: it refuses it, by name, from the CHECK constraint. The tree's DDL
    lists `'question'` (`factory/usage/ledger.py`); this table is what is on the
    operator's disk, and the two are not the same object.
    """
    path = tmp_path / "old-ledger.db"
    _install_pre_008_ledger(path)

    conn = sqlite3.connect(path)
    try:
        with pytest.raises(sqlite3.IntegrityError) as caught:
            conn.execute(
                "INSERT INTO usage_records (epic_id, node_id, attempt, persona, "
                "spec_ref, key_alias, final_usage_confirmed, termination, "
                "issued_at, torn_down_at) VALUES "
                "('demo', 'us1', 1, 'implementer', 'demo:US1', 'demo:us1:1:impl',"
                " 1, 'question', '2026-08-21T09:30:00Z', '2026-08-21T09:32:00Z')"
            )
    finally:
        conn.close()

    # Named, not generic. SQLite quotes the constraint it could not satisfy, so
    # the message an operator finds in the failed activity is the stale value
    # list itself — the four terminations of 2026-08-06, with `'question'` not
    # among them.
    message = str(caught.value)
    assert "CHECK constraint failed" in message
    assert "termination IN" in message
    assert "'question'" not in message


def test_connecting_a_pre_008_ledger_widens_it_so_a_question_teardown_lands(
    tmp_path: Path,
) -> None:
    """US3-S6 (T027): the teardown succeeds on a store that predates the value.

    `connect` is what `teardown_attempt` opens the ledger with, so the migration
    runs where the failure was: a store created before 008 admits
    `termination='question'` after one connect, and the row the park owes is
    written rather than refused. The scenario allows either "succeeds" or "fails
    by name"; this is the first, which is the one that un-wedges the epic.
    """
    path = tmp_path / "old-ledger.db"
    _install_pre_008_ledger(path)

    conn = ledger.connect(path)
    try:
        stored = ledger.upsert_record(
            conn, _record(termination=Termination.QUESTION, key_alias="demo:us1:1:i")
        )
        assert stored.id is not None
        [(termination,)] = conn.execute(
            "SELECT termination FROM usage_records WHERE key_alias = ?",
            ("demo:us1:1:i",),
        ).fetchall()
        assert termination == "question"

        # The table an operator's `.schema` shows is still `usage_records`, and
        # the widened list is the tree's. A rebuild that left the scaffolding
        # name behind would be a published surface changed under them (FR-012).
        [(recorded,)] = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='usage_records'"
        ).fetchall()
        assert "usage_records_v3" not in recorded
        assert "'question'" in recorded
        assert "'auth_failure'" in recorded
    finally:
        conn.close()


def test_the_widening_keeps_the_rows_the_ledger_already_had(tmp_path: Path) -> None:
    """A rebuild that loses spend is worse than the refusal it fixes.

    `usage_records` is the factory's only record of what was spent (constitution
    V), so the migration is judged on what survives it: the pre-existing row,
    with its `id`, its columns and the UNIQUE guard that makes a re-run teardown
    idempotent rather than duplicating. The indexes come back too — `DROP TABLE`
    takes them with it, and a ledger that silently lost its indexes would degrade
    `ergane usage` on the one table it reads.
    """
    path = tmp_path / "old-ledger.db"
    _install_pre_008_ledger(path)
    before = sqlite3.connect(path)
    try:
        [(old_id,)] = before.execute(
            "SELECT id FROM usage_records WHERE key_alias = 'older:us9:1:implementer'"
        ).fetchall()
    finally:
        before.close()

    conn = ledger.connect(path)
    try:
        rows = conn.execute(
            "SELECT id, epic_id, node_id, persona, termination FROM usage_records"
        ).fetchall()
        assert rows == [(old_id, "older", "us9", "implementer", "completed")]

        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND tbl_name='usage_records' AND name LIKE 'idx_%'"
            )
        }
        assert indexes == {
            "idx_usage_epic",
            "idx_usage_persona",
            "idx_usage_spec_ref",
            "idx_usage_attempt",
        }

        # The UNIQUE guard `upsert_record` relies on came across: the second
        # teardown of one attempt lands on the first one's row (SC-001).
        first = ledger.upsert_record(conn, _record(termination=Termination.QUESTION))
        second = ledger.upsert_record(conn, _record(termination=Termination.QUESTION))
        assert first.id == second.id
        [(count,)] = conn.execute("SELECT COUNT(*) FROM usage_records").fetchall()
        assert count == 2
    finally:
        conn.close()


def test_every_termination_the_factory_can_write_is_admitted_after_a_migration(
    tmp_path: Path,
) -> None:
    """`'question'` was not the only value added behind `IF NOT EXISTS`.

    070 added `'auth_failure'` the same way, so a ledger old enough to refuse one
    refuses the other, and a migration that named only the value this story
    tripped over would leave the next teardown to find the next one. The
    constraint is widened to whatever `_SCHEMA_DDL` admits, which is the whole
    `Termination` vocabulary.
    """
    path = tmp_path / "old-ledger.db"
    _install_pre_008_ledger(path)

    conn = ledger.connect(path)
    try:
        for index, termination in enumerate(Termination, start=1):
            stored = ledger.upsert_record(
                conn,
                _record(termination=termination, key_alias=f"demo:us1:{index}:impl"),
            )
            assert stored.termination == termination
    finally:
        conn.close()


def test_a_current_ledger_is_left_exactly_as_it_is(tmp_path: Path) -> None:
    """The migration is keyed off the recorded constraint, and no-ops otherwise.

    A ledger this ergane created already admits every value, so connecting it
    twice must not rebuild the table: a rebuild that ran on every connect would
    renumber nothing but would churn the one file the factory cannot afford to
    lose, on every teardown of every attempt.
    """
    path = tmp_path / "current-ledger.db"
    first = ledger.connect(path)
    try:
        ledger.upsert_record(first, _record(termination=Termination.QUESTION))
        [(recorded,)] = first.execute(
            "SELECT sql FROM sqlite_master WHERE name='usage_records'"
        ).fetchall()
    finally:
        first.close()

    second = ledger.connect(path)
    try:
        [(again,)] = second.execute(
            "SELECT sql FROM sqlite_master WHERE name='usage_records'"
        ).fetchall()
        # Byte-identical: nothing was rebuilt, nothing was renamed.
        assert again == recorded
        assert "usage_records_v3" not in again
        [(count,)] = second.execute("SELECT COUNT(*) FROM usage_records").fetchall()
        assert count == 1
    finally:
        second.close()


# --- the workflow half: what the wedge did to the epic -------------------------


class RefusingLedgerWorld(ScriptedWorld):
    """`teardown_attempt` fails the way a ledger older than `'question'` fails it.

    The one scripted delta from the ordinary world: the teardown of a QUESTION
    attempt raises the `IntegrityError` an installed pre-008 `usage_records`
    CHECK produces (asserted verbatim by the store tests above). Every other
    teardown behaves normally, so the failure is the park's and nothing else's —
    a world where every teardown failed would prove something much weaker.
    """

    def activities(self) -> list[Any]:
        script = self
        base = super().activities()

        @activity.defn(name="teardown_attempt")
        async def teardown_attempt(request: TeardownInput) -> UsageRecord:
            lease = request.lease
            script._log(f"teardown_attempt:{lease.persona}", lease.node_id)
            script.teardowns.append(request)
            if request.termination == Termination.QUESTION:
                raise ApplicationError(
                    "CHECK constraint failed: usage_records",
                    type="IntegrityError",
                )
            script._live_aliases.discard(lease.key_alias)
            return UsageRecord(
                epic_id=lease.epic_id,
                node_id=lease.node_id,
                attempt=lease.attempt,
                persona=lease.persona,
                spec_ref=lease.spec_ref,
                key_alias=lease.key_alias,
                prompt_tokens=1200,
                completion_tokens=180,
                cache_read_tokens=None,
                cache_write_tokens=None,
                request_count=1,
                spend_usd=0.004,
                final_usage_confirmed=True,
                termination=request.termination,
                issued_at=lease.issued_at,
                torn_down_at="2026-08-21T09:32:00Z",
            )

        return [
            teardown_attempt if _named(a) == "teardown_attempt" else a
            for a in base
        ]


def _questioning(world: ScriptedWorld) -> ScriptedWorld:
    """Arm `us1`'s marker, and leave the answer for the test to deliver."""
    world.question_bodies["us1"] = QUESTION_BODY
    return world


async def _park(handle: Any, script: ScriptedWorld) -> Any:
    """Wait until `us1` is parked, the epic is paused, and the question has shipped."""
    parked = await wait_for_status(
        handle,
        lambda status: states(status).get("us1") == NodeState.WAITING_OPERATOR
        and status.epic_state == EpicState.PAUSED,
        what="us1 to park WAITING_OPERATOR and the epic to pause",
    )
    await wait_for(
        lambda: len(script.question_requests) == 1,
        what="the question child to send its message",
    )
    return parked


async def _answer(env: WorkflowEnvironment, script: ScriptedWorld, text: str) -> None:
    """Answer the shipped question the way the bridge does — a signal to the child.

    `send_question` names the workflow the reply must reach (041-US3: the row
    points at the `QuestionWorkflow`, so a reply reaches what is waiting), and
    the id it was sent under is the one the signal threads to. This is the live
    return path with the live *timing*: the reply lands after the park, not
    inside the send the way the 008-US2 fixtures deliver it.
    """
    [sent] = script.question_requests
    child = env.client.get_workflow_handle(sent.workflow_id)
    await child.signal(QUESTION_SIGNAL_NAME, args=[sent.question_id, text])


async def test_a_teardown_the_ledger_refuses_at_the_park_does_not_wedge_the_epic(
    env: WorkflowEnvironment,
) -> None:
    """US3-S5 / T022 — the reproduction, and the fix it named (FR-009, FR-011).

    The whole 073 shape in one test: `us1` asks, parks, and its teardown is
    refused by a ledger whose CHECK predates `'question'`. Against the unfixed
    tree this hung — the coroutine raised holding `_paused`, `_drain_in_flight`
    skipped the corpse because the record still said `WAITING_OPERATOR`, and the
    epic sat PAUSED with `us1` parked and `us2`/`us3` PENDING until the test
    timed out (the run is pasted in
    `specs/079-a-pressed-button-does-what-it-says/evidence/us3-reproduction.md`).

    What is asserted is not that the teardown succeeds — with this ledger it
    cannot, and pretending otherwise would be the fix that deletes the check.
    It is that the failure costs one node instead of the epic: `us1` leaves
    `WAITING_OPERATOR` for a terminal that names the reason, the pause is
    released, and the sibling standing behind the park runs.
    """
    script = _questioning(
        RefusingLedgerWorld(
            {"us1": [passing()], "us2": [passing()], "us3": [passing()]},
            client=env.client,
        )
    )

    async with start_epic(env, script) as handle:
        await _park(handle, script)

        final = await wait_for_status(
            handle,
            lambda status: states(status).get("us1") != NodeState.WAITING_OPERATOR,
            what="us1 to stop being parked on a question its teardown cannot close",
            timeout=WEDGE_TIMEOUT_S,
        )

        # The node ends terminal, and the terminal says why — an operator reading
        # the status sees the ledger's refusal, not an unexplained park.
        assert final.nodes["us1"].state == NodeState.KILLED
        assert final.nodes["us1"].terminal_reason
        assert not final.nodes["us1"].awaiting_operator

        # FR-011: the scheduler is released. `us3` depends on nothing and was
        # PENDING behind the park; it dispatches once the pause lifts. `us2`
        # depended on `us1`, whose edge is now dead, so it is locked out rather
        # than left PENDING forever — the accounting the drain owes.
        resumed = await wait_for_status(
            handle,
            lambda status: "us3" in script.dispatched,
            what="the sibling behind the park to dispatch",
            timeout=WEDGE_TIMEOUT_S,
        )
        assert resumed.epic_state != EpicState.PAUSED
        assert states(resumed)["us2"] == NodeState.KILLED


async def test_an_answer_that_arrives_long_after_the_park_un_parks_the_node(
    env: WorkflowEnvironment,
) -> None:
    """US3-S1 / T023 (FR-009): answered → un-parked → a new attempt dispatched.

    The live timing, which the 008-US2 fixtures do not exercise: they deliver the
    reply from inside `send_question`, so the parent is still inside its teardown
    when the child settles and its `wait_condition` is satisfied before it is
    ever reached. Here the test waits for the park to be *observable* — the node
    `WAITING_OPERATOR`, the epic PAUSED, the question shipped — and only then
    signals the child, which is what an operator answering hours later does.

    This is the half the plan told the implementer not to guess at (trap 6), and
    it is the half that was already correct.
    """
    script = _questioning(
        ScriptedWorld(
            {"us1": [passing(), passing()], "us2": [passing()], "us3": [passing()]},
            client=env.client,
        )
    )

    async with start_epic(env, script) as handle:
        parked = await _park(handle, script)
        assert parked.nodes["us1"].attempt == 1
        assert [c.attempt for c in script.attempts if c.node_id == "us1"] == [1]

        await _answer(env, script, ANSWER_TEXT)

        resumed = await wait_for_status(
            handle,
            lambda status: states(status).get("us1") != NodeState.WAITING_OPERATOR,
            what="us1 to leave WAITING_OPERATOR once the answer lands",
        )
        assert not resumed.nodes["us1"].awaiting_operator

        # A new attempt, dispatched — not a node that merely changed state.
        await wait_for(
            lambda: [c.attempt for c in script.attempts if c.node_id == "us1"]
            == [1, 2],
            what="the answer attempt to dispatch",
        )
        # And it is a real attempt with its own key bracket, not a replay of the
        # question attempt's.
        assert [
            r.attempt for r in script.key_requests if r.node_id == "us1"
        ] == [1, 2]


async def test_the_answer_attempts_prompt_carries_the_exchange_verbatim(
    env: WorkflowEnvironment,
) -> None:
    """US3-S2 / T024 (FR-010): the assembled prompt string, asserted as a string.

    The claim is about bytes the agent reads, so it is made against the prompt
    the workflow actually handed the adapter — `AttemptContext.prompt` for the
    attempt that followed the answer — and both halves of the exchange are
    checked for verbatim, unwrapped presence: the question the agent asked and
    the answer the operator typed, under the dedicated `## Operator answer`
    heading that keeps them out of the verification-evidence section (FR-003).
    """
    script = _questioning(
        ScriptedWorld(
            {"us1": [passing(), passing()], "us2": [passing()], "us3": [passing()]},
            client=env.client,
        )
    )

    async with start_epic(env, script) as handle:
        await _park(handle, script)
        await _answer(env, script, ANSWER_TEXT)
        await wait_for(
            lambda: len(script.prompts_for("us1")) == 2,
            what="the answer attempt's prompt to be assembled",
        )

    question_prompt, answer_prompt = script.prompts_for("us1")

    # The park's own attempt was dispatched before any of this existed.
    assert ANSWER_HEADING not in question_prompt
    assert ANSWER_TEXT not in question_prompt

    assert ANSWER_HEADING in answer_prompt
    assert QUESTION_BODY in answer_prompt
    assert ANSWER_TEXT in answer_prompt
    # Verbatim means the whole thing, not a first line: every paragraph of the
    # operator's reply survives, in order, under the one heading.
    heading_at = answer_prompt.index(ANSWER_HEADING)
    assert answer_prompt.index(QUESTION_BODY) > heading_at
    assert answer_prompt.index(ANSWER_TEXT) > heading_at


def test_the_assembled_prompt_renders_the_exchange_without_a_workflow() -> None:
    """US3-S2's other half: the assembler is pure, so the string can be read whole.

    `build_attempt_prompt` is the one function that decides those bytes, and it
    takes the exchange as data. Asserting on it directly is what lets the
    evidence in `evidence/us3-reproduction.md` paste a prompt rather than
    describe one (constitution VIII).
    """
    prompt = build_attempt_prompt(
        node=make_node("us1", "US1"),
        epic_id=EPIC_ID,
        spec_text=SPEC_TEXT,
        plan_text=PLAN_TEXT,
        tasks_text=TASKS_TEXT,
        operator_answer=OperatorAnswer(
            question_text=QUESTION_BODY, answer_text=ANSWER_TEXT
        ),
    )

    assert ANSWER_HEADING in prompt
    assert QUESTION_BODY in prompt
    assert ANSWER_TEXT in prompt
    # Nothing paraphrased the operator: the reply's own line breaks are the ones
    # in the prompt.
    for line in ANSWER_TEXT.splitlines():
        assert line in prompt


async def test_a_sibling_pending_behind_the_park_dispatches_once_the_node_resumes(
    env: WorkflowEnvironment,
) -> None:
    """US3-S3 / T025 (FR-011): the half that cost 073 its morning.

    Two stories waited behind one park. The park pauses the epic deliberately —
    the scheduler must not spend keys on siblings while an operator is being
    asked a question — so the claim is not "the pause is wrong", it is that the
    pause *ends*: the independent leaf `us3` is PENDING at the park and running
    after the answer, without the operator touching anything but the reply.
    """
    script = _questioning(
        ScriptedWorld(
            {"us1": [passing(), passing()], "us2": [passing()], "us3": [passing()]},
            client=env.client,
        )
    )

    async with start_epic(env, script) as handle:
        parked = await _park(handle, script)
        # The premise: the sibling really is stopped behind the park, not merely
        # slow. Nothing but `us1` has been dispatched.
        assert states(parked)["us3"] == NodeState.PENDING
        assert states(parked)["us2"] == NodeState.PENDING
        assert script.dispatched == ["us1"]

        await _answer(env, script, ANSWER_TEXT)

        resumed = await wait_for_status(
            handle,
            lambda status: status.epic_state == EpicState.RUNNING
            and states(status).get("us1") != NodeState.WAITING_OPERATOR,
            what="the epic to resume once the node un-parks",
        )
        assert resumed.epic_state == EpicState.RUNNING

        status = await wait_for_status(
            handle,
            lambda s: "us3" in script.dispatched,
            what="us3, which waited behind the park, to dispatch",
        )
        assert "us3" in script.dispatched
        assert states(status)["us3"] != NodeState.PENDING


async def test_an_answered_park_lets_the_whole_epic_finish(
    env: WorkflowEnvironment,
) -> None:
    """FR-009 + FR-011 together: every node behind the park lands, not just one.

    The end-to-end reading of 073's loss. One question, answered once, and the
    epic completes with all three nodes merged — including `us2`, whose only
    relationship to the question is that it depended on the node that asked it.
    """
    script = _questioning(
        ScriptedWorld(
            {"us1": [passing(), passing()], "us2": [passing()], "us3": [passing()]},
            client=env.client,
        )
    )

    async with start_epic(env, script) as handle:
        await _park(handle, script)
        await _answer(env, script, ANSWER_TEXT)
        status = await handle.result()

    assert status.epic_state == EpicState.COMPLETED
    assert states(status) == {
        "us1": NodeState.MERGED,
        "us2": NodeState.MERGED,
        "us3": NodeState.MERGED,
    }
    assert "overrun" not in script.calls


# --- the control ---------------------------------------------------------------


async def test_an_expired_question_still_re_enters_the_ladder_as_a_fail(
    env: WorkflowEnvironment,
) -> None:
    """US3-S4 / T026 — **the control** (FR-012): expiry behaviour is unchanged.

    A question nobody answers must keep doing exactly what it did before this
    story: the child's own 8h window closes, `expire_question` marks the row, the
    node un-parks, and the attempt re-enters the ladder as a FAIL that consumes a
    slot (008 FR-001/FR-004 — the one case where a question burns, because the
    operator never engaged and a node cannot park forever).

    This is the test that catches the two cheap ways to make the rest of this
    file green: releasing the park by never parking, and treating every settled
    question as an answer. Neither survives an expiry that must still cost a
    slot.
    """
    script = _questioning(
        ScriptedWorld(
            # Ask on attempt 1; the expiry burns that slot, so the two ordinary
            # attempts left in the default budget of 3 are what follow. Both
            # pass-free: the node fails out through the ladder rather than
            # merging, so the FAIL the expiry appended is visible in the count.
            {
                "us1": [passing(), failing(2), failing(3), failing(4)],
                "us3": [passing()],
            },
            client=env.client,
            press="KILL",
        )
    )
    # No `question_answer`, and the test signals nothing: the window closes.

    status = await run_epic(env, script)

    # The expiry ran — the child's window, not the escalation hour.
    assert script.question_expirations
    # The node un-parked into the ladder and spent what the FAIL left it: the
    # question attempt (1), the two ordinary attempts remaining out of the
    # default budget of three, and one debugger cycle — then the escalation the
    # operator killed. One fewer than the answered case, which reaches five
    # (`test_an_answered_question_consumes_no_ladder_slot`, 008-US2): the
    # difference between those two numbers *is* the slot the expiry burned, and
    # a change that stopped the expiry costing one would show up here as a fifth
    # attempt.
    assert [c.attempt for c in script.attempts if c.node_id == "us1"] == [1, 2, 3, 4]
    assert states(status)["us1"] == NodeState.KILLED
    # And the epic did not stay paused behind the expired park: the independent
    # leaf ran.
    assert "us3" in script.dispatched


async def test_an_expired_question_leaves_no_node_parked_and_no_epic_paused(
    env: WorkflowEnvironment,
) -> None:
    """The control's other half: expiry releases the same two pieces of state.

    US3-S4 says "unchanged", and unchanged includes the un-park the expiry path
    has always done. Asserted separately from the ladder accounting above so a
    regression in either is legible on its own.
    """
    script = _questioning(
        ScriptedWorld(
            {"us1": [passing(), passing()], "us2": [passing()], "us3": [passing()]},
            client=env.client,
        )
    )

    status = await run_epic(env, script)

    assert script.question_expirations
    assert status.epic_state == EpicState.COMPLETED
    assert states(status)["us1"] == NodeState.MERGED
    assert not any(node.awaiting_operator for node in status.nodes.values())


async def test_a_kill_while_parked_still_leaves_the_node_parked(
    env: WorkflowEnvironment,
) -> None:
    """The other control: the release is for raises, not for the deliberate park.

    A kill landing while a node waits on a question is not a failure of the park
    — it is the epic stopping with the page open, and 008 decided the node stays
    parked and the question's row stays pending rather than being expired or
    answered on the operator's behalf. The `except Exception` clause must not
    reach that path, which `break`s rather than raises.
    """
    script = _questioning(
        ScriptedWorld(
            {"us1": [passing(), passing()], "us2": [passing()], "us3": [passing()]},
            client=env.client,
        )
    )

    async with start_epic(env, script) as handle:
        await _park(handle, script)
        await handle.signal(EpicWorkflow.kill_epic)
        status = await handle.result()

    assert status.epic_state == EpicState.KILLED
    # The park's own record is what 008 preserved: the node was never answered
    # and never expired, and the question was not settled behind the operator's
    # back.
    assert script.question_expirations == []
    assert [c.attempt for c in script.attempts if c.node_id == "us1"] == [1]


# --- the graph the reproduction runs on ----------------------------------------


def test_the_reproduction_graph_really_does_stand_a_sibling_behind_the_park() -> None:
    """The premise every un-park test above rests on, checked once.

    `us3` depends on nothing, so a `us3` that is PENDING at the park is stopped
    by the pause and by nothing else — which is what makes "the sibling
    dispatched" a statement about FR-011 rather than about a dependency edge
    resolving.
    """
    graph = make_graph()
    nodes: dict[str, WorkNode] = {node.id: node for node in graph.nodes}

    assert nodes["us3"].depends_on == []
    assert nodes["us3"].depends_on_merged == []
    assert nodes["us2"].depends_on == ["us1"]
