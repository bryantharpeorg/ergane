---
state: draft
depends_on_landed:
  - 130-the-boundary-detector-charges-an-attempt-only-for-what-it-wrote
fixes:
  - doctor/the-findings-store-has-no-repository-column-so-a-shared-runtime-root-collapses-two-repos-into-one-ledger
# DRAFTED 2026-09-04 by the refinement workflow (refinement-2026-09-04) from
# docs/triage-2026-09-03-ergane-web-round3.md § "the-findings-store-knows-which-
# repository-it-is-about" (lines 241-257), against ergane-buildout at 602a92c.
# Every `file:line` in spec.md and plan.md was read from that commit with `sed`
# and verified to resolve to the symbol named, not recalled.
#
# WHERE THIS CAME FROM. P-6 of the `ergane-web` consolidated hand-over
# (`ergane-findings-ergane-web-2026-09-03.md`), verified and re-scoped by the
# 2026-09-03 triage. One worker and one runtime root serving many target
# repositories is a topology this platform declares correct — the contrary
# diagnosis, `roadmap/target-repo-does-not-own-the-factory-root-so-every-node-
# strands`, was resolved WRONG DIAGNOSIS on 2026-08-24 after being falsified by
# execution. On that topology the platform's own defect channel is a report about
# neither repository, and the provenance it needs is already computed and thrown
# away.
#
# WHAT IT COST, MEASURED. Read live from `.factory/doctor.db` on 2026-09-04:
# `schema_version` = 1, 520 findings, 1032 events, and no column anywhere names a
# repository. `hardening/agent-worktree-boundary` reads `occurrences = 90`,
# spanning 2026-08-22 to 2026-09-03 across two target repositories — one row, 90
# events, and a `refs` array naming only the ninetieth observation (`epic:057-a-
# new-repo-gets-a-constitution`, `node:us4`). The evidence of the other
# eighty-nine is not merely un-queryable; it was overwritten, one report at a
# time, and `finding_events` never held it. Meanwhile the same collapse decides an
# exit code: a critical first recorded under repository A makes `ergane doctor`
# return 0 in repository B while overwriting A's evidence on the way.
#
# THE KEY IS DECLARED WHOLE, AND THE FR LIST IS WHY. The ledger row names three
# defects, not one — the missing column, the destroyed per-report provenance, and
# the cross-repository green. US1 carries the first, US2 the second, US3 the
# third. A spec that added the column alone would earn a triage closure and leave
# two thirds of the row running, which is this floor's most expensive recorded
# mistake (100, 092, 118). No key was removed and none was added.
#
# WHERE THE SOURCE ENTRY DISAGREED WITH THE TREE. Three of its seven traps cite
# lines that have moved or that name the wrong module. SCHEMA_VERSION is at
# `factory/doctor/store.py:20`, not :19, and its ON CONFLICT block is at
# `factory/doctor/store.py:160-171`, not 159-169. More seriously, its trap 4
# anchors `_report_if_new` and `_check_command` in `factory/doctor/cli.py` — and
# that module is the *second* face. The verb it names, `ergane doctor check`,
# does not exist: `ergane doctor` is a leaf command wired to `doctor_command` in
# `factory/cli/doctor.py`, which carries its own `_run_all_probes` and its own
# `_report_if_new`. A story that fixed the cited copy would land green and change
# nothing an operator runs. FR-015 and plan.md's trap 2 exist for that.
#
# TWO DEFECTS THE SOURCE ENTRY DID NOT NAME, FOUND BY READING. The detector's
# out-of-band batch file dedupes by key alone across a shared runtime root
# (`factory/workgraph/detector.py:621`), so the same collapse happens a second
# time in the record that exists precisely for when the store is gone — FR-011.
# And the migration cannot be keyed off SCHEMA_VERSION: `_bootstrap_schema`
# stamps the version only into a store that has none
# (`factory/doctor/store.py:127`), so an existing store reports 1 forever no
# matter what the constant says — FR-003.
#
# NOT IN SCOPE. Finding key identity does not change: the class key was a
# deliberate collapse (073 FR-024) and stays one row per key. Existing rows are
# not split retroactively beyond the stated migration, which stamps them "no
# repository stated" rather than guessing. There is no per-repository runtime
# root and no change to where the store lives (FR-006). `ergane repo forget
# --export` is not touched, and neither is the triage machinery.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04): the read path must survive a store
# nobody has opened read-write yet, or this spec breaks `ergane spec validate`
# itself — FR-016, US1-S5, trap 13; the migration fixture is pinned to a frozen
# literal so the story cannot prove itself against the DDL it is editing —
# US1-S2/S3, trap 12; `compare_and_report` builds two findings and only one was
# named — FR-010, US2-S6, trap 10; `ergane doctor` learns its repository from the
# working directory and gains no option for it — FR-017, US3-S3, trap 6; the
# `findings list` filter is derived from the trail, not from the row's own column
# — FR-012, FR-013; the truth table now says which exits take precedence; three
# anchors re-attributed (`factory/cli/repo_export.py`, `factory/usage/ledger.py`)
# and three written in symbol form. No FR was removed and no key changed.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), second pass, after adversarial
# review refuted the trio on two blocking defects. FR-011 now re-qualifies the
# batch grammar's entry-uniqueness rule on the (key, repository) pair instead of
# assuming there is none: `parse_findings_batch` refuses two entries under one
# key today (`factory/doctor/models.py:138`), a landed test and a committed
# fixture hold that rule, and US2-S4 would have met it as a wall — US2-S7 is the
# new control that stops the guard being deleted to get past it. US2-S3 and
# US2-S6 now assert the repository *field* read back through `get_finding`,
# because 130 lands first and its own US4-S3 already puts the repository into the
# finding's summary and refs, so a text assertion would pass on a zero-line
# detector diff. US2-S4's second half names the per-entry field it means. FR-002
# and FR-016 name `list_events`, the third read path, which no requirement
# reached. No FR was removed, no key changed, no hold text deleted, and the
# stories are the same three.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), third pass, after adversarial
# review refuted US3 as satisfiable by a zero-line production diff. The store the
# two runs resolve to was stated only to the operator (plan.md step 5) and never
# to the story: `factory/cli/doctor.py:65` — `_store_path` falls through to
# `factory/workgraph/worktree.py:191` — `resolve_factory_root`, whose default
# `factory/workgraph/worktree.py:93` is *relative*, so a test that merely changes
# directory hands repository B its own empty ledger and today's shipped code
# already returns the user exit code. US3-S3, US3-S4 and US3's Independent Test
# now carry the shared-store condition, T026/T027 must pin it and T032's pasted
# transcript must show the pin beside the exit codes; plan.md gains trap 15,
# which names `tests/test_runtime_root_findings.py:65` — `_chdir_tmp` as the
# idiomatic wrong move. Also corrected a count: US1 adds **three** dataclass
# fields, not two (T009, plan.md § Sizing). No FR was removed, no key changed, no
# hold text deleted, and the stories are the same three.
#
# THE OVERLAP WITH 130, AND THE ORDER IT FORCES. Draft spec
# `130-the-boundary-detector-charges-an-attempt-only-for-what-it-wrote` (drafted
# 2026-09-03, one day before this one) already owns the detector's repository:
# its FR-008 and US4-S3 thread the same value across the same seam
# (`factory/workgraph/detector.py:405` captures, `:598` drops). 130 puts it in the
# finding's summary and refs, because when 130 was written there was no column to
# put it on. That is not a contradiction, it is a sequence: 130 lands the
# threading, 143 lands the column and moves the value onto it. The
# `depends_on_landed` edge above is that decision made machine-enforceable — 143
# cannot dispatch until 130 has landed — and it is the operator's to revisit. If
# 130 is withdrawn, FR-010 becomes 143's whole job rather than its last step, and
# the edge must come out by hand.
---

