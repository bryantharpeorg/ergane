"""082-US2: `ergane worker deploy` — new code on the floor, old code untouched.

Every claim here is about what `deploy` *issued* and what it reported. Nothing
reaches the host: the runner is a fake modelling a plausible operator machine
(a git checkout, a systemd session, `uv`), and the Temporal seam is a fake
deployment directory whose versions appear when a unit that would register them
has been started. Both are recorders, because most of what this story promises
is about *which* commands ran and in what order — a refusal that has already
created a checkout is not a refusal, and a `set-current` issued before the
worker registered is the failure plan trap 7 names.

Written before `factory/supervision/deploy.py` existed, and failing at
collection:

    $ PYTHONDONTWRITEBYTECODE=1 uv run pytest -q tests/test_worker_deploy.py --no-header
    tests/test_worker_deploy.py:31: in <module>
        from factory.supervision.deploy import (
    E   ModuleNotFoundError: No module named 'factory.supervision.deploy'
    1 error in 0.09s
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator, Sequence

import pytest

from factory.cli.errors import OperatorError
from factory.locking import exclusive_lock
from factory.supervision.deploy import (
    DeploymentSnapshot,
    DeploymentsUnavailable,
    DeployReport,
    VersionState,
    deploy,
    deploy_lock_target,
)
from factory.supervision.units import (
    WORKER_TEMPLATE_UNIT,
    CommandResult,
    InstallLayout,
    instance_build_id,
    worker_instance,
)

#: The revision the fake host has committed, and the build id it shortens to.
HEAD_SHA = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
HEAD_SHORT = "a1b2c3d"

#: What was on the floor before this deploy.
OLD_SHORT = "9f8e7d6"


# --- fakes ------------------------------------------------------------------


class FakeHost:
    """One operator machine: a checkout, a systemd session, `uv`, `git`.

    Answers only the commands `deploy` is allowed to run, and records every
    one. Anything else raises rather than returning a silent zero, so a command
    added to the engine without a rule here is visible immediately.
    """

    def __init__(
        self,
        *,
        checkout: bool = True,
        dirty: bool = False,
        systemd: bool = True,
        revisions: Sequence[str] = ("HEAD",),
    ) -> None:
        self.checkout = checkout
        self.dirty = dirty
        self.systemd = systemd
        self.revisions = {name: HEAD_SHA for name in revisions}
        self.calls: list[tuple[str, ...]] = []
        self.units: set[str] = set()

    def __call__(
        self, argv: Sequence[str], *, cwd: Path | None = None
    ) -> CommandResult:
        args = tuple(argv)
        self.calls.append(args)
        if args[0] == "git":
            return self._git(args)
        if args[0] == "uv":
            return CommandResult(0)
        if args[0] == "systemctl":
            return self._systemctl(args)
        raise AssertionError(f"deploy ran a command this host has no rule for: {args}")

    def _git(self, args: tuple[str, ...]) -> CommandResult:
        if args[1:] == ("rev-parse", "--git-dir"):
            return CommandResult(0, ".git") if self.checkout else CommandResult(128)
        if args[1:] == ("status", "--porcelain"):
            return CommandResult(0, " M factory/worker.py" if self.dirty else "")
        if args[1:3] == ("rev-parse", "--verify"):
            wanted = args[-1].removesuffix("^{commit}")
            resolved = self.revisions.get(wanted)
            return CommandResult(0, resolved) if resolved else CommandResult(128)
        if args[1:3] == ("rev-parse", "--short"):
            return CommandResult(0, args[-1][:7])
        if args[1:4] == ("worktree", "add", "--detach"):
            tree = Path(args[4])
            (tree / ".venv/bin").mkdir(parents=True)
            (tree / ".venv/bin/python3").touch()
            return CommandResult(0)
        raise AssertionError(f"unexpected git command: {args}")

    def _systemctl(self, args: tuple[str, ...]) -> CommandResult:
        if not self.systemd:
            return CommandResult(1, "Failed to connect to bus: No medium found")
        verb, name = args[2], args[-1]
        if verb == "show":
            return CommandResult(0, "Version=255")
        if verb == "enable":
            self.units.add(name)
            return CommandResult(0)
        if verb == "is-active":
            live = name in self.units
            return CommandResult(0 if live else 3, "active" if live else "inactive")
        raise AssertionError(f"unexpected systemctl command: {args}")

    @property
    def mutations(self) -> list[tuple[str, ...]]:
        """Every call that changed something — what a refusal must leave empty.

        Read-only `git` questions are not mutations; `git worktree add`, `uv`
        and every `systemctl` verb but the session probe are.
        """
        return [
            call
            for call in self.calls
            if call[:2] == ("git", "worktree")
            or call[0] == "uv"
            or (call[0] == "systemctl" and call[2] != "show")
        ]


class FakeDeployments:
    """The deployment directory the server keeps, as `deploy` reads it.

    A version appears here `registers_after` snapshots after the unit that
    would register it was started — which is the real sequence (a worker
    registers when it has finished booting), and the reason the wait is
    bounded rather than assumed.
    """

    def __init__(
        self,
        host: FakeHost | None = None,
        *,
        current: str | None = OLD_SHORT,
        versions: dict[str, str] | None = None,
        registers_after: int = 1,
        available: bool = True,
    ) -> None:
        self.host = host
        self.current = current
        self.versions = {OLD_SHORT: "current"} if versions is None else dict(versions)
        self.registers_after = registers_after
        self.available = available
        self.snapshots = 0
        self.set_calls: list[str] = []
        self.started_at: dict[str, int] = {}

    def snapshot(self) -> DeploymentSnapshot:
        if not self.available:
            raise DeploymentsUnavailable("localhost:7233", "connection refused")
        self.snapshots += 1
        for unit in sorted(self.host.units if self.host else ()):
            build_id = instance_build_id(unit)
            first = self.started_at.setdefault(build_id, self.snapshots)
            if self.snapshots - first >= self.registers_after:
                self.versions.setdefault(build_id, "inactive")
        return DeploymentSnapshot(
            current=self.current,
            versions=tuple(
                VersionState(build_id, state)
                for build_id, state in sorted(self.versions.items())
            ),
        )

    def set_current(self, build_id: str) -> None:
        assert build_id in self.versions, "set-current before the worker registered"
        self.set_calls.append(build_id)
        if self.current is not None and self.current != build_id:
            self.versions[self.current] = "draining"
        self.current = build_id
        self.versions[build_id] = "current"


class FakeClock:
    """A monotonic clock that moves only when the caller sleeps."""

    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def layout(tmp_path: Path) -> Iterator[InstallLayout]:
    """An installed host: every root under `tmp_path`, template unit written."""
    home = tmp_path / "home"
    interpreter = home / "code/ergane/.venv/bin/python3"
    interpreter.parent.mkdir(parents=True)
    interpreter.touch()
    unit_dir = home / ".config/systemd/user"
    unit_dir.mkdir(parents=True)
    (unit_dir / WORKER_TEMPLATE_UNIT).write_text("[Service]\n", encoding="utf-8")
    yield InstallLayout(
        install_root=home / "code/ergane",
        interpreter=interpreter,
        unit_dir=unit_dir,
        generated_dir=home / ".local/state/ergane/supervision",
    )


def test_a_host_without_the_versioned_template_is_refused_by_name(
    layout: InstallLayout,
) -> None:
    """The instance is an instance *of* something, and install writes it."""
    (layout.unit_dir / WORKER_TEMPLATE_UNIT).unlink()
    host = FakeHost()

    with pytest.raises(OperatorError) as raised:
        run_deploy(layout, host, FakeDeployments(host))

    assert WORKER_TEMPLATE_UNIT in str(raised.value)
    assert "worker install" in str(raised.value)
    assert host.mutations == []


def run_deploy(
    layout: InstallLayout,
    host: FakeHost,
    directory: FakeDeployments,
    revision: str | None = None,
    **extra: float,
) -> DeployReport:
    clock = FakeClock()
    return deploy(
        layout,
        revision,
        run=host,
        deployments=directory,
        now=clock.now,
        sleep=clock.sleep,
        **extra,
    )


# ============================================================================
# US2-S4 / FR-004 — four refusals, each by name, each before anything moved
# ============================================================================


def test_a_tree_that_is_not_a_git_checkout_is_refused_by_name(
    layout: InstallLayout,
) -> None:
    """A wheel install is the live case: static code, and no sha to ship."""
    host = FakeHost(checkout=False)

    with pytest.raises(OperatorError) as raised:
        run_deploy(layout, host, FakeDeployments(host))

    assert str(layout.install_root) in str(raised.value)
    assert "git checkout" in str(raised.value)
    assert host.mutations == []
    assert not layout.deployments_dir.exists()


def test_a_revision_that_is_not_a_commit_is_refused_by_name(
    layout: InstallLayout,
) -> None:
    host = FakeHost()
    directory = FakeDeployments(host)

    with pytest.raises(OperatorError) as raised:
        run_deploy(layout, host, directory, "not-a-branch")

    assert "not-a-branch" in str(raised.value)
    assert host.mutations == []
    assert directory.set_calls == []


def test_a_dirty_tree_with_no_revision_named_is_refused_by_name(
    layout: InstallLayout,
) -> None:
    """A deploy ships commits; there is no sha for a dirty tree to answer to."""
    host = FakeHost(dirty=True)

    with pytest.raises(OperatorError) as raised:
        run_deploy(layout, host, FakeDeployments(host))

    message = str(raised.value)
    assert "uncommitted" in message and "factory/worker.py" in message
    assert host.mutations == []


def test_a_dirty_tree_deploys_the_revision_the_operator_named(
    layout: InstallLayout,
) -> None:
    """The control: the refusal is about the *unnamed* sha, not about dirt.

    An operator who names a commit has said which code they mean, and whatever
    they are editing in the working tree is beside the point — the frozen
    checkout comes out of the object database either way.
    """
    host = FakeHost(dirty=True, revisions=("HEAD", "v0.2.0"))
    directory = FakeDeployments(host)

    report = run_deploy(layout, host, directory, "v0.2.0")

    assert report.build_id == HEAD_SHORT
    assert directory.set_calls == [HEAD_SHORT]


def test_an_unreachable_systemd_session_is_refused_by_name(
    layout: InstallLayout,
) -> None:
    host = FakeHost(systemd=False)

    with pytest.raises(OperatorError) as raised:
        run_deploy(layout, host, FakeDeployments(host))

    assert "systemd" in str(raised.value)
    assert host.mutations == []


def test_an_unreachable_temporal_server_is_refused_before_anything_moves(
    layout: InstallLayout,
) -> None:
    """FR-004's fourth name, and the one that costs most if it comes late.

    A checkout and a `uv sync` are minutes; discovering the server is down
    after them leaves a half-deployed version with nothing to register against.
    """
    host = FakeHost()

    with pytest.raises(OperatorError) as raised:
        run_deploy(layout, host, FakeDeployments(host, available=False))

    assert "Temporal" in str(raised.value)
    assert "localhost:7233" in str(raised.value)
    assert host.mutations == []
    assert not layout.deployments_dir.exists()


# ============================================================================
# US2-S3 / FR-003 — freeze, start, wait, set current; and converge on a re-run
# ============================================================================


def test_the_happy_path_freezes_a_checkout_starts_the_unit_and_sets_current(
    layout: InstallLayout,
) -> None:
    host = FakeHost()
    directory = FakeDeployments(host)

    report = run_deploy(layout, host, directory)

    tree = layout.deployment_tree(HEAD_SHORT)
    assert ("git", "worktree", "add", "--detach", str(tree), HEAD_SHA) in host.calls
    assert ("uv", "sync", "--frozen") in host.calls
    assert host.units == {worker_instance(HEAD_SHORT)}
    assert directory.set_calls == [HEAD_SHORT]
    assert report.build_id == HEAD_SHORT
    assert report.checkout == tree
    assert report.degraded is None


def test_the_frozen_checkout_lives_outside_the_operators_own_checkout(
    layout: InstallLayout,
) -> None:
    """Plan trap 2. A worktree nested in the repo is executable surface in the
    one place this spec exists to stop executing from — and it would reach the
    gates and the judge as apparent work product besides."""
    host = FakeHost()

    report = run_deploy(layout, host, FakeDeployments(host))

    assert layout.install_root not in report.checkout.parents
    assert layout.deployments_dir in report.checkout.parents


def test_the_unit_is_started_before_the_version_is_made_current(
    layout: InstallLayout,
) -> None:
    """Plan trap 7: `set-current-version` before a worker registers fails.

    The ordering *is* the mitigation, so the fake asserts it from the inside —
    `set_current` on a build id the directory has never seen is the exact
    server-side error, and here it is an assertion.
    """
    host = FakeHost()
    directory = FakeDeployments(host, registers_after=2)

    run_deploy(layout, host, directory)

    assert directory.set_calls == [HEAD_SHORT]
    assert directory.snapshots >= 3  # preflight, then two polls


def test_deploying_the_already_current_revision_converges(
    layout: InstallLayout,
) -> None:
    """US2-S3. Twice in a row, and the second run changes nothing.

    Not merely "does not crash": no second `git worktree add` (which fails on
    an existing directory), no second unit, and no redundant `set-current`.
    """
    host = FakeHost()
    directory = FakeDeployments(host)

    first = run_deploy(layout, host, directory)
    host.calls.clear()
    second = run_deploy(layout, host, directory)

    assert first.build_id == second.build_id == HEAD_SHORT
    assert [call for call in host.calls if call[:2] == ("git", "worktree")] == []
    assert host.units == {worker_instance(HEAD_SHORT)}
    assert directory.set_calls == [HEAD_SHORT]
    assert second.already_current is True
    assert second.degraded is None


# ============================================================================
# US2-S5 / FR-003 — the registration wait is bounded, and a timeout converges
# ============================================================================


def test_a_version_that_never_registers_reports_degraded_and_leaves_the_unit_up(
    layout: InstallLayout,
) -> None:
    """No rollback: the idempotent re-run is the recovery (plan trap 7).

    Tearing the unit down here would delete the journal the operator needs in
    order to find out why it did not register.
    """
    host = FakeHost()
    directory = FakeDeployments(host, registers_after=10_000)

    report = run_deploy(layout, host, directory, wait_s=30.0, poll_s=5.0)

    assert report.degraded is not None
    assert HEAD_SHORT in report.degraded and "30s" in report.degraded
    assert host.units == {worker_instance(HEAD_SHORT)}
    assert directory.set_calls == []
    assert "worker deploy" in report.render()


def test_a_re_run_after_a_registration_timeout_converges(
    layout: InstallLayout,
) -> None:
    """US2-S5's second half: the same command again, and the deploy completes."""
    host = FakeHost()
    directory = FakeDeployments(host, registers_after=10_000)
    run_deploy(layout, host, directory, wait_s=30.0, poll_s=5.0)

    directory.registers_after = 0
    report = run_deploy(layout, host, directory, wait_s=30.0, poll_s=5.0)

    assert report.degraded is None
    assert directory.set_calls == [HEAD_SHORT]
    assert host.units == {worker_instance(HEAD_SHORT)}


