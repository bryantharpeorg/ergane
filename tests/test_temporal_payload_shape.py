"""What a record has to look like to survive being read out of an older history.

A Temporal workflow's state is not stored; it is *replayed*. Every payload the
run ever wrote — its input, the arguments of every signal it received, the result
of every activity it awaited — sits in a history that outlives the worker
process, the deploy, and in the roadmap's case the week. When a query arrives, or
a worker picks the run up again, today's code decodes yesterday's bytes.

That makes a dataclass field a wire-compatibility decision, and the two
directions are not symmetric. Measured against `temporalio` 1.31's default
payload converter, which is the one this factory runs:

    encoded  {"max_concurrent_epics": 1, "max_concurrent_nodes": 3, ...}
    decoded with an EXTRA key    -> fine, the unknown key is dropped
    decoded with a MISSING key   -> TypeError: RoadmapStatus.__init__()
                                    missing 1 required positional argument:
                                    'max_concurrent_nodes'

Removing a field is survivable. *Adding* one without a default is not: the
converter builds the record with `cls(**decoded)`, so a field the older payload
never carried is a missing required argument, and the exception surfaces to the
operator as whatever the call site happened to be doing — for 052 it was
`ergane status`, which died with that message and nothing else.

So the rule this file holds (FR-006) is: every field of a record that crosses
the Temporal payload boundary either has a default, or is named in an explicit
allowlist because a default there would be a lie.

Nothing here needs a Temporal server. The payload roundtrip goes through the
converter in-process, and the query is called as the plain method it is.
"""

from __future__ import annotations

import dataclasses
import json
import typing
from typing import Any

import pytest
import temporalio.activity
import temporalio.api.common.v1 as common
import temporalio.workflow
from temporalio.converter import default as default_data_converter

from factory.roadmap.workflow import RoadmapStatus, RoadmapWorkflow
from factory.worker import ACTIVITIES, WORKFLOWS

#: The seam the sweep measures against. It is the worker's own registration
#: rather than a list written here, because the boundary *is* what the worker
#: serves: `factory/worker.py` is the one place that knows every workflow type
#: and every activity the factory runs, and importing it is inert by
#: construction — the registration is data and `main` is what runs.
REGISTERED_WORKFLOWS = WORKFLOWS
REGISTERED_ACTIVITIES = ACTIVITIES


def payload_of(value: Any) -> common.Payload:
    """Encode with the converter the factory actually runs, not a stand-in."""
    return default_data_converter().payload_converter.to_payload(value)


def decode_as(payload: common.Payload, record: type) -> Any:
    """Decode with the converter the factory actually runs."""
    return default_data_converter().payload_converter.from_payload(payload, record)


def payload_missing(value: Any, *field_names: str) -> common.Payload:
    """The same payload as an older worker, before those fields existed, wrote it.

    A history recorded before a field existed is byte-for-byte a payload with
    that key absent, so the fixture is the real encoding with keys removed — not
    a hand-built dict that might disagree with the converter about how the rest
    of the record is spelled. Each name is asserted present before it is removed,
    so a renamed field makes this loud instead of making it vacuous.
    """
    encoded = payload_of(value)
    body = json.loads(encoded.data)
    for name in field_names:
        assert name in body, (
            f"{name!r} is not in the encoded payload of {type(value).__name__}, "
            "so removing it proves nothing"
        )
        del body[name]
    return common.Payload(metadata=encoded.metadata, data=json.dumps(body).encode())


# --- US2-S1: an older history is still readable -------------------------------


def test_roadmap_status_reconstructs_from_a_payload_that_predates_the_bound() -> None:
    """The exact shape of the 052 defect, as a payload rather than a story.

    `max_concurrent_nodes` joined `RoadmapStatus` after the record shipped. Every
    roadmap history written before that day encodes a `RoadmapStatus` without the
    key, and decoding one has to succeed at the documented default rather than
    raise.
    """
    current = RoadmapStatus(
        specs=[],
        running=[],
        parked=[],
        max_concurrent_epics=1,
        max_concurrent_nodes=3,
        paused=False,
    )
    older = payload_missing(current, "max_concurrent_nodes")

    reconstructed = decode_as(older, RoadmapStatus)

    # 1 is the default `RoadmapInput.max_concurrent_nodes` already documents:
    # one node in flight per child epic, the sequential behaviour an
    # unconfigured roadmap gets.
    assert reconstructed.max_concurrent_nodes == 1
    assert reconstructed.max_concurrent_epics == 1
    assert reconstructed.specs == []


