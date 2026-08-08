---
state: landed
# LANDED 2026-08-08 5:48 AM CT. Three stories, PRs #18–#20, $34.45, all three
# first-attempt PASS, 78 minutes — the cleanest epic the factory has run, and
# the cheapest per story ($11.48 against 016's $33.94).
#
# Proven live after landing: `factory-doctor report --batch
# specs/015-factory-doctor/seed-findings.json` ingested all 27 audit findings
# through the batch envelope FR-004 defines, and `list` renders them in the
# specified order (severity, occurrences descending, key).
#
# BUT `factory-doctor check` — the epic's headline command — raises
# RuntimeError on its first real invocation. The key-list probe's `gather`
# awaits `_closed_epics_from_temporal` inside a running event loop
# (`probes.py:308`) and that helper calls `asyncio.run` itself (`:521`). Exit
# code is 1, so it fails loudly rather than silently.
#
# Worth recording *why* verification missed it, because the cause is
# structural rather than careless: FR-005 requires each probe to split a thin
# snapshot gather from a pure evaluation "so its judgment is testable against
# scripted snapshots". The tests duly script the snapshots — which means the
# evaluation is well covered and `gather()` never executes under test. The
# seam that made the judgment testable is the seam that hid the defect. A
# green suite of 1784 tests and three PASS verdicts sat on top of a command
# that cannot run.
#
# Filed into the doctor's own ledger as `doctor/check-crashes-on-nested-
# asyncio-run` (critical) rather than hand-patched — converting a finding into
# a spec is what this epic is for, and it should be its own first customer.
# Readied 2026-08-08 ~12:15 AM CT after a full verification pass. The trio was
# drafted after 008/009 attested, so `git diff` against factory/ was empty and
# nearly every reuse anchor verified exact. Five corrections: FR-009 narrowed
# from "observed or attested" to attested frontmatter only (observed-landed
# facts live only inside a live RoadmapWorkflow's state, so the cheap
# per-command sweep could not read them); FR-007 now says a skipped probe
# outranks a critical finding when both occur, since the FR is what the judge
# grades; FR-004 defines the batch envelope the seed corpus already uses
# (top-level source/comment/findings) so T005 has a grammar to test against;
# FR-008 requires a failed promotion to leave nothing behind, which the
# refuse-existing rule would otherwise turn into a permanently blocked slug;
# and contracts/doctor-store.sql's header was reworded because the plan copies
# it verbatim into a module constant, where the word it used would have failed
# the D-021 sweep.
# Drafted 2026-08-07 from the operator's request: turn the repo/spec audit
# practice into a durable SRE surface — a `doctor` CLI category that keeps a
# recurrence-tracking findings ledger, probes the factory for known incident
# classes, and converts accepted findings into work-graph-ready spec
# scaffolds the factory then builds itself.
# Numbered 015: slots 010–014 are reserved for the audit-triage epics
# (bugfix, ci-provider-port, agent-sandbox, node-child-workflows,
# host-affinity) whose final numbering is still being triaged.
depends_on_landed: [009-roadmap-scheduler]
---

# Feature Specification: Factory Doctor

**Feature Branch**: `015-factory-doctor`

**Created**: 2026-08-07

**Status**: Drafted the morning after the factory's first unattended night.
That night produced two kinds of knowledge and only one of them has a durable
home. What the factory *built* is in git and Temporal. What the factory
*taught* — the restart gotcha (orphaned virtual keys after a closed epic), the
e5c5569 lesson (an activity fix is not live until the worker restarts), the
leaked key lease, the stale worktree pile — lives in a runbook memory and an
operator's attention. The same morning, a full repo/spec audit produced 27
structured findings on a review page: severity, refs, evidence, a story
mapping. That page is a one-shot artifact; the day it scrolls out of a chat
session, the findings are prose again.

**Input**: The factory has no memory of its own failure modes. Issues repeat
— the orphaned-key cleanup has been performed by hand more than once — and
nothing counts the repetitions, so "this keeps happening" is operator
intuition rather than a queryable fact. Improvement ideas exist only as
conversation until someone hand-authors a spec. The gap: findings need the
same treatment work-in-flight already gets — durable records, machine-checked
structure, and a mechanical path into the roadmap the factory already
schedules from.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Findings are durable records with recurrence (Priority: P1)

