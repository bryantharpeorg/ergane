---
state: draft
fixes:
  - status/parked-is-reported-as-a-bare-count-so-the-operator-cannot-tell-which-spec-is-parked
  - operator/a-completed-epic-goes-unattested-in-silence-while-status-keeps-calling-it-dispatchable
# DRAFTED 2026-09-03 by the operator session, against ergane-buildout at 238b494.
# Every `file:line` in spec.md and plan.md was read from that commit and verified
# to resolve to the symbol named, not recalled.
#
# WHERE THIS CAME FROM. N55 and P-7 of the `ergane-web` consolidated hand-over.
# N55: `ergane status specs` ends in `parked: 1` and `--json` carries the same
# bare integer; nothing anywhere names which spec it is. P-7 is N55 with the
# evidence it was missing — all three stories of one epic landed, its frontmatter
# still said `state: ready`, and the spec sat as the next thing the roadmap would
# pick up.
#
# WHAT THE BARE COUNT COST, MEASURED BY THE CONSUMER. It is the finding that
# turned an 11h40m outage into a diagnosis by elimination: every spec in the
# repository was parked behind one onboarding refusal, and the operator's only
# signal was `parked: 3` with no name in it. Both times the parked spec was
# identified by cross-referencing the `ready` list against `spec landed` for each
# entry — "that works with fourteen specs and does not with fifty". This
# repository has 117.
#
# A CORRECTION TO THE SOURCE DOCUMENT, made before drafting rather than
# discovered during. P-7 says the following tick "would have rebuilt three landed
# stories". IT WOULD NOT. `factory/roadmap/workflow.py:1269` is a zero-node delta
# refusal that sits before the single child-epic start, and it fires exactly here:
# a fully-landed spec derives an empty delta and parks. No child epic starts and
# no agent tokens are spent. This spec is scoped to what actually survives — a
# clone-and-onboard cycle paid on every tick for a spec that can never dispatch,
# roughly 288 times a day per such spec at the five-minute schedule, and a
# dispatchable queue that lists work nobody will do.
#
# NOT IN SCOPE. This spec does not write frontmatter — that is the `spec ready`
# authoring seam and it is a separate spec. It does not change the roadmap's park
# mechanism. And it does not make `compute_readiness` do git reads:
# `factory/roadmap/models.py:585` documents both resolvers as injected precisely
# so git stays out of workflow code (constitution IV), and that stays true.
#
# REFINED 2026-09-04 by the refinement workflow (refinement-2026-09-04); every
# anchor in spec.md, plan.md and tasks.md re-read from ergane-buildout at
# 602a92c. All nine citations the draft carried still resolve — 057's four
# landings touched `factory/cli/init.py`, `factory/constitution.py`,
# `factory/mergequeue/onboard.py` and `factory/stack_packs.py`, and the neighbour
# log over every file this plan touches holds nothing since 2026-09-02 — so
# nothing had moved. Every one is now written in the `path.py:NN` — `symbol`
# form, and twenty-two further citations were added, so the next drift is
# machine-caught rather than prose-checked.
#
# TWO OF THE FOUR DECLARED KEYS ARE REMOVED, AND THAT IS THIS PASS'S LEDGER ACT.
# `roadmap/a-landed-but-unattested-spec-parks-the-line-and-the-floor-idles-until-an-operator-attests`
# (critical) is TWO defects in one row. This spec fixes the first — the built
# spec stops being selected, so it never parks — and reaches nothing of the
# second, which is the one the row is named for: the roadmap idled through the
# 17:55, 18:00 and 18:05 ticks instead of proceeding to 120, contradicting its own
# module docstring, and the row records that the recovery needed a `rescan`
# signal and that which step was strictly necessary is UNPROVEN. A park from any
# other check reproduces it. Declaring it here would let
# `ergane findings triage --apply` close a critical stall on the strength of a
# half fix, which is exactly the shape 100 and 092 were caught in.
# `roadmap/the-status-board-marks-a-spec-dispatchable-that-the-roadmap-will-never-dispatch`
# reads like US2 by its name and is a different defect by its body: 105 finished
# 2 of 4 stories, so it is *not* observed-landed, and what strands it is the
# `entry.spec_dir not in self._landed` filter the dispatch loop applies and no
# surface shows. US2's predicate answers "every story landed"; it will still call
# 105 dispatchable. Both keys stay open and are named here so the next reader does
# not re-derive this.
#
# THE PLAN WAS WRONG ABOUT WHERE US3 LIVES, AND THAT IS THIS PASS'S EXPENSIVE
# FIND. It said US3 is "an early exit in the roadmap's per-spec path ... before
# the clone and onboard, guarded by the distinction US2 introduces". Inside the
# workflow that distinction does not exist: `compute_readiness` is handed
# `self._observed_resolver()`, the run-local `_landed` map, and a scheduled run
# starts fresh every five minutes with that map empty. An implementer obeying the
# old sentence would either guard on a fact that is always False — shipping a
# green story that changes nothing on a real floor — or shell git in workflow
# code and break constitution IV. US3 now adds a `landed_for_spec` activity
# mirroring `drift_for_spec`, injects it at the one `compute_readiness` call the
# scheduling pass makes, and the guard lands where the dispatchable list is built.
#
# FR-003 ASSERTED A DISTINCTION THE MECHANISM DOES NOT PRODUCE. It required the
# reported reason to separate "an unsatisfied `depends_on_landed` edge" from the
# other park reasons. No park carries one: the roadmap parks on `clone`, `derive`,
# `preflight:<check>`, `onboarding`, `manifest` and `collision`, and an
# unsatisfied edge is not a park at all — it is a blocker, already named on the
# queue line. FR-003 now requires the `check` and the `detail` the workflow
# already produced, carried verbatim, which is what makes an onboarding refusal
# and an empty delta tell themselves apart.
#
# FR-011 AND FR-012 ARE NEW, AND BOTH CLOSE A HOLE A GREEN DIFF COULD HAVE LEFT.
# US2's old S2 was satisfiable by a `factory/roadmap/models.py`-only diff while
# the human queue line went on printing `dispatchable`, because `_queue_lines`
# decides that word from `blockers` and never reads the flag (FR-011). And the
# landed read US3 adds is the third git read in the roadmap's scheduling pass; on
# 2026-08-26 one such read ran on the worker's event loop, held it 5m12s and
# killed a working node whose heartbeat timed out at 120s (FR-012).
#
# STILL NOT IN SCOPE, RESTATED AFTER THE ABOVE. No frontmatter is written. The
# park mechanism is unchanged — the same checks park the same specs with the same
# details; what changes is that the park is legible and that one class of spec
# stops reaching it. The `_landed` strand this spec does not fix keeps its open
# finding.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04): the adversarial review refuted the
# refined trio on two blocking defects and four minor ones, and every one was
# re-derived from the tree at 602a92c before it was accepted.
# (1) THE LEAD KEY WAS DECLARED WHOLE AND FIXED ONE SURFACE OF TWO. Its row says
# "nothing *anywhere* names which spec it is", and `factory/cli/roadmap.py:501`
# collapses the identical `roadmap_status` list with `len(status.parked)` on the
# second board — the board the critical row's own REPRODUCTION was read on
# ("watch `ergane roadmap status <specs-root>` report 'parked: 1'"), and whose
# sibling verb at `factory/cli/roadmap.py:403` — `roadmap_unpark_command` already
# asserts in its docstring that `ergane roadmap status` "names the parked spec
# and quotes the finding". That promise is false today and would still be false
# after the refined US1. FR-013 and US1-S5 extend US1 to it rather than dropping
# the key; its `--json` needs nothing, because `roadmap_status_command` prints
# `asdict(status)` and the findings are already whole in it.
# (2) THERE ARE TWO `compute_readiness` CALLS IN `factory/roadmap/workflow.py`,
# AND THE REFINED TRIO NAMED ONE. The scheduling pass calls it at :851; the
# `roadmap_status` query calls it again at :687 with its own
# `self._observed_resolver()`. US3-S2 requires the query to answer with the third
# state and had no FR behind it, and T023 told the implementer there was "one
# call site" — which ships a query that still says `ready` + dispatchable while
# the dispatch loop has already excluded the spec, the exact disagreement US3-S2
# forbids. FR-014 is new, US3 implements it, and the instruction is now the one
# the drift precedent actually sets: cache the read on the instance as `self._drift`
# is at :850 and read at :690, and let `factory/roadmap/workflow.py:1441` —
# `RoadmapWorkflow._observed_resolver` answer from both maps so both call sites
# follow from one change and cannot disagree.
# (3) THE PLAN'S "FOLLOWS FOR FREE" PARAGRAPH WAS WRONG ABOUT WHICH RENDERER.
# `factory/roadmap/cli.py:46` — `render_command` passes NO `landed_for` at all,
# deliberately (`factory/roadmap/cli.py:74` — `_cli_drift_resolver` says the
# offline render must work on a laptop with no factory running), so
# `_render_roadmap` can never print the third word however US2 changes
# `factory/roadmap/models.py`. Only `factory/cli/status.py:364` — `_entries`
# genuinely follows. US2-S2 no longer claims "the roadmap", the offline render is
# named out of scope, and the per-spec board at `factory/cli/roadmap.py:508`
# follows from FR-014 instead.
# (4) FR-011 ASSERTED AN ABSENCE AND NAMED NO REPLACEMENT. It said the word
# `dispatchable` must not be printed and left the else-branch to the
# implementer's invention on a spec whose whole subject is a legible board. It
# now pins the string to `awaiting attestation`, which is the fix shape the
# `operator/...` ledger row names in its own words.
# (5) 057 IS THE LIVE INSTANCE AND WAS CITED ONLY AS A NEIGHBOUR. At 602a92c it
# is the only `state: ready` spec in the corpus
# (`specs/057-a-new-repo-gets-a-constitution/spec.md:2`) and all four of its
# stories are landed on ergane-buildout (8ee5e9c, 602a92c, 5c43d4a, 1027a05), so
# it is the built-but-unattested spec this spec exists for and the one the
# roadmap clones, onboards and parks on every tick right now. plan.md's operator
# verification named a search over the corpus; it names 057 now.
# (6) TWO CITATIONS IN EARLIER PROVENANCE ARE OFF BY A FEW LINES AND ARE
# CORRECTED HERE RATHER THAN EDITED IN PLACE, because provenance is a chain.
# `factory/roadmap/models.py:585` in the DRAFTED `NOT IN SCOPE.` paragraph is the
# drift-fingerprint sentence; the injected-resolvers sentence it means is at
# `factory/roadmap/models.py:587` — `compute_readiness`, which FR-008 and plan.md
# already cite correctly. And "This repository has 117" in the DRAFTED cost
# paragraph was true when it was written; `ls -d specs/*/` counts 141 at 602a92c,
# and plan.md and tasks.md now say "more than a hundred and forty" so the number
# cannot rot again.
# NOT REPAIRED, DELIBERATELY: `specs/131-.../workgraph.json` is a compiled
# artefact from before the refinement and is outside this pass's write scope. It
# is stale in three ways now — `us2.requirement_keys` stops at FR-008, `us3`'s at
# FR-010, and it carries an inferred us3→us1 edge this refinement resolved — so
# it must be re-derived or deleted before any dispatch that reads a graph off
# disk. The two removed ledger keys stay open and unclaimed.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), second pass, against the
# adversarial review; every refutation re-derived from the tree at 602a92c
# before it was accepted, and two were declined with evidence.
# (A) THE RULE HAD TWO INPUTS WHERE THE MECHANISM HAS THREE, AND THE MISSING
# ONE WAS DRIFT. `factory/cli/status.py:469` — `_observed_landing` answers
# landed as soon as every declared story key has a landing commit, and
# `factory/workgraph/landed.py:130` — `landed_facts` matches commit SUBJECTS
# only — it never compares content. So an amended spec, one whose operator
# edited a scenario and flipped `state` back to `ready` because
# `factory/roadmap/models.py:586` — `compute_readiness` documents that as the
# rebuild path, satisfies "every declared story landed" while
# `factory/workgraph/delta.py:9` re-opens real work for it. The rule as refined
# would have made that spec not dispatchable, printed `awaiting attestation`
# over it and dropped it from the roadmap's dispatchable list — an operator loop
# with no exit, on the one path amendments are rebuilt through. Drift is now the
# third input: the truth table carries the column, FR-005 and FR-009 state the
# conjunction, FR-015 is the control, FR-016 makes `ergane status specs` supply
# the answer, and US2-S6/S7/S8 and trap 17 hold it.
# (B) AN UNSUPPLIED DRIFT ANSWER MUST NOT READ AS A NEGATIVE ONE.
# `factory/roadmap/models.py:592` — `compute_readiness` defaults `drifted_for`
# to a lambda returning False, and `collect_floor` supplies no drift resolver at
# all, so "no answer" and "not drifted" are the same value today. FR-015 makes
# the built determination require an answer that was actually supplied, which is
# what keeps `ergane roadmap render` — which passes no `landed_for` either —
# unchanged and safe.
# (C) THE QUERY REPORTS A SPEC'S OWN `landed` FROM A MAP THE MERGED RESOLVER
# DOES NOT REACH. `factory/roadmap/workflow.py:725` reads
# `self._landed.get(entry.spec_dir)` directly rather than through
# `factory/roadmap/workflow.py:1441` — `RoadmapWorkflow._observed_resolver`, so
# after US3 the per-spec board at `factory/cli/roadmap.py:508` would have
# printed the built spec's third word beside `(landed=False)` — a contradiction
# on the surface this spec exists to make legible, and the exact line the
# `operator/...` ledger row cites as its ref. FR-014 now owns that field too.
# (D) THE MERGED RESOLVER WIDENS DEPENDENCY SATISFACTION, AND THAT IS INTENDED
# RATHER THAN INCIDENTAL. `compute_readiness` satisfies every
# `depends_on_landed` edge through the same `observed(...)` seam, so a spec
# whose dependency is built-but-unattested becomes dispatchable inside the
# roadmap where today it waits. That is the first of the two consequences the
# `operator/...` row names, and it makes the roadmap agree with
# `ergane status specs`, which has read those edges from the landing history all
# along. Named in scope, required by FR-009, controlled by US3-S6.
# (E) BOTH ROADMAP READS ARE BOUNDED BY DECLARED STATE. `_compute_drift` awaits
# one activity per LANDED spec — 102 of the 141 in this corpus — every five
# minutes; an unbounded landed read would add 141 more git scans a tick to the
# story whose purpose is removing a per-tick cost. FR-009 bounds both reads to
# `ready` specs, which is one spec today.
# DECLINED, WITH EVIDENCE. The review asked for `factory/roadmap/models.py:91`
# to be rewritten in the `path.py:NN` — `symbol` form as `RENDERED_AMENDED`.
# That would refuse the gate: `factory/cli/nouns/spec.py:846` resolves symbol
# names from `ast.FunctionDef`, `ast.AsyncFunctionDef` and `ast.ClassDef` nodes
# only, so a module-level constant assignment is reported "is not defined in
# that file" at refusal severity for a draft spec. The bare citation is correct
# and stays. The review also asked for the stale `workgraph.json` to be deleted
# or re-derived; both acts are outside this pass's write scope, so the hazard is
# restated below rather than removed, and it is now wider than the note says —
# `us1` is short of FR-013, `us2` of FR-011 and FR-016, `us3` of FR-012 and
# FR-014, and FR-015 is owned by nobody in it.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), third pass, against the second
# adversarial review; every refutation re-derived from the tree at 602a92c
# before it was accepted, and one was declined because this pass may not write
# the file it names.
# (i) US3 HELD THE LANDED READ AND LET GO OF THE DRIFT READ, WHICH IS THE HALF
# THAT SAVES AN AMENDMENT. Inside the roadmap `drifted_for` is *always*
# supplied — `factory/roadmap/workflow.py:854` and
# `factory/roadmap/workflow.py:690` both pass
# `lambda spec_dir: self._drift.get(spec_dir, False)` — so FR-015's
# unsupplied-answer guard cannot fire there at all; and `self._drift` is
# populated only for `SpecState.LANDED` (`factory/roadmap/workflow.py:1508`),
# with `factory/roadmap/workflow.py:1455` — `RoadmapWorkflow._drift_resolver`
# short-circuiting every non-`landed` spec to `False` a second time. A US3 that
# adds the landed read and stops there satisfies S1 through S7 — `.get` answers
# `False` whether a drift read ran or not — and silently stops the floor
# rebuilding any spec the operator amended and flipped back to `ready`. FR-017
# is new, US3 implements it, US3-S8 is the positive lower bound that the drift
# read actually ran for that spec, and trap 21 carries the reproduction plus the
# awaiting order — `_compute_landed` before `_compute_drift` at
# `factory/roadmap/workflow.py:916` — without which the widened gate reads an
# empty landed map and the same regression arrives through ordering.
# (ii) FR-009 NARROWED THE DRIFT READ AND WOULD HAVE RETIRED `amended`, WHICH
# CORRECTS PARAGRAPH (E) ABOVE. Its second sentence bound *both* reads to
# `ready` entries — the wording (E) introduced — which read literally
# drops the drift read for `state: landed` specs — 102 of the 141 here — and
# silently retires the existing render at `factory/roadmap/models.py:544` —
# `SpecReadiness.rendered_state`, while tasks.md said "widen". Read one way the
# implementer regresses a landed feature with no test to catch it; read the
# other, the judge can fail a correct diff against FR-009's MUST. The bound is
# now split — the landed read `ready`-only, the drift read every `landed` entry
# as today *plus* the `ready` entries the landed read reported landed — and
# US3-S9 is the control that a drifted `landed` spec still renders `amended`.
# (iii) THREE PLACES WERE TRUE FOR A REASON THAT IS FALSE, OR SAID NOTHING AN
# IMPLEMENTER CAN ACT ON. plan.md's neighbour paragraph claimed
# `onboard_target_repo` is not the path the roadmap's onboarding gate calls; it
# is (`factory/activities/merge_activities.py:785` — `validate_target_repo`),
# and the real reason 057's `_standards_finding` cannot reach a roadmap park is
# that the call supplies no `init_facts` and `factory/mergequeue/onboard.py:479`
# — `evaluate_init_facts` returns `()` for `None`. Gap item 1 and trap 3 now say
# that `ParkedFinding`'s own docstring at `factory/roadmap/workflow.py:285`
# lists five checks and omits `manifest`, so an implementer who counts from the
# record rather than from the eight call sites does not conclude this spec
# invented a park class. Trap 11 was a description; it now names FR-006, the
# in-memory precedent at `factory/roadmap/workflow.py:1110` —
# `RoadmapWorkflow._apply_promotions`, and the write it forbids.
# (iv) THE OPERATOR VERIFICATION TOLD THE OPERATOR TO PRESERVE A HAZARD. 057 is
# the only `state: ready` spec in the corpus and sorts before 131, so flipping
# this spec ready while 057 is still built-and-unattested risks this epic never
# being dispatched — on the open critical finding this spec deliberately does
# not fix, which records the roadmap idling through three consecutive ticks
# after a park instead of proceeding. Step 1 now says: capture 057's queue lines
# for step 4's before-and-after, attest 057, signal `rescan`
# (`factory/roadmap/workflow.py:677` — `RoadmapWorkflow.rescan`), then flip.
# DECLINED, WITH EVIDENCE, AND THE HAZARD STANDS UNCHANGED. The review asked
# again for `specs/131-.../workgraph.json` to be deleted or re-derived. This
# pass may write only spec.md, plan.md and tasks.md and may not run
# `ergane spec derive`, so the stale artefact is untouched and the NOT REPAIRED
# note above still holds — wider now, because FR-017 is owned by nobody in it
# either. `ergane build start` takes a path to a compiled artefact
# (`factory/cli/nouns/build.py:2085`) and loads it verbatim
# (`factory/cli/nouns/build.py:808`), and `reset` resolves
# `<specs_root>/<epic_id>/workgraph.json` off disk with no Temporal fallback
# (`factory/cli/nouns/build.py:2147` — `resolve_reset_graph`), so a manual
# dispatch would spend three attempts against a graph that disagrees with this
# spec. The roadmap path is unaffected: it re-derives from the freshly read
# spec text through `derive_spec` at `factory/roadmap/workflow.py:1212`. Delete
# or re-derive the artefact before any dispatch that reads a graph off disk;
# every sibling of this batch carries one of the same vintage.
---

