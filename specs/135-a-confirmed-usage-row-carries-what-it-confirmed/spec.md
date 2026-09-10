---
state: draft
# RELEASE COORDINATION 2026-09-10: the user explicitly included audit packets
# in0.6. This usage-correctness trio remains coordinated release work; its
# historical US2 spend-contract decision hold is NOT implicitly cleared.
fixes:
  - feedback/pr-11-a-confirmed-usage-record-carries-nothing
# DRAFTED 2026-09-04 by the refinement workflow (refinement-2026-09-04) from
# docs/triage-2026-09-03-ergane-web-round3.md § "a-confirmed-usage-row-carries-what-it-confirmed"
# (lines 98-114), against ergane-buildout at 602a92c. Every `file:line` in
# spec.md and plan.md was read from that commit and verified to resolve to the
# symbol named, not recalled.
#
# WHERE THIS CAME FROM. PR-11 of the `ergane-web` consolidated hand-over
# (`ergane-findings-ergane-web-2026-09-03.md`), verified against the tree by the
# 2026-09-03 fan-out and then survived a refutation pass. The ledger row's own
# summary names three halves — set the flag only when the row carries final
# counts, write NULL spend when no price was reported, repair the rows already
# written — and this spec is one story per half, which is why the key is
# declared whole rather than half.
#
# WHAT IT COST, MEASURED. The hand-over counted 68 defeating rows, all of them
# judge rows. Re-measured on this host's `.factory/ledger.db` on 2026-09-04:
# 795 rows, of which 397 read `final_usage_confirmed = 1` with no prompt,
# completion or request count at all — every one of them also carrying a NULL
# request count, so the two candidate readings of "carries counts" partition the
# real corpus identically. 230 of those 397 also name a spend of `0.0`; the
# other 167 name a real non-zero figure, which is why the spend half of this
# spec nulls only the zero and keeps the measurement. `rollup` exports the
# flag's complement as `unconfirmed_rows`, so 397 rows currently tell a consumer
# that a scope was fully measured and then report nothing.
#
# THE SPEND STORY IS HELD UNTIL A DECISION EXISTS. US2 reverses a contract this
# tree wrote down on purpose: `get_spend` documents `/key/info`'s `0.0` as a
# real measurement. Reversing it is a decision, not an implementation detail, so
# US2 MUST NOT be dispatched — and therefore this spec MUST NOT be flipped
# `ready` — before an operator has written the `docs/decisions.md` entry that
# records the reversal (D-052 is the last entry at 602a92c, so D-053 or the next
# free number). US1 and US3 declare no edge to US2 and would run unaffected if
# the operator chooses to move US2 to its own spec under a new number; landed
# story numbers are immutable, so a split takes a new number and never a
# renumbering.
#
# NOT IN SCOPE. Judge attribution — the reason the judge's rows arrive empty —
# is the separate open finding `usage/the-ledger-attributes-almost-no-requests-to-the-judge`
# and is the trigger, not the defect; nothing here tries to make the proxy
# report the missing rows. `rollup`'s strict-totals rule was investigated during
# the hand-over, found correct, and is untouched. The subscription-lease branch
# is already honest and stays byte-identical. The repair rewrites the flag only:
# no stored `spend_usd`, no token column, no `id`, and no schema change.
#
# WHAT THE ENTRY SAID AND WHAT THIS SPEC DOES INSTEAD, ONCE. The backlog entry
# says "`spend_usd` is written NULL when no priced row was reported". Taken
# literally that also nulls the 167 rows whose key counter carried a real
# non-zero figure while the spend logs were empty, discarding a measurement the
# proxy did take. The ledger row's own notes ask only that a reported zero stay
# expressible as `0`, so US2 nulls the zero-with-no-rows case and keeps the
# non-zero counter. That narrowing is deliberate and is the one place this spec
# departs from the entry's wording.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), anchors re-read at 602a92c: the
# collision between US2 and the test US1 amends is now declared instead of
# discovered (FR-014, US2-S1, trap 11); US1-S4 pins the key counter non-zero so
# US2 cannot invert the assertion US1 wrote; the `UsageRecord` docstring US1
# makes false is in scope (FR-013, US1-S6); the strict-totals citation moved off
# `factory/usage/ledger.py:318`, which is the `unconfirmed_rows` line, onto the
# block that actually holds the rule; `_bootstrap_schema` is re-cited in the
# symbol form; trap 7's history claim is corrected to the two commits `git log`
# really returns; the US1 implementation task no longer names a variable that is
# out of scope at the line it edits; and US2-S4 is strengthened so an invented
# `D-` number cannot satisfy it. No anchor had moved in the tree, no story was
# split, and the `fixes:` list is unchanged at one key.
#
# THE HOLD ABOVE IS UNSATISFIED, CHECKED 2026-09-04 AT 602a92c. `docs/decisions.md`
# ends at `## D-052 · The install demonstration stays free ...` and carries no
# entry naming `get_spend`, `final_usage_confirmed` or the `0.0` reversal, so
# that paragraph is a live block rather than a formality: as it stands this spec
# must not be flipped, because a flip compiles and dispatches all three stories
# and US2's own last task then orders the agent to stop and report — an attempt
# spent by construction. The one-line pre-flip check is
# `grep -n '^## D-0' docs/decisions.md | tail -1`. Both routes out are the
# operator's, not an implementer's: (a) write the entry, then flip, and amend the
# hold paragraph to name the entry that satisfied it; or (b) move US2 to its own
# spec under a new number and flip what remains — in which case the spend half of
# `feedback/pr-11-a-confirmed-usage-record-carries-nothing` moves with it, that
# spec declares the key, and this one's `fixes:` must be re-stated as the flag
# and repair halves only. As written the key is whole only if all three stories
# land: landing US1 and US3 alone while leaving the declaration untouched is the
# 100/092/118 half-fix shape, where triage closes a key on a declaration the code
# did not earn.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04) after an adversarial review, anchors
# re-read at 602a92c. The gate's one refusal is fixed: plan.md's bare `:643` in
# § Sizing had no path to inherit and is now the full
# `tests/test_usage_activities.py:643`. US1-S3's token-less row now names the only
# route that can build it, because `tests/conftest.py:142` — `add_spend_row` takes
# both token counts as required `int`s and the `0` an implementer would substitute
# is itself a measurement, which would leave the scenario green and no longer
# discriminating (plan trap 13, T003). The four "stay green" assertions in FR-003,
# trap 8 and T002 are re-cited in the machine-checked `path.py:NN` — `symbol` form
# so their next move is caught by validate instead of by hand. FR-014 and US2-S1
# now locate the assertion US2 amends by its enclosing test rather than by a line
# US1's own new tests will shift. Trap 6 — spec 024's FR-006, which reads as a
# standing prohibition on US3 — now reaches an implementer, through T021 and the
# tasks preamble. The `get_spend` paste is cited as the `:268-275` it actually is.
# The review's second blocker, that this spec is not flippable, is the hold five
# paragraphs above: it stands unchanged and unsatisfied, and both routes out of it
# — writing the `docs/decisions.md` entry, or minting the split spec — are
# operator acts outside a refinement pass's writable set. No anchor moved, no
# story was split, no FR changed hands, and `fixes:` is unchanged at one key.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04) after a second adversarial review,
# anchors re-read at 602a92c: four minor defects fixed in place, and the blocking
# one re-verified and left standing because its remedy is not a file this pass may
# write. FR-003 and trap 8 claimed *four* tests assert `final_usage_confirmed is
# True`; three more do, on the live tiers — `tests/test_live_proxy.py:491`,
# `tests/test_live_proxy.py:549`, `tests/test_live_judge.py:567` — so both now name
# them, say they must be left unedited, and say why they are not evidence (no CI
# job and no node gate runs those tiers, and the judge one is already red on this
# spec's own trigger finding). US2 falsified the `spend_usd` column comment in the
# DDL and in its published contract while no requirement corrected it — the defect
# class this spec exists to fix — so FR-015, US2-S5, T015a and trap 14 now correct
# both sites, `### What this spec is not` separates the structure (untouched) from
# the comment (moves), and the Work Graph declares `concurrent_with: [US3]` for the
# one file US2 and US3 now share. Trap 5's claim that a rebuild "churns `id`s" was
# false — `factory/usage/ledger.py:196-198` says `id` is copied with the rest — and
# is replaced by the risk a rebuild really carries. T003 is labelled the control it
# already was, and T001 is told not to assert `spend_usd`, the line US2 nulls. The
# hold recorded above is unchanged and still unsatisfied, re-checked at 602a92c:
# `docs/decisions.md` ends at `## D-052` and names neither `get_spend` nor
# `final_usage_confirmed`, and neither route out of it — writing that entry, or
# minting the spec US2 would move to — is inside a refinement pass's writable set.
# No anchor moved, no story was split, no FR changed hands, and `fixes:` is
# unchanged at one key.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04) after a third adversarial review,
# anchors re-read at 602a92c and the hold re-checked against the working tree on
# 2026-09-05. Five minor defects fixed in place; the blocking one re-verified and
# left standing, because its remedy is not a file this pass may write. FR-002 now
# requires the flag predicate to be a module-level helper taking the three counts
# as arguments, and FR-006 requires US2 to call that same helper with
# `aggregate.prompt_tokens`, `aggregate.completion_tokens` and
# `aggregate.request_count`: the old instruction "reuse User Story 1's predicate"
# was not executable at `factory/activities/usage_activities.py:573-575`, where
# the `usage` dict is still being built and only `aggregate` is in scope, so it
# would have been satisfied by inventing a shape or by editing the one line trap
# 8's control tests watch (trap 12, T014). FR-003 and trap 8 claimed all three
# live-tier flag assertions sit beside a `prompt_tokens > 0`;
# `tests/test_live_proxy.py:549` —
# `test_the_attempt_lands_as_exactly_one_attributed_row` instead compares the
# stored row against the record, an equality that holds with both sides `NULL`, so
# both now say so and route its consistency through the sibling assertion at
# `tests/test_live_proxy.py:497`. The five assertion-line anchors that named their
# enclosing test only in prose — `tests/test_usage_activities.py:639` and `:643`,
# the two live-proxy lines and the live-judge line — are re-cited in the
# machine-checked `path.py:NN` — `symbol` form, so their next move is a validate
# refusal rather than a reader's catch. That rewrite exposed a second, quieter
# thing worth recording, because two earlier passes had already written citations
# in that form and got nothing for it: `_check_symbol_anchors` runs its recogniser
# over **one line at a time** (`factory/cli/nouns/spec.py`, the `finditer` inside
# the per-line loop at 943), so a citation whose path sits at the end of one line
# and whose symbol opens the next is invisible to the tier — it reads as an
# unnamed anchor and falls through to the resolution check, which only catches a
# blank or past-EOF line. Every split citation in the trio is therefore rejoined
# onto a single line. Measured before and after on the three documents: 27 of the
# 52 single-line `.py` anchors were machine-checked before this pass, 43 of 52
# after; the nine still unchecked are module constants, DDL text inside a string
# literal and two `pytestmark` lines, none of which the AST tier can resolve to a
# symbol. Controlled, not assumed: moving `tests/test_live_proxy.py:549`'s number
# to 400 makes validate refuse with "cites
# `test_the_attempt_lands_as_exactly_one_attributed_row` which actually occupies
# lines 535-551", and the same mutation before the rejoin was silently green.
# In tasks.md, the User Story 3 implementation task's stated reason for refusing a table rebuild is corrected to
# trap 5's — a rebuild rewrites the DDL `sqlite_master` records that
# `test_a_new_ledger_matches_the_published_contract_ddl` compares, not the row
# `id`s, which `factory/usage/ledger.py:196-198` says are copied with the rest —
# and T011 no longer locates the flag assertion by a number User Story 1's own new
# tests will shift. The insertion id `T015a` that the note above names is
# renumbered `T016` and the old T016-T026 shift up by one, so every id in the file
# is three digits again; the task the note above calls T021 is now T022, and the
# file runs T001-T027. The hold recorded four paragraphs above is unchanged
# and still unsatisfied, re-checked at 602a92c: `grep -n '^## D-0' docs/decisions.md
# | tail -1` prints `## D-052` and no line in that file names `get_spend` or
# `final_usage_confirmed`. Neither route out of it — writing that entry, or minting
# the spec User Story 2 would move to — is a file a refinement pass may write, so
# it stays an operator act and this spec stays `draft`. No anchor moved, no story
# was split, no FR changed hands, and `fixes:` is unchanged at one key.
---

