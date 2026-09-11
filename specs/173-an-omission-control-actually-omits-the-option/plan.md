# Implementation Plan: an omission control actually omits the option

## Evidence and boundaries

- `factory/verify/judge.py:307` — `build_prompt` is the landed prompt assembly
  boundary.  PR 512 changes only its fixed system-message wording in production.
- `factory/verify/judge.py:591` — `parse_verdict` remains the strict structured
  verdict boundary and is not part of this repair.
- `tests/test_judge.py:195` — `unified_diff` is the landed synthetic-diff test
  vocabulary; PR 512 adds the parked and generated fixtures near this seam.
- `specs/002-verification-gating/contracts/judge.md:25` — the existing judge
  contract remains synchronized with the production system message.

The parked PR 512 head is
`376ea7398345d24de48884405610caf7b1fe298d`; its effective authored head is
`3eab623`, and the salvage commit is tree-empty.  Detached qualification ran the
parked fixture with a recording callee.  True omission observed `"explicit"` and
did not crash.  The committed test instead passed explicit `None`, then used a
lambda that returned successfully for every value.  That test could not prove
the branch its name claimed.

## Implementation

1. Integrate the eleven authored commits from `8b80967` through `3eab623` in
   order.  Do not integrate salvage `376ea73`, mutate PR 512 or synthesize a
   combined replacement commit.
2. Preserve the parked completion fixture as historical evidence.  Execute it
   with a recorder that appends the received option and raises only for the
   string `"omitted"`.
3. Replace the misleading negative control with two calls.  The first is
   literally `complete("target")`; assert its result and capture
   `("explicit",)`.  The second is literally
   `complete("target", option=None)`; assert the visible exception and final
   capture `("explicit", "omitted")`.
4. Re-run the repaired completion and universal-safety sources.  Compare the
   standard-library-generated diffs byte-for-byte with the final user messages
   produced by `build_prompt`; retain the system-message/contract equality and
   diff-cap controls.
5. Commit a compact evidence note with the failing old call shape and passing
   corrected observations.  Run the focused judge, parser, gate-evidence,
   contradiction and diff-bound checks, then the full declared gate.

## Traps

1. **Syntax is evidence.** `option=None` is not omission.  A test name, comment
   or expected result cannot repair a call that still supplies the keyword.
2. **Observe the callee.** A stub returning the same value for every argument
   hides the distinction.  Record the value and make the wrong branch fail.
3. **Keep the repaired fixtures.** Completion omission must raise in the repaired
   after-source, and the safety example must still persist a distinct raw sibling.
4. **One source owns each repaired proof.** Execute the exact after-source used
   to generate the prompt diff; never maintain a second illustrative snippet.
5. **Do not broaden the judge.** The parser, model call, retry policy and verdict
   schema are not implicated.  This is a test-evidence repair.
6. **PR 512 stays parked.** Do not close, comment, retarget or rearm it.  Its
   authored commits are input provenance for a new normal factory landing.

## Scope

The effective PR 512 files in `factory/verify/judge.py`, `tests/test_judge.py`
and `specs/002-verification-gating/contracts/judge.md`, plus a compact evidence
file under this spec.  No dependency, parser, schema, workflow, retry, registry,
route, credential, doctor or live-service change.

## Qualification

A detached reviewer must execute both parked call shapes and observe
`("explicit", "omitted")`, execute both repaired after-sources, compare the two
generated diffs with the production prompt messages, run the focused contract
suite, confirm the bounded four-file payload, and then observe the full gate,
judge and native merge group on the exact candidate.  Green pytest alone is not
proof unless the committed omitted call contains no option keyword.
