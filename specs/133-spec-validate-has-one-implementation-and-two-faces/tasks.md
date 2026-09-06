# Tasks: spec validate has one implementation and two faces

Read `plan.md` before starting. Trap 1 will cost you the estimate twice over: the
source finding counted six layers with five already exported, the first draft of
this spec counted eleven by counting `_validate_command`'s numbered comments, and
a run emits **twelve**. Ten of the twelve are implemented inside the CLI module,
and **four of those ten have no function to move** — they are written inline in
`_validate_command`: `prompt_assembly` at
`factory/cli/nouns/spec.py:557-574`, `slice_coverage` at
`factory/cli/nouns/spec.py:582-604`, `slice_contention` at
`factory/cli/nouns/spec.py:614-631` and the `sentinels` wrapper at
`factory/cli/nouns/spec.py:638-645`, plus the derivation refusal at
`factory/cli/nouns/spec.py:535`. Trap 2 enumerates all five; US3 is scoped from
that list and not from the one contention block.

Trap 9 is the one that decides whether this lands: **a changed message is a
regression here.** This is a move. Every refusal string, every severity, the
layer run order and the order of the names in the emitted `checked` sequence
survive unchanged. US1 commits the golden captures that make "unchanged"
checkable — two fixture trios and **six** artifacts: each trio's stdout, its
stderr and its `--json` document. Two trios because a run carrying a refusal
never prints the all-pass sentence; three streams because refusals, advisories,
skipped-layer lines and information notes are all printed to **stderr** and a
stdout-only capture holds none of them (trap 19). US4 keeps it that way.

Trap 7 is the one that decides whether a story fits: **do not redesign the
checkers' signatures while relocating them.** They accumulate into caller-owned
lists today and they still do afterwards, with the one exception trap 7 names:
`factory/cli/nouns/spec.py:1781` — `_check_evidence` also returns its report, and
that return must survive. A move that becomes a rewrite doubles into the
65,536-byte diff refusal — `DIFF_REFUSAL_THRESHOLD` at
`factory/verify/diffbounds.py:66`, which defaults to the judge's input allowance
`DIFF_INPUT_LIMIT` at `factory/verify/diffbounds.py:47` and is what actually
refuses a story unjudged.

Trap 17 is the one that decides whether the module still imports: **the import
direction is one-way.** `factory/cli/nouns/spec.py` imports from `factory.spec`;
`factory/spec/` may never import back. A moved body that reads a CLI-module name
means that name moves too — which is why US1's move of the finding type is
mandatory and why the two anchor grammars travel with US2 and the scenario-id
grammar and the vacuous registry with US5.

Every line range in `plan.md` is a coordinate in the 602a92c tree. **From US2
onward the file is hundreds of lines shorter than that: locate what you are
moving by symbol name, not by line number.**

Tests are written first and must fail before the implementation that satisfies
them. Every acceptance scenario is provable from the diff, which is all the judge
sees; runtime evidence is committed as pasted output.

`[P]` marks tasks that may be written in parallel within their phase. Tasks
without it touch a region an earlier task in the same phase is already editing.

Task ids are stable identifiers, not an ordering: T051 to T054 were added by a
later repair and sit at the end of the sub-section they belong to rather than
renumbering the ids the traps and the provenance already cite. Do the tasks in
the order they are written.

## Phase 1: User Story 1 — A typed report exists, and today's output is captured

### Tests for this story (write FIRST, must fail)

- [ ] T001 [P] [US1] (spec US1-S1, FR-001) Assert `factory.spec` imports and
      exports `SpecValidation` and a finding type carrying a layer name, a
      severity and a message, plus an overall verdict.
- [ ] T002 [P] [US1] (spec US1-S2, FR-002, trap 10) Assert the report holds
      refusals, advisories, information notes and skipped layers — each skip with
      its reason string — as four separate members. The skipped channel is what
      makes today's refusals useful; collapsing it into passed or failed destroys
      information the verb currently prints.
- [ ] T003 [P] [US1] (spec US1-S3, FR-002) **The control.** Assert a report
      carrying only information entries verdicts as a pass, preserving that
      channel's deliberate non-effect on the exit code.
- [ ] T004 [P] [US1] (spec US1-S4, FR-001, trap 7) Assert the finding type
      constructed with a layer and a message alone defaults its severity to
      `refusal` and accepts `advisory` — the same constructor shape
      `factory/cli/nouns/spec.py:483` — `_ValidateFinding` has today, so no
      relocated checker needs a signature edit.
- [ ] T005 [P] [US1] (spec US1-S6, FR-001, trap 17) Assert
      `factory/cli/nouns/spec.py` no longer defines `_ValidateFinding` — read the
      module source for the `class _ValidateFinding` statement — and that the
      object still bound under that local name has its `__module__` under
      `factory.spec`. Binding the import under the old name is what keeps the
      module's twenty-odd construction sites out of this story's diff.
