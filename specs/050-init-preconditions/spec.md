---
state: landed
fixes:
  - hardening/mutating-a-production-safety-guard-escapes-the-sandbox
# Attested landed 2026-08-17 by an operator session, after `ergane spec landed
# specs/050-init-preconditions --default-branch ergane-buildout` observed all
# three stories in git: US1 8cff22f8f807, US2 deff9d0d7aa8, US3 a6f335815905.
# US1 landed 2026-08-16 under the eject-mode method (operator-run bwrap gate and
# judge). US2 and US3 were factory-dispatched overnight via `ergane build start`
# on the remainder graph (workgraph-remainder.json, committed here), both first
# attempt, gates and judge inside the epic workflow, landed by the merge queue
# as PRs #164 and #161.
# Drafted 2026-08-16 by an operator session, from a critical finding the
# operator session filed against itself an hour earlier:
# `install/init-creates-a-live-schedule-into-a-control-plane-it-then-reports-missing`.
#
# The finding was not reasoned into existence. It was produced by walking the
# portability path as a new user would: `uv build --wheel`, install the wheel
# into a clean venv, `git init` a fresh repository, and run `ergane init` under
# `env -i` with every Ergane variable unset. Accepting the interview defaults
# created a live recurring schedule on the operator's *production* Temporal
# namespace, pointed at a scratch temporary directory that no longer exists.
# That schedule had to be paused by hand, and its deletion needed the operator.
#
# So the reproduction in this spec is a transcript, not a hypothesis, and the
# blast radius is measured rather than imagined: the command that did it is the
# one the runbook tells a new user to type first.
#
# Three stories, and the split is along *what kind of thing goes wrong*, not
# along the code. US1 stops the unsafe act. US2 fixes the ordering that hid it.
# US3 closes the collision the slug default opens on any shared server. Each is
# independently valuable — US1 alone removes the production incident — and each
# is decidable from its own diff.
#
# Deliberately NOT in scope: changing what `ergane init` exits with. That was
# checked at drafting time and is correct as built. `init.py:459-464` documents
# the choice — the scaffold and the registry entry genuinely did succeed, and
# `ergane init --check` (`:846`) is the door whose exit code is the readiness
# verdict. An operator session nearly filed that as a defect and the code
# answered it. It is recorded in Out of Scope so the next reader does not spend
# the same attention.
---

# Feature Specification: 050-init-preconditions

## Context

`ergane init` joins a git repository to Ergane. Almost everything it does is
scoped to that repository: it writes `ergane.yaml`, appends to `.gitignore`,
creates `.ergane/`, and adds a row to the operator's own registry. All of that
is local, reversible, and visible in the working tree.

One act is not. `factory/cli/init.py:438` calls `_schedule()`, which creates a
recurring Temporal schedule on a shared server. That is the only thing `init`
does whose blast radius extends past the repository being joined, and it is the
only thing `init` does that another person can observe.

It is also unconditional. `_schedule` (`init.py:529`) has exactly one failure
branch — a manifest that will not load — and otherwise goes straight to
`apply_schedule()`. There is no check that a control plane exists, no check
that anything could service the epics the schedule will start, and no
confirmation.

### What actually happened

Measured on 2026-08-16 at 3:24 PM CT, from the shipped wheel, under
`env -i HOME=<scratch> PATH=/usr/bin:/bin:<venv>/bin`:

```
schedule: created ergane-roadmap-repo — created, starting roadmap-specs every
  300s over /tmp/.../portab/repo/specs (note: LITELLM_PROXY_URL is unset, so
  child epics cannot issue keys)
...
  [FAIL] control_plane: the control plane could not be probed:
    ControlPlaneConfigError: .../config.toml: [config_missing] cannot be read
    (No such file or directory); run `ergane install` to create the
    control-plane config
```

Read those two lines together. The command created a job that will run every
five minutes forever, having already computed and printed the reason that job
cannot do its work, and then reported that the subsystem the job depends on
does not exist. Every fact needed to refuse was in hand before the act.

The severity is not the wasted schedule. It is that this is the **documented
first command a new user runs**, so the failure is not a corner case reachable
by a mistake — it is the happy path. A user with any reachable Temporal gets a
permanent failing job; on a shared server they get it in someone else's
namespace. It is the third appearance of stray schedules in one day and the
first that needs no test, no mutation, and no error to reach.

### Why this is not the morning's finding

