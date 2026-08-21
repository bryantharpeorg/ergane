# Implementation Plan: the ledger triages what it can prove

**Spec**: `specs/073-the-ledger-triages-what-it-can-prove/spec.md`

## What already exists, and where

Every line below was read and **verified against `a58ec93` on 2026-08-20**.
Check each before you rely on it; this tree moves nightly.

**The frontmatter grammar US1 widens:**

- `factory/roadmap/models.py:113` — `_KNOWN_KEYS = ("state", "depends_on_landed")`.
  Its comment at `factory/roadmap/models.py:107-112` states why the set is closed:
  the frontmatter rides `PromptSources.spec_text` whole into agent payloads. Add
  exactly one name. Read that comment before you do — it is the reason the story
  is one tuple entry and not a general-purpose metadata block.
- `factory/roadmap/models.py:293-301` — the `unknown_key` refusal that reads
  `_KNOWN_KEYS`, and the message that quotes the grammar back at the author. It
  needs no change; it will name `fixes` automatically once the tuple carries it.
- `factory/roadmap/models.py:325-333` — the `depends_on_landed` shape check:
  absent reads as `[]`, `None` reads as `[]`, anything not a list of strings is a
  finding. **This is the worked example for FR-001 and FR-002.** Copy it exactly;
  a second shape-checking idiom in the same function is a review comment waiting
  to happen.
- `factory/roadmap/models.py:122-138` — `SpecEntry`, a frozen dataclass whose
  last field is `source: str = ""`. A new field must follow it and must also carry
  a default, and a list default on a frozen dataclass needs
  `field(default_factory=list)` — a bare `= []` is a shared-mutable bug the type
  checker will not catch here.
- `factory/roadmap/models.py:336-340` — where `SpecEntry` is constructed. One more
  keyword.

**The verb surface US2 and US3 extend:**

- `factory/cli/doctor.py:238-304` — `add_findings_parser`. Four verbs are
  registered here (`list`, `report`, `resolve`, `promote`), each on a shared
  `db_parent` that supplies `--db`. Register `triage` the same way.
- `factory/cli/doctor.py:307-319` — `_with_store`, the decorator every existing
  verb's runner is wrapped in. **`triage` must NOT use it** — see trap 3.
- `factory/cli/doctor.py:322-345` — `findings_list_command`, the closest existing
  verb in shape: reads `list_findings`, filters, prints a fixed-width table or
  `--json`. Copy its shape, including `--json`.
- `factory/cli/doctor.py:110-128` — `_resolve_promoted_findings`, which walks
  findings, reads `<promoted_spec>/spec.md` and resolves when the state is
  `landed`. It is the closest existing thing to FR-005 and it **writes**, which is
  precisely why triage must not inherit it.
- `factory/cli/doctor.py:131-143` — `_read_spec_state`, which splits frontmatter
  and returns `state`. Once US1 lands, prefer the roadmap reader's parsed
  `SpecEntry` so `fixes` and `state` come from one parse.
- `factory/cli/nouns/findings.py:8-13` — the `Noun` registration. No change.

**The store functions US3 needs, and the one it must not use:**

- `factory/doctor/store.py:271-310` — `resolve_by_spec(conn, key, *, spec_dir,
  resolved_at)`. It refuses only a finding already `resolved`; an `open` one is
  fine. **This is exactly FR-014.** Use as-is.
- `factory/doctor/store.py:229-268` — `resolve(conn, key, *, reason,
  resolved_at)`, the reason-carrying variant. FR-016's fold wants this one.
- `factory/doctor/store.py:112-180` — `report`. **Not an annotation path.** Trap 4.
- `factory/doctor/store.py:370-391` — `list_findings`, the only read you need.
- `factory/doctor/store.py:50-68` — the `findings` table. `status` carries a
  `CHECK` over exactly four values and **this spec adds no fifth**.

**The detector US4 and US5 change:**

- `factory/workgraph/detector.py:1-18` — the module docstring. Line 6 states the
  contract: a store, ledger or sibling worktree that was "**removed or
  truncated**". US4 makes the code honour the sentence.
- `factory/workgraph/detector.py:77-86` — `RuntimeRootState.changes_since`, whose
  test is `if before != after`. Three lines, and the centre of US4.
- `factory/workgraph/detector.py:241-276` — `_runtime_root_state`.
  `factory/workgraph/detector.py:253` names the three evidence stores;
  `factory/workgraph/detector.py:272` is `for path in node_dir.rglob("*")`, the
  full walk of every sibling worktree.
- `factory/workgraph/detector.py:329-330` — `_finding_key`, two lines, the centre
  of US5.
