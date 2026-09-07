---
state: draft
---

# Feature Specification: A deliberately defective synthetic trio for spec validate goldens

This directory is a **fixture**, not a spec the factory dispatches. It lives
under `tests/fixtures/` so the golden captures taken over it can never drift
with a corpus refinement (plan trap 12).

Authored to carry exactly one **refusal** and one **advisory**, both printed to
stderr (plan trap 19):

- **The refusal is an evidence refusal** (102-US1): the Then-clause below
  asserts a runtime outcome — "renders correctly in the browser" — that no
  gate the shared target repository's manifest declares can produce, and the
  scenario names no diff-carried evidence. US6-S4 takes the exact string to
  compare the moved checker against from this trio's stderr golden.
- **The advisory is a scenario-coverage advisory**: US1-S1 is declared below
  and its `tasks.md` never names it, which `_check_scenario_coverage` grades
  `advisory` at `factory/cli/nouns/spec.py:1414`.

A run carrying a refusal never prints the all-pass sentence (plan trap 3) —
that is the shape this trio exists to freeze alongside the clean one.

## Requirements *(mandatory)*

- **FR-001**: The system MUST draw the page.

### User Story 1 - The page is drawn (Priority: P1)

As an operator, I want the page drawn.

**Acceptance Scenarios**:

1. **Given** a built page, **When** the operator opens it, **Then** the page
   renders correctly in the browser.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001]
```