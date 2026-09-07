---
state: landed
fixes:
  - hardening/the-worktree-boundary-detector-charges-a-node-with-its-siblings-worktree
  - cli/spec-derive-json-rewrites-the-committed-artifact
  - hardening/the-worktree-boundary-detector-cannot-tell-an-operators-commit-from-an-agent-escaping
# Attested landed 2026-09-07. US1 b82ced5a135f (#441), US2 29362b931757 (#440),
# US3 fe24a5f39f29 (#442), US4 d6c17c8d14d6 (#443) — all four observed on
# ergane-buildout by content, all four on the first attempt, all PASS with no
# retry, no judge failure and no escalation.
#
# THREE FINDINGS, FOUR STORIES, AND THAT IS THE BENIGN DIRECTION. US3 (FR-006,
# the language-shaped list) is a hardening that closes no ledger row, so the
# `fixes:` list is shorter than the story count rather than longer. The half-fix
# shape this repository keeps catching is the opposite one.
#
# THE FIX IS DISCRIMINATION, NOT SILENCE. The risk in a detector spec is that a
# false-positive finding gets closed by reporting less. It was not: the target's
# HEAD is recorded beside the start snapshot, commit-carried paths are compared
# against the tree that HEAD names, and a path written *on top of* an operator
# commit stays charged (FR-007, FR-009). US1 was re-proven live rather than read:
# `spec derive --json` with no output path exits 0, emits a 3-node graph, reports
# no artifact path and writes nothing, while `--output` still writes. The control
# is this repository's own pre-130 checkout, which rewrote six committed
# artifacts on 2026-09-07 at 12:12Z running the same command.
# DRAFTED 2026-09-03 by the operator session, against ergane-buildout at 238b494.
# Every `file:line` in spec.md and plan.md was read from that commit and verified
# to resolve to the symbol named, not recalled.
#
# WHERE THIS CAME FROM. N29, N35 and N36 of the `ergane-web` consolidated
# hand-over. The compound number the consumer measured:
# `hardening/agent-worktree-boundary` stood at 11 occurrences, ALL FALSE — three
# operator edits, two `spec derive` writes, six cross-epic cache churn. On this
# host today the same key reads 90 occurrences at `critical`, last seen
# 2026-09-03.
#
# THE METHODOLOGICAL COST IS THE REAL FINDING, and the consumer wrote it against
# themselves. Chasing this detector as the cause of two dead epics burned three
# wrong diagnoses while the true cause — a stale-branch `PUSH_FAILED` — sat in the
# worker log in plain text the whole time. THIRTY FURTHER NODE-RUNS WERE DESTROYED
# before it was stopped. Their sentence for it: "A `critical` finding is a
# hypothesis. A stack trace is an observation." The fact that this detector was
# *also* genuinely broken made the wrong trail more convincing, not less.
#
# AND IT IS WHY `max_concurrent_epics` HAS STAYED AT 1 FOR AN ENTIRE BUILD — not
# because two epics are unsafe, but because the detector charges one epic for
# another's cache writes. This spec is the precondition for concurrency.
#
# THE SHAPE WORTH KEEPING, in the consumer's words: "the guard was designed
# correctly and its exclusion list was written by someone testing against a Python
# repo." A target-language-agnostic factory needs the list to come from the
# target's own ignore rules — `.gitignore` is right there — rather than from a
# constant. This tree already agrees with that in writing, at
# `factory/activities/roadmap_activities.py:190`.
#
# THIS SPEC KNOWINGLY OVERRIDES A COMMITTED CONTROL TEST. See plan.md trap 1:
# 073-US4 scenario 2 requires that a removed sibling worktree files a finding, and
# says in its own text "this is the behaviour that must survive". It must not
# survive, because the factory itself removes sibling worktrees as ordinary
# housekeeping. 073 did not know that. This spec says so out loud rather than
# quietly deleting the test.
#
# NOT IN SCOPE. This spec does not change what the detector does with a genuine
# escape, does not remove the finding, does not wire the finding into any verdict
# (it is advisory today and stays advisory), and does not clean up the existing
# `.factory-detector/findings.json` backlog.
#
# REFINED 2026-09-04 by the refinement workflow (refinement-2026-09-04); every
# anchor in spec.md, plan.md and tasks.md re-read from ergane-buildout at
# 602a92c. All 49 distinct anchors — 129 citations across the three documents —
# resolved, and none had moved: 057's four landings
# (34 files) touched no file this trio cites, and the last commit to
# `factory/workgraph/detector.py` is still 073's, 2026-08-21. Two anchors were
# wrong in kind rather than in line, and both are corrected below.
#
# THE OVERRIDE IS OF TWO SPECS, NOT ONE, AND THE SECOND ONE IS US4's.
# `specs/011-agent-sandbox/spec.md:191` is US1 scenario 3: an operator editing the
# target repo during an attempt must STILL be reported — "the detector reports
# what happened, and does not try to attribute intent" — and its committed control
# is `tests/test_us1_detector.py:322`. FR-007 reverses it. The drafted spec named
# only 073's sibling-removal control (trap 1) and would have sent US4's
# implementer into an undeclared collision with a landed scenario and a green
# test. Trap 9 now carries it, US4 says it out loud, and `011-US1-S5` — the
# sibling-worktree half of the same scenario list — is named beside 073's.
#
# FR-007 WAS UNDECIDABLE AS WRITTEN. "Authored by the operator" is not a fact
# filesystem state carries; two before/after snapshots have no author column, and
# an implementer told to find one will invent a heuristic. The two classes that
# ARE decidable from state the detector already holds or can cheaply record are
# now named in the FR itself: a change already present in the working tree when
# the attempt began (today's start snapshot is `_committed_state`, the teardown
# snapshot is `_tracked_state`, and the asymmetry is deliberate and documented),
# and a commit that moved the target repository's HEAD during the attempt. What
# stays reported is stated in "What this spec is not" rather than left implied.
#
# US1 WOULD HAVE BROKEN `ergane build ship --json`. Trap 3 said "a blanket guard
# breaks `build ship`" and named the wrong half: `ship_command` passes its OWN
# args namespace to `derive_spec_command`, ship declares `--json` with
# `dest="as_json"` at `factory/cli/nouns/build.py:2134`, and it then REQUIRES the
# artifact on disk. The guard the plan asked for — `--json` and no output path —
# is exactly the shape `ergane build ship --json` produces, so US1 as drafted
# would have made that command raise "derive reported success but wrote no
# artifact". No committed test covers it, so the suite would have stayed green.
# FR-011 and US1-S5 close it.
#
# US3 WAS AIMED AT A WALK US2 REMOVES. FR-006 asked for the exclusion list to come
# from the target's ignore rules; the only place that list is consulted is the
# sibling-worktree walk US2 stops, and the target-repo half already defers to the
# target's rules through `git ls-files --others --exclude-standard`. US3 is now
# the removal and the proof — and US2 is told, in its own slice, not to take the
# constants with it, because a story whose production work a predecessor already
# did arrives with nothing to do and no diff to be judged on.
#
# THE FOUR KEYS ARE KEPT, ALL FOUR, AND ONE OF THEM CARRIES A HAZARD.
# `hardening/agent-worktree-boundary` is the symptom row this detector writes on
# every teardown, not a defect row; the FRs address the cause of all 90 of its
# occurrences, which is why it is declared. But closing it makes the FIRST GENUINE
# ESCAPE AFTER LANDING read as this spec regressing, because a re-report against a
# resolved row flips it to `seen-after-fix`. Trap 7 now says so, and the operator
# sweep is named as the act that must follow.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04): two more committed controls this
# spec breaks are now declared instead of promised green; US1's criteria no longer
# pass against an untouched tree; two green-today scenarios are labelled controls;
# the anchor count and trap 5's opening claim are corrected; four keys unchanged.
# The trio now carries 58 distinct anchors across 172 citations, and the 32 that
# put their symbol on the next source line — checked by the coarse tier only — were
# reflowed onto one line, so the symbol tier now covers every Python citation and
# the next drift is machine-caught.
#
# THE OVERRIDE IS OF FOUR COMMITTED CONTROLS, NOT TWO. The refinement above found
# two (073-US4-S2's test and 011-US1-S3's) and missed two more in the same file.
# `tests/test_us1_detector.py:449` truncates the SIBLING WORKTREE and asserts at
# `tests/test_us1_detector.py:460-462` that the finding names it, so US2 kills it —
# yet US2-S3 and T010 told the implementer it passes unedited. And
# `tests/test_us1_detector.py:386` writes its tracked change BEFORE each of its
# four attempts starts, which is exactly the class FR-007 silences, so US4 kills it
# too. Both are now named in the scenarios, in traps 1 and 9, and in the tasks that
# must edit them. A node told a red test is a control spends the attempt arguing
# with its own acceptance criterion.
#
# US1 COULD HAVE LANDED WITH NO PRODUCTION DIFF. The write at
# `factory/workgraph/cli.py:384` emits `json.dumps(asdict(graph), indent=2)` — the
# same inputs give the same bytes — so "the artifact is byte-identical across the
# call" was green before the guard existed, and the ledger row says so in its own
# control ("the write is unconditional ... content identical but touches mtime").
# US1-S1 now seeds an artifact whose recorded `target_repo` differs from the one
# the invocation derives — the harm the row actually records, which poisoned 064's
# and 073's graphs — so today's unconditional write visibly destroys it; US1-S4
# asserts the absence of the artifact key rather than the truth of it; and T007's
# pasted sums must DIFFER before the guard and match after.
#
# THE SIBLING KEY'S SECOND HALF IS ANSWERED, NOT TAKEN.
# `hardening/the-worktree-boundary-detector-charges-a-node-with-its-siblings-worktree`
# names two halves, and its remedy 2 asks for the shared store files to be excluded
# because `verification.db` appeared in a node's charge sheet. That row was measured
# 2026-08-21 02:20Z; 073's loss-only rule landed the same day at 12:36Z and made a
# store that GROWS silent already. Remedy 2 is deliberately NOT taken: a store the
# attempt truncates or removes stays charged under FR-009, because that one is a
# genuine escape.
#
# ALSO NOT IN SCOPE, AND STILL OPEN:
# `hardening/the-boundary-detector-writes-its-own-findings-into-the-boundary-it-polices-and-files-them-as-a-critical-violation-by-the-node`
# (critical, 1 occurrence, 2026-09-03). The detector writes its snapshot and
# findings into `factory/workgraph/detector.py:381` — `_snapshot_dir`'s
# `<root>-detector/` directory and then reports those files as the node's own
# changes. Nothing here fixes it: `capture_start` writes the snapshot after reading
# the start state, so even US4's working-tree start snapshot leaves this attempt's
# own file reported. It is silent on THIS floor only because `.gitignore:22` ignores
# `.factory-detector/`; on a consumer install that ignores only `.ergane` it fires
# on every node. The operator who sweeps `hardening/agent-worktree-boundary` after
# landing must know that cause remains.
#
# THE COMPILED ARTIFACT IN THIS DIRECTORY PREDATES THE REFINEMENT. Its US1 node
# carries no FR-011, which is the requirement added to stop US1 breaking
# `ergane build ship --json`. `ergane build start` reads that file off disk;
# `build ship` and the roadmap re-derive. Re-derive or delete it before any
# dispatch that reads it — this refinement does not touch compiled artifacts.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04, adversarial round two): the two
# tasks that would have edited a LANDED story's scenario text are rewritten so
# the override lands outside the delta fingerprint; `hardening/agent-worktree-boundary`
# is withdrawn from `fixes:` as the detector's own channel key rather than a
# defect row; US1-S5 no longer asks a committed test to prove a ship; US2-S4 is
# labelled the control it is; and trap 1's `:157-158` is cut to the one
# assertion that actually goes red.
#
# THE OVERRIDE MUST NOT MOVE A LANDED STORY'S FINGERPRINT, AND AS DRAFTED IT
# WOULD HAVE. T009 said "edit 073-US4 scenario 2" and T020 said "edit 011-US1
# scenario 3". A landed story's digest is built from exactly that material:
# `factory/workgraph/landed.py:460` — `_story_parts` normalises the story title,
# `factory/workgraph/landed.py:461` folds in every `scenario.raw_text`, and
# `factory/workgraph/landed.py:475` folds in the bodies of the FRs that story
# implements. `factory/workgraph/delta.py:142` — `derive_delta` subtracts a
# landed story only while the pinned digest still equals the current one, so a
# changed digest REOPENS it as a node to dispatch — on the roadmap's own path
# (`factory/activities/roadmap_activities.py:423` — `_derive_from_git`), not just
# an operator's. Both specs are `state: landed`
# (`specs/011-agent-sandbox/spec.md:2`,
# `specs/073-the-ledger-triages-what-it-can-prove/spec.md:2`), and landed story
# numbers are immutable. FR-005 and FR-007 now require the reversal to be
# recorded where the digest cannot see it — a `#` provenance line inside the
# frontmatter fence, the overriding test's docstring, the commit message — and
# plan.md trap 15 carries the mechanism and the operator's proof.
#
# THE CHANNEL KEY IS WITHDRAWN, AND THE PARAGRAPH ABOVE THAT KEPT IT IS
# SUPERSEDED. `hardening/agent-worktree-boundary` is not a defect row: it is
# `FINDING_KEY` itself, at `factory/workgraph/detector.py:58`, so every finding
# this detector will ever file carries it — including the genuine escape FR-009
# requires to keep firing. Declared, it would have `ergane findings triage`
# classify the row FIXED on landing (`factory/doctor/triage.py:583` —
# `_declared_index` indexes `fixes:` from landed specs) and `--apply` resolve it
# (`factory/doctor/triage.py:864` — `apply_triage`), closing on paper the channel
# this spec exists to make trustworthy; the first real escape afterwards would
# re-report against a resolved row and read as this spec regressing. The
# paragraph above accepted that hazard as a misreading to expect; this one
# refuses to plant it. Three keys remain and each is fixed whole by the FRs that
# own it. The 90 accumulated occurrences are an operator sweep naming this spec
# by hand, which is what trap 7 now says.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04, adversarial round three): the stale
# compiled artifact in this directory is now **step 0 of the operator's
# pre-dispatch sequence** in plan.md, not a provenance line alone —
# `ergane build start` dispatches from that file
# (`factory/cli/nouns/build.py:808` — `start_command`) and its `us1` node's
# `requirement_keys` carry no FR-011, so a dispatch through that verb would send
# US1 to a node the judge never holds to the requirement this refinement added to
# stop it breaking `ergane build ship --json`. The seven citations that called
# `factory/workgraph/cli.py:382` "the write" now name the write itself at
# `factory/workgraph/cli.py:384` and keep the earlier line for the destination it
# assigns. Trap 5's "all four keys" and trap 11's ref counts are corrected to the
# three keys actually declared, and tasks.md's preamble now counts the five
# committed tests that carry edits — it had omitted
# `tests/test_us1_detector.py:322`, which its own T020 body names. No FR, no
# scenario, no story and no key changed.
---

