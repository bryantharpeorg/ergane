# Implementation Plan: declaring a spec ready is a verb that can refuse

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

Nothing under `factory/spec/` is cited by line, and that is deliberate: that
package does not exist at `602a92c` — `ls factory/spec` errors — and is created
by `133-spec-validate-has-one-implementation-and-two-faces`, this spec's
`depends_on_landed` edge. Names from that package are written in prose. An
anchor into a file 133 has not landed yet is a stale-anchor refusal today.

**And the reverse holds for eight citations on this page: they are coordinates in
the pre-133 tree, not edit sites.** This spec dispatches only after 133 lands,
and 133 moves the validation layers out of `factory/cli/nouns/spec.py` into
`factory/spec/`: its US2 removes the span holding `_DISPATCHABLE_STATES`
(`factory/cli/nouns/spec.py:800`), `_spec_state`
(`factory/cli/nouns/spec.py:803`) and `_check_symbol_anchors`
(`factory/cli/nouns/spec.py:904`, `factory/cli/nouns/spec.py:993`) and the span
holding `_check_anchor_resolution` (`factory/cli/nouns/spec.py:1206`); its US5
removes `_check_frontmatter` (`factory/cli/nouns/spec.py:999`,
`factory/cli/nouns/spec.py:1004`); its US6 removes `_check_evidence`
(`factory/cli/nouns/spec.py:1816`). 133 FR-010, FR-011 and FR-012 hold their
signatures and their refusal strings unchanged across that move, so every
*claim* those citations support survives — this page cites them as evidence for
what a layer does, and no task here edits one of those bodies. Find them by
symbol name in `factory/spec/`, not by the line numbers printed here. The
citations into `factory/cli/nouns/spec.py`'s **parser** — `:113`, `:114`,
`:117`, `:134`, `:156`, `:189`, `:216`, `:236`, `:1` — are the ones US3 really
edits, and 133 leaves them where they are.

## What already exists, and where

**The five verbs, and the shape a sixth and seventh must copy.**
`factory/cli/nouns/spec.py:113` — `_add_spec_parser` builds one subparser per
verb and ends each with `set_defaults(run=...)`: `list` at
`factory/cli/nouns/spec.py:117`, `validate` at `factory/cli/nouns/spec.py:134`,
`derive` at `factory/cli/nouns/spec.py:156`, `new` at
`factory/cli/nouns/spec.py:189`, `landed` at `factory/cli/nouns/spec.py:216`.
The noun is registered immediately below, with its summary string at
`factory/cli/nouns/spec.py:236`. `validate`'s two path flags are the pair the
ready verb needs — and its `--target-repo` default is the one thing on this page
you must **not** copy (trap 14):

```python
    validate_cmd.add_argument("spec_dir", help="the feature directory holding spec.md")
    validate_cmd.add_argument(
        "--target-repo",
        default="/srv/factory/targets/short-links",
        help="worker-host path to the target repo (default: /srv/factory/targets/short-links)",
    )
    validate_cmd.add_argument(
        "--specs-root",
        default=DEFAULT_SPECS_ROOT,
        help=f"where the worker finds feature specs (default: {DEFAULT_SPECS_ROOT})",
    )
```

**The frontmatter reader, and the exact reason a writer must not round-trip it.**
`factory/roadmap/models.py:240` — `_split_frontmatter` returns the block's YAML
text with the fences stripped, or `None` when the first line is not `---`. It is
a *lossy* splitter, and trap 1 turns on that: it does `text.splitlines()` and
returns two `"\n".join(...)` halves, so the trailing newline and any CRLF are
gone from its output.
`factory/roadmap/models.py:260` — `_parse_frontmatter` then hands that text to
`yaml.safe_load`, and `factory/roadmap/models.py:296` — `_shape_entry` refuses any
key outside the closed set at `factory/roadmap/models.py:117`. The loaded mapping
holds three keys and no comments; every `#` line in every spec's frontmatter —
the whole provenance chain this repository runs on — exists only in the text.
Trap 1.

The declared state itself already has a reader that does exactly this and nothing
more: `factory/cli/nouns/spec.py:803` — `_spec_state` returns the `state` value
from the block or `None`, and 133 FR-010 relocates it into `factory/spec/`
alongside the anchor layers. Reuse it rather than writing a third reading of the
declared state.

**The corpus read is all-or-nothing, and it runs every tick.**
`factory/roadmap/models.py:411` — `read_roadmap` walks each direct child
directory of the specs root, skipping only names beginning with a dot
(`factory/roadmap/models.py:440` — `read_roadmap`), and its docstring says a
corpus with any finding "raises `RoadmapError` and yields no partial roadmap".
`factory/roadmap/workflow.py:494` — `read_corpus_activity` is the only caller in
the dispatch path and its docstring is blunter still: a corpus that does not
parse "is a hard stop, not a parked spec". Traps 2 and 15.

