"""082-US2/US3: `ergane worker deploy` — new code on the floor, old code
untouched, and the old code's host reclaimed once nothing is left on it.

The verb the operator asked for, in the shape asked for: "draining off of one
worker while the next worker is already taking new work." A deploy freezes a
commit into a checkout of its own, gives it its own dependency environment,
starts it as an instance of the versioned unit template, waits for it to
register, and makes it current. Nothing is restarted, so nothing in flight is
cancelled: attempts stay pinned to the version that started them (US1), which
serves them until the last one closes.

Four properties are load-bearing. **Every refusal happens before anything moves**
(FR-004) — one that already created a worktree and synced a venv is a
half-deploy. **Re-running converges** (FR-003), the whole recovery story, because
a registration timeout deliberately leaves the unit running (US2-S5). **The wait
is bounded and its timeout is not a rollback** (trap 7): `set-current-version`
against an unregistered version fails, and a poll that never succeeds leaves the
unit up because that journal is the only evidence of why. **The report is read
back from the server** (FR-010): an operator watching a stuck drain needs the
server's answer, not ours.

**082-US3 adds the other end of that lifecycle.** A version nothing is pinned
to any more is a unit, a venv and a checkout that serve nothing, and "a trio of
workers" becomes a graveyard of them if reclaiming them depends on the operator
remembering. So the reap runs itself — from the probe's cycle and from the tail
of a deploy — and the *decision* it acts on is a pure function of (versions,
drainage, open work, units), which is what makes "the current version is never
reaped" and "a version with open work is never reaped" provable without a
machine to break. Every act it then performs is idempotent and every failure is
deferred rather than retried, because the server refuses to delete a version
whose pollers have not yet aged out and the answer to that is the next sweep.
"""

from __future__ import annotations

import dataclasses
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Collection, Mapping, Protocol, Sequence

from factory.cli.errors import EXIT_TRANSPORT, OperatorError
from factory.locking import LockUnavailable, exclusive_lock
from factory.supervision.units import CommandResult, InstallLayout, worker_instance

#: One command, optionally somewhere else: `(argv, *, cwd=None) -> CommandResult`.
Runner = Any

#: Short on purpose: the loser of a race reports the winner rather than
#: queueing behind a `uv sync`.
DEPLOY_LOCK_TIMEOUT_S = 5.0

#: How long a new instance has to register, and how often it is asked. The
#: `uv sync` is done by now; what remains is process start and a round trip.
REGISTRATION_WAIT_S = 120.0
REGISTRATION_POLL_S = 2.0

#: The sweep's patience for that lock, and it is deliberately near none: the
#: sweep runs every couple of minutes from the probe, so a deploy holding the
#: lock is a reason to come back rather than a reason to wait.
SWEEP_LOCK_TIMEOUT_S = 1.0


@dataclasses.dataclass(frozen=True)
class VersionState:
    """One version of the deployment, and what it is doing (FR-010)."""

    build_id: str
    state: str


@dataclasses.dataclass(frozen=True)
class DeploymentSnapshot:
    """The deployment directory as the server currently describes it."""

    current: str | None
    versions: tuple[VersionState, ...]


class DeploymentsUnavailable(RuntimeError):
    """The deployment directory could not be reached — raised by the Temporal
    seam, translated into FR-004's refusal by `deploy`, so a fake refuses on
    exactly the path the real server does."""

    def __init__(self, address: str, detail: str) -> None:
        self.address = address
        self.detail = detail
        super().__init__(f"cannot reach Temporal at {address}: {detail}")


