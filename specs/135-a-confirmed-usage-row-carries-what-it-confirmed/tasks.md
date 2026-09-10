# Tasks: a confirmed usage row carries what it confirmed

0.6 coordination (2026-09-10):167 owns audit packet acquisition/identity and
per-metric completeness. These tasks remain the existing three usage-correctness
slices; they do not make a request-only confirmed row token-complete. Preserve
160's eventual source-specific evidence when refining against its landed writer.
US2's recorded spend-contract decision hold remains; do not ready/dispatch the
whole trio without resolving it or explicitly splitting that slice. No live
ledger repair is part of this specification update.

Read `plan.md` before starting. Trap 1 is the test that pins this defect as
intended behaviour and must be amended rather than reverted or deleted. Trap 2
is the one-line fix that puts the change in the wrong function and silently
rewrites the dollar figure on the way past. Trap 4 is the version stamp that
cannot gate a migration, and trap 9 is why a correct repair looks broken when
the test forgets to reopen the database. Trap 11 is the one existing assertion
the spend half is expected to turn red — it is inside the test the flag half
amends, four lines below it — and trap 12 is the pair of scope errors around
the predicate: the name that does not exist at the line the flag goes on, and
the dict key that does not exist yet at the line the spend goes on, which is
why the predicate is a helper both stories call rather than an expression each
writes. Trap 13 is the fixture helper that cannot build the row User Story 1's
third test needs, and the `0` that suggests itself instead, which is green and
wrong. Trap 14 is the column comment User Story 2 makes false, which lives in
two files that no test compares — comments are stripped before the comparison
— so both have to be corrected by hand. Trap 6 is spec 024, which reads as a
standing prohibition on User Story 3's repair and is not one: 024 deferred the
backfill in writing at `specs/024-ledger-token-honesty/spec.md:123` and this
is where it lands. Trap 3 governs whether User Story 2 is dispatchable at all:
if `docs/decisions.md` carries no entry authorising the reversal, that story
was dispatched in error — say so in the attempt instead of inventing a `D-`
number.

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the
judge sees; runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already
editing.

## Phase 1: User Story 1 — The flag says whether the row carries counts

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001, trap 1) Given a proxy that answers
      `/key/info` and returns an empty spend-log row set, assert the stored
      row has `final_usage_confirmed is False` with `prompt_tokens`,
      `completion_tokens` and `request_count` all `None`. This is the
      assertion the suite currently makes backwards. Assert the flag and the
      three counts only — **do not assert `spend_usd` here**: an unpinned
      counter is `0.0` (`tests/conftest.py:142` — `add_spend_row` is the only
      thing that raises it), which is exactly the value User Story 2 nulls, so
      an assertion here is one more line that story would have to come back
      and rewrite (trap 11).
- [ ] T002 [P] [US1] (spec US1-S2, FR-003, trap 8) **The control.** Given
      spend logs that carry rows with token counts, assert the flag is still
      `True` and every count and the spend figure are unchanged. Four existing
      tests assert the same thing from other angles —
      `tests/test_usage_activities.py:564` — `test_teardown_records_the_attempts_usage_from_proxy_data`
      (its flag assertion at line 574),
      `tests/test_usage_activities.py:787` — `test_a_failed_revocation_still_records_the_attempt`
      (line 798), `tests/test_subscription_accounting.py:210` — `test_gateway_attempt_records_exactly_as_today`
      (line 226) and `tests/test_final_sweep.py:718` — `test_a_runaway_attempt_is_treated_exactly_like_a_cheap_one`
      (line 746) — and all four must stay green untouched. Three further
      assertions read the same flag on the live tiers —
      `tests/test_live_proxy.py:491` — `test_the_ledger_tokens_reconcile_with_the_proxys_spend_logs`,
      `tests/test_live_proxy.py:549` — `test_the_attempt_lands_as_exactly_one_attributed_row`
      and `tests/test_live_judge.py:567` — `test_the_recorded_tokens_are_the_judges_own`
      — and must be left unedited too, but they are **not** part of this
      diagnostic: both modules skip without proxy credentials, no CI job and
      no node gate runs them, and `tests/test_live_judge.py` is already red on
      this spec's own trigger finding. Never read a red there as a verdict on
      this change.
