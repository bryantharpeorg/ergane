# Implementation Plan: the ledger takes what is not yet a defect

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

The requirements this plan implements are numbered in `spec.md` §
*Functional Requirements*. The transcript in § *The alias trap, measured* was
produced on 2026-08-28, re-checked against the tree on 2026-09-04 and extended
that day with a third measurement; it is an input to this plan, not a hypothesis
for the implementer to re-derive.

## What already exists, and where

**The write verb, misnamed, and its own help string already knows the word.**
`factory/cli/doctor.py:276` registers it, and everything FR-001 must preserve is
the sixteen lines under it (`factory/cli/doctor.py:277-292`). The noun above it
carries the same word in prose — `factory/cli/doctor.py:262` is
`description="Report, list, resolve, or promote findings."`, printed by
`ergane findings --help` above the verb listing, so FR-003 owns it too:

```python
    report_parser = verbs.add_parser("report", help="record a finding", parents=[db_parent])
    report_parser.add_argument("--key", help="category/slug identity")
    report_parser.add_argument("--category", help="finding category")
```

One of those sixteen lines is a trap in its own right and trap 16 is about it:
`factory/cli/doctor.py:287` is
`report_parser.add_argument("--source", default="operator", help="reporter source")`,
and `reporter` contains `report`.

**The list command, and the two filters FR-005 joins.**
`factory/cli/doctor.py:368` — `findings_list_command` reads everything and
filters in Python; `factory/doctor/store.py:454` — `list_findings` takes no
filter arguments, and FR-005 deliberately does not change that signature:

```python
    findings = list_findings(conn)
    if severity is not None:
        findings = [f for f in findings if f.severity is severity]
    if status is not None:
        findings = [f for f in findings if f.status is status]

    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2))
        return EXIT_OK
```

That early return at `factory/cli/doctor.py:378-380` is why FR-006 puts the
withheld notice on stderr: the `--json` branch prints a bare array and returns
before the human renderer ever runs.

**The reference page that describes both verbs, and goes stale twice.**
`docs/cli/findings.md:10` carries the `findings list` synopsis —
`ergane findings list    [--db PATH] [--severity SEV] [--status STATUS] [--json]`
— and `docs/cli/findings.md:22` opens its section, whose flag sentence at
`docs/cli/findings.md:39` reads *Filter with `--severity` and `--status`, and
script against `--json`*. US1 rewrites three other lines of this same file
(`docs/cli/findings.md:11`, `:12`, `:56`), so US2 is the one story that changes
this page's *subject* — and nothing in the suite holds this page to the CLI,
which is why FR-006 asks for the synopsis-to-`--help` guard rather than for a
prose edit alone. `docs/cli/README.md:103` is the read-only verb list FR-009
adds `findings draft` to.

**The one *wired* path every probe finding takes into the store.** FR-007's
refusal goes here, not in a test over the registry —
`factory/cli/doctor.py:194-204`, ending at `factory/cli/doctor.py:240` —
`_report_if_new`. "Wired" is load-bearing: `factory/doctor/cli.py:257` —
`_report_if_new` is an identically-named twin beside a duplicate probe loop at
`factory/doctor/cli.py:214` — `_check_command`, left behind when the command
surface moved (that module's own docstring says so at
`factory/doctor/cli.py:3-6`). Nothing sets either as a runner, but twelve
modules import `factory.doctor.cli`, so a grep for `_report_if_new` returns two
definitions. Patch `factory/cli/doctor.py` only; patching the twin, or both,
produces a diff that reads correct and changes nothing:

```python
    for probe in _probes.REGISTRY:
        reports, probe_unexpected = _run_one_probe(probe, skipped_services)
        if probe_unexpected:
            unexpected_seen = True
        if reports is None:
            continue
        for report in reports:
            finding = _sanitize_finding(report.to_finding(source=probe.name))
            was_new = _report_if_new(conn, finding, seen_at=seen_at)
```

`factory/doctor/probes.py:43` — `FindingReport` carries `category` as a plain
field at `factory/doctor/probes.py:47`, and `factory/doctor/probes.py:53` —
`to_finding` copies it through untouched. Nothing between a probe and the store
looks at it today.

The loop's existing failure grammar decides FR-007's: `factory/cli/doctor.py:215`
— `_run_one_probe` swallows an unexpected exception at
`factory/cli/doctor.py:230-236`, prints one line to stderr and returns, and the
loop continues with the next probe. A reserved-lane refusal that raised
`OperatorError` would abort `factory/cli/doctor.py:188` — `_run_all_probes`
mid-registry, so one mis-categorised probe would cost every probe after it its
findings for that run. FR-007 skips the one report and continues, which is the
grammar already there.

**The triage arithmetic FR-008 must not break, and the class it must not
touch.** `factory/doctor/triage.py:204` — `Triage` documents its own invariant,
and the report prints both numbers so the day they disagree is visible:

```python
    `total` is the number of open and regressed findings; `classified` is how
    many landed in a class. The two are equal by construction, and the report
    prints both so that the day they are not, the operator sees it rather than a
    silently shortened list.
```