As the factory operator, I record improvement findings — from an audit
session, a probe, or my own observation — into a durable ledger keyed by a
stable identity, and when the same finding is reported again the ledger
counts the recurrence instead of duplicating the record, so that "this keeps
happening" becomes a number I can sort by.

A finding is identified by its key (a `category/slug` string); reporting a
key the ledger already holds open bumps its occurrence count and refreshes
its evidence. Reporting a key that was *resolved* reopens it as `regressed`
with its full history preserved — the SRE heart of the feature: a fix that
did not hold is a different, louder fact than a fresh finding, and the ledger
is what makes the two distinguishable.

**Why this priority**: Every other story writes to or reads from this
grammar. It also has standalone value the day it lands: the 27 findings from
the 2026-08-07 audit (shipped in this directory as `seed-findings.json`) get
a durable, queryable home instead of a chat artifact.

**Independent Test**: Against a scratch store, report, re-report,
batch-ingest, resolve, and re-report-after-resolve a corpus of findings;
assert identity, recurrence counts, regression transitions, all-or-nothing
batch refusal, and deterministic listing.

**Acceptance Scenarios**:

1. **Given** an empty store, **When** a finding is reported with key,
   category, severity, summary, and refs, **Then** `factory-doctor list`
   shows it `open` with occurrences 1 and matching first/last-seen.
2. **Given** an open finding, **When** its key is reported again, **Then** no
   second record exists; occurrences increments, last-seen advances, and the
   newest summary and refs are kept alongside the event history.
3. **Given** a resolved finding, **When** its key is reported again, **Then**
   its status becomes `regressed`, prior occurrences and resolution are
   preserved in its history, and the listing flags it distinctly from `open`.
4. **Given** a batch file in the findings JSON grammar, **When**
   `factory-doctor report --batch` ingests it, **Then** ingestion is
   all-or-nothing: one malformed entry refuses the whole batch naming the
   offending entry and rule, and the store is unchanged (the deriver's
   collection discipline, applied to ingestion).
5. **Given** `factory-doctor list`, **When** rendered, **Then** the *ordering*
   is deterministic — severity, then occurrences descending, then key — and
   every finding shows key, severity, status, occurrences, and age. Ordering,
   not bytes: `age` is derived from `last_seen` against the current clock, so
   a byte-identical assertion would be a test of the clock. Pin it in tests by
   freezing the clock or matching the field's shape.

---

### User Story 2 - Probes catch known incident classes before they repeat (Priority: P2)

As the factory operator, I run `factory-doctor check` and a registry of
deterministic probes examines the factory's own substrate — proxy keys,
worker vintage, worktrees, evidence stores — filing findings through the
ledger for anything wrong, so that the incident classes the factory has
already taught us are watched by a machine instead of remembered by me.

