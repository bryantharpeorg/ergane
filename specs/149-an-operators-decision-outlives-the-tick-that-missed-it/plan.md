# Implementation Plan: an operator's decision outlives the tick that missed it

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## What already exists, and where

**The two verbs are four lines and twenty, and neither looks at what owns
dispatch.** `factory/cli/roadmap.py:397` — `roadmap_promote_command` in full,
followed by the head of `factory/cli/roadmap.py:403` — `roadmap_unpark_command`:

```python
async def roadmap_promote_command(args: argparse.Namespace) -> int:
    handle = await _get_handle(args)
    await handle.signal("promote_spec", args.spec)
    return EXIT_OK
```

`factory/cli/roadmap.py:328` — `_get_handle` is `_locate` plus
`factory/cli/roadmap.py:334` — `_handle_for`, and `_handle_for` refuses on
exactly one condition — `factory/cli/roadmap.py:336` — `_handle_for`, that no run
id was resolved at all. Neither resolver filters on execution status:
`factory/roadmap/discovery.py:443` — `_newest_run` sends only a
`WorkflowId STARTS_WITH` predicate, and `factory/roadmap/discovery.py:364` —
`_find_bare_workflow` accepts any id whose `describe()` answers, which a closed
workflow's does.

`_get_handle` has exactly two callers in the tree — `factory/cli/roadmap.py:398`
and `factory/cli/roadmap.py:415` — and they are these two verbs. US1 replaces the
first with `_locate`, leaving one caller; US2 replaces the second, leaving none.
Trap 12 is what that costs.

**The branch to copy is nineteen lines up, and 046-US2 wrote the argument out.**
`factory/cli/roadmap.py:355` — `roadmap_pause_command`:

```python
    client, location = await _locate(args)
    if location.owner is RoadmapOwner.SCHEDULE:
        await client.get_schedule_handle(location.schedule_id).pause()
```

Its docstring says why, and the sentence is this spec's whole case: signalling the
run a schedule happens to be on "would report success while the next tick started
a fresh one and dispatch continued — worse than refusing, because it lies".
`factory/cli/roadmap.py:372` — `roadmap_resume_command` is the symmetric half.
`RoadmapOwner` is `factory/roadmap/discovery.py:51` — `RoadmapOwner`, four values
— `WORKFLOW`, `SCHEDULE`, `RUN`, `NONE` — and `location` comes from
`factory/roadmap/discovery.py:560` — `resolve_roadmap`. Four values, not two, is
why FR-010 needs two sentences and not one f-string (trap 13).

**Where the promotion has to arrive.** The corpus pass is
`factory/roadmap/workflow.py:832` — `_run_inner`, immediately followed by the
promotion application at `factory/roadmap/workflow.py:845` — `_run_inner`:

```python
            self._roadmap = await workflow.execute_activity(
                read_corpus_activity,
                ReadCorpusInput(specs_root=request.specs_root),
                **_FAST,
            )
```

The seam for FR-004 is between those two statements. `_promotions` itself is
initialised empty at `factory/roadmap/workflow.py:587` — `__init__` and assigned
from the carry-over at `factory/roadmap/workflow.py:815` — `_run_inner`; the
signal that writes it is `factory/roadmap/workflow.py:621` — `promote_spec` and
the reader is `factory/roadmap/workflow.py:1110` — `_apply_promotions`.

**The status query already reports promotions, so this spec buys visibility for
free.** `factory/roadmap/workflow.py:731` — `roadmap_status` sets
`promoted=entry.spec_dir in self._promotions`. Nothing in `factory/cli/status.py`
or the status board needs an edit for a recorded promotion to be reported; US3-S1
asserts that, and it is why this spec touches no reporting surface.

**The activity to model the reader on** is `factory/roadmap/workflow.py:494` —
`read_corpus_activity`, five lines in the same module. Registering it is nine
places, not two; trap 8 lists them.

