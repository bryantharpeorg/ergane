# Implementation Plan: the judge scores against what the factory measured

**Spec**: `specs/116-the-judge-scores-against-what-the-factory-measured/spec.md`

One section is added to a prompt, one contradiction check is added to the
composition, and one field is added to the record. Nothing about what the gates
measure or when the judge runs changes.

## What already exists, and where

- **The assembler**: `build_prompt(criteria, diff_text, *, prior_feedback=None)
  -> JudgePrompt` (`factory/verify/judge.py:240`). Its docstring (`:246-255`)
  states the section order and says it is not cosmetic — the requirement and its
  scenarios establish the standard before the diff, prior feedback says what the
  last attempt got wrong, and the diff goes last "because it is the only part
  that may have been cut". FR-005 places the new section inside that argument
  rather than beside it.
- **The one caller**: `factory/verify/judge.py:616`, inside the module's
  `run_judge`, which is wrapped by the activity at
  `factory/activities/verify_activities.py:409-423` and invoked from
  `factory/workgraph/workflow.py:2679`.
- **The guard that proves the invariant**: `judge_required(gate_results,
  output_check, criteria)` (`factory/verify/models.py`). Read its docstring
  before writing US1 — it is the argument for why a gate section is never
  misleading on the judged path, because it returns True only when
  `gates_passed(gate_results)` (`:517`).
- **The composition**: `compose_result` (`factory/verify/models.py`), whose
  verdict line is `passed = gates_passed(gate_results) and output_check.passed
  and judge_accepts` (`:608`). US2's contradiction check belongs where
  `judge_accepts` is derived, not in a fourth place that could disagree.
- **The retry machinery**: `parse_verdict` returns RETRY or FAIL depending on
  `judge_attempt >= 1 + max_judge_retries` (`factory/verify/judge.py:637-640`).
  US2's retry must ride that existing budget, not open a second one.
- **The strictness table**: `_STRICTNESS` (`factory/verify/judge.py:126-131`)
  makes "the stricter reading wins" a `max`. Do not add an outcome to it — a
  new outcome is explicitly out of scope.
- **The system prompt**: `SYSTEM_PROMPT` (`factory/verify/judge.py:133`),
  including the sentence that creates the defect: "if the evidence is not in the
  diff, the scenario does not pass."
- **The record**: `VerificationResult` and its serialisers in
  `factory/verify/store.py`; `truncated_input` is already carried from the
  prompt onto the verdict (`judge.py:636`), which is the precedent US3 follows.

## Traps

**Trap 1 — the system prompt must change, or US1 does nothing.** Adding a gate
section while leaving "if the evidence is not in the diff, the scenario does not
pass" untouched produces a judge that reads the gate results and then explains
why it may not use them. The sentence needs a companion clause: the gate results
are evidence, they are the factory's own measurement of this attempt, and a
scenario whose Then-clause names a gate outcome is scored against that
measurement. An attempt that adds the section and not the instruction has done
the mechanical half and left the defect.

**Trap 2 — do not weaken the instruction into "pass if it looks reasonable".**
The same sentence exists to stop the judge rubber-stamping. Widen it to *named
measurements*, not to overall impressions. The phrase "Never pass a scenario
because the change looks reasonable overall" stays.

**Trap 3 — FR-003 is the whole regression surface.** Every existing judge test
compares assembled prompts. Making the gate section unconditional would rewrite
all of them and make the diff unreadable. Default to no section, so the existing
corpus is untouched and the new behaviour arrives only where gate results are
supplied.

**Trap 4 — the budget is measured on the assembly, not on the diff.** The
prompt's size is what `prepare_diff` fits under `DIFF_INPUT_LIMIT`, and that
measurement weighs the listing, the preamble and every section. A gate section
added outside that accounting silently steals from the diff's share and truncates
evidence nobody disclosed. Add it to the same assembly the cap already measures.
(Spec 092 splits that constant into two; this epic must keep working whichever
lands first, so read the value through whatever name exists rather than
hardcoding 64 KiB.)

**Trap 5 — the contradiction check must key on the gate's *name*, and names come
from the manifest.** The verdict's text names a gate because the criteria and the
prompt name it; matching must be exact or on a word boundary, never a bare
substring, or a repo with gates `test` and `typecheck` will match `test` inside
`typecheck`. This repository has already been bitten once by an unanchored
match — the credential regex at `factory/cli/doctor.py:58`.

**Trap 6 — a contradiction is not a pass.** US2 says the finding must not *by
itself* produce a node FAIL. It does not say the attempt passes: other findings
stand, the output check stands, and the gates stand. Neutralise the one finding
and recompose; do not short-circuit to PASS.

**Trap 7 — one place decides.** `compose_result` already carries the comment
that the moment two places can decide a FAIL, the stored row and the retry prompt
can disagree. The contradiction check goes where `judge_accepts` is derived.

**Trap 8 — US3's silence must be a statement.** A row without the new field is
indistinguishable from a row written before this spec. Record both cases.

## Sizing

US1 is a prompt section, an instruction change and a parameter threaded from one
caller — small, and its risk is entirely trap 1 and trap 4. US2 is the epic's
real work: a matcher, a neutralisation, and a retry that rides an existing
budget. US3 is a field and a rendering.

If an attempt is editing a gate implementation or `judge_required`, it has gone
outside the spec.

## Verification the operator will run, independent of the gate

The gate proves the section is assembled and the contradiction is caught. It
cannot prove the deadlock is gone, because that needs a real model scoring a real
unscoreable scenario. After US1 lands:

```bash
eval "$(scripts/ergane-env.sh)"
# Build a criteria set with a Then-clause that names a runtime outcome
# ("Then the suite passes"), supply gate results showing that suite PASS, and
# score it against the real judge persona:
uv run python -c "
import asyncio, json
from factory.verify import judge
# assemble with and without the gate section and print both prompts
"
```

Score the same scenario twice against the live judge — once with the gate
section and once without — and paste both verdicts into the attestation. The
demonstration succeeds when the with-gates run passes the scenario and the
without-gates run fails it. That single pair is the whole argument of the spec,
and no gate can produce it because it requires a model.
