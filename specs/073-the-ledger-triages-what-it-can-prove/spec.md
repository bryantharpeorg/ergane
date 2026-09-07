---
state: landed
fixes:
  - hardening/the-boundary-detector-files-a-sibling-nodes-pytest-cache-as-this-attempts-escape
# Attested landed 2026-08-21 (10:00 AM CT), 5/5. US1 4411984207b5 (#259),
# US2 73fedb5361b5 (#260), US3 67a91c2a8ab6 (#262), US4 e5d4f26d6b77 (#261),
# US5 669006d63adc (#265) — all five observed on ergane-buildout by
# `ergane spec landed --default-branch ergane-buildout`, and each confirmed an
# ancestor of origin/ergane-buildout. Every node ran on `opus-closer`
# (subscription) and every node landed on its first attempt in the run that
# produced the commit.
#
# US3 CARRIES AN ASTERISK. Its first run parked on
# `escalation/an-answered-question-never-unparks-the-node` (critical, filed
# 2026-08-21): the answer was delivered and the QuestionWorkflow child COMPLETED,
# but the node stayed WAITING_OPERATOR and held US4/US5 behind it. A worker
# restart with zero pending activities reproduced the identical park, so the
# wedge is deterministic in the workflow code's answered branch
# (factory/workgraph/workflow.py:1639). The epic was terminated and US3-US5
# re-dispatched with corrected `depends_on_merged` edges. That defect is open and
# unfixed; nothing in this spec addresses it.
#
# WHAT THIS ATTESTATION DOES NOT CLAIM. The frontmatter below says US4 and US5
# fix `hardening/the-boundary-detector-files-a-sibling-nodes-pytest-cache-as-this-attempts-escape`
# (critical). That finding is still OPEN and unresolved, and the detector filed
# 17 further sibling-teardown criticals on this floor today — but the running
# worker has not been restarted since 06:36Z, so it has been executing pre-fix
# `factory/workgraph/detector.py` all day. Landing the fix and proving the fix are
# different facts; this attests the first only. Resolve the finding after a worker
# restart demonstrates a clean node.
#
# --- drafting note this supersedes ---
# Drafted 2026-08-20 7:05 AM CT by an operator session, after a read of the live
# store found 214 open findings — a backlog no operator can work through by
# hand, and which nothing in the CLI helps reduce.
#
# READY 2026-08-20 8:43 AM CT. The pre-dispatch review named in the line below
# is the one that gates this flip; it ran, it rewrote the spec, and the sweep
# afterwards exercised the corrected rule by hand across 70 findings. Every
# `file:line` anchor in the plan and tasks was resolved against `a58ec93`, and
# every bare `:NN` reference was expanded to a full path so no implementer has
# to infer which file a line belongs to.
#
# REVISED 2026-08-20 8:10 AM CT by the pre-dispatch review of this spec's own
# first draft. That draft proved "cured" from a finding key appearing in a
# landed spec's text. The review measured the corpus and found the rule unsound:
# 16 open findings are named by more than one spec, and
# `interpreter/ci-failure-never-reaches-an-agent` is named by six — of which 027
# names it in an out-of-scope list, 028 as background and 061 as *regressed*.
# Naming is not fixing, and no amount of date arithmetic recovers the difference.
# US1 exists because of that review; the prose rule survives only as a reported
# candidate class that `--apply` may never touch.
#
# US4 and US5 are the fix for
# `hardening/the-boundary-detector-files-a-sibling-nodes-pytest-cache-as-this-attempts-escape`
# (critical), filed the same morning from the same read.
#
# DO NOT FLIP READY without a pre-dispatch review.
#
# --- OVERRIDE, 2026-09-07, by epic 130 US2 (FR-005) ---
# specs/130-the-boundary-detector-charges-an-attempt-only-for-what-it-wrote
# deliberately reverses US4 scenario 2 — "a sibling worktree is removed during
# the attempt ... a finding is filed naming it ... the behaviour that must
# survive". 073 did not know that the factory itself removes sibling worktrees
# as ordinary housekeeping: `factory/workgraph/workflow.py` `_remove_worktree`
# is called from four sites in the workflow, so this scenario's committed
# control (`tests/test_detector_reports_removals_only.py`, now
# `test_sibling_worktree_removed_files_no_finding`) fired on the factory's own
# normal operation and charged it to whichever attempt happened to be tearing
# down. The inversion lives in that test's docstring; the scenario text, story
# titles, work-graph block and FR bodies here are fingerprint input and are
# untouched by the override.
---

