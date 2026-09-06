---
state: draft
fixes:
  - workgraph/a-relative-runtime-root-writes-multi-gigabyte-agent-homes-into-the-installed-package-directory
  - workgraph/the-prepared-worktree-path-is-relative-and-four-consumers-resolve-it-against-the-workers-cwd
  - operator/the-verification-store-path-is-cwd-relative-so-a-read-from-a-worktree-is-silently-empty
  - init/the-readiness-check-reports-on-the-runtime-root-init-wrote-not-the-one-the-engine-resolves
# DRAFTED 2026-09-03 by the operator session, against ergane-buildout at 238b494.
# Every `file:line` in spec.md and plan.md was read from that commit and verified
# to resolve to the symbol named, not recalled.
#
# WHERE THIS CAME FROM. Round-1 finding F6, graded "still open" in the
# `ergane-web` hand-over's regression table on 2026-08-28 and again on 2026-09-03
# — the only round-1 defect to survive two full rounds of fixes. Its grading
# sentence: "`DEFAULT_RUNTIME_ROOT = Path('.ergane')` and the worker's
# `WorkingDirectory` is site-packages, so the `ERGANE_ROOT` /
# `ERGANE_LEDGER_PATH` / `ERGANE_VERIFICATION_DB_PATH` overrides remain
# mandatory."
#
# WHY IT OUTRANKS ITS OWN SEVERITY. Four findings in this repository's own ledger
# are downstream of one resolver, three of them `critical`, and they present as
# four unrelated defects: agent homes written into site-packages, a prepared
# worktree path four consumers resolve differently, a verification store that
# reads empty from a worktree, and a readiness check that reports on a root the
# engine will not use. The mandatory-overrides workaround is why the factory
# appears to work — `scripts/ergane-env.sh` exists to paper over this.
#
# TWO SUBSYSTEMS HAVE ALREADY HAND-ROLLED REPO-ANCHORED COPIES TO AVOID IT, and
# both cite the 2026-08-14 store deletion in their own comments as the reason.
# That is corroboration, not a fix: it means three resolvers now disagree, and
# the two careful ones are invisible to the engine.
#
# NOT IN SCOPE. This spec does not remove the `ERGANE_ROOT` / `FACTORY_ROOT`
# overrides — they stay, and they stay honoured first. It does not relocate any
# existing store's contents, does not change the runtime root's directory layout,
# and does not touch the `.factory` → `.ergane` legacy-name reconciliation 043
# built.
#
# REFINED 2026-09-04 by the refinement workflow (refinement-2026-09-04); every
# anchor in spec.md, plan.md and tasks.md re-read from ergane-buildout at
# 602a92c.
#
# ANCHORS. 057 landed four stories between 238b494 and 602a92c, adding 372 lines
# to `factory/cli/init.py`, so `resolve_repo_runtime_root` moved 1737 → 2088 and
# validate refused on all six citations of it. Every other anchor drafted on
# 238b494 was re-read and had not moved. All function citations are now written
# in the symbol-tier form so the next drift is machine-caught, and eighteen new
# anchors were added for the mechanisms below.
#
# THE INSTRUCTION WAS WRONG ABOUT WHERE THE ANCHOR COMES FROM. "Anchored on the
# repository that owns it" named no mechanism, and a process whose cwd is
# site-packages is inside no repository at all. FR-009 now states the fallback
# and the refusal, and FR-010 makes the worker name the repository it already
# holds in `request.target_repo`. Two arms nobody had written down: a *relative*
# override answered with `.resolve()` freezes the cwd dependence instead of
# removing it (US1-S2), and `git rev-parse --show-toplevel` from inside a node
# worktree answers the worktree, which would leave the verification-store finding
# alive under a green suite (US1-S6).
#
# THE STORE PATHS ARE NOT DERIVED FROM THE ROOT AT ALL, so the drafted FR-004
# could not have fixed the store finding it declares. Five relative literals name
# the *legacy* `.factory/` directly and never consult the resolver; FR-004 now
# names them. A story that only makes the root absolute leaves all three stores
# exactly where they are.
#
# FR-007 AS DRAFTED WOULD HAVE REPEATED THE 2026-08-14 DELETION. `runtime_root_for`
# is environment-blind on purpose because `--clean-runtime` deletes what it
# returns; "reach their answer through the single shared resolver" would have
# handed an `ERGANE_ROOT` outside the repository to a delete path. FR-011 pins the
# blindness and FR-007 now consolidates the name choice only.
#
# ONE KEY WAS HALF-COVERED AND IS NOW WHOLE. The init key's summary is about the
# `.gitignore` line, not only about the report: init writes `.ergane/` alone while
# the engine may resolve `.factory/`. FR-012 adds the missing half. All four keys
# are kept; none is declared on FRs that do not reach it.
#
# STORIES SPLIT 3 → 4. US4 is new: the worker's runtime-root reads must name the
# repository the epic was dispatched against, which is what makes US1's refusal
# survivable in a wheel install rather than merely loud. Landed numbers are
# untouched; US1, US2 and US3 keep theirs.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04) after an adversarial review refuted
# the refined trio on two blocking defects and five minor ones. Measured against
# ergane-buildout at 602a92c, in this repository:
#
# THE FIX WOULD HAVE ORPHANED THIS REPOSITORY'S LIVE STORES. With every override
# unset the resolver answers `.ergane/` here (both names exist, new wins,
# `factory/workgraph/worktree.py:224-230`), while the populated stores are
# `.factory/verification.db` (11,857,920 B) and `.factory/ledger.db` (565,248 B)
# and the `.ergane/` copies are 0 bytes. FR-004 as written would have swapped
# live stores for empty files — the very empty-read failure the spec exists to
# close, reintroduced by the fix. FR-013 now requires the derived default to
# follow the populated file, and it must go beyond the rule 043 landed as
# `_resolve_store_path` (`factory/doctor/cli.py:58`), which tests existence only
# and therefore already answers a stale 28,672 B `.ergane/doctor.db` beside a
# 126,267,392 B `.factory/doctor.db`.
#
# THE STORE READERS HOLD NO REPOSITORY, so FR-009's refusal would have reached
# them. `target_repo` appears zero times in `factory/activities/verify_activities.py`
# and `factory/activities/notify_activities.py`, and `RecordVerificationInput`
# carries only `result` and `criteria_source_path`. FR-014 states the fallback
# explicitly so a wheel-installed worker keeps writing where it writes today
# rather than refusing every verification; the body's "What this spec is not"
# names the half that stays open.
#
# THE SUITE SUPPLIES EVERY OVERRIDE THE SCENARIOS ASSUME ABSENT.
# `_isolated_test_store` (`tests/conftest.py:525`) is session-scoped and autouse
# and sets both root variables and all four store variables for every test
# (`tests/conftest.py:545-552`), so "given no override" is a state a test must
# construct. US2's Then clauses now name the unset, US2-S3 additionally asserts
# which file both processes opened, and trap 14 carries the mechanism.
#
# THE DISCLOSURE HALF OF THE OPERATOR KEY IS NOW REACHED. That key's remedy shape
# has two halves — anchor the default, and print the store path on an empty
# result — and only the first was covered. FR-015 adds the second at
# `factory/cli/nouns/build.py:1554`. All four keys stay declared.
#
# ALSO: trap 4 now separates the cwd-relative fixtures that must change from 043's
# split-state, legacy-only, explicit-`--db` and no-literal-defaults assertions
# that must survive; three further test files that turn on the old contract are
# named; US2-S1 is labelled the control it is; and the plan's `prepare_worktree`
# adjacency claim, trap 5's citation and trap 2's branch description are
# corrected.
#
# REPAIRED AGAIN 2026-09-04 (refinement-2026-09-04, second adversarial pass).
# The first repair rewrote spec.md and plan.md and never re-opened tasks.md, so
# every requirement it added lived in two documents and not in the one the node's
# prompt slice is cut from. Six corrections, each re-derived from the tree at
# 602a92c:
#
# THE GATE WAS RED AND THE PRODUCER'S GREEN RUN PREDATED THE LAST EDIT. The
# symbol tier resolves `FunctionDef` / `AsyncFunctionDef` / `ClassDef` only
# (`_symbol_spans`, `factory/cli/nouns/spec.py:825`), so a module constant cited
# in the `` `path.py:NN` — `symbol` `` form is refused on sight. plan.md's Sizing
# now cites the two `diffbounds` constants coarsely — and cites the right one:
# the 64 KiB *refusal* is `DIFF_REFUSAL_THRESHOLD` (`factory/verify/diffbounds.py:66`),
# not `DIFF_INPUT_LIMIT` (`factory/verify/diffbounds.py:47`), which is the
# judge's attention allowance the threshold merely defaults to.
#
# TASKS.MD IS REWRITTEN AND IS NOW THE SAME DOCUMENT AS THE OTHER TWO. It carries
# FR-013, FR-014 and FR-015, the four scenarios that had no task (US1-S7,
# US2-S6, US2-S7, US2-S8), the retarget ruling in place of T007's wholesale
# rewrite, the corrected `prepare_worktree` adjacency, and the symbol-tier
# citation form on every Python anchor that names a symbol — the file the node
# reads was the one file whose drift nothing would have caught.
#
# US2'S DERIVATION LIST WAS SHORT BY THREE, AND THE MISSING THREE ARE THE
# REPRODUCTION. The operator key's own notes say "any read verb run from a node
# worktree" and give `ergane build answer` as the repro; `_store_path`
# (`factory/cli/nouns/answer.py:96`) was named nowhere, nor was
# `_verification_store_path` (`factory/cli/status.py:690`), nor
# `factory/notify/service.py:1049`, which reads the legacy variable directly and
# consults `resolve_env_path` not at all. Trap 13 forbids fixing this at the
# constant, so the enumeration *is* the scope: FR-004, US2-S2, US2-S9 and the
# tasks now name all six modules. Without this the spec half-fixed the key it
# declares.
#
# THE RELATIVE-OVERRIDE ANCHOR WAS AIMED AT THE WRONG FUNCTION. T009 sent the
# implementer into `resolve_env_path` (`factory/env.py:47`), a generic two-name
# helper with fifteen call sites of which three are runtime-root reads; the other
# twelve resolve the config path, the state home, the repo registry, the ledger
# and the verification store. Anchoring there re-anchors every relative override
# in the product and silently breaks `runtime_root_prefixes`
# (`factory/verify/diffcheck.py:287`), which reads a relative override *because*
# it is relative. FR-002 now forbids that site by name and the work moves into
# `resolve_factory_root`.
#
# THE RESET PATH IS A FOURTH BLIND RUNTIME-ROOT READ. `_reset_epic`
# (`factory/cli/nouns/build.py:1826`) resolves the root at
# `factory/cli/nouns/build.py:1888` while holding `graph.target_repo` five lines
# below it. FR-010 and US4-S4 now cover it.
#
# ONE ARTIFACT THIS REPAIR COULD NOT TOUCH, AND THE OPERATOR MUST.
# `workgraph.json` in this directory is a stale pre-refinement compile (three
# nodes, no US4, `requirement_keys` stopping at FR-008, and `us3.depends_on_merged`
# reading `["us2"]` where the Work Graph below declares US1 plus
# `concurrent_with: [US2]`). The roadmap re-derives from git, but
# `ergane build start` and `build reset` read that file off disk
# (`factory/cli/nouns/build.py:1644`). **Before the flip to `ready`, delete it or
# re-derive it with `ergane spec derive` — otherwise a manual dispatch silently
# builds the pre-refinement spec.** This pass was scoped to spec.md, plan.md and
# tasks.md and could not do it.
#
# REPAIRED A THIRD TIME 2026-09-04 (refinement-2026-09-04, third adversarial
# pass): US3 was handed an impossible requirement, the landing and salvage paths
# were missed entirely, US2 was sized against a guess, and a `fixes:` key was
# reached only halfway. Every claim below re-derived at 602a92c.
#
# WHAT IT COST, MEASURED. Round-1 F6 is the only defect to survive two full
# hand-over rounds — graded "still open" on 2026-08-28 and again on 2026-09-03 —
# so its cost is two rounds of fixes that did not reach it. The C-32 ledger row
# measures 4.2 GB of per-node agent HOMEs for eight epics written into
# `~/.local/share/uv/tools/ergane-cli/lib/python3.13/site-packages/.ergane/homes/`,
# one `uv tool upgrade` away from destruction. The operator row measures the
# other half: on 2026-08-30 a store read from a node worktree produced a false
# second confirmation that no question row existed, sent the 100/us2 park
# diagnosis to a wrong mechanism, and cost a finding that had to be withdrawn.
#
# US3 COULD NOT SATISFY BOTH THE REQUIREMENTS IT WAS GIVEN. FR-007 told
# `runtime_root_for` (`factory/cli/repo.py:418`) to reach its name choice
# "through the single shared resolver"; FR-011 and US3-S4 told it to stay
# environment-blind and keep returning a child of the repository, because
# `--clean-runtime` deletes what it returns. `resolve_factory_root` returns the
# override *first* (`factory/workgraph/worktree.py:211-216`) and US1 changed
# nothing about that, so no environment-blind entry point existed to call — while
# tasks.md forbade US3 from editing `factory/workgraph/worktree.py` to write one.
# All three of the implementer's exits were failures the plan itself names.
# FR-016 is new and makes the missing entry point US1's declared work: an
# environment-blind, repository-anchored name choice — `.ergane/` wins, a lone
# `.factory/` is honoured, neither means `.ergane/` — lifted out of
# `factory/workgraph/worktree.py:218-240` and called by name from FR-007.
#
# THE LANDING AND SALVAGE PATHS WERE MISSED, AND FR-009 WOULD HAVE STOPPED THEM.
# FR-010 enumerated the dispatch path, the two preflights and the reset path.
# `grep -rn "resolve_factory_root\|factory_root()" factory/` finds five more
# worker reads nobody had counted: `factory/activities/merge_activities.py:464`
# and `:602` pass `request.target_repo` on the line *above* a blind
# `resolve_factory_root(FACTORY_ROOT_ENV)[0]`; `factory/activities/agent_activities.py:861`
# and `:893` do the same from inputs that carry `target_repo`; and
# `factory/activities/agent_activities.py:796`, `:807` and `:822` plus
# `factory/activities/merge_activities.py:349` read blind from inputs that carry
# no repository at all. In a wheel install every one of them refuses the moment
# US1 merges. Worse than the refusal is the arm where a clone *is* discoverable
# from the wrong cwd: the dispatch path creates the worktree under
# `request.target_repo` while salvage looks for it under another root — verbatim
# the `WORKTREE_FAILED` and `[Errno 2] No such file or directory:
# /opt/ergane/.ergane/worktrees/...` shape in the C-23 row's own notes. FR-010
# now names all nine repository-holding reads and FR-018 is new for the four that
# hold none.
#
# ONE KEY WAS REACHED ONLY HALFWAY, AND IT IS THE ONE THAT SAYS SO ITSELF. The
# `worktree_path` key's remedy is two conjuncts: "make the path absolute at
# construction **and** audit the other `worktree_path` call sites -- salvage()
# and friends have the same shape". Nothing audited a single consumer. All ten
# take the root as an argument (`factory/workgraph/preflight.py:598` and nine
# inside `factory/workgraph/worktree.py`), so the audit *is* the enumeration of
# who supplies that argument — `ensure`, `salvage`, `push_branch`,
# `record_salvage_ref`, `mirror_node_branch`, `sync_with_target`, `reset`,
# `archive_and_clear_remote_branch`, `remove` and the preflight — and FR-010 plus
# FR-018 now carry it, story by story, in US4. The key stays declared because it
# is now reached whole.
#
# US2 WAS SIZED AGAINST A GUESS AND SPLIT 4 → 5. "Roughly 20–26 KB ... well
# inside the threshold" was a per-file estimate. Measured on this repository's own
# landed stories, `git show --format='' <sha> | wc -c`: 1027a05 is 63,932 B for
# 975 insertions — 1.6 KB under `DIFF_REFUSAL_THRESHOLD` — and 602a92c is
# 52,840 B for 906 changed lines, so this tree runs 55–75 diff bytes per changed
# line. US2 as written was ten production files, five FRs and nine scenarios:
# 39–65 KB, straddling the refusal, and its own plan told the implementer not to
# plan for a split. US5 is new and takes the operator-facing half — the four
# `_verification_store_path` / `_store_path` derivations, the three ledger
# derivations and the empty-result disclosure (FR-015, FR-017). Landed numbers
# are untouched; every existing story keeps its number.
#
# ALSO IN THIS PASS: the shared store helper now has a declared home
# (`factory/stores.py`, FR-004) instead of two forbidden ones; FR-013 says it
# follows the *pattern* of `_resolve_store_path` in that helper and states that
# `factory/doctor/cli.py` is out of scope, with the consequence named; US1-S7
# became an obligation on T007/T008 rather than a scenario a test-only diff could
# satisfy; the `resolve_env_path` count is corrected to three of fifteen
# (`factory/workgraph/worktree.py:211`, `factory/verify/diffcheck.py:304` and
# `factory/cli/nouns/build.py:1888`); `override.parts[0]` is cited at
# `factory/verify/diffcheck.py:305-306` rather than at :304; the second repair
# block's "three lines below" for the reset path is corrected to five; and the
# unit file's `WorkingDirectory` is now explicitly disclaimed rather than left
# silent. The stale `workgraph.json` is still on disk and still the operator's to
# clear — this pass was scoped to the three markdown files and could not.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04): a fourth adversarial pass refuted
# the trio on two blocking defects. Both were the same shape — an enumeration
# called closed that was not — and both are re-derived below at 602a92c.
#
# THE DECLARED KEY'S MEASURED HARM WAS OUTSIDE EVERY FR. C-32 measures 4.2 GB of
# per-node agent HOMEs under site-packages, and nothing in FR-001, FR-003,
# FR-010 or FR-018 reaches the code that creates them. `home_path`
# (`factory/workgraph/adapter.py:815` — `home_path`) is called with the relative
# `DEFAULT_FACTORY_ROOT` in the **workflow** (`factory/workgraph/workflow.py:1893`
# and `factory/workgraph/workflow.py:3985`), and the adapter mkdirs that relative
# string at `factory/workgraph/adapter.py:1060` and exports it as `HOME` at
# `factory/workgraph/adapter.py:971`. That call is not a `resolve_factory_root` or
# `factory_root()` read, so the grep the plan called "the whole enumeration"
# structurally cannot see it: all five stories could have landed green while the
# 4.2 GB kept accruing. The ledger row blames `factory_root()` and the spec
# inherited that diagnosis without re-deriving it. FR-020 and US4-S9 are new and
# put the derivation where the absolute root already exists — beside the
# `replace(context, session_id=...)` at `factory/activities/agent_activities.py:513`,
# whose own comment states the replay reasoning. The key stays declared because
# it is now reached whole.
#
# FR-009'S REFUSAL REACHED SEVEN OPERATOR VERBS NOBODY HAD COUNTED, AND WOULD
# HAVE TURNED THE SUITE RED AT US1'S OWN MERGE. The same grep returns twenty-two
# read sites, not thirteen: eight are operator paths — `ergane findings`,
# `ergane doctor`, `ergane spec validate` and `ergane repo migrate-runtime-root`
# — and trap 13 told the implementer of four of exactly those modules that "none
# of those should change". Three of the five doctor tests in
# `tests/test_runtime_root_findings.py` (`:135`, `:153`, `:179`) and 043's five
# migrate-verb tests (`tests/test_runtime_root.py:253-378`) run with both root
# variables deleted in a non-repository temporary directory and would have hit
# the refusal — and `tests/test_runtime_root_findings.py:64-73` is an **autouse**
# fixture, so the whole file is in that state. FR-019 is new, enumerates all
# seven, rules each one onto FR-014's fallback, and names the eighth
# (`_override_disagreement`) as unaffected by construction. US1's sizing now
# carries the five extra modules and the two test files nobody had named.
#
# ALSO IN THIS PASS: FR-006 says which value comes from which function after
# FR-007 re-points `resolve_repo_runtime_root` (the reported root from the shared
# resolver, the repository-relative name and `is_legacy` from the blind entry
# point) instead of leaving the split for the implementer to invent; US2-S1 no
# longer asks a test to call the Telegram bridge's read inside `main`, which
# connects to Temporal — it names the two callable derivations and the shared
# helper, and US2-S6 keeps the bridge by source assertion; US4-S10 is new for an
# `AttemptContext` whose `target_repo` is the empty default; FR-013 and "What
# this spec is not" narrow "`factory/doctor/cli.py` is out of scope" to the one
# function it means; and plan.md's `worktree_path` table, trap 16's site count
# and trap 18's misattributed quote are corrected. The stale `workgraph.json`
# is still on disk and still the operator's to clear before the flip — this pass
# was scoped to the three markdown files and could not.
---