# Feature Specification: a confirmed usage row carries what it confirmed

**Created**: 2026-09-04

**Depends on**: nothing.

## 0.6 audit-packet coordination (2026-09-10)

The approved packet feature is specified in167. This trio corrects the legacy
ledger's claims; it does not by itself provide complete audit evidence. Its
predicate accepts a measured request count with absent token counts, so neither
today's flag nor the corrected flag proves complete token coverage.167 records
per-dimension completeness and immutable execution identity separately.

The original three stories and finding scope remain unchanged. The inspected
decision log at buildout a654fca ends at D-055 and still has no decision
authorizing US2's zero-counter reversal; this release inclusion does not invent
one. Resolve that existing hold before readying this whole trio, or explicitly
split the held spend slice under a new spec number without closing the whole
finding.167 does not import the held reversal as a dependency and must remain
honest when reading existing rows. No historical dollars or live store are
rewritten by this documentation update. Full source-anchor/readiness refinement
remains a pre-dispatch step for this older trio.

## The gap, stated precisely

`final_usage_confirmed` is set from the wrong question. It answers "did both
proxy reads return?" when every consumer, and every comment in this tree, reads
it as "does this row carry final counts?".

The chain is four short steps:

1. `factory/activities/usage_activities.py:594` — `_record_for` writes
   `final_usage_confirmed=confirmed is not None`. The only thing that value can
   express is whether a reading happened.
