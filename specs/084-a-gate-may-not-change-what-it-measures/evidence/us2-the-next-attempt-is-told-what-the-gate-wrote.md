# 084-US2 evidence — SC-007, SC-008

Every block below is pasted verbatim from a run in this worktree on 2026-08-22,
against the code this story's diff contains. The driver imports the committed
fixtures rather than restating them, so what produced the evidence is the same
builder code the tests assert on — `dirtied_gate` and `attempt` from
`tests/test_the_next_attempt_is_told_what_the_gate_wrote.py`, `evidence_section`
from `tests/test_prompt_output_check.py`, and `tests/test_notify.py`'s
`make_gate`, `make_result` and `make_escalation`:

```python
# abridged; the driver is these four calls over the committed builders
from tests.test_prompt_output_check import evidence_section
from tests.test_the_next_attempt_is_told_what_the_gate_wrote import attempt, dirtied_gate

print(evidence_section(attempt(dirtied_gate())))               # SC-007
print(_gate_line(dirtied_gate()), _gate_line(notify_gate()))   # SC-008
```

The gate in these pastes is the field report's own shape: `compileall`, exiting
0, writing bytecode into a repository whose ignore rules never mentioned
`__pycache__/`. Paths carry `PLANTED-` markers so a reader can tell rendered
evidence from invented prose at a glance.

Fences here are four backticks, because the pasted prompt carries three-backtick
fences of its own.

## SC-007 — the retry prompt for an attempt whose gate dirtied the worktree

The gate's own tail is `Listing 'factory'...` — a clean, successful run. Nothing
in it says why the attempt failed, and before this story nothing else did
either. The second block is what US2 adds: the gate's name, its command, the
reason its exit code did not save it, and every path it wrote, quoted rather
than described.

````
## Prior attempt evidence

Earlier attempts at this node did not pass. Their evidence is reproduced
verbatim, oldest first — the last block is the attempt just made. Read it
as what actually happened, not as a summary of it:

### Attempt 1 — terminated `completed`, verdict FAIL

Gate `compile` (`uv run python -m compileall factory`) — DIRTIED_WORKTREE, exit 0:

```text
Listing 'factory'...
```

Gate `compile` (`uv run python -m compileall factory`) changed the node worktree while it ran, and the judge's patch is assembled from that worktree afterwards — so this gate edited the evidence it was scored on, which is why it did not pass despite its exit code. Fix the gate command, not the code it measured. Every path it wrote:

```text
factory/PLANTED-WRITE-01/__pycache__/models.cpython-313.pyc
factory/PLANTED-WRITE-02/__pycache__/gates.cpython-313.pyc
```
````

That section is the last of the assembled prompt, in the place it already had:

````
prompt bytes: 6378
evidence section bytes: 864
sections, in order:
  ## Role and scope
  ## The inner loop (advisory)
  ## The outer loop (authoritative)
  ## If you are blocked, ask the operator
  ## Story
  ## Plan
  ## Summary
  ## Technical Context
  ## Your task slice
  ## Phase 2: User Story 1 - Borrow a book (Priority: P1)
  ## Phase 9: User Story 3 - Reserve a book (Priority: P3)
  ## Prior attempt evidence
````

### Attribution — two dirtied gates, each with its own paths

`worktree_writes` is attributed to a gate by the name it was declared under
(084 FR-003), and this is what that attribution is *for*: "which command do I
fix?" is the first question the next attempt has to answer. The block renders
inside the gate loop, beside the gate that wrote.

````
## Prior attempt evidence

Earlier attempts at this node did not pass. Their evidence is reproduced
verbatim, oldest first — the last block is the attempt just made. Read it
as what actually happened, not as a summary of it:

### Attempt 1 — terminated `completed`, verdict FAIL

Gate `compile` (`uv run python -m compileall factory`) — DIRTIED_WORKTREE, exit 0:

```text
Listing 'factory'...
```

Gate `compile` (`uv run python -m compileall factory`) changed the node worktree while it ran, and the judge's patch is assembled from that worktree afterwards — so this gate edited the evidence it was scored on, which is why it did not pass despite its exit code. Fix the gate command, not the code it measured. Every path it wrote:

```text
factory/PLANTED-WRITE-01/__pycache__/models.cpython-313.pyc
factory/PLANTED-WRITE-02/__pycache__/gates.cpython-313.pyc
```

Gate `docs` (`uv run mkdocs build`) — DIRTIED_WORKTREE, exit 0:

```text
INFO - Building documentation...
```

Gate `docs` (`uv run mkdocs build`) changed the node worktree while it ran, and the judge's patch is assembled from that worktree afterwards — so this gate edited the evidence it was scored on, which is why it did not pass despite its exit code. Fix the gate command, not the code it measured. Every path it wrote:

```text
docs/PLANTED-OTHER-GATE-04/generated.md
```
````

### A gate that failed *and* wrote reports both

