---
state: draft
fixes:
  - init/the-init-verb-ships-a-spec-driven-factory-with-an-empty-specs-directory-and-no-agent-context
# DRAFTED 2026-09-04 by the refinement workflow (refinement-2026-09-04) from
# docs/triage-2026-09-03-ergane-web-round3.md § "a-scaffolded-repo-arrives-with-
# the-context-its-agents-need" (lines 167-183), against ergane-buildout at
# 602a92c. Every `file:line` in spec.md and plan.md was read from that commit
# with `sed -n 'Np'` and verified to resolve to the symbol named, not recalled.
#
# WHERE THIS CAME FROM. N43 of the `ergane-web` round-2 hand-over, filed
# 2026-08-29 and carried into the round-3 triage. It is the ledger's only
# `critical` row about what a stranger's repository looks like the moment ergane
# has finished scaffolding it. The reporter is a target repository of this
# factory (D-003), so the observation is a measurement rather than a review.
#
# WHAT IT COST, MEASURED. The reporter's own session — a hand-written CLAUDE.md
# whose second sentence says the repository is built by the factory, which is the
# strongest advisory context that has ever been put in front of one of these
# sessions — still hand-wrote 139 lines of Python into `.claude/skills/`, landed
# it, and offered four green gates as evidence. `pyproject.toml:87` collects
# `tests/` and nothing else, so those four gates covered none of the 139 lines.
# The work was reverted. The finding's own ranking of remedies follows from that
# one measurement: an enforcing hook is the only class of thing that corrected
# the session, and advisory prose is "necessary and insufficient".
#
# THE ENTRY'S FIRST TRAP IS NOW STALE, AND THAT IS THE WHOLE RESCOPE. The triage
# was verified at `238b494`; spec 057 landed its four stories the same day, at
# `8ee5e9c`, `5c43d4a`, `1027a05` and `602a92c`. `standards` is no longer empty
# by default: `factory/cli/init.py:1263` assigns it unconditionally and
# `factory/cli/init.py:1273` seeds a constitution at
# `.specify/memory/constitution.md`. So the `.specify/` quarter of the declared
# finding is already fixed and this spec does not re-fix it. What remains is the
# `.claude/` unit: the skills channel that is the only one a dispatched node can
# read, and the hook the finding ranked first.
#
# SUPERSESSION OF 087, IN WRITING AND DELIBERATELY.
# `specs/087-the-operators-skills-arrive-with-the-cli` is draft, un-refined, and
# rules this work out: "A story here that writes into a target repository is a
# defect even if it works" (spec.md:52), restated as its FR-010 (spec.md:276).
# That ruling came from an operator answer about *operator* skills on 2026-08-22
# and it stands for those. This spec owns the target-repo agent-context unit and
# supersedes the ruling for that unit alone; 087 keeps the operator-side skills
# and its FR-010 should be narrowed to "MUST NOT install operator skills into a
# target repository" when 087 is next refined. The two do not share a file: 087
# installs under the operator's own `$HOME`, this spec under `<repo>/.claude/`.
#
# NOT IN SCOPE. `CLAUDE.md` is not written, edited or read by this spec, in any
# repository. D-025 (`docs/decisions.md:600-608`) put standards in the manifest's
# `standards` key precisely "because a committed file is adapter-agnostic — no
# reliance on `CLAUDE.md` auto-loading", and `tests/test_claude_md.py` holds this
# repository's own page to orientation only. The finding's summary names a
# missing `CLAUDE.md` among four absences; that one is a remedy the tree has
# already ruled out and the reporter himself graded insufficient, so it is
# refused rather than deferred, and the key is declared whole on that basis.
# That refusal needs a successor artifact rather than a silence: when triage
# closes this key, the operator records against the row that the `CLAUDE.md`
# block the reporter graded "necessary" was *rejected* under D-025 and not
# overlooked, so the ledger carries the ruling. This spec files no such row
# itself — a draft spec may not write the doctor's store. Also
# out: scaffolding spec content beyond what `ergane spec new` already produces
# (`factory/doctor/scaffold.py:27` — `scaffold_spec`), any change to what the
# gates run, and any general prohibition on an operator writing code.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04): the hook's rule gained the actor
# dimension the ledger row itself carries ("on an operator branch") — a
# dispatched factory node is exempt by FR-021, because without it the installed
# hook refuses every implementer node's own production write and no environment
# variable can rescue it past `PASSTHROUGH_ENV`; the install rule gained its
# fourth state, a payload path already holding bytes ergane never recorded, so a
# first init cannot overwrite an operator's own `.claude/` file (FR-005, US2-S6);
# FR-004 and FR-005 now name the on-disk shape a project skill must have
# (`skills/<name>/SKILL.md` with `name`/`description` frontmatter, installed
# path-preserving) rather than two substrings in a file of any shape; FR-012
# gained the existence filter on a pack's declared source roots and a stated rule
# for which command word is a path, so `build` and `run` are not derived and a
# declared root the repository lacks is dropped; FR-020 makes init's own
# `git add` line name the unit it just installed; the `--check` half of US3 was
# split out as US5, unrenumbered, because US3 was the story with the least
# headroom under D-050's 64 KiB bound; FR-001's exemplar corrected from the
# registry resolver to the pack-directory resolver; and both other callers of
# `_write_scaffold` (`factory/cli/install.py:1001`,
# `factory/supervision/demo_driver.py:409`) are now named and scoped out in
# writing rather than left invisible behind a false uniqueness claim.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), second pass, answering the
# adversarial review: the refusal signal moved off exit 2, because `argparse`
# already exits 2 for an unrecognised verb (measured: `ergane repo gate-paths
# --check` exits 2 today) and 2 is the only status a `PreToolUse` hook blocks
# on, so the shipped `settings.json` on a host carrying an older `ergane` would
# have refused every Write in that repository — FR-014 now owns a status
# `argparse` cannot produce and new FR-022 makes the declared command translate
# it; FR-021 stopped keying the node exemption on the runtime root's directory
# name, which `factory/workgraph/worktree.py:191` — `resolve_factory_root`
# returns from an `ERGANE_ROOT`/`FACTORY_ROOT` override verbatim, and keys on
# the path shape and the node branch instead, which no override moves; FR-008
# alone gained the repository's *effective* ignore rules — FR-018 reports the
# derived gate-path set and says nothing about ignore rules — so a target that
# already ignores `.claude/` is told rather than silently handed a unit no node
# will see; FR-006 states that the install record is itself installed and
# committed, without which a second clone can never update anything; FR-014's
# trailing "with no message" clause, which contradicted FR-015, FR-016 and
# FR-021, is gone. Scenarios US2-S8, US4-S5, US5-S6 and the third assertion in
# US5-S3 are the reproductions.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), third pass, answering the second
# adversarial review: US2-S6 stopped naming a `settings.json` that is not in the
# payload at US2's dispatch — `settings.json` enters with FR-017 in US4, so the
# pre-existing case for that one file is US4-S4 under FR-019, and US2-S6 now
# reproduces the same install-table row against the one payload path US1 does
# ship plus a file of the operator's own at a path the payload does not name;
# T012 and T022 follow it and plan trap 13 states the ordering. Two US2 task
# citations of FR-018 are gone, because FR-018 is US4's and needs US3's
# derivation, which US2 has no edge to. FR-016's escape variable is named
# outright — `ERGANE_SKIP_GATE_PATH_CHECK`, after `scripts/hooks/pre-push:26` —
# so the operator sequence in plan.md is runnable without reading US5's diff.
# The refused `CLAUDE.md` remedy gained a successor sentence above, so closing
# this key leaves a ruling in the ledger rather than a silence.
---