2. `factory/activities/usage_activities.py:506` — `_read_final_usage` returns
   `None` for exactly two reasons — `client is None`, or a raised `LiteLLMError`
   — at `factory/activities/usage_activities.py:516-523`. Any successful pair of
   reads returns a `_ConfirmedUsage`, **including one whose row set is empty**.
3. An empty row set is not a measurement, and this tree already says so:
   `factory/usage/aggregate.py:39` — `aggregate_rows` documents at
   `factory/usage/aggregate.py:42-45` that "An empty row set is an unmeasured
   aggregate ... A zero is only a zero when a row said so", and returns `None`
   for prompt, completion and request count.
4. So the two halves of the row disagree by construction: the counts say
   "unmeasured" and the flag says "confirmed". `rollup` exports the flag's
   complement at `factory/usage/ledger.py:300` and again at
   `factory/usage/ledger.py:318` as `COALESCE(SUM(1 - final_usage_confirmed),
   0)` — the single signal a consumer has for "part of this scope was never
   measured" — and it reports zero for a scope that measured nothing.

**The contradiction is already written down, three times, in the three files
that would have to change.** `factory/usage/ledger.py:290-291` calls
`unconfirmed_rows` "the flag for rows whose token detail is missing", a
condition the writer never checks. The teardown module's own docstring, at
`factory/activities/usage_activities.py:22-26`, states the rule this spec is
asking for and then does the opposite four hundred lines later: "Mixing a
confirmed spend with absent token detail would publish a row that looks measured
and is not." And `factory/usage/models.py:139` — `UsageRecord`, the file a
reader opens to learn what the column means, describes a world with only two
shapes — "On the confirmed path every field is populated from proxy data. On the
fallback path `final_usage_confirmed` is False" — which the row this spec is
about has never fitted.

