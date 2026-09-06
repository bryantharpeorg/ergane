# Implementation Plan: an operator correction reaches a running node or says it cannot

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## What already exists, and where

**The whole mechanism, already written, already tested, already reachable from
one door.** `factory/workgraph/worktree.py:1316` — `sync_with_target` is the
function this spec routes to. The second half of its docstring,
`factory/workgraph/worktree.py:1332-1339`, is the contract US1 is buying, in the
tree's own words:

```
    A clean merge reports `clean=True` and returns the merged-in target head as
    the new `base_ref`, so re-verification's diff and judge see only the node's
    own work (D-027 extended). A conflict reports `clean=False` with the
    conflicted file list and leaves the conflict markers in the tree — the
    debugger persona's work surface (FR-006).

    The node branch is never rewritten: no rebase, no force, no reset. The commit
    the queue may still be deciding on stays reachable (FR-008).
```

The activity that wraps it is
`factory/activities/merge_activities.py:580` — `sync_landing_branch`; it calls
the helper on a thread at `factory/activities/merge_activities.py:596-598` and
turns three outcomes into data: clean, conflicted, and `refused=True` with a
reason. It is registered on the worker at `factory/worker.py:178`. The workflow
executes it in exactly one place — `factory/workgraph/workflow.py:3703` — on the
landing-recovery path, which is reached only after the merge queue rejects a
pull request. **US1 adds a second caller of an existing activity. It writes no
git.**

**The pin, and the sentence that makes it deliberate.**
`factory/workgraph/worktree.py:362` — `ensure` is idempotent by construction;
`factory/workgraph/worktree.py:371-375` says "an existing directory is returned
as-is, untouched — no fetch, no rebase, no reset". The currency test at
`factory/workgraph/worktree.py:420-441` names the rule this spec must not break:

```
                # Measured only here, on the preparation path — never between
                # attempts (118 FR-004, R5): `ensure` is the caller-side seam
                # the workflow executes once per node, before its attempt loop,
                # and a retry reuses the recorded `prepared` worktree without
                # calling it again, so the same tree the last attempt left
                # always opens, whatever the landing branch has done since.
```

`prepare_worktree` is executed once, at `factory/workgraph/workflow.py:1744`,
and the result is stored at `factory/workgraph/workflow.py:1758`.

**Where the pin is actually consumed, which is not the record.**
`factory/workgraph/workflow.py:1715` — `_run_node` keeps the prepared worktree in
a *local*, assigned at `factory/workgraph/workflow.py:1744`, and hands that local
— not `record.prepared` — to `factory/workgraph/workflow.py:2559` — `_verify` at
`factory/workgraph/workflow.py:2076-2080`. Inside `_verify` it becomes every
measurement the attempt is judged by:

```python
            RunGatesInput(worktree_path=prepared.path),
...
                base_ref=prepared.base_ref,
                expected_artifacts=[],
                # 092 FR-004: the target repo's own ceiling, pinned at dispatch.
                diff_size_limit=request.diff_refusal_bytes,
...
                    worktree_path=prepared.path, base_ref=prepared.base_ref
```

— the gates' path at `factory/workgraph/workflow.py:2601`, `check_output`'s base
and diff-size ceiling at `factory/workgraph/workflow.py:2614`, the judge's diff
base at `factory/workgraph/workflow.py:2629`, and the base written onto the
verification row at `factory/workgraph/workflow.py:2672`. `record.prepared` is
read again only on the recovery re-entry. This is why FR-005 is two clauses and
not one.

**The one channel that is NOT pinned, which 118 landed and this spec must not
rebuild.** `factory/activities/agent_activities.py:1022` — `resolve_standards`
(input dataclass at `factory/activities/agent_activities.py:1004`, blocking half
at `factory/activities/agent_activities.py:1059` — `_resolve_standards_sync`),
registered at `factory/worker.py:115`, executed per attempt at
`factory/workgraph/workflow.py:1826` and again on the recovery re-entry at
`factory/workgraph/workflow.py:3916`. Its docstring names this defect outright:
"a correction the operator lands mid-epic reaches no attempt of a running node.
This closes that gap per attempt".

