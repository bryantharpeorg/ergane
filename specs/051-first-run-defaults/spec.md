---
state: landed
# Attested landed 2026-08-16 by an operator session, after `ergane spec landed
# specs/051-first-run-defaults --default-branch ergane-buildout` observed both
# stories in git. Each passed the real bwrap boundary gate and an LLM judge on a
# diff that fit whole, judged on `ollama-cloud/glm-5.2` through the operator's
# own proxy: US1 5 of 5 at 46,058 bytes, US2 4 of 4 at 33,562.
#
# Two things this epic proved that its own spec had wrong:
#
# SC-001's literal reproduction cannot pass, and no implementation could make
# it. `git init . && ergane init` with no commit produces a repository with no
# refs at all, so the landing_branch check fails whatever the interview offers.
# That case is governed by US1-S3/FR-002 -- offer the literal, complete, exit 0
# -- and it does. The committed transcript covers both shapes rather than the
# one that flatters the story.
#
# "Flipping the default moves nothing that runs" was true of the worker and
# FALSE of the gate. `factory/verify/gates.py:96` is a strict env allowlist, so
# TEMPORAL_NAMESPACE never reaches a gate command, and `:495` does not unshare
# the network -- so before US2, `tests/test_live_capacity.py` dialled the
# production `factory` namespace from inside a gate sandbox. After it, the
# namespace does not exist and the SDK's heartbeat loop retried NOT_FOUND, so a
# suite HUNG rather than failing. US2 moved that failure back into the guard as
# a declared scope addition; without it the story could not pass its own gate.
# That is also where the probe workflows found running on the production
# namespace for up to fourteen hours came from.
# Drafted 2026-08-16 by an operator session, from two findings produced the same
# afternoon by walking the portability path on a machine that had never seen this
# project: a Debian 13 container, Python 3.12, git 2.47, the wheel from
# `uv build` installed with pip, and nothing else. No checkout, no
# ~/.config/ergane, no Temporal, no gh.
#
#   init/the-landing-branch-default-is-a-literal-not-the-repositorys-branch
#   install/two-defaults-for-the-temporal-namespace-disagree
#
# They are one spec because they are one defect wearing two hats: a default that
# is correct on the machine Ergane was written on and wrong on a stranger's.
# Neither was reasoned into existence and neither is hypothetical -- the first
# was read off a transcript, the second created a live schedule on the
# operator's production namespace that had to be paused by hand.
#
# Two stories, split by what kind of thing is wrong rather than by file. US1 is
# a default that should have been a reading. US2 is one fact spelled twice.
# Each is independently valuable and decidable from its own diff.
#
# Deliberately NOT in scope: `ergane init` exiting 0 while checks fail. That was
# re-measured at drafting time -- without a pipe, because a piped `echo $?`
# reports the pipe's status and nearly produced a third, false finding -- and it
# is correct as built. `init.py:459-464` documents the choice and
# 050-init-preconditions records it in its own Out of Scope. Do not relitigate it
# here.
---

# Feature Specification: 051-first-run-defaults

**Created**: 2026-08-16

## Context

The shortest possible first run of this product, on a machine with a stock git
configuration, is:

```
$ git init . && ergane init      # press enter through the interview
```

It ends with a failed check. Verbatim from the container transcript:

```
  [FAIL] landing_branch: the manifest declares `landing_branch: main` but
  /work/fresh has no such branch; create it with `git -C /work/fresh branch
  main`, or declare the branch this repository actually lands on
```

The message is good — it names the cause and offers two remedies. The defect is
that the operator should never have seen it. `git init` created `master`; the
interview offered `main`; and **the tool already knew which branch the
repository was on** when it asked.

`factory/cli/init.py:256` is the whole cause:

```python
    "landing_branch": "main",
```

a hardcoded interview placeholder, never derived from the repository being
joined. git 2.47 still defaults `init.defaultBranch` to `master` and only prints
a hint about it. A machine that sets `init.defaultBranch = main` — this
project's boxes, and most developer machines configured after 2020 — creates
`main`, and the placeholder is then accidentally correct. A stock CI image or a
fresh cloud VM is not that machine.

The same shape, one layer down, decides where an operator's work is scheduled:

| site | value |
| --- | --- |
| `factory/cli/install.py:71` — the install interview's seed | `ergane` |
| `factory/notify/service.py:111` — `DEFAULT_TEMPORAL_NAMESPACE` | `factory` |

An operator who presses enter through `ergane install` declares `ergane`.
Anything reaching the code fallback gets `factory` — which is *this
repository's own namespace*, the value `scripts/ergane-env.sh` exports and the
one this project's floor runs in. It reads like a constant that was right when
the factory was the only deployment and was never revisited when the product
grew an installer.