# Feature Specification: the findings store knows which repository it is about

**Created**: 2026-09-04
**Depends on**: `130-the-boundary-detector-charges-an-attempt-only-for-what-it-wrote`, landed. 130 threads the target repository across the detector's seam; this spec creates the column that value belongs in and moves it there.

## The gap, stated precisely

The doctor's ledger has no repository dimension anywhere — not in the schema, not
in the write path, not in the read path, and not in the rule that decides an exit
code. On a runtime root serving one repository that is invisible. On a runtime
root serving two it makes every answer wrong, and the wrongness is silent.

The chain is five short steps:

1. **The schema has fourteen columns and none of them names a repository.**
   `factory/doctor/store.py:50-68` is the `findings` table; the recurrence trail
   at `factory/doctor/store.py:70-79` carries six columns — `id`, `finding_key`,
   `seen_at`, `source`, `severity` and `kind`. Read live from `.factory/doctor.db`
   on 2026-09-04 and identical to the published contract at
   `specs/015-factory-doctor/contracts/doctor-store.sql:23`.

2. **The store is per runtime root, not per repository.**
   `factory/doctor/cli.py:50` — `_store_path` resolves the file through
   `factory/workgraph/worktree.py:191` — `resolve_factory_root`, which returns
   `$ERGANE_ROOT` or the *relative* `factory/workgraph/worktree.py:93`
   (`DEFAULT_RUNTIME_ROOT = Path(".ergane")`). One pinned root — this floor pins
   it at `scripts/ergane-env.sh:84` — is one ledger for every repository the
   worker builds.

