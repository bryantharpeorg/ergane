# Implementation Plan: the diff ceiling and the evidence doctrine agree

**Spec**: `specs/092-the-diff-ceiling-and-the-evidence-doctrine-agree/spec.md`

One constant becomes two names, the second becomes an operator dial, and the
verdict records when it was reached on abridged evidence. No algorithm changes.

## What already exists, and where

- **The constant and its own argument**: `DIFF_INPUT_LIMIT = 64 * 1024`
  (`factory/verify/diffbounds.py:42`), with the comment above it (`:36-41`)
  recording that it is "~16k tokens: comfortable beside the criteria and
  instructions in any cheap-tier model's context", that it was raised from
  60 KiB on 2026-08-17 because "the original value was a comfort margin, not a
  measurement, and its first false positive was a fully-green story refused four
  times at 61,725 bytes", and that it is "still an attention budget, not a
  context limit". Read that comment before naming anything — it is the argument
  for US1, written by someone who did not yet know it was being used twice.
- **The refusal**: `size_refusal(diff_text, *, limit=DIFF_INPUT_LIMIT)`
  (`factory/verify/diffbounds.py:113`). Its docstring is precise about *what* it
  measures: "the bytes the judge's prompt actually carries: the always-complete
  file listing, plus the preamble, plus every file's section. That assembly is
  what `prepare_diff` compares against the cap, so measuring the raw patch alone
  would disagree with it at the margin."
- **The abridger**: `prepare_diff(diff_text, *, limit=DIFF_INPUT_LIMIT)`
  (`factory/verify/judge.py:315`) — proportional per-file shares with a floor,
  head and tail kept, listing and preamble never abridged, truncation disclosed.
  Read-only to this epic (FR-008).
- **The seam, already cut**: `check_output(..., diff_size_limit: int | None =
  DIFF_INPUT_LIMIT)` (`factory/verify/diffcheck.py:162`), used at `:211`, with
  the rationale at `:178-184`. `None` disables the check. **No production caller
  passes it** — confirmed by grep at drafting time — so today the default is the
  only value the check ever sees.
- **`diff_size_refusal`** (`factory/verify/diffcheck.py:293`) is the wrapper that
  reads the worktree and calls `diffbounds.size_refusal` at `:329`.
- **The record**: `size_refusal` is persisted through
  `factory/verify/store.py:717` and `_size_refusal_to_dict` (`:721`), and read
  back at `:735`. `OutputCheck.size_refusal` is `factory/verify/models.py:433`,
  with the three-ways-to-fail argument at `:416`.
- **The prompt side**: `factory/workgraph/prompt.py:880-882` quotes the refusal
  listing into the next attempt's prompt, which is why
  `OVERSIZE_FILES_NAMED = 5` (`diffbounds.py:49`) is bounded.
- **The manifest's numeric-key idiom**: the ladder bounds checks at
  `factory/verify/factory_yaml.py:648-660` are the shape US2's refusals should
  copy — a type refusal naming the value, then a bounds refusal naming the floor.
- **The doctrine**: Principle VIII (`.specify/memory/constitution.md:63`) and
  D-037 (`docs/decisions.md:963`). US3 exists because of them.

## Traps

**Trap 1 — do not exempt lockfiles, or any path, by name or pattern.** This is
the single most likely wrong implementation, because it is what was done last
time and it appeared to work. Exempting generated files fixed the 185,682-byte
instance and hid the general defect, which reappeared at 74,465 bytes on a story
with no lockfiles in it at all. FR-008 forbids it. A path-shaped fix means the
attempt has solved the instance and left the mechanism.

**Trap 2 — the two limits are two *names*, never two copies of a number.** The
seam's own docstring warns about this: the default is read from
`factory.verify.diffbounds` "rather than restated here — a second copy of that
number would let tuning it silently do nothing." US1 must leave exactly one
definition of each of the two values, with the refusal threshold defined in terms
of the attention budget or beside it, never duplicated into `diffcheck.py`.

**Trap 3 — measure the same assembly both limits already measure.** Both
`size_refusal` and `prepare_diff` weigh the listing plus preamble plus sections,
deliberately, so that the two agree at the margin. Splitting the constant must
not split that measurement. If the refusal starts weighing the raw patch while
the abridger weighs the assembly, the pair disagree exactly where it matters:
where one would elide and the other would call the diff whole.

**Trap 4 — a threshold below the attention budget recreates the defect.**
FR-005 is not defensive tidiness. If an operator sets the refusal under the
abridgement budget, every diff that would have been abridged is refused instead,
which is precisely today's behaviour with a configurable name on it. Refuse at
load time, naming both values, so the misconfiguration cannot ship.

**Trap 5 — `None` still means disabled, and it is a control, not a feature.**
The seam's `None` exists so a test can show the refusal changed an outcome
rather than the outcome having been impossible. Keep it reachable from tests and
do not expose it as a manifest value; a repository that can turn the check off
from its manifest has no ceiling at all, and Principle VIII is non-negotiable.

**Trap 6 — US3's absence of a flag must be a statement.** A row with no
abridgement field is indistinguishable from a row written before this spec.
Record both outcomes explicitly (abridged, with the amount; or not abridged), so
a reader can tell "the judge saw it whole" from "nobody recorded".

**Trap 7 — the prompt quotes the refusal, so its shape is load-bearing.**
`factory/workgraph/prompt.py:880` puts the refusal listing into the next
attempt's prompt verbatim. Changing the refusal's rendering changes what an agent
is told; US1's rename must leave that text as it is unless a scenario asks
otherwise.

**Trap 8 — the manifest corpus is a regression surface.** Every existing
`ergane.yaml` in this repository and its fixtures omits the new key. US2-S2 is
the control that proves they all still load unchanged; write it over the supplied
corpus rather than over one hand-built manifest.

## Sizing

US1 is a rename plus one threaded parameter, and its risk is entirely in trap 2
and trap 3. US2 is a manifest key with two refusals, following an idiom the file
already has four examples of. US3 is the largest: a field on the check, through
the store's serialiser and back, plus a CLI rendering.

If an attempt is editing `prepare_diff`, it has gone outside the spec.

## Verification the operator will run, independent of the gate

The gate proves the split is correct in tests. It cannot prove that a story which
was unbuildable is now buildable, because that needs a real oversize diff through
a real judge. After US2 lands:

```bash
eval "$(scripts/ergane-env.sh)"
# 1. confirm today's behaviour is preserved at the default
uv run python -c "
from factory.verify.diffbounds import size_refusal
print('64KiB+1:', size_refusal('diff --git a/f b/f\n' + 'x'*66000) is not None)
print('32KiB  :', size_refusal('diff --git a/f b/f\n' + 'x'*32000) is not None)"
# 2. with a raised threshold declared in the manifest, the same diff is judged
#    rather than refused — run one real node whose diff exceeds 64 KiB and read:
uv run ergane build status <epic-id> --json | python3 -c "
import sys,json; d=json.load(sys.stdin); print(d)"
```

The demonstration succeeds when a node whose diff exceeds the old constant
reaches a judge verdict at all — PASS or FAIL, either is proof — and its record
says the judge's input was abridged. Before this spec that node cannot reach a
verdict by any route. Paste both outputs into the attestation.
