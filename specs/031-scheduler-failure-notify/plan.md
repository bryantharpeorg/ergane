# Plan: A pass failure is a fact told once, not a choice asked forever

All line references below were read against the tree at commit `9594787` on
2026-08-11. They are cited so you can find the code, not so you can trust the
numbers — grep for the named construct if a number does not resolve (trap 6).

## Reuse inventory

| What | Where | Used by |
| --- | --- | --- |
| The failure boundary: `try:` around `_run_inner`, report, `raise` | `factory/roadmap/workflow.py:658-664` (grep `_report_run_failure`) | US2 — kept; reporting made best-effort inside it |
| `_report_run_failure` | `workflow.py:884-925`; the churning key `workflow.info().workflow_id` at `:893` | US1 (the key), US2 (the delivery) |
| `_report_run_success` | `workflow.py:927-957`; same churning key at `:934` | US1, US2 |
| `_should_notify_failure` (1, then multiples of 3) | `workflow.py:142-150` | US1 — becomes powers of three |
| `roadmap_workflow_id` (the stable identity, pure, same module) | `workflow.py:162-172` (grep `ROADMAP_ID_PREFIX`) | US1 — the correct key, derivable from `request.specs_root` |
| `_NOTIFY` (one attempt, delivery failure is data) | `workflow.py:386-389` | US2 — the notice send keeps this posture |
| `record_roadmap_failure` + `roadmap_failures` DDL | `factory/activities/notify_activities.py:499-554`, DDL `:457-464` (grep `roadmap_failures`) | US1 — keyed by caller; US2 — escalation-row insert removed |
| The escalation-row insert inside it (RETRY/KILL, +3600s expiry) | `notify_activities.py:541-552` | US2 — this is what comes out |
| `reset_roadmap_failures` | `notify_activities.py:557-579` | US1 — recovery under a fresh workflow id |
| `send_escalation`'s `escalation_id` reuse branch | `notify_activities.py:284-291` | US2 — orphaned, deliberately left alone (trap 5) |
| `_send_question` — the buttonless send shape (no `reply_markup`) | `notify_activities.py:854-886` | US2 — the delivery precedent to copy |
| `manual_intervention_notice` — "a fact to be told, not a decision to be asked" | `factory/notify/messages.py:216-229` | US2 — the message-shape precedent |
| `escalation_message`'s deadline footer ("No answer by … KILL the node") | `messages.py:232-238` | US2 — the wrong grammar in today's page; must not appear in a notice |
| Bridge press on a closed workflow → "press again" toast | `factory/notify/service.py:94, :175-177, :317-331` | Evidence for US2; not modified |
| `pending_escalations` CLI listing (where forever-pending rows surface) | `factory/cli/nouns/build.py:525-534` | Evidence for US2; not modified |
| Worker activity registration | `factory/worker.py:125-126` | US2 — a new send activity registers beside these |
| Landed 021/us4 tests + the same-id restart loop | `tests/test_roadmap_failure_notifications.py` (the docstring at `:274-278`, the loop at `:283-289`) | US1 extends the harness for distinct ids; US2 re-points seams and the durability assertion |
| `build_corpus` / `RoadmapWorld` harness | `tests/test_roadmap_scheduler.py:198`, `:244` | Both stories' tests |

## Traps

### Trap 1 — the dedupe already exists; only its key is wrong

The cross-run mechanism the finding asks for is landed: `roadmap_failures` in
the evidence store, written before any send. The plausible wrong fix is to add
a second mechanism — a coarse time bucket, a new table, a Temporal search
attribute. Do none of that. Change what is passed as `roadmap_id` at the two
call sites (`workflow.py:893` and `:934`) from `workflow.info().workflow_id` to
`roadmap_workflow_id(request.specs_root)` — a pure function already defined in
the same module, deterministic, safe in workflow code. That is the whole of
FR-001/FR-002.

### Trap 2 — `workflow.info().workflow_id` looks right and is the bug

In every landed test it *equals* the stable id, because the harness starts runs
under `roadmap_workflow_id(specs_root)` — the docstring at
`test_roadmap_failure_notifications.py:274-278` says the next run is simulated
by restarting "under the same id" (the restart loop is at `:283-289`). A Temporal schedule appends the scheduled
time to the configured workflow id, so production runs never share an id. Your
new tests MUST start consecutive executions under *distinct* workflow ids over
one specs root — extend the harness with a workflow-id override rather than
copying its hardcoded id. A test that reuses one id proves nothing this story
adds.

### Trap 3 — notify then re-raise; the plausible wrong fix is a clean exit

FR-007. Once the page goes out it is tempting to return a status, or to convert
the failure into a recorded park, so the workflow "ends tidily". That is the
bug wearing a bow: Temporal's UI is the source of truth for a failed execution,
and 24 tidy exits are the original silence with extra steps. The boundary's
shape stays `report, then raise`. The one change FR-008 asks for is that the
report itself cannot mask the raise: wrap the reporting call so its own
exception is logged (`workflow.logger.exception`) and the original still
propagates. Equally: do not park the scheduler on anything — the corpus already
knows (017 held at draft over it) that a scheduler waiting on an operator
response deadlocks, and nothing in this spec waits.

### Trap 4 — "no buttons" means no pending row, not an empty keyboard

The plausible wrong fix for US2 is to keep `send_escalation` and pass an empty
`choices` list, or to keep writing the escalation row so the landed durability
test keeps passing untouched. The row is half the defect: nothing ever calls
`expire_escalation` for it (its would-be caller is dead), so it sits pending
forever, surfaces in `pending_escalations` (`build.py:525-534`), and invites a
press the bridge can only answer with "press again" (`service.py:94`). Delete
the insert at `notify_activities.py:541-552`; durability is the
`roadmap_failures` row, which the same activity already writes first. The
landed test `test_failure_is_recorded_when_notifier_is_down` asserts against
the escalations table — re-point that assertion at `roadmap_failures`, and add
its inverse: zero escalation rows for the roadmap. The fact the test proves
(record-before-send) must survive; the table it looks in changes.

