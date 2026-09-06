---
state: draft
fixes:
  - verify/an-operator-cannot-correct-a-running-epics-context-because-the-worktree-is-pinned-at-dispatch
# DRAFTED 2026-09-04 by the refinement workflow (refinement-2026-09-04) from
# docs/triage-2026-09-03-ergane-web-round3.md § "an-operator-correction-reaches-a-running-node-or-says-it-cannot"
# (lines 329-345), against ergane-buildout at 602a92c. Every `file:line` in
# spec.md and plan.md was read from that commit with `sed -n 'Np'` and verified
# to resolve to the symbol named, not recalled.
#
# WHERE THIS CAME FROM. N21 of the `ergane-web` round-2 hand-over, filed
# 2026-08-29 from a live build, closed against 118 on 2026-09-02 and REOPENED as
# `regressed` on 2026-09-03 when the round-3 triage found the closure did not
# hold. The row names three asks; 118 built one of them.
#
# WHAT IT COST, MEASURED BY THE CONSUMER. The operator diagnosed a missing fact,
# wrote it into the standards document, landed it on the landing branch, and
# waited. The live worktree had zero occurrences of the new text, and three
# further attempts each re-read the same stale document lacking the one fact
# they needed. Three attempts spent on a correction that had already been made.
#
# THE LEDGER ROW IS WRONG ABOUT WHICH HALF SURVIVED, AND THAT IS THE FIRST TRAP.
# The reopen note lists ask (1) — "re-read standards per attempt from the landing
# branch" — as NOT BUILT. It is built: `resolve_standards`
# (factory/activities/agent_activities.py:1022) runs per attempt from the landing
# head, and its own docstring names this defect as the thing it closes. What
# survives is ask (2), a lever, and ask (3), the words. Those are US1 and US2. An
# implementer who reads the ledger row as the specification will rebuild 118.
#
# THE MECHANISM ALREADY EXISTS. `sync_with_target`
# (factory/workgraph/worktree.py:1316) merges the landing head into the node
# branch inside its worktree — merge, never rebase, no force, no reset — and
# returns conflicted files as data. It is reachable from exactly one place: the
# landing-recovery path, after a merge-queue rejection. This spec is a route and
# a sentence, not an implementation.
#
# NOT IN SCOPE. The worktree is not un-pinned by default — that is 118 FR-004/R5
# and 002 FR-010, both deliberate, and both stated in the code at
# factory/workgraph/worktree.py:420-441. The spec, plan and tasks do not become
# per-attempt reads. The free-rebase and recovery-cycle accounting on the landing
# path is not touched. No fifth `EscalationChoice` member is added: the lever is
# a CLI verb, not a button. Conflicts are not resolved for the operator, and no
# debugger persona is handed the tree the way the landing path hands it one.
#
# THE KEY IS DECLARED WHOLE, DELIBERATELY. One key, fifteen FRs. Ask (1) already
# ships, so US1 (asks 2) and US2 (ask 3) finish the row rather than half-fixing
# it — the shape the 2026-09-02 sweep got wrong on 100, 092 and this very
# finding. If a reviewer disagrees that (1) is built, the correct act is to leave
# the key undeclared and re-report, not to widen this spec's scope. One deviation
# from the row's literal wording, stated here so the next triage reads the answer
# instead of re-deriving it: ask (2) asks for `ergane build refresh <epic>
# [node]` that REBASES "with the same free-rebase accounting"; this spec ships
# `ergane build resync <epic-id> <node-id>`, a MERGE (FR-004) with the landing
# path's accounting deliberately untouched (FR-009), because a rebase rewrites a
# branch the merge queue may still be deciding on and because a courtesy that
# spends recovery cycles is a lever the operator cannot afford to pull. Same ask,
# answered with the mechanism the tree already has.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04) after an adversarial review:
# FR-005 now binds the pin to the object the NEXT ATTEMPT is measured from, not
# only to the two record fields (US1-S2, plan trap 4); a conflicted re-sync's
# cost is made contractual — the tree keeps its markers and the node's remaining
# rungs run against them, said in the outcome, in `build status`, in the truth
# table and in § "What this spec is not" (FR-006, FR-010, plan trap 10);
# FR-010's readout gained the acceptance scenario and the test it lacked
# (US1-S8, T009a, T016), so the title's "or says it cannot" is now falsifiable
# from the diff; FR-007 names where a re-sync refusal is written instead of
# borrowing a helper that wants a branch and a provenance string; US1-S3 drops
# the git-reachability clause the scripted test world has no subject for and
# keeps it where it is measurable, in the operator sequence; US2-S2 and US2-S3
# gained the **When** the house grammar wants; four enclosing-symbol anchors now
# cite their definition line so the next drift is machine-caught. No FR was
# added or removed, no story was split, and `fixes:` is unchanged.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), second pass, after a further
# adversarial review: US1-S2 no longer asserts over `read_worktree_diff`, which
# the declared scripted world neither stubs
# (`tests/test_external_completion.py:437-445`) nor can reach — its criteria
# carry no scenarios (`tests/test_external_completion.py:465`), so
# `factory/verify/models.py:977` — `judge_required` is False on every attempt
# however the gates are scripted, and an assertion over zero calls would have
# passed vacuously on this story's most important control; the pin's second
# clause is now proved from the base on the verification row
# `factory/workgraph/workflow.py:2672` writes, which that world records for
# real. FR-011 and FR-015 no longer say the tree "has not moved since":
# `_CHOICE_EFFECTS` is keyed by choice, not by escalation site, so
# `factory/workgraph/workflow.py:4178` — `_escalate_landing` renders the same
# RETRY line about a pin `factory/workgraph/workflow.py:3734-3736` has already
# moved, and both sentences now name that mover beside the re-sync (US2-S1,
# US2-S5, plan trap 8). § Sizing says the scripted world is imported and
# subclassed rather than copied, and names what is dropped first if US1's diff
# approaches the bound. No FR was added or removed, no story was split, `fixes:`
# is unchanged, and the state is still draft.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), third pass, after a further
# adversarial review: FR-013 and US2-S3 no longer promise that ending the epic
# makes the roadmap rebuild the spec — a child that finishes with a FAILED or
# KILLED node is filed as finished-but-not-landed by
# `factory/roadmap/workflow.py:1416` — `_landed_status_for` into the map
# `factory/roadmap/workflow.py:864-871` excludes from `dispatchable`, carried
# across continue-as-new by `factory/roadmap/workflow.py:302` —
# `RoadmapCarryOver`, and a hand-started epic has no roadmap owner at all, so
# the flat claim fails the same test trap 8 applies to the other half of that
# sentence; US1-S2 and FR-005 now prove the record half through the
# `factory/workgraph/workflow.py:860` — `epic_status` query, because
# `record.base_ref` has no reader outside the landing path's own comparison
# (`factory/workgraph/workflow.py:3696`) and its write is a diff-only
# obligation. The plan gained the neighbour it had missed — 126-US2
# (`8d5102e`, 2026-09-02) put `archive_and_clear_remote_branch` on every
# terminal path and did not stub it in the scripted world US1 imports, so T001
# now appends two stubs — plus a trap for the roadmap sentence, the attempt
# report in § Sizing's arithmetic, and a worker restart before the operator
# sequence (the passthrough-import finding, which this spec does not fix and
# does not declare). Two anchors were corrected: the judge guard is
# `factory/workgraph/workflow.py:2625`, and the docstring quoted in the plan is
# `factory/workgraph/worktree.py:1332-1339`. No FR was added or removed, no
# story was split, `fixes:` is unchanged, and the state is still draft.
---

