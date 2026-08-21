---
state: draft
# Drafted 2026-08-20 ~6:00 PM CT by an operator session, at the operator's
# direction: "I want to add a way to factor in code quality in the scan as well
# ... perhaps the agent loop validates on both judge and a deterministic
# sonarqube style quality scan and either of those being too low can send it
# back for more work", then refined by two explicit decisions and one
# requirement added mid-draft.
#
# THE OPERATOR'S THREE DECISIONS, stated here so no implementer re-litigates
# them and no reviewer reads this spec as timid:
#
#   1. RECORD-ONLY FIRST. The scan runs, computes, and records. It does NOT
#      change a verdict. Thresholds come from a later spec, set against the
#      distribution this one measures. Chosen over gating-on-day-one because
#      dispatch rework is at 37.9% and flat across three weeks, so a new way to
#      fail would arrive as noise indistinguishable from signal.
#   2. DETERMINISTIC RULES ONLY, when gating eventually arrives. Lint
#      violations, type errors and security patterns -- checks where satisfying
#      them and gaming them are the same act. Complexity, duplication and
#      maintainability index are recorded and trended, never made to fail a
#      story. COVERAGE IS EXCLUDED ENTIRELY; see "What this spec refuses to
#      measure".
#   3. THE INTEGRATION IS A HOOK, NOT A HARDCODE. Added mid-draft: "i want these
#      integrations to be done in some sort of hook system so that they're
#      optional and easily swappable". This is why US3 exists and why the
#      registry, not the scanner, is the deliverable.
#
# WHAT WAS CHECKED BY RUNNING IT, 2026-08-20:
#
#   $ gh repo view --json visibility,nameWithOwner
#   {"nameWithOwner":"bryantharpeorg/ergane","visibility":"PUBLIC"}
#
# That answers the operator's open question ("github i believe also has code
# scanners now too, im not sure if theres a way to use theirs or if that
# requires a better account"). It does not require a better account: CodeQL code
# scanning is free for public repositories. It is nonetheless the WRONG SHAPE
# for this spec, and the reason is timing, not money -- see "Why GitHub's
# scanner is a backstop and not a step".
#
#   $ for t in ruff radon xenon pylint mypy bandit jscpd diff-cover; do ... done
#   all eight: not installed
#
# So no candidate scanner is present on this host, and Constitution III admits
# none of them. US1 exists to measure before that approval is spent.
#
# HELD AT DRAFT. 067-069 were flipped straight to `ready` and a twelve-agent
# pre-dispatch review then found 68 attempt-costing defects. That review is the
# rule now. This spec goes to `ready` only after it comes back clean.
---

# Feature Specification: a scanner the operator chooses runs in the loop

**Feature Branch**: `077-a-scanner-the-operator-chooses-runs-in-the-loop`
**Created**: 2026-08-20
**Status**: Draft

## The gap, stated precisely

Verification has exactly two instruments, and neither one measures.

A **gate** is deterministic and binary. It reports that `pytest` exited 1, with
32 KiB of tail. It cannot report that this diff added a function whose
cyclomatic complexity is 19 where the file's base was 7, because a `GateResult`
has no field for a number — `name`, `command`, `status`, `exit_code`,
`duration_s`, `output_tail` (`factory/verify/models.py:286-292`). Every gate
answer is a verdict already; nothing survives it that a later run could compare
against.

A **judge** measures, but it is an LLM. It is metered, it is
non-deterministic across runs, and its output is a scenario-by-scenario opinion
about acceptance criteria. Asking it "is the complexity acceptable" spends money
to get an answer that will not reproduce, on a question a parser can settle for
free.

Between them sits the whole of code quality, and nothing occupies it.

## A gate is the wrong place to put a threshold

The nearest workaround is a gate — `gates: {quality: "..."}`, non-zero exit
means FAIL. It needs no factory change at all, and it is the honest fallback if
this spec is never built. Three things make it unsuitable as the destination:

1. **Gate commands are read from the node's own worktree.** The verification
   loop is pinned at dispatch from the operator clone so a node cannot move it,
   but gate commands are deliberately left on the worktree side to preserve the
   CI backstop (`docs/architecture.md`, §6 step 2). A threshold on the worktree
   side is a threshold the agent being measured can edit.