- [ ] T006 [US1] (spec US1-S5, FR-014, trap 12, trap 13, trap 19) Assert the
      verb's stdout, its **stderr** and its `--json` document over **each** of the
      two committed fixture trios equal that trio's committed golden artifacts,
      with the repository root normalised out on both sides of every comparison.
      Six artifacts, six comparisons. Capture the two streams separately —
      `>stdout.txt 2>stderr.txt` — because `factory/cli/nouns/spec.py:710`,
      `factory/cli/nouns/spec.py:733` and `factory/cli/nouns/spec.py:739` print
      every finding, skip and information line to stderr while
      `factory/cli/nouns/spec.py:718` and `factory/cli/nouns/spec.py:725` print
      the all-pass sentence and the judge-evidence report to stdout.

### Implementation for this story

- [ ] T007 [US1] (FR-001, FR-002) Create the `factory/spec/` package and the typed
      report, modelling the finding on
      `factory/cli/nouns/spec.py:483` — `_ValidateFinding` but as a frozen
      dataclass with the same attribute names
      and the same keyword-only `severity` default. It must express the `advisory`
      severity the slice-contention layer assigns
      (`factory/cli/nouns/spec.py:617`), the information channel and the skipped
      channel with reasons, or the two forms disagree the first time either
      matters.
- [ ] T008 [US1] (FR-001, trap 17) Delete `factory/cli/nouns/spec.py:483-487` and
      import the new finding type into `factory/cli/nouns/spec.py`, binding it
      under the local name `_ValidateFinding` so no construction site in the
      module changes. This is mandatory and it belongs to US1: every relocated
      body from US2 onward constructs this type, and `factory/spec/` may never
      import it back out of the CLI module — the import block ends at
      `factory/cli/nouns/spec.py:62`, above where the type is bound today, so the
      cycle is an `ImportError` at interpreter start rather than a style problem.
- [ ] T009 [US1] (FR-014, trap 12, trap 13, trap 20) Add **two** synthetic
      fixture trios under `tests/`, each in its own parent directory holding
      nothing else — `factory/cli/nouns/spec.py:999` — `_check_frontmatter` reads
      `spec_dir.parent` as the specs root, so a trio dropped beside other files
      makes those files the roadmap. Add **one** fixture target repository both
      trios share: a directory committing an `ergane.yaml` that declares a single
      gate and carrying none of the files the trios cite — model it on
      `tests/test_102_unprovable_criteria.py:175` — `_repo`. Author the first
      trio to validate clean, with exactly one skipped layer and one information
      note: cite at least one `path:NN` anchor, and because the shared target
      repository carries none of the cited files
      `factory/cli/nouns/spec.py:1194` skips `anchor_resolution` alone —
      `factory/cli/nouns/spec.py:886` — `_check_symbol_anchors` skips only when
      `--target-repo` is not a readable directory
      (`factory/cli/nouns/spec.py:903`), so on this recipe it runs, appends
      `symbol_anchors` at `factory/cli/nouns/spec.py:996`, and the all-pass
      sentence still names "symbol anchors". Take the information note from an
      `ERGANE-TODO` sentinel, which `factory/cli/nouns/spec.py:638` turns into one
      `information` entry with no store and no absolute path. Author the second
      trio to carry a refusal and an advisory: make the refusal an **evidence**
      refusal, so US6-S4 has the exact string to compare against — that is what
      the shared repository's declared gate is for, since
      `factory/cli/nouns/spec.py:1815` skips the layer when the manifest declares
      none — and take the advisory from a declared acceptance scenario its
      `tasks.md` never names.
- [ ] T010 [US1] (FR-014, trap 11, trap 19) Capture the verb's stdout, its
      stderr and its `--json` document over **both** trios **before any layer body
      moves** and commit all six as golden artifacts, normalising the repository
      root to a placeholder on every one of them. Confirm the clean trio's
      **stdout** artifact contains the all-pass sentence —
      `factory/cli/nouns/spec.py:702`, the `if findings:` branch, means a run
      carrying a refusal never prints it, so the defective trio alone would freeze
      every shape except the one traps 4 and 5 rewrite — and confirm the defective
      trio's **stderr** artifact contains a line beginning
      `ergane spec validate — refusal:` and one beginning
      `ergane spec validate — advisory:`. Those two prefixes, the skipped-layer
      prefix and the information prefix appear on no other stream, and they are
      what T040 rewrites. The `fixes` layer's information note embeds the absolute
      store path, the evidence report the absolute manifest path and every
      skipped-layer reason the `--target-repo` string
      (`factory/cli/nouns/spec.py:1201`); a verbatim capture goes red on every
      other checkout, the merge-group build included.

### Verification for this story

- [ ] T011 [US1] Paste, as committed evidence, a constructed report and its
      verdict for each of the four channels, the head of each of the **six**
      golden artifacts showing the normalised repository root, the line of the
      clean trio's stdout artifact that carries the all-pass sentence, and the
      refusal and advisory lines of the defective trio's stderr artifact.

