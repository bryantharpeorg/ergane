# Implementation Plan: the live smoke runs, or the suite says why

Drafted 2026-08-27 against ergane-buildout at ba9be75. Every anchor below was
read from that commit. The offline transcript in § *The remedy, measured* was
produced on that commit and is the evidence this plan rests on — it is an input,
not a hypothesis for the implementer to re-litigate.

## Requirements, numbered here

- **FR-001** — The live-epic smoke's scratch manifest declares a runtime that
  `load_factory_config` accepts. The value is **derived from
  `SUPPORTED_BACKENDS` (`factory/verify/factory_yaml.py:90`)**, not written as
  the literal `bwrap`. A literal is what the fixture had; the point of this
  requirement is that the next change to that tuple breaks at the fixture rather
  than twelve days later at dispatch.
- **FR-002** — The smoke dispatches with `halt_after_pass=True`
  (`EpicInput.halt_after_pass`, `factory/workgraph/workflow.py:568`), set at its
  own `EpicInput` construction (`tests/test_live_epic.py:606`). This is not a
  workaround for the missing remote: it is the accurate description of an epic
  that has no forge, opens no proposal, and asserts only on PASSED-level facts.
- **FR-003** — Nothing the smoke asserts changes. The three assertions that could
  plausibly have been disturbed by FR-002 — the salvage commit is on the branch,
  the branch outlives the worktree, the worktree is swept — are pinned by tests
  that already exist, and they must still pass unmodified. See § *Why halting
  mode is safe here* for the read of the workflow that says they will.
- **FR-004** — A new offline check builds each live module's scratch target
  repository and runs the **real** onboarding over it —
  `onboard_target_repo(_forge(repo_path=...), ...)`
  (`factory/activities/merge_activities.py:612`, `:758`) — with no proxy, no
  agent, no Temporal server and no network.
- **FR-005** — That check filters the resulting findings through the **real**
  `_is_landing_only_check` (`factory/workgraph/workflow.py:374-378`) when, and
  only when, the module it is checking dispatches with `halt_after_pass=True`.
  Importing the predicate rather than restating the check names is the whole
  point: a second copy of `_LANDING_ONLY_CHECKS` in a test is two lists that
  drift while both stay green.
- **FR-006** — The check's failure message names the surviving findings, each
  with its check name and detail. `assert profile.passed` would have told the
  reader that something was wrong and nothing about which of two independent
  blockers to fix.
- **FR-007** — A guard fails when a `tests/test_live_*.py` module **hand-authors**
  a repository manifest — writes one from a literal in its own source — and is
  not in the covered set. Coverage enumerated by hand is how a fourth live module
  arrives uncovered under a green suite; this repository has shipped that exact
  shape three times in `page_holds_true.py`.

  The rule is deliberately about hand-authored manifests, and the boundary is
  load-bearing rather than cosmetic. As of ba9be75 exactly one live module
  hand-authors one: `manifest_source` in `tests/test_live_epic.py:298-312`.
  `tests/test_live_onramp.py` also ends up with a manifest, but it is *generated*
  by `ergane init` and then loaded by the real loader
  (`tests/test_live_onramp.py:687-694`) — writer and reader are the same code, so
  it cannot drift the way a literal can, and it cannot be built offline either
  because `init --wire` needs a real forge. A guard that demanded coverage of it
  would demand something impossible and be relaxed within the hour.
- **FR-008** — At the end of every run, the suite emits one report naming each
  live marker registered in `pyproject.toml:81-88`, whether tests carrying it
  ran, and the condition that would have run it. The marker's own registration
  string is the source of both its name and its condition.
- **FR-009** — The report is emitted on every run, green or red, and changes no
  exit status. A describer that can fail a build has acquired a second job.

## What already exists, and where

| Piece | Where | State |
| --- | --- | --- |
| The scratch manifest | `manifest_source`, `tests/test_live_epic.py:298-312` | Emits `runtime: python:3.11-bookworm`; unchanged since `e915296` (2026-08-06) |
| The refusal that rejects it | `_read_runtime`, `factory/verify/factory_yaml.py:294-300` | Landed in `8b768e6`, *011-agent-sandbox/us2* (2026-08-15) |
| The one supported backend | `SUPPORTED_BACKENDS`, `factory/verify/factory_yaml.py:90` | `("bwrap",)` — a tuple, so FR-001 has something to derive from |
| The scratch repo builder | `build_scratch_repo`, `tests/test_live_epic.py:506-530` | `git init -b main`, one commit, **no remote** |
| The onboarding gate | `factory/workgraph/workflow.py:1098-1143` | Landed `cc3a5e2` (2026-08-06); raises `GRAPH_INVALID` before any key is issued |
| The landing-only predicate | `_is_landing_only_check`, `factory/workgraph/workflow.py:374-378` | Built by 109-US3 for the demo's remote-less repo — the same situation |
| The smoke's dispatch | `start`, `tests/test_live_epic.py:599-618` | Constructs `EpicInput` at `:606` without `halt_after_pass` |
| The halt branch | `factory/workgraph/workflow.py:2179-2193` | Salvages via `_close_out`, then removes the worktree, then leaves the record at PASSED |
| The tier's on/off switch | `live_config`, `tests/test_live_epic.py:367-375` | Skips unless `LITELLM_PROXY_URL` and `LITELLM_MASTER_KEY` are set |
| The marker registrations | `pyproject.toml:81-88` | Six live markers, each with its auto-skip condition written into the string |
| The other manifest-writing live module | `tests/test_live_onramp.py:687-694` | Generates its manifest via `ergane init` and loads it with the real loader, so it cannot drift the same way — it is the shape FR-004 generalises |