- [ ] T003 [P] [US1] (spec US1-S3, FR-001, trap 13) **The control**, and the
      only one that constrains the shape of the predicate rather than its
      result: it passes against today's code and must still pass afterwards,
      and it fails only against a narrowed `prompt_tokens is not None` rule.
      Given three spend-log rows none of which reports a prompt or completion
      token column, assert the flag is `True` and `request_count` is `3`. Do
      not try to make it red first — the one way to do that is to widen the
      predicate, which is trap 8's named wrong move. The boundary the
      three-metric rule has to decide out loud: a drained row is a measurement
      even when its token columns are absent. Build the rows by appending raw
      dicts — `spend`, `model` and `request_id`, no token keys — to the fake's
      `spend_rows` store at `tests/conftest.py:114`, which
      `tests/conftest.py:409` — `_spend_logs` serves as-is.
      `tests/conftest.py:142` — `add_spend_row` **cannot** build this row: it
      declares both token counts as required `int`s and sums them. Do not pass
      `0` for them either — a reported zero is a measurement,
      `factory/usage/aggregate.py:90` — `_accumulate` folds it into the
      aggregate, and the scenario would pass while no longer distinguishing
      the three-metric rule from a narrow `prompt_tokens is not None`
      predicate.
- [ ] T004 [US1] (spec US1-S4, FR-002, traps 2 and 11) Given a lease whose
      last heartbeat snapshot carries a spend that differs from the key's
      `/key/info` counter, and a proxy that answers both reads with no rows,
      assert **in one test** that the flag is `False` **and** that `spend_usd`
      is the key's counter, not the snapshot's. Force the counter to a
      non-zero `0.42` with `tests/conftest.py:192` — `set_spend` against the
      `0.0417` snapshot at `tests/test_usage_activities.py:93`: an unforced
      counter is `0.0`, which is the exact value User Story 2 nulls, and an
      unpinned assertion here is one more line that story would have to
      rewrite. Not `[P]`: it is the pair of assertions that refuses the wrong
      fix, and it must be read as one scenario. A diff that made
      `_read_final_usage` return `None` for an empty row set passes the first
      assertion and fails the second.
- [ ] T005 [US1] (spec US1-S5, FR-005, traps 1 and 11) Amend
      `tests/test_usage_activities.py:626-645` —
      `test_an_attempt_that_never_called_the_proxy_records_unmeasured` in
      place: keep the docstring's claim, which already states this spec's
      rule, and invert the assertion at `tests/test_usage_activities.py:639`.
      Do not delete it, do not mark it skipped, and do not rename it away.
      Leave the spend assertion at `tests/test_usage_activities.py:643`
      exactly as it is — this story does not change the dollar figure, and
      that line belongs to User Story 2 (FR-014).

### Implementation for this story

- [ ] T006 [US1] (FR-001, FR-002, traps 2, 7 and 12) Add a module-level helper
      to `factory/activities/usage_activities.py` that takes the three count
      values as arguments and returns `True` when at least one of them is not
      `None`, and at `factory/activities/usage_activities.py:594` — `_record_for`
      replace `final_usage_confirmed=confirmed is not None` with a call to it
      over the three count values `_record_for` has already built into its
      `usage` dict — `usage["prompt_tokens"]`, `usage["completion_tokens"]`,
      `usage["request_count"]`. The helper is not decoration and must not be
      inlined back into the call site: User Story 2 has to apply the same rule
      from a line where the `usage` dict does not exist yet (T014), and a
      helper taking three values is the only shape both stories can share,
      which is what makes the flag and the spend unable to disagree (FR-002,
      trap 12). Do **not** write the call at line 585 against `aggregate`: it
      is bound only inside the `else` branch at
      `factory/activities/usage_activities.py:575` — `_record_for` and raises
      `UnboundLocalError` on the other two paths. That is about this call
      site only — User Story 2 calls the same helper *with* `aggregate`'s
      three fields from inside that `else` branch, where it is bound, and
      that is correct (T014, trap 12). All three of those dict
      values are `None` on the subscription and read-failure branches, so
      FR-004 falls out of the same expression. Take the rule itself from
      `factory/usage/aggregate.py:42-45`, which already states it. Do **not**
      change `factory/activities/usage_activities.py:506` — `_read_final_usage`,
      whose `None` means "a read failed" and routes the row into the snapshot
      fallback. Do **not** confine the change to
      `factory/activities/usage_activities.py:526` — `_is_subscription_lease`;
      070-US4 fixed a different empty-usage case and the defective rows all
      have real keys.
