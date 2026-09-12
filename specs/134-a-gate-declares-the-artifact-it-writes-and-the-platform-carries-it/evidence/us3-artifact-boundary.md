# US3 artifact-boundary evidence

Produced by calling `factory.verify.gates.run_gates` directly with two gates: the
first wrote a git-ignored declared coverage artifact, and the second declared an
absent coverage path. The destination is outside the watched worktree.

## Gate result records

```text
GateResult(name='first', command="printf 'coverage bytes\\n' > ignored-report.txt", status=<GateStatus.PASS: 'PASS'>, exit_code=0, duration_s=0.0015291718300431967, output_tail='', concurrent_gates=0, worktree_writes=(), writes_declared=False, artifacts=(GateArtifact(gate='first', path='ignored-report.txt', type=<ArtifactType.COVERAGE: 'coverage'>, present=True, size=15, stored_path='/tmp/tmpnxh610h6/artifact-store/first/7252a18bf02c453da6d83ac3729b2e7d94651e44bcfe15da9a796247274223de', status='permitted', provenance='new', reason=None),))
GateResult(name='second', command='true', status=<GateStatus.PASS: 'PASS'>, exit_code=0, duration_s=0.0013130279257893562, output_tail='', concurrent_gates=0, worktree_writes=(), writes_declared=False, artifacts=(GateArtifact(gate='second', path='missing-report.txt', type=<ArtifactType.COVERAGE: 'coverage'>, present=False, size=None, stored_path=None, status='absent', provenance='unchanged', reason='path does not name a file'),))
```

## Destination listing

```text
/tmp/tmpnxh610h6/artifact-store/first/7252a18bf02c453da6d83ac3729b2e7d94651e44bcfe15da9a796247274223de  size=15  bytes=b'coverage bytes\n'
```
