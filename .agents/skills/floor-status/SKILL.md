---
name: "floor-status"
description: "Report recorded floor facts: nodes, attempts, routing provenance, dispatch identity, and explicitly unavailable readings. Use only for status."
compatibility: "Requires the ergane CLI and the typed read surfaces documented here"
metadata:
  author: "operator session, 2026-09-09"
user-invocable: true
disable-model-invocation: false
---

# Floor status

This is a status skill. Every fact comes from a recorded read surface; do not
fetch, merge, push, dispatch, attest, answer, write findings, or change a
service while preparing it.

## Read the two typed surfaces

```bash
eval "$(scripts/ergane-env.sh)"
uv run ergane build status "$EPIC_ID" --json > status.json
uv run ergane build attempts "$EPIC_ID" --json > attempts.json
```

`status.json` says what the workflow currently reports, including any live-spend
or landing-head reading that was available. `attempts.json` carries the
verification rows that outlive the workflow. For an older row, a missing
dispatch, persona, model, or route is `<unknown>`, not zero and not a value
inferred from today's registry.

## Make unavailable facts visible

Write the readings that could not be taken into `services.json`:

```json
{
  "temporal": {"state": "unavailable", "reason": "socket unavailable"},
  "landing_head": {"state": "unavailable", "reason": "target repo absent"}
}
```

Do not retry a degraded read as a different fact, and do not infer a state from
a clock, a nearby checkout, or an inherited variable.

## Render the report

```bash
python3 .agents/skills/floor-status/floor_render.py \
  status.json attempts.json services.json
```

The report carries recorded runner, effective route, model, dispatch identity,
and evidence source. A historical attempt must not be rewritten from the
current persona registry. Preserve two dispatches of one node as two groups even
when their attempt numbers and old identity fields coincide.
