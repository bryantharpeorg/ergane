"""049-US3: the landing path proposes, lands and observes through the forge.

Every test answers "what edit would make this fail?" in its own docstring, and
the mutation transcript proving each answer is committed at
`specs/049-forge-seam/evidence/us3-mutations.md`. The defect that has cost this
repository most is a test that could not fail; four were found in one sitting on
2026-08-15, so the answer is written down rather than assumed.

Scope fence, because two sibling stories were building against the same base
commit: this file is US3's alone. US2 owns `factory/mergequeue/onboard.py` and
US5 the manifest parser; nothing here reads either.

The properties defended, in the story's order:

- **S1** one landing's whole life runs through the seam — find, open, request
  landing, observe pending, observe merged, observe rejected, withdraw, fetch
  evidence — against a forge that models a repository rather than a script; and
  no landing activity names `gh` or constructs its client any more, while the
  landing suite that was written against `gh` passes with no assertion changed.
- **S2** `CONFLICT` is decided from a forge-neutral fact, provably not from
  GitHub's `DIRTY`: the control is a forge that never says the word.
- **S3** a `PrSnapshot` recorded before this spec deserializes through Temporal's
  own converter and classifies exactly as it did. This is the expensive one.
- **S4** `factory/workgraph/workflow.py` still imports and calls exactly what it
  did; the seam did not reach into workflow code.
- **S5** the merge-surface structural guards still cover the moved landing code,
  and cover it *by construction* rather than because a path was added to a list.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
from pathlib import Path

import pytest
from temporalio.converter import DataConverter

from factory.activities import merge_activities
from factory.mergequeue.classify import classify
from factory.mergequeue.forge import Forge, ForgeError, Proposal
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

#: The activities the story rewires. Named as a literal so a rename or a deletion
#: fails here rather than quietly shrinking what the source sweeps below check.
LANDING_ACTIVITIES = (
    "open_landing_pr",
    "enqueue_landing",
    "poll_landing",
    "disable_auto_merge",
    "fetch_check_failure",
)


def _landing(**overrides: object) -> Landing:
    fields: dict[str, object] = dict(
        node_id="us3",
        branch="factory/049-forge-seam/us3",
        pr_number=7,
        enqueued_at="2026-08-16T10:00:00Z",
        state=LandingState.ENQUEUED,
    )
    fields.update(overrides)
    return Landing(**fields)  # type: ignore[arg-type]


def _open_one(model: RepositoryModel) -> tuple[FakeForge, Proposal]:
    """A forge with one open proposal whose landing has been requested."""
    forge = FakeForge(model)
    proposal = forge.open_proposal(
        base="main",
        head="factory/049-forge-seam/us3",
        title="049-forge-seam/us3: US3",
        body_file="/tmp/body.md",
    )
    forge.request_landing(proposal.number)
    return forge, proposal


# --- US3-S1 / FR-009: one landing's whole life, through the seam --------------


def test_a_landing_runs_its_whole_life_through_the_forge() -> None:
    """T021, the story's Independent Test: find, open, request landing, observe
    merged, observe rejected, withdraw — all of it against a forge that models a
    repository, and the record each observation yields is the one `classify`
    already consumes.

    What edit would make this fail? Any of the six operations returning something
    the classifier cannot read: an `observe_proposal` that dropped `merged_at`,
    an `open_proposal` that did not record the head, a `find_proposal` that
    answered before anything was opened. The assertions are on the *judgment of
    the model* — what `classify` says — never on which calls were made, which is
    what stops this from being the call-recorder defect
    (`ci/the-scripted-gh-fake-never-consumes-an-expectation`) in a new shape.
    """
    model = RepositoryModel(address="acme/app", default_branch="main")
    forge = FakeForge(model)
    head = "factory/049-forge-seam/us3"

    # Nothing is open yet: the idempotent open must look before it offers.
    assert forge.find_proposal(head) is None

    opened = forge.open_proposal(
        base="main", head=head, title="049-forge-seam/us3: US3",
        body_file="/tmp/body.md",
    )
    assert isinstance(opened, Proposal)
    # Offering again finds what is already there — one landing per head.
    assert forge.find_proposal(head) == opened

    forge.request_landing(opened.number)

    # Observed while the forge still holds it: keep polling.
    pending = forge.observe_proposal(opened.number)
    assert classify(pending, _landing(), LandingConfig(), now=NOW) is None

    # The forge lands it.
    model.landings.land(opened.number, at="2026-08-16T10:04:00Z")
    landed = forge.observe_proposal(opened.number)
    assert classify(landed, _landing(), LandingConfig(), now=NOW) == QueueOutcome.MERGED

    # A second life: the same repository rejects a proposal on failing checks,
    # and the evidence for that rejection comes back through the same seam.
    rejected_number = forge.open_proposal(
        base="main", head="factory/049-forge-seam/us9", title="t", body_file="/tmp/b.md",
    ).number
    forge.request_landing(rejected_number)
    model.landings.fail_checks(rejected_number, ("test",), log="FAILED test_add\n")

    observed = forge.observe_proposal(rejected_number)
    assert classify(observed, _landing(), LandingConfig(), now=NOW) == (
        QueueOutcome.CHECKS_FAILED
    )
    assert observed.failing_required_checks == ("test",)

    assert forge.failing_check_evidence(rejected_number, ("test",)) == (
        CheckFailure(
            name="test",
            url="https://forge.invalid/acme/app/proposals/2/checks/test",
            log_tail="FAILED test_add\n",
            note="",
        ),
    )

    # Withdrawing leaves the proposal open and un-landed — the kill path.
    forge.withdraw_landing(rejected_number)
    withdrawn = forge.observe_proposal(rejected_number)
    assert withdrawn.state == "OPEN"
    assert withdrawn.merged_at is None
    assert model.landings.proposals[rejected_number].landing_requested is False


def test_a_forge_that_refuses_a_landing_request_says_so_as_a_forge_error() -> None:
    """A refused landing is data the activity returns, never a crash (FR-009).

    What edit would make this fail? Having `request_landing` swallow the refusal
    and return normally — the shape that would let a killed queue read as a
    successful enqueue and strand the node waiting on a landing nobody asked for.
    """
    model = RepositoryModel()
    forge, proposal = _open_one(model)
    model.landings.refuse_landing = "landing is turned off for this repository"

    with pytest.raises(ForgeError) as excinfo:
        forge.request_landing(proposal.number)

    assert "turned off" in excinfo.value.detail


def test_evidence_gathering_degrades_rather_than_raising() -> None:
    """A forge that cannot produce a log states the absence in the record (FR-009).

    What edit would make this fail? Raising instead of degrading — the recovery
    cycle would then be lost to its own evidence-gathering, which is the failure
    the note field exists to prevent.
    """
    model = RepositoryModel()
    forge, proposal = _open_one(model)
    model.landings.fail_checks(proposal.number, ("test",), log="")

    evidence = forge.failing_check_evidence(proposal.number, ("test", "absent"))

    assert [e.name for e in evidence] == ["test", "absent"]
    assert evidence[0].log_tail == ""
    assert evidence[0].note != ""
    assert evidence[1].url == ""
    assert evidence[1].note != ""


def test_the_landing_activities_name_no_forge_native_client() -> None:
    """T022 / US3-S1: no landing activity constructs a client or names `gh`.

    Read off the *code* of the five activities and of the module's imports, so a
    command a test never happens to call still cannot be one the code can issue.
    Docstrings are excluded deliberately — prose that explains what GitHub does
    is not a coupling — and `onboard_target_repo`'s SC-001 wording is out of
    scope by name: US2 owns that prose, and neutralising it here would collide
    with a story running beside this one.

    What edit would make this fail? Putting `GhClient(` or `client.enqueue_pr(`
    back into any one of the five, or re-importing `factory.mergequeue.gh`.
    """
    source = Path(inspect.getfile(merge_activities)).read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Nothing in the module imports the forge-native client module any more.
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "factory.mergequeue.gh" not in imported, imported

    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    # Anti-vacuity: a renamed activity must fail here rather than drop out of the
    # sweep and leave it scanning nothing.
    missing = [name for name in LANDING_ACTIVITIES if name not in functions]
    assert not missing, f"the sweep found no activity named {missing}"

    offenders: list[str] = []
    for name in LANDING_ACTIVITIES:
        body = functions[name]
        for node in ast.walk(body):
            spelled = ""
            if isinstance(node, ast.Name):
                spelled = node.id
            elif isinstance(node, ast.Attribute):
                spelled = node.attr
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                # A docstring is the first statement of the function; skip it.
                if node is getattr(body.body[0], "value", None):
                    continue
                spelled = node.value
            if not spelled:
                continue
            words = set(spelled.lower().replace("-", "_").split("_"))
            if words & {"gh", "github"} or spelled.startswith("Gh"):
                offenders.append(f"{name}: {spelled!r}")

    assert offenders == [], (
        "these landing activities still name a forge-native client: " + str(offenders)
    )


#: Every landing test in `tests/test_merge_activities.py` — the suite that was
#: written against `gh` and must survive the move untouched. A literal, so a
#: deletion fails here instead of shrinking the digest's coverage in silence.
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

#: sha256 over those tests' `assert` statements, source-normalised, in file
#: order. Pinned at the commit this story branched from.
LANDING_SUITE_ASSERTION_DIGEST = (
    "3a0e47887df157d78bab4ecc5666b934c8eadc39b5f1e2304ba507ae9502be67"
)

#: How many assertions that digest covers. Pinned separately so a sweep that
#: collected none — the vacuous shape — cannot match by hashing the empty string.
LANDING_SUITE_ASSERTION_COUNT = 33


def _landing_suite_assertions() -> list[str]:
    path = REPO_ROOT / "tests" / "test_merge_activities.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in LANDING_SUITE_TESTS:
            continue
        for statement in ast.walk(node):
            if isinstance(statement, ast.Assert):
                segment = ast.get_source_segment(source, statement) or ""
                found.append(" ".join(segment.split()))
    return found


def test_the_existing_landing_suite_passes_with_no_assertion_changed() -> None:
    """T022 / US3-S1's second half, made mechanical.

    "The landing suite passes unmodified" is not provable by running it — a
    modified suite passes too. So this pins what those eleven tests *assert*: the
    source text of every `assert` statement in them, normalised for whitespace
    and hashed. The move behind the seam had to keep every one of them true, and
    a later story that relaxes one to make its own change fit must edit this
    pin deliberately rather than quietly.

    What edit would make this fail? Changing, adding or deleting any assertion in
    any of the eleven — verified by mutation M2.
    """
    collected = _landing_suite_assertions()

    # Anti-vacuity: hashing an empty list would pass forever once pinned.
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


def test_a_forge_reporting_a_conflict_yields_conflict_from_a_neutral_fact() -> None:
    """T023 / US3-S2: the target moved under the proposal, and the factory hears
    about it in its own vocabulary.

    The control is the point: this forge's `merge_state_status` is the empty
    string — it has never heard of GitHub's `DIRTY` — and `CONFLICT` still comes
    out. A classifier that had merely been renamed would answer `None` here.

    What edit would make this fail? Reverting `classify` to read
    `merge_state_status`, or having the model's `target_moved` set the old string
    instead of the neutral fact.
    """
    model = RepositoryModel()
    forge, proposal = _open_one(model)
    model.landings.target_moved(proposal.number)

    observed = forge.observe_proposal(proposal.number)

    assert observed.in_conflict is True
    assert observed.merge_state_status == ""
    assert classify(observed, _landing(), LandingConfig(), now=NOW) == (
        QueueOutcome.CONFLICT
    )


#: GitHub's `mergeStateStatus` vocabulary and the fields that carry it. None may
#: appear in the classifier's source: the whole of FR-010 is that the decision
#: stopped being made from one forge's spelling.
#:
#: `state == "CLOSED"` is deliberately absent from this list. FR-010 asks for one
#: neutral fact, the conflict one, and plan trap 12 is explicit that the symmetry
#: of making every observation a decisive neutral fact is to be resisted — the
#: heuristic that killed 009-us1's landing four seconds before it merged was
#: exactly that kind of extra decisive signal.
FORGE_NATIVE_STATUS_LITERALS = (
    "DIRTY",
    "BLOCKED",
    "BEHIND",
    "UNSTABLE",
    "HAS_HOOKS",
    "mergeStateStatus",
    "merge_state_status",
    "autoMergeRequest",
)


def test_the_classifier_source_names_no_forge_native_status_literal() -> None:
    """T023 / US3-S2's second half: read off `classify.py`'s own text.

    Its docstrings are swept too, on purpose — a table row still documenting
    `merge_state_status == DIRTY` would be a lie the next reader acts on, and the
    cheapest way to keep prose honest is to hold it to the same rule as the code.

    What edit would make this fail? Restoring the `DIRTY` comparison, or the
    docstring row that described it.
    """
    path = REPO_ROOT / "factory" / "mergequeue" / "classify.py"
    source = path.read_text(encoding="utf-8")

    # Anti-vacuity: a sweep that read nothing, or read the wrong file, passes
    # forever. This names something the classifier must still contain.
    assert "QueueOutcome.CONFLICT" in source, "read the wrong file, or an empty one"

    spelled = [word for word in FORGE_NATIVE_STATUS_LITERALS if word in source]
    assert spelled == [], (
        f"factory/mergequeue/classify.py still spells {spelled}; FR-010 requires "
        "the conflict decision to be made from a forge-neutral fact"
    )


# --- US3-S3 / FR-010, trap 8: a pre-spec record replays identically -----------

#: A `PrSnapshot` exactly as Temporal's JSON converter wrote one before this
#: spec: the eight fields the record had, and not one more. Kept as a literal
#: rather than built from the class, because a record built from today's class
#: would grow the new field and prove nothing.
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


def _replay(stored: dict[str, object]) -> PrSnapshot:
    """Deserialize `stored` the way a replaying workflow would — through
    Temporal's own default converter, not through `dataclasses`."""
    converter = DataConverter.default.payload_converter
    payload = converter.to_payloads([stored])[0]
    return converter.from_payloads([payload], [PrSnapshot])[0]


