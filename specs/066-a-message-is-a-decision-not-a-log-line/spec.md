---
state: draft
fixes:
  - roadmap/failure-notices-have-no-dedupe-and-flood-the-operator
# Drafted 2026-08-19 4:35 PM CT from the operator's own screenshot of the
# Telegram channel and his verdict on it: "none of these messages are helpful."
#
# THE FOUR MESSAGES HE WAS LOOKING AT, verbatim:
#
#   7:00 AM  Roadmap roadmap-specs failed (1 consecutive run):
#            drift_for_spec(020-landing-attribution) failed: git fetch --quiet
#            origin failed in /home/admin/code/ergane-roadmap-target:
#            channel-b: refusing ref refs/tags/v0.1.0 (tags carry the v1
#            implementation) fatal: ref updates aborted by hook
#            ... and the same again for 021-roadmap-operability, and ~61 more
#
#   7:21 AM  Roadmap roadmap-specs recovered after 1 consecutive failure.
#
#   8:49 AM  Roadmap roadmap-specs failed (1 consecutive run):
#            'NoneType' object has no attribute 'epic_state'
#
#   4:05 PM  Roadmap roadmap-specs failed (3 consecutive runs):
#            'NoneType' object has no attribute 'epic_state'
#
# A CORRECTION THIS SCREENSHOT FORCED, and it is why this spec is worth more
# than it looks. 065's own spec text asserts "No page fires" for the scheduler
# wedge. That is WRONG, and the 8:49 AM and 4:05 PM messages disprove it: the
# operator WAS told, twice, hours apart. 065 landed 3/3 before the error was
# caught, so the false sentence is in the tree.
#
# The real defect is worse than the one 065 described. It was never that the
# operator was not told. It is that being told changed nothing, because
# "'NoneType' object has no attribute 'epic_state'" does not tell a person that
# their factory has stopped building, that nothing will build until they act, or
# what the act is. The floor idled 1h49m in the morning and roughly 1h38m in the
# afternoon with those pages sitting unread-because-unreadable on his phone.
#
# The one message in the corpus that already does this right is the escalation:
# "No answer by <time> applies the default: KILL the node." It states the
# consequence of silence. Every other message should be held to that standard.
#
# Related finding, folded in as US3 rather than left separate:
#   roadmap/failure-notices-have-no-dedupe-and-flood-the-operator
#
# REFINED 2026-09-04 by the refinement workflow (refinement-2026-09-04); every
# anchor in spec.md, plan.md and tasks.md re-read from ergane-buildout at
# 602a92c.
#
# WHERE THIS CAME FROM, STILL. Nothing about the 2026-08-19 screenshot has been
# softened. Every claim above was re-checked against the tree and all of it is
# still true: the composer still interpolates the raw text, the drift loop still
# reports once per spec, and the count still resets to one on every spec.
#
# WHAT IT COST, MEASURED. 1h49m of idle floor in the morning and roughly 1h38m
# in the afternoon of 2026-08-19, both while a correct page sat unread. Plus 63
# notices and 66 Telegram sendMessage calls in six minutes that same morning,
# which is the ledger row this refinement now declares in `fixes:`.
#
# EVERY ANCHOR HAD MOVED, AND FOUR INSTRUCTIONS HAD GONE WRONG. The plan's four
# `file:line` citations and its six bare `:NN` refs all pointed somewhere else
# after 068, 079, 095, 113 and 126 landed in the same two modules. Four were not
# merely stale but actively misleading: `_should_notify_failure` 139 -> 152 (139
# is now blank, the only one validate caught); `_report_roadmap_failure` 955 ->
# 1044; the per-spec flood site 1281 -> 1387, where 1281 is now the loop-config
# read inside `_dispatch`, so an implementer obeying the old anchor would have
# edited the manifest park path instead of the drift loop; and
# `tests/page_holds_true.py`'s `run_help`, which the plan told FR-009 to reuse,
# DOES NOT EXIST -- 113 replaced it with `parse_argv`, which parses without
# spawning anything.
#
# THE DEFECT CHANGED SHAPE, AND US2 SHRANK. 079 landed `render_blast_radius` and
# `_CHOICE_EFFECTS` on 2026-08-22: the escalation message already names what
# each offered button does to the node and to the epic, and it already states
# the default on silence. US2 is therefore no longer "teach every message to do
# what the escalation does" -- the escalation is the model already in the tree,
# and FR-012 now guards it against being restructured to fit a new abstraction.
#
# THE EXPENSIVE FIND: THERE IS NO SEAM TO CLASSIFY A FAILURE ON. The composer
# receives a bare string, so "state what stopped in factory vocabulary" has no
# input to work from, and the tempting move is a regex table over exception
# text. The tree already argues against exactly that -- see
# `factory/workgraph/contention.py:24`. FR-007 is new: the cause is named where
# it is raised, at the three reporting sites, and travels to the composer as a
# value. That one seam is also what makes US3 possible, because a count that
# keys on a named cause is a count that stops resetting to one per spec.
#
# THREE LANDED TESTS ENSHRINE THE BEHAVIOUR BEING REVERSED, and an implementer
# who meets them by surprise will either keep the repr to stay green or delete
# the count with it. Named in plan.md trap 3 and repeated in tasks.md.
#
# FOUR CRITERIA WERE PASSABLE BY A DO-NOTHING DIFF and are now differential:
# old US1-S4 (the verbatim text is recorded -- true today), old US3-S3 (two
# distinct causes are both reported -- true today, 63 messages proves it), the
# escalation regression guard, and the command sweep, which was vacuous while no
# notice named a command.
#
# WHAT THE `fixes:` KEY BUYS, AND WHAT IT DOES NOT. One key,
# `roadmap/failure-notices-have-no-dedupe-and-flood-the-operator` (open,
# critical). Its remedy shape is exactly two sentences -- collapse identical
# failures within a pass, suppress repeats of an unchanged cause across passes
# -- and FR-014, FR-015 and FR-016 address both halves plus the regression the
# second half invites. No key is declared for US1 or US2: the readability
# complaint was never filed as a finding, only as the operator's sentence, so
# there is nothing in the ledger for them to close and none is claimed.
#
# NOT IN SCOPE. The escalation message's body, buttons, blast radius and
# deadline sentence (FR-012 forbids changing them). The question message, which
# already does what US2 asks and is likewise guarded by FR-012. The resolution
# notice, which fires after the decision is in. The stack heartbeat. Adding an
# inline keyboard to any notice -- 031's decision that a notice offers no choice
# over the wire stands. What is recorded: `roadmap_failures` keeps the verbatim
# text and this spec only changes what the phone gets. And no new notification
# channel or trigger: a change that improved each message and raised the count
# would have failed the operator who asked for this.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04): the notice-kind set is now
# enumerated once, in the rule's table, over all seven messages the factory
# composes -- three changed, two controls, two out of scope -- because spec.md
# named five kinds and plan.md and tasks.md bound a different five, so US2's
# surface differed by two composers depending on which document an implementer
# trusted; `question_message` is promoted to a control under FR-012 (its landed
# "No answer by ... lets the node proceed as a FAIL" sentence was at risk from
# T023) and `resolution_notice` is excluded by name, since "what happens if you
# do nothing" has no referent after the decision is in; FR-005 and FR-006 were
# passable by omission once FR-001 removed all failure detail from the notice
# and are now three-way ordering and notice-versus-row differentials; FR-011's
# mechanism was impossible -- `extract_commands` reads markdown code spans and a
# notice is plain text with no `parse_mode` anywhere in the tree -- and now
# names the declared-argv seam with `parse_argv`, plus plan trap 14; T035 told
# US3 to keep a per-failure row that `roadmap_id TEXT PRIMARY KEY` cannot hold
# and whose charitable reading drives the cause-keyed count to 63 in one pass,
# where `_should_notify_failure` sends nothing at all -- rewritten, with plan
# trap 15 carrying the reproduction and US3-S2 asserting the count is 1 after
# one pass; `factory/supervision/probe.py:404` was the healthy-heartbeat line
# being used to claim `decide_alert` has no decision in it, corrected to :376
# with the exclusion restated as a decision; and fourteen anchors were rewritten
# into the `path.py:NN` -- `symbol` form so the next drift is machine-caught.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04, second pass): the
# manual-intervention notice is now **out of scope** rather than one of the
# three changed, because it has no production caller -- `grep -rn
# manual_intervention --include=*.py factory/` returns only its definition at
# `factory/notify/messages.py:313`, every other reference in the repository is a
# test, and `factory/mergequeue/classify.py:74`'s DEQUEUED_BY_HUMAN composes no
# message -- so FR-008, FR-009, US2-S1, US2-S2 and four US2 tasks were spending
# a third of that story's diff, and two of its scenarios, on text no operator
# receives and the "count a normal day" verification could never register;
# plan trap 3 counted THREE landed tests asserting the behaviour US1 reverses
# where SIX exist, all in the two files US1 already edits (`:406`/`:422`,
# `tests/test_messages.py:282`/`:286`, `_failure_count_from` at `:176`,
# `:835`/`:862`, `:892`/`:913`, `:988`/`:1024`, plus the fourth verbatim
# assertion at `:575`), so an implementer who obeyed it met three more red tests
# at exactly the point the plan stopped speaking; plan trap 16 is new and names
# `_compose`'s front-clip of the body, the mechanism that made 079-US4 put the
# blast radius in the FOOTER, because nothing told this spec's implementer where
# the impact, options and pointer lines must sit; and plan trap 17 is new and
# names the specs-root seam FR-011's commands need -- the positional is derived
# by stripping `ROADMAP_ID_PREFIX` from `roadmap_id`, never a placeholder and
# never a new composer parameter, since a parameter drags
# `factory/roadmap/workflow.py:1073` into US2 and falsifies the Work Graph's
# no-shared-file justification for running US2 and US3 concurrently.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04, third pass): four sentences the
# second pass did not follow through still counted US2's surface at three
# composers and trap 3's list at three tests -- the Work Graph justification,
# which is where an operator reads US2's scope, plan trap 6, and both halves of
# plan Sizing -- and all four now say two composers and seven landed sites; trap
# 3's heading, T013 and the tasks preamble now agree on seven, because the list
# under that heading has had seven items since the second pass wrote it.
# US2-S5 was green on US2's own base, so T020 could not fail first as the
# heading it sits under requires: all three control halves pass there, and so
# does the options block, because US1 lands it under FR-003 and FR-005 -- the
# notice half is now the FR-009 silence sentence and a command line rendered
# from a declared invocation, which is what US2 alone adds. T022 and T024 gave
# opposite instructions about the same option lines and now describe one change.
# FR-006 and T011 forbade "no part" and "no substring" of the failure text
# reaching a notice, which is unsatisfiable read literally while FR-001 keeps
# the word "failed" and the count; both now forbid rendering the text or a
# quoted span of it. And plan trap 18 is new: FR-010 needs a cause finer than
# the reporting site, because `factory/roadmap/workflow.py:1387` --
# `_drift_resolver` raises both a fault that clears itself and one that never
# did, and nothing told the implementer to read the exception's structure rather
# than invent a flag per site.
---

