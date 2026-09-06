# Implementation Plan: a confirmed usage row carries what it confirmed

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## What already exists, and where

**One assignment site, and it asks the wrong question.**
`factory/activities/usage_activities.py:527` — `_record_for` builds the ledger
row, and its last interesting line is
`factory/activities/usage_activities.py:585` — `_record_for`:

```python
    return UsageRecord(
        epic_id=lease.epic_id,
        node_id=lease.node_id,
        attempt=lease.attempt,
        persona=lease.persona,
        spec_ref=lease.spec_ref,
        key_alias=lease.key_alias,
        final_usage_confirmed=confirmed is not None,
        termination=request.termination,
        issued_at=lease.issued_at,
        torn_down_at=_now_iso(),
        **usage,
    )
```

`confirmed` is a `_ConfirmedUsage | None`. It is `None` for exactly two reasons,
and `rows == []` is not one of them:
`factory/activities/usage_activities.py:497` — `_read_final_usage`, whose body
at `factory/activities/usage_activities.py:507-514` reads

```python
    if client is None:
        return None
    try:
        spend_usd = await client.get_spend(lease.key)
        rows = await client.fetch_spend_log_rows(lease.key, issued_at=lease.issued_at)
    except LiteLLMError:
        return None
    return _ConfirmedUsage(spend_usd=spend_usd, aggregate=aggregate_rows(rows))
```

**The `usage` dict, not `aggregate`, is what the predicate can read.** All three
branches of `_record_for` build the same six-key dict — the subscription branch
at `factory/activities/usage_activities.py:543` — `_record_for`, the
read-failure branch at `factory/activities/usage_activities.py:554` — `_record_for`,
and the confirmed branch, which binds `aggregate` at
`factory/activities/usage_activities.py:566` — `_record_for` and then copies it
in. `aggregate` exists on one of those three paths; `usage` exists on all of
them, and its three count keys are `None` on the two that are already honest.
Trap 12, FR-002.

**The correct rule is already written, in the module that computes the thing
being flagged.** `factory/usage/aggregate.py:39` — `aggregate_rows` says at
`factory/usage/aggregate.py:42-45`:

```
    An empty row set is an unmeasured aggregate: the proxy answered, but it
    answered "no rows", so there is no measurement of prompt, completion or
    request count. A zero is only a zero when a row said so. Cache metrics stay
    `None` when no row reported them.
```

FR-001 is that sentence, applied to the flag. The three metrics it names are the
three the predicate reads; the two cache metrics are deliberately excluded,
because `factory/usage/aggregate.py:90` — `_accumulate` leaves them `None`
whenever no row reported them, so a perfectly measured attempt on a backend that
publishes no cache block would otherwise read unconfirmed.

**The contradiction to cite, three times.** `factory/usage/ledger.py:290-291`
documents `unconfirmed_rows` as "the flag for rows whose token detail is
missing", and the two consumers that compute it are
`factory/usage/ledger.py:300` and `factory/usage/ledger.py:318`, both
`COALESCE(SUM(1 - final_usage_confirmed), 0)`. (The strict-totals rule sits in
the same block, at the prompt, completion and request lines of
`factory/usage/ledger.py:310-319`; it is correct, it is not the line above, and
no story touches it.) Stronger still, because it is in the file that must
change: the teardown module's own docstring at
`factory/activities/usage_activities.py:22-26` —

```
- **A partial reading is not a reading.** If either read fails, the whole
  confirmed path is abandoned for the flagged fallback — the last heartbeat's
  dollar figure, `NULL` tokens, `final_usage_confirmed = 0`. Mixing a confirmed
  spend with absent token detail would publish a row that looks measured and is
  not (FR-005).
```

That paragraph states this spec's rule and the code four hundred lines below it
does the opposite. No edit is needed there — US1 makes the sentence true.

**The third statement, and the only one US1 makes false rather than true.**
`factory/usage/models.py:139` — `UsageRecord` is where a reader goes to learn
what the column means, and it describes a world with exactly two shapes:

```
    On the confirmed path every field is populated from proxy data. On the
    fallback path `final_usage_confirmed` is False, `spend_usd` comes from the
    last snapshot (or is `None` if there never was one), and the token fields
    stay `None` — the row exists, flagged, rather than being invented (FR-005).
```

