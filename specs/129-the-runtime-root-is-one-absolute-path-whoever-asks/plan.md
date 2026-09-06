# Implementation Plan: the runtime root is one absolute path, whoever asks

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## What already exists, and where

**The constant and the resolver.** `DEFAULT_RUNTIME_ROOT`
(`factory/workgraph/worktree.py:93`) is `Path(".ergane")` — relative.
`resolve_factory_root` (`factory/workgraph/worktree.py:191` —
`resolve_factory_root`) is the shared resolver: it returns an override when one is
set (`factory/workgraph/worktree.py:211-216`), otherwise reconciles the `.factory`
legacy name against `.ergane` (`factory/workgraph/worktree.py:224-230` —
`.ergane/` wins when both exist), and only when *neither* name exists calls
`new.mkdir(parents=True, exist_ok=True)` at `factory/workgraph/worktree.py:239` —
`resolve_factory_root` before returning. **That mkdir is the whole of FR-003**: a
*read* of the root creates it, wherever the caller is standing.

```python
# factory/workgraph/worktree.py:93
DEFAULT_RUNTIME_ROOT = Path(".ergane")
```

**The name choice is real code, and it is trapped behind the override return.**
`factory/workgraph/worktree.py:218-240` is the whole of "which directory name does
this repository use" — new wins, lone legacy is honoured, neither means new — and
it is unreachable without first passing `factory/workgraph/worktree.py:211-216`,
which returns `ERGANE_ROOT` when it is set. That is why `runtime_root_for`
(`factory/cli/repo.py:433-439`) re-implements it: it needs the name of a
repository it is not standing in, and it must not be told a root by the
environment because `--clean-runtime` deletes what it returns. FR-016 lifts those
lines into an environment-blind function of one argument — call it
`chosen_runtime_root(repo)` unless a better name presents itself; the name is not
the requirement, the blindness and the no-mkdir are — and `resolve_factory_root`
then calls it for the no-override path with the repository FR-001 gives it. Its
one-time legacy `DeprecationWarning` stays where it is, in the resolver, because
`test_resolve_legacy_only_uses_it_and_names_migration`
(`tests/test_runtime_root.py:71` —
`test_resolve_legacy_only_uses_it_and_names_migration`) asserts on it and
`runtime_root_for` has never warned.

**The override does not resolve — and the helper that returns it is not the fix
site.** `factory/env.py:79` returns `Path(new_value)` and `factory/env.py:88`
returns `Path(old_value)` — both inside `resolve_env_path` (`factory/env.py:47` —
`resolve_env_path`), neither calling `.resolve()`:

```python
# factory/env.py:79 and :88, inside resolve_env_path
        return Path(new_value)
...
        return Path(old_value)
```

That function answers "which of these two variable names is set" for **fifteen**
call sites, and **three** of them read the runtime root:
`factory/workgraph/worktree.py:211`, `factory/verify/diffcheck.py:304` and the
reset path's own read at `factory/cli/nouns/build.py:1888` — that third one is
FR-010's, fixed by naming `graph.target_repo`, not by changing this helper. The
other twelve resolve the control-plane config path (`factory/config.py:125`,
`factory/controlplane/config.py:216`), the repo registry
(`factory/registry.py:167`), the ledger (`factory/activities/usage_activities.py:651`,
`factory/usage/cli.py:145`, `factory/cli/usage.py:112`) and the verification
store (`factory/activities/verify_activities.py:635`,
`factory/activities/notify_activities.py:778`, `factory/cli/status.py:691`,
`factory/cli/nouns/build.py:1485`, `factory/cli/nouns/build.py:1535`,
`factory/cli/nouns/answer.py:97`). FR-002's anchoring goes in the runtime-root
resolver, applied to what this helper returns. See trap 3.

**The anchor the spec asks for already has a reader in this module.**
`_repo_identity` (`factory/workgraph/worktree.py:1037` — `_repo_identity`) runs
one `git rev-parse --path-format=absolute --show-toplevel --git-common-dir` and
returns both, absolute, or `None` when there is no repository — "a non-zero exit
is an answer here, not a failure". `_owning_clone`
(`factory/workgraph/worktree.py:1072` — `_owning_clone`) turns a worktree plus its
common dir into the clone that owns it. Those two are the whole of FR-001's
discovery and FR-009's refusal; nothing new needs writing.

**The worker's cwd is never the target repository.**
`factory/supervision/units.py:593` — `_service_text` emits
`WorkingDirectory={layout.install_root if working_directory is None else working_directory}`,
and `factory/supervision/units.py:695` — `_temporal_text` emits
`WorkingDirectory={layout.install_root}`. 082's versioned worker template passes
`working_directory=layout.deployment_tree("%i")`, which is a deployment tree and
not a repository either. Nothing under `factory/supervision/` sets a runtime-root
variable: `grep -rn ERGANE_ROOT factory/supervision/` returns **0**. So the
deployed configuration is precisely the one this defect needs. The spec
deliberately does not change this file — see "What this spec is not".

**Thirteen worker reads take the root blind, and nine of them are standing next to
the answer.** `grep -rn "resolve_factory_root\|factory_root()" factory/` returns
**twenty-two** read sites, not thirteen: the thirteen in the table below, the
eight operator reads in the next section, and `factory_root`'s own delegate at
`factory/activities/agent_activities.py:195`. It is **not** the whole
enumeration — see "The grep cannot see the artifact the ledger measured" below,
and run
`grep -rn "resolve_factory_root\|factory_root()\|DEFAULT_FACTORY_ROOT\|DEFAULT_RUNTIME_ROOT" factory/`
instead. `factory_root` (`factory/activities/agent_activities.py:188` —
`factory_root`) takes no argument and delegates to the shared resolver. Its
callers, and the other blind readers, divide cleanly:

| Read | Reached from | Holds a repository? |
| --- | --- | --- |
| `factory/activities/agent_activities.py:420` | `prepare_worktree` (`factory/activities/agent_activities.py:398` — `prepare_worktree`) | yes — `request.target_repo`, passed at `factory/activities/agent_activities.py:417` |
| `factory/activities/agent_activities.py:498` | `run_agent_attempt` (`factory/activities/agent_activities.py:482` — `run_agent_attempt`) | yes — `AttemptContext.target_repo` (`factory/workgraph/models.py:463`) |
| `factory/activities/agent_activities.py:796`, `factory/activities/agent_activities.py:807`, `factory/activities/agent_activities.py:822` | `salvage_worktree` (`factory/activities/agent_activities.py:762` — `salvage_worktree`) | **no** — `SalvageWorktreeInput` (`factory/activities/agent_activities.py:745` — `SalvageWorktreeInput`) |
| `factory/activities/agent_activities.py:861` | `remove_worktree` (`factory/activities/agent_activities.py:847` — `remove_worktree`) | yes — `RemoveWorktreeInput` (`factory/activities/agent_activities.py:838` — `RemoveWorktreeInput`) |
| `factory/activities/agent_activities.py:893` | `archive_and_clear_remote_branch` (`factory/activities/agent_activities.py:877` — `archive_and_clear_remote_branch`) | yes — `ArchiveAndClearRemoteBranchInput` (`factory/activities/agent_activities.py:868` — `ArchiveAndClearRemoteBranchInput`) |
| `factory/activities/merge_activities.py:464` | `open_landing_pr` (`factory/activities/merge_activities.py:425` — `open_landing_pr`) | yes — `request.target_repo`, passed at `factory/activities/merge_activities.py:461` |
| `factory/activities/merge_activities.py:602` | `sync_landing_branch` (`factory/activities/merge_activities.py:580` — `sync_landing_branch`) | yes — `request.target_repo`, passed at `factory/activities/merge_activities.py:599` |
| `factory/activities/merge_activities.py:349` | `_landing_body_dir` (`factory/activities/merge_activities.py:342` — `_landing_body_dir`), called at `factory/activities/merge_activities.py:366` from `prepare_landing_pr` (`factory/activities/merge_activities.py:357` — `prepare_landing_pr`) | **no** — `PrepareLandingPrInput` (`factory/activities/merge_activities.py:112` — `PrepareLandingPrInput`) |
| `factory/cli/nouns/build.py:367` | `_preflight_factory_root` (`factory/cli/nouns/build.py:367` — `_preflight_factory_root`) | yes — the graph |
| `factory/activities/roadmap_activities.py:670` | `_preflight_factory_root` (`factory/activities/roadmap_activities.py:670` — `_preflight_factory_root`) | yes — the graph |
| `factory/cli/nouns/build.py:1888` | `_reset_epic` (`factory/cli/nouns/build.py:1826` — `_reset_epic`) | yes — `graph.target_repo`, five lines below at `factory/cli/nouns/build.py:1893` |