## The remedy, measured

Run on 2026-08-27 against ba9be75, importing the smoke's own `build_scratch_repo`
and calling the real `onboard_target_repo`. It took about two seconds and
required no proxy, no agent and no Temporal server. **Before:**

```
passed: False
  [FAIL] repo_read: could not read the repo via its forge (GH_REFUSED): no git remotes found
  [FAIL] factory_yaml: manifest failed to load: /tmp/.../factory.yaml:
         [runtime] declares `runtime: 'python:3.11-bookworm'`; the supported backend is `bwrap`
```

**After rewriting only the runtime to `bwrap`, then filtering through the real
`_is_landing_only_check`:**

```
with runtime: bwrap  -> passed: False
  [FAIL] repo_read: could not read the repo via its forge (GH_REFUSED): no git remotes found
after --halt-after-pass filter -> remaining failures: 0
PASSES ONBOARDING UNDER HALT: True
```

Two things follow, and the implementer should not need to rediscover either.
Both blockers are real and independent — fixing the manifest alone leaves
`repo_read` fatal. And US2's check is not a new idea that needs designing: it is
the transcript above, committed.

## Why halting mode is safe here

FR-002 is the requirement most likely to be argued with, so the read is written
out. Under `halt_after_pass`, `factory/workgraph/workflow.py:2179-2193` runs
`_close_out` — which salvages the attempt's work onto the node branch — and only
then removes the worktree, leaving the record at PASSED. The landing phase never
begins.

Every assertion the smoke makes is at or below PASSED:
`test_the_node_passed_and_the_epic_completed`,
`test_the_node_passed_on_its_first_attempt`,
`test_the_branch_holds_the_salvage_commit_for_the_attempt`,
`test_the_branch_carries_the_agent_s_work`,
`test_the_worktree_was_swept_and_the_branch_outlived_it`, the two store rows, the
gate identity, the two archives, the status query, and the master-key sweep.
`test_the_worktree_was_swept_and_the_branch_outlived_it` is the one that reads
most like a landing-phase fact, and it is precisely what the halt branch does.

What halting mode gives up is landing, and this smoke never had it: the scratch
repo has no remote, so there is no queue to enter. Landing is proven by
`tests/test_live_merge.py`, against a real sample repo, and this spec does not
touch it.

## Technical approach, story by story

### US1 — the smoke's repository onboards

Two edits in `tests/test_live_epic.py`. `manifest_source` interpolates
`SUPPORTED_BACKENDS[0]` (imported) instead of the literal string, and `start`
passes `halt_after_pass=True` into `EpicInput`. Both are pinned by tests that do
not need a live run: the manifest test builds the repo and loads it, and the
dispatch test asserts on the constructed `EpicInput` rather than on a run.

### US2 — the cheap tier notices

A new `tests/test_live_fixtures_onboard.py`. For each covered live module it
builds the scratch repo through that module's own builder, calls the real
`onboard_target_repo`, filters through the real `_is_landing_only_check` if that
module dispatches halting, and asserts nothing failed — reporting survivors by
name. The coverage guard reads the `tests/test_live_*.py` sources for manifest
writes and fails on any module that writes one and is not covered.

The module must import cleanly with no live environment. It touches the live
modules only to call their builders, and those imports are already side-effect
free — the skips live in fixtures, not at import time.

### US3 — a tier that did not run says so

A `pytest_terminal_summary` hook in `tests/conftest.py`. The marker names and
their conditions come from the registered `markers` list, parsed at the
`<name>: <description>` boundary, so there is exactly one place either is
written. Whether a marker ran is read from the session's own report objects. The
hook writes to the terminal reporter and returns; it sets no exit status.

## Traps

**T1 — do not make the smoke pass by weakening onboarding.** The tempting small
change is to make `repo_read` non-fatal, or to make onboarding advisory, or to
add a "test mode" that skips validation. All three would make a real epic
dispatchable against a repository the factory cannot read, which is the exact
thing the gate was built in `cc3a5e2` to prevent. The correct lever already
exists and was built for this situation by 109-US3: an epic that will not land is
not judged by landing checks. Use it.