def test_a_pre_spec_snapshot_deserializes_and_classifies_unchanged() -> None:
    """T024 / US3-S3: the most expensive class of bug this repository ships.

    `PrSnapshot` sits in live workflow histories. A replay rebuilds it from JSON
    that predates this story, so every field US3 adds must carry a default *and*
    the outcome must not move: 032, 038 and 039 were all a workflow reaching a
    different decision on the same history.

    A pre-spec conflict was recorded in GitHub's spelling, because that is the
    only spelling that existed. It still has to reach `CONFLICT` — which is why
    the legacy reading lives in the record's own constructor, once, and never in
    the classifier.

    What edit would make this fail? Giving `in_conflict` no default (the
    converter raises on the missing key), or dropping the constructor's legacy
    reading (the outcome silently becomes "keep polling" and the node waits out
    its stall window instead of recovering).
    """
    restored = _replay(PRE_SPEC_SNAPSHOT)

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
    assert classify(restored, _landing(), LandingConfig(), now=NOW) == (
        QueueOutcome.CONFLICT
    )


def test_every_field_this_story_added_to_the_poll_record_carries_a_default() -> None:
    """T024's structural half: stated as a property of the class, not of one
    stored payload, so a *second* field added later without a default fails here
    even if nobody writes a replay case for it.

    What edit would make this fail? Adding any field to `PrSnapshot` after
    `observed_at` without a default.
    """
    import dataclasses

    fields = {f.name: f for f in dataclasses.fields(PrSnapshot)}
    pre_spec = set(PRE_SPEC_SNAPSHOT)

    # Anti-vacuity: the pre-spec set must really be the record's original shape.
    assert pre_spec <= set(fields), pre_spec - set(fields)

    added = [name for name in fields if name not in pre_spec]
    assert added, "this story adds a field to the poll record; none was found"
    for name in added:
        field = fields[name]
        assert (
            field.default is not dataclasses.MISSING
            or field.default_factory is not dataclasses.MISSING  # type: ignore[misc]
        ), f"PrSnapshot.{name} crosses the Temporal payload boundary with no default"


