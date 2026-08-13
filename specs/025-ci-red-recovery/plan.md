# Plan: A red check that reaches no one

All line references below were **re-verified against the tree at commit
`f711f8e` on 2026-08-13**, replacing the 2026-08-11 `9594787` numbers this plan
originally carried. They are cited so you can find the code, not so you can
trust the numbers — see trap 9. Two rot events are already on the record: the
findings' refs were wrong within two days of the audit, and every
`workflow.py` anchor in the first draft of this plan had drifted ~35 lines by
the time of the re-verification, because 026–031 and 036–038 landed in between.
Assume a third.

One re-verification finding changes an instruction rather than a number:
**trap 3's live-guard template has been rewritten** since this plan was
drafted. Read that trap, not your memory of it.

## Reuse inventory

| What | Where | Used by |
| --- | --- | --- |
| `_RECOVERY_OUTCOMES = {CHECKS_FAILED, CONFLICT}` | `factory/workgraph/workflow.py:286` | context — grep `_RECOVERY_OUTCOMES` |
| Outcome recorded into queue history | `workflow.py:2164` (`ObservedOutcome(at=…, outcome=…)`) | US2 — the recording FR-004 extends |
| Recovery-eligible park to `REJECTED` | `workflow.py:2179` | context |
| `_run_recovery` (sync → attempt → re-enqueue) | `workflow.py:2202`; exhaustion gate `:2238-2240`; sync `:2256`; persona routing `:2280-2293` | US2, US3 — grep `def _run_recovery` |
| `_recovery_attempt` builds `LandingEvidence` | `workflow.py:2314` | US2 — where the fetch result is handed to the prompt |
| `_reenqueue` (salvage → PR → enqueue → poll) | `workflow.py:2413`; salvage `:2435`; `prepare_landing_pr` `:2445`; enqueue `:2471` | US3 — the futility gate goes after the salvage and before `prepare_landing_pr`; grep `def _reenqueue` |
| `_escalate_landing` + `_apply_landing_resolution`; RETRY grant | `workflow.py:2498`, `:2539`, `:2224` (docstring) / `:2238-2240` (the `granted` gate) | US3 — reuse, with a caller-side meaning for RETRY |
| `LandingEvidence` / `_landing_section` | `factory/workgraph/prompt.py:81`, `:466` | US2, US3 — the fields and rendering to extend |
| `ObservedOutcome`, `Landing`, `PrSnapshot.failing_required_checks`, closed-vocabulary docstring | `factory/mergequeue/models.py:76`, `:84`, `:123`, `:41-47` | US2, US3 |
| `max_recovery_cycles: int = 1` | `factory/mergequeue/models.py:203` | context |
| `CHECKS_FAILED` only when names non-empty | `factory/mergequeue/classify.py:76-77` | US2 — why empty names are unreachable |
| `GhClient` + command table + `_tail`/`_STDERR_TAIL_LIMIT` | `factory/mergequeue/gh.py:111`, `:8-16`, `:328`, `:55` | US2 — new `pr checks` / `run view --log-failed` methods live here |
| Structural guards over `gh.py` source | `tests/test_gh_client.py:178-215` | US2 — new commands must keep them green; `test_no_code_path_passes_delete_branch` greps the module source, so a new command string is inside its blast radius |
| `sync_landing_branch` — the `asyncio.to_thread` template | `factory/activities/merge_activities.py:391-431` | US2, US3 — **copy this shape**, not `poll_landing`'s (`:367-370`), which blocks the loop and is the open finding `interpreter/gh-subprocess-blocks-event-loop` |
| `open_landing_pr` pushes then drops the sha | `merge_activities.py:311-346`; `push_branch` returns it, `worktree.py:319` | US3 — FR-009's recording point |
| `salvage` commits, never pushes | `factory/workgraph/worktree.py:275-317` | US3 — why `origin/<branch>` stays the rejected tip |
| `render_landing_history` | `factory/notify/messages.py:197` | US2 — FR-008 extends it |
| Activity registration | `factory/worker.py:146-150` | US2, US3 — new activities register here |
| `ScriptedWorld`; `run_agent_attempt`; sampler + signal send; `script_landing`/`script_sync`; `checks_failed_snapshot` | `tests/test_interpreter.py:855`, `:1286`, `:1299-1312`, `:1123`/`:1139`, `:830` | all — grep `signal_during`, `running_sets` |
| Recovery tests + prompt capture (`prompts_for`) | `tests/test_interpreter.py:4200-4400`; `prompts_for` defined `:1090`, the recovery-prompt reads at `:4259` and `:4287` | US2, US3 — `script.prompts_for("us1")[1]` is the recovery prompt; that is the assertion style to copy |
| The four coincidence assertions | kill `test_kill_with_n_in_flight_salvages_every_one_before_terminating` `:5112` (assert `:5154`), pause `test_pause_with_n_in_flight_starts_nothing_new_and_lets_all_finish` `:5020` (`:5089`), cap-overlap `test_all_ready_nodes_are_in_flight_at_once_up_to_the_cap` `:4499` (`:4521`), landing-fanout `test_concurrent_passes_each_open_one_pr_and_enqueue_and_the_epic_waits` `:4767` (`:4809`) | US1 — the names are the durable handle; grep `len(running) == 3` and expect exactly four hits |
| The live-guard template (**socket probe**, not an exception list) | `tests/test_live_capacity.py:101-131` | trap 3 |