def test_roadmap_status_reconstructs_from_a_payload_that_predates_either_bound() -> None:
    """Both bounds are knobs with one documented default, so both must default.

    `max_concurrent_epics` is the older of the two and is not the field that
    broke `ergane status`, but it is the same kind of field — a bound whose
    absence means "the roadmap was not configured", never "the roadmap does not
    know" — so leaving it required would leave the same trap set one field over.
    """
    current = RoadmapStatus(
        specs=[],
        running=[],
        parked=[],
        max_concurrent_epics=2,
        max_concurrent_nodes=3,
    )
    older = payload_missing(current, "max_concurrent_epics", "max_concurrent_nodes")

    reconstructed = decode_as(older, RoadmapStatus)

    assert reconstructed.max_concurrent_epics == 1
    assert reconstructed.max_concurrent_nodes == 1


def test_the_zero_state_query_reports_the_bounds_in_force() -> None:
    """The construction site that raised the message the operator actually saw.

    `roadmap_status` answers before the corpus has been read — a run that has not
    finished its first pass, or one whose replay stopped short of it — and that
    branch built a `RoadmapStatus` without `max_concurrent_nodes` at all. With no
    default on the field it raised `TypeError` *inside the worker*, which the
    client re-raised as a query failure carrying the message verbatim.

    A default alone would make this branch answer, and answer wrongly: it would
    report the shipped default instead of the bound the run is holding. So the
    branch has to pass the bounds in force, and this test fails either way — no
    default (raises) or a default leaned on (reports 1 for a run bounded at 4).

    Calling the query as a plain method is deliberate: it is a read-only handler
    that executes no activity and touches no `workflow` API on this path, so it
    needs no server and no test environment to answer.
    """
    roadmap = RoadmapWorkflow()
    roadmap._max_concurrent_epics = 3
    roadmap._max_concurrent_nodes = 4

    answer = roadmap.roadmap_status()

    assert answer.specs == []
    assert answer.running == []
    assert answer.parked == []
    assert answer.max_concurrent_epics == 3
    assert answer.max_concurrent_nodes == 4


# --- US2-S2 / FR-007: the sweep, and the boundary it reads ---------------------


def workflow_boundary_types() -> list[Any]:
    """Every type a registered workflow puts on the wire.

    Read out of `temporalio`'s own workflow definition — the same metadata the
    worker uses to decide what to decode a payload as — rather than out of the
    source, so a handler this repository adds is on the boundary the moment it
    is decorated. Four surfaces, and all four end up in a history: the run's
    argument (which is also the continue-as-new payload), the run's result, each
    query's answer, and each signal's arguments.
    """
    found: list[Any] = []
    for workflow_class in REGISTERED_WORKFLOWS:
        defn = temporalio.workflow._Definition.from_class(workflow_class)
        found.extend(list(defn.arg_types or []) + [defn.ret_type])
        for query in defn.queries.values():
            found.extend(list(query.arg_types or []) + [query.ret_type])
        for signal in defn.signals.values():
            found.extend(list(signal.arg_types or []))
        for update in (getattr(defn, "updates", None) or {}).values():
            found.extend(list(update.arg_types or []) + [getattr(update, "ret_type", None)])
    return [t for t in found if t is not None]


def activity_boundary_types() -> list[Any]:
    """Every type a registered activity puts on the wire.

    Both directions count. An activity's *result* is written into the calling
    workflow's history and decoded again on every replay for the life of that
    run, which is the same exposure the workflow's own input has. An activity's
    *input* has a shorter fuse — it is decoded by whichever worker picks the task
    up, which can be one deployed after the workflow encoded it — but it is the
    same failure, so it is swept the same way.
    """
    found: list[Any] = []
    for activity_fn in REGISTERED_ACTIVITIES:
        defn = temporalio.activity._Definition.from_callable(activity_fn)
        assert defn is not None, f"{activity_fn!r} is registered but is not an activity"
        found.extend(list(defn.arg_types or []) + [defn.ret_type])
    return [t for t in found if t is not None]