**The one line that arms dispatch.** `factory/roadmap/models.py:570` —
`compute_readiness` computes, at `factory/roadmap/models.py:607` —
`compute_readiness`:

```python
        dispatchable = entry.state is SpecState.READY and not blockers
```

`factory/roadmap/workflow.py:864` — `_run_inner` filters on it at
`factory/roadmap/workflow.py:867` — `_run_inner`, and
`factory/roadmap/workflow.py:1294` — `_dispatch` starts the child epic.
`factory/verify/models.py:222` — `RoadmapDials` sets the tick at
`factory/verify/models.py:235` — `RoadmapDials`, `cadence_s` defaulting to 300.
Trap 9.

**The atomic-write precedent, in this tree, with its reasoning written down.**
`factory/registry.py:353` — `_write_document`:

```python
def _write_document(path: Path, document: Mapping[str, Any]) -> None:
    """Replace the registry atomically; a reader never sees a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(render_registry(document), encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(temporary, path)
```

The `os.replace` is at `factory/registry.py:359` — `_write_document`. The module
docstring states the property at `factory/registry.py:35`. FR-007. Note the
temporary sits *beside* the target, inside the same directory — which for a spec
means inside `specs/<dir>/`, where `read_roadmap` never looks, because it walks
directories and reads only `spec.md` inside each.

**The "has the tree moved" precedent, also in this tree.**
`factory/activities/verify_activities.py:621` — `_has_drifted` is the same guard
for criteria bytes:

```python
def _has_drifted(source: Path, snapshot_sha256: str) -> bool:
    """Whether the spec file's bytes still hash to the dispatch snapshot's (R8).

    A file that cannot be read is drift, not "no drift detected": a deleted spec
    is the loudest possible form of the system of record moving under a node.
    """
    try:
        current = hashlib.sha256(source.read_bytes()).hexdigest()
    except OSError:
        return True
    return current != snapshot_sha256
```

The digest line is `factory/activities/verify_activities.py:628` — `_has_drifted`.
Copy both halves: the digest *and* the rule that an unreadable file counts as
moved. FR-006, trap 3.

**The atomic-directory precedent for a whole spec, one function away.**
`factory/cli/nouns/spec.py:390` — `_new_command` writes the trio into a temporary
directory under the specs root and renames it into place at
`factory/cli/nouns/spec.py:438` — `_new_command`. The prefix it uses begins with
a dot, which is what keeps a half-written spec out of
`factory/roadmap/models.py:440` — `read_roadmap`'s scan. Same discipline, one
level up. (This is also the one verb that *writes*: it creates a trio. None of
the five edits an existing `state:` line, which is the gap.)

**The readiness resolver the verb must reuse, and the three readings that already
exist.** `factory/roadmap/models.py:570` — `compute_readiness` takes `landed_for`
and `drifted_for` and says why at `factory/roadmap/models.py:587` —
`compute_readiness`: "Both resolvers are injected so git reads stay out of
workflow code (constitution IV)." Its three callers inject three different
things.

- `factory/roadmap/cli.py:46` — `render_command` (this is `ergane spec list`,
  reached through `_list_command`) injects only a drift resolver at
  `factory/roadmap/cli.py:63` — `render_command`. No `landed_for` at all, so its
  blockers are attestation-only.
- `factory/cli/status.py:292` injects `factory/cli/status.py:441` —
  `_observed_landed_resolver`, which answers from the repository's landing history
  through `factory/workgraph/landed.py:130` — `landed_facts` and is deliberately
  conservative: `factory/cli/status.py:469` — `_observed_landing` returns `None`
  on any doubt so `compute_readiness` falls back to attestation.
- The roadmap workflow injects its own observed resolver at
  `factory/roadmap/workflow.py:851` — `_run_inner`.

`factory/cli/status.py:378` — `_readiness_basis` is the function that picks
between the second and a degraded attestation-only reading and returns
`factory/cli/status.py:247` — `ReadinessBasis` saying which it chose. That value
is the sentence a refusal owes the operator, and FR-019 makes the plan carry it.
The two helpers those functions read are
`factory/cli/status.py:425` — `_repo_holding`, which walks up from the specs root
to the repository holding it, and
`factory/cli/status.py:491` — `_declared_story_keys`. `_repo_holding` moves for
FR-011 and is then reused by FR-013 as the ready verb's `--target-repo` default.