**The accounting that belongs to the landing path and to nothing else.** Around
the recovery sync, `factory/workgraph/workflow.py:3711` escalates a refusal and
`factory/workgraph/workflow.py:3716` charges a recovery cycle:

```python
        if sync.refused:
            # A recovery that could not run is not a silent pass — it escalates.
            await self._escalate_and_apply(graph, request, resolved, sources, judge)
            return

        if free and not sync.clean:
            ...
            record.landing = replace(
                record.landing,
                recovery_cycles=record.landing.recovery_cycles + 1,
            )
```

Immediately below it, at `factory/workgraph/workflow.py:3734-3736`, is the half
US1 **does** copy — moving the branch point so re-verification measures the
node's own work. Read all three lines, not the last two:

```python
        prepared = replace(record.prepared, base_ref=sync.base_ref)
        record.base_ref = sync.base_ref
        record.prepared = prepared
```

And further down, at `factory/workgraph/workflow.py:3787-3794`, is the half US1
**does not** copy — the landing path's answer to a conflict, which is to change
whose job it is:

```python
        if sync.clean:
            persona = resolved.node.persona
            rung = "clean-sync recovery"
            conflicted_files = ()
        else:
            persona = DEBUGGER_PERSONA
            rung = "conflicted-sync recovery"
            conflicted_files = sync.conflicted_files
```

**The signal shape to copy.** `factory/workgraph/workflow.py:853` —
`complete_node_externally` buffers a tuple and validates nothing;
`factory/workgraph/workflow.py:2793` — `_pop_external_completion` takes it at the
decision point; `factory/workgraph/workflow.py:2819` —
`_refuse_buffered_external_completions` drains and records the ones that cannot
apply, and is already called on the preparation path at
`factory/workgraph/workflow.py:1762`. What it records through is
`factory/verify/store.py:1882` — `record_external_completion_signal`, an
audit log keyed on a branch and a provenance string; a re-sync request has
neither, so the shape is copied and the sink is not. The CLI half is
`factory/cli/nouns/build.py:1247` — `complete_node_externally_command`, three
lines over `factory/cli/nouns/build.py:1492` — `_send_signal_with_args`, with its
parser declared inside `factory/cli/nouns/build.py:2074` — `add_parser`, beside
the `complete-node-externally` parser at `factory/cli/nouns/build.py:2296`. The
signal name is a module constant at `factory/notify/service.py:115`.

**The offline way to drive the attempt loop is already written — do not invent a
second one, and know what it cannot see.**
`tests/test_external_completion.py:198` — `ConfigurableScript` is a scripted
activity world with per-attempt gate and judge control;
`tests/test_external_completion.py:258` — `ConfigurableScript.activities` is the
registry, returned whole at `tests/test_external_completion.py:437-445`, and it
already carries a `resolve_standards` stub at
`tests/test_external_completion.py:299` that 118 added for exactly this reason,
and a `prepare_worktree` stub at `tests/test_external_completion.py:309`. It
does **not** stub `sync_landing_branch`: US1's tests must add one the same way,
or the workflow will fail on an unregistered activity rather than on the
behaviour under test. **It is missing a second one, and that one is this plan's
neighbour.** 126-US2 (`8d5102e`, 2026-09-02) put
`archive_and_clear_remote_branch` on every terminal non-parked path:
`factory/workgraph/workflow.py:3087` — `_close_out` executes it under
`if state is not _PARKED:` (`factory/workgraph/workflow.py:3137`, the activity
at `factory/workgraph/workflow.py:3143`), and
`factory/workgraph/workflow.py:3594` — `_archive_and_clear_remote_branch` is
called from three more terminal sites. That story extended the interpreter
suite's world instead (`tests/test_interpreter.py:1560-1561`) and left this one
alone — its last commit is `a169063`, 118-US3, 2026-08-29 — so the gap has been
open here since. Diff every `execute_activity` target in
`factory/workgraph/workflow.py` against the registry and seven names come back
unstubbed: `sync_landing_branch`, `archive_and_clear_remote_branch`,
`read_worktree_diff`, `run_judge`, `compare_trees`, `fetch_check_failure` and
`ref_conflict_facts`. The judge pair is unreachable here (below); the last three
sit on the stale-ref and check-failure paths this world never takes;
`archive_and_clear_remote_branch` is the one that is both missing **and**
reached. Every US1 test whose node reaches a terminal state crosses it — T006's
three-attempt control ends through `_run_node`'s
`else: state = NodeState.KILLED` at
`factory/workgraph/workflow.py:2388-2390`, and T004 and T005 settle the epic the
way `tests/test_external_completion.py:705` —
`test_external_completion_fails_when_work_breaks_gates` already does, which is
the existing test that shows the gap. So the subclass appends **two** stubs, and
the second one returns an empty report list
(`factory/activities/agent_activities.py:877` — `archive_and_clear_remote_branch`
returns `list[str]`) even though no assertion in this story touches it — the
workflow does, on the way to every terminal state. Import and
subclass this world rather than copying it —
`tests/test_095_pre_agent_failure.py:42` is the house move, importing the
interpreter suite's Temporal wiring instead of standing up a second one — and
have the subclass append both stubs to `super().activities()`.