After US1 there is a third shape — the confirmed read happened, the counts are
`None`, the flag is False — and after US2 a fourth, that shape with a `NULL`
spend. FR-013 rewrites the paragraph once, in US1, phrased so that US2 does not
have to come back to it.

**The two branches that must not move.**
`factory/activities/usage_activities.py:543` — `_record_for` is 070-US4's
subscription branch (NULL everything, flag false) and
`factory/activities/usage_activities.py:554` — `_record_for` is the read-failure
fallback (NULL tokens, snapshot spend, flag false). Both are already honest.
FR-004.

**The spend line and the contract it would reverse.**
`factory/activities/usage_activities.py:573-575` — `_record_for`:

```python
            # The key's own counter, not the row sum: `/key/info` is the
            # contract's final spend, and the rows are the token detail (R2).
            "spend_usd": confirmed.spend_usd,
```

and the counter's own documentation,
`factory/usage/litellm_client.py:268` — `get_spend`, at
`factory/usage/litellm_client.py:268-275`:

```python
    async def get_spend(self, key: str) -> float:
        """The proxy's computed spend for `key` (R9's heartbeat read, R3 step 1).

        A returned `0.0` is a measurement — an unpriced model spends nothing —
        so unknown usage is this method raising, never a zero it invented
        (FR-005). Raises with `status == 404` once the key has been revoked,
        which is the signal teardown falls back on.
        """
```

US2 reverses the first sentence of that docstring for one case only: a `0.0`
counter with an empty row set. Trap 3.

**The column annotation US2 falsifies, and the test blind to it.**
`factory/usage/ledger.py:75` is one line of `_SCHEMA_DDL`:

```sql
    spend_usd              REAL,                             -- NULL only if no snapshot ever taken
```

`specs/001-usage-tracking/contracts/ledger-schema.sql:27` carries that line
character for character, which is what `factory/usage/ledger.py:55` claims of
the whole block ("Verbatim from `contracts/ledger-schema.sql`"). After US2 a row
torn down with a snapshot in hand can store `NULL` — the row
`tests/test_usage_activities.py:626` — `test_an_attempt_that_never_called_the_proxy_records_unmeasured`
writes is torn down with the `0.0417` snapshot
`tests/test_usage_activities.py:148` — `tear_down` passes by default at
`tests/test_usage_activities.py:153` — `tear_down` — so the annotation becomes
false in both files. Nothing in the suite notices:
`tests/test_ledger_schema.py:135` — `_canonical` strips every `--` comment
before `tests/test_ledger_schema.py:189` — `test_a_new_ledger_matches_the_published_contract_ddl`
compares the two schemas structure for structure. FR-015, trap 14.

**Where the fake's `0.0` counter comes from.**
`tests/conftest.py:142` — `add_spend_row` is the only thing that raises the fake
key's counter, so any test with an empty spend-log row set has a `/key/info`
counter of exactly `0.0` unless it forces one with
`tests/conftest.py:192` — `set_spend`. That is why
`tests/test_usage_activities.py:643` reads `record.spend_usd == 0.0` today, why
US1-S4 pins its counter, and why US2 has to amend that line. Trap 11. It is also
why the token-less row US1-S3 needs cannot be built through that helper at all —
trap 13.

**No repair path, and the migration hook that would carry one.**
`factory/usage/ledger.py:242` — `upsert_record` is the only writer.
`factory/usage/ledger.py:237` — `_migrate` is two lines and calls only
`factory/usage/ledger.py:188` — `_widen_terminations`. It is invoked from
`factory/usage/ledger.py:142` — `_bootstrap_schema`, on every `connect`, before
the connection is handed back — which is why a repair placed there reaches an
operator the first time any activity opens the ledger, with no new command.

**The version stamp cannot gate it.** `factory/usage/ledger.py:48` carries
`SCHEMA_VERSION = 2`, and `factory/usage/ledger.py:152` — `_bootstrap_schema`
inserts a version row **only when none is recorded**. An existing ledger keeps
whatever number it was first stamped with, forever. That is the same reasoning
the comment above `_widen_terminations` already states — "a version is a claim
and the schema is the fact" — and it is why the repair is written as a fixpoint
rather than as a versioned step. FR-012.

