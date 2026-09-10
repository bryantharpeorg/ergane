"""`ergane status`: the operator's morning question, answered in one screen.

What is running, what is it doing story by story, what is queued behind it,
what is waiting on a ready flip, and how fast is it moving. Every one of those
already had an answer somewhere — `build status` for one epic you already knew
the id of, `spec list` for the corpus, `roadmap status` for the scheduler,
`verification_results` for the clock — so this is a join, not a mechanism. It
re-queries nothing in its own way: the disposition is `factory.roadmap.
discovery`'s ladder, the per-epic table is `build status`'s renderer, readiness
is `compute_readiness`, and the wall-times are the evidence store's own columns.

Three properties are load-bearing:

- **It writes nothing.** No directory, no store, no signal (FR-002). The
  runtime-root resolver creates `.ergane/` as a side effect when neither root
  exists, so this module never calls it; the evidence store is opened through
  SQLite's `mode=ro` door and only when the file is already there.
- **Degraded is a mode, not an error.** An operator reaching for `ergane
  status` during an outage is the one who most needs the corpus half, so a
  Temporal failure becomes one note naming the address and an exit code that
  says "degraded", never an abort (FR-004). 052 split that into the two events
  it always was: the server not answering (`TRANSPORT_FAILED` — degraded, exit
  3) and a workflow refusing a reading the server did deliver (`QUERY_REFUSED`
  — the section says why, exit 0). One name for both is what let a refused
  roadmap query kill the whole command.
- **Pace is measurement.** `started_at`/`finished_at` bracket one verification,
  not one story: dispatch-to-verification and merge-queue time are not in the
  store at all. The output therefore carries attempt wall-times and a remaining
  count, and no arrival time anywhere (FR-003).

### Which basis "blocked by" is a fact about

`compute_readiness` takes two resolvers, and *which ones a caller injects is
the whole answer*. `ergane spec list` injects none, so a dependency counts as
satisfied only when its own frontmatter attests `state: landed`;
`RoadmapWorkflow` injects `landed_for=self._observed_resolver()` and resolves
landings it has watched. They disagree, and on 2026-08-15 the disagreement was
visible on one screen:

    $ ergane spec list specs
    011-agent-sandbox    ready   blocked by: 043-runtime-root-integrity
    $ ergane spec landed specs/043-runtime-root-integrity
    US1..US4 landed at ... (observed)

An operator reading the first line plans around a blocker that is not there —
the dangerous direction, because it is the one that stops work that would in
fact dispatch (finding
`interpreter/spec-list-reports-blockers-the-scheduler-does-not-see`).

This command does not inherit that. It injects a `landed_for` resolver that
reads the target repo's landing history through the existing `landed_facts`
reader — a spec is observed-landed when every story its spec declares has a
landing commit on the landing branch — and it *names the basis it used* on the
queue header. When no repo can be read the basis degrades to attestation, and
then every blocked line is labelled `[attestation only]`, because a blocked
line read on its own is exactly what misleads. The reading is done without
fetching (FR-002 again), which the header also says: a stale clone under-reports
landings, and the operator is entitled to know that is possible.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from temporalio.client import WorkflowQueryFailedError, WorkflowQueryRejectedError
from temporalio.service import RPCError

from factory.activities.roadmap_activities import _OPEN_EPIC_STATUS
from factory.activities.verify_activities import DEFAULT_VERIFICATION_DB_PATH
from factory.cli.errors import EXIT_OK, EXIT_TRANSPORT, OperatorError
from factory.registry import resolve_state_home
from factory.supervision.engine_identity import cli_version, engine_skew, read_identity
from factory.env import (
    ERGANE_VERIFICATION_DB_PATH_ENV,
    FACTORY_VERIFICATION_DB_PATH_ENV,
    resolve_env_path,
)
from factory.roadmap.discovery import (
    RoadmapOwner,
    RoadmapScheduleState,
    render_schedule_line,
    resolve_roadmap,
)
from factory.roadmap.models import (
    SPEC_NAME,
    LandedKind,
    LandedStatus,
    Roadmap,
    RoadmapError,
    SpecState,
    compute_readiness,
    read_roadmap,
)
from factory.verify.criteria import parse_spec
from factory.verify.models import RequirementKind
from factory.verify.store import attempt_timings, connect_readonly
from factory.workgraph.cli import DEFAULT_SPECS_ROOT
from factory.workgraph.delta import fingerprint_for
from factory.workgraph.landed import (
    _resolve_default_head as _landing_head,
    LandedFact,
    fingerprint,
    landed_facts,
)
from factory.workgraph.workflow import _TERMINAL_STATES
from factory.workgraph.worktree import landing_branch

#: The prefix `build`'s id seam applies; the epics section strips it back off to
#: recover the spec directory, which is what the evidence store is keyed by.
EPIC_ID_PREFIX = "epic-"

#: Node states that mean a story is done being worked, whichever way it ended.
#: Spelled as plain strings because the query answers with JSON, not enums.
_TERMINAL_NODE_STATES = frozenset(str(state) for state in _TERMINAL_STATES)


# --- the two ways a Temporal read fails ---------------------------------------
#
# Two names, because they are two events and this command says different things
# about them. Before 052 there was one name, and the difference cost the verb:
#
#     $ ergane status specs
#     ergane: unexpected error (RoadmapStatus.__init__() missing 1 required
#     positional argument: 'max_concurrent_nodes'); re-run with --debug
#     [exit 1]
#
# The roadmap query below was already wrapped in `except RPCError`, with a
# comment describing precisely that situation. It could never fire.
# `WorkflowQueryFailedError` is not an `RPCError` — `issubclass` is `False`, they
# are *siblings* under `TemporalError` — so a workflow-side refusal walked past
# the guard written for it and out through the CLI's boundary handler, taking
# the corpus half of the report with it. A guard is only as good as the class it
# names, and nothing in the suite was checking the name. Now something is
# (`tests/test_ergane_status.py`, the `EXPECTED_GUARDS` sweep).
#
# Neither tuple is a place to add `Exception`. A blanket catch around a query
# would have fixed the symptom and converted every future defect behind one into
# a blank section with a plausible note — the command would stop dying and start
# lying, which is the same silence one layer along (FR-004).

#: Transport: the server did not answer at all. Nothing this command wanted to
#: read is readable, so the report is degraded and exits `EXIT_TRANSPORT`.
TRANSPORT_FAILED: tuple[type[BaseException], ...] = (RPCError,)

#: The server answered and the *workflow* would not — most often because a
#: running history predates a field the query result now declares. Only the one
#: reading that was refused is missing, so the section that asked names the
#: cause and the command still exits 0. This is a degraded *reading*, not a
#: degraded connection, and conflating the two is what a single guard did.
QUERY_REFUSED: tuple[type[BaseException], ...] = (
    WorkflowQueryFailedError,
    WorkflowQueryRejectedError,
)


# --- the document -------------------------------------------------------------


@dataclass(frozen=True)
class RoadmapDisposition:
    """What owns dispatch, and what it says it is doing.

    The top half comes from the discovery ladder (owner, schedule, run, next
    tick); the bottom half from the run's own `roadmap_status` query, and is
    `None` when there is no run to ask.
    """

    owner: str
    workflow_id: str | None
    schedule_id: str | None
    schedule_paused: bool | None
    next_action_at: str | None
    looked_for: list[str]
    dispatch_paused: bool | None = None
    running: list[str] = field(default_factory=list)
    parked: int | None = None
    #: Why the bottom half is missing, when the run refused to answer. `None`
    #: whenever it answered *or* whenever there was no run to ask — an absent
    #: reading and a refused one look the same in the fields above, and only one
    #: of them is worth an operator's attention.
    dispatch_unavailable: str | None = None
    #: What the schedule is actually *doing* — `paused`, `running`, `starved` or
    #: `unknown` — decided on the location and copied here whole. The renderer
    #: below is handed a finished verdict rather than the `schedule_paused`
    #: boolean above and a clock, because a renderer that decides is a renderer
    #: the other verb can disagree with (FR-009). Carried as its plain word, as
    #: `owner` is, so `--json` says exactly what the human rendering says.
    schedule_state: str | None = None
    #: The evidence a starved line names, alongside `skipped_overlap_count`:
    #: how long since a tick *actually* started. `None` when none ever did.
    seconds_since_last_start: int | None = None
    #: Lifetime count of ticks the overlap policy skipped. Evidence inside the
    #: sentence, never a trigger — it never decreases.
    skipped_overlap_count: int | None = None


@dataclass(frozen=True)
class EpicView:
    """One running epic and its per-story table, as `epic_status` answers it."""

    workflow_id: str
    epic_id: str
    epic_state: str
    execution_status: str
    nodes: dict[str, Any]
    #: Why this epic has no table, when it refused the query. An epic that has
    #: closed is dropped instead; this field is only ever set for one that is
    #: open, listed, and unwilling to describe itself.
    refusal: str | None = None


@dataclass(frozen=True)
class AttemptPace:
    """One verification's measured wall-time. `seconds` is None if unparseable."""

    node_id: str
    attempt: int
    verdict: str
    seconds: int | None


