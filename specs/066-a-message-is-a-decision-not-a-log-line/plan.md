# Implementation Plan: a message is a decision, not a log line

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## What already exists, and where

**The composer that produced every message in the screenshot is fourteen lines
and takes a bare string.** `factory/notify/messages.py:329` —
`roadmap_failure_notice`:

```python
def roadmap_failure_notice(roadmap_id: str, failure_text: str, count: int) -> str:
    """The notify-only message when a roadmap pass fails.

    A scheduler pass failure is a fact to be told, not a decision to be asked:
    there is no inline keyboard, no offered choice, no response deadline, and
    no pending escalation row. The message carries the failure text verbatim
    and the consecutive count; the durable fact lives in the `roadmap_failures`
    record written before any send.
    """
    header = f"⚠️ Roadmap failure\nroadmap: {roadmap_id}\n\n"
    count_word = "run" if count == 1 else "runs"
    body = f"Roadmap {roadmap_id} failed ({count} consecutive {count_word}): {failure_text}"
    return _compose(header, body, "")
```

Two facts to take from it. The docstring's promise to carry the text verbatim is
the decision FR-001 reverses, so the docstring is part of the diff. And the
signature is the whole of FR-007's problem: `failure_text: str` is all the
composer knows, so "what stopped, in factory vocabulary" has no input.

**Six composers exist and the spec's table names all six.** There are exactly
six call sites of `factory/notify/messages.py:656` — `_compose`, one per
composer, and the spec's enumeration is derived from that count rather than from
a list somebody remembered. Sorted by what this story set does to them:

- **Changed by US2** — `factory/notify/messages.py:329` —
  `roadmap_failure_notice` (US1 restructures it first; US2 only extends it) and
  `factory/notify/messages.py:344` — `roadmap_recovery_notice`.
- **Controls, byte-unchanged** — `factory/notify/messages.py:414` —
  `escalation_message` and `factory/notify/messages.py:484` —
  `question_message`. FR-012 covers both.
- **Out of scope** — `factory/notify/messages.py:502` — `resolution_notice`,
  which fires after the decision is in, and
  `factory/notify/messages.py:313` — `manual_intervention_notice`, which
  nothing sends. The next paragraph is that second claim's evidence, because it
  is the reason this story set is two composers wide rather than three.

**`manual_intervention_notice` is dead code, and an earlier draft of this trio
spent a third of US2 on it.** `grep -rn manual_intervention --include=*.py
factory/` returns exactly one line — the definition at
`factory/notify/messages.py:313`. Every other reference in the repository is a
test: the import at `tests/test_messages.py:40`, and
`tests/test_messages.py:245` — `test_manual_intervention_notice_renders_with_no_buttons`
with its history-summary sibling below it. `factory/notify/service.py:77`
imports only `resolution_notice` of this family, and the merge-queue outcome
that would produce the fact the notice describes,
`factory/mergequeue/classify.py:74` (`DEQUEUED_BY_HUMAN`), composes no message
at all: `factory/workgraph/workflow.py:3408` records the observation and ends
the landing, and no notice follows. So the composer is written, tested, and
never delivered. It is out of scope by decision, stated in spec.md § "What this
spec is not"; wiring it to a send site is a real want and a different spec,
because a send site is a production file outside `factory/notify/messages.py`
and the Work Graph's concurrency justification for US2 and US3 rests on US2
having none.

**`_compose` protects the header and the footer and eats the body from the
front.** `factory/notify/messages.py:656` — `_compose` computes its room as
`MESSAGE_LIMIT - len(header) - len(footer)` and clips the body's *front*,
`factory/notify/messages.py:663-666`, against `MESSAGE_LIMIT = 4096` at
`factory/notify/messages.py:70`. Its own docstring says why: "the header names
the node and the footer states the consequence, so both survive intact and the
history absorbs the clip". That is the mechanism, and 079-US4 is the landed
precedent that obeys it — the escalation's blast-radius block sits in the
footer, not the body. Trap 16 is what this means for FR-005's three lines.

Prior art for turning raw output into one useful line is next door:
`factory/notify/messages.py:461` — `_render_check_evidence` and
`factory/notify/messages.py:476` — `_last_failing_test_line`. Read those before
inventing a new approach.

**The model is already in the tree, and 079 put it there.** The return of
`factory/notify/messages.py:414` — `escalation_message`, at
`factory/notify/messages.py:451`:

```python
    return _compose(
        _header("⚠️ Verification escalation", record),
        body,
        f"{bound}"
        f"\n\n{render_blast_radius(record.choices)}"
        f"\n\nNo answer by {record.expires_at} applies the default: "
        f"{_value(default)} the node.",
    )
```

`factory/notify/messages.py:358` — `render_blast_radius` renders one line per
*offered* choice from the table at `factory/notify/messages.py:134`
(`_CHOICE_EFFECTS`), and that table's comment already makes this spec's
argument:
"A label is four words on a phone, and four words cannot carry a blast radius."
US2 is not building that. US2 is bringing the two changed notices up to it,
and FR-012 keeps this message exactly as it is.

**The second control already does it too, without a keyboard.** The footer of
`factory/notify/messages.py:484` — `question_message`, at
`factory/notify/messages.py:495`:

```python
    footer = (
        f"\n\nReply to this message with your answer (attempt {record.attempt}). "
        f"No answer by {record.expires_at} lets the node proceed as a FAIL."
    )
```

That is an option an operator can take and a consequence of silence, landed by
008-US1 and never a defect. It is in FR-012 for the same reason the escalation
is: US2's temptation is one house style for every silence sentence, and the
house style would be applied to the sentence that has been right all along.

**The three sites that report a roadmap failure, each of which knows its cause
and none of which says so.**

- `factory/roadmap/workflow.py:1082` — `_report_run_failure`, the whole-pass
  catch, reached from `factory/roadmap/workflow.py:771` — `run`.
- `factory/roadmap/workflow.py:909` — `_run_inner`, the unreadable-child-result
  path: `discarded child result for {spec_dir}: could not read returned value as
  EpicStatus`.
- `factory/roadmap/workflow.py:1387` — `_drift_resolver`, the degrade path
  inside the per-spec loop:

```python
            except FailureError as exc:
                # Degrade: treat the spec as not drifted for this pass and report
                # the failure once through the roadmap's failure-notice channel.
                failure_text = self._roadmap_failure_message(exc)
                await self._report_roadmap_failure(
                    request,
                    f"drift_for_spec({spec_dir}) failed: {failure_text}",
                )
```

All three funnel through `factory/roadmap/workflow.py:1044` —
`_report_roadmap_failure`, which records first and sends second, and through
`factory/roadmap/workflow.py:1028` — `_roadmap_failure_message`, whose docstring
commits the text to being verbatim from the exception.

**The loop the third site sits in** is driven by
`factory/roadmap/workflow.py:1398` — `_compute_drift`, once per landed spec.
That is the pass boundary FR-014's fold belongs at.

**The count, and what it keys on.**
`factory/activities/notify_activities.py:680` — `record_roadmap_failure` raises
the consecutive count only when the new text is byte-identical to the stored
one, and resets it to 1 otherwise. Its table is created by
`factory/activities/notify_activities.py:606` (`_ROADMAP_FAILURES_DDL`),
executed with `executescript` on every call as `CREATE TABLE IF NOT EXISTS`, and
its primary key is `roadmap_id`, one row per roadmap for all time. The geometric
throttle that reads the count is `factory/roadmap/workflow.py:152` —
`_should_notify_failure`, and it is correct.

**The migration precedent** is `factory/verify/store.py:556` — `_migrate`: read
`PRAGMA table_info`, `ALTER TABLE … ADD COLUMN` when the column is missing. The
`roadmap_failures` table is not in it.

**The secret patterns** are `factory/controlplane/config.py:80`
(`_SECRET_PATTERNS`), already imported by `tests/test_readme.py:24` and
`tests/test_onramp_html.py:16` to refuse secret-shaped strings. FR-006 reuses
them; it does not restate them.

**The CLI parser and what it accepts**, rewritten by 113 on 2026-08-28:
`tests/page_holds_true.py:180` — `parse_argv` validates one argv through the
real parser without dispatching a handler or spawning a subprocess, substituting
angle-bracket placeholders first via `tests/page_holds_true.py:175` —
`_substitute_placeholders`. `tests/page_holds_true.py:358` — `split_argv` and
`tests/page_holds_true.py:346` — `verbs_of` split and name what an argv
contains. `tests/test_claude_md.py:57` (`COMMANDS`) is the shape to copy for the
parse half — and only that half; see trap 14 for the half that does not
transfer. The verbs a notice may name are the ones
`factory/cli/roadmap.py:73` — `add_roadmap_parser` registers — `start`,
`pause`, `resume`, `status`, `promote`, `unpark` — plus the other nouns' verbs.
Every one of them takes a `specs_root` positional, declared at
`factory/cli/roadmap.py:136` for `pause` and once more per verb below it.