`_to_result` keeps the command's own verdict as the headline — a FAIL is the
more actionable one — and still records the writes (084 FR-005). Note the
headline below is `FAIL, exit 1`, not `DIRTIED_WORKTREE`: the block is keyed on
the record's paths rather than on the status, so the paths are not lost for the
gate whose next attempt is most likely to trip over them again.

````
## Prior attempt evidence

Earlier attempts at this node did not pass. Their evidence is reproduced
verbatim, oldest first — the last block is the attempt just made. Read it
as what actually happened, not as a summary of it:

### Attempt 1 — terminated `completed`, verdict FAIL

Gate `test` (`uv run pytest -q`) — FAIL, exit 1:

```text
E   assert loans == 1
```

Gate `test` (`uv run pytest -q`) changed the node worktree while it ran, and the judge's patch is assembled from that worktree afterwards — so this gate edited the evidence it was scored on, which is why it did not pass despite its exit code. Fix the gate command, not the code it measured. Every path it wrote:

```text
factory/verify/PLANTED-REWRITE-03/formatted.py
```

Judge — RETRY:

```text
US1-S2 is not covered.
```
````

### The control — a failing gate that wrote nothing gains nothing

No block, no empty fence, no heading. A green gate's output is noise in a prompt
whose job is to say what went wrong (`factory/workgraph/prompt.py:701-703`), and
so is a heading over nothing.
`test_a_clean_attempt_renders_byte_identically_to_before_this_story` asserts the
whole section byte-for-byte against the golden captured before `_attempt_block`
was ever touched, so this is equality rather than a spot check.

````
## Prior attempt evidence

Earlier attempts at this node did not pass. Their evidence is reproduced
verbatim, oldest first — the last block is the attempt just made. Read it
as what actually happened, not as a summary of it:

### Attempt 1 — terminated `completed`, verdict FAIL

Gate `test` (`uv run pytest -q`) — FAIL, exit 1:

```text
E   assert loans == 1
```
````

## SC-008 — the operator-facing gate line, dirtied and clean

`concurrent_gates` is rendered on this line for exactly this reason: a marker
that lives only in the evidence store is one the operator never sees. The
operator deciding RETRY or KILL on a `DIRTIED_WORKTREE` verdict is asking "what
did it write", and the gate's quoted output tail cannot answer — the gate
exited 0.

Both control lines are byte-identical to their pre-story spelling. The contended
line shows both markers rendering together: a gate can be contended and dirty,
and neither fact substitutes for the other. The last line shows the message
budget honoured out loud — three paths named, the remaining six counted rather
than silently cut, because silent truncation would read as "that is all of
them".

````
dirtied:              gate compile: DIRTIED_WORKTREE (exit 0, 12.5s) [wrote 2 path(s): factory/PLANTED-WRITE-01/__pycache__/models.cpython-313.pyc, factory/PLANTED-WRITE-02/__pycache__/gates.cpython-313.pyc]
control (clean):      gate test: PASS (exit 0, 12.5s)
control (failed):     gate test: FAIL (exit 1, 12.5s)
contended + dirty:    gate compile: DIRTIED_WORKTREE (exit 0, 12.5s) [contended: 1 peer(s)] [wrote 2 path(s): factory/PLANTED-WRITE-01/__pycache__/models.cpython-313.pyc, factory/PLANTED-WRITE-02/__pycache__/gates.cpython-313.pyc]
many paths:           gate compile: DIRTIED_WORKTREE (exit 0, 12.5s) [wrote 9 path(s): factory/__pycache__/module_0.cpython-313.pyc, factory/__pycache__/module_1.cpython-313.pyc, factory/__pycache__/module_2.cpython-313.pyc, +6 more]
````

### The same line where the operator actually meets it

Rendered through `render_history` into the escalation body, beside a passing
gate that carries no marker:

````
⚠️ Verification escalation
epic: epic-7
node: node-3

Attempt 1 — FAIL
  gate lint: PASS (exit 0, 12.5s)
  gate compile: DIRTIED_WORKTREE (exit 0, 12.5s) [wrote 2 path(s): factory/PLANTED-WRITE-01/__pycache__/models.cpython-313.pyc, factory/PLANTED-WRITE-02/__pycache__/gates.cpython-313.pyc]
── compile output ──
Listing 'factory'...
Compiling 'factory/verify/gates.py'...


What each button does:
RETRY (🔁 Retry the node) — node: one more attempt, on the tree this one left behind. epic: unchanged — it keeps dispatching.
KILL (🛑 Kill the node) — node: ends KILLED, its branch preserved. epic: keeps dispatching, but every node waiting on this one is locked out and ends KILLED with it, undispatched.
PAUSE_EPIC (⏸️ Pause the epic) — node: ends parked, not killed — nothing waiting on it is locked out. epic: stops dispatching until you resume it; the undispatched nodes keep their place and run then.

No answer by 2026-08-04T12:00:00Z applies the default: KILL the node.
````

## The third renderer, decided rather than discovered