# Feature Specification: the runtime root is one absolute path, whoever asks

**Created**: 2026-09-03
**Depends on**: nothing.

## The gap, stated precisely

`DEFAULT_RUNTIME_ROOT = Path(".ergane")` (`factory/workgraph/worktree.py:93`) is a
**relative** path, and `resolve_factory_root`
(`factory/workgraph/worktree.py:191` — `resolve_factory_root`) returns it relative
on the paths that matter. Every consumer therefore resolves the runtime root
against **its own process's current working directory**, and the factory's
processes do not share one:

1. The worker's `WorkingDirectory` is the install root
   (`factory/supervision/units.py:593` — `_service_text`), which is site-packages
   in a wheel install; the versioned template overrides it with the deployment
   tree, which is not the target repository either.
2. The CLI's cwd is wherever the operator is standing.
3. A gate or an agent runs with its cwd inside a worktree.

Three consequences, each already filed as its own finding, each looking unrelated
to the others:

4. **Agent homes land in the installed package directory.** The no-override path
   at `factory/workgraph/worktree.py:239` — reached only when *neither*
   `.ergane/` nor `.factory/` exists — calls
   `new.mkdir(parents=True, exist_ok=True)`, so a read of the root *creates* it,
   wherever the caller happens to be standing. The worker reaches that line
   through `factory_root` (`factory/activities/agent_activities.py:188` —
   `factory_root`), whose own docstring still says "Relative by default".
