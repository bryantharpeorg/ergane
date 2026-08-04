"""The activity surface of verification — starting with the criteria snapshot.

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

The corpus is `tests/fixtures/speckit/` — the same real files
`tests/test_criteria.py` parses, including component 1's shipped spec. Testing
the activity against inline strings would prove only that the wrapper forwards
its argument; testing it against the corpus proves the wiring an operator
actually gets: `<specs_root>/<feature>/spec.md`.

Written before `factory/activities/verify_activities.py` exists (T010 precedes
T011): until the module lands, every test here fails at import. T021 extends
this file with the remaining verification activities.
"""

from __future__ import annotations

import hashlib
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from temporalio import activity
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from factory.activities.verify_activities import (
    CRITERIA_FILE_MISSING,
    CRITERIA_PARSE_FAILED,
    SnapshotCriteriaInput,
    snapshot_criteria,
)
from factory.verify.models import CriteriaSet, RequirementKind

CORPUS = Path(__file__).resolve().parent / "fixtures" / "speckit"

#: The fixture exercising every production of the grammar (architecture §2).
FULL_GRAMMAR = "010-full-grammar"

#: The real-world fixture: a verbatim copy of component 1's shipped spec.
REAL_WORLD = "001-usage-tracking"

#: The node's work-attribution key, carried through untouched (component 1).
SPEC_REF = "library-loans/borrow-flow"


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


# --- registration ----------------------------------------------------------


def test_the_activity_is_registered_under_its_contract_name() -> None:
    # A worker can only register decorated callables; the name is what
    # contracts/activities.md tells the workflow side to call.
    definition = activity._Definition.from_callable(snapshot_criteria)
    assert definition is not None, "snapshot_criteria must carry @activity.defn"
    assert definition.name == "snapshot_criteria"


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