Two things that registry does **not** contain decide how FR-005 is proved.
There is no `read_worktree_diff` stub and no `run_judge` stub, and the activity
is unreachable in this world anyway: `factory/workgraph/workflow.py:2625` gates
the diff read on `factory/verify/models.py:977` — `judge_required`, which needs
`factory/verify/models.py:967` — `has_scenarios`, and this world's criteria
factory `tests/test_external_completion.py:456` — `_criteria_for` builds its one
`Requirement` with `scenarios=[]` at `tests/test_external_completion.py:465`.
However the gates are scripted, the judge never runs here, so "every
`read_worktree_diff` call carried the merged head" is an assertion over an empty
set — a green test that proves nothing, on the story's most important control.
The `check_output` stub at `tests/test_external_completion.py:352-354` is
reachable but discards its request, so asserting on its input means overriding
the stub. The clause is proved instead from the base on the **verification
row**: the `record_verification` stub at
`tests/test_external_completion.py:356-367` hands the request to the real store
write, `factory/workgraph/workflow.py:2672` composes that row's `base_ref` from
the same `prepared` local `check_output` is measured with, and the column exists
at `factory/verify/store.py:234`.
`tests/test_external_completion.py:511` — `_verification_row` is the reader to
model the query on, and `tests/test_external_completion.py:521` — `_signal` is
the signal helper to model the new one on.

**The words, and the data they are missing.** The `_CHOICE_EFFECTS` map at
`factory/notify/messages.py:134` holds one sentence per choice; the RETRY entry
is `factory/notify/messages.py:135-138`:

```python
    EscalationChoice.RETRY: (
        "node: one more attempt, on the tree this one left behind. "
        "epic: unchanged — it keeps dispatching."
    ),
```

`factory/notify/messages.py:358` — `render_blast_radius` renders one line per
*offered* choice, through `factory/notify/messages.py:373` — `_effect_line`.
`ergane build status` already prints the pin: `factory/cli/nouns/build.py:504`
composes the node line and `factory/cli/nouns/build.py:524` — `_base_token`
renders `base <sha12> landing head <branch> <sha12>` from the `base_ref` 118-US2
put on `NodeStatus` at `factory/workgraph/workflow.py:890-894`. The per-node
sentence renderer to model FR-010's and FR-015's lines on is
`factory/cli/nouns/build.py:738` — `_attempt_note_lines`: a flattened sentence on
its own line, absent when the node carries no such key, never truncated because
"the half that names the remedy is the half at the end".

## Traps

**Trap 1 — The ledger row names the wrong surviving half, and reading it as the
specification rebuilds 118.** The reopen note lists three asks and marks ask (1),
"re-read standards per attempt from the landing branch", as NOT BUILT. It is
built: `factory/activities/agent_activities.py:1022` — `resolve_standards`,
executed per attempt at `factory/workgraph/workflow.py:1826`, registered at
`factory/worker.py:115`, with a docstring that quotes this very defect. The
surviving asks are (2) the lever and (3) the words. An implementer who starts
from the ledger row will spend a story re-deriving a resolution that already
ships, and the tell will be a diff touching
`factory/activities/agent_activities.py`. Nothing in this spec touches that file.

