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
# `factory/doctor/store.py:137` — `report`. It adds one lane, renames one verb,
# and adds one read-only verb that assembles a brief.
#
# REFINED 2026-09-04 by the refinement workflow (refinement-2026-09-04); every
# anchor in spec.md, plan.md and tasks.md re-read from ergane-buildout at
# 602a92c. No `fixes:` key was declared at drafting and none is added: no open
# ledger row names the verb's name, the lane or the brief, so there is nothing
# here to declare whole.
#
# TWO ANCHORS POINTED AT THE WRONG CODE, AND SIX RANGES ENDED ON A BLANK LINE.
# `factory/workgraph/adapter.py:922` now lands inside a gitconfig-writing helper;
# `ClaudeCodeAdapter` moved to `factory/workgraph/adapter.py:993`. `docs/architecture.md:518` is now a
# paragraph about the judge and CI; the line naming the verb moved to `docs/architecture.md:558`.
# Both are re-anchored in the symbol-tier form where a symbol is meant, so the
# next drift is machine-caught rather than read past.
#
# THE PROSE SCOPE OF FR-004 WAS WRONG, AND IT WOULD HAVE FAILED ITS OWN GUARD.
# The three call sites named at drafting are now nine lines in six tracked files:
# `docs/cli/findings.md` landed 2026-09-01 (`3e4ab2f`) with the verb in a
# synopsis twice and a section heading once, and `.claude/skills/findings-ingest/`
# landed 2026-08-29 (`8edc028`) naming it three more times. An implementer
# obeying the old list would land a rename whose own sweep test turns red.
#
# THE LANE IS NO LONGER HYPOTHETICAL, AND THAT SHARPENS US2. Measured on the live
# ledger 2026-09-04: 520 rows, 279 open or regressed, of which **23 are already
# `feedback/`** and 106 are critical. The ingest skill has been filing into the
# lane since 2026-08-29 and encodes its `info` rule in prose. Two of its own
# `findings list --json` call sites read every row on purpose, so US2 breaks them
# unless the same story fixes them — folded into FR-006 and US2-S2.
#
# US2-S3 WAS PASSABLE BY A TEST-ONLY DIFF, AND UNPROVABLE OFFLINE BESIDES. "Run
# every registered probe and assert none files into the lane" is true today with
# no production change, and running a probe calls `gather()`, which wants
# Temporal. FR-007 is now a refusal at the one choke point every probe finding
# passes through, proven non-vacuous by a synthetic probe.
#
# FR-011 SENT THE IMPLEMENTER TO A TEMPLATE SET THAT NO LONGER DESCRIBES THE
# CONTRACT. `.specify/templates/spec-template.md` has not been touched since
# 2026-08-06: it has no `## Work Graph` at all, puts Functional Requirements at
# level 3 under `## Requirements`, and still teaches `### Edge Cases` and
# `## Success Criteria`. A brief built from it would teach a drafter a shape
# `ergane spec validate` refuses and `derive_workgraph` cannot compile. FR-011
# now reads the shape from `scaffold_spec`, whose output `findings promote` puts
# through `derive_workgraph` before it will accept it.
#
# STRUCTURE. The twelve requirements moved out of plan.md into a level-2
# `## Functional Requirements` section here, `implements:` is declared on all
# three stories, and the two summary sections the house style dropped after 126
# are gone. Story numbers, titles and the US1 → US2 → US3 chain are unchanged.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04): the `findings list --json`
# consumer sweep was two call sites and the tree holds three — the mandated
# corpus dump at `.claude/skills/findings-ingest/SKILL.md:77` is added to FR-006,
# US2-S2, trap 11 and T019, and
# `.claude/skills/findings-ingest/SKILL.md:136` is re-described as the
# category-reuse check it actually is; FR-003's help half named no mechanism that can deliver it
# — measured, every shape the old T006 permitted prints `report` in argparse's
# usage metavar, so an explicit `metavar` on the findings `add_subparsers` plus a
# help-less second parser is now named, with the measurement in plan.md § *The
# alias trap, measured* and trap 13; the noun description at
# `factory/cli/doctor.py:262` still says "Report" and is now in FR-003's scope;
# FR-007 says which of refuse-and-abort or skip-and-continue it means and names
# the unwired twin `factory/doctor/cli.py:257`; FR-011 says which scaffold branch
# carries the `derive_workgraph` proof; T020's evidence was ~240 KiB against a
# 64 KiB refusal and is now bounded, with plan.md § *Sizing* carrying the
# measured bytes (trap 14). Two symbol anchors moved to the machine-checked form.
# No hold text was changed, no key declared, state stays draft.
#
# REPAIRED 2026-09-04, second pass (refinement-2026-09-04), anchors re-read at
# 602a92c. FR-003's `metavar` was a hardcoded brace list and is now *derived*
# from the subparsers' own `_name_parser_map` minus the one deprecated-name
# declaration: measured against argparse, a literal list is exactly what
# `tests/page_holds_true.py:346` — `verbs_of` reads as the verb set, so it would
# have made the `CLAUDE.md`, README and on-ramp guards blind to US3's own
# `draft` — and trap 13 and T006 had disagreed about whether `draft` belonged in
# the literal at all. The fragmentation half of US2 was a provable no-op:
# `_fragmented_groups` skips every key with fewer than three segments and all
# 279 open and regressed rows have exactly two, so gap step 4, FR-008, US2-S4,
# trap 10 and T015 now carry the harm that is real — a want pooled with the
# defects and given no heading of its own. 092 (`c06a556`, `03451a9`,
# 2026-08-30) split the diff constant in two: the refusal is
# `DIFF_REFUSAL_THRESHOLD` at `factory/verify/diffbounds.py:66`, not
# `DIFF_INPUT_LIMIT` at `:47`, and trap 14, § *Sizing* and T021 now say so while
# keeping 64 KiB as the default it still is. US2 gained the
# `docs/cli/findings.md` edit its own FR-009 discipline demands, held by a
# synopsis-to-`--help` guard a prose-only diff cannot satisfy; T001 freezes
# `factory.cli.doctor._utcnow`; T004's `record --help` assertion now excludes
# `--source`'s `reporter source` help string, which carries the substring and
# which FR-001 pins. Correcting the REFINED block above rather than editing it:
# its "no open ledger row names the verb" is too broad —
# `doctor/the-credential-sweep-on-findings-report-refuses-a-note-that-names-the-repositorys-own-epic`
# does name it, is touched and not fixed by anything here, and is declared by
# sibling draft 152, which edits the same write path and is named in plan.md
# § *Dispatch hazards*. Still no `fixes:` key, state stays draft.
#
# REPAIRED 2026-09-04, third pass (refinement-2026-09-04), anchors re-read at
# 602a92c. One blocking defect, in the one task that held FR-006, FR-007 and
# FR-008 to a single name: T016 asked for the reserved category to be asserted
# "by identity rather than by string equality", and that assertion is vacuous.
# Measured on this box, CPython 3.12.3: two modules each containing only
# `X = "feedback"` give `m1.X is m2.X` -> `True`, because CPython interns every
# identifier-shaped literal at compile time — so the guard passed against exactly
# the shape trap 1 exists to forbid, a private `RESERVED = "feedback"` in each of
# the three consumers. T016 is now a substitution: monkeypatch one module
# attribute to a non-identifier sentinel and assert the list's withholding, the
# probe refusal and the triage heading all move with it. T018 names the module
# that holds the constant, the call-time attribute read that lets the patch reach
# every consumer, and the `from ... import` shape that silently defeats it; trap 1
# carries the measurement and drops the vacuous instruction. § *Sizing* gains
# US2's measured estimate (45-55 KiB against the 65,536-byte refusal) and the
# split to make — FR-007 into a new story, never a renumber — if it ever refuses
# on size; no change is required before the flip. No FR, story, scenario or hold
# text changed, no key declared, state stays draft.
---

