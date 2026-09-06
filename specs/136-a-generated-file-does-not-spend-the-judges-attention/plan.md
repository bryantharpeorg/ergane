# Implementation Plan: a generated file does not spend the judge's attention

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## What already exists, and where

**One patch, two readers, no pathspec on either.** The bytes are produced by
`factory/workgraph/worktree.py:1496` — `diff`, and its docstring at
`factory/workgraph/worktree.py:1505-1507` names the only escape a generated file
has today:

```
    changes are one patch; ignored files stay out, so a target repo's
    `.gitignore` is what keeps generated noise from reaching the judge.
```

Its callers are exactly two — `factory/verify/diffcheck.py:390`, inside
`factory/verify/diffcheck.py:376` — `judge_input`, and
`factory/activities/agent_activities.py:735`, inside
`factory/activities/agent_activities.py:718` — `read_worktree_diff`. The first
feeds the refusal, the second feeds the judge's prompt. Neither passes a
pathspec, and there is no third caller.

**The one measurement the refusal takes.** `factory/verify/diffbounds.py:137` — `assembled`
is six lines and sums everything:

```python
    preamble, sections = split_sections(diff_text)
    if not sections:
        sections = [DiffSection(None, preamble, *count_changes(preamble))]
        preamble = ""

    whole = file_listing(sections) + preamble + "".join(s.text for s in sections)
    return len(whole.encode("utf-8")), sections
```

`factory/verify/diffbounds.py:182` — `size_refusal` compares that total to
`DIFF_REFUSAL_THRESHOLD` (`factory/verify/diffbounds.py:66`), and
`factory/verify/diffbounds.py:159` — `abridgement` compares the same total to
`DIFF_INPUT_LIMIT` (`factory/verify/diffbounds.py:47`). Read the docstring at
`factory/verify/diffbounds.py:140-145` before touching any of the three: it
states, in the tree's own words, that the refusal, the abridgement record and
`prepare_diff` all weigh the *same assembly*, and that two of them weighing
something else "would disagree exactly at the margin where one elides and the
other calls the diff whole (092 trap 3)". That sentence is the constraint this
whole spec is built around. Three call sites carry it:
`factory/verify/diffcheck.py:253` takes the refusal and
`factory/verify/diffcheck.py:262` takes the abridgement record, from the one
patch read at `factory/verify/diffcheck.py:248`.

**What `size_refusal` names, and where it is measured from.** Past the
comparison it builds `largest_files` from the *section bodies* — the sort at
`factory/verify/diffbounds.py:212` and the list comprehension at
`factory/verify/diffbounds.py:220-223` read `section.size`, which is the body's
own length (`factory/verify/diffbounds.py:80` — `DiffSection`, whose `size`
property is at `factory/verify/diffbounds.py:88-90`). `total_bytes` and
`largest_files` therefore come from one call today and agree by construction; the
moment FR-011 narrows only the first of them they stop agreeing. That is trap 16.

**The section model both modules share.** `factory/verify/diffbounds.py:80` — `DiffSection`
carries `path`, `text`, `added`, `removed` and a `size` property;
`factory/verify/diffbounds.py:93` — `split_sections` builds them and
`factory/verify/diffbounds.py:112` — `count_changes` derives the counts **from
the full section text**. `factory/verify/diffbounds.py:125` — `file_listing`
renders one line per named section from those counts. The judge module does not
own a second copy: `factory/verify/judge.py:63` imports `DiffSection`,
`count_changes`, `file_listing` and `split_sections` from `diffbounds` under
private aliases, with a comment at `factory/verify/judge.py:55-60` saying why.
One classification therefore reaches both readers. **The import runs one way
only**, and that is a fence rather than a habit: `factory/verify/diffbounds.py:9-14`
states that the judge is the component's only LLM edge and that exactly one
module may import it, and
`tests/test_verification_sweep.py:879` — `test_exactly_one_module_imports_the_judge`
asserts that as an exact set over every `factory/verify/*.py`
(`tests/test_verification_sweep.py:134-137`) against the single name
`JUDGE_CALLER` (`tests/test_verification_sweep.py:146`), which is
`factory/activities/verify_activities.py`. Anything both modules must agree on
byte-for-byte therefore lives in `diffbounds` and is imported by `judge`, never
the other way round. That is trap 15, and it decides where this spec's stub
renderer goes.

**The allocation, and what it costs today.** `factory/verify/judge.py:473` — `prepare_diff`
builds `whole` at `factory/verify/judge.py:493`, returns it
untouched when it fits, and otherwise hands every section's size to
`factory/verify/judge.py:515` — `_allocate` at `factory/verify/judge.py:501`.
`_allocate` splits the allowance in proportion to size with a floor of
`SMALL_FILE_FLOOR` (`factory/verify/judge.py:121`), and
`factory/verify/judge.py:542` — `_render_section` spends each grant on that
file's head and tail. Re-measured on 2026-09-04 by running it:

```
$ uv run python -c "from factory.verify.judge import _allocate; ..."
SMALL_FILE_FLOOR 2048
lockfile grant 24076 pct 37.0
source grants [2048]
source total 40960
sum 65036
```

Twenty 5,120-byte source sections plus one 102,400-byte generated section, with
an allowance of 65,036: the generated section takes 24,076 bytes, every source
section is cut to the floor, and the source bytes shown fall from 65,036 to
40,960. The same call with the generated size removed — which is what US2-S1's
Then is written against — was run on the same tree:

```
$ uv run python -c "from factory.verify.judge import _allocate; print(_allocate([5120]*20, 65036))"
[3251, 3252, ...]   # four grants of 3251, sixteen of 3252, sum 65036
```

The twenty source sections divide the whole allowance, 3,251 or 3,252 bytes
each, so the source bytes shown rise from 40,960 to 65,036. They are **not**
carried whole — every grant is below the 5,120-byte section size, so
`factory/verify/judge.py:542` — `_render_section` still renders each as head and
tail and `PreparedDiff.truncated` is still true for this fixture. That is the
correct post-fix outcome, and trap 17 is why it is written down here rather than
left to be discovered by a failing test.

**Where the elision must be disclosed.** `factory/verify/judge.py:261` — `PreparedDiff`
carries `text` and `truncated` (`factory/verify/judge.py:265`),
and `truncated` becomes `truncated_input` on the prompt
(`factory/verify/judge.py:286`) and from there onto the verdict and the stored
row. On the refusal side the record types are
`factory/verify/models.py:444` — `DiffSizeRefusal`,
`factory/verify/models.py:467` — `DiffAbridgement` and
`factory/verify/models.py:429` — `DiffFileSize`, all three carried on
`factory/verify/models.py:509` — `OutputCheck`, which
`factory/verify/diffcheck.py:172` — `check_output` fills at
`factory/verify/diffcheck.py:252-256` and `factory/verify/diffcheck.py:262`.
Filling the record is only half of writing it: `OutputCheck` is serialised field
by field by a hand-written whitelist at
`factory/verify/store.py:1129` — `_output_check_to_dict`
and read back one key at a time at
`factory/verify/store.py:1214` — `_output_check_from_dict`. A field added to the
dataclass and not to those two functions is dropped on write and absent on read,
and every operator-facing reader works from a loaded row — the rendering at
`factory/cli/nouns/build.py:1446` and the retry prompt at
`factory/workgraph/prompt.py:956`, which quotes
`factory/workgraph/prompt.py:975` — `_size_listing` verbatim into the next
attempt's brief. That is trap 14, and the same two readers are half of trap 16.

**The manifest vocabulary, and the tuple to put the key in.**
`_TOP_LEVEL_KEYS` is at `factory/verify/factory_yaml.py:109` and
`_V2_TOP_LEVEL_KEYS = _TOP_LEVEL_KEYS + ("ladder", "verify")` at
`factory/verify/factory_yaml.py:134`;
`factory/verify/factory_yaml.py:269` — `_reject_unknown_keys` picks between them
by version at `factory/verify/factory_yaml.py:270`. The reader list is inside
`factory/verify/factory_yaml.py:199` — `parse_factory_config`, where
`_read_writes` is called at `factory/verify/factory_yaml.py:217` and
`_read_diff_refusal_bytes` at `factory/verify/factory_yaml.py:224`. The two
readers worth modelling on are
`factory/verify/factory_yaml.py:633` — `_read_diff_refusal_bytes`, which is 092's
own dial and shows the refusal shape, and
`factory/verify/factory_yaml.py:694` — `_read_caches`, which is the list-shaped
reader and shows how an absent optional key becomes `()`.

**The pin, and every hop it already travels — the route forks, and the fork is
the hop a description leaves out.**
`factory/verify/factory_yaml.py:1068` — `load_loop_config` is the dispatch-time
read; its signature is at `factory/verify/factory_yaml.py:1070` and its return at
`factory/verify/factory_yaml.py:1086`. Its docstring at
`factory/verify/factory_yaml.py:1079-1083` states the rule this spec inherits:
a value that decides a verdict is read "from the declaration that owns it, once,
here (constitution IX)". From there `diff_refusal_bytes` travels through
`factory/activities/roadmap_activities.py:821` — `ReadLoopConfigResult` (field at
`factory/activities/roadmap_activities.py:833`, filled at
`factory/activities/roadmap_activities.py:858` and
`factory/activities/roadmap_activities.py:866`) and then **into two dispatch
paths, both of which must be wired**:

- the roadmap's own child start.
  `factory/roadmap/workflow.py:1170` — `_dispatch` awaits that activity result
  and builds the child's `EpicInput` at `factory/roadmap/workflow.py:1296`,
  naming the pinned value at `factory/roadmap/workflow.py:1303`. **This is the
  factory's normal dispatch path**: the roadmap schedule fires it unattended, so
  an epic no operator hand-started reaches its judge through this line and no
  other.
