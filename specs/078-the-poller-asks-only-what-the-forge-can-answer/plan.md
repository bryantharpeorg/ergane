# Implementation Plan: the poller asks only what the forge can answer

**Spec**: `specs/078-the-poller-asks-only-what-the-forge-can-answer/spec.md`

## What already exists, and where

**Every line number below was verified on 2026-08-21 by printing that exact line
individually** (`sed -n '<n>p' <file>`), not by counting `grep -A` context.
Check each one anyway before you rely on it: the findings this spec came from
carried anchors two to four hundred lines stale, because the tree moved under
them.

**The field set the poller sends:**

- `factory/mergequeue/gh.py:68` — `_VIEW_FIELDS = (`
- `:69` — `"state,isDraft,mergedAt,closedAt,mergeStateStatus,autoMergeRequest,"`
- `:70` — `"statusCheckRollup,baseRefOid"` — the one that is version-sensitive.
- `:62-67` — the comment explaining why `baseRefOid` is there. Read it before you
  consider removing the field; 069-US1's free rebase depends on it.
- `factory/mergequeue/gh.py:224` — `def poll_pr(self, pr_number: int) -> PrSnapshot:`
- `factory/mergequeue/gh.py:461` — `def _run_json(self, *args: str)`, and `:479`
  — `def _run(self, *args: str) -> GhRunResult:`. Both correct. Do not loosen.
- `factory/mergequeue/models.py:256` — `base_sha=_nullable_str(payload.get("baseRefOid")),`

**The check that cannot see the refusal:**

- `tests/test_gh_argv_contract.py:164` — `def _gh_would_refuse(argv: Sequence[str]) -> str:`
- `:169` — the docstring stating the rule as written: *"Exit 1 with 'unknown
  flag', 'unknown command', or a usage block means the argv is malformed."*
  **That sentence is the defect.** It enumerates three refusal shapes out of an
  open set.
- `:186` — `stderr = (completed.stderr or completed.stdout or "").lower()`
- `:188-190` — the three-way prose match.
- `:192` — `return completed.stderr or completed.stdout or ""` — and the fall
  through at `:193`, `return ""`, which the caller at `:203` (`if refusal:`)
  reads as accepted.
- `:196` — `@pytest.mark.skipif(_gh_binary() is None, reason="gh is not installed")`.
  This part is right; keep it — it is a runtime condition, not a bare marker.

**The refusal, run by hand on this host at 2026-08-21 07:12 CT, gh 2.98.0:**

```
$ cd /tmp && GH_TOKEN= GIT_TERMINAL_PROMPT=0 gh pr view 1 --json definitelyNotAField
Unknown JSON field: "definitelyNotAField"
Available fields:
  additions
  assignees
  author
  ...
EXIT=1
```

Lowercased: no `unknown flag`, no `unknown command`, no `usage:`. `_gh_would_refuse`
returns `""`. **The check watched a refusal and reported acceptance.**

**The poller task whose exception nobody reads:**

- `factory/workgraph/workflow.py:2637` — `self._landing_tasks[node.id] = asyncio.ensure_future(`
- `:2638` — `self._poll_landing(graph, record, config)` — the coroutine it wraps.
- `factory/workgraph/workflow.py:3239` — the second `ensure_future` site, on the
  requeue path. **Both need whatever you do; fixing one is half a fix.**
- `factory/workgraph/workflow.py:2641` — `async def _poll_landing(`
- `:2671` — `snapshot = await workflow.execute_activity(` and `:2672` —
  `poll_landing,`. This is the call that raises when `gh` refuses.
- `factory/workgraph/workflow.py:591` — `self._landing_tasks: dict[str, asyncio.Task[None]] = {}`
- `:1369-1371` — the only other use: cancel every task on kill, then clear.
  **Nothing anywhere awaits a landing task or reads its exception.**
- `factory/workgraph/workflow.py:2636` — `record.state = NodeState.ENQUEUED`, set
  just before the task is spawned. This is the state that then never changes.
- `factory/activities/merge_activities.py:410` — `async def poll_landing(request: PollLandingInput) -> PrSnapshot:`

**Where a capability check could live** — decide deliberately and say which in
the diff; both are defensible and only one should be built:

- `factory/controlplane/verify.py:305` — `class LLMProbe:` and `:311` —
  `async def gather(self, config: ControlPlaneConfig) -> LLMSnapshot:`. The
  probe protocol is at `:54` — `async def gather(self, config: ControlPlaneConfig) -> Any: ...`.
  This is the `install --verify` surface. The forge is arguably a control-plane
  subsystem and this is where an operator looks before dispatching.
- `factory/doctor/probes.py:260` — `class OrphanedKeyProbe:` onward, the doctor's
  probe set (`StaleWorkerProbe:322`, `StaleWorktreeProbe:387`,
  `StoreIntegrityProbe:439`, `RoadmapWedgeProbe:474`). This is the recurring
  health surface rather than the one-time install surface.

Today **neither of them looks at `gh` at all.** The only mention of a `gh`
version anywhere in the tree is prose in a failure message:
`factory/mergequeue/wiring.py:266` — `"(run: gh --version and update from https://cli.github.com), or"`.

