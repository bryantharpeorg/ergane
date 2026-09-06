# Implementation Plan: the boundary detector charges an attempt only for what it wrote

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

`git diff v0.5.0 HEAD -- factory/workgraph/detector.py` is **empty** — the tree
and the released wheel are identical here, so unusually for this corpus there is
no release-lag question. What the consumer measured is what you will edit. The
last commit to that file is 073's own, `669006d`, 2026-08-21; nothing has touched
it since, including the four 057 stories that landed between the drafting of this
spec and this refinement.

## What already exists, and where

**The constants.** `FINDING_KEY` (`factory/workgraph/detector.py:58`),
`EXCLUDED_DIR_NAMES` (`factory/workgraph/detector.py:70`) —
`frozenset({"__pycache__", ".pytest_cache"})` — and `EXCLUDED_SUFFIXES`
(`factory/workgraph/detector.py:73`), which is `(".pyc",)`. These three are
module-level assignments, not definitions, which is why they are cited in
parentheses and not in the `` `path.py:NN` — `symbol` `` form: the symbol tier
resolves function and class definitions only, and would refuse an assignment as
absent.

**The walk.** `factory/workgraph/detector.py:311` — `_runtime_root_state`
iterates every node directory under the runtime root and skips exactly one, at
`factory/workgraph/detector.py:336` — `_runtime_root_state`:

```python
                if node_dir.resolve() == own_resolved:
                    continue
```

Everything else is snapshotted, contents included, by
`factory/workgraph/detector.py:349` — `_snapshot_paths`, which prunes as it
descends. That walk is the **only** consumer of `EXCLUDED_DIR_NAMES` and
`EXCLUDED_SUFFIXES` in the entire tree; the two other places the name appears are
prose (`factory/activities/roadmap_activities.py:190` and
`tests/test_090_refusal_parks_the_spec.py:35`).

**The other half of the runtime-root snapshot, which survives all four stories.**
The same function records three named store files at the root before it reaches
the worktrees:

```python
    for name in ("doctor.db", "ledger.db", "verification.db"):
        path = root / name
        entries[name] = _describe_path(path)
```

Only *loss* is reported: `factory/workgraph/detector.py:134` — `_is_loss` returns
False when `before` is absent, so a creation is silent and a truncation is not.
This is what still catches the 2026-08-14 case — the runtime root deleted
outright — after US2 stops watching sibling worktrees.

**The target-repo half already defers to the target's own ignore rules.**
`factory/workgraph/detector.py:265` — `_tracked_state` reads untracked files with
`git ls-files --others --exclude-standard`, run in the target repository. A
JavaScript target's ignored `node_modules` is therefore already invisible to this
half. That is the mechanism FR-006 says must be the surviving one, and it is the
reason US3 is a removal rather than a rewrite.

**The two snapshots are different kinds.**
`factory/workgraph/detector.py:533` — `capture_start` calls
`factory/workgraph/detector.py:279` — `_committed_state` (the HEAD tree), while
`factory/workgraph/detector.py:592` — `compare_and_report` calls `_tracked_state`
(the working tree). The docstring at
`factory/workgraph/detector.py:279` — `_committed_state` says the asymmetry is
deliberate: working-tree changes present when the attempt begins "show up as a
difference at teardown". FR-007 reverses that half.

**The provenance that is captured and dropped.**
`factory/workgraph/detector.py:405` — `_write_snapshot` writes
`"target_repo": str(tracked.repo) if tracked else None` into the start snapshot;
`factory/workgraph/detector.py:584` — `compare_and_report` reads it back into
`start_tracked.repo`; and the builder it calls at
`factory/workgraph/detector.py:598` — `compare_and_report` is handed
`(context, tracked_changes, runtime_changes, seen_at)` and nothing else.
`factory/workgraph/detector.py:440` — `_build_finding` has no repository
parameter at all. FR-008 is mostly a matter of not throwing it away.

**The finding is advisory.** `compare_and_report` is called at
`factory/workgraph/adapter.py:1177` — `run_attempt` (the exception path) and
`factory/workgraph/adapter.py:1185` — `run_attempt` (the normal path), and **its
return value is discarded at both**. Nothing branches on it.

