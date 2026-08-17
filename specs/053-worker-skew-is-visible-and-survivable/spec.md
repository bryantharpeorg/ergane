---
state: draft
# specs_root: specs
# target_repo: /home/admin/code/ergane
# Scaffolded by `ergane findings promote` from
# `interpreter/build-status-crashes-on-a-closed-epic-noderecord` (warning,
# occurrence 2) and rewritten by an operator session on 2026-08-17 ~4:05 PM CT
# against the tree at 0c79d6f, with two live epics dispatched and unwatchable.
#
# The finding's key and its first occurrence's notes are both WRONG, and the
# spec says so below rather than inheriting them. "Closed epic" was the first
# guess; the second occurrence corrected it to a worker/CLI skew; reading the
# code corrected it again, to which side of the Temporal sandbox boundary a
# module sits on. Three readings of one error message, and only the third
# survives contact with `factory/workgraph/workflow.py:585`. Do not rename the
# key -- it is the ledger's identity for this defect and its history is the
# point.
#
# This is 052's sibling. 052's own Out of Scope closes with "Every other
# command's guards. This spec fixes factory/cli/status.py." This is that work,
# plus the mechanism 052 could not have seen because its defect never reached
# the sandbox.
#
# Numbered 053: 052 status-survives-a-degraded-query is the immediate
# predecessor and this spec is its continuation.
---

# Feature Specification: A half-stale worker is visible, and does not kill a read

**Created**: 2026-08-17

## The defect, measured

Two epics dispatched at 20:12:47Z. Eleven minutes later, on a fully green suite:

```
$ ergane build status 023-composable-verification
ergane: unexpected error ('NodeRecord' object has no attribute 'provenance');
re-run with --debug for the traceback
[exit 1]

$ ergane status specs
epics
  023-composable-verification  unavailable ('NodeRecord' object has no attribute 'provenance')
  042-supervised-services      unavailable ('NodeRecord' object has no attribute 'provenance')
[exit 0]
```

Same cause, two outcomes. **`ergane status` is behaving correctly** — that is
052 working exactly as designed, and this spec must not change it. `ergane build
status`, the verb `CLAUDE.md` names as the answer to "what is one epic doing
right now", cannot start.

## The error message is wrong about who raised it

The finding's first occurrence recorded that "the CLI reads `.provenance`
unconditionally". That is false, and a fix built on it would touch the wrong
file. `factory/cli/nouns/build.py:346` reads the node as a mapping:

```python
        provenance = node.get("provenance")
```

`Mapping.get` cannot raise `AttributeError`. The raise is in the **worker**, at
`factory/workgraph/workflow.py:585`, inside the `epic_status` query handler:

```python
                    provenance=record.provenance,
```

The strongest evidence is `ergane status`'s own behaviour. It degraded through
`QUERY_REFUSED` (`factory/cli/status.py:147`), whose two members are
`WorkflowQueryFailedError` and `WorkflowQueryRejectedError`. That class means
one specific thing: *the server accepted the query and the workflow refused it*.
The command that survived proves where the exception was born.

## Why the worker is half-stale, which is worse than stale

`ergane-worker.service` entered active at 17:31:46Z. `664ac8a` — 035-US2, which
added `NodeRecord.provenance` at `factory/workgraph/models.py:287` — landed at
18:47:10Z. The two epics started at 20:12:47Z, on a worker that booted before
the field existed.

A wholly stale worker would be fine: old workflow code never reads a field old
records do not have. What happened instead is that the two halves came from
different days:

- `factory/workgraph/workflow.py` is **re-imported from disk by the Temporal
  sandbox** when a workflow starts. The epics dispatched at 20:12Z got the
  post-035 source, which reads `record.provenance`.
- `factory/workgraph/models.py` is **passed through** — `workflow.py:119` opens
  `with workflow.unsafe.imports_passed_through():` and `NodeRecord` is imported
  at `:225`, inside that block. Passed-through modules stay as the worker
  imported them at boot, so `NodeRecord` is the 17:31Z class, without the field.

New code, old class, same process. Neither half is wrong on its own, and the
boundary that decided which is which is invisible from either side.

## Why 052's defense does not cover this, and could not

052's US2 requires that "every field of a record that crosses the Temporal
payload boundary MUST have a default" (FR-006), swept by a test (FR-007).

**That requirement is satisfied here.** `models.py:287` reads
`provenance: str | None = None`. A payload missing the key reconstructs
perfectly.

The default protects *deserialization*. This failure is on the *import* path,
where no default exists to consult, because the class object in memory never had
the attribute declared. A spec that responds to this by adding more defaults
will pass its own tests and change nothing.

## Why 052 stopped one module short

Two reasons, both structural rather than careless:

1. 052's Out of Scope names it: *"Every other command's guards. This spec fixes
   `factory/cli/status.py`."*