3. **Each report destroys the last one's evidence.** The upsert at
   `factory/doctor/store.py:165-171` sets `refs = excluded.refs`, `summary =
   excluded.summary`, `notes = excluded.notes` and `occurrences =
   findings.occurrences + 1`. The event appended beside it
   (`factory/doctor/store.py:204` — `report`) carries no refs and no repository.
   So provenance is not un-queryable; it is gone. Measured: one row at 90
   occurrences and 90 events whose `refs` name only the ninetieth.

4. **The information is already in hand and dropped on the floor.**
   `factory/workgraph/detector.py:405` — `_write_snapshot` writes
   `"target_repo": str(tracked.repo)` into the start snapshot, and
   `factory/workgraph/detector.py:584` — `compare_and_report` reads it back. The
   call one line before the finding is built, at
   `factory/workgraph/detector.py:598` — `compare_and_report`, hands
   `factory/workgraph/detector.py:440` — `_build_finding` everything except the
   repository, and the finding's only provenance is the two refs at
   `factory/workgraph/detector.py:467` — `_build_finding`. The *other* finding the
   same function files — the CRITICAL built inline at
   `factory/workgraph/detector.py:556-578` when the start snapshot is missing at
   teardown, persisted at `factory/workgraph/detector.py:579` — drops the
   repository too, and it is the finding filed for exactly the case a shared
   runtime root makes ambiguous.

5. **And the collapse decides an exit code.**
   `factory/cli/doctor.py:240` — `_report_if_new` calls it new when the *key* is
   absent, and `factory/cli/doctor.py:206-212` — `_run_all_probes` returns the
   user exit code only for newly inserted criticals. A critical condition first
   recorded under repository A therefore makes `ergane doctor` return 0 in
   repository B — while step 3 overwrites A's evidence with B's. `ergane doctor`
   also has no repository in scope to be per-repository about:
   `factory/cli/doctor.py:162` — `add_doctor_parser` registers `--db` and nothing
   else, and `factory/cli/doctor.py:177` — `doctor_command` calls
   `factory/cli/doctor.py:188` — `_run_all_probes` with a connection and no
   repository at all.