# Feature Specification: the ledger takes what is not yet a defect

**Created**: 2026-08-28
**Depends on**: nothing outside this spec. US1 → US2 → US3 are sequential, and
the reason is file contention rather than logic: all three edit
`factory/cli/doctor.py:251` — `add_findings_parser`.

## The gap, stated precisely

The factory can record a defect, count how often it recurs, decide what a landed
spec has closed, and scaffold a spec directory from what remains. It cannot
record a want. The routing table in `CLAUDE.md:101-106` has three destinations
and none of them fit: a binding rule needs a defect class that has bitten twice,
a finding needs a mechanism and a reproduction, and cross-session memory accepts
anything and dispatches nothing.

The causal chain, five steps, each read from the tree:

1. **The write verb answers to a name that means two things.** The subparser is
   registered as `report` at `factory/cli/doctor.py:276`, and its own help string
   on that same line is `record a finding`. Read by the person filing it means
   "file a report"; read by the person reading it means "run a report". Both
   readings are natural, which is what makes it a defect rather than a taste.
2. **Nothing stops a want being filed, so wants are already there.** `category`
   is documented in the schema itself as an open taxonomy
   (`factory/doctor/store.py:52`) and no `CHECK` constrains it, so a `feedback/`
   prefix costs nothing to adopt — and it has been adopted:
   `.claude/skills/findings-ingest/SKILL.md:150-161` routes every want into
   `feedback/…` at `info`, and has done since 2026-08-29.
