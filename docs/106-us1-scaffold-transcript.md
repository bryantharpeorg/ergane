# 106-US1 — scaffold generator transcript (US1-S1, US1-S2, US1-S3)

All output below was produced in-process with `factory.cli.main.main` and the
new `factory.doctor.scaffold.scaffold_spec` entry point.  The generator is pure
text in, text out; the directory write and the validator call are the test's
responsibility, exactly as US1's seam requires.

## T001 red: the old `_build_tasks_md`-shape lacks per-story phase headings

A `tasks.md` built from the legacy `_build_tasks_md` shape — `## Implementation`
and `## Verification` with no `## Phase N: User Story N — ...` headings — fails the
real validator with both a scenario-coverage advisory and three prompt-assembly
refusals:

```json
{
  "spec_dir": "/tmp/us1-red-a9mciqzm/demo-feature",
  "checked": [
    "frontmatter",
    "workgraph_derivation",
    "persona_registry",
    "scenario_coverage",
    "prompt_assembly",
    "slice_coverage",
    "slice_contention"
  ],
  "skipped": [],
  "findings": [
    {
      "layer": "scenario_coverage",
      "message": "acceptance scenarios with no task reference: US1-S1, US2-S1, US3-S1",
      "severity": "advisory"
    },
    {
      "layer": "prompt_assembly",
      "message": "tasks.md: node 'us1': tasks.md declares no phase naming user story US1, so this node has no task slice to work (FR-006)",
      "severity": "refusal"
    },
    {
      "layer": "prompt_assembly",
      "message": "tasks.md: node 'us2': tasks.md declares no phase naming user story US2, so this node has no task slice to work (FR-006)",
      "severity": "refusal"
    },
    {
      "layer": "prompt_assembly",
      "message": "tasks.md: node 'us3': tasks.md declares no phase naming user story US3, so this node has no task slice to work (FR-006)",
      "severity": "refusal"
    }
  ],
  "information": [
    {
      "layer": "slice_coverage",
      "message": "task ids inside no story's slice and naming no story, so they reach no node: T001, T002 — expected in a setup or verification phase the operator works by hand, a defect anywhere else"
    }
  ]
}
```

Exit code: `1`.

## The generator's trio for `demo-feature`

```text
=== spec.md ===
---
state: draft
---

# Feature Specification: demo-feature

This spec was scaffolded by `ergane spec new`. Each user story below is a
teaching slot: one fully worked story to imitate, one partial slot with blanks
to complete, and one skeletal slot holding only structure.

### User Story 1 - A demonstrative feature (Priority: P1)

As a developer reading my first scaffold, I see a worked story slot for US1.

**Acceptance Scenarios**:

1. **Given** a slug, a title and an already-resolved `path:line` anchor,
   **When** the generator runs, **Then** it returns three texts — one fully
   worked story, one partial, one skeletal — whose story headings, literal
   Given/When/Then acceptance scenarios, Work Graph fence with an explicit
   `implements:` on every node, and `state: draft` frontmatter are all present,
   with an ERGANE-TODO sentinel on every mandatory blank and no sentinel inside
   a story heading, the Work Graph fence, or a task id — proven by committed
   tests that parse the returned text rather than diff a golden file.

**Why this priority**: Core teaching story

**Independent Test**: Verify the scaffold structure parses cleanly.

### User Story 2 - A demonstrative feature — partial (Priority: P2)

As a developer reading my first scaffold, I see a teaching story slot for US2.

**Acceptance Scenarios**:

1. **Given** the returned trio written to a directory, **When** the real
   `ergane spec validate` runs over it, **Then** it exits 0 with no refusal and
   no scenario-coverage advisory, every compiled node's task slice resolves,
   and the generated stories name no file in common with each other — proven by
   a committed transcript and committed tests.

**Why this priority**: Teaching slot

**Independent Test**: Verify the scaffold structure parses cleanly.

### User Story 3 - A demonstrative feature — skeletal (Priority: P3)

As a developer reading my first scaffold, I see a teaching story slot for US3.

**Acceptance Scenarios**:

1. **Given** the generator's demonstration mode, **When** it runs, **Then** it
   returns the worked story alone with no sentinel and no skeletal slot, so the
   result derives cleanly — proven by a committed test.

**Why this priority**: Teaching slot

**Independent Test**: Verify the scaffold structure parses cleanly.

## Functional Requirements

- **FR-001**: The system MUST satisfy the acceptance scenarios of User Story 1.
- **FR-002**: The system MUST satisfy the acceptance scenarios of User Story 2.
- **FR-003**: The system MUST satisfy the acceptance scenarios of User Story 3.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001]
US2:
  depends_on: []
  implements: [FR-002]
US3:
  depends_on: []
  implements: [FR-003]
```

