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

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Awaitable, Callable

from temporalio import activity, workflow
from temporalio.common import RetryPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import ApplicationError, FailureError
from temporalio.workflow import ParentClosePolicy

with workflow.unsafe.imports_passed_through():
    from factory.activities.roadmap_activities import (
        CloneInput,
        CountOpenInput,
        DeriveInput,
        DriftInput,
        OnboardInput,
        PreflightInput,
        clone_target,
        count_open_epics,
        derive_spec,
        drift_for_spec,
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

    `carry_over` is US3's durability seam (FR-007): a run that resumes after a
    continue-as-new receives the previous run's observed landings, parked
    findings, promotions, and pause flag here, so the new run's empty instance
    fields are repopulated and the roadmap does not re-dispatch work whose
    result the carry-over already holds. `None` for the first run.

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
    carry_over: "RoadmapCarryOver | None" = None


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
class RoadmapCarryOver:
    """US3's explicit state across a continue-as-new boundary (FR-007).

    The one moment continue-as-new is safe is quiescence — zero children open
    — and the carry-over is the fixed-size input the new run receives so it
    does not re-dispatch work the previous run already did. Everything *not*
    here is re-read on the new run (the corpus, the capacity), which is what
    makes "restarting re-reads the world" true for free (SC-004): a spec
    edited to `ready` between runs is seen, but a spec already observed-landed
    or already parked is not re-dispatched.

    `landed` and `parked` are the observed-landed and parked-finding maps the
    run accumulated; `promotions` are the spec dirs the operator promoted by
    signal (FR-008); `paused` is the pause flag (FR-008); `max_concurrent_epics`
    is the bound (FR-005), carried so a restart honours the operator's knob.

    No credential reaches any field (FR-009): `ParkedFinding.detail` carries a
    refusal's text, never a key; the maps hold spec dirs and `LandedStatus`es.
    """

    landed: tuple[tuple[str, LandedStatus], ...] = ()
    parked: tuple[ParkedFinding, ...] = ()
    promotions: tuple[str, ...] = ()
    paused: bool = False
    max_concurrent_epics: int = 1

    @classmethod
    def from_state(
        cls,
        *,
        landed: dict[str, LandedStatus],
        parked: dict[str, ParkedFinding],
        promotions: dict[str, None] | set[str],
        paused: bool,
        max_concurrent_epics: int,
    ) -> "RoadmapCarryOver":
        """Build a carry-over from the run's live (mutable) state.

        The run holds its state in dicts (for `workflow.wait_condition`
        closures); the carry-over is frozen and ordered so the boundary
        payload is deterministic and serializable across the run.
        """
        return cls(
            landed=tuple(sorted(landed.items())),
            parked=tuple(parked[d] for d in sorted(parked)),
            promotions=tuple(sorted(set(promotions))),
            paused=paused,
            max_concurrent_epics=max_concurrent_epics,
        )

    def landed_map(self) -> dict[str, LandedStatus]:
        return dict(self.landed)

    def parked_map(self) -> dict[str, ParkedFinding]:
        return {p.spec_dir: p for p in self.parked}

    def promotion_set(self) -> set[str]:
        return set(self.promotions)


@dataclass(frozen=True)
class RoadmapSpecStatus:
    """One spec as an operator reads it (the `roadmap_status` query's answer).

    `state` is the declared intent; `rendered_state` is the state the operator
    sees (`amended` when a landed spec's fingerprints have drifted, otherwise
    the declared `state`). `dispatchable` is computed readiness; `blockers`
    names the unsatisfied edges; `landed` is whether this spec is itself
    observed-landed (a child returned COMPLETED with every landing MERGED);
    `unlanded` names dependencies that ran but did not land — the
    finished-but-not-landed report acceptance 4 demands, a subset of
    `blockers`. `landed_kind` is *how* this spec is landed — `ATTESTED`
    (frontmatter `state: landed`) or `OBSERVED` (a child returned landed) —
    `None` when it is not landed, so a report says why an edge is satisfied,
    not just that it is (FR-003, acceptance 5). `satisfied_as` carries the
    same distinction per satisfied dependency. `promoted` is US3's signal
    (FR-008): a draft the operator promoted is reported as promoted, not as
    `ready` in the file (the file remains the authority of record; the
    signal covers the gap until its next edit). `drifted` is US4's read-only
    signal: the frontmatter says `landed` but the fingerprints differ from
    their landing baseline.
    """

    spec_dir: str
    state: SpecState
    dispatchable: bool
    blockers: list[str]
    landed: bool
    unlanded: list[str]
    rendered_state: str = ""
    landed_kind: LandedKind | None = None
    satisfied_as: dict[str, LandedKind] = field(default_factory=dict)
    promoted: bool = False
    drifted: bool = False


@dataclass(frozen=True)
class RoadmapStatus:
    """The whole roadmap as an operator reads it — the query's answer and the
    run's result.

    `specs` is every spec in sorted order, `running` is the spec dirs whose
    child epics are in flight, `parked` is the specs refused this run with
    their findings verbatim, and `max_concurrent_epics` is the bound in force
    (FR-005). `paused` is US3's pause flag (FR-008): a roadmap between epics
    reports it is not dispatching because the operator parked it, not because
    nothing is ready. No credential reaches any field (FR-009, asserted in
    T012).
    """

    specs: list[RoadmapSpecStatus]
    running: list[str]
    parked: list[ParkedFinding]
    max_concurrent_epics: int
    paused: bool = False


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

    US2 runs the scheduler to quiescence and returns its status; US3 wraps the
    loop in continue-as-new at quiescence so no run's history grows with the
    number of epics (SC-003, FR-007), and exposes `pause_roadmap`,
    `resume_roadmap`, and `promote_spec` signals plus a `roadmap_status` query
    (FR-008). The child-start contract — ABANDON on parent close, default id
    reuse — is decided here and verified in T011; ABANDON is also what makes
    terminating the roadmap safe for a mid-flight child (SC-004).

    Continue-as-new fires *only* at quiescence — zero children open — the one
    moment no completion event can be lost across the run boundary. The new run
    receives the old run's state as an explicit `RoadmapCarryOver` input and
    re-reads everything else, which is what makes "restarting re-reads the
    world" true for free: a spec edited to `ready` between runs is seen, but a
    spec already observed-landed or already parked is not re-dispatched.
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
        #: Spec text read this pass, used by the drift resolver (FR-009). It is
        #: refreshed each time the corpus is re-read and fed to `derive_spec`, so
        #: the drift activity compares the same text that derivation uses.
        self._roadmap_text: dict[str, str] = {}
        #: US4 drift cache: spec_dir -> bool, refreshed each pass so the
        #: `roadmap_status` query can report drift without executing activities.
        self._drift: dict[str, bool] = {}
        #: US3 operator surface (FR-008). `pause_roadmap` parks dispatch
        #: between epics — the in-flight child finishes (the epic pause
        #: contract, one level up); `promote_spec` records a draft the
        #: operator promoted so the next pass treats it as ready. Both are
        #: history events, so replay rebuilds them exactly where the recorded
        #: run had them (the same rule the epic's `_paused`/`_kill_requested`
        #: follow), and both ride the carry-over across continue-as-new.
        self._paused = False
        self._promotions: dict[str, None] = {}

    # --- signals and query (FR-008) -------------------------------------------

    @workflow.signal
    def pause_roadmap(self) -> None:
        """Park dispatch between epics; the in-flight child finishes (FR-008).

        Only the scheduler is suspended — the child in flight keeps its ladder
        to the end, the same contract `pause_epic` honours one level down. A
        paused roadmap with no child in flight waits for `resume_roadmap`
        before dispatching; a paused roadmap with a child in flight lets the
        child land, then parks. Idempotent: pausing a paused roadmap is what
        an operator does when they are not sure the first one landed.
        """
        self._paused = True

    @workflow.signal
    def resume_roadmap(self) -> None:
        """Release the scheduler. A resume that arrives first never parks."""
        self._paused = False

    @workflow.signal
    def promote_spec(self, spec_dir: str) -> None:
        """Treat a named draft as ready on the next pass (FR-008, acceptance 3).

        The file remains the authority of record — the signal covers the gap
        until the frontmatter's next edit. The promotion applies while the
        spec's current frontmatter state is `draft`; if the operator edits the
        file to `ready`/`deferred`/`landed`, the file's state wins and the
        promotion is moot (the re-read sees the new state). Idempotent:
        promoting a spec twice is one promotion.
        """
        self._promotions[spec_dir] = None

    @workflow.query
    def roadmap_status(self) -> RoadmapStatus:
        """Every spec's state, the running children, parked findings, the bound.

        US3 (FR-008, acceptance 5): also reports the pause flag, per-spec
        promotions, and attested-vs-observed landings (FR-003's two kinds,
        surfaced in `landed_kind` and `satisfied_as`). Read-only: no activity,
        no mutation. No credential reaches any field (FR-009, asserted in T012).
        """
        roadmap = self._roadmap
        if roadmap is None:
            return RoadmapStatus(
                specs=[],
                running=[],
                parked=[],
                max_concurrent_epics=self._max_concurrent_epics,
                paused=self._paused,
            )
        # The query is read-only and runs without a request in scope, so it
        # cannot execute activities. It reports the drift computed on the last
        # scheduling pass (cached in `self._drift`) so the operator sees the same
        # `amended` state the dispatch loop saw (FR-009).
        readiness = compute_readiness(
            roadmap,
            landed_for=self._observed_resolver(),
            drifted_for=lambda spec_dir: self._drift.get(spec_dir, False),
        )
        specs: list[RoadmapSpecStatus] = []
        for entry in roadmap.entries:
            r = readiness.spec(entry.spec_dir)
            unlanded = [
                dep
                for dep in r.blockers
                if dep in self._landed and not self._landed[dep].landed
            ]
            # A spec's own landed state: observed takes precedence (the stronger,
            # derived fact), then attested (frontmatter `state: landed` — the
            # operator's word, FR-003's two kinds). `satisfied_as` already carries
            # the same precedence for dependencies; this mirrors it for the spec
            # itself, so an attested-landed spec reports `landed=True` with
            # `landed_kind=ATTESTED` and an observed one reports `OBSERVED`.
            own = self._landed.get(entry.spec_dir)
            if own is not None and own.landed:
                own_landed = True
                own_kind: LandedKind | None = own.kind
            elif entry.state is SpecState.LANDED:
                own_landed = True
                own_kind = LandedKind.ATTESTED
            else:
                own_landed = False
                own_kind = None
            specs.append(
                RoadmapSpecStatus(
                    spec_dir=entry.spec_dir,
                    state=entry.state,
                    dispatchable=r.dispatchable,
                    blockers=r.blockers,
                    landed=own_landed,
                    unlanded=unlanded,
                    rendered_state=r.rendered_state,
                    landed_kind=own_kind,
                    satisfied_as=dict(r.satisfied_as),
                    promoted=entry.spec_dir in self._promotions,
                    drifted=r.drifted,
                )
            )
        return RoadmapStatus(
            specs=specs,
            running=sorted(self._children),
            parked=[self._parked[d] for d in sorted(self._parked)],
            max_concurrent_epics=self._max_concurrent_epics,
            paused=self._paused,
        )

    # --- the main loop ---------------------------------------------------------

    @workflow.run
    async def run(self, request: RoadmapInput) -> RoadmapStatus:
        """Dispatch every dispatchable spec as a child, woken by completions.

        Reads the corpus, computes readiness against observed-landed facts
        (and the operator's promotions), and dispatches dispatchable specs in
        spec-directory order while capacity is free and the roadmap is not
        paused. Parks any spec whose pre-dispatch refuses, with the finding
        verbatim, and continues. Waits on child completions — never polls — to
        recompute readiness and dispatch newly-unblocked specs in the same
        pass. At quiescence (zero children open) after a child has concluded,
        continues-as-new carrying the run's state, so no run's history grows
        with the number of epics (FR-007); when nothing is dispatchable and
        none is in flight, returns.
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
        # US3: repopulate the run's state from the carry-over (FR-007). The
        # first run has no carry-over; a run resuming after continue-as-new
        # receives the previous run's landings, parked findings, promotions,
        # and pause flag so it does not re-dispatch work already done.
        if request.carry_over is not None:
            self._landed = request.carry_over.landed_map()
            self._parked = request.carry_over.parked_map()
            self._promotions = {d: None for d in request.carry_over.promotion_set()}
            self._paused = request.carry_over.paused
            self._max_concurrent_epics = request.carry_over.max_concurrent_epics

        # Whether any child concluded this run — the gate for continue-as-new.
        # CAN fires at quiescence only after a child has concluded, so a run
        # that finds nothing dispatchable returns rather than CAN-looping, and
        # every run that CANs did one epic's worth of work (the bound, FR-007).
        completed_this_run = False

        while True:
            self._roadmap = await workflow.execute_activity(
                read_corpus_activity,
                ReadCorpusInput(specs_root=request.specs_root),
                **_FAST,
            )
            # Per-spec text is read lazily by `_spec_text` and cached in
            # `_roadmap_text` so drift detection and derivation see the same text
            # without adding a batch read activity to every pass (SC-003).
            self._roadmap_text = {}
            # Apply the operator's promotions: a draft the operator promoted
            # by signal is treated as ready this pass (FR-008, acceptance 3).
            # The file remains the authority of record — a promotion only
            # applies while the current frontmatter state is `draft`, so an
            # edit to `ready`/`deferred`/`landed` makes the file's state win.
            self._roadmap = self._apply_promotions(self._roadmap)
            # US4: drift is read-only and repo-authoritative, but `compute_readiness`
            # is a pure synchronous function, so the async drift activity is awaited
            # here and the boolean result is injected (FR-009). The same map is cached
            # for the `roadmap_status` query.
            self._drift = await self._compute_drift(request)
            readiness = compute_readiness(
                self._roadmap,
                landed_for=self._observed_resolver(),
                drifted_for=lambda spec_dir: self._drift.get(spec_dir, False),
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
            # poll (FR-004). A paused roadmap reads capacity but dispatches
            # nothing: the in-flight child finishes, then dispatch parks.
            free = 0
            if dispatchable and not self._paused:
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
                    completed_this_run = True
                # A child concluded and zero are open now: continue-as-new at
                # quiescence (FR-007). The boundary is safe only here — no
                # completion event can be lost across it because no child is in
                # flight. The carry-over is the run's state as an explicit input
                # to the new run, which re-reads everything else.
                if not self._children and completed_this_run:
                    return await self._continue_as_new(request)
                continue

            # No child is in flight. A paused roadmap parks here: wait for
            # resume before dispatching again (FR-008). The in-flight child (if
            # any) has already finished above; with no child open, a paused
            # roadmap has nothing to wait on but the resume signal.
            if self._paused:
                await workflow.wait_condition(lambda: not self._paused)
                continue

            # If free capacity exists and a dispatchable spec remains un-tried
            # (one that parked a slot-free refusal above but left others, or
            # the bound held the rest), loop to reach it; if capacity is zero
            # we cannot make progress this run (every slot is held by an epic
            # the roadmap cannot observe completing), so we stop rather than
            # spin. Otherwise nothing is dispatchable and nothing is in flight.
            if free > 0 and any(
                entry.spec_dir not in self._parked
                and entry.spec_dir not in self._landed
                and entry.spec_dir not in self._children
                for entry in dispatchable
            ):
                continue
            # A child concluded this run and the roadmap is now quiescent —
            # continue-as-new to bound history (FR-007). The new run re-reads
            # the world and either dispatches the next spec or returns.
            if completed_this_run:
                return await self._continue_as_new(request)
            break

        return self.roadmap_status()

    # --- continue-as-new: the durability boundary (FR-007) -------------------

    async def _continue_as_new(self, request: RoadmapInput) -> RoadmapStatus:
        """Continue-as-new at quiescence, carrying the run's state (FR-007).

        Called only when zero children are open and a child has concluded this
        run — the one moment the boundary is safe. Builds the carry-over from
        the run's live state and continues-as-new with the same dispatch
        arguments plus the carry-over, so the new run resumes the roadmap without
        re-dispatching work whose result the carry-over holds. `continue_as_new`
        raises `NoReturn`, so the return annotation is the status the new run
        will eventually produce (the SDK surfaces it to the caller across the
        chain).
        """
        carry = RoadmapCarryOver.from_state(
            landed=self._landed,
            parked=self._parked,
            promotions=self._promotions,
            paused=self._paused,
            max_concurrent_epics=self._max_concurrent_epics,
        )
        return await workflow.continue_as_new(
            RoadmapInput(
                specs_root=request.specs_root,
                target_repo=request.target_repo,
                proxy_url=request.proxy_url,
                max_concurrent_epics=request.max_concurrent_epics,
                landing_config=request.landing_config,
                config=request.config,
                poll_interval_s=request.poll_interval_s,
                carry_over=carry,
            ),
        )

    def _apply_promotions(self, roadmap: Roadmap) -> Roadmap:
        """Return a roadmap where promoted drafts are treated as ready (FR-008).

        A promotion by signal covers the gap between a draft's frontmatter and
        its next edit (acceptance 3): while the spec's current state is
        `draft`, the promotion makes it `ready` for readiness computation, so
        it dispatches once its edges are satisfied. The file is the authority
        of record — if the operator edits the state away from `draft`, the
        file's state wins and the promotion is moot (the re-read sees the new
        state, and this function does not override it). A promoted spec is
        reported as `promoted` in `roadmap_status` regardless, so the operator
        sees the signal landed.
        """
        if not self._promotions:
            return roadmap
        entries = []
        for entry in roadmap.entries:
            if (
                entry.spec_dir in self._promotions
                and entry.state is SpecState.DRAFT
            ):
                entries.append(
                    SpecEntry(
                        spec_dir=entry.spec_dir,
                        state=SpecState.READY,
                        depends_on_landed=list(entry.depends_on_landed),
                        source=entry.source,
                    )
                )
            else:
                entries.append(entry)
        return Roadmap(specs_root=roadmap.specs_root, entries=entries)

    async def _read_spec_texts(self, specs_root: str) -> dict[str, str]:
        """Read every spec's text on demand, not in a batch (FR-009, FR-010).

        The drift resolver needs the current spec text for each `state: landed`
        spec, and `_dispatch` needs it for derivation. Reading lazily per spec
        keeps history small: a batch read would add N activities to every pass
        for a corpus of N specs, and US3's history-bound test measures each run.
        Workflow code cannot touch the filesystem, so each read runs as an activity.
        """
        if self._roadmap is None:
            return {}
        return {}

    async def _spec_text(self, specs_root: str, spec_dir: str) -> str:
        """Read one spec's text, caching it per pass."""
        text = self._roadmap_text.get(spec_dir)
        if text is None:
            text = await workflow.execute_activity(
                read_spec_text_activity,
                ReadSpecInput(specs_root=specs_root, spec_dir=spec_dir),
                **_FAST,
            )
            self._roadmap_text[spec_dir] = text
        return text

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

        # 2. Derivation — the pure delta deriver behind a thin activity. A spec that
        # does not compile (no Work Graph section, a dangling edge, or identity
        # broken by a missing/renumbered story) parks here.
        spec_text = await self._spec_text(request.specs_root, spec_dir)
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

        # 5. Zero-node delta refusal after clone, before child start (FR-010).
        # The clone is already refreshed; if the spec is fully landed and nothing
        # drifted, the delta graph is empty and there is no work to dispatch.
        if not graph.nodes:
            self._park(spec_dir, "derive", "delta is empty: all stories are satisfied")
            return

        # 6. Start the child epic — ABANDON on parent close (SC-004: killing the
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

    # --- the observed-landed and drift resolvers -------------------------------

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

    def _drift_resolver(self, request: RoadmapInput) -> Callable[[str], Awaitable[bool]]:
        """The seam `compute_readiness` reads drift facts through (FR-009).

        A drift query is an activity call: the workflow cannot shell git, so
        `drift_for_spec` reads the refreshed target repo and returns whether the
        spec's fingerprints differ from its landing baseline. The result is cached
        for the pass so the render query and dispatch loop see the same value.
        """
        cached: dict[str, bool] = {}

        async def resolve(spec_dir: str) -> bool:
            if spec_dir in cached:
                return cached[spec_dir]
            if self._roadmap is None:
                return False
            entry = next(
                (e for e in self._roadmap.entries if e.spec_dir == spec_dir), None
            )
            if entry is None or entry.state is not SpecState.LANDED:
                cached[spec_dir] = False
                return False
            spec_text = await self._spec_text(request.specs_root, spec_dir)
            drifted = await workflow.execute_activity(
                drift_for_spec,
                DriftInput(
                    target_repo=request.target_repo,
                    spec_dir=spec_dir,
                    spec_text=spec_text,
                ),
                **_FAST,
            )
            cached[spec_dir] = drifted
            return drifted

        return resolve

    async def _compute_drift(self, request: RoadmapInput) -> dict[str, bool]:
        """Refresh the drift cache for every landed spec in the current corpus.

        Drift is repo-authoritative and read-only: `drift_for_spec` shells git in an
        activity, so workflow code awaits the boolean result and injects it into the
        synchronous `compute_readiness` (FR-009). Only `state: landed` specs can drift;
        every other spec is reported as not drifted.
        """
        if self._roadmap is None:
            return {}
        drift: dict[str, bool] = {}
        resolver = self._drift_resolver(request)
        for entry in self._roadmap.entries:
            if entry.state is SpecState.LANDED:
                drift[entry.spec_dir] = await resolver(entry.spec_dir)
        return drift

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