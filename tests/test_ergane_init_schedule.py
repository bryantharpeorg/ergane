"""034 US6: a joined repo gets a scheduler, not just a worker.

Before this story nothing in `factory/` created a Temporal schedule, so a repo
could be scaffolded, registered, wired and pass `ergane init --check` and still
have no scheduler — flipping a spec to `ready` did nothing, with no error.

Every test drives the *real* lifecycle in `factory.roadmap.schedule` against
`tests.fake_schedules.FakeScheduleServer`; none reaches the operator's control
plane, which holds the live `ergane-roadmap` schedule (plan trap 11).  Two tests
here assert the guards that make that structural rather than customary.

Pasted evidence (constitution VIII / D-037) is at the bottom: the live
transcript, the mutation table, and why three of those mutations first survived.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

import pytest
from temporalio.client import ScheduleOverlapPolicy

import factory.cli.init as init_module
from factory import registry
from factory.cli.errors import EXIT_OK
from factory.roadmap import schedule as sched
from factory.roadmap.schedule import ScheduleUnavailable, schedule_id_for
from factory.roadmap.workflow import roadmap_workflow_id
from factory.verify.factory_yaml import FactoryConfigError, parse_factory_config
from factory.verify.models import RoadmapDials

from tests.fake_schedules import FakeScheduleServer, desired_for, seed
from tests.test_ergane_init import ScriptedPrompter, _git, _invoke
from tests.test_ergane_init_check import bind_offline_seams, make_repo

SLUG = "widgets"
SCHEDULE = schedule_id_for(SLUG)
Init = Callable[..., Any]


@pytest.fixture
def floor(monkeypatch: pytest.MonkeyPatch) -> FakeScheduleServer:
    """Every outward seam bound; the control plane the test may inspect."""
    control_plane = FakeScheduleServer()
    bind_offline_seams(monkeypatch, schedules=control_plane)
    return control_plane


@pytest.fixture
def init(monkeypatch: pytest.MonkeyPatch) -> Init:
    """Run a full `ergane init`, scripting the interview in `_TOP_LEVEL_KEYS` order."""

    def run(repo: Path, *, roadmap: str = "", slug: str = SLUG) -> Any:
        # …, landing_branch, roadmap, forge (049/US5, omitted), template source, slug
        answers = ["1", "bwrap", 'test: "uv run pytest -q"', "", "", "main", roadmap, "", "", "", "", "", slug]
        monkeypatch.setattr(init_module, "_prompter_factory", lambda: ScriptedPrompter(answers))
        return _invoke(["init", str(repo)])

    return run


def bare_repo(tmp_path: Path, name: str = "widgets") -> Path:
    """A git repo with one commit and no Ergane presence at all."""
    repo = tmp_path / name
    (repo / "specs").mkdir(parents=True)
    _git(repo, "init", "-b", "main", "--quiet")
    (repo / "README.md").write_text(f"# {name}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "initial commit")
    return repo


def registered(tmp_path: Path) -> Path:
    repo = make_repo(tmp_path)
    registry.register(SLUG, repo)
    return repo


def cadence(plane: FakeScheduleServer) -> list[float]:
    return [i.every.total_seconds() for i in plane.schedules[SCHEDULE].spec.intervals]


# --- T039 / US6-S1: the schedule exists, and its id distinguishes repos

def test_init_creates_a_schedule_carrying_the_slug_and_this_repos_arguments(
    tmp_path: Path, floor: FakeScheduleServer, init: Init
) -> None:
    """US6-S1, read off the control plane rather than off the command's report."""
    repo = bare_repo(tmp_path)

    result = init(repo)

    assert result.code == EXIT_OK, result.stderr
    # Spelled out, not computed with `schedule_id_for`: as `[SCHEDULE]` this
    # passed with the slug gone from the id, the expectation having moved with
    # the implementation (M2).
    assert list(floor.schedules) == ["ergane-roadmap-widgets"]
    args = floor.arguments(SCHEDULE)
    assert args["specs_root"] == str(repo / "specs")
    assert args["target_repo"] == str(repo)
    assert args["landing_branch"] == "main"
    # Looked before it leapt, and leapt once. (A later `describe` is the check.)
    assert floor.calls[:2] == [("describe", SCHEDULE), ("create", SCHEDULE)]
    assert [c for c in floor.calls if c[0] == "create"] == [("create", SCHEDULE)]
    assert SCHEDULE in result.stdout
    # The workflow it starts keeps the id `factory.roadmap.discovery` matches on,
    # so `ergane roadmap status/pause/resume` find it: a schedule the roadmap
    # verbs cannot see is one nobody can steer.
    assert floor.schedules[SCHEDULE].action.id == roadmap_workflow_id(str(repo / "specs"))
    # And why the id carries the slug: one control plane, many repos.
    assert init(bare_repo(tmp_path, "beta"), slug="beta").code == EXIT_OK
    assert sorted(floor.schedules) == ["ergane-roadmap-beta", "ergane-roadmap-widgets"]


