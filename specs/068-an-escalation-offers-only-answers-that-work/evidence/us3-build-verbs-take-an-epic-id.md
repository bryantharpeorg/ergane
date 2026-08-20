# US3 evidence: every build verb is keyed by the epic id

Runtime evidence for 068 US3, committed as an artifact because the judge sees
the diff and the acceptance criteria and nothing else (constitution VIII, 068
plan trap 10). Every block below is pasted tool output, not a description of it.

Collected on 2026-08-20 in this worktree, against a scratch epic
`077-demo-epic` planted at `/tmp/us3evidence/` with two survivor worktrees
(`us1`, `us2`), each carrying uncommitted work, and its compiled graph at
`/tmp/us3evidence/specs/077-demo-epic/workgraph.json`. No workflow named
`epic-077-demo-epic` has ever existed on the Temporal server the CLI dialled,
which is the state US3-S1 and US3-S5 are about.

## The subcommand enumeration (US3-S3, FR-010)

Read off the real parser by `add_parser`, not from a list written by hand:

```
subcommand                   first positional     classification
--------------------------------------------------------------------------------
start                        graph                declared exclusion
status                       epic_id              live-epic verb
pause                        epic_id              live-epic verb
resume                       epic_id              live-epic verb
kill                         epic_id              live-epic verb
answer                       epic_id              live-epic verb
resolve                      epic_id              live-epic verb
reset                        epic_id              live-epic verb
salvage                      graph                declared exclusion
complete-node-externally     epic_id              live-epic verb
external-completion-count    None                 declared exclusion
```

Eight live-epic verbs, eight `epic_id`. The three exclusions are declared with
their reasons in `tests/test_build_verbs_take_an_epic_id.py`
(`DECLARED_EXCLUSIONS`), and that test fails if a subcommand ever appears in
neither list.

## `reset <epic-id>` resolves the graph itself (US3-S1, FR-009)

`ergane build reset 077-demo-epic`, run from `/tmp/us3evidence` so the default
`--specs-root specs` applies. The only Temporal read is the RUNNING safety
check, and it answered `NOT_FOUND`; the graph came off disk:

```
us1: committed dirty state, removed worktree, archived branch
us2: committed dirty state, removed worktree, archived branch
exit=0
```

## The survivors are archived, not deleted (US3-S5)

`git -C target for-each-ref --format='%(refname)' refs/heads` after that run:

```
refs/heads/archive/factory/077-demo-epic/us1/7e3b3cfb801c
refs/heads/archive/factory/077-demo-epic/us2/c133cc860b56
refs/heads/ergane-buildout
```

The workflow was absent from Temporal for the whole of it, and reset proceeded
anyway — the behaviour `factory/cli/nouns/build.py`'s `NOT_FOUND` branch has
had since 047, carried through the argument change unchanged.

Still idempotent, by epic id:

```
$ ergane build reset 077-demo-epic
us1: nothing to do
us2: nothing to do
exit=0
```

## The graph path is still accepted, unchanged in meaning (US3-S4)

```
$ ergane build reset specs/077-demo-epic/workgraph.json
us1: nothing to do
us2: nothing to do
exit=0
```

## Neither form is silently reinterpreted (US3-S2, trap 8)

An epic id that names no compiled epic is refused naming the id **and** the
path it resolved:

```
$ ergane build reset 999-no-such-epic
ergane: no epic '999-no-such-epic' is compiled here (looked for
/tmp/us3evidence/specs/999-no-such-epic/workgraph.json); compile it with
`ergane spec derive`, pass --specs-root, or give the path to a compiled
workgraph.json instead of an epic id
exit=1
```

A mistyped **path** fails as a path, naming what was typed. It is never read as
an epic id, so the specs root the operator never mentioned does not appear:

```
$ ergane build reset nowhere/workgraph.json
ergane: cannot read nowhere/workgraph.json: [Errno 2] No such file or directory:
'nowhere/workgraph.json'
exit=1
```

The two forms are disjoint by construction rather than by precedence: an
argument carrying a path separator or a `.json` suffix is a path, everything
else is an epic id (`names_a_compiled_artifact`). Deciding by "does this file
exist?" is what would have produced the silent reinterpretation.

## The gate