# --- US3-S4 / FR-011: the epic workflow did not change ------------------------

#: What `factory/workgraph/workflow.py` imports from the modules this story
#: touches, pinned at the commit it branched from. FR-011 says the file must not
#: change; this is the half of that a test can hold — if the seam had needed to
#: reach into workflow code, one of these sets would have grown.
WORKFLOW_IMPORTS = {
    "factory.activities.merge_activities": {
        "CompareTreesInput",
        "DisableAutoMergeInput",
        "EnqueueLandingInput",
        "FetchCheckFailureInput",
        "OpenLandingPrInput",
        "PollLandingInput",
        "PrepareLandingPrInput",
        "SyncLandingBranchInput",
        "ValidateTargetRepoInput",
        "compare_trees",
        "disable_auto_merge",
        "enqueue_landing",
        "fetch_check_failure",
        "open_landing_pr",
        "poll_landing",
        "prepare_landing_pr",
        "sync_landing_branch",
        "validate_target_repo",
    },
    "factory.mergequeue.classify": {"classify"},
    "factory.mergequeue.models": {
        "CheckFailure",
        "Landing",
        "LandingConfig",
        "LandingState",
        "ObservedOutcome",
        "QueueOutcome",
        "TargetRepoProfile",
    },
}

#: The seam's own modules. The workflow may not import any of them: a forge
#: resolved in workflow code would be a side effect in a deterministic sandbox,
#: and the reason FR-011 is a requirement rather than a preference.
SEAM_MODULES = {
    "factory.mergequeue.forge",
    "factory.mergequeue.gh",
    "factory.mergequeue.github_forge",
}


