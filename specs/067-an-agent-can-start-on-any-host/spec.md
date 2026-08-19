---
state: draft
# HELD ready -> draft 2026-08-19 5:45 PM CT, BEFORE ANY DISPATCH, by the same
# operator session that wrote this spec ninety minutes earlier. A twelve-agent
# adversarial pre-dispatch review found 68 defects across 067/068/069 rated
# would-cost-an-attempt. Dispatching as written would have burned most of nine
# nodes. This returns to `ready` only after the findings are applied AND a
# re-review comes back clean.
#
# The classes found, so the rework is checkable rather than a matter of taste:
#
#   - LINE ANCHORS SYSTEMATICALLY OFF BY ONE OR TWO. Cited from grep context
#     rather than from opened files. `ladder.py:88` is a comment line and the
#     assignment is at :89; `:122` is `_debugger_cycles_spent`, while
#     `_attempts_spent` is at :111; `:100-106` is a def plus docstring, not the
#     comparison; `workflow.py:1459` is a closing paren and the conversion is at
#     :1460-1463; `escalation/workflow.py:395-399` is the EXPIRY fail-safe
#     branch, not the operator-KILL path the task sends an implementer to.
#   - CENTRAL FACTUAL CLAIMS FALSE. 068 asserts `reset` is the ONLY build verb
#     keyed by a compiled-artifact path. `start` and `salvage` are too, which
#     makes FR-010 unachievable as written and its family test unpassable.
#   - A PRESCRIBED RED TEST THAT DOES NOT REPRODUCE. A reviewer executed 068's
#     trap-6 recipe against the real tree and got a different result than the
#     trap asserts.
#   - A CONTROL TEST STRUCTURALLY UNABLE TO FAIL, proved by mutation.
#   - STORIES DECLARED INDEPENDENT THAT SHARE A FILE, in all three specs.
#
# The lesson, recorded where the next drafter meets it: A SPEC DRAFTED FROM GREP
# OUTPUT RATHER THAN FROM OPENED FILES READS AS AUTHORITATIVE AND IS NOT. Every
# anchor above was produced by reading `grep -n -A` context and miscounting the
# offset, which is invisible to the drafter and fatal to the implementer. The
# review cost fifteen minutes and caught what would have cost a night.
# Drafted 2026-08-19 5:20 PM CT by an operator session, from a build-session
# report filed by a consumer agent that dispatched, verified and landed a
# five-story spec against `bryantharpeorg/ergane-test` -- an operator that was
# itself an agent driving the CLI, which the reporter names as the emerging
# normal. Its headline metric is the right one: INTERVENTIONS PER LANDED STORY,
# roughly two dozen for five stories, target zero.
#
# Flipped straight to `ready` at the operator's instruction 2026-08-19 5:20 PM CT,
# and 063 and 064 were HELD to draft in the same breath to let this through --
# the roadmap dispatches in numeric order, so a lower number held at draft is the
# only lever that expresses priority.
#
# WHY THIS ONE JUMPED EVERYTHING. `ergane-cli 0.1.0` is published on PyPI and
# CANNOT EXEC AN AGENT ON ANY X86_64 HOST. Not "degrades" -- cannot start. And
# this factory's own host is `uname -m` = aarch64, the single architecture on
# which the defect is invisible, and the only one on which 054 ("a stranger can
# install ergane"), 059, 060, 061 and 062 have ever been validated. Every claim
# this project has made about a stranger's first run was measured on the one
# machine that cannot see the thing that would stop them.
#
# Verified against the tree before drafting, 2026-08-19:
#
#   - `factory/workgraph/adapter.py:427-431` and `factory/verify/gates.py:586-590`
#     both emit `--ro-bind /usr /usr`, `--symlink usr/bin /bin`,
#     `--symlink usr/lib /lib`, under a comment reading verbatim
#     `# on aarch64. No /lib64 on this host.`
#   - `ls -ld /lib64` on this host: No such file or directory. `/bin -> usr/bin`
#     and `/lib -> usr/lib` are symlinks. The comment is TRUE here.
#   - `factory/verify/toolchain.py:1-30` already states the rule this spec
#     applies to a second surface, and states it about THIS EXACT FAILURE MODE:
#     literals that "carried two things that are not facts about software, only
#     facts about one machine on one afternoon."
#   - `factory/verify/ladder.py:111-119` -- `_attempts_spent` counts every record
#     whose persona is not the debugger. A launch that never produced a token is
#     such a record.
#
# Filed as findings before drafting:
#   install/the-sandbox-mount-set-is-aarch64-only-so-no-agent-can-exec-on-x86-64
#   verify/an-exec-failure-before-the-agents-first-token-is-charged-to-the-ladder
#   interpreter/specs-root-is-compiled-relative-and-resolved-against-the-workers-cwd
---