The two landing rows are the most blatant instances in the tree: the blind
`worktrees.resolve_factory_root(FACTORY_ROOT_ENV)[0]` is the argument on the line
*after* the `request.target_repo` in the same call. Nine reads are FR-010; the
four in the "no" rows are FR-018 and are the dangerous ones, because they are the
back half of a node's life.

**Eight more reads are operator verbs, and FR-009's refusal reaches every one of
them the moment US1 merges.** None of these holds a repository or can obtain one,
and none of them is on a node's lifecycle:

| Read | Reached from | Verb |
| --- | --- | --- |
| `factory/cli/doctor.py:69` | `_store_path` (`factory/cli/doctor.py:65` — `_store_path`) | `ergane findings` |
| `factory/doctor/cli.py:54` | `_store_path` (`factory/doctor/cli.py:50` — `_store_path`) | `ergane findings` |
| `factory/cli/nouns/spec.py:1257` | `_check_fixes` (`factory/cli/nouns/spec.py:1231` — `_check_fixes`) | `ergane spec validate` |
| `factory/doctor/probes.py:148` | `_evidence_stores` (`factory/doctor/probes.py:147` — `_evidence_stores`) | `ergane doctor` |
| `factory/doctor/probes.py:285` | `_gather_async` (`factory/doctor/probes.py:265` — `_gather_async`) | `ergane doctor` |
| `factory/doctor/probes.py:393` | `_gather_async` (`factory/doctor/probes.py:392` — `_gather_async`) | `ergane doctor` |
| `factory/cli/repo.py:624` | `migrate_runtime_root_command` (`factory/cli/repo.py:613` — `migrate_runtime_root_command`) | `ergane repo migrate-runtime-root` |
| `factory/cli/repo.py:473` | `_override_disagreement` (`factory/cli/repo.py:455` — `_override_disagreement`) | `ergane repo forget --clean-runtime` |

The last row is the only one that needs nothing: `_override_disagreement` returns
at `factory/cli/repo.py:471` unless one of the two variables is set, so its read
is never the no-repository arm. The other seven are FR-019, and trap 20 is why
they are US1's work and not a later story's.

**The grep cannot see the artifact the ledger measured.** The C-32 row's summary
blames `factory_root()`, and its *measurement* is 4.2 GB of per-node agent HOMEs
under `site-packages/.ergane/homes/`. No `resolve_factory_root` or
`factory_root()` read produces those. The path is built in the **workflow**:

```python
# factory/workgraph/workflow.py:1893 and :3985, inside the AttemptContext call
                        home_path=str(home_path(DEFAULT_FACTORY_ROOT, graph.epic_id, node.id)),
```

`DEFAULT_FACTORY_ROOT` (`factory/workgraph/worktree.py:99`) aliases
`Path(".ergane")` (`factory/workgraph/worktree.py:93`), so that string is
relative; `graph.target_repo` is seven lines below it in the same constructor
(`factory/workgraph/workflow.py:1900` and `factory/workgraph/workflow.py:3992`).
The adapter then does `home = Path(context.home_path)`
(`factory/workgraph/adapter.py:1058`), `home.mkdir(parents=True, exist_ok=True)`
(`factory/workgraph/adapter.py:1060`) and `"HOME": str(context.home_path)`
(`factory/workgraph/adapter.py:971`) — three resolutions of a relative string
against the worker's cwd. `home_path` itself
(`factory/workgraph/adapter.py:815` — `home_path`) is fine; it joins whatever
root it is handed, exactly like `worktree_path`. That is FR-020, it is US4's, and
trap 21 says where the derivation goes and why not into the workflow.

**And those thirteen reads are the `worktree_path` audit the finding asks for.**
The C-23 row's remedy has two conjuncts — "make the path absolute at construction
**and** audit the other `worktree_path` call sites -- salvage() and friends have
the same shape". Every one of the ten call sites takes the root as an *argument*:

```
factory/workgraph/preflight.py:598   inside worktree_ownership_findings
factory/workgraph/worktree.py:396    inside ensure                     (factory/workgraph/worktree.py:362 — ensure)
factory/workgraph/worktree.py:530    inside salvage                    (factory/workgraph/worktree.py:511 — salvage)
factory/workgraph/worktree.py:586    inside push_branch                (factory/workgraph/worktree.py:555 — push_branch)
factory/workgraph/worktree.py:815    inside record_salvage_ref         (factory/workgraph/worktree.py:778 — record_salvage_ref)
factory/workgraph/worktree.py:893    inside mirror_node_branch         (factory/workgraph/worktree.py:855 — mirror_node_branch)
factory/workgraph/worktree.py:1342   inside sync_with_target           (factory/workgraph/worktree.py:1316 — sync_with_target)
factory/workgraph/worktree.py:1603   inside reset                      (factory/workgraph/worktree.py:1559 — reset)
factory/workgraph/worktree.py:1656   inside archive_and_clear_remote_branch (factory/workgraph/worktree.py:1634 — archive_and_clear_remote_branch)
factory/workgraph/worktree.py:1687   inside remove                     (factory/workgraph/worktree.py:1671 — remove)
```

The one call site outside `factory/workgraph/worktree.py` is
`factory/workgraph/preflight.py:598`, inside `worktree_ownership_findings`
(`factory/workgraph/preflight.py:563` — `worktree_ownership_findings`) and **not**
inside `landing_readiness_preflight` (`factory/workgraph/preflight.py:797` —
`landing_readiness_preflight`), which is 199 lines further down. The fence above
masks that citation from the anchor tiers, which is why it is repeated here in
symbol form; an implementer performing the US4-S8 audit by function name would
otherwise read the wrong function.

So the audit is not a tenth edit; it is the table above, read the other way. Fix
who supplies the root and all ten consumers are correct at once — which is why
US4 owns the key's second conjunct and US4-S8 is the regression guard on
`worktree_path` (`factory/workgraph/worktree.py:289` — `worktree_path`) itself.

**The store defaults never consult the resolver at all.** Five relative literals,
all naming the *legacy* directory the resolver no longer prefers:

```python
# factory/activities/verify_activities.py:128
DEFAULT_VERIFICATION_DB_PATH = ".factory/verification.db"
# factory/activities/usage_activities.py:99
DEFAULT_LEDGER_PATH = ".factory/ledger.db"
# factory/usage/cli.py:30 and factory/cli/usage.py:26
DEFAULT_LEDGER_PATH = Path(".factory") / "ledger.db"
```

**Six modules derive the verification store path, not two — and the four nobody
counted are the reproduction.** The worker's two are `_store_path`
(`factory/activities/verify_activities.py:634` — `_store_path`) and `_store_path`
(`factory/activities/notify_activities.py:770` — `_store_path`). The operator's
four are `_verification_store_path`, **defined twice** in the same module
(`factory/cli/nouns/build.py:1484` — `_verification_store_path` and
`factory/cli/nouns/build.py:1534` — `_verification_store_path`; the second
shadows the first), `_verification_store_path` (`factory/cli/status.py:690` —
`_verification_store_path`), `_store_path` (`factory/cli/nouns/answer.py:96` —
`_store_path`), and the bridge's entry point at `factory/notify/service.py:1049`
inside `main` (`factory/notify/service.py:1029` — `main`):

```python
# factory/notify/service.py:1049
    db_path = os.environ.get(VERIFICATION_DB_PATH_ENV) or DEFAULT_VERIFICATION_DB_PATH
```

That last line bypasses `resolve_env_path` entirely, so it honours
`FACTORY_VERIFICATION_DB_PATH` (`factory/activities/verify_activities.py:130`)
and not `ERGANE_VERIFICATION_DB_PATH`. `ergane build answer` reaches
`factory/cli/nouns/build.py:1534` and `factory/cli/nouns/answer.py:96`;
`ergane status` reaches `factory/cli/status.py:690`. The operator finding's own
notes give `ergane build answer` from a node worktree as the reproduction, so a
fix that stops at the worker's two closes nothing an operator can see. US2 takes
the worker's three (including the bridge); US5 takes the operator's four and the
three ledger readers.

**The shared helper's home is `factory/stores.py`, and it is a new file.** Both
natural homes are forbidden: `factory/workgraph/worktree.py` is US1's alone and
US2 must not edit it, and `factory/env.py` cannot import the resolver because the
resolver imports it (`factory/workgraph/worktree.py:84`). A new leaf module keeps
the import direction one-way — `factory/stores.py` imports `factory.env` and
`factory.workgraph.worktree`, and nine modules across `factory/activities/`,
`factory/cli/` and `factory/notify/` import it. Nothing imports those from
`worktree.py`, so no cycle is created; `factory/cli/status.py:110` already imports
from `factory.workgraph.worktree` and is the proof that this direction is
tolerable on the CLI's import path. Name the helper something that cannot be
confused with 043's `_resolve_store_path` (`factory/doctor/cli.py:58` —
`_resolve_store_path`), which stays where it is and keeps its own rule.

**And neither store module can be handed a repository.** `target_repo` appears
zero times in `factory/activities/verify_activities.py` and
`factory/activities/notify_activities.py`, and `RecordVerificationInput`
(`factory/activities/verify_activities.py:467` — `RecordVerificationInput`) carries
`result` and `criteria_source_path` only. FR-014 exists because of this: the
resolver refuses, and these readers must fall back rather than propagate it.

**043 ALREADY LANDED THE SPLIT-STATE RULE — COPY THE PATTERN, DO NOT EDIT THE
FUNCTION.** `_resolve_store_path` (`factory/doctor/cli.py:58` —
`_resolve_store_path`) is the one landed answer to "the resolver points at a root
with no data while the legacy root holds it". It is called by `_store_path`
(`factory/doctor/cli.py:50` — `_store_path`), by `factory/cli/doctor.py:70` and by
`factory/cli/nouns/spec.py:1258`, and `factory/cli/repo_export.py:146` names it as
the governing rule. Its contract is held by four committed tests —
`test_split_state_follows_populated_legacy_ledger`
(`tests/test_runtime_root_findings.py:153` —
`test_split_state_follows_populated_legacy_ledger`),
`test_legacy_only_root_reads_factory_doctor_db_and_warns_once`
(`tests/test_runtime_root_findings.py:179` —
`test_legacy_only_root_reads_factory_doctor_db_and_warns_once`),
`test_explicit_db_wins_over_resolver`
(`tests/test_runtime_root_findings.py:199` — `test_explicit_db_wins_over_resolver`)
and `test_doctor_modules_do_not_carry_factory_literal_defaults`
(`tests/test_runtime_root_findings.py:222` —
`test_doctor_modules_do_not_carry_factory_literal_defaults`) — and
`tests/test_runtime_root.py:253-378` holds 043's `repo migrate-runtime-root`
contract in five tests. **Those nine tests must still pass unchanged after US1,
US2 and US5.** FR-013 reproduces the *shape* of that rule in US2's new helper and
strengthens it from existence to content; `factory/doctor/cli.py` is not edited,
and the spec's "What this spec is not" states the consequence out loud. The last
of the four is also the shape US2-S6 copies: it asserts on the module's *source*,
which is the only way to hold a line inside a process entry point nobody calls
from a test.

**Two repo-anchored resolvers already exist and both explain themselves.**
`resolve_repo_runtime_root` (`factory/cli/init.py:2088` —
`resolve_repo_runtime_root`) and `runtime_root_for` (`factory/cli/repo.py:418` —
`runtime_root_for`). Read both docstrings before writing US3 — they name the mkdir
side effect and the cwd dependence as their reasons for not using the shared
resolver, and `runtime_root_for` cites the 2026-08-14 store deletion. **They are
the specification for what FR-016 should have been all along.**

**The readiness check already reads the repo-anchored answer, and that is only
half of its finding.** `factory/cli/init.py:2249` — `gather_init_facts`
computes `runtime_root_ignored=_git_ignores(repo_root, f"{root_name}/")` from
`resolve_repo_runtime_root`'s answer — so the report already names a resolved
root rather than a hardcoded one. What it does not do is honour the override the
engine honours, and what `init` does not do is ignore both names:
`factory/cli/init.py:1831` — `_write_scaffold` writes exactly one line,
`f"{RUNTIME_ROOT}/\n"`, from `RUNTIME_ROOT = Path(".ergane")` at
`factory/cli/init.py:135`. That is FR-012.

**The empty read has no voice.** `factory/cli/nouns/build.py:1554`, inside
`_answer` (`factory/cli/nouns/build.py:1547` — `_answer`), prints
`no pending questions for epic '<id>'` and names no file. That sentence is the
whole of the operator finding's second half, and FR-015 is its fix.

**The disclosure that keeps `--clean-runtime` honest.** `_override_disagreement`
(`factory/cli/repo.py:455` — `_override_disagreement`) consults
`resolve_factory_root()` *only* to report that an override names a different root,
never to retarget the delete. Read it before touching `runtime_root_for`.

**This behaviour is documented as intended.** `docs/architecture.md:199` says the
root "defaults to `.ergane` against the worker's working directory" —
that sentence is the design statement this spec falsifies.
`docs/architecture.md:203` ("Read paths below as relative to the resolved root")
stays true and needs no edit.

## Traps

**Trap 1 — DO NOT ADD A FOURTH RESOLVER.** Two hand-rolled repo-anchored copies
already exist (`factory/cli/init.py:2088` — `resolve_repo_runtime_root`,
`factory/cli/repo.py:418` — `runtime_root_for`), and the reason this defect has
survived two rounds of fixes is that every previous author worked around it
locally instead of correcting the shared one. FR-016 gives them something to call
and FR-007 requires them to call it. If US3 ends with three implementations still
standing, the spec has made the problem worse by adding a fourth answer that only
*some* callers use.

