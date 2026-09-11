# Implementation Plan: counterexample fixtures prove the defect they name

Refined 2026-09-11 against `ergane-buildout` at
`0dcb761ca6d3f7f24dd9eecf2c916e0230cbc654` and the parked PR 509 candidate at
`192fd7891e9316dddc369ff7d730c080e8b80cd6`.

## Current mechanism and reproduced failure

- `factory/verify/judge.py:307` — `build_prompt` owns the fixed system-message
  boundary changed by PR 509.  Its new default-path, universal-claim and
  advisory-boundary clauses are valid and must be retained.
- `factory/verify/judge.py:591` — `parse_verdict` remains the strict structured-verdict
  boundary.  It is not the defect and must not infer failures from prose.
- `tests/test_judge.py:195` — `unified_diff` is the current landed synthetic-diff
  helper.  PR 509 adds `COUNTEREXAMPLE_DIFF` and `UNIVERSAL_SAFETY_DIFF` nearby.
- `specs/002-verification-gating/contracts/judge.md:25` — the fixed-prompt contract
  must continue to match the shipped system message and the actual 64 KiB bound.

The operator executed the PR 509 fixture bodies without editing the candidate.
The completion call with no argument returned with `option_seen='explicit'` and
`crashed=False`.  The persistence fixture recorded
`('[SANITIZED]', '[SANITIZED]')`.  These are deterministic negative controls,
not an interpretation of model prose.  The spec-171 judge nevertheless called
them an omitted-option crash and an unsanitized slug and returned PASS.

## Implementation

1. Integrate the seven authored PR 509 commits in order, excluding the empty
   salvage marker.  Confirm the resulting three-file payload before repair.
2. Add focused executable controls at the existing test boundary.  The first red
   must run the integrated fixture content, not restate it as an assertion about
   words.  Record the actual omitted-call and persisted-field results.
3. Represent each repaired example as executable before/after source and derive
   the unified diff from those exact strings with the Python standard library.
   The same after-source is executed by the semantic test and carried to
   `build_prompt`, preventing the test and prompt fixtures from drifting apart.
4. For completion, keep the explicit-option path successful and put an explicit
   raised exception on the omitted path.  For universal safety, sanitize one
   field while persisting a distinct raw sibling field supplied by the caller.
5. Preserve the PR 509 system-prompt clauses and contract.  Add assertions that
   the exact generated diffs, criteria, green gate and system contract reach the
   real assembled prompt in the existing order.
6. Run the focused judge/prompt/parser/diff-bound controls, verify the production
   diff is still limited to `SYSTEM_PROMPT`, then run the complete declared gate.

## Traps

1. **Names are not behavior.** A helper named `crash_when_omitted` proves no crash,
   especially when omission supplies `"explicit"`.  Execute the path.
2. **A copied sanitized value is still sanitized.** Assigning `slug = name` after
   sanitizing `name` is not a sibling-field bypass.  Preserve and observe a raw,
   independently controlled sibling.
3. **One source owns both proofs.** Do not maintain a prompt diff and a separate
   executable snippet that can disagree.  Generate the diff from the source the
   test executes.
4. **The PR 509 prompt work is valid.** Do not discard or rewrite its fixed
   contract merely because its evidence fixtures are false.  The repair is the
   evidence seam.
5. **Do not teach the parser to read prose.** Structured per-scenario findings
   remain the only verdict.  No keyword detector, secondary judge or hard-coded
   incident rule belongs here.
6. **Keep the example synthetic and vendor-neutral.** It must not name Ergane
   doctor paths, Kimi, GLM, Codex, a live credential or a model alias.
7. **PR 509 is provenance, not a target for mutation.** Do not close, comment on,
   rearm or retarget it.  Produce a new normal factory landing.
8. **Full green is not fixture proof.** The PR 509 suite and formal gate were
   green while both examples contradicted their labels.  Require the semantic
   negative controls before trusting the full gate.

## Scope

The effective PR 509 payload in `factory/verify/judge.py`,
`tests/test_judge.py` and `specs/002-verification-gating/contracts/judge.md`, plus
test-only standard-library fixture construction.  No other production module,
dependency, model route, registry entry, retry setting, doctor code, workflow,
live service or external PR mutation.

## Qualification

The story is independently qualifiable when a detached reviewer can execute the
two after-sources and observe both contradictions, compare their generated diffs
byte-for-byte with the user message built by `build_prompt`, run the focused
judge/parser/diff-bound suite, confirm the three-file scope and 64 KiB ceiling,
and then observe the factory gate, judge and native merge group on the exact
candidate.  A model verdict alone is insufficient because that is the boundary
this repair exists to test.
