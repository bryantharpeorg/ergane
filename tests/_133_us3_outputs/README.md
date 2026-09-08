# 133-US3 verification outputs

Runtime evidence required by US3's acceptance scenarios (epic 133). Each file
holds pasted tool output; no prose substitutes for the run.

(`tests/_us3_outputs/` beside this directory is epic 043-US3's — the
`_us<story>_outputs` name collides across epics, so this one carries the epic
number.)

- `t071_checked_sequence_and_diff_size.txt` — T071: the `checked` sequence
  `validate_spec` returns for one real spec beside the sequence the verb prints
  for the same spec — identical, in the seeded-then-appended order — plus the
  zero-diff corpus sweep over all 147 specs of `specs/` (both faces agreeing on
  verdict, findings, checked, skipped, information and judge-evidence
  presence), and the assembled diff size against the 52,400-byte working
  ceiling.