# Tasks: a page that names a command runs it

**Input**: `spec.md` and `plan.md` in this directory, both drafted 2026-08-27
against ergane-buildout at 3e5c940.

Tests are written first and must fail before their implementation task runs.
`[P]` marks tasks that can proceed in parallel within their story because they
touch independent test functions; no `[P]` spans stories, because all three edit
`tests/page_holds_true.py`.

## Phase 1: User Story 1 — The sweep proves the invocation, not the verb

### Tests for this story (write FIRST, must fail)

- [ ] T001 [US1] (spec US1-S1, FR-001, FR-004) Missing-required-argument test,
  added to `tests/test_page_holds_true.py`: the parse check rejects the argv
  `["ergane", "usage"]` and the failure names `--by`. Quote the argument name in
  the assertion — this is the exact line that shipped in two pages on
  2026-08-27, and a test that only asserts "something failed" would have passed
  against a checker that rejected it for the wrong reason.
- [ ] T002 [P] [US1] (spec US1-S2, FR-001) Accepted-form test: the parse check
  accepts `["ergane", "usage", "--by", "epic"]`. The corrected form must pass as
  readily as the broken form fails, or pages start carrying `--help` to appease
  the suite (plan T4).
- [ ] T003 [P] [US1] (spec US1-S3, FR-003) Placeholder test: one placeholder of
  each shape that actually appears across the three pages — a path-shaped
  `<spec-dir>` and `<target-repo-path>`, an id-shaped `<epic-id>`, a slug-shaped
  `<repo-slug>` — is substituted and the resulting argv parses. Take the
  placeholders from the pages rather than inventing them.
- [ ] T004 [P] [US1] (spec US1-S4, FR-002) No-execution test: drive the parse
  check with a subprocess seam and assert it is **never** called, for every
  command on every swept page. These pages print `ergane build start` and
  `ergane uninstall`; a sweep that runs them dispatches an epic and tears down a
  host (plan T1).

### Implementation for this story

- [ ] T005 [US1] (FR-001, FR-002, FR-003, FR-004) Replace `run_help`
  (`tests/page_holds_true.py:194-195`) with a parse against `_build_parser()`
  (`factory/cli/main.py:100-122`), building the parser once per session;
  substitute placeholders on the argv before parsing; surface argparse's own
  message on rejection. Remove `run_help` rather than keeping both — a retained
  subprocess spawn is a retained opportunity to use it.

### Verification for this story

- [ ] T006 [US1] (spec US1-S1, spec US1-S2, SC-001) Paste into the PR: the sweep
  rejecting `ergane usage` with argparse's message, the same sweep accepting
  `ergane usage --by epic`, and the full-suite before-and-after counts.

## Phase 2: User Story 2 — The sweep refuses what it cannot parse

### Tests for this story (write FIRST, must fail)

- [ ] T007 [US2] (spec US2-S1, FR-005) Near-miss test: the extractor raises
  `UnrecognizedCommandError` (`page_holds_true.py:30-31`) on the code span
  `nergane repo forget` — the exact string that shipped in the released README on
  2026-08-18 under a green suite — and the message names the span.
- [ ] T008 [P] [US2] (spec US2-S2, FR-005) Nonexistent-verb test: the sweep fails
  on `ergane build landed`, the 2026-08-14 instance, naming the verb.
- [ ] T009 [P] [US2] (spec US2-S3, FR-007) Counting-guard test: add a
  command-shaped span to a fixture page and assert the anti-vacuity guard's count
  increases. A guard that checks the list is non-empty and contains two
  known-good commands is what was in place for both prior holes; this test is
  what makes it a count instead of a sample (plan T3).
- [ ] T010 [P] [US2] (spec US2-S4, FR-006) Not-a-command test: spans that must
  **not** be treated as commands, each taken from a real page — a repository path
  (`.specify/memory/constitution.md`), a config key (`llm.mode`), an environment
  variable (`UPSTREAM_MODEL_API_KEY`), a model alias (`demo/implementer`), and a
  bare flag (`--default-branch`). Each is ignored, and none fails the sweep.

### Implementation for this story

- [ ] T011 [US2] (FR-005, FR-006, FR-007) Invert the skip at
  `page_holds_true.py:118`: define command-shaped in code, raise
  `UnrecognizedCommandError` on command-shaped-and-unresolvable, ignore the rest,
  and rewrite the anti-vacuity guard as a count derived from the same rule.

### Verification for this story

- [ ] T012 [US2] (spec US2-S1, SC-002) Paste into the PR: the sweep failing on
  `nergane repo forget`, the guard's count before and after T009's fixture
  addition, and the full-suite before-and-after counts.

## Phase 3: User Story 3 — The HTML page is swept like the others

### Tests for this story (write FIRST, must fail)

- [ ] T013 [US3] (spec US3-S1, FR-008) HTML extraction test, in a new
  `tests/test_onramp_html.py`: the extractor finds commands inside `<code>` spans
  and `<pre class="well">` blocks of `docs/onramp.html`, with entities unescaped
  — the page writes `&lt;spec-dir&gt;` and `&amp;` inside command blocks, and a
  parser fed raw markup fails on the wrong thing. Use an HTML parser, not a
  regex (plan T5).
- [ ] T014 [P] [US3] (spec US3-S2, FR-008) Comment-stripping test:
  `<span class="cmt">` content inside code blocks is not parsed as a command. The
  page's every code well carries them.
- [ ] T015 [P] [US3] (spec US3-S3, FR-010) Path test: every repository path the
  onramp page cites exists, through the same path extractor the other two pages
  use.
- [ ] T016 [P] [US3] (spec US3-S4, FR-009) Shared-helper test: the three suites —
  `test_readme.py`, `test_claude_md.py`, `test_onramp_html.py` — resolve the same
  command extractor and the same parse check **by identity**. Copying the
  extractor into the new suite is faster and is the thing this assertion exists
  to prevent (plan T6).

### Implementation for this story

- [ ] T017 [US3] (FR-008, FR-009, FR-010) Add the HTML extractor to
  `tests/page_holds_true.py` beside the markdown readers, using the standard
  library's HTML parser; add `tests/test_onramp_html.py` mirroring
  `tests/test_readme.py` and sharing every check.

### Verification for this story

- [ ] T018 [US3] (spec US3-S1, SC-003) Paste into the PR: the onramp page's
  full extracted command list with each one's parse verdict, and the full-suite
  before-and-after counts.

## What no task here can prove

Every task above proves the new checks pass against a tree that already satisfies
them. **None of them proves the checks would have caught anything**, because by
the time they run the pages are correct — `README.md` was fixed by hand on
2026-08-27, and `docs/onramp.html` with it.

That proof is the operator verification in `plan.md`, and it is the one step of
this spec that matters most: put `ergane usage` back into the README table and
watch `tests/test_readme.py` go red; put `nergane repo forget` in a code span and
watch it go red for the other reason; revert both. This helper has now shipped
three checks that nobody had reason to trust, each green over a real defect. A
fourth that has never been observed failing would be the same thing again.

One thing tasks.md deliberately does not do: carry an exemption list. If the
strengthened sweep fails a page line nobody has re-read since it was written, the
story that introduced the check fixes the line (plan T7). A skip list is the same
hole in a new costume, and it is how all three prior instances survived.