class ReapRefused(RuntimeError):
    """The server would not delete a version record, and was reachable to say
    so. Almost always its poller check: a version whose worker stopped a minute
    ago still has pollers in the task-queue history. Not an operator's problem
    and not a retry loop's — the sweep after them converges (082-US3)."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class Deployments(Protocol):
    """What `deploy` needs from Temporal, and nothing else. A seam this narrow
    is what lets the whole verb be proven without a server."""

    def snapshot(self) -> DeploymentSnapshot: ...

    def set_current(self, build_id: str) -> None: ...

    def open_pinned(self, build_id: str) -> int: ...

    def delete(self, build_id: str) -> None: ...


def _run_command(argv: Sequence[str], *, cwd: Path | None = None) -> CommandResult:
    """`units._run_command`'s seam plus a working directory: `git worktree add`
    and `uv sync` are both about somewhere else."""
    finished = subprocess.run(  # noqa: S603 - fixed argv, no shell
        list(argv),
        capture_output=True,
        text=True,
        check=False,
        cwd=None if cwd is None else str(cwd),
    )
    return CommandResult(finished.returncode, (finished.stdout + finished.stderr).strip())


def deploy_lock_target(layout: InstallLayout) -> Path:
    """What the deploy lock guards (spec edge case: two deploys racing).

    Beside the deployments root rather than inside it, so a refusal before
    anything moves has genuinely created nothing under `deployments/`."""
    return layout.deployments_dir


def version_state(build_id: str, *, current: str | None, drainage: str) -> str:
    """What to call a version, given who is current and what it is draining —
    the mapping onto the three words FR-010 promises, kept pure."""
    if build_id == current:
        return "current"
    if drainage in ("draining", "drained"):
        return drainage
    return "inactive"


# --- 082-US3: the reap, decided purely and acted on idempotently -------------

#: The one state a version has to be in before anything is taken from it. Not
#: "inactive" and not "draining": FR-005 says *has completed* draining, and the
#: server is the only thing that knows when that became true.
DRAINED = "drained"


@dataclasses.dataclass(frozen=True)
class ReapTarget:
    """A version to take off this host, and the unit of it that is here.

    `unit` is `None` when no instance for this version is loaded — the version
    was deployed on another host, or an earlier sweep already stopped it. Its
    checkout and its record are still this host's to clean, which is why the
    decision reports the difference instead of the sweep guessing at it.
    """

    build_id: str
    unit: str | None


def reapable(
    snapshot: DeploymentSnapshot,
    *,
    open_work: Mapping[str, int],
    units: Collection[str],
) -> tuple[ReapTarget, ...]:
    """Which versions have nothing left on them (FR-005).

    Pure, and that is the point: the two properties this story is judged on are
    negative ones — the current version is never taken, and neither is a version
    with open pinned work — and a negative property proven against a live floor
    is proven by *not* observing something, once. Here each is a returned value.

    `open_work` maps a build id to how many open workflows are pinned to it. A
    build id **missing** from that mapping is one the server could not be asked
    about, and unknown is not zero: a reap cannot be undone, so a version whose
    open work could not be read stays exactly where it is.
    """
    return tuple(
        ReapTarget(
            state.build_id,
            worker_instance(state.build_id)
            if worker_instance(state.build_id) in units
            else None,
        )
        for state in snapshot.versions
        # The control, by name (US3-S2). It is redundant with the state check
        # below for any snapshot the server produced — `version_state` calls the
        # current version "current" whatever its drainage says — and it stays
        # anyway, because "never the current one" is the rule an operator relies
        # on, not an emergent property of how the state string is computed.
        if state.build_id != snapshot.current
        and state.state == DRAINED
        and open_work.get(state.build_id) == 0
    )


@dataclasses.dataclass(frozen=True)
class Reaped:
    """What one version's reap did, or why it stopped where it did."""

    build_id: str
    unit: str | None
    checkout: Path
    #: `None` when the version is gone from this host, root and branch. When it
    #: is set, everything up to that point still happened and a later sweep
    #: picks up from there: every act in `_reap` is a no-op once it has run.
    deferred: str | None = None

    @property
    def note(self) -> str:
        if self.deferred is None:
            return f"reaped drained version {self.build_id}"
        return f"version {self.build_id} not fully reaped: {self.deferred}"


