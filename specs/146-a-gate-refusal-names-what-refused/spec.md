---
state: draft
fixes:
  - verify/a-deterministic-gate-refusal-names-no-cause-an-operator-can-read
  - verify/a-gate-that-runs-exactly-once-cannot-see-a-flaky-gate
# DRAFTED 2026-09-04 by the refinement workflow (refinement-2026-09-04) from
# docs/triage-2026-09-03-ergane-web-round3.md § "a-gate-refusal-names-what-refused"
# (lines 294-311), against ergane-buildout at 602a92c.
# Every `file:line` in spec.md and plan.md was read from that commit with `sed`
# and verified to resolve to the symbol named, not recalled.
#
# WHERE THIS CAME FROM. Two ledger rows, both open, both `severity=warning`, and
# both about the same sentence. The first was measured by the operator on
# 2026-08-25 against epic-106 node us6 attempt 1: verdict FAIL, `judge_outcome`
# null, `rejection_cause` None, `terminal_reason` None — the deterministic gate
# refused before the judge ran, and that is the entire record. Five places were
# searched (the archived stdout.log, the attempt transcript directory, the
# worker journal over the exact window, `.factory` newer than the dispatch, and
# `ergane build --help`) and no gate output was in any of them. The second came
# from the `ergane-web` round-2 hand-over as N42: independent validation from a
# clean clone found a smoke gate failing 2 of 4 executions of the command
# exactly as declared, while the same test in isolation passed 3 of 3.
#
# WHAT IT COST, MEASURED. Diagnosing one refusal costs a hand re-run of the whole
# suite in the node's worktree — roughly 7 minutes on this box — and the re-run
# may not reproduce: on 2026-08-24 22:54 the operator gate on c3fb86e failed on
# `tests/test_us4_boundary.py::test_hanging_agent_is_killed_at_deadline_with_no_survivors`
# and that test passed in isolation in 3.40s, because the failure was contention
# against a concurrent boundary gate. A refusal that is not written down cannot
# be told from a flake after the fact. The second row's cost is the one the
# reporter named: twelve landed stories could not have caught the 2-of-4 smoke
# failure, so the defect shipped and the first person to meet it was whoever
# cloned the repository.
#
# WHY THE NAMING HALF IS FIRST. The reporter wrote, in the row itself, "This is
# not an argument for running every gate N times", and named a flake ledger keyed
# on test name as the cheapest alternative. A ledger keyed on test name needs a
# test name. Nothing in this factory records one today, so the naming half is the
# prerequisite that makes a flake countable at all, and it is US1 and US2.
#
# BOTH KEYS ARE DECLARED, AND HERE IS THE AUDIT. The first key is fixed whole by
# US1 (the row records what refused) and US2 (the operator reads it from
# `ergane build status --json` without a re-run) — its summary names exactly those
# two halves and nothing else. The second key asks for "some answer to 'would it
# pass again'" and names three acceptable ones: a repeat count on one gate, a
# nightly re-run of the landing branch, or a flake ledger keyed on test name. US3
# and US4 together build the first — US3 the repetition and disagreement
# mechanism, US4 the manifest declaration that drives it — and US1 supplies the
# key the third would need. Neither the nightly re-run nor a cross-attempt ledger
# is built; both are out of scope in the triage entry, and the reporter refused a
# default-on repetition outright. If a future reader judges that partial, the
# honest remedy is to reopen the second key rather than to read this note as a
# whole-fix claim it does not make.
#
# NOT IN SCOPE. No third `GateStatus` member and no third `OverallVerdict`
# member: a disagreement between executions is a recorded field, not a new
# outcome flowing through `gates_passed`, the verdict truth table and the ladder.
# No gate runs twice by default. No cross-attempt flake ledger. No change to what
# the judge is shown, to the retry ladder's arithmetic, or to the merge queue.
# The ledger grades both rows `warning` and the source document's own header
# reads P2; a promoted priority is not a licence for a larger build.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04), same sha 602a92c: split the
# oversized US3 into US3 (the repetition and disagreement mechanism, driven by a
# runner-level view) and a new US4 (the manifest declaration that fills that
# view), because the nearest landed analogue — 084-US3 (d4a1406), the same
# manifest-key-to-runner path — measured 49,371 bytes of a 65,536-byte refusal
# threshold at five scenarios, and the old US3 was a strict superset of it at ten.
# FR-011..FR-019 were renumbered so the mechanism FRs precede the declaration
# ones, and the prohibition half of the old FR-018 became its own FR; the FR count
# went 19 to 20 and no requirement was dropped. Narrowed FR-006 to
# `ergane build status --json`, which is the surface that actually carries an
# attempt's history. Tightened US1-S6 so the cross-executor claim cannot be
# discharged by a test that skips where bwrap is absent. Two traps added (the
# worker's parser predates the landing; a skipped bwrap test proves nothing) and
# four `_AcceptedConfig` citations rewritten into the checked symbol form.
# `fixes:` is unchanged: both keys still map whole onto the FRs, US3 and US4
# jointly where US3 alone stood before.
---

