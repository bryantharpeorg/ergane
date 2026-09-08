# US7 verification outputs

Runtime evidence required by US7's acceptance scenarios (epic
133-spec-validate-has-one-implementation-and-two-faces). Each file holds pasted
tool output; no prose description substitutes for the run.

- `t058_golden_comparison.txt` — T058: the comparison of `ergane spec validate`
  over both US1 fixture trios against the six committed golden artifacts, empty
  on all three streams, plus this story's `git diff --stat`, its assembled byte
  count against the 52,400-byte working ceiling, and the byte-identity proof
  that the moved source span left the CLI module unchanged.