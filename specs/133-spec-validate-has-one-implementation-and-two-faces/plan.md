# Implementation Plan: spec validate has one implementation and two faces

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing. This spec moves code out of
`factory/cli/nouns/spec.py`, so its own anchors will rot as it lands — that is
expected, and the anchors are a record of the tree the implementer was told
about. The § Sizing section names the line regions each story removes, so the
next author of a spec against this file can re-anchor from the shape rather than
from a diff. **Every relocation task after US1 runs against a file the earlier
stories have already shortened: locate what you are moving by symbol name, not by
line number.**

## What already exists, and where

**The function that holds the whole policy.**
`factory/cli/nouns/spec.py:490` — `_validate_command`,
`(args: argparse.Namespace) -> int`. It runs from line 490 to
line 750, 11,337 bytes.

**The twelve layers, in the order the code runs them.** The numbered comments
inside `_validate_command` run 1 to 11 and use `6.` twice, so counting the
comments gives eleven. Counting the `checked` list a run emits gives twelve.

| # | Layer name in the report | Implementation | Where |
| --- | --- | --- | --- |
| 1 | `frontmatter` | private | `factory/cli/nouns/spec.py:999` — `_check_frontmatter` |
| 2 | `fixes` | private | `factory/cli/nouns/spec.py:1231` — `_check_fixes` |
| 3 | `workgraph_derivation` in `checked`, **`workgraph` on the finding** | exported primitive, wrapper inline in `_validate_command` | `derive_workgraph` inside the `try` at `factory/cli/nouns/spec.py:525-535`, then `factory/cli/nouns/spec.py:1298` — `_check_workgraph` |
| 4 | `persona_registry` | private | `factory/cli/nouns/spec.py:1305` — `_check_personas` |
| 5 | `scenario_coverage` | private | `factory/cli/nouns/spec.py:1379` — `_check_scenario_coverage` |
| 6 | `prompt_assembly` | exported primitive, **wrapper inline in `_validate_command`** | `check_prompt_assembly` imported at `factory/cli/nouns/spec.py:60`; name, severity, `checked` append and skip reason at `factory/cli/nouns/spec.py:557-574` |
| 7 | `slice_coverage` | exported primitive, **wrapper inline in `_validate_command`** | `check_slice_coverage` imported at `factory/cli/nouns/spec.py:60`; name, severity, the `information` routing and skip reason at `factory/cli/nouns/spec.py:582-604` |
| 8 | `slice_contention` | **no function at all** | inline at `factory/cli/nouns/spec.py:614-631` |
| 9 | `sentinels` in `checked`, **`sentinel` on the finding** | private scanner, **wrapper inline** | `factory/cli/nouns/spec.py:463` — `_scan_sentinels_in_trio`, wrapped at `factory/cli/nouns/spec.py:638-645` |
| 10 | `anchor_resolution` | private | `factory/cli/nouns/spec.py:1023` — `_check_anchor_resolution` |
| 11 | `symbol_anchors` | private | `factory/cli/nouns/spec.py:886` — `_check_symbol_anchors` |
| 12 | `evidence` | private | `factory/cli/nouns/spec.py:1781` — `_check_evidence` |

**The `checked` list is seeded, not accumulated in run order.** Four names are
written literally before any layer runs:

```python
    checked = [
        "frontmatter",
        "workgraph_derivation",
        "persona_registry",
        "scenario_coverage",
    ]
```

at `factory/cli/nouns/spec.py:504`. The other eight are appended as their layers
finish, so `fixes` — which runs second — lands fifth in the emitted sequence.

**The five module-level names that sit outside every layer body.** This table was
produced by walking the module's AST at 602a92c and asking, for each relocation
span, which module-level names it loads that are bound outside it. Everything not
listed here is an import, and an import is re-satisfiable from its own upstream
module. These five are not.

| Name | Defined at | Read only from | Travels with |
| --- | --- | --- | --- |
| `_ValidateFinding` | `_ValidateFinding` (`factory/cli/nouns/spec.py`:483 in the pre-US1 tree; it is `SpecFinding` in `factory/spec/report.py:24` now, bound back under the old name at `factory/cli/nouns/spec.py:39`) | every relocated family, and `_validate_command` itself | **US1** |
| `_ANCHOR_RE` | `factory/cli/nouns/spec.py:68` | `factory/cli/nouns/spec.py:1123` | US2 |
| `_BARE_LINE_RE` | `factory/cli/nouns/spec.py:71` | `factory/cli/nouns/spec.py:1092` | US2 |
| `_SCENARIO_ID_RE` | `factory/cli/nouns/spec.py:65` | `factory/cli/nouns/spec.py:1407` | US5 |
| `_vacuous_registry` (and `_STRUCTURAL_TIMEOUT_S` at `factory/cli/nouns/spec.py:76`, which only it reads) | `factory/cli/nouns/spec.py:80` — `_vacuous_registry` | `factory/cli/nouns/spec.py:1306` | US5 |

**The report, assembled and consumed in place.** The dict literal opens at
`factory/cli/nouns/spec.py:677`; the `as_json` branch at
`factory/cli/nouns/spec.py:698` prints it at `factory/cli/nouns/spec.py:699` and
moves on. The verdict is computed and discarded at
`factory/cli/nouns/spec.py:750`:

```python
    return EXIT_USER if has_refusal else EXIT_OK
```

**The all-pass sentence is rendered from the `checked` list, and only on a run
with no refusal.** `factory/cli/nouns/spec.py:753` — `_all_pass_phrases`, whose
own docstring says `fixes` is inserted "only when the layer actually ran". It is
printed at `factory/cli/nouns/spec.py:718` when there are no findings at all, and
at `factory/cli/nouns/spec.py:714` with `see advisory above` when there are
advisories but no refusal. On a run carrying a refusal the sentence is never
emitted at all — which is why FR-014 needs two fixture trios.

**Five findings are constructed in `_validate_command`'s own body, and three
of them are whole layer wrappers.** `factory/cli/nouns/spec.py:535` (layer
`workgraph`, on a `DerivationError`), `factory/cli/nouns/spec.py:559`
(`prompt_assembly`), `factory/cli/nouns/spec.py:590` (`slice_coverage`, and it
is this line that routes on `entry.informational` between the `findings` and
`information` lists), `factory/cli/nouns/spec.py:617` (`slice_contention`) and
`factory/cli/nouns/spec.py:634` (`sentinel`). Three of the five sit inside a
complete layer wrapper that no `def _check_` function holds: `prompt_assembly`
at `factory/cli/nouns/spec.py:557-574`, `slice_coverage` at
`factory/cli/nouns/spec.py:582-604` and `sentinels` at
`factory/cli/nouns/spec.py:638-645`, each with its own `checked.append` and, for
the first two, an `else` branch writing a skip-reason string that exists nowhere
else in the tree.

