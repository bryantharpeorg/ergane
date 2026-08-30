---
state: landed
fixes:
# Attested landed 2026-08-30. US1 8b667afd018f, US2 2d9d256d4221 -- two stories,
# one round, both first attempt, dispatched 23:38 and complete by 00:33.
# 33 minutes from dispatch to both nodes ENQUEUED, the fastest epic of the run.
#
# THIS SPEC EXISTS BECAUSE 122 WAS SCOPED FROM A FOUR-FILE MEASUREMENT, and the
# lesson is worth more than the fix: a measurement used to scope a spec must cover
# the surface the spec claims to fix. 122's own success criterion was "set the
# implementer to opus-closer, run the suite, see it green" -- and no run of four
# predicted files could ever establish that. The prediction was right about all
# four and blind to the fifth, `tests/test_poll_usage.py:59`.
#
# NOTHING WAS LOST TO THAT, because the registry flip was held unpushed pending the
# full suite. This repository's gate IS `uv run pytest -q`, so a red suite is a red
# gate for every node -- which is exactly why the flip waits on a whole-suite run
# rather than a targeted one, both times.
  - ci/test-suite-pins-the-operator-dial
  - ci/landed-tests-read-the-operators-real-ledger-and-are-green-only-where-it-is-absent
# DRAFTED 2026-08-29 11:36 PM by the operator session, immediately after 122 landed and
# was found incomplete by the run that should have scoped it.
#
# 122 WAS SCOPED FROM A PARTIAL MEASUREMENT AND THIS IS THE REMAINDER. At 20:56 the
# implementer swap was measured against FOUR FILES chosen by predicting which would
# break. The prediction was right about all four and blind to a fifth. 122 was written,
# dispatched, landed and attested on that number. The full suite, run at 23:26 with the
# swap applied, reports 31 failures rather than 28, and the difference is:
#
#   tests/test_poll_usage.py:59      PERSONA = "implementer"
#
# Byte-identical to `tests/test_usage_activities.py:74`, which 122/US2 removed. Fifteen
# tests in that file lease a virtual key against whatever persona the operator has made
# the default builder, so all fifteen fail the moment that builder is subscription-routed
# and mints no key. This is the SEVENTH occurrence of
# `ci/test-suite-pins-the-operator-dial`.
#
# THE SECOND HALF IS THE SAME FAMILY 122/US3 FIXED THREE OF.
# `tests/test_spec_declares_its_fixes.py::test_validate_reports_the_same_result_with_and_without_fixes`
# fails with `assert 'fixes' in []` on the operator's host with the registry untouched --
# a fourth test whose verdict depends on whether a real findings store happens to exist.
#
# NOTHING WAS LOST. The registry flip was held unpushed pending the full suite, precisely
# because this repository's gate IS `uv run pytest -q` and a red suite is a red gate for
# every node. The incompleteness was caught by verification rather than by a failing
# attempt. The lesson is that it should not have needed to be.
#
# NOT IN SCOPE. No production code, no persona registry, no manifest. Two files under
# `tests/`.
---

# Feature Specification: the last two fixtures that choose for the operator

**Created**: 2026-08-29
**Depends on**: 122, landed.

## The gap, stated precisely

Two fixtures remain that decide something the operator owns:

1. `tests/test_poll_usage.py:59` names the operator's default builder as the persona
   fifteen tests lease a virtual key against. A subscription-routed builder mints no key,
   so all fifteen fail.
2. `tests/test_spec_declares_its_fixes.py` reaches the operator's real findings store, so
   its verdict depends on the host it runs on rather than on the code.

## The rule this spec is asking for

**A test may assert that the operator's wiring resolves. It may not assert what the
operator chose, and it may not read the operator's own stores.** Identical to 122's rule;
this is the surface 122's scoping missed.

## User Scenarios & Testing

### User Story 1 - The poll-usage fixtures own their persona (Priority: P1)

As an operator, the poll-usage tests exercise key polling without depending on which
persona I made the default builder.

**Why this priority**: P1 and it depends on nothing. It is the only thing standing between
the operator and the registry change he asked for.

**Acceptance Scenarios**:

1. **Given** an implementer that is a subscription persona, **When** the poll-usage tests
   run, **Then** they pass — proven by a committed test. Fifteen fail today.
2. **Given** a gateway-routed implementer, **When** they run, **Then** they pass exactly
   as today — proven by a committed test.
3. **Given** those fixtures, **When** they name a persona, **Then** it is one the tests
   own rather than a name read from the operator's registry — proven by a committed test.
   Substituting another *real* persona moves the pin instead of removing it.
4. **Given** the whole suite, **When** it is searched for fixtures naming
   `implementer`, **Then** none remains that leases a key against it — proven by a
   committed test. 122 removed two such pins and missed this one; this is the check that
   ends the class rather than its seventh instance.

### User Story 2 - A spec-declaration test builds its own store (Priority: P1)

As an operator, the fixes-declaration tests give the same verdict on a machine with a real
findings ledger and one without.

**Why this priority**: P1 and independent — a different file, a different mechanism. It is
red on the operator's host right now, with the registry untouched.

**Acceptance Scenarios**:

1. **Given** a host with a populated `.factory/doctor.db`, **When**
   `test_validate_reports_the_same_result_with_and_without_fixes` runs, **Then** it passes
   — proven by a committed test. It fails there today with `assert 'fixes' in []`.
2. **Given** a host with no findings store, **When** it runs, **Then** it passes — proven
   by a committed test. Both directions, because passing only in the boundary is the
   defect.
3. **Given** that test, **When** it resolves a store path, **Then** it is under the test's
   own temporary directory — proven by a committed test.
4. **Given** the fixes layer's absent-store path, **When** exercised, **Then** it still
   reports `not checked` rather than refusing — proven by a committed test. That behaviour
   is correct and must survive.

## Work Graph

```yaml
US1:
  implements: []
  depends_on: []
US2:
  implements: []
  depends_on: []
```

Two independent stories in two different files. No merge edges; both dispatch in one round.

## Requirements

- **FR-001**: Fixtures needing a gateway-routed persona MUST name one they own rather than
  the operator's default builder.
- **FR-002**: The poll-usage tests MUST pass with the implementer on either route.
- **FR-003**: No fixture in the suite MAY lease a virtual key against a persona name read
  from the shipped registry, and a committed check MUST enforce that.
- **FR-004**: Tests that read a findings store MUST build it under their own temporary
  directory.
- **FR-005**: The fixes layer's absent-store behaviour MUST be unchanged.

## Success Criteria (summary)

- With `implementer` set to `opus-closer`, `uv run pytest -q` shows no failure that is not
  a known live-tier failure.
- The suite gives the same verdict on a host with a real findings ledger and one without.
- An eighth occurrence of the pin class fails FR-003's check rather than blocking an
  operator instruction.