**Two of the names those bodies read are module-level imports, not local
definitions, and a mover who lists only the six symbols strands them.**
`factory/cli/status.py:378` — `_readiness_basis` calls `landing_branch`, imported
at `factory/cli/status.py:110` from `factory.workgraph.worktree`, and
`_landing_head`, which is *not* defined anywhere in that module: it is an alias
bound at `factory/cli/status.py:106` over
`factory.workgraph.landed._resolve_default_head`. `factory/cli/status.py:469` —
`_observed_landing` reads `landed_facts` from the same import block. Searching
the status module for `def _landing_head` finds nothing, which is the shape of
the wasted cycle: move the imports with the code, as imports. Traps 4, 8 and 14.

**The verdict half, and why it cannot be reached today.**
`factory/cli/nouns/spec.py:490` — `_validate_command` takes an
`argparse.Namespace`, prints, and returns an exit code;
`factory/cli/nouns/spec.py:275` — `validate_spec_command` wraps it so `build ship`
can stream the same stdout. The only other in-tree consumer builds an argv list —
`factory/cli/install.py:1078` — `_spec_validate_argv` — and runs it back through
the entry point from inside the package. 133 replaces all of that with a typed
report; FR-009 calls that report's function. Trap 6.

**A layer that refuses is one finding per fault, not one per layer.**
`factory/cli/nouns/spec.py:993` — `_check_symbol_anchors` appends a
`_ValidateFinding` inside a nested per-file, per-line, per-match loop, so three
bad anchors are three findings at one layer name; `factory/cli/nouns/spec.py:999`
— `_check_frontmatter` does the same at
`factory/cli/nouns/spec.py:1004` — `_check_frontmatter`, one per corpus fault
naming this spec. FR-009 is worded per *refusal* for that reason. Trap 10.

**A layer that does not run is recorded separately, and today that is three of
twelve.** `factory/cli/nouns/spec.py:904` — `_check_symbol_anchors`,
`factory/cli/nouns/spec.py:1206` — `_check_anchor_resolution` and
`factory/cli/nouns/spec.py:1816` — `_check_evidence` append to `skipped` and
return when the target repository cannot be read, and
`factory/cli/nouns/spec.py:1198-1200` says in the tree why that is deliberate:
`--target-repo`'s default "is a path most hosts do not carry, and a layer that
refuses instead of skipping turns every spec into a wall of false refusals".
133 FR-002 carries those skipped layers and their reasons as a separate member of
the report, which is what makes FR-017 implementable. Trap 14.

**The signal that looks like the transition and is not.**
`factory/roadmap/workflow.py:621` — `promote_spec` records a name in a dict, and
`factory/roadmap/workflow.py:1110` — `_apply_promotions` rewrites that spec's
in-memory entry to `ready` for one pass only, saying in its own docstring that
"the file is the authority of record". Trap 5.

**The state vocabulary, and the sentence this spec is careful not to overturn.**
`factory/roadmap/models.py:66` — `SpecState` calls `ready` "the operator's
declaration" and `landed` "an *attestation* for work that predates the roadmap",
and closes at `factory/roadmap/models.py:79` — `SpecState` with "intent is
declared, progress is observed". `CONTEXT.md:243` resolves the naming: the
unqualified word "promote" means the operator's fast-forward of `main`, and the
draft-to-ready transition is called **ready a spec** — which is where this verb's
name comes from. Trap 12.

**The two `state:` lines the tree writes today** are both fresh scaffold blocks,
and neither edits an existing one. `factory/doctor/scaffold.py:157-163` appends
`---`, then `factory/doctor/scaffold.py:158` — `_build_spec_md_from_slots`
appends `state: draft`, then the optional `fixes:` list, then the closing fence;
`factory/doctor/scaffold.py:326` — `_build_spec_md` does the same on the
`findings promote` path. Both render a new block. Nothing in the tree edits one.

## Traps

**Trap 1 — A YAML round-trip writes a file that parses, validates clean, and has
silently destroyed the provenance.** The obvious implementation of FR-003 is:
split the block with `factory/roadmap/models.py:240` — `_split_frontmatter`, load
it with `yaml.safe_load` the way `factory/roadmap/models.py:260` —
`_parse_frontmatter` does, set `state`, dump, re-fence. The loaded mapping holds
the three keys of `factory/roadmap/models.py:117` and nothing else — every `#`
comment line is gone, and with it the dated provenance chain that this
repository's own house rules say must be appended to and never deleted. **Nothing
catches it.** `read_roadmap` does not read comments; `compute_readiness` does not;
`ergane spec validate`'s frontmatter layer checks keys and state values. The
reproduction is the file you are editing: this spec's own frontmatter is more
than a hundred lines of comment around four lines of YAML.

