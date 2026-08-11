# Plan: A relaunch that does not resume the dead run

All line references were read against the tree at commit `9594787` on
2026-08-11. Beside each anchor is the construct to grep for, because numbers rot
before dispatch — see trap 1, where this spec's own finding proved it.

## Reuse inventory

| What | Where | Used by |
| --- | --- | --- |
| `ensure()`'s directory-reuse path (`if path.is_dir(): … return recorded`) | `factory/workgraph/worktree.py:204-206` — grep `path.is_dir()` | US1 — gains the ancestry check |
| The adopt path (directory present, record swept) | `worktree.py:207-216` — grep `adopt it rather` | US1 — left in place, see spec Edge Cases |
| Recorded-pin reuse on the create path (`pinned = base_ref or (recorded.base_ref …)`) | `worktree.py:218` — grep `pinned = base_ref` | US1 — the second site that trusts the pin |
| Branch-survival checkout | `worktree.py:220-226` — grep `_branch_exists(repo, branch)` | US1 (FR-005); its comment is the binding archive-never-delete intent |
| `capture_base_ref` — fetch semantics, no-origin rule, raise-on-fetch-failure | `worktree.py:157-178` — grep `def capture_base_ref` | US1 — the verification reads the same head this pins |
| `landing_branch` | `worktree.py:419-435` — grep `def landing_branch` | US1 — which head "current" means; US3 |
| `_branch_exists` — exit-code-as-answer subprocess shape | `worktree.py:608-617` — grep `def _branch_exists` | US1 — the template for `merge-base --is-ancestor`, see trap 3 |
| Sidecar helpers `_record_file` / `_record` / `_read_record` | `worktree.py:522-550` — grep `The base-ref record` | US1 (fresh sidecar on rebuild), US2 (the sweep) |
| `remove()` — directory sweep, sidecar untouched today | `worktree.py:498-516` — grep `def remove` | US2 — the one edit site (FR-007) |
| `salvage()`'s dirty-tree commit + idempotency shape | `worktree.py:234-275` — grep `def salvage` | US1, US3 — the model for committing an abandoned tree before archiving |
| `_SALVAGE_IDENTITY` + `_git` (identity, scrubbed env, `commit.gpgsign=false`) | `worktree.py:558-588` — grep `_SALVAGE_IDENTITY` | US1, US3 — archive commits are the factory's, not the host's |
| Workflow sweep call sites (all flow through one activity) | `factory/workgraph/workflow.py:1982-1990, :2136, :2148, :2530` — grep `remove_worktree` | US2 — context only, **not modified** |
| `remove_worktree` activity → `worktrees.remove` | `factory/activities/agent_activities.py:575-590` — grep `async def remove_worktree` | US2 — context only, not modified |
| `prepare_worktree` calls `ensure()` with **no** `base_ref` | `factory/activities/agent_activities.py:373-380` — grep `worktrees.ensure` | US1 — the recorded pin is the only pin in production |
| `build` noun grammar (`add_parser`, subcommand registration) | `factory/cli/nouns/build.py:603-` — grep `def add_parser` | US3 — `reset` registers beside `start`/`kill` |
| `workflow_id` convention (`epic-<id>`) | `factory/cli/nouns/build.py:78-80` — grep `def workflow_id` | US3 — the running guard describes this id |
| `load_workgraph` (graph-artifact argument shape) | `factory/cli/nouns/build.py:98-123` — grep `def load_workgraph` | US3 — reset takes the same argument as `start` |
| `describe()`-based execution status | `factory/workgraph/cli.py:586-` (grep `def status_command`) and `factory/cli/nouns/build.py:360-376` — grep `handle.describe()` | US3 — the RUNNING check; NOT_FOUND handling pattern at `build.py:422-427` |
| Exit-code contract (`EXIT_OK`/`EXIT_USER`/`EXIT_TRANSPORT`) | `factory/cli/errors.py` — grep `EXIT_TRANSPORT` | US3 |
| `FACTORY_ROOT` env resolution | `factory/activities/agent_activities.py:136, 157-163` — grep `FACTORY_ROOT_ENV` | US3 — reset finds the worktrees where the worker put them |
| Scratch-repo test fixtures (`target_repo`, `git`, `git_env`) | `tests/target_repo.py`; fixtures `no_operator_git_identity` and `factory_root` at `tests/test_worktree.py:104-121` | all stories — see trap 7 |
| Existing reuse/removal tests that must keep passing | `tests/test_worktree.py:236` (`test_second_ensure_reuses_the_worktree_unchanged`), `:606` (`test_remove_deletes_the_worktree_and_leaves_the_branch`) | US1, US2 — the second one asserts nothing about the sidecar today; US2 *extends* it with a sidecar assertion, all existing assertions still hold |
| CLI test harness for `build` (dispatcher + time-skipping `WorkflowEnvironment`) | `tests/test_ergane_build.py` — grep `ergane_main` | US3 |

## Traps

### Trap 1 — the finding's line numbers were already wrong when this plan was written

