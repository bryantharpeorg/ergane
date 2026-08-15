---
state: draft
# Drafted 2026-08-15 by an operator session, from three open critical findings
# sharing one mechanism: `mergequeue/agent-session-home-lands-on-the-landing-branch`,
# `verify/judge-cannot-see-a-large-diff`, and
# `verify/output-check-failure-reaches-no-agent` (filed the same morning), with
# `hygiene/runtime-root-not-gitignored-after-the-rename` closed as a side effect
# of US1 being deterministic rather than gitignore-dependent.
# Every acceptance scenario is provable from the diff (D-037): the incidents are
# reconstructed as committed fixtures.
---

# Feature Specification: 045-judge-diff-hygiene

## Context

Overnight 2026-08-14→15, agents working `033-ergane-install/us1` and
`034-ergane-init/us1` committed their own session homes — `.ergane/homes/`,
18 files, 2.0 MB — into their worktrees. Every judge scoring that followed saw a
diff dominated by session archives: eight consecutive FAILs across two epics,
each flagged `truncated_input: true`, each with feedback confidently describing
work as absent that the truncation had hidden. The verdicts were not wrong about
the diff they saw; they were wrong about the work. Worse, that blind feedback
steered: told to "re-do the work on the correct branch," a us2 agent committed
its implementation directly onto the operator's checkout — recurrence nine of
`hardening/agent-edits-the-operator-checkout-not-its-worktree`.

The same night exposed the second half of the mechanism. `033/us2` burned four
attempts with byte-identical `has_diff: false` output checks — and the retry
prompt never told it. `_attempt_block` (`factory/workgraph/prompt.py:556`)
renders failing gates and judge feedback only; an output-check failure produces
neither (the judge is correctly skipped when the output check fails —
`factory/verify/models.py:369`), so each retry was shown "nothing failed
loudly" and repeated the attempt blind.

One principle covers all of it: **the judge must only ever be shown a diff it
can actually judge, everything decidable deterministically must be decided
before a judge token is spent, and whatever decided a FAIL must reach the next
attempt.** The output check is where the factory already enforces "no gate and
no judge may rescue it" (`factory/verify/diffcheck.py:1-8`); this spec widens
that floor.

---

### User Story 1 - A diff carrying ignore-pattern or runtime-root paths fails before the judge (Priority: P1)

The session homes were tracked files matching an ignore pattern — and a tracked
file is invisible to gitignore, which is why prospectively fixing `.gitignore`
(`f6f5a67`) could not close the class: any node whose base predates the fix
still commits the junk. The check must therefore be the factory's, not git's: a
changed path that matches the target's ignore rules, or sits under a runtime
root, fails the output check deterministically, naming every offending path,
and the judge never runs.

**Why this priority**: This class burned eight attempts in one night and its
blind feedback caused a worktree escape. It is also the cheapest check in the
pipeline — a pattern match against a path list the output check already knows
how to collect.

**Independent Test**: Construct a worktree committing files under
`.ergane/homes/` and confirm the output check fails naming them with no judge
invocation; construct a clean worktree and confirm behavior is unchanged.

**Acceptance Scenarios**:

1. **Given** a node worktree whose commits include files under `.ergane/homes/`
   (the 2026-08-14 incident, reconstructed as a fixture), **When** the output
   check runs, **Then** it fails naming each offending path, and the
   verification result records no judge verdict — proven by a committed test.

2. **Given** a worktree committing a file that matches the target repository's
   own `.gitignore` patterns (e.g. a `__pycache__/` file), **When** the output
   check runs, **Then** it fails naming the path and the matching pattern —
   proven by a committed test whose fixture makes the file *tracked*, because a
   tracked file is precisely the case plain `git check-ignore` reports nothing
   for (exit 1) while `--no-index` reports the match; the test pins that
   distinction.

3. **Given** a worktree whose diff is clean of both classes, **When** the output
   check runs, **Then** its result is byte-identical to today's — proven by a
   committed test.

4. **Given** a worktree containing *untracked* ignored files (build noise),
   **When** the output check runs, **Then** they neither fail hygiene nor count
   as the diff FR-004 demands, exactly as today — proven by a committed test.

5. **Given** a read-scope node with no worktree, **When** the output check runs,
   **Then** the artifact path is untouched by this spec — proven by a committed
   test.

---

### User Story 2 - An oversized diff is refused deterministically, not judged truncated (Priority: P1)

Over `DIFF_INPUT_LIMIT` (`factory/verify/judge.py:59`), the judge's diff is
truncated per file and the verdict is flagged `truncated_input` — but the flag
changes nothing: the judge still rules, and absence-of-evidence findings from a
diff with its evidence cut out read exactly like real failures. Eight verdicts
proved that flag is a record, not a guard. A diff the judge cannot see whole is
not judgeable, and an unjudgeable attempt must fail deterministically — before
the judge, with feedback naming the total size, the limit, and the files that
spent the budget — so the next attempt knows to shrink the diff rather than to
"re-do" work that was never missing.

**Why this priority**: Same incident, second layer of defense. US1 removes the
noise that *made* the diffs oversized; US2 makes size itself unable to produce
a hallucinated verdict, whatever causes it next time.

