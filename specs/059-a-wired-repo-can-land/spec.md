---
state: ready
# Flipped draft -> ready 2026-08-19 ~12:15 AM CT at the operator's instruction.
# Ready is eligibility, not dispatch. This is the first of the six on-ramp specs
# and should be dispatched first: every other spec's end-to-end verification
# assumes a repository that can land, and 061 declares a hard dependency on it.
#
# Drafted 2026-08-18 ~11:50 PM CT by an operator session, from a first-time
# install report filed by an agent installing `ergane-cli 0.1.0` from PyPI onto
# a fresh Linux host against a new org-owned GitHub repository.
#
# Both defects were verified against the tree before this was written:
#
#   1. `allow_auto_merge` appears NOWHERE in `factory/`. Verified by
#      `grep -rn allow_auto_merge factory/` returning nothing. `wire_repo`
#      (`factory/mergequeue/wiring.py:250`) runs exactly three steps --
#      `_squash_title_step`, `_queue_step`, `_divergence_step` -- and none of
#      them touch the repository's auto-merge flag.
#   2. `_require_public` (`factory/mergequeue/wiring.py:307`) branches on
#      `visibility` alone. No owner-type check exists anywhere in
#      `factory/mergequeue/`.
#
# The reporter's measured matrix, which this spec treats as the requirement:
#
#     owner type    | visibility | plan | `merge_queue` ruleset rule
#     User          | public     | free | 422
#     Organization  | private    | Team | 422
#     Organization  | public     | free | works
#
# Confirmed independently against GitHub's own documentation before drafting,
# because the existing remedy text already cost this project money and a second
# wrong remedy would be worse than the first. GitHub's availability sentence:
#
#   "Pull request merge queues are available in any public repository owned by
#    an organization, or in private repositories owned by organizations using
#    GitHub Enterprise Cloud."
#
# That one sentence confirms both halves of US2 and is close to the wording the
# refusal should carry.
#
# Filed as findings before drafting:
#   mergequeue/wiring-never-enables-the-auto-merge-its-own-driver-requires
#   mergequeue/queue-precondition-checks-visibility-but-not-ownership
---

# Feature Specification: a wired repo can land

**Created**: 2026-08-18

## The gap, stated precisely

`ergane init --wire` reports success on repositories that cannot land, and
refuses repositories with a remedy that does not work. Both failures share a
shape: the wiring step configures what it knows how to configure and then
declares the repository ready, without ever asking whether the repository can do
the one thing wiring exists to enable.

A first-time operator hit both in a single session. After a clean `--wire` that
printed no refusal, the first enqueue failed:

```
GraphQL: Auto merge is not allowed for this repository (enablePullRequestAutoMerge)
```

That is not a GitHub quirk to be worked around. `factory/mergequeue/gh.py:22`
documents, as a structural guard the tests assert against the module source,
that the *only* merge invocation in the system is `gh pr merge --auto --<method>`.
Ergane's landing path is built on auto-merge. Wiring does not enable it.

The second failure cost money. A user-owned repository was refused by
`_require_public`, whose remedy reads:

> make `{owner_repo}` public, or move to a GitHub plan whose merge queue covers
> private repositories

The operator bought a GitHub Team plan on the strength of that sentence, moved
the repository into an organization, and the ruleset still returned:

```
POST /repos/{owner}/{repo}/rulesets
422 Validation Failed — "Invalid rule 'merge_queue': "
```

— with an empty detail string, so the error named nothing. Team does not cover
merge queue for private repositories; GitHub Enterprise Cloud does. The money is
unrecoverable and the wording is the reason.

## Why the 422 is so hard to read from where the operator stands

Three facts conspire, and a spec that does not name them will produce an
implementer who fixes the wrong one:

1. **The detail string is empty.** GitHub returns `Invalid rule 'merge_queue': `
   with nothing after the colon. There is no machine-readable reason and no
   human-readable one.
2. **A neighbouring payload succeeds.** A `required_status_checks`-only ruleset
   is accepted on the same repository with the same credentials. That makes the
   failure look payload-specific — a malformed `merge_queue` parameters block —
   when the payload is fine and the *repository* is ineligible.
3. **Visibility is a red herring on a user-owned repo.** `_require_public` lets a
   user-owned **public** repository straight through, because it is public. It
   then meets the opaque 422 with the operator believing the precondition
   already cleared.

The repair is to decide eligibility from the two properties GitHub actually uses
— owner type and visibility — before any ruleset is POSTed, so the operator
never meets the 422 at all.

## What this spec does not change