**Where the composer gets that positional**, since it is the one value FR-011
needs and the composer is not handed: it derives it from the `roadmap_id` it
already has. `factory/roadmap/workflow.py:178` — `roadmap_workflow_id` builds
the id as `ROADMAP_ID_PREFIX` (`factory/roadmap/workflow.py:175`) plus the specs
root's *basename*, so stripping that prefix off `roadmap-specs` yields `specs` —
which is exactly the spelling an operator types from the repository root, the
same one `CLAUDE.md` and the README use (`ergane spec list specs`). The full
path is not recoverable and does not need to be. Trap 17 carries the two wrong
moves this rules out.

**The tests that already hold this ground.** Every citation here is written in
the symbol form so the next drift is machine-caught rather than re-read by hand.

- `tests/test_messages.py:282` — `test_roadmap_failure_notice_carries_failure_text_and_count`, asserting `FAILURE_TEXT in notice` at `tests/test_messages.py:286`
- `tests/test_messages.py:290` — `test_roadmap_failure_notice_offers_nothing_and_names_no_deadline`
- `tests/test_roadmap_failure_notifications.py:406` — `test_a_failed_run_notifies_once_with_the_failure_verbatim`, asserting at `tests/test_roadmap_failure_notifications.py:422`
- `tests/test_roadmap_failure_notifications.py:835` — `test_clean_run_under_sandbox_with_prior_failure_reaches_completed`, asserting at `tests/test_roadmap_failure_notifications.py:862`
- `tests/test_roadmap_failure_notifications.py:892` — `test_failed_run_sends_notice_and_workflow_fails_with_original_exception`, asserting at `tests/test_roadmap_failure_notifications.py:913`
- `tests/test_roadmap_failure_notifications.py:988` — `test_unreadable_child_result_records_failure_and_notifies`, asserting `"001-alpha" in call.message and "could not read" in call.message` at `tests/test_roadmap_failure_notifications.py:1024`
- `tests/test_roadmap_failure_notifications.py:495` — `test_failure_is_recorded_when_notifier_is_down`, the durable row — this one asserts the *stored* text at `tests/test_roadmap_failure_notifications.py:532` and stays true
- `tests/test_roadmap_failure_notifications.py:176` — `_failure_count_from`, the helper that parses the count back out of the notice text at four call sites, the first inside `tests/test_roadmap_failure_notifications.py:547` — `test_schedule_churned_ids_accumulate_one_count_and_page_geometrically` at `:571`, then `:654`, `:701` and `:702`; that same test carries a fifth verbatim assertion of its own at `:575`

## Traps

**Trap 1 — The four messages in the frontmatter are the fixture, not
decoration.** All four came out of `factory/notify/messages.py:329` —
`roadmap_failure_notice`, and FR-001 and FR-002 are about them specifically. The
wrong move is inventing fresh example strings for the tests: a diff can then
satisfy every assertion while the four messages that actually failed a human are
unchanged. Use `'NoneType' object has no attribute 'epic_state'` and the
`drift_for_spec(020-landing-attribution) failed: git fetch --quiet origin …`
text as literal inputs.

**Trap 2 — Record before send; do not clean the page by dropping the
evidence.** `factory/roadmap/workflow.py:1044` — `_report_roadmap_failure`
writes the `roadmap_failures` row through `record_roadmap_failure` and only then
calls `send_roadmap_notice`, deliberately: "a notifier that is down loses the
message, not the fact." FR-004. The wrong move is dropping `failure_text` from
`RecordRoadmapFailureInput` because the notice no longer prints it, or reordering
so the send happens first. `tests/test_roadmap_failure_notifications.py:495` — `test_failure_is_recorded_when_notifier_is_down`
is what catches the reorder;
nothing catches the drop except FR-004's own paired test. FR-006's test is the
same pair with a credential in it, and it exists because the second wrong move —
protecting a secret by not recording it — looks responsible and destroys the
only copy.

**Trap 3 — Seven landed sites assert the behaviour US1 reverses, not three, and
they are the most expensive thing in this plan.** An earlier draft of this trap
named three. All seven sit in the two test files US1 already edits, so an
implementer who fixed the three named ones met four more red at exactly the
point this plan had stopped speaking — which is when the two wrong moves below
become tempting. Five of the seven are a one-line deletion, entry 3 is a helper
re-taught to parse the new phrasing, and entry 7 needs a decision. The whole
list, with what survives:

1. `tests/test_roadmap_failure_notifications.py:406` — `test_a_failed_run_notifies_once_with_the_failure_verbatim`,
   `assert FAILURE_MESSAGE in recorder.calls[0].message` at
   `tests/test_roadmap_failure_notifications.py:422`. The verbatim assertion
   goes; the "notifies once" assertion above it stays.
2. `tests/test_messages.py:282` — `test_roadmap_failure_notice_carries_failure_text_and_count`,
   `assert FAILURE_TEXT in notice` at `tests/test_messages.py:286`. The
   verbatim assertion goes; the `ROADMAP_ID` and `"3 consecutive"` assertions
   either side of it stay, and the test's name has to change with its intent.
3. `tests/test_roadmap_failure_notifications.py:176` — `_failure_count_from`,
   which parses the literal substrings `failed (` and ` consecutive run` out of
   the notice and feeds four assertions at
   `tests/test_roadmap_failure_notifications.py:571`, `:654`, `:701` and `:702`.
   The helper survives, re-taught to parse the new phrasing; deleting it deletes
   the count guarantee FR-001 explicitly keeps.
4. `tests/test_roadmap_failure_notifications.py:547` — `test_schedule_churned_ids_accumulate_one_count_and_page_geometrically`
   carries its own `assert FAILURE_MESSAGE in call.message` at `:575`, below the
   count assertions trap entry 3 covers. That verbatim assertion goes; the count
   and roadmap-id assertions in the same loop stay.
5. `tests/test_roadmap_failure_notifications.py:835` — `test_clean_run_under_sandbox_with_prior_failure_reaches_completed`,
   `assert FAILURE_MESSAGE in recorder.calls[0].message` at
   `tests/test_roadmap_failure_notifications.py:862`. The verbatim assertion
   goes; the reached-COMPLETED assertions stay.
6. `tests/test_roadmap_failure_notifications.py:892` — `test_failed_run_sends_notice_and_workflow_fails_with_original_exception`,
   `assert FAILURE_MESSAGE in notice.message` at
   `tests/test_roadmap_failure_notifications.py:913`. The verbatim assertion
   goes; the exception-chain assertion at
   `tests/test_roadmap_failure_notifications.py:907` is about the raised
   exception, not the notice, and stays untouched — a notice that stops printing
   the repr must not stop the workflow from raising it.
7. `tests/test_roadmap_failure_notifications.py:988` — `test_unreadable_child_result_records_failure_and_notifies`,
   `assert "001-alpha" in call.message and "could not read" in call.message` at
   `tests/test_roadmap_failure_notifications.py:1024`. This is the only one that
   needs a real decision rather than a deletion, because it asserts the text of
   the second of the three sites T008 changes,
   `factory/roadmap/workflow.py:909` — `_run_inner`. `"could not read"` is a
   span of the failure text and FR-006 keeps the text out of the notice, so the
   assertion must become the *named cause* that site now passes as a value —
   the discarded-child-result cause — asserted in the factory vocabulary FR-001
   requires. The `"001-alpha"` half survives only if the reporting site passes
   the spec dir as a value alongside the cause; if it does not, replace it with
   the affected-spec count FR-002 gives the notice, and never with a substring
   of the failure text.

`tests/test_roadmap_failure_notifications.py:495` — `test_failure_is_recorded_when_notifier_is_down`
looks like an eighth and is not: its `row[1] == FAILURE_MESSAGE` at
`tests/test_roadmap_failure_notifications.py:532` reads the stored row, which
FR-004 keeps verbatim. If that one goes red, the diff dropped the record.

These encode 031's FR-009/012, which FR-001 partly reverses and partly keeps.
There are two wrong moves and an implementer will be tempted by both: keep the
raw text so the suite stays green, which ships nothing; or delete the tests,
which also deletes the consecutive-count guarantee FR-001 explicitly keeps.
Rewrite their intent — the count survives, the repr does not.

**Trap 4 — A fallback that prints the raw text has changed nothing, and once it
is gone the ordering criterion has nothing to compare against.** FR-003 and
FR-005. The tempting shape is a lookup table of known causes with
`else: return failure_text`. That preserves today's behaviour for every failure
nobody has seen yet, which is every failure that will actually surprise an
operator. The generic path must state impact and options and point at the
`roadmap_failures` record. The second-order consequence is the reason FR-005 is
worded as a three-way order rather than as "impact before detail": once no
failure detail reaches the notice at all, "before any line carrying failure
detail" is a comparison against an empty set, and a test written that way passes
on a notice that lost the pointer, lost the options block, or lost both. Assert
the presence and the relative order of all three named lines.

