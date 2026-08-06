"""The activity surface of verification: five calls, and the promises they keep.

`factory/verify/` is a library of pure functions and one-purpose runners, each
already tested against its own module. This file is about what happens when the
orchestrator calls them: the translation between a dispatch and a library
argument, the mapping from a library exception to an error a workflow can branch
on without reading prose, and — the part no library test can reach — the order
the calls happen in.

`snapshot_criteria` is the only activity that runs *before* an agent does any
work, and everything the node is later judged against comes from its return
value (FR-010). That makes its two failure modes as important as its success
path: a spec the parser refuses and a spec file that is not there are both
"this node cannot be verified", but they send an operator to different places,
so they come back as different application errors and are asserted separately
here.

What these tests pin down:

- **The snapshot is the node's goalposts, taken once.** The returned
  `CriteriaSet` carries exactly the requirement keys the dispatch asked for, in
  the order it asked for them, plus the hash of the spec file's raw bytes and
  the moment it was read. Editing the spec afterwards must not change a snapshot
  already taken — that is what makes the drift flag (R8) meaningful rather than
  a race.
- **A parse failure names the requirement, through the activity boundary.** The
  parser's message is the operator's whole diagnosis, so `CRITERIA_PARSE_FAILED`
  carries it verbatim; an error that only said "spec did not parse" would make
  the activity strictly less useful than the library it wraps.
- **Both failures are permanent.** Neither a malformed spec nor an absent file
  becomes well-formed by being read again a second later, and the workflow's
  retry budget exists for proxies and worktrees, not for typos. They are
  non-retryable so the ladder escalates to the human who can actually fix the
  file.
- **Reading is idempotent.** The contract calls this a pure read (safe to
  retry), so two runs against an unchanged file agree on every field except the
  timestamp.
- **A gate that fails is data; a worktree that vanished is not.** `run_gates`
  returns one `GateResult` per declared gate whatever they did — including a
  single `CONFIG_ERROR` for an unusable manifest, because an empty gate list is
  exactly the shape a naive verdict reads as "nothing failed" (SC-002).
  `check_output`, by contrast, raises `WORKTREE_MISSING` rather than reporting
  the clean worktree an absent directory resembles: charging an infrastructure
  failure to the agent's attempt budget is the same mistake as passing on an
  empty diff, pointed the other way.
- **An outage is not a verdict.** `run_judge` maps an unreachable proxy to
  `JUDGE_UNAVAILABLE` and leaves the gates-only fallback to the composer. It is
  retryable — a backend that is down now may be up in a minute — which is the
  opposite of the criteria errors above, and the distinction is the whole reason
  the types are separate.
- **An anonymous verification row is refused, not written.** Every rollup and
  every escalation summary reads the evidence store by epic and node, so a row
  missing one of those does not merely lack detail: it is invisible in exactly
  the query that would have revealed the gap. `ATTRIBUTION_INCOMPLETE` raises
  before the write (the same discipline component 1's teardown follows).
- **The verdict truth table has no path to a false PASS (SC-002).** Composition
  is exhaustive here — every gate status, the output check, every judge outcome,
  and the vacuous no-gates case — because this function is the only thing
  standing between a green-looking attempt and an unlocked downstream edge
  (FR-005).
- **The judge is never asked when a gate failed.** Cheapest-first is invariant 2
  of the flow contract, and it is asserted the only way that cannot be faked:
  the fake proxy's request log is empty.

The corpus is `tests/fixtures/speckit/` — the same real files
`tests/test_criteria.py` parses, including component 1's shipped spec. Testing
the criteria activity against inline strings would prove only that the wrapper
forwards its argument; testing it against the corpus proves the wiring an
operator actually gets: `<specs_root>/<feature>/spec.md`. The gate and diff
activities get a real git repository (`tests/target_repo.py`) for the same
reason, and the judge gets the scripted fake proxy (`tests/judge_proxy.py`) with
the master key sitting in the process environment throughout, so "the master key
never reaches the judge" is asserted where it was available to leak (FR-009).

The criteria under judgment are hand-built rather than parsed: US2's tests are
independent of US1's parser (tasks.md § Dependencies), and hand-building is also
the only way to hold the scenario text still while asserting it arrives verbatim.

Written before the remaining activities exist (T021 precedes T022): until
`run_gates`, `check_output`, `run_judge`, `record_verification` and the
composition helpers land, every test here fails at import.
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
import threading
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Sequence

import pytest
from temporalio import activity
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from factory.activities import verify_activities
from factory.activities.verify_activities import (
    ATTRIBUTION_INCOMPLETE,
    CRITERIA_FILE_MISSING,
    CRITERIA_PARSE_FAILED,
    DEFAULT_VERIFICATION_DB_PATH,
    JUDGE_UNAVAILABLE,
    VERIFICATION_DB_PATH_ENV,
    WORKTREE_MISSING,
    CheckOutputInput,
    RecordVerificationInput,
    RunGatesInput,
    RunJudgeInput,
    SnapshotCriteriaInput,
    check_output,
    record_verification,
    run_gates,
    run_judge,
    snapshot_criteria,
)
from factory.config import WriteScope
from factory.verify import store
from factory.verify.judge import DEFAULT_MAX_JUDGE_RETRIES, MAX_HTTP_ATTEMPTS
from factory.verify.models import (
    CriteriaSet,
    GateResult,
    GateStatus,
    JudgeOutcome,
    JudgeScenarioFinding,
    JudgeVerdict,
    OutputCheck,
    OverallVerdict,
    Requirement,
    RequirementKind,
    Scenario,
    VerificationForm,
    VerificationResult,
    compose_result,
    judge_required,
)
from tests.judge_proxy import (
    JUDGE_MODEL_ALIAS,
    JUDGE_PROXY_URL,
    JUDGE_VIRTUAL_KEY,
    FakeJudgeProxy,
    verdict_json,
)
from tests.target_repo import GATE_ORDER_LOG, gate_order, git

CORPUS = Path(__file__).resolve().parent / "fixtures" / "speckit"

#: The fixture exercising every production of the grammar (architecture §2).
FULL_GRAMMAR = "010-full-grammar"

#: The real-world fixture: a verbatim copy of component 1's shipped spec.
REAL_WORLD = "001-usage-tracking"

#: The node's work-attribution key, carried through untouched (component 1).
SPEC_REF = "library-loans/borrow-flow"

#: Attribution dimensions every evidence row and every rollup is keyed by.
EPIC = "epic-7"
NODE = "node-3"
ATTEMPT = 2

#: A tracked file in the fixture repo, for "the agent edited something" cases.
TRACKED_FILE = "src/calc.py"

#: The artifact a read-scoped node (researcher) declares as its output (R7).
REPORT = "reports/findings.md"

#: The master key is in the worker environment for every judge call below — that
#: is the point: FR-009 is asserted where the credential was available to leak.
MASTER_KEY = "sk-master-must-never-reach-the-judge"

STARTED_AT = "2026-08-04T09:15:00Z"
FINISHED_AT = "2026-08-04T09:17:30Z"
CRITERIA_SHA = "c0ffee" + "0" * 58


# --- the criteria under judgment ---------------------------------------------

JUDGED_SCENARIO = Scenario(
    scenario_id="US2-S1",
    steps=[
        "**Given** a target repo with a committed `factory.yaml`",
        "**When** the verifier runs",
        "**Then** each declared gate executes with exit-code semantics",
    ],
    raw_text=(
        "1. **Given** a target repo with a committed `factory.yaml` declaring "
        "runtime and test/lint/typecheck commands, **When** the verifier runs, "
        "**Then** each declared gate executes with exit-code semantics (0 = pass)."
    ),
)

JUDGED_STORY = Requirement(
    key="US2",
    kind=RequirementKind.STORY,
    title="Two-tier verification of a node's diff",
    priority="P1",
    body=(
        "As the factory, when a node reports completion, I evaluate it with "
        "deterministic gates first and a bounded judge second."
    ),
    scenarios=[JUDGED_SCENARIO],
)

FUNCTIONAL = Requirement(
    key="FR-002",
    kind=RequirementKind.FUNCTIONAL,
    title=None,
    priority=None,
    body=(
        "The verifier MUST run every gate declared in the target repo's committed "
        "factory.yaml and record each gate's result."
    ),
    scenarios=[],
)

JUDGED_CRITERIA = CriteriaSet(
    feature="002-verification-gating",
    spec_ref=SPEC_REF,
    requirements=[JUDGED_STORY, FUNCTIONAL],
    source_path="specs/002-verification-gating/spec.md",
    source_sha256=CRITERIA_SHA,
    snapshotted_at=STARTED_AT,
)

#: A node that owes only declarative requirements: there is nothing for the judge
#: to score, so it is verified on gates and the output check alone.
FR_ONLY_CRITERIA = replace(JUDGED_CRITERIA, requirements=[FUNCTIONAL])

#: What a failing attempt hands the next one (FR-006) — quoted verbatim, so the
#: assertions can look for it character-for-character.
PRIOR_FEEDBACK = (
    "US2-S1 fails: run_gates() returns early on the first non-zero exit, so the "
    "typecheck gate never runs and its result is missing from the evidence."
)

DIFF_TEXT = (
    "diff --git a/src/gates.py b/src/gates.py\n"
    "index 1111111..2222222 100644\n"
    "--- a/src/gates.py\n"
    "+++ b/src/gates.py\n"
    "@@ -1,3 +1,4 @@\n"
    "+    results.append(_to_result(invocation, backend.run(invocation)))\n"
)


# --- fixtures & helpers ----------------------------------------------------


@pytest.fixture
def env() -> ActivityEnvironment:
    return ActivityEnvironment()


def snapshot_input(**overrides: Any) -> SnapshotCriteriaInput:
    """A dispatch against the grammar fixture; override only what a test is about."""
    fields: dict[str, Any] = {
        "specs_root": str(CORPUS),
        "feature": FULL_GRAMMAR,
        "spec_ref": SPEC_REF,
        "requirement_keys": ["US1", "FR-002"],
    }
    fields.update(overrides)
    return SnapshotCriteriaInput(**fields)


async def snapshot(env: ActivityEnvironment, **overrides: Any) -> CriteriaSet:
    return await env.run(snapshot_criteria, snapshot_input(**overrides))


async def failing_snapshot(
    env: ActivityEnvironment, **overrides: Any
) -> ApplicationError:
    """Run a snapshot expected to fail, returning the application error raised."""
    with pytest.raises(ApplicationError) as excinfo:
        await snapshot(env, **overrides)
    return excinfo.value


def spec_path(feature: str) -> Path:
    return CORPUS / feature / "spec.md"


def keys(criteria: CriteriaSet) -> list[str]:
    return [requirement.key for requirement in criteria.requirements]


def assert_iso_utc(value: str) -> None:
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None, f"{value!r} is not timezone-aware"
    assert parsed.utcoffset() == timedelta(0), f"{value!r} is not UTC"


def copied_corpus(tmp_path: Path, feature: str) -> Path:
    """A writable specs root holding one fixture — for the edit-after-snapshot tests."""
    root = tmp_path / "specs"
    shutil.copytree(CORPUS / feature, root / feature)
    return root


async def failing_activity(
    env: ActivityEnvironment, fn: Any, request: Any
) -> ApplicationError:
    """Run any activity expected to refuse, returning the error it raised."""
    with pytest.raises(ApplicationError) as excinfo:
        await env.run(fn, request)
    return excinfo.value


def assert_credential_free(error: BaseException, *secrets: str) -> None:
    """No secret may appear anywhere in the raised chain (FR-009, SC-004)."""
    seen: BaseException | None = error
    depth = 0
    while seen is not None and depth < 10:
        for rendering in (str(seen), repr(seen), str(seen.args)):
            for secret in secrets:
                assert secret not in rendering, (
                    f"{secret!r} leaked into {type(seen).__name__}"
                )
        seen = seen.__cause__ or seen.__context__
        depth += 1


# --- evidence builders -------------------------------------------------------


def gate(
    name: str = "test",
    status: GateStatus = GateStatus.PASS,
    *,
    exit_code: int | None = 0,
    output_tail: str = "",
) -> GateResult:
    return GateResult(
        name=name,
        command=f"bash gates/{name}.sh",
        status=status,
        exit_code=exit_code,
        duration_s=0.25,
        output_tail=output_tail,
    )


GREEN_GATES = [gate("lint"), gate("test"), gate("typecheck")]


def output(
    *,
    passed: bool = True,
    has_diff: bool = True,
    write_scope: str = WriteScope.WORKTREE.value,
    expected_artifacts: Sequence[str] = (),
    artifacts_present: bool | None = None,
) -> OutputCheck:
    return OutputCheck(
        write_scope=write_scope,
        has_diff=has_diff,
        expected_artifacts=list(expected_artifacts),
        artifacts_present=artifacts_present,
        passed=passed,
    )


PASSED_OUTPUT = output()

#: The anti-rubber-stamp failure: a write-scoped node whose worktree is clean.
EMPTY_OUTPUT = output(passed=False, has_diff=False)


def judged(
    outcome: JudgeOutcome = JudgeOutcome.PASS,
    *,
    feedback: str = "every scenario is satisfied",
    judge_attempt: int = 1,
) -> JudgeVerdict:
    return JudgeVerdict(
        outcome=outcome,
        findings=[
            JudgeScenarioFinding(
                scenario=JUDGED_SCENARIO.scenario_id,
                passed=outcome is JudgeOutcome.PASS,
                reasoning="the diff satisfies every step",
            )
        ],
        feedback=feedback,
        judge_attempt=judge_attempt,
        truncated_input=False,
        model_alias=JUDGE_MODEL_ALIAS,
    )


def compose(**overrides: Any) -> VerificationResult:
    """Compose a result from all-green evidence; override what a test is about."""
    fields: dict[str, Any] = {
        "epic_id": EPIC,
        "node_id": NODE,
        "attempt": ATTEMPT,
        "form": VerificationForm.PHASE,
        "gate_results": GREEN_GATES,
        "output_check": PASSED_OUTPUT,
        "judge": judged(),
        "criteria_sha256": CRITERIA_SHA,
        "spec_ref": SPEC_REF,
        "started_at": STARTED_AT,
        "finished_at": FINISHED_AT,
    }
    fields.update(overrides)
    return compose_result(**fields)


# --- store helpers -----------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the recording activity at a scratch evidence store."""
    path = tmp_path / ".factory" / "verification.db"
    monkeypatch.setenv(VERIFICATION_DB_PATH_ENV, str(path))
    return path


