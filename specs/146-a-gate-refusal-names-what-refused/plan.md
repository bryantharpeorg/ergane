# Implementation Plan: a gate refusal names what refused

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## What already exists, and where

**One gate, one result, and the result's whole account of a failure is a string.**
`factory/verify/models.py:362` — `GateResult` is frozen and additive-by-default;
its fields end with three that were each added the way this spec adds more:

```python
    name: str
    command: str
    status: GateStatus
    exit_code: int | None
    duration_s: float
    output_tail: str
    concurrent_gates: int = 0
    worktree_writes: tuple[str, ...] = ()
    writes_declared: bool = False
```

`concurrent_gates` (007 FR-005), `worktree_writes` and `writes_declared` (084)
are all defaulted, all documented in the class docstring, and all round-tripped
through the store. Copy that pattern exactly; there is no other pattern here.

**The single point every executor's outcome becomes a result** is
`factory/verify/gates.py:1583` — `_to_result`, and it already does one derivation
of this shape. The tail is finalised at `factory/verify/gates.py:1634` —
`_to_result`, annotated at `factory/verify/gates.py:1652` — `_to_result`, and
handed to the constructor at `factory/verify/gates.py:1655` — `_to_result`:

```python
    tail = tail_output(outcome.output)
    if snapshot_error:
        note = f"[worktree snapshot failed: {snapshot_error}]"
        tail = tail_output(f"{tail}\n{note}" if tail else note)
    ...
    if status in (GateStatus.FAIL, GateStatus.TIMEOUT):
        tail = tail_output(annotate_install_advice(tail))
```

The parse belongs after that last line, over `tail`, so the names are a fact
about the string the row keeps (trap 3). `_run_watched`
(`factory/verify/gates.py:1511` — `_run_watched`) says in its own docstring why
the derivation goes here rather than in a backend: the wrapper is "the single
line `SubprocessGateExecutor`, `BwrapGateExecutor` and production's
`_HeartbeatingExecutor` … all pass through, and a check inside any one of them is
bypassed by the other two."

**The precedent for the recogniser, argued and paid for.**
`factory/verify/gate_annotation.py:113` — `matched_install_signature` is 137 lines
of module whose whole thesis is "a signature, not a guess", with the measured
failure that produced it written into the module docstring: a loose match over
"install" or "not found" "annotates every failing gate with a `HOME` lecture, and
a retry prompt full of confident irrelevant advice is the failure US1 exists to
avoid". `factory/verify/gate_annotation.py:125` — `annotate_install_advice`
returns its argument object unchanged on the unmatched path, deliberately, so
"unchanged" is a property of the code and not a coincidence about whitespace.
Both decisions transfer whole to check names.

**Where the evidence is persisted, and how a new field survives an old row.**
`factory/verify/store.py:1091` — `_gate_to_dict` and
`factory/verify/store.py:1105` — `_gate_from_dict` are a JSON codec pair, not a
schema, so a new field needs no migration — only a `data.get(...)` with a
documented reading of absence:

```python
        "output_tail": gate.output_tail,
        "concurrent_gates": gate.concurrent_gates,
        "worktree_writes": list(gate.worktree_writes),
        "writes_declared": gate.writes_declared,
```

**What the operator actually reads.** `factory/workgraph/workflow.py:860` —
`epic_status` returns `history=tuple(record.history)` at
`factory/workgraph/workflow.py:895` — `epic_status`, and that history is
`factory/verify/models.py:1245` — `AttemptRecord`:

```python
    attempt: int
    persona: str
    verdict: OverallVerdict
    judge_outcome: JudgeOutcome | None = None
    model_alias: str = UNRESOLVED_MODEL_ALIAS
    pre_agent: bool = False
    credential_source: str | None = None
```

`model_alias`'s own docstring states the defaulting rule this spec's field
inherits: it defaults "because a history recorded before this field existed
genuinely does not know, and a default that guessed would be indistinguishable
from a reading."