# Feature Specification: the boundary detector charges an attempt only for what it wrote

**Created**: 2026-09-03
**Depends on**: nothing.

## The gap, stated precisely

A `critical` channel is firing on routine, correct behaviour, and it is fed by
four distinct sources — none of them an agent escaping its worktree.

1. **The detector watches the whole runtime root, not the attempt's worktree.**
   `factory/workgraph/detector.py:311` — `_runtime_root_state` walks every node
   directory under the root and skips exactly one — the attempt's own, at
   `factory/workgraph/detector.py:336` — `_runtime_root_state`. Every *other*
   node's worktree is therefore watched, so any two epics whose attempt windows
   overlap attribute each other's incidental writes. **And the factory itself
   supplies the churn**:
   `factory/workgraph/workflow.py:3582` — `_remove_worktree` is called from four
   sites in the workflow, so a sibling node finishing normally charges the running
   node a `critical`. The largest occurrence on this host names 4,210 removed
   paths, all of them one sibling node's worktree.

2. **The exclusion list is a Python-shaped constant.**
   `EXCLUDED_DIR_NAMES` (`factory/workgraph/detector.py:70`) is
   `frozenset({"__pycache__", ".pytest_cache"})` and `EXCLUDED_SUFFIXES`
   (`factory/workgraph/detector.py:73`) is `(".pyc",)`. A JavaScript target's
   `node_modules`, `.vite` and `dist` are not in it, and cannot be, because the
   right list is the target repository's own. That list is consulted in exactly
   one place — the sibling walk of source 1 — and nowhere else.

