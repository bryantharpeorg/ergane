# Implementation Plan: the ledger takes what is not yet a defect

Drafted 2026-08-28 against ergane-buildout at 8bb2d4b. Every anchor below was
read from that commit. The transcript in § *The alias trap, measured* was
produced on it and is an input to this plan, not a hypothesis for the implementer
to re-derive.

## Requirements, numbered here

### US1 — the write verb says it writes

- **FR-001** — `ergane findings record` is the write verb. Its arguments and its
  behaviour are exactly today's `report`: the same required set (`--key`,
  `--category`, `--severity`, `--summary` unless `--batch`), the same
  credential refusal (`factory/cli/doctor.py:458-465`, `:482-485`), the same
  `--source` default of `operator`, and the same runner wrapper
  (`_with_store`, `factory/cli/doctor.py:353`).
- **FR-002** — `ergane findings report` continues to work unchanged, exits with
  the same status, and writes one deprecation line **to stderr** naming
  `record`. Not stdout: `findings list --json` and `findings triage --json`
  establish that this noun's stdout is parsed, and a deprecation notice on it
  would be the kind of change that breaks a pipeline six weeks later for a
  reason nobody connects to this spec.
- **FR-003** — `report` appears in neither `ergane findings --help` nor the
  output of `ergane completion bash` and `ergane completion zsh`. The completion
  generator (`_noun_and_verb_map`, `factory/cli/completion.py:32-64`) must emit
  one name per distinct subparser object rather than every key of
  `_name_parser_map` (`:53`). See § *The alias trap, measured* — this is not a
  precaution, it is a defect the obvious implementation has.
- **FR-004** — The three prose call sites naming the old verb are updated:
  `CLAUDE.md:106`, `docs/architecture.md:518`,
  `.claude/skills/away-mode/SKILL.md:158`. A guard asserts the string
  `findings report` appears in no operator-facing markdown.
  `tests/test_ergane_env_completion.py:120` enumerates `("list", "report",
  "resolve", "promote")` and must be updated in the same commit, or the suite
  fails for the right reason at the wrong time.

### US2 — a want is not a defect, and the ledger can tell

- **FR-005** — `ergane findings list` gains `--category <name>`, filtering on the
  `category` column. It composes with `--severity` and `--status`; the filters
  are applied in `findings_list_command` (`factory/cli/doctor.py:368-392`), where
  the existing two already live, because `list_findings`
  (`factory/doctor/store.py:454`) takes no filter arguments and this story is not
  the place to change its signature.
- **FR-006** — `feedback` is a reserved category. With no `--category` and no
  `--all`, `findings list` omits those rows **and prints how many it omitted and
  the flag that shows them**. `--all` lists everything. The stated count is not
  a nicety: a view that drops rows silently converts a number the operator trusts
  into a number that is quietly partial, which is the same failure the spec's
  GitHub Issues objection describes, pointed inward.
- **FR-007** — No registered probe may file into the reserved category. A guard
  over `REGISTRY` (`factory/doctor/probes.py:628`) asserts it, so a probe added
  later that reaches for the word turns the suite red rather than polluting the
  lane. Probes construct findings in Python and never touch the CLI, so this is
  the only place the rule can be enforced.
- **FR-008** — `findings triage` reports feedback rows under their own heading
  and never includes one in a fragmented class (`_fragmented_groups`,
  `factory/doctor/triage.py:444`). The cold rule and the closed-by-a-landed-spec
  rule still apply to them; only the folding is excluded, because folding groups
  by textual similarity and a want that shares a word with three bugs produces a
  recommendation the operator cannot act on.

### US3 — getting it out again hands over the evidence

- **FR-009** — `ergane findings draft --key <key> [--key <key> ...]` writes one
  brief to a file and prints the path. It changes no row, no status and no
  event trail, and running it twice produces the same brief. It is the only
  findings verb that reads and does not write; see T2 for the wrapper that makes
  that non-obvious.
