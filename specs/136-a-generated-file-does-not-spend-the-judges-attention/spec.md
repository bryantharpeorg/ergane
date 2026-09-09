---
state: draft
fixes:
  - verify/the-diff-size-refusal-counts-generated-lockfiles-and-has-no-manifest-key
# DRAFTED 2026-09-04 by the refinement workflow (refinement-2026-09-04) from
# docs/triage-2026-09-03-ergane-web-round3.md § "a-generated-file-does-not-spend-the-judges-attention"
# (lines 115-131), against ergane-buildout at 602a92c. Every `file:line` in
# spec.md and plan.md was read from that commit with `sed -n 'Np'` and verified
# to resolve to the symbol named, not recalled.
#
# WHERE THIS CAME FROM. C-41 of the `ergane-web` hand-over, re-reported after
# 092 landed and re-verified against the tree on 2026-09-03. The ledger row is
# `regressed`, and the word is wrong: nothing regressed, because nothing was
# built. 092 declared this key under `fixes:` while its own prose argued against
# building it, and its FR-008 required leaving `prepare_diff` unchanged. This is
# the second dated instance of the standing lesson — a `fixes:` list longer than
# the functional requirements justify is a claim, not a fix — after 100.
#
# WHAT IT COST, MEASURED. On the container run: both gates PASS, refused at
# `check_output` with total_bytes 70,652 against 65,536 — 8% over — of which
# `package-lock.json` was 53,176, 75% of the whole allowance. Adding one browser
# dependency churned the lockfile and that alone spent three quarters of it. The
# ladder cannot fix it and demonstrably does not try: consecutive attempts
# produced byte-identical diffs, 70,652 both times. Earlier, on the same key: a
# scaffold story at 185,682 bytes, 161 KB of it two generated lockfiles, all four
# gates green. And past the refusal the same bytes are spent again — `_allocate`,
# re-measured by running it on 2026-09-04, gives a 102,400-byte generated file
# 24,076 of a 65,036-byte allowance (37.0%) and cuts all twenty source sections
# to the 2,048-byte floor: source bytes shown fall 65,036 -> 40,960.
#
# NOT IN SCOPE. This spec does not remove, weaken or make optional the size
# refusal; does not make `diff_check` optional; does not change the
# `diff_refusal_bytes` dial 092 landed; does not hard-code any lockfile name,
# suffix or package manager; does not derive the classification from
# `.gitattributes`; and does not declare the new key in this repository's own
# `ergane.yaml`. A manifest that declares nothing is measured, prepared and
# judged byte-identically to today.
#
# ONE KEY, DELIBERATELY.
# `verify/the-judges-attention-budget-and-the-refusal-threshold-are-the-same-constant`
# is resolved against 092 and is NOT declared here: 092 genuinely split the two
# constants and added the dial, and that half is done. The sibling row
# `verify/the-diff-size-check-measures-a-stacked-node-against-a-base-that-cannot-contain-its-declared-dependency`
# is open, critical, wears the same refusal message and is a different rule with
# a different owner; it is named in the plan as a trap and is not declared here.
# The third neighbour is
# `verify/agents-are-told-to-measure-diff-size-with-the-wrong-ruler` — open,
# critical, three occurrences — and it is not declared here either: it is about
# the ruler an agent is handed, not about what the ruler weighs. It touches this
# spec in one place, carried as plan trap 13. Its own diagnostic — "a healthy
# refusal sits within a kilobyte of `git diff <landing-branch>...HEAD`", measured
# at 757 and roughly 850 bytes on two nodes — stops holding for any repository
# that declares `generated_paths`, because the gap becomes the excluded body.
# FR-012's disclosure is what restores the subtraction, and it is the reason that
# requirement is not decoration.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04) against ergane-buildout at 602a92c,
# after an adversarial review refuted the trio on two blocking defects.
# WHAT CHANGED. (1) Trap 5 and T008 obeyed as written turned the suite red on a
# landed invariant nothing in the trio named — `tests/test_120_rewrite_carries_forward.py:310`
# asserts `carried == ["ladder", "verify"]` over `_KNOWN_KEYS` — so that test is
# now declared scope with the two wrong escapes named. (2) FR-012's disclosure
# would have landed where no operator could read it: `OutputCheck` is serialised
# by a hand-written whitelist, so FR-012 and US3-S2 now require the field to
# survive the store round trip. (3) FR-011 now says which side weighs the stub —
# both, because there is one assembly — and a new US3-S6 pins the abridgement
# record to it; US3-S1's arithmetic is restated accordingly. (4) US3-S4 named a
# refusal the anchor does not make: reworded to a v2 manifest declaring
# `verify: [gates, judge]`. (5) US1-S7's grep is scoped to the three modules that
# classify, because `npm` already appears ten times elsewhere in `factory/`.
# (6) The `_score`/`_judge` anchor, T030's phantom call chain through
# `diff_size_refusal`, T015's symbol form and US1's sizing (three
# `load_loop_config` unpack sites) are corrected. (7) The wrong-ruler neighbour
# is named above. Both operator holds survive verbatim: the `regressed` reading
# in trap 1, and the supersession of 092 FR-008 below.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), second pass, again at 602a92c,
# after a second adversarial review refuted the trio on two further blocking
# defects, both structural and both invisible to `spec validate`.
# WHAT CHANGED. (a) The one stub renderer had no legal home: the tasks put it in
# `factory/verify/judge.py` and then required `factory/verify/diffbounds.py` to
# weigh the identical bytes, across an import fence the tree enforces
# (`factory/verify/diffbounds.py:9-14`, asserted as an exact set by
# `tests/test_verification_sweep.py:879`). FR-007 and FR-011 now name
# `factory/verify/diffbounds.py` as its single home, reached from `prepare_diff`
# through the private-alias import already at `factory/verify/judge.py:63`; plan
# trap 15 states the fence and the three bad moves it removes. (b) FR-011
# narrowed `total_bytes` while `largest_files` was pinned unchanged, so a refusal
# in a pattern-declaring repository would have named a file larger than its own
# total and the retry prompt at `factory/workgraph/prompt.py:975` would have sent
# the agent after bytes nobody counted — re-creating the wrong-ruler neighbour on
# the very attempts this spec targets. FR-011 now builds `largest_files` from the
# same narrowed measurement, FR-014's "today's message" is qualified to the
# no-pattern case, US3-S7 pins it, and plan trap 16 names both leak sites.
# (c) Five controls and one vacuous assertion gained the mutation that makes them
# fail (US1-S6, US1-S7, US2-S3, US2-S5, US3-S3, US3-S4), modelled on
# `tests/test_forge_manifest.py:330-331`. (d) US3-S1's literal 17,476 is marked as
# the pre-marker measurement it is. (e) Load-bearing symbol anchors were reflowed
# onto one line so the symbol tier machine-checks them. Every hold survives
# verbatim: trap 1's `regressed` reading, and the supersession of 092 FR-008.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), third pass, again at 602a92c,
# after a third adversarial review refuted the trio on two blocking defects.
# WHAT CHANGED. (i) FR-004's pin route stopped one hop short of the dispatch the
# schedule actually fires: `EpicInput` is constructed at three sites and the trio
# named only the CLI's, never `factory/roadmap/workflow.py:1303` inside
# `factory/roadmap/workflow.py:1247` — `_dispatch`. An implementer copying the
# route "exactly" would have wired hand-started epics and left every
# roadmap-dispatched one measuring as it does today — trap 11's own failure
# shape. FR-004, US1-S5, plan § "The pin", trap 10, § Sizing and T005/T012 now
# carry both forks, and US1-S5 is asserted on the epic input rather than on the
# read result. (ii) US2-S1's Then was arithmetically unsatisfiable for its own
# fixture: twenty 5,120-byte source sections do not fit a 65,036-byte allowance
# once the generated body is gone, so `_allocate` still cuts them —
# `_allocate([5120]*20, 65036)` returns 3,251/3,252, measured at 602a92c. The
# Then is restated to those grants, T014 and T022 with it, and new plan trap 17
# names the two contortions an implementer would otherwise reach for. (iii)
# US3-S7's "states more bytes than its own `total_bytes`" half was vacuous for
# its fixture (the refusal only fires above the threshold, and 53,176 is below
# it); the named-path half is kept and the numeric one dropped, in US3-S7, T029
# and trap 16, which now says the pairing needs a lowered dial. (iv) US2's
# priority rationale claimed a band that is empty on a default configuration
# (`factory/verify/diffbounds.py:66`) and is now qualified. (v) US1-S7 and T007
# said `npm` appears ten times elsewhere in `factory/`; it appears fifteen.
# Every hold survives verbatim: trap 1's `regressed` reading, and the
# supersession of 092 FR-008.
---