**Which surface the refusal line actually reaches, and the near miss beside it.**
The record lands in `nodes.<id>.history`, and only the JSON view prints that:
`factory/cli/nouns/build.py:1188` — `_query_status` prints the query document
verbatim, which is why FR-006 says `ergane build status --json` and not
`ergane build status`. The human render is
`factory/cli/nouns/build.py:464` — `render_status`, one line per node plus
`factory/cli/nouns/build.py:738` — `_attempt_note_lines`, the per-attempt operator
sentence 095-US1 added for exactly this kind of reading. **That is the near miss
this spec deliberately does not use.** `attempt_note` is the *latest* attempt's
sentence, written where the line above cannot say the cause and read off the node
document rather than off an `AttemptRecord`; a refusal written there would be
overwritten by the next attempt and would carry no per-attempt history, which is
precisely the record the 2026-08-25 measurement went looking for. US2 writes the
refusal on the record, per attempt, and adds no line to `render_status`. An
implementer who finds `attempt_note` and wires the refusal into it satisfies no
scenario in this spec and breaks US2-S4's per-attempt claim.

**The four append sites, and why the fourth is different.** `AttemptRecord` is
constructed at `factory/workgraph/workflow.py:2041` — `_run_node` (the
unanswered-question FAIL — **no verification result exists there**),
`factory/workgraph/workflow.py:2096` — `_run_node` (the main loop),
`factory/workgraph/workflow.py:2886` — `_apply_external_completion_if_present`
(the operator hand-back) and `factory/workgraph/workflow.py:4018` —
`_recovery_attempt` (the conflicted re-sync). The three with a `result` in scope
take the refusal line; the first does not. FR-007.

**The gate line the operator reads in an escalation** is
`factory/notify/messages.py:581` — `_gate_line`, and it already carries two
markers appended the way this spec appends more:

```python
    if gate.concurrent_gates:
        line += f" [contended: {gate.concurrent_gates} peer(s)]"
    ...
    if gate.worktree_writes:
        written = gate.worktree_writes
        line += f" [wrote {len(written)} path(s): {_writes_marker(written)}]"
```

It is called from `factory/notify/messages.py:529` — `_render_attempt`, which
quotes a non-PASS gate's tail beneath it at `factory/notify/messages.py:536` —
`_render_attempt`.

**The manifest refuses repetition today, twice over.**
`factory/verify/factory_yaml.py:328` — `_read_gates` requires each gate value to
be a non-empty command string — there is no object form on which a count could
hang — and `factory/verify/factory_yaml.py:269` — `_reject_unknown_keys` refuses
any top-level key outside the version's known set, choosing it at
`factory/verify/factory_yaml.py:270` — `_reject_unknown_keys`. The new key goes
in `_V2_TOP_LEVEL_KEYS` (`factory/verify/factory_yaml.py:134`) and nowhere else
(trap 2).

**The reader to copy is `timeouts:`, field for field.**
`factory/verify/factory_yaml.py:397` — `_read_timeouts` is the exact shape FR-016
and FR-017 want — sparse, gate-keyed, and cross-checked against the declared
gates:

```python
    for name, seconds in timeouts.items():
        if name not in gates:
            raise FactoryConfigError(
                "timeouts",
                f"sets a timeout for {name!r}, which this manifest does not "
                f"declare as a gate; declared gates are {_names(gates)}",
                source=source,
            )
        if type(seconds) is not int or seconds <= 0:
```

Note `type(seconds) is not int` rather than `isinstance`: YAML spells booleans
`true`, and `isinstance(True, int)` is true, so a loose check would read
`runs: {test: true}` as a declaration. It is called from the reader list at
`factory/verify/factory_yaml.py:216`, which is where the new reader belongs, and
`FactoryConfig` is at `factory/verify/models.py:291` — `FactoryConfig` with
`gates` at `factory/verify/models.py:310` — `FactoryConfig`.

**The runners are near-identical twins, both iterate a mapping, and both already
take an optional gate-keyed view of exactly the shape US3 needs.**
`factory/verify/gates.py:1416` — `_run_gate_list` declares
`writes_view: Mapping[str, bool] | None = None` at
`factory/verify/gates.py:1421` — `_run_gate_list` and loops at
`factory/verify/gates.py:1447` — `_run_gate_list`;
`factory/verify/gates.py:1467` — `_run_gate_list_from_config` reads the same fact
off the config object at `factory/verify/gates.py:1480` —
`_run_gate_list_from_config` and loops at
`factory/verify/gates.py:1491` — `_run_gate_list_from_config`:

```python
    # `getattr` rather than an attribute read: this runner is also handed
    # config objects a caller built, and a shape that predates 084 declares
    # nothing rather than failing here.
    declared = dict(getattr(config, "writes", None) or {})
```