# Feature Specification: the ledger triages what it can prove

**Created**: 2026-08-20

## The gap, stated precisely

`ergane findings` can record a defect, list defects, resolve one by hand and
promote some into a spec. It has no way to answer the question an operator
actually asks after two weeks away: **which of these are still true?**

Measured on the live store at `2026-08-20T12:00Z`:

| | |
| --- | --- |
| findings, all states | 250 |
| open or regressed | **214** |
| open and critical | 110 |
| total occurrences | 340 |

Two hundred and fourteen rows is past the point where a human reads them. So
nobody does, and the ledger stops being the thing the constitution promotes
*from* — a defect class cannot be shown to have "recurred" if no one is counting.

### There is a linkage, and it is not written down anywhere a machine can read

A spec that fixes a finding names that finding's key in its own prose. 072 does
it in frontmatter; everything `ergane findings promote` scaffolds does it by
construction. 76 of the 214 open findings are named by some spec today.

**But naming is not fixing, and the corpus proves it.** Sixteen open findings are
named by more than one spec. `interpreter/ci-failure-never-reaches-an-agent` is
named by six:

| spec | how it names the finding |
| --- | --- |
| 025-ci-red-recovery | its fix |
| 071-a-red-check-tells-the-agent-what-broke | its fix |
| 027-gate-suite-fake-time | an out-of-scope list |
| 028-epic-relaunch-reset | background in a plan |
| 061-the-on-ramp-proves-itself-end-to-end | a note that it is **regressed** |
| 073 (this spec) | an example |

Four of the six would be read as a fix by any text rule, and one of those four
says the opposite. So the fix relation has to be **declared**, not inferred. That
is US1, and everything else rests on it.

### What is decidable once the linkage exists

Applying a declared-fix rule, with each finding's `last_seen` compared against the
commit that flipped the declaring spec to `state: landed`:

| class | count today | provable from |
| --- | --- | --- |
| declared fixed by a landed spec, not seen since | 0 — nothing declares yet | the declaration and the commit date |
| declared fixed, **seen since** | 0 — same reason | the same two facts |
| a landed spec's prose names it, no declaration | **49** | reported only; never applied |
| prose names it and it was **seen since** | **6** | reported as the top of the queue |
| one class filed under many keys | **40** | shared key prefix and a single source |
| everything else | 119 | nothing; a human must read it |

The declared classes are empty on the day this lands, and that is correct — the
back-fill is an operator's judgement, one spec at a time, and the report is what
makes it cheap by handing over the 49 candidates with the line to check.

### The six matter more than the forty-nine

`interpreter/ci-failure-never-reaches-an-agent` is named by `025-ci-red-recovery`,
which landed on 2026-08-13. It has been seen five times since, most recently
2026-08-19. `ci/test-suite-pins-the-operator-dial` is named by
`037-operator-dial-tests`, landed 2026-08-13, seen three times since — most
recently this morning.

A sweep that closed on the name alone would have deleted both. Surfacing "this
was fixed and came back" is worth more than closing forty-nine quiet rows.

### The forty are one alarm tripping itself

Every one is `hardening/agent-worktree-boundary/<epic>/<node>`, filed by
`agent-worktree-detector`, all critical, all open. The detector's own module
docstring says it reports a path "removed or truncated" under the runtime root.
Its comparison reports any difference at all.

Opened up, the 070/us1 finding lists **3,860 changed paths. 3,859 are creations**
(`None -> {...}`). Zero are removals. The single non-creation is `doctor.db`
growing by 4,096 bytes — and the detector is what grew it, because it snapshots
`doctor.db` at attempt start and writes its finding to `doctor.db` at teardown.

