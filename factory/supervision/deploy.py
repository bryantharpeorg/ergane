"""082-US2: `ergane worker deploy` — new code on the floor, old code untouched.

The verb the operator asked for, in the shape he asked for it: "draining off of
one worker while the next worker is already taking new work." A deploy freezes a
commit into a checkout of its own, gives it its own dependency environment,
starts it as an instance of the versioned unit template, waits for it to
register with Temporal, and makes it current. Nothing is restarted, so nothing
in flight is cancelled — the attempts already running stay pinned to the version
that started them (US1's `versioning_behavior`), and the version they are pinned
to keeps serving them until the last one closes.

Four properties are load-bearing, and each is a way this could have gone wrong:

**Every refusal happens before anything moves** (FR-004). A tree that is not a
git checkout, a revision that is not a commit, a dirty tree with no revision
named, a systemd session that is not there, a Temporal server that is not
answering: all five are established while the only thing this module has done is
ask questions. A refusal that has already created a worktree and synced a venv
is not a refusal, it is a half-deploy the operator now has to clean up.

**Re-running converges** (FR-003). The checkout is created only if it is not
there, the unit is enabled only if it is not running, the version is made
current only if it is not already. This is not politeness: it is the entire
recovery story, because a registration timeout deliberately leaves the unit
running (US2-S5) and the way out of that state is the same command again.

**The wait is bounded and its timeout is not a rollback** (plan trap 7).
`set-current-version` against a version no worker has registered fails, so the
poll has to come first; and a poll that never succeeds must leave the unit up,
because the journal of the worker that would not start is the only evidence of
why. Tearing it down would delete the answer.

**The report is read back from the server, never composed** (FR-010). What is on
the floor right now is a question only the deployment directory can answer, and
an operator watching a drain that will not finish needs the list to be the
server's rather than this process's opinion of it.
"""

from __future__ import annotations

import dataclasses
import subprocess
import time
from pathlib import Path
from typing import Callable, Protocol, Sequence

from factory.cli.errors import EXIT_TRANSPORT, OperatorError
from factory.locking import LockUnavailable, exclusive_lock
from factory.supervision.units import (
    WORKER_TEMPLATE_UNIT,
    CommandResult,
    InstallLayout,
    worker_instance,
)

#: How long to wait for a competing deploy to finish. Short on purpose: the
#: loser reports the winner rather than queueing behind a `uv sync`.
DEPLOY_LOCK_TIMEOUT_S = 5.0

#: How long a newly started instance has to register its version, and how often
#: it is asked. A cold `uv sync` is already done by this point, so what remains
#: is process start plus one Temporal round trip.
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
    """The deployment directory could not be reached or read.

    Raised by the Temporal seam and translated into FR-004's named refusal by
    `deploy`, so that a fake in a test refuses on exactly the path the real
    server refuses on.
    """

    def __init__(self, address: str, detail: str) -> None:
        self.address = address
        self.detail = detail
        super().__init__(f"cannot reach Temporal at {address}: {detail}")


class Deployments(Protocol):
    """What `deploy` needs from Temporal, and nothing else.

    Two questions, one of them twice. Keeping the seam this narrow is what lets
    the whole verb — the refusals, the ordering, the bounded wait, the report —
    be proven without a server.
    """

    def snapshot(self) -> DeploymentSnapshot: ...

    def set_current(self, build_id: str) -> None: ...


class Runner(Protocol):
    """One command, optionally somewhere else."""

    def __call__(
        self, argv: Sequence[str], *, cwd: Path | None = None
    ) -> CommandResult: ...


def _run_command(argv: Sequence[str], *, cwd: Path | None = None) -> CommandResult:
    """Run one command. The seam every test in this story closes.

    Same shape as `units._run_command` and the same reason — nothing in the
    suite may reach the session running the factory — with a working directory,
    because `git worktree add` and `uv sync` are both about somewhere else.
    """
    finished = subprocess.run(  # noqa: S603 - fixed argv, no shell
        list(argv),
        capture_output=True,
        text=True,
        check=False,
        cwd=None if cwd is None else str(cwd),
    )
    return CommandResult(finished.returncode, (finished.stdout + finished.stderr).strip())


def deploy_lock_target(layout: InstallLayout) -> Path:
    """What the deploy lock guards: the deployments root, as a sidecar.

    The lock file is `deployments.lock` beside the root rather than inside it,
    so a refusal that happens before anything moves has genuinely created
    nothing under `deployments/` (spec edge case: two deploys racing).
    """
    return layout.deployments_dir


