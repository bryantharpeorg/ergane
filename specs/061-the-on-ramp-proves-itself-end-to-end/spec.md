---
state: landed
# Attested landed 2026-08-21 (10:00 AM CT), 4/4. US1 83f0253f1506 (#224),
# US2 b4ebc30b72bf (#226), US3 e5cb0e95dedc (#264), US4 c678c11191f7 (#266) —
# all four observed on ergane-buildout by
# `ergane spec landed --default-branch ergane-buildout`, and each confirmed an
# ancestor of origin/ergane-buildout.
#
# Attempts, from the ledger rather than from a report: US1 and US3 first-attempt;
# US2 took two attempts across a re-dispatch (the killed run of 2026-08-19, whose
# hold note survives below); US4 took two, the first refused by `check_output` on
# diff size at 127,038 B against the 65,536 B ceiling with the gate already green,
# the second landing at 64,530 B — 1,006 B of margin — with the judge 5/5 and no
# feedback. US1/US2 ran on `implementer`; US3/US4 on `opus-closer` (subscription).
#
# WHAT THIS ATTESTATION DOES NOT CLAIM. US4's live end-to-end run is the
# operator's post-landing verification (SC-004, SC-005), not diff evidence, and
# it has not been run. The exercise, its per-stage failure reporting, its skip
# guard and its control transcripts are committed and judged; the live drive
# against a real forge is outstanding.
#
# --- release note this supersedes ---
# RELEASED draft -> ready 2026-08-21 ~6:45 AM CT on the operator's go, hold
# conditions answered:
#   1. Stale forge state CLEARED: PR #226 is MERGED (us2 landed b4ebc30), the
#      dead run's worktree/sidecar removed, factory/061 branches archived to
#      refs/archive/* (SHAs in ~/ergane-ops/archived-refs-2026-08-21.txt) and
#      deleted.
#   2. Spec 071 LANDED 2026-08-20 — a failing check's log now reaches the
#      recovery attempt. Unexercised by a real production failure yet; plan
#      trap 14 still tells the implementer to get the git identity right.
#   3. max_recovery_cycles is still 1 and unraisable — the soft condition,
#      accepted. Roadmap dispatch is PAUSED, so the re-dispatch loop this hold
#      existed to stop cannot fire; dispatch is by hand.
# us1 and us2 are landed; the remainder is us3+us4, edges depends_on_merged.
#
# --- original hold note (2026-08-19 6:18 PM CT), kept for the record ---
# HELD ready -> draft 2026-08-19 6:18 PM CT to STOP A RE-DISPATCH LOOP, not
# because anything is wrong with the spec. us1 is landed; us2-us4 are not.
#
# WHAT HAPPENED. The epic died at 23:10Z: us2's PR failed the required `test`
# check, the recovery attempt was told only the outcome word, it rebuilt
# identical code, `max_recovery_cycles` (1, and unraisable) was spent, and us2
# was KILLED taking us3 and us4 with it at attempt 0. The operator terminated the
# epic. The roadmap's next tick then RE-DISPATCHED IT FIVE MINUTES LATER, because
# `ready` plus `landed=False` is the whole of the dispatch predicate.
#
# WHY THAT WAS A LOOP RATHER THAN A RETRY. The relaunched node resumed the DEAD
# RUN'S TREE. Verified on the live worktree at 6:17 PM CT:
#   .factory/worktrees/061-.../us2 HEAD = `salvage(...): completed attempt 2`
#   tests/test_ergane_init_creates_specs.py:40 calls git commit, and the file
#   sets no user.email and no user.name anywhere.
# That is the exact fixture whose `exit 128` killed the epic. CI has no git
# identity; the sandbox HOME has a seeded .gitconfig, so it passes where it is
# written and fails where it is checked. The relaunch would have failed the same
# way, been killed the same way, and been re-dispatched again -- all night,
# unattended.
#
# WHAT MUST BE TRUE BEFORE THIS RETURNS TO `ready`:
#   1. The stale remote branches and PR #226 are cleared. `ergane build reset`
#      archives local state and never touches the forge, so the dead run's
#      `factory/061-.../us1` and `/us2` and its open PR outlive the kill. That is
#      069/US3.
#   2. The recovery agent receives the failing check's LOG.
#      `interpreter/ci-failure-never-reaches-an-agent` is now REGRESSED at four
#      occurrences -- it was marked resolved by spec 025, which landed, and whose
#      own prose describes this night verbatim. Until an agent is told what
#      failed, every red check costs the epic.
#   3. Ideally `max_recovery_cycles` becomes operator-settable at all
#      (`mergequeue/max-recovery-cycles-bounds-every-raced-node-and-no-operator-
#      can-raise-it`). It is 1, constructed bare at every call site, and no
#      configuration surface reaches it.
#
# Nothing restores this to `ready` automatically.
depends_on_landed: [059-a-wired-repo-can-land, 060-install-can-be-driven-without-a-human]
# Flipped draft -> ready 2026-08-19 ~12:15 AM CT at the operator's instruction.
# Ready is eligibility, not dispatch, and here the distinction is enforced: the
# scheduler will hold this epic until both named specs have landed.
# The dependency above is machine-enforced, not advisory. US4 drives a
# non-interactive install (060) against a repository that can actually land
# (059), and neither is substitutable -- 055 expressed the same constraint as a
# comment, and a comment is not something the scheduler can honour.
#
# Drafted 2026-08-18 ~12:05 AM CT by an operator session, from a first-time
# install report filed by an agent installing `ergane-cli 0.1.0` from PyPI.
#
# ORDERING: this epic must not be started until 060 has landed. US4 automates a
# complete install-to-landing run, which is impossible while `ergane install`
# and `ergane init` can only be answered by a human at a terminal. US1-US3 do
# not depend on 060 and could be dispatched earlier if 060 slips, but the spec
# is written as one because US4 is the story that gives the other three their
# point.
#
# This is the spec that addresses the defect CLASS rather than three defects.
# All three of US1, US2 and US3 are the same shape, and the shape is filed as
# `verify/readiness-proves-a-thing-is-declared-not-that-it-works`:
#
#   US1  the LLM probe asserts an endpoint answers, never that a key can be minted
#   US3  gate_check asserts a check named 'test' exists, never that it can fail
#   US2  init registers a schedule against a corpus it never creates
#
# Each was verified against the tree before drafting:
#
#   - `factory/controlplane/verify.py` references `/chat/completions` at :355 and
#     contains ZERO references to `/key/generate` or `issue_key`. Meanwhile
#     `factory/discovery/llm_scanner.py:137` ALREADY distinguishes a dispatchable
#     gateway from an inference-only endpoint on exactly that signal. The
#     knowledge is in the tree; the verify path does not use it.
#   - `factory/cli/init.py:816` mkdirs the runtime root and nothing creates
#     `specs/`. `factory/roadmap/models.py:398` calls `root.iterdir()` on a path
#     that does not exist. The reporter measured the consequence: the schedule's
#     OverlapPolicy is Skip, so one stuck failing run blocked the next three
#     ticks -- ActionCounts {"Total":4, "SkippedOverlap":3}.
#   - `factory/cli/init.py:275` sets `gates: {test: "true"}` in a dict its OWN
#     comment calls `_PLACEHOLDERS` -- "Placeholder values that keep a partial
#     manifest valid for full-parser checks" -- and that placeholder escapes into
#     live manifests. `factory/mergequeue/onboard.py:257` then reports
#     `required check 'test' exists` as a PASS.
#
# Specs 054 (a stranger can install Ergane) and 055 (the gateway is a choice
# with a scan) both landed and were attested on 2026-08-18. A stranger
# installing the very next day hit thirteen defects, three on the critical path.
# The specs were not badly built. Their criteria were provable from the diff
# (D-037), and presence is what a diff can cheaply show. US4 exists because
# nothing in this system currently measures the composition.
#
# Filed as findings before drafting:
#   verify/llm-probe-never-mints-a-key-so-a-config-only-proxy-passes
#   verify/the-default-gate-is-a-no-op-and-readiness-reports-it-green
#   verify/readiness-proves-a-thing-is-declared-not-that-it-works
#   install/init-registers-a-roadmap-schedule-over-a-specs-dir-it-never-creates
---

