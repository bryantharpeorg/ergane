---
# Attested landed 2026-08-07 (operator): the minimal WorkGraph interpreter
# (spec 005) shipped via the ralph Run 3 bootstrap before the roadmap grammar
# existed, so nothing will ever observe it landing. This is the attestation
# path 009's grammar defines for work that predates the roadmap.
state: landed
---

# Feature Specification: Minimal WorkGraph Interpreter

**Feature Branch**: `005-workgraph-interpreter`

**Created**: 2026-08-04

**Status**: Clarified 2026-08-05 (5 questions, see Clarifications) — ready for
`/speckit-plan`; one low-impact question deferred (see Open Questions)

**Input**: The bootstrap-minimal interpreter (D-002, D-018, D-024): one generic
Temporal workflow that reads a WorkGraph JSON DAG for an epic, dispatches nodes to
headless coding agents through the adapter seam, wraps every attempt in component 1's
key lifecycle and component 2's verification ladder, and unlocks downstream edges on
PASS. "Minimal" is defined by the D-024 crossover: just enough interpreter to take
`specs/003-merge-queue/` from spec to a verified branch with no human writing code.
Explicitly deferred: the `verifier` node type for cross-node checks, parallel node
execution, multi-epic scheduling. The WorkGraph is never hand-authored: it is
compiled mechanically from the epic's spec (FR-011).

## Clarifications

### Session 2026-08-05

- Q: Who writes the WorkGraph for epic 003 — hand-authored JSON, or derived
  mechanically from tasks.md? → A: Neither; spec-to-graph compilation is core
  Ergane functionality. The spec grammar is extended **additively** (no speckit
  template fork — vendored `.specify/templates/` are never modified) with a
  `## Work Graph` section holding a fenced YAML block that declares, per user
  story, `depends_on` (story ids) and `implements` (FR keys). The deriver
  compiles this into `workgraph.json` — one node per user story — making the
  spec the source of truth and the graph a compiled, inspectable artifact.
  Missing or invalid declarations fail derivation loudly; that validation, not
  the template, enforces the convention.
- Q: Prompt assembly (FR-006) — how much plan/tasks context, and is the ralph
  PROMPT.md contract the template? → A: Two nested loops (Sonar "Agent Centric
  Development Cycle" pattern). Inner agentic loop: the prompt embeds the
  ralph-derived contract generalized to the node's task slice — work the story's
  tasks in order, test-first, run the deterministic gate after each task, commit
  per task, stop when the slice is done or blocked. Context: the story's spec
  sections (story, acceptance scenarios, its `implements` FRs), full plan.md,
  the story's tasks.md slice; retries append verbatim failure evidence. Outer
  verification loop: the interpreter's attempt → 002 ladder → retry cycle. The
  inner loop is advisory (agent fast feedback); the outer loop is authoritative —
  agent self-reported success never marks a node PASSED (FR-012).
- Q: Worktree lifecycle — one worktree per node reused across attempts, and
  branch naming? → A: Confirmed. Exactly one worktree per node, created at first
  dispatch, reused across all attempts (including debugger, per 002), removed
  only after terminal-state salvage. Branch naming: `factory/<epic-id>/<node-id>`
  (e.g. `factory/003-merge-queue/us1`) — machine branches namespaced under
  `factory/`, attributable by ref alone (FR-013).
- Q: Where does a node's wall-clock timeout (FR-010) come from? → A: Persona
  registry default — `personas.yaml` gains a `timeout` field per agent-backed
  persona — overridable per story in the `## Work Graph` YAML declaration for
  exceptional nodes. Code never hardcodes a timeout (constitution VII pattern:
  operator-editable registry resolves runtime defaults).
- Q: How does an agent attempt receive the target repo's coding standards? →
  A: `factory.yaml` gains an optional `standards` key (path to the repo's
  standards doc); when declared, the assembled prompt includes a read-and-obey
  directive for it (FR-006). Adapter-agnostic by construction (D-018) — no
  reliance on any one agent's native CLAUDE.md auto-loading. Ergane's own
  `factory.yaml` points at `.specify/memory/constitution.md`, restoring ralph's
  "read the constitution and obey it" step for the 003 crossover.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Interpret a WorkGraph end to end (Priority: P1)

As the factory operator, I hand the interpreter an epic's WorkGraph (nodes with
persona, spec_ref, requirement keys, dependency edges) and it drives every node
through dispatch → agent attempt → verification → retry ladder to a terminal state,
with downstream edges unlocking only on PASS.

