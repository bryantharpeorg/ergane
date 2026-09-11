# US1 synthetic omission evidence

Synthetic execution: no model, proxy, or live service was used.

## Old control, before repair

The parked test supplied `complete("target", option=None)` and used a
constant-return callee, so it could not distinguish omission from explicit
null.  It passed:

```text
tests/test_judge.py::test_the_parked_completion_fixture_omission_is_safe_as_written PASSED [100%]
============================== 1 passed in 0.10s ===============================
```

## Recording-callee observation

```text
true_omission_capture=('explicit',)
true_omission_result='target:explicit'
explicit_none_capture=('explicit', 'omitted')
explicit_none_result=OmittedOptionError: option is required when omitted
```

## Corrected parked control

```text
tests/test_judge.py::test_the_parked_completion_fixture_omission_control_records_the_callee PASSED [100%]
============================== 1 passed in 0.15s ===============================
```

## Repaired after-sources

```text
completion_results=[('explicit option', 'target:explicit'), ('omitted option', 'OmittedOptionError', 'option is required when omitted')]
safety_results=[('[SANITIZED]', 'raw slug')]
completion_diff_matches=True
safety_diff_matches=True
completion_system_matches_source=True
safety_system_matches_source=True
```

## Story payload

Focused judge, parser, gate, contradiction, and diff-bound controls:

```text
90 passed in 0.16s
```

Full declared gate:

```text
6277 passed, 58 skipped in 652.04s
```

```text
story_files=4
story_diff_bytes=24117
diff_limit_bytes=65536
factory/verify/judge.py
specs/002-verification-gating/contracts/judge.md
specs/173-an-omission-control-actually-omits-the-option/evidence/us1-omission-red-green.md
tests/test_judge.py
```