There is a **second lossy route to the same violation**, and it does not involve
YAML at all: reconstructing the file as `"---\n" + block + "\n---\n" + body` from
`_split_frontmatter`'s two return values. That splitter does `text.splitlines()`
and joins with `"\n"`, so the reconstruction silently drops the file's trailing
newline and normalises any CRLF — a whole-file diff, not a one-line one. Use
`_split_frontmatter` to *locate* the fence pair, then edit the **original** text:
find the `state:` line inside the block's line range and replace that one line.
FR-003's test exists because no gate will do this for you.

**Trap 2 — A partial or malformed write stops every spec in the corpus, not the
one you wrote.** `factory/roadmap/workflow.py:494` — `read_corpus_activity` calls
`factory/roadmap/models.py:411` — `read_roadmap` on every tick, and both
docstrings say the same thing in different words: any fault raises and yields no
partial roadmap, and a corpus that does not parse is "a hard stop, not a parked
spec". A `Path.write_text` straight onto `spec.md` leaves a window in which a tick
reads a truncated file, and the cost of landing in that window is the whole line,
not this spec. FR-007 is `os.replace` for that reason, and
`factory/registry.py:353` — `_write_document` is the shape to copy. The temporary
goes **inside** `specs/<dir>/`, next to `spec.md`: `os.replace` is only atomic
within one filesystem, and `factory/roadmap/models.py:440` — `read_roadmap` walks
directories, so a file beside `spec.md` is invisible to the corpus while a
sibling *directory* named without a leading dot would not be.

**Trap 3 — The revision the change is computed against must be a content digest,
not a git object id.** The whole point of the pair is that the bytes can be shown
to a human before they are written, so the guard has to work on a file git has
never seen — and on this floor that is the normal case, not the edge: after this
refinement batch the working tree carries twenty-seven untracked spec
directories, `127` through `153`, every one of them a candidate for exactly this
verb. A `git rev-parse HEAD:<path>` guard refuses all twenty-seven and looks
correct on the one spec that happens to be committed. Copy
`factory/activities/verify_activities.py:621` — `_has_drifted`, including its
second rule: a file that cannot be read is *moved*, not "no change detected".