**Why the record can be a file at all.** `factory/roadmap/workflow.py:494` —
`read_corpus_activity` is one statement, `return read_roadmap(request.specs_root)`
— the corpus the workflow reasons about is read off the worker host's disk, by
path, on every pass, from no clone and no remote. The worker host and the
operator's shell are the same machine on this floor, so a file the CLI writes
beside the corpus is a file the next tick reads. **Do not take this from the
ledger instead of from the code**: `roadmap/dispatch-is-decided-by-the-operators-working-tree`
was resolved on 2026-09-02 by `090-the-factory-reads-origin-not-the-operators-checkout`,
whose title asserts the opposite of what this design leans on. It does not: 090
changed how the *target clone* is refreshed and left this read alone, which is why
the citation above is the source line rather than the closed row. One forward
note, owned by another spec and not by this one:
`roadmap/the-corpus-is-an-operator-checkout-that-does-not-track-the-landing-branch`
is still open and proposes resolving `state:` from the landing branch, which would
put the frontmatter and this record on different sources. Compatible today; the
spec that takes that key owns the reconciliation.

**Two readers already skip a leading dot, by name, before they look for a
`spec.md`.** `factory/roadmap/models.py:440` — `read_roadmap` filters
`not path.name.startswith(".")`, and `factory/doctor/triage.py:254` —
`read_spec_records` filters the same way. A third scanner,
`factory/cli/nouns/spec.py:302` — `_pick_spec_number`, does not filter dots but
only matches `^\d+-`, so a dot-named directory is invisible to all three. FR-003.

**What the guard sweep records about these two verbs today.**
`tests/test_ergane_status.py:1542` opens the roadmap module's block; the three
rows this spec touches are `tests/test_ergane_status.py:1546`,
`tests/test_ergane_status.py:1549` and `tests/test_ergane_status.py:1550`:

```python
        "_get_handle": set(),
        "roadmap_pause_command": set(),
        "roadmap_resume_command": set(),
        "roadmap_promote_command": set(),
        "roadmap_unpark_command": set(),
```

The table is compared against a set derived from the source by
`tests/test_ergane_status.py:1702` —
`test_the_guard_sweep_discovers_every_cli_module_that_awaits_temporal`, so a
`try` added to either verb without a matching row fails that test with a message
about "functions differ from expected" — and so does a function *removed* without
its row.

**The offline CLI floor, already written.**
`tests/test_roadmap_schedule_discovery.py:304` — `fake_temporal` installs a fake
at `Client.connect`; `tests/test_roadmap_schedule_discovery.py:334` —
`scheduled_floor` is two timestamped runs plus a schedule and no bare workflow;
`tests/test_roadmap_schedule_discovery.py:516` — `bare_floor` is the opposite;
`tests/test_roadmap_schedule_discovery.py:370` — `invoke` runs the real
`main` over a captured stdout and stderr. Reuse all four rather than writing a
second fake client.

**The only environment that runs the real `RoadmapWorkflow`** is
`tests/test_roadmap_scheduler.py:474` — `run_roadmap`, an async context manager
that starts the workflow and yields its handle. Four other modules import it
rather than rebuilding it — `tests/test_roadmap_operator_surface.py`,
`tests/test_roadmap_durability.py`, `tests/test_roadmap_prompt_assembly.py` and
the scheduler module's own tests — so US3's workflow tests belong there. Two
things about it decide how US3's tests are written: its worker registers a
hand-written activity list (the entry is
`tests/test_roadmap_scheduler.py:530` — `run_roadmap`, whose line reads
`read_corpus_activity,`), and its signature takes no `carry_over`
argument. Trap 8 covers the first; the second is why US3-S2 proves the union with
a mid-pass signal, which the yielded handle can already send, rather than with a
carry-over the harness cannot supply.

## Traps

