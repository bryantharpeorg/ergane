---
state: ready
fixes:
  - workgraph/a-stale-node-worktree-from-another-target-repo-is-silently-reused
  - merge/open-landing-pr-pushes-from-a-repo-without-the-node-branch
  - merge/landing-base-comes-from-the-target-repos-checked-out-branch
  - mergequeue/landing-base-follows-the-operator-checkout
  - workgraph/concurrent-nodes-collide-on-agent-session-ids
  - merge/a-hand-harvested-pr-title-makes-the-landing-invisible
# DRAFTED 2026-08-25 by an operator session, from five findings measured on this
# host on 2026-08-23 and 2026-08-24 and from three parallel anchor readers whose
# every file:line was opened individually against the tree at 0f77873.
#
# THE DAY THIS SPEC IS PRICED FROM. On 2026-08-24 seven of eight stories passed
# every gate and their judge and then died in the landing path. All seven were
# rescued by hand as operator-opened pull requests. Not one of spec 088's four
# stories used the landing path. Every defect below charges the full build —
# agent time, gate, judge — before it announces itself, and then announces
# itself as a bare git error naming the wrong cause.
#
# SIX FINDING KEYS, FIVE DEFECTS. `mergequeue/landing-base-follows-the-operator-
# checkout` (2026-08-17) and `merge/landing-base-comes-from-the-target-repos-
# checked-out-branch` (2026-08-24) are ONE mechanism filed twice, seven days
# apart, both open, both counting one occurrence. The ledger cannot see that it
# recurred because the duplicate keys hid the count. US3 closes both, and both
# are declared above so the ledger stops disagreeing with the disk.
#
# WHAT THE DRAFTING PASS SETTLED, so nobody re-derives it:
#   - Findings 1 and 2 are ONE defect seen from two ends: a node worktree whose
#     git registration belongs to a repository other than the dispatched
#     `target_repo`. Finding 1 is the cause (silent reuse at prepare time),
#     finding 2 is the symptom (a push from a repo that does not hold the ref).
#     They are US1 and US2 for that reason, and they share one predicate.
#   - The path/registration split is CORRECT and this spec does not touch it.
#     `worktree_path` is anchored to ERGANE_ROOT on purpose
#     (`factory/workgraph/worktree.py:243-250`): factory state inside the target
#     clone reads as agent work in 002's diff check. What is missing is not a
#     different path — it is a check that the path's owner is the repo that
#     asked for it.
#   - Do NOT resurrect `roadmap/target-repo-does-not-own-the-factory-root-so-
#     every-node-strands`. It is resolved as a WRONG DIAGNOSIS: spec 103 ran
#     clean under the identical configuration once the stale worktrees were
#     cleared. target_repo does not need to own ERGANE_ROOT.
#   - Every failure in US1/US2/US3 reproduces OFFLINE. Two `git init` repos, one
#     shared directory and a local bare origin produce `error: src refspec ...
#     does not match any` and `fatal: ... is not a working tree` verbatim, with
#     no network and no docker. The drafting session ran it. So the acceptance
#     criteria here are real committed tests, never labelled seam captures — the
#     one exception is US5, which needs a real `claude` binary.
#
# DO NOT FLIP READY without a pre-dispatch review, and read plan.md § Traps
# first: four of them decide whether an attempt lands — traps 1, 3, 6 and the
# 8/9 pair, the same four `tasks.md` reprints — and one of them is a measured
# false pass that would let an implementer ship a green test proving nothing.
# Read § Rulings too: R7, R13 and R14 settle three seams that each had two
# defensible answers of different blast radius.
---

# Feature Specification: a landing refuses before the build, not after

**Created**: 2026-08-25
**Evidence base**: the six finding keys declared above, read with
`ergane findings list`. Their notes carry measured reproductions, not narration.

## The gap, stated precisely

The factory has a preflight. `_onboard_target` (`factory/workgraph/workflow.py:1046`)
promises in its own docstring to refuse "before `resolve_graph`, before any key
is issued, before any worktree is prepared", and `_run_preflight`
(`factory/cli/nouns/build.py:684`) refuses an unassemblable prompt and an
unserved alias before `ergane build start` prints a workflow id. Both are the
right shape. Neither asks any question about the *landing*.

