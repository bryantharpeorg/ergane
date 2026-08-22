# Implementation Plan: a schedule that has not run does not say running

**Spec**: `specs/085-a-schedule-that-has-not-run-does-not-say-running/spec.md`

## What already exists, and where

**Every line number below was verified on 2026-08-21 by printing that exact line
individually** (`sed -n '<n>p' <file>`). Check each one anyway.

**The policy, which is correct and stays — `factory/roadmap/schedule.py`:**

- `:239-241` — *"Skip, not buffer: a tick landing while the previous roadmap run
  still works must not queue a second behind it, or a slow epic turns one cadence
  into an unbounded backlog of duplicate dispatch."* Read it. It is right.
- `:242` — `policy=SchedulePolicy(overlap=ScheduleOverlapPolicy.SKIP),`, set inside
  `_schedule_for` at `:217`.
- `:71` — `#: A fact about a live schedule, never a declaration.` It sits
  directly above `factory/roadmap/schedule.py:72` — `paused: bool = False`, the
  observed field of `RoadmapSchedule` (the class opens at `:59`, `task_queue`
  follows at `:73`) — and is this module's precedent for what an observed field
  looks like.
- `:96-97` — the `_DECLARED` comment (*"`paused` is deliberately absent"*), and
  `:98-101` the tuple itself. **Nothing this spec adds goes in it** (trap 4).
- `factory/roadmap/schedule.py:104` — `def disagreements(desired, live) -> tuple[str, ...]:`
  (spelled in full because `factory/roadmap/discovery.py:104` is cited below and
  is a different thing entirely — `class _Found:`)
- `factory/roadmap/schedule.py:176` — `async def describe_schedule(client, schedule_id) -> RoadmapSchedule | None:`
  (re-qualified: the bullet above names `factory/roadmap/discovery.py`, so a bare
  `:176` here would resolve against the wrong file.)
- `:188` — `intervals = list(described.schedule.spec.intervals)` and `:197` —
  `cadence_s=int(intervals[0].every.total_seconds()) if intervals else 0,`
  **This is where the cadence comes from.** Proven code, same object, same tree.
- `:247` — `def _refuse_live_client(client: Any, act: str) -> None:`, whose
  docstring at `:248-254` records that removing its sentinel check *"created five
  schedules on the operator's live namespace"* (trap 5).

**Where the fact is thrown away — `factory/roadmap/discovery.py`:**

- `:65` — `class RoadmapLocation:` (`@dataclass(frozen=True)` is at `:64`); fields
  `:74-82`, including `:80` `schedule_paused` and `:81` `next_action_at`.
- `:84-100` — the `@property` at `:84`, `def refusal(self) -> str:` at `:89`,
  returning the operator-facing sentence at `:97-100`. **This is the shape US2
  copies**: a computed property that phrases a fact for the operator, with a
  docstring saying what it degrades to.
- `factory/roadmap/discovery.py:104` — `class _Found:` (spelled in full: the
  `:104` cited in the section above is `factory/roadmap/schedule.py`'s
  `disagreements`); `:110-111` the same two fields, defaulting to `None`.
- `factory/roadmap/discovery.py:139` — `async def _find_owning_schedule(client, bare_id) -> _Found | None:`,
  whose docstring at `:147-148` already promises *"A schedule that owns dispatch
  is reported even when it has not ticked yet"*. (Re-qualified: the bullet above
  names `factory/roadmap/schedule.py`, so a bare `:139` here would resolve
  against the wrong file.)
- `:159` — `described = await client.get_schedule_handle(entry.id).describe()`
- **`:166-168` is the exact site**:
  ```python
          state = getattr(getattr(described, "schedule", None), "state", None)
          info = getattr(described, "info", None)
          next_times = list(getattr(info, "next_action_times", None) or [])
  ```
  `info` is bound at `:167`, one field read off it at `:168`.
  `num_actions_skipped_overlap`, `recent_actions`, `running_actions` and
  `created_at` are all on that object and all discarded.
- `:169-175` — the `_Found(...)` construction, five keyword arguments. `:241-245`
  is `LOOKUPS`, the three rungs, unchanged by this spec.
