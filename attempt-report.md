# Attempt 1 — US1: The housekeeping report stops overwriting the cause

## What changed

Six commits, tests first — T001–T004 committed observed-red, then T005/T006
(the suite made able to reach the code it changes, also committed red on the
missing field), then the implementation, then the evidence:

- `tests/test_127_us1_reason_survives_housekeeping.py` (new) — the four rows of
  the spec's truth table, pinned over both overwrite paths: the real-git
  refusal (T001, record half observed while the page is open), the
  `_escalate_ref_conflict` control (T002, trap 1 — the path the findings file
  does not name), the empty-report control (T003, trap 4), the never-promote
  control through `_close_out` (T004), and the same control with the *real*
  archive activity against a real bare origin.
- `tests/test_interpreter.py` — the archive stub can return a non-empty,
  per-node-scripted report (`script_archive_report`), and a test drives one
  through the ladder-exhaustion kill (T005, trap 2). Before this the stub
  answered `[]` unconditionally, so `if report:` had never been true under the
  whole interpreter suite and neither overwrite site had ever executed there.
- `tests/test_126_us2_kill_archives_remote.py` — the committed assertions that
  read the branch name and pushed sha out of `terminal_reason` are repointed at
  the new field (T006, trap 3: they were the defect written down and made
  green), and the empty-report comment is extended, not rewritten — it was
  true and stays true, and now names what both fields do in that case.
- `factory/workgraph/models.py` — `NodeRecord.housekeeping_report`, documented
  in the style of the sibling `attempt_note`: the docstring is the deliverable,
  recording why it is not `terminal_reason` (T007).
- `factory/workgraph/workflow.py` — `NodeStatus.housekeeping_report` beside its
  `terminal_reason`, populated from the record in the `epic_status` answer
  (T008); both overwrite sites — `_close_out` and
  `_archive_and_clear_remote_branch` — write the report to the new field with
  the `if report:` guard untouched, and the store of git's diagnosis at the
  ref-conflict site is untouched (T009).
- `docs/127-us1-kill-record-evidence.md` — T010: the terminal record from a
  real kill on a scratch remote, pasted. Real clone, real bare origin, real
  non-fast-forward refusal, the factory's own `ensure`/`push_branch`/
  `_failure_detail`/`archive_and_clear_remote_branch` doing the work; git's
  refusal visible in `terminal_reason` and the archive report beside it.

## How the scenarios are covered

- **US1-S1 (T001)** — a node whose push git refused non-fast-forward, whose
  remote branch was then archived and cleared: `terminal_reason` carries git's
  diagnosis (asserted against the real rejection line git wrote), the report is
  readable from `housekeeping_report` on the same record, and the final
  `epic_status` answer carries both. The record half is additionally observed
  mid-flight — the cause is on the record before any housekeeping ran, which is
  the fact the overwrite used to destroy.
- **US1-S2 (T003)** — a node ended with an empty housekeeping report:
  `terminal_reason` is unchanged from today's value (git's refusal, intact) and
  the new field is empty. Most nodes are this node; the guard that protects
  them is untouched.
- **US1-S3 (T004, T005)** — a node ended with a housekeeping report and no
  terminal reason: `terminal_reason` stays `None` and the report is in the new
  field — asserted through `_close_out` with a scripted report, through the
  interpreter with the newly-scriptable stub, and with the real activity
  against a real origin. A report is not a cause and is never promoted into
  one.
- **US1-S4 (T002)** — the kill path inside `_escalate_ref_conflict`, which
  reaches `_archive_and_clear_remote_branch` and never `_close_out`: the same
  separation holds, with a non-empty report, proving both overwrite sites were
  repaired and not just the one the finding names.

## Field name

`housekeeping_report`. The spec and tasks say only "the new field", so the name
was chosen to match the sibling it was modelled on: `attempt_note`, which
records what an attempt *was* beside the reason a node *ended*. The same name
is carried on `NodeRecord`, `NodeStatus` and the query population, and used by
US2's renderer work when it lands.

## Diff budget

The story's diff is code + tests + one pasted-evidence document, all trimmed to
what carries the answer; no gate tail is pasted. Well under the 64 KiB bound.

## Gates

`uv run pytest -q` (the one declared gate): 5700 passed, 58 skipped, green
after the tests, green again on the final state. The red states were committed
at `fd0e4ce` and `b05c4b2` before the implementation landed at `c0d9e1f`.