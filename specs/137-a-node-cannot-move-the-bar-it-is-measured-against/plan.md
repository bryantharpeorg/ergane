# Implementation Plan: a node cannot move the bar it is measured against

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## What already exists, and where

**The output check already has the diff's whole path list, and already knows how
to refuse one.** `factory/verify/diffcheck.py:172` — `check_output` reads the
changed paths at `factory/verify/diffcheck.py:231` — `check_output` through
`factory/verify/diffcheck.py:405` — `_changed_paths` (uncommitted *and*
committed, in that order), then asks one question about them at
`factory/verify/diffcheck.py:239` — `check_output`:

```python
    violations = (
        hygiene_violations(worktree, changed) if scope in DIFF_SCOPES else []
    )
```

That list is what decides the verdict at `factory/verify/diffcheck.py:274` —
`check_output` and is kept as evidence at `factory/verify/diffcheck.py:281` —
`check_output`. `factory/verify/diffcheck.py:311` — `hygiene_violations` knows two
rules and no more: the target repository's own ignore rules, and
`factory/verify/diffcheck.py:511` — `_runtime_root_rule`. Neither mentions
`specs/`.

**The pass/fail rule needs no edit at all.**
`factory/verify/diffcheck.py:166` — `decide_passed` is
`return has_diff and not violations and refusal is None`. Appending the new
entries to the same list is therefore the whole verdict change. FR-004.

**The evidence type already carries "which path, and which rule".**
`factory/verify/models.py:413` — `HygieneViolation` is `path` plus `rule`, and its
docstring says *why* `rule` is a quotable string rather than a category: the next
attempt is shown it verbatim. It also enumerates the shapes — "Two shapes occur"
— which is why FR-002 requires that paragraph amended rather than only the code.
The field it lands on is `factory/verify/models.py:554` — `OutputCheck`.

**The workflow's two construction sites, and both are inside one function.**
`factory/workgraph/workflow.py:2559` — `_verify` builds the output check's input
at `factory/workgraph/workflow.py:2609` — `_verify` and the recording input at
`factory/workgraph/workflow.py:2699` — `_verify`. It already holds every half of
both derivations: `request.graph` (used at
`factory/workgraph/workflow.py:2654` — `_verify`), `prepared.path` (used at
`factory/workgraph/workflow.py:2610` — `_verify`) and `prepared.base_ref`, which
it already passes twice — into the output check at
`factory/workgraph/workflow.py:2614` — `_verify` and onto the composed result at
`factory/workgraph/workflow.py:2672` — `_verify`. The dataclasses are
`factory/activities/verify_activities.py:294` — `CheckOutputInput` and
`factory/activities/verify_activities.py:467` — `RecordVerificationInput`, both
imported into workflow code under `workflow.unsafe.imports_passed_through()` at
`factory/workgraph/workflow.py:187`. Both already carry an optional field added
by an earlier spec with a default that keeps every older payload identical — copy
that shape.

**Everything the derivation needs is on the graph, and it is three strings.**
`factory/workgraph/models.py:252` — `WorkGraph` carries `feature`, `specs_root`
and `target_repo`; its docstring says outright that `specs_root` + `feature`
resolve the spec criteria are snapshotted from (D-023). The operator-side join is
already written once, at `factory/activities/verify_activities.py:208` —
`spec_path`, and the `SPEC_FILENAME` constant is beside it at
`factory/activities/verify_activities.py:124`. The new helper belongs there, as
its sibling: repository-relative directory in, no I/O.

**The two spec copies are two different revisions, and nothing keeps them in
step.** The dispatch snapshot is hashed from the operator's checkout:
`factory/workgraph/workflow.py:1736` — `_run_node` passes `graph.specs_root`, and
the compiled artifact
`specs/126-a-killed-node-leaves-no-ref-to-collide-with/workgraph.json` carries
`"specs_root": "/home/admin/code/ergane/specs"` beside
`"target_repo": "/home/admin/code/ergane"`. The node worktree is cut from
ORIGIN's landing head — `factory/workgraph/worktree.py:349` — `_remote_head`
fetches and resolves `origin/<branch>` — and then pinned for the node's whole
life: `factory/workgraph/worktree.py:362` — `ensure` says "no fetch, no rebase,
no reset". Nothing anywhere in `factory/` writes `SPEC_FILENAME` into a worktree.
Worktrees are placed by `factory/workgraph/worktree.py:289` — `worktree_path`
under the runtime root (`factory/workgraph/worktree.py:295` — `worktree_path`),
never inside the target clone, and `factory/workgraph/worktree.py:264` —
`PreparedWorktree` is what carries the path and the pin into the workflow.