The dollar figure makes it worse rather than better. When no row was reported,
`factory/activities/usage_activities.py:582-584` — `_record_for` still writes
`/key/info`'s counter, so the row names a spend of `0.0` — the one number in it
that looks like a measurement and is not.

And nothing repairs what has already been written.
`factory/usage/ledger.py:242` — `upsert_record` is the only writer,
`factory/usage/ledger.py:237` — `_migrate` calls only `_widen_terminations`, and
`factory/usage/ledger.py:48` carries `SCHEMA_VERSION = 2` with no data-repair
step behind it.

## The rule this spec is asking for

**A row is confirmed when the aggregate stored in it is a measurement, and a
dollar figure nothing was attributed to is not a measurement either.**

"The aggregate is a measurement" has exactly one meaning here, taken verbatim
from `aggregate_rows`'s own docstring: at least one of `prompt_tokens`,
`completion_tokens` and `request_count` is not `None`. An empty row set makes
all three `None` together; any drained row makes `request_count` a number.

The cases, complete:

| both reads returned | aggregate is a measurement | `/key/info` counter | `final_usage_confirmed` | `spend_usd` |
|---|---|---|---|---|
| yes | yes | any | **true** — unchanged | the counter — unchanged |
| yes | **no** | non-zero | **false** — today's defect | the counter — kept, it is a measurement |
| yes | **no** | `0.0` | **false** — today's defect | **NULL** — a zero nothing was attributed to |
| **no** (read failed) | — | — | false — unchanged | last snapshot — unchanged |
| subscription lease | — | — | false — unchanged | NULL — unchanged |

The last two rows are the paths 070-US4 and the fallback already made honest.
They are in the table because leaving them out is how a story widens.

### What this spec is not

It is not a change to why the judge's spend rows are missing. That is
`usage/the-ledger-attributes-almost-no-requests-to-the-judge`, still open, and
it is the trigger for this defect rather than the defect. This spec makes the
row honest about not knowing; it does not restore the knowledge.

It is not a change to `rollup`. The strict-totals rule — the three `CASE WHEN
COUNT(x) < COUNT(*) THEN NULL` expressions inside `_TOTALS_METRICS` at
`factory/usage/ledger.py:310-319`, on the prompt, completion and request lines
of that block — was reported as a defect during the hand-over and withdrawn the
same day: a scope containing an unmeasured row reports `NULL` rather than a
partial sum that looks complete, which is correct. The `unconfirmed_rows` entry
cited above at `factory/usage/ledger.py:318` is the last line of that same block
and is not part of that rule. This spec changes what those expressions are fed;
it does not change their SQL.

It is not a change to the published schema's structure. The column stays
`INTEGER NOT NULL CHECK (final_usage_confirmed IN (0, 1))`, no column is added,
dropped or retyped, and the repair is an `UPDATE` over data rather than a
rebuild of the table. One comment inside that DDL does move, and deliberately:
US2 makes it false. `factory/usage/ledger.py:75` and its published source
`specs/001-usage-tracking/contracts/ledger-schema.sql:27` both annotate
`spend_usd` as "NULL only if no snapshot ever taken", and after US2 a row torn
down with a snapshot in hand can carry `NULL`. FR-015 corrects both sites in the
diff that falsifies them. Nothing in the suite would catch it —
`tests/test_ledger_schema.py:135` — `_canonical` strips `--` comments before the
two schemas are compared — which is why it is a requirement here rather than a
courtesy left to the implementer.

It is not a spend repair. The rows already written keep the `spend_usd` they
carry, including the fabricated zeros; only the flag is repaired. That is what
keeps the repair free of the decision US2 waits on.