`factory/doctor/triage.py:470` — `classify` builds that pool from every open and
regressed row; `factory/doctor/triage.py:710` — `render` and
`factory/doctor/triage.py:675` — `to_document` are the two faces the heading
must appear in. The fragmentation class is **not** in FR-008's scope, and the
reason is a measurement rather than a preference — see trap 10 and
`factory/doctor/triage.py:455-456`:

```python
        segments = finding.key.split("/")
        if len(segments) < _MIN_SEGMENTS:
            continue
```

**The generator that already describes the trio contract, with a live proof —
on the sibling branch.** `factory/doctor/scaffold.py:153` —
`_build_spec_md_from_slots` emits the current shape, and
`factory/doctor/scaffold.py:203-226` is the part FR-011 needs:

```python
        lines.append("## Functional Requirements")
        lines.append("")
        for slot in slots:
            lines.append(
                f"- **FR-{slot['number']:03d}**: The system MUST satisfy the "
                f"acceptance scenarios of User Story {slot['number']}."
            )
```

followed by the `## Work Graph` fence with `implements:` on every node. The proof
that this shape is the contract is at `factory/cli/doctor.py:566-577`: `promote`
runs `derive_workgraph` over the scaffold's own text inside a temp directory and
refuses to rename it into place unless it compiles.

But read `factory/doctor/scaffold.py:27` — `scaffold_spec` before leaning on
that. It has two branches: `factory/doctor/scaffold.py:50-58` is taken when
`findings=` is passed and returns `factory/doctor/scaffold.py:321` —
`_build_spec_md`, and that is the branch `promote` calls at
`factory/cli/doctor.py:550-555` and therefore the branch `derive_workgraph`
proves. FR-011's brief reads the *other* branch. Both emit
`## Functional Requirements` at level 2 and a `## Work Graph` fence with
`implements:` today, so the instruction is safe — and nothing holds them to each
other, which is why T025 asserts the two branches agree on the skeleton rather
than trusting that they do.

**The completion generator, and the leak.** `factory/cli/completion.py:32` —
`_noun_and_verb_map` emits every key of `_name_parser_map` at
`factory/cli/completion.py:53`.

**The page guards that read the usage metavar as the verb list.**
`tests/page_holds_true.py:346` — `verbs_of` pulls the positional section out of a
`--help` text and matches `tests/page_holds_true.py:339`'s brace pattern first,
falling back to `tests/page_holds_true.py:343`'s indented-line pattern only when
there are no braces. `tests/test_claude_md.py:76` calls it and
`tests/test_claude_md.py:81` asserts every verb a page names is in the set it
returns; `tests/test_readme.py:66` and `tests/test_onramp_html.py:59` are the
same assertion over their own pages. That is why FR-003's metavar must be derived rather than
written out — see trap 13.

**The runtime-root resolution FR-012's output path must reuse.**
`factory/cli/doctor.py:65` — `_store_path` takes `--db` if given and otherwise
resolves through `resolve_factory_root()`. The brief's default path is the same
question with a different filename; answering it a second way is how the two
disagree.

**The wrapper `draft` must stay outside.** `factory/cli/doctor.py:353` —
`_with_store` runs `_resolve_promoted_findings` — a write — before every verb it
wraps, and `factory/cli/doctor.py:340-347` is the comment `triage` left behind
when it faced the same decision.

**The other places the verb's name is written.** Nine tracked lines in six
files: `CLAUDE.md:106`, `docs/architecture.md:558`, `docs/cli/findings.md:11`,
`docs/cli/findings.md:12`, `docs/cli/findings.md:56`,
`.claude/skills/away-mode/SKILL.md:158`,
`.claude/skills/findings-ingest/SKILL.md:186`,
`.claude/skills/findings-ingest/SKILL.md:249`,
`.claude/skills/findings-ingest/SKILL.md:250`; plus the verb tuple at
`tests/test_ergane_env_completion.py:120`, which spells it as a bare `"report"`
inside a tuple and is the one call site a grep for `findings report` misses.

**The lane, already in use.** `.claude/skills/findings-ingest/SKILL.md:150`
cites the same open-taxonomy comment this plan does and routes every want into
`feedback/…` at `info` (`.claude/skills/findings-ingest/SKILL.md:157-161`).
**Three** of its `findings list --json` call sites read every row on purpose, and
the enumeration was two until this refinement counted them with
`git grep -n 'findings list' -- '.claude' 'docs' '*.md'`:

- `.claude/skills/findings-ingest/SKILL.md:77-78` is the corpus dump, mandated at
  `.claude/skills/findings-ingest/SKILL.md:73` before any key is minted. It
  already filters — `select(.status=="open" or .status=="regressed")` — and every
  one of the ledger's 23 `feedback/` rows is `open`, so a default that hides the
  lane empties this dump of exactly the rows an ingest agent is checking against.
  That is the "split an identity" damage the skill spends
  `.claude/skills/findings-ingest/SKILL.md:57-67` describing: a duplicate key
  minted for a want that already has one, starting again at `occurrences: 1`.
