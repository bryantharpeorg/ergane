"""082-US2: `ergane worker deploy` — new code on the floor, old code untouched.

The verb the operator asked for, in his shape: "draining off of one worker while
the next worker is already taking new work." A deploy freezes a commit into a
checkout of its own, gives it its own dependency environment, starts it as an
instance of the versioned unit template, waits for it to register, and makes it
current. Nothing is restarted, so nothing in flight is cancelled: attempts stay
pinned to the version that started them (US1), which serves them until the last
one closes.

Four properties are load-bearing. **Every refusal happens before anything
moves** (FR-004) — one that already created a worktree and synced a venv is a
half-deploy. **Re-running converges** (FR-003), which is the whole recovery
story, because a registration timeout deliberately leaves the unit running
(US2-S5). **The wait is bounded and its timeout is not a rollback** (trap 7):
`set-current-version` against an unregistered version fails, and a poll that
never succeeds leaves the unit up because that journal is the only evidence of
why. **The report is read back from the server** (FR-010), because an operator
watching a stuck drain needs the server's answer rather than ours.
"""

from __future__ import annotations

import dataclasses
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence

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


class Deployments(Protocol):
    """What `deploy` needs from Temporal, and nothing else. A seam this narrow
    is what lets the whole verb be proven without a server."""

    def snapshot(self) -> DeploymentSnapshot: ...

    def set_current(self, build_id: str) -> None: ...


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


@dataclasses.dataclass(frozen=True)
class DeployReport:
    """What a deploy did, and what is on the floor now (FR-010)."""

    build_id: str
    checkout: Path
    unit: str
    already_current: bool
    versions: tuple[VersionState, ...] = ()
    degraded: str | None = None

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
        snapshot = _ask(directory)

    return DeployReport(
        build_id=build_id,
        checkout=tree,
        unit=unit,
        already_current=already_current,
        versions=snapshot.versions,
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

    # -- the plumbing ---------------------------------------------------------

    def _call(self, question):  # type: ignore[no-untyped-def]
        import asyncio

        from temporalio.client import Client
        from temporalio.service import RPCError

        async def asked():  # type: ignore[no-untyped-def]
            try:
                client = await Client.connect(self._address, namespace=self._namespace)
                return await question(client)
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
