# Implementation Plan: a landing refuses before the build, not after

**Spec**: `specs/107-a-landing-refuses-before-the-build-not-after/spec.md`
**Evidence base**: six finding keys, declared in the spec's frontmatter and read
with `ergane findings list`. Their notes carry the measured reproductions.

**Every line number below was read individually off `0f77873` on 2026-08-25**,
and the three git behaviours the plan turns on were *run*, not recalled. Re-verify
before flipping to ready, per house rule.

**Repaired 2026-08-25 against an adversarial review, same sha.** One blocking
finding — US5/FR-014's unruled implementation seam — is closed by **R13**. Six
non-blocking findings are closed: two wrong anchors (`ensure()`'s second create
path is `:368`, not `:380`; `reset()` archives at `:1086`, not `:1085`), **R7**
reversed from refuse to ignore-and-log, **R14** added for the retryability
asymmetry at US2's activity boundary, **R5** extended with the split-host answer,
trap 16 given two measured diff sizes, § Sizing given US6's fallback split seam,
and the trap count harmonised at four across all three documents. R14 introduced
a real slice contention with US3, which is why US2 now waits on US3 as well as
US1 — see the closing paragraph of R14.

## Terminology: "owning clone" and "dispatched target repo"

Two repositories are in play in almost every paragraph, and calling either one
"the repo" is how yesterday's diagnosis went wrong. Say **owning clone** for the
repository whose `.git` holds the worktree's registration and the node branch,
and **dispatched target repo** for `graph.target_repo` — the one the epic was
started against. When they are the same, everything works. This spec exists
because nothing checks whether they are.

## What already exists, and where

### US1/US2 — the worktree module (`factory/workgraph/worktree.py`, 1322 lines)

- `:217-231` `PreparedWorktree` — four fields: `path`, `branch`, `base_ref`,
  `default_branch`. **None names a repository.** Confirmed against the live
  sidecar at `.factory/worktrees/104-install-brings-the-container-up-configured/us5.json`,
  which records `default_branch: ergane-buildout` for a directory sitting under a
  clone checked out on `spec-routing-plan`.
- `:243-250` `worktree_path(factory_root, epic_id, node_id)` — the path is a pure
  function of three values, and `target_repo` is not one of them. The docstring
  at `:246-249` states why, and that reason is still good: factory state inside
  the target clone reads as agent work in 002's diff check. **Do not change this
  function.** The brief that produced this spec calls it "node_worktree_path
  (~:249)"; the symbol is `worktree_path`, `def` at `:243`, `return` at `:250`.
- `:303-378` `ensure()` — the only creator of a node worktree in the tree.
  - `:329` `if path.is_dir():` — the whole reuse decision.
  - `:331-337` the recorded-sidecar branch: checks only that the recorded
    `base_ref` is an ancestor of the new repo's landing head — which **both
    clones of one GitHub repo pass**, because every sha resolves in both — then
    returns the sidecar verbatim.
  - `:339-348` the adopt branch, and the worse half: a surviving directory whose
    sidecar was swept is adopted with no identity check at all. `_head(path)` is
    read from the FOREIGN repo's HEAD and `_default_branch(repo)` from the NEW
    repo's checked-out branch, and the two are written into one fresh sidecar.
  - `:368` and `:374` the two create paths — `git -C <target_repo> worktree add`.
    `:368` is the surviving-branch checkout (inside the `_branch_exists` arm that
    opens at `:361`); `:374` is the fresh-branch create. `:380` is a blank line
    and the brief's citation of it is wrong; the function ends at `:378`. The
    registration lands in the owning clone's `.git/worktrees/<node_id>/`, and the
    worktree gets a `.git` FILE reading `gitdir: <owner>/.git/worktrees/<node>`.
    That file is the only on-disk record of ownership and nothing reads it for
    identity.
- `:448-464` `push_branch` — US2's function. `repo = Path(target_repo)` at `:448`,
  `path = worktree_path(...)` at `:449`, the trunk guard at `:451-458` (which
  already reads the *declared* branch via `landing_branch`), the only other guard
  `if not path.is_dir()` at `:460`, the push in `repo` at `:463`, and the sha read
  out of `path` at `:464`. Nothing establishes that `path` is a worktree OF `repo`.
- `:691-705` `_main_worktree(path)` — already resolves the owning clone from a
  linked worktree via `git worktree list --porcelain`. The primitive exists; it is
  currently used only by the mirror path. **It is necessary and not sufficient**
  — see trap 1.
- `:908-931` `sync_with_target` — US2's second function: `default = landing_branch(repo)`,
  fetch in `repo`, merge `origin/<default>` inside `path`. Same split, recovery path.
- **US2's activity boundary, which is asymmetric with US1's until US2 fixes it.**
  `merge_activities.py:367-368` converts *every* `WorktreeError` into
  `ApplicationError(str(exc), type=PUSH_FAILED)` — no `non_retryable`, and
  `PUSH_FAILED`'s own docstring at `:77-80` says "Retryable, like the worktree
  operations: a lock or a slow filesystem is what a second attempt fixes." The
  call site uses `_GIT` (`workflow.py:379-382`), whose `_RETRIES`
  (`workflow.py:335-338`) is `maximum_attempts=3`. So without R14 the very
  condition US1 refuses permanently would be retried three times at the push.
  See R14.
- `:964-980` `landing_branch(repo)` — **the authoritative source, already in the
  tree.** Reads `factory.yaml`'s `landing_branch` (parsed at
  `factory/verify/factory_yaml.py:482`), falling back to the checked-out branch
  only on `FactoryConfigError`/`OSError`. Its docstring calls itself "a *decision*
  about which branch matters for landing… it replaces the three separate guesses
  the factory used to make". `ensure()` is the guess it never replaced.
