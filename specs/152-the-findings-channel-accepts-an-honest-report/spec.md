---
state: draft
fixes:
  - doctor/the-credential-sweep-on-findings-report-refuses-a-note-that-names-the-repositorys-own-epic
  - doctor/the-credential-sweep-runs-inside-the-batch-write-loop-so-a-refused-batch-is-partially-written
# DRAFTED 2026-09-04 by the refinement workflow (refinement-2026-09-04) from
# docs/triage-2026-09-03-ergane-web-round3.md § "the-findings-channel-accepts-an-honest-report"
# (lines 401-418), against ergane-buildout at 602a92c. Every `file:line` in
# spec.md and plan.md was read from that commit with `sed -n 'Np'` and verified
# to resolve to the symbol named, not recalled.
#
# WHERE THIS CAME FROM. N32 of the `ergane-web` round-2 hand-over, filed by a
# consumer repository that is itself a target of this factory (D-003), plus a
# sibling defect the same reporter isolated on 2026-08-28 while trying to file
# it. Both ledger rows were read in full before this spec was written; neither
# is cut from its own name.
#
# WHAT IT COST, MEASURED. Three server-side refusals, none of which could name
# what they had matched, against a local pre-screen that found the second match
# in seconds — the information exists at the point of refusal and is simply not
# returned. Four occurrences on the reporter's side, escalating from a single
# word being unmentionable to a whole epic directory being unmentionable. The
# ledger rows sit at `info` and `warning`; the recurrence, not the severity
# label, is the argument. The sibling row records a demonstration on a scratch
# store: a three-entry batch whose second note held one ordinary hyphenated
# English adjective and no credential of any kind, after which entry one was
# committed and the operator was told the batch was refused.
#
# THE ANCHORS THE SOURCE ENTRY GOT WRONG, AND IT IS THE DANGEROUS KIND. The
# triage entry's trap 1 cites `factory/doctor/cli.py:43` as the one line to fix.
# That module is not on the live path: `ergane findings report` is registered at
# `factory/cli/doctor.py:293` and handled by `factory/cli/doctor.py:450`, and
# `factory/cli/doctor.py:54` imports the legacy module for exactly one function.
# An implementer obeying the entry would edit a line no command reads, pass every
# gate, and change nothing. The two ledger rows' own refs already point at the
# live module; the document does not. Recorded as trap 1 in plan.md.
#
# WHAT THE RE-READ ADDED. The pattern is defined THREE times, not once —
# `factory/cli/doctor.py:58`, `factory/doctor/scaffold.py:21` and the legacy
# `factory/doctor/cli.py:43` — and the copy in the scaffolder redacts on the way
# OUT, so an honest note naming a hyphenated identifier is silently rewritten
# into the promoted spec. FR-004 makes the three one. That is a scope addition
# beyond the entry's Scope line, taken deliberately: a fix applied to one of
# three copies is the exact shape of the half-fix this floor has now recorded
# three times (100, 092, 120), and the ledger cannot tell a whole fix from a
# third of one. (The count in this paragraph is wrong and is corrected by the
# REPAIRED entry below: there are four copies, not three.)
#
# HOW THE TWO KEYS MAP, AND WHY NEITHER CLOSES ON ONE STORY. Both rows were read
# in full from `.factory/doctor.db` (`ergane findings list --json`) and both are
# open. The first records two complaints, not one: an unanchored pattern, closed
# by FR-001 through FR-004 in US1, and a refusal that names nothing, closed by
# FR-005 and FR-006 in US2. The second is the partial write, closed by FR-007 and
# FR-008, also in US2. Neither key is closed by US1 alone; if US2 is descoped,
# both come out of `fixes:` in the same edit. Two other `doctor/` rows are open and
# neither is declared here: the stale-worker probe row belongs to the probe path,
# and the missing repository column is the per-repo schema change the source entry
# puts out of scope by name.
#
# NEIGHBOURS. Nothing has landed on `factory/cli/doctor.py`,
# `factory/doctor/cli.py`, `factory/doctor/store.py`, `factory/doctor/models.py`
# or `factory/doctor/scaffold.py` since 2026-08-29 (089-US1/US2), well before the
# 2026-09-03 triage, so no neighbour landing changes this spec's shape.
#
# NOT IN SCOPE. This spec does not weaken the sweep for real credentials — FR-002
# is the control that says so, run through both doors. It adds no override flag
# and no way to force a refused report through. It does not change the findings
# schema, the batch grammar at `factory/doctor/models.py:81`, the recurrence
# machine at `factory/doctor/store.py:137`, or any severity in the ledger. It
# does not touch the boundary detector's own write path
# (`factory/workgraph/detector.py:43`), which reaches the store without going
# through this verb at all.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), against ergane-buildout at
# 602a92c, after an adversarial review refuted the draft: the copy count is
# corrected from three to FOUR and the export scrubber is brought into scope
# (FR-003, FR-004, US1-S4, new US1-S5, Sizing, trap 2); causal-chain step 5 is
# corrected — the scaffolder does NOT reach `factory/cli/doctor.py:82`, it has
# its own `_sanitize_text`; FR-003's list of doors is corrected from "listed" to
# the three call sites that actually exist; FR-008 is narrowed from "for any
# reason" to the two refusals this spec owns, because the hoist writes nothing
# rather than rolling anything back; and the pattern's literal source is removed
# from plan.md so the trio stays quotable in a finding. No FR is renumbered, no
# story is split, no key is added or removed, and both holds below survive.
#
# THE FOURTH COPY, AND WHY IT IS THE WORST ONE. `factory/cli/repo_export.py:55`
# compiles the same shape a fourth time, inside `_SECRET_PATTERNS`, consumed by
# `factory/cli/repo_export.py:197` — `_clean`, "the one choke point every exported
# string passes through". `_STORES` at `factory/cli/repo_export.py:64-68` names
# `doctor.db`/`findings`, so every exported finding's `notes` runs through it:
# `ergane repo export` rewrites the honest hyphenated word to the marker in a
# file the operator hands to someone else, for exactly the reason this spec
# exists. The draft's identity test asserted across three modules and would have
# gone green over the fourth — the half-fix its own trap 2 was written to
# prevent. That module keeps its two other credential shapes and the wider
# doctrine written at `factory/cli/repo_export.py:50-53`; only the shared shape
# becomes the one anchored object, and FR-002's control proves a boundary
# credential is still redacted on the way out.
---

