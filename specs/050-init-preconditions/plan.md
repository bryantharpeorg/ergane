# Implementation Plan: 050-init-preconditions

Refined against the tree at `c4bc570`. Every anchor below was read by hand at
that commit. Where an anchor moves before you dispatch, re-read it — a plan
citing a function that has since moved sends you hunting at the operator's
expense.

## What already exists, and where

| Thing | Where | What it does today |
| --- | --- | --- |
| The init command body | `factory/cli/init.py:435-468` | Interviews, scaffolds, registers, **schedules**, prints guidance, then runs readiness |
| The schedule step | `factory/cli/init.py:529-549` (`_schedule`) | Loads the manifest; on success calls `apply_schedule(desired)` unconditionally |
| The readiness report | `factory/cli/init.py:826-846` (`run_check`) | Prints each check, returns `EXIT_OK if profile.passed else EXIT_USER` |
| The control-plane probe | `factory/controlplane/` | Raises `ControlPlaneConfigError` with a `[config_missing]` code when `config.toml` cannot be read |
| Schedule application | `factory/roadmap/schedule.py` | `desired_for_repo`, `apply_schedule`, `format_step`, `schedule_id_for`, and the `ScheduleStep` / `FAILED` vocabulary |
| The init check facts | `factory/cli/init.py:713` (`_schedule_facts`) | Builds this repo's schedule facts as `InitFacts` kwargs |

Two facts make this cheaper than it looks:

- **`_schedule` already has a failure shape.** It returns
  `format_step(ScheduleStep(FAILED, schedule_id_for(slug), "<reason>"))` when
  the manifest will not load (`:539-545`). US1's refusal is a *second* instance
  of a branch that already exists, with a different reason string. You are not
  inventing an outcome, a return type or a rendering.
- **The control-plane failure is already computed.** `run_check` produces it
  today — that is where the `[FAIL] control_plane:` line in the reproduction
  came from. US1 needs that fact *earlier*, not for the first time.

## Route choices left to the implementer

- **Where the control-plane fact is computed once (FR-006).** Hoisting the
  probe above the schedule step and passing the result down, versus a small
  memoised accessor, are both acceptable. What is not acceptable is probing
  twice and hoping they agree.
- **How US3 records a schedule's repository root (FR-009).** The schedule
  already carries the specs path it walks. Whether you compare that, add a
  memo, or use the schedule's search attributes is yours — but read
  `desired_for_repo` before choosing, because whatever you compare has to
  survive a reconcile of a schedule this same code wrote.

## Traps

1. **The refusal must not raise.** `_schedule`'s docstring at `:532` says
   "Never raises (FR-017)", and `init` depends on that: a GitHub refusal must
   not cost the repo its scaffold. Your precondition is a `FAILED` step, not an
   exception. FR-002 and US1-S5 both exist to hold this, and S5 is specifically
   about a control plane that is *configured but unreachable* — a different case
   from *not configured*, and the one most likely to be turned into a crash.

2. **Do not satisfy US1 by not scheduling.** US1-S3 requires the created
   schedule and its reported line to be byte-identical to today's when the
   control plane is readable. A diff that removes scheduling passes S1 and S2
   and fails S3. This is why S3 exists.

3. **Assert against the schedule backend's state, not a call log.** US1-S1 says
   this explicitly. "We did not call apply_schedule" is a claim about your own
   code; "no schedule exists" is a claim about the world, and only the second
   one would have caught the defect this spec was filed for.

4. **Your test must not create a real schedule.** This spec exists *because* a
   command created a live schedule on a production namespace. A test that
   reaches a real Temporal to prove it did not schedule is the same defect with
   a test wrapper. There is precedent and it is not hypothetical: five stray
   schedules were found firing against pytest temp directories on 2026-08-16,
   and the root cause was a mutation defeating the guard that kept test runs
   off the production namespace
   (`hardening/mutating-a-production-safety-guard-escapes-the-sandbox`). Use a
   fake schedule backend. If you find yourself needing `TEMPORAL_ADDRESS` to
   run your test, stop and reconsider the seam.

5. **US2 is about position, not presence.** A test asserting both lines appear
   passes today, before your change. US2-S1 must compare their *indices* in the
   captured output. Write it, watch it fail against the current ordering, then
   fix the ordering.

6. **US3's comparison must be able to see a stranger.** US3-S3 forbids deciding
   from local filesystem state, because a check that reads only local state
   cannot observe another operator's repository at all and would pass
   vacuously. This is the anti-vacuity requirement of this spec.

7. **The judge sees only your diff and the criteria** — no base tree, no commit
   message, no terminal (constitution principle VIII / D-037). SC-001 wants the
   `env -i` reproduction transcript, and SC-002 wants the mutation diff and the
   failing test names. Both must be *committed files*, or they do not exist.

8. **Re-running init in a joined repository is supported.** US3-S2 protects it.
   Whatever identity check you add must let the same repository reconcile its
   own schedule, or you break a workflow that works today.

9. **A reachable control plane is not the same as the *operator's* control
   plane, and this story only checks the first.** Two literals in the tree name
   the Temporal namespace: `factory/cli/install.py:71` seeds the install
   interview with `ergane`, and `factory/notify/service.py:111` sets
   `DEFAULT_TEMPORAL_NAMESPACE = "factory"`. A caller that reaches the fallback
   gets `factory`; an operator who pressed enter through the interview declared
   `ergane`. FR-001 catches this on a fresh machine, where nothing is listening
   and the step refuses — but it does **not** catch it on a machine that already
   runs a control plane on `factory`, which is every developer box in this
   project. That is how the orphan schedule `ergane-roadmap-repo` was created on
   2026-08-16: an `env -i` init found a live `factory` namespace, passed every
   readability check this spec will add, and scheduled into a namespace the
   operator had never named. Do not widen this spec to fix the two literals —
   that is `install/two-defaults-for-the-temporal-namespace-disagree` and it
   carries a migration. Do make sure your refusal message says *which* namespace
   it reached, so the next person sees the mismatch instead of a bare success.

## Sizing

Small. US1 is a precondition and a second `FAILED` branch in a function that
already has one. US2 is a reordering plus a shared fact. US3 is one comparison
and its refusal. The 61,440-byte diff bound
(`factory/verify/diffbounds.py`, import `DIFF_INPUT_LIMIT` rather than quoting
it) is not expected to bind on any of the three; if it does, you have taken on
more than the story asked for.

## Verification the operator will run, independent of the gate

The reproduction from the spec's Context, re-run against the built wheel:
build, install into a clean venv, `git init` a fresh repository, then
`env -i HOME=<scratch> PATH=/usr/bin:/bin:<venv>/bin ergane init`, and confirm
against the live namespace that no schedule was created. A green suite is
evidence, not proof; this defect was found by running the thing.
