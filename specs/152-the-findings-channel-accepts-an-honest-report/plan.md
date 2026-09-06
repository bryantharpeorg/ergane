# Implementation Plan: the findings channel accepts an honest report

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## What already exists, and where

**The live verb is in `factory/cli/doctor.py`, not in `factory/doctor/cli.py`.**
`ergane findings report` is registered at `factory/cli/doctor.py:293` inside
`factory/cli/doctor.py:251` — `add_findings_parser`, and handled by
`factory/cli/doctor.py:450` — `findings_report_command`. The legacy module is
imported once, at `factory/cli/doctor.py:54`, and used for exactly one function:
`factory/cli/doctor.py:65` — `_store_path` calls `_doctor_cli._resolve_store_path`
at `factory/cli/doctor.py:70`, and nothing else in this module reaches it.
`factory/doctor/cli.py:121` — `_report_command` is a same-shaped copy that no
parser reaches; it is exercised only by tests that import it directly. Read
trap 1 before you edit anything.

**The pattern is one line and it exists four times.** It is a module-level
`re.compile` of the same source string at `factory/cli/doctor.py:58`,
`factory/doctor/scaffold.py:21`, `factory/doctor/cli.py:43` and — inside the
`_SECRET_PATTERNS` tuple — `factory/cli/repo_export.py:55`. All four are
byte-identical today.

The shape, described rather than pasted: two literal letters, a hyphen, then
eight or more characters from a class holding letters, digits, underscore and
hyphen. **There is no left boundary before the two letters**, which is the whole
defect: the match may begin anywhere, including inside an ordinary word whose
final two letters happen to be those two. The pattern's source is deliberately
not written literally anywhere in this trio — see trap 3 — and neither is the
word that trips it.

**Two consumers in the live module, and the second one is the one nobody
expects.** `factory/cli/doctor.py:76` — `_contains_secret` calls `.search()` and
throws the match object away; `factory/cli/doctor.py:82` — `_sanitize_text` calls
`.sub()` with the marker:

```python
def _contains_secret(value: str | None) -> bool:
    if value is None:
        return False
    return bool(_CREDENTIAL_RE.search(value))


def _sanitize_text(value: str | None) -> str | None:
    if value is None:
        return None
    return _CREDENTIAL_RE.sub("[REDACTED]", value)
```

`_sanitize_text` is reached from `factory/cli/doctor.py:85` — `_sanitize_finding`,
which runs over probe output at `factory/cli/doctor.py:201` — `_run_all_probes`
and over every finding being promoted at `factory/cli/doctor.py:537`.

**The scaffolder sanitises again, with its own copy.** `factory/doctor/scaffold.py:53`
inside `factory/doctor/scaffold.py:27` — `scaffold_spec` calls the scaffolder's own
`factory/doctor/scaffold.py:297` — `_sanitize_finding`, which calls the
scaffolder's own `factory/doctor/scaffold.py:281` — `_sanitize_text` against the
copy at `factory/doctor/scaffold.py:21`. `factory/doctor/scaffold.py:74` —
`_build_trio` does the same over the slug, title and anchor. Nothing on this path
reads `factory/cli/doctor.py:82`, so an accepted note that names a hyphenated
identifier is rewritten into the promoted spec as the marker even after the live
door is fixed.

**The fourth copy is the export scrubber, and it is on the same store.**
`factory/cli/repo_export.py:55` is the first entry of `_SECRET_PATTERNS`; the two
beside it — a Telegram-shaped token and a forge-token shape — already carry their
own left `\b`, so the unanchored one is the odd member of its own tuple. Every
exported string passes through one function:

```python
def _clean(value: Any) -> Any:
    """The one choke point every exported string passes through."""
    if not isinstance(value, str):
        return value
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub(REDACTION, value)
    return value
```

at `factory/cli/repo_export.py:197` — `_clean`, called per column at
`factory/cli/repo_export.py:201`. `_STORES` at `factory/cli/repo_export.py:64-68`
names `("findings", "doctor.db", "findings", "key")` first, so **every exported
finding's `summary`, `refs` and `notes` run through this copy**. The entry point
is `factory/cli/repo_export.py:107` — `export_records`, whose docstring says it
commits nothing and touches no store: it is a pure read, which is what makes it
safe to drive by hand in verification step 5. Its only CLI door is
`ergane repo forget <slug> --export DIR`, registered at `factory/cli/repo.py:194`
and called at `factory/cli/repo.py:372` — a verb that also deregisters the
repository, which is why the operator step below calls `export_records` directly
rather than through it.

**The doctrine written above that tuple is not the thing being changed.**
`factory/cli/repo_export.py:50-53` says the shapes are "deliberately wider than
any one store's contents", because the cost of a miss is a key in a file handed to
someone else. That sentence is about *how many shapes* are swept, not about
matching mid-word, and it stays true after this spec: the two other shapes are
untouched and the third gains the same left boundary they already have.