5. **A prepared worktree path is handed onward still relative.** `worktree_path`
   (`factory/workgraph/worktree.py:289` — `worktree_path`) joins whatever root it
   is handed, so a relative root makes a relative worktree path and every
   consumer resolves it against a cwd that is not the one it was computed in.
6. **A verification store read from a worktree is silently empty** — not an error,
   an empty result, which is the worst shape a wrong answer can take. And the
   mechanism is worse than "the root is relative": the store default is not
   derived from the root at all. `DEFAULT_VERIFICATION_DB_PATH` is the literal
   `".factory/verification.db"` (`factory/activities/verify_activities.py:128`),
   and `DEFAULT_LEDGER_PATH` is `".factory/ledger.db"` in three separate modules
   (`factory/activities/usage_activities.py:99`, `factory/usage/cli.py:30`,
   `factory/cli/usage.py:26`). All five name the *legacy* directory, which the
   resolver no longer prefers, and none of them consults it.
7. **And that literal is read in six modules, not two.** The two the worker uses
   are `_store_path` (`factory/activities/verify_activities.py:634` —
   `_store_path`) and `_store_path`
   (`factory/activities/notify_activities.py:770` — `_store_path`). The four the
   *operator* uses are the ones the filed finding was actually reported against —
   its notes say "any read verb run from a node worktree" and name
   `ergane build answer` as the reproduction: `_verification_store_path`, defined
   **twice** in one module (`factory/cli/nouns/build.py:1484` —
   `_verification_store_path` and `factory/cli/nouns/build.py:1534` —
   `_verification_store_path`), `_verification_store_path`
   (`factory/cli/status.py:690` — `_verification_store_path`), `_store_path`
   (`factory/cli/nouns/answer.py:96` — `_store_path`), and the Telegram bridge's
   entry point — `factory/notify/service.py:1049`, inside `main`
   (`factory/notify/service.py:1029` — `main`) — which reads
   `os.environ.get(VERIFICATION_DB_PATH_ENV) or DEFAULT_VERIFICATION_DB_PATH` and
   so consults `resolve_env_path` not at all, honouring only the *legacy*
   variable name (`factory/activities/verify_activities.py:130`). A fix that
   reaches four of the six leaves the reproduction alive.
8. **Which is why deriving the store from the root is not, by itself, safe.**
   A repository can hold both names, and this one does. With every override unset
   the resolver returns `.ergane/` (`factory/workgraph/worktree.py:224-230` — new
   wins when both exist) while the populated stores are `.factory/verification.db`
   (11,857,920 bytes) and `.factory/ledger.db` (565,248 bytes) and the `.ergane/`
   copies are 0 bytes. 043 already met this and landed a rule for it —
   `_resolve_store_path` (`factory/doctor/cli.py:58` — `_resolve_store_path`) —
   but that rule follows *existence*, and a 0-byte file exists: it answers the
   stale 28,672-byte `.ergane/doctor.db` beside the live 126,267,392-byte
   `.factory/doctor.db` today.