# Feature Specification: a message is a decision, not a log line

**Created**: 2026-08-19
**Depends on**: nothing.

## The gap, stated precisely

Ergane's operator channel forwards internal failure text to a human phone
unedited. A Python exception repr, a shell stderr tail and a spec-dir loop
variable all arrive as written. The chain is five steps:

1. A failed roadmap pass is reported by `factory/roadmap/workflow.py:1082` —
   `_report_run_failure`, which derives its text from
   `factory/roadmap/workflow.py:1028` — `_roadmap_failure_message`. That
   function's docstring commits it: "The failure message, verbatim from the
   exception (FR-009/012)."
2. The string reaches the phone unchanged. `factory/notify/messages.py:329` —
   `roadmap_failure_notice` interpolates it into
   `Roadmap {id} failed ({n} consecutive {word}): {failure_text}`, and its own
   docstring says "The message carries the failure text verbatim".
3. So the page read `'NoneType' object has no attribute 'epic_state'` — a true
   statement about a stack frame and a useless statement about a factory. What
   it meant was: the scheduler is dead, nothing will build until you clear it,
   and here is the command. The operator was paged twice, hours apart, and acted
   on neither; the floor idled about 3h27m across the two outages.
4. The same path fans out per spec. `factory/roadmap/workflow.py:1387` —
   `_drift_resolver` calls the reporter from inside the per-spec drift loop, so
   one fault that fails every spec in the corpus sends one notice per spec: 63
   in six minutes on 2026-08-19, and 66 Telegram sends.