# Feature Specification: a gate refusal names what refused

**Created**: 2026-09-04
**Depends on**: nothing.

## The gap, stated precisely

A node refused by the deterministic gate records `verdict: FAIL` with
`judge_outcome: null`, and no surface an operator can reach names the check that
failed. The chain is seven steps, and the last two are why a re-run does not
close it.

1. A gate's entire account of its own failure is a text tail. `GateResult`
   carries `output_tail` at `factory/verify/models.py:403` — `GateResult`, the
   last 32 KiB of combined stdout and stderr, cut by
   `factory/verify/gates.py:369` — `tail_output`. There is no field for a check
   name, and nothing derives one.
2. The evidence store persists exactly that and nothing computed from it:
   `factory/verify/store.py:1091` — `_gate_to_dict` writes `output_tail`,
   `worktree_writes` and `writes_declared`, so re-reading a stored row gives back
   the same undifferentiated text.
3. Everything downstream that is not the operator does get the tail. The retry
   prompt quotes it verbatim for the next attempt at
   `factory/workgraph/prompt.py:867` — `_attempt_block`; the judge is shown the
   last 2 KiB at `factory/verify/judge.py:441` — `_gate_blocks`; the escalation
   message quotes it at `factory/notify/messages.py:536` — `_render_attempt`.
4. What the operator reads is `ergane build status --json`, and it reads the epic
   status query, which returns `history=tuple(record.history)` at
   `factory/workgraph/workflow.py:895` — `epic_status`.
5. That history is a tuple of `AttemptRecord`
   (`factory/verify/models.py:1245` — `AttemptRecord`), whose fields are attempt,
   persona, verdict, judge_outcome, model_alias, pre_agent and credential_source.
   No gate, no check, no output. The measured row was
   `{'attempt': 1, 'judge_outcome': None, 'model_alias': ..., 'persona': ...,
   'verdict': 'FAIL'}` and that is the whole record. **The agent is told and the
   operator is not.**
6. So the operator's only move is to re-run the suite by hand in the node's
   worktree, and a re-run answers a different question than the one asked,
   because every gate is executed exactly once.
   `factory/verify/gates.py:1447` — `_run_gate_list` and
   `factory/verify/gates.py:1491` — `_run_gate_list_from_config` each iterate a
   mapping of gate name to command — a mapping cannot hold one name twice — and
   `factory/verify/factory_yaml.py:328` — `_read_gates` requires every gate value
   to be a non-empty command string, so the manifest has no object form on which
   a count could be declared. A gate failing 2 of 4 executions passes half the
   attempts, and passing is the end of the matter.
7. The vocabulary for the answer already exists and stopped one step short. The
   `gate_contradictions` column at `factory/verify/store.py:241` is real and
   populated, but `factory/verify/models.py:706` — `detect_gate_contradictions`
   matches judge findings against gates *this attempt* recorded PASS. That is
   judge-versus-measurement inside one execution. It is never
   execution-versus-execution, and it never names a check.

## The rule this spec is asking for

**A gate refusal is a record of what refused — the checks named where the
runner's output format is recognised, the raw tail where it is not — readable by
the operator from the attempt record itself; and a repository may declare that a
named gate is executed more than once per attempt, so executions that disagree
are recorded as a disagreement instead of being settled by whichever one
happened to go last.**

What a gate records about the checks that refused it:

| gate outcome | output carries a recognised runner's summary | recorded check names |
|---|---|---|
| PASS | — | **none** — a green gate refused nothing |
| non-PASS | yes | the names that runner printed, in the order printed |
| non-PASS | no | **none**, and the tail remains the whole evidence, unchanged |

What a gate records when repetition is declared for it:

| repetitions declared for this gate | statuses across its executions | the reported row | disagreement |
|---|---|---|---|
| none declared | one execution | that execution's row, byte-identical to today | false |
| N ≥ 2 | every execution PASS | the last execution's row | false |
| N ≥ 2 | one distinct non-PASS status | the first non-PASS execution's row | false |
| N ≥ 2 | more than one distinct status | the first non-PASS execution's row | **true** |

Strictest-execution-wins is not a new policy. It is the rule
`factory/verify/gates.py:1583` — `_to_result` already states for itself in its
own docstring: fail-closed wherever the evidence is missing rather than merely
expected.

### What this spec is not

It is not a new verdict. No `GateStatus` member is added
(`factory/verify/models.py:73` — `GateStatus` keeps exactly five) and no
`OverallVerdict` member is added (`factory/verify/models.py:114` —
`OverallVerdict` keeps exactly two). A disagreement is a field beside the status,
never a status, so `factory/verify/models.py:950` — `gates_passed` and the
verdict truth table are untouched.

It is not a change to how many times gates run. A repository that declares no
repetition executes every gate once, exactly as today, and records that it did.

It is not a flake ledger. Nothing correlates check names across attempts, across
nodes or across epics; a name is recorded on the row that produced it, and what
anybody does with the corpus is a later spec's problem.

It is not an inference engine. A gate whose output matches no recognised runner
records no names at all, rather than a guess assembled from lines containing the
word "failed".

## User Scenarios & Testing

### User Story 1 - The gate result records the checks that refused it (Priority: P1)

As the factory, when a deterministic gate refuses a node, I write down which
checks refused it, so the fact survives the attempt that produced it.

**Why this priority**: P1 and it depends on nothing. Every other story in this
spec reads a field this one creates; without it US2 has nothing to report and the
flake in US3 is countable only as an anonymous status change.

**Independent Test**: Build a gate outcome carrying a recognised runner's failure
summary, turn it into a result, and read the recorded names; do the same for an
outcome carrying an unrecognised format and for a green gate.

**Acceptance Scenarios**:

1. **Given** a gate that exited non-zero and whose recorded output carries a
   recognised runner's failure summary, **When** the outcome becomes a
   `GateResult`, **Then** the result carries the check names that summary
   printed, in the order printed, and a committed test asserts each name against
   the pasted output it was parsed from.
2. **Given** a gate that exited non-zero and whose recorded output matches no
   recognised runner signature, **When** the outcome becomes a `GateResult`,
   **Then** the result carries no names and its `output_tail` is unchanged —
   asserted by a committed test on the same object, so a diff that started
   guessing at "failed"-shaped lines fails it.
3. **Given** a gate that exited zero and passed, **When** the outcome becomes a
   `GateResult`, **Then** the result carries no names, because a green gate
   refused nothing.
4. **Given** a gate whose output was long enough that the recorded tail dropped
   its earlier lines, **When** the names are recorded, **Then** every recorded
   name appears literally in the `output_tail` on that same result, proven by a
   committed test that asserts the containment for each name rather than
   asserting the count.
5. **Given** a result carrying recorded names, **When** it is written to the
   verification store and read back, **Then** the names round-trip; and **Given**
   a stored row written before this field existed, **When** it is read back,
   **Then** the names read as empty and no other field moves.
6. **Given** the shipped subprocess executor and a second backend handed to the
   same `factory/verify/gates.py:1511` — `_run_watched` seam, neither of them
   skippable on a host without bubblewrap, **When** each produces a failing
   outcome for one shared fixture command, **Then** both results carry the same
   names, because the derivation is applied once at the single point every
   executor's outcome becomes a `GateResult`. A committed test drives both
   backends; a test that calls the parser directly cannot satisfy this scenario,
   and a bubblewrap-guarded assertion may be added beside this pair but may never
   be the only proof, because it does not execute on the host the gate runs on.

### User Story 2 - The operator reads what refused without re-running the suite (Priority: P1)

As an operator whose node was refused by the gates, `ergane build status --json`
tells me which gate refused and which checks it named.

**Why this priority**: P1 and it depends on US1 having written the names down.
This is the story that ends the measured cost: seven minutes of hand re-running,
against a suite that may not reproduce the failure.

**Independent Test**: Compose a verification result whose gate refused with named
checks, append it to a node's history, and read the attempt record the status
query returns.

**Acceptance Scenarios**:

1. **Given** an attempt refused by a deterministic gate whose result named two
   checks, **When** the attempt record is built, **Then** the record carries a
   refusal line naming the gate, its status and both check names, and a committed
   test asserts the exact string.
