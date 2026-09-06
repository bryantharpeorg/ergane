---
state: draft
fixes:
  - roadmap/promote-cannot-act-when-no-run-is-live
  - roadmap/unpark-cannot-reach-a-scheduled-run
# DRAFTED 2026-09-04 by the refinement workflow (refinement-2026-09-04) from
# docs/triage-2026-09-03-ergane-web-round3.md § "an-operators-decision-outlives-the-tick-that-missed-it"
# (lines 346-363), against ergane-buildout at 602a92c. Every `file:line` in
# spec.md, plan.md and tasks.md was read from that commit with `sed -n 'Np'` and
# verified to resolve to the symbol named, not recalled.
#
# WHERE THIS CAME FROM. Two ledger rows, minted eleven days apart from the same
# mechanism. `roadmap/promote-cannot-act-when-no-run-is-live` was filed by an
# operator on 2026-08-19; `roadmap/unpark-cannot-reach-a-scheduled-run` by the
# `ergane-web` round-3 triage on 2026-09-03, which took care to say it is a
# different mechanism from the older, resolved
# `roadmap/a-parked-spec-can-never-be-unparked` and must not be closed against
# it. Both are open at `warning`.
#
# WHAT IT COST, MEASURED. The 2026-08-19 report is one sitting: six specs being
# flipped from draft to ready, and *every* `ergane roadmap promote` invocation
# answering `unexpected error (workflow execution already completed)`. The
# arithmetic behind "every" is in the schedule: a tick starts a run that drains
# and exits in about twenty seconds, and the cadence on this floor is three
# hundred. The verb is therefore addressable for roughly one second in fifteen,
# and unusable in exactly the state an operator is most often in — editing specs
# while nothing is dispatching. The fallback that works is editing `state:` in
# the frontmatter by hand, which is the whole complaint: the CLI verb is the
# documented path and the file edit is the one that functions.
#
# NOT IN SCOPE. The pause/resume branch is correct and is not touched. The
# roadmap is not made long-lived, and no `idle_rescan_s` is added to the
# schedule's arguments as a workaround — that would keep one run alive so the
# verbs could reach it, which is treating the symptom by making the roadmap the
# thing that never ends. No new escalation button. No change to what a park
# means or to when a spec is parked. No un-promote verb.
#
# THE MEMO ROUTE WAS CHECKED AND IS CLOSED BY CONSTRUCTION, so this spec does not
# design onto it. `factory/roadmap/schedule.py:270-271` says it in the tree's own
# words: `ScheduleUpdate` has no memo field, so a memo could never be reconciled.
# Durable state on disk is the only route left, and the corpus the roadmap reads
# is already on disk on the same host.
#
# THE TWO KEYS ARE NOT SYMMETRIC, AND THE SPEC SAYS SO RATHER THAN PRETENDING.
# For `promote` a decision is genuinely discarded: a promotion lives only as a
# run's in-memory `_promotions`, and there is no home for it that is not the
# spec's own frontmatter. For `unpark` nothing durable is lost — a fresh tick
# starts with `_parked = {}` and re-runs clone, derivation, preflight and
# onboarding against the document as it now stands, so a fixed spec is retried
# whether or not the operator says anything. The unpark half is therefore a
# refusal that tells the truth, not a second record; US2 exists to make that
# honest instead of leaving a raw RPC error on the operator's terminal. Ten of
# the thirteen requirements are the promote half, which is the ratio the two
# rows deserve.
#
# WHAT THE RE-READ FOUND. Every anchor the triage entry cites still resolves at
# 602a92c except one, which was cited against the wrong class:
# `RoadmapInput.idle_rescan_s` is at `factory/roadmap/workflow.py:280`, not at
# :330 — line 330 is `RoadmapCarryOver`'s field of the same name. Both are
# `None` by default so the entry's conclusion holds, but the citation is
# corrected here and written in the symbol-tier form so the next drift is
# machine-caught. The `break` the entry places at :979 is at :979. Nothing has
# landed on any file this spec touches since the triage: the newest commit on
# `factory/cli/roadmap.py`, `factory/roadmap/*.py`, `factory/worker.py` and
# `tests/test_ergane_status.py` is 126's, from 2026-09-02, a day before the
# triage read them.
#
# THREE HAZARDS THE ENTRY DID NOT NAME, ALL FOUND BY READING THE SUITE.
# (1) `tests/test_roadmap_schedule_discovery.py:593` asserts `promote` is
# *silent* — `(0, "", "")` — so FR-007's printed path deliberately ends a
# control that 046-US2 wrote, and the amendment must not take pause/resume's
# silence with it. (2) That module drives every verb at
# `SPECS_ROOT = "/srv/factory/ergane/specs"`, a path that does not exist, so the
# moment `promote` writes a file those tests must move to a writable root.
# (3) The fake workflow handle's `signal` never raises
# (`tests/test_roadmap_schedule_discovery.py:214`), so the defect this spec
# fixes cannot be reproduced with the fixture as it stands; a test that does not
# extend it proves nothing.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04): an adversarial review refuted the
# first draft on sizing and on two wrong enumerations of the test surface, and
# all of it re-derived from the tree before being fixed.
# STORY SPLIT: US1 carried ten of thirteen FRs and five distinct pieces of work
# — it is split at the writer/reader seam into US1 (the record and the verb) and
# a new US3 (the roadmap reads it, depending on US1 for the derivation
# function). US2 keeps its number and its scope; no story is renumbered.
# INSTRUCTIONS CORRECTED, both invisible to validate because both are a claim
# about which files exist rather than about a line: `read_corpus_activity` is
# registered in six roadmap *test* workers as well as in `factory/worker.py`, so
# trap 8 now names nine sites and the harness whose forgetting presents as a
# hang; and `tests/test_roadmap_prompt_assembly.py:572` patches the `_get_handle`
# seam US2 deletes while resolving `specs_root="specs"` to this floor's live
# `roadmap-specs`, which trap 12 now names as the reason to convert it in the
# same commit.
# CRITERIA AND WORDING: FR-005's patch gate gained the criterion it lacked
# (US3-S3), FR-009 now refuses before any client is opened so the absent-root
# test needs no floor, FR-010 is split by owner because a completed *bare* run
# has no next tick to promise, and `_get_handle`'s removal — with its row at
# `tests/test_ergane_status.py:1546` — is decided rather than left open.
# EVIDENCE: the resolved-ledger-row citation the plan leaned on is replaced by
# the code it was standing in for, and four anchors were reflowed so the symbol
# tier can fire on them. Keys unchanged; holds unchanged; state stays draft.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04): a second adversarial review
# refuted the absent-root test as non-hermetic, and the refutation was
# re-derived from the tree before anything was changed.
# TEST DESIGN CORRECTED: T006's rationale — "an implementation that connects
# first fails here on the attempt" — is false on this floor. `tests/conftest.py`
# isolates only the `ERGANE_*`, `FACTORY_*` and `TELEGRAM_*` names and patches
# no `Client.connect`, so under the tests-first rule the mandatory red run of
# that test would have reached `factory/cli/roadmap.py:201` — `_connect` for
# real; and trap 4's "the root must be named `specs`" rule, carried into a test
# that needs no floor, resolves through
# `factory/roadmap/workflow.py:178` — `roadmap_workflow_id` to `roadmap-specs`,
# this host's live roadmap. US1-S5, FR-009, trap 4 and T006 now prove the
# ordering by stubbing the connect seam and forbid that root name there.
# SIZING CORRECTED: registering US3's activity puts its input record on the
# swept Temporal payload boundary, so `tests/test_temporal_payload_shape.py`
# joins US3's sizing, trap 8 and T026.
# EVIDENCE WORDING: T021's capture now says what closing
# `roadmap/unpark-cannot-reach-a-scheduled-run` means — a refusal that explains,
# plus US2-S3's control that nothing durable was lost — so a later triage cannot
# read the row as "unpark now reaches a scheduled run".
# ANCHORS: ten citations that resolve inside a named Python symbol were reflowed
# into the symbol-tier form so their next drift is machine-caught. Keys
# unchanged; holds unchanged; state stays draft.
---