**Trap 4 — Do not add a git read inside `compute_readiness`, do not write a
fourth resolver, and do not assert the absence of the wrong import.** FR-010,
FR-011, FR-019. `factory/roadmap/models.py:587` — `compute_readiness` states the
constraint: both resolvers are injected so git reads stay out of workflow code.
So the verb supplies its own — and the tempting move is to write one, because it
is twenty lines. There are already three readings of readiness in this tree
(`factory/roadmap/cli.py:63` — `render_command` injects none,
`factory/cli/status.py:292` injects the observed one,
`factory/roadmap/workflow.py:851` — `_run_inner` injects the workflow's) and a
fourth is precisely how `spec ready` comes to permit a flip the roadmap then
refuses — the disagreement US2-S1 and US4-S3 exist to make impossible. US2 moves
`factory/cli/status.py:441` — `_observed_landed_resolver` and its helpers into
`factory/spec/`; US4 injects that one.

The second half of this trap is the test, and it has already bitten this spec
once. The obvious way to prove "no git read was added to
`factory/roadmap/models.py`" is to assert it imports nothing from
`factory.workgraph` — and that assertion is **false against the tree before a
line is written**: `factory/roadmap/models.py:53` reads
`from factory.workgraph.models import find_cycle`, and
`factory/roadmap/models.py:374` — `_cross_validate` calls it at
`factory/roadmap/models.py:400`, which is the corpus cycle check `read_roadmap`
runs at `factory/roadmap/models.py:475`. Written that way the test is red on
arrival, still red when the story is correct, and the cheap way to green it
deletes the cycle detector out of the corpus reader that three other draft specs
build on. Assert on the two git-reading modules by name —
`factory.workgraph.landed` and `factory.workgraph.worktree` — plus `subprocess`
and a `["git", ...]` argv literal, read the imports with `ast` rather than a
substring scan, and leave `find_cycle` alone. Do not assert on the substring
"git" either: that module's docstrings say the word four times today.

And put that assertion where its colour is honest. Written correctly it is green
before this story starts and green after it is correct, because `US2` never edits
`factory/roadmap/models.py` at all — its move is out of `factory/cli/status.py`
— so it is a **non-regression control**, not one of the reds the phase opens
with, and `tasks.md` gives it its own heading and says so in its first sentence.
An implementer who finds it under "write FIRST, must fail" reaches for the one
widening that makes it fail, which is the deleted-`find_cycle` trap above. The
red US2-S2 actually asks for is the other half: after the move there is exactly
one definition site for the six names, `factory/cli/status.py` defines none of
them and only re-binds them, and `_readiness_basis.__module__` and
`_observed_landed_resolver.__module__` both name the new module under
`factory.spec` — which is the module FR-019 sends the ready planner to, so
`ergane status` and the ready verb reach one function in one place. That
assertion is false against `factory/cli/status.py:378` and
`factory/cli/status.py:441` as they stand and true only once they have moved.

**Trap 5 — `promote_spec` is not this transition, and no workflow file may be
edited.** `factory/roadmap/workflow.py:621` — `promote_spec` and
`factory/roadmap/workflow.py:1110` — `_apply_promotions` implement a
one-pass, in-memory promotion that requires a live workflow run to receive a
signal and vanishes at the next tick. An implementer who reads them as "the
transition already exists" will wire the verb to the signal, and will ship
something that needs Temporal to be up in order to declare an intent that is a
property of a file. Both stay exactly as they are; if you find yourself editing
`factory/roadmap/workflow.py`, the design is wrong.

**Trap 6 — The validation verdict comes from 133's function, not from argv and
not from re-composed layers.** FR-009. `factory/cli/install.py:1078` —
`_spec_validate_argv` is the in-tree example of the wrong route: it builds
`["spec", "validate", ...]` and runs it back through the entry point, which
yields an exit code and stdout and loses every per-layer message FR-009 requires
quoted. Re-composing the exported checkers is worse — that is the drift 133
exists to end, and at `602a92c` ten of the twelve layers are private to
`factory/cli/nouns/spec.py`. Call the library form 133 exports over the same
`spec_dir`, `target_repo` and `specs_root` the verb was given.

**Trap 7 — 133's fixture trios are frozen byte for byte; copy one, never edit
one.** 133 FR-014 commits golden captures of the verb's stdout, its stderr and
its `--json` document over two fixture trios held under `tests/` — one clean, one
deliberately defective — and 133 FR-006 asserts the verb's output equals those
artifacts byte for byte. US4-S2 wants the defective trio and US4-S1 wants the
clean one, and the wrong move is to add a `depends_on_landed` line or change a
`state:` line in the committed fixture to suit this story: that rewrites the
capture and turns a landed test red for a reason this spec is not about. Copy the
trio into a `tmp_path` corpus and edit the copy. The right move for the *edge*
half is a second spec directory in that same `tmp_path` corpus, because
`factory/roadmap/models.py:411` — `read_roadmap` refuses a `depends_on_landed`
entry naming a directory the corpus does not hold. Note that 133 FR-014 says the
*clean* trio's golden stderr carries "an information note and a skipped-layer
line" — so the copy US4-S1 uses must be driven against a target repository under
which its citations resolve, or FR-017 will refuse the permitted case (trap 14).

**Trap 8 — Moving `ReadinessBasis` without re-binding its name turns a landed test
red, and three sibling drafts are reading these line numbers right now.** FR-011.
`tests/test_both_verbs_agree_about_the_schedule.py:54` imports `ReadinessBasis`
from `factory.cli.status`, and `factory/cli/status.py:264` holds it as a field of
the floor status the whole status command returns;
`tests/test_ergane_status.py:1211` —
`test_the_queue_header_names_the_readiness_basis` asserts the rendered header
carries it. Define the moved names in `factory/spec/` and import them back into
`factory/cli/status.py` under exactly the names they have now — the same
discipline 133 FR-001 applies to its finding type — so no construction site, no
call site and no test import in that module changes. That re-bind is also what
keeps three untracked sibling specs compiling against this module rather than
against a hole; § Sizing names them and says which order the four must land in.

**Trap 9 — A test that writes `state: ready` into a real directory under `specs/`
dispatches an epic, and no gate catches it.** `factory/verify/models.py:235` —
`RoadmapDials` puts the tick at 300 seconds; `factory/roadmap/workflow.py:494` —
`read_corpus_activity` re-reads the operator's own specs root on every one of
them; `factory/roadmap/workflow.py:867` — `_run_inner` selects on the flag
`factory/roadmap/models.py:607` — `compute_readiness` computes from that line;
`factory/roadmap/workflow.py:1294` — `_dispatch` starts the child. Every test in
this spec that exercises the ready path builds its corpus under `tmp_path`. A
test that flips a real spec and restores it in a `finally` is not good enough
either: the window is real and the failure is money, not a red suite.

**Trap 10 — A refusal that quotes a string you wrote passes a weak test and tells
the operator nothing; one refusal per layer is the same mistake at half scale;
and a two-field refusal has exactly one place to put the report's layer name.**
FR-009, FR-017, US4-S2. The shortcut is
`if report.refusals: refuse("validate", "spec does not validate")`. It satisfies
any test that asserts "there is a refusal at layer `validate`", and it throws away
the only thing the operator needs — which layer refused and what it said. The
subtler version is to group the report's refusals by layer name and emit one
`StateRefusal` each: three bad anchors are three findings at
`factory/cli/nouns/spec.py:993` — `_check_symbol_anchors`, and grouping keeps one
message and discards two. Build one `StateRefusal` **per refusal in the report**.

Then there is the field question, and it has one answer rather than two workable
ones. `StateRefusal` carries a layer and a message (FR-001), and the refusal has
two layer names to carry: its own (`validate`) and the report's (`symbol_anchors`,
say). Putting the report's layer in the `layer` field makes a program that
switches on `layer` see twelve values that mean "the trio does not validate";
dropping it loses the only routing the operator has. So the layer is `validate`
and the message is `f"{inner.layer}: {inner.message}"` — one rendering function,
used for `validate_skipped` too, so what the operator reads at
`factory/cli/nouns/spec.py:1` and what a caller reads out of `--json` cannot
disagree. US4-S2's committed test builds its expected sequence by rendering the
report's own refusals, so a hand-written summary, a group-by-layer collapse and a
different rendering all fail.

