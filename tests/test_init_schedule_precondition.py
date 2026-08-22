"""050 US1: `ergane init` never schedules into a control plane that is not there.

Almost everything `ergane init` does is scoped to the repository being joined —
the manifest, the `.gitignore` line, `.ergane/`, the registry row — all local,
reversible, and visible in the working tree.  One act is not: `_schedule`
publishes a recurring job onto a shared Temporal server, and until this story it
was unconditional.  On 2026-08-16 that cost the operator a live
`ergane-roadmap-repo` schedule firing every five minutes at a scratch directory
that no longer existed, created by an `env -i` run of the command the runbook
tells a new user to type first — and created *after* the same run had already
computed and printed the reason it could not work.

So the tests here are about the world rather than about the code: every claim
that no schedule was created is read off the schedule backend's state, never off
a call log (US1-S1, plan trap 3).  "We did not call `apply_schedule`" is a claim
about our own source; "this control plane holds no schedule" is a claim about
the thing that got the operator paged.

Nothing here reaches a real Temporal, and
`test_nothing_in_this_phase_can_reach_a_real_temporal` is the guard on that
rather than a promise: a test that reached a live control plane to prove it did
not schedule would be this spec's own defect wearing a test wrapper.  The
precedent is not hypothetical — five stray schedules were found firing against
pytest temporary directories the same morning, from a mutation that defeated the
guard keeping test runs off the production namespace.

Pasted evidence (constitution VIII / D-037) lives in
`specs/050-init-preconditions/evidence/`: the `env -i` reproduction transcript
against the built wheel (SC-001) and the mutation battery (SC-002).
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from typing import Any, Callable

import pytest

import factory.cli.init as init_module
from factory import registry
from factory.cli.errors import EXIT_OK
from factory.controlplane.resolve import DEFAULT_SOURCE
from factory.env import ERGANE_CONFIG_PATH_ENV, FACTORY_CONFIG_PATH_ENV
from factory.notify.service import (
    DEFAULT_TEMPORAL_NAMESPACE,
    TEMPORAL_ADDRESS_ENV,
    TEMPORAL_NAMESPACE_ENV,
)
from factory.roadmap import schedule as sched
from factory.roadmap.schedule import ScheduleUnavailable, schedule_id_for
from factory.usage.litellm_client import PROXY_URL_ENV

from tests.fake_schedules import FakeScheduleServer
from tests.test_ergane_init import ScriptedPrompter, _git, _invoke
from tests.test_ergane_init_check import bind_offline_seams

SLUG = "widgets"
SCHEDULE = schedule_id_for(SLUG)
Init = Callable[..., Any]

#: A control-plane config that parses.  The Temporal it declares is a name that
#: does not resolve, so a mutation that got past both isolation guards would
#: fail DNS rather than find this host's live control plane.
READABLE_CONFIG = """\
version = 1

[llm]
mode = "gateway"
base_url = "http://litellm.invalid"
master_key_env = "LITELLM_MASTER_KEY"

[memory]
backend = "none"

[temporal]
mode = "external"
address = "control-plane.invalid:7233"
namespace = "declared-by-the-config"

[telemetry]

[escalation]
adapter = "telegram"
chat_id_env = "TELEGRAM_CHAT_ID"
bot_token_env = "TELEGRAM_BOT_TOKEN"
"""


# --- the two states of a control plane, and a repository to join --------------


def readable_control_plane(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, text: str = READABLE_CONFIG
) -> Path:
    """Point the config path at a file holding `text`."""
    path = tmp_path / "control-plane" / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    monkeypatch.setenv(ERGANE_CONFIG_PATH_ENV, str(path))
    monkeypatch.setenv(FACTORY_CONFIG_PATH_ENV, str(path))
    return path


def no_control_plane(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the config path at a file that is not there — the reproduction's state.

    This is what `env -i` on a fresh machine produces: `ergane install` has never
    run, so there is no `config.toml` to read.
    """
    path = tmp_path / "control-plane" / "absent.toml"
    monkeypatch.setenv(ERGANE_CONFIG_PATH_ENV, str(path))
    monkeypatch.setenv(FACTORY_CONFIG_PATH_ENV, str(path))
    return path


