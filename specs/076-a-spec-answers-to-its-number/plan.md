# Implementation Plan: a spec answers to its number

**Spec**: `specs/076-a-spec-answers-to-its-number/spec.md`

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## What already exists, and where

**The four verbs that take a spec, and the five bare `Path()` calls that resolve
one.** The argument is registered as a directory in two noun modules:
`factory/cli/nouns/spec.py:137` — `_add_spec_parser` (validate),
`factory/cli/nouns/spec.py:159` — `_add_spec_parser` (derive),
`factory/cli/nouns/spec.py:219` — `_add_spec_parser` (landed) and
`factory/cli/nouns/build.py:2111` — `add_parser` (`build ship`). All four read:

```python
    validate_cmd.add_argument("spec_dir", help="the feature directory holding spec.md")
```

The handlers then turn the string straight into a path, with no resolution and
no specs-root join:

- `factory/cli/nouns/spec.py:491` — `_validate_command`
- `factory/cli/nouns/spec.py:256` — `_derive_command` (the sentinel gate, which
  reads the trio off disk before delegating)
- `factory/workgraph/cli.py:175` — `landed_command`
- `factory/workgraph/cli.py:307` — `derive_command`
- `factory/cli/nouns/build.py:1034` — `ship_command`

`ship_command` is the one the draft did not know about: spec 106 landed it on
2026-08-25 and it computes its own epic id at
`factory/cli/nouns/build.py:1035` — `ship_command` before delegating to
`validate_spec_command` and `derive_spec_command`
(`factory/cli/nouns/spec.py:275` — `validate_spec_command`,
`factory/cli/nouns/spec.py:285` — `derive_spec_command`), handing them the same
`Namespace`. It reaches them through a **deferred import inside the function
body**:

```python
def ship_command(args: argparse.Namespace) -> int:
    # docstring elided
    from factory.cli.nouns.spec import derive_spec_command, validate_spec_command
```

at `factory/cli/nouns/build.py:1031`, landed by 106-US4 and deferred on purpose
— at module scope it is a cycle. It sits **three lines above** the
`factory/cli/nouns/build.py:1034` — `ship_command` anchor T013 sends you to, and
it is not yours to touch; read trap 8 before you edit that function. It is also
a **writer and a dispatcher**: it derives, then calls
`factory/cli/nouns/build.py:1230` — `_confirm_dispatch` and starts the epic. See
trap 18 before you put it in an evidence command line.

**The writer half of the identity rule is already in the tree, and it is the
rule to copy.** `factory/cli/nouns/spec.py:302` — `_pick_spec_number` reads the
pattern assigned at `factory/cli/nouns/spec.py:299`, under its doc comment at
`factory/cli/nouns/spec.py:298`:

```python
#: Direct child directory name matching `<NNN>-<slug>`.
_SPEC_NUMBER_RE = re.compile(r"^(\d+)-")
```

and, over the direct children of the specs root, builds `seen[int] -> [names]`,
refusing before it mints anything when any number has more than one name:

```python
    duplicates = [number for number, names in seen.items() if len(names) > 1]
    if duplicates:
        duplicates.sort()
        raise OperatorError(
            f"specs root {specs_root} has multiple directories claiming number "
            f"{', '.join(f'{n:03d}' for n in duplicates)}; refusing to guess"
        )
```

That is FR-002 and FR-003 already written, for the writer. `^(\d+)-` consumes
the **whole** leading digit run, so the value it yields is an integer — `07` is
seven, not a prefix of seventy. The reader must agree with it or `spec new` will
mint numbers the resolver cannot find. (`_SPEC_NUMBER_RE` is a module constant,
so the symbol tier cannot machine-check that citation — the tier reads function
and class definitions only, `factory/cli/nouns/spec.py:825` — `_symbol_spans`.
Re-read line 299 by eye whenever this plan is re-anchored.)

**Where a shared resolver can live.** `factory/cli/nouns/spec.py:47` already
imports `DEFAULT_SPECS_ROOT`, `SPEC_NAME`, `_resolve_identity_path`,
`_target_repo_for_spec`, `derive_command` and `landed_command` from
`factory.workgraph.cli`, and `factory/cli/nouns/build.py:147` imports
`DEFAULT_SPECS_ROOT` from the same module. Both constants live there —
`factory/workgraph/cli.py:61` (`SPEC_NAME`) and `factory/workgraph/cli.py:65`
(`DEFAULT_SPECS_ROOT`) — beside the existing argument resolver
`factory/workgraph/cli.py:282` — `_resolve_identity_path`. A second
`SPEC_NAME` already exists at `factory/roadmap/models.py:57`; do not add a
third.