**Two layer names are spelled one way on the finding and another in `checked`,
and both spellings are rendered.** `checked` is seeded with
`workgraph_derivation` at `factory/cli/nouns/spec.py:506`, but the derivation
finding carries `workgraph` (`factory/cli/nouns/spec.py:535`, and again inside
`factory/cli/nouns/spec.py:1298` — `_check_workgraph` at
`factory/cli/nouns/spec.py:1308`). `checked` gains `sentinels` at
`factory/cli/nouns/spec.py:645`, but the note carries `sentinel`
(`factory/cli/nouns/spec.py:634`). Both spellings reach the operator: the
finding's through the `[layer]` prefix printed at
`factory/cli/nouns/spec.py:710` and the `--json` `findings[].layer` key
(`factory/cli/nouns/spec.py:682`), the `checked` one through the `checked`
array. Neither pair is a typo to fix here.

**The finding type is private and is not a dataclass.**
`_ValidateFinding` (`factory/cli/nouns/spec.py`:483 in the pre-US1 tree; it is `SpecFinding` in `factory/spec/report.py:24` now, bound back under the old name at `factory/cli/nouns/spec.py:39`), `__init__(self, layer, message, *, severity="refusal")`.

**The evidence layer both accumulates and returns.**
`factory/cli/nouns/spec.py:1781` — `_check_evidence` appends into the caller-owned
lists like every other checker *and* returns `_JudgeEvidenceReport`. The verb
binds it at `factory/cli/nouns/spec.py:675`, prints it at
`factory/cli/nouns/spec.py:724` and serialises it under the `judge_evidence` key
at `factory/cli/nouns/spec.py:693`.

**The decoy.** `factory/cli/nouns/spec.py:276` — `validate_spec_command` is a CLI
wrapper: Namespace in, delegate to `_validate_command`, print, exit code back. It
exists so `build ship` could stream the same stdout, at
`factory/cli/nouns/build.py:1076`. `grep -rn "validate_spec\|SpecValidation" factory/`
returns exactly three hits — that wrapper and its two call sites. `ls factory/spec`
errors.

**The in-tree argv caller.**
`factory/cli/install.py:1078` — `_spec_validate_argv` builds the argv list;
`factory/cli/install.py:1028` runs it
back through the CLI entry point via `factory/cli/install.py:1071` — `_run_cli`,
whose docstring is "Run one `ergane` invocation, streaming its labeled output
as-is."

**The deterministic bound this spec is sized against.** The constant
`DIFF_INPUT_LIMIT` is assigned `64 * 1024` at
`factory/verify/diffbounds.py:47`.

## Traps

**Trap 1 — THERE ARE TWELVE LAYERS AND THE SOURCE DOCUMENT SAYS SIX.** PR-8
counted six layers with five exported. The drafted spec counted eleven, by
counting `_validate_command`'s numbered comments, which run 1 to 11 with `6.`
used twice. A run emits twelve names in `checked`. Ten of the twelve are
implemented inside the CLI module. An implementer who scopes from either count
leaves layers behind and passes every test they wrote. Read the table above, and
if you want the count from the tree rather than from this page, run the verb with
`--json` and count `checked`. FR-004.

**Trap 2 — FOUR LAYERS HAVE NO `def _check_` TO MOVE, AND A SWEEP OF THE
PRIVATE CHECKERS FINDS NONE OF THEM.** `_validate_command` constructs a finding
at **five** sites in its own body, not one, and three of those sites are
complete layer wrappers — name, severity, `checked` append and, for two of them,
an `else` branch holding a skip-reason string that exists nowhere else in the
tree. Enumerated, because US3's scope is exactly this list:

1. `factory/cli/nouns/spec.py:535` — the `DerivationError` refusal, layer
   `workgraph`, inside the `try` at `factory/cli/nouns/spec.py:525-535`. No
   `checked` append: `workgraph_derivation` was seeded at
   `factory/cli/nouns/spec.py:506`.
2. `factory/cli/nouns/spec.py:557-574` — the whole `prompt_assembly` layer.
   Finding at `factory/cli/nouns/spec.py:559`, `checked` append at
   `factory/cli/nouns/spec.py:560`, and an `else` whose reason string — "the
   work graph did not compile, so there are no nodes to assemble a prompt for"
   — is written here and only here.
3. `factory/cli/nouns/spec.py:582-604` — the whole `slice_coverage` layer.
   Finding at `factory/cli/nouns/spec.py:590`, and it is this line, not the
   exported checker, that decides on `entry.informational` whether an answer
   lands in `findings` or in `information`. Its `else` carries a two-way reason
   string keyed on why `coverage` is `None`.
4. `factory/cli/nouns/spec.py:614-631` — `slice_contention`, reading
   `graph.inferred_edges` and grading `advisory`
   (`factory/cli/nouns/spec.py:617`).
5. `factory/cli/nouns/spec.py:638-645` — the `sentinels` layer: the scanner is a
   function US5 moves, but the loop, the `information` routing, the message
   format and the unconditional `checked.append` at
   `factory/cli/nouns/spec.py:645` are here, and the note's layer name is
   `sentinel`, not `sentinels`.

Grepping for `def _check_` returns eight functions and finds none of these five.
Read the advisory scoping literally too: `slice_contention` is **not** the only
advisory in the module.
`factory/cli/nouns/spec.py:1379` — `_check_scenario_coverage` grades its
uncovered-scenario finding `advisory` at
`factory/cli/nouns/spec.py:1414`, and that is the one trap 13 uses to build the
defective fixture trio. FR-004, FR-008: the CLI must construct no finding of its
own when US3 is done, and these five are the constructions that will still be
there. An implementer who scopes US3 from "move the one inline block" moves one
of five and fails their own T037.

**Trap 3 — THE `checked` LIST'S ORDER IS NOT THE RUN ORDER, AND WHAT A TIDY-UP
BREAKS IS THE `--json` DOCUMENT, NOT THE SENTENCE.** Four names are seeded at
`factory/cli/nouns/spec.py:504` before any layer runs; `fixes` runs second and is
appended at `factory/cli/nouns/spec.py:1301`, so it lands fifth. Rebuilding the
report by appending each layer as it runs looks obviously more correct, and what
it changes is the `checked` array serialised into the `--json` document — the
dict opened at `factory/cli/nouns/spec.py:677` and printed at
`factory/cli/nouns/spec.py:699`. **The two controls are T034's direct sequence
assertion and FR-007's JSON golden**, and they are the only two. FR-005.