def test_the_registration_poll_stops_at_the_bound_rather_than_forever(
    layout: InstallLayout,
) -> None:
    host = FakeHost()
    directory = FakeDeployments(host, registers_after=10_000)
    clock = FakeClock()

    deploy(
        layout,
        None,
        run=host,
        deployments=directory,
        now=clock.now,
        sleep=clock.sleep,
        wait_s=20.0,
        poll_s=5.0,
    )

    assert clock.t <= 25.0


# ============================================================================
# US2-S6 / FR-010 — the report names every version and its state
# ============================================================================


def test_the_report_names_every_version_and_its_state() -> None:
    """One command's output answers "what is on the floor right now"."""
    report = DeployReport(
        build_id="c0ffee1",
        checkout=Path("/state/ergane/supervision/deployments/c0ffee1/tree"),
        unit=worker_instance("c0ffee1"),
        already_current=False,
        versions=(
            VersionState("1234567", "drained"),
            VersionState("9f8e7d6", "draining"),
            VersionState("c0ffee1", "current"),
        ),
    )

    rendered = report.render()

    for build_id, state in (
        ("c0ffee1", "current"),
        ("9f8e7d6", "draining"),
        ("1234567", "drained"),
    ):
        line = next(l for l in rendered.splitlines() if build_id in l)
        assert state in line, f"{build_id} is not reported as {state}: {line!r}"
    assert str(report.checkout) in rendered
    assert report.unit in rendered