2. **Given** an attempt refused by a gate whose result named no checks, **When**
   the attempt record is built, **Then** the refusal line still names the gate and
   its status and says the check names were not recognised — never an empty
   string, which reads as "nothing refused".
3. **Given** an attempt that passed its gates, **When** the attempt record is
   built, **Then** the record's refusal line is absent, so the field marks a
   refusal rather than annotating every row.
4. **Given** each of the three places the epic workflow appends an attempt record
   *from a verification result* — the main loop, the operator hand-back path and
   the conflicted re-sync recovery — **When** each appends, **Then** each
   populates the refusal line from the one shared derivation, proven by a
   committed test that exercises all three paths and by a diff in which the
   derivation is called three times and spelled once.
5. **Given** a node history recorded before this field existed, **When** it is
   replayed and the status query answers, **Then** the query answers with the
   refusal line absent and raises nothing, because the field is defaulted the way
   `model_alias` is.
6. **Given** an escalation message rendering a refused attempt, **When** its gate
   line is composed, **Then** the line carries the named checks as a marker beside
   the contention and writes markers already there, asserted against the pasted
   rendered message committed as evidence.
7. **Given** the fourth append site, where an unanswered operator question burns
   a slot and no verification result exists, **When** it appends its FAIL record,
   **Then** the record carries no refusal line, because no gate produced a result
   there and a line invented for it would name a refusal that did not happen.

### User Story 3 - A gate can be executed more than once, and a disagreement is recorded (Priority: P2)

As the factory, when a gate is to be executed more than once per attempt, I run
it that many times and record whether those executions disagreed, so a flake is a
fact on the row rather than a coin toss nobody sees.

**Why this priority**: P2, and it depends on US1's result shape. It is the
mechanism half of the second ledger row, and it is separated from the declaration
half (US4) because the two together are the size of a story that has already been
refused unjudged in this repository — see plan.md § Sizing. It comes after the
naming stories deliberately: a repetition primitive whose disagreements are
anonymous would produce a second unreadable verdict, which is the defect the first
two stories exist to end.

**Independent Test**: Hand the gate runner a repetition view directly — the way
`writes_view` is handed to it today — drive it with a scripted executor that
returns different outcomes on successive executions, and read the single result
the gate produced.

**Acceptance Scenarios**:

1. **Given** a repetition view declaring three executions for one gate and an
   executor scripted to return PASS every time, **When** the gates are run,
   **Then** the executor was invoked three times for that gate, the gate
   contributed exactly one result, and the declaration order of the results is
   unchanged — asserted by a committed test over the scripted executor's recorded
   invocations.
2. **Given** a repetition view declaring two executions and an executor scripted
   to return PASS then FAIL, **When** the gates are run, **Then** the reported row
   is the failing execution's own row — its status, its exit code, its duration
   and its tail, none of them blended — and the row records two executions and a
   disagreement.
3. **Given** the same view and an executor scripted to return FAIL then FAIL with
   the same status, **When** the gates are run, **Then** the row records two
   executions and **no** disagreement, because both executions agreed about the
   verdict.
4. **Given** no repetition view at all, in each of the two gate-list runners,
   **When** the gates are run, **Then** every gate is executed once, each row
   records one execution and no disagreement, and a committed test asserts the
   executor invocation count per gate is one in both runners — the control that a
   diff changing the default cannot pass.
5. **Given** a gate row recording a disagreement, **When** the deterministic half
   of the verdict is composed, **Then** the composed result is decided by the
   recorded status alone and `GateStatus` and `OverallVerdict` each still declare
   the same members they declare today, asserted by a committed test that
   enumerates both enums.
6. **Given** a result recording an execution count and a disagreement, **When** it
   is written to the verification store and read back, **Then** both round-trip;
   and **Given** a stored row written before these fields existed, **When** it is
   read back, **Then** it reads as one execution and no disagreement and no other
   field moves.

### User Story 4 - A repository declares which gate is executed more than once (Priority: P2)

As an operator who suspects a gate is unreliable, I declare in the manifest that
it runs more than once per attempt, and that declaration reaches the runner on the
path my nodes actually take.

**Why this priority**: P2, and it depends on US3's repetition view existing to
fill. It is the half of the second ledger row an operator can reach: US3's
mechanism is inert until a manifest can drive it.