# --- T040 / US6-S2: the dials are declared, and re-running reconciles them

def test_declared_dials_reach_the_schedule_and_a_re_run_reconciles_them(
    tmp_path: Path, floor: FakeScheduleServer, init: Init
) -> None:
    """US6-S2, both halves, on the *live* schedule and never on the manifest."""
    repo = bare_repo(tmp_path)

    first = init(repo, roadmap="{cadence_s: 900, max_concurrent_epics: 3, max_concurrent_nodes: 2}")

    assert first.code == EXIT_OK, first.stderr
    assert cadence(floor) == [900.0]
    assert floor.arguments(SCHEDULE)["max_concurrent_epics"] == 3
    assert floor.arguments(SCHEDULE)["max_concurrent_nodes"] == 2
    # Skip, not buffer: buffering turns a slow epic into an unbounded backlog of
    # duplicate dispatch, one per tick — what a cadence dial makes easiest to
    # cause, and the policy the hand-made live schedule also carries.
    assert floor.schedules[SCHEDULE].policy.overlap is ScheduleOverlapPolicy.SKIP

    second = init(repo, roadmap="{cadence_s: 60, max_concurrent_epics: 4}")

    assert second.code == EXIT_OK, second.stderr
    assert cadence(floor) == [60.0]
    assert floor.arguments(SCHEDULE)["max_concurrent_epics"] == 4
    assert ("update", SCHEDULE) in floor.calls
    assert "reconciled" in second.stdout


def test_the_manifest_parser_types_the_roadmap_dials() -> None:
    """FR-015: declared in the manifest, and `None` when it is not declared."""
    base = "version: 1\nruntime: bwrap\ngates:\n  test: 'true'\n"
    dials = "roadmap:\n  cadence_s: 120\n  max_concurrent_epics: 2\n  max_concurrent_nodes: 3\n"
    assert parse_factory_config(base + dials).roadmap == RoadmapDials(120, 2, 3)
    assert parse_factory_config(base).roadmap is None


@pytest.mark.parametrize(
    "block",
    [
        "roadmap:\n  cadence_s: 0\n",
        "roadmap:\n  cadence_s: '300'\n",
        "roadmap:\n  max_concurrent_epics: true\n",
        "roadmap:\n  max_concurrent_nodes: -1\n",
        "roadmap:\n  cadence: 300\n",
        "roadmap:\n",
    ],
)
def test_a_dial_declared_badly_is_refused_rather_than_guessed(block: str) -> None:
    """Declared means declared — this parser's own rule, applied to the new key."""
    with pytest.raises(FactoryConfigError) as raised:
        parse_factory_config("version: 1\nruntime: bwrap\ngates:\n  test: 'true'\n" + block)
    assert raised.value.rule == "roadmap"


# --- T041 / US6-S3: an unchanged re-run changes nothing

def test_an_unchanged_re_run_reports_already_satisfied_and_changes_nothing(
    tmp_path: Path, floor: FakeScheduleServer, init: Init
) -> None:
    """US6-S3: "changes nothing" compared on the live schedule, not claimed."""
    repo = bare_repo(tmp_path)
    assert init(repo, roadmap="{cadence_s: 600}").code == EXIT_OK
    before = floor.snapshot(SCHEDULE)
    floor.calls.clear()

    result = init(repo, roadmap="{cadence_s: 600}")

    assert result.code == EXIT_OK, result.stderr
    assert floor.snapshot(SCHEDULE) == before
    writes = [call for call in floor.calls if call[0] != "describe"]
    assert writes == [], f"an unchanged re-run wrote to the control plane: {writes}"
    assert "already satisfied" in result.stdout


def test_reconciliation_never_resumes_a_schedule_an_operator_paused(
    tmp_path: Path, floor: FakeScheduleServer
) -> None:
    """Pausing is an operator's act; init reconciles declarations, not dispatch.

    Both paths, because only the second can catch the mistake: a *matching*
    paused schedule is left alone without `update_schedule` ever running, so the
    second half drifts the cadence to force the update and reads the flag back.
    A mutation resuming the schedule survived the first half alone (M8).
    """
    repo = registered(tmp_path)
    seed(floor, desired_for(repo, cadence_s=1800), paused=True)

    matched = sched.apply_schedule(desired_for(repo, cadence_s=1800))

    assert matched.action == "unchanged"
    assert floor.calls == [("describe", SCHEDULE)]

    reconciled = sched.apply_schedule(desired_for(repo, cadence_s=300))

    assert reconciled.action == "updated"
    assert cadence(floor) == [300.0]
    assert floor.schedules[SCHEDULE].state.paused is True, "resumed a paused schedule"


