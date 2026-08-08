---
state: draft
# Drafted 2026-08-08 from `hardening/agents-inherit-operator-home` (critical,
# open, ledger source `operator-2026-08-08`), which was proved by process
# inspection during 016's us4 at 2:05 AM CT: the agent's pid had sibling
# processes in the same worktree, one of them an MCP server the factory never
# asked for.
#
# Numbered 018: 010–014 stay reserved for audit-triage epics, 015 is the
# doctor, 016 the delta, 017 the peer channel. This finding's source is an
# operator observation rather than an accepted audit id, so it does not spend
# one of the reserved numbers — see the Assumptions on its relationship to the
# audit's F1 (`hardening/agent-sandbox`), which stays a separate, larger epic.
#
# Scope is deliberately the HOME half and nothing more. Read the Assumptions
# before widening it: this spec changes what an agent *loads*, not what an
# agent *can reach*, and a plan or a test that claims otherwise is wrong.
---

# Feature Specification: Agent Home Isolation

**Feature Branch**: `018-agent-home-isolation`

**Created**: 2026-08-08

**Status**: Drafted the same day the finding was widened. The adapter's child
environment is an allowlist built by construction rather than by filtering
(`attempt_env`, `factory/workgraph/adapter.py`), and that design is the reason
`LITELLM_MASTER_KEY` and `TELEGRAM_BOT_TOKEN` are absent from every agent — they
are never written, so they cannot leak. `HOME` is on that allowlist, and it
carries in more than the credentials the allowlist keeps out.

**Input**: `PASSTHROUGH_ENV` (`factory/workgraph/adapter.py:75`) passes the
worker's `HOME` to every attempt, so every dispatched agent runs as the operator
does. On the current worker host that means the agent loads a 128 KB
`~/.claude.json` carrying `oauthAccount`, `userID`, `machineID`, a `projects`
map spanning 79 unrelated project directories, and a user-scope `mcpServers`
block; it reads the operator's global `~/.claude/CLAUDE.md` as instructions; it
writes its own state into the operator's `~/.claude/`; and it does all of this
under `--dangerously-skip-permissions`, so nothing prompts.

Three distinct costs, in descending order of consequence. **Authority**: the
agent inherits the operator's connected accounts and the tools they carry, so a
node dispatched to write Python has live tools it was never scoped for.
**Instruction**: the operator's global `CLAUDE.md` is a second standards channel
reaching implementers, which D-025 chose the committed `standards` path
specifically to avoid. **Cost**: the inherited tool schemas ride in every
request of every attempt, on a factory whose whole spend discipline is
per-node attribution.

None of it is a regression and none of it is exotic. It has been true of every
epic the factory has ever run, and it is true because the allowlist admits one
name whose value is a doorway.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The agent's home belongs to the factory (Priority: P1)

As the factory operator, every attempt runs with a `HOME` the factory created
under its own state root, so that an agent starts from a home whose entire
contents the factory put there — and the operator's home is not one of the
inputs to a dispatch.

The home is keyed per node, exactly as the worktree and the pid file already
are (`worktree_path` and `pid_file`, both `(factory_root, epic_id, node_id)`).
Per node rather than per attempt because a node's retries share the tree they
are retrying in and should share the state beside it; per node rather than one
factory-wide home because `--max-concurrent-nodes 2` is real — 016 dispatched
us3 and us4 together — and two live agents writing one configuration file is a
race the factory would be introducing on purpose.

`HOME` is **replaced, never removed**. The name must still be present and must
still point somewhere real: the adapter's own `_archive_session` resolves the
session transcript from *the child's* `HOME` and returns early when the name is
absent, so an allowlist that simply dropped it would stop archiving evidence and
the loss would be indistinguishable from an agent that wrote no transcript.

**Why this priority**: Every other story in this spec is a property of the home
this one creates.

**Independent Test**: Build the child environment for a context whose worker
environment carries a populated `HOME`, and assert the value the child receives
is the factory's per-node path and not the worker's; assert two nodes of one
epic receive different paths; assert the directory exists before launch.

**Acceptance Scenarios**:

1. **Given** a worker process whose own `HOME` is the operator's, **When** the
   child environment for an attempt is built, **Then** `HOME` is the factory's
   per-node path and no value in the built environment is a path under the
   operator's home.
2. **Given** two nodes of the same epic dispatched concurrently, **When** their
   environments are built, **Then** their homes are different directories.
