# Implementation Plan: the status board names the spec it cannot dispatch

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## What already exists, and where

**The park listing is already on the wire; two `len()` calls are the whole
defect.** `_park` (`factory/roadmap/workflow.py:1433` — `RoadmapWorkflow._park`)
writes a `ParkedFinding` (`factory/roadmap/workflow.py:351` — `ParkedFinding`)
with three fields — `spec_dir`, `check`, `detail` — and `roadmap_status`
(`factory/roadmap/workflow.py:725` — `RoadmapWorkflow.roadmap_status`) returns
the list of them, typed `parked: list[ParkedFinding]` at
`factory/roadmap/workflow.py:443`. `_disposition` (`factory/cli/status.py:511` —
`_disposition`) receives that document and, at `factory/cli/status.py:554`, does
this:

```python
        parked=None if document is None else len(document.get("parked") or []),
```

The names and reasons are in `document` at that moment. US1 is the work of
carrying them one field further — in both places that drop them.

**The `ergane status specs` surfaces, and why there is only one renderer to
edit there.** The human roadmap block is `factory/cli/status.py:753` —
`_roadmap_lines`, whose parked line is `factory/cli/status.py:780`:

```python
        lines.append(f"parked: {disposition.parked}")
```

That verb's `--json` has no renderer of its own: `status_command`
(`factory/cli/status.py:272` — `status_command`) prints `asdict(floor)` at
`factory/cli/status.py:276`, so a field added to the `RoadmapDisposition` record
(`factory/cli/status.py:164` — `RoadmapDisposition`, whose `parked: int | None`
sits at `factory/cli/status.py:180`) reaches the JSON with no second edit. That
is what makes FR-002 nearly free and FR-004 worth stating: the JSON *will* change
shape, and the human block must not.

**The second board, in a different file, does the same collapse — and its
`--json` is already correct.** `_render_status` (`factory/cli/roadmap.py:484` —
`_render_status`) is handed the whole `RoadmapStatus`, findings included, and
prints at `factory/cli/roadmap.py:501`:

```python
        f"parked: {len(status.parked)}",
```

`roadmap_status_command` (`factory/cli/roadmap.py:420` —
`roadmap_status_command`) prints `asdict(status)` for `--json`, so that half
already carries `spec_dir`, `check` and `detail` per finding and needs nothing.
Only the human render loses them. FR-013 is that one block, and it is where the
incident was actually read: the ledger's roadmap-stall row records its
reproduction as "watch `ergane roadmap status <specs-root>` report `parked: 1`",
and `roadmap_unpark_command` (`factory/cli/roadmap.py:403` —
`roadmap_unpark_command`) already writes the fixed behaviour into its docstring
at `factory/cli/roadmap.py:406` as though it were true.

**The one line US2 changes.** `factory/roadmap/models.py:607` —
`compute_readiness`:

```python
        dispatchable = entry.state is SpecState.READY and not blockers
```

The line below it computes `drifted` and is gated on `SpecState.LANDED`, so it
cannot reach a `ready` spec. The injected `observed(...)` resolver is called only
inside the `depends_on` loop above, for an entry's *dependencies*, never for the
entry's own `spec_dir`.

**Both resolvers are injected on purpose.** `factory/roadmap/models.py:587` —
`compute_readiness` says why in its own docstring: "Both resolvers are injected
so git reads stay out of workflow code (constitution IV)." FR-008 preserves that.
The answer US2 needs must arrive through the resolver, not through a new git
read.

**The resolver that already produces the needed fact exists, on the CLI side.**
`factory/cli/status.py:441` — `_observed_landed_resolver` is
`compute_readiness`'s `landed_for`, backed by the repository's landing history
(`_observed_landing`, `factory/cli/status.py:469` — `_observed_landing`, which
calls `landed_facts`). `collect_floor` (`factory/cli/status.py:284` —
`collect_floor`) already injects it at `factory/cli/status.py:292`, one line
above the queue build at `factory/cli/status.py:293`. For US2 this means the fact
is in the process today and only the predicate ignores it.

**The rendered state, and the constant beside it.** `factory/roadmap/models.py:544`
— `SpecReadiness.rendered_state` today rewrites exactly one state:

```python
        if self.drifted and self.state is SpecState.LANDED:
            return RENDERED_AMENDED
        return self.state.value
```

`RENDERED_AMENDED` is defined at `factory/roadmap/models.py:91`. US2's third word
is a second constant beside it and a second branch here — which means
`SpecReadiness` (`factory/roadmap/models.py:516` — `SpecReadiness`) must carry
the fact as a field, exactly as it carries `drifted`, because `rendered_state` is
a property with no access to the resolver.

**The one renderer that follows US2 for free, and the two that do not.**
`_entries` (`factory/cli/status.py:364` — `_entries`) already copies
`spec.rendered_state` and `spec.dispatchable` into each `QueueEntry`, so the
`ergane status specs` queue follows `factory/roadmap/models.py` with no edit —
that one is genuinely free. The other two are not, and the refined draft of this
plan got one of them wrong:

- `_render_roadmap` (`factory/roadmap/cli.py:92` — `_render_roadmap`) does print
  `rendered_state` and nothing else, but it can never print the third word,
  because `render_command` (`factory/roadmap/cli.py:46` — `render_command`)
  calls `compute_readiness` at `factory/roadmap/cli.py:63` with **no**
  `landed_for` argument at all. That is deliberate:
  `factory/roadmap/cli.py:74` — `_cli_drift_resolver` documents that the render
  command "must work on a laptop with no factory running" and "therefore cannot
  read the target repo's landing history". `ergane roadmap render` is out of
  scope and stays as it is.
- The per-spec board at `factory/cli/roadmap.py:508`, inside
  `factory/cli/roadmap.py:484` — `_render_status`, prints
  `spec.rendered_state` and a `[*]` marker from `spec.dispatchable`. It is fed by
  the workflow query, not by `factory/roadmap/models.py` directly, so it follows
  only once FR-014 lands. No edit is needed there either — but a US2 reviewer who
  expects that board to change is looking at a US3 outcome.

**What US2 *does* have to edit, and would miss.** `factory/cli/status.py:810` —
`_queue_lines` decides the word from the blockers list, not from the flag:

```python
        if entry.blockers:
            lines.append(f"{base}  blocked by: {', '.join(entry.blockers)}{label}")
        else:
            lines.append(f"{base}  dispatchable")
```

**The roadmap calls `compute_readiness` TWICE, and both calls are fed the same
run-local resolver.** The scheduling pass calls it at
`factory/roadmap/workflow.py:851`, inside `factory/roadmap/workflow.py:872` —
`RoadmapWorkflow._run_inner`; the `roadmap_status` query calls it again at
`factory/roadmap/workflow.py:687`, inside `factory/roadmap/workflow.py:725` —
`RoadmapWorkflow.roadmap_status`. Both hand it `self._observed_resolver()`
(`factory/roadmap/workflow.py:1441` — `RoadmapWorkflow._observed_resolver`),
which reads `self._landed` — the children *this run* watched, declared at
`factory/roadmap/workflow.py:624`. The dispatchable list is built immediately
below the pass's call, at `factory/roadmap/workflow.py:864`, and the clause that
strands a partially landed spec is `entry.spec_dir not in self._landed` at
`factory/roadmap/workflow.py:870`.

**How the drift precedent solves exactly this two-call-sites problem, and the
shape US3 must copy.** `self._drift` is written once per pass at
`factory/roadmap/workflow.py:916` — the comment two lines above it, at
`factory/roadmap/workflow.py:848`, says "The same map is cached for the
`roadmap_status` query" — consumed by the pass at
`factory/roadmap/workflow.py:854` and read again by the query at
`factory/roadmap/workflow.py:690`. That instance cache is *why* the query and the
dispatch loop already agree about `amended`. The landed answer needs the same
treatment, and the cheapest way to get it is to teach
`factory/roadmap/workflow.py:1441` — `RoadmapWorkflow._observed_resolver` to
answer from the cached read as well as from `self._landed`: one change, and both
call sites follow.

**"Landed" is fingerprint-blind, and that is what makes the rule need a third
input.** `factory/cli/status.py:469` — `_observed_landing` answers
`LandedStatus(landed=True)` as soon as every declared story key appears in
`factory/workgraph/landed.py:130` — `landed_facts`, and that scan matches commit
*subjects*; it never compares the spec's content to what landed. The delta does:
`factory/workgraph/delta.py:9` re-opens every landed story whose fingerprint
changed. And `factory/roadmap/models.py:586` — `compute_readiness` documents the
operator's route for an amended spec in its own docstring — "a drifted spec
renders as `amended` and is not dispatchable until the operator flips `state` to
`ready`". Flipped back to `ready`, that spec has a landing commit for every story
and real work in its delta. Landed and built are therefore two different facts,
and only the pair (landed, not drifted) means "nothing left to do".

**The drift seam exists, and every caller that matters is wired wrong for this
use.** `factory/roadmap/models.py:592` — `compute_readiness` defaults
`drifted_for` to a lambda returning `False`, so "nobody supplied an answer" and
"not drifted" are the same value today. Three callers:
`collect_floor` supplies none at all (`factory/cli/status.py:292`);
`factory/roadmap/cli.py:46` — `render_command` supplies one that always answers
`False` and no `landed_for`; and the workflow supplies
`self._drift.get(spec_dir, False)`, a map `factory/roadmap/workflow.py:1508` —
`RoadmapWorkflow._compute_drift` fills for `SpecState.LANDED` entries only, with
`factory/roadmap/workflow.py:1455` — `RoadmapWorkflow._drift_resolver` short-
circuiting any non-`landed` spec to `False` a second time. Every one of them
would answer "not drifted" for a `ready` spec that is drifted. FR-015 is the
rule that makes that safe: the built determination requires an answer that was
*supplied*, and treats the default as drift.