# Feature Specification: an operator's decision outlives the tick that missed it

**Created**: 2026-09-04
**Depends on**: nothing.

## The gap, stated precisely

`ergane roadmap promote` and `ergane roadmap unpark` address a **run**. On a
scheduled floor there is almost never a run to address, and when the verb misses,
the operator's decision is not deferred — it is discarded, and what they are told
about it is a Python exception.

The chain is five steps:

1. Both verbs resolve a workflow handle and signal it.
   `factory/cli/roadmap.py:397` — `roadmap_promote_command` is three lines:
   `_get_handle`, then `handle.signal("promote_spec", args.spec)`.
   `factory/cli/roadmap.py:403` — `roadmap_unpark_command` is the same shape.
2. The handle may name a run that has already completed.
   `factory/cli/roadmap.py:334` — `_handle_for` refuses on exactly one condition,
   `factory/cli/roadmap.py:336` — `_handle_for`: that no run id could be resolved
   at all. A closed run has an id like any other, and neither resolver filters on
   execution status — `factory/roadmap/discovery.py:443` — `_newest_run` lists with
   no status predicate, and `factory/roadmap/discovery.py:364` —
   `_find_bare_workflow` accepts any id whose `describe()` answers, which a closed
   workflow's does.
3. On a schedule, every run is a completed run for almost the whole interval.
   `factory/roadmap/schedule.py:75` — `arguments` passes no `carry_over` and no
   `idle_rescan_s`; `factory/roadmap/workflow.py:280` — `RoadmapInput` defaults
   `idle_rescan_s` to `None`, so `factory/roadmap/workflow.py:979` — `_run_inner`
   takes the `break` and the run returns. Each tick starts a **new** workflow
   (`factory/roadmap/schedule.py:230` — `_schedule_for`), whose
   `factory/roadmap/workflow.py:587` — `__init__` begins with an empty
   `_promotions`, repopulated only from the carry-over at
   `factory/roadmap/workflow.py:815` — `_run_inner` — and a schedule tick carries
   none.
