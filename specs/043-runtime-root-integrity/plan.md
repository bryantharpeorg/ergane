# Plan: 043-runtime-root-integrity

Refined against the tree at `17d5eb0` on 2026-08-14. Every line anchor below was
checked by hand against that commit; re-check them if the tree moves before dispatch.

Scaffolded by `ergane findings promote` from four findings:

| Finding | Sev | Story |
| --- | --- | --- |
| `ci/store-isolation-test-demands-the-live-store-be-deleted` | critical | US1 |
| `doctor/findings-store-not-routed-through-runtime-root-resolver` | critical | US2 |
| `cli/migrate-runtime-root-cannot-run` | critical | US3 |
| `cli/migrate-refusal-names-the-deprecated-variable` | warning | US4 |

## What already exists, and where

| Thing | Location | Note |
| --- | --- | --- |
| `resolve_factory_root(env_name="FACTORY_ROOT") -> (Path, RuntimeRootChoice)` | `factory/workgraph/worktree.py:135` | The resolver US2 must route through. **Creates the directory as a side effect** — see trap 2. |
| `RuntimeRootChoice` (`NEW` / `LEGACY`) | `factory/workgraph/worktree.py:125` | Describes the *directory*, never the *variable*. Relevant to US4. |
| `_warn_legacy_root_once` + `_DEPRECATED_LEGACY_ROOT` | `factory/workgraph/worktree.py:185` | Process-global sentinel — see trap 3. |
| `resolve_env_path(new, old, default)` | `factory/env.py:37` | Owns `ERGANE_*` / `FACTORY_*` precedence. Reuse it; do not re-implement it. |
| `_WARNED` deprecation sentinel | `factory/env.py:33` | Second process-global — see trap 3. |
| `DEFAULT_VERIFICATION_DB_PATH = ".factory/verification.db"` | `factory/activities/verify_activities.py:126` | The literal US1's assertion collides with. |
| Doctor path literals | `factory/cli/doctor.py:41`, `factory/doctor/cli.py:40`, `factory/doctor/probes.py:133` and `:135` | The four sites US2 must remove. |
| `_open_client` | `factory/cli/repo.py:49` | Missing `import os`; `os.environ` at `:51-52`. |
| `_temporal_client_factory` seam | `factory/cli/repo.py:63` | Defaults to `_open_client`. No test enters the default. |
| Override refusal | `factory/cli/repo.py:152` | Hardcodes `FACTORY_ROOT` in the message. |
| `_running_epic_ids()` call site | `factory/cli/repo.py:160` | The only real path through the verb. |
| The failing assertion | `tests/test_store_isolation.py:199-202` | Landed by 030/US1 in `c572fdb`. |
| Its stated intent | `tests/test_store_isolation.py:143-145` (comment) | Says "was not created" — the intent is right, the implementation is not. |
| Poison-path assertions | `tests/test_store_isolation.py:135-138`, `:229-230` | These are `/nonexistent-030-proof/...`. **Safe. Leave them alone.** |

## Route choices left to the implementer

**US2, following the data.** FR-006 permits either following the populated legacy
ledger or refusing. Refusing is safer and cheaper to reason about; following is
kinder to an operator mid-migration. Pick one and say which in the commit message,
the way `039/US1` did.

**US4, learning which variable won.** Two routes. (a) Read both names in
`factory/cli/repo.py` and name whichever is set — small, but duplicates a precedence
rule `factory/env.py:resolve_env_path` already owns, and duplicated precedence is
how the two names drift apart. (b) Extend the resolver to report the source
alongside the path — better placed, but `resolve_factory_root` has a second caller
at `factory/activities/merge_activities.py:310` that must keep working. Prefer (b);
if you take (a), say why.

## Traps

**Trap 1 — this repo is in the split state, and the obvious US2 fix destroys the
ledger on it.** Right now `.ergane/` exists (it holds `homes/`) and `.factory/`
exists (it holds all three databases). `resolve_factory_root()` checks
`new.is_dir()` first, so it returns `.ergane/` and warns that the legacy directory
is ignored. Route `doctor.db` "through the resolver" as the finding literally asks
and, on this host, the doctor opens `.ergane/doctor.db` — which does not exist —
creates it empty, and 84 findings with their recurrence counts stop being visible.
That is precisely the loss the finding was filed to prevent, caused by the fix for
the finding. FR-006 exists because of this. Build the split-state test first and
watch it fail before you touch a path default.

**Trap 2 — the resolver creates directories.** `resolve_factory_root()` ends with
`new.mkdir(parents=True, exist_ok=True)` when neither root exists
(`factory/workgraph/worktree.py:179`). A test that calls it without `monkeypatch.chdir`
into a tmp directory creates `.ergane/` inside whatever cwd it inherited — which,
for a gate run, is the node worktree, and for an operator run is the checkout.
Every test you add for US2 and US4 must chdir into tmp first.

**Trap 3 — two process-global warning sentinels will make your tests lie.**
`_DEPRECATED_LEGACY_ROOT` (`worktree.py:185`) and `_WARNED` (`env.py:33`) are
module-level, deliberately, so operators are not flooded. The consequence for you is
that a test asserting a deprecation fires passes when run alone and fails in the
full suite, or the reverse, depending on which test ran first. Reset the sentinel in
a fixture. Do not "fix" the flake by removing the assertion, and do not remove the
gating — trap 7 of 040 put it there on purpose.

**Trap 4 — US2 lands before US3, and the reason is not stylistic.** Today the
`NameError` is the only thing stopping an operator migrating the runtime root. Fix
US3 first and you have armed the very data loss US2 exists to prevent, with no
warning to anyone. The work graph encodes this; do not "optimise" it into a
parallel fan-out.

**Trap 5 — the one-line fix is not the story.** US3's defect is `import os`. If your
diff is that line plus a test that rebinds `_temporal_client_factory`, you have
reproduced the exact conditions that shipped the bug: the suite was green at 2265
passed while the command could not start. FR-004 is the requirement. The AST test in
US3-S3 is the general form; the closed-port test in US3-S1 is the specific one. Both.

**Trap 6 — do not delete US1's assertion.** The test proves something real and its
comment states the right intent. Replace non-existence with non-mutation. And note
that SC-004 is a *control*: you must show the original assertion failing on a
populated host, so that the diff carries evidence the fix changed an outcome rather
than the suite having been green anyway. A passing suite is not proof here — this is
a bug that a passing suite shipped.

**Trap 7 — the judge sees the diff and the criteria, nothing else.** No base tree,
no commit message, no terminal. Every "pasted output" clause in the acceptance
scenarios means a committed file containing that output. Runtime evidence that
exists only in your shell is invisible to the verdict.

**Trap 8 — the poison-path assertions are not the bug.** `tests/test_store_isolation.py:135-138`
and `:229-230` also assert non-existence, and they are correct: they target
`/nonexistent-030-proof/...`, a path chosen so the proof is safe even when it fails.
US1-S4 asks you to confirm every remaining non-existence assertion targets a tmp or
impossible path. Confirming is the task. Changing them is not.

**Trap 9 — `.factory` appears in prose all over this tree.** Docstrings, comments,
this plan. US2-S3 is about *path defaults*, not about the string. A grep-driven
sweep will rewrite documentation and miss `probes.py:135`. Walk the code.

## Verification the operator will run, independent of the gate

- Reinstate the original assertion on a populated host and watch it fail (SC-004).
- Build the split-state layout by hand and confirm the recurrence count survives.
- `TEMPORAL_ADDRESS=127.0.0.1:1 ergane repo migrate-runtime-root` and confirm the
  error is a transport refusal naming the address, not a `NameError`.