@dataclass(frozen=True)
class EpicPace:
    """One epic's measured attempts and how many of its stories are still open."""

    epic_id: str
    attempts: list[AttemptPace]
    stories_total: int
    stories_remaining: int


@dataclass(frozen=True)
class QueueEntry:
    """One spec as the queue and drafts sections read it."""

    spec_dir: str
    state: str
    dispatchable: bool
    blockers: list[str]


@dataclass(frozen=True)
class ReadinessBasis:
    """Which facts decided "blocked", said in a sentence the operator can read."""

    observed: bool
    detail: str


@dataclass(frozen=True)
class FloorStatus:
    """The whole floor: one document, rendered human or `--json` (FR-005)."""

    specs_root: str
    roadmap: RoadmapDisposition | None
    epics: list[EpicView]
    queue: list[QueueEntry]
    drafts: list[QueueEntry]
    pace: list[EpicPace]
    readiness_basis: ReadinessBasis
    notes: list[str]
    degraded: bool


# --- the command --------------------------------------------------------------


def status_command(args: argparse.Namespace) -> int:
    """Read the floor and print it, once."""
    floor = asyncio.run(collect_floor(Path(args.specs_root)))
    if getattr(args, "as_json", False):
        print(json.dumps(asdict(floor), indent=2))
    else:
        print(render_floor(floor))
    # FR-004: the code distinguishes a report that is complete from one that had
    # to leave sections out. Transport is the reason it ever happens.
    return EXIT_TRANSPORT if floor.degraded else EXIT_OK