**The specs-root sentinel a landed fix depends on.** `derive_command` decides
what to compile into the graph by comparing the raw flag value against the
default string:

```python
    if args.specs_root == DEFAULT_SPECS_ROOT:
        specs_root = str(spec_dir.resolve().parent)
    else:
        specs_root = _resolve_identity_path(
            args.specs_root, "--specs-root", must_exist=True
        )
```

at `factory/workgraph/cli.py:332` — `derive_command`. The comment above it
records the outage that produced it: in the demo container the working directory
is the image root, so a graph compiled with the CWD-relative default carried
`specs_root: '/opt/ergane/specs'` and every dispatch was refused. The finding is
`workgraph/derive-resolves-specs-root-against-the-cwd-not-the-target-repo`,
resolved, and its regression suite is `tests/test_derive_specs_root_default.py`
— which already builds the two-root fixture US1-S9 needs (a repo under
`tmp_path/repo`, a decoy `specs/` under `tmp_path/image-root`, `monkeypatch.chdir`
to the decoy) and already asserts `graph["specs_root"] == str(repo / "specs")`.
Extend it; do not rebuild it.

**The identity a resolved directory has to preserve.** The epic id **is** the
directory name, computed at four sites:
`factory/cli/nouns/spec.py:498` — `_validate_command`,
`factory/workgraph/cli.py:314` — `derive_command`,
`factory/workgraph/cli.py:182` — `landed_command` and
`factory/cli/nouns/build.py:1035` — `ship_command`, all reading
`epic_id = spec_dir.resolve().name`.

**The corpus pass, and what it does *not* hold.**
`factory/roadmap/models.py:411` — `read_roadmap` parses every spec's
**frontmatter** into `factory/roadmap/models.py:126` — `SpecEntry`;
`factory/roadmap/models.py:570` — `compute_readiness` turns that into
`factory/roadmap/models.py:516` — `SpecReadiness`, which carries `spec_dir`,
`state`, `dispatchable`, `blockers`, `satisfied_as`, `drifted` and
`rendered_state` — **and no counts of any kind**.
`factory/roadmap/cli.py:46` — `render_command` calls both and hands the result
to `factory/roadmap/cli.py:92` — `_render_roadmap`, whose docstring states the
row contract US3 must not break: "Reads the corpus from disk (no service) … A
blocked spec names its unsatisfied dependencies on its line, so the operator's
next move … is on the line — never a bare 'blocked'." The row is built at
`factory/roadmap/cli.py:108` — `_render_roadmap` onward, two ljust'd columns
plus an optional `blocked by:` tail.

Two facts about that pass decide US3, and the old plan had both wrong.
`render_command` passes **only** `drifted_for` — it supplies no `landed_for` at
all — and even when one is supplied, `compute_readiness` consults it once per
dependency edge and it returns a boolean `LandedStatus`, never a count. And the
resolver it does pass says in its own docstring at
`factory/roadmap/cli.py:78` — `_cli_drift_resolver` that "The render command
must work on a laptop with no factory running (US1). It therefore cannot read
the target repo's landing history." US3 is amending that contract; see traps 13
and 17.

**The landed-per-spec readers that already exist, and the fetch rule they obey.**
`factory/workgraph/landed.py:130` — `landed_facts` is the one scanner, and its
signature is `landed_facts(repo, spec_dir, *, default_branch, fetch=True)`. Its
docstring at `factory/workgraph/landed.py:145` — `landed_facts` is the rule this
spec's reporting verbs live under:

```
    `fetch` is the read-only caller's opt-out (046 FR-002). Derivation and drift
    detection decide what an epic builds, so they must not read a stale baseline
    and they keep the default. A *reporting* caller must not touch the network
    or write a remote-tracking ref to answer a question, so `ergane status`
    passes `fetch=False` and says on its own output that the answer was read
    without fetching …
```

The default really does fetch: `factory/workgraph/landed.py:273` —
`_resolve_default_head` runs `git fetch --quiet origin` whenever the repo has an
`origin` remote. `ergane status` is the written precedent for the reporting
side: `factory/cli/status.py:469` — `_observed_landing` calls
`factory/cli/status.py:483` — `_observed_landing`
(`landed_facts(repo, spec_dir, default_branch=branch, fetch=False)`) over the
story keys from `factory/cli/status.py:491` — `_declared_story_keys`, cached one
scan per spec by `factory/cli/status.py:441` — `_observed_landed_resolver`; the
repository and branch come from `factory/cli/status.py:425` — `_repo_holding`
and `factory/cli/status.py:401` — `_readiness_basis`, which calls
`factory/workgraph/worktree.py:1471` — `landing_branch` and, when there is no
repository or no readable branch, returns a labelled degrade instead of a
number. That whole chain is what FR-011 and FR-016 mean by "the reader"; US2
builds the one-spec form of it and US3 reuses it.

