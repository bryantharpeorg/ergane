# Operator-built stories awaiting a judge

Stories in this log were built or finished by an operator session rather than by
a dispatched implementer, landed through the normal path — deterministic gates,
a `factory/<epic>/<node>` branch, a titled pull request, the merge queue — and
merged **without an LLM judge verdict**, because no judge model was reachable at
the time.

That is the whole reason this file exists. A merged story normally carries two
independent signals: the gates say the code runs, and the judge says the code
answers the acceptance criteria it was dispatched against. These stories carry
only the first. This log is the debt register for the second, and it is written
*before* the judge runs, so that the review has something specific to judge
rather than an invitation to re-read a night's work.

Each entry states what landed, what evidence exists, and — the part that matters
— **what a judge would have checked and did not**. If you are the judge, read
that last section first.

## How to discharge an entry

Judge the merged diff against the acceptance scenarios quoted in the entry.
Nothing else is admissible: a judge sees the diff and the criteria, never the
base tree, the commit message or a terminal (constitution VIII, D-037). On PASS,
mark the entry discharged with the date and where the verdict came from. On
anything else, file a finding and open a follow-up story — do not edit landed
code in place from this log.

## Why the count matters

Every entry here is also an occurrence on the finding
`verify/operator-completed-a-story-externally`. That counter is the early
warning the escape hatch was designed to need: operator completion is meant to
be a deliberate, rare release valve for a stuck story, and its failure mode is
quietly becoming the way work gets done. If this count climbs faster than the
factory's own landings, the hatch has become the default and something upstream
is broken.

---

## 033-ergane-install / US2 — install proves every connection

| | |
| --- | --- |
| Landed | PR #83, branch `factory/033-ergane-install/us2` |
| Built by | the dispatched implementer; six commits, unmodified, rebased onto buildout by the operator |
| Judged | **no** — no judge model reachable |
| Blocked because | Ollama account weekly usage limit, 2026-08-15 20:08 CT |

### Why this landed by hand

The node did not fail on merit. It failed four attempts at the test gate on
**eight tests its own diff never touched** — `tests/test_us3_boundary.py` and
`tests/test_us4_boundary.py`, which belong to 011. This was the first epic whose
gates ran inside the bubblewrap boundary, and the boundary lacked a git identity
(`fatal: unable to auto-detect email address`) and the agent-runner install
directory (`bwrap: Can't find source path .../share/claude/versions/2.1.223`).
Both were fixed in PR #82. The relaunched attempt then died on a provider 429
before it could write anything, and the operator killed the epic.

So the work was complete and correct before any of that. Rebasing it forward and
landing it is a verification job, not a build job — which is exactly the case the
hatch is cheapest for.

### Evidence

Gates run inside the real `BwrapGateExecutor`, the same boundary the factory
uses — not a host run:

```
test: PASS exit=0 241.1s
2396 passed, 44 skipped, 4 warnings in 240.58s (0:04:00)
```

Baseline `ergane-buildout` at `a7d9a22` is `2378 passed, 44 skipped`, so this
story adds 18 tests and breaks none.

### What a judge would have checked, and did not

The acceptance scenarios, verbatim from `specs/033-ergane-install/spec.md`:

1. **Given** all five subsystems reachable, **When** `ergane install --verify`
   runs, **Then** every finding passes, each names what it actually did (not
   "ok" — "completed a 1-token completion against persona `implementer`"), and
   the exit code is 0.
2. **Given** Temporal reachable but the declared namespace absent, **When**
   verify runs, **Then** the temporal finding fails naming the namespace and the
   command that would create it, while the other four findings still render —
   one failure never masks the rest.
3. **Given** an escalation transport configured, **When** verify runs, **Then** a
   test message is delivered through it and the finding names the transport and
   what was delivered; the finding also records that lifecycle verification
   arrives with 041, so the operator reads a deferral rather than a pass that
   covered less than it appeared to.
4. **Given** any probe whose target does not answer, **When** verify runs,
   **Then** that probe fails within its declared timeout with the timeout named
   — hanging is a defect, not patience.
5. **Given** a subsystem declared `none` (memory or telemetry), **When** verify
   runs, **Then** that subsystem renders an explicit skipped-by-declaration
   finding — the operator sees the absence was chosen, not missed.

And FR-006: probe every declared subsystem with a gather/judgment split, render
one finding per check in the doctor's findings grammar, bound every probe by an
explicit timeout, let no failure mask another, exit non-zero on any failure,
render skipped-by-declaration for `none`, and say so in the detail when a check's
full proof is deferred to a later epic.

The operator's own read of the diff found each of these represented — the five
probes split `gather()` from `evaluate()`, the orchestrator turns each probe's
exception into that probe's own finding and continues the loop, the exit code is
`0 if all(f.passed ...) else 1`, and the escalation finding appends the 041
deferral to its detail. **Treat that reading as a claim, not a verdict.** It was
made by the same session that landed the code, which is precisely the
independence a judge exists to supply. Specifically unexamined by anyone else:

- whether each passing finding's detail really *names what it did* to scenario
  1's standard, rather than being merely non-empty;
- whether the Temporal failure detail names **the command that would create the
  namespace**, which scenario 2 requires explicitly;
- whether the live-double coverage (`T018`) truly executes every probe's real
  `gather()`, or whether one path is still reached only through a fake;
- whether the timeout in scenario 4 is enforced by the probe's own bound rather
  than incidentally by the client library's default.

---

## 046-operator-status-cli / US2 — the roadmap verbs can see schedule-driven runs

| | |
| --- | --- |
| Landed | PR #85, branch `factory/046-operator-status-cli/us2` |
| Built by | a subagent implementer dispatched by the operator session |
| Judged | **no** — no judge model reachable |
| Blocked because | Ollama account weekly usage limit, 2026-08-15 20:08 CT |

### Evidence

Gates inside the real `BwrapGateExecutor`:

```
test: PASS exit=0 240.2s
2398 passed, 44 skipped, 4 warnings in 239.59s (0:03:59)
```

And, unusually for this log, **an A/B against production**. Same command, same
live paused `ergane-roadmap` schedule, only the code differing:

```
$ ergane roadmap status specs          # ergane-buildout at a7d9a22
ergane: no roadmap 'specs' is running here (looked for workflow id roadmap-specs)

$ ergane roadmap status specs          # this branch
schedule: ergane-roadmap (paused)
run: roadmap-specs-2026-08-15T09:40:00Z
next tick: 2026-08-15T20:00:00+00:00
roadmap: running
concurrency: 2 epic(s), 1 node(s)
```

That refusal is the filed defect, reproduced on the real system and then gone on
the real system. It is the strongest evidence any entry in this log carries, and
it is worth naming why: it is not a claim about a test, it is the behaviour of
the deployed thing.

### What a judge would have checked, and did not

US2-S1 the newest run reported with both the run id and the owning schedule
named; US2-S2 the schedule paused, proven by reading it back, with human output
saying *schedule* rather than merely *run*; US2-S3 resume symmetric; US2-S4 a
bare workflow with no schedule behaving byte-identically to today; US2-S5 a
refusal naming everything it looked for — the bare id, the schedule, the run
prefix.

The story carries its own control (`test_control_the_bare_rung_alone_reproduces_the_2026_08_15_refusal`,
which cuts `LOOKUPS` back to the pre-046 rung against an identical floor and
reproduces the historical refusal verbatim) and asserts the trap directly
(`pause` asserts `client.signals == []`). Both are strong. What no independent
reader has checked:

- whether US2-S4's "byte-identical" claim holds for **every** verb and flag
  combination, or only for the four the tests exercise;
- whether the fake client's `ScheduleActionStartWorkflow` objects are faithful
  enough that a real server could still diverge — the time-skipping test server
  implements neither schedules nor workflow listing, so nothing in CI exercises
  rungs 2 and 3 against real Temporal. The operator's live A/B above covers
  `status`; **`pause` and `resume` against a real schedule remain unexercised
  outside the fake**, because running them would have toggled the live roadmap.

---

## 045-judge-diff-hygiene / US1 — a diff carrying ignore-pattern paths fails before the judge

| | |
| --- | --- |
| Landed | PR #86, branch `factory/045-judge-diff-hygiene/us1` |
| Built by | a subagent implementer dispatched by the operator session |
| Judged | **no** — no judge model reachable |
| Blocked because | Ollama account weekly usage limit, 2026-08-15 20:08 CT |

### Evidence

Full suite `2397 passed, 44 skipped, 4 warnings in 260.51s`.

Operator probe, run against a throwaway repository carrying **this
repository's real `.gitignore`**, committing an agent home exactly as the
2026-08-14 incident did:

```
runtime root prefixes: ('.ergane', '.factory')
changed paths: ['.ergane/homes/033-ergane-install/us2/.claude/projects/session.jsonl', 'real_work.py']
violations: 1
  .ergane/homes/033-ergane-install/us2/.claude/projects/session.jsonl  <-  .gitignore:17:.ergane/
```

The story's own diff also survives the check it adds.

### What a judge would have checked, and did not

US1-S1 a committed session home fails the output check and the judge is never
asked; US1-S2 a tracked ignored file is named with both its path and the pattern
that refused it; US1-S3 an ordinary diff produces today's `OutputCheck` byte for
byte; US1-S4 untracked ignored noise is neither a diff nor a violation; US1-S5
and FR-008 leave read-scope nodes untouched; FR-006 nothing fails open.

Two things are unusually well proved here and should not be re-litigated: trap 1
is *executed* rather than cited (a tracked ignored file committed with
`git add -f`, then both `check-ignore` forms asserted), and FR-006's fail-closed
path uses real git rather than a monkeypatch. What no independent reader has
checked:

- whether the byte-parity claim in US1-S3 covers the `OutputCheck` shapes
  produced by every write scope, or only the two the tests construct;
- whether preferring the ignore rule over the runtime-root prefix is the right
  precedence — it is defensible and documented, but it means this repository
  reports `.gitignore:17:.ergane/` where a repo without that pattern reports
  `runtime root: .ergane/`, so the message an operator sees depends on the
  target repo's own config;
- **a known gap, already flagged by its author**: `notify/messages.py` still
  renders a bare `output check: FAILED` for a hygiene failure, because rendering
  the evidence belongs to US3. Until US3 lands, the escalation message is the one
  place a hygiene failure reaches a human without its reason.

---

# Verdicts, 2026-08-15

The debt above was discharged the same night it was incurred. An OpenRouter key
arrived around 21:20 CT, which made a judge reachable again — not the house
judge (`ollama-cloud/glm-5.2`, still behind the weekly cap) but
`deepseek/deepseek-v4-pro-0813`, a third model family, distinct from both the
implementer that wrote most of this work and the Claude models that finished it.

Nothing here re-implements judging. `run_judge` takes its endpoint, key and model
as arguments precisely so a caller can point it elsewhere, so these are the
factory's own prompt, parser and verdict grammar, aimed at a different host. The
verdicts are the real article, not an approximation of one.

| story | verdict |
| --- | --- |
| 045-judge-diff-hygiene / US1 | **PASS** — 5 of 5 scenarios |
| 046-operator-status-cli / US2 | **PASS** |
| 046-operator-status-cli / US3 | **PASS** — 3 of 3 |
| 044-prompt-assembly-preflight / US1 | **RETRY** — US1-S2 not satisfied |
| 033-ergane-install / US2 | **RETRY** — US1-S1 and US1-S4 not satisfied |

## What this exercise proved about self-reading

Two of the five came back with failures, and **both had been named in advance**
in this file's "what a judge would have checked and did not" sections. That is
the result worth keeping: the operator's read found every scenario *represented*
and the judge found two of them *unsatisfied*. Representation is not
satisfaction, and the reader who lands the code is not positioned to tell the
difference — which is the whole argument for an independent verdict, restated
with evidence rather than asserted.

The practical consequence: when a story lands unjudged, the "what a judge would
have checked" section is not documentation. It is the work queue.

## 033-ergane-install / US2 — two real defects, fix in flight

**US2-S1.** `TemporalProbe` never checks the namespace. It calls
`get_workflow_handle("ergane-install-verify")`, calls `describe()`, and maps
`RPCStatusCode.NOT_FOUND` to "the namespace is not registered" — but NOT_FOUND
there means the *workflow* is absent. Measured on the host the factory runs on:

```
$ temporal operator namespace describe -n factory
  NamespaceInfo.Name    factory
  NamespaceInfo.Id      d3e55ab2-5a0b-4735-9283-a66d4431ee5d

$ temporal workflow describe --workflow-id ergane-install-verify
  Error: failed describing workflow: workflow not found for ID
```

So `ergane install --verify`, on this machine, reports a namespace that
demonstrably exists as missing and tells the operator to create it. The landed
test passes only because it **seeds that workflow first** — a test that
manufactures its own passing condition, which is worse than no test at all.

**US2-S4.** No `asyncio.wait_for` around `Client.connect` or `describe()`. The
`elapsed >= timeout` branch is reached only *after* an exception surfaces, so an
address that accepts and never answers hangs past the declared bound. The
scenario's own words: "hanging is a defect, not patience."

Filed as `verify/operator-read-missed-what-the-judge-caught`. Fix in progress.

## 044-prompt-assembly-preflight / US1 — a spec question, not a code defect

The judge failed US1-S2 for the reason the implementer had already disclosed in
its own report: the committed test drives `check_prompt_assembly` directly
rather than running `ergane spec validate`, because a *freshly derived* graph
cannot contain a story whose section the assembler cannot find — `parse_spec`'s
heading grammar is strictly narrower than the assembler's, and the deriver
cross-validates every `implements` key against the spec. The spec.md half of
assembly only fires against a **committed** `workgraph.json` that has drifted
from the spec beside it, which is exactly what `ergane build start` dispatches
and exactly what `validate` does not read.

So implementer and judge agree on the facts and disagree on the conclusion: one
called the scenario unreachable, the other called it unsatisfied. Both are
right, which means the defect is in the scenario rather than in either of them.
US1-S2 as written describes behaviour the current contract cannot produce.

This is an operator decision, not a patch. Making `validate` read the committed
artifact would change what FR-001 means by "every node of the derived graph" —
a contract change that deserves a spec rather than a quiet amendment. Recorded
here, open, for that decision.