4. So the signal lands on a completed run and nothing catches it. The guard sweep
   records the fact: `tests/test_ergane_status.py:1549` and
   `tests/test_ergane_status.py:1550` are `roadmap_promote_command: set()` and
   `roadmap_unpark_command: set()` — zero guard clauses — so the `RPCError` falls
   through to `factory/cli/errors.py:69` — `run_cli` and prints
   `ergane: unexpected error (...); re-run with --debug for the traceback`.
5. And the decision has nowhere else to go. A promotion exists only as a run's
   `_promotions` (`factory/roadmap/workflow.py:621` — `promote_spec`), read by
   `factory/roadmap/workflow.py:1110` — `_apply_promotions`. The one alternative
   channel a schedule could carry is closed by construction:
   `factory/roadmap/schedule.py:270` — `create_schedule` records that
   `ScheduleUpdate` has no memo field, so a memo could never be reconciled.

**The asymmetry is the tell.** `pause` and `resume` were taught this exact lesson
by 046-US2 and act on whatever owns dispatch —
`factory/cli/roadmap.py:355` — `roadmap_pause_command` and
`factory/cli/roadmap.py:372` — `roadmap_resume_command` both branch on
`location.owner is RoadmapOwner.SCHEDULE`. `promote` and `unpark` were left
addressing the run, and `pause`'s docstring even states the reason the run is the
wrong target. The reasoning is already in this file, applied to two verbs out of
four.

**And the two halves are not the same defect.** A promotion is *lost*: there is no
file-independent home for it, so the operator's only working move is editing the
frontmatter by hand. A park is not lost: the next tick begins with `_parked = {}`
and re-runs every pre-dispatch check against the document as it now stands, so a
fixed spec is retried whether or not anyone unparks it. `unpark` on a schedule is
a verb with nothing to spend — which is a sentence worth printing, not a
traceback.

## The rule this spec is asking for

**A promotion is written down where the next pass will read it, before any signal
is attempted; and a verb that can only reach a run says what owns dispatch
instead of printing a Temporal exception.**