# Feature Specification: the on-ramp proves itself end to end

**Created**: 2026-08-18

## The gap, stated precisely

Every readiness check Ergane ships asserts that a thing is **declared**. None
asserts that it **works**. The distinction sounds academic until you line up what
a first-time operator actually hit:

| Check | What it asserts | What it never asserts |
| --- | --- | --- |
| `LLMProbe.gather` | an endpoint answers a completion | a virtual key can be minted |
| `gate_check:test` | a required check named `test` exists | that check can ever fail |
| `ergane init --check` | the schedule is registered | its first tick will not crash |

Each check is individually honest. Together they produce a machine that reports
`11/11` and `6/6` green and cannot dispatch, cannot land, and dies on its first
roadmap tick — which is exactly what happened.

This spec repairs the three instances and then, in US4, builds the thing whose
absence allowed all three: a check that runs the on-ramp end to end and asserts
the outcome rather than the parts.

## Why the LLM probe is the most expensive one

Dispatch does not run on chat completions. It runs on a virtual key minted per
attempt (`factory/usage/litellm_client.py`, `issue_key`), read back via
`/key/info` and `/spend/logs/v2`, then revoked. Those endpoints are
**database-backed** in LiteLLM. A proxy started without `DATABASE_URL` answers
`/v1/models` and `/v1/chat/completions` perfectly and 404s every one of them.