def _workflow_imports() -> dict[str, set[str]]:
    path = REPO_ROOT / "factory" / "workgraph" / "workflow.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.setdefault(node.module, set()).update(
                alias.name for alias in node.names
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                found.setdefault(alias.name, set())
    return found


def test_the_epic_workflow_imports_exactly_what_it_imported_before() -> None:
    """T025 / US3-S4: the fence, pinned.

    Every replay defect this repository has shipped came from a workflow edit, so
    the story that moves the landing surface is the one that must prove it did
    not touch the workflow. Equality against non-empty literals rather than a
    subset check, so a *removed* import fails here too.

    What edit would make this fail? Importing the forge into workflow code, or
    adding, removing or renaming any landing activity the workflow calls.
    """
    found = _workflow_imports()

    for module, expected in WORKFLOW_IMPORTS.items():
        assert expected, f"the pin for {module} is empty"
        assert found.get(module) == expected, (
            f"factory/workgraph/workflow.py's imports from {module} changed: "
            f"{sorted(found.get(module) or ())} != {sorted(expected)}"
        )

    reached = SEAM_MODULES & set(found)
    assert not reached, (
        f"the epic workflow imports {sorted(reached)}; the forge is resolved in "
        "activities, never in workflow code (FR-011)"
    )


def test_the_classifier_signature_the_workflow_calls_is_unchanged() -> None:
    """T025's second half: the workflow's *call* into the classifier, not just
    its import. `classify` is called positionally with three records and one
    keyword clock; a signature change would force a workflow edit, which is the
    thing FR-011 forbids.

    What edit would make this fail? Adding a parameter to `classify`, reordering
    its three positional records, or making `now` positional.
    """
    signature = inspect.signature(classify)
    parameters = list(signature.parameters.values())

    assert [p.name for p in parameters] == ["snapshot", "landing", "config", "now"]
    assert [p.kind for p in parameters[:3]] == [
        inspect.Parameter.POSITIONAL_OR_KEYWORD
    ] * 3
    assert parameters[3].kind is inspect.Parameter.KEYWORD_ONLY


