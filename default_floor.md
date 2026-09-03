# Default floor

The principles below are a starting point. They are yours to keep, edit, or remove. Ergane seeds them only because a repository that has thought about its own standards gets better work than one that has not.

## Acceptance criteria must be provable from the diff

**Why this is here:** the judge is handed only the story's diff and the criteria snapshot. A criterion that names a CI observation, a running system, or a commit message describes evidence the judge cannot see, so correct work will fail and no number of attempts can change that.

**What removing this costs:** if a criterion cannot be checked from the diff alone, the factory will spend attempts failing it.

## Work arrives as vertical slices with tests first

**Why this is here:** the factory dispatches one story at a time and the gates run tests against what comes back. A story that is not a testable slice is not a thing this factory can land.

**What removing this costs:** work that is not shaped as a slice with tests will pass no gate the factory runs.

---

# Project principles

Add what this repository believes about how its agents should work. This section is intentionally empty when seeded.

---

# Governance

This document belongs to the repository. Edit it directly. Ergane will not rewrite it once it exists, and will not re-impose a principle you have removed.

When a default floor is updated in a future Ergane release, repositories seeded from an older floor are only informed; being behind is not a defect, because the document is yours.