So an operator can stand up a config-only LiteLLM, watch `ergane install
--verify` report `[PASS] llm`, and discover the gateway is unusable only when
the first epic dies mid-dispatch — after the interview, after the worker install,
after wiring, after onboarding.

The repair is unusually cheap, because the system already knows how to tell the
difference. `factory/discovery/llm_scanner.py:137` classifies an endpoint as
`DISPATCHABLE` when "/v1/models and /key/generate both answer" and
`INFERENCE_ONLY` when "the key-management API does not". 055 built that. The
verify path simply does not consult it.

## Why a missing directory is a four-tick outage

`ergane init` registers a roadmap schedule polling `<repo>/specs` every 300
seconds and never creates `specs/`. `read_roadmap` calls `root.iterdir()` and
raises. That alone would be a bad first impression. The `OverlapPolicy` makes it
worse: it is `Skip`, so the stuck failing run blocks subsequent ticks, and the
reporter measured `{"Total": 4, "SkippedOverlap": 3}`.

The operator sees a red worker on a brand-new repository with nothing to
correlate it to, because the failure is in the journal and `--check` reports all
green.

There are two candidate repairs and this spec picks the second as primary.
Creating `specs/` in `init` fixes the symptom. Making `read_roadmap` treat a
missing root as an empty corpus fixes the class — an empty corpus is *already* a
valid state that renders zero rows and exits 0, so a missing one has an obvious
correct answer. The spec requires both, because a fresh repository should have a
`specs/` directory anyway, and because the reader should not raise on a state its
own renderer handles.

This must be done without weakening `read_roadmap`'s loud-failure discipline. Its
docstring is explicit that a corpus with any finding raises and yields no partial
roadmap, "the same 'emits nothing on failure' discipline as the deriver". A
missing root is not a malformed corpus; it is an absent one. Those must stay
distinguishable.

## Why the default gate is a design defect and not a typo

`factory/cli/init.py:275` sets `gates: {test: "true"}` — the shell builtin, which
always exits 0. That value lives in a dictionary the code itself names
`_PLACEHOLDERS`, with a comment describing it as values "that keep a partial
manifest valid for full-parser checks". It was never meant to be a gate. It
escapes into live manifests anyway, and `factory/mergequeue/onboard.py:257` then
reports `required check 'test' exists` as a pass.