# Feature Specification: a generated file does not spend the judge's attention

**Created**: 2026-09-04
**Depends on**: nothing.

## The gap, stated precisely

A machine-generated file that a repository must commit — a lockfile — is charged
to the story that touched it twice: once against the size at which the story is
refused unbuilt, and again against the bytes the judge is given to read. Neither
charge can be declined, and no dial, exemption or disclosure exists for either.

The chain is six steps:

1. The patch is assembled by `factory/workgraph/worktree.py:1496` — `diff`,
   which stages the worktree into a scratch index and diffs it against the
   node's base. Its own docstring names the only escape a generated file has:
   "ignored files stay out, so a target repo's `.gitignore` is what keeps
   generated noise from reaching the judge"
   (`factory/workgraph/worktree.py:1505-1507`). A `package-lock.json` must be
   tracked for `npm ci` to be reproducible, so it is structurally outside that
   escape.
2. That patch is read twice, by two callers, with no pathspec on either:
   `factory/verify/diffcheck.py:376` — `judge_input` for the size check, and
   `factory/activities/agent_activities.py:739` — `read_worktree_diff` for the
   judge's prompt. Both reach `worktrees.diff` directly
   (`factory/verify/diffcheck.py:390` and
   `factory/activities/agent_activities.py:735`).