Earlier the same day, five schedules
(`ergane-roadmap-{declared,beta,alpha,my-app,myapp}`) were found firing every
five minutes against pytest temporary directories. That root cause was a test
sandbox escape: a mutation replaced a `PYTEST_CURRENT_TEST` guard with `if
False:`, and the guard was the only thing keeping test runs off the production
namespace. The remedy there is to make the sandbox hold under mutation.

This is a different door into the same room, and no sandbox is involved. Fixing
one does not fix the other, which is why this is its own spec rather than a
story appended to that work.

## What a precondition means here

The distinction this spec turns on is between acts that are **local and
reversible** and acts that **publish state to shared infrastructure**. `init`
may always do the first; the entire interview, the scaffold and the registry
row stay available even on a machine with nothing else installed, and that
matters because being able to join a repository before standing up a control
plane is a real workflow.

The second kind needs a reason to believe it will work. Not a guarantee — the
control plane can always fail later — but the cheap, already-computed check
that it exists at all.

## User Scenarios & Testing

### User Story 1 - A schedule is never created into a control plane that is not there (Priority: P1)

As a new operator running `ergane init` on a fresh machine, I do not create a
recurring job on shared infrastructure that nothing can service. The scaffold,
the registry entry and the interview all still happen; the one act with reach
beyond my repository waits until the thing it depends on exists, and tells me
so in the words that name the fix.

**Why this priority**: it is the whole production incident. It is also the only
story here that must land before a second machine is provisioned, because the
first thing that machine would otherwise do is schedule work it cannot perform.

**Independent Test**: run the full init path against a control plane that
cannot be read and confirm no schedule was created; run it against one that can
and confirm the schedule is created exactly as it is today.

**Acceptance Scenarios**:

1. **Given** a repository being joined and a control-plane config that cannot
   be read, **When** `ergane init` runs to completion, **Then** no schedule is
   created — proven by a committed test asserting against the *schedule
   backend's state*, never against a call log — and the reported line names the
   control plane as the reason and `ergane install` as the remedy.
2. **Given** the same run, **When** the rest of init is inspected, **Then**
   `ergane.yaml`, the `.gitignore` entry, `.ergane/` and the registry row are
   all written exactly as they are today — the refusal is scoped to the one act
   that leaves the repository, proven by a committed test.
3. **Given** a readable control-plane config, **When** `ergane init` runs,
   **Then** the schedule is created and the reported line is byte-identical to
   today's for the same inputs — proven by a committed test, so this story
   cannot be satisfied by disabling scheduling.
4. **Given** the diff, **When** the precondition is deleted from the source,
   **Then** at least one committed test fails. The mutation belongs in the
   evidence file: a precondition with no test that dies when it is removed is
   the defect this spec exists to fix, wearing a different hat.
5. **Given** a control plane that is configured but unreachable at the moment
   init runs, **When** init runs, **Then** the schedule step reports a failure
   and raises nothing — FR-017's existing promise that this step never raises
   is preserved, and a committed test proves it. *Refusing* and *crashing* are
   different outcomes and only one of them is wanted.

---

### User Story 2 - Readiness is reported before the act that depends on it (Priority: P2)

As an operator reading `init`'s output, the checks that decide whether an act
is safe appear before that act, so the transcript reads as a decision rather
than as a confession. Today the control-plane failure is printed after the
schedule it should have prevented.

**Why this priority**: it is what made US1's defect survive being visible. The
information was on screen; it was on screen too late to mean anything. It is
P2 because US1 makes the outcome correct on its own — this makes it *legible*,
and legibility is what stops the next such act from being added below the line
again.

**Independent Test**: capture init's output for a run with a failing
precondition and assert the ordering of the two lines, not their presence.

**Acceptance Scenarios**:

1. **Given** a run whose control plane cannot be read, **When** the output is
   captured, **Then** the control-plane verdict appears *before* the schedule
   line — proven by a committed test comparing their positions in the captured
   output, not by asserting either line exists.
2. **Given** a run where everything passes, **When** the output is captured,
   **Then** it still ends with the readiness report as it does today, and the
   `next, run:` guidance still names the paths to commit — reordering a
   precondition must not reorder the operator's instructions.
3. **Given** the diff, **When** the checks are read, **Then** the readiness
   check is executed once per init run and its result reused, not run twice —
   proven by a committed test, because a probe that is cheap to repeat today is
   a network call tomorrow.

---

### User Story 3 - A schedule identity cannot collide with a stranger's (Priority: P3)

