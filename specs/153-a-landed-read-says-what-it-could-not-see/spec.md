---
state: draft
fixes:
  - gates/landing-read-is-blind-on-the-runner
  - gates/merge-group-ref-slows-first-paint-past-assertion
# DRAFTED 2026-09-04 by the refinement workflow (refinement-2026-09-04) from
# docs/triage-2026-09-03-ergane-web-round3.md § "a-landed-read-says-what-it-could-not-see"
# (lines 419-436), against ergane-buildout at 602a92c. Every `file:line` in
# spec.md and plan.md was read from that commit with `sed -n 'Np'` and verified
# to resolve to the symbol named, not recalled.
#
# WHERE THIS CAME FROM. The P3 staged entry of the `ergane-web` round-3 triage,
# which graded two reporter claims down and kept what survived a refutation
# pass. Both keys were minted 2026-09-03 by that triage and both are open with
# one occurrence: `gates/landing-read-is-blind-on-the-runner` at `warning`,
# `gates/merge-group-ref-slows-first-paint-past-assertion` at `info`. The second
# key's NAME describes a merge-group timing claim that was refuted; its SUMMARY
# and notes scope it to one surviving residue, and this spec is cut from the
# summary. Read the row, not the name.
#
# WHAT IT COST, MEASURED. Nothing yet, and that is the whole reason it is P3.
# The reporter's trigger — a landing read on a forge runner's shallow checkout —
# was refuted: no `landed_facts` call site runs on a runner, the workflow
# `ergane init --wire` generates never invokes `ergane`, and no `--depth` exists
# anywhere in `factory/`. What was NOT refuted is the code defect, and this
# refinement re-reproduced it at 602a92c on a depth-1 clone of this repository:
# `landed_facts` returns US1/US2/US3 of 126 all ATTESTED at the shallow head,
# where the full clone returns them OBSERVED at d5119a8/8d5102e/94c8cd8. The
# read is not merely blind; it pins the wrong commit and hands that to the
# fingerprint baseline. Cost so far: zero. Cost if a target clone is ever made
# shallow: a delta derived against a baseline that never happened.
#
# NOT IN SCOPE. Do NOT add `fetch-depth: 0` to the workflow `ergane init --wire`
# generates — no landing read runs there and that half of the reporter's ask
# builds nothing while changing every consumer's CI. Do NOT change `fetch=True`
# on the derive paths (factory/workgraph/cli.py:452,
# factory/activities/roadmap_activities.py:409 and :532), which must not read a
# stale baseline. Do NOT shorten `GIT_TIMEOUT_S`; the 300s-versus-5s comparison
# in the source finding is a category error across two repositories, and the
# real 300s exposure was fixed on 2026-08-26. Most of the second half already
# landed under 046 FR-002 and 052 — this spec rebuilds none of it and touches
# exactly one verb.
#
# NEIGHBOURS CHECKED. `git log --since=2026-09-01` over every file this spec
# touches returns four commits, all from 125 and 126 and all before the triage's
# own baseline; the four 057 landings between 238b494 and 602a92c touch
# `factory/cli/init.py`, `factory/mergequeue/onboard.py` and their tests and
# reach none of this spec's files. Every anchor the source entry cites was
# re-read and every one of them still says what the entry claims, with two
# corrections recorded in plan.md: the generated workflow lives at
# `factory/mergequeue/wiring.py`, not `wiring.py` at the repository root as the
# entry writes it, and the shallow head the reproduction pins is now a node
# landing rather than the operator commit the entry measured at 238b494.
#
# THREE HAZARDS THIS REFINEMENT ADDED, NONE OF THEM IN THE SOURCE ENTRY. The two
# exit-code vocabularies disagree by one (`EXIT_TRANSPORT` is 2 in
# `factory/workgraph/cli.py` and 3 in `factory/cli/errors.py`, where 2 means
# usage) and only the RAISE path is translated. Existing tests construct the
# verb's `args` as a bare class with two attributes, so a new flag read without
# a default breaks them for a reason this spec is not about. And a degraded read
# that still prints today's rescue suggestion is advice to open a duplicate
# landing for a story that landed invisibly — the honesty gap turned expensive.
# All three are traps 6, 7 and 8 in plan.md.
---