## User Scenarios & Testing

### User Story 1 - The flag says whether the row carries counts (Priority: P1)

As an operator reading `unconfirmed_rows`, a scope that measured nothing tells
me so instead of telling me it is complete.

**Why this priority**: P1 and it depends on nothing. It is the whole of the
consumer-visible defect: 397 of this host's 795 rows assert a measurement they
do not carry. It is also the rule the other two stories are written against —
US2's spend branch and US3's repair predicate are both "the aggregate is not a
measurement", so neither has a definition until this lands.

**Independent Test**: Tear an attempt down against a proxy that answers both
reads and reports no spend-log rows, and read the stored row's flag and counts.

**Acceptance Scenarios**:

1. **Given** an attempt whose proxy answers `/key/info` and returns an empty
   spend-log row set, **When** teardown writes the row, **Then** a committed
   test asserts `final_usage_confirmed` is `False` while `prompt_tokens`,
   `completion_tokens` and `request_count` are all `None` — the row that today
   asserts the opposite.
2. **Given** an attempt whose spend logs carry rows with token counts, **When**
   teardown writes the row, **Then** `final_usage_confirmed` is `True` and every
   count and the spend figure are unchanged from today. **The control**: this
   passes before the change and must still pass after it, which is what bounds
   the story to the empty-aggregate case.
3. **Given** an attempt whose spend logs carry three rows, none of which reports
   a prompt or completion token column at all — the key absent from the row
   rather than present with a `0`, which is a measurement and which no helper in
   this tree can build anyway (plan trap 13) — **When** teardown writes the row,
   **Then** `final_usage_confirmed` is `True` and `request_count` is `3`,
   because a drained row is a measurement even when its token columns are absent
   — the boundary the rule has to decide out loud rather than by accident.
4. **Given** a lease carrying a last heartbeat snapshot whose spend differs from
   the key's own counter — the counter forced to a non-zero `0.42` through
   `tests/conftest.py:192` — `set_spend`, against the `0.0417` snapshot at
   `tests/test_usage_activities.py:93` — and a proxy that answers both reads
   with no rows, **When** teardown writes the row, **Then** one committed test
   asserts both that `final_usage_confirmed` is `False` **and** that `spend_usd`
   is `0.42`, the key's counter rather than the snapshot's — so the diff cannot
   have reached the verdict by making `_read_final_usage` return `None`, which
   would have routed the attempt into the snapshot fallback and changed the
   dollar figure this story is not allowed to touch. The counter is pinned
   non-zero deliberately: US2 nulls a `0.0` counter on this exact path, and an
   unpinned counter is `0.0`, so an unpinned assertion here would be one US2 had
   to rewrite.
5. **Given** `tests/test_usage_activities.py:626-645` —
   `test_an_attempt_that_never_called_the_proxy_records_unmeasured`, whose
   docstring already says "there is no measurement" and whose flag assertion at
   `tests/test_usage_activities.py:639` — `test_an_attempt_that_never_called_the_proxy_records_unmeasured`
   says the row is confirmed, **When** the story lands, **Then** the diff amends
   that test in place — docstring's claim intact, assertion inverted — rather
   than deleting or skipping it, so the suite states the rule instead of pinning
   the defect. The spend assertion four lines below it, at
   `tests/test_usage_activities.py:643` — `test_an_attempt_that_never_called_the_proxy_records_unmeasured`,
   is left exactly as it is: US1 does not touch the dollar figure, and that line
   is US2's to amend (FR-014). Both are cited in the symbol form deliberately:
   the next move of either assertion is then refused by `spec validate` rather
   than found by hand.
6. **Given** `factory/usage/models.py:139` — `UsageRecord`, whose docstring
   tells every reader that "On the confirmed path every field is populated from
   proxy data" and that the flag is False only on the fallback path, **When**
   the story lands, **Then** the diff rewrites that paragraph to say what the
   flag now means — the row carries at least one count — and says it without
   re-asserting that a confirmed reading always populates every field, so US2's
   `NULL` spend cannot falsify the same paragraph a second time.

### User Story 2 - A dollar figure nothing was attributed to is not a measurement (Priority: P2)

As an operator, a row that measured nothing does not name a price.

**Why this priority**: P2, and it depends on US1 for the definition of "not a
measurement" and for the file it edits. It is held on an operator decision: it
reverses `get_spend`'s documented contract, and that reversal belongs in
`docs/decisions.md` before it belongs in code.

**Independent Test**: Tear down two attempts against an empty spend-log row set
— one whose key counter reads `0.0`, one whose counter reads a real figure — and
read the two stored `spend_usd` values.

**Acceptance Scenarios**:

1. **Given** an attempt whose spend-log row set is empty and whose `/key/info`
   counter reads `0.0` — the shape
   `tests/test_usage_activities.py:626` — `test_an_attempt_that_never_called_the_proxy_records_unmeasured`
   already sets up, since that fake's counter moves only when a spend row is
   added — **When** teardown writes the row, **Then** that test's `spend_usd`
   assertion is amended in place from `spend_usd == 0.0` to `spend_usd is None`,
   with the rest of the test — including the flag assertion US1 inverted — left
   as US1 left it, so the stored row no longer names a price for a scope nothing
   was attributed to and the suite carries one statement of the rule rather than
   two. The two line numbers this spec gives inside that test —
   `tests/test_usage_activities.py:639` — `test_an_attempt_that_never_called_the_proxy_records_unmeasured`
   for the flag and `tests/test_usage_activities.py:643` — `test_an_attempt_that_never_called_the_proxy_records_unmeasured`
   for the spend — were read before US1 landed, and US1 adds tests to the same
   module: find both by the enclosing test's name and by the assertion text,
   never by the number.
2. **Given** an attempt whose spend-log row set is empty and whose `/key/info`
   counter reads a non-zero figure, **When** teardown writes the row, **Then**
   `spend_usd` is that figure, because a non-zero counter is a measurement the
   proxy did take even when the per-request rows are missing. 167 of this host's
   397 defeating rows are this shape, and nulling them would discard data.
3. **Given** an attempt whose spend logs carry rows summing to a figure that
   differs from the key's counter, **When** teardown writes the row, **Then**
   `spend_usd` is still the key's counter and
   `tests/test_usage_activities.py:604` — `test_the_confirmed_spend_is_the_keys_own_total`
   is untouched by the diff. **The control**: `/key/info` remains the contract's
   final spend wherever a row was reported.
4. **Given** the branch that writes `None` instead of the counter, **When** the
   diff is read, **Then** the comment beside it names the `docs/decisions.md`
   entry that authorises the reversal by its `D-` identifier **and quotes that
   entry's heading line verbatim**, so a `D-` number no entry carries is legible
   as an invention in the diff itself rather than only to a reader who opens the
   decision log — the reversal of
   `factory/usage/litellm_client.py:268` — `get_spend`'s documented "a returned
   `0.0` is a measurement" is traceable to a decision rather than to an
   implementer's judgement.
5. **Given** the `spend_usd` annotation "NULL only if no snapshot ever taken",
   carried identically by `factory/usage/ledger.py:75` and by
   `specs/001-usage-tracking/contracts/ledger-schema.sql:27`, and falsified by
   this story — the row `test_an_attempt_that_never_called_the_proxy_records_unmeasured`
   writes is torn down with the `0.0417` snapshot that
   `tests/test_usage_activities.py:148` — `tear_down` passes by default (the
   default is at `tests/test_usage_activities.py:153` — `tear_down`), and after
   this story that row stores `NULL` — **When** the diff is read, **Then** it
   corrects that annotation at both sites to the same new text, so the contract
   an operator reads and the DDL the factory executes still say the same thing.
   No committed test can carry this one:
   `tests/test_ledger_schema.py:135` — `_canonical` strips `--` comments before
   `tests/test_ledger_schema.py:189` — `test_a_new_ledger_matches_the_published_contract_ddl`
   compares the two schemas, so a comment that lies is invisible to the gate and
   visible only in the diff.

### User Story 3 - The rows already written say what they measured (Priority: P3)

As an operator, opening the ledger with a current ergane repairs the rows that
were written under the old rule instead of leaving them to defeat every rollup
forever.

**Why this priority**: P3, and it depends on US1 for the predicate it applies.
397 of this host's 795 rows are already wrong and no future correctness reaches
them: `upsert_record` only ever touches the attempt it is called for. It is last
because the flag must be law before history is rewritten to match it.

**Independent Test**: Write a legacy row into a ledger with plain SQL, close the
connection, reopen the ledger with `connect`, and read the row back.

**Acceptance Scenarios**:

1. **Given** a ledger holding a row with `final_usage_confirmed = 1` and
   `prompt_tokens`, `completion_tokens` and `request_count` all `NULL`, **When**
   the ledger is reopened, **Then** a committed test asserts that row now reads
   `final_usage_confirmed = 0` and that every other column — `spend_usd`, `id`,
   `key_alias`, `termination`, both timestamps — is unchanged.
2. **Given** a ledger holding a row with `final_usage_confirmed = 1` and a
   `request_count` of `3`, **When** the ledger is reopened, **Then** that row is
   untouched, flag included. **The control**: the repair is scoped to rows that
   carry no counts, and a diff that flipped every row would fail it.
3. **Given** two legacy rows, one carrying `spend_usd = 0.0` and one carrying
   `spend_usd = 0.42`, **When** the ledger is reopened, **Then** both keep the
   `spend_usd` they were written with, because the repair rewrites the flag and
   nothing else — the assertion that keeps this story free of the decision US2
   waits on.
