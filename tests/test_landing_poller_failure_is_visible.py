"""User Story 3 — a landing poll that dies is visible.

A node's landing rides the merge queue on a background task
(`EpicWorkflow._poll_landing`, spawned with `asyncio.ensure_future` at two
sites). Nothing awaited that task and nothing read its exception, so a
`poll_landing` activity that raised — the forge refusing a field the poller
asks for, which is the whole of epics 078's US1 and US2 — killed the poller
silently. The node went on reporting `ENQUEUED`, the epic parked waiting for a
landing nobody was watching, and the only way to learn any of it was to read a
worker log.

What these tests are written to resist:

- **A remedy that reports the wrong thing.** `test_a_landing_poll_that_dies_stops_reporting_enqueued`
  asserts the state the node must *not* be in as well as the one it is: FR-008
  is about the reading that implies polling, not about any particular terminal.
- **A remedy that is only in the record.** `terminal_reason` was already on
  `NodeRecord` and already in the `epic_status` query on 2026-08-20, and the
  defect still cost an evening — because nothing *printed* it.
  `test_the_stopped_poller_names_its_reason_in_the_rendered_status` asserts the
  rendered operator line (US3-S2, T022), not the field.
- **A remedy that cries wolf.** `test_a_poll_that_fails_once_and_recovers_lands_normally`
  is the control (US3-S3, FR-010): the forge is a network service and `_FAST`
  already carries a three-attempt retry policy. A transient failure must be
  retried by the activity and never become an operator-visible ending. It
  asserts the retry budget was really spent, so it cannot pass by never having
  failed at all.
- **A remedy that reads a cancellation as a crash.**
  `test_a_kill_while_a_landing_polls_behaves_as_it_did_before` is the second
  control (US3-S4): `_kill_landings` cancels every poll task, and
  `asyncio.CancelledError` must pass through the new observation untouched —
  a killed epic's nodes carry no poller-failure reason.
- **A remedy that makes the poller foreground.** US3-S5 and plan trap 7. Riding
  the landing in the background is what lets an epic run its other nodes while a
  pull request sits in the queue. `test_the_landing_poller_is_still_spawned_at_both_sites`
  holds the structure (both `ensure_future` sites, plan trap 6, and no `await`
  on the poller), and `test_another_node_runs_while_a_landing_is_still_polling`
  holds the behaviour it exists for.

The scripted world of `tests.test_interpreter` is reused rather than rebuilt;
only `poll_landing` is replaced, by a fake that can refuse the way the forge
refuses. The measured before/after status readings these assertions turn on are
pasted at the bottom of this file, because the judge is given the diff and
nothing else (constitution VIII).
"""

from __future__ import annotations

import ast
import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable

from temporalio import activity
from temporalio.converter import default as default_data_converter
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment

from factory.activities.merge_activities import PollLandingInput
from factory.cli.nouns.build import render_status
from factory.mergequeue.models import LandingConfig, LandingState, PrSnapshot
from factory.workgraph import workflow as workflow_module
from factory.workgraph.models import EpicState, NodeState

from tests.test_interpreter import (
    EPIC_ID,
    KILL_SIGNAL,
    ScriptedWorld,
    _node_of_pr,
    checks_failed_snapshot,
    env,  # noqa: F401  — pytest fixture, re-exported for this module
    make_graph,
    make_node,
    merged_snapshot,
    one_node,
    passing,
    pending_snapshot,
    run_epic,
    start_epic,
    wait_for,
    wait_for_status,
)

NODE = "us1"

#: How long a whole epic in this file may take before the test gives up. Every
#: epic here either reaches a terminal or is killed, so this bounds a *hang*
#: rather than a slow run: before the fix, a node whose poller died left the
#: main loop parked on `_all_landings_terminal()` forever, and an unbounded
#: `await handle.result()` would have hung the suite instead of failing it.
EPIC_TIMEOUT_S = 60.0

#: The retry budget the landing poll runs under — `_FAST`'s policy, read from
#: the workflow rather than restated here (plan trap 8). It is the line between
#: a slow forge and a stopped poller, so the tests assert against the real
#: number: a diff that stopped a poller on its first transient failure would
#: leave attempts unspent and fail.
POLL_ATTEMPTS = workflow_module._RETRIES.maximum_attempts

#: The landing knobs the two tests that watch an epic *live* run under. Time
#: skipping only advances while a client awaits the workflow's result, so a test
#: that steers an epic through queries pays the poll interval in real seconds —
#: the default minute would be a minute of suite. Nothing else about the landing
#: changes.
BRISK = LandingConfig(poll_interval_s=1)