9. **And thirteen worker reads take the root blind, on three different paths of
   one node's life.** `grep -rn "resolve_factory_root\|factory_root()" factory/`
   answers with twenty-two read sites. Thirteen of them are the worker's: the
   dispatch path (`factory/activities/agent_activities.py:420`
   and `factory/activities/agent_activities.py:498`), the two dispatch preflights
   (`factory/cli/nouns/build.py:367` — `_preflight_factory_root` and
   `factory/activities/roadmap_activities.py:670` — `_preflight_factory_root`),
   the reset path (`factory/cli/nouns/build.py:1888`), the **landing** path
   (`factory/activities/merge_activities.py:464` and
   `factory/activities/merge_activities.py:602`, each one line below a
   `request.target_repo` the same call already passes, plus
   `factory/activities/merge_activities.py:349` — `_landing_body_dir`), the
   **salvage** path (`factory/activities/agent_activities.py:796`,
   `factory/activities/agent_activities.py:807` and
   `factory/activities/agent_activities.py:822`) and the sweep path
   (`factory/activities/agent_activities.py:861` and
   `factory/activities/agent_activities.py:893`). Nine of the thirteen sit in a
   call that is already holding the repository. Four are not: `SalvageWorktreeInput`
   (`factory/activities/agent_activities.py:745` — `SalvageWorktreeInput`) and
   `PrepareLandingPrInput` (`factory/activities/merge_activities.py:112` —
   `PrepareLandingPrInput`) carry no `target_repo` at all. **These are one node's
   lifecycle**: `ensure` (`factory/workgraph/worktree.py:362` — `ensure`) creates
   the worktree under the root the dispatch read, and `salvage`
   (`factory/workgraph/worktree.py:511` — `salvage`) looks for it under the root
   the salvage activity read. Make those two roots disagree and the second half of
   every node fails on a missing directory.
10. **Eight of the other nine reads are operator verbs, and they hold no
   repository either.** `_store_path` (`factory/cli/doctor.py:65` —
   `_store_path`) at `factory/cli/doctor.py:69`, `_store_path`
   (`factory/doctor/cli.py:50` — `_store_path`) at `factory/doctor/cli.py:54`,
   `_check_fixes` (`factory/cli/nouns/spec.py:1231` — `_check_fixes`) at
   `factory/cli/nouns/spec.py:1257`, `_evidence_stores`
   (`factory/doctor/probes.py:147` — `_evidence_stores`) at
   `factory/doctor/probes.py:148`, the two `_gather_async` reads at
   `factory/doctor/probes.py:285` and `factory/doctor/probes.py:393`, and
   `migrate_runtime_root_command` (`factory/cli/repo.py:613` —
   `migrate_runtime_root_command`) at `factory/cli/repo.py:624`. These are
   `ergane findings`, `ergane doctor`, `ergane spec validate` and
   `ergane repo migrate-runtime-root`. The eighth, `_override_disagreement`
   (`factory/cli/repo.py:455` — `_override_disagreement`) at
   `factory/cli/repo.py:473`, is unreachable without an override because it
   returns first at `factory/cli/repo.py:471`. A refusal that reaches the seven
   takes the committed suite with it: `tests/test_runtime_root_findings.py:64-73`
   is an **autouse** fixture that deletes both root variables and chdirs every
   test in the file into a non-repository temporary directory, and 043's five
   migrate-verb tests (`tests/test_runtime_root.py:253-378`) do the same by hand.
   The twenty-second read is `factory_root`'s own delegate at
   `factory/activities/agent_activities.py:195`.
11. **And that grep is not the whole enumeration, which is why the harm the
   ledger actually measured is not in it.** The C-32 row measures 4.2 GB of
   per-node agent HOMEs under site-packages, and no `resolve_factory_root` or
   `factory_root()` read produces them. `home_path`
   (`factory/workgraph/adapter.py:815` — `home_path`) is called with the relative
   `DEFAULT_FACTORY_ROOT` (`factory/workgraph/worktree.py:99`, an alias of
   `Path(".ergane")` at `factory/workgraph/worktree.py:93`) in the **workflow** —
   `factory/workgraph/workflow.py:1893` and `factory/workgraph/workflow.py:3985`,
   each holding `graph.target_repo` seven lines below
   (`factory/workgraph/workflow.py:1900`, `factory/workgraph/workflow.py:3992`) —
   and the adapter turns that relative string into a directory at
   `factory/workgraph/adapter.py:1060` and exports it as `HOME` at
   `factory/workgraph/adapter.py:971`, both against the worker's own working
   directory. `grep -rn "DEFAULT_FACTORY_ROOT\|DEFAULT_RUNTIME_ROOT" factory/` is
   the search that finds it, and nothing in this spec's first four passes ran it.

**And the overrides do not save you.** `factory/env.py:79` and
`factory/env.py:88` — both inside `resolve_env_path` (`factory/env.py:47` —
`resolve_env_path`) — return `Path(value)` with **no** `.resolve()`, so
`ERGANE_ROOT=.ergane` is exactly as cwd-dependent as no override at all. That
function is the diagnosis and not the fix site: it is a generic two-name env
helper with fifteen call sites, of which only three read the runtime root —
`factory/workgraph/worktree.py:211`, `factory/verify/diffcheck.py:304` and the
reset path's own read at `factory/cli/nouns/build.py:1888`. The second of those
*wants* the relative form, because `runtime_root_prefixes`
(`factory/verify/diffcheck.py:287` — `runtime_root_prefixes`) skips any override
that is already absolute and takes `override.parts[0]`
(`factory/verify/diffcheck.py:305-306`). Nothing in `factory/supervision/` sets
any of these variables: `grep -rn ERGANE_ROOT factory/supervision/` returns
**zero** matches, and the only `Environment=` line the unit generator emits is the
build id.

**Two subsystems have already worked around it**, each with its own repo-anchored
resolver and each explaining in a comment that it cannot use the shared one:
`resolve_repo_runtime_root` (`factory/cli/init.py:2088` —
`resolve_repo_runtime_root`) and `runtime_root_for` (`factory/cli/repo.py:418` —
`runtime_root_for`). So the tree currently holds three answers to "where is the
runtime root", and the one the engine uses is the one that is wrong.

## The rule this spec is asking for

**The runtime root resolves to an absolute path anchored on the repository that
owns it — the owning clone, named by the caller or discovered from git, never the
calling process's working directory — and when no such repository can be
established the resolver refuses instead of answering from wherever it is
standing.**

The inputs combine, so the whole of the rule is this table:

| Override | Caller names a repository | Owning clone discoverable from cwd | The resolver returns |
| --- | --- | --- | --- |
| absolute | either | either | the override, unchanged |
| relative | yes | either | the override joined to the named repository, absolute |
| relative | no | yes | the override joined to the owning clone, absolute |
| relative | no | no | a refusal naming the variable and its value |
| none | yes | either | the chosen name under the named repository, absolute |
| none | no | yes | the chosen name under the owning clone, absolute |
| none | no | no | a refusal naming what it was asked |

No row creates a directory. "The chosen name" is 043's existing precedence,
unchanged: `.ergane/` wins, a lone `.factory/` is honoured, neither means
`.ergane/`. That name choice is also callable on its own, without consulting the
environment, because two callers need the name of a repository they are not
standing in and one of them deletes what it is told (FR-016, FR-011).

A store default derived from that root has one extra rule of its own, because the
name the resolver chooses and the name the data is under can differ:

| Store file under the resolved root | Store file under the other runtime-root name | The reader opens |
| --- | --- | --- |
| has content | either | the one under the resolved root |
| absent or 0 bytes | has content | the populated one, unmoved |
| absent or 0 bytes | absent or 0 bytes | the one under the resolved root |

### What this spec is not

It is not the removal of the overrides. `ERGANE_ROOT` and `FACTORY_ROOT` keep
winning over the default; what changes is that a *relative* override is anchored
on the same repository the default is anchored on, so setting one relatively stops
being a trap.

It is not a change to `resolve_env_path` (`factory/env.py:47` —
`resolve_env_path`). That helper answers "which of these two variable names is
set, and what does it say" for fifteen paths, twelve of which are not the runtime
root — the control-plane config file, the engine state home, the repo registry,
the ledger, the verification store. Anchoring inside it would re-anchor all
fifteen, and it would break `runtime_root_prefixes`
(`factory/verify/diffcheck.py:287` — `runtime_root_prefixes`), whose whole job is
to read a *relative* override's first path segment. FR-002's anchoring happens
where a repository is available, in the runtime-root resolver, applied to the
value that helper returns.