2. **A gate result has no score.** Nothing to trend, nothing to ratchet against,
   nothing that reaches `ergane findings` or the rework trend.
3. **A gate is already a verdict.** There is no way to express "run this, record
   what it says, and change nothing" — which is precisely the first phase the
   operator asked for.

## Why GitHub's scanner is a backstop and not a step

GitHub code scanning is free here — the repository is public. It is still the
wrong instrument for the ladder, for a reason that has nothing to do with
licensing: **it is asynchronous and it lives after the fact.** It runs in
Actions, on a pushed ref, and uploads SARIF that lands in the Security tab
minutes later. The loop needs a verdict in the node's worktree, before the pull
request exists, while the ladder still has an attempt to spend.

Its natural home is exactly where the merge-group build already sits: a
post-merge deterministic backstop that catches what the loop missed. That is
worth having and it is not this spec.

The CodeQL *CLI* does run locally and synchronously and would be admissible as
an adapter under US3 — at the cost of a large pack download and a multi-minute
scan, which US1 is what measures.

## SARIF is the seam, not a bespoke plugin protocol

Every candidate — ruff, semgrep, bandit, the CodeQL CLI, and GitHub's own
upload path — converges on one format: SARIF 2.1.0, the OASIS standard GitHub
code scanning ingests. That is unusually lucky and this spec should spend it.

So the adapter contract is not "implement our interface". It is **run a command
in the worktree; leave SARIF behind; the factory reads it.** A scanner that
emits SARIF is swappable by editing one line of `factory.yaml` and installing a
binary. Only a scanner that needs real logic — one that talks to a server API,
say, or a SonarQube instance, whose native export is not SARIF — needs a Python
adapter, and the registry in US3 is where it registers.

## What this spec refuses to measure

**Coverage.** Named here as declared scope so no implementer adds it as an
obvious omission and no reviewer files it as a gap.

The same agent writes the code and the tests. A coverage number is the one
quality metric whose cheapest satisfying move is to write tests that assert
nothing, and this repository has already shipped four tests found structurally
unable to fail. A coverage gate does not detect that failure mode; it rewards
it. The judge, which reads what a test actually asserts, is the correct
instrument, and it already exists.

**Aggregate scores, as a gate.** Cyclomatic complexity, duplication ratio and
maintainability index are recorded by this spec and trended by US5. They are
excluded from any future gating decision because their cheapest satisfying moves
are `_helper_1`/`_helper_2` and a premature abstraction over two things that
should have stayed apart — both of which make the code worse while making the
number better.

## What this spec does not change

- **No verdict moves.** `OverallVerdict` composition is untouched. A scan
  reporting four hundred findings and a scan reporting none leave the attempt in
  exactly the state gates, diff check and judge left it. This is a property with
  tests, not a default with a flag.
- **No ladder change.** `ladder.next_action` does not learn about scans.
- **No new mandatory dependency.** A manifest that does not name `quality`
  imports no scanner module, installs nothing, and behaves byte-identically.
- **No threshold, anywhere.** Not in the manifest schema, not in the models, not
  behind a disabled flag. The follow-on spec adds them against measured data.
- **`personas.yaml`, gate execution, and the merge queue** are all untouched.

## User Scenarios & Testing

### User Story 1 - The operator learns which scanners survive this sandbox (Priority: P1)

Before Constitution III approval is spent on a dependency, somebody runs the
candidates and writes down what happened.

**Why this priority**: every later story's shape depends on facts nobody has.
Whether `ruff` emits SARIF under the flag its docs claim, what a scan costs in
wall-clock on a real node diff, and — the one that decides everything — whether
a scanner runs at all under bwrap `--clearenv` with no network and no writable
`HOME`.

**Independent test**: the committed research note names each candidate, the
exact command run, the exit code, the wall-clock, and whether SARIF came back
well-formed; a real SARIF file from each surviving candidate is committed beside
it.

**Acceptance Scenarios**:

1. **Given** no scanner is installed on this host and none is on the approved
   roster, **When** the spike runs candidates through `uvx` without editing
   `pyproject.toml`, **Then** no dependency is added to the project and the
   evidence is still produced.
2. **Given** a candidate scanner, **When** it is run inside the real bwrap
   sandbox the gates use — not a bare subprocess — **Then** the note records
   whether it succeeded, and if it failed, the exact failure.