**Do not expect the all-pass sentence to catch it, because it cannot.**
`factory/cli/nouns/spec.py:753` — `_all_pass_phrases` starts from a fixed
five-phrase list at `factory/cli/nouns/spec.py:763` and then reads `checked` for
**membership** and nothing else — `if "fixes" in checked` at
`factory/cli/nouns/spec.py:770`, `if "anchor_resolution" in checked` at
`factory/cli/nouns/spec.py:766`, `if "symbol_anchors" in checked` at
`factory/cli/nouns/spec.py:774` — with a fixed `insert(1, …)` for the first.
Its own docstring claims the phrases come out "in the order the layers run"; the
code never reads an order at all. A reordered `checked` changes not one byte of
stdout. This paragraph is here because the earlier draft of this trap said the
opposite, and a trap an implementer can falsify in thirty seconds is a trap they
correctly stop obeying.

**What does rewrite the sentence is a layer's MEMBERSHIP in `checked`** — which
is precisely what traps 4 and 5 are about, and why FR-014 asks for a **clean**
fixture trio as well as a defective one. `factory/cli/nouns/spec.py:702` — the
`if findings:` branch — means a run carrying a refusal never prints the sentence
at all, so a golden taken over one defective trio freezes every shape except that
one.

**Trap 4 — `_check_fixes` HAS FOUR EARLY RETURNS AND ONLY ONE PATH APPENDS.**
`factory/cli/nouns/spec.py:1231` — `_check_fixes`:

1. `factory/cli/nouns/spec.py:1244` — returns **silently**, touching no list at
   all, when `spec.md` cannot be read. The comment beside it says why: "The
   frontmatter layer already reports a missing spec.md; do not double-report."
   This is the return a relocation is most likely to "normalise" into a skipped
   entry, because it is the one with no visible output to preserve, and doing so
   produces a double report on the one input that already refuses.
2. `factory/cli/nouns/spec.py:1255` — returns silently when the spec declares no
   `fixes:` key.
3. `factory/cli/nouns/spec.py:1267` — appends one `skipped` entry and returns
   when there is no store.
4. `factory/cli/nouns/spec.py:1279` — appends a *different* `skipped` entry and
   returns when the store cannot be opened.

Only the success path reaches `factory/cli/nouns/spec.py:1301`. So a spec with no
`fixes:` key is neither checked nor skipped for that layer, and the all-pass
sentence omits the word. A relocation that normalises any of the four into
always-append-something changes the output of most of the corpus. FR-011, FR-005.

**Trap 5 — `_check_anchor_resolution` APPENDS `checked` AT FOUR SEPARATE
EXITS.** They are at `factory/cli/nouns/spec.py:1057`,
`factory/cli/nouns/spec.py:1150`, `factory/cli/nouns/spec.py:1189` and
`factory/cli/nouns/spec.py:1228`, guarding "no documents", "no citations", "no
citations after reporting the unanchorable ones" and the normal end. Hoisting
them into one append at the caller is the obvious tidy-up and it makes the layer
report as checked on a path where today it does not. FR-010, FR-005.

**Trap 6 — A MOVE IS A DELETE PLUS AN ADD, AND AN OVERSIZE STORY IS REFUSED AT
65,536 BYTES.** The dial that refuses is `DIFF_REFUSAL_THRESHOLD`, assigned at
`factory/verify/diffbounds.py:66` as — and today equal to — `DIFF_INPUT_LIMIT`,
which is assigned `64 * 1024` at `factory/verify/diffbounds.py:47` and is the
separate question of what the judge may be shown (092 split them for exactly
this reason; the comment at `factory/verify/diffbounds.py:49` is the argument).
`ergane.yaml` declares no manifest override, so 65,536 stands. The refusal
counts the assembled diff text with no elision (D-050). The five families the draft put in one story measure 36,232 bytes of
source at 602a92c, which is a ~72,000-byte diff before a line of test. That is
why there are three relocation stories and not one. The largest of the three,
US6, is 18,391 bytes; if while working you find yourself moving more than about
19 KB of source in one story, stop and say so on the escalation rather than
shipping a diff the verifier will refuse.

**Trap 7 — DO NOT REDESIGN THE CHECKERS' SIGNATURES WHILE RELOCATING THEM.**
Every private checker accumulates into caller-owned lists — `findings`,
`skipped`, `checked`, `information` — rather than returning anything;
`factory/cli/nouns/spec.py:1023` — `_check_anchor_resolution` takes six
parameters for exactly that reason. **One exception, and US6's implementer meets
it first:** `factory/cli/nouns/spec.py:1781` — `_check_evidence` does both. It
appends into the same caller-owned lists *and* returns `_JudgeEvidenceReport`,
which the verb binds at `factory/cli/nouns/spec.py:675`, prints at
`factory/cli/nouns/spec.py:724` and serialises under `judge_evidence` at
`factory/cli/nouns/spec.py:693`. Keep that return exactly as it is; do not fold it
into the lists to make the family uniform. Converting any of them to return a
typed result while moving turns a mechanical move into a rewrite, doubles the
diff into Trap 6's refusal, and destroys the only cheap evidence that nothing
changed. The typed report is assembled by `validate_spec` from those lists in
US3, once. FR-010, FR-011, FR-012.

**Trap 8 — `validate_spec_command` IS NOT THE SEAM.**
`factory/cli/nouns/spec.py:276` — `validate_spec_command` is the one public name
in the area and it has the right shape at a glance. It takes an
`argparse.Namespace`, prints, and returns an exit code, and it exists only so
`build ship` (`factory/cli/nouns/build.py:1076`) could stream the same stdout.
Building the library form on it produces something that still needs a Namespace
and still prints — the exact thing the consumer in the ledger row cannot use.
FR-003.

**Trap 9 — A CHANGED MESSAGE IS A REGRESSION, NOT AN IMPROVEMENT.** This is a
move. `spec validate`'s refusals are read closely by operators and quoted in
specs; 072's whole lesson is that naming the line, the rule and what the refusal
cost downstream is the shape worth keeping. FR-006 and FR-007 require the output
to match a golden artifact byte for byte, and US4 is what keeps it matching.
Resist every opportunity to improve wording while moving it. **FR-006 names two
streams on purpose:** the four prefixes this trap is about — `— refusal:`,
`— advisory:`, `— layer 'X' not checked:` and `— noted, not a refusal:` — are all
printed to stderr and appear in no stdout capture at all (trap 19). A
stdout-only golden would have let US3 rewrite every one of them green.

**Trap 10 — THE SKIPPED CHANNEL IS LOAD-BEARING AND EASY TO COLLAPSE.** When the
work graph does not compile, later layers are reported as *not checked* with a
reason, and that chain is what made 072's refusal useful. A typed report that
folds "skipped" into "passed" or into "failed" destroys information the verb
prints today and cannot be recovered from the exit code. FR-002.

**Trap 11 — THE GOLDEN CAPTURE IS HOST-DEPENDENT UNLESS YOU NORMALISE IT.** The
`fixes` layer's information note embeds the absolute store path — see the
`f"verified {len(fixes)} finding key(s) against {store_path}"` construction under
`factory/cli/nouns/spec.py:1231` — and the evidence layer's report embeds the
absolute manifest path. A capture taken on this host and committed verbatim goes
red on any other checkout, including the merge-group build. Normalise the
repository root to a placeholder on both sides of the comparison — **on all three
streams**, because the skipped-layer reasons quote `--target-repo` verbatim
(`factory/cli/nouns/spec.py:1201`) and they are printed to stderr (trap 19).
FR-014.