3. `factory/verify/diffbounds.py:137` — `assembled` sums the complete file
   listing, the preamble and **every** file's whole section at
   `factory/verify/diffbounds.py:155`, and
   `factory/verify/diffbounds.py:182` — `size_refusal` compares that total to
   the threshold. A generated file's bytes are weighed in full, and over the
   threshold the story is refused before any judge runs.
4. Past that check the same bytes are spent again.
   `factory/verify/judge.py:473` — `prepare_diff` hands every section's size to
   `factory/verify/judge.py:515` — `_allocate` at
   `factory/verify/judge.py:501`, which splits the allowance in proportion to
   size. A generated file therefore takes a proportional share of the judge's
   attention away from the source under judgement.
5. No exemption exists anywhere in the tree — and as of epic 130 there is no
   exclusion list of any kind left to extend. The pair that used to sit in
   `factory/workgraph/detector.py` (`EXCLUDED_DIR_NAMES`, `EXCLUDED_SUFFIXES`)
   governed the runtime-root snapshot rather than the diff, and 130 US3 FR-006
   deleted it as "a Python-shaped guess about someone else's repository"
   (`factory/workgraph/detector.py:35`). That deletion is now asserted by
   `tests/test_us3_no_language_shaped_list.py:183` —
   `test_detector_defines_no_generated_path_exclusion_list`. The tree is
   therefore not merely silent about generated files: it has already ruled
   against the one shape of answer an implementer would reach for first.
6. And there is no opting out: a v2 manifest that declares a `verify:` list
   without `diff_check` is refused at `factory/verify/factory_yaml.py:958-963`,
   and a manifest that declares no `verify:` block at all gets the default order
   (`factory/verify/models.py:340`), which contains it. Every repository runs
   step 3.

**Measured, twice, on real work.** A scaffold story: 185,682 bytes against
65,536, 161 KB of it two generated lockfiles, all four gates green, judge never
reached. A container run: 70,652 against 65,536 — 8% over — of which
`package-lock.json` was 53,176, three quarters of the allowance, spent because
one browser dependency was added. Consecutive attempts produced byte-identical
diffs, 70,652 both times: the ladder cannot make a lockfile smaller and the
agent is not told that the judge's input rather than its code is what overflowed.

**And the remedy 092 shipped relocates the cost rather than removing it.** An
operator whose only instrument is `diff_refusal_bytes` raises the threshold for
every story, and the diff then reaches the judge with the generated file still
in it, taking its proportional share. Re-measured by running `_allocate` on
2026-09-04: over twenty 5,120-byte source sections plus one 102,400-byte
generated section with an allowance of 65,036, the generated section is granted
24,076 bytes — 37.0% — and every source section is cut to the
`SMALL_FILE_FLOOR` of 2,048 (`factory/verify/judge.py:121`). Source bytes shown
fall from 65,036 to 40,960. Raising the dial buys a worse verdict.

## The rule this spec is asking for

**A repository may declare which of its committed paths are machine-generated,
and those paths' bodies are weighed by neither the refusal nor the judge's
allowance — while their names, and their real insertion and deletion counts,
stay in the file listing so the judge still knows they changed.**

The cases, complete:

| path matches a declared pattern | weighed by `size_refusal` | shown to the judge | in the file listing |
|---|---|---|---|
| no | its bytes, in full | its allocated share of the allowance | yes, real counts |
| yes | **its stub only**, never its body | **a stub** naming path, real counts and real byte size | yes, real counts, marked generated |
| nothing declared | its bytes, in full — today | today's share — today | today's line, byte-identical |

There is one assembly, not two: the bytes the refusal weighs are the bytes the
judge's prompt carries, stub for stub and marker for marker. One function renders
that stub, in `factory/verify/diffbounds.py`, because the judge module may not be
imported by the module that measures. The declaration is the only source of the
classification, and it is read once, at dispatch, from the committed manifest of
the repository being built.

### What this spec is not