It is not a change to the worker unit. `factory/supervision/units.py:593` —
`_service_text` keeps emitting `WorkingDirectory={layout.install_root}`. The
C-32 row's remedy offers two conjuncts and the second — "the worker unit should
set `WorkingDirectory=`" — is deliberately not taken, because after FR-001 and
FR-010 no runtime root depends on the process's directory and setting one would
re-establish exactly the dependence this spec removes. The key is closed at the
resolver rather than at the unit.

It is not a relocation. No store's contents move on disk. That is a stronger
promise than "the resolved directory does not change", and it has to be, because
in this repository the resolved directory *will* change for a reader that unsets
`ERGANE_ROOT`: the resolver answers `.ergane/` while the populated stores sit
under `.factory/`. FR-013 is what keeps that from becoming a silent swap.

It is not a change to `_resolve_store_path` (`factory/doctor/cli.py:58` —
`_resolve_store_path`). That is 043's landed rule and the *pattern* FR-013
follows; it is not edited, and its committed contract tests keep passing
unchanged. FR-019 does add the refusal fallback one function above it, to
`_store_path` (`factory/doctor/cli.py:50` — `_store_path`), which changes no
answer this rule gives — it only keeps FR-009 from reaching a reader that holds
no repository. The consequence is stated rather than hidden: after this
spec `ergane findings` still opens whichever doctor store *exists* first, which on
this host is the stale 28,672 B `.ergane/doctor.db` beside the live
126,267,392 B `.factory/doctor.db`. Strengthening that rule from existence to
content is a separate change against a separate landed spec's guarantees.

It is not a change to the legacy-name reconciliation. The `.factory` / `.ergane`
choice 043 built keeps its behaviour and its precedence.

It is not a change to what `--clean-runtime` deletes. `runtime_root_for` stays
environment-blind, for the reason written in its own docstring.

It is not a change to the workflow. `factory/workgraph/workflow.py:1893` and
`factory/workgraph/workflow.py:3985` keep computing the per-node home the way
they do today, because a workflow cannot resolve a runtime root without I/O and
joining `graph.target_repo` to a hard-coded `.ergane` there would answer wrongly
for a repository holding only `.factory/`. FR-020 moves the derivation to the
activity that already holds the resolved absolute root, and leaves the workflow's
value in place so an in-flight epic's replay still deserialises.

It is not the threading of a repository into the verification and escalation
activity inputs. `RecordVerificationInput`
(`factory/activities/verify_activities.py:467` — `RecordVerificationInput`) carries
`result` and `criteria_source_path` and nothing else, and `target_repo` appears
zero times in either store module. Those readers take FR-014's fallback, which
means a wheel-installed worker standing in no clone still resolves its store the
way it does today and the operator's overrides remain the answer there. That half
of the verification-store finding stays open; the half it was filed against — an
operator standing in a node worktree, where an owning clone *is* discoverable —
is closed by FR-004, FR-013, FR-015 and FR-017. The salvage and landing inputs
are a different matter and are **in** scope: FR-018 covers them, because there a
disagreeing root is not a wrong store but a missing worktree.

## User Scenarios & Testing

### User Story 1 - The root is absolute and anchored on its repository (Priority: P1)

As an operator, the runtime root is the same directory whether the worker, the CLI
or a gate is asking.

**Why this priority**: P1 and it depends on nothing. Every other story reads the
answer this one corrects. It is also the story that removes the mandatory
overrides, which is what makes the defect stop being invisible. FR-019 rides with
it rather than trailing behind it: FR-009's refusal reaches seven operator verbs
the moment this story merges, so the story that introduces the refusal is the
story that must decide them.

**Independent Test**: Resolve the root from three different working directories
with no environment set, and compare the three answers.

**Acceptance Scenarios**:

1. **Given** a repository, no runtime-root override — both `ERGANE_ROOT` and
   `FACTORY_ROOT` deleted by the test, because the suite's session fixture sets
   them — and a caller that names that repository, **When** the root is resolved
   from the repository root, from a subdirectory of it, and from a directory
   outside it, **Then** all three calls return the identical absolute path under
   that repository, proven by a committed test that changes the working directory
   between the three calls.
2. **Given** a relative override such as `ERGANE_ROOT=.ergane` and a named
   repository, **When** the root is resolved from a working directory that is not
   that repository, **Then** the answer is the named repository's `.ergane`, not
   the working directory's, and the anchoring is done by the runtime-root resolver
   rather than by `resolve_env_path` (`factory/env.py:47` — `resolve_env_path`) —
   proven by one committed test that asserts the full path and a second that
   asserts `runtime_root_prefixes` (`factory/verify/diffcheck.py:287` —
   `runtime_root_prefixes`) still returns the relative override's first segment,
   which it cannot if the helper started resolving.
3. **The control.** **Given** an absolute override, **When** the root is resolved,
   **Then** it is returned unchanged and still wins over the repository-anchored
   default, proven by a committed test; this story removes no operator control.
4. **Given** a repository whose runtime root does not yet exist, **When** the root
   is merely *read*, **Then** the repository's directory listing is unchanged in
   the assertion that follows the read, and a separate explicit ensure call does
   create it — both proven by one committed test, because a read that creates is
   how a wrong cwd becomes a multi-gigabyte directory in site-packages.
5. **Given** no override, no repository named by the caller, and a working
   directory inside no git repository, **When** the root is resolved, **Then** the
   resolver refuses with a message naming what it was asked, and the temporary
   directory still contains no `.ergane`, proven by a committed test.
6. **Given** a working directory inside a linked git worktree of the repository,
   **When** the root is resolved with no repository named by the caller, **Then**
   the answer is the owning clone's root rather than the worktree's, proven by a
   committed test that creates a real linked worktree — because `git rev-parse
   --show-toplevel` answers the worktree, and anchoring there recreates the
   empty-store defect this spec exists to close.
7. **Given** an `ERGANE_ROOT` set to a directory outside the repository and a
   repository holding only a legacy `.factory/`, **When** the **name choice** is
   asked for that repository on its own, **Then** it answers that repository's
   `.factory` — the override is not consulted, the answer is a child of the
   repository by construction, and no directory is created — proven by one
   committed test covering all three of the precedence arms (`.ergane/` wins, a
   lone `.factory/` is honoured, neither means `.ergane/`). This is the entry
   point `runtime_root_for` (`factory/cli/repo.py:418` — `runtime_root_for`)
   needs and cannot get from the resolver, whose first act is to return the
   override (`factory/workgraph/worktree.py:211-216`).
8. **Given** each of the seven operator reads FR-019 names, and a process
   standing in a directory inside no git repository with both root variables
   deleted, **When** each verb resolves its runtime root, **Then** it answers the
   process-relative name choice and creates nothing, rather than raising FR-009's
   refusal — proven by a committed test naming all seven and by 043's own
   committed tests still passing: `tests/test_runtime_root_findings.py:135`,
   `tests/test_runtime_root_findings.py:153` and
   `tests/test_runtime_root_findings.py:179` run under the autouse `_chdir_tmp`
   fixture (`tests/test_runtime_root_findings.py:64-73`), and the migrate-verb
   tests at `tests/test_runtime_root.py:253-378` unset the variables by hand.

### User Story 2 - The worker's store default is derived once, and follows the data (Priority: P2)

As an operator, a verification store written by the worker is the store the worker
reads, from anywhere, and deriving it from the root does not orphan what is
already on disk.

**Why this priority**: P2 and it reads US1's answer. An absolute root whose
derived paths are still relative fixes the resolver and none of the three filed
consequences. This story writes the one shared helper US5 then calls.

**Independent Test**: Derive the verification store path from a changed cwd, with
no override, and read what it points at.

**Acceptance Scenarios**:

1. **Given** a test that has deleted `ERGANE_VERIFICATION_DB_PATH` and
   `FACTORY_VERIFICATION_DB_PATH`, **When** the verification store path is derived
   through each of the three **worker-side** callables — `_store_path`
   (`factory/activities/verify_activities.py:634` — `_store_path`), `_store_path`
   (`factory/activities/notify_activities.py:770` — `_store_path`) and the shared
   helper FR-004 introduces, which is what the Telegram bridge reaches after this
   story — first from the repository and again from a directory inside a node
   worktree, **Then** all six answers are the same absolute file beneath the
   resolved runtime root rather than a `.factory/verification.db` beneath each
   caller, proven by one committed test that names all three and asserts no answer
   contains the worktree's own directory. The bridge's own line at
   `factory/notify/service.py:1049` is **not** callable from a test: it sits
   inside `main` (`factory/notify/service.py:1029` — `main`), which connects to
   Temporal and polls, so US2-S6 holds that line by asserting on the module's
   source instead.