- the hand-started CLI. `factory/cli/nouns/build.py:826` unpacks the read,
  `factory/cli/nouns/build.py:845` passes it to the helper whose signature is at
  `factory/cli/nouns/build.py:890` (with the "this caller read no manifest"
  default at `factory/cli/nouns/build.py:915`), and
  `factory/cli/nouns/build.py:951` names it on the `EpicInput` constructed at
  `factory/cli/nouns/build.py:931`.

Both land on `factory/workgraph/workflow.py:532` — `EpicInput` at
`factory/workgraph/workflow.py:595`. Copy that route exactly, both forks:
eleven lines across five files, and it is the whole of FR-004. `grep -n 'EpicInput(' factory/` returns a
third construction site, `factory/workgraph/cli.py:675`; it carries no 092 pin
either, it is the legacy entry point, and adding the field there is not what
US1-S5 asks for. `load_loop_config` returns a 3-tuple today, so widening it edits
five unpackings, two in production
(`factory/activities/roadmap_activities.py:858`,
`factory/cli/nouns/build.py:826`) and three in landed tests
(`tests/test_092_manifest_threshold.py:186`,
`tests/test_092_manifest_threshold.py:233`,
`tests/test_023_us2_dispatch_pin.py:823`).

**The two last hops, one per consuming story.** For the refusal:
`factory/activities/verify_activities.py:294` — `CheckOutputInput` carries
`diff_size_limit` at `factory/activities/verify_activities.py:323` and passes it
at `factory/activities/verify_activities.py:344`; the workflow builds it at
`factory/workgraph/workflow.py:2607` and `factory/workgraph/workflow.py:2609`,
naming the pinned value at `factory/workgraph/workflow.py:2619`. For the judge:
`factory/activities/verify_activities.py:399` — `RunJudgeInput` is handed to
`factory/activities/verify_activities.py:430` — `run_judge`, which calls
`factory/verify/judge.py:752` — `run_judge` at
`factory/activities/verify_activities.py:444`; the workflow reads the diff at
`factory/workgraph/workflow.py:2627` and constructs the judge input at
`factory/workgraph/workflow.py:2923`, inside
`factory/workgraph/workflow.py:2901` — `_score` — **not** inside
`factory/workgraph/workflow.py:2708` — `_judge`, which reaches it only through
`self._score(...)` at `factory/workgraph/workflow.py:2771`. Edit `_score`; read
`_judge` for the retry loop around it. `factory/verify/judge.py:307` — `build_prompt`
calls `prepare_diff` at `factory/verify/judge.py:352`.

**The only exclusion list in the tree, and it is not this one.**
`factory/workgraph/detector.py:70` is `EXCLUDED_DIR_NAMES` and
`factory/workgraph/detector.py:73` is `EXCLUDED_SUFFIXES`; the comment above them
at `factory/workgraph/detector.py:66` describes generated content, which is why
an implementer will find them. They govern the runtime-root snapshot, never the
diff. Do not extend them and do not import them.

## Traps

**Trap 1 — the ledger says `regressed` and nothing regressed; it was never
built.** `specs/092-the-diff-ceiling-and-the-evidence-doctrine-agree/spec.md:19`
and `specs/092-the-diff-ceiling-and-the-evidence-doctrine-agree/spec.md:20`
declare both keys under `fixes:`, while the same file's prose at
`specs/092-the-diff-ceiling-and-the-evidence-doctrine-agree/spec.md:36-38`
argues against the lockfile half in so many words — "exempting lockfiles fixes
the instance and hides the general problem". All eight of 092's FRs are about
splitting the constants and adding the dial. The store then flipped the row to
`regressed` on the next sighting because a spec that did not close the key had
closed it. The wrong move an implementer will make is to treat `regressed` as an
invitation to bisect for a fix that came undone. There is nothing to find. This
needs an implementation.

**Trap 2 — 092 FR-008 forbids exactly what FR-007 and FR-011 require, and this
spec supersedes it in writing.**
`specs/092-the-diff-ceiling-and-the-evidence-doctrine-agree/spec.md:250-252`
reads "Every story MUST leave `prepare_diff`'s abridgement algorithm ...
unchanged, and MUST NOT exempt any path by name or pattern from the measured
size." An implementer who reads 092 while working here — and they should, it is
the nearest neighbour — will find a landed, attested requirement that forbids
this story. The supersession is stated in spec.md § "What this spec is not" and
that section is the authority. (092's own inline citation of `prepare_diff` in
that sentence has rotted: the function now lives at
`factory/verify/judge.py:473` — `prepare_diff`.)