## Phase 2: User Story 2 — The anchor and symbol layers leave the CLI module

Locate every item below by symbol name. US1 has already removed the finding type
from this file, so the line numbers in `plan.md` § Sizing no longer point where
they did at 602a92c.

### Tests for this story (write FIRST, must fail)

- [ ] T012 [P] [US2] (spec US2-S1, FR-010, trap 17) Assert
      `factory/cli/nouns/spec.py` no longer defines `_check_anchor_resolution`,
      `_check_symbol_anchors`, `_symbol_spans`, `_line_hits_symbol`,
      `_read_citation_files`, `_spec_state`, `_severity_for_state`,
      `_SYMBOL_ANCHOR_RE`, `_DISPATCHABLE_STATES`, `_ANCHOR_RE` or
      `_BARE_LINE_RE`, by reading the module source rather than by importing
      names that would still resolve through the import. `_SYMBOL_ANCHOR_RE`
      (`factory/cli/nouns/spec.py:795`) and `_DISPATCHABLE_STATES`
      (`factory/cli/nouns/spec.py:800`) sit inside the span this story moves;
      `_ANCHOR_RE` and `_BARE_LINE_RE` are the module-level regexes read only
      from inside the moved checker — at `factory/cli/nouns/spec.py:1123` and
      `factory/cli/nouns/spec.py:1092` — and leaving any of the four behind makes
      the moved body reach back into the module it just left, which cannot
      import.
- [ ] T013 [P] [US2] (spec US2-S4, FR-010) Assert the anchor checkers the CLI
      module calls are the objects defined in `factory.spec` — compare
      `__module__` — so a re-declaration cannot pass as a move. Re-declaring the
      anchor grammar inside `factory/spec/` is the shortcut this forbids.
- [ ] T014 [P] [US2] (spec US2-S2, FR-010, trap 5, trap 7) Assert the moved
      functions keep their parameters and still append into caller-owned
      `findings`, `skipped` and `checked` lists, and that
      `_check_anchor_resolution` still appends `anchor_resolution` to `checked`
      at each of its four exits — `factory/cli/nouns/spec.py:1057`,
      `factory/cli/nouns/spec.py:1156`, `factory/cli/nouns/spec.py:1189` and
      `factory/cli/nouns/spec.py:1228` today — by driving the four conditions.

### Implementation for this story

- [ ] T015 [US2] (spec US2-S1, FR-010, trap 6, trap 7, trap 17) Move into
      `factory/spec/`, by name: the symbol-anchor regex `_SYMBOL_ANCHOR_RE`
      (`factory/cli/nouns/spec.py:795`) and `_DISPATCHABLE_STATES`
      (`factory/cli/nouns/spec.py:800`), both of which sit inside the span below
      and are read only by the checkers in it,
      `factory/cli/nouns/spec.py:803` — `_spec_state`,
      `factory/cli/nouns/spec.py:818` — `_severity_for_state`,
      `factory/cli/nouns/spec.py:825` — `_symbol_spans`,
      `factory/cli/nouns/spec.py:855` — `_line_hits_symbol` and
      `factory/cli/nouns/spec.py:886` — `_check_symbol_anchors` (the span
      `factory/cli/nouns/spec.py:793-996` at 602a92c);
      `factory/cli/nouns/spec.py:1011` — `_read_citation_files` and
      `factory/cli/nouns/spec.py:1023` — `_check_anchor_resolution` (the span
      `factory/cli/nouns/spec.py:1011-1228`); and the two module-level regexes
      `_ANCHOR_RE` and `_BARE_LINE_RE` with their `#:` comments
      (`factory/cli/nouns/spec.py:67-71`). Leave
      `factory/cli/nouns/spec.py:999` — `_check_frontmatter` where it is; it
      belongs to US5. 18,098 bytes of source, so about a 36 KB diff — keep the
      moves mechanical, change no string, and do not merge the four `checked`
      appends into one.
- [ ] T016 [US2] (FR-010) Import the moved names back into
      `factory/cli/nouns/spec.py` so `_validate_command` calls them exactly as it
      does today. The CLI still composes; that is US3's job to end.

### Verification for this story

- [ ] T017 [US2] (spec US2-S3, FR-006, trap 19) Paste, as committed evidence, the
      comparison of the verb's stdout, its stderr and its `--json` output over
      both fixture trios against US1's six golden artifacts — it must be empty on
      all three streams — and the
      `git diff --stat` line for this story showing the byte size of the move.
      The standing guard that keeps it empty is the golden test US1 committed in
      T006; name that test file by path in the evidence so a reader can re-run it.

## Phase 3: User Story 5 — The frontmatter, ledger, graph, persona, scenario and sentinel layers leave the CLI module

Locate every item below by symbol name. US1 and US2 have already removed the
finding type and roughly 420 lines from this file, so the `plan.md` § Sizing line
numbers are a map of what to move, not a place to cut.

### Tests for this story (write FIRST, must fail)