**The offline shapes the tests already have.**
`tests/test_ledger_schema.py:167` — `ledger` is a `connect`-ed scratch database,
`tests/test_ledger_schema.py:162` — `db_path` is its path,
`tests/test_ledger_schema.py:106` — `raw_insert` writes a row with plain SQL so
the DDL's constraints answer, and
`tests/test_ledger_schema.py:82` — `make_record` builds a populated
`UsageRecord`. US3 needs all four.
`tests/test_ledger_schema.py:189` — `test_a_new_ledger_matches_the_published_contract_ddl`
compares a fresh ledger's schema against the published contract file structure
for structure, and is the test a table rebuild would put at risk.

## Traps

**Trap 1 — A test pins the defect as intended behaviour, and its own docstring
argues against it.** `tests/test_usage_activities.py:626-645` is
`test_an_attempt_that_never_called_the_proxy_records_unmeasured`. Its docstring
says "The proxy answered 'no rows' — there is no measurement, so tokens are
NULL", and then `tests/test_usage_activities.py:639` — `test_an_attempt_that_never_called_the_proxy_records_unmeasured`
asserts `record.final_usage_confirmed is True` beside three `None` counts and
`spend_usd == 0.0`. That is the hand-over's judge row, reproduced by the suite.
The wrong move is to read the red as a regression and revert the change, or to
delete the test to make the suite green. FR-005 requires it amended in place:
the docstring is the requirement and the assertion is the bug. US1 inverts the
flag assertion and leaves the spend assertion alone; trap 11 is the other half.

**Trap 2 — The one-line fix is in the wrong function and silently changes the
dollar figure.** It is very tempting to write `if not rows: return None` inside
`factory/activities/usage_activities.py:497` — `_read_final_usage`. That is
wrong. `None` routes the attempt into the fallback branch at
`factory/activities/usage_activities.py:554` — `_record_for`, which writes
`snapshot.spend_usd` — the last heartbeat — instead of the key's counter, and
writes `None` when there was never a snapshot. The flag would come out right and
the spend would silently become a different number on 397 rows' worth of future
attempts, doing US2's job by accident and doing it differently from how US2 does
it. FR-002 puts the decision at the assignment site, and US1-S4 is the scenario
that catches this: it asserts the flag and the spend in one test, over a lease
whose snapshot disagrees with the counter.

**Trap 3 — The spend half reverses a contract this tree wrote on purpose, and
must not be dispatched before the decision exists.**
`factory/usage/litellm_client.py:268` — `get_spend` documents `/key/info`'s
`0.0` as a real measurement in as many words. US2 says that once nothing is
attributed to the key, a `0.0` counter is equally consistent with "the requests
went somewhere else" — which is not a theory, it is what the 167
non-zero-counter rows with empty row sets demonstrate. That is a decision, and
it belongs in `docs/decisions.md` before it belongs in code. **If no such entry
exists when you read this, US2 was dispatched in error: say so in the attempt
rather than inventing a `D-` number.** At `602a92c` the file ended at `D-052`
and carried no such entry, which is why the spec's frontmatter records the hold
as unsatisfied. The second wrong move is to "fix" spend by summing the rows
instead of reading the counter; that breaks
`tests/test_usage_activities.py:604` — `test_the_confirmed_spend_is_the_keys_own_total`,
which is a deliberate contract and stays green. FR-008, FR-009.

**Trap 4 — `SCHEMA_VERSION` cannot gate the repair, and bumping it does nothing
for an existing ledger.** `factory/usage/ledger.py:152` — `_bootstrap_schema`
stamps a version only when the `schema_version` table is empty, so the ledger on
this host still records whatever it was first stamped with and always will. A
repair gated on "recorded version < 3" therefore runs on every open forever, and
a repair gated on "recorded version >= 3" never runs at all. Neither is what the
implementer thinks they wrote. Write the repair as an unconditional `UPDATE`
with a `WHERE` clause that is its own fixpoint, and leave
`factory/usage/ledger.py:48`'s `SCHEMA_VERSION = 2` alone — the DDL has not
changed. FR-012, and US3-S4 is the scenario that proves it.

