---
state: draft
---

# Feature Specification: A clean synthetic trio for spec validate goldens

This directory is a **fixture**, not a spec the factory dispatches. It lives
under `tests/fixtures/` so the golden captures taken over it can never drift
with a corpus refinement (plan trap 12): nothing here is read by anything
except `tests/test_133_us1_typed_report_and_golden_captures.py`.

Authored to validate **clean**: every layer runs, none refuses, none advises.
Its one skipped layer is `anchor_resolution` — the `path:NN` citation below
names a file the shared fixture target repository does not carry, which makes
`_check_anchor_resolution` skip with "none of the cited paths exist under
target repository …" while `_check_symbol_anchors` still runs (plan trap 13).
Its one information note rides an `ERGANE-TODO` sentinel, which needs no store
and embeds no absolute path.

## Requirements *(mandatory)*

- **FR-001**: The fixture MUST stay exactly as captured.

### User Story 1 - The fixture is stable (Priority: P1)

As the golden test, I want this trio byte-stable, so the captures taken over
it stay meaningful.

**Acceptance Scenarios**:

1. **Given** the fixture as committed, **When** `spec validate` runs over it,
   **Then** every layer reports and nothing refuses. Editing any document here
   is editing the goldens; change the trio and re-capture together, or leave
   both alone. See `tests/golden/spec_validate/README.md`. The sentence that
   names the anchored file is
   `factory/cli/nouns/spec.py:1` and is deliberately stale — the shared target
   repository carries no such file, and that is the skip the capture freezes.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001]
```