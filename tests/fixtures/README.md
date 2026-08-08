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

## `workgraph/` — WorkGraph deriver corpus (005 T020, SC-006)

One directory per fixture spec, mirroring the `speckit/` layout. Every fixture is
the same feature — "Short Links", three stories (`US1`, `US2`, `US3`) and four
functional requirements (`FR-001`…`FR-004`) — with **byte-identical** stories and
requirement bullets. Only the `**Input**:` note and the `## Work Graph` section
differ, so a fixture that fails has exactly one explanation, and every rejection
fixture is a spec the criteria parser accepts: what the deriver refuses is the work
graph, never the spec around it.

| fixture | expectation |
|---|---|
| `valid_epic` | Derives. Three nodes in spec order — `us1` (`depends_on: []`, implements FR-001/FR-002), `us2` (depends on `us1`, `timeout: 7200`), `us3` (independent leaf). The one edge, the one independent root, and the one per-story override; the section also carries prose the fence-masked scan reads past. |
| `missing_story` | Rejected (`coverage`): the block declares `US1` and `US2` only. Error names `US3` — the story that would have become a silent orphan. |
| `unknown_story` | Rejected (`story_id`): all three stories are declared, plus `US4`, which the spec does not declare. Error names `US4`. |
| `unknown_fr` | Rejected (`implements`): `US2` implements `FR-404`, which the spec does not declare. Error names `US2`. |
| `unknown_dep` | Rejected (`depends_on`): `US2` depends on `US9`, which nothing declares. Error names `US2`. |
| `cycle` | Rejected (`acyclic`): `US2` waits on `US3` and `US3` on `US2`. Error names that cycle's members and *not* `US1`, which is outside it. |
| `self_dep` | Rejected (`depends_on`): `US2` depends on itself. Error names `US2`. |
| `no_section` | Rejected (`section_missing`): no `## Work Graph` section. The only header of that name sits inside a four-backtick fence wrapping a three-backtick YAML block — it is masked, so a scan that finds it would derive a graph from quoted prose. Names no story. |
| `two_blocks` | Rejected (`section_missing`): the section holds two fenced YAML blocks. The **first is the complete valid graph** and the second a leftover earlier revision, so a deriver that silently takes the first cannot be told from a correct one by its output — only the rule can. Names no story. |
| `non_mapping` | Rejected (`mapping`): the block is a YAML sequence of story ids, not a mapping of story id → declaration. Names no story. |
| `unknown_key` | Rejected (`unknown_key`): `US2`'s declaration carries `persona: debugger` — post-bootstrap grammar, refused rather than ignored. Error names `US2`. |
| `bad_timeout` | Rejected (`timeout`): `US2` declares `timeout: 0`. An integer, so a deriver that only type-checks accepts it; zero seconds is no deadline. Error names `US2`. |

Derivation is pure (text in → `WorkGraph` out), so these are read as text: `epic_id`,
`feature`, `specs_root` and `target_repo` come from the CLI, not from the fixture,
and the directory name is not parsed. `specs/003-merge-queue/spec.md` is the
real-world derive fixture (T030), the way `001-usage-tracking` is the parser's.

## `target_repo/` — gate-runner and diff-check corpus (T013)

A tiny but real target repo: `README.md`, `src/calc.py`, `docs/notes.md`, the
committed `factory.yaml`, and the `gates/` scripts every manifest invokes. It is
stored as plain files — a nested `.git` cannot be committed — and built into an
actual repository under `tmp_path` by `tests/target_repo.py`
(`build_target_repo`, `add_worktree`) or the `target_repo` / `node_worktree`
fixtures in `tests/conftest.py`. Each build is one commit on `main`, made with a
fixed identity and date and with the host's git configuration silenced, so gates
and diffs see the same repo on every machine.

A **variant** is the same skeleton with a different manifest at the root — never
different sources, so a failing case has exactly one explanation.

