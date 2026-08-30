# US2 attempt report — the usage fixtures stopped naming the operator's builder

The pair below is the evidence. A run that was already green proves no fix, and
one that is green only afterwards proves no regression was avoided, so both
directions are recorded, with tool output pasted rather than described.

The registry used for the "subscription implementer" runs is the shipped
`personas.yaml` with one entry re-routed, exactly as the plan's operator
verification does it:

```
implementer: {'agent': 'subscription', 'model': 'claude-opus-5', 'fallback': None,
              'skills': ['implement', 'tdd'], 'write_scope': 'worktree',
              'needs_worktree': True, 'timeout': 14400, 'context_window': 1048576}
```

## Before — `PERSONA = "implementer"`

The usage module against that registry (`ERGANE_PERSONAS_PATH` pointed at it):

```
$ ERGANE_PERSONAS_PATH=/tmp/personas-sub.yaml uv run pytest -q tests/test_usage_activities.py
FAILED tests/test_usage_activities.py::test_issue_attempt_key_mints_a_key_bound_to_the_attempt
FAILED tests/test_usage_activities.py::test_issue_attempt_key_sends_the_dimensions_and_never_a_cap
FAILED tests/test_usage_activities.py::test_issue_attempt_key_applies_the_backstop_ttl
FAILED tests/test_usage_activities.py::test_a_persistent_proxy_failure_raises_key_issuance_failed
FAILED tests/test_usage_activities.py::test_a_rejected_credential_fails_issuance_permanently
FAILED tests/test_usage_activities.py::test_missing_worker_credentials_fail_issuance_before_any_call
FAILED tests/test_usage_activities.py::test_a_failed_issuance_leaves_no_ledger_row
FAILED tests/test_usage_activities.py::test_issue_attempt_key_reclaims_an_orphaned_alias_of_the_same_epic
FAILED tests/test_usage_activities.py::test_issue_attempt_key_recovery_is_idempotent
FAILED tests/test_usage_activities.py::test_issue_attempt_key_refuses_to_disturb_a_live_epic_alias
FAILED tests/test_usage_activities.py::test_recovered_orphan_keeps_historical_spend_attributable
FAILED tests/test_usage_activities.py::test_teardown_reads_then_writes_then_deletes_last
FAILED tests/test_usage_activities.py::test_teardown_records_the_attempts_usage_from_proxy_data
FAILED tests/test_usage_activities.py::test_the_confirmed_spend_is_the_keys_own_total
FAILED tests/test_usage_activities.py::test_an_attempt_that_never_called_the_proxy_records_unmeasured
FAILED tests/test_usage_activities.py::test_a_key_already_gone_falls_back_to_the_last_snapshot
FAILED tests/test_usage_activities.py::test_a_failed_spend_log_read_falls_back_too
FAILED tests/test_usage_activities.py::test_running_teardown_twice_leaves_exactly_one_row
FAILED tests/test_usage_activities.py::test_a_failed_revocation_still_records_the_attempt
FAILED tests/test_usage_activities.py::test_a_failed_ledger_write_leaves_the_key_alive
FAILED tests/test_usage_activities.py::test_a_refused_row_leaves_the_usage_recoverable[epic_id]
FAILED tests/test_usage_activities.py::test_a_refused_row_leaves_the_usage_recoverable[node_id]
FAILED tests/test_usage_activities.py::test_a_refused_row_leaves_the_usage_recoverable[persona]
FAILED tests/test_usage_activities.py::test_a_refused_row_leaves_the_usage_recoverable[spec_ref]
24 failed, 23 passed in 0.42s
```

Twenty-four, not the thirteen the plan estimated: the count in the plan is of
test *functions*, and four of them are parametrized. The gate command is
`uv run pytest -q` (`factory.yaml`), so any one of these reddens every node.

This story's own tests, still under the pinned constant — the subscription run
and the fixture-ownership check fail, the gateway control and the no-key
coverage already pass:

```
$ uv run pytest -q tests/test_122_usage_fixture_persona.py
E   AssertionError: PERSONA = 'implementer' is a persona the operator's registry
    defines, so re-routing it decides whether these tests pass
FAILED tests/test_122_usage_fixture_persona.py::test_the_usage_tests_pass_with_a_subscription_implementer
FAILED tests/test_122_usage_fixture_persona.py::test_the_usage_fixtures_lease_against_a_persona_the_tests_own
2 failed, 4 passed in 1.69s
```

## After — `PERSONA = "gateway-CHANGEME"`

One constant. The thirteen functions were not touched individually.

```
$ uv run pytest -q tests/test_122_usage_fixture_persona.py
6 passed in 1.46s

$ ERGANE_PERSONAS_PATH=/tmp/personas-sub.yaml uv run pytest -q tests/test_usage_activities.py
47 passed in 0.29s
```

47, up from the 45 of the untouched module: the two added are the deliberate
no-key coverage (FR-005), which the pin used to provide only by accident and
only on an operator's host.

The whole gate, on the registry as it actually ships:

```
$ uv run pytest -q
5219 passed, 58 skipped, 8 warnings in 370.80s (0:06:10)
```

## What is not proven here

US1 and US3. `tests/test_us2_shipped_registry.py:344` still asserts a slash in
the implementer's model, so the plan's four-file operator verification is not
green until all three stories land. This report covers the two files US2 owns.