**It supersedes 092 FR-008, and says so.** That requirement — at
`specs/092-the-diff-ceiling-and-the-evidence-doctrine-agree/spec.md:250-252` —
reads "Every story MUST leave `prepare_diff`'s abridgement algorithm ...
unchanged, and MUST NOT exempt any path by name or pattern from the measured
size." (092's own citation of `prepare_diff` inside that sentence has since
rotted — it names a line that is now inside `build_prompt`'s docstring; the
function is at `factory/verify/judge.py:473` — `prepare_diff`.) It was written
to stop 092 fixing the
instance and hiding the general problem, and it did its job: 092 split the two
constants and added the dial. The general problem is now fixed, and the instance
is still live, so the prohibition has outlived its argument. This spec changes
`prepare_diff` and exempts declared paths from the measured size, deliberately
and in writing.

It is not a relaxation of the size refusal. A diff whose non-generated bytes
exceed the threshold is refused exactly as it is today, and `diff_check` stays
mandatory. A diff with **no** declared pattern in it is refused with today's
message and today's list of largest files, byte for byte. Where a pattern *is*
declared the message is unchanged in shape and wording, and the one thing that
narrows is what the numbers in it are measured over: FR-011 requires
`largest_files` to be built from the same narrowed assembly as `total_bytes`, so
the record never names a file whose bytes it did not count.

It is not a change to the `diff_refusal_bytes` dial 092 landed, in default,
floor, refusal shape or manifest spelling.

It is not a hard-coded list of lockfiles. No filename, suffix or package-manager
name becomes generated by being one; a repository declares its own, or nothing
is excluded. Deriving the set from a repository's `.gitattributes`
`linguist-generated` markers is deliberately deferred: the classification would
then depend on a worktree read taken at two separate seams, and two reads of one
rule is exactly the disagreement `factory/verify/diffbounds.py:140-145` exists
to prevent.

It is not a way for a node to exempt itself. The patterns are pinned at dispatch
from the operator clone, beside the ladder and the refusal threshold, and a node
worktree's copy of the manifest is never consulted.

## User Scenarios & Testing

### User Story 1 - A repository declares which of its committed paths are generated (Priority: P1)

As an operator whose build system commits a lockfile, I can write down that the
lockfile is generated, in the file that governs how my repository is built, and
the factory carries that declaration to the place a verdict is formed.

**Why this priority**: P1 and it depends on nothing. Without a declaration there
is nothing for either measurement to consult. This story is the declaration and
nothing else: parsing it, refusing a malformed one, keeping it out of v1, and
proving this repository does not spend the key. Carrying it to the epic — and the
one real hazard in that, a value that decides a verdict being readable from the
worktree of the node being judged — is US4, split out of this story on 2026-09-08
because the pair was thirteen tasks, and no story above eleven has landed on this
floor.

**Independent Test**: Load a manifest declaring the key and read the parsed
configuration; load the same body under v1 and read the refusal; load three
malformed values and read the three messages.

**Acceptance Scenarios**:

1. **Given** a v2 manifest declaring
   `generated_paths: ["package-lock.json", "**/*.lock"]`, **When** the manifest
   is loaded, **Then** it parses and the parsed configuration carries both
   patterns in declaration order, asserted by a committed test.

2. **Given** one manifest body declaring the key, loaded twice — once under
   `version: 2` and once under `version: 1` — **When** each is loaded, **Then**
   the v2 load parses and carries the patterns while the v1 load is refused as
   an unknown top-level key naming `generated_paths`. A committed test asserts
   both halves in one function: the v1 half alone passes today, before any
   change, so only the pair can fail a diff that registered the key in the wrong
   tuple. **And Given** `_KNOWN_KEYS`, **Then** the landed enumeration at
   `tests/test_120_rewrite_carries_forward.py:310` names the new key beside
   `ladder` and `verify` — the v2-only keys `ergane init` carries without asking
   — because registering the key changes what that list contains and nothing
   else.

3. **Given** manifests declaring `generated_paths: [""]`, `generated_paths: [7]`
   and `generated_paths: "package-lock.json"`, **When** each is loaded, **Then**
   each is refused with a message naming the offending value and the rule, and a
   committed test asserts all three messages.

4. **Given** this repository's own `ergane.yaml`, **When** a committed test
   parses it, **Then** it declares no `generated_paths` and resolves to the empty
   declaration — the mirror of
   `tests/test_forge_manifest.py:339` — `test_this_repositorys_own_manifest_does_not_spend_the_key`,
   because the
   config gate parses a node's manifest with the *worker's* installed parser and
   a diff that both teaches the key and spends it is refused at `CONFIG_ERROR`
   in 0.0s on every attempt. This one passes before the diff as well as after,
   the way its model says of itself at `tests/test_forge_manifest.py:340`, so the
   committed test states its own mutation: declare the key in `ergane.yaml` and
   this test fails.

### User Story 2 - The judge's attention is not spent on a generated file (Priority: P2)

As an operator, the model scoring my story reads my source instead of my
dependency tree, and its prompt says out loud which bodies it was not shown.

