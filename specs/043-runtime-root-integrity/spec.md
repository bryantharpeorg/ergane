---
state: ready
# specs_root: specs
# target_repo: /home/admin/code/ergane
# Scaffolded by `ergane findings promote` on 2026-08-14 from four findings, then
# rewritten by an operator session the same afternoon. The scaffold's generated
# criteria ("the ledger records a resolution tied to this spec") are not provable
# from a diff and were replaced wholesale; see D-037 / constitution principle VIII.
#
# Renamed from 043-engine-state-relocation before any dispatch. This spec does NOT
# relocate the stores out of the target repo. That is a live question the operator
# has not settled — the case for it is multi-repo correctness (the three databases
# are engine-scoped and 034 is building toward an engine that serves many repos),
# and the case against it is that 011-agent-sandbox already closes the safety half.
# US1 here fixes the detector so it is sound wherever the stores live, which is
# what makes the relocation question separable rather than urgent.
#
# Common thread across all four stories: every one is a place where the code names
# the runtime root wrongly, or asserts something false about it.
---

# Feature Specification: 043-runtime-root-integrity

## Context

On 2026-08-14 an agent working `033-ergane-install/us2` ran, verbatim from its
transcript:

```bash
cd /home/admin/code/ergane && rm -rf .factory && uv run pytest -q \
  tests/test_store_isolation.py::test_leaking_writers_are_contained
```

It destroyed the live evidence store, the findings ledger, the usage ledger, every
archived transcript, and both live node worktrees — the last of these because node
worktrees live *inside* the directory it deleted. The epic ended one story of three
and took a concurrent epic's gate run down with it. Recovery came from a nightly
off-host snapshot taken 8h44m earlier.

The escape from the worktree is a separate, older defect
(`hardening/agent-edits-the-operator-checkout-not-its-worktree`, eight occurrences,
already promoted; containment is `011-agent-sandbox`). **This spec is about why the
agent ran the `rm` at all**, which is the part no sandbox addresses.

The test it was running asserts, as its final statement, that
`.factory/verification.db` does not exist. That path is
`DEFAULT_VERIFICATION_DB_PATH` — where the production system keeps the live store.
The assertion is relative to the process cwd, and pytest runs from the repo root,
so on any host where the factory has actually run, the test fails permanently and
its failure message names the file to delete:

```
AssertionError: cwd-relative default store .factory/verification.db was created
```

The agent read that message and satisfied it. It was the cheapest correct reading
of a red test. The test has been in this state since `030-test-suite-store-isolation/us1`
landed it in `c572fdb`; it passed its own gate and its own judge because a fresh
node worktree at dispatch time has no `.factory/` in it.

The remaining three stories are the surrounding defects in how the runtime root is
addressed, all filed the same day, and they have a dispatch-order constraint
between them that is stated in the Work Graph and repeated here because getting it
backwards silently destroys data: **US2 must land before US3.**

---

### User Story 1 - The leak detector stops requiring the live store's absence (Priority: P1)

`test_leaking_writers_are_contained` proves something worth proving: that the real
activities the roadmap registers write only into pytest's session store and never
into the cwd-relative default. Its own comment says so — "assert every write lands
in the session's tmp store and the cwd-relative default was not created." The
implementation conflates *was not created by this test* with *does not exist at
all*, and only the first of those is true of a correct system.

The detector must distinguish them. Whether the default path already held a live
database before the test began is not the test's business; whether the test's own
activities touched it is precisely its business.

**Why this priority**: It is a live landmine. Any agent dispatched near store
isolation meets a red test whose stated remedy is deleting production data, and one
already has. It is also the only story here with no dependency, so it can land first.

**Independent Test**: Run the suite twice on a host with a populated
`.factory/verification.db` — once as-is, once with a deliberately reintroduced
leaking writer — and confirm the first passes with the store untouched and the
second fails naming the leak.

**Acceptance Scenarios**:

1. **Given** a host where `.factory/verification.db` already exists and holds rows,
   **When** `test_leaking_writers_are_contained` runs, **Then** it passes, and the
   diff contains that test's pasted output showing the pass alongside the file's
   size and modification time recorded before and after, identical in both.

2. **Given** the same test, **When** a writer that resolves its path from the cwd
   default instead of the session store is introduced in a control, **Then** the
   control fails and names the offending path, and the diff contains the pasted
   failure output.