- [ ] T007 [US1] (FR-004) Leave the subscription branch at
      `factory/activities/usage_activities.py:552` — `_record_for` and the
      read-failure fallback at `factory/activities/usage_activities.py:563` — `_record_for`
      writing `final_usage_confirmed` false with the spend figures they write
      today. Both are already honest; the diff must show them unchanged.
- [ ] T008 [US1] (FR-001) Leave the two cache metrics out of the predicate.
      `factory/usage/aggregate.py:90` — `_accumulate` leaves them `None`
      whenever no row reported them, so including them would mark a fully
      measured attempt unconfirmed on any backend that publishes no cache
      block.
- [ ] T009 [P] [US1] (spec US1-S6, FR-013) Rewrite the two-shape paragraph in
      the docstring at `factory/usage/models.py:139` — `UsageRecord` so it
      states what the flag now means — the row carries at least one count —
      instead of "On the confirmed path every field is populated from proxy
      data". Do not re-assert that a confirmed reading populates every field:
      User Story 2 adds a confirmed-path row with a `NULL` spend, and this
      paragraph should still be true afterwards. `[P]`: a different file from
      every other task in this phase.

### Verification for this story

- [ ] T010 [US1] Paste, as committed evidence, the row a teardown writes
      against an empty spend-log row set before and after the change — flag,
      three counts and spend in both — so the inversion is legible without
      re-running anything.

## Phase 2: User Story 2 — A dollar figure nothing was attributed to is not a measurement

### Tests for this story (write FIRST, must fail)

- [ ] T011 [US2] (spec US2-S1, FR-006, FR-014, trap 11) Amend in place, from
      `assert record.spend_usd == 0.0` to the `None` this story writes, the
      `spend_usd` assertion inside `test_an_attempt_that_never_called_the_proxy_records_unmeasured`
      — the test User Story 1 already amended. It stood at
      `tests/test_usage_activities.py:643` when this spec was written and User
      Story 1 has since added tests to that module, so find it by that test's
      name and the assertion's text rather than by the number. That test's
      proxy answers with no rows and its key counter is `0.0` by construction
      (`tests/conftest.py:142` — `add_spend_row` is the only thing that raises
      it), so it *is* this story's first scenario. Leave the rest of the test
      alone, including the flag assertion User Story 1 inverted, four lines
      above it — find that one the same way, by the test's name and the
      assertion's text, not by a number this spec recorded before User Story 1
      added tests to the module. Do not add a second test asserting `None`
      beside one asserting `0.0`. Not `[P]`: it edits a region User Story 1
      has just touched.
- [ ] T012 [P] [US2] (spec US2-S2, FR-007) Given an empty spend-log row set
      and a non-zero `/key/info` counter, assert `spend_usd` is that figure.
      167 of this host's 397 defeating rows are this shape and nulling them
      would discard a measurement the proxy did take.
- [ ] T013 [P] [US2] (spec US2-S3, FR-008, trap 3) **The control.** Given
      spend logs whose row sum differs from the key's counter, assert
      `spend_usd` is still the counter, and leave
      `tests/test_usage_activities.py:604` — `test_the_confirmed_spend_is_the_keys_own_total`
      untouched. Summing the rows instead of reading the counter is the wrong
      fix and that test is the deliberate contract it would break.

### Implementation for this story