def stored_rows(path: Path) -> list[dict[str, Any]]:
    """Every evidence row, read back with plain `sqlite3` (quickstart §5)."""
    if not path.exists():
        return []
    conn = sqlite3.connect(path)
    try:
        cursor = conn.execute("SELECT * FROM verification_results ORDER BY id")
        return [
            {column[0]: value for column, value in zip(cursor.description, row)}
            for row in cursor.fetchall()
        ]
    finally:
        conn.close()


def only_stored_row(path: Path) -> dict[str, Any]:
    rows = stored_rows(path)
    assert len(rows) == 1, f"expected exactly one evidence row, found {len(rows)}"
    return rows[0]


async def record(
    env: ActivityEnvironment,
    result: VerificationResult,
    *,
    criteria_source_path: Path | str | None = None,
) -> Any:
    return await env.run(
        record_verification,
        RecordVerificationInput(
            result=result,
            criteria_source_path=(
                None if criteria_source_path is None else str(criteria_source_path)
            ),
        ),
    )


def write_criteria_source(tmp_path: Path, text: str = "# spec\n") -> tuple[Path, str]:
    """A stand-in spec file and the hash a dispatch-time snapshot of it carried."""
    path = tmp_path / "spec.md"
    path.write_text(text, encoding="utf-8")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


