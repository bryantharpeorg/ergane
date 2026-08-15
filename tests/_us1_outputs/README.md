# US1 verification outputs

These files are the runtime evidence required by the acceptance scenarios for
US1 of epic 043-runtime-root-integrity.  Each file contains pasted tool output;
no prose description substitutes for the run.

- `us1-s01-populated-pass.txt` — `test_leaking_writers_are_contained` passing on a
  populated `.factory/verification.db` layout built in pytest tmp, with size and mtime
  identical before and after.
- `us1-s01-original-assertion-failure.txt` — the same test failing when the original
  non-existence assertion is reinstated against the populated layout (SC-004 control).
- `us1-s02-control-failure.txt` — the control test failing when the detector is asked
  to ignore a write to the cwd-relative default path, naming the offending path.
- `us1-s03-absent-pass.txt` — the test passing on a checkout with no runtime root
  directory and creating none.
- `us1-s04-audit.txt` — line-by-line audit of every non-existence assertion in
  `tests/test_store_isolation.py`, confirming each remaining one is safe.