3. **Given** the same node retried, **When** a second attempt's environment is
   built, **Then** it is the same home the first attempt used — retries share
   state as they already share the worktree.
4. **Given** an attempt about to launch, **When** the adapter runs, **Then** the
   home directory exists — an agent MUST NOT be launched into a `HOME` that is
   not there.
5. **Given** the built environment, **When** it is inspected, **Then** `HOME` is
   present — the name is replaced, not omitted, because the archive step reads
   it.

---

### User Story 2 - The agent starts, works and is archived on that home (Priority: P1)

As the factory operator, an attempt on a factory-owned home starts without
prompting, commits its own work, and produces the same evidence it produces
today, so that isolating the home costs the factory nothing it currently has.

The agent CLI needs less than this story originally assumed: probed on a bare
home it started and answered without prompting, and created its own
configuration and state directories. So the factory's obligation is mostly
negative — the home must exist and be writable, and its contents must never be
copied from, read from, or seeded against the operator's configuration, because
copying would re-import precisely what this spec removes, `oauthAccount`
included. If some later CLI version does need a fact asserted, it is a fact the
factory asserts about a directory it owns, not a fact it borrows.

Git identity is the exception, and it is not hypothetical: the same probe's
`git commit` inside the worktree failed with `Author identity unknown`. Salvage
is unaffected — it carries its own (`_SALVAGE_IDENTITY`,
`factory/workgraph/worktree.py`), so constitution VI holds and the worktree
tests have run with an empty `HOME` since they were written. The agent's *own*
commits are what break: they run in the child environment, which carries no
identity, and a fresh home has no `~/.gitconfig` to fall back on. Such an agent
still has its work salvaged, so nothing is lost — but it loses the incremental
history the prompt asks it to keep, and it spends its attempt finding out why.

**Why this priority**: US1 without this is an isolated home that may not run an
agent. The two together are the feature.

**Independent Test**: A real attempt against the stub agent on a factory-owned
home produces a transcript directory containing both artifacts; a git commit
made from inside the worktree under the child environment succeeds and carries
the factory identity.

**Acceptance Scenarios**:

1. **Given** a factory-owned home with no operator configuration anywhere in it,
   **When** an attempt runs, **Then** the agent starts and completes without an
   interactive prompt and without a configuration error.
2. **Given** a completed attempt, **When** its transcript directory is read,
   **Then** it holds `stdout.log` and the session transcript, the same two
   artifacts as before this change — the archive resolves from the child's home
   and must be proved to compose, not assumed to.
3. **Given** an agent working in its worktree, **When** it commits its own work,
   **Then** the commit succeeds and is attributed to the factory's identity, the
   same name and address salvage uses — never the operator's.
4. **Given** the seeded home, **When** its contents are inspected, **Then**
   every file in it was written by the factory from its own constants; no file
   was copied from or derived from the operator's home.
5. **Given** an attempt that ends on any terminal path, **When** cleanup runs,
   **Then** the archived evidence is already independent of the home and
   survives it.

---

### User Story 3 - The isolation is asserted, not reviewed (Priority: P2)

As the factory operator, a test fails if the worker's home can reach an agent
again, so that this property is defended by the suite rather than by whoever
next edits the adapter.

This repository already holds the idiom: the credential sweep in
`tests/test_workgraph_sweep.py` asserts that the virtual key is read in exactly
one function and that the built environment is exactly four names, which is why
`LITELLM_MASTER_KEY` has stayed out by construction. The same sweep is what this
change must extend rather than edit around — its pinned expectation currently
includes the operator's `HOME`, and updating it is the point of contact where a
future reader learns the rule changed.

The docs owe one sentence more than the change itself: the boundary. Replacing
`HOME` removes what an agent *loads*. It does not confine what an agent *can
reach* — there is no filesystem sandbox, `--dangerously-skip-permissions` is
unchanged, and an agent that goes looking can still read anything the worker
user can. That is `hardening/agent-sandbox`'s scope and it stays open. A
decision entry that implies otherwise would be worse than no entry.

**Why this priority**: The property is cheap to hold and easy to lose — one name
added back to a tuple, in a diff about something else.

**Independent Test**: The sweep fails when `HOME` is restored to the passthrough
tuple, and fails when the built environment gains any value under the operator's
home.

**Acceptance Scenarios**:

1. **Given** the adapter with `HOME` returned to the passthrough allowlist,
   **When** the suite runs, **Then** a test fails naming the rule and why it
   exists.