**The reading side has no way to ask the question either.**
`factory/cli/doctor.py:266-273` registers `--severity`, `--status`, `--json` and
`--db` and nothing else, and `factory/doctor/store.py:454` — `list_findings`
selects the whole table unfiltered. `ergane findings report`
(`factory/cli/doctor.py:276-288`) takes no target at all.

## The rule this spec is asking for

**A finding is about a repository: every observation records which one, the
recurrence trail keeps each observation's own evidence, and "have we seen this
before" is a question asked per repository — while the finding key stays one
class, one row.**

The exit code of `ergane doctor`, complete:

| key already in the store | observed in **this** repository before | critical | exit |
|---|---|---|---|
| no | no | yes | **1** — today's behaviour, unchanged |
| yes, repository A only | no | yes | **1** — today returns 0; this is the change |
| yes | yes | yes | **0** — unchanged; a recurrence is not news |
| yes, repository A only | no | no | **0** — unchanged; only criticals set the exit |

The table describes the newness rule and nothing else, and two earlier branches
take precedence over all four rows. `factory/cli/doctor.py:206-212` —
`_run_all_probes` returns `EXIT_TRANSPORT` (3) when any probed service did not
answer, and `EXIT_USER` when a probe raised something unexpected, both *before*
it looks at new criticals. So the table holds only on a run where every probe
answered — which is why the operator's step 4 in plan.md says so, and why a 3
read there is a service being down rather than a failed verification of this
spec.

### What this spec is not

It is not a change to finding identity. The key stays the class
(073 FR-024): one key, one row, one `occurrences` total. The repository is a
dimension of each *observation*, recovered from the event trail, never a second
key. A spec that split rows per repository would undo the collapse that makes
recurrence countable at all.

It is not a per-repository runtime root. The store stays exactly where
`resolve_factory_root` puts it (FR-006). The defect is a missing column, not a
missing directory, and moving the file would break `ergane repo forget --export`,
whose whole selection rule is store location.

It is not a retroactive re-attribution. Rows written before the column existed
read as "no repository stated" and stay that way; guessing which repository the
first eighty-nine observations were about is exactly the fabrication this spec
exists to stop.

It is not a change to `ergane repo forget --export`, to `ergane findings triage`,
or to any severity, status or resolution rule. It is also not a new option on
`ergane doctor`: that verb learns its repository from where it is run (FR-017),
because an operator who has to name the repository they are standing in will not,
and the defect survives.

## User Scenarios & Testing

### User Story 1 - The ledger has a repository column, and an existing store gains it without losing a row (Priority: P1)

As an operator whose one worker builds two repositories, the ledger can hold the
distinction — and my 520 existing rows survive learning it.

**Why this priority**: P1 and it depends on nothing. Nothing downstream can
record, filter or count a repository until a column exists to hold it. It is also
where the only irreversible risk lives: a migration that drops a row cannot be
undone by the next story — and a read path that assumes the migration has already
run takes the validate gate down with it.

**Independent Test**: Build a store from a frozen literal copy of the version-1
DDL pinned in the test module, populate it, open it with `connect`, and read the
schema and every prior row back; then open the un-migrated copy with
`connect_readonly` and read it.

**Acceptance Scenarios**:

1. **Given** a store created fresh by `connect`, **When** its schema is read,
   **Then** `findings` carries a nullable repository column and `finding_events`
   carries both a repository column and a column holding that observation's own
   refs, proven by a committed test asserting the column list of each table.
2. **Given** a database built from a frozen literal pre-143 copy of the version-1
   DDL, written out in the test module rather than read from
   `specs/015-factory-doctor/contracts/doctor-store.sql` — because this same story
   edits that file — and populated with findings and events, **When** `connect`
   opens it, **Then** every prior `findings` row survives with all fourteen of its
   previous column values unchanged and every prior `finding_events` row with all
   six of its own, the new columns exist, and the pre-existing rows read as no
   repository stated. Asserted by a committed test that reads one row of each
   table before and after and compares them, and whose pasted evidence shows
   `PRAGMA table_info` on the fixture *before* `connect`, listing fourteen
   columns.
