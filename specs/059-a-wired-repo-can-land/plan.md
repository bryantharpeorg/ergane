# Implementation Plan: a wired repo can land

**Spec**: `specs/059-a-wired-repo-can-land/spec.md`

## What already exists, and where

- `factory/mergequeue/wiring.py:225` — `wire_repo`, the whole entry point. It
  calls `_require_gh`, then `client.repo_view()`, then `_require_public`, then
  runs a list of steps at `:250`.
- `factory/mergequeue/wiring.py:250` — the step list:
  `_squash_title_step`, `_queue_step`, `_divergence_step`. US1 adds a fourth.
- `factory/mergequeue/wiring.py:331` — `_squash_title_step`, the closest
  structural model for the new step. It is a PATCH against
  `repos/{owner_repo}` returning a `WiringStep`. Copy its shape.
- `factory/mergequeue/wiring.py:307` — `_require_public`, which US2 replaces
  with a two-property predicate.
- `factory/mergequeue/wiring.py:78` — `manual_steps`, the numbered by-hand list.
  It already emits `gh api -X PATCH repos/{owner_repo} -f
  squash_merge_commit_title=...` as step 1; the auto-merge PATCH belongs
  immediately beside it.
- `factory/mergequeue/gh.py:236` — `repo_view`, which requests
  `nameWithOwner,visibility,defaultBranchRef` in one `_run_json` call. US2 adds
  `isInOrganization` to that string. Its docstring already explains that one
  call serves several consumers; extend the docstring rather than adding a call.
- `factory/mergequeue/gh.py:22` — the module docstring's structural guards. Read
  it before touching anything: the tests assert against the module *source* that
  the only merge invocation is `gh pr merge --auto`, and that no path requests
  branch deletion. A new step must not widen either surface.
- The existing wiring test double. Find it and drive everything through it —
  every acceptance criterion in this spec is written to be satisfiable against a
  fake client, and none of them need a live GitHub.

## Traps

These are named hazards, not advice. Each has already cost this factory or this
project time or money.

**1. This spec exists because a check asserted a declaration instead of a
capability. Do not repeat the shape.** `--wire` set the settings it knew about
and reported success; nothing asked whether the repository could land. A test
asserting "the auto-merge step is in the list" is the same class of check that
produced the bug. Write the test so it would fail if the step were present but
addressed at the wrong repository, or issued with the flag set false. Assert the
call's *content*, not its existence.

**2. The empty 422 detail string is the whole reason US2 is hard.** GitHub
returns `Invalid rule 'merge_queue': ` with nothing after the colon. You will not
be able to write a test that parses a reason out of a live error, and you must
not try. The eligibility decision is made *before* the POST, from `repo_view`
fields, and that is the only mechanism this spec accepts.

**3. A neighbouring payload succeeds, which will send you after the wrong
bug.** A `required_status_checks`-only ruleset is accepted on a repository whose
`merge_queue` rule is rejected. If you start from the payload you will spend the
attempt tuning a parameters block that is already correct. The disqualifying
property is the repository's, not the request's.

**4. `Team` is a word that must appear exactly once, as a negation.** The
remedy that cost money read as a recommendation to buy Team. SC-003 makes this
checkable. If your remedy string mentions Team in any construction that a hurried
reader could parse as "buy this", you have rebuilt the defect. The safe wording
names Enterprise Cloud as the thing that works and Team as the thing that does
not.

**5. Do not add a second `gh` call for owner type.** `repo_view` is one
`_run_json` and several consumers depend on its shape. `isInOrganization` is a
documented `gh repo view --json` field — verified available on this host — so it
costs one more entry in an existing comma-separated string and zero extra round
trips. US2-S5 asserts no additional invocation was recorded, so a second call
fails the story.

**6. Refuse before you POST, and prove the ordering.** The value of US2 is that
the operator never meets the 422. A precondition that runs after the ruleset call
is worthless even if its message is perfect. Assert call ordering in the test,
not just the refusal.

**7. The judge sees the diff and the criteria. Nothing else.** No base tree, no
commit message, no terminal. SC-001 and SC-002 are runtime evidence, so they must
be **committed as pasted output inside the diff**. 053/US1 shipped without its
transcript and had to add it on a second attempt; write it the first time.

**8. Both stories edit `factory/mergequeue/wiring.py`.** The declared edge
serialises them. Do not do US2's work inside US1 to save a round — the graph is
what the next reader will believe. US3 also touches the same file and is declared
after both.

**9. Idempotence is not optional for the auto-merge PATCH.** Operators re-run
`--wire`. A step that errors because the flag is already true converts a
successful re-run into a failure, and re-running wiring is the documented
recovery path for half the findings in this ledger.

**10. `manual_steps` renders for repositories the code could not read.** Its
signature defaults `owner_repo` to `<owner>/<repo>` precisely because a refusal
can precede reading the slug. Your new numbered step must render correctly with
the placeholder, not just with a resolved slug.

## Sizing

Three small stories against one module. US1 is one step function modelled on
`_squash_title_step`, one line in the step list, one line in `manual_steps`, and
their tests. US2 is a predicate replacing a guard, one field added to a JSON
field list, and a four-cell parametrised test. US3 is documentation plus the
matrix test that holds it true. None should need a second attempt if traps 1, 4
and 5 are respected.

The whole spec is smaller than 054 and should be dispatched first among the six
on-ramp specs, because every other spec's end-to-end verification assumes a
repository that can land.

## Verification the operator will run, independent of the gate

A green suite is evidence, not proof — this repository has shipped a command
that could not start on a fully green run.

- **Prove US1 by control.** On a scratch org-owned public repository, disable
  `allow_auto_merge` by hand, run `ergane init --wire`, and confirm the flag is
  on afterwards via `gh api repos/{owner}/{repo} --jq .allow_auto_merge`. Then
  enqueue something and watch it land. That is SC-001 and it is the only check
  that catches wiring which is *complete but still unlandable*.
- **Prove US2 by mutation, across the matrix.** Run `--wire` against a user-owned
  public repo and confirm the refusal names ownership and that no ruleset POST
  appears in `gh` traffic. Then run it against an org-owned public repo and
  confirm it proceeds. Two cells, opposite outcomes, same command.
- **Read the remedy text out loud.** SC-003 is a wording criterion and wording is
  what caused the loss. Before landing, read every refusal string this module can
  emit and ask whether a tired operator at midnight would spend money on the
  strength of it.
