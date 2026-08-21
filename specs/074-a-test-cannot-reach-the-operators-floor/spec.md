---
state: draft
# Drafted 2026-08-20 10:30 AM CT by an operator session, from a triage pass over
# the 143 findings that survived the 2026-08-20 sweep. Six of them — five
# critical — are one mechanism wearing five faces, and that mechanism has already
# emptied this repository's runtime root once, created five live schedules on the
# production namespace, committed 33 files of operator scratch to a branch, and
# paged the operator from a test.
#
# This spec is the declared fix for:
#   hardening/repo-cli-open-client-has-no-pytest-refusal                   (critical)
#   hardening/mutating-a-production-safety-guard-escapes-the-sandbox       (critical)
#   hardening/a-story-created-five-live-roadmap-schedules-that-paged-the-operator (critical)
#   hardening/reset-commits-the-operator-checkout                          (critical)
#   notify/live-telegram-smoke-pages-the-operator-from-every-agent-suite-run (critical)
#   hardening/live-tier-probes-leak-onto-the-production-namespace-wearing-the-epic-prefix (critical)
#
# Those six lines become a `fixes:` frontmatter key once 073/US1 lands and widens
# the grammar. Until then the frontmatter grammar is closed to `state` and
# `depends_on_landed`, and a `fixes:` key here would be refused by
# `ergane spec validate` — so this comment is the declaration, exactly as 072
# does it.
#
# DO NOT FLIP READY without a pre-dispatch review.
---

# Feature Specification: a test cannot reach the operator's floor

**Created**: 2026-08-20

## The gap, stated precisely

This repository already knows the shape of the answer. It is written down, in
prose, at `factory/cli/repo.py:465`:

> A convention is not a boundary for an act that deletes.

That sentence was paid for on 2026-08-14, when a process satisfying a test
emptied the live runtime root. D-045 turned it into a boundary at the one choke
point every deletion goes through, and the class has not recurred.

**The same sentence is true of an act that reaches production, and there it is
still only a convention.** The binding is a seam in `tests/`; the enforcement is
one `PYTEST_CURRENT_TEST` check on one module out of ten.

### Measured against `a58ec93`

Ten call sites in `factory/` construct a real Temporal client:

| site | guarded under pytest |
| --- | --- |
| `factory/roadmap/schedule.py:165` | **yes** — `schedule.py:156-162` |
| `factory/workgraph/cli.py:817` | no |
| `factory/cli/nouns/__init__.py:54` | no |
| `factory/cli/roadmap.py:188` | no |
| `factory/cli/repo.py:84` | no |
| `factory/doctor/probes.py:491` | no |
| `factory/doctor/probes.py:603` | no |
| `factory/controlplane/verify.py:185` | no |
| `factory/notify/service.py:801` | no |
| `factory/worker.py:283` | no |

`PYTEST_CURRENT_TEST` appears in exactly three modules —
`factory/roadmap/schedule.py:156`, `factory/verify/store.py:281` and
`factory/cli/repo.py:475`. The sharpest evidence that this is a convention and
not a boundary is that the third and the fourth row of that table are **the same
file**: `factory/cli/repo.py` guards its deletion path at `:458-484` and leaves
its client constructor at `:79-89` open.

### What that costs, in incidents rather than in theory

- **`hardening/repo-cli-open-client-has-no-pytest-refusal`.** A `repo` CLI test
  that forgets to bind the seam does not fail and does not error. It consults the
  operator's production control plane and its verdict depends on what the floor
  happens to be doing. Mutation M8 deleted the destination check from "export
  refuses a destination inside the runtime root" and **the test still passed** —
  it had dialled the operator's real Temporal, found a genuinely open epic, and
  refused for that reason instead. Exit 1 either way, and the asserted substring
  "runtime root" appears in both messages.