**The sandbox is the layer that actually contains the write.**
`factory/workgraph/adapter.py:523` — `_build_argv` binds the worktree's *parent*
read-only "so bwrap does not create a writable intermediate directory that exposes
sibling worktrees", and `factory/workgraph/adapter.py:538` — `_build_argv` binds
the whole runtime root read-only "so stores and sibling worktrees cannot be
altered".
`tests/test_us3_boundary.py:232` — `test_write_to_target_repo_working_tree_fails_and_leaves_tree_unchanged`
drives
that with the real backend and pastes the OS refusal. This is why FR-004's loss of
observation is affordable: the observation was never able to attribute, and the
prevention lives a layer down.

**The unconditional artifact write.**
`factory/workgraph/cli.py:384` — `derive_command` writes the graph before `--json`
is consulted, into the destination assigned one line above it at
`factory/workgraph/cli.py:382`, and the bytes are a pure function of the derived
graph:

```python
    destination = Path(args.output) if args.output else spec_dir / ARTIFACT_NAME
    try:
        destination.write_text(
            json.dumps(asdict(graph), indent=2) + "\n", encoding="utf-8"
        )
```

The statement a guard has to reach is the `write_text` call, not the assignment
above it: `factory/workgraph/cli.py:382` decides *where*,
`factory/workgraph/cli.py:384` decides *whether*.

`as_json` is first read at `factory/workgraph/cli.py:390` — `derive_command`, and
the document it builds carries `"artifact": str(destination)` at
`factory/workgraph/cli.py:391` — `derive_command`. There are **97** committed
artifacts in the tree (`git ls-files specs/ | grep -c workgraph.json`), so this
write has real consumers.

**There is one write site, reached through two doors.** `ergane spec derive` runs
`factory/cli/nouns/spec.py:255` — `_derive_command`, which gates on ERGANE-TODO
sentinels and then delegates to the handler above; `--json` is declared with
`dest="as_json"` at `factory/cli/nouns/spec.py:182` — `_add_spec_parser`. The
second door is `factory/cli/nouns/build.py:1045` — `ship_command`. Both end at
`factory/workgraph/cli.py:384`, so one guard covers both — which is exactly why
the guard must be written for both. See trap 3.

**The tree already argues US3's direction, in its own words.**
`factory/activities/roadmap_activities.py:190`: git's own ignore rules — "the
*target repo's*, not a list this function carries" — are what keep generated
directories out, closing with "`EXCLUDED_DIR_NAMES` is the standing reminder of
what a hand-written list costs." That comment is about this constant.

## Traps

**Trap 1 — A COMMITTED SPEC REQUIRES THE BEHAVIOUR THIS SPEC REMOVES, AND SAYS SO
IN ITS OWN TEXT.** `specs/073-the-ledger-triages-what-it-can-prove/spec.md:282`
is US4 scenario 2: "Given a runtime root where a sibling worktree is removed
during the attempt ... a finding is filed naming it — proven by a committed test.
**This is scenario 1's control, and it is the behaviour that must survive.**" Its
committed control is
`tests/test_detector_reports_removals_only.py:176` — `test_sibling_worktree_removed_files_a_finding_naming_it`,
and the same file's banner comment above it reads "the control — removal must
survive". The landed requirement standing behind the scenarios is
`specs/011-agent-sandbox/spec.md:358`, 011's FR-012: the detector MUST cover
"every node worktree other than the attempt's own" and MUST file a critical when
any of them is "removed, truncated or replaced". FR-005 reverses that MUST, and a
reader who checks the override must find it named rather than left standing.

073 was not wrong on its own terms; it did not know that **the factory itself
removes sibling worktrees as ordinary housekeeping**.
`factory/workgraph/workflow.py:3582` — `_remove_worktree` is called at
`factory/workgraph/workflow.py:3329` — `_escalate_ref_conflict`,
`factory/workgraph/workflow.py:3550` — `_poll_landing`,
`factory/workgraph/workflow.py:3576` — `_poll_landing` and
`factory/workgraph/workflow.py:4298` — `_apply_landing_resolution`. So 073's
"control" fires on the factory's own normal operation. The same requirement is
also written into `specs/011-agent-sandbox/spec.md:198`, US1 scenario 5, which
names "a sibling's worktree" alongside the evidence stores.