| variant | manifest | what it is for |
|---|---|---|
| `passing` | the fixture's own `factory.yaml` | Three gates in declaration order `lint` → `test` → `typecheck` (neither canonical nor alphabetical), all exit 0. Only `lint` declares a timeout, so the runner's 600s default is exercised by the same run. |
| `failing-gate` | `manifests/failing-gate.yaml` | `test` runs `gates/fail.sh` → exit **3**, evidence on both stdout (`test: 2 passed, 1 failed`) and stderr (`E       assert add(2, 2) == 5`). `typecheck` is declared *after* it, so "one result per declared gate" is observable. |
| `hanging-gate` | `manifests/hanging-gate.yaml` | `test` sleeps 30s under a **1s** declared timeout → TIMEOUT; prints `hang: started, sleeping` first, so partial output of a killed process is assertable. `typecheck` follows it. |
| `sigterm-defying-gate` | `manifests/sigterm-defying-gate.yaml` | Same 1s deadline against a script that traps SIGTERM and keeps its own child alive — only the SIGKILL escalation (R3) reclaims it. Bounded by the runner's grace period, so shorten it or expect a slow test. |
| `noisy-gate` | `manifests/noisy-gate.yaml` | One failing gate emitting ~106 KiB. `NOISE-HEAD first line of output` must be gone from a correctly capped 32 KiB tail; `NOISE-TAIL last line of output` must survive. |
| `env-probe` | `manifests/env-probe.yaml` | One passing gate that prints `LITELLM_MASTER_KEY=[…]`, `TELEGRAM_BOT_TOKEN=[…]`, `PATH`, `HOME` and `declare -x` from inside the child — the only place env scrubbing is observable. Set the secrets in the test process and assert `<unset>` (or at least the absence of the values) in `output_tail`. |
| `malformed-manifest` | `manifests/malformed.yaml` | Unparseable YAML (unclosed flow sequence) → the runner's single `CONFIG_ERROR` result. |
| `unknown-gate` | `manifests/unknown-gate.yaml` | Parses as YAML, fails schema validation (`build` is not a v1 gate name) → the other half of the runner's `CONFIG_ERROR` path. |
| `missing-manifest` | *(none — deleted before the commit)* | No `factory.yaml` at all: `CONFIG_ERROR`, verdict FAIL, never pass-by-default. |

For diff-check tests (T015), the built worktree starts clean: `README.md` and
`src/calc.py` are tracked files to modify, and `docs/notes.md` is a non-empty
tracked artifact for read-scope `expected_artifacts`. Untracked-only work is the
case where `git status --porcelain` is non-empty while `git diff HEAD` is empty —
both are consulted for exactly that reason.

Every gate script appends its name to `.factory-gate-order.log`, which the
skeleton's `.gitignore` excludes: execution order is recoverable
(`tests/target_repo.py:gate_order`) without a gate run leaving a diff that a
diff-check test would read as agent work.

## `roadmap/` — roadmap grammar + readiness corpus (009-US1, T003/T004)

One directory per fixture case, each holding a `specs/` tree of
`<spec-dir>/spec.md` files — the same layout as the real `specs/` root, so the
reader is exercised against the shape it ships against. Frontmatter is the new
field (FR-001/FR-002); the `**Status**:` prose every spec already carries is
dead text the reader never consults (plan § US1 trap).

| fixture | expectation |
|---|---|
| `valid` | Parses. Five specs: `001-alpha` attests `landed`; `002-bravo` has no frontmatter and reads `draft` (FR-002); `003-ready` is `ready` on the attested `001-alpha` (dispatchable); `004-blocked` is `ready` on the draft `002-bravo` (blocked, edge named); `006-deferred` is `deferred`. |
| `cycle` | Rejected (`cycle`): `001-a` ⇄ `002-b` is the cycle; `003-c` is outside it and must not appear in the finding. |
| `unknown_key` | Rejected (`unknown_key`): `001-x` carries `priority`, a key the closed grammar (`state`, `depends_on_landed`) does not admit. Names the key and the file. |
| `unknown_state` | Rejected (`unknown_state`): `001-x` declares `state: building` — only the system may say `building`. Names the value and the file. |
| `non_mapping` | Rejected (`non_mapping`): frontmatter is a YAML sequence, not a mapping. Names the file. |
| `dangling_dep` | Rejected (`dangling_dep`): `001-x` depends on `002-nowhere`, a spec directory this corpus does not hold. An edge to nothing can never be satisfied. |

The reader is pure over the corpus (the `test_derivation_opens_no_file`
pattern): it walks the `specs/` root it is handed and reads each `spec.md`, and
nothing else. Readiness is computed separately over the parsed roadmap
(`compute_readiness`); the observed-landed seam (FR-003) is exercised by
injecting a `landed_for` resolver, the surface US2 fills against Temporal + git.

## `remainders/` — hand-trimmed remainder graphs (016 SC-002 ground truth)

Byte-verbatim copies of the two `workgraph-remainder.json` files an operator
hand-trimmed on 2026-08-07 to resume split epics — 007 (us1/us2 landed,
us3/us4/us5 remaining, us3's satisfied edge deleted by hand) and 009 (us1
landed, us2/us3 remaining). Each was a manually computed delta and a D-025
violation; 016-delta-derivation's SC-002 requires `derive_delta` to reproduce
them node-for-node and edge-for-edge. They are the only record of what the
operator's judgment computed — banked here per 016 T001 before a `git clean`
could erase them.