- `:982-993` `_default_branch(repo)` — `git symbolic-ref --short HEAD`. The
  observation. Live: `/home/admin/code/ergane` answers `spec-routing-plan`;
  `/home/admin/code/ergane-roadmap-target` answers `ergane-buildout`.
- `:1059` `reset()` (which archives at `:1086`, under the `had_directory or
  had_branch` guard at `:1085`), `:1122` inside `remove()`, and
  `:1212` inside `_archive_node` — all three shell
  `git -C <target_repo> worktree remove --force <path>`. **Measured in a two-repo
  fixture: from a non-owning repo git answers `fatal: '<path>' is not a working
  tree`.** The operator's escape hatch is broken the same way the push is.
- `:1302-1315` `_branch_exists(repo, branch)` — a ready-made predicate. Verified
  live: `/home/admin/code/ergane` says NO for `factory/104-…/us5`;
  `/home/admin/code/ergane-roadmap-target` says YES.
- `:145-160` `resolve_factory_root(env_name)` — how any host-side caller gets the
  root. US4 needs this; the workflow may never call it.

`factory/activities/agent_activities.py`:

- `:125-145` the error-type constants, with `STANDARDS_MISSING` at `:131` and
  `WORKTREE_FAILED` at `:137`, each with a docstring explaining *why* it is or is
  not retryable. US1's new constant goes here, in that style.
- `:398-411` `prepare_worktree`'s `asyncio.to_thread(worktrees.ensure, …)` — the
  only caller of `ensure()` on the dispatch path, converting `WorktreeError` into
  a **retryable** `WORKTREE_FAILED` at `:407`.
- `:413-437` `_require_standards` — **the exact precedent US1 copies**: a
  structural refusal raised as a non-retryable `ApplicationError` from this same
  activity, with a message naming both the path and the node.

### US3 — the landing base (`factory/activities/merge_activities.py`, `factory/workgraph/workflow.py`)

- `merge_activities.py:347-384` `open_landing_pr` — pushes, then
  `forge.open_proposal(base=request.base, …)` at `:379`. No validation, no
  re-resolution, no mention of where the value came from. The module already
  imports `worktrees`, and a git read inside an activity is constitution-IV-legal
  where the workflow's would not be.
- `workflow.py:2833-2844` — the first landing, `base=prepared.default_branch` at
  `:2839`.
- `workflow.py:3547-3558` — the requeue after a rejection, `base=prepared.default_branch`
  at `:3553`. **The site a busy epic runs most.**
- `factory/mergequeue/models.py` `LandingConfig` — five dials, no branch. There is
  no landing-branch input, and `factory/roadmap/schedule.py:14-18` rules on why:
  one "would be a second answer to 'which branch does the factory land on', which
  `roadmap_activities` already derives from the target clone's manifest".
- `factory/activities/roadmap_activities.py:191` and `:296` — the roadmap's own
  derive path already resolves it correctly with `landing_branch(...)`. **The
  landing path is the outlier, not the rule.**
- `tests/test_worktree.py:440` `test_prepared_worktree_default_branch_still_reports_checked_out_branch`
  — read this test before touching anything. See trap 3.

### US4 — the pre-dispatch seam (`factory/workgraph/preflight.py`)

- `preflight.py:1-45` — the module docstring is this spec's thesis, written a
  fortnight earlier: "knowable offline, ruinous at dispatch". It names the
  2026-08-15 epic that died one tick after dispatch for a fact a file read would
  have caught.
- `preflight.py:99-118` `PreflightFinding` — `check`, `passed`, `detail`,
  `transport`. Four fields, already rendered by both surfaces. **Use it. Do not
  invent a finding type.**
- `factory/cli/nouns/build.py:316-332` `_run_preflight(graph)` — assembly first,
  then aliases, both collected rather than short-circuited, with the reasoning in
  the docstring. `:684-695` is where `_start_epic` calls it, prints
  `ergane: preflight [<check>]: <detail>` per finding, and abandons dispatch.
- `factory/activities/roadmap_activities.py:389-420` `preflight_spec` — the same
  two checks from the same module for the scheduled path, with `PreflightInput`
  at `:320-345` carrying `graph`, `proxy_url`, `spec_dir`, `specs_root`. Its
  docstring states the rule US4 must obey: the pure checks live in the preflight
  module so the two surfaces cannot drift.
- `workflow.py:1046-1073` `_onboard_target`, called at `:864` — the other,
  earlier gate: it renders a `Finding` list into a non-retryable `GRAPH_INVALID`
  before `_resolve`, before any persona, key or worktree. **It is not where US4
  goes** (see ruling R4), but read it: it is the shape a refusal takes here.
- `workflow.py:1564-1580` — the dispatch sequence, and the answer to "what is the
  latest free moment": `snapshot_criteria` (`:1564`) → `prepare_worktree`
  (`:1574`) → … → `issue_attempt_key` (`:1667`). `:1667` is the first line that
  spends money; everything at or before `:1574` is free.

### US5 — session identity (`factory/workgraph/models.py`, `adapter.py`, `agent_activities.py`)

- `models.py:400-419` `AttemptContext` — the docstring at `:405-406` states the
  replay contract: "`session_id` is generated with `workflow.uuid4()` so a replay
  reuses the id it already issued", and the same paragraph declares the field set
  **closed on purpose**. US5 adds no field.
- `workflow.py:1704` and `workflow.py:3414` — the two issue sites, normal dispatch
  and REJECTED-landing recovery. **US5 changes neither.**
- `workflow.py:2180-2186` — `start_activity(run_agent_attempt, activity_id=context.node_id,
  heartbeat_timeout=_agent_heartbeat_timeout(...), retry_policy=_AGENT_RETRIES)`.
  Temporal serialises the `AttemptContext` into history once; the retry
  re-delivers the identical bytes.
- `workflow.py:340-348` `_AGENT_RETRIES` (`maximum_attempts=2`) — its docstring
  says the relaunch exists because "a worker that died mid-attempt leaves an
  orphaned agent the adapter reaps before starting again (R4), which is worth
  exactly one retry". The repeated id makes that designed-for recovery
  structurally impossible.
