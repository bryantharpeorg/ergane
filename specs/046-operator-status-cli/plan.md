# Plan: 046-operator-status-cli

Refined against the tree at `ed8f24c` on 2026-08-15 (011/us1 and us2 landed;
043 landed in full). Every line anchor below was checked by hand that morning;
grep the construct rather than trusting the number if the tree has moved.

Findings this spec closes or touches:

| Finding | Sev | Disposition |
| --- | --- | --- |
| `cli/roadmap-verbs-cannot-see-schedule-driven-runs` | warning | Closed by US2 |
| `cli/landed-defaults-to-the-wrong-branch` | warning | **Not this spec's** — its `landed` leg is already fixed in-tree (verified 2026-08-15: `ergane spec landed` with no flag printed `default branch: ergane-buildout` from `factory.yaml:43`, landed by 020-US1); its other two legs are tangled in the operator's pending 016 decision. Recorded here so nobody re-fixes the fixed leg or pre-empts the decision. |

Two paper cuts named in the requesting conversation turned out to already be
fixed, verified live the same hour: `ergane build kill --yes` exists
(`factory/cli/nouns/build.py:417-420` confirms unless `--yes`, flag at
`:708`), and `spec landed`'s manifest default per the table above. They are
out of scope, with the evidence, so this spec stays three small stories.

## Reuse inventory

| What | Where | Used by |
| --- | --- | --- |
| The epic-id prefix seam | `factory/cli/nouns/build.py:91-93` — `workflow_id()` prepends `epic-` unconditionally; every build verb routes through it | US3 — normalize here and only here |
| `build status`'s query + human view | `factory/cli/nouns/build.py` — grep `status_command`; `--json` prints the query verbatim | US1 — per-epic story tables are this, reused not re-queried differently |
| The roadmap workflow id | `factory/roadmap/workflow.py:162` — `roadmap_workflow_id(specs_root)` → `roadmap-<root>`; schedule runs append `-<timestamp>` | US2 — the prefix the discovery matches |
| The verbs that cannot see schedules | `factory/cli/roadmap.py:163-164` (id construction), `:210-218` (`status` dials the bare id and refuses) | US2 |
| Workflow listing precedent | `factory/activities/roadmap_activities.py:448` — `list_workflows` by id prefix | US1, US2 |
| Spec states, readiness, blockers | `factory/roadmap/models.py:26` (readiness definition), rendering at `factory/roadmap/cli.py:47-122` | US1 — FR-008 says reuse this reader; `spec list`'s output is the proof of its shape |
| Verification timestamps for pace | `factory/verify/store.py:245` (`_RESULT_COLUMNS`, includes `started_at`/`finished_at`), `:275` (`_SELECT_RESULT_SQL`) | US1 |
| The read path to the store | `resolve_factory_root()` at `factory/workgraph/worktree.py:135` — **creates the directory as a side effect at `:180`** | US1 — trap 1 |
| Transport-refusal conventions | `factory/cli/errors.py` — grep `EXIT_TRANSPORT`; 043-US3's closed-port test is the precedent shape | US1's degraded mode, US2's refusals |
| Schedule API | none in this repository — `temporalio` `Client.list_schedules` / `get_schedule_handle`; the live schedule (`ergane-roadmap`) was operator-created | US2 — see trap 3 |

## Route choices left to the implementer

**Where `ergane status` gets its epic list.** Two candidates: list running
`EpicWorkflow` executions (the `:448` precedent) and query each, or accept the
roadmap run's own view when one exists. Prefer listing executions — it works
when the roadmap is paused with an epic still running, which is exactly the
floor an operator most wants to see. Say which you chose.

**What "recent landings" means, if you render them.** The verification store
has PASS rows; git has landing commits; `spec landed` has attributions. FR-001
does not demand a landings section — add it only if one of those sources
yields it without a new mechanism, and name the source in the commit.

## Traps

### Trap 1 — the resolver you must call is not read-only, and FR-002 says status is

`resolve_factory_root()` ends by creating the runtime root when neither root
exists (`worktree.py:180`). A status command that runs on a fresh checkout and
leaves a `.ergane/` behind has violated FR-002 and US1-S6 — and 043's trap 2
already recorded the general form: every test that touches the resolver must
`monkeypatch.chdir` into tmp first. Resolve the path without triggering the
mkdir (read the resolution, do not demand the directory), or open the store
only when the file already exists. SC-003 asserts the filesystem afterwards.

### Trap 2 — pausing the run is a lie when a schedule owns dispatch