The result is a fully wired autonomous factory whose sole quality gate cannot
fail, reporting green on every readiness signal. Given D-024 removes the human
from the loop by construction, "all checks green" in that configuration means
"anything an agent writes will land".

## User Scenarios & Testing

### User Story 1 - Verification proves the gateway can mint a key, not merely answer (Priority: P1)

As an operator running `ergane install --verify`, a passing `llm` check means
the gateway can actually dispatch, because verification exercised the capability
dispatch depends on.

**Why this priority**: P1. It converts the single most expensive failure mode in
the system — discovered mid-epic, after every other setup step — into a fast
local check.

**Independent Test**: drive the probe against a simulated inference-only endpoint
and a simulated dispatchable one, and assert opposite verdicts.

**Acceptance Scenarios**:

1. **Given** a gateway that answers `/v1/models` and `/v1/chat/completions` but
   404s `/key/generate`, **When** `ergane install --verify` runs, **Then** the
   `llm` check **fails**, naming key management as the missing capability and
   the database backing as its usual cause — proven by a committed test driving
   the probe through its injected seam against that simulated endpoint.
2. **Given** a gateway that answers all three, **When** `--verify` runs,
   **Then** the `llm` check passes — proven by a committed test. A probe that
   fails everything is not an improvement over one that passes everything.
3. **Given** the diff, **When** the probe's key handling is inspected, **Then**
   it mints a short-TTL key, asserts the minted key is model-constrained, and
   revokes it — proven by a committed test asserting all three calls occur and
   that revocation happens even when the assertion between them fails. A probe
   that leaks a key on its own failure path is a probe that degrades the system
   it is checking.
4. **Given** the diff, **When** the classification logic is inspected, **Then**
   it reuses `factory/discovery/llm_scanner.py`'s existing
   `DISPATCHABLE`/`INFERENCE_ONLY` distinction rather than reimplementing it —
   proven by a committed test importing the shared symbol. Two classifiers for
   one question drift, and the drift is invisible because both suites stay green.
5. **Given** a gateway that mints a key but returns one with no model
   constraint, **When** `--verify` runs, **Then** it fails naming the constraint
   as the missing property — proven by a committed test. Per-attempt model
   constraint is the property `llm.mode = "direct"` was refused to protect; a
   verification that does not check it protects nothing.

---

### User Story 2 - A fresh repository survives its first roadmap tick (Priority: P1)

As an operator who has just run `ergane init` on a new repository, the roadmap
schedule runs cleanly instead of raising and blocking three subsequent ticks.

**Why this priority**: P1. Every new operator hits it, on their first repository,
within five minutes, and the evidence is in a journal they have no reason to be
reading.

**Independent Test**: call the reader against a missing root and against an empty
one and assert both yield an empty roadmap; assert a malformed corpus still
raises.

**Acceptance Scenarios**:

1. **Given** a specs root that does not exist, **When** `read_roadmap` runs,
   **Then** it returns an empty roadmap rather than raising — proven by a
   committed test.
2. **Given** a specs root that exists and is empty, **When** `read_roadmap`
   runs, **Then** it returns an empty roadmap — proven by a committed test. This
   cell already works and must keep working; a test that omits it cannot detect a
   reader that now returns empty for everything.
3. **Given** a specs root containing a malformed corpus, **When** `read_roadmap`
   runs, **Then** it still raises naming every fault — proven by a committed
   test. The loud-failure discipline the docstring commits to is not weakened by
   this story; absent and malformed are different states.
4. **Given** the diff, **When** `ergane init` completes on a fresh repository,
   **Then** a `specs/` directory exists — proven by a committed test asserting
   its creation alongside the runtime root at `factory/cli/init.py:816`.
5. **Given** a fresh repository, **When** the roadmap schedule's first tick runs,
   **Then** it completes and renders zero rows — proven by a committed test
   driving the workflow's read path against a freshly-initialised tree.

---

### User Story 3 - A gate that cannot fail is named as one (Priority: P2)

As an operator reading `ergane init --check`, a gate command that can never fail
is reported as a distinct condition rather than as a passing gate.