# Feature Specification: an operator correction reaches a running node or says it cannot

**Created**: 2026-09-04
**Depends on**: nothing.

## The gap, stated precisely

An operator watching a node fail the same way three times does the obvious thing:
they fix the document the agent is reading and let the next attempt pick it up.
For everything except one document, that correction cannot arrive, and nothing
tells them so.

The chain is five steps:

1. A node's worktree is prepared **once**, before its attempt loop.
   `factory/workgraph/workflow.py:1744` is the only `prepare_worktree` call in
   the node lifecycle; `factory/workgraph/workflow.py:1758` stores the result on
   the record, and every later attempt reads that stored value rather than
   preparing again.
2. Preparation is idempotent by construction.
   `factory/workgraph/worktree.py:362` — `ensure` says so in its own docstring at
   `factory/workgraph/worktree.py:371-375`: "an existing directory is returned
   as-is, untouched — no fetch, no rebase, no reset". The currency test beside it
   is explicit about when it runs —
   `factory/workgraph/worktree.py:420-441`: "Measured only here, on the
   preparation path — never between attempts (118 FR-004, R5)".
3. Exactly one channel escapes the pin.
   `factory/activities/agent_activities.py:1022` — `resolve_standards` reads the
   standards document from the landing head per attempt, executed inside the
   attempt loop at `factory/workgraph/workflow.py:1826`. Everything else the
   agent reads is the dispatch-time copy: the tree itself, and the spec, plan and
   tasks that `factory/workgraph/workflow.py:1013` loads once per epic.