The finding cites `:200-213`, `:216-224` and `:507`. At `9594787` those are
`:204-216`, `:220-226` and `:522-528` — drifted in the two days since the audit.
Something else may land between this plan and your worktree. Grep for the
construct named in the inventory, never trust the number, and say so in your
commit message if a citation here no longer matches the code. The code wins.

### Trap 2 — the plausible wrong fix is to re-pin instead of verify-or-rebuild

Once you see a stale pin, the tempting one-liner is to have `ensure()` recapture
the head when the recorded one looks old, keeping the tree. Do not. The pin's
immutability for a *kept* tree is load-bearing — the module docstring
(`worktree.py:13-23`) says why: recapturing HEAD would quietly re-parent a node
whose attempt 3 started after someone else's merge, and
`test_second_ensure_reuses_the_worktree_unchanged` exists to catch exactly that.
The rule is binary: verify and keep everything unchanged, or archive and rebuild
everything fresh. Never a kept tree with a moved pin.

### Trap 3 — `_git` raises on non-zero exit, and `merge-base --is-ancestor` answers in exit codes

`git merge-base --is-ancestor A B` says "no" with exit status 1, and `_git`
(`worktree.py:566-588`) converts any non-zero exit into a raised
`WorktreeError`. Route the ancestry question through `_git` and every honest
"no" becomes an infrastructure failure that kills the prepare. Model the helper
on `_branch_exists` (`worktree.py:608-617`), which runs `subprocess.run`
directly and reads `returncode` as the answer. Reserve the raise for a git that
actually failed (exit > 1, timeout, missing repo).

### Trap 4 — "record" means two different things in this module, and the docstring will tell you not to do US2

The module docstring's third load-bearing decision reads "**Removal takes the
directory, never the record**" (`worktree.py:34-36`) — there, "record" means the
*branch and its salvage commits*. Thirty lines from the bottom, the section
header "The base-ref record" (`worktree.py:519`) uses the same word for the
`<node>.json` sidecar. The plausible wrong move is reading the first as
forbidding the second's deletion and shipping US2 as a no-op. It does not forbid
it: US2 deletes the sidecar, keeps the branch, and **rewrites both pieces of
prose** so the next reader is not handed the same ambiguity. The bullet is also
echoed outside this module — `remove_worktree`'s activity docstring ("never
deletion of the record", `factory/activities/agent_activities.py:578`) and
`_close_out`'s ("never the record", `factory/workgraph/workflow.py:1956-1958`) — and
both mean the *branch*. Those two sites are outside T014's write scope: do not
read either as forbidding the sidecar sweep, and do not turn them into the
workflow/activity edits US2 promised not to make.

### Trap 5 — archive means rename; `branch -D` is the wrong fix that loses the node's record

The comment at `worktree.py:221-223` is binding intent: "its salvaged history is
the node's record and must stay reachable." Every path this spec adds renames
into the archive namespace and deletes nothing — no `git branch -D`, no
`push --delete`, no `update-ref -d`. Two mechanical details: suffix the archive
name with the archived tip (short sha), so the name is unique, idempotent on
retry, and no plain `archive/factory/<epic>/<node>` branch ever exists to
collide with the suffixed names (git refuses a ref that is both a file and a
directory). If the archive name already exists at the same commit, that is a
completed prior archive, not an error; at a different commit, refuse — never
overwrite.

### Trap 6 — terminate runs no cleanup, and reset must not try to fix that

`temporal workflow terminate` skips the workflow's kill sequence entirely —
that is the related open finding `interpreter/cancel-bypasses-kill-sequence`,
and it is *why* the survivors exist. The wrong fix is teaching `reset` to
signal, cancel, or otherwise drive the workflow, or teaching the workflow to
handle terminate. Reset's only Temporal interaction is one read
(`describe()`) for the RUNNING guard (FR-010). Name the related finding in a
comment; fix nothing about it.

### Trap 7 — tests build their own scratch repos and touch nothing live

Every test builds its target under `tmp_path` via the `tests/target_repo.py`
fixtures, uses the `no_operator_git_identity` and `factory_root` fixtures from
`tests/test_worktree.py`, and points at no live path — the finding
`hardening/test-suite-writes-to-the-live-evidence-store` (promoted to
`specs/030-test-suite-store-isolation`) is about suites that did. US3's
Temporal-touching tests use the time-skipping `WorkflowEnvironment` or a
monkeypatched connection exactly as `tests/test_ergane_build.py` already does.
One naming hazard there: despite its name,
`test_pause_refuses_to_signal_an_epic_that_is_not_running`
(`tests/test_ergane_build.py:799`) points at a dead address and asserts exit 3
— it is the template for FR-010's *unreachable-server* leg, not for NOT_FOUND.
No existing test drives the NOT_FOUND branch; US3-S4 gets it by running reset
against the time-skipping environment with no workflow ever started, so
`describe()` raises `RPCError` with `NOT_FOUND`. No test connects to a real
server, a real proxy, or the real `.factory/`.

### Trap 8 — the check lives in `ensure()`, not in the activity and never in the workflow