So the landing path is where the factory spends first and checks afterwards.
Three preconditions decide whether a verified story can land, all three are
knowable at dispatch for the price of one `git` call, and all three are read for
the first time after the agent, the gate and the judge have been paid:

- **Which repository owns the node's worktree.** The worktree PATH is a pure
  function of `(factory_root, epic_id, node_id)` (`worktree.py:243`); the git
  REGISTRATION belongs to `target_repo`. `ensure()` reuses an existing directory
  on either of two branches (`worktree.py:329-348`) and neither asks who owns
  it. A live example is on this host right now:
  `.factory/worktrees/104-install-brings-the-container-up-configured/us5`
  reports `--git-common-dir` of `/home/admin/code/ergane-roadmap-target/.git`,
  while a dispatch naming `/home/admin/code/ergane` would push from a repo whose
  ref store has never held that branch.
- **Where the branch is pushed from.** `push_branch` (`worktree.py:448-464`)
  guards only that the branch is not the trunk and that the directory exists,
  then runs `git push` in `target_repo` and reads the returned sha out of the
  worktree. When the two disagree, git says `error: src refspec ... does not
  match any` and nothing else. That message sent one full day of diagnosis down
  the wrong path and produced a finding that had to be resolved as a wrong
  diagnosis.
- **What the PR is based on.** All three arms of `ensure()` capture
  `_default_branch(repo)` — `git symbolic-ref --short HEAD` of the target clone
  — into `PreparedWorktree.default_branch` (`worktree.py:346`, `:371`, `:377`),
  and the workflow spends it as `gh pr create --base` at
  `workflow.py:2839` and again at `workflow.py:3553`. Four sidecars on this host
  record `default_branch: spec-routing-plan`; older ones record
  `attest/023-042-landed` and `operator/apache-2-license`. Meanwhile
  `landing_branch(repo)` (`worktree.py:964`) already reads the declared answer
  out of `factory.yaml`, and `factory.yaml:43` declares `ergane-buildout`.
  Nothing in the PR-base path calls it.

Two further defects share the shape. An agent session id is issued once per
attempt with `workflow.uuid4()` and re-delivered byte-identical on an activity
retry, so the runner refuses the relaunch that `_AGENT_RETRIES` exists to
provide — and the retry truncates the log that would have said so. And the one
recovery path an operator has when a landing dies is a hand-opened pull request,
whose title must match an end-to-end anchored grammar (`landed.py:39`) that
nothing tells the operator, so a rescue that merges perfectly can be invisible
to `spec landed` and to `--delta` forever.

## The rule this spec is asking for

**Every precondition a landing depends on is checked before the build is paid
for; and where a check can only fire late, its refusal names the real cause, the
two things that disagree, and the command that fixes it.**

### The ruling, made here rather than left to the implementer

- **Git is the authority on who owns a worktree, and the sidecar is not.**
  `PreparedWorktree` (`worktree.py:217`) has four fields and none of them names
  a repository, and the branch of `ensure()` that would be repaired by adding
  one (`:341-348`) is precisely the branch that fires when the sidecar has been
  swept. The ownership question is answered by asking git, once, and by one
  helper that every caller routes through. The tree already holds three
  independent derivations of "which repo owns this worktree" — `_main_worktree`
  (`worktree.py:691`), `adapter._resolve_target_git_dir` (`adapter.py:577`), and
  the unstated assumption inside `push_branch`. This spec adds a fourth only if
  it is the one the others could have used; it does not add a fifth.
- **The check is two assertions, not one.** `--show-toplevel` must equal the
  resolved worktree path AND `--git-common-dir` must equal the target repo's.
  The second alone is a measured false pass: ERGANE_ROOT sits inside the
  operator's clone, so a bare directory under `.factory/worktrees/` makes git
  walk *up* and cheerfully report the operator clone as its owner. The drafting
  session created such a directory and watched it pass.