FR-005 reverses both **deliberately and in writing**. Do not quietly delete 073's
test: invert it, and make the diff say that this spec overrides a prior spec's
scenario and why. A silent deletion of another spec's committed control is
indistinguishable from a story weakening a test to go green. **Write that
statement into 073's frontmatter comment block and the test's docstring, never
into 073's scenario text** — the scenario text is fingerprint input and editing it
reopens a landed story. Trap 15 is that mechanism, and it applies to 011 in the
same breath.

**Three tests must be edited in US2, not one.** The second is
`tests/test_detector_reports_removals_only.py:144` — `test_sibling_worktree_gaining_files_files_no_finding`.
Exactly one of its two snapshot assertions goes red:
`tests/test_detector_reports_removals_only.py:158` names `sibling.py`, and that
stops being true once the walk stops visiting siblings. Its neighbour at
`tests/test_detector_reports_removals_only.py:157` — the bare `assert entries` —
**stays true and must be kept**, because the three store files recorded at
`factory/workgraph/detector.py:323` — `_runtime_root_state` survive US2 and are
what keeps the snapshot non-empty at all. Update that line's message string
("the snapshot should still record the sibling's real content" becomes false),
not its assertion; deleting it loses the only check that the runtime-root snapshot
holds anything. The test's final assertion — no finding is filed — stays as it is.
The third is the one the drafted spec promised would pass unedited:
`tests/test_us1_detector.py:429` — `test_agent_truncating_runtime_root_store_files_finding`
truncates the sibling worktree at `tests/test_us1_detector.py:449` and then asserts
at `tests/test_us1_detector.py:460-462` that the finding names
`worktrees/<epic>/us2`. Today that passes only because the runtime-root walk records
the sibling's file; after T013 the path is in neither snapshot, so **exactly one
assertion in it goes red** while its `doctor.db` and `ledger.db` halves stay green.
Its docstring calls it "US1-S5 / FR-012", so it is 011-US1 scenario 5's third
committed control, not a separate requirement. Remove the sibling assertion, keep
the store assertions and the read-only assertion at
`tests/test_us1_detector.py:468`, and say in the diff which scenario is overridden.
Do not "fix" it by making US2 keep snapshotting siblings.

**Trap 2 — DO NOT WIRE THE FINDING INTO A VERDICT.** The return of
`compare_and_report` is discarded at
`factory/workgraph/adapter.py:1177` — `run_attempt` and
`factory/workgraph/adapter.py:1185` — `run_attempt`. An
implementer who "fixes" the detector will be tempted to make its now-trustworthy
finding actually *do* something. FR-010 forbids it. A channel that has been firing
90 false criticals is not one to make enforcing in the same change that makes it
accurate — and the whole cost recorded against this detector came from believing
it, not from it being ignored.

**Trap 3 — THE GUARD THE FIRST DRAFT ASKED FOR BREAKS `ergane build ship --json`,
AND NO TEST WOULD HAVE CAUGHT IT.**
`factory/cli/nouns/build.py:1029` — `ship_command` passes **its own** `args`
namespace straight to the derive handler at
`factory/cli/nouns/build.py:1045` — `ship_command`, and ship declares its own
`--json` with `dest="as_json"` at
`factory/cli/nouns/build.py:2134` — `add_parser`. Ship then requires the artifact
on disk at
`factory/cli/nouns/build.py:1051` — `ship_command`, raising "derive reported
success but wrote no artifact" when it is missing. So `ergane build ship --json`
presents to the handler as exactly `as_json=True, output=None` — the shape the
guard is supposed to deny — and there is **no committed test that runs ship with
`--json`** (`grep -n as_json tests/test_ergane_build_ship.py` returns nothing), so
the suite stays green while the command breaks. FR-011 is the requirement; the
cheapest satisfying shape is for the caller that needs the artifact to ask for it
by path, since FR-002 already makes an explicit output path a request to persist.
Whatever shape you pick, US1-S5's test must fail against a guard keyed on `--json`
alone.

**Trap 4 — The `--json` document claims an artifact it may not have written.**
`factory/workgraph/cli.py:391` — `derive_command` emits
`"artifact": str(destination)`. If US1 stops writing, that key becomes a lie. Drop
it, or make it explicitly a would-be path. FR-003 exists because a consumer parsing
that key would follow it to a file that is absent or stale.