- `.claude/skills/findings-ingest/SKILL.md:136` is the **category-reuse** check,
  under the bullet *Reuse an existing category*: `jq -r '.[].key' | cut -d/ -f1 |
  sort -u` lists distinct category *prefixes*, not keys. Hidden lane, and
  `feedback` vanishes from the list of categories in use, so the next ingest
  invents one.
- `.claude/skills/findings-ingest/SKILL.md:187` is the rehearsal row count over
  the scratch store at `/tmp/rehearse.db`, which the skill fills with feedback
  rows on purpose and then checks at
  `.claude/skills/findings-ingest/SKILL.md:190-193` that every `feedback/` row is
  `info`.

**Where `draft` sits relative to `promote`.** `factory/cli/doctor.py:514` —
`findings_promote_command` already refuses unknown and already-promoted keys,
refuses to overwrite an existing spec directory, and compiles the trio before
renaming it into place (`factory/cli/doctor.py:514-584`). What it cannot do is
write the *content*: the findings variant of `factory/doctor/scaffold.py:27` —
`scaffold_spec` at `factory/doctor/scaffold.py:50-58` turns findings into
skeletal text. So `draft` sits *before* `promote`, not instead of it, which is
also why FR-009 changes no status — there is no `drafting` value in the `status`
`CHECK` (`factory/doctor/store.py:55-56`), adding one is a migration this spec
has ruled out, and a row that stays `open` until a spec exists is honest anyway.

## The alias trap, measured

FR-003 exists because the obvious implementation of FR-002 leaks. Run on
2026-08-28 against a bare `argparse` tree matching this noun's shape:

```
name_parser_map keys: ['list', 'record', 'report']
grouped by parser object: [['record', 'report'], ['list']]
choices: ['list', 'record', 'report']
```

`add_parser("record", aliases=["report"])` registers **both** names in
`_name_parser_map`, and `factory/cli/completion.py:53` emits every key. So the
deprecated alias would be advertised by shell completion to every operator on the
box — the precise opposite of deprecating it.

The fix is in the same transcript: grouping by `id(parser)` recovers the
canonical name, because `add_parser` registers it before any alias. Today's
output for comparison, which the implementer should diff against:

```
        findings) local verbs='list promote report resolve triage' ;;
```

Whichever mechanism is chosen for the alias — argparse `aliases=`, or a second
`add_parser` sharing a `parents=` parent and `set_defaults` — the completion
assertion has to be written against the *output*, not against the mechanism,
because both mechanisms leak the same way.

**And `--help` leaks separately, which the 2026-08-28 transcript did not cover.**
Measured 2026-09-04 against the same bare `argparse` tree, printing
`ergane findings --help` for each shape the old T006 permitted:

```
aliases=["report"] + help=, no metavar : usage {list,record,report}   body "record (report)"
aliases=["report"] + help=, metavar    : usage VERB                   body "record (report)"
second add_parser("report"), no metavar: usage {list,record,report}   body has no report
second add_parser("report") + metavar  : usage VERB                   body has no report
```

`add_subparsers` sets `choices = _name_parser_map`, so **every registered name
renders into the usage metavar** unless an explicit `metavar` overrides it, and
`aliases=` combined with `help=` additionally prints `record (report)` in the
body no matter what the metavar says. Exactly one of the four shapes satisfies
FR-003: a second `add_parser("report")` carrying **no** `help=`, plus an explicit
`metavar` on the `add_subparsers` call at `factory/cli/doctor.py:264`. That is
what T006 must land, and it is why T007's `id(parser)` fix alone is not enough —
under that mechanism the two parsers are distinct objects and grouping by
`id(parser)` keeps both names.

**And a metavar written out by hand goes wrong the next time a verb is added,
which in this spec is three stories later.** Measured 2026-09-04 against the
same tree, with the deprecated parser marked by one
`set_defaults(deprecated_name="report")` and the metavar built two ways —
`literal` is the brace string typed by hand, `derived` is
`"{" + ",".join(n for n, sub in verbs._name_parser_map.items() if sub.get_default("deprecated_name") is None) + "}"`
evaluated after every verb is registered — and read back through the same rule
`tests/page_holds_true.py:346` — `verbs_of` uses:

```
mode=literal  draft=False  report in help: False  verbs_of=[list, promote, record, resolve, triage]
mode=literal  draft=True   report in help: False  verbs_of=[list, promote, record, resolve, triage]
mode=derived  draft=False  report in help: False  verbs_of=[list, promote, record, resolve, triage]
mode=derived  draft=True   report in help: False  verbs_of=[draft, list, promote, record, resolve, triage]
```

Both shapes hide `report`. Only the derived one still tells the truth once US3
registers `draft`: under the literal, `ergane findings draft` parses fine and
every page guard in the repository rejects a page that recommends it, because
`verbs_of` reads the braces and the braces are a hand-written copy. `metavar`
overrides the rendered label only — it never touches `choices`, which is why the
literal shape does not break parsing and therefore fails silently until a page
names the new verb.