**Independent Test**: Drive a worktree whose diff exceeds the limit through
verification and confirm the deterministic FAIL names sizes and files with the
judge never invoked; drive one under the limit and confirm the judge path is
unchanged.

**Acceptance Scenarios**:

1. **Given** a worktree whose diff against base exceeds `DIFF_INPUT_LIMIT`,
   **When** verification runs, **Then** the attempt fails before any judge
   call, and the recorded evidence names the total diff size, the limit, and
   the largest contributing files with their sizes — proven by a committed
   test.

2. **Given** a diff under the limit, **When** verification runs, **Then** the
   judge is invoked exactly as today and the result is unchanged — proven by a
   committed test.

3. **Given** the size check disabled through its seam, **When** the oversized
   worktree from scenario 1 is verified, **Then** the diff reaches the judge
   truncated — the control proving the check changed an outcome (SC-004) —
   proven by a committed test.

4. **Given** the diff, **When** `factory/verify/judge.py` is read, **Then**
   `prepare_diff`'s truncation at `:316` still exists unchanged, as defense in
   depth behind the new check.

---

### User Story 3 - A failed output check reaches the next attempt (Priority: P1)

Four attempts failed on `has_diff: false` and no prompt ever said so. The
evidence block the retry is shown renders failing gates and judge feedback
only; when the output check is what decided the FAIL — and it is the *only*
decider whenever it fails, because the judge is then skipped — the next attempt
is told nothing at all. Whatever the output check records, including what US1
and US2 add to it, must render into the retry prompt verbatim.

**Why this priority**: Feedback is the only mechanism by which a retry can be
better than a re-roll. Without this story, US1 and US2 produce correct FAILs
that agents repeat blind — the 4× `has_diff:false` burn, generalized.

**Independent Test**: Build attempt evidence carrying each failure shape and
confirm the rendered prompt names it; build passing evidence and confirm the
rendered prompt is byte-identical to today's.

**Acceptance Scenarios**:

1. **Given** attempt evidence whose output check failed with `has_diff: false`,
   **When** the next attempt's prompt is assembled, **Then** the evidence block
   states that the attempt produced no diff against its base — proven by a
   committed test.

2. **Given** an output check that failed on hygiene (US1), **When** the prompt
   is assembled, **Then** every offending path is listed verbatim — proven by a
   committed test.

3. **Given** an output check that failed on size (US2), **When** the prompt is
   assembled, **Then** the size, limit and named files appear — proven by a
   committed test.

4. **Given** attempt evidence whose output check passed, **When** the prompt is
   assembled, **Then** it is byte-identical to today's rendering — proven by a
   committed test asserting equality against the current fixture corpus.

---

## Functional Requirements

- **FR-001**: The output check MUST fail any attempt whose changed paths
  (committed or uncommitted) match the target repository's ignore rules or fall
  under a runtime root, and MUST record every offending path. Pattern matching
  MUST NOT depend on the file's tracked status.
- **FR-002**: When the output check fails, the system MUST NOT request a judge
  completion — the existing `judge_required` mechanism, preserved.
- **FR-003**: An attempt whose diff exceeds the judge's input limit MUST fail
  deterministically before the judge, recording the total size, the limit, and
  the largest contributing files with sizes.
- **FR-004**: For worktrees clean of both classes and under the limit, every
  verdict, row and prompt MUST be byte-identical to current behavior.
- **FR-005**: A failed output check MUST render its recorded evidence into the
  next attempt's evidence block verbatim.
- **FR-006**: Nothing fails open: ignore rules that cannot be read, or a git
  that cannot answer, MUST surface as the existing infrastructure failure
  (`WorktreeMissingError` → `WORKTREE_MISSING`), never as a pass.
- **FR-007**: The runtime-root prefixes MUST cover both the legacy and current
  root names as `factory/env.py` resolves them, never a single hardcoded
  literal.
- **FR-008**: Read-scope verification (artifact-proof) MUST be unchanged.

## Success Criteria

- **SC-001**: The 2026-08-14 homes commit, reconstructed as a fixture, fails the
  output check naming its paths with zero judge invocations.
- **SC-002**: The 4× `has_diff:false` burn is structurally impossible to repeat
  blind: any output-check FAIL's reason appears in the next attempt's prompt.
- **SC-003**: The full suite passes with existing verification fixtures
  unchanged — the parity half of the spec, FR-004.
- **SC-004**: **Control.** With the size check disabled through its seam, the
  oversized fixture reaches the judge truncated — establishing the check
  changed an outcome rather than the case having been impossible.

## Out of Scope

- An operator override or allowlist for hygiene failures. If a legitimate story
  must commit a path matching an ignore rule, that is a spec-refinement
  conversation, not a knob — revisit only if the refusal ever names a
  legitimate path.
- Retry-signature parking (two identical failures → park). Separate candidate.
- Any change to what the judge is asked or how it rules. This spec controls
  what reaches it, not what it does.
- Sandbox enforcement of where agents may write — that is `011-agent-sandbox`.
  This spec catches what lands in a diff regardless of how it got there.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-006, FR-007, FR-008]
US2:
  depends_on: [US1]
  implements: [FR-003]
US3:
  depends_on: [US2]
  implements: [FR-005, FR-004]
```