- [ ] T018 [P] [US5] (spec US5-S1, FR-011, trap 17) Assert
      `factory/cli/nouns/spec.py` no longer defines `_check_frontmatter`,
      `_check_fixes`, `_check_workgraph`, `_check_personas`, `_candidate_graph`,
      `_check_scenario_coverage`, `_scan_sentinels_in_trio`, `_tasks_text`,
      `_SCENARIO_ID_RE`, `_vacuous_registry` or `_STRUCTURAL_TIMEOUT_S`, and that
      the objects the CLI calls have `__module__` under `factory.spec`. The last
      three are module-level names read only from inside the moved bodies —
      `factory/cli/nouns/spec.py:1407` and `factory/cli/nouns/spec.py:1306` — and
      `_STRUCTURAL_TIMEOUT_S` is read only by `_vacuous_registry` itself.
- [ ] T019 [P] [US5] (spec US5-S2, FR-011, trap 4) **The control.** Drive
      `_check_fixes`'s **four** early returns and assert each is intact: an
      unreadable `spec.md` returns silently, adding to no list at all
      (`factory/cli/nouns/spec.py:1250`, whose comment says the frontmatter layer
      already reports it and this must not double-report); a spec with no `fixes:`
      key adds neither a `checked` nor a `skipped` entry
      (`factory/cli/nouns/spec.py:1255`); an absent store adds one `skipped` entry
      only (`factory/cli/nouns/spec.py:1267`); an unopenable store adds a
      different `skipped` entry only (`factory/cli/nouns/spec.py:1279`); and only
      the success path appends `fixes` to `checked`
      (`factory/cli/nouns/spec.py:1301`). The silent OSError path is the one a
      relocation "normalises" into a skip, because it is the one with no output to
      preserve, and normalising it double-reports the exact input that already
      refuses. A relocation that normalises any of the four changes the all-pass
      sentence for most of the corpus.
- [ ] T020 [P] [US5] (spec US5-S4, FR-011, trap 16) Assert every refusal string
      and parameter is unchanged, including that the moved `_check_fixes` still
      calls `resolve_factory_root()` — `factory/cli/nouns/spec.py:1257` today —
      rather than resolving the path itself. Draft 129 changes what that resolver
      returns and states it will not edit its callers.
- [ ] T021 [P] [US5] (spec US5-S5, FR-011, trap 18) Assert `_vacuous_registry` is
      reachable at its new home under `factory.spec` and still answers with empty
      `skills` for every persona the graph names — the assertion
      `tests/test_062_us3_skills.py:141` makes today through the CLI module, which
      is 062-US3 FR-009's standing proof and the only in-tree reference to the
      helper outside `factory/cli/nouns/spec.py`.

### Implementation for this story

- [ ] T022 [US5] (FR-011, trap 6, trap 7, trap 17) Move into `factory/spec/`, by
      name: `factory/cli/nouns/spec.py:462` — `_scan_sentinels_in_trio` (the span
      `factory/cli/nouns/spec.py:462-480` at 602a92c),
      `factory/cli/nouns/spec.py:779` — `_tasks_text`
      (`factory/cli/nouns/spec.py:779-790`),
      `factory/cli/nouns/spec.py:999` — `_check_frontmatter`
      (`factory/cli/nouns/spec.py:999-1008`),
      `factory/cli/nouns/spec.py:1231` — `_check_fixes`
      (`factory/cli/nouns/spec.py:1231-1301`),
      `factory/cli/nouns/spec.py:1304` — `_check_workgraph`,
      `factory/cli/nouns/spec.py:1311` — `_check_personas` and
      `factory/cli/nouns/spec.py:1330` — `_candidate_graph`
      (`factory/cli/nouns/spec.py:1304-1376`), and
      `factory/cli/nouns/spec.py:1379` — `_check_scenario_coverage` **alone** —
      its body ends at line 1416 and everything below that belongs to the evidence
      layer US6 moves (`factory/cli/nouns/spec.py:1379-1416`). Take with them the
      two module-level names only they read: the scenario-id grammar
      `_SCENARIO_ID_RE` with its `#:` comment
      (`factory/cli/nouns/spec.py:64-65`) and `_STRUCTURAL_TIMEOUT_S` with
      `factory/cli/nouns/spec.py:79` — `_vacuous_registry`
      (`factory/cli/nouns/spec.py:73-98`). 8,937 bytes of source, about an 18 KB
      diff.
- [ ] T023 [US5] (FR-011) Import the moved names back into
      `factory/cli/nouns/spec.py` so `_validate_command` calls them exactly as it
      does today — and so `factory/cli/nouns/spec.py:255` — `_derive_command`
      keeps calling `_scan_sentinels_in_trio` at
      `factory/cli/nouns/spec.py:257` for its sentinel gate. That gate's refusal
      text does not change; only where the helper lives does.
- [ ] T024 [US5] (spec US5-S5, FR-011, trap 18) Point
      `tests/test_062_us3_skills.py:141` at `_vacuous_registry`'s new home. Update
      the assertion to the new seam; do not delete it, and do not leave a shim in
      the CLI module to spare the edit.