# Feature Specification: an agent can start on any host

**Created**: 2026-08-19

## The gap, stated precisely

Three defects that share one property: **a fact about the operator's machine was
written down as though it were a fact about software.** Each is invisible on the
machine it was written on, and each stops a stranger cold.

## The mount set describes one host and claims to describe all of them

Both sandbox boundaries build their bwrap argv from literals:

```python
# Minimal system tree: read-only /usr plus the symlinks Ubuntu uses
# on aarch64. No /lib64 on this host.
"--ro-bind", "/usr", "/usr",
"--symlink", "usr/bin", "/bin",
"--symlink", "usr/lib", "/lib",
```

`factory/workgraph/adapter.py:427-431` and `factory/verify/gates.py:586-590`,
identical in both places.

That comment is true of the machine it was written on. On x86_64 the ELF
interpreter of every dynamically linked binary is `/lib64/ld-linux-x86-64.so.2`,
and without a `/lib64` entry in the container it is absent. The runner cannot be
exec'd at all. The failure reads:

```
bwrap: execvp claude: No such file or directory
```

— an **ENOENT for the interpreter**, naming a binary that exists, in a 48-byte
transcript. In the reported session it burned four ladder attempts and an
escalation before a human-readable cause existed anywhere.

**This is the exact defect class `factory/verify/toolchain.py` was written to
eliminate**, on the one surface it did not cover. That module's own docstring:

> the literals carried two things that are not facts about software, only facts
> about one machine on one afternoon

It fixed the executables. The mounts kept the literals.

## A launch that never happened is charged as an attempt

`factory/verify/ladder.py:111-119` counts attempts as records whose persona is not
the debugger. A bwrap exec failure produces such a record, indistinguishable
from an agent that ran and wrote a bad diff. So the ladder charges it, offers
the debugger rung a 48-byte transcript containing only the `execvp` line, and
escalates when the budget runs out.

Fixing the mount set removes one cause. It does not change that **any**
pre-first-token launch fault — a revoked gateway key, an unwritable HOME, a
missing runner, a container that will not start — walks a ladder that cannot
help and spends a budget meant for code that is wrong. The ladder exists to give
a struggling agent more rope. An agent that never started is not struggling.

## A compiled graph carries a path that means two different things

`ergane build start graph.json` failed with:

```
cannot read prompt source specs/001-trip-expenses/spec.md: [Errno 2] No such file or directory
```

because the graph carried `specs_root: "specs"` and the **worker** resolved it
against its own working directory. The remedy — re-derive with
`--specs-root "$PWD/specs"` — is not discoverable from the error.

The compiled graph is already machine-local by design: `target_repo` is a
worker-host absolute path. So there is no portability argument for keeping
`specs_root` relative, and every reason to refuse one.

## User Scenarios & Testing

### User Story 1 - The sandbox mount set is read from the host, not declared (Priority: P1)

As an operator on any Linux host, an agent and a gate can be exec'd inside the
sandbox, because the container's system tree is derived from the host's own
layout rather than from one machine's layout written down as a constant.

**Why this priority**: P1, and it outranks everything else queued. Until it
lands, the published package cannot run an agent on the majority of Linux hosts,
and no other improvement is reachable by anyone affected.

**Independent Test**: build the argv against a fake host tree that has `/lib64`
and against one that does not, and assert the argv follows each.

**Acceptance Scenarios**:

1. **Given** a host layout in which `/lib64` is a symlink, **When** the agent
   sandbox argv is built, **Then** it contains a `--symlink` entry for `/lib64`
   pointing at that symlink's own target — proven by a committed test that
   supplies the layout rather than reading the real root, so the assertion holds
   on every architecture including the aarch64 one this is developed on.