async def collect_floor(specs_root: Path) -> FloorStatus:
    """Join every source into one document, corpus first.

    Corpus first on purpose: it is the half that survives an outage, and doing
    it before the client is opened means a Temporal failure cannot cost it.
    """
    roadmap = _read_corpus(specs_root)
    basis, landed_for, drifted_for = _readiness_basis(roadmap, specs_root)
    readiness = compute_readiness(
        roadmap, landed_for=landed_for, drifted_for=drifted_for
    )
    queue = _entries(readiness, SpecState.READY)
    drafts = _entries(readiness, SpecState.DRAFT)

    notes: list[str] = []
    disposition: RoadmapDisposition | None = None
    epics: list[EpicView] = []
    degraded = False

    sentence = engine_skew(read_identity(resolve_state_home()))
    if sentence is not None:
        notes.append(sentence)

    from factory.cli.nouns import _open_client

    try:
        client = await _open_client()
    except OperatorError as error:
        notes.append(f"{error}; the roadmap and epics sections could not be read")
        degraded = True
    else:
        try:
            disposition = await _disposition(client, specs_root)
            epics = await _running_epics(client)
        except TRANSPORT_FAILED as error:
            notes.append(
                f"Temporal answered, but not the reads this needs ({error}); "
                "the roadmap and epics sections could not be read"
            )
            disposition = None
            epics = []
            degraded = True
        except QUERY_REFUSED as error:
            # A backstop, and worth naming as one rather than leaving to be
            # discovered: every query this command makes today is guarded at its
            # own call site, where the refusal can be reported in the section
            # that asked for it, so nothing reaches here yet. What this clause
            # buys is the *next* query added to either helper — it degrades
            # instead of killing the command, which is the failure mode 052
            # exists to end, and it does so before anyone remembers to guard it.
            # It is not `degraded`: the server answered.
            notes.append(
                f"a workflow refused a query ({error}); the reading it would "
                "have provided is missing from this report"
            )

    return FloorStatus(
        specs_root=str(specs_root),
        roadmap=disposition,
        epics=epics,
        queue=queue,
        drafts=drafts,
        pace=_pace(epics),
        readiness_basis=basis,
        notes=notes,
        degraded=degraded,
    )


