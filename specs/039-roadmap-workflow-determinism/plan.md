# Plan: A scheduler that cannot report its own success

All line references below were read against the tree at commit `54e1153` on
2026-08-13, **after 030 landed** — this spec was deliberately drafted at that
point rather than earlier, because 030 rewrote `tests/conftest.py` and the
roadmap test harnesses that US1's regression test sits beside. They are cited so
you can find the code, not so you can trust the numbers; grep the construct
named beside each anchor. See trap 5.

## Reuse inventory

| What | Where | Used by |
| --- | --- | --- |
| The defect itself | `factory/roadmap/workflow.py:136-140` — grep `def _verification_db_path` | US1 — the function to delete or relocate |
| Call site 1 (failure path) | `workflow.py:922`, inside `_report_roadmap_failure` at `:903` | US1 |
| Call site 2 (success path) | `workflow.py:956`, inside `_report_run_success` at `:945` | US1 — **the one that actually fired** |
| The workflow's only argument | `RoadmapInput` at `workflow.py:190` — a frozen dataclass crossing a Temporal boundary | US1 — FR-002's first route |
| Where the operator starts it | `factory/cli/roadmap.py:180` (`RoadmapInput(`) | US1 — if the path is carried on input, this is where it is filled |
| Where the roadmap starts a child | `workflow.py:871` (`RoadmapInput(`) | US1 — a second construction site; both must stay valid |
| The workflow decorator, and the run entry | `workflow.py:443` (`@workflow.defn`), `:644` (`@workflow.run`) | US2 — what the guard scans for |
| The clean sibling | `factory/workgraph/workflow.py` — no `environ`/`getenv` anywhere | US2 — the guard must pass on it today |
| The activities that already receive `db_path` | `record_roadmap_failure` and `reset_roadmap_failures` in `factory/activities/notify_activities.py:536` — grep `RecordRoadmapFailureInput` | US1 — FR-002's second route |
| The store path resolver the activities use | `notify_activities.py:643-651`, the read itself at `:649` — grep `def _store_path` | US1 — the correct, in-activity precedent: the *same* `os.environ.get(VERIFICATION_DB_PATH_ENV) or DEFAULT_VERIFICATION_DB_PATH`, legitimate because it runs in an activity. US2's guard must not flag it. |
| Roadmap test harnesses | `tests/test_roadmap_scheduler.py` (`run_roadmap`), `tests/test_ergane_roadmap.py` (`_worker`), `tests/test_roadmap_failure_notifications.py` | US1 — where the regression test belongs |
| The session store-isolation fixture 030 just landed | `tests/conftest.py` — grep `_isolated_test_store` | US1 — your test inherits it; do not redirect the store yourself |
| The store guard 030 just landed | `factory/verify/store.py` — grep `EVIDENCE_STORE_ALLOW_REAL_ENV` | context — a test that opens a real store path now raises |

## Traps

### Trap 1 — the forbidden fix is silencing the sandbox

The error text itself suggests the wrong repair: *"mark the import as pass
through."* Do not. `passthrough_modules`, `sandboxed=False`, or a
`workflow.unsafe.imports_passed_through()` block around this read would all make
the symptom disappear and leave a workflow that reads process state during
replay — which is exactly the nondeterminism the sandbox exists to prevent, and
would turn a loud wedge into a quiet wrong answer. The sandbox is the only
component that caught this defect. FR-005 forbids weakening it, and US1-S4 is
the scenario that checks you didn't.

### Trap 2 — a fake Temporal environment will not catch this

The bug lives in the sandbox, so a test that stubs the workflow, calls
`_report_run_success` directly, or runs with sandboxing off passes happily
against the broken code. It has to be a real `WorkflowEnvironment` with the
sandbox enabled, driving the workflow to a clean completion. If your new test
passes when you revert the fix, the test is wrong — that is precisely what
US1-S3's red-then-green transcript is for.

### Trap 3 — the success path needs a *prior failure* to be reachable

`_report_run_success` (`:945`) resets the consecutive-failure count and only
sends a recovery notice `if prior_count:`. But the crash is in the
`reset_roadmap_failures` call that computes `prior_count`, which runs
unconditionally — so a bare happy-path run reaches it. Read the function before
you script your fixture: the scenario you need is a pass that *completes*, and
whether a prior failure exists changes only what happens after the crash point.
Scripting a prior failure anyway is the stronger test, because it exercises both
the reset and the notice.

### Trap 4 — do not "fix" the roadmap's observable behaviour while you are in there

FR-009 is a fence. The `roadmap_failures` count, its reset semantics and the
notice text are 031's contract, and `tests/test_roadmap_failure_notifications.py`
asserts them. This story moves *where a path is computed*, nothing else. A diff
that also improves the notice text, changes the throttle, or renames a field is
a diff whose regression risk nobody scoped.

### Trap 5 — these anchors were written the same day 030 landed, and the tree is moving

`workflow.py`'s anchors drifted ~35 lines in two days during the 025–031 run,
and `notify_activities.py`'s `_store_path` moved ~58. Grep for the construct —
`def _verification_db_path`, `def _report_run_success`, `class RoadmapInput`,
`@workflow.defn`, `def _store_path` — and if a citation here disagrees with the
tree, the tree wins and you say so in your commit message.

