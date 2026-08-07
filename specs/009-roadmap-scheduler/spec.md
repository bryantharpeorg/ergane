---
state: ready
# Run order decided 2026-08-07: 007 → 009 → 008. 007 and this spec share
# workgraph/models.py (_find_cycle), so they run sequentially. 006's
# requirement is story-level (us1 heartbeat, us2 preflight), carried by
# tasks.md T001; this grammar's edges are spec-level.
depends_on_landed: [003-merge-queue, 007-parallel-dispatch]
---

# Feature Specification: Roadmap Scheduler

**Feature Branch**: `009-roadmap-scheduler`

**Created**: 2026-08-07

**Status**: Drafted the night the factory ran two epics end-to-end and every
hand-off between them was a human. The 003 crossover completed at 22:36 UTC;
007 had been dev-ready for hours; nothing connected those two facts except an
operator noticing. Every step between "an epic finished" and "the next one
started" — judging a spec ready, fresh-cloning at the newly-landed base,
deriving, preflighting, starting — was operator judgment applied to conditions
a machine can read.

**Input**: The factory can run one epic superbly and cannot decide to run the
next one at all. Specs have no machine-readable state ("READY" on tonight's
status board was an operator's judgment extracted from prose), and no component
watches for the moment a dependency lands. The frontmatter block at the top of
this very file is the convention this spec proposes — inert to every parser in
the repo today (verified against the deriver's fence rules and the criteria
snapshotter), load-bearing once US1 lands.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The roadmap is machine-readable (Priority: P1)

As the factory operator, I declare each spec's intent — `draft`, `ready`,
`deferred`, or attested `landed` — in a frontmatter block on the spec itself,
and one command shows me the whole roadmap: every spec, its state, and exactly
what blocks it, so that "what can run next" is a computation instead of my
memory.

Intent is declared; progress is observed. The file may say `ready`; only the
system may say `building`, and "landed" for a dependency edge is a fact derived
from Temporal and git — with one deliberate exception: `state: landed` may be
written by the operator as an *attestation* for work that predates the roadmap
(001, 002, 005 were never epics; nothing will ever observe them landing).

**Why this priority**: Every other story computes over this grammar. It also
has standalone value the day it lands: the status board's READY column stops
being judgment.

**Independent Test**: Add frontmatter to a corpus of spec fixtures; assert the
parser yields states and dependency edges, rejects unknown keys and unknown
states with named findings, and computes readiness correctly against attested
and unsatisfied dependencies.

**Acceptance Scenarios**:

1. **Given** a spec with `state: ready` and `depends_on_landed` naming an
   attested-landed spec, **When** the roadmap is read, **Then** the spec is
   reported dispatchable.
2. **Given** a spec with no frontmatter at all, **When** the roadmap is read,
   **Then** it is `draft` — the field is additive and every existing spec
   remains valid unchanged.
3. **Given** frontmatter with an unknown key or an unknown state value,
   **When** the roadmap is read, **Then** the spec is rejected with a finding
   naming the key and the file — silently dropping a key an author wrote is how
   a roadmap comes to mean something other than it says (the deriver's own
   discipline, applied one level up).
4. **Given** a dependency cycle between specs, **When** the roadmap is read,
   **Then** the cycle is reported naming only the specs on it.
5. **Given** the render command, **When** an operator runs it, **Then** every
   spec appears with its state and, for each blocked spec, the names of the
   unsatisfied dependencies — never a bare "blocked".

---

### User Story 2 - A ready spec dispatches when its dependencies land (Priority: P1)

As the factory operator, when an epic completes with every landing merged, any
spec that was waiting on it dispatches automatically — fresh clone, derive,
preflight, start — so that the gap between "dev-ready" and "building" stops
being measured in operator attention.

One long-lived `RoadmapWorkflow` starts each dispatchable spec's `EpicWorkflow`
as a child workflow and is woken by the child's completion event — no polling
anywhere. "Landed" is computed from the child's returned `EpicStatus`: the epic
`COMPLETED` and every node's landing `MERGED`. An epic that completes with a
`FAILED` node is finished but not landed; its dependents stay blocked and the
roadmap says why.

At most one epic runs at a time by default. Self-hosting epics share one
repository, and two concurrent epics are only safe when their files are
disjoint — a fact the roadmap cannot yet see. The bound is a knob, not a law.

**Why this priority**: This is the feature. US1 without it is a nicer status
board.

**Independent Test**: Under time skipping with scripted epic children, a
two-spec roadmap (`B depends_on_landed A`) runs A to landed and dispatches B
with no external signal; a child completing with a failed landing leaves B
blocked with a finding.

**Acceptance Scenarios**:

1. **Given** a ready spec whose dependencies are landed, **When** capacity is
   free, **Then** the roadmap runs the pre-dispatch pipeline — fresh clone at
   the current default branch, derive, the 006 preflight and 003 onboarding
   checks — and starts the epic as a child workflow.
2. **Given** a pre-dispatch check that refuses (unserved alias, onboarding
   finding, derivation error), **When** dispatch is attempted, **Then** the
   spec parks with the finding verbatim and the roadmap continues with other
   work — one bad spec must not stall the line.
3. **Given** a child epic that completes with all landings merged, **When**
   the parent wakes, **Then** dependent specs become dispatchable in the same
   scheduling pass.
4. **Given** a child epic that completes without landing (failed or killed
   nodes), **When** the parent wakes, **Then** dependents remain blocked and
   the roadmap reports the dependency as finished-but-not-landed.
5. **Given** the concurrency bound, **When** two specs are simultaneously
   dispatchable, **Then** dispatch order follows spec-directory order
   (lexicographic — the numbered-directory convention makes this the roadmap's
   declared order) and the second waits for capacity.

---

### User Story 3 - The roadmap runs indefinitely and answers the operator (Priority: P2)

As the factory operator, the roadmap workflow survives months of epics without
hitting Temporal's history limit, and I can pause it, resume it, promote a
spec, and ask it what it is doing, so that the scheduler earns the same
operational trust the epic interpreter earned tonight.

The history bound is the 006-US1 lesson applied one level up: the roadmap
continues-as-new after each epic concludes, at quiescence — never with a child
in flight — carrying its state forward as an explicit input. Kill semantics
stay at the epic level (`kill_epic` exists and works); killing the roadmap
itself must never kill a mid-flight epic.

**Why this priority**: Real, but the factory can bank value from US2 with an
operator restarting the roadmap weekly. Durability and steering make it
unattended; they do not make it work.

**Independent Test**: Drive a scripted roadmap through several epic
completions; assert each run's history event count is bounded by a constant,
state survives continue-as-new, pause parks dispatch between epics, and a
promoted spec dispatches on the next pass.

**Acceptance Scenarios**:

1. **Given** N sequential epics, **When** the roadmap processes all of them,
   **Then** no single workflow run's history grows with N.
2. **Given** `pause_roadmap`, **When** the current child completes, **Then**
   nothing new dispatches until `resume_roadmap` — the epic pause contract,
   one level up.
3. **Given** `promote_spec` naming a draft spec, **When** the signal lands,
   **Then** the spec is treated as ready on the next scheduling pass and the
   promotion is visible in `roadmap_status` (the file remains the authority of
   record; the signal covers the gap until its next edit).
4. **Given** a roadmap terminated by the operator, **When** a child epic is in
   flight, **Then** the child survives and finishes under its own contract.
5. **Given** `roadmap_status`, **When** queried, **Then** it reports every
   spec's state, the running child, parked findings, and the bound in force.

---

### Edge Cases

- A spec that is `ready` but has no `## Work Graph` section (001/002/005-style
  documents): derivation is the dispatch gate and will refuse; the roadmap must
  surface that as a parked finding, not retry it forever.
- A child workflow id that already exists from tonight's manual operation
  (`epic-006-interpreter-hardening` has five closed runs): starting a new run
  under a reused id is the proven pattern; colliding with a *running* manual
  epic must park with the collision named, never adopt silently.
- The roadmap starting while an operator-started epic is mid-flight: capacity
  accounting must count it or dispatch around it — decided in plan.md; what it
  must never do is assume the world is empty because it just started.
- An attested `landed` on a spec whose work is not actually on the default
  branch: the attestation is the operator's to get right; the roadmap trusts
  it and says in `roadmap_status` that the fact was attested, not observed.
- Frontmatter reaches Temporal payloads via `PromptSources.spec_text` (the
  assembler slices it out of agent prompts, verified). Nothing secret may ever
  appear in frontmatter; the grammar's keys are closed precisely so this stays
  provable.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Spec frontmatter MUST support `state: draft | ready | deferred |
  landed` and `depends_on_landed: [<spec-dir>, ...]`; unknown keys and unknown
  values MUST be rejected with findings naming the offender and the file.
- **FR-002**: A spec without frontmatter MUST read as `draft`; adopting the
  grammar MUST NOT invalidate or alter the meaning of any existing spec.
- **FR-003**: Readiness MUST be computed as `state: ready` with every
  `depends_on_landed` entry satisfied; satisfied means observed-landed (a child
  epic returned COMPLETED with every landing MERGED) or attested (`state:
  landed` in that spec's own frontmatter). The two kinds MUST be
  distinguishable in reporting.
- **FR-004**: A `RoadmapWorkflow` MUST dispatch each dispatchable spec as a
  child `EpicWorkflow`, waking on child completion events — the scheduler MUST
  NOT poll for epic state on any interval.
- **FR-005**: Concurrent child epics MUST be bounded, default one, adjustable
  per roadmap run; dispatch order among simultaneously dispatchable specs MUST
  be deterministic — lexicographic by spec directory name, which the numbered
  directories make the roadmap's declared order.
- **FR-006**: Pre-dispatch MUST run, per spec: fresh target clone at the
  current default branch, derivation, and the existing preflight and onboarding
  checks; any refusal MUST park the spec with the finding and MUST NOT stall
  the roadmap.
- **FR-007**: The roadmap MUST continue-as-new at quiescence after a child
  concludes, carrying its state as an explicit input; no run's history may grow
  with the number of epics processed.
- **FR-008**: The roadmap MUST expose `pause_roadmap`, `resume_roadmap`, and
  `promote_spec` signals and a `roadmap_status` query; terminating the roadmap
  MUST NOT terminate a child epic in flight.
- **FR-009**: No credential value MUST ever reach frontmatter, roadmap
  findings, status output, or the roadmap's workflow input (001's discipline,
  extended): the sweep MUST assert each surface.
- **FR-010**: The supersession of D-002's single-workflow-type invariant MUST
  be recorded in the decision log when this spec's first implementation lands.

### Key Entities

- **Roadmap entry** — one spec directory's declared intent: state, dependency
  edges, and the source file they were read from.
- **Roadmap graph** — the entries plus derived facts: readiness, blockers,
  observed vs attested landings. The scheduling input.
- **RoadmapWorkflow** — the long-lived parent; children are `EpicWorkflow`
  runs. The factory's second workflow type, by recorded decision.
- **Parked finding** — a spec the roadmap tried and refused, with the refusal
  verbatim; cleared by the next frontmatter edit or promotion.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Tonight's hand-off, replayed: with 007 `ready` and dependent on
  003, the roadmap dispatches 007 within one scheduling pass of 003's landing,
  with zero operator actions between the two events.
- **SC-002**: A not-ready or blocked spec never dispatches: no clone, no key,
  no workflow, and the blocker is named in `roadmap_status`.
- **SC-003**: The roadmap processes ten scripted epics with every run's
  history event count under a fixed constant.
- **SC-004**: Killing the roadmap mid-child leaves the child running to its
  own conclusion; restarting the roadmap re-reads the world and continues
  without double-dispatching.
- **SC-005**: The full existing suite stays green; every existing spec parses
  exactly as before under the new grammar.

## Work Graph

US2 depends on US1: the scheduler computes over the grammar and the readiness
rules US1 defines. US3 depends on US2: durability and steering harden a
scheduler that must first exist. Nothing here touches the epic interpreter's
internals — the roadmap consumes `EpicWorkflow` through its public contract
(input, result, signals), which is what makes the child-workflow seam safe.

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003]
US2:
  depends_on: [US1]
  implements: [FR-004, FR-005, FR-006, FR-009]
