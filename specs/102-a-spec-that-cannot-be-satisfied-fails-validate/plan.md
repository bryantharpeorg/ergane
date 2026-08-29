# Implementation Plan: a spec that cannot be satisfied fails validate

**Spec**: `specs/102-a-spec-that-cannot-be-satisfied-fails-validate/spec.md`

A sixth layer in `spec validate` that asks whether each Then-clause can be
evidenced, a report of what the judge will see, and an instruction the judge must
obey about its own remediation menu.

## What already exists, and where

- **The validate composition**: `validate_spec_command(args)`
  (`factory/cli/nouns/spec.py:250`) composes frontmatter, work-graph derivation,
  persona registry, scenario coverage, prompt assembly and slice coverage, each
  with a precise refusal and a `layer '<name>' not checked: <reason>` form for a
  layer it could not run. US1 adds a layer to that composition and follows both
  idioms.
- **The criteria parser**: `factory.verify.criteria.parse_spec` — one of the five
  already-exported checks validate composes. It is where a Then-clause becomes
  structured text, and therefore where US1 reads from.
- **The declared gates**: the manifest's `gates:` block, loaded through
  `factory/verify/factory_yaml.py`. US1 needs the gate *names* for the repository
  the spec targets. `diff_check` is mandatory (`:748-751`) and `gates` and
  `judge` are the other two reserved step names (`:151`).
- **The judge's instructions**: `SYSTEM_PROMPT` (`factory/verify/judge.py:133`),
  including "Never pass a scenario because the change looks reasonable overall".
  US3 adds a companion prohibition about remediation.
- **The verdict shape**: `parse_verdict` and `JudgeVerdict.findings`
  (`factory/verify/judge.py:632-645`). US3's recording and filtering happen where
  findings become the next attempt's feedback.
- **The prior-feedback path**: `build_prompt(..., prior_feedback=...)`
  (`:240-244`) is what carries a previous verdict's text into the next attempt.
  FR-009 is enforced there.
- **`criteria_drift`**: computed by re-hashing the spec file
  (`factory/activities/verify_activities.py:50`, `:449`, `:461-467`). Read-only
  to this epic — it did not fire because nothing drifted.

## Traps

**Trap 1 — this spec and 116 can cancel each other out, and US1-S2 is the
guard.** 116 puts the gate results in the judge's prompt, which makes a
Then-clause naming a gate outcome *provable*. If US1 refuses every clause that
mentions a runtime outcome, it refuses exactly the scenarios 116 just made
answerable, and the pair is a net loss. The rule is: refuse a clause that no
**declared gate** can evidence. Write US1-S2 first and let it constrain the
implementation.

**Trap 2 — this is a heuristic, and a false refusal is worse than a missed
one.** Validate is a gate on authoring, and an author who is refused for a
legitimate clause will phrase around the checker rather than improve the spec —
the same asymmetry that makes half-correct guidance worse than none. Prefer the
warning form (FR-007) wherever confidence is low, and reserve the refusal for
clauses that are clearly unprovable.

**Trap 3 — do not invent a natural-language classifier.** The temptation is to
detect "runtime outcome" by pattern-matching English. Anchor instead on what can
be checked: does the clause reference an artefact a declared gate produces, or a
gate name, or something the diff can show? Keep the rule small enough to state in
the refusal text, because FR-005 requires the refusal to teach.

**Trap 4 — the check needs the target repository's manifest, and validate may
run without one.** `spec validate` takes a `--target-repo`. When no manifest can
be read, the layer must report `not checked` naming the reason, following the
existing idiom — never refuse. This is the same shape spec 089's `fixes:` layer
needs, and if that has landed, reuse whatever it established rather than adding a
second way to say "not checked".

**Trap 5 — FR-003 is the regression surface.** Every spec in this corpus must
validate exactly as before. Run the new layer over the whole `specs/` tree in a
test and assert no verdict changed except where a scenario deliberately asserts
otherwise.

**Trap 6 — US3's prohibition must be tested by behaviour, not by string.**
Asserting the system prompt contains a sentence proves the sentence is there, not
that it works. FR-009 is the enforceable half: a proposal that appears anyway is
recorded and filtered before it reaches the next attempt. Build the filter and
test the filter; the instruction reduces how often it fires.

**Trap 7 — distinguish "this criterion cannot be met" from "change this
criterion".** FR-010 preserves the first and FR-009 blocks the second, and they
are one sentence apart in natural language. A filter that removes both silences
the judge's most useful signal — that the operator wrote an unsatisfiable
criterion, which is the very thing US1 exists to catch earlier. Surface the
report to the operator even while withholding the proposal from the agent.

**Trap 8 — a filtered proposal must still be visible.** FR-009 says recorded, not
discarded. An operator reviewing why an epic struggled needs to see that the
judge wanted the bar moved; the agent does not.

## Sizing

US1 is the epic's real work and its risk is entirely traps 1-3. US2 is a report
assembled from what US1 already computes. US3 is an instruction, a filter and a
recording — small, with trap 7 the one that decides whether it helps or harms.

If an attempt is editing `criteria_drift` or the judge's prompt *contents*
(116 owns that), it has gone outside the spec.

## Verification the operator will run, independent of the gate

The gate proves the layer refuses and warns. The demonstration is the deadlock
that motivated it:

```bash
eval "$(scripts/ergane-env.sh)"
# 1. write a scenario whose Then-clause asserts a runtime outcome no gate covers
#    ("Then the font renders correctly in the browser") and validate it
uv run ergane spec validate <spec-dir> --target-repo .
# 2. rephrase it against a declared gate ("Then the smoke gate passes") and
#    validate again
uv run ergane spec validate <spec-dir> --target-repo .
```

The demonstration succeeds when the first run refuses with a suggestion and the
second passes. Paste both outputs into the attestation. The pair is the whole
argument: the check must refuse the unprovable clause **and** admit the one a
gate can evidence, because refusing both would undo spec 116.