# Feature Specification: the status board names the spec it cannot dispatch

**Created**: 2026-09-03
**Depends on**: nothing.

## The gap, stated precisely

Two facts the platform already computes are thrown away before an operator can
read them, and one of the two costs a clone every five minutes.

1. **The roadmap knows exactly which specs it parked, and why.** `_park`
   (`factory/roadmap/workflow.py:1433` — `RoadmapWorkflow._park`) records a
   `ParkedFinding` (`factory/roadmap/workflow.py:351` — `ParkedFinding`) carrying
   the spec directory, the `check` that refused — one of `clone`, `derive`,
   `preflight:<check>`, `onboarding`, `manifest`, `collision` — and the refusal
   `detail` verbatim. Those six are read from the eight `self._park(...)` call
   sites, which are the authority: the record's own docstring at
   `factory/roadmap/workflow.py:351` — `ParkedFinding` lists five and omits
   `manifest`. The `roadmap_status` query
   (`factory/roadmap/workflow.py:725` — `RoadmapWorkflow.roadmap_status`) returns
   that whole list.

2. **The CLI throws the list away on arrival.** `factory/cli/status.py:554` is,
   verbatim:

```python
        parked=None if document is None else len(document.get("parked") or []),
```

   Every name and every reason is inside `document`. `len()` is where they stop.