**The refusal sites, all four of them, in one function.** Batch:
`factory/cli/doctor.py:458` and `factory/cli/doctor.py:462`. Single:
`factory/cli/doctor.py:482` and `factory/cli/doctor.py:484`. Every one raises
`OperatorError` with a fixed sentence. Nothing carries a field name, an offset or
a span.

**The write loop, and why a refusal is not a rollback.** The loop opens at
`factory/cli/doctor.py:457`; the write is `factory/cli/doctor.py:466`:

```python
        for raw in findings:
            if _contains_secret(raw.summary) or _contains_secret(raw.notes):
                raise OperatorError(
                    f"batch refused: finding {raw.key!r} contains a credential-like value"
                )
            if any(_contains_secret(ref) for ref in raw.refs):
                raise OperatorError(
                    f"batch refused: finding {raw.key!r} contains a credential-like value"
                )
            report(conn, raw, seen_at=seen_at)
```

`factory/doctor/store.py:137` — `report` opens `with conn:` at
`factory/doctor/store.py:149`, and a `with` block on a sqlite3 connection commits
on a clean exit. There is no outer transaction. The grammar check is the model to
follow: `factory/doctor/models.py:81` — `parse_findings_batch` validates the
whole file first and raises once through `factory/doctor/models.py:66` —
`raise_if_any`, collecting every defect into one readable error. That is FR-007's
shape, already written, twenty lines above the code you are fixing.

**The guarantee the partial write contradicts** is
`specs/015-factory-doctor/spec.md:119-123`: "ingestion is all-or-nothing: one
malformed entry refuses the whole batch naming the offending entry and rule, and
the store is unchanged". It is true of the grammar and false of the sweep.

**Why the re-run is worse than the refusal.** `factory/doctor/store.py:170`
increments `occurrences`; `factory/doctor/store.py:171` advances `last_seen`.
`factory/doctor/triage.py:631` — `_class_declared` reads `last_seen` to decide
whether a declared fix holds or the defect was seen after it, and
`factory/doctor/triage.py:552` inside `factory/doctor/triage.py:470` — `classify`
reads it again for the cold class. A double-counted re-run silently moves rows
between triage classes.

**The fixture discipline this spec needs is already written.**
`tests/test_125_us3_credential_runway.py:229` —
`test_no_credential_value_appears_in_us3_source` asserts that no live credential
prefix appears in its own story's files, and builds the forbidden strings from
fragments at `tests/test_125_us3_credential_runway.py:241` precisely so the test
file does not contain them. Copy that discipline for both the trigger word and
the synthetic credential.

**The one existing test module for this verb drives the real CLI** —
`tests/test_ergane_findings.py:37` — `_invoke` calls `main_module.main(argv)`, so
`invoke("findings", "report", ...)` reaches `findings_report_command`. Its store
fixture at `tests/test_ergane_findings.py:59` — `db_path` builds a `.factory/doctor.db` under
`tmp_path` and its seeder at `tests/test_ergane_findings.py:64` — `seeded_db`
writes rows through the store API with an explicit `seen_at`, which is exactly
the shape US2-S3 needs for the untouched-`last_seen` assertion.

**The export door already has a test module and a seam.**
`tests/test_ergane_repo_forget.py:540` —
`test_no_credential_shaped_value_reaches_an_exported_file` runs a real export and
asserts the seeded credential is gone and the marker is present.
`tests/test_ergane_repo_forget.py:113` — `seed_stores` takes a `secret=` keyword
and writes it into the findings row's `summary` and `notes`, which is exactly the
seam US1-S5 needs — pass a value carrying both the trigger word and the synthetic
credential. That existing test stays green under FR-001 because its fixture at
`tests/test_ergane_repo_forget.py:61-65` sits after a space in the seeded text, so
it still begins at a token boundary; check that before you assume your change is
safe.

## Traps

**Trap 1 — The document that sent you here names a module no command runs.** The
triage entry says the pattern to fix is at `factory/doctor/cli.py:43`. It is
there, and editing it changes nothing an operator can observe:
`ergane findings report` is registered at `factory/cli/doctor.py:293` and handled
at `factory/cli/doctor.py:450` — `findings_report_command`, which reads the copy
at `factory/cli/doctor.py:58`. The wrong move is the cheap one — edit the line
the document names, watch the tests that import `factory.doctor.cli` directly go
green, and ship a story that leaves the channel exactly as silent as it was. Both
ledger rows' own `refs` already point at `factory/cli/doctor.py`; the prose that
sent you here does not. FR-001 is satisfied only when the live door changes
behaviour, which is why US1-S1 reports through the CLI rather than calling a
helper.