**Why this priority**: P2, and it must land before the refusal half. Its own
value is immediate, but it is smaller on a default configuration than the band
between the two limits suggests: `factory/verify/diffbounds.py:66` reads
`DIFF_REFUSAL_THRESHOLD = DIFF_INPUT_LIMIT`, so unless an operator raised
`diff_refusal_bytes` a diff large enough to be abridged is refused by the
untouched `assembled` first and never reaches a judge at all. What US2 alone
changes on such a repository is every *under*-limit prompt, which stops carrying
the generated body (US2-S2) — the judge reads source instead of a dependency
tree — not which stories are refused. Where the dial *was* raised — the operator
§ "the remedy 092 shipped relocates the cost" is about — the band is real, every
diff in it is abridged today, and a generated file takes a proportional share of
that abridgement. Landing the refusal half first would let a diff through whose
judge prompt is *worse* than today's.

**Independent Test**: Prepare a diff of source sections plus one generated
section and read the grants and the assembled text; drive `run_judge` with an
activity input carrying the patterns and read the prompt.

**Acceptance Scenarios**:

1. **Given** twenty 5,120-byte source sections plus one 102,400-byte section
   whose path matches a declared pattern, and an allowance of 65,036, **When**
   the judge's diff is prepared, **Then** only the twenty source sizes reach
   `factory/verify/judge.py:515` — `_allocate`, the whole 65,036-byte allowance
   is divided among those twenty — 3,251 or 3,252 bytes each, up from the
   2,048-byte floor every one of them is cut to today — and the generated
   section is replaced by a stub. A committed test asserts those grants and
   commits, as pasted output, today's numbers beside the new ones: today the
   generated section takes 24,076 of 65,036 (37.0%) and every source section is
   cut to 2,048, so the source bytes shown rise from 40,960 to 65,036. The
   sections are still abridged after the fix and the scenario must not say
   otherwise — 20 x 5,120 = 102,400 source bytes do not fit a 65,036-byte
   allowance either, so a Then written as "every source section is carried
   whole" is unsatisfiable for this fixture (plan trap 17). What changes is the
   ratio: none of the allowance is spent on bytes no human wrote.
2. **Given** a diff comfortably under the attention limit that contains a
   generated section, **When** the judge's diff is prepared, **Then** the
   generated body is still elided and the stub still names the path, its real
   added and removed counts and its real byte size. A committed test asserts the
   under-limit case specifically, because a fix applied only on the abridgement
   path would leave the two measurements disagreeing exactly where 092's own
   trap 3 says they must not.
3. **Given** a diff whose only elision is a declared generated file, **When** the
   prompt is assembled, **Then** the prepared text carries the stub in place of
   the generated body **and** `PreparedDiff.truncated` is false and the verdict's
   `truncated_input` is false, asserted by one committed test — the assertion is
   that an elision happened and was not called a truncation, not that nothing
   happened, and "the judge could not see everything it needed" keeps meaning
   today what it means today. Mutation: return the section whole and the stub
   assertion fails; set `truncated` from the elision and the second half fails.
4. **Given** an epic whose target repository declares patterns, **When** the
   workflow scores an attempt, **Then** the patterns reach `prepare_diff` from
   the pinned epic input through the judge activity's own input and
   `judge.run_judge`, proven by a committed test that names them **only** on the
   activity input. A test that hands patterns to `prepare_diff` directly cannot
   satisfy this scenario, which is the point: a declaration production never
   reads fixes nothing.
5. **Given** a manifest declaring no patterns, **When** any diff is prepared,
   **Then** the assembled prompt is byte-identical to the one produced today,
   asserted by a committed test over a fixture diff whose expected bytes were
   captured from the tree before the implementation landed. This control passes
   before the diff too, so the committed test states its own mutation: elide by
   suffix rather than by declaration and this test fails.

### User Story 3 - The refusal stops counting bytes the judge will never read (Priority: P3)

As an operator, a story is refused unbuilt for the size of the work it did, not
for the size of the file its package manager rewrote — and the record says which
bytes were left out.

**Why this priority**: P3, and it depends on US2 having already removed those
bytes from the judge's prompt. This is the story that ends the outage: it is the
half that turns 70,652 measured bytes into the bytes the story itself wrote plus
the stub line that names what was left out, and it is the half that must not land
alone.

**Independent Test**: Run the output check over a diff containing a generated
section, at a threshold the whole diff exceeds and the remainder does not, and
read the verdict and the record, both in memory and after a store round trip.

**Acceptance Scenarios**:

1. **Given** a diff of 70,652 assembled bytes of which 53,176 belong to a path
   matching a declared pattern, and a threshold of 65,536, **When** the output
   check runs, **Then** no size refusal is recorded and the measured total equals
   the assembly `prepare_diff` builds from the same patch and the same patterns,
   compared against it directly rather than against a literal. A committed test
   asserts that equality, and it is stated that way because the arithmetic
   `70,652 - 53,176 = 17,476` is the pre-marker measurement: the total also
   carries the stub and the listing's generated marker, both of which FR-011
   weighs on both sides. **And Given** the identical diff with no pattern
   declared, **Then** it is still refused with today's message. A committed test
   asserts both halves, so only a production change can pass it.