3. **So both `ergane status specs` surfaces have only an integer.** The human
   line is `factory/cli/status.py:780`, and `--json` is `asdict(floor)`
   (`factory/cli/status.py:272` — `status_command`, which prints it at
   `factory/cli/status.py:276`) over a `RoadmapDisposition`
   (`factory/cli/status.py:164` — `RoadmapDisposition`) whose `parked` field is
   typed `int | None` at `factory/cli/status.py:180`. The shape of the mismatch is
   what makes it expensive: **parking is common, is not an error, and its remedy
   is always a per-spec act** — attesting one spec, fixing one repository, editing
   one document. A count is precisely the one shape of answer an operator cannot
   act on.

4. **A second board does the same collapse, on the verb the incident was read
   on.** `factory/cli/roadmap.py:484` — `_render_status` holds the whole
   `list[ParkedFinding]` in hand and prints, at `factory/cli/roadmap.py:501`:

```python
        f"parked: {len(status.parked)}",
```

   Its `--json` is unaffected — `roadmap_status_command`
   (`factory/cli/roadmap.py:420` — `roadmap_status_command`) prints
   `asdict(status)`, so the findings are already whole there. Two things make
   this surface load-bearing rather than incidental. The recorded reproduction of
   the roadmap-stall incident is "watch `ergane roadmap status <specs-root>`
   report `parked: 1`", and the sibling verb's own docstring at
   `factory/cli/roadmap.py:403` — `roadmap_unpark_command` already tells the
   operator that "`ergane roadmap status` names the parked spec and quotes the
   finding; the operator fixes what it named and runs this" — a promise the code
   does not keep.

