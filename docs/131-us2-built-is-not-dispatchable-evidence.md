# 131-US2 — before-and-after queue evidence

The plan names `057-a-new-repo-gets-a-constitution` as its live fixture, but this
attempt's base tree has it as `state: landed`; the operator had attested it
since the plan was written. `164-codex-keeps-its-seeded-home-across-the-worktree-boundary`
is the current `state: ready` fixture with one observed landing, so the same
comparison is recorded against it. No live corpus state is edited.

## Before

```text
queue
  164-codex-keeps-its-seeded-home-across-the-worktree-boundary  ready  dispatchable
```

## After (filled by the implementation task)

The plan's `057` fixture was attested before this attempt started, so the
after evidence below uses an isolated copy of the corpus with `057` restored
to the historical `602a92c` text and its four landing-commit subjects minted.
This avoids editing the live corpus.

### 057 before the predicate changed

Tool: `compute_readiness(..., landed_for=landed_for)` with no drift resolver —
exactly the pre-change read.

```text
057-a-new-repo-gets-a-constitution ready dispatchable
```

### 057 after `ergane status specs`

```text
queue (readiness: attestation, plus landings on main (979d1b332cae) in
/home/admin/code/ergane/.factory/worktrees/131-the-status-board-names-the-spec-it-cannot-dispatch/us2/.factory-tmp/us2-evidence-057-corpus/repo, read without fetching)
  057-a-new-repo-gets-a-constitution                            built  awaiting attestation
```

### 057 drift control

The isolated copy changed one acceptance-scenario word after its four landing
commits, then ran the new reporting resolvers. It remains dispatchable because
drift is real work; it does not inherit the attestation word.

```text
057-a-new-repo-gets-a-constitution ready dispatchable
```

### Live control from the unchanged current corpus

The live `057` is now `state: landed`, but `164-codex-keeps-its-seeded-home-across-the-worktree-boundary`
was `state: ready` with one observed landing before the implementation:

```text
164-codex-keeps-its-seeded-home-across-the-worktree-boundary  ready  dispatchable
```