**Why this priority**: P2. It does not block anyone, which is precisely why it is
dangerous: the configuration it hides is a factory that lands whatever an agent
writes.

**Independent Test**: run the check against manifests declaring no-op and real
gate commands and assert the reported condition differs.

**Acceptance Scenarios**:

1. **Given** a manifest declaring a gate whose command is `true`, **When**
   `ergane init --check` runs, **Then** it reports a distinct finding stating the
   gate is a no-op and that no gate can fail — not a pass — proven by a committed
   test asserting the finding's key and text.
2. **Given** gate commands `:` and the empty string, **When** the check runs,
   **Then** each is recognised as a no-op — proven by a committed test
   parametrised over all three forms.
3. **Given** a manifest declaring a real gate command, **When** the check runs,
   **Then** it reports the existing pass unchanged — proven by a committed test.
4. **Given** the diff, **When** the no-op finding's severity is inspected,
   **Then** it does not fail `--check` outright — proven by a committed test
   asserting exit status. An operator deliberately running without gates during
   evaluation is making a choice; the requirement is that the choice be visible,
   not that it be forbidden.
5. **Given** the diff, **When** `_PLACEHOLDERS` (`factory/cli/init.py:398`) is
   inspected, **Then** the gate placeholder is either removed or renamed so that
   a value the code calls a placeholder cannot silently become a live gate —
   proven by a committed test asserting a freshly-initialised manifest does not
   declare `true` as a gate.

---

### User Story 4 - The on-ramp is exercised end to end, and the exercise is the check (Priority: P1)

As a maintainer, one committed test drives a scratch repository from install
through init, wiring, dispatch and landing, so that a defect anywhere in the
composition fails a build rather than a stranger's evening.

**Why this priority**: P1 despite being last. It is the only story here that
addresses why the other three shipped. US1-US3 fix three instances; US4 is what
catches the fourth.

**Independent Test**: it is the test. It runs the real verbs against a scratch
target and asserts a pull request landed.

**Acceptance Scenarios**:

1. **Given** a scratch organization-owned repository and a host meeting the
   documented prerequisites, **When** the end-to-end exercise runs, **Then** it
   drives `ergane install`, `ergane init --wire`, `ergane repo onboard` and a
   dispatched trivial epic without human input, and asserts a pull request
   reached a landed state — proven by the committed exercise plus, pasted into
   the diff, the skip-path transcript and the simulated per-stage drives
   (US4-S2). The implementer's sandbox has no live GitHub, Temporal or gateway,
   so the full live run is the operator's verification after landing (SC-004,
   SC-005), not diff evidence.
2. **Given** the exercise, **When** any single stage fails, **Then** it reports
   which stage and stops — proven by a committed test driving a simulated
   failure at each stage and asserting the reported stage name. An end-to-end
   test that reports only "failed" costs more to diagnose than it saves.
3. **Given** the exercise, **When** it is inspected for what it asserts,
   **Then** its final assertion is a landed pull request, not the exit status of
   the last command — proven by reading the committed assertion. This story
   exists because exit statuses were green while the outcome was absent.
4. **Given** the exercise, **When** it runs in an environment lacking the live
   prerequisites, **Then** it skips with a message naming what is missing rather
   than failing or silently passing — proven by a committed test. A live-tier
   guard must catch what the client actually raises; markers alone are
   decorative, because nothing passes `-m` in CI or the gate.
5. **Given** the diff, **When** the exercise's scratch resources are inspected,
   **Then** it creates and destroys its own target repository and runtime root,
   touching neither the operator's live store nor any repository it did not
   create — proven by a committed test asserting the paths it writes are all
   beneath its own temporary root.

### Edge Cases

- **The gateway mints a key but `/spend/logs/v2` 404s.** Partial database
  backing. Report which endpoint failed, since the remedies differ.
- **`read_roadmap` is handed a path that exists but is a file.** Distinct from
  absent and from empty; must not be silently treated as an empty corpus.