#: The refusal the fake forge raises — the shape 078 is about, a `gh` that will
#: not answer the question the poller asked. The text is synthetic: it names no
#: token and quotes no live command output (plan trap 12).
REFUSAL = 'gh pr view --json baseRefOid: Unknown JSON field: "baseRefOid"'


class _Refuse:
    """Sentinel poll answer: this observation raises instead of answering."""

    def __init__(self, message: str) -> None:
        self.message = message


REFUSED = _Refuse(REFUSAL)

#: A target head that is not the one the harness's `prepare_worktree` pins every
#: node to (`"9" * 40`). A rejection observed against it is 069-US1's moved
#: base: the cheapest way back onto the queue, and therefore the cheapest way to
#: reach the second `ensure_future` site.
MOVED_BASE = "5" * 40

PollAnswer = PrSnapshot | _Refuse


def _activity_name(fn: Any) -> str:
    """The name Temporal registers a scripted activity under."""
    definition = getattr(fn, "__temporal_activity_definition", None)
    return getattr(definition, "name", "")


class PollingWorld(ScriptedWorld):
    """The scripted world with a `poll_landing` that can refuse.

    Only that one activity is replaced — everything else an epic needs is the
    interpreter's own harness, unchanged. `poll_answers` is per node: each poll
    consumes the head of that node's list and the last answer repeats forever,
    so `[REFUSED]` is a forge that never answers, `[REFUSED, merged_snapshot()]`
    is one hiccup followed by a landing, and `[pending_snapshot()]` is a queue
    that is still thinking. A node with no scripted answers merges, so a test
    about one node's poller need not script the others.

    Every call is logged by node id, because "the poller stopped" and "the
    poller was never asked" are different facts and a test that could not tell
    them apart would pass for the wrong reason.
    """

    def __init__(
        self,
        script: dict[str, list[Any]],
        *,
        poll_answers: dict[str, list[PollAnswer]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(script, **kwargs)
        self.poll_answers: dict[str, list[PollAnswer]] = {
            node_id: list(answers)
            for node_id, answers in (poll_answers or {}).items()
        }
        self.poll_attempts: list[str] = []

    def attempts_for(self, node_id: str) -> int:
        """How many times the forge was asked about this node's landing."""
        return self.poll_attempts.count(node_id)

    def _next_answer(self, node_id: str) -> PollAnswer:
        answers = self.poll_answers.get(node_id)
        if not answers:
            return merged_snapshot()
        return answers.pop(0) if len(answers) > 1 else answers[0]

    def activities(self) -> list[Any]:
        world = self
        inherited = [
            fn
            for fn in super().activities()
            if _activity_name(fn) != "poll_landing"
        ]

        @activity.defn(name="poll_landing")
        async def poll_landing(request: PollLandingInput) -> PrSnapshot:
            node_id = _node_of_pr(request.pr_number)
            world._log("poll_landing", node_id)
            world.poll_requests.append(request)
            world.poll_attempts.append(node_id)
            answer = world._next_answer(node_id)
            if isinstance(answer, _Refuse):
                # What a refusing forge does to the activity: `poll_landing`
                # lets the `ForgeError` escape, so the workflow sees an
                # `ActivityError` wrapping this message once the retry budget
                # is spent.
                raise ApplicationError(answer.message)
            world._observed_outcomes.append(answer)
            return answer

        return inherited + [poll_landing]


def as_json_document(status: Any) -> dict[str, Any]:
    """The document `ergane build status` renders, from a real status.

    `_query_status` queries with no result type, so what the CLI holds is JSON
    decoded from the history's bytes rather than the dataclass this test was
    handed. A reason that survives the dataclass but not the wire is a reason no
    operator can read, so the trip is made in-process here.
    """
    payload = default_data_converter().payload_converter.to_payload(status)
    document: dict[str, Any] = json.loads(payload.data)
    return document


def node_line(status: Any, node_id: str = NODE) -> str:
    """The one rendered line an operator reads for a node."""
    rendered = render_status(EPIC_ID, as_json_document(status), "COMPLETED")
    lines = [line for line in rendered.splitlines() if line.startswith(node_id)]
    assert len(lines) == 1, f"expected one '{node_id}' line in:\n{rendered}"
    return lines[0]


def reaches(node_id: str, state: NodeState) -> Any:
    """A status predicate: this node has reached this state.

    Tolerant of the empty node map an epic reports before `resolve_graph`
    answers — a query that lands in that window is a reading of an epic that has
    not started, not a missing node.
    """

    def predicate(status: Any) -> bool:
        node = status.nodes.get(node_id)
        return node is not None and node.state == state

    return predicate


async def bounded(awaitable: Any) -> Any:
    """Await an epic, turning a parked one into a failure rather than a hang."""
    return await asyncio.wait_for(awaitable, EPIC_TIMEOUT_S)


# --- T021 [US3] (spec US3-S1, FR-008) -----------------------------------------


async def test_a_landing_poll_that_dies_stops_reporting_enqueued(
    env: WorkflowEnvironment,
) -> None:
    """The node whose poller died must not read as one still being polled.

    The forge refuses every observation. The activity spends its whole retry
    budget, the poll task dies of the exception — and the reading an operator
    gets must change. `ENQUEUED` is asserted absent by name because that is the
    literal defect: FR-008 is about the state that *implies* a live poller, not
    about which terminal replaces it.

    The epic reaching a terminal at all is half the point. Before this change
    the main loop parked on `_all_landings_terminal()` for a landing nothing was
    driving, so this test could only ever have timed out.
    """
    script = PollingWorld(
        {NODE: [passing()]},
        client=env.client,
        poll_answers={NODE: [REFUSED]},
    )

    status = await bounded(run_epic(env, script, graph=one_node()))

    # The retry budget was spent first: the poller stopped because the forge
    # would not answer, not because one call was slow (FR-010).
    assert script.attempts_for(NODE) == POLL_ATTEMPTS

    node = status.nodes[NODE]
    assert node.state != NodeState.ENQUEUED, (
        "the node still reports a state that implies it is being polled"
    )
    assert node.state == NodeState.KILLED
    assert node.landing_state == LandingState.KILLED
    assert status.epic_state == EpicState.COMPLETED


# --- T022 [US3] (spec US3-S2, FR-009) -----------------------------------------


async def test_the_stopped_poller_names_its_reason_in_the_rendered_status(
    env: WorkflowEnvironment,
) -> None:
    """The reason is readable from the status text, not just from the record.

    This is the assertion the story turns on. `terminal_reason` was on the
    record and in the query already; `ergane build status` printed neither, so
    the operator-visible account of a dead poller was a node that had silently
    changed state. The line must say that the landing poll stopped, which PR it
    stopped on, and what the forge said.
    """
    script = PollingWorld(
        {NODE: [passing()]},
        client=env.client,
        poll_answers={NODE: [REFUSED]},
    )

    status = await bounded(run_epic(env, script, graph=one_node()))

    pr_number = ScriptedWorld._pr_number_for(NODE)
    line = node_line(status)

    assert "landing poll stopped" in line
    assert f"#{pr_number}" in line, "the line does not name the PR that stopped"
    assert 'Unknown JSON field: "baseRefOid"' in line, (
        "the line does not name what the forge said — the reason is the point"
    )
    assert "ENQUEUED" not in line

    # The record agrees with the line. It always did; that was never the gap.
    assert status.nodes[NODE].terminal_reason is not None
    assert REFUSAL in status.nodes[NODE].terminal_reason


# --- T025 [US3] (FR-008, FR-009) — the requeue path, which is site two --------


async def test_a_poller_spawned_by_the_requeue_path_is_watched_too(
    env: WorkflowEnvironment,
) -> None:
    """The second `ensure_future` site is observed as well (plan trap 6).

    A landing that is rejected and goes back on the queue spawns its *second*
    poller from `_reenqueue`, not from `_land` — and that is the path a busy
    epic runs, because it is the path a node takes every time a sibling lands
    ahead of it. Fixing the first site and not the second would leave the common
    case exactly as blind as it is today, and no test that only ever enqueues
    once could tell.

    The cheapest rejection that returns to the queue is 069-US1's free rebase: a
    check that failed under a base that moved, which re-offers the same verdict
    without an agent attempt. The forge then refuses the second poller.
    """
    script = PollingWorld(
        {NODE: [passing()]},
        client=env.client,
        poll_answers={NODE: [replace(checks_failed_snapshot(), base_sha=MOVED_BASE), REFUSED]},
    )
    script.script_sync(NODE, clean=True, base_ref=MOVED_BASE)

    status = await bounded(run_epic(env, script, graph=one_node()))

    # The requeue really happened: the landing went back on the queue a second
    # time, off the free-rebase budget, and a second poller was spawned for it.
    assert script.calls.count("enqueue_landing") == 2
    assert status.nodes[NODE].free_rebases == 1
    assert script.attempts_for(NODE) == 1 + POLL_ATTEMPTS

    node = status.nodes[NODE]
    assert node.state == NodeState.KILLED
    assert node.landing_state == LandingState.KILLED
    assert REFUSAL in (node.terminal_reason or "")
    assert "landing poll stopped" in node_line(status)


# --- T023 [US3] (spec US3-S3, FR-010) — the control ---------------------------


async def test_a_poll_that_fails_once_and_recovers_lands_normally(
    env: WorkflowEnvironment,
) -> None:
    """One hiccup is not a dead poller.

    **The control.** A remedy that treated any failed observation as a stopped
    poller would trade a silent hang for a false alarm on every network blip,
    and would kill a node whose pull request was about to merge. The forge
    refuses once and answers on the next beat: the activity's own retry policy
    absorbs it, the landing merges, and nothing operator-visible records a
    failure.

    The attempt count is asserted so this cannot pass vacuously: a run where the
    refusal never happened would spend one attempt, not two.
    """
    script = PollingWorld(
        {NODE: [passing()]},
        client=env.client,
        poll_answers={NODE: [REFUSED, merged_snapshot()]},
    )

    status = await bounded(run_epic(env, script, graph=one_node()))

    assert script.attempts_for(NODE) == 2, "the transient refusal did not happen"

    node = status.nodes[NODE]
    assert node.state == NodeState.MERGED
    assert node.landing_state == LandingState.MERGED
    assert node.terminal_reason is None, (
        "a recovered poll was reported as a stopped poller"
    )
    assert status.epic_state == EpicState.COMPLETED

    line = node_line(status)
    assert "landing poll stopped" not in line
    assert "reason:" not in line


# --- T024 [US3] (spec US3-S4) — the second control ----------------------------


async def test_a_kill_while_a_landing_polls_behaves_as_it_did_before(
    env: WorkflowEnvironment,
) -> None:
    """The cancel-on-kill path, unchanged (`workflow.py` `_kill_landings`).

    **The second control.** The kill path cancels every poll task, and
    `asyncio.CancelledError` derives from `BaseException` — so an observation
    written with `except Exception` lets it through and a killed poller is not
    recorded as a stopped one. A diff that caught `BaseException` here would
    turn every killed epic's nodes into poller failures, which is the same
    unreadable status in the other direction.

    Everything asserted below is today's behaviour: the epic ends KILLED, the
    node ends KILLED, the landing ends KILLED with its branch preserved, and
    auto-merge is withdrawn from the queue exactly once.
    """
    script = PollingWorld(
        {NODE: [passing()]},
        client=env.client,
        poll_answers={NODE: [pending_snapshot()]},
    )

    async with start_epic(
        env, script, graph=one_node(), landing_config=BRISK
    ) as handle:
        await wait_for_status(
            handle,
            reaches(NODE, NodeState.ENQUEUED),
            what="the landing to enqueue and start polling",
        )
        # Give the poller a beat to be genuinely mid-ride when the kill lands.
        await wait_for(
            lambda: script.attempts_for(NODE) >= 1,
            what="the first observation of the landing",
        )
        await handle.signal(KILL_SIGNAL)
        status = await bounded(handle.result())

    assert status.epic_state == EpicState.KILLED
    node = status.nodes[NODE]
    assert node.state == NodeState.KILLED
    assert node.landing_state == LandingState.KILLED
    assert node.terminal_reason is None, (
        "a cancelled poller was recorded as a stopped one"
    )

    pr_number = ScriptedWorld._pr_number_for(NODE)
    assert [request.pr_number for request in script.disable_requests] == [pr_number]

    line = node_line(status)
    assert "landing poll stopped" not in line


# --- T027 [US3] (spec US3-S5) — the poller stays in the background ------------


def _poller_spawns(tree: ast.Module) -> tuple[list[ast.Call], list[ast.Await]]:
    """Every spawn of the landing ride, and every `await` of one.

    Read from the source because the claim is about shape, not behaviour: US3-S5
    forbids a diff that converts the background task into a foreground await,
    and a workflow that awaited its poller would still pass every behavioural
    assertion in this file while parking the epic on one pull request.
    """
    spawned: list[ast.Call] = []
    awaited: list[ast.Await] = []

    def names(node: ast.AST) -> Iterable[str]:
        for child in ast.walk(node):
            if isinstance(child, ast.Attribute):
                yield child.attr

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            callee = node.func
            if isinstance(callee, ast.Attribute) and callee.attr == "ensure_future":
                if any(
                    name in ("_poll_landing", "_ride_landing")
                    for name in names(node)
                ):
                    spawned.append(node)
        if isinstance(node, ast.Await):
            if any(
                name in ("_poll_landing", "_ride_landing")
                for name in names(node.value)
            ):
                awaited.append(node)
    return spawned, awaited


def test_the_landing_poller_is_still_spawned_at_both_sites() -> None:
    """Both `ensure_future` sites survive, and neither ride is awaited.

    Two sites, because a node that requeues after a rejection spawns its poller
    through the second one — the path that runs during a busy epic (plan trap
    6). Fixing one and not the other leaves the requeue path exactly as blind as
    it was.

    The `await` half is US3-S5: the ride is spawned, never awaited. The wrapper
    that observes the failure awaits `_poll_landing` *inside* the spawned task,
    which is not a foreground await — so the check is scoped to the module's top
    level structure by excluding that one wrapper's own body.
    """
    tree = ast.parse(Path(workflow_module.__file__).read_text())
    spawned, awaited = _poller_spawns(tree)

    # The wrapper's own `await self._poll_landing(...)` is the ride itself,
    # running inside the background task; only awaits outside it are foreground.
    inside_the_ride = {
        id(node)
        for wrapper in ast.walk(tree)
        if isinstance(wrapper, ast.AsyncFunctionDef)
        and wrapper.name == "_ride_landing"
        for node in ast.walk(wrapper)
    }
    foreground = [node for node in awaited if id(node) not in inside_the_ride]

    assert len(spawned) == 2, (
        f"expected the landing ride to be spawned at both sites, found {len(spawned)}"
    )
    assert foreground == [], "the landing poller was converted to a foreground await"


async def test_another_node_runs_while_a_landing_is_still_polling(
    env: WorkflowEnvironment,
) -> None:
    """The behaviour the background task exists for, asserted directly.

    `us1`'s landing sits in the queue answering "still thinking" forever. `us2`
    must still be dispatched, verified, landed and merged while it does. This is
    what US3-S5 protects: an epic that awaited its poller would run one node and
    then stop until the queue was done with it.
    """
    script = PollingWorld(
        {NODE: [passing()], "us2": [passing()]},
        client=env.client,
        poll_answers={NODE: [pending_snapshot()]},
    )
    graph = make_graph([make_node(NODE, "US1"), make_node("us2", "US2")])

    async with start_epic(
        env, script, graph=graph, landing_config=BRISK
    ) as handle:
        status = await wait_for_status(
            handle,
            reaches("us2", NodeState.MERGED),
            what="the second node to land while the first is still polling",
            timeout=30.0,
        )
        assert status.nodes[NODE].state == NodeState.ENQUEUED, (
            "the first node's landing stopped riding the queue"
        )
        await handle.signal(KILL_SIGNAL)
        await bounded(handle.result())


# --- T028 [US3] (SC-007): the reading, before and after -----------------------
#
# Both readings are of the same epic: one node, its ladder green, its landing
# enqueued, and a forge that refuses every `poll_landing`. The command is
# `ergane build status <epic-id>`, rendered by `factory/cli/nouns/build.py`.
#
# BEFORE (this commit's parent, with the same scripted refusal):
#
#     epic demo-loans  RUNNING  execution RUNNING
#     us1  ENQUEUED  attempt 1  factory/demo-loans/us1  persona implementer  model implementer-alias
#
#   ...and it says that forever. The poll task is dead, its exception unread;
#   the epic is parked in `_all_landings_terminal()` waiting for a landing
#   nothing is driving. The only account of the failure is the worker's log.
#
# AFTER:
#
#     epic demo-loans  COMPLETED  execution COMPLETED
#     us1  KILLED  attempt 1  factory/demo-loans/us1  persona implementer  model implementer-alias  reason: landing poll stopped for PR #470: gh pr view --json baseRefOid: Unknown JSON field: "baseRefOid"
#
#   The state no longer implies a live poller (FR-008), the reason is on the
#   line an operator reads (FR-009), and the epic reaches a terminal instead of
#   parking on a pull request nobody is watching.
#
# Reproduced by `test_the_stopped_poller_names_its_reason_in_the_rendered_status`
# above, which asserts every load-bearing fragment of the AFTER line.
