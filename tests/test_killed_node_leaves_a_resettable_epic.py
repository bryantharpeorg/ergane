"""068-US2: a killed node leaves an epic `ergane build reset` can act on.

Three defects compounded into a loop with no exit. US1 fixed the first (RETRY
now grants). This file is about the second and third halves of that loop:

- **`kill_epic` was a flag nobody read while an escalation was open.**
  `EpicWorkflow._escalate` awaited its child unconditionally, so an epic holding
  a stalled page ignored `ergane build kill` for up to `escalation_timeout_s`
  (an hour, by default) and the operator reached for `temporal workflow
  terminate`. FR-006.
- **`ergane build reset` refused any RUNNING epic**, and a stalled escalation is
  exactly what keeps one running — so the sanctioned recovery verb was
  unavailable in precisely the state it exists for. FR-007. The refusal is
  right in general and stays: `test_reset_refuses_an_epic_with_a_node_at_work`
  is this file's control, and widening the precondition by *status* rather than
  by *what kind of child is alive* would delete it (plan trap 7).
- **The menu had no way to end the epic.** `KILL` ends one node; `PAUSE_EPIC`
  parks the epic and ends the node. An operator who wanted the epic gone had to
  press KILL on every node's page in turn and then reach for Temporal anyway.
  FR-008 adds `KILL_EPIC`, and this file holds all three apart.

Nothing here fakes the lifecycle under test. The epic, the escalation children,
the notify activities and the store are real; the target repositories, their
worktrees and their branches are real git; the only fakes are the agent and the
socket, neither of which any claim here is about.

**Plan trap 8a, answered rather than left implicit.** US2 and US3 both declare
`depends_on: []` and both edit `factory/cli/nouns/build.py` — US3 the subparser
registrations, US2 the `_reset_epic` precondition — so at a concurrency above
one they would build against the same base in separate worktrees and land in
whichever order the queue picked. The plan offered two ways out and asked that
one be named in the diff. **The ordering option was taken, and by history rather
than by declaration: US3 landed first (`a76c0ee`), so this story is built on top
of it** — `reset` already resolves an epic id through `resolve_reset_graph`, and
nothing here touches a subparser. That is why the file is only edited by one
live node, and why `tests/test_build_verbs_take_an_epic_id.py` is US3's and is
not edited here.
"""
from __future__ import annotations

import asyncio
from contextlib import closing
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Iterator

import pytest
from temporalio.testing import WorkflowEnvironment

from factory.activities.notify_activities import (
    DEFAULT_CHOICES,
    expire_escalation,
    send_escalation,
)
from factory.activities.verify_activities import (
    ERGANE_VERIFICATION_DB_PATH_ENV,
    VERIFICATION_DB_PATH_ENV,
)
from factory.cli.errors import OperatorError
from factory.cli.nouns.build import (
    _reset_epic,
    nodes_at_work,
    nodes_awaiting_operator,
    reset_refusal,
)
from factory.env import ERGANE_ROOT_ENV, FACTORY_ROOT_ENV
from factory.notify.adapter import (
    ESCALATION_ADAPTER_ENV,
    register_adapter,
    unregister_adapter,
)
from factory.notify.messages import callback_data, parse_callback_data
from factory.notify.messages import escalation_actions
from factory.notify.service import (
    SIGNAL_NAME,
    TEMPORAL_ADDRESS_ENV,
    TEMPORAL_NAMESPACE_ENV,
)
from factory.verify import store
from factory.verify.models import EscalationChoice, EscalationRecord
from factory.workgraph.models import EpicState, NodeState, WorkGraph
from factory.workgraph.workflow import EpicWorkflow
from factory.workgraph.worktree import branch_name, ensure, worktree_path