3. **The factory's own CLI writes into the tree the detector polices.**
   `ergane spec derive --json` writes `specs/<dir>/workgraph.json` as a side effect
   with no output path given — the write at
   `factory/workgraph/cli.py:384` — `derive_command` is unconditional, and its
   destination is assigned one line above it at `factory/workgraph/cli.py:382`;
   the bytes it writes are `json.dumps(asdict(graph), indent=2)`, so the same inputs
   give the same file; `--json` is not consulted until
   `factory/workgraph/cli.py:390` — `derive_command`. So a verb that reads as
   "print, do not persist" persists, and the mutation is then attributed to
   whichever agent happens to be running. **The factory's own CLI produces the
   violation the factory's own detector reports against a third party.** The
   ledger row for it records the sharper harm: run with `--target-repo $PWD` from
   the operator's checkout it rewrites the committed artifact's `target_repo`, and
   both 064's and 073's committed graphs had to be caught and re-derived.

4. **The two snapshots are not the same kind of snapshot.** The start snapshot is
   the *committed* tree — `factory/workgraph/detector.py:279` — `_committed_state`,
   called at `factory/workgraph/detector.py:533` — `capture_start` — while the
   teardown snapshot is the *working* tree,
   `factory/workgraph/detector.py:592` — `compare_and_report`. So every
   uncommitted change already sitting in the target
   repository when the attempt begins is reported at teardown as though the
   attempt made it, and an operator commit during the attempt is reported the same
   way. That is deliberate today and documented as such; it is also the mechanism
   behind the two occurrences that named the constitution and `CLAUDE.md` as
   evidence of an escape, which were the operator's own commits — made while
   following the documented recovery.