5. The throttle that should have stopped the flood cannot see the cause.
   `factory/activities/notify_activities.py:680` — `record_roadmap_failure`
   raises the consecutive count only when `last_failure_text` is byte-identical
   to the previous one, and `drift_for_spec(020-…) failed: …` and
   `drift_for_spec(021-…) failed: …` are different strings. The count reset to 1
   sixty-three times, so `factory/roadmap/workflow.py:152` —
   `_should_notify_failure` returned True every time. The throttle is correct;
   what it keys on is wrong.

Two messages in the corpus already get this right, and they are the model rather
than victims. `factory/notify/messages.py:414` — `escalation_message` ends "No
answer by {expires_at} applies the default: …" and, since 079 landed on
2026-08-22, also carries `factory/notify/messages.py:358` —
`render_blast_radius`, one line per offered button naming what it does to the
node and to the epic. `factory/notify/messages.py:484` — `question_message`
carries the same shape in a register with no keyboard: "Reply to this message
with your answer" is the option, and "No answer by {expires_at} lets the node
proceed as a FAIL" is the consequence of silence. Everything this spec asks for,
those two messages already do.

## The rule this spec is asking for

**A message the factory sends an operator states what stopped, what it costs to
do nothing, and what the options are — and one cause sends one message, however
many specs it touched.**

