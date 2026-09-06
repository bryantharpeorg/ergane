# Implementation Plan: the findings store knows which repository it is about

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## What already exists, and where

**The schema, and the one thing it does not say.** `factory/doctor/store.py:50-68`
is the `findings` table — fourteen columns, `key` the primary key — and
`factory/doctor/store.py:70-79` is the recurrence trail, six columns:

```sql
CREATE TABLE IF NOT EXISTS finding_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_key TEXT NOT NULL REFERENCES findings(key),
    seen_at     TEXT NOT NULL,                -- ISO-8601 UTC
    source      TEXT NOT NULL,
    severity    TEXT NOT NULL
        CHECK (severity IN ('critical', 'warning', 'info')),
    kind        TEXT NOT NULL
        CHECK (kind IN ('reported', 'promoted', 'resolved', 'regressed'))
);
```

Neither table names a repository, and the trail carries no refs — so the
recurrence count survives and the evidence behind it does not. Fourteen and six
are the two numbers a migration test must assert; they are not the same number.
The module DDL is declared verbatim from
`specs/015-factory-doctor/contracts/doctor-store.sql:23`, and `SCHEMA_VERSION` is
`1` at `factory/doctor/store.py:20`.

**The upsert that overwrites.** `factory/doctor/store.py:137` — `report` opens the
transaction; the conflict clause at `factory/doctor/store.py:165-171` is the
mechanism:

```sql
            ON CONFLICT (key) DO UPDATE SET
                status = CASE
                    WHEN findings.status = 'resolved' THEN 'regressed'
                    ELSE findings.status
                END,
                severity = excluded.severity,
                summary = excluded.summary,
                refs = excluded.refs,
                notes = excluded.notes,
                source = excluded.source,
                occurrences = findings.occurrences + 1,
                last_seen = excluded.last_seen
```

The event appended after it, at `factory/doctor/store.py:204` — `report`, chooses
only a `kind`. Measured on the live store 2026-09-04:
`hardening/agent-worktree-boundary` holds `occurrences = 90` and 90 events, and
its `refs` array names one epic — the ninetieth.

**The migration precedent is already written, in the sibling store, and its
comment is the design.** `factory/usage/ledger.py:142` — `_bootstrap_schema` runs
the DDL and then calls `_migrate` one line later, at
`factory/usage/ledger.py:150` — `_bootstrap_schema`;
`factory/usage/ledger.py:237` — `_migrate` is the one-line dispatcher and
`factory/usage/ledger.py:188` — `_widen_terminations` is the worked example. The
sentence that matters is not attached to that function: it is the four-line `#:`
doc-comment at `factory/usage/ledger.py:167-170`, twenty lines above it, written
for the constant `_TERMINATION_CHECK` at `factory/usage/ledger.py:171`:

```python
#: Keyed off the recorded constraint rather than off `SCHEMA_VERSION`, for
#: `factory/verify/store.py`'s reason: a version is a claim and the schema is the
#: fact. The value list is read out of `_SCHEMA_DDL` rather than restated here,
#: so the migration cannot drift from the DDL it migrates towards.
```

Copy that discipline exactly. The doctor's case is easier than the ledger's — a
new nullable column is a plain `ALTER TABLE ... ADD COLUMN`, not a table rebuild,
because nothing here widens a `CHECK` — but the keying rule is identical and
trap 1 is why.

**The precedent for testing that migration is also already written.**
`tests/test_escalation_record.py:156` (`_PRE_041_ESCALATIONS_DDL`) is a frozen
literal of the pre-041 escalations schema, with a comment saying exactly why it is
written out rather than read from anywhere: "so the migration is tested against a
shape, not against whatever the file says today". It is driven by
`tests/test_escalation_record.py:187` —
`test_a_store_written_before_this_story_migrates_in_place`, whose docstring names
the failure this spec must not repeat: "the first thing the factory does with one
is `SELECT` the escalation columns by name. A migration that only ran on a fresh
database would leave the running deployment answering `no such column`". That is
traps 12 and 13, already suffered once, in another store.

**The doctor store's own bootstrap, and the trap inside it.**
`factory/doctor/store.py:123` — `_bootstrap_schema` is four statements, and the
third is the hazard: `factory/doctor/store.py:127` — `_bootstrap_schema` reads
`if recorded == 0:`, so
the version row is written only into a store that has none. The live store reports
`schema_version = 1` with 520 findings and 1032 events, and will keep reporting 1
after `SCHEMA_VERSION` is bumped.