**Trap 5 — TWO RESOLVED ROWS LOOK LIKE THIS SPEC'S WORK AND ARE NOT.** All three
keys in this spec's `fixes:` list are **open** — three, not four: the detector's
own channel key is deliberately not declared, and trap 7 says why. What is
resolved is a different
pair — `hardening/the-worktree-boundary-detector-snapshots-the-whole-runtime-root-...`
and `cli/spec-derive-json-writes-into-the-target-repo-...` — whose resolutions
begin "duplicate identity: merged into", naming two of the declared keys as their
canonical rows. Neither is in `fixes:`, and neither is evidence that any of this
work is done. Reading a resolved row as a landed fix is exactly the mistake the
standing lesson warns about.

**Trap 6 — 073 genuinely fixed one half, and only one.**
`hardening/the-boundary-detector-files-a-sibling-nodes-pytest-cache-as-this-attempts-escape`
is correctly resolved by 073: its `_is_loss` narrowing at
`factory/workgraph/detector.py:134` — `_is_loss` covers sibling **creations**. It
does not catch a sibling **removal**, which is the shape still firing. Do not
conclude from that resolved row that the sibling problem is solved.

**Trap 7 — `hardening/agent-worktree-boundary` IS THE DETECTOR'S OWN CHANNEL KEY,
AND IT IS DELIBERATELY NOT DECLARED.** It is not a defect row: it is `FINDING_KEY`
at `factory/workgraph/detector.py:58`, the key **every** finding this detector will
ever file carries, including the genuine escape FR-009 requires to keep firing. Do
not add it back to `fixes:` on the reasoning that this spec removes the cause of
its 90 occurrences — it does, and that is still the wrong move. A landed spec's
`fixes:` list is read by `factory/doctor/triage.py:583` — `_declared_index`, which
indexes declarations from landed specs only, and `factory/doctor/triage.py:864` —
`apply_triage` resolves what it classifies; declaring the channel key would close
the channel on paper the moment this spec lands, and the **first genuine escape**
afterwards would re-report against a resolved row as `seen-after-fix` — i.e. as
this spec regressing. The accumulated row is closed by an operator, by hand,
naming this spec, after `ergane findings list` has shown it not incrementing across
a full epic (operator step 5). That is a decision this diff must not make for them.

**Trap 8 — US3 IS A DELETION. DO NOT BUILD AN IGNORE-RULE ENGINE.** FR-006 reads
"come from the target repository's own ignore rules", and the tempting move is to
add a `.gitignore` parser, a `pathspec` dependency, or a `git check-ignore` call
per path. All three are wrong. After US2 the detector looks in exactly two places:
the target repository, where `factory/workgraph/detector.py:265` — `_tracked_state`
already applies the target's rules through `--exclude-standard`, and the three
named store files at the runtime root. There is nothing left for a list to prune,
so the correct diff removes `EXCLUDED_DIR_NAMES`, `EXCLUDED_SUFFIXES` and
`factory/workgraph/detector.py:349` — `_snapshot_paths`, and adds the test that
says no such list came back. The second wrong move is reading **ergane's own**
`.gitignore`: the detector runs on a host building someone else's repository, and
a fix that works on this floor and fails on every consumer is the exact shape of
the defect being fixed.

**Trap 9 — US4 OVERRIDES A SECOND COMMITTED SCENARIO, AND ITS CONTROL TEST IS
GREEN TODAY.** `specs/011-agent-sandbox/spec.md:191` is US1 scenario 3: "Given an
attempt during which the operator themself edits the target repository ... the
finding still reports the change — the detector reports what happened, and does
not try to attribute intent." Its committed control is
`tests/test_us1_detector.py:322` — `test_operator_work_is_reported_and_untouched`,
which writes an uncommitted `operator_work.txt` before the attempt and asserts the
finding names it. FR-007 reverses the *reporting* half of that test and keeps the
*read-only* half — the detector must still leave the operator's file
byte-identical, which is why US4-S5 exists. Edit that test openly, in the same
style trap 1 demands for 073, and say in the diff which scenario is being
overridden and why — in the test's docstring and in a `#` provenance line inside
011's frontmatter fence, **not** in 011's scenario text. Trap 15 says what editing
that text would cost.