**The branch order the printing command carries.** `landed_command` resolves the
repo at `factory/workgraph/cli.py:183` — `landed_command` through
`factory/workgraph/cli.py:474` — `_target_repo_for_spec`, then:

```python
    default_branch = args.default_branch or landing_branch(repo)
```

at `factory/workgraph/cli.py:186` — `landed_command`, whose comment states the
order: "explicit flag, then manifest declaration, then today's literal 'main'.
The parser default must be None or the manifest can never win." Copy that
**order**. Do not copy the call that follows it — see trap 10.

**The degrade pattern US2 must reuse rather than reinvent.**
`factory/cli/status.py:284` — `collect_floor` reads the corpus first, on
purpose — "it is the half that survives an outage, and doing it before the
client is opened means a Temporal failure cannot cost it" — then opens the
client and catches three distinct things: the `OperatorError` the opener raises,
the transport tuple at `factory/cli/status.py:147`, and the query-refusal tuple
at `factory/cli/status.py:154`. The comment above them says why neither tuple is
a place to add `Exception`: "the command would stop dying and start lying".
`factory/cli/status.py:364` — `_entries` is how a corpus is narrowed to one
state, which is FR-012's precedent.

**The one-epic reading FR-015 needs, and where it is not.** `collect_floor`
lists *running* epics, which is a different question. The only single-epic
reader in the tree is `factory/cli/nouns/build.py:1119` — `_query_status`, and
it prints and returns an exit code rather than returning data, so there is no
value in it to reuse — importing it would buy a printed line and an exit code,
not an epic state. So `show` composes the pieces itself: `client.get_workflow_handle(workflow_id(epic_id))` with
`factory/workgraph/cli.py:160` — `workflow_id`, `await handle.query("epic_status")`
driven through `asyncio.run` the way
`factory/cli/nouns/build.py:1005` — `status_command` drives `_query_status`, and
the two guard tuples above around the query. That is the plumbing US2's sizing
paragraph counts.

**The task-count reader.** Task ids are recognised by the regex at
`factory/workgraph/preflight.py:329`, which the slice-coverage layer already
reads; `factory/cli/nouns/spec.py:788` — `_tasks_text` is how the trio's tasks
document is read off disk.

## Traps

**1. Every line number in this plan moves when 133 lands — re-anchor before you
edit anything.** All FRs. `depends_on_landed` names
`133-spec-validate-has-one-implementation-and-two-faces`, and 133 moves ten
validation layer bodies out of `factory/cli/nouns/spec.py` into a new
`factory/spec/` package and rewrites `_validate_command` into a renderer over
one composition. That is roughly a thousand lines leaving a 1,865-line module,
so every `factory/cli/nouns/spec.py:NNN` below is stale by the time you read it.
Two anchors this plan depends on are the ones 133 is *least* likely to move —
`factory/cli/nouns/spec.py:137` — `_add_spec_parser` and the argparse block
around it. "Least likely" is the honest claim, not "excluded": 133's NOT IN
SCOPE names the sentinel gate in `_derive_command`, `spec new`, `spec derive`
and `spec landed`, and is silent about the `validate` parser registration. By
contrast `factory/cli/nouns/spec.py:491` — `_validate_command` is inside the
function 133 rewrites. Anchor to the symbol, re-read it, and where 133 declares a shape
(`validate_spec(spec_dir, *, target_repo, specs_root)`) prefer that shape over a
line number. The wrong move is to trust a number here and edit the line it names.

**2. A number is an integer, not a prefix — and the draft of this spec taught
the opposite.** FR-002, US1-S5. The `^(\d+)-` at
`factory/cli/nouns/spec.py:299` consumes the whole digit run, so `07` is the
number seven and matches `007-…` alone.

Here is the failure, on a corpus where a prefix matcher is single-valued and so
answers instead of refusing: a specs root holding `070-alpha` and nothing else
whose name begins `07`. Integer equality refuses `07` there — no spec is
numbered seven. `name.startswith(value)` finds exactly one candidate, returns
`070-alpha`, is right for months, and then derives the wrong spec — and `derive`
overwrites `workgraph.json`, so the damage is a graph that looks fine and builds
the wrong thing.

