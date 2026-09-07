"""127-US1 — the housekeeping report stops overwriting the cause.

A node whose push git refused carries git's own diagnosis in `terminal_reason`
(100-US2's whole point). 126-US2 then archives the dead branch and clears the
live ref on the way out, and assigns the archive-and-clear report OVER that
same field — so the operator reading the killed node sees what the factory
tidied up after the death and not why it died. 126-US2's own docstring
(`factory/workgraph/workflow.py:3239`) states `terminal_reason` carries git's
diagnosis; the overwrite contradicts it.

The rule (spec 127's truth table): `terminal_reason` carries the cause and
only the cause; the housekeeping report gets its own field beside it. Four
combinations, pinned across this module and `tests/test_interpreter.py`:

- **T001 (US1-S1, FR-001/FR-003)** — real git end to end. A real refusal, a
  real refusal record, the operator's KILL, and the archive: the record keeps
  git's diagnosis, the report is readable beside it, and the `epic_status`
  answer carries both. The record half is observed while the page is open —
  the cause is on the record *before* any housekeeping ran, which is the fact
  the overwrite used to destroy.
- **T002 (US1-S4, FR-002, trap 1)** — the control that matters most. The kill
  path inside `_escalate_ref_conflict` reaches
  `_archive_and_clear_remote_branch` directly and never `_close_out`, so a fix
  applied only to `_close_out` — the site the findings file names — passes
  T001 and fails this one.
- **T003 (US1-S2, FR-003, trap 4)** — the empty-report control. Most nodes
  have nothing to tidy; a cause and an empty report must read exactly as they
  did before this story.
- **T004 (US1-S3, FR-004)** — the never-promote control, through `_close_out`:
  a report with no cause stays out of `terminal_reason`. The absence of a
  cause is itself the honest answer.
- **T004b** — the same never-promote control with the *real* archive activity
  against a real bare origin, so the report an operator would actually read is
  the one shown landing in the new field.

The findings file calls the refusing method `_handle_push_refusal`; that name
is not in the tree — 126-US3 renamed it `_escalate_ref_conflict`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from temporalio import activity
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment

from factory.activities.agent_activities import (
    ArchiveAndClearRemoteBranchInput,
    archive_and_clear_remote_branch,
)
from factory.activities.merge_activities import (
    LANDING_REF_CONFLICT,
    OpenLandingPrInput,
)
from factory.activities.notify_activities import SendEscalationInput, SentEscalation
from factory.verify.models import EscalationChoice
from factory.workgraph.models import EpicState, NodeState
from factory.workgraph.workflow import EpicWorkflow
from factory.workgraph.worktree import WorktreeError, push_branch
from tests.target_repo import git_env  # noqa: F401 — re-exported for git fixtures
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
from tests.test_100_push_reports_refusal import (  # noqa: F401 — fixtures re-exported
    BRANCH,
    NODE,
    Refusal,
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
from tests.test_epic_escalation_child import ladder_fails

#: The report a scripted archive hands back when a test asks for work to
#: report. Wording modelled on the real activity's kept-ref line
#: (`worktree._clear_remote_branch`), which is the shape an operator reads.
KEPT_REF_REPORT = [
    "archived branch",
    f"kept origin branch {BRANCH} at abcdef123456: no archive ref of this node "
    "holds that commit, so nothing else carries its content (FR-002)",
]


# --- worlds -------------------------------------------------------------------


class RefusedArchiveWorld(ScriptedWorld):
    """The landing push git refused, with the archive activity under the test's hand.

    `open_landing_pr` raises exactly what the real activity raises for a
    non-fast-forward refusal — `ApplicationError(str(exc), type=LANDING_REF_CONFLICT,
    non_retryable=True) from exc` over a `WorktreeError` a real git really
    wrote — which is what routes the node into `_escalate_ref_conflict`.

    `archive_report` is what the scripted `archive_and_clear_remote_branch`
    answers. The default is the empty report most nodes produce; a non-empty
    value drives the overwrite sites with a report, which the interpreter suite
    never did before this story (its stub answered `[]` unconditionally, so
    `if report:` had never been true under it).

    `send_escalation` takes a view of the whole epic while the page is open,
    the way 100's `RefConflictWorld` does: the cause is written before the page
    goes out, so a view taken then is the record *before* any housekeeping.
    """

    def __init__(
        self,
        script: dict[str, list[Any]],
        *,
        error: WorktreeError,
        archive_report: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(script, **kwargs)
        self.error = error
        self.archive_report = list(archive_report or [])
        self.archive_requests: list[Any] = []
        self.escalation_views: list[Any] = []

    def activities(self) -> list[Any]:
        world = self
        inherited = super().activities()
        wrapped = {"open_landing_pr", "archive_and_clear_remote_branch",
                   "send_escalation"}
        real = {_activity_name(fn): fn for fn in inherited}

        @activity.defn(name="open_landing_pr")
        async def open_landing_pr_(request: OpenLandingPrInput) -> Any:
            world._log("open_landing_pr", request.node_id)
            world.landing_requests.append(request)
            raise ApplicationError(
                str(world.error), type=LANDING_REF_CONFLICT, non_retryable=True
            ) from world.error

        @activity.defn(name="archive_and_clear_remote_branch")
        async def archive_and_clear_remote_branch_(
            request: ArchiveAndClearRemoteBranchInput,
        ) -> list[str]:
            world._log("archive_and_clear_remote_branch", request.node_id)
            world.archive_requests.append(request)
            return list(world.archive_report)

        @activity.defn(name="send_escalation")
        async def send_escalation_(request: SendEscalationInput) -> SentEscalation:
            world.escalation_views.append(
                await world.handle.query(EpicWorkflow.epic_status)
            )
            return await real["send_escalation"](request)

        return [fn for fn in inherited if _activity_name(fn) not in wrapped] + [
            open_landing_pr_,
            archive_and_clear_remote_branch_,
            send_escalation_,
        ]


class KillWithReportWorld(ScriptedWorld):
    """The ordinary ladder-exhaustion kill, with an archive that has news.

    Only the archive stub is overridden, and only to let a test hand it a
    report; every other activity is the shared fake's. This is the path through
    `_close_out` — salvage, sweep, then the archive on the terminal state — so
    between it and `RefusedArchiveWorld` both overwrite sites are driven with a
    non-empty report.
    """

    def __init__(
        self,
        script: dict[str, list[Any]],
        *,
        archive_report: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(script, **kwargs)
        self.archive_report = list(archive_report or [])
        self.archive_requests: list[Any] = []

    def activities(self) -> list[Any]:
        world = self
        inherited = super().activities()

        @activity.defn(name="archive_and_clear_remote_branch")
        async def archive_and_clear_remote_branch_(
            request: ArchiveAndClearRemoteBranchInput,
        ) -> list[str]:
            world._log("archive_and_clear_remote_branch", request.node_id)
            world.archive_requests.append(request)
            return list(world.archive_report)

        return [
            fn
            for fn in inherited
            if _activity_name(fn) != "archive_and_clear_remote_branch"
        ] + [archive_and_clear_remote_branch_]


# --- T001 [US1] (spec US1-S1, FR-001, FR-003) ---------------------------------


async def test_git_refusal_survives_the_archive_on_the_record_and_the_query(
    env: WorkflowEnvironment, refusal: Refusal
) -> None:
    """The killed node says why it died, and says separately what was tidied.

    Real git, real origin, real refusal — the exact sequence 126's plan
    documents: a stale tip on origin refuses the push, the operator answers
    KILL, the kill path archives the branch and clears the live ref. Before
    this story the archive report landed on `terminal_reason` and git's
    diagnosis was gone.

    The record half and the query half of FR-001 are separate assertions. The
    query half is the final `epic_status` answer, which must carry both fields
    populated — a field that stopped at `NodeRecord` would reach no renderer,
    which is the defect in a new slot.
    """
    world = RefusedArchiveWorld(
        {NODE: [passing()]},
        client=env.client,
        error=refusal.error,
        archive_report=KEPT_REF_REPORT,
        press=EscalationChoice.KILL.value,
    )

    status = await run_epic(env, world, graph=one_node())

    # The path is the one this story is about: refused push, paged operator,
    # KILL, archive.
    assert len(world.escalation_requests) == 1
    assert len(world.archive_requests) == 1
    assert states(status)[NODE] == NodeState.KILLED
    assert status.epic_state == EpicState.COMPLETED

    # Record half, observed while the page was open — before housekeeping ran.
    [during] = world.escalation_views
    reason_on_record = during.nodes[NODE].terminal_reason or ""
    assert flat(refusal.rejection) in flat(reason_on_record), (
        f"git's refusal was not on the record before the page went out: "
        f"{reason_on_record!r}"
    )

    # Query half: both fields, on the same answer, each carrying its own fact.
    node = status.nodes[NODE]
    assert node.terminal_reason is not None
    assert flat(refusal.rejection) in flat(node.terminal_reason)
    assert BRANCH in node.terminal_reason
    # ...and the report is beside it, not over it.
    report = "; ".join(KEPT_REF_REPORT)
    assert node.housekeeping_report == report
    assert flat(refusal.rejection) not in flat(node.housekeeping_report)
    assert "kept origin branch" not in flat(node.terminal_reason)


# --- T002 [US1] (spec US1-S4, FR-002, trap 1) — the control -------------------


async def test_kill_through_escalate_ref_conflict_keeps_the_separation(
    env: WorkflowEnvironment, refusal: Refusal
) -> None:
    """The overwrite site the finding does not name is repaired too.

    `_escalate_ref_conflict`'s kill path calls `_remove_worktree` and then
    `_archive_and_clear_remote_branch` directly — it never reaches `_close_out`,
    whose archive site the findings file cites. A fix applied only to
    `_close_out` passes every test that drives the ordinary kill and leaves
    this exact case — the one that cost the four hours — overwriting still. The
    report here is non-empty so the `if report:` guard is genuinely taken on
    this path.
    """
    world = RefusedArchiveWorld(
        {NODE: [passing()]},
        client=env.client,
        error=refusal.error,
        archive_report=KEPT_REF_REPORT,
        press=EscalationChoice.KILL.value,
    )

    status = await run_epic(env, world, graph=one_node())

    assert states(status)[NODE] == NodeState.KILLED
    assert world.archive_requests, "the kill path never ran the archive"

    node = status.nodes[NODE]
    # git's diagnosis survived the archive.
    assert node.terminal_reason is not None
    assert flat(refusal.rejection) in flat(node.terminal_reason)
    # and the report is in its own field, verbatim, not merged into the cause.
    assert node.housekeeping_report == "; ".join(KEPT_REF_REPORT)
    assert "kept origin branch" not in flat(node.terminal_reason)


# --- T003 [US1] (spec US1-S2, FR-003, trap 4) — the empty-report control ------


async def test_an_empty_report_leaves_the_cause_exactly_as_it_was(
    env: WorkflowEnvironment, refusal: Refusal
) -> None:
    """A node with nothing to tidy reads exactly as it does now (trap 4).

    Both overwrite sites are guarded by `if report:`; the guard is what has
    always kept a cause intact when the archive had nothing to say. This is
    most nodes. The regression that would matter here is wider than the defect:
    a refactor that unconditionally clears `terminal_reason` turns every
    ordinary death into an unexplained one.
    """
    world = RefusedArchiveWorld(
        {NODE: [passing()]},
        client=env.client,
        error=refusal.error,
        # archive_report unset: the empty report most nodes produce.
        press=EscalationChoice.KILL.value,
    )

    status = await run_epic(env, world, graph=one_node())

    node = status.nodes[NODE]
    assert states(status)[NODE] == NodeState.KILLED
    # The cause is unchanged from today's value: git's refusal, untouched.
    assert node.terminal_reason is not None
    assert flat(refusal.rejection) in flat(node.terminal_reason)
    # And the new field is empty — there was nothing to report.
    assert not node.housekeeping_report


# --- T004 [US1] (spec US1-S3, FR-004) — the never-promote control -------------


async def test_a_report_is_never_promoted_into_a_cause(
    env: WorkflowEnvironment,
) -> None:
    """An ordinary kill that never failed a push stays causeless (US1-S3).

    The operator's KILL press is a decision, not a cause: today the node ends
    with `terminal_reason is None`, and the archive report — when there is one
    — is promoted into the empty slot as if the tidy-up had ended the node.
    The absence of a cause is itself the honest answer, and the report belongs
    in its own field.
    """
    world = KillWithReportWorld(
        {NODE: ladder_fails()},
        client=env.client,
        archive_report=KEPT_REF_REPORT,
        press=EscalationChoice.KILL.value,
    )

    status = await run_epic(env, world, graph=one_node())

    node = status.nodes[NODE]
    assert states(status)[NODE] == NodeState.KILLED
    assert node.terminal_reason is None
    assert node.housekeeping_report == "; ".join(KEPT_REF_REPORT)


# --- and the real archive, for the record -------------------------------------


@pytest.fixture
def runtime_root(factory_root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the real archive activity's root resolution at this test's root.

    `push_branch` is called by the test with an explicit `factory_root`; the
    activity resolves its own from the environment (constitution IX — the
    declaration, never the process's cwd). Both have to name one directory, or
    the archive would refuse a worktree that is merely somewhere else.
    """
    monkeypatch.setenv("ERGANE_ROOT", str(factory_root))
    monkeypatch.setenv("FACTORY_ROOT", str(factory_root))
    return factory_root


