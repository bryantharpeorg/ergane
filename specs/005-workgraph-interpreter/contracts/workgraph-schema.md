# Contract: `## Work Graph` grammar and `workgraph.json` schema

Owned by `factory/workgraph/derive.py` (pure) and `factory/workgraph/models.py`
(validation). FR-002, FR-011, SC-006. The spec section is an **additive authoring
convention** — vendored `.specify/templates/` are never modified; this validation,
not the template, enforces it.

## The spec section (authoring grammar)

A level-2 header `## Work Graph` anywhere in the feature spec, containing one
fenced YAML block (` ```yaml `). Headers are found with the fence-masked scan the
criteria parser uses; content outside the fence is ignored (prose is welcome).

```markdown
## Work Graph

​```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002]
US2:
  depends_on: [US1]
  implements: [FR-003]
  timeout: 7200        # optional per-story override, seconds
​```
```

Shape rules (violations name the story and emit nothing):

| rule | requirement |
|---|---|
| `section_missing` | spec has exactly one `## Work Graph` section with exactly one fenced YAML block |
| `mapping` | block is a mapping of story id → declaration mapping |
| `story_id` | every top-level key matches `US<n>` and is a story the criteria parser finds in this spec |
| `coverage` | every story the criteria parser finds has a declaration (no silent orphans) |
| `depends_on` | present, a list (may be empty) of declared story ids; no self-dependency |
| `implements` | present, a list (may be empty) of `FR-###` keys declared in this spec |
| `timeout` | absent, or a positive integer of seconds |
| `unknown_key` | no other keys in a declaration |
| `acyclic` | the `depends_on` relation has no cycle (error names one cycle's members) |

## Derivation semantics (pure: spec text → WorkGraph)

- One node per story. `id` = story key lowercased (`US1` → `us1`).
- `requirement_keys` = `[story_key, *implements]` — the exact filter later handed
  to `snapshot_criteria`.
- `spec_ref` = `<feature>:<story_key>` (component 1's attribution string).
- `persona`: `implementer` for every derived node in the minimal interpreter
  (verifier nodes and per-story personas are post-bootstrap grammar).
- `depends_on` story ids are lowercased to node ids.
- Node order in the output = story order in the spec (scheduling order, R10).
- `epic_id` = the feature directory name; `feature`, `specs_root`, `target_repo`
  are supplied by the caller (the CLI), not parsed from the spec.

## `workgraph.json`

The compiled, inspectable artifact — written by `factory-epic derive` next to the
spec, consumed by `factory-epic start`. JSON of `WorkGraph` (data-model.md):

```json
{
  "epic_id": "003-merge-queue",
  "feature": "003-merge-queue",
  "specs_root": "specs",
  "target_repo": "/home/admin/code/ergane-target",
  "nodes": [
    {
      "id": "us1",
      "story_key": "US1",
      "persona": "implementer",
      "spec_ref": "003-merge-queue:US1",
      "requirement_keys": ["US1", "FR-001", "FR-002"],
      "depends_on": [],
      "timeout_override_s": null
    }
  ]
}
```

## Start-time validation (FR-002)

`factory-epic start` and the workflow's first step both re-validate (the file is
hand-editable; re-validation makes that harmless): structural rules above, plus
persona resolvable in the registry, persona-or-override timeout resolvable (R8),
`epic_id`/`feature`/`target_repo` non-blank. The workflow rejects an invalid graph
before any key is issued or worktree created — nothing dispatches (spec edge case).