**Trap 1 — The memo route is closed by construction; do not design onto it.**
`factory/roadmap/schedule.py:270` — `create_schedule` states it in the tree's own
words: `ScheduleUpdate` has no memo field, so a memo could never be reconciled,
and `factory/roadmap/schedule.py:217` — `_schedule_for` builds the whole schedule
from `factory/roadmap/schedule.py:75` — `arguments`, which is six keys and no
carry-over. An implementer who reaches for a memo, a search attribute or a
schedule argument to carry the promotion will write code that
`factory/roadmap/schedule.py:284` — `update_schedule` silently reconciles away at
the next `ergane init`. Durable state on disk is the only route. FR-001.

**Trap 2 — The failure this spec fixes is a raised exception, not a false
success.** The older ledger row's summary reads like pause's pre-046 defect
("reports success while a fresh tick starts"), and that is *not* what happens
here: `handle.signal` against a closed run raises, and with
`tests/test_ergane_status.py:1549` recording zero guards the `RPCError` reaches
`factory/cli/errors.py:69` — `run_cli` and prints `unexpected error (...)`. An
implementer who writes the test for the wrong failure — asserting that promote
does not falsely report success — gets a green test against a defect that was
never there, and leaves the traceback in place. FR-008 and FR-010 are both about
the raised path. Reproduce it first.

**Trap 3 — The fake handle cannot raise, so the defect cannot be reproduced with
the fixture as it stands.** `tests/test_roadmap_schedule_discovery.py:214` — `signal`
appends to a list and returns:

```python
    async def signal(self, name: str, *args: Any, **kwargs: Any) -> None:
        self._client.signals.append((self.id, name))
```

There is no seam for "this run has completed". A test written by copying
`tests/test_roadmap_schedule_discovery.py:593` — `test_bare_workflow_promote_signals_the_workflow`
and asserting on `client.signals` passes today, before any change, and proves
nothing. The fake must gain a way to raise the refusal the real client raises — an
`RPCError` the module already imports and already constructs at
`tests/test_roadmap_schedule_discovery.py:207` — before US1-S4 or US2-S1 can fail
for the right reason. FR-008, FR-010.

**Trap 4 — That module's specs root does not exist, and its fakes are keyed on the
root's *name*.** `tests/test_roadmap_schedule_discovery.py:99` is
`SPECS_ROOT = "/srv/factory/ergane/specs"`, a path chosen because nothing ever
opened it. The moment `promote` writes a file, every test in that module which
drives `promote` must move to a writable root — and the new root must be
`tmp_path / "specs"`, not a bare `tmp_path`.
`factory/roadmap/workflow.py:178` — `roadmap_workflow_id` derives the roadmap's id
from the specs root's directory *name*, and the module's fakes are keyed on the
result: `tests/test_roadmap_schedule_discovery.py:104` and
`tests/test_roadmap_schedule_discovery.py:105` are
`BARE_ID = "roadmap-specs"` and `RUN_PREFIX = "roadmap-specs-"`. A test handed a
bare `tmp_path` gets `roadmap-<pytest-tmp-dir-name>`, the fake answers for nothing,
and the test asserts `_locate`'s "no roadmap is running here" refusal instead of
ever reaching the write. Two wrong moves to refuse: making the writer tolerate an
unwritable root so the fictional constant keeps working — that deletes FR-009's
refusal and hides an operator's typo — and pointing a test at this repository's own
`specs/`, which would create a directory in the operator's working tree.
`factory/cli/repo.py:578` — `_refuse_unsafe_removal` is this tree's precedent for
that hazard class, and trap 12 is its live instance. FR-009.

The naming rule has exactly one exception, and getting it wrong points the red
run at the operator's floor. It exists only for tests that must be *answered* by
the fakes keyed on `BARE_ID`/`RUN_PREFIX`; the absent-root test of FR-009 (T006)
reaches no floor at all, and there the name is a hazard rather than a
requirement. Nothing in the suite blocks a real connection —
`grep -n TEMPORAL tests/conftest.py` returns nothing, and the module's only
`Client.connect` patch is `tests/test_roadmap_schedule_discovery.py:304` —
`fake_temporal`, which that test does not use — so under the tests-first rule
the mandatory red run executes today's
`factory/cli/roadmap.py:397` — `roadmap_promote_command`, which is `_get_handle`
→ `factory/cli/roadmap.py:308` — `_locate` →
`factory/cli/roadmap.py:201` — `_connect`. Hand that run an absent
`tmp_path / "specs"` and `factory/roadmap/workflow.py:178` —
`roadmap_workflow_id` derives `roadmap-specs`, which on this host is the
operator's live roadmap: the schedule answers, `_handle_for` returns its newest
run, and the red phase signals `promote_spec` at the real floor. So T006 must
stub `_connect` and must name its absent root anything but `specs`. Do not
prove the ordering by *hoping* a connection fails; that is the same wrong move
trap 12 catches in an existing test. FR-009.