## Traps

**Trap 1 — the reserved category must be one constant, and `is` cannot prove
it.** FR-006, FR-007 and FR-008 all turn on the word `feedback`, and three
surfaces read it: `factory/cli/doctor.py:368` — `findings_list_command`,
`factory/cli/doctor.py:240` — `_report_if_new`, and the two triage faces
`factory/doctor/triage.py:710` — `render` and `factory/doctor/triage.py:675` —
`to_document`. Spelled as a literal in each place they agree on the day they are
written and diverge on the day one is edited; the list would then hide one set
while triage separates another. Declare it once and import it — but the obvious
proof of that is vacuous, and this plan carried the vacuous proof until
2026-09-04. **Measured on this box, CPython 3.12.3: two modules each containing
only `X = "feedback"` give `m1.X is m2.X` → `True`.** CPython interns every
identifier-shaped string literal at compile time, so an assertion that the
surfaces resolve the name *by identity rather than by string equality* is
already green against exactly the shape this trap forbids — a private
`RESERVED = "feedback"` sitting in each of them. Interning is what makes it
vacuous rather than anything general about strings: the same pair of modules
holding `"zzz-not-a-lane"` gives `False`, which is why the sentinel T016 patches
in must not be identifier-shaped either if it is ever compared with `is`.

What does prove the coupling is a **substitution**. Put the constant in one leaf
module, have every consumer read it as a module attribute *at call time* —
`import factory.doctor.lane as _lane`, then `_lane.RESERVED_CATEGORY` at the
point of use, which is the shape `factory/cli/doctor.py:27` already uses for
`_probes` and the only reason T014 is able to replace `REGISTRY` at all — then
monkeypatch that one attribute to a sentinel and assert all three surfaces move
to it together. A surface that still spells the literal stays behind on
`feedback` while the others follow the sentinel, and the test goes red naming
it. T016 is that test; T018 is the import shape it requires. The tempting move
that quietly defeats both is `from factory.doctor.lane import
RESERVED_CATEGORY`, which binds the value into the consumer's namespace at
import time so the patch reaches nothing — it reads as the more idiomatic
import, and it turns T016 green against a broken tree in the other direction.

**Trap 2 — `draft` must not be wrapped in `_with_store`.** That wrapper
(`factory/cli/doctor.py:353-365`) runs `_resolve_promoted_findings` — a write —
before every verb it wraps. FR-009 says `draft` changes nothing, and a wrapped
`draft` would violate it invisibly, because the write is correct behaviour for a
different verb. The tempting move is to copy the `set_defaults` line from the
verb above it. `triage` already faced this exact decision and left the reasoning
at `factory/cli/doctor.py:340-347`; read that comment before wiring the new verb,
and note it ends `triage_parser.set_defaults(run=findings_triage_command)` with
no wrapper at `factory/cli/doctor.py:348`.

**Trap 3 — do not add a severity or a status.** The tempting change is a
`feedback` severity or a `drafting` status, and both are `CHECK`-constrained
(`factory/doctor/store.py:53-56`) with `SCHEMA_VERSION = 1` and no migration path
(`factory/doctor/store.py:20`). Migrations are possible; that is not the point.
The point is that this spec buys a lane for the price of a prefix (FR-006), and a
story that spends a migration on cosmetics has spent it before the lane has
proved it is used.

**Trap 4 — the completion output is the assertion, not the mechanism.** See §
*The alias trap, measured*. A test asserting "the parser has an alias" passes
while `factory/cli/completion.py:53` advertises the deprecated name to every
shell on the box. FR-003 is satisfied only by an assertion over the text
`ergane completion bash` and `ergane completion zsh` emit.

**Trap 5 — hiding rows without saying so is the defect, not the feature.**
FR-006's withheld count is the whole difference between a lane and a lie.
Measured on the live ledger on 2026-09-04: 520 rows, 279 open or regressed, 23 of
them already `feedback/`, 106 critical. A `findings list` that quietly omits
twenty-three rows leaves the operator confident about a number that is now 9%
wrong, and the operator reads that number as a health signal. The tempting
implementation is a one-line list comprehension beside the two filters at
`factory/cli/doctor.py:373-376`; that is the whole defect, shipped.

**Trap 6 — `draft` must not grow a dispatcher.** FR-012 is a hard boundary.
Reaching for `factory/workgraph/adapter.py:993` — `ClaudeCodeAdapter` means
constructing an `AttemptContext` — a worktree, a heartbeat, a pid file, a
per-node HOME, a transcript archive — to run one prompt. That is a second node
lifecycle, it is not what this story was sized for, and the operator's stated
position is that the drafter stays in the loop until the drafts prove otherwise.
The test is written against a stripped environment rather than against the
absence of an import, because an import can be added back without failing it.

