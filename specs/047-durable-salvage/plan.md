# Plan: 047-durable-salvage

Refined against the tree at `5e38c19` on 2026-08-16. Every line anchor below was
checked by hand against that commit; re-check them if the tree moves before
dispatch. (The operator checkout was ten commits stale when this refinement
started; every anchor here was re-verified after the fast-forward, and the CLI
anchors in particular moved — `factory/cli/nouns/build.py` shifted by ~58 lines
between `b4ec780` and `5e38c19`.)

Findings this spec closes or narrows:

| Finding | Sev | Story |
| --- | --- | --- |
| `hardening/salvage-is-lost-when-a-node-never-reaches-a-pr` | critical | US1 (off-machine half), US2 (dangling-sha half) |

US3 discharges no finding. It exists so the other two can be checked without git
plumbing, and because this repository's standing rule is to verify what the
factory believes rather than what it reports.

## Where this spec disagrees with the finding

The finding is the only record of this defect, and its stated mechanism is
wrong in two places. The spec is written to what I measured, not to what the
finding says. Do not "fix" the spec to agree with the finding.

**The finding says the salvage commit "dies with `remove_worktree`".** It does
not. `remove` (`factory/workgraph/worktree.py:696`) runs `git worktree remove
--force` and `git worktree prune`; a linked worktree shares the target
repository's object database and ref store, so the commit and the branch both
survive. `remove_worktree`'s own docstring says so
(`factory/activities/agent_activities.py:592-598`), and so does the module
docstring (`worktree.py:34-38`). Verified: 28 local `factory/**` branches exist
in this clone right now, long after their worktrees were swept.

**The finding says "every killed node in the factory's history has therefore
lost its work silently".** It has not. What is true is narrower, and still
critical:

1. Nothing is off-machine. 8 of 28 local `factory/**` branches have no
   counterpart on `origin`; four of those are in flight, and four are
   terminated nodes whose only copy is this disk.
2. A *superseded per-attempt* salvage sha becomes unreachable and is eventually
   pruned. Three such commits are dangling in this clone at `5e38c19`, each
   reachable from **zero** refs — `7c818d8` and `c840683`
   (`028-epic-relaunch-reset/us3`, 2026-08-13) and `53bdbb4`
   (`003-merge-queue/us3`, 2026-08-06).

**The brief's lead about `archive_message()` is a dead end, and I chased it to
the bottom.** `archive_message` (`worktree.py:253`) is used by `_archive_node`
(`:775`), which **renames** the branch with `git branch -m` (`:822`) into
`archive/factory/<epic>/<node>/<tip12>` and explicitly *refuses* to overwrite an
existing archive ref (`:816`). Archiving therefore *preserves* reachability — it
is not how a salvage sha is lost. The mechanism that is actually visible in the
tree is history rewriting: `factory/028-epic-relaunch-reset/us3`'s reflog carries
four `commit (amend)` entries, and the parent of `7c818d8` is not an ancestor of
the branch today. An amend, a hand `git branch -D` before a relaunch, or any
other rewrite orphans whatever salvage commit sat on the rewritten line.

