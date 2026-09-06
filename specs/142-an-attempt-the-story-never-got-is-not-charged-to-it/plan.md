# Implementation Plan: an attempt the story never got is not charged to it

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## What already exists, and where

**The accounting function is not called what the triage entry and both ledger
rows call it.** They name `charged_attempts`; no such symbol exists in this tree
and `git log -S charged_attempts -- factory/verify/ladder.py` returns nothing.
The function is `factory/verify/ladder.py:368` — `_attempts_spent`, and its whole
body is four lines:

```python
    promotion_target = config.promotion_persona if config is not None else None
    excluded = {DEBUGGER_PERSONA, promotion_target} if promotion_target else {DEBUGGER_PERSONA}
    return sum(
        1
        for record in history
        if record.persona not in excluded and not record.pre_agent
    )
```

Its docstring at `factory/verify/ladder.py:378` already argues this spec's case
for a different noun: "A pre-agent failure is excluded too (095-US2, FR-005): the
agent never started, so it is not a rung at all — the same argument as the
debugger's, from the other end." The exclusion is a property of the record, not
of the config (`factory/verify/ladder.py:380`), which is why it works at call
sites that pass no config. Keep that property.

**The flag that exclusion reads is a claim about the agent, and it is False
here.** `factory/workgraph/workflow.py:2109` sets it:

```python
                        pre_agent=termination == Termination.PRE_AGENT_FAILURE,
```

`Termination.PRE_AGENT_FAILURE` (`factory/usage/models.py:68`) is documented as
"an attempt in which no agent turn ever ran ... the whole attempt ending before
the start". A boundary that could not start is the opposite case: the agent ran
for its full time and produced a diff, and only the verification refused.

**And that append is one of three.** `grep -n 'record.history.append'
factory/workgraph/workflow.py` returns 2040 (the question expiry, trap 8), 2095
(the ladder loop, above), 2885 and 4017. The last two each call `self._verify`
first — `factory/workgraph/workflow.py:2871` and
`factory/workgraph/workflow.py:4005` — so they run the same gates through the same
activity on the same host, and each appends its own record:

```python
        record.history.append(
            AttemptRecord(
                attempt=record.attempt,
                persona=resolved.node.persona,
                verdict=result.verdict,
```