Constitution IV: workflow code makes pure decisions and may not run git. The
plausible wrong home for the ancestry check is `prepare_worktree` (it would work
today) — but `ensure()` is the single funnel every reuse path flows through,
tests exercise it directly, and a second caller of `ensure()` added later would
silently skip an activity-level check. Same logic gives US2 its shape: sweep the
sidecar inside `remove()` and every workflow path inherits it with zero workflow
edits (FR-007).

## Approach

### US1 — verify, then keep everything or rebuild everything

1. Add a private ancestry helper shaped like `_branch_exists` (trap 3):
   `_is_ancestor(repo, ancestor, descendant) -> bool` over
   `git merge-base --is-ancestor`.
2. Add a "current landing head" reader: fetch per `capture_base_ref`'s rule
   (skip fetch when no `origin`; raise on fetch failure — its docstring's
   rationale applies verbatim) and `rev-parse` `origin/<landing_branch>` or
   HEAD. Reusing `capture_base_ref` itself is fine if the refactor stays
   invisible to its callers.
3. In `ensure()`: whenever a *recorded* pin is about to be trusted — the
   directory-reuse return and the `pinned = … recorded.base_ref …` create path —
   verify `_is_ancestor(recorded.base_ref, current_head)` first. Pass: today's
   behaviour, untouched (FR-002). Fail: archive-and-rebuild (step 5).
4. On the branch-survival path with no recorded pin (FR-005): after capturing
   the fresh pin, check out the branch only if
   `_is_ancestor(pinned, branch_tip)`; otherwise archive-and-rebuild.
5. Archive-and-rebuild, one private helper both US1 paths and US3 share:
   if the worktree directory exists and is dirty, commit everything to the node
   branch with `_SALVAGE_IDENTITY` (the `salvage()` shape, message naming the
   supersession); `git worktree remove --force` + `prune`; rename the branch to
   `archive/factory/<epic>/<node>/<tip12>` (trap 5's rules); delete the sidecar;
   then fall through to the fresh-create path with a fresh
   `capture_base_ref` pin and a fresh sidecar.

### US2 — one deletion, two prose corrections

`remove()` gains `record_file.unlink(missing_ok=True)` beside the directory
sweep, keeping idempotency (FR-006). Then trap 4's prose work: recast the module
docstring's "never the record" bullet to say the branch survives while the
directory *and the base-ref sidecar* go, and note in the base-ref-record section
that the sidecar's life ends with the directory. No workflow or activity edits
(FR-007) — scenario US2-S3 proves inheritance through the existing activity.

### US3 — the verb

1. `reset_command(args)` beside `start_command`'s handler conventions: load the
   graph via `load_workgraph` (same argument, same refusals), resolve the
   factory root from `FACTORY_ROOT` env falling back to `.factory` (the
   activities' rule), resolve the target clone from the graph's `target_repo`.
2. RUNNING guard first (FR-010): `describe()` on `workflow_id(epic_id)`;
   RUNNING → `OperatorError`, exit nonzero, nothing touched; NOT_FOUND →
   proceed; RPC failure → transport error exit 3 (the `_send_signal` error
   shape at `build.py:417-434` is the template).
3. Per node in graph order: run the shared archive helper from US1 step 5
   (commit dirty state, remove directory, archive branch, delete sidecar),
   collecting per-node actions; print the report; `EXIT_OK`. A node with
   nothing on disk reports "nothing to do".
4. Register `reset` in `add_parser` with help text naming what it is for: the
   supported path after a terminate, before a relaunch.

## Complexity Tracking

| Thing | Why it is not simpler |
| --- | --- |
| A fetch inside every `prepare_worktree` (US1) | Ancestry against unfetched local refs can silently pass on a stale view — the same quiet-stale defect `capture_base_ref`'s docstring records fixing, one layer down. |
| Verify-or-rebuild instead of a refuse-and-message | Refusing costs the operator a manual round trip and leaves the healing steps undocumented again; archiving first means rebuilding loses nothing (FR-004), so the guard can act instead of complain. This is also why the finding's fix 2 needs no separate home. |
| Archive namespace with per-tip suffix instead of a plain rename | A plain `archive/factory/<epic>/<node>` collides with itself on the second relaunch and with git's ref d/f rule if a suffixed name ever coexists; the tip suffix is unique, idempotent on retry, and self-describing. |
| Reset takes the graph artifact, not an epic id | The graph is the one file naming the epic id, target repo and the exact node set reset may touch (FR-011); an epic-id form would guess the target repo or re-derive, and `build start` already made this the argument shape for "act on a compiled epic". |
| A Temporal `describe()` in a git cleanup verb | Resetting a live epic's worktrees corrupts running attempts; one read is the cheapest check that cannot be wrong about RUNNING. Refusing on an unreachable server (not skipping) keeps the guard un-bypassable, and a relaunch needs the server up anyway. |

## Verification

The gate command green, in the worktree, with the new tests failing before
their implementation tasks and passing after (constitution II). The tests that
did not exist before are the point: a stale pin rebuilt with history archived, a
sidecar that dies with its directory, and a reset that is idempotent, guarded,
and provably deletes nothing. Post-landing, the operator's smoke is SC-001 run
by hand against a scratch clone — terminate, reset, relaunch, and read the
fresh tree — because a green suite has shipped a command that could not start
before.
