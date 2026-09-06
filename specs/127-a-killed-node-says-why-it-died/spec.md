---
state: draft
fixes:
  - interpreter/the-ref-clearing-report-overwrites-the-terminal-reason-that-explains-why-a-node-died
  - verify/a-landing-recovery-escalation-names-no-exhausted-bound
# DRAFTED 2026-09-03 by the operator session, against ergane-buildout at 238b494.
# Every `file:line` in spec.md and plan.md was read from that commit and verified
# to resolve to the symbol named, not recalled. 072's lesson, applied.
#
# WHERE THIS CAME FROM. The `ergane-web` consolidated hand-over of 2026-09-03
# (`ergane-findings-ergane-web-2026-09-03.md`), a document written by a consumer
# repository that is itself a target of this factory. Its single most useful
# sentence, and the reason this spec is P0:
#
#   "Every one of the run's expensive failures was diagnosable in one line that
#    ergane did not print."
#
# Measured, in that run: `PUSH_FAILED` cost four hours and three wrong diagnoses
# while the exception sat in `journalctl`; `terminal_reason` read `Activity task
# failed`. The audit-gate asymmetry stopped every spec in the repository for
# 11h40m. The document's closing ask is this spec's whole scope — "make
# `terminal_reason` carry the real cause, and have `ergane status` / `build
# status` surface it. Six of the ten top-priority findings become five-minute
# problems the moment that is true."
#
# THIS SPEC CLEANS UP AFTER 126, WHICH THIS FACTORY LANDED YESTERDAY. 126-US2's
# own docstring (`factory/workgraph/workflow.py:3239`) states that
# `terminal_reason` carries git's diagnosis, that it is what `ergane build status`
# prints, and that a node which later merges "keeps that line, and should". Its
# implementation then assigns the archive-and-clear housekeeping report OVER that
# field. The story contradicts its own docstring, and it landed on
# `judge_outcome: UNAVAILABLE` — the one story doing delicate ref surgery is the
# one that got no scoring. That is filed and it is FR-001 through FR-005 here.
#
# NOT IN SCOPE. This spec does not change what `_failure_detail` walks, does not
# add or rename a terminal state, does not touch the escalation button set (126-US3
# already settled that widening the choice set deserves its own decision), and does
# not rewrite `ergane status`'s spec or queue sections. It adds one field, stops
# two writes, adds one read to two renderers, adds one verb, and adds one argument
# to one existing call.
#
# REFINED 2026-09-04 by the refinement workflow (refinement-2026-09-04); every
# anchor in spec.md, plan.md and tasks.md re-read from ergane-buildout at 602a92c.
# Forty-odd path anchors and eighteen bare line refs re-read; NONE had moved —
# 057's four landings touch no file this spec anchors. What changed is what those
# anchors MEAN, in four places:
#
# US2 WAS BUILT ON A FALSE READING AND IS REWRITTEN. `ergane status` renders no
# node lines of its own: `factory/cli/status.py:788` imports `render_status` from
# `factory.cli.nouns.build` at `factory/cli/status.py:796` and reuses it, under a
# comment at `factory/cli/status.py:794` saying why. So the cause is ALREADY
# printed on both surfaces. The draft's "`terminal_reason` appears zero times in
# `factory/cli/status.py`" was true and meant the opposite of what it was read to
# mean, and the draft's implementation task would have added exactly the second
# renderer that comment exists to prevent. The DRAFTED block's closing tally is
# left standing as written, and is wrong by one clause: it is one token in ONE
# renderer, which the other surface inherits — not one read in two.
#
# US3's SOURCE WAS WRONG. `terminal_reason` is not in the verification store; it
# lives in workflow memory and reaches a reader only through the `epic_status`
# query. A verb built to FR-009 as drafted — "from the stores only" — would have
# shipped without the one datum this spec exists for. US3 now reads two sources
# and refuses legibly when the execution has aged out.
#
# US4's REUSE INSTRUCTION WAS WRONG. `exhausted_bound`
# (`factory/verify/ladder.py:270`) reads a `VerificationConfig` and cannot name
# `max_recovery_cycles`, which is a `LandingConfig` dial
# (`factory/mergequeue/models.py:393`). Calling it on the landing path returns the
# wrong bound or `None`. FR-011 now says: build an `ExhaustedBound` for the landing
# dial and render it through the existing `_bound_sentence`.
#
# TWO REQUIREMENTS WIDENED. FR-001 now carries the new field into the query answer
# (`factory/workgraph/workflow.py:599`), because a field no renderer can reach
# repeats the defect in a new slot. FR-009 now covers the queue outcome and the
# transcript directory — two of the four invisibles its finding names that the
# draft did not reach. Three fixes keys kept; none added, none removed.
#
# STILL NOT IN SCOPE, named here so a later triage is not misled: `ergane build
# watch`, the second verb the causal-chain finding's reporter asked for, is NOT
# built. That key is declared fixed on the chain being readable in one call, not
# on follow-mode. If follow-mode is still wanted after this lands it needs its own
# spec and its own key.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), against ergane-buildout at 602a92c:
# the causal-chain fixes key is WITHDRAWN rather than half-declared; a fourth key
# is named as read and not declared; FR-009 bounds the gate output it prints;
# FR-010 names the discriminator between "no such epic" and "the execution aged
# out"; escalation prose is put out of scope in the body; FR-005's test-comment
# instruction is corrected from "make a true comment false" to "extend it"; and
# two plan pointers (the paste task's number, the factory-root resolution) are
# repaired. No FR is renumbered, no story is split, no anchor moved.
#
# THE CAUSAL-CHAIN KEY IS NO LONGER DECLARED. The key
# `operator/the-causal-chain-behind-a-node-state-is-only-readable-from-the-filesystem`
# has been REMOVED from `fixes:`. Its ledger notes ask for two verbs, not one:
# `ergane build why` — built here, as FR-009 and FR-010 — and `ergane build
# watch`, follow-mode streaming transitions WITH REASONS, which is not built here;
# nor is the third invisible that key names, "`build status` shows RUNNING ->
# VERIFYING -> RUNNING with no reason attached, so the operator polls in a shell
# loop". Declaring the key would close the whole row on the half this spec builds
# and leave the other half with no successor — the shape an operator had to
# correct by hand in 5fa87c2 for 100, and the same shape as 092 and 118. This
# SUPERSEDES the REFINED block's closing paragraph on one clause: the key is not
# "declared fixed on the chain being readable in one call"; it is not declared at
# all. Whoever builds follow-mode declares it, or an operator splits the row into
# a read half and a follow half before that happens. The reservation is recorded
# here because this spec may not write to the ledger; it is not a substitute for
# the ledger, which is exactly why the key is withdrawn instead.
#
# ONE MORE KEY READ AND DELIBERATELY NOT DECLARED.
# `verify/a-deterministic-gate-refusal-names-no-cause-an-operator-can-read` is
# open, and FR-009 removes its loudest complaint — "No verb exposes an attempt's
# gate output", after which its reporter re-ran a seven-minute suite by hand and
# still could not tell a refusal from a flake. It is NOT declared because its
# other half is untouched here: it asks that the refusal be persisted beside
# `stdout.log` as `attempt-N/gate.log` and surfaced on the status line as
# `rejection_cause`, and this spec adds no writer and no status-line field. Named
# so a later triage can see it was weighed rather than missed.
#
# THE ESCALATION TEXT IS OUT OF SCOPE, AND WHY. The causal-chain notes list
# "escalation text" among what a `why` verb should print. The `epic_status` answer
# carries only `awaiting_operator` (`factory/workgraph/workflow.py:672`), and
# `NodeRecord` carries escalation *ids* (`factory/workgraph/models.py:377`) rather
# than the composed message, so printing the prose would need the new query column
# FR-009 forbids in the same sentence. Excluded, and said out loud in "What this
# spec is not" rather than left for an implementer to discover.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04, second pass), against
# ergane-buildout at 602a92c: US3 IS SPLIT because it was measured over the diff
# bound; the two absences and their discriminator become US5, a NEW story number
# (US4 keeps its number and its content — nothing is renumbered); FR-010 sheds the
# passed-node clause to FR-009 so the two blocks match the new cut; the gate
# clipper's import is corrected — `factory/cli/nouns/build.py:94` imports
# `factory.notify.service`, not `factory.notify.messages`, so FR-009 now permits
# promoting `_tail` to a public name rather than leaving an implementer to balk at
# a private cross-module import and write a second clipper; two `:3252` cites
# become `:3252-3253`, which is where the store actually happens; and plan.md's
# trap paragraphs are put back in order. No FR is renumbered and no fixes key
# moves.
#
# WHY THE SPLIT, MEASURED. `DIFF_REFUSAL_THRESHOLD = DIFF_INPUT_LIMIT = 65,536`
# (`factory/verify/diffbounds.py:47` and `factory/verify/diffbounds.py:66`, D-050),
# and a story over it is refused UNJUDGED with the attempt spent — that constant's
# own comment records a story no attempt could pass at 74,465 bytes with four gates
# green and the judge never reached. The nearest measured analogue on this tree is
# 092-US3 (`03451a9`), which added `ergane build attempts` — a read-only CLI verb
# over the same verification store, three scenarios, one source — and came to
# 60,162 bytes, 92% of the bound. US3 as drafted was strictly larger on every axis:
# five scenarios, two sources joined, a two-branch `NOT_FOUND` discriminator, six
# printed facts, transcript composition, tail clipping and two pasted runs.
# Clipping the tail and trimming the pastes is mitigation, not sizing. The cut is
# vertical: US3 is the verb over both sources for an execution that is still there,
# US5 is the two absences. Between them US3 refuses on `NOT_FOUND` exactly as
# `factory/cli/nouns/build.py:1135-1138` does today, which is honest and is what
# US5 then replaces.
#
# THE COMPILED ARTIFACT BESIDE THIS SPEC IS NOW STALE, AND THIS PASS MAY NOT
# REWRITE IT. `workgraph.json` in this directory was derived from the four-story
# spec and holds four nodes; the split makes five. `ergane build start` loads that
# file off disk (`factory/cli/nouns/build.py:808`) rather than re-reading the
# spec, so a hand-run start against it would dispatch four nodes and drop US5
# without saying so. The roadmap derives from the spec text and is unaffected.
# Re-derive before any manual start.
---