# --- judge helpers -----------------------------------------------------------


@pytest.fixture
def judge_proxy(monkeypatch: pytest.MonkeyPatch) -> FakeJudgeProxy:
    """A fake `/chat/completions` behind the activity's transport seam.

    The seam supplies only a transport, so the per-attempt virtual key still has
    to arrive from the dispatch and the fake still 401s if the wrong credential
    shows up. Backoff is zeroed because these tests are about the mapping from an
    outage to an error type, not about how long the judge waits.
    """
    monkeypatch.setenv("LITELLM_MASTER_KEY", MASTER_KEY)
    proxy = FakeJudgeProxy()
    monkeypatch.setattr(verify_activities, "judge_transport", lambda: proxy.transport)
    monkeypatch.setattr(verify_activities, "JUDGE_RETRY_BACKOFF_S", 0.0)
    return proxy


def judge_input(**overrides: Any) -> RunJudgeInput:
    fields: dict[str, Any] = {
        "criteria": JUDGED_CRITERIA,
        "diff_text": DIFF_TEXT,
        "virtual_key": JUDGE_VIRTUAL_KEY,
        "proxy_url": JUDGE_PROXY_URL,
        "model_alias": JUDGE_MODEL_ALIAS,
        "judge_attempt": 1,
    }
    fields.update(overrides)
    return RunJudgeInput(**fields)


async def ask_judge(env: ActivityEnvironment, **overrides: Any) -> JudgeVerdict:
    return await env.run(run_judge, judge_input(**overrides))


def scenario_pass(feedback: str = "the scenario is satisfied") -> str:
    return verdict_json(
        verdict="pass",
        scenarios=[(JUDGED_SCENARIO.scenario_id, True)],
        feedback=feedback,
    )


# --- registration ----------------------------------------------------------


@pytest.mark.parametrize(
    "fn",
    [snapshot_criteria, run_gates, check_output, run_judge, record_verification],
    ids=lambda fn: fn.__name__,
)
def test_every_activity_is_registered_under_its_contract_name(fn: Any) -> None:
    # A worker can only register decorated callables, and the name is what
    # contracts/activities.md tells the workflow side to call — so a rename here
    # is a workflow that calls into nothing.
    definition = activity._Definition.from_callable(fn)
    assert definition is not None, f"{fn.__name__} must carry @activity.defn"
    assert definition.name == fn.__name__


# --- the snapshot ----------------------------------------------------------


async def test_snapshot_returns_the_requested_requirements_in_request_order(
    env: ActivityEnvironment,
) -> None:
    criteria = await snapshot(env, requirement_keys=["FR-002", "US1"])

    assert isinstance(criteria, CriteriaSet)
    # The node owes exactly what it was dispatched against — no more (the
    # fixture declares three stories and four FRs), and in the order asked for.
    assert keys(criteria) == ["FR-002", "US1"]

    story = criteria.requirements[1]
    assert story.kind is RequirementKind.STORY
    assert story.priority == "P1"
    # The scenarios travel with the story: they are what the judge scores
    # (FR-003), so an activity that returned bare keys would be useless.
    assert [scenario.scenario_id for scenario in story.scenarios] == [
        "US1-S1",
        "US1-S2",
        "US1-S3",
    ]


async def test_snapshot_carries_its_attribution_and_source(
    env: ActivityEnvironment,
) -> None:
    criteria = await snapshot(env)

    assert criteria.feature == FULL_GRAMMAR
    # spec_ref comes from the dispatch, not the file: it is component 1's
    # work-attribution key and the activity has no business inventing one.
    assert criteria.spec_ref == SPEC_REF
    # The path the operator would open — `<specs_root>/<feature>/spec.md` (D-023).
    assert Path(criteria.source_path) == spec_path(FULL_GRAMMAR)


async def test_snapshot_hashes_the_raw_spec_bytes_and_stamps_the_moment(
    env: ActivityEnvironment,
) -> None:
    criteria = await snapshot(env)

    # Raw bytes, not parsed requirements: drift asks "did the system of record
    # change under this node?", and a whitespace-only edit is still an edit (R8).
    expected = hashlib.sha256(spec_path(FULL_GRAMMAR).read_bytes()).hexdigest()
    assert criteria.source_sha256 == expected
    assert_iso_utc(criteria.snapshotted_at)


async def test_no_requested_keys_snapshots_the_whole_spec(
    env: ActivityEnvironment,
) -> None:
    criteria = await snapshot(env, requirement_keys=[])

    # An unfiltered dispatch is a legitimate one (a node that owes the whole
    # feature); it must not quietly mean "no criteria", which would let an
    # empty diff sail through the judge with nothing to score.
    assert keys(criteria) == ["US1", "US2", "US3", "FR-001", "FR-002", "FR-003", "FR-004"]