This repository's own corpus **hides** that failure rather than showing it, and
the draft of this plan claimed the opposite. Ten directories begin `07` here at
`602a92c` — `070-…` through `079-…` — so a prefix matcher finds ten and refuses
under FR-003, while integer equality resolves `07` to
`specs/007-parallel-dispatch`, which exists. Do not write a live-corpus check
that demands a refusal for `07`; it demands the one answer FR-002 forbids.
US1-S5's fixture is where the two designs are told apart: `070-…` beside
`071-…`, where a prefix
matcher produces a refusal naming both neighbours and the scenario asserts the
refusal names neither. The tempting move
is to make prefixes "helpful"; US1-S5 exists to make that a failing test. Note
the second half of US1-S5's proof clause: the refusal must name the **specs
root**, because today's do-nothing failure already prints `cannot read
07/spec.md` and already mentions neither neighbour, so a test written to the
negative half alone is green before you write a line.

**3. Ambiguity refuses; it never picks.** FR-003, US1-S4. With integer equality
the ambiguous case is reachable only from a corpus where two directories claim
one number — `070-alpha` beside `70-beta`. It is rare, it is a real corpus
defect, and `_pick_spec_number` already refuses to mint into it with a message
naming the duplicates. Copy that refusal's shape; do not take the first match,
the lowest, or the "best" one. Note for the fixture: you cannot build that corpus
with `ergane spec new`, because `_pick_spec_number` refuses first — make the
directories by hand.

**4. The path form is load-bearing and must not regress.** FR-005, US1-S3. Every
runbook, every `~/ergane-ops` note and the roadmap's own dispatch pass a path in
full, and some pass an absolute path whose parent is not the specs root. This
story *adds* an accepted form. Try the path first — `Path(value).is_dir()` — and
fall back to number resolution only when it is not a directory. A change that
normalises everything through the matcher breaks the absolute-path caller, and
that caller is the demo container.

**5. `--specs-root` is not on every verb, and assuming it is crashes the one that
lacks it.** FR-006, US1-S7. `validate` registers it at
`factory/cli/nouns/spec.py:144`, `derive` at `factory/cli/nouns/spec.py:166` and
`build ship` at `factory/cli/nouns/build.py:2118`. `landed` registers
`--default-branch` and `--json` and nothing else — read
`factory/cli/nouns/spec.py:219` through the end of that block. A resolver that
reads `args.specs_root` unconditionally raises `AttributeError` on
`ergane spec landed 076`. Use `getattr(args, "specs_root", DEFAULT_SPECS_ROOT)`
or resolve the root at each call site.

**6. Do not rebind `args.specs_root`; that value is compared, not used — and the
only differential that can catch you is the demo-container one.** FR-014,
US1-S9. `factory/workgraph/cli.py:332` — `derive_command` tests
`args.specs_root == DEFAULT_SPECS_ROOT` — an equality against the literal
default string — to decide whether the compiled graph gets the spec directory's
own parent or the flag's resolved path. The obvious implementation of FR-006
("join the specs root, then write it back so everything downstream agrees")
flips that comparison to False for *every* caller, path callers included, and
re-opens `workgraph/derive-resolves-specs-root-against-the-cwd-not-the-target-repo`,
which cost a whole demo run. Resolve into a local, return the directory, leave
the namespace alone.

The subtle half is how you prove it. Deriving the **same spec under the default
root** by number and by path cannot fail on the rebind: the resolved directory's
parent and the joined default root are the same absolute path there, so both
branches of the comparison produce the same `specs_root` and both
implementations pass. The regression is visible only where the two disagree —
an absolute spec directory whose parent is **not** `<cwd>/specs`, run from a
working directory that is not the repo. That is the shape the comment at
`factory/workgraph/cli.py:316` — `derive_command` records and the shape
`tests/test_derive_specs_root_default.py` already builds. Extend that suite, and
assert directly that `args.specs_root` still holds the literal default string
after resolution has run.

**7. The epic id comes from the directory name, at four sites in three
modules.** FR-013, US1-S8. `epic_id = spec_dir.resolve().name` is computed at
`factory/cli/nouns/spec.py:498` — `_validate_command`,
`factory/workgraph/cli.py:314` — `derive_command`,
`factory/workgraph/cli.py:182` — `landed_command` and
`factory/cli/nouns/build.py:1035` — `ship_command`. Resolution must return the
actual directory, never a constructed path that merely reads the right
`spec.md`. A test that resolves `075` and asserts the epic id is the full slug
at every one of those four sites is the cheap guard, and it is the difference
between this story working and producing epics named `075`.

**8. The resolver has one home both noun modules already import — and the
sibling import you will find in `build.py` is landed code, not a violation to
clean up.** FR-001, FR-013. Read this before you edit `ship_command`.

The premise this trap used to carry was false, and it was dangerous in exactly
the place the implementer stands. `factory/cli/nouns/build.py:1031` reads
`from factory.cli.nouns.spec import derive_spec_command, validate_spec_command`,
deferred inside `ship_command`'s body — 106-US4 landed it so `ergane build ship`
could delegate validate and derive, and deferring it is how the module cycle is
avoided. **Leave it exactly where it is.** T013 edits
`factory/cli/nouns/build.py:1034` — `ship_command`, three lines below that
import, so an implementer holding "build.py must not import spec.py" meets the
import while editing and does the tidy-up: hoists it to module scope, which is a
cycle, or deletes it as a layering violation, which breaks `ergane build ship`
— one of the four verbs FR-001 is about, and the one US1-S8 asserts an epic id
for.

Where the *resolver* goes is decided on other grounds, and those grounds are
sufficient on their own. `factory/workgraph/cli.py` already holds `SPEC_NAME`
(`factory/workgraph/cli.py:61`), `DEFAULT_SPECS_ROOT`
(`factory/workgraph/cli.py:65`) and the sibling argument resolver
`factory/workgraph/cli.py:282` — `_resolve_identity_path`, and **both** noun
modules already import from it at module scope (`factory/cli/nouns/spec.py:47`,
`factory/cli/nouns/build.py:147`) — so putting it there adds no import edge to
either module and needs no second deferred import. Put it there and export it
under a public name. Putting it in `factory/cli/nouns/spec.py` instead would
make `build.py` reach a second symbol across that deferred import, and it
collides head-on with 133, which is deleting from that module.

**9. `show` must not need a service, and the guard is already written down.**
FR-009, US2-S4. `factory/cli/status.py:284` — `collect_floor` reads the corpus
*before* opening a client, and catches exactly three things: the `OperatorError`
the opener raises, `factory/cli/status.py:147`'s transport tuple, and
`factory/cli/status.py:154`'s query-refusal tuple. The comment above those
tuples is the trap in the author's own words — a blanket `except Exception`
"would have fixed the symptom and converted every future defect behind one into
a blank section with a plausible note — the command would stop dying and start
lying". `spec list` and `spec validate` both work on a laptop with no factory
running, and an operator's first instinct on a broken floor is to run a status
command. If `show` connects unconditionally it becomes the one spec verb that
fails when it is needed most.

**10. Reuse `landed_facts`, not `landed_command` — and pass `fetch=False`, or
`show` writes a remote-tracking ref and dies offline.** FR-008, US2-S2. This is
the trap the old plan got backwards: it sent `show` at `landed_command`'s
reader, and that reader fetches.
`factory/workgraph/landed.py:130` — `landed_facts` defaults to `fetch=True`;
`factory/workgraph/cli.py:168` — `landed_command` calls it with no `fetch`
argument, so `derive`'s
network-touching default is what a printing command keeps;
`factory/workgraph/landed.py:273` — `_resolve_default_head` then runs
`git fetch --quiet origin` on any repo with an origin, and a failure there
surfaces as an `OperatorError`. The rule is written in `landed_facts`' own
docstring at `factory/workgraph/landed.py:145` — `landed_facts`: "A *reporting*
caller must not touch the network or write a remote-tracking ref to answer a
question, so `ergane status` passes `fetch=False`". `show` is a reporting
caller. Call `landed_facts(repo, epic_id, default_branch=…, fetch=False)`
directly, the way `factory/cli/status.py:483` — `_observed_landing` does, keep
`landed_command`'s branch **order** (flag, manifest, `main`), and say on the
output that the answer was read without fetching. Put that call behind **one
named, per-spec-cached reader** rather than inline in `show`'s body: FR-008
requires it and FR-011 makes US3 import the same object, so an inline call here
guarantees US3 writes the second landed implementation FR-011 forbids.

The reason this one is expensive rather than merely wrong: a `tmp_path` fixture
repo has no `origin`, so `_resolve_default_head` skips the fetch and US2-S2
passes green either way. The assertion that catches it has to be explicit —
assert the reader was called with `fetch=False`, or that no `git fetch` ran.
Without it, the offline box is where you find out.

Two details decide whether the copied branch order compiles at all. Its first
arm is `args.default_branch`, so `show`'s parser must register
`--default-branch` with a `None` default — copy the order onto a parser that has
no such flag and every `ergane spec show` run raises `AttributeError`, which is
trap 5 reappearing inside code US2 is writing. And take the repository from
`factory/cli/status.py:425` — `_repo_holding`, not
`factory/workgraph/cli.py:474` — `_target_repo_for_spec`. The first tests `.git`
for *existence*, which its docstring says is deliberate: in a git worktree
`.git` is a file. The second requires a directory and, failing to find one,
falls back to `spec_dir.parent.parent.parent`. Every node runs in a worktree.

**11. A filter that matches nothing emits nothing.** FR-012, US3-S3. The
tempting implementation returns the unfiltered list when the filter matches zero
rows, because an empty screen "looks broken". An empty result *is* the answer,
and a silent fallback to everything is how an operator concludes there is work
ready when there is none. Say so in one line and emit no spec row.

**12. `list` is one line per spec, and that is the invariant — not a frozen
render.** FR-011, US3-S4. `factory/roadmap/cli.py:92` — `_render_roadmap`
promises the blocked-spec case names its blockers on the line, and the row is
two ljust'd columns built from `factory/roadmap/cli.py:108` — `_render_roadmap`
onward. US3 adds a column; it does not restructure the row into a block, and it
must not push the blockers off the line or widen the columns so far that a
141-spec corpus wraps. Read US3-S4 carefully: it asserts *those three
invariants*, not that the unflagged output is unchanged. It cannot assert that,
because FR-011 changes the unflagged output on purpose — a control written as
"equals a committed golden capture" would either forbid the column US3-S1
requires or pin whatever the implementer happened to produce. If you keep a
golden file at all, keep it as a committed BEFORE capture and assert that the
only difference is the added column.

**13. The pass that computes readiness holds no landing data — the count is new
work, not a field you missed.** FR-011, US3-S1. `read_roadmap`
(`factory/roadmap/models.py:411` — `read_roadmap`) parses **frontmatter** and
skips the body; `SpecEntry` (`factory/roadmap/models.py:126` — `SpecEntry`)
carries `spec_dir`, `state`, `depends_on_landed`, `source` and `fixes`, and no
stories; `SpecReadiness` (`factory/roadmap/models.py:516` — `SpecReadiness`)
carries `dispatchable`, `blockers`, `satisfied_as`, `drifted` and no counts; and
`render_command` (`factory/roadmap/cli.py:46` — `render_command`) passes no
`landed_for` at all. The old plan told you to take the count "from that same
pass". You cannot; there is nothing there to take. What survives of that
instruction is the honest half — **one frontmatter walk, not two** — so the
state column and the count column cannot come from two reads that disagree.

The count itself is built the way `ergane status` builds its observed-landed
answer: total from the declared stories (`factory/cli/status.py:491` —
`_declared_story_keys`), landed from `factory/workgraph/landed.py:130` —
`landed_facts` with `fetch=False`, repository from
`factory/cli/status.py:425` — `_repo_holding`, branch from
`factory/cli/status.py:401` — `_readiness_basis` via
`factory/workgraph/worktree.py:1471` — `landing_branch`. Never `main` by
default: `CLAUDE.md` carries that trap in as many words, because the factory
lands on the buildout branch and `main` moves only when an operator promotes, so
a `main` default under-reports the whole corpus between promotions. US3 **imports** the
named reader US2 built for FR-008 — FR-008 requires it to be a named,
per-spec-cached callable precisely so there is an object here to import; a
second implementation is what drifts.

**14. The render's own docstring says it cannot read landing history — you are
amending a decision, and it has a price.** FR-011, FR-016, US3-S5.
`factory/roadmap/cli.py:78` — `_cli_drift_resolver` states it plainly: "The
render command must work on a laptop with no factory running (US1). It therefore
cannot read the target repo's landing history." A landed count makes `list` shell
git once per spec — one cached scan per spec, over 141 directories at `602a92c`,
and `ergane spec landed` over all specs is already recorded in project memory as
timing out. Two obligations follow and FR-016 is both of them. The laptop case
must still work: no repository, or no resolvable branch, renders `unknown` and
one explanatory line — never `0`, which reads as "landed nothing", and never a
traceback. And the scan must be cached per spec the way
`factory/cli/status.py:441` — `_observed_landed_resolver` caches it, not
recomputed per row or per dependency edge. The wrong move is to make the count
unconditional and discover the cost on the operator's corpus.

**15. Determinism is not at issue; the fixture corpus is.** All stories. These
are CLI verbs, not workflow code, so clocks and the filesystem are fine. What is
not fine is testing against this repository's own `specs/` — 141 directories at
602a92c, refined weekly, and the numbers this spec's own scenarios name would
drift under the test. Every story builds its corpus under `tmp_path`.

**16. The judge sees the diff and the criteria, and nothing else.** All stories.
`factory/verify/criteria.py:17` states which parts of a spec are criteria: the
story headers, the acceptance scenarios and the FR bullets, and everything else
is read past. This spec carries no `## Success Criteria` section for that
reason — the operator's own verification lives at the end of this plan and in
the trailing tasks phase, where no node reads it. Every Then above is written
"proven by a committed test" so it is decidable from the diff alone.