**What US2 needs on the CLI side, and the two public helpers it is built from.**
`factory/cli/status.py:378` — `_readiness_basis` already resolves the repository
and the landing branch and hands back the observed-landed resolver; the drift
resolver belongs beside it, injected at the same call
(`factory/cli/status.py:292`). Its body is the comparison
`factory/activities/roadmap_activities.py:512` — `_drift_from_git` makes, out of
two public functions: `factory/workgraph/landed.py:407` — `fingerprint` pins a
story at its landing commit, and `factory/workgraph/delta.py:48` —
`fingerprint_for` computes the same digest from the spec text on disk. Different
digests for any story means drifted.

**The precedent US3 copies, in full.** Drift is the same problem already solved:
`_compute_drift` (`factory/roadmap/workflow.py:1508` —
`RoadmapWorkflow._compute_drift`) awaits one activity per candidate spec and
injects the result into the same `compute_readiness` call; the activity is
`drift_for_spec` (`factory/activities/roadmap_activities.py:496` —
`drift_for_spec`) over `DriftInput` (`factory/activities/roadmap_activities.py:482`
— `DriftInput`), with a module-level test seam at
`factory/activities/roadmap_activities.py:491` so scheduler tests need no real
clone, a blocking half at `factory/activities/roadmap_activities.py:512` —
`_drift_from_git`, and a registration line at `factory/worker.py:192`.

**The cost US3 removes, and the backstop it must not remove.** `_dispatch`
(`factory/roadmap/workflow.py:1247` — `RoadmapWorkflow._dispatch`) runs
`clone_target` at `factory/roadmap/workflow.py:1187` and `onboard_target` at
`factory/roadmap/workflow.py:1334` before reaching:

```python
        if not graph.nodes:
            self._park(spec_dir, "derive", "delta is empty: all stories are satisfied")
            return
```

at `factory/roadmap/workflow.py:1269`.

**The live instance, on this floor, today.**
`specs/057-a-new-repo-gets-a-constitution/spec.md:2` reads `state: ready` and is
the only `ready` spec in the corpus at `602a92c`; all four of its declared
stories are landed on `ergane-buildout` (`8ee5e9c` US1, `602a92c` US2,
`5c43d4a` US3, `1027a05` US4). It is therefore the built-but-unattested spec this
whole spec exists for, and the spec the roadmap selects, clones, onboards and
parks on every tick with a free slot right now. Use it as the fixture in the
operator verification below rather than searching the corpus for one.