**Trap 11 — Idempotence is not free here, and the honest answer is a refusal.** A
second ready on a spec already declaring `ready` has nothing to write. Returning a
permitted plan whose change is `None` makes "permitted" mean two things and hands
the apply function a value it cannot act on; returning a change identical to the
file makes the digest guard trivially pass and rewrites the file for no reason,
moving its mtime and its git status under an operator who is watching both. FR-004
makes it a refusal at layer `transition`, distinguishable by its layer from the
precondition layers, so a program can tell "nothing to do" from "not allowed" from
"not yet" from "not checked".

**Trap 12 — Do not give `landed` a verb, and do not let the generic planner become
one.** The entry's own narrowing takes `spec attest` off this docket, and
`factory/roadmap/models.py:66` — `SpecState` calls `landed` an attestation about
work the roadmap will never observe. A planning function that accepts any
`SpecState` is the surface through which this spec ships the attestation verb it
was told not to build, and the first caller to reach for it will be a consumer,
not this repository. FR-004's catch-all row refuses every requested state other
than `ready` and `deferred` at layer `transition`, and the two exported planners
of FR-008 are the only public entry points.

**Trap 13 — Three strings name this noun's verbs and one of them is already
wrong.** FR-016. `factory/cli/nouns/spec.py:1` (the module docstring) and
`factory/cli/nouns/spec.py:236` (the `NOUN` summary) both read "list, validate,
derive, new, landed"; `factory/cli/nouns/spec.py:114` — `_add_spec_parser` reads
"work with specs: list, validate, derive, landed" and has omitted `new` since it
shipped. Updating the two that look right and leaving the third is the likely
outcome, which is why US3-S5 derives the expected set from the parser's own
registered subcommands rather than restating it — a test written that way is red
on today's tree before this story adds a single verb, and stays green afterwards
only if all three strings are corrected.

**Trap 14 — Copy `validate`'s `--target-repo` default and the precondition this
whole spec exists for is hollow.** FR-013, FR-017, US4-S5, US3-S6. The default is
the literal `/srv/factory/targets/short-links` (pasted above), and it does not
exist on this host — `ls` on it fails. Run the way FR-013 originally defined it,
`ergane spec validate specs/<dir> --specs-root specs` prints this and exits **0**:

```
ergane spec validate — layer 'anchor_resolution' not checked: target repository /srv/factory/targets/short-links is not a readable directory
ergane spec validate — layer 'symbol_anchors' not checked: target repository /srv/factory/targets/short-links is not a readable directory
ergane spec validate — layer 'evidence' not checked: cannot read the gates /srv/factory/targets/short-links declares: /srv/factory/targets/short-links/ergane.yaml: [missing_manifest] cannot be read (No such file or directory); every target repo must commit a ergane.yaml declaring its gates
ergane spec validate — noted, not a refusal: [fixes] verified 1 finding key(s) against /home/admin/code/ergane/.factory/doctor.db
ergane spec validate — noted, not a refusal: [slice_coverage] task ids inside no story's slice and naming no story, so they reach no node: T036, T037 — expected in a setup or verification phase the operator works by hand, a defect anywhere else
specs/<dir>/spec.md: frontmatter, fixes, work-graph derivation, persona registry, scenario coverage, prompt assembly and slice coverage all pass
```

