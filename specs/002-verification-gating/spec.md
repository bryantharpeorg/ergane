# Feature Specification: Verification Gating

**Feature Branch**: `002-verification-gating`

**Created**: 2026-07-24

**Status**: Draft

**Input**: Component 2 of the Ergane factory (D-001, D-008, D-009, D-011, D-019):
verifier node type, mechanical OpenSpec criteria parser, two-tier verification
(deterministic gates + bounded LLM judge) running in the inner loop before any PR,
retry-with-feedback, and the Telegram escalation path. Downstream DAG edges unlock only
on pass.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Mechanical criteria parsing (Priority: P1)

As the factory, I extract acceptance criteria from a vanilla OpenSpec change delta
without any LLM involvement, so verification is grounded in exactly what the spec says
and parsing is deterministic and testable.

**Why this priority**: Everything downstream (gates, judge, unlocking) consumes parsed
criteria; wrong parsing poisons the whole component.

**Independent Test**: Feed fixture delta files exercising the full grammar; assert the
extracted requirement/scenario structures.

**Acceptance Scenarios**:

1. **Given** a delta spec at `openspec/changes/<name>/specs/<capability>/spec.md`,
   **When** parsed, **Then** each `## ADDED|MODIFIED|REMOVED|RENAMED Requirements`
   section yields its operation bucket, each `### Requirement: <name>` yields a
   requirement keyed by its trimmed header text, and each `#### Scenario: <desc>` under
   it yields one acceptance criterion with its `- **GIVEN/WHEN/THEN/AND**` steps
   captured verbatim.
2. **Given** a requirement body lacking `SHALL`/`MUST`, or a requirement with zero
   scenarios, **When** parsed, **Then** a validation error identifies the exact
   requirement (mirroring upstream OpenSpec validation).
3. **Given** markdown headers inside fenced code blocks, **When** parsed, **Then** they
   are ignored (fence masking).
4. **Given** `- FROM:`/`- TO:` lines in a RENAMED section, **When** parsed, **Then**
   the rename mapping is extracted.

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
   `judge` persona (cheap tier, read-only, own budget key per component 1), receives
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
   capped at 2 (bounded judge spend); gate-fail retries are capped at a configured
   limit.
3. **Given** the retry cap is exhausted, **When** the next failure occurs, **Then**
   the node is handed to the `debugger` persona (fresh budget key, same worktree) for
   one diagnosis-and-fix cycle before any human escalation.
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
- Judge budget key breaches mid-judgment → component 1 policy (hard-kill) applies;
  verification records the judge as unavailable and the verdict falls back to
  deterministic-gates-only with an operator notification.
- Scenario text changed between dispatch and verify (spec edited mid-flight) → verify
  against the criteria snapshot taken at dispatch, and flag the drift in the result.
- REMOVED requirements → verified by absence: gates still run; judge confirms no
  surviving behavior contradicts the removal.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST parse acceptance criteria from vanilla OpenSpec delta
  files mechanically (no LLM), keying on the stock grammar: operation sections
  (`## ADDED|MODIFIED|REMOVED|RENAMED Requirements`), `### Requirement:` headers
  (identity = trimmed header text; body must contain SHALL/MUST), `#### Scenario:`
  blocks, `- **GIVEN/WHEN/THEN/AND**` steps, `- FROM:`/`- TO:` renames, with code-fence
  masking.
- **FR-002**: The verifier node type MUST run the target repo's declared gates
  (test/lint/typecheck from committed `factory.yaml`) in the node's sandboxed worktree
  with exit-code semantics and per-gate timeout, recording per-gate results.
- **FR-003**: The LLM judge MUST run only after all deterministic gates pass, as the
  `judge` persona on its own budget key, scoring the node's diff against the parsed
  scenarios and returning pass / retry-with-feedback / fail with per-scenario
  reasoning.
- **FR-004**: A non-no-op node with an empty diff MUST fail verification regardless of
  gate and judge results.
- **FR-005**: Downstream DAG edges MUST unlock only on an overall PASS verdict.
- **FR-006**: Retries MUST inject the failure evidence (gate output, judge feedback)
  verbatim into the retry prompt. Judge-initiated retries MUST be capped at 2; total
  retries at a configured cap.
- **FR-007**: After retry exhaustion the node MUST be routed to the `debugger` persona
  for one bounded cycle before human escalation.
- **FR-008**: Escalations MUST be delivered via Telegram with inline-button choices
  mapped to orchestration signals, defaulting to kill after 1 hour of silence.
- **FR-009**: The judge MUST never run as a CI/merge-queue check; its scope is the
  inner loop only.
- **FR-010**: Verification MUST evaluate against the criteria snapshot captured at node
  dispatch and flag any drift from the current spec state.

### Key Entities

- **CriteriaSet**: parsed requirements/scenarios for one node — operation, requirement
  key, scenario descriptions and steps; snapshotted at dispatch.
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

- **SC-001**: Criteria parsing matches upstream OpenSpec semantics on a fixture corpus
  covering every grammar production (100% of fixtures).
- **SC-002**: Zero verdicts of PASS ever issued while any deterministic gate fails or
  the diff is empty on a non-no-op node.
- **SC-003**: Judge cost per node is bounded: at most (1 + 2 retries) judge invocations
  per verification cycle, never invoked in CI.
- **SC-004**: In failure-injection tests, 100% of retry prompts contain the prior
  failure evidence verbatim.
- **SC-005**: Every human escalation carries the full failure history and resolves via
  button, or defaults to kill at 1 hour.

## Assumptions

- Component 1 (per-node budgets) is complete: verifier/judge/debugger nodes get keys,
  breach policies, and ledger rows through it.
- Target repos are prepared with a committed `factory.yaml`; its schema is owned by
  this component.
- The Telegram notifier (long-polling, inline buttons → signals) is built as part of
  this component; `python-telegram-bot` requires operator approval before adoption
  (constitution III).
- The judge rubric consumes parsed scenarios as-is; rubric wording is an implementation
  detail of the plan, not this spec.
- OpenSpec `--json` output is an acceptable alternative input to markdown parsing if it
  proves more stable; either way FR-001's semantics hold.
