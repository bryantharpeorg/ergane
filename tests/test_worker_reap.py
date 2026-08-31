"""082-US3: a drained version leaves the host — and nothing else does.

The story is two controls and one act, so this suite is mostly controls. The
decision is a pure function over (versions, drainage, open work, units), which
is what makes "the current version is never reaped" and "a version with open
work is never reaped" assertions about a return value rather than about a
machine that would have to be broken to prove them.

Nothing here reaches the host or the server. The runner is a fake operator
machine that **raises on any command the sweep is not allowed to run**, which is
how "removed through git's own worktree removal, never a bare `rm`" (plan trap
3) is proven rather than asserted: a `rm -rf` would come back as an
AssertionError naming the argv.

Written before `reapable`/`sweep` existed:

    $ PYTHONDONTWRITEBYTECODE=1 uv run pytest -q tests/test_worker_reap.py --no-header
    tests/test_worker_reap.py:39: in <module>
        from factory.supervision.deploy import (
    E   ImportError: cannot import name 'ReapTarget' from 'factory.supervision.deploy'
    1 error in 0.34s
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator, Mapping, Sequence

import pytest

from factory.supervision.deploy import (
    DeploymentSnapshot,
    DeploymentsUnavailable,
    Reaped,
    ReapTarget,
    SweepReport,
    VersionState,
    deploy_lock_target,
    open_pinned_query,
    reapable,
    sweep,
)
from factory.supervision.units import (
    CommandResult,
    InstallLayout,
    worker_instance,
)

#: The version serving new work, and two that are not.
CURRENT = "b683288"
DRAINED = "e423f13"
OTHER = "9f8e7d6"


def snapshot_of(current: str | None, **states: str) -> DeploymentSnapshot:
    """A deployment directory in one line: `snapshot_of(CURRENT, e423f13=...)`.

    `current` is passed rather than derived from the states, so a test can hand
    the decision a snapshot the server would never produce — a current version
    labelled drained is exactly the input US3-S2's control needs.
    """
    return DeploymentSnapshot(
        current=current,
        versions=tuple(VersionState(build, state) for build, state in states.items()),
    )


# --- T019 / US3-S2 — the control: the current version is never reaped ---------


def test_the_current_version_is_never_reaped_however_idle_it_looks() -> None:
    """The control, at its most adversarial: a current version the server has
    also labelled drained, with not one open workflow on it. Idleness is not
    the question — being current is."""
    decided = reapable(
        snapshot_of(CURRENT, **{CURRENT: "drained"}),
        open_work={CURRENT: 0},
        units=(worker_instance(CURRENT),),
    )

    assert decided == ()


def test_a_drained_version_beside_the_current_one_is_the_only_one_taken() -> None:
    """The same control from the other side: the sweep is not inert, it is
    selective. Both versions are idle; only the non-current one goes."""
    decided = reapable(
        snapshot_of(CURRENT, **{CURRENT: "current", DRAINED: "drained"}),
        open_work={CURRENT: 0, DRAINED: 0},
        units=(worker_instance(CURRENT), worker_instance(DRAINED)),
    )

    assert decided == (ReapTarget(DRAINED, worker_instance(DRAINED)),)


def test_a_version_still_draining_is_left_alone() -> None:
    """FR-005 says *has completed* draining. A version the server still calls
    draining has work it has not finished, whatever the count says today."""
    assert (
        reapable(
            snapshot_of(CURRENT, **{CURRENT: "current", DRAINED: "draining"}),
            open_work={DRAINED: 0},
            units=(),
        )
        == ()
    )


# --- T020 / US3-S3 — open pinned work, at decision time and at action time ----


def test_a_version_with_any_open_pinned_workflow_is_left_alone() -> None:
    decided = reapable(
        snapshot_of(CURRENT, **{CURRENT: "current", DRAINED: "drained"}),
        open_work={CURRENT: 0, DRAINED: 1},
        units=(worker_instance(DRAINED),),
    )

    assert decided == ()


def test_a_version_whose_open_work_could_not_be_read_is_left_alone() -> None:
    """Unknown is not zero. A version the server could not be asked about is
    one that might be serving an epic, and a reap is not undoable."""
    decided = reapable(
        snapshot_of(CURRENT, **{CURRENT: "current", DRAINED: "drained"}),
        open_work={CURRENT: 0},
        units=(worker_instance(DRAINED),),
    )

    assert decided == ()


def test_work_that_arrives_after_the_decision_stops_the_reap(
    layout: InstallLayout,
) -> None:
    """The spec's edge case, and the reason the count is asked twice: the sweep
    decided on a floor that has since changed. Nothing may move."""
    host = FakeHost(layout, instances=(DRAINED,), trees=(DRAINED,))
    directory = FakeDeployments(
        current=CURRENT,
        versions={CURRENT: "current", DRAINED: "drained"},
        open_work={DRAINED: 0},
        # An epic pinned to the old version starts between the decision and the
        # act — the racing dispatch the spec names.
        open_work_after_first_read={DRAINED: 1},
    )

    report = sweep(layout, deployments=directory, run=host)

    assert host.mutations == []
    assert directory.deleted == []
    assert layout.deployment_tree(DRAINED).exists()
    assert report.reaped[0].deferred is not None
    assert "open" in report.reaped[0].deferred


# --- T021 / FR-005, plan trap 3 — the checkout goes through git ---------------


def test_a_reap_stops_the_unit_removes_the_checkout_and_deletes_the_record(
    layout: InstallLayout,
) -> None:
    """The whole act, in the one order that is safe: the worker stops before
    the code it is running is removed, and the record goes last because a
    version whose worker is still polling cannot be deleted."""
    host = FakeHost(layout, instances=(DRAINED,), trees=(DRAINED,))
    directory = FakeDeployments(
        current=CURRENT,
        versions={CURRENT: "current", DRAINED: "drained"},
        open_work={CURRENT: 0, DRAINED: 0},
    )

    report = sweep(layout, deployments=directory, run=host)

    assert host.mutations == [
        ("systemctl", "--user", "disable", "--now", worker_instance(DRAINED)),
        ("git", "worktree", "remove", "--force", str(layout.deployment_tree(DRAINED))),
        ("git", "worktree", "prune"),
    ]
    assert host.cwd_of(("git", "worktree", "remove")) == layout.install_root
    assert not layout.deployment_tree(DRAINED).exists()
    assert directory.deleted == [DRAINED]
    assert [one.build_id for one in report.reaped] == [DRAINED]
    assert report.reaped[0].deferred is None
    assert DRAINED in report.render()


def test_a_checkout_git_will_not_remove_is_left_on_disk(
    layout: InstallLayout,
) -> None:
    """The trap, exactly (plan trap 3): `git worktree add` wrote state into the
    main repo's `.git`, so a refused removal is pruned and reported — never
    finished off with a bare delete. The tree is still there, and so is the
    version record: a re-run converges, and until it does the report says why."""
    host = FakeHost(layout, instances=(DRAINED,), trees=(DRAINED,), git_removes=False)
    directory = FakeDeployments(
        current=CURRENT,
        versions={CURRENT: "current", DRAINED: "drained"},
        open_work={CURRENT: 0, DRAINED: 0},
    )

    report = sweep(layout, deployments=directory, run=host)

    assert ("git", "worktree", "prune") in host.mutations
    assert layout.deployment_tree(DRAINED).exists()
    assert directory.deleted == []
    assert "worktree" in (report.reaped[0].deferred or "")


def test_a_checkout_already_gone_is_pruned_and_the_reap_completes(
    layout: InstallLayout,
) -> None:
    """Convergence: a half-finished earlier sweep, or an operator who removed
    the tree by hand. The registration in the main repo's `.git` is the thing
    left to clean, and `prune` is what cleans it."""
    host = FakeHost(layout, instances=(DRAINED,), trees=())
    directory = FakeDeployments(
        current=CURRENT,
        versions={CURRENT: "current", DRAINED: "drained"},
        open_work={CURRENT: 0, DRAINED: 0},
    )

    report = sweep(layout, deployments=directory, run=host)

    assert ("git", "worktree", "prune") in host.mutations
    assert not any(call[:3] == ("git", "worktree", "remove") for call in host.mutations)
    assert directory.deleted == [DRAINED]
    assert report.reaped[0].deferred is None


def test_a_unit_that_will_not_stop_keeps_its_checkout(layout: InstallLayout) -> None:
    """The safety inside the order: removing the code from under a worker that
    is still running is worse than leaving a checkout on disk for a cycle."""
    host = FakeHost(layout, instances=(DRAINED,), trees=(DRAINED,), systemd_stops=False)
    directory = FakeDeployments(
        current=CURRENT,
        versions={CURRENT: "current", DRAINED: "drained"},
        open_work={CURRENT: 0, DRAINED: 0},
    )

    report = sweep(layout, deployments=directory, run=host)

    assert not any(call[0] == "git" for call in host.mutations)
    assert layout.deployment_tree(DRAINED).exists()
    assert directory.deleted == []
    assert "unit" in (report.reaped[0].deferred or "")


def test_a_version_with_no_unit_on_this_host_is_still_reaped(
    layout: InstallLayout,
) -> None:
    """Which is why `units` is one of the decision's four inputs: the record
    and the checkout are this host's to clean even when the unit is already
    gone, and `disable` on a unit that is not there is noise, not work."""
    host = FakeHost(layout, instances=(), trees=(DRAINED,))
    directory = FakeDeployments(
        current=CURRENT,
        versions={CURRENT: "current", DRAINED: "drained"},
        open_work={CURRENT: 0, DRAINED: 0},
    )

    report = sweep(layout, deployments=directory, run=host)

    assert not any(call[0] == "systemctl" for call in host.mutations)
    assert not layout.deployment_tree(DRAINED).exists()
    assert directory.deleted == [DRAINED]
    assert report.reaped[0].unit is None


# --- the sweep's own refusals -------------------------------------------------


def test_a_sweep_that_cannot_reach_temporal_touches_nothing(
    layout: InstallLayout,
) -> None:
    """The probe runs this every couple of minutes, and Temporal being away is
    the condition the probe exists to report. It is a note, not an exception."""
    host = FakeHost(layout, instances=(DRAINED,), trees=(DRAINED,))
    directory = FakeDeployments(available=False)

    report = sweep(layout, deployments=directory, run=host)

    assert host.mutations == []
    assert report.reaped == ()
    assert "7233" in (report.unavailable or "")
    assert "cannot" in report.render()


def test_a_sweep_defers_to_a_deploy_holding_the_lock(layout: InstallLayout) -> None:
    """A deploy is mid-`uv sync` on a version the server has not been told about
    yet. The sweep does not queue behind it and does not race it — it says so
    and leaves; the next firing of the timer converges."""
    from factory.locking import exclusive_lock

    host = FakeHost(layout, instances=(DRAINED,), trees=(DRAINED,))
    directory = FakeDeployments(
        current=CURRENT,
        versions={CURRENT: "current", DRAINED: "drained"},
        open_work={CURRENT: 0, DRAINED: 0},
    )

    with exclusive_lock(deploy_lock_target(layout), timeout_s=0):
        report = sweep(layout, deployments=directory, run=host, lock_timeout_s=0)

    assert host.mutations == []
    assert directory.deleted == []
    assert "deploy" in (report.unavailable or "")


def test_a_report_with_nothing_to_say_says_so() -> None:
    assert "nothing" in SweepReport().render()


def test_open_work_is_counted_under_the_colon_form_of_the_version() -> None:
    """The probe's finding, kept as a test because the wrong form is silent.

    `WorkerDeploymentVersion.to_canonical_string()` joins with a dot; visibility
    indexes with a colon. A dotted query does not error — it answers zero for
    every version, forever, which is precisely the answer that makes the sweep
    delete a version an epic is running on.
    """
    query = open_pinned_query(DRAINED, "ergane-worker")

    assert f'"ergane-worker:{DRAINED}"' in query
    assert f"ergane-worker.{DRAINED}" not in query
    assert 'ExecutionStatus = "Running"' in query


# --- T022 — the sweep is wired into the probe's cycle -------------------------


def probe_host(swept: SweepReport) -> object:
    """A machine that reads healthy and sweeps whatever this test says."""
    from factory.supervision.probe import Host

    return Host(
        systemctl=lambda _argv: CommandResult(0, "active"),
        process_table=lambda: "",
        meminfo=lambda: "MemAvailable: 67108864 kB\n",
        uptime_s=lambda: 10_000.0,
        kill=lambda _pid: None,
        dial=lambda _address, _port: True,
        sweep=lambda: swept,
    )


def test_the_probes_cycle_reaps_and_says_what_it_took() -> None:
    """The wiring, and the reason it is the probe that carries it: nothing else
    runs on a timer, and a reap that waits for the operator to run a command is
    the graveyard this story exists to prevent."""
    from factory.supervision.probe import ProbeConfig, assess

    verdict = assess(
        ProbeConfig(units=(), dial=()),
        probe_host(SweepReport((Reaped(DRAINED, None, Path("/gone")),))),
    )

    assert any(DRAINED in note for note in verdict.notes)
    assert verdict.status == "healthy"


def test_a_sweep_that_took_nothing_is_silent() -> None:
    """FR-013's muting rule reaches this too: a note every two minutes saying
    nothing was reaped is a channel an operator learns to skip."""
    from factory.supervision.probe import ProbeConfig, assess

    verdict = assess(ProbeConfig(units=(), dial=()), probe_host(SweepReport()))

    assert verdict.notes == ()


def test_the_real_probe_host_sweeps_versions_for_real() -> None:
    """The default is a no-op so no test can reach the floor by forgetting to
    pass one — which would also ship a probe that never reaps. This is the
    assertion that the production wiring is not that default."""
    from factory.supervision.probe import _sweep_versions, real_host

    assert real_host().sweep is _sweep_versions


# --- fakes --------------------------------------------------------------------


class FakeHost:
    """One operator machine, answering only the four commands a sweep may run.

    Anything else — a `rm`, a `shutil.rmtree` shelled out, a `systemctl kill` —
    comes back as an AssertionError naming the argv, which is trap 3's proof.
    """

    def __init__(
        self,
        layout: InstallLayout,
        *,
        instances: Sequence[str] = (),
        trees: Sequence[str] = (),
        git_removes: bool = True,
        systemd_stops: bool = True,
    ) -> None:
        self.layout = layout
        self.instances = [worker_instance(build) for build in instances]
        self.git_removes, self.systemd_stops = git_removes, systemd_stops
        self.calls: list[tuple[tuple[str, ...], Path | None]] = []
        for build in trees:
            layout.deployment_tree(build).mkdir(parents=True)
            (layout.deployment_tree(build) / ".git").write_text("gitdir: ...")

    def __call__(
        self, argv: Sequence[str], *, cwd: Path | None = None
    ) -> CommandResult:
        args = tuple(argv)
        self.calls.append((args, cwd))
        if args[:3] == ("systemctl", "--user", "list-units"):
            return CommandResult(
                0, "\n".join(f"{name} loaded active running" for name in self.instances)
            )
        if args[:4] == ("systemctl", "--user", "disable", "--now"):
            if not self.systemd_stops:
                return CommandResult(1, f"Failed to stop {args[-1]}: unit is masked")
            self.instances = [name for name in self.instances if name != args[-1]]
            return CommandResult(0)
        if args[:4] == ("git", "worktree", "remove", "--force"):
            tree = Path(args[-1])
            if not self.git_removes:
                return CommandResult(1, f"fatal: '{tree}' contains modified files")
            for child in sorted(tree.rglob("*"), reverse=True):
                child.unlink()
            tree.rmdir()
            return CommandResult(0)
        if args == ("git", "worktree", "prune"):
            return CommandResult(0)
        raise AssertionError(f"the sweep ran a command it has no business running: {args}")

    @property
    def mutations(self) -> list[tuple[str, ...]]:
        """Every call that changed something — what a refusal leaves empty."""
        return [
            args
            for args, _ in self.calls
            if args[:3] != ("systemctl", "--user", "list-units")
        ]

    def cwd_of(self, prefix: tuple[str, ...]) -> Path | None:
        return next(cwd for args, cwd in self.calls if args[: len(prefix)] == prefix)


class FakeDeployments:
    """The deployment directory, with a count of open pinned work per version
    that can change between the sweep's decision and its act."""

    def __init__(
        self,
        *,
        current: str | None = None,
        versions: Mapping[str, str] | None = None,
        open_work: Mapping[str, int] | None = None,
        open_work_after_first_read: Mapping[str, int] | None = None,
        available: bool = True,
    ) -> None:
        self.current = current
        self.versions = dict(versions or {})
        self.open_work = dict(open_work or {})
        self.later = open_work_after_first_read
        self.available = available
        self.deleted: list[str] = []
        self.reads: list[str] = []

    def snapshot(self) -> DeploymentSnapshot:
        self._reachable()
        return DeploymentSnapshot(
            current=self.current,
            versions=tuple(
                VersionState(build, state) for build, state in sorted(self.versions.items())
            ),
        )

    def open_pinned(self, build_id: str) -> int:
        self._reachable()
        answer = self.open_work[build_id]
        self.reads.append(build_id)
        if self.later is not None:
            self.open_work.update(self.later)
        return answer

    def delete(self, build_id: str) -> None:
        self._reachable()
        self.deleted.append(build_id)
        self.versions.pop(build_id, None)

    def _reachable(self) -> None:
        if not self.available:
            raise DeploymentsUnavailable("localhost:7233", "connection refused")


@pytest.fixture
def layout(tmp_path: Path) -> Iterator[InstallLayout]:
    """An installed host, every root under `tmp_path`."""
    home = tmp_path / "home"
    interpreter = home / "code/ergane/.venv/bin/python3"
    interpreter.parent.mkdir(parents=True)
    interpreter.touch()
    yield InstallLayout(
        install_root=home / "code/ergane",
        interpreter=interpreter,
        unit_dir=home / ".config/systemd/user",
        generated_dir=home / ".local/state/ergane/supervision",
        # 119-US1: the mode is declared, never defaulted.
        temporal_mode="external",
    )
