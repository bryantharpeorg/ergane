---
state: ready
# Flipped ready 2026-08-11 PM CT on the operator's word ("flip all 6"); the
# paused roadmap dispatches serially (max_concurrent_epics=1) in dir order
# once unpaused.
# specs_root: specs
# target_repo: /home/admin/code/ergane
# Scaffolded by `ergane findings promote` from
# `targets/salvage-only-pr-lands-invisible` (critical, observed 2026-08-09 on
# 021-roadmap-operability/us4, PR #28), then refined against the tree at
# 9594787 on 2026-08-11.
---

# Feature Specification: A one-commit PR must not land under a salvage subject

## The mechanism

The landing-attribution contract has two ends. The render end is
`pr_title` (`factory/mergequeue/messages.py:42`), which titles every landing PR
`<epic_id>/<node_id>: <story title>`. The parse end is `_LANDING_RE`
(`factory/workgraph/landed.py:39`), which `landed_facts` runs over the default
branch's merge subjects to decide which stories are landed. The contract holds
only if the merge subject *is* the PR title — and GitHub makes that a repo
setting, not a law. With `squash_merge_commit_title=COMMIT_OR_PR_TITLE`
(GitHub's default, and what PR #28's behavior proves this repo was set to on
2026-08-09), a squash merge of a **one-commit PR** takes its subject from that
single commit's message instead of from the PR title. Verified 2026-08-11: the
live repo now reads `PR_TITLE` — the setting was already corrected sometime
after the incident, so Phase 1's PATCH is expected to be a confirming
read-back, and the onboarding check is the half that keeps it true.

The factory manufactures exactly that case. When an attempt commits nothing
itself, salvage (constitution VI) commits the whole tree in one commit whose
subject is `salvage(<epic>/<node>): completed attempt N` — so the PR holds
exactly one commit, the salvage commit, and the merge lands under the salvage
subject. `landed_facts` must refuse that subject: salvage commits ride every
node branch's history, and 020-US2's own negative test
(`tests/test_landed.py:214`) exists to keep them refused. The story is fully in
the tree and invisible to the reader, and a delta derivation would re-dispatch
work that already landed — the exact failure 016 and 020 were built to prevent.

This is proved, not hypothesized: PR #28 (021-roadmap-operability/us4) held one
commit and landed as `salvage(021-roadmap-operability/us4): completed attempt 1
(#28)`; PRs #26 (5 commits), #27 (2) and #29 (3) all used the PR title and read
correctly. The work is fully present at `e4e90c3`, and `ergane build landed`
cannot and must not report US4 from it.

## The fix, in two deterministic halves

1. **One operator call, repo-wide**: `gh api -X PATCH
   repos/bryantharpeorg/ergane -f squash_merge_commit_title=PR_TITLE` makes the
   merge subject depend on the thing the factory controls — the PR title it
   writes — rather than on how many commits an agent happened to make. That is
   Phase 1 of tasks.md, dispatched to no node — and as of 2026-08-11 the live
   repo already reads `PR_TITLE`, so Phase 1 verifies first and PATCHes only
   on a regression.
2. **One onboarding check, forever**: `ergane repo onboard` (and the epic-start
   onboarding gate that shares its logic) gains a finding asserting the target
   repo's `squash_merge_commit_title` is `PR_TITLE`, so no target repo — this
   one after a settings regression, or any future one arriving with GitHub's
   default — can silently reopen the hole.

The landing reader does not change. Making salvage subjects parse as landings
is the forbidden inverse fix (see Out of Scope).

## User Scenarios & Testing

### User Story 1 - Onboarding refuses a repo that titles squash merges from commits (Priority: P1)

`ergane repo onboard` gathers the target repo's `squash_merge_commit_title`
setting through the same `gh` boundary as its other repo facts, and
`evaluate_repo` turns it into a finding: pass exactly when the value is
`PR_TITLE`, fail otherwise — including when the setting cannot be read at all.
The finding's detail is actionable in the house style: it names the observed
value and the one `gh api -X PATCH` call that fixes it. Because
`onboard_target_repo` is shared by the offline CLI and the `validate_target_repo`
activity, the epic-start onboarding gate (`factory/workgraph/workflow.py:815`)
inherits the check with no extra wiring: a non-conforming repo is refused for
dispatch before any key is issued or worktree created.

The story also proves the boundary it must not cross: `landed_facts` continues
to refuse salvage subjects, now demonstrated against PR #28's verbatim
real-world subject.

**Goal**: a target repo whose squash merges would not carry the landing grammar
is a failing onboarding finding with the remedy in hand, and the landing
reader's refusal of salvage subjects is untouched and re-proved.

**Independent Test**: table-test `evaluate_repo` with the setting conforming,
non-conforming, and unreadable; drive `onboard_target_repo` through a scripted
`FakeGh` both ways; and run the landed-facts negative test against PR #28's
exact subject and its epic-anchored twin.

**Acceptance Scenarios**:

1. **Given** an otherwise conforming target repo whose
   `squash_merge_commit_title` is `PR_TITLE`, **When** it is onboarded, **Then**
   the profile carries a passing `squash_title` finding and the profile as a
   whole still passes.
2. **Given** a target repo whose `squash_merge_commit_title` is
   `COMMIT_OR_PR_TITLE`, **When** it is onboarded, **Then** the profile fails,
   and the `squash_title` finding's detail names the observed value and the
   exact remedy call (`gh api -X PATCH repos/<owner_repo> -f
   squash_merge_commit_title=PR_TITLE`).