- [ ] T014 [US2] (FR-006, FR-007, traps 3 and 12) In the confirmed branch, at
      `factory/activities/usage_activities.py:582-584` — `_record_for`, write
      `None` for `spend_usd` when the aggregate is not a measurement **and**
      the key's counter is `0.0`, and keep the counter in every other case.
      Decide "not a measurement" by **calling User Story 1's module-level
      helper** with `aggregate.prompt_tokens`, `aggregate.completion_tokens`
      and `aggregate.request_count` — the names bound at
      `factory/activities/usage_activities.py:575` — `_record_for`, which are
      the same three values the flag reads. Do not restate the predicate as a
      second expression, and do not reach for `usage["prompt_tokens"]` here:
      at this line the `usage` dict is still being built and that key does not
      exist yet, which is the mirror image of trap 12. Do not hoist a local
      above the dict either — that edit lands on
      `factory/activities/usage_activities.py:594` — `_record_for`, the line
      trap 8's four control tests watch. The shared helper is what makes "the
      flag and the spend cannot disagree" a fact about the code rather than an
      instruction.
- [ ] T015 [US2] (spec US2-S4, FR-009, trap 3) Name, in the comment beside
      that branch, the `docs/decisions.md` entry that authorises the reversal
      — its `D-` identifier **and** its heading line quoted verbatim, so an
      identifier no entry carries is visible in the diff itself. It reverses
      the first sentence of `factory/usage/litellm_client.py:268` — `get_spend`'s
      docstring, which documents a returned `0.0` as a real measurement. **If
      no such entry exists when you read this, stop and report it**: this
      story was dispatched before the decision it depends on, and an invented
      identifier is worse than a failed attempt.
- [ ] T016 [US2] (spec US2-S5, FR-015, trap 14) Correct the `spend_usd` column
      annotation this story falsifies — "NULL only if no snapshot ever taken"
      — at both of the sites that carry it: `factory/usage/ledger.py:75`,
      inside the `_SCHEMA_DDL` literal, and
      `specs/001-usage-tracking/contracts/ledger-schema.sql:27`, which
      `factory/usage/ledger.py:55` declares that literal verbatim from. Same
      new text in both, naming the case this story introduces: `NULL` also
      means nothing was attributed to the key, so there was no price to
      record. Change nothing else in either file — not the type, not a
      constraint, not the column order. No test can catch a mistake here:
      `tests/test_ledger_schema.py:135` — `_canonical` strips `--` comments
      before `tests/test_ledger_schema.py:189` — `test_a_new_ledger_matches_the_published_contract_ddl`
      compares the two schemas, so the two files can drift apart with the
      suite green. Not `[P]`: the DDL file is the one file this story shares
      with User Story 3, which the Work Graph waives with `concurrent_with`
      because the regions are more than a hundred lines apart.

### Verification for this story

- [ ] T017 [US2] Paste, as committed evidence, two things: the two rows
      written against an empty spend-log row set — one with a `0.0` counter,
      one with a non-zero counter — showing `NULL` in the first and the figure
      in the second; and the output of `grep -n '^## D-0' docs/decisions.md |
      tail -3`, which is what proves the entry the comment cites existed when
      this attempt ran.

## Phase 3: User Story 3 — The rows already written say what they measured

### Tests for this story (write FIRST, must fail)

- [ ] T018 [US3] (spec US3-S1, FR-010, trap 9) Write a legacy row with
      `tests/test_ledger_schema.py:106` — `raw_insert` (whose defaults are
      already this shape: flag `1`, all three counts `None`), **close the
      connection**, reopen the same path with `connect`, and assert the row
      now reads `final_usage_confirmed = 0` with `spend_usd`, `id`,
      `key_alias`, `termination` and both timestamps unchanged. Not `[P]`:
      reopening is the fixture shape every other test in this phase builds on.
      A test that asserts on the connection the fixture already opened reads
      `1` and proves nothing.
- [ ] T019 [P] [US3] (spec US3-S2, FR-010) **The control.** Write a legacy row
      carrying `request_count = 3` with the flag at `1`, reopen, and assert it
      is untouched. A repair that flipped every confirmed row would fail this.