The information needed to tell the last of these apart is **already captured and
thrown away**: `factory/workgraph/detector.py:405` — `_write_snapshot` records
`"target_repo"`, `factory/workgraph/detector.py:584` — `compare_and_report` reads
it back into the start state, and the builder it then calls at
`factory/workgraph/detector.py:598` — `compare_and_report` is never given it.

## The rule this spec is asking for

**An attempt is charged only for what that attempt wrote, inside the paths it is
actually policing — and a change the operator or the factory itself made is never
attributed to a running node.**

The cases, complete. "Charged" means a `critical` finding filed against the
running attempt:

| where the change is | what made it | today | after this spec |
|---|---|---|---|
| a tracked path in the target repo | the attempt | charged | **charged, unchanged** |
| a tracked path in the target repo | already dirty when the attempt began | charged | **silent** (FR-007) |
| a tracked path in the target repo | an operator commit during the attempt | charged | **silent** (FR-007) |
| a tracked path in the target repo | `spec derive --json` | charged | **the write no longer happens** (FR-001) |
| a path the target repo ignores | anything | silent | **silent, unchanged** (FR-006) |
| an evidence store at the runtime root, truncated or removed | anything | charged | **charged, unchanged** (FR-009) |
| an evidence store at the runtime root, grown | anything | silent | silent, unchanged |
| inside a sibling node's worktree | anything, including `_remove_worktree` | charged | **silent** (FR-004, FR-005) |