4. The mechanism a correction would need already exists and is wired to one
   caller. `factory/workgraph/worktree.py:1316` — `sync_with_target` fetches the
   remote and merges `origin/<landing>` into the node branch inside its worktree.
   Its docstring at `factory/workgraph/worktree.py:1324-1339` states the terms:
   "a merge, never a rebase", "no rebase, no force, no reset", the pushed commit
   stays reachable, and a conflict comes back as a file list rather than as an
   exception. The activity wrapping it is
   `factory/activities/merge_activities.py:580` — `sync_landing_branch`, and the
   workflow executes it at `factory/workgraph/workflow.py:3703` — on the
   landing-recovery path, which is reached only after the merge queue has
   rejected a pull request.
5. No surface says any of this. The blast-radius text an operator reads before
   pressing RETRY is the `_CHOICE_EFFECTS` map at
   `factory/notify/messages.py:134`, whose RETRY entry at
   `factory/notify/messages.py:135-138` reads "node: one more attempt, on the
   tree this one left behind". That says the tree is *reused*. It
   does not say the tree was branched from the landing branch at dispatch, and it
   does not say what that means for a document the operator has just corrected.
   That map is keyed by choice and not by escalation site, so the same sentence
   is also what a landing escalation shows: `factory/workgraph/workflow.py:4178`
   — `_escalate_landing` offers RETRY through
   `factory/verify/ladder.py:116` — `offered_choices` at
   `factory/workgraph/workflow.py:4220`, and a node that reached it through a
   recovery has already had its pin moved at
   `factory/workgraph/workflow.py:3734-3736`. Whatever sentence replaces the
   present one has to be true on both paths.
   `ergane build status` prints the pin and the landing head side by side
   (`factory/cli/nouns/build.py:504`, rendered by
   `factory/cli/nouns/build.py:524` — `_base_token`) and says nothing about
   whether that pin can move, or what moves it.

**So the data is already on the screen and the sentence that would make it
actionable is missing, and the one function that could act on it is behind a
door only the merge queue can open.**

## The rule this spec is asking for

**A running node's tree is pinned at dispatch; every operator surface that offers
another attempt says so, and says truthfully what can move it; and one bounded
verb re-syncs that tree with the landing branch between attempts — merging, never
discarding — or reports exactly why it could not, including when the merge left
work for a human.**

The four cases, complete:

| re-sync requested | what the sync did | what the node does next | what the operator reads |
|---|---|---|---|
| **no** | — | next attempt opens the pinned tree, unchanged | the RETRY line says the tree was branched at dispatch, names the only two things that move it, and names the two recoveries |
| yes | merged clean | next attempt opens the tree with the landing head merged in, and is measured from that head | status names the new pin |
| yes | **conflicted** | the merge is left conflicted in the tree — markers and an unmerged index — nothing is rewritten, and every remaining rung runs against that tree until a human resolves it | status names the conflicted paths **and says the tree still carries them**, so the operator reads the cost rather than a courtesy |
| yes | **could not run** | next attempt opens the pinned tree, unchanged; no escalation, no attempt spent | status names the refusal and its reason |

The bottom two rows are the half the title is about. A lever that silently does
nothing when it cannot act is worse than no lever, because it converts a wait for
a change that cannot arrive into a wait for a change the operator believes they
requested. The third row is the expensive one and the one an implementer will be
tempted to report as benign: `factory/workgraph/worktree.py:1334-1336` leaves the
markers deliberately, so a conflicted re-sync hands the node a tree its own gates
cannot build in. That is the same "attempts spent on something that cannot work"
this finding measured, and the only defence a spec of this size can offer is to
make the operator read it.