**Trap 5 — FR-007 deliberately ends a control, and only half of it.**
`tests/test_roadmap_schedule_discovery.py:593` — `test_bare_workflow_promote_signals_the_workflow`
asserts `(result.code, result.stdout, result.stderr) == (0, "", "")`. Printing the
record path makes that assertion fail, and the failure is *correct*: 046-US2 wrote
it when promote had nothing to say. Amend that one test. Do **not** touch
`tests/test_roadmap_schedule_discovery.py:575` — `test_bare_workflow_pause_and_resume_signal_the_workflow_silently`,
which asserts the same silence for pause and resume and is still true; and do not
respond to the red by dropping the print, which is FR-007.

**Trap 6 — The guard sweep is derived from the source and asserted by name, in
both directions.** Adding `try: ... except RPCError:` to either verb changes what
`tests/test_ergane_status.py:1702` —
`test_the_guard_sweep_discovers_every_cli_module_that_awaits_temporal` discovers,
and the run fails with "guards something other than []". The fix is the matching
row in the table at `tests/test_ergane_status.py:1542`, not deleting the row and
not widening to a bare `except Exception` — `tests/test_ergane_status.py:1901` —
`test_no_temporal_call_site_is_guarded_by_a_blanket_except` forbids exactly that.
The other direction bites US2: the sweep compares *set equality* of a module's
functions (`tests/test_ergane_status.py:1721` —
`test_the_guard_sweep_discovers_every_cli_module_that_awaits_temporal` is the
`set(actual_functions) == set(expected_functions)` assertion), so when
`_get_handle` loses its last caller and is removed, the `_get_handle` row at
`tests/test_ergane_status.py:1546` must be removed in the same commit — here
deleting the row *is* the fix, and leaving it fails with the same "functions
differ from expected" message. If a guard names a transport class, the verb must
also join the anti-vacuity list asserted at `tests/test_ergane_status.py:1841` —
`test_no_temporal_call_site_catches_the_transport_failure_alone`, which is a
sorted literal: adding to it in the wrong position fails on ordering,
not on meaning. FR-012, FR-013.

**Trap 7 — The roadmap is `AUTO_UPGRADE`, so a new activity call inside a
replayed prefix is a non-determinism failure, not a deployment detail.**
`factory/roadmap/workflow.py:528-530` declares it, and the comment above it
explains that the roadmap is the one workflow that never ends, so pinning it was
rejected. A run in flight adopts new code at its next workflow task and replays
its history under that code; a run whose history has one `read_corpus_activity`
where the new code schedules two will fail replay. The precedent for the gate is
`factory/workgraph/workflow.py:1826` — `_run_node`, `workflow.patched(...)` around
118's per-attempt standards read. The tempting wrong move is "the schedule's runs
live twenty seconds, so nobody is mid-flight" — which is false for the bare
roadmap an operator started with `--idle-rescan-s`, and false for any tick that is
waiting on a child epic. US3-S3 is what makes the gate provable rather than
merely instructed. FR-005.

**Trap 8 — Registering the new activity is nine places, not two, and the six the
entry did not name fail as a *hang*.** In production it is two:
`factory/worker.py:85` is the import and `factory/worker.py:197` is the entry in
`ACTIVITIES`; the import alone compiles and parks. But six test modules build their
own roadmap `Worker` from a hand-enumerated activity list containing
`read_corpus_activity`, and the seed US3 adds runs on **every** pass —
`workflow.patched(...)` returns True on a fresh run — so every one of them
schedules the new activity too:

- `tests/test_ergane_roadmap.py:137` — `_worker`
- `tests/test_scheduled_epics_carry_the_dials.py:124` — `_worker`
- `tests/test_roadmap_first_tick_on_fresh_init.py:118` — `_run_roadmap`
- `tests/test_roadmap_scheduler.py:530` — `run_roadmap` (the shared harness —
  `tests/test_roadmap_operator_surface.py`, `tests/test_roadmap_durability.py` and
  `tests/test_roadmap_prompt_assembly.py` import it rather than rebuilding it, so
  this one line covers four modules)
- `tests/test_roadmap_failure_notifications.py:238` — `run_roadmap_with_notifications`
- `tests/test_roadmap_failure_notifications.py:333` — `run_roadmap_with_sandboxed_workflow`
- `tests/test_023_us2_dispatch_pin.py:671` — `_run_roadmap`

Each also needs the import beside it. The symptom of forgetting one is the reason
this is a trap rather than a note: an activity nothing polls for does not raise —
the workflow task parks and the test sits until its own `wait_for` expires, so the
failure names a timeout and not an activity. In production the same forgetting is
a roadmap that has silently stopped dispatching. FR-006 requires the committed
assertion over `factory/worker.py`'s list precisely because the symptom is
silence.

And registering it has a tenth consequence, in a module nothing above names:
the activity's *input record* joins the swept Temporal payload boundary.
`tests/test_temporal_payload_shape.py:55` takes `factory.worker.ACTIVITIES`
whole, `tests/test_temporal_payload_shape.py:212` — `activity_boundary_types`
walks every registered activity's argument and return types, and
`tests/test_temporal_payload_shape.py:629` —
`test_every_boundary_field_has_a_default_or_is_allowlisted` fails any dataclass
field that has neither a default nor a row in `MUST_BE_PRESENT`. The sibling
this activity is modelled on is allowlisted by hand —
`tests/test_temporal_payload_shape.py:477` is
`"factory.roadmap.workflow.ReadCorpusInput": ("specs_root",)` — so an input
record with a bare `specs_root: str` fails in a module US3 would not otherwise
open. Give every field a default, or add the row beside that one with the same
kind of justification its neighbours carry; the reverse direction is guarded
too, by `tests/test_temporal_payload_shape.py:650` —
`test_the_allowlist_names_only_fields_that_are_still_on_the_boundary`, so a row
for a record that never lands is also a failure.

**Trap 9 — The record must be invisible to every reader of the corpus by *name*,
not by luck.** `factory/roadmap/models.py:440` — `read_roadmap` and
`factory/doctor/triage.py:254` — `read_spec_records` both filter
`not path.name.startswith(".")`. A directory named without the leading dot
survives those filters and is then skipped only because it holds no `spec.md`
(`factory/roadmap/models.py:445` — `read_roadmap`) — a weaker guarantee that the
next scanner added to the tree need not honour. Name the directory with a leading
dot, and write the `.gitignore` in the same act that creates it: a corpus under
version control that acquires an untracked promotions file will eventually acquire
a *tracked* one, and a tracked promotion promotes on every clone. FR-003.

**Trap 10 — Seed by union, and never consume.** Two mistakes here, and they are
opposites. The first is assigning `self._promotions` from the record, which drops
the carry-over's promotions assigned at `factory/roadmap/workflow.py:815` —
`_run_inner` and any promotion signalled mid-pass at
`factory/roadmap/workflow.py:621` — `promote_spec`. Union into it. The second is
deleting the record entry once it has been applied: a tick that reads a promotion
and then parks the spec on a preflight refusal would have spent it for nothing,
and the operator would have to promote again without being told why. A promotion
ends when the frontmatter leaves `draft`, and
`factory/roadmap/workflow.py:1110` — `_apply_promotions` already makes it moot at
that moment, without anyone writing to disk from a workflow. FR-004.