**A SECOND TEST IN THAT FILE HAS THE SAME SHAPE AND IS NOT OBVIOUS.**
`tests/test_us1_detector.py:357` — `test_detector_runs_on_completed_agent_error_timeout_and_killed`
writes its tracked-file change at `tests/test_us1_detector.py:386`, **before** each
of its four `env.run(run_agent_attempt, ...)` calls — and `capture_start` runs
inside `run_attempt` at `factory/workgraph/adapter.py:1129` — `run_attempt`, before
the agent launches. So under FR-007 every iteration records the change at start,
reports nothing at teardown, and the closing `finding is not None` and
`occurrences >= 4` assertions go red. The correction is not to weaken those
assertions: move each iteration's write to *during* the attempt, exactly as
`tests/test_us1_detector.py:249` — `test_agent_modifying_tracked_file_in_target_repo_files_finding`
already does. Before dispatching US4, re-read the whole file for that shape — a
write before `env.run` is now the excluded class; `:249` is safe, `:322` and `:357`
are not. `tests/test_us3_boundary.py`
also *relies* on this behaviour in a comment at its line 244-247, explaining why
its fixture commits the file first; that comment becomes wrong and should be
corrected in the same story.

**Trap 10 — US2 MUST NOT TAKE US3's WORK WITH IT.** Once the walk stops visiting
sibling worktrees, `factory/workgraph/detector.py:349` — `_snapshot_paths` and both
constants become unreferenced, and the tidy instinct is to delete them in the same
change. Do not: US3 is a separate node whose entire production diff is that removal
plus the test that no list came back, and a story that arrives to find its work
already done has nothing to be judged on. Leave them in place; US3's slice says so
from the other side.

**Trap 11 — THE LEDGER ROWS NAME A FILE THAT DOES NOT EXIST.** Two of the three
declared findings carry `factory/verify/boundary.py` in their `refs`, and the
third names `factory/cli/repo.py`. There is no `factory/verify/boundary.py` in this tree; the
detector is `factory/workgraph/detector.py` and the derive write is
`factory/workgraph/cli.py`. The refs were written by a consumer reading their own
symptoms, not this source tree. Follow the anchors in this plan, not the refs in
the ledger.

**Trap 12 — THE MODULE'S OWN PROSE ASSERTS THE BEHAVIOUR YOU ARE REVERSING.** The
module docstring at `factory/workgraph/detector.py:1` says the detector reports
"any evidence store / ledger / **sibling worktree** that was removed or truncated";
`factory/workgraph/detector.py:203` — `_tracked_state` says "it never tries to
attribute intent"; `factory/workgraph/detector.py:279` — `_committed_state`
explains the start-snapshot asymmetry as a feature; and
`factory/workgraph/detector.py:314` — `_runtime_root_state` says "``own_worktree``
is excluded: the agent is allowed to write there." Each of those sentences becomes
false in the story that changes the behaviour under it. Update the prose in the same
diff. A landed story whose docstring contradicts its own code is a shape this
factory has shipped before, and it costs a reader an hour to work out which one is
lying.

**Trap 13 — YOUR EVIDENCE MUST BE SOMETHING A NODE CAN PRODUCE.** The operator
sequence below runs two overlapping epics and makes a live operator commit; a node
in a worktree can do neither. Every "paste, as committed evidence" task in
`tasks.md` therefore asks for the transcript of a test **you** wrote and ran —
tool output pasted, never described (constitution VIII, D-037). Building a fake
runtime root with a sibling worktree is a `tmp_path` fixture, not a dispatch;
`tests/test_detector_reports_removals_only.py:58` — `sibling` is the one to copy.

