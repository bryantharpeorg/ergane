# Plan: A one-commit PR must not land under a salvage subject

All line references below were read against the tree at commit `9594787` on
2026-08-11. They are cited so you can find the code, not so you can trust the
numbers — see trap 5, and grep for the named construct when a number is stale.

## The shape of this change

The onboarding pipeline already has a place for exactly this kind of fact. The
activity half (`onboard_target_repo`) gathers repo facts through `GhClient`;
the pure half (`evaluate_repo`) turns facts into findings, one check at a time,
each failing closed with an actionable detail. This story adds one fact (the
repo's `squash_merge_commit_title`) and one finding (`squash_title`). You are
not inventing a pattern — every piece you need has a worked example within
arm's reach, named below.

## Reuse inventory

| What | Where (at `9594787` — grep the construct, not the number) | Used by |
| --- | --- | --- |
| The pure judgment to extend | `factory/mergequeue/onboard.py:45` — `evaluate_repo` | US1 — gains one keyword fact |
| The finding house style | `factory/mergequeue/onboard.py:109-187` — `_visibility_finding` … `_unknown_check_finding` | US1 — copy the pass/fail + remedy-naming shape |
| The fact gatherer | `factory/activities/merge_activities.py:434` — `onboard_target_repo` | US1 — one more read inside the gh-guarded region |
| The gh REST house pattern | `factory/mergequeue/gh.py:205` — `rules_for_branch`, via `_run_json("api", ...)` | US1 — the template for the new `GhClient` method |
| The `repo view` field list | `factory/mergequeue/gh.py:197` — `"nameWithOwner,visibility,defaultBranchRef"` | context only — cannot express this setting (trap 2) |
| The gh-failure routing | `factory/activities/merge_activities.py:565` — `_profile_from_gh_failure` | US1 — reused as-is, never modified |
| The models | `factory/mergequeue/models.py:154` `TargetRepoProfile`, `:175` `Finding` | US1 — read, not changed (see Complexity) |
| The pure table tests | `tests/test_onboard.py` — `evaluate_repo` with keyword facts, no fakes | US1 — the new finding's tests live here |
| The scripted-gh tests | `tests/test_merge_activities.py:493` — `_fake_gh_conforming`; `tests/fake_gh.py:114` — `expect_json` | US1 — the activity-path tests extend this script |
| The landing grammar's parse end | `factory/workgraph/landed.py:39` `_LANDING_RE`, `:47` `_HISTORICAL_LANDING_RE` | **untouchable** — trap 1 |
| The salvage subject's writer | `factory/workgraph/worktree.py:144` — `salvage_message`, prefix at `:149` | **untouchable** — trap 1 |
| The negative table this spec strengthens | `tests/test_landed.py:214` — `test_salvage_subject_is_not_a_landing` (020-US2's T013) | US1 — gains PR #28's verbatim subject |
| The epic-start onboarding gate | `factory/workgraph/workflow.py:815` — `_onboard_target`, invoked at `:651` | context — inherits the check for free, and is why the operator PATCH precedes dispatch |
| The grammar's render end | `factory/mergequeue/messages.py:42` — `pr_title` | context — the value `PR_TITLE` makes authoritative |

## Traps

### Trap 1 — the inverse fix is forbidden, and a test already forbids it

The tempting fix, staring straight at the evidence, is to make the *reader*
recognize salvage subjects — teach `_LANDING_RE` or `_HISTORICAL_LANDING_RE`
the `salvage(<epic>/<node>): ...` shape so PR #28's merge "counts". Do not.
Salvage commits ride **every** node branch's history on every terminal path,
including failure, so any branch merge anywhere would import them into the
default branch and a salvage-aware reader would fabricate landings for stories
that never passed. `tests/test_landed.py:214` (020-US2's own negative test)
exists precisely to refuse them, and this story's scenario 5 adds the verbatim
PR #28 subject — `(#28)` suffix and all — to that table so the refusal is
proved against the real-world string. One subtlety makes a second subject
necessary: the fixture (`repo_builder`, `tests/test_landed.py:101`) hardcodes
`specs/016-delta-derivation` and every test scans `EPIC_ID =
"016-delta-derivation"`, so the verbatim 021 subject is refused by the epic
anchor before the grammar is ever consulted — a salvage-aware reader would
still leave that scan empty, and the guard alone could never go red. The
load-bearing case is therefore the same suffixed shape anchored to the scanned
epic (`salvage(016-delta-derivation/us1): completed attempt 1 (#28)`), which
only a grammar refusal keeps out. Your diff touches neither
`factory/workgraph/landed.py` nor `factory/workgraph/worktree.py` (SC-004).

### Trap 2 — `gh repo view --json` cannot express this setting

The plausible one-line fix is appending `squashMergeCommitTitle` to the
existing field list at `gh.py:197`. It fails at runtime with a gh usage error:
gh's repo-view field set carries `squashMergeAllowed` but **no**
`squashMergeCommitTitle` — verified against the installed gh 2.45.0 at spec
time (`gh repo view --json` with no fields prints the roster). The setting is
reachable via REST: `gh api repos/<owner_repo>` returns
`squash_merge_commit_title` as an uppercase enum string. Add a new `GhClient`
method on the `rules_for_branch` pattern (`_run_json("api", ...)`, raise
`GhError(GH_REFUSED, ...)` on a non-dict shape) rather than bending `repo_view`.

### Trap 3 — absence must fail, not default

GitHub's REST repo payload includes the merge-settings fields only for tokens
with push access; for anyone else the key is simply absent. The plausible wrong
fix is `payload.get("squash_merge_commit_title", "PR_TITLE")` — a silent pass
for exactly the caller who could not see the setting. Follow the
`factory_yaml` finding's precedent (`onboard.py` module docstring: "never a
pass by default"): model the fact as `str | None`, make `None` a failing
`squash_title` finding whose detail says the setting was unreadable and names
the likely cause (token lacks push permission). Making the `evaluate_repo`
parameter default to `None` — rather than required, and rather than defaulting
to a passing value — is what makes fail-closed structural: a call site that
forgets to gather the fact produces a failing finding, not a quiet pass.

### Trap 4 — the setting is repo-scoped, not branch-scoped

The existing queue facts come from the branch-rules API, and the merge-queue
rule's parameters carry `merge_method: "SQUASH"` — so the reflex is to fish for
the title source in the same rules payload (`_queue_from_rules`,
`merge_activities.py:522`). It is not there. `squash_merge_commit_title` lives
on the repo object, which is why the fix command PATCHes `repos/<owner_repo>`
with no branch in sight. Gather it with the new repo-level read; leave
`_queue_from_rules` and the classic-protection fallback exactly alone.

### Trap 5 — line numbers rot before dispatch

Every number in this plan was read at `9594787` on 2026-08-11, and 010's plan
documented findings whose refs went stale-to-inverted within a day. Something
may land between this plan and your worktree. Grep for the construct beside
each anchor: `evaluate_repo`, `onboard_target_repo`, `rules_for_branch`,
`_fake_gh_conforming`, `test_salvage_subject_is_not_a_landing`,
`salvage_message`, `pr_title`. If a citation does not match what you find, the
code wins, and you say so in your commit message.

### Trap 6 — `FakeGh` is strict, and the pure tests break loudly by design

`FakeGh` raises on any gh invocation it was not scripted for
(`tests/fake_gh.py:78`), so the moment `onboard_target_repo` issues the new
settings read, every scripted onboarding test in
`tests/test_merge_activities.py` that reaches the read needs the new
expectation added to its script. Exactly one of the six
`test_validate_target_repo_*` tests routes through `_fake_gh_conforming`; the
other five script their calls individually — check each. Five of the six reach
past the rules read and will break; the exception is
`test_validate_target_repo_a_gh_failure_is_a_failed_validation_not_a_pass`,
which fails on `repo view` and returns through `_profile_from_gh_failure`
before any settings read, so it needs nothing. Symmetrically, the new `evaluate_repo` parameter
will flip the pure happy-path tests in `tests/test_onboard.py` to failing
(fail-closed default) until they pass `squash_merge_commit_title="PR_TITLE"`.
Both breakages are the design working. The wrong fix is loosening either seam
— a permissive `FakeGh` fallback or a passing default — to keep old tests
green; the right fix is updating the tests to state the new fact.

## Approach

### US1 — one fact, one finding, one strengthened negative table

1. **`factory/mergequeue/gh.py`**: add a `GhClient` method (suggested:
   `merge_settings(self, owner_repo: str) -> dict[str, Any]`) under the
   US3-onboarding section, calling `_run_json("api", f"repos/{owner_repo}")`
   and raising `GhError(GH_REFUSED, ...)` on a non-dict payload — the
   `classic_branch_protection` method at `:224` is the closest template.
2. **`factory/activities/merge_activities.py`**: in `onboard_target_repo`,
   after the rules/fallback block and inside the same `try`/`except GhError`
   discipline (a failed read routes to `_profile_from_gh_failure`, reused
   as-is), read `merge_settings(owner_repo)` and extract
   `squash_merge_commit_title` as `str | None` — absent key stays `None`,
   never a default. Pass it to `evaluate_repo`.
3. **`factory/mergequeue/onboard.py`**: `evaluate_repo` gains
   `squash_merge_commit_title: str | None = None`; a new
   `_squash_title_finding` appended right after `_queue_finding` (repo health
   before gate mapping, per the ordering note in `evaluate_repo`'s docstring).
   Pass iff the value is exactly `"PR_TITLE"`; the failing detail names the
   observed value (or "unreadable") and the verbatim remedy
   `gh api -X PATCH repos/<owner_repo> -f squash_merge_commit_title=PR_TITLE`.
   Update the module docstring's check roster, which enumerates every check.
4. **`tests/test_landed.py`**: add two subjects to the salvage-refusal
   negatives: PR #28's exact subject
   `salvage(021-roadmap-operability/us4): completed attempt 1 (#28)`, and the
   same suffixed shape anchored to the epic the fixture actually scans —
   `salvage(016-delta-derivation/us1): completed attempt 1 (#28)` (`us1` maps
   to a declared story). The anchored twin is the load-bearing guard: the 021
   subject is refused by the epic anchor alone (trap 1). Note the suffix: the
   existing table's salvage subjects carry no ` (#NN)`, and the real merged
   subject does — that suffix is what GitHub appends, and the refusal must
   hold with it present.

Testing needs no live gh anywhere: the pure tests hand `evaluate_repo` its
facts directly, and the activity tests script the exact argv through `FakeGh`
(`expect_json("api", "repos/OWNER/REPO", payload={...})` — a distinct argv from
the rules call, so prefix matching cannot collide).

## Complexity Tracking

| Thing | Why it is not simpler |
| --- | --- |
| A new `GhClient` method instead of extending `repo_view` | `gh repo view --json` has no field for this setting (trap 2); one REST read is the minimal correct gather. |
| `str \| None` with a `None` default on `evaluate_repo` | A required parameter would also work, but the `None` default makes fail-closed structural for future call sites, and absence-is-failure is the spec's FR-003. |
| No new `TargetRepoProfile` field | The finding's detail already carries the observed value to both renderers (`_render_onboard` and `--json` via the findings tuple); a new fact field would widen a frozen dataclass that rides Temporal payloads for no reader that needs it. |
| Why an onboarding check at all, when the PATCH already fixes the repo | The PATCH fixes one repo once; nothing else stops a settings regression or a future target arriving with GitHub's default (`COMMIT_OR_PR_TITLE`), and the epic-start gate makes the check self-enforcing at every dispatch. |

## Verification

`uv run pytest -q` green in the worktree — that is the implementer's whole
evidence (the worker imports factory code from its own checkout; nothing you
change is live until an operator restarts it). The tests that did not exist
before are the point: the `squash_title` finding in all three postures
(conforming, non-conforming, unreadable), the activity path both ways through
a scripted `FakeGh`, and PR #28's verbatim subject — plus its epic-anchored
twin, the half that can actually go red — refused by `landed_facts`.
The live half — PATCHing the real repo and reading `PR_TITLE` back — is
operator work in tasks.md Phase 1, not node work, and SC-002's "next
one-commit squash merge carries the PR title" is confirmed by the operator on
the first landing after both halves are in place.