3. **Given** a candidate that claims SARIF support, **When** its output is
   parsed, **Then** the note records the actual flag that worked, because a
   documented flag that does not exist is this repository's most expensive
   recurring defect class.
4. **Given** the spike completes, **When** it recommends a default scanner,
   **Then** the recommendation cites the measured wall-clock, because a scanner
   slower than the gates it follows changes the loop's economics.

---

### User Story 2 - A loop can name a quality step, and one that does not costs nothing (Priority: P1)

`verify:` grows a fourth step name.

**Why this priority**: nothing else can land without the step existing, and the
"costs nothing when absent" half is what keeps the factory portable into a
brownfield repo that wants none of this.

**Independent test**: a v2 manifest declaring `verify: [gates, diff_check,
quality, judge]` resolves; one omitting `quality` resolves to a configuration
byte-identical to today's and imports no scanner module.

**Acceptance Scenarios**:

1. **Given** a v2 manifest with `quality` in `verify:`, **When** it is parsed,
   **Then** the step is accepted and appears in the resolved order.
2. **Given** a manifest placing `quality` before `gates` or before
   `diff_check`, **When** it is parsed, **Then** it is refused by name — a
   scanner only ever reads work that already compiles.
3. **Given** a manifest placing `judge` before `quality`, **When** it is parsed,
   **Then** it is refused: the deterministic step runs first, so a red scan can
   skip a metered judge exactly as a red gate already does.
4. **Given** a manifest naming a scanner that is not in the closed set, **When**
   it is parsed, **Then** it is refused with the admissible names listed.
5. **Given** a manifest with no `quality` step, **When** the loop resolves,
   **Then** no scanner module is imported and no scanner configuration is
   required.
6. **Given** two manifests differing only in their scanner name, **When** each
   resolves, **Then** their `loop_digest` values differ — a PASS is a claim
   relative to a named definition of verified, and the scanner is part of that
   name.
7. **Given** a v1 manifest that declares `quality:`, **When** it is parsed,
   **Then** it is refused, matching how v1 already refuses `ladder:` and
   `verify:`.

---

### User Story 3 - A scanner is an adapter resolved by name (Priority: P1)

The hook system itself. This is the story the operator asked for.

**Why this priority**: it is the difference between shipping a SonarQube
integration and shipping the ability to swap one out. The factory already has
this pattern twice — `factory/notify/adapter.py` and
`factory/mergequeue/forge.py` — and both are lazy-import registries held to a
config's closed set in both directions by a conformance suite.

**Independent test**: a scanner registered under a name is returned by
`resolve_scanner(name)`; resolving a name outside the closed set raises with the
registered names listed; the module imports no scanner's dependencies at import
time.

**Acceptance Scenarios**:

1. **Given** the scanner registry, **When** the module is imported, **Then** no
   candidate scanner's package is imported — resolution is lazy, exactly as the
   messenger registry is, so a factory with no scanner installed still starts.
2. **Given** the built-in `sarif` adapter and a declared command, **When** it
   runs in a worktree, **Then** it executes the command, reads the SARIF file it
   left, and returns parsed findings — with no knowledge of which tool produced
   them.
3. **Given** the built-in `none` scanner, **When** it runs, **Then** it returns
   an empty report and touches nothing, so "configured but disabled" is
   expressible without editing `verify:`.
4. **Given** a scanner that exits non-zero, times out, or writes malformed
   SARIF, **When** it runs, **Then** the report records `scanner_unavailable`
   with the reason and **nothing raises** — a scanner that could not scan is
   data, exactly as an unreachable judge is, and exactly as a transport that
   could not send is.
5. **Given** the closed set in configuration and the registry's keys, **When**
   the conformance suite runs, **Then** they match in both directions, so a name
   the parser admits always resolves and a name it refuses never reaches the
   registry.
6. **Given** a scanner command that needs network or a writable cache, **When**
   it runs under the gates' sandbox, **Then** the failure is recorded as
   `scanner_unavailable` rather than surfacing as a mysterious empty report.

---

### User Story 4 - Findings are scoped to the diff, recorded, and change nothing (Priority: P1)

**Why this priority**: this is where record-only becomes a fact about the code
rather than a promise in a spec.

