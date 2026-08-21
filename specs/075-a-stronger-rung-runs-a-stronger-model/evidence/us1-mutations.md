# 075-US1 evidence

The whole suite, on the committed implementation:

    $ uv run pytest -q
    3939 passed, 49 skipped, 6 warnings in 308.30s (0:05:08)

T002 and T004 are controls, and a control nobody has watched fail is a comment.
Each edit below was applied to a green committed HEAD, run over
`tests/test_rung_resolves_its_own_model.py` (6 tests), and reverted with
`git checkout HEAD -- factory/workgraph/workflow.py`.

| edit | tests red |
|---|---|
| M1 `_routing_for` returns the debugger's entry for every attempt | 4 · both controls, S5, S6 |
| M2 the clean-sync recovery fork selects `DEBUGGER_PERSONA` too | 1 · the second control |
| M3 both attempt sites take `model_alias` from `resolved` (pre-075) | 3 · S1, S3, S6 |
| M4 an unresolvable rung persona falls back to another entry | 1 · S5 |
| M5 `agent` resolved separately, from the node's persona | 1 · S6 |

**M1** is trap 3 exactly — "a change that returns B for every attempt passes
scenario 1 and is wrong". It leaves S1 and S3 green:

    $ uv run pytest -q -p no:randomly tests/test_rung_resolves_its_own_model.py
    FAILED tests/test_rung_resolves_its_own_model.py::test_an_ordinary_attempt_carries_the_nodes_own_model
    FAILED tests/test_rung_resolves_its_own_model.py::test_a_clean_resync_recovery_keeps_the_nodes_own_persona_and_model
    FAILED tests/test_rung_resolves_its_own_model.py::test_a_rung_persona_absent_from_the_snapshot_fails_the_node
    FAILED tests/test_rung_resolves_its_own_model.py::test_agent_and_model_alias_come_from_one_resolved_entry
    4 failed, 2 passed in 1.63s

**M2**, the fork at `factory/workgraph/workflow.py` collapsed so every recovery
is the debugger's:

    FAILED tests/test_rung_resolves_its_own_model.py::test_a_clean_resync_recovery_keeps_the_nodes_own_persona_and_model
    1 failed, 5 passed in 1.64s

**M3**, the defect itself put back — the rung still selects the persona, the
attempt still runs the node's model:

    FAILED tests/test_rung_resolves_its_own_model.py::test_the_debugger_rung_carries_the_debugger_personas_model
    FAILED tests/test_rung_resolves_its_own_model.py::test_a_conflicted_recovery_carries_the_conflict_rungs_model
    FAILED tests/test_rung_resolves_its_own_model.py::test_agent_and_model_alias_come_from_one_resolved_entry
    3 failed, 3 passed in 1.71s

**M4**, the silent fallback FR-005 forbids:

    FAILED tests/test_rung_resolves_its_own_model.py::test_a_rung_persona_absent_from_the_snapshot_fails_the_node
    1 failed, 5 passed in 1.72s

**M5**, `agent` and `model_alias` resolved by two lookups again (FR-002):

    FAILED tests/test_rung_resolves_its_own_model.py::test_agent_and_model_alias_come_from_one_resolved_entry
    1 failed, 5 passed in 1.74s

## The mutation that hung instead of reddening, and what it found

The first attempt at M1 was the literal wording of trap 3 — make the *persona
selection* unconditional (`_rung_selection` always returns `DEBUGGER_PERSONA`,
and the loop starts on it). That run never finished: it did not redden, it hung.

`_attempts_spent` (`factory/verify/ladder.py`) excludes `DEBUGGER_PERSONA` from
the ordinary budget, so a node whose every attempt is recorded under the debugger
never spends an attempt, `next_action` never leaves `RETRY`, and the ladder loops
forever. That is a property of the ladder's accounting, not of this story's
change, and it is why the mutation used above moves the *routing* rather than the
persona: it reproduces the wrong behaviour trap 3 warns about (the rung's model
on every attempt) while leaving the accounting the ladder depends on intact.

Worth knowing for US2, which configures a promotion persona:
`_attempts_spent` excludes that persona too, so the same shape is reachable if a
rung ever selects it unconditionally.