The first row carries its own hazard, in the other direction. The honest sentence
is *not* "the tree has not moved since dispatch", because the factory already has
one mover: a landing recovery re-binds the pin at
`factory/workgraph/workflow.py:3734-3736`, and the RETRY line renders on that
escalation too. A sentence that over-claims is the same defect this spec exists
to end, told the other way around — the operator concludes their correction
cannot have arrived when it has already merged.

### What this spec is not

It is not an un-pinning of the worktree. The default stays exactly as
`factory/workgraph/worktree.py:420-441` describes it: measured on the preparation
path, never between attempts. The sync is reachable only from an operator's
explicit request, and a node nobody signals runs today's activity sequence.

It is not a second standards channel. 118 landed
`factory/activities/agent_activities.py:1022` — `resolve_standards` and this spec
does not rebuild, widen or duplicate it; it names it, in the words an operator
reads.

It is not a change to the landing path. Recovery cycles and free rebases are that
path's accounting and stay untouched, including the escalation a refused sync
raises there, and including the pin move at
`factory/workgraph/workflow.py:3734-3736` — which US2's sentence must *describe*
and must not alter.

It is not a conflict resolver, and it does not repeat the landing path's answer to
a conflict. At `factory/workgraph/workflow.py:3787-3794` a conflicted recovery
sync switches the attempt's persona to the debugger — "a conflicted one is a
different job, handed to the debugger". There is no debugger here and no second
git helper (FR-004), so a conflicted re-sync ends the node's *useful* ladder
until a human acts: the remaining rungs will run against a tree carrying
`<<<<<<<`. This spec does not fix that; FR-006 and FR-010 require it to be said
out loud, in the outcome the operator reads, so the choice to resolve the tree or
end the node is theirs and is informed.

It is not a fifth button. `factory/verify/models.py:141` — `EscalationChoice`
stays RETRY / KILL / PAUSE_EPIC / KILL_EPIC.

## User Scenarios & Testing

### User Story 1 - One verb re-syncs a running node's tree, or says why it could not (Priority: P1)

As an operator who has just landed the fix a stuck node needs, I can ask that
node's tree to take it, and I am told what happened either way.

**Why this priority**: P1 and it depends on nothing. It is the ask the finding
calls a "middle lever" — between waiting for a change that cannot arrive and
throwing the epic away. It is also the story US2's words have to describe: a
sentence naming a recovery must not ship before the recovery does.

**Independent Test**: Drive a node's attempt loop with the request buffered and
read what the workflow executed, what the record carries afterwards, what base
the next attempt's verification row was written with, and what
`ergane build status` renders — clean, conflicted and refused, one run each.

**Acceptance Scenarios**:

1. **Given** a node whose first attempt has failed and whose ladder will run
   another, **When** the operator's re-sync request is buffered before that next
   attempt begins, **Then** the diff shows the attempt loop executing the
   existing `factory/activities/merge_activities.py:580` — `sync_landing_branch`
   activity for that node before the attempt's prompt is built, proven by a
   committed test that asserts the activity ran exactly once and ran before the
   agent was dispatched.
2. **Given** that request and a merge that succeeds, **When** the sync returns
   and the following attempt is verified, **Then** the merged-in head is the
   node's base pin on **both** `record.base_ref` and `record.prepared` **and** is
   the base recorded on that attempt's verification row — the value
   `factory/workgraph/workflow.py:2672` writes from the same `prepared` local
   `check_output` is measured with at `factory/workgraph/workflow.py:2614`. One
   committed test asserts the two of those a test can reach: the
   `record.prepared` half through the
   `factory/workgraph/workflow.py:860` — `epic_status` query, whose
   `NodeStatus.base_ref` is composed from `record.prepared.base_ref` at
   `factory/workgraph/workflow.py:890-894`, and the local half from that
   verification row. `record.base_ref` has no reader outside the landing path's
   own pre-sync comparison at `factory/workgraph/workflow.py:3696`, so its write
   is proved by being in the diff and by nothing else — said here so an
   implementer does not mistake the query's `base_ref`, which is
   `record.prepared`'s, for it. A diff that writes the record fields and leaves
   `factory/workgraph/workflow.py:1715` — `_run_node`'s own `prepared` local
   stale passes the query half and fails the row, and the following attempt is
   then measured from the pre-merge base — every story that landed underneath
   this node read as its work.