**Independent Test**: Load a manifest declaring `runs:` for one gate under each
schema version, then resolve the same declaration through the candidate-parser
protocol and confirm the gate was executed the declared number of times.

**Acceptance Scenarios**:

1. **Given** a v2 manifest declaring `runs: {test: 3}` beside a `gates:` block
   that declares `test`, **When** the manifest is loaded, **Then** it parses and
   the parsed configuration carries that mapping.
2. **Given** a v2 manifest whose `runs:` entry names a gate the manifest does not
   declare, **When** it is loaded, **Then** it is refused with a message naming
   the entry and listing the declared gates; and **Given** an entry whose value is
   not a whole number greater than zero, **When** it is loaded, **Then** it is
   refused naming that value.
3. **Given** one manifest body declaring `runs:`, loaded twice — once under
   `version: 2` and once under `version: 1` — **When** each is loaded, **Then**
   the v2 load parses and carries the mapping while the v1 load is refused as an
   unknown top-level key. A committed test asserts both halves, and only the pair
   can fail a diff that registered the key in the v1 tuple.
4. **Given** a worktree that carries its own copy of the manifest parser, so the
   runner takes the candidate-parser path, **When** a manifest declaring `runs:`
   is resolved through that path, **Then** the declaration reaches the runner as a
   repetition view and the gate is executed the declared number of times. A
   committed test drives the candidate path with a scripted candidate result;
   a test that only exercises the in-process configuration cannot satisfy this
   scenario, and neither can one in which the accepted view is built and never
   handed to the runner.
5. **Given** an attempt whose gate row records a disagreement, **When** the retry
   prompt's attempt block and the escalation message's gate line are composed,
   **Then** each names the disagreement and the number of executions, so the next
   attempt is not sent to rewrite working code — asserted against pasted rendered
   output committed as evidence.

## Functional Requirements

- **FR-001**: A `GateResult` MUST carry the names of the checks that refused it,
  parsed from the gate's own recorded output where a runner's summary format is
  recognised, and empty where it is not.
- **FR-002**: The recogniser MUST be signature-based — a named runner and the
  exact shape it prints — following
  `factory/verify/gate_annotation.py:113` — `matched_install_signature`. A general
  search for lines containing words like "failed" MUST NOT be used, and output
  matching no signature MUST be recorded unchanged with no names.
- **FR-003**: The names MUST be parsed from the recorded `output_tail` of the
  same result, so every recorded name is present in the evidence that row
  carries; and the derivation MUST be applied at
  `factory/verify/gates.py:1583` — `_to_result`, the single point every executor's
  outcome becomes a result, and in no individual executor. The committed test that
  proves this MUST drive at least two backends through
  `factory/verify/gates.py:1511` — `_run_watched` without a host-dependent skip.
- **FR-004**: A gate whose status is PASS MUST record no names.
- **FR-005**: The field MUST default to empty and MUST round-trip through
  `factory/verify/store.py:1091` — `_gate_to_dict` and
  `factory/verify/store.py:1105` — `_gate_from_dict`, with an absent value on a
  row written before the field read as empty.
- **FR-006**: `AttemptRecord` (`factory/verify/models.py:1245` — `AttemptRecord`)
  MUST carry a refusal line naming the gate that refused the attempt, its status,
  and the checks it named; the epic status query MUST return it unchanged, so
  `ergane build status --json` answers "what refused" without a re-run.
- **FR-007**: The refusal line MUST be derived by one shared function called at
  every site that appends an `AttemptRecord` **from a verification result** — the
  main loop, the operator hand-back path and the conflicted re-sync recovery —
  and spelled once. The fourth append site, the unanswered-question FAIL at
  `factory/workgraph/workflow.py:2041` — `_run_node`, holds no verification
  result and MUST carry no refusal line.
- **FR-008**: An attempt refused with no recognised check names MUST still name
  the gate and its status and MUST state that the check names were not
  recognised; an attempt whose gates passed MUST carry no refusal line.
- **FR-009**: The refusal line field MUST be defaulted, so a node history
  recorded before it existed replays and answers the status query rather than
  refusing it, following `model_alias` at
  `factory/verify/models.py:1245` — `AttemptRecord`.
- **FR-010**: The escalation message's gate line
  (`factory/notify/messages.py:581` — `_gate_line`) MUST carry the named checks as
  a marker beside the contention and writes markers already rendered there.