3. **Given** that same frozen-literal store, already migrated, **When** `connect`
   opens it a second and third time, **Then** nothing changes, no row is
   duplicated and no column is added twice, because the migration is keyed off the
   schema the store actually has and not off the version it recorded. A committed
   test asserts the row count and column list are equal across all three opens.
4. **Given** the module's DDL constant and the published contract at
   `specs/015-factory-doctor/contracts/doctor-store.sql`, **When** the diff is
   read, **Then** both declare the new columns, so the two cannot be edited apart
   and the structure-for-structure test in `tests/test_doctor_store.py` holds. A
   diff that edits only the module fails this scenario.
5. **Given** that same frozen-literal store, **not** yet opened by `connect` and
   therefore still fourteen columns wide, **When** it is opened with
   `factory/doctor/store.py:98` — `connect_readonly` — the door `ergane spec
   validate` and `ergane findings triage` use, which sets `query_only = ON` and
   can never migrate — **Then** `get_finding`, `list_findings` and
   `factory/doctor/store.py:493` — `list_events` all return their rows with the
   repository reading as none, rather than raising `no such column`. A committed
   test drives all three functions on that connection; a diff that names a new
   column in any of the three SELECT lists and stops fails here.

### User Story 2 - Every report names the repository it is about, and the trail keeps its own evidence (Priority: P1)

As an operator reading a finding at its ninetieth occurrence, I can see which
repository each of the ninety observations was about, and what each one saw.

**Why this priority**: P1, and it is the half the source entry warned would be
skipped. A column with nothing written into it fixes nothing, and per-report
provenance is destroyed rather than merely unqueryable, so restoring it is work
the column does not do by itself.

**Independent Test**: Report one key twice from two different repositories with
different refs, then read the recurrence trail.

**Acceptance Scenarios**:

1. **Given** one finding key reported twice with different refs, the first naming
   repository A and the second repository B, **When** the recurrence trail is
   read, **Then** it holds two events, each naming its own repository and carrying
   its own refs, and the first event's refs are still the refs the first report
   supplied. A committed test asserts both events; today's trail holds neither
   column, so no diff that leaves `report` alone can pass this.
2. **Given** `ergane findings report` invoked with the repository named, **When**
   the row is read back, **Then** it names that repository; **and given** the same
   command with no repository named, **Then** the row records none, rather than
   the resolver's default being written in as a fact nobody stated. Both halves in
   one committed test.
3. **Given** an attempt whose boundary detector fires, driven through
   `factory/workgraph/detector.py:538` — `compare_and_report` with a real
   `target_repo` argument, **When** the filed row is read back through
   `factory/doctor/store.py:478` — `get_finding`, **Then** that row carries the
   target repository **on the repository column US1 added**, asserted as that
   field's value. An assertion on the finding's summary or on its refs does not
   satisfy this scenario and proves nothing here: the frontmatter's
   `depends_on_landed` edge makes 130 land first, and 130's own FR-008 and US4-S3
   already put the target repository into that summary and those refs — so a text
   assertion passes with a zero-line production diff in
   `factory/workgraph/detector.py`. A test that builds the `Finding` directly, or
   that passes a repository to `_build_finding` itself, fails for the other half
   of the same reason: the value must arrive through the detector's own seam,
   because a repository the detector never threads is a repository production
   never records.