3. **Given** a re-sync whose merge conflicts, **When** the sync returns, **Then**
   the diff introduces no rebase, reset or force-push call and routes the merge
   through the existing
   `factory/activities/merge_activities.py:580` — `sync_landing_branch` activity,
   and a committed test asserts the recorded outcome carries the conflicted paths
   **and** states that the tree still holds unresolved conflict markers, and that
   the node keeps running its ladder.
4. **Given** a re-sync the worker cannot run at all — the worktree is gone —
   **When** the activity reports its refusal, **Then** the reason is recorded on
   the node, no escalation is opened, no attempt is spent, and the next attempt
   opens the pinned tree; one committed test asserts all four.
5. **Given** no re-sync request at all, **When** the node runs three attempts,
   **Then** the diff shows no sync activity executed on that path and a committed
   test asserts the recorded base pin is identical across all three attempts.
   This is the control: without it, a diff that syncs every attempt passes every
   other scenario in this story.
6. **Given** a re-sync request naming a node that is not at work, **When** the
   ladder reaches its decision, **Then** the request is refused with a recorded
   reason rather than left buffered, asserted by a committed test that reads the
   recorded refusal.
7. **Given** an epic id that names no running workflow, **When**
   `ergane build resync` is run against it, **Then** the command exits non-zero
   with the same `no epic '<id>' is running here` refusal every other signal verb
   prints, proven by a committed test — and the diff shows the command's only
   effect is the signal: it opens no repository and calls no worktree helper.
8. **Given** one node whose last re-sync conflicted and one whose last re-sync
   was refused, **When** `ergane build status` renders each node's block,
   **Then** the block for the first carries the conflicted paths and the sentence
   that the tree still holds unresolved markers its remaining attempts will run
   against, and the block for the second carries the refusal and its reason,
   proven by one committed test asserting both rendered blocks. Without this the
   whole non-clean half of FR-010 is unfalsifiable from the diff.

### User Story 2 - Every surface that offers another attempt says the tree is pinned (Priority: P2)

As an operator deciding whether to press RETRY, I read what the next attempt will
actually see, and what I can do about it.

**Why this priority**: P2, and it waits on US1 because it names US1's verb. It is
the cheapest of the finding's three asks and the one that ends the specific waste
measured: an operator who knows the tree is pinned does not spend three attempts
waiting for a document to arrive.

**Independent Test**: Render the blast-radius block for a choice set containing
RETRY and for one that does not, and render a status line for a node with a
prepared worktree; read all three.

**Acceptance Scenarios**:

1. **Given** an escalation offering RETRY — from the verification ladder or from
   `factory/workgraph/workflow.py:4178` — `_escalate_landing`, which renders the
   same entry of the same map — **When** the blast-radius block is rendered,
   **Then** the RETRY line states that the tree the next attempt opens was
   branched from the landing branch when the node was dispatched and that it
   moves only when a landing recovery syncs it or an operator re-syncs it,
   proven by a committed test asserting the rendered line names both movers. A
   line claiming only that the tree "has not moved since" would be false on the
   landing escalation, where `factory/workgraph/workflow.py:3734-3736` has
   already moved it.
2. **Given** the same rendered line, **When** the blast-radius block is rendered
   for a choice set containing RETRY, **Then** it names the standards document as
   the one channel re-read from the landing branch each attempt, and makes no
   claim about the spec, the plan or the tasks, which
   `factory/workgraph/workflow.py:1013` reads once per epic. The committed test
   asserts the line verbatim, so a later claim about a channel that does not
   refresh is a visible diff rather than a quiet widening.
3. **Given** the same rendered line, **When** the blast-radius block is rendered
   for a choice set containing RETRY, **Then** it names both supported
   recoveries by name — `ergane build resync` for this node, and ending the epic
   and starting the spec again from the landing branch as it then stands, said
   as the operator's own move for a hand-started epic and as a later roadmap
   run's for a spec the roadmap owns — asserted by a committed test that finds
   both recoveries and asserts the line nowhere promises that ending the epic
   makes the roadmap rebuild it. That flat claim is false twice over:
   `factory/roadmap/workflow.py:1416` — `_landed_status_for` files a child that
   completed with a FAILED or KILLED node into the map
   `factory/roadmap/workflow.py:864-871` excludes from `dispatchable`, and an
   epic started with `ergane build start` has no roadmap owner at all.
