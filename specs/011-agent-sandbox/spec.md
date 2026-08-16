---
state: landed
depends_on_landed: [043-runtime-root-integrity]
# Attested landed 2026-08-15. US1 ed8f24c5a3b1 (#74), US2 8b768e606222 (#75),
# US3 678291be5117 (#76), US4 0daa9761ec6d (#77), US5 48daae1a80c7 (#78) — all
# observed on ergane-buildout. Four operator follow-ups landed after the epic
# closed, each fixing something the five green stories could not see: the
# sandbox was never applied to a real dispatch (#79), the boundary made the
# worktree read-only (#80), it could not run the repo's toolchain (#81), and it
# could not run the repo's own suite (#82). That gap between "epic complete"
# and "mechanism works in production" is the reason 011 is worth re-reading
# before trusting any future isolation claim.
# specs_root: specs
# target_repo: /home/admin/code/ergane (the old ergane-011-target scratch repo
#   never existed on this host; the boundary code lands in factory/, so the
#   factory is the target, as with every self-build epic)
# Scaffolded by `ergane findings promote` from two findings that are one subject:
#   hardening/agent-sandbox (critical, audit-2026-08-07 F1, "#1 blast radius")
#   hardening/agent-edits-the-operator-checkout-not-its-worktree (critical,
#     operator-2026-08-11 — the live incident that proved F1)
# Refined against the tree at 5f0042e on 2026-08-11.
# Re-refined 2026-08-14 against 0bf0c93: sandbox backend decided (bwrap — see
#   plan.md "Decided at refinement"), and the oversized US2 split into
#   US2/US3/US4 with the old US3 renumbered US5. Nothing had landed, so the
#   renumbering was free.
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

### And then, three days later, the destructive form

2026-08-14, epic `033-ergane-install`, node `us2`, attempt 1. From the attempt's
own transcript, verbatim:

```bash
cd /home/admin/code/ergane && rm -rf .factory && uv run pytest -q \
  tests/test_store_isolation.py::test_leaking_writers_are_contained
```

The transcript's `cwd` field was
`/home/admin/code/ergane/.factory/worktrees/033-ergane-install/us2`. **The agent
was correctly inside its worktree and deliberately left it.** This is the second
data point and it is worse than the first in every dimension that matters:

- It was **not confusion about paths.** The 2026-08-11 census can be read as an
  agent that never noticed which tree it was in. This one typed `cd` to an
  absolute operator path on purpose, to clean a directory it believed was its own
  scratch state.
- It **destroyed rather than contaminated.** `verification.db` 892,928 bytes → 0.
  The findings ledger, with 77 findings and every recurrence count → empty. The
  usage ledger → empty. Every attempt transcript → gone.
- It **deleted the running nodes**, including itself. Node worktrees live at
  `.factory/worktrees/<epic>/<node>` — *inside the directory it removed*. Its own
  worktree vanished mid-attempt, so the node died with no escalation, `us3` was
  killed as a dependent, and the epic ended with one story of three. A second
  epic, `034-ergane-init`, had a gate running at that moment and watched its
  files disappear: hundreds of `FileNotFoundError`s that had nothing to do with
  the code under test.
- It was **irreversible on this host.** No local copy, and no process still held
  the deleted inodes. Recovery came from an off-host nightly `restic` snapshot
  taken 8h44m earlier, which is luck the design did not earn.

The irony is exact and worth keeping in the spec: the agent was setting up
`test_leaking_writers_are_contained`, the test that exists to prove writers do
not reach the live store.

**And it was not an isolated impulse.** Reconciling the operator's checkout
afterwards turned up that agent's *entire story output* sitting there, written in
the ten minutes before the deletion: `factory/cli/install.py` (11:42:15),
`factory/cli/nouns/install.py` (11:40:50), `factory/controlplane/probes.py`
(11:46:58), `tests/test_controlplane_probes.py` (11:45:51). Its predecessor
`033/us1` had done the same — `factory/controlplane/config.py` and
`tests/test_controlplane_config.py` were written into the operator's tree *as
well as* the worktree they correctly landed from.

That changes the reading of the `rm -rf`. An agent that has spent ten minutes
building its story inside `/home/admin/code/ergane` is not confused when it
treats that directory as its workspace and `.factory` as its scratch state — it
is acting consistently on a model the system did nothing to contradict. **The
escape and the destruction are one defect at two severities, not two defects.**
An agent working in the wrong tree will, sooner or later, clean the wrong tree.

