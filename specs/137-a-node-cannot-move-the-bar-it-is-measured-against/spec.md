---
state: draft
fixes:
  - verify/a-nodes-write-scope-is-the-worktree-and-the-spec-lives-in-the-worktree-so-a-node-can-rewrite-the-criteria-it-is-measured-against
# DRAFTED 2026-09-04 by the refinement workflow (refinement-2026-09-04) from
# docs/triage-2026-09-03-ergane-web-round3.md § "a-node-cannot-move-the-bar-it-is-measured-against"
# (lines 132-148), against ergane-buildout at 602a92c. Every `file:line` in
# spec.md and plan.md was read from that commit and verified to fall inside the
# symbol named, not recalled.
# REPAIRED 2026-09-04 (refinement-2026-09-04): the corpus scan behind FR-003 had
# found one of two live classes of legitimate node write into the dispatched
# directory, so the rule is narrowed from "the whole directory minus `evidence/`"
# to the three criteria documents by name — which is what the rule sentence and
# truth-table rows 1-2 already said; `evidence/` and the fifteen committed
# `attempt-report-<story>.md` files are now outcomes, not exceptions. Trap 2
# carries both halves of the scan; trap 8 now names `_verify` and `request.graph`
# rather than `_run_node`; T005 carries the harness override the scenario needs;
# T017 and trap 9 name a NEW recorder list; two constant cites take the machine-
# checked symbol form; the provenance now says the row must be re-opened, not
# closed, if the sandbox half is still wanted. No key added, none removed.
# REPAIRED 2026-09-04 (refinement-2026-09-04), answering the review that refuted
# the flip: that block above reported four edits to plan.md and tasks.md that were
# never written — this pass writes them, and corrects its last clause. THE GATE
# refused (exit 1, three `symbol_anchors` findings) because the "machine-checked
# symbol form" it claims is impossible for a module-level constant:
# `factory/cli/nouns/spec.py:825` — `_symbol_spans` indexes `def` and `class`
# nodes only, so `DIFF_SCOPES`, `PLAN_FILENAME` and `TASKS_FILENAME` are back in
# the coarse form and must stay there. plan.md trap 2 and tasks.md T008 still
# taught the superseded directory-minus-`evidence/` rule, which refuses the
# fifteen committed `attempt-report-<story>.md` files US1-S2 says must pass; both
# now name the three documents. T002 and T012 gained the attempt-report case,
# without which the wrong rule shipped green. Trap 9 and T017 said "widen the
# existing recorder": `tests/test_interpreter.py:974` is a
# `list[VerificationResult]` read by seventeen assertions, so they now say add a
# NEW list beside it. Trap 8 names `_verify`. Trap 2's stale task ids T009/T017
# are now T012/T022. plan.md § "Verification the operator will run" gained the
# step 6 the frontmatter points at twice — the ledger row's amendment and the
# re-open contract, which is the only thing standing between this and a
# half-fix closed row. Counts corrected: fourteen tracked trios, twenty-one
# tasks, not fifteen trios. US1-S6's "no filesystem read" is now diff-provable.
# No key added, none removed.
# REPAIRED 2026-09-04 (refinement-2026-09-04), answering the second refutation:
# US2's drift comparison is rebuilt on the node's own base ref, because holding
# the worktree copy against the DISPATCH SNAPSHOT compared two files that were
# never guaranteed to agree and flagged ordinary dispatches (see the block below);
# the corpus scan is finished — node commits are now scanned against the three
# document names, which found a third class the earlier two scans could not see,
# and it is refused on purpose; plan.md § "Verification" step 3 no longer claims
# `ergane build status` prints `criteria_drift` (no operator surface does) and
# US2's narrative no longer claims an escalation summary reads it; the residue
# row is now a PRE-DISPATCH act at step 0 rather than a post-landing promise;
# T006 names its module and the [P] collision with T005 is gone; and the block
# above says "seventeen assertions" where trap 9 and T017 correctly say sixteen
# sites — `grep -c 'script\.records' tests/test_interpreter.py` is 18 lines, two
# of them the fake's own append and `len()`. No key added, none removed.
#
# WHERE THIS CAME FROM. N51 of the `ergane-web` round-3 hand-over, whose
# surviving half is the open critical ledger row named in `fixes:` above. 102
# closed the other half — the judge can no longer propose a criterion rewrite,
# and `screen_feedback` enforces it rather than instructing it. What survives is
# the unprompted act: the node's write scope is the worktree, the spec lives in
# the worktree, and the drift flag hashes the operator-side copy, so three
# controls all fail open.
#
# WHAT IT COST, MEASURED. The reported incident: a node on its last rung edited
# its own acceptance scenario AND a SHALL clause of a functional requirement,
# and the amendment landed. It is not a consumer-only defect — `701be6e`, the
# node PR for `016-delta-derivation/us4` (#17), deleted a sentence from
# `specs/016-delta-derivation/spec.md`, the spec that node was dispatched
# against, and merged into this repository. The row's own note is the measure of
# how expensive the blind spot is: it records the flagging control as working
# when the control cannot see this edit at all.
#
# WHAT THE ENTRY GOT WRONG, AND IT WOULD HAVE BROKEN THE CORPUS TWICE. The
# entry's Scope says "a diff touching the dispatched spec's own directory fails
# verification". Two classes of file already land inside that directory on the
# dispatched node's own pull request, and both are house doctrine rather than
# accident. Fifty files sit under `specs/*/evidence/` — `d5119a8` (#424) added
# `specs/126-.../evidence/us1-preflight-refusal.txt` on the US1 node's own PR,
# and `7211032` (#331), `a57c59d` (#328) and `606ffdb` (#321) are the same shape.
# Fifteen more are `specs/<dispatched-dir>/attempt-report-<story>.md` across
# twelve spec directories, every one added by that directory's own node PR
# (`5c98cbf` #382, `ab165da` #383, `9df94e3` #385, `2cedd34` #386, `62cc820`
# #387, `2d9d256` #389, `03451a9` #392, `cea2c35` #396, `6f7347e` #400,
# `8f5f633` #404, `7fd478e` #407, `03774cc` #409, `109ac89` #410, `240f7ae`
# #413, `30246c7` #416), and twenty-one tasks across fourteen tracked trios'
# tasks.md still instruct a node to write exactly that path. Nothing binding
# names a directory: the constitution and D-050 require the evidence committed,
# not a place to put it. So the rule here refuses the three criteria documents BY
# NAME rather than the directory minus a carve-out, which is what the rule
# sentence below always said.
#
# THE THIRD CLASS, AND THE SCAN THAT FINALLY FOUND IT. The two scans behind the
# block above — `git ls-files 'specs/*/evidence/*'` and
# `git ls-files 'specs/*/attempt-report-*.md'` — enumerate files that exist, and
# so are structurally blind to a node that EDITED a file already there. The scan
# that is not blind runs the other way: for each of the 310 node commits whose
# subject is `<dir>/usN:`, ask `git show --name-only` for changes to
# `specs/<same dir>/{spec,plan,tasks}.md`. It returns eight, and six of them are
# a class neither earlier scan could see: a node ticking `- [ ]` to `- [x]` in
# its OWN dispatched `tasks.md` — `ea92b35` (#159, 052/us1, 7 ticks, nothing
# else), `1bfc8c8` (#143, 049/us6, 6), `0f8f6b3` (#139, 049/us4, 8), `65d53b5`
# (#97, 033/us3, 18), `a3c4141` (#5, 007/us3, 3), and `aacc7fc` (#129, 034/us5,
# ticks PLUS rewritten task prose, which is the defect shape landing beside the
# benign one). The remaining two are already named above: `701be6e` (all three
# documents) and `cbf994e` (#56, 027/us2, an operator-completed externally-built
# story). THE RULE REFUSES ALL SIX ON PURPOSE, and the truth table says so
# rather than staying silent: the practice stopped on 2026-08-17 and has not
# recurred in the ~150 node PRs since, nothing in `factory/workgraph/prompt.py`
# instructs it, and a node is handed its own task slice rather than a document to
# maintain. So no live conforming work breaks — but replaying one of those six
# epics under this rule now fails the output check, and an operator reading a
# scan of files-that-exist would never have known.
#
# THE ANCHOR THE ENTRY AND THE LEDGER ROW BOTH MISS BY TWO. The row's refs and
# the entry both name "verify_activities.py:183" for
# `path = spec_path(request.specs_root, request.feature)`. In this tree that line
# is `factory/activities/verify_activities.py:181`, at 602a92c and at 238b494
# alike; :183 is `return load_criteria(`. The claim is right and the anchor is
# not; this spec cites :181, with the repository-relative path the house rule
# requires.
#
# THE LEDGER ROW'S NOTES ARE WRONG IN THEIR FIRST HALF. The row asserts
# "criteria_drift does now fire (verified 2026-09-03, verify_activities.py:605-617
# re-hashes the spec file)". It re-hashes the OPERATOR-SIDE path. A FACTUAL
# CORRECTION block appended to the same row on 2026-09-03 says so, but the wrong
# sentence still reads first and `findings list` prints it first. The operator
# should amend the row — plan.md § "Verification the operator will run" step 6 —
# and plan.md trap 1 is what protects the implementer meanwhile.
#
# WHY US2 IS MEASURED AGAINST THE BASE REF AND NOT THE SNAPSHOT. The first draft
# of FR-007 said "either copy failing to hash to the dispatch snapshot is drift".
# That is a false-positive machine, because the two copies are not two readings of
# one file. The snapshot is hashed from the OPERATOR'S WORKING TREE
# (`factory/workgraph/workflow.py:1736` — `_run_node` passes `graph.specs_root`,
# and `specs/126-a-killed-node-leaves-no-ref-to-collide-with/workgraph.json`
# shows that is `/home/admin/code/ergane/specs`), while the node worktree is cut
# from ORIGIN's landing head and pinned there for the node's whole life
# (`factory/workgraph/worktree.py:349` — `_remote_head` resolves
# `origin/<landing branch>`; `factory/workgraph/worktree.py:362` — `ensure` says
# "no fetch, no rebase, no reset"). Nothing copies the operator's `spec.md` into
# the worktree. So the ordinary case — the operator refines a spec, the roadmap's
# five-minute schedule dispatches it from the working tree before the edit is
# pushed, origin still carries yesterday's bytes — would have flagged
# `criteria_drift` on every row of every such epic, with no node edit anywhere.
# The question this spec actually wants answered is "did the NODE move it", so
# the worktree copy is now compared against that same path at the node's own base
# ref (`prepared.base_ref`, the pin already recorded on the result at
# `factory/verify/models.py:942`). A worktree copy that is merely an older
# committed revision than the snapshot is not drift; the same copy with one line
# added by the node is.
#
# ONE KEY, AND WHAT IT DOES NOT CLOSE. Eleven FRs, all aimed at the one row.
# The row's own Fix names three remedies: make `specs/` read-only to a node,
# forbid the judge from prescribing criterion edits (102 did that), and fail
# verification when the diff touches `specs/`. This spec closes the landing and
# the detection. After it the node can still WRITE the bytes — the sandbox and
# `write_scope` are untouched — and a diff touching a DIFFERENT spec's directory
# is still not refused (`7d9f207` is a landed node PR that edited six other
# specs). THE KEY IS THEREFORE DECLARED FOR THE LANDING-AND-DETECTION HALF ONLY:
# the residue must be filed as its own open row BEFORE this spec is dispatched —
# plan.md § "Verification the operator will run" step 0, which is a pre-dispatch
# act precisely because a prose promise to re-open a row after a sweep is what
# 100, 092 and 118 each broke. A closed row is how a half-fix becomes invisible.
#
# NOT IN SCOPE. This spec does not re-open 102's invitation half; the prompt and
# `screen_feedback` are correct. It does not change the snapshot-once contract
# that fixes the goalposts for a node's whole life. It adds no AMENDED verdict.
# It does not touch `personas.yaml`, `WriteScope`, or the agent sandbox, and it
# does not make `specs/` read-only. It renders `criteria_drift` nowhere: no
# operator surface prints that column today and this spec does not add one.
---