4. **Given** an escalation whose offered choices do not include RETRY, **When**
   the block is rendered, **Then** none of that text appears, because
   `factory/notify/messages.py:358` — `render_blast_radius` renders one line per
   *offered* choice. The committed test drives a RETRY-less choice set and
   asserts the absence — the control that keeps this story from becoming a
   paragraph bolted onto the message body.
5. **Given** a node with a prepared worktree, **When** `ergane build status`
   renders it, **Then** the output carries a sentence stating that the base is
   the pin taken at dispatch and moves between attempts only when a landing
   recovery syncs it or a re-sync is applied, and a committed test asserts that
   the existing `base <sha12> landing head <branch> <sha12>` token from
   `factory/cli/nouns/build.py:524` — `_base_token` is unchanged, character for
   character, beside it.

## Functional Requirements

- **FR-001**: `ergane build resync <epic-id> <node-id>` MUST reach the running
  epic by workflow signal, through the same seam every other signal verb uses
  (`factory/cli/nouns/build.py:1492` — `_send_signal_with_args`), and MUST NOT
  read or write the node's worktree from the CLI process.
- **FR-002**: The signal handler MUST only buffer the request — no activity, no
  await — following `factory/workgraph/workflow.py:838` — `kill_epic`, whose
  docstring states why a handler that acted would race the lifecycle it is
  trying to change.
- **FR-003**: A buffered request MUST be applied between attempts, before the
  next attempt's prompt is built, and never while an attempt is in flight; the
  sync MUST be reachable only from a buffered request, so a node nobody signals
  executes exactly the activity sequence it executes today.
- **FR-004**: The sync MUST run through the existing
  `factory/activities/merge_activities.py:580` — `sync_landing_branch` activity,
  and therefore through `factory/workgraph/worktree.py:1316` —
  `sync_with_target`'s merge. No second git helper may be written, and the node
  branch MUST NOT be rebased, reset or force-pushed.
- **FR-005**: On a clean sync the merged-in head MUST become the node's base pin
  on both `record.base_ref` and `record.prepared`, exactly as the landing path
  already does it at `factory/workgraph/workflow.py:3734-3736` — **and** it MUST
  be the base the following attempt is actually measured from. The `prepared`
  value `factory/workgraph/workflow.py:1715` — `_run_node` holds in its own local
  and hands to `factory/workgraph/workflow.py:2559` — `_verify` at
  `factory/workgraph/workflow.py:2076-2080` MUST carry the merged-in head, so
  that attempt's `check_output` (`factory/workgraph/workflow.py:2614`), its
  diff-size refusal, its judge diff
  (`factory/workgraph/workflow.py:2629`) and the base recorded on the
  verification row (`factory/workgraph/workflow.py:2672`) all measure from it.
  Writing the two record fields alone does not satisfy this requirement, and the
  verification row is the one of those four an offline attempt loop can read
  back. Of the two record fields only `record.prepared` has a reader: the
  `factory/workgraph/workflow.py:860` — `epic_status` query composes
  `NodeStatus.base_ref` from it at `factory/workgraph/workflow.py:890-894`.
  `record.base_ref` is read only by the landing path's own pre-sync comparison
  at `factory/workgraph/workflow.py:3696`, so its write is an obligation the
  diff carries and no assertion can reach, and a test asserting the query's
  `base_ref` has proved `record.prepared` rather than it.
- **FR-006**: A sync that conflicts MUST record the conflicted paths on the node
  and let the node continue, and the recorded outcome MUST also state that the
  tree still holds unresolved conflict markers and that the node's remaining
  attempts will run against them until a human resolves the tree or ends the
  node. A sync the worker cannot run MUST record the refusal and its reason.
  Neither may open an escalation, end the node, or spend an attempt, and neither
  may hand the tree to another persona the way
  `factory/workgraph/workflow.py:3787-3794` does on the landing path.