def bare_repo(tmp_path: Path, name: str = "widgets") -> Path:
    """A git repo with one commit and no Ergane presence at all."""
    repo = tmp_path / name
    (repo / "specs").mkdir(parents=True)
    _git(repo, "init", "-b", "main", "--quiet")
    (repo / "README.md").write_text(f"# {name}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "initial commit")
    return repo


@pytest.fixture
def floor(monkeypatch: pytest.MonkeyPatch) -> FakeScheduleServer:
    """Every outward seam bound; the control plane these tests may inspect.

    Two variables the operator's own shell exports are removed, because the
    reported schedule line is pinned byte for byte below and both of them steer
    it: `LITELLM_PROXY_URL` decides the trailing note, and `TEMPORAL_NAMESPACE`
    decides which namespace the refusal names.  `TEMPORAL_ADDRESS` is
    deliberately *left alone* — a battery is run against a closed port, and a
    fixture that deleted it would hand a mutant this host's default instead.
    """
    control_plane = FakeScheduleServer()
    bind_offline_seams(monkeypatch, schedules=control_plane)
    monkeypatch.delenv(PROXY_URL_ENV, raising=False)
    monkeypatch.delenv(TEMPORAL_NAMESPACE_ENV, raising=False)
    return control_plane


@pytest.fixture
def init(monkeypatch: pytest.MonkeyPatch) -> Init:
    """Run a full `ergane init`, scripting the interview in `_TOP_LEVEL_KEYS` order."""

    def run(repo: Path, *, slug: str = SLUG) -> Any:
        # …, landing_branch, roadmap, forge (049/US5, omitted), slug
        answers = ["1", "bwrap", 'test: "uv run pytest -q"', "", "", "main", "", "", "", slug]
        monkeypatch.setattr(init_module, "_prompter_factory", lambda: ScriptedPrompter(answers))
        return _invoke(["init", str(repo)])

    return run


def schedule_line(stdout: str) -> str:
    """The one line init reports about the schedule."""
    lines = [line for line in stdout.splitlines() if line.startswith("schedule: ")]
    assert len(lines) == 1, f"expected exactly one schedule line, got {lines}"
    return lines[0]


# --- T001 / US1-S1: the backend holds no schedule -----------------------------


def test_no_schedule_is_created_when_the_control_plane_cannot_be_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, floor: FakeScheduleServer, init: Init
) -> None:
    """US1-S1, and the whole production incident.

    The assertion is `floor.schedules == {}` — the backend's state — and not
    "`apply_schedule` was not called".  The backend here is one that *would*
    have accepted the create: `FakeScheduleServer` stores whatever it is given,
    so deleting the precondition from `init.py` turns this red rather than
    leaving it green against a stand-in that would have refused anyway.
    """
    repo = bare_repo(tmp_path)
    no_control_plane(monkeypatch, tmp_path)

    result = init(repo)

    assert result.code == EXIT_OK, result.stderr
    assert floor.schedules == {}, f"a schedule was published: {list(floor.schedules)}"
    # Supporting, never load-bearing: the state above is the claim.  Writes
    # only — the readiness report `init` ends with still *describes* the
    # schedule to judge it, which is a read, predates this story, and is not
    # what FR-001 forbids.  Asserting no call at all would make this test fail
    # for a reason that has nothing to do with the precondition.
    writes = [call for call in floor.calls if call[0] != "describe"]
    assert writes == [], f"the control plane was written to: {writes}"


# --- T002 / US1-S1, FR-003: the line names the cause, the remedy and where ----


def test_the_refusal_names_the_control_plane_the_remedy_and_the_namespace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, floor: FakeScheduleServer, init: Init
) -> None:
    """FR-003, plus plan trap 9.

    Three claims, and the third is the one that is easy to leave out.  A
    *reachable* control plane is not the same as the *operator's* control plane:
    this story only checks the first, so on a machine already running Temporal
    the refusal never fires and a schedule lands in whichever namespace the
    fallback picked.  Naming the namespace and the source that chose it is what
    lets the next reader see a mismatch instead of a bare success — `built-in
    default` means nobody chose it.
    """
    repo = bare_repo(tmp_path)
    no_control_plane(monkeypatch, tmp_path)

    line = schedule_line(init(repo).stdout)

    assert line.startswith(f"schedule: failed {SCHEDULE} — "), line
    assert "control plane" in line, line
    assert "`ergane install`" in line, line
    assert f"namespace '{DEFAULT_TEMPORAL_NAMESPACE}'" in line, line
    assert DEFAULT_SOURCE in line, line
    # The cause, in the vocabulary `run_check` already renders it in.
    assert "ControlPlaneConfigError" in line, line