That one is `factory/workgraph/workflow.py:2885`, inside
`factory/workgraph/workflow.py:2837` — `_apply_external_completion_if_present`
(the operator's hand-back). The other is `factory/workgraph/workflow.py:4017`,
inside `factory/workgraph/workflow.py:3879` — `_recovery_attempt`, whose docstring
calls it "the full 002 ladder authority (gates -> output -> judge)" and which
raises the number at `factory/workgraph/workflow.py:3910` under the comment "a
recovery is an attempt too". Both write the node's own persona, so
`_attempts_spent` counts both. Neither is `pre_agent`. FR-013 exists because of
them.

**Which of the boundary's two refusals production can actually reach.** The
backend is chosen by `factory/verify/gates.py:1346` — `_resolve_gate_executor`,
and the choice is guarded:

```python
    if executor is not None:
        return executor
    if boundary.runtime == "bwrap" and BWRAP_BACKEND_BINARY.is_file():
        return BwrapGateExecutor(caches=boundary.caches)
    return SubprocessGateExecutor()
```

Its docstring says why (`factory/verify/gates.py:1355`): the fallback "keeps the
suite green on hosts where bwrap is not installed". The production verify activity
resolves through it — `factory/activities/verify_activities.py:280` wraps
`gates.resolve_gate_executor(...)` in the heartbeating executor. So on a host with
no `bwrap`, verification gets a `SubprocessGateExecutor`
(`factory/verify/gates.py:430` — `SubprocessGateExecutor`), which has no refusal
arm at all: `factory/verify/gates.py:446` goes straight to `subprocess.Popen`. The
missing-binary refusal below is therefore reachable only through an injected
executor or a race between the `is_file()` at `factory/verify/gates.py:1364` and
the one at `factory/verify/gates.py:581`. **The live trigger is the toolchain
arm**, and it is the one the operator steps drive.

**The boundary's two refusals, and why they look like failures.**
`factory/verify/gates.py:583`, inside `factory/verify/gates.py:578` —
`BwrapGateExecutor.run`, is the missing-binary refusal:

```python
        binary = BWRAP_BACKEND_BINARY
        if not binary.is_file():
            return ExecutionOutcome(
                exit_code=127,
                output=(
                    f"sandbox backend 'bwrap' not available: {binary} "
                    "missing on this host"
                ),
                duration_s=0.0,
                timed_out=False,
            )
```

and `factory/verify/gates.py:605` is the toolchain refusal, raised out of
`_build_argv` and caught as `ToolchainError` — the same shape, "a 127 outcome
carrying the reason, not an exception the gate runner has no place to put"
(`factory/verify/gates.py:599`). `ExecutionOutcome` is
`factory/verify/gates.py:273` — `ExecutionOutcome` and carries four fields today:
`exit_code`, `output`, `duration_s`, `timed_out`.

**The single funnel, and the ladder that flattens both refusals into FAIL.**
`factory/verify/gates.py:1583` — `_to_result` is called exactly once, from
`factory/verify/gates.py:1555` inside `factory/verify/gates.py:1511` —
`_run_watched`, and its status ladder is six lines:

```python
    if outcome.timed_out:
        status, exit_code = GateStatus.TIMEOUT, None
    elif outcome.exit_code != 0:
        status, exit_code = GateStatus.FAIL, outcome.exit_code
    elif snapshot_error:
        status, exit_code = GateStatus.DIRTIED_WORKTREE, 0
    elif worktree_writes and not writes_declared:
        status, exit_code = GateStatus.DIRTIED_WORKTREE, 0
    else:
        status, exit_code = GateStatus.PASS, 0
```

`factory/verify/gates.py:1625` is the line that swallows the distinction. The
module's own comment at `factory/verify/gates.py:1645` says `_to_result` is "the
single line every backend's outcome passes through — `SubprocessGateExecutor`,
`BwrapGateExecutor` and the activity's `_HeartbeatingExecutor` alike", which is
why the branch belongs here and in no executor.

**The status enum and the verdict it feeds.** `factory/verify/models.py:73` —
`GateStatus` holds five members at `factory/verify/models.py:93-97`, and
`factory/verify/models.py:76` reserves `CONFIG_ERROR` for "a missing or malformed
`factory.yaml`". `factory/verify/models.py:950` — `gates_passed` is:

```python
    return bool(gate_results) and all(
        gate.status == GateStatus.PASS for gate in gate_results
    )
```

so a new member fails the deterministic half with no edit at all, which is
FR-003. Its docstring at `factory/verify/models.py:958` states the comparison
rule the new branch must follow: "Statuses are compared by value, not by
identity: a `GateResult` that crossed a Temporal payload boundary carries the
enum's string."

**The wrapper the new field must survive, and the codec it must not need.**
`factory/activities/verify_activities.py:248` — `_HeartbeatingExecutor.run` ends
`return self._inner.run(invocation)`, so a field added to `ExecutionOutcome`
reaches `_to_result` untouched — and `ExecutionOutcome` never crosses a payload
boundary. `GateResult` does: `factory/verify/store.py:1095` writes
`GateStatus(gate.status).value` and `factory/verify/store.py:1109` reads
`GateStatus(data["status"])`. A new enum member round-trips through both for
free; a new boolean field on `GateResult` would need a codec change in both
directions plus a default for old rows (`factory/verify/store.py:1116` is what
that costs). Put the fact in the status.

**The bound this spec must copy, argued in the tree already.**
`factory/verify/ladder.py:410` — `pre_agent_bound_spent` sits on
`factory/verify/ladder.py:393` — `pre_agent_failures_spent`, which counts "the
length of the unbroken tail". `factory/verify/ladder.py:188` — `next_action`
consults it at `factory/verify/ladder.py:228`, above the ordinary-allowance
branch, and the comment at `factory/verify/ladder.py:222` names the reason: "An
exclusion without a bound of its own is a starvation bug (plan trap 2)". The dial
is `factory/verify/models.py:1215`, whose comment block from
`factory/verify/models.py:1206` explains the default of 4.

**Registering a ladder dial is three edits, not one.** `_LADDER_KEYS` is
`factory/verify/factory_yaml.py:144-151`, `_LADDER_BOUNDS` is
`factory/verify/factory_yaml.py:157-164`, and the construction that turns read
values into a `VerificationConfig` is `factory/verify/factory_yaml.py:880-889`,
with `max_pre_agent_failures` at `factory/verify/factory_yaml.py:888` as the
worked example. All three sit inside `factory/verify/factory_yaml.py:818` —
`_read_ladder` and its neighbours.

**The sentence the escalation prints, and where the new bound joins it.**
`factory/verify/ladder.py:270` — `exhausted_bound` opens by asking `next_action`
itself (`factory/verify/ladder.py:305`) so a node with somewhere left to go can
never be described as exhausted, then branches in the order `next_action` reaches
them. The pre-agent branch is `factory/verify/ladder.py:311-321` and names the
remedy — "Re-authenticate on the worker host". The new branch goes beside it, and
its remedy is a different one. The workflow's fail-safe default for that bound is
`factory/workgraph/workflow.py:2146-2152`, which chooses `PAUSE_EPIC` over `KILL`
because "a dead credential is fixed by re-authenticating, not by killing the
node" — the same argument holds for a host with no sandbox binary.

**The question path, which already costs no rung and already says so.** The
marker reclassifies at `factory/workgraph/workflow.py:1949`; on an answer,
`factory/workgraph/workflow.py:2058` stores the exchange and the comment above it
at `factory/workgraph/workflow.py:2053` states the current behaviour exactly:

```python
                            # The operator answered. Carry the exchange verbatim into
                            # the next attempt's prompt under a dedicated section
                            # (FR-003) — the question the agent asked and the answer the
                            # operator gave, read as the operator's decision. No
                            # `AttemptRecord` is appended: the QUESTION attempt broke
                            # the loop before the history append, so `_attempts_spent`
                            # excludes it by construction and the answer costs no slot
                            # (FR-001). The retry re-enters the ladder with the same
                            # budget it had before the question.
```

The expiry branch above it, `factory/workgraph/workflow.py:2040`, appends a
charged FAIL on purpose, and `factory/workgraph/workflow.py:2038` says so. The
loop then `continue`s to `factory/workgraph/workflow.py:1815`, which is
`record.attempt += 1`.

**What US4 renders, and the two fields it renders from.**
`factory/notify/messages.py:529` — `_render_attempt` opens with
`factory/notify/messages.py:531`:

```python
    lines = [f"Attempt {result.attempt} — {_value(result.verdict)}"]
```

and `factory/notify/messages.py:270` — `render_history` joins those with blank
lines. `factory/verify/models.py:937` and `factory/verify/models.py:938` are
`started_at` and `finished_at`, both `NOT NULL` in the store
(`factory/verify/store.py:224` and `factory/verify/store.py:225`; the gate JSON
sits above them at `factory/verify/store.py:216`), and both written
by `factory/workgraph/workflow.py:4362` — `_now`, which formats through
`factory/workgraph/workflow.py:4371` — `_iso` as
`isoformat(timespec="seconds").replace("+00:00", "Z")` — whole seconds, `Z`
suffix.

**The operator's reading of this history, and the two surfaces that are not
readings of it.** `factory/workgraph/workflow.py:860` — `epic_status` puts every
`AttemptRecord` into the status document — `factory/workgraph/workflow.py:895` is
`history=tuple(record.history)` — and `factory/cli/nouns/build.py:1175-1188`
copies that document and prints it as JSON under `--json`. So a reason field
added to the record is
readable through `ergane build status <epic> --json` with no CLI change at all,
and that is the only reading of it there is. The *rendered* status line is not:
`factory/cli/nouns/build.py:464` — `render_status` prints
`factory/cli/nouns/build.py:503`, `attempt {node['attempt']}` and the tokens
beside it, and neither token is the ladder's history —
`factory/cli/nouns/build.py:718` — `_reason_token` renders `terminal_reason`
(why a node *ended*), and `factory/cli/nouns/build.py:738` —
`_attempt_note_lines` renders `attempt_note`, which 095-US1 writes for the
pre-agent failure alone (`factory/workgraph/workflow.py:1918`) and rewrites every
attempt. `ergane build attempts` is not a reading of it either:
`factory/cli/nouns/build.py:1352` — `render_attempts` prints
`factory/cli/nouns/build.py:1390`, one line per `VerificationResult` out of the
evidence store — node, attempt, form, verdict, judge-input token — with no gate
row and no history in it. US1's new `GateStatus` does reach a human surface,
through the page rather than the CLI: `factory/notify/messages.py:581` —
`_gate_line` renders `factory/notify/messages.py:584`,
`gate {name}: {status} (exit N, X.Xs)`, for every gate of every attempt in the
escalation history.

**The offline seam for driving the boundary refusals — and the seam that looks
like it and is not.** The tempting one is the module attribute:
`tests/test_101_declared_caches.py:363` and `tests/test_sandbox_mount_set.py:287`
both reach it with `monkeypatch.setattr(gates_module, "BWRAP_BACKEND_BINARY",
...)`, and both plant a *real* binary so the host stops being a variable.
Pointing it at a path that does not exist does **not** drive
`factory/verify/gates.py:583` through those tests' own route:
`tests/test_101_declared_caches.py:366` is `executor =
resolve_gate_executor(host.worktree)`, and with the attribute pointed at nothing
that returns a `SubprocessGateExecutor` (`factory/verify/gates.py:1364`). To reach
the refusal, **construct `BwrapGateExecutor` directly** and call `run` on it — the
class is `factory/verify/gates.py:578` — `BwrapGateExecutor.run` and it needs no
resolution helper. Note what is **not** there: no test in this suite asserts that
refusal. `tests/test_sandbox_mount_set.py:133` writes
`gates_module.BWRAP_BACKEND_BINARY = Path("/nonexistent/bwrap")` inside that
module's own docstring, as a recipe an operator runs by hand
(`tests/test_sandbox_mount_set.py:135` is the `pytest -p no_bwrap_plugin`
invocation beside it), and every other bwrap test skips when the binary is
missing (`tests/test_us3_boundary.py:192`). The `ToolchainError` half — the arm
production actually reaches — is better served:
`tests/test_toolchain_discovery.py:287` —
`test_a_missing_tool_is_absent_rather_than_guessed` drives it with
`pytest.raises` at `tests/test_toolchain_discovery.py:298`, by emptying
`_SYSTEM_FALLBACK_DIRS` on a planted host, which makes
`BwrapGateExecutor.run` return the 127 outcome at `factory/verify/gates.py:605`.
`PlantedHost` is a module-local helper class rather than a pytest fixture —
`tests/test_toolchain_discovery.py:131` — `PlantedHost` — so the new test imports
it from that module.

**The seam US2-S7 needs, which already exists.** `tests/test_interpreter.py:688` —
`scored` takes a `gates=` list, so a scripted attempt can carry any `GateResult`
the story invents, and `tests/test_rung_resolves_its_own_model.py:183` —
`test_a_clean_resync_recovery_keeps_the_nodes_own_persona_and_model` already
drives a **clean re-sync recovery** end to end in a `WorkflowEnvironment`
(`script_landing(..., checks_failed_snapshot(), merged_snapshot())` plus
`script_sync("us1", clean=True, ...)`). A clean re-sync keeps the node's own
persona, which is the case `_attempts_spent` counts — so that is the fixture the
recovery scenario copies.
**The seam US2-S8 needs, which also already exists.**
`tests/test_external_completion.py:705` —
`test_external_completion_fails_when_work_breaks_gates` already drives an
operator hand-back whose gates fail, end to end in a `WorkflowEnvironment`: its
`tests/test_external_completion.py:198` — `ConfigurableScript` takes a list of
per-attempt gate results and `tests/test_external_completion.py:252` —
`_fail_gate` is the entry to swap for a boundary-never-ran result. The node is
exhausted first (`max_attempts=1` at `tests/test_external_completion.py:487`,
because the hand-back is refused while attempts remain), so the history that
comes back holds one genuine charged record and then the hand-back's — which is
what makes "the ordinary allowance counts only the genuine attempts before it"
an assertion rather than a tautology. The settled `EpicStatus` carries the
history verbatim (`factory/workgraph/workflow.py:895`), so the test reads it
without touching the store.

## Traps

**Trap 1 — The exclusion mechanism already exists and the name in the entry does
not.** FR-005. Both new ledger rows and the triage entry say `charged_attempts`;
grep finds nothing, because the function is
`factory/verify/ladder.py:368` — `_attempts_spent`. An implementer who greps the
entry's name concludes the mechanism is missing and builds a second one beside
it. Worse: the obvious shortcut once found is to set `pre_agent=True` for a
boundary refusal. That flag is a claim about the agent
(`factory/verify/models.py:1273`), and it is what
`factory/verify/ladder.py:311-321` uses to tell the operator "Re-authenticate on
the worker host" — so a boundary whose toolchain would not resolve would page
the operator about a credential that is fine. The new exclusion needs its own
predicate and its own reason value.

**Trap 2 — Exit code 127 is not the signal, and branching on it inverts the
defect.** FR-001. Both boundary refusals return `exit_code=127`
(`factory/verify/gates.py:583`, `factory/verify/gates.py:605`) — but so does
`bash -c` when the *gate command itself* is misspelled or its binary is not in the
container's `PATH`. A branch written as `elif outcome.exit_code == 127:` in
`factory/verify/gates.py:1583` — `_to_result` would stop charging the node for
"your `typecheck` gate names a binary that does not exist", which is a real defect
in the repository under test and must keep costing a rung. US1-S3 exists to fail
that diff: it pins a ran-and-exited-127 command as `FAIL` beside a never-started
outcome. Carry the fact on `ExecutionOutcome`
(`factory/verify/gates.py:273` — `ExecutionOutcome`) instead.

**Trap 3 — `CONFIG_ERROR` is not an escape hatch, and it must stay charged.**
FR-002, FR-004. `factory/verify/models.py:76` and
`factory/verify/factory_yaml.py:1103` reserve that status for a missing or
malformed manifest, and its synthetic gate is literally named `config`
(`factory/verify/gates.py:1307`). Reusing it here would be wrong twice: the name
lies, and — the half that costs money — an unusable `factory.yaml` is a fact about
the worktree the agent has just been editing, so excluding it from the ladder
would hand an agent a free loop for breaking the manifest. US1-S5 asserts the new
predicate answers "it ran" for `CONFIG_ERROR`. The empty list is the same trap
one step further in: a predicate shaped `all(result never started)` answers
"never ran" over zero results, and `factory/verify/gates.py:1620` states this
module's rule for exactly that shape — "fail-closed is this module's rule
wherever the evidence is missing". `factory/verify/models.py:950` — `gates_passed`
already refuses an empty list for the same reason. US1-S5 asserts it as a fourth
case.

**Trap 4 — Do not touch `gates_passed`, and do not compare the new status with
`is`.** FR-003. `factory/verify/models.py:950` — `gates_passed` already refuses
anything that is not `PASS`, so the new member fails the deterministic half for
free; editing it is how this story accidentally lets a never-started gate land.
Every other consumer keys off `PASS` the same way —
`factory/notify/messages.py:536`, `factory/verify/judge.py:441` — so none of them
needs a branch either. But `factory/workgraph/prompt.py:868` reads
`if gate.status is GateStatus.PASS:`, an identity comparison, and
`factory/verify/models.py:958` explains why that is a trap for anything that
crosses a Temporal payload boundary. Write the new comparison by value.

**Trap 5 — An exclusion without a bound is a starvation defect, which is why
US2 ships the dial in the same story.** FR-007.
`factory/verify/ladder.py:220-229` already carries the argument in the tree's own
words, for the pre-agent case. If the exclusion lands in one commit and the bound
in the next, a worker host whose boundary cannot resolve its toolchain retries
the same node forever in between, holding a slot at concurrency 1 and starving
every other spec — a live regression on the landing branch, not a hypothetical. Do not "split this story to
make it smaller": the smallness is bought with an outage window.

**Trap 6 — A ladder dial is three registrations, and a dataclass default is not
one of them.** FR-007. The dial must appear in `_LADDER_KEYS`
(`factory/verify/factory_yaml.py:144-151`), in `_LADDER_BOUNDS`
(`factory/verify/factory_yaml.py:157-164`) and in the construction at
`factory/verify/factory_yaml.py:888`. A dial added to
`factory/verify/models.py:1181` — `VerificationConfig` alone reads its default in
every test the implementer writes and is refused as an unknown key the first time
an operator declares it in a manifest. US2-S6 is the scenario that catches it, and it needs
both halves — declared and undeclared — in one test.

The default is load-bearing and FR-007 fixes it at 4.
`factory/verify/models.py:1206` gives the argument for the dial this one copies:
4 is "above the default
`max_attempts` of 3, so the exclusion is observable". Default this one to 3 and
US2-S2 becomes unprovable — a history of three boundary refusals escalates on the
new dial at exactly the rung the ordinary allowance would have escalated on, and
`next_action` returns the same `ESCALATE` either way. That is why US2-S2 and
US2-S4 assert through `factory/verify/ladder.py:270` — `exhausted_bound`, which
names the dial, rather than through `next_action`, which cannot.

**Trap 7 — The answered-question path already costs no rung; the defect is the
hole in the history, not a charge to remove.** FR-009. The ledger row says a node
"advanced to attempt 2 with an empty history list" and infers that it "begins its
real work one rung down". The first clause is true, the inference is not:
`factory/workgraph/workflow.py:2053` says no record is appended, so
`_attempts_spent` sees nothing and the ordinary allowance is genuinely intact. An
implementer who takes the row literally will hunt for a charge, find none, and
then do one of two wrong things — conclude the story is a no-op, or stop
`factory/workgraph/workflow.py:1815` from incrementing `record.attempt`. The
second is the expensive one: the attempt number is part of the evidence store's
upsert key, `UNIQUE (epic_id, node_id, attempt, form, dispatch)` at
`factory/verify/store.py:260`, so re-using it makes the answered attempt overwrite
the question attempt's row. Leave the number alone and append the record.

The record's verdict is the third wrong move, because the spec's truth table
prints "no rung" and an implementer reads that as "nothing failed".
`AttemptRecord.verdict` (`factory/verify/models.py:1264`) has no default, so a
value must be chosen, and `factory/verify/ladder.py:209` returns
`NextAction.PASSED` the moment the last record reads `PASS` — writing `PASS` here
lands the node with nothing verified. Copy the expiry branch four lines above
(`factory/workgraph/workflow.py:2040`): `OverallVerdict.FAIL`, made uncharged by
the reason field rather than un-failed by the verdict.

**Trap 8 — The expired question must keep burning its rung.** FR-010.
`factory/workgraph/workflow.py:2040` appends a charged FAIL when the operator
never engaged, and `factory/workgraph/workflow.py:2038` explains that "the FAIL
`AttemptRecord` is what `_attempts_spent` counts, so appending it here is what
consumes the slot" — 008-US2 FR-001/FR-004, deliberate. A story that adds the new
reason field to *both* branches because they sit four lines apart lets a node park
on unanswered questions forever. US3-S3 pins the two paths side by side in one
test for this reason.

**Trap 9 — One reason field, not a flag per trigger.** FR-006. There are already
three "not a rung" conditions on `factory/verify/models.py:1245` —
`AttemptRecord`: the debugger persona, the promotion persona and `pre_agent`. Two
more booleans would make five ways to ask one question and four places to forget
one. Add a single reason field (empty means charged), give it a named constant per
reason, and have `_attempts_spent` exclude on it. US3 then costs one constant and
one append instead of a second schema change — which is the whole reason US2 and
US3 are separate stories rather than one.

**Trap 10 — The escalation renderer may not read a clock and may not raise.**
FR-011, FR-012. `factory/notify/messages.py:529` — `_render_attempt` runs on the
paging path; an exception there is a page that never arrives on the one night it
mattered. The timestamps are whole seconds with a `Z` suffix
(`factory/workgraph/workflow.py:4371` — `_iso`), so parse defensively and omit the
line when either value will not parse. And compute the elapsed from the two stored
values only: US4-S1 asserts the rendered number equals the difference of two known
timestamps, which no implementation that consults the wall clock can satisfy.

**Trap 11 — `concurrent_gates` is a dead end, and the key's name will send you
there.** The key `gates/concurrent-epics-collide-on-a-fixed-gate-port` is refuted
by its own occurrences 3-5, which record `max_concurrent_nodes=1`. The field
`factory/verify/models.py:404` already recorded 0 for all three reported failures,
and its only readers are `factory/notify/messages.py:588` and
`factory/verify/store.py:1099`/`factory/verify/store.py:1116` — nothing in the
verdict path consults it. Do not add a contention branch, do not allocate ports,
and do not give the boundary `--unshare-net`: `factory/verify/gates.py:885` —
`_resolver_binds` documents that a namespace with no `/etc/resolv.conf` turns every
package install into "Temporary failure in name resolution", which reads like a
broken dependency rather than a missing mount.

**Trap 12 — The uncharged reason has exactly one operator reading, and it is the
JSON one.** FR-006, FR-009. `ergane build status <epic> --json` carries the
history verbatim (`factory/workgraph/workflow.py:895`,
`factory/cli/nouns/build.py:1175-1188`); the rendered line
(`factory/cli/nouns/build.py:503`) prints only `attempt N`, and `ergane build
attempts` (`factory/cli/nouns/build.py:1352` — `render_attempts`) prints neither
the history nor a gate row. Two wrong moves follow from that. The first is to add
a reason token to the rendered line while passing through: that is a fifth
production file in the story trap 5 already refuses to split, on a surface no
scenario here asserts and no FR here asks for. The second is more expensive,
because it looks like a failure of the fix: after an answered question the
rendered line reads `attempt 2`, and an implementer or an operator who takes that
as "a rung was spent" will go and stop `factory/workgraph/workflow.py:1815` from
incrementing — the number is the dispatch counter and part of the evidence
store's upsert key (`factory/verify/store.py:260`). The reading that answers "was
a rung spent" is the history's reason field in the JSON document, and after that
the arithmetic the escalation prints.

**Trap 13 — Removing `bwrap` reproduces the opposite of this defect, and the
first draft of this plan told you to do it.** FR-001, FR-008. The experiment
everyone reaches for is "move `bwrap` aside and watch the boundary refuse". It
does not refuse. `factory/verify/gates.py:1346` — `_resolve_gate_executor` returns
`SubprocessGateExecutor` unless the binary is present
(`factory/verify/gates.py:1364`), the docstring at
`factory/verify/gates.py:1355` says that is deliberate, and the production verify
activity resolves through it (`factory/activities/verify_activities.py:280`). So
the gates run on the host and pass or fail normally. Worse, the *agent* side does
not fall back at all: `factory/workgraph/adapter.py:1207` — `_resolve_backend` is
documented as "never a silent fallback to the host launch (FR-008)", and
`factory/workgraph/adapter.py:675` raises `AdapterError` for the missing binary —
so the dispatch dies before the agent's first token and the node pages on
`max_pre_agent_failures`, the exact credential-shaped escalation FR-008 forbids.
An implementer who "verifies the fix" that way sees no reason field, no new
status, and a credential page, and concludes the change does not work. Drive the
`ToolchainError` arm at `factory/verify/gates.py:605` instead — binary present,
`uv` or `git` unresolvable — and construct `BwrapGateExecutor` directly in tests.

**Trap 14 — There are three sites that append a verification-derived record, and
the obvious fix wires one.** FR-013. `factory/workgraph/workflow.py:2095` is the
one every reader finds, because it is the one in `_run_node`'s ladder loop. The
other two are `factory/workgraph/workflow.py:2885` — inside
`factory/workgraph/workflow.py:2837` — `_apply_external_completion_if_present` —
and `factory/workgraph/workflow.py:4017` — inside
`factory/workgraph/workflow.py:3879` — `_recovery_attempt`. Both call
`self._verify` first (`factory/workgraph/workflow.py:2871`,
`factory/workgraph/workflow.py:4005`), so both run the same gates through the same
activity on the same host, and both leave `pre_agent` False. The hand-back writes
`resolved.node.persona`; the recovery writes the persona its fork selected, the
node's own on a clean re-sync (`tests/test_rung_resolves_its_own_model.py:183` is
that path) and the debugger's on a conflicted one. So
`factory/verify/ladder.py:368` — `_attempts_spent` counts the hand-back and every
clean-re-sync recovery — the debugger's cycle is excluded on its own rung, which
is why US2-S7 drives the clean fork. A fix
that sets the reason at 2095 alone leaves FR-005 false on two of the three paths
while the ledger row it declares — "a boundary gate that never started is still
recorded as a FAIL and still charges the node a rung" — stays true on them; a fix
that wires two of the three leaves it true on the third, which is the same defect
one third smaller. That
is the 100/092/118 half-fix shape, at the level of a single `if`. Derive the reason
**once**, from `result.gate_results` through the FR-004 predicate, and pass it at
all three appends. Two scenarios hold the two non-loop sites and nothing else
here does: US2-S7 the recovery, US2-S8 the hand-back. The operator sequence below
drives the ladder loop alone — a worker host cannot be held in a
boundary-refusing state across an operator's hand-back — so those two paths are
proven by committed test or they are not proven.

