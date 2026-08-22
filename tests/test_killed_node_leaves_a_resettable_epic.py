"""068-US2: a killed node leaves an epic `ergane build reset` can act on.

US1 fixed the first of three compounding defects (RETRY now grants); these are
the other two and the missing answer that made them inescapable.

**FR-006**: both escalation paths awaited their child unconditionally, so
`kill_epic` was a flag nobody read — an epic holding a stalled page ignored
`ergane build kill` for the whole of `escalation_timeout_s`, an hour, and the
operator used `temporal workflow terminate`. **FR-007**: `reset` refused any
RUNNING epic, and a stalled escalation is what keeps one running, so the
recovery verb was unavailable in the one state it exists for. That refusal is
right in general and stays — `test_reset_refuses_an_epic_with_a_node_at_work`
is the control, and keying the widening on *status* rather than on *what kind
of child is alive* deletes it (plan trap 7). **FR-008**: the menu had no way to
end the epic, so wanting one gone meant pressing KILL on every node's page and
reaching for Temporal anyway.

Nothing here fakes the lifecycle under test — epic, escalation children, notify
activities, store, and target repos with real git worktrees and branches. The
world that arranges them is 041-US3's rather than a second copy: `env`,
`db_path`, `adapter`, `dialled`, `RealNotifyWorld` and the store readers come
from `tests/test_epic_escalation_child.py`.

**Plan trap 8a** asked which remedy was taken for US2 and US3 both editing
`factory/cli/nouns/build.py`: **ordering, by history — US3 landed first
(`a76c0ee`), so this builds on it.** `reset` already takes an epic id through
`resolve_reset_graph`, nothing here touches a subparser, and
`tests/test_build_verbs_take_an_epic_id.py` is US3's and is not edited.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest
from temporalio.testing import WorkflowEnvironment

from factory.activities.notify_activities import DEFAULT_CHOICES
from factory.cli.errors import OperatorError
from factory.cli.nouns.build import (
    _reset_epic,
    nodes_at_work,
    nodes_awaiting_operator,
    reset_refusal,
)
from factory.env import ERGANE_ROOT_ENV, FACTORY_ROOT_ENV
from factory.notify.messages import (
    callback_data,
    escalation_actions,
    parse_callback_data,
)
from factory.notify.service import SIGNAL_NAME
from factory.verify import store
from factory.verify.models import EscalationChoice, EscalationRecord
from factory.workgraph.models import EpicState, NodeState, WorkGraph
from factory.workgraph.workflow import EpicWorkflow
from factory.workgraph.worktree import branch_name, ensure

from tests.test_epic_escalation_child import (  # noqa: F401 — pytest fixtures
    FakeAdapter,
    RealNotifyWorld,
    adapter,
    db_path,
    dialled,
    env,
    ladder_fails,
    pending,
    read,
    until,
)
from tests.test_ergane_build import ref_exists
from tests.test_interpreter import (
    EPIC_ID,
    make_graph,
    make_node,
    passing,
    start_epic,
    states,
    wait_for_status,
)

Survivors = tuple[WorkGraph, Path, Path, dict[str, Path]]


@pytest.fixture
def survivors(
    target_repo: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Survivors:
    """A real target repo with a dirty worktree per node, and the epic's graph.

    Shaped like `tests/test_ergane_build.py::_make_reset_target`, keeping the
    interpreter epic id so the workflow the epic runs under and the one
    `_reset_epic` looks for are the same without either deriving it.
    """
    repo = target_repo("passing")
    factory_root = tmp_path / ".factory-root"
    monkeypatch.setenv(ERGANE_ROOT_ENV, str(factory_root))
    monkeypatch.delenv(FACTORY_ROOT_ENV, raising=False)

    worktrees: dict[str, Path] = {}
    for node_id in ("us1", "us2"):
        worktrees[node_id] = Path(
            ensure(repo, EPIC_ID, node_id, factory_root=factory_root).path
        )
        (worktrees[node_id] / f"by_{node_id}.py").write_text("V = 1\n", encoding="utf-8")
    graph = make_graph(
        [make_node("us1", "US1"), make_node("us2", "US2")], target_repo=str(repo)
    )
    return graph, repo, factory_root, worktrees


def resolution_of(db_path: Path, escalation_id: str) -> Any:
    return read(db_path, store.get_escalation, escalation_id).resolution


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
    """The effect, not the exit status — US2-S2 names that distinction itself."""
    for node_id, worktree in worktrees.items():
        assert not worktree.exists(), f"{node_id}: worktree not removed"
        sidecar = factory_root / "worktrees" / EPIC_ID / f"{node_id}.json"
        assert not sidecar.exists(), f"{node_id}: sidecar not removed"
        branch = f"refs/heads/{branch_name(EPIC_ID, node_id)}"
        assert not ref_exists(repo, branch), f"{node_id}: branch not archived"


# --- T015 / US2-S5 / FR-008: three answers, three different things ----------


def test_the_menu_offers_ending_the_node_and_ending_the_epic_as_two_buttons() -> None:
    """US2-S5, the menu half: two presses, not one press applied twice.

    Decoded off the rendered buttons rather than read from `DEFAULT_CHOICES`,
    because the payload is what reaches the ladder — a menu whose two faces
    encode one choice is this story's shape, and comparing the enum to itself
    would never see it.
    """
    actions = escalation_actions(
        EscalationRecord(
            "0123456789ab", "escalation-0123456789ab", EPIC_ID, "us1",
            list(DEFAULT_CHOICES), "attempt 4: gates failed",
            "2026-08-20T11:00:00Z", "2026-08-20T12:00:00Z", delivered=True,
        )
    )
    decoded = [parse_callback_data(a.payload) for a in actions]
    assert all(press is not None for press in decoded), actions
    assert [p.choice for p in decoded] == ["RETRY", "KILL", "PAUSE_EPIC", "KILL_EPIC"]

    # Distinct payloads and faces: an operator on a phone decides an epic's
    # fate from the label alone.
    faces = {p.choice: a.label for p, a in zip(decoded, actions)}
    assert len({a.payload for a in actions}) == len(actions)
    assert len(set(faces.values())) == len(actions), faces
    assert "node" in faces["KILL"] and "epic" in faces["KILL_EPIC"]

    # PAUSE_EPIC is a third thing and is spelled as one (spec § Edge Cases): it
    # must collapse into neither of the two the story distinguishes.
    payload = lambda choice: callback_data("0123456789ab", choice)
    assert faces["PAUSE_EPIC"] not in (faces["KILL"], faces["KILL_EPIC"])
    assert payload(EscalationChoice.PAUSE_EPIC) not in (
        payload(EscalationChoice.KILL),
        payload(EscalationChoice.KILL_EPIC),
    )


async def test_kill_ends_the_node_kill_epic_ends_the_epic_and_pause_ends_neither(
    env: WorkflowEnvironment, db_path: Path, adapter: FakeAdapter
) -> None:
    """US2-S5, the effect half: three answers, three epic outcomes.

    One graph, one script. `KILL` ends **the node** — `us2`, undispatched because
    the scheduler runs one at a time, still gets its turn and the epic COMPLETES.
    `KILL_EPIC` ends **the epic**: `us2` never dispatches. `PAUSE_EPIC` ends
    neither — PAUSED, `us2` still PENDING ahead of a resume. `us2`'s terminal
    state is the discriminator a label cannot fake.

    079-US4 changed what `us1` reads as under the third press: parked on the
    operator rather than `FAILED`, because `FAILED` is in `_UNREACHABLE` and the
    press was killing this graph's dependents too (`tests/test_pause_is_not_a_
    kill.py`). `us2` was already PENDING here — it depends on nothing — which is
    why this test never saw the defect and why the one that does is separate.
    """
    graph = make_graph([make_node("us1", "US1"), make_node("us2", "US2")])

    async def answered_with(choice: EscalationChoice, workflow_id: str) -> Any:
        script = RealNotifyWorld(
            {"us1": ladder_fails(), "us2": [passing()]}, client=env.client
        )
        async with start_epic(
            env, script, graph=graph, workflow_id=workflow_id
        ) as handle:
            [row] = await until("us1's escalation", lambda: pending(db_path) or None)
            await press(env, row, choice)
            if choice is not EscalationChoice.PAUSE_EPIC:
                return await handle.result()
            # A paused epic never completes: read it, then stop it so the
            # worker can shut down.
            parked = await wait_for_status(
                handle,
                lambda status: status.epic_state == EpicState.PAUSED,
                what="the epic parked rather than ended",
                timeout=30.0,
            )
            await handle.signal(EpicWorkflow.kill_epic)
            await handle.result()
            return parked

    node = await answered_with(EscalationChoice.KILL, "epic-kill-the-node")
    assert node.epic_state == EpicState.COMPLETED
    assert states(node) == {"us1": NodeState.KILLED, "us2": NodeState.MERGED}, (
        "KILL ends the node only; us2 must still get its turn"
    )

    epic = await answered_with(EscalationChoice.KILL_EPIC, "epic-kill-the-epic")
    assert epic.epic_state == EpicState.KILLED
    assert states(epic) == {"us1": NodeState.KILLED, "us2": NodeState.KILLED}
    assert epic.nodes["us2"].attempt == 0, "us2 must never have dispatched"

    parked = await answered_with(EscalationChoice.PAUSE_EPIC, "epic-pause-the-epic")
    assert parked.epic_state == EpicState.PAUSED
    assert parked.epic_state not in (EpicState.KILLED, EpicState.COMPLETED)
    assert states(parked) == {
        "us1": NodeState.WAITING_OPERATOR,
        "us2": NodeState.PENDING,
    }


# --- T011 / US2-S1 / FR-006: no living escalation child ---------------------


async def test_a_node_killed_from_an_escalation_leaves_no_living_child(
    env: WorkflowEnvironment, db_path: Path, adapter: FakeAdapter
) -> None:
    """US2-S1: no living escalation child once the node is killed.

    Against Temporal's view of the child execution as well as the row: a settled
    row beside a running workflow is exactly the combination that strands an
    epic, so the row alone is the weaker claim.
    """
    script = RealNotifyWorld({"us1": ladder_fails()}, client=env.client)

    async with start_epic(
        env, script, graph=make_graph([make_node("us1", "US1")])
    ) as handle:
        [row] = await until("us1's escalation", lambda: pending(db_path) or None)
        assert await child_status(env, row.workflow_id) == "RUNNING"
        await press(env, row, EscalationChoice.KILL)
        result = await handle.result()
        assert await child_status(env, row.workflow_id) != "RUNNING"

    assert states(result)["us1"] == NodeState.KILLED
    assert pending(db_path) == [], "no escalation may outlive the node it paged for"
    assert resolution_of(db_path, row.escalation_id) == EscalationChoice.KILL.value


async def test_killing_the_epic_cancels_a_sibling_s_open_escalation(
    env: WorkflowEnvironment, db_path: Path, adapter: FakeAdapter
) -> None:
    """FR-006's hard half: the page nobody answered dies with the epic.

    Two nodes escalate at once and one press ends the epic; the other's child
    must be gone within the test's seconds rather than the child's hour. Its row
    stays PENDING on purpose — a stopped epic is neither a press nor a burn, and
    writing `KILL` there presses a button on the operator's behalf.
    """
    script = RealNotifyWorld(
        {"us1": ladder_fails(), "us2": ladder_fails()}, client=env.client
    )
    graph = make_graph([make_node("us1", "US1"), make_node("us2", "US2")])

    async with start_epic(env, script, graph=graph, max_concurrent_nodes=2) as handle:
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
    assert resolution_of(db_path, rows["us2"].escalation_id) is None, (
        "a stopped epic must not answer the operator's own question for them"
    )


# --- T014 / US2-S4: the control — a working node still refuses --------------


async def test_reset_refuses_an_epic_with_a_node_at_work(
    env: WorkflowEnvironment,
    db_path: Path,
    adapter: FakeAdapter,
    dialled: None,
    survivors: Survivors,
) -> None:
    """US2-S4, the control (plan trap 7): reset still refuses live work, by name.

    A reset under a running epic interrupts an agent mid-attempt and archives the
    tree it is writing to. Asserted the strict way, so loosening the status test
    cannot pass it: the refusal names the working node, nothing on disk moves.
    """
    graph, _repo, factory_root, worktrees = survivors
    script = RealNotifyWorld(
        {"us1": [passing()], "us2": [passing()]},
        client=env.client,
        dispatch_delay_s={"us1": 3.0},
    )

    async with start_epic(env, script, graph=graph) as handle:
        await wait_for_status(
            handle,
            lambda status: getattr(status.nodes.get("us1"), "state", None)
            == NodeState.RUNNING,
            what="us1 dispatched and working",
            timeout=30.0,
        )
        with pytest.raises(OperatorError) as refusal:
            await _reset_epic(graph)

        assert "us1" in str(refusal.value), str(refusal.value)
        assert f"epic-{EPIC_ID}" in str(refusal.value)
        for node_id, worktree in worktrees.items():
            assert worktree.exists(), f"{node_id}: reset touched a live worktree"
            assert (factory_root / "worktrees" / EPIC_ID / f"{node_id}.json").exists()

        await handle.signal(EpicWorkflow.kill_epic)
        await handle.result()


# --- T013 / US2-S3: the deadlock's own shape --------------------------------


async def test_reset_succeeds_when_the_only_living_child_is_a_stalled_escalation(
    env: WorkflowEnvironment,
    db_path: Path,
    adapter: FakeAdapter,
    dialled: None,
    survivors: Survivors,
) -> None:
    """US2-S3: the scenario the story exists for.

    The epic is RUNNING, and the only reason it is RUNNING is an unanswered page.
    Nothing dispatches, nothing writes to a worktree, and the operator has given
    up — so `reset` archives rather than refusing for a wait it read as activity.
    """
    graph, repo, factory_root, worktrees = survivors
    script = RealNotifyWorld(
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
        assert resolution_of(db_path, row.escalation_id) is None

        await handle.signal(EpicWorkflow.kill_epic)
        await handle.result()


# --- T012 / US2-S2: kill from an escalation, then reset ---------------------


async def test_reset_succeeds_against_an_epic_whose_node_was_killed_from_a_page(
    env: WorkflowEnvironment,
    db_path: Path,
    adapter: FakeAdapter,
    dialled: None,
    survivors: Survivors,
) -> None:
    """US2-S2 and SC-003: press KILL_EPIC, then reset — no Temporal surgery.

    The closed loop end to end, in the order an operator meets it. Exit status
    *and* effect: a reset that returns 0 having archived nothing satisfies
    neither the scenario nor the operator.
    """
    graph, repo, factory_root, worktrees = survivors
    script = RealNotifyWorld(
        {"us1": ladder_fails(), "us2": [passing()]}, client=env.client
    )

    async with start_epic(env, script, graph=graph) as handle:
        [row] = await until("us1's escalation", lambda: pending(db_path) or None)
        await press(env, row, EscalationChoice.KILL_EPIC)
        result = await handle.result()

    assert result.epic_state == EpicState.KILLED
    assert pending(db_path) == []
    assert resolution_of(db_path, row.escalation_id) == EscalationChoice.KILL_EPIC.value

    assert await _reset_epic(graph) == 0
    reset_effect(repo, factory_root, worktrees)


# --- the precondition itself, read as a function ----------------------------


def document(**nodes: dict[str, Any]) -> dict[str, Any]:
    """An `epic_status` answer in the shape the query hands the CLI: plain JSON."""
    return {"epic_state": "RUNNING", "nodes": dict(nodes)}


def test_a_running_epic_is_reset_only_when_it_is_waiting_on_a_human() -> None:
    """FR-007's rule, both directions, over the whole decision.

    Against the query's raw document — strings and all, because that untyped
    shape is what the CLI reads, and a worker predating `awaiting_operator`
    still answers. `nodes_at_work` alone would widen too far: an epic that
    started and has not dispatched reports no work either, and archiving the
    worktrees it is about to prepare is the race the old blanket refusal
    accidentally prevented. So the rule needs a waiter *present*, not merely
    work absent, and the halves are asserted apart so neither can go alone.
    """
    paged = {"state": "VERIFYING", "awaiting_operator": True}
    working = {"state": "RUNNING", "awaiting_operator": False}

    # A node parked on a page is not work; the same state without a page is, and
    # so is a node whose worker reported no such field at all.
    assert nodes_at_work(document(us1=paged, us2=working)) == ("us2",)
    assert nodes_awaiting_operator(document(us1=paged, us2=working)) == ("us1",)
    assert nodes_at_work(document(us1={"state": "VERIFYING"})) == ("us1",)

    # Stalled: a waiter, nothing in flight. The deadlock's own shape.
    assert reset_refusal(EPIC_ID, document(us1=paged, us2={"state": "PENDING"})) is None

    # A waiter and a worker: refused, naming the worker and not the waiter.
    refused = reset_refusal(EPIC_ID, document(us1=paged, us2=working))
    assert refused is not None and "us2" in refused and "us1" not in refused, refused

    # Started, nothing dispatched, nobody paged: still refused, in the sentence
    # the verb has always printed. So is an epic that has reported no node.
    assert reset_refusal(EPIC_ID, document(us1={"state": "PENDING"})) == (
        f"epic '{EPIC_ID}' is running (workflow id epic-{EPIC_ID}); "
        "refusing to reset while the workflow is active"
    )
    assert reset_refusal(EPIC_ID, {"nodes": {}}) is not None


# --- runtime evidence, pasted verbatim (constitution VIII / D-037) ----------
#
# Red, before any implementation existed (ec74f47):
#   E ImportError: cannot import name 'nodes_at_work' from factory.cli.nouns.build
#
# The menu, decoded off the rendered buttons, in offered order (SC-003):
#   RETRY 🔁 Retry the node        | KILL      🛑 Kill the node
#   PAUSE_EPIC ⏸️ Pause the epic   | KILL_EPIC 💥 End the whole epic
#
# Kill from a page, then reset, no Temporal surgery (SC-003) — the two reset
# scenarios above under `-s`. First block is US2-S3, where the epic is alive and
# waiting so reset says so and archives anyway; second is US2-S2, after
# KILL_EPIC ended the epic, where there is nothing left to warn about:
#   note: epic 'demo-loans' is still running, waiting on an operator for us1;
#         end it with `ergane build kill demo-loans`
#   us1: committed dirty state, removed worktree, archived branch
#   us2: committed dirty state, removed worktree, archived branch
#   us1: committed dirty state, removed worktree, archived branch
#   us2: committed dirty state, removed worktree, archived branch
#
# Five mutations, each reverted before the next, named by the claim they kill:
#  1. `nodes_at_work` always `()` -> FAILED test_reset_refuses_an_epic_with_a_
#     node_at_work, test_a_running_epic_is_reset_only_when_it_is_waiting...
#  2. the escalation child awaited unconditionally again — the tree exactly as
#     it stood before this story -> FAILED test_killing_the_epic_cancels_a_
#     sibling_s_open_escalation: "a stopped epic must not answer the operator's
#     own question for them / assert 'EXPIRED' is None". The sibling's page runs
#     its whole hour and expires. Under the time-skipping server that hour costs
#     the test nothing, which is why the assertion is on the row and not the
#     clock: the wall-clock hour is the production symptom, is not observable
#     here, and is not claimed measured.
#  3. `KILL_EPIC` stops setting `_kill_requested` -> FAILED test_kill_ends_the_
#     node_kill_epic_ends_the_epic..., "+ COMPLETED" (the epic finished us2
#     instead of stopping), and two others with it.
#  4. `awaiting_operator` hardcoded False -> FAILED test_reset_succeeds_when_the
#     _only_living_child...: "refusing to reset while us1 is still working".
#  5. `reset_refusal` drops the must-be-waiting leg -> FAILED test_a_running_
#     epic_is_reset_only... and tests/test_ergane_build.py::test_reset_guard_
#     cases (assert 0 != 0). The second is 047's guard, and the reason the rule
#     is "a waiter is present" rather than "no work is present".
#
# No baseline run of the untouched tree was made, so none is quoted. After, the
# gate `factory.yaml` declares:  3903 passed, 49 skipped in 305.04s.
#
# The diff was measured with `diffcheck.diff_size_refusal` rather than estimated
# — a story this wide is refusable before a judge reads a line of it, which is
# why `docs/architecture.md` is not in it (see the final report):
#   refusal: None
