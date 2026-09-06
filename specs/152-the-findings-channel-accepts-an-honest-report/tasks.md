# Tasks: the findings channel accepts an honest report

Read `plan.md` before starting. Trap 1 is the one that will cost you the whole
story: the document this spec came from names `factory/doctor/cli.py:43` as the
line to fix, and no command reads that module — the live door is
`factory/cli/doctor.py:450` — `findings_report_command`, reading the copy at
`factory/cli/doctor.py:58`. Trap 2 is the second-order version of the same
mistake: the pattern exists **four** times, and two of those copies redact on the
way **out** — the scaffolder's, into a promoted spec, and the exporter's at
`factory/cli/repo_export.py:55`, into a file the operator hands to someone else —
so a one-line fix is a quarter of a fix. Trap 3 forbids writing the trigger string
or the pattern's own source literally anywhere in this diff, including docstrings
and pasted evidence — build them from fragments. Trap 4 is why this spec has two
stories: anchoring the pattern does nothing at all about the partial write.

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the judge
sees; runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

## Phase 1: User Story 1 — A hyphenated English word is not a credential

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001, traps 1 and 3) Report, through the CLI
      the way `tests/test_ergane_findings.py:37` — `_invoke` does, a finding whose
      note contains a word whose final two letters are the pattern's two,
      immediately followed by a hyphen and a ten-character lower-case tail.
      Assert the verb exits 0 and the stored note equals the submitted text
      character for character. **Assemble the word from separate string fragments**
      — a literal makes this test file unquotable in a finding, which is the bug.
      Drive it through the CLI, not through `_contains_secret`: a helper-level test
      would pass against the legacy module and prove nothing about the live door.
- [ ] T002 [P] [US1] (spec US1-S2, FR-002, trap 7) **The control.** Report a
      synthetic credential value — also built from fragments — twice: once after a
      space and once after an `=`. Assert both are refused, through the batch door
      and the single door, and that no row was written by either. A diff that
      satisfies T001 by deleting or defanging the sweep must fail here.
- [ ] T003 [P] [US1] (spec US1-S3, FR-003, trap 2) Seed a finding whose note
      contains the T001 word, promote it, and assert the scaffolded trio contains
      that word intact and does **not** contain the redaction marker. This is the
      path through `factory/doctor/scaffold.py:281` — `_sanitize_text`, which a
      refusal-only fix leaves rewriting honest prose.
- [ ] T004 [P] [US1] (spec US1-S4, FR-004, trap 2) Import
      `factory.cli.doctor`, `factory.doctor.scaffold`, `factory.doctor.cli` and
      `factory.cli.repo_export` and assert all four name the **same** compiled
      pattern object by identity (`is`) — for `repo_export` that is the first
      element of `_SECRET_PATTERNS` at `factory/cli/repo_export.py:55` — so no
      future correction can be applied to part of the sweep and declared whole.
      Assert also that the other two elements of that tuple are still present, so
      the identity edit cannot be made by deleting them.
- [ ] T005 [P] [US1] (spec US1-S5, FR-002, FR-003, traps 2 and 3) The export door.
      Beside `tests/test_ergane_repo_forget.py:540` —
      `test_no_credential_shaped_value_reaches_an_exported_file`, add a case that
      seeds, through `tests/test_ergane_repo_forget.py:113` — `seed_stores`, a
      findings row whose text carries **both** the T001 word and a synthetic
      credential at a token boundary, exports, and asserts the written
      `findings.jsonl` holds the word intact **and** the redaction marker in place
      of the credential. Both halves matter: the first is the defect, the second is
      the control that `factory/cli/repo_export.py:197` — `_clean` was not
      loosened. Build both fragments the way trap 3 requires; do not copy the
      existing fixture value at `tests/test_ergane_repo_forget.py:61-65`.

### Implementation for this story

- [ ] T006 [US1] (FR-001, FR-004, traps 2 and 7) Give the pattern one home and
      anchor it there: a lookbehind that refuses an ASCII letter or digit
      immediately before the two-letter prefix, and **nothing more** — a credential
      after `=`, after a hyphen, or at the start of a value must still match.
- [ ] T007 [US1] (FR-004, trap 2) Collapse the four module-level definitions —
      `factory/cli/doctor.py:58`, `factory/doctor/scaffold.py:21`,
      `factory/doctor/cli.py:43` and the first element of `_SECRET_PATTERNS` at
      `factory/cli/repo_export.py:55` — so that exactly one of them (or the new
      home module T006 creates) compiles the object and every other one imports
      it, so
      `factory/cli/doctor.py:76` — `_contains_secret`,
      `factory/cli/doctor.py:82` — `_sanitize_text`,
      `factory/doctor/scaffold.py:281` — `_sanitize_text` and
      `factory/cli/repo_export.py:197` — `_clean` all consult one pattern. Leave
      the two sibling shapes in that tuple and the doctrine comment at
      `factory/cli/repo_export.py:50-53` exactly as they are.