### What this spec is not

It is not a relaxation of the boundary. A genuine escape — an attempt modifying a
tracked path in the target repository, or truncating an evidence store under the
runtime root — still files a `critical` finding with its evidence unchanged.

It is not a claim that the detector can name an author. Two filesystem snapshots
have no author column. The two classes FR-007 excludes are the two that are
decidable from recorded state; an uncommitted write made in the target repository
*during* the attempt by anything other than the attempt is still reported, and
that is the honest limit of a state-difference detector.

It accepts one deliberate loss of observation. After FR-004 the detector can no
longer see an attempt reaching into a *sibling's* worktree — because it never
could tell that apart from the sibling's own work, or from the factory's
housekeeping, which is the whole defect. What prevents that write is a layer
below: the sandbox binds the worktree's parent read-only precisely so sibling
worktrees are not reachable (`factory/workgraph/adapter.py:523` — `_build_argv`,
`factory/workgraph/adapter.py:538` — `_build_argv`).

It is not a promotion of the finding into a verdict. `compare_and_report`'s return
value is discarded today at `factory/workgraph/adapter.py:1177` — `run_attempt`
and `factory/workgraph/adapter.py:1185` — `run_attempt`; the finding gates nothing
and kills nothing, and this spec keeps it that way. Making a false-positive channel
*enforcing* while fixing its false positives is how a fix becomes an outage.

It is not the backlog cleanup. The existing `findings.json` and the 90 accumulated
occurrences are swept separately, once the detector stops firing.

And it does not close the detector's own channel.
`hardening/agent-worktree-boundary` is `FINDING_KEY` at
`factory/workgraph/detector.py:58` — the key every finding this detector will ever
file carries, the genuine escape FR-009 keeps firing included — so it is
deliberately **not** declared in `fixes:`, even though this spec removes the cause
of all 90 of its occurrences. Declaring it would close the channel mechanically on
landing and make the next real escape read as this spec regressing. The accumulated
row is swept by an operator naming this spec by hand, after the row is observed to
stop incrementing (plan.md trap 7).

## User Scenarios & Testing

### User Story 1 - A read-only-looking verb does not write (Priority: P1)

As an operator measuring a work graph, `--json` prints and does not persist.

**Why this priority**: P1 and it depends on nothing. It is the only source of the
false positives that the *factory itself* causes through a verb an operator runs
deliberately, and it is the smallest of the four.

