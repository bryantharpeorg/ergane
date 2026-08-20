"""KILL leaves the epic in a state the CLI can recover (068-US2).

The deadlock this story exists for: an epic parked on an escalation nobody
answers is `RUNNING` as far as Temporal is concerned, so `ergane build reset`
refuses it — and `ergane build kill` does not help, because neither `_escalate`
nor `_escalate_landing` ever looked at `_kill_requested`, so the epic ignored
the signal for up to `escalation_timeout_s` (an hour, by default). The operator's
only remaining move was `temporal workflow terminate`, which is exactly the raw
surgery this story removes.

Three claims, and each is written so that production code doing nothing fails it:

- **FR-006** — a node killed from an escalation leaves no *living* escalation
  child. Proved against the child workflow's own execution status, not against
  the node's state: a node ends `KILLED` on the expiry path too, so the node
  state alone would pass against an epic that stranded its child.
- **FR-007** — `reset` succeeds against an epic whose only living child is a
  stalled escalation, and still refuses one with a genuinely running node. Both
  directions, because a reset that succeeds unconditionally passes the first
  half and is a worse defect than the one being fixed (plan trap 7).
- **FR-008** — ending the node and ending the epic are distinguishable choices.
  Read off the offered buttons and off the pure mapping the workflow routes on,
  so a third button whose meaning collapsed into `KILL`'s would fail.

Nothing here fakes the escalation lifecycle: the epic, the notify activities,
the store and the children are real (`RealNotifyWorld`, borrowed from
`tests/test_epic_escalation_child.py`'s posture), and the only fake is the
socket. The reset half is equally unfaked — a real fixture repository, a real
node worktree with real uncommitted work in it, and the real `ergane` entry
point — because the claim is that a survivor's work is archived, which nothing
in-memory can stand in for.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Iterator, NamedTuple

import pytest
from temporalio.testing import WorkflowEnvironment

from factory.activities.agent_activities import ERGANE_ROOT_ENV, FACTORY_ROOT_ENV
from factory.activities.notify_activities import (
    DEFAULT_CHOICES,
    expire_escalation,
    expire_question,
    find_ferried_question,
    send_escalation,
    send_question,
)
from factory.activities.verify_activities import (
    ERGANE_VERIFICATION_DB_PATH_ENV,
    VERIFICATION_DB_PATH_ENV,
)
from factory.cli.main import main as ergane_main
from factory.notify.adapter import (
    ESCALATION_ADAPTER_ENV,
    register_adapter,
    unregister_adapter,
)
from factory.notify.messages import escalation_actions
from factory.notify.service import (
    SIGNAL_NAME,
    TEMPORAL_ADDRESS_ENV,
    TEMPORAL_NAMESPACE_ENV,
)
from factory.verify import store
from factory.verify.ladder import next_action
from factory.verify.models import (
    EpicEffect,
    EscalationChoice,
    EscalationRecord,
    NextAction,
    VerificationConfig,
    epic_effect,
)
from factory.workgraph.models import EpicState, NodeState, WorkGraph
from factory.workgraph.worktree import branch_name, ensure
from factory.workgraph.workflow import EpicWorkflow

from tests.test_epic_escalation_child import RealNotifyWorld, until
from tests.test_interpreter import (
    EPIC_ID,
    WORKFLOW_ID,
    failing,
    make_graph,
    make_node,
    passing,
    start_epic,
    states,
    wait_for_status,
)
from tests.test_messenger_adapter import FakeAdapter

FAKE_ADAPTER_NAME = "fake-messenger-068-us2"

#: Long enough that the node is provably still in flight while `reset` runs, and
#: short enough that the control test costs seconds rather than minutes.
HELD_DISPATCH_S = 6.0


# --- fixtures ----------------------------------------------------------------


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    environment = await WorkflowEnvironment.start_time_skipping()
    try:
        yield environment
    finally:
        await environment.shutdown()


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A real evidence store, under tmp, where the activities find it."""
    path = tmp_path / ".factory" / "verification.db"
    monkeypatch.setenv(ERGANE_VERIFICATION_DB_PATH_ENV, str(path))
    monkeypatch.delenv(VERIFICATION_DB_PATH_ENV, raising=False)
    return path


@pytest.fixture
def adapter(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeAdapter]:
    """A transport that is not Telegram, selected the way a real one is."""
    fake = FakeAdapter()
    register_adapter(FAKE_ADAPTER_NAME, lambda **_seams: fake)
    monkeypatch.setenv(ESCALATION_ADAPTER_ENV, FAKE_ADAPTER_NAME)
    try:
        yield fake
    finally:
        unregister_adapter(FAKE_ADAPTER_NAME)