- [ ] T051 [US5] (spec US5-S5, FR-011, trap 22) Point the other four in-tree
      tests that reach this family as attributes of `factory.cli.nouns.spec` at
      `factory.spec` too, keeping every assertion each of them makes:
      `tests/test_slice_coverage.py:290` (the `_ValidateFinding` annotation) with
      its four calls at `tests/test_slice_coverage.py:292`,
      `tests/test_slice_coverage.py:294`, `tests/test_slice_coverage.py:295` and
      `tests/test_slice_coverage.py:296`;
      `tests/test_prompt_assembly.py:387` with its four at
      `tests/test_prompt_assembly.py:389`, `tests/test_prompt_assembly.py:397`,
      `tests/test_prompt_assembly.py:398` and
      `tests/test_prompt_assembly.py:399`, **and** its source-reading guard at
      `tests/test_prompt_assembly.py:361`, which must now read the module that
      holds the layer rather than the CLI module it left, or 044 FR-004's
      duplicate-grammar proof starts guarding nothing;
      `tests/test_122_findings_store_isolation.py:31`, whose import is at
      **module scope** so an unbound name there is a collection error that takes
      the whole file down, with its call at
      `tests/test_122_findings_store_isolation.py:241`; and
      `tests/test_us1_registry_resolution.py:159`. Do not assume the import-back
      of T023 keeps them green: it does only while every moved name is re-bound
      under its old private name, and US3 removes the CLI's last call to nine of
      them, at which point the ordinary tidy-up of an unused import breaks all
      four at once. The declared gate is `uv run pytest -q` (`ergane.yaml:34`);
      there is no lint gate to catch it earlier.

### Verification for this story

- [ ] T025 [US5] (spec US5-S3, FR-006, trap 19) Paste, as committed evidence, the
      comparison of the verb's stdout, its stderr and its `--json` output over
      both fixture trios against US1's six golden artifacts — it must be empty on
      all three streams — and the transcript
      of the four `_check_fixes` early-return cases showing what each appended.
      Name US1's golden test file by path as the standing guard.

## Phase 4: User Story 6 — The judge-evidence layer leaves the CLI module

Locate every item below by symbol name. Three stories have already shortened this
file; `plan.md`'s span for this family, `factory/cli/nouns/spec.py:1419-1865`, is
past the end of the file you will actually open.

### Tests for this story (write FIRST, must fail)

- [ ] T026 [P] [US6] (spec US6-S1, FR-012) Assert `factory/cli/nouns/spec.py` no
      longer defines `_check_evidence`, `_JudgeEvidenceReport`, `_StoryCriteria`,
      `_BorderlineClause`, `_Declarations`, `_then_clauses`, `_runtime_markers`,
      `_names_a_declared_gate`, `_manifest_declares_no_gates`, `_declared_gates`,
      `_evidence_refusal`, `_borderline_warning`, `_story_criteria`,
      `_RUNTIME_MARKERS`, `_DIFF_EVIDENCE_RE` or `_PROVABLE_EXAMPLE`, and that
      the objects the CLI calls have `__module__` under `factory.spec`.
      `_RUNTIME_MARKERS` is the closed marker vocabulary
      `factory/cli/nouns/spec.py:1508` — `_runtime_markers` reads; it is assigned
      at `factory/cli/nouns/spec.py:1440`, which is above the span the draft of
      this plan gave, and it must travel with the reader that is its only
      consumer.
- [ ] T027 [P] [US6] (spec US6-S2, FR-012, trap 7) Assert the moved report type's
      `as_dict()` and `lines()` output are unchanged — the verb serialises the
      first into `--json` at `factory/cli/nouns/spec.py:693` and prints the second
      at `factory/cli/nouns/spec.py:724`, so both are stdout — and that the moved
      checker still **returns** that report as well as appending to the
      caller-owned lists. It is the one checker in the family that does both; a
      relocation that folds the return into the lists deletes the `judge_evidence`
      key.
- [ ] T028 [P] [US6] (spec US6-S4, FR-012, trap 19) Given a spec whose only
      defect is an unevidenceable Then-clause, assert the refusal the moved
      checker **appends to the caller-owned `findings` list** —
      `factory/cli/nouns/spec.py:1849` appends it; nothing raises — is the same
      string US1's golden capture of the defective trio's **stderr** recorded.
      The refusal line is on stderr and in the `--json` `findings[].message`; it
      is in no stdout artifact.

### Implementation for this story