- `factory/workgraph/detector.py:333-385` — `_build_finding`, which assembles
  refs, notes and summary. `factory/workgraph/detector.py:355` is the literal
  heading `"Runtime-root paths removed or truncated:"` currently printed above a
  list of creations.
- `factory/workgraph/detector.py:56-62` — `TrackedState.changed`, and
  `factory/workgraph/detector.py:127-206` — `_tracked_state`. **Out of scope. Do
  not touch.** FR-023.

## Traps

**1. Naming is not fixing, and this spec exists because the first draft got that
wrong.** Measured on the corpus: 16 open findings are named by more than one
spec, and `interpreter/ci-failure-never-reaches-an-agent` is named by six — 025
and 071 as their fix, 027 in an out-of-scope list, 028 as background, and **061 in
a note saying the finding is regressed**. Any text rule reads four of those as a
fix and one of the four says the opposite. FR-005 rests on the declared `fixes:`
key and nothing else; FR-008's candidate class is where prose goes, and FR-019
forbids `--apply` from ever touching it. US3-S2 is the test that keeps them apart.

**2. A spec can say `state: landed` with no commit that says so.** 070 and 071 are
both `state: landed` in the working tree with the flip uncommitted, so
`git log -S 'state: landed'` finds nothing for either. That is not a pickaxe
quirk, it is the working-tree-versus-branch defect class this repository already
has a finding for. Classify undated as needs-a-human (FR-007). The tempting
fallbacks — file mtime, the human-written `# ATTESTED landed …` comment, "assume
it landed before today" — each silently produce the trap-1 failure. US2-S3 is the
test.

**3. Use `git log --reverse` and take the first commit, not `git log -1`.** The
question FR-005 asks is *when did this first land*, and `-1` answers *when was
`state: landed` last touched*, which is a different date on any spec whose
frontmatter was edited after landing. They agree on 025 and diverge on any spec
with a post-landing amendment.

**4. `triage` without `--apply` must not write one byte, and `_with_store` would.**
`factory/cli/doctor.py:307-319` calls `_resolve_promoted_findings` before every
verb, and that function resolves rows. Wrapping `triage` in it makes FR-013 false
on any store where a promoted spec has just landed — and the failure is invisible,
because the write is correct behaviour for a different verb. Give `triage` its own
runner that opens the store and calls the classifier. US2-S8 hashes the file.

**5. `report()` is not an annotation path.** `factory/doctor/store.py:112-180`
increments `occurrences`, advances `last_seen`, and appends a `finding_events`
row on every call — and flips any `resolved` row to `regressed` on the way past.
Annotating 119 findings through it would add 119 phantom recurrences to a ledger
whose entire purpose is counting recurrence. Write a new `annotate()` beside
`resolve` that updates `notes` and nothing else. FR-018 and US3-S6 hold you to it.

**6. Match finding keys on segment boundaries, never as a bare substring.** Today
no key is a strict prefix of another, so the naive `key in text` test happens to
be safe — and US5 destroys that property, because
`hardening/agent-worktree-boundary` becomes a real key and is a prefix of all
forty legacy `hardening/agent-worktree-boundary/<epic>/<node>` rows. A substring
test written today is a defect that arrives when US5 lands, in a different story,
where nobody will be looking for it. FR-009 says segment-bounded; do it in both
the prose scan and the fragmentation grouping.

**7. Define the fragmentation prefix by segment count, not by splitting on the
last slash.** FR-009: three or more segments, grouped by the first two, same
`source`, at least two members. Most keys in the store are exactly
`category/slug` and must form no group at all; a rule that groups by
`everything-before-the-last-slash` puts every two-segment key into a group named
by its category and reports 27 fragmented classes that are not classes.

**8. The detector's docstring and its code disagree, and the code is wrong.**
Measured on the live store: the 070/us1 finding lists **3,860 changes, of which
3,859 are creations** (`None -> {...}`) and **zero are removals**. The heading
printed above them says "removed or truncated". US4 is not new behaviour; it is
making three lines of comparison match a sentence that has been in the module
since it was written.

**9. The one non-creation was the detector tripping itself.** `doctor.db` grew
4,096 bytes between snapshot and teardown.
`factory/workgraph/detector.py:253` snapshots `doctor.db`;
`factory/workgraph/detector.py:470` writes to `doctor.db`. Under FR-020 alone
this entry still fires on every attempt forever, because growth is not creation.
FR-021 is why it must be named separately, and note the asymmetry it demands:
growth silent, truncation loud. US4-S3 and US4-S4 are the pair.