3. **Every view then counts those wants as defects.** `findings list` registers
   `--severity`, `--status` and `--json` and nothing else
   (`factory/cli/doctor.py:266-273`), and `factory/cli/doctor.py:368` —
   `findings_list_command` applies exactly those two filters over the unfiltered
   read `factory/doctor/store.py:454` — `list_findings`. Measured on the live
   ledger on 2026-09-04: 279 open or regressed rows, **23 of them already
   `feedback/`**. The number the operator reads as a health signal is 9% wants.
4. **Triage pools them with the defects and gives them no heading of their
   own.** `factory/doctor/triage.py:470` — `classify` builds its pool from every
   open and regressed row, so a want is counted in `total` and in `classified`
   beside the defects and then falls down the same ladder — the prose class, the
   cold rule at `factory/doctor/triage.py:549-551`, and finally the residue —
   and is then listed under the same class headings the defects are, in both
   faces (`factory/doctor/triage.py:710` — `render` and
   `factory/doctor/triage.py:675` — `to_document`), with nothing in either
   document saying it is not one. The folding class is *not*
   the harm here and cannot be: `factory/doctor/triage.py:444` —
   `_fragmented_groups` skips every key with fewer than three segments
   (`factory/doctor/triage.py:108`; the module's own class list says the same at
   `factory/doctor/triage.py:33`), and measured on the live ledger on 2026-09-04
   all 279 open and regressed rows — the 23 `feedback/` rows included — have
   exactly two.
5. **And the way out saves no work.** `factory/cli/doctor.py:514` —
   `findings_promote_command` scaffolds a spec directory, but the text it writes
   comes from the skeletal findings variant of `factory/doctor/scaffold.py:27` —
   `scaffold_spec` (`factory/doctor/scaffold.py:50-58`). The evidence, the
   anchors, the traps and the acceptance scenarios — everything that makes a spec
   worth dispatching — are still assembled by hand from a store the drafter has
   to know how to query, including the event trail at
   `factory/doctor/store.py:493` — `list_events`, which no CLI verb reads today.

## The rule this spec is asking for

**Something not yet a defect has a durable home that says it is not a defect, and
getting it out again hands the drafter the evidence instead of the task of
finding it.**

What `findings list` shows, for every combination of row and flag:

| row | no flags | `--category feedback` | `--category <other>` | `--all` |
|---|---|---|---|---|
| defect, e.g. `verify/…` | listed | withheld | listed iff the category matches | listed |
| reserved, `feedback/…` | **withheld, and the count named on stderr** | listed | withheld | listed |

`--severity` and `--status` compose with every column of that table rather than
replacing it, and `--json` keeps emitting the bare array its in-tree consumers
already parse (`.claude/skills/findings-ingest/SKILL.md:77`,
`.claude/skills/findings-ingest/SKILL.md:136` and
`.claude/skills/findings-ingest/SKILL.md:187`); the
withheld notice goes to stderr on that path for the same reason FR-002's
deprecation does.

### What this spec is not

It is not a second dispatcher. `ergane findings draft` assembles a brief and
stops; the agent that consumes it is invoked by the operator, in a separate
process, by whatever means the operator already uses. The node adapter
`factory/workgraph/adapter.py:993` — `ClaudeCodeAdapter` is shaped around an
`AttemptContext` — a worktree, a heartbeat, a pid file, a per-node HOME, a
transcript archive — and reaching for it here would build a second lifecycle to
run one prompt.