The overnight operational record is the reason FR-006 says "the thing that
owns dispatch": a schedule-driven roadmap pauses at the *schedule*
(`temporal schedule toggle` was the fallback that worked), because a paused or
terminated run is replaced at the next tick. A `pause` that signals the
current run reports success and dispatch continues — worse than the current
refusal, because it lies. US2-S2 reads the schedule back rather than trusting
the verb's own report.

### Trap 3 — the schedule id is not derivable, so discovery must be honest

The live schedule id is `ergane-roadmap`, chosen by an operator's hand;
nothing maps `specs` → that string. Discovery is: list schedules, match the
one whose action starts workflows with the `roadmap_workflow_id(root)` prefix
(`factory/roadmap/workflow.py:162`). If listing yields nothing, fall through
to the newest timestamped run, then the bare id — and when all three miss,
FR-007's refusal names all three, in the order tried. Do not hardcode
`ergane-roadmap` anywhere, including tests.

### Trap 4 — do not re-implement "ready"

`factory/roadmap/models.py:26` defines readiness: `state: ready` AND every
`depends_on_landed` edge satisfied. The rendering at `roadmap/cli.py:47-122`
is what `spec list` prints. FR-008 exists because a second readiness
computation drifts — the queue section of `ergane status` calls the existing
reader and formats, nothing more.

### Trap 5 — pace is measurement, and the store only measures verification

`started_at`/`finished_at` bracket one verification, not one story:
dispatch-to-verification-start and merge-queue time are not in the store.
Present attempt wall-times as exactly that — "attempt N verified in Xm" — and
the remaining-story count beside them. The moment the output contains an
arrival time, FR-003 is violated and the operator starts trusting a number the
data cannot support. (The requesting conversation's ETA tables were operator
judgment layered on these same timestamps; the verb supplies the layer that is
fact.)

### Trap 6 — degraded is a mode, not an error

US1-S4: with Temporal down, the spec sections still render. The temptation is
to let the first transport error abort the command — but the operator reaching
for `ergane status` during an outage is the operator who most needs the
file-derived half. Catch the transport failure where it occurs, render the
note with the address (the `EXIT_TRANSPORT` conventions in
`factory/cli/errors.py` name the shape), and keep going. Test against a
closed port (`TEMPORAL_ADDRESS=127.0.0.1:1`), the 043-US3 precedent.

### Trap 7 — US3 normalizes at the seam, not at the callers

`workflow_id()` (`build.py:91-93`) is the one place `epic-` is prepended. Strip
a redundant prefix there — nowhere else — so every verb inherits the fix and
US3-S1's every-verb test is one parametrization. Do not normalize inside
individual verbs, and do not touch how *failures* resolve: an id that matches
neither form fails with today's error (US3-S2), and the both-candidates error
text (US3-S3) comes from this same seam.

### Trap 8 — anchors rot

The tree took four landings yesterday and two this morning. Grep the
construct — `workflow_id`, `roadmap_workflow_id`, `list_workflows`,
`_RESULT_COLUMNS` — and when a citation disagrees with the tree, the tree
wins and you say so in the commit.

## Approach

### US2 — discovery first (US1 consumes it)

1. One resolution helper: bare workflow → owning schedule → newest
   timestamped run, returning what it found and how (trap 3).
2. `status` renders the newest run plus the schedule's paused state;
   `pause`/`resume` act on the schedule when one owns dispatch (trap 2), else
   the bare workflow exactly as today (US2-S4 pins byte-parity).
3. The nothing-found refusal names all three lookups (FR-007).

### US1 — the join

1. Sections in order: disposition (US2's helper), running epics
   (`list_workflows` + the existing per-epic query), queue and drafts (the
   roadmap reader, trap 4), pace (trap 5).
2. Read-only throughout (trap 1); degraded mode per trap 6; `--json` is the
   same document the human view renders from (FR-005).

### US3 — the prefix seam

1. Normalize in `workflow_id()` (trap 7); parametrized test across every
   verb that calls it; the two error shapes per US3-S2/S3.

## Verification the operator will run, independent of the gate

- `ergane status` on the live floor, eyeballed against `temporal workflow
  list` and `spec list`.
- `ergane roadmap status specs` with the schedule active — the exact
  invocation that failed on 2026-08-15 — and then `pause`/`resume`, reading
  the schedule state back with `temporal schedule describe` between each.
- `ergane status` from a scratch checkout with no runtime root, then `ls -la`
  for anything created.