**Trap 2 — Four copies, and the last one bites on the way out of the repository.**
FR-004. `factory/cli/doctor.py:58`, `factory/doctor/scaffold.py:21`,
`factory/doctor/cli.py:43` and `factory/cli/repo_export.py:55` each compile their
own. Anchoring one leaves the promoted spec still rewriting an honest note into
the marker through `factory/doctor/scaffold.py:281` — `_sanitize_text`, and leaves
`ergane repo forget --export` rewriting it through
`factory/cli/repo_export.py:197` — `_clean` in a file the operator hands to
someone else. The fourth copy is the one that is easy to miss and the worst to
miss: `_STORES` at `factory/cli/repo_export.py:64-68` puts the findings store
first, so it runs over the same `notes` column the sweep guards, and the draft of
this very spec counted three copies and wrote an identity test that would have
gone green over it. The wrong move is to fix the live copy, prove it with a
refusal test, and declare both ledger rows closed — that is the shape this floor
has now recorded three times (100 on the kill path, 092 on the lockfile half, 120
on the fresh-repository half), and `findings triage` closes a row on a spec's
`fixes:` declaration without being able to tell a whole fix from a quarter of one.
Verify the count yourself before you start: grep `--include=*.py factory/` for the
compiled pattern's source, assembling the search string from fragments in your
shell the way trap 3 requires of the fixtures. It returns exactly those four files
today, and it is the check that caught the fourth. Give the pattern one home,
import it into every other module that sweeps or redacts, leave the two sibling shapes in
`_SECRET_PATTERNS` alone, and let US1-S4 assert the identity.

**Trap 3 — The trigger cannot be written down, and this repository's own notes go
through the same sweep.** The tripping string is an ordinary English word whose
final two letters are the pattern's two, immediately followed by a hyphen and a
long lower-case tail. Written literally into a test file, that file's contents can
never be quoted in a finding, a note, or a promoted spec — the fixture would make
its own bug unreportable, which is the bug. Build it from fragments the way
`tests/test_125_us3_credential_runway.py:241` builds its forbidden prefixes, and
do the same for the synthetic credential in FR-002's control. The same
prohibition covers the pattern's own source string: this trio describes it and
never pastes it, and the value at `tests/test_ergane_repo_forget.py:61-65` — which
*is* of the matching shape — is referred to by its name and never copied into a
note, a docstring, a commit message or pasted evidence. The wrong move is to paste
the reporter's epic identifier verbatim "so the test is realistic".

**Trap 4 — The second ledger row is a partial-write bug, not a duplicate of the
first.** Anchoring the pattern removes the false positive and leaves the partial
write completely intact: a **real** credential in entry three still commits
entries one and two. Read the mapping before you believe one story is enough:
the first row records **two** complaints — an unanchored pattern, closed by
FR-001 through FR-004 in US1, and a refusal that names nothing, closed by FR-005
and FR-006 in US2 — while the second row is closed by FR-007 and FR-008, also in
US2. **Neither key is closed by US1 alone.** A diff that lands US1 and declares
both is the half-fix in its purest form, and `ergane findings triage --apply`
would close both rows on the strength of the `fixes:` block without being able to
tell. If US2 is descoped for any reason, both keys come out of `fixes:` in the
same edit.

**Trap 5 — "The store is unchanged" needs the seeded row, not just an empty
store.** FR-008. A three-entry batch against an empty store, with the offender
third, does fail today — entries one and two are committed — so an
assert-store-is-empty test is genuinely red first. But it does not cover the
damage the ledger row actually describes: the operator's *re-run*, where the
earlier keys already exist and `factory/doctor/store.py:170` increments
`occurrences` while `factory/doctor/store.py:171` advances `last_seen`, the field
`factory/doctor/triage.py:631` — `_class_declared` reads. Seed the first entry's
key through the store API with an explicit `seen_at`, the way
`tests/test_ergane_findings.py:64` — `seeded_db` does, and assert both fields
afterwards.

**Trap 6 — The one test module for this verb freezes the wrong clock.** The
autouse fixture at `tests/test_ergane_findings.py:106` —
`_freeze_doctor_utcnow` patches `_utcnow` on the **legacy** module,
`factory.doctor.cli`. The live command has its own at `factory/cli/doctor.py:61`
— `_utcnow`, read at `factory/cli/doctor.py:451` and at
`factory/cli/doctor.py:382`. Nothing in that module asserts a rendered age, so
the mismatch is invisible and every test passes. A new test that leans on that
fixture to prove `last_seen` did not advance is asserting against the real clock
and will be green for the wrong reason. Patch `factory.cli.doctor._utcnow`, or —
better — seed with an explicit `seen_at` and assert the stored value.

