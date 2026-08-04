# Test fixtures

## `speckit/` — criteria-parser corpus (T007, SC-001)

One directory per fixture feature, each holding a `spec.md`, mirroring the real
`specs/<feature>/spec.md` layout so `CriteriaSet.feature` is the directory name
(data-model.md). Between them the fixtures exercise every production of the Spec Kit
grammar the parser keys on (architecture §2) plus every validation rule.

| fixture | expectation |
|---|---|
| `010-full-grammar` | Parses. 3 stories + 4 functional requirements. `US1` (P1, "Borrow a book") 3 scenarios — `US1-S2` has two `**And**` steps after `**Then**`, `US1-S3` wraps across lines; `US2` (P2) 2 scenarios; `US3` (P3) 1 scenario. `FR-001`/`FR-003`/`FR-004` use MUST, `FR-002` uses SHALL, `FR-004` wraps across lines. The markdown fence in US2's body and the bare fence under the FR list are masked, so `US8`, `FR-900` and `FR-901` never appear. Bold bullets under **Key Entities** and **Measurable Outcomes** (`SC-###`) are not requirements. |
| `011-fenced-decoys` | Parses. Exactly 1 story (`US1`, 1 scenario) + 1 functional requirement (`FR-001`), both declared *after* three fenced blocks — proving fences close as well as open. `US5`, `US6`, `US7`, `FR-555`, `FR-666`, `FR-777` are all fence-masked. Covers fences with a `markdown` info string, a `text` info string, and none. |
| `012-story-without-scenarios` | Rejected: `US2` declares no `**Acceptance Scenarios**:` section. Error names `US2` (not `US1`, which is well-formed). |
| `013-story-empty-scenario-list` | Rejected: `US2` declares `**Acceptance Scenarios**:` with no numbered items — the shape a half-filled template leaves. Error names `US2`. |
| `014-fr-missing-modal` | Rejected: `FR-002`'s body carries neither MUST nor SHALL. Error names `FR-002`; `FR-001` (MUST) and `FR-003` (SHALL) are well-formed. |
| `015-scenario-without-keywords` | Rejected: the second acceptance-scenario item of `US1` is bold-formatted prose (`**Note**: …`) with no `**Given**`/`**When**`/`**Then**`/`**And**` step — a parser that only checks "contains some bold" wrongly accepts it. Error names `US1-S2`; items 1 and 3 are well-formed. |
| `016-duplicate-story-key` | Rejected: two headers declare User Story 2 (different titles and priorities). Error names `US2`. |
| `017-duplicate-fr-key` | Rejected: `FR-002` is declared twice with different bodies. Error names `FR-002`. |
| `001-usage-tracking` | Real-world fixture (SC-001): a byte-verbatim copy of `specs/001-usage-tracking/spec.md`. Parses with 3 stories (`US1` 5 scenarios, `US2` 4, `US3` 2) and 12 functional requirements `FR-001`…`FR-012`. Its `### Key Entities` and `SC-###` bullets must not be mistaken for requirements. |

Requesting a requirement key that no fixture declares (e.g. `FR-404`) is the
"unknown requested key" validation case; `010-full-grammar` serves for it.

## `target_repo/` — gate-runner corpus

Populated by T013.