**One thing I could not reproduce, and am not asserting.** I cannot explain from
the tree how `81905eb1f8bb…` specifically came to be lost. `factory/027-gate-
suite-fake-time/us2`'s reflog is complete from its `branch: Created from
a564b8c` entry and contains no commit for attempts 2, 3 or 4 at all, which is
inconsistent with those salvages ever having been made in this clone. The sha is
absent from the operator checkout and from all three sibling target clones on
this host. **The spec does not claim a mechanism for that particular sha**; it
claims the general one, which I proved by control (below). If an implementer
finds the specific answer, it belongs in a finding, not in this spec.

## What already exists, and where

| Thing | Location | Note |
| --- | --- | --- |
| `salvage(epic_id, node_id, *, termination, attempt, factory_root)` | `factory/workgraph/worktree.py:372` | US1 and US2's home. `git add -A`, commit `--allow-empty`, `return _head(path)` at `:413`. **No push, no `update-ref`.** |
| Salvage's per-attempt idempotency short-circuit | `factory/workgraph/worktree.py:396` | `if _head_subject(path) == message and not _is_dirty(path): return _head(path)` — **the early return that will silently skip your mirror.** See trap 5. |
| The dirty re-salvage the docstring permits | `factory/workgraph/worktree.py:387-389` | "the same attempt gaining a second commit is a cosmetic defect, losing the work is not." This is why FR-007 exists. |
| `push_branch(target_repo, epic_id, node_id, *, factory_root, remote)` | `factory/workgraph/worktree.py:416` | The only push in the tree. Landing-branch guard at `:444-449`; the push itself at `:454`. |
| The single `push_branch` caller | `factory/activities/merge_activities.py:371` | Inside `open_landing_pr`. A repo-wide grep finds no other. Do not change it (FR-012). |
| `_has_remote(repo, remote)` | `factory/workgraph/worktree.py:907` | Already the "is there an origin at all" probe `capture_base_ref` uses at `:288`. Reuse it; do not re-implement. |
| `_git(cwd, *args, env_extra=...)` | `factory/workgraph/worktree.py:827` | Scrubbed-env, `GIT_TERMINAL_PROMPT=0`, timeout-bounded. Raises `WorktreeError` on non-zero with git's stderr in the message. Every new git call goes through it — see trap 7. |
| `_archive_node` | `factory/workgraph/worktree.py:775` | Renames (`:822`), refuses to overwrite (`:816`). **Needs no change**: per-attempt refs are independent of the branch, so they survive an archive untouched. |
| `reset` (the `build reset` path) | `factory/workgraph/worktree.py:652` | Also needs no change, for the same reason. |
| `salvage_worktree` activity | `factory/activities/agent_activities.py:561` | Returns `str`. Wraps `worktrees.salvage` at `:571`. Its input `SalvageWorktreeInput` (`:543`) carries **no `target_repo`** — see the route choice below. |
| `factory_root()` | `factory/activities/agent_activities.py:164` | What the activity already passes as `factory_root`. |
| `remove_worktree` activity | `factory/activities/agent_activities.py:592` | Deletes the directory, leaves the branch. Unchanged by this spec. |
| The three `salvage_worktree` call sites | `factory/workgraph/workflow.py:1319`, `:2019`, `:2534` | Question-park, `_close_out`, `_reenqueue`. **All three discard the returned sha.** Do not add a fourth call — see trap 6. |
| `NodeStatus` | `factory/workgraph/workflow.py:429` | Deliberately narrow; carries no salvage sha. Out of scope to widen. |
| `reset_command` / `_reset_epic` | `factory/cli/nouns/build.py:590`, `:600` | **US3's shape model**: takes a compiled work graph, loops `graph.nodes`, calls into `worktree.py`, prints one line per node. |
| `build` verb registration pattern | `factory/cli/nouns/build.py:725` (`add_parser`), `:731` (`commands`), `:812-817` (the `reset` verb) | Add the new verb here. `NOUN` at `:820` needs no edit — noun discovery is by module, verbs by `set_defaults(run=…)`. |
| `ergane status` | `factory/cli/status.py:199` | The live-floor verb. Needs Temporal and the verification store. **Wrong home for US3** — a terminated epic's workflow may be gone. |
| `spec landed` | `factory/workgraph/cli.py:154` | Reports landed stories, silent on the rest. **Wrong home for US3**, and it must stay silent: 020-US2's negative test requires salvage subjects to be refused as landings (`factory/workgraph/landed.py:45`). |
| `origin_repo` fixture — a bare remote in `tmp_path` | `tests/test_worktree.py:770-783` | **This is the fixture remote.** `git init --bare`, `remote add origin`, `push -u origin main`. Reuse it; do not build a second one. |
| `test_push_branch_pushes_the_node_branch_to_origin` | `tests/test_worktree.py:786` | The assertion shape to copy: `ref_exists(bare, …)` then `head(bare, …) == head(worktree)`. |
| Test helpers `head` / `subject` / `ref_exists` | `tests/test_worktree.py:135`, `:139`, `:158` | Already there. |
| `no_operator_git_identity` autouse fixture | `tests/test_worktree.py:106` | Empties `HOME` and nulls global/system git config for every test in the file. Your tests inherit it. |
| `target_repo` fixture factory | `tests/conftest.py:592` | The real-git skeleton every worktree test builds on. |
| The no-remote precedent | `tests/test_worktree.py:314` | `test_capture_base_ref_without_an_origin_reads_the_local_head` — a clone with no remote is a supported target, not a broken one. |

## The two probes, verbatim

Run on this host on 2026-08-16 against real git. Both are load-bearing: the
first establishes that the whole of US1 and US2 can be done from inside the
node's worktree, and the second is the control US2 is built around. Your tests
must earn their own evidence — do not cite this document in a test.

### Probe 1 — a linked worktree can reach the remote and the shared ref store

```
$ git worktree add --quiet -b factory/e/us1 ../wt main
$ cd ../wt
$ git remote get-url origin
../origin.git
$ git push --quiet origin factory/e/us1        # exit 0
$ git update-ref refs/salvage/e/us1/attempt-1 $A1
$ git push --quiet origin refs/salvage/e/us1/attempt-1:refs/salvage/e/us1/attempt-1
$ git -C ../origin.git for-each-ref --format='%(refname)'
refs/heads/factory/e/us1
refs/heads/main
refs/salvage/e/us1/attempt-1
$ git -C ../repo for-each-ref refs/salvage      # written from the worktree, visible in the repo
refs/salvage/e/us1/attempt-1
```

A linked worktree shares the repository's config, object database and ref store.
`salvage()` therefore needs no `target_repo` argument to do any of this.

### Probe 2 — control and treatment for the dangling sha

Same sequence both times: salvage attempt 1, then rewrite the branch with `git
commit --amend` (the rewrite `028-epic-relaunch-reset/us3` actually performed),
then `git reflog expire --expire=now --all && git gc --prune=now`.

```
== CONTROL: no per-attempt ref ==
  PRUNED — this is the live defect

