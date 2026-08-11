# Plan: A red check that reaches no one

All line references below were read against the tree at commit `9594787` on
2026-08-11. They are cited so you can find the code, not so you can trust the
numbers — see trap 9, and note that the findings' own refs had already rotted
(`_RECOVERY_OUTCOMES` "at :2084" is at `:284`, the flaky test "at :4822" is at
`:4958`) in the two days between the audit and this plan.

## Reuse inventory

| What | Where | Used by |
| --- | --- | --- |
| `_RECOVERY_OUTCOMES = {CHECKS_FAILED, CONFLICT}` | `factory/workgraph/workflow.py:284` | context — grep `_RECOVERY_OUTCOMES` |
| Outcome recorded into queue history | `workflow.py:2126-2130` (`ObservedOutcome(at=…, outcome=…)`) | US2 — the recording FR-004 extends |
| Recovery-eligible park to `REJECTED` | `workflow.py:2140-2145` | context |
| `_run_recovery` (sync → attempt → re-enqueue) | `workflow.py:2167`; exhaustion gate `:2205`; sync `:2220`; persona routing `:2244-2249` | US2, US3 — grep `def _run_recovery` |
| `_recovery_attempt` builds `LandingEvidence` | `workflow.py:2303-2316` | US2 — where the fetch result is handed to the prompt |
| `_reenqueue` (salvage → PR → enqueue → poll) | `workflow.py:2376`; enqueue `:2434` | US3 — the futility gate goes before its push/PR steps; grep `def _reenqueue` |
| `_escalate_landing` + `_apply_landing_resolution`; RETRY grant | `workflow.py:2461`, `:2502`, `:2269-2274` | US3 — reuse, with a caller-side meaning for RETRY |
| `LandingEvidence` / `_landing_section` | `factory/workgraph/prompt.py:81`, `:466` | US2, US3 — the fields and rendering to extend |
| `ObservedOutcome`, `Landing`, `PrSnapshot.failing_required_checks`, closed-vocabulary docstring | `factory/mergequeue/models.py:76`, `:84`, `:123`, `:41-47` | US2, US3 |
| `max_recovery_cycles: int = 1` | `factory/mergequeue/models.py:203` | context |
| `CHECKS_FAILED` only when names non-empty | `factory/mergequeue/classify.py:76-77` | US2 — why empty names are unreachable |
| `GhClient` + command table + `_tail`/`_STDERR_TAIL_LIMIT` | `factory/mergequeue/gh.py:111`, `:8-16`, `:314`, `:55` | US2 — new `pr checks` / `run view --log-failed` methods live here |
| Structural guards over `gh.py` source | `tests/test_gh_client.py:200-207` | US2 — new commands must keep them green |
| `sync_landing_branch` — the `asyncio.to_thread` template | `factory/activities/merge_activities.py:391-431` | US2, US3 — **copy this shape**, not `poll_landing`'s (`:367-370`), which blocks the loop and is the open finding `interpreter/gh-subprocess-blocks-event-loop` |
| `open_landing_pr` pushes then drops the sha | `merge_activities.py:311-346`; `push_branch` returns it, `worktree.py:278` | US3 — FR-009's recording point |
| `salvage` commits, never pushes | `factory/workgraph/worktree.py:234-275` | US3 — why `origin/<branch>` stays the rejected tip |
| `render_landing_history` | `factory/notify/messages.py:197` | US2 — FR-008 extends it |
| Activity registration | `factory/worker.py:146-148` | US2, US3 — new activities register here |
| `ScriptedWorld`; sampler + signal send; `script_landing`/`script_sync`; `checks_failed_snapshot` | `tests/test_interpreter.py:837`, `:1276-1289`, `:1100-1139`, `:812` | all — grep `signal_during`, `running_sets` |
| Recovery tests + prompt capture (`prompts_for`) | `tests/test_interpreter.py:4046-4162`, `:4105` | US2, US3 — the assertion style to copy |
| The four coincidence assertions | kill `:4958` (assert `:5000`), pause `:4866` (`:4935`), cap-overlap `:4345` (`:4367`), landing-fanout `:4613` (`:4655` — a fourth site the findings did not name) | US1 |
| The live-guard template (catches `RuntimeError`) | `tests/test_live_capacity.py:101-128` | trap 3 |

