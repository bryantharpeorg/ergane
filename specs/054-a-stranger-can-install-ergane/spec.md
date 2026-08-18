---
state: landed
# Attested landed 2026-08-18. US1 be33c95 (#190), US2 6d1253e (#191),
# US3 e72ced4 (#193) -- all three observed on ergane-buildout.
#
# Committed late, and that is the note worth keeping: this trio was written and
# dispatched from the working tree without ever being committed, so the epic
# built and landed three stories against a spec that was not in git. The only
# 054 path in the merged tree before this commit was
# `evidence/us1-sc-001.md`, which US1's own agent committed. `ergane spec
# landed` could not read the epic at all -- it resolves the spec out of the
# landed commit, and refused with "exists on disk, but not in <sha>". Dispatch
# reads the working tree; every downstream verb reads git. Commit the trio
# before `ergane build start`, not after.
#
# US2 took two attempts. The judge caught what the plan's trap 1 predicted:
# `test_host_with_every_prerequisite_passes` reached the real host indirectly
# through the default seam, and the story's own AST-scan guard could not see an
# indirect call. US2-S4's wording -- "no committed test for it calls the real
# host" -- is what gave the judge the hook. One retry instead of the four the
# same defect class cost 042/US3.
# Flipped draft -> ready 2026-08-17 ~9:33 PM CT at the operator's instruction,
# in the same session that drafted it and against the measurement below.
#
# Drafted 2026-08-17 ~9:30 PM CT by an operator session, from a question the
# operator asked directly: "after we finish tonight's work, what will be left to
# install it on a new machine/environment?"
#
# The answer, measured rather than recalled. Every provisioning spec is landed,
# verified by content against `ergane-buildout`:
#
#   033-ergane-install 3/3   034-ergane-init 7/7   041-escalation-workflow 4/4
#   042-supervised-services 4/4   043-runtime-root-integrity 4/4
#   048-declared-control-plane 4/4   050-init-preconditions 3/3
#   051-first-run-defaults 2/2
#
# So the mechanism is finished. What is left is the approach to it. Three facts,
# each checked against the tree on the day this was written:
#
#   1. `ls README*` exits 2. `docs/` holds architecture, decisions, a queue
#      canary and a verification log -- nothing that says "start here".
#      `pyproject.toml` declares `version = "0.1.0"` and the `ergane` entry
#      point, and nothing is published, so the first step of every install is an
#      unwritten `git clone` the new operator has to be told about by a human.
#   2. `ergane install --verify` runs five probes -- llm, temporal, memory,
#      telemetry, escalation -- and no probe consults a host prerequisite. Not
#      bwrap, not an authenticated `gh`, not a systemd user session. `ergane
#      doctor` does not either: its four probes (orphaned-key, stale-worker,
#      stale-worktree, store-integrity) are runtime health, not host readiness.
#   3. `factory/controlplane/verify.py:193` reads `persona = "implementer"`.
#      One persona of the registry is proved. A wrong `judge` alias -- and every
#      alias in the shipped `personas.yaml` belongs to one operator's proxy --
#      passes install clean and surfaces later as a verification failure.
#
# Numbered 054: 053 worker skew. Nothing in 001-053 covers the entry.
---

# Feature Specification: a stranger can install Ergane

**Created**: 2026-08-17

## The gap, stated precisely

Ergane is installable. It is not installable *by someone who has not been told
how*, and those are different properties. The verb chain exists and is good:

```
ergane install              # interview five subsystems -> ~/.config/ergane/config.toml
ergane install --verify     # probe each one, including a live completion
ergane worker install       # systemd units: worker, bridge, bounded slice, probe timer
cd <repo> && ergane init --wire
ergane repo onboard
```

Every one of those verbs resolves today. What does not exist is any artifact in
this repository that names that chain in order, states what must already be true
of the host before the first command, or tells the reader how to obtain `ergane`
at all. The chain is knowledge held by the operator who built it.

## Why a page, and why a test on the page

A getting-started page that nobody checks decays into a liability faster than no
page at all, because a stale command reads as authority. This repository has
already solved that problem once, for `CLAUDE.md`, in `tests/test_claude_md.py`:
304 lines that extract every command the file names and assert each resolves,
extract every path it cites and assert each exists, and -- the part that matters
-- assert that the extraction itself found something, so the sweep cannot pass
by reading nothing.

That test is the reuse anchor. This spec's page earns the same enforcement, or
it is not worth writing.

## What this spec is not trying to fix

The largest single obstacle between a bare machine and a first epic is that
`llm.mode` accepts exactly one dispatchable value. `factory/controlplane/config.py`
refuses the other in terms that are worth quoting, because they explain why:

> `llm.mode = "direct"` cannot be dispatched against: every attempt runs on its
> own model-constrained, TTL'd virtual key minted at the gateway ... Put a
> LiteLLM-shaped gateway in front of the provider and declare
> `llm.mode = "gateway"`.

That is a correct design decision and this spec does not revisit it. A gateway is
a prerequisite, like git. The repair is to *say so, in the place a new operator
looks first*, rather than to let them discover it at the fourth interview
question. Standing up a gateway stays out of scope, permanently, and US1 names it
as a prerequisite rather than a step.

## User Scenarios & Testing

### User Story 1 - The repository tells a new operator where to start (Priority: P1)

As someone who has just been handed this repository, I can read one page that
takes me from a bare machine to a dispatched epic, and every command on it works.

**Why this priority**: it is the whole gap. Items 2 and 3 improve an install the
reader cannot currently reach.

**Independent Test**: delete nothing and mock nothing -- run the committed sweep
over the new page and confirm every command it names resolves and every path it
cites exists.

**Acceptance Scenarios**:

1. **Given** the diff, **When** `README.md` at the repository root is read,
   **Then** it names, in order, the commands that take a host from nothing to a
   dispatched epic, and states the prerequisites that must already be true --
   including a LiteLLM-shaped gateway, an authenticated `gh`, and `bwrap` --
   proven by a committed test that extracts the commands and asserts each
   resolves against the CLI's own `--help`.
2. **Given** the committed sweep, **When** it runs against a `README.md` whose
   command list is empty, **Then** it fails -- proven by a committed anti-vacuity
   test asserting the extraction found a non-empty list containing
   `ergane install` and `ergane init` by name. A sweep that reads nothing and
   reports success is the failure mode this story exists to prevent.
3. **Given** the diff, **When** every path the page cites is checked, **Then**
   each exists in the tree -- proven by a committed test with its own
   anti-vacuity assertion.
4. **Given** the diff, **When** the page is read for secrets, **Then** it names
   environment variable *names* and never a value, and no token, key or address
   belonging to a live deployment appears -- proven by a committed test asserting
   the page contains no value matching the shipped secret-shaped patterns.
5. **Given** the diff, **When** the page's claims about spec state, story counts
   or spend are checked, **Then** there are none -- the page directs the reader
   to the live source instead, held by a committed test on the same principle
   `tests/test_claude_md.py` already enforces for `CLAUDE.md`.

---

### User Story 2 - Install refuses a host that cannot run an agent, and names what is missing (Priority: P1)

As an operator installing on a new machine, `ergane install --verify` tells me
which host prerequisite is absent, instead of letting me discover it when the
first attempt fails inside a sandbox.

**Why this priority**: P1 because the failure it prevents is expensive and
late. A host without `bwrap` completes the entire interview, passes all five
current probes, and fails at the first dispatched attempt.

**Independent Test**: run the host probe against a simulated host that lacks each
prerequisite in turn and confirm one finding per absence, naming the prerequisite.

**Acceptance Scenarios**:

1. **Given** a host missing `bwrap`, **When** `ergane install --verify` runs,
   **Then** it emits a failing finding naming `bwrap` and what it is needed for
   -- proven by a committed test that **simulates** the host through the probe's
   injected seam.
2. **Given** a host whose `gh` is present but unauthenticated, **When**
   `--verify` runs, **Then** the finding distinguishes *absent* from
   *present-but-unauthenticated*, because the remedies differ -- proven by a
   committed test.
3. **Given** a host with every prerequisite present, **When** `--verify` runs,
   **Then** the host check passes and the other five probes' behaviour is
   byte-identical to today's -- proven by a committed test.
4. **Given** the diff, **When** the new probe is read, **Then** it consults the
   host only through an injected seam, and no committed test for it calls the
   real host -- proven by a committed test asserting the seam is injectable and
   that the probe's own tests pass with the host simulated. A test that shells
   out to the real host passes in one environment and fails in the other,
   deterministically, and no retry can repair it.
5. **Given** the probe finds a missing prerequisite, **When** it reports,
   **Then** it reports and does not remediate -- it installs nothing, writes
   nothing outside its finding, and the operator decides.

---

### User Story 3 - Verify proves every model the registry can dispatch, not one (Priority: P2)

As an operator whose gateway is not the one this repository was built against,
`ergane install --verify` tells me every alias my gateway is missing, in one run.

**Why this priority**: P2 because US2 is the more common failure on a new host.
This one is the more *confusing* failure: install passes, the first epic builds,
and the judge dies.

