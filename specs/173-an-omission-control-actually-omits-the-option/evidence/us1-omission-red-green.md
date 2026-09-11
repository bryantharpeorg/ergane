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
