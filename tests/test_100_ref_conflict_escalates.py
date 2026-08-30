"""US3 — a deterministic ref conflict escalates instead of killing the epic.

US2 gave the refusal its words. This story gives it a *route*. A push git
refused non-fast-forward is deterministic: the second attempt is refused for the
same reason as the first, and the third for the same reason as the second — so
spending `PUSH_FAILED`'s three attempts on it buys nothing, and the node it
finally kills was verified, its work already committed and pushed nowhere. What
dies with it is every node waiting behind it.

The carve-out follows the precedent 107-US2 set two error types up in the same
file: an ownership refusal was taken out of `PUSH_FAILED` because two
repositories disagreeing about who owns a directory answers the same way on
every retry. A stale remote ref is the same shape of fact, with one difference
that decides the routing: an operator clears it in one command. So it pages
them, and the page carries the command.

The tests below split by boundary, because the change does:

- **T015 (US3-S1)** — the *activity* boundary. A real git refusal, classified,
  crossing `open_landing_pr` as a non-retryable error type of its own.
- **T016 (US3-S2, trap 6)** — the *workflow* boundary. The node escalates rather
  than terminating, the activity is tried once rather than three times, and the
  failure underneath the page is recorded rather than swallowed: escalating is
  not the same as not failing.
- **T017 (US3-S3)** — the *operator's* boundary. The page names the ref, quotes
  git's reason, and spells the command that clears it.
- **T018 (US3-S4, trap 5)** — **the control**, in three places: a real rejection
  that is not a non-fast-forward stays retryable, an unclassifiable stderr falls
  back to the retryable path, and a `PUSH_FAILED` still spends its three
  attempts and still pages nobody. This story carves out one cause; asserting
  only the carve-out would pass just as happily if every push failure had been
  made non-retryable.
- **T019 (US3-S5, trap 7)** — the *sibling* boundary. The cost that justifies
  the story: siblings examined at the moment the page is raised, and again after
  the operator clears the ref and presses retry.

The refusal these tests classify is a real one — real git, real remote, real
non-fast-forward — reused from US2's module rather than re-fixtured here, so
both stories keep classifying the same bytes git actually wrote.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from temporalio import activity
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment, WorkflowEnvironment

from factory.activities.merge_activities import (
    LANDING_REF_CONFLICT,
    PUSH_FAILED,
    OpenLandingPrInput,
    open_landing_pr,
)
from factory.verify.models import EscalationChoice
from factory.workgraph.models import NodeState
from factory.workgraph.workflow import EpicWorkflow
from factory.workgraph.worktree import (
    WorktreeError,
    is_non_fast_forward,
    push_branch,
    ref_conflict_remedy,
)
from tests.test_100_push_reports_refusal import (  # noqa: F401 — fixtures re-exported
    BRANCH,
    NODE,
    Refusal,
    RefusedPushWorld,
    _activity_name,
    _origin,
    _prepare,
    _rebuild_on_a_sibling_commit,
    factory_root,
    flat,
    no_operator_git_identity,
    refusal,
    repo,
)
from tests.test_interpreter import (
    EPIC_ID,
    ScriptedWorld,
    env,  # noqa: F401 — pytest fixture, re-exported for this module
    make_graph,
    make_node,
    one_node,
    passing,
    run_epic,
    states,
)

#: The command US3-S3 says the page must carry. Spelled out here rather than
#: imported, so a change to `ref_conflict_remedy` has to face a test that says
#: what the operator is supposed to be able to type.
CLEARING_COMMAND = f"git push --delete origin {BRANCH}"


@pytest.fixture
def activity_env() -> ActivityEnvironment:
    """The activity boundary, run without a workflow around it."""
    return ActivityEnvironment()


@pytest.fixture
def runtime_root(factory_root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the activity's own root resolution at this test's worktree root.

    `push_branch` is called by the test with an explicit `factory_root`; the
    activity resolves its own from the environment (constitution IX — the
    declaration, never the process's cwd). Both have to name one directory, or
    the activity would refuse a worktree that is merely somewhere else.
    """
    monkeypatch.setenv("ERGANE_ROOT", str(factory_root))
    monkeypatch.delenv("FACTORY_ROOT", raising=False)
    return factory_root


