# Feature Specification: Scenario Item Without Keyword Steps

**Feature Branch**: `015-scenario-without-keywords`

**Created**: 2026-08-04

**Status**: Draft

**Input**: Invalid fixture. The second acceptance scenario of User Story 1 carries no
bold **Given**/**When**/**Then**/**And** steps — it is bold-formatted prose, so a
parser that merely looks for "some bold text" accepts it wrongly. The parser must
reject the file and name `US1-S2`. Items 1 and 3 are well-formed, so item 2 is the
only defect.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Story with one keyword-less scenario (Priority: P1)

As the corpus, I carry a scenario list whose second item states no Given/When/Then
steps.

**Why this priority**: A scenario with no steps gives the judge nothing to score per
FR-003's strict per-scenario criterion.

**Independent Test**: Parse the file and assert the error names US1-S2.

**Acceptance Scenarios**:

1. **Given** a well-formed scenario item, **When** it is parsed, **Then** its bold steps are captured in order.
2. **Note**: the system does the right thing when asked, which is not something a judge can score.
3. **Given** a keyword-less item anywhere in the list, **When** the list is parsed, **Then** the whole file is rejected.

---

### Edge Cases

- What happens when a scenario is written as prose? (Rejected, naming the scenario id.)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The parser MUST reject an acceptance-scenario item carrying no bold keyword steps, naming its scenario id.
