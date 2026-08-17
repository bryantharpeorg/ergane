# US1 evidence: the tests red before the implementation, and the mutation battery

Constitution VIII / D-037: the judge is given this diff and the criteria, never
a terminal. Every block below is tool output pasted verbatim, produced by the
command shown above it.

## 1. The tests, watched failing before `factory/cli/init.py` was touched

A test that has never been observed to fail is not evidence. This is the run at
`3e9cbde` with `tests/test_init_schedule_precondition.py` written and no
production change made yet.

```
$ PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/test_init_schedule_precondition.py --tb=line -q
FFF..F..                                                                 [100%]
=================================== FAILURES ===================================
E   AssertionError: a schedule was published: ['ergane-roadmap-widgets']
    assert {'ergane-road...g_actions=0))} == {}

      Left contains 1 more item:
      {'ergane-roadmap-widgets': Schedule(action=ScheduleActionStartWorkflow(workflow='RoadmapWorkflow',
                                                                             args=[metadata {
        key: "encoding"
        value: "json/plain"
      }...
tests/test_init_schedule_precondition.py:187: AssertionError: a schedule was published: ['ergane-roadmap-widgets']
E   AssertionError: schedule: created ergane-roadmap-widgets — created, starting
    roadmap-specs every 300s over .../widgets/specs (note: LITELLM_PROXY_URL is
    unset, so child epics cannot issue keys)
tests/test_init_schedule_precondition.py:214: AssertionError
E   assert False
     +  where False = 'schedule: created ergane-roadmap-refused — created, ...'.startswith(
            'schedule: failed ergane-roadmap-refused')
tests/test_init_schedule_precondition.py:248: assert False
E   AssertionError: schedule: created ergane-roadmap-widgets — created, starting
    roadmap-specs every 300s over .../widgets/specs (note: LITELLM_PROXY_URL is
    unset, so child epics cannot issue keys)
tests/test_init_schedule_precondition.py:348: AssertionError
=========================== short test summary item ============================
FAILED tests/test_init_schedule_precondition.py::test_no_schedule_is_created_when_the_control_plane_cannot_be_read
FAILED tests/test_init_schedule_precondition.py::test_the_refusal_names_the_control_plane_the_remedy_and_the_namespace
FAILED tests/test_init_schedule_precondition.py::test_the_refusal_costs_the_repository_none_of_its_local_scaffold
FAILED tests/test_init_schedule_precondition.py::test_a_control_plane_config_that_will_not_parse_fails_the_step_without_raising
4 failed, 4 passed in 0.44s
```

Read the four passes as carefully as the four failures. They are the tests that
describe behaviour this story must **preserve** rather than introduce — a
readable control plane still creating the schedule and reporting the same line
(US1-S3), an unreachable one still failing the step instead of raising (US1-S5),
the anti-vacuity guard, and FR-010's no-opt-out check. A story satisfied by
deleting the schedule step would have turned those red instead, which is exactly
why US1-S3 is a scenario.

Eight items collected, not "the tests I named" — a mistyped node id collects
nothing and reports success.

## 2. The battery's instrument, checked before it is trusted

Five ways a battery lied on this host this week, and what each one costs here:

- `PYTHONDONTWRITEBYTECODE=1` **and** an explicit `__pycache__` purge between
  rows. CPython validates a cached `.pyc` on `(mtime-in-whole-seconds, size)`
  only, so two same-size mutants inside one wall-clock second make the second
  run execute the first's bytecode. It fails toward green and reproduces stably.
- The tree is asserted clean — tracked **and** untracked — before and after
  every row. `git checkout -- .` does not remove untracked files, and a battery
  run against one survives the revert and contaminates every later row.
- A specific collected-item count, below, rather than a belief about what the
  selector matches.
- `passed` and `skipped` are quoted; warning counts are not, because a warm
  cache suppresses compile-time warnings.
- At least one row's fake backend would have *accepted* the create. A mutation
  that removes a precondition is invisible to any test whose backend would have
  refused anyway, and `FakeScheduleServer` stores whatever it is handed.

The whole battery runs with `TEMPORAL_ADDRESS=127.0.0.1:1`. The strongest
mutation against a safety guard is disabling it, and on 2026-08-16 a battery run
without the closed port created five schedules on the operator's live namespace.

### M0 — the point-at-nothing control, run first

```
$ uv run pytest -q tests/test_init_schedule_precondition.py::test_this_function_does_not_exist
ERROR: not found: .../tests/test_init_schedule_precondition.py::test_this_function_does_not_exist
(no match in any of [<Module test_init_schedule_precondition.py>])

no tests ran in 0.18s
exit=4

$ uv run pytest -q --collect-only <the nine files>
125 tests collected in 0.38s
```

The first half says the harness would notice a selector that matches nothing.
The second says what the selector the battery actually uses collects: **125
items**, and every row below is that same 125.

### Baseline, unmutated

```
$ uv run pytest -q --tb=no <the nine files>
125 passed in 7.02s
   tree clean after BASELINE
```

## 3. The battery

