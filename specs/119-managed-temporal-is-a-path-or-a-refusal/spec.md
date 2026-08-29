---
state: draft
fixes:
  - temporal/managed-mode-is-a-dead-path-and-verification-reports-it-passing
# DRAFTED 2026-08-28 by the operator session, against ergane-buildout at 8bb2d4b.
# A new number: none of the 089-102 slots reserved on 2026-08-23 names this.
#
# THE DOCUMENTED FIRST-RUN PATH CANNOT PRODUCE A SERVER, AND VERIFICATION SAYS IT
# DID. `install --from-file` accepted `mode = "managed"`. `--verify` printed
# `[PASS] temporal: managed Temporal: the engine installs and supervises the
# server`. Worker install produced no server. Worker and bridge crash-looped
# until systemd's start limit gave up. Three separate patches were needed before
# a server existed.
#
# N6a — THE DECLARED MODE NEVER REACHES THE LAYOUT, AND A DOCSTRING DESCRIBES A
# MECHANISM THAT DOES NOT EXIST. `resolve_layout`
# (`factory/supervision/units.py:255`) takes six keyword arguments and none of
# them is `temporal_mode`; its docstring says it resolves "where this
# installation actually is", from the filesystem. So `temporal_mode` keeps its
# dataclass default `"external"` (`:201`) and no caller ever sets it. Meanwhile
# `_temporal_managed` (`:324`) says "`ergane worker install` is the supervised
# path and defaults to managed. The `ergane install` walkthrough sets
# `temporal_mode="external"` when the operator chose external Temporal, and that
# layout is what `resolve_layout` will produce for the same host." Every clause
# of that is a description of a mechanism that is not in the code: nothing writes
# the value, nothing reads a declared one, and the default is the opposite of
# what the sentence claims.
#
# N6b — THE WRAPPER DROPS EVERY ARGUMENT AFTER THE THIRD. `ergane-run.sh` ends in
# `exec "${{3:-<interpreter>}}" -m "$1"` (`:600`). Its three positionals are the
# module, the working directory and the interpreter; anything after them is
# discarded. Worker and bridge pass a module name and nothing else, which is why
# nobody noticed. The Temporal unit's `ExecStart` passes `--db-filename`,
# `--namespace` and `--log-level`, and all three vanish.
#
# N6c — NOTHING CREATES THE SQLITE DIRECTORY. Neither worker install nor the
# server module makes it, so the server cannot open its own database.
#
# SECONDARY DEFECTS FROM THE SAME CHAIN, ALL OBSERVED. `--verify` passed three
# times while no server existed, and the reason is sharper than "it does not
# dial". `TemporalProbe.gather` (`factory/controlplane/verify.py:686-696`)
# short-circuits managed mode with a comment that states the contract: "Managed
# mode installs and supervises its own server; the verify check is whether the
# unit was generated, which happens at install time, not here." That reasoning is
# defensible — dialling would require a live server already running. But the code
# does not check unit generation either: it returns a `TemporalSnapshot` with
# `namespace_exists=True` hardcoded and a detail string asserting the engine
# supervises the server. So the probe claims a contract it does not enforce, and
# its premise is false anyway, because N6a means the unit is never generated.
# Fix the premise (US1) and the check becomes worth making honest (US3).
# Neither the worker nor the bridge
# unit carries an ordering dependency on the Temporal unit, so both burn their
# systemd start limit on every boot. Worker install reports only the probe timer
# and says nothing about the three services it also started, which were already
# failing as the verb returned. And worker uninstall dials Temporal first, so the
# verb whose job is to remove the units depends on the service they run.
#
# WHY THE DOCSTRING MATTERS AS MUCH AS THE CODE. A reader checking whether this
# path works finds a docstring asserting it does, one function above the default
# that makes it false. That is why this went three patches deep before anyone
# doubted the mechanism rather than their own configuration.
#
# NOT IN SCOPE. This spec does not add a Temporal deployment mode, does not
# change the external path, does not vendor a server binary, and does not change
# what the walkthrough asks the operator. It makes the declared mode reach the
# thing that acts on it, or refuse.
---

# Feature Specification: managed Temporal is a path or a refusal

**Created**: 2026-08-28
**Depends on**: nothing outside this spec.

## The gap, stated precisely

An operator declares `mode = "managed"`, the installer accepts it, verification
confirms it, and no server exists. Four things had to be simultaneously true for
that outcome, and each is independently a defect:

1. The declared mode is never carried into the layout that decides what gets
   generated, so the managed units are not written.
2. The wrapper every unit runs through discards arguments past the third, so even
   a generated Temporal unit could not receive its own flags.
3. Nothing creates the directory the server's database lives in.
4. Verification asserts the server is there without asking it anything.

Fix any three and the path still fails. Fix the fourth alone and it fails
silently, which is what happened.

## The rule this spec is asking for

**A declared mode either produces the thing it names, or the verb refuses at the
moment it is declared — and verification proves the server by talking to it.**

### What this spec is not

It is not a new deployment mode, and it is not a change to the external path,
which works.

It is not a vendored server. How the binary arrives is unchanged.

It is not a redesign of the wrapper. One positional contract is corrected; the
wrapper's shape stays.

## User Scenarios & Testing