**Trap 2 — The CLI is not on the worker host, and the tree may have an agent in
it.** `sync_with_target` is a plain synchronous function and it is *right there*;
calling it from the new command is the obvious move and it is wrong twice over.
`target_repo` is a worker-host path — the flag says so at
`factory/cli/nouns/build.py:2115`, "worker-host path to the repository the epic
builds in" — and the worktree lives under the worker's factory root, which the
operator's shell may not share. Worse, an attempt may be in flight with an agent
writing in that tree; merging into it mid-attempt corrupts the very work FR-004
promises to preserve. The lever is a signal the workflow applies between
attempts. FR-001, FR-003.

**Trap 3 — "Just sync every attempt" un-pins the worktree and breaks replay at
the same time.** It is one line shorter than the correct design and it is what an
implementer reaches for when the signal plumbing gets tedious. It contradicts
`factory/workgraph/worktree.py:420-441` — 118 FR-004/R5 decided the tree stays
pinned between attempts, and 002 FR-010 before it — and it also changes the
activity sequence every already-recorded history was written with, which is
precisely why the neighbouring per-attempt read at
`factory/workgraph/workflow.py:1826` sits behind
`workflow.patched("standards-resolved-per-attempt")`. Keep the sync reachable
only from a buffered request: a history carrying no such signal then replays
against an unchanged sequence and needs no patch of its own. FR-003, FR-008, and
US1-S5 is the test that catches the shortcut.

**Trap 4 — Writing the two record fields is the half-fix: the pin the next
attempt is measured from is a local, and it is not one of them.**
`factory/workgraph/workflow.py:3734-3736` is three lines, and the first one —
`prepared = replace(record.prepared, base_ref=sync.base_ref)` — is the one an
implementer copying "move the pin" drops, because the two below it read like the
whole job. On the recovery path that rebinding is why the fix works at all. In
the attempt loop the equivalent local is assigned at
`factory/workgraph/workflow.py:1744` and handed to
`factory/workgraph/workflow.py:2559` — `_verify` at
`factory/workgraph/workflow.py:2076-2080`, where it becomes `check_output`'s
`base_ref` (`factory/workgraph/workflow.py:2614`), the judge's diff base
(`factory/workgraph/workflow.py:2629`) and the verification row's base
(`factory/workgraph/workflow.py:2672`). A diff that writes `record.base_ref` and
`record.prepared` and leaves that local stale satisfies "the pin moved" word for
word while the next attempt's diff still contains every story that landed under
this node: the judge reads other people's code as this node's work and the
deterministic 64 KiB diff bound (D-050) starts refusing for a reason nothing in
the output explains. Move all three. US1-S2 asserts the two
a test can reach: `record.prepared` through the
`factory/workgraph/workflow.py:860` — `epic_status` query, which composes
`NodeStatus.base_ref` from it at `factory/workgraph/workflow.py:890-894`, and
the local through the base on the following attempt's verification row — the one
of the four measurements the scripted world can read back, since the judge's
diff read never happens there (see the section above) and an assertion written
against it would pass over zero calls and hide exactly this half-fix. The third
write, `record.base_ref`, has **no reader at all** outside the landing path's own
pre-sync comparison at `factory/workgraph/workflow.py:3696`: it is proved by
being in the diff, and an implementer who asserts the query's `base_ref` and
stops has proved `record.prepared` twice. FR-005.

**Trap 5 — The operator lever is not the recovery path and must not borrow its
accounting.** The block at `factory/workgraph/workflow.py:3711` escalates on a
refused sync and `factory/workgraph/workflow.py:3716` charges a recovery cycle on
a conflicted one. Copying that block wholesale into the attempt loop turns an
operator courtesy into a spent recovery cycle and an escalation page nobody
asked for — and, since a refusal there `return`s, into a node that stops. In this
story a refusal is *reported and survived*: the node runs its next attempt on the
tree it already has. That is what the spec's title means by "or says it cannot".
FR-006, FR-009.

