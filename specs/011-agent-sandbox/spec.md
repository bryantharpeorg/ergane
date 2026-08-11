---
state: draft
# specs_root: specs
# target_repo: /home/admin/code/ergane-011-target
# Scaffolded by `ergane findings promote` from two findings that are one subject:
#   hardening/agent-sandbox (critical, audit-2026-08-07 F1, "#1 blast radius")
#   hardening/agent-edits-the-operator-checkout-not-its-worktree (critical,
#     operator-2026-08-11 — the live incident that proved F1)
# Refined against the tree at 5f0042e on 2026-08-11.
#
# Numbered 011 because F1 is an audit-triage finding and 011-014 are reserved
# for those. 010 took the B-series; this takes the first F.
---

# Feature Specification: The worktree is where the agent starts, not where it is kept

## The defect in one sentence

A dispatched agent's containment is a single `cwd=` argument to
`create_subprocess_exec`, so an absolute path walks straight out of the worktree
into the operator's live checkout, and every write that does so succeeds
silently.

## What was actually observed

2026-08-11, epic `010-interpreter-bugfixes`, node `us2`, attempt 1. Tool-call
census from the attempt transcript:

| target | Read | Edit |
| --- | --- | --- |
| `/home/admin/code/ergane` (operator's checkout) | 58 | 4 |
| `.factory/worktrees/010-interpreter-bugfixes/us2` (its own) | 2 | 0 |

The four edits left `factory/workgraph/workflow.py` and
`tests/test_interpreter.py` modified and uncommitted in the operator's tree. The
agent also read `.specify/memory/constitution.md`, `factory.yaml`,
`pyproject.toml`, `docs/architecture.md` and `docs/decisions.md`: read access to
the operator's tree is total.

**Every one of those writes returned success.** That is the property this spec
exists to destroy. The gate then ran against the worktree — which held the tests
and none of the implementation — so the attempt failed on its own fail-first
tests, and from inside the agent the honest reading was "my tests fail", not "I
am editing the wrong repository".

## Why this is critical rather than untidy

- **Verification goes blind.** Gates, judge and diff all read the worktree. Work
  done outside it can neither pass nor fail; it is not in the thing being examined.
- **Live code gets contaminated.** The operator's checkout is what the worker
  imports. Unreviewed interpreter code sat in it for two hours. The worker had
  imported at 22:39:20 and the contamination is stamped 01:31:08, so the running
  epic was clean by timing, not by design.
- **The concurrency guarantee stops holding.** Worktree isolation is one of the
  four layers that let nodes run in parallel. At `--max-concurrent-nodes > 1`
  two agents can edit the same operator file simultaneously, neither aware of
  the other.

## What this is not

This is **not** `hardening/agents-inherit-operator-home`, and spec 018 does not
overlap it. 018 changes what an agent *loads* — the inherited `HOME`, and with it
`~/.claude.json`, the operator's MCP servers and global instructions. This spec
changes what an agent can *reach and mutate*. Give the agent a pristine
factory-owned home and it still opens `/home/admin/code/ergane/...` successfully,
because an absolute path has nothing to do with `HOME`. 018 would have prevented
zero of the four edits.

### User Story 1 - An attempt that writes outside its worktree is caught and named (Priority: P1)

Before the boundary exists, the factory can at least stop being blind to the
breach. An attempt records the state of the target repository's working tree when
it starts and again when it tears down; any tracked file that changed there
during the attempt is reported as a critical finding naming the paths, and the
operator is told.

**Why this priority**: It is the cheapest thing here, it is independently
valuable while the boundary is being built, and it is what makes US2 provable —
a containment claim with no detector behind it is an assertion. It also survives
US2 as the standing regression guard.

**Independent Test**: Run an attempt whose scripted agent writes one tracked file
in the target repo; assert a finding naming that path. Run one that stays inside
its worktree; assert silence.

**Acceptance Scenarios**:

1. **Given** an attempt whose agent modifies a tracked file in the target
   repository outside its worktree, **When** the attempt tears down, **Then** a
   critical finding is filed naming the changed paths, the epic, the node and the
   attempt.
2. **Given** an attempt whose agent writes only inside its own worktree, **When**
   the attempt tears down, **Then** no finding is filed.
3. **Given** an attempt during which the operator themself edits the target
   repository, **When** the attempt tears down, **Then** the finding still reports
   the change — the detector reports what happened, and does not try to attribute
   intent.
4. **Given** the detector runs, **When** it inspects the target repository,
   **Then** it only reads: it never stashes, checks out, cleans or otherwise
   mutates the operator's tree.

### User Story 2 - The agent runs inside the runtime the manifest already declares (Priority: P1)

The agent process runs inside the image named by `factory.yaml`'s `runtime:` key,
with its node worktree and the git plumbing that worktree requires bind-mounted
writable, and the target repository's working tree absent from its filesystem
entirely. A write outside the worktree fails at the OS, and the agent sees the
error on its own tool call.

**Why this priority**: It is the fix. Everything else here is scaffolding around it.

**Independent Test**: Run an attempt whose scripted agent attempts to write an
absolute path into the target repo's working tree; assert the write fails and the
operator's tree is unchanged. Then assert the same attempt can still commit,
which is what proves the git plumbing survived.

**Acceptance Scenarios**:

1. **Given** an agent that writes to an absolute path in the target repository's
   working tree, **When** the write executes, **Then** it fails, the operator's
   tree is unchanged, and US1's detector reports nothing because nothing happened.
2. **Given** an agent inside the boundary, **When** it runs `git add`, `git
   commit` and `git diff` in its worktree, **Then** all succeed — the worktree's
   `.git` indirection into the parent repository is satisfied.
3. **Given** an agent inside the boundary, **When** its attempt exceeds the
   persona's timeout, **Then** the attempt is terminated and classified `timeout`
   exactly as it is today, and no process from it survives.
4. **Given** an attempt inside the boundary that completes, **When** it tears
   down, **Then** its stdout log and session transcript are archived to the same
   paths, with the same contents, as an attempt produces today.
5. **Given** an agent inside the boundary, **When** it attempts to read the
   operator's `~/.config/gh` or any path outside what was mounted, **Then** the
   read fails.
6. **Given** a manifest whose `runtime:` names an image, **When** an attempt is
   dispatched, **Then** the image actually used is that one, and a mismatch is a
   refusal rather than a silent host fallback.

### User Story 3 - Verification does not reopen what the agent boundary closed (Priority: P2)

Gates run inside the same boundary as the agent that produced the diff. A gate
command is repo-authored text executed as `bash -c`; running it on the host after
containing the agent would leave the escape open one step later in the ladder.

**Why this priority**: It closes the leak, but the leak requires an agent to have
already written a hostile or confused gate command, which is a narrower path than
the one already observed. It is the right third story and the wrong first one.

**Independent Test**: Point a fixture repo's gate command at a path outside the
worktree; assert it fails inside the boundary where it would have succeeded on
the host.

**Acceptance Scenarios**:

1. **Given** a gate command that reads or writes outside the worktree, **When**
   the gate runs, **Then** it fails rather than succeeding against the host.
2. **Given** the existing gate suite, **When** gates run inside the boundary,
   **Then** their outcomes — PASS, FAIL, TIMEOUT and the captured output tail —
   are unchanged from running them on the host.
3. **Given** a gate that hangs, **When** its deadline expires, **Then** it is
   killed together with every process it spawned, as it is today.

## Functional Requirements

- **FR-001**: An attempt MUST capture the target repository's tracked-file state
  at start and at teardown, and MUST file a critical finding when they differ.
- **FR-002**: The detector MUST be read-only with respect to the target
  repository; it MUST NOT stash, clean, check out or otherwise mutate it.
- **FR-003**: The agent process MUST execute inside the runtime image named by
  the resolved `factory.yaml`'s `runtime:` key.
- **FR-004**: The agent's filesystem view MUST include its node worktree as
  writable, and MUST NOT include the target repository's working tree.
- **FR-005**: The agent's filesystem view MUST include whatever git metadata the
  worktree requires to commit, diff and branch — the worktree's `gitdir` and the
  shared object store — without exposing the working tree those live beside.
- **FR-006**: The attempt deadline MUST remain enforceable: when it expires, the
  agent and every process it spawned MUST be terminated, and the attempt
  classified `timeout` as it is today.
- **FR-007**: The stdout log and session transcript MUST be archived to the same
  paths with the same contents as an attempt produces today.
- **FR-008**: A runtime that cannot be provided MUST be a refusal naming the
  image, never a silent fallback to running on the host.
- **FR-009**: Gate execution MUST run inside the same boundary as the agent, and
  gate outcomes MUST be unchanged from host execution for gates that stay inside
  the worktree.
- **FR-010**: The test suite MUST NOT require a container runtime to be present;
  the boundary MUST sit behind a seam a test can substitute.
- **FR-011**: This feature MUST NOT change what an agent is asked to do: the
  prompt, the standards path, the gates declared by the target repo, the judge
  and every routing decision are untouched.

## Out of scope — named so an implementer does not build them

- **Network isolation and egress policy.** The boundary this spec builds is a
  filesystem one. An agent still reaches the proxy, and must. Restricting egress
  is a separate feature with its own failure modes.
- **Containing the worker or the workflow.** Only the agent (US2) and the gates
  (US3) move. The Temporal worker, the activities and the interpreter stay on the
  host; containing them is a deployment change, not this.
- **Replacing 018.** If US2 lands first it will incidentally deny the agent the
  operator's `HOME`, but 018 states that property, tests it and keeps it stated.
  Neither spec may be quietly deleted in favour of the other.
- **Retroactive review of what past agents read.** The read surface was total
  until this lands; enumerating what that touched is an audit, not a feature.

## Success Criteria

- **SC-001**: With a scripted agent that writes one tracked file in the target
  repo outside its worktree, the run files a critical finding naming that path.
- **SC-002**: With the boundary in place, the same scripted agent's write fails,
  and the operator's `git status` is byte-identical before and after the attempt.
- **SC-003**: An attempt inside the boundary commits, is judged and lands through
  the merge queue with no change to its evidence trail.
- **SC-004**: A timeout inside the boundary leaves no surviving process.
- **SC-005**: The full suite passes on a host with no container runtime installed.
- **SC-006**: The full suite stays green and no dependency outside the approved
  roster is added.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-003, FR-004, FR-005, FR-006, FR-007, FR-008, FR-010, FR-011]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-009]
```
