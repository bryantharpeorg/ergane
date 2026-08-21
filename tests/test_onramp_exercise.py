"""The on-ramp exercise, driven through simulations (061 US4: T027-T030, T032).

`tests/test_live_onramp.py` is the exercise and needs a live GitHub, Temporal
and gateway; this file needs none. It drives that module's orchestration through
a scripted driver and asserts the four properties FR-012 requires, none of which
a green live run shows.

Trap 1 is why the scripted driver writes real files: a test asserting a helper
*returns* paths under the root is a presence test, and would pass against a
`Workspace` that read its runtime root from the environment. So `ScriptedDriver`
creates the artifact each live stage creates, at the paths the workspace names,
and the US4-S5 test asserts the *poisoned* directories are still empty. Trap 14
is why it commits through `tests.target_repo.git`, whose `git_env()` supplies
the identity: a CI runner has none, and this epic has died twice on that.

The per-stage failure messages, the skip transcript and six mutations with what
each turns red are pasted in
`specs/061-the-on-ramp-proves-itself-end-to-end/evidence/us4-onramp-exercise.md`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# The orchestration lives beside the exercise it drives; this file drives the
# same functions offline.
from tests.test_live_onramp import (
    MERGED,
    PullRequest,
    Stage,
    StageFailed,
    Workspace,
    assert_pull_request_landed,
    missing_prerequisites,
    probe_temporal,
    run_exercise,
    skip_message,
)
from tests.target_repo import git

#: Every stage `run_exercise` drives, in order. `Stage.CLEANUP` is not here: it
#: runs on both paths rather than in sequence.
DRIVE_STAGES = (
    Stage.PROVISION,
    Stage.INSTALL,
    Stage.INIT,
    Stage.ONBOARD,
    Stage.DISPATCH,
    Stage.LAND,
)
STAGE_IDS = [stage.value for stage in DRIVE_STAGES]

#: Fixed rather than minted from the clock: a workspace built from the same root
#: twice must be the same workspace.
EPIC_ID = "onramp-exercise"

#: What a successful simulated drive reads back from the forge.
LANDED = PullRequest(
    number=61,
    state=MERGED,
    merged_at="2026-08-21T17:04:11Z",
    url="https://github.com/ergane-scratch/onramp-61/pull/61",
)

#: Where the exercise would write if it read the ambient environment: every one
#: relocates a real Ergane path.
AMBIENT_PATH_VARIABLES = (
    "ERGANE_ROOT",
    "FACTORY_ROOT",
    "ERGANE_STATE_HOME",
    "FACTORY_STATE_HOME",
    "ERGANE_CONFIG_PATH",
    "FACTORY_CONFIG_PATH",
    "ERGANE_PERSONAS_PATH",
    "FACTORY_PERSONAS_PATH",
    "ERGANE_LEDGER_PATH",
    "FACTORY_LEDGER_PATH",
    "ERGANE_VERIFICATION_DB_PATH",
    "FACTORY_VERIFICATION_DB_PATH",
    "XDG_CONFIG_HOME",
    "XDG_STATE_HOME",
    "HOME",
)


class ScriptedDriver:
    """The live driver's shape, writing the live driver's artifacts, offline."""

    def __init__(
        self,
        *,
        fail_at: Stage | None = None,
        cleanup_error: str | None = None,
        pull_request: PullRequest = LANDED,
    ) -> None:
        self.fail_at = fail_at
        self.cleanup_error = cleanup_error
        self.pull_request = pull_request
        #: Stages that ran to completion, and every path they created — so the
        #: US4-S5 assertion reads files rather than a declaration.
        self.ran: list[Stage] = []
        self.wrote: list[Path] = []
        self.cleanups = 0

    def _enter(self, stage: Stage) -> None:
        if self.fail_at is stage:
            raise RuntimeError(f"simulated {stage.value} failure")

    def _write(self, path: Path, text: str = "") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self.wrote.append(path)

    def _mkdir(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        self.wrote.append(path)

    def provision(self, workspace: Workspace) -> None:
        self._enter(Stage.PROVISION)
        self._write(workspace.clone / "README.md", "scratch target\n")
        # Trap 14: the identity comes from `git_env()`, never from the host.
        git(workspace.clone, "init", "-b", "main", "--quiet")
        git(workspace.clone, "add", "-A")
        git(workspace.clone, "commit", "--quiet", "-m", "scratch target repo")
        self.wrote.append(workspace.clone / ".git")
        self.ran.append(Stage.PROVISION)

    def install(self, workspace: Workspace) -> None:
        self._enter(Stage.INSTALL)
        self._write(workspace.answer_file, "version = 1\n")
        self._write(workspace.config_path, "version = 1\n")
        self._write(workspace.personas_path, "implementer: {}\n")
        self.ran.append(Stage.INSTALL)

    def init(self, workspace: Workspace) -> None:
        self._enter(Stage.INIT)
        self._write(workspace.clone / "ergane.yaml", "version: 1\n")
        self._mkdir(workspace.runtime_root)
        self._mkdir(workspace.specs_root)
        self._write(workspace.registry_path, "{}\n")
        self.ran.append(Stage.INIT)

    def onboard(self, workspace: Workspace) -> None:
        self._enter(Stage.ONBOARD)
        self.ran.append(Stage.ONBOARD)

    def dispatch(self, workspace: Workspace) -> int:
        self._enter(Stage.DISPATCH)
        self._write(workspace.spec_dir / "spec.md", "# scratch spec\n")
        self._write(workspace.ledger_path)
        self._write(workspace.verification_db)
        self.ran.append(Stage.DISPATCH)
        return self.pull_request.number

    def land(self, workspace: Workspace, pr_number: int) -> PullRequest:
        self._enter(Stage.LAND)
        assert pr_number == self.pull_request.number
        self.ran.append(Stage.LAND)
        return self.pull_request

    def cleanup(self, workspace: Workspace) -> None:
        self.cleanups += 1
        if self.cleanup_error is not None:
            raise RuntimeError(self.cleanup_error)


@pytest.fixture()
def workspace(tmp_path: Path) -> Workspace:
    """A workspace beneath this test's own temporary root."""
    return Workspace.beneath(tmp_path / "onramp", epic_id=EPIC_ID)