2. **Given** that same diff and declaration, **When** the check's record is
   written to the store and read back, **Then** the loaded record names the
   excluded path and the bytes it carried, asserted by a committed test that
   round-trips the row the way `tests/test_092_abridged_is_recorded.py:148`
   round-trips the abridgement record — a disclosure that exists only in memory
   reaches no operator, because every operator-facing reader works from a loaded
   row (`factory/cli/nouns/build.py:1625`), and a measurement that left something
   out and did not say so is the omission Principle VIII refuses.
3. **Given** a diff of 70,652 bytes with no generated file in it at all, **When**
   the output check runs at the same threshold, **Then** it is still refused,
   with today's message and today's largest-files list, asserted by a committed
   test whose expected strings are copied from the current behaviour. This
   control passes before the diff too, so the committed test states its own
   mutation: exclude by suffix rather than by declaration and this refusal
   disappears.
4. **Given** a v2 manifest declaring `verify: [gates, judge]`, **When** it is
   loaded, **Then** it is still refused by
   `factory/verify/factory_yaml.py:958-963` with its message unchanged, asserted
   by a committed test — the refusal is narrowed in what it weighs and in nothing
   else. This control passes before the diff too, so the committed test states
   its own mutation: make `diff_check` optional to get a story's bytes under the
   threshold and this test fails.
5. **Given** an epic whose target repository declares patterns, **When** the
   workflow runs the output check, **Then** the patterns reach `check_output`
   from the pinned epic input through the activity's own input, proven by a
   committed test that names them only on that input; **and** an activity input
   declaring none measures byte-identically to today, asserted in the same test.
6. **Given** a diff that exceeds the attention limit only because of a declared
   generated body, **When** the abridgement record is taken and the judge's diff
   is prepared from the same patch and the same patterns, **Then** the record's
   `abridged` and `PreparedDiff.truncated` agree, asserted by a committed test —
   the invariant `tests/test_092_abridged_is_recorded.py:141` already pins for
   the no-pattern case, held at the margin the patterns move.
7. **Given** a diff whose non-generated bytes alone exceed the threshold and
   which also carries a declared generated section of 53,176 bytes, **When** the
   output check runs, **Then** the refusal fires and no entry in its
   `largest_files` names the generated path, while the excluded path and its real
   byte count are on the FR-012 record — asserted by one committed test.
   Mutation: rank `largest_files` over the section bodies the way today's code
   does and the generated path is named as the biggest thing that spent a total
   which never counted it, which is what
   `factory/workgraph/prompt.py:975` — `_size_listing` would then put in the next
   attempt's prompt. The assertion is over the *name*, not over an inequality:
   the refusal only fires above the threshold, so at this fixture's threshold the
   un-narrowed entry's 53,176 bytes are necessarily smaller than the record's own
   `total_bytes` and "states more bytes than its own total" would catch nothing
   here (plan trap 16).

### User Story 4 - The declaration reaches the epic that will be judged (Priority: P1)

As an operator whose manifest names a lockfile, the value I committed is the
value the verdict is formed against — not one a node could rewrite on its way to
being judged — and the file listing says which files it applied to.

**Why this priority**: P1, and it is the second half of US1, split out on
2026-09-08 for size. It carries the one real hazard in this spec: a value that
decides a verdict must not be readable from the worktree of the node being
judged, and there are **two** paths that start an epic, so a route wired through
only one leaves every scheduled epic carrying the empty default. It runs after
US1 because there is nothing to carry until the manifest parses, and before US2
because `prepare_diff` has nothing to elide until a section knows whether it is
generated.

**Independent Test**: Start an epic from a repository whose committed manifest
and whose node worktree declare *different* patterns, on each dispatch path, and
read the patterns off the `EpicInput` each was started with; build the sections
and the file listing from a diff and read the marker.

**Acceptance Scenarios**:

1. **Given** a diff containing one section whose path matches a declared pattern
   and one that matches none, **When** the sections are built and the file
   listing is assembled, **Then** the matching section is classified generated
   and its listing line carries its real added and removed counts plus an
   explicit marker, while the other line is byte-identical to today's. **And
   Given** the same diff with no pattern declared, **Then** the whole listing is
   byte-identical to the string it produces today — a committed test asserts the
   pair, so a diff that marked every file could not pass.