@dataclasses.dataclass(frozen=True)
class SweepReport:
    """What one sweep took, and what it could not."""

    reaped: tuple[Reaped, ...] = ()
    #: Why no decision was taken at all — Temporal away, or a deploy holding
    #: the lock. Distinct from an empty `reaped`, which means the floor was
    #: read and had nothing on it to take.
    unavailable: str | None = None

    @property
    def notes(self) -> tuple[str, ...]:
        """One line each, for the probe's verdict (042 FR-013)."""
        if self.unavailable is not None:
            return (f"version sweep skipped: {self.unavailable}",)
        return tuple(one.note for one in self.reaped)

    def render(self) -> str:
        if self.unavailable is not None:
            return f"version sweep skipped: {self.unavailable}"
        if not self.reaped:
            return "reaped nothing: no version has finished draining"
        return "\n".join(
            ["reaped:"]
            + [
                f"  {one.build_id}  "
                + (
                    "unit stopped and disabled, checkout removed, record deleted"
                    if one.deferred is None
                    else one.deferred
                )
                for one in self.reaped
            ]
        )


@dataclasses.dataclass(frozen=True)
class DeployReport:
    """What a deploy did, and what is on the floor now (FR-010)."""

    build_id: str
    checkout: Path
    unit: str
    already_current: bool
    versions: tuple[VersionState, ...] = ()
    degraded: str | None = None
    #: What the tail of this deploy reaped (082-US3), when it got that far.
    swept: SweepReport | None = None

    def render(self) -> str:
        if self.degraded:
            headline = [
                f"DEGRADED: {self.degraded}",
                f"  the unit {self.unit} is left running and no version was made "
                "current;",
                f"  read `journalctl --user -u {self.unit}`, then re-run "
                f"`ergane worker deploy {self.build_id}` to converge",
            ]
        else:
            verb = "already current" if self.already_current else "now current"
            headline = [
                f"deployed {self.build_id}: {verb}",
                f"  checkout: {self.checkout}",
                f"  unit: {self.unit}",
            ]
        # Every version, always: a drain that will not finish is a list that
        # does not shrink, which is only visible if the list is printed.
        return "\n".join(
            headline
            + ["versions of this deployment:"]
            + [f"  {state.build_id}  {state.state}" for state in self.versions]
            + ([self.swept.render()] if self.swept is not None else [])
        )


def deploy(
    layout: InstallLayout,
    revision: str | None = None,
    *,
    deployments: Deployments | None = None,
    run: Runner | None = None,
    wait_s: float = REGISTRATION_WAIT_S,
    poll_s: float = REGISTRATION_POLL_S,
    now: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    lock_timeout_s: float = DEPLOY_LOCK_TIMEOUT_S,
) -> DeployReport:
    """Put `revision` on the floor beside whatever is already there (FR-003)."""
    runner = _run_command if run is None else run
    directory = TemporalDeployments() if deployments is None else deployments
    try:
        with exclusive_lock(deploy_lock_target(layout), timeout_s=lock_timeout_s):
            return _deploy(layout, revision, directory, runner, wait_s, poll_s,
                           now, sleep)
    except LockUnavailable as error:
        raise OperatorError(
            f"another deploy holds the lock on {error.target} (waited "
            f"{error.timeout_s:g}s); it is the one putting a version on the "
            "floor — let it finish, then re-run this one, which converges"
        ) from None