**T2 — do not hardcode `bwrap`.** FR-001 asks for the value to come from
`SUPPORTED_BACKENDS`. Writing the literal makes the test green today and
reproduces the original defect exactly: a fixture that agrees with the code by
coincidence rather than by construction. The tuple is one import away.

**T3 — do not copy `_LANDING_ONLY_CHECKS` into the test.** FR-005 says import
the predicate. Restating the four names and three prefixes in a test file
produces two lists, and the day someone adds a fifth landing check the test keeps
passing against the old set. This repository has the receipts for exactly this
failure mode in `tests/page_holds_true.py`, three times.

**T4 — the new check must not skip.** FR-004's whole value is that it runs when
nothing else in the tier does. If it acquires an environment guard, a network
call, or an import of something that needs credentials, it becomes a second
invisible test and this spec has produced nothing. Verify by running it with a
deliberately emptied environment.

**T5 — the coverage guard must fail closed.** FR-007's guard is worth having only
if a live module that writes a manifest and is not covered turns it red. A guard
that reports "0 uncovered modules" because its own discovery found no modules is
the vacuous sweep this repository has shipped before. Prove it by adding a
throwaway manifest-writing module in the test and asserting the guard notices.

**T6 — US3 is a describer, not a gate.** FR-009 is a hard boundary. A summary
hook that fails a run when a tier did not execute would turn every developer's
`pytest -q` red for lacking production credentials, and the first response would
be to delete the hook. Report; do not judge.

**T7 — do not "fix" the judge's spend-log requirement.** Seven of the nineteen
errors on 2026-08-27 came from `tests/test_live_judge.py:348`, where a real judge
call completes and no spend-log row appears within 90s. That is a fact about the
operator's LiteLLM deployment, tracked as
`ci/live-tier-fails-on-missing-spend-log-rows`. It is out of scope, and the only
way to make it green from inside this repository is to weaken an assertion that
exists to prove per-persona attribution. Leave it alone.

**T8 — the live modules must stay importable without credentials.** US2 imports
them. If any live module grows a module-level environment read, US2's check dies
at collection and the guard it provides evaporates. If one already does, that is
a finding to file and a line to move into a fixture, not a reason to guard the
import.

## Work Graph

```yaml
US1:
  implements: [FR-001, FR-002, FR-003]
  depends_on: []
US2:
  implements: [FR-004, FR-005, FR-006, FR-007]
  depends_on: []
  depends_on_merged: [US1]
US3:
  implements: [FR-008, FR-009]
  depends_on: []
```

US2 asserts that the corrected manifest onboards, so it waits for US1 to land.
US3 owns `tests/conftest.py` alone and shares no file with either, so it runs
concurrently.

## Sizing

Three small stories. US1 is two edits and two tests. US2 is one new module. US3
is one hook.

**The risk is not size, it is the shape of the temptation.** Every story here
can be made green by a cheaper change that reintroduces the defect: hardcode the
backend (T2), copy the check list (T3), guard the new test behind the same
environment that hid the old one (T4). A landed story that did any of those has
delivered a green suite and no protection, which is precisely the state this
spec was written to end.

## File contention

| story | owns |
| --- | --- |
| US1 | `tests/test_live_epic.py`, and its new tests |
| US2 | `tests/test_live_fixtures_onboard.py` (new) |
| US3 | `tests/conftest.py` |

No two stories own a file. US2 reads US1's module but does not edit it.

## Dispatch hazards, for the operator running this epic

- **Re-derive the workgraph at dispatch** with `--target-repo "$PWD"` from the
  operator checkout; the committed artifact carries compile-time absolute paths.
- **This epic edits `tests/conftest.py` (US3).** That file is imported by every
  test in the suite, so a defect there fails every subsequent node's gate for a
  reason that node cannot see. It is concurrent with US1/US2 by file ownership,
  but if the floor is being watched rather than left alone, landing it last costs
  nothing.
- **Do not run `scripts/gate-commit` while an attempt is in flight.**
- **The live tier will still be invisible to the gate after this lands.** That is
  intended. US2 is what makes the gate notice, and it notices by checking inputs,
  not by running the tier.

## Verification the operator will run, independent of the gate

The gate can prove the smoke would start. It cannot prove the smoke finishes,
because the gate does not run it.

After it lands, once, deliberately: `eval "$(scripts/ergane-env.sh)"`, then
`uv run pytest -m live_epic -q`, and watch a real agent turn `check_greet` green
against a real proxy. Then revert the manifest's runtime to
`python:3.11-bookworm` in a scratch copy and watch US2's check go red naming the
backend.

Twelve days of green gates proved neither of those. A spec that ends with a green
gate and no run would be the third time this repository accepted the same
evidence.
