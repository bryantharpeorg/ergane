# 084-US3 evidence — SC-009, SC-010, SC-011

Every block below is pasted verbatim from a run in this worktree on 2026-08-22.
The driver is built on the helpers this story committed —
`tests/test_a_gate_may_declare_that_it_writes.py`'s `_manifest`, `WRITING_COMMAND`
and `WRITTEN_PATH`, over US1's `_node_worktree` and `StubGateExecutor` — so what
produced the evidence is the same fixture code the tests run on:

```python
from tests.test_a_gate_that_writes_does_not_pass import (
    IGNORED_BY_THE_REAL_GATE, StubGateExecutor, _node_worktree)
from tests.test_a_gate_may_declare_that_it_writes import (
    WRITING_COMMAND, WRITTEN_PATH, _manifest)

worktree = _node_worktree(scratch(), ignore=IGNORED_BY_THE_REAL_GATE)
manifest = _manifest(worktree, {"test": WRITING_COMMAND}, writes={"test": True})
results  = run_gates(worktree, manifest_path=manifest, executor=SubprocessGateExecutor())
```

Each result line is `name / status / exit_code / worktree_writes / writes_declared`.

## The suite this story added

```
test_a_declared_gate_that_writes_still_passes PASSED [  8%]
test_a_declared_gate_still_records_what_it_wrote PASSED [ 16%]
test_both_gate_list_runners_honour_the_declaration[_run_gate_list] PASSED [ 25%]
test_both_gate_list_runners_honour_the_declaration[_run_gate_list_from_config] PASSED [ 33%]
test_the_candidate_protocol_carries_the_declaration PASSED [ 41%]
test_a_writes_entry_for_an_unknown_gate_is_refused PASSED [ 50%]
test_a_non_boolean_writes_value_is_refused PASSED [ 58%]
test_a_manifest_without_the_key_parses_exactly_as_today PASSED [ 66%]
test_declaring_false_is_not_a_declaration PASSED [ 75%]
test_a_declaration_does_not_excuse_an_unreadable_snapshot PASSED [ 83%]
test_writes_declared_round_trips_through_the_evidence_store PASSED [ 91%]
test_a_row_written_before_this_field_reads_back_as_undeclared PASSED [100%]
============================== 12 passed in 0.70s ==============================
```

And this repository's whole suite, with the manifest key added to the parser and
therefore to `ergane init`'s interview:

```
4304 passed, 52 skipped, 6 warnings in 337.12s (0:05:37)
```

## SC-009 — the declared gate writes, exits 0, and the run passes

The gate is `echo generated > generated.txt`, and `generated.txt` is *not*
ignored by the fixture repo: without the declaration this is US1's refusal
exactly.

```
--- the fixture manifest ---
version: 1
runtime: bwrap
gates:
  test: 'echo generated > generated.txt'
writes:
  test: true
--- the gate really wrote ---
generated.txt: 'generated\n'
--- the result ---
test / PASS / exit=0 / worktree_writes=('generated.txt',) / writes_declared=True
gates_passed(results) = True
```

The paths are **not** omitted because they were declared — they are recorded and
flagged. This is the same row through both halves of the evidence codec, which
is the surface the retry prompt and the operator's notification are built from:

```
{
  "name": "test",
  "command": "echo generated > generated.txt",
  "status": "PASS",
  "exit_code": 0,
  "duration_s": 0.0016621819813735783,
  "output_tail": "",
  "concurrent_gates": 0,
  "worktree_writes": [
    "generated.txt"
  ],
  "writes_declared": true
}
```

### The controls: absent and `false` are both "nothing declared"

The same gate writing the same path, changing only the manifest:

```
no writes: key at all    -> test / DIRTIED_WORKTREE / exit=0 / worktree_writes=('generated.txt',) / writes_declared=False
writes: {test: false}    -> test / DIRTIED_WORKTREE / exit=0 / worktree_writes=('generated.txt',) / writes_declared=False
```

So the key is not a switch with one position: naming a gate at all does not turn
US1's refusal off, and every target repo's committed manifest — none of which
has this key — keeps the behaviour it had.

## SC-010 — a `writes:` entry naming a gate the manifest does not declare