## Traps

### Trap 1 — deleting the flaky assertion does not de-flake the test

The tempting fix for US1 is to drop
`assert any(len(running) == 3 …)` and call the durable assertions sufficient.
It does not work: the *premise* is what races. If the kill signal lands before
`us3` is dispatched, `us3` has no worktree and no salvage, so
`salvaged_nodes == {"us1", "us2", "us3"}` at `:5175-5177` fails a few lines
later — the same flake with a different message. Gate the signal on the
declared set being in flight; do not weaken what the test claims.

### Trap 2 — the forbidden fix is retrying the required check

No rerun of a red check, no `pytest-rerunfailures` (also constitution III — an
unapproved dependency), no retry loop anywhere near the queue's gate. The
required check is the one deterministic thing the merge queue trusts; an
automatic retry converts every real regression into "try again until green".
US3's escalation exists precisely so a *human* makes the flake call.

### Trap 3 — markers are decorative, and a live guard probes rather than catches

Nothing passes `-m` in the gate (`factory.yaml` → `uv run pytest -q`) or in CI
(`.github/workflows/test.yml`, same command), so moving a test behind a marker
changes nothing — every live test in this repo skips by guard alone. This spec
needs no live test: every seam is fakeable (`GhRunner`, `ScriptedWorld`), and
reaching for a live one is a design smell here.

If one is ever written anyway, **the template changed after this plan was
first drafted and the older instruction is now wrong.** The guard is no longer
an exception list. `tests/test_live_capacity.py:101-131` now probes *positively*
— `_temporal_reachable()` opens a TCP socket to the gRPC port and skips on
`OSError`, with the `except (OSError, RuntimeError)` around `Client.connect`
kept only as a second line. Its own docstring says why: "a guard that
enumerates exception types misses the next SDK release." Copy the probe, not
the catch. The proof is unchanged and non-negotiable — run the single test with
`TEMPORAL_ADDRESS=127.0.0.1:1` and paste the result (trap 10). A guard that
never fires in CI is exactly how the deterministic-red incident started, and
028/us3 burned three CI runs and two kills on this same class of mistake before
landing on 2026-08-13.

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

Twice now, measured. The findings carried refs from two days before this plan
and both were already wrong (`:2084` → `:286`/`:2179`; `:4822` → `:5112`). Then
the plan's own numbers rotted before dispatch: every `workflow.py` anchor moved
~35 lines and every `test_interpreter.py` anchor moved 250–500 as 026–031 and
036–038 landed, which is why the table above was rewritten at `f711f8e`.
Something will land between that re-verification and your worktree too.