# --- T003 / US1-S2, FR-004: everything repository-scoped is untouched ---------


def test_the_refusal_costs_the_repository_none_of_its_local_scaffold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, floor: FakeScheduleServer, init: Init
) -> None:
    """US1-S2: the precondition is scoped to the one act that leaves the repo.

    Proven by joining two repositories with the same answers — one with a
    readable control plane, one without — and comparing what each was left
    with.  "Exactly as they are today" needs something to be exactly *like*, and
    a second repository is the only such thing a committed test can hold: the
    judge sees this diff and no base tree (constitution VIII).
    """
    refused = bare_repo(tmp_path, "refused")
    allowed = bare_repo(tmp_path, "allowed")

    no_control_plane(monkeypatch, tmp_path)
    first = init(refused, slug="refused")
    readable_control_plane(monkeypatch, tmp_path)
    second = init(allowed, slug="allowed")

    assert first.code == EXIT_OK, first.stderr
    assert second.code == EXIT_OK, second.stderr
    # The one act that differs, and only it.
    assert schedule_line(first.stdout).startswith(f"schedule: failed ergane-roadmap-refused")
    assert schedule_line(second.stdout).startswith("schedule: created ergane-roadmap-allowed")

    for name in ("ergane.yaml", ".gitignore"):
        assert (refused / name).read_text(encoding="utf-8") == (
            allowed / name
        ).read_text(encoding="utf-8"), f"{name} differs under a refused schedule"
    assert (refused / "ergane.yaml").read_text(encoding="utf-8").strip() != ""
    assert ".ergane/" in (refused / ".gitignore").read_text(encoding="utf-8")
    assert (refused / ".ergane").is_dir()

    entry = registry.load_registry().get("refused")
    assert entry is not None and Path(entry.path) == refused


# --- T004 / US1-S3, FR-005: a readable control plane schedules as it does today


def test_a_readable_control_plane_creates_the_schedule_and_reports_it_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, floor: FakeScheduleServer, init: Init
) -> None:
    """US1-S3 — the scenario that stops this story being satisfied by not scheduling.

    The expected line is spelled out rather than built with `format_step` and
    `schedule_id_for`.  034's own battery recorded why: an assertion written as
    `== [SCHEDULE]` passed with the slug gone from the identifier, because the
    expectation moved with the implementation.  An expected value computed by
    the code under test cannot fail.
    """
    repo = bare_repo(tmp_path)
    readable_control_plane(monkeypatch, tmp_path)

    result = init(repo)

    assert result.code == EXIT_OK, result.stderr
    assert schedule_line(result.stdout) == (
        "schedule: created ergane-roadmap-widgets — created, starting "
        f"roadmap-specs every 300s over {repo / 'specs'} "
        "(note: LITELLM_PROXY_URL is unset, so child epics cannot issue keys)"
    )
    assert list(floor.schedules) == ["ergane-roadmap-widgets"]
    args = floor.arguments("ergane-roadmap-widgets")
    assert args["specs_root"] == str(repo / "specs")
    assert args["target_repo"] == str(repo)
    assert args["landing_branch"] == "main"


# --- T005 / US1-S5, FR-002: configured but unreachable refuses, never raises ---


def test_a_configured_but_unreachable_control_plane_fails_the_step_without_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, floor: FakeScheduleServer, init: Init
) -> None:
    """US1-S5: *refusing* and *crashing* are different outcomes.

    Configured but unreachable is a different case from not configured, and it
    is the one a new precondition most easily turns into a crash — the config
    reads fine, so the guard passes, and the failure arrives from the network
    instead.  `_schedule` promises never to raise (FR-017) because init depends
    on it: a control plane that is down must not cost the repository its
    scaffold.
    """
    repo = bare_repo(tmp_path)
    readable_control_plane(monkeypatch, tmp_path)

    async def unreachable() -> Any:
        raise ScheduleUnavailable("cannot reach Temporal at control-plane.invalid:7233")

    monkeypatch.setattr(sched, "_schedule_client_factory", unreachable)

    result = init(repo)

    assert result.code == EXIT_OK, result.stderr
    line = schedule_line(result.stdout)
    assert line.startswith(f"schedule: failed {SCHEDULE} — "), line
    assert "cannot reach Temporal at control-plane.invalid:7233" in line, line
    assert floor.schedules == {}
    # The scaffold survived the unreachable control plane, which is what FR-017
    # bought and what this precondition must not take back.
    assert (repo / "ergane.yaml").is_file() and (repo / ".ergane").is_dir()