**Trap 5 — There is no seam to classify a failure on, and sniffing the text is
the mistake this tree has already refused once.**
`factory/notify/messages.py:329` — `roadmap_failure_notice` receives
`failure_text: str` and nothing else, so a composer asked to say what stopped can
only pattern-match on exception strings. `factory/workgraph/contention.py:24`
names that move by name: it is "the same mistake as classifying a rejection by
its message text (069 plan trap 2)". FR-007 is the fix and it is US1's real
work: each of the three reporting sites —
`factory/roadmap/workflow.py:1082` — `_report_run_failure`,
`factory/roadmap/workflow.py:909` — `_run_inner`, and
`factory/roadmap/workflow.py:1387` — `_drift_resolver` — names its own cause and
passes it as a value. US1-S7 is the test that a diff which regex-matched instead
cannot pass.

**Trap 6 — Two messages are the model, not victims, and one of them is easy to
miss.** `factory/notify/messages.py:358` — `render_blast_radius` and the effects
table at `factory/notify/messages.py:134` (`_CHOICE_EFFECTS`) landed with 079 on
2026-08-22, and the return at `factory/notify/messages.py:451` inside
`factory/notify/messages.py:414` — `escalation_message` already states the
default on silence. The second is `factory/notify/messages.py:484` —
`question_message`, whose landed footer says "Reply to this message with your
answer" and "No answer by … lets the node proceed as a FAIL". FR-012 forbids
changing either. There are two wrong moves. Refactoring escalation and notices
into one generic builder: the escalation comes out shorter and vaguer to fit the
abstraction, and the story that was supposed to raise every other message has
lowered the only good one. And sweeping the question message into "every notice
gets a house-style silence sentence": it already has one, it is 008-US1's, and a
rewrite of it is a regression that no test in the tree catches today — which is
why US2-S5 asserts both controls in the same test as the change.

**Trap 7 — An options block that borrows the escalation's words breaks a landed
test, and the test is right.** `tests/test_messages.py:290` — `test_roadmap_failure_notice_offers_nothing_and_names_no_deadline`
asserts that
`"No answer by"`, `"expires"`, `"Retry"`, `"Kill"` and `"button"` are all absent
from a roadmap notice. That is 031's decision — a notice offers no choice over
the wire, so a keyboard word in one is a promise the bridge would have to refuse
— and FR-012 keeps it. FR-008 and FR-009 must therefore be satisfied in a
different register: the options are `ergane` commands the operator runs, and the
silence sentence names the next scheduled pass, not a deadline. Note the
asymmetry this creates and do not "fix" it: the question message may keep
`No answer by`, because it is not a roadmap notice and that test does not reach
it.

**Trap 8 — The throttle keys on the rendered text, and the throttle is not the
bug.** `factory/activities/notify_activities.py:680` —
`record_roadmap_failure` raises the count only on
`row[1] == request.failure_text` and resets it to 1 otherwise, so
`drift_for_spec(020-…) failed: …` and `drift_for_spec(021-…) failed: …` reset it
sixty-three times in one pass. FR-015 changes what is compared. The wrong move
is editing `factory/roadmap/workflow.py:152` — `_should_notify_failure`, which
is a correct powers-of-three throttle that was fed a count that never rose.

**Trap 9 — `CREATE TABLE IF NOT EXISTS` will not add your column to a live
store.** `factory/activities/notify_activities.py:606`
(`_ROADMAP_FAILURES_DDL`) is executed with `executescript` on every call and is a
no-op against an existing database, so a column added there exists in a fresh
`tmp_path` store and nowhere else — green suite, broken operator. FR-015
requires the additive path instead, modelled on
`factory/verify/store.py:556` — `_migrate`: `PRAGMA table_info`, then
`ALTER TABLE roadmap_failures ADD COLUMN …` when it is missing. A test that
creates the old table first and then calls the activity is the one that proves
it.

**Trap 10 — The fold belongs at the pass boundary, not inside the activity.**
`factory/roadmap/workflow.py:1387` — `_drift_resolver` reports from inside the
per-spec loop that `factory/roadmap/workflow.py:1398` — `_compute_drift` drives,
which is why one cause becomes N notices. FR-014 wants the causes accumulated
across the pass and reported once when the loop ends. The wrong move is
deduplicating inside `record_roadmap_failure`: it is an activity, it is retried,
it holds no per-pass state, and suppressing sends there would also suppress the
count `_should_notify_failure` reads.