# --- T015 [US3] (spec US3-S1, FR-007, trap 5) ---------------------------------


async def test_a_non_fast_forward_push_fails_non_retryably(
    activity_env: ActivityEnvironment,
    runtime_root: Path,
    refusal: Refusal,
    repo: Path,
) -> None:
    """US3-S1: the refusal crosses the activity as its own non-retryable type.

    The `refusal` fixture has already left the world in the failing state — the
    remote holds a tip this branch is not descended from — so the activity's own
    push is refused by the same remote for the same reason, which is the point:
    nothing here simulates the classification's input.

    Two assertions, and both matter. Non-retryable, because three attempts at a
    deterministic refusal is the waste this story removes; and a type of its own
    rather than `PUSH_FAILED`, because the workflow routes on the type and a
    reclassified `PUSH_FAILED` would take every other push failure with it.
    """
    with pytest.raises(ApplicationError) as raised:
        await activity_env.run(
            open_landing_pr,
            OpenLandingPrInput(
                epic_id=EPIC_ID,
                node_id=NODE,
                target_repo=str(repo),
                branch=BRANCH,
                title="US3",
                body_file="/tmp/body.md",
            ),
        )

    assert raised.value.type == LANDING_REF_CONFLICT
    assert raised.value.type != PUSH_FAILED
    assert raised.value.non_retryable is True
    # US2's words survive the reclassification: the reason is still git's.
    assert flat(refusal.rejection) in flat(str(raised.value))


# --- T016 [US3] (spec US3-S2, FR-008, trap 6) ---------------------------------


class RefConflictWorld(ScriptedWorld):
    """The scripted world whose landing push git refuses non-fast-forward.

    Two activities are wrapped rather than replaced, so everything the landing
    phase does around them stays the real fake's:

    - `open_landing_pr` raises exactly what the activity now raises for a ref
      conflict — same type, same non-retryable flag, same `from exc` cause chain
      over a `WorktreeError` a real git really produced — for its first
      `failures` calls, and succeeds after that. The count is what proves the
      operator's grant put the node back to work rather than merely ending it
      more politely.
    - `send_escalation` takes a view of the whole epic *while the page is open*.
      That view is US3-S5's evidence: the question is what has happened to the
      siblings at the moment the node escalates, and a status read after the
      epic finishes cannot answer it.
    """

    def __init__(
        self,
        script: dict[str, list[Any]],
        *,
        error: WorktreeError,
        failures: int = 1,
        **kwargs: Any,
    ) -> None:
        super().__init__(script, **kwargs)
        self.error = error
        self.failures = failures
        self.open_attempts = 0
        self.escalation_views: list[Any] = []

    def activities(self) -> list[Any]:
        world = self
        inherited = super().activities()
        wrapped = {"open_landing_pr", "send_escalation"}
        real = {_activity_name(fn): fn for fn in inherited}

        @activity.defn(name="open_landing_pr")
        async def open_landing_pr_(request: OpenLandingPrInput) -> Any:
            world.open_attempts += 1
            if world.open_attempts > world.failures:
                return await real["open_landing_pr"](request)
            world._log("open_landing_pr", request.node_id)
            world.landing_requests.append(request)
            raise ApplicationError(
                str(world.error), type=LANDING_REF_CONFLICT, non_retryable=True
            ) from world.error

        @activity.defn(name="send_escalation")
        async def send_escalation_(request: Any) -> Any:
            world.escalation_views.append(
                await world.handle.query(EpicWorkflow.epic_status)
            )
            return await real["send_escalation"](request)

        return [fn for fn in inherited if _activity_name(fn) not in wrapped] + [
            open_landing_pr_,
            send_escalation_,
        ]


