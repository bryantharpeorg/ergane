---
state: draft
# DRAFTED 2026-08-28 by the operator session, against ergane-buildout at 8bb2d4b.
# 8bb2d4b is one spec-only commit ahead of origin/ergane-buildout at b5bffad;
# every `factory/` and `tests/` anchor below is byte-identical on both, and each
# was read from the tree rather than recalled.
#
# WHY THIS EXISTS. There is today no durable place to put something that is not
# yet a defect and not yet a spec. The operator's options are cross-session
# memory — which, as `CLAUDE.md` states, reaches no implementer because nothing
# dispatches it — or writing a spec trio, which is the expensive step the
# operator is trying to defer. So the thought is held in a head, and the head is
# the one component with no backup.
#
# THE STORE ALREADY EXISTS AND IS ALREADY THE RIGHT SHAPE. The doctor's ledger
# (`.factory/doctor.db`) is durable, identity-keyed on `category/slug`, counts
# recurrences, carries an append-only `finding_events` trail, refuses
# credential-like input on the way in, and has `promote` — a verb that already
# scaffolds a spec directory from selected keys. It held 138 open rows when this
# was drafted. Nothing about it needs replacing. What it lacks is a lane that is
# not a defect, a verb whose name means one thing, and a way out that hands a
# drafter everything it needs.
#
# WHY NOT GITHUB ISSUES. Considered and rejected by the operator on 2026-08-28,
# for a reason that is about readers rather than mechanism: an open issue list is
# read by anyone who finds it as a defect backlog. A stranger scrolling forty
# open issues concludes the system is broken; they cannot tell "this is a
# collection of things somebody wants" from "this is a list of things that do not
# work". The same hazard exists *inside* the ledger, which is why US2 is not
# cosmetic — it is the same argument applied to the operator's own health count.
# The mechanical objections are secondary but real: a second source of truth
# outside the tree, which neither `triage` nor `promote` can read without new
# plumbing, and which `ergane uninstall` would have to learn about.
#
# WHY NOT A TEMPORAL QUEUE. A signal-fed inbox workflow would need
# `continue-as-new` to outlive retention, plus a hand-rolled query surface and
# hand-rolled dedup — a database written inside a workflow engine to obtain what
# one SQLite table already provides. Temporal is the right host for a worker that
# reads the queue on a schedule. It is the wrong host for the queue.
#
# THE NAMING DEFECT IS REAL AND WAS FOUND BY READING THE HELP TEXT. `ergane
# findings report` reads as both "file a report" and "run a report", and the
# subparser's own help string is `record a finding` — the code already knows the
# word it wants. `CONTEXT.md` has resolved exactly this shape before, for
# `promote`, where four senses lived in the tree simultaneously; the resolution
# there was to name one sense, qualify the others, and let landed identifiers
# keep their names. This spec applies that precedent.
#
# NOT IN SCOPE. This spec does not invoke an agent, does not put anything on a
# Temporal schedule, does not migrate the store's schema, does not change what
# any probe files, and does not alter the recurrence machine at
# `factory/doctor/store.py:137`. It adds one lane, renames one verb, and adds one
# read-only verb that assembles a brief.
---

# Feature Specification: the ledger takes what is not yet a defect

**Created**: 2026-08-28
**Depends on**: nothing outside this spec. US1 → US2 → US3 are sequential, and
the reason is file contention rather than logic: all three edit
`add_findings_parser` in `factory/cli/doctor.py:251-350`.

## The gap, stated precisely

The factory can record a defect, count how often it recurs, decide what a landed
spec has closed, and scaffold a spec directory from what remains. It cannot
record a want.

That is not a small omission, because the routing table in `CLAUDE.md` has only
three destinations and none of them fit. A binding rule requires a defect class
that has bitten twice. A finding requires "mechanism and evidence" — a
`file:line` and a reproduction. Cross-session memory accepts anything and
dispatches nothing. So an idea that is merely *good* has nowhere to go, and the
observed consequence is that it is rediscovered later by an agent, at full price,
or not at all.

Three specific things stand between the ledger and that job:

1. **The write verb's name means two things.** `ergane findings report` is read
   as "file a report" by the person filing and as "run a report" by the person
   reading. Both readings are natural; that is what makes it a defect rather
   than a preference.
2. **There is no lane.** `category` is documented in the schema itself as an
   *open taxonomy* (`factory/doctor/store.py:52`) and nothing validates it, so a
   `feedback/` prefix costs nothing to adopt — but `findings list`
   (`factory/cli/doctor.py:266-273`) filters only on `--severity` and
   `--status`. Feedback filed today is indistinguishable from a defect in every
   view, and inflates the open count the operator reads as a health signal.