That comment is why US3 can land before US4 without a manifest key existing:
the config-driven runner reads its repetition view the same defensive way, so a
`FactoryConfig` that predates US4 declares nothing rather than raising.
Repetition is a loop *inside* one entry — a mapping cannot hold one name twice —
and both bodies call `_run_watched`, which is where the snapshot chain lives
(trap 10).

**Which runner a repository takes is decided by whether its worktree carries a
parser**, at `factory/verify/gates.py:1289` — `run_gates`, and the accepted shape
carries three fields (`factory/verify/gates.py:205` — `_AcceptedConfig`) whose
docstring is the warning trap 1 repeats:

```python
    "The subset the runner consumes" is the whole hazard: a field the manifest
    parser reads and the parser CLI emits still arrives here as nothing unless
    it is named. `writes` is carried for that reason (084 FR-012) — the runner
    this shape feeds is the one a worktree carrying its own parser selects,
    which is every Ergane node, so a declaration that stopped at
    `FactoryConfig` would be parsed, stored, emitted and never read.
```

The emitter needs no edit: `factory/verify/factory_yaml.py:1129` — `_main` prints
`json.dumps(dataclasses.asdict(config))` at
`factory/verify/factory_yaml.py:1152` — `_main`, which carries every field of
`FactoryConfig` automatically. The reader does:
`factory/verify/gates.py:1045` — `_interpret_candidate` picks three keys by name
at `factory/verify/gates.py:1076` — `_interpret_candidate` and drops the rest.
And the hand-off does: `factory/verify/gates.py:1292` — `run_gates` lifts
`writes_view` off the acceptance and `factory/verify/gates.py:1298` — `run_gates`
passes it on. 084's own SC-011 is that mutation: delete that one argument and
eleven of its twelve tests still pass.

**The near miss with the right name.** The `gate_contradictions` column at
`factory/verify/store.py:241`, migrated at `factory/verify/store.py:622`, belongs
to `factory/verify/models.py:706` — `detect_gate_contradictions`, which matches
judge findings against gates *this attempt* recorded PASS. Judge-versus-
measurement inside one execution. Reuse its shape, never its column (trap 8).

**The verdict this spec may not move** is
`factory/verify/models.py:950` — `gates_passed`, an `all(...)` over statuses,
composed from `factory/verify/models.py:73` — `GateStatus` (five members) and
`factory/verify/models.py:114` — `OverallVerdict` (two).

## Traps

**Trap 1 — The candidate-parser path is the one every Ergane node takes, and it
carries only the fields it names.** FR-019. `factory/verify/gates.py:1289` —
`run_gates` selects the candidate path when `<worktree>/factory/verify/
factory_yaml.py` exists, which is true of every node this factory dispatches
against itself. The emitter is automatic, which is exactly what makes this trap
expensive: an implementer adds `runs` to `FactoryConfig`, sees `asdict` carry it
into the protocol JSON, reasons that the protocol is generic, and stops. It is
not generic. `factory/verify/gates.py:1076` — `_interpret_candidate` reads
`gates`, `timeouts` and `writes` by name and discards everything else, and
`factory/verify/gates.py:205` — `_AcceptedConfig` declares exactly those three.
There is a second, quieter half: even a field the interpreter accepts is inert
unless `factory/verify/gates.py:1298` — `run_gates` passes it on, which is 084's
own SC-011 mutation — remove that argument and eleven of twelve tests stay green.
The declaration would then be parsed, refused-on-v1, stored, emitted and never
read. US4-S4 exists to make a test that only drives the in-process configuration
insufficient.

**Trap 2 — Register `runs:` in `_V2_TOP_LEVEL_KEYS` only, and the reader you are
copying registers its key in the other tuple.** FR-018.
`factory/verify/factory_yaml.py:270` — `_reject_unknown_keys` picks the known-set
by version. `timeouts` — whose reader is the model for FR-016 — lives in
`_TOP_LEVEL_KEYS` (`factory/verify/factory_yaml.py:109`), the **v1** list, so
copying the pattern wholesale widens v1, and every other US4 test still passes
because only US4-S3's paired test asserts the v1 refusal. Registering it anywhere
else costs more than FR-018: `_KNOWN_KEYS` (`factory/cli/init.py:511`) is
literally `_V2_TOP_LEVEL_KEYS`, so the right tuple makes `ergane init` carry the
key forward and rewrite it with **no edit to `factory/cli/init.py` at all**, and
any other tuple makes `ergane init` refuse every manifest that declares it. That
is 120's defect reproduced from the other side.