The cases, complete:

| verb | what owns dispatch | a run is live | result |
|---|---|---|---|
| `promote` | schedule | either | recorded durably; no run is signalled; the next pass reads it |
| `promote` | bare workflow or run | yes | recorded durably **and** signalled — today's signal, unchanged |
| `promote` | bare workflow or run | no, it has completed | recorded durably; "no live run to tell"; exit 0 |
| `promote` | nothing found | — | today's refusal naming every rung, unchanged |
| `promote` | not yet resolved | — | specs root absent or unwritable: refuse naming the path before a client is opened, write nothing |
| `unpark` | schedule | no, it has completed | one sentence naming the schedule and the next tick; nothing written; exit 0 |
| `unpark` | bare workflow or run | no, it has completed | one sentence naming the run that ended and `ergane roadmap start`; nothing written; exit 0 |
| `unpark` | any | yes | today's signal, silent, exit 0 |
| `unpark` | schedule that has started no run | — | today's refusal naming the schedule and the run prefix, unchanged |

### What this spec is not

It is not a second authority over a spec's state. The frontmatter stays the
authority of record: `factory/roadmap/workflow.py:1110` — `_apply_promotions`
already applies a promotion only while the spec's current state is `draft`, so an
edit to `ready`, `deferred` or `landed` makes the record moot without anyone
clearing it. The record covers the gap the signal was invented to cover; it does
not replace the file.

It is not the ledger row's other remedy. That row offers two directions —
"promote should write the frontmatter and let the next pass read it, or it should
say plainly that no run is live" — and the first is rejected here on purpose. The
frontmatter is a tracked document that a human reads and a reviewer diffs, and a
verb that edits it makes the CLI a second author of the spec: the flip an operator
performs by hand is a commit with a message, while a CLI write would land as an
unstaged edit nobody attributed. It would also be strictly stronger than the
signal it replaces, because the signal is spent by one run and a frontmatter edit
is permanent. The record is deliberately the weaker thing: it only ever matters
while the spec is still `draft`, so the file always wins.

It is not an un-promote verb, and that absence is a decision rather than an
oversight. Today a mistaken promotion dies with the run that received the signal;
after this spec it survives until the frontmatter leaves `draft`, which is a real
cost and is stated here rather than discovered later. The operator's remedy is the
move they already make: edit `state:` to `deferred` — or to `ready`, if the
promotion was right — and the record is moot. A verb that deleted a line from a
hidden file would be a second way to do what the file already does, with its own
refusals to design; if an operator asks for it, it is its own spec.

It is not a durable park. Nothing durable is lost when an unpark misses, and
inventing a park record to make the two verbs look alike would create state whose
only job is to be cleared.

It is not a change to pause or resume, to what a park means, or to the schedule's
arguments. In particular it does not add `idle_rescan_s` to the schedule so that a
run stays alive to be signalled: that keeps one workflow running forever to avoid
writing one file.

It is not a widening of the corpus. The record lives where the corpus read already
refuses to look, and a specs root with no record behaves exactly as it does today.

## User Scenarios & Testing

### User Story 1 - A promotion is written down before it is signalled (Priority: P1)

As an operator promoting a draft while the floor is between ticks, my decision is
recorded rather than lost to a run that ended before I typed the command, and the
command tells me where it went.

**Why this priority**: P1 and it depends on nothing. This is the half where a
decision is genuinely discarded, and the half with no working alternative but a
hand edit to the frontmatter. It also introduces the record's path derivation,
which US3 reads, and the ownership branch US2's sentence is written against.

**Independent Test**: Run `ergane roadmap promote` against a scheduled floor whose
runs have all completed, then read the record on disk and confirm no signal was
sent.

**Acceptance Scenarios**:

1. **Given** a schedule owns dispatch and its newest run has completed, **When**
   the operator runs `ergane roadmap promote <specs-root> --spec <dir>`, **Then**
   the command exits 0, the record under the specs root names that spec dir, the
   directory holding it also carries a `.gitignore` ignoring its own contents, the
   stdout names the absolute path written, and no workflow was signalled — a
   committed test asserts the file's parsed contents and that the client recorded
   zero signals.