async def test_the_node_escalates_rather_than_terminating(
    env: WorkflowEnvironment, refusal: Refusal
) -> None:
    """US3-S2: a page, raised once, over a failure that is still on the record.

    The node is verified and its push is refused. What must *not* happen is the
    node ending on the refusal; what must happen is an operator being asked.
    Asserted at the moment it matters — the view taken while the page is open
    shows the node alive, not KILLED — because a node that died and then had its
    death reported would look the same in a final status.

    Trap 6 is the other half. Escalating is not the same as not failing: the
    activity really did fail, and the failure is on the record where an operator
    reads it (`terminal_reason`, which `ergane build status` prints) rather than
    swallowed to keep the node breathing. An escalation with no recorded failure
    behind it is unreadable.

    And it is tried once. Three attempts at a deterministic refusal, interleaved
    with Temporal's retry noise, is the waste FR-007 removes; a routing change
    that left the error retryable would show `open_attempts == 3` here.
    """
    script = RefConflictWorld(
        {NODE: [passing()]},
        client=env.client,
        error=refusal.error,
        failures=1,
        press=EscalationChoice.KILL.value,
    )

    status = await run_epic(env, script, graph=one_node())

    assert script.open_attempts == 1, (
        "the deterministic refusal was retried; the carve-out is not in force"
    )
    assert len(script.escalation_requests) == 1, (
        "the node did not page an operator about a ref conflict"
    )
    assert script.escalation_requests[0].node_id == NODE

    [view] = script.escalation_views
    assert states(view)[NODE] not in {NodeState.KILLED, NodeState.FAILED}, (
        "the node was terminated before the operator was asked, which is the "
        "behaviour this story replaces"
    )

    # Trap 6: the failure underneath the page is recorded, not swallowed.
    reason = view.nodes[NODE].terminal_reason or ""
    assert flat(refusal.rejection) in flat(reason), (
        f"the refusal behind the escalation is nowhere on the record: {reason!r}"
    )

    # The operator answered KILL, so the node ends killed — by their hand.
    assert states(status)[NODE] == NodeState.KILLED


# --- T017 [US3] (spec US3-S3, FR-008) -----------------------------------------


async def test_the_escalation_names_the_ref_the_reason_and_the_command(
    env: WorkflowEnvironment, refusal: Refusal
) -> None:
    """US3-S3: the page is a fix, not a notification.

    An operator woken by this has to be able to act without opening a terminal
    to find out what happened. Three facts do that, and the page carries all
    three: which ref would not move, what git said about it, and the one command
    that clears it. The command is asserted as the literal string an operator
    would type — a page that named the ref and the reason and left them to
    derive the remedy is the page this story is replacing.
    """
    script = RefConflictWorld(
        {NODE: [passing()]},
        client=env.client,
        error=refusal.error,
        failures=1,
        press=EscalationChoice.KILL.value,
    )

    await run_epic(env, script, graph=one_node())

    [escalation] = script.escalation_requests
    summary = flat(escalation.history_summary)

    assert BRANCH in summary, f"the page does not name the ref: {summary!r}"
    assert flat(refusal.rejection) in summary, (
        f"the page does not carry git's reason: {summary!r}"
    )
    assert CLEARING_COMMAND in summary, (
        f"the page does not name the command that clears it: {summary!r}"
    )
    # FR-010: the tempting one-liner is the one thing the page must never
    # suggest — it turns a recoverable conflict into unrecoverable data loss.
    assert "--force" not in summary
    assert ref_conflict_remedy("origin", BRANCH) == CLEARING_COMMAND


# --- T018 [US3] (spec US3-S4, FR-009, trap 5) — the control --------------------


def _decline_every_push(bare: Path) -> None:
    """Make the remote refuse for a reason that is not a ref conflict.

    A `pre-receive` hook that exits non-zero produces a real rejection with a
    real `! [remote rejected] … (pre-receive hook declined)` status line — the
    same shape of line the classifier anchors on, with a different reason inside
    it. That is the discrimination trap 5 is about: a guard that matched on the
    line's prefix alone, or on a substring anywhere in stderr, would call this a
    ref conflict and refuse it non-retryably for an outage a retry would clear.
    """
    hook = bare / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)