# Feature Specification: a node cannot move the bar it is measured against

**Created**: 2026-09-04
**Depends on**: nothing.

## The gap, stated precisely

A node is dispatched to satisfy a spec, and the spec is a file inside the tree
the node is allowed to write. Nothing between the agent's keystroke and the merge
queue reads that as a problem.

The chain is six steps, and every control on it fails open:

1. **The write scope says where, never what.** `factory/config.py:159` —
   `WriteScope` is a closed set of three values, and the `DIFF_SCOPES` frozenset
   at `factory/verify/diffcheck.py:120` turns `worktree` into "your diff is your
   proof of work". Every dispatched persona carries it
   (`personas.yaml:274`, `personas.yaml:374`, `personas.yaml:414`, `personas.yaml:469`). No value of it excludes a path.
2. **The spec is in the worktree.** `specs/<feature>/spec.md` is tracked on the
   landing branch, so it is checked out into every node worktree
   (`factory/workgraph/worktree.py:289` — `worktree_path`, which places the
   worktree under the runtime root at `factory/workgraph/worktree.py:295` —
   `worktree_path`).
3. **The output check refuses two classes and neither is this one.**
   `factory/verify/diffcheck.py:311` — `hygiene_violations` refuses only what the
   target repository's own ignore rules already refuse and what sits under a
   factory runtime root (`factory/verify/diffcheck.py:511` —
   `_runtime_root_rule`). It is handed the diff's whole path list at
   `factory/verify/diffcheck.py:239` — `check_output`, and `specs/` is not a rule
   it knows.