2. **Given** the same directory named once relatively and once absolutely,
   **When** the record is written through one spelling and read through the other,
   **Then** both resolve to one file, asserted by a committed test that compares
   the two resolved paths and reads back what the other wrote.
3. **Given** a bare workflow owns dispatch and its run is live, **When** promote
   runs, **Then** the record is written **and** `promote_spec` is signalled to that
   workflow, so the pass in flight still acts — a committed test asserts both, and
   it is the control that this story did not quietly stop signalling.
4. **Given** a run that has completed, **When** promote runs and the signal is
   refused, **Then** the command exits 0, its stderr contains no `unexpected
   error` text, and its stdout says the promotion was recorded and that no live
   run could be told — asserted by a committed test whose fake handle raises the
   refusal the real client raises.
5. **Given** a specs root that does not exist, **When** promote runs, **Then** the
   command refuses with one line naming that path, creates no directory and no
   file, and refuses before any Temporal client is opened — asserted by a
   committed test that replaces `factory/cli/roadmap.py:201` — `_connect` with a
   stub raising on any call, then asserts the refusal and that the stub was never
   called — and the refusal is an operator refusal rather than the `unexpected
   error` text.
6. **Given** a specs root that holds the record directory, **When** the corpus is
   read, **Then** `read_roadmap` returns the same roadmap it returns for a root
   without it and the doctor's spec read reports no extra spec, proven by a
   committed test over both readers, so the record is invisible to the corpus by
   name rather than by luck.

### User Story 2 - `unpark` answers for the tick that already re-checked the spec (Priority: P2)

As an operator who has just fixed a parked spec, the unpark verb tells me what
owns dispatch and what has already happened, instead of handing me a Temporal
exception.

**Why this priority**: P2 and it needs nothing US1 produces, but it edits the same
two files US1 does. It is the smaller half on purpose: nothing durable is lost
when an unpark misses, so the whole remedy is a sentence that names what owns
dispatch and what it means for this operator's spec.

**Independent Test**: Run `ergane roadmap unpark` against a scheduled floor whose
newest run has completed, and read the exit code, the stdout and the stderr.

**Acceptance Scenarios**:

1. **Given** a schedule owns dispatch and its newest run has completed, **When**
   the operator runs `ergane roadmap unpark <specs-root> --spec <dir>`, **Then**
   the command exits 0, its stderr contains no `unexpected error` text, and its
   stdout names the owning schedule, states that a fresh run starts with no parks,
   and states that the next tick re-checks the spec — asserted by a committed test
   whose fake handle raises the refusal a completed run raises.
2. **Given** a bare workflow owns dispatch and its run is live, **When** unpark
   runs, **Then** `unpark_spec` is signalled to that workflow with the spec dir as
   its argument and the command is silent at exit 0, byte-identical to today — a
   committed test asserts the signal list, the signal's argument, the empty stdout
   and the empty stderr, and it is the control that this story changed only the
   missing-run path.
3. **Given** an unpark on a scheduled floor, **When** the command returns,
   **Then** no promotions record and no park record exist under the specs root —
   asserted by a committed test that lists the directory, because the tempting
   symmetry with US1 would create durable state whose only job is to be cleared.
4. **Given** a schedule that owns dispatch and has started no run at all, **When**
   unpark runs, **Then** today's refusal naming the schedule and the run prefix is
   unchanged, asserted by a committed test — the missing-run case already had an
   honest answer and this story does not reword it.
5. **Given** the guard sweep's expectation table, **When** the sweep runs, **Then**
   the guard set it discovers for `roadmap_unpark_command` is non-empty and equal
   to the table's row, and a committed test asserts that a deliberately stale row
   is reported as a mismatch — the pair cannot pass while the verb still catches
   nothing, which is what makes the row load-bearing rather than decorative.
6. **Given** a bare workflow owns dispatch and its run has completed, **When**
   unpark runs, **Then** the sentence names that run as ended and names
   `ergane roadmap start` as what makes a next pass happen, and it does **not**
   promise a next tick — asserted by a committed test that compares the two owners'
   sentences and fails if they are the same string, because there is no schedule
   on this floor to start anything.

