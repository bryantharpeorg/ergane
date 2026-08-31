# Attempt report — US3, a reader can tell two dispatches apart

Evidence no gate can produce, committed as an artifact the diff contains
(constitution VIII). Tool output is pasted, not described.

## T023 — FR-010: the two things this epic may not change

FR-010 names the usage ledger and Temporal's retention. Checked over the whole
epic — US1's and US2's commits as well as this story's — because the
requirement binds every story, and `8f5f633` is the commit this epic branched
from.

```
$ git diff 8f5f633 --stat -- factory/usage/ specs/001-per-node-usage-tracking/
(no output)

$ git rev-parse 8f5f633:factory/usage/ledger.py
80107f7b5ec9b02a67fbb565757c6fe4310e8a49
$ git hash-object factory/usage/ledger.py
80107f7b5ec9b02a67fbb565757c6fe4310e8a49
$ git rev-parse 8f5f633:factory/usage/models.py
75a05d864aed2682390c80608a597766c577f4a6
$ git hash-object factory/usage/models.py
75a05d864aed2682390c80608a597766c577f4a6
$ git rev-parse 8f5f633:factory/usage/aggregate.py
d1b2d76e90924deef3501182a82e709181754db6
$ git hash-object factory/usage/aggregate.py
d1b2d76e90924deef3501182a82e709181754db6

$ git diff 8f5f633 | grep -cE "retention|RetentionPeriod"
0

$ git diff 8f5f633 --stat
 factory/cli/nouns/build.py                         |  39 +-
 factory/verify/models.py                           | 109 ++++++
 factory/verify/store.py                            | 355 +++++++++++++++--
 factory/workgraph/workflow.py                      |  48 ++-
 .../contracts/verification-store.sql               |  20 +-
 tests/test_117_dispatch_scoped_rows.py             | 413 ++++++++++++++++++++
 tests/test_117_row_names_its_builder.py            | 264 +++++++++++++
 tests/test_117_two_dispatches_read_apart.py        | 426 ++++++++++++++++++
 tests/test_escalation_record.py                    |   9 +-
 tests/test_interpreter.py                          |  15 +-
 tests/test_verify_store.py                         |  50 ++-
 11 files changed, 1693 insertions(+), 55 deletions(-)
```

Identical blobs for the ledger's three modules and no file of its package in
the epic's diff at all. Retention is stronger than unchanged: the epic's whole
diff contains no line mentioning it in either spelling, and a namespace's
retention period is not configured anywhere in this repository — it is a
property of the Temporal server the worker dials, which nothing here writes.
Every store this epic touches is the evidence store; the ledger is a separate
database with a separate writer, and this story adds no writer at all.

## T024 — the demonstration: what ran, and what did not

**The live half did not run, and could not be run from this node.** The plan's
§ *Verification the operator will run* starts with `build start`, which
dispatches real agents through the proxy. A node's environment carries no
proxy credentials by construction (constitution V), and the environment script
refuses here for the same reason it refused 116's:

```
$ bash scripts/ergane-env.sh
ERROR: sops not on PATH
$ env | grep -icE 'litellm|anthropic|proxy'
0
```

There is nothing to ferry to the operator about it: the answer would have to be
a credential, and a credential is the one thing that may not enter a node. A
node dispatching an epic is also outside this slice by any reading.

### The half that did run: two real dispatches, the real recording path

`build reset` plus a second `build start` produces two runs of the interpreter
over one node, and that is the fact the reading turns on. Two runs of the real
`EpicWorkflow` against a scripted world give exactly that — no proxy, no agent,
no repository — with the dispatch identity, the persona/alias/route resolution
and `upsert_result` all the production ones. The first build spends three
attempts (the killed one), the re-dispatch spends two:

```
$ uv run python /tmp/us3_demo.py
dispatch 1 = 6bcc72e7-401a-45a0-a3c7-cf76f80dd9b5
dispatch 2 = 4cbcb5bf-76d3-437c-bea3-21fb52beaf04

5 rows for us1, 2 dispatches:
  attempt 1  FAIL  implementer  implementer-alias  subscription  dispatch 6bcc72e7-401a-45a0-a3c7-cf76f80dd9b5
  attempt 2  FAIL  implementer  implementer-alias  subscription  dispatch 6bcc72e7-401a-45a0-a3c7-cf76f80dd9b5
  attempt 3  PASS  implementer  implementer-alias  subscription  dispatch 6bcc72e7-401a-45a0-a3c7-cf76f80dd9b5
  attempt 1  FAIL  implementer  implementer-alias  subscription  dispatch 4cbcb5bf-76d3-437c-bea3-21fb52beaf04
  attempt 2  PASS  implementer  implementer-alias  subscription  dispatch 4cbcb5bf-76d3-437c-bea3-21fb52beaf04
```