2. **Given** the same two store variables deleted by the test, and rows written to
   the verification store by a process standing in the repository, **When** the
   store is opened by a process standing inside a node worktree, **Then** the
   written rows come back **and** the single file both processes opened is the one
   beneath the resolved runtime root, asserted by path in the same committed test
   — the row assertion alone would pass with an absolute override in force, which
   is the state every test in this suite starts in.
3. **The control.** **Given** a Python process in a directory inside no git
   repository, **When** it imports the shared store helper and the modules that
   define these store defaults, **Then** the import succeeds and no runtime root
   is resolved, proven by a committed test — because deriving a module-level
   constant from the resolver at import time turns US1's refusal into an import
   error for `ergane --help`.
4. **Given** a repository holding both runtime-root names, where the store under
   the resolved `.ergane/` is 0 bytes and the store under `.factory/` holds rows —
   the state `/home/admin/code/ergane` is in, measured on 2026-09-04 as
   `.factory/verification.db` 11,857,920 B against `.ergane/verification.db`
   0 B — **When** the store path is derived with no override by a process standing
   **inside a node worktree of that repository**, **Then** the reader opens the
   populated `.factory/` file and its rows come back, proven by a committed test
   that seeds both files and asserts on the row contents; an existence test alone
   fails this scenario, which is why 043's landed rule is followed as a pattern
   rather than called, and today the same call answers an absent
   `<worktree>/.factory/verification.db`.
5. **Given** a process whose working directory is inside no git repository and
   that names no repository, **When** a store reader derives its default, **Then**
   it falls back to today's process-relative default and returns a path rather
   than propagating the resolver's refusal, proven by a committed test — because
   `RecordVerificationInput` (`factory/activities/verify_activities.py:467` —
   `RecordVerificationInput`) carries no repository, so a refusal here would stop
   a wheel-installed worker recording any verification at all.
6. **Given** the Telegram bridge entry point, which today reads
   `os.environ.get(VERIFICATION_DB_PATH_ENV) or DEFAULT_VERIFICATION_DB_PATH` at
   `factory/notify/service.py:1049` inside `main`
   (`factory/notify/service.py:1029` — `main`) and so honours only the legacy
   variable and no resolver at all, **When** this story lands, **Then** it reaches
   its store through the same helper as the other two and a committed test asserts
   the module's source carries no direct read of that variable beside the relative
   literal — in the shape of
   `test_doctor_modules_do_not_carry_factory_literal_defaults`
   (`tests/test_runtime_root_findings.py:222` —
   `test_doctor_modules_do_not_carry_factory_literal_defaults`), which is how 043
   held the same line.
7. **The control.** **Given** 043's four committed contract tests —
   `tests/test_runtime_root_findings.py:153`,
   `tests/test_runtime_root_findings.py:179`,
   `tests/test_runtime_root_findings.py:199` and
   `tests/test_runtime_root_findings.py:222` — **When** this story lands, **Then**
   their assertions are unchanged in the committed diff, because `ergane findings`
   keeps 043's existence rule and this story's content rule lives only in the new
   shared helper.

### User Story 3 - One resolver, and the readiness check reports it (Priority: P3)

As an operator running the readiness check, the root it reports is the root the
engine will use.

**Why this priority**: P3. It is the smallest story and the one that makes the
other two verifiable by an operator rather than only by a test. It also retires
the two hand-rolled resolvers, which is the part that stops this defect recurring.

**Independent Test**: Run the readiness check in a repository where the engine's
root and the written root would differ, and read what it reports.

**Acceptance Scenarios**:

1. **Given** a repository and an `ERGANE_ROOT` naming a directory inside it under
   neither runtime-root name — the arm where `resolve_repo_runtime_root`'s own
   name choice and the engine's answer diverge — **When** the readiness check
   reports the runtime root, **Then** the value it reports is the one the shared
   resolver returns, obtained from that resolver rather than from a second name
   choice of the check's own, proven by a committed test asserting the two are
   equal in this arm; today `factory/cli/init.py:2249` — `gather_init_facts`
   derives the name from `resolve_repo_runtime_root` and consults no override, so
   a diff that leaves that second name choice standing fails this scenario even
   though the no-override arm already agrees.
2. **Given** the two repo-anchored resolvers that exist today, **When** this story
   is complete, **Then** both reach the repository-anchored name choice through
   the environment-blind entry point US1 landed for FR-016 rather than deriving it
   themselves, and a committed test asserts all three call sites return the same
   value for one repository with no override set.
3. **The control.** **Given** the shared resolver is asked for a root that does
   not exist, **When** any of the three call sites asks, **Then** none of them
   creates it, proven by a committed test that asserts the directory listing is
   unchanged — preserving the property both hand-rolled copies were written to
   obtain.
4. **The control.** **Given** an `ERGANE_ROOT` naming a directory outside the
   repository, **When** `runtime_root_for` is asked for that repository's runtime
   root, **Then** it still returns a child of that repository and the environment
   is not consulted, proven by a committed test — because `--clean-runtime`
   deletes what this function returns, and on 2026-08-14 this repository lost its
   whole runtime root to a process acting on a root it had been handed.
5. **Given** an `ERGANE_ROOT` naming a directory outside the repository, **When**
   the readiness check reports on the runtime root, **Then** it names that root and
   says it lies outside the repository, rather than reporting the repository's
   `.gitignore` as failing, proven by a committed test on the reported finding.
6. **Given** a repository being scaffolded, **When** `init` writes the
   `.gitignore`, **Then** the file carries ignore entries for **both** runtime-root
   names, proven by a committed test on the file's contents — init cannot know
   which name the engine will resolve, and a root that reaches git history lands
   megabytes of agent output on a landing branch.
7. **The control.** **Given** a repository holding only a legacy `.factory/`,
   **When** the shared resolver, the readiness check and `runtime_root_for` are
   each asked, **Then** all three still choose `.factory/` and no store's contents
   have moved, proven by a committed test that asserts the file listing before and
   after.

### User Story 4 - Every read on a node's lifecycle resolves one root (Priority: P2)

As an operator running a wheel-installed worker, a dispatch, its landing and its
salvage all resolve the runtime root of the repository the epic names, not of
whatever directory systemd started the process in.

**Why this priority**: P2, and it is what makes US1's refusal survivable rather
than merely loud. In a wheel install the worker's cwd is inside no clone, so after
US1 thirteen worker reads refuse unless the callers name the repository they
already hold, or fall back where they cannot. It also carries the audit the
`worktree_path` finding asks for by name, and the per-node agent HOME — the one
artifact the C-32 row actually measured, which no runtime-root read produces.

**Independent Test**: Call the dispatch, landing and salvage activities from a
working directory outside the target repository and read which root each used.

**Acceptance Scenarios**:

1. **Given** a worker process whose working directory is outside the target
   repository and no override set, **When** it prepares a worktree for an epic,
   **Then** the runtime root it uses is under `request.target_repo`, proven by a
   committed test that runs the activity from a temporary directory.
2. **Given** the same conditions, **When** the dispatch preflight reads the runtime
   root, **Then** it reads it for the repository the dispatch names rather than
   from the process's working directory, proven by a committed test covering both
   preflight readers.
3. **The control.** **Given** an absolute `ERGANE_ROOT`, **When** a dispatch
   resolves the runtime root, **Then** the override still wins over the repository
   the epic names, proven by a committed test — the anchor does not overrule an
   explicit operator choice.
4. **Given** a `build reset` run from a working directory outside the target
   repository with no override set, **When** `_reset_epic`
   (`factory/cli/nouns/build.py:1826` — `_reset_epic`) resolves the runtime root
   it will archive worktrees under, **Then** the root is under the graph's
   `target_repo`, proven by a committed test asserting the archived path lies
   inside that repository — today `factory/cli/nouns/build.py:1888` reads the
   root blind while `graph.target_repo` is in scope five lines below at
   `factory/cli/nouns/build.py:1893`, so a reset from the wrong directory
   archives nothing and reports success.
