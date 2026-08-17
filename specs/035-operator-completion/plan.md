# Plan: An operator may finish what an agent could not — visibly, and counted

All line references were read against the tree at `8ac64fd` on 2026-08-12 and
verified by grep the same day. They are cited so you can find the code, not so
you can trust the numbers — grep for the named construct if a number does not
resolve.

## Reuse inventory

| What | Where | Used by |
| --- | --- | --- |
| The operator-signal pattern, three of them | `factory/workgraph/workflow.py:514` (`pause_epic`), `:527` (`resume_epic`), `:532` (`kill_epic`) | US1 — the shape a new signal copies |
| A signal carrying operator payload, and its deliberate incuriosity | `factory/escalation/workflow.py:246` `escalation_resolved(escalation_id, choice)` — **moved out of the epic workflow by 041-escalation-workflow, which landed 2026-08-16**; the free-text sibling at `:570` `question_answered(question_id, answer_text)` | US1 — the closest precedent: buffered, not validated at receipt, because validating against state the workflow may not have written yet drops the fastest presses |
| Signal name constants live beside the sender, not the workflow | `factory/notify/service.py:86` `SIGNAL_NAME = "escalation_resolved"`, `:95` `QUESTION_SIGNAL_NAME` | US1 — where the new constant belongs |
| The CLI's signal verbs and their plumbing | `factory/cli/nouns/build.py:90-92` (`PAUSE_SIGNAL`/`RESUME_SIGNAL`/`KILL_SIGNAL`), sent via `_send_signal` at `:396`, `:401`, `:414` | US1 — the operator's entry point is a new verb here |
| The ladder that decides a node is out of road | `factory/verify/ladder.py:63` `next_action(history, config, *, escalations)`; `_TERMINAL_ACTIONS` in `workflow.py` | US1 — read this to know "exhausted"; do not redefine it |
| The verification record write | `factory/verify/store.py:328` (`INSERT INTO verification_results`), columns in `_RESULT_COLUMNS` at `:308` | US1 — provenance is a new column on this row |
| The attempt loop and where a node's result is produced | the attempt loop in `workflow.py` — a 2,557-line file; locate it by `next_action` rather than by line (evidence list, the `while True` attempt bracket, `next_action` call at `:1476`) | US1 — the completion path rejoins here |
| The recurrence machine — a durable count with first/last seen | `factory/doctor/store.py:112` `report(conn, finding, *, seen_at)` and its `occurrences = findings.occurrences + 1` upsert | US3 — the counting shape to copy, including the trap below |
| The landed attestation reader | `factory/workgraph/landed.py:254` `_attesting_commit`, and the `state: landed` frontmatter contract at `:102-110` | US2 — where the attestation's meaning is defined |
| Requested-by record, verbatim | cross-session memory `fail-out-escape-hatch`, and this spec's frontmatter | All three — Bryan's three conditions are binding, not preferences |

## Traps

### Trap 1 — this is the feature that can quietly end the factory

Every other spec in this corpus makes the factory build more of itself. This one
lets something else build it. `CLAUDE.md`'s first line and D-024 both claim no
production code here is written by a human; this is the sanctioned exception,
and a sanctioned exception with no friction becomes the default path.

The plausible wrong implementation is the *convenient* one: a signal that works
on any node, provenance that defaults to something sensible, a count nobody
surfaces. Each of those is individually reasonable and together they produce a
factory that is quietly hand-built. FR-002, FR-003 and FR-005 exist to make the
hatch deliberately awkward. **If a change makes this feature easier to reach,
that is a reason to reject it, not to ship it.**

### Trap 2 — provenance cannot ship one merge later

US1 must land the provenance record with the mechanism. The tempting split is
"mechanism now, marking in US2" — that is why US2 covers the *surfaces*
(status, trailer, PR body, attestation) and not the *record*. Between those two
merges there would be a version of ergane that lands human-written code and
stores nothing saying so, and any node completed in that window is
indistinguishable from agent work forever after. There is no backfill: the
information is not recoverable from the diff.

### Trap 3 — do not let anything automatic reach the signal

FR-003 is a structural requirement, not a behavioural one, and SC-003 is graded
by grep. The ladder's exhaustion path, the recovery cycle, the attempt timeout
and escalation expiry must all continue to fail or escalate exactly as today.