def _deploy(
    layout: InstallLayout,
    revision: str | None,
    directory: Deployments,
    run: Runner,
    wait_s: float,
    poll_s: float,
    now: Callable[[], float],
    sleep: Callable[[float], None],
) -> DeployReport:
    source = layout.install_root
    sha, build_id = _commit_to_deploy(source, revision, run)
    _require_host(run)
    # The last question before the first change: a `git worktree add` and a
    # `uv sync` are minutes, and finding the server gone after them leaves a
    # frozen checkout with nothing to register against.
    snapshot = _ask(directory)

    tree = layout.deployment_tree(build_id)
    _freeze(tree, sha, source, run)
    _sync(tree, run)

    unit = worker_instance(build_id)
    _start(unit, run)

    registered, snapshot = _await_registration(
        directory, build_id, wait_s=wait_s, poll_s=poll_s, now=now, sleep=sleep
    )
    if not registered:
        return DeployReport(
            build_id=build_id,
            checkout=tree,
            unit=unit,
            already_current=False,
            versions=snapshot.versions,
            degraded=(
                f"version {build_id} did not register with Temporal within "
                f"{wait_s:g}s"
            ),
        )

    already_current = snapshot.current == build_id
    if not already_current:
        _set_current(directory, build_id)

    # 082-US3: the tail of a deploy is the moment a version most often becomes
    # reapable — the one this deploy just replaced starts draining here — and it
    # is also the moment an operator is watching. Inside the lock this deploy
    # already holds, so `sweep`'s own acquisition would deadlock on it (`flock`
    # contends between two descriptions in one process, by design: see
    # `factory/locking.py`).
    swept = _sweep(layout, directory, run)

    return DeployReport(
        build_id=build_id,
        checkout=tree,
        unit=unit,
        already_current=already_current,
        # Read back after the sweep rather than after the promotion, so the list
        # is the floor as the operator will find it, not as it was mid-verb.
        versions=_ask(directory).versions,
        swept=swept,
    )


# --- the refusals, all of them before anything moves (FR-004) ---------------


def _commit_to_deploy(
    source: Path, revision: str | None, run: Runner
) -> tuple[str, str]:
    """The commit, and the build id it will register as.

    The build id is asked of git rather than sliced off the sha: the worker
    establishes its own with `git rev-parse --short HEAD` in the frozen checkout
    (082-US1), and a version whose halves disagree on how long "short" is
    refuses to boot."""
    if run(("git", "rev-parse", "--git-dir"), cwd=source).code != 0:
        raise OperatorError(
            f"{source} is not a git checkout, so there is no commit to deploy. "
            "A wheel or an unpacked tree is static code with no sha to be "
            "accountable to. Run this from the operator's checkout."
        )
    dirt = run(("git", "status", "--porcelain"), cwd=source).out if not revision else ""
    if dirt:
        raise OperatorError(
            f"{source} has uncommitted changes ({dirt.splitlines()[0].strip()}) "
            "and no revision was named. A deploy ships commits: there is no sha "
            "for a dirty tree to be accountable to. Commit them, or name the "
            "revision to deploy."
        )
    named = revision or "HEAD"
    resolved = run(
        ("git", "rev-parse", "--verify", "--quiet", f"{named}^{{commit}}"), cwd=source
    )
    if resolved.code != 0 or not resolved.out:
        raise OperatorError(
            f"{named!r} does not resolve to a commit in {source}. Deploy takes a "
            "revision git can name — sha, tag, branch — because the build id it "
            "registers is that commit's short sha."
        )
    sha = resolved.out.split()[0]
    short = run(("git", "rev-parse", "--short", sha), cwd=source)
    if short.code != 0 or not short.out:
        raise OperatorError(f"git could not shorten {sha} in {source}")
    return sha, short.out.split()[0]


def _require_host(run: Runner) -> None:
    """A session to start the unit in (FR-004)."""
    if run(("systemctl", "--user", "show", "--property=Version")).code != 0:
        raise OperatorError(
            "the systemd user session is not reachable, so a versioned worker "
            "cannot be started or supervised — usually a session with no bus; "
            "`loginctl enable-linger` and a login session fix it."
        )


def _ask(directory: Deployments) -> DeploymentSnapshot:
    try:
        return directory.snapshot()
    except DeploymentsUnavailable as error:
        raise OperatorError(
            f"cannot reach Temporal at {error.address} to read the "
            f"'ergane-worker' deployment ({error.detail}); a deploy that cannot "
            "read it can neither await a registration nor set a current "
            "version, so nothing was started",
            EXIT_TRANSPORT,
        ) from None