5. **Separately, a fully-landed spec still advertises itself as dispatchable.**
   `factory/roadmap/models.py:607` is, verbatim:

```python
        dispatchable = entry.state is SpecState.READY and not blockers
```

   The injected `observed(...)` resolver — the thing that knows whether a spec's
   stories have landed — is consulted only inside the `depends_on` loop above, for
   an entry's *dependencies*. It is never called for the entry's own `spec_dir`.
   The `drifted` computation on the next line is gated on `SpecState.LANDED`, so
   it cannot reach a `ready` spec either.

6. **The fact is already in the process at the status surface.**
   `factory/cli/status.py:441` — `_observed_landed_resolver` is
   `compute_readiness`'s `landed_for`, backed by the landing history, and
   `collect_floor` (`factory/cli/status.py:284` — `collect_floor`) injects it at
   `factory/cli/status.py:292`. **Confirmed empirically**: injecting a
   `landed_for` resolver that answers landed=True still yields
   `dispatchable=True`. Only the predicate ignores it.

7. **Even with the flag corrected, the human queue line would still read
   `dispatchable`.** `factory/cli/status.py:810` — `_queue_lines` decides that
   word from `entry.blockers` alone; a spec with no blockers prints
   `dispatchable` whatever the computed flag says.

8. **Inside the roadmap the same predicate is fed a different resolver, at two
   call sites.** The scheduling pass calls `compute_readiness` at
   `factory/roadmap/workflow.py:851` and the `roadmap_status` query calls it
   again at `factory/roadmap/workflow.py:687`; both are handed
   `self._observed_resolver()` (`factory/roadmap/workflow.py:1441` —
   `RoadmapWorkflow._observed_resolver`), which answers from `self._landed`
   (`factory/roadmap/workflow.py:624`) — the children *this run* watched. A
   scheduled run starts fresh every five minutes with that map empty. So the
   correction in 5 is invisible to the roadmap until the roadmap gets a landed
   read of its own, the way it already has a drift read of its own
   (`factory/roadmap/workflow.py:1508` — `RoadmapWorkflow._compute_drift`), and
   **both** call sites must see that read or the query and the dispatch loop can
   disagree about the same spec.

