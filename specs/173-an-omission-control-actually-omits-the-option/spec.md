---
state: landed
# Attested landed 2026-09-11. US1 94406402cb33 (#514) on attempt 1 — observed
# on ergane-buildout by content. The node itself is recorded KILLED: PR 514's
# first merge-group run was cancelled at 11:32:58Z and not requeued until
# 12:34:28Z, and that 62-minute gap exhausted the 7200s stall window at
# 12:36:15Z with failing_checks=[]. The requeued run then passed and the forge
# merged the PR at 13:03:28Z, 27 minutes after the kill. The store's verdict
# and the branch disagree, and the branch is the fact. Occurrence 3 of the
# landing finding a-cancelled-required-check-is-not-a-failing-check-...-and-dies.
depends_on_landed:
  - 170-the-historical-ingest-default-is-a-real-path
fixes:
  - verification/omission-negative-control-invokes-explicit-none
---

# Feature Specification: an omission control actually omits the option

**Created**: 2026-09-11

## Why this repair exists

Spec 172 repaired two false counterexample fixtures, but its first committed
negative control repeated the evidence mistake in a subtler form.  The test
named an omitted call while invoking `complete("target", option=None)`.  The
parked fixture treats those calls differently: real omission supplies the
default value `"explicit"`, while explicit `None` enters the branch that rewrites
the value to `"omitted"`.  A lambda that ignores that value hid the substitution.

Detached execution of the exact candidate proved the distinction.  A call with
no keyword completed and the callee observed `"explicit"`; the committed test
instead supplied `None`.  The repaired completion source, repaired universal
safety source and prompt assembly otherwise passed their semantic controls and
148 related tests.  PR 512 therefore remains open and unarmed.  This successor
integrates its authored work, excludes its salvage marker, and repairs only the
negative-control evidence seam.

## User Scenarios & Testing

### User Story 1 - Omission and explicit null are different observations (Priority: P1)

As a verifier, I can see that a counterexample described as an omitted argument
actually executes a call with no argument, and that the captured value proves
which path ran.

**Independent Test**: Execute the parked completion fixture twice through a
recording `crash_when_omitted`: once as `complete("target")`, and once as
`complete("target", option=None)`.  No model, proxy or live service is needed.

**Acceptance Scenarios**:

1. **Given** the parked completion fixture whose default is `"explicit"`,
   **When** the committed negative control calls `complete("target")` with no
   option keyword, **Then** it completes without a crash and the recorder proves
   the callee saw exactly `"explicit"` — not `None` or `"omitted"`.
2. **Given** the same fixture and a recorder that raises only when it sees
   `"omitted"`, **When** a separate control calls with explicit `option=None`,
   **Then** that call raises and the ordered capture is
   `("explicit", "omitted")`, proving the two call shapes cannot be substituted.
3. **Given** the repaired executable before/after sources from PR 512, **When**
   their generated diffs are assembled through the production prompt, **Then**
   explicit completion succeeds, true omission raises the visible exception,
   the raw sibling still bypasses sanitization, and both exact diffs reach the
   user message after criteria and sampled gate evidence.
4. **Given** the authored PR 512 candidate through `3eab623`, **When** this repair
   is assembled, **Then** those commits are integrated in order, salvage
   `376ea73` is excluded, the fixed system-message and 64 KiB contract remain
   unchanged, and no parser, schema, retry, model, route or credential code moves.
5. **Given** the corrected negative control, **When** focused and full gates run,
   **Then** compact committed evidence records the old explicit-`None` call, the
   true omitted observation, the distinct explicit-`None` failure and the green
   repaired-source checks before normal judge and native merge-queue handling.

## Functional Requirements

- **FR-001**: The repair MUST integrate authored commits `8b80967` through
  `3eab623` in order and MUST exclude salvage `376ea73`.
- **FR-002**: The committed parked-fixture negative control MUST invoke
  `complete("target")` without an option keyword and MUST capture the exact value
  received by `crash_when_omitted`.
- **FR-003**: A separate explicit-`None` invocation MUST prove that it reaches
  `"omitted"` and raises, so the test cannot conflate explicit null with omission.
- **FR-004**: The repaired completion and universal-safety after-sources MUST
  remain executable, and the prompt diffs MUST be generated from those same
  sources rather than copied separately.
- **FR-005**: Production prompt wording, structured verdict parsing, advisory
  boundaries and the actual 64 KiB input contract MUST remain as in PR 512.
- **FR-006**: Committed evidence MUST contain the concrete before/after call
  results and the focused green result, labelled as synthetic execution.
- **FR-007**: The change MUST NOT add a dependency or alter retry, registry,
  routing, credential, doctor, workflow or live-service behavior.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007]
```

PR 512 remains provenance only.  Readying this spec does not authorize changing,
closing or rearming that PR.