@pytest.fixture()
def poisoned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point every Ergane path variable at a directory the run must not use."""
    poison = tmp_path / "operators-live-store"
    poison.mkdir()
    for name in AMBIENT_PATH_VARIABLES:
        monkeypatch.setenv(name, str(poison / name.lower()))
    return poison


def _satisfied_environment(tmp_path: Path) -> dict[str, str]:
    """An environment in which every prerequisite is present."""
    binaries = tmp_path / "bin"
    binaries.mkdir(parents=True, exist_ok=True)
    for name in ("gh", "claude"):
        stub = binaries / name
        stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        stub.chmod(0o755)
    return {
        "PATH": str(binaries),
        "ERGANE_ONRAMP_ORG": "ergane-scratch",
        "LITELLM_PROXY_URL": "http://127.0.0.1:4000",
        "LITELLM_MASTER_KEY": "sk-not-a-real-key",
        "TEMPORAL_ADDRESS": "127.0.0.1:7233",
        "TEMPORAL_NAMESPACE": "ergane",
    }


def _present(**_: object) -> None:
    return None


# --- T027 / US4-S2: a failure names its stage ---


@pytest.mark.parametrize("stage", DRIVE_STAGES, ids=STAGE_IDS)
def test_a_failure_at_any_stage_is_reported_by_stage_name(
    workspace: Workspace, stage: Stage
) -> None:
    """Each stage fails in turn; the exercise names it and stops."""
    driver = ScriptedDriver(fail_at=stage)

    with pytest.raises(StageFailed) as raised:
        run_exercise(driver, workspace)

    assert raised.value.stage is stage
    assert stage.value in str(raised.value)
    assert f"simulated {stage.value} failure" in str(raised.value)
    assert driver.ran == list(DRIVE_STAGES[: DRIVE_STAGES.index(stage)])
    # FR-012's other half, on the same drive: the scratch repository is
    # destroyed however the run ends, and the interesting leak is the early one
    # — a provision that half-created it and then failed.
    assert driver.cleanups == 1


def test_a_cleanup_failure_is_reported_as_the_cleanup_stage(
    workspace: Workspace,
) -> None:
    """A cleanup that cannot finish is a named failure, not a silence:
    swallowed, it would leak the scratch repository and report success."""
    driver = ScriptedDriver(cleanup_error="scratch repo would not delete")

    with pytest.raises(StageFailed) as raised:
        run_exercise(driver, workspace)

    assert raised.value.stage is Stage.CLEANUP
    assert "scratch repo would not delete" in str(raised.value)


def test_a_cleanup_failure_does_not_hide_the_stage_that_failed(
    workspace: Workspace,
) -> None:
    """When both fail, the drive failure is raised and the cleanup one noted."""
    driver = ScriptedDriver(fail_at=Stage.DISPATCH, cleanup_error="repo still there")

    with pytest.raises(StageFailed) as raised:
        run_exercise(driver, workspace)

    assert raised.value.stage is Stage.DISPATCH
    assert any("repo still there" in note for note in raised.value.__notes__)


# --- T028 / US4-S4: skip, naming what is missing ---


def test_every_missing_prerequisite_is_named_with_its_remedy(tmp_path: Path) -> None:
    """An empty environment yields one named prerequisite per missing thing,
    and the skip message carries them all."""
    missing = missing_prerequisites(
        {"PATH": str(tmp_path / "empty")},
        probe_temporal=lambda address, namespace: "nothing answers",
        probe_gh_auth=lambda: "gh is not authenticated",
        probe_personas=lambda: "personas.yaml still names CHANGEME",
    )

    assert [item.name for item in missing] == [
        "scratch organization",
        "gh",
        "gh authentication",
        "claude",
        "gateway",
        "personas",
        "temporal",
    ]

    message = skip_message(missing)
    assert "on-ramp exercise" in message
    for item in missing:
        assert item.detail, f"prerequisite {item.name} names no remedy"
        assert item.name in message and item.detail in message


def test_a_fully_provisioned_host_is_missing_nothing(tmp_path: Path) -> None:
    """The positive cell (trap 2): a guard that skips everything is not a
    guard."""
    missing = missing_prerequisites(
        _satisfied_environment(tmp_path),
        probe_temporal=lambda address, namespace: None,
        probe_gh_auth=_present,
        probe_personas=_present,
    )

    assert missing == ()


def test_the_temporal_guard_catches_what_the_client_actually_raises(
    tmp_path: Path,
) -> None:
    """Trap 8, executed rather than trusted: a dead port is a `RuntimeError`."""
    reason = probe_temporal("127.0.0.1:1", "default")

    assert reason is not None, "a dead port must be reported, not treated as live"
    assert "127.0.0.1:1" in reason
    assert "RuntimeError" in reason, (
        "the guard reported the failure but not its class; if temporalio has "
        "changed what it raises, this is where the guard finds out"
    )

    # And through the guard the live module actually calls, since a probe that
    # is correct and unreferenced is the shape of every defect this spec repairs.
    environ = _satisfied_environment(tmp_path)
    environ["TEMPORAL_ADDRESS"] = "127.0.0.1:1"
    missing = missing_prerequisites(
        environ, probe_gh_auth=_present, probe_personas=_present
    )
    assert [item.name for item in missing] == ["temporal"]
    assert "127.0.0.1:1" in missing[0].detail


# --- T029 / US4-S5: nothing is written outside its own root ---


def test_the_exercise_writes_nothing_outside_its_own_root(
    workspace: Workspace, poisoned: Path
) -> None:
    """A full drive with every path variable pointing at the operator's store."""
    driver = ScriptedDriver()

    landed = run_exercise(driver, workspace)

    assert landed == LANDED
    assert driver.cleanups == 1
    assert driver.wrote, "the drive wrote nothing, so it asserted nothing"
    for path in driver.wrote:
        assert path.is_relative_to(workspace.root), f"{path} escaped {workspace.root}"
    assert list(poisoned.rglob("*")) == [], (
        f"the exercise wrote into the ambient store: "
        f"{[str(p) for p in poisoned.rglob('*')]}"
    )

    # The declaration matches the drive, and the environment the live run
    # exports for the real CLI verbs relocates every variable under the root: a
    # missing one is a path that run would take from the operator's host.
    environment = workspace.environment()
    for path in workspace.written_paths():
        assert path.is_relative_to(workspace.root)
    for name in AMBIENT_PATH_VARIABLES:
        assert name in environment, f"{name} is not relocated under the root"
        assert Path(environment[name]).is_relative_to(workspace.root)

    # And the workspace is a function of its root alone: rebuilt here, with the
    # poisoned variables still set, it is the same workspace (trap 9).
    assert Workspace.beneath(workspace.root, epic_id=EPIC_ID) == workspace