# --- the corpus half ----------------------------------------------------------


def _read_corpus(specs_root: Path) -> Roadmap:
    """The corpus, or a refusal — a broken corpus yields no partial report."""
    try:
        return read_roadmap(specs_root)
    except RoadmapError as error:
        raise OperatorError(str(error)) from error
    except OSError as error:
        raise OperatorError(f"cannot read specs root {specs_root}: {error}") from error


def _entries(readiness: Any, state: SpecState) -> list[QueueEntry]:
    """Every spec in one declared state, in the corpus's own sorted order."""
    return [
        QueueEntry(
            spec_dir=spec.spec_dir,
            state=spec.rendered_state,
            dispatchable=spec.dispatchable,
            blockers=list(spec.blockers),
        )
        for spec in readiness.specs
        if spec.state is state
    ]


def _readiness_basis(
    roadmap: Roadmap, specs_root: Path
) -> tuple[
    ReadinessBasis,
    Callable[[str], LandedStatus | None] | None,
    Callable[[str], bool] | None,
]:
    """Decide what "landed" is allowed to mean here, and say so.

    Returns the sentence the queue header carries and the resolvers
    `compute_readiness` reads observed landings and drift through — both `None`
    when there is no repository to read, which is the case that degrades to
    attestation and therefore the case that must be labelled.
    """
    repo = _repo_holding(specs_root)
    if repo is None:
        return (
            ReadinessBasis(
                observed=False,
                detail=(
                    "attestation only — no git repository holds this specs root, "
                    "so a landing nothing attests is invisible here"
                ),
            ),
            None,
            None,
        )

    branch = landing_branch(repo)
    try:
        head = _landing_head(repo, branch, fetch=False)
    except Exception as error:  # WorktreeError, or a repo with no commits yet
        return (
            ReadinessBasis(
                observed=False,
                detail=f"attestation only — cannot read branch {branch}: {error}",
            ),
            None,
            None,
        )

    return (
        ReadinessBasis(
            observed=True,
            detail=(
                f"attestation, plus landings on {branch} ({head[:12]}) in {repo}, "
                "read without fetching"
            ),
        ),
        _observed_landed_resolver(roadmap, specs_root, repo, branch),
        _drifted_landed_resolver(specs_root, repo, branch),
    )


def _repo_holding(specs_root: Path) -> Path | None:
    """The git repository the corpus lives in, or None.

    `.git` is tested for existence rather than for being a directory: in a git
    *worktree* it is a file, and an operator running this from a worktree is
    running it from a repository.
    """
    current = specs_root.resolve()
    while True:
        if (current / ".git").exists():
            return current
        if current == current.parent:
            return None
        current = current.parent


def _observed_landed_resolver(
    roadmap: Roadmap, specs_root: Path, repo: Path, branch: str
) -> Callable[[str], LandedStatus | None]:
    """`compute_readiness`'s `landed_for`, backed by the repo's landing history.

    A spec is observed-landed when its spec declares at least one story and
    every declared story has a landing commit reachable from the landing branch.
    A spec whose frontmatter already attests `state: landed` is answered `None`
    without touching git: the attested path in `compute_readiness` satisfies it
    anyway, and a status command should not run a log scan to learn something
    the file already said. Answers are cached, so the corpus costs one scan per
    dependency actually consulted, not one per edge.
    """
    states = {entry.spec_dir: entry.state for entry in roadmap.entries}
    cache: dict[str, LandedStatus | None] = {}

    def resolve(spec_dir: str) -> LandedStatus | None:
        if spec_dir not in cache:
            cache[spec_dir] = (
                None
                if states.get(spec_dir) is SpecState.LANDED
                else _observed_landing(repo, branch, specs_root, spec_dir)
            )
        return cache[spec_dir]

    return resolve