**Independent Test**: Seed a spec directory's artifact with a `target_repo` this
invocation would not derive, run `spec derive --json` with no output path, and check
whether those bytes are still on disk.

**Acceptance Scenarios**:

1. **Given** a spec directory whose committed work-graph artifact differs from
   what this invocation would derive — its recorded `target_repo` naming a
   different path, which is the harm the ledger row records and the way 064's and
   073's committed graphs were poisoned — **When** `ergane spec derive --json` runs
   with no output path, **Then** the graph is printed and the seeded bytes are
   still the file's bytes, proven by a committed test that seeds the differing
   artifact first and therefore fails against today's unconditional write. A
   fixture that derives the artifact and then re-derives it compares one
   deterministic output against itself and is green before this story starts.
2. **Given** the same spec directory, **When** `ergane spec derive --json -o
   <path>` runs, **Then** the graph is written to that path, because an explicit
   output path is a request to persist — proven by a committed test.
3. **Given** the same spec directory, **When** `ergane spec derive` runs **without**
   `--json`, **Then** the artifact is written exactly as today, because the verbs
   that depend on that write must keep working — proven by a committed test.
4. **Given** the `--json` document emitted with no output path, **When** it is
   parsed, **Then** it carries no artifact path at all — the key is absent or null
   — proven by a committed test asserting on the parsed document. Asserted the
   other way round ("it does not name a file that was not written") the criterion
   is true today, because today the file is always written.
5. **Given** `ergane build ship --json`, which passes its own namespace — carrying
   `as_json` and no output path — to the same derive handler and then requires the
   artifact on disk, **When** it runs, **Then** it still resolves the artifact on
   disk and reaches its compiled-graph summary rather than raising "derive
   reported success but wrote no artifact", proven by a committed test that fails
   against a guard keyed on `--json` alone.

### User Story 2 - The detector watches the attempt's own worktree (Priority: P2)

As an operator running two epics, neither is charged for the other's housekeeping.

**Why this priority**: P2 and it depends on nothing. This is the story that makes
`max_concurrent_epics: 2` usable, and it is the largest single source of the
false-positive count.

**Independent Test**: Run an attempt while a sibling node's worktree is created,
written to and removed, and read what the detector files.

**Acceptance Scenarios**:

1. **Given** an attempt running while a **sibling** node's worktree is written to,
   **When** the detector compares at teardown, **Then** no finding is filed for
   the running attempt — proven by a committed test. **This scenario is a
   control**: it is already true through the loss-only rule at
   `factory/workgraph/detector.py:134` — `_is_loss`, so its test is green before
   this story and must stay green after it. What does change in
   `tests/test_detector_reports_removals_only.py:144` — `test_sibling_worktree_gaining_files_files_no_finding`
   is its start-snapshot assertion, and US2-S2 carries that edit.
2. **Given** an attempt running while a sibling node's worktree is **removed** —
   which the factory does as ordinary housekeeping through
   `factory/workgraph/workflow.py:3582` — `_remove_worktree` — **When** the
   detector compares, **Then** no finding is filed, proven by a committed test.
   **This deliberately reverses 073-US4 scenario 2**
   (`specs/073-the-ledger-triages-what-it-can-prove/spec.md:282`) and the
   sibling-worktree half of `specs/011-agent-sandbox/spec.md:198`, both of which
   required the opposite and called it a control. The reversal is recorded as a
   `#` provenance line inside each landed spec's frontmatter fence and in the
   overriding test's docstring; in this diff both specs' scenario text, story
   titles, work-graph blocks and FR bodies are byte-identical, because those four
   are what the delta fingerprints (FR-005).
3. **Given** an attempt that genuinely writes outside its own worktree — a tracked
   path modified in the target repository, or an evidence store at the runtime
   root truncated — **When** the detector compares, **Then** a `critical` finding
   is filed with its evidence unchanged from today's, proven by
   `tests/test_us1_detector.py:249` — `test_agent_modifying_tracked_file_in_target_repo_files_finding`
   passing unedited, and by the store half of
   `tests/test_us1_detector.py:429` — `test_agent_truncating_runtime_root_store_files_finding`
   — its `doctor.db` and `ledger.db` assertions and the read-only assertion at
   `tests/test_us1_detector.py:468` — still passing after the assertion at
   `tests/test_us1_detector.py:460-462`, which requires the finding to name the
   sibling worktree truncated at `tests/test_us1_detector.py:449`, is removed in
   this story's diff. **That removal is the third committed control this spec
   overrides**, and it is 011-US1 scenario 5's sibling half again.
