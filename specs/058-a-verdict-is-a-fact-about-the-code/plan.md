# Implementation Plan: a verdict is a fact about the code

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## Read the evidence before the plan

`evidence/055-us1-attempt1-gate.txt` — in full,
`specs/058-a-verdict-is-a-fact-about-the-code/evidence/055-us1-attempt1-gate.txt`
— is the captured gate output of the run this spec exists for: 141 lines, the
real `pytest` tail, not a summary. The failing assertion, the passing assertion
above it, and the suite counts are all in there. **Read it first.** This spec's
diagnosis has now been wrong twice, both times in the direction that reading the
source and not the failure produces, and the second wrong version is the one an
earlier draft of this plan told you to fix.

## What already exists, and where

**The test that fires, whole.** `tests/test_us4_boundary.py:202` — `test_hanging_agent_is_killed_at_deadline_with_no_survivors`. Nothing in this
file has changed since 2026-08-15, so every line number below is stable, and any
disagreement you find is an authoring error in an earlier draft rather than
drift:

```python
    adapter = ClaudeCodeAdapter(executable=str(STUB_AGENT_PATH), grace_s=1.0)
    result = await adapter.run_attempt(
        _context(str(worktree), str(per_node_home), str(repo), session_id=session_id, timeout_s=3),
        factory_root=factory_root,
    )

    assert result.termination == "timeout"
```

- the bwrap skip guard: `tests/test_us4_boundary.py:209` — `test_hanging_agent_is_killed_at_deadline_with_no_survivors`,
  whose predicate is `tests/test_us4_boundary.py:165` — `_bwrap_available`
- the scripted hang, `ignore_sigterm=True, spawn_child=True, sleep_s=300.0`:
  `tests/test_us4_boundary.py:104` — `_script_hang`
- the tightened grace, `grace_s=1.0`: `tests/test_us4_boundary.py:224` — `test_hanging_agent_is_killed_at_deadline_with_no_survivors`
- the launch itself, one awaited call: `tests/test_us4_boundary.py:225` — `test_hanging_agent_is_killed_at_deadline_with_no_survivors`
- the attempt deadline, `timeout_s=3`: `tests/test_us4_boundary.py:226` — `test_hanging_agent_is_killed_at_deadline_with_no_survivors`
- the assertion that **passed**: `tests/test_us4_boundary.py:230` — `test_hanging_agent_is_killed_at_deadline_with_no_survivors`
- the assertion that **failed**: `tests/test_us4_boundary.py:236-238`
- the reap window, `await asyncio.sleep(0.2)`:
  `tests/test_us4_boundary.py:241` — `test_hanging_agent_is_killed_at_deadline_with_no_survivors`
- the two survivor checks it gates: `tests/test_us4_boundary.py:245-251`

**The stub's start-up sequence, in order.** `tests/stub_agent.py:385` — `main`.
Everything between the first line and the handler is a candidate delay point, and
FR-002's knob is a delay inserted at one of them:

| order | line | what happens |
|---|---|---|
| 1 | `tests/stub_agent.py:389` — `main` | `load_control(home)` reads the control file |
| 2 | `tests/stub_agent.py:390` — `main` | `_claim_record_dir(cwd)` creates `.stub-agent/<n>/` |
| 3 | `tests/stub_agent.py:394` — `main` | `_spawn_child` forks a second process when scripted |
| 4 | 396-404 | argv, env, cwd and process records are written |
| 5 | `tests/stub_agent.py:407` — `main` | `recorder.write(STDIN_FILE, _read_stdin())` — blocks until the adapter's feeder closes the pipe |
| 6 | `tests/stub_agent.py:409` — `on_term` | the handler is *defined* |
| 7 | `tests/stub_agent.py:414` — `main` | `signal.signal(signal.SIGTERM, on_term)` — the handler is *installed* |
| 8 | `tests/stub_agent.py:447` — `main` | `time.sleep(control.sleep_s)` — the scripted hang |

The comment immediately above step 5 names the readiness file a test should poll
for (`tests/stub_agent.py:405-406`). **No test in either boundary suite polls for
it — but three other modules do**, and that is the next section.

**Only steps 3 through 8 are knobbable, and FR-002 is written over those.** Two
lines of the stub fix the range and neither is negotiable. The knob is *read* out
of the control file by step 1 (`tests/stub_agent.py:389` — `main`), so "delay
before step 1" cannot be expressed at all. And the record directory the knob echo
has to be written into does not exist until step 2
(`tests/stub_agent.py:390` — `main`), so the stub must claim the recorder and
write its echo *before* it sleeps — which makes a delay "at step 2"
indistinguishable from one at step 3, and makes a delay applied before the echo
write leave no echo on disk at all, because a delay longer than the attempt's
deadline kills the stub where it stands and nothing after the sleep runs. The
other end of the range is step 8: a delay after the handler is installed
*passes*, so that column has a summary line and an echo and no failure to paste.
That is why FR-002's artifact set is per-outcome — summary line and echo always,
the `pytest` failure only where the run fails — and why demanding all three at
every point would have specified a transcript no implementer could produce.

**The readiness convention already exists, three times over.** An earlier draft
of this plan said flatly "No test polls for it". That is false outside the
boundary suites, and it is the single fact that most changes what US2 is for:

- `tests/test_adapter.py:292` — `stub_is_up` — globs `.stub-agent/*/stdin.txt`,
  one argument, carries the docstring explaining *why* the stdin record is the
  right key.
- `tests/test_agent_activities.py:408` — `stub_is_up` — the same body and the
  same docstring, a separate copy.
- `tests/test_us1_detector.py:198` — `stub_is_up` — a **different signature**,
  `(worktree, attempt)`, keying on `.stub-agent/<attempt>/stdin.txt` rather than
  globbing. Any promoted single function has to serve both shapes.

There are **eleven** live `wait_until` calls in the tree and **seven** of them
poll `stub_is_up` — an earlier draft of this plan said eight and opened its list
with a call that waits on something else entirely. The seven:
`tests/test_adapter.py:981` — `test_a_live_process_group_from_a_previous_run_is_reaped_before_relaunch`,
`tests/test_adapter.py:1006` — `test_the_pid_file_names_this_attempts_group_and_is_removed_on_exit`,
`tests/test_agent_activities.py:998` — `test_a_cancelled_attempt_dies_keeps_its_evidence_and_reports_killed`,
and four in `tests/test_us1_detector.py` —
`tests/test_us1_detector.py:271` — `test_agent_modifying_tracked_file_in_target_repo_files_finding`,
`tests/test_us1_detector.py:403` — `test_detector_runs_on_completed_agent_error_timeout_and_killed`,
`tests/test_us1_detector.py:446` — `test_agent_truncating_runtime_root_store_files_finding` and
`tests/test_us1_detector.py:491` — `test_detector_reports_even_when_runtime_root_is_deleted`.
The other four poll something else and are still US2's, because US2 deletes the
definition they call:
`tests/test_adapter.py:832` — `test_a_run_that_outlives_its_deadline_is_terminated_and_classified_timeout`
waits on `not pid_alive(grandchild)`,
`tests/test_adapter.py:1112` — `test_the_pid_record_never_lands_inside_the_worktree` on a
file appearing, `tests/test_adapter.py:1414` — `test_a_ferry_question_ships_upward_once` on a
list growing, and
`tests/test_agent_activities.py:1010` — `test_a_cancelled_attempt_dies_keeps_its_evidence_and_reports_killed`
on a pid dying. The shape that makes a readiness wait expressible at all is
`tests/test_adapter.py:979` — `test_a_live_process_group_from_a_previous_run_is_reaped_before_relaunch`:
`asyncio.create_task(run_attempt(...))`, then `await wait_until(...)`, then
`await run` in a `finally`.

**The knob mechanism FR-002 extends already exists.** `Control` is a frozen
dataclass (`tests/stub_agent.py:139` — `Control`) whose fields are one per
assertion the adapter contract calls for; `ignore_sigterm` is one
(`tests/stub_agent.py:152` — `Control`), consumed at
`tests/stub_agent.py:411` — `on_term`. `write_control`
(`tests/stub_agent.py:183` — `write_control`) raises `TypeError` on an unknown
field rather than ignoring it, and `as_dict`
(`tests/stub_agent.py:167` — `as_dict`) is written out field by field — a new
field that is not added *there* is silently dropped on the round trip. The
record directory the stub writes into is claimed per launch and written through
`tests/stub_agent.py:305` — `write`, which is where FR-002's knob echo goes.

**Why `signals=[]` means the handler never ran.** `Invocation.signals`
(`tests/stub_agent.py:248` — `signals`) reads the signals file on access and
returns `[]` when it does not exist (`tests/stub_agent.py:256` — `signals`).
`_Recorder.append` flushes every line (`tests/stub_agent.py:308` — `append`), and
`_Recorder.signal` writes through it (`tests/stub_agent.py:313` — `signal`), so a
handler that ran left a line on disk.

**Why the drain had already finished.** `invocations` reads `stdin.txt`
unconditionally when it builds an `Invocation`
(`tests/stub_agent.py:278` — `invocations`), and `last_invocation`
(`tests/stub_agent.py:287` — `last_invocation`) raises `LookupError` when there is
no record at all. The captured run got neither: it got an `AssertionError` on the
line after `last_invocation` returned. Read that as fact — it is the single most
load-bearing sentence in this plan.

**What the deadline actually does.** `factory/workgraph/adapter.py:1144` — `run_attempt`
launches the backend and `factory/workgraph/adapter.py:1148` — `run_attempt`
immediately enters `factory/workgraph/adapter.py:1290` — `_monitor`
with `timeout_s`. The clock starts at launch, inside one awaited call, so there
is no seam at which a test could wait for readiness *before* the deadline begins.
At expiry, `factory/workgraph/adapter.py:1461` — `_reclaim` sends SIGTERM to the
group, `factory/workgraph/adapter.py:1463` — `_reclaim` waits `grace_s`, and
`factory/workgraph/adapter.py:1464` — `_reclaim` sends SIGKILL.