**Trap 11 — Do not build the symmetric park record.** It is the obvious next step
and it is wrong. A schedule tick begins with `_parked = {}`
(`factory/roadmap/workflow.py:565` — `__init__`) and re-runs clone, derivation,
preflight and onboarding against the document as it now stands, so a fixed spec is
retried at the next tick whether or not anybody unparks it; the park never
survived to be spent. A durable park record would be state whose only job is to be
cleared, and it would make the line stop retrying a spec that a re-read would have
passed. FR-011 asserts nothing is written, as a control, because the reviewer
cannot see an absence any other way.

**Trap 12 — One existing test patches the seam US2 deletes, and its specs root is
this floor's live roadmap.** `tests/test_roadmap_prompt_assembly.py:572` —
`test_the_unpark_verb_carries_the_spec_the_operator_named` monkeypatches
`roadmap_cli._get_handle` with its own handle and then calls
`roadmap_unpark_command(SimpleNamespace(specs_root="specs", spec="001-runtime-root"))`.
Unlike its neighbour nineteen lines above it, it installs **no** fake client — the
patched seam was the whole isolation. The moment `roadmap_unpark_command` calls
`_locate` instead, that monkeypatch is inert, `_locate` calls `_connect()` with no
arguments, and `factory/roadmap/workflow.py:178` — `roadmap_workflow_id` turns
`specs_root="specs"` into `roadmap-specs` — which on this host is the operator's
**live** roadmap id. There is no autouse fixture in `tests/conftest.py` that
blocks `Client.connect`, so the suite either fails in a module US2 never declared
or reaches the production control plane and signals `unpark_spec` at it. Convert
it in the same commit as the rewrite: keep its `_Handle` (it is the only test that
asserts the signal's *argument*, which the shared fake at
`tests/test_roadmap_schedule_discovery.py:214` does not record) and patch at the
new seam — `roadmap_cli._locate`, returning a fake client whose
`get_workflow_handle` hands back that `_Handle` — or move it to
`fake_temporal`/`bare_floor` only if the argument assertion survives the move.
Never leave it reaching a real client. FR-011.

**Trap 13 — One f-string for two owners prints a false sentence.** FR-010 covers a
completed run under *either* owner, and the honest answer differs:
`factory/roadmap/discovery.py:51` — `RoadmapOwner` has four values, and only
`SCHEDULE` has a next tick. On a bare floor — a `roadmap-<root>` workflow started
by `ergane roadmap start` that has since exited — nothing will start a next pass,
so telling the operator "the next pass re-checks the spec" sends them to wait for
something that will never happen, which is exactly the class of lie 046-US2
removed from `pause`. Branch on `location.owner`, the way
`factory/cli/roadmap.py:355` — `roadmap_pause_command` already does, and name
`ergane roadmap start` on the run-owned branch. US2-S6 fails when the two
sentences are the same string, so this cannot be satisfied by one format call.
FR-010.

## Sizing

**US1 — the record and the verb.** Production: `factory/roadmap/promotions.py`
(new: the path derivation, the read and the write, and the `OperatorError`
refusals) and `factory/cli/roadmap.py` (`roadmap_promote_command` and its
ownership branch). Tests: a new module for the record itself, amendments to
`tests/test_roadmap_schedule_discovery.py` (the raising fake, the `tmp_path /
"specs"` root, three new cases and one amended silence assertion), and the
`roadmap_promote_command` row in `tests/test_ergane_status.py`.

**US2 — the unpark sentence.** Production: `factory/cli/roadmap.py` and no other
file — in particular not `factory/roadmap/workflow.py`, because the unpark path is
a CLI refusal and nothing about a park changes; `_get_handle` is removed here,
where it loses its last caller. Tests: amendments to
`tests/test_roadmap_schedule_discovery.py`, the `roadmap_unpark_command` row **and
the `_get_handle` row** in `tests/test_ergane_status.py` (rows at
`tests/test_ergane_status.py:1550` and `tests/test_ergane_status.py:1546`), and the
conversion of `tests/test_roadmap_prompt_assembly.py:572` —
`test_the_unpark_verb_carries_the_spec_the_operator_named` that trap 12 names.
That last file is the one the first draft of this plan omitted; it is production
code's blast radius, not an optional tidy.

