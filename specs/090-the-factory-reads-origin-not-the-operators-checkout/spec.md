---
state: ready
fixes:
  - roadmap/clone-target-hard-resets-the-operators-own-checkout-every-tick-and-destroys-uncommitted-work
  - roadmap/dispatch-is-decided-by-the-operators-working-tree
# DRAFTED 2026-08-28 by the operator session, against ergane-buildout at 8bb2d4b.
# The directory was reserved — empty and untracked — by the spec-routing session
# on 2026-08-23 at 14:04, alongside 089 and 091-102.
#
# THE DEFECT IS ONE LINE, AND THE DOCSTRING ABOVE IT DISAGREES WITH IT.
# `_refresh_to_default` (`factory/activities/roadmap_activities.py:105`) says it
# refreshes "so the epic derives from the trunk's current head". It then does:
#
#     default = _default_branch(repo)          # :118
#     _git(repo, "fetch", "--quiet", "origin")
#     _git(repo, "checkout", "--quiet", default)
#     _git(repo, "reset", "--quiet", "--hard", f"origin/{default}")
#
# and `_default_branch` (`factory/workgraph/worktree.py:1265`) is
# `git symbolic-ref --short HEAD` — documented, correctly, as "the target
# clone's default branch (its current HEAD's symbolic ref)". So the docstring
# says *the trunk* and the code reads *whatever branch the operator happens to
# be standing on*, then hard-resets it to its own remote and derives the epic
# from it. Every 300 s.
#
# THE ANSWER IS ALREADY IN THE TREE, ONE MODULE OVER. 107-US3 landed
# `resolve_landing_base` (`factory/workgraph/worktree.py:1225`): it reads the
# manifest's `landing_branch` first, falls back to `_default_branch` only when
# the manifest is absent or malformed, and carries the arm that answered in
# `.source` so a caller can say which one did. `landing_branch()` (`:1254`)
# calls it "a *decision* about which branch matters for landing, replacing the
# three separate guesses the factory used to make." The landing path was
# converted (`factory/activities/merge_activities.py:437`) and the roadmap's
# refresh was not. This spec converts the last caller.
#
# WHY THIS IS THE PREREQUISITE IT IS. Three things wait on it. An operator
# branch that is unpushed stops the line at clone — measured at 6h34m and about
# 78 ticks, surfaced only as a bare `parked` count with no name in it. A pushed
# one is worse: the reset succeeds and the factory derives and lands epics
# against a feature branch as though it were the trunk. And there is no durable
# place in the operator's checkout for any authoring seam to write — uncommitted
# is destroyed by `reset --hard`, locally committed is destroyed too because the
# reset is to the remote ref, and a direct push to the landing branch is refused
# by ruleset. That is why the round-2 hand-over names this a hard prerequisite of
# its spec-authoring request, ahead of the seam itself.
#
# CHECKING OUT THE LANDING BRANCH IS NOT A WORKAROUND. A tick already in flight
# reads HEAD before the operator's checkout and writes it back after. Observed
# inside one second: `checkout: moving from spec/… to dev` immediately followed
# by `checkout: moving from dev to spec/…`, after which the factory ran on the
# feature branch for eight minutes while `git status` said working tree clean.
#
# NOT IN SCOPE. This spec does not add a spec-authoring verb, does not change
# how spec *state* is read once the clone is correct, does not touch
# `resolve_landing_base` itself (107 owns it and it is correct), and does not
# change the landing path (already converted). It also does not stop the roadmap
# resetting — a fetch-and-reset of the landing branch is the right behaviour and
# is what makes an epic derive from current trunk. It makes the roadmap reset
# the *right* branch, and refuse when resetting would destroy work.
---

# Feature Specification: the factory reads origin, not the operator's checkout

**Created**: 2026-08-28
**Depends on**: nothing outside this spec. All three stories edit
`factory/activities/roadmap_activities.py`, so they are serialised on file
ownership rather than on logic.

## The gap, stated precisely

The roadmap's pre-dispatch refresh answers the question "which branch does this
epic derive from?" by asking the operator's working copy which branch it has
checked out. That is not a property of the repository; it is a property of what
a human was doing thirty seconds ago.

Three consequences, all observed rather than reasoned about:

1. **It destroys work.** `reset --hard origin/<branch>` on whichever branch the
   operator is on discards uncommitted changes, and discards locally committed
   ones too, because the reset target is the remote ref.
2. **It builds against the wrong tree.** If that branch is pushed, the reset
   succeeds and the factory derives, dispatches and lands epics against a
   feature branch as though it were the trunk.
3. **It stalls the line silently.** If that branch is unpushed, `origin/<branch>`
   does not resolve, every tick fails at clone, and the operator's only signal
   is a `parked` count carrying no name.

The repository already knows the right answer — `landing_branch` is in the
manifest, and `resolve_landing_base` is the one derivation that reads it. The
roadmap simply does not call it.

## The rule this spec is asking for

**The branch the factory refreshes, derives from and dispatches against is the
one the manifest declares — and a refresh that would destroy uncommitted work
parks the spec instead.**

### What this spec is not

It is not a change to `resolve_landing_base`. That function landed with 107, is
the single derivation by design, and reports its own provenance. This spec adds
a caller.

It is not the removal of the reset. Fetching and hard-resetting the landing
branch is what makes each epic derive from the current trunk rather than from
whatever the clone last saw, and that is correct. The defect is the branch it
picks and its willingness to discard work to get there.

It is not spec-state routing. Reading a spec's `state:` from a working tree
rather than from origin is a related defect with its own key; once the clone is
refreshed to the declared branch, that read is against the right tree, which is
why both keys are declared here — but no story changes the reader.

## User Scenarios & Testing