4. **The only prohibition is prose.** `factory/workgraph/prompt.py:200` tells the
   agent "Do not weaken tests, skip gates, or narrow acceptance criteria to reach
   a green run." That paragraph binds intent. It does not read the diff.
5. **The drift flag hashes a file the node cannot reach.** `criteria.source_path`
   is built from `specs_root` (`factory/activities/verify_activities.py:208` —
   `spec_path`, called at `factory/activities/verify_activities.py:181` —
   `snapshot_criteria`), recorded at `factory/verify/criteria.py:480` —
   `load_criteria`, carried into the row at `factory/workgraph/workflow.py:2699` —
   `_verify`, and re-hashed at `factory/activities/verify_activities.py:617` —
   `_with_drift` through `factory/activities/verify_activities.py:621` —
   `_has_drifted`. `specs_root` in a compiled graph is the operator's checkout —
   `specs/126-a-killed-node-leaves-no-ref-to-collide-with/workgraph.json` carries
   `/home/admin/code/ergane/specs` — while the node worktree is cut from origin's
   landing head (`factory/workgraph/worktree.py:349` — `_remote_head`) and pinned
   there (`factory/workgraph/worktree.py:362` — `ensure`). For a worktree-side
   edit the bytes compared never change, so drift **cannot** fire.
