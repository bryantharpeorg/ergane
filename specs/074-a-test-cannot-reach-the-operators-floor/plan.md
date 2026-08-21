# Implementation Plan: a test cannot reach the operator's floor

**Spec**: `specs/074-a-test-cannot-reach-the-operators-floor/spec.md`

## What already exists, and where

Every line below was read and **verified against `a58ec93` on 2026-08-20**.
Re-check each before you rely on it. Spec 072 exists because anchors in plans go
stale and the failure presents as an agent that "did not follow the plan".

### The doctrine, already written down twice

- `factory/roadmap/schedule.py:22-26` — the module docstring that states the
  two-independent-guards rule in one sentence and names both halves. **This is
  the design US2 generalises.** Read it before writing anything.
- `factory/cli/repo.py:459-473` — `_refuse_unsafe_removal`'s docstring, which
  states the thesis of this whole spec ("A convention is not a boundary for an
  act that deletes"), explains D-045's shape, and explains at
  `factory/cli/repo.py:468-470` why *this* guard deliberately has no
  acknowledgment variable: "nothing needs to empty a real runtime root from
  inside a test, and a door with no user is only a way in."
- `factory/verify/store.py:266` — `connect()`, and its guard at
  `factory/verify/store.py:279-281`, which *does* carry an acknowledgment
  variable via `resolve_env_flag` because a sanctioned live smoke must open a
  real store. **FR-009 is the choice between these two shapes.** Read both.

### The guarded site

- `factory/roadmap/schedule.py:153-162` — the refusal: resolves the target, then
  raises `ScheduleUnavailable` naming the address, the namespace and the seam to
  bind. Copy this message shape; it is the only one in the tree that names all
  three.
- `factory/roadmap/schedule.py:164-167` — the `Client.connect` it guards.

### The nine unguarded sites US1 migrates

- `factory/workgraph/cli.py:817`
- `factory/cli/nouns/__init__.py:54` — this is the `_connect()` that
  `factory/cli/nouns/build.py:896 _reset_epic` calls, so US1 and US4 meet here.
- `factory/cli/roadmap.py:188`
- `factory/cli/repo.py:84` — inside `_open_client`, `factory/cli/repo.py:79-89`,
  whose seam is declared immediately below at `factory/cli/repo.py:92-93`.
- `factory/doctor/probes.py:491`
- `factory/doctor/probes.py:603`
- `factory/controlplane/verify.py:185`
- `factory/notify/service.py:801`
- `factory/worker.py:283` — inside `async def main()` at `factory/worker.py:274`.
  FR-006 is about this one.

### US3's surface

- `pyproject.toml:72-78` — the five markers. Every description reads "auto-skips
  unless *`<credential>`* is set". That sentence is the defect, stated in the
  manifest.
- `tests/test_live_notify.py` — the live Telegram smoke. Its module docstring
  claims "`uv run pytest -q` stays a pure-unit suite and `-m live_telegram`
  selects this". The second half of that claim is false today (see trap 8) and
  this story either makes it true or stops the file from claiming it.
- `tests/test_live_capacity.py:169` and
  `factory/activities/roadmap_activities.py:494` — the refs on
  `hardening/live-tier-probes-leak-onto-the-production-namespace-wearing-the-epic-prefix`.

### US4's surface

- `factory/workgraph/worktree.py:401-402` — **the mechanism, in two lines:**

  ```python
  if not path.is_dir():
      raise WorktreeError(f"node worktree does not exist: {path}")
  ```

  A husk *is* a directory. It passes. Then `factory/workgraph/worktree.py:408`
  runs `_git(path, "add", "-A")`, git walks up out of the husk, finds the
  operator's checkout, and stages it.
- `factory/workgraph/worktree.py:1234-1245` — `_git`, the single runner:
  `["git", "-C", str(cwd), *args]`. **Read trap 2 before you put anything here.**
- `factory/workgraph/worktree.py:460`, `:912`, `:1018`, and the sibling gates at
  `:329`, `:1082`, `:1121`, `:1198` — the other `is_dir()` gates on node paths.
  Enumerate them yourself; FR-015 is about the ones that precede a git
  invocation, not about all nine.
- `factory/cli/nouns/build.py:886 reset_command` → `:896 _reset_epic` →
  `reset_worktree(...)`, the second route named in the finding.
- `factory/workgraph/worktree.py:381 salvage(...)` and `:252 salvage_message` —
  the first route. `396611b` is the commit it produced on 2026-08-15.

### US5's surface

- `factory/activities/roadmap_activities.py:476 _list_open_epics`, and the
  grammar at `factory/activities/roadmap_activities.py:496`:
  `if execution.id.startswith("epic-")`. A bare literal, not the constant.
- `factory/activities/roadmap_activities.py:510` — `_open_epics_provider`, the
  seam a test binds.
- The same prefix, spelled five times: `factory/cli/status.py:107`
  `EPIC_ID_PREFIX = "epic-"`, `factory/cli/nouns/build.py:125` the same constant
  again, `factory/activities/roadmap_activities.py:496` the bare literal,
  `factory/workgraph/cli.py:145` `f"epic-{epic_id}"`, and
  `factory/roadmap/workflow.py:194` `f"epic-{spec_dir}"`.
  `factory/escalation/client.py:53` documents why one of them is pinned.
  **Trap 4.**

## Traps

**1. The husk defect is not a missing check — it is the wrong check.**
`factory/workgraph/worktree.py:401-402` already refuses. It refuses on
`is_dir()`, and a husk is a directory whose `.git` file is gone. An implementer
who reads "add a guard" will add a second `is_dir()` in a new place and prove it
with a test that deletes the whole directory — which the existing line already
catches. The test that matters deletes **only `path/.git`** and leaves the
directory populated. US4-S2.

**2. Do not put the worktree check inside `_git`.**
`factory/workgraph/worktree.py:1234-1245` runs against target-repo clones as well
as node worktrees, and the direct `subprocess.run` calls at `:1286`, `:1305` and
`:1316` run against `repo` paths that are legitimately not worktrees. A blanket
"cwd must be a worktree" breaks the merge-base, rev-parse and remote reads.
Write `require_live_worktree(path)` and call it from the node-path gates.

**3. Node worktrees live *inside* the operator's checkout, so "walk up until you
find a repository" always succeeds and is never evidence.** That nesting is
structural, not a misconfiguration — it is why this class exists at all and it is
already a known finding of its own. The check is whether `path/.git` exists and
resolves into this repository's gitdir, not whether git can find *a* repository
from `path`. `git -C <path> rev-parse --show-toplevel` returns the operator's
checkout from inside a husk and looks like success. US4-S5 is the test that
catches an implementation that used it.

**4. Narrow the probe's id, never the epic grammar.** The `epic-` prefix is
spelled at five sites listed above, two of which construct real epic ids
(`factory/workgraph/cli.py:145`, `factory/roadmap/workflow.py:194`). Making
`_list_open_epics` stricter risks a real epic stopping being counted, which fails
*open* — the roadmap would over-dispatch. FR-019 changes what probes are
**named**; FR-020's exclusion must be expressible as "not an epic id" without
tightening what an epic id is. Prove FR-021 against a real id from
`factory/roadmap/workflow.py:194`.

**5. US2 is not solved by a second environment variable.** The whole finding is
that a guard readable from `os.environ` gets disabled during the mutation proof
this repository requires. A second `os.environ.get(...)` in the same function is
one guard with two names — mutation M12 would have removed the `if` containing
both. The two defences must fail independently: one on the test process's
identity, one on the client's provenance at the point of use.
`factory/roadmap/schedule.py:22-26` is the worked example — refuse to *connect*,
and separately refuse to *act through* a real client. US2-S3 is the test that
distinguishes a real pair from a disguised single: with both disabled, it must
connect.

**6. FR-009 wants exactly one door, and the tree holds an argument about doors.**
`factory/verify/store.py:279-281` has an acknowledgment variable;
`factory/cli/repo.py:468-470` deliberately refuses to have one and says why.
Choose deliberately and say which in the commit. The spec's answer is the named
opt-in of FR-010 and nothing else — no bare boolean, no marker file.

**7. A substring two refusals share is how a test passes for the wrong reason.**
Mutation M8 deleted the destination check from "export refuses a destination
inside the runtime root" and the test still passed, because the CLI had reached
the operator's real Temporal, found an open epic, and refused for *that* reason
— and both messages contained "runtime root". FR-005 is that incident turned into
a rule. When you write a refusal, grep the tree for the substring your test will
assert on.

**8. The live markers are decorative — nothing passes `-m`.** Neither CI nor the
gate selects by marker, so renaming or re-describing a marker changes nothing at
runtime. The only thing that runs is the skip expression *inside* each test
module. FR-014's enumerating test is what makes this real, and it must read the
skip condition, not the marker. Related: a guard must catch what the client
actually raises — `temporalio` raises `RuntimeError` on a dead port, not a typed
transport error. Prove any connectivity branch with `TEMPORAL_ADDRESS=127.0.0.1:1`.

**9. `factory/worker.py` must still start.** FR-006. The worker is the one caller
that is *supposed* to reach production, and it is also the process that imports
everything else here. A guard that keys on "am I in a test" is correct; a guard
that keys on "is this the worker" is not, because a test that imports the worker
must not connect either. US1-S5.

**10. This spec touches ten modules the worker imports live.** Do not land any
of it while an epic is in flight — the worker re-imports workflow code from disk
while activity modules stay passthrough from the stale process, which is a known
finding in its own right (`hardening/self-landing-stales-the-running-worker`).
067 was running when this spec was drafted.

**11. Criteria are provable from the diff and nothing else.** The judge sees the
diff and the story's acceptance scenarios — no base tree, no terminal, no commit
message. Every scenario above says "proven by a committed test" for that reason.
Where a scenario needs runtime evidence, the evidence must be *pasted into a
committed file*, and the Success Criteria in the spec are the operator's, not the
judge's — do not treat them as your acceptance bar.

**12. One test file per story.** Five stories, five new files. Do not append to
an existing test module: concurrent nodes in separate worktrees both editing
`tests/test_worktree.py` is a merge conflict the queue resolves by rejecting
somebody.

**13. Never write outside your worktree.** The node worktree is nested inside the
operator's checkout, so `../` reaches real files and nothing enforces the
boundary. This is the spec whose subject is exactly that class; do not become an
occurrence of it.

**14. Do not delete the live tiers.** US3 changes how they are selected. A tier
that can no longer be run at all fails FR-010's third scenario and removes the
only evidence anyone has that the live path works.

## Sizing

US1 is the largest story: one new module (~80 lines with its docstring), nine
call-site edits of roughly three lines each, and one test file. That is well
inside the diff-size refusal, but it is nine files and the refusal is measured on
the whole diff. **If the size refusal fires, split at the CLI boundary** —
`factory/workgraph/cli.py`, `factory/cli/nouns/__init__.py`,
`factory/cli/roadmap.py` and `factory/cli/repo.py` first, then
`factory/doctor/probes.py`, `factory/controlplane/verify.py`,
`factory/notify/service.py` and `factory/worker.py` — and land FR-003's
tree-walking test with the second half, since it cannot pass until the last site
is migrated. Do not split it pre-emptively; a two-node chain costs a full
dispatch cycle.

US2 is small and dense: two defences, four tests, no migration. US3 is mostly
`tests/` and `pyproject.toml`. US4 is one helper plus two call sites. US5 is the
smallest — one predicate and its callers.

US3, US4 and US5 share no file with each other or with US1/US2 and can run
concurrently.

## Verification the operator will run, independent of the gate

The Success Criteria in the spec are this list. They are deliberately not
acceptance scenarios: SC-003 re-runs the incident that created five live
schedules, and SC-006 aims a destructive verb at a husk. Neither belongs in a
suite an agent runs dozens of times per attempt.