- **FR-010** — The brief carries, for every named finding, every stored column —
  key, category, severity, status, summary, notes, refs, source, occurrences,
  first_seen, last_seen — **and** the complete event trail from `list_events`
  (`factory/doctor/store.py:493`). Occurrence count and first-seen date are what
  separate "somebody thought this once" from "this has come up three times since
  Tuesday", and a drafter that has to query for them will not.
- **FR-011** — The brief states the contract its output must satisfy: the
  spec/plan/tasks trio, the Work Graph block with `implements:` and
  `depends_on_merged:`, and `ergane spec validate` as the acceptance test. The
  trio's shape is read from `.specify/templates/spec-template.md`,
  `plan-template.md` and `tasks-template.md` at runtime, not restated in the
  command's source. A second copy of the spec format is a copy that drifts from
  the validator while both stay green.
- **FR-012** — The command invokes no agent, writes nothing under `specs/`, and
  opens no network connection. Proven by a test run with no credentials and no
  network, not by inspection.

## What already exists, and where

| Piece | Where | State |
| --- | --- | --- |
| The parser this spec edits three times | `add_findings_parser`, `factory/cli/doctor.py:251-350` | Five verbs: list, report, resolve, promote, triage |
| The write verb, misnamed | `factory/cli/doctor.py:276-293` | Its own help string already reads `record a finding` |
| The recurrence machine | `report`, `factory/doctor/store.py:137-206` | Untouched by this spec |
| The category column | `factory/doctor/store.py:52` | Documented in the schema as an *open taxonomy* — nothing validates it |
| The severity constraint | `factory/doctor/store.py:53-54` | `CHECK … IN ('critical','warning','info')` — why feedback is filed at `info` |
| The list filters | `findings_list_command`, `factory/cli/doctor.py:368-392` | `--severity` and `--status`, applied in Python after `list_findings` |
| The unfiltered read | `list_findings`, `factory/doctor/store.py:454` | Takes no arguments; returns everything |
| The event trail reader | `list_events`, `factory/doctor/store.py:493` | Already exists; FR-010 is its first CLI consumer |
| The scaffold `promote` uses | `scaffold_spec`, `factory/doctor/scaffold.py:27-66` | Has a findings variant; produces skeletal text, which is why US3 is not "just use promote" |
| The completion generator | `_noun_and_verb_map`, `factory/cli/completion.py:32-64` | Reads `_name_parser_map.keys()` at `:53` — the alias leak |
| The completion assertion | `tests/test_ergane_env_completion.py:120` | Enumerates the four verb names as literals |
| The probe registry | `REGISTRY`, `factory/doctor/probes.py:628` | A list; FR-007's guard iterates it |
| The fragmented-class folding | `_fragmented_groups`, `factory/doctor/triage.py:444` | What FR-008 excludes feedback from |
| The node adapter US3 must not reach for | `ClaudeCodeAdapter`, `factory/workgraph/adapter.py:922` | Shaped around `AttemptContext`: worktree, heartbeat, pid file, per-node HOME, transcript archive |

## The alias trap, measured

FR-003 exists because the obvious implementation of FR-002 leaks. Run on
2026-08-28 against a bare `argparse` tree matching this noun's shape:

```
name_parser_map keys: ['list', 'record', 'report']
grouped by parser object: [['record', 'report'], ['list']]
choices: ['list', 'record', 'report']
```

`add_parser("record", aliases=["report"])` registers **both** names in
`_name_parser_map`, and `_noun_and_verb_map` at `factory/cli/completion.py:53`
emits every key. So the deprecated alias would be advertised by shell completion
to every operator on the box — the precise opposite of deprecating it.

The fix is in the same transcript: grouping by `id(parser)` recovers the
canonical name, because `add_parser` registers it before any alias. Today's
output for comparison, which the implementer should diff against:

```
        findings) local verbs='list promote report resolve triage' ;;
```

Two things follow. The completion generator is in scope for US1 and is not
optional. And whichever mechanism is chosen for the alias — argparse `aliases=`,
or a second `add_parser` sharing a `parents=` parent and `set_defaults` — the
completion assertion has to be written against the *output*, not against the
mechanism, because both mechanisms leak the same way.

## Why `draft` is not `promote` with better text