2. The sweep that enforces the guards — `EXPECTED_GUARDS` at
   `tests/test_ergane_status.py:1494` — parses exactly one file, via
   `_status_source_tree()` reading `status_module.__file__`. It is a good test
   pointed at one module, so `factory/cli/nouns/build.py` gaining a Temporal
   call is invisible to it.

`build.py` carries **eight** `except RPCError` clauses — `:285`, `:469`, `:492`,
`:616`, `:636`, `:717`, `:758`, `:917` — and mentions
`WorkflowQueryFailedError` nowhere. One of them, `_query_status:469`, guards the
only true workflow query in the module and is **proven dead** by the transcript
above. The other seven are the same bet against the same client on different
call types, exactly as 052 found three sites and could prove one.

## User Scenarios & Testing

### User Story 1 - A refused query degrades `build status` instead of killing it (Priority: P1)

As an operator watching a running epic, `ergane build status` reports what it
can when the workflow refuses the `epic_status` query, rather than exiting 1
with "unexpected error".

**Why this priority**: it is the whole defect, and it is the verb for the one
question — *what is this epic doing right now* — that has no other answer short
of reading Temporal's Web UI and the node worktree by hand, which is what the
operator did on 2026-08-17.

The story's one structural trap is that **not every site in this file should
degrade.** `build status` is a read: a partial answer beats no answer.
`build start`, `build kill`, `build answer`, `build reset` and `build resolve`
are writes, and a write that proceeds on a half-read query is worse than one
that refuses. The repair is per-site and must be argued per-site; a module-wide
`except` is the wrong shape here for the same reason 052 gave at
`status.py:133` — *"the command would stop dying and start lying."*

**Independent Test**: make the `epic_status` query raise
`WorkflowQueryFailedError` — the type `temporalio` actually raises — and confirm
`ergane build status` completes, exits 0, and names the refusal.

**Acceptance Scenarios**:

1. **Given** an `epic_status` query that raises `WorkflowQueryFailedError`,
   **When** `ergane build status <epic>` runs, **Then** it completes, exits 0,
   and reports the epic's state as unavailable with the refusal's own message —
   proven by a committed test that raises **the type the client raises**, not a
   stand-in that inherits from whatever the catch names.
2. **Given** an `epic_status` query that raises `RPCError`, **When**
   `ergane build status` runs, **Then** its behaviour is byte-identical to
   today's, including the `NOT_FOUND` path that reports "no epic is running
   here" — proven by a committed test. This repair may not change the transport
   path.
3. **Given** a signal-sending verb whose call is refused, **When** it runs,
   **Then** it still exits non-zero — proven by a committed test naming at least
   one write verb. A write must not learn to shrug.
4. **Given** a query that raises neither guarded class, **When**
   `ergane build status` runs, **Then** the exception still escapes. This story
   MUST NOT introduce a bare `except Exception` around a Temporal call.

---

### User Story 2 - The guard sweep covers every module that awaits Temporal (Priority: P2)

As this repository, the test that enforces which failure classes a Temporal call
site guards reads every CLI module that awaits Temporal, not one chosen by name.

**Why this priority**: P2 because US1 alone restores the verb. This is what stops
the third module doing it again — and there will be a third, because
`_awaiting_functions()` already works on any module and only the file it is
pointed at is narrow.

**Independent Test**: point the generalized sweep at a module with a deliberately
wrong guard and confirm it fails; point it at the repaired tree and confirm it
passes and reports a non-empty module set including `build.py` by name.

**Acceptance Scenarios**:

1. **Given** the CLI package, **When** the sweep runs, **Then** it discovers
   every module containing a function that awaits Temporal, rather than reading
   a hardcoded module, and asserts each such function's guard set — proven by a
   committed test.
2. **Given** the discovered module set, **When** the sweep runs, **Then** it
   asserts the set is non-empty and contains both `factory/cli/status.py` and
   `factory/cli/nouns/build.py` by name — an anti-vacuity assertion, because a
   discovery sweep that finds nothing passes silently.
3. **Given** a module whose guard names a class the client cannot raise, **When**
   the sweep runs, **Then** it fails and names the module, the function and the
   class — proven by a committed negative case.
4. **Given** 052's existing assertions about `factory/cli/status.py`, **When**
   the generalized sweep runs, **Then** they still hold unchanged. This story
   may not weaken 052 to make room for itself.

---

### User Story 3 - The operator can see that the worker is not the tree (Priority: P2)

As an operator, when a read verb is degraded because the worker is running
different code than my CLI, the command tells me that, rather than handing me a
Python attribute error to interpret.

**Why this priority**: P2 because US1 makes the verb survive. This is what makes
the *cause* legible, and it is the half that pays: any future landing that adds
a field to a workflow-visible record reproduces this defect, and the symptom
will again look like a data problem rather than a deployment one. On
2026-08-17 the first two diagnoses were both wrong for exactly that reason.