def _drifted_landed_resolver(
    specs_root: Path, repo: Path, branch: str
) -> Callable[[str], bool]:
    """`compute_readiness`'s `drifted_for`, backed by the same landing facts.

    A story drifts when its pinned fingerprint and the fingerprint in the
    working-tree spec differ. A story without a baseline cannot say either way,
    so it is skipped; an unreadable repository is reported as not drifted, the
    same conservative direction `_observed_landing` takes. Reporting callers
    never fetch: staleness remains visible in the readiness basis.
    """
    facts_by_spec: dict[str, dict[str, LandedFact]] = {}

    def resolve(spec_dir: str) -> bool:
        if spec_dir not in facts_by_spec:
            try:
                facts_by_spec[spec_dir] = landed_facts(
                    repo,
                    spec_dir,
                    default_branch=branch,
                    fetch=False,
                )
            except Exception:
                facts_by_spec[spec_dir] = {}

        declared = _declared_story_keys(specs_root / spec_dir / SPEC_NAME)
        if not declared:
            return False

        for story_key in declared:
            fact = facts_by_spec[spec_dir].get(story_key)
            if fact is None:
                continue
            try:
                pinned = fingerprint(repo, fact.commit, spec_dir, story_key)
            except Exception:
                continue
            try:
                spec_text = (specs_root / spec_dir / SPEC_NAME).read_text(
                    encoding="utf-8"
                )
            except OSError:
                continue
            current = fingerprint_for(spec_text, story_key)
            if pinned.digest is not None and current.digest != pinned.digest:
                return True
        return False

    return resolve


def _observed_landing(
    repo: Path, branch: str, specs_root: Path, spec_dir: str
) -> LandedStatus | None:
    """Landed iff every story the spec declares has landed. Any doubt is `None`.

    `None` rather than `LandedStatus(landed=False)` on failure, deliberately: it
    lets `compute_readiness` fall through to the frontmatter, so an unreadable
    repository can only ever make this command *more* conservative than the
    attested reading, never less.
    """
    declared = _declared_story_keys(specs_root / spec_dir / SPEC_NAME)
    if not declared:
        return None
    try:
        facts = landed_facts(repo, spec_dir, default_branch=branch, fetch=False)
    except Exception:
        return None
    if all(story_key in facts for story_key in declared):
        return LandedStatus(landed=True, kind=LandedKind.OBSERVED)
    return None


def _declared_story_keys(spec_path: Path) -> tuple[str, ...]:
    """The story keys a spec declares, or `()` if it cannot be read or parsed."""
    try:
        text = spec_path.read_text(encoding="utf-8")
    except OSError:
        return ()
    try:
        requirements = parse_spec(text)
    except Exception:
        return ()
    return tuple(
        requirement.key
        for requirement in requirements
        if requirement.kind is RequirementKind.STORY
    )


# --- the Temporal half --------------------------------------------------------