def test_the_report_of_a_real_deploy_carries_the_servers_own_version_list(
    layout: InstallLayout,
) -> None:
    """Read back, not composed: the list is the server's answer after the set.

    A report assembled from what deploy *intended* would show a clean floor
    while a stuck drain piles versions up — which is the one thing FR-010 is
    for.
    """
    host = FakeHost()
    directory = FakeDeployments(
        host, versions={OLD_SHORT: "current", "1234567": "drained"}
    )

    report = run_deploy(layout, host, directory)

    assert [(state.build_id, state.state) for state in report.versions] == [
        ("1234567", "drained"),
        (OLD_SHORT, "draining"),
        (HEAD_SHORT, "current"),
    ]
    rendered = report.render()
    assert f"{OLD_SHORT}" in rendered and "draining" in rendered


# ============================================================================
# Spec edge case — two deploys racing: the verb takes a lock, the loser reports
# ============================================================================


def test_a_second_deploy_reports_the_lock_the_first_one_holds(
    layout: InstallLayout,
) -> None:
    host = FakeHost()

    with exclusive_lock(deploy_lock_target(layout), timeout_s=0):
        with pytest.raises(OperatorError) as raised:
            run_deploy(layout, host, FakeDeployments(host), lock_timeout_s=0.0)

    assert str(deploy_lock_target(layout)) in str(raised.value)
    assert host.mutations == []