## Sizing

**US1** touches `factory/verify/gates.py` (one field on `ExecutionOutcome`, two
refusal sites, one branch in `_to_result`) and `factory/verify/models.py` (one
`GateStatus` member and one predicate beside `gates_passed`). Under sixty
production lines. Its tests go in a new module that **constructs
`BwrapGateExecutor` itself** — the module attribute at
`tests/test_101_declared_caches.py:363` is the seam for the binary, but the
resolution helper beside it is not the route (trap 13) — and are pure unit calls
into `_to_result` and `gates_passed` for the rest.

**US2** touches `factory/verify/models.py` (the reason field on `AttemptRecord`,
its constants, the new dial on `VerificationConfig`),
`factory/verify/factory_yaml.py` (three registrations),
`factory/verify/ladder.py` (`_attempts_spent`'s predicate, the two new
tail-counting functions, one branch in `next_action`, one branch in
`exhausted_bound`) and `factory/workgraph/workflow.py` (one shared derivation of
the reason, set at all three append sites — `factory/workgraph/workflow.py:2095`,
`factory/workgraph/workflow.py:2885`, `factory/workgraph/workflow.py:4017` — plus
the fail-safe default). Four production files and roughly a hundred and twenty
lines: it is the largest story here, and trap 5 is why it is not split. Its nearest
landed comparable is 095-US2 (84ffa26) at 448 insertions / 33.6 KB, which built the
same exclusion, tail counter, dial and three registrations; this one adds two more
append sites and reuses the `ExhaustedBound` machinery 095-US3 built, so the
estimate lands well under the 64 KiB bound.

