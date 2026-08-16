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