- [ ] T029 [US6] (FR-012, trap 6, trap 7) Move the whole judge-evidence family
      into `factory/spec/` as one contiguous unit — the span
      `factory/cli/nouns/spec.py:1419-1865` at 602a92c, which begins at the
      `# --- criterion evidence (102-US1) ---` banner and holds `_RUNTIME_MARKERS`
      (`factory/cli/nouns/spec.py:1440`), `_DIFF_EVIDENCE_RE`
      (`factory/cli/nouns/spec.py:1481`), `_PROVABLE_EXAMPLE`
      (`factory/cli/nouns/spec.py:1488`),
      `factory/cli/nouns/spec.py:1491` — `_then_clauses`,
      `factory/cli/nouns/spec.py:1508` — `_runtime_markers`,
      `factory/cli/nouns/spec.py:1513` — `_names_a_declared_gate`,
      `factory/cli/nouns/spec.py:1520` — `_manifest_declares_no_gates`,
      `factory/cli/nouns/spec.py:1539` — `_Declarations`,
      `factory/cli/nouns/spec.py:1559` — `_declared_gates`,
      `factory/cli/nouns/spec.py:1588` — `_evidence_refusal`,
      `factory/cli/nouns/spec.py:1647` — `_StoryCriteria`,
      `factory/cli/nouns/spec.py:1656` — `_BorderlineClause`,
      `factory/cli/nouns/spec.py:1666` — `_JudgeEvidenceReport`,
      `factory/cli/nouns/spec.py:1748` — `_borderline_warning`,
      `factory/cli/nouns/spec.py:1768` — `_story_criteria` and
      `factory/cli/nouns/spec.py:1781` — `_check_evidence`. 18,391 bytes of
      source, about a 37 KB diff — the largest story in this spec and still inside
      the 65,536-byte bound. Do not start at the `_DIFF_EVIDENCE_RE` comment:
      `_RUNTIME_MARKERS` sits above it and belongs to this family, not to US5's.
- [ ] T030 [US6] (FR-012) Import the moved names back into
      `factory/cli/nouns/spec.py` so `_validate_command` calls the checker, binds
      its returned report and prints it exactly as it does today.

### Verification for this story

- [ ] T031 [US6] (spec US6-S3, FR-006, trap 19) Paste, as committed evidence, the
      comparison of the verb's stdout, its stderr and its `--json` output over
      both fixture trios against US1's six golden artifacts — it must be empty on
      all three streams — naming US1's golden
      test file by path as the standing guard.

## Phase 5: User Story 3 — The verb is a renderer over one composition

### Tests for this story (write FIRST, must fail)

- [ ] T032 [P] [US3] (spec US3-S1, FR-003, trap 8) Assert
      `validate_spec(spec_dir, *, target_repo, specs_root)` returns the typed
      report with **no** `argparse.Namespace` constructed and **no** stdout
      captured. Do not build on
      `factory/cli/nouns/spec.py:275` — `validate_spec_command`: it has the right
      name and the wrong shape, and it
      exists only so `build ship` (`factory/cli/nouns/build.py:1039`) could stream
      the same stdout.
- [ ] T033 [P] [US3] (spec US3-S2, FR-004, trap 2) Drive the library form over
      specs defective in each of the five ways a re-composing consumer misses
      today — a stale line anchor, a symbol anchor, an unresolvable `fixes:` key,
      a missing judge-evidence answer and a slice contention — and assert each is
      present in the returned report, the contention one at severity `advisory`.
      Write these five trios into a `tmp_path` tree at test time rather than
      committing them: `tests/test_anchor_resolution.py` already works this way
      and says why in its docstring — "Every fixture is a supplied tmp tree, never
      this repository, because the anchors in `factory/` move". Fifteen committed
      files would also put this story's diff at risk of trap 6. **Three of the
      five need a fixture a bare trio cannot carry, and skip silently without it
      (trap 20):** the `fixes` trio needs a real store under `tmp_path` — model
      `tests/test_089_validate_checks_fixes.py:32` — `_own_findings_store`, since
      `factory/cli/nouns/spec.py:1260` skips rather than refuses when there is no
      store; the judge-evidence trio needs a `--target-repo` committing an
      `ergane.yaml` that declares a gate — model
      `tests/test_102_unprovable_criteria.py:175` — `_repo`, since
      `factory/cli/nouns/spec.py:1815` skips when the manifest declares none; and
      the stale-anchor trio needs its cited `.py` file to exist under the target
      repo, since `factory/cli/nouns/spec.py:1194` skips the whole layer when no
      cited path can be read. A skipped layer does not fail this assertion; it
      makes it vacuous.
- [ ] T034 [P] [US3] (spec US3-S3, FR-005, trap 3) **The control.** Assert the
      report's `checked` sequence equals the order the verb emits today —
      `frontmatter`, `workgraph_derivation`, `persona_registry`,
      `scenario_coverage`, `fixes`, … — which is the seed at
      `factory/cli/nouns/spec.py:504` followed by the appends, and is **not** the
      order the layers run in. Tidying it into run order is invisible on stdout —
      `factory/cli/nouns/spec.py:753` — `_all_pass_phrases` tests `checked` for
      membership only, at `factory/cli/nouns/spec.py:770`,
      `factory/cli/nouns/spec.py:772` and `factory/cli/nouns/spec.py:774`, and
      never reads its order — so this assertion and T036's JSON golden are the
      only two things that catch it.