**Trap 7 — `.specify/templates/` is stale, and FR-011 no longer points there.**
This is the one instruction in the 2026-08-28 draft that would have sent a
correct implementer somewhere wrong. `.specify/templates/spec-template.md` has
not been touched since 2026-08-06 (`e915296`): it has **no `## Work Graph`
section at all**, it puts requirements at level 3 —
`.specify/templates/spec-template.md:88` under
`.specify/templates/spec-template.md:81` — and it still teaches
`.specify/templates/spec-template.md:71` — `### Edge Cases` and
`.specify/templates/spec-template.md:106` — `## Success Criteria`, both dropped
from the house shape. A brief built from those files teaches a drafter a spec
that `derive_workgraph` cannot compile, and both stay green while the drafts get
quietly worse. FR-011 reads `factory/doctor/scaffold.py:153` —
`_build_spec_md_from_slots` instead, because that generator's output is put
through `derive_workgraph` at `factory/cli/doctor.py:566-577` before `promote`
will accept it, which makes it the only in-tree description of the shape with a
live proof attached.

**Trap 8 — `report` has one caller that is not prose.**
`tests/test_ergane_env_completion.py:120` asserts on the literal verb tuple
`("list", "report", "resolve", "promote")`. It must move in the same commit as
the rename (FR-004) or the suite fails for the right reason at the wrong time. It
is the one call site a grep for `findings report` does not surface.

**Trap 9 — the prose sweep is six files, and the guard must be scoped or it eats
its own spec.** FR-004's guard asserts `findings report` appears in no tracked
operator-facing markdown. Two exclusions are mandatory and neither is obvious.
`specs/` must be excluded: this spec's own `spec.md` quotes the old verb by
design, as does `specs/089-a-spec-that-fixes-a-finding-declares-it/plan.md:130`,
and a landed spec's prose is history that may not be rewritten. Untracked
operator documents in the working tree must also be excluded — the operator's
checkout carries several that a node's worktree does not, so a guard that walks
the filesystem is green in the node and red on the operator's box. Enumerate with
`git ls-files '*.md'`. The opposite failure is a guard so narrowly scoped it
proves nothing, which is why FR-004 also requires it to be shown failing against
a fixture that carries the string.

**Trap 10 — the fragmentation class is out of scope, and a scenario written over
it passes against an empty diff.** The 2026-08-28 draft asked FR-008 to exclude
feedback rows from `factory/doctor/triage.py:444` — `_fragmented_groups`, on the
theory that a batch-ingested want shares a group with the defects ingested beside
it. Measured 2026-09-04, it cannot: that function skips every key with fewer than
three segments (`factory/doctor/triage.py:455-456`, guarding on
`factory/doctor/triage.py:108`, and the module's own class list says so at
`factory/doctor/triage.py:33`), and **all 279 open and regressed rows in this
ledger have exactly two** — the 23 `feedback/` rows included. So the exclusion is
a no-op, and worse, the fixture that would exercise it cannot be built honestly:
the group key is the first *two* segments, so a three-segment `feedback/x/y` row
can only share a group with `feedback/x/z` siblings, which are reserved-lane rows
themselves — `category` is documented as the key's prefix at
`factory/doctor/store.py:52`. An implementer handed the old FR either burns the
attempt building an impossible fixture or writes the vacuous version and lands
green over a change that does nothing. FR-008 now asks for the heading in both
faces and for the pool to be left alone, and says `_fragmented_groups` must not
be touched. The related trap survives and is the reason the pool clause is
there: dropping feedback rows at the top of `factory/doctor/triage.py:470` —
`classify` breaks the invariant `factory/doctor/triage.py:204` — `Triage` states
in its own docstring, where `total` and `classified` are equal by construction
and the footer prints both so a mismatch is visible. A feedback row is still cold
if it is cold, and still closed by a landed spec that declares it.

**Trap 11 — `--json` stays a bare array, and the consumer sweep is three lines,
not two.** `factory/cli/doctor.py:378-380` prints
`json.dumps([asdict(f) for f in findings])` and returns. Wrapping that in an
object to carry the withheld count is the natural way to satisfy FR-006 and it
breaks three in-tree consumers on the spot, all in the ingest skill:
`.claude/skills/findings-ingest/SKILL.md:77` is the corpus dump that decides
whether a key already exists — the one the skill calls mandatory — and it selects
`open` and `regressed`, which is every feedback row there is;
`.claude/skills/findings-ingest/SKILL.md:136` runs `jq -r '.[].key' | cut -d/ -f1`
to list the categories already in use; and
`.claude/skills/findings-ingest/SKILL.md:187` runs `jq length` over the rehearsal
store. All three are read by an agent doing an ingest, and the first one failing
quietly mints duplicate keys for wants that already have them. The notice goes to
stderr, and the same story adds `--all` to all three. The tempting shortcut is to
copy the two-line list out of the 2026-08-28 draft; re-run
`git grep -n 'findings list' -- '.claude' 'docs' '*.md'` instead, because the
count has already changed once.