== TREATMENT: per-attempt ref written at salvage time ==
  commit
  SURVIVED via refs/salvage/e/us1/attempt-1
  refs/salvage/e/us1/attempt-1 51a8890
```

## Route choices left to the implementer

**Where the mirror lives (US1).** Two candidates. **(a) A new
`mirror_node_branch(...)` in `worktree.py` next to `push_branch`, called by the
`salvage_worktree` activity right after `worktrees.salvage`.** `salvage`'s
signature, return type and every existing test stay exactly as they are; the new
function is independently unit-testable; the activity catches its result and
never re-raises. **(b) Fold the mirror into `salvage` itself and change its
return type to a small frozen result.** Fewer moving parts, but it changes a
function with eight existing tests and a return type the activity re-exports.
**Prefer (a).** Whichever you take, the mirror must run on the idempotency
short-circuit path too (trap 5), and the disable-seam for SC-004's control must
be explicit — a parameter or an injected callable, never an environment read.

**How a per-attempt ref is named (US2).** Recommended:
`refs/salvage/<epic_id>/<node_id>/attempt-<n>-<sha12>` — **named after the commit
it points at**, which makes it idempotent by construction (the same salvage
writes the same ref name at the same sha, so a re-run is a no-op) and makes
FR-007 free (the dirty re-salvage writes a *second* ref, and neither commit is
orphaned). The alternative, a bare `attempt-<n>` ref plus a refuse-to-move guard
in the style of `_archive_node` (`worktree.py:816`), is **worse here**: that
refusal would raise on a path constitution VI says must always succeed. If you
take it anyway, say in the commit message how FR-002 is still satisfied.

Note the ref-name shape constraint: git cannot hold both `refs/x/attempt-1` and
`refs/x/attempt-1/<sha>`, so pick one level and stay on it.

**How US3 answers "is it off this machine".** Two candidates. **(a) `git
ls-remote --heads origin <branch>`** — the honest current answer, and it works
offline in tests because the fixture remote is a local bare path. **(b) Read
`refs/remotes/origin/<branch>`** — no network at all, but it answers about the
last fetch rather than about the remote. Prefer (a), and degrade to "unknown" —
never to an error — when there is no remote or `ls-remote` fails (FR-010).
**Whichever you pick, `git fetch` is forbidden**: it writes tracking refs, and
FR-009 says the verb creates nothing.

**Which name the verb gets (US3).** `ergane build salvage <workgraph.json>`,
registered beside `reset` at `factory/cli/nouns/build.py:812-817`. Do not add a
noun: `ergane status` is the live floor and `ergane spec landed` is landings, and
the plan table above says why neither can carry this.

## Traps

**Trap 1 — "what would make this test pass if the production code did nothing?"**
Ask it of every test you write, before you write the implementation. This
repository has already found four tests that were structurally unable to fail.
Two shapes will bite here specifically. A test that asserts `ref_exists(bare,
"refs/heads/factory/…")` passes trivially if some *other* fixture step already
pushed that branch — `origin_repo` (`tests/test_worktree.py:770`) pushes `main`,
so check what your fixture has already sent. And a test that asserts a sha
"still resolves" after a `gc` proves nothing unless a control proves the same
sequence *without* the fix prunes it.

**Trap 2 — the gc control is harder than it looks, and I got it wrong first.**
My own first control did not prune, and the reason is a hazard US1 creates for
US2: **pushing the branch also writes `refs/remotes/origin/<branch>` in the local
clone**, which pins the pushed tip and keeps the object alive through any `gc`.
So a US2 control run in a repo that has a remote measures the tracking ref, not
the salvage ref. Build the control in a clone with no remote, or delete the
tracking ref in the control, and assert the control **fails to resolve** — a
control that silently passes is the same defect as trap 1. Also: `git gc` alone
does not prune recent objects (`gc.pruneExpire` defaults to two weeks). The
sequence that actually prunes is `git reflog expire --expire=now --all` followed
by `git gc --prune=now`.

**Trap 3 — no test may push to a real remote.** The fixture remote is a bare
repository inside `tmp_path`, created exactly as `origin_repo` does
(`tests/test_worktree.py:770-783`): `git init --bare <tmp>/origin.git`, `git
remote add origin <that path>`, `git push -u origin main`. It is a filesystem
path, so it needs no network and no credentials, and it accepts arbitrary ref
namespaces — which is what makes US2-S6 testable at all.

A bare fixture accepting the namespace does not prove GitHub accepts it, and the
drafting pass correctly flagged that as unprovable from a diff. **The operator
settled it out of band on 2026-08-16: `refs/salvage/*` pushes to
`bryantharpeorg/ergane` and reads back through `git ls-remote`**, proven by
mirroring the three orphaned salvage commits there. So the namespace is not a
risk to design around, and the graceful-degradation path FR-002/FR-008 require
is a safety net rather than the expected case. Do not weaken the degradation
requirement on the strength of that result — a target repository is not
necessarily on GitHub, which is the whole point of FR-002.

For US2-S7's refusing
remote, use a bare repository configured to reject the namespace (a
`receive.denyCurrentBranch`-style config, a pre-receive hook, or an `origin` URL
that does not exist) — any of them exercises the same degradation path.

**Trap 4 — `--allow-empty` means an empty salvage is normal, not an edge case.**
`salvage` commits an empty tree deliberately (`worktree.py:24-32` and `:384-385`):
SC-004 of the original spec asks that *every terminal attempt* be observable from
the ref alone. An empty salvage must still mirror and must still get a
per-attempt ref (FR-011). A mirror or ref writer that short-circuits on "nothing
changed" deletes exactly the record that says an attempt produced nothing.

**Trap 5 — the idempotency short-circuit will skip your mirror.**
`worktree.py:396` returns early when the head subject already matches this
attempt's message and the tree is clean. That is precisely the activity-retry
path — and a retry after a *failed push* is the case where the mirror most needs
to run. If you fold the mirror into `salvage` (route (a)'s alternative), it must
sit after both exits, not inside the commit branch. This is also why US1-S4 is a
scenario rather than an assumption.

**Trap 6 — do not add a workflow command.** FR-005. The three
`salvage_worktree` call sites (`workflow.py:1319`, `:2019`, `:2534`) stay exactly
as they are, and no fourth activity is scheduled. A new `execute_activity` in
`EpicWorkflow` changes the command sequence, which is a replay hazard for
in-flight epics — the class 032, 038 and 039 were all written about. Everything
this spec needs happens *inside* the existing activity. That is also why
`SalvageWorktreeInput` (`agent_activities.py:543`) needs no new field: probe 1
shows the worktree already knows its own remote.

**Trap 7 — reuse `_git`, and do not widen the environment.** `_git`
(`worktree.py:827`) runs with `scrubbed_env()` plus `GIT_TERMINAL_PROMPT=0`. The
allowlist (`factory/verify/gates.py:85-97`) is `PATH`, `HOME`, `TMPDIR`, locale,
`TZ`, `TERM`, `USER`, `LOGNAME`, `SHELL` — no `SSH_AUTH_SOCK`, no token. The
landing push already works under exactly that environment, so a mirror through
the same runner inherits the same credential story and adds no new credential
surface. Adding an env var to make a push work would be a constitution-V change
wearing a bug fix's clothes.

**Trap 8 — a mirror failure must be caught, not propagated.** `_git` raises
`WorktreeError` on any non-zero exit, and `salvage_worktree` converts
`WorktreeError` into an `ApplicationError(WORKTREE_FAILED)`
(`agent_activities.py:578-579`). If the mirror's failure reaches that handler,
an unreachable remote turns a successful salvage into a failed terminal
activity — the exact inversion of constitution VI. Catch `WorktreeError` at the
mirror boundary and carry git's message into the reported outcome (FR-002 says
git's own text, not a paraphrase: an agent or operator re-driven on a summary
debugs the summary).

**Trap 9 — every scenario must be decidable from your diff alone.** Constitution
principle VIII / D-037: the judge sees the story's diff and the criteria
snapshot, never the base tree, a commit message, a terminal, or the running
system. "The branch appears on origin" is not provable from a diff; "a committed
test drives salvage against a bare fixture remote in `tmp_path` and asserts the
ref arrived" is. Every scenario in spec.md is already phrased that way — keep
them that way, and where you need runtime evidence, paste the tool output into a
committed file rather than describing it. Correct, complete work fails an
unprovable criterion, and no number of attempts fixes that.

**Trap 10 — parity is byte parity.** `tests/test_worktree.py` has six
`test_salvage_*` tests (`:466` onward) and five push tests (`:409`, `:786`,
`:805`, `:822`, `:839`) today. FR-012 and SC-006
mean they pass unchanged, not "equivalently". If one of them needs editing, that
is a signal you changed a contract, and the edit belongs in the commit message
as a stated decision.

**Trap 11 — `reset` and `_archive_node` are not yours to touch.** Both were
suspects and both are innocent (see the disagreement section). Per-attempt refs
are independent of the branch, so an archive or a `build reset` leaves them
standing, which is the behaviour FR-006 wants. Changing either one is scope
creep with a merge-conflict cost against 028's landed work.

## Sizing

Three thin stories, chained on merge-edges because each reads the code the last
one added. US1 is one new function plus one activity line plus tests. US2 is one
ref write plus tests. US3 is one CLI verb plus tests. None of them should need a
second file beyond its test file. If a story starts wanting a fourth production
file, stop and re-split: the story that cost this repository six attempts'
combined spend was oversized and split too coarsely.

## Verification the operator will run, independent of the gate

- Create a scratch clone with a bare `origin`, drive a node through a killed
  termination, and confirm the branch is on the bare remote — then repeat with
  `git remote remove origin` and confirm the salvage still happens and nothing
  raises.
- Reconstruct the 028/us3 sequence by hand: salvage, `git commit --amend`,
  `git reflog expire --expire=now --all`, `git gc --prune=now`, then
  `git cat-file -t <recorded sha>`.
- Run `ergane build salvage` against `specs/027-gate-suite-fake-time/workgraph.json`
  in the operator checkout with the Temporal worker stopped, and read what it
  says about `us2` — whose branch is real, whose work is on this disk only, and
  whose attempt-4 sha is gone.
- Count again: `for b in $(git for-each-ref --format='%(refname:short)'
  refs/heads/factory); do git show-ref --verify --quiet
  "refs/remotes/origin/$b" || echo "$b"; done` should list only epics in flight.