**Trap 5 — The repair is one `UPDATE`, not a table rebuild.**
`factory/usage/ledger.py:188` — `_widen_terminations` is the only precedent in
the file and it rebuilds the table — new table, rows copied, old dropped,
indexes recreated — because `ALTER TABLE` cannot widen a `CHECK`. None of that
applies to a value change. What a rebuild would put at risk here is not the row
identity — `factory/usage/ledger.py:196-198` says `id` is copied with the rest,
and it is, because the column list comes from `PRAGMA table_info(usage_records)`
at `factory/usage/ledger.py:220-228`. It is the shape, in two ways its own
docstring and its caller name. The docstring names the first: "a rebuild that
guessed the shape would be the one migration that could silently drop a column".
The caller names the second: `factory/usage/ledger.py:142` — `_bootstrap_schema`
runs `_migrate` on **every** `connect`, a brand-new ledger included, immediately
after applying the DDL — so whatever text a rebuild wrote becomes the DDL
`sqlite_master` records, which is exactly what
`tests/test_ledger_schema.py:189` — `test_a_new_ledger_matches_the_published_contract_ddl`
compares against the published contract. One `UPDATE` touches none of that.
FR-011.

**Trap 6 — 024 is the ancestor of this defect and its FR-006 forbade exactly
this repair.** `specs/024-ledger-token-honesty/spec.md:117` says "This feature
MUST NOT rewrite, migrate or backfill any row written before it lands", and
`specs/024-ledger-token-honesty/spec.md:112` says "`spend_usd` MUST be
unaffected". 024 landed on 2026-08-17 and is what made `aggregate_rows` return
`None` instead of a fabricated `0` — which is what created the visible shape of
this defect, a NULL-count row flagged confirmed. An implementer who reads 024
will conclude the repair is prohibited. It is not: 024 deferred it in writing
("a one-off operator migration over historical evidence ... FR-006 forbids it
here") and US3 is where it lands. Cite 024 in the story; do not treat it as a
standing prohibition, and do not treat it as the fix either.

**Trap 7 — 070-US4 is a decoy.** `git log --all --grep=final_usage_confirmed`
returns two commits and they are the same work: `da44b6e`, the squashed 070-US4
landing, and `8adde4b`, its pre-squash counterpart. What that work added is
`factory/activities/usage_activities.py:517` — `_is_subscription_lease` and the
branch at `factory/activities/usage_activities.py:543` — `_record_for`, which
writes `final_usage_confirmed=False` for an empty key. It fixed a **different**
empty-usage case and left this one. An implementer who greps the history will
find those commits, conclude the flag was already fixed, and confine the change
to the subscription branch — where it does nothing, because the defective rows
all have real keys.

**Trap 8 — Four other tests assert `final_usage_confirmed is True` and all four
must stay green untouched.** `tests/test_usage_activities.py:564` — `test_teardown_records_the_attempts_usage_from_proxy_data`
(its flag assertion at line 574),
`tests/test_usage_activities.py:787` — `test_a_failed_revocation_still_records_the_attempt`
(line 798), `tests/test_subscription_accounting.py:210` — `test_gateway_attempt_records_exactly_as_today`
(line 226) and `tests/test_final_sweep.py:718` — `test_a_runaway_attempt_is_treated_exactly_like_a_cheap_one`
(line 746). Each is cited at its `def` so that the next move of any of them is
caught by `spec validate` rather than by an operator's eye. Every one of them
runs against a proxy whose spend logs carry rows, so the correct change leaves
all four alone. Three more assertions read the same flag and are **not** part of
this diagnostic, because nothing an implementer or a node runs will execute
them: `tests/test_live_proxy.py:491` — `test_the_ledger_tokens_reconcile_with_the_proxys_spend_logs`,
`tests/test_live_proxy.py:549` — `test_the_attempt_lands_as_exactly_one_attributed_row`,
and `tests/test_live_judge.py:567` — `test_the_recorded_tokens_are_the_judges_own`.
Both modules carry `pytestmark = pytest.mark.live_proxy`
(`tests/test_live_proxy.py:73`, `tests/test_live_judge.py:91`) and skip without
proxy credentials, no CI job and no node gate runs those tiers, and
`tests/test_live_judge.py` is already failing on this spec's own trigger,
`usage/the-ledger-attributes-almost-no-requests-to-the-judge`. Two of the three
run against real spend rows and assert `prompt_tokens > 0` beside the flag —
`tests/test_live_proxy.py:497` — `test_the_ledger_tokens_reconcile_with_the_proxys_spend_logs`
and `tests/test_live_judge.py:572` — `test_the_recorded_tokens_are_the_judges_own`.
The third does not, and reading it as if it did is the mistake this paragraph
used to make: `tests/test_live_proxy.py:550` — `test_the_attempt_lands_as_exactly_one_attributed_row`
asserts `stored["prompt_tokens"] == attempt.record.prompt_tokens`, an equality
that holds even when both sides are `NULL`, so it says nothing about whether the
row carried counts. Its consistency after US1 follows from its sibling at
`tests/test_live_proxy.py:497`, which asserts a positive count on the same live
attempt. All three stay consistent with the rule US1 writes — but leave them
unedited, and never read a red there as a verdict on this change. FR-003. If any
of them goes red, the predicate is too broad — most likely it read
`prompt_tokens is not None` alone rather than the three-metric rule, or it moved
the decision into `_read_final_usage` (trap 2). This rule is about those four
tests and not about `tests/test_usage_activities.py:643`, which trap 11 covers.
FR-003.

**Trap 9 — `raw_insert`'s defaults are exactly the defective shape, and the
repair will look broken if the test does not reconnect.**
`tests/test_ledger_schema.py:106` — `raw_insert` defaults to
`"final_usage_confirmed": 1` with `prompt_tokens`, `completion_tokens` and
`request_count` all `None` — the row US3 repairs. But `_migrate` runs inside
`connect`, which the `tests/test_ledger_schema.py:167` — `ledger` fixture
already called before the test body inserts anything. A test that inserts
through that fixture and asserts on the same connection reads `1`, and the wrong
move is to conclude the repair does not work and go widen it. Close the
connection and `connect` again — that reopening is the story's Independent Test
and the thing US3-S1 actually asserts.

**Trap 10 — The repair rewrites the flag and nothing else, and that is what
keeps it dispatchable.** It is tempting to null the 230 fabricated `spend_usd =
0.0` values in the same `UPDATE`, since US3 is standing right next to them.
Doing so imports the operator decision US2 waits on into a story that otherwise
has no dependency on it, and the two would have to land together. FR-011 and
US3-S3 forbid it: a legacy row keeps the `spend_usd` it was written with, zero
included.

**Trap 11 — The spend half turns red an assertion the flag half just amended,
and that is the one red it is allowed to cause.**
`tests/test_usage_activities.py:643` — `test_an_attempt_that_never_called_the_proxy_records_unmeasured`
asserts `record.spend_usd == 0.0` four lines below the flag assertion US1
inverts, inside the same test trap 1 is about. That `0.0` is not a chosen
fixture value: `tests/conftest.py:142` — `add_spend_row` is the only thing that
raises the fake key's counter, so an empty spend-log row set means a `/key/info`
counter of exactly `0.0` unless the test forces one with
`tests/conftest.py:192` — `set_spend`. US1 leaves that line green, because US1
changes the flag and not the figure. US2's FR-006 turns it red the moment it
lands. The wrong moves, in the order they will occur to the implementer: read
the red as trap 8's "predicate too broad" and narrow the branch until `0.0`
survives; revert; or add a second test asserting `None` and leave the one
asserting `0.0` in place, so the suite states both rules at once. FR-014
requires that single assertion amended in place, and US2-S1 is written as that
amendment rather than as a new test. The same mechanism is why US1-S4 pins its
counter non-zero through `set_spend`: an unpinned counter is `0.0`, so an
unpinned assertion there would be one more line US2 had to come back and
rewrite.

**Trap 12 — `aggregate` does not exist at the line the predicate goes on.**
`factory/activities/usage_activities.py:566` — `_record_for` binds `aggregate`
inside the `else` branch only. A predicate written at
`factory/activities/usage_activities.py:585` — `_record_for` as
`aggregate.request_count is not None` raises `UnboundLocalError` on the
subscription and read-failure paths, and the implementer learns that from a
stack trace rather than from this file. Read the three counts out of the `usage`
dict all three branches have already built — `usage["prompt_tokens"]`,
`usage["completion_tokens"]`, `usage["request_count"]` — which are `None` on
both of the branches that are already honest, so FR-004 falls out of the same
expression instead of needing a special case. FR-002.

**And the mirror image, which is why FR-002 asks for a helper rather than an
expression.** US2's branch goes twelve lines earlier, at
`factory/activities/usage_activities.py:573-575` — `_record_for`, *inside* the
dict literal that is still being built: `usage["prompt_tokens"]` does not exist
there, and the only names in scope are `aggregate` — bound at
`factory/activities/usage_activities.py:566` — `_record_for` — and `confirmed`.
So "reuse US1's predicate" is not an instruction an implementer can carry out
unless US1 left something callable behind, and the two ways of improvising it
are both bad: restate the expression over `aggregate` and the flag and the spend
can drift apart, or hoist a local above the dict and the edit lands on
`factory/activities/usage_activities.py:585` — `_record_for`, the one line trap
8's four control tests watch. FR-002 therefore requires US1 to land a
module-level helper over the three values, and FR-006 requires US2 to call that
same helper with `aggregate.prompt_tokens`, `aggregate.completion_tokens` and
`aggregate.request_count`. Calling it against `aggregate` there is correct and
is not what the paragraph above forbids — inside the `else` branch `aggregate`
is bound; it is at line 585, outside it, that it is not.

**Trap 13 — The token-less row US1-S3 needs cannot be built with the helper
every other test uses, and the substitute that suggests itself is green and
wrong.** `tests/conftest.py:142` — `add_spend_row` declares `prompt_tokens: int`
and `completion_tokens: int` as required keyword arguments with no defaults, and
sums them into `total_tokens` at `tests/conftest.py:181` — `add_spend_row`, so
`prompt_tokens=None` is a `TypeError` rather than a token-less row. Two wrong
moves follow, in the order they occur to an implementer. The first is to widen
`add_spend_row`'s signature — a fixture shared by every usage test, in a file no
story here declares, which drags US1 into a file its Sizing does not name. The
second is worse because it passes: substituting `0`. A reported `0` **is** a
measurement — `factory/usage/aggregate.py:90` — `_accumulate` folds it in, so
the aggregate's `prompt_tokens` comes out `0` rather than `None` — and the
scenario then stops distinguishing the three-metric rule from a narrow
`prompt_tokens is not None` predicate, which is the one thing US1-S3 exists to
refuse and a difference the judge cannot see in the diff. The route that works
is the fake's own store: `tests/conftest.py:114` holds `spend_rows` as a plain
dict of lists, `tests/conftest.py:409` — `_spend_logs` serves whatever is in it,
and `factory/usage/litellm_client.py:284` — `fetch_spend_log_rows` passes rows
through untouched ("rows are passed through untouched, cache metadata and all").
Append raw dicts carrying `spend`, `model` and `request_id` and no token keys,
and `factory/usage/aggregate.py:39` — `aggregate_rows` counts each row while
leaving both token metrics `None` — which is exactly the shape the scenario
names. FR-001, US1-S3, T003.

**Trap 14 — The comment the spend half makes false lives in two files, and the
one test that reads them both is blind to comments.**
`factory/usage/ledger.py:75` annotates `spend_usd` as "NULL only if no snapshot
ever taken", and `specs/001-usage-tracking/contracts/ledger-schema.sql:27`
carries the same line because `factory/usage/ledger.py:55` declares the DDL
verbatim from that contract. US2 falsifies both. Two wrong moves, in the order
they occur. The first is to fix the DDL string and leave the contract file, on
the reasoning that the suite is green either way — it is green either way, and
that is the trap: `tests/test_ledger_schema.py:135` — `_canonical` deletes every
`--` comment before `tests/test_ledger_schema.py:189` — `test_a_new_ledger_matches_the_published_contract_ddl`
compares, so the two files can drift apart forever without a red. The second is
to "fix" it by changing the column instead of the comment — a type, a
constraint, a `NOT NULL` — which is a schema change this spec forbids and which
that same test *would* catch. FR-015 requires one edit to each file, same new
text, nothing else in the DDL moved.

## Sizing

US1 touches `factory/activities/usage_activities.py` — one predicate, used at
one assignment site — `factory/usage/models.py`, where one docstring paragraph
is rewritten (FR-013), and `tests/test_usage_activities.py`, where one existing
assertion is inverted and three tests are added. Under thirty production lines.
US1-S3 also *reads* `tests/conftest.py` — it appends a token-less row straight
to the fake's `spend_rows` store, because `add_spend_row` cannot build one (trap
13) — but writes nothing there, so that file stays out of every story's diff.