# --- US3-S5 / FR-017, traps 6 and 11: the structural guards still hold --------


def test_the_merge_surface_guards_already_cover_the_landing_seam() -> None:
    """T026 / US3-S5: covered by construction, not by remembering.

    `tests/test_mergequeue_sweep.py` sweeps `factory/mergequeue/**` plus two named
    files. The forge modules are inside that directory, so the three guards
    reached them without this story adding a path to the swept set — which is the
    assertion that tells "covered by construction" apart from "covered because
    somebody widened a list". The set is imported from the sweep itself rather
    than recomputed, so a narrowed sweep fails here.

    What edit would make this fail? Moving any forge module out of
    `factory/mergequeue/`, which is exactly the change FR-017 forbids.
    """
    swept = {path.relative_to(REPO_ROOT).as_posix() for path in COMMAND_MODULES}

    assert {
        "factory/mergequeue/forge.py",
        "factory/mergequeue/github_forge.py",
        "factory/mergequeue/classify.py",
        "factory/activities/merge_activities.py",
    } <= swept, sorted(swept)


def test_the_three_structural_guards_still_hold_over_the_moved_code() -> None:
    """T026 / US3-S5: run them, rather than assert they exist.

    No path requests branch deletion, no push is forced, and the only merge form
    in source is the automatic one. These were earned by incidents — a merged
    branch deleted out from under the queue, a history rewrite mid-decision — and
    a story that moves the landing commands is the story most able to break one.

    What edit would make this fail? Spelling `--delete-branch`, a forced push, or
    a `pr merge` without `--auto`/`--disable-auto` anywhere in the merge surface
    — verified by mutation M6.
    """
    assert COMMAND_MODULES, "the merge-surface sweep matched no module"

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


def test_the_landing_seam_carries_the_no_strategy_flag_behaviour_across() -> None:
    """Plan trap 11: `request_landing` sends no merge-strategy flag, and that is
    deliberate — a branch governed by a landing policy owns its own method, and
    `gh` refuses the flag outright (proved live 2026-08-07). The operator's
    declared intent still crosses the seam, so a forge that *can* honour it may;
    GitHub's implementation carries it and does not send it.

    What edit would make this fail? "Restoring" the flag while moving the call
    behind the seam — the argv equality in the landing suite would catch it too,
    but only for the one command a test happens to issue.
    """
    signature = inspect.signature(Forge.request_landing)

    assert list(signature.parameters) == ["self", "proposal", "declared_method"]
    assert signature.parameters["declared_method"].default == ""
    assert (
        signature.parameters["declared_method"].kind
        is inspect.Parameter.KEYWORD_ONLY
    )