def records_within(annotation: Any, found: dict[type, None]) -> None:
    """Collect the dataclasses reachable from one annotation, containers included.

    A record on the boundary drags its fields' records onto the boundary with
    it: `EpicInput.graph` is a `WorkGraph`, whose `nodes` are `WorkNode`s, and a
    field added to `WorkNode` without a default breaks the decode of every epic
    history ever written just as surely as one added to `EpicInput`.
    """
    parameters = typing.get_args(annotation)
    if parameters:
        for parameter in parameters:
            records_within(parameter, found)
        return
    if not isinstance(annotation, type) or not dataclasses.is_dataclass(annotation):
        return
    if annotation in found:
        return
    found[annotation] = None
    hints = typing.get_type_hints(annotation)
    for field in dataclasses.fields(annotation):
        records_within(hints.get(field.name, field.type), found)


def boundary_records() -> list[type]:
    """Every record that crosses the Temporal payload boundary, sorted."""
    found: dict[type, None] = {}
    for annotation in workflow_boundary_types() + activity_boundary_types():
        records_within(annotation, found)
    return sorted(found, key=record_id)


def record_id(record: type) -> str:
    """`module.Name` — the key the allowlist is written in, and the test id."""
    return f"{record.__module__}.{record.__name__}"


def fields_without_a_default(record: type) -> tuple[str, ...]:
    return tuple(
        field.name
        for field in dataclasses.fields(record)
        if field.default is dataclasses.MISSING
        and field.default_factory is dataclasses.MISSING
    )