4. **Given** a ledger whose `schema_version` table records `1`, **When** it is
   reopened twice in succession, **Then** the legacy row is repaired on the
   first open and the second open changes no row, proving the repair is a
   fixpoint and is not gated on the recorded version — which
   `factory/usage/ledger.py:152` — `_bootstrap_schema` never updates for a
   ledger that already carries one.

## Functional Requirements

- **FR-001**: Teardown MUST write `final_usage_confirmed` true only when the
  aggregate it stores is a measurement — at least one of `prompt_tokens`,
  `completion_tokens` and `request_count` is not `None` — and false otherwise,
  including when both proxy reads succeeded and the spend-log row set was empty.
- **FR-002**: The decision MUST be taken at the single assignment site,
  `factory/activities/usage_activities.py:594` — `_record_for`, from the three
  count values that function has already assembled into the `usage` dict it is
  about to expand — `prompt_tokens`, `completion_tokens` and `request_count` —
  rather than from a name bound on only one of its three branches. Those three
  are `None` on the subscription and read-failure branches as well, so FR-004
  holds by construction. The predicate itself MUST be a module-level helper in
  `factory/activities/usage_activities.py` that takes those three values as its
  arguments and returns a `bool`, rather than an expression inlined at the
  assignment site. US2 has to apply the same rule from inside the `else` branch
  at `factory/activities/usage_activities.py:575` — `_record_for`, where the
  `usage` dict is still being built and cannot be read and only `aggregate` is
  in scope, so a helper is what makes "the flag and the spend cannot disagree" a
  fact about the code rather than an instruction an implementer has to honour
  (FR-006, trap 12). `factory/activities/usage_activities.py:506` — `_read_final_usage`
  MUST keep returning a `_ConfirmedUsage` for a successful pair of reads with an
  empty row set, so the key's own spend figure still reaches the row and the
  snapshot fallback is not entered.
- **FR-003**: A row whose aggregate carries counts MUST keep its flag, its
  counts and its spend figure exactly as they are today, and the four
  gate-visible tests that assert `final_usage_confirmed is True` —
  `tests/test_usage_activities.py:564` — `test_teardown_records_the_attempts_usage_from_proxy_data`
  (its flag assertion at line 574),
  `tests/test_usage_activities.py:787` — `test_a_failed_revocation_still_records_the_attempt`
  (line 798), `tests/test_subscription_accounting.py:210` — `test_gateway_attempt_records_exactly_as_today`
  (line 226) and `tests/test_final_sweep.py:718` — `test_a_runaway_attempt_is_treated_exactly_like_a_cheap_one`
  (line 746) — MUST stay green untouched. Three further assertions read the same
  flag on the live tiers — `tests/test_live_proxy.py:491` — `test_the_ledger_tokens_reconcile_with_the_proxys_spend_logs`,
  `tests/test_live_proxy.py:549` — `test_the_attempt_lands_as_exactly_one_attributed_row`
  and `tests/test_live_judge.py:567` — `test_the_recorded_tokens_are_the_judges_own`
  — and MUST be left unedited by this story's diff as well. They are not
  evidence and MUST NOT be treated as any: no CI job and no node gate runs those
  tiers, they skip without proxy credentials, and `tests/test_live_judge.py` is
  already failing on this spec's own trigger,
  `usage/the-ledger-attributes-almost-no-requests-to-the-judge`. Two of the
  three assert a positive count beside the flag on the same live attempt:
  `tests/test_live_proxy.py:497` — `test_the_ledger_tokens_reconcile_with_the_proxys_spend_logs`
  and `tests/test_live_judge.py:572` — `test_the_recorded_tokens_are_the_judges_own`
  both read `prompt_tokens > 0`. The third does not, and this spec must not
  claim it does: `tests/test_live_proxy.py:550` — `test_the_attempt_lands_as_exactly_one_attributed_row`
  compares the stored row against the record it was written from, an equality
  that would hold with both sides `NULL`, so its consistency after this story
  follows from its sibling assertion at `tests/test_live_proxy.py:497` on the
  same live attempt rather than from anything it asserts itself. All three stay
  consistent with the rule this story writes.
- **FR-004**: The subscription-lease branch at
  `factory/activities/usage_activities.py:552` — `_record_for` and the
  read-failure fallback at `factory/activities/usage_activities.py:563` — `_record_for`
  MUST keep writing `final_usage_confirmed` false with the spend figures they
  write today.
- **FR-005**: `tests/test_usage_activities.py:626-645` MUST be amended rather
  than deleted or skipped, keeping the claim its docstring already makes and
  correcting the assertion that contradicts it. Its `spend_usd` assertion at
  `tests/test_usage_activities.py:643` — `test_an_attempt_that_never_called_the_proxy_records_unmeasured`
  MUST be left unchanged by this story.
