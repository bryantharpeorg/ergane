# Implementation Plan: the landing dials belong to the operator

**Spec**: `specs/081-the-landing-dials-belong-to-the-operator/spec.md`

## What already exists, and where

**Every line number below was verified on 2026-08-21 by printing that exact line
individually** (`sed -n '<n>p' <file>`). Check each one anyway.

**The dials:**

- `factory/mergequeue/models.py:377` — `class LandingConfig:`
- `:381-386` — the docstring explaining what each field is for. Read it; it
  already argues that these are knobs rather than constants.
- `:388` — `merge_method: str = "squash"`
- `:389` — `poll_interval_s: int = 60`
- `:390` — `stall_after_s: int = 7200`
- `:391` — `max_recovery_cycles: int = 1`
- `factory/mergequeue/models.py:139` — the state docstring naming
  `LandingConfig.max_recovery_cycles` as what bounds `ENQUEUED` (FR-006 of the
  spec that built it).

**The three places it is constructed, all bare:**

- `factory/cli/roadmap.py:247` — `landing_config=LandingConfig(),`
- `factory/workgraph/workflow.py:429` — `landing_config: LandingConfig = LandingConfig()`
- `factory/roadmap/workflow.py:263` — `landing_config: LandingConfig = LandingConfig()`

**The place it is not passed at all:**

- `factory/cli/nouns/build.py:592` — `EpicInput(` … the arguments below it are
  `graph`, `proxy_url`, `config`, `verify_order`, `max_concurrent_nodes`. **No
  `landing_config`.** A hand-started epic cannot carry one today even if the CLI
  parsed it.
- `factory/workgraph/cli.py:571` — the second `EpicInput(` site.
- `factory/roadmap/workflow.py:1258` — the third, which *does* pass
  `landing_config=request.landing_config` — and `request.landing_config` is the
  bare one from `factory/cli/roadmap.py:247`.

**Where the dials are consumed — this is what FR-003 has to drive:**

- `factory/workgraph/workflow.py:2813` — `if not granted and landing.recovery_cycles >= config.max_recovery_cycles:`
- `factory/workgraph/workflow.py:2851` — `if not granted and spent >= config.max_recovery_cycles:`
- `factory/workgraph/workflow.py:2850` — `spent = record.landing.recovery_cycles`
- `factory/workgraph/workflow.py:2664` — `timeout=timedelta(seconds=config.poll_interval_s),` in the poll loop.
- `stall_after_s` is read by the classifier — find `classify` from
  `factory/workgraph/workflow.py:2679` and read where it compares against the
  config, rather than trusting this line.

**The precedent for an operator-shaped config on the same command:**

- `factory/cli/nouns/build.py:1405-1406` — `start.add_argument(` /
  `"--max-concurrent-nodes",` — the flag shape to copy.
- `factory/cli/nouns/build.py:226` and `:230` — how that flag validates a
  positive integer and refuses by name. FR-004 wants exactly this treatment.
- `factory/cli/nouns/build.py:516` — `config = with_promotion_persona(config, promotion_persona)`
  — 070's precedent for the CLI *shaping* a config object before dispatch.
- `factory/cli/nouns/build.py:564` — `config: VerificationConfig | None = None,`
  and `:584` — `config = VerificationConfig()`. The ladder's caps already travel
  this way; the landing's do not.
- `factory/workgraph/workflow.py:413-422` — `EpicInput`'s docstring, which
  already says `landing_config` is "the merge-queue's knobs". The design intent
  is on the page; only the wiring is missing.

## Traps

**1. Do not change a default.** The spec is explicit and the operator asked for
it explicitly: `merge_method="squash"`, `poll_interval_s=60`,
`stall_after_s=7200`, `max_recovery_cycles=1` all stay. US1-S2 is the control
that proves it, and a diff that "improves" a default while making it settable has
changed unattended behaviour for every existing user of this release.

**2. Storing the value is not implementing the dial.** FR-003, US1-S3, US1-S4.
This repository has filed the same defect five times under
`verify/readiness-proves-a-thing-is-declared-not-that-it-works`: a setting that
parses, persists and is never read. Drive the recovery path and drive the
classifier. A test that asserts `config.max_recovery_cycles == 3` proves the
dataclass works.

**3. All three `EpicInput` sites.** US1-S6. `factory/cli/nouns/build.py:592`,
`factory/workgraph/cli.py:571`, `factory/roadmap/workflow.py:1258`. A site that
drops an operator-set value produces "set but ignored", which costs more operator
time than "cannot be set" because it looks like it worked.

**4. Validate at the command, not in the workflow.** FR-004 and US1-S5. A
negative interval that reaches a workflow becomes a determinism problem and an
activity failure hours later; the same value refused by `build start` costs
nothing. `factory/cli/nouns/build.py:226-230` is the shape.

**5. Say what a change does to a running epic.** FR-007 and US2-S3. An epic
compiles its dispatch at start. The honest answer is almost certainly "the next
dispatch, not the running one" — write that down and prove it, rather than
leaving the operator to infer it from a dial that appears not to work.

**6. `stall_after_s` has a consumer you have not read yet.** The plan names
`max_recovery_cycles` and `poll_interval_s` precisely and deliberately does not
name the stall comparison, because it lives inside `classify` and the anchor
would be a guess. Find it, read it, and cite it in your diff.

**7. Do not touch 069's pricing.** A `BASE_MOVED` rejection is charged to neither
budget (`factory/mergequeue/models.py:89` documents it). This spec raises the
*bound*, it does not re-price anything.

**8. `merge_method` is passed verbatim to the forge.** An unknown value there is
a forge error at landing time, which is the worst place for it. FR-004 covers it;
decide whether the valid set is enumerated in the CLI or checked against the
forge, and say which.

**9. Degraded status must stay degraded-not-broken.** US3-S3. Spec 052 landed
that principle for `ergane build status`; a new field that raises when it cannot
be read regresses it.

**10. The judge sees the diff and the criteria, nothing else** (Constitution
Principle VIII). Every SC needs committed, pasted output. SC-003 in particular
needs *both* runs — with the raised bound and with the default — because the
comparison is the evidence.

**11. One test file per story.**
- US1 → `tests/test_landing_dials_reach_the_epic.py`
- US2 → `tests/test_scheduled_epics_carry_the_dials.py`
- US3 → `tests/test_status_shows_the_dials_in_force.py`
US1 and US3 both edit `factory/cli/nouns/build.py`; US1 and US2 both reach
`EpicInput`. The `depends_on_merged` chain is what keeps them from racing.

## Sizing

**US1 is medium.** Four flags, their validation, one construction site to widen
and two to check — plus the two behaviour-driving tests, which are where the
time goes and where the value is.

**US2 is small.** One construction site and the plumbing that reaches it, plus
the statement FR-007 asks for.

**US3 is small.** One rendering change and the degraded-path control.

**None of them should need a second attempt.** If one does, the most likely cause
is trap 2 — a story that stored the value, passed its own test, and was correctly
failed by the judge for not driving the behaviour.

## Verification the operator will run, independent of the gate

- **Start an epic with `max_recovery_cycles` raised and watch a raced node
  recover twice.** That is the measurement the whole spec exists for, and the
  free-rebase path it exercises has still never run in production.
- **Start one with `stall_after_s` lowered and leave it unattended.** The
  2026-08-19 request was exactly this.
- **Start one with nothing set** and confirm the four defaults in status output —
  the control, and the one that protects everyone who upgrades.
- **Give `build start` a nonsense dial** and confirm it refuses at the command.
</content>