## Traps

### Trap 1 — deleting the flaky assertion does not de-flake the test

The tempting fix for US1 is to drop
`assert any(len(running) == 3 …)` and call the durable assertions sufficient.
It does not work: the *premise* is what races. If the kill signal lands before
`us3` is dispatched, `us3` has no worktree and no salvage, so
`salvaged_nodes == {"us1", "us2", "us3"}` at `:5021-5024` fails on the very
next line — the same flake with a different message. Gate the signal on the
declared set being in flight; do not weaken what the test claims.

### Trap 2 — the forbidden fix is retrying the required check

No rerun of a red check, no `pytest-rerunfailures` (also constitution III — an
unapproved dependency), no retry loop anywhere near the queue's gate. The
required check is the one deterministic thing the merge queue trusts; an
automatic retry converts every real regression into "try again until green".
US3's escalation exists precisely so a *human* makes the flake call.

### Trap 3 — markers are decorative, and a live guard must catch what is raised

Nothing passes `-m` in the gate (`factory.yaml` → `uv run pytest -q`) or in CI
(`.github/workflows/test.yml`, same command), so moving a test behind a marker
changes nothing — every live test in this repo skips by guard alone. This spec
needs no live test: every seam is fakeable (`GhRunner`, `ScriptedWorld`), and
reaching for a live one is a design smell here. If one is ever written anyway,
its guard must catch what the client actually raises — temporalio's
`Client.connect` raises `RuntimeError` against a refused port, not `OSError` or
`RPCError`; the correct template is `tests/test_live_capacity.py:101-128`, and
the proof is running the single test with `TEMPORAL_ADDRESS=127.0.0.1:1`. A
guard that never fires in CI is exactly how the deterministic-red incident
started.

### Trap 4 — `gh` runs in activities, on a thread, never in workflow code

The evidence fetch (US2) and the tree comparison (US3) both spawn subprocesses.
Both must be activities, and both must use the `asyncio.to_thread` shape
`sync_landing_branch` already demonstrates (`merge_activities.py:391-431`).
The plausible wrong fix is copying `poll_landing` (`:367-370`), which calls the
synchronous client directly from an async activity and blocks the worker's
event loop — that is the open finding
`interpreter/gh-subprocess-blocks-event-loop`, and this spec must not add
another instance. Nor may it "fix" the existing blockers: that finding's spec
owns them, and touching them here widens the diff for no scenario.

### Trap 5 — the vocabularies are closed and the records are frozen

Do not add a `QueueOutcome` or `LandingState` member for futility — the models
docstring (`models.py:41-47`) closes the set on purpose, because a new member
changes what a PASS means for every consumer. Route futility through the
existing `_escalate_landing` machinery with caller-side handling of `RETRY`.
And every record touched here (`ObservedOutcome`, `Landing`,
`OpenLandingPrResult`, `LandingEvidence`) is a frozen dataclass crossing a
Temporal boundary: new fields take defaults (`()` / `None`) or every history
recorded before this spec fails to deserialize and replay; mutate with
`dataclasses.replace`, never in place.

### Trap 6 — compare trees, never commits

The incident's re-enqueued tip differed from the rejected tip by two salvage
commits while its tree was byte-identical. A sha comparison therefore *never*
fires and the futility gate silently does nothing — the fix ships dead. Compare
`<sha>^{tree}` identities (both commits are present in the node's worktree:
the rejected tip was pushed from it, the sync merged into it). US3-S5 exists to
catch exactly this wrong fix.

### Trap 7 — a failed evidence fetch must not eat the cycle