5. **Given** a worker process outside the target repository and no override,
   **When** the landing path pushes the node branch and syncs it with the target,
   **Then** both resolve the root of `request.target_repo`, proven by a committed
   test on both activities — today `factory/activities/merge_activities.py:464`
   and `factory/activities/merge_activities.py:602` each compute
   `worktrees.resolve_factory_root(FACTORY_ROOT_ENV)[0]` one line below the
   `request.target_repo` the same call already passes
   (`factory/activities/merge_activities.py:461` and
   `factory/activities/merge_activities.py:599`).
6. **Given** a node whose worktree was created by the dispatch path under
   `request.target_repo` and a process standing outside that repository with no
   override, **When** salvage runs — `salvage`
   (`factory/workgraph/worktree.py:511` — `salvage`), `record_salvage_ref`
   (`factory/workgraph/worktree.py:778` — `record_salvage_ref`) and
   `mirror_node_branch` (`factory/workgraph/worktree.py:855` —
   `mirror_node_branch`), reached from
   `factory/activities/agent_activities.py:796`,
   `factory/activities/agent_activities.py:807` and
   `factory/activities/agent_activities.py:822` — **Then** the path each computes
   is the directory the dispatch created and not a sibling under another root,
   proven by a committed test that creates the worktree through the dispatch path
   and asserts the salvage path equals it; today `SalvageWorktreeInput`
   (`factory/activities/agent_activities.py:745` — `SalvageWorktreeInput`) carries
   no repository, and a disagreement here is the `[Errno 2] No such file or
   directory: /opt/ergane/.ergane/worktrees/...` failure recorded in the
   `worktree_path` finding's own notes.
7. **The control.** **Given** a salvage input constructed without the repository —
   the payload shape an epic already in flight replays — **When** the activity
   resolves its root, **Then** it falls back to today's read and returns a path
   rather than raising FR-009's refusal, proven by a committed test that omits the
   field; a required new field on an activity input is a replay hazard for every
   in-flight epic, which is the reason `salvage_worktree`
   (`factory/activities/agent_activities.py:762` — `salvage_worktree`) states in
   its own docstring for keeping its payload narrow.
8. **The control.** **Given** an absolute runtime root, **When** a worktree path
   is derived from it by `worktree_path` (`factory/workgraph/worktree.py:289` —
   `worktree_path`), **Then** that path is absolute and names the same directory
   from two different working directories, proven by a committed test. All ten
   call sites take the root as an argument — `factory/workgraph/preflight.py:598`
   and nine inside `factory/workgraph/worktree.py` — so this is a regression guard
   on the derivation, and the audit the finding asks for is the enumeration of
   who supplies that argument, which is scenarios 1 through 7.
9. **Given** an `AttemptContext` carrying the relative `home_path` the workflow
   computes today — `home_path(DEFAULT_FACTORY_ROOT, ...)` at
   `factory/workgraph/workflow.py:1893` and `factory/workgraph/workflow.py:3985`
   — and a worker process whose working directory is outside the target
   repository with no override set, **When** the attempt's per-node HOME is
   created (`factory/workgraph/adapter.py:1060`, inside `run_attempt`,
   `factory/workgraph/adapter.py:1022` — `run_attempt`) and exported
   (`factory/workgraph/adapter.py:971`), **Then** the directory created is beneath
   the target repository's resolved runtime root and the process's own working
   directory gains no `.ergane`, proven by one committed test that asserts both
   paths after running the activity from a temporary directory. This is the
   4.2 GB the C-32 row measured; no `resolve_factory_root` read produces it, so
   scenarios 1 through 8 do not cover it.
10. **The control.** **Given** an `AttemptContext` whose `target_repo` is the
   empty default (`factory/workgraph/models.py:463`, `str = ""`, the value a
   payload predating the field replays with), **When** `run_agent_attempt`
   (`factory/activities/agent_activities.py:482` — `run_agent_attempt`) resolves
   its root at `factory/activities/agent_activities.py:498`, **Then** it falls
   back to today's read and returns a path rather than raising FR-009's refusal or
   anchoring on `Path("")`, proven by a committed test that constructs the context
   with the field left at its default.

### User Story 5 - The operator's read verbs open the same store, and say which (Priority: P3)

As an operator standing in a node worktree, `ergane build answer` and
`ergane status` open the store the worker wrote, and an empty answer names the
file it came from.

**Why this priority**: P3 and it reads US2's helper. These four derivations plus
the three ledger derivations are what the operator finding was actually filed
against — its notes name `ergane build answer` from a node worktree as the
reproduction — and the empty-result disclosure is the second half of its stated
remedy.

**Independent Test**: Run the two read verbs from inside a node worktree and read
which store path each names.

**Acceptance Scenarios**:

1. **Given** a test that has deleted `ERGANE_VERIFICATION_DB_PATH` and
   `FACTORY_VERIFICATION_DB_PATH`, **When** the verification store path is derived
   through each of the **operator-side** derivations — the winning
   `_verification_store_path` (`factory/cli/nouns/build.py:1534` —
   `_verification_store_path`), `_verification_store_path`
   (`factory/cli/status.py:690` — `_verification_store_path`) and `_store_path`
   (`factory/cli/nouns/answer.py:96` — `_store_path`) — first from the repository
   and again from a directory inside a node worktree, **Then** all six answers are
   the same absolute file beneath the resolved runtime root and none contains the
   worktree's own directory, proven by one committed test naming all three. These
   are what `ergane build answer` and `ergane status` reach.
2. **The control that catches the shadow.** **Given** the two byte-identical
   definitions of `_verification_store_path` in one module
   (`factory/cli/nouns/build.py:1484` — `_verification_store_path` and
   `factory/cli/nouns/build.py:1534` — `_verification_store_path`, the second
   winning), **When** each is called, **Then** both return the same absolute path,
   proven by a committed test that imports and calls them individually — editing
   only the first passes every CLI test and changes nothing.
3. **Given** `ERGANE_LEDGER_PATH` and `LEDGER_PATH` deleted by the test, **When**
   the ledger path is resolved through each of the three modules that define
   `DEFAULT_LEDGER_PATH` (`factory/activities/usage_activities.py:99`,
   `factory/usage/cli.py:30`, `factory/cli/usage.py:26`), **Then** all three
   return the same absolute file beneath the resolved runtime root, proven by one
   committed test that names all three call paths.
4. **Given** a read verb whose query returns no rows, **When** it reports that,
   **Then** the message names the absolute store file it opened alongside the
   count, proven by a committed test asserting the printed line contains that
   path — today `factory/cli/nouns/build.py:1554`, inside `_answer`
   (`factory/cli/nouns/build.py:1547` — `_answer`), prints only "no pending
   questions for epic", which is indistinguishable from a quiet floor.
5. **The control.** **Given** a process in a directory inside no git repository,
   **When** it runs the CLI's own help path and imports these six modules,
   **Then** the import succeeds, no runtime root is resolved and no refusal is
   raised, proven by a committed test — these modules are on `ergane --help`'s
   import path, so an import-time derivation breaks the CLI outside a clone.

## Functional Requirements

- **FR-001**: The runtime root MUST resolve to an absolute path anchored on the
  repository that owns it — the owning clone — with no dependence on the calling
  process's working directory, and MUST NOT anchor on a linked worktree of that
  repository.
- **FR-002**: A runtime-root override MUST continue to take precedence over the
  repository-anchored default, and a **relative** override MUST be anchored on the
  same repository the default is anchored on rather than on the calling process's
  working directory. That anchoring MUST happen in the runtime-root resolver,
  applied to the value `resolve_env_path` (`factory/env.py:47` —
  `resolve_env_path`) returns, and MUST NOT be added inside `resolve_env_path`
  itself: fifteen call sites share that helper and only three of them are
  runtime-root reads, and `runtime_root_prefixes`
  (`factory/verify/diffcheck.py:287` — `runtime_root_prefixes`) depends on
  receiving a relative override still relative.
- **FR-003**: Reading the runtime root MUST NOT create it. Creation MUST remain an
  explicit act of the verbs whose job is to create it.
- **FR-004**: The worker-side verification store default MUST be derived from the
  resolved runtime root rather than from its own relative literal —
  `DEFAULT_VERIFICATION_DB_PATH` (`factory/activities/verify_activities.py:128`),
  which names the legacy directory and consults no resolver today — and the
  derivation MUST live in **one** shared helper in a **new module**,
  `factory/stores.py`, which imports the runtime-root resolver and is imported by
  its callers and never the reverse. Neither `factory/workgraph/worktree.py` (US1's
  file) nor `factory/env.py` (FR-002) is that home. The worker-side derivations
  MUST call it: `_store_path` (`factory/activities/verify_activities.py:634` —
  `_store_path`), `_store_path` (`factory/activities/notify_activities.py:770` —
  `_store_path`) and the bridge's inline read at
  `factory/notify/service.py:1049`, which honours only the legacy variable name
  (`factory/activities/verify_activities.py:130`) and reaches no resolver at all.
