# Implementation Plan: a killed node says why it died

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing. 126's own anchors rotted in nine hours
because its own stories moved the lines it cited, and this spec edits three of the
same files.

## What already exists, and where

**The cause is computed correctly and the computation is not the problem.**
`_failure_detail` (`factory/workgraph/workflow.py:509` — `_failure_detail`) walks
an exception's cause chain to the frame carrying the real reason, bounded by the
constant documented at `factory/workgraph/workflow.py:503`. It has **three** call
sites at HEAD — `factory/workgraph/workflow.py:1657` (100's, in the reaper),
`factory/workgraph/workflow.py:3252` (126's, on the push refusal) and
`factory/workgraph/workflow.py:3484` (the landing poller). The one that matters
here is `:3252`; the *store* is the line after it,
`factory/workgraph/workflow.py:3253` (`record.terminal_reason = detail`), which is
the line the finding's own row cites and the one every sentence about "where git's
diagnosis is kept" means. Both sit under a docstring line at
`factory/workgraph/workflow.py:3239` that states the contract this spec restores:
`terminal_reason` carries git's reason, it is what `ergane build status` prints,
and a node that later merges "keeps that line, and should".

**The method the finding names does not exist under that name.** The ledger row
and the memory note both call it `_handle_push_refusal`. In the tree it is
`_escalate_ref_conflict` (`factory/workgraph/workflow.py:3216` —
`_escalate_ref_conflict`), renamed by 126-US3. Grepping the finding's own words
finds nothing.

**The two overwrite sites are three lines each and identical.**

```python
            if report:
                record.terminal_reason = "; ".join(report)
```

at `factory/workgraph/workflow.py:3151-3152` inside `_close_out`
(`factory/workgraph/workflow.py:3087` — `_close_out`), and at
`factory/workgraph/workflow.py:3612-3613` inside
`_archive_and_clear_remote_branch` (`factory/workgraph/workflow.py:3594` —
`_archive_and_clear_remote_branch`). The report is the return of the
`archive_and_clear_remote_branch` activity.

**The field to add has a precedent in the same dataclass, and a second home in
the query answer.** `NodeRecord` is at `factory/workgraph/models.py:324` —
`NodeRecord`. `terminal_reason` is declared at `factory/workgraph/models.py:387`
with a docstring at `factory/workgraph/models.py:383-386`. Nine lines below it,
`attempt_note` (`factory/workgraph/models.py:398`) carries a docstring at
`factory/workgraph/models.py:390-397` whose entire job is to explain why it is
*distinct* from `terminal_reason` — "Distinct from `terminal_reason`, which
answers why a node *ended*". **Copy that shape.** Then copy it once more into the
query answer: `NodeStatus` (`factory/workgraph/workflow.py:599` — `NodeStatus`)
declares its own `terminal_reason` at `factory/workgraph/workflow.py:641` and is
populated from the record at `factory/workgraph/workflow.py:882`. Both halves are
FR-001; a field that stops at `NodeRecord` reaches no renderer at all.

**`ergane status` has no node renderer, and must not grow one.** `_epic_lines`
(`factory/cli/status.py:788` — `_epic_lines`) imports `render_status` from
`factory.cli.nouns.build` at `factory/cli/status.py:796` and calls it at
`factory/cli/status.py:805`, under a comment at `factory/cli/status.py:794-795`
that says why:

```python
    # The per-epic table is `build status`'s renderer, reused rather than
    # re-formatted, so the two verbs cannot drift into two shapes.
```

So `grep -c terminal_reason factory/cli/status.py` returning **0** is a fact about
*delegation*, not about blindness: the cause is already printed on that surface.
US2's work is one token in the shared renderer, which `ergane status` then
inherits for free.

**The renderer to extend is `render_status`** (`factory/cli/nouns/build.py:464` —
`render_status`). Its node line is assembled at
`factory/cli/nouns/build.py:501-506` and already ends with `_reason_token`
(`factory/cli/nouns/build.py:718` — `_reason_token`), which flattens whitespace
for a documented reason (`factory/cli/nouns/build.py:728-730`). The shape to copy
for the housekeeping token is `_attempt_note_lines`
(`factory/cli/nouns/build.py:738` — `_attempt_note_lines`), the sibling that
already renders a second record field beside the same line.

**The two sources US3 must join.** `attempts_command`
(`factory/cli/nouns/build.py:1284` — `attempts_command`) reads the verification
store with no Temporal client, and its docstring at
`factory/cli/nouns/build.py:1287-1290` says why: "the moment an operator asks what
a verdict rested on is usually the moment the execution has aged out of Temporal".
`node_history` (`factory/verify/store.py:873` — `node_history`) is the per-node
query. The *ending* is not there: `terminal_reason` exists in
`factory/workgraph/models.py`, `factory/workgraph/workflow.py` and
`factory/cli/nouns/build.py` and nowhere under `factory/verify/`, so it reaches a
reader only through `_query_status` (`factory/cli/nouns/build.py:1119` —
`_query_status`), whose `epic_status` query is at
`factory/cli/nouns/build.py:1125` and whose not-found refusal — the shape FR-010
asks US5 to split in two — is at `factory/cli/nouns/build.py:1135-1138`. The
landing's queue outcomes ride the same query: `NodeStatus.landing_history` at
`factory/workgraph/workflow.py:622` and `rejection_cause` at
`factory/workgraph/workflow.py:638`. The transcript directory is composed by
`transcript_dir` (`factory/workgraph/adapter.py:771` — `transcript_dir`).

**The escalation pair US4 reuses is built, wired, and plumbed end to end — for a
different dial.** `ExhaustedBound` (`factory/verify/ladder.py:244` —
`ExhaustedBound`) holds `dial`, `value` and `note` and renders itself at
`factory/verify/ladder.py:265-267`. `_bound_sentence`
(`factory/workgraph/workflow.py:4351` — `_bound_sentence`) is the whole of the
rendering on the workflow side. `EscalationRequest`
(`factory/escalation/workflow.py:128` — `EscalationRequest`) already declares
`exhausted_bound` at `factory/escalation/workflow.py:162`, carries it to the
activity at `factory/escalation/workflow.py:336`, into the record at
`factory/activities/notify_activities.py:538`, and prints it at
`factory/notify/messages.py:450`. The verification path fills it at
`factory/workgraph/workflow.py:2160`. `_escalate_landing`
(`factory/workgraph/workflow.py:4178` — `_escalate_landing`) builds its request at
`factory/workgraph/workflow.py:4215-4223` — `epic_id`, `node_id`,
`history_summary`, `choices`, `timeout_s`, `check_evidence` — and no
`exhausted_bound`. Its three callers are
`factory/workgraph/workflow.py:3817` (the recovery cycle failed again),
`factory/workgraph/workflow.py:3866` (inside `_escalate_and_apply`, the route the
exhaustion checks at `factory/workgraph/workflow.py:3685` and
`factory/workgraph/workflow.py:3723` take) and
`factory/workgraph/workflow.py:4079` (the futile re-enqueue, which is not an
exhaustion). What the operator gets today is the spent count and nothing else:
`render_landing_history` (`factory/notify/messages.py:288` —
`render_landing_history`) appends `Recovery cycles: N` at
`factory/notify/messages.py:308-309`, and `max_recovery_cycles`
(`factory/mergequeue/models.py:393`) appears **0** times under `factory/notify/`
and `factory/escalation/`.

## Traps

**Trap 1 — There are TWO overwrite sites, and the finding names only one.** The
`ergane-web` document and the ledger row both cite `_close_out`. The push-refusal
KILL path does not go through `_close_out` at all:
`factory/workgraph/workflow.py:3329-3330`, inside `_escalate_ref_conflict`, calls
`_remove_worktree` and then `_archive_and_clear_remote_branch` directly, so it
reaches the overwrite at `factory/workgraph/workflow.py:3613` and never the one at
`factory/workgraph/workflow.py:3152`. **A fix applied only to `_close_out` leaves
the exact case that cost four hours still broken, and every test written from the
finding's own text will pass.** US1-S4 is the control. FR-002.

**Trap 2 — THE SUITE IS STRUCTURALLY BLIND TO THIS DEFECT.** In
`tests/test_interpreter.py:1560-1565` the `archive_and_clear_remote_branch`
activity is stubbed:

```python
        @activity.defn(name="archive_and_clear_remote_branch")
        async def archive_and_clear_remote_branch(
            request: ArchiveAndClearRemoteBranchInput,
        ) -> list[str]:
            script._log("archive_and_clear_remote_branch", request.node_id)
            return []
```

It returns `[]`. So `if report:` is **never true** anywhere in the interpreter
suite, and no test in it has ever executed either overwrite. FR-005 requires at
least one test that drives a non-empty report through the interpreter; without it,
US1 can be "verified" by a suite that cannot reach the code it changes. The wrong
move is to write the new tests only against the real-git file, where a passing
suite proves nothing about the interpreter path US1 also edits.

**Trap 3 — A COMMITTED TEST PINS THE DEFECT AS INTENDED BEHAVIOUR.**
`tests/test_126_us2_kill_archives_remote.py:260-262` asserts:

```python
    assert status.nodes[NODE].terminal_reason is not None
    assert BRANCH in status.nodes[NODE].terminal_reason
    assert pushed[:12] in status.nodes[NODE].terminal_reason
```

and `tests/test_126_us2_kill_archives_remote.py:285-286` asserts `"origin" in …
terminal_reason`. **These assertions are the defect, written down and made
green.** A correct fix MUST repoint them at the new field. If they are still green
and unedited at the end of US1, the fix did not land — and because they are a
*passing* test, nothing will say so.

Beside them sits a comment that is **not** wrong and must not be "corrected" into
being wrong. `tests/test_126_us2_kill_archives_remote.py:318-319` reads:

```python
    # A true no-op second run returns an empty report; the workflow records
    # that as no terminal_reason, which is the right shape for idempotency.
```

That sentence is about the EMPTY-report path — row two of the spec's truth table,
which US1-S2 and trap 4 both require to stay byte-unchanged — so it is **still
true after this fix**. The draft of this plan said it "becomes false"; it does
not, and an implementer who sets out to falsify it has exactly one way to succeed:
change the empty-report path, which US1-S2 forbids. What FR-005 wants is the
opposite move — EXTEND that comment in the same edit to name the new field's value
in the same case, so the file states what both fields do rather than only one.
FR-005.

**Trap 4 — The empty-report case is the one that must not regress.** Both sites
are guarded by `if report:`. A node with nothing to tidy has always kept its
cause, and that is most nodes — row two of the spec's truth table. US1-S2 pins it.
A refactor that unconditionally writes the new field is fine; one that
unconditionally clears `terminal_reason` is a wider outage than the defect.
FR-003.

**Trap 5 — `ergane status` ALREADY PRINTS THE CAUSE, AND ADDING A RENDERER TO IT
IS THE WRONG MOVE.** This trap replaces the draft's, which had it backwards.
`grep -c terminal_reason factory/cli/status.py` is `0` because `_epic_lines`
(`factory/cli/status.py:788` — `_epic_lines`) imports `render_status` at
`factory/cli/status.py:796` and reuses it, under a comment at
`factory/cli/status.py:794-795` saying the two verbs must not drift into two
shapes. An implementer who reads the zero as "this surface is blind" will add a
second node renderer inside `factory/cli/status.py` — the precise thing that
comment exists to prevent, and the precise thing FR-006 forbids. The token goes in
`factory/cli/nouns/build.py` and `ergane status` inherits it. US2-S2 is the
control: it compares the two verbs' node lines for one document and fails if they
diverge.

**Trap 6 — Add a sibling token; do not write a second flattener.**
`_reason_token` (`factory/cli/nouns/build.py:718` — `_reason_token`) already
flattens whitespace for a documented reason
(`factory/cli/nouns/build.py:728-730`), and `_attempt_note_lines`
(`factory/cli/nouns/build.py:738` — `_attempt_note_lines`) is the sibling that
shows how a second record field is rendered beside the same line. Two renderers
that can disagree about how a multi-line git error becomes one status line is a
smaller version of the defect this spec is fixing. FR-008.

**Trap 7 — `exhausted_bound` CANNOT NAME THE LANDING DIAL, AND CALLING IT ON THIS
PATH IS THE WRONG MOVE.** This is the correction that matters most in US4.
`exhausted_bound` (`factory/verify/ladder.py:270` — `exhausted_bound`) takes a
`VerificationConfig` and can only ever return one of four dials —
`max_pre_agent_failures` (`factory/verify/ladder.py:313`), `debugger_cycles`
(`factory/verify/ladder.py:325`), `max_judge_retries`
(`factory/verify/ladder.py:336`) or `max_attempts`. It opens by asking
`next_action` (`factory/verify/ladder.py:305`) and returns `None` unless that says
`ESCALATE` — which, on a node that PASSED verification and is now landing, it does
not. So an implementer who follows "reuse the pair the verification escalation
uses" literally gets `None` on every landing escalation, and a test written the
same way passes because `None` is also the correct answer for the
cycle-remaining branch. **The bound is `max_recovery_cycles`
(`factory/mergequeue/models.py:393`), a `LandingConfig` dial.** Build an
`ExhaustedBound` (`factory/verify/ladder.py:244` — `ExhaustedBound`) for it,
render it with `_bound_sentence` (`factory/workgraph/workflow.py:4351` —
`_bound_sentence`), and pass it on `EscalationRequest.exhausted_bound`
(`factory/escalation/workflow.py:162`), which is already plumbed to the printer at
`factory/notify/messages.py:450`. FR-011.

**Trap 8 — Compute the bound where the exhaustion is decided, not inside
`_escalate_landing`.** 095's architecture is that the caller answers, because only
the caller holds the history and the config — see the comment at
`factory/workgraph/workflow.py:2153-2159`. The two landing callers already compute
the same predicate for `retry_grants_work`:
`factory/workgraph/workflow.py:3825-3827` and
`factory/workgraph/workflow.py:3862-3865`. The third caller,
`factory/workgraph/workflow.py:4079`, is the futile re-enqueue and passes
`retry_grants_work=True` unconditionally — it is not an exhaustion and must name
no bound. Deriving the answer a second time inside `_escalate_landing` would give
the futile page a bound it did not earn. FR-011, FR-012.

**Trap 9 — Do NOT re-word `ExhaustedBound.describe`.** It renders
`ladder exhausted: {dial} = {value} — {note}` at
`factory/verify/ladder.py:265-267` and the verification path prints exactly that
string. The prefix reads oddly beside a landing dial and the tempting move is to
generalise it; doing so changes the verification message and fails US4-S3, which
is byte-identical-to-today. Carry the landing wording in `note`, which is what
`note` is for. FR-012.

**Trap 10 — `build why` HAS TWO SOURCES, AND THE ENDING IS NOT IN THE STORE.**
The draft said "from the stores only", and `terminal_reason` is in no store:
`grep -rn terminal_reason factory/verify/` returns nothing. It reaches a reader
only through the `epic_status` query (`factory/cli/nouns/build.py:1125`), which
needs a live execution. An implementer who honours "stores only" ships a `why`
verb missing the one datum this spec exists for; one who dials Temporal for
everything ships a verb that is unavailable exactly when it is wanted, which is
the trade `attempts_command`'s docstring
(`factory/cli/nouns/build.py:1287-1290`) already refused. The answer is both: the
store half always, the ending when the query answers, and — in US5 — a named
absence when it does not. **US3 joins both sources; that part is not deferrable
and is not what the split moved.** FR-009.

**And the two absences arrive as the same absence — which is US5's whole story.**
An epic id nothing is running under (US5-S1) and an epic whose execution has aged
out (US5-S2) BOTH reach the verb as `RPCStatusCode.NOT_FOUND` on the `epic_status`
query, which `factory/cli/nouns/build.py:1135-1138` collapses into one refusal
today. The only fact that separates them is whether the verification store holds
rows for that epic, so read `epic_history` (`factory/verify/store.py:899` —
`epic_history`) — whose own docstring at `factory/verify/store.py:902-905` says it
"exists for the moment both are gone", meaning the graph and Temporal. **No rows:
refuse (US5-S1). Rows: degrade (US5-S2).** An implementer who branches on the
status code alone can build only one of the two, and whichever one he writes first
will look correct in its own test. FR-010.

**Trap 11 — Print the transcript path; do not read it.** FR-009 asks for the
transcript directory because "reachable only by knowing
`<root>/transcripts/<epic>/<node>/attempt-N/`" is one of the four invisibles the
causal-chain finding was filed on. Compose it with `transcript_dir`
(`factory/workgraph/adapter.py:771` — `transcript_dir`); do not open it, list it
or tail it. A verb that walks the filesystem on the operator's behalf has moved
the work, not removed it — and the walk is what the finding is about.

`transcript_dir` takes `factory_root` as its **first argument**, and this module
already resolves it exactly once, correctly: `resolve_env_path(ERGANE_ROOT_ENV,
FACTORY_ROOT_ENV, DEFAULT_FACTORY_ROOT_PATH)` at
`factory/cli/nouns/build.py:1888-1890`. Reuse that call. A bare relative default —
`Path(".factory")` or the like — prints a path that is right only from the
worker's cwd, which is the live open defect draft spec 129 exists for
(`workgraph/a-relative-runtime-root-…`, `operator/the-verification-store-path-is-
cwd-relative-…`). The printed path IS this clause of FR-009; a wrong one is worse
than none, because the operator will `cd` to it. FR-009.

**Trap 12 — `_verification_store_path` is defined TWICE in the file US3 edits.**
`factory/cli/nouns/build.py:1484` and `factory/cli/nouns/build.py:1534` are
byte-identical definitions; the second shadows the first. Call the module-level
name, add no third copy, and do not "tidy" the duplicate inside this story — that
is an unrelated edit in a file three stories are already contending over.

**Trap 13 — RELEASE-LAG TRAP: do not judge this spec against the 0.5.0 wheel.**
`_failure_detail` has **one** call site in
`git show v0.5.0:factory/workgraph/workflow.py` (its line 3042, the landing
poller) and **three** at HEAD; the two sites this spec depends on — 100's at
`factory/workgraph/workflow.py:1657` and 126's at
`factory/workgraph/workflow.py:3252` — do not exist in the wheel at all. (The
draft said three and seven; that was `grep -c` counting prose mentions, and it is
corrected here.) The `ergane-web` document that motivated this spec re-measured
everything against the installed 0.5.0 wheel, so several of its status lines are
true of the wheel and false of this branch. Read the tree.

**Trap 14 — US2 must not alter non-terminal output.** FR-007 scopes the new token
to a node that has a housekeeping report. US2-S4 is the control that an ordinary
running epic renders byte-identically, because `ergane status` is the verb an
operator watches continuously and a diff in its steady-state output is a change to
the thing everyone reads.

**Trap 15 — THE GATE TAIL IS HALF THIS STORY'S DIFF BOUND, AND US3 SPENDS IT
TWICE.** `GateResult.output_tail` (`factory/verify/models.py:362` — `GateResult`)
is documented at `factory/verify/models.py:367-368` as "the last ≤32 KiB of
combined stdout+stderr", and the store persists it whole
(`factory/verify/store.py:1098`). US3 both PRINTS that field (FR-009) and PASTES a
real run of the verb as committed evidence (T022), against
`DIFF_INPUT_LIMIT = 64 * 1024` (`factory/verify/diffbounds.py:47`, D-050). Print it
raw and one noisy gate makes the verb unreadable; paste it raw and the story is
refused for diff size before anyone judges the work — which is what US3 was split
for. Use the clipper at `factory/notify/messages.py:641` — `_tail` — which keeps
the last `EVIDENCE_TAIL_LINES` lines (`factory/notify/messages.py:79` — 20) and
names what it dropped, the same clipping the escalation pages already do. Then
trim the pasted run in T022 to the lines that carry the answer.

**Read the import line before you assume the dependency is already there.**
`factory/cli/nouns/build.py:94` imports from `factory.notify.service`, NOT from
`factory.notify.messages` — the package is already a dependency of this module,
the module is not. And the clipper is a private name: every production importer of
`factory.notify.messages` today takes public names only
(`factory/activities/notify_activities.py:74`, `factory/notify/service.py:74`,
`factory/workgraph/workflow.py:216`, `factory/roadmap/workflow.py:89`), and the
only precedent for importing a private one is a test. So an implementer told
merely to "reuse `_tail`" meets a cross-module private import with no precedent,
balks, and writes a second clipper — the duplication trap 6 argues against for the
reason token, reappearing here. **FR-009 settles it: promote the clipper to a
public name in `factory/notify/messages.py`, behaviour and bound unchanged, and
import that.** It has four call sites inside that module
(`factory/notify/messages.py:539`, `factory/notify/messages.py:547`,
`factory/notify/messages.py:571` and `factory/notify/messages.py:576`), so the
rename is five lines and no behaviour. US4 does not edit that file, so this does
not disturb the `concurrent_with` waiver. FR-009.

**Trap 16 — US3 MUST STOP AT THE PRESENT EXECUTION, AND US5 MUST REPLACE ITS
REFUSAL RATHER THAN SIT BESIDE IT.** These two are one verb cut in half for size,
which makes each one's boundary a hazard the other pays for. US3's implementer
will be tempted to "finish the job" and build the `epic_history` discriminator
while already inside the command function — that puts back exactly the bytes the
split removed, and the refusal for going over is unjudged and unretryable
(`DIFF_REFUSAL_THRESHOLD`, `factory/verify/diffbounds.py:66`). US3 refuses on
`NOT_FOUND` in the shape `factory/cli/nouns/build.py:1135-1138` already refuses
in, and stops. US5's implementer then faces the mirror temptation: adding a second
absence path beside the one US3 shipped, leaving two refusals whose messages can
drift. US5 REPLACES that branch. FR-009, FR-010.

## Sizing

**US1** — `factory/workgraph/models.py` (one field plus its docstring),
`factory/workgraph/workflow.py` (the `NodeStatus` field, its population at
`factory/workgraph/workflow.py:882`, and the two three-line assignment edits),
`tests/test_interpreter.py` (the stub), `tests/test_126_us2_kill_archives_remote.py`
(the repointed assertions and the stale comment), one new test module. Most of the
story is test work, because two of the three test changes are corrections to
assertions that currently encode the defect.

**US2** — `factory/cli/nouns/build.py` only: one token function beside
`_reason_token` and one interpolation in the line assembled at
`factory/cli/nouns/build.py:501-506`. Plus one new test module covering both verbs.
No new data, no new store access, and no edit to `factory/cli/status.py` at all.

**US3** — `factory/cli/nouns/build.py` (a parser registration beside
`factory/cli/nouns/build.py:2280`, a command function and a renderer),
`factory/notify/messages.py` (the five-line rename that makes the clipper public,
trap 15), and one new test module needing both a store fixture and an
`epic_status` query fake. Three scenarios and ONE pasted run, trimmed. **This
story is the one the size bound is about.** The measured analogue is 092-US3
(`03451a9`), which added `ergane build attempts` — a read-only CLI verb over the
same store, three scenarios, one source — at 60,162 bytes against a 65,536-byte
refusal threshold (`DIFF_REFUSAL_THRESHOLD`, `factory/verify/diffbounds.py:66`).
US3 as first drafted carried five scenarios, the two-source join, the
`NOT_FOUND` discriminator and two pasted runs, and was measured over that bound;
US5 is the half that was cut out. Do not put it back (trap 16), and do not paste
an unclipped gate tail: `output_tail` alone is up to 32 KiB
(`factory/verify/models.py:362` — `GateResult`), half the bound.

**US4** — `factory/workgraph/workflow.py` only: one parameter on
`_escalate_landing`, one field on the request it builds at
`factory/workgraph/workflow.py:4215-4223`, and the bound computed at the two
exhaustion callers. Plus the control test that the verification path is unchanged.

**US5** — `factory/cli/nouns/build.py` only: the refusal branch US3 shipped,
replaced by the two-way read of `epic_history` (`factory/verify/store.py:899` —
`epic_history`), plus one new test module with a two-branch store fixture. Two
scenarios and one pasted refusal. It is the smallest story after US4.

US1 and US4 both edit `factory/workgraph/workflow.py`; US2, US3 and US5 all edit
`factory/cli/nouns/build.py`. Those two contentions are why the graph declares the
edges it does rather than running five stories at once. **US1 shares no production
file with US3 or US5, and US4 shares no production file with US2, US3 or US5** —
US4 and US3 both cite `factory/notify/messages.py`, but only US3 edits it, which is
what the `concurrent_with` waiver records. No pair among US2, US3 and US5 can run
first together, because each needs the one before it.

## Verification the operator will run, independent of the gate

Per constitution VIII and D-037 the judge sees the diff and the criteria only, so
runtime evidence must be committed as pasted output. Beyond that:

1. On a scratch clone, arrange a node whose push will be refused non-fast-forward
   and let it die — the exact sequence 126's plan documents.
2. Read `ergane build status` and `ergane status` for that epic. Both must name
   git's refusal as the cause and the archive report as a separate token, and the
   two verbs' node lines must agree character for character.
3. Run `ergane build why <epic> <node>` and confirm the chain it prints matches
   what a `journalctl` read would have told you — then confirm you did not need
   the journal.
4. Run `ergane build why` against an epic id nothing is running under, and again
   against an epic whose execution has aged out, and read both answers: the first
   is a refusal naming the store it read, the second is half a chain and a named
   absence. Before US5 lands both are the same refusal, which is the state US5
   exists to end.
5. Compose a landing escalation with the recovery cycles spent and read the
   message: it must name `max_recovery_cycles` and its value, not only the count
   of cycles spent.

Step 2 is the falsifiable test of the whole spec: it is the surface that read
`Activity task failed` for every death in the `ergane-web` run.
