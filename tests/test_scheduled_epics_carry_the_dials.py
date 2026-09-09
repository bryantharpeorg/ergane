"""081-US2: the epics a roadmap dispatches run the dials its operator set.

US1 made the landing dials settable on `ergane build start`, which is the epic
an operator starts by hand. The roadmap is the other half, and it is the half
the spec was written for: the 2026-08-19 request that produced it was "lower
`stall_after_s` before I leave this running overnight", and overnight is the
roadmap's case, not the hand-start's.

`factory/roadmap/workflow.py` has always forwarded `request.landing_config` to
every child `EpicInput` faithfully. What it forwarded was
`factory/cli/roadmap.py`'s bare `LandingConfig()` — so the roadmap dispatched
the defaults no matter what the operator wanted, and the one site that looked
wired was the one that could not be. These tests drive the whole chain, from the
flag the operator types to the `EpicInput` the child epic is started with,
because the two halves in between were each individually convincing.

FR-007, US2-S3 — WHAT A DIAL CHANGE DOES TO A RUNNING EPIC, STATED PLAINLY:

    **A dial change reaches the next dispatch. It never reaches an epic that is
    already running, and it never reaches a roadmap run that is already
    running.**

    A child epic's `EpicInput` is built once, inside `_dispatch`, from the
    roadmap run's own input, and handed across the child-workflow boundary as a
    frozen payload. Nothing reads it again. A roadmap run's landing config comes
    from the `RoadmapInput` it was started with and is carried verbatim across
    every continue-as-new boundary; no signal on `RoadmapWorkflow` changes it,
    by design (044's signals are pause, resume, rescan, promote and unpark, and
    that is the whole set).

    So the operator's move is: start a new roadmap with the new dials. The epics
    already in flight keep the dials they were dispatched with, and that is not
    a defect to work around — it is the same rule as every other field of
    `RoadmapInput`, and an operator who expects otherwise concludes the dial
    does not work when it does.

Four tests below prove each clause: the value reaches the child (US2-S1), an
unset dial is still today's number (US2-S2, the control), a change reaches the
next dispatch and not the epic held open beside it (US2-S3), and the value the
run started with is what every later dispatch of that run gets, across the
continue-as-new boundary included.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterator

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from factory.mergequeue.models import LandingConfig
from factory.roadmap.models import SpecState
from factory.roadmap.workflow import (
    RoadmapWorkflow,
    roadmap_workflow_id,
)
from factory.workgraph.workflow import EpicInput, TASK_QUEUE

from tests.roadmap_script import ScriptedEpicWorkflow, _SCRIPT
from tests.test_ergane_roadmap import (
    TARGET_REPO,
    Run,
    _run_in_thread,
    env,  # noqa: F401  — pytest fixture, re-exported for this module
    invoke,  # noqa: F401  — pytest fixture, re-exported for this module
)
from tests.test_roadmap_scheduler import (
    HARNESS_REVISION,
    RoadmapWorld,
    _BootRevisionInterceptor,
    _RecordingInterceptor,
    build_corpus,
)


# --- the harness --------------------------------------------------------------


def _worker(
    env: WorkflowEnvironment,
    world: RoadmapWorld,
    records: list[ChildStartRecord],
) -> Worker:
    """The real `RoadmapWorkflow` with scripted seams and a recorded child start.

    `tests/test_ergane_roadmap.py` has this worker without the interceptor and
    `tests/test_roadmap_scheduler.py` has the interceptor without the CLI. This
    story needs both at once: the flag has to be typed at the command, and the
    `EpicInput` the child is actually started with has to be read off the wire —
    asserting anything in between is how a dial that parses and is dropped one
    frame later passes its own test.
    """
    from factory.activities.notify_activities import (
        record_roadmap_failure,
        reset_roadmap_failures,
        send_escalation,
        send_roadmap_notice,
    )
    from factory.activities.roadmap_activities import (
        clone_target,
        count_open_epics,
        derive_spec,
        drift_for_spec,
        onboard_target,
        preflight_spec,
        read_loop_config,
        tree_revision_activity,
    )
    from factory.roadmap.workflow import read_corpus_activity, read_spec_text_activity

    return Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[RoadmapWorkflow, ScriptedEpicWorkflow],
        activities=[
            clone_target,
            derive_spec,
            drift_for_spec,
            preflight_spec,
            onboard_target,
            count_open_epics,
            read_corpus_activity,
            read_loop_config,
            read_spec_text_activity,
            # 156-US2: the tree-revision read, served so the skew check's
            # activity call lands (the shared world's seam answers aligned).
            tree_revision_activity,
            record_roadmap_failure,
            reset_roadmap_failures,
            send_roadmap_notice,
            send_escalation,
        ],
        # 156-US2: the boot stamp rides ahead of the recorder, so the skew
        # check reads the aligned harness revision and dispatches as before.
        interceptors=[_BootRevisionInterceptor(HARNESS_REVISION), _RecordingInterceptor(records)],
        workflow_runner=UnsandboxedWorkflowRunner(),
    )


@pytest.fixture
def world() -> Iterator[RoadmapWorld]:
    """A scripted world whose seams are restored, and a clean epic script."""
    _SCRIPT.statuses = {}
    _SCRIPT.hold = set()
    _SCRIPT.on_dispatch = None
    _SCRIPT.on_complete = None
    scripted = RoadmapWorld()
    scripted.apply()
    try:
        yield scripted
    finally:
        scripted.restore()
        _SCRIPT.statuses = {}
        _SCRIPT.hold = set()
        _SCRIPT.on_dispatch = None
        _SCRIPT.on_complete = None


def _corpus(root: Path, name: str, specs: dict[str, dict[str, Any]]) -> Path:
    """A specs corpus whose *directory name* is `name`.

    `roadmap_workflow_id` is `roadmap-<basename of the specs root>`, and
    `build_corpus` always writes into `<root>/specs`, so two corpora built the
    plain way share one roadmap id and the second start is refused as a
    duplicate. The dial-change case needs two roadmaps alive at once, so the
    root is renamed to something that identifies it.
    """
    built = build_corpus(root, specs)
    renamed = built.parent / name
    built.rename(renamed)
    return renamed


async def _await_dispatches(records: list[ChildStartRecord], count: int) -> None:
    """Wait until `count` child epics have been started, or fail saying how many.

    Dispatch runs through real activities (clone, derive, preflight, onboard,
    manifest), so this is ordinary polling rather than a Temporal timer — the
    time-skipping clock is not involved and cannot skip past it.
    """
    async def reached() -> None:
        while len(records) < count:
            await asyncio.sleep(0.02)

    try:
        await asyncio.wait_for(reached(), timeout=30)
    except asyncio.TimeoutError:  # pragma: no cover - a failure path
        raise AssertionError(
            f"expected {count} child epic starts, saw {len(records)}: {records}"
        ) from None


def _child_input(record: ChildStartRecord) -> EpicInput:
    """The `EpicInput` one recorded child start carried."""
    assert record.args, record
    return record.args[0]


def _start(
    invoke: Callable[..., Run], specs_root: Path, *dials: str
) -> Awaitable[Run]:
    """`ergane roadmap start <root> --target-repo … <dials>` as an awaitable call."""
    return _run_in_thread(
        invoke,
        "roadmap",
        "start",
        str(specs_root),
        "--target-repo",
        TARGET_REPO,
        *dials,
    )


# --- T016 / US2-S1 (FR-006): the dial reaches the child -----------------------


#: Every dial, all five, set to something no default could be mistaken for.
#: Named once so the assertion below and the control that follows it cannot
#: drift into agreeing by accident.
OPERATOR_DIALS = LandingConfig(
    merge_method="rebase",
    poll_interval_s=15,
    stall_after_s=900,
    max_recovery_cycles=3,
    max_free_rebases=7,
)


async def test_a_dial_set_on_the_roadmap_reaches_the_child_epic(
    env: WorkflowEnvironment,
    tmp_path: Path,
    invoke: Callable[..., Run],
    world: RoadmapWorld,
) -> None:
    """US2-S1, FR-006: what the operator typed is what the child epic runs.

    Driven end to end — the flags go in at `ergane roadmap start` and the
    assertion is on the `EpicInput` the roadmap handed `start_child_workflow`.
    Nothing in between is asserted, because everything in between was already
    convincing while the dispatched dials were the defaults.
    """
    specs_root = _corpus(tmp_path, "alpha", {"001-alpha": dict(state=SpecState.READY)})
    records: list[ChildStartRecord] = []

    async with _worker(env, world, records):
        result = await _start(
            invoke,
            specs_root,
            "--merge-method",
            "rebase",
            "--landing-poll-interval-s",
            "15",
            "--stall-after-s",
            "900",
            "--max-recovery-cycles",
            "3",
            "--max-free-rebases",
            "7",
        )
        assert result.code == 0, result
        await _await_dispatches(records, 1)
        await env.client.get_workflow_handle(
            roadmap_workflow_id(str(specs_root))
        ).result()

    landing = _child_input(records[0]).landing_config
    assert landing == OPERATOR_DIALS, landing


# --- T017 / US2-S2 (FR-006): the control --------------------------------------


async def test_a_roadmap_that_sets_nothing_dispatches_todays_defaults(
    env: WorkflowEnvironment,
    tmp_path: Path,
    invoke: Callable[..., Run],
    world: RoadmapWorld,
) -> None:
    """US2-S2, FR-002, plan trap 1: **the control.**

    An operator who sets no dial gets the epic they got yesterday. The four
    values the spec pins are named as literals rather than compared against
    `LandingConfig()`, deliberately: a comparison against the dataclass moves
    with any diff that changes a default and would pass while every unattended
    roadmap on this release quietly started behaving differently.
    """
    specs_root = _corpus(tmp_path, "bravo", {"001-bravo": dict(state=SpecState.READY)})
    records: list[ChildStartRecord] = []

    async with _worker(env, world, records):
        result = await _start(invoke, specs_root)
        assert result.code == 0, result
        await _await_dispatches(records, 1)
        await env.client.get_workflow_handle(
            roadmap_workflow_id(str(specs_root))
        ).result()

    landing = _child_input(records[0]).landing_config
    assert landing.merge_method == "squash", landing
    assert landing.poll_interval_s == 60, landing
    assert landing.stall_after_s == 7200, landing
    assert landing.max_recovery_cycles == 1, landing
    # 069's bound, set after the spec was written and pinned here for the same
    # reason as the other four: nothing about this story may move it.
    assert landing.max_free_rebases == 3, landing


# --- T018 / US2-S3 (FR-007): what a change reaches ----------------------------


async def test_a_dial_change_reaches_the_next_dispatch_never_the_running_epic(
    env: WorkflowEnvironment,
    tmp_path: Path,
    invoke: Callable[..., Run],
    world: RoadmapWorld,
) -> None:
    """US2-S3, FR-007: the answer, proven rather than asserted in prose.

    One epic is genuinely in flight — the scripted child for `001-held` blocks
    until this test releases it — dispatched by a roadmap started with
    `--stall-after-s 900`. With it still open, the operator changes the dial the
    only way a dial can be changed: they start a roadmap with the new value.

    Both halves are then true at once, which is the whole of FR-007's answer:
    the epic dispatched before the change still carries 900, and the epic
    dispatched after it carries 1800. A change reaches the next dispatch and
    nothing that is already running.
    """
    held_root = _corpus(tmp_path, "held", {"001-held": dict(state=SpecState.READY)})
    next_root = _corpus(tmp_path, "next", {"002-next": dict(state=SpecState.READY)})
    _SCRIPT.hold = {"001-held"}
    records: list[ChildStartRecord] = []

    async with _worker(env, world, records):
        first = await _start(invoke, held_root, "--stall-after-s", "900")
        assert first.code == 0, first
        await _await_dispatches(records, 1)

        # The dial change, with the first epic still open.
        second = await _start(invoke, next_root, "--stall-after-s", "1800")
        assert second.code == 0, second
        await _await_dispatches(records, 2)

        running = _child_input(records[0])
        dispatched_after = _child_input(records[1])
        assert running.landing_config.stall_after_s == 900, running
        assert dispatched_after.landing_config.stall_after_s == 1800, dispatched_after

        # Let the held epic finish so both roadmaps drain rather than leaking a
        # blocked workflow into the next test's environment.
        _SCRIPT.release("001-held")
        await env.client.get_workflow_handle("epic-001-held").signal("release")
        await env.client.get_workflow_handle(
            roadmap_workflow_id(str(held_root))
        ).result()
        await env.client.get_workflow_handle(
            roadmap_workflow_id(str(next_root))
        ).result()

    # And it stayed changed for nobody: the record of the running epic's input is
    # the payload it was started with, and no later dispatch rewrote it.
    assert _child_input(records[0]).landing_config.stall_after_s == 900


async def test_every_dispatch_of_one_run_gets_the_dial_that_run_started_with(
    env: WorkflowEnvironment,
    tmp_path: Path,
    invoke: Callable[..., Run],
    world: RoadmapWorld,
) -> None:
    """FR-007's other clause: the value is compiled at start, for the whole run.

    Two dispatchable specs at one epic of capacity: the first child lands, the
    roadmap reaches quiescence and continues-as-new, and the second child is
    dispatched by the *new* run. Both carry the operator's value, which is what
    makes "start a new roadmap" the whole of the change procedure — a dial does
    not decay across the durability boundary, and equally does not pick up a new
    value there.
    """
    specs_root = _corpus(
        tmp_path,
        "charlie",
        {
            "001-charlie": dict(state=SpecState.READY),
            "002-delta": dict(state=SpecState.READY),
        },
    )
    records: list[ChildStartRecord] = []

    async with _worker(env, world, records):
        result = await _start(invoke, specs_root, "--max-recovery-cycles", "4")
        assert result.code == 0, result
        await _await_dispatches(records, 2)
        await env.client.get_workflow_handle(
            roadmap_workflow_id(str(specs_root))
        ).result()

    assert len(records) == 2, records
    for record in records:
        assert _child_input(record).landing_config.max_recovery_cycles == 4, record


def test_no_roadmap_signal_changes_the_dials_of_a_running_roadmap() -> None:
    """FR-007: there is no mid-run change, and that is a fact about the tree.

    The test above proves what a change reaches. This one proves the sentence
    before it — that the only way to change a dial is to start a new roadmap —
    by reading every `@workflow.signal` the roadmap declares. A signal added
    later that reconfigures landing makes this fail, which is correct: FR-007's
    stated answer would no longer be the true one, and the statement in
    `factory/cli/roadmap.py` would have to change with it.
    """
    source = Path(__file__).resolve().parents[1] / "factory" / "roadmap" / "workflow.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    workflow_class = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "RoadmapWorkflow"
    )
    signals = {
        member.name
        for member in workflow_class.body
        if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
        for decorator in member.decorator_list
        if isinstance(decorator, ast.Attribute) and decorator.attr == "signal"
    }
    assert signals == {
        "pause_roadmap",
        "resume_roadmap",
        "rescan",
        "promote_spec",
        "unpark_spec",
    }, signals


# --- T019 / US2-S4 (FR-006): no site builds the dials bare --------------------


def _roadmap_input_calls(root: Path) -> dict[str, list[ast.Call]]:
    """Every `RoadmapInput(...)` construction under `factory/`, by file.

    Discovered rather than listed for the reason US1 gives for the `EpicInput`
    sites: the failure US2-S4 names is a site that drops the operator's value,
    and a fourth one added next month is exactly as silent as the one this story
    fixes.
    """
    found: dict[str, list[ast.Call]] = {}
    for path in sorted((root / "factory").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "RoadmapInput"
        ]
        if calls:
            found[str(path.relative_to(root))] = calls
    return found


def test_no_roadmap_input_site_default_constructs_a_landing_config() -> None:
    """US2-S4: `factory/cli/roadmap.py` no longer builds `LandingConfig()` bare.

    A bare construction here is not a missing feature, it is a *disproof* of the
    one downstream site that always looked right:
    `factory/roadmap/workflow.py`'s `landing_config=request.landing_config` has
    forwarded faithfully since 044, and forwarded the defaults every time,
    because this is where the value it forwards was made.
    """
    root = Path(__file__).resolve().parents[1]
    calls = _roadmap_input_calls(root)

    assert "factory/cli/roadmap.py" in calls, (
        f"the roadmap's start site moved or vanished; found {sorted(calls)}"
    )

    for location, site_calls in calls.items():
        for call in site_calls:
            keywords = {kw.arg: kw.value for kw in call.keywords}
            assert "landing_config" in keywords, (
                f"{location}:{call.lineno} constructs RoadmapInput without "
                "landing_config; every child epic it dispatches loses the dials"
            )
            value = keywords["landing_config"]
            assert not (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id == "LandingConfig"
                and not value.args
                and not value.keywords
            ), (
                f"{location}:{call.lineno} passes a bare LandingConfig(); the "
                "operator's dials are discarded here as surely as by omitting it"
            )


# --- FR-004 on this verb: the refusal is the shared one -----------------------


@pytest.mark.parametrize(
    "flag, value, complaint",
    [
        ("--stall-after-s", "0", "stall-after-s must be an integer >= 1"),
        (
            "--landing-poll-interval-s",
            "-1",
            "landing-poll-interval-s must be an integer >= 1",
        ),
        ("--merge-method", "cherry-pick", "merge-method must be one of"),
    ],
)
def test_an_impossible_dial_is_refused_at_the_roadmap_command(
    tmp_path: Path,
    invoke: Callable[..., Run],
    flag: str,
    value: str,
    complaint: str,
) -> None:
    """FR-004 holds on the roadmap verb too, and holds because it is one surface.

    The roadmap is the worse place for a bad dial than the hand-start: it is not
    one epic that fails hours later, it is every child of an unattended run. The
    refusal is `factory/cli/landing.py`'s, unmodified — this asserts the flags
    were declared through the shared module rather than re-spelled here, which
    is the drift `factory/cli/promotion.py` was factored out to prevent.
    """
    result = invoke(
        "roadmap",
        "start",
        str(tmp_path / "specs"),
        "--target-repo",
        TARGET_REPO,
        flag,
        value,
    )
    assert result.code == 2, result
    # Refused *by the dial's own complaint*, not by argparse never having heard
    # of the flag: "unrecognized arguments: --stall-after-s 0" also names the
    # dial and quotes the value, and would pass a laxer assertion while the
    # roadmap offered no dials at all.
    assert "unrecognized arguments" not in result.stderr, result.stderr
    assert complaint in result.stderr, result.stderr
    assert repr(value) in result.stderr or value in result.stderr, result.stderr


# ==============================================================================
# Runtime evidence (constitution VIII: pasted, not described). 2026-08-22, this
# worktree, `uv run` at the repo root.
# ==============================================================================
#
# --- SC-006: a roadmap-dispatched child epic carrying an operator-set dial ----
#
# Captured by a throwaway module beside this one (deleted after the run) that
# drives the same harness these tests use and prints the `EpicInput` the
# roadmap handed `start_child_workflow`:
#
#   $ uv run pytest -q -s tests/_evidence_us2.py
#   $ ergane roadmap start /tmp/.../overnight --target-repo /srv/factory/targets/library \
#         --stall-after-s 900 --max-recovery-cycles 3
#   roadmap-overnight
#
#   child workflow started: EpicWorkflow id=epic-001-overnight
#   child epic id:          001-overnight
#   child EpicInput.landing_config:
#       merge_method         'squash'
#       poll_interval_s      60
#       stall_after_s        900
#       max_recovery_cycles  3
#       max_free_rebases     3
#   .
#   1 passed in 0.91s
#
# The two dials the operator set arrived; the three they did not are today's
# values, which is FR-002 holding on this path too.
#
# --- The suite (FR-006, FR-007, FR-004 on this verb) --------------------------
#
#   $ uv run pytest tests/test_scheduled_epics_carry_the_dials.py -v --no-header
#   collected 9 items
#
#   ...::test_a_dial_set_on_the_roadmap_reaches_the_child_epic PASSED   [ 11%]
#   ...::test_a_roadmap_that_sets_nothing_dispatches_todays_defaults PASSED   [ 22%]
#   ...::test_a_dial_change_reaches_the_next_dispatch_never_the_running_epic PASSED   [ 33%]
#   ...::test_every_dispatch_of_one_run_gets_the_dial_that_run_started_with PASSED   [ 44%]
#   ...::test_no_roadmap_signal_changes_the_dials_of_a_running_roadmap PASSED   [ 55%]
#   ...::test_no_roadmap_input_site_default_constructs_a_landing_config PASSED   [ 66%]
#   ...::test_an_impossible_dial_is_refused_at_the_roadmap_command[--stall-after-s-0-...] PASSED   [ 77%]
#   ...::test_an_impossible_dial_is_refused_at_the_roadmap_command[--landing-poll-interval-s--1-...] PASSED   [ 88%]
#   ...::test_an_impossible_dial_is_refused_at_the_roadmap_command[--merge-method-cherry-pick-...] PASSED   [100%]
#
#   ============================ 9 passed in 1.25s =============================
#
# --- The mutation: does any of this actually drive the wiring? ----------------
#
# `factory/cli/roadmap.py`'s construction reverted to the bare
# `landing_config=LandingConfig()` this story removed — the exact line as it
# stood before — and the suite re-run. Applied, captured, reverted:
#
#   mutated: the roadmap builds LandingConfig() bare again
#   FAILED ...::test_a_dial_set_on_the_roadmap_reaches_the_child_epic
#   FAILED ...::test_a_dial_change_reaches_the_next_dispatch_never_the_running_epic
#   FAILED ...::test_every_dispatch_of_one_run_gets_the_dial_that_run_started_with
#   FAILED ...::test_no_roadmap_input_site_default_constructs_a_landing_config
#   4 failed, 5 passed in 1.27s
#
# The control and the signal case survive the mutation, which is what makes
# them the control: neither is evidence that anything was wired, and both must
# hold on either side of this story.
#
# --- The surface, as the operator meets it -----------------------------------
#
#   $ uv run ergane roadmap start --help
#     --merge-method METHOD
#                           how a passing node's pull request lands (merge,
#                           rebase, squash; default: squash)
#     --landing-poll-interval-s SECONDS
#                           how often a landing in the queue is polled (default:
#                           60)
#     --stall-after-s SECONDS
#                           how long a landing may sit queued and unanswered
#                           before it classifies as stalled (default: 7200)
#     --max-recovery-cycles N
#                           how many times a rejected landing may be recovered
#                           before the node escalates (default: 1)
#     --max-free-rebases N  how many times a landing rejected for a moved base
#                           may be rebased and requeued for free (default: 3)
#
#   $ uv run ergane roadmap start specs --target-repo /srv/x --stall-after-s 0
#   ergane roadmap start: error: argument --stall-after-s: stall-after-s must be
#   an integer >= 1, got '0'
#
# --- Out of scope, and named rather than left to be discovered ----------------
#
# A roadmap run started by its *Temporal schedule* (`ergane init`'s, via
# `factory/roadmap/schedule.py`'s `RoadmapSchedule.arguments()`) carries no
# landing config, so its children run the defaults. That is not a regression
# and not this story's line: those arguments declare no `config`,
# `poll_interval_s` or `idle_rescan_s` either, so *every* operator overlay on a
# roadmap reaches it through `ergane roadmap start` today. Moving them onto the
# manifest is a manifest change (`RoadmapDials`), which US2 does not make.