`uv run pytest -q` in this worktree, whole suite:

```
3823 passed, 49 skipped, 7 warnings in 305.77s (0:05:05)
```

The six pre-existing `reset` call sites that pass a graph path
(`tests/test_ergane_build.py:1284, 1297, 1342, 1363, 1378, 1422`) are inside
that total and were not edited.

### The gate, re-run, and the one flake that has to be named

A verification run of the same commit failed the gate on a test this diff does
not touch and does not import — `tests/test_roadmap_prompt_assembly.py::
test_the_operator_unparks_a_fixed_spec_and_the_next_tick_dispatches_it`, an 044
US2 test — with a dispatch **order** assertion inverted:

```
E       AssertionError: assert ['001-runtime..., '002-bravo'] == ['002-bravo',...runtime-root']
E         At index 0 diff: '001-runtime-root' != '002-bravo'
1 failed, 3823 passed, 48 skipped, 6 warnings in 303.79s (0:05:03)
```

Re-run whole, unchanged tree, same commit:

```
3823 passed, 49 skipped, 6 warnings in 302.32s (0:05:02)
```

The file alone, twelve consecutive runs: `8 passed` every time. The single test,
twenty-five consecutive runs *while the full suite ran beside it* for CPU
contention: `1 passed` every time. It is rare, not load-triggered in any way
this worktree could provoke on demand.

The mechanism is in the test, not in the code under it. Its `env` fixture is
`WorkflowEnvironment.start_time_skipping()` (`tests/test_roadmap_scheduler.py`,
the `env` fixture), so the server jumps the clock whenever every workflow is
blocked. `_await_running` returns as soon as `roadmap_status` reports the child
**started**, which is strictly earlier than the child's first workflow task —
and that first task is where `ScriptedEpicWorkflow.run` calls `on_dispatch`
(`tests/roadmap_script.py`). So after the `unpark_spec` signal the skipped clock
can carry the roadmap into its next tick and run `001-runtime-root`'s child to
completion before the held `002-bravo` child has executed its first task, and
the list the assertion reads is in start-*execution* order rather than
start order. Two elements, inverted — exactly the observed failure.

Left alone deliberately: it belongs to 044, not to this story, and the plan's
trap 9 says to say so rather than edit across the line. Reordering another
story's assertion to reach a green run is the shape of change the outer loop
exists to refuse. It is reported here so the next reader does not read a red
gate on this branch as US3 having broken the roadmap scheduler.

## Before the change: the red run

`tests/test_build_verbs_take_an_epic_id.py` against the unmodified
`factory/cli/nouns/build.py`:

```
FAILED test_reset_resolves_the_graph_from_the_epic_id_without_temporal_history
FAILED test_unknown_epic_id_is_refused_naming_the_id_and_where_it_looked
FAILED test_every_live_epic_verb_takes_epic_id_as_its_first_positional
FAILED test_a_missing_graph_path_is_never_reinterpreted_as_an_epic_id
FAILED test_reset_archives_survivors_when_the_workflow_is_gone_from_temporal[epic-id]
5 failed, 2 passed in 0.67s
```

The two that passed red are the two that assert the **old** argument form still
works — `test_a_supplied_graph_path_is_still_accepted` and the `[graph-path]`
leg of the US3-S5 test. They are supposed to pass before and after; that is the
whole content of US3-S4.

## The concurrency fork (plan trap 8a)

US2 and US3 both edit `factory/cli/nouns/build.py` — US2 widens `_reset_epic`,
US3 rewrites the `reset` subparser and `reset_command` — and both declare
`depends_on: []`. **This story's answer: dispatch this epic at
`--max-concurrent-nodes 1`.** Not a `depends_on: [us2]` edge: `depends_on`
models what a story needs to *exist*, and US3 needs nothing from US2. The
contention is over one file, which is a scheduling fact rather than a graph one,
and encoding it as an edge would leave a false dependency in the compiled
artifact for every future re-derivation of this spec. The same decision is
stated in the test module's docstring, where the next person to edit either
region will meet it.

The two regions do not overlap: US2's edit is inside `_reset_epic`, which this
diff does not touch, and this diff's edits are in `reset_command`, the two new
helpers above it, and the `reset` subparser.