Every one of the 3,859 creations is under `worktrees/070-.../us4/` — a
**different node's** worktree, which the detector walks in full and which was
running its own tests concurrently. The paths are `.pytest_cache`, `__pycache__`
and `.pyc`.

So the detector is guaranteed to fire on every attempt under any concurrency
above one, attributing a neighbour's test run to whichever node happens to tear
down. That is why the count exploded on 2026-08-19 and not before.

It is not free. Those **40 rows hold 25.6 MB of the store's 25.9 MB of notes** —
98.9% — and `report`'s upsert rewrites the notes blob on every occurrence.

## User Scenarios & Testing

### User Story 1 - A spec declares which findings it fixes (Priority: P1)

As an operator, a spec states in its frontmatter which findings it closes, so the
fix relation is a declared fact instead of a guess about prose.

**Why this priority**: P1 and it depends on nothing. Every other story's proof
rests on it, and without it the sweep can only ever produce candidates.

**Acceptance Scenarios**:

1. **Given** a spec whose frontmatter carries `fixes:` with a list of finding
   keys, **When** its frontmatter is read, **Then** those keys are available on
   the parsed record — proven by a committed test.
2. **Given** a spec whose frontmatter omits `fixes:`, **When** it is read,
   **Then** the record carries an empty list and the spec is valid — proven by a
   committed test. The key is additive; 68 existing specs omit it.
3. **Given** a spec whose `fixes:` is a bare string rather than a list, **When**
   it is read, **Then** it is refused naming the offending spec — proven by a
   committed test. A scalar where a list belongs is the frontmatter defect this
   repository has already paid for once.
4. **Given** a spec whose frontmatter carries a key that is neither `state`,
   `depends_on_landed` nor `fixes`, **When** it is read, **Then** it is still
   refused — proven by a committed test. The grammar stays closed; this story
   widens it by exactly one name.
5. **Given** any spec in the corpus, **When** `ergane spec validate` runs,
   **Then** its result is unchanged from before this story — proven by a
   committed test over a supplied corpus carrying both forms.

### User Story 2 - A sweep tells the operator what it can prove (Priority: P1)

As an operator returning to a two-hundred-row ledger, `ergane findings triage`
sorts it into classes I can act on without reading every row, and changes
nothing.

**Why this priority**: P1. The report alone is the catch-up mechanism; `--apply`
is a convenience on top of it.

**Acceptance Scenarios**:

1. **Given** an open finding declared by a `state: landed` spec's `fixes:`, whose
   `last_seen` is at or before that spec's landing commit, **When** triage runs,
   **Then** it is reported as fixed and the report names the declaring spec —
   proven by a committed test over a supplied specs tree and a supplied store.
2. **Given** the same finding with `last_seen` **after** the landing commit,
   **When** triage runs, **Then** it is reported as seen after its fix landed and
   is **not** reported as fixed — proven by a committed test. This is the control
   that keeps a live regression out of the closable pile.
3. **Given** a finding declared by a landed spec whose landing commit cannot be
   dated, **When** triage runs, **Then** it is reported as needing a human and is
   **not** reported as fixed — proven by a committed test.
4. **Given** a finding no `fixes:` declares but whose key appears in a landed
   spec's prose, **When** triage runs, **Then** it is reported as a candidate,
   named separately from the declared class, together with every spec whose prose
   names it — proven by a committed test carrying two such specs.
5. **Given** two or more open findings whose keys carry three or more segments,
   share their first two, and share one `source`, **When** triage runs, **Then**
   they are reported as one fragmented class naming the shared prefix and the
   member count — proven by a committed test.
6. **Given** a single open finding with no prefix-sharing sibling, **When** triage
   runs, **Then** it is **not** reported as fragmented — proven by a committed
   test. This is scenario 5's control.
7. **Given** a finding whose `last_seen` is older than the cold threshold with
   exactly one occurrence, **When** triage runs, **Then** it is reported as cold;
   **and given** one inside the threshold, **Then** it is not — proven by one
   committed test carrying both.
8. **Given** any store, **When** triage runs without `--apply`, **Then** the store
   file's bytes are unchanged — proven by a committed test that hashes the file
   before and after.