4. **Given** the detector firing for two different target repositories against one
   runtime root, **When** the out-of-band batch at
   `factory/workgraph/detector.py:613` — `_persist_finding` is read, **Then** it
   holds two entries, one per repository, rather than the second having replaced
   the first — and that file, re-ingested through
   `factory/doctor/models.py:81` — `parse_findings_batch`, parses into two
   `Finding`s each carrying its own repository **as its own per-entry
   `repository` key**, asserted on the parsed `Finding`'s repository field rather
   than on its summary or its refs. A committed test asserts both entries survive
   and both parse. Today that file is refused outright, because both entries
   carry the one class key and the grammar rejects a repeated key — see
   scenario 7 — so no diff that leaves the grammar's uniqueness rule alone can
   pass this.
5. **Given** two spellings of one repository — its top level, and a subdirectory
   inside the same work tree — **When** a finding is reported against each,
   **Then** both observations record the identical repository string, because one
   resolver produced it. A committed test asserts the equality; without a single
   resolver a repository has as many identities as it has spellings, which is the
   defect this spec is about, one level down.
6. **Given** a teardown at which the start snapshot is missing — the second and
   inline finding `compare_and_report` files, built at
   `factory/workgraph/detector.py:556-578` and persisted at
   `factory/workgraph/detector.py:579` — **When** that CRITICAL is read back
   through `factory/doctor/store.py:478` — `get_finding`, **Then** it carries the
   target repository **on the repository column US1 added**, asserted as that
   field's value and not as text inside its summary or its refs, for US2-S3's
   reason: 130 lands the summary wording first. A committed test drives
   `compare_and_report` with no snapshot on disk; a diff that threads the
   repository only into `_build_finding` leaves production filing
   repository-less criticals on exactly the path a deleted runtime root takes, and
   fails this scenario while passing scenario 3.

7. **Given** a batch file holding two entries under one key that name the
   **same** repository — the committed fixture
   `tests/fixtures/doctor/batch-duplicate-key/findings.json` is one, its two
   entries naming no repository at all — **When** it is parsed, **Then**
   `factory/doctor/models.py:81` — `parse_findings_batch` still refuses the whole
   batch naming that key, so the landed guard at
   `tests/test_doctor_models.py:90` — `test_batch_duplicate_key_refuses_naming_key`
   holds with its fixture unedited. A committed test asserts the refusal for a
   same-repository pair beside scenario 4's acceptance of a cross-repository
   pair. Deleting the `duplicate_key` rejection is the cheap way to make scenario
   4 pass; it fails this one, and it would let a genuinely repeated entry inside
   one repository upsert twice and inflate the `occurrences` total 073 FR-024
   exists to keep honest.

### User Story 3 - Reading is per repository, and a repository's own first sighting is news (Priority: P2)

As an operator running `ergane doctor` in repository B, a critical condition
present in B does not read green because A saw it first.

**Why this priority**: P2 and it depends on US2 having written values worth
reading. It carries the sharpest half of the defect — the one that silently
converts a critical finding into a passing check — but it is inert until there is
a repository on the row.

**Independent Test**: Record one key under two repositories in **one** findings
store — a single pinned runtime root, or one explicit `--db`, for both runs — then
run the list verb with a repository filter and `doctor_command` with its working
directory set to each repository in turn, reading the exit codes.

**Acceptance Scenarios**:

1. **Given** one key observed in repository A and in repository B, **When**
   `ergane findings list` is run with the repository filter set to A, **Then**
   only A's observation is listed; **and when** it is run with no filter, **Then**
   the key is still listed exactly once, because the row was never split. A
   committed test asserts both listings. The filter is answered from
   `finding_events`, not from the row's own repository column, which names only
   the latest observation: a row filter would list nothing for A and pass a test
   written to expect that.
2. **Given** one key observed twice under repository A and once under repository
   B, **When** `ergane findings list --json` is read, **Then** each record carries
   per-repository counts reading 2 for A and 1 for B while the row's own
   `occurrences` still reads 3 — the counts are derived from the recurrence trail
   and the identity is untouched. A committed test asserts all three numbers
   together, reading them from that JSON output and not from the store function
   alone; asserting only the per-repository pair would pass a diff that split the
   row.
