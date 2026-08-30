# Attempt report — 122 / US3: a test that reads a findings store builds its own

T016. The plan's § *Verification the operator will run* run by hand, before and
after, on 2026-08-30. Either run alone proves nothing: a suite that was already
green proves no fix, and one green only afterwards proves no regression was
avoided.

## What was actually wrong

`ERGANE_ROOT` pins the *first* of two findings-store candidates. When the
runtime root it names holds no ledger, `factory/doctor/cli.py:_resolve_store_path`
falls back to the legacy runtime root **relative to the working directory** —
the operator's real ledger on the machine that does the building. The suite-wide
redirect in `tests/conftest.py:524` pins only the first candidate, so three of
the eleven tests in the two 089 fixes-layer modules decided their verdict from
whatever findings the host happened to hold:

```
[fixes] spec declares unknown finding key(s): any/key (store: .factory/doctor.db)
```

Green on a fresh clone, red on the operator's host. Passing only in the boundary
is exactly the defect (US3-S2).

## The sequence that was run

Verbatim from the plan, with one addition the plan's own measurement requires:
the operator's host **has** a populated ledger and this build host does not, so
a store was seeded at the legacy path first. Without it the before-run reports
25 failed rather than 28 — the three ledger failures are invisible on a machine
with no ledger, which is the defect restated.

```bash
eval "$(scripts/ergane-env.sh)"
cp personas.yaml /tmp/personas.bak
# swap the implementer to agent: subscription / model: claude-opus-5 / fallback: null
# (the plan's python heredoc, applied verbatim — asserted to match exactly once)
# seed a populated ledger at the legacy candidate, i.e. the operator's condition
uv run pytest -q tests/test_us2_shipped_registry.py tests/test_usage_activities.py \
  tests/test_089_validate_checks_fixes.py tests/test_089_promote_declares_fixes.py
cp /tmp/personas.bak personas.yaml     # restored; `git status` clean afterwards
```

## Before — subscription implementer, populated ledger, pre-spec tree

The two 089 modules restored to `4b2d6f0` (the branch base, before this story).

```
FAILED tests/test_us2_shipped_registry.py::test_repo_root_registry_still_resolves_real_wiring_in_checkout
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
FAILED tests/test_089_validate_checks_fixes.py::test_validate_reports_fixes_not_checked_when_store_is_absent
FAILED tests/test_089_validate_checks_fixes.py::test_validate_does_not_create_missing_store
FAILED tests/test_089_promote_declares_fixes.py::test_validate_verdict_unchanged
28 failed, 35 passed in 19.81s
```

**28 failed** — the figure the plan measured, reproduced. Three of them are this
story's; the other 25 are the two registry pins US1 and US2 remove, and are not
in this worktree.

## After — the same swap, the same ledger, this story's tree

```
FAILED tests/test_us2_shipped_registry.py::test_repo_root_registry_still_resolves_real_wiring_in_checkout
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
25 failed, 38 passed in 19.76s
```

**28 → 25.** Every failure this story owns is gone; the 25 that remain are
`test_us2_shipped_registry.py` and `test_usage_activities.py`, which belong to
US1 and US2 and are untouched here. The demonstration is green for this story's
scope and will be green outright once its two siblings land.

## The pair the story is actually graded on

The four-file sequence above carries two stories' worth of noise. The same
before/after over only the two files US3 owns, on the same populated ledger:

```
# before (tree at 4b2d6f0)
FAILED tests/test_089_validate_checks_fixes.py::test_validate_reports_fixes_not_checked_when_store_is_absent
FAILED tests/test_089_validate_checks_fixes.py::test_validate_does_not_create_missing_store
FAILED tests/test_089_promote_declares_fixes.py::test_validate_verdict_unchanged
3 failed, 8 passed in 18.68s

# after
11 passed in 18.40s
```

And the other direction — the one that was already green and must stay green,
because a fix that only satisfies the operator's host has made the tests depend
on it harder (US3-S2, trap 6):

```
# after, no findings store anywhere on the host
11 passed in 18.41s
```

The guard that holds both directions from now on:

```
$ uv run pytest -q tests/test_122_findings_store_isolation.py
5 passed in 2.13s
```

It runs those two files as their own pytest session under three shapes of host —
a populated ledger, no ledger at all, and a ledger that is not a database — and
requires the same green result from each. The poisoned shape is the behavioural
form of FR-006: a store the guarded tests never resolve can be corrupt for free,
so if any of them resolves the operator's, that run goes red.

## The whole suite, unswapped

```
$ uv run pytest -q
5216 passed, 58 skipped, 8 warnings in 369.44s (0:06:09)
```

## Restoration

`personas.yaml` was restored from `/tmp/personas.bak` and `git status` reports it
unmodified. The seeded ledger was written to the worktree's own gitignored
runtime root and removed; nothing outside this worktree was touched.