#: Every boundary field whose absence must stay loud (FR-006's allowlist).
#:
#: A default is a promise that "the payload did not say" and "the value is this"
#: mean the same thing. For the fields below they do not, and a default would
#: turn a decode that should fail into a report that is quietly wrong. They fall
#: into three kinds, and every entry here is one of them:
#:
#: 1. **Coordinates** — `epic_id`, `node_id`, `attempt`, `spec_dir`, `spec_ref`,
#:    `escalation_id`, `question_id`, `target_repo`, `worktree_path`, `branch`,
#:    `pr_number`. These address something. A default addresses the wrong thing,
#:    and the factory acts on addresses: it clones repos, writes worktrees,
#:    settles escalations and attributes spend by them.
#:
#: 2. **The record's substance** — `nodes`, `graph`, `specs`, `running`,
#:    `parked`, `blockers`, `detail`, `question_text`, `history_summary`,
#:    `log_tail`, `requirement_keys`. Defaulting these to empty converts "this
#:    could not be read" into "there is nothing", which is the same silence 052
#:    exists to end: the command stops dying and starts lying.
#:
#: 3. **Verdicts and measurements** — `passed`, `outcome`, `state`, `delivered`,
#:    `landed`, `exit_code`, `prompt_tokens`, `spend_usd`, `observed_at`,
#:    `snapshotted_at`. Constitution V says recorded usage is never fabricated —
#:    unknown is flagged, not zeroed — and a defaulted verdict is a fabricated
#:    one. `0` tokens and `PASS` are answers; the absence of an answer is not.
#:
#: A field that is none of those three gets a default instead of a line here.
#: That is the judgement the two `RoadmapStatus` bounds failed on their way in,
#: and the reason this list does not name them.
#:
#: Adding a field to a boundary record without a default therefore costs a
#: deliberate edit here, which is the whole mechanism: 045's trap 5, restated as
#: 049's FR-010, made enforceable instead of remembered.
MUST_BE_PRESENT: dict[str, tuple[str, ...]] = {
    "factory.activities.agent_activities.LoadPromptSourcesInput": (
        "specs_root", "feature", "target_repo"
    ),
    "factory.activities.agent_activities.PrepareWorktreeInput": (
        "epic_id", "node_id", "target_repo"
    ),
    "factory.activities.agent_activities.PromptSources": (
        "spec_text", "plan_text", "tasks_text"
    ),
    "factory.activities.agent_activities.ReadWorktreeDiffInput": (
        "worktree_path", "base_ref"
    ),
    "factory.activities.agent_activities.RemoveWorktreeInput": (
        "epic_id", "node_id", "target_repo"
    ),
    "factory.activities.agent_activities.ResolvePersonaInput": ("persona",),
    "factory.activities.agent_activities.SalvageWorktreeInput": (
        "epic_id", "node_id", "termination", "attempt"
    ),
    "factory.activities.merge_activities.CompareTreesInput": (
        "epic_id", "node_id", "target_repo", "rejected_tip", "current_head"
    ),
    "factory.activities.merge_activities.DisableAutoMergeInput": (
        "pr_number", "target_repo"
    ),
    "factory.activities.merge_activities.DisableResult": ("failed", "reason",),
    "factory.activities.merge_activities.EnqueueLandingInput": (
        "pr_number", "merge_method", "target_repo"
    ),
    "factory.activities.merge_activities.EnqueueResult": ("rejected", "reason",),
    "factory.activities.merge_activities.FetchCheckFailureInput": (
        "epic_id", "node_id", "pr_number", "check_names", "target_repo"
    ),
    "factory.activities.merge_activities.OpenLandingPrInput": (
        "epic_id", "node_id", "target_repo", "base", "branch", "title",
        "body_file"
    ),
    "factory.activities.merge_activities.OpenLandingPrResult": ("number", "url",),
    "factory.activities.merge_activities.PollLandingInput": (
        "pr_number", "target_repo"
    ),
    "factory.activities.merge_activities.PrepareLandingPrInput": (
        "epic_id", "node_id", "branch", "attempt", "feature",
        "requirement_keys", "result", "story_title"
    ),
    "factory.activities.merge_activities.PrepareLandingPrResult": (
        "body_file", "title"
    ),
    "factory.activities.merge_activities.SyncLandingBranchInput": (
        "epic_id", "node_id", "target_repo"
    ),
    "factory.activities.merge_activities.SyncLandingBranchResult": (
        "clean", "base_ref", "conflicted_files", "refused", "reason"
    ),
    "factory.activities.merge_activities.ValidateTargetRepoInput": ("target_repo",),
    "factory.activities.notify_activities.ExpireEscalationInput": ("escalation_id",),
    "factory.activities.notify_activities.ExpireQuestionInput": ("question_id",),
    "factory.activities.notify_activities.ExpiredEscalation": ("final_state",),
    "factory.activities.notify_activities.ExpiredQuestion": ("final_state",),
    "factory.activities.notify_activities.FindFerriedQuestion": ("question_id",),
    "factory.activities.notify_activities.FindFerriedQuestionInput": (
        "epic_id", "node_id", "attempt"
    ),
    "factory.activities.notify_activities.RecordRoadmapFailureInput": (
        "db_path", "roadmap_id", "failure_text"
    ),
    "factory.activities.notify_activities.RecordRoadmapFailureResult": ("count",),
    "factory.activities.notify_activities.ResetRoadmapFailuresInput": (
        "db_path", "roadmap_id"
    ),
    "factory.activities.notify_activities.SendEscalationInput": (
        "workflow_id", "epic_id", "node_id", "history_summary"
    ),
    "factory.activities.notify_activities.SendQuestionInput": (
        "workflow_id", "epic_id", "node_id", "attempt", "question_text"
    ),
    "factory.activities.notify_activities.SendRoadmapNoticeInput": (
        "roadmap_id", "message"
    ),
    "factory.activities.notify_activities.SentEscalation": (
        "escalation_id", "delivered", "expires_at"
    ),
    "factory.activities.notify_activities.SentQuestion": (
        "question_id", "message_id", "sent_at", "expires_at"
    ),
    "factory.activities.notify_activities.SentRoadmapNotice": ("delivered",),
    "factory.activities.notify_activities.SettleEscalationInput": (
        "escalation_id", "choice"
    ),
    "factory.activities.notify_activities.SettleQuestionInput": (
        "question_id", "answer_text"
    ),
    "factory.activities.notify_activities.SettledEscalation": (
        "final_state", "settled_here"
    ),
    "factory.activities.notify_activities.SettledQuestion": (
        "final_state", "settled_here"
    ),
    "factory.activities.roadmap_activities.CloneInput": ("target_repo", "spec_dir",),
    "factory.activities.roadmap_activities.CloneResult": (
        "path", "default_branch", "head_ref"
    ),
    "factory.activities.roadmap_activities.CountOpenResult": ("open_ids",),
    "factory.activities.roadmap_activities.DeriveInput": (
        "spec_text", "epic_id", "feature", "specs_root", "target_repo"
    ),
    "factory.activities.roadmap_activities.DriftInput": (
        "target_repo", "spec_dir", "spec_text"
    ),
    "factory.activities.roadmap_activities.OnboardInput": ("target_repo", "spec_dir",),
    "factory.activities.roadmap_activities.PreflightInput": (
        "graph", "proxy_url", "spec_dir"
    ),
    "factory.activities.roadmap_activities.ReadLoopConfigInput": ("target_repo",),
    "factory.activities.roadmap_activities.ReadLoopConfigResult": (
        "config", "verify_order"
    ),
    "factory.activities.usage_activities.IssueKeyInput": (
        "node_id", "epic_id", "attempt", "persona", "spec_ref"
    ),
    "factory.activities.usage_activities.TeardownInput": ("lease", "termination",),
    "factory.activities.verify_activities.CheckOutputInput": (
        "worktree_path", "write_scope"
    ),
    "factory.activities.verify_activities.DetectQuestionInput": ("transcript_path",),
    "factory.activities.verify_activities.RecordExternalCompletionInput": (
        "epic_id", "node_id", "branch", "provenance", "accepted", "reason"
    ),
    "factory.activities.verify_activities.RecordVerificationInput": ("result",),
    "factory.activities.verify_activities.RecordedVerification": (
        "row_id", "criteria_drift"
    ),
    "factory.activities.verify_activities.RunGatesInput": ("worktree_path",),
    "factory.activities.verify_activities.RunJudgeInput": (
        "criteria", "diff_text", "virtual_key", "proxy_url", "model_alias"
    ),
    "factory.activities.verify_activities.SnapshotCriteriaInput": (
        "specs_root", "feature", "spec_ref"
    ),
    "factory.escalation.question.QuestionOutcome": ("question_id", "outcome",),
    "factory.escalation.question.QuestionRequest": (
        "epic_id", "node_id", "attempt", "question_text"
    ),
    "factory.escalation.workflow.EscalationOutcome": (
        "escalation_id", "outcome", "resolution", "identity", "delivered"
    ),
    "factory.escalation.workflow.EscalationRequest": (
        "epic_id", "node_id", "history_summary"
    ),
    "factory.escalation.workflow.OpenEscalation": (
        "escalation_id", "epic_id", "node_id", "question", "expires_at"
    ),
    "factory.mergequeue.models.CheckFailure": ("name", "url", "log_tail", "note",),
    "factory.mergequeue.models.Finding": ("check", "passed", "detail",),
    "factory.mergequeue.models.ObservedOutcome": ("at", "outcome",),
    "factory.mergequeue.models.PrSnapshot": (
        "state", "is_draft", "auto_merge_requested", "merge_state_status",
        "merged_at", "closed_at", "failing_required_checks", "observed_at"
    ),
    "factory.mergequeue.models.TargetRepoProfile": (
        "repo", "default_branch", "visibility", "queue_enabled",
        "required_checks", "declared_gates", "findings", "passed"
    ),
    "factory.roadmap.models.LandedStatus": ("landed", "kind",),
    "factory.roadmap.models.Roadmap": ("specs_root", "entries",),
    "factory.roadmap.models.SpecEntry": ("spec_dir", "state", "depends_on_landed",),
    "factory.roadmap.workflow.ParkedFinding": ("spec_dir", "check", "detail",),
    "factory.roadmap.workflow.ReadCorpusInput": ("specs_root",),
    "factory.roadmap.workflow.ReadSpecInput": ("specs_root", "spec_dir",),
    "factory.roadmap.workflow.RoadmapInput": (
        "specs_root", "target_repo", "proxy_url"
    ),
    "factory.roadmap.workflow.RoadmapSpecStatus": (
        "spec_dir", "state", "dispatchable", "blockers", "landed", "unlanded"
    ),
    # The bounds are NOT here: `max_concurrent_epics` and `max_concurrent_nodes`
    # are knobs with one documented default (one epic, one node), so an older
    # payload that carries neither means "unconfigured", not "unknown". That is
    # the whole of 052 US2 — see the record's own docstring.
    "factory.roadmap.workflow.RoadmapStatus": ("specs", "running", "parked"),
    "factory.usage.models.KeyLease": (
        "key", "key_alias", "node_id", "epic_id", "attempt", "persona",
        "spec_ref", "issued_at"
    ),
    "factory.usage.models.UsageRecord": (
        "epic_id", "node_id", "attempt", "persona", "spec_ref", "key_alias",
        "prompt_tokens", "completion_tokens", "cache_read_tokens",
        "cache_write_tokens", "request_count", "spend_usd",
        "final_usage_confirmed", "termination", "issued_at", "torn_down_at"
    ),
    "factory.usage.models.UsageSnapshot": ("spend_usd", "captured_at",),
    # 069-US1 put `AttemptRecord` on the boundary: `NodeStatus` now carries the
    # node's ladder history, because a rejection spends from two budgets and a
    # reader who can see only `recovery_cycles` cannot tell a node that stopped
    # being charged from one still dying of the other. Its three required fields
    # are kind 1 and kind 3: `attempt` addresses the evidence row and the spend
    # key, `persona` decides which budget the record counts against
    # (`factory/verify/ladder.py`), and `verdict` is the verdict itself. A
    # defaulted persona would silently move a debugger cycle onto the attempt
    # budget, which is the arithmetic this whole story turns on.
    "factory.verify.models.AttemptRecord": ("attempt", "persona", "verdict",),
    "factory.verify.models.CriteriaSet": (
        "feature", "spec_ref", "requirements", "source_path", "source_sha256",
        "snapshotted_at"
    ),
    "factory.verify.models.DiffFileSize": ("path", "size_bytes",),
    "factory.verify.models.DiffSizeRefusal": (
        "total_bytes", "limit_bytes", "largest_files"
    ),
    "factory.verify.models.GateResult": (
        "name", "command", "status", "exit_code", "duration_s", "output_tail"
    ),
    "factory.verify.models.HygieneViolation": ("path", "rule",),
    "factory.verify.models.JudgeScenarioFinding": ("scenario", "passed", "reasoning",),
    "factory.verify.models.JudgeVerdict": (
        "outcome", "findings", "feedback", "judge_attempt", "truncated_input",
        "model_alias"
    ),
    "factory.verify.models.OutputCheck": (
        "write_scope", "has_diff", "expected_artifacts", "artifacts_present",
        "passed"
    ),
    "factory.verify.models.Requirement": ("key", "kind", "title", "priority", "body",),
    "factory.verify.models.Scenario": ("scenario_id", "steps", "raw_text",),
    "factory.verify.models.VerificationResult": (
        "epic_id", "node_id", "attempt", "form", "gate_results", "output_check",
        "judge", "verdict", "judge_unavailable", "criteria_drift",
        "criteria_sha256", "spec_ref", "started_at", "finished_at"
    ),
    "factory.verify.question.QuestionMarker": ("is_question",),
    "factory.workgraph.models.AdapterResult": ("termination",),
    "factory.workgraph.models.AttemptContext": (
        "epic_id", "node_id", "attempt", "prompt", "worktree_path", "home_path",
        "proxy_url", "virtual_key", "model_alias", "session_id", "timeout_s"
    ),
    # Kind 1, coordinates: both fields address a node of the graph. A default
    # would attribute an inferred edge to whatever node sorts first, and an
    # operator reading provenance would go and edit the wrong story.
    "factory.workgraph.models.InferredEdge": ("node_id", "depends_on_merged"),
    "factory.workgraph.models.ResolvedNode": (
        "node", "model_alias", "models", "write_scope", "timeout_s"
    ),
    "factory.workgraph.models.ResolvedPersona": ("persona", "model_alias", "models",),
    "factory.workgraph.models.WorkGraph": (
        "epic_id", "feature", "specs_root", "target_repo", "nodes"
    ),
    "factory.workgraph.models.WorkNode": (
        "id", "story_key", "persona", "spec_ref", "requirement_keys",
        "depends_on"
    ),
    "factory.workgraph.preflight.PreflightFinding": ("check", "passed", "detail",),
    "factory.workgraph.workflow.EpicInput": ("graph", "proxy_url",),
    "factory.workgraph.workflow.EpicStatus": ("epic_state", "nodes",),
    "factory.workgraph.workflow.NodeStatus": ("state", "attempt", "branch",),
    "factory.workgraph.worktree.PreparedWorktree": ("path", "branch", "base_ref",),}