Five rows where before this epic there would have been three, both attempt-one
rows present, each naming its dispatch, its persona and its model. The last
line of the reading is `node_history` and `dispatch_groups` — the plan's step 3
— and it is grouped: the killed build's three attempts, then the re-dispatch's
two, and not the interleaved `1, 1, 2, 2, 3` that ordering by attempt gives
over the same rows.

The same store through the CLI, which is US3-S2:

```
$ ERGANE_VERIFICATION_DB_PATH=/tmp/us3-demo/verification.db \
    uv run ergane build attempts demo-loans
epic demo-loans  9 verifications
us1  dispatch 1 of 2  6bcc72e7-401a-45a0-a3c7-cf76f80dd9b5
us1  attempt 1  PHASE  FAIL  judge input: not recorded
us1  attempt 2  PHASE  FAIL  judge input: not recorded
us1  attempt 3  PHASE  PASS  judge input: not recorded
us1  dispatch 2 of 2  4cbcb5bf-76d3-437c-bea3-21fb52beaf04
us1  attempt 1  PHASE  FAIL  judge input: not recorded
us1  attempt 2  PHASE  PASS  judge input: not recorded
us2  dispatch 1 of 2  6bcc72e7-401a-45a0-a3c7-cf76f80dd9b5
us2  attempt 1  PHASE  PASS  judge input: not recorded
us2  dispatch 2 of 2  4cbcb5bf-76d3-437c-bea3-21fb52beaf04
us2  attempt 1  PHASE  PASS  judge input: not recorded
us3  dispatch 1 of 2  6bcc72e7-401a-45a0-a3c7-cf76f80dd9b5
us3  attempt 1  PHASE  PASS  judge input: not recorded
us3  dispatch 2 of 2  4cbcb5bf-76d3-437c-bea3-21fb52beaf04
us3  attempt 1  PHASE  PASS  judge input: not recorded
```

### What the demonstration found, which the tests had not

Both runs record inside one second, and `finished_at` is stamped to the second.
Every dispatch therefore tied on the clock, the ordering fell through to its
last term — the dispatch itself — and the **second** build was printed first,
because `064a…` sorts before `8330…`:

```
dispatch 1 = 8330015d-5634-4618-a036-461f5fb2b600
dispatch 2 = 064a8569-032c-47aa-b310-c45fe03dd1ba

5 rows for us1, 2 dispatches:
  attempt 1  FAIL  implementer  implementer-alias  subscription  dispatch 064a8569-032c-47aa-b310-c45fe03dd1ba
  attempt 2  PASS  implementer  implementer-alias  subscription  dispatch 064a8569-032c-47aa-b310-c45fe03dd1ba
  attempt 1  FAIL  implementer  implementer-alias  subscription  dispatch 8330015d-5634-4618-a036-461f5fb2b600
  attempt 2  FAIL  implementer  implementer-alias  subscription  dispatch 8330015d-5634-4618-a036-461f5fb2b600
  attempt 3  PASS  implementer  implementer-alias  subscription  dispatch 8330015d-5634-4618-a036-461f5fb2b600
```

Ordering a tie by uuid is not an ordering. The insertion order of a group's
first row is now consulted where the clock has no answer — last, never first,
which is what plan trap 7 forbids — and
`test_two_dispatches_the_clock_cannot_separate_still_read_in_order` holds it
there. The run pasted above is from after that fix, and its two uuids sort the
other way round from the builds they name (`4cbc…` < `6bcc…`, dispatch 2 before
dispatch 1) while the reading still puts the older build first: the tie-break
is doing the work, and it is doing it in the right direction.

### What the operator still has to run

With `eval "$(scripts/ergane-env.sh)"` in a shell that has `sops`, the plan's
three steps against a real one-story spec: `build start`, `build reset`, `build
start` again, then `ergane build attempts <epic>`. The demonstration succeeds
when that reading shows the same two headings over the same node with the two
builds' attempts under each. The claim not evidenced here is that a real
`build reset` leaves the first dispatch's rows in place — this report shows two
real interpreter runs and one store, not a reset between them.
