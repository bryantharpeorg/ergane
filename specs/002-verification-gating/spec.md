# Feature Specification: Verification Gating

**Feature Branch**: `002-verification-gating`

**Created**: 2026-07-24

**Status**: Draft

**Input**: Component 2 of the Ergane factory (D-001, D-008, D-009, D-011, D-019,
D-023): verifier node type, mechanical Spec Kit criteria parser, two-tier verification
(deterministic gates + bounded LLM judge) running in the inner loop before any PR,
retry-with-feedback, and the Telegram escalation path. Downstream DAG edges unlock only
on pass.

## Clarifications

### Session 2026-07-24

- Q: Is verification a DAG node or a phase of producing nodes? → A: Both — every producing node has a built-in verify phase (attempt → verify → retry, same worktree, per-attempt keys); an explicit `verifier` node type additionally exists for cross-node/integration checks (e.g. after a fan-in). Downstream edges unlock on verified-PASS in either form.
- Q: Judge pass criterion? → A: Strict per-scenario — every acceptance scenario must individually pass; any failing scenario yields retry/fail with that scenario cited in the feedback. Applies to both verification forms.
- Q: Default retry ladder? → A: 3 total attempts per node (initial + 2 retries, any failure mix; judge-initiated retries still capped at 2 within that), then one debugger cycle, then Telegram escalation. Configurable; default is 3.
- Q: Which nodes may legitimately produce an empty diff? → A: Persona-derived — `write_scope: read` personas (researcher, judge; also verifier nodes) are exempt from the empty-diff check but must produce their declared artifact (report, verdict) to pass; write-scoped personas (implementer, debugger, architect) always require a non-empty diff.
- Q: Notifier library? → A: `python-telegram-bot` approved (constitution III roster updated); long-polling, inline keyboards, callback handling out of the box.

### Session 2026-08-04

- Q: Input grammar still OpenSpec deltas? → A: No — Spec Kit feature specs (D-023). US1, FR-001, SC-001, the data model's criteria entities, and the judge rubric are re-scoped to the Spec Kit template grammar; delta operations (ADDED/MODIFIED/REMOVED/RENAMED) and rename mapping are removed entirely.
- Q: How are FR-keyed nodes judged, given FRs carry no scenarios? → A: Nodes dispatched on functional-requirement keys only are verified by deterministic gates + output check (no judge — nothing scenario-shaped to score); the judge runs whenever the node's CriteriaSet contains story (`US<n>`) scenarios. This is the existing "judge is None when the node has no scenarios" rule, now load-bearing.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Mechanical criteria parsing (Priority: P1)

As the factory, I extract acceptance criteria from a Spec Kit feature spec
(`specs/<feature>/spec.md`, D-023) without any LLM involvement, so verification is
grounded in exactly what the spec says and parsing is deterministic and testable.

**Why this priority**: Everything downstream (gates, judge, unlocking) consumes parsed
criteria; wrong parsing poisons the whole component.

**Independent Test**: Feed fixture spec files exercising the full template grammar;
assert the extracted requirement/scenario structures.

**Acceptance Scenarios**:

1. **Given** a feature spec at `specs/<feature>/spec.md`, **When** parsed, **Then**
   each `### User Story <n> - <title> (Priority: P<m>)` header yields a story
   requirement keyed `US<n>` with its title and priority, each numbered item under
   its `**Acceptance Scenarios**:` list yields one acceptance criterion with scenario
   id `US<n>-S<k>` and its bold **Given/When/Then/And** segments captured verbatim in
   order, and each `- **FR-###**:` bullet under `### Functional Requirements` yields
   a functional requirement keyed `FR-###`.
2. **Given** an FR body lacking `SHALL`/`MUST`, a user story with zero acceptance
   scenarios, a scenario item with no bold keyword steps, or duplicate requirement
   keys, **When** parsed, **Then** a validation error identifies the exact
   requirement.
3. **Given** markdown headers or FR-like bullets inside fenced code blocks, **When**
   parsed, **Then** they are ignored (fence masking).
4. **Given** requirement keys requested at node dispatch (e.g. `US2`, `FR-007`),
   **When** the spec lacks one of them, **Then** parsing fails naming the missing
   key; otherwise the CriteriaSet contains exactly the requested requirements.

---

### User Story 2 - Two-tier verification of a node's diff (Priority: P1)