**10. The creations belonged to a different node.** Every one of the 3,859 was
under `worktrees/070-…/us4/`, reported against `us1`.
`factory/workgraph/detector.py:272` rglobs every sibling worktree in full, and
siblings run concurrently. FR-022 excludes `__pycache__`, `.pytest_cache` and
`*.pyc` **at capture** rather than at comparison — exclude at capture and the
snapshot stops being enormous too. This is why the count exploded on 2026-08-19
and not before: it tracks concurrency, not agent behaviour.

**11. Do not weaken the tracked-path check.** `TrackedState.changed` and
`_tracked_state` are the half that caught four real escapes, including the one
that committed onto the landing branch. US4 touches `changes_since` and
`_runtime_root_state` only. US4-S5 is the regression guard, and a diff that edits
`changed()` fails FR-023 on sight.

**12. The fold is not durable until US5 lands.** US3's `--apply` resolves the
forty legacy per-node rows, and until US5 changes `_finding_key` the very next
attempt mints a fresh one. That is not a defect in either story, but a `--apply`
run between them will look like it did nothing. Say so in the output.

**13. Every fixture is a supplied tree — never this repository, never
`.factory/`.** Build stores with `connect()` on a tmp path and corpora with
`tmp_path`. A test that opens `.factory/doctor.db` reads the running factory's
production evidence; a test that asserts against real `specs/` fails next week
when a spec state flips. This repository has already paid once for a test whose
only green condition was deleting the live store.

**14. Do not commit the archived store as a fixture.** It is 70 MB. The success
criteria name a path outside the repository for exactly this reason — a
multi-megabyte fixture in a diff is the `verify/judge-cannot-see-a-large-diff`
failure, and this one is thirty times the size that caused it.

**15. The controls are the story, not a courtesy.** US1-S4, US2-S6, US2-S9,
US3-S7, US4-S1 and US5-S4. A classifier that calls everything needs-a-human
passes every positive assertion in US2. Each class needs a paired silence:
declared-but-seen-since is not fixed, prose is not a declaration, a lone key is
not fragmented, a fresh finding is not cold, a growing store is not a violation.
Prove each control can fail by flipping one field in the same fixture.

**16. Widening `_KNOWN_KEYS` will break a test that asserts the grammar, and that
test is right to exist.** Update it in the same diff rather than working around
it, and keep US1-S4's assertion that an unknown key is still refused — the value
of a closed grammar is that widening it is a visible act.

**17. The judge sees the diff and the criteria — and Success Criteria are NOT
criteria.** `factory/verify/criteria.py` reads Success Criteria bullets past; what
reaches the judge is each story's acceptance scenarios and its FR bullets.
SC-001 through SC-007 are the operator's. Every Then-clause in the spec is written
"proven by a committed test" precisely so it is provable from the diff alone.

**18. One test file per story, named here.**
- US1 → `tests/test_spec_declares_its_fixes.py`
- US2 → `tests/test_findings_triage_classifies.py`
- US3 → `tests/test_findings_triage_applies.py`
- US4 → `tests/test_detector_reports_removals_only.py`
- US5 → `tests/test_detector_keys_on_the_class.py`

## Sizing

US1 is one tuple entry, one shape check copied from its neighbour, one dataclass
field and one keyword. It is the smallest story here and it gates two others, so
it wants the shortest possible path to landing — resist adding validation of the
keys it names (see the spec's third assumption).

US2 is one read of `list_findings`, one walk of the specs corpus, one `git log`
per candidate spec, and six predicates. Its difficulty is entirely traps 1, 2 and
3 — knowing which facts constitute a proof. Cache the `git log` per spec
directory: there are 69 spec directories and 214 findings, and the naive shape
runs the subprocess 214 times.

US3 is six branches over US2's classes plus one new store function. Its difficulty
is trap 5: resisting `report()`.

US4 is a predicate change in a three-line comparison plus an exclusion filter at
capture. Small, and the tests are the work.

US5 is a two-line key change plus a truncation in `_build_finding`. Smallest of
the five.

## Verification the operator will run, independent of the gate

- **Prove US2 by the six.** Run triage against the archived store and confirm
  `interpreter/ci-failure-never-reaches-an-agent` and
  `ci/test-suite-pins-the-operator-dial` appear as seen-after-fix candidates and
  not as fixed. If either appears as fixed, trap 1 was not implemented.
- **Prove US2 by emptiness.** The archive declares no `fixes:` anywhere, so the
  fixed class must be empty. A non-zero fixed count is prose inference.
- **Prove US2 by hash.** `sha256sum` the store, run triage, hash again.
- **Prove US3 by copy.** Never against the live store on the first run. Copy,
  apply, diff the open counts, then decide.
- **Prove US4 by control.** Supplied runtime root, sibling gains a
  `.pytest_cache` → silence. Same root, sibling removed → finding. Both pasted.
- **Prove US5 by count.** Two nodes, two violations, one row, occurrences 2.