- **`hardening/a-story-created-five-live-roadmap-schedules-that-paged-the-operator`.**
  Five unpaused schedules on the production namespace, 5-minute cadence, pointed
  at `/tmp/pytest-of-admin/...`. Four `RoadmapWorkflow` runs failed, the failure
  counter was written against the *real* roadmap's id, and 031's notifier paged
  the operator's phone. `ergane roadmap status specs` stayed broken afterwards,
  because `_locate` resolves the newest `roadmap-specs*` run and the newest was a
  test's corpse.
- **`notify/live-telegram-smoke-pages-the-operator-from-every-agent-suite-run`.**
  The live Telegram smoke skips only on *absent* credentials. An operator with a
  token in their shell arms it by existing.

### The part that makes a third guard necessary rather than tidy

`hardening/mutating-a-production-safety-guard-escapes-the-sandbox` is not a
variation on the others. It is the reason the others cannot be fixed by adding
more `PYTEST_CURRENT_TEST` checks.

This repository requires mutation proof that a behaviour is not vacuous. **The
strongest mutation against a safety guard is disabling the guard.** Mutation M12
replaced the `PYTEST_CURRENT_TEST` check inside `_default_schedule_client` with
`if False:` — the correct thing to do when proving that check is load-bearing —
and the suite then created the five live schedules above.

So the practice this factory depends on for test honesty is, for one class of
code, an operation that reaches production. A single env-var guard is therefore
not merely thin; it is *guaranteed to be disabled at least once per proof*.

`factory/roadmap/schedule.py:22-26` already states the answer and already
implements it for one module:

> two independent guards are the enforcement — `_default_schedule_client` will
> not connect under `PYTEST_CURRENT_TEST`, and `_refuse_live_client` will not
> mutate through a real client under it. Removing either alone still refuses.

This spec generalises that sentence to every module. It invents nothing.

### Two neighbours in the same class

- **`hardening/reset-commits-the-operator-checkout`** (2 occurrences). A git
  operation pointed at a *husk* node path — a worktree directory whose `.git`
  file is gone — walks up and resolves to the operator's checkout. It has
  arrived twice by two routes: `build reset`, and the salvage path during
  teardown, which committed 33 files of operator scratch as
  `396611b salvage(011-agent-sandbox/us3)`. Node worktrees are nested *inside* the
  operator's checkout, so "walk up until you find a repository" always succeeds
  and always succeeds wrongly.
- **`hardening/live-tier-probes-leak-onto-the-production-namespace-wearing-the-epic-prefix`**
  (2 occurrences). A leaked probe workflow was named `epic-capacity-can-3d2bb231`.
  The production worker fails its tasks — the class is not registered — and worse,
  `_list_open_epics` counts it as an open epic, so a leaked test artefact silently
  consumes a concurrency slot the operator cannot see.

## User Scenarios & Testing

### User Story 1 - One place builds a real client (Priority: P1)

As an operator, every real Temporal client in the factory is constructed at one
choke point, so there is one place to guard and a new caller cannot miss it.

**Why this priority**: P1 and it depends on nothing. US2 has nothing to harden
until the choke point exists, and the nine unguarded sites are the surface every
other story's incident came through.

**Acceptance Scenarios**:

1. **Given** the factory package, **When** it is searched for `Client.connect`,
   **Then** exactly one module contains it — proven by a committed test that
   walks `factory/**/*.py` and fails naming any other file. A test that greps the
   tree is the only form of this proof that stays true as the tree grows.
2. **Given** a caller that previously connected directly, **When** it needs a
   client, **Then** it obtains one from the choke point and its behaviour on a
   reachable control plane is unchanged — proven by committed tests for each
   migrated caller.
3. **Given** `PYTEST_CURRENT_TEST` is set, **When** any caller asks the choke
   point for a client, **Then** it refuses, and the refusal names both the
   address it declined to reach and the seam the test should bind instead —
   proven by a committed test.