- **The end-to-end exercise is interrupted.** It must not leave a scratch
  repository or schedule behind; cleanup runs on failure as well as success.
- **A no-op gate declared deliberately for evaluation.** Reported every run, not
  suppressible by a flag — the visibility is the whole feature.

## Requirements

### Functional Requirements

- **FR-001**: `LLMProbe` MUST mint a short-TTL virtual key, assert it is
  model-constrained, and revoke it, as part of `ergane install --verify`.
- **FR-002**: Revocation MUST occur even when the intervening assertion fails.
- **FR-003**: The dispatchable/inference-only distinction MUST be the one
  `factory/discovery/llm_scanner.py` already defines, not a second copy.
- **FR-004**: A gateway lacking key management MUST fail the `llm` check, naming
  key management and its usual cause.
- **FR-005**: `read_roadmap` MUST treat a missing specs root as an empty corpus.
- **FR-006**: `read_roadmap` MUST continue to raise, naming every fault, on a
  malformed corpus.
- **FR-007**: `ergane init` MUST create `specs/` on a fresh repository.
- **FR-008**: `ergane init --check` MUST report a no-op gate command as a
  distinct finding, recognising at least `true`, `:` and the empty string.
- **FR-009**: The no-op finding MUST NOT fail `--check`.
- **FR-010**: A freshly-initialised manifest MUST NOT declare a no-op gate.
- **FR-011**: A committed end-to-end exercise MUST drive install through landing
  against a scratch target, asserting a landed pull request.
- **FR-012**: The exercise MUST name the failing stage, skip cleanly without live
  prerequisites, and clean up its own resources on success and failure alike.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: []
  implements: [FR-005, FR-006, FR-007]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-008, FR-009, FR-010]
  persona: opus-closer
US4:
  depends_on: []
  depends_on_merged: [US1, US2, US3]
  implements: [FR-011, FR-012]
  persona: opus-closer
```

US3's edge on US2 is a **merge** edge declared for contention: both edit
`factory/cli/init.py`, US2 adding the `specs/` creation at :816 and US3 changing
the gate placeholder at :273.

US4's edges are **pass** edges and they are the point of the spec. The exercise
asserts the composition, so it must be built against the three repairs rather
than beside them — SC-005 requires that reverting any one of them fails US4, and
that is only meaningful if US4 was built after all three landed.

US1 and US2 share nothing: `factory/controlplane/verify.py` against
`factory/roadmap/models.py`.

**This epic must not be dispatched until 059 and 060 have landed.** US4 drives a
non-interactive install (060) against a repository that can land (059), and
neither is substitutable.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Pointed at a LiteLLM started without `DATABASE_URL`, `ergane
  install --verify` fails the `llm` check; pointed at the same proxy with a
  database, it passes — evidenced by both transcripts committed in the diff.
- **SC-002**: On a freshly initialised repository, the roadmap schedule's first
  three ticks complete with zero `SkippedOverlap` — evidenced by committed
  schedule output.
- **SC-003**: `ergane init --check` on a default-initialised repository reports
  the gate as a no-op rather than as a pass.
- **SC-004**: The end-to-end exercise, run against a scratch repository, lands a
  pull request without human input — evidenced by the operator running the
  committed exercise against live prerequisites after landing and recording the
  merged pull request at resolution. The diff carries the skip-path and
  simulated-stage evidence; the implementer's sandbox cannot reach live
  prerequisites, so the live transcript is not diff evidence.
- **SC-005**: Reverting any one of US1, US2 or US3's fixes causes the US4
  exercise to fail. If it does not, the exercise is not measuring the
  composition and US4 has not been built.

## Assumptions

- 060 has landed, so install and init can be driven without a terminal. US4 is
  not buildable otherwise.
- 059 has landed, so a wired scratch repository can actually land a pull request.
  US4's final assertion depends on it.
- The scratch target for US4 is organization-owned, per 059's eligibility rule.
- LiteLLM's key-management endpoints remain database-backed. If that changes, the
  probe's failure message becomes wrong before the probe does; SC-001 is the
  check that would catch it.