4. **Given** any comparison, **When** the detector reports, **Then** its return
   value still gates nothing, so this story cannot turn an advisory channel into
   an enforcing one — proven by a committed test asserting both call sites in
   `factory/workgraph/adapter.py` discard it. **This scenario is a control**: both
   sites discard the return today
   (`factory/workgraph/adapter.py:1177` — `run_attempt` and
   `factory/workgraph/adapter.py:1185` — `run_attempt`), so the test is green
   before this story and its job is to stay green through the walk change.
5. **Given** the runtime root is deleted outright during the attempt, **When** the
   detector compares, **Then** it still files a finding naming the evidence stores
   it lost, proven by
   `tests/test_us1_detector.py:476` — `test_detector_reports_even_when_runtime_root_is_deleted`
   passing unedited.

### User Story 3 - The detector carries no language-shaped list (Priority: P3)

As an operator building a JavaScript target, my `node_modules` is not an escape,
and no constant in the detector decides that.

**Why this priority**: P3 and it follows US2 because US2 removes the only caller
of the list. It is what makes the detector language-agnostic rather than
Python-shaped, and it is the story that keeps a hand-written list from growing
back.

**Independent Test**: Import the detector and look for a generated-path list; run
an attempt in a target repository whose `.gitignore` covers a generated directory
and read what is filed.

**Acceptance Scenarios**:

1. **Given** the detector module after this story, **When** it is imported,
   **Then** it defines no generated-path exclusion list and no ignore-rule parser
   replaced one — `EXCLUDED_DIR_NAMES`, `EXCLUDED_SUFFIXES` and the walk that
   consulted them are gone, proven by a committed test asserting the names are
   absent from the module.
2. **Given** a target repository whose own ignore rules cover a generated
   directory, **When** an attempt writes into that directory and the detector
   compares, **Then** no finding is filed for those paths — because the surviving
   rule is git's own `--exclude-standard` read in the target repository at
   `factory/workgraph/detector.py:265` — `_tracked_state`, proven by a committed
   test using a `.gitignore` fixture in the target. **This scenario is a
   control**: that mechanism is already in place, so the test is green before this
   story and its job is to stay green through the removal. US3-S1 is the
   criterion the removal has to earn.
3. **Given** a target repository that does **not** ignore a directory, **When** an
   attempt writes into it outside its worktree, **Then** a finding is filed,
   because ignoring is the target's statement and not the detector's guess —
   proven by a committed test that is the same fixture with the `.gitignore` line
   removed.

### User Story 4 - A finding names the repository, and the operator's own work is not it (Priority: P3)

As an operator, my own commit is not filed as an agent escaping its sandbox.

**Why this priority**: P3 and it follows US3 because it edits the same builder. It
is the smallest remaining source and the one that made the channel unreadable,
because it fires on the exact action the documented recovery tells the operator to
take.

**Independent Test**: Make an operator commit in the target repository while a node
runs, and read what the detector files.

**Acceptance Scenarios**:

1. **Given** a change already present in the target repository's working tree when
   the attempt begins, **When** the detector compares at teardown, **Then** no
   finding is filed for that path, proven by a committed test. **This deliberately
   reverses `specs/011-agent-sandbox/spec.md:191` and BOTH of its committed
   controls**:
   `tests/test_us1_detector.py:322` — `test_operator_work_is_reported_and_untouched`,
   and
   `tests/test_us1_detector.py:357` — `test_detector_runs_on_completed_agent_error_timeout_and_killed`,
   whose four iterations each write their tracked change at
   `tests/test_us1_detector.py:386`, before the attempt — and therefore before
   `capture_start` — starts. Both are edited in this story's diff; the fourth
   control this spec overrides is the second of them. 011's own text is not
   edited: the override is a `#` provenance line inside its frontmatter fence, and
   its scenario text, story titles, work-graph block and FR bodies are
   byte-identical in this diff (FR-007).
2. **Given** the target repository's HEAD moves during the attempt because the
   operator committed, **When** the detector compares, **Then** no finding is
   filed for the paths that commit carried, **and** a path the attempt changed on
   top of that commit is still filed — proven by one committed test holding both
   halves.
3. **Given** a finding that **is** filed, **When** it is built, **Then** it names
   the target repository it is about, using the value
   `factory/workgraph/detector.py:405` — `_write_snapshot` already captures and
   `factory/workgraph/detector.py:598` — `compare_and_report` today drops — proven
   by a committed test reading the finding's summary and refs.