**The pin is already on the row, so US2 needs no new field for it.**
`factory/verify/models.py:942` — `VerificationResult` carries
`base_ref: str = UNKNOWN_BASE_REF`, and its docstring says the value "comes from
`PreparedWorktree.base_ref` and from nowhere else: re-reading git at
record-writing time gives an answer that can differ from the one the attempt ran
against". That sentence is the reason the drift read takes the base ref off
`request.result` rather than as a third input. The sentinel is
`factory/verify/models.py:798`, documented at `factory/verify/models.py:791`.

**Reading a blob at a ref is already solved, in an activity, with a precedent to
copy.** `factory/activities/agent_activities.py:1103` — `_git_show` is one
function: `worktrees._git(repo, "show", f"{rev}:{path}")`, with a docstring
saying why the worktree module's wrapper is the only git wrapper here.
`factory/workgraph/worktree.py:1940` — `_git` runs one command with a scrubbed
environment and a bounded timeout and raises `WorktreeError` on **any** non-zero
exit — which is why "the file is not at the base ref" and "git is broken" arrive
as the same exception and FR-008 has to say what each means.

**The drift path, end to end.** `factory/verify/criteria.py:480` —
`load_criteria` records `source_path`; `factory/workgraph/workflow.py:2699` —
`_verify` hands it to the activity; `factory/activities/verify_activities.py:507`
— `record_verification` calls `factory/activities/verify_activities.py:602` —
`_with_drift`, which delegates at `factory/activities/verify_activities.py:617` —
`_with_drift` to `factory/activities/verify_activities.py:621` — `_has_drifted`.
Read `_with_drift`'s docstring before touching it: two of its three sentences are
contracts this spec must preserve (FR-009).

**The test homes exist and both are the obvious ones.** US1's library tests belong
in `tests/test_diff_hygiene.py`, beside
`tests/test_diff_hygiene.py:207` —
`test_the_refusal_names_the_rule_that_refused_each_path` (the shape for FR-002)
and `tests/test_diff_hygiene.py:381` —
`test_an_ordinary_diff_produces_todays_output_check_exactly` (the shape for
FR-005); its one unit test of the new derivation helper (T006) belongs in
`tests/test_verify_activities.py`, which is where that helper's module is tested.
US2's belong in the same module, which already has the whole harness:
`tests/test_verify_activities.py:448` — `record`,
`tests/test_verify_activities.py:465` — `write_criteria_source`, and the four
existing drift tests at `tests/test_verify_activities.py:1236` —
`test_a_spec_edited_under_the_node_is_flagged_as_drift`,
`tests/test_verify_activities.py:1258` — `test_a_spec_that_vanished_is_drift_too`
and `tests/test_verify_activities.py:1274` —
`test_drift_the_caller_already_detected_is_never_cleared`.

**A real repository and a real node worktree are one import away.** That module
already imports `tests/target_repo.py:90` — `git` (at
`tests/test_verify_activities.py:148`) and uses it against a real worktree at
`tests/test_verify_activities.py:994`. `tests/target_repo.py:102` —
`build_target_repo` commits the fixture skeleton on a branch, and
`tests/target_repo.py:131` — `add_worktree` attaches a node worktree to it, "the
shape a node actually gets". US2's tests need exactly that: commit
`specs/<feature>/spec.md` into the repo, attach the worktree, edit the copy inside
it, and pass the repo's head as the base ref. Do not build a bare directory and
call it a worktree — a comparison against a base ref has nothing to read there.