**17. Two suites already exist for the two hardest scenarios — extend them.**

- US1 → `tests/test_spec_number_resolution.py` is new, **but** US1-S9 belongs in
  `tests/test_derive_specs_root_default.py`, the landed regression for the fix
  FR-014 protects: it already builds the repo/decoy-root/`chdir` fixture and
  already asserts the compiled `specs_root`. Adding the by-number case and the
  "`args.specs_root` unchanged" assertion there means a future FR-014 breakage
  fails the suite that exists to catch it.
- US1-S1 and US1-S8 need `build ship` driven end to end;
  `tests/test_ergane_build_ship.py` (19.9 KB) already does that. Copy its shape
  rather than inventing a third harness.
- US2 → `tests/test_spec_show.py` (new).
- US3 → `tests/test_spec_list_filters.py` (new).

**18. Two of the four verbs write and one of them dispatches — keep them out of
"run it twice and diff it".** All stories, and T015 in particular.
`ergane spec derive` writes `<spec-dir>/workgraph.json` unless `-o` sends it
elsewhere, and `specs/*/workgraph.json` is tracked in this repository — the open
finding `cli/spec-derive-json-rewrites-the-committed-artifact` is exactly this
mechanism, and it is how a stale `target_repo` reached two committed graphs.
`specs/076-a-spec-answers-to-its-number/` has **no** compiled graph at
`602a92c`; an evidence command that derives it manufactures one inside the
node's own worktree, the node commits it into the US1 PR, and `build start`
reads a compiled graph off disk. `factory/cli/nouns/build.py:1029` —
`ship_command` is worse: it validates, derives, prints the summary, then calls
`factory/cli/nouns/build.py:1230` — `_confirm_dispatch`, which takes EOF as a
decline (so a non-interactive run prints "ergane: ship cancelled" and returns
`EXIT_USER`), and the obvious fix for that — `--yes` — **dispatches epic 076**.
Both `derive` and `ship` also take a `required=True --target-repo`
(`factory/cli/nouns/build.py:2114`). Paste evidence only for the read-shaped
verbs, and prove `ship` by committed test instead (US1-S8 already does).