# Feature Specification: a scaffolded repo arrives with the context its agents need

**Created**: 2026-09-04
**Depends on**: nothing. Spec 057 landed on 2026-09-03 and this spec builds on
what it left, but it needs no unlanded work.

## The gap, stated precisely

`ergane init` scaffolds a spec-driven factory into a repository and puts nothing
in the one directory a dispatched agent can read.

The chain is five short steps:

1. Init's scaffold writer says out loud what it writes.
   `factory/cli/init.py:1816` — `_write_scaffold` opens "Write exactly the
   declared files and nothing else", and the declared files are the manifest
   (`factory/cli/init.py:1826-1828`), one `.gitignore` line
   (`factory/cli/init.py:1830-1837`), the runtime root
   (`factory/cli/init.py:1839-1840`) and an empty `specs/`
   (`factory/cli/init.py:1842-1843`). Spec 057 added a fifth output beside it on
   2026-09-03 — the seeded constitution at `factory/cli/init.py:1273`.
2. The one channel that reaches a dispatched agent is `<repo>/.claude/skills/`,
   and this tree already records why: `factory/config.py:177-179` states that
   home-scoped skills are invisible to a node because dispatch constructs a
   per-node HOME (`factory/workgraph/adapter.py:815` — `home_path`), and that
   "Project-scoped skills committed at `<repo>/.claude/skills/` remain visible,
   because the node's worktree carries committed files".
3. Ergane writes nothing there.
   `grep -nE 'CLAUDE\.md|\.specify|\.claude' factory/cli/init.py` returns exactly
   one line, `factory/cli/init.py:1847` — the constitution's default path — and
   nothing at all under `.claude/`.
4. Nor could it today: the distribution carries no such payload. The wheel ships
   `packages = ["factory"]` (`pyproject.toml:49`), and the only non-Python data
   inside that package is the three stack packs 057 added
   (`factory/stack_packs/python.yaml`) and one merge-queue ruleset
   (`factory/mergequeue/merge_queue_ruleset.json`).
5. And advisory context has been measured insufficient on exactly this
   repository. The reporter's session hand-wrote 139 lines of Python into
   `.claude/skills/` and offered four green gates as evidence, while
   `pyproject.toml:87` declares `testpaths = ["tests"]`, so nothing under
   `.claude/` was collected and those gates covered none of it.

