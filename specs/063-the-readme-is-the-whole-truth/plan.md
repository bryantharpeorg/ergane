# Implementation Plan: the README is the whole truth

**Spec**: `specs/063-the-readme-is-the-whole-truth/spec.md`

## What already exists, and where

- `tests/page_holds_true.py:44` — `extract_commands`, the shared helper. Line 54
  is the hole:
  `if not words or words[0] != "ergane": continue`. This is the single line US1
  is about.
- `tests/page_holds_true.py:56` — the placeholder filter (`<spec-dir>` and
  friends are dropped before `--help`). Near-miss detection runs before this.
- `tests/page_holds_true.py:62–69` — `_CHOICES`, `_POSITIONALS`,
  `_INDENTED_VERB`: how argparse's help output is parsed into a known verb set.
  **This is where the list of known entrypoints already comes from.** Near-miss
  detection should compare against that, not against a hand-written list that
  would drift.
- `tests/test_readme.py` — 054's suite: command sweep (:42), anti-vacuity (:82),
  path sweep (:103), path anti-vacuity (:112), no-secret (:119), no-spec-status
  (:136), no-spend (:152). FR-008 says all of these keep passing.
- `tests/test_claude_md.py` — imports the same helper; inherits the fix.
- `README.md` — **rewritten by the operator on 2026-08-19; every line number this
  plan used to cite is dead.** Do not anchor to line numbers here. Anchor to the
  headings, which are stable: "What you must already have" (with the
  "A LiteLLM gateway, backed by a database" subsection), "Installing Ergane"
  (with "The difference that will bite you"), and "Leaving". The six statements
  US2 must guard all live under the first two.
- `factory/controlplane/verify.py:311` — `LLMProbe.gather`, whose alias
  derivation is at `:329-337` (`alias_to_personas`). **Re-verified 2026-08-21
  against `origin/ergane-buildout`: this function moved roughly fifteen lines
  down when 061-US1 landed, and the anchor this plan carried before that was
  stale.**
  FR-010 requires `--requirements` to use the same one. Note 061/US1 also edits
  this function; if 061 has landed, re-read it before extracting the derivation.
- `factory/cli/install.py:217` — `add_install_arguments`, where
  `--requirements` goes.

## Traps

**1. This is the fifth instance of the presence-not-capability class, and US1 is
where it is easiest to rebuild.** The existing sweep asserts that the commands it
*recognised* resolve. It never asserts that it recognised the commands that are
there. If your fix asserts "the near-miss detector exists" rather than "the sweep
fails on a bad page", you have written the same shape again. US1-S5 makes this
explicit: assert the sweep **fails** on a bad fixture.

**2. A near-miss detector that flags `git clone` will be disabled within a
week.** US1-S2. The pages legitimately name `git`, `uv`, `gh`, `systemctl`,
`cd` and more. Bound the detector: compare against the known entrypoint set, and
flag only words within a small edit distance of one of them. A word that is
nothing like any known command is somebody else's tool, not a typo.

**3. Derive the known-entrypoint set from the CLI, not from a literal.** The
helper already parses argparse's own help output to learn verbs
(`tests/page_holds_true.py:62–69`). A hand-written list of entrypoints would go
stale exactly like the page it is checking, and with less visibility.

**4. Do not write a second extractor.** 054's trap 3, still live and now
load-bearing for two pages. FR-003 and US1-S4 require the logic in the shared
helper. Two extractors is how the pages drift apart with both suites green.

**5. The typos are already fixed — prove the detector on a fixture.** The
operator corrected both `nergane` spans on 2026-08-19, so the real pages can no
longer demonstrate that your detector fires. If your only evidence is "both pages
pass", you have proven the absence of false positives and nothing else, and a
detector that never fires passes that test perfectly. Build the fixture page
(T001) and assert the **failure** on it. This is FR-004 and it is the single
easiest way to rebuild the exact defect this spec exists to remove.