@pytest.fixture
def dialled(env: WorkflowEnvironment, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the CLI's `_connect` at this test's server."""
    monkeypatch.setenv(
        TEMPORAL_ADDRESS_ENV, env.client.service_client.config.target_host
    )
    monkeypatch.setenv(TEMPORAL_NAMESPACE_ENV, env.client.namespace)


class Survivors(NamedTuple):
    """A real target repo, a real node worktree with real work in it, and the
    compiled graph naming both — everything `reset` reads and writes."""

    repo: Path
    factory_root: Path
    graph: WorkGraph
    graph_path: Path
    worktrees: dict[str, Path]


@pytest.fixture
def survivors(
    target_repo: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Callable[..., Survivors]:
    """Build the on-disk half of the deadlock, for whichever node ids a test names.

    Dirty worktrees on purpose: `reset`'s whole promise is that a terminated
    node's uncommitted work is committed and archived rather than dropped
    (constitution VI), so a clean tree would let a `reset` that removed the
    directory and lost the work pass.
    """

    def build(*node_ids: str) -> Survivors:
        repo = target_repo("passing")
        factory_root = tmp_path / ".factory"
        monkeypatch.setenv(ERGANE_ROOT_ENV, str(factory_root))
        monkeypatch.delenv(FACTORY_ROOT_ENV, raising=False)

        worktrees: dict[str, Path] = {}
        for node_id in node_ids:
            prepared = ensure(repo, EPIC_ID, node_id, factory_root=factory_root)
            worktree = Path(prepared.path)
            worktrees[node_id] = worktree
            (worktree / f"survivor_{node_id}.py").write_text(
                f"# work {node_id} had not committed when the epic stalled\n",
                encoding="utf-8",
            )

        specs_root = (tmp_path / "specs").resolve()
        specs_root.mkdir(parents=True, exist_ok=True)
        graph = make_graph(
            [make_node(node_id, node_id.upper()) for node_id in node_ids],
            target_repo=str(repo.resolve()),
            specs_root=str(specs_root),
        )
        graph_path = tmp_path / "workgraph.json"
        graph_path.write_text(
            json.dumps(dataclasses.asdict(graph)), encoding="utf-8"
        )
        return Survivors(repo, factory_root, graph, graph_path, worktrees)

    return build


# --- small helpers -----------------------------------------------------------


class Run(NamedTuple):
    code: int
    stdout: str
    stderr: str


def _invoke(argv: tuple[str, ...]) -> int:
    try:
        code = ergane_main(list(argv))
    except SystemExit as exit_request:
        code = exit_request.code
    return 0 if code is None else int(code)


@pytest.fixture
def reset_cli(
    capsys: pytest.CaptureFixture[str],
) -> Callable[..., Any]:
    """Run the real `ergane build reset` off the event loop, and report its exit.

    Off the loop because the verb is `asyncio.run(...)` inside, and these tests
    are async: the exit status is the claim, so it is read from the entry point
    rather than from the coroutine underneath it.
    """

    async def invoke(graph_path: Path) -> Run:
        code = await asyncio.to_thread(
            _invoke, ("build", "reset", str(graph_path))
        )
        captured = capsys.readouterr()
        return Run(code, captured.out, captured.err)

    return invoke


def read(db_path: Path, reader: Any, *args: Any) -> Any:
    with closing(store.connect(db_path)) as conn:
        return reader(conn, *args)


def pending(db_path: Path) -> list[Any]:
    return read(db_path, store.pending_escalations)


def ladder_fails() -> list[Any]:
    """The script that exhausts a node's ladder into an escalation."""
    return [failing(n) for n in (1, 2, 3, 4)]


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def ref_exists(repo: Path, ref: str) -> bool:
    return (
        subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", ref],
            capture_output=True,
            text=True,
        ).returncode
        == 0
    )


def archived(repo: Path, node_id: str) -> list[str]:
    """Every archive ref `reset` left behind for one node."""
    prefix = f"archive/factory/{EPIC_ID}/{node_id}/"
    refs = git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    return [ref for ref in refs.splitlines() if ref.startswith(prefix)]


async def execution_status(env: WorkflowEnvironment, workflow_id: str) -> str:
    described = await env.client.get_workflow_handle(workflow_id).describe()
    assert described.status is not None
    return described.status.name