### Trap 6 — the guard must find the class by construction, not by name

The tempting US2 implementation is a test that imports the two known modules and
checks them. That guards the instance, not the class: the next workflow module
is added by someone who never reads this spec, and the guard stays green while
the hole reopens. Discover the modules by scanning `factory/` for the workflow
decorator, then analyse each one. Prefer reading the module source with `ast`
over importing it — an import executes module-level code and couples the guard
to import side effects, and `ast` gives you the function name FR-007 wants you
to report for free.

**A grep-based guard fails on the current tree, and here is the exhibit.**
`grep -n 'environ\|getenv' factory/workgraph/workflow.py` returns two hits
today (`:731`, `:734`) and that module is clean — both are prose comments
containing the word *environment*, about the Temporal test environment
advancing its clock. A text-matching guard reports two false positives on the
one module that is already correct, which is how a guard gets deleted in its
first week. `ast` sees an `Attribute` node or it sees nothing.

### Trap 7 — the guard must not be right for the wrong reason

`_verification_db_path` was *correct* for two months in activity context, and
`notify_activities._store_path` does the same read legitimately today. A guard
that bans `os.environ` anywhere in the file, or anywhere in `factory/`, would
fail on correct code and get weakened the first time it fired — which is how a
guard becomes decorative. Scope it: functions reachable from workflow scope, in
modules that define a workflow. US2-S4 is the scenario that checks you drew the
line and not a bigger one.

### Trap 8 — the proof is part of the deliverable

Both stories turn on runtime behaviour the judge cannot observe: it sees the
diff and the criteria, never a terminal (constitution VIII). So the red-then-
green transcripts are committed artifacts — pasted verbatim into a comment block
in the test file, not described, not summarized, not left in the commit message.
This has now cost the factory twice: 027/US2 died four times on criteria that
could not be judged, and 028/US3's agent fixed its story correctly and skipped
the paste, so an operator had to re-run the command by hand to produce the
evidence.

## Approach

### US1 — take the read out of workflow scope

1. Decide the route. **Reading it inside the activity is the smaller diff and
   the better shape**: `record_roadmap_failure` and `reset_roadmap_failures`
   already receive `db_path`, and `notify_activities._store_path` already does
   this resolution correctly in activity context. Making `db_path` optional on
   those two inputs — falling back to `_store_path()` inside the activity when
   the caller does not supply one — removes both workflow-scope calls without
   touching `RoadmapInput` or either of its two construction sites. Carrying it
   on `RoadmapInput` (FR-002's other route) also satisfies the FRs, but it means
   filling the field at `cli/roadmap.py:180` *and* `workflow.py:871`, and a
   frozen dataclass crossing a Temporal boundary needs a defaulted field so old
   histories still deserialize. Pick one; say which and why in the commit.
2. Delete `_verification_db_path` if nothing else calls it. Leaving a dead
   workflow-scope environment reader in the module is an invitation.
3. Write the regression test beside the existing roadmap tests, using a real
   `WorkflowEnvironment` with the sandbox on. Script a prior failure, run a pass
   to clean completion, assert it reaches a completed state. The store is
   already redirected for you by 030's `_isolated_test_store` fixture in
   `tests/conftest.py` — do not redirect it again, and do not point any test at
   a real store path, which 030's guard now refuses outright.
4. Produce the transcript FR-004 requires: run the new test green, revert the
   fix, run it again and capture the `RestrictedWorkflowAccessError`, restore
   the fix, run it green. Paste all three verbatim into a comment block in the
   test file.

### US2 — a guard that finds the class

1. Discover modules: walk `factory/` for `.py` files whose source contains the
   workflow definition decorator. Assert the discovery itself is non-empty — a
   scanner that silently finds nothing is a test that always passes.
2. For each, parse with `ast` and collect the functions reachable at workflow
   scope: methods of the class carrying the workflow decorator, plus
   module-level functions those methods call. Flag any that reference
   `os.environ`, `environ.get`, or `os.getenv`.
3. Fail with the module path and the function name (FR-007).
4. Prove it both ways and paste both: green on the fixed tree, and red — naming
   the function — with a read reintroduced.

## Complexity Tracking

| Thing | Why it is not simpler |
| --- | --- |
| An `ast` scan rather than a grep | FR-007 wants the offending *function* named, and a grep cannot tell a workflow method from an activity in the same file. The scan surface is two files, so the cost is small. |
| A guard at all, for a one-instance defect | The instance is one function; the class is "a workflow module reads process state", whose failure mode is a scheduler that dies without telling anyone. It went unnoticed for a day with an operator actively working the floor. |
| Committed transcripts rather than a green suite | The judge cannot run tests (constitution VIII). A green gate proves the test passes now; it cannot prove the test would have caught the bug. |

## Verification

`uv run pytest -q` green in the worktree, before and after each story. As of 030
that command is safe from any directory and needs no env scrubbing.

Green is necessary and not sufficient here. The whole claim of US1 is that a
specific test *fails on the old code*, and of US2 that the guard *fires on a
reintroduction* — neither is visible in a passing run. The transcripts are the
evidence; see trap 8.
