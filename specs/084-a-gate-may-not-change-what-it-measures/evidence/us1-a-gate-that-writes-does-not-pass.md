# 084-US1 evidence — SC-001 … SC-006

Every block below is pasted from a run in this worktree on 2026-08-22, verbatim.
The scenario pastes come from a driver script built on the helpers committed in
`tests/test_a_gate_that_writes_does_not_pass.py` — `_node_worktree`, `_manifest`
and `StubGateExecutor` — so what produced the evidence is the same fixture code
the tests run on:

```python
from tests.test_a_gate_that_writes_does_not_pass import _manifest, _node_worktree
worktree = _node_worktree(scratch(), ignore=IGNORED_BY_THE_REAL_GATE)
manifest = _manifest(worktree, {"test": "echo generated > generated.txt"})
results  = run_gates(worktree, manifest_path=manifest, executor=SubprocessGateExecutor())
```

Each result line is `name / status / exit_code / worktree_writes`.

## The suite this story added

```
tests/test_a_gate_that_writes_does_not_pass.py::test_a_gate_that_writes_an_unignored_file_is_not_reported_pass PASSED [  7%]
tests/test_a_gate_that_writes_does_not_pass.py::test_a_gate_that_writes_only_ignored_paths_still_passes PASSED [ 15%]
tests/test_a_gate_that_writes_does_not_pass.py::test_a_gate_that_rewrites_a_modified_tracked_file_is_refused PASSED [ 23%]
tests/test_a_gate_that_writes_does_not_pass.py::test_both_gate_list_runners_refuse_a_gate_that_dirties[_run_gate_list] PASSED [ 30%]
tests/test_a_gate_that_writes_does_not_pass.py::test_both_gate_list_runners_refuse_a_gate_that_dirties[_run_gate_list_from_config] PASSED [ 38%]
tests/test_a_gate_that_writes_does_not_pass.py::test_run_gates_refuses_on_the_candidate_parser_path PASSED [ 46%]
tests/test_a_gate_that_writes_does_not_pass.py::test_a_dirtying_gate_is_refused_under_every_executor[SubprocessGateExecutor] PASSED [ 53%]
tests/test_a_gate_that_writes_does_not_pass.py::test_a_dirtying_gate_is_refused_under_every_executor[StubGateExecutor] PASSED [ 61%]
tests/test_a_gate_that_writes_does_not_pass.py::test_a_dirtying_gate_is_refused_under_every_executor[BwrapGateExecutor] PASSED [ 69%]
tests/test_a_gate_that_writes_does_not_pass.py::test_a_failing_gate_that_dirties_keeps_fail_and_does_not_stop_the_run PASSED [ 76%]
tests/test_a_gate_that_writes_does_not_pass.py::test_an_unreadable_snapshot_is_evidence_not_a_clean_worktree PASSED [ 84%]
tests/test_a_gate_that_writes_does_not_pass.py::test_worktree_writes_round_trips_through_the_evidence_store PASSED [ 92%]
tests/test_a_gate_that_writes_does_not_pass.py::test_a_row_written_before_this_field_reads_back_as_nothing_recorded PASSED [100%]

============================== 13 passed in 0.30s ==============================
```

## SC-001 — the refusal, with the gate's name and the path

Gate `test` is `echo generated > generated.txt`; the repo's `.gitignore` names
`__pycache__/` and `.pytest_cache/`, and not this.

```
== SC-001: a gate that writes an unignored file ==
  name='test' status=DIRTIED_WORKTREE exit_code=0 writes=('generated.txt',)
  gates_passed(results)=False
```

The command succeeded — `exit_code=0` — and the run refuses it anyway. The
second line is FR-004 arriving at the decider that already owns the
deterministic half (`factory/verify/models.py:501-515`), with no edit to it.

## SC-002 — the control: a gate that writes only ignored paths

The fixture gate writes exactly what `uv run pytest -q` writes, into a repo that
ignores exactly what this one ignores. It is a **fixture** gate and deliberately
not a nested `uv run pytest -q` (plan trap 17).

```
== SC-002: the control — only .gitignore-matched paths ==
  .gitignore = ['__pycache__/', '.pytest_cache/']
  name='test' status=PASS exit_code=0 writes=()
  gates_passed(results)=True
  the paths the gate really wrote, and which the check did not count:
    __pycache__/src.cpython-312.pyc exists=True
    .pytest_cache/CACHEDIR.TAG exists=True
  git status --porcelain --ignored, after the gate:
    ?? ergane.yaml
    !! .pytest_cache/
    !! __pycache__/
```