def _set_current(directory: Deployments, build_id: str) -> None:
    try:
        directory.set_current(build_id)
    except DeploymentsUnavailable as error:
        raise OperatorError(
            f"{build_id} registered, but Temporal at {error.address} did not "
            f"accept it as current ({error.detail}); its unit is left running — "
            f"re-run `ergane worker deploy {build_id}` to converge",
            EXIT_TRANSPORT,
        ) from None


# --- the acts, each of them a no-op when it has already happened -------------


def _freeze(tree: Path, sha: str, source: Path, run: Runner) -> None:
    """The frozen checkout, outside the operator's own (plan trap 2).

    `worktree add` not a clone, so the deployment shares the object database;
    `--detach` because a version is a commit, not a branch that could move under
    it; skipped when the tree is there, which is what makes a re-run converge."""
    if tree.exists():
        return
    tree.parent.mkdir(parents=True, exist_ok=True)
    result = run(("git", "worktree", "add", "--detach", str(tree), sha), cwd=source)
    if result.code != 0:
        raise OperatorError(f"could not freeze {sha} into {tree}: {result.out}")


def _sync(tree: Path, run: Runner) -> None:
    """The deployment's own environment, from its own lockfile.

    `--frozen` on purpose: resolving fresh dependencies would give a version the
    commit's code and today's environment — the drift this spec exists to end."""
    result = run(("uv", "sync", "--frozen"), cwd=tree)
    if result.code != 0:
        raise OperatorError(
            f"`uv sync --frozen` failed in {tree}: {result.out}. The frozen "
            "checkout is left in place; fix the environment and re-run the same "
            "deploy, which converges."
        )


def _start(unit: str, run: Runner) -> None:
    """Start the instance, enabled so a reboot brings the floor back up.

    `enable --now` on a unit already both exits 0 — convergent and correct."""
    result = run(("systemctl", "--user", "enable", "--now", unit))
    if result.code != 0:
        raise OperatorError(f"could not start {unit}: {result.out}")


def _await_registration(
    directory: Deployments,
    build_id: str,
    *,
    wait_s: float,
    poll_s: float,
    now: Callable[[], float],
    sleep: Callable[[float], None],
) -> tuple[bool, DeploymentSnapshot]:
    """Wait, bounded, for the new worker to register its version (trap 7).

    Returns the last snapshot either way: a floor with a version that will not
    start is when an operator most needs the rest of the list."""
    deadline = now() + wait_s
    while True:
        snapshot = _ask(directory)
        if any(state.build_id == build_id for state in snapshot.versions):
            return True, snapshot
        remaining = deadline - now()
        if remaining <= 0:
            return False, snapshot
        sleep(min(poll_s, remaining))


# --- the sweep: what acts on the decision (FR-005) ---------------------------


def sweep(
    layout: InstallLayout,
    *,
    deployments: Deployments | None = None,
    run: Runner | None = None,
    lock_timeout_s: float = SWEEP_LOCK_TIMEOUT_S,
) -> SweepReport:
    """Take every drained version off this host, and report what happened.

    Raises nothing. Its two callers are the probe's timer and the tail of a
    deploy, and neither has anywhere to put an exception: a sweep that cannot
    reach Temporal is a note on a floor that has a bigger problem, and a sweep
    that finds a deploy holding the lock has one job, which is to leave.
    """
    runner = _run_command if run is None else run
    directory = TemporalDeployments() if deployments is None else deployments
    try:
        with exclusive_lock(deploy_lock_target(layout), timeout_s=lock_timeout_s):
            return _sweep(layout, directory, runner)
    except LockUnavailable:
        # Not a failure. A deploy is mid-`uv sync` on a version the server has
        # not been told about yet; the next firing of the timer converges.
        return SweepReport(
            unavailable="a deploy holds the deployment lock; the next sweep converges"
        )


