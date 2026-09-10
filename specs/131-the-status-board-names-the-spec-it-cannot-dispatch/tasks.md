# Tasks: the status board names the spec it cannot dispatch

Read `plan.md` before starting. Four traps decide whether this spec is worth
building at all, and one decides whether it is a fix or a regression. **Trap 1:
the expensive half is already fixed** — the source finding says a landed spec
would be rebuilt; it would not, because the zero-node delta refusal parks it
before any child epic starts. An implementer who goes hunting for a runaway
rebuild will find nothing, conclude the finding is invalid, and close a real
defect. What survives is the wasted clone-and-onboard cycle and the legibility
gap. **Trap 17: a spec the operator amended looks exactly like a spec that is
finished** — "landed" is read from commit subjects and compares no content, so
the rule needs drift as a third input or the floor stops rebuilding amendments.
**Trap 7: the roadmap's landed resolver is empty on a scheduled run**, so US2's
predicate alone changes nothing inside the roadmap and US3's guard must be fed by
a landed read of the roadmap's own. **Trap 14: there are two `compute_readiness`
calls in `factory/roadmap/workflow.py`** — the pass at
`factory/roadmap/workflow.py:851` and the `roadmap_status` query at
`factory/roadmap/workflow.py:687` — and a change that reaches only the first
makes the two operator surfaces disagree, which is the thing US3 exists to
prevent. **Trap 21 is trap 17 one layer up**: inside the roadmap a drift answer
is *always* supplied, so FR-015's unsupplied-answer guard cannot fire there and
`self._drift.get(spec_dir, False)` makes "nobody computed one" and "not drifted"
the same value. A US3 that widens the landed read and not the drift read passes
T023 through T029 and stops the floor rebuilding amendments; T036 is the only
task that fails when it does.

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the judge
sees; runtime evidence is committed as pasted output, and kept to the lines that
carry the fact.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — Parked names the spec and the reason

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001, FR-003, trap 2) In
      `tests/test_131_us1_parked_names_the_spec.py`, drive the human rendering
      with a roadmap document carrying two parked entries and assert each parked
      spec directory appears with the check that refused it and the detail
      verbatim, not only a count.

- [ ] T002 [P] [US1] (spec US1-S2, FR-002) Assert the `ergane status specs`
      `--json` payload carries, per parked spec, the directory, the check and the
      detail as separate fields rather than an integer.

- [ ] T003 [P] [US1] (spec US1-S3, FR-003, trap 3) Assert an entry parked with
      check `onboarding` and one parked with check `derive` and the empty-delta
      detail are told apart on both surfaces by the fields the roadmap recorded.
      Do not invent a park class: the six checks the roadmap actually writes are
      `clone`, `derive`, `preflight:<check>`, `onboarding`, `manifest` and
      `collision`, and an unsatisfied dependency edge is a blocker, never a park.
      Count them from the eight `self._park(...)` call sites, not from the
      record: the `ParkedFinding` docstring is itself stale and lists five,
      omitting `manifest` (plan trap 3 anchors both).

- [ ] T004 [P] [US1] (spec US1-S4, FR-004, trap 13) **The control.** With a
      document carrying no parked entries, assert the human roadmap block is
      byte-identical to today's — the `parked: 0` line included — and that the
      added JSON field is present and empty rather than absent.

- [ ] T005 [P] [US1] (spec US1-S5, FR-013, trap 15) In
      `tests/test_131_us1_roadmap_status_names_the_spec.py`, call
      `factory/cli/roadmap.py:484` — `_render_status` with a `RoadmapStatus`
      carrying two `ParkedFinding`s of different checks and assert each spec
      directory, check and detail appears under the `parked:` line. Assert also
      that the `--json` half is unchanged: `factory/cli/roadmap.py:420` —
      `roadmap_status_command` already prints `asdict(status)` and the findings
      are whole in it today, so a second JSON shape is a regression, not a
      feature.

### Implementation for this story

