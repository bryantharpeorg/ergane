# US2 verification outputs

Runtime evidence required by US2's acceptance scenarios (epic
133-spec-validate-has-one-implementation-and-two-faces). Each file holds pasted
tool output; no prose description substitutes for the run.

- `t017_golden_comparison.txt` — T017: the comparison of `ergane spec validate`
  over both US1 fixture trios against the six committed golden artifacts, empty
  on all three streams, plus this story's `git diff --stat` and its assembled
  byte count against the 52,400-byte working ceiling, plus the byte-identity
  proof that the moved source spans left the CLI module unchanged.