As an operator on a shared Temporal server, joining a repository whose
directory happens to be named the same as someone else's does not silently
adopt, overwrite or fight over their schedule.

**Why this priority**: it is a real hazard rather than a hypothetical one — the
slug defaults to the directory name, and the run that produced this spec
defaulted to the slug `repo`, which is precisely the name a scratch clone or a
tutorial checkout gets. It is P3 because a single-operator server, which is
every deployment today, cannot hit it.

**Independent Test**: apply a schedule for a slug whose id already exists and
was created for a different repository root, and confirm the outcome is a
refusal naming both roots rather than a reconcile.

**Acceptance Scenarios**:

1. **Given** an existing schedule under the id a new repository's slug would
   produce, and whose recorded repository root differs from the one being
   joined, **When** init reaches the schedule step, **Then** it refuses that
   step, names both roots, and leaves the existing schedule unmodified —
   proven by a committed test asserting the existing schedule's state is
   unchanged.
2. **Given** an existing schedule under that id whose recorded root is the
   *same* repository, **When** init runs again, **Then** it reconciles exactly
   as it does today — re-running init in a joined repository is a supported act
   and this story must not break it.
3. **Given** the diff, **When** the comparison is read, **Then** it is made
   against a fact recorded on the schedule itself rather than against anything
   read from the local filesystem — a check that consults only local state
   cannot see a stranger's repository at all, and would pass vacuously.

## Functional Requirements

- **FR-001**: `ergane init` MUST NOT create or modify a Temporal schedule when
  the control-plane configuration cannot be read.
- **FR-002**: The refusal MUST be reported as a failed *step*, not raised.
  `init.py`'s FR-017 contract that the schedule step never raises is preserved
  unchanged.
- **FR-003**: The refusal message MUST name the control plane as the cause and
  `ergane install` as the remedy, matching the vocabulary the readiness check
  already uses so an operator meets one phrasing rather than two.
- **FR-004**: Every local, repository-scoped act of `init` — the manifest, the
  `.gitignore` entry, the runtime root and the registry row — MUST be
  unaffected by the precondition.
- **FR-005**: When the control plane is readable, the schedule step's behaviour
  and its reported line MUST be unchanged from today for identical inputs.
- **FR-006**: The control-plane readability check MUST be evaluated once per
  `init` run and its result shared between the schedule precondition and the
  readiness report.
- **FR-007**: `init`'s output MUST present the control-plane verdict before the
  schedule step's line.
- **FR-008**: The schedule step MUST refuse when a schedule already exists
  under the derived id and is recorded against a different repository root, and
  MUST leave that schedule unmodified.
- **FR-009**: The identity comparison in FR-008 MUST be made against state
  recorded on the schedule, not against the local filesystem.
- **FR-010**: `ergane init` MUST NOT gain a flag that disables scheduling as
  the means of satisfying FR-001. The precondition is a fact about the
  environment, not an operator preference, and an opt-out would be the first
  thing a runbook told people to paste.

## Success Criteria

- **SC-001**: The exact reproduction recorded in this spec's Context — the
  shipped wheel, a clean venv, a fresh repository, `env -i` with no Ergane
  variables — creates no schedule, and the transcript is committed as evidence.
- **SC-002**: Deleting the precondition from the source turns at least one
  committed test red, recorded in the evidence file with the diff of the
  mutation and the failing test names.
- **SC-003**: On a host with a readable control plane, `ergane init` produces
  the same schedule and the same reported line it produces today.

## Out of Scope

- **`init`'s exit code.** Checked at drafting time and correct as built:
  `init.py:459-464` documents that the readiness verdict is reported rather
  than returned because the scaffold and registry entry did succeed, and
  `ergane init --check` (`:846`) returns `EXIT_OK if profile.passed else
  EXIT_USER`. Nothing here changes it.
- **The test-sandbox escape.** `hardening/mutating-a-production-safety-guard-escapes-the-sandbox`
  covers the other door onto the same namespace. Neither fix implies the other.
- **Which namespace a fresh install should use.** The `env -i` run resolved
  namespace `factory` and `localhost:7233` with nothing set, which is worth
  confirming as intended, but it is a question about install's defaults rather
  than about init's preconditions. Recorded here so it is not lost.
- **Deleting the schedule the reproduction created.** Done by hand; it is
  paused and awaiting an operator's `temporal schedule delete`.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-010]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-006, FR-007]
US3:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-008, FR-009]
```