That disagreement is not theoretical. On 2026-08-16 an `env -i` run of
`ergane init` with no config found a live control plane on `factory`, passed
every readability check, and created the schedule `ergane-roadmap-repo` in a
namespace the operator had never named. It had to be paused by hand.

050-init-preconditions stops that on a *fresh* machine, where nothing is
listening and the schedule step refuses. It does not stop it on a machine that
already runs a control plane on `factory`, which is every developer box in this
project. That residue is US2's, and 050's plan carries a trap saying so and
telling that story's implementer not to chase it.

## What a portable default means here

A default is a **guess about the operator's world**. This spec draws one line
through both stories:

- A default that can be **read from the world** must be read, not guessed.
  The repository's current branch is a fact on disk; asking about it while
  offering a different answer is the tool disagreeing with something it can see.
- A default that **cannot** be read must be spelled **once**. Two literals for
  one fact is not redundancy; it is a disagreement waiting for the one caller
  that reaches the second one.

Neither story removes the operator's ability to answer differently. The
interview is a question, and it stays a question — this is about what it offers
before the operator types, not about what it will accept.

## User Scenarios & Testing

### User Story 1 - The interview offers the branch the repository is actually on (Priority: P1)

As an operator joining a fresh repository on a stock machine, the landing-branch
question offers the branch I am on, so pressing enter produces a manifest that
passes its own readiness check.

**Why this priority**: it is the first command the runbook tells a new user to
type, and it currently ends in a red line on any machine that has not opted into
`init.defaultBranch = main`. First-impression confidence is the whole of the
cost, and it is paid by exactly the users this product is trying to win.

**Independent Test**: `git init` a repository on a machine whose git creates
`master`, run the interview accepting every default, and confirm the resulting
manifest's `landing_branch` check passes.

**Acceptance Scenarios**:

1. **Given** a repository whose current branch is `master`, **When** the
   interview presents the landing-branch question, **Then** the offered default
   is `master` — proven by a committed test asserting the prompt text, not the
   accepted value.
2. **Given** the same repository, **When** the operator presses enter, **Then**
   the written manifest declares `master` and the `landing_branch` readiness
   check passes — proven by a committed test that runs the real check against
   the real written file, never against a constructed profile.
3. **Given** a repository with **no commits and no resolvable HEAD**, **When**
   the interview runs, **Then** it offers the existing literal rather than
   failing, and `ergane init` completes — proven by a committed test. An empty
   repository is a normal thing to join and must not become an error.
4. **Given** an operator who types a branch name, **When** it differs from the
   repository's current branch, **Then** the typed value wins unchanged —
   proven by a committed test. This is a default, not a constraint.
5. **Given** a repository already joined, **When** `ergane init` is re-run,
   **Then** the existing manifest's `landing_branch` is offered as the default
   ahead of the repository reading — proven by a committed test. Re-running init
   in a joined repository reconciles what is declared; it must not silently
   re-point a repository at whatever branch happens to be checked out.

---

### User Story 2 - The Temporal namespace is one fact, spelled once (Priority: P2)

As an operator, the namespace my install declares and the namespace an
unconfigured command falls back to cannot disagree, because a schedule created
in the wrong one is invisible in the right one.

**Why this priority**: P2 because 050-init-preconditions removes the loud case —
the schedule created against a control plane that is not there. What survives is
quieter and worse: a schedule created against a control plane that *is* there
and is not the operator's.

**Independent Test**: read both sites and confirm exactly one literal exists;
then resolve the namespace with nothing declared and nothing exported, and
confirm the value is the one the install interview would seed.

**Acceptance Scenarios**:

1. **Given** the shipped package, **When** it is swept for a Temporal-namespace
   default, **Then** exactly one literal exists and every other site derives
   from it — proven by a committed sweep with an anti-vacuity assertion that the
   file list it read is non-empty and contains both modules by name.
2. **Given** no config and no environment, **When** the namespace is resolved,
   **Then** the value is the same one `ergane install` seeds its interview with
   — proven by a committed test asserting the two are the same object or the
   same name resolved from one source, never two equal string literals.
3. **Given** a config that declares a namespace, **When** the namespace is
   resolved, **Then** the declaration wins over the single default — proven by a
   committed test. Unifying the defaults must not disturb the precedence
   048-declared-control-plane landed.
4. **Given** the diff, **When** `factory/notify/service.py` and
   `factory/cli/install.py` are read, **Then** neither spells a namespace the
   other does not derive from — proven by the same sweep, so the guard fails on
   a re-leak rather than on a count.

## Functional Requirements

- **FR-001**: The landing-branch interview default MUST be read from the
  repository being joined, using its current branch.