The reason is concrete and recent. On 2026-08-11, 032/us1 burned four attempts
because its story was self-contradictory. An automatic hatch would have fired on
attempt two, landed operator-written code, and left the contradictory story text
in place for the *next* spec to hit. The four expensive failures are what
surfaced the defect. A rescue that hides the signal is worse than the failure it
prevents.

### Trap 4 — the operator supplies authorship, never a verdict

The completion path rejoins the normal flow *before* verification, not after.
Gates run, the judge scores, the merge queue re-tests the speculative merge. It
must be possible — and there must be a test proving it — for externally-supplied
work to **fail**. If your implementation makes external completion imply PASS,
you have built a way to merge unverified code and the blast radius is the whole
repository.

### Trap 5 — a re-report overwrites, and an inflated count is worse than none

`factory/doctor/store.py:112`'s upsert does `occurrences = findings.occurrences
+ 1` **and** replaces `summary`, `refs`, `notes`. Copy the increment, but know
what it costs: on 2026-08-12 the operator ran one batch twice and turned two
one-off findings into false recurrences, which had to be corrected by hand in
SQL. This count is the evidence for "are we bailing out more often", so a
double-count is not cosmetic — it invents a trend. Make the write idempotent per
(spec, node, attempt), not per call.

### Trap 6 — zero must be measured, not inferred

FR-008 is easy to under-build. "No rows" and "the counter never ran" look
identical from the outside, and the number this feature exists to drive to zero
is exactly the number a broken counter also reports. The surface must be able to
say "0, and I checked" — and it should say the target is zero, because a bare
number means nothing to whoever reads it next.

### Trap 7 — no test may touch the live evidence store

`hardening/test-suite-writes-to-the-live-evidence-store` is open and this
epic's suite runs on the worker host. Every new test builds its stores under
`tmp_path`, exports nothing, and reads nothing from `.factory/`.

## Approach

### US1 — the signal, the guard, the record

1. Add `EXTERNAL_COMPLETION_SIGNAL = "complete_node_externally"` beside the
   existing constants in `factory/notify/service.py:86-95`, and the signal
   handler beside its siblings in `workflow.py` (after `:537`). Payload:
   `(node_id, branch, provenance)`. Buffer it the way `escalation_resolved`
   buffers into `_resolutions` — receipt validates nothing.
2. Read the buffer where the node's ladder outcome is decided (`workflow.py`
   near the `next_action` call at `:1476`). The guard is the whole point: accept
   only when the ladder is exhausted for that node; otherwise record a refusal
   and leave the node alone (FR-002). Do not invent a new notion of exhausted —
   read the one `factory/verify/ladder.py:63` already computes.
3. On acceptance, the node's result is the named branch. Add a `provenance`
   column to `verification_results` (`factory/verify/store.py:308`,
   `_RESULT_COLUMNS`), non-null on this path, and write the record before the
   node proceeds.
4. Rejoin the normal path at VERIFYING so gates, judge, PR and queue all run
   unchanged (trap 4). Nothing about this path grants a pass.
5. Add the CLI verb beside `build.py:508-513`'s siblings. It should require the
   provenance argument rather than defaulting it — the friction is deliberate
   (trap 1).

### US2 — the four surfaces

Dispatches after US1 has **merged**.

1. `ergane build status`: the node's row states external completion beside its
   state, with no flag needed to see it.
2. The landing commit gains a provenance trailer, so `git log` and any
   trailer-reading tool sees it without consulting the factory's stores.
3. The PR body states the work was completed externally and that the node's
   ladder was exhausted — the eligibility is part of the record.
4. The spec's `state: landed` attestation states the spec contains
   externally-completed work. `factory/workgraph/landed.py:102-110` and `:254`
   define what an attestation means today; this extends that meaning rather than
   adding a parallel one.
5. Agent-completed nodes carry none of these (FR-006). A marking that fires on
   everything carries no information.

### US3 — the count

Dispatches after US1 has **merged**; independent of US2.

1. A durable counter keyed by (spec, node) carrying provenance and timestamp,
   idempotent per completion (trap 5).
2. A read surface reporting the total and the per-spec breakdown, and an
   explicit `0` for a corpus that has never used the hatch (trap 6, FR-008).
3. The surface states the target is zero. This is the one place the feature
   argues against its own use, and that is intentional.

## Complexity Tracking

| Thing | Why it is not simpler |
| --- | --- |
| A guard on ladder exhaustion rather than "any node" | Without it the hatch is reachable at any moment and becomes the fast path; FR-002 is most of what keeps this feature honest. |
| Provenance in US1 rather than US2 | A merge window where ergane lands human code and records nothing saying so is unrecoverable — the information is not in the diff (trap 2). |
| Four surfaces rather than one column | Each answers a different reader: the operator (status), the historian (trailer), the reviewer (PR), the auditor (attestation). A database column serves none of them at the moment they ask. |
| A count, for a feature meant to be rare | Rare things are exactly the ones memory gets wrong. The target is zero, and a target you cannot measure is a wish. |
| Three stories | US1 is safety-critical and irreducible; US2 and US3 are additive and independent, so neither should gate the other. |

## Verification

`uv run pytest -q` green in the worktree, clean env, never with the operator
environment exported (trap 7).

Two checks beyond the suite, both graded by inspection rather than assertion:

- **SC-003 is a grep.** There must be no call path from ladder exhaustion,
  recovery, timeout or escalation expiry to the completion signal. State in the
  PR body what you grepped for.
- **Trap 4 needs a test that fails.** Externally-supplied work that breaks the
  gates must fail the node, demonstrated, not asserted. If every test in this
  spec passes on work that was never verified, the feature is a merge bypass
  wearing a provenance field.

## Added at the 2026-08-16 re-verification

Re-read against `851e0bf`. **Every anchor in the table above had drifted**, and
one had moved out of the file entirely — the corrections are applied in place.
The structural one is worth stating on its own, because it changes what you copy:

**`escalation_resolved` is no longer in `factory/workgraph/workflow.py`.**
041-escalation-workflow landed on 2026-08-16 and moved it to
`factory/escalation/workflow.py:246`. The epic workflow now defines exactly three
signals — `pause_epic` (`:514`), `resume_epic` (`:527`), `kill_epic` (`:532`).
So the "signal carrying operator payload" pattern this plan tells you to copy
lives in a **different module** from the three no-payload signals, and you must
decide which neighbourhood `complete_node_externally` belongs in rather than
assuming they are still siblings. `factory/workgraph/workflow.py` is now 2,557
lines; locate the attempt loop by `next_action` rather than by line number.

**One question this spec should answer before it dispatches, and does not.**
This session ran an "eject mode" in which the operator session dispatched
implementer agents by hand — worktrees, real boundary gates, a real judge, real
merge-queue landings — because the factory's own model backend was unavailable.
Sixty-plus commits landed that way on 2026-08-16. That is **not** what this spec
counts, and the distinction is sharp enough to write down: 035 counts work whose
*code was written by the operator*. Eject mode changed who **orchestrated** the
agents, not who **wrote** the code — every line still came from a model, through
the same gates, judged the same way. A future reader will ask; answer them here
rather than letting them re-derive it.

## Instrument traps carried forward from 2026-08-16

**Purge `__pycache__` between mutants**, or run under `PYTHONDONTWRITEBYTECODE=1`.
CPython validates a cached `.pyc` on `(mtime-in-whole-seconds, size)` only, so two
same-size mutants written inside one wall-clock second make the second run execute
the *first* mutant's bytecode. It fails toward green and reproduces stably.

**Quote `passed` and `skipped`, never the warning count** — a warm cache
suppresses compile-time warnings. Baseline skips were re-measured at 47 on this
host on 2026-08-17 (the 3 beyond the old 44 are `test_live_capacity` guards
skipping on an unregistered namespace); measure your own baseline at your base
commit before writing anything, and a skip beyond it is a hidden test you must
declare.

**Measure exit codes without a pipe.** `cmd | head; echo $?` reports the pipe's
status, not the command's.

**Assert against the store's state, not a call log.** This story writes a
`provenance` column and increments a durable count. "We called `report`" is a
claim about your own code; "the row reads `provenance=external` and the count is
2" is a claim about the world. Only the second can catch the defect this spec
exists to prevent — a fail-out that quietly does not get counted.