**The consequence is not "the agent is less informed".** It is that the design's
only agent-facing channel is empty in every repository ergane has ever
scaffolded, and that the one remedy the finding could measure — an enforcing
hook — does not exist in any form.

## The rule this spec is asking for

**A repository ergane scaffolds arrives carrying one versioned unit of agent
context — the skills a dispatched node can actually read, and a Write/Edit hook
scoped to the paths that repository's own gate commands compile and to writers
who are not the factory's own dispatched nodes — installed by `init`, updated by
a later `init` only where the operator has not edited it, never overwriting a
file the operator had there first, and carried inside the distribution rather
than copied by hand.**

The hook's decision, complete. The second column is the qualifier the ledger row
states in its own words and this spec's first draft dropped: the rule is that
"code under the paths your own gates compile should not arrive **on an operator
branch**", and a dispatched implementer node is not an operator:

| target path under a derived gate path | invocation is a dispatched factory node | manifest and payload readable | escape variable set | result |
|---|---|---|---|---|
| yes | no | yes | no | **refuse**, with the unit's own refusal status, naming the path, the gate and the rule |
| no | — | yes | no | allow, silently |
| yes | **yes** | yes | — | allow, and say the node exemption applied |
| yes | no | yes | **yes** | allow, and say the escape was used |
| — | — | **no** | — | allow, and say on stderr what could not be read |

**The refusal is not exit 2, and that is measured rather than preferred.**
`argparse` exits 2 for an unrecognised verb or flag: on this tree today
`ergane repo gate-paths --check` exits 2 with
`argument verb: invalid choice: 'gate-paths'`, because the verb does not exist
yet. Exit 2 is also the only status a `PreToolUse` hook treats as a refusal. A
repository carrying the shipped `settings.json` on any host whose installed
`ergane` predates this verb — 0.5.0 is the released version, so that is the
ordinary rollout state — would therefore refuse every Write and Edit in that
repository, which is the lockout this spec exists to avoid. So the verb owns a
refusal status `argparse` cannot produce (FR-014), and the command the shipped
`settings.json` declares is what maps that one status to 2 and every other
status, 2 included, to 0 (FR-022).

The install decision, complete. The third column is the state a first install
actually meets in any repository that has ever been opened in an agent session:

| payload file at the target path | ergane recorded a digest for it | its bytes match that digest | result |
|---|---|---|---|
| absent | — | — | written, reported as seeded |
| present | yes | yes | rewritten to the shipped bytes, reported as updated |
| present | yes | **no** | **left untouched**, reported as kept |
| present | **no** | — | **left untouched**, reported as kept, and no digest recorded for it |

### What this spec is not

**It supersedes one ruling in `specs/087-the-operators-skills-arrive-with-the-cli`,
narrowly and in writing.** 087 says at `specs/087-the-operators-skills-arrive-with-the-cli/spec.md:52`
that "A story here that writes into a target repository is a defect even if it
works", and turns that into `specs/087-the-operators-skills-arrive-with-the-cli/spec.md:276`
— FR-010. That ruling was made about the five *operator* skills and it stands for
them. This spec owns the target-repository agent-context unit; 087 keeps the
operator-side install. They share no file: 087 writes under the operator's own
home, this spec under `<repo>/.claude/`.

**It does not write, edit or read `CLAUDE.md` in any repository.** D-025
(`docs/decisions.md:600-608`) chose the manifest's `standards` key over
`CLAUDE.md` auto-loading, and nothing here reopens that.

**It installs the unit from `init` only, not from the two demonstration paths
that share the scaffold writer.** `_write_scaffold` has three production callers,
not one: `factory/cli/init.py:1268`, `factory/cli/install.py:1001` and
`factory/supervision/demo_driver.py:409`. The second scaffolds a repository
inside a `tempfile.TemporaryDirectory` to demonstrate `check_repo` and deletes it
on the way out; the third is the container demo driver's step 3 of 5, against its
own throwaway repository. Neither is a repository a node is dispatched against,
and 057's seeded constitution is already absent from both for the same reason.
Installing the unit in one of them and not in `init` — or in the demos alone —
would make the demonstration diverge from init in a second way rather than
converge, so both are out of scope deliberately and named here so the next reader
does not mistake the omission for the false claim that init is the only caller.

**It does not scaffold spec content.** `ergane spec new` already produces a
compiling trio from code (`factory/doctor/scaffold.py:27` — `scaffold_spec`,
called at `factory/cli/nouns/spec.py:405`); this spec makes init *say* so and
adds nothing beside it.

**It is not a prohibition on writing code by hand.** The hook refuses only under
the paths a repository's own gate commands compile. A file those gates do not
compile is outside its reach by construction, and that is the design: the
operator legitimately hand-edits specs, the manifest, fixtures and docs, and a
blunt rule that refused those would be deleted whole rather than obeyed.

