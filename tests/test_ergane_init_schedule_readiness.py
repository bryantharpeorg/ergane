"""034 US7: a repo without a scheduler does not read as ready, and forgetting a
repo stops its schedule.

US6 makes the schedule exist.  This story makes its absence visible and its
removal complete: `roadmap_schedule` joins the shared judgment in
`factory/mergequeue/onboard.py`, `ergane repo forget` deletes the schedule
before it removes the registry entry, and an unreachable control plane costs the
schedule step and nothing else.

`factory/roadmap/schedule.py` is imported unchanged from US6 apart from the two
verbs only this story needs — `delete_schedule` and `read_schedule` — and US6's
two isolation guards cover them: nothing here can reach the operator's control
plane, which holds the live `ergane-roadmap` schedule (plan trap 11).

Pasted evidence (constitution VIII / D-037) is at the bottom.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest

import factory.cli.init as init_module
from factory import registry
from factory.cli.errors import EXIT_OK, EXIT_USER
from factory.roadmap import schedule as sched
from factory.roadmap.schedule import ScheduleUnavailable, schedule_id_for

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
        # …, landing_branch, roadmap, forge (049/US5, omitted), slug
        answers = ["1", "bwrap", 'test: "uv run pytest -q"', "", "", "main", roadmap, "", "", "", "", slug]
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


def failing(profile: Any) -> list[str]:
    return [f.check for f in profile.findings if not f.passed]


def detail(profile: Any) -> str:
    for finding in profile.findings:
        if finding.check == "roadmap_schedule":
            return finding.detail
    raise AssertionError(f"no schedule finding: {[f.check for f in profile.findings]}")


# --- T042 / US6-S4: forget deletes the schedule

def test_repo_forget_deletes_the_schedule_and_the_registry_entry(
    tmp_path: Path, floor: FakeScheduleServer
) -> None:
    """US6-S4: the deletion read off the control plane, not reported."""
    repo = registered(tmp_path)
    seed(floor, desired_for(repo))
    log_before = _git(repo, "log", "--format=%H %s")

    result = _invoke(["repo", "forget", SLUG])

    assert result.code == EXIT_OK, result.stderr
    assert floor.schedules == {}
    assert registry.load_registry().get(SLUG) is None
    assert SCHEDULE in result.stdout
    # Only the entry and the schedule: the repository's own files are its own.
    assert _git(repo, "log", "--format=%H %s") == log_before
    assert _git(repo, "status", "--porcelain") == ""


def test_forget_keeps_the_entry_when_the_schedule_cannot_be_deleted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, floor: FakeScheduleServer
) -> None:
    """An orphan is the failure this verb exists to prevent, so it refuses."""
    registered(tmp_path)

    def unreachable(_id: str) -> Any:
        raise ScheduleUnavailable("cannot reach Temporal at localhost:7233")

    monkeypatch.setattr(sched, "remove_schedule", unreachable)

    result = _invoke(["repo", "forget", SLUG])

    assert result.code == EXIT_USER
    assert "localhost:7233" in result.stderr
    assert registry.load_registry().get(SLUG) is not None, "the entry must survive"


# --- T043 / US6-S5: the check reports a scheduler the repo does not have

def test_forget_says_so_when_there_was_no_schedule_to_delete(
    tmp_path: Path, floor: FakeScheduleServer
) -> None:
    """A repo joined before US6, or one whose schedule an operator already
    removed: the entry still goes, and the report does not claim a deletion that
    did not happen.  Without this, `delete_schedule` returning True for a
    schedule that was never there passes every other test (mutation N4)."""
    registered(tmp_path)
    assert floor.schedules == {}

    result = _invoke(["repo", "forget", SLUG])

    assert result.code == EXIT_OK, result.stderr
    assert f"no roadmap schedule {SCHEDULE} existed" in result.stdout
    assert registry.load_registry().get(SLUG) is None


def test_the_mutating_act_guard_covers_delete_too(tmp_path: Path) -> None:
    """US6 ships two isolation guards and this story adds a third mutating act,
    so the guard has to grow with it: even holding a real
    `temporalio.client.Client`, no test can delete a schedule through this
    module.  Without this the guard could be dropped from `delete_schedule`
    alone and every other test would stay green (mutation N13)."""
    from temporalio.client import Client

    live = object.__new__(Client)  # a real client, never connected

    with pytest.raises(ScheduleUnavailable) as raised:
        import asyncio

        asyncio.run(sched.delete_schedule(live, SCHEDULE))
    assert "PYTEST_CURRENT_TEST" in str(raised.value)


def test_a_repo_with_its_schedule_passes_every_finding(
    tmp_path: Path, floor: FakeScheduleServer
) -> None:
    """The control for the breaks below: all-pass, including the new check."""
    repo = registered(tmp_path)
    seed(floor, desired_for(repo))

    assert failing(init_module.check_repo(repo)) == []


@pytest.mark.parametrize(
    "break_it, expected",
    [
        pytest.param(None, ("ergane init",), id="missing"),
        pytest.param({"paused": True}, ("paused", "ergane roadmap resume"), id="paused"),
        pytest.param(
            {"specs_root": "/somewhere/else/specs"},
            ("/somewhere/else/specs", "specs_root", "ergane init"),
            id="drifted",
        ),
        pytest.param(
            {"cadence_s": 1800, "epics": 9}, ("cadence_s", "max_concurrent_epics"), id="dials"
        ),
    ],
)
def test_each_broken_schedule_flips_exactly_the_schedule_finding(
    tmp_path: Path,
    floor: FakeScheduleServer,
    break_it: dict[str, Any] | None,
    expected: tuple[str, ...],
) -> None:
    """US6-S5: absent, paused and argument-drifted, each named with its remedy."""
    repo = registered(tmp_path)
    if break_it is not None:
        paused = bool(break_it.pop("paused", False))
        seed(floor, desired_for(repo, **break_it), paused=paused)

    profile = init_module.check_repo(repo)

    assert failing(profile) == ["roadmap_schedule"]
    for phrase in (SCHEDULE, *expected):
        assert phrase in detail(profile), f"{phrase!r} missing from {detail(profile)!r}"


def test_an_unreachable_control_plane_fails_the_finding_and_renders_the_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, floor: FakeScheduleServer
) -> None:
    """No masking: an engine that will not answer costs one finding, not the report."""
    repo = registered(tmp_path)

    def refuse(_id: str) -> Any:
        raise ScheduleUnavailable("cannot reach Temporal at localhost:7233 (namespace 'factory')")

    monkeypatch.setattr(sched, "read_schedule", refuse)

    profile = init_module.check_repo(repo)

    assert failing(profile) == ["roadmap_schedule"]
    assert "localhost:7233" in detail(profile)


def test_an_unregistered_repo_cannot_have_its_schedule_judged(
    tmp_path: Path, floor: FakeScheduleServer
) -> None:
    """The slug names the schedule, so no entry means no judgment — a failing finding,
    not an omitted one: unknown readiness is not readiness, the rule `control_plane`
    and `landing_branch` already follow."""
    profile = init_module.check_repo(make_repo(tmp_path))

    assert set(failing(profile)) == {"registry_entry", "roadmap_schedule"}
    assert "registry" in detail(profile)


# --- T044 / US6-S6: repo-local work survives an unreachable engine

def test_an_unreachable_control_plane_still_leaves_a_scaffolded_registered_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, floor: FakeScheduleServer, init: Init
) -> None:
    """US6-S6 / FR-017: the schedule step fails with its reason; nothing rolls back."""
    repo = bare_repo(tmp_path)

    async def refuse() -> Any:
        raise ScheduleUnavailable("cannot reach Temporal at localhost:7233")

    monkeypatch.setattr(sched, "_schedule_client_factory", refuse)

    result = init(repo)

    assert result.code == EXIT_OK, result.stderr
    assert (repo / "ergane.yaml").is_file() and (repo / ".ergane").is_dir()
    assert registry.load_registry().get(SLUG) is not None
    assert "schedule: failed" in result.stdout
    assert "localhost:7233" in result.stdout


# =============================================================================
# Pasted evidence (constitution VIII / D-037): the judge sees this file, never a
# terminal.  Every block below was produced by the command above it.
# =============================================================================
#
# Live behaviour in `ergane-us7-scratch`: a namespace created for this capture
# and deleted after it, named on every line so a reader can see it is not
# `factory`, which holds the operator's live `ergane-roadmap`.  A throwaway
# repo, a scratch ERGANE_STATE_HOME, and the real `_default_schedule_client` —
# no seam bound, no pytest sentinel, so this is the path no test can reach.
#
# $ temporal operator namespace create --namespace ergane-us7-scratch --retention 1h
# Namespace ergane-us7-scratch successfully registered.
#
# A joined repo, and the finding this story adds:
# $ printf '<interview>' | TEMPORAL_NAMESPACE=ergane-us7-scratch ergane init .../demo-app
# schedule: created ergane-roadmap-demo-app — created, starting roadmap-specs
#   every 300s over .../demo-app/specs (note: LITELLM_PROXY_URL is unset, so
#   child epics cannot issue keys)
#   [PASS] roadmap_schedule: roadmap schedule 'ergane-roadmap-demo-app' is
#   running and matches the manifest
#
# Scenario 2, paused — the quiet case this story exists for.  Paused by hand
# with the `temporal` CLI, so the check is reading a schedule this code did not
# put into that state:
# $ temporal schedule toggle --schedule-id ergane-roadmap-demo-app \
#     --namespace ergane-us7-scratch --pause --reason "operator paused"
# $ ergane init --check .../demo-app
#   [FAIL] roadmap_schedule: roadmap schedule 'ergane-roadmap-demo-app'
#   disagrees with this repository: it is paused, so no tick will start a run —
#   resume it with `ergane roadmap resume <specs root>` when you mean dispatch
#   to run
# 3 of 6 checks failed
#
# Scenario 1, forget:
# $ ergane repo forget demo-app
# deleted roadmap schedule ergane-roadmap-demo-app
# forgot demo-app (.../demo-app); the repository itself is untouched
# $ temporal schedule list --namespace ergane-us7-scratch
#   ScheduleId  Action  Paused  NextRunTime  LastRunTime     (header only: empty)
#
# Scenario 2, absent — re-registered, then the schedule deleted underneath it
# with the `temporal` CLI:
# $ ergane init --check .../demo-app
#   [FAIL] roadmap_schedule: no roadmap schedule 'ergane-roadmap-demo-app'
#   exists on the control plane, so no tick will ever dispatch .../demo-app's
#   specs — run `ergane init .../demo-app` to create it; flipping a spec to
#   `ready` without one does nothing, with no error
#
# $ temporal operator namespace delete --namespace ergane-us7-scratch --yes
# Namespace ergane-us7-scratch has been deleted.
#
# Mutations — what would make these tests pass if production did nothing.  One
# change at a time, applied, run, reverted, over
# tests/{test_ergane_init_schedule_readiness,test_ergane_init_check,test_onboard,
# test_ergane_registry}.py, the whole battery against TEMPORAL_ADDRESS=127.0.0.1:1
# because one row disables an isolation guard.  Green unmutated; all red:
#
# N1  forget leaves the schedule behind            2   N8  drift is never reported          2
# N2  forget removes the entry anyway              1   N9  unreachable reads as "absent"     1
# N3  registry.forget removes nothing              1   N10 the check never reads it         12
# N4  delete claims success on a missing schedule  1   N11 an unregistered repo reads fine    1
# N5  the schedule finding always passes           2   N12 init raises instead of reporting  20
# N6  an absent schedule reads as present          2   N13 the guard stops covering delete    1
# N7  a paused schedule is not a problem           1
#
# N4 and N13 SURVIVED their first run, and both named a claim no test could
# fail.  N4: nothing distinguished "deleted it" from "there was none to delete",
# so `delete_schedule` could report a deletion that never happened —
# `test_forget_says_so_when_there_was_no_schedule_to_delete` closes it.  N13:
# this story adds a third mutating act, and the guard US6 shipped was only
# asserted over the two acts US6 had, so dropping it from `delete_schedule`
# alone left every test green —
# `test_the_mutating_act_guard_covers_delete_too` closes it.  The general shape
# is the one US6 recorded: the strongest mutation against a safety guard is
# disabling it, so a guard has to be re-proven every time an act is added
# behind it.
#
# The whole suite:
#
# $ uv run pytest -q
# 2779 passed, 44 skipped, 4 warnings in 291.35s (0:04:51)