# --- T011 / US2-S1 / FR-006 --------------------------------------------------


async def test_a_kill_resolution_leaves_no_living_escalation_child(
    env: WorkflowEnvironment, db_path: Path, adapter: FakeAdapter
) -> None:
    """US2-S1: the node the operator killed took its escalation child with it.

    The claim is about the *child*, so it is read off the child's own execution
    status and off the store's pending set — never off `states(result)`, which
    says `KILLED` on the expiry path and on a crash too and would therefore pass
    against an epic that left an hour-long child running behind it.
    """
    script = RealNotifyWorld({"us1": ladder_fails()}, client=env.client)

    async with start_epic(env, script, graph=one_node()) as handle:
        [row] = await until("the escalation row", lambda: pending(db_path) or None)
        await env.client.get_workflow_handle(row.workflow_id).signal(
            SIGNAL_NAME, args=[row.escalation_id, EscalationChoice.KILL.value]
        )
        result = await handle.result()

    assert states(result)["us1"] == NodeState.KILLED
    assert await execution_status(env, row.workflow_id) != "RUNNING"
    assert pending(db_path) == [], "no escalation may outlive the node it paged for"
    settled = read(db_path, store.get_escalation, row.escalation_id)
    assert settled.resolution == EscalationChoice.KILL.value


async def test_build_kill_ends_an_epic_stalled_on_an_escalation(
    env: WorkflowEnvironment, db_path: Path, adapter: FakeAdapter
) -> None:
    """FR-006's live half: `kill_epic` reaches a node parked on an escalation.

    This is the defect. `_escalate` awaited its child unconditionally, so the
    signal sat unread until the escalation's own hour ran out — and the epic
    that "ignored the kill" is the one the operator then terminated by hand.

    `await handle.result()` returning at all is the assertion: the fixture's
    `WorkflowEnvironment` skips time only while a client awaits a result, so a
    `_escalate` that still waits out its child would either hang here or come
    back with the row `EXPIRED`. `resolution is None` discriminates between
    those two endings — a stopped epic is neither a press nor a burn, so the row
    is left exactly as the operator's kill found it.
    """
    script = RealNotifyWorld({"us1": ladder_fails()}, client=env.client)

    async with start_epic(env, script, graph=one_node()) as handle:
        [row] = await until("the escalation row", lambda: pending(db_path) or None)
        await handle.signal("kill_epic")
        result = await handle.result()

    assert result.epic_state == EpicState.KILLED
    assert states(result)["us1"] == NodeState.KILLED
    assert await execution_status(env, row.workflow_id) != "RUNNING"
    stalled = read(db_path, store.get_escalation, row.escalation_id)
    assert stalled.resolution is None, "a stopped epic is neither a press nor a burn"


# --- T012 / US2-S2 / FR-007 --------------------------------------------------


async def test_reset_succeeds_against_the_epic_a_kill_resolution_left(
    env: WorkflowEnvironment,
    db_path: Path,
    adapter: FakeAdapter,
    dialled: None,
    survivors: Callable[..., Survivors],
    reset_cli: Callable[..., Any],
) -> None:
    """US2-S2: exit 0 *and* the effect — the survivor's work is archived.

    Exit status alone would pass against a verb that printed nothing and
    returned, which is why the uncommitted file is asserted to be reachable from
    an archive ref afterwards: `reset` commits a dirty tree before it removes
    it (constitution VI, no work is ever lost).
    """
    plant = survivors("us1")
    script = RealNotifyWorld({"us1": ladder_fails()}, client=env.client)

    async with start_epic(env, script, graph=plant.graph) as handle:
        [row] = await until("the escalation row", lambda: pending(db_path) or None)
        await env.client.get_workflow_handle(row.workflow_id).signal(
            SIGNAL_NAME, args=[row.escalation_id, EscalationChoice.KILL.value]
        )
        result = await handle.result()

    assert states(result)["us1"] == NodeState.KILLED

    outcome = await reset_cli(plant.graph_path)

    assert outcome.code == 0, outcome.stderr
    assert "us1:" in outcome.stdout
    assert not plant.worktrees["us1"].exists()
    assert not ref_exists(plant.repo, f"refs/heads/{branch_name(EPIC_ID, 'us1')}")
    [archive] = archived(plant.repo, "us1")
    assert "survivor_us1.py" in git(plant.repo, "ls-tree", "--name-only", archive)