6. **It has already landed here.** `701be6e`, the node PR for
   `016-delta-derivation/us4` (#17), deleted a sentence from
   `specs/016-delta-derivation/spec.md` — the spec that node was dispatched
   against — and merged. Seven more node PRs changed a criteria document of their
   own dispatched directory; six of those are `tasks.md` checkbox ticks.

**The node's own verdict was never the exposure.** Criteria are snapshotted once,
before the first attempt (`factory/workgraph/workflow.py:1736` — `_run_node`), the
row records the snapshot's hash (`factory/workgraph/workflow.py:2661` —
`_verify`), and even the prompt is assembled from the operator-side copy
(`factory/activities/agent_activities.py:963` — `load_prompt_sources`). A node
cannot lower its own bar for its own attempt. What it can do is **land** a lower
bar, which then binds every later dispatch of that spec — including the
re-dispatch of the very story that weakened it.

## The rule this spec is asking for

**A node's diff may not carry a change to the spec, plan or tasks it is being
measured against — the attempt is refused before it can land — and the drift flag
is measured against the bytes the node itself started from.**

Three documents, named. `SPEC_FILENAME`, `PLAN_FILENAME` and `TASKS_FILENAME`, at
`factory/activities/agent_activities.py:183`,
`factory/activities/agent_activities.py:184` and
`factory/activities/agent_activities.py:185`, are already the set the prompt is
assembled from; the refusal is about those three files in the dispatched
directory and about nothing else in it. (All three are module-level constants, so
the coarse cite is the only form the symbol tier can check —
`factory/cli/nouns/spec.py:825` — `_symbol_spans` indexes `def` and `class` nodes
only. Do not "upgrade" them; the gate refuses it.)