4. **Given** a refusal from the choke point and a refusal from an unrelated
   precondition, **When** a test asserts on the refusal text, **Then** the two
   messages are distinguishable by a substring unique to each — proven by a
   committed test asserting both. This is FR-005 and it exists because M8 passed
   against `"runtime root"`, a substring two different refusals shared.
5. **Given** the worker entrypoint `factory/worker.py:274`, **When** it is run
   outside pytest, **Then** it connects exactly as it does today — proven by a
   committed test. The worker is production; the guard is about the test process,
   not about this caller.

---

### User Story 2 - Disabling one guard is not enough (Priority: P1)

As an operator, a test process cannot reach the production control plane even
when the `PYTEST_CURRENT_TEST` refusal has been removed, so proving that refusal
is load-bearing does not itself reach production.

**Why this priority**: P1, depends on US1. Without it, every mutation battery run
against the choke point is an incident waiting for its turn, and US1's single
guard would concentrate that risk rather than reduce it.

**Acceptance Scenarios**:

1. **Given** the `PYTEST_CURRENT_TEST` refusal is neutralised in-process,
   **When** a test asks the choke point for a client, **Then** it still refuses,
   and the refusal names the second defence — proven by a committed test that
   disables the first defence the way a mutation would.
2. **Given** the second defence is neutralised in-process instead, **When** a
   test asks for a client, **Then** the `PYTEST_CURRENT_TEST` refusal still fires
   — proven by a committed test. Either alone suffices; that is what
   `factory/roadmap/schedule.py:22-26` means by independent.
3. **Given** both defences are neutralised, **When** a test asks for a client,
   **Then** it connects — proven by a committed test against a local server or a
   refused-connection address. Two guards that cannot both be removed would be
   one guard wearing a disguise, and the mutation battery could not tell.
4. **Given** a sanctioned live tier has been opted into by name (US3), **When**
   it asks for a client, **Then** both defences stand down and it connects —
   proven by a committed test. A door with no user is only a way in, so this door
   has exactly one, and it is explicit.

---

### User Story 3 - A live tier is opted into, never armed by a credential (Priority: P1)

As an operator, a live-tier test runs because someone named that tier, not
because a credential happened to be in the environment.

**Why this priority**: P1 and it depends on nothing. It is the whole of the
Telegram paging incident and half of the namespace leak, and it is independent of
the client work.

**Acceptance Scenarios**:

1. **Given** `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are both set and no tier
   has been opted into, **When** the suite runs, **Then** the live Telegram test
   skips and nothing is sent — proven by a committed test.
2. **Given** a tier is opted into by name but its credentials are absent, **When**
   the suite runs, **Then** the test **fails** naming the missing credential
   rather than skipping — proven by a committed test. Asking for a live run and
   silently not getting one is how a tier rots unnoticed.
3. **Given** a tier is opted into by name with its credentials present, **When**
   the suite runs, **Then** that tier's tests run — proven by a committed test
   that asserts selection, not by running the live tier itself.
4. **Given** the opt-in names one tier, **When** the suite runs, **Then** the
   other tiers still skip — proven by a committed test. One name arms one tier.
5. **Given** every live-tier test in `tests/`, **When** the suite is searched,
   **Then** each one's skip condition is the opt-in and not the presence of a
   credential — proven by a committed test that enumerates them and fails naming
   any that guards on a credential alone.

---

### User Story 4 - A git operation on a husk refuses (Priority: P1)

As an operator, a git operation aimed at a node path that is not a live worktree
refuses by name instead of resolving to the operator's checkout.

**Why this priority**: P1 and it depends on nothing. It is the only story here
whose incident wrote to the operator's git history, and the class has already
recurred once by a second route.

**Acceptance Scenarios**:

1. **Given** a node path that is a live worktree, **When** a git operation is
   aimed at it, **Then** it proceeds exactly as today — proven by a committed
   test over a real worktree built in a temporary directory.
2. **Given** a node path whose `.git` file has been removed — a husk — **When** a
   git operation is aimed at it, **Then** it refuses, naming the path and the
   fact that it is not a worktree, and touches no repository — proven by a
   committed test asserting the operator repository's `HEAD` and status are
   unchanged.
3. **Given** a node path that does not exist at all, **When** a git operation is
   aimed at it, **Then** it refuses the same way — proven by a committed test.
   A missing directory resolves upward exactly as a husk does.
4. **Given** the husk refusal, **When** it is reached from the teardown salvage
   path and from `build reset`, **Then** both refuse — proven by committed tests
   for each. The finding records both routes; one fix that covers one route
   leaves the class open.
5. **Given** a node worktree nested inside the operator's checkout — which is
   where they live — **When** the check runs, **Then** it is recognised as a
   worktree and not as the operator's repository — proven by a committed test.

---

### User Story 5 - A probe workflow cannot be counted as an epic (Priority: P2)

As an operator, a workflow created by a probe or a test cannot be mistaken for a
running epic, so a leaked artefact never consumes a concurrency slot.

**Why this priority**: P2 and it depends on nothing. US1 through US3 should stop
new leaks; this story bounds the damage of the ones already on the namespace and
of any that get through.

**Acceptance Scenarios**:

1. **Given** a workflow id created by a probe, **When** it is constructed,
   **Then** it does not match the grammar `_list_open_epics` recognises — proven
   by a committed test asserting both the new id's shape and its exclusion.
2. **Given** a namespace holding a leaked probe workflow under the old `epic-`
   prefix, **When** open epics are listed, **Then** it is not counted — proven by
   a committed test over a supplied listing. The five already on the namespace
   predate any fix and must stop counting without being deleted first.
3. **Given** a real epic id, **When** open epics are listed, **Then** it is
   counted exactly as today — proven by a committed test. The grammar narrows
   for probes only.

## Requirements

- **FR-001**: Exactly one module in `factory/` MUST construct a real Temporal
  client. Every other module MUST obtain one from it.
- **FR-002**: The nine call sites listed in "Measured against `a58ec93`" MUST be
  migrated to that choke point, and their behaviour against a reachable control
  plane MUST be unchanged.
- **FR-003**: A committed test MUST walk `factory/**/*.py` and MUST fail, naming
  the file, if any module other than the choke point constructs a client
  directly.
- **FR-004**: The choke point MUST refuse to connect when `PYTEST_CURRENT_TEST`
  is set, and the refusal MUST name the address, the namespace, and the seam a
  test should bind.
- **FR-005**: Every refusal this spec introduces MUST carry a substring unique to
  it, and no two refusals reachable from one call path MAY share the substring a
  test asserts on.
- **FR-006**: `factory/worker.py`'s production start-up path MUST be unchanged
  outside pytest.
- **FR-007**: A second defence, independent of `PYTEST_CURRENT_TEST`, MUST refuse
  a production connection from a test process.
- **FR-008**: Either defence alone MUST refuse, and a test process MUST be able
  to connect only when both have been neutralised.
- **FR-009**: There MUST be exactly one sanctioned way to stand both defences
  down, and it MUST be the named opt-in of FR-010 — not a bare environment
  variable, not a file's presence, and not a credential.
- **FR-010**: A live tier MUST run only when it is named in an explicit opt-in.
- **FR-011**: The presence of a tier's credentials MUST NOT select that tier.
- **FR-012**: A tier that is named but whose credentials are absent MUST fail,
  naming the missing credential, and MUST NOT skip.
- **FR-013**: Naming one tier MUST arm that tier only.
- **FR-014**: A committed test MUST enumerate every live-tier test in `tests/`
  and MUST fail, naming the test, if any of them skips on a credential rather
  than on the opt-in.
- **FR-015**: A git operation aimed at a node path MUST verify that the path is a
  live worktree before running, and MUST refuse naming the path otherwise.
- **FR-016**: That refusal MUST fire before any repository is touched.
- **FR-017**: A node worktree nested inside the operator's checkout MUST be
  recognised as a worktree.
- **FR-018**: Both the `build reset` route and the teardown salvage route MUST go
  through the check of FR-015.
- **FR-019**: A workflow id created by a probe or a test MUST NOT match the
  grammar that identifies an epic.
- **FR-020**: Listing open epics MUST exclude ids that do not match that grammar,
  including workflows already on a namespace under the old prefix.
- **FR-021**: Listing open epics MUST count real epic ids exactly as it does
  today.

## Work Graph

```yaml
US1:
  depends_on: []
  persona: opus-closer
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006]
US2:
  depends_on: [US1]
  implements: [FR-007, FR-008, FR-009]