US3:
  depends_on: [US2]
  implements: [FR-007, FR-008, FR-010]
```

## Assumptions

- 003 has landed: "landed" is defined by the landing phase's terminal states,
  and the pre-dispatch pipeline reuses 003's onboarding gate. This spec's own
  frontmatter declares that dependency.
- 006-US2's preflight exists (it does; it passed tonight) and is reusable at
  dispatch time.
- 007 lands before this epic runs (the frontmatter edge above): both epics
  touch `factory/workgraph/models.py`, and sequential execution is the same
  conflict-avoidance argument 006/007 use (decided 2026-08-07).
- Telegram remains the notification surface; the roadmap emits through the
  existing bridge and adds no new channel. 008, if built, composes: a child
  epic parked on an operator question does not block the roadmap's accounting.
- The concurrency bound stays at one until the roadmap can reason about file
  overlap between specs; raising it is an operator act, not a default.

## Decision: intent in frontmatter, observation in the system (decided 2026-08-06/07, Bryan)

Four calls, made in conversation the night the need was demonstrated:

1. **The state field lives in YAML frontmatter on each spec.md**, not in a
   central roadmap file. It travels with the spec, it is repo-authoritative
   (D-023), and it is invisible to agent prompts (the assembler slices spec.md
   to story sections and FR bullets — verified, not assumed). The cost — no
   one-glance file — is what the US1 render command exists to pay back.
2. **`draft`/`ready`/`deferred`/`landed` are declarations; `building` and
   observed-landed are never written back.** The file says what the operator
   wants; the system reports what is. Tonight's US5 work exists because a
   written status lied; this grammar is designed so the written part cannot.
3. **Orchestration is Temporal-native** — child workflows and completion
   events, not a cron loop re-deriving world state on a timer. The scheduler
   inherits the same durability that let tonight's frozen epic resume across a
   five-hour dead server without losing a step.
4. **Default concurrency is one.** Tonight's two concurrent epics worked
   because their files were hand-picked to be disjoint; the roadmap cannot yet
   see that, so it does not assume it.

**The decision-log number is deliberately unassigned here** — claimed at
landing time in `docs/decisions.md`, after whatever 003 and 006 consume, and
alongside the D-002 supersession FR-010 requires.