US2 touches `factory/activities/usage_activities.py` — one branch on the same
`usage` dict `_record_for` already builds — and
`tests/test_usage_activities.py`, where one existing assertion is amended
(`tests/test_usage_activities.py:643` as this spec was written, FR-014, located
by its enclosing test once US1's new tests have shifted it) and two tests are
added. It also corrects one comment line in each of `factory/usage/ledger.py`
and `specs/001-usage-tracking/contracts/ledger-schema.sql` (FR-015), and cites
`docs/decisions.md`, which it reads and does not write: the entry is an operator
act that precedes dispatch (trap 3). Under twenty production lines.

US3 touches `factory/usage/ledger.py` — one function called from `_migrate` —
and `tests/test_ledger_schema.py`. Under twenty production lines.

US1 and US2 share `factory/activities/usage_activities.py` and
`tests/test_usage_activities.py` — and inside that test module they share one
test, four lines apart, and inside the production module they share the
predicate helper FR-002 asks US1 to land and FR-006 asks US2 to call — which is
why US2 declares `depends_on_merged` on US1 rather than racing it.
`factory/usage/models.py` is US1's alone. US3 shares nothing with US1, and
shares exactly one file with US2: `factory/usage/ledger.py`, where US2 rewrites
the comment at `factory/usage/ledger.py:75` inside the `_SCHEMA_DDL` literal and
US3 adds a function beside `factory/usage/ledger.py:188` — `_widen_terminations`
and one call line in `factory/usage/ledger.py:237` — `_migrate`, more than a
hundred lines away. That pair is declared `concurrent_with` in the Work Graph
rather than ordered, because an edge would make the repair wait on the story
held for an operator decision. `tests/test_ledger_schema.py` and
`specs/001-usage-tracking/contracts/ledger-schema.sql` are named by no other
story, so US2 and US3 may still run concurrently once US1 has merged.

All three are far inside the 64 KiB deterministic diff bound (D-050). The pasted
evidence each verification task asks for is a short `sqlite3` transcript and a
short test report, not a full run.

## Verification the operator will run, independent of the gate

Per constitution VIII and D-037 the judge sees the diff and the criteria only,
so runtime evidence is committed as pasted output.

**Before any of it, the flip check.** US2 reverses a written contract and must
not reach an agent before the decision that authorises it exists. `grep -n '^##
D-0' docs/decisions.md | tail -1` answers in one line: at `602a92c` it prints
`D-052` and no entry in the file authorises the reversal, so this spec is not
flippable as it stands. Either that entry is written first, or US2 moves to its
own spec under a new number and the spend half of the declared finding key moves
with it. This is the check the frontmatter's hold paragraph names, in a form
that can be run.

1. Before landing anything, take the baseline this spec is measured against:
   `sqlite3 -readonly .factory/ledger.db "select count(*) from usage_records;
   select count(*) from usage_records where final_usage_confirmed=1 and
   prompt_tokens is null and completion_tokens is null and request_count is
   null;"`. At 602a92c that answers `795` and `397`. Keep the transcript.
2. After US1 lands, run one real attempt against a proxy whose spend logs stay
   empty for the attempt's key — a judge node is the reliable way, since that is
   where the empty row sets come from — and read its ledger row. The flag must
   be `0` and the counts must be `NULL`. A row that still reads `1` means the
   predicate never reached the writer.
3. After US1 lands, confirm the flag did **not** move for a measured attempt:
   read an implementer node's row from the same epic and check it still carries
   counts with the flag at `1`.
4. After US2 lands, repeat step 2 and read `spend_usd`. It must be `NULL` where
   the key counter was `0.0`, and it must still carry the counter where it was
   not — which the same query answers, since both shapes occur in one epic.
5. After US3 lands, open the host ledger once with a current ergane — any
   activity that calls `connect` will do — and re-run step 1's second query. It
   must answer `0`, and `select count(*) from usage_records;` must still answer
   the same total as step 1. Then run `ergane usage --by persona` and confirm
   `unconfirmed_rows` for the judge is no longer `0` while its token totals are
   `NULL`.

Step 5 is the falsifiable test of the whole spec: it is the contradiction the
hand-over reported, read back out of the operator's own ledger.