**The two doors into the store, and only one of them can migrate.**
`factory/doctor/store.py:86` — `connect` creates the file, applies the DDL and
calls `_bootstrap_schema`. `factory/doctor/store.py:98` — `connect_readonly`
opens a `mode=ro` URI and sets `PRAGMA query_only = ON`, and its docstring says
why: `ergane findings triage` without `--apply` "has to be able to state the
guarantee (073 FR-013)". A migration therefore cannot run there, ever. Two
consumers reach the store through that door, and both are gates this floor stands
on: `factory/cli/nouns/spec.py:1231` — `_check_fixes`, the `fixes` layer of
`ergane spec validate`, which opens at
`factory/cli/nouns/spec.py:1271` — `_check_fixes` and calls `get_finding` at
`factory/cli/nouns/spec.py:1282` — `_check_fixes` inside a `try/finally` with **no
`except`**; and `factory/cli/doctor.py:394` — `findings_triage_command`, which
chooses its opener at `factory/cli/doctor.py:417` — `findings_triage_command` and
calls `list_findings` at
`factory/cli/doctor.py:426` — `findings_triage_command`. Trap 13.

**The reading side.** `factory/doctor/store.py:454` — `list_findings` selects the
whole table at `factory/doctor/store.py:461-474` and orders it;
`factory/doctor/store.py:478` — `get_finding` names the same fourteen columns
explicitly. There is a **third** explicit SELECT list, and no requirement reached
it before this repair: `factory/doctor/store.py:493` — `list_events` names the
trail's six columns at `factory/doctor/store.py:497` — `list_events`. It is
reached from nothing in `factory/` — only `tests/test_findings_triage_applies.py`
calls it — which is why it is easy to leave behind and why FR-002 and FR-016 now
name it: US2-S1 reads the trail, and a trail that can only be read with raw SQL
is not a product surface. Note that `factory/cli/repo_export.py:72-75`
(`_EVENTS_SQL`) does not go through it. The only filtering in the product is in
Python, at
`factory/cli/doctor.py:368` — `findings_list_command` and
`factory/cli/doctor.py:372-376`, and those two filters are row-attribute filters —
severity and status are properties of the row, which is a *latest-observation*
summary. The parser that registers what may be filtered on is
`factory/cli/doctor.py:266-273`, and `ergane findings report`'s options are
`factory/cli/doctor.py:276-288`, ending at the `Finding` construction at
`factory/cli/doctor.py:487` — `findings_report_command` and the write at
`factory/cli/doctor.py:503` — `findings_report_command`. The `--json` record FR-013
must carry counts on is emitted at
`factory/cli/doctor.py:379` — `findings_list_command`, and it is
`print(json.dumps([asdict(f) for f in findings], indent=2))` — `asdict` over the
frozen `Finding` and nothing else. So a derived per-repository count cannot ride
on the dataclass without becoming a second store column, which FR-001 forbids:
the counts have to be assembled into the emitted record at that line, from the
grouped query beside `list_findings`, leaving `Finding` itself alone. T029 says
where.

**The detector already holds the repository and drops it — twice.**
`factory/workgraph/detector.py:391` — `_write_snapshot` writes it at
`factory/workgraph/detector.py:405`; `factory/workgraph/detector.py:538` —
`compare_and_report` takes `target_repo` as its second parameter and reads the
snapshot's copy back at `factory/workgraph/detector.py:584`. Then
`factory/workgraph/detector.py:598` — `compare_and_report` calls
`factory/workgraph/detector.py:440` — `_build_finding` with four arguments, none
of them the repository, and the finding returned at
`factory/workgraph/detector.py:503-518` carries as provenance only the two refs
built at `factory/workgraph/detector.py:467` — `_build_finding`. **That is not the
only `Finding` this function files.** The branch at
`factory/workgraph/detector.py:554` — `compare_and_report`
(`if not snapshot_path.exists():`) constructs a CRITICAL inline at
`factory/workgraph/detector.py:556-578` — "detector start snapshot missing at
teardown" — and persists it at
`factory/workgraph/detector.py:579` — `compare_and_report`, with `target_repo` in
scope and unused, then returns. The key itself is the class constant at
`factory/workgraph/detector.py:58` and does not change (073 FR-024). The two
callers already pass the repository: `factory/workgraph/adapter.py:1177` —
`run_attempt` and `factory/workgraph/adapter.py:1185` — `run_attempt`.

**The out-of-band batch, and its own collapse.**
`factory/workgraph/detector.py:607` — `_persist_finding` writes
`factory/workgraph/detector.py:613` (`snapshot_dir / "findings.json"`) into the
directory `factory/workgraph/detector.py:381` — `_snapshot_dir` returns, which is
derived from the *runtime root* at `factory/workgraph/detector.py:388` — one
directory for every repository the root serves. Its dedupe is
`factory/workgraph/detector.py:621` — `_persist_finding`:

```python
    existing = [entry for entry in batch["findings"] if entry.get("key") != finding.key]
```

