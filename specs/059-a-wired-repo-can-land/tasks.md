# Tasks: a wired repo can land

**Spec**: `specs/059-a-wired-repo-can-land/spec.md`
**Plan**: `specs/059-a-wired-repo-can-land/plan.md`

Read the plan's **Traps** before the first task. Trap 1 is the one that decides
whether this spec fixes the bug or reproduces its shape one level up. Trap 4 is
the one that already cost money.

Tests are written before the implementation and must fail for the stated reason
before anything is made to pass. A test that passes on first write has not
established what it claims.

All three stories edit `factory/mergequeue/wiring.py`. The declared edges
serialise them: US1 → US2 → US3.

## Phase 1: User Story 1 — Wiring enables the auto-merge its own driver requires

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1) In the wiring test module: drive `wire_repo` against the
      existing fake client and assert the recorded call list contains a PATCH to
      `repos/{owner_repo}` setting `allow_auto_merge` true. Assert the call's
      **content** — target slug and flag value — not merely that a call of that
      name occurred (trap 1).
- [ ] T002 [P] [US1] (spec US1-S2) Assert `manual_steps` renders a numbered step enabling
      auto-merge, and that it renders correctly with the default
      `owner_repo="<owner>/<repo>"` placeholder as well as with a resolved slug
      (trap 10).
- [ ] T003 [P] [US1] (spec US1-S3) Assert the auto-merge operation appears in the returned
      `WiringStep` list with its own name and status, like its three siblings.
- [ ] T004 [P] [US1] (spec US1-S4) Drive the fake client to refuse the auto-merge PATCH and
      assert `wire_repo` reports a failure naming the setting — not a success
      with a missing step.
- [ ] T005 [P] [US1] (spec Edge Cases) Assert the step succeeds when the flag is already
      enabled: re-running wiring must not convert an idempotent PATCH into a
      failure (trap 9). Assert a 403 is reported as a permissions condition
      distinct from the flag being off.

### Implementation for this story

- [ ] T006 [US1] (FR-001, FR-003) Add `_auto_merge_step(client, owner_repo)` to
      `factory/mergequeue/wiring.py`, modelled on `_squash_title_step` (:331).
      It issues the `allow_auto_merge` PATCH against `repos/{owner_repo}` and
      returns a named `WiringStep`. Do not widen the module's command surface —
      re-read `factory/mergequeue/gh.py:22`'s structural guards first.
- [ ] T007 [US1] (FR-001) Add it to the step list at `factory/mergequeue/wiring.py:250`,
      beside `_squash_title_step`.
- [ ] T008 [US1] (FR-002) Add the by-hand equivalent to `manual_steps` (:78) beside the
      existing squash-title PATCH at :88, renumbering the list.
- [ ] T009 [US1] Document in the step's docstring *why* it exists: the merge driver's
      only merge invocation is `gh pr merge --auto`, so the repository flag is a
      precondition of the landing path rather than a convenience.

## Phase 2: User Story 2 — A repository that cannot host a queue is refused before wiring, with the true reason

### Tests for this story (write FIRST, must fail)

- [ ] T010 [P] [US2] (spec US2-S1, US2-S2, US2-S3, US2-S4) One parametrised test over all four cells of the
      owner-type × visibility matrix, asserting for each whether a refusal is
      raised and, where it is, which properties the message names. Enumerate the
      passing cell explicitly — a matrix test that omits it cannot catch a
      predicate that refuses everything.
- [ ] T011 [P] [US2] (spec US2-S2) Assert the private-repo remedy contains "Enterprise Cloud"
      and states that Team is insufficient. Assert the word "Team" appears in no
      other construction (trap 4, SC-003).
- [ ] T012 [P] [US2] (spec US2-S5) Assert `repo_view`'s requested field list contains
      `isInOrganization`, and that driving `wire_repo` records no additional
      `gh` invocation beyond today's (trap 5).
- [ ] T013 [P] [US2] (spec US2-S1, trap 6) Assert ordering: for a refused repository, no
      `rulesets` POST appears in the recorded call list at all. The refusal must
      precede the request, not follow it.
- [ ] T014 [P] [US2] (spec US2-S6) Assert a refusal still carries the complete `manual_steps`
      list.
- [ ] T015 [P] [US2] (spec Edge Cases) Assert that a `repo_view` payload lacking
      `isInOrganization` refuses with a message naming the `gh` version
      requirement, rather than defaulting to either answer.

### Implementation for this story

- [ ] T016 [US2] (FR-008) Add `isInOrganization` to the `--json` field string in
      `factory/mergequeue/gh.py:245`, and extend `repo_view`'s docstring to say
      why the field is there.
- [ ] T017 [US2] (FR-004, FR-005, FR-006, FR-007, FR-009) Replace `_require_public`
      (`factory/mergequeue/wiring.py:307`) with a single predicate over (owner
      type, visibility). Refuse user-owned regardless of visibility; name both
      properties when both disqualify; name GitHub Enterprise Cloud, and Team's
      insufficiency, in the private-repo remedy.
- [ ] T018 [US2] (FR-004) Update the call site at `factory/mergequeue/wiring.py:243` to
      pass owner type alongside visibility.
- [ ] T019 [US2] (FR-010) Confirm every refusal branch still passes `manual_steps`
      through.

## Phase 3: User Story 3 — The precondition's matrix is written down where it can be checked

### Tests for this story (write FIRST, must fail)

- [ ] T020 [P] [US3] (spec US3-S2) Assert the module documentation contains GitHub's
      availability sentence verbatim, so the claim is re-checkable against the
      vendor rather than against this repository's memory of it.
- [ ] T021 [P] [US3] (spec US3-S1) Assert the eligibility decision is reachable as one named
      predicate and drive it directly across all four cells.

### Implementation for this story

- [ ] T022 [US3] (FR-009) Document the eligibility rule as a four-cell table in the
      module docstring, quoting: "Pull request merge queues are available in any
      public repository owned by an organization, or in private repositories
      owned by organizations using GitHub Enterprise Cloud." Cite it as GitHub's
      documented availability statement.
- [ ] T023 [US3] Add a `docs/decisions.md` entry recording that D-007's precondition
      now covers ownership as well as visibility, and that the earlier remedy
      wording was withdrawn because it named a plan that does not cover the case.
      Supersede, never edit in place.

## Verification

- [ ] T024 (SC-001) On a scratch organization-owned public repository: disable
      `allow_auto_merge` by hand, run `ergane init --wire`, confirm the flag is
      on via `gh api repos/{owner}/{repo} --jq .allow_auto_merge`, then enqueue a
      pull request and watch it land. **Paste the terminal output into the diff**
      — the judge sees nothing else (trap 7).
- [ ] T025 (SC-002) On a scratch user-owned repository: run `ergane init --wire`,
      confirm the refusal names organization ownership, and confirm no `rulesets`
      POST was issued. Paste the output into the diff.
- [ ] T026 (SC-003) Read every refusal string this module can emit and confirm none
      recommends a plan that does not cover the operator's case.
- [ ] T027 (SC-004) Invert each cell of the matrix in turn and confirm the test
      fails for that cell. A matrix test nobody has seen fail is a matrix test
      nobody has tested.
