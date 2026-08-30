# US2 attempt report — the operator's demonstration

The gate proves the suite is green with the registry as it stands. It cannot prove this
spec's purpose, which needs a registry change the spec does not make. This is that run,
whole — the plan's § *Verification the operator will run*, executed verbatim, on the
**whole suite** rather than a predicted subset, because scoping 122 from four predicted
files is precisely how this spec came to exist.

## The sequence

```bash
eval "$(scripts/ergane-env.sh)"
cp personas.yaml /tmp/personas.bak
python3 - <<'PY'
import pathlib
p = pathlib.Path("personas.yaml"); t = p.read_text()
p.write_text(t.replace("  agent: claude-code\n  model: ollama-cloud/glm-5.3\n  fallback: local/qwen3.6-27b",
                       "  agent: subscription\n  model: claude-opus-5\n  fallback: null", 1))
PY
uv run pytest -q                       # expect: no failure outside the known live tiers
cp /tmp/personas.bak personas.yaml
```

The swap landed on `personas.yaml:188-190`, and `git status` after the restore is empty:
the registry this attempt commits is byte-identical to the one it started from.

## The whole suite, with the implementer subscription-routed

```
================================== live tiers ==================================
live_capacity   did not run — runs when a server answers at TEMPORAL_ADDRESS/TEMPORAL_NAMESPACE
live_epic       did not run — runs when Tier 1 env is set
live_merge      did not run — runs when FACTORY_SAMPLE_REPO is set and gh is authenticated
live_onramp     did not run — runs when every prerequisite in docs/onramp-exercise.md is present
live_proxy      did not run — runs when LITELLM_PROXY_URL and LITELLM_MASTER_KEY are set
live_telegram   did not run — runs when TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set
=========================== short test summary info ============================
FAILED tests/test_controlplane_direct_mode.py::test_issue_attempt_key_returns_declared_credential_and_writes_row
FAILED tests/test_controlplane_direct_mode.py::test_issue_attempt_key_for_gateway_still_mints
FAILED tests/test_final_sweep.py::test_no_failure_path_renders_the_master_key[a_worker_host_with_no_proxy_url]
FAILED tests/test_final_sweep.py::test_no_failure_path_renders_the_master_key[a_worker_host_with_no_master_key]
FAILED tests/test_final_sweep.py::test_no_failure_path_renders_the_master_key[a_rejected_credential_on_issue]
FAILED tests/test_final_sweep.py::test_no_failure_path_renders_the_master_key[a_proxy_that_will_not_mint_a_key]
FAILED tests/test_final_sweep.py::test_the_master_key_reaches_no_byte_the_component_persists
FAILED tests/test_final_sweep.py::test_a_runaway_attempt_is_treated_exactly_like_a_cheap_one
FAILED tests/test_final_sweep.py::test_an_enormous_spend_still_only_gets_an_uncapped_key
FAILED tests/test_poll_usage.py::test_poll_returns_the_keys_current_spend - f...
FAILED tests/test_poll_usage.py::test_the_snapshot_says_when_it_was_taken - f...
FAILED tests/test_poll_usage.py::test_successive_polls_track_the_attempt_as_it_spends
FAILED tests/test_poll_usage.py::test_a_poll_is_one_key_info_read_and_nothing_more
FAILED tests/test_poll_usage.py::test_any_usage_level_produces_a_snapshot_and_nothing_else[0.0]
FAILED tests/test_poll_usage.py::test_any_usage_level_produces_a_snapshot_and_nothing_else[1e-06]
FAILED tests/test_poll_usage.py::test_any_usage_level_produces_a_snapshot_and_nothing_else[42.5]
FAILED tests/test_poll_usage.py::test_any_usage_level_produces_a_snapshot_and_nothing_else[10000.0]
FAILED tests/test_poll_usage.py::test_any_usage_level_produces_a_snapshot_and_nothing_else[1000000000.0]
FAILED tests/test_poll_usage.py::test_any_usage_level_produces_a_snapshot_and_nothing_else[9900000000000000.0]
FAILED tests/test_poll_usage.py::test_polling_leaves_the_running_attempt_untouched
FAILED tests/test_poll_usage.py::test_a_missed_poll_costs_only_that_beat - fa...
FAILED tests/test_poll_usage.py::test_polling_a_key_that_is_already_gone_raises
FAILED tests/test_poll_usage.py::test_the_snapshot_never_carries_the_master_key
FAILED tests/test_poll_usage.py::test_the_polled_snapshot_is_what_teardown_records_when_the_proxy_is_lost
24 failed, 5210 passed, 58 skipped, 8 warnings in 375.73s (0:06:15)
```