**Why this priority**: This is the component; everything else in the factory already
exists as callable parts (001 activities, 002 activities and ladder) waiting for the
loop that composes them.

**Independent Test**: Run the interpreter in Temporal's time-skipping test environment
against a small scripted graph (fake agent activity, scripted verification results);
assert node state transitions, edge unlocking, and terminal epic state.

**Acceptance Scenarios**:

1. **Given** a WorkGraph with nodes A → B (B depends on A), **When** the interpreter
   runs and A's attempt verifies PASS, **Then** B dispatches only after A's PASS and
   the epic completes when all nodes are terminal.
2. **Given** a node whose verification fails, **When** the ladder returns RETRY,
   **Then** the interpreter re-dispatches the node with the failure evidence in the
   prompt and the attempt counter incremented, per 002's ladder semantics.
3. **Given** a node that exhausts the ladder into ESCALATE, **When** the operator
   answers the Telegram escalation with KILL, **Then** the node terminates KILLED,
   its worktree is salvaged to its branch (constitution VI), and dependent nodes
   never dispatch.
4. **Given** an epic interrupted mid-flight (worker restart), **When** the workflow
   replays, **Then** no attempt is double-dispatched and no key is double-issued
   (all side effects in activities; workflow logic is pure).

---

### User Story 2 - Agent attempts through the adapter seam (Priority: P1)

As the factory, each producing node's attempt runs a headless coding agent (Claude
Code first) in an isolated git worktree via the narrow adapter (D-018): launch,
monitor, terminate, classify termination. The attempt is bracketed by component 1's
`issue_attempt_key` / `teardown_attempt`, and its transcript is preserved.

**Why this priority**: The adapter is the only place the factory touches an agent;
without it US1 has nothing real to dispatch. Ties with US1; testable with a fake
process.

**Independent Test**: Run the adapter activity against a stub executable standing in
for the agent CLI; assert env construction (proxy URL + virtual key + model alias),
worktree isolation, termination classification, and transcript archiving.

**Acceptance Scenarios**:

1. **Given** a dispatched node, **When** the adapter launches the agent, **Then** the
   agent process receives exactly: the node prompt, the worktree cwd, and env
   carrying the proxy base URL, the node's virtual key, and the persona's model
   alias — never the master key or bot token.
2. **Given** an agent process that exits, **When** the adapter classifies it,
   **Then** the result is exactly one of the shared Termination values (component 1's
   enum) plus a log/transcript path — no diff, no usage numbers (those are read from
   the worktree and ledger respectively, D-018).
3. **Given** an agent that exceeds the node's wall-clock timeout, **When** the
   deadline passes, **Then** the adapter terminates the process (TERM then KILL),
   classifies TIMEOUT, and the worktree is salvaged.
4. **Given** any terminal attempt, **When** teardown completes, **Then** the full
   session transcript file is archived under the factory state directory keyed by
   the attempt's attribution (epic/node/attempt) and referenced from the run record.

---

### User Story 3 - Operate a running epic (Priority: P2)

As the factory operator, I can start an epic from a workgraph file, watch node
states, and pause or kill the epic — via a small CLI and Temporal signals — without
touching workflow internals.

**Why this priority**: The bootstrap loop needs a human-holdable steering wheel, but
a minimal one; the Temporal Web UI covers deep inspection.

**Independent Test**: Start a scripted epic via the CLI against the dev server;
signal pause and kill; assert the workflow honors both and the CLI's status output
matches workflow state.

**Acceptance Scenarios**:

1. **Given** a workgraph JSON file, **When** I run the start CLI, **Then** an epic
   workflow starts on the `factory` namespace / `workgraph` queue with the graph as
   input, and the CLI prints the workflow id.
2. **Given** a running epic, **When** I signal `pause_epic` (directly or via a
   Telegram escalation choice), **Then** no new nodes dispatch until `resume_epic`,
   while in-flight attempts run to completion.