- [ ] T035 [P] [US3] (spec US3-S4, FR-006, trap 19) Assert the verb's stdout
      **and its stderr** over **each** of US1's two fixture trios each equal that
      trio's golden artifact for that stream byte for byte, and that its exit code
      is unchanged. The clean trio's stdout carries the all-pass sentence; the
      defective trio never prints one. The four rendered prefixes T040 rewrites
      live only in the stderr artifacts, so the stdout comparison alone would pass
      over a renderer that changed every one of them.
- [ ] T036 [P] [US3] (spec US3-S5, FR-007, trap 21) Assert `--json` over each
      fixture trio equals that trio's golden JSON artifact byte for byte. The dict
      is assembled inline at `factory/cli/nouns/spec.py:677` and printed at
      `factory/cli/nouns/spec.py:699` today, and both its key order and the
      deliberate absence of `judge_evidence`
      (`factory/cli/nouns/spec.py:693`) are part of what "byte for byte" means.
      This is also the assertion that catches a tidied `checked` order, which
      changes nothing on stdout.
- [ ] T037 [P] [US3] (spec US3-S6, FR-008, trap 2) Assert the CLI module
      constructs no finding of its own. There are **five** such constructions to
      account for, not one, and a `def _check_` sweep finds none of them:
      `factory/cli/nouns/spec.py:535` (layer `workgraph`, the `DerivationError`
      refusal), `factory/cli/nouns/spec.py:559` (`prompt_assembly`),
      `factory/cli/nouns/spec.py:590` (`slice_coverage`, and the line that routes
      on `entry.informational`), `factory/cli/nouns/spec.py:617`
      (`slice_contention`) and `factory/cli/nouns/spec.py:640` (`sentinel`).
      Assert on the module source, so a construction that moved into a helper
      still in the CLI module does not pass.
- [ ] T038 [P] [US3] (spec US3-S7, FR-013, trap 14) Assert the demonstration's
      validate stage obtains its verdict through the library form and that the
      lines it prints are unchanged. `factory/cli/install.py:1071` — `_run_cli`
      exists to stream labeled output and
      `tests/test_110_us1_demo_first_boot.py:425` asserts that argv path returns
      0; update that assertion to the new seam rather than deleting it.
- [ ] T052 [P] [US3] (spec US3-S8, FR-015, trap 23) **The control on the
      controls.** Assert that for a spec the layer refuses, the layer-disabled
      run and the layer-enabled run return **different** findings — once for the
      `fixes` helper
      `tests/test_089_validate_checks_fixes.py:300` — `_validate_without_fixes_layer`
      and once for the evidence helper
      `tests/test_102_unprovable_criteria.py:425` — `_validate_without_evidence_layer`.
      Both rebind the layer on
      `factory.cli.nouns.spec` today
      (`tests/test_089_validate_checks_fixes.py:307`,
      `tests/test_102_unprovable_criteria.py:432`) and both keep working through
      US5 and US6, because `_validate_command` resolves that module global at
      call time. The moment the verb is a renderer over `factory.spec`, the
      rebinding lands on a name nothing calls, both runs become the same run and
      both corpus comparisons pass over a hundred and thirty specs while
      covering nothing —
      `tests/test_102_unprovable_criteria.py:458` says out loud that with the
      layer disabled both runs are the same run. This assertion is what makes
      that failure red instead of green.
- [ ] T053 [P] [US3] (spec US3-S9, FR-015, FR-008, trap 22) Assert
      `factory/cli/nouns/spec.py` no longer imports the relocated layer
      functions at all — read the module source — and that no file under
      `tests/` reaches one of them as an attribute of `factory.cli.nouns.spec`.
      The four files T051 re-pointed and the two helpers T054 re-points are the
      whole in-tree set at 602a92c; this assertion is what stops the next one
      being written.

### Implementation for this story

- [ ] T039 [US3] (FR-003, FR-004, FR-005, trap 2) Add `validate_spec` to
      `factory/spec/`, composing all twelve layers in today's run order and
      building the typed report from the caller-owned lists at the end. Four of
      the twelve have no function to move and must be carried across as written,
      wrapper and all: `prompt_assembly` (`factory/cli/nouns/spec.py:557-574`,
      finding at `factory/cli/nouns/spec.py:559`, `checked` append at
      `factory/cli/nouns/spec.py:560`, skip-reason string in its `else`),
      `slice_coverage` (`factory/cli/nouns/spec.py:582-604`, finding at
      `factory/cli/nouns/spec.py:590`, the `entry.informational` routing, a
      two-way skip reason), `slice_contention`
      (`factory/cli/nouns/spec.py:614-631`) and the `sentinels` wrapper around
      the scanner US5 moved (`factory/cli/nouns/spec.py:638-645`, with its
      unconditional `checked.append`); plus the derivation refusal at
      `factory/cli/nouns/spec.py:535`. Carry two spellings verbatim rather than
      normalising them: the derivation finding's layer is `workgraph` while
      `checked` carries `workgraph_derivation` (seeded at
      `factory/cli/nouns/spec.py:506`), and the sentinel note's layer is
      `sentinel` while `checked` carries `sentinels`
      (`factory/cli/nouns/spec.py:645`). Both spellings are rendered — the
      finding's in the `[layer]` prefix and in `--json` `findings[].layer`
      (`factory/cli/nouns/spec.py:682`) — so folding either pair into one name
      is an output change FR-005 forbids and neither golden trio happens to
      catch.