**Trap 3 — the three measurements must move together, and the stub is weighed by
all of them.** `factory/verify/diffbounds.py:140-145` says the refusal, the
abridgement record and `prepare_diff` weigh the same assembly, and that a
disagreement matters "exactly at the margin where one elides and the other calls
the diff whole". So the elision in `prepare_diff` (FR-007) must be
unconditional — FR-008 — and the exclusion in `assembled` (FR-011) must be the
same rule over the same sections. There are two tempting shortcuts and both
recreate 092 trap 3:

- eliding only on the over-limit path in `prepare_diff`, because that is where
  the abridging code already lives. An under-limit diff would then be shown whole
  while the refusal weighed less than it showed.
- making `assembled` drop the generated section entirely — body *and* stub —
  while `prepare_diff` still emits the stub. The two totals then differ by the
  stub bytes plus the listing's generated marker, permanently, and the difference
  bites at the margin: `tests/test_092_abridged_is_recorded.py:141` asserts
  `prepare_diff(patch).truncated is record.abridged`, which goes false for a
  pattern-declaring repository whose diff lands within a stub's length of the
  limit.

FR-011 answers the question the spec is otherwise silent on: **the stub and the
marker are weighed by both sides**, because there is one assembly. `assembled`
substitutes the stub for the body; it does not delete the section. And
`factory/verify/diffcheck.py:262` — the `abridgement(patch)` call — must be given
the same patterns as `factory/verify/diffcheck.py:253`, or the record over-reports
against a prompt that was never abridged. Trap 15 is the third shortcut, and it
is the one a task list can hand you without your noticing.

**Trap 4 — compute the classification from the section's real text, elide only at
render time.** `factory/verify/diffbounds.py:112` — `count_changes` derives
`added` and `removed` from the full section text, and
`factory/verify/diffbounds.py:125` — `file_listing` renders from those counts.
An implementer who "elides" by rewriting the section's `text` before the section
is constructed gets a listing that reports `+0 -0`, which tells the judge the
lockfile did not change — strictly worse than today, and it will pass every test
that only asserts the total. FR-005 requires the real counts in the listing;
assert them against a fixture whose lockfile hunks are known.

**Trap 5 — register the key in `_V2_TOP_LEVEL_KEYS` only, and that edit lands on
a landed invariant test nobody would go looking for.** `diff_refusal_bytes` is
registered in `_TOP_LEVEL_KEYS` (`factory/verify/factory_yaml.py:120`), the v1
list — and that tuple is also what `ergane init`'s interview asks about:
`tests/test_forge_manifest.py:333` asserts `set(_PROMPTS) == set(_TOP_LEVEL_KEYS)`.
Registering `generated_paths` there fails that test until an interview prompt is
added too, which widens this spec into `ergane init`. Register it in
`_V2_TOP_LEVEL_KEYS` (`factory/verify/factory_yaml.py:134`) instead, where
`ladder` and `verify` live: `_KNOWN_KEYS` (`factory/cli/init.py:511`) *is* that
tuple, so `ergane init` carries the key forward
(`factory/cli/init.py:783`) and rewrites it through `yaml.safe_dump`
(`factory/cli/init.py:1076`) with no edit to `factory/cli/init.py` at all, and
FR-001's v1 refusal falls out of `factory/verify/factory_yaml.py:270` for free.

**One edit does follow, and it is declared scope rather than a surprise.** 120
FR-006 pinned the other half of that arrangement as an invariant:
`tests/test_120_rewrite_carries_forward.py:310` reads
`carried = [key for key in init_module._KNOWN_KEYS if key not in _TOP_LEVEL_KEYS]`
at `tests/test_120_rewrite_carries_forward.py:308` and asserts
`carried == ["ladder", "verify"]`. That expected value is an *enumeration of the
v2-only keys*, not a guard on anything this spec does, so registering a third v2
key makes it stale by construction and it must gain `"generated_paths"` — a list
comparison, so the order matters and the new key goes last, after `"verify"`,
because `_V2_TOP_LEVEL_KEYS` is built by concatenation. The declared gate is
`uv run pytest -q` (`ergane.yaml:34`), so this fails on US1's first gate run if it
is not done. Two escapes will look available from there and both are wrong:
weakening the assertion to a set comparison strips 120 FR-006 of the ordering it
was written to pin, and retreating to `_TOP_LEVEL_KEYS` is what the first half of
this trap forbids and fails `tests/test_forge_manifest.py:333` instead. Edit the
expected list; change nothing else in that file. The second assertion at
`tests/test_120_rewrite_carries_forward.py:311` —
`assert not set(carried) & set(init_module._PROMPTS)` — stays true untouched,
because this spec adds no interview prompt.