## Traps

**1. Do not remove `baseRefOid`.** It is the most tempting one-line "fix" in this
spec and it silently undoes 069-US1. Without that field every landing rejection
is priced as the node's own defect and the free rebase — which has still never
run in production — never fires. If your diff shrinks `_VIEW_FIELDS`, stop.

**2. Do not loosen `_run_json`.** It is correct: it reports that it received
something that is not JSON. Making it tolerant would silence every call site,
including the ones that are right.

**3. The exit code is the contract; the prose is not.** FR-001. `gh`'s messages
differ across versions, subcommands and locales. Read `completed.returncode`.
The one value you must not treat as a refusal is the authentication exit (4) —
that is FR-002 and US1-S2, and getting it wrong makes the check unrunnable in
CI, which is the same as deleting it.

**4. A check that denies everything is not an improvement.** US1-S2 is the
control and it is the failure mode of this exact change. Watch the corrected
check pass on a well-formed unauthenticated command before you believe it.

**5. Derive the field set; do not copy it.** FR-003, US2-S4, SC-006. This defect
is one hand-maintained list disagreeing with another. Adding a third list is
writing the defect again, one layer up. The check and the probe must read the
same object the poller reads.

**6. Both `ensure_future` sites.** `factory/workgraph/workflow.py:2637` and
`:3239`. A node that requeues
after a rejection spawns a second poller through the second site; fixing only
the first leaves the requeue path exactly as blind as it is today, and the
requeue path is the one that runs during a busy epic.

**7. Do not convert the poller to a foreground await.** US3-S5. Riding the
landing in the background is what lets an epic run other nodes while a pull
request sits in the queue. The defect is that nobody reads the task's exception,
not that the task exists. Observe the failure; keep the concurrency.

**8. One transient failure is not a dead poller.** FR-010 and US3-S3. The forge
is a network service and `_FAST` already carries a retry policy
(`factory/workgraph/workflow.py:338`). Read that policy before deciding what
"stopped" means, and let the activity's own retries do their job.

**9. Guard, do not mark.** FR-004 and the open finding
`live-tier-skips-by-guard-not-marker`: nothing in this repository passes `-m` in
CI or in the gate, so a `pytest.mark` is decorative and a marked test is an unrun
test. `tests/test_gh_argv_contract.py:196` already does this correctly — copy
that shape.

**10. You probably cannot install an old `gh` to test with.** US1-S4 and SC-004
need a refusal, and this host runs gh 2.98.0, which accepts every field the
poller sends. Two honest routes: name a field that no `gh` has (the refusal
shape is identical, and that is exactly how the evidence above was produced), or
put a stub `gh` earlier on `PATH` that exits non-zero with a realistic message.
**Say in the diff which you did.** Claiming to have tested against gh 2.45.0 when
you did not is worse than the defect.

**11. `install --verify` versus `doctor` is a real decision, not a coin flip.**
Trap-free either way, but pick one, state the reason in the diff, and do not
build both. An operator meets `--verify` once at install and `doctor` whenever
something is wrong; this defect is a first-run defect and it recurs after a `gh`
downgrade, which argues for `--verify` primarily.

**12. The judge sees the diff and the criteria, nothing else** (Constitution
Principle VIII). Every SC here requires committed, pasted output. A terminal you
ran and did not commit did not happen. `gh` can echo a token in an error — read
what you paste before you commit it.

**13. One test file per story.**
- US1 → `tests/test_gh_argv_contract.py` (existing; this story owns it)
- US2 → `tests/test_forge_capability_probe.py`
- US3 → `tests/test_landing_poller_failure_is_visible.py`

## Sizing

**US1 is small** — the classifier is nine lines and the work is mostly in the
tests that prove the new classification both ways. Its risk is trap 4, and it is
a real risk: the natural first draft denies on any non-zero exit and breaks
every unauthenticated run.

**US2 is medium.** Most of it is deciding where the probe lives and wiring one
more probe into a surface that already has a probe protocol. The part that will
take the time is FR-003's derive-don't-copy, and that part is the point.

**US3 is medium and the least certain.** It changes the workflow, which means
determinism rules apply and replay tests are in scope. Read
`factory/workgraph/workflow.py:2641-2701` end to end before writing anything.
If it turns out that observing the task's exception cannot be done without
restructuring the loop, say so in the diff and implement the narrowest thing
that satisfies FR-008 and FR-009 — a recorded reason on the node record is worth
more than an elegant rework.

## Verification the operator will run, independent of the gate

- **Point the factory at a stub `gh` that refuses a field, and dispatch a
  one-story epic.** The measurement that matters is whether the operator learns
  before the epic parks. Nothing in the suite can answer that.
- **Watch the corrected contract check go red on purpose**, then green. A green
  run of a new check proves it ran, not that it works — which is the whole
  history of this defect.
- **Run install verification on a host with no `gh` at all** and read what it
  says. Absent and incapable must not produce the same sentence.
- **Kill an epic mid-landing** after US3 and confirm the cancel path still
  behaves as it does today.
</content>