- **The landing base is declared, never observed — and a base still arriving in
  the payload is ignored out loud, never refused.** `landing_branch()` already
  exists, already reads `factory.yaml`, and already governs `push_branch`'s
  trunk guard four lines above the broken push. The base is resolved from it, at
  the moment the PR is opened, inside the activity — which retroactively
  corrects sidecars already written. `PreparedWorktree.default_branch` keeps
  meaning what a landed test says it means (`tests/test_worktree.py:440`: "an
  observation about the clone, not a decision"); it simply stops being routed
  into the most consequential decision in the landing path. During an upgrade
  window, a task scheduled by older workflow code still carries a base, and on
  this host that base is *already the disagreeing one* — four sidecars record
  `spec-routing-plan` against a `factory.yaml` declaring `ergane-buildout`. A
  refusal there would manufacture the very defect this spec removes: a landing
  that dies after the build was paid for. It is ignored, and the log line says it
  was ignored and what it disagreed with (plan R7).
- **A launch that never started is a launch failure, not a new kind of ending.**
  FR-014 reuses `AGENT_LAUNCH_FAILED`, the non-retryable activity error type
  already at `agent_activities.py:142` and already routed by the workflow into a
  bounded launch-retry loop that spends no ladder attempt. It adds no member to
  `Termination`, because a member is a *graded* ending and a refusal that
  produced no diff has nothing to grade. Plan R13 carries the full derivation,
  including the two modules and four parametrized suites a member would have
  reached.
- **A refusal states both sides and hands over a command.** The operator's
  escape hatch is itself broken — `remove()` (`worktree.py:1122`),
  `_archive_node` (`:1212`) and `reset()` (`:1086`) all shell
  `git -C <target_repo> worktree remove`, which answers `fatal: ... is not a
  working tree` from a repo that does not own the path. So the remedy text is
  part of the contract, not decoration: a refusal that does not name the OWNING
  clone leaves the operator with a hard stop and no move.
- **The session id is derived where determinism is not required.** The workflow
  keeps issuing `workflow.uuid4()` at both sites (`workflow.py:1704`, `:3414`)
  because the Nth uuid4 of a run must reproduce on replay. The per-execution
  value is derived inside the activity, from `activity.info().attempt`, which
  exists nowhere else and is the only thing that distinguishes an execution from
  its retry. `record.attempt` is the ladder attempt and is identical across a
  retry; it discriminates nothing.
- **A rescue gets a supported grammar, and the honest limit is stated.** The
  reader already accepts two grammars with two provenance kinds
  (`landed.py:39`, `:47`); a third is a shape it has. The trailer is set at merge
  time and is immutable afterwards, exactly like the subject — so this makes
  future rescues survivable and recovers PR #297 not at all.

## What this spec does not change

- **The worktree path convention.** `worktree_path` stays a function of
  `(factory_root, epic_id, node_id)` (`worktree.py:243`). Keying the directory
  by target repo would prevent one cause while leaving the bare-directory, the
  hand-deleted-branch and the cross-host-clone cases undetected, and would make
  paths unreadable to an operator debugging at 2am.
- **`PreparedWorktree`'s field set and the meaning of `default_branch`.**
  `tests/test_worktree.py:440` pins it deliberately and that decision stands.
- **The reuse rule.** `ensure()` still returns an existing worktree untouched —
  no fetch, no rebase, no reset (FR-013 of its own spec). The refusal fires only
  when the directory belongs to another repository.
- **Auto-repair.** Nothing in this spec removes, rebuilds or archives a worktree
  registered to a repository the epic was not asked to touch. That is an
  operator verb with the owning repo printed first, and it is not this spec.
- **`_AGENT_RETRIES` and the heartbeat bounds** (`workflow.py:346`, `:451`).
  Spec 099 owns the worker-restart half of this class; US5 changes what an
  execution is *called*, never how many there are.
- **`_LANDING_RE`'s anchors** (`landed.py:39`). A third grammar is added beside
  it. Relaxing it would start matching ordinary operator subjects, which
  `landed.py:45-46` excludes on purpose, and would silently mark unbuilt stories
  landed.
- **The `Termination` enum and the usage ledger's schema.**
  `factory/usage/models.py:27-56` gains no member and
  `factory/usage/ledger.py:77-79`'s `termination IN (...)` `CHECK` list is not
  widened, so `_widen_terminations` has nothing to migrate and the four suites
  that iterate `list(Termination)` gain no case. Plan R13 rules this; a
  ledger-visible termination for launch refusals, if it is ever wanted, is a
  separate spec that owns the DDL and the migration.

## User Scenarios & Testing

### User Story 1 - A worktree says which repository owns it (Priority: P1)

As the dispatch path, before an agent is paid for anything, I ask git which
repository owns the directory I am about to hand over — and I refuse a directory
that belongs to a different clone, naming both clones and the command that
clears it.

**Independent Test**: two `git init` repositories share one worktree root; a
worktree is registered to the first and `ensure()` is called for the second.
The call refuses; the message names the owning clone, the dispatched repo and a
remedy command; and a bare directory that is not a worktree at all refuses too
rather than passing by walking up the tree.

**Acceptance Scenarios**:

1. **Given** a node worktree registered to repository A and a dispatch naming
   repository B, **When** `ensure()` reaches its existing-directory branch with
   the sidecar present, **Then** it refuses instead of returning the recorded
   worktree, and the refusal names the worktree path, A as the owner, B as the
   dispatched target repo, and a `git -C <A> worktree remove --force <path>`
   remedy — proven by a committed two-repository test.
2. **Given** the same cross-registered directory with its sidecar swept,
   **When** `ensure()` reaches its adopt branch, **Then** it refuses on the same
   terms rather than adopting the foreign tree and minting a fresh sidecar from
   two repositories' answers — proven by a committed test, because this is the
   branch a sidecar field could never have protected.
3. **Given** a directory under the factory root that is not a git worktree at
   all, **When** the ownership check runs, **Then** it refuses naming that
   directory — and a test asserts it does NOT pass by inheriting the enclosing
   clone, which is what a `--git-common-dir` comparison alone would do.
4. **Given** a worktree correctly registered to the dispatched target repo,
   **When** `ensure()` runs, **Then** it returns exactly what it returns today,
   and the existing worktree tests pass unmodified — proven by the suite.
5. **Given** the refusal crossing the activity boundary, **When**
   `prepare_worktree` catches it, **Then** it surfaces as a NON-retryable
   application error distinct from `WORKTREE_FAILED`, because a repository
   mismatch never resolves by retrying — proven by a committed activity test.

### User Story 2 - The landing push names the repository that holds the branch (Priority: P1)

As the landing path, when a push is about to fail because the branch lives in a
different repository's ref store, I say so — instead of letting git say `src
refspec does not match any` and sending a day of diagnosis somewhere else.

**Independent Test**: with the cross-registered fixture from US1, `push_branch`
refuses before running `git push`, and the refusal names the worktree, its
owning clone, the target repo and the branch. The same assertion guards the
recovery-path merge.

**Acceptance Scenarios**:

1. **Given** a node worktree owned by repository A and a push requested against
   repository B, **When** `push_branch` runs, **Then** it refuses before
   invoking `git push`, and the message names the branch, the worktree path, A
   as the repository that actually holds the ref, and B as the one that was
   asked to push — proven by a committed test asserting no push subprocess ran.
2. **Given** the same mismatch, **When** the recovery path's merge with the
   landing branch runs, **Then** it refuses on the same terms rather than
   merging a remote-tracking ref that belongs to another repository's ref store
   — proven by a committed test.
3. **Given** a correctly owned worktree, **When** either function runs, **Then**
   behaviour is unchanged, the trunk guard still fires on its own terms, and the
   returned pushed sha is still the worktree's head — proven by the existing
   tests passing unmodified.
4. **Given** the refusal crossing the landing activity's boundary, **When**
   `open_landing_pr` catches it, **Then** it surfaces as a NON-retryable
   application error of a type distinct from the retryable `PUSH_FAILED` every
   other git failure keeps, so a deterministic repository mismatch is stated once
   instead of three times — and **Given** an ordinary git failure, **Then** it is
   still `PUSH_FAILED` and still retryable, proven by a committed test over both.

### User Story 3 - The landing base is the branch the repo declares (Priority: P1)

As the landing activity, I open the pull request against the branch the target
repository declares it lands on — not against whatever an operator happened to
have checked out when the worktree was prepared.

**Independent Test**: a clone whose checked-out branch differs from its declared
`landing_branch` opens a PR based on the declared branch; a clone with no usable
manifest opens against the fallback and says in its result which arm answered.

**Acceptance Scenarios**:

1. **Given** a target repo checked out on `some-operator-branch` whose
   `factory.yaml` declares `landing_branch: ergane-buildout`, **When** the
   landing opens the proposal, **Then** the base is `ergane-buildout` — proven
   by a committed test whose fixture makes the two branches DIFFER, because
   every fixture in the tree today sets checked-out, declared and `main` to one
   value and is therefore green against the broken base.
2. **Given** the same clone, **When** the base is resolved, **Then** the result
   records which arm answered — the manifest declaration or the checked-out-HEAD
   fallback — and a clone whose manifest is missing or malformed produces the
   fallback answer *labelled as a fallback*, never a silent reinstatement of the
   defect — proven by two committed tests.
3. **Given** both landing call sites — the first landing and the requeue after a
   rejection — **When** either opens a proposal, **Then** both resolve the base
   the same way through one code path, and a test asserts the requeue site is
   covered, because it is the site a busy epic runs most.
4. **Given** a node whose sidecar already records an operator branch as its
   `default_branch`, **When** its landing opens, **Then** the base is still the
   declared branch — proven by a committed test over a pre-populated sidecar,
   because a fix that only changed what future sidecars record would leave every
   already-prepared node landing on the wrong base.

### User Story 4 - The epic refuses at dispatch, before it spends (Priority: P1)

As an operator starting an epic — by hand or by schedule — I am told before
anything dispatches that a node's worktree belongs to another clone, or that
this repository's landing branch is being guessed rather than declared, with
every offending node named at once and one remedy block to run.

**Independent Test**: the shared preflight, driven offline over a graph and a
fixture factory root, returns one finding per cross-registered node and one
finding when the landing branch resolves by fallback; both dispatch surfaces
call the same function.

**Acceptance Scenarios**:

1. **Given** a graph whose nodes have worktrees on disk registered to another
   repository, **When** the pre-dispatch check runs, **Then** it returns a
   finding naming every offending node in one pass — not the first — each with
   its owning clone, and the factory root the check read, and dispatch does not
   proceed — proven by a committed test over a fixture root and two repos.
2. **Given** a graph whose nodes have no worktrees yet, or worktrees correctly
   owned, **When** the check runs, **Then** it returns nothing and costs one git
   call per existing directory — proven by a committed test asserting silence.
3. **Given** a target repo whose `factory.yaml` declares a landing branch,
   **When** the check runs, **Then** it reports nothing; **and Given** one whose
   manifest is missing or malformed so the branch resolves from HEAD, **Then**
   it returns a finding naming the repo, the branch that would be used and the
   fact that it was inferred — proven by two committed tests.
4. **Given** `ergane build start` and the roadmap's pre-dispatch activity,
   **When** each runs its preflight, **Then** both reach these checks through
   the one shared module the prompt-assembly and alias checks already share, and
   a test asserts the roadmap path returns the same findings for the same
   fixture — one implementation, two surfaces.

### User Story 5 - One agent execution, one session id (Priority: P1)

As the agent activity, when Temporal retries me with the identical payload, I
launch the runner under an identifier that execution has not used before — so
the one relaunch the retry policy exists to provide can actually start, and when
a launch is refused the operator is told what was refused.

**Independent Test**: the derivation is a pure function of (issued id, activity
attempt): attempt 1 returns the issued id unchanged, attempt 2 returns a
different valid UUID, and the same inputs always return the same output. A
stub-runner attempt asserts the argv and the archived transcript name track the
derived id together.

**Acceptance Scenarios**:

1. **Given** the session id the workflow issued, **When** the activity runs its
   first execution, **Then** the runner-visible id is that id unchanged — proven
   by a committed test, so every existing archive name, transcript path and
   status reading is untouched for the runs that never retry.
2. **Given** the identical payload on activity attempt 2, **When** the activity
   runs, **Then** the runner-visible id is a different, syntactically valid
   UUID, derived deterministically from the issued id and the attempt number —
   proven by a committed test asserting both distinctness and UUID validity,
   because the runner rejects a non-UUID before it rejects a duplicate.
3. **Given** an attempt whose derived id is in effect, **When** the invocation
   and the transcript archive are inspected, **Then** both name the same derived
   id — proven by a committed test over an injected runner seam, because the
   launch key and the archive key are the same string and must move together.
4. **Given** an attempt archive that already holds a stdout log from a previous
   execution, **When** the next execution opens its own, **Then** the earlier
   log is preserved under a name that says which execution wrote it, and the
   file the detector reads keeps its name and meaning — proven by a committed
   test, because today's truncating open destroys exactly the evidence that
   would name the cause.
5. **Given** a stdout log whose content is the runner's already-in-use refusal,
   **When** the attempt is classified, **Then** it is reported as a named
   launch refusal — the existing non-retryable launch-failure error type, quoting
   the runner's own line — rather than as a missing transcript, and the
   `Termination` enum gains no member — proven by a committed test that asserts
   the *behaviour*, never the 74-byte length, which is one CLI release from being
   wrong.
6. **Given** an ordinary non-zero exit whose stdout carries no such marker,
   **When** it is classified, **Then** it is still an ordinary agent error and
   still ordinary ladder input — proven by a committed test, because a classifier
   that raised on every non-zero exit would convert the whole ladder into launch
   failures and stop the node ever being graded.

### User Story 6 - A rescued landing is visible (Priority: P2)

As an operator who had to rescue a story by hand, I can make that rescue
attributable — and the tool tells me the exact line to use rather than expecting
me to remember an anchored grammar.

**Independent Test**: a commit whose body carries the rescue trailer is read as
a landing for that story with its own provenance kind; multi-line bodies parse;
`ergane spec landed` prints, for every story it found no landing for, the exact
title and trailer a rescue must carry.

**Acceptance Scenarios**:

1. **Given** a commit on the landing branch whose subject is prose and whose
   body carries the rescue trailer naming this epic, node and story, **When**
   landed facts are read, **Then** that story is landed at that commit with a
   provenance kind distinct from the queue-observed one — proven by a committed
   test over a fixture repository.
2. **Given** a history of commits with multi-line bodies, blank lines and
   subjects containing every delimiter the reader uses, **When** the log is
   read, **Then** every commit parses and no body is mistaken for a subject —
   proven by a committed test, because widening the read from subjects to
   bodies is a change to how the log is SPLIT, not a change to a regex.
3. **Given** one commit that matches a subject grammar and also carries the
   trailer, **When** it is read, **Then** the declared precedence decides which
   kind is recorded, and the rule is asserted rather than left to scan order.
4. **Given** a trailer naming an epic or a story the spec does not declare,
   **When** it is read, **Then** it is ignored exactly as an unrecognised
   subject is — a rescue grammar may not mark an unbuilt story landed.
5. **Given** a spec with stories the reader found no landing for, **When**
   `ergane spec landed` runs, **Then** for each such story it prints the exact
   PR title and the exact trailer line a rescue must carry, ready to paste —
   proven by a committed CLI test.

## Requirements

### Functional Requirements

- **FR-001**: One helper MUST answer "which repository owns this directory" by
  asking git, and MUST assert BOTH that the resolved top level equals the
  directory itself AND that its common git directory is the target repo's. A
  directory that is not a git worktree MUST be an answer, never an exception
  that escapes.
- **FR-002**: `ensure()` MUST apply that check on BOTH of its existing-directory
  branches — the recorded-sidecar branch and the adopt branch — and refuse a
  directory owned by another repository rather than returning or adopting it.
  The reuse rule is otherwise unchanged.
- **FR-003**: The refusal MUST name the worktree path, the owning clone, the
  dispatched target repo, and a copy-pasteable remedy issued **against the
  owning clone**; it MUST be raised as an exception type distinguishable from an
  ordinary worktree failure, so every activity boundary can discriminate it; and
  `prepare_worktree` MUST surface it as a non-retryable application error of a
  type distinct from `WORKTREE_FAILED`.
- **FR-004**: `push_branch` MUST assert ownership before invoking `git push` and
  MUST refuse naming the branch, the worktree, the repository that holds the ref
  and the repository that was asked to push. Where that refusal crosses the
  landing activity's boundary it MUST become a non-retryable application error of
  a type distinct from `PUSH_FAILED`, which every other git failure keeps and
  which stays retryable.
- **FR-005**: The recovery-path sync with the landing branch MUST take the same
  assertion, because it fetches in one repository and merges inside a directory
  that may belong to another.
- **FR-006**: The landing base MUST be resolved inside the landing activity from
  the target repository's declared landing branch, and the workflow MUST stop
  supplying it. A base already recorded in a node's sidecar MUST NOT decide it.
- **FR-007**: The resolution MUST state which arm answered — the manifest
  declaration or the checked-out-HEAD fallback — in the activity's result and in
  its log line, so a clone with a missing or malformed manifest cannot silently
  reinstate the defect. A base still supplied in the request MUST be ignored
  rather than honoured and rather than refused, and when it differs from the
  resolved base the log line MUST say that it was ignored and what it disagreed
  with — a refusal there would kill the ordinary pre-upgrade payload, which is
  the defect class this spec exists to remove.
- **FR-008**: Both landing call sites, the first landing and the requeue after a
  rejection, MUST reach the base through that one path.
- **FR-009**: A pre-dispatch check MUST report every node of a graph whose
  existing worktree is registered to a repository other than the graph's target
  repo — all of them in one pass, each with its owning clone, and naming the
  factory root the check read.
- **FR-010**: A pre-dispatch check MUST resolve the landing branch the way the
  landing will and MUST report a finding when it resolved by fallback rather
  than by declaration, naming the repository and the branch that would be used.
- **FR-011**: Both dispatch surfaces — `ergane build start` and the roadmap's
  pre-dispatch activity — MUST reach FR-009 and FR-010 through the one shared
  preflight module they already share for prompt assembly and aliases. No second
  implementation.
- **FR-012**: The runner-visible session id MUST be derived inside the agent
  activity from the workflow-issued id and the activity execution attempt: the
  first execution keeps the issued id, and any later execution gets a different,
  deterministically derived, syntactically valid UUID. The workflow's issuance
  sites MUST NOT change.
- **FR-013**: An execution MUST NOT destroy a previous execution's archived
  stdout log; the file the detector reads MUST keep its name and its meaning.
- **FR-014**: A launch the runner refused because the identifier was already in
  use MUST be classified and reported as a named launch refusal quoting the
  runner's own line, never as a missing transcript. It MUST use the existing
  non-retryable launch-failure error type, which the workflow already routes into
  a bounded launch-retry loop that spends no ladder attempt; it MUST NOT add a
  member to the `Termination` enum or widen the usage ledger's schema (plan R13).
- **FR-015**: The landed reader MUST accept a third grammar — a rescue trailer
  in the commit BODY naming epic, node and story — with its own provenance kind,
  declared precedence against the two existing grammars, and the same refusal to
  credit an epic or story the spec does not declare.
- **FR-016**: The log read MUST be widened to commit bodies using a record
  separator, and multi-line bodies MUST parse without any body line being read
  as a subject.
- **FR-017**: `ergane spec landed` MUST print, for every story it found no
  landing for, the exact PR title and the exact trailer line a rescue must carry.

## Work Graph

```yaml
US1:
  persona: opus-closer
  implements: [FR-001, FR-002, FR-003]
  depends_on: []
  depends_on_merged: []
US2:
  persona: opus-closer
  implements: [FR-004, FR-005]
  depends_on: []
  depends_on_merged: [US1, US3]
US3:
  persona: opus-closer
  implements: [FR-006, FR-007, FR-008]
  depends_on: []
  depends_on_merged: []
US4:
  persona: opus-closer
  implements: [FR-009, FR-010, FR-011]
  depends_on: []
  depends_on_merged: [US1]
  concurrent_with: [US2]
US5:
  persona: opus-closer
  implements: [FR-012, FR-013, FR-014]
  depends_on: []
  depends_on_merged: []
  concurrent_with: [US1]
US6:
  persona: opus-closer
  implements: [FR-015, FR-016, FR-017]
  depends_on: []
  depends_on_merged: []
```

Four of six stories start immediately: US1, US3, US5 and US6. US1 owns the
ownership predicate, so US4 (which reports it before dispatch) waits for US1 to
merge and for nothing else.

**US2 waits for both US1 and US3, and the second edge is the one worth
explaining.** US2 needs US1's predicate to exist in its base. It also edits
`open_landing_pr` in `factory/activities/merge_activities.py` — R14's
non-retryable `except` clause — and that is the same function US3 rewrites the
base resolution inside, including the docstring both would change. Racing them
puts two agents in one forty-line function, and the loser of that race is
rejected by the merge queue for the other's change; a speculative-merge ejection
is invisible to the poller, which is a worse failure than a wait. The wait is
cheap in the direction chosen: US3 is the fix that killed seven stories on
2026-08-24 and it starts at once, while US2 — the smallest story here — absorbs
the delay. The reverse ordering would have made the highest-value story the
third link of a three-deep chain.

Two waivers, both stated so the pair reads as considered rather than missed.
**US4 with US2**: both name `factory/workgraph/worktree.py`, but US2 edits two
functions in it and US4 only imports the predicate US1 landed — concurrent is
safe, and neither may edit the other's function. **US5 with US1**: both name
`factory/activities/agent_activities.py`, US1 at `prepare_worktree` and US5 at
`run_agent_attempt` and the result classifier, several hundred lines apart, with
US1's one new error-type constant the only line either adds near the top.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Paste the ownership check's output for three directories — one
  correctly owned, one owned by another clone, one that is not a worktree at all
  — beside the refusal text an operator would see, remedy command included.
- **SC-002**: Paste the refused push: the message the factory now prints, beside
  the bare `error: src refspec ... does not match any` it replaces.
- **SC-003**: Paste the resolved base for a clone whose checked-out branch and
  declared landing branch differ, showing the declared branch winning and the
  arm that answered named; and the same for a clone with no usable manifest,
  showing the fallback labelled.
- **SC-004**: Paste the pre-dispatch findings for a graph with two
  cross-registered nodes: both named in one report, each with its owning clone,
  the factory root stated, and one remedy block.
- **SC-005**: Paste the derived session ids for activity attempts 1 and 2 from
  one issued id, showing attempt 1 unchanged and attempt 2 a different valid
  UUID; and the preserved-log directory listing after a second execution.
- **SC-006**: Paste `ergane spec landed` for a spec with one rescued story and
  one unbuilt one: the rescued story reported landed with its own kind, and the
  unbuilt one printed with the exact title and trailer a rescue would need.

## Assumptions

- **git ≥ 2.31 on the worker host** for `--path-format=absolute` (this host runs
  2.43.0, verified by running it). If the check ever runs inside the engine image
  from specs 088/104, that image's git version becomes a real precondition —
  pin it or use the porcelain form, which has no version floor.
- **Both dispatch surfaces read the same factory root as the worker.** The
  roadmap's pre-dispatch activity runs on the worker host and reads its root;
  `ergane build start` runs in the operator's shell. They agree on this host
  because `scripts/ergane-env.sh` sets one value, which is exactly why FR-009
  requires the finding to NAME the root it read rather than assume it. Where they
  do not agree — a split-host install — US4's CLI arm is **advisory only**: it
  reads a disk the epic will not build on, so it can be silent about a graph that
  will strand. That is not repaired here and must not be repaired by having the
  CLI reach the worker's disk; US1's `ensure()` refusal runs on the worker beside
  the directory it judges and is the enforcement on such a host (plan R5).
- **The whole of US1, US2, US3 and US4 reproduces offline** — two `git init`
  repositories, one shared directory, one local bare origin. No network, no
  docker socket, no forge. Only US5's real-runner reproduction needs hardware,
  and it is on the operator's list in `plan.md`, gating nothing.
- **A rescue trailer is written in the pull request body and carried into the
  squash commit body by the forge.** Like the subject, it is set at merge time
  and immutable afterwards. PR #297 is not recoverable by any grammar, and one
  story of spec 088 stays permanently invisible to `--delta`.