`promote` (`factory/cli/doctor.py:514-580`) already refuses unknown and
already-promoted keys, refuses to overwrite an existing spec directory, writes
the trio into a temp dir and compiles the workgraph the way `spec derive` will.
All of that is correct and none of it is duplicated here.

What it cannot do is write the *content*. `scaffold_spec`'s findings variant
(`factory/doctor/scaffold.py:49-57`) turns findings into skeletal text; the
evidence, the anchors, the traps and the acceptance scenarios — everything that
makes a spec worth dispatching — are still assembled by hand.

So `draft` sits before `promote`, not instead of it: it produces the brief a
drafter needs, the drafter produces the trio, and `promote` remains the verb that
records the status transition when a spec directory actually exists. That
ordering is also why FR-009 says `draft` changes no status. There is no
`drafting` value in the `status` CHECK (`factory/doctor/store.py:55-56`), adding
one is a migration this spec has ruled out, and a row that stayed `open` until a
spec exists is honest anyway.

## Technical approach, story by story

### US1 — the rename

`factory/cli/doctor.py`: `record` becomes the registered verb; `report` is
registered so that it runs the same command function, prints its deprecation to
stderr, and does not surface in help. `factory/cli/completion.py`:
`_noun_and_verb_map` groups by parser identity before sorting. Then the three
prose call sites, the completion test's literal list, and a guard over
operator-facing markdown.

### US2 — the lane

`findings_list_command` gains `--category` and `--all` alongside the two filters
already applied there, plus the withheld-count line. `factory/doctor/triage.py`
grows the separate heading and excludes the reserved category from
`_fragmented_groups`. The probe guard is a new test over `REGISTRY`.

The reserved name lives in exactly one constant, imported by the CLI, the triage
module and both guards. Three string literals spelling `"feedback"` is how the
lane comes to mean one thing in the list and another in triage.

### US3 — the brief

A new verb reading the named findings and their events, rendering one text file.
The trio contract is read from `.specify/templates/` at runtime. No store write,
no `specs/` write, no network. The output path defaults under the resolved
runtime root and is overridable.

## Traps

**T1 — the reserved category must be one constant.** FR-006, FR-007 and FR-008
all turn on the word `feedback`. Spelled as a literal in each place, the list
hides one set, triage excludes another, and the probe guard checks a third. They
will agree on the day they are written and diverge on the day one is edited.

**T2 — `draft` must not be wrapped in `_with_store`.** That wrapper
(`factory/cli/doctor.py:353-365`) runs `_resolve_promoted_findings` — a write —
before every verb it wraps. FR-009 says `draft` changes nothing, and a wrapped
`draft` would violate it invisibly, because the write is correct behaviour for a
different verb. `triage` already faced this exact decision and the code carries
a long comment at `factory/cli/doctor.py:340-347` explaining why it opted out.
Read that comment before wiring the new verb.

**T3 — do not add a severity or a status.** The tempting change is a `feedback`
severity or a `drafting` status, and both are `CHECK`-constrained
(`factory/doctor/store.py:53-56`), so both are migrations. `schema_version`
exists and migrations are possible; that is not the point. The point is that this
spec buys a lane for the price of a prefix, and a story that spends a migration
on cosmetics has spent it before the lane has proved it is used.

**T4 — the completion output is the assertion, not the mechanism.** See § *The
alias trap, measured*. A test asserting "the parser has an alias" passes while
completion advertises the deprecated name. Assert on the emitted script.

**T5 — hiding rows without saying so is the defect, not the feature.** FR-006's
withheld count is the whole difference between a lane and a lie. A `findings
list` that quietly omits nine rows leaves the operator confident about a number
that is now partial — and the operator reads that number as a health signal, most
recently on 2026-08-28 when it stood at 138 open with 59 critical.

**T6 — `draft` must not grow a dispatcher.** FR-012 is a hard boundary. Reaching
for `ClaudeCodeAdapter` (`factory/workgraph/adapter.py:922`) means constructing
an `AttemptContext` — a worktree, a heartbeat, a pid file, a per-node HOME, a
transcript archive — to run one prompt. That is a second node lifecycle, it is
not what this story was sized for, and the operator's stated position is that the
drafter stays in the loop until the drafts prove otherwise.