#: Resolved once, at import, so a sweep that reads nothing is visible as an
#: empty parametrization rather than as a test that quietly never ran.
BOUNDARY_RECORDS = boundary_records()


def test_the_sweep_read_a_non_empty_boundary_that_names_roadmap_status() -> None:
    """FR-007's anti-vacuity assertion: the sweep below has to be able to fail.

    A parametrized sweep over an empty list does not fail — it collects zero
    cases and the run is green with nothing asserted. `tests/test_final_sweep.py`
    carries the same guard for the same reason, and it carries it because that
    already happened in this repository.

    So this test names what the discovery must have found. `RoadmapStatus` is
    named because FR-007 names it: it is the record 052 was filed about. The
    other three are landmarks on the surfaces `RoadmapStatus` alone would not
    cover — a workflow input, an activity result, and a record only reachable
    through another record's field — so a discovery that half-collapses is as
    loud as one that collapses entirely.
    """
    swept = {record_id(record) for record in BOUNDARY_RECORDS}

    assert swept, (
        "the boundary sweep found no records at all — it is reading nothing, "
        "and every assertion parametrized over it is vacuous"
    )
    assert {
        "factory.roadmap.workflow.RoadmapStatus",  # a query answer and a run result
        "factory.workgraph.workflow.EpicInput",  # a run argument
        "factory.usage.models.UsageRecord",  # an activity result
        "factory.workgraph.models.WorkNode",  # reached only through WorkGraph.nodes
    } <= swept, f"the boundary sweep lost a surface; it read {sorted(swept)}"