async def _disposition(client: Any, specs_root: Path) -> RoadmapDisposition:
    """Where the roadmap is, what owns it, and what it says it is doing.

    The location is US2's ladder verbatim — bare workflow, then owning schedule,
    then newest timestamped run — so a schedule-driven floor is read here for
    the same reason `ergane roadmap status` can read it.
    """
    location = await resolve_roadmap(client, str(specs_root))
    document: Mapping[str, Any] | None = None
    refusal: str | None = None
    if location.workflow_id is not None:
        try:
            document = await client.get_workflow_handle(location.workflow_id).query(
                "roadmap_status"
            )
        except TRANSPORT_FAILED:
            # The run exists but will not answer: the disposition is still real,
            # and it is more useful than nothing.
            document = None
        except QUERY_REFUSED as error:
            # Same outcome for the document, deliberately different for the
            # report. The run reached the server and refused this reading, which
            # is a fact about the *run* — a history recorded before the query
            # result grew a field, most often — and an operator who is told only
            # "unavailable" goes to the Temporal UI to find out why. So the
            # cause is carried up and printed where it was asked for. The
            # disposition around it stays, for the reason above: it came from
            # the discovery ladder, not from the query, and it is still true.
            document = None
            refusal = str(error) or type(error).__name__

    # One clock for the verdict and for the evidence it names, so the two halves
    # of a starved sentence cannot be measured a moment apart.
    now = datetime.now(timezone.utc)
    return RoadmapDisposition(
        owner=str(location.owner.value),
        workflow_id=location.workflow_id,
        schedule_id=location.schedule_id,
        schedule_paused=location.schedule_paused,
        next_action_at=location.next_action_at,
        looked_for=list(location.looked_for),
        dispatch_paused=None if document is None else bool(document.get("paused")),
        running=[] if document is None else list(document.get("running") or []),
        parked=None if document is None else len(document.get("parked") or []),
        dispatch_unavailable=refusal,
        schedule_state=str(location.schedule_state_at(now)),
        seconds_since_last_start=location.seconds_since_last_start(now),
        skipped_overlap_count=location.skipped_overlap_count,
    )


async def _running_epics(client: Any) -> list[EpicView]:
    """Every open `epic-*` workflow, queried for its story table.

    Listing rather than asking the roadmap for its children (the plan's route
    choice): it is the only reading that still works when the roadmap is paused
    with an epic in flight, which is precisely the floor an operator most wants
    to see. The visibility filter is the roadmap's own capacity query, so the
    narrowing happens on the server and a closed epic never reaches the report.
    """
    listed: list[tuple[str, str]] = []
    async for execution in client.list_workflows(
        f'ExecutionStatus = "{_OPEN_EPIC_STATUS}"'
    ):
        workflow_id = str(execution.id)
        if workflow_id.startswith(EPIC_ID_PREFIX):
            listed.append((workflow_id, _execution_status(execution)))

    views: list[EpicView] = []
    for workflow_id, execution_status in sorted(listed):
        try:
            document = await client.get_workflow_handle(workflow_id).query("epic_status")
        except TRANSPORT_FAILED:
            # An epic that closed between the listing and the query is not an
            # error; it is simply no longer part of the answer.
            continue
        except QUERY_REFUSED as error:
            # Not that event. The server reached this epic and it is still open
            # — it came back from a filter that asks for running executions —
            # so dropping it would under-report the floor by exactly the epic
            # something is wrong with. It is listed without a table instead,
            # carrying the reason it has none.
            views.append(
                EpicView(
                    workflow_id=workflow_id,
                    epic_id=workflow_id[len(EPIC_ID_PREFIX) :],
                    epic_state="",
                    execution_status=execution_status,
                    nodes={},
                    refusal=str(error) or type(error).__name__,
                )
            )
            continue
        views.append(
            EpicView(
                workflow_id=workflow_id,
                epic_id=workflow_id[len(EPIC_ID_PREFIX) :],
                epic_state=str(document.get("epic_state", "")),
                execution_status=execution_status,
                nodes=dict(document.get("nodes") or {}),
            )
        )
    return views


def _execution_status(execution: Any) -> str:
    """The listing's own execution status, or the status that was filtered for."""
    status = getattr(execution, "status", None)
    name = getattr(status, "name", None)
    return str(name) if name else _OPEN_EPIC_STATUS.upper()


# --- pace ---------------------------------------------------------------------


def _pace(epics: Sequence[EpicView]) -> list[EpicPace]:
    """Measured attempt wall-times per running epic, plus what is still open.

    An epic that refused its query is skipped rather than counted: its story
    totals would both be zero, and "0 of 0 stories remaining" is a measurement
    the operator would have no way to distinguish from a finished epic.
    """
    measurable = [epic for epic in epics if epic.refusal is None]
    if not measurable:
        return []
    conn = open_store_readonly(_verification_store_path())
    try:
        return [_epic_pace(conn, epic) for epic in measurable]
    finally:
        if conn is not None:
            conn.close()


