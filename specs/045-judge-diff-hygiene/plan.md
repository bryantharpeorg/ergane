# Plan: 045-judge-diff-hygiene

Refined against the tree at `ca122ad` on 2026-08-15. Every line anchor below was
checked by hand against that commit; re-check them if the tree moves before
dispatch.

Findings this spec closes or narrows:

| Finding | Sev | Story |
| --- | --- | --- |
| `mergequeue/agent-session-home-lands-on-the-landing-branch` | critical | US1 |
| `hygiene/runtime-root-not-gitignored-after-the-rename` | warning | US1 (the deterministic check makes the gitignore gap moot) |
| `verify/judge-cannot-see-a-large-diff` | critical | US2 |
| `verify/output-check-failure-reaches-no-agent` | critical | US3 |

## What already exists, and where

| Thing | Location | Note |
| --- | --- | --- |
| `check_output` / `_has_diff` | `factory/verify/diffcheck.py:106`, `:157` | The home for US1 and (recommended) US2. Already collects porcelain status and `git diff <base> --name-only` (`:167`, `:182`) — the changed-path list US1 needs is one `--name-only` away. |
| The floor principle | `factory/verify/diffcheck.py:1-8` | "No gate and no judge may rescue it." US1/US2 widen this floor; they do not create a second one. |
| `_git` runner | `factory/verify/diffcheck.py:186` | Scrubbed-env, timeout-bounded read-only git. Run `check-ignore` through it. |
| `WorktreeMissingError` | `factory/verify/diffcheck.py:74` | FR-006's existing shape: unreadable ≠ clean. |
| `OutputCheck` model | `factory/verify/models.py:241` | US1/US2 extend it. **New fields need defaults** — see trap 5. |
| `judge_required` | `factory/verify/models.py:355` | Already skips the judge when `output_check.passed` is false (`:369-373`). US1/US2 ride this; do not touch it. |
| `compose_result` | `factory/verify/models.py:376` | The only verdict-maker. Failures go through `OutputCheck.passed`, never a new verdict path — see trap 4. |
| Verification sequence | `factory/workgraph/workflow.py:1761-1795` | gates → check_output → `judge_required` → read_worktree_diff → judge → compose_result. |
| `DIFF_INPUT_LIMIT` | `factory/verify/judge.py:59` | 60 KiB. US2's threshold — read it, never restate it (trap 8). |
| `prepare_diff` | `factory/verify/judge.py:316` | Today's truncation; stays as defense in depth (US2-S4). |
| `truncated_input` | `factory/verify/judge.py:194-207` | The flag that proved to be a record, not a guard. |
| `_attempt_block` | `factory/workgraph/prompt.py:556` | US3's whole surface: renders failing gates and judge feedback only; `_NOTHING_FAILED_LOUDLY` is what a failed output check renders as today. |
| `_quote` | `factory/workgraph/prompt.py:589` | Fence helper for anything US3 renders; do not hand-roll fences. |
| Runtime-root names | `factory/env.py:37` (`resolve_env_path`), `factory/workgraph/worktree.py:135` | FR-007: derive both prefixes; 043 just spent a story on code that hardcoded one. |

## The check-ignore probe, verbatim

Run 2026-08-15 on this host; this asymmetry is the whole reason gitignore could
not stop the incident and the reason FR-001 says "MUST NOT depend on tracked
status":

```
$ git check-ignore -v .ergane/homes/session.json          # file is TRACKED
$ echo $?
1                                                          # no match reported
$ git check-ignore -v --no-index .ergane/homes/session.json
.gitignore:1:.ergane/	.ergane/homes/session.json
$ echo $?
0
```

Use `--no-index`, or evaluate the patterns directly; a test must pin whichever
you choose against a *tracked* fixture file (US1-S2).

## Route choices left to the implementer

**Where US2's size check runs.** Two candidates. (a) Inside
`check_output`: compute the diff's byte size there (`git diff <base>` piped
through the existing `_git` runner) and fold the verdict into
`OutputCheck.passed` — one floor, one home, `judge_required` needs no change,
and US3's rendering gets the evidence for free. (b) In the workflow between
`read_worktree_diff` (`workflow.py:1784`) and `_judge` (`:1791`) — closer to
where the diff text already exists, but it creates a second place a FAIL is
decided and workflow-side logic where activity-side suffices. Prefer (a); if
you take (b), keep it a pure function and say why. Either way the disable-seam
for SC-004's control must exist and must be explicit, not an environment read.