**Trap 12 — FR-007 cannot be proved by looking at today's probes.** Two things
make the obvious test worthless. First, it passes with an empty production diff:
none of the five entries in `REGISTRY` (`factory/doctor/probes.py:628`) files
into `feedback` today, so "assert no probe does" is already true. Second, running
a probe means calling `gather()`, and `factory/doctor/probes.py:620-622` raises
`ServiceNotAnswering` when Temporal does not answer — so a test that runs the
registry is a live-tier test wearing a unit test's clothes. The refusal belongs at
`factory/cli/doctor.py:240` — `_report_if_new`, where every probe finding passes
regardless of which probe produced it, and the test **replaces** `REGISTRY` —
`monkeypatch.setattr(_probes, "REGISTRY", [SyntheticFeedbackProbe(), SyntheticDefectProbe()])`
— rather than appending to it. Appending leaves the five real entries in the list,
so `factory/cli/doctor.py:188` — `_run_all_probes` still calls
`OrphanedKeyProbe`, `StaleWorkerProbe` and `RoadmapWedgeProbe` against the live
control plane and `StoreIntegrityProbe` against the resolved runtime root: slow
and non-hermetic offline, and a unit test reading the operator's real Temporal
when it answers. Non-vacuity comes from the synthetic probe being driven through
the real loop, not from the real probes running beside it — and the second
synthetic probe is what proves FR-007 skips rather than aborts.

And write the refusal in `factory/cli/doctor.py` only. `factory/doctor/cli.py:257`
— `_report_if_new` is an identically-named twin beside a duplicate loop at
`factory/doctor/cli.py:214` — `_check_command`; no parser reaches either, twelve
modules still import that module, and a grep for the symbol returns both. A patch
landed on the twin looks right in the diff and changes nothing at runtime.

**Trap 13 — the metavar must be derived, or US3 breaks every page guard in the
repository.** FR-003 has two halves and only one of them was measured at
drafting. T007's completion fix does nothing for `ergane findings --help`,
because argparse renders the usage metavar from `_name_parser_map` itself: see §
*The alias trap, measured*, second transcript. The tempting repair — and the one
this plan itself prescribed until 2026-09-04 — is to type the brace list out:
`metavar="{list,record,resolve,promote,triage}"`. Do not. `metavar` overrides the
rendered label and nothing else — `choices` is untouched, so nothing about
parsing breaks and the mistake is silent — while
`tests/page_holds_true.py:346` — `verbs_of` reads exactly those braces
(`tests/page_holds_true.py:339`) as the verb set before it falls back to the
indented listing (`tests/page_holds_true.py:343`), and
`tests/test_claude_md.py:81`, `tests/test_readme.py:66` and
`tests/test_onramp_html.py:59` assert every verb their page names is in that set.
US3 registers `draft` three stories later; under a hand-written metavar, `ergane
findings draft` parses, `docs/cli/findings.md` documents it, and the first page
that recommends it turns the suite red claiming the verb does not exist. Build
the string after registration from `_name_parser_map`, dropping the one parser
carrying the deprecated-name declaration T006 writes and T007 reads — one
declaration, two readers, which is trap 1 applied to the verb list. The third
transcript in § *The alias trap, measured* shows both shapes measured side by
side. Never reach for the shape that removes `record`'s `help=` to hide the
alias: that empties the verb listing of the canonical verb as well.

**Trap 14 — the live ledger will not fit in the evidence, and the constant that
refuses is not the one D-050 was written about.** 092 landed on 2026-08-30
(`c06a556`, `03451a9`) and split one constant in two.
`factory/verify/diffbounds.py:47` — the `DIFF_INPUT_LIMIT` this plan cited until
2026-09-04 — is now the size a diff is *abridged* to for the judge. What refuses
a story unjudged is `factory/verify/diffbounds.py:66`, `DIFF_REFUSAL_THRESHOLD`,
read by `factory/verify/diffbounds.py:182` — `size_refusal` and overridable from
the manifest through `factory/verify/factory_yaml.py:633` —
`_read_diff_refusal_bytes`, which may only raise it above the abridgement size
(`factory/verify/factory_yaml.py:682-690`). The number is unchanged: this
repository's `ergane.yaml` declares no `diff_refusal_bytes`, so the threshold is
the default 65,536 bytes, pasted evidence included (D-050). Measured on this tree
on 2026-09-04: `ergane findings list` is **56,899 bytes**,
`ergane findings triage` is **43,538**, `ergane findings triage --json` is
**87,193**, and `ergane findings list --json` is **119 MB** — the
`hardening/agent-worktree-boundary` rows carry multi-megabyte summaries. Any two
of the first three exceed the threshold on their own. The verification tasks
paste *excerpts and counts*, never a whole listing, and never the `--json`
document: pipe it to `jq length` and paste the number. This one bites twice,
because the open row `interpreter/size-refusal-feedback-reaches-no-retry-agent`
says a size refusal reaches no retry agent — so the ladder re-runs an identical
oversized diff until it is exhausted, and the story dies of a paste.