- [ ] T006 [US1] (FR-001, FR-002, FR-003, trap 2) In `factory/cli/status.py`,
      stop discarding the listing: the roadmap document's `parked` entries
      already carry `spec_dir`, `check` and `detail`, and `factory/cli/status.py:554`
      collapses them with `len()`. Carry the three fields onto the
      `RoadmapDisposition` record (`factory/cli/status.py:164` —
      `RoadmapDisposition`), which `factory/cli/status.py:272` — `status_command`
      serialises whole at `factory/cli/status.py:276`, so that verb's `--json`
      needs no second renderer. **Do not build a durable park store, a sidecar
      file or a history scan**: the listing has exactly the lifetime the count has
      today, and giving it another is days of work and a write on a read path.

- [ ] T007 [US1] (FR-001, FR-004, trap 13) In `factory/cli/status.py:753` —
      `_roadmap_lines`, print the named entries under the existing
      `parked: <n>` line at `factory/cli/status.py:780` rather than in place of
      it, so the zero case renders byte-for-byte as it does today.

- [ ] T008 [US1] (FR-013, trap 15) In `factory/cli/roadmap.py:484` —
      `_render_status`, print the same three fields under the second count at
      `factory/cli/roadmap.py:501`, which today collapses the identical
      `list[ParkedFinding]` with `len(status.parked)`. This is the verb the
      incident was read on, and `factory/cli/roadmap.py:403` —
      `roadmap_unpark_command` already tells the operator at
      `factory/cli/roadmap.py:406` that this document "names the parked spec and
      quotes the finding". Touch nothing else in the file — in particular leave
      `factory/cli/roadmap.py:420` — `roadmap_status_command`'s `--json` branch
      alone — and do not confuse this module with `factory/roadmap/cli.py`, the
      offline render, which has no parked count at all.

### Verification for this story

- [ ] T009 [US1] Paste, as committed evidence, the human `ergane status specs`
      roadmap block, the corresponding `--json` fragment, and the
      `ergane roadmap status specs` parked block, for a floor with at least two
      parked specs of different checks, showing each name and each reason. Paste
      the blocks, not the whole documents.

## Phase 2: User Story 2 — A built spec is rendered as built, not as ready

### Tests for this story (write FIRST, must fail)

- [ ] T010 [P] [US2] (spec US2-S1, FR-005, trap 12) In
      `tests/test_131_us2_built_is_not_dispatchable.py`, compute readiness for a
      `ready` spec with a `landed_for` resolver answering landed=True and a
      `drifted_for` resolver answering False, and assert it is **not**
      dispatchable. Reproduce the inverse first — today that same injection still
      yields `dispatchable=True` — because it is the cheapest possible proof this
      story landed.

- [ ] T011 [P] [US2] (spec US2-S2, FR-006, trap 4) Assert the spec's rendered
      state is a third word, distinct from **both** `ready` and `landed`.
      Rendering it `landed` asserts an attestation nobody made, and attestation
      is the operator act the state exists to prompt.

- [ ] T012 [P] [US2] (spec US2-S3, FR-011, trap 6) Assert the human queue line
      for that spec carries the third state and the literal string
      `awaiting attestation`, and does **not** contain the word `dispatchable`.
      Assert the whole line, not the absence alone: today the line is built from
      the blockers list, so a spec with no blockers prints `dispatchable`
      whatever the computed flag says — this test fails against a
      `factory/roadmap/models.py`-only change, which is the point of it — and a
      change that merely deletes the word leaves the operator a line that says
      nothing.

- [ ] T013 [P] [US2] (spec US2-S4, FR-007) **The control.** Given a `ready` spec
      some of whose stories have not landed, assert it is dispatchable and its
      rendered state is still `ready`, exactly as today.

### Implementation for this story