## What this story owns, and what it proves

`tests/test_spec_declares_its_fixes.py` does not appear above, in either direction. It was
never in the swap's blast radius — its pin was the *host*, not the registry — so the
demonstration that matters for US2 is the host matrix, and it is committed as
`tests/test_123_fixes_declaration_store_isolation.py` rather than pasted: the guarded file
is run as its own pytest session under a populated operator ledger, no ledger at all, and
a ledger that is not a SQLite database, and the same green result is required from each.

Before this story, two of those three shapes were red, and this is the whole of the
difference — the store the test reads is now one it builds:

```
FAILED tests/test_123_fixes_declaration_store_isolation.py::test_fixes_declaration_tests_pass_with_a_populated_operator_ledger
FAILED tests/test_123_fixes_declaration_store_isolation.py::test_fixes_declaration_tests_never_open_the_operator_runtime_root_store
2 failed, 3 passed in 1.89s
```

The fourth shape is the one the spec actually names: the operator's own host, whose
`.factory/doctor.db` is 126,267,392 bytes and holds
`interpreter/ci-failure-never-reaches-an-agent` — the key the declaring fixture spec
names, which is why the layer *ran* there and the skip the old assertion demanded was
empty. Run from that directory, against that ledger, after the fix:

```
$ cd /home/admin/code/ergane
$ env -u ERGANE_ROOT -u FACTORY_ROOT PYTHONPATH=<worktree> \
    .venv/bin/python -m pytest -q -p no:cacheprovider <worktree>/tests/test_spec_declares_its_fixes.py
.............                                                            [100%]
13 passed in 0.19s
```

The ledger's mtime is unchanged by that run. It is not read; it is not opened.

## A surface neither story of this spec covers

**Nine of the twenty-four failures above belong to no task slice in this epic.** They are
`tests/test_final_sweep.py` (seven) and `tests/test_controlplane_direct_mode.py` (two),
and they are the same defect class in the same shape:

```
tests/test_final_sweep.py:88             PERSONA = "implementer"
tests/test_controlplane_direct_mode.py   persona="implementer"  (lines 163, 262, 324, 358)
```

`tests/test_final_sweep.py:88` is byte-identical to the `tests/test_poll_usage.py:59` this
spec was written for, which is itself byte-identical to the
`tests/test_usage_activities.py:74` that 122/US2 removed. All nine pass with the registry
restored — the same three files, unswapped, report `633 passed in 1.71s` — so they are
swap-induced and not pre-existing.

US2 does not touch them: its slice is one file, and editing `test_final_sweep.py` would be
starting work no task names. They are recorded here rather than fixed because the lesson
this spec exists to record is that a *measured* remainder beats a predicted one, and the
operator's success criterion — "`uv run pytest -q` shows no failure that is not a known
live-tier failure" — is not met by US1 and US2 together. FR-003's suite-wide check, if
US1 writes it to catch any fixture leasing a key against a registry-read persona name
rather than only the fixtures in its own file, catches these nine as well.

## The gate, with the registry as it stands

The same whole suite, `personas.yaml` back to `agent: claude-code` /
`ollama-cloud/glm-5.3` / `local/qwen3.6-27b`, with this story's two files in it:

```
5234 passed, 58 skipped, 7 warnings in 370.17s (0:06:10)
```

Both runs collected the same 5,234 tests, so the whole of the difference is the twenty-four
above: nothing outside the swap changed, and the gate is green as it stands.

