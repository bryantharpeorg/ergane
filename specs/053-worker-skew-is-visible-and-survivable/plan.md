# Implementation Plan: 053-worker-skew-is-visible-and-survivable

Refined against the tree at `0c79d6f` on 2026-08-17 ~4:10 PM CT. Every anchor
below was read by hand at that commit and the defect re-measured the same minute
(`ergane build status 023-composable-verification` → exit 1). Where an anchor has
moved before you dispatch, re-read it — `build.py` is an actively edited file and
several specs this month cited a line that had drifted.

## What already exists, and where

| Thing | Where | What it does today |
| --- | --- | --- |
| The raise | `factory/workgraph/workflow.py:585` | `provenance=record.provenance` inside the `epic_status` query handler — **this runs in the worker** |
| The passthrough boundary | `factory/workgraph/workflow.py:119` | `with workflow.unsafe.imports_passed_through():` — `NodeRecord` is imported at `:225`, inside it |
| The field | `factory/workgraph/models.py:287` | `provenance: str | None = None` — it already has a default |
| The dying query | `factory/cli/nouns/build.py:468` | `await handle.query("epic_status")` — the only real workflow query in the module |
| The guard that never fires | `factory/cli/nouns/build.py:469` | `except RPCError as error:` |
| The other seven same-shape guards | `build.py:285`, `:492`, `:616`, `:636`, `:717`, `:758`, `:917` | Same bet, same client, different call types, not proven dead |
| What `build.py` imports today | `build.py:26` | `from temporalio.service import RPCError, RPCStatusCode` — no query-failure class anywhere in the file |
| The tolerant reader | `build.py:346` | `node.get("provenance")` — a `Mapping.get`; **it is not the bug** |
| The pattern to copy | `factory/cli/status.py:140`, `:147` | `TRANSPORT_FAILED` and `QUERY_REFUSED`, with the reasoning that produced them |
| Its imports | `status.py:72-73` | `WorkflowQueryFailedError`, `WorkflowQueryRejectedError`, `RPCError` |
| The sweep to generalize | `tests/test_ergane_status.py:1494` | `EXPECTED_GUARDS`, fed by `_status_source_tree()` reading one `__file__` |
| Its reusable half | `tests/test_ergane_status.py:1505` | `_awaiting_functions()` — already module-agnostic; only its input is narrow |
| Where the worker boots | `factory/worker.py:201` | `build_worker(client)`, 242 lines — US3's capture point |

`factory/cli/nouns/build.py` is 1,100 lines. `tests/test_ergane_status.py` is
1,731.

## The fact that decides US1

```
issubclass(WorkflowQueryFailedError, RPCError)  ->  False
WorkflowQueryFailedError.__mro__ = [WorkflowQueryFailedError, TemporalError, ...]
```

Run it yourself before writing anything. It is the whole diagnosis of the guard,
and it takes ten seconds. 052 established it for `status.py`; this spec applies
it one module over.

## Traps

1. **The finding's own notes are wrong, and the spec says so. Do not build from
   them.** `interpreter/build-status-crashes-on-a-closed-epic-noderecord` says in
   its first occurrence that "the CLI reads `.provenance` unconditionally". It
   does not — `build.py:346` uses `Mapping.get`. The raise is in the **worker**,
   at `workflow.py:585`. A repair aimed at the CLI's read will change a line that
   was never wrong and leave the verb dying. The proof of where it raises is that
   `ergane status` caught it with `QUERY_REFUSED`, a class that by definition
   means the workflow refused.

2. **Do not give `provenance` a default. It has one.** `models.py:287` is
   `provenance: str | None = None`, which already satisfies 052's FR-006. This
   failure is on the *import* path, not the deserialization path: the class
   object in the worker's memory never declared the attribute, so there is no
   default to consult. A diff that adds defaults will pass its own tests, look
   like a fix, and change nothing. This is the single most likely way to ship a
   green suite over an unfixed defect on this story.

3. **Do not restart the worker — not to reproduce, not to verify, not to make a
   test pass.** `systemctl --user restart ergane-worker.service` kills every
   in-flight attempt on the machine, which on the day this spec was written meant
   two live epics. Reproduce the skew *synthetically*: construct the refusal the
   worker would send, or a record object lacking the attribute, inside the test.
   Touching a live user unit is outside any node's worktree and outside this
   story.