**Trap 12 — DO NOT GOLDEN A LIVE CORPUS SPEC.** Every spec under `specs/` is
edited by refinement, sometimes weekly, and its validate output changes with it.
A golden taken against `specs/057-…` goes red the next time someone re-anchors
057, for a reason that has nothing to do with this spec, and the obvious fix
— re-taking the golden — silently erases the only proof that the move changed
nothing. Commit synthetic fixture trios under `tests/` instead. FR-014.

**Trap 13 — THE FIXTURE TRIO'S PARENT DIRECTORY IS ITS SPECS ROOT, AND ONE TRIO
CANNOT COVER FOUR CHANNELS.**
`factory/cli/nouns/spec.py:999` — `_check_frontmatter` computes
`specs_root = spec_dir.parent` and calls `read_roadmap` on it, so a fixture trio
dropped straight into `tests/fixtures/` makes the whole of `tests/fixtures/` the
roadmap the frontmatter layer reads. Give **each** trio its own parent directory
holding nothing else — two trios, two parents. The split between them is forced
by the rendering, not by taste: a run carrying a refusal never prints the all-pass
sentence (trap 3). Both trios can share **one** fixture target repository: a
directory that commits an `ergane.yaml` declaring a single gate and carries none
of the files the trios cite.

- **The clean trio** takes the `else` branch at `factory/cli/nouns/spec.py:717`
  and prints the all-pass sentence on stdout. Its *skipped* layer is
  `anchor_resolution`, and on that recipe only that one: cite at least one
  `path:NN` anchor in the trio, and because the shared target repository carries
  none of the cited files `factory/cli/nouns/spec.py:1194` skips the layer with
  "none of the cited paths exist under target repository …".
  `factory/cli/nouns/spec.py:886` — `_check_symbol_anchors` does **not** skip
  there: its only skip is at `factory/cli/nouns/spec.py:903`, guarded by
  `if not target_path.is_dir()`, so a readable tree that merely lacks the cited
  files sets `layer_ran` and appends `symbol_anchors` to `checked` at
  `factory/cli/nouns/spec.py:996` — an absent cited module takes the bare
  `continue` at `factory/cli/nouns/spec.py:961`. One skip, and the all-pass
  sentence still names "symbol anchors". If you want *both* anchor layers skipped
  instead, point `--target-repo` at a path that is not a directory at all — then
  `factory/cli/nouns/spec.py:903` and `factory/cli/nouns/spec.py:1194` both fire,
  the evidence layer skips with them, and the sentence names neither anchor
  phrase. The two recipes produce different goldens; commit the fixture for the
  one you pick so the artifact is reproducible. Get the *information* note
  host-independently from an `ERGANE-TODO` sentinel in the trio — the loop at
  `factory/cli/nouns/spec.py:638` appends one `information` entry per sentinel and
  `factory/cli/nouns/spec.py:645` reports the layer in `checked` whatever happens.
  Do not reach for the `fixes` layer's note for this: it needs a store and it
  embeds an absolute path (trap 11, trap 20).
- **The defective trio** carries a refusal and an advisory, and both of them are
  printed to stderr (trap 19). Make the refusal an **evidence** refusal — a
  Then-clause naming a runtime outcome no declared gate can produce — because
  US6-S4 asserts the moved checker produces that exact string and takes it from
  this trio's stderr golden. That is what the shared target repository's
  `ergane.yaml` is for: without a readable manifest declaring gates,
  `factory/cli/nouns/spec.py:1559` — `_declared_gates` returns `gates=None` and
  `factory/cli/nouns/spec.py:1815` skips the layer instead of refusing. The
  in-tree model for that fixture repository is
  `tests/test_102_unprovable_criteria.py:175` — `_repo`. The cheapest
  host-independent advisory is `scenario_coverage`: declare an acceptance scenario
  the trio's `tasks.md` never names, and `factory/cli/nouns/spec.py:1410`
  constructs it at severity `advisory`.

**Trap 14 — THE DEMONSTRATION STREAMS THE CLI'S OUTPUT ON PURPOSE.**
`factory/cli/install.py:1071` — `_run_cli` exists to stream labeled output, and
`factory/cli/install.py:1028` calls it for the validate stage so a stranger
watching `ergane install` sees the real verdict.
`tests/test_110_us1_demo_first_boot.py:425` asserts that argv path returns 0.
Converting it to a bare `validate_spec` call satisfies FR-013's letter and
deletes the demonstration's whole point — the lines it prints. Route it through
the same renderer the verb uses, and update that test to the new seam rather than
deleting its assertion. FR-013.

**Trap 15 — THE CORPUS PARITY TEST MUST NOT SPAWN A PROCESS PER SPEC.** There are
more than 130 spec directories and validate does real file IO per layer. Driving
the CLI face with `subprocess.run` once per spec is minutes of suite wall time,
and this repository already has three tests that account for over half the
suite's duration. Drive the CLI face in-process through the CLI entry point with
stdout captured. FR-009.

**Trap 16 — TWO NEIGHBOURS ARE MOVING AROUND YOU, AND NEITHER SHOULD CHANGE WHAT
YOU WRITE.** Draft 129 changes what `resolve_factory_root()` returns — the call
`_check_fixes` makes at `factory/cli/nouns/spec.py:1257` — and says in its own
plan that it fixes this at the resolver and will *not* edit its roughly fifteen
callers. So carry that call verbatim through the relocation; do not resolve or
absolutise the path yourself. Draft 076 makes every spec verb accept a bare
number and lands *after* this spec, re-anchoring against the shape you leave. Keep
the argv-to-`Path` resolution in the CLI: `validate_spec` takes an already
resolved `Path`, so 076 has one place to put the number lookup.

**Trap 17 — THE IMPORT DIRECTION IS ONE-WAY, AND THE OBVIOUS SHORTCUT IS A HARD
`ImportError`.** From US1 onward `factory/cli/nouns/spec.py` imports from
`factory.spec` at module scope, so `factory/spec/` may **never** import from
`factory.cli.nouns.spec`. This is not a style preference. The CLI module's import
block ends at `factory/cli/nouns/spec.py:62`, and the five names in the table
above are bound at lines 65 to 98 and 483 to 487 — *below* where a
`from factory.spec import …` line lands. So an import back re-enters a
half-initialised `factory.cli.nouns.spec` before those names exist and raises
`ImportError` at interpreter start, not at call time. The consequence for the
implementer: **a moved body that needs a CLI-module name means the name moves
too.** Do not leave `_ANCHOR_RE`, `_BARE_LINE_RE`, `_SCENARIO_ID_RE`,
`_vacuous_registry`, `_STRUCTURAL_TIMEOUT_S` or `_ValidateFinding` behind, and do
not re-declare the anchor or scenario-id grammars inside `factory/spec/` to route
around it — a second copy of 072's grammar is the exact duplication this spec
exists to end, and neither FR-010's name list nor US2-S1's Then authorises it.
FR-001, FR-010, FR-011.