def _sweep(layout: InstallLayout, directory: Deployments, run: Runner) -> SweepReport:
    """The sweep proper, with the lock already held by the caller."""
    try:
        snapshot = directory.snapshot()
        open_work = {
            state.build_id: directory.open_pinned(state.build_id)
            for state in snapshot.versions
            if state.build_id != snapshot.current
        }
    except DeploymentsUnavailable as error:
        return SweepReport(unavailable=str(error))

    targets = reapable(snapshot, open_work=open_work, units=_instances(run))
    return SweepReport(tuple(_reap(layout, target, directory, run) for target in targets))


def _instances(run: Runner) -> tuple[str, ...]:
    """Every versioned worker instance this host has loaded.

    `--all`, because an instance that is enabled but not running still has a
    symlink to remove, and `disable` is how it is removed. A host with no user
    session answers nothing, which reads as no units — correct, and the reap
    then takes only the checkout and the record.
    """
    listed = run(
        (
            "systemctl",
            "--user",
            "list-units",
            "--all",
            "--plain",
            "--no-legend",
            worker_instance("*"),
        )
    )
    if listed.code != 0:
        return ()
    return tuple(
        line.split()[0] for line in listed.out.splitlines() if line.split()
    )


def _reap(
    layout: InstallLayout, target: ReapTarget, directory: Deployments, run: Runner
) -> Reaped:
    """Take one version off the host, in the only order that is safe.

    The unit first, because removing the checkout out from under a running
    worker is strictly worse than leaving a directory on disk for a cycle. The
    record last, because a version whose pollers the server can still see is one
    it refuses to delete — probed on the dev server, 1.31.2, seconds after that
    version's worker had shut down:

        version 'probe-082-us3:v1' cannot be deleted since it has active pollers

    That refusal is not an error and not a retry loop: pollers age out of the
    server's task-queue history on its own clock (~5 minutes, measured), so the
    deletion lands on a later sweep and every step above it is a no-op by then.
    """
    checkout = layout.deployment_tree(target.build_id)

    # The spec's edge case, and the reason the count is read twice: the decision
    # was taken against a floor that a dispatch may have changed since. Reading
    # it again immediately before the first irreversible act is what makes the
    # window this narrow.
    try:
        open_now = directory.open_pinned(target.build_id)
    except DeploymentsUnavailable as error:
        return Reaped(target.build_id, target.unit, checkout, error.detail)
    if open_now:
        return Reaped(
            target.build_id,
            target.unit,
            checkout,
            f"{open_now} workflow(s) pinned to it are open again — it was idle "
            "when the sweep decided and is not now",
        )

    if target.unit is not None:
        # One verb for both halves of FR-005: `--now` stops it, `disable`
        # removes the symlink that would start it again at the next boot.
        stopped = run(("systemctl", "--user", "disable", "--now", target.unit))
        if stopped.code != 0:
            return Reaped(
                target.build_id,
                target.unit,
                checkout,
                f"its unit {target.unit} would not stop ({stopped.out}), so its "
                "checkout was left where it is",
            )

    refused = _remove_checkout(checkout, layout.install_root, run)
    if refused is not None:
        return Reaped(target.build_id, target.unit, checkout, refused)

    try:
        directory.delete(target.build_id)
    except (DeploymentsUnavailable, ReapRefused) as error:
        return Reaped(
            target.build_id,
            target.unit,
            checkout,
            f"unit and checkout are gone; the server kept the record ({error.detail})",
        )
    return Reaped(target.build_id, target.unit, checkout)


def _remove_checkout(checkout: Path, source: Path, run: Runner) -> str | None:
    """Remove a frozen checkout the way git can account for (plan trap 3).

    `git worktree add` wrote the deployment into the *main* repository's `.git`,
    so a bare `rm -rf` leaves a registration behind that nothing here would ever
    clean. Removal goes through git, which also refuses any path that is not one
    of this repository's worktrees — a safety a recursive delete of a computed
    path does not have. `--force` because the dirt in there is the venv and the
    bytecode this deployment itself wrote, and `prune` afterwards because a tree
    already gone by other means still has its registration.
    """
    if checkout.exists():
        removed = run(("git", "worktree", "remove", "--force", str(checkout)), cwd=source)
        if removed.code != 0:
            run(("git", "worktree", "prune"), cwd=source)
            if checkout.exists():
                return (
                    f"`git worktree remove` refused its checkout at {checkout} "
                    f"({removed.out}); it is still on disk, and nothing here "
                    "will delete it any other way"
                )
    run(("git", "worktree", "prune"), cwd=source)
    _drop_if_empty(checkout.parent)
    return None