Nine files: `test_init_schedule_precondition`, `test_ergane_init_schedule`,
`test_ergane_init_schedule_readiness`, `test_ergane_init_check`,
`test_ergane_init`, `test_ergane_registry`, `test_ergane_repo_forget`,
`test_ergane_init_wiring`, `test_forge_wiring`. One change at a time, applied,
run, reverted, tree asserted clean each time. Green unmutated; **every row red**.

| # | the mutation | result |
| --- | --- | --- |
| M0 | *control:* a node id that does not exist | `no tests ran`, exit 4 |
| M1 | **the precondition branch deleted from `_schedule`** | 4 failed, 121 passed |
| M2 | `_control_plane_reason` never reads the config, so it always answers "readable" | 4 failed, 121 passed |
| M3 | the refusal stops naming which Temporal it would have reached | 1 failed, 124 passed |
| M4 | the refusal drops its own `ergane install` clause | 2 failed, 123 passed |
| M5 | the refusal raises instead of returning a failed step | 22 failed, 103 passed |
| M6 | the refusal asks which Temporal without guarding the answer | 1 failed, 124 passed |
| M7 | the step refuses unconditionally — "satisfy US1 by not scheduling" | 6 failed, 119 passed |
| M8 | the offline fixture stops leaving a readable config behind | 3 failed, 122 passed |

### M1 — the mandatory one (US1-S4, SC-002)

The diff applied:

```
@@ -634,13 +634,2 @@ def _schedule(repo_root: Path, slug: str, *, control_plane_reason: str | None) -
     """
-    if control_plane_reason is not None:
-        return roadmap_schedule.format_step(
-            roadmap_schedule.ScheduleStep(
-                roadmap_schedule.FAILED,
-                roadmap_schedule.schedule_id_for(slug),
-                f"refused: the control plane could not be read, so no schedule "
-                f"was created — {control_plane_reason} — and `ergane install` is "
-                f"what creates it; a schedule for this repository would "
-                f"otherwise have gone to {_schedule_target()}",
-            )
-        )
     try:
```

and the tests that went red:

```
4 failed, 121 passed
FAILED test_init_schedule_precondition.py::test_no_schedule_is_created_when_the_control_plane_cannot_be_read
FAILED test_init_schedule_precondition.py::test_the_refusal_names_the_control_plane_the_remedy_and_the_namespace
FAILED test_init_schedule_precondition.py::test_the_refusal_costs_the_repository_none_of_its_local_scaffold
FAILED test_init_schedule_precondition.py::test_a_control_plane_config_that_will_not_parse_fails_the_step_without_raising
```

The first of those is the one that matters, and its failure message is the
incident in miniature:

```
AssertionError: a schedule was published: ['ergane-roadmap-widgets']
```

Not "apply_schedule was called" — a schedule exists on the backend. M2 is the
same claim reached by a different route: leave the branch in place and make the
fact it reads always say "readable". It kills the same four, which is what
"deleting the precondition" means in the general case.

### M7 — the mutation that proves the story was not satisfied by not scheduling

```
6 failed, 119 passed
FAILED test_init_schedule_precondition.py::test_a_readable_control_plane_creates_the_schedule_and_reports_it_unchanged
FAILED test_init_schedule_precondition.py::test_the_refusal_costs_the_repository_none_of_its_local_scaffold
FAILED test_init_schedule_precondition.py::test_a_configured_but_unreachable_control_plane_fails_the_step_without_raising
FAILED test_ergane_init_schedule.py::test_init_creates_a_schedule_carrying_the_slug_and_this_repos_arguments
FAILED test_ergane_init_schedule.py::test_declared_dials_reach_the_schedule_and_a_re_run_reconciles_them
FAILED test_ergane_init_schedule.py::test_an_unchanged_re_run_reports_already_satisfied_and_changes_nothing
```

A diff that removed scheduling passes US1-S1 and US1-S2 and fails US1-S3. This
is the row that says so, and 034's own three tests are in it.

### M5 — refusing and crashing are different outcomes

```
22 failed, 103 passed
FAILED test_init_schedule_precondition.py::test_no_schedule_is_created_when_the_control_plane_cannot_be_read
FAILED test_init_schedule_precondition.py::test_the_refusal_names_the_control_plane_the_remedy_and_the_namespace
FAILED test_init_schedule_precondition.py::test_the_refusal_costs_the_repository_none_of_its_local_scaffold
FAILED test_init_schedule_precondition.py::test_a_control_plane_config_that_will_not_parse_fails_the_step_without_raising
FAILED test_ergane_init.py::test_the_interview_offers_no_multi_line_default
FAILED test_ergane_registry.py::test_completed_init_maps_the_slug_to_the_repo_absolute_path
FAILED test_ergane_registry.py::test_the_registry_entry_exists_nowhere_inside_the_repo
…and 14 more in test_ergane_registry.py, elided for length; the four above
and these fourteen are every failure in the row.
```

Eighteen of those twenty-two are in `test_ergane_registry.py`, which drives a
full `ergane init` and binds no control-plane config at all. That is FR-002 and
FR-017 measured rather than asserted: turning the refusal into an exception does
not merely change a message, it takes an entire module's worth of repositories'
scaffolds and registry rows with it.