**Independent Test**: point the registry at a set of aliases, half of which the
simulated gateway knows, and confirm one finding per unknown alias.

**Acceptance Scenarios**:

1. **Given** a registry whose personas resolve to several distinct model
   aliases, **When** `--verify` runs, **Then** every distinct alias is proved,
   not only `implementer`'s -- proven by a committed test asserting the set of
   aliases probed equals the set of distinct aliases in the registry.
2. **Given** two personas sharing one alias, **When** `--verify` runs, **Then**
   that alias is probed once, not twice -- a live completion per persona is
   spend the operator did not ask for, and the registry has more personas than
   models.
3. **Given** a gateway that does not know one alias, **When** `--verify` runs,
   **Then** the finding names the alias, the personas that would have used it,
   and that the others passed -- proven by a committed test. Reporting only the
   first failure hides how much work the operator still has.
4. **Given** a persona declared `agent: none`, **When** `--verify` runs, **Then**
   it is skipped and no completion is attempted, because such a persona has no
   model by construction -- proven by a committed test.
5. **Given** the diff, **When** the fallback aliases are considered, **Then** the
   spec states whether they are probed and the test holds that decision, so the
   answer is a decision rather than an omission.

## Functional Requirements

- **FR-001**: The repository MUST contain a root `README.md` that names, in
  order, the commands taking a host from nothing to a dispatched epic.
- **FR-002**: `README.md` MUST state the prerequisites that must already be true
  of the host, and MUST name the LiteLLM-shaped gateway among them.
- **FR-003**: A committed sweep MUST assert that every command `README.md` names
  resolves and every path it cites exists, each with an anti-vacuity assertion
  that the extraction read a non-empty list.
- **FR-004**: `README.md` MUST NOT contain a secret value, and MUST NOT state a
  spec state, story count or spend figure that a live source already answers.
- **FR-005**: `ergane install --verify` MUST emit a finding per absent host
  prerequisite, covering at minimum `bwrap`, an authenticated `gh`, and `git`.
- **FR-006**: The host probe MUST distinguish absent from present-but-unusable.
- **FR-007**: The host probe MUST consult the host through an injected seam, and
  its committed tests MUST simulate the host rather than probe it.
- **FR-008**: `ergane install --verify` MUST prove every distinct model alias the
  persona registry can dispatch, and MUST probe each distinct alias exactly once.
- **FR-009**: A failing alias MUST NOT stop the sweep; every alias MUST be
  reported.
- **FR-010**: A probe added by this spec MUST NOT remediate: it MUST report the
  condition and MUST NOT install, write or change anything on the host.

## Success Criteria

- **SC-001**: A reader following `README.md` on a host that already satisfies
  the stated prerequisites reaches a dispatched epic without consulting any
  other document. Evidence is a committed transcript of the command sequence.
- **SC-002**: The count of host prerequisites checked by `--verify` is greater
  than zero, asserted by a test rather than by reading.
- **SC-003**: The set of model aliases `--verify` probes equals the set of
  distinct dispatchable aliases in the registry, asserted by a test.
- **SC-004**: No test added by this spec consults the real host for a value that
  differs between the bwrap gate and a CI runner.

## Out of Scope

- **Standing up a LiteLLM gateway.** Permanently. It is a prerequisite, and
  `llm.mode = "direct"` is refused for reasons the config file states well. US1
  names it; nothing here provisions it.
- **Publishing the package.** Whether `ergane` becomes `uv tool install`-able is
  a distribution decision with its own consequences. `README.md` documents the
  path that works today.
- **Installing prerequisites.** FR-010 is deliberate: a tool that installs
  `bwrap` for you is a tool that needs privileges it should not hold.
- **The `update` verb.** Staying current in place is the portability principle's
  fourth verb and has no spec yet. This one covers arrival, not maintenance.
- **A guided first-run walkthrough.** Wanted, not drafted, and it belongs to
  `ergane init` rather than to a page.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: []
  implements: [FR-005, FR-006, FR-007, FR-010]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-008, FR-009]
```

US1 touches `README.md` and a new test file, and shares nothing with the others.

US3's edge is a **merge** edge, not a pass edge, and it is declared for
contention rather than for correctness: US2 and US3 both edit
`factory/controlplane/verify.py`, US3 changing a line inside `LLMProbe` while
US2 appends a class and a `REGISTRY` entry. A dependency edge models what a
story needs to *exist*, which is not the same question as what it will *touch* —
so the edge is declared deliberately, because concurrent worktrees on one module
is a collision this repository has already paid for more than once, and it
presents as tests dying after a clean rebase rather than as a conflict.