- [ ] T040 [US3] (FR-006, FR-007, FR-008, trap 19, trap 21) Reduce
      `factory/cli/nouns/spec.py:490-750` — `_validate_command` to a renderer over
      `validate_spec`, and replace the inline dict at
      `factory/cli/nouns/spec.py:677` with a serialisation of the report that
      keeps that dict's key order and leaves `judge_evidence` absent rather than
      null when there is no report. Every printed line,
      `factory/cli/nouns/spec.py:753` — `_all_pass_phrases` included, stays where
      it is — **and on the stream it is on today**: findings, skipped layers,
      information notes and the sentinel count to stderr
      (`factory/cli/nouns/spec.py:710`, `factory/cli/nouns/spec.py:733`,
      `factory/cli/nouns/spec.py:739`, `factory/cli/nouns/spec.py:747`), the
      all-pass sentence and the judge-evidence report to stdout
      (`factory/cli/nouns/spec.py:718`, `factory/cli/nouns/spec.py:725`). This is
      the task US1's stderr goldens exist to fail against.
- [ ] T041 [US3] (FR-013, trap 14) Convert `factory/cli/install.py:1028`, which
      runs `factory/cli/install.py:1078` — `_spec_validate_argv` back through the
      CLI entry point from inside the package, to reach the library form through
      the same renderer, so the demonstration still prints the verdict a stranger
      is watching for.
- [ ] T054 [US3] (FR-015, trap 23) Re-point the two corpus controls at the
      module the composition actually reads:
      `tests/test_089_validate_checks_fixes.py:300` — `_validate_without_fixes_layer`
      and
      `tests/test_102_unprovable_criteria.py:425` — `_validate_without_evidence_layer`.
      Each rebinds a name on
      `factory.cli.nouns.spec` and then compares the whole corpus with and
      without the layer; after T040 that rebinding disables nothing. Do not
      delete either helper and do not weaken its assertion — the corpus
      comparison is the only coverage those two layers have outside their own
      fixtures. T052 is the assertion that proves the re-point took.

### Verification for this story

- [ ] T042 [US3] Paste, as committed evidence, the diff between the pre-change and
      post-change output sweep described in `plan.md` step 4, captured on both
      streams — it must be empty on each — the demonstration's validate stage
      output before and after T041, and the transcript of the two re-pointed
      corpus controls of T054 showing a **differing** verdict on the spec each
      layer refuses, which is what proves they are still disabling something.

## Phase 6: User Story 4 — The two forms agree, provably

### Tests for this story (write FIRST, must fail)

- [ ] T043 [P] [US4] (spec US4-S1, FR-009) Drive both forms over every spec
      directory in `specs/` and assert the same verdict for each.
- [ ] T044 [P] [US4] (spec US4-S2, FR-009) Assert they agree on the per-layer
      findings and severities, not merely on the overall pass or fail. Agreement
      on the verdict alone would let a severity drift silently, which is the exact
      failure this story exists to prevent.
- [ ] T045 [P] [US4] (spec US4-S3, FR-009, trap 12) Assert the corpus is
      enumerated by globbing `specs/` at call time. A test that lists spec
      directories literally passes today and stops covering new specs the moment
      one is minted, which happens weekly here.
- [ ] T046 [P] [US4] (spec US4-S4, FR-009, trap 15) Assert the CLI face is driven
      in-process through the CLI entry point with stdout captured, not by spawning
      a subprocess per spec. There are more than 130 spec directories, and this
      repository already has three tests accounting for over half the suite's wall
      time.

### Implementation for this story

- [ ] T047 [US4] (FR-009) Add the corpus parity test. This is the free correctness
      check PR-8 named: the corpus is on disk, and it is the cheapest way to
      guarantee the two faces never disagree.

### Verification for this story

- [ ] T048 [US4] Paste the parity test's summary line over the full corpus, naming
      the number of specs compared, together with its pasted wall-clock time.

## Verification

- [ ] T049 The full gate command passes green.
- [ ] T050 The operator sequence in `plan.md` § "Verification the operator will
      run" is executed end to end. **Step 0 — confirming no stale
      `workgraph.json` sits beside this spec — and step 1 — capturing the
      corpus-wide output sweep BEFORE dispatching US1 — cannot be done after the
      fact.** Step 0 is what stops a four-node graph compiled from the draft being
      dispatched against a six-story spec; step 1 is what makes the empty diffs at
      steps 3 and 4 mean something.