One entry per key, so the second repository's entry replaces the first's — the
same defect as the store's, in the file that exists for when the store is gone.
It then writes the store too at `factory/workgraph/detector.py:638` —
`_persist_finding`.

**The batch grammar it is re-ingested through.**
`factory/doctor/models.py:81` — `parse_findings_batch` refuses a per-entry
`source` and a per-entry `status` because "the file is one provenance", and
constructs each `Finding` at `factory/doctor/models.py:145-163` —
`parse_findings_batch` from an explicit field list. An unknown entry key is not
refused; it is silently dropped there. `factory/doctor/models.py:30` — `Finding`
is the frozen carrier every writer builds. Note what that one-provenance rule is
about: `source`, the reporter. It is not about location, and one batch file is one
*runtime root*, which is precisely the thing that serves many repositories — so
the repository is a per-entry field and there is nothing to deliberate.

**The two faces of the doctor CLI.** `factory/doctor/cli.py:50` — `_store_path`
and `factory/doctor/cli.py:58` — `_resolve_store_path` still resolve the file, and
`factory/cli/doctor.py:65` — `_store_path` delegates to them at
`factory/cli/doctor.py:70` — `_store_path`. But the *verb* is registered in the
newer module:
`ergane doctor` is a leaf command (`ergane doctor --help` shows only `--db`) wired
to `factory/cli/doctor.py:177` — `doctor_command`, which calls
`factory/cli/doctor.py:188` — `_run_all_probes`, which uses
`factory/cli/doctor.py:240` — `_report_if_new` and returns at
`factory/cli/doctor.py:206-212`. The identically named
`factory/doctor/cli.py:214` — `_check_command` and
`factory/doctor/cli.py:257` — `_report_if_new` have no caller anywhere in
`factory/` or in `tests/`: `_check_command` is named only by its own module
docstring at `factory/doctor/cli.py:4`, and `_report_if_new` is called only from
inside `_check_command`, at `factory/doctor/cli.py:231` — `_check_command`. The
two test modules that touch that file touch nothing else in it —
`tests/test_ergane_findings.py:107` — `_freeze_doctor_utcnow` imports it to
monkeypatch `_utcnow`, and
`tests/test_ergane_spec.py:951` —
`test_sentinel_gate_lives_at_the_verb_not_the_deriver` reads a *different* module
(`factory/cli/doctor.py`) as text. They are dead code. This spec neither fixes
nor deletes them (FR-015), and no test will go red if you leave them alone —
which is the temptation trap 2 is about, inverted.

**What `ergane doctor` knows about where it is: nothing.**
`factory/cli/doctor.py:162` — `add_doctor_parser` registers one option, `--db`,
and `factory/cli/doctor.py:177` — `doctor_command` passes a connection and
nothing else to `_run_all_probes`. There is no repository in scope anywhere on
that path today, which is why FR-017 has to say where one comes from. The
repository is the working directory, resolved the way
`factory/cli/init.py:295` — `resolve_repo_root` already resolves one, with
`rev-parse --show-toplevel`.

**The harness that already drives the verb, and the two dimensions it lacks.**
`tests/test_ergane_ports.py:80` — `_patch_probe` replaces
`factory.doctor.probes.REGISTRY` with a single synthetic probe, and
`tests/test_ergane_ports.py:108` —
`test_doctor_non_service_probe_exception_is_one_line_naming_debug` and
`tests/test_ergane_ports.py:127` — `test_doctor_unreachable_service_exits_three`
drive `invoke("doctor")` end to end, asserting exit codes 1 and 3 through the
real verb. That is the fixture US3-S3 and US3-S4 need. What it does not have is a
probe whose `evaluate` returns a critical `FindingReport`, and a working
directory that says which repository the run is about. Extend it; do not write a
second one.

**Where the repository is resolved from today, and why it is not per-repo.**
`factory/workgraph/worktree.py:191` — `resolve_factory_root` returns the
`ERGANE_ROOT`/`FACTORY_ROOT` override or the relative `.ergane`
(`factory/workgraph/worktree.py:93`), and this floor pins the override at
`scripts/ergane-env.sh:84`. That pin is what makes one ledger serve two
repositories, and FR-006 says it stays.

**A neighbour that will read the new column for free, and one that will not.**
`factory/cli/repo_export.py:167` — `_read` exports with `SELECT *`, so the new
`findings` column ships in `findings.jsonl` with no edit; the events query at
`factory/cli/repo_export.py:72-75` names its four columns explicitly, so the new
event columns will *not*. Neither is this spec's business (see trap 8). The export
opens every store through `factory/verify/store.py`'s own read-only door at
`factory/cli/repo_export.py:104` — `open_store`, but `SELECT *` is why it
survives an un-migrated
store where trap 13's two consumers do not.

