# 163-US1 evidence — the configuration-to-verification connection, red then green

The story's regression red-first, with the exact commands and results pasted
(constitution VIII / D-037: the judge sees this diff and nothing else). The
tests walk the connection the incident exposed — manifest `timeouts:` through
`load_loop_config` into `EpicInput.config.gate_timeout_s` and out to
`EpicWorkflow._verify`'s scheduled `run_gates` `heartbeat_timeout` — and
assert at the seams: the `EpicInput` is read off the client the CLI started
the epic with, and the heartbeat bound is read off the run history's
`ActivityTaskScheduled` event.

## Red (against 778de44, the pre-story tree)

    $ uv run pytest tests/test_163_declared_gate_deadline.py -q --no-header
    FAILED tests/test_163_declared_gate_deadline.py::test_a_declared_900s_test_gate_pins_900_into_the_epic_input
    FAILED tests/test_163_declared_gate_deadline.py::test_the_deadline_matrix[v1-declared-900]
    FAILED tests/test_163_declared_gate_deadline.py::test_the_deadline_matrix[v2-declared-900]
    FAILED tests/test_163_declared_gate_deadline.py::test_the_deadline_matrix[single-explicit-shorter]
    FAILED tests/test_163_declared_gate_deadline.py::test_the_deadline_matrix[v2-mixed-max]
    FAILED tests/test_163_declared_gate_deadline.py::test_the_derivation_scan_is_declared_gates_not_the_whole_timeout_map
    FAILED tests/test_163_declared_gate_deadline.py::test_the_roadmap_overlays_the_promotion_rung_on_the_derived_basis
    FAILED tests/test_163_declared_gate_deadline.py::test_the_roadmap_child_input_carries_the_derived_basis
    FAILED tests/test_163_declared_gate_deadline.py::test_a_pinned_input_is_untouched_by_a_later_manifest_edit
    FAILED tests/test_163_declared_gate_deadline.py::test_the_derivation_reads_the_manifest_by_its_resolved_name
    =================== 10 failed, 9 passed, 1 warning in 1.34s ====================

The red assertion, from the S1 CLI case (the pin, not the parse — plan trap 1):

        payload = await _captured_epic_input(
            tmp_path, run_async, dispatch_recorder, timeouts={"test": DECLARED_S}
        )

    >       assert payload.config.gate_timeout_s == DECLARED_S
    E       assert 600 == 900
    E        +  where 600 = VerificationConfig(max_attempts=3, max_judge_retries=2, debugger_cycles=1, gate_timeout_s=600,
                escalation_timeout_s=3600, promotion_persona=None, promotion_cycles=1, max_launch_retries=2,
                max_pre_agent_failures=4).gate_timeout_s