The cases. Rows one to four come from the file scans in the provenance block; row
five comes from the scan that reads node commits rather than files, which is the
only one that can see a document a node edited in place:

| changed path | is it a criteria document of the dispatched spec | result |
|---|---|---|
| `specs/<feature>/spec.md` | yes — the criteria are snapshotted from it | **refused**, `passed=False`, rule names the dispatched directory |
| `specs/<feature>/plan.md` or `specs/<feature>/tasks.md` | yes — the prompt is assembled from them | **refused**, same rule, one entry per refused path |
| `specs/<feature>/evidence/us1.txt` | no | pass — fifty such files are committed already, on the dispatched node's own PRs |
| `specs/<feature>/attempt-report-us3.md` | no | pass — fifteen such files across twelve spec directories, likewise on the dispatched node's own PRs, and twenty-one tasks across fourteen trios still instruct one |
| `specs/<feature>/tasks.md`, changed only from `- [ ]` to `- [x]` | yes — it is still `tasks.md` | **refused, deliberately.** Six landed node PRs did exactly this — `ea92b35` (#159), `1bfc8c8` (#143), `0f8f6b3` (#139), `65d53b5` (#97), `a3c4141` (#5), `aacc7fc` (#129, ticks plus rewritten task prose) — none since 2026-08-17, and nothing instructs it |
| `specs/<other>/spec.md` | no — a different bar | pass, unchanged; out of scope |
| any path, no dispatched directory declared | — | pass, byte-identical to today |

### What this spec is not

It is not a sandbox change. `write_scope` keeps its three values, `personas.yaml`
is untouched, and the agent can still write the bytes. This spec refuses the
diff, not the keystroke — and the diff is what lands.

It is not a refusal of the dispatched directory. Two classes of file land inside
it on the dispatched node's own pull request as a matter of house doctrine — the
pasted evidence under `evidence/` that Principle VIII requires, and the
`attempt-report-<story>.md` artifact fourteen trios instruct — and both keep
landing. Nothing binding names a directory for committed evidence, so a rule that
picked one would refuse conforming work in twelve directories that already exist.

It is not a rule with an exception for a small edit. A node ticking its own
`tasks.md` checkboxes is refused like any other change to that file: six landed
node PRs did it, the last on 2026-08-17, and reading content to tell a tick from
a rewrite would put the refusal in the business of judging edits rather than
naming files — while `aacc7fc` shows the two arriving in one commit. The class is
dormant, so refusing it costs no live conforming work; replaying one of those six
epics under this rule would fail its output check, which is the intended answer.

It is not a re-opening of 102's invitation half.
`factory/verify/remediation.py:191` — `screen_feedback` is correct and unedited.

It is not a change to the snapshot-once contract. The criteria the judge scores
against are still the ones taken before the first attempt, from `specs_root`, and
the row still records that snapshot's hash however either file changes.

It is not a re-hash of the dispatch snapshot against the worktree. The two copies
come from different places — the operator's working tree and origin's landing head
— and are routinely different with no node edit involved, so the worktree half of
the drift flag asks only whether the node changed the file relative to its own base
ref.

It is not a `specs/`-wide refusal. A diff touching a different spec's directory
still passes: `7d9f207` is a landed node PR that edited six other specs' `spec.md`
files, and refusing that class is a different rule with a different blast radius.

It adds no judge verdict. There is no AMENDED outcome here — a refused attempt
fails the output check, which already records three ways for a diff-scope node to
fail and expresses all of them as `passed=False` on one record.

It adds no operator surface. `criteria_drift` is a column on the evidence row
(`factory/verify/store.py:221`) that nothing in `factory/cli`, `factory/notify` or
`factory/escalation` prints, and this spec does not change that; the operator
reads it with a query, and making it legible is a different spec.

## User Scenarios & Testing

### User Story 1 - A diff that moves the node's own bar is refused before it can land (Priority: P1)

As an operator, a story that rewrites the spec it was dispatched against cannot
merge that rewrite, whatever the gates and the judge say about the rest of it.

**Why this priority**: P1 and it depends on nothing. This is the half that closes
the exposure — a weakened spec that lands binds every later dispatch — and the
half the reported incident and `701be6e` both exercised. US2's flag is worth
having only once the landing is shut.

**Independent Test**: Run the output check over a worktree whose diff carries the
dispatched spec's `spec.md` and `tasks.md`, and read the verdict and the recorded
refusals; then over one whose spec-side paths are the two artifact classes that
already land on node PRs — a file under `evidence/` and an
`attempt-report-<story>.md` — and read that both pass.

**Acceptance Scenarios**:

1. **Given** a diff-scope worktree whose changed paths include a production file,
   `specs/<feature>/spec.md` and `specs/<feature>/tasks.md`, where
   `specs/<feature>` is the directory the node was dispatched against, **When**
   the output check runs with that directory declared, **Then** it returns
   `passed=False` and records one entry per refused document, each carrying its
   path together with a rule that names the dispatched spec directory. A
   committed test asserts the verdict and both recorded paths and rules, so an
   implementation that refuses only `spec.md` fails it.
2. **Given** the same declared directory and a worktree whose only spec-side
   changed paths are `specs/<feature>/evidence/us1-report.txt` and
   `specs/<feature>/attempt-report-us1.md`, **When** the output check runs,
   **Then** it passes and records no refusal for either path, because those are
   the two classes of file the dispatched node's own pull request already carries
   — fifty committed under `evidence/` and fifteen attempt reports across twelve
   spec directories. The same committed test asserts both paths beside scenario 1
   over one fixture, so an implementation that refuses the whole directory fails
   it, and so does one that refuses the directory with an `evidence/` carve-out:
   the attempt report sits beside `evidence/`, not under it.
3. **Given** a diff whose only spec-side changed path is `specs/<other>/spec.md` —
   a spec this node was not dispatched against — **When** the output check runs
   with `specs/<feature>` declared, **Then** it passes, because the rule is about
   the bar this node is measured against and not about `specs/` wholesale. The
   same committed test asserts this beside scenario 1, so a check that refuses
   nothing cannot satisfy the pair.
4. **Given** a worktree whose diff includes `specs/<feature>/spec.md` and a caller
   that declares **no** dispatched spec directory, **When** the output check runs,
   **Then** the returned record equals the `OutputCheck` today's code returns for
   that worktree, asserted by a committed test that constructs the expected value
   literally, so every existing caller and every stored row is unaffected.
5. **Given** a work graph whose `specs_root` lies inside `target_repo`, **When**
   the epic workflow builds the output check's input for a node, **Then** that
   input names `specs/<feature>` as the dispatched spec directory, asserted by a
   committed test that reads the recorded input the workflow constructed. A test
   that hands the directory to the library seam by hand cannot satisfy this.
6. **Given** a work graph whose `specs_root` lies outside `target_repo`, **When**
   the same derivation runs, **Then** it yields no dispatched spec directory,
   asserted by a committed test that drives it with paths that do not exist on
   disk; the same test also drives it with `Path.exists` and `Path.stat` patched
   to raise and asserts the answer is unchanged, so an implementation that reads
   the filesystem fails rather than passes.

### User Story 2 - Drift is measured against the bytes the node started from (Priority: P2)

As an operator, when a node edits the spec inside its worktree the evidence row
says so — and when nobody edited anything, the row stays quiet even though the
operator's copy and origin's copy have drifted apart on their own.

**Why this priority**: P2 and it waits on US1's derivation of the repository-relative
spec directory. It is the detection half: US1 stops the edit landing, this records
on the evidence row that an attempt tried. It is worth building only if it can tell
a node edit from the routine disagreement between the operator's working tree and
origin's landing head, which is why the comparison is against the node's base ref
and not against the dispatch snapshot.

**Independent Test**: Record one verification for a node worktree whose copy of the
dispatched `spec.md` differs from the same path at the node's base ref, and read
`criteria_drift` off the returned value and the stored row; then record another
whose worktree copy matches its base ref but differs from the dispatch snapshot,
and read that the flag stays false.

**Acceptance Scenarios**:

1. **Given** a node worktree whose base ref carries `specs/<feature>/spec.md`, a
   worktree copy whose bytes differ from that base blob, and an operator-side copy
   that still hashes to the dispatch snapshot, **When** the verification is
   recorded, **Then** `criteria_drift` is true and the stored row's
   `criteria_sha256` is still the snapshot's. A committed test builds a real
   repository and node worktree and asserts both halves; today's code reads only
   the operator-side copy and answers false, so it fails before the change.
2. **Given** a node worktree whose copy of `specs/<feature>/spec.md` is byte-identical
   to the same path at its base ref but does **not** hash to the dispatch snapshot —
   the routine case where the operator's working tree has moved ahead of origin's
   landing head between the edit and the push — **When** the verification is
   recorded, **Then** `criteria_drift` is false, asserted by a committed test that
   makes the three byte sequences explicit. An implementation that compares the
   worktree copy against the snapshot flags this and fails.
3. **Given** a base ref with no `specs/<feature>/spec.md` and no copy at that path
   in the worktree — the ordinary case for a spec not committed to the landing
   branch — **When** the verification is recorded, **Then** `criteria_drift` is
   false; and given a base ref that carries the file and a worktree the node
   deleted it from, **Then** it is true; and given an operator-side copy that has
   been deleted, **Then** it is still true. One committed test asserts all three,
   so a change that reuses the operator-side "unreadable is drift" rule for the
   worktree copy fails it.
4. **Given** a caller whose result already carries drift, **When** the
   verification is recorded with both copies matching their baselines, **Then**
   `criteria_drift` stays true, asserted by a committed test, because a verifier
   that watched the spec move must not be overruled by a later read. The same test
   asserts that a result whose `base_ref` is `UNKNOWN_BASE_REF` attempts no
   worktree read at all.
5. **Given** the epic workflow recording an attempt for a node, **When** it calls
   the recording activity, **Then** the input it constructed carries the prepared
   worktree's path and the same repository-relative spec directory US1 derives,
   asserted by a committed test that captures the whole recording input rather
   than only its result.

## Functional Requirements

- **FR-001**: The output check MUST refuse a diff-scope attempt — `passed=False` —
  when any changed path is `spec.md`, `plan.md` or `tasks.md` directly inside the
  dispatched spec's own directory, and MUST record one entry per refused path
  carrying that path and the rule that refused it. The refusal MUST be by path,
  never by reading the changed file's content, so a checkbox tick and a rewritten
  requirement are refused alike.
- **FR-002**: The rule text MUST name the dispatched spec directory and MUST be
  distinguishable from the ignore-rule and runtime-root rule shapes already
  recorded on the same field, and the documentation of that field MUST be amended
  to enumerate the new shape.
- **FR-003**: A changed path inside the dispatched spec directory that is not one
  of those three documents MUST NOT be refused — in particular anything under its
  `evidence/` subdirectory and any `attempt-report-<story>.md` beside them —
  because both classes already arrive on the dispatched node's own pull request:
  fifty committed evidence files, and fifteen attempt reports across twelve spec
  directories that twenty-one tasks in fourteen trios' tasks.md still instruct.
- **FR-004**: A diff carrying no refused path MUST be evaluated exactly as today —
  including one that changes a different spec's directory — and the ignore-rule
  and runtime-root hygiene rules, the diff size refusal and the pass/fail rule
  they feed MUST be left unchanged.
- **FR-005**: When the caller declares no dispatched spec directory, including
  when the spec lies outside the target repository, the output check MUST return
  exactly what it returns today for the same worktree.
- **FR-006**: The epic workflow MUST derive the dispatched spec's
  repository-relative directory from the work graph by path arithmetic alone, with
  no filesystem read, and pass it into the output check's input, so the refusal is
  reached on the production path rather than only through the library seam.
- **FR-007**: `criteria_drift` MUST additionally be true when the node's worktree
  copy of the dispatched `spec.md` differs from that same repository-relative path
  at the node's own base ref — the pin already recorded on the attempt's result —
  and MUST NOT be true merely because the worktree copy differs from the dispatch
  snapshot, since the operator-side and worktree-side copies come from different
  revisions and routinely differ with no node edit involved.
- **FR-008**: The worktree comparison MUST answer "not drift" when neither the base
  ref nor the worktree carries the file, and "drift" when exactly one of them does;
  it MUST attempt no worktree read when the caller supplied no worktree path, no
  repository-relative spec directory, or a result whose base ref is the unknown
  sentinel; a base-ref read that fails for any other reason MUST leave the
  operator-side answer standing rather than manufacture drift; and the
  operator-side rule — unreadable is drift — MUST stay exactly as it is.
- **FR-009**: Drift already carried by the caller's result MUST still never be
  cleared, and the row MUST still record the dispatch snapshot's hash rather than
  either file's current one.
- **FR-010**: The epic workflow MUST pass the prepared worktree's path and the same
  repository-relative spec directory FR-006 derives into the recording input, so
  the new comparison has both of its sides on the production path; the base ref
  MUST be taken from the result the workflow already composed rather than
  re-derived, so the drift read uses the same pin the gates and the judge were
  measured against.
- **FR-011**: The snapshot-once contract MUST be left intact: the criteria the
  judge scores against MUST still be taken once, before the first attempt, from
  `specs_root`; the recorded criteria hash MUST still be the dispatch snapshot's;
  and the worktree copy MUST NOT be read as criteria by any story.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-007, FR-008, FR-009, FR-010, FR-011]
```

One `depends_on_merged` edge, declared rather than left inferred (069-US2 FR-007).
US2 reuses the repository-relative spec directory US1 derives and joins it to the
prepared worktree's path, and the two stories edit the same two files —
`factory/activities/verify_activities.py` and `factory/workgraph/workflow.py` — in
different functions. The edge therefore buys both correctness of sequencing and
freedom from contention: US2 opened against an unmerged US1 would either duplicate
the derivation or import a symbol that does not exist on its base.
