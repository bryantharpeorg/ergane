---
state: draft
# DRAFTED 2026-08-27 by the operator session, against ergane-buildout at 3e5c940.
# Every file:line below was read from that commit and verified before drafting.
#
# WHY THIS EXISTS, WITH THE RECEIPT. On 2026-08-27 an operator session verified
# `docs/onramp.html` against the shipped 0.5.0 CLI and found four defects. One of
# them was a command that cannot run:
#
#     $ ergane usage
#     ergane usage: error: the following arguments are required: --by
#
# `README.md` carried the same broken line, in its own "Asking the system about
# itself" table. `tests/test_readme.py` was green. It is green because
# `run_help` (`tests/page_holds_true.py:194-195`) appends `--help` and checks the
# exit status:
#
#     def run_help(command): return subprocess.run(command + ["--help"], …)
#
# `ergane usage --help` exits 0. `ergane usage` exits 2. The sweep proves a VERB
# EXISTS. It has never proved that the invocation as printed would run, and the
# distinction is the whole difference between a page that documents a CLI and a
# page that names one.
#
# THIS IS THE THIRD HOLE IN THE SAME HELPER, and the pattern is now the finding
# rather than any one instance:
#   - 2026-08-14: `docs/claude-md-command-sweep-is-vacuous` — the sweep had
#     masked `ergane build landed`, a verb that does not exist.
#   - 2026-08-18: the README shipped containing `nergane repo forget` and
#     `nergane worker uninstall` (a stray leading `n`) and the sweep passed.
#     `extract_commands` does `if not words or words[0] != "ergane": continue`,
#     so anything not starting with the exact token is silently skipped; the
#     anti-vacuity guard only checked the extracted list was non-empty and
#     contained correctly-spelled `ergane install` / `ergane init`.
#   - 2026-08-27: `ergane usage`, in two pages at once, through `run_help`.
# The general lesson was written down after the second one and is quoted here
# because this spec is its implementation: **a sweep that skips what it cannot
# parse will always pass; it must fail on anything that looks like its subject
# and does not resolve.**
#
# THE THIRD PAGE IS NOT SWEPT AT ALL. `docs/onramp.html` has no test. `README.md`
# has `tests/test_readme.py` and `CLAUDE.md` has `tests/test_claude_md.py`, both
# over `tests/page_holds_true.py`; its extractors read markdown code spans and
# fenced bash blocks (`_FENCED_BASH`, `page_holds_true.py:35`), and the onramp
# page is HTML. It drifted four ways in a single day and nothing noticed, because
# nothing was looking.
#
# WHY A PARSE AND NOT A RUN. The obvious fix — execute what the page prints — is
# refused. `ergane build start` dispatches an epic. `ergane uninstall` tears down
# a host. `ergane install` writes a config. A documentation sweep must never
# acquire the authority to do any of that, and a suite that shells real verbs is
# how this project acquired 8,131 orphaned test servers. `argparse` gives the
# third option: `_build_parser()` (`factory/cli/main.py:100-122`) can parse an
# argv without dispatching it, and a missing required argument raises there. That
# is exactly the defect class that shipped, caught with no side effects at all.
#
# NOT IN SCOPE. This spec does not rewrite the pages, does not add a fourth page,
# and does not change any CLI signature. If the strengthened sweep finds further
# broken lines when it first runs — it may — fixing those is part of the story
# that introduces the check, and nothing beyond the pages already swept.
---

# Feature Specification: a page that names a command runs it

**Created**: 2026-08-27
**Depends on**: nothing. US1 → US2 → US3 are sequential; all three edit
`tests/page_holds_true.py`.

## The gap, stated precisely

Three pages describe this CLI to a new operator. Two are swept by a helper that
cannot detect the defect that shipped in both of them, and the third is not swept
at all.

The helper's docstring states its own contract:

```
tests/page_holds_true.py:1-12
    - every command the page names still resolves,
    - every path the page cites still exists,
    - the page states no status a live source already answers.
```

"Resolves" is doing work it cannot bear. `run_help` appends `--help`, which
suppresses every required-argument check argparse would otherwise make, so a
printed `ergane usage` and a printed `ergane usage --by epic` are
indistinguishable to the sweep — and only one of them runs.

Below that sits an older hole in the same file. `extract_commands`
(`page_holds_true.py:118`) skips any code span whose first word is not exactly
`ergane`, which is why `nergane repo forget` shipped in a released README under a
green suite. The guard added afterwards checks that the extracted list is
non-empty and contains two known-good commands — which is a test that the
extractor found *something*, not that it found *everything*.

## The rule this spec is asking for

**Every command a page prints is parsed as printed, by the CLI's own parser, and
a page that names something command-shaped which the sweep cannot resolve fails
rather than skips — for all three pages, the HTML one included.**

### What this spec is not

It is not an execution harness. Nothing here runs an `ergane` verb; the sweep
gains the power to reject an argv, never to act on one. It is not a style check —
prose, tone and structure remain nobody's test. And it does not extend to pages
outside the three named: a fourth page is a fourth story, deliberately not
written here.

## User Scenarios & Testing

### User Story 1 - The sweep proves the invocation, not the verb (Priority: P1)

As the documentation sweep, I parse each printed command as it is printed, so a
line missing a required argument fails me.

**Why this priority**: P1 and first. This is the defect that shipped, in two
pages, past a green suite, and it is the one an operator meets by copying a line
and getting exit 2.

**Independent Test**: feed the parse check a handful of argvs — one complete, one
missing a required flag, one naming a verb that does not exist — and read back
which were rejected.

**Acceptance Scenarios**:

1. **Given** the printed command `ergane usage`, **When** the sweep checks it,
   **Then** it **fails**, naming the missing `--by` — proven by a committed test
   that asserts the failure and quotes the argument name, so the check that
   would have caught the real defect is itself pinned by a test.
2. **Given** the printed command `ergane usage --by epic`, **When** the sweep
   checks it, **Then** it passes — the fix must be accepted as readily as the
   defect is rejected, or pages start carrying `--help` to appease a test.
3. **Given** a printed command containing a placeholder the reader is meant to
   fill in — `<spec-dir>`, `<epic-id>`, `<target-repo-path>` — **When** the sweep
   checks it, **Then** the placeholder is substituted with a value of the right
   shape and the command parses, and a committed test covers one placeholder of
   each kind that appears across the three pages.
4. **Given** the parse check, **When** it runs against any command on any swept
   page, **Then** **no** `ergane` verb is executed — proven by a test that drives
   the check with a subprocess seam asserted never to be called. A sweep that
   dispatches an epic to prove a page is correct is the one outcome worse than
   the defect (`ergane build start` and `ergane uninstall` are both printed on
   these pages).

### User Story 2 - The sweep refuses what it cannot parse (Priority: P1)

As the documentation sweep, I fail on anything that looks like my subject and
does not resolve, instead of skipping it.

**Why this priority**: P1. This is the hole that has now been found three times
in the same file. Closing it is what stops the fourth.

**Independent Test**: feed the extractor spans that are command-shaped but not
recognised, and assert each one raises rather than being dropped.

**Acceptance Scenarios**:

1. **Given** a code span reading `nergane repo forget` — the exact string that
   shipped in the released README on 2026-08-18 — **When** the extractor runs,
   **Then** it raises rather than skipping, and the message names the span.
   `UnrecognizedCommandError` already exists for this purpose
   (`tests/page_holds_true.py:30-31`); this scenario is about the paths that do
   not raise it.
2. **Given** a code span naming a verb that does not exist —
   `ergane build landed`, the 2026-08-14 instance — **When** the sweep runs,
   **Then** it fails naming the verb.
3. **Given** the anti-vacuity guard, **When** it runs, **Then** it asserts the
   extractor found every command-shaped span on the page rather than merely a
   non-empty list containing two known-good ones — proven by a test that adds a
   command-shaped span to a fixture page and asserts the count the guard sees
   increases. A guard that passes on a page whose extractor silently dropped half
   the commands is the defect, not the check.
4. **Given** a code span that is genuinely not a command — a file path, a config
   key, an environment variable name, a model alias — **When** the extractor
   runs, **Then** it is not treated as one and does not fail the sweep. The rule
   is "looks like its subject", and the test states where that line is drawn with
   examples of each kind taken from the real pages.

### User Story 3 - The HTML page is swept like the others (Priority: P2)

As `docs/onramp.html`, I answer to the same three checks the README and CLAUDE.md
answer to.

**Why this priority**: P2 by size. It is one extractor and one test module, and
it is last because it should inherit US1 and US2's strengthened checks rather
than a copy of today's.

**Independent Test**: run the extractor over the committed page and assert it
finds the commands that are visibly on it.

**Acceptance Scenarios**:

1. **Given** `docs/onramp.html`, **When** the sweep extracts its commands,
   **Then** it finds those inside `<code>` spans and inside `<pre class="well">`
   blocks, and unescapes HTML entities before parsing — the page writes
   `&lt;spec-dir&gt;` and `&amp;` in shell pipelines, and a parser fed raw markup
   fails on the wrong thing.
2. **Given** the same page, **When** the sweep runs its comment-stripping,
   **Then** shell comments inside code blocks — marked up as
   `<span class="cmt">` — are not parsed as commands.
3. **Given** the page, **When** the path check runs, **Then** every repository
   path it cites exists — `.specify/memory/constitution.md`,
   `docs/architecture.md`, `docs/decisions.md`, `CONTEXT.md` and any other —
   using the same path extractor the other two pages use.
4. **Given** all three pages, **When** the full sweep runs, **Then** each is
   checked by the same three checks through the same helper, and a test asserts
   the three suites resolve the same extractor and the same parse check by
   identity — one parser per convention was the helper's founding rule
   (`page_holds_true.py:9-12`) and a third page is exactly when it gets broken.

## Work Graph

```yaml
US1:
  implements: []
  depends_on: []
US2:
  implements: []
  depends_on: []
  depends_on_merged: [US1]
US3:
  implements: []
  depends_on: []
  depends_on_merged: [US2]
```

Chain depth 3. All three stories edit `tests/page_holds_true.py`, so they are
strictly sequential; there is no concurrency to be had and pretending otherwise
buys three-way conflicts on one file.

## Requirements (summary — numbered at refinement)

Parse-as-printed through the CLI's own parser with no execution; placeholder
substitution by shape; the required-argument failure and its named argument; the
extractor that raises on command-shaped spans it cannot resolve; an anti-vacuity
guard that counts rather than samples; the boundary between a command and a path
or alias; the HTML extractor with entity unescaping and comment stripping; and
one shared helper across all three pages.

## Success Criteria (summary)

Pasted: the sweep failing on `ergane usage` and passing on `ergane usage --by
epic`; the sweep failing on `nergane repo forget`; the onramp page's extracted
command list; and the full-suite before-and-after counts.

**Operator verification, which is the point of the spec**: revert the
2026-08-27 fix to `README.md` — put `ergane usage` back — and watch the suite go
red. A check that would not have caught the defect it was written for is worth
nothing, and the only way to know is to reintroduce it once, deliberately, and
see the test fail.