**The boundary the signal has to cross.** The agent is launched under
`--unshare-pid --die-with-parent` (`factory/workgraph/adapter.py:621` — `_build_argv`), so bwrap holds a PID namespace and the stub is inside it. Both
share one host process group, so `os.killpg` reaches both — and bwrap exiting on
its own TERM collapses the namespace with an uncatchable SIGKILL. The binary
that has to be present for any of this to run is
`/usr/bin/bwrap`, named at `factory/workgraph/adapter.py:334`; without it the
whole test skips and this story is blocked, not adapted (trap 6).

**The helper US2 promotes exists FIVE times, in TWO variants.** An earlier draft
said three, byte-identical. Both halves are wrong. Variant A — no docstring,
default `20.0`, loop clock — is at `tests/test_us4_boundary.py:146` — `wait_until`,
`tests/test_us3_boundary.py:147` — `wait_until` and
`tests/test_us1_detector.py:175` — `wait_until`:

```python
async def wait_until(
    predicate: Callable[[], bool], *, what: str, timeout_s: float = 20.0
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"timed out after {timeout_s}s waiting for {what}")
```

Variant B — docstring, default `PATIENCE_S`, `time.monotonic()` — is at
`tests/test_adapter.py:280` — `wait_until` and
`tests/test_agent_activities.py:396` — `wait_until`:

```python
async def wait_until(
    predicate: Callable[[], bool], *, what: str, timeout_s: float = PATIENCE_S
) -> None:
    """Poll `predicate` until it holds, or fail naming what never happened."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"timed out after {timeout_s}s waiting for {what}")
```

Three facts about that pair, each of which changes an instruction. `PATIENCE_S`
is `20.0` in both modules that define it (`tests/test_adapter.py:146`,
`tests/test_agent_activities.py:190`), so the two variants agree on the bound
and differ only in clock source and documentation — promoting either changes no
timing. Neither boundary suite ever *calls* its own copy: `wait_until` is dead
code in `tests/test_us4_boundary.py` and `tests/test_us3_boundary.py` until US1
lands its bounded reap wait, so US2 deletes two definitions there and converts no
call site. And neither body reports the **elapsed** wait, which is the delta
FR-004 asks for — US1 adds it to the `tests/test_us4_boundary.py` copy, and that
mutated body is what US2 promotes.

**Three near-misses that share the prefix and are not in the population.**
`tests/test_escalation_workflow.py:300` — `wait_until_waiting` and
`tests/test_escalation_workflow.py:319` — `wait_until_settled` poll Temporal
state through their own signatures and are imported by
`tests/test_ergane_escalations.py`; `tests/test_110_us1_demo_first_boot.py:193` — `_wait_until`
is a private bool-returning poll with five call sites inside its own module. US2
promotes none of them and edits none of those modules. They matter to FR-006
rather than to FR-005: a census that matches `def wait_until` as *text* refuses
`tests/test_escalation_workflow.py`, a module this story may not touch and for
which FR-006 — unlike FR-007 — grants no exemption mechanism, and the escape an
implementer reaches for then is the unstated self-exemption trap 10 calls a
census a judge can refuse. Match the two names exactly, with `ast`, on the
`tests/test_123_no_fixture_pins_the_builder.py:445` — `test_no_fixture_leases_a_virtual_key_against_a_registry_persona`
precedent, and all three fall outside the population by construction.

**A second call site with the same assertion and a tighter deadline.**
`tests/test_adapter.py:799` — `test_a_run_that_outlives_its_deadline_is_terminated_and_classified_timeout`
scripts the same hang (`tests/test_adapter.py:815` — `test_a_run_that_outlives_its_deadline_is_terminated_and_classified_timeout`) and
makes the same TERM assertion (`tests/test_adapter.py:828` — `test_a_run_that_outlives_its_deadline_is_terminated_and_classified_timeout`) at
`DEADLINE_S = 1` (`tests/test_adapter.py:142`). It runs on the host backend, so it
boots faster, but it is the same shape and the same risk. Note that it *already*
ends in a bounded wait (`tests/test_adapter.py:832` — `test_a_run_that_outlives_its_deadline_is_terminated_and_classified_timeout`),
so US2's work at this site is an import change, not a restructure.

**Where the promoted helper goes.** A new module under `tests/` — `tests/` is a
package (`tests/__init__.py` exists) and the tree already imports across it as
`from tests.stub_agent import ...` in **twelve** modules
(`grep -rl 'tests\.stub_agent' tests/*.py`; nineteen paths match repo-wide, but
seven of those are stale copies under `.claude/worktrees/`, which is why the
matcher is written down here — trap 7). So
`from tests.agent_wait import wait_until, stub_is_up` needs no new machinery, and
a dedicated support module is the convention being *followed* rather than
invented: `tests/` already holds nine non-`test_` support modules —
`fake_forge.py`, `fake_gh.py`, `fake_schedules.py`, `judge_proxy.py`,
`page_holds_true.py`, `reference_flow.py`, `roadmap_script.py`, `stub_agent.py`
and `target_repo.py`.