3. **Given** a checkout with no runtime root directory at all, **When** the test
   runs, **Then** it passes without creating one, and the diff contains pasted
   output showing the directory absent after the run.

4. **Given** the whole test module, **When** the diff is read, **Then** no
   assertion in it requires the non-existence of a path that the production
   defaults name, and every remaining non-existence assertion targets either a
   pytest tmp path or a deliberately impossible path.

---

### User Story 2 - The findings ledger is addressed through the resolver (Priority: P1)

`040-manifest-rename/US2` introduced `resolve_factory_root()` at
`factory/workgraph/worktree.py:135` and routed the runtime-root readers through it.
The doctor's were missed. Four sites still carry the literal `.factory` as a path
default: `factory/cli/doctor.py:41`, `factory/doctor/cli.py:40`, and
`factory/doctor/probes.py:133` and `:135`.

The consequence is quiet and expensive. The moment an operator migrates the runtime
root to `.ergane/`, the doctor creates a fresh empty ledger at the legacy path and
every recurrence count resets to one. Recurrence is what decides constitutional
promotion — a finding that has bitten three times is a different object from one
that has bitten once — so losing the counts loses the only evidence that makes
"this has recurred" a fact rather than a recollection.

**Why this priority**: It must land before US3. Today the `NameError` in US3 is the
only thing preventing anyone from migrating; fixing US3 first arms this one.

**Independent Test**: Migrate a scratch repo's runtime root and confirm the
recurrence counts survive.

**Acceptance Scenarios**:

1. **Given** a repo whose runtime root is `.ergane/` containing a `doctor.db` with a
   finding at recurrence three, **When** `ergane findings list` runs with no `--db`
   flag, **Then** it reports that finding at recurrence three, proven by a committed
   test that constructs both directories and asserts on the output.

2. **Given** a repo whose only runtime root is the legacy `.factory/`, **When** the
   same command runs, **Then** it reads `.factory/doctor.db` and emits the one-time
   legacy deprecation, proven by a committed test.

3. **Given** the diff, **When** `factory/cli/doctor.py`, `factory/doctor/cli.py` and
   `factory/doctor/probes.py` are read, **Then** none of them contains a path
   default built from the literal `.factory`, and each derives its path from
   `resolve_factory_root()`.

4. **Given** an explicit `--db` argument, **When** any doctor command runs, **Then**
   the argument still wins over the resolver, proven by a committed test.

5. **Given** a repo in the split state this one is in right now — `.ergane/`
   present but holding no ledger, `.factory/doctor.db` present and populated —
   **When** any doctor command runs with no `--db`, **Then** it MUST NOT silently
   open an empty ledger at the resolved root: it either reads the populated legacy
   ledger or refuses naming both paths. Proven by a committed test that constructs
   exactly that layout and asserts the recurrence count is preserved or the refusal
   is raised.

---

### User Story 3 - `ergane repo migrate-runtime-root` can start (Priority: P1)

`factory/cli/repo.py:51-52` calls `os.environ.get(...)`. The module imports
`argparse`, `asyncio`, `shutil`, `dataclasses`, `pathlib` and `typing`. It does not
import `os`. `_open_client` is the default of the `_temporal_client_factory` seam at
`:63`, and the running-epic refusal calls it through `_running_epic_ids()` at
`:160` — so the only real path through the verb dies before it does anything:

```
ergane: unexpected error (name 'os' is not defined)
```

The suite was green at 2265 passed when this shipped, because every test rebinds
the seam and none of them ever enters the function the seam defaults to. The
one-line fix is not the story. **The story is the test that would have caught it**,
and the general shape of that test is what makes this worth a story rather than a
patch: a seam introduced to make a gather testable must have at least one test that
executes its real default.

**Why this priority**: 040 shipped a command that cannot start, and the runtime root
cannot be migrated until it can. Depends on US2 — see that story.

**Independent Test**: From a scratch repo containing only a legacy runtime root,
with no environment overrides, run the verb and watch it reach its refusal or its
dry run rather than a `NameError`.

**Acceptance Scenarios**:

1. **Given** `TEMPORAL_ADDRESS` pointing at a closed port and
   `_temporal_client_factory` left at its default, **When** `_running_epic_ids()`
   is called, **Then** it raises `OperatorError` naming the unreachable address and
   carrying `EXIT_TRANSPORT`, not `NameError`, proven by a committed test that does
   not rebind the seam.

2. **Given** a scratch repo holding only a legacy runtime root and a reachable
   Temporal with no epics open, **When** the verb runs without `--yes`, **Then** it
   prints the dry-run line, and the diff contains that pasted output.

3. **Given** the diff, **When** `factory/cli/repo.py` is read, **Then** every global
   name it references at module or function scope is bound by an import or a
   definition in that file, proven by a committed test that walks the module's AST
   rather than grepping it.

---

### User Story 4 - The migration refusal names the variable the operator set (Priority: P2)

With `ERGANE_ROOT` set and `FACTORY_ROOT` unset, `factory/cli/repo.py:152` prints:

```
FACTORY_ROOT is set to <path>; migration only moves the default legacy root
when no override is present
```

It names the variable the operator did not set, in the one epic whose entire
purpose was moving operators off that name. `factory/env.py` already knows which
name won; `resolve_factory_root()` currently discards that knowledge, returning
only the path and a `RuntimeRootChoice` that describes the directory rather than
the variable.

**Why this priority**: Cosmetic against the other three, and it touches the same
file and adjacent lines as US3, so it follows it rather than racing it.

**Independent Test**: Set each variable in turn and read the refusal.

**Acceptance Scenarios**:

1. **Given** `ERGANE_ROOT` set to a path outside the default roots and
   `FACTORY_ROOT` unset, **When** the verb runs, **Then** the refusal names
   `ERGANE_ROOT` and quotes its value, proven by a committed test.

2. **Given** `FACTORY_ROOT` set and `ERGANE_ROOT` unset, **When** the verb runs,
   **Then** the refusal names `FACTORY_ROOT`, proven by a committed test.

3. **Given** both set to different values, **When** the verb runs, **Then** the
   refusal names `ERGANE_ROOT` and its value — matching the precedence
   `factory/env.py:resolve_env_path` already implements — proven by a committed
   test.

---

## Functional Requirements

- **FR-001**: A test that guards against writes leaking into a production default
  path MUST determine whether *this test* created or modified that path, and MUST
  NOT assert the path's non-existence.
- **FR-002**: Every reader and writer of the findings ledger MUST derive its path
  from `resolve_factory_root()`, and MUST NOT carry a path default built from a
  runtime-root directory literal. An explicit `--db` argument MUST still win.
- **FR-006**: Where a resolver would point a store at a location holding no data
  while a populated store exists at the location previously used, the system MUST
  NOT open the empty one silently. It either follows the data or refuses naming
  both paths.
- **FR-003**: `ergane repo migrate-runtime-root` MUST reach its refusal, dry run or
  move rather than raising `NameError`.
- **FR-004**: Where a seam exists so tests can substitute a collaborator, at least
  one test MUST exercise the seam's real default without rebinding it.
- **FR-005**: An error that names an environment variable MUST name the variable
  the operator actually set, following the precedence in
  `factory/env.py:resolve_env_path`.

## Success Criteria

- **SC-001**: The full suite passes on a host whose runtime root already contains
  populated stores, with those stores byte-identical before and after.
- **SC-002**: A finding at recurrence three survives a runtime-root migration with
  its count intact.
- **SC-003**: `ergane repo migrate-runtime-root` completes a dry run from a scratch
  repo containing only a legacy root.
- **SC-004**: **Control.** With FR-001's fix reverted and the stores populated, the
  original assertion fails and its message names the live store — establishing that
  the fix changed the outcome rather than the suite having been green anyway.

## Out of Scope

- Relocating the three engine stores out of the target repository. Argued for on
  multi-repo grounds, not settled, and deliberately separable once US1 lands.
- Off-host replication of the stores. The nightly snapshot already covers host loss
  and proved it on 2026-08-14.
- Anything that stops an agent reaching the runtime root — that is `011-agent-sandbox`.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001]
US2:
  depends_on: []
  implements: [FR-002, FR-006]
US3:
  depends_on: [US2]
  implements: [FR-003, FR-004]
US4:
  depends_on: [US3]
  implements: [FR-005]
```