4. **Reads degrade, writes die — and the split is per-site, not per-module.**
   `build status` is a read: a partial answer beats none. `build start`, `kill`,
   `answer`, `reset` and `resolve` mutate, and a write that proceeds on a
   half-read query is worse than one that refuses (FR-004, US1-S3). A single
   module-wide catch is the wrong shape for the reason `status.py:133` gives:
   *"the command would stop dying and start lying."*

5. **Do not fix this with `except Exception`.** FR-005 forbids it and US1-S4
   tests for it. Same reason as trap 4, stated as a rule.

6. **Raise the type the client raises.** A test that defines
   `class FakeQueryFailed(RPCError)` and raises that passes against the *broken*
   code, because it inherits from the class the broken code catches — a test
   structurally unable to fail. Import `WorkflowQueryFailedError` from
   `temporalio.client`. Four tests in this repository have already been found in
   exactly that state.

7. **US2's sweep must be able to fail.** A discovery sweep that finds no modules
   passes forever while asserting nothing. Assert the discovered set is non-empty
   **and** names both `factory/cli/status.py` and `factory/cli/nouns/build.py`
   (FR-007). Run the point-at-nothing mutation **first**, not last: if the sweep
   stays green pointed at a directory that does not exist, every other mutant is
   meaningless. `tests/test_final_sweep.py:644` is the precedent, and it exists
   because this already happened here.

8. **US2 may not weaken 052 to make room for itself.** `EXPECTED_GUARDS`'
   existing entries for `collect_floor`, `_disposition` and `_running_epics` are
   load-bearing and must still hold, unchanged, after generalization (US2-S4).
   Widening a test's scope by loosening its assertions is a net loss.

9. **US3's revision must be captured at worker start, not per call.** A
   `git rev-parse` executed when the query is answered reports the *tree's*
   revision, which is the CLI's — the two would always match and the warning
   would never fire. Capture once at `factory/worker.py:201` and carry it
   (US3-S4). This is the trap that makes US3 either work or be decorative.

10. **A warning that is always on is not a warning** (US3-S2). Same-revision runs
    must be byte-identical to today's output, everywhere, and SC-005 wants a
    committed before/after pair proving it.

11. **Measure exit codes without a pipe.** `cmd | head; echo $?` reports the
    pipe's status, and SC-001 is an exit code. Capture `rc=$?` before any pipe.

12. **Purge `__pycache__` between mutants**, or run with
    `PYTHONDONTWRITEBYTECODE=1`. CPython validates a cached `.pyc` on
    `(mtime-in-whole-seconds, size)` only, so two same-size mutants inside one
    wall-clock second run the first mutant's bytecode. Swapping one exception
    class for another preserves size almost exactly, which aims this trap
    directly at US1.

13. **Quote `passed` and `skipped`, never the warning count.** A warm cache
    suppresses compile-time warnings, so warning counts are not comparable
    between runs.

14. **SC-001 and SC-005 are claims about a running deployment**, so they need
    committed transcripts. The judge sees only your diff and the criteria — no
    base tree, no commit message, no terminal (constitution VIII / D-037).

## Dispatch condition

**US3 edits `factory/worker.py`, which the running worker imports.** Land it when
the floor is otherwise quiet, or accept that the change reaches the running
worker only at its next restart — which is the same skew this spec is about, and
would be an unusually pointed way to learn the lesson twice.

US2 and US3 both merge-edge to US1 rather than running beside it, because all
three touch `build.py` or the tests that read it. `depends_on_merged` models what
a story needs to *exist*; here it is also being used to keep two agents out of
one file.

## Sizing

Small to medium. US1 is two imports, a per-site guard decision, and a report
line, plus the tests that prove each guard is right. US2 is a discovery function
and an anti-vacuity assertion over machinery that already exists. US3 is the
largest: a value captured at worker start, carried through the query answer, and
compared at the CLI — with the whole of US3-S3 being about the case where it is
absent.

The 65,536-byte diff bound (`factory/verify/diffbounds.py`, import
`DIFF_INPUT_LIMIT` rather than quoting it) should not bind on any of the three.
If it does on US1, you have taken on more than the story asked for.

## Verification the operator will run, independent of the gate

`ergane build status <epic>` against a live epic whose worker predates a field in
its own query answer — which is the state of this machine as the spec is written,
and will stop being true the moment the worker restarts. Capture the transcript
before that happens.

A green suite is evidence, not proof. This defect shipped past a fully green
suite, in a repository that had already fixed the same defect class one module
over, with a test written specifically to prevent it.