- [ ] T018 [US2] (FR-005, FR-007, FR-008, FR-015, traps 17 and 18) In
      `factory/roadmap/models.py:607` — `compute_readiness`, consult the injected
      `observed(...)` resolver for the entry's **own** `spec_dir` — today it is
      called only inside the `depends_on` loop, for an entry's dependencies — and
      make a `ready` spec not dispatchable when every story is observed landed
      **and** a drift resolver that was actually supplied answers False for it.
      Both halves are load-bearing: landing is read from commit subjects and is
      blind to content, and an unsupplied answer is not a negative one. Add no
      git read; both resolvers are injected on purpose and
      `factory/roadmap/models.py:587` — `compute_readiness` says why in its own
      docstring.

- [ ] T019 [US2] (FR-006, trap 4) Carry the fact as a field on
      `factory/roadmap/models.py:516` — `SpecReadiness`, exactly as `drifted` is
      carried, and add the second branch and its constant to
      `factory/roadmap/models.py:544` — `SpecReadiness.rendered_state`, beside
      the existing `landed` → `amended` rewrite and the constant at
      `factory/roadmap/models.py:91`. Leave `drifted` itself as it is — it means
      "declared `landed` and the fingerprints moved", and `rendered_state` must
      go on printing `amended` only for that case.
      `factory/cli/status.py:364` — `_entries` already copies `rendered_state`
      and `dispatchable` into every queue entry, so the `ergane status specs`
      queue follows with no edit; the offline `factory/roadmap/cli.py:92` —
      `_render_roadmap` does **not** and must not be made to (trap 16).

- [ ] T021 [US2] (FR-011, trap 6) In `factory/cli/status.py:810` —
      `_queue_lines`, decide the word `dispatchable` from the entry's computed
      flag rather than from the absence of blockers, and print
      `awaiting attestation` where the flag is false and no blocker explains it.

### Verification for this story

- [ ] T022 [US2] Paste, as committed evidence, the queue lines for
      `057-a-new-repo-gets-a-constitution` — the one `state: ready` spec in this
      corpus whose four stories are all landed on `ergane-buildout` — before and
      after the change: `ready  dispatchable`, then the third word followed by
      `awaiting attestation`. Paste beside them the control: the same two lines
      for a spec whose stories are all landed but whose text was edited after
      they landed, which must read `ready  dispatchable` both times.

## Phase 3: User Story 4 — Readiness reaches its facts only through the resolvers it is given

Split out of US2 on 2026-09-08 for size. Merges after US2, before US3.

### Tests for this story (write FIRST, must fail)

- [ ] T014 [P] [US4] (spec US4-S1, FR-008, trap 5) **The control.** Assert
      `compute_readiness` reaches the landed fact and the drift fact only through
      the injected resolvers: supply both from lambdas, pass no repository, and
      assert the answer is correct — a git read added inside
      `factory/roadmap/models.py` would make this case fail or hang.

- [ ] T015 [P] [US4] (spec US4-S2, FR-015, trap 17) **The control that decides
      whether this story is a fix or a regression.** Given a `ready` spec whose
      every story is observed landed and whose `drifted_for` answers True, assert
      it is **dispatchable** and renders `ready`, exactly as today. That is an
      amended spec the operator flipped back to `ready` to have rebuilt: its
      stories all have landing commits, and only the fingerprint answer separates
      it from a finished one. Write this test before T010's implementation, not
      after; the whole rule is wrong without it.

- [ ] T016 [P] [US4] (spec US4-S3, FR-015, trap 18) **The control.** Given that
      same landed spec and **no** `drifted_for` argument at all, assert it is
      dispatchable and renders `ready`. `factory/roadmap/models.py:592` —
      `compute_readiness` defaults the resolver to a lambda returning False, so a
      built determination that reads the default as "not drifted" silently
      changes every caller that supplies none.

