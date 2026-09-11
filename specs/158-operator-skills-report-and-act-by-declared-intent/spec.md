---
state: landed
# Attested landed 2026-09-11. US1 1cee726baa44, US2 e4fba1927753,
# US3 4083f3476f71, and US4 6c953da2d2f1 (#520) were observed on
# ergane-buildout. The US4 continuation workflow recorded MERGED and COMPLETED;
# an independent clean-tree qualification passed all 21 focused tests, both
# concrete boundary probes, and left the operational findings store unchanged.
depends_on_landed:
  - 087-the-operators-skills-arrive-with-the-cli
  - 157-one-operator-contract-serves-both-clients
---

# Feature Specification: operator skills report and act by declared intent

## Provenance and boundary

This spec is work package B plus the historical-ingestion half of work package F
from the 2026-09-09 Codex-primary audit. It repairs the behavior of the canonical
operator skills after spec 087 packages them. Packaging, destination ownership,
and uninstall behavior remain 087's. Scheduling and away authority remain 162's.

The central rule is that a reporting request observes. Fetching, merging,
dispatching, attesting, answering, applying findings, and publishing are separate
actions that occur only when the operator declares that intent.

### User Story 1 - Floor and escalation reports are pure observations (Priority: P1)

As an operator asking what is happening, I receive current, provenance-bearing
facts without changing the floor I am observing.

**Acceptance Scenarios**:

1. **Given** status fixtures containing gateway and subscription routes, promotion rungs, two dispatches of one spec, and unavailable live services, **When** `floor-status` renders them, **Then** it reports the recorded runner, effective route, model, dispatch identity, evidence source, and unavailable facts without consulting today's registry to rewrite history — proven by committed fixture tests.
2. **Given** a status-only invocation, **When** the skill and helper surface are inspected and executed against fakes, **Then** they perform no fetch, merge, push, dispatch, attestation, answer, findings write, or service mutation — proven by denied mutation fakes and a static command sweep.
3. **Given** an open escalation with a choice set and current recovery evidence, **When** `escalation-triage` prepares its brief, **Then** it reads the choices actually offered, distinguishes observation from a proposed answer, and never presses a choice or assumes a fixed button set — proven by committed tests.

**Why this priority**: A read that can land code is not a safe daily operator surface.

**Independent Test**: Run both skills over frozen fixtures with every mutating seam configured to raise; rendering must still succeed.

### User Story 2 - Build metrics preserve identity and unknown quantities (Priority: P1)

As an operator comparing runners, I receive measurements that do not merge
distinct dispatches or turn absent subscription evidence into zero.

**Acceptance Scenarios**:

1. **Given** two dispatches sharing epic, node, and attempt ordinals but carrying distinct dispatch identities, **When** metrics are computed, **Then** the rows remain separate and can be grouped by recorded runner, route, and model without losing either execution — proven by committed database fixtures.
2. **Given** an empty ledger, legacy rows missing newer dimensions, and subscription rows with unknown tokens or dollars, **When** reports are rendered, **Then** no division-by-zero occurs and every missing dimension remains explicitly unknown rather than zero or inferred — proven by parameterized tests.
3. **Given** LOC measurement is requested, **When** the helper resolves its tool, **Then** it uses a declared stable local executable or reports the capability unavailable, creates run-unique scratch outputs, and never downloads executable code from a mutable remote branch — proven by a network-denied test and source sweep.

**Why this priority**: These measurements decide whether a later Codex-primary pilot is credible.

**Independent Test**: Build a temporary ledger with the counterexamples and execute the helper without network access.

### User Story 3 - A rendered spec carries the validator's actual verdict (Priority: P1)

As a refiner, I see the same validation truth in HTML that the CLI and library
produce, including refusal, advisory, skipped, and unavailable states.

**Acceptance Scenarios**:

1. **Given** a trio with one refusal, one advisory, and one skipped validation layer, **When** `spec-html` renders it, **Then** the page consumes `factory.spec.validate_spec` and preserves all three classifications and reasons rather than reimplementing them — proven by a shared-report fixture test.
2. **Given** landing lookup is unavailable or fails, **When** the page is rendered, **Then** the landing section says unavailable or error with the original safe detail and never substitutes an empty mapping that resembles no landed stories — proven by committed failure-path tests.
3. **Given** no publication was requested, **When** rendering completes, **Then** it writes only to a caller-selected local output or unique scratch path and returns that path; remote publication is a separate explicit action — proven by filesystem-difference tests.

**Why this priority**: A polished page that weakens the validator is a more persuasive wrong answer.

**Independent Test**: Construct the validation report in memory, deny git/network access, and compare every rendered state to the library object.

### User Story 4 - Historical findings remain historical (Priority: P1)

As an operator ingesting an old report, I can preserve its observation identity
and time without manufacturing a new recurrence today.

**Acceptance Scenarios**:

1. **Given** a historical finding with source identity and observation time, **When** it is parsed and rehearsed, **Then** the proposed event retains those fields and is distinguishable from a current live observation — proven by model, parser, and round-trip tests.
2. **Given** the same historical observation is ingested twice, **When** application is explicitly authorized, **Then** it records at most one event and does not advance recurrence or `last_seen` to ingestion time — proven by a temporary-store test.
3. **Given** historical prose says a defect was fixed or a current ledger row remains open, **When** ingestion runs, **Then** neither fact resolves the other automatically; resolution requires current implementation evidence and a separate authorized act — proven by transition tests.
4. **Given** analysis was requested without application, **When** `findings-ingest` completes, **Then** it produces a sanitized rehearsal and leaves the operational ledger unchanged — proven by before/after database hashes.

**Why this priority**: Recurrence is a governance input; manufactured sightings corrupt constitutional promotion decisions.

**Independent Test**: Use a temporary doctor store and a fixed clock to prove historical time, idempotency, and analysis-only purity.

## Functional Requirements

- **FR-001**: Reporting helpers MUST consume read-only CLI or library surfaces and MUST make no implicit fetch, merge, dispatch, attestation, answer, findings, publication, or service action.
- **FR-002**: Floor status MUST use recorded runner, route, model, dispatch, and snapshot provenance; it MUST NOT derive historical routing from today's registry or the retired `agent == "subscription"` sentinel.
- **FR-003**: Escalation triage MUST read the offered choices and MUST NOT answer on the operator's behalf.
- **FR-004**: Build metrics MUST preserve dispatch identity and MUST render missing historical dimensions and unmeasured quantities as unknown.
- **FR-005**: Metrics over an empty input MUST produce a valid empty report without division by zero.
- **FR-006**: LOC measurement MUST use a declared stable local dependency boundary or report unavailable; it MUST NOT download executable code.
- **FR-007**: Spec HTML MUST consume `factory.spec.validate_spec` and preserve every finding severity and skipped-layer reason.
- **FR-008**: Landing-read errors MUST remain visible and MUST NOT become an empty landed mapping.
- **FR-009**: Local rendering MUST be the default; publication MUST require separately declared intent.
- **FR-010**: Historical finding events MUST carry stable observation identity and time distinct from ingestion time.
- **FR-011**: Re-ingesting one historical observation MUST be idempotent and MUST NOT manufacture recurrence.
- **FR-012**: Historical claims MUST NOT resolve a current finding without current evidence and an explicit resolution action.
- **FR-013**: Analysis-only findings ingestion MUST not open the operational store for writing.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003]
US2:
  depends_on: []
  implements: [FR-004, FR-005, FR-006]
US3:
  depends_on: []
  implements: [FR-007, FR-008, FR-009]
US4:
  depends_on: []
  implements: [FR-010, FR-011, FR-012, FR-013]
```