# --- T030 / spec § Edge Cases: cleanup runs on both paths ---


def test_cleanup_runs_when_the_pull_request_did_not_land(
    workspace: Workspace,
) -> None:
    """The failure this exercise exists to produce still cleans up after itself."""
    driver = ScriptedDriver(
        pull_request=PullRequest(
            number=61, state="OPEN", merged_at=None, url="https://example.invalid/61"
        )
    )

    with pytest.raises(StageFailed) as raised:
        run_exercise(driver, workspace)

    assert raised.value.stage is Stage.LAND
    assert driver.cleanups == 1


# --- T032 / US4-S3: the final assertion is the pull request ---


def test_the_final_assertion_is_the_outcome_not_an_exit_status() -> None:
    """US4-S3, read off the assertion itself: an OPEN pull request whose every
    command exited zero is the run this story exists to turn red, and a
    `MERGED` state with no instant is a label rather than the event `gh pr
    view` reports."""
    assert_pull_request_landed(LANDED)

    with pytest.raises(StageFailed) as open_pr:
        assert_pull_request_landed(
            PullRequest(number=61, state="OPEN", merged_at=None, url="u")
        )
    assert open_pr.value.stage is Stage.LAND
    assert "OPEN" in str(open_pr.value) and MERGED in str(open_pr.value)

    with pytest.raises(StageFailed) as no_instant:
        assert_pull_request_landed(
            PullRequest(number=61, state=MERGED, merged_at=None, url="u")
        )
    assert "merged_at" in str(no_instant.value)

    with pytest.raises(StageFailed) as no_pr:
        assert_pull_request_landed(None)
    assert "no pull request" in str(no_pr.value)