The recovery path holds the same defect in miniature: `_report_run_success`
sends through `send_escalation` with no `escalation_id`, and the
insert-when-None branch (`notify_activities.py:284-285`) then writes a fresh
pending RETRY/KILL row — for a message that announces recovery. Re-pointing
*both* reporters at the notice send (T012) is what removes it; deleting only
`record_roadmap_failure`'s insert while leaving either reporter on
`send_escalation` keeps half the defect.

### Trap 5 — leave `send_escalation`'s `escalation_id` branch alone

After US2 nothing passes `escalation_id` to `send_escalation`
(`notify_activities.py:284-291` and the field at `:129-142` exist for the
roadmap path being removed). Removing them is a tidying instinct that widens
the diff into the epic escalation ladder — working code nobody asked this spec
to touch (the 010 US2 scenario-4 precedent). Leave the branch; it costs
nothing.

### Trap 6 — these line numbers rot

The 010 epic proved that refs a day old can be off by hundreds of lines and
even inverted in meaning. This plan was read at `9594787`; something may land
between it and your worktree. Grep for the construct, never trust the number:
`_should_notify_failure`, `roadmap_failures`, `_report_run_failure`,
`manual_intervention_notice`, `ROADMAP_ID_PREFIX`. If a citation here does not
match the tree, the tree wins and you say so in your commit message.

### Trap 7 — the suite must not touch the live evidence store or a real notifier

The open finding `hardening/test-suite-writes-to-the-live-evidence-store` is
about exactly this component. Every test builds its own store under `tmp_path`
(the landed file's `env` fixture already sets `VERIFICATION_DB_PATH_ENV` there —
keep that pattern) and replaces every send activity with a recording seam. No
test may read `.factory/verification.db` or open a socket toward Telegram.

## Approach

### US1 — one stable key, and a geometric page bound

1. In `_report_run_failure` and `_report_run_success`, derive
   `roadmap_id = roadmap_workflow_id(request.specs_root)` and use it for the
   store key and the message text. Both functions already receive `request`.
   The summary then reads `Roadmap roadmap-specs failed (3 consecutive runs)` —
   stable across scheduled executions, which is what makes the count legible.
2. Rewrite `_should_notify_failure` to page when the count is a power of three
   (1, 3, 9, 27, …). This is compatible with every landed assertion: one
   failure pages once; three failures page at 1 and 3 (fewer than three
   messages, count named); recovery is untouched.
3. Tests, in the landed file, using a harness extended with a workflow-id
   override: three failing executions under three schedule-shaped ids
   (`roadmap-<name>-<timestamp>`) over one specs root; a green run under a
   fourth id for recovery; nine failures for the geometric bound; two corpora
   for key independence.

### US2 — the notice grammar, end to end

1. `factory/notify/messages.py`: pure renderers `roadmap_failure_notice(...)`
   and `roadmap_recovery_notice(...)`. Copy `manual_intervention_notice`'s
   doctrine (fact, not choice) and `_compose`'s clipping; body is the failure
   text verbatim plus the count; no `expires_at` anywhere in the text; no
   keyboard function exists for them at all.
2. `factory/activities/notify_activities.py`: a small send activity for the
   notice, copying `_send_question`'s shape — token and chat id read from the
   worker environment inside the activity, sent with no `reply_markup`, a
   failed delivery returns a false flag rather than raising. Remove the
   escalation-row insert from `record_roadmap_failure` and the `escalation_id`
   field from its result (its only consumer was the send being replaced).
3. `factory/roadmap/workflow.py`: point both reporters at the new activity with
   `**_NOTIFY`; wrap the reporting call at the `run()` boundary so a reporter
   failure is logged and the original exception still propagates (FR-008).
4. `factory/worker.py`: register the new activity beside
   `record_roadmap_failure` (`:125-126`).
5. Tests: renderer unit tests in `tests/test_messages.py` (verbatim text,
   count, no deadline sentence, nothing offered); workflow tests in the landed
   file with the recording seam re-registered under the new activity's name —
   still-FAILED-with-original-exception, durability re-pointed at
   `roadmap_failures` plus zero escalation rows, and the reporter-broken case
   asserting the original exception survives.

## Complexity Tracking

| Thing | Why it is not simpler |
| --- | --- |
| A new send activity instead of `send_escalation` with no choices | An escalation with zero buttons still writes a pending row, advertises a deadline, and drags resolution machinery into a path with nothing to resolve; the buttonless send already exists as a shape in `_send_question`. |
| Powers-of-three paging instead of a time bucket | The store row already counts consecutive failures; the geometric test is one function, adds no clock, and turns the incident's 24 failures into 3 pages. A time bucket is a second mechanism with its own edge cases (FR-002 forbids it). |
| Editing a landed test file | Its assertions pinned the escalation-row implementation detail; the facts it proves survive with re-pointed targets. The alternative — a parallel test file asserting contradictory behavior — leaves the suite lying in one direction or the other. |
| No delivery-evidence column on `roadmap_failures` | Temporal history already records the failure and the notice activity's outcome; a column would duplicate evidence nothing reads. |

## Verification

The gate is `uv run pytest -q` (factory.yaml's one gate) — green in the node's
worktree, never with an operator environment exported (trap 7). Beyond green,
the tests that did not exist before are the point: consecutive failures under
*distinct* workflow ids accumulating one count, and a failure page that offers
nothing while the workflow execution still fails. If either passes before its
implementation task runs, the test is wrong — constitution II.