# ============================================================================
# The verb — thin, and one decision of its own
# ============================================================================


def _run_verb(
    monkeypatch: pytest.MonkeyPatch, report: DeployReport, capsys: pytest.CaptureFixture
) -> tuple[int, str]:
    from factory.cli.main import main as ergane_main

    seen: dict[str, object] = {}

    def fake_deploy(layout: InstallLayout, revision: str | None = None) -> DeployReport:
        seen["revision"] = revision
        return report

    monkeypatch.setattr("factory.supervision.deploy.deploy", fake_deploy)
    code = ergane_main(["worker", "deploy", "v0.2.0"])
    assert seen["revision"] == "v0.2.0"
    return code, capsys.readouterr().out


def test_the_verb_prints_the_report_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    code, printed = _run_verb(
        monkeypatch,
        DeployReport(
            build_id=HEAD_SHORT,
            checkout=Path("/state/deployments") / HEAD_SHORT / "tree",
            unit=worker_instance(HEAD_SHORT),
            already_current=False,
            versions=(VersionState(HEAD_SHORT, "current"),),
        ),
        capsys,
    )

    assert code == 0
    assert HEAD_SHORT in printed and "current" in printed


def test_a_degraded_deploy_does_not_exit_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Exiting 0 here would tell a script the floor moved when it has not."""
    code, printed = _run_verb(
        monkeypatch,
        DeployReport(
            build_id=HEAD_SHORT,
            checkout=Path("/state/deployments") / HEAD_SHORT / "tree",
            unit=worker_instance(HEAD_SHORT),
            already_current=False,
            versions=(VersionState(OLD_SHORT, "current"),),
            degraded=f"version {HEAD_SHORT} did not register with Temporal",
        ),
        capsys,
    )

    assert code != 0
    assert "DEGRADED" in printed
