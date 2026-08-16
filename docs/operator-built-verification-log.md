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