# --- T013 / US2-S3 / FR-007: the deadlock's own shape ------------------------


async def test_reset_succeeds_against_an_epic_stalled_on_an_escalation(
    env: WorkflowEnvironment,
    db_path: Path,
    adapter: FakeAdapter,
    dialled: None,
    survivors: Callable[..., Survivors],
    reset_cli: Callable[..., Any],
) -> None:
    """US2-S3: the scenario the story exists for.

    The epic is `RUNNING` and stays running for the whole of this test — nobody
    presses anything and nothing expires — so the old `described.status.name ==
    "RUNNING"` refusal fires and the operator is sent to Temporal. The pending
    row asserted before and after the reset is what pins the premise: the epic
    really was mid-escalation when the verb ran, not terminal a moment earlier.
    """
    plant = survivors("us1")
    script = RealNotifyWorld({"us1": ladder_fails()}, client=env.client)

    async with start_epic(env, script, graph=plant.graph) as handle:
        [row] = await until("the escalation row", lambda: pending(db_path) or None)

        outcome = await reset_cli(plant.graph_path)

        assert outcome.code == 0, outcome.stderr
        assert pending(db_path) == [row], "the epic was mid-escalation throughout"
        live = await handle.query(EpicWorkflow.epic_status)
        assert live.epic_state == EpicState.RUNNING

        assert not plant.worktrees["us1"].exists()
        [archive] = archived(plant.repo, "us1")
        assert "survivor_us1.py" in git(
            plant.repo, "ls-tree", "--name-only", archive
        )

        await handle.terminate()


# --- T014 / US2-S4 / FR-007: the control (plan trap 7) -----------------------


async def test_reset_still_refuses_an_epic_with_a_genuinely_running_node(
    env: WorkflowEnvironment,
    db_path: Path,
    adapter: FakeAdapter,
    dialled: None,
    survivors: Callable[..., Survivors],
    reset_cli: Callable[..., Any],
) -> None:
    """US2-S4: the refusal is correct in general; only the escalation case is wrong.

    Same verb, same epic id, same on-disk survivors as US2-S3 — the *only*
    difference is that the node is mid-attempt rather than parked on an
    answer. A widening keyed on the workflow's status instead of on what kind of
    child is alive passes US2-S3 and fails here, by yanking the worktree out
    from under a live agent.

    The refusal must also say what is running: an operator told only "no" cannot
    tell a stall from work in progress, which is how they end up reaching for
    `temporal workflow terminate` anyway.
    """
    plant = survivors("us1")
    script = RealNotifyWorld(
        {"us1": ladder_fails()},
        client=env.client,
        dispatch_delay_s={"us1": HELD_DISPATCH_S},
    )

    async with start_epic(env, script, graph=plant.graph) as handle:
        await wait_for_status(
            handle,
            # `.get`, because the epic's node map is empty until `resolve_graph`
            # returns — an epic that has not built its records yet is a third
            # thing, and waiting through it is what makes the premise "mid
            # attempt" rather than "somewhere in start-up".
            lambda status: getattr(status.nodes.get("us1"), "state", None)
            == NodeState.RUNNING,
            what="us1 genuinely in flight",
        )

        outcome = await reset_cli(plant.graph_path)

        assert outcome.code == 1
        assert "us1" in outcome.stderr, "the refusal must name what is running"
        assert WORKFLOW_ID in outcome.stderr
        assert plant.worktrees["us1"].exists(), "nothing may be touched on a refusal"
        assert ref_exists(plant.repo, f"refs/heads/{branch_name(EPIC_ID, 'us1')}")
        assert archived(plant.repo, "us1") == []

        await handle.terminate()


# --- T015 / US2-S5 / FR-008 --------------------------------------------------


def test_ending_the_node_and_ending_the_epic_are_distinguishable_choices() -> None:
    """US2-S5: three offered options, three meanings, no two the same.

    Asserted as the whole mapping rather than as "KILL_EPIC exists", because a
    fourth button wired to the same effect as `KILL` is exactly the failure this
    scenario is about: an operator who wants the epic gone should not have to
    kill nodes one at a time and then reach for Temporal.

    `PAUSE_EPIC` collapses into neither — it ends the node and *parks* the epic
    (`factory/workgraph/workflow.py`'s escalation branch), which is a third
    answer, not a spelling of one of the other two.
    """
    config = VerificationConfig()

    def ends_the_node(choice: EscalationChoice) -> bool:
        return next_action([], config, escalations=[choice]) == NextAction.KILLED

    meanings = {
        choice: (ends_the_node(choice), epic_effect(choice))
        for choice in DEFAULT_CHOICES
    }

    assert meanings == {
        EscalationChoice.RETRY: (False, EpicEffect.CONTINUE),
        EscalationChoice.KILL: (True, EpicEffect.CONTINUE),
        EscalationChoice.KILL_EPIC: (True, EpicEffect.END),
        EscalationChoice.PAUSE_EPIC: (True, EpicEffect.PAUSE),
    }
    assert len(set(meanings.values())) == len(meanings), "two buttons, one meaning"