def test_a_control_plane_config_that_will_not_parse_fails_the_step_without_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, floor: FakeScheduleServer, init: Init
) -> None:
    """The second half of "configured but unreachable", and the sharper half.

    A *broken* config is not a missing one: the resolver that answers "which
    Temporal would this have reached" refuses outright on a config it cannot
    use, so a refusal message that asks it the question without guarding the
    answer raises out of a function whose docstring says it never does — and
    takes the operator's scaffold with it.
    """
    repo = bare_repo(tmp_path)
    readable_control_plane(monkeypatch, tmp_path, text="this is not TOML at [all\n")

    result = init(repo)

    assert result.code == EXIT_OK, result.stderr
    line = schedule_line(result.stdout)
    assert line.startswith(f"schedule: failed {SCHEDULE} — "), line
    assert "control plane" in line and "`ergane install`" in line, line
    assert floor.schedules == {}


# --- T006: the anti-vacuity guard for plan trap 4 -----------------------------


def test_nothing_in_this_phase_can_reach_a_real_temporal() -> None:
    """Plan trap 4, asserted rather than promised.

    Two independent claims.  First, no test in this module hands Temporal an
    address or a namespace: the seam here is a code seam
    (`_schedule_client_factory`), and a test that needed `TEMPORAL_ADDRESS` set
    to run would be one connection away from the operator's control plane.
    Deleting those variables is allowed and done — it is the direction that
    narrows the blast radius; setting them is what this forbids.

    Second, the production connect path refuses under `PYTEST_CURRENT_TEST` at
    all, so the protection does not depend on this module remembering to bind
    anything.  Both are needed: the first can be satisfied by a module that
    binds nothing, and the second by one that sets the address and binds
    nothing.
    """
    module = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    banned = {TEMPORAL_ADDRESS_ENV, TEMPORAL_NAMESPACE_ENV}
    declared: list[str] = []
    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, "attr", "") not in {"setenv", "putenv"}:
            continue
        first = node.args[0] if node.args else None
        if isinstance(first, ast.Constant) and first.value in banned:
            declared.append(str(first.value))
        # `monkeypatch.setenv(TEMPORAL_ADDRESS_ENV, …)` reads as a Name, and the
        # constant form is the one nobody would write; both are refused.
        if isinstance(first, ast.Name) and first.id in {
            "TEMPORAL_ADDRESS_ENV",
            "TEMPORAL_NAMESPACE_ENV",
        }:
            declared.append(first.id)
    assert declared == [], f"this phase points a test at a Temporal: {declared}"

    with pytest.raises(ScheduleUnavailable) as raised:
        asyncio.run(sched._default_schedule_client())
    assert "PYTEST_CURRENT_TEST" in str(raised.value)


# --- T010 / FR-010: no flag may turn scheduling off ---------------------------


def test_init_gains_no_flag_that_disables_scheduling() -> None:
    """FR-010: the precondition is a fact about the environment, not a preference.

    An opt-out would be the first thing a runbook told people to paste, and the
    incident this spec exists for would come back through it wearing an operator's
    consent.  Asserted against the parser's real option strings, so adding the
    flag anywhere in the interview or the command line trips this.
    """
    import argparse

    parser = argparse.ArgumentParser()
    init_module.add_init_parser(parser.add_subparsers(dest="command"))

    options = {
        option
        for action in parser._subparsers._group_actions[0].choices["init"]._actions
        for option in action.option_strings
    }
    forbidden = [
        option
        for option in options
        if "schedul" in option or "roadmap" in option or option in {"--no-wire", "--local"}
    ]
    assert forbidden == [], f"init grew a scheduling opt-out: {forbidden}"