**Trap 11 — Collapsing distinct causes is worse than repeating one.** FR-016 and
US3-S3. A hash over the whole pass, or a "one notice per pass" rule, hides a
second genuine fault behind the first — and the second fault is the one nobody
knows about. The scenario drives a pass with sixty specs on one cause and one on
another and asserts exactly two notices, so a naive collapse fails it.

**Trap 12 — `run_help` does not exist any more.** The 2026-08-19 draft of this
plan told FR-009's implementer to reuse `tests/page_holds_true.py`'s `run_help`;
113 replaced it on 2026-08-28. What exists for FR-011 is
`tests/page_holds_true.py:180` — `parse_argv`, which validates through the real
parser without dispatching a handler or spawning a subprocess, plus
`tests/page_holds_true.py:358` — `split_argv` and
`tests/page_holds_true.py:346` — `verbs_of`. The wrong move is writing a second
CLI-parsing helper, which is how two suites drift apart with both green (054
trap 3). Reuse `parse_argv`. What you may **not** reuse is the extraction half —
that is trap 14.

**Trap 13 — The judge sees the diff and the criteria, nothing else.**
Constitution VIII and D-037. Every runtime claim in this spec — the count of
notices a pass produced, the before-and-after of the four screenshot messages,
the message volume over a day — must be committed as pasted tool output in the
diff, not described. A criterion that named a terminal, a Telegram channel or a
running scheduler would be unprovable by construction and would burn attempts.