# --- the two guards, and one design claim

def test_the_default_client_refuses_to_connect_from_a_test() -> None:
    """Guard one: no test may open a client onto the operator's control plane."""
    with pytest.raises(ScheduleUnavailable) as raised:
        asyncio.run(sched._default_schedule_client())
    assert "PYTEST_CURRENT_TEST" in str(raised.value)


def test_the_lifecycle_refuses_to_mutate_through_a_real_client(tmp_path: Path) -> None:
    """Guard two, independent of the first (D-045's shape).

    The connect guard is one `if` away from being gone, and when a mutation
    removed it the suite created five schedules on the operator's live namespace
    — `tests/test_ergane_registry.py` drives a full `ergane init` and binds no
    schedule seam, so nothing else stood in the way.  US7 extends this to
    `delete_schedule` when it adds it.
    """
    from temporalio.client import Client

    live = object.__new__(Client)  # a real client, never connected
    desired = desired_for(tmp_path / "widgets")

    for act in (sched.create_schedule(live, desired), sched.update_schedule(live, desired)):
        with pytest.raises(ScheduleUnavailable) as raised:
            asyncio.run(act)
        assert "PYTEST_CURRENT_TEST" in str(raised.value)


def test_the_declared_landing_branch_is_not_a_roadmap_input_field() -> None:
    """Why `landing_branch` rides in the arguments as a declaration only.

    `RoadmapInput` has no such field and the converter drops unknown keys —
    proven, not asserted, because the justification rests on it:
    `roadmap_activities` already derives the branch from the target clone's
    manifest, and a second field would be a second answer to one question.
    """
    from temporalio.converter import default as default_converter

    from factory.roadmap.workflow import RoadmapInput

    converter = default_converter().payload_converter
    payloads = converter.to_payloads(
        [{"specs_root": "/a", "target_repo": "/b", "proxy_url": "u", "landing_branch": "x"}]
    )
    [decoded] = converter.from_payloads(payloads, [RoadmapInput])

    assert isinstance(decoded, RoadmapInput)
    assert not hasattr(decoded, "landing_branch")