The remedy this story does **not** take is removing `models.py` from the
passthrough block. That would close the skew at its source and it is out of
scope here — passthrough exists so dataclass identity survives the activity
boundary, and changing it is a measurement, not a patch. See Out of Scope.

**Independent Test**: run a read verb against a worker whose recorded revision
differs from the CLI's and confirm the output names both revisions and the
remedy.

**Acceptance Scenarios**:

1. **Given** a worker that recorded revision A at boot and a CLI at revision B,
   **When** a read verb reports a refused query, **Then** its message names both
   revisions and states that the worker is running different code — proven by a
   committed test.
2. **Given** a worker and CLI at the same revision, **When** any verb runs,
   **Then** no skew notice appears anywhere — proven by a committed test. A
   warning that is always on is not a warning.
3. **Given** a worker that recorded no revision at all — one built before this
   story, or from a source tree that is not a git checkout — **When** a read verb
   runs, **Then** it degrades to today's behaviour without raising, and says the
   worker's revision is unknown rather than guessing.
4. **Given** the diff, **When** the revision is captured, **Then** it is read
   once at worker start and carried in the query answer, not recomputed per
   call — proven by a committed test, because a revision the worker re-reads
   from disk would report the *tree's* revision and defeat the whole story.

## Functional Requirements

- **FR-001**: `ergane build status` MUST complete and exit 0 when the
  `epic_status` query is refused by the workflow.
- **FR-002**: The refusal MUST be reported in place, naming the cause, rather
  than replacing the whole report.
- **FR-003**: Each guarded Temporal call site in `factory/cli/nouns/build.py`
  MUST catch the classes the client can actually raise for that call, and MUST
  NOT catch a class the client cannot raise there.
- **FR-004**: A verb that sends a signal or otherwise mutates state MUST still
  exit non-zero when its call fails.
- **FR-005**: This spec MUST NOT introduce a bare `except Exception` around a
  Temporal call.
- **FR-006**: Behaviour on `RPCError`, including the `NOT_FOUND` "no epic is
  running here" path, MUST be unchanged.
- **FR-007**: The guard sweep MUST discover the modules it checks rather than
  naming one, and MUST assert the discovered set is non-empty and contains
  `factory/cli/status.py` and `factory/cli/nouns/build.py`.
- **FR-008**: The worker MUST record the revision of the code it imported, once,
  at start.
- **FR-009**: A read verb reporting a refused query MUST name the worker's
  revision and the CLI's when they differ, and MUST say nothing when they match.
- **FR-010**: An absent worker revision MUST degrade to today's behaviour and be
  reported as unknown, never inferred.

## Success Criteria

- **SC-001**: `ergane build status <epic>` exits 0 against a workflow that
  refuses `epic_status`. Evidence is a committed transcript, because this is a
  claim about a running deployment and the judge reads only the diff.
- **SC-002**: The count of Temporal call sites in `factory/cli/nouns/build.py`
  guarded only by a class the client cannot raise there is zero, asserted by a
  test rather than by reading.
- **SC-003**: The guard sweep's module set is derived, non-empty, and names both
  modules — asserted, not documented.
- **SC-004**: No test raises a stand-in exception where the real client's type is
  available.
- **SC-005**: With worker and CLI at one revision, the full output of every verb
  this spec touches is byte-identical to today's except for the degraded path —
  evidence is a committed before/after transcript pair.

## Out of Scope

- **Taking `factory/workgraph/models.py` out of the passthrough block.** It
  would close the skew at its source, and that is precisely why it is not a
  side-effect of a status-verb repair: passthrough is there so dataclass
  identity survives the activity boundary, and the blast radius is every payload
  the factory converts. If it is worth doing it is worth its own spec, with a
  measurement first.
- **Restarting the worker.** The immediate unblock is
  `systemctl --user restart ergane-worker.service` between attempts, and it is an
  operator act. This spec exists because the operator should not have needed to
  diagnose it first.
- **The `provenance` field itself.** 035 shipped it correctly, with a default,
  satisfying 052's FR-006. It is the messenger.
- **`ergane status`.** It already survives this. Changing it is a regression
  risk with no defect behind it, and 052's assertions about it are load-bearing
  for US2.
- **Renaming the finding key.** `interpreter/build-status-crashes-on-a-closed-
  epic-noderecord` is wrong on its face and is the ledger's identity for this
  defect. Its three-reading history is evidence, not clutter.

## Work Graph

A fan-out behind one story. US2 asserts the guard decisions US1 makes, and US3
renders its notice on the degraded path US1 creates, so neither can be built
against a tree without US1 in it.

Both edges are **merge** edges rather than pass edges, for two reasons. The
first is correctness: a pass edge would let a node build against a base that
does not contain the guards it is extending. The second is contention — all
three stories reach `factory/cli/nouns/build.py` or the tests that read it, and
concurrent worktrees on one module is a collision this repository has already
paid for more than once.

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-007]
US3:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-008, FR-009, FR-010]
```