**Trap 18 — MOVING `_vacuous_registry` BREAKS A TEST THAT REACHES IT THROUGH THE
CLI MODULE.** `tests/test_062_us3_skills.py:141` calls
`spec_noun._vacuous_registry(graph)` and asserts the registry it returns answers
with empty `skills` — that is 062-US3 FR-009's standing proof, and it is the only
in-tree reference to the helper outside `factory/cli/nouns/spec.py`. Point it at
the new home; do not delete the assertion, and do not keep a shim in the CLI
module to spare the edit. Same shape as trap 14, different file. FR-011.

**Trap 19 — THREE OF THE FOUR CHANNELS PRINT TO STDERR, SO A STDOUT-ONLY GOLDEN
FREEZES ALMOST NOTHING.** The verb splits its streams, and the split is invisible
from the four-channel table in `spec.md` unless you read the calls. Every finding
line, refusal and advisory alike, is printed with `file=sys.stderr` at
`factory/cli/nouns/spec.py:710`; every skipped-layer line at
`factory/cli/nouns/spec.py:733`; every information note at
`factory/cli/nouns/spec.py:739`; the trailing ERGANE-TODO count at
`factory/cli/nouns/spec.py:747`. Exactly three writes reach stdout: the all-pass
sentence at `factory/cli/nouns/spec.py:714` and `factory/cli/nouns/spec.py:718`,
the judge-evidence report lines at `factory/cli/nouns/spec.py:725`, and the
`--json` document at `factory/cli/nouns/spec.py:699`. Reproduce it before you
capture anything:

```bash
ergane spec validate <trio> --target-repo <fixture-repo> --specs-root <parent> \
  >stdout.txt 2>stderr.txt
```

The consequence is FR-014's shape. A stdout-only capture freezes none of the four
rendered prefixes trap 9 forbids changing, and US3's T040 is exactly the task that
rewrites them — so the one story in this spec with output-regression risk would
have had no artifact to fail against. Three artifacts per trio, six in all.
FR-006, FR-014.

**Trap 20 — THREE LAYERS SKIP RATHER THAN REFUSE WHEN THEIR PRECONDITION IS
ABSENT, SO A BARE `tmp_path` TRIO ASSERTS NOTHING.** US3-S2 drives the library
form over five specs, each defective in one of the five ways a re-composing
consumer misses. Three of the five need a fixture the trio itself cannot carry:

- **`fixes`.** `factory/cli/nouns/spec.py:1231` — `_check_fixes` calls
  `resolve_factory_root()` at `factory/cli/nouns/spec.py:1257`, and at
  `factory/cli/nouns/spec.py:1260` appends a `skipped` entry and returns when no
  store exists there. So a trio with an unresolvable `fixes:` key refuses on a
  host that happens to have a `.factory/doctor.db` and skips silently on one that
  does not — a test that passes here and is vacuous in a fresh checkout. Build the
  store under `tmp_path`:
  `tests/test_089_validate_checks_fixes.py:32` — `_own_findings_store` is the
  in-tree model, and it points **both** store
  candidates at the test's own tree for exactly this reason.
- **`evidence`.** `factory/cli/nouns/spec.py:1559` — `_declared_gates` returns
  `gates=None` when the target repository has no readable manifest, and
  `factory/cli/nouns/spec.py:1815` turns that into a skip rather than a refusal.
  The trio needs a `--target-repo` that commits an `ergane.yaml` declaring a gate;
  `tests/test_102_unprovable_criteria.py:175` — `_repo` is the model.
- **`anchor_resolution`.** `factory/cli/nouns/spec.py:1194` skips the whole layer
  when none of the cited paths can be read, so the stale-anchor trio needs the
  cited `.py` file to exist under its target repo with content that makes the
  citation stale. `tests/test_anchor_resolution.py` is the model, and its
  docstring says why every fixture is a supplied tmp tree and never this
  repository.

A skip does not fail the assertion US3-S2 makes; it makes it vacuous, which is
the failure mode this spec exists to end. FR-004.

**Trap 21 — THE `--json` DOCUMENT'S KEY ORDER, AND THE ABSENCE OF
`judge_evidence`, ARE BOTH LOAD-BEARING.** FR-007 makes that document
byte-for-byte, and it is `json.dumps(report, indent=2)` at
`factory/cli/nouns/spec.py:699` over the dict literal opened at
`factory/cli/nouns/spec.py:677`, whose keys are written in the order `spec_dir`,
`checked`, `skipped`, `findings`, `information`, with `judge_evidence` appended
at `factory/cli/nouns/spec.py:693` only when the evidence layer returned a
report.
The comment at `factory/cli/nouns/spec.py:689` says the absence is deliberate:
"Absent rather than empty when there is no report to make". A
`dataclasses.asdict()` over the new report type, or any serialiser that emits its
fields in declaration order, reorders those keys and emits `judge_evidence: null`
— and FR-007's golden goes red for a reason the implementer has to rediscover
from the diff. Serialise in the dict's order, and keep the key absent rather than
null. FR-007.

**Trap 22 — FOUR IN-TREE TESTS REACH THE MOVED LAYER BODIES AS ATTRIBUTES OF
THE CLI MODULE, AND THE IMPORT-BACK THAT KEEPS THEM GREEN IS NOT A CONTRACT.**
Trap 18 named one such file. There are five, and the other four all reach names
US5 moves:

- `tests/test_slice_coverage.py:290` annotates on `spec_noun._ValidateFinding`
  and calls `spec_noun._check_frontmatter` at
  `tests/test_slice_coverage.py:292`, `spec_noun._check_workgraph` at
  `tests/test_slice_coverage.py:294`, `spec_noun._check_personas` at
  `tests/test_slice_coverage.py:295` and `spec_noun._check_scenario_coverage` at
  `tests/test_slice_coverage.py:296`.
- `tests/test_prompt_assembly.py:387` does the same four at
  `tests/test_prompt_assembly.py:389`, `tests/test_prompt_assembly.py:397`,
  `tests/test_prompt_assembly.py:398` and `tests/test_prompt_assembly.py:399` —
  and at `tests/test_prompt_assembly.py:361` it reads `spec_noun.__file__`'s
  source and asserts the module implementing the layer does not re-state the
  story-heading grammar. When the layer body moves, that guard must follow it or
  it starts guarding a module that no longer holds the layer: 044 FR-004's
  duplicate-grammar proof goes vacuous exactly the way trap 23's controls do.