async def test_the_real_archive_report_lands_in_the_new_field(
    env: WorkflowEnvironment,
    repo: Path,
    factory_root: Path,
    tmp_path: Path,
    runtime_root: Path,
) -> None:
    """The scripted worlds stand in for a report the real activity writes.

    This test runs the real `archive_and_clear_remote_branch` against the real
    bare origin the `repo` fixture builds, through the ordinary kill path, and
    asserts the report an operator would actually read reaches the new field
    with `terminal_reason` still `None` — the end-to-end shape the story pastes
    as committed evidence.
    """
    bare = _origin(repo, tmp_path)
    del bare
    _prepare(repo, factory_root)
    push_branch(repo, EPIC_ID, NODE, factory_root=factory_root)

    class RealArchiveKill(KillWithReportWorld):
        def activities(self) -> list[Any]:
            inherited = [
                fn
                for fn in super().activities()
                if _activity_name(fn) != "archive_and_clear_remote_branch"
            ]
            return inherited + [archive_and_clear_remote_branch]

    world = RealArchiveKill(
        {NODE: ladder_fails()},
        client=env.client,
        press=EscalationChoice.KILL.value,
    )

    status = await run_epic(
        env, world, graph=make_graph([make_node(NODE, "US1")], target_repo=str(repo))
    )

    node = status.nodes[NODE]
    assert states(status)[NODE] == NodeState.KILLED
    assert node.terminal_reason is None
    assert node.housekeeping_report is not None
    # The real report names the branch twice over — the live name it cleared
    # and the archive name it kept it under.
    assert BRANCH in node.housekeeping_report
    assert "deleted origin branch" in node.housekeeping_report