# Implementation Plan: the factory reads origin, not the operator's checkout

**Spec**: `specs/090-the-factory-reads-origin-not-the-operators-checkout/spec.md`

One function is wrong and one function is right. `_refresh_to_default`
(`factory/activities/roadmap_activities.py:105`) picks its branch with
`_default_branch`; `resolve_landing_base` (`factory/workgraph/worktree.py:1225`)
picks it from the manifest and says who answered. This epic converts the caller
and adds a guard so the conversion cannot destroy work on the way.

## What already exists, and where

- **The wrong read**, in full, at `factory/activities/roadmap_activities.py:117-122`:
  a deferred import of `_default_branch`, `_git` and `_head` from
  `factory.workgraph.worktree`, then `default = _default_branch(repo)`, then
  fetch / checkout / `reset --hard origin/<default>`. Its docstring (`:106-113`)
  says the epic derives from "the trunk's current head" — read it, and note that
  the code does not do what it says.
- **The right read** is `resolve_landing_base(repo) -> LandingBase`
  (`factory/workgraph/worktree.py:1225`): manifest first, `_default_branch` only
  when the manifest is absent or malformed, with `.source` carrying which arm
  answered and `.detail` carrying the loader's complaint. `LANDING_BASE_MANIFEST`
  and `LANDING_BASE_HEAD` are its two arm values.
- **The precedent for converting a caller** is `land_node`
  (`factory/activities/merge_activities.py:437`), which calls
  `resolve_landing_base` and then `_log_landing_base` (`:385`) to state the base,
  the repo it was read from and the arm. Read that function before writing US3 —
  it is the shape US3 is asking for, one activity over, and its trap 5 comment
  explains why the arm must be on the line even when the manifest answered.
- **The seam** is `_clone_runner` (`roadmap_activities.py:127`): production
  points it at `_refresh_to_default`, tests hand back a scripted `CloneResult` so
  the activity never spawns git. `clone_target` (`:131`) is the thin wrapper.
- **The park path** is `factory/roadmap/workflow.py:1186-1194`: the activity is
  awaited inside `try: … except FailureError as exc: self._park(spec_dir,
  "clone", str(exc)); return`.

## Traps

**Trap 1 — a refusal is not an exception here, and the docstring says so.**
`clone_target`'s docstring (`:132-141`) draws a line the implementer must keep:
"Never raises on a refused clone — that is a pre-dispatch refusal the workflow
parks — but a git error propagates as an activity failure." US2's refusal is a
*refused clone*, not a git error. Raising from the activity would land it in the
`FailureError` arm and park it with a stringified exception, which works by
accident and contradicts the contract. Carry the refusal on `CloneResult` and
have the workflow park on it explicitly. If that means the workflow grows a
branch it did not have, that is the correct cost.

**Trap 2 — `reset --hard` to a *remote* ref destroys local commits too.** The
obvious dirty check is `git status --porcelain`, and it is half the check. The
reset target is `origin/<branch>`, so a commit made locally and not pushed is
discarded just as surely as an uncommitted edit — and that is the case the
round-2 report measured, because a grooming write that was committed to be safe
was destroyed anyway. FR-003 requires both: a dirty working tree *and*
ahead-of-remote commits.

**Trap 3 — ignored files must not park anything.** `reset --hard` does not touch
ignored files, so counting them as work-at-risk would park every clone that has
ever run a build (`.factory/`, `node_modules/`, `__pycache__`). Ask git, with the
target repo's own ignore rules; do not hand-roll a list. This repository has
already paid once for a guard whose exclusion list was written against a Python
repo (`EXCLUDED_DIR_NAMES`, `factory/workgraph/detector.py:70`).

**Trap 4 — do not touch `resolve_landing_base`.** It is 107's, it is the single
derivation, and it *fails open* deliberately: an absent or malformed manifest
returns the HEAD arm rather than raising, because the gate run will report the
bad manifest as a `CONFIG_ERROR` and a branch reader should not pre-empt that
with a less informative exception. US1-S3 inherits that decision; an
implementer who "fixes" the fallback has broken 107 (FR-008).

**Trap 5 — keep the deferred import.** The imports at `:117-118` are inside the
function, not at module scope. Do not lift them: `factory.workgraph.worktree`
pulls in the workgraph package, and the roadmap activities module is imported by
the worker's activity registration path. Add `resolve_landing_base` to the same
deferred import line.

**Trap 6 — the test seam is `_clone_runner`, but US1 and US2 need real git.**
Scripted results cannot prove reset semantics or that a branch was left
untouched. Build real repositories under `tmp_path` with a local `origin` remote
and drive `_refresh_to_default` directly; reserve `_clone_runner` for tests about
the *workflow's* handling of the result.

**Trap 7 — US1-S4 is the anti-regression that matters.** It is easy to satisfy
US1 by calling `resolve_landing_base` and then still calling `_default_branch`
somewhere for the result's fields. The scenario exists to prove there is exactly
one derivation, which is the whole argument of `landing_branch`'s docstring
(`:1254-1261`): "the same read with the provenance dropped, never a second
derivation."

## Sizing

US1 is small — one import, one call, one field. US2 carries the epic's only real
design work (the refusal's shape, and where the workflow reads it) and should be
sized above the others. US3 is a field and a log line, and is mostly a
transcription of `_log_landing_base`.

If an attempt is editing `factory/workgraph/worktree.py`, it has gone outside the
spec: that module is read-only to this epic (FR-008).

## Verification the operator will run, independent of the gate

The gate proves the tests pass in a sandbox. It cannot prove the roadmap stopped
resetting a real operator checkout, because that needs a running schedule. After
US2 lands, with the worker up and a roadmap schedule active:

```bash
cd <target-clone>
git checkout -b operator/scratch
echo "scratch" >> README.md            # uncommitted work on a non-landing branch
git rev-parse --abbrev-ref HEAD
# wait out one full roadmap tick (default 300 s), then:
git rev-parse --abbrev-ref HEAD        # must still be operator/scratch
git status --porcelain                 # must still show the modification
git reflog -5                          # must show no 'reset: moving to origin/...'
```

Before this spec, the reflog shows `checkout: moving from operator/scratch to
operator/scratch` followed by `reset: moving to origin/operator/scratch`, and the
modification is gone. Paste the three outputs into the attestation — the reflog
is the load-bearing one, because a clean `git status` after a reset is
indistinguishable from a clean `git status` that was never touched.