9. **What that costs.** With the built spec still in the dispatchable list
   (`factory/roadmap/workflow.py:864`), every pass with a free epic slot calls
   `_dispatch` (`factory/roadmap/workflow.py:1247` —
   `RoadmapWorkflow._dispatch`), which pays `clone_target`
   (`factory/roadmap/workflow.py:1187`), derivation, preflight and
   `onboard_target` (`factory/roadmap/workflow.py:1334`) before the zero-node
   refusal at `factory/roadmap/workflow.py:1269` parks it. At a five-minute
   schedule that is up to 288 cycles a day per such spec — paid exactly when the
   floor is idle, since a busy floor has no free slot.

10. **"Landed" is read from commit subjects, so it cannot see a spec that
   changed after it landed.** `factory/cli/status.py:469` — `_observed_landing`
   answers landed as soon as every declared story key has a landing commit, and
   `factory/workgraph/landed.py:130` — `landed_facts` matches commit *subjects*;
   content is never compared. The delta does compare it —
   `factory/workgraph/delta.py:9` re-opens every landed story whose fingerprint
   changed — and `factory/roadmap/models.py:586` — `compute_readiness` documents
   the operator's rebuild path for an amended spec as flipping `state` back to
   `ready`. So "every story landed" and "there is nothing left to build" are two
   different facts, and the second needs a drift answer as well as a landed one.

Nothing under `factory/` writes `state: landed` back into frontmatter —
attestation is an operator act — so the window between "every story landed" and
"someone attested it" is real, and on this floor it has lasted days. It is open
right now: `specs/057-a-new-repo-gets-a-constitution/spec.md:2` reads
`state: ready` and every one of 057's four stories is landed on `ergane-buildout`
(`8ee5e9c`, `602a92c`, `5c43d4a`, `1027a05`).

## The rule this spec is asking for

**A spec the roadmap cannot or will not dispatch is named, with its reason, on
every surface that counts it — and a spec whose every story has landed is not
offered as work, is not called dispatchable, and is not paid for.**

Three inputs combine: the declared frontmatter state, whether every declared
story is observed landed, and whether any of those stories has drifted from the
content it landed with. The third is what separates a spec with nothing left to
do from an amended one the operator flipped back to `ready` to have rebuilt, and
an *unsupplied* drift answer counts as drift, never as its absence:

| frontmatter `state` | every declared story landed | drift answer for that spec | rendered state | dispatchable | roadmap clones and onboards it |
| --- | --- | --- | --- | --- | --- |
| `ready` | no | not consulted | `ready` | yes | yes, exactly as today |
| `ready` | yes | supplied, and no fingerprint changed | a third word, neither `ready` nor `landed` | no | no |
| `ready` | yes | supplied, and some fingerprint changed | `ready` | yes | yes, exactly as today — this is the rebuild of an amendment |
| `ready` | yes | none supplied | `ready` | yes | yes, exactly as today |
| `landed` | not consulted | renders `amended` when drifted, as today | `landed`, or `amended` when drifted | no | no, exactly as today |
| `draft` or `deferred` | not consulted | not consulted | as declared | no | no, exactly as today |

### What this spec is not

It is not the authoring seam. Nothing here writes frontmatter; `state: ready`
stays an operator's declaration, and making it writable is a different spec.

It is not a change to the park mechanism. The roadmap parks exactly what it parks
today, for exactly the same reasons, with the same `check` and the same `detail`.
What changes is that the park is legible, and that one class of spec stops
reaching it.

It is not a claim that an empty epic is being dispatched. It is not —
`factory/roadmap/workflow.py:1269` already refuses a zero-node delta before any
child epic starts. The cost this spec removes is the clone-and-onboard cycle paid
to reach that refusal, and the queue that lies about what is left to do.

It is not a way to stop an amendment from being rebuilt. A spec whose text the
operator changed after it landed still has a landing commit for every story, so
the landed input alone cannot tell it from a finished one; the drift input is
what does. FR-015 is its control on the `ergane status specs` side and FR-017 is
its control inside the roadmap, where FR-015 cannot reach: both roadmap call
sites always *supply* a drift answer (`factory/roadmap/workflow.py:854`,
`factory/roadmap/workflow.py:690`), so there only a drift read that actually
covers the spec keeps the path open. The amended-rebuild path
`factory/roadmap/models.py:586` — `compute_readiness` documents — flip `state`
back to `ready`, let `factory/workgraph/delta.py:9` re-open the changed stories —
works after this spec exactly as it works today.

It does widen one thing deliberately, and says so here rather than leaving it to
be discovered. Inside the roadmap, `depends_on_landed` edges are satisfied
through the same `observed(...)` seam this spec teaches to answer from a real
landed read, so a spec whose dependency is built-but-unattested becomes
dispatchable where today it waits for an attestation. That is the first of the
two consequences the `operator/...` ledger row names, and it makes the roadmap
agree with `ergane status specs`, which has satisfied those edges from the
landing history all along (`factory/cli/status.py:441` —
`_observed_landed_resolver`). FR-009 requires it and US3-S6 controls it.

