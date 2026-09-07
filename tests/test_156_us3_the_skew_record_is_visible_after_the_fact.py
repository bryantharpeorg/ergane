"""156 US3: the skew a dispatch refused on is visible after the fact.

US3-S1: a `build start` refused under US1 leaves a record an operator can read
an hour later — the refusal message itself names both revisions, and re-running
the command (or `build status`, whose answer path
`factory/cli/nouns/build.py` reads `worker_revision` from the same
`epic_status` document) recomputes the skew from live sources. Nothing is
remembered: a refusal that quoted a stored record would keep naming a skew that
has already moved.

US3-S2: a spec parked under US2 leaves the same kind of record in the parked
list — the detail the park wrote reaches `roadmap status` verbatim, both
revisions intact, and it survives the tick that wrote it (the same pass
dispatches the next spec; the record is still there at the end of the run).

US3-S3: neither refusal is a durable state to clean up. When the worker is
restarted and the skew clears, the same commands run clean — and no store was
minted on the way: the refusal path writes nothing durable, so an
implementation that adds skew state fails the tripwire here.

The start-path fixtures are US1's, imported (`start_env`, `run_async`,
`_write_graph`): the refusal under record is the one US1 built, and a second
copy of its harness would be a second place to drift. The roadmap-side fakes
are the scheduler harness's, for the same reason. The status-path fakes are the
053 status-refusal shape — the client `_query_status` already reads through.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable

import pytest

import factory.cli.nouns as nouns_package
from factory.cli.nouns import build as build_module
from factory.roadmap.models import SpecState
from factory.workgraph.preflight import PreflightFinding

from tests.test_156_us1_build_start_refuses_skewed_worker import (
    CLI_REVISION,
    RESTART_REMEDY,
    WORKER_REVISION_A,
    WORKER_REVISION_B,
    WORKFLOW_ID,
    _open_epics,
    _query_document,
    _write_graph,
    fake_lite_llm_and_preflight,  # noqa: F401 - start_env's fixture dependency
    run,
    run_async,
    start_env,
)
from tests.test_ergane_build_status_refusal import (
    _FakeWorkflow,
    _invoke as invoke_status,
    fake_status_client,
)
from tests.test_ergane_roadmap import (
    TARGET_REPO,
    _run_in_thread,
    _wait_for_running,
    _worker,
    env as roadmap_env,
    invoke as roadmap_invoke,
)
from tests.test_roadmap_scheduler import (
    RoadmapWorld,
    _status_of,
    build_corpus,
    run_to_completion,
)
from tests.roadmap_script import _SCRIPT

#: A third revision for the recompute proof: the first refusal named B, so a
#: record that answered from memory would still name B after the advertisement
#: has moved to C. Equal length to the others (a short sha) and unequal to both.
WORKER_REVISION_C = "feedc0d"

STATUS_EPIC_ID = "156-us3-demo"
STATUS_WORKFLOW_ID = f"epic-{STATUS_EPIC_ID}"


# --- T012 / US3-S1: the record is recomputable from live sources ---------------


async def test_a_refused_start_reads_its_record_again_from_live_sources_on_re_run(
    run_async: Callable[..., object],
    tmp_path: Path,
    start_env: Callable[..., object],
) -> None:
    """US3-S1: re-running a refused `build start` re-derives the refusal.

    The scenario's "when the operator re-runs it": the same command, run again,
    reads both revisions from the same live seams (`_worker_advertisement` and
    `_cli_revision`) and refuses again with the same line. The third run is the
    recompute proof: with the worker's advertisement moved to C — a worker
    restarted onto different code — the refusal names C and no longer names B.
    A record read from a store would still name B; this one cannot.
    """
    client = start_env(worker_revision_seam=WORKER_REVISION_B)
    graph_path = _write_graph(tmp_path)

    first = await run_async("build", "start", str(graph_path))  # type: ignore[operator]
    assert first.code != 0
    assert client.started == []
    first_lines = [
        line for line in first.stderr.splitlines() if "worker revision" in line
    ]
    assert len(first_lines) == 1
    assert WORKER_REVISION_B in first_lines[0]
    assert CLI_REVISION in first_lines[0]
    assert RESTART_REMEDY in first_lines[0]

    second = await run_async("build", "start", str(graph_path))  # type: ignore[operator]
    assert second.code != 0
    second_lines = [
        line for line in second.stderr.splitlines() if "worker revision" in line
    ]
    assert second_lines == first_lines, (
        "the re-run's refusal is not the refusal recomputed from the same live "
        f"sources:\n  first:  {first_lines}\n  second: {second_lines}"
    )

    # The advertisement moves (the worker was restarted onto different code):
    # the record follows the live answer, not the refusal that came before.
    client.open_epics = _open_epics(WORKER_REVISION_C)
    third = await run_async("build", "start", str(graph_path))  # type: ignore[operator]
    assert third.code != 0
    third_lines = [
        line for line in third.stderr.splitlines() if "worker revision" in line
    ]
    assert len(third_lines) == 1
    assert WORKER_REVISION_C in third_lines[0]
    assert WORKER_REVISION_B not in third_lines[0], (
        "the re-run quoted the earlier refusal's revision — the record is being "
        "remembered somewhere instead of recomputed from the live advertisement"
    )


def test_build_status_reports_the_skew_from_the_same_live_sources(
    fake_status_client: Callable[..., object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S1: `build status` carries the live worker revision beside the tree's.

    The "any command that reports the tree's revision" arm. The status answer
    path reads `worker_revision` off the same `epic_status` document the refusal
    read (FR-002's single source), compares it against `_cli_revision`, and
    renders the notice naming both — so the operator's second command an hour
    later says what the refused dispatch said, recomputed from live sources.
    """
    fake_status_client(
        workflows={
            STATUS_WORKFLOW_ID: _FakeWorkflow(_query_document(WORKER_REVISION_B))
        }
    )
    monkeypatch.setattr(
        nouns_package, "_cli_revision_for_tests", lambda: CLI_REVISION
    )

    result = invoke_status("build", "status", STATUS_EPIC_ID)

    assert result.code == 0, result.stderr
    notice_lines = [
        line for line in result.stderr.splitlines() if "worker revision" in line
    ]
    assert len(notice_lines) == 1
    assert WORKER_REVISION_B in notice_lines[0]
    assert CLI_REVISION in notice_lines[0]