2. **Given** the built child environment, **When** the sweep inspects it,
   **Then** it asserts the exact set of names and that the home among them is
   the factory's — the allowlist stays a construction, not a filter.
3. **Given** the decision log, **When** this feature lands, **Then** it carries
   an entry recording the change *and* the boundary it does not cross.

---

### Edge Cases

- An attempt whose home cannot be created is an infrastructure failure, named
  and raised — never a quiet fallback to the operator's home, which would
  restore the defect exactly when the disk is already misbehaving.
- A home that survives its node's cleanup is clutter, not a leak; a home deleted
  before its transcript is archived is evidence loss. The archive copy happens
  first, and already does.
- An agent that writes nothing to its home is normal and not an error, exactly
  as an agent that writes no session transcript is normal today.
- The per-cwd transcript directory rule (`project_dir_name`) belongs to the
  agent CLI, not to the factory. This spec does not change it; it changes only
  the root the rule is applied under. If the CLI's rule ever changes, both this
  spec's archive path and today's break together, and the Tier 1 smoke is what
  notices.
- The operator's global `CLAUDE.md` currently instructs agents about a memory
  server. That instruction also tells autonomous agents not to write, so the
  observed harm to date is cost and confusion rather than pollution. It is still
  a standards channel D-025 deliberately did not choose, and it stops reaching
  agents when the home does.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The agent's `HOME` MUST be a directory the factory owns under
  `FACTORY_ROOT`, keyed per node with the same `(factory_root, epic_id,
  node_id)` identity the worktree and pid file already use; the worker's own
  `HOME` MUST NOT reach any child process.
- **FR-002**: `HOME` MUST be replaced rather than removed from the child
  environment. Omitting the name would silently disable session-transcript
  archiving, which resolves the source path from the child's `HOME` and treats
  its absence as "no transcript" rather than as an error.
- **FR-003**: The home MUST exist before an agent is launched, MUST be reused
  across a node's attempts, and MUST NOT be shared between concurrently
  dispatched nodes. A home that cannot be created MUST raise a named
  infrastructure failure; falling back to the worker's home is forbidden.
- **FR-004**: Whatever configuration the agent CLI requires to start
  non-interactively MUST be written by the factory from its own constants. The
  factory MUST NOT copy, read, or derive any part of it from the operator's
  configuration.
- **FR-005**: An agent's own git commits inside its worktree MUST continue to
  succeed under the factory-owned home, carrying the factory's existing salvage
  identity rather than the operator's or a newly invented one.
- **FR-006**: A completed attempt's evidence MUST be unchanged in shape and
  location: `stdout.log` and the session transcript, in the attempt's transcript
  directory under `FACTORY_ROOT`, independent of the home once archived.
- **FR-007**: A structural test MUST fail if the worker's `HOME` can reach a
  child again, extending the existing credential sweep rather than replacing it,
  so the child environment stays a construction whose whole content is asserted.
- **FR-008**: `docs/architecture.md` and `docs/decisions.md` MUST record the
  change and MUST state its boundary explicitly: this isolates what an agent
  loads, not what an agent can reach; filesystem confinement remains the open
  `hardening/agent-sandbox` scope.

### Key Entities

- **Attempt home** — the per-node directory the factory creates and passes as
  `HOME`: same identity as the worktree, same lifetime.
- **Seeded configuration** — the minimum the factory writes into that home to
  let the CLI start non-interactively, from constants, never copied.
- **Session archive** — `stdout.log` plus the agent's own transcript, resolved
  from the child's home and copied into the attempt's transcript directory.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A real dispatched attempt completes on a factory-owned home, and
  its transcript directory holds both artifacts — the same evidence the same
  attempt produces today.
- **SC-002**: The built child environment contains no value that is a path under
  the operator's home, asserted against a worker environment that carries one.
- **SC-003**: With the operator's configuration present on the host, an
  attempt's home contains no MCP server the factory did not write, no
  `oauthAccount`, and no operator `CLAUDE.md`.
- **SC-004**: A commit made from inside the worktree under the child environment
  succeeds and is attributed to the factory identity.
- **SC-005**: The full suite stays green, no dependency is added, and two nodes
  dispatched at `--max-concurrent-nodes 2` complete without sharing a home.

## Work Graph

US2 needs US1's home to exist before it can start an agent on one, and both
edit the adapter, so US2 chains on US1 **merged** rather than riding a pass
edge — the 009 first-run lesson. US3 asserts the property the other two
establish and touches the sweep and the docs, so it chains on US2 merged.