D-007 stands. The merge queue really is unavailable to this project on private
repositories under any plan it holds, and this spec does not add a private-repo
path, a plan-detection probe, or a fallback that lands without a queue. It
changes *which repositories are refused* and *what the refusal tells the operator
to do*, and it makes a repository that passes the precondition actually able to
land.

## User Scenarios & Testing

### User Story 1 - Wiring enables the auto-merge its own driver requires (Priority: P1)

As an operator who has just run `ergane init --wire` without a refusal, I can
enqueue a pull request and have it land, because wiring turned on the repository
setting the merge driver depends on.

**Why this priority**: P1 because without it, `--wire` has a success path that
produces an unlandable repository. Every downstream story in every other spec
assumes landing works.

**Independent Test**: drive `wire_repo` against the existing fake client and
assert the auto-merge PATCH is among the calls it issues; assert the manual-steps
list names the same operation.

**Acceptance Scenarios**:

1. **Given** the diff, **When** `wire_repo` runs against the test double,
   **Then** it issues a step enabling the repository's `allow_auto_merge` flag,
   alongside the existing squash-title, queue and divergence steps — proven by a
   committed test asserting the recorded call list contains the auto-merge
   PATCH addressed at the resolved `owner_repo`.
2. **Given** the diff, **When** `manual_steps` is rendered, **Then** it names
   enabling auto-merge as one of its numbered steps — proven by a committed test
   asserting the rendered list contains it. An operator who is refused and
   follows the printed steps by hand must not land in the same hole the
   automated path just left.
3. **Given** the diff, **When** the auto-merge step's outcome is inspected,
   **Then** it is reported as a named `WiringStep` like its siblings rather than
   a silent side effect — proven by a committed test asserting the step appears
   in the returned step list with its own name and status.
4. **Given** the diff, **When** the auto-merge PATCH fails, **Then** the failure
   surfaces as a wiring failure naming the flag, not as a success — proven by a
   committed test driving the double to refuse that one call and asserting the
   result reports it.

---

### User Story 2 - A repository that cannot host a queue is refused before wiring, with the true reason (Priority: P1)

As an operator wiring a repository GitHub will not accept, I am told which
property disqualifies it and what would actually fix it, before any ruleset is
attempted.

**Why this priority**: P1 and equal to US1. This is the story that has already
cost money, and the cost was caused entirely by wording.

**Independent Test**: drive the precondition over the four cells of the
owner-type × visibility matrix and assert the refusal, or absence of one, for
each; assert the remedy strings by content.

**Acceptance Scenarios**:

1. **Given** a user-owned repository that is public, **When** the merge-queue
   precondition runs, **Then** it refuses before any ruleset call, naming
   organization ownership as the missing property — proven by a committed test
   driving the precondition with a user-owned public repo view and asserting the
   refusal message names it. This cell is the one today's code passes through to
   an opaque 422.
2. **Given** an organization-owned repository that is private, **When** the
   precondition runs, **Then** the refusal names **GitHub Enterprise Cloud** as
   the plan that covers merge queue for private repositories, and states
   explicitly that GitHub Team does not — proven by a committed test asserting
   both the presence of "Enterprise Cloud" and the explicit insufficiency of
   Team in the remedy text.
3. **Given** an organization-owned repository that is public, **When** the
   precondition runs, **Then** it does not refuse — proven by a committed test
   asserting wiring proceeds for that cell.
4. **Given** a user-owned repository that is private, **When** the precondition
   runs, **Then** the refusal names both missing properties rather than only the
   first one checked — proven by a committed test asserting the message names
   ownership and visibility together. An operator told to make it public, who
   then discovers ownership is also disqualifying, has been sent around the loop
   twice for one decision.
5. **Given** the diff, **When** `repo_view` is inspected, **Then** owner type is
   resolved from the same single `gh repo view` call that already returns
   `nameWithOwner` and `visibility`, via the `isInOrganization` field — proven by
   a committed test asserting the requested field list contains it and that no
   additional `gh` invocation was recorded.
6. **Given** the diff, **When** `manual_steps` is rendered for a refused
   repository, **Then** the printed by-hand path is still complete — proven by a
   committed test. FR-006 of the original wiring work holds: a refused operator
   is never left without a route.

---

### User Story 3 - The precondition's matrix is written down where it can be checked (Priority: P2)

As a future maintainer, I can read the eligibility rule as a table rather than
inferring it from branching code, and a change to the code that contradicts the
table fails a test.

**Why this priority**: P2. The behaviour ships in US1 and US2; this story stops
it from silently drifting back. GitHub's availability rules have changed before
and will change again, and the next person to touch this needs to see the claim
being made.

**Independent Test**: assert the documented matrix and the implemented decision
agree, cell by cell, from one shared source.