**It does not reach the write that produced the finding, and says so rather
than implying otherwise.** The hook refuses only under the paths a repository's
own gate commands compile, and `.claude/` is outside those by construction: in
this repository the single gate is `uv run pytest -q` (`ergane.yaml:34`) and the
derived set is `tests` alone, so the 139 lines of Python that step 5 measures
would not have been refused by this hook either. Step 5 is evidence that
*advisory* context fails, not evidence that this hook would have blocked that
particular write. What addresses that half is FR-003 — no `.py` file in the
shipped payload, so ergane never adds to the problem — and the skill document;
FR-013 and FR-018 are what keep the remaining gap visible instead of letting an
installed hook read as protection it does not give.

**It does not change what any gate runs**, and a repository that never runs
`ergane init` again is byte-identical to today.

## User Scenarios & Testing

### User Story 1 - The unit exists, is declared, and travels in the wheel (Priority: P1)

As a stranger who installed `ergane-cli` from PyPI, the agent context ergane
means to install is actually inside the thing I installed, in the shape an agent
can load.

**Why this priority**: P1 and it depends on nothing. Every other story installs,
renders or reads this payload; without it they have nothing to move. It is also
where the packaging defect lives, and packaging defects are invisible in a
checkout — 057's own pack test exists because an installed ergane once carried
none of its data files.

**Independent Test**: Build a wheel from the tree and list its contents; resolve
the unit through its resolver and read back its version, its file list and the
skill document's parsed frontmatter.

**Acceptance Scenarios**:

1. **Given** the shipped unit and a wheel built from this tree, **When** the
   wheel's entries are listed, **Then** the unit's declaration names at least one
   file and every file it names is present inside the wheel under `factory/`,
   proven by a committed test that reads the built zip rather than
   `pyproject.toml`, following `tests/test_057_us2_stack_pack.py:296` —
   `test_every_shipped_pack_travels_in_the_wheel`. The non-emptiness half is
   asserted first, because every other claim in this story is vacuous over an
   empty payload.
2. **Given** a payload file present in the package but absent from the unit's
   declaration, **When** the unit is resolved, **Then** resolution is refused
   with a message naming that file; and given a declaration naming a file that is
   not present, resolution is refused naming that file too. Both directions in
   one committed test, so a payload file added without being declared cannot
   ship unnoticed.
3. **Given** the shipped payload, **When** its entries are enumerated, **Then**
   none of them is a `.py` file, asserted by a committed test whose message names
   `pyproject.toml:87` as the reason — a shipped Python file under `.claude/`
   would be ungated by construction in every repository that received it.
4. **Given** the shipped skill document, **When** the payload is enumerated and
   the document is parsed, **Then** its relative path is `skills/<name>/SKILL.md`
   for the directory that holds it, its YAML frontmatter parses and carries both
   a `name` and a `description` key, and its body names the manifest's
   `standards` key and the `ergane spec new` verb as literal substrings — all
   four asserted by one committed test against the parsed document, following the
   shape this repository's own project skills use
   (`.claude/skills/spec-html/SKILL.md:1-3`). A document at any other relative
   path satisfies the substring half and loads in no agent, which is why the path
   and the frontmatter are asserted rather than the text alone.

### User Story 2 - `init` installs the unit, and a later `init` updates it without overwriting the operator (Priority: P1)

As an operator, running `ergane init` again gives me the current agent context,
does not throw away the edits I made to it, and does not touch what I had in
`.claude/` before ergane ever ran.

**Why this priority**: P1, and it is the story that closes the declared finding's
`.claude/skills/` half. It depends on US1 having something to install. The update
half is what makes the unit maintainable rather than a one-time drop.

**Independent Test**: Run init on a scratch repository twice, edit one payload
file between the runs, run it once more on a second repository that already
carries its own `.claude/` files, and read the resulting bytes, the install
record and every report.

**Acceptance Scenarios**:

1. **Given** a repository with no `.claude/` directory, **When** `ergane init`
   runs, **Then** every payload file exists under `<repo>/.claude/` at the
   payload's own relative path, carrying the shipped bytes, and an install record
   beside them names the unit version and one digest per installed file.
2. **Given** that repository with no payload file changed, **When** `ergane init`
   runs a second time, **Then** each payload file is rewritten to the shipped
   bytes and named in the report as updated, and the record carries the shipped
   version.
3. **Given** a payload file whose bytes the operator has changed, **When**
   `ergane init` runs again, **Then** that file's bytes are unchanged, the report
   names it as kept, and its unedited siblings are still updated in the same run.
4. **Given** a repository where init has just installed the unit, **When** the
   `.gitignore` init wrote is read, **Then** it matches none of the files init
   installed under `<repo>/.claude/`, asserted file by file over the install
   record rather than by looking for one literal string, and the test names the
   reason: a node's worktree carries committed files
   (`factory/config.py:177-179`), so an ignored unit reaches no agent at all.
5. **Given** a completed init run, **When** its "written:" report
   (`factory/cli/init.py:1326-1331`) is read, **Then** it names the unit's
   install root and version beside the existing lines, and states that `specs/`
   is scaffolded empty on purpose because `ergane spec new` produces a compiling
   trio.