**T7 — the brief must read its contract, not restate it.** FR-011 says
`.specify/templates/` at runtime. A brief carrying its own copy of the trio
format is a copy that drifts from what `ergane spec validate` demands, and both
stay green while the drafts get quietly worse. This repository has shipped the
two-lists-that-drift shape before; `plan.md` for spec 114 records three instances
in one file.

**T8 — `report` has one caller that is not prose.**
`tests/test_ergane_env_completion.py:120` asserts on the literal verb list. It
must move in the same commit as the rename. It is listed here because it is the
one call site a grep for "findings report" does not surface — it spells the verb
as a bare `"report"` inside a tuple.

## Work Graph

```yaml
US1:
  implements: [FR-001, FR-002, FR-003, FR-004]
  depends_on: []
US2:
  implements: [FR-005, FR-006, FR-007, FR-008]
  depends_on: []
  depends_on_merged: [US1]
US3:
  implements: [FR-009, FR-010, FR-011, FR-012]
  depends_on: []
  depends_on_merged: [US2]
```

## Sizing

Three stories, ascending. US1 is a rename plus a six-line fix to the completion
generator plus four documentation edits. US2 is two flags, one constant, one
heading and two guards. US3 is one new verb that renders text.

**The chain is the cost, not the stories.** Depth three at roughly an hour to an
hour and three quarters per story means this epic is a half-day of wall clock
even though no single story is hard. If that matters more than the file
contention does, US1 and US3 could in principle be split apart — but see below
for why the recommendation is to leave them serialised.

## File contention

| story | owns |
| --- | --- |
| US1 | `factory/cli/doctor.py`, `factory/cli/completion.py`, `tests/test_ergane_env_completion.py`, `CLAUDE.md`, `docs/architecture.md`, `.claude/skills/away-mode/SKILL.md` |
| US2 | `factory/cli/doctor.py`, `factory/doctor/triage.py` |
| US3 | `factory/cli/doctor.py` |

All three edit `add_findings_parser` in `factory/cli/doctor.py:251-350`. This is
stated as `depends_on_merged` rather than left to the merge queue on purpose:
`depends_on_merged` models what a story needs to *exist*, not what it will
*touch*, so two correctly-independent stories extending one file are exactly the
shape that lands clean and then fails the next node's gate after a clean rebase.
This repository has the receipt — `factory/cli/init.py` took eight commits in one
day and cost two hand-merges and a rework cycle.

Serialising three small stories costs about two hours of wall clock. One
hand-merge costs more than that and arrives as a mystery.

## Dispatch hazards, for the operator running this epic

- **Re-derive the workgraph at dispatch** with `--target-repo "$PWD"` from the
  operator checkout; a committed artifact carries compile-time absolute paths.
- **`8bb2d4b` is unpushed as of drafting.** The constitution and the specs
  corpus reach implementers through the landing branch, so push before
  dispatching or the epic compiles against `b5bffad`.
- **US1 edits `CLAUDE.md`,** which `tests/test_claude_md.py` holds to the rule
  that every command it names must resolve. Renaming the verb without renaming
  the row in that table fails the gate — which is the guard working, and worth
  knowing before it reads as a mystery.
- **Do not run `scripts/gate-commit` while an attempt is in flight.**
- **This spec's own key convention is `feedback/<slug>`.** If you start filing
  against the lane before US2 lands, the rows are still correct — they simply
  appear in the default list until the filter exists.

## Verification the operator will run, independent of the gate

The gate can prove the verb renamed, the lane filters, and the brief renders.
It cannot prove the brief is *useful*, because usefulness is a property of what a
drafter does with it.

After US3 lands, once, deliberately: take a want that has been sitting in
cross-session memory rather than in the tree, file it with
`ergane findings record --category feedback --severity info`, run
`ergane findings draft` over it, and hand the brief to a drafting session. Then
read what comes back against what the spec template alone would have produced.

If the difference is small, the schedule that was deferred out of this spec
should stay deferred, and the honest conclusion is that the queue is worth having
and the drafter is not yet worth automating.