**Trap 14 — The 113 command sweep cannot see a notice, and making it see one
would put backticks on the operator's phone.** This is the trap that would have
cost US2 the whole of its diff bound. `tests/page_holds_true.py:292` —
`assert_commands_not_dropped` and `tests/page_holds_true.py:301` —
`extract_commands` both read from `tests/page_holds_true.py:283` —
`_command_shaped_spans`, which reads spans from `tests/page_holds_true.py:41` —
`code_spans`: backticked spans and fenced ```bash blocks, nothing else. A notice
is plain text — `factory/notify/messages.py:656` — `_compose` adds no markup,
and `parse_mode` appears nowhere in `factory/` or `tests/`, so
`factory/notify/service.py:318`'s `send_message` call ships the text literally
and Telegram renders it literally. The sweep therefore returns **0** over any
notice corpus, and the anti-vacuity assertion cannot be met. There are two wrong
moves and the first is the seductive one: wrap the notice's commands in
backticks so the extractor finds them, which puts visible backticks on the phone
in the one spec whose entire subject is how a message reads. The second is
writing a second extractor, which trap 12 forbids. There is a third constraint
underneath, so that nobody "fixes" it by tweaking the span shape:
`tests/page_holds_true.py:258` — `_is_command_shaped` drops any span containing
`/`, `.` or `=`, and every roadmap verb takes a `specs_root` positional, so a
real invocation is invisible to that rule whatever the markup. FR-011's answer
is the declared-invocation seam: the composer holds each `ergane` invocation as
an argv value, renders it into the notice text, and the test parses the declared
argv with `parse_argv` and asserts the rendered form appears verbatim in the
notice that declared it. Non-vacuity is then asserted directly, on the declared
set, and no markup reaches the operator.

**Trap 15 — Recording per spec while sending one notice silently sends
nothing.** FR-014 and FR-015 together, and this is the failure mode of the
charitable reading of "keep the record per failure". The store has no
per-failure row and never has:
`factory/activities/notify_activities.py:606` (`_ROADMAP_FAILURES_DDL`) declares
`roadmap_id TEXT PRIMARY KEY` with `consecutive_count`,
`last_failure_text` and `updated_at`, and
`factory/activities/notify_activities.py:680` — `record_roadmap_failure`
INSERTs once and thereafter UPDATEs that one row in place. Today's 63-notice
pass leaves exactly one row. So an implementer who folds the *send* to one per
cause but leaves the *record* call inside the per-spec loop gets this: US3's
count now keys on the cause (FR-015), sixty-three records under one cause in one
pass drive `consecutive_count` to 63, and
`factory/roadmap/workflow.py:152` — `_should_notify_failure` reduces 63 → 21 → 7
and returns False. The pass that produced 63 notices before the change produces
**zero** after it, and every test that counts notices at 1 for a first pass
fails in a way that reads like a fold bug. Record once per distinct cause per
pass, before the send, as FR-004 requires — and US3-S2's "count is 1 after one
pass" assertion is the guard that catches this specific mistake rather than
letting it be diagnosed from a silent phone. A per-failure history table is out
of scope: no FR asks for one, FR-015 permits only an additive `ADD COLUMN`, and
the verbatim text of the reported cause stays in `last_failure_text` exactly as
it does today.

**Trap 16 — The clip eats the front of the body, so a durable line placed there
is the first thing the operator loses.** `factory/notify/messages.py:656` — `_compose`
computes `room = MESSAGE_LIMIT - len(header) - len(footer)` and, when the body
is longer, replaces its front with `_HISTORY_TRUNCATED`:
`factory/notify/messages.py:663-666`. Only the header and the footer are
guaranteed to reach the phone. This is not theory — it is why 079-US4 put the
blast-radius block in the escalation's *footer* rather than its body, and that
commit is the landed precedent to copy. The wrong move here is composing FR-005's
impact line, options block and pointer into the front of the body, which is
precisely the half a clip removes, and removing the pointer first: the one line
that tells the operator where the truth is recorded is the first thing lost.
The exposure is latent rather than certain for a roadmap notice today, because
FR-001 takes the unbounded failure text out of the body — but FR-002 puts an
affected-spec count in, and an implementer who renders the affected spec *names*
instead of the count has an unbounded body again on a 63-spec pass. Two ways
out, both acceptable: put the durable lines in the footer, or keep the body
bounded by construction and say so in the test. Choose one deliberately;
US1-S5's ordering assertion passes either way and will not catch this for you.

**Trap 17 — The specs-root positional has a seam, and both of the other two
moves are wrong.** FR-011 requires every `ergane` command a notice names to be
runnable, and every roadmap verb takes a `specs_root` positional —
`factory/cli/roadmap.py:73` — `add_roadmap_parser` declares it once per verb
from `factory/cli/roadmap.py:136` down. The composer is handed a `roadmap_id`
and nothing else. The seam is that `roadmap_id` already contains what is needed:
`factory/roadmap/workflow.py:178` — `roadmap_workflow_id` builds it as
`ROADMAP_ID_PREFIX` (`factory/roadmap/workflow.py:175`) plus the specs root's
basename, so stripping the prefix off `roadmap-specs` gives `specs`, the
spelling an operator types from the repository root. Two wrong moves. **A
placeholder**: `ergane roadmap status <specs-root>` *passes* FR-011's parse
check, because `<specs-root>` is not in `tests/page_holds_true.py:163`
(`_PLACEHOLDER_VALUES`) and argparse accepts any string for a positional — so
the test goes green while the operator's phone shows a command that cannot be
typed, and plan verification step 5 is the only thing that catches it. FR-011's
no-angle-brackets clause exists for this. **A new parameter**: adding a
specs-root argument to `roadmap_failure_notice` forces an edit to
`factory/roadmap/workflow.py:1073` and `factory/roadmap/workflow.py:1103`,
which puts US2 in the file US3 is rewriting and falsifies both this plan's
Sizing paragraph and the Work Graph's justification for running US2 and US3
concurrently. US2 changes no composer signature; US1 sets them.

**Trap 18 — The reporting site is not the cause, and FR-010 needs a finer one
than trap 5 hands you.** FR-010 and US2-S3 require a notice to say whether its
cause clears itself, which means at least two causes with opposite answers must
exist. Trap 5 names the three *sites* that must name a cause; it does not say
the site is the cause, and an implementer who reads it that way mints a
three-value vocabulary in which FR-010 cannot be satisfied honestly.
`factory/roadmap/workflow.py:1387` — `_drift_resolver` raises both kinds
through one site: the 2026-08-19 `git fetch` hook refusal never cleared and
needed the operator, while an activity timeout on the same `drift_for_spec`
call is retried by the next scheduled pass. The whole-pass site,
`factory/roadmap/workflow.py:1082` — `_report_run_failure`, is the mirror
image: the 7:21 AM recovery notice in the frontmatter is proof that a
whole-pass failure *did* clear itself. So the cause must be decided from the
exception's structure — its type and its `FailureError` chain — and never from
its text, which is trap 5's refusal restated one level down. The landed
precedent is `factory/roadmap/workflow.py:1438` — `_derivation_detail`, which
reaches through `exc.cause` and tests `isinstance(inner, ApplicationError)`
rather than reading a string, and the comment at
`factory/roadmap/workflow.py:1182-1183` is the tree already reasoning this way
about the same base class. The wrong move is one cause per site with a
hardcoded self-clearing flag on each: it satisfies US2-S3's test, and leaves
verification step 4 unmet, because the scheduler wedge and a transient drift
failure would then carry the same answer. US2-S3's test therefore drives two
causes out of the *same* site — a `drift_for_spec` failure whose chain bottoms
out in a non-retryable `ApplicationError` (the hook refusal: it will not clear
itself) and one whose chain bottoms out in a Temporal timeout (the next
scheduled pass retries it). The cause vocabulary is minted in US1 by T008, so
this constraint has to be met a story before the requirement that needs it.

## Sizing

**US1** touches `factory/notify/messages.py` (the failure composer, the notice
structure) and `factory/roadmap/workflow.py` (the named cause at the three
reporting sites and through `_report_roadmap_failure`). Its tests live in
`tests/test_messages.py` and `tests/test_roadmap_failure_notifications.py`, and
rewriting the seven landed sites trap 3 names — five verbatim assertions that
go, the count helper re-taught, and the unreadable-child-result assertion that
needs a decision — is part of its diff. Five of those are a one-line deletion
inside a test that otherwise stands, so seven sites is a larger count than the
earlier draft claimed and not a much larger diff.

**US2** touches `factory/notify/messages.py` and no other production file, and
exactly two composers in it: `factory/notify/messages.py:329` —
`roadmap_failure_notice` and `factory/notify/messages.py:344` —
`roadmap_recovery_notice`. `factory/notify/messages.py:414` —
`escalation_message` and `factory/notify/messages.py:484` — `question_message`
are read as controls and not edited; `factory/notify/messages.py:502` —
`resolution_notice` and `factory/notify/messages.py:313` —
`manual_intervention_notice` are not touched at all. No composer signature
changes in US2 (trap 17): a new parameter would put this story in
`factory/roadmap/workflow.py` alongside US3. `roadmap_failure_notice` arrives with
an options block already built by US1 under FR-003 and FR-005 — US2 extends it
with the silence sentence and does not restructure it. Its tests are
`tests/test_messages.py` plus one new module for the declared-invocation check,
which copies the parse half of `tests/test_claude_md.py:57` (`COMMANDS`) and
not the extraction half (trap 14).

**US3** touches `factory/roadmap/workflow.py` (accumulate causes across the pass,
report once at the `_compute_drift` boundary) and
`factory/activities/notify_activities.py` (key the count on the cause, plus the
additive migration). Its tests are
`tests/test_roadmap_failure_notifications.py`. It does **not** edit
`factory/notify/messages.py`: US1 gives the notice its field for the affected
spec count and US3 fills it.

US2 and US3 name no production file in common, which is why they carry no edge
between them and are meant to run concurrently once US1 lands. US1 shares a file
with each of them, which is why each waits on US1 having *merged* rather than
having verified.

All three are well inside the 64 KiB deterministic diff bound (D-050). US1 is the
largest — roughly two hundred production lines plus the seven rewritten test
sites trap 3 enumerates, five of them a single assertion each —
and its pasted evidence is the four before-and-after messages, which are five
lines each, not a transcript. US3's pasted evidence is two notice counts.

## Verification the operator will run, independent of the gate

Per Constitution VIII and D-037 the judge sees the diff and the criteria only, so
every runtime reading below must also be committed as pasted output in the story
that produces it.

1. **Read the four.** Compose the messages from the 2026-08-19 screenshot with
   the new composers and read them as the person holding the phone at 4:05 PM.
   Could he have acted? This is unfalsifiable by a gate, which is exactly why it
   is the operator's step.
2. **Hand one to a stranger.** Someone who does not maintain Ergane should be
   able to say, from the notice alone, what stopped and what their choices are.
3. **Replay the flood.** Break `git fetch` in the roadmap target clone the way
   the 2026-08-19 hook did, run one full corpus pass, and count the notices. 63
   before; the target is one, naming the affected spec count. Read the
   `roadmap_failures` row after it too: `consecutive_count` must be 1, not 63
   (trap 15).
4. **Replay the wedge.** Force the `'NoneType' object has no attribute
   'epic_state'` path and read the page. It must say the scheduler has stopped,
   that nothing will build until it is cleared, that it will not clear itself,
   and name the command.
5. **Run every command any notice names**, by hand, against a live install, from
   the directory the operator actually works in. The declared-invocation check
   proves they parse; only this proves they do what the sentence claims, and it
   is the only step that catches a specs-root positional rendered as
   `<specs-root>` — that spelling parses (trap 17). Read them on the phone
   first: no backticks should be visible (trap 14).
6. **Count a normal day.** Total operator-channel message volume before and
   after. If it rose, the spec failed regardless of what the suite says.

Step 3 is the falsifiable test of US3 and step 4 of US1 and US2 together: they
are the two outages of 2026-08-19, run forwards.