3. **Given** a running epic, **When** I signal `kill_epic`, **Then** in-flight
   attempts are terminated through the adapter, worktrees are salvaged, keys are
   torn down, and the epic reaches a terminal KILLED state with every node recorded.
4. **Given** an epic spec with a `## Work Graph` section, **When** I run the
   derive CLI, **Then** `workgraph.json` is emitted (or the specific validation
   errors are listed and nothing is emitted) without starting any workflow.

---

### Edge Cases

- WorkGraph fails validation (unknown persona, dependency cycle, missing requirement
  keys, dangling edge) → the workflow rejects it at start; nothing dispatches.
- The spec's `## Work Graph` section is missing, malformed, or references an
  unknown story id or FR key → derivation fails with the specific error and emits
  nothing; the epic cannot start from an undeclared graph.
- A node's `snapshot_criteria` fails at dispatch (bad spec) → node fails without an
  agent attempt; ladder and escalation apply as for any failure.
- Worker host restarts mid-attempt → Temporal retries the attempt activity; the
  adapter detects and reaps the orphaned agent process before relaunching.
- An epic references a spec file that changes mid-flight → 002's drift flag surfaces
  in verification records; the interpreter never re-parses mid-epic (FR-010 of 002).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The interpreter MUST be one generic Temporal workflow (namespace
  `factory`, task queue `workgraph`) whose logic is fixed and whose per-epic behavior
  comes entirely from WorkGraph data (D-002); node routing, retry, and unlock
  decisions are pure workflow code with all side effects in activities.
- **FR-002**: The WorkGraph input MUST be validated before any dispatch: nodes carry
  `id`, `persona` (resolvable in the registry), `spec_ref`, `requirement_keys`,
  `depends_on`; the graph must be acyclic with no dangling references.
- **FR-003**: A node MUST dispatch only when all its `depends_on` nodes are PASSED
  (FR-005 of 002); a node with no dependencies dispatches at epic start.
- **FR-004**: Every attempt MUST be bracketed by component 1's `issue_attempt_key`
  and `teardown_attempt` (constitution V), and every verification recorded via
  component 2's `record_verification` before any ladder action is taken.
- **FR-005**: The agent adapter MUST be a separate activity with the D-018 contract:
  inputs (prompt, worktree path, env: proxy URL + virtual key + model alias, session
  id), outputs (termination class from the shared enum + transcript/log path) and
  nothing else; diffs come from the worktree, usage from the ledger.
- **FR-006**: Attempt prompts MUST be assembled — purely and unit-testably — from:
  the node's story sections (story, acceptance scenarios, its `implements` FRs),
  the epic's full plan.md, the story's tasks.md slice, and, on retries, the
  verbatim failure evidence per 002 FR-006. The prompt embeds the ralph-derived
  inner-loop contract scoped to the node: work the slice task-by-task, test-first,
  run the deterministic gate after each task, commit per task, stop when the
  slice is done or blocked. When the target repo's `factory.yaml` declares a
  `standards` path, the prompt MUST include a read-and-obey directive for that
  document.
- **FR-007**: Every attempt's full agent transcript MUST be archived on teardown
  under the factory state directory, keyed by epic/node/attempt, on every
  termination path; transcripts stay on the worker host and are never committed to
  any repository.
- **FR-008**: The workflow MUST honor `pause_epic`, `resume_epic`, and `kill_epic`
  signals, and route 002's escalation-resolution signals to the owning node's
  ladder; kill paths salvage worktrees before cleanup (constitution VI).
- **FR-009**: A start CLI MUST launch an epic from a workgraph JSON file and print
  the workflow id; a status query MUST report per-node states. Anything richer is
  out of scope (Temporal Web UI covers it).
- **FR-010**: Node wall-clock timeouts MUST be enforced through the adapter
  (terminate, classify TIMEOUT, salvage); a hung agent can never wedge the epic.
  The timeout value resolves persona-first: the persona registry's `timeout`
  default (new field, agent-backed personas), overridable per story in the
  `## Work Graph` YAML declaration; code never hardcodes a timeout.
