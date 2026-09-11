# Implementation Plan: a judge cannot waive a concrete counterexample

Refined 2026-09-11 against `ergane-buildout` at `d4784d5fe95b`.

## Current mechanism and incident evidence

- `factory/verify/judge.py:138` defines the fixed system prompt. Lines 143-147
  require per-scenario evidence, while lines 149-158 describe green gate results
  as measurements. Nothing says tests are samples rather than the boundary of
  public behavior.
- `factory/verify/judge.py:160` makes acceptance criteria the standard. Preserve
  that boundary while clarifying how unqualified defaults and universal words
  are read.
- `factory/verify/judge.py:591` strictly parses one result per dispatched
  scenario and lines 645-651 make the stricter per-scenario reading win. The
  parser is not the defect and should not infer bugs from free-form feedback.
- `tests/test_judge.py:343` begins prompt-assembly coverage;
  `tests/test_judge.py:352` checks the response schema and
  `tests/test_judge.py:361` proves criteria arrive verbatim.
- `specs/002-verification-gating/contracts/judge.md:25` documents the fixed
  template and must agree with the shipped prompt contract.

The 158/US4 evidence row records a whole, unabridged diff. Its judge feedback
identified the default `mkstemp` fd/path defect verbatim, stated that no test
covered the branch, called it non-blocking, and returned PASS. This rules out
diff truncation and proves the failure is interpretation, not visibility.

## Implementation

1. Add a short vendor-neutral paragraph to the fixed system prompt after the
   gate-evidence paragraph. State that tests sample behavior, concrete code
   counterexamples remain evidence, unqualified public behavior includes
   defaults, and universal claims require branch/field inspection.
2. Tie every blocking defect back to the closest dispatched scenario. Preserve
   advisory reporting for a defect that contradicts no criterion, so the judge
   does not become an unbounded code-review persona.
3. Add prompt-contract tests built from a small synthetic CLI diff and green
   gate result. Assert the actual assembled system message carries each semantic
   rule and that the user message still carries criteria, gates and the whole
   diff in the existing order.
4. Keep verdict parsing, schema, diff preparation, gate contradiction logic and
   registry untouched. Update the judge contract document to match.
5. Run the focused judge/prompt/contract tests and the full declared gate.

## Traps

1. **The judge already saw the crash.** Raising the diff limit, changing file
   allocation or switching models does not address this incident.
2. **Green tests are positive evidence, not an eraser.** The new instruction
   must say how a visible counterexample and a green sampled gate coexist.
3. **Criteria still bind scope.** “Fail any bug you see” invents requirements
   and defeats the spec boundary. Require a contradiction with a dispatched
   scenario.
4. **Feedback is not machine-readable proof.** Do not add keyword matching over
   prose such as “bug,” “incorrect,” or “non-blocking.” The structured scenario
   result remains the decision.
5. **A string-presence test alone is weak.** Assemble a realistic prompt with a
   green gate and a default-path counterexample, then assert section order and
   the complete semantic contract at the actual judge boundary.
6. **Do not pin the lesson to one vendor.** The active registry may rotate; the
   contract must hold for every judge model.

## Scope

`factory/verify/judge.py`, its focused tests and the existing judge contract.
No model routing, acceptance parser, verification store, gate command, retry
budget, live completion, doctor code or PR504 mutation.