**Trap 2 — The mkdir on read is load-bearing for some callers.** The call at
`factory/workgraph/worktree.py:239` — `resolve_factory_root` is on the no-override
path **and fires only when neither `.ergane/` nor `.factory/` exists** — an
implementer auditing the legacy branch will not find it there — and some verbs
rely on the root existing after they ask for it. FR-003 does not say "delete the
mkdir"; it says a *read* must not create. Separate the two: a resolver that
answers, and an explicit ensure the creating verbs call. An implementer who simply
deletes the line will produce a green suite and a factory that cannot bootstrap.

**Trap 3 — `resolve_env_path` IS THE DIAGNOSIS, NOT THE FIX SITE, AND `.resolve()`
FREEZES THE CWD DEPENDENCE RATHER THAN REMOVING IT.** Two wrong moves live on the
same two lines. The first is to reach for `.resolve()` on the returns at
`factory/env.py:79` and `factory/env.py:88`: `Path(".ergane").resolve()` is
`<cwd>/.ergane` — absolute, still wrong, and a test that asserts only
`result.is_absolute()` goes green on it. The second, and the more expensive, is to
do the *correct* anchoring in that function anyway. `resolve_env_path`
(`factory/env.py:47` — `resolve_env_path`) is a generic two-name env helper with
fifteen call sites and is handed no repository and no way to obtain one; three of
the fifteen read the runtime root — `factory/workgraph/worktree.py:211`,
`factory/verify/diffcheck.py:304` and the reset path at
`factory/cli/nouns/build.py:1888`, which FR-010 fixes by naming
`graph.target_repo` rather than by touching this helper — and twelve do not.
Anchor here and you re-anchor `ERGANE_CONFIG_PATH`,
`ERGANE_VERIFICATION_DB_PATH`, `ERGANE_LEDGER_PATH` and the repo registry as a
side effect — including the store variables US2's own tests then depend on — and
you silently break `runtime_root_prefixes` (`factory/verify/diffcheck.py:287` —
`runtime_root_prefixes`), which skips an override that is already absolute and
reads `override.parts[0]` (`factory/verify/diffcheck.py:305-306`), so it would
stop recognising a relative runtime root in a node's diff. Threading a repository
parameter through fifteen call sites is the opposite mistake and is the shape
trap 13 forbids. FR-002's anchoring belongs in `resolve_factory_root`
(`factory/workgraph/worktree.py:191` — `resolve_factory_root`), where the
repository is named or discoverable, applied to the value the helper returned.
US1-S2 exists to fail both wrong versions: it asserts the *full* path equals the
named repository's `.ergane` from a working directory that is not that repository,
and it asserts `runtime_root_prefixes` still sees the relative override. Every
developer on this floor has `ERGANE_ROOT` set by `scripts/ergane-env.sh` to an
absolute path, so the relative-override arm never fires in local testing.

**Trap 4 — SOME OF THE COMMITTED TESTS ENCODE THE DEFECT AND SOME PROTECT 043.
THEY ARE IN THE SAME TWO FILES. RETARGET, DO NOT REWRITE.** What must change is
the *cwd-relative setup*: `tests/test_runtime_root.py` and
`tests/test_runtime_root_findings.py` `chdir` into a tmp dir and let the resolver
answer from there, which is the behaviour this spec removes. Retarget that setup
so each test names its repository — `_unset_factory_root`
(`tests/test_runtime_root.py:43` — `_unset_factory_root`) is the fixture to
extend. Three tests in the first file assert the *old* contract directly and are
the ones whose bodies change: `test_resolve_no_root_creates_ergane`
(`tests/test_runtime_root.py:60` — `test_resolve_no_root_creates_ergane`) becomes
an assertion about the explicit ensure,
`test_resolve_legacy_only_uses_it_and_names_migration`
(`tests/test_runtime_root.py:71` —
`test_resolve_legacy_only_uses_it_and_names_migration`) and
`test_resolve_new_wins_when_both_exist` (`tests/test_runtime_root.py:90` —
`test_resolve_new_wins_when_both_exist`) keep their *assertions* and change only
how the repository is named. What must **not** change are the assertions listed
under "043 ALREADY LANDED THE SPLIT-STATE RULE" above — the four
`tests/test_runtime_root_findings.py` contract tests at :153, :179, :199 and :222,
and 043's five migrate-verb tests spanning `tests/test_runtime_root.py:253-378`.
Rewriting those away deletes a landed spec's regression guarantee, including the
one guarantee that would have caught the split-state hazard FR-013 exists for; and
the two files are 14,374 B and 8,979 B, so a wholesale rewrite is ~46 KB of diff
on its own — see Sizing. **The setup that has to be retargeted is bigger than the
three bodies**: `_chdir_tmp` (`tests/test_runtime_root_findings.py:65` —
`_chdir_tmp`) is `autouse=True` and deletes both root variables and chdirs into a
non-repository `tmp_path` for **every** test in that file
(`tests/test_runtime_root_findings.py:64-73`), and each of the five migrate-verb
tests calls `_unset_factory_root` then `monkeypatch.chdir(tmp_path)` by hand.
After FR-009 that state is the refusal, so `tests/test_runtime_root_findings.py:135`,
`tests/test_runtime_root_findings.py:153` and
`tests/test_runtime_root_findings.py:179` and the migrate-verb tests survive only
because of trap 20's fallback — read that trap before touching either file.
`test_explicit_db_wins_over_resolver` (`tests/test_runtime_root_findings.py:199` —
`test_explicit_db_wins_over_resolver`) and
`test_doctor_modules_do_not_carry_factory_literal_defaults`
(`tests/test_runtime_root_findings.py:222` —
`test_doctor_modules_do_not_carry_factory_literal_defaults`) never reach the
resolver at all — the first returns on the explicit `--db` branch, the second is a
pure AST check — so they are unaffected either way. Four more files turn on the
old contract and are not in either of those two:
`test_stale_worktree_gather_from_sync_context` (`tests/test_doctor_probes.py:390` —
`test_stale_worktree_gather_from_sync_context`) deletes both root variables,
chdirs into a non-repository `tmp_path` and asserts on `.factory/worktrees/`
beneath it through `factory/doctor/probes.py`, which is trap 20's third module; and `test_the_resolver_would_have_created_the_runtime_root`
(`tests/test_ergane_status.py:1047` —
`test_the_resolver_would_have_created_the_runtime_root`) is a **named control**
that delenvs both root variables, chdirs to a non-repo tmp dir and asserts
`resolve_factory_root()` creates `.ergane` — FR-003 removes the create and FR-009
makes that call refuse, so it dies twice over and must be **re-pointed at the new
explicit ensure, not deleted**, or the "nothing was created" test above it loses
its control; `test_check_does_not_create_the_runtime_root_it_is_judging`
(`tests/test_ergane_init_check.py:637` —
`test_check_does_not_create_the_runtime_root_it_is_judging`) and the comment block
at `tests/test_clean_runtime_names_the_root_it_did_not_clean.py:444` both state
the create-and-cwd behaviour in prose that goes stale the moment US1 lands. An
implementer who touches only the two obvious files hits a red suite and spends
attempt time rediscovering the rest.