Every message the factory composes for a human, complete. There are exactly six
call sites of `factory/notify/messages.py:656` — `_compose`, one per composer,
plus the stack heartbeat, which is composed elsewhere. This table is the whole
enumeration and the only one: where a story, a requirement or a task says "every
notice", it means the rows marked **changed**.

| message | this spec | names what stopped | names options | names what silence does | carries the raw text |
|---|---|---|---|---|---|
| roadmap failure notice | **changed** (US1, US2) | yes, in factory vocabulary, with the affected spec count | yes, as commands | yes — the next scheduled pass, or "this will not clear itself" | **no** — a pointer to the record |
| roadmap recovery notice | **changed** (US2) | yes — what resumed | one line: there is nothing to decide | the same line: nothing is pending, so silence costs nothing | no |
| manual-intervention notice | **out of scope** | — | — | — | — |
| escalation message | **control** | unchanged | unchanged (`render_blast_radius`) | unchanged ("No answer by …") | unchanged |
| question message | **control** | unchanged — the agent's own question is the body | unchanged ("Reply to this message with your answer") | unchanged ("No answer by … lets the node proceed as a FAIL") | unchanged |
| resolution notice | **out of scope** | — | — | — | — |
| stack heartbeat | **out of scope** | — | — | — | — |

The rows in order: `factory/notify/messages.py:329` —
`roadmap_failure_notice`, `factory/notify/messages.py:344` —
`roadmap_recovery_notice`, `factory/notify/messages.py:313` —
`manual_intervention_notice`, `factory/notify/messages.py:414` —
`escalation_message`, `factory/notify/messages.py:484` — `question_message`,
`factory/notify/messages.py:502` — `resolution_notice`, and
`factory/supervision/probe.py:376` — `decide_alert`.

A **control** is a message that already satisfies this spec's rule and whose
rendered text FR-012 requires to come out of the diff byte-identical. The two
controls are not exempt from the rule; they are the proof it can be met, and a
diff that improved the two changed notices by restructuring either of them has
lowered the corpus rather than raised it.

Three rows are **out of scope**, for three different reasons, and the
differences matter when this spec is next read. The resolution notice is
delivered and has nothing left to decide. The stack heartbeat has a decision in
it and belongs to another surface. The manual-intervention notice has plenty to
decide and is never delivered at all: nothing in production calls it. The next
section says how each of those was established.

### What this spec is not

It is not a change to the escalation. 079 landed the model this spec
generalises; FR-012 makes an escalation that got shorter, vaguer or restructured
a test failure rather than a judgement call.