### M6 — the sharp edge of "never raises"

Removing the guard around the resolver that answers *which Temporal would this
have reached* kills exactly one test, and it is the one written for it:

```
1 failed, 124 passed
FAILED test_init_schedule_precondition.py::test_a_control_plane_config_that_will_not_parse_fails_the_step_without_raising
```

A *missing* config degrades to the built-in defaults and resolves fine; a
*broken* one refuses outright. The refusal message is the last place in this
code path that may raise, and only the second case can prove the guard is real.

### M8 — the fixture change is load-bearing, not cosmetic

```
3 failed, 122 passed
FAILED test_ergane_init_schedule.py::test_init_creates_a_schedule_carrying_the_slug_and_this_repos_arguments
FAILED test_ergane_init_schedule.py::test_declared_dials_reach_the_schedule_and_a_re_run_reconciles_them
FAILED test_ergane_init_schedule.py::test_an_unchanged_re_run_reports_already_satisfied_and_changes_nothing
```

`bind_offline_seams` promised a healthy control plane while the suite's session
fixture pointed `ERGANE_CONFIG_PATH` at a file nothing creates. Left that way,
every init driven through it would take the refusal path — 034's three scenarios
would be measuring this story instead of their own, and they say so.

## 4. One mutation that first SURVIVED, and what it changed

**M4 was green in `test_the_refusal_names_the_control_plane_the_remedy_and_the_namespace`
on its first run.** The test asserted `"`ergane install`" in line` — and that
phrase was in the line whether or not this code put it there, because the config
loader's own `[config_missing]` message already ends with *run `ergane install`
to create the control-plane config*. The assertion was being satisfied by
borrowed text: it tested the borrowing, not the refusal. It only failed in the
parse-failure test, where the loader's message carries no remedy at all.

The assertion now names the refusal's own clause — `"`ergane install` is what
creates it"` — and M4 kills both tests:

```
$ MUTANT=M4 …; uv run pytest -q --tb=no <the nine files>
2 failed, 123 passed in 6.39s
FAILED test_init_schedule_precondition.py::test_the_refusal_names_the_control_plane_the_remedy_and_the_namespace
FAILED test_init_schedule_precondition.py::test_a_control_plane_config_that_will_not_parse_fails_the_step_without_raising
```

This is its own species of the tests-that-cannot-fail class, and worth naming
because it is not a weak assertion: it is a strong assertion about a string that
something *else* in the message guarantees. A test whose subject is a message
has to assert on the part the code under test is responsible for.

## 5. The full suite, and what it left on the live control plane

Run in the worktree with a purged `__pycache__` and a deleted `.pytest_cache` —
a cold cache, stated because a warm one suppresses compile-time warnings, which
is why the count below quotes `passed` and `skipped` and not warnings. Run in
the *normal* environment rather than the battery's closed-port one, so the skip
count is comparable to the 44 the suite has today: closing the port would skip
the live tier by guard and a new skip is a finding, not a detail.

```
$ uv run pytest -q
3151 passed, 44 skipped, 6 warnings in 306.89s (0:05:06)
pytest rc=0
```

44 skips, the expected baseline, and no new one.

Then the check the plan asks for, which a green suite is not a substitute for:

```
$ temporal schedule list --namespace factory      # after that run
    ScheduleId                Action              Paused  NextRunTime  LastRunTime
  ergane-roadmap  {"Workflow":"RoadmapWorkflow"}  true    1 day ago    1 day ago
rc=0
```

One schedule, the operator's, still paused. The suite created nothing — which is
the same sentence 034's evidence ends with, and the reason it is repeated is
that the run in between those two sentences is the one that created five.

## 6. The diff, measured the way the judge measures it

Against the merge-base, not the moving tip, and through `size_refusal` rather
than `git diff | wc -c` — the latter omits the generated file listing and
preamble the judge's prompt actually carries.

```
$ git add -A && git diff --cached $(git merge-base HEAD origin/ergane-buildout)
merge-base: 3e9cbde1d147d6667c2ff28f3e644bf56bb3a7a8

measured as the judge measures : 55193 bytes
DIFF_INPUT_LIMIT               : 61440 bytes
size_refusal(diff_text)        : None

   18870  tests/test_init_schedule_precondition.py
   16440  specs/050-init-preconditions/evidence/us1-mutations.md
   10540  specs/050-init-preconditions/evidence/us1-reproduction.md
    5372  factory/cli/init.py
    3687  tests/test_ergane_init_check.py
```

`DIFF_INPUT_LIMIT` is imported rather than quoted. No refusal, with 6247 bytes
of headroom. The production change is 5.4 KB of a 61 KB budget; the two evidence
files SC-001 and SC-002 require are 27 KB of it, which is the cost of a judge
that sees no terminal.

The measurement is self-referential — this file is inside the diff it reports,
so writing the figure down moves it. The figure above is the one measured after
the last edit to this file, and it is stable because the replacement is the same
number of digits wide.