(A judge-evidence section follows those lines; it is elided here because it is
long, not because the run stopped.) Three of the twelve layers did not run —
`factory/cli/nouns/spec.py:904` — `_check_symbol_anchors`,
`factory/cli/nouns/spec.py:1206` — `_check_anchor_resolution`,
`factory/cli/nouns/spec.py:1816` — `_check_evidence` — and they are exactly the
three that catch a stale anchor. The wrong move is to accept
`report.refusals == []` as "validate clean": the verb would then arm a dispatch
having checked no anchor, and tell the operator the precondition held. Two things
prevent it, and both are required: default `--target-repo` to
`factory/cli/status.py:425` — `_repo_holding` over the specs root, and refuse at
layer `validate_skipped` on any skipped layer (FR-017), reading the report's own
skipped member rather than re-deriving it, and rendering each one as
`<layer>: <reason>` the way trap 10 fixes for `validate`. The consequence for
tests is real: a permitted plan needs a run in which nothing skipped, so US4-S1's
corpus is driven against a target repository under which its citations resolve,
and a copied fixture that declares `fixes:` keys needs a findings store or the
`fixes` layer skips too — the copy is yours to edit (trap 7).

**Trap 15 — One malformed sibling spec makes the ready planner raise, not
refuse.** FR-018. `factory/roadmap/models.py:411` — `read_roadmap` refuses the
**corpus**, not the spec: any fault anywhere — a dangling `depends_on_landed`, an
unknown key, a bad state — raises `RoadmapError` naming every fault and yields no
partial roadmap. FR-010 reads the corpus through it, so on a floor whose specs
root carries twenty-seven untracked drafts, one bad sibling turns
`ergane spec ready <dir>` into a traceback. That is the one input a verb built to
be refusable must not crash on. Catch it, turn each named fault into a
`StateRefusal` at layer `corpus`, and return a plan. Note the asymmetry the defer
planner depends on: `defer` reads no corpus at all (FR-012), so a broken corpus
must still be parkable.

## Sizing

The bound is `factory/verify/diffbounds.py`'s `DIFF_INPUT_LIMIT`, 65,536 bytes,
above which a story is refused unjudged (D-050) — the whole attempt spent before
the judge is reached. This tree's own recent commits price a changed line:
`602a92c` is 906 changed lines over 52,840 bytes and `1027a05` is 1,025 over
63,932, so 58 to 62 bytes per changed line, and the bound is about 1,080 changed
lines including pasted evidence. Every estimate below is in those units, and each
story states the point at which an implementer must stop and escalate rather than
ship a diff that will be refused unread.

**US1** touches one production file: a new module under `factory/spec/` holding
`SpecStateChange`, `StateRefusal`, `SpecStatePlan`, the planning function and the
apply function. Roughly a hundred and fifty lines, plus one new test module of
five tests — call it 400 changed lines, about 24 KB. It imports nothing from
`factory/cli/`; its only in-tree dependencies are
`factory/roadmap/models.py:240` — `_split_frontmatter` and the enum at
`factory/roadmap/models.py:66` — `SpecState`. Comfortable. Escalate above 55 KB.

**US2 is a pure relocation, and it is a separate story because of the arithmetic
below.** `factory/cli/status.py` loses
`factory/cli/status.py:247` — `ReadinessBasis`,
`factory/cli/status.py:378` — `_readiness_basis`,
`factory/cli/status.py:441` — `_observed_landed_resolver`,
`factory/cli/status.py:469` — `_observed_landing`,
`factory/cli/status.py:425` — `_repo_holding` and
`factory/cli/status.py:491` — `_declared_story_keys`, and gains an import binding
those names back (trap 8). Measured on this tree, `factory/cli/status.py:247-251`
plus `factory/cli/status.py:378-505` is 4,768 bytes over 133 lines, and a move
pays for those lines twice — about 270 changed lines and 10 KB — plus the import
block, two tests and one pasted transcript: call it 400 changed lines, 16 KB.
`factory/spec/` is the home rather than `factory/roadmap/` because the moved code
shells git through `factory/workgraph/landed.py:130` — `landed_facts`, and
`factory/roadmap/` is where the workflow's own imports live. Escalate above 55 KB.

**US4** touches the new module only, and carries the four precondition layers
(`validate`, `validate_skipped`, `depends_on_landed`, `corpus`), the two exported
planners, six tests — two of which copy a 133 fixture trio into a `tmp_path`
corpus — and one verification task pasting three refusal reports beside a
`spec validate` transcript. Two hundred production lines and six corpus-building
tests is 700 to 800 changed lines, 42 to 48 KB. That is the heaviest story of the
four and it is the reason US2 is not part of it: measured together they were 900
to 1,000 changed lines, 55 to 60 KB, inside ten percent of the refusal with no
margin for an implementer who writes one more test than planned. Escalate above
55 KB — and if the two fixture copies grow, cut the pasted evidence in the
verification task to the three refusal reports and drop the `spec validate`
transcript rather than trimming a test.