# Feature Specification: the findings channel accepts an honest report

**Created**: 2026-09-04
**Depends on**: nothing.

## The gap, stated precisely

The one class of false positive that silences the reporting channel itself: a
target repository cannot file a finding whose text names its own primary epic,
and naming the epic is the first thing any useful finding does. The report that
documented this bug could not be filed verbatim, by the bug.

The chain is seven steps, and the last three are a second defect wearing the
first one's clothes:

1. The credential pattern at `factory/cli/doctor.py:58` requires two literal
   letters, a hyphen, and eight or more characters from a class that includes
   letters, digits, underscore and hyphen — with **no left boundary**, so it may
   begin matching in the middle of an ordinary word.
2. `factory/cli/doctor.py:76` — `_contains_secret` returns a bare `bool` from
   `.search()`, discarding the match object, so the offset and the span are gone
   before any caller can report them.
3. The refusals therefore name nothing: `factory/cli/doctor.py:482` inside
   `factory/cli/doctor.py:450` — `findings_report_command` raises with a fixed
   sentence, and the batch variant at `factory/cli/doctor.py:458` names only the
   entry's key. No field, no offset, no redacted span. The only way to find the
   cause is to bisect your own note.
4. So an English word whose last two letters are the pattern's two letters,
   immediately followed by a hyphen and a long lower-case tail, is refused as a
   credential — and an epic identifier of that shape makes its own repository
   unable to report anything that names it.