- `workflow.py:445-460` `_agent_heartbeat_timeout` — `max(min(timeout_s/2, 120s),
  5 × HEARTBEAT_INTERVAL_S)`. Why four nodes died within three seconds of each
  other: under a stalled worker every in-flight agent activity times out inside
  one ~2-minute window.
- `adapter.py:1051-1061` `argv` — `--session-id <context.session_id>`, the one
  place the id becomes a runner-visible fact.
- `adapter.py:1355-1369` `_archive_session` — the transcript is looked up at
  `$HOME/.claude/projects/<slug>/<session_id>.jsonl`. **Launch key and archive key
  are the same string; they move together or they disagree.**
- `adapter.py:998` `with (archive / STDOUT_LOG_NAME).open("wb") as log:` — the
  truncating open. Corroborated on disk: `.factory/transcripts/088-…/us2/attempt-1/`
  holds two different `<uuid>.jsonl` files beside a stdout.log of zero bytes.
- `adapter.py:1320` `_reap` — kills the orphaned process group from the node pid
  file before relaunching. It handles the PROCESS. The contended resource is a
  FILE.
- `adapter.py:157` `SUBSCRIPTION_REFUSAL_MARKER` and
  `agent_activities.py:515-546` `_classify_subscription_auth_failure`, called at
  `:492` on `run_agent_attempt`'s success path — **the precedent US5's FR-014
  copies for DETECTION and not for OUTCOME**: an `AGENT_ERROR` whose archived stdout carries a known marker is
  reclassified in the activity that owns interpreting the adapter's output. Its
  outcome, `Termination.AUTH_FAILURE`, is the half FR-014 must not copy. See R13,
  which rules that seam so no story has to.
- `agent_activities.py:139-142` `AGENT_LAUNCH_FAILED` — "the activity error type
  for an agent that could not be started at all… Distinct from a non-zero exit,
  which is an `AGENT_ERROR` termination and ordinary ladder input." Raised
  non-retryable at `:510-512` from `run_agent_attempt`'s `except AdapterError`
  at `:507`.
- `workflow.py:655-658` `_LaunchFailed` and `workflow.py:2205-2211` — the
  workflow reads `cause.type == AGENT_LAUNCH_FAILED` off the `ActivityError` and
  raises the workflow-internal signal.
- `workflow.py:1978-1986` — what that signal buys: `record.launch_failures += 1`,
  launch evidence appended, and **no `AttemptRecord`**, "that is what
  `_attempts_spent` counts". Bounded separately by `config.max_launch_retries`
  at `:1989`. A launch fault costs no ladder attempt.
- `factory/usage/models.py:27-58` `Termination` and `factory/usage/ledger.py:77-79`
  the `termination IN (...)` `CHECK` list, migrated by `_widen_terminations`
  (`ledger.py:188`) reading the value list back out of the DDL. `ledger.py:157-160`
  records the two widenings in so many words: "008 added `'question'` on
  2026-08-07, 070 added `'auth_failure'`." **US5 adds nothing here** — R13 says
  why, and this entry exists so the implementer can see the cost it avoided
  rather than discovering it mid-story.
- `tests/test_usage_activities.py:586`, `tests/test_ledger_schema.py:300`,
  `tests/test_workgraph_models.py:634` parametrize over `list(Termination)`, and
  `tests/test_workgraph_sweep.py:1340-1343` over every member except `QUESTION`,
  asserting each "passes a green node and fails a red one". Four suites a new
  member would enter automatically; see R13 for why that assertion would be false
  for a launch that never produced a diff.
- `factory/verify/question.py:118-138` `_read_stdout` — where
  `TranscriptReadError("stdout.log not found in transcript")` is raised, which
  `verify_activities.py:378-379` turns into `DETECT_FAILED`. This is the message
  that named a missing file for a repeated identifier.
