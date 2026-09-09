# Implementation Plan: a declared gate deadline reaches the workflow

## Verified seams

- `factory/verify/factory_yaml.py:1134` — `load_loop_config` currently returns the parsed ladder unchanged. This is the smallest shared dispatch-time seam.
- `factory/verify/models.py:1189` — `VerificationConfig` already carries `gate_timeout_s` across the workflow boundary. Reuse it; no new serialized field is needed.
- `factory/verify/factory_yaml.py:884` — `_read_ladder` deliberately retains the default; the manifest's ladder must not grow a second gate-timeout setting.
- `factory/verify/gates.py:1569` — `_resolve_timeout` defines effective per-gate precedence. Reuse the existing default authority without adding an import cycle.
- `factory/cli/nouns/build.py:822` — `start_command` reads `load_loop_config` before constructing an epic through `_start_epic`.
- `factory/activities/roadmap_activities.py:843` — `read_loop_config` supplies the roadmap's configuration read.
- `factory/roadmap/workflow.py:256` — `_child_config` overlays only the promotion persona and should preserve the derived basis.
- `factory/workgraph/workflow.py:2596` — `EpicWorkflow._verify` schedules `run_gates` with the pinned basis plus `_GATE_HEARTBEAT_GRACE_S`.
- `factory/activities/verify_activities.py:232` — `_HeartbeatingExecutor` emits a beat before each gate; this story does not replace that mechanism.

Symbols govern; re-resolve these line hints before editing. Read the complete
spec, plan, tasks and declared standards before implementation.

## Smallest implementation

Derive the maximum effective deadline for the declared gate names at
`load_loop_config`, and replace only the existing ladder field in the returned
dispatch configuration. An empty gate set uses the existing default. Avoid
changing `parse_factory_config`'s ladder defaults or exposing a new dial.
The existing callers and `_verify` then carry the value without new workflow
commands, activities, or payload fields.

## Traps

1. A parser test alone cannot catch this incident: parsing 900 already works.
   Record the input handed to dispatch and the options handed to `run_gates`.
2. `max([default, ...])` is wrong for all-explicit shorter deadlines. Include
   the default only for a gate whose deadline is omitted, or for no gates.
3. Scan declared gate names, not every timeout dictionary entry. Preserve the
   parser's existing validation and refusal behavior.
4. The roadmap promotion override must not reconstruct the config and lose
   the derived field. Test through its production composition seam.
5. Do not read a manifest inside workflow code. Old pinned inputs still mean
   what they meant; a deployment does not repair an already-running epic.
6. Preserve subprocess deadlines, timeout result reporting and process-group
   cleanup. Increasing a watchdog is not permission to disable a gate timer.
7. No new dependency. Use existing pytest, Temporal test helpers and injected
   activity/client seams. Avoid wall-clock fifteen-minute tests.
8. The current required suite can stall on hosted CI. Keep scope on this
   timer defect; report an unrelated gate failure instead of skipping it.
9. Keep the complete diff below 64 KiB. Small behavioral tests are the primary
   evidence; do not paste the entire suite log into the story diff.
10. `_GATES` also carries an independent two-hour total activity deadline.
    Preserve it; this repair concerns the heartbeat deadline for the requested
    900-second gate, not arbitrary suites exceeding that existing ceiling.

## Verification

Write and run the configuration-to-verification regression red before the
change, then green. Run existing manifest, CLI, roadmap and gate-termination
tests, followed by the declared full gate. Commit a compact evidence note with
the exact red/green commands and results, explicitly identifying any skipped
live paths. The outer factory verdict and native merge queue remain required.