- **FR-005**: A store written by a process in one working directory MUST be
  readable by a process in another, asserted by a test that changes the working
  directory between write and read and that deletes the store override variables
  the suite's session fixture sets.
- **FR-006**: The readiness check MUST report the runtime root the engine
  resolves, obtained from the shared resolver rather than from a name choice of
  its own, including when an override names a directory outside the repository.
- **FR-007**: `resolve_repo_runtime_root` (`factory/cli/init.py:2088` —
  `resolve_repo_runtime_root`) and `runtime_root_for` (`factory/cli/repo.py:418` —
  `runtime_root_for`) MUST reach the repository-anchored name choice through the
  environment-blind entry point FR-016 puts in `factory/workgraph/worktree.py`,
  rather than deriving it themselves or calling `resolve_factory_root`
  (`factory/workgraph/worktree.py:191` — `resolve_factory_root`), whose first act
  is to return the override; and a test MUST assert the call sites agree with no
  override set.
- **FR-008**: The `.factory` / `.ergane` legacy-name precedence MUST be unchanged,
  and no store's contents may be relocated.
- **FR-009**: When no repository is named by the caller and no owning clone can be
  discovered, the resolver MUST refuse with a message naming what it was asked,
  and MUST NOT answer from the process's working directory or create a directory
  there.
- **FR-010**: Every runtime-root read whose call already holds a repository MUST
  name it. There are nine: the dispatch path
  (`factory/activities/agent_activities.py:420` and
  `factory/activities/agent_activities.py:498`, which reaches it through
  `AttemptContext.target_repo`, `factory/workgraph/models.py:463`), the two
  dispatch preflights (`factory/cli/nouns/build.py:367` —
  `_preflight_factory_root` and `factory/activities/roadmap_activities.py:670` —
  `_preflight_factory_root`), the reset path `_reset_epic`
  (`factory/cli/nouns/build.py:1826` — `_reset_epic`), which holds
  `graph.target_repo` and today reads the root blind at
  `factory/cli/nouns/build.py:1888`, the landing path
  (`factory/activities/merge_activities.py:464` and
  `factory/activities/merge_activities.py:602`), and the sweep path
  (`factory/activities/agent_activities.py:861` and
  `factory/activities/agent_activities.py:893`, whose inputs
  `RemoveWorktreeInput`, `factory/activities/agent_activities.py:838` —
  `RemoveWorktreeInput`, and `ArchiveAndClearRemoteBranchInput`,
  `factory/activities/agent_activities.py:868` —
  `ArchiveAndClearRemoteBranchInput`, both already carry `target_repo`).
- **FR-011**: `runtime_root_for` MUST remain environment-blind and MUST keep
  returning a child of the repository it is asked about, because `--clean-runtime`
  deletes what it returns.
- **FR-012**: `init` MUST write ignore entries for **both** runtime-root names,
  because it cannot know which name the engine will later resolve.
- **FR-013**: The shared helper FR-004 introduces MUST open the populated file
  when the file under the resolved root is absent or empty and the file under the
  other runtime-root name holds content. It MUST follow the *pattern* of the rule
  043 landed as `_resolve_store_path` (`factory/doctor/cli.py:58` —
  `_resolve_store_path`), strengthened from existence to content because a 0-byte
  file exists, and MUST NOT edit that function: `factory/doctor/cli.py` is out of
  this spec's scope and its four committed contract tests
  (`tests/test_runtime_root_findings.py:153`,
  `tests/test_runtime_root_findings.py:179`,
  `tests/test_runtime_root_findings.py:199`,
  `tests/test_runtime_root_findings.py:222`) MUST pass unchanged. Nothing is
  copied or moved.
- **FR-014**: A store reader MUST NOT propagate FR-009's refusal. When no
  repository can be established it MUST fall back to the process-relative default
  it uses today, because `_store_path`
  (`factory/activities/verify_activities.py:634` — `_store_path`) and `_store_path`
  (`factory/activities/notify_activities.py:770` — `_store_path`) are handed no
  repository and cannot obtain one.
- **FR-015**: A read verb that returns no rows MUST name the absolute store file
  it opened, because an empty result and a wrong store are indistinguishable
  otherwise — `factory/cli/nouns/build.py:1554` prints neither today.
- **FR-016**: The runtime-root module MUST expose the name choice on its own, as
  an **environment-blind** function that takes a repository and returns a child of
  it — `.ergane/` wins, a lone `.factory/` is honoured, neither means `.ergane/`
  — creating nothing. That rule lives inside `resolve_factory_root` today
  (`factory/workgraph/worktree.py:218-240`) behind an override return
  (`factory/workgraph/worktree.py:211-216`) and is therefore unreachable by the
  two callers that need it, one of which deletes what it is told (FR-011).
  `resolve_factory_root`'s own behaviour, including its one-time legacy warning,
  MUST be unchanged.
- **FR-017**: The operator-side verification store derivations and the three
  `DEFAULT_LEDGER_PATH` derivations MUST reach the same shared helper FR-004
  introduces: both `_verification_store_path` definitions
  (`factory/cli/nouns/build.py:1484` and `factory/cli/nouns/build.py:1534`, the
  second shadowing the first, so editing one changes nothing),
  `_verification_store_path` (`factory/cli/status.py:690` —
  `_verification_store_path`), `_store_path` (`factory/cli/nouns/answer.py:96` —
  `_store_path`), and the ledger readers at
  `factory/activities/usage_activities.py:651`, `factory/usage/cli.py:145` and
  `factory/cli/usage.py:112`.
- **FR-018**: The runtime-root reads whose call holds **no** repository —
  `factory/activities/agent_activities.py:796`,
  `factory/activities/agent_activities.py:807` and
  `factory/activities/agent_activities.py:822`, reached from
  `SalvageWorktreeInput` (`factory/activities/agent_activities.py:745` —
  `SalvageWorktreeInput`), and `_landing_body_dir`
  (`factory/activities/merge_activities.py:342` — `_landing_body_dir`) at
  `factory/activities/merge_activities.py:349`, reached from
  `PrepareLandingPrInput` (`factory/activities/merge_activities.py:112` —
  `PrepareLandingPrInput`) — MUST resolve the same root the dispatch path resolved
  for the same node, and MUST NOT propagate FR-009's refusal. Any mechanism that
  proves the first is acceptable; an activity-input field added for it MUST be
  optional, so an epic already in flight replaying an older payload still
  resolves.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-009, FR-016]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-004, FR-005, FR-013, FR-014]
US3:
  depends_on: []
  depends_on_merged: [US1]
  concurrent_with: [US2, US4]
  implements: [FR-006, FR-007, FR-008, FR-011, FR-012]
US4:
  depends_on: []
  depends_on_merged: [US1]
  concurrent_with: [US2]
  implements: [FR-010, FR-018]
US5:
  depends_on: []
  depends_on_merged: [US2, US4]
  implements: [FR-015, FR-017]
```

Five `depends_on_merged` edges, declared rather than left inferred (069-US2
FR-007). US1 owns `factory/workgraph/worktree.py`, and every other story reads the
contract it establishes rather than editing it: US2 cannot assert that a derived
store path is absolute until the root is and cannot state FR-014's fallback until
FR-009's refusal exists; US3 cannot consolidate three resolvers onto one until
FR-016 has published the environment-blind name choice they need; and US4 cannot
pass a repository to a resolver that does not yet accept one. US5 waits on US2 for
the shared helper it calls and on US4 because both edit
`factory/cli/nouns/build.py` — US4 the preflight reader and the reset path's blind
root read, US5 the two `_verification_store_path` definitions and the empty-result
disclosure — and that is the only production file they share. FR-020 adds
`factory/workgraph/adapter.py` to US4, and no other story cites it. `concurrent_with`
overrides the contention edges the detector infers from slices that merely *cite*
`factory/workgraph/worktree.py`: US2 cites it to name the resolver its helper
calls, US3 cites it only to forbid editing it, and US4 cites the nine
`worktree_path` consumers whose callers it is auditing. None of the three edits
that file — it is US1's alone — so US2, US3 and US4 share no production file and
may run concurrently once US1 has merged.
