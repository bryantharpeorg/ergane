# Implementation Plan: a stronger rung runs a stronger model

**Spec**: `specs/075-a-stronger-rung-runs-a-stronger-model/spec.md`

## What already exists, and where

Every line below was **read and verified against the tree on 2026-08-20**, after
067/068/069 were dispatched. Check each again before you rely on it: this
repository stales its own specs by shipping, and 067's plan lost fourteen anchors
overnight to exactly that.

**The single resolution, and the two places it is consumed:**

- `factory/workgraph/workflow.py:712` — `resolved = await self._resolve(graph)`.
  **Once per epic, before the attempt loop.** This is the root of the defect: it
  is not wrong to resolve here, it is wrong that nothing resolves again.
- `factory/workgraph/workflow.py:1380` — `model_alias=resolved.model_alias` in the
  ordinary attempt's context.
- `factory/workgraph/workflow.py:2785` — the same line in the **recovery**
  attempt's context.
- `factory/workgraph/models.py:207` — `ResolvedNode.model_alias`, whose docstring
  at `:201` states the constitutional rule: it "is the only place a model name
  enters an epic (constitution VII)". Whatever you build must keep that true.

**The three rungs that select a persona and change nothing:**

- `factory/workgraph/workflow.py:1608` —
  `DEBUGGER_PERSONA if action == NextAction.DEBUGGER else node.persona`.
- `factory/workgraph/workflow.py:2650` and `:2653` — the recovery's fork:
  `persona = resolved.node.persona` on a clean sync, `persona = DEBUGGER_PERSONA`
  on a conflicted one.
- `factory/verify/ladder.py:173` — `_promotion_available`, which returns `False`
  whenever `config.promotion_persona is None`.

**The half that already works — do not rewrite it:**

- `factory/workgraph/workflow.py:2753-2622`:
  ```python
  recovery_persona_entry = self._personas.get(persona)
  recovery_agent = recovery_persona_entry.agent if recovery_persona_entry is not None else ""
  ```
  The recovery path **already** looks the rung's persona up and takes its
  `agent`. Your change is to take `model_alias` from the same entry. The comment
  directly above it (`:2751-2620`) says "Recovery re-uses the same persona as the
  original node" — **that comment is false for a conflicted sync**, which is what
  `:2653` does. Fix the comment while you are there.

**The snapshot the lookup uses, and why it misses:**

- `947` —
  `self._personas = {item.node.persona: self._resolve_persona(item.node.persona) for item in resolved}`.
  Keyed by the personas **nodes declare**. `DEBUGGER_PERSONA` is absent unless a
  story happens to declare it, so `self._personas.get(persona)` is `None` on
  every conflicted recovery and `recovery_agent` degrades to `""`.
- `factory/workgraph/workflow.py:558` — `self._personas: dict[str, Persona] = {}`,
  its declaration.
- `factory/verify/ladder.py:71` — `PROMOTION_PERSONA = "__promotion__"`, the
  synthetic placeholder. It must never be resolved as a real registry entry.

**The config that cannot be set:**

- `factory/cli/roadmap.py:236` — `config=VerificationConfig()`, bare.
- `factory/cli/nouns/build.py:511` — `config = VerificationConfig()`, bare.
- Neither `ergane build start` nor `ergane roadmap start` exposes a flag for any
  field of it. `promotion_persona`, `max_attempts` and `promotion_cycles` are all
  unreachable; this spec adds only the first.

## Traps

**1. The registry read is ALREADY in workflow code, and you must not add more.**
`factory/workgraph/workflow.py:927-942` — `_resolve_persona` does
`from factory.config import load_personas` and calls it, and it is reached from
`_resolve` at `:947`, which is workflow code. **That is a filesystem read on a
replay path.** It is a latent determinism defect that predates this spec and is
not yours to fix here — but a change that resolves a persona *per attempt* by
calling it again turns a latent defect into a live one, and 039 exists because
this class of thing wedges epics. **Resolve every persona you might need once, at
epic start, into `self._personas`, and select from the map thereafter.** File the
existing read as its own finding rather than widening it.

**2. Snapshot discipline is a stated contract, not an implementation detail.**
`ResolvedNode`'s docstring (`factory/workgraph/models.py:196-199`): "The same
snapshot discipline as 002's criteria: an operator editing `personas.yaml`
mid-epic changes the *next* epic, never the one in flight." FR-004 restates it.
Populating the map with more personas at epic start preserves it; re-reading the
file when a rung fires breaks it, and would break it *silently* — the epic that
suffers is the one already running.

**3. The control is the story.** US1-S2 and US1-S4. A change that returns the
rung's model for every attempt satisfies scenario 1 perfectly and is a worse bug
than the one you are fixing, because it silently promotes every ordinary attempt
to the expensive builder. Both controls must assert the *node's* model on the
ordinary and clean-sync paths, and the mutation that proves they can fail is to
make the selection unconditional and watch them go red.