## Sizing

Three stories, chained, each sized to stay under the 65,536-byte deterministic
diff refusal — `DIFF_REFUSAL_THRESHOLD` at `factory/verify/diffbounds.py:66`,
which is defined as, and today equals, the judge's input allowance
`DIFF_INPUT_LIMIT` at `factory/verify/diffbounds.py:47`. `ergane.yaml` sets no
override.

**US1** touches `factory/workgraph/cli.py` (the resolver, plus the two handlers
at `factory/workgraph/cli.py:175` — `landed_command` and
`factory/workgraph/cli.py:307` — `derive_command`),
`factory/cli/nouns/spec.py` (two handlers and three help strings) and
`factory/cli/nouns/build.py` (`ship_command` and one help string), plus
`tests/test_spec_number_resolution.py` and a new case in the existing
`tests/test_derive_specs_root_default.py`. Three production files, one new test
file and one extended one; the resolver itself is one function of roughly the
size of `_pick_spec_number`. Its whole difficulty is traps 2, 4 and 6 — integer
not prefix, path-first, and leaving the namespace alone.

**US2** touches `factory/cli/nouns/spec.py` (the new `show` verb, its parser
registration — the spec argument, `--json` and `--default-branch` — its document
object and its render), plus
`tests/test_spec_show.py`. It writes **one small named reader and no new
scanner.** FR-008 requires the landed half to be a named, per-spec-cached
callable — the one-spec analogue of
`factory/cli/status.py:441` — `_observed_landed_resolver` — wrapping a direct
`landed_facts(..., fetch=False)` call with `landed_command`'s branch order, and
FR-011 makes US3 import that same object rather than write a second landed
implementation. It is a seam of a few lines around an existing scanner, not a
scanner; US3's paragraph below reuses it, and the two paragraphs must keep
saying the same thing. The rest is composition: the blockers come from
`compute_readiness`, and the epic state is
`client.get_workflow_handle(workflow_id(epic_id))` plus
`await handle.query("epic_status")` under the two guard tuples at
`factory/cli/status.py:147` and `factory/cli/status.py:154`, driven through
`asyncio.run` — roughly twenty lines, not a second status module. Its difficulty
is traps 9 and 10: degrading without a control plane, and not fetching.