@pytest.mark.parametrize("record", BOUNDARY_RECORDS, ids=record_id)
def test_every_boundary_field_has_a_default_or_is_allowlisted(record: type) -> None:
    """FR-006, over every record the worker's registration puts on the wire.

    The failure this prevents is not hypothetical and not subtle: a field added
    here without a default makes every history written before today undecodable,
    and the operator meets it as `__init__() missing 1 required positional
    argument` from whichever command happened to ask.
    """
    required = set(fields_without_a_default(record))
    allowlisted = set(MUST_BE_PRESENT.get(record_id(record), ()))
    unaccounted = sorted(required - allowlisted)

    assert not unaccounted, (
        f"{record_id(record)} crosses the Temporal payload boundary, and "
        f"{unaccounted} have neither a default nor a line in MUST_BE_PRESENT. "
        "A payload written before one of them existed cannot be decoded at all "
        "(FR-006). Give the field a default, or — if absence there must stay "
        "loud — name it in MUST_BE_PRESENT with which of the three kinds it is."
    )


def test_the_allowlist_names_only_fields_that_are_still_on_the_boundary() -> None:
    """The allowlist is a claim about today's records, so it has to rot loudly.

    Without this, a renamed field or a record that left the boundary leaves a
    dead entry behind, and the next field to take that name inherits an
    exemption nobody granted.
    """
    on_the_boundary = {record_id(record): record for record in BOUNDARY_RECORDS}

    strays = sorted(set(MUST_BE_PRESENT) - set(on_the_boundary))
    assert not strays, (
        f"MUST_BE_PRESENT names {strays}, which no longer cross the boundary"
    )

    phantoms = sorted(
        f"{name}.{field}"
        for name, allowlisted in MUST_BE_PRESENT.items()
        for field in allowlisted
        if field not in {f.name for f in dataclasses.fields(on_the_boundary[name])}
    )
    assert not phantoms, f"MUST_BE_PRESENT names fields that do not exist: {phantoms}"