- [ ] T008 [US1] (FR-003) Confirm by reading that the promote, scaffold and export
      paths need no edit of their own once T007 lands: `factory/cli/doctor.py:537`,
      `factory/doctor/scaffold.py:53` and `factory/cli/repo_export.py:201` reach
      their substitutions through the helpers T007 rewired. Then re-run the count
      check from trap 2 across `factory/` and state the result in the PR: if it
      names a module this plan did not, a fifth copy exists and the identity test
      must grow to cover it before this story lands.

### Verification for this story

- [ ] T009 [US1] Paste, as committed evidence, four short transcripts against a
      scratch store: the hyphenated-word report accepted with its note read back
      intact, the synthetic credential still refused, the promoted trio's text
      showing the word rather than the marker, and the exported `findings.jsonl`
      showing the word intact beside the marker where the credential was. Assemble
      the fragments in the shell so no file in the diff holds the trigger or the
      pattern source literally (trap 3).

## Phase 2: User Story 2 — A refusal says where it matched, and refuses before it writes

### Tests for this story (write FIRST, must fail)

- [ ] T010 [P] [US2] (spec US2-S1, FR-005, trap 8) Report a note carrying a
      synthetic credential twenty characters in. Assert the refusal names the field
      (`notes`), names the zero-based offset, and quotes the up-to-twelve
      characters of that field immediately preceding the match.
- [ ] T011 [P] [US2] (spec US2-S2, FR-006, trap 8) **The control that keeps T010
      safe.** Assert the matched value appears nowhere in the refusal text and that
      the redaction marker stands in its place. Truncating the match is not
      redacting it.
- [ ] T012 [US2] (spec US2-S3, FR-007, FR-008, traps 5 and 6) Seed the first
      entry's key through the store API with an explicit `seen_at`, the way
      `tests/test_ergane_findings.py:64` — `seeded_db` does. Run a three-entry
      batch whose **third** entry carries a synthetic credential. Assert the batch
      is refused, that no new row exists, and that the seeded row still reads
      `occurrences` 1 with its original `last_seen`. Do **not** rely on the autouse
      fixture at `tests/test_ergane_findings.py:106` — `_freeze_doctor_utcnow`: it
      patches the legacy module and does not reach
      `factory/cli/doctor.py:61` — `_utcnow`. Not `[P]`: it shares the store
      fixture with T013.
- [ ] T013 [US2] (spec US2-S4, FR-007) Run a batch whose **second and fourth**
      entries each carry a synthetic credential and assert the refusal names both
      keys, in file order, in one message — the shape
      `factory/doctor/models.py:66` — `raise_if_any` already uses for the grammar.
- [ ] T014 [P] [US2] (spec US2-S5, FR-009, trap 9) Refuse the same text through
      the single door and the batch door and assert both messages carry the same
      field, offset and preceding-context rendering, proving one formatter serves
      both rather than one door being corrected alone.

### Implementation for this story

- [ ] T015 [US2] (FR-005, FR-006, FR-009, traps 8 and 9) Make the sweep return
      where it matched instead of a bare `bool` —
      `factory/cli/doctor.py:76` — `_contains_secret` throws the match object away
      — and add one refusal formatter that renders field, offset, preceding context
      and the redaction marker. Do **not** compile a second pattern in the refusal
      path; that is how the extra copies were born (FR-004).
- [ ] T016 [US2] (FR-007, FR-008, trap 4) Hoist the sweep above the write loop in
      `factory/cli/doctor.py:450` — `findings_report_command`: today the loop opens
      at `factory/cli/doctor.py:457`, the refusals sit at
      `factory/cli/doctor.py:458` and `factory/cli/doctor.py:462`, and the write is
      the next statement at `factory/cli/doctor.py:466`. Sweep every parsed entry
      first, collect every offender, raise once — the shape
      `factory/doctor/models.py:81` — `parse_findings_batch` already uses.
- [ ] T017 [US2] (FR-009) Route the single door's refusals —
      `factory/cli/doctor.py:482` and `factory/cli/doctor.py:484` — through the
      same formatter, so the two doors cannot drift.
- [ ] T018 [US2] (FR-008) Confirm by reading that no rollback code was needed:
      `factory/doctor/store.py:137` — `report` commits per call at
      `factory/doctor/store.py:149`, so FR-008's guarantee comes from writing
      nothing, not from undoing a write — which is why FR-008 is scoped to the
      grammar check and the credential sweep and claims nothing about a sqlite
      failure part-way through the loop. If you find yourself opening a transaction
      around the loop, the hoist did not happen.

### Verification for this story

- [ ] T019 [US2] Paste, as committed evidence, two short transcripts against a
      scratch store: the refusal for a note carrying a synthetic credential, showing
      the field, the offset and the preceding characters and **not** the value; and
      the three-entry batch run against a store holding the first key, with
      `ergane findings list --json` before and after showing `occurrences` and
      `last_seen` unchanged.

## Verification

- [ ] T020 The full gate command passes green.
- [ ] T021 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end against a scratch store. Step 6 is the falsifiable
      test of this whole spec: file this spec's own two ledger rows again, verbatim,
      notes included, through `ergane findings report --batch`. The report that
      documents the bug must be fileable by the bug, and it is refused today.