**6. `README.md` is an entry page, not a second standards channel.** 054's trap
7, and `tests/test_claude_md.py` holds `CLAUDE.md` to the same line. US2 guards
prerequisites and install paths. It does not add requirements for how code is
written; those belong to the standards path `factory.yaml` names.

**12. US2 is now a guarding story, not a writing story, and the difference is
the whole point.** The prose already exists. If you re-word it, you will spend
the story arguing with a page that is already correct and land nothing that
survives the next edit. What is missing is that **nothing asserts any of it** —
delete the database sentence today and the full suite is green. Write the
mutation tests. Each one takes a copy of the page text, removes one protected
statement, and asserts the check fails. If your test instead reads the real
`README.md` and asserts a substring is present, you have written a test that
cannot fail on any page anyone would actually write, which is the fifth instance
of this spec set's defect class wearing a sixth hat.

**13. Guard the meaning, not the sentence.** FR-011 and US2-S5. A test keyed to
the literal string "must be backed by a database" fails the moment someone
improves the wording to "requires a database-backed proxy", and the person whose
build it breaks will delete it rather than fix it. Assert over a small set of
required concepts — that the page says a database is required, that it names the
key-management endpoints, that it warns a config-only proxy still answers chat
completions — in a way a reworded page still satisfies. Then demonstrate that:
US2-S5 requires a committed test showing a reworded equivalent passes.

**7. No status in the page.** Spec states, story counts and spend figures have
live sources and rot between writing and reading. US3-S5 exists partly for this
reason: naming `ergane install --requirements` keeps the alias list live instead
of copying it into prose that goes stale.

**8. `--requirements` must not multiply spend or mint anything.** It prints what
the gateway must serve. It does not probe, complete, or mint a key — that is
`--verify`'s job, and 061/US1 is making that job more expensive. Keep them
distinct.

**9. Personas declared `agent: none` have no model by construction.** 054's trap
5. Skip them; do not probe and catch.

**10. The judge sees the diff and the criteria. Nothing else.** SC-001 requires
running a deliberately-broken page and observing the failure — **paste that
output into the diff.**

**11. Story edges.** US1 edits `tests/page_holds_true.py` and adds a fixture; US2
adds tests that read `README.md`; both land on the shared test surface, so
serialise US1 → US2. US3 edits `factory/cli/install.py` and then `README.md`, so
it follows US2 — otherwise it edits the page out from under an assertion that has
not been written yet.

## Sizing

Three small stories. US1 is one function in a shared helper plus a fixture page.
US2 is a set of mutation tests over page text — no prose, the prose already
landed. US3 is a flag, an extraction of an existing derivation, and tests.

The only real risk is trap 2 — a detector tuned too tightly generates false
positives on the many legitimate non-Ergane commands these pages name, and a
noisy guard gets removed. Tune it against the actual pages before declaring US1
done.

## Verification the operator will run, independent of the gate

- **Prove US1 by breaking the page.** Introduce a one-character typo into a
  command in `README.md`, run the suite, watch it fail, and revert. Then do the
  same in `CLAUDE.md`. That is SC-001 and it is the only check that distinguishes
  a working detector from a detector that compiles.
- **Prove US1-S2 by counting false positives.** Run the detector over both pages
  as they stand and confirm zero flags on `git`, `uv`, `gh` and every other
  legitimate tool they name.
- **Prove US2 by deleting sentences.** Remove each of the six protected
  statements from `README.md` in turn, run the suite, and watch it fail with a
  message that names what went missing. Six runs, six failures, all six pasted
  into the diff. SC-005. A guard nobody has watched fail is a guard nobody has
  tested.
- **Prove US2's prose separately, and by following it.** On a host meeting the
  stated prerequisites, follow `README.md` top to bottom, including standing up a
  gateway from its description alone. SC-002 and SC-003. The reporter needed
  three source files; the test of the page is that the next reader needs none.
  This one is the operator's to run and is not the implementer's story.
- **Prove US3 by agreement.** Run `ergane install --requirements` and `ergane
  install --verify` against the same registry and confirm the alias sets match.
  SC-004.