async def test_a_push_refused_for_another_reason_stays_retryable(
    activity_env: ActivityEnvironment,
    runtime_root: Path,
    repo: Path,
    factory_root: Path,
    tmp_path: Path,
) -> None:
    """US3-S4: one cause is carved out, not the class.

    A real refusal by a real remote, for a reason that is not a
    non-fast-forward, keeps today's retryable `PUSH_FAILED` — a hook that will
    be re-enabled, a remote that is briefly unhappy, a lock: all the things a
    second attempt fixes. Asserted through the same activity boundary as the
    carve-out above, so the two answers are compared where the workflow reads
    them.
    """
    bare = _origin(repo, tmp_path)
    _prepare(repo, factory_root)
    _decline_every_push(bare)

    with pytest.raises(WorktreeError) as refused:
        push_branch(repo, EPIC_ID, NODE, factory_root=factory_root)
    assert "! [" in refused.value.stderr, (
        "the fixture did not produce a per-ref rejection line, so it does not "
        f"test the discrimination it claims to:\n{refused.value.stderr}"
    )
    assert not is_non_fast_forward(refused.value.stderr)

    with pytest.raises(ApplicationError) as raised:
        await activity_env.run(
            open_landing_pr,
            OpenLandingPrInput(
                epic_id=EPIC_ID,
                node_id=NODE,
                target_repo=str(repo),
                branch=BRANCH,
                title="US3",
                body_file="/tmp/body.md",
            ),
        )

    assert raised.value.type == PUSH_FAILED
    assert raised.value.type != LANDING_REF_CONFLICT
    assert not raised.value.non_retryable


def test_an_unclassifiable_stderr_falls_back_to_the_retryable_path(
    refusal: Refusal,
) -> None:
    """US3-S4 / trap 5: the classifier says yes narrowly and no by default.

    The one case it must answer yes to is git's own, so the positive sample is
    the bytes git wrote a moment ago rather than a string this file decided git
    ought to write. Every negative is a way a looser guard goes wrong: a
    substring hunt over the whole of stderr fires on a hint paragraph and on an
    `error:` summary line; a prefix-only match fires on every other per-ref
    rejection; and nothing at all — a git that died without writing, a refusal
    raised before the subprocess — must not read as a conflict either.

    FR-009 is why the default is this direction: an ambiguous classification
    costs one retry, and the other way round it costs an operator a page for a
    fault that was going to clear itself.
    """
    assert is_non_fast_forward(refusal.stderr) is True

    for unclassifiable in (
        "",
        "   \n\n",
        "fatal: Authentication failed for 'https://example.invalid/repo.git'",
        "fatal: 'origin' does not appear to be a git repository",
        # The phrase, in prose, nowhere near a per-ref status line.
        "hint: Updates were rejected because this push is a (non-fast-forward)\n"
        "error: failed to push some refs (non-fast-forward)",
        # A per-ref rejection line — the right shape, the wrong reason.
        "To /tmp/origin.git\n"
        " ! [remote rejected] work -> work (pre-receive hook declined)\n"
        "error: failed to push some refs to '/tmp/origin.git'",
        # The phrase inside the ref name rather than as git's verdict.
        " ! [remote rejected] non-fast-forward -> non-fast-forward (declined)",
    ):
        assert is_non_fast_forward(unclassifiable) is False, (
            f"classified as a ref conflict, and it is not: {unclassifiable!r}"
        )


async def test_an_ordinary_push_failure_still_retries_and_pages_nobody(
    env: WorkflowEnvironment, refusal: Refusal
) -> None:
    """US3-S4, at the workflow boundary: today's path is untouched.

    `PUSH_FAILED` is what every push failure but one still raises, and nothing
    about its route changed: Temporal spends the three attempts the retry policy
    allows, no operator is paged, and the node ends killed with git's reason on
    it (US2's claim, which this story must not have broken). Without this
    control, a change that routed *every* landing failure to an escalation would
    pass every other test in this file.
    """
    script = RefusedPushWorld(
        {NODE: [passing()]}, client=env.client, error=refusal.error
    )

    status = await run_epic(env, script, graph=one_node())

    assert script.open_attempts == 3, (
        "the retryable push failure no longer spends its retry budget: "
        f"{script.open_attempts} attempt(s)"
    )
    assert script.escalation_requests == [], (
        "an ordinary push failure paged an operator; US3 carves out one cause, "
        "not the class"
    )
    assert states(status)[NODE] == NodeState.KILLED
    assert flat(refusal.rejection) in flat(status.nodes[NODE].terminal_reason or "")