**Trap 6 — do not declare the key in this repository's own `ergane.yaml`.** The
config gate parses a node's manifest with the **worker's installed parser**, not
the worktree's.
`tests/test_forge_manifest.py:339` — `test_this_repositorys_own_manifest_does_not_spend_the_key`
records what that cost when 049 hit it, and `ergane.yaml`'s own header comment
records what it cost 020/US1: four deaths. A diff that both teaches
`generated_paths` and writes it into `ergane.yaml` is refused at `CONFIG_ERROR`
in 0.0s, before any gate command runs, on every attempt of every rung, forever.
FR-006 and its mirror test exist so the temptation is met as declared scope.
Declaring it here is an operator commit after the story lands and the worker
restarts.

**Trap 7 — do not add a pathspec to `worktrees.diff`, however tempting the
one-line fix looks.** `factory/workgraph/worktree.py:1496` — `diff` has exactly
two callers (`factory/verify/diffcheck.py:390` and
`factory/activities/agent_activities.py:735`), so excluding the file there would
appear to fix both halves at once. It would also delete the file from the patch
entirely: the section never exists, so `file_listing` cannot name it, the counts
are gone, and the judge is not told a dependency changed. FR-005 requires the
opposite. Exclude the *body* from two measurements; never the *file* from the
patch.

**Trap 8 — the lockfile cannot take the escape the docstring offers, and the
remedy is not to send the operator after it.**
`factory/workgraph/worktree.py:1505-1507` says a target repo's `.gitignore` is
what keeps generated noise out. A `package-lock.json` must be tracked for
`npm ci` to be reproducible, and the repository that reported this deliberately
commits it. "Gitignore your lockfile" is not a remedy and must not appear in any
message this story writes.

**Trap 9 — a declared pattern that matches nothing is silent, and the record is
the only mitigation.** Unlike 128's boundary-only list there is no declared set
to cross-check a pattern against — a diff simply may not touch a lockfile — so a
misspelled pattern exempts nothing while reading as though it exempts something.
FR-012's disclosure is what makes that visible on the attempt where it mattered.
Do not "improve" on it by refusing a pattern that matched nothing in one diff:
that would refuse every ordinary story in a repository that declared a lockfile.

**Trap 10 — the patterns are pinned, never read from the node's worktree.**
`factory/verify/factory_yaml.py:1079-1083` states the rule for the sibling dial:
a value that decides a verdict is read from the declaration that owns it, once,
at dispatch. A node that could write `generated_paths: ["**"]` into its
worktree's manifest would exempt its entire diff from the refusal and from the
judge — voting on its own verdict, with a pattern language. Thread the value
along the route `diff_refusal_bytes` already takes
(`factory/verify/factory_yaml.py:1086`,
`factory/activities/roadmap_activities.py:858`,
`factory/activities/roadmap_activities.py:866`,
`factory/roadmap/workflow.py:1303`,
`factory/cli/nouns/build.py:826`, `factory/cli/nouns/build.py:845`,
`factory/cli/nouns/build.py:951`,
`factory/workgraph/workflow.py:595`) and nowhere else — **both** forks. The one
that gets left out is the roadmap's, because a route recited from the CLI's
`ergane build start` reads complete without it, and it is the wrong one to leave
out: the schedule dispatches through
`factory/roadmap/workflow.py:1170` — `_dispatch` unattended, so wiring only the
CLI ships a manifest key that every hand-run epic honours and every scheduled
epic ignores — green tests, green gate, the outage intact wherever the factory
actually runs. That is trap 11's failure shape landing on a hop rather than on a
seam. US1-S5 is the test that catches it; it needs two manifests on disk and an
assertion over the `EpicInput` each path actually starts the epic with —
`tests/test_023_us2_dispatch_pin.py:731` — `test_roadmap_dispatch_reads_config_per_child`
captures the roadmap's child start and is the shape to copy.

**Trap 11 — the declaration must leave the schema, in both consuming stories.**
FR-010 and FR-013. An implementer who adds `generated_paths` to `FactoryConfig`,
gives `prepare_diff` and `assembled` a keyword argument with an empty default,
writes every test by passing patterns in by hand and stops there gets a green
gate, a passing judge, and a manifest key production never reads — the outage
intact behind two landed stories. US2-S4 and US3-S5 may name the patterns only
on the activity input
(`factory/activities/verify_activities.py:399` — `RunJudgeInput` and
`factory/activities/verify_activities.py:294` — `CheckOutputInput`), which is
what makes them unsatisfiable by the shortcut.

**Trap 12 — `diff_check` is mandatory and the refusal is not on the table, but
read the branch before writing a test against it.**
`factory/verify/factory_yaml.py:958-963` refuses a manifest that declares a
`verify:` list without `diff_check` in it. It does **not** fire for a manifest
with no `verify:` block: `factory/verify/factory_yaml.py:915` — `_read_verify`
returns the default order at `factory/verify/factory_yaml.py:923-924`, and that
default (`factory/verify/models.py:340`) already contains `diff_check`. A test
written from the words "a manifest that omits `diff_check`" fails against today's
tree before any change; US3-S4 names `verify: [gates, judge]` for that reason.
When a story cannot get its own bytes under the threshold the cheapest-looking
moves are to make the check optional, to raise the default, or to widen
`DIFF_REFUSAL_THRESHOLD` (`factory/verify/diffbounds.py:66`). All three are out
of scope and FR-014 asserts against them.