def _epic_pace(conn: sqlite3.Connection | None, epic: EpicView) -> EpicPace:
    timings = [] if conn is None else attempt_timings(conn, epic.epic_id)
    return EpicPace(
        epic_id=epic.epic_id,
        attempts=[
            AttemptPace(
                node_id=timing.node_id,
                attempt=timing.attempt,
                verdict=timing.verdict,
                seconds=_seconds_between(timing.started_at, timing.finished_at),
            )
            for timing in timings
        ],
        stories_total=len(epic.nodes),
        stories_remaining=sum(
            1
            for node in epic.nodes.values()
            if str(node.get("state")) not in _TERMINAL_NODE_STATES
        ),
    )


def open_store_readonly(path: str | Path) -> sqlite3.Connection | None:
    """The evidence store, read-only, or `None` when there is nothing to read.

    Both halves are FR-002. The existence check is what stops a report from
    creating the store (and its parent directory) as a side effect of asking
    about it, and `connect_readonly` is what makes "not opened for write" a
    property of the connection rather than of this module's manners.

    One thing `mode=ro` does *not* prevent, said plainly rather than left to be
    discovered: reading a WAL-mode database materialises its `-wal`/`-shm`
    sidecars if they are absent, because that is how SQLite arranges shared
    access. No directory is created, no row is touched, and the connection still
    refuses every write — but it is a file appearing beside a store that already
    existed, so it is written down here rather than claimed away.
    """
    location = Path(path)
    if not location.exists():
        return None
    try:
        return connect_readonly(location)
    except sqlite3.Error:
        return None


def _verification_store_path() -> Path:
    return resolve_env_path(
        ERGANE_VERIFICATION_DB_PATH_ENV,
        FACTORY_VERIFICATION_DB_PATH_ENV,
        DEFAULT_VERIFICATION_DB_PATH,
    )


def _seconds_between(started_at: str, finished_at: str) -> int | None:
    """Whole seconds between two stamps, or None if either will not parse."""
    try:
        started = datetime.fromisoformat(started_at)
        finished = datetime.fromisoformat(finished_at)
    except (TypeError, ValueError):
        return None
    return int((finished - started).total_seconds())