Both halves are in the paste: the gate really did write both paths (`exists=True`,
and git's `!!` lines confirm git considers them ignored rather than absent), and
`writes=()` is the check declining to count them.

### And the real control, on this repository's own worktree

Trap 17 rules the full-suite-as-a-gate recursion out of the criterion, but the
underlying question — *did this brick the floor?* — is answerable cheaply by
running the snapshot helper around this repo's own gate command, in this
worktree, without a gate run wrapping it:

```
before: tree=dcd94240f1a1a8192c780b5af255c7927a898ee2 error=''
gate command exited 0: 48 passed in 10.80s
after:  tree=dcd94240f1a1a8192c780b5af255c7927a898ee2 error=''
worktree_writes=() error=''
git status --porcelain, this worktree, after the gate:
  (clean)
```

Byte-identical tree ids across a real `uv run pytest` invocation in a real
Ergane worktree. Note that this required a fix: `e5f9ce6` bumped the package to
0.2.0 without relocking, so every `uv run` was rewriting the tracked, unignored
`uv.lock` on its way to the command. That is exactly what this story refuses,
and the commit resyncing the lock is in this branch.

## SC-003 — the rewrite `git status --porcelain` cannot see

The agent modifies `src.py`; the gate then rewrites it with different content.

```
== SC-003: a tracked file the agent had already modified ==
  git status --porcelain BEFORE the gate: ' M src.py\n?? ergane.yaml\n'
  git status --porcelain AFTER  the gate: ' M src.py\n?? ergane.yaml\n'
  identical=True
  src.py content after the gate: 'value = 3\n'
  name='test' status=DIRTIED_WORKTREE exit_code=0 writes=('src.py',)
```

The two porcelain reads are the same bytes for two different trees, and the
third line proves the file really changed between them. A status-based check
would have called this clean; the scratch-index tree hash names the file.

## SC-004 — both gate-list runners, and three executors

```
== SC-004: both gate-list runners, three executors ==
  runner=_run_gate_list executor=StubGateExecutor
  name='test' status=DIRTIED_WORKTREE exit_code=0 writes=('generated.txt',)
  runner=_run_gate_list_from_config executor=StubGateExecutor
  name='test' status=DIRTIED_WORKTREE exit_code=0 writes=('generated.txt',)
  runner=run_gates executor=SubprocessGateExecutor
  name='test' status=DIRTIED_WORKTREE exit_code=0 writes=('generated.txt',)
  runner=run_gates executor=StubGateExecutor
  name='test' status=DIRTIED_WORKTREE exit_code=0 writes=('generated.txt',)
  runner=run_gates executor=BwrapGateExecutor
  name='test' status=DIRTIED_WORKTREE exit_code=0 writes=('generated.txt',)
```

`StubGateExecutor` is the load-bearing case: it implements the `GateExecutor`
protocol, ships nowhere, and runs no process at all — it performs its writes and
returns an outcome. Surviving it is what proves the check sits at
`backend.run(invocation)` rather than inside a shipped executor. That is not a
test-only shape: production already interposes a fourth executor,
`_HeartbeatingExecutor` (`factory/activities/verify_activities.py:231-258`),
which is what `run_gates` actually receives at `:278-279` — so a check inside
`SubprocessGateExecutor` would be bypassed by the wrapper production uses.

**This host has a working bwrap, so its case ran rather than skipping** — the
last pair of lines above. The guard is in the test regardless, copied from
`_bwrap_available()` (`tests/test_us4_boundary.py:165`), because a sandboxed node
agent may have no nested bubblewrap:

```python
def _bwrap_available() -> bool:
    return BWRAP_BACKEND_BINARY.is_file() and os.access(BWRAP_BACKEND_BINARY, os.X_OK)

...
    if executor_name == "BwrapGateExecutor" and not _bwrap_available():
        pytest.skip(f"{BWRAP_BACKEND_BINARY} not available on this host")
```

## SC-005 — failing *and* dirtied, with the next gate still run

Gate `lint` is `echo dirt > dirt.txt; exit 3`; gate `test` is declared after it.

```
== SC-005: failing and dirtied at once ==
  results returned: ['lint', 'test']
  name='lint' status=FAIL exit_code=3 writes=('dirt.txt',)
  name='test' status=PASS exit_code=0 writes=()
```

FAIL stays the headline and `exit_code=3` survives — the more actionable fact —
while the path is still recorded, and the gate declared after the failure is
still in the returned list. `test` records nothing because `lint`'s leavings
were already there when it started: the "after" snapshot of one gate is the
"before" of the next, which is both why N gates cost N+1 snapshots and why every
path is attributed to exactly one gate.

## SC-006 — a snapshot git refuses

The worktree's `.git` is a gitfile pointing at a directory that does not exist.

```
== SC-006: a snapshot git refuses ==
  run_gates returned a list of 1
  name='test' status=DIRTIED_WORKTREE exit_code=0 writes=()
  output_tail:
    hello

    [worktree snapshot failed: git add -A failed in /tmp/us1-evidence-jdq_l936/broken-repo: fatal: not a git repository: /nonexistent-ergane-084]
  gates_passed(results)=False
```

A list, not an exception; not PASS; git's own message in the tail, beside the
gate's own output (`hello`) rather than instead of it. An unreadable snapshot is
a tree the check cannot vouch for, and this module fails closed everywhere else.

**The tail is asserted on its version-stable half.** The paste above is from
git 2.43 on this host, which echoes the missing gitdir; the merge-queue runner's
git prints `fatal: not a git repository: (null)` for the same gitfile, and the
first landing attempt failed there on an assertion that the echoed path appears:

```
FAILED tests/test_a_gate_that_writes_does_not_pass.py::test_an_unreadable_snapshot_is_evidence_not_a_clean_worktree
  AssertionError: assert '/nonexistent-ergane-084' in 'hello\n\n[worktree snapshot
  failed: git add -A failed in /tmp/.../broken-repo: fatal: not a git repository: (null)]'
```

So the test asserts `fatal: not a git repository` — git's error *class*, which
both versions print — plus the two facts this repository owns and git cannot
reword: the `worktree snapshot failed` marker and the path of the tree that
could not be read. Which tree was unreadable is what the next attempt needs; how
its git phrased the complaint is not something a committed test may depend on.
