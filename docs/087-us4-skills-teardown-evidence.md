# 087-US4 — skill teardown preservation and ordering evidence

Command: `uv run pytest -q`

Actual full-gate result: `6170 passed, 58 skipped, 15 warnings in 612.21s`.

The compact preservation/ordering controls are committed in
`tests/test_087_us4_skills_teardown.py`:

- `test_wide_uninstall_purge_preserves_only_needed_skill_evidence` proves that
  the modified skill path stays, only the modified manifest entry survives, and
  unrelated state files and directories are removed.
- The same test asserts `5/7 skill teardown` precedes `6/7 clear state`, then
  runs teardown again and verifies that the retained record still names the
  modified skill entry.
- `test_check_drives_real_skill_and_state_surveys_without_performs` asserts the
  check records no perform, leaves the filesystem snapshot unchanged, and
  observes the same `5/7` before `6/7` order.
- `test_malformed_manifest_refuses_before_the_wider_teardown_acts` is the
  negative control: a malformed manifest leaves the filesystem snapshot
  unchanged and refuses before wider teardown acts.