**US3** touches `factory/roadmap/cli.py` (the count column and the state filter
on `_render_roadmap` and `render_command`, plus the degrade line),
`factory/cli/nouns/spec.py` (the `--state` flag on the `list` parser) and one
landed-count seam — the named cached per-spec reader US2 built for FR-008,
**imported rather than reimplemented**, passed
into `render_command` the way `factory/cli/status.py:441` —
`_observed_landed_resolver` is passed into `compute_readiness`, so the offline
render keeps working when the seam answers `None`. Plus
`tests/test_spec_list_filters.py`. Its difficulty is trap 14: a git-backed
column on a command whose docstring says it is disk-only.

**The evidence each story pastes counts against the same allowance as its
code** (D-050), and **US3 is the story where that binds** — not US1, which is
what the draft of this paragraph said. Measured at `602a92c`, one full
`ergane spec list specs` render is 144 rows and 11,965 bytes; FR-011's count
column adds roughly eight characters a row, so one render is about 13 KB, and
about the same again once it is added diff lines. Two full renders would be some
27 KB of evidence before a line of US3's code — in a story that also carries
`tests/test_spec_list_filters.py` with a two-branch git fixture. T036 therefore
pastes **excerpts** with a stated row count, never whole renders. US1 is the
next tightest and T015 is trimmed the same way: two `diff` invocations, one
refusal and one summary line, not eight transcripts. US2 pastes one short
report.