2. **Given** a target repository whose committed manifest declares patterns and
   whose node worktree carries a *different* manifest declaring others, **When**
   an epic is started from it, **Then** the `EpicInput` the epic is started with
   carries the committed clone's patterns and not the worktree's — asserted on
   **both** dispatch paths by committed tests, the roadmap's own child start as
   well as the hand-started CLI's, because the roadmap is what the schedule
   fires and a route wired only through `factory/cli/nouns/build.py:951` would
   leave every scheduled epic carrying the empty default — which is the half-done
   wiring this scenario exists to catch. Reading the patterns back off
   `factory/verify/factory_yaml.py:1134` — `load_loop_config` or off
   `factory/activities/roadmap_activities.py:822` — `ReadLoopConfigResult` does
   not satisfy this scenario: both sit upstream of the fork, and the fork is
   where the wiring can be half-done. The models are
   `tests/test_023_us2_dispatch_pin.py:756` — `test_roadmap_dispatch_reads_config_per_child`,
   which captures the child `EpicInput` the roadmap dispatched, and
   `tests/test_023_us2_dispatch_pin.py:389` — `test_cli_dispatch_v2_manifest_pins_declared_caps_and_order`.

3. **Given** the three modules that classify, render and measure a section —
   `factory/verify/diffbounds.py`, `factory/verify/judge.py` and
   `factory/verify/diffcheck.py` — **When** a committed test greps them for
   lockfile filenames and package-manager names, **Then** none appears, so the
   declaration is the only source of the answer. The scope is part of the
   assertion and the test says why: `npm` is already written fifteen times
   elsewhere in `factory/` — counted at 602a92c across four files — in a cache
   example at `factory/verify/factory_yaml.py:804`, in
   the stack packs at `factory/stack_packs.py:45` and in gate prose at
   `factory/verify/gates.py:834`, and none of those is a classification rule. A
   grep of all of `factory/` fails today, before any change, and this scoped one
   passes today, so the committed test carries its own mutation in the shape
   `tests/test_forge_manifest.py:330-331` uses: hard-code `package-lock.json` in
   the matcher and this test fails.

## Functional Requirements

- **FR-001**: The v2 manifest MUST accept a top-level `generated_paths:` list of
  path patterns beside `gates:`, and a v1 manifest declaring the key MUST be
  refused as an unknown top-level key.
- **FR-002**: A `generated_paths` value that is not a list, or an entry that is
  not a non-empty string, MUST be refused with a message naming the offending
  value and the rule, in the shape the manifest's other typed keys are refused.
- **FR-003**: A manifest declaring no `generated_paths` MUST parse to an empty
  declaration. The byte-identity that follows from an empty declaration is owned
  by the stories that can prove it: FR-015 for the sections and the file listing,
  FR-008 for the judge's prompt, FR-013 for the measurement.
- **FR-004**: The declared patterns MUST be pinned at dispatch by the same read
  that pins the ladder and the refusal threshold
  (`factory/verify/factory_yaml.py:1134` — `load_loop_config`) and carried onto
  the epic input beside `diff_refusal_bytes` on **every** path that starts an
  epic — the roadmap's own child start at `factory/roadmap/workflow.py:1303` as
  well as the hand-started CLI's at `factory/cli/nouns/build.py:951` — and no
  code path may read them from a node's worktree.
- **FR-005**: A diff section MUST carry whether its path matches a declared
  pattern, and the file listing MUST name a generated file with its real added
  and removed counts plus an explicit marker; no filename, suffix or
  package-manager name may be hard-coded as generated in the modules that
  classify, render or measure a section.
- **FR-006**: This repository's own `ergane.yaml` MUST NOT declare
  `generated_paths`, and a committed test MUST assert it, because the config gate
  parses a node's manifest with the worker's installed parser.
- **FR-007**: `factory/verify/judge.py:473` — `prepare_diff` MUST replace a
  generated section with a stub naming its path, its real added and removed
  counts and its real byte size, and MUST pass only the sizes of sections that
  are not generated to `factory/verify/judge.py:515` — `_allocate`. Exactly one
  function MUST produce that stub, and it MUST live in
  `factory/verify/diffbounds.py`, reached from `prepare_diff` through the
  private-alias import already at `factory/verify/judge.py:63`; a second
  implementation of the stub's bytes anywhere in the tree violates FR-011.
- **FR-008**: That elision MUST happen whether or not the assembled diff exceeds
  the attention limit, so the bytes the judge's prompt carries are the bytes the
  refusal weighs — and a diff with no declared pattern in it MUST assemble the
  prompt today's code assembles, byte for byte.
- **FR-009**: `PreparedDiff.truncated` MUST NOT be set by the elision alone: a
  diff whose only elision is a declared generated file MUST report
  `truncated_input` false on the verdict.
- **FR-010**: The patterns MUST reach `prepare_diff` from the pinned epic input
  through the judge activity's input and
  `factory/verify/judge.py:752` — `run_judge`; no test naming them directly on
  `prepare_diff` may satisfy FR-007
  or FR-008.