3. **There is no way out that saves any work.** `promote`
   (`factory/cli/doctor.py:514`) produces a spec directory whose text is a
   scaffold, and everything that makes a spec worth dispatching — the evidence,
   the anchors, the traps, the acceptance scenarios — still has to be assembled
   by hand from a store the drafter has to know how to query.

## The rule this spec is asking for

**Something not yet a defect has a durable home that says it is not a defect,
and getting it out again hands the drafter the evidence instead of the task of
finding it.**

### What this spec is not

It is not a second dispatcher. `ergane findings draft` assembles a brief and
stops; the agent that consumes it is invoked by the operator, in a separate
process, by whatever means the operator already uses. The node adapter
(`factory/workgraph/adapter.py:922`) is shaped around an `AttemptContext` — a
worktree, a heartbeat, a pid file, a per-node HOME, a transcript archive — and
reaching for it here would build a second lifecycle to run one prompt.

It is not a schedule. Putting the drafter on a tick beside `ergane-roadmap` is
the obvious next move and is deliberately deferred: an unattended drafter writes
specs nobody asked for, and this repository's own measured position is that the
leverage is in refinement, which is where the operator's judgment lives. Ship
the verb, watch the drafts, schedule it when they stop needing a reader.

It is not a schema migration. `severity` is pinned by a `CHECK` constraint
(`factory/doctor/store.py:53-54`) and `status` by another
(`:55-56`). Feedback is filed at `info`, which is an accepted compromise rather
than a good fit, and it is named as one so that no implementer invents a fourth
severity to make it fit better.

## User Scenarios & Testing

### User Story 1 - The write verb says it writes (Priority: P1)

As an operator filing something into the ledger, I type a verb that can only
mean writing, so the command I run and the command I read are not the same word.

**Why this priority**: P1 and first. US2 and US3 both add surface to the same
parser function, and a rename landing after them is a rename that has to touch
their work too.

**Independent Test**: run `ergane findings record` and `ergane findings report`
against a scratch store and compare the rows they produce; then read
`ergane findings --help` and `ergane completion bash` for the old name.

**Acceptance Scenarios**:

1. **Given** a scratch store, **When** the same finding is filed once through
   `ergane findings record` and once through `ergane findings report`, **Then**
   the resulting row is identical in every column and the recurrence machine
   advanced exactly as it does today — proven against the store, not against the
   parser, because the point of the alias is that behaviour did not change.
2. **Given** `ergane findings report`, **When** it runs, **Then** it succeeds
   with the same exit status and writes a deprecation line **to stderr** naming
   `record`. On stdout it would corrupt the output of anything parsing the
   command, and the in-tree callers are documentation and a skill, both of which
   a human reads.
3. **Given** `ergane findings --help` and `ergane completion bash`, **When**
   either is read, **Then** neither offers `report`. A deprecated alias
   advertised by shell completion is not deprecated; it is a second supported
   name with a note attached.
4. **Given** the three places in the tree that name the old verb in prose —
   `CLAUDE.md:106`, `docs/architecture.md:518`,
   `.claude/skills/away-mode/SKILL.md:158` — **When** this story lands, **Then**
   each names `record`, and a test asserts the old verb string appears in no
   operator-facing document. `tests/test_claude_md.py` already holds `CLAUDE.md`
   to the rule that every command it names must resolve; this keeps that true
   rather than relying on it to notice.

### User Story 2 - A want is not a defect, and the ledger can tell (Priority: P1)

As the operator reading a findings list, I see defects by default and am told how
many non-defects I am not being shown, so the open count keeps meaning what it
means today.

**Why this priority**: P1. Without it the lane is a naming convention the
operator has to remember, and the first consequence of forgetting is the exact
failure the GitHub Issues objection describes — a list that reads as a defect
backlog to whoever opens it, including the operator six weeks later.

**Independent Test**: file one defect and one feedback row into a scratch store,
then read `findings list` with no flags, with `--category feedback`, and with
`--all`.

**Acceptance Scenarios**:

1. **Given** a store holding both defect rows and `feedback/` rows, **When**
   `ergane findings list` runs with no filters, **Then** the feedback rows are
   absent and the output states how many were withheld and the flag that shows
   them. A view that silently drops rows is worse than one that never had the
   lane, because it makes the operator confident about a number that is now
   partial.