**Not `tests/stub_agent.py`** — trap 5 says why, and it is measured.
**Not `tests/conftest.py`** either, and an earlier draft of this plan gave a
false reason for that, in the one section whose whole job is to describe the
tree. It said nothing in the tree imports a symbol from conftest by name.
Fifteen modules do (`grep -rl 'from tests.conftest import' tests/*.py`), so
importing from conftest by name is itself an established convention here. The
reason that survives measurement is smaller and sufficient: `tests/conftest.py`
is 840 lines and pytest auto-loads it into every session, so a two-symbol
readiness helper belongs in its own module beside the other nine rather than
inside the file every test in the repository already pays for. FR-005 now names
both exclusions itself, so this is a criterion the judge can hold the diff to
rather than a preference this plan holds — check it there before you choose a
filename. That new module is also the one exemption FR-006's census carries: it
defines both symbols, so a census written without the exemption refuses the
promotion it exists to prove.

**The guard precedent for US3, and the one that is wrong.**
`tests/test_123_no_fixture_pins_the_builder.py:445` — `test_no_fixture_leases_a_virtual_key_against_a_registry_persona` reads this
repository's own **test** source with `ast` and refuses a mechanism; it is driven
against synthetic source at
`tests/test_123_no_fixture_pins_the_builder.py:510` — `test_the_guard_catches_the_pin_this_story_removes`, and kept honest by
`tests/test_123_no_fixture_pins_the_builder.py:534` — `test_the_guard_reads_the_key_leasing_fixtures_that_exist_today`. That is the
pattern. `tests/test_final_sweep.py` is **not**: its sweeps are parametrized over
`COMPONENT_MODULES` (`tests/test_final_sweep.py:104`), which is
`COMPONENT_ROOT.rglob("*.py")` — production modules under `factory/`, never
tests. Its two transferable ideas are the exemption-is-a-decision test
(`tests/test_final_sweep.py:625` — `test_the_compose_exemption_buys_exactly_one_compound_and_no_more`) and the
non-vacuity guard (`tests/test_final_sweep.py:684` — `test_the_source_sweep_actually_read_the_component`).

**Context, not a target.** `factory/verify/gates.py:99-102` is the comment that
names this hazard; `factory/verify/gates.py:110` is
`DEFAULT_GATE_CONCURRENCY: int = 1`, which bounds gates and not agents. Out of
scope, and named here so nobody re-derives it.

## Traps