6. **Given** a repository that already carries, at the relative path the
   shipped declaration names for it, a `<repo>/.claude/skills/<name>/SKILL.md`
   of its own that ergane never installed and for which the install record holds
   no digest, and beside it a second file the operator keeps under
   `<repo>/.claude/` at a path the payload does not name, **When** `ergane init`
   runs there for the first time, **Then** the file at the payload path holds
   byte-for-byte the bytes it held before, the report names it as kept, and the
   record it writes carries no digest for it; and the operator's other file is
   byte-for-byte unchanged and named nowhere in the report, because init decides
   over payload paths and touches nothing else under `<repo>/.claude/` —
   asserted by one committed test that reads both paths from the declaration
   rather than hardcoding them, because this is the state of every repository
   that has been opened in an agent session before ergane reached it. The same
   row for `settings.json` is US4-S4 under FR-019: that file enters the payload
   with FR-017, which US4 owns, so at this story's dispatch it is not a payload
   path and init has no opinion about it.
7. **Given** a completed init run, **When** the `git ... add ...` line init
   prints (`factory/cli/init.py:1342`, built by `factory/cli/init.py:1364` —
   `_paths_to_commit`) is read, **Then** it names every file in the install
   record *and the record itself*, and does not name `<repo>/.claude` as a
   directory, asserted file by file over the record by a committed test — an
   init that reports the unit written and then tells the operator to stage
   everything except it commits a repository whose unit reaches no node, and a
   record left uncommitted leaves the next clone with no digest for any payload
   file.
8. **Given** a repository whose own `.gitignore` already carried `.claude/`
   before ergane ran, **When** `ergane init` installs the unit, **Then** the
   report names each installed file the repository's effective ignore rules
   cover and states that the unit will reach no dispatched node until that
   changes, asserted by a committed test — the entry init writes is not the only
   entry that can hide the unit, and the operator's only other symptom is init's
   own printed `git add` line failing on ignored paths, with nothing in that
   failure connecting it to the "written:" block above.

### User Story 3 - The gate paths are derived from the manifest, and a verb answers with them (Priority: P1)

As an operator, ergane can say which paths my own gates compile, and can be wrong
only in the direction I can see.

**Why this priority**: P1 and it depends on nothing — it reads the manifest and
the stack packs, not the unit. It is the hard half of the finding: the scoping is
what makes the hook usable, and a blunt rule fails.

**Independent Test**: Derive the paths for repositories whose manifests carry the
shipped Python pack's gate commands, an `npm --prefix web run build` gate, and no
path-naming gate at all, and run the listing verb against each.

**Acceptance Scenarios**:

1. **Given** a repository carrying the shipped Python pack's markers and gate
   commands — `uv run pytest -q`, `uv run ruff check .`, `uv run mypy .`
   (`factory/stack_packs/python.yaml`) — that has a `tests/` directory and no
   `src/` directory, **When** the gate paths are derived, **Then** the repository
   root is **not** among them, `tests` is, and the pack's other declared source
   root `src` is **not**, because the repository does not contain it. A committed
   test asserts the root's absence by name, because `.` resolves to an existing
   path and a derivation that kept it would refuse every write in the repository,
   including the operator's specs; and asserts `src`'s absence, because a
   declared root that does not exist is a guess the hook would report as
   protection.
2. **Given** a repository with both a `web/` and a `build/` directory whose gate
   command is `npm --prefix web run build`, **When** the paths are derived,
   **Then** `web` is in the set and attributed to that gate by name, and neither
   `build` nor `run` is, asserted by one committed test — both are bare words
   that name existing directories, and only `web` is a path-shaped argument under
   FR-012's rule.
3. **Given** a repository whose gate commands name no path-shaped argument and
   whose resolved stack pack declares no source root that the repository
   contains, **When** the paths are derived, **Then** the set is empty and the
   derivation reports it as empty rather than falling back to the repository
   root.
4. **Given** a repository whose derivation yields two paths from two different
   gates, **When** `ergane repo gate-paths <repo>` runs, **Then** it prints one
   line per path naming the path and the gate it came from, asserted against the
   captured output by a committed test.

### User Story 5 - `--check` answers a tool hook, and knows an operator from a dispatched node (Priority: P1)

As an operator, the hook asks ergane one question per write and gets an answer
that refuses my hand-written production code without refusing the factory's own
implementer nodes.

**Why this priority**: P1. It is the half of the derivation that anything
actually calls, and it carries the one input whose absence would make the
installed hook stop the factory itself. Split from US3 rather than carried with
it because US3 plus this is the largest slice in the spec and D-050's 64 KiB diff
bound is a refusal, not a warning.

**Independent Test**: Run the verb against payloads on standard input in four
environments — an operator's, one whose HOME is a factory per-node home, one with
the escape set, and one whose manifest cannot be read.

**Acceptance Scenarios**:

1. **Given** a tool payload on standard input naming a file under a derived path,
   and an invocation that is not a dispatched node, **When**
   `ergane repo gate-paths --check` reads it, **Then** the command exits with
   the unit's declared refusal status and its message names the file, the gate
   the path came from, and the rule.
2. **Given** a payload naming a file under none of the derived paths, **When**
   the same command reads it, **Then** it exits 0 and writes no message.
3. **Given** a payload naming a file under a derived path and an environment
   whose `HOME` is a factory per-node home (`factory/workgraph/adapter.py:815` —
   `home_path`, the value `factory/workgraph/adapter.py:947` — `attempt_env`
   gives every dispatched child), **When** the command reads it, **Then** it
   exits 0 and writes one line saying the node exemption applied; and the same
   is asserted for a payload whose target path lies inside a node worktree
   (`factory/workgraph/worktree.py:289` — `worktree_path`), and a third time
   for both of those under a runtime root whose directory name is neither
   `.ergane` nor `.factory`, because `factory/workgraph/worktree.py:191` —
   `resolve_factory_root` returns an `ERGANE_ROOT`/`FACTORY_ROOT` override
   verbatim and a detector keyed on those two names would classify every node on
   such a host as an operator. All three in one committed test, because a hook
   that refuses here stops every implementer node from writing the production
   code it was dispatched to write.
4. **Given** an unreadable manifest, and separately a payload that does not
   parse, **When** the command reads each, **Then** it exits 0 in both cases and
   writes one line naming what it could not read — and a fixture of the payload
   shape is committed, so a change in that shape fails a committed test instead
   of silently allowing every write.
5. **Given** `ERGANE_SKIP_GATE_PATH_CHECK=1` in the environment, **When** the
   command reads a payload that would otherwise be refused, **Then** it exits 0
   and writes one line saying the escape was used, and the test names the
   variable literally rather than reading it back from the code under test.
6. **Given** the refusal path of scenario 1 and, separately, the `ergane repo`
   parser asked for a verb it does not have, **When** both exit statuses are
   captured in one committed test, **Then** the refusal status is not the
   parser's, and the parser's is 2 — asserted rather than assumed, because 2 is
   the only status a `PreToolUse` hook blocks on and a refusal that shares it
   makes every stale or renamed installation refuse every write.

### User Story 4 - The installed unit declares the hook, and says what it will and will not refuse (Priority: P2)

As an operator, the hook arrives wired up, and ergane tells me exactly what it
covers — including when that is nothing.

**Why this priority**: P2. It is small, and it depends on all four of the others
— the payload from US1, the install path from US2, the derivation from US3, the
verb from US5. Splitting it out keeps the larger stories from carrying a fifth
concern.

**Independent Test**: Parse the shipped `settings.json`, then run init on a
repository whose derivation is empty, on one whose derivation is two paths, and
on one whose `settings.json` the operator has changed, and read the reports.

**Acceptance Scenarios**:

1. **Given** the shipped payload's `settings.json`, **When** it is parsed,
   **Then** it declares a `PreToolUse` entry whose matcher covers both `Write`
   and `Edit` and whose command invokes `ergane repo gate-paths --check`,
   asserted by a committed test against the parsed document rather than against
   the file's text.
2. **Given** a repository whose derived gate-path set is empty, **When**
   `ergane init` runs, **Then** the report states that the installed hook will
   refuse nothing and names why — an installed hook that silently permits
   everything is worse than no hook, because it reads as protection.
3. **Given** a repository whose derived gate-path set is two paths, **When**
   `ergane init` runs, **Then** the report names both paths with their gates, so
   a set that covers the tests and not the production code is visible at install
   time rather than at the first refusal that never comes.
4. **Given** a repository whose `<repo>/.claude/settings.json` the operator has
   changed, **When** `ergane init` runs, **Then** that file is byte-for-byte
   unchanged and the report says the hook was not installed there, so the
   operator is told rather than left to discover it.
5. **Given** the command string the shipped `settings.json` declares and a stub
   `ergane` earlier on `PATH` that exits 2 with an `argparse` usage message,
   **When** that command string is executed against a payload that names a file
   under a derived path, **Then** its exit status is 0, proven by a committed
   test that captures it; and given the same command string with a stub that
   exits the declared refusal status, its exit status is 2. Both directions in
   one test, because an installed `ergane` that predates the verb is the
   ordinary rollout state and the first direction is the one that locks an
   operator out of their own repository.

## Functional Requirements

- **FR-001**: The agent-context unit MUST travel inside the import package as
  package data, resolved `importlib.resources`-first after
  `factory/stack_packs.py:182` — `resolve_stack_packs` and its directory
  resolution at `factory/stack_packs.py:196`, and MUST NOT be added to the
  wheel's force-include table: it lives inside `factory/`, and the table is for
  repo-root files.
- **FR-002**: The unit MUST carry a declaration inside the package naming its
  version and every payload file, and MUST name at least one; resolution MUST be
  refused when the declaration names a file that is absent, and MUST be refused
  when the payload holds a file the declaration does not name.
