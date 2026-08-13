# Tasks: 036-roadmap-drift-tolerance

The implementer works its slice test-first and commits once per task.

## Implementation

- [ ] T001 Read the three seams (plan §"Where the work is") and
      `tests/test_roadmap_failure_notifications.py` for the notice contract.
      No code yet; the commit is allowed to be empty.
- [ ] T002 US1-S1, US1-S2 and US1-S3 tests against a fixture repo (landing
      commit first, spec file after), then the `landed.py` no-baseline result
      and the `drift_for_spec` skip. Written first, failing first.
- [ ] T003 US1-S4 test through the scripted `_drift_runner` seam (raise → run
      survives, not-drifted, one notice with spec dir + verbatim error), then
      the workflow-side catch at workflow.py:1176 routed through 031's
      notification path.
- [ ] T004 US1-S5: run the pre-existing drift/roadmap tests and confirm they
      pass unmodified; then the full gate (`uv run pytest -q`) green.

## Verification

- [ ] Final gate command passes green; no pre-existing test edited.