**Trap 3 — Parse the recorded tail, never `outcome.output`.** FR-003, US1-S4. The
untruncated output is not evidence; nothing keeps it. The row keeps
`output_tail`, and the store, the judge, the retry prompt and the escalation
message all carry that. A name parsed from the full output but cut out of the
tail is a name the operator cannot find anywhere, which is a smaller version of
the defect this spec is fixing. Parse after
`factory/verify/gates.py:1652` — `_to_result`, so the annotation is already
folded in and the tail is final.

**Trap 4 — The derivation goes in `_to_result`, not in an executor.** FR-003,
US1-S6. Three executors produce outcomes and only one function turns them into
results. `factory/verify/gates.py:1511` — `_run_watched` makes this argument
about `backend.run` in its own docstring, and
`factory/verify/gates.py:1652` — `_to_result` is where the tree already applies a
tail derivation for the same reason. An implementer who puts the parse in
`SubprocessGateExecutor` will have green tests and no names under bwrap, which is
where production runs.

**Trap 5 — A signature, not a guess.** FR-002, US1-S2.
`factory/verify/gate_annotation.py:113` — `matched_install_signature` already paid
for this lesson and wrote the receipt into its module docstring. A pattern over
"failed" matches a green suite that prints the word in a test name, a linter's
own summary, and a compiler's prose. Name the runner and pin the exact shape it
prints against real committed output; where nothing matches, record nothing. The
temptation is strongest for the second and third runners — resist adding one you
cannot paste real output for.

**Trap 6 — A new import in `factory/workgraph/workflow.py` must go inside the
passthrough block.** FR-007. `with workflow.unsafe.imports_passed_through():`
opens at `factory/workgraph/workflow.py:119` and every non-stdlib import in that
module is inside it. An import added at the top of the file compiles, passes
every unit test, and fails inside Temporal's workflow sandbox at worker boot —
green suite, dead worker, and the failure surfaces as an epic that will not
start. Add the shared derivation's import beside the other
`from factory.verify...` lines in that block.

**Trap 7 — There are four append sites, the fourth must stay empty, and the
diff you will read as the pattern populated only two.** FR-007, FR-009, US2-S4,
US2-S7. The sites are `factory/workgraph/workflow.py:2041` — `_run_node`,
`factory/workgraph/workflow.py:2096` — `_run_node`,
`factory/workgraph/workflow.py:2886` — `_apply_external_completion_if_present`
and `factory/workgraph/workflow.py:4018` — `_recovery_attempt`. The first has no
verification result — it is the FAIL an unanswered operator question burns — and
must carry no refusal line. Commit `ed9aa51` (125-US1) added `credential_source`
and populated **two** of the four, for reasons specific to that field; an
implementer who reads that diff as "the pattern" will skip the hand-back path,
pass every test that only drives the main loop, and leave a hole exactly where
an operator most wants an answer. And the field must be **defaulted**:
`AttemptRecord` is replayed workflow state, and a required field breaks every
history recorded before it, which presents as `ergane build status` degrading to
a query refusal rather than as a test failure.

**Trap 8 — `gate_contradictions` is the near miss with the right name; reuse the
shape, not the column.** FR-013. The column at `factory/verify/store.py:241` and
its migration at `factory/verify/store.py:622` are 116-US3's, and
`factory/verify/models.py:706` — `detect_gate_contradictions` fills it with
judge-versus-measurement disagreements inside one execution. Writing this spec's
execution-versus-execution disagreement into the same column makes two different
facts indistinguishable in the store and corrupts 116's own reading of it. The
disagreement is two defaulted fields on `GateResult`, serialised through
`factory/verify/store.py:1091` — `_gate_to_dict`. No schema migration is needed
and none should be written.

**Trap 9 — Do not make a disagreement fail a passing gate.** FR-015.
`factory/verify/models.py:950` — `gates_passed` is an `all(...)` over statuses and
must stay one. The temptation is to make the disagreement "count" by failing a
PASS row that disagreed — and the arithmetic says that edit buys nothing:
disagreement means more than one distinct status across executions, so at least
one execution was non-PASS, so the reported row is already non-PASS under FR-012.
The edit therefore changes nothing this spec wants and silently changes what PASS
means for `noop_gate` and `CONFIG_ERROR` rows it is not about.