- **FR-003**: The shipped payload MUST contain no `.py` file, and a committed
  test MUST assert it, because `pyproject.toml:87` collects only `tests/` and a
  shipped Python file under `.claude/` would be ungated in every repository that
  received it.
- **FR-004**: The shipped payload MUST include a skill document at the relative
  path `skills/<name>/SKILL.md`, carrying YAML frontmatter with a `name` and a
  `description` key and a body naming the manifest's `standards` key and the
  `ergane spec new` verb. The path and the frontmatter are the loadable shape —
  `.claude/skills/spec-html/SKILL.md:1-3` is the exemplar in this repository —
  and a document of any other shape satisfies the text and reaches no agent.
- **FR-005**: `ergane init` MUST write, under `<repo>/.claude/` and at the
  payload's own relative path, creating parent directories, every payload file
  whose target path is absent or whose bytes match the digest recorded for it;
  MUST leave untouched any target path that already holds bytes for which the
  install record holds no digest; and MUST report which of the three happened,
  by path — on the same run that writes the manifest and the constitution.
- **FR-006**: `ergane init` MUST record the unit version and a digest of the
  bytes it wrote, per installed file, in an install record inside
  `<repo>/.claude/`, and MUST record no digest for a path it left untouched. The
  record is itself one of the installed files for FR-008's and FR-020's
  purposes — written under `<repo>/.claude/`, named in the staging line, and
  committed with the rest of the unit. A record that stays out of the repository
  leaves the next clone holding every payload file with a digest for none of
  them, so FR-005's fourth row keeps all of them forever and the update half of
  this spec works only for the operator who ran the first `init`.
- **FR-007**: A later `ergane init` MUST rewrite a payload file whose on-disk
  bytes still match its recorded digest, MUST leave a file whose bytes differ
  untouched, and MUST report which of the two happened, by path.
- **FR-008**: No `.gitignore` entry `ergane init` writes may match any file it
  installed under `<repo>/.claude/`, and a committed test MUST assert it file by
  file over the install record. `ergane init` MUST additionally test each
  installed file against the repository's *effective* ignore rules rather than
  against the entry it wrote alone, and MUST report, naming those files, when
  the unit it has just installed is ignored — a repository whose own
  `.gitignore` already carried `.claude/` receives the unit, is told it was
  written, and hands it to no dispatched node.
- **FR-009**: Init's written report (`factory/cli/init.py:1326-1331`) MUST name
  the unit's install root and its version.
- **FR-010**: Init's report MUST state that `specs/` is scaffolded empty
  deliberately and that `ergane spec new` produces a compiling trio.
- **FR-020**: The paths init prints for the operator to stage
  (`factory/cli/init.py:1364` — `_paths_to_commit`, printed at
  `factory/cli/init.py:1342`) MUST name every file in the install record, and
  the record itself, individually, and MUST NOT name `<repo>/.claude` as a
  directory, so that following init's own instruction commits the whole unit and
  nothing else the operator happens to keep there.
- **FR-011**: A stack pack MUST be able to declare the source roots its toolchain
  compiles, as data in the pack file, validated the way every other pack field is
  at `factory/stack_packs.py:141` — `_pack_from_data`; no code may branch on a
  pack's name.
- **FR-012**: A derivation MUST return, from a repository's declared gate
  commands (`factory/verify/models.py:310`) and its resolved stack pack, the
  repository-relative paths those gates compile, each attributed to the gate it
  came from. A word of a gate command counts as a path-shaped argument only when
  it names a path that exists in the repository **and** one of three things is
  true of it: it contains a path separator; it is the value of a preceding flag;
  or it is one of the pack's declared source roots. For a gate command that names
  no path-shaped argument, the pack's declared source roots are contributed
  instead, and a declared root the repository does not contain MUST be dropped
  rather than derived. The repository root MUST NOT be a derived path by any
  route.
- **FR-013**: `ergane repo gate-paths <repo>` MUST print the derived paths with
  their gates, one per line, and MUST print a line saying the set is empty and
  why when the derivation yields nothing.
- **FR-014**: `ergane repo gate-paths --check` MUST read a tool payload on
  standard input, resolve the target path from it, exit with the unit's declared
  refusal status and a message naming the path, the gate and the rule when that
  path is under a derived path and the invocation is not a dispatched factory
  node, and exit 0 otherwise. That refusal status MUST NOT be 2: `argparse`
  exits 2 for an unrecognised verb or flag — measured on this tree, where
  `ergane repo gate-paths --check` exits 2 today with
  `argument verb: invalid choice: 'gate-paths'` — and 2 is the only status a
  `PreToolUse` hook treats as a refusal, so a refusal that shares it turns every
  installation predating the verb, and every later rename of the verb or its
  flag, into a repository that refuses every Write and Edit.