## Traps

**Trap 1 — The migration must be keyed off the schema, not off the version, and a
version-keyed migration silently never runs.** FR-003.
`factory/doctor/store.py:127` — `_bootstrap_schema` reads `if recorded == 0:` —
the version row is stamped
only into a store that has none, so the live store reports `schema_version = 1`
today and will still report 1 after `SCHEMA_VERSION` is raised to 2. An
implementer who writes `if recorded_version < SCHEMA_VERSION: alter...` gets a
migration that never fires on any existing store and a test suite that is entirely
green, because every test store is created fresh by `connect` and therefore
already has the new DDL. Ask `PRAGMA table_info(findings)` whether the column is
there, the way `factory/usage/ledger.py:188` — `_widen_terminations` reads the
recorded DDL rather than the recorded version, and say so in a comment. US1-S3
exists to catch the other half: an `ALTER TABLE` run unconditionally raises
`duplicate column name` on the second connect, and `connect` is called on every
report.

**Trap 2 — `ergane doctor` is NOT `factory/doctor/cli.py`, and the source entry
points at the wrong module.** FR-015. The triage entry this spec came from cites
`factory/doctor/cli.py:257` — `_report_if_new` and
`factory/doctor/cli.py:214` — `_check_command`. Those are real functions and they
are not what runs. The verb resolves to `factory/cli/doctor.py:177` —
`doctor_command`, whose own `factory/cli/doctor.py:240` — `_report_if_new` is the
newness rule and whose exit arithmetic is `factory/cli/doctor.py:206-212`. A story
that fixes the cited copy passes every test it writes, passes the judge, and
leaves the defect running in the command an operator types. If both copies are
changed, change them for the same reason and say which one the test drives;
US3-S3 requires the test to drive `doctor_command`.

**Trap 3 — The new columns must be nullable, and there is a landed test that
proves why.** FR-001, FR-003. `tests/test_ergane_repo_forget.py:391` —
`test_export_carries_only_the_departing_repos_rows` is fed by helpers that insert
into `findings` with an explicit column list naming neither new column — eleven
columns at `tests/test_ergane_repo_forget.py:123` — `seed_stores`, ten at
`tests/test_ergane_repo_forget.py:176` — `add_findings`. (Fourteen is the
`findings` table's own width, which US1-S2 and T002 assert; the inserts are
narrower, and that is exactly why they break.) A `NOT NULL` column
without a default breaks every such insert across the suite, and — worse — an
`ALTER TABLE ADD COLUMN ... NOT NULL` without a default is refused outright by
SQLite on a populated table. Nullable is also the honest reading: FR-003 says a
row written before the column existed states no repository, and a `DEFAULT ''`
would turn "we do not know" into a repository named the empty string that
`findings list` would then filter on.

**Trap 4 — The contract file is outside `factory/` and the suite will not let you
skip it.** FR-004. `factory/doctor/store.py:25-26` declares `_SCHEMA_DDL` a
verbatim copy of `specs/015-factory-doctor/contracts/doctor-store.sql`, and three
tests hold it: `tests/test_doctor_store.py:142` —
`test_a_new_store_matches_the_published_contract_ddl` compares whole schemas,
`tests/test_doctor_store.py:148` —
`test_the_findings_columns_match_the_contract` and
`tests/test_doctor_store.py:156` —
`test_the_finding_events_columns_match_the_contract` compare column lists against
constants in the test file. Editing the module DDL alone turns all three red, and
the tempting repair — loosening the assertions, or deleting the contract
comparison — destroys the one guarantee that keeps a published contract honest.
Edit `specs/015-factory-doctor/contracts/doctor-store.sql`, the module constant
and the two expectation lists together, in one diff.