3. **Given** a merge-settings payload that omits `squash_merge_commit_title`
   entirely, **When** it is onboarded, **Then** the `squash_title` finding fails
   closed — an unreadable setting is never a pass — with a detail naming the
   likely cause (the token lacks push permission on the repo, which is what
   hides GitHub's merge-settings fields).
4. **Given** a `gh` failure on the merge-settings read itself, **When** it is
   onboarded, **Then** the result is a failed profile, exactly as the existing
   rules-read failure path behaves — never a pass.
5. **Given** a default-branch history containing PR #28's verbatim subject
   `salvage(021-roadmap-operability/us4): completed attempt 1 (#28)` **and**
   the same suffixed shape anchored to the scanned epic itself
   (`salvage(<scanned-epic>/us1): completed attempt 1 (#28)`, where `us1` maps
   to a declared story), **When** `landed_facts` scans it, **Then** no landing
   is reported for any story — the refusal 020-US2 requires still holds,
   suffix and all, and it holds by grammar, not merely because the epic anchor
   differs.

## Functional Requirements

- **FR-001**: Onboarding MUST gather the target repo's
  `squash_merge_commit_title` through the `GhClient` boundary, via the REST
  repo endpoint (`gh api repos/<owner_repo>`) — `gh repo view --json` cannot
  express this setting (its field set carries `squashMergeAllowed` but no
  `squashMergeCommitTitle`; verified against the installed gh 2.45.0).
- **FR-002**: `evaluate_repo` MUST emit a `squash_title` finding that passes
  exactly when the gathered value is the string `PR_TITLE`, and fails for any
  other value with a detail naming what was observed and the one-call remedy.
- **FR-003**: An absent or unreadable setting MUST fail the `squash_title`
  finding — never a pass by default, matching the `factory_yaml` finding's
  fail-closed precedent.
- **FR-004**: `TargetRepoProfile.passed` MUST remain the conjunction of its
  findings, so a repo failing `squash_title` is refused for dispatch by the
  existing epic-start onboarding gate with no new wiring.
- **FR-005**: The landing reader MUST NOT change: `_LANDING_RE`,
  `_HISTORICAL_LANDING_RE` and `salvage_message` keep their exact behavior, and
  the salvage-refusal negative table gains PR #28's verbatim subject as a
  standing guard.

## Success Criteria

- **SC-001**: Onboarding a repo whose setting is `COMMIT_OR_PR_TITLE` fails
  with a finding an operator can act on without re-deriving the problem;
  onboarding the same repo with `PR_TITLE` passes.
- **SC-002**: After Phase 1 (the read-back, and the PATCH only if the setting
  regressed), `gh api repos/bryantharpeorg/ergane --jq .squash_merge_commit_title`
  prints `PR_TITLE`, and the next one-commit squash merge on the landing branch
  carries the PR title as its subject.
- **SC-003**: The full suite is green, no dependency is added, and
  `tests/test_landed.py`'s pre-existing negative tests pass unmodified.
- **SC-004**: `factory/workgraph/landed.py` and
  `factory/workgraph/worktree.py` show no behavioral diff from this story.

## Edge Cases

- **Multi-commit PRs masked the defect.** Under `COMMIT_OR_PR_TITLE` a PR with
  two or more commits still merges under the PR title, which is why #26, #27
  and #29 read correctly and the bug waited for the first attempt that
  committed nothing. The check therefore asserts the *setting*, not any
  property of a particular PR — there is nothing to detect at landing time.
- **The epic-start gate makes this self-enforcing, and self-blocking.** Once
  this lands, every epic dispatch onboards the target first
  (`workflow.py:651`), so a still-unpatched repo refuses all dispatch with the
  finding naming the fix. Intended fail-closed behavior; it is why the Phase 1
  PATCH is sequenced before this epic dispatches.
- **Merge-settings visibility follows permission.** GitHub's REST repo payload
  carries `squash_merge_commit_title` only for tokens with push access. The
  factory's `gh` is the operator's and has it; a token that does not surfaces
  as scenario 3's fail-closed finding, not as a crash.
- **Value comparison is exact.** REST speaks uppercase enum strings
  (`PR_TITLE`, `COMMIT_OR_PR_TITLE`); the check compares the exact string and
  treats anything else — including casing surprises — as non-conforming.

## Assumptions

- GitHub's merge queue honors the repo-level `squash_merge_commit_title` when
  it squash-merges. Evidence: PR #28 (one commit) landed under its commit
  subject while #26/#27/#29 landed under their PR titles, all through the same
  queue with the same ruleset (`merge_method: SQUASH`).
- The one-time PATCH targets `bryantharpeorg/ergane` because every current
  target clone's origin is that repo; the onboarding check, not the PATCH, is
  what covers any future target.
- 021/us4's own visibility needs no repair here: 021's frontmatter is
  `state: landed`, so the per-story attestation fallback in `landed_facts`
  already gap-fills US4 with `kind=ATTESTED`.
- No new dependency, no new activity, no new store, no schema change.

## Out of Scope

- **Making salvage subjects parse as landings — forbidden.** Salvage commits
  appear in every node branch's history on every terminal path, so a reader
  that recognized them would fabricate landings wherever a branch is merged.
  020-US2's negative test (`tests/test_landed.py:214`) requires the refusal;
  this spec strengthens that table and changes nothing about the reader.
- **Re-attributing PR #28 or rewriting history.** The merged salvage subject is
  the evidence this happened; 021/us4 is covered by attestation.
- **Changing `salvage_message`, `pr_title`, or the PR body renderer.** The
  grammar's render end is correct; the defect was GitHub choosing not to use it.
- **Branch-ruleset merge-method enforcement.** The queue's `SQUASH` method is
  already asserted by the existing onboarding checks' domain; the title source
  is a different, repo-scoped setting and is all this spec adds.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005]
```