- `tests/test_122_findings_store_isolation.py:31` imports `_check_fixes` at
  **module scope**, so an unbound name there is a collection error that takes
  the whole file down, not one red test; the call is at
  `tests/test_122_findings_store_isolation.py:241`.
- `tests/test_us1_registry_resolution.py:159` names `spec_noun._check_personas`
  as one entry in the call-site table 044-US1 uses to prove every registry
  resolution goes through one loader.

None of the four is forced green by production code: every reader of these names
outside the moved spans is `_validate_command` or `_derive_command`. So they
survive US5 **only** if the implementer re-binds each moved name in the CLI
module under its old private name — and US5-S1's "imports them from
`factory.spec` instead" and T018's `__module__` assertion are both satisfied by
`from factory.spec import check_fixes` with the call site renamed, which unbinds
`spec_noun._check_fixes` and takes
`tests/test_122_findings_store_isolation.py` down at collection. Then US3
removes the CLI's last call to nine of these names (FR-008), the imports become
unused, and the ordinary tidy-up of an unused import breaks all four files at
once. The declared gate is `uv run pytest -q` (`ergane.yaml:34`) and there is no
lint gate to catch it earlier, so it surfaces as a red test gate and a spent
attempt. Re-point all four at `factory.spec` in US5, the way trap 18 re-points
`tests/test_062_us3_skills.py`, and do not leave a shim. FR-011, FR-015.

**Trap 23 — US3 SILENTLY VOIDS THE TWO CORPUS CONTROLS THAT GUARD THE `fixes`
AND `evidence` LAYERS.**
`tests/test_089_validate_checks_fixes.py:300` — `_validate_without_fixes_layer`
rebinds `factory.cli.nouns.spec._check_fixes` to
a no-op (`tests/test_089_validate_checks_fixes.py:307`), runs the CLI verb over
the whole corpus and asserts the with-layer and without-layer verdicts are
identical;
`tests/test_102_unprovable_criteria.py:425` — `_validate_without_evidence_layer`
does the same for `_check_evidence` at
`tests/test_102_unprovable_criteria.py:432`. Both work today, and they keep
working through US5 and US6, because `_validate_command` resolves the module
global at call time and the import-back rebinds that same global. **US3 kills
them without turning anything red.** Once the verb is a renderer over
`factory.spec`'s `validate_spec`, the composition reads `factory.spec`'s own
globals; the rebinding lands on a name nothing calls; both runs become the same
run; and both assertions pass over a hundred and thirty specs while covering
nothing. `tests/test_102_unprovable_criteria.py:449` — its own docstring calls
that comparison "the only thing standing between this layer and a hundred and
fifteen specs it was never tried against", and
`tests/test_102_unprovable_criteria.py:458` says out loud that with the layer
disabled both runs are the same run — which is the tell. This is trap 20's
failure mode ("a skip does not fail the assertion; it makes it vacuous") turned
on the spec's own controls. Re-point both helpers at the module the composition
reads, and prove the re-point with US3-S8: on a spec the layer refuses, the
disabled and enabled runs must **differ**. A control that cannot fail is not a
control. FR-015.

## Sizing

### The model, corrected against two measured stories (2026-09-07)

**This section used to be wrong in a way that cost an epic, and the correction is
the most load-bearing paragraph in this plan.** The old model said: a move shows
in the diff twice, so a relocation costs roughly double the source it moves,
"before tests and evidence." Both halves of that failed. The doubling is too low,
and the phrase "before tests and evidence" was never turned into a number, so
every per-story estimate below silently omitted the two largest terms.

Measured, from the only two stories of this spec that have been built:

| | US1 (landed, PASS) | US2 (killed, FAIL) |
| --- | --- | --- |
| source moved | — (authored) | 18,098 B |
| `factory/` diff | 4,850 | **42,753** |
| `tests/` diff | 38,155 | **22,034** |
| `attempt-report.md` | 15,233 | **7,636** |
| **assembled diff** | **58,238** | **72,423** |
| judge input | 59,490 — PASS, 9% spare | 72,750 — **abridged, FAIL** |

Three facts follow, and every estimate below is rebuilt on them:

1. **A relocation costs 2.36x its source, not 2x.** 42,753 / 18,098. The extra is
   the new module's own docstring, imports and re-indentation, plus the
   import-back line in the CLI module.
2. **Tests and committed evidence are 20 to 38 KB, and they are not optional.**
   They were 51% of US2's diff and 92% of US1's. A story budget that omits them
   is not conservative, it is wrong. Budget **20 KB of tests and 9 KB of pasted
   evidence** for a relocation with a focused test file; US1's 38 KB of tests was
   fixtures and goldens, which no later story repeats.
3. **The usable ceiling is 52,400 bytes, not 65,536.** US1 passed with nine
   percent to spare and that was the whole margin. Eighty percent of the bound is
   the number to build to, and a story that assembles past it should escalate
   rather than ship — the judge does not fail an oversized diff, it silently
   scores an abridged one.

So the working formula for a relocation is:

```
assembled diff  ~=  2.36 x (bytes of source moved)  +  20,000 (tests)  +  9,000 (evidence)
usable ceiling  =   52,400 bytes          (80% of the 65,536-byte bound)
implied source  <=  ~10,000 bytes per relocation story
```

That last line is the whole reason this spec now has five relocations instead of
three: **10 KB of source per story is the budget, and the old US2 and US6 were
17.7 KB and 18.4 KB.**

### Byte counts, and the tree they are counted in

Counts below are top-level symbol spans measured in the tree at **57bf698**,
after US1 landed — not at 602a92c, where this section used to be pinned and where
the numbers no longer resolve. **They remain a map of what to move, not a place to
cut: every story after US2 sees a file that is shorter again, so find each item by
its symbol name.** The anchors in this plan are refreshed to 57bf698 for the same
reason, and they will drift again with every landing in this chain; that is
inherent to a refactor spec whose stories all edit one module, and it is why the
instruction is to locate by symbol rather than to trust a line.

**US1** — mostly new files: `factory/spec/__init__.py` and a report module, six
tests, two synthetic fixture trios plus the one fixture target repository they
share, and **six** golden artifacts — each trio's stdout, its stderr and its
`--json` document (trap 19). The one production deletion is mandatory, not
optional:
`factory/cli/nouns/spec.py`:483-487 in the pre-US1 tree — `_ValidateFinding`, 205 B — moves to
`factory/spec/` and the CLI binds the import under the same local name, so none
of its twenty-odd construction sites changes. Trap 17 is why this cannot wait:
every relocated body constructs that type, and a moved body cannot import it back
out of the module it just left. **Estimate 25 to 35 KB of assembled diff**, and
it is an estimate rather than a measurement because every byte of it is authored
rather than moved: six fixture documents, one fixture manifest, six captures and
six tests. It is **not** the smallest story in the spec — US4 is — and it is the
only story whose size cannot be measured before it is written, so take the six
captures first and read their size: if the artifacts alone approach 20 KB, shrink
the trios rather than the coverage, and say so on the escalation rather than
shipping a diff trap 6 will refuse.

