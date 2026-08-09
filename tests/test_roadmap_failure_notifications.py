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
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from factory.activities.verify_activities import VERIFICATION_DB_PATH_ENV

import factory.activities.roadmap_activities as roadmap_activities
import factory.roadmap.workflow as factory_roadmap_workflow
from factory.activities.roadmap_activities import CountOpenInput, CountOpenResult
from factory.activities.notify_activities import (
    SendEscalationInput,
    SentEscalation,
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


class NotificationRecorder:
    """Replaces `send_escalation` so tests can assert on what was sent."""

    def __init__(self) -> None:
        self.calls: list[RecordedNotification] = []
        self.raise_on_send: bool = False
        self.fail_record_before_send: list[str] = []

    def record(self, request: SendEscalationInput) -> SentEscalation:
        self.calls.append(
            RecordedNotification(
                workflow_id=request.workflow_id,
                epic_id=request.epic_id,
                node_id=request.node_id,
                history_summary=request.history_summary,
            )
        )
        if self.raise_on_send:
            raise RuntimeError("notifier is down")
        return SentEscalation(
            escalation_id="deadbeefcafe",
            delivered=True,
            expires_at="2099-01-01T00:00:00Z",
        )


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[WorkflowEnvironment]:
    """Temporal with a clock the test owns.

    Each test gets its own verification database under `tmp_path` so
    consecutive-failure counts and escalation rows do not leak between tests.
    """
    db_path = str(tmp_path / "verification.db")
    old_db = os.environ.get(VERIFICATION_DB_PATH_ENV)
    os.environ[VERIFICATION_DB_PATH_ENV] = db_path
    environment = await WorkflowEnvironment.start_time_skipping()
    _SCRIPT.statuses = {}
    _SCRIPT.on_dispatch = None
    _SCRIPT.on_complete = None
    _SCRIPT.hold = set()
    try:
        yield environment
    finally:
        await environment.shutdown()
        if old_db is None:
            os.environ.pop(VERIFICATION_DB_PATH_ENV, None)
        else:
            os.environ[VERIFICATION_DB_PATH_ENV] = old_db
        _SCRIPT.statuses = {}
        _SCRIPT.on_dispatch = None
        _SCRIPT.on_complete = None
        _SCRIPT.hold = set()


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
) -> AsyncIterator[Any]:
    """Start the roadmap with a scripted failure and a recording notifier."""
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
        read_corpus_activity,
        read_spec_text_activity,
        record_roadmap_failure,
        reset_roadmap_failures,
    ]

    @activity.defn(name="send_escalation")
    async def recording_send_escalation(request: SendEscalationInput) -> SentEscalation:
        return recorder.record(request)

    activities.append(recording_send_escalation)

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
                id=roadmap_workflow_id(specs_root),
                task_queue="workgraph",
            )
            yield handle
    finally:
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
    assert FAILURE_MESSAGE in recorder.calls[0].history_summary, recorder.calls[0]


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
        "3" in call.history_summary or "three" in call.history_summary.lower()
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
        if "recover" in call.history_summary.lower()
        or "passed" in call.history_summary.lower()
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
    writes such a row before calling `send_escalation`, this test fails.
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
    # But the fact was recorded in the verification store.  The row must exist
    # before the send was attempted.
    from factory.verify.store import connect

    db_path = os.environ.get(VERIFICATION_DB_PATH_ENV)
    assert db_path is not None
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM escalations WHERE epic_id = ?",
            (roadmap_workflow_id(str(specs_root)),),
        ).fetchone()
        assert row[0] >= 1, "no escalation row recorded for the failed roadmap"
    finally:
        conn.close()