As the WorkGraph interpreter, after an implementer/debugger node produces work, a
verifier evaluates it: deterministic gates first (always), then an LLM judge scores the
diff against the parsed scenarios — all inside our sandbox, before any PR exists. Only a
pass unlocks downstream edges.

**Why this priority**: This is the gate that makes the factory trustworthy; it is the
component's reason to exist. Ties with US1; testable with a stub parser.

**Independent Test**: Run verification against a prepared worktree with known-passing
and known-failing gates and a scripted judge; assert verdict composition and edge
unlocking.

**Acceptance Scenarios**:

1. **Given** a target repo with a committed `factory.yaml` declaring runtime and
   test/lint/typecheck commands, **When** the verifier runs, **Then** each declared
   gate executes in the node's sandboxed worktree with exit-code semantics (0 = pass)
   and per-gate results are recorded.
2. **Given** any deterministic gate fails, **When** verification concludes, **Then**
   the verdict is FAIL, the judge is not consulted (cheapest-first), and gate output is
   preserved for the retry prompt.
3. **Given** all deterministic gates pass, **When** the judge runs, **Then** it is the
   `judge` persona (cheap tier, read-only, own attribution key per component 1), receives
   the diff plus the parsed scenarios for the node's requirement(s), and returns
   pass / retry-with-feedback / fail with per-scenario reasoning.
4. **Given** a non-no-op node whose diff is empty, **When** verification runs, **Then**
   the verdict is FAIL regardless of gate results (anti-rubber-stamp).
5. **Given** a verdict of PASS, **When** the interpreter processes it, **Then**
   downstream edges depending on this node unlock; on any other verdict they stay
   locked.

---

### User Story 3 - Retry with feedback, then escalate (Priority: P2)

As the factory operator, a failed verification doesn't immediately page me: the node
retries with the failure evidence injected verbatim, a debugger persona takes over
after repeated failures, and only then do I get a Telegram escalation.

**Why this priority**: Turns verification from a gate into a loop that usually
self-heals; depends on US2.

**Independent Test**: Script a verifier that fails N times; assert the retry ladder,
feedback injection, and escalation firing.

**Acceptance Scenarios**:

1. **Given** a FAIL or retry verdict, **When** the node retries, **Then** the retry
   prompt contains the failing gate output and/or the judge's feedback verbatim, and
   the attempt counter increments.
2. **Given** judge-initiated retries, **When** they recur, **Then** judge retries are
   capped at 2 (bounded judge spend) within a default total of 3 attempts per node
   (initial + 2 retries, from any mix of gate and judge failures; configurable).
3. **Given** the retry cap is exhausted, **When** the next failure occurs, **Then**
   the node is handed to the `debugger` persona (fresh attribution key, same worktree)
   for one diagnosis-and-fix cycle before any human escalation.
4. **Given** the debugger cycle also fails verification, **When** that verdict lands,
   **Then** a Telegram escalation fires with the failure history and choices
   [retry once more | kill node | pause epic], each mapped to an orchestration signal;
   no response for 1 hour → kill (worktree salvaged per component 1).

---

### Edge Cases

- `factory.yaml` missing or malformed in the target repo → node fails verification
  with a configuration error (never "pass by default").
- A gate command hangs → per-gate timeout, recorded as TIMEOUT, verdict FAIL.
- Judge response is malformed/unparseable → counts as a judge retry, not a pass.
- Judge model/backend unavailable mid-judgment → verification records the judge as
  unavailable and the verdict falls back to deterministic-gates-only with an operator
  notification. (Budget-breach handling deferred with spec 004.)
- Scenario text changed between dispatch and verify (spec edited mid-flight) → verify
  against the criteria snapshot taken at dispatch, and flag the drift in the result.
- Node dispatched on FR keys only (no scenarios anywhere in its CriteriaSet) → gates +
  output check decide; the judge is not invoked (nothing scenario-shaped to score).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST parse acceptance criteria from Spec Kit feature specs
  (`specs/<feature>/spec.md`) mechanically (no LLM), keying on the template grammar
  (D-023, architecture §2): `### User Story <n> - <title> (Priority: P<m>)` story
  headers (key = `US<n>`), numbered acceptance-scenario items whose bold
  **Given/When/Then/And** segments are the steps (scenario id `US<n>-S<k>`, steps
  verbatim in order), and `- **FR-###**:` functional-requirement bullets (key =
  `FR-###`; body must contain SHALL/MUST), with code-fence masking, duplicate-key
  rejection, and requirement filtering by requested keys.
