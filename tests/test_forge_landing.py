"""049-US3: the landing path proposes, lands and observes through the forge.

Every test says what edit would make it fail; the transcript proving each answer
is at `specs/049-forge-seam/evidence/us3-mutations.md`. Scope fence: US2 owns
`onboard.py` and US5 the manifest parser, and the prose in `onboard_target_repo`
still naming `gh` is US2's — which is why the sweep below is scoped to the five
landing activities.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import inspect
from pathlib import Path

import pytest
from temporalio.converter import DataConverter

from factory.activities import merge_activities
from factory.mergequeue.classify import classify
from factory.mergequeue.forge import ForgeError, Proposal
from factory.mergequeue.models import (
    CheckFailure,
    Landing,
    LandingConfig,
    LandingState,
    PrSnapshot,
    QueueOutcome,
)
from tests.fake_forge import FakeForge, RepositoryModel
from tests.test_mergequeue_sweep import COMMAND_MODULES

REPO_ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-08-16T10:05:00Z"
HEAD = "factory/049-forge-seam/us3"

#: The activities this story rewires — a literal, so a rename or a deletion
#: fails rather than quietly shrinking what the sweep below checks.
LANDING_ACTIVITIES = (
    "open_landing_pr", "enqueue_landing", "poll_landing",
    "disable_auto_merge", "fetch_check_failure",
)


def _outcome(snapshot: PrSnapshot) -> QueueOutcome | None:
    landing = Landing(
        node_id="us3", branch=HEAD, pr_number=7,
        enqueued_at="2026-08-16T10:00:00Z", state=LandingState.ENQUEUED,
    )
    return classify(snapshot, landing, LandingConfig(), now=NOW)


def _open_one(model: RepositoryModel) -> tuple[FakeForge, Proposal]:
    """A forge holding one open proposal whose landing has been requested."""
    forge = FakeForge(model)
    proposal = forge.open_proposal(
        base="main", head=HEAD, title="t", body_file="/tmp/body.md"
    )
    forge.request_landing(proposal.number)
    return forge, proposal


# --- US3-S1 / FR-009: one landing's whole life, through the seam --------------


def test_a_landing_runs_its_whole_life_through_the_forge() -> None:
    """T021, the story's Independent Test: find, open, request landing, observe
    merged, observe rejected, fetch evidence, withdraw, and a refusal. Every
    assertion is on what `classify` says about the *model*, never on which calls
    were made — which keeps this out of the shape filed as
    `ci/the-scripted-gh-fake-never-consumes-an-expectation`. What edit would make
    it fail? Any operation returning something the classifier cannot read.
    """
    model = RepositoryModel(address="acme/app", default_branch="main")
    forge = FakeForge(model)

    # Nothing offered yet: the idempotent open must look before it offers.
    assert forge.find_proposal(HEAD) is None

    opened = forge.open_proposal(
        base="main", head=HEAD, title="049-forge-seam/us3: US3",
        body_file="/tmp/body.md",
    )
    assert isinstance(opened, Proposal)
    # Offering again finds what is there — a forge holds one landing per head.
    assert forge.find_proposal(HEAD) == opened

    forge.request_landing(opened.number)
    assert _outcome(forge.observe_proposal(opened.number)) is None

    model.landings.land(opened.number, at="2026-08-16T10:04:00Z")
    assert _outcome(forge.observe_proposal(opened.number)) == QueueOutcome.MERGED

    # A second life: the same repository rejects a proposal on failing checks,
    # and the evidence for that rejection comes back through the same seam.
    rejected = forge.open_proposal(
        base="main", head="factory/049-forge-seam/us9", title="t",
        body_file="/tmp/b.md",
    ).number
    forge.request_landing(rejected)
    model.landings.fail_checks(rejected, ("test",), log="FAILED test_add\n")

    observed = forge.observe_proposal(rejected)
    assert _outcome(observed) == QueueOutcome.CHECKS_FAILED
    assert observed.failing_required_checks == ("test",)
    assert forge.failing_check_evidence(rejected, ("test",)) == (
        CheckFailure(
            "test",
            "https://forge.invalid/acme/app/proposals/2/checks/test",
            "FAILED test_add\n",
            "",
        ),
    )

    # One record per requested name whatever happened: a check whose log the
    # forge kept none of degrades, and one it never heard of still comes back.
    model.landings.fail_checks(rejected, ("test",), log="")
    degraded = forge.failing_check_evidence(rejected, ("test", "absent"))
    assert [e.name for e in degraded] == ["test", "absent"]
    assert degraded[0].note != "" and degraded[1].note != ""

    # Withdrawing leaves the proposal open and un-landed — the kill path.
    forge.withdraw_landing(rejected)
    withdrawn = forge.observe_proposal(rejected)
    assert (withdrawn.state, withdrawn.merged_at) == ("OPEN", None)
    assert model.landings.proposals[rejected].landing_requested is False

    # A repository that stops accepting landing requests refuses as data.
    model.landings.refuse_landing = "landing is turned off for this repository"
    with pytest.raises(ForgeError) as excinfo:
        forge.request_landing(rejected)
    assert "turned off" in excinfo.value.detail


def _spelled_in(function: ast.AST) -> set[str]:
    """Every name, attribute and non-docstring string the function's code spells."""
    docstring = getattr(getattr(function, "body")[0], "value", None)
    found: set[str] = set()
    for node in ast.walk(function):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node is not docstring:
                found.add(node.value)
    return found