It is not a change to the question message either. 008-US1 landed
`factory/notify/messages.py:484` — `question_message` with both halves of the
rule already in it, and the tempting move in US2 — rephrasing every silence
sentence into one house style — would rewrite the one that has been correct
since 008. FR-012 covers it for the same reason it covers the escalation.

It is not a change to the resolution notice.
`factory/notify/messages.py:502` — `resolution_notice` fires after the decision
is in: the buttons are gone, the choice is recorded, and its footer is either
"Resolved by button: X." or the expiry line. "What happens if you do nothing"
has no referent there, so FR-008, FR-009 and FR-010 do not reach it, and adding
an options block to a message with nothing left to decide is exactly the "more
messages, more lines" failure the last paragraph of this section refuses.

It is not a change to the manual-intervention notice, and the reason is that
nothing sends it. `factory/notify/messages.py:313` —
`manual_intervention_notice` is defined once and called nowhere in production:
`grep -rn manual_intervention --include=*.py factory/` returns that definition
and nothing else, and every remaining reference in the repository is a test —
the import at `tests/test_messages.py:40` and
`tests/test_messages.py:245` — `test_manual_intervention_notice_renders_with_no_buttons`.
`factory/notify/service.py:77` imports only `resolution_notice` of this family,
and the merge-queue outcome that would produce the fact the notice describes,
`factory/mergequeue/classify.py:74` (`DEQUEUED_BY_HUMAN`), composes no message
at all. An earlier draft of this spec marked it **changed** and spent two US2
scenarios and four US2 tasks on it — a third of that story's diff written into
text no operator will ever receive, and invisible to the one verification step
("count a normal day") that would otherwise have caught it. Wiring it to a send
site is a real want and it is not this spec: a send site is a production file
outside `factory/notify/messages.py`, and the Work Graph's justification for
running US2 and US3 concurrently rests on US2 having none.

It is not a lengthening of the heartbeat, and not because the heartbeat has no
decision in it. `factory/supervision/probe.py:376` — `decide_alert` is a
three-branch edge trigger, and its *first* branch pages on a first DEGRADED
observation carrying `verdict.detail` unedited — a message that says something
stopped, names no option and names no consequence of silence, which is the exact
shape FR-008 and FR-009 exist to fix. It is out of scope by decision: the stack
probe is 042's surface with its own alert vocabulary, its own state machine and
its own suite, and pulling it into a spec about the roadmap's notices would
widen the diff of the story already carrying the most. It is named here so the
next refinement does not have to rediscover that it was considered and declined.

It is not a keyboard on a notice. 031 decided that a notice offers no choice
over the wire — no inline keyboard, no offered choice, no response deadline, no
pending escalation row — and that decision stands. A notice's options are
commands the operator runs, not buttons the bridge would have to refuse.

It is not a reduction in what is recorded. The `roadmap_failures` row keeps the
verbatim text, written before any send. The phone gets the decision; the store
keeps the truth.

It is not more messages. A change that improved every message and raised the
count would have failed the operator who asked for this.

## User Scenarios & Testing

### User Story 1 - A failure notice says what stopped and what it blocks (Priority: P1)

As an operator reading my phone, I learn what has stopped working and what it
costs me, without opening a terminal.

**Why this priority**: P1 and it depends on nothing. It is the whole complaint,
and it builds the one thing US2 and US3 both need: a failure that arrives at the
composer as a named cause rather than as a sentence nobody can classify.

**Independent Test**: Report a known internal failure and read the notice text
and the store row it wrote: the notice states impact and carries no exception
repr, the row still holds the repr.

**Acceptance Scenarios**:

1. **Given** a roadmap pass that fails with `'NoneType' object has no attribute
   'epic_state'`, **When** the failure notice for it is composed, **Then** the
   text names the stage that stopped in the factory's own vocabulary, still
   names the consecutive-failure count, and does not contain that string —
   proven by a committed test using that exact input, because it is the string
   that actually failed a human, twice.
2. **Given** the same failure, **When** the notice is composed, **Then** it
   states what will not happen until the failure is resolved, and — when one
   cause failed more than one spec in the pass — how many specs it affected —
   proven by a committed test asserting both halves.
3. **Given** a cause the composer has no specific wording for, **When** the
   notice is composed, **Then** it still states impact and options and points to
   where the verbatim text is recorded, and the failure text is not the body —
   proven by a committed test over a cause the composer does not know. A
   fallback that prints the raw text has not changed the operator's experience,
   only postponed it.