- [ ] T017 [P] [US4] (spec US4-S4, FR-016, traps 17 and 20) In
      `tests/test_131_us2_status_supplies_drift.py`, assert the drift resolver
      `ergane status specs` supplies compares each story's fingerprint pinned at
      its landing commit against the fingerprint of the spec text on disk, and
      answers True when they differ. Assert it asks git **without fetching** —
      `factory/workgraph/landed.py:130` — `landed_facts` defaults `fetch=True`
      and a reporting command may not take that default — and that it is
      consulted only for a `ready` spec the landed read already reported landed,
      so the corpus does not pay a fingerprint comparison per spec.

### Implementation for this story

- [ ] T020 [US4] (FR-016, traps 17 and 20) Add the drift resolver
      `ergane status specs` supplies beside `factory/cli/status.py:378` —
      `_readiness_basis`, which already resolves the repository and the landing
      branch, and inject it at the `compute_readiness` call on
      `factory/cli/status.py:292`. Build it from two public helpers rather than a
      third fingerprint implementation: `factory/workgraph/landed.py:407` —
      `fingerprint` pins a story at its landing commit and
      `factory/workgraph/delta.py:48` — `fingerprint_for` computes the same
      digest from the spec text on disk; any story whose digests differ means
      drifted. Pass `fetch=False`, and consult it lazily — only for a `ready`
      spec the landed read already reported landed. Touch no other function in
      that file: US1 is editing the roadmap-disposition half of it concurrently.

## Phase 4: User Story 3 — The roadmap stops paying for a spec it will never dispatch

### Tests for this story (write FIRST, must fail)

- [ ] T023 [P] [US3] (spec US3-S1, FR-009, traps 1 and 7) In
      `tests/test_131_us3_roadmap_skips_a_built_spec.py`, run one scheduling pass
      with the roadmap's landed read scripted to report a `ready` spec as landed
      and its drift read scripted to report it unchanged, and assert the spec is
      absent from the dispatchable list and that neither `clone_target` nor
      `onboard_target` was executed on its account. This is the real cost — up to
      288 cycles a day per such spec at a five-minute schedule — not a rebuild,
      which is already refused.

- [ ] T024 [P] [US3] (spec US3-S2, FR-014, trap 14) After that same pass, query
      `roadmap_status` on the same workflow instance and assert it reports for
      that spec the `rendered_state` and the `dispatchable` flag the pass
      computed, **and** that the spec's own `landed` field is True with kind
      `OBSERVED`. This test is the one that fails when the landed read is
      injected only at `factory/roadmap/workflow.py:851`: the query calls
      `compute_readiness` a second time at `factory/roadmap/workflow.py:687` with
      its own resolver, and reads the spec's own landed state at
      `factory/roadmap/workflow.py:725` from a map the resolver does not touch,
      so an incomplete change leaves the per-spec board calling a spec built and
      saying its stories did not land.

- [ ] T025 [P] [US3] (spec US3-S3, FR-009) **The control.** Given a spec with
      genuine outstanding work, assert it is cloned, onboarded and dispatched
      exactly as today.

- [ ] T026 [P] [US3] (spec US3-S4, FR-010, trap 10) **The control.** Given a spec
      whose delta is empty for some other reason, assert the existing zero-node
      refusal at `factory/roadmap/workflow.py:1269` still parks it with the same
      detail. This story adds an earlier guard; removing the backstop because one
      of its cases became unreachable is how the other cases start dispatching.

- [ ] T028 [P] [US3] (spec US3-S5, FR-009, trap 7) **The control on the widening.**
      Given a `ready` spec whose `depends_on_landed` names a spec the roadmap's
      landed read reports as built but whose frontmatter is not `landed`, assert
      the dependent is dispatchable rather than blocked on that edge. This is a
      dispatch-behaviour change and it is intended: it is the ledger row's own
      first consequence, and it makes the roadmap agree with what
      `ergane status specs` has computed all along. Assert it so a later reader
      cannot mistake it for an accident and narrow the resolver back.

### Implementation for this story