def version_state(build_id: str, *, current: str | None, drainage: str) -> str:
    """What to call a version, given who is current and what it is draining.

    Pure, and separate from the server call, because "current / draining /
    drained" is the vocabulary FR-010 promises an operator and the mapping from
    two server fields onto it is the part worth being able to read.
    """
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
        # Every version, always — a drain that will not finish is a list that
        # does not shrink, and that is only visible if the list is printed.
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
            return _deploy(
                layout,
                revision,
                directory=directory,
                run=runner,
                wait_s=wait_s,
                poll_s=poll_s,
                now=now,
                sleep=sleep,
            )
    except LockUnavailable as error:
        raise OperatorError(
            f"another deploy holds the lock on {error.target} (waited "
            f"{error.timeout_s:g}s); it is the one putting a version on the "
            "floor — let it finish, then re-run this one, which converges"
        ) from None


def _deploy(
    layout: InstallLayout,
    revision: str | None,
    *,
    directory: Deployments,
    run: Runner,
    wait_s: float,
    poll_s: float,
    now: Callable[[], float],
    sleep: Callable[[float], None],
) -> DeployReport:
    source = layout.install_root
    _require_checkout(source, run)
    if revision is None:
        _require_clean(source, run)
    sha = _resolve_commit(source, revision or "HEAD", run)
    build_id = _short(source, sha, run)
    _require_template(layout)
    _require_systemd(run)
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


def _require_checkout(source: Path, run: Runner) -> None:
    if run(("git", "rev-parse", "--git-dir"), cwd=source).code != 0:
        raise OperatorError(
            f"{source} is not a git checkout, so there is no commit to deploy. "
            "A deploy ships a revision — a wheel or an unpacked tree is static "
            "code with no sha to be accountable to, and has nothing to roll "
            "forward from. Run this from the operator's checkout."
        )


def _require_clean(source: Path, run: Runner) -> None:
    dirt = run(("git", "status", "--porcelain"), cwd=source).out
    if dirt:
        first = dirt.splitlines()[0].strip()
        raise OperatorError(
            f"{source} has uncommitted changes ({first}) and no revision was "
            "named. A deploy ships commits: there is no sha for a dirty tree to "
            "be accountable to, and the version it registered could never be "
            "mapped back to code. Commit them, or name the revision to deploy."
        )


def _resolve_commit(source: Path, revision: str, run: Runner) -> str:
    resolved = run(
        ("git", "rev-parse", "--verify", "--quiet", f"{revision}^{{commit}}"),
        cwd=source,
    )
    if resolved.code != 0 or not resolved.out:
        raise OperatorError(
            f"{revision!r} does not resolve to a commit in {source}. Deploy takes "
            "a revision git can name — a sha, a tag, a branch — because the build "
            "id it registers is that commit's short sha."
        )
    return resolved.out.split()[0]


def _short(source: Path, sha: str, run: Runner) -> str:
    """The build id: the same spelling `_worker_revision()` will read back.

    Asked of git rather than sliced off the sha here, because the worker
    establishes its own build id with `git rev-parse --short HEAD` inside the
    frozen checkout (082-US1), and a version whose two halves disagree about how
    many characters "short" is refuses to boot.
    """
    answer = run(("git", "rev-parse", "--short", sha), cwd=source)
    if answer.code != 0 or not answer.out:
        raise OperatorError(f"git could not shorten {sha} in {source}")
    return answer.out.split()[0]


def _require_template(layout: InstallLayout) -> None:
    template = layout.unit_dir / WORKER_TEMPLATE_UNIT
    if not template.is_file():
        raise OperatorError(
            f"{template} is not there, so there is no unit to start an instance "
            "of. It is written by `ergane worker install`, which this host has "
            "either not run or last ran before versioned units existed — run it "
            "again, then deploy."
        )


def _require_systemd(run: Runner) -> None:
    if run(("systemctl", "--user", "show", "--property=Version")).code != 0:
        raise OperatorError(
            "the systemd user session is not reachable, so a versioned worker "
            "cannot be started or supervised. On a host that has one, this is "
            "usually a session without a bus (`systemctl --user` from a bare "
            "shell); `loginctl enable-linger` and a login session fix it."
        )


def _ask(directory: Deployments) -> DeploymentSnapshot:
    try:
        return directory.snapshot()
    except DeploymentsUnavailable as error:
        raise OperatorError(
            f"cannot reach Temporal at {error.address} to read the "
            f"'ergane-worker' deployment ({error.detail}); a deploy that cannot "
            "read the deployment cannot wait for the new version to register or "
            "make it current, so nothing was started",
            EXIT_TRANSPORT,
        ) from None