It is not a schedule. Putting the drafter on a tick beside `ergane-roadmap` is
the obvious next move and is deliberately deferred: an unattended drafter writes
specs nobody asked for, and this repository's own measured position is that the
leverage is in refinement, which is where the operator's judgment lives. Ship
the verb, watch the drafts, schedule it when they stop needing a reader.

It is not a schema migration. `severity` is pinned by a `CHECK` constraint
(`factory/doctor/store.py:53-54`) and `status` by another
(`factory/doctor/store.py:55-56`), and `SCHEMA_VERSION` is 1 with no migration
path (`factory/doctor/store.py:20`). Feedback is filed at `info`, which is an
accepted compromise rather than a good fit, and it is named as one so that no
implementer invents a fourth severity to make it fit better.

It is not a rewrite of triage's folding class. `_fragmented_groups` is left
alone, and the reason is arithmetic rather than taste: it reads only keys of
three or more segments, and no open or regressed row in this ledger has more
than two. A clause excluding the lane from it would be a change no row could
exercise, and a scenario written over it would pass against an empty production
diff.

It is not a correction of `.specify/templates/`. Those templates are stale
against the current spec shape and this spec routes around them rather than
rewriting them; saying so is what keeps FR-011 honest.

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

1. **Given** a scratch store and a frozen clock, **When** the same finding is
   filed once through `ergane findings record` and once through
   `ergane findings report`, **Then** every column of the resulting row matches
   and the recurrence machine advanced identically — asserted against the store
   rather than the parser, because the claim the alias makes is that behaviour
   did not change and only the row can prove that. The clock is frozen because
   `factory/cli/doctor.py:61` — `_utcnow` has second resolution and stamps
   `first_seen`, `last_seen` and the event row, so two invocations either side of
   a second boundary differ in three columns for no reason the rename caused.
2. **Given** `ergane findings report`, **When** it runs, **Then** it exits with
   the status `record` exits with, its stdout is byte-identical to `record`'s,
   and one deprecation line naming `record` is written to **stderr** — proven by
   a committed test that reads the two streams separately. On stdout it would
   corrupt anything parsing the command, and this noun's stdout is parsed.
3. **Given** `ergane findings --help`, `ergane completion bash` and
   `ergane completion zsh`, **When** each is read, **Then** none of them offers
   `report` — not in the usage line, not in the verb listing, and not in the
   noun's own description string at `factory/cli/doctor.py:262`, which today
   reads `Report, list, resolve, or promote findings.` — and the brace set the
   usage metavar renders equals the set of registered verbs minus the deprecated
   one, asserted against the emitted text rather than against the parser's alias
   table. A deprecated alias advertised by shell completion is not deprecated; it
   is a second supported name with a note attached, a help text that still opens
   with the old word is the rename half-done, and a hand-written metavar
   is a second copy of the verb list that the next verb added will contradict.
4. **Given** the nine lines in six tracked files that name the old verb —
   `CLAUDE.md:106`, `docs/architecture.md:558`, `docs/cli/findings.md:11`,
   `docs/cli/findings.md:12`, `docs/cli/findings.md:56`, `.claude/skills/away-mode/SKILL.md:158`,
   `.claude/skills/findings-ingest/SKILL.md:186`,
   `.claude/skills/findings-ingest/SKILL.md:249`,
   `.claude/skills/findings-ingest/SKILL.md:250` — and the verb
   tuple at `tests/test_ergane_env_completion.py:120`, **When** this story lands,
   **Then** each names `record` and a committed guard asserts the string
   `findings report` appears in no tracked operator-facing markdown outside
   `specs/`. The guard cannot be satisfied by a documentation-only diff, because
   `tests/page_holds_true.py:301` — `extract_commands` already holds `CLAUDE.md`
   to the rule that every command it names must parse, so a page naming a verb
   that does not exist turns the suite red.

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