=== plan.md ===
# Plan: demo-feature

A teaching plan: one worked story to imitate, one partial slot to complete, and
one skeletal slot to fill in.

## User Story 1 — A demonstrative feature

Worked story anchored at the resolved file:line given to the generator.

## User Story 2 — A demonstrative feature — partial

Partial slot: keep the tasks the generator wrote and add the rest.

## User Story 3 — A demonstrative feature — skeletal

Skeletal slot: replace each ERGANE-TODO with a real task.

=== tasks.md ===
# Tasks: demo-feature

## Phase 1: User Story 1 — A demonstrative feature

- [ ] [P] [US1-S1] Write the generator's failing tests around
      `factory/cli/main.py:171` — must fail.
- [ ] [US1] Implement the scaffold generator so the tests pass. Anchor with
      `factory/cli/main.py:171`.
- [ ] [US1] Paste the validator transcript and the demonstration mode output.

## Phase 2: User Story 2 — A demonstrative feature — partial

- [ ] [P] [US2-S1] Wire the `spec new` verb and numbering logic.
- [ ] [US2-S1] Pick a tracked anchor in the target repo and prove it resolves.
- [ ] ERGANE-TODO: add the next US2 task here.

## Phase 3: User Story 3 — A demonstrative feature — skeletal

- [ ] ERGANE-TODO: write US3-S1 task when the sentinel gate is added.
- [ ] ERGANE-TODO: write US3-S2 task for the derive refusal.
- [ ] ERGANE-TODO: write US3-S3 task for the missing assertion.

## Verification

- [ ] Final gate command passes green.
```

## `ergane spec validate --json` over the trio

```json
{
  "spec_dir": "/tmp/us1-green-do2fgcvn/demo-feature",
  "checked": [
    "frontmatter",
    "workgraph_derivation",
    "persona_registry",
    "scenario_coverage",
    "prompt_assembly",
    "slice_coverage",
    "slice_contention"
  ],
  "skipped": [],
  "findings": [],
  "information": []
}
```

Exit code: `0`.

## Demonstration mode: worked story alone, zero sentinels

```text
=== spec.md ===
---
state: draft
---

# Feature Specification: demo-feature

This is a throwaway demonstration spec. It carries one worked story, no
sentinels, and no skeletal slots so that `ergane spec derive` can compile it
cleanly.

### User Story 1 - A demonstrative feature (Priority: P1)

As a developer reading my first scaffold, I see a worked story slot for US1.

**Acceptance Scenarios**:

1. **Given** a slug, a title and an already-resolved `path:line` anchor,
   **When** the generator runs, **Then** it returns three texts — one fully
   worked story, one partial, one skeletal — whose story headings, literal
   Given/When/Then acceptance scenarios, Work Graph fence with an explicit
   `implements:` on every node, and `state: draft` frontmatter are all present,
   with an ERGANE-TODO sentinel on every mandatory blank and no sentinel inside
   a story heading, the Work Graph fence, or a task id — proven by committed
   tests that parse the returned text rather than diff a golden file.

**Why this priority**: Core teaching story

**Independent Test**: Verify the scaffold structure parses cleanly.

## Functional Requirements

- **FR-001**: The system MUST support the worked story `demo-feature`.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001]
```

=== plan.md ===
# Plan: demo-feature

A one-story throwaway plan for the install demonstration.

## User Story 1 — A demonstrative feature

The demonstration story; no contention, no sentinel.

=== tasks.md ===
# Tasks: demo-feature

## Phase 1: User Story 1 — A demonstrative feature

- [ ] [P] [US1-S1] Write the generator's failing tests around
      `factory/cli/main.py:171` — must fail.
- [ ] [US1] Implement the scaffold generator so the tests pass. Anchor with
      `factory/cli/main.py:171`.
- [ ] [US1] Paste the validator transcript and the demonstration mode output.
```

Sentinel count:

```text
$ grep -c "ERGANE-TODO" <(echo "$(cat spec.md plan.md tasks.md)")
0
```