4. **Given** one reported failure whose notice omits the exception repr,
   **When** the `roadmap_failures` row written by that same report is read,
   **Then** `last_failure_text` still holds the repr verbatim — proven by one
   committed test asserting both halves together, because the record half passes
   today, before any change, and only the pair can fail a diff that cleaned up
   the page by dropping the evidence.
5. **Given** a composed failure notice, **When** its lines are indexed,
   **Then** the impact line, the options block and the pointer to the
   `roadmap_failures` record are all three present and appear in that order —
   proven by one committed test comparing all three indices. Two indices would
   not be enough: the notice carries no failure detail at all once FR-001 lands,
   so an ordering claim written against "any line carrying failure detail" would
   be comparing against an empty set and would pass by omission. The 7:00 AM
   message put six lines of shell stderr above everything that mattered.
6. **Given** a failure text that is a shell stderr tail containing a value
   matching `_SECRET_PATTERNS`, **When** the failure is reported, **Then**
   neither the stderr tail nor the matching value appears in the composed
   notice, and the `roadmap_failures` row that same report wrote still holds
   both — proven by one committed test importing those patterns from
   `factory/controlplane/config.py` rather than restating them. The notice half
   fails today, because the composer interpolates the failure text whole; the
   row half passes today, and only the pair can fail a diff that protected the
   credential by dropping the record.
7. **Given** two different failure texts reported under one named cause and one
   failure text reported under two different named causes, **When** each notice
   is composed, **Then** the first pair share an impact statement and the second
   pair do not — proven by one committed test asserting both directions, which a
   composer that classified by matching the failure text cannot satisfy.

---

### User Story 2 - Every notice states the options and what silence does (Priority: P1)

As an operator, I can decide from the message itself, and I know what happens if
I decide nothing.

**Why this priority**: P1 and it waits on US1 having landed a cause to read.
This is the operator's literal request — a brief description of the issue and
the options to make the decision — and the escalation and the question message
already prove the shape works.

**Independent Test**: Compose the two changed notice kinds and read each one
for an options block, a silence sentence, and a command that the real CLI parser
accepts; then compose the two controls and diff them against today's output.

**Acceptance Scenarios**:

1. **Given** the two notices the rule's table marks **changed** — the roadmap
   failure notice and the roadmap recovery notice — **When** each is composed,
   **Then** each names its options as actions the operator can take, or says in
   one line that there is nothing to decide — proven by one committed test that
   composes both by name. "The workflow is in a failed state" is a description;
   "terminate the run so a fresh one starts" is an option, and the test for a
   line is whether an operator could do it.
2. **Given** those same two notices, **When** each is composed, **Then** the
   roadmap failure notice states what happens if the operator does nothing, and
   the recovery notice's single nothing-to-decide line stands as its answer,
   since its cause has already cleared — proven by one committed test naming
   both. This is the escalation's existing sentence generalised, and it is the
   single highest-value line in the corpus.
3. **Given** a notice for a cause that will not clear itself and a notice for a
   cause the next scheduled pass will retry, **When** each is composed,
   **Then** the first says so explicitly and the second names the mechanism that
   will retry rather than a wall-clock time the composer cannot know — proven by
   one committed test over both. The scheduler wedge never cleared on its own,
   and a message that reads like a transient error invites exactly the waiting
   that cost two hours.
4. **Given** the two changed notices, **When** the `ergane` invocations each one
   declares are collected, **Then** the collected set is not empty, every
   invocation in it parses under `tests/page_holds_true.py:180` — `parse_argv`,
   each one's rendered form appears verbatim in the notice that declared it, and
   no rendered form contains an angle-bracket placeholder — proven by one
   committed test. All four halves are load-bearing: a sweep that found nothing
   would pass vacuously; a declared invocation no notice prints would pass a
   parser check while the operator's phone still named a command that does not
   exist; and `ergane roadmap status <specs-root>` parses, because argparse
   accepts any string for a positional, while being the one thing an operator
   cannot type.