- **FR-006**: When the aggregate is not a measurement and the key's `/key/info`
  counter is `0.0`, `spend_usd` MUST be written `NULL`. "Not a measurement" MUST
  be decided by calling FR-002's helper with `aggregate.prompt_tokens`,
  `aggregate.completion_tokens` and `aggregate.request_count` — the three values
  bound at `factory/activities/usage_activities.py:575` — `_record_for`, which
  are the same three the flag reads — and MUST NOT be restated as a second
  expression, so the flag and the spend cannot come to disagree about one row.
- **FR-007**: When the aggregate is not a measurement and the key's counter is
  non-zero, `spend_usd` MUST be written as that counter, unchanged.
- **FR-008**: When the aggregate is a measurement, `spend_usd` MUST keep coming
  from the key's counter exactly as it does today, at
  `factory/activities/usage_activities.py:582-584` — `_record_for`.
- **FR-009**: The diff that performs the reversal MUST name, at the branch that
  performs it, the `docs/decisions.md` entry that authorises it, by `D-`
  identifier and by that entry's heading line quoted verbatim.
- **FR-010**: `factory/usage/ledger.py:237` — `_migrate` MUST repair every
  stored row that reads `final_usage_confirmed = 1` with `prompt_tokens`,
  `completion_tokens` and `request_count` all `NULL` so that it reads `0`, and
  MUST leave every other row unchanged.
- **FR-011**: The repair MUST NOT alter `spend_usd`, any token column, `id`, or
  the shape of the table, and MUST NOT rebuild `usage_records`.
- **FR-012**: The repair MUST be idempotent across reopenings and MUST NOT be
  gated on `SCHEMA_VERSION` or on the value recorded in `schema_version`.
- **FR-013**: The docstring at `factory/usage/models.py:139` — `UsageRecord`,
  which today describes `final_usage_confirmed` as a property of the confirmed
  path, MUST be corrected to describe it as a property of the row — that the row
  carries at least one count — and MUST NOT restate the claim that a confirmed
  reading always populates every field.
- **FR-014**: The `spend_usd` assertion inside
  `tests/test_usage_activities.py:626` — `test_an_attempt_that_never_called_the_proxy_records_unmeasured`,
  the test US1 amends — at `tests/test_usage_activities.py:643` — `test_an_attempt_that_never_called_the_proxy_records_unmeasured`
  as this spec was written, and to be located by that test's name and the
  assertion's text once US1's own new tests have shifted the number — MUST be
  amended in place from `0.0` to `None` rather than deleted, skipped, or left
  standing beside a second test that asserts the opposite. It is the one
  existing assertion the spend half is expected to turn red, and turning it red
  is not evidence that the predicate is too broad.
- **FR-015**: The `spend_usd` column annotation this story falsifies — "NULL
  only if no snapshot ever taken", carried identically at
  `factory/usage/ledger.py:75` and at its published source
  `specs/001-usage-tracking/contracts/ledger-schema.sql:27` — MUST be corrected
  at both sites, in the same diff as the branch that falsifies it, to state the
  case that branch introduces: `NULL` also means nothing was attributed to the
  key, so there was no price to record. The two lines MUST remain identical to
  each other, because `factory/usage/ledger.py:55` declares the whole block
  verbatim from that contract file. Neither the column's type nor any constraint
  may change.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-013]
US2:
  depends_on: []
  depends_on_merged: [US1]
  concurrent_with: [US3]
  implements: [FR-006, FR-007, FR-008, FR-009, FR-014, FR-015]
US3:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-010, FR-011, FR-012]
```

Two `depends_on_merged` edges, both declared rather than left inferred (069-US2
FR-007). US2 edits the same function US1 edits — `_record_for` in
`factory/activities/usage_activities.py` — and, at FR-014, the same test US1
amends four lines above, so raced they would collide in the merge queue and in
the file; the edge buys both correctness of sequencing and freedom from
contention. `factory/usage/models.py` is named by US1 alone. US3's own work
lives in `factory/usage/ledger.py` with its tests in
`tests/test_ledger_schema.py`, and its edge to US1 buys sequencing only — the
predicate it applies to history is the predicate US1 makes law, and a repair
that landed first would be rewriting rows to match a rule the writer had not yet
adopted. US2 names `factory/usage/ledger.py` too, at exactly one line: FR-015's
comment at `factory/usage/ledger.py:75`, inside the `_SCHEMA_DDL` string literal
and more than a hundred lines above the
`factory/usage/ledger.py:237` — `_migrate` neighbourhood US3 adds its repair
function to. That overlap is declared and waived — US2 carries `concurrent_with:
[US3]` — rather than ordered, because the only ordering available would make the
repair wait on the story held for an operator decision, and US3 is scoped to the
flag precisely so that decision cannot hold it hostage. The regions are
disjoint, neither story reads the other's, and no test file is shared: US2's
tests live in `tests/test_usage_activities.py` and US3's in
`tests/test_ledger_schema.py`.
