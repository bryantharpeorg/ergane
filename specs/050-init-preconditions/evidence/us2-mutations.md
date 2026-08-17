# US2 evidence: the ordering and sharing tests, and the mutation that proves them

Constitution VIII / D-037: the judge is given this diff and the criteria, never a
terminal. Every block below is tool output pasted verbatim, produced by the
command shown above it.

## 1. The tests, before `factory/cli/init.py` was touched for ordering

A test that has never been observed to fail is not evidence. `T013` compares the
indices of the control-plane verdict line and the schedule line; on the code
that computed the verdict only inside `run_check`, the verdict appeared after
the schedule step.

```
$ PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/test_init_readiness_ordering.py::test_control_plane_verdict_precedes_schedule_line_when_unreadable --tb=short -q
F
=================================== FAILURES ===================================
______ test_control_plane_verdict_precedes_schedule_line_when_unreadable _______
tests/test_init_readiness_ordering.py:94: in test_control_plane_verdict_precedes_schedule_line_when_unreadable
    assert verdict_index < schedule_index, (
E   AssertionError: control-plane verdict (line 7) must precede schedule line (line 6)
E       assert 7 < 6
=========================== short test failure summary ==========================
FAILED tests/test_init_readiness_ordering.py::test_control_plane_verdict_precedes_schedule_line_when_unreadable
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.17s
```

The failure is on *position*, not presence. Both lines already existed; the
schedule line simply came first.

## 2. The battery's instrument, checked before it is trusted

```
$ uv run pytest -q tests/test_init_readiness_ordering.py::test_this_function_does_not_exist
ERROR: not found: .../tests/test_init_readiness_ordering.py::test_this_function_does_not_exist
(no match in any of [<Module test_init_readiness_ordering.py>])

no tests ran in 0.07s
exit=4

$ uv run pytest -q --collect-only tests/test_init_readiness_ordering.py
3 tests collected in 0.07s
```

## 3. The battery

One change at a time, applied, run, reverted, tree asserted clean each time.
Green unmutated; **every row red**.

| # | the mutation | result |
| --- | --- | --- |
| M0 | *control:* a node id that does not exist | `no tests ran`, exit 4 |
| M1 | **baseline** | 3 passed |
| M2 | the verdict line is moved back below the schedule line | 1 failed, 2 passed |
| M3 | the precomputed readability result is no longer passed to `run_check` | 1 failed, 2 passed |

### M1 — baseline

```
$ uv run pytest -q --tb=short tests/test_init_readiness_ordering.py
...                                                                      [100%]
3 passed in 0.21s
```

### M2 — the ordering mutation (US2-S1, SC-002)

The diff applied:

```diff
@@ -541,9 +541,9 @@
     print(_registration_line(registration))
-    # US2-S1: the control-plane verdict is reported before the act that depends
-    # on it, so the transcript reads as a decision rather than a confession.
-    print(_control_plane_verdict_line(control_plane_reason))
     print(schedule_line)
+    # US2-S1: the control-plane verdict is reported before the act that depends
+    # on it, so the transcript reads as a decision rather than a confession.
+    print(_control_plane_verdict_line(control_plane_reason))
```

and the test that went red:

```
$ uv run pytest -q --tb=short tests/test_init_readiness_ordering.py::test_control_plane_verdict_precedes_schedule_line_when_unreadable
F
=================================== FAILURES ===================================
______ test_control_plane_verdict_precedes_schedule_line_when_unreadable _______
tests/test_init_readiness_ordering.py:94: in test_control_plane_verdict_precedes_schedule_line_when_unreadable
    assert verdict_index < schedule_index, (
E   AssertionError: control-plane verdict (line 7) must precede schedule line (line 6)
E       assert 7 < 6
=========================== short test summary info ============================
FAILED tests/test_init_readiness_ordering.py::test_control_plane_verdict_precedes_schedule_line_when_unreadable
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.17s
```

The assertion is on indices, not presence. Restoring the original ordering makes
the verdict appear after the act again, so `T013` fails.

### M3 — the sharing mutation (US2-S3, FR-006)

The diff applied: `run_check(repo_root)` is called with no precomputed
`control_plane` argument, so the readiness report re-runs `_controlplane_probe()`
instead of reusing the readability result the schedule precondition already
computed.

```diff
@@ -558,10 +558,7 @@
     print()
-    # FR-006: reuse the single readability result when it already refuses; when
-    # the control plane is readable, the readiness report still runs the probe
-    # suite so the operator sees per-subsystem detail.
-    run_check(
-        repo_root,
-        control_plane=((), control_plane_reason) if control_plane_reason is not None else None,
-    )
+    run_check(repo_root)
```

and the test that went red:

```
$ uv run pytest -q --tb=short tests/test_init_readiness_ordering.py::test_control_plane_readability_is_evaluated_once_and_reused
F
=================================== FAILURES ===================================
_________ test_control_plane_readability_is_evaluated_once_and_reused __________
tests/test_init_readiness_ordering.py:176: in test_control_plane_readability_is_evaluated_once_and_reused
    assert probe_calls == 0, f"_controlplane_probe ran {probe_calls} times; result should be reused"
E   AssertionError: _controlplane_probe ran 1 times; result should be reused
E       assert 1 == 0
=========================== short test summary info ============================
FAILED tests/test_init_readiness_ordering.py::test_control_plane_readability_is_evaluated_once_and_reused
1 failed, 2 passed in 0.18s
```

The readability result was not reused; the probe suite ran again for the
readiness report, and `T015` catches the second evaluation.