- `factory/roadmap/discovery.py:248` — `async def resolve_roadmap(client,
  specs_root) -> RoadmapLocation:`, with **two** `RoadmapLocation(...)`
  constructions: `:265-275` (found) and `:276-286` (the empty answer). Both need
  handling (trap 8). (Spelled in full: `factory/roadmap/schedule.py:248` is the
  opening line of `_refuse_live_client`'s docstring, cited in the section above.)

**Where the lie is printed — two renderers, one sentence:**

- `factory/cli/status.py:157` — `class RoadmapDisposition:`, fields `:165-178`
  (`:168` `schedule_paused`, `:169` `next_action_at`); `:518-529` constructs it,
  copying both off the location at `:522-523`.
- `factory/cli/status.py:723` — `def _roadmap_lines(floor: FloorStatus) -> list[str]:`
- `factory/cli/status.py:729` — `state = "paused" if disposition.schedule_paused else "running"`,
  printed at `:730` as `f"schedule: {disposition.schedule_id} ({state})"`, with
  `:736` the `f"next tick: {disposition.next_action_at}"` line.
- `:738` — `lines.append(f"dispatch: {'paused' if disposition.dispatch_paused else 'running'}")`
  **This is the word FR-012 adopts.** `ergane status` already calls this fact
  dispatch; `ergane roadmap status` calls it `roadmap`.
- `factory/cli/roadmap.py:424` — `def _render_disposition(location: RoadmapLocation) -> str:`
- `factory/cli/roadmap.py:432` — `state = "paused" if location.schedule_paused else "running"`
  — the same sentence, second file. `:433` and `:442` are its two lines.
- `factory/cli/roadmap.py:446` — `def _render_status(status: RoadmapStatus) -> str:`
  and `:448` — `f"roadmap: {'paused' if status.paused else 'running'}",` — the
  colliding line.

**What 065 already landed, so nobody rebuilds it:**

- `factory/roadmap/workflow.py:139` — `def _is_epic_status(value: object) -> bool:`
  and `:148` — `return hasattr(value, "epic_state") and hasattr(value, "nodes")`
- `factory/roadmap/workflow.py:882` — `status = handle.result()`, with `:883-895`
  discarding a bad child result and continuing.
- `factory/doctor/probes.py:474` — `class RoadmapWedgeProbe:` — catches a
  *workflow task in failed state*. A stuck-but-healthy run is invisible to it.
- **`factory/roadmap/workflow.py:849` is the finding's stale anchor**, reading
  `# Capacity: count every open epic-* workflow (the roadmap's own`.

**The test seams — read these before writing a line of test:**

**Each of the four fakes has TWO holes, not one, and they are in different
objects.** Every one of them builds `info=SimpleNamespace(next_action_times=...)`
and nothing else — that is the `ScheduleInfo` half, and it is where
`num_actions_skipped_overlap`, `recent_actions` and `created_at` come from. Three
of the four *also* build a `schedule` with only `action` and `state` on it and
**no `spec` attribute at all** — that is the `Schedule` half, and it is where the
cadence comes from. Either hole alone makes the new read degrade to `unknown`.
Each was printed line by line on 2026-08-21:

- `tests/fake_schedules.py:65` — `info=SimpleNamespace(next_action_times=[]),`,
  inside the `describe()` at `:57` of the in-memory schedule server bound to
  `factory.roadmap.schedule._schedule_client_factory`. **This is the one fake that
  does not need a `spec` added**: `:63` is `schedule=self._stored(),` and
  `_stored()` at `:51` returns a real `temporalio.client.Schedule` out of
  `self._server.schedules`, stored by `create_schedule` at `:90` from whatever the
  factory built — and the factory builds
  `spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=...)])` at
  `factory/roadmap/schedule.py:236-237`. So `described.schedule.spec.intervals`
  already resolves through this one. Its `info` half is still a hole.
- `tests/test_roadmap_schedule_discovery.py:156-158` — `info=SimpleNamespace(`
  / `next_action_times=list(self._schedule.next_action_times)` / `)`, inside
  `_FakeScheduleHandle.describe()` at `:143-159`. Its `class FakeSchedule:` is at
  `:129`, with `next_action_times` at `:135`. **`spec` is missing too**: the
  `schedule=SimpleNamespace(` at `:146` closes at `:155` and carries `action` and
  `state` (`:154`) and nothing else.
- `tests/test_roadmap_wedge_visibility.py:97-99` — the same three lines, inside
  the `describe()` at `:86-100`; `class FakeSchedule:` at `:74`,
  `next_action_times` at `:78`. **`spec` is missing too**: `schedule=SimpleNamespace(`
  at `:89` closes at `:96`, `state` at `:95`, no `spec`.
- `tests/test_ergane_status.py:355` — the same thing on one line,
  `info=SimpleNamespace(next_action_times=list(self._schedule.next_action_times)),`,
  inside the `describe()` at `:344-356`; `class FakeSchedule:` at `:326`,
  `next_action_times` at `:330`. **`spec` is missing too**:
  `schedule=SimpleNamespace(` at `:347` closes at `:354`, `state` at `:353`, no
  `spec`. **This is the fake US3's `ergane status` renderer tests run through**,
  so US3 cannot be tested without both of its halves.

The three `SimpleNamespace` fakes import from `temporalio.client` already —
`tests/test_roadmap_schedule_discovery.py:86` and
`tests/test_roadmap_wedge_visibility.py:29` both import
`ScheduleActionStartWorkflow`, and `tests/test_ergane_status.py:201` opens a
multi-name import from the same module — so `ScheduleSpec` and
`ScheduleIntervalSpec` are one name each away, and there is no need to invent a
namespace shape by hand. `factory/roadmap/schedule.py:222` and `:225` show the
import the production code uses for exactly these two.

**The renderer tests that already pin today's output — this is what the US3-S3
control has to keep green, and `tests/test_ergane_roadmap.py` is not among them
(it drives `start|pause|resume|promote|status` through the dispatcher and asserts
no rendered line at all):**

- `tests/test_roadmap_schedule_discovery.py:472` —
  `def test_bare_workflow_status_output_is_unchanged(`, whose assertion at
  `:491-498` compares `result.stdout` **byte for byte** and whose first element is
  `"roadmap: running\n"` (`:492`). **FR-012 renames exactly that line, so this
  test must be updated by US3** — it is the only equality assertion on the
  string, and leaving it fails the gate rather than passing wrongly.
- `tests/test_roadmap_schedule_discovery.py:340` —
  `def test_status_reports_the_newest_run_and_names_both(`, which asserts by
  containment (`:363-366`) and so survives, but whose docstring quotes the whole
  block including `roadmap: running` at `:351`. Docstrings at `:47`, `:479` and
  `:648` quote it too and go stale the same way.
- `tests/test_ergane_status.py:721-726` — the verbatim roadmap section quoted in
  the docstring of the disposition test, asserted by containment at `:753-756`
  (`schedule: … (paused)`, `next tick: …`). `tests/test_ergane_status.py:136-141`
  is the module docstring's copy of the same block.
- `tests/test_roadmap_wedge_visibility.py:1-15` — 065's tests, whose docstring
  explains why the floor is faked at `Client.connect` rather than driven through
  a time-skipping server. Follow that precedent.
- `tests/test_roadmap_first_tick_on_fresh_init.py` — the fresh-schedule window,
  but read its docstring at `:1-7` before assuming it protects US2-S5: it drives
  `factory.roadmap.workflow` through a real `WorkflowEnvironment` and imports
  neither `factory.roadmap.discovery` nor either CLI renderer. It proves the
  *workflow's* first tick does not raise on a freshly-initialised tree. **No
  existing test covers a never-ticked schedule's rendered verdict** — US2-S5 and
  US1-S3 are writing that coverage, not preserving it.

**The probe that makes this spec plumbing rather than research**, run on this host
2026-08-21 and to be committed as SC-001 evidence:

```
$ .venv/bin/python -c "import importlib.metadata as md; print(md.version('temporalio'))"
1.31.0
$ .venv/bin/python -c "import temporalio.client as c, dataclasses; [print(f.name, ':', f.type) for f in dataclasses.fields(c.ScheduleInfo)]"
num_actions : int
num_actions_missed_catchup_window : int
num_actions_skipped_overlap : int
running_actions : Sequence[ScheduleActionExecution]
recent_actions : Sequence[ScheduleActionResult]
next_action_times : Sequence[datetime]
created_at : datetime
last_updated_at : datetime | None
$ ... dataclasses.fields(c.ScheduleActionResult) ...
scheduled_at : datetime
started_at : datetime
action : ScheduleActionExecution
```

Two lines of that source are load-bearing beyond the field names, and SC-001
should carry them:

```
$ .venv/bin/python -c "import temporalio.client as c, inspect; print(inspect.getsource(c.ScheduleInfo))" | head -30
    recent_actions: Sequence[ScheduleActionResult]
    """10 most recent actions, oldest first."""
```

**"oldest first"** is trap 15 — the newest is `recent_actions[-1]`, and the
adjacent `next_action_times` read at `factory/roadmap/discovery.py:174` takes
`[0]`. The bound of ten is why only the newest entry is worth carrying: a schedule
starved far longer than ten cadences still has one.

## Traps

**1. A lifetime counter is not a health signal.** `num_actions_skipped_overlap`
never decreases, so `count > 0 → unhealthy` is a permanent warning, and a
permanent warning is read once and ignored forever — which is this outage in a new
hat. The trigger is *how long since a tick actually started*; the count is
evidence printed inside the sentence. US2-S3 is the control that proves you did
it that way and the scenario most likely to fail an attempt. The tree already
shares the instinct: `factory/workgraph/worktree.py:208` exists solely to emit its
deprecation *"once per Python process."*

**2. Two renderers, one sentence.** `factory/cli/status.py:729` and
`factory/cli/roadmap.py:432` are the same line in two files. Fixing one leaves the
other lying and a third caller would inherit it again. Put the verdict on
`RoadmapLocation` beside `refusal` (`factory/roadmap/discovery.py:89`) and have
both renderers read it. US3-S2 renders both from one location and asserts they
agree — a diff where each renderer computes its own answer passes its own tests
and fails there.

**3. Degrade, do not raise.** 052 landed the principle that a degraded status
query still renders the rest. Every new read uses the same `getattr(..., default)`
discipline already at `factory/roadmap/discovery.py:166-168`. A `described` object
from an older server, or a fake that predates this change, must yield `unknown`
and a complete report — not a traceback in the operator's floor view.

**4. Do not add the new fields to `_DECLARED`.**
`factory/roadmap/schedule.py:98-101` is the set a drift report names, and `:96-97`
says `paused` is deliberately absent for exactly this reason. An observed fact in
the declared set makes every `apply_schedule` run report a disagreement against
something no manifest can state.

**5. Tests reach schedules through the seam, never a real client.**
`factory/roadmap/schedule.py:247` exists because removing its sentinel check
*created five schedules on the operator's live namespace* — its docstring says so
at `:248-254`. One Temporal serves this host and it holds the live
`ergane-roadmap` schedule. Extend the fakes; never connect. (The docstring cites
"D-045", and `docs/decisions.md` carries **two** entries under that number: the
one meant here is *"Test-time isolation from the live evidence store is enforced,
not conventional"*, `docs/decisions.md:1001`, claimed at
`030-test-suite-store-isolation` US2 — not the `035-operator-completion` entry at
`docs/decisions.md:65`. Do not spend an attempt reconciling them; the numbering
collision is a repo defect, not this spec's.)

**6. Four fakes, TWO holes each, and the second hole is the one that sinks the
story.** This is the trap most likely to end an attempt, because failing it
produces a *passing* suite.

*Hole one, the `ScheduleInfo` half — all four fakes.*
`tests/fake_schedules.py:65`, `tests/test_roadmap_schedule_discovery.py:156-158`,
`tests/test_roadmap_wedge_visibility.py:97-99` and `tests/test_ergane_status.py:355`
all build `info=SimpleNamespace(next_action_times=...)` and nothing else. That is
where `num_actions_skipped_overlap`, `recent_actions` and `created_at` come from.

*Hole two, the `Schedule` half — three of the four.* FR-002 reads the cadence from
**`described.schedule.spec.intervals`**, and three of these fakes build a
`schedule` carrying `action` and `state` and **no `spec` attribute whatsoever**:

| fake | `schedule=` opens | closes | has `spec`? |
| --- | --- | --- | --- |
| `tests/test_roadmap_schedule_discovery.py` | `:146` | `:155` | **no** |
| `tests/test_roadmap_wedge_visibility.py` | `:89` | `:96` | **no** |
| `tests/test_ergane_status.py` | `:347` | `:354` | **no** |
| `tests/fake_schedules.py` | `:63` `schedule=self._stored(),` | — | **yes** — a real `Schedule` |

Only `tests/fake_schedules.py` is already whole on this half: `_stored()` at `:51`
returns the `Schedule` the factory itself built, and
`factory/roadmap/schedule.py:236-237` puts
`spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=...)])` on it.

*Why this is worse than an ordinary missing fixture.* FR-008 makes an unreadable
cadence `unknown`, and `unknown` is a state the new code is **designed** to
tolerate. So a fake left with no `spec` does not fail — it quietly yields
`unknown`, US2-S1/S2/S3/S5 and every starved rendering in US3 become unreachable,
and the suite goes green having exercised no verdict at all. That is precisely the
defect this spec exists to close, arriving through the test suite instead of the
CLI.

*The control.* US1-S7 / T009a assert a readable cadence through **every** fake, and
SC-009 commits the table. Write that control before extending the fakes, so you
watch it fail three times and then pass. A story that extends the `info` half and
declares victory is the single most likely way this spec burns a second attempt.

**7. 065 is done, and the finding's anchor for it is stale.** The guard is at
`factory/roadmap/workflow.py:139`/`:148` with its caller at `:882-895`;
`RoadmapWedgeProbe` is at `factory/doctor/probes.py:474`. The finding cites
`factory/roadmap/workflow.py:849`, which is a comment in the capacity block. Do
not rebuild the guard, and do not conclude from `:849` that it is missing. This
spec is about the schedule's visibility, not the crash that caused one wedge.

**8. `resolve_roadmap` constructs `RoadmapLocation` twice** —
`factory/roadmap/discovery.py:265-275` and `:276-286`. A new required field passed
at only one site is a `TypeError` at the empty answer, which is the path a new
user's very first `ergane status` takes. Default the fields, or pass them at both.

**9. The `next tick:` line is true and must not be touched.** During starvation the
schedule really will tick; it will just skip. `factory/cli/status.py:736` and
`factory/cli/roadmap.py:442` keep their wording and values, or US3-S3's
byte-for-byte control breaks for no gain.

**10. A schedule that has never ticked is not starved.**
`factory/roadmap/discovery.py:147-148` promises such a schedule is reported. Use
`ScheduleInfo.created_at` as the reference when `recent_actions` is empty. A false
`starved` on a thirty-second-old schedule makes `ergane init` look broken to every
new user. **Nothing in the suite guards that today**:
`tests/test_roadmap_first_tick_on_fresh_init.py` sounds like it does and does not
— its docstring at `:1-7` says it drives the *workflow's* first tick through a
real `WorkflowEnvironment`, and it imports neither `factory.roadmap.discovery`
nor either CLI renderer. US1-S3 and US2-S5 are the first coverage of the
never-ticked window, so write them as new ground rather than looking for an
existing case to keep green.

**11. `starved` is a new word, and it is genuinely unclaimed — the three words to
avoid are claimed in the code, not in `CONTEXT.md`.** Grepping `CONTEXT.md` for
them finds only `blocked`, at `CONTEXT.md:132` (*"A blocked agent's request for
information"*, the **Question** entry); `stalled` and `parked` are not in that
file at all, so do not conclude from a fruitless grep that they are free. Their
real owners: `stalled` → `factory/mergequeue/models.py:77`
(`STALLED = "STALLED"`), the outcome the classifier reaches past `stall_after_s`
(`factory/mergequeue/classify.py:19`, decided at `:92-94`); `parked` →
`factory/cli/roadmap.py:452`, `f"parked: {len(status.parked)}",` — which prints
**two lines below the line FR-012 rewrites**, in the same `_render_status` block.
Use `starved`, and use the same token in both renderers so the two stay
grep-comparable.

**12. Principle VIII.** The judge sees the diff and the criteria and nothing else.
SC-001 is pasted probe output, SC-004 a committed table, SC-006 and SC-007 pasted
renderings of both verbs. Describing behaviour instead of committing its output
fails the criterion however correct the code is.

**13. One test file per story.**
- US1 → `tests/test_schedule_ticks_survive_the_read.py`
- US2 → `tests/test_a_starved_schedule_is_not_running.py`
- US3 → `tests/test_both_verbs_agree_about_the_schedule.py`

**14. FR-012 breaks a byte-for-byte assertion that already exists, and US3 owns
fixing it.** `tests/test_roadmap_schedule_discovery.py:491-498` asserts
`result.stdout ==` a six-line string whose first element is `"roadmap: running\n"`
(`:492`). Renaming that line makes the equality fail, which is the correct
outcome — update the expected string in the same diff, and update the docstrings
that quote the block (`:47`, `:351`, `:479`, `:648`, and this test's own at
`:479-484`). Do **not** weaken the assertion from `==` to `in` to make it pass:
byte-for-byte is what US3-S3's control is worth, and downgrading it is a
regression dressed as a fix.

Two facts that make the rename safe rather than risky. First, `_render_status`
already prints a third line containing the word `running` —
`factory/cli/roadmap.py:451`, `f"running: {', '.join(status.running) or '-'}",`,
the list of running epics — so before the rename this block says `running` twice
about two different things, and `parked:` follows at `:452`. Second,
`factory/cli/status.py` already solved this: `:738` `dispatch:` sits immediately
above `:739` `running:` and `:740` `parked:`. Adopt that layout exactly and the
two verbs converge instead of drifting.

**15. `recent_actions` is oldest-first, and the line you are copying takes `[0]`.**
The read this story widens ends with
`factory/roadmap/discovery.py:174` —
`next_action_at=next_times[0].isoformat() if next_times else None,` — and `[0]` is
right *there*, because `next_action_times` is a list of future times in ascending
order and the soonest is the one wanted. `recent_actions` is the mirror image. The
installed SDK documents the field as **"10 most recent actions, oldest first."**,
so the newest is `recent_actions[-1]`. Reaching for `[0]` one field over is the
most natural thing an implementer will do in this diff, it raises no type error,
and it reports a start up to ten cadences stale — which under FR-006's
two-interval threshold manufactures `starved` on a schedule that is ticking
perfectly. US1-S6 / T001a is the control: entries with distinct times and an
assertion that fails at the wrong end.

**16. The one assumption that could have changed the design is settled — by type,
not by observation.** The spec's Assumptions used to flag "do skipped ticks appear
in `recent_actions` at all?" as the question that would reshape everything. It is
answered, and cheaply, without a live starved schedule. Run this and read the
dataclass source rather than the docs:

```
$ .venv/bin/python -c "import temporalio.client as c, inspect; print(inspect.getsource(c.ScheduleActionResult))"
    scheduled_at: datetime
    """Scheduled time of the action including jitter."""
    started_at: datetime
    """When the action actually started."""
    action: ScheduleActionExecution
    """Action that took place."""
    ...
        return ScheduleActionResult(
            scheduled_at=res.schedule_time.ToDatetime()...,
            started_at=res.actual_time.ToDatetime()...,
            action=ScheduleActionExecutionStartWorkflow._from_proto(
                res.start_workflow_result
            ),
        )
$ .venv/bin/python -c "import temporalio.client as c, dataclasses; print([f.name for f in dataclasses.fields(c.ScheduleActionExecutionStartWorkflow)])"
['workflow_id', 'first_execution_run_id']
```

Every entry is built from `res.start_workflow_result` and carries a
`first_execution_run_id`. **A skipped tick starts no workflow and has no run id,
so the type has nothing to put in the entry.** `started_at` comes from
`res.actual_time` and is documented *"When the action actually started."* That is
the whole answer, and it costs one command.

*The branch, if a live server ever disagrees.* Should a real describe ever return a
`recent_actions` entry whose `action.first_execution_run_id` is empty, that is a
skipped tick appearing in the list and the primitive changes shape: filter those
entries out before taking the newest, say so in the diff, and do **not** fall back
to deriving the last start from `num_actions` — a counter gives you a count, never
a time, and a verdict built on it is trap 1 wearing a different hat.

**17. 083 was pulled toward `factory/cli/roadmap.py` and ruled itself out of it —
so you are the only editor, unless 083 breaks its own rule.**
`specs/083-teardown-is-a-verb-that-names-what-it-removed/` is being drafted in the
same batch. Its US3 wires `ergane uninstall` to `roadmap_pause_command`
(`factory/cli/roadmap.py:310`), and to make that step testable the obvious move is
a client seam in this file — there is none today: `_connect()` at `:189` calls
`Client.connect` inline at `:193` and that is the file's only occurrence.
`factory/cli/repo.py:93` is the shape it would copy —
`_temporal_client_factory: Callable[[], Awaitable[Client]] = _open_client`, read at
`factory/cli/repo.py:98` — a module attribute a test can rebind, which is why
`factory/cli/repo.py` is testable and `factory/cli/roadmap.py` is not.

**083 declined that move.** Its plan's "The ruling on composition" puts the seam
in teardown's own step table instead, and its **FR-017 states that
`factory/cli/roadmap.py` MUST NOT be edited by 083 at all**, with a US3-S6 control
and a `git diff --stat` check behind it. So the expected outcome is that this spec
is the file's only editor in the window.

The hazard that remains is an 083 attempt that breaks that rule: the seam would
land above `factory/cli/roadmap.py:424` and shift every anchor below it silently,
because there is real content at the old numbers. Both stories are the tail of
their chain, so the two would land together. Four rules, and the spec states them
as declared scope under *The other spec that reaches for this file*:

1. **Stay inside the two render functions** — `_render_disposition`
   (`factory/cli/roadmap.py:424`) and `_render_status` (`:446`). Lines `:432` and
   `:448` are the whole of this spec's business in that file.
2. **Do not add or move a client seam** near `factory/cli/roadmap.py:189`/`:193`.
   083 ruled that seam out of its scope rather than into it, so building it here
   helps nobody — it just adds an unowned edit to a file two epics are reading at
   once.
3. **Do not touch `roadmap_pause_command` (`factory/cli/roadmap.py:310`)**, even
   though its ownership behaviour is a real defect and you will read straight past
   it. It is 083's defect and 083's story.
4. **If 083 landed first, re-derive the anchors rather than trusting them.**
   Under 083's FR-017 this file is untouched and they hold — but that is a rule an
   attempt can break. Re-derive by exact line text with `grep -n`, never by
   offset. A seam inserted anywhere above `factory/cli/roadmap.py:424` shifts all
   of them, and there is real content at the old numbers, so the misreading
   resolves silently instead of erroring.

## Sizing

**US1 is small, and it is the largest of the three.** Four fields onto two
dataclasses, one read site widened, two construction sites, and **eight fixture
edits, not four** — all four fakes need their `info` half filled in, and three of
those four need a `spec` added to the `schedule` half as well (trap 6). The time
goes into the degrade control, into noticing `resolve_roadmap` builds a location
twice, and into the fake-parity control that proves the `spec` half was not
skipped. An attempt that reads "four fakes" and edits four `info=` lines is the
predictable second attempt here.

**US2 is small but exacting.** One computed property and a named constant; the
whole story is the five-case verdict table, and every case is a scenario. A second
attempt here almost certainly means trap 1 — a verdict wired to the lifetime
counter, which passes a naive test and fails US2-S3.

**US3 is small.** Two renderers reading one property, one line renamed, the
byte-for-byte control, and the existing byte-for-byte assertion the rename breaks
(`tests/test_roadmap_schedule_discovery.py:491-498`, trap 14). A second attempt
means trap 2 (each renderer computing its own answer), trap 9 (a `next tick:`
line rewritten for tidiness), trap 14 answered by weakening `==` to `in`, or
trap 17 — widening the edit in `factory/cli/roadmap.py` past the two render
functions, into the seam 083 declined to add and this spec must not add either.

## Verification the operator will run, independent of the gate

- **Point `ergane status` at the live schedule while a roadmap run is wedged and
  read the schedule line.** That is the exact six-hour scenario and the only thing
  that proves the fix. Reproduce a wedge by terminating a child epic workflow the
  way the reporter did, and watch the line change.
- **Run `ergane status` and `ergane roadmap status` back to back on one floor and
  diff the verdict word.** Two renderers agreeing in tests and disagreeing in
  production is the failure mode trap 2 exists for.
- **Run `ergane init` on a scratch repo and read the schedule line inside the first
  cadence.** If it says starved, trap 10 was missed and every new user meets a
  broken-looking install.
- **Let the live schedule tick normally for one full cadence and confirm the line
  is byte-identical to today's.** The control, and the one that protects the
  operator's own muscle memory.
- **Grep the diff for the cadence read and count the fixtures that gained a
  `spec`.** Three of the four must have gained one; if only the `info=` lines
  moved, trap 6 was half-answered and the verdict suite is green for nothing. The
  gate cannot catch this — `unknown` is a state the code tolerates by design —
  which is why it belongs on the operator's own list.
