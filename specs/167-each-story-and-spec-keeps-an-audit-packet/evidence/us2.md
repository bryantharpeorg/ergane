# US2 evidence

Ran: uv run pytest -q tests/test_attestation_*.py

Result: 31 passed, 1 warning in 26.81s.

Before: fully_fixed=false, coverage=absent, composed_verdict=PASS, gate_truncated=true, judge_status=valid, objection=US2-S1: gate would fail.

After: fully_fixed=true, base=40×a, attempted=40×b, verified=40×c, files=4 (1 binary, 1 rename), log_truncated=true, coverage=absent, resolution=US2-S1 verified-fixed via job-1:valid:2 at rev-2.
