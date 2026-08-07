"""The roadmap's scheduler: one long-lived workflow that dispatches specs as children.

US2's `RoadmapWorkflow` is the factory's second workflow type. Where
`EpicWorkflow` drives one spec's nodes to terminal states, `RoadmapWorkflow`
drives a whole `specs/` corpus's dispatchable specs to their child epics —
woken by each child's completion event, bounded to one concurrent epic by
default, parking any spec whose pre-dispatch refuses so one bad spec does not
stall the line. The gap it closes was measured the night the plan was drafted:
003 landed at 22:36 UTC and dev-ready 007 sat idle behind it for want of an
operator glance.

The scheduler is event-driven (FR-004): it computes the dispatchable set,
starts each as a child `EpicWorkflow`, and waits on the children's
completion. No interval poll for epic state exists anywhere — the one
capacity read per scheduling pass is a single activity call triggered by a
child completion, not a timer. "Landed" is derived from the child's returned
`EpicStatus` (FR-006's whole point): the epic `COMPLETED` *and* every node's
landing `MERGED`. An epic that completes with a `FAILED` node is finished
but not landed; its dependents stay blocked and the roadmap says why.

Three orderings carry the weight, and each is load-bearing:

1. **Pre-dispatch runs before every child starts** (FR-006, acceptance 1).
   Each dispatchable spec gets a fresh target clone at the current default
   branch, a derivation, the 006 preflight and the 003 onboarding — all as
   activities, because workflow code touches nothing. A refusal parks the
   spec with the finding verbatim and the roadmap proceeds to the next
   dispatchable spec, so one bad spec never stalls the line (acceptance 2).

2. **Landed is derived, never declared** (FR-006). The roadmap re-reads the
   corpus's frontmatter each pass and computes readiness against a resolver
   that consults the child results it has observed. A child that completed
   with every landing MERGED marks its spec observed-landed and unblocks its
   dependents in the same pass (acceptance 3); a child that completed without
   landing leaves dependents blocked and reports the dependency as
   finished-but-not-landed (acceptance 4). `EpicState` has no LANDED member;
   it stays derived, one level up from the workgraph's own discipline.

3. **The bound is a knob, and the order is declared** (FR-005). At most
   `max_concurrent_epics` children run at once (default one), and when two
   specs are simultaneously dispatchable the second waits for capacity in
   spec-directory order — the lexicographic order `read_roadmap` returns,
   which the numbered-directory convention makes the roadmap's declared
   order (acceptance 5). Capacity accounting counts every open `epic-*`
   workflow — the roadmap's own children *and* an operator-started epic
   mid-flight when the roadmap booted — so a restart never double-dispatches.

Child policies (no precedent in the repo, decided here, verified in T011):
`parent_close_policy=ABANDON` — killing or continuing the roadmap must never
kill an epic (SC-004) — and the default id-reuse policy, so a closed
`epic-<spec>` id is reusable (tonight's five-closed-runs precedent) while a
running collision parks the spec with the collision named, never adopts.

FR-009 (the credential discipline 001 established, extended one level up):
the master key lives only in the worker host environment and is read inside
the preflight activity's seam. No key value reaches the roadmap's workflow
input, a parked finding, a `roadmap_status` payload, or frontmatter parsing
output. The sweep (T012) asserts each surface.

Everything here is pure decision-making over recorded results: no filesystem,
no clock but `workflow.now()`, no randomness but `workflow.uuid4()`, and no
scheduling input but the corpus and the child results. Continue-as-new and
the operator signals (`pause_roadmap`/`resume_roadmap`/`promote_spec`) are
US3 — US2 runs the scheduler to quiescence and returns its status.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable

from temporalio import activity, workflow
from temporalio.common import RetryPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import ApplicationError, FailureError
from temporalio.workflow import ParentClosePolicy

with workflow.unsafe.imports_passed_through():
    from factory.activities.roadmap_activities import (
        CloneInput,
        CountOpenInput,
        DeriveInput,
        OnboardInput,
        PreflightInput,
        clone_target,
        count_open_epics,
        derive_spec,
        onboard_target,
        preflight_spec,
    )
    from factory.mergequeue.models import LandingConfig, LandingState, TargetRepoProfile
    from factory.roadmap.models import (
        LandedKind,
        LandedStatus,
        Roadmap,
        RoadmapError,
        SpecEntry,
        SpecState,
        compute_readiness,
        read_roadmap,
    )
    from factory.verify.models import VerificationConfig
    from factory.workgraph.models import EpicState
    from factory.workgraph.preflight import PreflightFinding
    from factory.workgraph.workflow import (
        TASK_QUEUE,
        EpicInput,
        EpicStatus,
        EpicWorkflow,
    )


#: The id convention the roadmap takes: `roadmap-<specs-root-name>`, the sibling
#: of the epic CLI's `epic-<epic_id>` so the two id spaces cannot collide (the
#: plan's naming note). The spec dir under the roadmap is `<specs-root>/<dir>`,
#: and a child epic's id is `epic-<spec_dir>` — the epic CLI's own convention,
#: reused so an operator finds a roadmap-dispatched epic the same way they find
#: one they started by hand.
ROADMAP_ID_PREFIX = "roadmap-"


def roadmap_workflow_id(specs_root: str) -> str:
    """`roadmap-<specs-root-name>` — the roadmap's id, derived from its root.

    The specs root's directory name is the roadmap's identity (the plan's
    sibling convention to `epic-<epic_id>`), so two roadmaps over two different
    `specs/` roots never collide and an operator finds a roadmap by the root
    they pointed it at.
    """
    from pathlib import PurePosixPath

    return f"{ROADMAP_ID_PREFIX}{PurePosixPath(specs_root.rstrip('/')).name}"


#: The id a child epic runs under — the epic CLI's own convention, reused so a
#: roadmap-dispatched epic is indistinguishable from an operator-started one in
#: the Web UI and the capacity count.
def _epic_id_for(spec_dir: str) -> str:
    return f"epic-{spec_dir}"


@dataclass(frozen=True)
class RoadmapInput:
    """One roadmap run's whole dispatch — the workflow's only argument.

    `specs_root` is the `specs/` corpus the roadmap reads each pass;
    `target_repo` is the worker-host path to the target clone each child epic
    dispatches against (bootstrap topology); `proxy_url` is where each child's
    virtual key is honored. `max_concurrent_epics` is the bound (FR-005),
    default one. The remaining fields pass through to each child's `EpicInput`
    unchanged — the roadmap does not choose a ladder or a landing policy, it
    forwards the operator's.

    No credential (FR-009): the master key lives in the worker environment and
    is read inside the preflight activity's seam, never here.
    """

    specs_root: str
    target_repo: str
    proxy_url: str
    max_concurrent_epics: int = 1
    landing_config: LandingConfig = LandingConfig()
    config: VerificationConfig = VerificationConfig()
    poll_interval_s: int = 30


@dataclass(frozen=True)
class ParkedFinding:
    """One spec the roadmap tried and refused, with the refusal verbatim (FR-006).

    `check` is the pre-dispatch stage that refused (`clone`, `derive`,
    `preflight:<finding.check>`, `onboarding`, `collision`);
    `detail` is the refusal the stage produced, carried verbatim so the
    operator's next move (fix the spec, the proxy, or the repo) is on the
    finding. A parked spec does not re-dispatch this run — the line does not
    retry one bad spec forever (plan § Edge Cases).
    """

    spec_dir: str
    check: str
    detail: str


@dataclass(frozen=True)
class RoadmapSpecStatus:
    """One spec as an operator reads it (the `roadmap_status` query's answer).

    `state` is the declared intent; `dispatchable` is computed readiness;
    `blockers` names the unsatisfied edges; `landed` is whether this spec is
    itself observed-landed (a child returned COMPLETED with every landing
    MERGED); `unlanded` names dependencies that ran but did not land — the
    finished-but-not-landed report acceptance 4 demands, a subset of
    `blockers`.
    """

    spec_dir: str
    state: SpecState
    dispatchable: bool
    blockers: list[str]
    landed: bool
    unlanded: list[str]


@dataclass(frozen=True)
class RoadmapStatus:
    """The whole roadmap as an operator reads it — the query's answer and the
    run's result.

    `specs` is every spec in sorted order, `running` is the spec dirs whose
    child epics are in flight, `parked` is the specs refused this run with
    their findings verbatim, and `max_concurrent_epics` is the bound in force
    (FR-005). No credential reaches any field (FR-009, asserted in T012).
    """

    specs: list[RoadmapSpecStatus]
    running: list[str]
    parked: list[ParkedFinding]
    max_concurrent_epics: int


#: Reads and small writes: a corpus parse, a spec read, a derivation, the
#: preflight's two proxy reads, onboarding's repo read, and the capacity
#: list. Same retry shape as the workgraph workflow's `_FAST` — idempotent
#: reads and fresh-id sends, safe to retry a couple of times, not worth more
#: while a child's ladder holds a decision.
_RETRIES = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=3,
)
_FAST = {"start_to_close_timeout": timedelta(minutes=2), "retry_policy": _RETRIES}

#: git, which may be fetching a large repository for the first time (the same
#: bound the workgraph workflow's `_GIT` uses, derived from `worktree.GIT_TIMEOUT_S`).
_GIT = {"start_to_close_timeout": timedelta(minutes=10), "retry_policy": _RETRIES}


# --- filesystem reads the workflow needs (the workflow cannot read files) -----


@dataclass(frozen=True)
class ReadCorpusInput:
    """The specs root to read the corpus from (FR-006 corpus read)."""

    specs_root: str


@dataclass(frozen=True)
class ReadSpecInput:
    """One spec's text for derivation: which root, which spec dir."""

    specs_root: str
    spec_dir: str


@activity.defn
async def read_corpus_activity(request: ReadCorpusInput) -> Roadmap:
    """Read the whole corpus into a roadmap graph (FR-006 corpus read).

    A `RoadmapError` (a broken corpus) propagates as an activity failure the
    workflow raises — a corpus that does not parse is a hard stop, not a
    parked spec: there is no spec to park, and the operator's move is to fix
    the grammar.
    """
    return read_roadmap(request.specs_root)


@activity.defn
async def read_spec_text_activity(request: ReadSpecInput) -> str:
    """Read one spec's text for derivation (the workflow cannot read files)."""
    from pathlib import Path

    return (Path(request.specs_root) / request.spec_dir / "spec.md").read_text(
        encoding="utf-8"
    )


@workflow.defn
class RoadmapWorkflow:
    """One roadmap, from corpus read to every dispatchable spec's child landed.

    US2 runs the scheduler to quiescence and returns its status; US3 will wrap
    the loop in continue-as-new at quiescence so no run's history grows with
    the number of epics (SC-003). The child-start contract — ABANDON on
    parent close, default id reuse — is decided here and verified in T011.
    """

    def __init__(self) -> None:
        #: The corpus, re-read each pass (an edit reaches the next pass, never
        #: the one in flight — 002's criteria discipline, one level up).
        self._roadmap: Roadmap | None = None
        #: Observed-landed facts: spec_dir -> LandedStatus. A child that
        #: completed with every landing MERGED marks its spec landed=True; a
        #: child that completed without landing marks landed=False so the
        #: readiness report can name it finished-but-not-landed (acceptance 4).
        self._landed: dict[str, LandedStatus] = {}
        #: Specs parked this run, keyed by spec_dir. A parked spec does not
        #: re-dispatch — one bad spec must not stall the line, and the line does
        #: not retry it forever (FR-006, plan § Edge Cases).
        self._parked: dict[str, ParkedFinding] = {}
        #: In-flight child handles, keyed by spec_dir. The scheduler waits on
        #: these — never polls — so a completion is the event that wakes it.
        self._children: dict[str, Any] = {}
        self._max_concurrent_epics = 1

    # --- query ----------------------------------------------------------------

    @workflow.query
    def roadmap_status(self) -> RoadmapStatus:
        """Every spec's state, the running children, parked findings, the bound.

        Read-only: no activity, no mutation. No credential reaches any field
        (FR-009, asserted in T012).
        """
        roadmap = self._roadmap
        if roadmap is None:
            return RoadmapStatus(
                specs=[],
                running=[],
                parked=[],
                max_concurrent_epics=self._max_concurrent_epics,
            )
        readiness = compute_readiness(roadmap, landed_for=self._observed_resolver())
        specs: list[RoadmapSpecStatus] = []
        for entry in roadmap.entries:
            r = readiness.spec(entry.spec_dir)
            unlanded = [
                dep
                for dep in r.blockers
                if dep in self._landed and not self._landed[dep].landed
            ]
            own_landed = (
                entry.spec_dir in self._landed and self._landed[entry.spec_dir].landed
            )
            specs.append(
                RoadmapSpecStatus(
                    spec_dir=entry.spec_dir,
                    state=entry.state,
                    dispatchable=r.dispatchable,
                    blockers=r.blockers,
                    landed=own_landed,
                    unlanded=unlanded,
                )
            )
        return RoadmapStatus(
            specs=specs,
            running=sorted(self._children),
            parked=[self._parked[d] for d in sorted(self._parked)],
            max_concurrent_epics=self._max_concurrent_epics,
        )

    # --- the main loop ---------------------------------------------------------

    @workflow.run
    async def run(self, request: RoadmapInput) -> RoadmapStatus:
        """Dispatch every dispatchable spec as a child, woken by completions.

        Reads the corpus, computes readiness against observed-landed facts,
        and dispatches dispatchable specs in spec-directory order while
        capacity is free. Parks any spec whose pre-dispatch refuses, with the
        finding verbatim, and continues. Waits on child completions — never
        polls — to recompute readiness and dispatch newly-unblocked specs in
        the same pass. Returns when no spec is dispatchable and none is in
        flight (quiescence).
        """
        if not isinstance(request.max_concurrent_epics, int) or isinstance(
            request.max_concurrent_epics, bool
        ) or request.max_concurrent_epics < 1:
            raise ApplicationError(
                f"max_concurrent_epics must be a positive integer, got "
                f"{request.max_concurrent_epics!r}",
                non_retryable=True,
            )
        self._max_concurrent_epics = request.max_concurrent_epics

        while True:
            self._roadmap = await workflow.execute_activity(
                read_corpus_activity,
                ReadCorpusInput(specs_root=request.specs_root),
                **_FAST,
            )
            readiness = compute_readiness(
                self._roadmap, landed_for=self._observed_resolver()
            )
            # Dispatchable, in spec-directory order, excluding specs already
            # running, parked, or observed this run. A spec whose child has
            # concluded is recorded in `_landed` (landed or finished-but-not-
            # landed); neither re-dispatches — a landed spec is done, and a
            # finished-but-not-landed spec's dependents stay blocked by
            # acceptance 4 (the line does not retry it forever, FR-006).
            # Lexicographic order is `read_roadmap`'s sorted order, which the
            # numbered directories make the declared order (FR-005, acceptance 5).
            dispatchable = [
                entry
                for entry in self._roadmap.entries
                if readiness.spec(entry.spec_dir).dispatchable
                and entry.spec_dir not in self._children
                and entry.spec_dir not in self._parked
                and entry.spec_dir not in self._landed
            ]

            # Capacity: count every open epic-* workflow (the roadmap's own
            # children plus any operator-started epic), then fill free slots.
            # One read per pass, triggered by a completion — never an interval
            # poll (FR-004).
            free = 0
            if dispatchable:
                open_result = await workflow.execute_activity(
                    count_open_epics, CountOpenInput(), **_FAST
                )
                free = request.max_concurrent_epics - len(open_result.open_ids)
                # Dispatch in declaration order up to the free slots. A spec
                # that parks inside `_dispatch` consumes no slot, so the loop
                # below re-reads capacity and reaches the next dispatchable spec
                # in the same run — one bad spec never stalls the line (FR-006).
                for entry in dispatchable[: max(0, free)]:
                    await self._dispatch(entry, request)

            if self._children:
                # Wait for any child to complete — the event that wakes the
                # scheduler (FR-004). Reap finished children, record their landed
                # status, and loop to recompute readiness against the new facts.
                await workflow.wait_condition(
                    lambda: any(handle.done() for handle in self._children.values())
                )
                for spec_dir, handle in list(self._children.items()):
                    if not handle.done():
                        continue
                    del self._children[spec_dir]
                    # `result()` is a non-async accessor on a workflow future —
                    # the sandbox resolves the child's return value into it, so
                    # awaiting it raises (an `EpicStatus` is not awaitable). The
                    # `done()` guard above makes the value available now.
                    status: EpicStatus = handle.result()
                    self._landed[spec_dir] = self._landed_status_for(status)
                continue

            # No child is in flight. If free capacity exists and a dispatchable
            # spec remains un-tried (one that parked a slot-free refusal above
            # but left others, or the bound held the rest), loop to reach it;
            # if capacity is zero we cannot make progress this run (every slot
            # is held by an epic the roadmap cannot observe completing), so we
            # stop rather than spin. Otherwise nothing is dispatchable and
            # nothing is in flight — quiescence (US2 returns; US3 will
            # continue-as-new here instead).
            if free > 0 and any(
                entry.spec_dir not in self._parked
                and entry.spec_dir not in self._landed
                and entry.spec_dir not in self._children
                for entry in dispatchable
            ):
                continue
            break

        return self.roadmap_status()

    # --- dispatch: pre-dispatch, then start the child --------------------------

    async def _dispatch(self, entry: SpecEntry, request: RoadmapInput) -> None:
        """Run pre-dispatch for one spec, then start its child epic (FR-006).

        Any refusal parks the spec with the finding verbatim and returns
        without starting a child — the roadmap proceeds to the next
        dispatchable spec (acceptance 2). A child id that collides with a
        running workflow parks with the collision named, never adopts (T011).
        """
        spec_dir = entry.spec_dir
        child_workflow_id = _epic_id_for(spec_dir)

        # 1. Fresh clone at the current default branch (FR-006, acceptance 1).
        # A git failure surfaces as an `ActivityError` (a `FailureError`, not an
        # `ApplicationError`), so the catch is the `FailureError` base — a clone
        # that cannot be refreshed parks the spec rather than failing the
        # roadmap (FR-006: one bad spec must not stall the line).
        try:
            await workflow.execute_activity(
                clone_target,
                CloneInput(target_repo=request.target_repo, spec_dir=spec_dir),
                **_GIT,
            )
        except FailureError as exc:
            self._park(spec_dir, "clone", str(exc))
            return

        # 2. Derivation — the pure deriver behind a thin activity. A spec that
        # does not compile (no Work Graph section, a dangling edge) parks here.
        spec_text = await workflow.execute_activity(
            read_spec_text_activity,
            ReadSpecInput(specs_root=request.specs_root, spec_dir=spec_dir),
            **_FAST,
        )
        try:
            graph = await workflow.execute_activity(
                derive_spec,
                DeriveInput(
                    spec_text=spec_text,
                    epic_id=spec_dir,
                    feature=spec_dir,
                    specs_root=request.specs_root,
                    target_repo=request.target_repo,
                ),
                **_FAST,
            )
        except FailureError as exc:
            # The derive activity re-raises a `DerivationError` as a
            # non-retryable `ApplicationError` (a `FailureError`), so the
            # refusal's verbatim message is what parks the spec (FR-006).
            self._park(spec_dir, "derive", _derivation_detail(exc))
            return

        # 3. The 006 preflight (model aliases, key collisions) — shared with the
        # CLI so the two surfaces cannot drift. Any finding parks the spec with
        # the finding verbatim.
        findings: list[PreflightFinding] = await workflow.execute_activity(
            preflight_spec,
            PreflightInput(
                graph=graph, proxy_url=request.proxy_url, spec_dir=spec_dir
            ),
            **_FAST,
        )
        if findings:
            finding = findings[0]
            self._park(spec_dir, f"preflight:{finding.check}", finding.detail)
            return

        # 4. The 003 onboarding gate — reused as it stands. A failing repo
        # parks the spec (the child re-runs onboarding at its own start too).
        profile: TargetRepoProfile = await workflow.execute_activity(
            onboard_target,
            OnboardInput(target_repo=request.target_repo, spec_dir=spec_dir),
            **_FAST,
        )
        if not profile.passed:
            self._park(spec_dir, "onboarding", _onboarding_detail(profile))
            return

        # 5. Start the child epic — ABANDON on parent close (SC-004: killing the
        # roadmap never kills the epic), default id reuse (a closed id is
        # reusable; a running collision parks, never adopts — T011).
        try:
            handle = await workflow.start_child_workflow(
                EpicWorkflow.run,
                EpicInput(
                    graph=graph,
                    proxy_url=request.proxy_url,
                    config=request.config,
                    poll_interval_s=request.poll_interval_s,
                    landing_config=request.landing_config,
                ),
                id=child_workflow_id,
                task_queue=TASK_QUEUE,
                parent_close_policy=ParentClosePolicy.ABANDON,
                id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
            )
        except FailureError as exc:
            # A running collision under the child's id surfaces as a
            # `WorkflowAlreadyStartedError` (a `FailureError`): park with the
            # collision named, never adopt the running epic (T011).
            self._park(spec_dir, "collision", str(exc))
            return
        self._children[spec_dir] = handle

    def _park(self, spec_dir: str, check: str, detail: str) -> None:
        """Record a refusal verbatim so the line proceeds without the spec (FR-006)."""
        self._parked[spec_dir] = ParkedFinding(
            spec_dir=spec_dir, check=check, detail=detail
        )

    # --- the observed-landed resolver ----------------------------------------

    def _observed_resolver(self) -> Callable[[str], LandedStatus | None]:
        """The seam `compute_readiness` reads observed-landed facts through.

        Returns a `LandedStatus` for a spec the roadmap has watched a child of,
        or `None` to fall back to the frontmatter's attested path (FR-003's
        two kinds, distinguishable in reporting). Observed takes precedence
        over attested — it is the stronger, derived fact.
        """

        def resolve(spec_dir: str) -> LandedStatus | None:
            return self._landed.get(spec_dir)

        return resolve

    @staticmethod
    def _landed_status_for(status: EpicStatus) -> LandedStatus:
        """Derive landed from a child's `EpicStatus` (FR-006).

        Landed = `COMPLETED` *and* every node's landing `MERGED`. A child that
        completed with a FAILED or KILLED node is finished but not landed —
        `landed=False`, kind `OBSERVED` — so its dependents stay blocked and
        the readiness report names it finished-but-not-landed (acceptance 4).
        `EpicState` has no LANDED member; it stays derived.
        """
        completed = status.epic_state is EpicState.COMPLETED
        all_merged = all(
            node.landing_state is LandingState.MERGED
            for node in status.nodes.values()
        )
        return LandedStatus(
            landed=completed and all_merged, kind=LandedKind.OBSERVED
        )


# --- finding renderers (the verbatim-in-parked-finding discipline) ------------


def _derivation_detail(exc: FailureError) -> str:
    """The deriver's rejection, verbatim — the `DerivationError` message.

    The activity wraps a `DerivationError` in a non-retryable
    `ApplicationError`, which Temporal wraps again into an `ActivityError`
    whose own message is the generic "Activity task failed". The verbatim
    rejection rides on the inner cause (the same discipline the workgraph
    workflow uses to surface `resolve_graph`'s `GRAPH_INVALID` message), so the
    parked finding names the rejection — not "activity failed" (FR-006).
    """
    inner = exc.cause
    if isinstance(inner, ApplicationError):
        return inner.message or str(exc)
    return str(exc)


def _onboarding_detail(profile: TargetRepoProfile) -> str:
    """The onboarding findings rendered to one sentence (FR-006 verbatim).

    Each failing check names what was wrong; the parked finding carries them
    so the operator's move (fix the repo's visibility, merge queue, or checks)
    is on the finding.
    """
    failed = [f for f in profile.findings if not f.passed]
    if not failed:
        return f"target repo {profile.repo} failed onboarding"
    lines = [
        f"[{f.check}] {f.detail}" for f in failed
    ]
    return (
        f"target repo {profile.repo} failed onboarding:\n  "
        + "\n  ".join(lines)
    )