"""044 US2: the roadmap refuses to dispatch an epic whose prompts cannot assemble.

US1 put prompt assembly in `ergane spec validate`, where it costs one command.
That is advice: validation an operator must remember to run is not a gate, and
`tasks.md` is read live at dispatch, so a spec edited after a clean validate can
still arrive broken. US2 puts the same shared check in the slot the roadmap
already refuses from — the pre-epic preflight beside `check_aliases` — so a spec
whose prompts cannot assemble **parks**, with zero nodes dispatched and zero
attempts burned, exactly the way one whose model aliases are unserved does.

The incident is the fixture. `tests/fixtures/prompt_assembly/901-heading-defect`
is the 2026-08-15 kill reconstructed: a `tasks.md` whose phase headings name each
story's *title* and never the story key. It is planted into a roadmap corpus with
its frontmatter flipped to `ready` — the same bytes US1's offline layer refuses,
now put in front of a running scheduler.

Two properties carry this story, and both are asserted here rather than assumed:

- **Nothing was dispatched.** A park that still started the child epic would burn
  the attempts the park exists to save. The child-start interceptor records every
  `start_child_workflow` the roadmap issued, and the scripted epic's `on_dispatch`
  hook fires the moment a child begins running; both must be silent for the
  parked spec.

- **The check is offline.** It is a read of the spec trio and the derived graph
  and nothing else (FR-002), so it cannot make dispatch depend on a proxy that
  answers. `test_the_assembly_preflight_opens_no_client_and_no_socket` runs it
  with `socket.socket` and the proxy client's constructor both booby-trapped.

Trap 1 from the plan is the one that shapes the implementation: workflow code
cannot read files (constitution IV), so the check runs *inside* the preflight
activity, never in `RoadmapWorkflow._dispatch`. The workflow's only change is the
`specs_root` it already holds, carried into `PreflightInput` so the activity can
find the trio.

Red first, and red for the right reason. Against the tree with no check written,
`uv run pytest tests/test_roadmap_prompt_assembly.py -q --no-header` cannot even
import::

    E   ImportError: cannot import name 'prompt_assembly_preflight' from
    'factory.workgraph.preflight'

With `prompt_assembly_preflight` present but returning `[]` — the production code
doing nothing, which is also the mutation this file is proved against — verbatim::

    E       AssertionError: []
    E       assert '001-runtime-root' in {}
    E       AssertionError: assert [] == ['prompt-asse...mpt-assembly']
    E       AssertionError: assert [] == ['preflight:prompt-assembly']
    FAILED tests/test_roadmap_prompt_assembly.py::test_a_spec_whose_prompts_cannot_assemble_parks_with_nothing_dispatched
    FAILED tests/test_roadmap_prompt_assembly.py::test_the_assembly_preflight_opens_no_client_and_no_socket
    FAILED tests/test_roadmap_prompt_assembly.py::test_a_fixed_tasks_md_dispatches_on_the_next_roadmap_run
    FAILED tests/test_roadmap_prompt_assembly.py::test_build_start_refuses_an_epic_whose_prompts_cannot_assemble
    4 failed, 1 passed in 0.82s

The one that passes red is
`test_a_well_formed_ready_spec_still_dispatches_exactly_as_before`, and it had
to: it is the control (US2 scenario 2), asserting that a correct spec's dispatch
is *unchanged*. It goes red only if the new refusal ever refuses something it
should not — which is the thing a preflight is most dangerous for.

Green after, same command::

    5 passed in 0.76s

Proved by mutation, not by colour. Three separate breakages, each caught by
exactly the tests that should catch it and no others:

- Drop the assembly call from `preflight_spec` (the roadmap no longer checks)::

    FAILED ...::test_a_spec_whose_prompts_cannot_assemble_parks_with_nothing_dispatched
    FAILED ...::test_a_fixed_tasks_md_dispatches_on_the_next_roadmap_run
    2 failed, 3 passed in 0.81s

- Drop it from `build._run_preflight` (only the hand-started path stops checking)::

    FAILED ...::test_build_start_refuses_an_epic_whose_prompts_cannot_assemble
    1 failed, 4 passed in 0.81s

- Keep the park but delete the `return` after it, so the roadmap parks the spec
  *and* dispatches it anyway — the failure a park-only assertion would miss::

    E       AssertionError: assert ['epic-001-ru...ic-002-bravo'] == ['epic-002-bravo']
    E         At index 0 diff: 'epic-001-runtime-root' != 'epic-002-bravo'
    FAILED ...::test_a_spec_whose_prompts_cannot_assemble_parks_with_nothing_dispatched
    1 failed, 4 passed in 0.85s

Run the thing, not the tests about it. The production `preflight_spec` activity,
called directly over the reconstructed 043 trio (registry empty, proxy stubbed
to serve nothing, so the only voice is the assembly check), verbatim::

    park [preflight:prompt-assembly] tasks.md: node 'us1': tasks.md declares no phase naming user story US1, so this node has no task slice to work (FR-006). Nothing was dispatched.
    park [preflight:prompt-assembly] tasks.md: node 'us2': tasks.md declares no phase naming user story US2, so this node has no task slice to work (FR-006). Nothing was dispatched.
    park [preflight:prompt-assembly] tasks.md: node 'us3': tasks.md declares no phase naming user story US3, so this node has no task slice to work (FR-006). Nothing was dispatched.
    park [preflight:prompt-assembly] tasks.md: node 'us4': tasks.md declares no phase naming user story US4, so this node has no task slice to work (FR-006). Nothing was dispatched.
    findings=4 nodes=4

...and over `903-well-formed`, the same activity, same stubs::

    findings=0 nodes=2

And the whole suite, `uv run pytest -q`::

    2552 passed, 44 skipped, 5 warnings in 287.37s (0:04:47)

----

**US2-S4, rebuilt.** The first version of this file satisfied "the operator
unparks it" by starting a second roadmap run, and a judge review refused it —
rightly, and for a smaller reason than the mechanism gives. A park is written in
one place (`RoadmapWorkflow._park`), removed in none, and carried across every
continue-as-new by `RoadmapCarryOver`; both dispatch guards skip a parked spec
*before* any check runs. So a fixed `tasks.md` was invisible forever, and the
scenario's operator action did not exist. That is filed as
`roadmap/a-parked-spec-can-never-be-unparked` (critical). This story builds the
signal the scenario names — `unpark_spec`, mirroring `promote_spec` — and the
`ergane roadmap unpark` verb that sends it, and asserts the durability that
makes the signal the only exit.

Red for the three new cases, `uv run pytest tests/test_roadmap_prompt_assembly.py
-q --no-header`, verbatim::

    E       assert [ParkedFindin...dispatched.")] == []
    E         Left contains one more item: ParkedFinding(spec_dir='001-runtime-root', check='preflight:prompt-assembly', detail="tasks.md: node 'us1': tasks.md declares no phase naming user story US1, so this node has no task slice to work (FR-006). Nothing was dispatched.")
    E       AssertionError: assert (2, '', 'usag..., promote)\\n') == (0, '', '')
    E           AttributeError: module 'factory.cli.roadmap' has no attribute 'roadmap_unpark_command'
    FAILED ...::test_the_operator_unparks_a_fixed_spec_and_the_next_tick_dispatches_it
    FAILED ...::test_the_roadmap_unpark_verb_signals_the_running_roadmap
    FAILED ...::test_the_unpark_verb_carries_the_spec_the_operator_named
    3 failed, 5 passed in 1.12s

The first of those is the shape of the defect itself: the signal was sent to a
workflow that declares none, the roadmap ran to completion, and the spec was
still parked with its `tasks.md` long since fixed.

`test_a_park_survives_continue_as_new_when_no_one_unparks_it` passes red on
purpose — it pins behaviour that already exists, and it is what stops the unpark
test from being satisfiable by a roadmap that simply forgot its parks.

Green after::

    8 passed in 1.16s

Three more mutations, each red in exactly one place — and the first two are the
control/treatment pair that makes this story mean something::

    # unpark_spec accepts the signal and does nothing
    FAILED ...::test_the_operator_unparks_a_fixed_spec_and_the_next_tick_dispatches_it
    1 failed, 7 passed in 1.15s

    # the carry-over drops the parks at the continue-as-new boundary
    E       AssertionError: assert [] == ['001-runtime-root']
    FAILED ...::test_a_park_survives_continue_as_new_when_no_one_unparks_it
    1 failed, 7 passed in 1.26s

    # the verb signals `unpark_spec` without the spec dir
    E       AssertionError: assert [('unpark_spec', ())] == [('unpark_spe...time-root',))]
    FAILED ...::test_the_unpark_verb_carries_the_spec_the_operator_named
    1 failed, 7 passed in 1.14s

The verb as an operator meets it, `uv run python -m factory.cli.main roadmap
--help` and `... roadmap unpark --help`, verbatim::

    usage: ergane roadmap [-h] {start,pause,resume,status,promote,unpark} ...
        promote             promote a draft spec to ready
        unpark              clear a parked spec so the next pass tries it again

    usage: ergane roadmap unpark [-h] --spec SPEC specs_root
      --spec SPEC  spec directory name to unpark

And the whole suite again, `uv run pytest -q`::

    2555 passed, 44 skipped, 4 warnings in 284.04s (0:04:44)
"""