**How hygiene names the runtime root.** The worktree-relative prefixes to
refuse are the resolved names of both roots (FR-007). Derive them from the same
source `resolve_factory_root` reads rather than duplicating the precedence —
043/US4's route discussion applies verbatim here.

## Traps

**Trap 1 — plain `check-ignore` lies about tracked files.** Proven above. The
incident's files were tracked; a hygiene check that consults the index reports
the entire class clean. `--no-index`, always, and the US1-S2 fixture must
commit the file first or the test proves nothing.

**Trap 2 — do not break the untracked-ignored exemption.** `_has_diff` counts
untracked files but not ignored ones (`diffcheck.py:48-51`) — build noise has
never manufactured a diff and must not start failing hygiene either (US1-S4).
Hygiene examines paths that are *in the diff* (committed, or tracked-and-
modified, or untracked-and-unignored); it does not go looking for ignored files
on disk.

**Trap 3 — the read-scope asymmetry is deliberate.** `diffcheck.py:10-22`:
read-scope nodes are judged on artifacts, may have no git at all, and `_has_diff`
runs with `required=False`. Hygiene and size apply to diff-scoped nodes only
(FR-008); a hygiene check that raises on a missing repo for a read node breaks
`needs_worktree: false` personas.

**Trap 4 — one verdict-maker.** `compose_result` (`models.py:376`) states the
truth table once. Both new checks express themselves as `OutputCheck.passed =
False` plus recorded evidence; neither adds a verdict enum, a new result field
that decides, or a workflow branch that skips `compose_result`. The moment two
places can decide FAIL, the row and the prompt can disagree — the exact defect
class US3 exists to close.

**Trap 5 — old rows must still deserialize.** `OutputCheck` rows cross the
Temporal payload boundary and sit in `verification.db` as JSON. Every field US1
and US2 add needs a default such that existing stored rows load unchanged —
byte-parity (FR-004, US3-S4) is asserted against the current fixture corpus,
and a required new field fails it instantly.

**Trap 6 — `pass` parity means byte parity.** US1-S3 and US3-S4 say
*byte-identical*, not "equivalent": the retry prompt is assembled from this
evidence, and prompt stability is what makes an untouched graph assemble
identical prompts (`prompt.py:294-299` makes that promise explicitly). Fixture
comparisons, not spot checks.

**Trap 7 — the judge sees the diff and the criteria, nothing else.** Every
"proven by a committed test" and both reconstructed incidents mean committed
fixture files in your diff. The probe transcript above is already in this plan;
your tests must earn their own evidence, not cite this document.

**Trap 8 — do not restate the limit.** US2's tests read `DIFF_INPUT_LIMIT`
(`judge.py:59`), never hardcode 61440. The constant has moved once already
(60 KiB is itself a tuned value) and a test pinning the number turns the next
tuning into a false failure.

**Trap 9 — size feedback must name files, not just totals.** "Diff too large:
2.1 MB > 60 KiB" sends the agent hunting. "…of which `.ergane/homes/chat.json`
is 1.4 MB" ends the hunt in one line. The largest-contributors list is the
actionable half of FR-003; `prepare_diff`'s per-file accounting (`judge.py:316`
onward) already computes section sizes worth reusing.

**Trap 10 — US3 renders evidence, it does not summarize it.** FR-005 says
verbatim: the recorded paths, sizes and reasons, through `_quote`
(`prompt.py:589`), in the same discipline as gate tails — "an agent re-driven
on a summary debugs the summary." Resist writing prose about the failure;
quote the failure.

## Verification the operator will run, independent of the gate

- Rebuild the homes layout in a scratch worktree (commit files under
  `.ergane/homes/`), run verification, and read the FAIL naming the paths with
  `judge` absent from the row.
- Construct a >60 KiB diff, verify, and confirm zero judge-key mints in the
  ledger for that attempt.
- Take a real failed `has_diff:false` row from `verification.db` (2026-08-15
  has four) and render the next-attempt prompt; the empty-diff statement must
  be present.