**US3** touches `factory/cli/nouns/spec.py` — two subparsers beside the five at
`factory/cli/nouns/spec.py:113` — `_add_spec_parser`, two command functions, and
the three verb-list strings of trap 13 — plus one new test module of six tests
and four pasted transcripts. Under a hundred and fifty production lines; call it
450 changed lines, 27 KB. It adds no logic: every decision it renders was made in
US4, including the `--target-repo` default, which is the `_repo_holding` US2
relocated. Escalate above 55 KB.

**Files in common.** US1, US2 and US4 share the new `factory/spec/` module and no
other production file; US2 is the only story that edits `factory/cli/status.py`
and US3 the only one that edits `factory/cli/nouns/spec.py`, and neither of those
two files is touched by any other story. The declared chain US1 -> US2 -> US4 ->
US3 is therefore about correctness of sequencing on one new module, not about
contention across the tree.

**One sequencing hazard the operator owns, not the implementer.** Three sibling
drafts written in this same refinement batch anchor by line into the symbols US2
relocates: `153-a-landed-read-says-what-it-could-not-see` pastes and rewrites
`_readiness_basis` and cites `ReadinessBasis`;
`131-the-status-board-names-the-spec-it-cannot-dispatch` cites
`_observed_landed_resolver`, `_observed_landing` and `_readiness_basis` in nine
places; `140-a-story-can-land-with-a-requirement-open-and-say-so` cites
`_observed_landed_resolver`. Trap 8's re-bind keeps
`from factory.cli.status import ReadinessBasis` and every call site working, so
what those three lose is line numbers, not names — but a stale line anchor is a
validate refusal, and two stories editing the same hundred and thirty lines is a
merge-group collision. Land 131, 140 and 153 before 150-US2, or re-run their
anchors against `factory/spec/` afterwards. If they are flipped in the same
window, flip this spec last.

## Verification the operator will run, independent of the gate

Per constitution VIII and D-037 the judge sees the diff and the criteria only, so
runtime evidence is committed as pasted output. Beyond that, and **on a scratch
specs root, never on `specs/`** (trap 9):

1. Build a two-spec scratch corpus: one spec declaring `state: draft` with a
   `depends_on_landed` edge onto the second, and the second declaring
   `state: draft`. Run the ready verb with `--dry-run` on the first. It must
   refuse, naming the second directory and the state it declares, and print
   nothing it would write.
2. Edit the second spec to `state: landed` and re-run with `--dry-run`. The edge
   refusal must be gone. If a validation refusal remains, it must name the layer
   and quote that layer's own message — check it against
   `ergane spec validate <dir> --target-repo <the same repo> --specs-root <the
   same root>`, passing the flags explicitly so both runs check the same twelve
   layers, and confirm the two texts agree.
3. Run the ready verb once with `--target-repo` pointed at a path that does not
   exist. It must refuse at layer `validate_skipped`, naming
   `anchor_resolution`, `symbol_anchors` and `evidence` with the reason each was
   not run. A run that permits the flip here is trap 14, live.
4. Fix whatever `spec validate` refuses, then run the ready verb without
   `--dry-run` and with no `--target-repo` at all, so the default resolves. Open
   the file and confirm, line by line, that every `#` comment, the
   `depends_on_landed:` list and the `fixes:` list are exactly as they were and
   only the `state:` line changed. `git diff` on that file must show one changed
   line. This is trap 1, run forwards.
5. Run the ready verb again on the same spec. It must refuse at layer
   `transition` and write nothing.
6. Break one *other* spec in the scratch corpus — an unknown frontmatter key is
   enough — and run the ready verb on the first spec again. It must refuse at
   layer `corpus` naming the broken sibling, and must not traceback. Then run the
   defer verb on the same spec: parking must still work over a broken corpus.
7. Plan a defer on a spec whose trio `spec validate` refuses. It must be permitted
   — parking has no preconditions — and applying it must leave a corpus that
   `ergane spec list` still renders.
8. Hold the plan and the apply apart: with a scratch corpus, take a change with
   `--dry-run`, edit `spec.md` in an editor, then apply. The apply must refuse and
   the editor's bytes must survive.
9. Finally, and only on a scratch corpus, confirm the whole point: with the
   roadmap pointed at that corpus, a spec the verb refused to ready is not
   dispatched, and one it readied is. That is the act this spec makes refusable,
   run forwards.