1. **Given** a scratch store holding both defect rows and `feedback/` rows,
   **When** `ergane findings list` runs with no filters, **Then** the feedback
   rows are absent from stdout and a line naming how many were withheld and the
   flag that shows them is written, with the count read from the store rather
   than written as a literal — proven by a committed test whose fixture row count
   differs from any number in the source. A view that silently drops rows is
   worse than one that never had the lane, because it makes the operator
   confident about a number that is now partial.
2. **Given** the same store, **When** `--category feedback` is passed, **Then**
   only feedback rows are listed; **and when** `--all` is passed, **Then**
   everything is listed and `--json` still emits a bare array; **and** the three
   `findings list --json` call sites that read every row on purpose —
   `.claude/skills/findings-ingest/SKILL.md:77`,
   `.claude/skills/findings-ingest/SKILL.md:136` and
   `.claude/skills/findings-ingest/SKILL.md:187` — pass `--all` in the
   same commit, proven by a committed test that reads those three lines out of
   the skill file and asserts each carries the flag; **and** the reference page
   comes with them — the synopsis at `docs/cli/findings.md:10` and the
   `## ergane findings list` section at `docs/cli/findings.md:22` name
   `--category` and `--all` and state the reserved lane and the withheld notice,
   held by a committed guard asserting that every flag that synopsis line names
   is present in `ergane findings list --help`, which a prose-only diff cannot
   satisfy because it stays red until the flags exist. The first call site is the
   corpus dump the skill calls mandatory before minting any key
   (`.claude/skills/findings-ingest/SKILL.md:73`) and it already selects `open`
   and `regressed`, which is every feedback row in the ledger; hiding the lane
   from it makes an ingest agent mint a second key for a want that already has
   one. The second lists the distinct category prefixes, so a hidden lane makes
   `feedback` look like a category nobody has used. The third is the rehearsal
   row count over a scratch store the skill fills with feedback rows on purpose.
3. **Given** a probe whose evaluation returns a `factory/doctor/probes.py:43` —
   `FindingReport` in the reserved category, **When** it is driven through the
   one *wired* path every probe finding takes into the store —
   `factory/cli/doctor.py:194-204`, ending at `factory/cli/doctor.py:240` —
   `_report_if_new` — **Then** the report is skipped with a message naming the
   probe and the lane, no row is written, and the probes after it in the registry
   still file their own findings; **and** a committed test replaces `REGISTRY`
   (`factory/doctor/probes.py:628`) with exactly such a probe followed by an
   ordinary one, to prove both halves. Replacing rather than appending is what
   keeps the test hermetic: the five real entries reach Temporal and the runtime
   root. An assertion that today's five probes are clean is satisfied by a diff
   that changes nothing.
4. **Given** `ergane findings triage` over a store holding one `feedback/` row
   and three defect rows, **When** it classifies, **Then** the feedback row is
   listed under its own heading in **both** faces —
   `factory/doctor/triage.py:710` — `render` and
   `factory/doctor/triage.py:675` — `to_document` — is listed under no other
   class's heading in either, and `total` still equals `classified`
   (`factory/doctor/triage.py:204` — `Triage`), proven by a committed test that
   reads both documents. The heading is the whole of what this scenario buys: a
   want classified beside three defects and printed in the same list is a defect
   as far as the reader is concerned, and the reader is the operator counting the
   ledger's health. The heading is also the only half that new code can deliver
   here — the pool arithmetic already balances, which is why the scenario asserts
   it as a thing not broken rather than a thing built.

### User Story 3 - Getting it out again hands over the evidence (Priority: P2)

As a drafting agent, I receive one brief that already contains the finding's
whole history and the contract my output must satisfy, so I spend my context
writing the spec rather than discovering how to write one here.

**Why this priority**: P2. US1 and US2 make the queue real and legible; this is
what makes it worth having. It is last because it is the largest, and because a
brief written against a lane that does not exist yet would have to be revised
when it does.

**Independent Test**: file a feedback row with notes and refs, record it twice
more to build a trail, then run `ergane findings draft --key <key>` and read the
file it names.

**Acceptance Scenarios**:

1. **Given** one or more finding keys, **When** `ergane findings draft` runs,
   **Then** it writes one brief to a file and prints that path, every `findings`
   and `finding_events` row is unchanged, and a second invocation produces a
   byte-identical brief — proven by a committed test that snapshots both tables
   around the call. A queue-reading verb that mutates the queue cannot be run
   twice to see what it says.