**US2** — the symbol tier only. Removes `_SYMBOL_ANCHOR_RE`
      (`factory/cli/nouns/spec.py:789`) (90 B), `_DISPATCHABLE_STATES`
      (`factory/cli/nouns/spec.py:794`) (42 B), `factory/cli/nouns/spec.py:797` — `_spec_state`
(465 B), `factory/cli/nouns/spec.py:812` — `_severity_for_state` (212 B),
`factory/cli/nouns/spec.py:819` — `_symbol_spans` (1,162 B),
`factory/cli/nouns/spec.py:849` — `_line_hits_symbol` (1,004 B) and
`factory/cli/nouns/spec.py:880` — `_check_symbol_anchors` (4,347 B). Together
**7,322 bytes**: about a 17.3 KB move, **~46 KB assembled**, 71% of the bound.

The two shared helpers are the trap. `_spec_state` and `_severity_for_state` are
read from **two** call sites — `factory/cli/nouns/spec.py:906` inside the symbol
checker this story moves, and `factory/cli/nouns/spec.py:1155` inside the
resolution checker that does not move until US7. They travel with this story and
the CLI module binds them back under their own names, which is exactly what US1
did for `_ValidateFinding`. Copying them instead leaves two definitions of one
severity rule, and the golden captures would not catch it.

**US7** — the resolution tier only. Removes `factory/cli/nouns/spec.py:1005` —
`_read_citation_files` (478 B) and `factory/cli/nouns/spec.py:1017` —
`_check_anchor_resolution` (9,795 B), plus the two regexes that sit far above the
span and are read only from inside it: `_ANCHOR_RE`
      (`factory/cli/nouns/spec.py:69`) (52 B) and `_BARE_LINE_RE` (`factory/cli/nouns/spec.py:72`) (49 B).
Together **10,374 bytes**: about a 24.5 KB move, **~53 KB assembled**, 82% of the
bound and the tightest story in the chain. `_check_anchor_resolution` is 9,795
bytes in one function and cannot be halved without redesigning the checker, which
is not what this spec is for — so if the assembled diff measures past 52,400
bytes, cut the pasted evidence, not the coverage, and escalate before shipping.
The moved checker reads `_spec_state` and `_severity_for_state` from
`factory/spec/`, where US2 put them; importing them back out of the CLI module is
the circular shape trap 17 names.

**US5** — removes `factory/cli/nouns/spec.py:463-481` (`_scan_sentinels_in_trio`,
826 B), `factory/cli/nouns/spec.py:779-790` (`_tasks_text`, 543 B),
`factory/cli/nouns/spec.py:999-1008` (`_check_frontmatter`, 502 B),
`factory/cli/nouns/spec.py:1231-1301` (`_check_fixes`, 2,209 B),
`factory/cli/nouns/spec.py:1298-1370` (`_check_workgraph`, `_check_personas`
and `_candidate_graph`, 2,486 B) and `factory/cli/nouns/spec.py:1379-1416`
(`_check_scenario_coverage` alone, 1,308 B — its body ends at 1416 and everything
below that line belongs to the evidence layer), plus the two module-level names
those bodies alone read: `factory/cli/nouns/spec.py:65-66` (the scenario-id
grammar `_SCENARIO_ID_RE`, 114 B) and `factory/cli/nouns/spec.py:74-99`
(`_STRUCTURAL_TIMEOUT_S` and
`factory/cli/nouns/spec.py:80` — `_vacuous_registry`, 949 B). Together
**8,649 bytes** measured at 57bf698: about a 20.4 KB move, **~51 KB assembled**,
78% of the bound. It also edits the five in-tree tests that
reach these bodies through the CLI module: `tests/test_062_us3_skills.py`
(trap 18) and `tests/test_slice_coverage.py`, `tests/test_prompt_assembly.py`,
`tests/test_122_findings_store_isolation.py` and
`tests/test_us1_registry_resolution.py` (trap 22). Those five edits are a few
import lines and a call-site rename each — call it 2 KB — and skipping them is a
red gate, not a tidy-up left for later.

**US6 and US8** — the judge-evidence family is `factory/cli/nouns/spec.py:1405`
through the end of the module, **18,393 bytes across sixteen top-level names**.
At 2.36x that is a 43 KB move before a single test, so it cannot land as one
story; under the old model it was called "37 KB, the largest of the three and
still inside the bound", which is the same arithmetic error that killed US2.

The family has exactly one seam, and it was checked in the tree rather than
assumed: **no name in the vocabulary half is read by the report half's bodies
only — the dependency runs one way, report half reads vocabulary half.** So the
vocabulary moves first and the report follows.

**US6** — the vocabulary and refusal grammar, `factory/cli/nouns/spec.py:1405`
to 1616: the banner comment, `_RUNTIME_MARKERS`
      (`factory/cli/nouns/spec.py:1434`) (1,437 B), `_DIFF_EVIDENCE_RE`
      (`factory/cli/nouns/spec.py:1475`) (204 B), `_PROVABLE_EXAMPLE`
      (`factory/cli/nouns/spec.py:1482`) (55 B), `factory/cli/nouns/spec.py:1485` — `_then_clauses`
(637 B), `factory/cli/nouns/spec.py:1502` — `_runtime_markers` (218 B),
`factory/cli/nouns/spec.py:1507` — `_names_a_declared_gate` (259 B),
`factory/cli/nouns/spec.py:1514` — `_manifest_declares_no_gates` (742 B),
`factory/cli/nouns/spec.py:1533` — `_Declarations` (859 B),
`factory/cli/nouns/spec.py:1553` — `_declared_gates` (1,218 B) and
`factory/cli/nouns/spec.py:1582` — `_evidence_refusal` (1,466 B). Raw span
**8,863 bytes**: about a 20.9 KB move, **~50 KB assembled**, 76% of the bound.
`_RUNTIME_MARKERS` is the vocabulary `_runtime_markers` reads and must travel
with it; splitting those two strands a constant of this layer in the CLI module
or, worse, carries it away a story early with US5.

**US8** — the report type and the checker, `factory/cli/nouns/spec.py:1611` to
the end: `factory/cli/nouns/spec.py:1641` — `_StoryCriteria` (167 B),
`factory/cli/nouns/spec.py:1650` — `_BorderlineClause` (158 B),
`factory/cli/nouns/spec.py:1660` — `_JudgeEvidenceReport` (3,261 B),
`factory/cli/nouns/spec.py:1742` — `_borderline_warning` (852 B),
`factory/cli/nouns/spec.py:1762` — `_story_criteria` (450 B) and
`factory/cli/nouns/spec.py:1775` — `_check_evidence` (3,327 B). Raw span
**9,530 bytes**: about a 22.5 KB move, **~51 KB assembled**, 79% of the bound.
When it lands, no name of the evidence family remains in the CLI module.