**Acceptance Scenarios**:

1. **Given** the diff, **When** the eligibility decision is inspected, **Then**
   it is expressed as a single named predicate over (owner type, visibility)
   rather than as two independent guards — proven by a committed test that
   drives the predicate across all four cells and asserts each outcome.
2. **Given** the diff, **When** the module's documentation is read, **Then** it
   quotes GitHub's own availability sentence as the source of the rule, so a
   future reader can re-check the claim against the vendor rather than against
   this repository's memory of it — proven by a committed test asserting the
   quoted sentence is present.
3. **Given** the diff, **When** the four-cell test is inspected, **Then** it
   enumerates all four cells explicitly rather than testing only the refusing
   ones — proven by the committed test's own parametrisation naming each cell. A
   matrix test that omits the passing cell cannot detect a predicate that refuses
   everything.

### Edge Cases

- **`gh repo view` omits `isInOrganization`.** An older `gh` may not return the
  field. Treat absence as unknown and refuse with a message naming the `gh`
  version requirement rather than guessing, since guessing "user" blocks a valid
  org repo and guessing "organization" restores today's opaque 422.
- **The repository is owned by an organization but the ruleset still 422s.** Out
  of scope to diagnose further, but the failure must carry GitHub's response body
  through to the operator rather than swallowing it, so the next report has
  something to work from.
- **`allow_auto_merge` is already enabled.** The PATCH is idempotent; the step
  must report success, not a no-op error.
- **The operator lacks admin on the repository.** The auto-merge PATCH will 403.
  That is a distinct condition from the flag being off and must be reported as
  such.

## Requirements

### Functional Requirements

- **FR-001**: `wire_repo` MUST enable the target repository's `allow_auto_merge`
  setting as a named wiring step.
- **FR-002**: `manual_steps` MUST include the equivalent by-hand command.
- **FR-003**: The auto-merge step's failure MUST be reported as a wiring failure
  naming the setting, never absorbed into a success.
- **FR-004**: The merge-queue precondition MUST decide eligibility from owner
  type and visibility together, before any ruleset call is issued.
- **FR-005**: A user-owned repository MUST be refused regardless of visibility,
  with a message naming organization ownership as the missing property.
- **FR-006**: A private repository's remedy MUST name GitHub Enterprise Cloud and
  MUST state that GitHub Team is insufficient.
- **FR-007**: A repository failing on both properties MUST have both named in one
  refusal.
- **FR-008**: Owner type MUST be resolved from the existing `gh repo view` call
  by adding `isInOrganization` to its field list, without a second `gh`
  invocation.
- **FR-009**: The eligibility rule MUST be a single predicate over the two
  properties, documented with the vendor sentence it derives from.
- **FR-010**: Every refusal MUST continue to carry the complete manual-steps
  list.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-004, FR-005, FR-006, FR-007, FR-008, FR-010]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-009]
```

All three edges are **merge** edges rather than pass edges: no story needs
another to exist, but all three edit `factory/mergequeue/wiring.py`, and US1 and
US2 both edit the step list and the refusal path within a hundred lines of each
other. A dependency edge models what a story needs to exist, which is not the
same question as what it will touch — the edges here are declared for contention,
because concurrent worktrees on one module is a collision this repository has
already paid for more than once, and it presents as tests dying after a clean
rebase rather than as a conflict.

US3 is declared after US2 specifically because it documents the predicate US2
writes. Documenting a predicate that does not exist yet is how a spec produces a
story that cannot be judged.

## Success Criteria

### Measurable Outcomes

- **SC-001**: On a scratch organization-owned public repository, `ergane init
  --wire` followed by an enqueue lands a pull request with no manual GitHub
  settings change — evidenced by terminal output committed in the diff.
- **SC-002**: On a scratch user-owned repository, `ergane init --wire` refuses
  with a message naming organization ownership, and no `rulesets` POST is issued
  — evidenced by committed output.
- **SC-003**: No refusal produced by this module recommends a GitHub plan that
  does not cover the operator's case; the string "Team" appears only where it is
  named as insufficient.
- **SC-004**: The four-cell eligibility matrix is covered by tests that fail if
  any single cell's outcome is inverted.

## Assumptions

- GitHub's availability rule is as its documentation states and as the reporter
  measured; the vendor sentence is quoted in-tree so the claim is re-checkable.
- `isInOrganization` is available from the `gh` versions this project supports.
  The edge case above covers the alternative.
- Enabling `allow_auto_merge` is within the permissions an operator wiring their
  own repository already holds; the 403 case is reported, not worked around.
- This spec does not revisit D-007's underlying decision, only its precondition
  and its wording.