2. **Given** a host layout in which `/lib64` does not exist, **When** the argv is
   built, **Then** it contains no `/lib64` entry — proven by a committed test.
   Binding a path that is not there is a `bwrap: Can't find source path` failure,
   which is how the opposite over-correction presents.
3. **Given** each of `/bin`, `/lib`, `/lib64` and `/sbin`, **When** the argv is
   built, **Then** each is emitted if and only if it is a symlink on the host,
   with the host's own target — proven by a committed test over a layout where
   the four differ from each other, so the test cannot pass by treating them as a
   fixed set.
4. **Given** the diff, **When** both boundaries are inspected, **Then** the agent
   sandbox (`factory/workgraph/adapter.py`) and the gate sandbox
   (`factory/verify/gates.py`) derive the mount set from **one shared
   implementation** — proven by a committed test asserting both produce the same
   system-tree entries for one supplied layout. Two copies is how they came to
   disagree with reality in the same way twice.
5. **Given** the diff, **When** the comment above the mount set is read, **Then**
   it does not assert a fact about any particular host — proven by the absence of
   the phrase it replaces. The stale comment is the defect's documentation and
   must not survive the fix.
6. **Given** a layout in which `/usr` is absent, or in which one of `/bin`,
   `/lib`, `/lib64`, `/sbin` exists and is neither a symlink nor a bindable
   directory, **When** the mount set is derived, **Then** the derivation raises a
   named error identifying the path and what was found there, and no subprocess
   is created — proven by a committed test that calls the derivation directly.
   **A path that simply does not exist is US1-S2's case and MUST NOT refuse**:
   `/lib64` is absent on the aarch64 host this is developed on, and a refusal
   there disables every dispatch on this machine. `ToolchainError`
   (`factory/verify/toolchain.py`) is the precedent for the refusal's shape.

---

### User Story 2 - A launch that never reached the agent is not an attempt (Priority: P1)

As an operator, an infrastructure fault that stopped the agent from starting is
reported as an infrastructure fault immediately, instead of consuming my attempt
budget and paging me after the ladder exhausts.

**Why this priority**: P1. It is what turned a one-line mount bug into four
attempts and an escalation, and it generalises to every launch fault that will
ever exist.

**Independent Test**: drive a node whose sandbox launch fails before any output,
and assert the attempt budget is unchanged and the operator-facing condition
names the launch.

**Acceptance Scenarios**:

1. **Given** a sandbox launch that fails before the agent produces any output,
   **When** the node's next action is decided, **Then** the ladder's spent-attempt
   count is unchanged — proven by a committed test asserting the count directly,
   not by asserting the node retried.
2. **Given** the same, **When** the failure surfaces, **Then** it is reported as a
   launch failure distinct from an attempt failure, naming the launch fault —
   proven by a committed test asserting the reported condition.
3. **Given** the same, **When** the operator is notified, **Then** the
   notification happens on the launch failure rather than after the ladder
   exhausts — proven by a committed test asserting the notifier is reached
   without the budget being spent.
4. **Given** an agent that started, produced output, and then failed, **When**
   the next action is decided, **Then** it IS charged as an attempt exactly as
   today — proven by a committed test. The distinction is "did the agent
   start", and a fix that stops charging real failures is worse than the defect.
5. **Given** repeated launch failures, **When** they recur, **Then** the node does
   not loop indefinitely — proven by a committed test asserting a bounded number
   of launch retries before the node stops. An unbudgeted path with no bound is a
   different outage, not a fix.

---

### User Story 3 - A compiled graph means the same thing in both processes (Priority: P2)

As an operator, a graph I derive in one directory is dispatchable by a worker
whose working directory is somewhere else.

**Why this priority**: P2. One intervention rather than many, and the workaround
exists once known — but it fails at dispatch, after a key has been minted.

**Independent Test**: derive with a relative `--specs-root` and assert the
artifact carries an absolute path.

**Acceptance Scenarios**:

1. **Given** `ergane spec derive` invoked with a relative specs root, **When** the
   artifact is written, **Then** it carries an absolute path — proven by a
   committed test asserting the written value.