def test_build_status_json_carries_the_live_worker_revision_and_the_notice(
    fake_status_client: Callable[..., object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S1: the JSON answer carries both facts as fields, not just as prose.

    `worker_revision` is the live advertisement verbatim and `skew_notice` is
    the comparison — a reader scripting against the status answer gets the two
    revisions without parsing a sentence.
    """
    fake_status_client(
        workflows={
            STATUS_WORKFLOW_ID: _FakeWorkflow(_query_document(WORKER_REVISION_B))
        }
    )
    monkeypatch.setattr(
        nouns_package, "_cli_revision_for_tests", lambda: CLI_REVISION
    )

    result = invoke_status("build", "status", STATUS_EPIC_ID, "--json")

    assert result.code == 0, result.stderr
    document = result.json
    assert document["worker_revision"] == WORKER_REVISION_B
    assert CLI_REVISION in document["skew_notice"]
    assert WORKER_REVISION_B in document["skew_notice"]


def test_build_status_names_an_unknown_worker_as_unknown(
    fake_status_client: Callable[..., object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S1: the unknown-worker refusal has the same kind of record at status.

    A worker advertising `None` refuses at dispatch with the "unknown" wording
    (US1-S3); the status path's notice arm says the same thing about the same
    answer, so the record an hour later matches the refusal the operator saw.
    """
    fake_status_client(
        workflows={STATUS_WORKFLOW_ID: _FakeWorkflow(_query_document(None))}
    )
    monkeypatch.setattr(
        nouns_package, "_cli_revision_for_tests", lambda: CLI_REVISION
    )

    result = invoke_status("build", "status", STATUS_EPIC_ID)

    assert result.code == 0, result.stderr
    assert "worker revision is unknown" in result.stderr
    assert CLI_REVISION in result.stderr


# --- T012 / US3-S2: the parked list is the record -------------------------------


async def test_the_parked_list_is_the_record_and_survives_the_tick_that_wrote_it(
    roadmap_env: object,
    tmp_path: Path,
) -> None:
    """US3-S2: a park's detail reaches the parked list byte-verbatim and stays.

    The record for the roadmap seam is the parked list itself. A spec refused
    with the detail FR-004 mandates — both revisions and the restart remedy —
    is still carrying that detail verbatim at the end of the pass that also
    dispatched the next spec: the tick moved on, the record did not evaporate.

    The park here fires through the preflight stage (the one refusal grammar
    this tree has); which stage fires under skew is US2's T006. What US3 owns
    is the carriage: whatever detail a dispatch-park writes, the parked list
    holds it byte for byte.
    """
    detail = build_module.skew_refusal(WORKER_REVISION_B, CLI_REVISION)
    assert detail is not None and WORKER_REVISION_B in detail
    assert CLI_REVISION in detail and RESTART_REMEDY in detail

    specs_root = build_corpus(
        tmp_path,
        {
            "001-parked": dict(state=SpecState.READY),
            "002-next": dict(state=SpecState.READY),
        },
    )
    refusal = PreflightFinding(
        check="worker-revision",
        passed=False,
        detail=detail,
    )
    world = RoadmapWorld(
        preflight=lambda epic_id: [refusal] if epic_id == "001-parked" else []
    )
    status = await run_to_completion(
        roadmap_env, world, str(specs_root)  # type: ignore[arg-type]
    )

    parked = {p.spec_dir: p for p in status.parked}
    assert "001-parked" in parked, (
        f"the refused spec is not in the parked list: {status.parked}"
    )
    assert parked["001-parked"].detail == detail, (
        "the park detail did not survive to the status answer verbatim: "
        f"{parked['001-parked'].detail!r}"
    )
    # The tick that wrote the record proceeded to the next spec — the record
    # outlived the pass, it did not stall it.
    assert _status_of(status, "002-next").landed is True


async def test_roadmap_status_carries_the_park_record_verbatim(
    roadmap_env: object,
    tmp_path: Path,
    roadmap_invoke: Callable[..., object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S2: `ergane roadmap status` is the surface the record is readable on.

    The operator's verb — the one the scenario names — reads the run's status
    while the roadmap is live: the parked entry's detail carries both revisions
    and the remedy verbatim through `--json`, and the human view counts the
    park. No second surface is minted; the parked list is the record.
    """
    detail = build_module.skew_refusal(WORKER_REVISION_B, CLI_REVISION)
    assert detail is not None

    specs_root = build_corpus(
        tmp_path,
        {
            "001-parked": dict(state=SpecState.READY),
            "002-next": dict(state=SpecState.READY),
        },
    )
    refusal = PreflightFinding(
        check="worker-revision",
        passed=False,
        detail=detail,
    )
    world = RoadmapWorld(
        preflight=lambda epic_id: [refusal] if epic_id == "001-parked" else []
    )
    world.apply()
    _SCRIPT.statuses = {}
    _SCRIPT.on_dispatch = None
    _SCRIPT.on_complete = None
    # Hold the second spec's child so the run is alive when the operator's verb
    # reads it — the same posture every `roadmap status` test here uses.
    _SCRIPT.hold = {"002-next"}
    try:
        async with _worker(roadmap_env, world):  # type: ignore[arg-type]
            started = await _run_in_thread(
                roadmap_invoke,  # type: ignore[operator]
                "roadmap",
                "start",
                str(specs_root),
                "--target-repo",
                TARGET_REPO,
            )
            assert started.code == 0, started.stderr
            await _wait_for_running(roadmap_env, specs_root, "002-next")  # type: ignore[arg-type]

            json_view = await _run_in_thread(
                roadmap_invoke, "roadmap", "status", str(specs_root), "--json"
            )
            human_view = await _run_in_thread(
                roadmap_invoke, "roadmap", "status", str(specs_root)
            )

            assert json_view.code == 0, json_view.stderr
            document = json_view.json
            parked = {p["spec_dir"]: p for p in document["parked"]}
            assert "001-parked" in parked, f"not parked: {document['parked']}"
            assert parked["001-parked"]["detail"] == detail, (
                "the park detail the operator reads is not the detail the "
                f"refusal wrote: {parked['001-parked']['detail']!r}"
            )
            assert parked["001-parked"]["check"] == "preflight:worker-revision"

            # The human view counts the same record through the standing
            # rendering every other parked cause uses — no new surface.
            assert human_view.code == 0, human_view.stderr
            assert "parked: 1" in human_view.stdout

            # Let the held child land so the run ends cleanly.
            await roadmap_env.client.get_workflow_handle(  # type: ignore[union-attr]
                "epic-002-next"
            ).signal("release")
    finally:
        world.restore()
        _SCRIPT.hold = set()
        _SCRIPT.statuses = {}
        _SCRIPT.on_dispatch = None
        _SCRIPT.on_complete = None


# --- T013 / US3-S3: no residue, no store ----------------------------------------


async def test_a_cleared_skew_leaves_no_residue_in_the_command_it_refused(
    run_async: Callable[..., object],
    tmp_path: Path,
    start_env: Callable[..., object],
) -> None:
    """US3-S3: once the skew clears, the same command runs clean.

    The worker "restarts" onto the tree's revision (the advertisement returns
    to the CLI's), and the command that refused twice dispatches — no skew
    wording anywhere in either stream, nothing for the operator to clean up
    before working. A refusal that left durable state would have to be
    retracted here; this one leaves nothing.
    """
    start_env(worker_revision_seam=WORKER_REVISION_B)
    graph_path = _write_graph(tmp_path)

    refused = await run_async("build", "start", str(graph_path))  # type: ignore[operator]
    assert refused.code != 0

    client = start_env(worker_revision_seam=WORKER_REVISION_A)  # the restart
    cleared = await run_async("build", "start", str(graph_path))  # type: ignore[operator]

    assert cleared.code == 0, cleared.stderr
    assert cleared.stdout.strip() == WORKFLOW_ID
    assert len(client.started) == 1
    assert "different code" not in cleared.stdout
    assert "different code" not in cleared.stderr
    assert "restart" not in cleared.stdout.lower()


def test_build_status_shows_no_residue_once_the_worker_is_aligned(
    fake_status_client: Callable[..., object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US3-S3: the status record is gone the moment the skew is.

    The same status read that named the skew is silent about it once the
    advertisement equals the tree's revision — no notice line, no JSON field.
    The record was a fact about a moment, recomputed at every read; a cleared
    skew leaves no residue in the answer.
    """
    fake_status_client(
        workflows={
            STATUS_WORKFLOW_ID: _FakeWorkflow(_query_document(WORKER_REVISION_A))
        }
    )
    monkeypatch.setattr(
        nouns_package, "_cli_revision_for_tests", lambda: CLI_REVISION
    )

    human = invoke_status("build", "status", STATUS_EPIC_ID)
    assert human.code == 0, human.stderr
    assert "worker revision" not in human.stderr
    assert "different code" not in human.stderr

    as_json = invoke_status("build", "status", STATUS_EPIC_ID, "--json")
    assert as_json.code == 0, as_json.stderr
    document = as_json.json
    assert "skew_notice" not in document, (
        f"an aligned worker still carries a skew notice: {document['skew_notice']!r}"
    )


def _snapshot(roots: list[Path]) -> dict[str, str]:
    """Every path under `roots`, with file contents — the tripwire's baseline."""
    seen: dict[str, str] = {}
    for root in roots:
        if not root.exists():
            seen[str(root)] = "<absent>"
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file():
                seen[str(path)] = path.read_bytes().hex()
            else:
                seen[f"{path}/"] = "<dir>"
    return seen


async def test_a_refusal_mints_no_durable_skew_state(
    run_async: Callable[..., object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    start_env: Callable[..., object],
) -> None:
    """US3-S3 / T013's tripwire: the refusal path writes nothing durable.

    Every state root the CLI can reach is redirected into this test's tmp tree
    and snapshotted before and after a refused `build start` — and again after
    the aligned re-run. The refusal is a message and an exit code; if an
    implementation mints a skew store (a database, a sidecar, a row in an
    existing one), some byte under these roots moves and this fails.

    This is the test the plan means by "no new store is minted": it cannot pass
    on a tree that records the skew anywhere but the operator's scrollback.
    """
    state = tmp_path / "state"
    root = tmp_path / "runtime-root"
    home = tmp_path / "home"
    for variable in ("ERGANE_STATE_HOME", "FACTORY_STATE_HOME"):
        monkeypatch.setenv(variable, str(state))
    for variable in ("ERGANE_ROOT", "FACTORY_ROOT"):
        monkeypatch.setenv(variable, str(root))
    for variable in ("ERGANE_VERIFICATION_DB_PATH", "FACTORY_VERIFICATION_DB_PATH"):
        monkeypatch.setenv(variable, str(state / "verification.db"))
    for variable in ("ERGANE_LEDGER_PATH", "FACTORY_LEDGER_PATH"):
        monkeypatch.setenv(variable, str(state / "ledger.jsonl"))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    watched = [state, root, home]

    client = start_env(worker_revision_seam=WORKER_REVISION_B)
    graph_path = _write_graph(tmp_path)
    before = _snapshot(watched)

    refused = await run_async("build", "start", str(graph_path))  # type: ignore[operator]
    assert refused.code != 0
    assert client.started == []

    after_refusal = _snapshot(watched)
    assert after_refusal == before, (
        "the refused dispatch wrote durable state — the skew record is being "
        f"minted somewhere: {set(after_refusal) ^ set(before)}"
    )

    # The restart half: skew clears, the same command dispatches, and still
    # nothing durable appeared — the cleared skew needed no cleanup either.
    aligned_client = start_env(worker_revision_seam=WORKER_REVISION_A)
    aligned = await run_async("build", "start", str(graph_path))  # type: ignore[operator]
    assert aligned.code == 0, aligned.stderr
    assert len(aligned_client.started) == 1

    after_aligned = _snapshot(watched)
    assert after_aligned == before, (
        "the aligned re-run wrote durable state while clearing the skew — "
        f"residue was minted or cleaned: {set(after_aligned) ^ set(before)}"
    )


async def test_a_fresh_roadmap_run_shows_no_park_residue(
    roadmap_env: object,
    tmp_path: Path,
) -> None:
    """US3-S3: a cleared refusal leaves the next run's parked list empty.

    The park lives in the run chain's own state, carried explicitly across
    continue-as-new — never in a store a fresh run would inherit. The first run
    parks its spec; a fresh run over the same corpus, with the refusal cleared,
    dispatches that spec and parks nothing. An implementation that recorded
    parks durably would leak the first run's refusal into the second.
    """
    refusal = PreflightFinding(
        check="worker-revision",
        passed=False,
        detail=build_module.skew_refusal(WORKER_REVISION_B, CLI_REVISION) or "",
    )

    parked_root = build_corpus(tmp_path / "first", {"001-alpha": dict(state=SpecState.READY)})
    world = RoadmapWorld(preflight=lambda epic_id: [refusal])
    first = await run_to_completion(
        roadmap_env, world, str(parked_root)  # type: ignore[arg-type]
    )
    first_parked = {p.spec_dir: p for p in first.parked}
    assert "001-alpha" in first_parked, (
        f"the refusal was not recorded in the run that made it: {first.parked}"
    )

    # The skew cleared: a fresh run (a new chain, the corpus re-read) dispatches.
    cleared_root = build_corpus(tmp_path / "second", {"001-alpha": dict(state=SpecState.READY)})
    fresh_world = RoadmapWorld()
    second = await run_to_completion(
        roadmap_env, fresh_world, str(cleared_root)  # type: ignore[arg-type]
    )
    assert second.parked == [], (
        f"the fresh run inherited the earlier run's refusal: {second.parked}"
    )
    assert _status_of(second, "001-alpha").landed is True