**Trap 5 — ANCHORING ON `--show-toplevel` RECREATES THE DEFECT YOU ARE FIXING.**
Git walks *up* from the directory it is handed, so a node worktree answers
`--show-toplevel` with **the worktree's own root**, not the clone's. That is this
spec's claim, and US1-S6 is the test that proves or refutes it — build the linked
worktree with git and read the answer before writing the resolver. The comment at
`factory/workgraph/worktree.py:989` — `_worktree_ownership` corroborates the
walk-up mechanism only: it says a bare `mkdir` directory with no `.git` answers the
enclosing clone's toplevel with exit 0. An operator standing in a worktree is the
reproduction in the verification-store finding. So the anchor is the *owning
clone*: `_repo_identity` (`factory/workgraph/worktree.py:1037` —
`_repo_identity`) then `_owning_clone` (`factory/workgraph/worktree.py:1072` —
`_owning_clone`). US1-S6 fails an implementation that stops at the toplevel, and
it needs a fixture that creates a real linked worktree — a `tmp_path` with a
`.git` file will not reproduce it.

**Trap 6 — DERIVING A MODULE-LEVEL CONSTANT AT IMPORT TIME BREAKS `--help`.**
FR-004 says the store defaults must come from the resolved root. The wrong move is
to rewrite `DEFAULT_VERIFICATION_DB_PATH` (`factory/activities/verify_activities.py:128`)
as a call to the resolver: that runs at import, in whatever directory the process
started in, and after FR-009 it *raises* there — so `ergane --help` outside a
clone stops working. Compute the default inside the functions instead — the
derivations trap 13 enumerates — and leave the constants as file names. US2-S3
and US5-S5 are the tests that fail the import-time version, and US5 carries its
own because its four modules are on the CLI's import path and US2's are not.

**Trap 7 — `_verification_store_path` IS DEFINED TWICE IN ONE FILE.**
`factory/cli/nouns/build.py:1484` — `_verification_store_path` and
`factory/cli/nouns/build.py:1534` — `_verification_store_path` are byte-identical
and the second wins. Editing only the first passes every test that exercises the
CLI and changes nothing. Fix both, or collapse them to one. US5-S2 is the control
that catches the half-edit, and it must call each definition individually rather
than going through the CLI.

**Trap 8 — CONSOLIDATING `runtime_root_for` NAIVELY REPEATS THE 2026-08-14
DELETION.** Its docstring (`factory/cli/repo.py:418` — `runtime_root_for`) states
the rule: "the environment is not consulted here for that reason, and the result
is a child of `repo` by construction rather than by check", because
`--clean-runtime` deletes what it returns and on 2026-08-14 this repository lost
its whole runtime root to a process acting on a root it had been handed. The wrong
move is to satisfy FR-007 by calling `resolve_factory_root`
(`factory/workgraph/worktree.py:191` — `resolve_factory_root`): its **first** act
is to return `ERGANE_ROOT` (`factory/workgraph/worktree.py:211-216`), so
`--clean-runtime` would then be handed a root outside the repository. FR-007
consolidates onto FR-016's environment-blind entry point — the name choice only,
`.ergane/` wins and a lone `.factory/` is honoured — and nothing else. FR-011 and
US3-S4 pin the blindness. The override is still *reported* by
`_override_disagreement` (`factory/cli/repo.py:455` — `_override_disagreement`)
and never acted on. **If US3 finds it has no environment-blind entry point to
call, US1 was incomplete — that is FR-016, and it is US1's work, not a licence to
edit `factory/workgraph/worktree.py` here.**

**Trap 9 — An empty read is the failure mode, not an exception.** The verification
store case returns *no rows*, not an error. So a test that asserts "no exception"
proves nothing. FR-005 requires asserting the written rows come back, with a
working-directory change between the write and the read — and, because of trap 14,
with the store override variables deleted and the opened file asserted by path.

**Trap 10 — THE READINESS CHECK ALREADY DOES HALF OF WHAT ITS FINDING SAYS, SO
THE NO-OVERRIDE ARM PROVES NOTHING.** `factory/cli/init.py:2249` —
`gather_init_facts` already asks git about the *resolved* name rather than the
written one, so with no override set the reported root and the engine's root
already agree today and a test that only checks that arm passes on an unchanged
tree. An implementer reading the finding's title will look for a bug that is not
there and stop. The two live halves are: the check does not honour the override
the engine honours (FR-006, US3-S1 and US3-S5), and `init` writes only one ignore
line at `factory/cli/init.py:1831` — `_write_scaffold` (FR-012, US3-S6). Do not
"fix" line 2249 back to a hardcoded name.

**And know which of the two values comes from which function before you start.**
`resolve_repo_runtime_root` (`factory/cli/init.py:2088` —
`resolve_repo_runtime_root`) returns `(root_name, is_legacy)` — a
*repository-relative directory name*, not a path — and it has exactly one caller,
`factory/cli/init.py:2222` inside `gather_init_facts`
(`factory/cli/init.py:2200` — `gather_init_facts`), which spends it three times:
`runtime_root=`, `runtime_root_is_legacy=` and
`runtime_root_ignored=_git_ignores(repo_root, f"{root_name}/")`. FR-006 changes
only the first: the *reported root* becomes the shared resolver's answer, with
the override honoured. The *name* and the `is_legacy` flag keep coming from
`resolve_repo_runtime_root`, which FR-007 re-points at FR-016's blind entry point
— because `git check-ignore` can only be asked about a repository-relative path,
so feeding it an absolute override is meaningless (trap 11). An implementer who
replaces the whole function with the resolver's answer breaks
`runtime_root_ignored` for every override, and one who leaves the reported root
alone fails US3-S1.

**Trap 11 — AN OVERRIDE OUTSIDE THE REPOSITORY MUST NOT TURN THE CHECK RED.** Once
FR-006 makes the readiness check report the engine's root, an `ERGANE_ROOT` set to
`/var/lib/ergane` makes `git check-ignore` meaningless: the root cannot reach git
history at all. Reporting "not ignored" there would turn every correctly
configured wheel install red on its first check. US3-S5 requires the check to name
the root and say it lies outside the repository.

**Trap 12 — 043 IS THE CLOSEST PRIOR ART AND DELIBERATELY DID NOT PROMISE ALL OF
THIS.** Read `specs/043-runtime-root-integrity` before assuming the work is done:
its requirements cover the leak detector, the ledger path derivation and the
migrate verb, and its Out of Scope leaves store relocation unsettled. Citing 043
as evidence that the root is already absolute is one mistake this trap prevents.
The other, opposite mistake is treating 043 as irrelevant: its FR-006 landed as
`_resolve_store_path` (`factory/doctor/cli.py:58` — `_resolve_store_path`) and
that function is the pattern FR-013 copies into US2's new helper. Read it before
writing a new one — and do not edit it. US2-S7 asserts its four contract tests are
untouched in the diff.