- **FR-002**: When the repository has no resolvable HEAD, the interview MUST
  fall back to the existing literal and MUST NOT fail.
- **FR-003**: An operator-supplied landing branch MUST override the derived
  default unchanged.
- **FR-004**: When a manifest already declares a landing branch, that value MUST
  be offered ahead of the repository reading.
- **FR-005**: The default landing branch MUST NOT be presented as a value the
  tool has verified; it is an offer, and the readiness check remains the verdict.
- **FR-006**: Exactly one literal for the default Temporal namespace MUST exist
  in the shipped package. Every other site MUST derive from it.
- **FR-007**: The value the install interview seeds MUST be the same value an
  unconfigured resolution yields.
- **FR-008**: The precedence 048-declared-control-plane established —
  environment over declaration over default — MUST be unchanged.
- **FR-009**: A sweep MUST hold FR-006 by path, with an anti-vacuity assertion
  that it read a non-empty file list containing both modules by name.
- **FR-011**: The single literal FR-006 requires MUST read `ergane`. Decided by
  the operator on 2026-08-16. `factory` is this repository's own deployment name
  and a product default may not be one installation's proper noun.
- **FR-012**: `scripts/ergane-env.sh` MUST NOT be edited by this spec. It is the
  operator's own pin and the reason FR-011 is safe; see the note below.
- **FR-010**: The number of questions `ergane init` asks MUST be unchanged, and
  no manifest key MUST be added. Each story MUST change what a question *offers*,
  never how many there are. `ergane init` generates its interview from
  `_TOP_LEVEL_KEYS` and nine test files script that interview with fixed answer
  lists, so one new key breaks all nine.

## Why flipping the default does not move this floor

FR-011 sounds like it should require a migration. It does not, and the reason was
measured at `3d08d90` rather than reasoned:

```
scripts/ergane-env.sh:77   emit TEMPORAL_NAMESPACE "${TEMPORAL_NAMESPACE:-factory}"
ergane-worker-run.sh:18    eval "$(scripts/ergane-env.sh)"
ergane-worker.service:15   ExecStart=…/ergane-worker-run.sh
```

The live worker is a systemd user unit whose `ExecStart` runs a wrapper that
evals `ergane-env.sh`, which exports `TEMPORAL_NAMESPACE=factory` **explicitly**.
Under the precedence 048-declared-control-plane landed — environment over
declaration over default — the export wins and the code default is never
consulted. There is no `~/.config/ergane/config.toml` on that host at all; this
operator has never run `ergane install`.

So changing the constant to `ergane` moves nothing that is running. What it
changes is what a *stranger's* machine gets, which is the entire point.

The consequence worth stating plainly: after this lands, **`scripts/ergane-env.sh`
is the only thing pinning this floor to `factory`**. That is a per-repository
operator script, not the product, which is where a deployment's own name belongs.
Editing it and the constant in the same change is what would move the worker, so
FR-012 forbids touching it here.

## Success Criteria

- **SC-001**: On a machine whose git creates `master`, `git init . && ergane
  init` with every default accepted produces a manifest whose `landing_branch`
  check passes. The evidence is a committed transcript, since this is a claim
  about a machine.
- **SC-002**: The count of Temporal-namespace literals in the shipped package is
  exactly one, asserted by a test rather than by reading.
- **SC-003**: `ergane init --check` reports the same verdicts as before this spec
  for a repository whose branch already matched its manifest — this spec changes
  what is offered, not what is judged.
- **SC-004**: The number of questions `ergane init` asks is unchanged, and no
  scripted-interview answer list in `tests/` is edited.

## Out of Scope

- **`ergane init` exiting 0 while checks fail.** Correct as built and documented
  at `factory/cli/init.py:459-464`; already recorded in 050's Out of Scope. It
  was re-measured at drafting time and the earlier contrary reading was a
  measurement error — a piped `echo $?` reports the pipe's status.
- **Changing what this repository's own floor runs in.** The value question is
  answered — see FR-011 — but the answer must not move the operator's worker,
  and the reason it does not is measured rather than assumed. See the note
  below.
- **Any other interview default.** The schema version, runtime backend, gates and
  dials are not facts on disk in the way a branch is. Deriving them is a
  different argument and does not belong in this spec's evidence.
- **`ergane --version` reporting `localhost:7233` on an unconfigured machine.**
  Fixed by 048-declared-control-plane/US4, which routes all eleven connect sites
  through one resolver. Checked before drafting so this spec would not re-file it.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-010]
US2:
  depends_on: []
  implements: [FR-006, FR-007, FR-008, FR-009, FR-011, FR-012]
```

The two stories touch disjoint files and neither needs the other to exist, so
there is no `depends_on_merged` edge between them. They are one spec because
they are one lesson, not because they are one change.