9. **Given** any store, **When** triage runs, **Then** the class counts sum to the
   number of open and regressed findings, so no row is silently dropped — proven
   by a committed test.

### User Story 3 - The sweep can enact only what was declared (Priority: P1)

As an operator, `ergane findings triage --apply` closes the findings a landed
spec declared it fixed, folds the fragmented classes, and leaves everything else
exactly as it found it.

**Why this priority**: P1. Without it the operator re-derives the same list by
hand, which is the work the report exists to remove.

**Acceptance Scenarios**:

1. **Given** a finding triage classified as fixed, **When** `--apply` runs,
   **Then** its status is `resolved` and its resolution names the declaring spec
   directory — proven by a committed test.
2. **Given** a finding classified as a prose candidate, **When** `--apply` runs,
   **Then** its status is unchanged — proven by a committed test. Prose is not a
   declaration and `--apply` may never act on it.
3. **Given** a finding classified as seen after its fix landed, **When** `--apply`
   runs, **Then** its status, occurrences and `last_seen` are all unchanged —
   proven by a committed test. That class is the top of the operator's queue.
4. **Given** a fragmented class, **When** `--apply` runs, **Then** every member is
   resolved with a resolution naming the shared prefix and the number folded, and
   the report names the surviving class key — proven by a committed test.
5. **Given** a finding classified as cold or as needing a human, **When**
   `--apply` runs, **Then** its status remains `open` and only its notes gain the
   triage annotation — proven by a committed test.
6. **Given** an annotated finding, **When** `--apply` runs a second time, **Then**
   the annotation is not duplicated, and occurrences, `last_seen` and the event
   trail are unchanged — proven by a committed test.
7. **Given** a store where nothing is declared, **When** `--apply` runs, **Then**
   no finding changes status — proven by a committed test. This is the control,
   and it is the state of the live store on the day this lands.

### User Story 4 - The boundary detector reports what it says it reports (Priority: P1)

As an operator, the worktree-boundary detector files a finding when an attempt
removes or truncates something outside its worktree, and stays silent when a
concurrent sibling writes a cache file.

**Why this priority**: P1 and independent of everything above. It is filing
critical findings against every node right now; triage that does not stop the
source cleans a floor while the tap runs.

**Acceptance Scenarios**:

1. **Given** a runtime root where a sibling worktree gains files during the
   attempt, **When** the detector compares at teardown, **Then** no finding is
   filed — proven by a committed test over a supplied runtime root.
2. **Given** a runtime root where a sibling worktree is removed during the
   attempt, **When** the detector compares, **Then** a finding is filed naming it
   — proven by a committed test. This is scenario 1's control, and it is the
   behaviour that must survive.
3. **Given** a runtime root where an evidence store is truncated during the
   attempt, **When** the detector compares, **Then** a finding is filed naming it
   — proven by a committed test.
4. **Given** a runtime root where `doctor.db` merely grows during the attempt,
   **When** the detector compares, **Then** no finding is filed — proven by a
   committed test. The detector writes to `doctor.db` itself.
5. **Given** an attempt that modifies a tracked path in the target repository,
   **When** the detector compares, **Then** a finding is filed exactly as it is
   today — proven by a committed test. This is the half that caught the real
   escapes and it must not be weakened.

### User Story 5 - One class, one key, bounded evidence (Priority: P2)

As an operator, a recurring boundary violation is one row with a count, not one
row per node, and its evidence does not grow without limit.

**Why this priority**: P2 and it depends on US4. Once US4 stops the false
positives the remaining volume is small, but the keying is what turned four real
escapes into forty rows.

**Acceptance Scenarios**:

1. **Given** two attempts on different nodes that both violate the boundary,
   **When** each files its finding, **Then** one row exists with two occurrences
   — proven by a committed test.
2. **Given** such a finding, **When** it is read back, **Then** its refs name the
   epic and node of the attempt that filed it — proven by a committed test.
3. **Given** an attempt that changed more paths than the notes bound allows,
   **When** the finding is filed, **Then** the notes carry at most the bound and a
   count of the remainder — proven by a committed test.