This is a chain rather than a fan-out on purpose. All three stories converge on
`factory/workgraph/adapter.py`, and two concurrent worktrees editing one module
is the collision `--max-concurrent-nodes 2` avoids by disjointness, not by luck.

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-004, FR-005, FR-006]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-007, FR-008]
```

## Assumptions

- **This is the HOME half of the audit's F1, not F1.** The ledger carries
  `hardening/agent-sandbox` (critical, source `audit-2026-08-07`, noted "#1
  blast radius"), whose scope is runtime confinement. That epic remains open and
  unscheduled, and it is what actually stops an agent reading `~/.config`,
  `~/.ssh`, or the age key that decrypts the homelab secrets. This spec removes
  the automatic load, which is the cheap half and can land without the sandbox;
  it deliberately claims nothing about confinement. One note for whoever refines
  F1: of its two recorded anchors, `factory/verify/gates.py` still holds
  `GateExecutor` (at `:154`, the natural enforcement point it names), but
  `factory/workgraph/models.py:187` did not resolve to a runtime seam when
  checked on 2026-08-08 — that line is inside `WorkGraph`'s field block and the
  module names no `runtime` anywhere. F1's inventory needs re-verifying before
  it is dispatched, not inherited.
- **Numbering.** 010–014 are reserved for audit-triage epics accepted by id.
  This finding entered the ledger from an operator observation, so spending a
  reserved number would collide with F1's own triage later.
- **No new dependency.** The change is a path helper, a constructed directory,
  and a name in an existing allowlist.
- **The agent CLI's behaviour on a fresh home was probed on 2026-08-08 and is
  no longer an assumption.** Run with the live implementer alias, an empty
  `HOME`, and exactly the six environment names `attempt_env` builds, the CLI
  **started and answered without prompting** (exit 0) and created its own
  `.claude.json`, `.claude/plugins/`, `.claude/projects/`, `.claude/sessions/`
  and `.claude/backups/`. FR-004 is therefore mostly a prohibition rather than a
  construction: the home must exist and be writable, and the factory must not
  put the operator's configuration in it. Two live consequences came out of the
  same probe — see the next two bullets.
- **FR-005 is confirmed, not anticipated.** A `git commit` inside the worktree
  under that environment failed with `Author identity unknown` (exit 128). An
  agent on a factory-owned home cannot commit its own work until the home
  carries an identity. This is the one thing in this spec that would otherwise
  have been discovered as a burned attempt.
- **The transcript path is the one part still open.** The probe's first run
  invoked the CLI from the wrong working directory, so it wrote to
  `~/.claude/projects/-home-admin/<session>.jsonl` — correct behaviour for that
  cwd, and no evidence either way about a worktree cwd. What it does establish
  is that the `$HOME/.claude/projects/<project-dir>/<session>.jsonl` shape holds
  under a factory-owned home with the right session id; only the directory
  component is unconfirmed. T009 asserts it by reading the archive rather than
  by trusting this.
- **Persona registry, prompt assembly, and the judge are untouched.** The
  agent's model, its standards path, and its verification are all unchanged;
  only the directory it calls home moves.

## Decision: the agent's home is the factory's, keyed like its worktree (decided 2026-08-08)

Three calls, recorded here because each had a live alternative:

1. **Replace `HOME`, do not remove it.** Removing the name reads as the stricter
   choice and is the weaker one: the archive step returns early on a missing
   home and the resulting evidence loss looks exactly like an agent that wrote
   no transcript. The allowlist keeps four names; one of them now points
   somewhere the factory owns.
2. **Key it per node, not per attempt and not per factory.** Per attempt would
   re-onboard the CLI on every retry and discard state the retry is entitled to;
   one shared home would put concurrent agents on one configuration file, which
   `--max-concurrent-nodes 2` makes a real race rather than a theoretical one.
   Per node matches `worktree_path` and `pid_file`, so the home has the same
   identity and the same lifetime as everything else a node owns.
3. **Seed from constants, never from the operator's configuration.** The
   tempting shortcut when the CLI will not start is to copy the working config
   from `~`. That single line would restore `oauthAccount` and the whole
   inherited surface while every test in this spec kept passing.

**The decision-log number is deliberately unassigned here** — claimed at landing
time in `docs/decisions.md`, alongside the boundary statement FR-008 requires.