def test_the_landing_activities_name_no_forge_native_client() -> None:
    """T022 / US3-S1: no landing activity constructs a client or names `gh`, read
    off the *code* of the five and the module's imports, so a command no test
    happens to issue still cannot be one the code can issue. What edit would make
    this fail? Putting `GhClient(` back into any of the five, or re-importing
    `factory.mergequeue.gh`.
    """
    source = Path(inspect.getfile(merge_activities)).read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "factory.mergequeue.gh" not in imported, sorted(imported)

    activities = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in LANDING_ACTIVITIES
    }
    # Anti-vacuity: a renamed activity fails here rather than dropping out of
    # the sweep and leaving it scanning nothing.
    assert set(activities) == set(LANDING_ACTIVITIES), sorted(activities)

    offenders = [
        f"{name}: {word!r}"
        for name, node in activities.items()
        for word in _spelled_in(node)
        if set(word.lower().replace("-", "_").split("_")) & {"gh", "github"}
        or word.startswith("Gh")
    ]
    assert offenders == [], f"landing activities still naming a client: {offenders}"


#: Every landing test in `tests/test_merge_activities.py` — the suite written
#: against `gh` that must survive the move untouched.
LANDING_SUITE_TESTS = (
    "test_open_landing_pr_pushes_then_creates_a_ready_pr",
    "test_open_landing_pr_is_idempotent_reusing_an_existing_pr",
    "test_enqueue_landing_issues_auto_merge_from_config",
    "test_enqueue_landing_returns_a_queue_disabled_refusal_as_data",
    "test_poll_landing_returns_a_pr_snapshot",
    "test_disable_auto_merge_is_best_effort",
    "test_recovery_reenqueue_reuses_the_same_pr",
    "test_fetch_check_failure_returns_per_check_evidence",
    "test_fetch_check_failure_degrades_on_gh_error",
    "test_fetch_check_failure_degrades_when_link_has_no_run_id",
    "test_fetch_check_failure_uses_asyncio_to_thread",
)

#: sha256 over those tests' `assert` statements, whitespace-normalised, and how
#: many there are — the count pinned separately so a sweep that collected none
#: cannot match by hashing the empty string.
LANDING_SUITE_ASSERTION_DIGEST = (
    "3a0e47887df157d78bab4ecc5666b934c8eadc39b5f1e2304ba507ae9502be67"
)
LANDING_SUITE_ASSERTION_COUNT = 33


def test_the_existing_landing_suite_passes_with_no_assertion_changed() -> None:
    """T022 / US3-S1's second half, made mechanical: "the suite passes
    unmodified" cannot be proved by running it, since a modified suite passes
    too. This pins every `assert`'s source text in those eleven, so changing,
    adding or deleting one fails here.
    """
    path = REPO_ROOT / "tests" / "test_merge_activities.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    collected = [
        " ".join((ast.get_source_segment(source, statement) or "").split())
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in LANDING_SUITE_TESTS
        for statement in ast.walk(node)
        if isinstance(statement, ast.Assert)
    ]

    assert len(collected) == LANDING_SUITE_ASSERTION_COUNT, (
        f"the landing suite now has {len(collected)} assertions across "
        f"{len(LANDING_SUITE_TESTS)} tests, not {LANDING_SUITE_ASSERTION_COUNT}"
    )
    digest = hashlib.sha256("\n".join(collected).encode("utf-8")).hexdigest()
    assert digest == LANDING_SUITE_ASSERTION_DIGEST, (
        "an assertion in tests/test_merge_activities.py changed; US3-S1 requires "
        "the existing landing suite to pass with none of them touched"
    )


# --- US3-S2 / FR-010: CONFLICT comes from a neutral fact ----------------------

#: GitHub's `mergeStateStatus` vocabulary and the fields carrying it; none may
#: appear in the classifier's source. `state == "CLOSED"` and `autoMergeRequest`
#: are deliberately absent: FR-010 asks for one neutral fact, and trap 12 is
#: explicit that making every observation decisive is to be resisted.
FORGE_NATIVE_STATUS_LITERALS = (
    "DIRTY", "BLOCKED", "BEHIND", "UNSTABLE", "HAS_HOOKS",
    "mergeStateStatus", "merge_state_status",
)