2. **Given** the same for the target repository, **When** the artifact is written,
   **Then** that path is absolute too — proven by a committed test.
3. **Given** an artifact that carries a relative path from any source, **When** it
   is read for dispatch, **Then** it is refused naming the field and the path,
   before any key is minted — proven by a committed test. Refusing at read time
   is what makes an artifact written by an older version fail honestly rather
   than at the far end of a dispatch.
4. **Given** a derive whose specs root does not exist, **When** it resolves,
   **Then** it fails naming the resolved absolute path rather than the string it
   was given — proven by a committed test. Printing the resolved path is what
   makes a cwd mismatch self-evident.

---

### Edge Cases

- **A host where `/usr` itself is not merged.** Older or unusual distributions
  have real `/bin` and `/lib` directories rather than symlinks. US1-S3 covers it:
  emit an entry only where the host has a symlink, and the un-merged host gets
  none and no refusal; only `/usr` is required, and its bind carries the content.
- **A launch failure that is really a transient.** A gateway 503 at key-mint
  time is a launch fault by this story's definition, and US2-S5's bound is what
  stops it becoming an infinite unbudgeted loop.
- **An artifact derived before this spec lands.** It carries a relative path and
  US3-S3 refuses it by name. That is a deliberate, breaking, one-line-of-output
  failure rather than a silent misresolution, and re-deriving is the remedy.

## Requirements

### Functional Requirements

- **FR-001**: The sandbox system-tree mount set MUST be derived from the host's
  own filesystem layout rather than from constants.
- **FR-002**: For each of `/bin`, `/lib`, `/lib64` and `/sbin`, an entry MUST be
  emitted if and only if that path is a symlink on the host, using the host's own
  target.
- **FR-003**: Both the agent boundary and the gate boundary MUST obtain the
  system-tree mount set from one shared implementation.
- **FR-004**: `/usr` MUST exist and be bindable. `/bin`, `/lib`, `/lib64` and
  `/sbin` are mirrored only where the host has a symlink; **absence is never a
  refusal**. A path among those four that exists but is neither a symlink nor a
  bindable directory MUST produce a named refusal, raised by the mount-set
  derivation before any subprocess is created.
- **FR-005**: A sandbox launch that fails before the agent produces output MUST
  NOT consume the node's attempt budget.
- **FR-006**: Such a failure MUST be reported as a launch failure, distinct from
  an attempt failure, at the time it happens.
- **FR-007**: Launch retries MUST be bounded, so an unbudgeted path cannot loop
  indefinitely.
- **FR-008**: `spec derive` MUST resolve the specs root and the target repository
  to absolute paths in the artifact it writes.
- **FR-009**: A compiled graph carrying a relative path for either field MUST be
  refused at read time, naming the field and the value.
- **FR-010**: A path that does not resolve MUST be reported as the absolute path
  it resolved to, not as the string supplied.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: []
  implements: [FR-005, FR-006, FR-007]
US3:
  depends_on: []
  implements: [FR-008, FR-009, FR-010]
```

## Success Criteria

### Measurable Outcomes

- **SC-001**: Build both sandbox argvs against a supplied layout containing
  `/lib64` and against one without it, and paste both argvs into the diff. The
  two must differ by exactly the `/lib64` entry.
- **SC-002**: Remove the host-derivation and confirm the US1 tests fail. A mount
  set nobody has watched follow a different host is a mount set nobody has
  tested.
- **SC-003**: Drive a node whose launch fails before output, and paste the
  before-and-after attempt counts.
- **SC-004**: Confirm an agent that started and then failed is still charged,
  with the count pasted. This is the control for SC-003.
- **SC-005**: Derive a graph from a directory other than the repository root
  with a relative specs root, paste the artifact's resolved fields, and dispatch
  it from a third directory.

## Assumptions

- The host running the worker is the host whose layout matters. Both sandboxes
  fork on the worker, so reading the worker's own root is correct; no cross-host
  dispatch exists.
- `bwrap` remains the sandbox backend. Nothing here depends on that, but the
  argv shape does.
- The reporter's x86_64 verification is taken as accurate — they patched both
  boundaries in an installed venv and subsequently landed five stories — but no
  x86_64 host is available here, which is why every acceptance scenario is
  written against a **supplied** layout rather than the real root.