Each initial probe is earned by an observed incident, not invented: orphaned
virtual keys (the restart gotcha — keys minted for an epic outlive its
close), a stale worker (the e5c5569 landing failure — an activity-code fix
dispatched by a worker still running old code), stale worktrees (closed
epics' worktrees accumulating under `.factory/worktrees/`), and store
integrity (the evidence stores are the factory's memory; silent corruption is
the failure mode you find at restore time). Probes gather a snapshot thinly
and evaluate it purely, so every probe's judgment is testable against a
scripted snapshot without a live proxy or Temporal.

**Why this priority**: US1 without probes is a notebook. Probes make the
ledger self-feeding — recurrence tracking only means something when
detection is mechanical. P2 only because US1 is its foundation.

**Independent Test**: Feed each probe a scripted snapshot reproducing its
incident class and a clean snapshot; assert findings with stable keys on the
former, silence on the latter, and the exit-code contract for clean, newly
critical, and service-unreachable runs.

**Acceptance Scenarios**:

1. **Given** a proxy key whose alias names an epic whose workflow is closed,
   **When** `check` runs, **Then** an orphaned-key finding is filed whose key
   is stable across runs (re-runs recur, never duplicate) and whose evidence
   names the alias.
2. **Given** a worker whose process started before the newest commit touching
   `factory/`, **When** `check` runs, **Then** a stale-worker finding is
   filed naming both timestamps — the e5c5569 incident class.
3. **Given** worktrees under `.factory/worktrees/` belonging to closed
   epics, **When** `check` runs, **Then** a stale-worktree finding is filed
   naming the paths.
4. **Given** an evidence store that fails an integrity check, **When**
   `check` runs, **Then** a `critical` finding is filed naming the store.
5. **Given** all probes clean, **When** `check` runs, **Then** exit 0 and the
   ledger gains nothing; **Given** a probe files a new `critical` finding,
   **Then** exit 1; **Given** a service a probe needs is not answering,
   **Then** that probe reports skipped with the service named, other probes
   still run, and `check` exits 2.

---

### User Story 3 - Accepted findings become work the factory builds (Priority: P2)

As the factory operator, I pick findings from the ledger and
`factory-doctor promote` scaffolds a spec directory from them — stories and
requirements stubbed from the findings' own evidence, a `## Work Graph`
section that already compiles, frontmatter reading `state: draft` — so that
the path from "we keep seeing this" to "the factory is building the fix" is
one command plus my review, and never a hand-authored workgraph.

Promotion is scaffolding, not authorship: the operator (or an architect
session) refines the generated prose before flipping `state: ready` — the
flip is deliberately not the doctor's to make. The scaffold's structural
promise is absolute, though: what promote writes, the deriver compiles with
zero rejections, verified by running derivation as promote's own final step.
The loop then closes through the roadmap: promoted findings record their spec
directory, and when that spec's landing is observed or attested, the doctor
resolves them on its next run — and a probe re-reporting one afterward files
it as `regressed`, which is how the ledger distinguishes a fix that landed
from a fix that held.

**Why this priority**: This is the continuous-improvement loop the feature
exists for; it needs US1's records to promote. Without it the ledger is
readable but inert — with it, the audit page's "→ story" column becomes a
command.

**Independent Test**: Promote a group of seeded findings into a scratch specs
root; assert the scaffold's frontmatter, story and FR structure, that
derivation of the scaffold yields a graph with zero rejections, that findings
transition to `promoted` with the spec dir recorded, and that a landed state
on the promoted spec resolves them on the next doctor run.

**Acceptance Scenarios**:

1. **Given** open findings named by key, **When** `promote` runs with a
   target spec slug, **Then** a spec directory is created whose spec.md
   carries `state: draft` frontmatter, one user story per finding with the
   finding's summary, refs, and evidence folded in verbatim, functional
   requirements and a `## Work Graph` block covering every story.
2. **Given** a completed promotion, **When** the deriver runs on the
   scaffolded spec, **Then** it compiles with zero rejections — promote MUST
   have already verified this before reporting success.
3. **Given** a promotion, **When** it succeeds, **Then** each promoted
   finding's status is `promoted` with the spec directory recorded, and
   `list` shows the association.
4. **Given** a promote naming a spec directory that already exists, **When**
   it runs, **Then** it refuses before writing anything.
5. **Given** a promoted finding whose spec's frontmatter reads `state:
   landed`, **When** any doctor command next runs, **Then** the finding
   resolves automatically, recording the spec that resolved it.
6. **Given** a promote whose scaffold fails derivation, **When** it aborts,
   **Then** nothing it wrote survives — the finding stays unpromoted *and*
   the directory is gone, so retrying the same slug is not blocked by the
   refuse-existing-directory rule.

---

### Edge Cases

- A probe's service (proxy, Temporal) not answering is a *skip with the
  service named*, never a finding and never silence: a finding would cry wolf
  on every laptop run, and silence would report "clean" for "unexamined" —
  the distinction `check`'s exit 2 exists to keep.
- A finding key is its identity: renaming a key is creating a new finding,
  and the old one ages out by never recurring. The grammar documents this;
  the doctor never guesses that two keys are the same issue.
- `report --batch` on a file that duplicates a key within itself: refused
  naming the key — one batch, one report per identity, or the occurrence
  count stops meaning "distinct observations".
- Promoting an already-promoted finding: refused naming the spec it is
  already promoted into; a regressed finding, by contrast, may be promoted
  again (the first fix did not hold — new work is exactly right).
- The store bootstraps on first touch, like both existing stores; a missing
  `.factory/doctor.db` is day one, not an error.
- `doctor.db` is host-local evidence, not repo state: it is never committed,
  and its durability story (replication) is itself an open finding in the
  seed corpus (`hardening/litestream-evidence-stores`), deliberately not
  solved here.
- No credential value may reach findings, evidence, scaffolds, or the store —
  probe snapshots carry aliases and hashes, never key material (001's
  discipline; a ledger an operator pipes to a chat session must be safe to
  paste).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The findings grammar MUST define identity as a `category/slug`
  key with open categories, a closed severity set (`critical | warning |
  info`), a closed status set (`open | promoted | resolved | regressed`),
  evidence (summary, refs, notes, source), and occurrence facts (first-seen,
  last-seen, count); unknown severities and statuses MUST be refused naming
  the offender.
- **FR-002**: Re-reporting an existing key MUST recur (count, last-seen,
  latest evidence — never a duplicate record); re-reporting a `resolved` key
  MUST transition it to `regressed` preserving full history; every report
  MUST append to a per-finding event history.
- **FR-003**: Findings MUST persist in `.factory/doctor.db` under the
  evidence-store discipline: WAL with busy timeout, schema bootstrapped
  verbatim from `contracts/doctor-store.sql`, one writer module, and
  identity-keyed upserts so at-least-once callers land on one record.
- **FR-004**: `factory-doctor` MUST provide `report` (single finding via
  flags, or `--batch` from the findings JSON grammar, all-or-nothing),
  `list` (deterministic order: severity, occurrences descending, key), and
  `resolve` (manual, with a reason); exit codes MUST follow the existing
  contract — `0` success, `1` operator-fixable refusal, `2` service not
  answering. The batch file's envelope is part of the grammar: a required
  top-level `source` string applying to every entry in the file, an optional
  `comment` that is ignored, and a required `findings` list whose entries carry
  `key`, `category`, `severity`, `summary`, `refs`, and `notes` — no per-entry
  `source` override, so a file has exactly one provenance. `seed-findings.json`
  in this spec's directory is the grammar's first and largest instance.
- **FR-005**: Probes MUST live in a registry the `check` driver iterates —
  adding a probe MUST NOT require changing the driver — and each probe MUST
  split a thin snapshot gather from a pure evaluation so its judgment is
  testable against scripted snapshots.
- **FR-006**: The initial registry MUST cover the four observed incident
  classes: orphaned proxy keys whose alias names a closed epic; a worker
  process older than the newest commit touching `factory/`; worktrees under
  `.factory/worktrees/` for closed epics; and evidence-store integrity.
  Each probe's finding keys MUST be stable across runs so repeat detections
  recur rather than duplicate.
- **FR-007**: `check` MUST exit `0` when no probe files a new finding, `1`
  when any new `critical` finding is filed, and `2` when any probe was
  skipped because a service it needs did not answer; a skipped probe MUST be
  reported with the service named and MUST NOT prevent other probes from
  running. When a run both files a new critical finding and skips a probe, the
  exit MUST be `2`: an incomplete examination outranks a bad one, because the
  operator's next action is to re-run with the service up, not to read the
  finding.
- **FR-008**: `promote` MUST scaffold a spec directory from named findings —
  frontmatter `state: draft`, one story per finding carrying its evidence
  verbatim, FR stubs, and a `## Work Graph` section — MUST verify the
  scaffold compiles by running derivation before reporting success, MUST
  refuse an existing directory before writing, and MUST NOT write any state
  other than `draft`: flipping to `ready` is the operator's act alone. A
  scaffold that fails its own derivation check MUST leave nothing behind —
  write to a temporary location and rename on success, or remove what was
  written — because a half-written directory would collide with the
  refuse-existing rule and permanently block retrying that slug.
- **FR-009**: Promotion MUST record the spec directory on each promoted
  finding; a promoted finding whose spec is **attested** landed — frontmatter
  `state: landed`, read through the roadmap's own frontmatter grammar — MUST
  resolve automatically on the next doctor invocation, recording what resolved
  it; promoting an already-promoted finding MUST be refused, while promoting a
  `regressed` finding MUST be allowed. Attested only, deliberately:
  observed-landed facts exist solely inside a live `RoadmapWorkflow`'s state,
  reachable only by a Temporal query against a workflow that may have
  continued-as-new or closed, which no cheap sweep at the top of every doctor
  command can rely on. Closing on observation is a follow-on finding, not this
  requirement.
- **FR-010**: No credential value may ever appear in findings, event
  history, probe snapshots, scaffolds, or any doctor output; the sweep MUST
  assert each surface (001's grep-backed pattern).
- **FR-011**: The doctor MUST be read-only against everything but its own
  store and the spec directories it scaffolds: probes MUST NOT delete keys,
  prune worktrees, restart workers, or mutate any factory state — detection
  files findings; remediation is work the findings become.

### Key Entities

- **Finding** — one improvement opportunity with a stable identity: key,
  category, severity, status, evidence, occurrence facts, and (once
  promoted) the spec directory that owns its fix.
- **Finding event** — one observation of a finding: when, from which source,
  at what severity. The recurrence trail `list` sorts by.
- **Probe** — a named detector for one incident class: a thin snapshot
  gather plus a pure evaluation returning findings.
- **Scaffold** — the spec directory `promote` writes: a draft the deriver
  already accepts, awaiting human refinement and the `ready` flip.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The 2026-08-07 audit corpus (`seed-findings.json`, 27
  findings) ingests in one `report --batch` invocation; `list` renders all
  27 with the documented ordering; a chosen subset promotes into a scaffold
  the deriver compiles with zero rejections.
- **SC-002**: Each initial probe, fed a scripted snapshot reproducing its
  incident class, files the expected finding; fed a clean snapshot, files
  nothing; running `check` twice against the same broken snapshot yields
  recurrence, not duplication.
- **SC-003**: Resolve-then-re-report yields `regressed` with history intact,
  demonstrated end-to-end through the CLI, not only the store API.
- **SC-004**: The full existing suite stays green and the feature adds no
  new dependency (constitution III: `sqlite3` and `json` are stdlib, `yaml`
  is roster).
- **SC-005**: A scaffolded spec passes `factory-epic derive` unmodified —
  the structural guarantee measured on every promotion, not sampled.

## Work Graph

US2 and US3 both import the grammar and store US1 lands, so both edges are
**merged**, not passed — the 009 first-run lesson (a pass-edge dispatched
us2 into a worktree with no `factory/roadmap/`) applies verbatim to
`factory/doctor/`. US3 additionally chains on US2 merged rather than running
beside it: both stories extend the same CLI wiring module, and sequential
execution is the same same-file conflict-avoidance argument 006/007 and 009
used. Nothing here touches the epic interpreter, the roadmap workflow, or
the worker: the doctor is CLI verbs over its own store — which is what keeps
this spec buildable by the factory it examines.

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-005, FR-006, FR-007, FR-011]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-008, FR-009, FR-010]
```

## Assumptions

- 009 has landed (this spec's frontmatter edge): US3 reads spec states
  through the roadmap grammar module and the loop-closure semantics lean on
  its observed/attested distinction.
- The proxy admin surface the orphaned-key probe needs (`/key/list` paging)
  is already client-side in `factory/usage/litellm_client.py`; the probe
  composes existing calls and adds none.
- Worktree layout stays `.factory/worktrees/<epic>/<node>` and closed-ness
  of an epic is readable from Temporal through the existing describe path
  the CLI's `status` verb uses.
- The seed corpus ships in this directory and is data, not schema: the
  grammar is defined by FR-001 and the contract DDL; `seed-findings.json`
  is its first, largest test fixture.
- Scheduled/unattended `check` runs (cron, Temporal Schedule) are future
  work, deliberately out of scope: the doctor earns its keep as operator
  verbs first, and scheduling a verb that already works is a small follow-on
  finding — file it in the ledger.

## Decision: detection is durable, remediation is work (decided 2026-08-07, Bryan)

Five calls, made the morning the need was demonstrated:

1. **The ledger is the durable home of triage** — the audit review page was
   the one-shot view; findings live in `.factory/doctor.db` with identity
   and recurrence, not in artifacts or memory files.
2. **The doctor is CLI verbs, not a workflow type.** D-002's supersession
   was paid for the roadmap; the doctor needs no long-lived process to be
   useful, and a scheduled `check` can arrive later without changing any
   verb's contract.
3. **Probes detect; they never remediate** (FR-011). An orphaned key is
   deleted by an operator or by an epic the finding becomes — a diagnostic
   tool that mutates the system under diagnosis is how a doctor becomes a
   disease.
4. **Promotion writes `draft` and stops.** The deriver guarantees the
   scaffold's structure; a human owns its prose and its readiness — the same
   intent/observation split the roadmap grammar established.
5. **Severity and status are closed sets; category is open.** Recurrence
   arithmetic and exit codes compute over severity and status, so they are
   grammar; categories are taxonomy, and refusing a new taxonomy word would
   make the ledger resist exactly the findings it exists to collect.

**The decision-log number is deliberately unassigned here** — claimed at
landing time in `docs/decisions.md`, after whatever the in-flight epics
consume.