4. **Given** an attempt that changed fewer paths than the bound, **When** the
   finding is filed, **Then** every path appears and no truncation notice is added
   — proven by a committed test. This is scenario 3's control.

## Requirements

- **FR-001**: A spec's frontmatter MAY carry `fixes:`, a list of finding keys the
  spec closes. The parsed record MUST expose it, defaulting to an empty list.
- **FR-002**: A `fixes:` that is not a list MUST be refused naming the spec.
- **FR-003**: The frontmatter grammar MUST stay closed: `fixes` is added to the
  known keys and any other unknown key MUST still be refused.
- **FR-004**: `ergane findings triage` MUST assign every open and regressed
  finding to exactly one class and MUST print per-class counts and members.
- **FR-005**: A finding MUST be classed fixed when a spec whose frontmatter
  carries `state: landed` declares its key under `fixes:`, **and** the finding's
  `last_seen` is at or before the commit that first introduced that state.
- **FR-006**: A finding meeting FR-005's declaration condition whose `last_seen`
  is after that commit MUST be classed as seen after its fix landed, and MUST NOT
  be classed fixed.
- **FR-007**: When the landing commit cannot be dated, the finding MUST be classed
  as needing a human. An undated claim is not a proof.
- **FR-008**: A finding no `fixes:` declares, whose key appears in the prose of a
  landed spec, MUST be classed as a candidate, reported separately from the fixed
  class and naming **every** spec whose prose contains it.
- **FR-009**: Two or more open findings whose keys carry three or more
  slash-separated segments, share their first two, and share one `source` MUST be
  classed as one fragmented class naming that prefix. Key matching MUST be exact
  or segment-bounded, never a bare substring test.
- **FR-010**: A finding whose `last_seen` is older than a threshold and whose
  occurrences is one MUST be classed cold. The threshold MUST be operator-settable
  and MUST default to 14 days.
- **FR-011**: Every finding matching no other class MUST be classed as needing a
  human, and the report MUST show that the class counts sum to the open and
  regressed total.
- **FR-012**: The report MUST name, for each fixed finding, the declaring spec
  directory and the landing date, so the operator can check the claim without
  re-deriving it.
- **FR-013**: `triage` without `--apply` MUST NOT write to the store, and MUST NOT
  run any sweep that would.
- **FR-014**: `--apply` MUST resolve each fixed finding, recording the declaring
  spec directory as the resolution.
- **FR-015**: `--apply` MUST leave a finding classed under FR-006 or FR-008
  entirely unchanged — status, occurrences, `last_seen` and event trail.
- **FR-016**: `--apply` MUST resolve every member of a fragmented class with a
  resolution naming the shared prefix and the number folded, and MUST print the
  surviving class key.
- **FR-017**: `--apply` MUST leave cold and needs-a-human findings at status
  `open`, writing only a triage annotation into their notes.
- **FR-018**: The annotation MUST NOT change occurrences, `last_seen` or the event
  trail, and MUST be idempotent across repeated passes.
- **FR-019**: `--apply` MUST refuse to resolve any finding not in the fixed or
  fragmented classes.
- **FR-020**: The runtime-root comparison MUST report only a path that was removed
  or truncated, as the detector's contract already states. A path created during
  the attempt MUST NOT be a finding.
- **FR-021**: Growth of `doctor.db`, `ledger.db` or `verification.db` MUST NOT be
  a finding; truncation or removal of any of them MUST still be.
- **FR-022**: Generated paths — `__pycache__` directories, `.pytest_cache`
  directories and `*.pyc` files — MUST be excluded from the runtime-root snapshot,
  so a concurrent sibling's test run cannot be attributed to this attempt.
- **FR-023**: The tracked-path half of the detector MUST be unchanged.
- **FR-024**: The detector's finding key MUST be the class
  `hardening/agent-worktree-boundary`, carrying no epic or node suffix.
- **FR-025**: The finding's refs MUST name the epic and node of the attempt that
  filed it.
- **FR-026**: The finding's notes MUST be bounded to at most a fixed number of
  paths plus a count of the remainder.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003]
  persona: opus-closer