from __future__ import annotations

import asyncio
import shutil
import socket
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest
from temporalio.api.enums.v1 import EventType
from temporalio.testing import WorkflowEnvironment

from factory.roadmap.models import SpecState
from factory.roadmap.workflow import RoadmapStatus
from factory.usage.litellm_client import LiteLLMClient
from factory.workgraph.derive import derive_workgraph
from factory.workgraph.preflight import prompt_assembly_preflight

from tests.conftest import FAKE_MASTER_KEY, FakeLiteLLM
from tests.roadmap_script import _SCRIPT
from tests.test_roadmap_schedule_discovery import (  # noqa: F401  (fake_temporal)
    BARE_ID,
    SPECS_ROOT,
    bare_floor,
    fake_temporal,
    invoke,
)
from tests.test_roadmap_scheduler import (  # noqa: F401  (env is a fixture)
    ChildStartRecord,
    RoadmapWorld,
    TARGET_REPO,
    _status_of,
    build_corpus,
    env,
    run_roadmap,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "prompt_assembly"
HEADING_DEFECT = FIXTURES / "901-heading-defect"
WELL_FORMED = FIXTURES / "903-well-formed"

#: The refusal the 2026-08-15 dispatch tick printed, byte for byte. The park's
#: detail must quote it rather than summarize it: the operator's next move is an
#: edit to `tasks.md`, and a paraphrase of the grammar is not the grammar.
INCIDENT_REFUSAL = (
    "node 'us1': tasks.md declares no phase naming user story US1, so this node "
    "has no task slice to work (FR-006)"
)

#: The `tasks.md` the operator writes to fix the defect: the same four phases,
#: each heading now naming its story key. Nothing else about the trio changes.
FIXED_TASKS = """# Tasks: Runtime root integrity (reconstructed)

The repair: every phase heading now names its story key, so the assembler finds
a slice for each node.

## Phase 1: User Story 1 - The leak detector stops requiring the live store's absence

- [ ] T001 [P] Write the failing test: the detector passes on a host carrying a
      live store (spec US1-S1) — must fail.
- [ ] T002 Make it pass without deleting anything.

## Phase 2: User Story 2 - The findings ledger is addressed through the resolver

- [ ] T003 [P] Write the failing test: a relocated root is read from
      (spec US2-S1) — must fail.
- [ ] T004 Route the ledger read through the resolver.

## Phase 3: User Story 3 - The runtime root can be migrated

- [ ] T005 [P] Write the failing test: every store is present under the new root
      (spec US3-S1) — must fail.
- [ ] T006 Implement the migration.

## Phase 4: User Story 4 - The migration refusal names the variable the operator set

- [ ] T007 [P] Write the failing test: the refusal names the variable
      (spec US4-S1) — must fail.
- [ ] T008 Name the variable in the refusal.
"""


def plant_ready(fixture: Path, destination: Path) -> Path:
    """Copy a committed fixture trio into a corpus and mark it `ready`.

    The trio is copied whole — spec, plan and tasks — because the preflight reads
    all three, and the defect this story is about lives in the one a corpus
    builder would be least likely to write. Only the frontmatter state changes:
    the fixtures are authored `draft` so no other suite's corpus scan treats them
    as dispatchable, and a roadmap only reaches its pre-dispatch checks for a
    spec it considers ready.
    """
    shutil.copytree(fixture, destination)
    spec_path = destination / "spec.md"
    text = spec_path.read_text(encoding="utf-8")
    assert "state: draft" in text, f"{fixture} is no longer authored draft"
    spec_path.write_text(text.replace("state: draft", "state: ready", 1), encoding="utf-8")
    return destination


# --- T009 / US2-S1, SC-003: the park, with nothing dispatched -----------------


async def test_a_spec_whose_prompts_cannot_assemble_parks_with_nothing_dispatched(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """The 2026-08-15 kill, met by a running roadmap: park, not dispatch.

    `001-runtime-root` is the reconstructed incident, `ready`. `002-bravo` is an
    ordinary well-formed spec beside it. The roadmap must park the first with the
    assembler's refusal verbatim under the check name `prompt-assembly`, start no
    child for it at all — the epic that died in production was four nodes, four
    keys and four attempt slots — and go on to land the second, because one bad
    spec must not stall the line.
    """
    specs_root = build_corpus(tmp_path, {"002-bravo": dict(state=SpecState.READY)})
    plant_ready(HEADING_DEFECT, specs_root / "001-runtime-root")

    dispatched: list[str] = []
    starts: list[ChildStartRecord] = []
    world = RoadmapWorld()
    async with run_roadmap(
        env,
        world,
        str(specs_root),
        on_dispatch=dispatched.append,
        child_starts=starts,
    ) as handle:
        status = await handle.result()

    parked = {finding.spec_dir: finding for finding in status.parked}
    assert "001-runtime-root" in parked, status.parked
    assert parked["001-runtime-root"].check == "preflight:prompt-assembly"
    # The assembler's own words, not a summary of them.
    assert INCIDENT_REFUSAL in parked["001-runtime-root"].detail
    assert "tasks.md" in parked["001-runtime-root"].detail

    # Nothing was dispatched for it: no child was started, and none ran.
    assert [record.id for record in starts] == ["epic-002-bravo"]
    assert dispatched == ["002-bravo"]

    # The line kept moving.
    assert _status_of(status, "002-bravo").landed is True
    assert "002-bravo" not in parked


# --- T010 / US2-S2: a well-formed spec dispatches exactly as before -----------


async def test_a_well_formed_ready_spec_still_dispatches_exactly_as_before(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """The control: a trio whose every node assembles dispatches and lands.

    `903-well-formed` is the fixture US1 pins as clean. Planted `ready` in a
    corpus, it must reach its child epic with nothing parked — a preflight that
    refused a correct spec would be a worse failure than the one it prevents.
    """
    specs_root = tmp_path / "specs"
    specs_root.mkdir()
    plant_ready(WELL_FORMED, specs_root / "001-short-links")

    dispatched: list[str] = []
    starts: list[ChildStartRecord] = []
    world = RoadmapWorld()
    async with run_roadmap(
        env,
        world,
        str(specs_root),
        on_dispatch=dispatched.append,
        child_starts=starts,
    ) as handle:
        status = await handle.result()

    assert status.parked == []
    assert dispatched == ["001-short-links"]
    assert [record.id for record in starts] == ["epic-001-short-links"]
    assert _status_of(status, "001-short-links").landed is True


# --- T011 / US2-S3, FR-002: the check is a pure read --------------------------


def test_the_assembly_preflight_opens_no_client_and_no_socket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-002: the trio and the graph are the whole input — no proxy, no network.

    The alias half of the preflight dials the proxy; the assembly half must not,
    or a spec's dispatchability would come to depend on a service answering. Both
    routes out are booby-trapped: `socket.socket` raises on any dialled
    connection, and `LiteLLMClient.__init__` raises if a client is constructed at
    all. The findings still come back, so the check ran.
    """
    spec_dir = plant_ready(HEADING_DEFECT, tmp_path / "001-runtime-root")
    graph = derive_workgraph(
        (spec_dir / "spec.md").read_text(encoding="utf-8"),
        epic_id="001-runtime-root",
        feature="001-runtime-root",
        specs_root=str(tmp_path),
        target_repo=TARGET_REPO,
    )

    def no_socket(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the prompt-assembly preflight must open no socket")

    def no_client(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the prompt-assembly preflight must open no client")

    monkeypatch.setattr(socket, "socket", no_socket)
    monkeypatch.setattr(LiteLLMClient, "__init__", no_client)

    findings = prompt_assembly_preflight(graph, spec_dir)

    assert [finding.check for finding in findings] == ["prompt-assembly"] * 4
    assert all(finding.passed is False for finding in findings)
    # Not a transport failure: nothing was dialled, so nothing could be down.
    assert all(finding.transport is False for finding in findings)
    assert INCIDENT_REFUSAL in findings[0].detail


# --- T012 / US2-S4: the operator unparks, and the next tick dispatches ---------


async def _await_park(handle: Any, spec_dir: str) -> Any:
    """Poll `roadmap_status` until `spec_dir` is parked, and hand back its finding."""

    async def poll() -> Any:
        while True:
            status = await handle.query("roadmap_status", result_type=RoadmapStatus)
            for finding in status.parked:
                if finding.spec_dir == spec_dir:
                    return finding
            await asyncio.sleep(0.01)

    return await asyncio.wait_for(poll(), timeout=30)


async def _await_running(handle: Any, spec_dir: str) -> None:
    """Poll `roadmap_status` until `spec_dir`'s child epic is in flight.

    Both tests below hold `002-bravo` open to keep the roadmap alive, and then
    signal `epic-002-bravo` directly to release it. That signal needs the child
    to exist, and parking `001-runtime-root` happens strictly earlier in the same
    pass — so `_await_park` returning says nothing about whether the child has
    started yet.

    Until 052 US2 the gap was covered by accident. `roadmap_status` crashed while
    the roadmap had not yet read its corpus (`RoadmapStatus.__init__() missing 1
    required positional argument: 'max_concurrent_nodes'`), the SDK retried the
    failed query behind the client call, and the first answer therefore arrived
    ~120ms late — by which time the child was running. Repairing the query made
    the first answer arrive in ~10ms, which is early enough to see the park
    before the dispatch, and both tests started signalling a workflow that did
    not exist: `Execution not found in mutable state: workflowId='epic-002-bravo'`.

    So the wait is explicit now, and it says what it is waiting for.
    """

    async def poll() -> None:
        while True:
            status = await handle.query("roadmap_status", result_type=RoadmapStatus)
            if spec_dir in status.running:
                return
            await asyncio.sleep(0.01)

    await asyncio.wait_for(poll(), timeout=30)


async def test_the_operator_unparks_a_fixed_spec_and_the_next_tick_dispatches_it(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """US2-S4, literally: park, fix, **unpark the running roadmap**, dispatch.

    The park is a refusal to dispatch this spec *as it was read*, and the roadmap
    does not re-read it: both dispatch guards skip a parked spec before any check
    runs, and the park rides the carry-over across every continue-as-new. So an
    operator who fixes `tasks.md` and waits gets nothing — the fix is invisible
    until they say the park is spent. `unpark_spec` is that sentence, and this
    test sends it to the same running workflow rather than starting a new one:

    1. `001-runtime-root` (the reconstructed 043 defect) parks; `002-bravo`
       dispatches and is held open, which is what keeps this one run alive.
    2. The operator fixes `tasks.md`.
    3. The operator signals `unpark_spec("001-runtime-root")`.
    4. `002-bravo` is released, the roadmap reaches its next pass, and the
       unparked spec dispatches and lands — dispatched *after* bravo, in the
       tick that followed the signal.

    Nothing here re-checks assembly on the operator's behalf: the next pass runs
    every pre-dispatch check again, so an unpark of a still-broken spec simply
    parks again. The signal clears a verdict; it does not grant one.
    """
    specs_root = build_corpus(tmp_path, {"002-bravo": dict(state=SpecState.READY)})
    spec_dir = plant_ready(HEADING_DEFECT, specs_root / "001-runtime-root")

    # Hold bravo's child open so the roadmap is still running — and still this
    # run — when the edit and the signal land.
    _SCRIPT.hold = {"002-bravo"}

    dispatched: list[str] = []
    async with run_roadmap(
        env, RoadmapWorld(), str(specs_root), on_dispatch=dispatched.append
    ) as handle:
        parked = await _await_park(handle, "001-runtime-root")
        assert parked.check == "preflight:prompt-assembly"
        assert INCIDENT_REFUSAL in parked.detail

        (spec_dir / "tasks.md").write_text(FIXED_TASKS, encoding="utf-8")
        await handle.signal("unpark_spec", "001-runtime-root")

        # Let the held child finish; the roadmap's next pass is what dispatches.
        await _await_running(handle, "002-bravo")
        await env.client.get_workflow_handle("epic-002-bravo").signal("release")
        status = await handle.result()

    assert status.parked == []
    assert dispatched == ["002-bravo", "001-runtime-root"]
    assert _status_of(status, "001-runtime-root").landed is True


async def test_a_park_survives_continue_as_new_when_no_one_unparks_it(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """The park is durable, which is what makes the unpark signal mean anything.

    Identical to the test above in every respect but one: nobody signals. The
    `tasks.md` is fixed just the same, the roadmap crosses a continue-as-new
    boundary just the same (bravo's completion at quiescence forces one, and the
    first run's history is asserted to carry the event), and the spec stays
    parked and undispatched anyway.

    Without this, the unpark test proves nothing: a roadmap that quietly dropped
    its parks — or never parked at all — would pass it. With it, the pair is a
    control and a treatment. It is also the mechanism of
    `roadmap/a-parked-spec-can-never-be-unparked` (critical, 2026-08-16) pinned
    as a test: before `unpark_spec` there was no exit from this state, because
    nothing writes to `_parked` but `_park`, and nothing removed from it at all.
    """
    specs_root = build_corpus(tmp_path, {"002-bravo": dict(state=SpecState.READY)})
    spec_dir = plant_ready(HEADING_DEFECT, specs_root / "001-runtime-root")

    _SCRIPT.hold = {"002-bravo"}

    dispatched: list[str] = []
    async with run_roadmap(
        env, RoadmapWorld(), str(specs_root), on_dispatch=dispatched.append
    ) as handle:
        await _await_park(handle, "001-runtime-root")

        # The operator fixes the document — and does nothing else.
        (spec_dir / "tasks.md").write_text(FIXED_TASKS, encoding="utf-8")

        await _await_running(handle, "002-bravo")
        await env.client.get_workflow_handle("epic-002-bravo").signal("release")
        status = await handle.result()

        # The boundary was really crossed. The first run's last event is the
        # continue-as-new itself, so the park reported below is one that rode
        # the carry-over rather than one that never met a boundary. (The
        # handle's own `fetch_history` follows the chain to the final run,
        # which ends COMPLETED — the first run has to be asked for by id.)
        first_run = env.client.get_workflow_handle(
            handle.id, run_id=handle.first_execution_run_id
        )
        history = await first_run.fetch_history()
        assert (
            history.events[-1].event_type
            == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_CONTINUED_AS_NEW
        ), "the roadmap never continued-as-new, so nothing was carried over"

    assert [finding.spec_dir for finding in status.parked] == ["001-runtime-root"]
    assert dispatched == ["002-bravo"]
    assert _status_of(status, "001-runtime-root").landed is False


# --- T012 / US2-S4: the verb the operator actually types -----------------------


def test_the_roadmap_unpark_verb_signals_the_running_roadmap(
    fake_temporal: Callable[..., Any],
) -> None:
    """`ergane roadmap unpark <root> --spec <dir>` reaches the run, silently.

    The same resolution, exit code and silence `promote` has — a signal verb
    that printed something would be the odd one out on this noun.
    """
    client = bare_floor(fake_temporal)

    result = invoke("roadmap", "unpark", SPECS_ROOT, "--spec", "011-agent-sandbox")

    assert (result.code, result.stdout, result.stderr) == (0, "", "")
    assert client.signals == [(BARE_ID, "unpark_spec")]


async def test_the_unpark_verb_carries_the_spec_the_operator_named() -> None:
    """The signal's argument, which the shared fake handle does not record.

    A verb that sent `unpark_spec` with no spec dir would satisfy the test above
    and unpark nothing, so the argument is asserted here against a handle that
    keeps it.
    """
    from factory.cli import roadmap as roadmap_cli

    sent: list[tuple[str, tuple[Any, ...]]] = []

    class _Handle:
        async def signal(self, name: str, *args: Any) -> None:
            sent.append((name, args))

    async def _handle(_args: Any) -> Any:
        return _Handle()

    original = roadmap_cli._get_handle
    roadmap_cli._get_handle = _handle  # type: ignore[assignment]
    try:
        code = await roadmap_cli.roadmap_unpark_command(
            SimpleNamespace(specs_root="specs", spec="001-runtime-root")
        )
    finally:
        roadmap_cli._get_handle = original  # type: ignore[assignment]

    assert code == 0
    assert sent == [("unpark_spec", ("001-runtime-root",))]


# --- T014 / FR-003: `ergane build start` refuses on the same check -------------


async def test_build_start_refuses_an_epic_whose_prompts_cannot_assemble(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The hand-started epic gets the same refusal the roadmap's does.

    `ergane build start` runs the preflight before it starts a workflow, and an
    operator starting the reconstructed 043 epic by hand would otherwise watch
    the same four nodes die one tick later. The registry is empty and the proxy
    is a fake that serves everything asked of it, so the only thing that can
    speak here is the assembly check.
    """
    from factory.cli.nouns import build as build_noun

    spec_dir = plant_ready(HEADING_DEFECT, tmp_path / "001-runtime-root")
    graph = derive_workgraph(
        (spec_dir / "spec.md").read_text(encoding="utf-8"),
        epic_id="001-runtime-root",
        feature="001-runtime-root",
        specs_root=str(tmp_path),
        target_repo=TARGET_REPO,
    )

    fake = FakeLiteLLM()
    monkeypatch.setattr(build_noun, "_preflight_registry", dict)
    monkeypatch.setattr(
        build_noun,
        "_open_preflight_client",
        lambda: LiteLLMClient(
            base_url=fake.base_url,
            master_key=FAKE_MASTER_KEY,
            transport=fake.transport,
        ),
    )

    findings = await build_noun._run_preflight(graph)

    assert [finding.check for finding in findings] == ["prompt-assembly"] * 4
    assert INCIDENT_REFUSAL in findings[0].detail
    # Exit 1 (a user error the operator fixes), never exit 3 (a service failure).
    assert await build_noun._preflight_exit_code(findings) == 1
