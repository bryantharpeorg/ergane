---
name: "escalation-triage"
description: "Prepare an observation brief for an open escalation from the choices it actually offered and recovery evidence; never answer it."
compatibility: "Requires the ergane CLI and the typed escalation read surface"
metadata:
  author: "operator session, 2026-09-09"
user-invocable: true
disable-model-invocation: false
---

# Escalation triage

Prepare the brief, then stop. The escalation belongs to the operator: this
surface never sends an answer, presses a choice, or assumes a fixed button set.

## Read the open escalation

```bash
eval "$(scripts/ergane-env.sh)"
uv run ergane escalations list --json > escalations.json
```

Select the record by `escalation_id`. The `choices` field is the set actually
offered by the workflow; when it is absent, say that the choice set is
unavailable rather than substituting a known enum.

## Add the recovery evidence

Read the relevant attempt evidence with the CLI's read-only verification
surface. Record what was tested, whether the tested branch moved, and each live
reading that could not be taken. Ingestion time is not observation time; carry
the recorded observation identity when the source provides one.

## Prepare the brief

```bash
python3 .agents/skills/escalation-triage/escalation_render.py escalation.json
```

The report labels facts as `observed:` and its recommendation as a proposed
answer. It may recommend only a value in `choices`. It must state that no answer
was sent, and it must not call a resolve or answer seam.