**Trap 10 — The snapshot chain must be threaded through the repeated
executions.** FR-011, FR-012. `factory/verify/gates.py:1511` — `_run_watched`
takes a `before` snapshot and returns the `after` so it becomes the next gate's
`before`: "N gates cost N+1 snapshots, not 2N, and every path is attributed to
exactly one gate." A repetition loop that passes the same `before` to every
execution re-attributes everything the first execution wrote to the second, and a
gate that legitimately writes will look like it wrote twice as much and be
demoted to `DIRTIED_WORKTREE` on a run it did not dirty. Thread the returned
snapshot through the executions the way the outer loop already threads it through
gates.

**Trap 11 — Do not run every gate twice by default, and do not make repetition a
repository-wide switch.** FR-014, US3-S4. The reporter refused default repetition
in the ledger row itself — "This is not an argument for running every gate N
times" — and the cost is not hypothetical: the boundary gate's suite is this
repository's slowest, and doubling it doubles every attempt's wall clock for
every node. The view is sparse and gate-keyed for the same reason
`factory/verify/factory_yaml.py:431` — `_read_writes` is: "a key with one
position would let a repo turn off the whole check by naming a gate at all".
US3-S4 is the control a diff changing the default cannot pass.

**Trap 12 — The implementing node may not declare `runs:` in this repository's
own `ergane.yaml`, because the worker's parser predates the landing.** FR-016,
FR-018, US4. The config gate parses a node's manifest with the **worker's**
installed parser, not the worktree's, so a story that adds its own new key to
`ergane.yaml` is rejected at `CONFIG_ERROR` in 0.0s before any gate command runs.
`ergane.yaml:49-53` says so in the file itself, about the last key that tried it:
"a story that adds this key to its own manifest is rejected at CONFIG_ERROR in
0.0s before any gate command runs. 020's US1 died four times proving it." The
temptation here is unusually strong, because the obvious way to demonstrate
repetition is to declare it and watch. Do not. Every manifest US4 exercises is a
test fixture or a scripted candidate document written under `tmp_path`; the
repository's own `ergane.yaml` is not touched by any task in this spec, and the
operator step that declares the key runs against a scratch repository after the
worker has been restarted on the landed code.

**Trap 13 — A bubblewrap-guarded test proves nothing on the host the gate runs
on.** FR-003, US1-S6. This tree's convention guards every bwrap-driving test with
`@pytest.mark.skipif(not BWRAP_PRESENT, ...)` — the flag is defined at
`tests/test_us5_gates.py:44` — and `tests/test_sandbox_mount_set.py:156` records
that sixteen such tests already skip on the host this repository's gate runs on.
So the natural way to write US1-S6 — drive `SubprocessGateExecutor` and
`BwrapGateExecutor` and assert equal names — lands as a green gate, a passing
judge, and one half that never executed. Drive the subprocess executor for real
and a second backend through the same `_run_watched` seam without a skip guard,
so the claim under test is the *call site* rather than the binary. A bwrap-guarded
assertion may sit beside that pair; it may not replace it.

## Sizing

The bound is measured, not assumed. `DIFF_REFUSAL_THRESHOLD` is
`DIFF_INPUT_LIMIT` at `factory/verify/diffbounds.py:66`, which is 64 KiB at
`factory/verify/diffbounds.py:47`, and this repository's `ergane.yaml` declares no
`diff_refusal_bytes`, so 65,536 bytes is what a story here is refused unjudged
above (D-050). The calibration is the nearest landed analogue: **084-US3
(`d4a1406`) did this spec's exact schema path** — a new top-level manifest key,
its reader, the `FactoryConfig` field, `_AcceptedConfig`, `_interpret_candidate`,
both gate-list runners, the store codec and a `_gate_line` marker — and its diff
measured **49,371 bytes** at five acceptance scenarios, four FRs and twelve tasks,
of which 401 lines were one test module and 193 lines were the pasted evidence
file. That is 75% of the threshold for strictly less work than the old US3 carried
at ten scenarios, which is why it was split. Two more recent landings bracket it:
057-US4 (`1027a05`) landed at 63,932 bytes on five scenarios, and 126-US3
(`94c8cd8`) at 32,059 on four. Nothing in the recent corpus carries ten scenarios
in one node.

US1 touches `factory/verify/models.py` (one defaulted field plus its docstring
paragraph on `GateResult`), `factory/verify/gates.py` (one call in `_to_result`),
`factory/verify/store.py` (one line in each codec) and one new module holding the
recogniser, beside `factory/verify/gate_annotation.py` and modelled on it. Its
tests are one new module plus a fixture of real runner output. Six scenarios, five
FRs, eleven tasks; the production half is under a hundred lines and the fixture is
one pasted failure summary.