It does not make a *partially* landed spec legible. A spec whose epic finished
with some stories unlanded is stranded by a different filter — the
`entry.spec_dir not in self._landed` clause at `factory/roadmap/workflow.py:870`,
inside the comprehension that starts at `factory/roadmap/workflow.py:864` — that
no surface shows; that is an open finding and a different spec.

It does not reach the offline render. `factory/roadmap/cli.py:46` —
`render_command` passes no `landed_for` resolver at all, by a decision its own
`factory/roadmap/cli.py:74` — `_cli_drift_resolver` documents: that verb must
work on a laptop with no factory running and therefore cannot read the target
repo's landing history. `factory/roadmap/cli.py:92` — `_render_roadmap` will keep
printing `ready` for a built spec after this spec lands, and that is correct, not
a residue. The two surfaces that *do* change are `ergane status specs`, whose
`collect_floor` injects the landing-history resolver, and the per-spec board at
`factory/cli/roadmap.py:508`, which reads the workflow query and therefore
follows FR-014.

## User Scenarios & Testing

### User Story 1 - Parked names the spec and the reason (Priority: P1)

As an operator, when the line is stopped I am told which spec stopped it and why,
without cross-referencing two commands per spec.

**Why this priority**: P1 and it depends on nothing. It is the story that turns an
11h40m diagnosis into a five-minute one, and the reason text it surfaces is
already computed, already carried across the wire, and discarded by one `len()` —
twice, in two files.

**Independent Test**: Answer the roadmap query with two parked findings of
different checks, render all three surfaces, and read the names and the reasons.

**Acceptance Scenarios**:

1. **Given** a roadmap answering with one or more parked findings, **When**
   `ergane status specs` renders, **Then** it names each parked spec directory
   with the `check` that refused it and the `detail` verbatim, rather than only
   counting them.
2. **Given** the same answer, **When** `--json` is requested, **Then** the payload
   carries, for each parked spec, its directory, its check and its detail as
   separate fields rather than an integer.
3. **Given** one spec parked by an onboarding refusal and another parked with
   `derive` and the empty-delta detail, **When** either surface renders, **Then**
   the two entries are told apart by their check and their detail, because the
   operator's next act differs — fix the repository, or attest the spec.
4. **Given** a roadmap answering with no parked findings, **When** the human
   surface renders, **Then** the roadmap block is byte-identical to today's, and
   the added JSON field is present and empty rather than absent — proven by a
   committed test.
5. **Given** the same two parked findings, **When** `ergane roadmap status` builds
   its human document, **Then** the block under `parked:` names each parked spec
   with its check and its detail, so the promise
   `factory/cli/roadmap.py:403` — `roadmap_unpark_command` already makes in its
   docstring becomes true — proven by a committed test over
   `factory/cli/roadmap.py:484` — `_render_status`, whose `--json` half needs no
   change because it prints the query answer whole.

### User Story 2 - A built spec is rendered as built, not as ready (Priority: P2)

As an operator, a spec whose every story has landed does not sit in my
dispatchable queue calling itself dispatchable.

**Why this priority**: P2 and it depends on nothing in this spec, but it is second
because US1 is what an operator reaches for during an outage and this is what
prevents a slower, quieter waste. It is also US3's substrate.

**Independent Test**: Compute readiness for a spec whose frontmatter reads `ready`
with a `landed_for` resolver that answers landed=True and a `drifted_for`
resolver that answers False, and read both the flag and the rendered queue line;
then flip the drift answer and read them again.

**Acceptance Scenarios**:

1. **Given** a spec whose frontmatter reads `ready`, whose every story is
   observed landed, and whose supplied drift answer reports no changed
   fingerprint, **When** readiness is computed, **Then** it is not dispatchable.

2. **Given** the same spec, **When** the `ergane status specs` queue entry is
   built, **Then** its state is a third word, distinct from both `ready` and
   `landed`, because the operator's outstanding act is attestation and printing
   `landed` would assert an attestation nobody made.

3. **Given** the same spec and no unsatisfied dependency, **When** the human queue
   line is built, **Then** the line carries that third state and the words
   `awaiting attestation` in place of the word `dispatchable`, because the word
   follows the computed flag rather than the absence of blockers, and the
   operator's outstanding act belongs on the line.

4. **Given** a spec whose frontmatter reads `ready` and some of whose stories have
   **not** landed, **When** readiness is computed, **Then** it is dispatchable and
   its rendered state is `ready`, exactly as today.
### User Story 3 - The roadmap stops paying for a spec it will never dispatch (Priority: P3)

As an operator, a built-but-unattested spec does not cost a clone and an onboard
every five minutes.

**Why this priority**: P3 and it follows US2 because it consumes the predicate US2
changes. It is last because the cost is steady waste rather than a stopped line,
and because it is the story most likely to be over-scoped if attempted first.

**Independent Test**: Run one scheduling pass with the roadmap's landed read
scripted to answer landed for a `ready` spec and its drift read scripted to
answer not-drifted, count the activities executed for that spec, and query
`roadmap_status` on the same instance.

**Acceptance Scenarios**:

1. **Given** a spec whose frontmatter reads `ready` and whose every story the
   roadmap's own landed read reports as landed, **When** the scheduling pass
   builds its dispatchable list, **Then** that spec is absent from it and neither
   `clone_target` nor `onboard_target` is executed on its account.

2. **Given** the same pass has run, **When** the `roadmap_status` query answers —
   which calls `compute_readiness` a second time, at
   `factory/roadmap/workflow.py:687`, not the pass's call at
   `factory/roadmap/workflow.py:851` — **Then** it reports for that spec the same
   `rendered_state` and the same `dispatchable` flag the pass computed, so the
   two answers cannot disagree about why nothing happened.

3. **Given** a spec with genuine outstanding work, **When** the pass runs, **Then**
   it is cloned, onboarded and dispatched exactly as today.

4. **Given** a spec whose delta is empty for some other reason, **When** it is
   dispatched, **Then** the zero-node refusal at
   `factory/roadmap/workflow.py:1269` still parks it with the same detail, because
   this story adds an earlier guard and does not replace the backstop.