**Trap 5 — One repository must have one spelling, and nothing in the tree gives
you one today.** FR-007. The detector will hand you `str(tracked.repo)`, an
operator will type a relative path, and `ergane doctor` will resolve one off the
cwd (FR-017); if each writer normalises for itself, `/home/admin/code/ergane`,
`/home/admin/code/ergane/` and `/home/admin/code/ergane/factory` become three
repositories and every count this spec adds is wrong. Write one resolver, put it
where every writer already imports from (`factory/doctor/models.py:30` —
`Finding`'s module is imported by the CLI and by
`factory/workgraph/detector.py:440` — `_build_finding`'s module alike), and route
all three writers through it. Say in a comment that this is why a
dataclass-and-grammar module now shells out to git: the alternative is a second
spelling rule, and the whole defect one level down is a repository having as many
identities as it has spellings. The call to copy is the
`rev-parse --show-toplevel` at
`factory/cli/init.py:295` — `resolve_repo_root`, not the detector's own
git helpers, which answer a different question. US2-S5 is the test that proves the
resolver exists.

**Trap 6 — Do not default the repository into a report that did not name one, and
do not give `ergane doctor` a flag either.** FR-009, FR-017. It is tempting to
make `ergane findings report` fall back to the resolver so no row is ever blank.
That writes an unstated fact into the ledger, and this spec's whole argument is
that a report about neither repository is worse than a report that says so.
`ergane doctor` is the opposite case and must resolve a repository deliberately —
from its **working directory**, through FR-007's resolver, with no new option.
Adding `--repository` to `ergane doctor` is the second way this story lands green
and changes nothing: the test passes it explicitly, the judge sees a per-repository
newness rule, and a bare `ergane doctor` typed in repository B still returns 0 for
a critical first recorded in A — the exact defect US3 exists for, and the exact
thing the operator's step 4 does. The two verbs are different verbs with different
knowledge and the difference is the point.

**Trap 7 — Do not split the row.** FR-001, FR-013. Once the trail carries a
repository, the natural next thought is one row per key per repository. That
reverses 073 FR-024 — the deliberate collapse the finding key exists to be — and
it breaks recurrence counting, which is what makes promotion into the constitution
a fact rather than a recollection. `occurrences` on the row stays the total across
repositories; the per-repository number is a `GROUP BY` over `finding_events`.
US3-S2 asserts all three numbers together for exactly this reason: asserting only
the per-repository pair would pass a diff that split the row. The same reasoning
decides the filter of FR-012: the row's repository column names the *latest*
observation only, so a filter applied to it — the shape
`factory/cli/doctor.py:372-376` sets for severity and status — answers a different
question and returns nothing for the repository that reported first.

**Trap 8 — Two neighbours will react to the schema change and neither is yours to
fix.** `factory/cli/repo_export.py:167` — `_read` uses `SELECT *`, so the new
`findings` column starts appearing in `findings.jsonl` the moment US1 lands — that
is fine and needs no edit. The events query at
`factory/cli/repo_export.py:72-75` names four columns and will keep exporting
four. And two pieces of prose become false: the module docstring at
`factory/cli/repo_export.py:7-8` ("No store here has a repo column") and the
docstring of `tests/test_ergane_repo_forget.py:391` —
`test_export_carries_only_the_departing_repos_rows`. Correct the two sentences
where they are now wrong; do **not** change what the export selects, which is by
store location and out of scope.

**Trap 9 — The out-of-band batch collapses the same way, and fixing only the
database leaves it.** FR-011. `factory/workgraph/detector.py:621` —
`_persist_finding` drops any existing entry with the same key before appending,
and the file it writes lives in one directory per runtime root
(`factory/workgraph/detector.py:388` — `_snapshot_dir`), not one per repository.
So on the topology this spec is about, the surviving record loses the first
repository exactly as the store does. Key the dedupe on the pair, and carry the
repository through `factory/doctor/models.py:81` — `parse_findings_batch` as a
per-entry field when the batch is re-ingested.

**The parser will not merely fail to help you — it refuses the file you are about
to start writing.** `factory/doctor/models.py:138` — `parse_findings_batch` is
`if raw_key in seen_keys:`, `factory/doctor/models.py:139` —
`parse_findings_batch` adds a `duplicate_key` rejection, and
`factory/doctor/models.py:142` — `parse_findings_batch` raises the accumulated
rejections as a `ValueError`, surfaced to the operator by
`factory/cli/doctor.py:456` — `findings_report_command` as `batch refused:`. And
`factory/workgraph/detector.py:419` — `_finding_key` returns the class constant
`factory/workgraph/detector.py:58` for every attempt in every repository, so the
two entries US2-S4 requires carry an *identical* key: today's grammar rejects the
pair outright. The rule is landed and held by a test and a fixture —
`tests/test_doctor_models.py:90` — `test_batch_duplicate_key_refuses_naming_key`
and `tests/fixtures/doctor/batch-duplicate-key/findings.json`.

Write T015 first, as the tests-first order requires, and it will die with
`[duplicate_key]` before it ever reaches the dedupe you came to change. The wrong
move at that moment is deleting the rejection: a genuinely repeated entry inside
one repository then upserts twice and inflates the `occurrences` count 073 FR-024
exists to keep honest, and nothing in the suite would say so. Re-qualify the rule
on the (key, repository) pair instead (FR-011). Both entries of the committed
fixture name no repository, so that pair stays equal and the landed test keeps
passing **with the fixture unedited** — it is your control, and US2-S7 is that
same assertion written into this spec. Add a *new* fixture for the case that must
now parse: two entries, one key, two repositories. The last hazard is the quiet
one: an entry key the constructor does not name is silently dropped at
`factory/doctor/models.py:145-163` — `parse_findings_batch`, so a repository
added to the JSON and not to that field list looks like it works and is not
there.

**Trap 10 — The detector's seam is `compare_and_report`, not `_build_finding`, and
`compare_and_report` files two findings.** FR-010.
`factory/workgraph/detector.py:440` — `_build_finding` is a private helper with no
repository in scope; an implementer can give it a parameter, write every test by
calling it directly, and never touch `factory/workgraph/detector.py:598` —
`compare_and_report`, where the argument must actually be passed. The result is a
green story and a production path that still files findings about no repository.
US2-S3 forbids that shape: the test must drive
`factory/workgraph/detector.py:538` — `compare_and_report`, which the two callers
at `factory/workgraph/adapter.py:1177` — `run_attempt` and
`factory/workgraph/adapter.py:1185` — `run_attempt` already supply a `target_repo`
to. The second half of this trap is the one that reads like a whole fix and is
not: the branch at `factory/workgraph/detector.py:554` — `compare_and_report`
builds its own CRITICAL inline at `factory/workgraph/detector.py:556-578` and
persists it at `factory/workgraph/detector.py:579` — `compare_and_report` without
going near `_build_finding` at all.
A diff that threads the repository through `_build_finding` alone passes US2-S3
and leaves production filing repository-less criticals on the missing-snapshot
path — the path that exists for the deleted-runtime-root case this topology makes
ambiguous. That is the 100/092/118 half-fix shape, inside one function. US2-S6 is
the control.

**Trap 11 — Do not move the store.** FR-006. The shortest-looking fix to "two
repositories share one ledger" is one ledger each, and it is wrong twice over:
`ergane repo forget --export` selects a repository's rows *by store location* —
its module docstring says so at `factory/cli/repo_export.py:7-14` ("What *is*
repo-scoped is the file ... So selection is by store location"), and the read-only
opener it routes every store through is
`factory/cli/repo_export.py:104` — `open_store` — so a
shared root is the case the export already cannot handle and a per-repo root would
only hide; and the whole topology — one worker, one runtime root, many targets —
was settled in the ledger when
`roadmap/target-repo-does-not-own-the-factory-root-so-every-node-strands` was
resolved WRONG DIAGNOSIS on 2026-08-24 after a spec dispatched under exactly that
configuration landed cleanly. If you find yourself editing
`factory/workgraph/worktree.py:191` — `resolve_factory_root` or
`factory/doctor/cli.py:58` — `_resolve_store_path`, stop: the design is wrong.

**Trap 12 — Build the migration fixture from a frozen literal, never from the
contract file this story edits.** FR-003, FR-016. `tests/test_doctor_store.py:33`
holds `CONTRACT_DDL` as a path to
`specs/015-factory-doctor/contracts/doctor-store.sql` and
`tests/test_doctor_store.py:130` — `contract_db` builds a database from it. That
is the obvious fixture for "a version-1 store", and it is a trap: T007 rewrites
that very file in this same story, so a fixture read from it is a *post*-migration
store. Every assertion then passes for free — the prior rows survive trivially,
the new columns exist trivially, the three-opens comparison is trivially equal —
and a `_migrate` keyed off `SCHEMA_VERSION` (trap 1's named wrong move, guaranteed
dead by `factory/doctor/store.py:127` — `_bootstrap_schema`), or no migration at
all, is green. The
shape to copy is `tests/test_escalation_record.py:156`
(`_PRE_041_ESCALATIONS_DDL`): the old schema written out as a literal in the test
module, with the comment saying why, driven by
`tests/test_escalation_record.py:187` —
`test_a_store_written_before_this_story_migrates_in_place`. The falsifier to paste
is `PRAGMA table_info(findings)` on the fixture **before** `connect` touches it: if
it does not read fourteen columns, the fixture is not testing a migration.

**Trap 13 — The read path must serve a store nobody has opened read-write yet, and
the consumer that breaks is the validate gate.** FR-016.
`factory/doctor/store.py:98` — `connect_readonly` sets `PRAGMA query_only = ON`, so
the migration can only ever run from `factory/doctor/store.py:86` — `connect`. Add
the new column to the explicit SELECT lists in `factory/doctor/store.py:454` —
`list_findings` and `factory/doctor/store.py:478` — `get_finding` and stop, and
every read-only consumer of a store that has not yet been opened read-write raises
`sqlite3.OperationalError: no such column`. Two consumers, both gates:
`factory/cli/nouns/spec.py:1231` — `_check_fixes` opens at
`factory/cli/nouns/spec.py:1271` — `_check_fixes` and calls `get_finding` at
`factory/cli/nouns/spec.py:1282` — `_check_fixes` in a `try/finally` with no
`except`, so
`ergane spec validate` does not skip the fixes layer — it crashes, and that is the
command every spec in this corpus is gated by; and
`factory/cli/doctor.py:394` — `findings_triage_command` chooses
`connect_readonly` at `factory/cli/doctor.py:417` — `findings_triage_command`
without `--apply` and calls `list_findings` at
`factory/cli/doctor.py:426` — `findings_triage_command`. Nothing in the suite goes
red,
for trap 1's reason — every test store is created fresh by `connect` — and triage
is out of scope, so the implementer is told not to look. Read the columns the
store actually has (`PRAGMA table_info`), or select the known columns and fill
the new ones from a guarded read. The same applies to the third SELECT list,
`factory/doctor/store.py:493` — `list_events`, which FR-002 and FR-016 name and
which nothing in `factory/` calls today. US1-S5 is the reproduction.

**Trap 14 — Spec 130 already owns the detector's repository; this story is the
second half of that work, not the first.** FR-010. Draft spec
`specs/130-the-boundary-detector-charges-an-attempt-only-for-what-it-wrote` (drafted
2026-09-03) declares in its FR-008 that "a filed finding MUST name the target
repository it is about, reusing the value already captured in the start snapshot",
and its US4-S3 names the same two lines this plan does —
`factory/workgraph/detector.py:405` captures,
`factory/workgraph/detector.py:598` drops. 130 puts the value in the finding's
summary and refs because when it was written there was no column. Three of 130's
four stories edit `factory/workgraph/detector.py`. The frontmatter's
`depends_on_landed` edge is the operator's decision recorded: 130 lands the
threading first, and US2 here moves the value onto the new field and extends it to
the missing-snapshot branch 130 does not name. Before you write a line in
`factory/workgraph/detector.py`, read what 130 landed: if the `target_repo` is
already flowing into `_build_finding`, your job is the field and US2-S6, not the
seam. If 130 was withdrawn instead, the seam is yours and the edge in the
frontmatter is stale — say so in the PR rather than assuming. Either way, the
assertion US2-S3 and US2-S6 require is on the repository **column** read back
through `factory/doctor/store.py:478` — `get_finding`, never on the finding's
summary or refs: 130's US4-S3 already puts the repository into that prose, so a
text assertion is satisfied by 130's diff and says nothing about yours.

**Trap 15 — Two working directories are not two repositories unless they share one
store, and the whole of US3 passes green on unmodified code if they do not.**
FR-014, FR-017, US3-S3, US3-S4. `factory/cli/doctor.py:65` — `_store_path` returns
`--db` when it is given one and otherwise resolves through
`factory/workgraph/worktree.py:191` — `resolve_factory_root`, whose fallback
`factory/workgraph/worktree.py:93` (`DEFAULT_RUNTIME_ROOT = Path(".ergane")`) is
*relative to the process's working directory*. So a test that changes directory
into repository B and pins nothing gives B its own empty ledger:
`factory/cli/doctor.py:240` — `_report_if_new` finds no prior row, returns
`True`, and `factory/cli/doctor.py:206-212` — `_run_all_probes` returns
`EXIT_USER` — which is exactly the value US3-S3 asserts, on today's shipped code,
with a zero-line production diff. US3-S4's control passes for the same reason, so
the pair that was written to be unfailable-together is unfailable in the wrong
direction. The wrong move is idiomatic in this suite:
`tests/test_runtime_root_findings.py:65` — `_chdir_tmp` deletes `ERGANE_ROOT` and
`FACTORY_ROOT` and then chdirs, deliberately, so the resolver reads the cwd —
correct for that module, fatal here. The harness US3 extends already does the
opposite: the session fixture pins both names to one path at
`tests/conftest.py:545`. Keep that pin, or pass the same explicit `--db` to both
runs, and let the working directory be the only difference. The falsifier is
cheap and you should run it: check out the tree unmodified, run T026 and T027 with
the pin removed, and watch them pass. If they pass, they are testing the resolver,
not this spec.

## Sizing

US1 touches `factory/doctor/store.py` (the DDL constant, `SCHEMA_VERSION`,
`_bootstrap_schema`, a new `_migrate`, and the two read functions FR-016 names),
`factory/doctor/models.py` (**three** fields across two frozen carriers:
`repository` on `Finding`, and `repository` **and** `refs` on `FindingEvent` —
one field on the first, two on the second), and
`specs/015-factory-doctor/contracts/doctor-store.sql`. Its tests live in
`tests/test_doctor_store.py`, whose two column-expectation lists must move with the
schema and which gains the frozen-literal fixture of trap 12.

US2 touches `factory/doctor/store.py` (the upsert and the event insert),
`factory/doctor/models.py` (the resolver and the batch grammar),
`factory/cli/doctor.py` (the `report` option and its `Finding` construction) and
`factory/workgraph/detector.py` (the thread from `compare_and_report` through
`_build_finding` and into the missing-snapshot branch, and the batch dedupe). It
touches no workflow and no activity: `factory/workgraph/adapter.py` already passes
`target_repo` and needs no edit.

US3 touches `factory/cli/doctor.py` (the `list` filter, the per-repository counts,
the newness rule and the working-directory resolution of FR-017) and
`factory/doctor/store.py` (one grouped query). By FR-006 it touches neither
`factory/workgraph/worktree.py` nor `factory/doctor/cli.py`'s store resolution; by
FR-015 the newness rule is changed in `factory/cli/doctor.py` and not in
`factory/doctor/cli.py`. It also extends the `ergane doctor` harness that already exists,
`tests/test_ergane_ports.py:80` — `_patch_probe`, in the two directions it does
not go today: a probe whose `evaluate` returns a critical, and a working directory
that says which repository the run is about — against the **one** store the session
fixture already pins at `tests/conftest.py:545`, which trap 15 says must survive the
extension. Real work, but bounded, and not a new harness.

The three stories share `factory/doctor/store.py`, and US2 and US3 share
`factory/cli/doctor.py` — which is why the Work Graph is a chain rather than a
fan-out. Inside this spec the one production file no other story touches is
`factory/workgraph/detector.py`, which is US2's alone; the contract SQL is US1's
alone. Across specs that is not true: `factory/workgraph/detector.py` is also
edited by three of 130's four stories, which is what the `depends_on_landed` edge
and trap 14 are for. 143 must not be flipped ready alongside 130.

Every story is well inside the 64 KiB deterministic diff bound (D-050): US1 is
around a hundred production lines plus one test module's edits, US2 around a
hundred and twenty across four files, US3 around ninety across two, and the pasted
evidence each verification task asks for is a short `sqlite3` transcript and a few
exit codes, not a suite log.

## Verification the operator will run, independent of the gate

Per constitution VIII and D-037 the judge sees the diff and the criteria only, so
runtime evidence must be committed as pasted output. Beyond that:

1. Copy `.factory/doctor.db` to a scratch path — 520 findings, 1032 events,
   `schema_version` 1 as of 2026-09-04 — and open the copy with the new `connect`.
   Confirm with `sqlite3` that the row and event counts are unchanged, that
   `PRAGMA table_info` shows the new columns, and that
   `hardening/agent-worktree-boundary` still reads `occurrences = 90`. Then open
   it a second time and confirm nothing changed again.
2. Take a *second* copy, do **not** open it with `connect`, and run
   `ergane spec validate` and `ergane findings triage` (no `--apply`) against it.
   Both must answer. This is trap 13 run forwards: on the shipped code today they
   answer, and a diff that names the new column in a SELECT list makes the first
   one crash rather than skip a layer.
3. Run an epic against a target repository and read the **repository column** out
   of `doctor.db` for the detector's finding — `SELECT` that column, not the
   summary string, which 130 already fills in — and read the per-entry
   `repository` of `<runtime-root>-detector/findings.json`. Then delete the start
   snapshot mid-attempt and confirm the missing-snapshot CRITICAL's column is
   filled too. This is the only step that exercises both seams of trap 10 end to
   end, and reading the column rather than the prose is what makes it a check of
   *this* spec rather than of 130.
4. Report the same key twice with different `--refs`, once per repository, then
   read `finding_events`. Both observations must keep their own refs. Today the
   second erases the first and the trail holds neither column; that contrast is
   the whole of US2.
5. With every probe answering — `EXIT_TRANSPORT` (3) and the unexpected-error
   branch at `factory/cli/doctor.py:206-212` both precede the new-criticals
   branch, so a 3 here means a service is down, not that this spec failed — `cd`
   into repository A and run `ergane doctor` until a critical is recorded, then
   `cd` into repository B and run the same bare command and read `$?`. Both
   shells must carry the *same* pinned `ERGANE_ROOT` (`scripts/ergane-env.sh:84`):
   two roots are two ledgers, and the step then demonstrates nothing. It must be
   1. Run it in B again and it must be 0. Then run it in A again and confirm it is
   still 0 — the rule gained a dimension and lost no silence. The command must be
   bare: if you had to name the repository, FR-017 was not implemented.
6. Run `ergane findings list --json` with and without the repository filter and
   confirm the unfiltered listing still shows each key exactly once, with its
   `occurrences` total unchanged from step 1 and its per-repository counts beside
   it.

Step 5 is the falsifiable test of the sharpest half: it is the green check that
was never green, run forwards.