4. **Given** a genuine escape by the running attempt, **When** the detector
   compares, **Then** the finding is filed exactly as today with its evidence
   intact, proven by a committed test.
5. **Given** the detector inspects the target repository, **When** it does,
   **Then** it still only reads — it never stashes, checks out, cleans or
   otherwise mutates the operator's tree — proven by a committed test asserting
   the operator's file is byte-identical afterwards.

## Functional Requirements

- **FR-001**: `ergane spec derive --json` with no output path MUST NOT write the
  work-graph artifact.
- **FR-002**: An explicit output path MUST still write, and `spec derive` without
  `--json` MUST write exactly as today.
- **FR-003**: The `--json` document MUST NOT report an artifact path it did not
  write.
- **FR-004**: The detector MUST NOT file a finding against an attempt for changes
  inside another node's worktree, whether those changes are creations, writes or
  removals.
- **FR-005**: FR-004 MUST hold for a sibling worktree **removed** during the
  attempt, deliberately reversing 073-US4 scenario 2, the sibling-worktree half
  of 011-US1 scenario 5, and the landed requirement standing behind both —
  `specs/011-agent-sandbox/spec.md:358`, 011's FR-012, which requires the detector
  to cover "every node worktree other than the attempt's own" and to file a
  critical when any of them is "removed, truncated or replaced" — because the
  factory itself removes sibling worktrees as ordinary housekeeping. That
  reversal MUST be recorded without changing what the delta fingerprints: those
  landed specs' story titles, acceptance-scenario text, work-graph declarations
  and implemented FR bodies MUST stay byte-identical, and the statement of the
  override MUST live in a frontmatter provenance comment, the overriding test's
  docstring and the commit message instead.
- **FR-006**: The detector MUST NOT decide what is generated from a hard-coded,
  language-specific list: `EXCLUDED_DIR_NAMES`, `EXCLUDED_SUFFIXES` and the walk
  that consults them MUST be removed rather than re-implemented, no ignore-rule
  parser or new dependency may replace them, and the surviving rule MUST be the
  target repository's own ignore rules as git already applies them there.
- **FR-007**: A change the running attempt did not make MUST NOT be attributed to
  it, for the two classes decidable from recorded state: a change already present
  in the target repository's working tree when the attempt began, and a change
  carried by a commit that moved the target repository's HEAD during the attempt.
  A path the attempt changed on top of such a commit MUST still be filed. This
  reverses 011-US1 scenario 3 (`specs/011-agent-sandbox/spec.md:191`) and both of
  its committed controls,
  `tests/test_us1_detector.py:322` — `test_operator_work_is_reported_and_untouched`
  and
  `tests/test_us1_detector.py:357` — `test_detector_runs_on_completed_agent_error_timeout_and_killed`.
  As in FR-005, that reversal MUST be recorded without changing what the delta
  fingerprints: 011's story titles, scenario text, work-graph declarations and
  implemented FR bodies MUST stay byte-identical.
- **FR-008**: A filed finding MUST name the target repository it is about, reusing
  the value already captured in the start snapshot.
- **FR-009**: A genuine escape — a tracked path in the target repository modified
  by the attempt, or an evidence store under the runtime root removed or truncated
  — MUST still file a `critical` finding with its evidence unchanged.
- **FR-010**: The detector's report MUST remain advisory: its return value MUST
  continue to gate nothing, and no story here may wire it into a verdict.
- **FR-011**: `ergane build ship` MUST keep working with `--json`: the guard added
  for FR-001 MUST NOT deny the write to a caller that requires the artifact on
  disk, and that caller MUST be exercised by a committed test.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-011]
US2:
  depends_on: []
  implements: [FR-004, FR-005, FR-009, FR-010]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-006]
US4:
  depends_on: []
  depends_on_merged: [US3]
  implements: [FR-007, FR-008]
```

US1 is concurrent with US2: they share no file, US1 editing
`factory/workgraph/cli.py` and `factory/cli/nouns/build.py`, US2
`factory/workgraph/detector.py`.

The two `depends_on_merged` edges are declared rather than left inferred (069-US2
FR-007) and both are file contention on `factory/workgraph/detector.py`: US2
changes which paths the walk visits, US3 removes the walk and the list that pruned
it, and US4 changes what the builder does with what survives. Three concurrent
edits to one walk is the collision shape that passes every PR check and fails in
the merge group. The US2 → US3 edge carries a second reason: US3's production work
is the removal of code US2 leaves unreferenced, so it can only be judged once US2
has landed.
