# Feature Specification: Minimal WorkGraph Interpreter

**Feature Branch**: `005-workgraph-interpreter`

**Created**: 2026-08-04

**Status**: Draft — needs `/speckit-clarify` before planning (see Open Questions)

**Input**: The bootstrap-minimal interpreter (D-002, D-018, D-024): one generic
Temporal workflow that reads a WorkGraph JSON DAG for an epic, dispatches nodes to
headless coding agents through the adapter seam, wraps every attempt in component 1's
key lifecycle and component 2's verification ladder, and unlocks downstream edges on
PASS. "Minimal" is defined by the D-024 crossover: just enough interpreter to take
`specs/003-merge-queue/` from spec to a verified branch with no human writing code.
Explicitly deferred: the `verifier` node type for cross-node checks, parallel node
execution, multi-epic scheduling, workgraph.json authoring tooling.

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

---

### Edge Cases

- WorkGraph fails validation (unknown persona, dependency cycle, missing requirement
  keys, dangling edge) → the workflow rejects it at start; nothing dispatches.
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
- **FR-006**: Attempt prompts MUST be assembled from the node's spec context (feature
  spec, plan/tasks excerpts for its requirement keys) plus, on retries, the verbatim
  failure evidence per 002 FR-006 — assembly is pure and unit-testable.
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

### Key Entities

- **WorkGraph**: epic id, target repo/specs root, list of nodes with dependency
  edges; pure data, validated at start.
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

## Assumptions

- Components 1 and 2 are implemented and green; their activities are consumed as-is.
- Tier 1 infrastructure exists for live runs: LiteLLM proxy + Postgres, Temporal
  dev server on the designated worker host, Telegram bot. All tests run against
  fakes/time-skipping (Tier 0).
- Claude Code is the first adapter target; the CLI is present on the worker host.
  The adapter contract keeps it swappable (D-018).
- Single worker host, single epic at a time is acceptable for bootstrap (the
  `.factory/` SQLite constraint); concurrency is a post-bootstrap concern.

## Open Questions (for /speckit-clarify)

- Who writes the WorkGraph for epic 003 — hand-authored JSON (bootstrap-simplest),
  or derived mechanically from 003's tasks.md phases/dependencies (speckit tasks are
  nearly a DAG already)?
- Prompt assembly (FR-006): how much of plan.md/tasks.md context per node, and is
  the ralph PROMPT.md contract the template?
- Worktree lifecycle: one worktree per node reused across attempts (002 assumes
  same-worktree retries) — confirm, and confirm branch naming.
- Does the pause signal need persistence across worker restarts beyond Temporal's
  own replay (i.e., is a paused epic durable by construction)? Presumed yes.