5. The same shape drives the redaction on the way **out**, and it does so from
   three further copies, none of which reads the one at `factory/cli/doctor.py:58`.
   `factory/cli/doctor.py:82` — `_sanitize_text` substitutes the marker over probe
   output at `factory/cli/doctor.py:201` — `_run_all_probes` and over every finding
   being promoted at `factory/cli/doctor.py:537`. The scaffolder substitutes it
   again from its **own** copy at `factory/doctor/scaffold.py:21`, through
   `factory/doctor/scaffold.py:281` — `_sanitize_text`, reached at
   `factory/doctor/scaffold.py:53` when the trio is built. And the exporter
   substitutes it a third time from a copy at `factory/cli/repo_export.py:55`,
   through `factory/cli/repo_export.py:197` — `_clean`, over every string of every
   row of every store named in `factory/cli/repo_export.py:64-68` — the findings
   store among them. The false positive does not merely refuse a report; it
   rewrites an accepted one, in the promoted spec and in the exported file.
6. In the batch door the sweep runs **inside** the write loop: the loop opens at
   `factory/cli/doctor.py:457`, the two refusals sit at `factory/cli/doctor.py:458`
   and `factory/cli/doctor.py:462`, and the write is the next statement at
   `factory/cli/doctor.py:466`. `factory/doctor/store.py:149` — `report` opens
   `with conn:`, which commits on exit. Entry N tripping the sweep therefore
   leaves entries 1..N-1 committed while the verb exits saying the batch was
   refused — contradicting the all-or-nothing guarantee stated and tested at
   `specs/015-factory-doctor/spec.md:119-123`, which the grammar check at
   `factory/doctor/models.py:81` — `parse_findings_batch` does honour.
7. And the obvious recovery corrupts the evidence. `report` is a recurrence
   machine: `factory/doctor/store.py:170` increments `occurrences` and
   `factory/doctor/store.py:171` advances `last_seen`. An operator who fixes the
   tripping entry and re-runs double-counts every earlier key, and `last_seen` is
   the exact field `factory/doctor/triage.py:631` — `_class_declared` uses to
   separate the fixed class from the seen-after-fix class.

## The rule this spec is asking for

**The sweep refuses text that carries a credential, tells the reporter where it
matched without repeating what it matched, and writes nothing at all when it
refuses.**

The five cases, complete:

| what the text carries | today | after this spec |
|---|---|---|
| an ordinary word whose tail happens to fit the pattern, hyphen and all | refused, naming nothing | **accepted** |
| a credential beginning at a token boundary | refused, naming nothing | refused, naming the field, the offset and the characters **before** the match — never the match |
| a credential in the third entry of a three-entry batch | refused; entries one and two are already committed, with `occurrences` incremented | refused; the store is byte-for-byte unchanged |
| two offending entries in one batch | refused, naming the first only | refused, naming both |
| an already-stored note of the first shape, on its way out through promote, scaffold or export | rewritten to the redaction marker in the promoted spec and in the exported file | left intact, while a real credential in the same note is still redacted |

### What this spec is not

It is not a relaxation of the sweep. A credential that begins at a token boundary
is refused exactly as it is today, in the batch door and the single door alike,
and FR-002 is the control that proves it.

It is not a narrowing of the export scrubber. `factory/cli/repo_export.py` keeps
both of its other credential shapes and keeps the doctrine written at
`factory/cli/repo_export.py:50-53` — deliberately wider than any one store's
contents, because the cost of a miss is a key in a file handed to someone else.
Only the one shared shape becomes the single anchored object, and the two shapes
beside it in `factory/cli/repo_export.py:55` already carry a left boundary of
their own, which is why anchoring the third is a correction rather than a
loosening. FR-002's control covers the export door as well as the two report
doors.