- **FR-011**: A gate for which a repetition view declares N executions MUST be
  executed N times within its single manifest entry, in both
  `factory/verify/gates.py:1416` — `_run_gate_list` and
  `factory/verify/gates.py:1467` — `_run_gate_list_from_config`. The view MUST be
  optional and gate-keyed, shaped like the `writes_view` those two runners already
  take. The one-result-per-declared-gate contract and the declaration order of
  results MUST NOT change.
- **FR-012**: The reported row MUST be one execution's own row — the first
  non-PASS execution if there is one, otherwise the last — with its own status,
  exit code, duration and tail. Only the execution count and the disagreement
  flag may be computed across executions.
- **FR-013**: The result MUST record how many times the gate was executed and
  whether the executions disagreed, disagreement being more than one distinct
  status across them; both MUST be defaulted fields on
  `factory/verify/models.py:362` — `GateResult` and MUST round-trip through the
  store codecs, with absent read as one execution and no disagreement.
- **FR-014**: A gate for which no repetition is declared MUST behave exactly as
  today: it is executed once, its row records one execution and no disagreement,
  and no other recorded field moves. This MUST hold in both runners.
- **FR-015**: A disagreement MUST NOT add a `GateStatus` member, MUST NOT add an
  `OverallVerdict` member, and MUST NOT change
  `factory/verify/models.py:950` — `gates_passed`, which stays decided by the
  reported status alone.
- **FR-016**: A v2 manifest MUST accept a top-level `runs:` mapping of declared
  gate name to a whole number of executions greater than zero, sparse the way
  `factory/verify/factory_yaml.py:397` — `_read_timeouts` is: absent means nothing
  declared.
- **FR-017**: A `runs:` entry naming a gate the manifest does not declare MUST be
  refused, naming the entry and listing the declared gates; an entry whose value
  is not a whole number greater than zero MUST be refused naming that value.
- **FR-018**: `runs:` MUST be refused on a v1 manifest as an unknown top-level
  key. It MUST be registered in `_V2_TOP_LEVEL_KEYS`
  (`factory/verify/factory_yaml.py:134`) and MUST NOT be registered in
  `_TOP_LEVEL_KEYS` (`factory/verify/factory_yaml.py:109`).
- **FR-019**: The declaration MUST reach the runner through the candidate-parser
  protocol as well as through the in-process configuration —
  `factory/verify/gates.py:205` — `_AcceptedConfig` and
  `factory/verify/gates.py:1045` — `_interpret_candidate` — because a worktree
  carrying its own parser takes that path, which is every Ergane node; and
  `factory/verify/gates.py:1289` — `run_gates` MUST hand the accepted view to
  `factory/verify/gates.py:1416` — `_run_gate_list`, because a view lifted off the
  acceptance and never passed on is the same defect one step later.
- **FR-020**: A disagreement MUST be named, with its execution count, in the retry
  prompt's attempt block (`factory/workgraph/prompt.py:843` — `_attempt_block`)
  and in the escalation gate line.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-006, FR-007, FR-008, FR-009, FR-010]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-011, FR-012, FR-013, FR-014, FR-015]
US4:
  depends_on: []
  depends_on_merged: [US3]
  implements: [FR-016, FR-017, FR-018, FR-019, FR-020]
```

Three `depends_on_merged` edges and no pass-edges, declared rather than left
inferred (069-US2 FR-007). US2 reads the field US1 adds to `GateResult` and would
have nothing to report before it merges; the edge is therefore correctness of
sequencing rather than freedom from contention, and US2's own production files —
`factory/workgraph/workflow.py` and `factory/notify/messages.py` — are ones US1
never opens.

The US2 → US3 edge is contention rather than sequencing. US3 adds two more fields
to the same `GateResult` US1 extends, threads them through the same two store
codecs and edits the same `factory/verify/gates.py` US1 edits; US2 in turn edits
`factory/verify/models.py`, the file US1 and US3 both open. Three stories editing
one module concurrently would each pass their own gate and collide in the queue,
so the ordering is declared at dispatch instead of discovered at merge.

The US3 → US4 edge is both. US4 fills the repetition view US3 defines — a
declaration with no mechanism to drive is parsed and never read, which is trap 1's
defect written into the Work Graph — and US4's disagreement markers land in
`factory/notify/messages.py:581` — `_gate_line`, the function US2 also edits, and
in `factory/verify/gates.py`, the file US3 also edits. Merging US3 first is what
makes US4's own gate a real test of the pair.
