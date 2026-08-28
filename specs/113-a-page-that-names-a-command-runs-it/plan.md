# Implementation Plan: a page that names a command runs it

Drafted 2026-08-27 against ergane-buildout at 3e5c940. Every anchor below was
read from that commit. The three dated instances in spec.md's frontmatter — the
2026-08-14 vacuous sweep, the 2026-08-18 `nergane` README, the 2026-08-27
`ergane usage` — are inputs to this plan, not open questions.

## Requirements, numbered here

- **FR-001** — Every extracted command is parsed **as printed** by the CLI's own
  parser, obtained from `_build_parser()` (`factory/cli/main.py:100-122`), with
  no `--help` appended and no subprocess spawned. A command that argparse rejects
  fails the sweep, and the failure names what argparse named.
- **FR-002** — Parsing is the whole check. No `ergane` verb is executed by the
  sweep, ever. `run_help` (`tests/page_holds_true.py:194-195`) is replaced by the
  parse, not supplemented by it: keeping both means keeping a subprocess spawn
  per command for a check the parse already makes.
- **FR-003** — Placeholders are substituted before parsing, by shape rather than
  by exhaustive list: an angle-bracket token becomes a value of the kind its name
  implies (a path-shaped placeholder becomes a path, an id-shaped one an
  identifier). The extractor already recognises placeholders as a category
  (`page_holds_true.py:118-123`); this requirement is about what happens after
  they are recognised.
- **FR-004** — A required argument missing from a printed command is a failure
  naming that argument. This is the FR that would have caught `ergane usage`,
  and its test quotes `--by`.