**Trap 6 — A conflicted sync is not a failure to be retried.** `sync_with_target`
leaves the markers in the tree on purpose
(`factory/workgraph/worktree.py:1334-1336`) — on the landing path a debugger
persona resolves them. Here there is no debugger: the operator asked, the merge
conflicted, and the honest outcome is that the paths are named and the request is
**consumed**. Re-applying the request on the next attempt would re-run a merge
into a tree that already carries markers. Take the request once, following
`factory/workgraph/workflow.py:2793` — `_pop_external_completion`. FR-006.

**Trap 7 — Extend the existing string; a second block breaks the property
079-US1 landed.** `factory/notify/messages.py:358` — `render_blast_radius`
renders one line per *offered* choice, "for the reason 079-US1 landed: what an
escalation offers is computed per node, and a block rendered from the vocabulary
would describe a retry button that is not on the keyboard". A paragraph appended
to the message body says the tree is pinned on escalations that offer no RETRY at
all, which is a claim about a button that is not there. The comment above the
`_CHOICE_EFFECTS` map at `factory/notify/messages.py:134` also names the test
that reads these sentences back, `tests/test_pause_is_not_a_kill.py`; a second block
is invisible to it. Edit the RETRY entry in place. US2-S4 is the control.
FR-011, FR-014.

**Trap 8 — The status data is already there; the gap is words — and the
obvious words are false.** The tempting sentence is "the tree was branched at
dispatch and has not moved since", and it is wrong in a state the factory
reaches on its own. `_CHOICE_EFFECTS` is keyed by choice, not by escalation
site, so `factory/workgraph/workflow.py:4178` — `_escalate_landing` renders the
RETRY line too whenever `factory/verify/ladder.py:116` — `offered_choices`
grants it at `factory/workgraph/workflow.py:4220` — and the landing-recovery
path has already moved the pin three lines at a time at
`factory/workgraph/workflow.py:3734-3736`. A node rejected by the queue,
recovery-synced and then escalated would read that its tree cannot have taken
the operator's correction when it already merged it: the same misinformation
this spec exists to end, told backwards. Name both movers — a landing recovery,
and `ergane build resync` — in the message (FR-011) and in the status sentence
(FR-015), and let US2-S1 and US2-S5 assert the qualified wording rather than the
flat claim. The rest of trap 8 is unchanged: 118-US2 put the
prepared worktree's base on `NodeStatus`
(`factory/workgraph/workflow.py:890-894`) and
`factory/cli/nouns/build.py:524` — `_base_token` renders it beside the landing
head. Do not re-derive the base, do not reformat that token, do not print a
second one, and above all do not compute "is this pin stale?" in the CLI — that
comparison is `factory/workgraph/worktree.py:362` — `ensure`'s, it needs a fetch,
and a renderer that fetches is a renderer that hangs. US2-S5 asserts the existing
token is unchanged character for character. The re-sync outcome US1 adds is a
sentence line of its own, modelled on
`factory/cli/nouns/build.py:738` — `_attempt_note_lines`, and US1-S8 is what
keeps the two non-clean shapes of it from being quietly skipped. FR-010, FR-015.

**Trap 9 — A re-sync is not a fifth button.** `factory/verify/models.py:141` —
`EscalationChoice` is exactly RETRY / KILL / PAUSE_EPIC / KILL_EPIC; its values
ride inside `callback_data` as `esc:<12-hex>:<choice>`, which Telegram bounds at
64 bytes, and the ladder's `_ends_the_node`, the keyboard, the callback decoder
and `_CHOICE_EFFECTS` are all 1:1 with the enum. Adding a member to get a button
changes four surfaces and a wire format to deliver a verb. The lever is
`ergane build resync`. FR-001.