**Trap 7 — Do not weaken the sweep, and do not add a way around it.** The entry's
own out-of-scope line. The lookbehind must exclude a letter or digit before the
prefix and **nothing else**: a credential after `=`, after a hyphen, or at the
start of a value must still match, or FR-002's control fails — in the two report
doors *and* in the exporter, where a miss is a key in a file handed to someone
else. The tempting wrong moves are widening the required tail length, dropping the
hyphen from the character class, deleting one of the two sibling shapes in
`factory/cli/repo_export.py:55` while you are in there, or adding a `--force` flag
so a reporter can push text through. None of those is this spec; the sweep stops
being wrong rather than becoming optional or narrower.

**Trap 8 — The echo is the half that matters, and it must not print the match.**
FR-005 with FR-006. The reporter's own local pre-screen found a second match in
seconds that three server-side refusals could not name at all — the information
exists at `factory/cli/doctor.py:76` — `_contains_secret` and is thrown away when
the match object is reduced to a `bool`. Return what preceded the match, not the
match: a real credential survives blind text-mutation exactly as well as prose
does, so silence buys no security, while echoing the value would. The wrong move
is to print the matched span "redacted" by truncation — the first eight characters
of a credential are still eight characters of a credential.

**Trap 9 — Do not grow a fifth copy while fixing the first four.** FR-009. The
refusal formatter needs a match object, which `_contains_secret` does not return.
The tempting shortcut is to leave that helper alone and call `.search()` again in
the refusal path from a locally compiled pattern — which is how the extra copies
were born. Change the helper (or replace it) so exactly one object answers both
"does this contain one" and "where".

## Sizing

US1 is one lookbehind, one shared home for the pattern, and an import edit in
every other module that holds a copy — three of them if the home is one of the
four, four if it is a new module. It
touches `factory/cli/doctor.py` (the constant block, lines 58 to 98),
`factory/doctor/scaffold.py`, `factory/doctor/cli.py`, `factory/cli/repo_export.py`
(the first element of `_SECRET_PATTERNS` only), and whichever module becomes the
pattern's single home. Tests: one new module for the report and identity cases,
the promote/scaffold assertion, and one case added to
`tests/test_ergane_repo_forget.py` beside
`tests/test_ergane_repo_forget.py:540` for the export door.

US2 is the refusal formatter and the hoist. It touches `factory/cli/doctor.py`
only — `findings_report_command`, lines 450 to 504, plus the formatter beside the
sweep helpers — and its tests live in `tests/test_ergane_findings.py` and one new
module for the batch cases.

The two stories are **not** file-disjoint: both edit `factory/cli/doctor.py`, in
regions roughly four hundred lines apart. That is why US2 carries
`depends_on_merged: [US1]` rather than running beside it. US1 owns
`factory/doctor/scaffold.py`, `factory/doctor/cli.py` and
`factory/cli/repo_export.py` alone; US2 touches none of them. Neither story
touches `factory/doctor/store.py`, `factory/doctor/models.py` or
`factory/workgraph/detector.py`.

Both stories are well inside the 64 KiB deterministic diff bound (D-050): each is
under a hundred production lines plus tests, and the pasted evidence each
verification task asks for is a handful of short refusals, not a transcript.

## Verification the operator will run, independent of the gate

Per constitution VIII and D-037 the judge sees the diff and the criteria only, so
runtime evidence must be committed as pasted output. Beyond that, against a
scratch store (`--db` on a temporary path, never the real ledger):

1. Report a finding whose note contains a word of the tripping shape, assembled
   in the shell from two fragments so no file on disk holds it. Before the change
   it is refused; after, it is accepted, and `ergane findings list --json` shows
   the note stored character for character.
2. Report one carrying a synthetic credential after a space, and again after an
   `=`. Both must still be refused, and the refusal must name the field and the
   offset and must not contain the value.
3. Run a three-entry batch whose third entry carries a synthetic credential
   against a store already holding the first entry's key. The verb must refuse and
   `ergane findings list --json` must still show that key at `occurrences` 1 with
   its original `last_seen`.
4. Promote a finding whose note contains the tripping word and read the
   scaffolded trio. The word must be present; the redaction marker must not.
5. The export door, driven directly rather than through
   `ergane repo forget --export`, which would deregister a repository: copy the
   scratch store to a temporary runtime root and call
   `factory/cli/repo_export.py:107` — `export_records` against it with a
   destination outside that root. Read the written `findings.jsonl`: the tripping
   word must be present and the synthetic credential must be the redaction marker.
   Before the change the word is the marker too, which is what makes this step
   falsifiable.
6. The falsifiable test of the whole spec: file this spec's own two ledger rows
   again, verbatim, through `ergane findings report --batch`, notes included. The
   report that documents the bug must be fileable by the bug. It is refused today.