US2:
  depends_on: [US1]
  implements: [FR-004, FR-005, FR-006, FR-007, FR-008, FR-009, FR-010, FR-011, FR-012, FR-013]
  persona: opus-closer
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-014, FR-015, FR-016, FR-017, FR-018, FR-019]
  persona: opus-closer
US4:
  depends_on: []
  implements: [FR-020, FR-021, FR-022, FR-023]
  persona: opus-closer
US5:
  depends_on: []
  depends_on_merged: [US4]
  implements: [FR-024, FR-025, FR-026]
  persona: opus-closer
```

The chain US1 → US2 → US3 is real, not merely contentious: US2's proof rule reads
a field US1 creates, and US3 acts on classes US2 defines. The unlanded
code-needing edges (US3 → US2, US5 → US4) are `depends_on_merged`, because the
dependent story must find its dependency's code in its own base tree — a
`depends_on` edge releases on verification, before the code lands, and
dispatching US3 that way parked it behind an operator question on 2026-08-21.
(US2's edge keeps its original `depends_on` form only because both ends are
already landed and editing it would change a landed story's fingerprint.) US4 and US5 are a
separate module and share no file with the first three; US5 changes the same
finding-construction path US4 changes, and its bounded-notes requirement only
makes sense once one row absorbs every occurrence.

## Success Criteria

- **SC-001**: Run `ergane findings triage --db ~/ergane-ops/doctor.db.pre-sweep-2026-08-20`
  against the archived pre-sweep store — 69,840,896 bytes, sha256
  `6272178eb0e08d7401fd595fe3f77cb7a19d41f09e1997bdcdd99622e73f09ac`, deliberately
  kept outside the repository — and paste the output. The candidate class must
  hold at least 40 findings, each naming every spec whose prose contains it.
- **SC-002**: Paste the fixed and seen-after-fix counts from that same run. Both
  must be zero, because no spec in the archive declares `fixes:` — and a run that
  reports a non-zero fixed count against a corpus with no declarations has
  inferred a fix from prose, which FR-008 forbids.
- **SC-003**: Add `fixes:` to one landed spec in a scratch copy of the corpus,
  re-run, and paste the finding moving from candidate to fixed.
- **SC-004**: Run triage twice with no `--apply` and paste `sha256sum` of the
  store from before, between and after. All three must match.
- **SC-005**: Copy the archive, run `--apply` against the copy, and paste
  `ergane findings list --status open | wc -l` before and after. Nothing may be
  resolved except fragmented-class members, and
  `interpreter/ci-failure-never-reaches-an-agent` must still be open.
- **SC-006**: Build a runtime root where a sibling worktree gains a
  `.pytest_cache` during an attempt, run the detector, and paste the silence. Then
  delete the sibling worktree, re-run, and paste the finding.
- **SC-007**: File two boundary findings from two different nodes and paste
  `ergane findings list` showing one row with two occurrences, then paste the
  length of its notes.

## Assumptions

- The prose candidates are not resolved by this spec. An operator session swept
  them by hand on 2026-08-20 using this spec's own classification: of 48
  candidates, **27 were confirmed closed and resolved and 21 were not**, because
  the naming spec said "filed as", "out of scope", "carried, characterized, NOT
  fixed", or in one case named the finding while declaring itself "not a defect
  fix". The same pass folded 43 detector per-node keys into their class. That is
  why the live store now holds 148 open rows rather than 218, and why the
  archived store — which still holds all of them — is the corpus the success
  criteria run against.
- The hand sweep is also the evidence for FR-008. A rule that treated prose as a
  declaration would have closed 21 findings that are open on purpose, including
  two that 056 filed *because it found them* and one that 065 names under a
  heading reading "NOT IN SCOPE".
- Spec state is read from the operator's working tree, which is where every other
  spec reader in this repository reads it. That is a known defect class in its own
  right — see `roadmap/dispatch-is-decided-by-the-operators-working-tree` — and
  fixing it is not in scope. The report must be explicit about which tree it read.
- A `fixes:` entry naming a key the ledger does not hold is not an error. Specs
  and stores move independently, and coupling `ergane spec validate` to a store it
  may not be able to reach would make validation depend on the runtime root.
