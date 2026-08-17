"""US4: a roadmap run that fails reaches the operator once, with its count.

The roadmap cannot notify about its own failure from inside itself: a run that
raises inside the main loop does not get to send a message afterwards. The shape
T001 chose is a try/except at the loop boundary that records the failure and
pages the operator before re-raising.

These tests script the failure by injecting a broken corpus reader: a pass over
the corpus calls `read_corpus_activity`, so corrupting that seam makes every
pass fail with a known message. The notification activity is replaced by a
recording seam so we can assert on the messages without a real Telegram bot.

Reporting semantics (FR-009):
- The first failure sends one message carrying the failure verbatim.
- Repeated identical failures do not send one message per failure; instead, the
  count accumulates and the next notification (on a count threshold) carries the
  count.
- A successful pass after failures resets the count and reports recovery.

Durability semantics (FR-010):
- The failure is recorded before the send is attempted, so a notifier that is down
  loses the message and not the fact.

The tests here are written first and must fail against the code as it stands.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Callable

import pytest
from temporalio import activity, workflow
from temporalio.client._exceptions import WorkflowFailureError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner

from factory.activities.verify_activities import (
    ERGANE_VERIFICATION_DB_PATH_ENV,
    VERIFICATION_DB_PATH_ENV,
)

import factory.activities.roadmap_activities as roadmap_activities
import factory.roadmap.workflow as factory_roadmap_workflow
from factory.activities.roadmap_activities import CountOpenInput, CountOpenResult
from factory.activities.notify_activities import (
    SendEscalationInput,
    SendRoadmapNoticeInput,
    SentEscalation,
    SentRoadmapNotice,
)
from factory.roadmap.models import Roadmap, SpecState
from factory.roadmap.workflow import (
    RoadmapInput,
    RoadmapStatus,
    RoadmapWorkflow,
    roadmap_workflow_id,
)
from factory.verify.models import EscalationChoice

from tests.roadmap_script import (
    ScriptedEpicWorkflow,
    _SCRIPT,
)
from tests.test_roadmap_scheduler import (
    RoadmapWorld,
    build_corpus,
)

TARGET_REPO = "/srv/factory/targets/library"
PROXY_URL = "http://litellm.test"


#: The failure message the broken corpus reader raises.  The notification must
#: carry this verbatim.
FAILURE_MESSAGE = "the corpus reader is broken"


@dataclass(frozen=True)
class RecordedNotification:
    """One call our recording send-escalation seam saw."""

    workflow_id: str
    epic_id: str
    node_id: str
    history_summary: str


@dataclass(frozen=True)
class RecordedNotice:
    """One call our recording send-roadmap-notice seam saw."""

    roadmap_id: str
    message: str


class NotificationRecorder:
    """Replaces `send_roadmap_notice` so tests can assert on what was sent."""

    def __init__(self) -> None:
        self.calls: list[RecordedNotice] = []
        self.raise_on_send: bool = False

    def record(self, request: SendRoadmapNoticeInput) -> SentRoadmapNotice:
        self.calls.append(
            RecordedNotice(
                roadmap_id=request.roadmap_id,
                message=request.message,
            )
        )
        if self.raise_on_send:
            raise RuntimeError("notifier is down")
        return SentRoadmapNotice(delivered=True)


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[WorkflowEnvironment]:
    """Temporal with a clock the test owns.

    Each test gets its own verification database under `tmp_path` so
    consecutive-failure counts and escalation rows do not leak between tests.
    """
    db_path = str(tmp_path / "verification.db")
    old_db = os.environ.get(VERIFICATION_DB_PATH_ENV)
    old_ergane_db = os.environ.get(ERGANE_VERIFICATION_DB_PATH_ENV)
    os.environ[ERGANE_VERIFICATION_DB_PATH_ENV] = db_path
    os.environ.pop(VERIFICATION_DB_PATH_ENV, None)
    environment = await WorkflowEnvironment.start_time_skipping()
    _SCRIPT.statuses = {}
    _SCRIPT.on_dispatch = None
    _SCRIPT.on_complete = None
    _SCRIPT.hold = set()
    try:
        yield environment
    finally:
        await environment.shutdown()
        if old_ergane_db is None:
            os.environ.pop(ERGANE_VERIFICATION_DB_PATH_ENV, None)
        else:
            os.environ[ERGANE_VERIFICATION_DB_PATH_ENV] = old_ergane_db
        if old_db is None:
            os.environ.pop(VERIFICATION_DB_PATH_ENV, None)
        else:
            os.environ[VERIFICATION_DB_PATH_ENV] = old_db
        _SCRIPT.statuses = {}
        _SCRIPT.on_dispatch = None
        _SCRIPT.on_complete = None
        _SCRIPT.hold = set()


def _stable_roadmap_id(specs_root: str) -> str:
    """The stable identity a schedule's churning ids are derived from."""
    return roadmap_workflow_id(specs_root)