- **FR-005** — The extractor raises `UnrecognizedCommandError`
  (`page_holds_true.py:30-31`) on any code span that is command-shaped and does
  not resolve, in place of today's `if not words or words[0] != "ergane":
  continue` (`:118`, the skip that shipped `nergane repo forget`).
  "Command-shaped" is defined by a rule in the code and pinned by tests naming
  both sides of the line.
- **FR-006** — A span that is genuinely not a command — a repository path, a
  config key such as `llm.mode`, an environment variable name, a model alias such
  as `demo/implementer`, a flag quoted on its own — is not treated as one. Both
  FR-005 and FR-006 are pinned with real examples taken from the three pages, not
  invented ones.
- **FR-007** — The anti-vacuity guard asserts the extractor found **every**
  command-shaped span on the page. Today it checks the list is non-empty and
  contains correctly-spelled `ergane install` and `ergane init`, which is a
  sample, and a sample is what let a page ship with half its commands dropped.
  The replacement counts.
- **FR-008** — `docs/onramp.html` is swept by the same three checks as
  `README.md` and `CLAUDE.md`, through the same helper. Its extractor reads
  `<code>` spans and `<pre class="well">` blocks, unescapes HTML entities before
  parsing (`&lt;`, `&gt;`, `&amp;` all appear in its command blocks), and ignores
  `<span class="cmt">` content, which is shell comments as the page's stylesheet
  marks them.
- **FR-009** — There is one extractor per convention and one parse check, shared
  by all three suites. A test asserts the three resolve the same callables by
  identity. The helper's founding rule is that a second parser in a second file
  is how two pages drift while both suites stay green (`page_holds_true.py:9-12`);
  a third page is when that rule is most likely to be broken for convenience.
- **FR-010** — The path check and the no-live-status check apply to the onramp
  page unchanged. Every repository path it cites must exist; it may state no
  status a live source already answers.

## What already exists, and where

| Piece | Where | State |
| --- | --- | --- |
| The shared helper and its stated contract | `tests/page_holds_true.py:1-12` | Three checks, named correctly; "resolves" is the word doing more than it can |
| Command extraction | `extract_commands`, `page_holds_true.py:118` | Skips any span whose first word is not exactly `ergane` — the `nergane` hole |
| The exception that exists for this | `UnrecognizedCommandError`, `:30-31` | Already defined for "close to, but not equal to, a known entrypoint"; the skip path never raises it |
| Code-span and fenced-bash readers | `code_spans`, `_FENCED_BASH`, `:35-45` | Markdown only — no HTML reader |
| The resolve check | `run_help`, `:194-195` | Appends `--help`; this is the defect |
| The CLI parser, importable and pure | `_build_parser()`, `factory/cli/main.py:100-122` | `add_subparsers(dest="noun")` at `:122`; `parse_args` raises `SystemExit(2)` on a missing required argument without dispatching anything |
| The two existing suites | `tests/test_readme.py`, `tests/test_claude_md.py` | 72 tests across these and `test_page_holds_true.py`, green on 2026-08-27 both before and after the `ergane usage` fix |
| The unswept page | `docs/onramp.html` | 500+ lines, ~22 distinct `ergane` invocations, corrected by hand on 2026-08-27 |

## Technical approach, story by story

### US1 — the sweep proves the invocation, not the verb

Replace `run_help` with a parse. `_build_parser()` returns a configured
`ArgumentParser`; `parse_args(argv)` on it raises `SystemExit` with the message
on stderr for a missing required argument, and returns a namespace otherwise —
without calling any handler, because argparse only stores the callable that
`main` later dispatches. Capture stderr, re-raise as a test failure carrying
argparse's own words. Placeholder substitution happens on the argv list before it
reaches the parser.

The parser is built once per session and reused; building it per command is
~22 × 3 constructions for no benefit.

### US2 — the sweep refuses what it cannot parse

Invert `extract_commands`'s skip. The rule becomes: a span is command-shaped if
its first word is `ergane` **or** is within a small edit distance of it, or if
the span's shape is `<word> <word>…` with no path separators, no `=`, and no
`/`. Command-shaped and unresolvable raises; not command-shaped is ignored. The
edit-distance clause is what catches `nergane` specifically, and the shape clause
is what catches a renamed entrypoint. The anti-vacuity guard becomes a count
derived from the same rule.

### US3 — the HTML page is swept like the others

One extractor beside the markdown ones, reading `<code>` and `<pre class="well">`
with an HTML parser rather than a regex — the page is real markup with nested
spans, and a regex over it is a fourth hole waiting. Unescape entities, drop
`<span class="cmt">` subtrees, hand the resulting text to the same command and
path readers US1 and US2 strengthened. A new `tests/test_onramp_html.py` mirrors
`test_readme.py`.

## Traps

**T1 — do not execute anything, and the pages make this concrete.** These pages
print `ergane build start`, which dispatches an epic; `ergane uninstall`, which
tears down a host; `ergane install`, which writes a config; and
`ergane repo forget`, which unregisters a repository. A sweep that "just runs
them to be sure" is a suite with the authority to destroy the machine it runs
on. It is also how this project acquired 8,131 orphaned test servers that OOM'd
the host. FR-002 is not a preference.

**T2 — this file has had three holes and every one of them was a skip.** The
2026-08-14 vacuous sweep, the 2026-08-18 `nergane`, the 2026-08-27
`--help`-suppressed required argument. Each was a case the checker declined to
judge rather than judged wrongly. When implementing, the question to ask of every
branch is not "is this correct" but "what does this branch decline to look at",
and the answer must be a test.

**T3 — the anti-vacuity guard must count, not sample.** Asserting the extracted
list is non-empty and contains two known-good commands is exactly what was in
place when the README shipped with two broken ones. The guard's job is to prove
the extractor did not silently drop anything, and only a count derived from the
same command-shaped rule can do that (FR-007).

**T4 — `--help` must not become the workaround.** If the parse check is
unpleasant to satisfy, the cheap fix is to write `ergane usage --help` on the
page, or to exempt a command with a comment. Both make the page worse to read in
order to make a test pass. US1-S2 exists to ensure the corrected form passes as
easily as the broken form fails; if that stops being true, the check is wrong,
not the page.

**T5 — do not regex the HTML.** `docs/onramp.html` has nested `<span>` inside
`<code>` inside `<pre>`, entity-escaped shell operators, and a `.cmt` class whose
content is comments. Every one of those breaks a regex in a way that reads as a
passing test. Use an HTML parser; the standard library has one, and the operator
session used exactly it on 2026-08-27 to well-form-check the page.

**T6 — one helper, three pages.** FR-009's identity assertion looks pedantic and
is the single most likely requirement to be quietly dropped, because copying the
extractor into the new HTML suite is faster than sharing it. The helper's own
docstring says why not. If the three suites stop sharing, this spec has produced
a third page that drifts independently — which is the situation it was written to
end.

**T7 — expect the strengthened sweep to find more.** When FR-001 first runs
across all three pages it may fail on lines nobody has looked at since they were
written. Fixing those is part of the story that introduces the check — a
strengthened test landing with an exemption list is the same skip in a new
costume. If a page line is genuinely un-parseable and genuinely correct, that is
a finding to file, not an exemption to add.

## Work Graph

```yaml
US1:
  implements: [FR-001, FR-002, FR-003, FR-004]
  depends_on: []