- **FR-021**: `--check` MUST exit 0, writing one line saying the node exemption
  applied, when the invocation is a dispatched factory node. It MUST decide that
  from markers the factory already sets whose *shape* is fixed wherever the
  runtime root happens to live: a `HOME` whose trailing segments are
  `homes/<epic>/<node>` (`factory/workgraph/adapter.py:815` — `home_path`,
  carried into the child by `factory/workgraph/adapter.py:947` — `attempt_env`),
  a target path with a `worktrees/<epic>/<node>` tail
  (`factory/workgraph/worktree.py:289` — `worktree_path`), or a checked-out
  branch matching `factory/<epic>/<node>` (`factory/workgraph/worktree.py:284` —
  `branch_name`, which is the ledger row's "operator branch" made literal). The
  runtime root's own directory name MUST NOT be the key:
  `factory/workgraph/worktree.py:191` — `resolve_factory_root` returns an
  `ERGANE_ROOT`/`FACTORY_ROOT` override verbatim
  (`factory/workgraph/worktree.py:211-216`), so `.ergane`
  (`factory/workgraph/worktree.py:93`) and `.factory`
  (`factory/workgraph/worktree.py:96`) are defaults and not facts — this floor
  sets its own root from `scripts/ergane-env.sh:84`, and
  `factory/cli/repo.py:328` says the same in the tree's own words. It MUST NOT
  depend on a new environment variable reaching the node, and this spec MUST NOT
  edit the passthrough allowlist at `factory/workgraph/adapter.py:104`.
- **FR-015**: `--check` MUST exit 0, writing one line naming what it could not
  read, when the manifest is unreadable or the payload does not parse; a fixture
  of the payload shape MUST be committed and the parse asserted against it.
- **FR-016**: `--check` MUST exit 0 and say so when the environment variable
  `ERGANE_SKIP_GATE_PATH_CHECK` is set to `1`, because a rule with no escape is
  deleted whole rather than obeyed. That name and that value are the shape this
  tree already uses for a deliberate override (`scripts/hooks/pre-push:26`), and
  it is stated here rather than left to the implementer so that the operator
  sequence in plan.md is runnable by someone who has not read the diff. The
  escape is for the operator's own session; it is not the mechanism FR-021 uses,
  and cannot be, because no new name reaches a dispatched node.
- **FR-017**: The shipped payload MUST include a `settings.json` declaring a
  `PreToolUse` hook whose matcher covers `Write` and `Edit` and whose command
  invokes `ergane repo gate-paths --check`.
- **FR-018**: `ergane init` MUST report the derived gate-path set it found, with
  each path's gate; when that set is empty it MUST say that the installed hook
  will refuse nothing, and why.
- **FR-019**: An existing `<repo>/.claude/settings.json` whose bytes differ from
  the recorded digest, or for which no digest is recorded, MUST be left untouched
  under FR-005 and FR-007, and the report MUST say the hook was not installed
  there.
- **FR-022**: The command the shipped `settings.json` declares MUST map only
  FR-014's refusal status to exit 2 and every other exit status of the invoked
  `ergane`, 2 included, to exit 0; a committed test MUST assert both directions
  by executing the declared command string against a stub `ergane` on `PATH`. An
  `ergane` that is missing, older than the verb, or renamed must leave the write
  alone, which is the failure mode a bare `exit 2` cannot distinguish from a
  refusal.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-005, FR-006, FR-007, FR-008, FR-009, FR-010, FR-020]
US3:
  depends_on: []
  concurrent_with: [US1]
  implements: [FR-011, FR-012, FR-013]
US5:
  depends_on: []
  depends_on_merged: [US3]
  implements: [FR-014, FR-021, FR-015, FR-016]
US4:
  depends_on: []
  depends_on_merged: [US1, US2, US3, US5]
  implements: [FR-017, FR-018, FR-019, FR-022]
```

Every edge is `depends_on_merged` and every one is declared rather than left
inferred (069-US2 FR-007). US1 and US3 carry `concurrent_with` rather than an
edge, and that override is deliberate: their task slices both *cite*
`factory/stack_packs.py` and `tests/test_057_us2_stack_pack.py`, so an inferred
ordering falls out of the citations, but US1 only copies those two files'
patterns and edits neither. US1 adds a new module and a payload directory under
`factory/`; US3 edits `factory/stack_packs.py`, the three shipped pack files and
adds a derivation module plus one verb in `factory/cli/repo.py`. The two write no
file in common. US2 reads the resolver US1 adds and edits `factory/cli/init.py`,
which is why its edge is on merge rather than on pass — it needs US1's code in
the base, not US1's verdict. US5 is the second half of the same CLI file US3
touches and calls the derivation US3 writes, so its edge is on US3's merge for
both reasons at once; it is a separate node rather than four more tasks in US3
because US3 plus US5 in one diff is the only slice in this spec with no headroom
under D-050's 64 KiB refusal. US4 is last because it is the only story that needs
all four: it adds a file to US1's payload, report lines to US2's init path, the
set US3 derives, and it names US5's verb in the command it declares. Landing it
earlier would ship a hook declaration pointing at a verb that does not exist —
which is also FR-022's subject, since that is exactly the state of every host
whose installed `ergane` has not caught up, and it is why the translation lives
in the declared command rather than in the verb's own exit code.