def test_the_offered_buttons_read_as_four_distinct_answers() -> None:
    """US2-S5, as the operator meets it: the faces on the buttons.

    The mapping above is the factory's reading; this is the operator's. A
    correct mapping behind two identical labels is still an escalation that
    offers only answers the operator cannot tell apart, and the label is what
    they press on a phone with a failing build above it.
    """
    record = _escalation_record(list(DEFAULT_CHOICES))
    actions = escalation_actions(record)

    assert [action.payload.rsplit(":", 1)[-1] for action in actions] == [
        choice.value for choice in DEFAULT_CHOICES
    ]
    labels = [action.label for action in actions]
    assert len(set(labels)) == len(labels), "two buttons, one face"
    by_choice = dict(zip(DEFAULT_CHOICES, labels))
    assert "node" in by_choice[EscalationChoice.KILL].lower()
    assert "epic" in by_choice[EscalationChoice.KILL_EPIC].lower()
    assert by_choice[EscalationChoice.KILL] != by_choice[EscalationChoice.KILL_EPIC]


async def test_a_kill_epic_press_ends_the_epic_and_a_kill_press_does_not(
    env: WorkflowEnvironment, db_path: Path, adapter: FakeAdapter
) -> None:
    """US2-S5's other half: the distinction is real at runtime, both directions.

    Two epics, identical but for the button pressed. `KILL` ends `us1` and lets
    `us2` run to `MERGED`; `KILL_EPIC` ends the whole thing, `us2` included. One
    direction alone proves nothing — a `KILL` wired to kill the epic passes the
    `KILL_EPIC` half, and a `KILL_EPIC` wired to kill only the node passes the
    `KILL` half.
    """
    graph = make_graph([make_node("us1", "US1"), make_node("us2", "US2")])

    async def press(choice: EscalationChoice, workflow_id: str) -> Any:
        script = RealNotifyWorld(
            {"us1": ladder_fails(), "us2": [passing()]},
            client=env.client,
            dispatch_delay_s={"us2": HELD_DISPATCH_S},
        )
        async with start_epic(
            env, script, graph=graph, workflow_id=workflow_id, max_concurrent_nodes=2
        ) as handle:
            [row] = await until(
                "the escalation row",
                lambda: [r for r in pending(db_path) if r.node_id == "us1"] or None,
            )
            await env.client.get_workflow_handle(row.workflow_id).signal(
                SIGNAL_NAME, args=[row.escalation_id, choice.value]
            )
            return await handle.result()

    killed_node = await press(EscalationChoice.KILL, "epic-kill-node")
    killed_epic = await press(EscalationChoice.KILL_EPIC, "epic-kill-epic")

    assert killed_node.epic_state == EpicState.COMPLETED
    assert states(killed_node)["us1"] == NodeState.KILLED
    assert states(killed_node)["us2"] == NodeState.MERGED

    assert killed_epic.epic_state == EpicState.KILLED
    assert states(killed_epic)["us1"] == NodeState.KILLED
    assert states(killed_epic)["us2"] != NodeState.MERGED