**And both seams already have a recorder in the interpreter suite — one of them
sufficient, one of them not.** `tests/test_interpreter.py:1477` — `check_output`
appends the whole `CheckOutputInput` to `script.output_requests` (declared beside
its siblings at `tests/test_interpreter.py:971`), and
`tests/test_interpreter.py:4305`, inside
`tests/test_interpreter.py:4282` —
`test_the_diff_the_judge_scores_is_read_by_an_activity`, is the exact assertion to
copy for US1-S5. `tests/test_interpreter.py:1513` — `record_verification` appends
only `request.result` to `script.records`, which is declared as a
`list[VerificationResult]` at `tests/test_interpreter.py:974`, so US2-S5 needs a
second list rather than a wider one (trap 9). The epic's graph comes from
`tests/test_interpreter.py:425` — `make_graph`, whose `**overrides` is how a
scenario changes `specs_root` (trap 11). For a real worktree with real files in
it, `tests/test_023_us2_dispatch_pin.py:807` —
`test_worktree_manifest_ladder_rewrite_has_no_effect` is the precedent: it
replaces the scripted `prepare_worktree` with one that creates the directory and
writes a file the node is pretending to have tampered with. Copy that; do not
invent a second way to get bytes into a node worktree.

## Traps

**Trap 1 — The ledger row's own notes are wrong, and the correction is buried at
the bottom of them.** The row this spec declares asserts "criteria_drift does now
fire (verified 2026-09-03, verify_activities.py:605-617 re-hashes the spec file)".
The mechanism says otherwise: `factory/activities/verify_activities.py:621` —
`_has_drifted` is handed `criteria.source_path`, which
`factory/verify/criteria.py:480` — `load_criteria` records from the `specs_root`
join at `factory/activities/verify_activities.py:208` — `spec_path`. That is the
operator's checkout. A FACTUAL CORRECTION block appended to the same row says so,
but it is thousands of characters below the sentence it corrects and
`ergane findings list` prints the sentence first. The wrong move is to read the
row, conclude US2 is already done, and ship US1 alone. FR-007.

**Trap 2 — Refuse three documents by name, never the directory, because two
classes of file already land inside it on the node's own PR.** The backlog entry
this spec came from says a diff touching the dispatched spec's own directory
fails verification. Run the scan before you believe it; both halves are in this
tree at `602a92c`:

```
$ git ls-files 'specs/*/evidence/*' | wc -l
50
$ git ls-files 'specs/*/attempt-report-*.md' | wc -l
15
```