2. **Given** a finding recorded three times across two distinct `seen_at` values,
   **When** the brief is written, **Then** it carries every stored column and
   every event returned by `factory/doctor/store.py:493` — `list_events`,
   asserted on `occurrences == 3` and on both dates. Occurrence count and
   first-seen date are the difference between "somebody thought this once" and
   "this has come up three times since Tuesday", and that difference is most of
   what a drafter needs to judge priority.
3. **Given** the brief's statement of what the drafter must produce, **When** the
   section skeleton it teaches is compared with the one
   `factory/doctor/scaffold.py:153` — `_build_spec_md_from_slots` emits, **Then**
   they agree section for section — `## Functional Requirements` at level 2 and a
   `## Work Graph` fence carrying `implements:` on every node
   (`factory/doctor/scaffold.py:203-226`) — and the brief names
   `ergane spec validate` as the acceptance test its output must pass; **and**
   the same test asserts that `factory/doctor/scaffold.py:321` —
   `_build_spec_md`, the sibling branch whose output `promote` actually compiles,
   emits that same skeleton. Proven by a committed test that changes the
   generator in a fixture and asserts the brief changes with it; a test that only
   looks for the words passes against a hardcoded copy, which is the drift this
   scenario exists to prevent, and a brief derived from one branch while the
   `derive_workgraph` proof runs over the other is that drift with a proof
   attached to the wrong half.
4. **Given** the command, **When** it runs with `LITELLM_PROXY_URL`,
   `LITELLM_MASTER_KEY`, `TEMPORAL_ADDRESS` and `TEMPORAL_NAMESPACE` unset and
   the socket constructor patched to raise, **Then** it exits 0, no path under
   `specs/` was created or modified, and no subprocess was spawned — proven by a
   committed test that asserts on the stripped environment rather than on the
   absence of an import. The whole reason this story is affordable is that it
   assembles text; a version that grew a dispatcher would have acquired the node
   lifecycle it was written to avoid.

## Functional Requirements

- **FR-001**: `ergane findings record` MUST be the write verb, with today's
  arguments and behaviour exactly — the same required set (`--key`,
  `--category`, `--severity`, `--summary` unless `--batch`), the same credential
  refusals (`factory/cli/doctor.py:458-465` and
  `factory/cli/doctor.py:482-485`), the same `--source` default of `operator`,
  and the same runner wrapper `factory/cli/doctor.py:353` — `_with_store`. Every
  argument's `help=` string is part of "exactly", including `--source`'s
  `reporter source` at `factory/cli/doctor.py:287`, which contains the substring
  `report` and is the one occurrence FR-003's sweep may not chase.
- **FR-002**: `ergane findings report` MUST continue to work unchanged, exit with
  the status `record` exits with, produce byte-identical stdout, and write one
  deprecation line naming `record` to **stderr**. Not stdout:
  `findings list --json` and `findings triage --json` establish that this noun's
  stdout is parsed.
- **FR-003**: `report` MUST appear in neither `ergane findings --help` nor the
  output of `ergane completion bash` and `ergane completion zsh`. Two mechanisms
  are required and neither is optional. First, the findings `add_subparsers` call
  at `factory/cli/doctor.py:264` MUST carry an explicit `metavar`, because
  argparse otherwise renders every registered name — alias or not — into the
  usage line, and the deprecated parser MUST be registered without a `help=` so
  it takes no line in the verb listing either. That `metavar` MUST be **derived**,
  after every verb is registered, from the subparsers' own `_name_parser_map`
  minus the single declaration of which name is deprecated — the same declaration
  `factory/cli/completion.py:32` — `_noun_and_verb_map` reads — and MUST NOT be a
  hand-written list of verb names. A hand-written brace list is a second
  declaration of the verb set with nothing holding it to the parser, and it is
  read *as* the verb set: `tests/page_holds_true.py:346` — `verbs_of` matches the
  braces out of the positional section before it falls back to the indented
  listing, so a literal would make the `CLAUDE.md`, README and on-ramp page
  guards blind to every verb registered afterwards — starting with US3's own
  `draft`, which those guards would then reject as a verb that does not exist. A
  committed test MUST assert that the brace set the metavar renders equals the
  set of registered verbs minus the deprecated one. Second, the completion
  generator `factory/cli/completion.py:32` — `_noun_and_verb_map` MUST omit the
  deprecated name where it reads `_name_parser_map`
  (`factory/cli/completion.py:53`), from that same single declaration rather than
  from a second list. The noun's own description string at
  `factory/cli/doctor.py:262` — today `Report, list, resolve, or promote
  findings.` — MUST be rewritten to name `record`, because
  `ergane findings --help` prints it above the verb listing.
