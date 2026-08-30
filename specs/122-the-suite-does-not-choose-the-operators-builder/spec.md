---
state: landed
fixes:
# Attested landed 2026-08-29. US1 2cedd3429e22, US2 9df94e33c4b2,
# US3 62cc8207e3db -- three stories, one round, ALL THREE FIRST ATTEMPT,
# dispatched 22:13, landed 22:40 / 22:49 / 23:12 -- 59 minutes for three.
#
# THE DEMONSTRATION, RUN AND RECORDED, because the gate could not prove this
# spec worked -- proving it required a registry change the spec deliberately
# does not make. Same four files, same swap of `implementer` to
# `agent: subscription / model: claude-opus-5`:
#
#   2026-08-29 20:56, before this spec:   28 failed, 35 passed
#   2026-08-29 23:24, after it landed:    65 passed
#
# That pair is the evidence and either half alone proves nothing: a suite
# already green proves no fix, and one green only afterwards proves no
# regression was avoided. The operator's builder was switched to
# opus-closer immediately after, which is what the spec existed for.
  - ci/test-suite-pins-the-operator-dial
  - ci/landed-tests-read-the-operators-real-ledger-and-are-green-only-where-it-is-absent
# DRAFTED 2026-08-29 by the operator session, against ergane-buildout at c94b547,
# after measuring the swap rather than reasoning about it.
#
# THE OPERATOR ASKED FOR ONE THING AND THE SUITE REFUSED IT. The instruction was
# "the implementer should default to the opus-closer persona". Applied to
# `personas.yaml` and run: **25 tests fail**, from exactly two pins.
#
#   tests/test_us2_shipped_registry.py:344   assert "/" in registry["implementer"].model
#   tests/test_usage_activities.py:74        PERSONA = "implementer"
#
# A subscription persona's model is `claude-opus-5` — no slash — and it mints no
# virtual key, so a fixture that leases one for `implementer` fails. Neither pin
# is about the code under test. Both encode a guess about which vendor the
# operator will choose.
#
# THE FIRST PIN CARRIES ITS OWN INDICTMENT, THREE LINES ABOVE ITSELF:
#
#     # The repo's real wiring still resolves. Assert that it LOADS, not which
#     # vendor it names: pinning the alias here makes the operator's own dial
#     # untouchable, which is `ci/test-suite-pins-the-operator-dial` — the same
#     # defect 037 un-pinned for `context_window`, recurring on `model` when the
#     # implementer was pointed at Opus 5 on 2026-08-19.
#     assert registry["implementer"].model
#     assert "/" in registry["implementer"].model
#
# The comment states the rule correctly, names the finding, cites the prior
# recurrence — and the next line breaks it. A previous fix un-pinned
# `context_window` and re-pinned `model` in the same breath. That is why this
# spec does not un-pin a third field: it asserts against the assertions
# themselves (US1-S4), so the seventh recurrence fails a test instead of
# surprising an operator.
#
# WHY THE COST IS OUT OF PROPORTION. This repository's gate is
# `test: "uv run pytest -q"` (`ergane.yaml`). A red suite is a red GATE, so a
# pinned dial does not merely block a push — it fails every node of every epic
# until the dial is put back. The operator spent 2026-08-29 hand-editing each
# compiled work graph to route around it, because the registry could not say
# what he wanted it to say.
#
# THE SECOND FINDING IS THE SAME DISEASE ON A DIFFERENT ORGAN. Three tests 089
# landed on 2026-08-29 validate a placeholder finding key against the operator's
# REAL ledger at `.factory/doctor.db`. They pass in a node's worktree only
# because that store is absent there, taking the fixes layer's
# "store absent, not checked" path. Green in the boundary, red on the operator's
# host — the inverse of the usual direction, which is why nothing caught it at
# landing. 089's own plan named this as trap 7: "fixtures are supplied trees,
# never `.factory/`."
#
# NOT IN SCOPE. This spec changes no production code, no persona registry, no
# manifest, and does not decide which model the implementer should be. It makes
# the suite stop having an opinion about that.
---

# Feature Specification: the suite does not choose the operator's builder

**Created**: 2026-08-29
**Depends on**: nothing outside this spec.

## The gap, stated precisely

Two test-local constants decide which vendor the operator's builder may be:

1. **An assertion about the shape of a model alias.** `"/" in ...model` is true
   of every gateway alias and false of every subscription one, so it is a
   vendor-routing decision written as a format check.
2. **A fixture persona name.** `PERSONA = "implementer"` makes thirteen usage
   tests lease a virtual key for whatever the operator's builder is — which only
   works while that builder routes through the gateway.

Neither is about the behaviour under test. Both fail the moment the operator
picks a subscription-routed builder, and because the gate is the suite, that
failure reaches every node rather than only a push.

Separately, three tests validate a fixture's finding key against the operator's
real ledger, and are green only on machines where that ledger does not exist.

## The rule this spec is asking for

**A test may assert that the operator's wiring resolves. It may not assert what
the operator chose, and it may not read the operator's own stores.**