def _set_current(directory: Deployments, build_id: str) -> None:
    try:
        directory.set_current(build_id)
    except DeploymentsUnavailable as error:
        raise OperatorError(
            f"the version {build_id} registered, but Temporal at {error.address} "
            f"did not accept it as current ({error.detail}); its unit is left "
            f"running — re-run `ergane worker deploy {build_id}` to converge",
            EXIT_TRANSPORT,
        ) from None


# --- the acts, each of them a no-op when it has already happened -------------


def _freeze(tree: Path, sha: str, source: Path, run: Runner) -> None:
    """The frozen checkout, outside the operator's own (plan trap 2).

    `git worktree add` rather than a clone so the deployment shares the object
    database it came from, and `--detach` because a version is a commit and not
    a branch that could move under it. Skipped when the tree is already there,
    which is what makes a second deploy of the same revision converge instead of
    failing on an existing directory.
    """
    if tree.exists():
        return
    tree.parent.mkdir(parents=True, exist_ok=True)
    result = run(("git", "worktree", "add", "--detach", str(tree), sha), cwd=source)
    if result.code != 0:
        raise OperatorError(f"could not freeze {sha} into {tree}: {result.out}")


def _sync(tree: Path, run: Runner) -> None:
    """The deployment's own dependency environment, from its own lockfile.

    `--frozen` on purpose: a deployment resolving fresh dependencies is a
    version whose code is the commit's and whose environment is today's, which
    is exactly the drift this spec exists to end. Re-run every time — a
    half-synced venv from an interrupted deploy converges here.
    """
    result = run(("uv", "sync", "--frozen"), cwd=tree)
    if result.code != 0:
        raise OperatorError(
            f"`uv sync --frozen` failed in {tree}: {result.out}. The frozen "
            "checkout is left in place; fix the environment and re-run the same "
            "deploy, which converges."
        )


def _start(unit: str, run: Runner) -> None:
    """Start the instance, enabled so a reboot brings the floor back up.

    `enable --now` on a unit that is already both is a no-op that exits 0, so
    this is the convergent spelling as well as the correct one.
    """
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

    Returns the last snapshot either way: the report names every version even
    when this one never showed up, because a floor with a version that will not
    start is exactly when an operator needs to see the rest of the list.
    """
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

    A fresh connection per question rather than one held open: the poll asks
    every couple of seconds at most, a connection is milliseconds, and a server
    that goes away *during* the wait then surfaces as the same named refusal as
    one that was never there.
    """

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
            client = await Client.connect(self._address, namespace=self._namespace)
            return await question(client)

        try:
            return asyncio.run(asked())
        except DeploymentsUnavailable:
            raise
        except (RPCError, RuntimeError, OSError) as error:
            # temporalio raises a bare RuntimeError on a dead port, which is why
            # this catches the base class rather than a transport-specific one.
            raise DeploymentsUnavailable(self._address, str(error)) from None

    async def _describe(self, client):  # type: ignore[no-untyped-def]
        from temporalio.api.workflowservice.v1 import DescribeWorkerDeploymentRequest
        from temporalio.service import RPCError, RPCStatusCode

        try:
            response = await client.service_client.workflow_service.describe_worker_deployment(
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
        return DeploymentSnapshot(
            current=current,
            versions=tuple(
                sorted(
                    (
                        VersionState(
                            summary.deployment_version.build_id,
                            version_state(
                                summary.deployment_version.build_id,
                                current=current,
                                drainage=_drainage(summary.drainage_status),
                            ),
                        )
                        for summary in info.version_summaries
                    ),
                    key=lambda state: state.build_id,
                )
            ),
        )

    async def _set_current(self, client, build_id: str) -> None:  # type: ignore[no-untyped-def]
        from temporalio.api.workflowservice.v1 import (
            DescribeWorkerDeploymentRequest,
            SetWorkerDeploymentCurrentVersionRequest,
        )

        service = client.service_client.workflow_service
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
                # The floor has one task queue (`workgraph`). The flag matters
                # for the version being replaced: a previously-current version
                # that polled a queue this one does not would otherwise refuse
                # the promotion of correct code.
                ignore_missing_task_queues=True,
            )
        )


def _drainage(status: int) -> str:
    """The server's drainage enum in this module's own three words.

    Imported inside the function like every other Temporal name here: this
    module sits beside `factory/supervision/probe.py`, which runs when Temporal
    is the thing that died, and neither of them should put a proto import on
    that path for the sake of a word.
    """
    from temporalio.api.enums.v1 import VersionDrainageStatus

    if status == VersionDrainageStatus.VERSION_DRAINAGE_STATUS_DRAINING:
        return "draining"
    if status == VersionDrainageStatus.VERSION_DRAINAGE_STATUS_DRAINED:
        return "drained"
    return ""