**Trap 13 — FIX THE DERIVATIONS, NOT THE CALLERS — AND THE ENUMERATION IS THE
SCOPE, SPLIT ACROSS TWO STORIES.** Roughly fifteen call sites take the raw answer,
among them `factory/doctor/probes.py`, `factory/cli/doctor.py`,
`factory/cli/nouns/spec.py` and `factory/doctor/cli.py`. **None of those changes
its store derivation in US2 or US5** — that is what this trap forbids. It is not
the same as "none of those files changes": four of them take a one-line refusal
opt-out in **US1** under FR-019, because FR-009's refusal reaches them the moment
the resolver starts refusing (trap 20). Keep the two apart: US2 and US5 must not
touch these files at all, and US1 must not change what they *derive*. What
changes in US2 and US5 is the *derivations*, because trap 6 forbids fixing this at
the constant. **US2 owns three**: `_store_path`
(`factory/activities/verify_activities.py:634` — `_store_path`), `_store_path`
(`factory/activities/notify_activities.py:770` — `_store_path`) and the bridge's
inline read at `factory/notify/service.py:1049`. **US5 owns seven**: both
`_verification_store_path` definitions (`factory/cli/nouns/build.py:1484`,
`factory/cli/nouns/build.py:1534`), `_verification_store_path`
(`factory/cli/status.py:690` — `_verification_store_path`), `_store_path`
(`factory/cli/nouns/answer.py:96` — `_store_path`), and the three
`DEFAULT_LEDGER_PATH` readers (`factory/activities/usage_activities.py:651`,
`factory/usage/cli.py:145`, `factory/cli/usage.py:112`). **US5's four verification
derivations are the reproduction**: `ergane status` and `ergane build answer` from
a node worktree is verbatim what the operator finding's notes describe. Leave them
and the spec half-fixes the key it declares — which is why they are their own
story rather than a tail on US2's. If either story's diff touches fifteen files,
the fix went in at the wrong layer.

**Trap 14 — "GIVEN NO OVERRIDE" IS NOT THE STATE A TEST STARTS IN.**
`_isolated_test_store` (`tests/conftest.py:525` — `_isolated_test_store`) is
`scope="session", autouse=True` and sets `ERGANE_ROOT`, `FACTORY_ROOT`,
`ERGANE_VERIFICATION_DB_PATH`, `VERIFICATION_DB_PATH`, `ERGANE_LEDGER_PATH` and
`LEDGER_PATH` to absolute session paths for **every** test in the suite
(`tests/conftest.py:545-552`). So a US2 or US5 test that does not delenv them is
asserting nothing: with `ERGANE_VERIFICATION_DB_PATH` set absolute, `_store_path`
(`factory/activities/verify_activities.py:634` — `_store_path`) already returns the
same file from the repository and from a worktree, and rows written in one cwd
already come back in the other **with production code untouched**. That is a
test-only diff passing an acceptance scenario — the exact shape that let this
defect survive two rounds of fixes. The pattern to copy is `_unset_factory_root`
(`tests/test_runtime_root.py:43` — `_unset_factory_root`), extended to the four
store variables. US1's scenarios fail loudly under the override; US2's and US5's
would pass silently, so the delenv is an obligation there, not a choice.

**Trap 15 — DERIVING THE STORE FROM THE ROOT ORPHANS THIS REPOSITORY'S DATA.**
Measured in `/home/admin/code/ergane` on 2026-09-04 with every override unset: the
resolver answers `.ergane/` (both names exist, new wins,
`factory/workgraph/worktree.py:224-230`), while `.factory/verification.db` is
11,857,920 B and `.factory/ledger.db` is 565,248 B and `.ergane/verification.db`
and `.ergane/ledger.db` are both **0 bytes**. A naive FR-004 therefore swaps the
live stores for empty files — reintroducing, as the fix, the empty-read failure
trap 9 names. 043's landed `_resolve_store_path` (`factory/doctor/cli.py:58` —
`_resolve_store_path`) is the right shape but is not sufficient: it follows
*existence*, and a 0-byte file exists — which is why `ergane findings` answers the
stale 28,672 B `.ergane/doctor.db` beside the live 126,267,392 B
`.factory/doctor.db` on this host right now, and will keep doing so, because
FR-013 fixes US2's helper and not that function. FR-013 requires content, not
existence. Nothing is copied and nothing is moved; the reader follows the data.
Note the arm US2-S4 tests: the process must stand where an owning clone is
discoverable — inside the repository or one of its worktrees — or FR-014's
fallback fires first and FR-013 is never reached.

**Trap 16 — THE STORE READERS CANNOT BE HANDED A REPOSITORY, SO THE REFUSAL MUST
NOT REACH THEM.** `target_repo` appears zero times in
`factory/activities/verify_activities.py` and
`factory/activities/notify_activities.py`, and `RecordVerificationInput`
(`factory/activities/verify_activities.py:467` — `RecordVerificationInput`) carries
`result` and `criteria_source_path` only. Threading a repository into those
activity inputs is a workflow-input change and is explicitly out of scope. So
FR-014 is the answer: catch FR-009's refusal at the derivation and fall back to
today's process-relative default. Get this wrong in the raising direction and a
wheel-installed worker refuses every `store.connect(_store_path())` —
`factory/activities/verify_activities.py:509` and
`factory/activities/verify_activities.py:576`, and twelve `_store_path()` call
sites in `factory/activities/notify_activities.py`, eight of them
`store.connect(_store_path())` — unless the operator sets the very override this
spec says stops being mandatory. Trap 14 guarantees no test in the
suite would show you.

**Trap 17 — THE FRONT AND BACK HALVES OF ONE NODE MUST RESOLVE THE SAME ROOT, AND
FR-018'S FALLBACK IS NOT ENOUGH ON ITS OWN.** `ensure`
(`factory/workgraph/worktree.py:362` — `ensure`) creates the worktree at
`worktree_path(factory_root, ...)` (`factory/workgraph/worktree.py:396`) using the
root the *dispatch* read, which after FR-010 is under `request.target_repo`.
`salvage` (`factory/workgraph/worktree.py:511` — `salvage`) looks for it at
`factory/workgraph/worktree.py:530` using the root the *salvage activity* read —
and `SalvageWorktreeInput` (`factory/activities/agent_activities.py:745` —
`SalvageWorktreeInput`) carries no repository, so a plain "fall back to the
process-relative default" makes those two roots differ in exactly the deployment
this spec exists for. The symptom is not a wrong store, it is
`[Errno 2] No such file or directory: /opt/ergane/.ergane/worktrees/...`, recorded
verbatim in the C-23 row's notes as one of three failures in sequence. So FR-018
requires *sameness*, and the fallback only covers the arm where the dispatch
itself fell back. US4-S6 is the test: create the worktree through the dispatch
path and assert the salvage path equals it. `_landing_body_dir`
(`factory/activities/merge_activities.py:342` — `_landing_body_dir`) is the same
shape one step milder — a transcript path in a PR body that names a directory
nothing wrote.

**Trap 18 — A REQUIRED NEW FIELD ON AN ACTIVITY INPUT IS A REPLAY HAZARD.** The
straightforward fix for trap 17 is to carry `target_repo` on
`SalvageWorktreeInput` (`factory/activities/agent_activities.py:745` —
`SalvageWorktreeInput`) and `PrepareLandingPrInput`
(`factory/activities/merge_activities.py:112` — `PrepareLandingPrInput`), the way
`RemoveWorktreeInput` (`factory/activities/agent_activities.py:838` —
`RemoveWorktreeInput`) already does. Make it **optional with a default**, the way
`AttemptContext.target_repo` is (`factory/workgraph/models.py:463`, `str = ""`).
The sentence that states the reason out loud belongs to the *next* field, not to
that one: `factory/workgraph/models.py:466` says the default exists "for legacy
payloads that predate this field" about `agent: str = ""`
(`factory/workgraph/models.py:467`), while `target_repo`'s own comment
(`factory/workgraph/models.py:460-462`) says only that it is fixed at dispatch.
Both are the precedent; only the second carries the rationale. A required field
turns every in-flight epic's replay into a deserialisation failure, and `salvage_worktree`
(`factory/activities/agent_activities.py:762` — `salvage_worktree`) says so in its
own docstring about its return value. US4-S7 is the control that constructs the
input without the field.