- [ ] T020 [P] [US3] (spec US3-S3, FR-011, trap 10) Write two legacy rows, one
      with `spend_usd = 0.0` and one with `spend_usd = 0.42`, reopen, and
      assert both keep the figure they were written with. The repair rewrites
      the flag and nothing else — that is what keeps this story free of the
      operator decision User Story 2 waits on.
- [ ] T021 [P] [US3] (spec US3-S4, FR-012, trap 4) Given a database whose
      `schema_version` table records `1`, assert the legacy row is repaired on
      the first reopen and that a second reopen changes no row. The repair is
      a fixpoint and is not gated on the recorded version, which
      `factory/usage/ledger.py:152` — `_bootstrap_schema` never updates for a
      database that already carries one.

### Implementation for this story

- [ ] T022 [US3] (FR-010, FR-011, traps 5 and 6) Add one repair function to
      `factory/usage/ledger.py` and call it from
      `factory/usage/ledger.py:237` — `_migrate` beside
      `factory/usage/ledger.py:188` — `_widen_terminations`. It is a single
      `UPDATE ... SET final_usage_confirmed = 0 WHERE final_usage_confirmed =
      1 AND prompt_tokens IS NULL AND completion_tokens IS NULL AND
      request_count IS NULL`. Do **not** copy `_widen_terminations`'s
      table-rebuild shape: it rebuilds only because `ALTER TABLE` cannot widen
      a `CHECK`. It does **not** churn `id`s, and do not repeat that reason:
      `factory/usage/ledger.py:196-198` says `id` is copied with the rest, and
      the column list at `factory/usage/ledger.py:220-228` is read from
      `PRAGMA table_info(usage_records)`, so it is. The risk a rebuild really
      carries here is the schema text.
      `factory/usage/ledger.py:142` — `_bootstrap_schema` runs `_migrate` on
      **every** `connect`, a brand-new ledger included, so whatever a rebuild
      wrote becomes the DDL `sqlite_master` records — which is exactly what
      `tests/test_ledger_schema.py:189` — `test_a_new_ledger_matches_the_published_contract_ddl`
      compares against the published contract — and its own docstring names
      the other half, "the one migration that could silently drop a column".
      One `UPDATE` touches neither (trap 5).
      `specs/024-ledger-token-honesty/spec.md:117` — "MUST NOT rewrite,
      migrate or backfill any row written before it lands" — is not a standing
      prohibition on this task: 024 scoped the backfill out of itself in
      writing at `specs/024-ledger-token-honesty/spec.md:123` ("a one-off
      operator migration over historical evidence"), and this story is where
      it lands. Cite 024 in the commit rather than treating it as a refusal
      (trap 6).
- [ ] T023 [US3] (FR-012, trap 4) Leave `factory/usage/ledger.py:48`'s
      `SCHEMA_VERSION = 2` alone and add no version gate. The DDL has not
      changed, and `factory/usage/ledger.py:142` — `_bootstrap_schema` stamps
      a version only when none is recorded, so any gate keyed on the stamp
      either never fires or fires forever.
- [ ] T024 [US3] (FR-011) Confirm by reading that
      `tests/test_ledger_schema.py:189` — `test_a_new_ledger_matches_the_published_contract_ddl`
      still passes without an edit. **If it needed one, the design is wrong**:
      this story changes data, not schema.

### Verification for this story

- [ ] T025 [US3] Paste, as committed evidence, a `sqlite3` transcript over a
      scratch database: the row count and the count of flag-`1`-with-no-counts
      rows before the reopen, and the same two counts after — the second
      falling to zero while the first is unchanged.

## Verification

- [ ] T026 The full gate command passes green.
- [ ] T027 The operator sequence in `plan.md` § "Verification the operator
      will run" is executed end to end, starting with the flip check that
      precedes its numbered steps. Step 1 is taken **before** anything lands,
      and step 5 — reopening the host ledger and re-running the baseline query
      — is the falsifiable test of this whole spec, because it is the
      contradiction the hand-over reported, read back out of the operator's
      own ledger.