**Trap 13 — the sibling defects that wear this one's message and this one's
constant.**
`verify/the-diff-size-check-measures-a-stacked-node-against-a-base-that-cannot-contain-its-declared-dependency`
is a separate open critical row: a dependent node is measured against a base that
cannot contain its predecessor's landed bytes, so it is charged for work it did
not do. It produces the same refusal message and the same `largest_files` shape,
and an implementer reading the ledger will find it. It is a different rule with a
different owner — "bytes the node did not write" is not "bytes no human wrote" —
and widening this spec to cover it would produce an exemption nobody can reason
about. It shares one live diagnostic with
`verify/agents-are-told-to-measure-diff-size-with-the-wrong-ruler`, also open and
critical: *a healthy refusal sits within a kilobyte of*
`git diff <landing-branch>...HEAD` — measured at 757 and roughly 850 bytes on two
nodes, which is how a measurement fault was told apart from a genuinely oversized
story. **This spec makes that heuristic false** for any repository declaring
`generated_paths`: the gap becomes the excluded body, tens of kilobytes rather
than one. Neither row is declared under `fixes:` here and neither is fixed here.
FR-012's disclosure is what restores the subtraction — the excluded paths and
their bytes, on the record — so write it as the operator's instrument rather than
as a nicety, and do not shorten it to a single count.

**Trap 14 — a record field that is not serialised is a disclosure no operator can
read.** `OutputCheck` is written to the store field by field:
`factory/verify/store.py:1129` — `_output_check_to_dict` lists `size_refusal` and
`abridgement` explicitly, and
`factory/verify/store.py:1214` — `_output_check_from_dict` reads them back one by
one. A new FR-012 field added
only where `check_output` fills it is dropped on write and absent on read, and
`factory/cli/nouns/build.py:1446` and `factory/workgraph/prompt.py:956` both
render from a *loaded* row — so the cheapest implementation that satisfies an
in-memory assertion lands a disclosure nobody will ever see, which is trap 1's
shape repeated inside this spec. 092 set the standard the other way and it is the
model to copy: `tests/test_092_abridged_is_recorded.py:148` asserts the loaded
record equals the written one, and `tests/test_092_abridged_is_recorded.py:274`
asserts the serialised document. Absent must read as "nothing was excluded", the
way `abridgement` absent reads as "nobody measured", so rows written before this
story load unchanged.

**Trap 15 — the stub renderer has exactly one legal home, and the obvious one is
not it.** The stub is the only thing in this spec both measurements must produce
identically to the byte (FR-011), so it must be one function. The instinctive
place to put it is beside
`factory/verify/judge.py:542` — `_render_section`, where a file's rendering
already lives. That placement is unavailable: `factory/verify/diffbounds.py:9-14`
declares the fence — the judge is the component's only LLM edge, and exactly one
module in the component may import it — and
`tests/test_verification_sweep.py:879` — `test_exactly_one_module_imports_the_judge`
enforces it as an **exact set** over every file under `factory/verify/`
(`tests/test_verification_sweep.py:134-137`), so `diffbounds` importing `judge`
turns the declared gate red on a landed invariant. It is also an import cycle:
`factory/verify/judge.py:63` already imports four names *from* `diffbounds`.
Three recoveries will present themselves once US2 has merged with the stub in the
wrong module, and all three are worse than getting it right first:

- import `judge` from `diffbounds` — fails
  `tests/test_verification_sweep.py:879` and cycles at import time;
- re-implement the stub string inside
  `factory/verify/diffbounds.py:137` — `assembled` — two implementations of the
  one rule that must agree to the byte, which is trap 3's second bullet, and it
  lands **green** because US3-S6's fixture only has to cross the limit because of
  the generated body: a few bytes of stub drift will not flip `abridged` against
  `truncated` there;
- move US2's landed function into `diffbounds` from inside US3 — which reopens a
  merged story's file and contradicts § Sizing.

So FR-007 puts the single stub function in `factory/verify/diffbounds.py`, beside
`factory/verify/diffbounds.py:125` — `file_listing`, and `prepare_diff` reaches
it exactly the way it already reaches `_file_listing`: one more name in the
private-alias import at `factory/verify/judge.py:63`. US2 owns that file for the
length of one function; US3 calls it.