`factory/mergequeue/messages.py:130-141` `_gate_status` renders a `GateResult`
into the merge-queue PR body and takes no marker in this story, deliberately.
`render_pr_body` is documented as "the PR body for a passing node"
(`factory/mergequeue/messages.py:66`) and `gates_passed`
(`factory/verify/models.py:501-515`) refuses any status that is not `PASS`, so a
`DIRTIED_WORKTREE` gate cannot appear in a landed PR's gate list at all. A
marker there would be unreachable code wearing the costume of coverage.
`test_a_dirtied_gate_never_reaches_a_landed_pr_body` pins that premise instead
of the absent branch, so if it ever stops holding this suite says so rather than
the PR body going quietly silent.

## The suite this story added

````
============================= test session starts ==============================
test_the_retry_prompt_names_the_gate_its_command_and_every_path_it_wrote PASSED [  5%]
test_the_paths_are_quoted_verbatim_not_summarised PASSED [ 11%]
test_each_gate_renders_its_own_writes_and_no_other_s PASSED [ 17%]
test_each_attempt_renders_its_own_writes_and_no_other_s PASSED [ 23%]
test_a_gate_that_failed_and_also_wrote_reports_both PASSED [ 29%]
test_the_writes_sit_with_their_gate_and_before_the_judge PASSED [ 35%]
test_the_prompt_does_not_send_the_next_attempt_at_the_manifest PASSED [ 41%]
test_a_clean_attempt_renders_byte_identically_to_before_this_story PASSED [ 47%]
test_a_passing_gate_that_somehow_carried_writes_is_still_not_quoted PASSED [ 52%]
test_a_failing_gate_that_wrote_nothing_gains_no_empty_block PASSED [ 58%]
test_the_operator_gate_line_carries_the_writes_marker PASSED [ 64%]
test_the_marker_reaches_the_escalation_message_not_only_the_helper PASSED [ 70%]
test_a_clean_gate_line_carries_no_marker PASSED [ 76%]
test_both_markers_render_together_when_both_were_recorded PASSED [ 82%]
test_a_gate_that_wrote_many_paths_names_some_and_counts_the_rest PASSED [ 88%]
test_a_dirtied_gate_never_reaches_a_landed_pr_body PASSED [ 94%]
test_the_planted_gate_is_the_one_us1_would_actually_produce PASSED [100%]
============================== 17 passed in 0.03s ==============================
````

## Proved by mutation, not by assertion count

A rendering test is the shape most prone to passing whatever the renderer does,
so each property was checked by breaking the production code five ways and
watching which tests noticed. Verbatim, reverting between each:

````
=== M1: the block names the gate but not the paths ===
FAILED test_the_retry_prompt_names_the_gate_its_command_and_every_path_it_wrote
FAILED test_the_paths_are_quoted_verbatim_not_summarised
FAILED test_each_gate_renders_its_own_writes_and_no_other_s
FAILED test_each_attempt_renders_its_own_writes_and_no_other_s
FAILED test_a_gate_that_failed_and_also_wrote_reports_both
FAILED test_the_writes_sit_with_their_gate_and_before_the_judge
6 failed, 23 passed in 0.08s

=== M2: the block renders for every failing gate, writes or not ===
FAILED test_a_clean_attempt_renders_byte_identically_to_before_this_story
FAILED test_a_failing_gate_that_wrote_nothing_gains_no_empty_block
FAILED test_a_passing_output_check_renders_byte_identically_to_today
3 failed, 26 passed in 0.08s

=== M3: the block pools the attempt's writes instead of the gate's ===
FAILED test_each_gate_renders_its_own_writes_and_no_other_s
1 failed, 28 passed in 0.07s

=== M4: the operator's gate line drops the marker ===
FAILED test_the_operator_gate_line_carries_the_writes_marker
FAILED test_the_marker_reaches_the_escalation_message_not_only_the_helper
FAILED test_both_markers_render_together_when_both_were_recorded
FAILED test_a_gate_that_wrote_many_paths_names_some_and_counts_the_rest
4 failed, 25 passed in 0.09s

=== M5: the operator's marker clips silently ===
FAILED test_a_gate_that_wrote_many_paths_names_some_and_counts_the_rest
1 failed, 28 passed in 0.08s

=== reverted ===
29 passed in 0.05s
````

M1 is the one that matters. It is the renderer this story could most plausibly
have shipped — an honest-looking sentence naming the gate and counting its
writes — and it satisfies "the prompt says something about worktree writes"
completely. Six tests refuse it, because a count is a description and a path is
an instruction. M2 is the control's half: byte parity is what notices a block
rendered over a gate that wrote nothing, and it fails
`tests/test_prompt_output_check.py`'s golden as well as this story's, which is
the same corpus saying the same thing twice. M3 is attribution — one pooled list
reads as plausible until two gates write different paths. M5 is the smallest and
the least obvious: a marker that clips without saying so reads as a complete
list, which is the one thing a marker may not do.