def test_a_forge_reporting_a_conflict_yields_conflict_from_a_neutral_fact() -> None:
    """T023 / US3-S2, both halves. The control is the point: this forge's
    `merge_state_status` is the empty string — it has never heard of `DIRTY` —
    and `CONFLICT` still comes out, where a classifier that had merely been
    renamed would answer `None`. Then `classify.py`'s source, docstrings swept
    too. What edit would make it fail? Reverting `classify` to read
    `merge_state_status`."""
    model = RepositoryModel()
    forge, proposal = _open_one(model)
    model.landings.target_moved(proposal.number)

    observed = forge.observe_proposal(proposal.number)
    assert observed.in_conflict is True
    assert observed.merge_state_status == ""
    assert _outcome(observed) == QueueOutcome.CONFLICT

    source = (REPO_ROOT / "factory" / "mergequeue" / "classify.py").read_text(
        encoding="utf-8"
    )
    # Anti-vacuity: a sweep that read nothing, or the wrong file, passes forever.
    assert "QueueOutcome.CONFLICT" in source, "read the wrong file, or an empty one"
    spelled = [word for word in FORGE_NATIVE_STATUS_LITERALS if word in source]
    assert spelled == [], (
        f"factory/mergequeue/classify.py still spells {spelled}; FR-010 requires "
        "the conflict decision to be made from a forge-neutral fact"
    )


# --- US3-S3 / FR-010, trap 8: a pre-spec record replays identically -----------

#: A `PrSnapshot` as Temporal's JSON converter wrote one before this spec: the
#: eight fields it had, and not one more. A literal, since anything built from
#: today's class would grow the new field and prove nothing.
PRE_SPEC_SNAPSHOT = {
    "state": "OPEN",
    "is_draft": False,
    "auto_merge_requested": False,
    "merge_state_status": "DIRTY",
    "merged_at": None,
    "closed_at": None,
    "failing_required_checks": [],
    "observed_at": "2026-08-06T10:05:00Z",
}


def test_a_pre_spec_snapshot_deserializes_and_classifies_unchanged() -> None:
    """T024 / US3-S3: the most expensive class of bug this repository ships.

    `PrSnapshot` sits in live workflow histories, and a replay rebuilds it from
    JSON predating this story — through Temporal's own converter, which is why
    this uses that and not `dataclasses`. 032, 038 and 039 were each a workflow
    reaching a different decision on the same history, and a pre-spec conflict
    recorded in GitHub's spelling still has to reach `CONFLICT`. What edit would
    make it fail? Giving `in_conflict` no default (the converter raises on the
    missing key), or dropping the constructor's legacy reading — the outcome
    becomes "keep polling" and the node stalls.
    """
    converter = DataConverter.default.payload_converter
    payload = converter.to_payloads([PRE_SPEC_SNAPSHOT])[0]
    restored = converter.from_payloads([payload], [PrSnapshot])[0]

    # Loads unchanged: every field the record had is exactly what was stored.
    assert restored.state == "OPEN"
    assert restored.is_draft is False
    assert restored.auto_merge_requested is False
    assert restored.merge_state_status == "DIRTY"
    assert restored.merged_at is None
    assert restored.closed_at is None
    assert restored.failing_required_checks == ()
    assert restored.observed_at == "2026-08-06T10:05:00Z"

    # And classifies as it did.
    assert _outcome(restored) == QueueOutcome.CONFLICT

    # Stated structurally too, so a *second* field added later without a default
    # fails here even without a replay case of its own.
    fields = {f.name: f for f in dataclasses.fields(PrSnapshot)}
    # Anti-vacuity: the pre-spec set must really be the record's original shape.
    assert set(PRE_SPEC_SNAPSHOT) <= set(fields)
    added = [name for name in fields if name not in PRE_SPEC_SNAPSHOT]
    assert added, "this story adds a field to the poll record; none was found"
    for name in added:
        field = fields[name]
        assert (
            field.default is not dataclasses.MISSING
            or field.default_factory is not dataclasses.MISSING  # type: ignore[misc]
        ), f"PrSnapshot.{name} crosses the Temporal payload boundary with no default"


# --- US3-S4 / FR-011: the epic workflow did not change ------------------------

