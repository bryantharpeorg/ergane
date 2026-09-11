---
state: ready
---

# Feature Specification: a judge cannot waive a concrete counterexample

## Why this repair exists

During 158/US4, the judge read the whole 39,678-byte diff and explicitly found
that the default analysis path passed an integer file descriptor to `Path`.
It nevertheless marked every scenario and the overall verdict PASS, calling the
crash a non-blocking observation because no committed test exercised that
branch. The scenario said that analysis-only `findings-ingest` completes and
produces a sanitized rehearsal; it did not exclude the public default path.

Green tests are evidence from sampled executions. They do not erase a concrete
counterexample visible in the diff, and an optional CLI argument does not remove
its default behavior from an unqualified public-command scenario.

## User Stories *(mandatory)*

### User Story 1 - A concrete scenario counterexample is blocking (Priority: P1)

As the operator, I want a judge that discovers a definite counterexample to a
dispatched scenario to fail that scenario, even when the deterministic suite is
green and the committed tests did not sample the faulty branch.

**Independent Test**: Assemble the real judge prompt around a small synthetic
diff with a green gate, an explicit-option test and a visibly crashing default
branch. Inspect the fixed system contract and run the strict verdict parser
against representative responses to prove the scenario remains the unit of the
decision.

**Acceptance Scenarios**:

1. **Given** an unqualified scenario that a public command completes, and a
   diff where its omitted optional argument deterministically crashes, **When**
   the judge evaluates the scenario beside a green test gate, **Then** its fixed
   instructions classify the default invocation as in scope and require that
   scenario to fail; lack of a regression test cannot make the counterexample
   non-blocking.
2. **Given** a scenario using universal safety language such as “sanitized,”
   “never,” “every,” or “unchanged,” **When** one externally controlled persisted
   field visibly violates that claim, **Then** the judge must trace the claim
   across the relevant branches and fields and fail the closest dispatched
   scenario rather than placing the defect only in PASS feedback.
3. **Given** a defect visible in the diff that does not contradict any dispatched
   requirement or scenario, **When** the judge reports it, **Then** the existing
   criteria boundary remains: it may be advisory feedback and does not invent a
   new acceptance criterion.
4. **Given** the tightened instructions, **When** existing verdicts are parsed
   and gate contradictions are reconciled, **Then** the strict JSON schema,
   per-scenario cross-check, retry bounds, model-independent routing and
   deterministic gate authority remain unchanged.

## Functional Requirements *(mandatory)*

- **FR-001**: The judge contract MUST state that committed tests are sampled
  evidence and do not define or narrow a scenario's behavioral scope.
- **FR-002**: An unqualified public API or CLI scenario MUST include its reachable
  default and omitted-option paths unless the criterion explicitly narrows them.
- **FR-003**: A concrete counterexample that contradicts a dispatched scenario
  MUST make that scenario fail; the judge MUST NOT return PASS while relegating
  the same counterexample to feedback.
- **FR-004**: Universal safety claims MUST be evaluated across the relevant
  externally controlled fields and reachable branches visible in the evidence.
- **FR-005**: The change MUST preserve the existing prohibition on inventing
  requirements for defects unrelated to every dispatched criterion.
- **FR-006**: The JSON verdict grammar, per-scenario IDs, parser strictness,
  gate-result evidence, diff bounds and persona/model registry MUST remain
  unchanged.
- **FR-007**: The instruction MUST be vendor-neutral and MUST NOT name Kimi,
  GLM, this incident's repository paths or any current model alias.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007]
```

## Assumptions

- Prompt semantics reduce recurrence but cannot prove that a probabilistic model
  will find every defect. Deterministic regressions for the two 158/US4 bugs
  belong to spec 170.