# --- T019 [US3] (spec US3-S5, FR-008, trap 7) ---------------------------------


def _merge_gated_pair() -> Any:
    """`us1`, the node whose push is refused; `us2`, waiting on it to merge.

    A merge-gated edge is the shape the cascade actually has: `us2` cannot
    dispatch until `us1` *merges*, so at the moment `us1`'s push is refused it
    is PENDING — dispatched by nothing, salvageable from nothing — and a `us1`
    that ends KILLED takes it with it through `_lock_out_dependents`. That is
    the cost the spec puts at three siblings, reduced to the smallest graph that
    still has it. `us3` depends on nothing and is the control inside the
    control: it must be unaffected either way.
    """
    return make_graph(
        [
            make_node("us1", "US1"),
            make_node("us2", "US2", depends_on_merged=["us1"]),
            make_node("us3", "US3"),
        ]
    )


async def test_no_pending_sibling_is_killed_when_a_node_escalates(
    env: WorkflowEnvironment, refusal: Refusal
) -> None:
    """US3-S5: the siblings are still there when the operator answers.

    Examined twice, because the claim has two halves and only one of them is
    visible at the end.

    While the page is open: `us2` is PENDING. Nothing has locked its edge out,
    because `us1` has not ended — which is the whole difference between a page
    and a kill, and the reason the view is taken from inside `send_escalation`
    rather than from the final status.

    After the operator clears the stale ref and presses retry: the push that
    follows succeeds, `us1` lands, and `us2` dispatches and lands behind it. No
    node in the graph was ever killed. Before this story `us1` died on the
    refusal after three attempts, `us2` died with it having never run, and the
    work `us1` had already done and verified was thrown away.
    """
    script = RefConflictWorld(
        {"us1": [passing()], "us2": [passing()], "us3": [passing()]},
        client=env.client,
        error=refusal.error,
        failures=1,
        press=EscalationChoice.RETRY.value,
    )

    status = await run_epic(env, script, graph=_merge_gated_pair())

    [view] = script.escalation_views
    during = states(view)
    assert during["us1"] not in {NodeState.KILLED, NodeState.FAILED}
    assert during["us2"] == NodeState.PENDING, (
        "the sibling waiting on this node was already gone when the operator "
        f"was asked: {during}"
    )

    # The grant put the node back to work: one refused push, one that landed.
    assert script.open_attempts == 2
    assert states(status) == {
        "us1": NodeState.MERGED,
        "us2": NodeState.MERGED,
        "us3": NodeState.MERGED,
    }
    assert script.escalation_requests[0].node_id == "us1"
    # RETRY was offered, or the press could not have been honoured (079-US1).
    assert EscalationChoice.RETRY.value in {
        str(choice) for choice in script.escalation_requests[0].choices
    }


async def test_the_epic_is_not_stopped_by_one_nodes_ref_conflict(
    env: WorkflowEnvironment, refusal: Refusal
) -> None:
    """US3-S5, the other direction: an unrelated sibling runs regardless.

    `us3` depends on nothing, so a ref conflict on `us1` is none of its
    business. The operator kills `us1` — the harshest answer that is not
    `KILL_EPIC` — and the epic still runs `us3` to a landing. A "kill" that
    stopped the epic would satisfy every assertion about `us1` and none about
    what this story is for.
    """
    script = RefConflictWorld(
        {"us1": [passing()], "us2": [passing()], "us3": [passing()]},
        client=env.client,
        error=refusal.error,
        failures=1,
        press=EscalationChoice.KILL.value,
    )

    status = await run_epic(env, script, graph=_merge_gated_pair())

    assert states(status)["us1"] == NodeState.KILLED
    assert states(status)["us3"] == NodeState.MERGED
    # us2 was merge-gated on a node that will never merge, so it ends locked
    # out — by the operator's answer, which is a decision, not by a retry
    # policy running out three attempts into a refusal nobody was told about.
    assert states(status)["us2"] == NodeState.KILLED