def _drop_if_empty(directory: Path) -> None:
    """The `deployments/<build-id>/` wrapper git never knew about.

    `rmdir`, never a recursive delete: the checkout inside it was git's, and an
    empty directory is the only thing this is allowed to be sure about.
    """
    try:
        directory.rmdir()
    except OSError:
        return


class TemporalDeployments:
    """The deployment directory, over the server's own worker-deployment API.

    A fresh connection per question: the poll asks every couple of seconds, a
    connection is milliseconds, and a server that goes away mid-wait surfaces as
    the same refusal as one never there."""

    def __init__(self, *, deployment_name: str | None = None) -> None:
        from factory.controlplane.resolve import resolve_temporal_target
        from factory.versioning import DEPLOYMENT_NAME

        self._name = DEPLOYMENT_NAME if deployment_name is None else deployment_name
        target = resolve_temporal_target()
        self._address = target.address
        self._namespace = target.namespace

    def snapshot(self) -> DeploymentSnapshot:
        return self._call(self._describe)

    def set_current(self, build_id: str) -> None:
        self._call(lambda client: self._set_current(client, build_id))

    def open_pinned(self, build_id: str) -> int:
        """How many open workflows are pinned to this version (082-US3)."""
        return self._call(
            lambda client: client.count_workflows(open_pinned_query(build_id, self._name))
        ).count

    def delete(self, build_id: str) -> None:
        self._call(lambda client: self._delete(client, build_id))

    # -- the plumbing ---------------------------------------------------------

    def _call(self, question):  # type: ignore[no-untyped-def]
        import asyncio

        from temporalio.client import Client
        from temporalio.service import RPCError

        async def asked():  # type: ignore[no-untyped-def]
            try:
                client = await Client.connect(self._address, namespace=self._namespace)
                return await question(client)
            except ReapRefused:
                # A reached server saying no. It is a `RuntimeError`, so without
                # this it would be reported as a server that could not be
                # reached — and the sweep would call a refusal an outage.
                raise
            except (RPCError, RuntimeError, OSError) as error:
                # temporalio raises a bare RuntimeError on a dead port, hence the
                # base class. Caught *inside* the coroutine so `asyncio.run`'s
                # own RuntimeError — a caller already holding a loop — reports
                # the programming error it is rather than a server that is away.
                raise DeploymentsUnavailable(self._address, str(error)) from None

        return asyncio.run(asked())

    async def _describe(self, client):  # type: ignore[no-untyped-def]
        from temporalio.api.workflowservice.v1 import DescribeWorkerDeploymentRequest
        from temporalio.service import RPCError, RPCStatusCode

        try:
            response = await self._service(client).describe_worker_deployment(
                DescribeWorkerDeploymentRequest(
                    namespace=self._namespace, deployment_name=self._name
                )
            )
        except RPCError as error:
            if error.status == RPCStatusCode.NOT_FOUND:
                # No worker has ever registered a version. Not an error: it is
                # the state of a floor on the day before its first deploy.
                return DeploymentSnapshot(current=None, versions=())
            raise
        info = response.worker_deployment_info
        current = info.routing_config.current_deployment_version.build_id or None
        states = [
            VersionState(
                summary.deployment_version.build_id,
                version_state(
                    summary.deployment_version.build_id,
                    current=current,
                    drainage=_drainage(summary.drainage_status),
                ),
            )
            for summary in info.version_summaries
        ]
        return DeploymentSnapshot(
            current=current, versions=tuple(sorted(states, key=lambda one: one.build_id))
        )

    @staticmethod
    def _service(client):  # type: ignore[no-untyped-def]
        return client.service_client.workflow_service

    async def _delete(self, client, build_id: str) -> None:  # type: ignore[no-untyped-def]
        from temporalio.api.deployment.v1 import (
            WorkerDeploymentVersion as VersionMessage,
        )
        from temporalio.api.workflowservice.v1 import (
            DeleteWorkerDeploymentVersionRequest,
        )
        from temporalio.service import RPCError, RPCStatusCode

        try:
            await self._service(client).delete_worker_deployment_version(
                DeleteWorkerDeploymentVersionRequest(
                    namespace=self._namespace,
                    deployment_version=VersionMessage(
                        deployment_name=self._name, build_id=build_id
                    ),
                    # False on purpose. The server re-checks drainage before it
                    # deletes, which makes this call a second lock on the same
                    # door as `reapable`'s drained check — and the one lock this
                    # process cannot talk itself past.
                    skip_drainage=False,
                    identity="ergane version sweep",
                )
            )
        except RPCError as error:
            if error.status == RPCStatusCode.NOT_FOUND:
                # Already gone: an earlier sweep, or another host. Convergence
                # is the whole design, so arriving second is a success.
                return
            raise ReapRefused(error.message) from None

    async def _set_current(self, client, build_id: str) -> None:  # type: ignore[no-untyped-def]
        from temporalio.api.workflowservice.v1 import (
            DescribeWorkerDeploymentRequest,
            SetWorkerDeploymentCurrentVersionRequest,
        )

        service = self._service(client)
        described = await service.describe_worker_deployment(
            DescribeWorkerDeploymentRequest(
                namespace=self._namespace, deployment_name=self._name
            )
        )
        await service.set_worker_deployment_current_version(
            SetWorkerDeploymentCurrentVersionRequest(
                namespace=self._namespace,
                deployment_name=self._name,
                build_id=build_id,
                conflict_token=described.conflict_token,
                identity="ergane worker deploy",
                # One task queue (`workgraph`) — the flag is for the version
                # being replaced: one that polled a queue this does not would
                # otherwise refuse the promotion of correct code.
                ignore_missing_task_queues=True,
            )
        )


