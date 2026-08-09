# Implementation Plan: Landing Attribution

**Branch**: `020-landing-attribution` | **Date**: 2026-08-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/020-landing-attribution/spec.md`

## Summary

One optional manifest key, and a second regex. US1 makes the landing branch a
declaration instead of three guesses, and threads it through the sites that
*decide* on a branch while leaving alone the sites that merely *report* which
branch a clone is on — that distinction is the whole of the story's difficulty.
US2 teaches `landed_facts` the subject line git wrote before the merge queue
owned it, in the same `git log` pass, with its own provenance kind.

This plan is deliberately self-contained: the prompt assembler ships
spec/plan/tasks only, so every fact an implementer node needs is inlined, each
verified against the tree on 2026-08-09 — and T001 re-verifies them against the
tree that actually hosts the work.

## Technical Context

**Language/Version**: Python 3.11+ (D-003); the worker host runs 3.13.

**Primary Dependencies**: none added. `re`, `pathlib`, and the manifest parser
that already exists.

**Verified reuse inventory** (file:line as of 2026-08-09; T001 re-checks):

- **The manifest schema**: `_TOP_LEVEL_KEYS = ("version", "runtime", "gates",
  "timeouts", "standards")` at `factory/verify/factory_yaml.py:61`, with
  `_reject_unknown_keys` at `:138` — adding a name to that tuple is the whole of
  "the schema now accepts it". `parse_factory_config` at `:85` reads each key
  through a `_read_*` helper and assembles `FactoryConfig`; `_read_standards`
  (`:268`) is the exact template for an optional string key, including the
  "declared means declared" refusal of `standards:` with no value (`:274-283`).
- **The manifest loader, and the posture for a missing file**:
  `load_factory_config(source)` at `factory/verify/factory_yaml.py:294`, and
  `_declared_standards(target_repo)` at
  `factory/activities/agent_activities.py:655`, which wraps it in
  `except FactoryConfigError: return None` and whose docstring explains *why*
  absence is not a failure here. Copy that posture for a repo with no manifest;
  do **not** copy it for a manifest that declares the key badly (FR-001).
- **The six `_default_branch` call sites** (`factory/workgraph/worktree.py:417`,
  which runs `git symbolic-ref --short HEAD`). They are not the same kind of
  call, and this is the story's central distinction:

  | site | what it is asking | US1 |
  | --- | --- | --- |
  | `capture_base_ref:176` — `rev-parse origin/<branch>` | what every node branches from | **must use the declared branch** |
  | `push` guard `:302` — refuse `branch == default` | which name a node must never push over | **must use the declared branch** |
  | `land`/salvage fetch `:363` — names `remote/<default>` | which head a merge edge rebases onto | **must use the declared branch** |
  | `ensure:212` and `:228` — `PreparedWorktree(..., _default_branch(repo))` | which branch this clone has checked out | **leave alone** — the field records an observation about the clone |
  | `roadmap_activities.py:108` and `:184` — `CloneResult.default_branch` | same observation, reported to the roadmap | **leave alone** |
  | `roadmap_activities.py:268` — feeds `landed_facts` | which branch to scan for landings | **must use the declared branch** |

- **`roadmap_activities._default_branch`** at `factory/activities/roadmap_activities.py:216`
  is a *second*, distinct helper: it wraps the worktree one in a try/except and
  falls back to the literal `"main"`. It is used at `:268` only. FR-004 is about
  this one.
- **The CLI's two branch decisions**: `landed_command` at
  `factory/workgraph/cli.py:215` passes `args.default_branch` straight through
  (`:232`), and `_build_baseline` at `:336` assigns `default_branch = "main"` at
  `:348` with no flag anywhere on the `derive` parser. Both already hold the
  repo path — `_target_repo_for_spec(spec_dir)` at `:230` and `:347` — so both
  can read the manifest without a new argument.
- **The parser**: `landed.add_argument("--default-branch", default="main", ...)`
  at `factory/workgraph/cli.py:895`.
- **The landing grammar**: `_LANDING_RE` at `factory/workgraph/landed.py:39`,
  matched at `:104` inside `landed_facts` (`:81`). The loop is newest-first with
  `if story_key not in observed` at `:110` — first-seen-wins.
- **`LandedKind`** at `factory/workgraph/landed.py:47`: a `StrEnum` with
  `OBSERVED` and `ATTESTED`, rendered by `landed_command` as
  `f"{story_key} landed at {fact.commit[:12]} ({fact.kind.value})"`
  (`factory/workgraph/cli.py:239`).
- **The log scan**: `_git_log_subjects` at `factory/workgraph/landed.py:154`
  runs `git log --format=%H\t%s <head> --` with **no `--no-merges`**. Merge
  commits are already in the stream; only the recognizer is missing.
- **The node-id convention that licenses the inference**: `id=story_key.lower()`
  at `factory/workgraph/derive.py:184`.

**The three historical subjects, verbatim** — the only commits this grammar has
ever produced, all reachable from `ergane-buildout`:

```
Merge branch 'factory/006-interpreter-hardening/us1' into ergane-buildout
Merge branch 'factory/006-interpreter-hardening/us2' into ergane-buildout
Merge branch 'factory/006-interpreter-hardening/us5' into ergane-buildout
```

**The near-misses that must not match**, all real subjects in this history:

```
salvage(006-interpreter-hardening/us5): completed attempt 1
salvage(003-merge-queue/us1): killed attempt 1
017-peer-channel: US4 — ephemeral consults + two-layer memory split
006 US1: attempt delivery-path and history-cost tests (T005, T006)
fix the us1×003 merge seam: recovery path called _attempt with a dead kwarg
```

The last three are operator commits. None contains `<something>/<something>:
US<n>` and none is a merge, so today's grammar already rejects them — but the
new recognizer must be written so it still does, and the salvage subject is the
dangerous one because it *does* carry `<epic>/<node>`.

**Storage**: none. No store, no schema migration, no state file.

**Testing**: `pytest`. US1's manifest half is unit-level against
`parse_factory_config`. US1's branch half needs a fixture git repository — a
clone checked out on an unrelated branch is the case that matters and it cannot
be faked with a string. US2 likewise wants a fixture repository containing a
real merge commit, not a list of subject strings; see the trap below.

**Project Type**: single Python package. Changes touch
`factory/verify/factory_yaml.py`, `factory/workgraph/worktree.py`,
`factory/workgraph/cli.py`, `factory/activities/roadmap_activities.py`,
`factory/workgraph/landed.py`, `factory.yaml`, and their tests.

## Constitution Check

- **I (build order)**: hardening on landed components; no reordering.
- **II (test-first)**: every task pairs a failing test with implementation.
- **III (dependencies)**: none added.
- **V (credentials)**: untouched. No credential is read, written, or logged
  anywhere in this feature.
- **VI (salvage)**: `land`'s fetch changes which head a merge edge rebases onto,
  which is a correctness fix rather than a change to the salvage contract. The
  terminal paths are untouched.
- **VII (persona routing)**: untouched; no model name is read or written.

## Approach by story

### US1 — the landing branch is declared once (FR-001..004)

Add `landing_branch` to `_TOP_LEVEL_KEYS` and a `_read_landing_branch` beside
`_read_standards`, differing in exactly one way: absent yields `"main"` rather
than `None`, because FR-001 makes the default explicit rather than optional at
the point of use. Add the field to `FactoryConfig`. Declare
`landing_branch: ergane-buildout` in this repository's own `factory.yaml`.

Then one new public helper — `landing_branch(target_repo) -> str` in
`factory/workgraph/worktree.py`, beside the private `_default_branch` it falls
back to. It reads the manifest with `load_factory_config`, returns the declared
value, and on `FactoryConfigError` or a missing file returns `_default_branch(repo)`
— which is today's behaviour, and is what FR-003's second sentence requires.
Point the four decision sites in the table above at it. Leave the four
observation sites alone.

**Trap — the argparse default is what silently defeats this story.**
`landed.add_argument("--default-branch", default="main")` means
`args.default_branch` is *always* truthy, so a manifest read after it can never
win and a test that only checks `landed --default-branch ergane-buildout` will
pass anyway. Change the parser default to `None` and resolve in the command:
explicit flag, else manifest, else `"main"`. The acceptance evidence for FR-002
is `factory-epic landed` **with no flag** returning the declared branch's
landings; write that test first and it cannot be faked.

**Trap — do not repoint all six `_default_branch` callers.** Two of them
(`ensure:212`, `:228`) fill `PreparedWorktree.default_branch`, which is a record
of *what this clone had checked out* when the worktree was prepared, and the
roadmap's `CloneResult.default_branch` is the same observation. Repointing those
would make the field lie. The table above is the authority; if a seventh caller
appears in the tree, classify it by the same question — *is this a decision or
an observation?*

**Trap — the push guard is a decision site and it is easy to miss.**
`worktree.py:302` refuses to push a node branch whose name equals the default,
so that a node never clobbers the trunk. If the declared landing branch and the
clone's checked-out branch differ, a guard reading the clone's branch is
guarding the wrong name. This is also the story's sharpest test: a clone checked
out on an unrelated branch, a node branch named after the *declared* one, and a
push that must be refused.

**Check before writing:** `factory/workgraph/worktree.py` does not currently
import from `factory.verify.factory_yaml`. Confirm that adding the import
introduces no cycle (`factory_yaml` imports `yaml` and `factory.verify.models`;
it does not import `worktree`). If it does cycle, the helper belongs in
`factory/verify/factory_yaml.py` instead and `worktree` calls it — decide on the
evidence, and say which you found.

### US2 — landings older than the merge queue are read as history (FR-005..008)

A second compiled pattern beside `_LANDING_RE`, matched in the same loop in
`landed_facts`. The subject is git's own:
`Merge branch 'factory/<epic_id>/<node_id>' into <branch>`. Anchor it end to end,
require the literal `factory/` prefix inside the quotes, and require the whole
subject to be that merge sentence — a loose pattern is what lets the salvage
subject through.

Story key from node id by upper-casing. Cite `factory/workgraph/derive.py:184`
in the code comment: `id=story_key.lower()` is the *entire* justification for the
inference, and a reader who does not know that line will read the upper-casing
as a guess. Guard it: if the inferred key is not one the spec declares, it is not
a landing (spec § Edge Cases), because inventing a story key is worse than
missing one.

A third `LandedKind`. The two existing members answer "by grammar" and "by
attestation"; this is a third answer and collapsing it into `OBSERVED` would tell
an operator that a fact came from the attribution contract when it came from a
subject git composed. `landed_command` already prints `fact.kind.value`
(`factory/workgraph/cli.py:239`), so the rendering follows for free — but assert
it, because "for free" is how a rendering regression ships.

**Trap — write the precedence rule down, do not inherit it.** A story with both
a pre-queue merge and a later queue landing resolves correctly today only because
the scan is newest-first and the loop says `if story_key not in observed`
(`factory/workgraph/landed.py:110`). That is a property of the loop's shape, and
the next person to restructure the loop will not know it is load-bearing. FR-007
wants a test that fails if the older fact wins, and a comment that says why the
order matters.

**Trap — test against a real repository, not a list of strings.** The recognizer
is trivially unit-testable against subject strings, and such a test would keep
passing if `_git_log_subjects` ever gained `--no-merges` — which would make the
whole story dead code, silently. At least one test must build a fixture
repository with a genuine merge commit and read it end to end.

**Trap — `salvage(<epic>/<node>): completed attempt 1` is in every branch's
history.** It carries the epic id and node id in the same order the new pattern
looks for them. It is the negative case that matters most; write it before the
positive one.

## Complexity Tracking

| Risk | Why it is real | Mitigation |
|---|---|---|
| The manifest never wins | `--default-branch` defaults to a truthy string, so the read happens but is discarded | Parser default becomes `None`; the acceptance test passes no flag |
| A `_default_branch` caller is repointed that should not be | Four of the six sites report an observation about a clone | The call-site table; classify by decision-vs-observation |
| The push guard keeps reading the clone's branch | It is the least obvious of the four decision sites | Its own acceptance scenario and its own test |
| The new recognizer eats the salvage subject | Same `<epic>/<node>` shape, present in every branch | Negative test written first |
| The story becomes dead code if the log scan changes | `--no-merges` would remove the input entirely, with every string-level test still green | One end-to-end test over a fixture repository with a real merge |