# Feature Specification: a killed node says why it died

**Created**: 2026-09-03
**Depends on**: nothing outside this spec. 126 has landed; this repairs it.

## The gap, stated precisely

The factory computes the cause of a node's death, overwrites it with
housekeeping, and then prints the housekeeping as the cause. Four steps, each of
them individually defensible:

1. **The cause is computed and then overwritten.** `_failure_detail`
   (`factory/workgraph/workflow.py:509` — `_failure_detail`) walks an exception's
   cause chain to the frame that carries the real reason, and
   `factory/workgraph/workflow.py:3252-3253` calls it on a refused push and stores
   git's own diagnosis into `record.terminal_reason`. Then the housekeeping report
   from archiving and clearing the remote ref is assigned over the same field — at
   `factory/workgraph/workflow.py:3152` inside `_close_out`, and again at
   `factory/workgraph/workflow.py:3613` inside `_archive_and_clear_remote_branch`.
   Both are guarded by `if report:`, which is non-empty precisely when the node HAS
   a remote branch — the only case in which a push refusal can occur. **The
   overwrite fires exactly when the cause is worth keeping.**

2. **The overwrite is not hidden; it is published as the cause.** `_reason_token`
   (`factory/cli/nouns/build.py:718` — `_reason_token`) prints `terminal_reason`
   at the end of every node line `render_status` assembles
   (`factory/cli/nouns/build.py:505`), and `ergane status` reaches the same line by
   importing that renderer rather than writing one
   (`factory/cli/status.py:796`). So both surfaces faithfully print whatever is in
   the slot, and on the path this spec exists for that is `deleted origin branch …
   (kept as archive/…)` where git's refusal used to be. One field is answering two
   questions, and the second answer wins.

