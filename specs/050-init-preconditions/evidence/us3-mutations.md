# US3 evidence: the tests red before the implementation, and the mutation battery

Constitution VIII / D-037: the judge is given this diff and the criteria, never
a terminal. Every block below is tool output pasted verbatim, produced by the
command shown above it.

## 1. The tests, watched failing before `factory/roadmap/schedule.py` was touched

A test that has never been observed to fail is not evidence. This is the run with
`tests/test_init_schedule_identity.py` written and no production change made yet.

```
$ PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/test_init_schedule_identity.py --tb=short -q
F.F                                                                      [100%]
=================================== FAILURES ===================================
_________ test_init_refuses_when_schedule_belongs_to_a_different_repo __________
tests/test_init_schedule_identity.py:97: in test_init_refuses_when_schedule_belongs_to_a_different_repo
    assert line.startswith(f"schedule: failed {SCHEDULE}"), line
E   AssertionError: schedule: updated ergane-roadmap-widgets — reconciled to the manifest — specs_root: schedule has '/tmp/pytest-of-admin/pytest-0/test_init_refuses_when_schedul0/stranger/specs', manifest declares '/tmp/pytest-of-admin/pytest-0/test_init_refuses_when_schedul0/widgets/specs'; target_repo: schedule has '/tmp/pytest-of-admin/pytest-0/test_init_refuses_when_schedul0/stranger', manifest declares '/tmp/pytest-of-admin/pytest-0/test_init_refuses_when_schedul0/widgets'
E   assert False
=========================== short test summary info ============================
FAILED tests/test_init_schedule_identity.py::test_init_refuses_when_schedule_belongs_to_a_different_repo
FAILED tests/test_init_schedule_identity.py::test_identity_comparison_reads_schedule_not_local_filesystem
2 failed, 1 passed in 0.67s
```

The passing test is `test_init_reconciles_when_schedule_belongs_to_this_repo`
(US3-S2): the same repository must still be allowed to reconcile its own
schedule.

## 2. The mutation battery

One mutation: make the identity comparison read local filesystem state instead of
the repository root recorded on the schedule. A local-only check cannot see a
stranger's repository and would pass vacuously; this row proves T021 catches
that.

### The diff applied

```diff
--- a/factory/roadmap/schedule.py
+++ b/factory/roadmap/schedule.py
@@ -333,7 +333,7 @@ async def _apply(desired: RoadmapSchedule) -> ScheduleStep:
     # 050/US3: the schedule id is derived from the slug, so a different repository
     # with the same slug (or an orphan left by a moved repo) must not be adopted or
     # overwritten.  The comparison is against the root recorded on the schedule,
     # not the local filesystem — a local-only check cannot see a stranger's repo.
-    if live.target_repo != desired.target_repo:
+    if not Path(desired.specs_root).exists():
         return ScheduleStep(
             FAILED,
             desired.schedule_id,
```

### Result

```
$ PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/test_init_schedule_identity.py --tb=short -q
F.F                                                                      [100%]
=================================== FAILURES ===================================
_________ test_init_refuses_when_schedule_belongs_to_a_different_repo __________
tests/test_init_schedule_identity.py:97: in test_init_refuses_when_schedule_belongs_to_a_different_repo
    assert line.startswith(f"schedule: failed {SCHEDULE}"), line
E   AssertionError: schedule: updated ergane-roadmap-widgets — reconciled to the manifest — specs_root: schedule has '/tmp/pytest-of-admin/pytest-9/test_init_refuses_when_schedul0/stranger/specs', manifest declares '/tmp/pytest-of-admin/pytest-0/test_init_refuses_when_schedul0/widgets/specs'; target_repo: schedule has '/tmp/pytest-of-admin/pytest-9/test_init_refuses_when_schedul0/stranger', manifest declares '/tmp/pytest-of-admin/pytest-0/test_init_refuses_when_schedul0/widgets'
E   assert False
_________ test_identity_comparison_reads_schedule_not_local_filesystem _________
tests/test_init_schedule_identity.py:161: in test_identity_comparison_reads_schedule_not_local_filesystem
    assert line.startswith(f"schedule: failed {SCHEDULE}"), line
E   AssertionError: schedule: updated ergane-roadmap-widgets — reconciled to the manifest — specs_root: schedule has '/tmp/pytest-of-admin/pytest-9/test_identity_comparison_reads0/another-checkout/repo/specs', manifest declares '/tmp/pytest-of-admin/pytest-0/test_identity_comparison_reads0/widgets/specs'; target_repo: schedule has '/tmp/pytest-of-admin/pytest-9/test_identity_comparison_reads0/another-checkout/repo', manifest declares '/tmp/pytest-of-admin/pytest-0/test_identity_comparison_reads0/widgets'
E   assert False
=========================== short test summary info ============================
FAILED tests/test_init_schedule_identity.py::test_init_refuses_when_schedule_belongs_to_a_different_repo
FAILED tests/test_init_schedule_identity.py::test_identity_comparison_reads_schedule_not_local_filesystem
2 failed, 1 passed in 0.50s
```

Both US3-S1 (FR-008) and US3-S3 (FR-009) go red, because a local-state check
sees this repository's `specs/` directory and reconciles the stranger's schedule
instead of refusing. The schedule's recorded root is ignored, exactly the
vacuity this story forbids.

### Reverted, clean

```
$ git checkout -- factory/roadmap/schedule.py
$ PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/test_init_schedule_identity.py --tb=short -q
...                                                                      [100%]
3 passed in 0.41s
```

## 3. Related tests after the implementation

```
$ PYTHONDONTWRITEBYTECODE=1 uv run pytest -q tests/test_init_schedule_identity.py tests/test_init_schedule_precondition.py tests/test_ergane_init_schedule.py tests/test_ergane_init_schedule_readiness.py tests/test_ergane_init_check.py tests/test_ergane_init.py tests/test_ergane_registry.py tests/test_ergane_repo_forget.py tests/test_ergane_init_wiring.py tests/test_forge_wiring.py
125 passed in 4.71s
```