**Trap 15 — the identical-row test needs a frozen clock or it flakes on a second
boundary.** T001 compares every column of two rows written by two separate
invocations. `factory/cli/doctor.py:61` — `_utcnow` returns UTC at second
resolution and the write path stamps `first_seen`, `last_seen` and the
`finding_events` row from it, so two invocations either side of a tick differ in
three columns and the test fails for a reason the rename did not cause — rarely,
which is the worst frequency. The repository already solved this and the pattern
is two lines: `tests/test_ergane_findings.py:106` — `_freeze_doctor_utcnow` is an
autouse fixture that monkeypatches `factory.cli.doctor._utcnow` to a constant.
That fixture is module-local; a new `tests/test_115_us1_record_verb.py` does not
inherit it, so copy it or compare the columns with the timestamps excluded and
say which are excluded and why.

**Trap 16 — `reporter` contains `report`, and FR-001 pins the string that says
so.** The obvious spelling of US1-S3's assertion is "the substring `report`
appears nowhere in the findings help, case-insensitively". Run against a
correctly renamed tree it still fails, on
`factory/cli/doctor.py:287` — `report_parser.add_argument("--source",
default="operator", help="reporter source")`, which `ergane findings record
--help` prints as `--source SOURCE       reporter source`. FR-001 pins today's
arguments exactly, help strings included, so the remedy is not to reword the
option: scope the assertion to the surfaces US1-S3 names — the usage line, the
verb listing, the noun description — and, on `record --help`, exempt that one
line explicitly rather than by loosening the match. An assertion loosened to
`\breport\b` would pass on `reporter` and also on a usage line that still said
`report`.

## Sizing

Three stories, ascending, none near the 65,536-byte refusal
(`factory/verify/diffbounds.py:66`, `DIFF_REFUSAL_THRESHOLD`, D-050) **provided
the evidence is excerpted rather than dumped** — see trap 14.

| story | production files | test files | prose files |
| --- | --- | --- | --- |
| US1 | `factory/cli/doctor.py`, `factory/cli/completion.py` | `tests/test_ergane_env_completion.py`, one new module | `CLAUDE.md`, `docs/architecture.md`, `docs/cli/findings.md`, `.claude/skills/away-mode/SKILL.md`, `.claude/skills/findings-ingest/SKILL.md` |
| US2 | `factory/cli/doctor.py`, `factory/doctor/triage.py`, one constant module | one new module | `.claude/skills/findings-ingest/SKILL.md`, `docs/cli/findings.md` |
| US3 | `factory/cli/doctor.py` | one new module | `docs/cli/findings.md`, `docs/cli/README.md` |

US1 is a rename, a derived metavar, a six-line fix to the completion generator,
nine prose lines and one test tuple. US2 is two flags, one constant, one refusal,
one heading in two faces, three `--all` flags in a skill and one synopsis. US3 is
one verb that assembles text.

**No two stories share a production file except `factory/cli/doctor.py`, and
every one of them edits `factory/cli/doctor.py:251` — `add_findings_parser`.**
That is why the Work Graph carries two `depends_on_merged` edges rather than
leaving three correctly-independent stories to the merge queue: this repository
has the receipt, `factory/cli/init.py` took eight commits in one day and cost two
hand-merges and a rework cycle. Serialising three small stories costs about two
hours of wall clock; one hand-merge costs more than that and arrives as a
mystery. All three also touch `docs/cli/findings.md`, which is prose and would
merge cleanly, but the serialisation makes it moot.

The pasted evidence each verification task asks for is rows, excerpts and counts
— never a whole listing. That distinction is the whole margin, and it is not a
comfort claim: measured 2026-09-04, `ergane findings list` alone is 56,899 bytes
against a 65,536-byte threshold, `ergane findings triage` is 43,538 and
`ergane findings triage --json` is 87,193, so US2's evidence would have been about
240 KiB if the tasks had asked for the documents themselves. T021 names the byte
bound and lists exactly which lines it wants; T029 names the same bound for the
brief, because a finding's `notes` field runs to multiple KiB in this ledger and
FR-010 asks the brief to carry every column plus the whole trail. The store US2's
own tests build is where a full listing may be pasted from, because it holds a
handful of fixture rows rather than 520.

**US2 is the one with the thin margin, and the split to make if it refuses is
FR-007's.** It carries three disjoint production surfaces behind seven tests —
the list command's two flags and its withheld notice, the refusal on the probe
path, and the heading in both triage faces — plus three lines of
`.claude/skills/findings-ingest/SKILL.md` and two sections of
`docs/cli/findings.md`; estimated at 45-55 KiB once T021's declared 16 KiB of
evidence is counted, against the 65,536-byte refusal. Story commits on this
branch measure between 14,808 and 63,932 bytes, so that is an ordinary size
here, but it leaves about a fifth in hand rather than half. It is not split now
because all three surfaces turn on the one constant T016 substitutes, and
splitting would put that constant in a different pull request from two of its
consumers. If US2 refuses on size at dispatch, lift FR-007 — the probe-path
refusal, roughly twenty production lines and one test — into a new story
sequenced after US2 rather than reworking the trio: `factory/doctor/lane.py`
and its consumers already exist by then, so the split costs a number and
nothing else. US1, US2 and US3 keep their numbers either way.