**US3 — the roadmap reads it.** Production: `factory/roadmap/workflow.py` (the
read activity beside `read_corpus_activity`, and the patched seed between the
corpus read and `_apply_promotions`) and `factory/worker.py` (two lines). Tests:
new cases in `tests/test_roadmap_scheduler.py` over `run_roadmap`, plus the
one-line activity registration in each of the six modules trap 8 lists —
`tests/test_ergane_roadmap.py`, `tests/test_scheduled_epics_carry_the_dials.py`,
`tests/test_roadmap_first_tick_on_fresh_init.py`, `tests/test_roadmap_scheduler.py`,
`tests/test_roadmap_failure_notifications.py` (two lists) and
`tests/test_023_us2_dispatch_pin.py` — and, if the new input record carries a
field with no default, one allowlist row in `tests/test_temporal_payload_shape.py`
(trap 8's last paragraph: registering the activity is what puts its record on
that sweep). US3 reads `factory/roadmap/promotions.py` and does not edit it,
which is why its edge on US1 is a pass-edge.

**What they share.** US1 and US2 share `factory/cli/roadmap.py` and the guard
sweep's expectation table; that is what the `depends_on_merged` edge is for, and
it is why they are not declared concurrent. US3 shares **no production file with
either** — it is the workflow, the worker and the roadmap test harnesses — and it
shares no test file with US2 at all.

**Against the 64 KiB deterministic diff bound (D-050).** This is why the story was
split rather than sized optimistically. The bound is measured on the assembled
diff *including* pasted evidence, and this repository's own recent stories put a
1,025-line change at 63,932 bytes — inside the last 2% before refusal. The
unsplit US1 implied roughly eight hundred to a thousand changed lines across four
production files and three test modules, plus a verification task's pasted
captures: the wrong side of that measurement to be guessing on. As split, US1 is
around two hundred production lines plus two test modules, US2 under sixty
production lines plus three test amendments, and US3 under a hundred production
lines plus seven small test edits. Each verification task asks for two short
terminal captures, not a transcript.

## Verification the operator will run, independent of the gate

Per constitution VIII and D-037 the judge sees the diff and the criteria only, so
runtime evidence must be committed as pasted output. Beyond that:

1. With the schedule live and no tick in flight, run
   `ergane roadmap promote <specs-root> --spec <a draft spec>`. It must exit 0 and
   name the file it wrote. Confirm the file exists and names that spec, and that
   the directory holding it carries a `.gitignore`.
2. Run `git status --short` in the repository that holds the corpus. The
   promotions directory must not appear.
3. Wait one tick, then run `ergane roadmap status <specs-root>`. The promoted spec
   must render `promoted=True`, and — if its edges are satisfied — must dispatch.
   This is the falsifiable test of the whole spec: it is the 2026-08-19 sitting,
   run forwards, and it is the step that a schema-only change cannot pass.
4. Edit that spec's frontmatter to `ready`, wait a tick, and confirm nothing
   changes — the record must be moot, not a second authority, and the file must
   still win.
5. Run `ergane roadmap unpark <specs-root> --spec <any spec>` against the same
   floor. It must exit 0, print the sentence naming the schedule, and leave the
   promotions directory holding exactly what step 1 left in it.
6. Run `ergane roadmap promote /nonexistent/specs --spec x`. It must refuse in one
   line naming that path, and `/nonexistent` must still not exist afterwards. With
   Temporal stopped it must give the same refusal, which is the evidence that
   FR-009 refuses before it connects.
7. Start a bare roadmap with `ergane roadmap start`, promote against it while it
   is live, and confirm both halves: the record is written *and* the run's status
   reports the promotion without waiting for a tick. Then let that run end and run
   `unpark` against it: the sentence must name `ergane roadmap start`, not a next
   tick.