**4. `agent` and `model_alias` must come from one lookup.** FR-002. They are
already adjacent at `factory/workgraph/workflow.py:2753-2622` and
`factory/workgraph/workflow.py:2785`, and they already disagree. If your
diff leaves two independent resolutions, you have reproduced the cause while
fixing the symptom — the same shape as 067's two mount-set literals.

**5. Do not hardcode a model name anywhere.** Constitution VII, and
`factory/workgraph/models.py:201` says it in the tree: the registry is the only place a model alias
may appear. The rung selects a *persona*; the persona names the model.

**6. `PROMOTION_PERSONA` is a sentinel, not a persona.** `factory/verify/ladder.py:71` sets it to
`"__promotion__"` and `_promotion_cycles_spent` (`:159`) uses it as a fallback
that "never appears in real history". A change that tries to resolve it against
the registry will fail on a floor where promotion is unconfigured — which is
every floor today.

**7. The key alias is already right; do not change key issuance.** D-026 puts the
persona in the virtual key's alias, and both occurrences of this defect were
*found* by that alias disagreeing with the running process. Ledger attribution is
correct today. This spec changes what the agent runs, not how it is billed.

**8. Attempt accounting is already ready for the promotion rung.**
`factory/verify/ladder.py:141` builds `excluded = {DEBUGGER_PERSONA,
promotion_target}` when a promotion persona is configured, so a promoted attempt
is already kept off the ordinary budget. Switching the rung on does not require
touching `_attempts_spent` — and if you find yourself changing it, re-read US5's
tests first.

**9. Determinism, for the workflow half.** `next_action` and the rung selection
run in workflow code. No clocks, no environment, no filesystem. The selection
must be a pure function of `(history, config, the snapshot)`.

**10. One test file per story, named here.**
- US1 → `tests/test_rung_resolves_its_own_model.py`
- US2 → `tests/test_promotion_persona_is_operator_settable.py`
- US3 → `tests/test_attempt_reports_persona_and_model.py`

**11. US3 gates on US1 AND US2 having MERGED, and both edges are load-bearing
for different reasons.** The Work Graph uses `depends_on_merged: [US1, US2]`.

- **US1** because US3 reports a field US1 creates. A `depends_on` edge would
  release US3 while US1 was still riding the queue, and it would build against a
  base without the field. `depends_on` unlocks on verification,
  `depends_on_merged` on merge (`factory/workgraph/derive.py:550`). That
  distinction cost a rework on 068 the day this was written.
- **US2** for a different reason entirely: **both edit
  `factory/cli/nouns/build.py`.** US2 adds the flag near `:511`; US3 renders the
  new fields in `ergane build status`. `depends_on_merged` models what a story
  needs to *exist*, not what it will *touch*, so nothing would have stopped these
  two running concurrently at `--max-concurrent-nodes` above 1 and colliding.
  This was caught in review only by listing the files each story's tasks name —
  it is invisible in the story text, and on 068 the identical shape presented as
  a `CONFLICT` rejection on a shared **test** file rather than as anything the
  graph could see.

The cost is that US3 runs last and alone. Take it: the alternative is a rework
cycle plus a merge-queue rejection, which is strictly slower.

**12. The judge sees the diff and the criteria — and Success Criteria are not
criteria.** `factory/verify/criteria.py` reads Success Criteria bullets past;
what reaches a judge is each story's acceptance scenarios and FR bullets. SC-001
through SC-005 are the operator's. Every Then-clause above is written "proven by
a committed test" so that it is provable from the diff alone.

## Sizing

Three stories. US1 and US2 are independent; US3 waits on US1's merge.

US1 is the real work and it is smaller than it looks: the lookup exists, the
`agent` half already flows, and the map is one comprehension. Its difficulty is
entirely traps 1, 2 and 3 — resolving *more* at epic start rather than *again*
per attempt, and writing controls that can fail.

US2 is two argparse flags, a pass-through, and a pre-flight registry check. The
smallest story in the set.

US3 is a field on `AttemptRecord` and two renderers.

## Verification the operator will run, independent of the gate

- **Prove US1 by control.** Point `debugger` at a model the node is not using,
  drive a debugger rung, and read `--model` off the live process — not the key
  alias, which was already correct and is what hid this twice. Then drive an
  ordinary attempt and read it again. They must differ.
- **Prove US2 by absence.** Start an epic with no flag and confirm the promotion
  rung never fires, then start one with it and confirm it does.
- **Prove US3 against a real history.** A node that took a debugger rung should
  show two different models across its attempts in `build status --json`.