**Trap 16 — narrowing the total without narrowing what the record names produces
a refusal that contradicts itself.** `size_refusal` takes `total_bytes` and
`largest_files` from the same call today —
`factory/verify/diffbounds.py:208` unpacks `assembled`, and
`factory/verify/diffbounds.py:212` and
`factory/verify/diffbounds.py:220-223` rank the same sections by `section.size`,
the body's own length. Narrow only the total, as FR-011's first sentence does,
and a refusal in a pattern-declaring repository writes a record whose
`largest_files` names `package-lock.json` at 53,176 bytes that its own
`total_bytes` never counted — one record, two rulers. Read the arithmetic before
writing an assertion about it. `largest_files` exists only when the refusal
fires: `factory/verify/diffbounds.py:209` returns `None` for any total at or
under the limit. So the striking pairing — 53,176 named beside a `total_bytes` of
about 17,500, the container run's narrowed total — is reachable only where an
operator lowered `diff_refusal_bytes` below the generated section's own size. At
the default threshold the fault is quieter and is about the **name**, not the
number: the entry names a body nobody weighed, while the total, being above the
threshold, is the larger of the two. US3-S7 asserts the name for exactly that
reason and deliberately asserts no inequality.

Either way the fault does not stop at the record.
`factory/workgraph/prompt.py:956` quotes
`factory/workgraph/prompt.py:975` — `_size_listing` into the next attempt's
brief, so the ladder would tell the agent to go and shrink a file that no longer
costs it anything. That is
`verify/agents-are-told-to-measure-diff-size-with-the-wrong-ruler` — the open
critical row trap 13 declines to fix — re-created by this spec's own output, on
exactly the attempts it targets. FR-011's last sentence is the answer: build
`largest_files` from the narrowed measurement, so an uncounted body is never
named as what spent the allowance, and US3-S7 asserts it. The disclosure of what
*was* excluded belongs on FR-012's field, with its real byte count, where it does
not have to share a unit with a total it was left out of.

**Trap 17 — the elision does not make an over-limit diff fit, and an acceptance
criterion written as though it did is unsatisfiable.** What FR-007 takes out of
`factory/verify/judge.py:515` — `_allocate`'s input is the generated file's
*size*, not the pressure on the allowance. US2-S1's fixture is twenty 5,120-byte
source sections against a 65,036-byte allowance: 102,400 bytes of source, so
`factory/verify/judge.py:473` — `prepare_diff` still takes the over-limit path at
`factory/verify/judge.py:501` and `_allocate` still cuts. Measured at 602a92c,
`_allocate([5120]*20, 65036)` returns 3,251 and 3,252 — every grant below the
5,120-byte section size, so `factory/verify/judge.py:542` — `_render_section`
renders every one of them as head and tail. The win this story books is the
ratio, not wholeness: 65,036 source bytes shown instead of 40,960, none of the
allowance spent on bytes no human wrote. Two moves follow from misreading that,
and the second is the expensive one:

- shrinking the fixture until the source fits — twenty 2,560-byte sections total
  51,200, under the allowance — which makes "carried whole" true and proves
  nothing, because `prepare_diff` then returns at
  `factory/verify/judge.py:495` and `_allocate` is never called at all;
- contorting the production code to satisfy the impossible Then: raising
  `SMALL_FILE_FLOOR` (`factory/verify/judge.py:121`), carrying non-generated
  sections whole regardless of the allowance, or exempting source from the
  allocation. Each changes the abridger for every repository in the world,
  declared patterns or not, and each is a rewrite of the algorithm 092 FR-008
  fenced — the one thing this spec supersedes narrowly and on purpose.

Keep the fixture; assert the grants.

## Sizing