**Trap 10 — A conflicted re-sync is the expensive outcome, and "paths recorded,
node keeps running" reads as if it were cheap.** `sync_with_target` leaves the
conflict markers and an unmerged index in the tree deliberately
(`factory/workgraph/worktree.py:1334-1336`), and the landing path answers that
state by changing whose job it is: `factory/workgraph/workflow.py:3787-3794`
routes a conflicted sync to `DEBUGGER_PERSONA`. This story has no debugger,
aborts nothing, and may write no second git helper (FR-004) — so every remaining
rung of the ladder runs its gates against a tree containing `<<<<<<<` and burns
an attempt each time. That is the *same* waste the finding measured, recreated by
its own fix, and the tempting diff — record the file list, move on, print the
paths — is the one that hides it: the operator reads a courtesy and waits again.
FR-006 and FR-010 make the consequence part of the outcome, in the record and in
`ergane build status`: the markers are still there, and the node's remaining
attempts will run against them until a human resolves the tree or ends the node.
The tree is at `factory/workgraph/worktree.py:289` — `worktree_path`, i.e.
`<factory root>/worktrees/<epic id>/<node id>` on the worker host; resolving it
is the operator's move and this spec does not make it for them. US1-S3 and
US1-S8 are the tests, and operator steps 4 and 7 are the falsification.

**Trap 11 — "end the epic and the roadmap rebuilds it" is the one sentence in
US2 the factory itself falsifies.** It is the obvious phrasing for FR-013's
second recovery and it is wrong on both of the paths an epic can be started on.
A roadmap child that completes with a FAILED or KILLED node is not landed but is
still *concluded*: `factory/roadmap/workflow.py:1416` — `_landed_status_for`
returns `landed=False` for it, the run records it in `_landed`, and
`factory/roadmap/workflow.py:864-871` excludes every spec in that map from
`dispatchable` — so the run that dispatched this epic will not dispatch the spec
again, and `factory/roadmap/workflow.py:302` — `RoadmapCarryOver` carries the
map across continue-as-new so a restart does not clear it either
(`factory/roadmap/workflow.py:816`). An epic started by hand with
`ergane build start` has no roadmap owner at all. This is the same error trap 8
catches on the other half of the same sentence: a line that renders wherever
RETRY is offered must be true wherever RETRY is offered, and an operator who
ends the epic on the strength of a promised rebuild waits for a dispatch that
never comes — the finding's own measured failure, recreated by its fix. Say the
restart is the operator's move for a hand-started epic and a later roadmap run's
for a spec the roadmap owns. FR-013, US2-S3, T019 and T022; T019 is the test
that catches the flat claim.

## Sizing

US1 touches `factory/workgraph/workflow.py` (one signal handler, one buffer, one
application point in the attempt loop, one field on `NodeStatus`),
`factory/cli/nouns/build.py` (the command, its parser entry, and the outcome
line), and `factory/notify/service.py` (the signal-name constant). Its tests live
in one new module that **imports and subclasses**
`tests/test_external_completion.py:198` — `ConfigurableScript` rather than
copying it: the harness above
`tests/test_external_completion.py:521` — `_signal` measures 19,628 bytes, and a
copy would put US1 within a few kilobytes of the refusal on its own — plus a CLI
refusal test and one renderer
test for the two non-clean status shapes.

US2 touches `factory/notify/messages.py` (one dictionary entry) and
`factory/cli/nouns/build.py` (one sentence beside the base token). Its tests are
renderer tests: no workflow, no Temporal environment.

The two stories share exactly one production file,
`factory/cli/nouns/build.py`, in different functions — which is why the Work
Graph declares the merge edge rather than leaving it to be inferred. Every other
production file is owned by one story: `factory/workgraph/workflow.py` and
`factory/notify/service.py` by US1, `factory/notify/messages.py` by US2.