5. **Given** a `ready` spec whose `depends_on_landed` names a spec that is built
   but unattested, **When** the scheduling pass computes readiness, **Then** the
   dependent is dispatchable rather than blocked on that edge, because the
   roadmap now satisfies it from the same landed answer `ergane status specs`
   already uses — proven by a committed test that scripts the dependency's
   landed read.

### User Story 4 - Readiness reaches its facts only through the resolvers it is given (Priority: P2)

As an operator, the predicate that decides whether a spec is dispatchable asks
nobody on its own — it is handed the landed fact and the drift fact — and an
amended spec I flipped back to `ready` is still dispatchable.

**Why this priority**: P2, and it is the second half of US2, split out on
2026-09-08 because the pair ran to thirteen tasks and no story above eleven has
landed on this floor. US2 makes a built spec render as built; this story is the
contract that keeps that predicate honest — no git read of its own, drift means
dispatchable, and an answer nobody gave is not a negative answer. It merges after
US2 and before US3, which consumes the finished predicate.

**Independent Test**: Compute readiness with both facts supplied and no
repository; then with a drift answer reporting a changed fingerprint; then with
no drift resolver supplied at all, and read the flag each time.

**Acceptance Scenarios**:

1. **Given** readiness computation, **When** it runs, **Then** it performs no git
   read of its own and reaches the landed fact and the drift fact only through
   the injected resolvers — proven by a committed test that supplies both facts
   and no repository.

2. **Given** a spec whose frontmatter reads `ready` and whose every story is
   observed landed, but whose supplied drift answer reports a changed
   fingerprint, **When** readiness is computed, **Then** it is dispatchable and
   its rendered state is `ready`, exactly as today, because an amended spec the
   operator flipped back to `ready` has real work the delta will re-open —
   proven by a committed test.

3. **Given** that same landed spec and no drift resolver supplied at all,
   **When** readiness is computed, **Then** it is dispatchable and renders
   `ready`, because an answer nobody gave is not a negative answer — proven by a
   committed test that passes no `drifted_for`.

4. **Given** `ergane status specs` reading a repository, **When** its readiness
   basis is assembled, **Then** it supplies a drift resolver that compares each
   story's fingerprint pinned at its landing commit against the fingerprint of
   the spec text on disk, asks git without fetching, and is consulted only for a
   `ready` spec its landed read already reported landed — proven by a committed
   test.
### User Story 5 - The drift read is bounded, and paid for once (Priority: P3)

As an operator, the read that decides a spec is finished costs one bounded git
question per spec per pass, not a clone, and the activity that answers it is the
only place that asks.

**Why this priority**: P3, and it is the second half of US3, split out on
2026-09-08 for the same reason — thirteen tasks. US3 stops the roadmap
dispatching a built spec; this story is the cost discipline around the read that
lets it decide, and the controls that keep a future widening from turning one
bounded question back into a clone. It merges last because it constrains code US3
writes.

**Independent Test**: Run one scheduling pass and count the activities executed
for the spec, and assert the bound on what the drift read may ask.

**Acceptance Scenarios**:

1. **Given** the roadmap's landed read, **When** the activity runs, **Then** the
   git work is performed off the event loop, in the same split
   `factory/activities/roadmap_activities.py:512` — `_drift_from_git` makes —
   proven by a committed test.

2. **Given** a corpus of specs in every declared state, **When** the pass runs,
   **Then** the roadmap's landed read is executed only for the entries whose
   declared state is `ready`, as
   `factory/roadmap/workflow.py:1508` — `RoadmapWorkflow._compute_drift` already
   restricts its own read to `landed` — proven by a committed test that counts
   the activity calls.

3. **Given** a `ready` spec whose every story the roadmap's own landed read
   reports as landed but whose own drift read reports a changed fingerprint,
   **When** the scheduling pass builds its dispatchable list, **Then** the spec
   is in it and is cloned, onboarded and dispatched exactly as today, **and**
   the roadmap's drift read was executed for that spec rather than defaulted —
   proven by a committed test that scripts both reads and asserts the drift
   activity ran for it.

4. **Given** a spec whose frontmatter reads `landed` and one of whose stories'
   fingerprints has changed, **When** the pass runs and the `roadmap_status`
   query answers, **Then** it is reported drifted and renders `amended`, exactly
   as it does today, because the drift read is widened and never narrowed —
   proven by a committed test.
## Functional Requirements

- **FR-001**: `ergane status specs` MUST name each parked spec directory, with the
  `check` that refused it and the refusal `detail`, rather than reporting only a
  count.
- **FR-002**: The `--json` payload MUST carry, per parked spec, the directory, the
  check and the detail as separate fields.
- **FR-003**: The reported reason MUST be the `check` and `detail` the workflow
  already recorded on the `ParkedFinding` (`factory/roadmap/workflow.py:351` —
  `ParkedFinding`), carried verbatim and not re-derived, so an onboarding refusal
  and an empty delta tell themselves apart by what the roadmap actually said.
- **FR-004**: With no parked spec the human rendering MUST be byte-identical to
  today's, and the added JSON field MUST be present and empty rather than absent.
- **FR-005**: A spec whose frontmatter reads `ready` MUST NOT be dispatchable
  when every declared story is observed landed **and** a supplied drift answer
  reports that no declared story's fingerprint has changed since it landed. Both
  conditions are required: landing is read from commit subjects
  (`factory/workgraph/landed.py:130` — `landed_facts`) and is blind to content,
  so "landed" alone does not mean there is nothing left to build.
- **FR-006**: That spec MUST render as a state distinct from both `ready` and
  `landed`, because attestation is an outstanding operator act and rendering it as
  `landed` would assert an attestation nobody made.
- **FR-007**: A `ready` spec with unlanded stories MUST remain dispatchable, and
  MUST keep rendering as `ready`, exactly as today.
- **FR-008**: `compute_readiness` MUST perform no git read of its own and MUST
  reach the landed fact and the drift fact only through the injected resolvers,
  preserving the separation `factory/roadmap/models.py:587` —
  `compute_readiness` documents.