Grep for the construct, not the number: `_RECOVERY_OUTCOMES`,
`def _run_recovery`, `def _reenqueue`, `def _recovery_attempt`,
`def _escalate_landing`, `failing_required_checks`, `def _landing_section`,
`running_sets`, `signal_during`, `def push_branch`, `def salvage`. If a
citation here does not match the tree, the tree wins — say so in your commit
message.

### Trap 10 — the proof is part of the deliverable, not a step you performed

Every claim this spec makes about *timing* — a premise that no longer races, a
guard that fires with no server up — is invisible in a diff. The judge sees the
diff and the criteria and nothing else (constitution VIII): it cannot run your
tests, read your terminal, or take your word that you checked.

So where a scenario turns on runtime behaviour, the evidence is committed with
the code, as tool output pasted verbatim into the test file's own comment
block — never summarized, never described, never left in the commit message.
For US1 that means the actual `pytest` lines from a repeat run of each
converted test (`-p no:randomly --count` is not available; run the four tests
in a loop and paste the tallies), and for any live guard the literal output of

```
TEMPORAL_ADDRESS=127.0.0.1:1 uv run pytest <the single test> -q
```

This is not ceremony. On 2026-08-13 an agent on 028/us3 fixed its story
correctly and skipped the paste, and the only reason the evidence exists is
that an operator re-ran the command by hand afterwards. The next story that
does that will be judged on an assertion nobody can check.

## Approach

### US1 — gate the signal on the declared in-flight set

1. Give `ScriptedWorld` an opt-in declaration, e.g.
   `signal_after_dispatch_of: frozenset[str] | None`. In `run_agent_attempt`
   (`:1286`), when this node carries a `signal_during` entry and the declaration
   is set: after logging its own dispatch, wait — bounded by the existing
   `WAIT_TIMEOUT_S` — until every declared node id has been observed dispatched
   (the fake already records dispatches), *then* take the running-set sample
   (`:1299-1305`), *then* send the signal (`:1307-1312`). On timeout, record a
   named marker (e.g.
   `signal_gate_timeout` in `script.calls`) and send anyway, so the test fails
   on the recorded evidence with a reason instead of hanging (FR-002). Give the
   world an opt-in per-node dispatch delay as well (e.g.
   `dispatch_delay_s: dict[str, float]`, slept before the attempt logs its
   dispatch at `:1287-1288`), so US1-S1's premise — the third pickup arriving
   slow — is scripted in the demonstration rather than left to the scheduler's
   mood: without it, a run where no race happens cannot distinguish "the gate
   held the signal" from "the gate was never needed".
2. Convert all four `assert any(len(running) == 3 …)` sites to declare the
   premise — the kill test (`:5112`, assert `:5154`), the pause sibling
   (`:5020`, `:5089`), the cap-overlap test
   (`test_all_ready_nodes_are_in_flight_at_once_up_to_the_cap`, `:4499`,
   `:4521`) and the landing-fanout test
   (`test_concurrent_passes_each_open_one_pr_and_enqueue_and_the_epic_waits`,
   `:4767`, `:4809`). The cap-overlap and landing-fanout tests have no signal;
   for them, hold each attempt at the same barrier before sampling so the
   size-3 sample is deterministic.

   Two neighbours look like they belong on that list and do not — leave both
   alone, and do not widen the diff to reach them. `:4554` and `:4665` assert
   *upper* bounds (`<= 2`, `<= 1`), which no race can falsify.
   `test_a_slot_is_refilled_the_moment_a_node_reaches_terminal` (`:4533`) reads
   `script.running_sets[2]` positionally (`:4569`), which is safe only because
   the cap forces `us3` to dispatch third and `all_passing()` gives each node
   exactly one attempt; it is not a flake today. If your harness change alters
   how many samples get appended, that index breaks — and then it is yours to
   fix, in this same diff, rather than a separate concern.
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

Green is necessary and not sufficient. US1's whole claim is that a test that
*used to* pass ~95% of the time now passes every time, and one green run is
equally consistent with both. Repeat the four converted tests enough times to
mean something and commit the tallies as pasted output — see trap 10.