US2 touches `factory/verify/models.py` (one defaulted field on `AttemptRecord`),
`factory/workgraph/workflow.py` (one import inside the passthrough block and
three call sites), `factory/notify/messages.py` (one marker in `_gate_line`), and
the module US1 created gains the shared derivation. Its tests are one new module
plus an addition to the existing message-rendering tests. Seven scenarios, five
FRs, twelve tasks; the smallest production diff of the four.

US3 touches `factory/verify/gates.py` (the repetition loop, the optional view on
`_run_gate_list`, the defensive `getattr` in `_run_gate_list_from_config`),
`factory/verify/models.py` (two defaulted fields on `GateResult`) and
`factory/verify/store.py` (two lines in each codec) — **three production files, no
manifest surface at all**. Its tests are one new module driving both runners with
a scripted executor. Six scenarios, five FRs, ten tasks. Against 084-US3's five
files and 49,371 bytes this is the smaller half by production surface, and its
pasted evidence is one invocation-count table rather than a transcript.

US4 touches `factory/verify/factory_yaml.py` (one tuple entry, one reader, one
call in the reader list), `factory/verify/models.py` (one field on
`FactoryConfig`), `factory/verify/gates.py` (the protocol shape, the interpreter
and the `run_gates` hand-off), `factory/workgraph/prompt.py` and
`factory/notify/messages.py` (one marker each). Its tests are additions to
`tests/test_factory_yaml.py` for the schema half plus one new module driving the
candidate path. Five scenarios, five FRs, ten tasks — the same scenario count and
a comparable file count to 084-US3, which is the point of the split: US4 is that
landed story's size, not twice it, and its pasted evidence is one rendered attempt
block beside one rendered gate line.

No two stories are independent of each other on `factory/verify/models.py`,
`factory/verify/gates.py` or `factory/verify/store.py`, which is why the Work
Graph is a chain rather than a fan. The pair sharing the fewest production files
is US2 and US3: `factory/verify/models.py` alone, and in different classes
(`AttemptRecord` against `GateResult`). US1 and US4 share
`factory/verify/gates.py` but no function within it — US1 edits `_to_result`, US4
edits `_interpret_candidate` and `run_gates`.

## Verification the operator will run, independent of the gate

Per constitution VIII and D-037 the judge sees the diff and the criteria only, so
runtime evidence must be committed as pasted output. Beyond that:

1. On a scratch repository, declare a gate whose command runs a test suite with a
   deliberately failing test, dispatch a node, and let the gate refuse. Read
   `ergane build status --json` and confirm the attempt record names the gate and
   the failing check. Today that reading is `judge_outcome: null`, `verdict:
   FAIL`, and nothing else — the exact document the ledger row records.
2. Repeat with a gate command whose failure output is not a recognised runner's —
   a shell script that exits 1 with prose. The status must still name the gate and
   its status and say the check names were not recognised, and the recorded tail
   must be unchanged from what the command printed.
3. **On a scratch repository, and only after the worker has been restarted on the
   landed code** — trap 12: a `runs:` key in this repository's own `ergane.yaml`
   is refused at `CONFIG_ERROR` in 0.0s by the worker's older parser, which is how
   020's US1 died four times. Add `runs: {<that gate>: 3}` to the scratch
   repository's manifest and dispatch again with the test passing. Confirm from
   the gate's own output that the command ran three times and that the node's
   evidence carries one result for that gate.
4. Make the test fail exactly once in three by keying it on an external file the
   test itself rewrites, dispatch, and confirm the recorded row reports the
   failing execution, records three executions, and records a disagreement — and
   that the escalation message and the next attempt's prompt both say so.
5. Remove the `runs:` key and dispatch once more. Every gate must run exactly
   once and every row must record one execution and no disagreement — the control
   for trap 11.
6. Run `ergane init --check` against the scratch repository from step 3, confirm
   it does not refuse, then run `ergane init` and confirm the rewritten manifest
   still carries the `runs:` block. That is trap 2's falsifiable half: a key in the
   wrong tuple makes this step fail loudly.

Step 1 is the falsifiable test of the whole spec: it is the 2026-08-25 reading,
run forwards, with an answer where the ledger row recorded a blank.