Both stories sit inside the 64 KiB deterministic diff bound (D-050) on the
imported-world reading, and only on it. US1 is under one hundred and fifty
production lines plus one test module of roughly 30-40 KB; US2 is under thirty
plus two renderer tests. The pasted evidence each verification task asks for is
short command output, not a transcript. The margin is real but not generous:
the ledger carries a measured instance of a comparably shaped first story
refused at 73,973 bytes of which roughly 58% was test code, and 118-US3
(`a169063`) measured 59,174 bytes — 90% of the refusal. Read that story's
split before sizing this one, because the pasted evidence is part of it:
`git show --format='' a169063 -- attempt-report.md | wc -c` is 15,361 bytes
against 25,239 of tests and 18,574 of `factory/`. A fifth of a landed story
this shape is its attempt report, and D-050 counts it. US1's nine tests at the
house rate, its production lines and a report of that size land in the
mid-fifty-thousands: inside the bound, and not comfortably — which is why T016
asks for three status blocks and a three-line log rather than a transcript.
If US1's diff approaches the bound, drop in this order, and say so in the attempt report
rather than compressing the assertions: first the CLI refusal test (T008, whose
subject is one seam already covered by every other signal verb), then the
renderer test (T009a) — both are separable modules with no dependency on the
scripted world. The controls (T006, T009) and the pin test (T003) are the last
things to go, because they are the story.

## Verification the operator will run, independent of the gate

Per Constitution VIII and D-037 the judge sees the diff and the criteria only, so
every runtime reading below is committed as pasted output.

**Before step 1, once US1 lands: `systemctl --user restart ergane-worker.service`,
then confirm the new signal constant imports.** T010 adds a name to
`factory/notify/service.py`, which `factory/workgraph/workflow.py:169` imports
inside `workflow.unsafe.imports_passed_through()`. The open critical finding
`interpreter/a-landed-activity-type-blocks-every-new-epic-until-the-worker-restarts`
records the consequence — any story adding a name to such a module blocks every
subsequent epic until the worker is restarted, its occurrence 2 being 118-US2
landing `UNKNOWN_BASE_REF` — and the symptom is an `ImportError` naming a file
that is correct on disk. Step 1 is exactly the dispatch that would die on it.
This spec neither fixes that finding nor declares it.

Beyond that, on a scratch target repository:

1. Start an epic and let its first attempt fail. Run `ergane build status
   <epic>` and record the node's `base <sha12> landing head <branch> <sha12>`
   line. The two shas should already differ once something else has landed.
2. Land a commit on the landing branch. Run
   `ergane build resync <epic> <node>`, then re-read status. The pin must have
   moved to the landing head, and `git -C <worktree> log --oneline -3` must show
   a merge commit with the node's own commits still reachable beneath it. Then
   read the next attempt's verification row: its base must be the merged-in
   head, not the pre-sync one. A pin that moved on the status line while the
   verification row still carries the old base is trap 4 in the wild.
3. Run `ergane build resync` against an epic id that is not running. It must
   exit non-zero with `no epic '<id>' is running here` — the same refusal
   `ergane build pause` gives, from the same seam.
4. Make it conflict on purpose: land a commit touching the same lines the node
   edited, then re-sync. Status must name the conflicted paths **and say the tree
   still carries unresolved markers its remaining attempts will run against**,
   the node must still be running its ladder, and `git -C <worktree> reflog` must
   show no reset and no rebase. This is the falsifiable test of FR-004 — the
   whole argument for a merge rather than a rebase is that the operator's lever
   cannot destroy an agent's work — and of FR-006's second clause, which is the
   only thing standing between a conflicted tree and three more burnt attempts.
5. Remove the worktree directory by hand and re-sync. The refusal and its reason
   must appear on the status line, no escalation may arrive on the operator
   channel, and the node's attempt number must be unchanged when the next
   attempt runs.
6. Trigger an escalation that offers RETRY and read the blast-radius block: the
   RETRY line must name the pin, the standards channel and both recoveries. Then
   read a block for a choice set without RETRY and confirm none of that text is
   present.
7. Finish step 4 the way the status line says to: on the worker host, resolve the
   conflict in
   `<factory root>/worktrees/<epic id>/<node id>`
   (`factory/workgraph/worktree.py:289` — `worktree_path`) and commit it, then let
   the ladder run one more rung and confirm its gates go green again. Nothing in
   this spec does that for the operator, which is exactly why step 4 requires the
   status line to say so.

Steps 4, 5 and 7 together are what the title claims: the lever either does the
thing, or says why it did not and what it left behind, and neither answer costs
the operator an attempt they did not know they were spending.