#: What `factory/workgraph/workflow.py` imports from the modules this story
#: touches, pinned at the commit it branched from — the half of FR-011 a test can
#: hold: had the seam reached into workflow code, a set here would have grown.
WORKFLOW_IMPORTS = {
    "factory.activities.merge_activities": {
        "CompareTreesInput", "DisableAutoMergeInput", "EnqueueLandingInput",
        "FetchCheckFailureInput", "OpenLandingPrInput", "PollLandingInput",
        "PrepareLandingPrInput", "SyncLandingBranchInput", "ValidateTargetRepoInput",
        "compare_trees", "disable_auto_merge", "enqueue_landing",
        "fetch_check_failure", "open_landing_pr", "poll_landing",
        "prepare_landing_pr", "sync_landing_branch", "validate_target_repo",
    },
    "factory.mergequeue.classify": {"classify"},
    "factory.mergequeue.models": {
        "CheckFailure", "Landing", "LandingConfig", "LandingState",
        "ObservedOutcome", "QueueOutcome", "RejectionCause", "TargetRepoProfile",
    },
    # 069-US1: `rejection_cause` is the second pure decision the workflow makes
    # over a poll — `classify` says what the queue answered, this says whose
    # fault it was. Pinned here for the same reason `classify` is: it is a pure
    # function the workflow calls, and a forge reached from that call site would
    # be a side effect inside a deterministic sandbox.
    "factory.mergequeue.rejection": {"rejection_cause"},
}

#: The seam's own modules; the workflow may not import any, since a forge
#: resolved there would be a side effect inside a deterministic sandbox.
SEAM_MODULES = {
    "factory.mergequeue.forge",
    "factory.mergequeue.gh",
    "factory.mergequeue.github_forge",
}


def test_the_epic_workflow_imports_and_calls_exactly_what_it_did() -> None:
    """T025 / US3-S4: the fence, pinned — the imports and the classifier's call
    shape. Every replay defect this repository has shipped came from a workflow
    edit. Equality against non-empty literals rather than a subset check, so a
    *removed* import fails too; `classify` is still called positionally with
    three records and one keyword clock, since a signature change would force the
    workflow edit FR-011 forbids. What edit would make it fail? Importing the
    forge there, renaming a landing activity, or changing that signature.
    """
    path = REPO_ROOT / "factory" / "workgraph" / "workflow.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.setdefault(node.module, set()).update(a.name for a in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                found.setdefault(alias.name, set())

    for module, expected in WORKFLOW_IMPORTS.items():
        assert expected, f"the pin for {module} is empty"
        assert found.get(module) == expected, (
            f"workflow.py's imports from {module} changed: "
            f"{sorted(found.get(module) or ())} != {sorted(expected)}"
        )

    reached = SEAM_MODULES & set(found)
    assert not reached, (
        f"the epic workflow imports {sorted(reached)}; the forge is resolved in "
        "activities, never in workflow code (FR-011)"
    )

    parameters = list(inspect.signature(classify).parameters.values())
    assert [p.name for p in parameters] == ["snapshot", "landing", "config", "now"]
    assert [p.kind for p in parameters[:3]] == [
        inspect.Parameter.POSITIONAL_OR_KEYWORD
    ] * 3
    assert parameters[3].kind is inspect.Parameter.KEYWORD_ONLY


# --- US3-S5 / FR-017, trap 6: the structural guards still hold ----------------


def test_the_three_structural_guards_still_hold_over_the_moved_code() -> None:
    """T026 / US3-S5: run the guards rather than assert they exist, having first
    proved they reached the moved code *by construction* —
    `tests/test_mergequeue_sweep.py` sweeps `factory/mergequeue/**`, so the forge
    is covered because of where FR-017 put it, not because this story widened a
    list; the set is imported from the sweep, so a narrowed sweep fails too. What
    edit would make it fail? Moving a forge module out of that directory, or
    spelling `--delete-branch`, a forced push, or a `pr merge` without
    `--auto`/`--disable-auto` in the merge surface.
    """
    assert COMMAND_MODULES, "the merge-surface sweep matched no module"
    swept = {path.relative_to(REPO_ROOT).as_posix() for path in COMMAND_MODULES}
    assert {
        "factory/mergequeue/forge.py",
        "factory/mergequeue/github_forge.py",
        "factory/mergequeue/classify.py",
        "factory/activities/merge_activities.py",
    } <= swept, sorted(swept)

    deletions: list[str] = []
    forced: list[str] = []
    direct: list[str] = []
    for path in COMMAND_MODULES:
        where = path.relative_to(REPO_ROOT).as_posix()
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "--delete-branch" in line:
                deletions.append(f"{where}:{lineno}")
            if "push" in line and "--force" in line:
                forced.append(f"{where}:{lineno}")
            if ('"merge"' in line or "'merge'" in line) and "pr" in line:
                if "--auto" not in line and "--disable-auto" not in line:
                    direct.append(f"{where}:{lineno}")

    assert deletions == [], f"a merge-surface path deletes a branch: {deletions}"
    assert forced == [], f"a merge-surface path forces a push: {forced}"
    assert direct == [], f"a merge-surface path merges directly: {direct}"