async def test_snapshotting_twice_agrees_on_everything_but_the_clock(
    env: ActivityEnvironment,
) -> None:
    first = await snapshot(env)
    second = await snapshot(env)

    # Pure read, safe to retry (contracts/activities.md): Temporal running it
    # twice must not hand the node two different sets of goalposts.
    assert first.requirements == second.requirements
    assert first.source_sha256 == second.source_sha256
    assert (first.feature, first.spec_ref, first.source_path) == (
        second.feature,
        second.spec_ref,
        second.source_path,
    )


async def test_a_snapshot_is_unaffected_by_a_later_edit_to_the_spec(
    env: ActivityEnvironment, tmp_path: Path
) -> None:
    root = copied_corpus(tmp_path, FULL_GRAMMAR)
    taken = await snapshot(env, specs_root=str(root))

    edited = root / FULL_GRAMMAR / "spec.md"
    edited.write_bytes(edited.read_bytes() + b"\n<!-- an operator kept typing -->\n")
    later = await snapshot(env, specs_root=str(root))

    # The snapshot in workflow state stays the attempt's goalposts (FR-010);
    # only a fresh read sees the new bytes, and the difference between the two
    # hashes is precisely the drift signal a verification result carries (R8).
    assert taken.source_sha256 != later.source_sha256
    assert taken.requirements == later.requirements


async def test_the_real_world_spec_snapshots_through_the_activity(
    env: ActivityEnvironment,
) -> None:
    criteria = await snapshot(
        env, feature=REAL_WORLD, requirement_keys=["US2", "FR-009"]
    )

    # Component 1's shipped spec, unedited: the grammar has to survive contact
    # with a file nobody wrote for the parser (SC-001, D-024).
    assert keys(criteria) == ["US2", "FR-009"]
    assert criteria.requirements[0].scenarios
    assert "MUST" in criteria.requirements[1].body or "SHALL" in (
        criteria.requirements[1].body
    )


# --- refusals --------------------------------------------------------------


async def test_a_malformed_spec_fails_with_the_validation_message(
    env: ActivityEnvironment,
) -> None:
    error = await failing_snapshot(
        env, feature="014-fr-missing-modal", requirement_keys=[]
    )

    assert error.type == CRITERIA_PARSE_FAILED
    message = str(error)
    # The parser's message is the operator's entire diagnosis: which
    # requirement, and what is wrong with it (spec US1). Losing it at the
    # activity boundary would make this error strictly less useful than the
    # library call it wraps.
    assert "FR-002" in message
    assert "MUST" in message or "SHALL" in message
    # And it still names only the offender — the well-formed siblings would
    # send the operator to the wrong line.
    assert "FR-001" not in message
    assert "FR-003" not in message


async def test_a_malformed_spec_is_not_retried(env: ActivityEnvironment) -> None:
    error = await failing_snapshot(
        env, feature="012-story-without-scenarios", requirement_keys=[]
    )

    assert error.type == CRITERIA_PARSE_FAILED
    assert "US2" in str(error)
    # Re-reading the same bytes a second later produces the same failure. The
    # retry budget is for proxies and worktrees; a spec with no acceptance
    # scenarios needs a human, so the ladder should escalate rather than spin.
    assert error.non_retryable is True


async def test_the_whole_spec_is_validated_even_when_one_key_is_requested(
    env: ActivityEnvironment,
) -> None:
    error = await failing_snapshot(
        env, feature="014-fr-missing-modal", requirement_keys=["US1"]
    )

    # A lazily-validated spec would let this node dispatch happily while the
    # next node against the same file refuses — two nodes disagreeing about
    # whether the system of record is usable.
    assert error.type == CRITERIA_PARSE_FAILED
    assert "FR-002" in str(error)


async def test_a_requested_key_the_spec_does_not_declare_names_that_key(
    env: ActivityEnvironment,
) -> None:
    error = await failing_snapshot(env, requirement_keys=["US1", "FR-404"])

    # Dispatching against a key that does not exist would verify the node
    # against nothing, and a node verified against nothing passes on an empty
    # diff — exactly what FR-004 exists to prevent.
    assert error.type == CRITERIA_PARSE_FAILED
    assert "FR-404" in str(error)


async def test_an_absent_spec_file_is_a_missing_file_not_a_parse_failure(
    env: ActivityEnvironment, tmp_path: Path
) -> None:
    error = await failing_snapshot(env, specs_root=str(tmp_path))

    # A wiring mistake (wrong specs root, wrong feature name) and a spec that
    # needs editing are different jobs for different people, so they are
    # different error types — the workflow must be able to tell them apart
    # without reading prose.
    assert error.type == CRITERIA_FILE_MISSING
    assert error.type != CRITERIA_PARSE_FAILED
    # The message says which path was tried; "file missing" without the path is
    # unactionable when the root, the feature and the filename are all suspects.
    assert str(tmp_path / FULL_GRAMMAR / "spec.md") in str(error)
    assert error.non_retryable is True


async def test_a_feature_directory_without_a_spec_is_also_missing(
    env: ActivityEnvironment, tmp_path: Path
) -> None:
    root = tmp_path / "specs"
    (root / FULL_GRAMMAR).mkdir(parents=True)

    error = await failing_snapshot(env, specs_root=str(root))

    # The directory existing proves nothing: D-023 names `spec.md` as the
    # system of record, and an empty feature directory has no criteria in it.
    assert error.type == CRITERIA_FILE_MISSING


# --- run_gates -------------------------------------------------------------


async def test_gates_come_back_one_per_declared_gate_in_declaration_order(
    env: ActivityEnvironment, node_worktree: Callable[..., Path]
) -> None:
    worktree = node_worktree("passing")

    results = await env.run(run_gates, RunGatesInput(worktree_path=str(worktree)))

    # The fixture declares lint → test → typecheck, which is neither alphabetical
    # nor the contract's listing order: a runner that sorted gate names would
    # spend a full test run before the lint that fails in two seconds.
    assert [result.name for result in results] == ["lint", "test", "typecheck"]
    assert {result.status for result in results} == {GateStatus.PASS}
    # And the commands really ran, in that order, in the worktree — the log is
    # written by the gate scripts themselves, not inferred from the results.
    assert gate_order(worktree) == ["lint", "test", "typecheck"]


async def test_a_long_gate_suite_heartbeats_as_it_goes(
    env: ActivityEnvironment, node_worktree: Callable[..., Path]
) -> None:
    loop_thread = threading.current_thread()
    beats: list[tuple[Any, ...]] = []
    beat_threads: list[threading.Thread] = []

    def record(*args: Any) -> None:
        beats.append(args)
        beat_threads.append(threading.current_thread())

    env.on_heartbeat = record

    await env.run(run_gates, RunGatesInput(worktree_path=str(node_worktree("passing"))))

    # A repo's test suite may legitimately run for ten minutes (the default
    # per-gate deadline), so an activity that reported nothing until the last
    # gate finished would be killed by its own heartbeat timeout long before it
    # had an answer (contracts/activities.md).
    assert [args[0] for args in beats] == ["lint", "test", "typecheck"]
    # And every beat was DELIVERED from the event-loop thread. The gates run in
    # `asyncio.to_thread`'s worker thread, and an async activity's heartbeat
    # called there dies in `asyncio.create_task` under a real worker (found
    # live 2026-08-05) — while this environment's synchronous heartbeat
    # happily records it, which is exactly why the thread is asserted and not
    # just the beat.
    assert set(beat_threads) == {loop_thread}, (
        "gate heartbeats must be marshalled onto the event loop, not fired "
        "from the gate executor's thread"
    )


