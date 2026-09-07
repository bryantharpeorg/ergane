# 127-US3 — the verb's answer, beside the journalctl line

Committed evidence for epic 127's T022: ONE run of `ergane build why`, pasted,
beside the `journalctl` line that was previously the only place that answer
existed. Every line is printed output; nothing is described that was not read.

## How this was produced

A real target clone with a real bare `origin` under `/tmp` (scratch, outside
the worktree), the factory's own `ensure` and `push_branch` doing the work: the
first push landed a tip on origin, the branch was reset one commit and rebuilt
with different work (the ancestry a re-dispatch after a kill has), and the
second push was refused non-fast-forward. `open_landing_pr` raised what the
real activity raises — `ApplicationError(str(exc), type=LANDING_REF_CONFLICT,
non_retryable=True) from exc` — the node paged its operator, the answer was
KILL, and the archive-and-clear ran with a report to make. The epic ended
KILLED under workflow id `epic-why-evidence-final3` (a live Temporal server on
`localhost:7233`, a real worker registered on its task queue), and `ergane
build why` was then executed as a real CLI subprocess against that execution —
same process shape the operator runs.

The verification row the chain quotes was written to a real evidence store with
the factory's own `compose_result` and `upsert_result`: gates FAIL, judge
RETRY — the shape of a node whose suite died on its way to a landing.

## The journalctl line (what you used to have to go and find)

The worker logs the exception the interpreter swallowed. That was the whole
diagnosis, and it was on no ergane surface:

```text
temporalio.exceptions.ApplicationError: LANDING_REF_CONFLICT: push of
'factory/127-us3-evidence-demo/us1' to origin failed (repo
/tmp/127-us3-evidence/clean): To /tmp/127-us3-evidence/origin.git
 ! [rejected]        factory/127-us3-evidence-demo/us1 ->
factory/127-us3-evidence-demo/us1 (non-fast-forward)
error: failed to push some refs to '/tmp/127-us3-evidence/origin.git'
hint: Updates were rejected because a pushed branch tip is behind its remote
```

## The run (US3-S1, FR-009) — one command, no journal

```text
$ ergane build why why-evidence-final3 us1
epic why-evidence-final3 — why
us1:
  attempt 1: FAIL (PHASE, verified at 2026-09-06T10:03:00Z)
      gate test: FAIL — exit 1
        gate output (last 20 lines):
          [... 22 lines truncated ...]
          FAILED tests/test_37.py::test_thing_37 - assert 2 == 3
          FAILED tests/test_38.py::test_thing_38 - assert 2 == 3
          FAILED tests/test_39.py::test_thing_39 - assert 2 == 3
          E   AssertionError: the landing's push was refused
          1 failed, 412 passed in 214.60s
    judge: RETRY
    judge feedback:
      The scenario the landing needs was never exercised; the diff deletes
      the acceptance check rather than satisfying it.
  transcript: /tmp/127-us3-evidence/factory-root/transcripts/why-evidence-final3/us1/attempt-1
  ending: WorktreeError: push of 'factory/127-us3-evidence-demo/us1' to origin failed (repo /tmp/127-us3-evidence/clean): To /tmp/127-us3-evidence/origin.git
 ! [rejected]        factory/127-us3-evidence-demo/us1 -> factory/127-us3-evidence-demo/us1 (non-fast-forward)
error: failed to push some refs to '/tmp/127-us3-evidence/origin.git'
hint: Updates were rejected because a pushed branch tip is behind its remote
hint: counterpart. If you want to integrate the remote changes, use 'git pull'
hint: before pushing again.
hint: See the 'Note about fast-forwards' in 'git push --help' for details.
  housekeeping: archived branch; kept origin branch factory/127-us3-evidence-demo/us1 at abcdef123456: no archive ref of this node holds that commit, so nothing else carries its content (FR-002)
```

## What the run shows, against the requirement

- **the last verdict** — `attempt 1: FAIL (PHASE …)`, from `node_history`
  (the verification store).
- **the failing gate and a bounded tail** — `gate test: FAIL — exit 1`, then
  the last `EVIDENCE_TAIL_LINES` lines with `[... 22 lines truncated ...]`
  naming the drop. The stored `output_tail` was 42 lines; the verb printed 20
  of them, not the field whole — up to 32 KiB had it been noisy.
- **the judge feedback, where one exists** — `judge: RETRY` and its feedback,
  from the same row.
- **the queue outcomes and rejection cause the landing recorded** — carried on
  the query answer for a node whose landing got as far as the queue; this one
  died at the push, before a landing existed, so the ending carries the
  terminal reason and the housekeeping report instead.
- **the transcript directory of the latest attempt** — composed from the
  declared factory root, printed and never opened.
- **the terminal reason** — git's own refusal, under `ending:`. The
  housekeeping report is beside it as its own labelled line, which is US1's
  field reaching this verb through the query.

The one command replaces the filesystem walk and the journal read. Nothing
here needed `journalctl`; the walk the finding was filed on is gone.