**US3** touches `factory/workgraph/workflow.py` alone — one `AttemptRecord`
append in the answered branch of the question path, using the constant US2
added.

**US4** touches `factory/notify/messages.py` alone.

US1 and US2 share `factory/verify/models.py`; US2 and US3 share
`factory/workgraph/workflow.py`. Both pairs carry a declared `depends_on_merged`
edge, so neither pair is ever in flight at once. **US4 shares no production file
with any other story** and is the only one that could run beside them.

All four are well inside the 64 KiB deterministic diff bound (D-050,
`factory/verify/diffbounds.py`): the largest is US2 at four files of small edits
plus three test modules — the two ladder ones and the workflow-driven pair
(T018 in `tests/test_rung_resolves_its_own_model.py`'s scripted world, T018b in
`tests/test_external_completion.py`'s), each a copy of a test that already exists
with its gate results swapped — and the pasted evidence each verification task
asks for is a few dozen lines of rendered text, not a transcript.

## Verification the operator will run, independent of the gate

Per constitution VIII and D-037 the judge sees the diff and the criteria only, so
runtime evidence must be committed as pasted output. Beyond that:

1. **First, falsify the reproduction that looks obvious** (trap 13). With `bwrap`
   moved aside, run one line against the installed package on the worker host —
   `python -c "from factory.verify.gates import resolve_gate_executor;
   print(type(resolve_gate_executor('<a worktree>')))"`. It must print
   `SubprocessGateExecutor`. That is the proof that removing the binary reproduces
   nothing here: the gates fall back to the host, and the *agent* refuses instead
   (`factory/workgraph/adapter.py:675`), which pages on `max_pre_agent_failures`.
   Restore `bwrap` before anything else.
2. **Drive the reachable arm end to end.** With `bwrap` present, dispatch one story
   with `max_attempts` deliberately below the new dial — 2 against 4. While that
   node's agent is still running (before it reaches VERIFYING, readable from
   `ergane build status <epic>`), move the `uv` binary out of every directory
   toolchain discovery searches; restore it as soon as the node's verification has
   failed once. The agent launched before the move, so it finishes and produces a
   diff, and the boundary then refuses at `factory/verify/gates.py:605`. Read
   `ergane build status <epic> --json`: that attempt's record under
   `nodes.<node>.history` must carry the new reason field, and the ordinary
   allowance must not have moved — the node must still get its two genuine
   attempts afterwards. Read the JSON, not the rendered line and not `ergane build
   attempts`: neither shows the history, and `attempts` shows no gate row at all
   (trap 12). Also read the escalation when it comes: its per-gate line
   (`factory/notify/messages.py:581` — `_gate_line`) must show the new status
   rather than `FAIL`.
   **The dial's other half, checked separately** because a host cannot be held in
   that state for four consecutive attempts: declare the new dial in the target
   repo's `ladder:` block (`ergane.yaml:100` is where this repository's own block
   starts) and load it through the loader the worker uses —
   `python -c "from factory.verify.factory_yaml import load_factory_config;
   print(load_factory_config('ergane.yaml').ladder)"`. The declared value must come
   back, and a value outside `factory/verify/factory_yaml.py:163`'s bounds must be
   refused by name. A dataclass default passes neither check.