3. **There is no verb that assembles the chain, and the ending is not in the
   store the read-only verbs use.** The evidence is spread across two places: the
   verification store holds the verdicts, the gate results and the judge's
   feedback, and `attempts_command` (`factory/cli/nouns/build.py:1284` —
   `attempts_command`) already reads it with no Temporal client. The *ending* —
   `terminal_reason`, the landing's queue outcomes — is in workflow memory and
   reaches a reader only through the `epic_status` query
   (`factory/workgraph/workflow.py:882`). Nothing joins them, so answering "why did
   this die" is a filesystem walk and a `journalctl` read, which is what cost four
   hours.

4. **A landing-recovery escalation names no exhausted bound.** 095 built
   `exhausted_bound` (`factory/verify/ladder.py:270` — `exhausted_bound`) and wired
   it into the verification escalation at `factory/workgraph/workflow.py:2160`,
   rendering through `_bound_sentence` (`factory/workgraph/workflow.py:4351` —
   `_bound_sentence`) and printing at `factory/notify/messages.py:450`.
   `_escalate_landing` (`factory/workgraph/workflow.py:4178` — `_escalate_landing`)
   builds its `EscalationRequest` at `factory/workgraph/workflow.py:4215` with no
   `exhausted_bound` at all. Its message prints the cycles *spent*
   (`factory/notify/messages.py:309`) and never the dial they were spent against,
   and `max_recovery_cycles` appears **zero** times anywhere under
   `factory/notify/` or `factory/escalation/`. 095's FR-008 is written unrestricted
   — "An escalation MUST name which ladder bound was exhausted and its configured
   value" — so this is that requirement unmet on the landing path, not a new one.