### What this spec is not

It is not a change to `personas.yaml`. Which model the implementer names stays
the operator's decision, made after this lands.

It is not a change to any production module. Every edit is under `tests/`.

It is not a fix to the fixes layer. Its absent-store path is correct and is what
made the 089 tests pass in the boundary; the fixtures are what is wrong.

## User Scenarios & Testing

### User Story 1 - The registry test asserts loading, not vendor (Priority: P1)

As an operator, I can point the implementer at any persona the registry defines
without a test failing.

**Why this priority**: P1 and it depends on nothing. It is the assertion that
directly refuses the operator's instruction.

**Acceptance Scenarios**:

1. **Given** a registry whose implementer routes through the gateway, **When**
   the suite runs, **Then** it passes — proven by a committed test. The status
   quo must keep working.
2. **Given** a registry whose implementer is a subscription persona with no
   slash in its model, **When** the suite runs, **Then** it passes — proven by a
   committed test. This is the case that fails today.
3. **Given** a registry entry with an empty model, **When** the suite runs,
   **Then** it fails — proven by a committed test. The check that the wiring
   *resolves* is real and is kept.
4. **Given** the assertions this suite makes about the shipped registry, **When**
   they are read, **Then** none of them constrains which vendor or route a
   persona names — proven by a committed test that inspects the assertions
   themselves. Six recurrences were each fixed by removing one literal; this is
   the guard that makes a seventh fail here.

### User Story 2 - A fixture that needs a gateway persona names one (Priority: P1)

As an operator, the usage tests exercise key leasing without depending on which
persona I made the default builder.

**Why this priority**: P1 and independent of US1 — a different file, a different
mechanism. It is the larger half of the breakage: thirteen tests turn on one
module-level constant.

**Acceptance Scenarios**:

1. **Given** the usage tests, **When** they lease a virtual key, **Then** the
   persona they name is one they choose for themselves and not the operator's
   default builder — proven by a committed test.
2. **Given** an implementer that routes through the gateway, **When** the usage
   tests run, **Then** they pass exactly as today — proven by a committed test.
3. **Given** an implementer that is a subscription persona, **When** the usage
   tests run, **Then** they still pass — proven by a committed test. They are
   about key leasing, not about who the builder is.
4. **Given** a persona that genuinely mints no key, **When** a lease is
   attempted, **Then** the refusal is still asserted somewhere in the suite —
   proven by a committed test. Decoupling from the operator's dial must not
   delete the coverage that a subscription persona has no key.

### User Story 3 - A test that reads a findings store builds its own (Priority: P1)

As an operator, running the suite on a machine that has a real findings ledger
gives the same result as running it where none exists.

**Why this priority**: P1 and independent. It is a different failure with the
same cause, and it is currently red on the operator's host.

**Acceptance Scenarios**:

1. **Given** a host with a populated `.factory/doctor.db`, **When** the 089
   fixes-layer tests run, **Then** they pass — proven by a committed test. They
   fail there today.
2. **Given** a host with no findings store at all, **When** the same tests run,
   **Then** they pass — proven by a committed test. Both directions, because
   passing only in the boundary is exactly the defect.
3. **Given** those tests, **When** they resolve a store path, **Then** it is
   under the test's own temporary directory — proven by a committed test that
   asserts no test in the file names the operator's runtime root.
4. **Given** the fixes layer's absent-store path, **When** it is exercised,
   **Then** it still reports `not checked` rather than refusing — proven by a
   committed test. That behaviour is correct and this story must not change it.

## Work Graph

```yaml
US1:
  implements: []
  depends_on: []
US2:
  implements: []
  depends_on: []
US3:
  implements: []
  depends_on: []
```

Three independent stories in three different files —
`tests/test_us2_shipped_registry.py`, `tests/test_usage_activities.py`, and the
two `tests/test_089_*.py`. No merge edges, so all three dispatch in one round.

## Requirements

- **FR-001**: The suite MUST NOT assert that the implementer's model has any
  particular shape, vendor or route.
- **FR-002**: The suite MUST still fail when a shipped registry entry does not
  resolve.
- **FR-003**: Fixtures needing a gateway-routed persona MUST name one
  explicitly rather than borrowing the operator's default builder.
- **FR-004**: The usage tests MUST pass with the implementer on either route.
- **FR-005**: Coverage that a subscription persona mints no virtual key MUST
  survive.
- **FR-006**: Tests that read a findings store MUST build it under their own
  temporary directory.
- **FR-007**: The fixes layer's absent-store behaviour MUST be unchanged.
- **FR-008**: The suite MUST contain a check that fails if a future assertion
  constrains which vendor or route a persona names.

## Success Criteria (summary)

- An operator can set `implementer` to `opus-closer` in `personas.yaml`, run the
  suite, and see it green.
- The suite gives the same verdict on a host with a real findings ledger and one
  without.
- The seventh recurrence of this defect class fails a test rather than blocking
  an operator instruction.