```
--- the manifest ---
version: 1
runtime: bwrap
gates:
  test: 'uv run pytest -q'
writes:
  typecheck: true
--- the parser's own message ---
FactoryConfigError: ergane.yaml: [writes] declares writes for 'typecheck', which this manifest does not declare as a gate; declared gates are 'test'
rule = 'writes'
--- and a non-boolean value ---
FactoryConfigError: ergane.yaml: [writes] gives gate 'test' the writes declaration 1; it must be `true` or `false`
```

The message names the unknown gate and lists the declared ones, so the typo is
fixable from the refusal alone. It follows `_read_timeouts`'s refusal shape
field for field, including the `type(...) is not bool` check — spelled exactly
rather than as `isinstance`, because `isinstance(True, int)` is true and the
loose forms of the two checks would each accept the other's values.

## SC-011 — each of the two gate-list runners, named

This is the criterion that distinguishes a declaration that works from one that
is merely parsed, stored and emitted.

```
_run_gate_list            (the CANDIDATE-PARSER runner: the fork is
                           `if candidate_path.exists():` in run_gates,
                           so this is the runner every Ergane node takes)
                        -> test / PASS / exit=0 / worktree_writes=('generated.txt',) / writes_declared=True
_run_gate_list_from_config (every other target repo)
                        -> test / PASS / exit=0 / worktree_writes=('generated.txt',) / writes_declared=True
```

Both are driven by `StubGateExecutor`, which is neither shipped executor, so the
declaration is being honoured at the runner rather than anywhere inside a
backend.

And end to end through `run_gates` over the candidate-parser fork, where the
candidate's stdout is not hand-written protocol JSON but
`json.dumps(dataclasses.asdict(config))` — the exact expression the parser CLI
prints, so the emitting and reading halves are asserted against each other:

```
candidate stdout `writes` key: {'test': True}
run_gates over the candidate path -> test / PASS / exit=0 / worktree_writes=('generated.txt',) / writes_declared=True
```

### The mutation that says SC-011 is load-bearing

The declaration reaches `_run_gate_list` only because it is carried through four
sites the config runner gets for free. Dropping the last of them — `run_gates`
no longer hands `writes_view` to `_run_gate_list` — is a one-line change, and
this is the whole suite under it:

```
E       AssertionError: assert <GateStatus.DIRTIED_WORKTREE: 'DIRTIED_WORKTREE'> is <GateStatus.PASS: 'PASS'>
E        +  where <GateStatus.DIRTIED_WORKTREE: 'DIRTIED_WORKTREE'> = GateResult(name='test', command='echo generated > generated.txt', status=<GateStatus.DIRTIED_WORKTR..._s=0.001390916993841529, output_tail='', concurrent_gates=0, worktree_writes=('generated.txt',), writes_declared=False).status
E        +  and   <GateStatus.PASS: 'PASS'> = GateStatus.PASS

tests/test_a_gate_may_declare_that_it_writes.py:238: AssertionError
=========================== short test summary info ============================
FAILED tests/test_a_gate_may_declare_that_it_writes.py::test_the_candidate_protocol_carries_the_declaration
1 failed, 11 passed in 0.27s
```

Eleven of twelve still pass. A story scored on anything less than SC-011 would
have gone green there, with a declaration that is parsed, stored, emitted and
never read — dead on the runner Ergane's own nodes take, including this one,
with a manifest that looks correct. That is
`verify/readiness-proves-a-thing-is-declared-not-that-it-works`, and the
mutation above is what says this story does not have it.

## What is deliberately *not* declared away

A declaration says what a gate writes. It is not a claim about a tree git could
not read, so a snapshot failure still refuses:

```python
# tests/test_a_gate_may_declare_that_it_writes.py
def test_a_declaration_does_not_excuse_an_unreadable_snapshot(...):
    ...
    assert result.status is not GateStatus.PASS
    assert result.writes_declared is True
    assert "worktree snapshot failed" in result.output_tail
```

And the declaration is not a new `GateStatus` member: a declared writer keeps
PASS, so `gates_passed` needs no edit and the stored row cannot disagree with
the decider that owns the deterministic half.
