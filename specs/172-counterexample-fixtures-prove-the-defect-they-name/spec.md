---
state: ready
depends_on_landed:
  - 170-the-historical-ingest-default-is-a-real-path
---

# Feature Specification: counterexample fixtures prove the defect they name

## Why this repair exists

Spec 171 correctly tightened the fixed judge contract, but its passing candidate
did not prove the two counterexamples used to test that contract.  In PR 509's
effective candidate (`192fd7891e9316dddc369ff7d730c080e8b80cd6`), the supposed
omitted-option crash defaults the option to `"explicit"`, so omission never
enters the `option is None` branch.  Its supposed unsanitized sibling assigns
`record.slug = record.name` after `record.name` was sanitized, so both persisted
fields are sanitized.  The tests assert suggestive strings rather than execute
the examples.

The judge then described those two nonexistent defects as proven and returned
PASS.  PR 509 is parked, unmerged and unarmed.  This repair preserves the valid
vendor-neutral prompt and contract work while making the evidence fixtures
executable contradictions instead of labels a judge can repeat.

## User Stories *(mandatory)*

### User Story 1 - Counterexample evidence survives a negative control (Priority: P1)

As the operator, I want every synthetic counterexample used to bind the judge to
be executable, so a green string-presence test cannot call safe fixture code a
crash or a sanitization bypass.

**Independent Test**: Integrate the effective three-file PR 509 candidate without
its empty salvage marker.  Execute its two existing fixture snippets as negative
controls and record the specific red results: an omitted completion sees
`"explicit"` without entering a crashing branch, and the persisted name and slug
are both sanitized.  Replace the fixtures with diffs generated from executable
before/after source.  Prove that the explicit completion succeeds while the
omitted invocation raises, and that a sanitized name is persisted beside a raw
externally controlled sibling.  Assemble those exact generated diffs through
the real `build_prompt` boundary beside the green gate and scenarios.

**Acceptance Scenarios**:

1. **Given** the parked PR 509 candidate, **When** its omitted-option fixture is
   executed as written, **Then** a regression test first proves that the claimed
   crash is absent before the fixture is repaired.
2. **Given** an executable public completion function with an optional argument,
   **When** its repaired after-source is called explicitly and with the argument
   omitted, **Then** the explicit call completes and the omitted call raises the
   visible exception carried by the generated diff.
3. **Given** an executable persistence example with two externally controlled
   sibling fields, **When** its repaired after-source is run, **Then** the nested
   name is sanitized while the raw sibling is observably persisted unchanged,
   making the universal-safety contradiction real.
4. **Given** the repaired executable sources, **When** the real judge prompt is
   assembled, **Then** its user message contains the exact source-derived diffs,
   dispatched scenarios and green gate while its fixed system message retains
   the default-path, universal-claim and advisory-boundary instructions.
5. **Given** the complete repair, **When** focused and full gates run, **Then** the
   strict JSON parser, scenario IDs, diff bounds, gate contradiction authority,
   retry budgets, registry and route selection remain unchanged.

## Functional Requirements *(mandatory)*

- **FR-001**: The effective prompt, contract and focused-test payload from PR 509
  MUST be integrated from commits `a154f1b46e1faeb9fff6d31254f6d1feb992e1f3`
  through `192fd7891e9316dddc369ff7d730c080e8b80cd6`; the empty salvage commit
  `3e9e2ea3c5c1ca213a061f99b2a95e8e6dff34db` MUST NOT be used as authored work.
- **FR-002**: Before repair, tests MUST execute the parked completion fixture and
  prove that omission selects `"explicit"` and does not reach its alleged
  omitted-option failure.
- **FR-003**: The repaired completion diff MUST be derived from executable source;
  an explicit-option call MUST complete and an omitted-option call MUST raise the
  same visible exception shown in the diff.
- **FR-004**: Before repair, tests MUST execute the parked universal-safety fixture
  and prove that both the name and sibling field are persisted sanitized.
- **FR-005**: The repaired universal-safety diff MUST be derived from executable
  source and MUST persist at least one raw externally controlled sibling field
  beside a separately sanitized field.
- **FR-006**: The exact source-derived counterexample diffs, criteria and sampled
  green gate MUST pass through the production `build_prompt` boundary; tests MUST
  assert semantic execution results as well as prompt presence and ordering.
- **FR-007**: The vendor-neutral prompt clauses and synchronized judge contract
  from PR 509 MUST be preserved, including the corrected 64 KiB documentation.
- **FR-008**: Production changes MUST remain confined to the fixed judge prompt;
  verdict parsing, schemas, diff preparation, gate authority, retries, registry,
  routing, credentials and doctor behavior MUST remain unchanged.
- **FR-009**: The change MUST NOT add a dependency, network call, live model
  call, PR 509 mutation or incident-specific vendor/model wording.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, FR-008, FR-009]
```

## Assumptions

- The production behavior being repaired is the judge's fixed instruction.  The
  executable fixtures are deterministic evidence that those instructions are
  tested against real contradictions; they do not attempt to make an LLM
  deterministic or add a second verdict engine.
- PR 509 remains parked as provenance.  Landing this repair does not authorize
  closing, editing or rearming it.