**Which stories share no production file**: none. US1 and US2 both edit
`factory/cli/nouns/spec.py`; US2 and US3 both edit it too. That is why the Work
Graph is a chain rather than three parallel nodes, and why every edge is
`depends_on_merged`.

## Verification the operator will run, independent of the gate

1. **Prove US1 by agreement, on the two verbs that only read.** Run
   `ergane spec validate` and `ergane spec landed` twice each — once with `076`,
   once with `specs/076-a-spec-answers-to-its-number` — and diff the two
   outputs. They must be identical apart from any echo of the argument itself.
   Do **not** put `spec derive` or `build ship` in this step: derive writes a
   tracked `workgraph.json` and ship dispatches (trap 18). Their resolution is
   proven by US1-S8's committed test instead.
2. **Prove the no-prefix rule on the live corpus, in both directions.** Run
   `ergane spec validate 07 --target-repo .`. Under FR-002 `07` is the number
   seven, so it must **resolve** — to `specs/007-parallel-dispatch`, which
   exists at `602a92c`; the summary lines name the spec path, so read them. It
   must not refuse and it must not mention
   `070-a-story-can-choose-who-builds-it`: a prefix matcher finds every
   directory whose name begins `07` — ten of them at `602a92c`, `070-…` through
   `079-…` — and refuses under FR-003, so this run is the discriminator. Then
   prove the miss with a number no directory claims: run
   `ergane spec validate 999 --target-repo .` and read the refusal, which must
   name `999` **and** the specs root it searched. Today that command prints
   `cannot read 999/spec.md` and names no root, so the root is the half that
   proves production code ran.
3. **Prove FR-014 by artifact, from a foreign working directory.** From a
   directory that is not this repository and that itself contains a decoy
   `specs/`, run
   `ergane spec derive /home/admin/code/ergane/specs/076-a-spec-answers-to-its-number
   --target-repo /home/admin/code/ergane -o <a scratch path>` with no
   `--specs-root`, and read the compiled graph's `specs_root`: it must be
   `/home/admin/code/ergane/specs`, never the decoy under the working directory.
   Use `-o` so the tracked artifact is not written (trap 18). Running the same
   comparison from inside the repository proves nothing — both branches agree
   there.
4. **Prove US2 against a known answer, and prove it does not fetch.** Run
   `ergane spec show 076` beside `ergane spec landed
   specs/076-a-spec-answers-to-its-number --default-branch ergane-buildout`; the
   landed counts must agree. Then run `show` again with
   `GIT_TRACE=1` or on a box with no route to the remote, and confirm no
   `git fetch` appears and the report says the answer was read without fetching.
   Then stop the control plane (`systemctl --user stop` the worker, or point at
   a dead address) and run `show` once more: every disk fact must still be there
   and the epic state must read unknown.
5. **Prove US3 by absence, and by degrade.** Run `ergane spec list specs
   --state ready` beside the unfiltered list and confirm the filtered render
   holds only the ready row. The empty-match case has no live corpus to run on —
   at `602a92c` every state the enum accepts has a member (102 `landed`, 40
   `draft`, 1 `ready`, 1 `deferred`), so `--state landed` matches a hundred
   specs rather than none. Prove it on the copy instead: copy `specs/` into a
   directory no git repository holds, delete the one `deferred` spec from the
   copy, and run `--state deferred` there — one line, no spec row. That same
   copy is the degrade check: run `list` over it unfiltered and every count must
   read `unknown`, with the explanatory line present.
6. **Prove the anchors survived 133.** Before dispatch, re-run
   `ergane spec validate specs/076-a-spec-answers-to-its-number --target-repo .
   --specs-root specs` against the tree 133 landed on. A refusal here is trap 1
   firing, and it is cheaper than an implementer meeting it.