**Trap 14 — US1'S NATURAL FIXTURE IS GREEN BEFORE YOU WRITE A LINE OF
PRODUCTION CODE.** `factory/workgraph/cli.py:384` — `derive_command` writes
`json.dumps(asdict(graph), indent=2)`, a pure function of the spec text, the tasks
text, `--target-repo` and `--specs-root`. So the obvious test — derive the
artifact, run `derive --json`, assert the bytes did not change — passes against
today's unconditional write, and the declared ledger row says so in its own control
line: "same command with the committed target leaves content identical but touches
mtime — the write is unconditional". A test that cannot fail is not a test, and the
phase's "write FIRST, must fail" rule is what catches it. The fixture must make the
on-disk artifact **differ** from what the invocation would derive: seed it with a
`target_repo` naming another path (that is the recorded harm — 064's and 073's
committed graphs were rewritten exactly this way from an operator checkout), then
assert those seeded bytes survive the call. Apply the same test to the other four:
US1-S2 and US1-S3 are controls by construction, US1-S4 must assert the artifact key
is **absent** rather than that it is honest, and US1-S5 must be written so it fails
against a guard keyed on `--json` alone (trap 3).

**Trap 15 — EDITING A LANDED STORY'S SCENARIO TEXT REOPENS IT, AND THIS SPEC
OVERRIDES TWO LANDED STORIES.** `specs/011-agent-sandbox/spec.md:2` and
`specs/073-the-ledger-triages-what-it-can-prove/spec.md:2` are both
`state: landed`. A landed story's identity is a digest over exactly the material an
override is tempting to edit:
`factory/workgraph/landed.py:438` — `_story_parts` normalises the story title at
`factory/workgraph/landed.py:460`, folds in every acceptance scenario's raw text at
`factory/workgraph/landed.py:461`, and folds in the bodies of the FRs that story
implements at `factory/workgraph/landed.py:475`; the work-graph declaration goes in
too, through `factory/workgraph/landed.py:481` — `_declaration_text`. Delta
derivation subtracts a landed story **only** while the pinned digest still equals
the current one — `factory/workgraph/delta.py:142` — `derive_delta` — and
re-opens it as a node to dispatch when it does not
(`factory/workgraph/delta.py:194` — `derive_delta` is the subtraction that then
does not happen). Worse, the guard at
`factory/workgraph/delta.py:151` — `derive_delta` can raise `DerivationError` on
identity instead. This is not a manual-only path: the roadmap re-derives through
`factory/activities/roadmap_activities.py:423` — `_derive_from_git` on its own
schedule. So a well-meant "edit 073-US4 scenario 2 to say it was overridden" spends
a future attempt rebuilding a story that landed on 2026-08-21.

The override still has to be **written down**, or a reader meets a green test that
contradicts a landed scenario and cannot tell a deliberate reversal from a
weakened test. Write it in the three places the digest does not read: a `#`
provenance line inside the landed spec's frontmatter fence (comments are inside the
YAML fence and never reach `_story_parts`), the docstring of the test that inverts
the behaviour, and the commit message. Leave the scenario text, the story titles,
the `## Work Graph` block and the FR bodies byte-identical. Operator step 6 is the
proof, and it is the step to run before believing this trap was respected.

## Sizing

US1 touches `factory/workgraph/cli.py` and, for FR-011, whichever side of
`factory/cli/nouns/build.py` — `ship_command` you choose to make the request
explicit. Tests: a derive-artifact byte-comparison, the two write controls, the
document assertion, and one ship-with-`--json` test. Small.

US2 is the walk in `_runtime_root_state`, plus editing two tests in
`tests/test_detector_reports_removals_only.py`, one assertion in
`tests/test_us1_detector.py:429` — `test_agent_truncating_runtime_root_store_files_finding`,
and one `#` provenance line inside the frontmatter fence of
`specs/073-the-ledger-triages-what-it-can-prove/spec.md` — never its scenario
text, which is fingerprint input (trap 15). Small in production
lines; the test work and the written override are the bulk. US2 and US4 both edit
`tests/test_us1_detector.py`, which the merged edges already serialise.

US3 is a removal: two constants, one generator function, the prose that names them,
and a test asserting the names are absent. It is the smallest diff of the four and
the one with the longest reach — it is what stops a hand-written list growing back
in a target language nobody here tested against — and it can only be judged after
US2 has landed.

US4 carries `target_repo` through to
`factory/workgraph/detector.py:440` — `_build_finding`, makes the start snapshot
symmetrical with the teardown one, records the target repository's HEAD so a commit
during the attempt is distinguishable from a write, and edits **two** tests in
`tests/test_us1_detector.py` — `:322` and `:357` (trap 9) — plus one `#`
provenance line inside `specs/011-agent-sandbox/spec.md`'s frontmatter fence
(trap 15). Largest of the four in production lines, still small in absolute terms.