def open_pinned_query(build_id: str, deployment_name: str) -> str:
    """The visibility query counting what is still pinned to a version.

    **The separator is a colon, and getting it wrong is silent.** The SDK's own
    `WorkerDeploymentVersion.to_canonical_string()` joins with a *dot*, and
    visibility indexes `TemporalWorkerDeploymentVersion` with a colon — probed
    on the dev server, 1.31.2, against a version with one open pinned workflow:

        TemporalWorkerDeploymentVersion = "probe-082-us3.v1"  -> []
        TemporalWorkerDeploymentVersion = "probe-082-us3:v1"  -> ['probe-082-us3-open']

    The dotted form does not error. It answers zero, forever, for every version
    — and a zero here is what tells the sweep a version is finished with. That
    is the difference between a reaper and a reaper that deletes the version an
    epic is running on, so the string is built here, once, and nowhere else.
    """
    return (
        f'TemporalWorkerDeploymentVersion = "{deployment_name}:{build_id}" '
        f'AND ExecutionStatus = "{_OPEN_STATUS}"'
    )


#: Temporal's one open execution status. Spelled here rather than imported from
#: `roadmap_activities` so this module keeps its module-scope import list free
#: of anything that reaches an activity or a client (the probe imports it).
_OPEN_STATUS = "Running"


def _drainage(status: int) -> str:
    """The server's drainage enum in this module's own words. Imported inside
    the function like every Temporal name here: this module sits beside the
    probe, which runs when Temporal is what died."""
    from temporalio.api.enums.v1 import VersionDrainageStatus

    if status == VersionDrainageStatus.VERSION_DRAINAGE_STATUS_DRAINING:
        return "draining"
    if status == VersionDrainageStatus.VERSION_DRAINAGE_STATUS_DRAINED:
        return "drained"
    return ""