- **FR-002**: Verification MUST run the target repo's declared gates (test/lint/
  typecheck from committed `factory.yaml`) in the node's sandboxed worktree with
  exit-code semantics and per-gate timeout, recording per-gate results. It runs in two
  forms: (a) as a built-in phase of every producing node's attempt lifecycle, and
  (b) as an explicit `verifier` DAG node type for checks spanning multiple upstream
  nodes (integration/fan-in gates); both forms share the same gate runner and verdict
  model.
- **FR-003**: The LLM judge MUST run only after all deterministic gates pass, as the
  `judge` persona on its own attribution key, scoring the node's diff against the parsed
  scenarios and returning pass / retry-with-feedback / fail with per-scenario
  reasoning. The verdict criterion is strict: PASS requires every scenario to
  individually pass; any failing scenario forces retry-with-feedback (or fail) and
  MUST be cited by name in the feedback. Holistic or threshold-based passing is
  prohibited, in both verification forms.
- **FR-004**: A node whose persona has write scope (`worktree` or `docs`) MUST fail
  verification on an empty diff regardless of gate and judge results
  (anti-rubber-stamp). Nodes whose persona is `write_scope: read` (researcher, judge)
  and verifier nodes are exempt from the diff check but MUST produce their declared
  output artifact (report, verdict) to pass — no node passes with neither diff nor
  artifact.
- **FR-005**: Downstream DAG edges MUST unlock only on an overall PASS verdict.
- **FR-006**: Retries MUST inject the failure evidence (gate output, judge feedback)
  verbatim into the retry prompt. Judge-initiated retries MUST be capped at 2; total
  attempts per node default to 3 (initial + 2 retries, any failure mix),
  configurable per deployment.
- **FR-007**: After retry exhaustion the node MUST be routed to the `debugger` persona
  for one bounded cycle before human escalation.
- **FR-008**: Escalations MUST be delivered via Telegram with inline-button choices
  mapped to orchestration signals, defaulting to kill after 1 hour of silence.
- **FR-009**: The judge MUST never run as a CI/merge-queue check; its scope is the
  inner loop only.
- **FR-010**: Verification MUST evaluate against the criteria snapshot captured at node
  dispatch and flag any drift from the current spec state.

### Key Entities

- **CriteriaSet**: parsed requirements/scenarios for one node — requirement kind
  (story/functional) and key, scenario ids and steps; snapshotted at dispatch.
- **GateResult**: one deterministic gate execution — name, command, exit status,
  duration, output tail, pass/fail/timeout.
- **JudgeVerdict**: pass | retry (with feedback text) | fail, plus per-scenario
  reasoning and the judge attempt number.
- **VerificationResult**: composition of gate results + optional judge verdict +
  anti-rubber-stamp check → overall PASS/FAIL, with the evidence bundle used for
  retries and escalation.
- **factory.yaml**: per-target-repo manifest — runtime image, test/lint/typecheck
  commands.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Criteria parsing matches Spec Kit template semantics on a fixture corpus
  covering every grammar production, including at least one of Ergane's own feature
  specs verbatim (100% of fixtures).
- **SC-002**: Zero verdicts of PASS ever issued while any deterministic gate fails or
  the diff is empty on a non-no-op node.
- **SC-003**: Judge cost per node is bounded: at most (1 + 2 retries) judge invocations
  per verification cycle, never invoked in CI.
- **SC-004**: In failure-injection tests, 100% of retry prompts contain the prior
  failure evidence verbatim.
- **SC-005**: Every human escalation carries the full failure history and resolves via
  button, or defaults to kill at 1 hour.

## Assumptions

- Component 1 (per-node usage tracking, `001-usage-tracking`) is complete: judge and
  debugger nodes get attribution keys and ledger rows through it. Budget caps and
  breach policy are deferred (spec 004) — "own budget key" phrases in this spec mean
  the node's own usage-tracked key, with no cap.
- Target repos are prepared with a committed `factory.yaml`; its schema is owned by
  this component.
- The Telegram notifier (long-polling, inline buttons → signals) is built as part of
  this component using `python-telegram-bot` (approved 2026-07-24, constitution III).
- The judge rubric consumes parsed scenarios as-is; rubric wording is an implementation
  detail of the plan, not this spec.
- The input grammar is the Spec Kit feature-spec template (D-023). Spec Kit has no
  CLI/JSON emitter, so the markdown parser is the sole mechanical path; Ergane's own
  `specs/` directory provides real-world fixture material (D-024).