- **FR-004**: Every tracked operator-facing line naming the old verb MUST name
  `record` — nine lines in six files: `CLAUDE.md:106`,
  `docs/architecture.md:558`, `docs/cli/findings.md:11`,
  `docs/cli/findings.md:12`, `docs/cli/findings.md:56`,
  `.claude/skills/away-mode/SKILL.md:158`,
  `.claude/skills/findings-ingest/SKILL.md:186`,
   `.claude/skills/findings-ingest/SKILL.md:249`,
   `.claude/skills/findings-ingest/SKILL.md:250` — and the verb
  tuple at `tests/test_ergane_env_completion.py:120` MUST be updated in the same
  commit. A committed guard MUST assert the string `findings report` appears in
  no tracked markdown outside `specs/`, and MUST be proven to fail against a
  fixture carrying it.
- **FR-005**: `ergane findings list` MUST gain `--category <name>`, filtering on
  the `category` column and composing with `--severity` and `--status`. The
  filter MUST be applied in `factory/cli/doctor.py:368` —
  `findings_list_command`, where the existing two already live, because
  `factory/doctor/store.py:454` — `list_findings` takes no filter arguments and
  this story is not the place to change its signature.
- **FR-006**: `feedback` MUST be a reserved category. With neither `--category`
  nor `--all`, `findings list` MUST omit those rows and MUST name how many it
  omitted and the flag that shows them, with the count derived from the store.
  `--all` MUST list everything. Under `--json` the document MUST stay a bare
  array and the notice MUST go to stderr, and the three in-tree call sites that
  read every row on purpose —
  `.claude/skills/findings-ingest/SKILL.md:77`,
  `.claude/skills/findings-ingest/SKILL.md:136` and
  `.claude/skills/findings-ingest/SKILL.md:187` — MUST pass `--all` in the same
  commit, asserted by a committed test that reads those lines out of the skill
  file. The reference page MUST move with the interface: the `findings list`
  synopsis at `docs/cli/findings.md:10` and the `## ergane findings list` section
  at `docs/cli/findings.md:22` MUST name `--category` and `--all` and state the
  reserved lane and the withheld notice, and a committed guard MUST assert that
  every flag that synopsis line names is present in `ergane findings list
  --help`. That guard is what keeps the page from being prose nobody checks —
  FR-009 imposes the same discipline on `draft`, and US1 rewrites three other
  lines of this same file. The enumeration MUST be re-verified with
  `git grep -n 'findings list' -- '.claude' 'docs' '*.md'` before the story is
  dispatched, the way FR-004's sweep was: it was two lines at drafting and is
  three today.
- **FR-007**: A `factory/doctor/probes.py:43` — `FindingReport` in the reserved
  category MUST be refused where probe findings enter the store — the loop at
  `factory/cli/doctor.py:194-204` and `factory/cli/doctor.py:240` —
  `_report_if_new` — with a message naming the probe and the lane, and no row
  written. The refusal MUST **skip that one report and continue the loop**, not
  raise: `factory/cli/doctor.py:230-236` already swallows a probe's unexpected
  error and carries on, and an `OperatorError` here would mean one
  mis-categorised probe costs every later probe its findings for that run. The
  refusal MUST be proven non-vacuous by a test that **replaces** `REGISTRY`
  (`factory/doctor/probes.py:628`) with a reserved-category probe followed by an
  ordinary one and asserts the second still files; an assertion over today's five
  probes alone is satisfied by a diff that changes nothing, and appending to the
  live registry runs all five against Temporal and the runtime root. The refusal
  goes in `factory/cli/doctor.py` alone: `factory/doctor/cli.py:257` —
  `_report_if_new` is an identically-named legacy twin that no parser reaches,
  and patching it changes nothing at runtime while looking correct in a diff.