### User Story 1 - The refresh follows the manifest, not the checkout (Priority: P1)

As an operator, the roadmap refreshes the branch my manifest declares, so what I
have checked out in my own clone cannot decide what the factory builds.

**Why this priority**: P1 and it depends on nothing. It is the defect. Every
other story here is a guard around it.

**Acceptance Scenarios**:

1. **Given** a target clone whose manifest declares `landing_branch: dev` and
   whose HEAD is on an unrelated branch `spec/x`, **When** the roadmap's clone
   activity runs, **Then** the clone is left on `dev` reset to `origin/dev`, and
   `spec/x` is neither checked out nor reset — proven by a committed test.
2. **Given** the same clone, **When** the activity returns, **Then** the result's
   branch field names `dev` and its head field names `origin/dev`'s SHA —
   proven by a committed test.
3. **Given** a clone whose manifest is absent or malformed, **When** the activity
   runs, **Then** it falls back to the checked-out HEAD exactly as
   `resolve_landing_base` already does, and the result records that the fallback
   arm answered — proven by a committed test. Failing open is 107's decision and
   this story inherits it rather than re-litigating it.
4. **Given** any clone, **When** the activity runs, **Then** the branch it used
   came from `resolve_landing_base` and not from a second call to
   `_default_branch` — proven by a committed test that patches the one seam and
   observes the other is never reached.

### User Story 2 - A refresh that would destroy work parks the spec instead (Priority: P1)

As an operator, the factory refuses to discard changes in my clone that I have
not pushed, and tells me which spec it parked and why.

**Why this priority**: P1. US1 makes the common case safe by never touching the
operator's own branch, but an operator working directly on the landing branch is
still exposed, and that is the case where the reset is least expected.

**Acceptance Scenarios**:

1. **Given** a clone on the declared landing branch with an uncommitted
   modification to a tracked file, **When** the roadmap's clone activity runs,
   **Then** it parks the spec naming the dirty paths and performs no reset, and
   the modification is still present afterwards — proven by a committed test.
2. **Given** a clone on the declared landing branch carrying a local commit that
   is not on `origin/<branch>`, **When** the activity runs, **Then** it parks
   naming the unpushed commit and performs no reset — proven by a committed
   test. The reset target is the remote ref, so a local commit is destroyed just
   as surely as an uncommitted change.
3. **Given** a clean clone on the declared landing branch, **When** the activity
   runs, **Then** it fetches and resets exactly as it does today — proven by a
   committed test. This story adds a refusal, not a behaviour change on the
   path that was always safe.
4. **Given** untracked files that the target repo's `.gitignore` covers, **When**
   the activity runs, **Then** they do not park the spec — proven by a committed
   test. A reset does not discard ignored files, so treating them as work at
   risk would park every clone that has ever run a build.

### User Story 3 - The tick says which branch it used and who named it (Priority: P2)

As an operator, I can read from the roadmap's own record which branch a tick
refreshed, which arm named it, and what head it landed on.

**Why this priority**: P2. It does not change what the factory builds, but the
6h34m outage this spec exists to prevent was extended by the absence of exactly
this line.

**Acceptance Scenarios**:

1. **Given** a manifest that declares the landing branch, **When** the clone
   activity completes, **Then** its result carries the arm that answered as a
   distinguishable value, not only the branch name — proven by a committed test.
2. **Given** a clone that fell back to the checked-out HEAD, **When** the
   activity completes, **Then** the fallback is recorded with the loader's own
   complaint, so an operator learns why the guess was made — proven by a
   committed test.
3. **Given** a spec parked by US2's refusal, **When** the operator reads the park
   reason, **Then** it names the branch, the paths at risk, and the act that
   would clear it — proven by a committed test.

## Work Graph

```yaml
US1:
  implements: []
  depends_on: []
US2:
  implements: []
  depends_on: []
  depends_on_merged: [US1]
US3:
  implements: []
  depends_on: []
  depends_on_merged: [US2]
```

All three stories change `_refresh_to_default` and the `CloneResult` it returns
in `factory/activities/roadmap_activities.py:100-140`, so they are serialised on
file ownership rather than on logic. US2's refusal is also easier to write once
US1 has made the branch a known quantity rather than a read of HEAD.

## Requirements

- **FR-001**: The roadmap's clone activity MUST obtain the branch it refreshes
  from `resolve_landing_base`, and MUST NOT call `_default_branch` directly.
- **FR-002**: The clone activity MUST leave the clone checked out on that branch
  and reset to its remote ref, and MUST NOT check out or reset any other branch.
- **FR-003**: The clone activity MUST refuse, and the workflow MUST park the
  spec, when the clone carries an uncommitted change to a tracked file or a
  commit absent from the remote ref it would reset to.
- **FR-004**: The refusal MUST name the branch, the paths or commits at risk,
  and the operator act that clears the refusal.
- **FR-005**: Files the target repository ignores MUST NOT trigger the refusal.
- **FR-006**: The clone result MUST carry which arm named the branch, and when
  the fallback arm answered it MUST carry the reason.
- **FR-007**: A clean clone on the declared landing branch MUST be refreshed
  exactly as it is today.
- **FR-008**: Every story MUST leave `resolve_landing_base` and
  `_default_branch` (`factory/workgraph/worktree.py:1225`, `:1265`) unchanged.

## Success Criteria (summary)

- An operator can hold any branch checked out in the target clone, with
  uncommitted work on it, while the roadmap ticks — and find that work intact
  and the epic built against the declared landing branch.
- An unpushed operator branch can no longer stall the line, because the roadmap
  never resolves `origin/<that branch>` in the first place.
- A parked spec names the branch and the work that parked it, so the diagnosis
  is a line of output rather than an inspection of the reflog.