3. With `bwrap` and the toolchain both in place, break one gate command instead
   (point it at a binary that does not exist so the command itself exits 127), and
   confirm the node **does** spend
   its rungs and escalates on `max_attempts`. This is the control for trap 2, and
   it is the step that fails if the implementation branched on the exit code.
4. Dispatch a story whose plan mandates a stop-and-ask, answer the question, and
   read `ergane build status <epic> --json`: the node's `history` must hold a
   record for the parked attempt whose reason names the pause and whose verdict
   is `FAIL`. The rendered line will read `attempt 2` — that is the dispatch
   counter, not a rung (trap 12), and the reading that settles it is the ladder's
   own: with `max_attempts` at 2, the node must still get two genuine attempts
   after the answer before it escalates. Then let a second question expire
   unanswered and confirm that one **does** spend a rung — the escalation arrives
   one genuine attempt earlier.
5. Force an escalation with two or more attempts behind it and read the message an
   operator actually receives: each attempt line must state its elapsed time and
   the history must state the span across all of them.

Step 1 is the one to run first and the one to believe: it costs a minute and it
stops an afternoon spent "reproducing" a defect the tree cannot produce that way
(trap 13). Step 2 proves the new exclusion exists on the arm production reaches.
Step 3 is the falsifiable test of the whole spec — the only step that proves the
exclusion did not swallow the failures it was never meant to excuse.