# Feature Specification: a landed read says what it could not see

**Created**: 2026-09-04
**Depends on**: nothing.

## The gap, stated precisely

One function decides what the factory believes has landed, and it cannot tell
"nothing landed" from "I could not see". The chain is seven steps.

1. `factory/workgraph/landed.py:130` — `landed_facts` is the single reader. Four
   call sites share it: derivation, drift detection, `ergane status` and
   `ergane spec landed`.
2. It resolves a head through `factory/workgraph/landed.py:257` —
   `_resolve_default_head`, which raises only when the ref cannot resolve at all.
   A shallow clone resolves its head perfectly well, so nothing refuses here.
3. It then scans with `factory/workgraph/landed.py:290` — `_git_log_subjects`, a
   bare `git log` over that head. It asserts nothing about how much history the
   clone holds, because git's own output for a truncated history and for a short
   history is the same output.
4. Finding no attributed commit, the attestation fallback at
   `factory/workgraph/landed.py:229` runs.
   `factory/workgraph/landed.py:360` — `_attesting_commit` walks the truncated
   log, `rev-parse <commit>^` fails at the graft boundary, and the
   `except WorktreeError` at `factory/workgraph/landed.py:375` treats that as
   "root commit: it is the introduction if it attests" — so **every** story is
   pinned ATTESTED at the shallow head.
5. Reproduced at 602a92c on a depth-1 clone of this repository: the three stories
   of `126-a-killed-node-leaves-no-ref-to-collide-with` come back ATTESTED at the
   shallow head, where the full clone returns them OBSERVED at d5119a8, 8d5102e
   and 94c8cd8. For a spec whose frontmatter is not attested `landed`, the same
   read returns the empty mapping instead — indistinguishable from the honest
   "no story has landed" that `tests/test_landed.py:587` —
   `test_unattested_unattributed_spec_yields_empty_baseline` asserts for a real
   repository.
6. That result is the fingerprint baseline: `factory/activities/roadmap_activities.py:409`
   inside `factory/activities/roadmap_activities.py:393` — `_derive_from_git`
   compiles the delta against it, and `factory/activities/roadmap_activities.py:532`
   inside `factory/activities/roadmap_activities.py:511` — `_drift_from_git`
   compares fingerprints pinned at it. A wrong pin is a wrong answer about what
   to build, delivered with no hint that anything was unreadable.
7. Nothing anywhere measures this. `grep -rn 'shallow' factory/ --include=*.py`
   returns five hits, every one of them prose about bind ordering or header
   nesting, and `rev-parse --is-shallow-repository` appears nowhere in the tree.

The second honesty gap is in the one verb an operator points at this reader by
hand. `factory/workgraph/cli.py:168` — `landed_command` calls the reader at
`factory/workgraph/cli.py:188` with the networked default, has no way to opt out
of the fetch, and turns any failure into
`_OperatorError(f"cannot read landed facts for {epic_id}: ...")` at
`factory/workgraph/cli.py:190-192` — a user error, as though the operator had
typed something wrong. The sibling reporting path already knows better:
`factory/cli/status.py:378` — `_readiness_basis` passes `fetch=False` at
`factory/cli/status.py:403` and returns a named degradation at
`factory/cli/status.py:404-411` when the branch cannot be read.

## The rule this spec is asking for

**A landing read that cannot see the history says so, in a named degradation
that no caller can mistake for the fact that nothing has landed.**

The three cases, complete:

| history | spec attested `state: landed` | today | with this spec |
|---|---|---|---|
| complete | either | facts as scanned | **unchanged, byte for byte** |
| incomplete | yes | every story ATTESTED at the shallow head | **named degradation, no facts returned** |
| incomplete | no | `{}` — the same answer as "nothing landed" | **named degradation, no facts returned** |

And the verb's two inputs, which combine:

| `--no-fetch` | the read | today | with this spec |
|---|---|---|---|
| absent | succeeds | facts printed, exit 0 | unchanged |
| **present** | succeeds | **flag does not exist** | facts printed without touching the network, exit 0 |
| either | fails | `cannot read landed facts for <epic>`, exit 1, nothing printed | named degradation, declared stories printed as unconfirmed, no rescue suggestion, transport exit |

### What this spec is not

It is not a change to what the factory clones. Nothing in `factory/` passes
`--depth`, and this spec adds nothing that does; the shallow repository is one an
operator builds. What changes is that such a repository becomes loud instead of
wrong.

It is not a relaxation of the fetching default on the deciding paths. Derivation
and drift detection keep `fetch=True` at `factory/workgraph/cli.py:452`,
`factory/activities/roadmap_activities.py:409` and
`factory/activities/roadmap_activities.py:532`, because a decision about what to
build may not be made against a stale baseline.

It is not the reporter's original ask. The generated workflow at
`factory/mergequeue/wiring.py:143` — `render_gates_workflow` gains no
`fetch-depth`, because no landing read runs there.

It is not a rewrite of the reporting callers. `factory/cli/status.py:483` and
`factory/cli/nouns/build.py:1114` already pass `fetch=False`; 046 FR-002 and 052
did that work and this spec leaves it alone.

## User Scenarios & Testing

### User Story 1 - The read measures the history before it trusts it (Priority: P1)

As the factory, when I am asked what has landed and the repository cannot show me,
I say that I cannot see rather than inventing a commit.

**Why this priority**: P1 and it depends on nothing. It is the half that can give a
wrong answer rather than no answer, and the second half needs a degradation
vocabulary to report before it can report one.

**Independent Test**: Build one repository with a real landing, clone it twice —
once complete, once at depth 1 — and read both.

**Acceptance Scenarios**:

1. **Given** a repository whose history is complete and one whose history is
   truncated, both holding the same attested spec, **When** each is read, **Then**
   a committed test asserts the complete read returns the story pinned at its real
   landing commit while the truncated read raises a degradation whose message names
   the incomplete history, and the pair fails on any diff that changes only one of
   them.
2. **Given** a truncated history and a spec whose frontmatter is **not** attested
   `state: landed`, **When** it is read, **Then** a committed test asserts the read
   raises the same named degradation, and asserts in the same test that a
   *complete* history over the same unattested spec still returns the empty mapping
   — so the diff proves the two answers are no longer the same answer.
3. **Given** a repository whose history is complete, **When** it is read, **Then**
   a committed test asserts the returned facts equal, entry for entry, the facts
   the reader returns today, and that the measurement it added costs exactly one
   additional git invocation.
4. **Given** a target clone whose history is truncated, **When** the derivation
   path reads its baseline, **Then** a committed test asserts it refuses with a
   message naming the incomplete history instead of compiling a graph against
   stories pinned at the shallow head.
5. **Given** a specs root held by a repository whose history is truncated, **When**
   the readiness basis is computed, **Then** a committed test asserts its detail
   sentence names the incomplete history, and asserts it does **not** contain the
   phrase this code emits today claiming landings on the branch were read.

### User Story 2 - The one verb an operator aims at the reader can read offline, and reports what it could not see (Priority: P2)

As an operator asking which of a spec's stories have landed, I can ask without the
network, and when the answer cannot be trusted I am told which fact is missing
rather than told I made a mistake.

**Why this priority**: P2 and it consumes the vocabulary US1 introduces. It is the
platform residue the second key is scoped to, and it is the last landing read in
the tree still taking the networked default.

**Independent Test**: Run the verb against a spec directory with and without the
new flag, and against a repository whose landing branch cannot be resolved.

**Acceptance Scenarios**:

1. **Given** the verb invoked with `--no-fetch`, **When** it reads, **Then** a
   committed test asserts the reader is called with `fetch=False`, proven by a
   recorded call rather than by the absence of network traffic.
2. **Given** the verb invoked without the flag, **When** it reads, **Then** a
   committed test asserts the reader is called with the fetching default, and the
   same test drives the handler with an argument object that carries neither the
   new flag nor `as_json` and asserts it still succeeds — so the pair fails any
   diff that reads the flag without a default.