### User Story 1 - The declared mode reaches the layout, or the verb refuses (Priority: P1)

As an operator, declaring managed Temporal either generates the managed units or
tells me at install time that it will not.

**Why this priority**: P1 and it depends on nothing. Without it the other stories
fix a path that is never taken.

**Acceptance Scenarios**:

1. **Given** an install declaring managed mode, **When** the layout is resolved,
   **Then** the layout carries managed mode — proven by a committed test.
2. **Given** that layout, **When** the generated files are enumerated, **Then**
   the Temporal server unit is among them — proven by a committed test.
3. **Given** an install declaring external mode, **When** the layout is
   resolved, **Then** it carries external mode and no Temporal unit is generated
   — proven by a committed test. The working path stays working.
4. **Given** an installation whose declared mode cannot be determined, **When**
   the layout is resolved, **Then** the verb refuses naming what it could not
   read, rather than defaulting silently — proven by a committed test. A silent
   default is what made this defect survive three patches.
5. **Given** `_temporal_managed`, **When** its docstring is read, **Then** it
   describes the mechanism that exists — proven by a committed test asserting the
   behaviour the docstring claims.

### User Story 2 - A unit's arguments reach the process (Priority: P1)

As an operator, the flags a generated unit passes are the flags the process
receives.

**Why this priority**: P1. It is a one-line contract error whose blast radius is
every unit that takes an argument, and today that is exactly the one unit nobody
could get running.

**Acceptance Scenarios**:

1. **Given** a unit passing a module and three flags through the wrapper,
   **When** the wrapper runs, **Then** the process receives all three flags —
   proven by a committed test.
2. **Given** a unit passing only a module name, **When** the wrapper runs,
   **Then** it behaves exactly as it does today — proven by a committed test.
   Worker and bridge take this path and must not change.
3. **Given** a unit overriding the working directory and the interpreter, **When**
   the wrapper runs, **Then** both overrides still apply and are not passed on to
   the module — proven by a committed test. The three positionals keep their
   meaning; only what follows them changes.

### User Story 3 - The server can start, and verification proves it (Priority: P1)

As an operator, the managed server has somewhere to put its database, starts in
the right order, and is confirmed by being asked rather than by being assumed.

**Why this priority**: P1. Story 3 is the difference between "the units exist"
and "the path works", and its verification half is what stopped anyone noticing.

**Acceptance Scenarios**:

1. **Given** a managed installation whose database directory does not exist,
   **When** the server starts, **Then** the directory is created — proven by a
   committed test.
2. **Given** a managed installation, **When** the worker and bridge units are
   generated, **Then** each declares an ordering dependency on the Temporal unit
   — proven by a committed test. Without it both burn their start limit on every
   boot.
3. **Given** a managed installation with no server running, **When** `--verify`
   runs, **Then** it fails naming the unreachable server — proven by a committed
   test. It currently passes.
4. **Given** a managed installation with a server running, **When** `--verify`
   runs, **Then** it passes having dialled the server — proven by a committed
   test.
5. **Given** worker install, **When** it returns, **Then** it reports every
   service it started and the state each is in — proven by a committed test. It
   currently reports only the probe timer, while three services fail behind it.
6. **Given** worker uninstall, **When** it runs against an unreachable Temporal,
   **Then** it removes the units anyway — proven by a committed test. The verb
   that removes the units may not depend on the service they run.

## Work Graph

```yaml
US1:
  implements: []
  depends_on: []
US2:
  implements: []
  depends_on: []
  depends_on_merged: [US1]
US3:
  implements: []
  depends_on: []
  depends_on_merged: [US2]
```

All three change `factory/supervision/units.py` — US1 the layout resolver, US2
the wrapper template, US3 the generated units — and US3 also changes
`factory/controlplane/verify.py`. They are serialised on **file ownership rather
than on logic**: the three edits are logically independent and touch distant
regions of one file, and the chain is declared rather than raced because the
merge-group build tests the merged tree, where a race costs a rebuild.

## Requirements

- **FR-001**: The declared Temporal mode MUST be carried into the resolved
  layout.
- **FR-002**: A managed layout MUST generate the Temporal server unit; an
  external layout MUST NOT.
- **FR-003**: An installation whose declared mode cannot be determined MUST be
  refused, naming what could not be read.
- **FR-004**: `_temporal_managed`'s docstring MUST describe the mechanism that
  exists.
- **FR-005**: The wrapper MUST pass every argument after its three positionals
  through to the module.
- **FR-006**: A unit passing only a module name MUST behave exactly as today.
- **FR-007**: The managed server's database directory MUST be created if absent.
- **FR-008**: Worker and bridge units MUST declare an ordering dependency on the
  Temporal unit in a managed installation.
- **FR-009**: `--verify` MUST confirm managed Temporal by dialling it, and MUST
  fail when it cannot be reached.
- **FR-010**: Worker install MUST report every service it started and each
  service's state.
- **FR-011**: Worker uninstall MUST remove units without requiring Temporal to be
  reachable.

## Success Criteria (summary)

- A fresh host declaring managed mode has a running server after `worker
  install`, with no hand-patching.
- `--verify` cannot pass while no server exists.
- An operator who mis-declares a mode learns at install time, not after three
  patches.