## Dispatch hazards, for the operator running this epic

- **Delete or re-derive `workgraph.json` before any hand-run `build start` —
  this is a step, not a note.** The committed artifact beside this file was
  compiled at 8bb2d4b, before this refinement declared `implements:` on any
  story, and its three nodes read `requirement_keys: ["US1"]`, `["US2"]`,
  `["US3"]` with no FR at all (confirmed by reading the file on 2026-09-04).
  `ergane build start` resolves `<specs_root>/<epic-id>/workgraph.json` off disk,
  and those requirement keys are what select the prompt's requirement fence and
  the criteria the judge scores against, so dispatching from that artifact hands
  every node a criteria set naming no requirement. The roadmap path is safe — it
  derives fresh from the spec text — so this bites the manual dispatch only.
  Neither the refinement nor the repair workflow is permitted to write or delete
  it. Run `ergane spec derive specs/115-the-ledger-takes-what-is-not-yet-a-defect
  --target-repo "$PWD"` and confirm each node's `requirement_keys` ends in its own
  FRs, or delete the file, before starting the epic by hand. Read the open row
  `cli/spec-derive-json-rewrites-the-committed-artifact` first: `--json` presents
  as a read and still writes the artifact, so it is the wrong flag to check with.
- **Spec `152-the-findings-channel-accepts-an-honest-report` is the other draft
  on this file.** It was written the same day against the same commit, it
  declares `doctor/the-credential-sweep-on-findings-report-refuses-a-note-that-names-the-repositorys-own-epic`
  in its `fixes:`, and it edits the findings write path beside the credential
  refusals FR-001 pins at `factory/cli/doctor.py:458-465` and
  `factory/cli/doctor.py:482-485`. Neither spec fixes the other's defect and
  neither names a dependency on the other, so the ordering is the operator's:
  land this spec's US1 first and 152 rebases onto a renamed verb, or land 152
  first and US1's prose sweep has one more file to touch. Running both epics
  concurrently contends on `factory/cli/doctor.py:251` — `add_findings_parser`,
  which is the one thing the Work Graph already refuses to do inside this spec.
  152's own prose quotes `ergane findings report` throughout and survives FR-004's
  guard only because that guard excludes `specs/`.
- **US1 edits `CLAUDE.md`**, which `tests/test_claude_md.py` holds to the rule
  that every command it names must resolve, through
  `tests/page_holds_true.py:301` — `extract_commands`. Renaming the verb without
  renaming the row in that table fails the gate — which is the guard working, and
  worth knowing before it reads as a mystery.
- **Do not run `scripts/gate-commit` while an attempt is in flight.**
- **This spec's own key convention is `feedback/<slug>`,** and the lane is
  already populated: 23 open rows on 2026-09-04. Rows filed before US2 lands are
  still correct; they simply appear in the default list until the filter exists.

## Verification the operator will run, independent of the gate

Per constitution VIII and D-037 the judge sees the diff and the criteria only, so
runtime evidence is committed as pasted output. Beyond that, and in order:

1. Against a scratch store, file one row with `ergane findings record` and one
   with `ergane findings report`, and confirm by reading both rows that the
   second differs only in nothing. Confirm the deprecation line arrives on
   stderr by redirecting stdout to a file and watching the terminal.
2. Run `ergane completion bash | grep 'findings)'` and confirm the emitted verb
   list names `record` and not `report`. This is the assertion trap 4 is about,
   run by hand against the real generator rather than a fixture. Then read
   `ergane findings --help` and confirm the brace list in the usage line holds
   every verb the parser has except `report` — after US3, that includes `draft`,
   which is trap 13's whole point.
3. Against the **live** ledger, run `ergane findings list` and confirm the
   withheld line names 23 or more rows and the flag that shows them; then
   `--category feedback`; then `--all`; then
   `ergane findings list --json | jq length` against `--all` and without it, and
   confirm the two numbers differ by exactly the withheld count.
4. Run `ergane findings triage` and `ergane findings triage --json` over the live
   ledger and confirm the feedback rows appear under their own heading in both,
   that no feedback row is listed under another class's heading, and that the
   footer's `total` and `classified` still agree.
5. After US3 lands, once, deliberately: take a want that has been sitting in
   cross-session memory rather than in the tree, file it with
   `ergane findings record --category feedback --severity info`, run
   `ergane findings draft` over it, and hand the brief to a drafting session.
   Read what comes back against what `ergane findings promote` alone would have
   produced.

The gate can prove the verb renamed, the lane filtered, and the brief assembled.
It cannot prove the brief is *useful*, because usefulness is a property of what a
drafter does with it. If the difference at step 5 is small, the schedule this
spec deferred should stay deferred, and the honest conclusion is that the queue
is worth having and the drafter is not yet worth automating.