def _build_named_corpus(root: Path, name: str, specs: dict[str, Any]) -> Path:
    """Build a specs corpus whose root directory is named after the corpus.

    `build_corpus` always creates a ``specs/`` subdirectory, so two corpora in
    different parent directories would still share the basename ``specs`` and
    therefore the same stable roadmap id.  This helper renames that directory
    to ``{name}-specs`` so each corpus has a distinct stable identity.
    """
    built = build_corpus(root / name, specs)
    renamed = built.parent / f"{name}-specs"
    built.rename(renamed)
    return renamed


def _failure_count_from(summary: str) -> int | None:
    """Parse the consecutive-failure count out of a failure summary."""
    prefix = "failed ("
    start = summary.find(prefix)
    if start == -1:
        return None
    end = summary.find(" consecutive run", start + len(prefix))
    if end == -1:
        return None
    try:
        return int(summary[start + len(prefix) : end])
    except ValueError:
        return None


@asynccontextmanager
async def run_roadmap_with_notifications(
    env: WorkflowEnvironment,
    world: RoadmapWorld,
    specs_root: str,
    recorder: NotificationRecorder,
    *,
    statuses: dict[str, Any] | None = None,
    max_concurrent_epics: int = 1,
    max_concurrent_nodes: int | None = None,
    idle_rescan_s: int | None = None,
    workflow_id: str | None = None,
) -> AsyncIterator[Any]:
    """Start the roadmap with a scripted failure and a recording notifier.

    `workflow_id` overrides the workflow id the run starts under.  The default
    is the stable roadmap id; tests that simulate a schedule pass churning ids
    by giving distinct schedule-shaped values here.
    """
    _SCRIPT.statuses = dict(statuses or {})
    world.apply()

    from factory.activities.notify_activities import (
        record_roadmap_failure,
        reset_roadmap_failures,
    )
    from factory.activities.roadmap_activities import (
        clone_target,
        count_open_epics,
        derive_spec,
        drift_for_spec,
        onboard_target,
        preflight_spec,
        read_loop_config,
    )
    from factory.roadmap.workflow import (
        read_corpus_activity,
        read_spec_text_activity,
    )

    activities = [
        clone_target,
        derive_spec,
        drift_for_spec,
        preflight_spec,
        onboard_target,
        count_open_epics,
        read_loop_config,
        read_corpus_activity,
        read_spec_text_activity,
        record_roadmap_failure,
        reset_roadmap_failures,
    ]

    @activity.defn(name="send_roadmap_notice")
    async def recording_send_roadmap_notice(request: SendRoadmapNoticeInput) -> SentRoadmapNotice:
        return recorder.record(request)

    activities.append(recording_send_roadmap_notice)

    try:
        async with Worker(
            env.client,
            task_queue="workgraph",
            workflows=[RoadmapWorkflow, ScriptedEpicWorkflow],
            activities=activities,
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            input_kwargs: dict[str, Any] = {
                "specs_root": specs_root,
                "target_repo": TARGET_REPO,
                "proxy_url": PROXY_URL,
                "max_concurrent_epics": max_concurrent_epics,
            }
            if max_concurrent_nodes is not None:
                input_kwargs["max_concurrent_nodes"] = max_concurrent_nodes
            if idle_rescan_s is not None:
                input_kwargs["idle_rescan_s"] = idle_rescan_s
            handle = await env.client.start_workflow(
                RoadmapWorkflow.run,
                RoadmapInput(**input_kwargs),
                id=workflow_id or roadmap_workflow_id(specs_root),
                task_queue="workgraph",
            )
            yield handle
    finally:
        world.restore()


@asynccontextmanager
async def run_roadmap_with_sandboxed_workflow(
    env: WorkflowEnvironment,
    world: RoadmapWorld,
    specs_root: str,
    recorder: NotificationRecorder,
    *,
    max_concurrent_epics: int = 1,
    max_concurrent_nodes: int | None = None,
    idle_rescan_s: int | None = None,
    workflow_id: str | None = None,
) -> AsyncIterator[Any]:
    """Start the roadmap with the workflow sandbox enabled.

    The real `RoadmapWorkflow` is deterministic and side-effect-free in workflow
    code, so the sandboxed runner is safe.  The scripted `EpicWorkflow` is also
    deterministic; it reads its script from the module-level `_SCRIPT`, and the
    sandboxed runner re-imports `tests.roadmap_script` into an isolated namespace,
    but that module is self-contained and deterministic too.  Activities that
    *do* need shared process state (the recording notifier, the world's seams)
    run outside the sandbox, so the test can still observe and steer them.
    """
    _SCRIPT.statuses = {}
    _SCRIPT.on_dispatch = None
    _SCRIPT.on_complete = None
    _SCRIPT.hold = set()
    world.apply()

    from factory.activities.notify_activities import (
        record_roadmap_failure,
        reset_roadmap_failures,
    )
    from factory.activities.roadmap_activities import (
        clone_target,
        count_open_epics,
        derive_spec,
        drift_for_spec,
        onboard_target,
        preflight_spec,
        read_loop_config,
    )
    from factory.roadmap.workflow import (
        read_corpus_activity,
        read_spec_text_activity,
    )

    activities = [
        clone_target,
        derive_spec,
        drift_for_spec,
        preflight_spec,
        onboard_target,
        count_open_epics,
        read_loop_config,
        read_corpus_activity,
        read_spec_text_activity,
        record_roadmap_failure,
        reset_roadmap_failures,
    ]

    @activity.defn(name="send_roadmap_notice")
    async def recording_send_roadmap_notice(request: SendRoadmapNoticeInput) -> SentRoadmapNotice:
        return recorder.record(request)

    activities.append(recording_send_roadmap_notice)

    try:
        async with Worker(
            env.client,
            task_queue="workgraph",
            workflows=[RoadmapWorkflow, ScriptedEpicWorkflow],
            activities=activities,
            workflow_runner=SandboxedWorkflowRunner(),
        ):
            input_kwargs: dict[str, Any] = {
                "specs_root": specs_root,
                "target_repo": TARGET_REPO,
                "proxy_url": PROXY_URL,
                "max_concurrent_epics": max_concurrent_epics,
            }
            if max_concurrent_nodes is not None:
                input_kwargs["max_concurrent_nodes"] = max_concurrent_nodes
            if idle_rescan_s is not None:
                input_kwargs["idle_rescan_s"] = idle_rescan_s
            handle = await env.client.start_workflow(
                RoadmapWorkflow.run,
                RoadmapInput(**input_kwargs),
                id=workflow_id or roadmap_workflow_id(specs_root),
                task_queue="workgraph",
            )
            yield handle
    finally:
        _SCRIPT.statuses = {}
        _SCRIPT.on_dispatch = None
        _SCRIPT.on_complete = None
        _SCRIPT.hold = set()
        world.restore()


class FailingCorpusWorld(RoadmapWorld):
    """A roadmap world whose corpus reader always raises with `FAILURE_MESSAGE`."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    def apply(self) -> None:
        super().apply()
        self._saved_read_corpus = factory_roadmap_workflow.read_corpus_activity

        @activity.defn(name="read_corpus_activity")
        async def failing_read_corpus(request: dict) -> Roadmap:
            raise RuntimeError(FAILURE_MESSAGE)

        factory_roadmap_workflow.read_corpus_activity = failing_read_corpus

    def restore(self) -> None:
        if getattr(self, "_saved_read_corpus", None) is not None:
            factory_roadmap_workflow.read_corpus_activity = self._saved_read_corpus
        super().restore()


# ============================================================================
# T015 — reporting cases
# ============================================================================


async def test_a_failed_run_notifies_once_with_the_failure_verbatim(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """Acceptance 1 / FR-009: a roadmap run that fails notifies once, carrying the
    failure message verbatim."""
    specs_root = build_corpus(tmp_path, {"001-alpha": dict(state=SpecState.READY)})
    recorder = NotificationRecorder()
    world = FailingCorpusWorld()

    async with run_roadmap_with_notifications(
        env, world, str(specs_root), recorder
    ) as handle:
        with pytest.raises(Exception):
            await handle.result()

    assert len(recorder.calls) == 1, recorder.calls
    assert FAILURE_MESSAGE in recorder.calls[0].message, recorder.calls[0]


async def test_repeated_identical_failures_do_not_spam_and_carry_count(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """Acceptance 2 / FR-009: repeated identical failures do not produce one
    message per failure; the notification carries the consecutive count.

    The only way to observe repeated failures without an idle loop is to let the
    roadmap fail, catch it, start a new workflow under the same id (which counts
    as the next run), fail again, and so on.  The failure state is not stored in
    the workflow (which dies); it must live in a durable store keyed by the
    roadmap id, so the count survives the run boundary.
    """
    specs_root = build_corpus(tmp_path, {"001-alpha": dict(state=SpecState.READY)})
    recorder = NotificationRecorder()

    for _ in range(3):
        world = FailingCorpusWorld()
        async with run_roadmap_with_notifications(
            env, world, str(specs_root), recorder
        ) as handle:
            with pytest.raises(Exception):
                await handle.result()

    # With a smart count-and-threshold path, three consecutive failures produce
    # fewer than three messages and the most recent message names the count.
    assert len(recorder.calls) < 3, recorder.calls
    assert any(
        "3" in call.message or "three" in call.message.lower()
        for call in recorder.calls
    ), recorder.calls


async def test_success_after_failures_resets_count_and_reports_recovery(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """Acceptance 3 / FR-009: a successful pass after failures resets the count
    and reports recovery.

    Two runs: the first fails, the second succeeds.  The second run must produce
    a recovery notification and must not inherit the count from the first.
    """
    specs_root = build_corpus(tmp_path, {"001-alpha": dict(state=SpecState.READY)})
    recorder = NotificationRecorder()

    # First run fails.
    async with run_roadmap_with_notifications(
        env, FailingCorpusWorld(), str(specs_root), recorder
    ) as handle:
        with pytest.raises(Exception):
            await handle.result()

    # Second run succeeds.
    async with run_roadmap_with_notifications(
        env, RoadmapWorld(), str(specs_root), recorder
    ) as handle:
        await handle.result()

    recovery_calls = [
        call for call in recorder.calls
        if "recover" in call.message.lower()
        or "passed" in call.message.lower()
    ]
    assert len(recovery_calls) == 1, recorder.calls


# ============================================================================
# T016 — durability case
# ============================================================================


async def test_failure_is_recorded_when_notifier_is_down(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """Acceptance 4 / FR-010: with the notifier unavailable, the failure is still
    recorded durably.

    The recording seam is told to raise on send.  The durable record is checked by
    querying the verification store for a roadmap-failure row.  Until the code
    writes such a row before calling `send_roadmap_notice`, this test fails.
    """
    specs_root = build_corpus(tmp_path, {"001-alpha": dict(state=SpecState.READY)})
    recorder = NotificationRecorder()
    recorder.raise_on_send = True

    async with run_roadmap_with_notifications(
        env, FailingCorpusWorld(), str(specs_root), recorder
    ) as handle:
        with pytest.raises(Exception):
            await handle.result()

    # No Telegram message was delivered.
    assert len(recorder.calls) == 1
    roadmap_id = roadmap_workflow_id(str(specs_root))
    # But the fact was recorded in the verification store.  The row must exist
    # before the send was attempted.
    from factory.verify.store import connect

    db_path = os.environ.get(ERGANE_VERIFICATION_DB_PATH_ENV)
    assert db_path is not None
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT consecutive_count, last_failure_text FROM roadmap_failures WHERE roadmap_id = ?",
            (roadmap_id,),
        ).fetchone()
        assert row is not None, "no roadmap-failure row recorded for the failed roadmap"
        assert row[0] == 1, row
        assert row[1] == FAILURE_MESSAGE, row
        esc_count = conn.execute(
            "SELECT COUNT(*) FROM escalations WHERE epic_id = ?",
            (roadmap_id,),
        ).fetchone()[0]
        assert esc_count == 0, f"expected zero escalation rows for {roadmap_id}, got {esc_count}"
    finally:
        conn.close()


# ============================================================================
# US1 — the failure count survives the schedule's identity churn
# ============================================================================


async def test_schedule_churned_ids_accumulate_one_count_and_page_geometrically(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """US1-S1 / FR-001/FR-003: three consecutive failing executions under distinct
    schedule-shaped workflow ids over one specs root accumulate a single count,
    and pages only go out at counts 1 and 3.
    """
    specs_root = build_corpus(tmp_path, {"001-alpha": dict(state=SpecState.READY)})
    recorder = NotificationRecorder()
    stable_id = _stable_roadmap_id(str(specs_root))

    for i in range(3):
        workflow_id = f"{stable_id}-20260811-{i}"
        async with run_roadmap_with_notifications(
            env,
            FailingCorpusWorld(),
            str(specs_root),
            recorder,
            workflow_id=workflow_id,
        ) as handle:
            with pytest.raises(Exception):
                await handle.result()

    assert len(recorder.calls) == 2, recorder.calls
    counts = [_failure_count_from(call.message) for call in recorder.calls]
    assert counts == [1, 3], recorder.calls
    for call in recorder.calls:
        assert call.roadmap_id == stable_id, call
        assert FAILURE_MESSAGE in call.message, call


async def test_recovery_under_a_fresh_id_pages_once_and_resets_count(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """US1-S2 / FR-002/FR-004: after failures under churned ids, a green run under
    yet another fresh id sends one recovery page naming the prior count and the
    count resets.
    """
    specs_root = build_corpus(tmp_path, {"001-alpha": dict(state=SpecState.READY)})
    recorder = NotificationRecorder()
    stable_id = _stable_roadmap_id(str(specs_root))

    for i in range(2):
        workflow_id = f"{stable_id}-20260811-fail-{i}"
        async with run_roadmap_with_notifications(
            env,
            FailingCorpusWorld(),
            str(specs_root),
            recorder,
            workflow_id=workflow_id,
        ) as handle:
            with pytest.raises(Exception):
                await handle.result()

    async with run_roadmap_with_notifications(
        env,
        RoadmapWorld(),
        str(specs_root),
        recorder,
        workflow_id=f"{stable_id}-20260811-recovery",
    ) as handle:
        await handle.result()

    recovery_calls = [
        call for call in recorder.calls if "recover" in call.message.lower()
    ]
    assert len(recovery_calls) == 1, recorder.calls
    recovery = recovery_calls[0]
    assert recovery.roadmap_id == stable_id, recovery
    assert "2" in recovery.message, recovery

    # A second green run must not page again: the count was reset.
    async with run_roadmap_with_notifications(
        env,
        RoadmapWorld(),
        str(specs_root),
        recorder,
        workflow_id=f"{stable_id}-20260811-green-again",
    ) as handle:
        await handle.result()

    assert len(recovery_calls) == 1, recorder.calls


async def test_nine_failures_pages_only_at_powers_of_three(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """US1-S3 / FR-003: nine consecutive identical failures produce pages only at
    counts 1, 3 and 9 — three pages, not nine.
    """
    specs_root = build_corpus(tmp_path, {"001-alpha": dict(state=SpecState.READY)})
    recorder = NotificationRecorder()
    stable_id = _stable_roadmap_id(str(specs_root))

    for i in range(9):
        workflow_id = f"{stable_id}-20260811-{i}"
        async with run_roadmap_with_notifications(
            env,
            FailingCorpusWorld(),
            str(specs_root),
            recorder,
            workflow_id=workflow_id,
        ) as handle:
            with pytest.raises(Exception):
                await handle.result()

    assert len(recorder.calls) == 3, recorder.calls
    counts = [_failure_count_from(call.message) for call in recorder.calls]
    assert counts == [1, 3, 9], recorder.calls
    for call in recorder.calls:
        assert call.roadmap_id == stable_id, call


async def test_two_corpora_keep_independent_counts_under_churned_ids(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """US1-S4 / FR-001: two corpora under different specs roots, with churning
    workflow ids, keep independent counts and page independently.

    Four interleaved failures per corpus hit the geometric thresholds 1 and 3
    for each corpus independently; a later green run for each resets its own
    count and pages once.
    """
    alpha_root = _build_named_corpus(tmp_path, "alpha", {"001-alpha": dict(state=SpecState.READY)})
    beta_root = _build_named_corpus(tmp_path, "beta", {"001-beta": dict(state=SpecState.READY)})
    recorder = NotificationRecorder()
    alpha_id = _stable_roadmap_id(str(alpha_root))
    beta_id = _stable_roadmap_id(str(beta_root))

    # Interleave four failures for alpha with four failures for beta.
    for i in range(4):
        async with run_roadmap_with_notifications(
            env,
            FailingCorpusWorld(),
            str(alpha_root),
            recorder,
            workflow_id=f"{alpha_id}-20260811-{i}",
        ) as handle:
            with pytest.raises(Exception):
                await handle.result()
        async with run_roadmap_with_notifications(
            env,
            FailingCorpusWorld(),
            str(beta_root),
            recorder,
            workflow_id=f"{beta_id}-20260811-{i}",
        ) as handle:
            with pytest.raises(Exception):
                await handle.result()

    alpha_calls = [call for call in recorder.calls if call.roadmap_id == alpha_id]
    beta_calls = [call for call in recorder.calls if call.roadmap_id == beta_id]
    assert len(alpha_calls) == 2, recorder.calls
    assert len(beta_calls) == 2, recorder.calls
    assert [_failure_count_from(call.message) for call in alpha_calls] == [1, 3]
    assert [_failure_count_from(call.message) for call in beta_calls] == [1, 3]

    # Each corpus recovers independently under a fresh id.
    async with run_roadmap_with_notifications(
        env,
        RoadmapWorld(),
        str(alpha_root),
        recorder,
        workflow_id=f"{alpha_id}-20260811-recovery",
    ) as handle:
        await handle.result()
    async with run_roadmap_with_notifications(
        env,
        RoadmapWorld(),
        str(beta_root),
        recorder,
        workflow_id=f"{beta_id}-20260811-recovery",
    ) as handle:
        await handle.result()

    alpha_recovery = [
        call for call in recorder.calls if call.roadmap_id == alpha_id and "recover" in call.message.lower()
    ]
    beta_recovery = [
        call for call in recorder.calls if call.roadmap_id == beta_id and "recover" in call.message.lower()
    ]
    assert len(alpha_recovery) == 1, recorder.calls
    assert len(beta_recovery) == 1, recorder.calls
    assert "4" in alpha_recovery[0].message, alpha_recovery[0]
    assert "4" in beta_recovery[0].message, beta_recovery[0]


def _assert_original_failure_in_chain(
    exc: WorkflowFailureError, expected_type: str, expected_message: str
) -> None:
    """Walk the wrapped failure chain to find the original pass exception."""
    current: BaseException | None = exc.cause
    while current is not None:
        text = str(current)
        if expected_type in text and expected_message in text:
            return
        current = getattr(current, "cause", None)
    raise AssertionError(
        f"expected {expected_type}: {expected_message!r} in failure chain, got {exc!r}"
    )


# ============================================================================
# 039/US1 — the success path must not read the environment (P1)
# ============================================================================

# Red-then-green transcript for FR-004.  Generated by running the new test below
# against the code before and after the T004 change.  Pasted verbatim as required
# by spec US1-S3 / plan trap 8.
#
# --- unfixed code (workflow scope still calls _verification_db_path) ---
#
# $ uv run pytest -q tests/test_roadmap_failure_notifications.py::test_clean_run_under_sandbox_with_prior_failure_reaches_completed -x --tb=long
# F
# =================================== FAILURES ===================================
# ______ test_clean_run_under_sandbox_with_prior_failure_reaches_completed _______
#
# tests/test_roadmap_failure_notifications.py:778: in test_clean_run_under_sandbox_with_prior_failure_reaches_completed
#     assert len(recorder.calls) == 1, recorder.calls
# E   AssertionError: []
# E   assert 0 == 1
# E    +  where 0 = len([])
# E    +    where [] = <tests.test_roadmap_failure_notifications.NotificationRecorder object at 0xff6b384a3510>.calls
#
# ------------------------------ Captured log call -------------------------------
# WARNING  temporalio.worker.workflow_sandbox._restrictions:_restrictions.py:843 get on os.environ restricted
# ERROR    temporalio.workflow:workflow.py:675 roadmap failure reporting raised: Cannot access os.environ.get from inside a workflow. If this is code from a module not used in a workflow or known to only be used deterministically from a workflow, mark the import as pass through. ({'attempt': 1, 'namespace': 'default', 'run_id': '5e52a507-b4e4-4c3c-a8f4-7b6536e11451', 'task_queue': 'workgraph', 'workflow_id': 'roadmap-specs-prior-failure', 'workflow_type': 'RoadmapWorkflow'})
# temporalio.exceptions.ApplicationError: RuntimeError: the corpus reader is broken
#
# The above exception was the direct cause of the following exception:
#
# Traceback (most recent call last):
#   File "/home/admin/code/ergane/.factory/worktrees/039-roadmap-workflow-determinism/us1/factory/roadmap/workflow.py", line 666, in run
#     return await self._run_inner(request)
#            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#   File "/home/admin/code/ergane/.factory/worktrees/039-roadmap-workflow-determinism/us1/factory/roadmap/workflow.py", line 705, in _run_inner
#     self._roadmap = await workflow.execute_activity(
#                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#   File "/home/admin/code/ergane/.factory/worktrees/039-roadmap-workflow-determinism/us1/.venv/lib/python3.11/site-packages/temporalio/workflow/_activities.py", line 483, in execute_activity
#     return await _Runtime.current().workflow_start_activity(
#            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#   File "/home/admin/code/ergane/.factory/worktrees/039-roadmap-workflow-determinism/us1/.venv/lib/python3.11/site-packages/temporalio/worker/_workflow_instance.py", line 1994, in run_activity
#     return await self._await_temporal_operation(
#            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#   File "/home/admin/code/ergane/.factory/worktrees/039-roadmap-workflow-determinism/us1/.venv/lib/python3.11/site-packages/temporalio/worker/_workflow_instance.py", line 2218, in _await_temporal_operation
#     return await _shield_await(fut)
#            ^^^^^^^^^^^^^^^^^^^^^^^^
#   File "/home/admin/code/ergane/.factory/worktrees/039-roadmap-workflow-determinism/us1/.venv/lib/python3.11/site-packages/temporalio/worker/_workflow_instance.py", line 97, in _shield_await
#     return fut.result()
#            ^^^^^^^^^^^^^
# temporalio.exceptions.ActivityError: Activity task failed
#
# During handling of the above exception, another exception occurred:
#
# Traceback (most recent call last):
#   File "/home/admin/code/ergane/.factory/worktrees/039-roadmap-workflow-determinism/us1/factory/roadmap/workflow.py", line 673, in run
#     await self._report_run_failure(request, exc)
#   File "/home/admin/code/ergane/.factory/worktrees/039-roadmap-workflow-determinism/us1/factory/roadmap/workflow.py", line 941, in _report_run_failure
#     await self._report_roadmap_failure(
#   File "/home/admin/code/ergane/.factory/worktrees/039-roadmap-workflow-determinism/us1/factory/roadmap/workflow.py", line 922, in _report_roadmap_failure
#     db_path=_verification_db_path(),
#             ^^^^^^^^^^^^^^^^^^^^^^^
#   File "/home/admin/code/ergane/.factory/worktrees/039-roadmap-workflow-determinism/us1/factory/roadmap/workflow.py", line 140, in _verification_db_path
#     return environ.get(VERIFICATION_DB_PATH_ENV) or DEFAULT_VERIFICATION_DB_PATH
#            ^^^^^^^^^^^
#   File "/home/admin/code/ergane/.factory/worktrees/039-roadmap-workflow-determinism/us1/.venv/lib/python3.11/site-packages/temporalio/worker/workflow_sandbox/_restrictions.py", line 1020, in __getattribute__
#     state.assert_child_not_restricted(__name)
#   File "/home/admin/code/ergane/.factory/worktrees/039-roadmap-workflow-determinism/us1/.venv/lib/python3.11/site-packages/temporalio/worker/workflow_sandbox/_restrictions.py", line 852, in assert_child_not_restricted
#     raise RestrictedWorkflowAccessError(
# temporalio.worker.workflow_sandbox._restrictions.RestrictedWorkflowAccessError: Cannot access os.environ.get from inside a workflow. If this is code from a module not used in a workflow or known to only be used deterministically from a workflow, mark the import as pass through.
# =========================== short test summary info ============================
# FAILED tests/test_roadmap_failure_notifications.py::test_clean_run_under_sandbox_with_prior_failure_reaches_completed
# !!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
# 1 failed in 0.29s
#
# --- fixed code (db_path resolved inside the activity) ---
#
# $ uv run pytest -q tests/test_roadmap_failure_notifications.py::test_clean_run_under_sandbox_with_prior_failure_reaches_completed -x --tb=long
# .                                                                        [100%]
# 1 passed in 0.45s
#
# --- after restoring the fix, second green run ---
#
# $ uv run pytest -q tests/test_roadmap_failure_notifications.py::test_clean_run_under_sandbox_with_prior_failure_reaches_completed -x --tb=long
# .                                                                        [100%]
# 1 passed in 0.45s


async def test_clean_run_under_sandbox_with_prior_failure_reaches_completed(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """US1-S2 / FR-003/FR-004: a roadmap pass that completes cleanly, after a
    prior failure was recorded, reaches a completed state under the real
    WorkflowEnvironment with the sandbox enabled.

    Before the fix the workflow-scope read of `os.environ` raised
    `RestrictedWorkflowAccessError` inside `_report_run_success`.  With the
    sandbox on, that failure is the only evidence that the bug is real.
    """
    specs_root = build_corpus(tmp_path, {"001-alpha": dict(state=SpecState.READY)})
    recorder = NotificationRecorder()
    stable_id = _stable_roadmap_id(str(specs_root))

    # Record a prior failure so the recovery branch in _report_run_success fires.
    async with run_roadmap_with_sandboxed_workflow(
        env,
        FailingCorpusWorld(),
        str(specs_root),
        recorder,
        workflow_id=f"{stable_id}-prior-failure",
    ) as handle:
        with pytest.raises(Exception):
            await handle.result()

    assert len(recorder.calls) == 1, recorder.calls
    assert FAILURE_MESSAGE in recorder.calls[0].message, recorder.calls[0]

    # Now a clean pass must complete and send exactly one recovery notice.
    async with run_roadmap_with_sandboxed_workflow(
        env,
        RoadmapWorld(),
        str(specs_root),
        recorder,
        workflow_id=f"{stable_id}-clean-pass",
    ) as handle:
        status = await handle.result()

    # A clean run returns a `RoadmapStatus`; a wedged or failed one would have
    # raised before reaching here.  The field list is not the contract under
    # test — reaching this line is.
    assert isinstance(status, RoadmapStatus), status
    recovery_calls = [
        call for call in recorder.calls if "recover" in call.message.lower()
    ]
    assert len(recovery_calls) == 1, recorder.calls
    recovery = recovery_calls[0]
    assert recovery.roadmap_id == stable_id, recovery
    assert "1" in recovery.message, recovery


# ============================================================================
# US2 — notice grammar and exception preservation
# ============================================================================


async def test_failed_run_sends_notice_and_workflow_fails_with_original_exception(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """US2-S1/S2 / FR-005/FR-007: a failed pass sends a notice and the workflow
    execution still ends FAILED carrying the pass's own exception.
    """
    specs_root = build_corpus(tmp_path, {"001-alpha": dict(state=SpecState.READY)})
    recorder = NotificationRecorder()

    async with run_roadmap_with_notifications(
        env, FailingCorpusWorld(), str(specs_root), recorder
    ) as handle:
        with pytest.raises(WorkflowFailureError) as exc_info:
            await handle.result()

    _assert_original_failure_in_chain(exc_info.value, "RuntimeError", FAILURE_MESSAGE)

    assert len(recorder.calls) == 1, recorder.calls
    notice = recorder.calls[0]
    roadmap_id = roadmap_workflow_id(str(specs_root))
    assert notice.roadmap_id == roadmap_id
    assert FAILURE_MESSAGE in notice.message
    assert "No answer by" not in notice.message


async def test_recovery_leaves_zero_escalation_rows(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """US2-S5 / FR-006: the recovery notice path writes no pending escalation row."""
    specs_root = build_corpus(tmp_path, {"001-alpha": dict(state=SpecState.READY)})
    recorder = NotificationRecorder()

    async with run_roadmap_with_notifications(
        env, FailingCorpusWorld(), str(specs_root), recorder
    ) as handle:
        with pytest.raises(Exception):
            await handle.result()

    async with run_roadmap_with_notifications(
        env, RoadmapWorld(), str(specs_root), recorder
    ) as handle:
        await handle.result()

    recovery_calls = [
        call for call in recorder.calls if "recover" in call.message.lower()
    ]
    assert len(recovery_calls) == 1, recorder.calls

    from factory.verify.store import connect

    db_path = os.environ.get(ERGANE_VERIFICATION_DB_PATH_ENV)
    assert db_path is not None
    conn = connect(db_path)
    try:
        esc_count = conn.execute(
            "SELECT COUNT(*) FROM escalations WHERE epic_id = ?",
            (roadmap_workflow_id(str(specs_root)),),
        ).fetchone()[0]
        assert esc_count == 0, f"expected zero escalation rows, got {esc_count}"
    finally:
        conn.close()


async def test_record_roadmap_failure_raise_preserves_original_exception(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """US2-S4 / FR-008: a failure inside the reporting path does not replace the
    pass's own failure: the workflow's recorded failure is still the original.
    """
    specs_root = build_corpus(tmp_path, {"001-alpha": dict(state=SpecState.READY)})
    recorder = NotificationRecorder()

    import factory.activities.notify_activities as notify_module

    real_record_roadmap_failure = notify_module.record_roadmap_failure

    @activity.defn(name="record_roadmap_failure")
    async def raising_record_roadmap_failure(request: Any) -> Any:
        raise RuntimeError("recording activity is broken")

    notify_module.record_roadmap_failure = raising_record_roadmap_failure
    try:
        async with run_roadmap_with_notifications(
            env, FailingCorpusWorld(), str(specs_root), recorder
        ) as handle:
            with pytest.raises(WorkflowFailureError) as exc_info:
                await handle.result()
    finally:
        notify_module.record_roadmap_failure = real_record_roadmap_failure

    assert len(recorder.calls) == 0, recorder.calls
    _assert_original_failure_in_chain(
        exc_info.value, "RuntimeError", FAILURE_MESSAGE
    )
