# US5 bounded-read control evidence

Isolated fault-injection controls ran against the merged US3 behavior:

```text
tests/test_131_us5_bounded_reads.py::test_landed_for_spec_does_not_block_the_event_loop PASSED
tests/test_131_us5_bounded_reads.py::test_landed_for_spec_test_detects_an_on_loop_git_read PASSED
tests/test_131_us5_bounded_reads.py::test_landed_for_spec_is_registered_on_the_worker PASSED
tests/test_131_us5_bounded_reads.py::test_registration_test_detects_a_missing_activity PASSED
tests/test_131_us5_bounded_reads.py::test_roadmap_landed_read_is_bounded_to_ready_and_drift_to_landed PASSED
tests/test_131_us5_bounded_reads.py::test_cost_control_detects_an_unbounded_landed_read PASSED
tests/test_131_us5_bounded_reads.py::test_a_built_but_drifted_ready_spec_is_read_and_dispatched PASSED
tests/test_131_us5_bounded_reads.py::test_a_landed_amended_spec_still_renders_amended PASSED
tests/test_131_us5_bounded_reads.py::test_amendment_control_detects_a_narrowed_drift_read PASSED
tests/test_131_us5_bounded_reads.py::test_dispatch_control_detects_a_suppressed_drift_read PASSED
```

`uv run pytest -q tests/test_131_us5_bounded_reads.py` ended with
`10 passed in 2.01s`. Production seams were restored by the test's
`monkeypatch` fixtures and no production code was changed for this control.