**Trap 1 — The mechanism is NOT established, and an earlier draft of this plan
said it was.** That draft named two candidates and asserted that candidate 1
("SIGTERM arrives before `tests/stub_agent.py:414` — `main` executes because the
stub must first drain stdin at `tests/stub_agent.py:407` — `main`") "predicts
`signals=[]` exactly, which is what was captured". It is falsified by the same
evidence file: `invocations` reads `stdin.txt` unconditionally
(`tests/stub_agent.py:278` — `invocations`), so the drain had finished before the
record was read. The window that remains between steps 5 and 7 of the table above
is a closure definition and one call. FR-002 exists so you demonstrate the
signature by experiment instead of by argument, and so the stub records enough to
tell the two candidates apart. The wrong move is to open with a fix for the
mechanism this plan used to assert.

**Trap 2 — The reap window at `tests/test_us4_boundary.py:241` — `test_hanging_agent_is_killed_at_deadline_with_no_survivors` is not what fired,
and it is still yours to convert.** `await asyncio.sleep(0.2)` gates the survivor
checks at `tests/test_us4_boundary.py:245-251`, and those **passed** in the
captured run. Changing it fixes nothing that fired. But it is a fixed sleep
standing between a launch and an assertion about another process's state, inside
the very test FR-004 governs, and FR-004 is US1's — so US1 converts it and US1-S5
is the check. An earlier draft assigned it to US2; that contradicted the Work
Graph and is corrected here. The wrong move in both directions: shipping a diff
that changes only this line and calling it the fix, or leaving it in place because
"the plan said it was somebody else's".

**Trap 3 — There is no seam at which the test can wait before the clock starts,
and US2 is scoped around that rather than against it.**
`factory/workgraph/adapter.py:1144` — `run_attempt` launches the process and
`factory/workgraph/adapter.py:1148` — `run_attempt` enters the monitor in the same
awaited call, so "wait for readiness, *then* start the deadline" is not
expressible at this call site. Every launch in both boundary suites is exactly
that shape — `tests/test_us4_boundary.py:225` — `test_hanging_agent_is_killed_at_deadline_with_no_survivors`,
`tests/test_us4_boundary.py:279` — `test_attempt_inside_boundary_archives_stdout_and_transcript`,
`tests/test_us3_boundary.py:207` — `test_git_plumbing_succeeds_inside_bwrap_boundary`
and seven more — and neither suite contains a single `asyncio.create_task`. An
earlier draft of this spec therefore asked US2 to "convert every racing launch to
the shared helper", an instruction with no meaning at any call site it named: a
readiness wait cannot run while an inline-awaited call is in flight, and one
placed after it returns is a no-op because the stub is already dead. That
requirement is gone. US2 unifies the helper and its predicate; the launch shape
is out of scope and `### What this spec is not` says so. The fix for FR-001
therefore lives in the stub's own ordering (a test double, freely editable) or in
what the test observes — never in production code, which this spec does not
touch. The wrong move is to restructure ten boundary launches onto
`asyncio.create_task` because a census could not otherwise find anything to
count.

**Trap 4 — A test that cannot fail is worse than a flaky one.** Every reflex that
makes this green — widening a wait until anything settles, dropping the signal
assertion, `pytest.mark.skip`, `xfail`, a retry loop — ships the boundary defect
the test exists to catch. FR-003 forbids all of it and US1-S3 requires the fixed
test to go red on a real leak. Prove that by mutation, not by argument: break the
namespace teardown, capture the red run, restore the tree, and paste all three
into the diff. The wrong move is to argue in the PR body that it would still
fail.

**Trap 5 — The knob is the stub's, and the shared helper is not.**
`tests/stub_agent.py` is a test double, so nothing under `factory/` may import
it, detect it, or branch on it (FR-008) — and US1 proves that from its own diff
(US1-S7), because a guard for it cannot be written red-first: nothing under
`factory/` names the knob before this spec or after it. A new `Control` field
must be added to the dataclass (`tests/stub_agent.py:139` — `Control`) **and** to
`as_dict` (`tests/stub_agent.py:167` — `as_dict`), which is written out field by
field; a field missing from `as_dict` round-trips as its default and every
experiment silently runs unknobbed — which reads exactly like "the mechanism did
not reproduce". That failure mode is also why FR-002 asks the stub to echo the
knob it actually applied into its own record directory
(`tests/stub_agent.py:305` — `write`): an unknobbed run and a knobbed one are
otherwise indistinguishable in the transcript. The other half of this trap points
the other way: **do not put US2's promoted `wait_until` in this file.**
`tests/stub_agent.py` is not a test-support module, it is the program the adapter
launches (`#!/usr/bin/env python3`, mode 0775, `main()` at
`tests/stub_agent.py:385` — `main`), and its own docstring argues it must stay a
minimal, directly-executable program. Its imports at `tests/stub_agent.py:56-65`
are `json, os, re, signal, subprocess, sys, time` — no `asyncio`. An
`async def wait_until` there forces `import asyncio` at module scope on every
launch: measured on this host with `python3 -X importtime` (CPython 3.12.3),
`asyncio` costs 18-26 ms cumulative against about 7 ms for `subprocess`, the
stub's heaviest current import. That is 18-26 ms added to the stub's start-up —
the exact window US1 exists to characterise, and the window between the stdin
drain (`tests/stub_agent.py:407` — `main`) and the handler installation
(`tests/stub_agent.py:414` — `main`) that produces the captured `signals=[]`. US2
would measurably worsen the race US1 just fixed, and no gate in this repository
would notice. Put it in a new module under `tests/` instead.

**Trap 6 — Without `bwrap` in your own worktree, US1 is blocked, not adapted —
and `-q` cannot tell you which.**
`tests/test_us4_boundary.py:209` — `test_hanging_agent_is_killed_at_deadline_with_no_survivors` skips the whole test
when `/usr/bin/bwrap` (`factory/workgraph/adapter.py:334`) is missing or not
executable (`tests/test_us4_boundary.py:165` — `_bwrap_available`), so "the suite
is green" is compatible with "the test never ran". This is not hypothetical:
occurrence 3 of `ci/the-deadline-boundary-test-fails-intermittently-in-the-full-suite`
(2026-08-29, epic-089/us3) records the agent's own run reporting *58* skipped
while its gate reported *57* skipped and one failure — the test skipped for the
agent and ran for the gate, and the story paid a full attempt for the difference.
Two instructions follow, and both are load-bearing. **First**: if the test skips
in your worktree, stop. Report blocked, paste the skip line, and do not derive,
estimate or reconstruct any transcript from the stub's source — every outcome in
the matrix is predictable on paper (trap 12), so a reconstructed transcript is
both easy to write and worthless, and it is the cheapest wrong move available to
a blocked implementer. **Second**: the declared gate is `uv run pytest -q`
(`ergane.yaml:34`), which prints counts and names no passing or skipped test —
`evidence/055-us1-attempt1-gate.txt` carries a test name only because that run
*failed*. So quote `passed` and `skipped` from the `-q` summary, and get the
names and the selection from an invocation that prints test ids: `-rs` for the
skip report, and a targeted `uv run pytest tests/test_us4_boundary.py -k
hanging_agent -v` beside it. FR-009.

**Trap 7 — The baseline number in an earlier draft is stale, and every number
here will be too.** That draft said 3567 passed / 47 skipped, which was true of
`evidence/055-us1-attempt1-gate.txt` on 2026-08-18. The ledger's own occurrences
record 4769/49 on 2026-08-24 and 5154/57 on 2026-08-29. Measure the baseline in
your own worktree in your first task and quote that; never carry a number
forward from a document — including from another story's phase, which your
prompt slice does not contain. This trap has already caught this plan twice — see
trap 11.

**Trap 8 — Purge `__pycache__` between mutants**, or run under
`PYTHONDONTWRITEBYTECODE=1`. CPython validates a cached `.pyc` on
`(mtime-in-whole-seconds, size)` only, so two same-size mutants written inside one
wall-clock second make the second run execute the first's bytecode. It fails
toward green and reproduces stably, which is the worst combination available.

**Trap 9 — Do not tune to this host.** Twenty cores today, and a bound calibrated
against that is a bound that breaks on the next machine. Express every wait as a
deadline on an observable condition (FR-004). Equally, do not reach for
`--max-concurrent-nodes`: occurrence 4 fired at fan-out **one**, against an
operator's own `scripts/gate-commit` run, so lowering the dial is not a fix and
raising it is not this spec's business.

**Trap 10 — The census and the guard can both pass by matching nothing, and the
census can also refuse the thing it exists to prove.** A parametrized sweep over
an empty file list passes without asserting anything, and a census whose matcher
never matches reports zero offenders with a green tick. FR-006 and FR-007 both
require the non-vacuity half, and
`tests/test_final_sweep.py:684` — `test_the_source_sweep_actually_read_the_component`
is the shape to copy. FR-006's non-vacuity half is deliberately bound to a
**named module list** rather than to "the files I scanned": an earlier draft let
the census satisfy "the population it examined is non-empty" by counting the two
files it opened, which is true of every possible diff including a no-op. The
opposite error is now written into FR-006 as well: "no module under `tests/`
defines its own `wait_until`" is false the moment US2 lands, because the shared
module is under `tests/` and defines it. The census asserts that the shared
module is the *sole* definer — one apiece there, zero everywhere else — and an
implementer who invents an unstated self-exemption instead has shipped a census a
judge can refuse. The wrong move is a census that counts what it can find and
asserts only that the count is zero.

**Trap 11 — Ban the pattern, not the construct, count it yourself, and know that
your two matchers will disagree.** There are seventy-odd fixed-sleep call sites
across the test tree and most are legitimate — yielding the event loop, not
waiting for a process; the readiness helper itself contains one, at 602a92c
inside `tests/test_us4_boundary.py:153` — `wait_until` and after US2 inside the
shared module that body was promoted into. At 602a92c a text matcher
(`asyncio.sleep(` plus `time.sleep(` over `tests/*.py`) counts **72 across 29
modules** while an `ast` walk over `Call` nodes counts **65 across 27** — the gap
is string literals such as
`tests/test_us4_boundary.py:250` — `test_hanging_agent_is_killed_at_deadline_with_no_survivors`
and `tests/test_us4_boundary.py:391` — `test_boundary_disabled_via_host_backend_reproduces_damage`,
which mention a sleep without calling one. A guard built on `ast` sees the
smaller number and must not be judged against the larger. An earlier draft of
this plan said 69 across 29 and carried that number forward from a document,
which is precisely what trap 7 forbids — so measure it with a matcher you write
down, and say which matcher produced the number. A guard that bans
`asyncio.sleep` outright will be deleted by the next person who needs one. Ban a
fixed sleep standing between launching something and asserting about its state,
and prove both halves against synthetic source (US3-S2, US3-S3). The exemption
precedent — an exemption is a vocabulary decision, driven against synthetic
source, never a way to quiet a failing module — is
`tests/test_final_sweep.py:625` — `test_the_compose_exemption_buys_exactly_one_compound_and_no_more`.

**Trap 12 — The delay-point matrix cannot identify the mechanism, and a
transcript of it can be written without running anything.** Every outcome is
derivable from the stub's own source. A delay before the argv record leaves a
`.stub-agent/<n>/` that `invocations` skips for want of an argv file, so
`last_invocation` (`tests/stub_agent.py:287` — `last_invocation`) raises
`LookupError`. A delay anywhere inside the record writes leaves the first file
`invocations` reads after the argv record missing, so it
(`tests/stub_agent.py:278` — `invocations`) raises `FileNotFoundError` — the
`stdin.txt` case an earlier draft named is the last of those, not the only one. A
delay after the handler installation (`tests/stub_agent.py:414` — `main`)
passes. Exactly one window — between step 5
and step 7 of the start-up table — yields `signals=[]`, and that is the window
this spec's own frontmatter calls "not credible" as the wild mechanism. So one
column always reproduces, "if nothing reproduces, report blocked" can never fire,
and an operator checking that "the point the transcript names is the point the
fix moved" would be confirming a tautology. Two consequences, both of them
requirements rather than observations. **The transcript must carry run-only
material** — per point, the invocation, that run's own `pytest` summary line, the
knob echo the stub wrote into that run's record directory, and, for every point
whose run fails, the failure as `pytest` printed it including the run's own
`tmp_path` (US1-S2, FR-002). The passing point carries the first three and says
so in place of a failure, which is why the artifact set is per-outcome and why
the matrix covers the knobbable range and not the two points before it. A table
of four prose verdicts is a document this plan already contains and proves
nothing;
the wrong move, and the one an implementer blocked by trap 6 will reach for
first, is to compose it from the paragraph you are reading. **And the stub must
record the moment it installs its handler** (US1-S6), which separates the two
mechanisms that produce `signals=[]`. Marker absent and `signals=[]` means the
stub never reached step 7. Marker present and `signals=[]` means it did, and no
catchable TERM was ever delivered — the remaining candidate, TERM reaching bwrap
and the stub through one process group while `--unshare-pid --die-with-parent`
(`factory/workgraph/adapter.py:621` — `_build_argv`) collapses the namespace with
SIGKILL. The evidence points at closing the window in the stub's own ordering,
since the handler's closure needs only `recorder`
(`tests/stub_agent.py:390` — `main`) and `control`
(`tests/stub_agent.py:389` — `main`) and can be installed before the records are
written — but that is a hypothesis, not an instruction. Demonstrate it, do not
assume it. If both marker states come back inconsistent with everything above,
report blocked with the transcript and file a finding; constitution II says a fix
you cannot demonstrate was needed is not this story.

**Trap 13 — US1 mutates the body US2 promotes, so re-diff all five at US2
time.** FR-004 makes US1 add elapsed-time reporting to
`tests/test_us4_boundary.py:146` — `wait_until`. US2 merge-depends on US1, so by
the time US2 dispatches, that copy differs from the other four and *is* the one
FR-005 says to promote. The wrong move is to trust this plan's pasted bodies as
current: re-read all five, diff them, and paste the comparison into the diff
(US2-S4). The second wrong move is to promote variant A's clock under variant B's
five live call sites without saying so — the bound is identical (`PATIENCE_S` is
`20.0`), but which monotonic clock a helper reads is a decision, not a deletion
side effect.

**Trap 14 — "The guarded suites" is not a population, and picking the small
reading makes US3 vacuous.** An earlier draft of this spec used that phrase four
times and never resolved it to a file list, and the two available readings differ
by an order of magnitude. Read narrowly — the two boundary suites — the guard has
nothing at all to find by the time this story dispatches. US1 converts the reap
window `tests/test_us4_boundary.py:241` — `test_hanging_agent_is_killed_at_deadline_with_no_survivors`
and US2 deletes both modules' `wait_until` definitions, and those were the only
sleeps either file held, so after the merge edges this story depends on, the two
boundary suites contain **no fixed sleep whatsoever** and a guard scoped to them
matches nothing — exactly what trap 10 forbids. FR-007 therefore names the
population outright: **every `*.py` file under `tests/`, walked recursively**,
the same population FR-006's census walks and the one
`tests/test_123_no_fixture_pins_the_builder.py:445` — `test_no_fixture_leases_a_virtual_key_against_a_registry_persona`
itself walks. That is 335 files at 602a92c, of which 27-29 contain a fixed sleep
depending on your matcher (trap 11) — the population is the file list, not that
count — and the guard must classify every one of those sleeps correctly, because
US3-S1 requires it green on the converted tree.

**Expect a real exemption list, and do not read it as a disabled guard.** This is
grandfathering rather than misclassification, and it is measured. At 602a92c a
positive-duration fixed sleep standing outside any poll loop and followed by an
assertion about another process's or task's state appears at
`tests/test_engine_identity.py:394`, `tests/test_engine_identity.py:429`,
`tests/test_engine_identity.py:483`,
`tests/test_110_us1_demo_first_boot.py:280`,
`tests/test_110_us1_demo_first_boot.py:524` and
`tests/test_interpreter.py:3067`, besides the reap window US1 converts. Several
are genuinely the banned shape — sleep `0.05`, then assert another process's
identity file is or is not on disk — and Sizing forbids this story to edit any of
those modules. So the honest landing is a guard that ships with roughly that many
named entries against roughly zero live offenders. The remedy for a call site the
matcher refuses is a **named exemption inside the guard module** — file, line,
one-line reason — kept honest by US3-S4's companion test, which asserts every
entry still matches the raw matcher and that the exemptions leave US3-S2's
synthetic source refused. The wrong move, and the one Sizing forbids, is to edit
another test module to quiet the guard: US3 adds one module and edits none.

## Sizing

Every story is test-only. No file under `factory/` is edited by any of them. The
bound US1's transcripts are sized against is `DIFF_REFUSAL_THRESHOLD`
(`factory/verify/diffbounds.py:66`) — the constant above which a story is refused
unjudged — and **not** `DIFF_INPUT_LIMIT` (`factory/verify/diffbounds.py:47`),
which since 092 is only what the judge may be *shown*. 092 (`03451a9`,
2026-08-30, after this spec was drafted) split the two: it moved no number —
`DIFF_REFUSAL_THRESHOLD` is defined *as* `DIFF_INPUT_LIMIT`, both are 64 KiB, and
`ergane.yaml` declares no override — but it moved the name, and the threshold is
now an operator-tunable manifest key. Import the threshold rather than quoting
either number.

- **US1** touches `tests/stub_agent.py` (the `Control` knob, the knob echo, the
  handler-install record, and — if the experiment supports it — the start-up
  ordering), `tests/test_us4_boundary.py` (the synchronisation, the elapsed-wait
  helper and the reap window), and adds three files under **this spec's own**
  `evidence/` directory, written with their full repository-relative paths —
  `specs/058-a-verdict-is-a-fact-about-the-code/evidence/delay-point-matrix.txt`,
  `specs/058-a-verdict-is-a-fact-about-the-code/evidence/pre-fix-under-knob.txt`
  and the mutation transcript beside them. There is no top-level `evidence/` in
  this repository and a diff that creates one is wrong. **The transcripts are the
  size risk, not the code, and "exactly as `pytest` printed it" needs a rule.**
  One `pytest` failure entry for this test is fifty lines
  (`specs/058-a-verdict-is-a-fact-about-the-code/evidence/055-us1-attempt1-gate.txt:70-119`)
  and about forty-five of them are echoed test source, with the `tmp_path` line
  the criterion turns on sitting at the *top* of the entry rather than in that
  source. So keep verbatim what only the run could have produced — the argument
  header carrying that run's own `tmp_path`, `factory_root` and `per_node_home`,
  every `E` line, and the `tests/test_us4_boundary.py:NNN: AssertionError`
  location line — and elide the echoed source with an ellipsis. That is about
  twelve lines per point: hold the matrix to a hundred and twenty lines and the
  other two to sixty, and never paste a full suite tail. This is the heaviest
  story in the spec; if the three transcripts together push the diff toward
  `DIFF_REFUSAL_THRESHOLD`, cut echoed source, never assertions and never the
  run-only material FR-002 names.
- **US2** adds one new module under `tests/` holding `wait_until` and
  `stub_is_up`, deletes five `wait_until` definitions
  (`tests/test_us4_boundary.py`, `tests/test_us3_boundary.py`,
  `tests/test_us1_detector.py`, `tests/test_adapter.py`,
  `tests/test_agent_activities.py`) and three `stub_is_up` definitions
  (`tests/test_adapter.py`, `tests/test_agent_activities.py`,
  `tests/test_us1_detector.py`), edits the import block of each of those modules,
  and adds a census module. It does **not** touch `tests/stub_agent.py` and does
  **not** restructure any launch.
- **US3** adds one new guard module — the matcher, the named exemption list, the
  two synthetic cases, the non-vacuity check and the exemption companion — and
  edits no other file. Its population is every module under `tests/`, but it
  *reads* them rather than writing them: a misclassification is answered with an
  exemption entry in this module (trap 14), never with an edit to the module it
  misjudged.

**US3 shares no production file with either other story** — it adds a module and
edits none. US1 and US2 both edit `tests/test_us4_boundary.py`, which is why the
Work Graph makes US2 merge-depend on US1 rather than run beside it; US1 is also
the only story that edits `tests/stub_agent.py`.

## Verification the operator will run, independent of the gate

1. Re-run the affected test alone twenty times on an idle host and confirm twenty
   passes: `uv run pytest tests/test_us4_boundary.py -k hanging_agent --count 20`
   (or a shell loop). The pre-change failure rate on an idle host is zero, so this
   proves nothing on its own and is the control for step 2.
2. Re-run it under deliberate contention — a second full `uv run pytest -q` on the
   same host — and confirm it still passes. This is the step that discriminates,
   and it is the one an operator can run that a node cannot.
3. Read the committed delay-point transcript and check four things, in this
   order: that each point carries run-only material — a `pytest` summary line
   with its own elapsed seconds, a failure printed by `pytest` quoting that run's
   own `tmp_path`, and the stub's own knob echo from that run's record directory
   — rather than four prose verdicts, which are derivable from `tests/stub_agent.py`
   and from this spec without running anything; that it records all four outcomes
   rather than a pass/fail binary; that it says in its own words that the
   reproducing column demonstrates the signature rather than identifying the
   mechanism; and only then that the landed fix moved the window the transcript
   names. Checking only the last is the tautology trap 12 describes — one column
   always reproduces, so "the fix moved the point the matrix named" is true of
   every fix that touches the start-up sequence at all.
4. Force a `signals=[]` outcome by hand — script the stub with the knob set past
   the handler installation and no TERM handler reachable — and confirm the
   failure message names which of the two mechanisms it found, by reading the
   handler-install marker on disk. This is the check that makes the *next*
   recurrence diagnosable in one read instead of one spec.
5. Confirm the mutation transcript restores the tree: `git status --porcelain`
   after checkout is empty, and the mutant does not appear in the landed diff.
6. Dispatch the next epic at `ergane build start --max-concurrent-nodes 3` and
   watch for a gate failure attributable to a neighbour. This is the payoff the
   spec exists for, it is an observation over time rather than a test, and it is
   deliberately not a story criterion — a node proves what its diff shows and
   nothing more (constitution VIII). Occurrence 4 also means the weaker version of
   this check matters: run `scripts/gate-commit` on a comment-only change while a
   node gate is in flight, which is the configuration that fired at fan-out one.
7. Read US3's exemption list and confirm each entry names a real call site with a
   reason, and that the list is short enough to read. Expect **a handful and not
   zero**: seven call sites match the banned shape by hand at 602a92c — three in
   `tests/test_engine_identity.py`, two in
   `tests/test_110_us1_demo_first_boot.py`, one in `tests/test_interpreter.py`
   and the reap window US1 converts — in modules US3 may not edit, so entries of
   that order are grandfathering rather than a guard turned off. What *would* be
   a guard turned off in place is an exemption list that has grown toward the
   population it walks, or one whose entries no longer match the raw matcher —
   which is what US3-S4's companion test exists to fail.
8. Resolve `ci/flaky-concurrency-test-is-a-random-epic-killer` only after steps 2,
   4 and 6 hold. The row has been resolved once before (2026-08-13, against
   `specs/025-ci-red-recovery`) and regressed; a `fixes:` declaration is a claim
   about the world, not a measurement of it.
