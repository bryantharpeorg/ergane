# Attempt 1 — US4: A finding names the repository, and the operator's own work is not it

## What changed

Three commits, tests first:

- `tests/test_us4_operator_work_not_charged.py` (new, T020–T024) — six tests at
  the detector surface: the FR-007 exclusion (pre-existing working-tree content,
  both untracked and *tracked-modified*, files nothing), its boundary (a write
  on top of pre-existing dirt still files), US4-S2 (an operator commit during
  the attempt carries its own paths; a write on top of the commit still files —
  one test, both halves), FR-008 (the finding carries `repo:<path>` in refs and
  names the repository in its summary), the escape control (both halves intact,
  counts exact), and US4-S5 (the detector leaves the operator's file
  byte-identical, HEAD unmoved, stash empty, file still untracked). Driven
  through `capture_start` / `compare_and_report` against a `tmp_path` runtime
  root, the pattern US2/US3 established.
- Both committed controls of 011-US1 scenario 3, edited openly in
  `tests/test_us1_detector.py` (T020): `test_operator_work_is_reported_and_untouched`
  now asserts the silence the override mandates and keeps the read-only half
  (US4-S5); `test_detector_runs_on_completed_agent_error_timeout_and_killed`
  moves each iteration's tracked write to *during* the attempt — a write before
  `capture_start` is now the excluded class — without weakening its closing
  assertions. Neither control was deleted or softened.
- `factory/workgraph/detector.py` (T025) — the start snapshot is the working
  tree, the same kind the teardown comparison takes, so content present when
  the attempt began is recorded as seen and files nothing. Modified tracked
  paths record content via `git hash-object` (read-only, no `-w`): `diff-index`
  prints an all-zero sha for unstaged modifications, so two working-tree
  snapshots could not otherwise agree on an untouched dirty tree. HEAD is
  recorded in the start snapshot; when HEAD moved during the attempt, teardown
  content is compared against the tree the new HEAD names — commit-carried
  paths file nothing, a write on top of the commit still files. The finding
  carries `repo:<path>` in refs and names the repository in its summary
  (FR-008), from the value `_write_snapshot` already captured and
  `compare_and_report` used to drop. Docstrings updated in the same diff
  (trap 12).
- `specs/011-agent-sandbox/spec.md` — the override recorded as `#` provenance
  lines inside the frontmatter fence only; scenario text, story titles,
  work-graph block and FR bodies byte-identical (trap 15).
- `tests/test_us3_boundary.py` — the fixture comment that explained the start
  snapshot as "the committed tree" corrected in the same story (T025).
- `docs/130-us4-operator-work-not-charged-evidence.md` (T026) — pasted
  transcripts: the T026 run holding both edited controls and the escape control
  together (8 passed), the full story files run (12 passed), the three new
  tests observed red against the pre-story module, the delta proof, and the
  011 diff stat.

## Verification

- Test-first observed red: the two FR-007 exclusion tests and the FR-008
  naming assertion failed against fe24a5f's detector on the exact clauses they
  enforce; the three controls passed before and after. Red transcript pasted in
  the evidence doc.
- `uv run pytest` (the repo's declared gate, `factory.yaml`): **5747 passed,
  58 skipped** in 508s, run after the main commit.
- `ergane spec derive specs/011-agent-sandbox --delta --target-repo $PWD -o
  $(mktemp)` → `nothing to build: all stories are already landed and
  unchanged` — the override did not reopen the landed story (operator step 6).
- Full story diff: 49,532 bytes against the 64 KiB refusal in
  `factory/verify/diffbounds.py`.
- Final detector suites re-run after a last `_content_sha` fallback fix
  (empty sha on unreadable content, the module's convention, rather than
  silently standing in committed content): 24 + 6 passed.

## Notes for the operator

- The snapshot-missing finding (built inline in `compare_and_report`) is
  untouched by this story; it carries epic/node refs already. FR-008's naming
  applies to the finding `_build_finding` constructs.
- Live operator-commit verification (operator step 4) needs a real dispatch
  and is yours; the committed tests hold both halves of that scenario at the
  detector surface.