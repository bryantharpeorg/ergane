# Ergane

An agentic software factory that builds itself: Spec Kit specs in, merged and verified
code out, with no human-written production code. This file is the project's vocabulary —
what the words mean, and which word to use when several are floating around. It is a
glossary and nothing else; behaviour lives in
[`.specify/memory/constitution.md`](.specify/memory/constitution.md) (normative),
[`docs/architecture.md`](docs/architecture.md) (descriptive), and
[`docs/decisions.md`](docs/decisions.md) (immutable log).

## Language

### The unit of work

**Epic**:
One spec's worth of work, driven end to end by a single `EpicWorkflow` execution.
_Avoid_: feature, project, sprint

**Node**:
One user story's unit of dispatch within an epic — the thing an agent is given.
_Avoid_: task, job, ticket

**Attempt**:
One agent run at one node, bracketed by a virtual key and closed by a teardown.
_Avoid_: try, retry, run

**Ladder**:
The bounded sequence of attempts a node may spend before it is terminal.
_Avoid_: retry policy, budget

**Persona**:
A named role — implementer, judge, architect, debugger — that selects a model, a write
scope, and a timeout. A persona is not a model; swapping the model behind a persona
leaves the persona intact.
_Avoid_: agent type, model tier, seat

### Dependencies and landing

**Pass-edge** (`depends_on`):
An ordering-only dependency: the predecessor must reach a verdict, and nothing about its
code is guaranteed to be present.
_Avoid_: dependency, blocker

**Merge-edge** (`depends_on_merged`):
A content dependency: the predecessor's work must be *merged* before the dependent's
worktree is created, so the dependent's base contains that code.
_Avoid_: hard dependency, strict edge

**Base pin**:
The commit a node's worktree was created from — the fetched head of the remote's default
branch, captured once at first dispatch and reused across that node's attempts.
_Avoid_: base, HEAD, checkout

**Landing**:
A node's journey from verdict to merged: push, PR, queue, required checks, merge.
_Avoid_: deploy, release, ship

**Salvage**:
Preserving an attempt's committed work on its branch before the worktree is swept, on
every terminal path including failure.
_Avoid_: backup, stash

**Promotion**:
An operator's deliberate fast-forward of `main` to the factory's branch at a milestone.
Distinct from **landing**, which is what the factory does on its own branch.
_Avoid_: release, merge to main

### Verification

**Gate**:
A deterministic command declared in `factory.yaml` whose exit status decides green. Gates
are the only thing a merge queue's required checks may run.
_Avoid_: test, check, CI

**Judge**:
The LLM that scores an attempt's diff against the spec's acceptance scenarios. It runs in
the inner loop, pre-CI, and never inside CI.
_Avoid_: reviewer, critic, evaluator

**Verdict**:
The judge's outcome for one attempt — PASS, RETRY, or FAIL.
_Avoid_: result, score

**Acceptance scenario**:
A Given/When/Then item parsed mechanically from a spec's story; the unit the judge scores
against.
_Avoid_: test case, requirement

### Reconciliation

**Attested landing**:
A story treated as landed because its spec's frontmatter says `state: landed`, baselined
at the commit that wrote the attestation.
_Avoid_: assumed, declared

**Observed landing**:
A story known to be landed because a commit reachable from the default branch carries its
attribution in the subject.
_Avoid_: real, actual

**Fingerprint**:
A story's judgeable content — scenarios, implemented FR bodies, work-graph declaration —
pinned at a revision.
_Avoid_: hash, checksum, signature

**Delta**:
The compiled workgraph of work that remains for a spec, plus the provenance explaining
what was subtracted and why.
_Avoid_: diff, backlog

**Remainder**:
The delta of a spec whose epic closed with some stories landed and some not.
_Avoid_: leftovers, rest

### Attention

**Question**:
A blocked agent's request for information, routed to the operator; answering it costs the
node no attempt, and it parks rather than fails.
_Avoid_: escalation, prompt

**Escalation**:
A decision the factory cannot make, offered to the operator as buttons with a one-hour
expiry. Distinct from a **Question**: an escalation asks for a *choice*, a question asks
for *knowledge*.
_Avoid_: alert, notification