**Independent test**: an attempt whose scan reports findings and an attempt
whose scan reports none produce the same `OverallVerdict` for the same gates,
diff check and judge results; the evidence rows differ.

**Acceptance Scenarios**:

1. **Given** a scan reporting findings across the whole repository, **When** the
   report is scoped, **Then** only findings on lines this attempt's diff touched
   survive — a node does not inherit the debt of every node before it.
2. **Given** an attempt that adds a new file, **When** the report is scoped,
   **Then** every finding in that file survives, because all of it is new.
3. **Given** a scan reporting four hundred findings, **When** the verdict is
   composed, **Then** the verdict is identical to the same attempt with a clean
   scan. **The verdict function does not receive the quality report at all.**
4. **Given** a completed scan, **When** the verification row is written, **Then**
   it carries the scoped findings, the scanner name, and the scanner's own
   version string, so a later change in finding counts can be attributed to the
   code rather than to a scanner upgrade.
5. **Given** a scan that never ran because an earlier step already failed,
   **When** the row is written, **Then** the quality evidence is NULL — a
   different fact from a scan that ran and found nothing, mirroring how
   `judge_verdict` is NULL when the judge never ran.
6. **Given** a redelivered activity, **When** the row is upserted, **Then** it
   lands on the first run's row rather than duplicating evidence.

---

### User Story 5 - The recorded scans are queryable, so thresholds can be measured (Priority: P2)

**Why this priority**: without it, the record-only phase produces a table nobody
reads and the follow-on spec sets its thresholds by guess — which is the exact
failure this sequencing was chosen to avoid. `DIFF_INPUT_LIMIT` was set as "a
comfort margin, not a measurement", and its first false positive refused a
fully-green story four times.

**Independent test**: a command reports finding counts per attempt, per rule and
per story over a date range, against a store seeded with known rows.

**Acceptance Scenarios**:

1. **Given** a store with recorded scans, **When** the operator asks for the
   distribution, **Then** they get counts per rule, ordered by frequency, over a
   selectable window.
2. **Given** the same store, **When** the operator asks per story, **Then** they
   get findings per attempt, so "did the second attempt improve" is answerable.
3. **Given** rows written before this spec, **When** the query runs, **Then**
   they are reported as unmeasured rather than as zero findings.
4. **Given** a window in which the scanner name changed, **When** the query
   runs, **Then** the change is visible in the output, because counts either
   side of it are not comparable.

---

### Edge Cases

- **A scanner that is slower than the gates.** Recorded by US1, bounded by the
  same per-step timeout machinery the gates use. A scanner that hangs must be
  killed by process group, not by root PID, for the reason `gates.py` documents
  at length.
- **A scanner emitting SARIF with no `physicalLocation`.** Rule-level findings
  with no line cannot be diff-scoped. They are recorded and excluded from the
  scoped set, never silently mapped to line 1.
- **SARIF paths relative to a different root.** The URIs a scanner writes may be
  absolute, worktree-relative, or prefixed with `file://`. Normalise against the
  worktree root, and refuse to scope a finding whose path does not resolve
  inside it.
- **A diff that renames a file.** A finding on the new path is in scope; the old
  path no longer exists to scope against.
- **Two scanners declared.** Out of scope: one scanner per loop, by construction.
  The follow-on spec may compose; this one may not.

## Requirements

### Functional Requirements

- **FR-001**: The spike MUST run each candidate scanner without adding any
  dependency to `pyproject.toml`.
- **FR-002**: The spike MUST run each candidate inside the same sandbox the
  gates use, and record the result.
- **FR-003**: The spike MUST record, per candidate, the exact command, exit
  code, wall-clock, and whether well-formed SARIF was produced.
- **FR-004**: The spike MUST commit a real SARIF artifact from each surviving
  candidate as evidence.
- **FR-005**: `quality` MUST be an admissible `verify:` step name.
- **FR-006**: `quality` MUST be refused when ordered before `gates` or before
  `diff_check`, and `judge` MUST be refused when ordered before `quality`.
- **FR-007**: A `quality:` configuration block MUST name its scanner from a
  closed set, and MUST be refused by name otherwise.
- **FR-008**: A manifest omitting `quality` MUST resolve to a configuration
  identical to today's, and MUST import no scanner module.
- **FR-009**: The resolved scanner MUST contribute to `loop_digest` and
  `loop_summary`.