The fifty arrive on node pull requests — `d5119a8` (#424) added
`specs/126-a-killed-node-leaves-no-ref-to-collide-with/evidence/us1-preflight-refusal.txt`
on the US1 node's own PR, and `7211032` (#331), `a57c59d` (#328) and `606ffdb`
(#321) are the same shape — because every trio's `### Verification for this story`
phase carries a "Paste, as committed evidence, ..." task, which is how Principle
VIII (`.specify/memory/constitution.md:63`) is satisfied for anything a diff
cannot show. The fifteen are `specs/<dispatched-dir>/attempt-report-<story>.md`
across twelve directories, each added by that directory's own node PR (`5c98cbf`
#382, `ab165da` #383, `9df94e3` #385, `2cedd34` #386, `62cc820` #387, `2d9d256`
#389, `03451a9` #392, `cea2c35` #396, `6f7347e` #400, `8f5f633` #404, `7fd478e`
#407, `03774cc` #409, `109ac89` #410, `240f7ae` #413, `30246c7` #416), and
twenty-one tasks across fourteen tracked trios' `tasks.md` still instruct one.
They sit **beside** `evidence/`, not under it, so an `evidence/`-only carve-out is
not a narrower version of the right rule — it is the wrong rule with a smaller
blast radius, and it still makes twelve directories unlandable and refuses T012
and T022 of this spec. The rule to build is exactly this: **refuse `spec.md`,
`plan.md` and `tasks.md` directly inside the dispatched directory; every other
path inside it passes, `evidence/` and `attempt-report-<story>.md` included.**
The refusal is by path and never by content: a third class exists — six landed
node PRs that ticked their own `tasks.md` checkboxes, none since 2026-08-17 (trap
12) — and it is refused on purpose, so do not add a "but it was only a checkbox"
read of the file. FR-001, FR-003.

**Trap 3 — There are two files behind one name, and the test that convinced
everyone otherwise is misnamed.**
`tests/test_verify_activities.py:1236` —
`test_a_spec_edited_under_the_node_is_flagged_as_drift` is green today. Its name
says "under the node"; its body writes to the stand-in the caller passed as
`criteria_source_path`, which on the production path is the operator's file. The
wrong move is to read that green test as coverage for the worktree copy and skip
US2-S1. Write the new test so it edits **only** the worktree copy and leaves the
operator-side copy hashing to the snapshot; that is the assertion today's code
fails. FR-007.

**Trap 4 — The dispatch snapshot is NOT the baseline for the worktree copy, and
using it flags every ordinary dispatch.** This is the trap that refuted the first
draft of US2, and it is the one to read twice. The snapshot is hashed from the
operator's working tree — `factory/workgraph/workflow.py:1736` — `_run_node`
passes `graph.specs_root`, which
`specs/126-a-killed-node-leaves-no-ref-to-collide-with/workgraph.json` shows is
`/home/admin/code/ergane/specs`. The worktree copy comes from origin's landing
head — `factory/workgraph/worktree.py:349` — `_remote_head` — and is pinned for
the node's whole life by `factory/workgraph/worktree.py:362` — `ensure` ("no
fetch, no rebase, no reset"). **Nothing copies one into the other.** So the
sentence "the worktree copy does not hash to the snapshot" is true on every
attempt of every node whenever the operator's checkout and origin merely
disagree, which is the normal state of a spec being refined: the roadmap
dispatches from the operator's working tree on a five-minute schedule, and origin
lags every uncommitted or unpushed edit. A re-dispatch of a killed epic is the
same shape with the divergence in the other direction. The correct baseline is the
node's OWN starting bytes: the same repository-relative path at `prepared.base_ref`,
which `factory/verify/models.py:942` — `VerificationResult` already carries onto
the row. Compare blob identities rather than re-reading text —
`git -C <worktree> rev-parse <base_ref>:<relpath>` against
`git -C <worktree> hash-object -- <relpath>` — through
`factory/workgraph/worktree.py:1940` — `_git`, the way
`factory/activities/agent_activities.py:1103` — `_git_show` already does it from
an activity. FR-007.

**Trap 5 — A node cannot lower its own bar for its own verdict, so write the
criteria to the landing.** Criteria are snapshotted once before the first attempt
at `factory/workgraph/workflow.py:1736` — `_run_node`; the row records
`criteria.source_sha256` at `factory/workgraph/workflow.py:2661` — `_verify`; the
prompt is assembled from the operator-side copy at
`factory/activities/agent_activities.py:963` — `load_prompt_sources`. A scenario
of the shape "the node edits its spec and the judge still fails it" is therefore
**true today**, before any change, and a do-nothing production diff passes it.
Every scenario in this spec is written to the refusal and to the recorded row
instead. If you find yourself adding one about what the judge sees, stop: you have
written an unprovable criterion, which is the exact defect 102 exists to refuse.
FR-001, FR-011.

**Trap 6 — Do not widen the runtime-root prefixes, and do not touch
`decide_passed`.** The cheap-looking move is to add `specs` to
`factory/verify/diffcheck.py:287` — `runtime_root_prefixes`. That function is
derived, not restated, precisely so that the two factory roots stay in one place —
and adding a third name there refuses **every** path under `specs/` in **every**
repository, including `evidence/` and the attempt reports (trap 2) and every other
spec, with no per-dispatch knowledge at all. Equally,
`factory/verify/diffcheck.py:166` — `decide_passed` already refuses whenever
`violations` is non-empty; editing it is how the size refusal and the ignore rules
get softened by accident, and there is an existing test asserting today's record
shape byte-for-byte at `tests/test_diff_hygiene.py:381` —
`test_an_ordinary_diff_produces_todays_output_check_exactly`. Add a pure function
beside `factory/verify/diffcheck.py:311` — `hygiene_violations` and append its
result to the same list. FR-004.

**Trap 7 — The evidence type's docstring enumerates the rule shapes, so a third
one makes it wrong.** `factory/verify/models.py:413` — `HygieneViolation` says
"Two shapes occur" and names both. Shipping a third rule string without amending
that paragraph leaves a docstring that contradicts the code in the one place the
next attempt is told to read for the rule that refused it. Amend it in the same
diff. FR-002.

**Trap 8 — The workflow may not touch the filesystem, so the derivation is path
arithmetic and its failure is an answer, not an error.** Principle IV
(`.specify/memory/constitution.md:33`): workflow code makes pure decisions, side
effects live in activities. Both construction sites are inside
`factory/workgraph/workflow.py:2559` — `_verify`, which already reaches
`request.graph` (`factory/workgraph/workflow.py:2654` — `_verify`) and therefore
`graph.specs_root`, `graph.feature` and `graph.target_repo`, plus `prepared.path`
for US2. `Path(specs_root).relative_to(target_repo) / feature` is the whole
derivation, and `relative_to` raising `ValueError` is the "the spec lives outside
this repository" answer — return nothing and let FR-005 hold. The wrong moves are
calling `Path.exists()` or shelling git from workflow code, and swallowing the
`ValueError` into a bare `except` that hides a genuinely malformed graph. Note
that the snapshot site at `factory/workgraph/workflow.py:1736` — `_run_node` is
**not** where this belongs: it runs once per node, before the first attempt, and
the input you are filling is built per attempt in `_verify`. The git read US2
needs is not an exception to this rule: it happens inside
`factory/activities/verify_activities.py:507` — `record_verification`, which is an
activity. FR-006.

**Trap 9 — Two seams, and the second recorder must be a NEW list, not a wider
one.** `tests/test_interpreter.py:1477` — `check_output` records the whole input,
so US1-S5 is a two-line assertion modelled on
`tests/test_interpreter.py:4305`. `tests/test_interpreter.py:1513` —
`record_verification` records `request.result` only, so an implementer asserting
US2-S5 against `script.records` will find no worktree path on it, conclude the
seam is untestable, and prove the field by calling the activity directly — which
is precisely the shortcut US2-S5 exists to refuse. The other wrong move is to
"widen" `script.records` in place: it is declared
`list[VerificationResult]` at `tests/test_interpreter.py:974` and sixteen
sites in the same module read `r.node_id`, `r.attempt`, `r.verdict` and
`r.criteria_sha256` off its members (`tests/test_interpreter.py:2094`,
`tests/test_interpreter.py:2709`, `tests/test_interpreter.py:2730`,
`tests/test_interpreter.py:4365` among them), so changing its element type turns a
one-scenario problem into a suite-wide failure. Add a **new**
`record_requests: list[RecordVerificationInput]` beside
`tests/test_interpreter.py:971` — the same shape as `output_requests`,
`gate_requests` and `judge_requests` — append to it at
`tests/test_interpreter.py:1517` and leave `script.records` exactly as it is.
FR-010.

**Trap 10 — 102 declared this out of its own scope, and that declaration is what
US2 supersedes.** `specs/102-a-spec-that-cannot-be-satisfied-fails-validate/spec.md:93`
says "It is not a change to `criteria_drift`. Its hashing is correct; it did not
fire because nothing drifted", and its FR-011 at
`specs/102-a-spec-that-cannot-be-satisfied-fails-validate/spec.md:215` required
every story to leave that hashing unchanged. This spec supersedes that FR **for
the drift inputs only**: the hash function, the snapshot and the recorded value
are untouched (FR-011); what changes is which files are hashed, and against what.
Say so in the code comment, or the next reader will file this as a regression of
102.

**Trap 11 — The interpreter harness's default graph puts `specs_root` OUTSIDE
`target_repo`, so US1-S5 written against it proves nothing.**
`tests/test_interpreter.py:425` — `make_graph` fills `specs_root` from
`tests/test_interpreter.py:240` (the string `"specs"`, relative) and `target_repo`
from `tests/test_interpreter.py:241` (the absolute
`"/srv/factory/targets/library"`). `Path("specs").relative_to("/srv/factory/targets/library")`
raises `ValueError`, so on the default graph the correct implementation derives
**nothing**. An implementer who writes US1-S5 against the default fixture sees the
assertion fail, concludes T007 is broken, and starts editing a correct helper; the
worse outcome is asserting `is None` instead and shipping a scenario that a
do-nothing derivation also satisfies. Pass the override — `make_graph` takes
`**overrides`, so `make_graph(specs_root=f"{TARGET_REPO}/specs")` is the whole fix
— and keep the default graph as US1-S6's outside-the-repo case. FR-005, FR-006.

**Trap 12 — Absence and unreadability mean four different things now, and only
one of them is drift.** `factory/activities/verify_activities.py:624` —
`_has_drifted` states the operator-side rule in its own docstring — "A file that
cannot be read is drift" — and returns True for `OSError` at
`factory/activities/verify_activities.py:630` — `_has_drifted`. That is correct
for the operator-side copy and wrong for the worktree comparison, where four cases
have to be told apart. Absent at the base ref **and** absent in the worktree is
the ordinary dispatch of a spec that is not committed to the landing branch — this
spec's own directory is untracked as it is written (`git ls-files specs/137-...`
returns nothing) — and it is **not** drift. Present on exactly one side is drift:
the node created the file, or deleted it. And a base-ref read that fails for any
other reason is **not** drift, because
`factory/workgraph/worktree.py:1940` — `_git` raises `WorktreeError` on every
non-zero exit, so "no such path at that ref" and "git could not run" arrive as one
exception and the fail-loud reading would flag every dispatch on a host with a
broken git. The fourth case is the caller with nothing to compare: no worktree
path, no derived directory, or a result whose `base_ref` is
`factory/verify/models.py:798`'s sentinel — attempt no read at all. Leave
`_has_drifted` untouched; give the worktree comparison its own function. FR-008.

**Trap 13 — Do not tick the boxes in this file.** Six landed node PRs changed
their own dispatched `tasks.md` by flipping `- [ ]` to `- [x]` — `ea92b35` (#159),
`1bfc8c8` (#143), `0f8f6b3` (#139), `65d53b5` (#97), `a3c4141` (#5) and `aacc7fc`
(#129, which also rewrote task prose) — and the rule US1 builds refuses exactly
that. The last of them was 2026-08-17 and nothing in
`factory/workgraph/prompt.py:200` asks for it, but an agent that reads a checklist
tends to tick it. A node of THIS spec that ticks its own boxes fails its own
output check the moment US1 lands, and the failure will read as a bug in the rule
rather than as the rule working. Leave the checkboxes alone; the evidence tasks
T012 and T022 are where a story records that it is done. FR-001.

## Sizing

US1 is one pure function beside `hygiene_violations`, one call appended into the
existing `violations` list, one new parameter on the library `check_output`, one
optional field on `CheckOutputInput`, one helper beside `spec_path`, one
derivation at the workflow's construction site, and one docstring paragraph. It
touches `factory/verify/diffcheck.py`, `factory/verify/models.py`,
`factory/activities/verify_activities.py` and `factory/workgraph/workflow.py`.
Its tests live in `tests/test_diff_hygiene.py`, `tests/test_interpreter.py` and —
for T006's unit test of the new derivation helper, whose module is tested there —
`tests/test_verify_activities.py`.

US2 is one optional field pair on `RecordVerificationInput`, a second comparison
inside `_with_drift` with its own function and its own absence rules, and one
derivation at the workflow's recording site. It touches
`factory/activities/verify_activities.py` and `factory/workgraph/workflow.py`,
and — by FR-004 and FR-011 — **no other production file**, in particular neither
`factory/verify/diffcheck.py` nor `factory/verify/criteria.py`;
`factory/workgraph/worktree.py` is imported for its git wrapper and not edited.
Its tests live in `tests/test_verify_activities.py` and
`tests/test_interpreter.py`.

The two stories share two production files and edit different functions in each:
US1 works in `check_output`/`CheckOutputInput` and the new helper, US2 in
`_with_drift`/`RecordVerificationInput`. They share no production **function**,
and the `depends_on_merged` edge serialises them so the shared files never merge
concurrently. They also share one test module — `tests/test_verify_activities.py`,
where US1 has a single helper unit test and US2 has its drift suite — in different
test functions, and the same edge serialises that. US2 reuses US1's helper rather
than re-deriving it, which is the other reason the edge is declared.

Both stories are well inside the 64 KiB deterministic diff bound (D-050): US1 is
under a hundred production lines plus three test modules, US2 under sixty plus
two, and the pasted evidence each verification task asks for is two short reports,
not a transcript.

## Verification the operator will run, independent of the gate

Per constitution VIII and D-037 the judge sees the diff and the criteria only, so
runtime evidence must be committed as pasted output. Beyond that:

0. **Before dispatching this spec at all, file the residue as its own open ledger
   row.** This spec closes two of the declared row's three named remedies and
   leaves the write-scope one open — a node can still write the bytes, and a diff
   touching a *different* spec's directory is still not refused (`7d9f207` landed
   exactly that). File that residue with `ergane findings report` first, so a row
   exists that `ergane findings triage --apply` cannot sweep away, and cite the new
   key here. The reason this is step 0 and not step 7 is that 100, 092 and 118 each
   left the same promise as prose and each broke it: a critical row closed on a
   half-fix is invisible from the moment the sweep runs.
1. Dispatch a one-story epic against a scratch spec, let the node run, then — in
   the node's worktree, before verification — append a line to the dispatched
   `spec.md`. The attempt must fail the output check, and the refusal must name
   that path.
2. Repeat twice more, writing the same bytes into
   `<worktree>/specs/<feature>/evidence/` and then into
   `<worktree>/specs/<feature>/attempt-report-us1.md` instead. Both attempts must
   pass, and both files must land. This is the step that proves the corpus still
   works; skip it and every story in `specs/` becomes unlandable — fifty evidence
   files and fifteen attempt reports are already committed that way.
3. Read `criteria_drift` for the attempt in step 1 **with a query, not with a
   verb**: `sqlite3 .factory/verification.db "select node_id, attempt,
   criteria_drift, criteria_sha256 from verification_results order by id desc
   limit 5"`. The column is `factory/verify/store.py:221`; nothing in
   `factory/cli`, `factory/notify` or `factory/escalation` prints it, so
   `ergane build status` and `ergane build attempts` will show no drift field and
   an operator who expects one will read the feature as broken. It must be true,
   with the operator-side `spec.md` untouched throughout.
4. Dispatch a spec whose directory is **not** committed to the landing branch, so
   neither the base ref nor the worktree carries a copy. The attempt must complete
   with `criteria_drift` false. This is trap 12 run forwards.
5. Commit and push a spec, then edit the operator's working-tree copy WITHOUT
   pushing it, and dispatch. The snapshot now hashes the operator's newer bytes
   while the worktree carries origin's older ones, and no node has touched
   anything: `criteria_drift` must be false. This is trap 4 run forwards, and it
   is the false positive that would otherwise have flagged every row of every
   epic dispatched from a working tree ahead of origin.
6. Onboard a target repository whose `specs_root` sits outside the clone and run
   one epic. Nothing may be refused and nothing may be flagged.
7. **Amend the declared row's notes, and this step is not optional.** The
   parenthetical "criteria_drift does now fire (verified 2026-09-03,
   verify_activities.py:605-617 re-hashes the spec file)" is wrong (trap 1), its
   FACTUAL CORRECTION sits thousands of characters below it, and
   `ergane findings list` prints the wrong sentence first. With step 0's row on
   file, resolving this one is honest; without it, it is the fourth half-fix.

Step 1 paired with step 2 is the falsifiable test of US1: the first is `701be6e`
run forwards and refused, the second is the fifty committed evidence files and
fifteen attempt reports still landing. Step 1 paired with step 5 is the
falsifiable test of US2: drift on the edit the node made, silence on the
divergence it did not.