**Park**:
A non-terminal wait: the node keeps its place and its remaining attempts.
_Avoid_: pause, block, hang

### Knowledge

**Binding rule**:
A constraint that must change how future code is written, so it lives in the standards
document implementer agents are told to read and obey. Promoted only after a defect class
recurs.
_Avoid_: guideline, best practice

**Lesson**:
Something learned that helps the operator agent reason but binds no implementer; it lives
in cross-session memory and reaches code only when an operator writes it into a spec's
plan as a trap.
_Avoid_: rule, convention

**Finding**:
One open, recurrence-tracked defect or risk in the doctor's ledger, carrying its
mechanism and its evidence.
_Avoid_: bug, issue, ticket

**Trap**:
A named hazard written into a spec's plan so the implementer meets it as scope rather than
as a failure.
_Avoid_: warning, note, gotcha

**Standards document**:
The one committed file `factory.yaml` names, whose path prompt assembly tells every
attempt to read and obey. Ergane's is its constitution.
_Avoid_: style guide, docs

## Relationships

- An **Epic** contains one or more **Nodes**; a **Node** spends one or more **Attempts**
  up to its **Ladder**'s bound
- A **Node** runs under exactly one **Persona**; a **Persona** may serve many nodes
- An **Attempt** produces a **Verdict** only after its **Gates** pass — a red gate is
  never judged
- A PASS **Verdict** begins a **Landing**; every terminal attempt is **Salvaged** first
- A **Merge-edge** guarantees the dependent's **Base pin** contains the predecessor's
  merge; a **Pass-edge** guarantees nothing about content
- **Attested** and **Observed landings** are both landings; a spec may carry a mix, and
  each **Node** resolves on its own evidence
- A **Delta** is computed from a spec's text and its **Landings**; a **Remainder** is the
  delta of a partly-landed spec
- A **Finding** that recurs may be promoted to a **Binding rule**; a **Lesson** reaches
  code only by becoming a **Trap** in some spec's plan
- **Promotion** moves `main`; **Landing** moves the factory's branch. The queue is never
  retargeted at `main`

## Example dialogue

> **Operator:** "us3 and us4 both have their dependencies landed, so they can run as a
> concurrent pair."
>
> **Factory:** "They have no **Pass-edge** left, but they both edit key issuance, so they
> need a **Merge-edge** between them — otherwise the second one's **Base pin** won't
> contain the first one's code and the **Landing** collides in the queue."
>
> **Operator:** "Fine. And 006's stories are landed, so the **Delta** gives me just those
> two?"
>
> **Factory:** "No. 006's stories are **Attested** at best — they merged before the queue
> existed, so no commit carries their attribution and there is no **Observed landing** to
> subtract. The **Remainder** would re-emit all five."

## Flagged ambiguities

- **"landed" vs "shipped"** — used interchangeably on an early status board, implying two
  degrees of done. Resolved: there is one terminal state, **landed**. How the code got
  there (bootstrap, or built by the factory through a **Landing**) is provenance, recorded
  separately, never a second status.
- **"landed" as spec state vs story fact** — a spec's frontmatter `state: landed` is an
  **Attestation** about the whole spec; a story's landing is a per-**Node** fact read from
  git. A spec can be attested landed while one of its stories has no **Observed landing**.
- **"dependency"** — meant both **Pass-edge** and **Merge-edge** in early specs, which is
  how a dependent came to be dispatched against a base that did not contain the code it
  imported. Always say which.
- **"question" vs "escalation"** — both reach the operator's phone, so they were conflated.
  A **Question** asks for knowledge and costs no attempt; an **Escalation** asks for a
  choice and expires in an hour.
- **"cap", "budget", "quota", "breach"** — forbidden in component identifiers and
  non-docstring strings while budget enforcement stays deferred, and asserted by a sweep
  test. Say **bound** or **limit**. A requirement that puts a forbidden word in an
  implementer's mouth will fail its own gate.
- **"rule" vs "lesson"** — used interchangeably for anything learned. Resolved above: a
  **Binding rule** constrains implementers and is versioned; a **Lesson** informs the
  operator agent and is not.
