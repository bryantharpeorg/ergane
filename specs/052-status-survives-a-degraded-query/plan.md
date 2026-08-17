# Implementation Plan: 052-status-survives-a-degraded-query

Refined against the tree at `cfb9553` on 2026-08-16. Every anchor below was read
by hand at that commit and the defect re-measured the same minute (`ergane status
specs` → exit 1). Where an anchor moves before you dispatch, re-read it: five
specs this week cited a line that had drifted, and one cited a file that no
longer existed.

## What already exists, and where

| Thing | Where | What it does today |
| --- | --- | --- |
| The dying query | `factory/cli/status.py:432` | Queries the live roadmap workflow with `roadmap_status` |
| The fallback that never fires | `factory/cli/status.py:435` | `except RPCError:` with a comment describing exactly this case |
| The other two same-shape guards | `factory/cli/status.py:239`, `:474` | Same bet, same client, not proven dead |
| The import | `factory/cli/status.py:68` | `from temporalio.service import RPCError` — the only guarded type in the file |
| The record | `factory/roadmap/workflow.py:366` | `max_concurrent_nodes: int`, no default |
| The precedent beside it | `factory/roadmap/workflow.py:269` | `paused: bool = False` — the shape US2 wants everywhere |

`factory/cli/status.py` is 735 lines.

## The fact that decides US1

```
issubclass(WorkflowQueryFailedError, RPCError)  ->  False
WorkflowQueryFailedError.__mro__ = [WorkflowQueryFailedError, TemporalError, ...]
```

Run that yourself before you write anything. It is the whole diagnosis, and it
takes ten seconds to confirm or refute.

## Traps

1. **Do not fix this with `except Exception`.** FR-004 forbids it and US1-S4
   tests for it. A bare catch around a query converts every future defect into a
   blank section, which is the same class of silence this spec exists to end —
   the command would stop dying and start lying.

2. **Raise the type the client raises.** A test that defines its own
   `class FakeQueryFailed(RPCError)` and raises that will pass against the
   *broken* code, because it inherits from the class the broken code catches.
   That is a test that cannot fail. Import `WorkflowQueryFailedError` from
   `temporalio.client` and raise it. This is the single most likely way to ship
   a green suite over an unfixed defect.

3. **The message names `RoadmapStatus`; the bug is the guard.** Repairing only
   the missing default makes *this* query answer and leaves the guard dead for
   the next field. US2 exists for the default, US1 for the guard, and they are
   separate stories because fixing either alone is a defensible-looking dead end.

4. **US2's sweep must be able to fail.** A parametrized sweep over an empty
   record list passes forever without asserting anything;
   `tests/test_final_sweep.py:644` is the precedent and exists because that
   already happened here. Assert the list is non-empty **and** names
   `RoadmapStatus`. Run the point-at-nothing mutation **first**, not last: if the
   sweep stays green pointed at a module that does not exist, every other mutant
   is meaningless.

5. **SC-001 is a claim about a running deployment**, so it needs a committed
   transcript. The judge sees only your diff and the criteria — no base tree, no
   commit message, no terminal (constitution VIII / D-037).

6. **Do not terminate or migrate the live roadmap workflow to make the transcript
   nicer.** It is the evidence. It is also on the operator's production namespace
   and three leaked test workflows were terminated there tonight; that namespace
   has had enough traffic from tests for one day. Out of Scope says so.

7. **Measure exit codes without a pipe.** `cmd | head; echo $?` reports the
   pipe's status. SC-001 is an exit code, so a piped measurement would measure
   the wrong thing entirely. Capture `rc=$?` before any pipe. That error produced
   a false reading of `ergane install --verify` earlier today.

8. **Purge `__pycache__` between mutants**, or run under
   `PYTHONDONTWRITEBYTECODE=1`. CPython validates a cached `.pyc` on
   `(mtime-in-whole-seconds, size)` only, so two same-size mutants inside one
   wall-clock second make the second run execute the *first* mutant's bytecode.
   Swapping one exception class for another preserves size almost exactly, so
   this trap is aimed directly at US1.

9. **Quote `passed` and `skipped`, never the warning count.** A warm cache
   suppresses compile-time warnings. Baseline skips are 44; a new skip is a
   hidden test you must declare.

## Sizing

Small. US1 is an import, a catch clause, and a report line, plus the tests that
prove the catch is right. US2 is a default and a sweep. The 61,440-byte diff
bound (`factory/verify/diffbounds.py`, import `DIFF_INPUT_LIMIT` rather than
quoting it) should not bind on either; if it does, you have taken on more than
the story asked for.

## Verification the operator will run, independent of the gate

`ergane status specs` against the live control plane, whose roadmap workflow
refuses the query today. A green suite is evidence, not proof — this defect
shipped past a fully green suite, and was found by running the thing.