US2:
  implements: [FR-005, FR-006, FR-007]
  depends_on: []
  depends_on_merged: [US1]
US3:
  implements: [FR-008, FR-009, FR-010]
  depends_on: []
  depends_on_merged: [US2]
```

Chain depth 3, and deliberately so: all three stories edit
`tests/page_holds_true.py`, and a concurrent graph over one file buys conflicts,
not throughput.

## Sizing

Three stories, each small. US1 replaces one function and adds substitution. US2
inverts one branch and rewrites one guard. US3 adds one extractor and one suite.

**The risk is not size, it is the temptation to exempt.** Each story strengthens
a check across pages nobody has re-read recently, and each will surface work that
looks unrelated. The unit of value is "the check is honest"; a landed story whose
check carries a skip list has delivered nothing (plan T7).

## File contention

| story | owns |
| --- | --- |
| US1 | `tests/page_holds_true.py` (the resolve check), its tests in `tests/test_page_holds_true.py`, and any page line the new check fails |
| US2 | `tests/page_holds_true.py` (the extractor and the guard), the same test module |
| US3 | `tests/page_holds_true.py` (the HTML extractor), `tests/test_onramp_html.py` (new), and any onramp line the sweep fails |

All three own the same file. Strictly sequential.

## Dispatch hazards, for the operator running this epic

- **Re-derive the workgraph at dispatch** with `--target-repo "$PWD"` from the
  operator checkout; the committed artifact carries compile-time absolute paths.
- **This epic changes the tests that gate every other epic.** `test_readme.py`
  and `test_claude_md.py` run in every gate. A story that lands a check stricter
  than the tree satisfies turns every subsequent node's gate red for a reason
  that node cannot see. Each story must land with the pages already satisfying
  its own check (plan T7).
- **`docs/onramp.html` is also edited by spec 111 US2**, which brings its
  AppArmor procedure into agreement with the committed profile. If both epics are
  on the floor, land 111-US2 first or expect the onramp sweep to arrive at a page
  that is about to change.
- **Do not run `scripts/gate-commit` while an attempt is in flight.**

## Verification the operator will run, independent of the gate

The gate proves the new checks pass. It cannot prove they would have caught
anything, because by the time they run the pages are already correct.

After it lands, once, deliberately: put `ergane usage` back into `README.md`'s
table, run `tests/test_readme.py`, and watch it go red. Then put
`nergane repo forget` in a code span and watch it go red for the other reason.
Then revert both. A regression test that has never been shown to fail on the
regression it names is a test nobody has any reason to trust — and this file has
now shipped three that nobody had reason to trust.
