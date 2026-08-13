---
state: landed
# Attested landed 2026-08-13 12:15Z by the operator: US1 (the only story)
# observed at 60a6b22 (PR #48, first attempt, ~28 min dispatch to merged).
# The dial is SET: implementer.context_window: 262144 went into
# personas.yaml the moment this landed, full suite green with it.
# Flipped ready 2026-08-13 11:41Z on Bryan's word ("flip them") and
# dispatched immediately, two-wide with 036 (disjoint scopes: one test
# module vs roadmap code).
# specs_root: specs
# target_repo: /home/admin/code/ergane-roadmap-target
# Scaffolded by `ergane findings promote` from
# `ci/test-suite-pins-the-operator-dial` (critical, filed 2026-08-13 within
# the hour of the defect reddening trunk), then refined by the operator
# session the same night against the tree at 8bdb425. Bryan reviews and
# flips ready.
# POST-LANDING OPERATOR STEP: re-set `implementer.context_window: 262144` in
# personas.yaml — the dial is parked there with a comment naming this spec's
# finding, and every kimi attempt runs 200k-assumed until it is set.
---

# Feature Specification: The suite may hold the resolver to the registry, never the registry to a value

personas.yaml's own header calls its fields "the operator's dial — edit these
freely." On 2026-08-13 the operator set the documented `context_window` dial
and trunk went red:
`tests/test_agent_activities.py::test_context_window_is_resolved_onto_the_node_and_none_when_omitted`
asserts against `load_personas()` — the live shipped registry — that
`context_window is None`. A test that pins an operator dial makes the dial
unusable: gates run the full suite, so turning it reddens every epic's gate at
once. Two concurrent epics were killed over it the night it was found.

The invariant worth keeping is the resolver's, not the registry's: whatever
the registry declares rides verbatim onto the resolved node, and an *omitted*
declaration resolves to None. Both halves are provable on fixture registries;
neither needs an opinion about what the shipped file currently says.

### User Story 1 - Un-pin the dial (Priority: P1)

Rework the pinning test so the omitted-→-None case runs on a fixture registry
(`load_personas(path=…)` already accepts one — no production change), keep the
declared-window verbatim case, and add the guard that was missing: the module's
tests stay green when a copy of the shipped registry declares a window on any
persona.

**Why this priority**: the context-window dial (018/US4's whole point) is
parked until this lands, and every kimi attempt is running with 62,144 tokens
of its window unreachable — measured cost on every story the factory builds.

**Independent Test**: run the touched module twice — once against the shipped
registry, once against a copy with `implementer.context_window: 262144` — both
green, with the omitted-→-None and declared-→-verbatim invariants still
asserted.

**Acceptance Scenarios**:

1. **Given** the shipped personas.yaml exactly as committed, **When** the full
   suite runs, **Then** it is green (this diff breaks nothing).
2. **Given** a registry file identical to the shipped one except
   `implementer.context_window: 262144`, **When** the touched test module runs
   with the registry seam pointed at it, **Then** it is green — no assertion
   in the module demands a literal value of any dial in the live file.
3. **Given** a fixture registry whose personas omit `context_window`, **When**
   a graph resolves against it, **Then** every resolved node carries None —
   the omitted-→-None invariant survives, proven without the shipped file.
4. **Given** a Persona declaring a window, **When** a node resolves, **Then**
   the value rides verbatim (the existing declared-window case is kept, not
   weakened).

## Functional Requirements

- **FR-001**: The suite MUST remain green when the operator sets
  `context_window` on any persona in the shipped personas.yaml.
- **FR-002**: The omitted-declaration-resolves-to-None invariant MUST remain
  covered, via a fixture registry rather than the shipped file.
- **FR-003**: The declared-window-rides-verbatim invariant MUST remain covered.
- **FR-004**: The diff MUST be tests-only: nothing under `factory/` changes,
  and `personas.yaml` itself is not touched (re-setting the dial is the
  operator's post-landing step, deliberately outside this story).

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
```
