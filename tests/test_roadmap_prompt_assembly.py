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

    5 passed in 1.31s
"""

from __future__ import annotations

import shutil
import socket
from pathlib import Path
from typing import Any

import pytest
from temporalio.testing import WorkflowEnvironment

from factory.roadmap.models import SpecState
from factory.usage.litellm_client import LiteLLMClient
from factory.workgraph.derive import derive_workgraph
from factory.workgraph.preflight import prompt_assembly_preflight

from tests.conftest import FAKE_MASTER_KEY, FakeLiteLLM
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


# --- T012 / US2-S4: the fix is picked up ---------------------------------------


async def test_a_fixed_tasks_md_dispatches_on_the_next_roadmap_run(
    env: WorkflowEnvironment, tmp_path: Path
) -> None:
    """A park is a refusal to dispatch *this* spec as written, not a verdict.

    The operator's recovery is an edit: the same four phases, each heading now
    naming its story key. The park itself is run state — it survives
    continue-as-new by design, and no signal clears it — so the operator's unpark
    is the roadmap's next run, which is what this asserts: same corpus, same
    workflow id, fixed `tasks.md`, and the spec that parked now dispatches and
    lands.
    """
    specs_root = tmp_path / "specs"
    specs_root.mkdir()
    spec_dir = plant_ready(HEADING_DEFECT, specs_root / "001-runtime-root")

    async with run_roadmap(env, RoadmapWorld(), str(specs_root)) as handle:
        parked_status = await handle.result()
    assert [finding.check for finding in parked_status.parked] == [
        "preflight:prompt-assembly"
    ]

    # The operator fixes the document the finding named.
    (spec_dir / "tasks.md").write_text(FIXED_TASKS, encoding="utf-8")

    dispatched: list[str] = []
    async with run_roadmap(
        env, RoadmapWorld(), str(specs_root), on_dispatch=dispatched.append
    ) as handle:
        status = await handle.result()

    assert status.parked == []
    assert dispatched == ["001-runtime-root"]
    assert _status_of(status, "001-runtime-root").landed is True


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
