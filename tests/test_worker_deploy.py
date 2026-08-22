"""082-US2: `ergane worker deploy` — new code on the floor, old code untouched.

Every claim here is about what `deploy` *issued* and what it reported. Nothing
reaches the host: the runner is a fake operator machine and the Temporal seam a
fake deployment directory whose versions appear only once a unit that would
register them has started. Both are recorders, because most of what this story
promises is about *which* commands ran and in what order — a refusal that
already created a checkout is not one, and a `set-current` before registration
is the failure trap 7 names.

Written before `factory/supervision/deploy.py` existed:

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
    """One operator machine: a checkout, a systemd session, `uv`, `git`. Answers
    only what `deploy` may run and records every call; anything else raises
    rather than returning a silent zero."""

    def __init__(
        self,
        *,
        checkout: bool = True,
        dirty: bool = False,
        systemd: bool = True,
        revisions: Sequence[str] = ("HEAD",),
    ) -> None:
        self.checkout, self.dirty, self.systemd = checkout, dirty, systemd
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
            resolved = self.revisions.get(args[-1].removesuffix("^{commit}"))
            return CommandResult(0, resolved) if resolved else CommandResult(128)
        if args[1:3] == ("rev-parse", "--short"):
            return CommandResult(0, args[-1][:7])
        if args[1:4] == ("worktree", "add", "--detach"):
            (Path(args[4]) / ".venv/bin").mkdir(parents=True)
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
        raise AssertionError(f"unexpected systemctl command: {args}")

    @property
    def mutations(self) -> list[tuple[str, ...]]:
        """Every call that changed something — what a refusal leaves empty."""
        return [
            call
            for call in self.calls
            if call[:2] == ("git", "worktree")
            or call[0] == "uv"
            or (call[0] == "systemctl" and call[2] != "show")
        ]


class FakeDeployments:
    """The deployment directory the server keeps, as `deploy` reads it. A
    version appears `registers_after` snapshots after the unit that registers it
    started — the real sequence, and why the wait is bounded not assumed."""

    def __init__(
        self,
        host: FakeHost | None = None,
        *,
        current: str | None = OLD_SHORT,
        versions: dict[str, str] | None = None,
        registers_after: int = 1,
        available: bool = True,
    ) -> None:
        self.host, self.current, self.available = host, current, available
        self.versions = {OLD_SHORT: "current"} if versions is None else dict(versions)
        self.registers_after = registers_after
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
        # The server's own error, as an assertion: `set-current-version` against
        # a version no worker has registered fails (plan trap 7).
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


# --- US2-S4 / FR-004 — the refusals, each by name, each before anything moved ---


def test_a_tree_that_is_not_a_git_checkout_is_refused(layout: InstallLayout) -> None:
    """A wheel install is the live case: static code, and no sha to ship."""
    host = FakeHost(checkout=False)

    with pytest.raises(OperatorError) as raised:
        run_deploy(layout, host, FakeDeployments(host))

    assert str(layout.install_root) in str(raised.value)
    assert "git checkout" in str(raised.value)
    assert host.mutations == []
    assert not layout.deployments_dir.exists()


def test_a_revision_that_is_not_a_commit_is_refused(layout: InstallLayout) -> None:
    host = FakeHost()
    directory = FakeDeployments(host)

    with pytest.raises(OperatorError) as raised:
        run_deploy(layout, host, directory, "not-a-branch")

    assert "not-a-branch" in str(raised.value)
    assert host.mutations == []
    assert directory.set_calls == []


def test_a_dirty_tree_with_no_revision_named_is_refused(layout: InstallLayout) -> None:
    """A deploy ships commits; there is no sha for a dirty tree to answer to."""
    host = FakeHost(dirty=True)

    with pytest.raises(OperatorError) as raised:
        run_deploy(layout, host, FakeDeployments(host))

    assert "uncommitted" in str(raised.value)
    assert "factory/worker.py" in str(raised.value)
    assert host.mutations == []


def test_a_dirty_tree_deploys_the_revision_the_operator_named(
    layout: InstallLayout,
) -> None:
    """The control: the refusal is about the *unnamed* sha, not about dirt —
    the frozen checkout comes out of the object database either way."""
    host = FakeHost(dirty=True, revisions=("HEAD", "v0.2.0"))
    directory = FakeDeployments(host)

    assert run_deploy(layout, host, directory, "v0.2.0").build_id == HEAD_SHORT
    assert directory.set_calls == [HEAD_SHORT]


def test_an_unreachable_systemd_session_is_refused(layout: InstallLayout) -> None:
    host = FakeHost(systemd=False)

    with pytest.raises(OperatorError) as raised:
        run_deploy(layout, host, FakeDeployments(host))

    assert "systemd" in str(raised.value)
    assert host.mutations == []


def test_an_unreachable_temporal_server_is_refused_before_anything_moves(
    layout: InstallLayout,
) -> None:
    """The refusal that costs most if it comes late: a checkout and a `uv sync`
    are minutes, and finding the server gone after them leaves a frozen checkout
    with nothing to register against."""
    host = FakeHost()

    with pytest.raises(OperatorError) as raised:
        run_deploy(layout, host, FakeDeployments(host, available=False))

    assert "Temporal" in str(raised.value) and "localhost:7233" in str(raised.value)
    assert host.mutations == []
    assert not layout.deployments_dir.exists()


# --- US2-S3 / FR-003 — freeze, start, wait, set current; and converge on a re-run ---


def test_the_happy_path_freezes_starts_waits_and_sets_current(
    layout: InstallLayout,
) -> None:
    """One deploy, and the four things it must do — in that order.

    The ordering is trap 7's mitigation, asserted by the fake from the inside;
    `registers_after=2` makes the wait real rather than incidental; and the
    checkout living outside the operator's own is trap 2, a worktree nested in
    the repo being executable surface where this spec forbids it."""
    host = FakeHost()
    directory = FakeDeployments(host, registers_after=2)

    report = run_deploy(layout, host, directory)

    tree = layout.deployment_tree(HEAD_SHORT)
    assert ("git", "worktree", "add", "--detach", str(tree), HEAD_SHA) in host.calls
    assert ("uv", "sync", "--frozen") in host.calls
    assert host.units == {worker_instance(HEAD_SHORT)}
    assert directory.set_calls == [HEAD_SHORT]
    assert directory.snapshots >= 3  # the preflight read, then two polls
    assert report.build_id == HEAD_SHORT
    assert report.checkout == tree and report.degraded is None
    assert layout.install_root not in tree.parents
    assert layout.deployments_dir in tree.parents


def test_deploying_the_already_current_revision_converges(
    layout: InstallLayout,
) -> None:
    """US2-S3. Twice in a row, and the second changes nothing: no second
    `git worktree add` (which fails on an existing directory), no second unit,
    no redundant `set-current`."""
    host = FakeHost()
    directory = FakeDeployments(host)

    first = run_deploy(layout, host, directory)
    host.calls.clear()
    second = run_deploy(layout, host, directory)

    assert first.build_id == second.build_id == HEAD_SHORT
    assert [call for call in host.calls if call[:2] == ("git", "worktree")] == []
    assert host.units == {worker_instance(HEAD_SHORT)}
    assert directory.set_calls == [HEAD_SHORT]
    assert second.already_current is True and second.degraded is None


# --- US2-S5 / FR-003 — the registration wait is bounded, and a timeout converges ---


def test_a_version_that_never_registers_reports_degraded_and_leaves_the_unit_up(
    layout: InstallLayout,
) -> None:
    """No rollback: the idempotent re-run is the recovery (trap 7). Tearing the
    unit down would delete the journal that says why it did not register; the
    clock proves the wait is bounded, not merely finite."""
    host = FakeHost()
    directory = FakeDeployments(host, registers_after=10_000)
    clock = FakeClock()

    report = deploy(
        layout,
        None,
        run=host,
        deployments=directory,
        now=clock.now,
        sleep=clock.sleep,
        wait_s=30.0,
        poll_s=5.0,
    )

    assert report.degraded is not None
    assert HEAD_SHORT in report.degraded and "30s" in report.degraded
    assert clock.t <= 35.0
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


# --- US2-S6 / FR-010 — the report names every version and its state ---


def test_the_report_names_every_version_and_its_state() -> None:
    """One command's output answers "what is on the floor right now"."""
    report = DeployReport(
        build_id="c0ffee1",
        checkout=Path("/state/supervision/deployments/c0ffee1/tree"),
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
        line = next(one for one in rendered.splitlines() if build_id in one)
        assert state in line, f"{build_id} is not reported as {state}: {line!r}"
    assert str(report.checkout) in rendered and report.unit in rendered


def test_the_report_of_a_real_deploy_carries_the_servers_own_version_list(
    layout: InstallLayout,
) -> None:
    """Read back, not composed: a report assembled from what deploy *intended*
    would show a clean floor while a stuck drain piles versions up."""
    host = FakeHost()
    directory = FakeDeployments(
        host, versions={OLD_SHORT: "current", "1234567": "drained"}
    )

    report = run_deploy(layout, host, directory)

    assert [(one.build_id, one.state) for one in report.versions] == [
        ("1234567", "drained"),
        (OLD_SHORT, "draining"),
        (HEAD_SHORT, "current"),
    ]
    assert OLD_SHORT in report.render() and "draining" in report.render()


# --- Spec edge case — two deploys racing: the verb takes a lock, the loser reports ---


def test_a_second_deploy_reports_the_lock_the_first_one_holds(
    layout: InstallLayout,
) -> None:
    host = FakeHost()

    with exclusive_lock(deploy_lock_target(layout), timeout_s=0):
        with pytest.raises(OperatorError) as raised:
            run_deploy(layout, host, FakeDeployments(host), lock_timeout_s=0.0)

    assert str(deploy_lock_target(layout)) in str(raised.value)
    assert host.mutations == []


# --- US2-S2 — what the next epic reports, which is the value 053 injects ---
#
# This scenario reads a number the deploy does not compute: the epic's
# `worker_revision`, injected by the interceptor `build_worker` wires. Running
# T018's live evidence on 2026-08-22 found that interceptor had never fired, and
# that it would have raised `NameError` if it had — fixed here, because a
# deployed build id no epic reports is a deploy nobody can confirm.


def test_the_epic_dispatch_input_is_given_the_workers_revision() -> None:
    import asyncio

    from temporalio.worker._interceptor import (
        ExecuteWorkflowInput,
        WorkflowInboundInterceptor,
    )

    from factory import worker as worker_module
    from factory.workgraph.models import WorkGraph
    from factory.workgraph.workflow import EpicInput

    class EpicWorkflow:
        """The sandbox's re-import of the workflow class, not this process's:
        the SDK imports the module again, so the class an interceptor is handed
        is a *different object* of the same name, and `input.type is
        EpicWorkflow` never matches."""

        async def run(self, request: object) -> None: ...

    seen: dict[str, object] = {}

    class Recording(WorkflowInboundInterceptor):
        def __init__(self) -> None:  # the chain ends here; no `next` to hold
            pass

        async def execute_workflow(self, input: ExecuteWorkflowInput) -> object:
            seen["args"] = input.args
            return "the result"

    inbound = worker_module._WorkerRevisionInterceptor("c0ffee1")
    outer = inbound.workflow_interceptor_class(None)(Recording())
    graph = WorkGraph(
        epic_id="e", feature="f", specs_root="specs", target_repo="/tmp/x", nodes=[]
    )

    result = asyncio.run(
        outer.execute_workflow(
            ExecuteWorkflowInput(
                type=EpicWorkflow,
                run_fn=EpicWorkflow.run,
                args=(EpicInput(graph=graph, proxy_url="http://unused.invalid"),),
                headers={},
            )
        )
    )

    assert seen["args"][0].worker_revision == "c0ffee1"
    # 086-US1: an inbound interceptor sits on the result path, and one that
    # awaits without returning completes every workflow with None.
    assert result == "the result"


# --- The verb — thin, and one decision of its own ---


@pytest.mark.parametrize(
    "degraded, expected",
    [
        (None, 0),
        # Exiting 0 here would tell a script the floor moved when it has not.
        ("version a1b2c3d did not register with Temporal", 1),
    ],
)
def test_the_verb_prints_the_report_and_exits_on_the_deploys_verdict(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
    degraded: str | None,
    expected: int,
) -> None:
    from factory.cli.main import main as ergane_main

    seen: dict[str, object] = {}
    report = DeployReport(
        build_id=HEAD_SHORT,
        checkout=Path("/state/deployments") / HEAD_SHORT / "tree",
        unit=worker_instance(HEAD_SHORT),
        already_current=False,
        versions=(VersionState(HEAD_SHORT, "current"),),
        degraded=degraded,
    )

    def fake_deploy(layout: InstallLayout, revision: str | None = None) -> DeployReport:
        seen["revision"] = revision
        return report

    monkeypatch.setattr("factory.supervision.deploy.deploy", fake_deploy)
    code = ergane_main(["worker", "deploy", "v0.2.0"])

    assert seen["revision"] == "v0.2.0"
    assert code == expected
    assert HEAD_SHORT in capsys.readouterr().out
