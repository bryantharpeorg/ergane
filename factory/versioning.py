"""Whether this worker declares which code it is, and what it declares (082-US1).

One decision, read once from the environment, consumed in two places that must
never disagree: the `Worker(...)` construction in `factory/worker.py`, and the
`versioning_behavior` argument on the four `@workflow.defn` decorators. It lives
here rather than in either of them because a floor where those two answers
differ is a floor that stalls.

**Why the decorator is gated too, and not only the worker keyword.** The obvious
shape — decorate the definitions unconditionally, add `deployment_config` only
when the environment asks — is wrong, and the dev server says so out loud. A
worker constructed without deployment options cannot complete a workflow task
for a definition that declares a behavior:

    Error while completing workflow activation
      error=code: 'Client specified an invalid argument',
      message: "versioning behavior cannot be specified without deployment
                options being set with versioned mode"

The task is retried, forever, and the epic never moves. Since FR-001 requires a
worker without the variable to behave *exactly* as today — this story lands dark
and US2 turns it on — the gate has to reach the decorator. The transcript is in
`specs/082-an-epic-finishes-on-the-code-it-started-with/evidence/us1-t001-t002-probes.md`
(part A).

`VersioningBehavior.UNSPECIFIED` is the disengaged value rather than `None`
because the SDK already treats it as absent: it is `0`, and the workflow
instance tests the field for truth before putting it on the completion. So a
disengaged worker sends exactly the bytes it sent before this module existed.

**The build id is the checkout's revision, never the environment's opinion of
it.** The variable names the build id the deployment *expects*; the value that
is registered is the one `_worker_revision()` reads out of the tree the worker
imported. That is what makes a restart-in-place re-register the same version
instead of minting a new one, and it is why a revision this worker cannot read
is a refusal (US1-S5) rather than a fallback: a version nobody can map back to a
commit is a version nobody can redeploy, and every epic pinned to it is stranded.
"""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Mapping, Sequence
from typing import Any, Final

from temporalio.common import VersioningBehavior, WorkerDeploymentVersion

#: The one deployment this factory has, because it has one worker and one queue
#: (`factory/worker.py`'s docstring). Versions of it are the code revisions that
#: have served it; the current one is what new epics start on.
DEPLOYMENT_NAME: Final = "ergane-worker"

#: The explicit environment FR-001 requires. Set — to the revision the deploy
#: froze — versioning is engaged; absent or blank, this worker is today's worker
#: down to the wire format.
WORKER_BUILD_ID_ENV: Final = "ERGANE_WORKER_BUILD_ID"


class VersioningRefused(RuntimeError):
    """Versioning was engaged and the build id could not be honestly established.

    Raised at worker construction, which on a worker host is process start, so
    the operator reads it in `journalctl` rather than discovering it as epics
    that never route.
    """


def requested_build_id(environ: Mapping[str, str]) -> str | None:
    """The build id the environment names, or `None` when it names none."""
    return (environ.get(WORKER_BUILD_ID_ENV) or "").strip() or None


#: Frozen at import, because the `@workflow.defn` decorators are evaluated at
#: import and there is no later moment at which they could be re-decided. A unit
#: file sets the variable before the process starts; nothing inside the process
#: changes it.
ENGAGED_BUILD_ID: Final[str | None] = requested_build_id(os.environ)


def workflow_versioning_behavior(
    behavior: VersioningBehavior, *, engaged: bool | None = None
) -> VersioningBehavior:
    """The behavior to declare on a `@workflow.defn`, gated by the environment.

    `engaged` is for tests that need to state the gate rather than inherit it;
    production passes nothing and gets the frozen decision.
    """
    if engaged is None:
        engaged = ENGAGED_BUILD_ID is not None
    return behavior if engaged else VersioningBehavior.UNSPECIFIED


def resolve_deployment_version(
    *, revision: str | None, requested: str | None
) -> WorkerDeploymentVersion | None:
    """The version this worker registers as, or `None` when versioning is off.

    `revision` is what `_worker_revision()` read out of the imported tree;
    `requested` is what the environment named. Pure, so the two refusals below
    are provable without a server.
    """
    requested = (requested or "").strip() or None
    if requested is None:
        return None

    if revision is None:
        raise VersioningRefused(
            f"{WORKER_BUILD_ID_ENV}={requested} engages worker versioning, but this "
            f"worker cannot read its own revision: `git rev-parse --short HEAD` "
            f"answered nothing for the tree it imported `factory/` from (a wheel, or "
            f"an unpacked source tree). Registering deployment '{DEPLOYMENT_NAME}' "
            f"with an unknowable build id would pin epics to a version that cannot be "
            f"mapped back to a commit or redeployed. Run the worker from a git "
            f"checkout, or unset {WORKER_BUILD_ID_ENV} to run unversioned."
        )

    if revision != requested:
        raise VersioningRefused(
            f"{WORKER_BUILD_ID_ENV}={requested} names a build id this worker is not "
            f"running: the tree it imported `factory/` from is at {revision}. The "
            f"build id is the checkout's revision, never the environment's opinion of "
            f"it — that is what makes a restart in place re-register the same version "
            f"instead of minting a new one. Redeploy the expected revision, or unset "
            f"{WORKER_BUILD_ID_ENV} to run unversioned."
        )

    return WorkerDeploymentVersion(deployment_name=DEPLOYMENT_NAME, build_id=revision)


#: What the server reports for a run that carries no versioning information at
#: all — the integer, because it arrives on a proto and not as an SDK enum.
UNVERSIONED_BEHAVIOR: Final = int(VersioningBehavior.UNSPECIFIED)


@dataclasses.dataclass(frozen=True)
class OpenEpic:
    """One open epic, and what the server says it is versioned as (082-US4).

    `behavior` is the server's own enum value rather than a bool this module
    derived, so the classification below is a decision about data and not a
    restatement of a read that already made it.
    """

    epic_id: str
    behavior: int = UNVERSIONED_BEHAVIOR
    build_id: str | None = None


def predates_versioning(epic: OpenEpic) -> bool:
    """Whether this epic was started by a worker that declared no version.

    The one thing T002's probe measured that the hoped-for answer got wrong: a
    pre-versioning run is *not* stalled when a versioned worker becomes current.
    It is served, adopted onto whatever version is current at its next workflow
    task, and pinned there — so what removing the unversioned worker costs is
    not a stall but an epic finishing on code it did not start with, plus the
    agents its attempts are running inside that unit's cgroup.
    """
    return epic.behavior == UNVERSIONED_BEHAVIOR


def strandable_epics(epics: Sequence[OpenEpic]) -> tuple[str, ...]:
    """The open epics that retiring the unversioned worker would strand.

    Pure, and sorted, because it is the body of a refusal an operator reads.
    """
    return tuple(sorted(epic.epic_id for epic in epics if predates_versioning(epic)))


def open_epic_from(execution: Any) -> OpenEpic:
    """One `list_workflows` result as this module's own two facts.

    `raw_info.versioning_info` is where the server puts them; the SDK's
    `WorkflowExecution` does not lift them onto attributes of its own. Read
    defensively — a server old enough to omit the field entirely reports every
    epic as pre-versioning, which is the safe direction for a refusal to err in.
    """
    info = getattr(getattr(execution, "raw_info", None), "versioning_info", None)
    version = getattr(info, "deployment_version", None)
    return OpenEpic(
        epic_id=str(execution.id),
        behavior=int(getattr(info, "behavior", UNVERSIONED_BEHAVIOR) or 0),
        build_id=(getattr(version, "build_id", "") or "") or None,
    )