- **FR-011**: The WorkGraph MUST be compiled mechanically from the epic's spec: a
  derive step (exposed alongside the FR-009 CLI) parses the spec's `## Work Graph`
  section — a fenced YAML block mapping each user story to `depends_on` (story
  ids) and `implements` (FR keys) — and emits one node per user story. Derivation
  is a pure function (spec text in → WorkGraph out), unit-testable without
  infrastructure, and MUST fail loudly naming the story when a declaration is
  missing or references an unknown story id or FR key. The section is an additive
  authoring convention; vendored speckit templates are never modified.
- **FR-012**: The agent's inner loop (self-run gates, per-task commits) is
  advisory only; a node reaches PASSED solely through 002's independent
  verification ladder after the attempt terminates. Agent self-reported success
  MUST never influence node state.
- **FR-013**: Each node MUST have exactly one git worktree, created at first
  dispatch on branch `factory/<epic-id>/<node-id>` and reused across all of the
  node's attempts (including debugger attempts, per 002's same-worktree retry
  semantics); it is removed only after the node reaches a terminal state with
  its salvage commit (constitution VI) on the branch.

### Key Entities

- **WorkGraph**: epic id, target repo/specs root, list of nodes with dependency
  edges; compiled from the epic spec's `## Work Graph` declaration (one node per
  user story), never hand-authored; pure data, validated at start.
- **NodeState**: PENDING → KEY_ISSUED → RUNNING → VERIFYING → {PASSED | FAILED →
  ladder → RETRY/DEBUGGER/ESCALATE | KILLED}; the workflow's in-memory record per
  node, queryable.
- **AttemptContext**: everything one attempt needs (prompt, worktree, key lease,
  model alias, timeout) — assembled pure, consumed by activities.
- **AdapterResult**: termination class + transcript path (D-018's narrow output).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In the time-skipping test environment, a scripted 3-node graph
  (chain + independent leaf) reaches epic completion with node states, edge-unlock
  order, and attempt counts exactly as scripted — deterministically across replays.
- **SC-002**: Zero dispatches of a node whose dependencies are not all PASSED, in
  every test including failure and kill paths.
- **SC-003**: 100% of attempts in tests have a matching usage-ledger row (component
  1) and verification record (component 2) — no attempt exists that both stores
  don't know about.
- **SC-004**: 100% of terminal attempts (including TIMEOUT and KILLED) leave a
  salvage commit on the node branch and an archived transcript.
- **SC-005**: The end-to-end bootstrap epic — Ergane dispatching
  `specs/003-merge-queue/` against its own repo (D-024) — produces a verified
  branch with zero human-written code, with a human merging manually.
- **SC-006**: The deriver, run against a fixture spec with a `## Work Graph`
  section, emits exactly the expected nodes, edges, and requirement keys, and
  rejects fixtures with a missing story declaration, unknown story id, or unknown
  FR key — deterministically, with the offending story named in the error.

## Assumptions

- Components 1 and 2 are implemented and green; their activities are consumed as-is.
- Tier 1 infrastructure exists for live runs: LiteLLM proxy + Postgres, Temporal
  dev server on the designated worker host, Telegram bot. All tests run against
  fakes/time-skipping (Tier 0).
- Claude Code is the first adapter target; the CLI is present on the worker host.
  The adapter contract keeps it swappable (D-018).
- Single worker host, single epic at a time is acceptable for bootstrap (the
  `.factory/` SQLite constraint); concurrency is a post-bootstrap concern.
- The `## Work Graph` spec-grammar extension is an additive authoring convention
  enforced by derivation-time validation, not by template changes — keeping this
  repo off the speckit upgrade path. `specs/003-merge-queue/spec.md` gains its
  declaration before the crossover epic, and the extension is recorded as a
  decision-log entry.
- Ergane's own `factory.yaml` is committed before the crossover epic, declaring
  its gate commands and `standards: .specify/memory/constitution.md`. The
  `standards` key is one optional addition to the factory.yaml schema (owned by
  002's loader); the `timeout` field is one addition to the persona registry.

## Open Questions (for /speckit-clarify)

- Does the pause signal need persistence across worker restarts beyond Temporal's
  own replay (i.e., is a paused epic durable by construction)? Presumed yes.