# =============================================================================
# Pasted evidence (constitution VIII / D-037): the judge sees this file, never a
# terminal.  Every block below was produced by the command above it.
# =============================================================================
#
# The hand-made schedule this story had to model, read-only:
#
# $ temporal schedule describe --schedule-id ergane-roadmap --namespace factory
#   ScheduleId        ergane-roadmap
#   Action            {"ID":"roadmap-specs","Workflow":"RoadmapWorkflow",
#                      "Args":[{"metadata":{"encoding":"anNvbi9wbGFpbg=="},
#                      "data":"eyJzcGVjc19yb290IjoiL2hvbWUvYWRtaW4vY29kZS9lcmdh..."}],
#                      "TaskQueue":"workgraph", ...}
#   Spec              [{"every":"5m 0s"}]
#   OverlapPolicy     Skip
#   Paused            true
#   ActionCounts      {"Total":150,"MissedCatchupWindow":0,"SkippedOverlap":211}
#
# That `Args` blob is scenario 2's complaint made concrete — the only way to
# change `max_concurrent_epics` on it is to hand-edit a base64 payload.
#
# The production path, in `ergane-us6-scratch`: a namespace created for this
# capture and deleted after it, named on every line so a reader can see it is
# not `factory`.  A throwaway repo, a scratch ERGANE_STATE_HOME, and the real
# `_default_schedule_client` — no seam bound, no pytest sentinel, so this is the
# one path no test can reach.
#
# $ temporal operator namespace create --namespace ergane-us6-scratch --retention 1h
# Namespace ergane-us6-scratch successfully registered.
# $ temporal schedule list --namespace ergane-us6-scratch
#   ScheduleId  Action  Paused  NextRunTime  LastRunTime     (header only: empty)
#
# Scenario 1 — $ printf '<interview>' | TEMPORAL_NAMESPACE=ergane-us6-scratch \
#     ergane init .../demo-app
# schedule: created ergane-roadmap-demo-app — created, starting roadmap-specs
#   every 600s over .../demo-app/specs (note: LITELLM_PROXY_URL is unset, so
#   child epics cannot issue keys)
#
# $ temporal schedule describe --schedule-id ergane-roadmap-demo-app \
#     --namespace ergane-us6-scratch
#   ScheduleId        ergane-roadmap-demo-app
#   Spec              [{"every":"10m 0s"}]
#   OverlapPolicy     Skip
#   Paused            false
#
# Scenario 3 — the same interview again, unchanged:
# schedule: unchanged ergane-roadmap-demo-app — already satisfied; nothing changed
#
# Scenario 2 — re-run declaring {cadence_s: 60, max_concurrent_epics: 5,
# max_concurrent_nodes: 1}:
# schedule: updated ergane-roadmap-demo-app — reconciled to the manifest —
#   cadence_s: schedule has 600, manifest declares 60; max_concurrent_epics:
#   schedule has 2, manifest declares 5; max_concurrent_nodes: schedule has 3,
#   manifest declares 1
#   Spec              [{"every":"1m 0s"}]
#
# and the action's arguments, decoded off the live schedule — scenario 1's three
# facts and scenario 2's dials, in one payload:
#   {"landing_branch":"main","max_concurrent_epics":5,"max_concurrent_nodes":1,
#    "proxy_url":"","specs_root":".../demo-app/specs","target_repo":".../demo-app"}
#
# $ temporal operator namespace delete --namespace ergane-us6-scratch --yes
# Namespace ergane-us6-scratch has been deleted.
#
# Mutations — what would make these tests pass if production did nothing.  One
# change at a time, applied, run, reverted, over tests/{test_ergane_init_schedule,
# test_ergane_init_check,test_factory_yaml,test_ergane_registry}.py.  The whole
# battery runs with TEMPORAL_ADDRESS=127.0.0.1:1, because one row removes the
# guard standing in front of the operator's control plane and the strongest
# mutation against a safety guard is disabling it.  Green unmutated; all red:
#
# M1  apply_schedule never reaches the control plane   4   M10 decode reads handed-in dicts   2
# M2  the schedule id drops the slug                   1   M11 the connect guard removed      1
# M3  the arguments drop landing_branch                3   M12 the mutating-act guard removed 1
# M4  the arguments drop specs_root                    3   M13 init stops creating it         3
# M5  desired_for_repo ignores the dials               1   M14 undeclared parses as defaults  4
# M6  a drifted schedule is never reconciled           2   M15 a bad dial is accepted         4
# M7  every re-run rewrites the schedule               2   M16 the workflow id stops matching 1
# M8  reconciliation resumes a paused schedule         1   M17 the spec ignores the cadence   3
# M9  disagreements never finds anything               2   M18 overlap stops being Skip       1
#
# Three of these SURVIVED a first run — nothing red — and each named a claim no
# test could fail.  They are the reason three assertions above are written the
# way they are:
#
#   M2  the assertion read `== [SCHEDULE]`, and `SCHEDULE` is
#       `schedule_id_for(SLUG)`, so removing the slug from the identifier moved
#       the expectation with the implementation and a schedule id naming no repo
#       at all passed.  It is spelled out as a literal now.  This is its own
#       species of the tests-that-cannot-fail class: not a weak assertion, but
#       one whose expected value is computed by the code under test.
#   M8  the only paused case seeded a schedule that already matched, so `apply`
#       returned `unchanged` and `update_schedule` never ran.  The second half of
#       `test_reconciliation_never_resumes_a_schedule_an_operator_paused` forces
#       the update.
#   M18 nothing read the overlap policy.
#
# What the first battery cost, recorded rather than hidden: M11 was first run
# WITHOUT the closed port.  With the connect guard gone,
# `tests/test_ergane_registry.py` — which drives a full `ergane init` and binds
# no schedule seam — created five unpaused schedules on the operator's live
# `factory` namespace under its own slugs (alpha, beta, myapp, my-app,
# declared), each aimed at a pytest tmp directory that no longer existed.  Every
# tick failed and the operator was paged.  Two things came out of it, both here:
# the battery runs against a closed port, and `_refuse_live_client` is a second
# guard — because a single guard cannot be mutation-proven without a live
# escape, which is the general shape of the hazard and why D-045 asked for
# enforcement at the choke point rather than a convention.
#
# The whole suite, with both guards in place:
#
# $ uv run pytest -q
# 2767 passed, 44 skipped, 4 warnings in 292.81s (0:04:52)
#
# $ temporal schedule list --namespace factory      # after that run
#     ScheduleId                Action              Paused  NextRunTime   LastRunTime
#   ergane-roadmap  {"Workflow":"RoadmapWorkflow"}  true    22 hours ago  1 day ago
#
# One schedule, the operator's, still paused: the suite created nothing.
#
# One flake seen once and not reproduced:
# tests/test_us4_boundary.py::test_hanging_agent_is_killed_at_deadline_with_no_survivors
# failed on an earlier whole-suite run taken immediately after the mutation
# battery and a live capture had loaded the host.  It scans host processes 0.2s
# after a bwrap namespace is torn down.  It passes alone, passes as a module
# three times in a row, and passed on the run above; nothing in this diff is
# reachable from the sandbox boundary.  Recorded rather than hidden.