Between the rejection and the recovery attempt now sits a network call. If a
`GhError` (or an Actions log that has expired) propagates out of the fetch, the
recovery cycle dies to its own evidence-gathering — strictly worse than today's
blindness. The fetch activity returns degraded evidence as data (names +
"log unavailable: <reason>"), never raises for a fetch-shaped failure; FR-007
and US2-S3 pin it.

### Trap 8 — bound the log tail

A CI log can be megabytes. An unbounded tail lands in the prompt and can also
ride into the judge's context, which has already been blown by oversized input
once (the diff-size gap in the judge's budget). Keep a per-check and a total
bound as named constants beside `_STDERR_TAIL_LIMIT` (`gh.py:55`); quote the
*tail*, since pytest and most build tools print the failure summary last.

### Trap 9 — these line numbers rot faster than you think

Both findings carried refs from two days before this plan and both were already
wrong (`:2084` → `:284`/`:2140`; `:4822` → `:4958`). Something may land between
this plan and your worktree. Grep for the construct, not the number:
`_RECOVERY_OUTCOMES`, `def _run_recovery`, `def _reenqueue`,
`failing_required_checks`, `def _landing_section`, `running_sets`,
`signal_during`, `def sync_with_target`. If a citation here does not match the
tree, the tree wins — say so in your commit message.

## Approach

### US1 — gate the signal on the declared in-flight set

1. Give `ScriptedWorld` an opt-in declaration, e.g.
   `signal_after_dispatch_of: frozenset[str] | None`. In `run_agent_attempt`
   (`:1262`), when this node carries a `signal_during` entry and the declaration
   is set: after logging its own dispatch, wait — bounded by the existing
   `WAIT_TIMEOUT_S` — until every declared node id has been observed dispatched
   (the fake already records dispatches), *then* take the running-set sample,
   *then* send the signal. On timeout, record a named marker (e.g.
   `signal_gate_timeout` in `script.calls`) and send anyway, so the test fails
   on the recorded evidence with a reason instead of hanging (FR-002). Give the
   world an opt-in per-node dispatch delay as well (e.g.
   `dispatch_delay_s: dict[str, float]`, slept before the attempt logs its
   dispatch at `:1264-1265`), so US1-S1's premise — the third pickup arriving
   slow — is scripted in the demonstration rather than left to the scheduler's
   mood: without it, a run where no race happens cannot distinguish "the gate
   held the signal" from "the gate was never needed".
2. Convert the kill test (`:4958`), the pause sibling (`:4866`), the
   cap-overlap test (`:4345`) and the landing-fanout test
   (`test_concurrent_passes_each_open_one_pr_and_enqueue_and_the_epic_waits`,
   `:4613`, assert `:4655`) to declare the premise. The cap-overlap and
   landing-fanout tests have no signal; for them, hold each attempt at the same
   barrier before sampling so the size-3 sample is deterministic. The cap-2
   test (`:4379`) asserts an upper bound and needs nothing.
3. Every existing durable assertion stays byte-for-byte (trap 1, FR-003).

### US2 — carry the red check's evidence into the recovery attempt

1. `ObservedOutcome` gains `failing_checks: tuple[str, ...] = ()`; the
   recording site (`workflow.py:2126-2130`) fills it from
   `snapshot.failing_required_checks`. `render_landing_history`
   (`notify/messages.py:197`) appends the names to a `CHECKS_FAILED` line.
2. `GhClient` gains two methods, extending the command-table docstring:
   `pr_checks(pr_number)` → `gh pr checks <n> --json name,state,link`, and
   `run_failed_log(run_id)` → `gh run view <run-id> --log-failed`. The run id
   is parsed from the check's `link` (`…/actions/runs/<id>/job/…`); a link that
   does not parse degrades to name + link only.
3. New activity `fetch_check_failure` in `merge_activities.py`, registered in
   `factory/worker.py`: input pr_number + check names + target_repo; output a
   frozen record of per-check `(name, url, log_tail, note)`. Runs the client
   via `asyncio.to_thread` (trap 4), truncates with bounded constants (trap 8),
   and converts every `GhError` into degraded evidence, never a raise (trap 7).
4. `_run_recovery` calls it only on the `CHECKS_FAILED` + clean-sync path,
   before `_recovery_attempt`; `LandingEvidence` gains the evidence fields
   (defaults keep CONFLICT and replay untouched), and `_landing_section`
   (`prompt.py:466`) renders name, URL and log tail verbatim under the existing
   heading — the 002 discipline: quote, never summarize.

### US3 — record the tip, compare the trees, escalate the futile re-enqueue

1. `push_branch` already returns the pushed sha (`worktree.py:278`);
   `open_landing_pr` stops dropping it — `OpenLandingPrResult` gains
   `pushed_sha: str | None = None` — and the workflow records it on the landing:
   `Landing` gains `enqueued_tip: str | None = None`, set at both enqueue sites
   (first landing and `_reenqueue`).
2. New worktree helper `trees_identical(path, ref_a, ref_b)` comparing
   `rev-parse <ref>^{tree}` ids (trap 6), wrapped by a small activity in the
   `sync_landing_branch` shape.
3. In `_reenqueue`, after salvage and before `prepare_landing_pr`: if
   `landing.enqueued_tip` is set and the worktree HEAD's tree equals the
   rejected tip's tree, skip the enqueue and call `_escalate_landing`; `RETRY`
   proceeds with the interrupted enqueue (the same cycle — `recovery_cycles`
   is not incremented again), everything else routes through
   `_apply_landing_resolution` unchanged. US3-S1's "naming the futility" needs
   one small seam: `_escalate_landing` today sends only
   `render_landing_history(record.landing)` as `history_summary` (`:2480`), so
   give it an optional note (default `None`, appended to the summary) and pass
   the futility sentence from the gate — the operator must see *why* this
   escalation is not the ordinary exhaustion one. An absent `enqueued_tip`
   (pre-spec history) proceeds as today — absence is never futility.
4. The sync-moved-nothing fact: `_run_recovery` already holds both refs —
   `record.base_ref` before the sync and `sync.base_ref` after. If they are
   equal, pass a `base_unmoved=True` flag into the evidence handed to
   `_recovery_attempt`, and `_landing_section` renders the one sentence FR-013
   asks for. No new git call needed.

## Complexity Tracking

| Thing | Why it is not simpler |
| --- | --- |
| A harness gate instead of deleting one assertion | Deleting it leaves the same flake in the salvage assertion (trap 1); the premise is what must become deterministic. |
| A new fetch activity instead of widening `poll_landing` | The poll runs every 60s on the queue's beat; fetching logs there would spend a subprocess per poll and block the loop the finding already names. The fetch runs once, on rejection. |
| Recording `enqueued_tip` instead of reading `origin/<branch>` at compare time | The remote ref is a moving convention ("nothing else pushes") — the recorded sha is a fact, survives an interleaved push, and makes the comparison pure local `rev-parse`. |
| Tree comparison as an activity | Workflow code must stay deterministic and side-effect free (constitution IV); `git rev-parse` is a side effect. |
| Extending `LandingEvidence` rather than a new prompt section | The landing rejection section already exists and is already tested; a second section would give the agent two places to look for one rejection. |

## Verification

`uv run pytest -q` green, in the worktree, before and after each story. The
tests that did not exist before are the point: a kill test whose premise cannot
race, a recovery prompt containing a scripted CI log line, and a futile
re-enqueue that escalates instead of spending a CI run. If any of them passes
before its implementation task runs, the test is wrong — constitution II.
Nothing here needs a live service; every new test runs through `ScriptedWorld`,
`FakeGh`/`GhRunner`, or `tmp_path` git repos, exactly like the suites it
extends.