**Neighbours, read.** Nothing has landed on any file above since 2026-09-02
(126's three stories). 057's four landings between the drafting commit and
`602a92c` touch `factory/cli/init.py`, `factory/constitution.py`,
`factory/stack_packs.py` and `factory/mergequeue/onboard.py`; the last of those
adds `_standards_finding` to `factory/mergequeue/onboard.py:479` —
`evaluate_init_facts`. That finding cannot reach a roadmap park, but **not**
because `onboard_target_repo` is off the roadmap's path — it is on it:
`onboard_target` delegates to `factory/activities/merge_activities.py:785` —
`validate_target_repo`, which calls `onboard_target_repo`. The reason is that
this call supplies no `init_facts`, and `evaluate_init_facts` returns `()` when
they are `None` (`factory/mergequeue/onboard.py:429`); only
`factory/cli/init.py:2289`, the `ergane init --check` door, supplies them. The
park detail US1 reports is therefore unchanged in shape, and no anchor in this
plan moved.

## Traps

**Trap 1 — THE EXPENSIVE HALF IS ALREADY FIXED. DO NOT BUILD IT AGAIN AND DO NOT
CLAIM IT.** The source document says the next tick "would have rebuilt three
landed stories". It would not. The refusal at
`factory/roadmap/workflow.py:1269` fires exactly on this case, before any child
epic starts, so **no agent tokens are spent today**. An implementer who reads the
finding text and sets out to stop a runaway rebuild will find nothing to fix,
conclude the finding is invalid, and close a real defect. What actually survives
is (a) a clone-and-onboard cycle paid on every pass with a free epic slot — up to
288 a day per such spec at a five-minute schedule — and (b) the legibility gap.
Scope to those.

**Trap 2 — THE PARK LISTING IS ALREADY IN THE PAYLOAD; DO NOT BUILD A STORE FOR
IT.** FR-001, FR-002, FR-013. `_parked` (`factory/roadmap/workflow.py:565`) is
run-local and a scheduled run completes in about twenty seconds, which is true and
is *not* US1's problem: today's count has exactly that lifetime, because it too is
read from the live run's query at `factory/cli/status.py:554`, and the human
block only prints a parked line at all when a run answered. An implementer who
reads "run-local" as "US1 must find a durable source" will design a park store,
a sidecar file or a history scan — days of work, a write on the read path, and a
different lifetime from the count it replaces. The change is: stop calling
`len()`, carry `spec_dir`, `check` and `detail` to `RoadmapDisposition`
(`factory/cli/status.py:164` — `RoadmapDisposition`), print them under the
existing line at `factory/cli/status.py:780`, and print them under the second
count at `factory/cli/roadmap.py:501` too. Park durability is out of scope and
unchanged.

**Trap 3 — NO PARK CARRIES AN UNSATISFIED `depends_on_landed` EDGE.** FR-003.
The draft of this spec required the reason to separate an unsatisfied dependency
edge from the other park causes. It cannot: every `self._park(...)` call site in
`factory/roadmap/workflow.py` passes one of `clone`, `derive`,
`preflight:<check>`, `onboarding`, `manifest`, `collision` — grep them and count
— and an unsatisfied edge never parks, it renders as `blocked by:` on the queue
line at `factory/cli/status.py:810` — `_queue_lines`. Count from the call sites,
not from the record: the docstring on `factory/roadmap/workflow.py:351` —
`ParkedFinding` is itself stale, listing five checks and omitting `manifest`, so
an implementer who reads the class while carrying its three fields gets five and
may conclude this spec invented a park class. An implementer who tries to
satisfy the old wording will invent a seventh park class, which means writing to
`_parked` from a new place and reporting a spec as parked that the roadmap never
refused. Carry the two fields that exist.

**Trap 4 — THE NEW STATE IS NOT `landed`.** FR-006. It is tempting to render a
fully-built `ready` spec as `landed` and be done. That asserts an attestation
nobody made, and attestation is the operator act the state exists to prompt. The
distinction goes in `factory/roadmap/models.py:544` —
`SpecReadiness.rendered_state`, beside the existing `landed` → `amended` rewrite,
with its constant beside `factory/roadmap/models.py:91`.

**Trap 5 — DO NOT MAKE `compute_readiness` READ GIT.** FR-008. The function is
workflow code and `factory/roadmap/models.py:587` — `compute_readiness` says so.
The landed fact arrives through the injected resolver — which already exists at
`factory/cli/status.py:441` — `_observed_landed_resolver` — or it does not
arrive. A `subprocess` or `landed_facts` call added inside
`factory/roadmap/models.py` passes every test on a developer's checkout and is
non-deterministic inside a workflow.

**Trap 6 — `_queue_lines` PRINTS `dispatchable` WITHOUT READING THE FLAG, AND THE
REPLACEMENT STRING IS PART OF THE REQUIREMENT.** FR-011, US2-S3.
`factory/cli/status.py:810` — `_queue_lines` prints `blocked by: ...` when
`entry.blockers` is non-empty and the literal word `dispatchable` otherwise. A
built spec has no blockers, so a US2 that changes only
`factory/roadmap/models.py` produces a queue line reading
`131-...  built  dispatchable`, passes a models-only unit test, and ships the
contradiction. Reproduce it before editing: it is one rendered line. The second
half of the trap is quieter — an implementer who deletes the word and prints
nothing has made the board *less* legible than it was, on a spec whose subject is
legibility. FR-011 pins the else-branch to `awaiting attestation`, which is the
`operator/...` ledger row's own phrase for the fix ("mark a spec whose stories are
all landed-by-content but whose frontmatter is not `landed` as awaiting
attestation, rather than as dispatchable work"). Assert the exact string.

**Trap 7 — THE WORKFLOW'S LANDED RESOLVER IS EMPTY ON A SCHEDULED RUN, SO US2
ALONE CHANGES NOTHING INSIDE THE ROADMAP.** FR-009. This is the trap that decides
whether US3 is real work or a green no-op. `factory/roadmap/workflow.py:851`
hands `compute_readiness` the resolver at `factory/roadmap/workflow.py:1441` —
`RoadmapWorkflow._observed_resolver`, which answers only for specs *this run*
watched a child of; the schedule starts a fresh run every five minutes, so on the
run that pays the clone that map is empty and `landed` is always None. An
implementer who "guards the early exit on the distinction US2 introduces" inside
`_dispatch` guards on a fact that is never true, watches every test pass, and
changes nothing on a real floor. US3's work is a landed read *of the roadmap's
own*, mirroring `factory/roadmap/workflow.py:1508` —
`RoadmapWorkflow._compute_drift`, reaching `compute_readiness` as `landed_for`
and merged with the existing `_landed` answer so a spec the run itself watched
still resolves. The guard then costs nothing: the spec is simply absent from the
dispatchable list at `factory/roadmap/workflow.py:864`, so `_dispatch` — and its
clone and its onboard — is never called. One consequence of merging is
deliberate and must not be "fixed" back: `compute_readiness` satisfies every
`depends_on_landed` edge through that same `observed(...)` seam, so a spec whose
dependency is built-but-unattested becomes dispatchable inside the roadmap where
today it waits. That is the ledger row's own first consequence ("a finished
spec's dependents stay blocked because readiness is computed from attestation"),
it is what `ergane status specs` has computed all along, and FR-009 requires it.
An implementer who notices the change and narrows the resolver to the entry's own
`spec_dir` has re-opened the defect.

**Trap 8 — AN `async` ACTIVITY MAY NOT SHELL GIT ON THE LOOP.** FR-012. This is
not hypothetical and the incident is written into the tree: the comment on
`factory/activities/roadmap_activities.py:512` — `_drift_from_git` records that
on 2026-08-26 this body ran directly on the worker's event loop, `landed_facts`
held it for 5m12s through a 300-second git timeout, and Temporal killed a node
that was working correctly with 138 insertions on disk — recurring every five
minutes until the schedule was paused. The new activity must be `async def` with
the git work behind `asyncio.to_thread`, exactly as
`factory/activities/roadmap_activities.py:496` — `drift_for_spec` does.

**Trap 9 — AN ACTIVITY NOT IN THE WORKER'S LIST DOES NOT EXIST.** FR-012.
`factory/worker.py:192` is the registration line for `drift_for_spec`; the new
activity needs one beside it. Omitted, the workflow raises at the first pass that
calls it and every scheduled tick fails — a failure that looks like a Temporal
problem and is a one-line omission. Add a scripted-seam test that does not need
the worker, *and* the registration line.

**Trap 10 — US3 ADDS A GUARD; IT DOES NOT REPLACE THE BACKSTOP.** FR-010. The
zero-node refusal at `factory/roadmap/workflow.py:1269` catches empty deltas
arising for other reasons — a spec whose stories are all satisfied by drift
resolution, a delta narrowed by hand. Removing it because US3 makes one of its
cases unreachable is how the other cases start dispatching an empty epic.

**Trap 11 — NOTHING IN `factory/` WRITES `state: landed` BACK, AND THE
TEMPTATION HAS A NAMED ADDRESS.** FR-006, US2-S2. Attestation is an operator act,
which is *why* the built-but-`ready` window is real and lasts days — and an
implementer holding a spec the code now knows is finished will reach for the
obvious close: write `state: landed` into that spec's frontmatter and drop the
third word as redundant. The address that invites it is
`factory/roadmap/workflow.py:1187` — `RoadmapWorkflow._apply_promotions`, which
already rewrites a spec's state for readiness — and that function's own docstring
is the answer: it rewrites the *in-memory* entry only, because "the file is the
authority of record". Reproduce the boundary before editing:
`grep -rn "state: landed" --include=*.py factory/` returns docstrings and
comparisons and not one write. A frontmatter write added here puts a write into
the one path that hard-resets the operator's checkout, and it makes FR-006's
third state unreachable — the spec would read `landed` before anyone attested
it.

**Trap 12 — CHECK THE EMPIRICAL CLAIM YOURSELF BEFORE TRUSTING THE FIX.**
US2-S1. Injecting a `landed_for` resolver that answers landed=True still yields
`dispatchable=True` today. Reproduce that first and assert its inverse
afterwards; it is the cheapest possible proof that US2 landed, and it takes one
call to `compute_readiness` with a lambda.

**Trap 13 — FR-004 IS A BYTE-IDENTITY CONTROL, NOT A SENTIMENT.** With no parked
spec the human block must be what it is today, `parked: 0` line included: an
operator's eye and several tests read that shape. The JSON is allowed to gain the
new field — it must be present and empty, not absent, so a consumer can tell
"none parked" from "this version does not report it".

**Trap 14 — THERE ARE TWO `compute_readiness` CALLS IN
`factory/roadmap/workflow.py`, AND AN EARLIER DRAFT OF THIS PLAN SAID ONE.**
FR-014, US3-S2. The pass calls it at `factory/roadmap/workflow.py:851`; the
`roadmap_status` query calls it again at `factory/roadmap/workflow.py:687`, with
its own `self._observed_resolver()`. An implementer who injects the landed read
only at the pass's call site ships a change whose own US3-S2 test fails: the
query keeps reporting `ready` and `dispatchable=True` for a spec the dispatch
loop has already excluded, so `ergane status specs` and `ergane roadmap status`
disagree about the same spec — precisely the failure this story exists to
prevent. The tree already contains the answer for the sibling fact: `self._drift`
is written once at `factory/roadmap/workflow.py:916`, read by the pass at
`factory/roadmap/workflow.py:854` and by the query at
`factory/roadmap/workflow.py:690`, and the comment at
`factory/roadmap/workflow.py:848` says the cache exists for exactly this reason.
Cache the landed read on the instance the same way and let
`factory/roadmap/workflow.py:1441` — `RoadmapWorkflow._observed_resolver` answer
from both maps, so one change serves both call sites and they cannot drift apart
later. Do **not** add an activity call inside the query: a Temporal query is
read-only and cannot execute activities.

There is a second read in that query the resolver does **not** reach, and it is
the one an operator looks at. `factory/roadmap/workflow.py:725` —
`RoadmapWorkflow.roadmap_status` reads `own = self._landed.get(entry.spec_dir)`
directly to fill `RoadmapSpecStatus.landed`, and the per-spec board prints it at
`factory/cli/roadmap.py:508` as `[ ] <spec>: <state> (landed=..., promoted=...)`.
Change only the resolver and that board prints the built spec's third word beside
`landed=False` — a line that calls a spec built and says its stories did not
land, on the surface this spec exists to make legible, and at the exact line the
`operator/...` ledger row cites as its ref. Feed that field from the same merged
answer, with `LandedKind.OBSERVED`, and the board reads `landed=True`.

**Trap 15 — THE SECOND PARKED COUNT IS IN A DIFFERENT FILE WITH A NEARLY
IDENTICAL NAME.** FR-013, US1-S5. The two modules are `factory/cli/roadmap.py`
(the operator verb: `_render_status`, the parked count at
`factory/cli/roadmap.py:501`) and `factory/roadmap/cli.py` (the offline render:
`_render_roadmap`, no parked count at all, no factory required). US1's edit
belongs in the first. An implementer who opens the second will find nothing that
looks like the trap description and may conclude the defect is stale. Note also
what US1 must **not** touch in the first file: `roadmap_status_command`
(`factory/cli/roadmap.py:420` — `roadmap_status_command`) already prints
`asdict(status)` for `--json`, so the findings are whole there today; adding a
second JSON shape beside it is how two payloads start disagreeing.

**Trap 16 — `ergane roadmap render` CANNOT SHOW THE THIRD WORD, AND MAKING IT
DO SO BREAKS ITS CONTRACT.** FR-006, and the scope line in spec.md.
`render_command` (`factory/roadmap/cli.py:46` — `render_command`) calls
`compute_readiness` at `factory/roadmap/cli.py:63` with `drifted_for` only and no
`landed_for`, because `factory/roadmap/cli.py:74` — `_cli_drift_resolver`
documents that the verb must work with no factory running and therefore cannot
read the target repo's landing history. An implementer who "makes the roadmap
render agree" by wiring `landed_facts` into it has put a git read of the target
repository into the one command that is specified to need none, and the offline
render stops being deterministic. Leave it printing `ready`; that is correct.

**Trap 17 — AN AMENDED SPEC LOOKS EXACTLY LIKE A BUILT ONE, AND THE RULE MUST
TELL THEM APART OR THE FLOOR STOPS REBUILDING AMENDMENTS.** FR-005, FR-015,
US2-S6. This is the trap that decides whether this spec is a fix or a regression.
`factory/cli/status.py:469` — `_observed_landing` is satisfied by commit
subjects (`factory/workgraph/landed.py:130` — `landed_facts` compares no
content), so a spec whose text the operator edited *after* it landed still
reports every story landed. The documented way to rebuild that spec is to flip
`state` back to `ready` — `factory/roadmap/models.py:586` — `compute_readiness`
says so in its own docstring — and `factory/workgraph/delta.py:9` then re-opens
exactly the stories whose fingerprint changed. An implementer who writes FR-005
as "ready + all stories landed → not dispatchable" ships a loop with no exit:
attesting renders it `landed`, drift renders it `amended`, flipping to `ready`
renders it `awaiting attestation`, and the roadmap never clones it again.
Reproduce before editing: compute readiness with `landed_for` answering landed
and `drifted_for` answering `True`, and assert the spec is still dispatchable.

**Trap 18 — AN UNSUPPLIED DRIFT ANSWER IS NOT "NOT DRIFTED".** FR-015, US2-S7.
`factory/roadmap/models.py:592` — `compute_readiness` defaults `drifted_for` to a
lambda returning `False`, which is the same value a real resolver returns for a
clean spec. Read that default as "not drifted" and every caller that supplies no
resolver silently acquires the new behaviour — including
`factory/roadmap/cli.py:46` — `render_command`, which supplies no `landed_for`
either and is specified to work with no factory running (trap 16). The built
determination must require an answer that was actually supplied; test it by
calling `compute_readiness` with `landed_for` only and asserting nothing changed.

**Trap 19 — BOUND BOTH ROADMAP READS BY DECLARED STATE, OR THE COST STORY ADDS
COST.** FR-009, US3-S7. `factory/roadmap/workflow.py:1508` —
`RoadmapWorkflow._compute_drift` bounds itself with `if entry.state is
SpecState.LANDED`, and it already awaits one activity per landed spec — 102 of
the 141 in this corpus — on every tick. "Once per candidate spec" is not a bound:
unbounded, the new landed read adds 141 more sequential git scans every five
minutes, on the story whose whole purpose is to stop paying a per-tick git cost.
The mirror of `_compute_drift`'s `LANDED` is `READY`, and the drift half is
narrower still — only the `ready` specs the landed read reported landed need a
drift answer at all, which is one spec on this floor today. Note that the
existing `factory/roadmap/workflow.py:1455` —
`RoadmapWorkflow._drift_resolver` refuses any non-`landed` spec before it reaches
the activity, so widening `_compute_drift`'s bound alone changes nothing; both
gates move together or neither does. And *widening* is the whole word:
`_compute_drift` must go on covering every `landed` entry exactly as it does
today. Narrow it to `ready` — which is one way to read a bound stated over "both
reads" — and the existing render at `factory/roadmap/models.py:544` —
`SpecReadiness.rendered_state` quietly stops firing for the 102 `landed` specs in
this corpus of 141, with no other test in this trio to notice. US3-S9 is that
control.

**Trap 20 — `ergane status specs` MUST NOT FETCH TO ANSWER A QUESTION.** FR-016.
`factory/workgraph/landed.py:130` — `landed_facts` defaults `fetch=True`, and
`factory/activities/roadmap_activities.py:512` — `_drift_from_git` takes that
default because it decides what an epic builds. A reporting command may not: the
rest of `factory/cli/status.py` already passes `fetch=False` and says on its own
output that the answer was read without fetching. A drift resolver copied from
the activity without that argument puts a network round trip on `ergane status
specs`, which is the one command an operator runs while the network is the thing
that is broken.

**Trap 21 — INSIDE THE ROADMAP THE DRIFT ANSWER IS ALWAYS SUPPLIED, SO FR-015
CANNOT SAVE THE AMENDED SPEC THERE — AND THE ORDER OF THE TWO AWAITS DECIDES IT
TOO.** FR-017, FR-009, US3-S8. This is US3's version of trap 17, and it is the
trap that decides whether US3 is a fix or a regression.
`factory/roadmap/workflow.py:854` and `factory/roadmap/workflow.py:690` both pass
`drifted_for=lambda spec_dir: self._drift.get(spec_dir, False)`, so inside the
workflow an answer is *always* supplied and the `.get(..., False)` default makes
"nobody computed one" and "not drifted" the same value — the exact collapse
FR-015 forbids one layer down, reproduced where FR-015 cannot reach. Today
`self._drift` is populated only for `SpecState.LANDED` at
`factory/roadmap/workflow.py:1508`, and `factory/roadmap/workflow.py:1455` —
`RoadmapWorkflow._drift_resolver` short-circuits every non-`landed` spec to
`False` a second time, so a `ready` spec always reads back not-drifted. An
implementer who adds `_compute_landed` and stops there ships a story that passes
every other US3 scenario — `.get` answers `False` whether a drift read ran or
not — and silently stops the roadmap rebuilding any spec the operator amended and
flipped back to `ready`. Both drift gates must move with the landed read, and
US3-S8 is the *positive* bound that proves the read ran for that spec, because
every other bound in this story is an upper one that zero drift reads satisfy.

The second half is an ordering rather than a predicate, and it fails the same
way. Await `_compute_landed` **before**
`self._drift = await self._compute_drift(request)` at
`factory/roadmap/workflow.py:916`: the widened drift gate asks which `ready`
specs the landed read reported landed, so in the reverse order that gate reads an
empty landed map, no `ready` spec gets a drift entry,
`factory/roadmap/workflow.py:854` answers `False`, and the amended spec is
dropped from the dispatchable list at `factory/roadmap/workflow.py:864` — the
same regression, arriving through order instead of through the rule. Reproduce
it: script the landed read landed and the drift read drifted, run one pass, and
assert the spec is still dispatched.

**Trap 22 — A NEW PRODUCER OF PARKS LANDED AFTER THIS PLAN WAS WRITTEN, AND IT
ROUTES THROUGH THE SURFACE THIS SPEC FIXES.** Spec 156 US2 landed as `1c96876`
on 2026-09-08, adding `factory/roadmap/workflow.py:209` — `_skew_park_detail`
and a `self._park(spec_dir, "dispatch", refusal)` call in
`factory/roadmap/workflow.py:1397` — `RoadmapWorkflow._dispatch`. Its own comment
says the refusal "renders through the same park-reason surface every other park
uses" — which is, today, the bare integer this spec exists to replace.

Two consequences, and neither is optional. **First, the enumeration of park
reasons in this plan is not closed.** Count the `_park(` call sites in
`factory/roadmap/workflow.py` when you start, rather than trusting a list
written before 156 landed; a renderer that names four reasons and meets five
prints the same silence for the fifth. **Second, the headline scenario now has a
cheap reproduction that costs no epic**: restart the worker onto a revision the
tree does not match, let one roadmap tick fire, and every ready spec parks with
a skew reason `ergane status specs` will not print. That is the demonstration to
run before you believe the fix, and it is faster than the onboarding refusal the
original evidence came from.

Note also that this file moved by +78 to +135 lines on 2026-09-08. Every anchor
in this document was re-resolved against `1c96876` and none is older. If 156's
successors land before this spec dispatches, re-run `ergane spec validate` — and
do not read a green result as proof, because the symbol tier does not see an
anchor whose path and symbol are split across two lines.


## Sizing

US1 touches `factory/cli/status.py` — the `RoadmapDisposition` record
(`factory/cli/status.py:164`), its construction (`factory/cli/status.py:554`) and
the renderer (`factory/cli/status.py:753` — `_roadmap_lines`) — and one block of
`factory/cli/roadmap.py`: the parked line at `factory/cli/roadmap.py:501` inside
`factory/cli/roadmap.py:484` — `_render_status`. Two files, four small edits, no
new record on the roadmap side. Its tests are new, in a file of their own.

US2 touches `factory/roadmap/models.py` — one predicate at
`factory/roadmap/models.py:607`, one constant beside
`factory/roadmap/models.py:91`, one field on `factory/roadmap/models.py:516` —
`SpecReadiness` and one branch in `factory/roadmap/models.py:544` —
`SpecReadiness.rendered_state` — and two regions of `factory/cli/status.py`: one
branch of `factory/cli/status.py:810` — `_queue_lines`, and the drift resolver
beside `factory/cli/status.py:378` — `_readiness_basis` with its injection at
`factory/cli/status.py:292`. That resolver is the one genuinely new function in
the story, about twenty lines over two public helpers
(`factory/workgraph/landed.py:407` — `fingerprint` and
`factory/workgraph/delta.py:48` — `fingerprint_for`). Still small, and the tests
are the bulk.

US3 touches `factory/roadmap/workflow.py` (a `_compute_landed` beside
`factory/roadmap/workflow.py:1508` — `RoadmapWorkflow._compute_drift`, bounded
to `SpecState.READY` exactly as that one is bounded to `SpecState.LANDED` at
`factory/roadmap/workflow.py:1508`; the two drift gates at
`factory/roadmap/workflow.py:1508` and `factory/roadmap/workflow.py:1455` widened
together — widened, not moved: every `landed` entry keeps its drift read — to
cover the `ready` specs the landed read reported landed, and awaited in that
order (trap 21); the
injection at `factory/roadmap/workflow.py:851`; the cached read consumed by the
query at `factory/roadmap/workflow.py:687`; the own-landed field at
`factory/roadmap/workflow.py:725`; and the seam at
`factory/roadmap/workflow.py:1441` — `RoadmapWorkflow._observed_resolver` that
lets one change serve both call sites),
`factory/activities/roadmap_activities.py` (a new input record, activity and
blocking half, mirroring `factory/activities/roadmap_activities.py:482` onwards)
and one line at `factory/worker.py:192`. It opens neither sibling's file: the
board line at `factory/cli/roadmap.py:508` follows from the query's answer and
needs no edit.

US1 and US2 share `factory/cli/status.py` in different functions —
`_roadmap_lines` against `_queue_lines` — which is why the Work Graph declares
`concurrent_with` rather than leaving an edge to be inferred. `factory/cli/roadmap.py`
is US1's alone; neither sibling opens it. US3 shares no production file with
either.

Every story's pasted evidence is a handful of rendered lines, not a log: US3's
two-pass evidence must be the dispatch decision lines and the activity list for
those passes, never a whole workflow history, or the story's diff approaches the
64 KiB refusal in `factory/verify/diffbounds.py` (D-050) on evidence alone.

## Verification the operator will run, independent of the gate

Per constitution VIII and D-037 the judge sees the diff and the criteria only, so
runtime evidence must be committed as pasted output. Beyond that, this repository
is the fixture — it holds more than a hundred and forty specs and a real backlog,
and one named live instance of the defect:

1. Before any code: confirm the instance is still live. At `602a92c`,
   `specs/057-a-new-repo-gets-a-constitution/spec.md:2` reads `state: ready` and
   `ergane spec landed specs/057-a-new-repo-gets-a-constitution --default-branch ergane-buildout`
   reports every story landed. `ergane status specs` lists 057 as
   `ready  dispatchable`. That is the finding, reproduced on this floor by two
   commands rather than a search, and it is what makes step 4 falsifiable. If an
   operator has attested 057 by the time this runs, `grep -l '^state: ready' specs/*/spec.md`
   names the current instances; the check is unchanged.
   Then, before this spec is flipped `ready`: capture 057's queue lines — step 4
   needs the before-and-after — and **attest 057**, writing `state: landed` into
   its frontmatter, and signal the running roadmap to rescan
   (`factory/roadmap/workflow.py:677` — `RoadmapWorkflow.rescan`). 057 is the
   only `state: ready` spec in the corpus and sorts before 131, and the open
   critical finding this spec deliberately does not fix
   (`roadmap/a-landed-but-unattested-spec-parks-the-line-and-the-floor-idles-until-an-operator-attests`)
   records the roadmap idling through three consecutive ticks after a park
   instead of proceeding to the next dispatchable spec. Leaving 057 ready-and-
   built is preserving the condition that could stop this epic ever being
   dispatched.
2. Run `ergane status specs` today with the roadmap running and note the bare
   `parked` count. Land US1 and re-run: every parked spec is named, with its
   check and its detail.
3. Confirm the `--json` payload of `ergane status specs` carries the same three
   fields per parked spec, and that with nothing parked the human block is
   unchanged. Then run `ergane roadmap status specs` and confirm its human
   document names them too, while its `--json` is what it always was.
4. Land US2 and re-run step 1's spec: 057 renders with the third word and its
   queue line reads `awaiting attestation` where it read `dispatchable`.
4b. The control that proves the rule did not swallow the rebuild path, run on a
   scratch copy of the corpus so nothing is dispatched: edit one acceptance
   scenario of a landed spec, flip its `state` to `ready`, and run
   `ergane status specs`. It must read `ready  dispatchable`, not the third word
   — `ergane spec landed <that spec> --default-branch ergane-buildout` still
   reports every story landed, and only the fingerprint comparison tells the two
   cases apart. Run the same edit against 057 before US2 lands to see that the
   two specs are indistinguishable today.
5. Land US3, then watch two roadmap ticks in Temporal's Web UI on port 8233: 057
   draws no `clone_target` and no `onboard_target` activity, while a spec with
   real work still dispatches — and `ergane roadmap status specs`, which asks the
   query rather than the pass, reports 057 with the same third state and no `[*]`
   marker. This is the step that distinguishes US3 from a green no-op; trap 7 is
   why it must be watched rather than assumed, and trap 14 is why the query must
   be read as well as the activity list.