- **FR-008**: `findings triage` MUST report feedback rows under their own heading
  in both `factory/doctor/triage.py:710` — `render` and
  `factory/doctor/triage.py:675` — `to_document`, and MUST list no feedback row
  under any other class's heading in either face. They MUST remain in the
  classification pool `factory/doctor/triage.py:470` — `classify` builds, so
  `total` and `classified` (`factory/doctor/triage.py:204` — `Triage`) still
  balance; the cold rule and the closed-by-a-landed-spec rule still reach them.
  The folding class at `factory/doctor/triage.py:444` — `_fragmented_groups` is
  explicitly **out of scope** and MUST NOT be changed by this story. That is a
  measurement, not a preference: it skips every key with fewer than three
  segments (`factory/doctor/triage.py:108`), and on the live ledger on 2026-09-04
  all 279 open and regressed rows — the 23 `feedback/` rows included — have
  exactly two, so an exclusion there is a change no row in this store can
  exercise and a scenario written over it would pass against an empty production
  diff.
- **FR-009**: `ergane findings draft --key <key> [--key <key> ...]` MUST write one
  brief to a file and print the path. It MUST change no row, no status and no
  event trail, and two invocations MUST produce byte-identical briefs. It MUST be
  wired outside `factory/cli/doctor.py:353` — `_with_store`;
  `docs/cli/findings.md` MUST gain its synopsis line and section; and the
  read-only verb list at `docs/cli/README.md:103` MUST name it, because `draft`
  writes no row and that list is where a reader learns which verbs do not.
- **FR-010**: The brief MUST carry, for every named finding, every stored column
  — key, category, severity, status, summary, notes, refs, source, occurrences,
  first_seen, last_seen — and the complete event trail from
  `factory/doctor/store.py:493` — `list_events`. Occurrence count and first-seen
  date are what separate "somebody thought this once" from "this has come up
  three times since Tuesday", and a drafter that has to query for them will not.
- **FR-011**: The brief MUST state the contract its output satisfies — the
  spec/plan/tasks trio, `## Functional Requirements` at level 2, a `## Work
  Graph` fence with `implements:` on every node, `state: draft` frontmatter, and
  `ergane spec validate` as the acceptance test — and MUST derive that skeleton
  from `factory/doctor/scaffold.py:27` — `scaffold_spec` rather than restating it
  in the command's source or reading `.specify/templates/`. `scaffold_spec` is
  the only in-tree description of the shape with a live proof, but the proof is
  on the sibling branch: `promote` calls it with `findings=` and compiles
  `factory/doctor/scaffold.py:321` — `_build_spec_md` through `derive_workgraph`
  at `factory/cli/doctor.py:566-577`, while the brief reads the slot branch
  `factory/doctor/scaffold.py:153` — `_build_spec_md_from_slots`. Both emit the
  same skeleton today and nothing holds them to it, so the same test that pins
  the brief to the slot branch MUST also assert the two branches agree on the
  section skeleton.
- **FR-012**: The command MUST invoke no agent, write nothing under `specs/`, and
  open no network connection, proven by a test run with the gateway and Temporal
  environment variables unset and the socket constructor patched to raise. Its
  output path MUST resolve through the same runtime root every other findings
  verb uses (`factory/cli/doctor.py:65` — `_store_path`) and MUST be overridable.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-005, FR-006, FR-007, FR-008]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-009, FR-010, FR-011, FR-012]
```

Two `depends_on_merged` edges, declared rather than left to the merge queue. All
three stories add or change verbs inside `factory/cli/doctor.py:251` —
`add_findings_parser`, so they are serialised on file ownership rather than on
logic; `depends_on_merged` models what a story needs to *exist*, and two
correctly-independent stories extending one function are exactly the shape that
lands clean and then fails the next node's gate after a clean rebase. US2 also
needs US1's prose sweep to have landed before it edits two more lines of
`.claude/skills/findings-ingest/SKILL.md` and three of `docs/cli/findings.md`,
and US3 adds a section to that same page and depends on US1's derived metavar to
carry `draft` without a second edit. See `plan.md` § *Sizing* for the per-story
file lists.