US1 touches `factory/verify/factory_yaml.py` (one tuple entry, one reader, one
line in `parse_factory_config`, one element on `load_loop_config`'s return),
`factory/verify/models.py` (one field on `FactoryConfig`),
`factory/verify/diffbounds.py` (the classification on `DiffSection`, a matcher,
and the listing marker), `factory/activities/roadmap_activities.py`,
`factory/roadmap/workflow.py` (one line, at `factory/roadmap/workflow.py:1303` —
the roadmap's own child start, the fork a CLI-shaped route description leaves
out), `factory/cli/nouns/build.py` (four lines:
`factory/cli/nouns/build.py:826`, `factory/cli/nouns/build.py:845`,
`factory/cli/nouns/build.py:890` and `factory/cli/nouns/build.py:951`) and
`factory/workgraph/workflow.py` (one field and one argument). Its tests live in a
new module beside
`tests/test_forge_manifest.py`'s shape, plus the two mirror assertions FR-006 and
FR-005 require. Four landed test files also change by one line each, and they are
declared scope rather than collateral: the enumeration at
`tests/test_120_rewrite_carries_forward.py:310` (trap 5) and the three 3-tuple
unpackings of `load_loop_config` at `tests/test_092_manifest_threshold.py:186`,
`tests/test_092_manifest_threshold.py:233` and
`tests/test_023_us2_dispatch_pin.py:823`.

US2 touches `factory/verify/diffbounds.py` (the one stub renderer, beside
`factory/verify/diffbounds.py:125` — `file_listing`, and its name added to the
private-alias import at `factory/verify/judge.py:63` — trap 15 is why it lives
here and not in the judge), `factory/verify/judge.py` (the filtered call to
`_allocate` and the parameter on `prepare_diff`,
`factory/verify/judge.py:307` — `build_prompt` and
`factory/verify/judge.py:752` — `run_judge`),
`factory/activities/verify_activities.py` (one field on `RunJudgeInput`, one
argument at `factory/activities/verify_activities.py:444`) and
`factory/workgraph/workflow.py` (one line at
`factory/workgraph/workflow.py:2923`, inside
`factory/workgraph/workflow.py:2901` — `_score`).

US3 touches `factory/verify/diffbounds.py`
(`factory/verify/diffbounds.py:137` — `assembled`,
`factory/verify/diffbounds.py:159` — `abridgement`, which shares it, and
`factory/verify/diffbounds.py:182` — `size_refusal`, whose `largest_files` is
built from the narrowed measurement — trap 16; it calls US2's stub function, it
does not write a second one),
`factory/verify/diffcheck.py` (`factory/verify/diffcheck.py:172` — `check_output`,
at both `factory/verify/diffcheck.py:253` and
`factory/verify/diffcheck.py:262`;
`factory/verify/diffcheck.py:342` — `diff_size_refusal` is a parallel public seam
with **no production caller** — update its signature for consistency, never as
the route), `factory/verify/models.py` (the disclosure fields),
`factory/verify/store.py`
(`factory/verify/store.py:1129` — `_output_check_to_dict` and
`factory/verify/store.py:1214` — `_output_check_from_dict`, trap 14),
`factory/activities/verify_activities.py` (one field on `CheckOutputInput`) and
`factory/workgraph/workflow.py` (one line at
`factory/workgraph/workflow.py:2619`).

No two stories are free of shared production files: all three touch
`factory/verify/diffbounds.py` — US1 the classification and the listing marker,
US2 the one stub function, US3 the three measurements that consume it — US1 and
US3 both touch `factory/verify/models.py`, all three touch
`factory/workgraph/workflow.py`, and US2 and US3 both touch
`factory/activities/verify_activities.py`. That is why the Work Graph serialises
all three with `depends_on_merged` rather than leaving any pair concurrent; the
edges buy ordering, and the contention relief is a side effect.

All three are well inside the 64 KiB deterministic diff bound (D-050). US1 is the
largest: roughly 180 production lines across seven files, four one-line edits to
landed test modules, and one new test module — call it 30-40 KiB with T013's
pasted evidence, which is two short blocks rather than a transcript. US2 and US3
are each under a hundred production lines plus one test module; US3's store
round-trip test is short because
`tests/test_092_abridged_is_recorded.py:148` is the shape to copy. If US2's
allocation comparison grows past a screen, cut it to the two `_allocate` result
lines rather than the whole session.

## Verification the operator will run, independent of the gate

Per constitution VIII and D-037 the judge sees the diff and the criteria only, so
runtime evidence must be committed as pasted output. Beyond that:

1. On a scratch repository with a committed lockfile large enough to matter, run
   an epic with no `generated_paths` declared. Confirm today's behaviour: either
   the size refusal fires, or the judge's prompt carries the lockfile body.
2. Declare the lockfile in `generated_paths:` and re-run the same story. The
   refusal must not fire, and the prompt must carry the stub with the real
   counts.
3. Misspell the pattern and re-run. Nothing may be excluded, and the record —
   read back from the store rather than from a log line, via
   `ergane build status <epic-id>` — must show nothing excluded. That is trap 9's
   mitigation and trap 14's, checked together rather than assumed.
4. Write a *different* `generated_paths` list into the node's worktree copy of
   the manifest mid-attempt and confirm the pinned value did not move. This is
   the one step no committed test can fully stand in for, because it is about
   which file was read and when. Run it twice — once through `ergane build
   start` and once through a roadmap dispatch — because those are two different
   `EpicInput` construction sites (`factory/cli/nouns/build.py:931` and
   `factory/roadmap/workflow.py:1296`), and a story that wired one of them passes
   every other committed test in this spec.
5. Add enough source to the same story that its non-generated bytes alone exceed
   the threshold, and read the refusal the ladder quotes back. No file it names
   as a largest contributor may state more bytes than the total it is printed
   beside. That is trap 16, checked against
   `factory/workgraph/prompt.py:975` — `_size_listing`'s actual output rather
   than against the record alone.
6. Run `ergane spec validate` over this directory, then read
   `factory/verify/diffbounds.py` and `factory/verify/judge.py` side by side and
   confirm the exclusion is the same rule over the same sections in both, stub
   bytes included, and that exactly one function in the tree renders the stub. A
   difference here is 092 trap 3, and it will not show up as a failing test.

Step 2 is the falsifiable test of the whole spec: it is the container run's
70,652 bytes against 65,536, run forwards.