It is not an override. There is no flag, environment variable or force switch
that lets a reporter push text past the sweep; the fix is that the sweep stops
being wrong, not that it becomes optional.

It is not a schema change. The findings grammar, the recurrence machine and the
ledger's severities are untouched; a batch that parses today parses identically
after this spec.

## User Scenarios & Testing

### User Story 1 - A hyphenated English word is not a credential (Priority: P1)

As a target repository filing a finding about my own build, I can name my own
epic in the note without the channel refusing me — and without that name being
rewritten to the marker in the promoted spec or in the exported file — and the
sweep still catches a real credential on every one of those paths.

**Why this priority**: P1 and it depends on nothing. This is the half that opens
the channel back up. US2 makes a refusal legible, which only matters for the
refusals that survive this story.

**Independent Test**: Report a finding whose note contains a hyphenated word of
the tripping shape and read the exit; report one carrying a synthetic credential
at a token boundary and read the refusal; promote a finding whose note contains
that same hyphenated word and read the scaffolded text; export a store holding
that note and read the exported file.

**Acceptance Scenarios**:

1. **Given** a finding note containing an ordinary word whose final two letters
   are the pattern's two letters, immediately followed by a hyphen and a
   ten-character lower-case tail — built in the test from separate fragments, never
   written literally — **When** it is reported through the live verb, **Then** a
   committed test asserts the report is accepted and the stored note is identical
   to the text submitted, character for character.
2. **Given** a synthetic credential value that begins at a token boundary — after
   a space, and again after an `=` — **When** it is reported through the batch door
   and through the single door, **Then** a committed test asserts both are refused
   and that no row was written by either. This is the control: a diff that
   satisfies scenario 1 by deleting the sweep fails here.
3. **Given** a stored finding whose note contains that same hyphenated word,
   **When** it is promoted and the trio is scaffolded, **Then** a committed test
   asserts the scaffolded text contains the word intact and does not contain the
   redaction marker — because a second copy of the pattern drives the substitution
   at `factory/doctor/scaffold.py:281` and a fix applied only to the refusal leaves
   this path rewriting honest prose.
4. **Given** the four modules that sweep or redact —
   `factory/cli/doctor.py:58`, `factory/doctor/scaffold.py:21`,
   `factory/doctor/cli.py:43` and `factory/cli/repo_export.py:55` — **When** each is
   imported, **Then** a committed test asserts all four name the **same** compiled
   pattern object by identity, so a future correction cannot be applied to part of
   the sweep and declared whole.
5. **Given** a findings row whose `notes` holds both that hyphenated word and a
   synthetic credential at a token boundary, **When** the store is exported
   through `factory/cli/repo_export.py:197` — `_clean`, **Then** a committed test
   asserts the exported text contains the word intact and contains the redaction
   marker in place of the credential — the fourth copy, on the one path that hands
   the file to someone else.

### User Story 2 - A refusal says where it matched, and refuses before it writes (Priority: P2)

As a reporter whose text was refused, I am told the field and the offset instead
of being asked to bisect my own note — and a refused batch leaves my ledger
exactly as it found it.

**Why this priority**: P2 and it consumes the single pattern US1 creates. Its two
halves are the two ledger rows this spec declares: the refusal that names nothing
is the second half of the first row, and the partial write is the whole of the
second.

**Independent Test**: Report a finding carrying a synthetic credential and read
the refusal text; run a three-entry batch whose third entry carries one against a
store already holding the first entry's key, then read that key's row.

**Acceptance Scenarios**:

1. **Given** a finding note carrying a synthetic credential twenty characters
   into the note, **When** it is refused, **Then** a committed test asserts the
   refusal names the field (`notes`), names the offset, and quotes the characters
   of that field immediately preceding the match.
2. **Given** the same refusal, **When** its text is read, **Then** a committed
   test asserts the matched value does not appear anywhere in it and that the
   redaction marker stands in its place. Scenario 1 without this one is a leak.