async def test_a_failing_gate_is_data_and_does_not_cancel_the_gates_after_it(
    env: ActivityEnvironment, node_worktree: Callable[..., Path]
) -> None:
    worktree = node_worktree("failing-gate")

    results = await env.run(run_gates, RunGatesInput(worktree_path=str(worktree)))

    # Gate failures are evidence, never exceptions: an activity that raised
    # would cost the attempt the very output the retry prompt quotes (FR-006).
    assert [(result.name, result.status) for result in results] == [
        ("lint", GateStatus.PASS),
        ("test", GateStatus.FAIL),
        ("typecheck", GateStatus.PASS),
    ]
    failed = results[1]
    assert failed.exit_code == 3
    # Both streams: the line explaining the failure was written to stderr.
    assert "assert add(2, 2) == 5" in failed.output_tail


async def test_a_hanging_gate_comes_back_as_a_timeout(
    env: ActivityEnvironment, node_worktree: Callable[..., Path]
) -> None:
    worktree = node_worktree("hanging-gate")

    results = await env.run(run_gates, RunGatesInput(worktree_path=str(worktree)))

    timed_out = results[0]
    assert timed_out.status is GateStatus.TIMEOUT
    # There was no exit status to read, and the evidence says so rather than
    # inventing one — a `0` here would read as a pass.
    assert timed_out.exit_code is None
    # What it printed before it was killed is kept: that is where the
    # explanation is.
    assert "hang: started" in timed_out.output_tail
    # And the deadline did not swallow the gate declared after it.
    assert [result.name for result in results] == ["test", "typecheck"]


async def test_a_missing_manifest_is_one_config_error_not_an_empty_gate_list(
    env: ActivityEnvironment, node_worktree: Callable[..., Path]
) -> None:
    worktree = node_worktree("missing-manifest")

    results = await env.run(run_gates, RunGatesInput(worktree_path=str(worktree)))

    # An empty list is exactly the shape a naive verdict reads as "nothing
    # failed" (SC-002), so an unusable manifest is one gate result that fails.
    assert len(results) == 1
    config = results[0]
    assert (config.name, config.status) == ("config", GateStatus.CONFIG_ERROR)
    assert config.exit_code is None
    # The message names the rule violated, because the operator's next action is
    # to edit the manifest (contracts/factory-yaml.md).
    assert "factory.yaml" in config.output_tail


async def test_a_manifest_outside_the_worktree_and_an_overridden_deadline(
    env: ActivityEnvironment, node_worktree: Callable[..., Path], tmp_path: Path
) -> None:
    worktree = node_worktree("passing")
    manifest = tmp_path / "operator-factory.yaml"
    manifest.write_text(
        "version: 1\nruntime: python:3.11-bookworm\ngates:\n  test: \"sleep 30\"\n",
        encoding="utf-8",
    )

    results = await env.run(
        run_gates,
        RunGatesInput(
            worktree_path=str(worktree),
            factory_yaml_path=str(manifest),
            timeout_overrides={"test": 1},
        ),
    )

    # Two fields at once, because they fail the same way if the wrapper drops
    # them: the manifest read is the operator's, not the worktree's (whose three
    # gates never ran), and the deadline is the caller's, on a gate that
    # declared none.
    assert [(result.name, result.status) for result in results] == [
        ("test", GateStatus.TIMEOUT)
    ]
    assert gate_order(worktree) == []


# --- check_output ----------------------------------------------------------


async def test_a_clean_write_scope_worktree_does_not_pass(
    env: ActivityEnvironment, node_worktree: Callable[..., Path]
) -> None:
    worktree = node_worktree("passing")

    result = await env.run(
        check_output,
        CheckOutputInput(worktree_path=str(worktree), write_scope="worktree"),
    )

    # The floor under every other verdict (FR-004): an agent that burned its
    # budget and changed nothing does not get a PASS from a green test suite.
    assert result.has_diff is False
    assert result.passed is False
    # The scope arrives as a plain string across the Temporal payload boundary
    # and must resolve to the registry's member, not be echoed as a stranger.
    assert result.write_scope == WriteScope.WORKTREE.value


async def test_an_edited_file_is_proof_of_work(
    env: ActivityEnvironment, node_worktree: Callable[..., Path]
) -> None:
    worktree = node_worktree("passing")
    (worktree / TRACKED_FILE).write_text("def add(a, b):\n    return a + b + 0\n")

    result = await env.run(
        check_output,
        CheckOutputInput(
            worktree_path=str(worktree), write_scope=WriteScope.WORKTREE.value
        ),
    )

    assert (result.has_diff, result.passed) == (True, True)


async def test_a_read_scope_is_judged_on_its_declared_artifact(
    env: ActivityEnvironment, node_worktree: Callable[..., Path]
) -> None:
    worktree = node_worktree("passing")
    report = worktree / REPORT
    report.parent.mkdir(parents=True)
    report.write_text("# findings\n\nthe proxy pages at 100 rows.\n", encoding="utf-8")

    result = await env.run(
        check_output,
        CheckOutputInput(
            worktree_path=str(worktree),
            write_scope=WriteScope.READ.value,
            expected_artifacts=[REPORT],
        ),
    )

    # A researcher's output is a report, not a diff (R7); the diff is recorded
    # as evidence and ignored as a criterion.
    assert result.artifacts_present is True
    assert result.expected_artifacts == [REPORT]
    assert result.passed is True


async def test_an_empty_artifact_is_not_an_artifact(
    env: ActivityEnvironment, node_worktree: Callable[..., Path]
) -> None:
    worktree = node_worktree("passing")
    report = worktree / REPORT
    report.parent.mkdir(parents=True)
    report.touch()

    result = await env.run(
        check_output,
        CheckOutputInput(
            worktree_path=str(worktree),
            write_scope=WriteScope.READ.value,
            expected_artifacts=[REPORT],
        ),
    )

    # A zero-byte file is the shape "the agent created the path and gave up"
    # takes, and it proves nothing about the work.
    assert (result.artifacts_present, result.passed) == (False, False)