It also means the operator's checkout silently accumulates agent output that
nothing detects and nothing prevents — visible only when some later git
operation happens to collide with it. In this case the only surviving copy of a
killed node's work was sitting untracked in the operator's tree.

Two earlier events complete the picture. On 2026-08-12 an agent ran
`pkill -f "python -"` inside its worktree to clean up stray test servers; the
pattern matched the systemd unit's own command line and **SIGTERMed the worker
that was running the agent**. Temporal survived only because it is a Go binary.
That is filed as `hardening/agent-pkill-kills-the-live-worker`, and the mitigation
shipped since — spelling the unit's `ExecStart` so it carries no `python -`
substring — is a dodge of one string, not a boundary.

Taken together: an agent can currently read anything the operator can read, write
anything the operator can write, delete the factory's own state and running
nodes, and signal any process on the host including the worker executing it.

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
  the other. On 2026-08-14 this stopped being hypothetical: with two epics
  running, one epic's agent destroyed the other's in-flight attempt.
- **The factory can lose its own memory.** The evidence store, the findings
  ledger and the usage ledger all live under the runtime root, which is a
  perfectly ordinary directory to an agent holding an absolute path. The findings
  ledger is the thing that makes "this defect has recurred" a countable fact
  rather than a recollection — Principle-promotion depends on it — and it was
  reduced to an empty schema by one command.
- **An agent can end its own attempt, and its neighbours'.** Because node
  worktrees live *inside* the runtime root, "clean the state directory" and
  "destroy every running node" are the same command. No escalation fires, because
  the machinery that would raise one is what got deleted.

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
5. **Given** an attempt whose agent removes or truncates a file under the
   factory's runtime root that belongs to another node or to the engine — an
   evidence store, a ledger, a sibling's worktree — **When** the attempt tears
   down, **Then** a critical finding names those paths. A tracked-file diff of
   the target repository cannot see this: the runtime root is gitignored, so the
   2026-08-14 destruction would have produced **silence** from a detector that
   only watched tracked files.
6. **Given** an attempt whose agent deletes the runtime root outright, **When**
   the detector runs at teardown, **Then** it still reports, rather than failing
   because the state it meant to compare against is the state that was destroyed.
   A detector that dies with the thing it is watching reports nothing on exactly
   the worst case.

### User Story 2 - The launch goes behind a seam, and an absent backend is a refusal (Priority: P1)

The agent launch moves behind a substitutable seam, the way gate execution
already sits behind `GateExecutor`. The seam resolves the sandbox backend named
by the manifest's `runtime:` key — on this floor, `bwrap` — and a backend that
cannot be provided is a refusal naming the backend and the platform, never a
silent fallback to the host. Tests drive the seam with a fake, so the suite
never needs the backend present.