- `adapter.py:718-750` — `transcript_dir` (keyed by epic/node/**attempt**),
  `pid_file` and `home_path` (keyed by epic/node). `home_path`'s docstring —
  "per-node, not per-attempt: two concurrent nodes of one epic must not write one
  configuration file" — is the proof that two distinct NODES cannot see each
  other's session files. See trap 8.

### US6 — the landed reader (`factory/workgraph/landed.py`, `factory/workgraph/cli.py`)

- `landed.py:36-42` `_LANDING_RE` — `^<epic_id>/<node_id>: US<N>( (#<pr>))?$`,
  anchored at both ends, matched against the SUBJECT only.
- `landed.py:44-50` `_HISTORICAL_LANDING_RE` — **the decisive precedent**: a
  second accepted grammar, matched in the same pass, with its own provenance kind.
- `landed.py:56-61` `LandedKind` — `OBSERVED`, `ATTESTED`, `HISTORICAL`. Three
  already; a fourth is a shape this enum has.
- `landed.py:100-175` `landed_facts` — one newest-first scan; the comment fixes
  first-seen-per-story as the precedence rule; `:165-175` is the per-story
  attestation gap-fill, which is all-or-nothing per spec and cannot express "US1
  was rescued while US3 is genuinely unbuilt".
- `landed.py:230-245` `_git_log_subjects` — `--format=%H<TAB>%s`. **Subject only.
  The reader has never seen a commit body.** Verified working replacement shape,
  run on this repo: `git log -z --format=%H%x1f%B` — NUL between commits, unit
  separator between hash and body.
- `factory/mergequeue/messages.py:41-49` `pr_title` — the render end, whose
  docstring already names `_LANDING_RE` as the parse end and says a change to
  either must change both (D-034).
- `workflow.py:2829` `PrepareLandingPrInput(story_title=node.story_key)` — proof
  the title's story part is always literally `USn`, so only hand-opened PRs can
  fall outside the anchored grammar.
- `factory/workgraph/cli.py:165-195` — `ergane spec landed`: it already reads
  `spec_text`, resolves the repo, resolves `default_branch` via `landing_branch`,
  and prints one line per **landed** story. FR-017's printer goes here; the story
  list comes from the spec text it has already read.
- `factory/roadmap/models.py:94-105` — a SECOND `LandedKind` (`ATTESTED`,
  `OBSERVED`) belonging to the roadmap's *spec-level* dependency satisfaction.
  A read of every `LandedKind` reference on 2026-08-25 found no conversion
  between the two enums — but confirm that before assuming it, and if a
  conversion exists, the story covers both or says it does not.

## Rulings this plan makes, so no story has to

**R1 — The ownership check is two assertions in one git call.**
`git -C <path> rev-parse --path-format=absolute --show-toplevel --git-common-dir`
returns two lines. Assert BOTH: line 1 equals the resolved worktree path, and
line 2 equals the same read taken in the dispatched target repo. Measured at
3 ms on this repository. `--path-format=absolute` needs git ≥ 2.31; this host
runs 2.43.0. The porcelain form (`git worktree list --porcelain`) is acceptable
if a version floor is unwelcome — but it answers only the second assertion, and
the first is the one that matters (trap 1).

**R2 — One helper, and every site routed through it.** US1 defines it in
`worktree.py` beside `_main_worktree`. US2 and US4 import it. Nobody writes a
second derivation. The tree already holds three independent answers to "which
repo owns this worktree"; a fourth is only acceptable because it is the one the
others could have used, and a fifth is a defect.

**R3 — Refuse; never repair.** On a mismatch the factory stops and prints the
command. It does not remove the foreign registration, because that would delete
work in a repository the epic was never asked to touch — the inversion of
constitution VI from the other side — and because in the two-dispatcher
configuration a live node in the *other* dispatcher may be writing to that tree
at that moment.

**R4 — US4 goes in the preflight module, not in `_onboard_target`.**
`_onboard_target` is earlier and reads a repo through the forge; the preflight
module is where the two dispatch surfaces already share host-side, file-reading
checks, and it is the only place one implementation reaches both `ergane build
start` and the roadmap. `_onboard_target` also cannot read the factory root: it
is workflow-adjacent and the root is a worker-host fact.

**R5 — US4 does not make US1 redundant, and US1 does not make US4 optional.**
The preflight is epic-wide and can go stale — a late node in a long epic is
checked at onboarding and dispatched hours later. `ensure()` is per node and is
the last free moment. Ship both; one predicate; the preflight is the report and
`ensure()` is the enforcement.

**This is also the answer to the split-host case, and it is worth saying rather
than leaving the reader to join it to the Assumptions section.** `ergane build
start` runs in the operator's shell and resolves its own root through
`resolve_factory_root` (`worktree.py:145-160`); the worker resolves the worker
host's. On a deployment where those differ, the CLI arm of US4 reads a directory
tree that is not the one the epic will build in, so it can return **silence for a
graph that will strand** — an advisory check, not a gate. That is not a defect in
US4 and it must not be repaired by having the CLI reach the worker's disk. It is
why FR-009 requires the finding to NAME the root it read, so a reader can tell
"checked and clean" from "checked the wrong disk"; and it is why US1's `ensure()`
refusal, which runs on the worker beside the directory it is judging, is the only
real enforcement on such a host. US4 is the cheap early report; US1 is the
guarantee. Do not let a US4 test be written as if it were the guarantee.

**R6 — The base is resolved at open time, not at prepare time.** This is the
whole reason US3 lives in `open_landing_pr` and not in `ensure()`: a fix inside
`ensure()` cannot repair the four sidecars on this host that already record
`spec-routing-plan`, because `ensure()` returns `recorded` untouched at
`worktree.py:334`. A fix at open time corrects them retroactively.

**R7 — `OpenLandingPrInput.base` stops being a decision, and a non-empty value is
IGNORED AND LOGGED, never refused.** The two workflow call sites stop passing it.
Keep the field with an empty default so an activity task scheduled by an older
worker still deserialises, and let empty mean "resolve from the target repo's
manifest".

The drafting pass wrote "refused by name" here, on the reasoning that a field
which is quietly overridden is a lie in the payload. **That is reversed, and the
reversal is the whole point of this spec.** During any upgrade window an
activity task scheduled by pre-US3 workflow code and executed by post-US3
activity code carries a non-empty base — and on this host the value it carries is
*already the disagreeing one*: `prepared.default_branch` is `spec-routing-plan`
(four sidecars on disk record it) while `factory.yaml:43` declares
`ergane-buildout`. A refusal would therefore turn the ordinary pre-upgrade
payload into a dead landing after the build was paid for, which is the exact
class this spec exists to remove. Spec 082's rolling workers and the standing
"never modify factory code while an attempt is in flight" rule keep the window
narrow; they do not close it, and a fix that can only fail closed on the way in
is not a fix.

So: resolve from the manifest, ignore any supplied value, and when the ignored
value differs from the resolved one, say so on the activity's log line — the same
line FR-007 already requires, naming the resolved base, the repository and the
arm that answered. The payload is not a lie when the activity states plainly what
it did with it. This is an operator-visible behaviour change from the draft; it
is recorded here rather than left as the author's call.

**R8 — The derived session id is a `uuid5`.** The runner validates twice:
`Invalid session ID. Must be a valid UUID.` comes *before* `is already in use.`
`uuid5(namespace, f"{issued}:{attempt}")` is deterministic, valid, and derives
from values already in the frame. A suffixed string like `<uuid>-2` trades one
74-byte refusal for another.

**R9 — Derive once, at the top of the activity, and pass the replaced context
down.** `AttemptContext` is frozen, so use `dataclasses.replace`. Both `argv`
(`adapter.py:1059`) and `_archive_session` (`adapter.py:1364`) read
`context.session_id`, so one replacement moves both and they cannot disagree.

**R10 — The preserved log keeps the reader's filename.** Do not rename
`stdout.log` and do not append to it. Before the truncating open, if a non-empty
`stdout.log` is already there, move it aside to a name that states which
execution wrote it. `_read_stdout` (`question.py:118-138`) and the subscription
classifier keep reading exactly the file they read today.

**R11 — The rescue trailer is subordinate to both subject grammars.** For one
commit, try `_LANDING_RE`, then `_HISTORICAL_LANDING_RE`, then the trailer. The
newest-first, first-seen-per-story rule is unchanged. State the precedence in a
test, not in scan order.

**R12 — No auto-sweep of stale worktrees, and say so out loud.** `ergane build
kill` does not sweep — `kill_command` (`factory/cli/nouns/build.py:871`) sends a
signal and runs no git; `_kill_landings` (`workflow.py:1496-1528`) cancels the
poll tasks and never calls `_remove_worktree`; `_kill_remaining` (`:1530`) is
bookkeeping; `_reap_finished` (`:1486`) records a raised node coroutine as KILLED
and removes nothing. Removal lives only at `_close_out` (`workflow.py:2785`,
skipped on the PASS path by the `state is None` return at `:2784`) and at
`:3016`/`:3041` inside the landing poller a kill has just cancelled. So the state
US1 refuses on is produced by a mechanism this spec does not fix. **That is
deliberate**: a sweep built on today's `reset` would resolve the repo from
`workgraph.json` — the wrong repo in precisely the case that needs it — and would
inherit the same blindness. The sweep is follow-on work and belongs beside spec
100. What this spec owes the operator instead is a refusal that prints the exact
command, run against the owning clone, that clears it (FR-003). See trap 6.

**R13 — FR-014's refusal is a LAUNCH FAILURE, not a new `Termination`.** US5
copies the subscription precedent's *detection* and not its *outcome*. The named
launch refusal FR-014 asks for is
`ApplicationError(type=AGENT_LAUNCH_FAILED, non_retryable=True)`, the constant
already at `agent_activities.py:142`. **No member is added to `Termination`.**
This ruling exists because "follow the precedent exactly" has two defensible
readings whose blast radius differs by two modules and four test suites, and the
mid-story discovery of that is what trap 17 was written to prevent.

Why the existing constant and not a new member:

1. **A `Termination` is a graded ending; this one has nothing to grade.**
   `tests/test_workgraph_sweep.py:1340-1343` parametrizes over every member
   except `QUESTION` and asserts each "passes a green node and fails a red one".
   A launch the runner refused before the first token wrote no diff, so that
   assertion is not merely inconvenient for a new member — it is false for it.
2. **A `Termination` spends a ladder attempt and a launch fault must not.**
   `workflow.py:1978-1986` increments `record.launch_failures`, appends launch
   evidence, and pointedly does *not* append an `AttemptRecord` — "that is what
   `_attempts_spent` counts" — bounding launch retries separately at `:1989` via
   `config.max_launch_retries`. Charging the node an attempt for a collision the
   factory itself caused is the wrong accounting.
3. **It is the other half of the fix, not just a nicer label.**
   `session_id=str(workflow.uuid4())` is issued at `workflow.py:1704` **inside**
   the ladder loop, so the `_LaunchFailed` loop-around re-issues a fresh id.
   FR-012 clears the collision across an activity retry; FR-014's classification
   clears the residual case across the loop-around. Neither is dead code once the
   other lands — say so, or an implementer will read FR-014 as decoration.
4. **The cost avoided is real and was measured, not assumed.** A member means
   editing `factory/usage/models.py:27-58` and the `termination IN (...)` `CHECK`
   at `factory/usage/ledger.py:77-79`, whose value list `_widen_terminations`
   (`ledger.py:188`) reads back out of the DDL to migrate ledgers that already
   exist; and it enters four parametrized suites automatically
   (`tests/test_usage_activities.py:586`, `tests/test_ledger_schema.py:300`,
   `tests/test_workgraph_models.py:634`, `tests/test_workgraph_sweep.py:1340`).
   `ledger.py:157-160` names both prior widenings and 079-US3's wedge, which is
   what a mishandled one costs. US5 is at ten tasks and its diff must fit 65,536
   bytes; that work does not fit and does not belong here.

**The shape differs from the precedent and this is the part to get right.**
`_classify_subscription_auth_failure` *returns* a reclassified `AdapterResult`.
FR-014's classifier *raises*. The adapter does not raise `AdapterError` here —
the binary exists, it started, and it exited 1 — so the refusal arrives as an
ordinary `AGENT_ERROR` result with the marker in the archived stdout, and the
raise happens on the success path at `agent_activities.py:492`, beside (not
inside) the existing `except AdapterError` at `:507-512`. Copy the detection;
write the outcome fresh. If a member ever *is* wanted for ledger reporting, it is
a separate spec with the DDL and the migration in its scope.

**R14 — the ownership refusal is non-retryable at BOTH activity boundaries.**
US1's FR-003 makes it non-retryable at `prepare_worktree`; without this ruling
US2 would leave the identical condition on the retryable path, because
`merge_activities.py:367-368` converts every `WorktreeError` into `PUSH_FAILED`,
which is documented retryable at `:77-80` and whose call site carries
`maximum_attempts=3` (`workflow.py:379-382` → `:335-338`). Three retries of a
deterministic repository mismatch cost almost nothing in money and cost the whole
of what US2 is for: the refusal that was supposed to sharpen a day of misdirected
diagnosis arrives three times, interleaved with Temporal's own retry noise.

So US1 raises the ownership refusal as an exception type distinguishable from an
ordinary `WorktreeError` — it must be, or `prepare_worktree` could not satisfy
FR-003 either — and US2 catches that type first in `open_landing_pr`, ahead of
the existing `except worktree.WorktreeError`, raising a non-retryable
`ApplicationError` of its own type. One new constant in `merge_activities.py`, in
the style of `LANDING_REFUSED` at `:71-75` which is already the module's
non-retryable precedent. Every other `WorktreeError` stays on today's retryable
`PUSH_FAILED` path, untouched.

**R14 is what puts US2 behind US3 as well as US1, and that edge is deliberate.**
Once US2 edits `open_landing_pr` it is inside the same forty-line function US3
rewrites the base resolution in — including the docstring at
`merge_activities.py:356-357` ("Raises `PUSH_FAILED` (retryable) when git
refused"), which both stories have a reason to change. `ergane spec validate`
reports that contention as an advisory the moment R14 is written in; racing it
would let the merge queue reject whichever story landed second, and a
speculative-merge ejection is invisible to the poller. So the edge is declared,
in the direction that costs least: US3 is the defect that killed seven stories on
2026-08-24 and it starts at once, while US2 — the smallest story here, already
waiting on US1 — absorbs the wait. Ordering it the other way would have made the
highest-value fix the end of a three-deep chain. **If a refinement pass ever
drops R14, drop US2's `US3` edge with it and re-run `spec validate`**; leaving
one without the other is how a graph acquires a wait nobody can explain.

## Traps

Ten of these are drawn from the hazards three anchor readers found. **Four of
them decide whether an attempt lands** — traps 1, 3, 6 and the 8/9 pair — and
`tasks.md` reprints exactly those four in its preamble.

**1. THE MEASURED FALSE PASS — check the top level, not only the common dir.**
`ERGANE_ROOT` is `/home/admin/code/ergane/.factory`, i.e. *inside* the operator's
clone. The drafting session created a bare directory at
`.factory/worktrees/zz-probe-orphan/us1` — no `.git` at all — and git walked UP
and answered `--show-toplevel /home/admin/code/ergane`, `--git-common-dir
/home/admin/code/ergane/.git`, exit 0. A check that asks only "who owns this
worktree" — **including one built on the existing `_main_worktree`** — PASSES a
directory that is not a worktree at all. Assert `--show-toplevel == realpath(path)`
as well, and write US1-S3 as the test that proves you did. This is the single
most likely way to ship a green test that proves nothing.

**2. THE SIDECAR IS NOT THE AUTHORITY.** Adding a `target_repo` field to
`PreparedWorktree` (`worktree.py:217`) looks like the cheap fix and leaves the
worst branch open: the adopt path (`worktree.py:339-348`) fires *precisely when
the sidecar was swept*. Git answers the ownership question; a sidecar field, if
you want one at all, is a fast pre-check that saves a subprocess and decides
nothing. US1-S2 is the test that catches a sidecar-only fix.

**3. THE BASE FIX IS NOT WHERE IT LOOKS. Do not touch `ensure()`.**
`tests/test_worktree.py:440` is `test_prepared_worktree_default_branch_still_reports_checked_out_branch`.
Spec 020 fixed `push_branch`'s guard to read the declared branch, then
*deliberately* left `PreparedWorktree.default_branch` on the checked-out branch
and pinned it, with the written rationale "an observation about the clone, not a
decision… Repointing this field would make it lie about the clone's state." It
asserts `default_branch == "unrelated-local-work"`. Repointing
`worktree.py:346`/`:371`/`:377` to `landing_branch(repo)` breaks that test by
design, silently reverses a landed decision, AND does not repair the sidecars
already on disk. US3 changes the routing, never the value.

**4. TWO LANDING CALL SITES, NOT ONE.** `workflow.py:2839` is the first landing;
`workflow.py:3553` is the requeue after a rejection, and it is the one a busy
epic runs most — every node whose sibling lands ahead of it comes back through
it. A fix at `:2839` alone passes every happy-path test and leaves the common
case broken. US3-S3 exists to force the second one.

**5. `landing_branch()` FAILS OPEN.** `worktree.py:975-979` swallows
`FactoryConfigError`/`OSError` and falls back to the checked-out branch. A target
clone with a typo'd or missing `factory.yaml` silently reinstates the exact
defect being fixed, with no word to the operator. Every message and every result
must name WHICH arm answered — "declared in factory.yaml" versus "fell back to
the checked-out HEAD" — or the fix is untestable from the outside. FR-007 and
FR-010 are both this trap.

**6. THIS DEFECT HAS A PRODUCER AND THIS SPEC DOES NOT FIX IT.** Read R12. The
stale worktrees US1 refuses on are made by killed and raised nodes that nothing
sweeps. So a refusal that does not hand over a working command converts a silent
wrong-repo build into a hard dispatch stop the operator must hand-clean every
time — and the obvious command does not work: `remove()`, `reset()` and
`_archive_node` all shell `git -C <target_repo> worktree remove`, which answers
`fatal: '<path>' is not a working tree` from a repo that does not own the path
(measured in the fixture). **The remedy string is an acceptance criterion, not
polish.** It must be issued against the OWNING clone, and US1-S1 asserts it.

**7. DO NOT "FIX" THE PUSH BY MOVING IT INTO THE WORKTREE.** Both clones on this
host share origin `https://github.com/bryantharpeorg/ergane.git`, so relocating
`git push` into the worktree would pass every test here **while pushing on behalf
of the wrong repository**. The ownership assertion is the fix; relocation is a
coincidence that happens to be true on one machine.

**8. THE SESSION-ID FINDING'S OWN HEADLINE IS A MIS-DIAGNOSIS; DO NOT COPY IT.**
It says the id reaches "a second concurrently-live runner process… or a shared
agent state dir". There is no shared state dir — `HOME` is per `(epic, node)` and
`adapter.py:742` says so — and liveness is irrelevant: the drafting session
reproduced the refusal against a bare `<uuid>.jsonl` file with **no process
anywhere**, and a control run with a fresh uuid in the same HOME did not refuse.
The collision is **intra-node and sequential**, and it crosses exactly one
boundary: an activity retry. Concurrency is the trigger, not the mechanism. A
story written against "concurrent nodes collide" reaches for a lock or a
namespace and does not fix the retry.

**9. `record.attempt` IS NOT THE DISCRIMINATOR.** It is the ladder attempt and it
is identical on both executions of one activity — it is already in the payload.
Only `activity.info().attempt` tells them apart, and it exists only inside the
activity. That is why the fix cannot be workflow-side, and it is why the replay
property is preserved by construction: the workflow computes nothing new.

**10. DO NOT MAKE THE WORKFLOW LESS DETERMINISTIC.** No stdlib `uuid4`, no
`secrets`, no `os.urandom`, no `time.time()`, no environment read, and no change
to how many `workflow.uuid4()` calls a run makes — the Nth call's value is a
function of (run seed, call ordinal), so shifting the ordinal changes every later
id in the run. `interpreter/replay-test-nondeterminism-under-load` is already
promoted with eight occurrences; a determinism regression here is expensive and
slow to attribute.

**11. ASSERT THE BEHAVIOUR, NOT THE 74 BYTES.** The tell is
`Error: Session ID <36-char uuid> is already in use.` plus a newline, from claude
2.1.223. A criterion asserting the literal length rots on the next CLI bump. Test
that a second launch under the same id refuses and one under a derived id does
not; keep the byte count as narrative evidence.

**12. WIDENING THE LOG READ IS A CHANGE TO HOW IT IS SPLIT.** `_git_log_subjects`
(`landed.py:236`) is `--format=%H<TAB>%s` and the loop is line-oriented. A naive
`%B` mis-parses every multi-line message in the repository's history. Use a
record separator — `git log -z --format=%H%x1f%B` is verified working on this
tree — and rewrite the splitting loop. US6-S2 is the test that proves you did.

**13. ADD A GRAMMAR; DO NOT WIDEN `_LANDING_RE`.** Relaxing its anchors would
start matching ordinary operator subjects like `<epic>: US4 — …`, which
`landed.py:45-46` excludes on purpose, and would silently mark unbuilt stories
landed. That is a worse failure than the one being fixed. Same discipline for the
trailer: an epic or story the spec does not declare is ignored (US6-S4).

**14. NO RESCUE GRAMMAR RECOVERS PR #297.** Its subject is already on
`ergane-buildout` and rewriting the landing branch is not an option. One story of
spec 088 stays permanently invisible to `spec landed` and to `--delta`. Say so;
do not imply a recovery. The operator's standing workaround is to derive the full
graph and hand-build a remainder file for `build start`, never to trust `--delta`
on 088.

**15. NO SEAM CAPTURE IS NEEDED FOR US1–US4, AND REACHING FOR ONE IS
OVER-ENGINEERING.** The whole failure reproduces offline. The drafting session
built two `git init` repositories plus a local bare origin in a shared directory
and got, verbatim and with no network and no docker:

```
$ git -C B push origin factory/epic/us1
error: src refspec factory/epic/us1 does not match any
$ git -C B worktree remove --force <shared>/us1
fatal: '<shared>/us1' is not a working tree
```

So these acceptance criteria are **real committed tests**. Do not mock git, do
not stub a forge for the ownership assertions, and do not move anything to an
operator list. US5 is the one exception: its refusal needs a real `claude`
binary, so its criteria are the pure derivation plus an injected-runner seam
capture, labelled as such, with the two-execution reproduction on the operator's
list where it gates nothing.

**16. DIFF SIZE — SIZE FOR 65,536 BYTES, AND THE HEADROOM IS SMALLER THAN THE
TASK COUNT SUGGESTS.** `DIFF_INPUT_LIMIT` is `64 * 1024`
(`factory/verify/diffbounds.py:42`). Past it the deterministic check refuses the
diff and **the judge is never called**. One story on 2026-08-24 measured 65,200
of 65,536. Two landed nine-to-ten-task stories in this codebase, measured on this
tree with `git diff <sha>^ <sha> | wc -c`:

```
f1d480f  082-an-epic-finishes-on-the-code-it-started-with/us4: US4 (#296)   64,127
7c39b8a  103-install-proposes-personas-and-proves-them/us4: US4 (#303)      63,674
```

Both landed within 2 KB of the refusal. So a nine-task story here is not
comfortably inside the cap — it is at the cap, and the margin is a rounding
error. `worktree.py` is 1322 lines and densely docstringed: a story that rewrote
`ensure()`'s structure, added a two-repo fixture and touched the CLI would not
fit. Every story here is scoped to one helper plus two call sites plus its tests.
**No story may refactor a function it did not come to change**, and every story
of nine tasks or more has a named fallback split seam in § Sizing — use it rather
than trimming tests.

**17. SIBLING KEYS COLLIDE TOO — AND THAT IS OUT OF SCOPE.** `pid_file`
(`adapter.py:732`) and `home_path` (`adapter.py:742`) are keyed by the identical
`(factory_root, epic_id, node_id)` triple with the same missing `target_repo`.
`pid_file` is the R4 stale-process guard. A worktree-only fix leaves two
dispatchers of one epic id sharing a stale-process handle and a HOME. This is
named here so no implementer discovers it mid-story and widens scope. It is
follow-on work; do not do it here.

**18. THE WORKER IMPORTS THIS CODE LIVE.** `worktree.py`, `merge_activities.py`,
`workflow.py`, `adapter.py` and `agent_activities.py` are all in the dispatch or
landing path. Per `CLAUDE.md`, none of it may be modified while an attempt is in
flight, and the constitution reaches agents only via the landing branch. Note the
irony that a worker restart is itself the prime trigger for the retry storm US5
is about.

## Sizing

Six stories, fifty-six tasks, none over ten, every diff scoped to fit inside
`DIFF_INPUT_LIMIT`. Ten is the ceiling here rather than eleven because trap 16's
two measurements put a nine-task story within 2 KB of the refusal; the two
ten-task stories (US1, US5) are the two whose tasks are smallest.

- **US1** is the largest of the worktree pair: one ~20-line helper, two guarded
  branches, one error constant, one raise site, and a two-repository fixture that
  the next two stories reuse. Ten tasks.
- **US2** is small because US1 already paid for the predicate and the fixture:
  two call sites in `worktree.py`, one `except` clause and one error constant in
  `merge_activities.py` (R14), and their tests. Nine tasks.
- **US3** is ~15 lines in `open_landing_pr`, two one-line workflow edits, and the
  fixture nobody has built yet — a clone whose checked-out branch and declared
  landing branch DIFFER. The fixture is the work; every existing fixture in the
  tree sets both to `main`, which is why the suite is green against a broken base.
  Nine tasks, the ninth being R7's ignored-base test, which reuses that same
  fixture and adds one request field.
- **US4** is one pure function per check plus two thin wirings. Nine tasks. Watch
  the temptation to re-derive ownership locally instead of importing US1's helper
  (R2).
- **US5** is a pure derivation, one `dataclasses.replace`, one file move before an
  existing open, and one classifier following an existing precedent's detection
  and raising the error type that already exists (R13). Ten tasks, **re-checked
  after R13**: the ruling takes work off this story rather than adding it — no
  enum member, no DDL edit, no ledger migration, no new case in four parametrized
  suites — so ten is what it was and what it stays. The only tree-wide edit US5
  makes is inside `agent_activities.py` and `adapter.py`.
- **US6** is the one with a real parsing change in it — the log split. Nine tasks,
  and the multi-line fixture is worth building first.

If US1 must be split at refinement, the seam is "helper + its tests" versus "the
two `ensure()` guards".

**US6's fallback split seam, if its diff approaches the cap:** the log split
(`_git_log_subjects` rewritten to `git log -z --format=%H%x1f%B`, plus its
multi-line-body fixture repository and the parse test, FR-016) is one half, and
the trailer grammar plus its provenance kind plus the CLI printer (FR-015 and
FR-017) is the other. The seam holds because the first half is a pure change to
how the log is *split* and leaves every existing grammar reading exactly what it
reads today — it is shippable and green on its own — while the second half needs
bodies to be visible before it can match anything in one. Split in that order,
never the reverse. Trap 16's measurement is why this seam is named rather than
assumed unnecessary: nine tasks landed 63,674 bytes on 103/us4, and US6 carries a
fixture repository, five tests and a pasted-evidence file.

Do not split US2, US3 or US5, whose halves share every fixture.

## What else is in flight, and why it does not collide

- **Spec 099** (`a-worker-restart-does-not-orphan-the-work-in-flight`, draft) is
  the sibling of US5 and owns the *other* half: `_AGENT_RETRIES`, the heartbeat
  bounds and the restart itself. US5 changes what an execution is called and what
  it does to its predecessor's log; it does not touch `workflow.py:340-348` or
  `:445-460`. **Neither spec may edit `_AGENT_RETRIES`.** If 099 is dispatched
  first, re-read this section before dispatching US5.
- **Specs 104/105/106** touch `install.py`, `init.py`, `build.py` and
  `container/`. US4 touches `factory/cli/nouns/build.py` — a different `build.py`
  from 105/106's install-side edits, but confirm the region before dispatching
  them into the same window; the merge queue handles disjoint regions, and a
  speculative-merge ejection is invisible to the poller.
- **Spec 100** (`a-reset-leaves-nothing-behind`, no trio yet) is where the
  kill/reset sweep belongs (R12). This spec deliberately leaves it there.
- **Spec 088** is landed but its US1 is permanently invisible to `--delta`
  (trap 14). Do not use 088 as a fixture for anything US6 asserts.

## Verification the operator will run, independent of the gate

None of these gate a story. All of them are the run that makes the work real.

1. **Clear the live landmine, then dispatch 104.**
   `.factory/worktrees/104-install-brings-the-container-up-configured/us5` is
   registered to `/home/admin/code/ergane-roadmap-target` right now. Capture its
   `rev-parse` output as the before-picture *first* — it is the live reproduction
   for US1 and US2 — then clear it from the owning clone, then dispatch 104 and
   watch the factory open its own PR.
2. **The two-dispatcher collision, on purpose.** Dispatch one epic id by hand
   against `/home/admin/code/ergane` while the roadmap holds
   `/home/admin/code/ergane-roadmap-target`, and confirm the refusal arrives
   *before* an agent starts and prints a command that actually works when pasted.
3. **A landing from an operator branch.** Check the target clone out on any
   branch other than `ergane-buildout`, dispatch one small story, and confirm the
   PR opens against `ergane-buildout` anyway — the base this spec exists to fix.
4. **The session-id reproduction, with a real runner.** In a scratch HOME
   containing only `$HOME/.claude/projects/<slug>/<uuid>.jsonl`, run
   `claude -p --dangerously-skip-permissions --session-id <uuid>` and watch it
   refuse in 74 bytes; repeat with the derived id and watch it proceed. Then run
   one epic at `--max-concurrent-nodes 2` and see whether the cap is safe again.
   **Do not raise the cap unattended before this run passes** — the standing
   operator rule is cap 1.
5. **A rescue, end to end.** Take one story, open its PR by hand with the trailer
   `ergane spec landed` printed for it, merge it, and confirm `ergane spec landed
   --default-branch ergane-buildout` sees it with the rescue kind. Remember that
   `spec landed` scans `main` by default and the factory lands on
   `ergane-buildout`; without the flag this check reports a false negative and
   looks exactly like the fix failing.
6. **`ergane spec derive --delta` with `-o`, always.** Without `-o` it overwrites
   the tracked `workgraph.json`.