async def test_a_vanished_worktree_is_an_error_not_a_failed_verdict(
    env: ActivityEnvironment, tmp_path: Path
) -> None:
    missing = tmp_path / "worktrees" / "node-3"

    error = await failing_activity(
        env,
        check_output,
        CheckOutputInput(worktree_path=str(missing), write_scope="worktree"),
    )

    # An absent directory resembles a clean worktree exactly, and reading it as
    # one would charge an infrastructure failure to the agent's attempt budget —
    # the mirror image of the false PASS this component exists to prevent.
    assert error.type == WORKTREE_MISSING
    # By the time an operator sees this they are holding a node id, not a path.
    assert str(missing) in str(error)


async def test_gate_leavings_are_not_mistaken_for_agent_work(
    env: ActivityEnvironment, node_worktree: Callable[..., Path]
) -> None:
    worktree = node_worktree("passing")
    await env.run(run_gates, RunGatesInput(worktree_path=str(worktree)))
    assert (worktree / GATE_ORDER_LOG).exists()

    result = await env.run(
        check_output,
        CheckOutputInput(worktree_path=str(worktree), write_scope="worktree"),
    )

    # Verification runs the gates before it looks for a diff, so anything the
    # gates themselves leave behind would manufacture the proof of work FR-004
    # demands. Ignored files do not count as a diff.
    assert result.passed is False
    assert git(worktree, "status", "--porcelain").strip() == ""


# --- run_judge -------------------------------------------------------------


async def test_the_judge_scores_the_dispatched_scenario(
    env: ActivityEnvironment, judge_proxy: FakeJudgeProxy
) -> None:
    judge_proxy.reply(scenario_pass())

    verdict = await ask_judge(env)

    assert verdict.outcome is JudgeOutcome.PASS
    assert [finding.scenario for finding in verdict.findings] == [
        JUDGED_SCENARIO.scenario_id
    ]
    assert verdict.judge_attempt == 1
    # The alias comes from the dispatch, which read it from the persona registry:
    # code never names a model (constitution VII).
    assert verdict.model_alias == JUDGE_MODEL_ALIAS
    assert judge_proxy.last.path.endswith("/chat/completions")
    # The per-attempt key component 1 minted, not the worker's master key.
    assert judge_proxy.last.headers["authorization"] == f"Bearer {JUDGE_VIRTUAL_KEY}"
    assert MASTER_KEY not in judge_proxy.transcript()


async def test_the_prompt_carries_the_criteria_and_prior_feedback_verbatim(
    env: ActivityEnvironment, judge_proxy: FakeJudgeProxy
) -> None:
    judge_proxy.reply(scenario_pass())

    await ask_judge(env, prior_feedback=PRIOR_FEEDBACK, judge_attempt=2)

    sent = judge_proxy.last.user_message
    # Criteria are the standard being applied and feedback is what the last
    # attempt got wrong (FR-006, SC-004) — both travel character-for-character,
    # because a wrapper that summarized either would move the goalposts.
    assert JUDGED_SCENARIO.raw_text in sent
    assert JUDGED_STORY.body in sent
    assert PRIOR_FEEDBACK in sent


async def test_a_malformed_response_asks_for_another_judge_attempt(
    env: ActivityEnvironment, judge_proxy: FakeJudgeProxy
) -> None:
    judge_proxy.reply("Sure! The diff looks good to me.")

    verdict = await ask_judge(env, judge_attempt=1)

    # Garbage is neither a pass nor an error: it consumes one judge attempt and
    # comes back as RETRY carrying the parse failure as the next prompt's
    # feedback (R5).
    assert verdict.outcome is JudgeOutcome.RETRY
    assert verdict.findings == []
    assert "could not be read" in verdict.feedback


async def test_malformed_on_the_last_judge_attempt_is_a_failure(
    env: ActivityEnvironment, judge_proxy: FakeJudgeProxy
) -> None:
    judge_proxy.reply("still not JSON")

    verdict = await ask_judge(
        env,
        judge_attempt=1 + DEFAULT_MAX_JUDGE_RETRIES,
        max_judge_retries=DEFAULT_MAX_JUDGE_RETRIES,
    )

    # The bound is what keeps a model that cannot follow the schema from
    # becoming unbounded spend (SC-003) — and it lands on FAIL, never on a pass.
    assert verdict.outcome is JudgeOutcome.FAIL


async def test_a_stricter_finding_overrides_a_claimed_overall_pass(
    env: ActivityEnvironment, judge_proxy: FakeJudgeProxy
) -> None:
    judge_proxy.reply(
        verdict_json(
            verdict="pass",
            scenarios=[(JUDGED_SCENARIO.scenario_id, False)],
            feedback="US2-S1: the typecheck gate result is missing",
        )
    )

    verdict = await ask_judge(env)

    # Holistic passing is what FR-003 prohibits, and the prohibition survives
    # the activity boundary: the stricter reading wins.
    assert verdict.outcome is JudgeOutcome.RETRY


async def test_an_unreachable_proxy_is_an_outage_not_a_verdict(
    env: ActivityEnvironment, judge_proxy: FakeJudgeProxy
) -> None:
    judge_proxy.fail_always(503)

    error = await failing_activity(env, run_judge, judge_input())

    assert error.type == JUDGE_UNAVAILABLE
    # Bounded, so an outage cannot become an unbounded wait inside one activity.
    assert len(judge_proxy.calls) == MAX_HTTP_ATTEMPTS
    # Retryable, unlike the criteria errors above: a backend that is down now
    # may be up in a minute, and the gates-only fallback is the composer's
    # decision to take once the workflow's retry budget is spent.
    assert error.non_retryable is False
    assert_credential_free(error, MASTER_KEY, JUDGE_VIRTUAL_KEY)


async def test_a_rejected_virtual_key_never_echoes_a_credential(
    env: ActivityEnvironment, judge_proxy: FakeJudgeProxy
) -> None:
    wrong = "sk-wrong-attempt-key"

    error = await failing_activity(env, run_judge, judge_input(virtual_key=wrong))

    assert error.type == JUDGE_UNAVAILABLE
    # The error path is the one place a credential must not arrive by accident,
    # and the guarantee is enforced rather than assumed of the server (FR-009).
    assert_credential_free(error, MASTER_KEY, JUDGE_VIRTUAL_KEY, wrong)


# --- record_verification ---------------------------------------------------


async def test_recording_writes_one_operator_readable_row(
    env: ActivityEnvironment, db_path: Path
) -> None:
    recorded = await record(env, compose())

    row = only_stored_row(db_path)
    assert recorded.row_id == row["id"]
    assert (row["epic_id"], row["node_id"], row["attempt"]) == (EPIC, NODE, ATTEMPT)
    assert row["form"] == VerificationForm.PHASE.value
    assert row["verdict"] == OverallVerdict.PASS.value
    assert row["spec_ref"] == SPEC_REF
    # Flags are the integers the DDL's CHECK constraints accept, so the
    # quickstart's `sqlite3` queries read as written (quickstart §5).
    assert (row["judge_unavailable"], row["criteria_drift"]) == (0, 0)