- **FR-009**: The roadmap MUST NOT clone or onboard the target repository on
  account of a spec whose every story its own landed read reports as landed and
  whose own drift read reports no changed fingerprint; the spec MUST be absent
  from the dispatchable list rather than refused inside `_dispatch`. The landed
  read MUST be performed only for entries whose declared state is `ready`,
  mirroring the bound `factory/roadmap/workflow.py:1508` —
  `RoadmapWorkflow._compute_drift` already puts on its own read. The drift read
  MUST keep covering every `landed` entry exactly as it does today, and MUST
  additionally cover the `ready` entries the landed read reported landed — and
  no others: it is widened, never narrowed, so a `landed` spec whose
  fingerprints moved MUST still report drifted and render `amended`. And because
  that landed answer is the seam `compute_readiness` satisfies
  `depends_on_landed` edges from, a spec whose
  dependency is built-but-unattested MUST become dispatchable inside the roadmap
  where it is blocked today — the first consequence the `operator/...` ledger row
  names, and the roadmap converging on what `ergane status specs` already
  computes.
- **FR-010**: The existing zero-node delta refusal at
  `factory/roadmap/workflow.py:1269` MUST still fire unchanged for every other
  empty-delta cause.
- **FR-011**: The human queue line MUST decide the word `dispatchable` from the
  computed flag, not from the absence of blockers, and where the flag is false and
  no blocker explains it the line MUST read `awaiting attestation` in that word's
  place — the act the ledger row names as the fix shape — so the change is a
  string an operator can read rather than a removal.
- **FR-012**: The roadmap's landed read MUST perform its git work off the
  workflow worker's event loop, as `factory/activities/roadmap_activities.py:512`
  — `_drift_from_git` does, and MUST be registered on the worker's activity list.
- **FR-013**: `ergane roadmap status`'s human document MUST name each parked spec,
  with its check and its detail, under the count at `factory/cli/roadmap.py:501`,
  because that verb is where the recorded reproduction was read and
  `factory/cli/roadmap.py:403` — `roadmap_unpark_command` already documents the
  naming as fact. Its `--json` output MUST stay the query answer verbatim.
- **FR-014**: The `roadmap_status` query MUST compute readiness from the same
  landed answer the scheduling pass used, so the query at
  `factory/roadmap/workflow.py:687` and the dispatch loop at
  `factory/roadmap/workflow.py:864` cannot disagree about a built spec. The
  query MUST also report each spec's own `landed` field from that same answer —
  it is read at `factory/roadmap/workflow.py:725` from `self._landed` alone
  today — so the per-spec board at `factory/cli/roadmap.py:508` cannot print a
  spec's built state beside `landed=False`.
- **FR-015**: A `ready` spec whose every story is observed landed but whose
  supplied drift answer reports a changed fingerprint MUST stay dispatchable and
  MUST keep rendering `ready`; and where no drift answer is supplied at all the
  spec MUST be treated exactly as it is today — dispatchable, rendered `ready`.
  An answer nobody gave is never read as a negative answer, which is what keeps
  the amended-rebuild path `factory/roadmap/models.py:586` — `compute_readiness`
  documents open, and keeps every caller that supplies no resolver — including
  `factory/roadmap/cli.py:46` — `render_command` — unchanged.
- **FR-016**: `ergane status specs` MUST supply that drift answer, computed from
  the same pinned-against-current fingerprint comparison the roadmap's drift read
  makes (`factory/workgraph/landed.py:407` — `fingerprint` against
  `factory/workgraph/delta.py:48` — `fingerprint_for`), asking git without
  fetching as the rest of that command already does, and consulted only for a
  `ready` spec its landed read already reported landed.
- **FR-017**: A `ready` spec whose every story the roadmap's own landed read
  reports as landed and whose own drift read reports a changed fingerprint MUST
  stay in the roadmap's dispatchable list and MUST be cloned, onboarded and
  dispatched exactly as today; the roadmap MUST execute that drift read for such
  a spec rather than leave it defaulted. FR-015's unsupplied-answer guard cannot
  do this work here: both roadmap call sites always supply a resolver
  (`factory/roadmap/workflow.py:854` and `factory/roadmap/workflow.py:690` pass
  `self._drift.get(spec_dir, False)`), so inside the roadmap "nobody computed an
  answer" and "not drifted" are the same value, and only a drift read that
  actually ran for the spec separates an amendment from a finished spec.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-013]
US2:
  depends_on: []
  concurrent_with: [US1]
  implements: [FR-005, FR-006, FR-007, FR-011]
US4:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-008, FR-015, FR-016]
US3:
  depends_on: []
  depends_on_merged: [US4]
  implements: [FR-009, FR-010, FR-014]
US5:
  depends_on: []
  depends_on_merged: [US3]
  implements: [FR-012, FR-017]
```

**The 2026-09-08 split.** US2 and US3 each ran to thirteen tasks, above anything
that has landed on this floor, so each was cut in two: US2 -> US2 + **US4**, and
US3 -> US3 + **US5**. The new numbers are labels appended at the end; the edges
are the order, and they read US2 -> US4 -> US3 -> US5, with US1 concurrent. What
previously waited on the whole of US2 now waits on US4.

US1 and US2 both edit `factory/cli/status.py`, and the `concurrent_with` on US2 is
the author's declaration that they may race anyway (069-US2 FR-007): US1 works on
the roadmap-disposition half — the record at `factory/cli/status.py:164` and the
renderer at `factory/cli/status.py:753` — `_roadmap_lines` — plus a second file
neither sibling opens, `factory/cli/roadmap.py`; and US2 works on the queue half,
`factory/cli/status.py:810` — `_queue_lines`, and on the readiness basis,
`factory/cli/status.py:378` — `_readiness_basis` and its injection at
`factory/cli/status.py:292`, plus `factory/roadmap/models.py`, which US1 does not
open. All three of US2's regions sit above or below US1's two, and neither
story's tasks name the other's function, so the diffs land in different regions
of one file.

The one `depends_on_merged` edge is declared rather than left inferred. US3
consumes the predicate US2 changes: until `compute_readiness` treats an
own-landed spec as not dispatchable, a landed resolver injected into the roadmap
changes nothing. Built concurrently, US3 would have to invent a second answer to
"is this spec already built", and two answers that can disagree about whether to
spend a clone is a worse defect than the cost it saves.

US3 shares no production file with either sibling: it works in
`factory/roadmap/workflow.py`, `factory/activities/roadmap_activities.py` and
`factory/worker.py`.