5. **Given** an escalation record, a question record and a roadmap failure,
   **When** all three messages are composed, **Then** the escalation still
   carries its blast-radius block and its "No answer by …" sentence unchanged,
   the question message still carries "Reply to this message with your answer"
   and its "No answer by … lets the node proceed as a FAIL" sentence unchanged,
   and the roadmap failure notice carries the what-silence-costs sentence
   FR-009 requires and at least one command line rendered from an invocation it
   declares, while still naming no inline keyboard, no offered choice and no
   response deadline — proven by one committed test asserting all three. **The
   controls ride with the change**: all three control halves are already
   satisfied on this story's base — the escalation and the question message
   because they have been right since 079 and 008, and the notice's no-keyboard
   half because `tests/test_messages.py:290` —
   `test_roadmap_failure_notice_offers_nothing_and_names_no_deadline` has
   asserted it all along — as is the options block, which US1 lands under FR-003
   and FR-005. The silence sentence and the rendered command are what US2 itself
   adds, so they are the halves that fail before the implementation; the
   controls ride along to refuse a diff that raised the two changed notices by
   restructuring the two that were already right.
6. **Given** a roadmap pass that succeeds after prior failures, **When** the
   recovery notice is composed, **Then** it names what resumed and not only that
   recovery happened — proven by a committed test. "Recovered after 1
   consecutive failure" does not tell an operator whether their work started
   moving again.

---

### User Story 3 - One cause is one message (Priority: P2)

As an operator, a single fault that touches fifty specs pages me once.

**Why this priority**: P2 only because US1 and US2 make each individual message
worth reading. Sixty-three readable messages is still an unusable phone. It
waits on US1 having landed the named cause, which is the thing a count can key
on.

**Independent Test**: Drive one persistent fault across a full corpus pass and
count the notices the operator received.

**Acceptance Scenarios**:

1. **Given** a pass in which one cause fails every spec in the corpus, with
   failure texts differing only by spec name, **When** the pass completes,
   **Then** the operator received exactly one notice and it names how many specs
   the cause affected — proven by a committed test driving a multi-spec corpus.
   On 2026-08-19 this shape produced 63 notices in six minutes.
2. **Given** that same single pass, **When** the `roadmap_failures` row is read
   after it, **Then** the consecutive count for that cause is exactly 1, and
   **Given** the same cause persisting across the next two passes with a
   different failure text each time, **When** those passes run, **Then** the
   count rises 1, 2, 3 across them instead of resetting, and the notices fall to
   the geometric throttle's rate — proven by one committed test reading both the
   count the store holds and the number of notices sent after each pass. The
   count-after-one-pass half is the guard: a report per spec would drive it to
   63 in one pass, and 63 is not a power of three, so the one notice scenario 1
   promises would never be sent at all.
3. **Given** one pass in which most specs fail on one cause and at least one
   fails on a different cause, **When** the pass completes, **Then** exactly two
   notices were sent, one per cause — proven by one committed test asserting the
   count is two. Today that pass sends one notice per spec, so the assertion
   fails before the change; collapsing distinct causes is a worse failure than
   repeating one, and this scenario refuses both.

## Functional Requirements

- **FR-001**: A roadmap failure notice MUST state what has stopped in factory
  vocabulary, MUST continue to name the consecutive-failure count, and MUST NOT
  contain the raw exception repr or shell stderr that produced it.
- **FR-002**: A failure notice MUST state the blast radius — what will not
  happen until the failure is resolved — and, when one cause failed more than
  one spec in the pass, how many specs it affected.
- **FR-003**: A cause the composer has no specific wording for MUST still
  produce an impact-and-options notice carrying a pointer to where the verbatim
  text is recorded, and MUST NOT fall back to rendering the failure text as the
  body.
- **FR-004**: The verbatim failure text MUST remain written to `roadmap_failures`
  before any send is attempted, and MUST remain retrievable from that row for the
  same report whose notice omits it.
- **FR-005**: A composed failure notice MUST carry an impact statement, an
  options block and a pointer to the `roadmap_failures` record, all three
  present, in that order.
- **FR-006**: A composed notice MUST NOT render the failure text, whole or as a
  quoted span of it, on any path; and in particular MUST NOT carry a value
  matching `_SECRET_PATTERNS` taken from a report whose `roadmap_failures` row
  still holds it.