- **FR-007**: A request naming a node that is not at work MUST be refused with a
  recorded reason rather than left buffered, in the shape of
  `factory/workgraph/workflow.py:2819` —
  `_refuse_buffered_external_completions`. That helper is a shape to copy, not a
  helper to call: it writes through
  `factory/verify/store.py:1882` — `record_external_completion_signal`, which
  wants a branch and a provenance string a re-sync request does not have. A
  re-sync refusal is recorded on the node record and read back through
  `ergane build status` (FR-010), and it MUST NOT reach the external-completion
  audit log or its durable counter.
- **FR-008**: With no request buffered, the attempt loop MUST execute no sync
  activity, and a node's base pin MUST be identical across its attempts.
- **FR-009**: The lever MUST NOT read or write `record.landing`. Recovery cycles
  and free rebases are the landing path's accounting and stay exactly as they
  are, including the escalation a refused sync raises there.
- **FR-010**: The outcome of the last applied re-sync MUST be readable from
  `ergane build status` for that node, in all three shapes: clean with the new
  pin; conflicted with the paths **and** the sentence that the tree still holds
  unresolved markers its remaining attempts will run against; refused with the
  reason.
- **FR-011**: The RETRY entry of the `_CHOICE_EFFECTS` map at
  `factory/notify/messages.py:134` MUST state that the tree the next attempt
  opens was branched from the landing branch when the node was dispatched, and
  that it moves only when a landing recovery syncs it
  (`factory/workgraph/workflow.py:3734-3736`) or an operator applies the verb
  FR-001 adds. It MUST NOT claim the tree has not moved since dispatch: the map
  is keyed by choice rather than by escalation site, so
  `factory/workgraph/workflow.py:4178` — `_escalate_landing` renders this same
  line whenever `factory/verify/ladder.py:116` — `offered_choices` grants RETRY
  at `factory/workgraph/workflow.py:4220`, and a node that reached that
  escalation through a recovery has a pin the factory itself has moved.
- **FR-012**: That same entry MUST name the standards document as the one
  channel re-read from the landing branch per attempt, and MUST NOT claim that
  the spec, the plan or the tasks refresh.
- **FR-013**: That same entry MUST name both supported recoveries: the verb
  FR-001 adds, and ending the epic and starting the spec again from the landing
  branch as it then stands. It MUST NOT state the second as an automatic
  rebuild. `factory/roadmap/workflow.py:1416` — `_landed_status_for` records a
  child that completed with a FAILED or KILLED node as finished-but-not-landed,
  `factory/roadmap/workflow.py:864-871` excludes every spec in that map from
  `dispatchable`, and `factory/roadmap/workflow.py:302` — `RoadmapCarryOver`
  carries the map across continue-as-new, so the roadmap run that dispatched
  this epic will not dispatch the spec again; an epic started by hand with
  `ergane build start` has no roadmap owner to rebuild it at all. The line MUST
  say the restart is the operator's move for a hand-started epic and a later
  roadmap run's for a spec the roadmap owns.
- **FR-014**: The text MUST be an extension of the existing `_CHOICE_EFFECTS`
  entry rather than a second block, and
  `factory/notify/messages.py:358` — `render_blast_radius` MUST keep rendering
  exactly one line per offered choice and nothing for a choice not offered.
- **FR-015**: `ergane build status` MUST state that a node's base pin is taken at
  dispatch and moves between attempts only when a landing recovery syncs it or a
  re-sync is applied, beside the token
  `factory/cli/nouns/build.py:524` — `_base_token` already renders, leaving that
  token's text unchanged.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, FR-008, FR-009, FR-010]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-011, FR-012, FR-013, FR-014, FR-015]
```

One `depends_on_merged` edge, declared rather than left to be inferred (069-US2
FR-008: an edge the author states is an edge the author considered). It carries
two jobs at once. It is a correctness edge: FR-013 requires US2's sentence to
name the verb FR-001 adds, and a message advertising a verb nobody can run is a
worse defect than the silence it replaces. It is also the contention edge, because
both stories edit `factory/cli/nouns/build.py` — US1 adds the verb, its parser
entry and the re-sync outcome lines, US2 adds the pin sentence beside
`factory/cli/nouns/build.py:524` — `_base_token`. Every other production file is
owned by exactly one story.