### User Story 3 - The roadmap reads the record on its next pass (Priority: P1)

As the roadmap, I begin each pass by reading the promotions an operator recorded
while I was not running, so a decision taken between ticks is acted on at the next
one.

**Why this priority**: P1, and the half that makes US1 worth landing — a record
nothing reads is a file. It is a separate story because it is a separate node: it
touches the workflow, the worker and every test that builds a roadmap worker, and
shares no production file with US1's CLI-and-module diff.

**Independent Test**: Seed a record naming a draft spec under a corpus, run one
roadmap pass over it, and read the run's status document.

**Acceptance Scenarios**:

1. **Given** a record naming a draft spec and a roadmap run that reads that
   corpus, **When** the run completes one pass with no signal sent and no
   carry-over supplied, **Then** the promotion is applied for that pass and the
   run's `roadmap_status` document reports `promoted` true for that spec, proven
   by a committed test over the workflow.
2. **Given** a run whose record names one draft spec, **When** a second spec is
   promoted by signal mid-pass, **Then** both promotions are applied and neither
   source is dropped, proven by a committed test that asserts `promoted` true for
   both spec dirs — the seed unions into the promotions already held rather than
   assigning over them.
3. **Given** the seeding block this story adds, **When** its source is read,
   **Then** the new activity is scheduled only inside a `workflow.patched(...)`
   branch, asserted by a committed test that reads the source of the seeding block
   and fails when the call is reached unguarded, because this workflow is declared
   `AUTO_UPGRADE` and a run in flight replays its history under the new code.
4. **Given** the activity that reads the record, **When** the worker's activity
   list is asserted, **Then** it contains that activity, proven by a committed
   test over `factory/worker.py`'s list; and the diff registers the same activity
   in each of the six roadmap test workers plan.md names, so no roadmap
   environment test schedules an activity its own worker does not serve.

## Functional Requirements

- **FR-001**: The promotions record MUST live at a path derived from the specs
  root, and the writer and the reader MUST resolve the same absolute file whether
  the specs root is spelled relatively or absolutely.
- **FR-002**: `ergane roadmap promote` MUST write the promotion to that record
  before it attempts any signal, so a decision is never lost to a run that cannot
  receive it.
- **FR-003**: The record MUST sit in a directory that the corpus read already
  skips (`factory/roadmap/models.py:440` — `read_roadmap`) and that the doctor's
  spec read already skips (`factory/doctor/triage.py:254` — `read_spec_records`),
  and creating it MUST also write a `.gitignore` ignoring the directory's
  contents, so a version-controlled corpus never acquires a tracked promotion.
- **FR-004**: The roadmap MUST seed its promotions from the record on every corpus
  pass, unioned with promotions already held from the carry-over or from a signal,
  and MUST NOT drop either source.
- **FR-005**: That read MUST be gated by `workflow.patched(...)` in the shape
  `factory/workgraph/workflow.py:1826` — `_run_node` already uses, because the
  roadmap is declared `AUTO_UPGRADE` at `factory/roadmap/workflow.py:528-530` and a
  run in flight replays its own history under the new code; and a committed test
  MUST assert the gate from the source, so an unguarded call cannot pass.
- **FR-006**: The read MUST be a registered activity in the worker's activity list
  (`factory/worker.py:197`), asserted by a committed test, and MUST also be
  registered in every test module that builds a roadmap worker from a hand-written
  activity list, so no roadmap workflow — in production or in a test environment —
  can schedule an activity no worker serves.
- **FR-007**: `promote` MUST print the absolute path of the record it wrote and the
  spec it recorded. The silence assertion at
  `tests/test_roadmap_schedule_discovery.py:593` — `test_bare_workflow_promote_signals_the_workflow`
  MUST be amended for `promote` alone, and the pause/resume silence control at
  `tests/test_roadmap_schedule_discovery.py:575` — `test_bare_workflow_pause_and_resume_signal_the_workflow_silently`
  MUST be left exactly as it stands.