- [ ] T030 [US3] (FR-012, traps 8, 9 and 23) Before T031 consumes the landed
      read, create it in `factory/activities/roadmap_activities.py` as an
      `async def` activity mirroring
      `factory/activities/roadmap_activities.py:496` — `drift_for_spec`: an input
      record beside `factory/activities/roadmap_activities.py:482` — `DriftInput`,
      a module-level scripted seam beside
      `factory/activities/roadmap_activities.py:491` so scheduler tests need no
      real clone, and the blocking git work behind `asyncio.to_thread` as
      `factory/activities/roadmap_activities.py:512` — `_drift_from_git` does.
      Register it with `factory/worker.py` — `build_worker`. The tests above
      exercise the read through a real scheduling pass before implementation;
      US5 later adds its dedicated threading and read-bound regression controls.

- [ ] T031 [US3] (FR-009, FR-014, traps 7, 14 and 19) In
      `factory/roadmap/workflow.py`, add a `_compute_landed` beside
      `factory/roadmap/workflow.py:1508` — `RoadmapWorkflow._compute_drift` that
      awaits that activity **only for entries whose state is `SpecState.READY`**,
      exactly as `_compute_drift` restricts itself to `SpecState.LANDED` at
      `factory/roadmap/workflow.py:1508` — 102 of this corpus's 141 specs are
      landed, so an unbounded read adds a git scan per spec per tick. Widen the
      drift read to cover the `ready` specs that landed read reported landed, at
      both gates that stand in the way: the bound at
      `factory/roadmap/workflow.py:1508` and the short-circuit at
      `factory/roadmap/workflow.py:1455` — `RoadmapWorkflow._drift_resolver`,
      which returns False for any non-`landed` spec before the activity is
      reached. Widen those gates rather than moving them — every `landed` entry
      keeps its drift read, or the existing `amended` render stops firing for the
      102 landed specs here (T037) — and **await `_compute_landed` before
      `self._drift = await self._compute_drift(request)` at
      `factory/roadmap/workflow.py:916`**: the widened gate asks which `ready`
      specs the landed read reported landed, so the reverse order leaves every
      `ready` spec with no drift entry, `factory/roadmap/workflow.py:854` answers
      False, and that reads as "supplied, and not drifted" — dropping a genuinely
      amended spec from the dispatchable list, trap 21's regression arriving
      through ordering rather than through the predicate. Cache the landed answer
      on the instance exactly as `self._drift`
      is cached at `factory/roadmap/workflow.py:916` for this same reason (the
      comment at `factory/roadmap/workflow.py:848` says so), and make
      `factory/roadmap/workflow.py:1441` — `RoadmapWorkflow._observed_resolver`
      answer from that cache as well as from `self._landed` — declared at
      `factory/roadmap/workflow.py:624`, and the stronger answer where a spec has
      one, since it is what this run actually watched — so that **both**
      `compute_readiness` call sites follow from one change: the pass at
      `factory/roadmap/workflow.py:851` and the `roadmap_status` query at
      `factory/roadmap/workflow.py:687`. Feed the query's own-landed read at
      `factory/roadmap/workflow.py:725` — `RoadmapWorkflow.roadmap_status` from
      that same merged answer, with kind `OBSERVED`: it reads `self._landed`
      alone today, so leaving it makes the per-spec board print a spec's built
      state beside `landed=False`. The built spec then never reaches the
      dispatchable list at `factory/roadmap/workflow.py:864`, so
      `factory/roadmap/workflow.py:1247` — `RoadmapWorkflow._dispatch` is never
      called for it and neither is its clone. Do not call the activity from
      inside the query: a Temporal query is read-only and cannot execute
      activities.

- [ ] T032 [US3] (FR-010, trap 10) Leave `factory/roadmap/workflow.py:1269`
      exactly as it stands. The guard is at selection; the refusal is the
      backstop for every other empty-delta cause.

### Verification for this story