- **FR-011**: `factory/verify/diffbounds.py:137` — `assembled` MUST weigh a
  generated section as the stub FR-007 renders rather than as its body, so its
  total is byte-for-byte the assembly `prepare_diff` builds: the complete file
  listing, the preamble, every other section whole, and one stub per generated
  section. The stub's own bytes and the listing's generated marker are weighed by
  both sides, because there is one assembly and not two — which is why FR-007
  puts the single stub function in `factory/verify/diffbounds.py`: that module
  may not import `factory/verify/judge.py`
  (`factory/verify/diffbounds.py:9-14`, asserted as an exact set by
  `tests/test_verification_sweep.py:879` — `test_exactly_one_module_imports_the_judge`),
  so the other placement leaves no way to share one implementation. The
  abridgement record MUST be taken over that same assembly with the same patterns
  (`factory/verify/diffbounds.py:159` — `abridgement`, called at
  `factory/verify/diffcheck.py:262`), so the record and `prepare_diff` cannot
  disagree about whether the judge saw the diff whole. And the refusal's
  `largest_files` MUST be built from that same narrowed measurement — a section
  whose body was not counted MUST NOT appear in it — so no entry can state more
  bytes than the `total_bytes` it is recorded beside.
- **FR-012**: The verification record MUST state which paths were excluded from
  the measurement and how many bytes they carried, on every attempt where any
  were — and that disclosure MUST survive the store, written by
  `factory/verify/store.py:1129` — `_output_check_to_dict` and read back by
  `factory/verify/store.py:1214` — `_output_check_from_dict`, with an absent
  field meaning "nothing was excluded" for every row written before this story.
- **FR-013**: The patterns MUST reach
  `factory/verify/diffcheck.py:172` — `check_output` from the pinned epic input
  through the output-check activity's
  input, and an activity input declaring none MUST measure byte-identically to
  today.
- **FR-014**: The size refusal MUST NOT be removed, weakened or made optional and
  `diff_check` MUST stay mandatory: a diff of non-generated bytes above the
  threshold MUST still be refused, a diff carrying no declared pattern MUST be
  refused with today's message and today's `largest_files` list byte for byte,
  and a v2 manifest declaring a `verify:` list without `diff_check` MUST still be
  refused by `factory/verify/factory_yaml.py:958-963`.

- **FR-015**: With no `generated_paths` declared, the diff sections and the file
  listing built from any diff MUST be byte-identical to the ones today's code
  builds. This is the empty-declaration control for the classification FR-005
  adds, and it is US4's to prove because US4 is where the classification lands.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-006]
US4:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-004, FR-005, FR-015]
US2:
  depends_on: []
  depends_on_merged: [US4]
  implements: [FR-007, FR-008, FR-009, FR-010]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-011, FR-012, FR-013, FR-014]
```

Three `depends_on_merged` edges, declared rather than left inferred (069-US2
FR-007), and all three are ordering rather than contention relief. **US4 is
numbered last and runs second**: it was split out of US1 on 2026-09-08 because the
pair ran to thirteen tasks and no story above eleven has landed on this floor. The
number is a label; the edges are the order, and they read US1 -> US4 -> US2 -> US3.

US4 cannot be written against a tree where US1 has not landed, because there is no
parsed declaration to carry or to classify against.

US2 reads a classification and a pinned value US4 adds, so it cannot be written
against a tree where US4 has not landed: `prepare_diff` has nothing to elide
until a section knows whether it is generated, and nothing to be given until the
epic input carries the patterns.

The US2 -> US3 edge is the one worth arguing, because the two stories touch
different functions and could otherwise run together. It exists because the
half-landed states are not symmetric. US2 alone leaves the judge's prompt better
and every story refused today still refused, at one stated cost: the abridgement
record shares `factory/verify/diffbounds.py:137` — `assembled`, whose measurement
US2 does not change, so between US2 merging and US3 merging a pattern-declaring
repository records a total above the attention limit for a prompt that was not
abridged, and `factory/cli/nouns/build.py:1625` renders that row as abridged.
That is 092 FR-007's disclosure, wrong, for one story's duration; FR-011 closes
it by construction, which is why it is written into US3 rather than left to be
noticed. US3 alone is worse than a wrong record: the refusal would let through a
diff whose judge prompt still hands 37% of the allowance to a lockfile, so a
story that is honestly refused today would instead be judged badly — worse than
the defect this spec exists to remove. The edge makes that state unreachable and
bounds the interim cost to one story.

The three stories also overlap on files, which the same edges serialise:
`factory/verify/diffbounds.py` is touched by all three — US1 adds the
classification and the listing marker, US2 adds the one stub function FR-007 and
FR-011 require to have a single home there, and US3 narrows `assembled` and the
refusal record — `factory/verify/models.py` by US1 and US3, and
`factory/workgraph/workflow.py` by all three, one line each.