#: The escalations table exactly as every store written before this story has
#: it: a `resolution` CHECK that has never heard of `KILL_EPIC`. Written out
#: here rather than read from git, so the migration is tested against a shape
#: rather than against whatever the file says today (`test_escalation_record`'s
#: posture for the 041 column, applied to the constraint).
_PRE_068_ESCALATIONS_DDL = """
CREATE TABLE schema_version (version INTEGER NOT NULL);
INSERT INTO schema_version (version) VALUES (6);

CREATE TABLE escalations (
    escalation_id  TEXT PRIMARY KEY,
    workflow_id    TEXT NOT NULL,
    epic_id        TEXT NOT NULL,
    node_id        TEXT NOT NULL,
    choices        TEXT NOT NULL,
    history_summary TEXT NOT NULL,
    delivered      INTEGER NOT NULL DEFAULT 0 CHECK (delivered IN (0, 1)),
    sent_at        TEXT NOT NULL,
    expires_at     TEXT NOT NULL,
    resolution     TEXT CHECK (resolution IN ('RETRY', 'KILL', 'PAUSE_EPIC', 'EXPIRED')),
    resolved_at    TEXT,
    resolved_via   TEXT CHECK (resolved_via IN ('BUTTON', 'TIMEOUT')),
    check_evidence TEXT NOT NULL DEFAULT '[]',
    CHECK ((resolution IS NULL) = (resolved_at IS NULL))
);

CREATE INDEX idx_esc_pending ON escalations (resolution) WHERE resolution IS NULL;
CREATE INDEX idx_esc_node    ON escalations (epic_id, node_id);

INSERT INTO escalations (
    escalation_id, workflow_id, epic_id, node_id, choices, history_summary,
    delivered, sent_at, expires_at, resolution, resolved_at
) VALUES (
    'deadbeef0068', 'epic-041-one-escalation', '041-one-escalation',
    'us3', '["RETRY", "KILL"]', 'a row written before KILL_EPIC existed',
    1, '2026-08-19T14:55:00Z', '2026-08-19T15:55:00Z', 'KILL',
    '2026-08-19T15:00:00Z'
);
"""


def test_a_store_written_before_this_story_can_record_a_kill_epic(
    tmp_path: Path,
) -> None:
    """FR-008 reaches the stores that already exist, rows intact.

    A button the operator can press and the store then refuses is worse than no
    button: it pages a human, takes their decision, and drops it at
    `settle_escalation` with an `IntegrityError`. Every
    `.factory/verification.db` in the world was written under the old CHECK, so
    the new value has to arrive by migration or not at all.

    The pre-existing row is asserted across on purpose: a rebuild that recreated
    the table and forgot to copy would pass a bare "can I insert KILL_EPIC now"
    check while having thrown the escalation history away. So are the indexes —
    SQLite carries them along with a renamed table, and a rebuild that left them
    on the old name would silently deoptimize `pending_escalations`, which is the
    query every operator surface drains through.
    """
    db_path = tmp_path / ".factory" / "verification.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    legacy = sqlite3.connect(db_path)
    try:
        legacy.executescript(_PRE_068_ESCALATIONS_DDL)
        legacy.commit()
    finally:
        legacy.close()

    with closing(store.connect(db_path)) as conn:
        store.insert_escalation(
            conn,
            EscalationRecord(
                escalation_id="0123456789ab",
                workflow_id=WORKFLOW_ID,
                epic_id=EPIC_ID,
                node_id="us1",
                choices=list(DEFAULT_CHOICES),
                history_summary="four attempts, all failing",
                sent_at="2026-08-20T00:00:00Z",
                expires_at="2026-08-20T01:00:00Z",
                delivered=True,
            ),
        )
        store.resolve_escalation(
            conn,
            "0123456789ab",
            EscalationChoice.KILL_EPIC,
            resolved_at="2026-08-20T00:05:00Z",
        )
        conn.commit()

        assert (
            store.get_escalation(conn, "0123456789ab").resolution
            == EscalationChoice.KILL_EPIC.value
        )
        carried = store.get_escalation(conn, "deadbeef0068")
        assert carried.resolution == EscalationChoice.KILL.value
        assert carried.history_summary == "a row written before KILL_EPIC existed"
        assert conn.execute("SELECT version FROM schema_version").fetchone() == (
            store.SCHEMA_VERSION,
        )
        indexed = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'index' AND tbl_name = 'escalations'"
            )
        }
        assert {"idx_esc_pending", "idx_esc_node"} <= indexed


# --- fixtures the tests above compose ----------------------------------------


def one_node() -> WorkGraph:
    return make_graph([make_node("us1", "US1")])


def _escalation_record(choices: list[EscalationChoice]) -> EscalationRecord:
    """One escalation row, as the renderer receives it from the store."""
    return EscalationRecord(
        escalation_id="0123456789ab",
        workflow_id=WORKFLOW_ID,
        epic_id=EPIC_ID,
        node_id="us1",
        choices=tuple(choices),
        history_summary="four attempts, all failing",
        delivered=True,
        sent_at="2026-08-20T00:00:00Z",
        expires_at="2026-08-20T01:00:00Z",
    )
