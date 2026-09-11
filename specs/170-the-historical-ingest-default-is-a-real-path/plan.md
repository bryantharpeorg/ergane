# Implementation Plan: the historical ingest default is a real path

Refined 2026-09-11 against `ergane-buildout` at `d4784d5fe95b`. Resolve
citations by symbol if intervening landings move their line numbers.

## Preserved candidate and current base

- The complete factory-authored candidate is the four-commit range
  `aa6d8ce..3015d69` on
  `origin/factory/158-operator-skills-report-and-act-by-declared-intent/us4`,
  based on `e4fba1927753`. Commit `db05f7163163` is only the factory salvage
  marker and carries no source change.
- `specs/158-operator-skills-report-and-act-by-declared-intent/spec.md:66`
  defines the original historical-ingestion story and its four scenarios.
- `factory/doctor/cli.py:89` contains the existing credential matcher and
  sanitizer; `factory/doctor/cli.py:101` sanitizes the current finding carrier
  but the buildout base has no historical command yet.
- `factory/doctor/models.py:29` and `factory/doctor/models.py:47` are the current
  finding and event carriers that the candidate extends.
- `factory/doctor/store.py:18` declares schema version 1;
  `factory/doctor/store.py:123` is the existing bootstrap boundary the candidate
  extends with an idempotent migration.
- `.agents/skills/findings-ingest/SKILL.md` is the operator workflow that must
  continue to separate rehearsal from application.

Integrate the preserved candidate on the current buildout base before making
the repair. Prefer cherry-picking its four authored commits in order or applying
their exact tree delta. Do not cherry-pick the salvage marker, edit PR504, or
reimplement the already-qualified event model from memory.

## Proven red loops

The candidate's focused module passed 34 tests, while two independent disposable
checks fail deterministically:

1. A namespace produced by the real argument parser for `findings ingest
   --batch <path>` reaches the analysis-only default and crashes because
   `tempfile.mkstemp()` returns `(integer_fd, pathname)` and the implementation
   calls `Path(integer_fd).unlink()`.
2. A batch whose `observation_id` contains a synthetic credential-shaped marker
   completes rehearsal and the marker is present byte-for-byte in the stored
   event. The candidate sanitizes the nested `Finding` but copies the sibling
   identity field unchanged.

Keep both loops under temporary roots and use synthetic markers only. Never read
or print a real credential.

## Implementation

1. Integrate the candidate's models, parser, schema migration, historical store
   writer, CLI surface, skill update and focused tests on the current base.
2. Before changing the two faulty branches, convert both qualification loops to
   committed regressions at the real command/store seam and observe the specific
   failures.
3. Repair default rehearsal creation by treating the first `mkstemp` value as a
   descriptor and the second as the path. Close the descriptor on every path,
   remove or safely reuse the placeholder as SQLite requires, and keep the
   printed path readable after return.
4. Extend the historical sanitization boundary to observation identity. Preserve
   deterministic idempotency without collapsing distinct credential-bearing
   source identities; sanitization, stable derivation or refusal is acceptable
   only if every FR-003/FR-004 assertion holds.
5. Re-run the two red loops, all 158/US4 focused tests, doctor store/CLI controls,
   schema-contract parity and the full declared gate.

## Traps

1. **A parser default is not a command test.** The candidate asserts
   `args.apply is False` but never calls the command with the omitted optional
   path. The regression must reach temporary-file creation and inspect its result.
2. **`mkstemp` returns two different types.** Closing the pathname or unlinking
   the integer repeats the bug. Leaving the descriptor open passes the happy
   path while leaking one descriptor per rehearsal.
3. **The historical carrier has a sibling identity field.** Sanitizing only
   `observation.observation` leaves `observation_id` untouched.
4. **Redaction can destroy identity.** Replacing every secret-like fragment with
   one constant may collapse two different historical observations and silently
   turn the second into a duplicate. Test sameness and distinctness.
5. **Analysis is not application.** No test or implementation path may open the
   operational database merely to prove it stayed unchanged.
6. **Current reporting semantics are a control.** Do not route live `report`
   through the historical writer or add observation identity to current events.
7. **The parked branch is evidence, not a landing target.** Do not push to,
   close, re-arm or otherwise mutate PR504 from this story.

## Scope

The candidate's eight paths plus focused repairs and bounded evidence. No judge
prompt, model route, worker deployment, roadmap state, live ledger or release
publication belongs in this story.