- **FR-007**: A failure's cause MUST be named by the code that reports it and
  travel to the composer as a value; the composer MUST NOT decide what stopped by
  matching the failure text.
- **FR-008**: Each of the two notices the rule's table marks **changed** —
  `roadmap_failure_notice` and `roadmap_recovery_notice` — MUST name its options
  as actions the operator can take, or state in one line that there is nothing
  to decide. No other composer is in this requirement's scope, and in particular
  `manual_intervention_notice` is not, because nothing in production sends it.
- **FR-009**: Of those same two, the roadmap failure notice MUST state what
  happens if the operator does nothing; the recovery notice, whose cause has
  already cleared, satisfies this with the one nothing-to-decide line FR-008
  requires of it and MUST NOT gain a second sentence.
- **FR-010**: A failure notice MUST say whether its cause clears itself, and
  where it does MUST name the mechanism that will retry rather than a wall-clock
  time.
- **FR-011**: Every `ergane` command a changed notice names MUST be rendered
  from an invocation the composer holds as a value, built only from data the
  composer is already given; every such invocation MUST parse under the real CLI
  parser through `tests/page_holds_true.py:180` — `parse_argv`; the set of
  declared invocations MUST NOT be empty; each invocation's rendered form MUST
  appear verbatim in the notice that declared it; and no rendered form may
  contain an angle-bracket placeholder. `tests/page_holds_true.py:301` —
  `extract_commands` and `tests/page_holds_true.py:292` —
  `assert_commands_not_dropped` MUST NOT be used over notice text, and no second
  CLI parser may be introduced.
- **FR-012**: The escalation message's body, blast-radius block and
  default-on-silence sentence, and the question message's reply line and its
  "No answer by … lets the node proceed as a FAIL" sentence, MUST all be
  unchanged; and no notice may gain an inline keyboard, an offered choice or a
  response deadline.
- **FR-013**: A recovery notice MUST name what resumed.
- **FR-014**: One cause failing many specs in one pass MUST produce one notice,
  naming how many specs it affected, and MUST write one `roadmap_failures`
  update for that cause in that pass — one before the send, as FR-004 requires,
  and not one per affected spec.
- **FR-015**: The consecutive-failure count MUST key on the named cause rather
  than on the failure text, MUST be 1 after a single pass however many specs the
  cause failed, and any column the store needs for that MUST be added by an
  additive migration rather than by editing the existing
  `CREATE TABLE IF NOT EXISTS`.
- **FR-016**: Two distinct causes in one pass MUST both be reported.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-008, FR-009, FR-010, FR-011, FR-012, FR-013]
US3:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-014, FR-015, FR-016]
```

Both edges are `depends_on_merged` and both are declared rather than left
inferred. US2 rewrites two composers in `factory/notify/messages.py`, the file
US1 restructures, so the two cannot be in flight against the same base without
the second landing into a conflict it did not cause. US3 changes
`factory/roadmap/workflow.py`, the file US1 threads the named cause through, for
the same reason — and it needs that cause to exist before a count can key on it.
Neither edge is a pass edge: waiting for US1's verification would not stop
either collision, because a verified-but-unlanded US1 is not in the base US2 and
US3 branch from.

US2 and US3 carry no edge between them and are meant to run concurrently once
US1 lands: US2 touches `factory/notify/messages.py` and the message tests, US3
touches `factory/roadmap/workflow.py`,
`factory/activities/notify_activities.py` and the roadmap-notification tests, and
they name no production file in common. US3 does not edit the composer at all —
US1 gives the notice a field for the affected spec count and US3 fills it.

That no-common-file sentence rests on a constraint US2 must honour and it is
stated here because it is where the claim lives: **US2 may not change any
composer's signature.** `factory/roadmap/workflow.py:1073` calls
`roadmap_failure_notice` and `factory/roadmap/workflow.py:1103` calls
`roadmap_recovery_notice`, so a new parameter — for the specs-root positional
FR-011's commands need, most temptingly — pulls `factory/roadmap/workflow.py`
into US2's diff, puts it in the same file US3 is rewriting, and makes this
paragraph false. US1 sets the signatures both later stories live with; plan trap
17 names the seam that makes a new parameter unnecessary.