Nine of the ten failures are `assert 600 == <declared>`; the tenth
(`test_the_derivation_scan_is_declared_gates_not_the_whole_timeout_map`) was
first refused by the parser for a timeout naming an undeclared gate and, once
the manifest declared both gates, failed on the same `600 == 900` assertion.
The nine passing tests are the controls: the unchanged 600/600 pair, both
no-timeout-block matrix rows, the omitted-entry derivation, the
scheduling-seam pair (900→960 and 600→660 read off run history — the
workflow's arithmetic was never the defect; the pin was), the grace literal,
the malformed-declaration refusals, and the old-default-only input.

## Green (same file, after T005)

    $ uv run pytest tests/test_163_declared_gate_deadline.py -q --no-header
    ======================== 19 passed, 1 warning in 1.34s =========================

## Focused neighbours (each green after T005)

    $ uv run pytest tests/test_factory_yaml.py tests/test_gates.py \
        tests/test_023_us2_dispatch_pin.py tests/test_092_manifest_threshold.py \
        tests/test_promotion_persona_is_operator_settable.py \
        tests/test_landing_dials_reach_the_epic.py -q --no-header
    ============================= 267 passed in 14.08s =============================

    $ uv run pytest tests/test_scheduled_epics_carry_the_dials.py \
        tests/test_roadmap_scheduler.py tests/test_verify_activities.py \
        tests/test_us5_gates.py -q --no-header
    ======================= 134 passed, 1 skipped in 11.93s ========================

    $ uv run pytest tests/test_workgraph_sweep.py tests/test_verification_sweep.py \
        tests/test_forge_manifest.py tests/test_a_gate_may_declare_that_it_writes.py \
        tests/test_noop_gate.py -q --no-header
    ============================= 311 passed in 8.86s ==============================

    $ uv run pytest tests/test_interpreter.py -q --no-header
    ======================== 94 passed in 90.78s (0:01:30) =========================

    $ uv run pytest tests/test_engine_skew_preflight.py \
        tests/test_156_us1_build_start_refuses_skewed_worker.py \
        tests/test_156_us3_the_skew_record_is_visible_after_the_fact.py \
        tests/test_ergane_build.py -q --no-header
    ======================== 69 passed, 1 warning in 7.09s =========================

    $ uv run pytest tests/test_023_us2_dispatch_pin.py \
        tests/test_163_declared_gate_deadline.py tests/test_roadmap_scheduler.py \
        tests/test_roadmap_durability.py tests/test_roadmap_wedge_visibility.py \
        tests/test_scheduled_epics_carry_the_dials.py tests/test_ergane_roadmap.py \
        tests/test_roadmap_first_tick_on_fresh_init.py \
        tests/test_roadmap_activities_off_the_event_loop.py -q --no-header
    ======================== 94 passed, 1 warning in 14.68s ========================

    $ uv run pytest tests/test_ladder.py tests/test_verify_store.py \
        tests/test_116_gate_is_ground_truth.py tests/test_ergane_build_ship.py \
        tests/test_declared_control_plane.py tests/test_engine_identity.py \
        tests/test_ergane_init.py tests/test_roadmap_failure_notifications.py \
        tests/test_worktree.py -q --no-header
    290 passed across these files (individual invocations, all green):
    test_ladder.py 44, test_verify_store.py 85, test_116_gate_is_ground_truth.py 22,
    test_ergane_build_ship.py 12, test_declared_control_plane.py 18,
    test_engine_identity.py 16, test_ergane_init.py 15,
    test_roadmap_failure_notifications.py 13, test_worktree.py 65

## Declared full gate

`factory.yaml`'s gate is `uv run pytest -q`.

    $ uv run pytest -q
    ========== 5958 passed, 58 skipped, 15 warnings in 599.05s (0:09:59) ===========

Run twice to the end: the first full-gate run (against the T005 commit,
pre-seam-presence fix) returned `1 failed, 5957 passed, 58 skipped in
604.63s` — the failure being this story's own
`test_the_roadmap_child_input_carries_the_derived_basis`, a test-interaction
defect in the new file (see below), which the fix committed at 828baee
closes. The second run, quoted above, is fully green.

## Skipped live paths (58 skipped, unchanged in kind by this story)

- `tests/test_us5_gates.py:522` — agent runner not installed on this host
  (the bwrap boundary's live arm).
- The five live tiers (`live_capacity`, `live_epic`, `live_merge`,
  `live_onramp`, `live_proxy`) — each skips by its own env contract
  (`TEMPORAL_ADDRESS`/`TEMPORAL_NAMESPACE` for capacity and epic, a real
  forge for merge, the onramp prerequisites for onramp,
  `LITELLM_PROXY_URL`+`LITELLM_MASTER_KEY` for proxy, and Telegram
  credentials for the sixth). None of them is a gate this story could have
  exercised in-sandbox: the pinned-input semantics they would observe live
  are held at the seams this story's committed tests assert (the `EpicInput`
  handed to `start_workflow`, the scheduled `run_gates` heartbeat read off
  history). No live dispatch was attempted by this node; a running epic's
  non-migration is asserted structurally (`EpicInput.config` is a frozen
  dataclass, pinned at dispatch, read by `_verify` from that payload alone)
  and through the `load_loop_config` before/after-manifest-edit test.

## The one defect this story's own run exposed (fixed, not skipped)

`RoadmapWorld.restore` (`tests/test_roadmap_scheduler.py:523`) *deletes* a
runner seam whose pre-world value was `None`, so "absent" is a module state a
preceding test leaves behind. The roadmap activity reads the module global at
call time, so the story's roadmap harness — which runs the *real*
`read_loop_config` — NameError'd mid-flight when the full suite reached it
after a deleting restore, instead of reading the manifest. The harness now
distinguishes "seam absent" from "seam `None`", ensures the attribute exists
before the run (`None` = "no runner, read the manifest for real"), and puts
back exactly the state it found. Committed at 828baee; the combined suite of
the deleting module and this file is green together.

## Diff size

    $ git diff HEAD~3 | wc -c
    45800

against the 64 KiB refusal threshold (`DIFF_INPUT_LIMIT`,
`factory/verify/diffbounds.py`): 45,800 bytes, 70% of the ceiling. The
evidence note itself is committed inside that budget.

## What this story did not change (the negative controls, stated)

- No new dial: `_read_ladder` still retains the default and refuses unknown
  keys (`test_factory_yaml.py`'s 169 tests unchanged and green).
- No new serialized field: `VerificationConfig.gate_timeout_s` is the only
  carrier; `_child_config`'s overlay stays one field wide and preserves the
  derived basis beside it.
- The runner's per-gate resolution (`_resolve_timeout`), its termination
  path (SIGTERM → SIGKILL against the process group) and the two-hour total
  activity ceiling (`_GATES`) are untouched — `tests/test_gates.py`'s 48
  tests pass unmodified.
- The grace constant is asserted as the literal 60
  (`test_the_grace_constant_is_the_existing_sixty_seconds`), and the
  scheduling pair is read off run history, not off a source string.