async def test_recording_the_same_attempt_twice_lands_on_the_first_row(
    env: ActivityEnvironment, db_path: Path
) -> None:
    first = await record(env, compose())
    second = await record(env, compose(judge=judged(JudgeOutcome.RETRY)))

    # Temporal runs an activity at least once, so the upsert key
    # `(epic, node, attempt, form)` is what makes "one row per attempt" a
    # property of the schema rather than of the caller's care.
    assert second.row_id == first.row_id
    row = only_stored_row(db_path)
    # The second recording is the current one.
    assert row["verdict"] == OverallVerdict.FAIL.value


async def test_the_same_attempt_verified_twice_over_keeps_both_forms(
    env: ActivityEnvironment, db_path: Path
) -> None:
    await record(env, compose())
    await record(env, compose(form=VerificationForm.NODE))

    # One attempt can be verified both as a node's built-in phase and by an
    # explicit verifier node (FR-002); `form` is in the upsert key so the two
    # do not overwrite each other.
    assert [row["form"] for row in stored_rows(db_path)] == ["PHASE", "NODE"]


async def test_the_full_evidence_bundle_round_trips(
    env: ActivityEnvironment, db_path: Path
) -> None:
    result = compose(
        gate_results=[
            gate("lint"),
            gate("test", GateStatus.FAIL, exit_code=3, output_tail="E  assert 2 == 5"),
        ],
        judge=None,
    )

    await record(env, result)

    stored = store.connect(db_path)
    try:
        history = store.node_history(stored, EPIC, NODE)
    finally:
        stored.close()

    # The retry prompt quotes `output_tail` and judge feedback verbatim (FR-006,
    # SC-004) and escalation messages carry the full history (SC-005), so a
    # lossy write would not surface here — it would surface inside a prompt.
    assert len(history) == 1
    assert history[0].gate_results == result.gate_results
    assert history[0].output_check == result.output_check
    # NULL means the judge never ran, which is a different fact from a judge
    # that ran and returned FAIL.
    assert history[0].judge is None


@pytest.mark.parametrize(
    "missing, overrides",
    [
        ("epic_id", {"epic_id": ""}),
        ("epic_id", {"epic_id": "   "}),
        ("node_id", {"node_id": ""}),
        ("spec_ref", {"spec_ref": ""}),
        ("attempt", {"attempt": 0}),
    ],
    ids=["blank-epic", "whitespace-epic", "blank-node", "blank-spec-ref", "attempt-0"],
)
async def test_an_unattributable_result_is_refused_before_it_is_written(
    env: ActivityEnvironment, db_path: Path, missing: str, overrides: dict[str, Any]
) -> None:
    error = await failing_activity(
        env,
        record_verification,
        RecordVerificationInput(result=compose(**overrides)),
    )

    assert error.type == ATTRIBUTION_INCOMPLETE
    assert missing in str(error)
    # The dispatch is wrong, not the moment: a rerun rebuilds exactly the same
    # unaccountable row, so spinning on it only delays the diagnosis.
    assert error.non_retryable is True
    # Every escalation summary and every rollup reads this store by epic and
    # node; a row missing one is not merely thin, it is absent from the query
    # that would have shown the gap.
    assert stored_rows(db_path) == []


async def test_an_unchanged_spec_file_is_not_drift(
    env: ActivityEnvironment, db_path: Path, tmp_path: Path
) -> None:
    source, digest = write_criteria_source(tmp_path)

    recorded = await record(
        env, compose(criteria_sha256=digest), criteria_source_path=source
    )

    assert recorded.criteria_drift is False
    assert only_stored_row(db_path)["criteria_drift"] == 0


async def test_a_spec_edited_under_the_node_is_flagged_as_drift(
    env: ActivityEnvironment, db_path: Path, tmp_path: Path
) -> None:
    source, digest = write_criteria_source(tmp_path)
    source.write_text("# spec\n\nand one more requirement\n", encoding="utf-8")

    recorded = await record(
        env, compose(criteria_sha256=digest), criteria_source_path=source
    )

    # The node is still judged against the dispatch snapshot (FR-010); drift
    # flags the row so an operator can see the goalposts moved, and it never
    # changes the verdict.
    assert recorded.criteria_drift is True
    row = only_stored_row(db_path)
    assert row["criteria_drift"] == 1
    assert row["verdict"] == OverallVerdict.PASS.value
    # The snapshot's hash is what the row records, not the file's new one:
    # otherwise the evidence would agree with a spec the node never saw.
    assert row["criteria_sha256"] == digest


async def test_a_spec_that_vanished_is_drift_too(
    env: ActivityEnvironment, db_path: Path, tmp_path: Path
) -> None:
    source, digest = write_criteria_source(tmp_path)
    source.unlink()

    recorded = await record(
        env, compose(criteria_sha256=digest), criteria_source_path=source
    )

    # A deleted spec is the loudest form of "the system of record changed under
    # this node" (R8), and it must not read as "no drift detected".
    assert recorded.criteria_drift is True
    assert only_stored_row(db_path)["criteria_drift"] == 1


async def test_drift_the_caller_already_detected_is_never_cleared(
    env: ActivityEnvironment, db_path: Path, tmp_path: Path
) -> None:
    source, digest = write_criteria_source(tmp_path)

    recorded = await record(
        env,
        compose(criteria_sha256=digest, criteria_drift=True),
        criteria_source_path=source,
    )

    # The contract says the activity recomputes drift *if the caller hasn't*
    # (contracts/activities.md) — a caller that saw the spec change mid-attempt
    # must not have its finding overwritten by a file that has since been
    # restored.
    assert recorded.criteria_drift is True
    assert only_stored_row(db_path)["criteria_drift"] == 1


async def test_without_a_source_path_the_callers_flag_stands(
    env: ActivityEnvironment, db_path: Path
) -> None:
    recorded = await record(env, compose(criteria_drift=False))

    # Nothing to re-hash is not the same as "nothing changed", but it is the
    # only honest answer available, and inventing drift here would flag every
    # row an interpreter recorded without the path.
    assert recorded.criteria_drift is False
    assert only_stored_row(db_path)["criteria_drift"] == 0


def test_the_default_store_path_is_the_documented_one() -> None:
    # quickstart §5 tells the operator to open `.factory/verification.db`, and
    # the 001 ledger sits beside it under the same `.factory/` directory.
    assert DEFAULT_VERIFICATION_DB_PATH == ".factory/verification.db"
    assert VERIFICATION_DB_PATH_ENV.startswith("FACTORY_")


