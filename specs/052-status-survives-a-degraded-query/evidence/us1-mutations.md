# 052-US1 mutation battery

## The suite

    $ uv run pytest -q -p no:cacheprovider
    3218 passed, 47 skipped, 6 warnings in 325.68s (0:05:25)

(An earlier full run, before `test_an_epic_with_no_table_is_not_paced_as_a_finished_one`
was added in response to M10, read `3217 passed, 47 skipped, 6 warnings in
339.58s`. The difference is that one test.)

Cold cache — every `__pycache__` under the worktree purged and
`PYTHONDONTWRITEBYTECODE=1` set — because CPython validates a cached `.pyc` on
`(mtime-in-whole-seconds, size)` alone, and **swapping one exception class for
another preserves file size almost exactly**, which is precisely what this story
does. Two same-size mutants written inside one wall-clock second would otherwise
make the second run execute the first's bytecode, and it fails *toward green*.

Only `passed` and `skipped` are quoted. The warning count is not evidence: the
`SyntaxWarning` in this suite fires at compile time, so a warm cache reports
fewer of them on an identical tree.

### The skip count, declared

**47, against the plan's stated baseline of 44.** The three are not this diff
and not a hidden test. Every skip in the suite is a live-tier environment guard,
and all 47 come from the `tests/test_live_*` files:

| reason | count |
|---|---|
| `LITELLM_PROXY_URL` / `LITELLM_MASTER_KEY` absent (live proxy, judge, epic) | 30 |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` absent (live notify) | 9 |
| `FACTORY_SAMPLE_REPO` absent (live merge) | 6 |
| `Namespace ergane is not found` at `localhost:7233` (live capacity) | 3 |

The last row is the delta. `tests/test_live_capacity.py:158` skips when the
namespace it reads is unregistered, and this host's Temporal has only
`['default', 'factory', 'temporal-system']` — so three tests that *ran* when the
44 baseline was taken skip now. They are guarded on the environment, not on
anything in this diff, which touches three files (`factory/cli/status.py`, this
spec's evidence, `tests/test_ergane_status.py`) that none of the live-tier files
import. Worth an operator's attention as a separate matter: three live-capacity
tests are silently not running on this host.

`tests/test_ergane_status.py` contributes 37 tests and **zero skips**.

## The battery

One production edit at a time against a clean **committed** tree, over
`tests/test_ergane_status.py`. Every row purges `__pycache__` and runs under
`PYTHONDONTWRITEBYTECODE=1`; every row restores with `git checkout --` and then
asserts `git status --porcelain` empty — which lists **untracked** files, the
ones `checkout` does not remove — before and after. The **collected count is
recorded on every row**, because a run that collected nothing reads exactly like
a survivor.

| # | mutation | collected | result |
|---|---|---|---|
| M0 | **control — point at nothing**: a node id that does not exist | 0 | `1 warning in 0.18s` |
| M0b | **control — no edit at all** | 37 | `37 passed, 1 warning in 2.54s` |
| M1 | `_disposition`'s query guard loses `QUERY_REFUSED` (the `46c50f5` shape) | 37 | `4 failed, 33 passed, 1 warning in 2.49s` |
| M2 | `_running_epics`'s query guard loses `QUERY_REFUSED` | 37 | `4 failed, 33 passed, 1 warning in 2.51s` |
| M3 | `collect_floor`'s band loses `QUERY_REFUSED` — the backstop alone | 37 | `2 failed, 35 passed, 1 warning in 2.39s` |
| M4 | **trap 2** — `QUERY_REFUSED` becomes `(RPCError,)`, so only a test raising the client's real type can notice | 37 | `8 failed, 29 passed, 1 warning in 2.42s` |
| M5 | **FR-004** — `_disposition` guards the query with `Exception` | 37 | `4 failed, 33 passed, 1 warning in 2.32s` |
| M6 | **FR-002** — the refusal is caught but reported nowhere | 37 | `3 failed, 34 passed, 1 warning in 2.34s` |
| M7 | the roadmap section stops rendering the cause it was handed | 37 | `2 failed, 35 passed, 1 warning in 2.32s` |
| M8 | **FR-001** — a refusal is treated as an outage (`degraded`, exit 3) | 37 | `4 failed, 33 passed, 1 warning in 3.08s` |
| M9 | a refusing epic is dropped like a closed one instead of listed | 37 | `2 failed, 35 passed, 1 warning in 3.50s` |
| M10 | `_pace` stops skipping the epic with no table | 37 | `1 failed, 36 passed, 1 warning in 3.33s` |
| M11 | **FR-005** — transport is handled as a refusal | 37 | `10 failed, 27 passed, 1 warning in 3.18s` |

No survivors.

### M0, and why it is the first row rather than the last

    $ uv run pytest -q -p no:cacheprovider \
        "tests/test_ergane_status.py::test_this_node_id_does_not_exist"; rc=$?
    EXIT (before any pipe) = 4
    ERROR: not found: .../tests/test_ergane_status.py::test_this_node_id_does_not_exist
    1 warning in 0.18s

`1 warning in 0.18s` is what a run that executed **nothing** prints. It carries
no red, no count and no complaint on the summary line, so a battery that quoted
only that line would read every subsequent row as meaningful when the runner
might have been pointing at nothing at all. The collected count and the exit
code are what tell the two apart, and both are recorded above.

The exit code in that transcript was itself measured twice. The first reading
came from `pytest ... | tail -6; rc=$?`, which reported **0** — because `$?` was
`tail`'s status, not pytest's. Re-measured without the pipe it is **4**. That is
plan trap 7, made in the course of guarding against it.

### M4 is the trap-2 assertion

A test that defined its own `class FakeQueryFailed(RPCError)` and raised that
would pass against the *broken* code, because it inherits from the class the
broken code caught. M4 collapses `QUERY_REFUSED` to `(RPCError,)`: every test
that raises a hand-rolled `RPCError` subclass stays green, and only tests raising
the genuine `temporalio.client.WorkflowQueryFailedError` go red. Eight go red.

### M5 is what proves T004 can fail

`test_no_temporal_call_site_is_guarded_by_a_blanket_except` and its runtime
partner were both green on arrival — they forbid a repair, and the repair was
never made, so there was no moment at which they could have been red. M5 makes
the forbidden repair and they go red. Ability-to-fail proved by mutation rather
than claimed by history.

### The two rows that had to be corrected

**M9's first run collected 0** and reported `ERRORS`. Not a survivor — a defect
in the battery. The anchor `"# Not that event."` matched a *prefix* of a longer
comment line, so the inserted `continue` was spliced into the middle of it and
the module stopped parsing:

    E   SyntaxError: invalid syntax
    !!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!
    1 warning, 1 error in 0.20s

Re-anchored on the handler's whole body, M9 is red, and it kills two tests.

**M10 genuinely survived**: `36 passed`, whole suite green with `_pace`'s skip
removed. `_pace` filters out an epic that refused its query, because such an
epic has an empty node table and would otherwise be measured as `0 of 0 stories
remaining` — which renders identically to an epic that has finished every story,
in the one section an operator reads to judge how much work is left. That
behaviour had no test. `test_an_epic_with_no_table_is_not_paced_as_a_finished_one`
was written in response, the mutant re-run, and it now dies. The ordering is
recorded honestly: mutant → test → mutant dies, not a claim of red-first.
