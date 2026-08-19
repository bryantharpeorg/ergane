# Implementation Plan: a message is a decision, not a log line

**Spec**: `specs/066-a-message-is-a-decision-not-a-log-line/spec.md`

## What already exists, and where

Read against the tree on 2026-08-19. Check each anchor before relying on it.

- `factory/notify/messages.py` — every operator-facing string is composed here.
  The composers this spec changes:
  - `:257` `manual_intervention_notice`
  - `:273` `roadmap_failure_notice(roadmap_id, failure_text, count)` — **the one
    that produced every message in the operator's screenshot.** Its docstring
    says it "carries the failure text verbatim", which is exactly the decision
    being reversed.
  - `:288` `roadmap_recovery_notice(roadmap_id, prior_count)` — FR-013.
  - `:302` `escalation_message` — **the model.** Its final line, `"No answer by
    {expires_at} applies the default: KILL the node."`, is the sentence US2
    generalises. Do not regress it.
  - `:337` `question_message`, `:355` `resolution_notice`.
  - `:314` `_render_check_evidence` and `:330` `_last_failing_test_line` — prior
    art for turning raw output into a single useful line. Read these before
    inventing a new approach; the pattern is already here.
- `factory/roadmap/workflow.py:139` `_should_notify_failure` — geometric
  throttle on the consecutive count, powers of three. **The throttle is correct;
  it was defeated because the count keys on text that differs per spec.** FR-011
  changes what it keys on, not the throttle.
- `factory/roadmap/workflow.py:955` `_report_roadmap_failure` — records to the
  store first, then sends. FR-004 depends on that ordering being kept.
- `factory/roadmap/workflow.py:1281` — the per-spec call site inside the drift
  resolver. This is where 63 messages came from: one call per spec, each with a
  different `failure_text`.
- `factory/verify/models.py` / the `roadmap_failures` table in
  `.ergane/verification.db` — where the verbatim text already lives durably.
  FR-004 is mostly a matter of not removing this.
- `factory/controlplane/config.py` `_SECRET_PATTERNS` — already used by
  `tests/test_readme.py` to refuse secret-shaped strings. The edge case wants
  the notice path to use the same patterns.
- `tests/page_holds_true.py` — `extract_commands`, `run_help`, `split_argv`,
  `verbs_of`. **FR-009 must reuse these, not reimplement them.** 063/US1 is
  adding near-miss detection to the same helper; if 063 has landed, re-read it.
- `tests/test_roadmap_failure_notifications.py` — where US3's assertions belong.

## Traps

**1. The screenshot is the acceptance test.** Four real messages, quoted in the
spec's frontmatter. If your diff does not visibly improve those four, it has not
done the job, whatever the unit tests say. SC-001 requires the before-and-after
of all four in the diff.

**2. Do not delete the evidence to clean up the page.** FR-004. The verbatim
text is written to `roadmap_failures` *before* any send, deliberately, so a
notifier that is down loses the message and not the fact. Keep that ordering.
The phone gets the decision; the store keeps the truth.

**3. A fallback that prints the raw text has changed nothing.** FR-003. The
tempting shape is a lookup table of known failures with `else: return
failure_text`. That preserves today's behaviour for every failure nobody has
seen yet — which is every failure that will actually surprise an operator.
The generic path must still state impact and options.

**4. The escalation message is the model, not a victim.** `escalation_message`
already states its default-on-silence. US2 generalises that sentence to the
other composers. If your diff makes the escalation *worse* — shorter, vaguer,
restructured to fit a new abstraction — you have inverted the story.

**5. Options are actions, not descriptions.** US2-S1. "The workflow is in a
failed state" is a description. "Terminate the run so a fresh one starts, or
pause the schedule" is a pair of options. The test for a line is whether an
operator could do it.

**6. Any command a message names must resolve.** FR-009 and US2-S5. Reuse
`tests/page_holds_true.py`; a second command sweep is how the two drift apart
with both suites green — 054's trap 3, and 063 is currently reinforcing the same
helper.

**7. Throttling keys on the cause.** FR-011. `_should_notify_failure` is fine.
What broke is that `drift_for_spec(020-...) failed: <same git error>` and
`drift_for_spec(021-...) failed: <same git error>` are different strings, so the
consecutive count reset to one 63 times. Key the count on something stable
across specs — the underlying error, not the rendered sentence.

**8. Collapsing distinct causes is worse than repeating one.** US3-S3. An
over-eager dedupe that hides a second, different fault behind the first is a
regression, and it is the failure mode a naive hash-of-everything produces.

**9. Do not lengthen the heartbeat.** The edge case. `💚 ergane stack healthy`
has no decision in it and should stay one line. This spec is about messages that
ask something of the operator.

**10. Volume must go down, not up.** The Assumptions say it plainly. If a change
improves each message and produces more of them, it has failed the operator who
asked for this.

**11. The judge sees the diff and the criteria.** SC-001 through SC-004 need
committed evidence — paste the rendered before-and-after strings into the diff
rather than describing them.

## Sizing

Three small stories, all in one module plus one call site.

US1 is the shape change: a notice becomes structured (impact, options, detail)
rather than a formatted string. US2 fills in two fields for every composer. US3
is a change to what the failure count keys on, plus a fold at the call site.

The risk is not difficulty, it is taste. There is no gate that can tell a
helpful sentence from an unhelpful one, so the operator's own read of SC-002 is
the real acceptance test, and the four screenshot messages are the fixture that
makes that judgement concrete rather than abstract.

## Verification the operator will run, independent of the gate

- **Read the four.** Render the messages from the 2026-08-19 screenshot with the
  new composers and read them as the person holding the phone at 4:05 PM. Could
  he have acted?
- **Hand one to a stranger.** SC-002. Someone who does not maintain Ergane
  should be able to say what stopped and what the choices are.
- **Replay the flood.** Drive the fetch fault across a full corpus pass and
  count the messages. 63 before; the target is one.
- **Count a normal day.** Total message volume before and after. If it rose,
  the spec failed regardless of what the tests say.