2. **Given** the same store, **When** `--category feedback` is passed, **Then**
   only feedback rows are listed; **and when** `--all` is passed, **Then**
   everything is listed. The filter composes with `--severity` and `--status`
   rather than replacing them.
3. **Given** the probe registry (`factory/doctor/probes.py:628`), **When** every
   registered probe is run, **Then** none of them files into the reserved
   category — asserted by a guard over the registry, so a probe added later that
   reaches for the word turns the suite red instead of quietly polluting the
   lane that exists to stay clean.
4. **Given** `ergane findings triage`, **When** it classifies a store containing
   feedback rows, **Then** those rows are reported under their own heading and
   are never folded into a defect fragmented class
   (`factory/doctor/triage.py:444`). A want grouped with three bugs because they
   share a word produces a fragmented-class recommendation the operator cannot
   act on.

### User Story 3 - Getting it out again hands over the evidence (Priority: P2)

As a drafting agent, I receive one brief that already contains the finding's
whole history and the contract my output must satisfy, so I spend my context
writing the spec rather than discovering how to write one here.

**Why this priority**: P2. US1 and US2 make the queue real and legible; this is
what makes it worth having. It is last because it is the largest, and because a
brief written against a lane that does not exist yet would have to be revised
when it does.

**Independent Test**: file a feedback row with notes and refs, report it twice
more to build a trail, then run `ergane findings draft --key <key>` and read the
file it names.

**Acceptance Scenarios**:

1. **Given** one or more finding keys, **When** `ergane findings draft` runs,
   **Then** it writes one brief to a file and prints that path, changes no row
   and no status, and produces the same brief when run again. A queue-reading
   verb that mutates the queue cannot be run twice to see what it says.
2. **Given** a finding reported three times across two days, **When** the brief
   is written, **Then** it carries every stored column *and* the full event trail
   from `list_events` (`factory/doctor/store.py:493`) — not the summary alone.
   Occurrence count and first-seen date are the difference between "somebody
   thought this once" and "this has come up three times since Tuesday", and that
   difference is most of what a drafter needs to judge priority.
3. **Given** the brief, **When** it states what the drafter must produce,
   **Then** the trio's shape is drawn from the repository's own templates in
   `.specify/templates/` rather than restated in the command's source, and the
   brief names `ergane spec validate` as the acceptance test its output must
   pass. A brief carrying a second copy of the spec format is a copy that drifts
   from the validator while both stay green.
4. **Given** the command, **When** it finishes, **Then** it has invoked no agent,
   written nothing under `specs/`, and opened no network connection — proven by a
   test that runs it with no credentials and no network. The whole reason this
   story is affordable is that it assembles text; a version that grew a
   dispatcher would have acquired the node lifecycle it was written to avoid.

## Work Graph

```yaml
US1:
  implements: []
  depends_on: []
US2:
  implements: []
  depends_on: []
  depends_on_merged: [US1]
US3:
  implements: []
  depends_on: []
  depends_on_merged: [US2]
```

All three stories add or change verbs inside `add_findings_parser`
(`factory/cli/doctor.py:251-350`), so they are serialised on file ownership
rather than on logic. See `plan.md` § *File contention* for why this is stated as
a dependency instead of left to the merge.

## Requirements (summary — numbered at refinement)

The write verb is `record`; `report` still works, warns on stderr, and appears in
neither `--help` nor completion; the three prose call sites are updated and
pinned. `findings list` gains a `--category` filter, hides the reserved
`feedback` lane by default while stating what it hid, and offers `--all`; no
probe may file into that lane; triage reports it separately and never folds it
into a defect class. `findings draft` writes one brief per invocation carrying
every stored column and the full event trail, states the trio contract from the
repository's own templates, names `ergane spec validate` as its acceptance test,
and invokes nothing.

## Success Criteria (summary)

Pasted: the two rows produced by `record` and by `report`, shown identical; the
deprecation line on stderr with stdout shown clean; the `findings` line of
`ergane completion bash` before and after; `findings list` output with the lane
hidden and the withheld count shown, then with `--category feedback`, then with
`--all`; the probe-registry guard failing against a deliberately mislabelled
probe; a written brief for a finding reported three times, with its event trail
visible; and the full-suite before-and-after counts for each story.

**Operator verification, which is the point of the spec**: after US3 lands, file
a real want that has been sitting in memory, run `ergane findings draft` over it,
hand the brief to a drafting session, and see whether what comes back needs less
work than starting from the spec template. If it does not, US4 — the schedule —
is correctly deferred and should stay that way.