**Trap 19 — THE SHARED STORE HELPER HAS EXACTLY ONE LEGAL HOME.**
`factory/workgraph/worktree.py` is US1's file and US2 must not edit it;
`factory/env.py` cannot import the resolver because the resolver imports
`factory.env`. FR-004 therefore names `factory/stores.py`, a new leaf module, and
the import direction is one-way: `factory/stores.py` imports the resolver, nine
modules import `factory/stores.py`, and nothing in `factory/workgraph/` imports
`factory/stores.py`. Reversing that direction, or reaching for a lazy import
inside a function to break a cycle you created, is the sign the helper went in the
wrong place. Do not name it `_resolve_store_path`: 043 already owns that name in
`factory/doctor/cli.py` (`factory/doctor/cli.py:58` — `_resolve_store_path`), it
stays, and two functions with one name across two rules is how the next reader
concludes the doctor store was fixed too.

**Trap 20 — FR-009'S REFUSAL LANDS ON SEVEN OPERATOR VERBS, AND THREE OF THEM ARE
HELD BY 043'S OWN TESTS.** `grep -rn "resolve_factory_root\|factory_root()"
factory/` returns twenty-two read sites, not thirteen. Eight are operator verbs
holding no repository — the table under "Eight more reads are operator verbs" —
and the moment `resolve_factory_root` starts refusing, `ergane findings`,
`ergane doctor`, `ergane spec validate` and `ergane repo migrate-runtime-root`
refuse with it wherever the operator is standing outside a clone. Three of them
are held by committed tests that construct exactly that state:
`tests/test_runtime_root_findings.py:135`, `:153` and `:179` run under the
**autouse** `_chdir_tmp` (`tests/test_runtime_root_findings.py:65` —
`_chdir_tmp`), which deletes both root variables and chdirs into a
non-repository `tmp_path`; the five migrate-verb tests at
`tests/test_runtime_root.py:253-378` do it by hand; and
`test_stale_worktree_gather_from_sync_context` (`tests/test_doctor_probes.py:390`
— `test_stale_worktree_gather_from_sync_context`) does it for
`factory/doctor/probes.py`. So FR-019's fallback is not a nicety — it is what
keeps US1's own merge green, which is why it is US1's work and not US3's or a
later story's, even though four of the five files it touches belong to nobody
else. Two wrong moves. The first is to skip it and discover the red suite after
writing the resolver; the second is to write the fallback as a literal
`Path(".factory")` inside `factory/cli/doctor.py`, `factory/doctor/cli.py` or
`factory/doctor/probes.py`, which
`test_doctor_modules_do_not_carry_factory_literal_defaults`
(`tests/test_runtime_root_findings.py:222` —
`test_doctor_modules_do_not_carry_factory_literal_defaults`) refuses by AST in
exactly those three modules. Call FR-016's name choice with the working directory
instead. `_override_disagreement` (`factory/cli/repo.py:455` —
`_override_disagreement`) is the one read that needs nothing: it returns at
`factory/cli/repo.py:471` unless an override is set.

**Trap 21 — THE 4.2 GB IS NOT BEHIND ANY RUNTIME-ROOT READ, AND THE FIX DOES NOT
GO IN THE WORKFLOW.** The C-32 row's summary blames `factory_root()`; its
measurement is 4.2 GB of agent HOMEs under `site-packages/.ergane/homes/`. Those
come from `home_path(DEFAULT_FACTORY_ROOT, ...)` built in the workflow
(`factory/workgraph/workflow.py:1893`, `factory/workgraph/workflow.py:3985`) and
mkdir'd from a relative string in the adapter
(`factory/workgraph/adapter.py:1060`). Fix the reads in FR-010 and FR-018 and the
transcript directory and the pid file become absolute while the HOME keeps
landing in site-packages — a green suite over a finding that is still accruing.
The tempting fix is to change the workflow lines to join `graph.target_repo`,
which is right there (`factory/workgraph/workflow.py:1900`,
`factory/workgraph/workflow.py:3992`). **Do not.** A workflow may not touch the
filesystem, so it cannot ask which runtime-root name this repository uses; joining
a hard-coded `.ergane` answers wrongly for a repository holding only `.factory/`,
and changing the formula moves the HOME of an epic already in flight. The
derivation belongs in `run_agent_attempt`
(`factory/activities/agent_activities.py:482` — `run_agent_attempt`), which
already holds the resolved absolute root from
`factory/activities/agent_activities.py:498` and already replaces the frozen
context once — `context = replace(context, session_id=derived)`
(`factory/activities/agent_activities.py:513`), whose own comment block states the
replay reasoning this change reuses. Leave the two workflow sites computing a
value so an older payload still deserialises; the activity's derivation is what
the adapter creates and exports (`factory/workgraph/adapter.py:1060`,
`factory/workgraph/adapter.py:971`). One more consumer to check before editing:
`_build_argv` (`factory/workgraph/adapter.py:464` — `_build_argv`) walks *up* from
the home to find the runtime root to read-only-bind
(`factory/workgraph/adapter.py:529-534`), so a home that is no longer three levels
under the root silently changes the sandbox's bind set.

## Sizing

**The measured basis, because the previous draft guessed.** `git show --format=''
<sha> | wc -c` on this repository's four most recent landed stories: 1027a05
(057/US4) is 63,932 B for 975 insertions across 26 files — 1.6 KB under the
refusal; 602a92c (057/US2) is 52,840 B for 906 changed lines across 7 files;
8ee5e9c (057/US1) is 37,856 B for 647 changed lines; 94c8cd8 (126/US3) is
32,059 B for 427. That is **55–75 diff bytes per changed line** in this tree,
because every function here carries a long docstring. Size a story by estimating
*changed lines* and multiplying, not by counting files. The bound is
`DIFF_REFUSAL_THRESHOLD` at `factory/verify/diffbounds.py:66`; it reads 64 KiB
today only because it defaults to the judge's separate attention allowance,
`DIFF_INPUT_LIMIT` at `factory/verify/diffbounds.py:47`, and the comment between
them says plainly that the two are distinct settings which merely share a value,
so cite the refusal one when you mean the refusal. Both weigh the whole assembly,
pasted evidence included, computed by `factory/verify/diffbounds.py:137` —
`assembled`.

US1 is **one production file of substance**, `factory/workgraph/worktree.py` — the
resolver, an optional repository parameter, the answer/ensure split, the
relative-override anchoring per trap 3, FR-016's extracted name choice, and reuse
of `_repo_identity` and `_owning_clone` — **plus one line each in five operator
modules** for FR-019's refusal opt-out: `factory/cli/doctor.py`,
`factory/doctor/cli.py`, `factory/doctor/probes.py` (three reads),
`factory/cli/nouns/spec.py` and `factory/cli/repo.py`. Trap 20 is why those five
cannot wait for a later story. `factory/env.py` is **not** in US1's scope: trap 3
explains why the anchoring cannot live there, and a diff that edits
`factory/env.py:79` or `factory/env.py:88` fails US1-S2's second assertion. Its
tests are a **new** file carrying US1-S1 through US1-S8, plus scoped edits:
retarget the `chdir` setup in `tests/test_runtime_root.py` (14,374 B) and
`tests/test_runtime_root_findings.py` (8,979 B) so each test names its repository
— including the autouse `_chdir_tmp` (`tests/test_runtime_root_findings.py:65` —
`_chdir_tmp`), which governs the whole of the second file — re-point the control
at `tests/test_ergane_status.py:1047`, and correct the two stale docstrings named
in trap 4. `tests/test_doctor_probes.py` needs nothing if FR-019's fallback is
right and is the cheapest proof that it is. Estimate 400–560 changed lines →
**27–42 KB** at the measured rate, plus 1–2 KB of pasted evidence. It has room; a *wholesale rewrite* of those two test
files would be roughly 46 KB on its own and would not. **Do not rewrite them;
retarget them.**

US2 is `factory/stores.py` (new: the shared helper, FR-013's content rule,
FR-014's fallback) plus three one-to-four-line call-site changes in
`factory/activities/verify_activities.py`,
`factory/activities/notify_activities.py` and `factory/notify/service.py`, with
seven scenarios' worth of tests — two of which need a real linked worktree and one
of which seeds two sqlite files and asserts on row contents. Estimate 400–550
changed lines → **26–41 KB**, plus 2–3 KB of pasted store paths and `stat` output.
It stays there only because the fix is one shared helper: if each of the three
call sites grows its own copy of the split-state logic, the story doubles and
should have been split. It must not edit `factory/workgraph/worktree.py`; if it
needs to, US1 was incomplete.

US3 is `factory/cli/init.py` (the readiness check's source of truth and the
`.gitignore` line), `factory/cli/repo.py` (delete the hand-rolled name choice, keep
the environment blindness, call FR-016's entry point) and `docs/architecture.md:199`.
Largest deletion, smallest addition; estimate 250–400 changed lines → **17–30 KB**.
It must not edit `factory/workgraph/worktree.py`: FR-016 is US1's work and trap 8
says what to do if it appears to be missing.

US4 is `factory/activities/agent_activities.py` (`factory_root` gains the
repository, eight call sites, one optional input field, and FR-020's home
derivation beside the existing `replace(context, session_id=...)` at
`factory/activities/agent_activities.py:513`),
`factory/activities/merge_activities.py` (three reads, one optional input field),
`factory/activities/roadmap_activities.py`, `factory/cli/nouns/build.py` (the
preflight reader plus `_reset_epic`'s blind root read at
`factory/cli/nouns/build.py:1888`) and `factory/workgraph/adapter.py` (the home
the activity now supplies, and the bind walk at
`factory/workgraph/adapter.py:529-534` trap 21 names), plus ten scenarios' worth
of tests that run activities from a directory outside the repository, one that
creates a worktree through the dispatch path and finds it through the salvage
path, and one that asserts the created HOME lies under the target repository.
Estimate 460–630 changed lines → **30–47 KB**, which is the largest story here
and still 17 KB under the refusal. If the dispatch, landing and salvage reads do
not collapse to one parameter on `factory_root` plus two optional input fields,
stop and split along the salvage/landing seam — FR-020 with the salvage half is
the natural second node — rather than pushing through.

US5 is `factory/cli/nouns/build.py` (both `_verification_store_path` definitions
and `_answer`'s empty-result line), `factory/cli/status.py`,
`factory/cli/nouns/answer.py`, `factory/activities/usage_activities.py`,
`factory/usage/cli.py` and `factory/cli/usage.py` — seven derivations, each one to
four lines, all calling US2's helper — with five scenarios' worth of tests.
Estimate 250–400 changed lines → **17–30 KB**, plus the pasted output of
`ergane status` and `ergane build answer` run from two directories.

Shared production files: US4 and US5 both touch `factory/cli/nouns/build.py`,
which is why US5 waits on US4; US5 and US2 share `factory/stores.py`, which is why
US5 waits on US2; US1 and US3 both touch `factory/cli/repo.py` — US1 one line for
FR-019, US3 the hand-rolled name choice — and US3 already waits on US1's merge, so
that pair is sequenced rather than concurrent. **US2, US3 and US4 share no
production file with each other** — each cites `factory/workgraph/worktree.py` and
none edits it — which is what the `concurrent_with` declarations say. Every story's evidence is pasted paths and row
listings: tens of lines, not a transcript.

## Verification the operator will run, independent of the gate

Per constitution VIII and D-037 the judge sees the diff and the criteria only, so
runtime evidence must be committed as pasted output. Beyond that:

1. **Unset every runtime-root and store variable** — do not
   `eval scripts/ergane-env.sh`. This is the whole point; with the script loaded
   the defect cannot reproduce.
2. Before changing anything, with those variables unset, print the store paths the
   CLI would open — the verification store and the ledger — and `stat -c '%n %s'`
   both runtime-root names' copies of each. On this floor that prints
   `.factory/verification.db` at 11,857,920 B beside a 0-byte
   `.ergane/verification.db`. Keep the output; step 10 compares against it.
3. From the repository root, run a verb that reports the runtime root. Record it.
4. `cd /tmp` and run the same verb against the same repository. It must report the
   same absolute path, and must not have created `.ergane` in `/tmp`.
5. From a directory inside no git repository, with no repository named, run the
   same verb and confirm it refuses by name rather than answering.
6. `cd` into a node worktree under `.factory/worktrees/` and run the same verb. It
   must report the owning clone's root, not the worktree's.
7. From that same worktree run **`ergane build answer <epic-id>`** and
   **`ergane status`** — the two verbs the operator finding was filed against.
   Each must name the store file it opened, and it must be the clone's populated
   one. This is the step that distinguishes a fix from a half fix.
8. Confirm no `.ergane` directory has appeared anywhere under the installed wheel
   — in particular no `homes/` under it. `du -sh` the site-packages tree before and
   after a dispatch; on this floor the C-32 row measured 4.2 GB accumulating there,
   and steps 3 through 7 would all pass while it kept growing.
9. Write a verification row from the repository root, then read it from inside a
   worktree. The row must come back. This step passes on a fresh empty store, so
   it is not sufficient on its own — step 10 is what makes it mean something.
10. Print the store paths again, exactly as in step 2, and compare. The path may
    change name; the **size must not drop**. A path that now names a 0-byte file
    is the orphaning trap 15 describes, and it is the failure this whole procedure
    exists to catch.
11. `ergane init --check` in a repository holding only `.factory/`, then again with
    `ERGANE_ROOT` pointing outside it. Neither run may report a red
    `runtime_root_ignored` for a root git cannot see.
12. Dispatch one node from a working directory that is not the target repository,
    let it terminate, and confirm the salvage commit exists on the node branch.
    This is the step that catches trap 17: the dispatch and the salvage must have
    found the same worktree, and a disagreement shows up as `WORKTREE_FAILED` with
    a path under the install root rather than under the target repository.

13. With every runtime-root variable still unset, `cd` to a directory inside no
    git repository and run `ergane findings list`, `ergane doctor`,
    `ergane spec validate <a spec dir>` and
    `ergane repo migrate-runtime-root` (without `--yes`). None may raise the
    resolver's refusal, and none may create a runtime root in that directory.
    This is FR-019, and it is the step that catches a US1 that made the resolver
    correct and the CLI unusable.
14. From the same directory, run `ergane --help`. It must print.

Step 1 is the step everyone will skip, and skipping it makes every later step pass
for the wrong reason. Steps 2 and 10 are the pair that no green suite can replace,
step 7 is the one the previous draft had no equivalent of, step 8's `du` is the
only one that looks at the artifact C-32 actually measured, step 12 is the one
that exercises a whole node's lifecycle rather than one read of it, and step 13 is
the one that proves the refusal did not take the operator's own verbs with it.