- **FR-008**: When a schedule owns dispatch, `promote` MUST NOT signal any run.
  When a run owns dispatch, `promote` MUST still signal `promote_spec`; a signal
  refused because that run has completed MUST be reported as recorded-but-not-
  signalled at exit 0 and MUST NOT reach `factory/cli/errors.py:69` — `run_cli`'s
  unexpected-error text. Any other RPC failure MUST still refuse as a transport
  error.
- **FR-009**: `promote` MUST refuse, naming the path, when the specs root does not
  exist or the record cannot be written, and MUST create nothing in that case. The
  absent-root refusal MUST happen before a Temporal client is opened, so an
  operator's typo costs no round trip; and the committed test of that ordering
  MUST prove it by stubbing `factory/cli/roadmap.py:201` — `_connect` and
  asserting the stub was never called, not by relying on a real connection
  failing, because nothing in the suite blocks one.
- **FR-010**: `unpark` against a run that has completed MUST exit 0 rather than
  surfacing the raw `RPCError`, and MUST print one sentence chosen by what owns
  dispatch: when a schedule owns it, naming that schedule, that a fresh run carries
  no parks, and that the next tick re-checks the spec; when a bare workflow or an
  unowned run owns it, naming that the run has ended and the park died with it, and
  naming `ergane roadmap start` as what makes a next pass happen. It MUST NOT
  promise a next pass on a floor where nothing will start one.
- **FR-011**: `unpark` against a live run MUST still signal `unpark_spec` with the
  spec dir as its argument, silently at exit 0, and `unpark` MUST NOT write the
  promotions record or any park record.
- **FR-012**: The guard sweep's expectation table (`tests/test_ergane_status.py:1542`)
  MUST name exactly the classes `roadmap_promote_command` catches, and if that
  guard names a transport class the verb MUST also appear in the anti-vacuity list
  at `tests/test_ergane_status.py:1841`.
- **FR-013**: The same table MUST name exactly the classes `roadmap_unpark_command`
  catches — a non-empty set, under the same anti-vacuity rule — a committed test
  MUST assert that a stale row is reported as a mismatch, and if `_get_handle`
  loses its last caller and is removed, its row MUST be removed with it so the
  table still mirrors the module.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-007, FR-008, FR-009, FR-012]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-010, FR-011, FR-013]
US3:
  depends_on: [US1]
  concurrent_with: [US2]
  implements: [FR-004, FR-005, FR-006]
```

Two edges, and they are different kinds on purpose. US3 carries a **pass-edge** on
US1 because it is a code dependency and not a textual one: the seeding activity
reads the record through the path derivation FR-001 puts in
`factory/roadmap/promotions.py`, so US3 cannot compile against a tree that lacks
it. US2 carries a `depends_on_merged` and no pass-edge: its whole change is a
refusal path in one CLI function, and it needs nothing US1 produces — but both
stories edit `factory/cli/roadmap.py` and both change a row in the guard sweep's
expectation table in `tests/test_ergane_status.py`, and US2's sentence is written
against the ownership branch US1 introduces. That merged edge buys a clean base
for the second diff rather than freedom from contention, and it is declared rather
than left to be inferred (069-US2 FR-007).

US3 declares `concurrent_with: [US2]`, which is an override of an inferred edge
and not a wish. The two stories are ordered only if they *write* the same file,
and they do not: US2 writes `factory/cli/roadmap.py`, `tests/test_ergane_status.py`,
`tests/test_roadmap_schedule_discovery.py` and
`tests/test_roadmap_prompt_assembly.py`; US3 writes `factory/roadmap/workflow.py`,
`factory/worker.py` and the roadmap test harnesses. The two files the inference
sees in both slices are *cited*, not edited — US2's last task reads
`factory/roadmap/workflow.py` to confirm it needed no change, which is the control
that the unpark half is a sentence and not a store, and US3 cites the guard
sweep in `tests/test_ergane_status.py` only as the shape a source-derived
assertion takes. Deleting those citations to quiet the inference would cost the
implementer two of the things this spec knows, so the edge is declared away
instead.