from tests.test_interpreter import (
    EPIC_ID,
    ScriptedWorld,
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

#: Polls are wall-clock: time skipping advances only while a workflow *result*
#: is awaited, so waiting for a store row never burns an escalation's hour.
POLL_STEP_S = 0.02
POLL_TRIES = 1500

#: The notify activities that must be real here: every claim in this file is
#: about the rows they write and the children they close, and a fake writes
#: none.  `settle_escalation` is already real in the scripted world.
REAL = frozenset("send_escalation expire_escalation".split())


class RealEscalationWorld(ScriptedWorld):
    """The scripted epic, with the escalation lifecycle for real."""

    def activities(self) -> list[Any]:
        kept = [fn for fn in super().activities() if fn.__name__ not in REAL]
        return [*kept, send_escalation, expire_escalation]


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


@pytest.fixture
def survivors(
    target_repo: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[WorkGraph, Path, Path, dict[str, Path]]:
    """A real target repo with a dirty worktree per node, and the epic's graph.

    Shaped like `tests/test_ergane_build.py::_make_reset_target`, because
    `reset` is the same verb and the claim here is about its precondition
    rather than about its effect on git.  The graph names the *interpreter*
    suite's epic id, so the workflow the epic runs under and the workflow
    `_reset_epic` looks for are the same one without either side deriving it.
    """
    repo = target_repo("passing")
    factory_root = tmp_path / ".factory-root"
    monkeypatch.setenv(ERGANE_ROOT_ENV, str(factory_root))
    monkeypatch.delenv(FACTORY_ROOT_ENV, raising=False)

    worktrees: dict[str, Path] = {}
    for node_id in ("us1", "us2"):
        prepared = ensure(repo, EPIC_ID, node_id, factory_root=factory_root)
        worktree = Path(prepared.path)
        worktrees[node_id] = worktree
        (worktree / f"added_by_{node_id}.py").write_text(
            f"VALUE_{node_id} = 1\n", encoding="utf-8"
        )
    graph = make_graph(
        [make_node("us1", "US1"), make_node("us2", "US2")],
        target_repo=str(repo),
    )
    return graph, repo, factory_root, worktrees


# --- helpers -----------------------------------------------------------------


def read(db_path: Path, reader: Any, *args: Any) -> Any:
    with closing(store.connect(db_path)) as conn:
        return reader(conn, *args)


def pending(db_path: Path) -> list[Any]:
    return read(db_path, store.pending_escalations)


async def until(what: str, predicate: Any) -> Any:
    """Poll a store-backed predicate until it is true, in real time."""
    for _ in range(POLL_TRIES):
        found = predicate()
        if found:
            return found
        await asyncio.sleep(POLL_STEP_S)
    raise AssertionError(f"never observed: {what}")


def ladder_fails() -> list[Any]:
    """The script that exhausts a node into an escalation."""
    return [failing(n) for n in (1, 2, 3, 4)]


async def press(env: WorkflowEnvironment, row: Any, choice: EscalationChoice) -> None:
    """Answer one escalation through the row's own workflow, as a button does."""
    await env.client.get_workflow_handle(row.workflow_id).signal(
        SIGNAL_NAME, args=[row.escalation_id, choice.value]
    )


async def child_status(env: WorkflowEnvironment, workflow_id: str) -> str:
    described = await env.client.get_workflow_handle(workflow_id).describe()
    assert described.status is not None
    return described.status.name


def reset_effect(repo: Path, factory_root: Path, worktrees: dict[str, Path]) -> None:
    """Assert reset did what reset does, for every node of the graph.

    The effect, not the exit status: a `reset` that returned 0 and archived
    nothing is the failure US2-S2 names in as many words ("the reset effect,
    not merely that no exception was raised").
    """
    from tests.test_ergane_build import ref_exists

    for node_id, worktree in worktrees.items():
        assert not worktree.exists(), f"{node_id}: worktree not removed"
        sidecar = factory_root / "worktrees" / EPIC_ID / f"{node_id}.json"
        assert not sidecar.exists(), f"{node_id}: sidecar not removed"
        assert not ref_exists(repo, f"refs/heads/{branch_name(EPIC_ID, node_id)}"), (
            f"{node_id}: node branch not archived"
        )


# --- T015 / US2-S5 / FR-008: three answers, three different things ----------


def offered_record() -> EscalationRecord:
    """One escalation offering whatever the ladder offers when nothing narrows it."""
    return EscalationRecord(
        escalation_id="0123456789ab",
        workflow_id="escalation-0123456789ab",
        epic_id=EPIC_ID,
        node_id="us1",
        choices=list(DEFAULT_CHOICES),
        history_summary="attempt 4: gates failed",
        sent_at="2026-08-20T11:00:00Z",
        expires_at="2026-08-20T12:00:00Z",
        delivered=True,
    )


def test_the_menu_offers_ending_the_node_and_ending_the_epic_as_two_buttons() -> None:
    """US2-S5, the menu half: two presses, not one press applied twice.

    Read off the rendered buttons and decoded back through the callback grammar
    rather than off `DEFAULT_CHOICES`, because what reaches the ladder is the
    payload a press carries: a menu whose two faces encode the same choice is
    the defect this story is about, and comparing the enum to itself would
    never see it.
    """
    actions = escalation_actions(offered_record())
    decoded = []
    for action in actions:
        pressed = parse_callback_data(action.payload)
        assert pressed is not None, action.label
        decoded.append(pressed.choice)

    assert decoded == ["RETRY", "KILL", "PAUSE_EPIC", "KILL_EPIC"]

    # Distinct payloads and distinct faces. An operator reading these on a phone
    # decides an epic's fate from the label alone.
    assert len({action.payload for action in actions}) == len(actions)
    labels = [action.label for action in actions]
    assert len(set(labels)) == len(labels), labels
    faces = dict(zip(decoded, labels))
    assert faces["KILL"] != faces["KILL_EPIC"]
    assert "node" in faces["KILL"] and "epic" in faces["KILL_EPIC"]

    # PAUSE_EPIC is a third thing and is spelled as one (spec § Edge Cases): it
    # must collapse into neither of the two the story distinguishes.
    assert faces["PAUSE_EPIC"] not in (faces["KILL"], faces["KILL_EPIC"])
    assert callback_data("0123456789ab", EscalationChoice.PAUSE_EPIC) not in (
        callback_data("0123456789ab", EscalationChoice.KILL),
        callback_data("0123456789ab", EscalationChoice.KILL_EPIC),
    )


async def test_kill_ends_the_node_kill_epic_ends_the_epic_and_pause_ends_neither(
    env: WorkflowEnvironment, db_path: Path, adapter: FakeAdapter
) -> None:
    """US2-S5, the effect half: the three answers produce three epic outcomes.

    The menu-level test above proves the buttons differ. This proves what an
    operator actually buys with each, on the same graph and the same script:

    - `KILL` ends **the node**. `us2` — which has not dispatched, because the
      scheduler is at one node at a time — still runs, and the epic COMPLETES.
    - `KILL_EPIC` ends **the epic**. `us2` never dispatches at all and the epic
      is KILLED.
    - `PAUSE_EPIC` ends neither: the epic is PAUSED, `us2` is still PENDING and
      a resume would still run it.

    `us2`'s terminal state is the discriminator that a label cannot fake.
    """
    graph = make_graph([make_node("us1", "US1"), make_node("us2", "US2")])

    # --- KILL: the node dies, the epic carries on.
    script = RealEscalationWorld(
        {"us1": ladder_fails(), "us2": [passing()]}, client=env.client
    )
    async with start_epic(
        env, script, graph=graph, workflow_id="epic-kill-the-node"
    ) as handle:
        [row] = await until("us1's escalation", lambda: pending(db_path) or None)
        await press(env, row, EscalationChoice.KILL)
        killed_node = await handle.result()

    assert states(killed_node)["us1"] == NodeState.KILLED
    assert states(killed_node)["us2"] == NodeState.MERGED, (
        "KILL must end the node only; us2 never got its turn"
    )
    assert killed_node.epic_state == EpicState.COMPLETED

    # --- KILL_EPIC: the epic dies, and takes the undispatched node with it.
    script = RealEscalationWorld(
        {"us1": ladder_fails(), "us2": [passing()]}, client=env.client
    )
    async with start_epic(
        env, script, graph=graph, workflow_id="epic-kill-the-epic"
    ) as handle:
        [row] = await until(
            "us1's escalation", lambda: [r for r in pending(db_path)] or None
        )
        await press(env, row, EscalationChoice.KILL_EPIC)
        killed_epic = await handle.result()

    assert killed_epic.epic_state == EpicState.KILLED
    assert states(killed_epic)["us1"] == NodeState.KILLED
    assert states(killed_epic)["us2"] == NodeState.KILLED
    assert killed_epic.nodes["us2"].attempt == 0, "us2 must never have dispatched"

    # --- PAUSE_EPIC: neither. The epic parks with us2 still ahead of it.
    script = RealEscalationWorld(
        {"us1": ladder_fails(), "us2": [passing()]}, client=env.client
    )
    async with start_epic(
        env, script, graph=graph, workflow_id="epic-pause-the-epic"
    ) as handle:
        [row] = await until(
            "us1's escalation", lambda: [r for r in pending(db_path)] or None
        )
        await press(env, row, EscalationChoice.PAUSE_EPIC)
        paused = await wait_for_status(
            handle,
            lambda status: status.epic_state == EpicState.PAUSED,
            what="the epic parked rather than ended",
            timeout=30.0,
        )
        assert states(paused)["us1"] == NodeState.FAILED
        assert states(paused)["us2"] == NodeState.PENDING
        assert paused.epic_state not in (EpicState.KILLED, EpicState.COMPLETED)
        await handle.signal(EpicWorkflow.kill_epic)
        await handle.result()


# --- T011 / US2-S1 / FR-006: no living escalation child ---------------------


async def test_a_node_killed_from_an_escalation_leaves_no_living_child(
    env: WorkflowEnvironment, db_path: Path, adapter: FakeAdapter
) -> None:
    """US2-S1: the epic holds no living escalation child once the node is killed.

    Asserted against Temporal's own view of the child execution, not against the
    store: a settled row and a running workflow are exactly the combination that
    strands an epic, so the row is the weaker claim and is checked as well.
    """
    script = RealEscalationWorld({"us1": ladder_fails()}, client=env.client)
    graph = make_graph([make_node("us1", "US1")])

    async with start_epic(env, script, graph=graph) as handle:
        [row] = await until("us1's escalation", lambda: pending(db_path) or None)
        assert await child_status(env, row.workflow_id) == "RUNNING"
        await press(env, row, EscalationChoice.KILL)
        result = await handle.result()

        assert await child_status(env, row.workflow_id) != "RUNNING"

    assert states(result)["us1"] == NodeState.KILLED
    assert pending(db_path) == [], "no escalation may outlive the node it paged for"
    settled = read(db_path, store.get_escalation, row.escalation_id)
    assert settled.resolution == EscalationChoice.KILL.value


async def test_killing_the_epic_cancels_a_sibling_s_open_escalation(
    env: WorkflowEnvironment, db_path: Path, adapter: FakeAdapter
) -> None:
    """FR-006's hard half: the page nobody answered dies with the epic.

    `kill_epic` set a flag that neither `_escalate` nor `_escalate_landing`
    read, so an epic holding an open page ignored the operator's stop for up to
    `escalation_timeout_s` — an hour — and `ergane build kill` looked broken.
    Two nodes escalate at once; one press ends the epic; the other node's child
    must be gone within the test's seconds rather than the child's hour.

    Its row stays PENDING on purpose: a stopped epic is neither a press nor a
    burn, and writing `KILL` there would be pressing a button on the operator's
    behalf.
    """
    script = RealEscalationWorld(
        {"us1": ladder_fails(), "us2": ladder_fails()}, client=env.client
    )
    graph = make_graph([make_node("us1", "US1"), make_node("us2", "US2")])

    async with start_epic(
        env, script, graph=graph, max_concurrent_nodes=2
    ) as handle:
        both = await until(
            "two escalations open at once",
            lambda: pending(db_path) if len(pending(db_path)) == 2 else None,
        )
        rows = {row.node_id: row for row in both}
        await press(env, rows["us1"], EscalationChoice.KILL_EPIC)
        result = await handle.result()

        assert await child_status(env, rows["us2"].workflow_id) != "RUNNING"

    assert result.epic_state == EpicState.KILLED
    assert states(result) == {"us1": NodeState.KILLED, "us2": NodeState.KILLED}
    unanswered = read(db_path, store.get_escalation, rows["us2"].escalation_id)
    assert unanswered.resolution is None, (
        "a stopped epic must not answer the operator's own question for them"
    )


# --- T014 / US2-S4: the control — a working node still refuses --------------


async def test_reset_refuses_an_epic_with_a_node_at_work(
    env: WorkflowEnvironment,
    db_path: Path,
    adapter: FakeAdapter,
    dialled: None,
    survivors: tuple[WorkGraph, Path, Path, dict[str, Path]],
) -> None:
    """US2-S4, the control (plan trap 7): reset still refuses live work, by name.

    A reset that succeeds against a genuinely running epic interrupts an agent
    mid-attempt and archives the tree it is writing to. Widening the
    precondition by loosening the status test rather than by asking what kind of
    child is alive deletes this guard, so it is asserted the strict way: the
    refusal names the node that is working, and nothing on disk is touched.
    """
    graph, repo, factory_root, worktrees = survivors
    script = RealEscalationWorld(
        {"us1": [passing()], "us2": [passing()]},
        client=env.client,
        dispatch_delay_s={"us1": 3.0},
    )

    async with start_epic(env, script, graph=graph) as handle:
        await wait_for_status(
            handle,
            lambda status: (
                status.nodes.get("us1") is not None
                and status.nodes["us1"].state == NodeState.RUNNING
            ),
            what="us1 dispatched and working",
            timeout=30.0,
        )
        with pytest.raises(OperatorError) as refusal:
            await _reset_epic(graph)

        assert "us1" in str(refusal.value), str(refusal.value)
        assert f"epic-{EPIC_ID}" in str(refusal.value)

        for node_id, worktree in worktrees.items():
            assert worktree.exists(), f"{node_id}: reset touched a live worktree"
            assert (
                factory_root / "worktrees" / EPIC_ID / f"{node_id}.json"
            ).exists()

        await handle.signal(EpicWorkflow.kill_epic)
        await handle.result()


# --- T013 / US2-S3: the deadlock's own shape --------------------------------


async def test_reset_succeeds_when_the_only_living_child_is_a_stalled_escalation(
    env: WorkflowEnvironment,
    db_path: Path,
    adapter: FakeAdapter,
    dialled: None,
    survivors: tuple[WorkGraph, Path, Path, dict[str, Path]],
) -> None:
    """US2-S3: the scenario the story exists for.

    The epic is RUNNING, and the only reason it is RUNNING is that a human has
    not answered a page. Nothing is dispatching, nothing is writing to a
    worktree, and the operator has decided to give up — so `reset` must archive
    the survivors rather than refuse for an activity that is really a wait.
    """
    graph, repo, factory_root, worktrees = survivors
    script = RealEscalationWorld(
        {"us1": ladder_fails(), "us2": [passing()]}, client=env.client
    )

    async with start_epic(env, script, graph=graph) as handle:
        [row] = await until("us1's escalation", lambda: pending(db_path) or None)
        stalled = await handle.query(EpicWorkflow.epic_status)
        assert stalled.epic_state == EpicState.RUNNING, (
            "the epic must really be running, or this proves nothing"
        )

        assert await _reset_epic(graph) == 0
        reset_effect(repo, factory_root, worktrees)

        # The page is still the operator's to answer or ignore: reset archives,
        # it does not press (spec § Assumptions).
        assert read(db_path, store.get_escalation, row.escalation_id).resolution is None

        await handle.signal(EpicWorkflow.kill_epic)
        await handle.result()


# --- T012 / US2-S2: kill from an escalation, then reset ---------------------


async def test_reset_succeeds_against_an_epic_whose_node_was_killed_from_a_page(
    env: WorkflowEnvironment,
    db_path: Path,
    adapter: FakeAdapter,
    dialled: None,
    survivors: tuple[WorkGraph, Path, Path, dict[str, Path]],
) -> None:
    """US2-S2 and SC-003: press KILL_EPIC, then run reset — no Temporal surgery.

    The whole closed loop, end to end and in the order an operator meets it.
    Exit status *and* effect, because a `reset` that returns 0 having archived
    nothing satisfies neither the scenario nor the operator.
    """
    graph, repo, factory_root, worktrees = survivors
    script = RealEscalationWorld(
        {"us1": ladder_fails(), "us2": [passing()]}, client=env.client
    )

    async with start_epic(env, script, graph=graph) as handle:
        [row] = await until("us1's escalation", lambda: pending(db_path) or None)
        await press(env, row, EscalationChoice.KILL_EPIC)
        result = await handle.result()

    assert result.epic_state == EpicState.KILLED
    assert pending(db_path) == []

    assert await _reset_epic(graph) == 0
    reset_effect(repo, factory_root, worktrees)


# --- the precondition itself, read as a function ----------------------------


def status_document(**nodes: dict[str, Any]) -> dict[str, Any]:
    """An `epic_status` answer in the shape the query hands the CLI: plain JSON."""
    return {"epic_state": "RUNNING", "nodes": dict(nodes)}


def test_the_precondition_separates_work_from_waiting() -> None:
    """FR-007 as a table, so the two halves cannot be read as one.

    The CLI reads the query's raw document rather than a typed result — an epic
    whose history predates a field still answers — so the reading is asserted
    against that shape, strings and all.
    """
    document = status_document(
        us1={"state": "VERIFYING", "awaiting_operator": True},
        us2={"state": "RUNNING", "awaiting_operator": False},
        us3={"state": "WAITING_OPERATOR", "awaiting_operator": True},
        us4={"state": "KILLED", "awaiting_operator": False},
        us5={"state": "PENDING", "awaiting_operator": False},
    )

    assert nodes_at_work(document) == ("us2",)
    assert nodes_awaiting_operator(document) == ("us1", "us3")

    # A node parked on a page is not work; a node with the same state and no
    # page is. That difference is the whole widening.
    paged = status_document(us1={"state": "VERIFYING", "awaiting_operator": True})
    working = status_document(us1={"state": "VERIFYING", "awaiting_operator": False})
    assert nodes_at_work(paged) == ()
    assert nodes_at_work(working) == ("us1",)

    # A document from a worker that predates the field reads as "at work",
    # which is the safe answer: reset refuses rather than archiving under an
    # epic it cannot interrogate.
    old = status_document(us1={"state": "VERIFYING"})
    assert nodes_at_work(old) == ("us1",)


def test_a_running_epic_is_reset_only_when_it_is_waiting_on_a_human() -> None:
    """FR-007's rule, both directions, as a table over the whole decision.

    `nodes_at_work` on its own would widen too far: an epic that has started and
    not yet dispatched reports no work either, and archiving the worktrees it is
    about to prepare is the race the old blanket refusal accidentally prevented.
    So the rule needs a waiter present, not merely work absent — and asserting
    the two halves separately is what stops one of them being deleted.
    """
    stalled = status_document(
        us1={"state": "VERIFYING", "awaiting_operator": True},
        us2={"state": "PENDING", "awaiting_operator": False},
    )
    assert reset_refusal(EPIC_ID, stalled) is None, "the deadlock's own shape"

    live = status_document(
        us1={"state": "VERIFYING", "awaiting_operator": True},
        us2={"state": "RUNNING", "awaiting_operator": False},
    )
    refused = reset_refusal(EPIC_ID, live)
    assert refused is not None and "us2" in refused, refused
    assert "us1" not in refused, "the waiting node is not what is refused for"

    # Started, nothing dispatched, nobody paged: still a refusal, and the same
    # sentence the verb has always printed.
    fresh = status_document(us1={"state": "PENDING", "awaiting_operator": False})
    assert reset_refusal(EPIC_ID, fresh) == (
        f"epic '{EPIC_ID}' is running (workflow id epic-{EPIC_ID}); "
        "refusing to reset while the workflow is active"
    )
    assert reset_refusal(EPIC_ID, {"nodes": {}}) is not None, (
        "an epic that has reported no node at all has not said it is idle"
    )


# --- the store has to admit the fourth answer ------------------------------


#: The `escalations` table exactly as every store in the world holds it today:
#: `resolution` CHECK-pinned to the three buttons that existed before this
#: story, plus `EXPIRED`.
_PRE_068_ESCALATIONS_DDL = """
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

INSERT INTO escalations (
    escalation_id, workflow_id, epic_id, node_id, choices, history_summary,
    delivered, sent_at, expires_at, resolution, resolved_at, resolved_via
) VALUES (
    'deadbeef0068', 'escalation-deadbeef0068', 'demo-loans', 'us1',
    '["RETRY", "KILL"]', 'a row written before the fourth button existed',
    1, '2026-08-19T14:55:00Z', '2026-08-19T15:55:00Z',
    'KILL', '2026-08-19T15:00:00Z', 'BUTTON'
);
"""


def test_an_existing_store_learns_to_hold_the_new_answer(tmp_path: Path) -> None:
    """FR-008's other half: a button the store rejects is a button that does nothing.

    The choice rides into `settle_escalation` as text and lands in a column
    whose CHECK constraint predates it, and SQLite cannot alter a CHECK — so
    without the rebuild, `KILL_EPIC` renders, sends, is pressed, and then fails
    the write. The escalation stays pending and the epic stays exactly where the
    press was meant to get it out of, which is the defect wearing a new hat.

    Asserted by writing the value, not by reading the DDL: the constraint is
    only interesting because of what it refuses.
    """
    import sqlite3

    db = tmp_path / "verification.db"
    old = sqlite3.connect(db)
    try:
        old.executescript(_PRE_068_ESCALATIONS_DDL)
        old.commit()
    finally:
        old.close()

    with closing(store.connect(db)) as migrated:
        migrated.execute(
            "INSERT INTO escalations (escalation_id, workflow_id, epic_id, "
            "node_id, choices, history_summary, delivered, sent_at, expires_at, "
            "resolution, resolved_at, resolved_via) VALUES "
            "(?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, 'BUTTON')",
            (
                "0123456789ab",
                "escalation-0123456789ab",
                EPIC_ID,
                "us2",
                '["RETRY", "KILL", "PAUSE_EPIC", "KILL_EPIC"]',
                "the epic the operator ended",
                "2026-08-20T11:00:00Z",
                "2026-08-20T12:00:00Z",
                EscalationChoice.KILL_EPIC.value,
                "2026-08-20T11:05:00Z",
            ),
        )
        written = store.get_escalation(migrated, "0123456789ab")
        assert written is not None
        assert written.resolution == EscalationChoice.KILL_EPIC.value

        # The rebuild is a copy, so the row that was already there survives it
        # whole — a migration that lost a settled escalation would be a worse
        # outage than the one this story fixes.
        kept = store.get_escalation(migrated, "deadbeef0068")
        assert kept is not None
        assert kept.resolution == EscalationChoice.KILL.value
        assert kept.history_summary == "a row written before the fourth button existed"
        assert kept.check_evidence == ()

        # Still closed against everything that is not an answer.
        with pytest.raises(sqlite3.IntegrityError):
            migrated.execute(
                "UPDATE escalations SET resolution = 'KILL_THE_WHOLE_FACTORY' "
                "WHERE escalation_id = ?",
                ("0123456789ab",),
            )


# --- runtime evidence, pasted verbatim (constitution VIII / D-037) ----------
#
# Filled in by the implementation commit.