3. **Given** a three-entry batch whose **third** entry carries a synthetic
   credential, run against a store that already holds the first entry's key with
   `occurrences` at 1 and a known `last_seen`, **When** the batch is refused,
   **Then** a committed test asserts no new row exists, and that the pre-existing
   row still reads `occurrences` 1 with its original `last_seen` — the field
   `factory/doctor/triage.py:631` — `_class_declared` reads. A store-empty
   assertion alone does not cover the re-run, which is where the evidence is
   corrupted.
4. **Given** a batch whose **second and fourth** entries each carry a synthetic
   credential, **When** it is refused, **Then** a committed test asserts the
   refusal names both keys, in file order, in one message — following the staged
   rejection the grammar check already uses at `factory/doctor/models.py:66` —
   `raise_if_any`.
5. **Given** the single-finding door and the batch door refusing the same text,
   **When** both refusals are read, **Then** a committed test asserts they carry
   the same field, offset and preceding-context rendering, because both call one
   formatter — proving no door was fixed alone.

## Functional Requirements

- **FR-001**: The credential pattern MUST NOT match when the character
  immediately preceding its two-letter prefix is an ASCII letter or digit, so an
  ordinary hyphenated word is not read as a credential.
- **FR-002**: The pattern MUST still match a credential that begins at a token
  boundary — at the start of the text, after whitespace, or after a separator such
  as `=` or `-` — both report doors MUST still refuse one and write nothing, and
  the export scrubber MUST still replace one with the redaction marker.
- **FR-003**: Every redacting substitution driven by this shape MUST use the same
  anchored pattern as the refusal — the one at `factory/cli/doctor.py:82` reached
  from probe output and from promote, the scaffolder's at
  `factory/doctor/scaffold.py:281`, and the exporter's at
  `factory/cli/repo_export.py:197` — so honest prose is not rewritten to the
  redaction marker on the way out of any of them.
- **FR-004**: The package MUST hold exactly one compiled pattern for this
  credential shape, and every module that sweeps or redacts with it MUST consume
  that one object; a committed test MUST assert the identity across the four
  modules that hold a copy today. The two other shapes in
  `factory/cli/repo_export.py:55` are unchanged and stay where they are.
- **FR-005**: A refusal MUST name the field it matched in, the zero-based
  character offset of the match within that field, and the up-to-twelve characters
  of that field immediately preceding the match.
- **FR-006**: A refusal MUST NOT contain the matched text; the span MUST be
  rendered as the redaction marker, and a committed test MUST assert the synthetic
  value is absent from the message.
- **FR-007**: In the batch door the sweep MUST run over every parsed entry before
  the first row is written, and MUST name every offending entry in one message
  rather than stopping at the first.
- **FR-008**: When a batch is refused by the grammar check or by the credential
  sweep, the store MUST be unchanged: no row inserted, no `occurrences`
  incremented, and no `last_seen` advanced. The guarantee comes from writing
  nothing, not from undoing a write.
- **FR-009**: The single-finding door and the batch door MUST produce their
  refusal text through one shared formatter, so neither can be corrected alone.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-005, FR-006, FR-007, FR-008, FR-009]
```

One `depends_on_merged` edge, declared rather than left inferred (069-US2
FR-007). It is doing two jobs. First, correctness of sequencing: US2's refusal
formatter must ask the pattern where it matched, and FR-004 makes "the pattern" a
single object that US1 creates — a US2 written against four copies would report
an offset computed by whichever copy its module happened to import. Second,
contention: this is the one pair in this spec that does **not** touch disjoint
files. Both stories edit `factory/cli/doctor.py`, US1 in the helper block at
lines 58 to 98 and US2 in `findings_report_command` at lines 450 to 504, and
serialising them is cheaper than resolving that overlap in the merge queue.