def _duration(seconds: int | None) -> str:
    """`45s`, `12m30s`, `2h10m30s` — a wall-time, never an instant."""
    if seconds is None:
        return "unknown"
    if seconds < 0:
        return "unknown"
    hours, rest = divmod(seconds, 3600)
    minutes, remainder = divmod(rest, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{remainder:02d}s"
    if minutes:
        return f"{minutes}m{remainder:02d}s"
    return f"{remainder}s"


# --- the human view -----------------------------------------------------------


def render_floor(floor: FloorStatus) -> str:
    """Five sections, in the order the morning question is asked.

    Section headers are unindented and everything else is indented, which is
    what lets the report be skimmed — and what lets a test assert the order
    without matching prose.
    """
    lines: list[str] = []
    for note in floor.notes:
        lines.append(f"note: {note}")
    if floor.notes:
        lines.append("")

    lines += _section("roadmap", _roadmap_lines(floor))
    lines += _section("epics", _epic_lines(floor))
    lines += _section(
        f"queue (readiness: {floor.readiness_basis.detail})", _queue_lines(floor)
    )
    lines += _section("drafts", _draft_lines(floor))
    lines += _section("pace", _pace_lines(floor))
    return "\n".join(lines).rstrip("\n")


def _section(header: str, body: Iterable[str]) -> list[str]:
    return [header, *(f"  {line}" for line in body), ""]


def _roadmap_lines(floor: FloorStatus) -> list[str]:
    if floor.roadmap is None:
        return ["unavailable (see note)"]
    disposition = floor.roadmap
    lines: list[str] = []
    if disposition.schedule_id is not None:
        # Read, never re-derived: the verdict was decided on the location and
        # `_disposition` copied it here. This line and `roadmap.py`'s were the
        # same sentence written twice, which is why one could be fixed while the
        # other went on lying (FR-009).
        lines.append(
            render_schedule_line(
                disposition.schedule_id,
                disposition.schedule_state or RoadmapScheduleState.UNKNOWN.value,
                seconds_since_last_start=disposition.seconds_since_last_start,
                skipped_overlap_count=disposition.skipped_overlap_count,
            )
        )
    if disposition.owner == RoadmapOwner.RUN.value:
        lines.append("schedule: none found")
    if disposition.workflow_id is not None:
        lines.append(f"run: {disposition.workflow_id}")
    if disposition.next_action_at is not None:
        lines.append(f"next tick: {disposition.next_action_at}")
    if disposition.dispatch_paused is not None:
        lines.append(f"dispatch: {'paused' if disposition.dispatch_paused else 'running'}")
        lines.append(f"running: {', '.join(disposition.running) or '-'}")
        lines.append(f"parked: {disposition.parked}")
    if disposition.dispatch_unavailable is not None:
        lines.append(f"dispatch: unavailable ({disposition.dispatch_unavailable})")
    if not lines:
        lines.append(f"none running (looked for {', then '.join(disposition.looked_for)})")
    return lines


def _epic_lines(floor: FloorStatus) -> list[str]:
    if floor.roadmap is None and not floor.epics:
        return ["unavailable (see note)"]
    if not floor.epics:
        return ["none running"]

    # The per-epic table is `build status`'s renderer, reused rather than
    # re-formatted, so the two verbs cannot drift into two shapes.
    from factory.cli.nouns.build import render_status

    lines: list[str] = []
    for epic in floor.epics:
        if epic.refusal is not None:
            lines.append(f"{epic.epic_id}  unavailable ({epic.refusal})")
            continue
        document = {"epic_state": epic.epic_state, "nodes": epic.nodes}
        lines.extend(
            render_status(epic.epic_id, document, epic.execution_status).splitlines()
        )
    return lines


def _queue_lines(floor: FloorStatus) -> list[str]:
    if not floor.queue:
        return ["nothing is ready"]
    width = max(len(entry.spec_dir) for entry in floor.queue)
    state_width = max(len(entry.state) for entry in floor.queue)
    label = "" if floor.readiness_basis.observed else " [attestation only]"
    lines: list[str] = []
    for entry in floor.queue:
        base = f"{entry.spec_dir.ljust(width)}  {entry.state.ljust(state_width)}"
        if entry.blockers:
            lines.append(f"{base}  blocked by: {', '.join(entry.blockers)}{label}")
        elif not entry.dispatchable:
            lines.append(f"{base}  awaiting attestation")
        else:
            lines.append(f"{base}  dispatchable")
    return lines


def _draft_lines(floor: FloorStatus) -> list[str]:
    if not floor.drafts:
        return ["none"]
    width = max(len(entry.spec_dir) for entry in floor.drafts)
    return [f"{entry.spec_dir.ljust(width)}  {entry.state}" for entry in floor.drafts]


def _pace_lines(floor: FloorStatus) -> list[str]:
    if not floor.pace:
        if floor.roadmap is None:
            return ["unavailable (see note)"]
        if floor.epics:
            return ["no running epic answered with a story table"]
        return ["no epic is running"]

    lines: list[str] = []
    for epic in floor.pace:
        lines.append(epic.epic_id)
        if not epic.attempts:
            lines.append("  no attempt recorded for this epic yet")
        for attempt in epic.attempts:
            lines.append(
                f"  {attempt.node_id}  attempt {attempt.attempt}  "
                f"{attempt.verdict}  verified in {_duration(attempt.seconds)}"
            )
        lines.append(
            f"  {epic.stories_remaining} of {epic.stories_total} stories remaining"
        )
    lines.append("measured wall-times of finished attempts only")
    return lines


# --- parser -------------------------------------------------------------------


def add_status_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "status",
        help="what the whole floor is doing right now",
        description=(
            "The morning question in one screen: the roadmap's disposition, "
            "every running epic with its stories, the ready queue with its "
            "blockers, the drafts, and each epic's measured attempt wall-times. "
            "Reads only; writes, signals and creates nothing."
        ),
    )
    parser.add_argument(
        "specs_root",
        nargs="?",
        default=DEFAULT_SPECS_ROOT,
        help=f"the specs root to read (default: {DEFAULT_SPECS_ROOT})",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="print the whole floor as one document instead of the five sections",
    )
    parser.set_defaults(run=status_command)
