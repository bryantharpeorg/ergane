# US2 verification outputs

These files are the runtime evidence required by the acceptance scenarios for
US2 of epic 133-spec-validate-has-one-implementation-and-two-faces. Each file
contains pasted tool output; no prose description substitutes for the run.

- `t017_golden_comparison.txt` — the comparison of this story's stdout, stderr
  and `--json` output over both fixture trios against US1's six golden
  artifacts (T017, spec US2-S3, FR-006, plan trap 19): empty on all three
  streams, plus the `git diff --stat` line for the story and the
  byte-identity proof for the moved source. The standing guard that keeps the
  comparison empty is `tests/test_133_us1_typed_report_and_golden_captures.py`.