Every story's diff — code, edited tests, new tests and pasted evidence together —
is far inside the 64 KiB refusal in `factory/verify/diffbounds.py`, provided the
pasted evidence is a focused pytest transcript and not a run log. US2, US3 and US4
all edit `factory/workgraph/detector.py`, which is why they are serialised. US1
shares no production file with any of them.

## Verification the operator will run, independent of the gate

Per constitution VIII and D-037 the judge sees the diff and the criteria only, so
runtime evidence must be committed as pasted output. Beyond that:

**0. Before any dispatch, delete the compiled artifact sitting in this spec
directory.** `specs/130-the-boundary-detector-charges-an-attempt-only-for-what-it-wrote/workgraph.json`
was compiled on 2026-09-04, *before* this refinement, and its `us1` node's
`requirement_keys` read `["US1", "FR-001", "FR-002", "FR-003"]` — **no FR-011**,
which is exactly the requirement added to stop US1 shipping a `--json` guard that
breaks `ergane build ship --json` with a green suite (trap 3). `ergane build start`
dispatches from the artifact it is handed, loaded at
`factory/cli/nouns/build.py:808` — `start_command`, and `ergane build reset`
resolves one from `<specs-root>/<epic-id>/workgraph.json` at
`factory/cli/nouns/build.py:1657` — `resolve_reset_graph` and loads it at
`factory/cli/nouns/build.py:1667` — `resolve_reset_graph`; a node dispatched
through either is never held to FR-011 by the judge, because FR-011 is not in its
requirement keys. The roadmap path is safe — it re-derives from the spec text
through `factory/activities/roadmap_activities.py:423` — `_derive_from_git` — and
that asymmetry is what makes this easy to walk into: whether a dispatch honours
this refinement depends on which verb the operator used. So, before flipping the
spec:

```bash
rm specs/130-the-boundary-detector-charges-an-attempt-only-for-what-it-wrote/workgraph.json
```

and do not commit that file with the trio. A compiled graph committed beside a
spec it no longer matches is the same stale artifact FR-001 exists to stop
`spec derive --json` making, and it is how 064's and 073's committed graphs were
poisoned.

1. `git status` clean, then `ergane spec derive --json` against a real spec
   directory **whose committed artifact records a different `target_repo`** — the
   only invocation that makes the write visible, and the one the ledger row
   records. `git status` must still be clean. Then `ergane build ship --json
   --target-repo $PWD <spec-dir>` up to the confirmation pause: it must reach the
   summary rather than raising "derive reported success but wrote no artifact".
2. Raise `max_concurrent_epics` to 2 and dispatch two epics that overlap. Neither
   may file a boundary finding against the other.
3. Let a sibling node finish and have its worktree removed while another attempt
   runs. No finding.
4. Make an operator commit in the target repository while a node runs. No finding.
   Then leave an uncommitted edit in place across an attempt: also no finding, and
   the file is untouched.
5. Confirm `ergane findings list` shows `hardening/agent-worktree-boundary`
   **not incrementing** across a full epic, then sweep the accumulated row by hand,
   naming this spec — the key is not in `fixes:` precisely so that nothing closes
   it mechanically, and trap 7 says why.
6. Prove the two landed specs this one overrides were not reopened by the
   override. For each of `specs/011-agent-sandbox` and
   `specs/073-the-ledger-triages-what-it-can-prove`, run
   `ergane spec derive <spec-dir> --delta --target-repo $PWD -o "$(mktemp)"`. Each
   must print "nothing to build: all stories are already landed and unchanged" —
   the early return at `factory/workgraph/cli.py:359` — `derive_command`, whose
   message is at `factory/workgraph/cli.py:363` — `derive_command`. Any other
   output names a story whose fingerprint moved, and that story will be dispatched
   again the next time its epic is derived. `-o` to a scratch path is not
   decorative: a non-empty delta falls through to the write at
   `factory/workgraph/cli.py:384` — `derive_command` and would rewrite the
   committed artifact of a landed spec.

Step 2 is the falsifiable test of the whole spec: `max_concurrent_epics` has been
pinned at 1 for an entire build because of this detector, and raising it is the
outcome that justifies the work.