async def test_the_store_path_comes_from_the_worker_environment(
    env: ActivityEnvironment, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    elsewhere = tmp_path / "somewhere" / "else" / "verification.db"
    monkeypatch.setenv(VERIFICATION_DB_PATH_ENV, str(elsewhere))

    await record(env, compose())

    # Directories and all: the first verification of a fresh deployment must not
    # fail because nobody created `.factory/` first.
    assert len(stored_rows(elsewhere)) == 1


# --- the verdict truth table (SC-002) --------------------------------------


@pytest.mark.parametrize(
    "case, overrides, verdict, judge_unavailable",
    [
        (
            "all-green-and-the-judge-agrees",
            {},
            OverallVerdict.PASS,
            False,
        ),
        (
            "a-failing-gate-cannot-be-rescued",
            {"gate_results": [gate("lint"), gate("test", GateStatus.FAIL, exit_code=1)],
             "judge": None},
            OverallVerdict.FAIL,
            False,
        ),
        (
            "a-timed-out-gate-is-not-a-pass",
            {"gate_results": [gate("test", GateStatus.TIMEOUT, exit_code=None)],
             "judge": None},
            OverallVerdict.FAIL,
            False,
        ),
        (
            "an-unusable-manifest-never-passes-by-default",
            {"gate_results": [gate("config", GateStatus.CONFIG_ERROR, exit_code=None)],
             "judge": None},
            OverallVerdict.FAIL,
            False,
        ),
        (
            "an-empty-write-scope-diff-fails-past-green-gates",
            {"output_check": EMPTY_OUTPUT, "judge": None},
            OverallVerdict.FAIL,
            False,
        ),
        (
            "a-read-node-without-its-artifact-fails-too",
            {
                "output_check": output(
                    passed=False,
                    has_diff=False,
                    write_scope=WriteScope.READ.value,
                    expected_artifacts=[REPORT],
                    artifacts_present=False,
                ),
                "judge": None,
            },
            OverallVerdict.FAIL,
            False,
        ),
        (
            "a-judge-retry-is-still-a-failed-verification",
            {"judge": judged(JudgeOutcome.RETRY)},
            OverallVerdict.FAIL,
            False,
        ),
        (
            "a-judge-failure-is-a-failed-verification",
            {"judge": judged(JudgeOutcome.FAIL)},
            OverallVerdict.FAIL,
            False,
        ),
        (
            "an-unreachable-judge-falls-back-to-the-gates",
            {"judge": judged(JudgeOutcome.UNAVAILABLE)},
            OverallVerdict.PASS,
            True,
        ),
        (
            "an-unreachable-judge-cannot-rescue-a-failing-gate",
            {
                "gate_results": [gate("test", GateStatus.FAIL, exit_code=1)],
                "judge": judged(JudgeOutcome.UNAVAILABLE),
            },
            OverallVerdict.FAIL,
            True,
        ),
        (
            "a-node-with-no-scenarios-passes-on-gates-and-output-alone",
            {"judge": None},
            OverallVerdict.PASS,
            False,
        ),
        (
            "no-gates-at-all-is-not-nothing-failed",
            {"gate_results": [], "judge": None},
            OverallVerdict.FAIL,
            False,
        ),
    ],
    ids=lambda value: value if type(value) is str else None,
)
def test_the_verdict_truth_table(
    case: str,
    overrides: dict[str, Any],
    verdict: OverallVerdict,
    judge_unavailable: bool,
) -> None:
    result = compose(**overrides)

    # This function is the only thing between a green-looking attempt and an
    # unlocked downstream edge (FR-005), so every row of data-model.md's table
    # is here, including the vacuous one: a verification that ran no gates
    # verified nothing, and "no failures" is not the same as "passed".
    assert result.verdict is verdict, case
    assert result.judge_unavailable is judge_unavailable, case


def test_drift_flags_a_result_and_never_changes_its_verdict() -> None:
    drifted = compose(criteria_drift=True)
    steady = compose(criteria_drift=False)

    # Drift is evidence, not a decision (R8): the same evidence must compose to
    # the same verdict whether or not the spec moved.
    assert drifted.criteria_drift is True
    assert drifted.verdict is steady.verdict is OverallVerdict.PASS


def test_composition_carries_the_evidence_through_untouched() -> None:
    result = compose()

    # The composer decides two fields and copies the rest: an evidence bundle
    # that was edited on its way into the store would make the row disagree
    # with the retry prompt built from the same values.
    assert result.gate_results == GREEN_GATES
    assert result.output_check == PASSED_OUTPUT
    assert result.judge == judged()
    assert (result.started_at, result.finished_at) == (STARTED_AT, FINISHED_AT)
    assert result.criteria_sha256 == CRITERIA_SHA


# --- cheapest first (flow invariant 2) -------------------------------------


@pytest.mark.parametrize(
    "case, gates, out, criteria, required",
    [
        ("all-green-with-scenarios", GREEN_GATES, PASSED_OUTPUT, JUDGED_CRITERIA, True),
        (
            "a-failing-gate-stops-before-the-judge",
            [gate("lint"), gate("test", GateStatus.FAIL, exit_code=1)],
            PASSED_OUTPUT,
            JUDGED_CRITERIA,
            False,
        ),
        (
            "a-timeout-stops-before-the-judge",
            [gate("test", GateStatus.TIMEOUT, exit_code=None)],
            PASSED_OUTPUT,
            JUDGED_CRITERIA,
            False,
        ),
        (
            "an-unusable-manifest-stops-before-the-judge",
            [gate("config", GateStatus.CONFIG_ERROR, exit_code=None)],
            PASSED_OUTPUT,
            JUDGED_CRITERIA,
            False,
        ),
        (
            "an-empty-diff-stops-before-the-judge",
            GREEN_GATES,
            EMPTY_OUTPUT,
            JUDGED_CRITERIA,
            False,
        ),
        (
            "nothing-to-score-stops-before-the-judge",
            GREEN_GATES,
            PASSED_OUTPUT,
            FR_ONLY_CRITERIA,
            False,
        ),
        ("no-gates-ran-at-all", [], PASSED_OUTPUT, JUDGED_CRITERIA, False),
    ],
    ids=lambda value: value if type(value) is str else None,
)
def test_when_the_judge_is_worth_asking(
    case: str,
    gates: list[GateResult],
    out: OutputCheck,
    criteria: CriteriaSet,
    required: bool,
) -> None:
    # Cheapest-first is invariant 2 of contracts/verification-flow.md, and it is
    # a spend decision as much as a correctness one: a node whose lint gate
    # failed in two seconds must not cost a judge completion to find that out.
    assert judge_required(gates, out, criteria) is required, case


async def test_a_failing_gate_means_the_judge_is_never_asked(
    env: ActivityEnvironment, judge_proxy: FakeJudgeProxy
) -> None:
    gates = [gate("lint"), gate("test", GateStatus.FAIL, exit_code=3)]

    # The reference flow's own guard, in the shape contracts/verification-flow.md
    # writes it. The fake has no scripted reply, so a wrong predicate here does
    # not merely fail this assertion — it fails loudly, on a proxy call that
    # should never have happened.
    consulted = judge_required(gates, PASSED_OUTPUT, JUDGED_CRITERIA)
    if consulted:
        await ask_judge(env)

    assert consulted is False
    assert judge_proxy.calls == [], "the judge was consulted over a failed gate"
    assert compose(gate_results=gates, judge=None).verdict is OverallVerdict.FAIL