**Why this priority**: The seam is what makes every containment claim after it
testable, and it is the cross-platform story: Linux hosts (and Windows hosts,
which run Ergane inside WSL2's real Linux kernel) use bwrap; a macOS backend
(Seatbelt) is a future second implementation behind this same seam, not a
change to it.

**Independent Test**: Dispatch through the seam with a fake backend
substituted; assert the fake received exactly what today's direct launch
builds, and that an unavailable backend refuses by name.

**Acceptance Scenarios**:

1. **Given** the launch behind the seam, **When** an attempt is dispatched with
   a fake backend substituted, **Then** the argv, the prompt, the standards
   path and the persona routing the fake receives are identical to what the
   direct launch builds today.
2. **Given** a manifest naming `bwrap` on a host where the backend is absent,
   **When** an attempt is dispatched, **Then** dispatch refuses with a message
   naming the backend and the platform, and no agent process runs on the host.
3. **Given** a manifest whose `runtime:` still holds a container image
   reference — the pre-this-spec value — **When** the manifest is validated,
   **Then** validation refuses and names the supported backend, and this
   repository's own `factory.yaml` is updated to `runtime: bwrap` in the same
   diff.
4. **Given** a host with no sandbox backend installed, **When** the full suite
   runs, **Then** it is green: seam-driven tests pass against the fake, and
   live-boundary tests guard on backend *detection* — a skip standing in for a
   seam-provable claim is not compliance.

### User Story 3 - The agent's filesystem is its worktree, not the host (Priority: P1)

The bwrap backend mounts the node worktree writable, the git plumbing that
worktree requires, a writable temp, a factory-owned home and the read-only
toolchain — and nothing else. The target repository's working tree, the
factory's runtime root and the operator's home are absent from the agent's
filesystem entirely. A write outside the mount set fails at the OS, and the
agent sees the error on its own tool call.

**Why this priority**: It is the fix. Everything else here is scaffolding
around it.

**Independent Test**: Run an attempt whose scripted agent attempts to write an
absolute path into the target repo's working tree; assert the write fails and
the operator's tree is unchanged. Then assert the same attempt can still
commit, which is what proves the git plumbing survived.

**Evidence rule for every scenario below**: the judge is given the diff and
these criteria — never a terminal, never the base tree (constitution VIII).
Live-boundary claims are met by tool output pasted verbatim into a comment
block in the test file.

**Acceptance Scenarios**:

1. **Given** an agent that writes to an absolute path in the target repository's
   working tree, **When** the write executes, **Then** it fails, the operator's
   tree is unchanged, and US1's detector reports nothing because nothing happened.
2. **Given** an agent inside the boundary, **When** it runs `git add`, `git
   commit` and `git diff` in its worktree, **Then** all succeed — the worktree's
   `.git` indirection into the parent repository is satisfied.
3. **Given** an agent inside the boundary, **When** it attempts to read the
   operator's `~/.config/gh` or any path outside the mount set, **Then** the
   read fails.
4. **Given** an agent inside the boundary, **When** it runs
   `rm -rf /home/<operator>/code/<repo>/.factory` — the literal 2026-08-14
   command — **Then** it fails, and afterwards the evidence store, both ledgers,
   every sibling node's worktree and its own worktree are all intact. The mount
   set exposes the node's **own** worktree, never the runtime root that contains
   it.

### User Story 4 - Deadlines, transcripts and signals survive the boundary (Priority: P1)

The attempt lifecycle keeps every property it has today with the agent inside
the boundary: the deadline kills the agent and everything it spawned, the
stdout log and session transcript archive to the same paths with the same
contents, and nothing the agent signals reaches a process outside the boundary.

**Why this priority**: A boundary that leaks processes past their deadline or
loses transcripts trades one incident class for two new ones. These are the
properties plan traps 2 and 3 exist for, and the 2026-08-12 `pkill` incident
is the third.

**Independent Test**: A deliberately hanging scripted agent is killed at
deadline with no surviving process; a completing one archives its transcript
byte-identically; a `pkill`-ing one leaves the worker alive.

**Evidence rule for every scenario below**: as US3 — live claims land as
verbatim pasted output committed in the diff.

**Acceptance Scenarios**:

1. **Given** an agent inside the boundary, **When** its attempt exceeds the
   persona's timeout, **Then** the attempt is terminated and classified `timeout`
   exactly as it is today, and no process from it survives.
2. **Given** an attempt inside the boundary that completes, **When** it tears
   down, **Then** its stdout log and session transcript are archived to the same
   paths, with the same contents, as an attempt produces today.
3. **Given** an agent inside the boundary, **When** it runs `pkill -f "python -"`
   or otherwise signals by pattern, **Then** no process outside the boundary
   receives a signal, and the worker executing the attempt is still running
   afterwards. Assert on the worker's liveness, not on the exit code of `pkill`.
4. **Given** the boundary deliberately disabled through the seam's explicit
   host implementation, **When** the scripted agents from US3-S4 and US4-S3 run
   again, **Then** the damage reproduces — the control that proves the boundary
   is what does the work (SC-009).

### User Story 5 - Verification does not reopen what the agent boundary closed (Priority: P2)

Gates run inside the same boundary as the agent that produced the diff. A gate
command is repo-authored text executed as `bash -c`; running it on the host after
containing the agent would leave the escape open one step later in the ladder.

**Why this priority**: It closes the leak, but the leak requires an agent to have
already written a hostile or confused gate command, which is a narrower path than
the one already observed. It is the right final story and the wrong first one.

**Independent Test**: Point a fixture repo's gate command at a path outside the
worktree; assert it fails inside the boundary where it would have succeeded on
the host.

**Evidence rule**: as US3 — live claims land as verbatim pasted output
committed in the diff.

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
- **FR-012**: The detector MUST also cover the factory's own runtime root — the
  evidence store, the ledgers, and every node worktree other than the attempt's
  own — and MUST file a critical finding when any of them is removed, truncated
  or replaced during an attempt. The runtime root is gitignored, so FR-001's
  tracked-file comparison is structurally blind to it.
- **FR-013**: The detector MUST still report when the state it compares against
  has itself been destroyed; it MUST NOT depend on reading anything under the
  runtime root at teardown to know that the runtime root is gone.
- **FR-003**: The agent process MUST execute inside the sandbox backend named by
  the resolved `factory.yaml`'s `runtime:` key. The key's value domain becomes a
  backend name — `bwrap` — no longer a container image reference; the image form
  is refused at validation.
- **FR-004**: The agent's filesystem view MUST include its node worktree as
  writable, and MUST NOT include the target repository's working tree.
- **FR-014**: The agent's filesystem view MUST NOT include the factory's runtime
  root, any evidence store or ledger, any other node's worktree, or the parent
  directory of its own worktree. Mounting the runtime root and relying on the
  agent to stay in its subdirectory reproduces exactly the containment this spec
  exists to replace — the node worktree is a *leaf* of the runtime root, and only
  that leaf may be mounted.
- **FR-015**: The agent MUST NOT be able to signal, terminate or otherwise affect
  any process outside its own boundary, including the worker that dispatched it.
- **FR-005**: The agent's filesystem view MUST include whatever git metadata the
  worktree requires to commit, diff and branch — the worktree's `gitdir` and the
  shared object store — without exposing the working tree those live beside.
- **FR-006**: The attempt deadline MUST remain enforceable: when it expires, the
  agent and every process it spawned MUST be terminated, and the attempt
  classified `timeout` as it is today.
- **FR-007**: The stdout log and session transcript MUST be archived to the same
  paths with the same contents as an attempt produces today.
- **FR-008**: A sandbox backend that cannot be provided MUST be a refusal naming
  the backend and the platform, never a silent fallback to running on the host.
- **FR-009**: Gate execution MUST run inside the same boundary as the agent, and
  gate outcomes MUST be unchanged from host execution for gates that stay inside
  the worktree.
- **FR-010**: The test suite MUST NOT require the sandbox backend to be present;
  the boundary MUST sit behind a seam a test can substitute, and tests that do
  exercise the live backend MUST guard on detecting it rather than on markers.
- **FR-011**: This feature MUST NOT change what an agent is asked to do: the
  prompt, the standards path, the gates declared by the target repo, the judge
  and every routing decision are untouched.

## Out of scope — named so an implementer does not build them

- **Network isolation and egress policy.** The boundary this spec builds is a
  filesystem one. An agent still reaches the proxy, and must. Restricting egress
  is a separate feature with its own failure modes. Concretely for the backend:
  do not pass `--unshare-net`.
- **A macOS backend.** bwrap is built on Linux kernel namespaces and has no Mac
  form; the macOS equivalent is Seatbelt (`sandbox-exec`), reached most credibly
  through Anthropic's `sandbox-runtime`, and it is a *second implementation
  behind US2's seam* for a future spec with a Mac host to prove it on — not
  this one. Windows needs no backend of its own: Ergane on Windows runs inside
  WSL2, a real Linux kernel where bwrap works unchanged, and what WSL2 needs is
  install documentation, not code.
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
- **SC-005**: The full suite passes on a host with no sandbox backend installed:
  seam-driven tests run against the fake, live-boundary tests guard by
  detection. A skip standing in for a seam-provable claim is not compliance.
- **SC-006**: The full suite stays green and no dependency outside the approved
  roster is added. bwrap is a host binary, not a Python dependency; the roster
  does not change.
- **SC-007**: The literal 2026-08-14 command —
  `cd <target-repo> && rm -rf .factory` — executed by a scripted agent inside the
  boundary, leaves the evidence store, both ledgers and every node worktree
  byte-identical. Measured by comparing file sizes and row counts before and
  after, pasted into the diff.
- **SC-008**: A scripted agent running `pkill -f "python -"` inside the boundary
  leaves the worker process alive, asserted by the worker's own liveness rather
  than by the signal command's exit status.
- **SC-009**: With the boundary deliberately disabled, the same two scripted
  agents reproduce the damage, and with it enabled they do not. A containment
  claim proven only in the passing direction has not been proven — this is the
  control, and it is what distinguishes this from the guard that was already
  believed to exist.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-012, FR-013]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-008, FR-010, FR-011]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-003, FR-004, FR-005, FR-014]
US4:
  depends_on: []
  depends_on_merged: [US3]
  implements: [FR-006, FR-007, FR-015]
US5:
  depends_on: []
  depends_on_merged: [US4]
  implements: [FR-009]
```