US3:
  depends_on: []
  implements: [FR-010, FR-011, FR-012, FR-013, FR-014]
US4:
  depends_on: []
  implements: [FR-015, FR-016, FR-017, FR-018]
US5:
  depends_on: []
  implements: [FR-019, FR-020, FR-021]
```

US2 depends on US1 because it hardens a choke point US1 creates; there is no
second defence to write until there is one place to write it in. US3, US4 and
US5 share no file with the first two and no file with each other: US3 is
`tests/` and `pyproject.toml`, US4 is the git helper and its two callers, US5 is
the epic-id grammar. FR-009 is US2's because standing the defences down is the
choke point's decision; US3 only supplies the name.

## Success Criteria

- **SC-001**: With `PYTEST_CURRENT_TEST` set and `TEMPORAL_ADDRESS` pointed at
  the operator's real control plane, call each of the ten migrated entry points
  and paste the ten refusals. None may reach the network.
- **SC-002**: Paste `grep -rn "Client.connect" factory/ --include=*.py`. Exactly
  one file may appear.
- **SC-003**: Neutralise the `PYTEST_CURRENT_TEST` refusal the way mutation M12
  did — replace its condition with a constant false — run the full suite, and
  paste the result together with `temporal schedule list` and `temporal workflow
  list` taken before and after. No schedule and no workflow may appear that was
  not there before. This is the incident of
  `hardening/mutating-a-production-safety-guard-escapes-the-sandbox`, re-run.
- **SC-004**: With `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` exported and no
  tier opted into, run the full suite and paste the skip line for the live
  Telegram test. Confirm no message arrived.
- **SC-005**: Opt into the Telegram tier with its credentials unset and paste the
  failure naming the missing credential.
- **SC-006**: Build a husk — a node worktree whose `.git` file has been deleted —
  aim `build reset` at it, and paste the refusal together with `git status
  --porcelain` and `git rev-parse HEAD` for the operator's checkout taken before
  and after. Both must be unchanged. Repeat for the salvage route.
- **SC-007**: Paste a listing that contains `epic-capacity-can-3d2bb231` and the
  open-epic count computed from it. The count must exclude it.

## Assumptions

- The nine unguarded call sites were enumerated against `a58ec93` on 2026-08-20.
  An implementer must re-enumerate rather than trust the table: this spec's own
  plan carries the anchors, and 072 exists because anchors go stale.
- `factory/worker.py:283` is in the table because a test that imports the worker
  must not connect, not because the worker's own start-up is suspect. FR-006
  states the constraint that keeps it working.
- The five leaked schedules named in
  `hardening/a-story-created-five-live-roadmap-schedules-that-paged-the-operator`
  were deleted by an operator on 2026-08-16 and are not this spec's to clean up.
  The leaked `epic-capacity-can-3d2bb231` workflow may still be on the namespace;
  US5 makes it stop counting rather than requiring it to be removed first.
- The second-order damage in that finding — `ergane roadmap status specs`
  resolving to a test's failed run — is **not** fixed here. It is a `_locate`
  defect, it survives independently of how the corpse got there, and folding it
  in would give US1 a second subject.