- **FR-010**: The `quality:` block MUST be pinned at dispatch from the operator
  clone, never read from the node worktree.
- **FR-011**: A v1 manifest declaring `quality:` MUST be refused.
- **FR-012**: Scanners MUST be resolved by name from a registry, with the
  scanner's own dependencies imported lazily at resolve time.
- **FR-013**: The registry's keys and the configuration's closed set MUST be
  held equal in both directions by a conformance test.
- **FR-014**: A built-in `sarif` adapter MUST run a declared command in the
  worktree and parse the SARIF it leaves, without knowledge of the producing
  tool.
- **FR-015**: A built-in `none` scanner MUST return an empty report.
- **FR-016**: A scanner that fails, times out, or emits unparseable output MUST
  produce a `scanner_unavailable` report and MUST NOT raise.
- **FR-017**: Findings MUST be scoped to lines the attempt's diff touched; all
  findings in a file the attempt created are in scope.
- **FR-018**: A finding with no resolvable location inside the worktree MUST be
  recorded and excluded from the scoped set.
- **FR-019**: The composed verdict MUST NOT depend on the quality report, and
  the verdict function MUST NOT receive it.
- **FR-020**: The verification row MUST carry the scoped findings, the scanner
  name, and the scanner's version string.
- **FR-021**: Quality evidence MUST be NULL when the scan did not run,
  distinguishably from an empty report.
- **FR-022**: Quality evidence MUST upsert on the existing attempt key.
- **FR-023**: An operator command MUST report finding distribution per rule, per
  story, and over a selectable window.
- **FR-024**: Pre-077 rows MUST report as unmeasured, never as zero.
- **FR-025**: A scanner-name change within a queried window MUST be visible in
  the output.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: []
  implements: [FR-005, FR-006, FR-007, FR-008, FR-009, FR-010, FR-011]
US3:
  depends_on: [US2]
  implements: [FR-012, FR-013, FR-014, FR-015, FR-016]
US4:
  depends_on: [US3]
  depends_on_merged: [US2]
  implements: [FR-017, FR-018, FR-019, FR-020, FR-021, FR-022]
US5:
  depends_on: [US4]
  implements: [FR-023, FR-024, FR-025]
```

US1 is genuinely independent: it adds no production code and its output is a
research note. Everything else is a chain, and the chain is real rather than
contentious — US3's registry is resolved by the name US2's parser admits, US4
scopes the report US3 produces, and US5 queries the rows US4 writes.

US4's `depends_on_merged: [US2]` is declared rather than left to the transitive
chain, and it is doing a second job: US2 and US4 both edit
`factory/verify/models.py`, so a race would see whichever landed second rejected
for the other's change. `ergane spec validate` infers this contention; declaring
it makes the wait a decision instead of an accident.

The chain is the reason this spec is five stories rather than three. Collapsing
US2 into US3 was considered and rejected: a parser change and a registry are
different enough that a single agent doing both is the shape that produced this
repository's most expensive story.

## Success Criteria

### Measurable Outcomes

- **SC-001**: A manifest omitting `quality` produces a verification run whose
  behaviour and `loop_digest` are unchanged from before this spec.
- **SC-002**: Swapping the scanner requires editing one line of `factory.yaml`
  and installing a binary — no factory code change.
- **SC-003**: For any fixed set of gate, diff-check and judge results, the
  composed verdict is identical for a clean scan and a four-hundred-finding
  scan.
- **SC-004**: A scanner that cannot run leaves a recorded reason, and the
  attempt's verdict is what it would have been with no scanner configured.
- **SC-005**: After the record-only period, the operator can produce a
  per-rule finding distribution from the store without writing SQL by hand.
- **SC-006**: No new dependency is added to `pyproject.toml` by US1.

## Assumptions

- The candidate scanners' SARIF support is assumed but **not** verified; US1
  exists to verify it, and every later story's default scanner is whatever US1
  recommends rather than whatever this spec guesses.
- SonarQube proper is assumed to need a running server and to lack first-class
  SARIF *export*. If US1 finds otherwise, it is admissible under US3's registry
  like anything else; the operator named it as an example, not a requirement.
- The follow-on gating spec is assumed, not scheduled. If it is never written,
  this spec still pays for itself as measurement.
