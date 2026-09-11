# Implementation Plan: operator skills report and act by declared intent

## Current seams

- `.agents/skills/floor-status/floor_render.py:43` — `render_floor` and `.agents/skills/escalation-triage/escalation_render.py:34` — `render_brief` are the landed US1 renderer seams.
- `factory/cli/nouns/build.py:491` — `render_status`, `factory/cli/nouns/build.py:1203` — `status_command`, and `factory/cli/nouns/build.py:1577` — `render_attempts` are the read surfaces US1 consumes.
- `factory/cli/nouns/escalations.py:29` — `render` and the escalation query expose current options without choosing one.
- `.agents/skills/build-metrics/scripts/rework.py:165` — `main` and `.agents/skills/build-metrics/scripts/loc.py:18` — `loc_tool` are the landed US2 aggregation and stable-local-tool boundaries.
- `factory/spec/composition.py:64` — `validate_spec` remains the one validation composition. `.agents/skills/spec-html/render.py:94` — `read_landing` is the landed US3 tagged landing-read boundary.
- `factory/doctor/cli.py:150` — `_report_command` stamps ingestion time, while `factory/doctor/store.py:167` — `report` accepts only `seen_at`; neither remaining US4 seam represents historical observation identity.
- Spec 087 moves these project skills to their canonical packaged location. Resolve paths from the installed skill root rather than baking either client's home into helpers.

## Story slices

### US1 — Pure floor and escalation reads

Separate the observation pipeline from action instructions. Prefer typed status,
attempt, and escalation inputs to regexes over Temporal start payloads. Tests use
denied mutation fakes and fixtures containing route transitions and promotions.

### US2 — Honest metrics

Add dispatch to the record key before aggregation. Treat legacy absence as a
first-class unknown. Replace the network-downloaded LOC executable with an
explicit local-tool resolver and unique temporary outputs; do not add a package.

### US3 — One validation truth

Adapt the renderer around `SpecValidation`; do not import private parser pieces
or retain duplicate graph/anchor validation. Model landing availability as a
tagged result so empty, unavailable, and error are three values. Publication is
not part of rendering.

### US4 — Historical event identity

Extend the doctor event contract narrowly with an observation id and observed
time, including schema migration and idempotency. Keep ingestion/rehearsal
separate from apply. A historical fix claim is evidence to inspect, never a
resolution transition.

## Traps

1. **A report can mutate through a helper.** Static text review is insufficient; deny every action seam in tests.
2. **Today's registry is not yesterday's attempt.** Routing comes from frozen execution/evidence data.
3. **Promotion rungs are resolved.** Do not restore the obsolete claim that debugger promotion has no model.
4. **Two dispatches may share every old key field.** Dispatch identity must join before grouping.
5. **Unknown is not zero.** This applies independently to tokens, dollars, runner, route, model, and landing state.
6. **An empty ledger is valid.** A percentage helper needs an explicit empty denominator path.
7. **No new dependency is approved.** The LOC tool is local-and-declared or unavailable.
8. **HTML is a view, not a validator.** Preserve the exact library report, including skipped layers.
9. **No landing data and failed landing lookup differ.** Keep both visible.
10. **Ingestion time is not observation time.** Historical replay must not look like a new sighting.
11. **A duplicate observation may have a different file name.** Idempotency keys on source identity, not batch position.
12. **Operational root is explicit.** Tests use temporary stores; later operator validation names `/home/admin/code/ergane/.factory` without opening it for writes.
13. **`mkstemp` returns an open descriptor and a path.** The optional rehearsal-store path must use and clean up the path, close the descriptor, and work when the caller omits `--rehearsal-db`; never pass the descriptor itself to `Path`.
14. **Historical identity is persisted data.** Sanitize `observation_id` and all event metadata before either rehearsal or apply, not only the nested `Finding`; a credential-shaped identity must never reach `finding_events` verbatim.

## Verification

Each story has temporary inputs and denied mutation/network seams. Run focused
tests, inspect source for forbidden action commands in reporting paths, then run
the declared gate. Verify the operational doctor database hash is unchanged.