## The rule this spec is asking for

**`terminal_reason` carries the cause and only the cause, the housekeeping report
gets its own slot beside it, every surface an operator reads prints the two as two
things, and one verb assembles the chain behind them.**

The two facts combine four ways, and all four are pinned:

| a cause was recorded | the housekeeping report | `terminal_reason` after | the new field after |
| --- | --- | --- | --- |
| yes (git's refusal) | non-empty | the cause, unchanged | the report |
| yes | empty | the cause, unchanged | empty |
| no | non-empty | stays `None` | the report |
| no | empty | stays `None` | empty |

Row one is the defect. Row two is most nodes and must not move. Row three is the
one an over-eager refactor gets wrong by promoting bookkeeping into a cause.

### What this spec is not

It is not a change to how a cause is *computed*. `_failure_detail` keeps its walk
and its depth bound. What changes is that nothing overwrites its answer.

It is not a new terminal state, and it is not a new escalation button. US4 changes
what a message *says*, not what the operator may press.

It is not a rewrite of `ergane status`, and it does not give that verb a renderer
of its own. It reuses `render_status` today and must still reuse it afterwards;
US2's work is a token in the shared renderer, which both surfaces then inherit.

It is not a reader for escalation prose. The causal-chain finding lists "escalation
text" among what a `why` verb should print, and this spec does not print it: the
`epic_status` answer carries only `awaiting_operator`
(`factory/workgraph/workflow.py:672`) and the record carries escalation ids
(`factory/workgraph/models.py:377`), not the composed message, so surfacing the
prose would need the new query column FR-009 forbids in the same sentence.

It is not follow-mode. `ergane build watch` — streaming state transitions with
their reasons — is not built here, which is why the frontmatter declares no fixes
key for the causal chain.

## User Scenarios & Testing

### User Story 1 - The housekeeping report stops overwriting the cause (Priority: P1)

As an operator reading a killed node, the reason I see is why it died, not what
the factory tidied up afterwards.

**Why this priority**: P1 and it depends on nothing. Every other story in this
spec reads the field this one repairs; printing an overwritten field more widely
would spread the defect rather than fix it.

**Independent Test**: Kill a node that has a remote branch on a push refusal, then
read its terminal record: the reason is git's, and the archive report is beside it.

**Acceptance Scenarios**:

1. **Given** a node whose push was refused non-fast-forward and whose remote branch
   is then archived and cleared, **When** the node reaches its terminal state,
   **Then** `terminal_reason` carries git's diagnosis of the refusal and the
   archive-and-clear report is readable from a separate field on the same record,
   and the query answer carries both.
2. **Given** a node ended with an empty housekeeping report, **When** it reaches its
   terminal state, **Then** `terminal_reason` is unchanged from today's value and
   the new field is empty, so a node with nothing to tidy reads exactly as it does
   now.
3. **Given** a node ended with a housekeeping report and **no** terminal reason —
   an ordinary kill that never failed a push — **When** it reaches its terminal
   state, **Then** `terminal_reason` stays `None` and the report is in the new
   field, because the report is not a cause and must never be promoted into one.
4. **Given** the kill path inside `_escalate_ref_conflict`
   (`factory/workgraph/workflow.py:3216` — `_escalate_ref_conflict`), which at
   `factory/workgraph/workflow.py:3330` reaches `_archive_and_clear_remote_branch`
   and never `_close_out`, **When** a node is killed through it, **Then** the same
   separation holds — proving both overwrite sites were repaired and not just the
   one the finding names.

### User Story 2 - Both surfaces print the cause and the housekeeping as two things (Priority: P1)

As an operator, whichever status verb I reach for, a terminal node tells me why it
is terminal and, separately, what was tidied up after it.

**Why this priority**: P1. The field US1 adds is invisible until a renderer reads
it, and the surface that reads it is shared, so one token serves both verbs.
Second only because it prints the field US1 creates.

**Independent Test**: Run both status verbs against an epic with a killed node that
had a remote branch, and read the node lines.

**Acceptance Scenarios**:

1. **Given** an epic with a terminal node carrying both a cause and a housekeeping
   report, **When** `ergane build status` renders it, **Then** the node's line
   carries the two as distinct labelled tokens and neither is shown as the other.
2. **Given** the same epic, **When** `ergane status` renders it, **Then** its node
   lines carry both, because that verb reaches them through `render_status`
   (`factory/cli/nouns/build.py:464` — `render_status`) rather than a renderer of
   its own — pinned by a committed test that compares the two verbs' node lines for
   one document and fails if they diverge.
3. **Given** a node with a housekeeping report and no terminal reason, **When**
   either verb renders it, **Then** no cause is claimed for it and only the
   housekeeping token appears.
4. **Given** an epic whose nodes are all non-terminal, **When** either verb renders
   it, **Then** the output is byte-identical to today's, so this story cannot
   change a surface it is not about.

### User Story 3 - One verb assembles the causal chain (Priority: P2)

As an operator diagnosing a dead node, I run one command instead of walking a
filesystem and reading a journal.

**Why this priority**: P2. US1 and US2 make the ending honest and visible; this
makes the *chain* behind it readable, which is the difference between knowing a
push was refused and knowing which gate failed three attempts earlier. It is
scoped to an execution the server still holds; US5 adds the two absences, because
one story carrying both was measured over the diff bound.

**Independent Test**: Run the verb against an epic with a failed node and read what
it assembles; then run it against a node that passed.

**Acceptance Scenarios**:

1. **Given** an epic with a node that failed verification and was killed after its
   landing was rejected, **When** `ergane build why <epic-id> <node-id>` runs,
   **Then** it prints the node's last verdict, the failing gate with a **bounded**
   tail of its output — the last `EVIDENCE_TAIL_LINES` lines
   (`factory/notify/messages.py:79`) with what was dropped named, never the whole
   32 KiB field — the judge's feedback where one exists, the queue outcomes its
   landing recorded, the transcript directory of the latest attempt, and the
   terminal reason.
2. **Given** the same epic and no node argument, **When** `ergane build why
   <epic-id>` runs, **Then** it reports every terminal node of that epic in the
   same shape.
3. **Given** a node that passed and landed, **When** the verb runs against it,
   **Then** it says the node has no failure to explain rather than printing an
   empty chain.

### User Story 4 - A landing-recovery escalation names its exhausted bound (Priority: P3)

As an operator deciding on a one-hour clock, I am told which dial ran out and what
it was set to, not just how many cycles were spent.

**Why this priority**: P3 and it is the smallest story here — one argument on one
existing call, plus the two call sites that know the answer. Lowest because it is
one escalation path, while US1 through US3 are every terminal node. It is included
because it is 095's FR-008 unmet, and an unmet FR that nobody notices is how a
requirement quietly stops binding.

**Independent Test**: Compose a landing-recovery escalation with its recovery
cycles spent and read the message; then compose one with a cycle remaining.

**Acceptance Scenarios**:

1. **Given** a node escalating from the landing-recovery path with its recovery
   cycles spent, **When** the escalation message is composed, **Then** it names
   `max_recovery_cycles` and its configured value, in the sentence shape
   `ExhaustedBound.describe` already produces for the verification path.
2. **Given** a node escalating from the landing-recovery path with a cycle
   remaining, **When** the message is composed, **Then** it names no exhausted
   bound, because a dial that has not been reached must not be reported as spent.
3. **Given** a verification escalation, **When** it is composed, **Then** it is
   byte-identical to today's, so this story cannot alter the path 095 already
   built.

### User Story 5 - The verb tells "no such epic" from "the execution aged out" (Priority: P2)

As an operator asking why a node died some days after it died, I am given the half
of the chain that still exists instead of a refusal that reads as if the epic never
happened.

**Why this priority**: P2, the same priority as US3, because it is the second half
of the same verb: the moment this question is asked is usually the moment the
execution has aged out, which is the trade `attempts_command`'s docstring
(`factory/cli/nouns/build.py:1287-1290`) already refused to make. It is a separate
story rather than two more scenarios on US3 for one reason, and it is a measured
one: US3 carrying all five scenarios, both sources, the discriminator and its
pasted runs was sized over `DIFF_REFUSAL_THRESHOLD`
(`factory/verify/diffbounds.py:66`), where a story is refused unjudged and the
attempt is spent. Until this story lands, `build why` refuses on `NOT_FOUND` in
exactly the shape `factory/cli/nouns/build.py:1135-1138` refuses in today — no
worse than the verb it sits beside, and honest about what it does not know.

**Independent Test**: Run the verb against an epic id nothing is running under, and
again against an epic whose verification rows exist but whose execution has aged
out of the server; read both answers.

**Acceptance Scenarios**:

1. **Given** an epic id nothing is running under — the `epic_status` query answers
   `NOT_FOUND` and the verification store holds **no** rows for that epic —
   **When** the verb runs, **Then** it refuses naming the epic id, the workflow id
   it looked for and the verification store path it read, and exits non-zero with
   no traceback.
2. **Given** an epic whose verification rows exist but whose execution has aged out
   of the server — the same `NOT_FOUND`, but **with** rows in the store — **When**
   the verb runs, **Then** it prints the half of the chain the store holds and says
   in place of the ending that the execution is gone, rather than refusing the
   whole reading.

## Functional Requirements

- **FR-001**: `NodeRecord` (`factory/workgraph/models.py:324` — `NodeRecord`) MUST
  carry the archive-and-clear housekeeping report in a field distinct from
  `terminal_reason`, documented in the style of the sibling `attempt_note` field
  (`factory/workgraph/models.py:390-398`), which already records why it is not
  `terminal_reason`; and the query answer `NodeStatus`
  (`factory/workgraph/workflow.py:599` — `NodeStatus`) MUST carry the same field,
  populated beside `terminal_reason` at `factory/workgraph/workflow.py:882` — a
  field no renderer can reach would repeat the defect in a new slot.
- **FR-002**: The archive-and-clear housekeeping report MUST NOT be assigned to
  `terminal_reason` at either overwrite site — `factory/workgraph/workflow.py:3152`
  or `factory/workgraph/workflow.py:3613`.
- **FR-003**: A node whose push was refused MUST retain git's diagnosis in
  `terminal_reason` through archiving and clearing its remote branch.
- **FR-004**: A housekeeping report MUST NOT be promoted into `terminal_reason`
  when no cause was recorded; the absence of a cause is itself the honest answer.
- **FR-005**: The committed assertions that today read the branch name and pushed
  sha out of `terminal_reason`
  (`tests/test_126_us2_kill_archives_remote.py:260-262` and
  `tests/test_126_us2_kill_archives_remote.py:285-286`) MUST be repointed at the new
  field; the comment at `tests/test_126_us2_kill_archives_remote.py:318-319`, which
  describes the **empty-report** path and stays true after this change, MUST be
  EXTENDED to name the new field's value in that same case rather than rewritten as
  if it had become false; and at least one test MUST drive a **non-empty**
  housekeeping report through the interpreter, which today cannot happen.
- **FR-006**: `ergane status` MUST keep reaching its node lines through
  `render_status`, as `_epic_lines` (`factory/cli/status.py:788` — `_epic_lines`)
  does today; this spec MUST NOT add a node renderer to `factory/cli/status.py`,
  because two renderers that can disagree is the drift the reuse was put there to
  prevent.
- **FR-007**: `ergane build status` MUST print the housekeeping report on the
  node's line as a labelled token distinct from the cause.
- **FR-008**: That token MUST be a sibling of `_reason_token`
  (`factory/cli/nouns/build.py:718` — `_reason_token`) in the same module,
  flattening whitespace the way it does, and the cause MUST keep reaching both
  surfaces through `_reason_token` itself rather than a second renderer.
- **FR-009**: `ergane build why <epic-id> [node-id]` MUST assemble the last
  verdict, the failing gate and a bounded tail of its output, the judge feedback
  where one exists, the queue outcomes and rejection cause the landing recorded,
  the transcript directory of the latest attempt, and the terminal reason — reading
  the `epic_status` query for the record and `node_history`
  (`factory/verify/store.py:873` — `node_history`) for the attempts, and adding no
  store, no query column and no directory read. A node that passed MUST be told it
  has no failure to explain rather than shown an empty chain. The gate output MUST
  be printed through the clipper at `factory/notify/messages.py:641` — `_tail` —
  which keeps the last `EVIDENCE_TAIL_LINES` lines
  (`factory/notify/messages.py:79`) and names what it dropped; because that name is
  private and no production module imports a private name from
  `factory.notify.messages` today, FR-009 permits promoting it to a public name in
  that module, behaviour and bound unchanged, rather than writing a second clipper.
  `GateResult.output_tail` (`factory/verify/models.py:362` — `GateResult`) is the
  last ≤32 KiB of a gate's combined output and the store persists it whole
  (`factory/verify/store.py:1098`), which is half this story's diff bound on its
  own.
- **FR-010**: `build why` MUST tell "no such epic" from "the execution aged out" by
  the verification store rather than by the query alone, because both reach the
  verb as `RPCStatusCode.NOT_FOUND` on `epic_status`, which
  `factory/cli/nouns/build.py:1135-1138` collapses into a single refusal today.
  `NOT_FOUND` with **no** rows from `epic_history` (`factory/verify/store.py:899` —
  `epic_history`) MUST refuse, naming the epic id, the workflow id it looked for
  and the store path it read, and exiting non-zero without a traceback; `NOT_FOUND`
  **with** rows MUST print the store half of the chain and report the ending as
  unavailable.
- **FR-011**: `_escalate_landing` MUST carry an exhausted bound naming
  `max_recovery_cycles` (`factory/mergequeue/models.py:393`) and its configured
  value when the landing-recovery cycles are spent, built as an `ExhaustedBound`
  (`factory/verify/ladder.py:244` — `ExhaustedBound`), rendered by the existing
  `_bound_sentence`, and carried on `EscalationRequest.exhausted_bound`
  (`factory/escalation/workflow.py:162`). It MUST NOT call `exhausted_bound`, which
  reads a `VerificationConfig` and cannot name a `LandingConfig` dial.
- **FR-012**: A landing escalation with a cycle remaining MUST name no exhausted
  bound; `ExhaustedBound.describe` (`factory/verify/ladder.py:265-267`) MUST be
  left unchanged; and a verification escalation MUST be byte-identical to today's.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-006, FR-007, FR-008]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-009]
US4:
  depends_on: []
  depends_on_merged: [US1]
  concurrent_with: [US3]
  implements: [FR-011, FR-012]
US5:
  depends_on: []
  depends_on_merged: [US3]
  implements: [FR-010]
```

Four `depends_on_merged` edges, all declared rather than left inferred
(069-US2 FR-007), and each one buys something specific:

- **US2 after US1** because US2 prints the field US1 adds to the record and to the
  query answer. Built concurrently, US2 would render a field that does not exist
  yet on its base.
- **US4 after US1** because both edit `factory/workgraph/workflow.py`. The regions
  are far apart — the two overwrite sites and the query answer against the
  escalation builder — but 126's own lesson is that two stories sharing a file pass
  their own PR checks and fail in the merge group, and the second must then be
  rebuilt rather than patched.
- **US3 after US2** because both edit `factory/cli/nouns/build.py`: US2 adds a
  token beside `_reason_token`, US3 adds a subcommand and a renderer in the same
  module.
- **US5 after US3** because US5 rewrites the refusal branch of the command US3
  adds, in the same module and often in the same function. It is the second half of
  one verb, split for size rather than for independence, so serialising it costs
  nothing this graph could otherwise have spent.

US2 and US4 are concurrent with each other once US1 has merged, and US4 is
concurrent with both US3 and US5, which is the only parallelism this graph can
honestly offer.

`concurrent_with: [US3]` on US4 is a declared override of an inferred contention
edge, not a new dependency. Both stories name `factory/notify/messages.py` — US4
because that is where `exhausted_bound` is printed
(`factory/notify/messages.py:450`), US3 because it clips the gate output through
the helper at `factory/notify/messages.py:641` — **and US4 does not edit that
file**: US4's production diff is `factory/workgraph/workflow.py` alone. US3 may
touch it, by one rename if it promotes that clipper to a public name (FR-009), and
US4 still cannot collide with that. The two cite a module US4 only imports from;
left inferred, the edge would serialise two stories that cannot collide. US5 names
neither `factory/notify/messages.py` nor `factory/workgraph/workflow.py`, so it
needs no such override against US4.