- [ ] T033 [US3] Paste, as committed evidence, the dispatch decision and the
      executed-activity names for two consecutive roadmap passes, plus the
      `roadmap_status` answer for the same spec: no clone and no onboard for the
      built-but-unattested spec, a clone and an onboard for a spec with real
      work, and a query answer that agrees with the pass — including its own
      `landed` field. Paste those lines only — a whole workflow history spends
      the story's diff limit on evidence.

## Phase 5: User Story 5 — The drift read is bounded, and paid for once

Split out of US3 on 2026-09-08 for size. Merges last.

The activity itself must already exist in the merged US3 base (T030); this
slice proves its threading and read bounds rather than creating a prerequisite
after its consumer. Existing correct behavior is a passing control, not a reason
to duplicate production code or fabricate a failing baseline (plan trap 23).

### Tests for this story (write FIRST; prove sensitivity with negative controls)

- [ ] T027 [P] [US5] (spec US5-S1, FR-012, traps 8 and 9) Assert the new activity
      performs its git work off the event loop — the same split
      `factory/activities/roadmap_activities.py:512` — `_drift_from_git` makes —
      and that it is present in the worker's registered activity list at
      `factory/worker.py:192`.

- [ ] T029 [P] [US5] (spec US5-S2, FR-009, trap 19) **The cost control.** Given a
      corpus with specs in every declared state, assert the landed read is
      executed only for the entries whose declared state is `ready` — count the
      activity calls — and that the drift read is executed only for those of them
      the landed read reported landed. Unbounded, this story adds one git scan
      per corpus entry every five minutes to the story whose purpose is removing
      a per-tick cost. Both assertions here are *upper* bounds, which zero reads
      satisfy; T036 supplies the lower bound that the drift read actually ran.

- [ ] T036 [P] [US5] (spec US5-S3, FR-017, trap 21) **The control that decides
      whether this story is a fix or a regression.** Run one scheduling pass with
      the roadmap's landed read scripted to report a `ready` spec as landed and
      its drift read scripted to report a changed fingerprint, and assert the
      spec **is** in the dispatchable list, that it is cloned, onboarded and
      dispatched exactly as today, and — the part no other scenario here can
      state — that the drift read was **executed** for that spec. Inside the
      roadmap `drifted_for` is always supplied
      (`factory/roadmap/workflow.py:854` and `factory/roadmap/workflow.py:690`),
      so `self._drift.get(spec_dir, False)` answers False whether the read ran or
      not: without this positive bound, a US3 that widens the landed read alone
      passes T023 through T029 and stops the floor rebuilding an amended spec.

- [ ] T037 [P] [US5] (spec US5-S4, FR-009, trap 19) **The control on the bound.**
      Given a spec whose frontmatter reads `landed` and one of whose stories'
      fingerprints has changed, assert the pass and the `roadmap_status` query
      both still report it drifted and rendering `amended`, exactly as today. The
      drift read is widened, never narrowed: the bound at
      `factory/roadmap/workflow.py:1508` must go on covering every `landed`
      entry, and 102 of this corpus's 141 specs are `landed`.

### Verification for this story

- [ ] T038 [US5] Run the dedicated controls against the merged US3 behavior.
      Prove the new assertions detect an on-loop git read, a missing activity
      registration, an unbounded landed read, and a suppressed required drift
      read using isolated test-scoped fault injection. Commit compact actual
      results; restore every injected fault before the gate. Change production
      code only for a demonstrated remaining defect, never to make a passing
      baseline appear red.


## Verification

- [ ] T034 The full gate command passes green.
- [ ] T035 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end against **this repository**, which holds more
      than a hundred and forty specs and a real backlog. Step 1 — confirming that
      `057-a-new-repo-gets-a-constitution` still reads `state: ready` with every
      story landed, and that `ergane status specs` still calls it dispatchable —
      is worth doing before writing any code, because it is the finding
      reproduced on this floor by two commands and it is what makes step 4
      falsifiable. Step 4b is the one that proves the rule did not swallow the
      rebuild of an amended spec.