3. **Given** a critical probe finding already recorded under repository A, **and
   given** that both runs resolve to **one** findings store — a single pinned
   runtime root, or one explicit `--db` — with the working directory as the only
   thing that differs, **When** `ergane doctor` runs with its working directory
   inside repository B — the only repository input it has, resolved through
   FR-007's resolver, with no new option — and the same probe fires again,
   **Then** the command returns the user exit code, proven by a committed test
   that drives `factory/cli/doctor.py:177` — `doctor_command` with the working
   directory as the only thing that says which repository this is, and asserts its
   return value. A test in which each repository gets its own `.ergane` satisfies
   nothing here and is the way this whole story lands green on a zero-line
   production diff: `factory/cli/doctor.py:65` — `_store_path` falls through to
   `factory/workgraph/worktree.py:191` — `resolve_factory_root`, whose default
   `factory/workgraph/worktree.py:93` is a *relative* path, so a repository with
   its own empty ledger has always returned the user exit code. A test that passes
   the repository in as an argument or option, or that drives the same-named
   handler in `factory/doctor/cli.py`, fails this scenario for the other two
   reasons: the first changes the door the operator uses and the second is not
   what the `ergane doctor` verb runs.
4. **Given** that same key now already observed under repository B, **and given**
   the same single store scenario 3 pinned — the run reads back what the previous
   run wrote, because a second runtime root would make this a first sighting and
   not a repeat — **When** `ergane doctor` runs from inside B again, **Then** it
   returns zero — the rule gained a dimension rather than losing its silence. A
   committed test asserts this beside scenario 3 and shares scenario 3's pinned
   store, and only the pair can fail a diff that deleted the newness rule instead
   of qualifying it.

## Functional Requirements

- **FR-001**: The `findings` table MUST carry a nullable repository column naming
  the repository an observation is about, while the finding key remains the sole
  identity (073 FR-024) and no row is split by repository.
- **FR-002**: The `finding_events` table MUST carry that observation's own
  repository and its own refs, so a later report cannot destroy an earlier one's
  evidence, and `factory/doctor/store.py:493` — `list_events` MUST return both,
  so the trail is readable through the product rather than only through raw SQL
  against the table.
- **FR-003**: `connect` MUST bring an existing store up to the new shape in place,
  keyed off the schema the store actually has rather than off the recorded
  `SCHEMA_VERSION`, preserving every existing row and every existing column value;
  rows recorded before the column existed MUST read as no repository stated rather
  than being attributed to one.
- **FR-004**: `SCHEMA_VERSION` MUST be bumped and the published contract
  `specs/015-factory-doctor/contracts/doctor-store.sql` MUST be updated in the
  same diff, so the module DDL and the contract stay structure-for-structure
  identical and `tests/test_doctor_store.py:142` —
  `test_a_new_store_matches_the_published_contract_ddl` still holds.
- **FR-005**: A store in which no observation names a repository MUST behave
  exactly as it does today on every existing read and write path.
- **FR-006**: The store MUST NOT become per-repository. Neither
  `factory/workgraph/worktree.py:191` — `resolve_factory_root` nor
  `factory/doctor/cli.py:58` — `_resolve_store_path` may be edited to place a
  ledger per target repository; the repository is a column, not a path.
- **FR-007**: One resolver MUST turn a repository path into the single string
  every writer records — the git top level when the path lies inside a work tree,
  otherwise the resolved absolute path — so one repository has exactly one
  spelling in the ledger.
- **FR-008**: `report` MUST record the observation's repository on the row and
  MUST append it, together with that report's own refs, to the recurrence trail.
- **FR-009**: `ergane findings report` MUST accept the repository as an option; a
  report that names none MUST record none rather than substituting a default.
- **FR-010**: The boundary detector MUST file **every** finding it files against
  the target repository it already snapshotted — both the comparison finding
  threaded from `factory/workgraph/detector.py:538` — `compare_and_report` into
  `factory/workgraph/detector.py:440` — `_build_finding`, and the missing-snapshot
  CRITICAL built inline at `factory/workgraph/detector.py:556-578` — and not
  rediscovered from the environment.