**US3** — rewrites `factory/cli/nouns/spec.py:490-750` (11,337 B) into a
renderer and adds the composition module under `factory/spec/`. That module has
to carry more than the drafted estimate assumed: the composition half of the
rewritten function measures 6,607 B (`factory/cli/nouns/spec.py:504-660`) and
includes the three inline layer wrappers of trap 2 with their skip-reason
strings, so allow for roughly the same size again in the new module rather than
for the one contention block. It also touches `factory/cli/install.py` around
`factory/cli/install.py:1028`, `tests/test_110_us1_demo_first_boot.py`, and —
trap 23 — `tests/test_089_validate_checks_fixes.py` and
`tests/test_102_unprovable_criteria.py`, whose two control helpers must be
re-pointed at the module the composition reads. Expect **49 to 64 KB** of
assembled diff including its nine scenarios' tests and pasted evidence — the old
figure of 40 to 55 KB was written under the model this section has since
corrected, and did not count the 9 KB of committed evidence every story in this
spec carries. It is the widest estimate here and the only one that is an estimate
rather than a measurement, because it writes new code rather than moving old.
**Measure it: assemble the diff, `wc -c` it, and if it passes 52,400 bytes —
eighty percent of the bound, the margin US1 did not have when it landed at
59,490 — stop and say so on the escalation rather than shipping something the
judge will score in abridged form.** The two ways it grows past
that are both avoidable — committing the five defective trios US3-S2 needs
instead of writing them to a `tmp_path` tree at test time (fifteen extra files),
and pasting whole golden artifacts as evidence rather than the empty diff
against them. The single behavioural story.

**US4** — one new test file. Touches no production file.

**What shares no production file**: only US4, and only because it adds a test.
Every other story edits `factory/cli/nouns/spec.py`, and every story after US1
adds to `factory/spec/`. That is the whole argument for the chain, and it is why
no `concurrent_with` override appears in the Work Graph.

**What is left in `factory/cli/nouns/spec.py` when the spec has landed**: the
module docstring and the import block (lines 1 to 62 today, plus new
`from factory.spec import …` lines), the noun and argument wiring, the other
verbs' handlers including `_derive_command` and its sentinel gate — which keeps
calling the relocated `_scan_sentinels_in_trio` through the import —
`validate_spec_command` at 275, the renderer that `_validate_command` becomes,
and `_all_pass_phrases`. Gone are the finding type, the four module-level
grammars and helpers in the table above, and every layer body from the sentinel
scan to the end of the evidence machinery.

For draft 076, which lands after this one and re-anchors against that shape: its
plan currently cites `factory/cli/nouns/spec.py` at 88-179, 112, 134, 167, 203-207,
213-217, 231 and 238, and **all of those are pre-072 numbers that no longer
resolve to what 076 says they do** — 076 has to re-anchor regardless of this spec.
Two of its citations matter here. Its parser wiring lands in the region above the
verbs, which this spec does not touch. Its `epic_id = spec_dir.resolve().name`
citation resolves at 602a92c to `factory/cli/nouns/spec.py:498`, which is
**inside** `_validate_command` and therefore inside the region US3 rewrites — so
that one is not "above the region this spec touches". The `Path(args.spec_dir)`
resolution stays in the CLI either way, because the library form is given a
`Path`, so 076 still has one place to put the number lookup.

## Verification the operator will run, independent of the gate

Per constitution VIII and D-037 the judge sees the diff and the criteria only, so
runtime evidence is committed as pasted output. Beyond that:

0. **Before dispatching anything**, confirm no compiled artifact sits beside this
   spec: `ls specs/133-*/workgraph.json` must find nothing. One derived at
   238b494 from the four-story draft was present at refinement time, and
   `ergane build start` reads a compiled graph off disk
   (`factory/cli/nouns/build.py:845` — `start_command`). Dispatching it would
   build a four-node graph against a six-story spec and judge US2 against the
   composition requirements it no longer implements. `ergane spec validate`
   cannot see this file and will stay green with it there. Delete it —
   `rm specs/133-spec-validate-has-one-implementation-and-two-faces/workgraph.json`
   — or re-derive and confirm the node list is us1, us2, us5, us6, us3, us4. It
   was still on disk on 2026-09-04 carrying four nodes, `us1`, `us2`, `us3`,
   `us4`; a refinement pass is not permitted to write or delete it, so this step
   is the operator's and nobody else's.
1. **Before dispatching US1**, capture `ergane spec validate` output for every
   spec in `specs/` — text and `--json` — into a file outside the tree. This is
   the corpus-wide control the per-story golden cannot be, and it cannot be taken
   after the fact.
2. After US1 lands, confirm the **six** committed golden artifacts exist under
   `tests/`, that each fixture trio's parent directory holds nothing else, that
   the clean trio's **stdout** artifact carries the all-pass sentence, and that
   the defective trio's **stderr** artifact carries one line beginning
   `ergane spec validate — refusal:` and one beginning
   `ergane spec validate — advisory:`. Those prefixes are the ones US3 rewrites
   and they are printed on no other stream (trap 19); the sentence is the line
   traps 4 and 5 would rewrite by changing which layers reach `checked`.
3. After each of US2, US5 and US6 lands, re-run the step 1 sweep and diff it
   against the capture. It must be empty at every one of the three landings, not
   only at the end.
4. After US3 lands, re-run the sweep a fourth time and diff. Then, from a Python
   session that has not imported `argparse`, call
   `validate_spec(Path("specs/133-…"), target_repo=…, specs_root="specs")` and
   read the returned report.
5. Confirm `grep -n "_spec_validate_argv" factory/cli/install.py` returns nothing
   and that `ergane install`'s demonstration still prints its validate stage.
5a. After US3 lands, prove the two corpus controls of trap 23 still control
   something: run `tests/test_089_validate_checks_fixes.py` and
   `tests/test_102_unprovable_criteria.py` with their disabling helper turned
   into a genuine no-op by hand — patching a name nothing calls — and confirm
   the corpus comparison goes **red**. A control that stays green when it is
   disabling nothing is the defect this step exists to catch, and it is
   invisible to the suite. Then confirm
   `grep -rn "cli.nouns.spec" tests/` names no relocated layer function.
6. Confirm `grep -rn "_vacuous_registry" factory/cli/nouns/spec.py` returns
   nothing after US5 and that `tests/test_062_us3_skills.py` still asserts the
   registry's empty `skills`.
7. After US4 lands, run the parity test alone and read its wall-clock time. If it
   is spawning a process per spec, that number says so.

Steps 0 and 1 are the ones that cannot be done after the fact: step 0 because a
stale graph is read at dispatch and never mentioned again, step 1 because it is
what makes the empty diffs at steps 3 and 4 mean anything. Do both first.