3. **Given** a repository whose landing branch cannot be resolved on this ref,
   **When** the verb runs, **Then** a committed test asserts the message names the
   degradation and the branch it could not reach, and asserts the string
   `cannot read landed facts for` does not appear in it.
4. **Given** that same degraded read, **When** the verb renders its report,
   **Then** a committed test asserts every story the spec declares is printed as
   unconfirmed, and asserts that neither the rescue pull-request title nor the
   rescue trailer appears anywhere in the output — because a rescue opened for a
   story that landed invisibly duplicates a landing.
5. **Given** that same degraded read invoked through the noun's handler, **When**
   it returns, **Then** a committed test asserts the exit code is the unified
   transport code `3` and asserts it is neither `1` nor `2`, and a second assertion
   in the same test covers the `--json` form, whose document carries the
   degradation as a field beside `facts`.

## Functional Requirements

- **FR-001**: A single named helper in `factory/workgraph/landed.py` MUST answer
  whether a repository's history is complete, by asking git rather than by
  inferring it from a scan's result, and both `landed_facts` and the readiness
  basis MUST ask that one helper so the two doors cannot drift.
- **FR-002**: On an incomplete history `landed_facts` MUST raise a degradation
  named for that condition and MUST NOT return facts — in particular neither an
  ATTESTED fact pinned at the truncated head nor the empty mapping that means no
  story has landed.
- **FR-003**: The degradation MUST be raised by `landed_facts` itself before the
  history scan begins, and MUST be a subclass of `WorktreeError`, so it cannot be
  swallowed by the `except WorktreeError` inside
  `factory/workgraph/landed.py:360` — `_attesting_commit` and so
  `factory/cli/status.py:469` — `_observed_landing` keeps degrading to its
  documented "any doubt is `None`" rather than failing.
- **FR-004**: On a complete history the facts returned MUST be identical to
  today's, and the measurement MUST add exactly one git invocation.
- **FR-005**: When the repository holding the specs root has an incomplete
  history, `factory/cli/status.py:378` — `_readiness_basis` MUST report a detail
  naming that condition instead of the sentence at
  `factory/cli/status.py:413-419` claiming landings on the branch were read.
- **FR-006**: `ergane spec landed` MUST accept a `--no-fetch` flag that passes
  `fetch=False` to the reader, the opt-out the reader's own contract already
  grants a read-only caller at `factory/workgraph/landed.py:147`.
- **FR-007**: Without the flag the verb MUST keep today's fetching default, and
  the handler MUST read the flag with a default so an argument object that does
  not carry it — the shape `tests/test_landed.py:350` already constructs — keeps
  working.
- **FR-008**: When the read fails, the verb MUST report a named degradation
  identifying what could not be seen, carrying git's own reason, instead of the
  user error `cannot read landed facts for <epic>` at
  `factory/workgraph/cli.py:190-192`.
- **FR-009**: A degraded run MUST print every story the spec declares as
  unconfirmed and MUST NOT print the rescue pull-request title or the rescue
  trailer for any of them — the output at `factory/workgraph/cli.py:230-238` and
  its `--json` counterpart at `factory/workgraph/cli.py:209-221` — because that
  suggestion, followed, duplicates a landing the read could not see.
- **FR-010**: A degraded run MUST exit with the unified transport code defined at
  `factory/cli/errors.py:26`, and MUST NOT exit with the user code or with the
  usage code at `factory/cli/errors.py:25`.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-006, FR-007, FR-008, FR-009, FR-010]
```

One `depends_on_merged` edge, declared rather than left to inference (069-US2
FR-007). US2's FR-008 must name an incomplete history among the degradations it
reports, and that condition does not exist until US1 raises it; a US2 built first
would have only the unreachable-branch case to report and would land a message
vocabulary that has to be widened again. The two stories share no production
file — US1 is `factory/workgraph/landed.py` and `factory/cli/status.py`, US2 is
`factory/workgraph/cli.py` and `factory/cli/nouns/spec.py` — so the edge buys
correct sequencing rather than freedom from contention, and no `concurrent_with`
override is needed.