- **FR-011**: The detector's out-of-band batch MUST keep one entry per key **and**
  repository rather than one per key, and the batch grammar
  (`factory/doctor/models.py:81` — `parse_findings_batch`) MUST carry a
  repository through as a **per-entry** field. Because every attempt in every
  repository files the one class key, that grammar's entry-uniqueness rule
  (`factory/doctor/models.py:138` — `parse_findings_batch`) MUST be re-qualified
  on the (key, repository) pair rather than removed: two entries sharing a key
  but naming different repositories MUST parse, and two entries sharing both MUST
  still be refused naming the key. So the record that survives a deleted runtime
  root is not collapsed the same way the store is, and a genuinely repeated entry
  inside one repository still cannot inflate `occurrences` (073 FR-024).
- **FR-012**: `ergane findings list` MUST accept a repository filter and show only
  observations of that repository, answered from the `finding_events` trail rather
  than from the row's own repository column, while an unfiltered listing still
  shows each key once.
- **FR-013**: Per-repository occurrence counts MUST be derived from the recurrence
  trail and carried on each record of `ergane findings list --json`, leaving the
  row's own `occurrences` total unchanged.
- **FR-014**: `ergane doctor`'s newness rule MUST be per key **and** repository: a
  critical finding whose first observation in this repository is this run MUST
  return the user exit code even when the key already exists from another
  repository.
- **FR-015**: FR-014 MUST NOT re-raise for a key already observed in this
  repository, and MUST be implemented in `factory/cli/doctor.py:188` —
  `_run_all_probes`, the module the `ergane doctor` verb actually runs, and not in
  the identically named handler at `factory/doctor/cli.py:214` — `_check_command`.
- **FR-016**: Every read path MUST serve a store that predates the column on a
  connection that cannot migrate it. `factory/doctor/store.py:98` —
  `connect_readonly` sets `query_only = ON`, so the migration can only ever run
  from `factory/doctor/store.py:86` — `connect`; `factory/doctor/store.py:454` —
  `list_findings`, `factory/doctor/store.py:478` — `get_finding` and
  `factory/doctor/store.py:493` — `list_events` MUST therefore read what the
  store actually has — the column list from `PRAGMA table_info`, or the known
  columns with the new ones filled from a guarded read — rather than naming a new
  column unconditionally in their SELECT lists.
- **FR-017**: `ergane doctor` MUST derive the repository it is reporting about
  from the process's working directory through FR-007's resolver, record it on
  every finding it files, and gain **no** new option for it; `--db` is unchanged.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-016]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-007, FR-008, FR-009, FR-010, FR-011]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-012, FR-013, FR-014, FR-015, FR-017]
```

Two `depends_on_merged` edges and no pass-edges, declared rather than left
inferred (069-US2 FR-007). US2 writes values into columns only US1 creates, and
US3 reads values only US2 writes, so each edge buys correctness of sequencing
before it buys anything else. Both edges are also the contention answer: all three
stories edit `factory/doctor/store.py`, and US2 and US3 both edit
`factory/cli/doctor.py`, so raced siblings would collide in the merge queue and
the later arrival would be rejected for a change it did not make. The chain is
deliberately linear rather than a fan-out from US1, because US3's newness rule is
only testable against a trail that already carries repositories. FR-016 sits in
US1 rather than in a story of its own because it is a property of the same diff
that adds the column: the moment `_SCHEMA_DDL` grows a column, every read-only
consumer of an un-migrated store is on the line. The one contention edge the graph
cannot express is with another spec: 130 edits `factory/workgraph/detector.py` in
three of its four stories, which is why the frontmatter carries a
`depends_on_landed` edge to it rather than a `concurrent_with` note here.
