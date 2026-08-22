---
state: draft
# HELD AT DRAFT. Drafted 2026-08-21 ~5:35 PM CT by an operator session, at the
# operator's instruction, tree at dcc854d (ergane-buildout), byte-identical to
# origin. No ready flip, no derive, no dispatch until the operator says so: this
# spec changes what "green" means for every target repo, and that is a decision
# he takes deliberately rather than one a scheduler takes for him.
#
# WHAT THIS IS. On 2026-08-19 a consumer built against Ergane on a target repo
# whose own `factory.yaml` declared a gate running `python3 -m compileall`. The
# gate wrote `src/__pycache__/*.pyc` into the node's worktree. The agent
# committed them. Four `.pyc` files landed in US1's diff, which no human read.
# The reporter was scrupulous that the gate was theirs and the mistake was
# theirs. It is filed anyway, and correctly: **the factory let a verification
# step mutate the thing being verified, and said nothing.**
#
# THE MEASUREMENT, read out of the tree rather than remembered. The ordering is
# the whole defect and it is fifteen lines of `factory/workgraph/workflow.py`:
#   :2114  `gate_results = await workflow.execute_activity(`
#   :2115  `run_gates,`
#   :2116  `RunGatesInput(worktree_path=prepared.path),`
#   :2122  `output = await workflow.execute_activity(`
#   :2123  `check_output,`
#   :2125  `worktree_path=prepared.path,`  <- the worktree the gates just ran in
#   :2127  `# Work is measured from where the node began (D-027): the agent`
#   :2128  `# commits as it goes, so HEAD has moved with the work.`
# Gates run, then the diff is measured, in the same worktree, in that order.
# Anything a gate wrote is inside the thing `check_output` then measures.
#
# AND THE SANDBOX IS NOT WHERE THIS GETS FIXED. `factory/verify/gates.py:628-630`
# binds the worktree's parent read-only and **the node worktree itself writable**,
# on purpose, with the reason in the comment above it. The remedy is observation,
# not prevention.
#
# WHAT IS ALREADY FIXED, so no implementer rebuilds it. Ignored files already
# stay out of the judge's input — `worktree.diff`
# (`factory/workgraph/worktree.py:1006-1007`) says so in as many words — and a
# path that reaches the diff and should not have is already refused with its rule
# quoted to the next attempt (`factory/verify/diffcheck.py:262-290`,
# `factory/workgraph/prompt.py:764`). The hole between them is exactly this: a
# gate writing a path the target repo does NOT ignore. The consumer's `.pyc`
# files were committed, which proves their repo did not ignore them.
#
# LIVE PROBE RUN AT DRAFT TIME, not read from docs. A scratch-index tree hash
# (`GIT_INDEX_FILE=<tmp> git add -A && git write-tree`) over a repo whose
# `.gitignore` names `__pycache__/`:
#   base:            41550e0d1d1561a567c2386cd66050500e0771bb
#   after ignored:   41550e0d1d1561a567c2386cd66050500e0771bb   <- unchanged
#   after untracked: 23a425340c976150f9fbe57c2299ac764bb67e08
#   git diff-tree -r --name-only <base> <after>  ->  untracked_new.txt
# And the same mechanism caught a rewrite of an already-modified tracked file,
# which `git status --porcelain` cannot see because the porcelain line is
# byte-identical before and after. That is the measurement this spec is built on.
#
# THE TWO FINDINGS ARE ONE DEFECT, FILED TWICE. Two reporters filed the same
# mechanism on the same day at two severities. This spec closes both, and says
# so rather than leaving a duplicate open behind it.
#
# Filed as:
#   verify/gates-can-mutate-the-worktree-they-gate                    CRITICAL, open
#   verify/a-gate-that-dirties-the-worktree-changes-the-diff-it-is-
#     measuring                                                       WARNING,  open
#
# NOT filed here, and named out of scope below: verify/a-warm-pycache-suppresses-
# compile-time-warnings-so-warning-counts-are-not-comparable. Same surface,
# different consequence — that one is about comparability between runs, this one
# is about a gate mutating its own subject.
#
# CROSS-SPEC CRITIC PASS APPLIED 2026-08-21 ~6:55 PM CT. STILL HELD AT DRAFT —
# this pass changed no state and asks for no dispatch. A critic read 084 beside
# 083 and 085 and the house exemplar; every line it cited was re-printed against
# dcc854d before anything moved here. The material rulings it forced:
#
#   - **US3 could have passed with the feature dead.** All four of its scenarios
#     ran against `_run_gate_list_from_config`, which is handed the whole
#     `FactoryConfig` and gets a new field for free. `_run_gate_list` — the
#     runner Ergane's own nodes take, decided by `if candidate_path.exists():`
#     at `factory/verify/gates.py:1135` — receives the declaration through
#     nothing: `_AcceptedConfig` (`factory/verify/gates.py:181-186`) carries
#     three fields and `_interpret_candidate` reads two keys. That is
#     `verify/readiness-proves-a-thing-is-declared-not-that-it-works`, filed
#     five times in this repository, sitting inside a spec written to close a
#     defect. **US3-S3, FR-012 and SC-011 now require both runners**, in the
#     shape US1-S4 already uses.
#   - **The declaration is named and shaped here.** Top-level `writes:`, keyed
#     by gate name, boolean value, in exactly the position and sparseness
#     `timeouts:` has. It was left open to the implementer and is not any more.
#   - **FR-010's evidence form is ruled**: a second scalar on `GateResult`
#     (`writes_declared`), not a flag on each path entry, and explicitly **not**
#     a third `GateStatus` member — a declared writer keeps PASS, and a new
#     status would force the one edit to `gates_passed` that trap 12 forbids.
#   - **SC-002 is no longer readable as a nested full-suite run.** Read
#     literally it was `uv run pytest -q` invoked as a gate, inside a gate run,
#     inside the node's own gate run; this host has already been OOM-killed by
#     orphaned test servers once
#     (`hardening/orphaned-test-servers-exhaust-host-memory`). It is a fixture
#     gate writing the same ignored paths, and the real suite control stays the
#     operator's, out of band.
#   - **SC-004 rules what a bwrap-less host may paste.** The node agent is
#     itself sandboxed, so nested bwrap is likely unavailable to it, and a bare
#     `SKIPPED` does not read to a judge as "produced four ways". A stub
#     `GateExecutor` carries the seam proof; the bwrap case is a skip whose
#     guard is named beside it.
---

# Feature Specification: a gate may not change what it measures

## The gap, stated precisely

A gate is a deterministic command a target repo declares in its own
`factory.yaml`. Gates are user-authored by design — that is the point of the
manifest — so "write no side effects" cannot be enforced by reviewing them.
Nothing today checks that a gate left the worktree as it found it.

The consequence has two sizes. The small one is what was measured: build noise
lands in a diff nobody reads. The large one is why this is filed CRITICAL: **a
gate that rewrites a source file silently alters what the judge scores.** The
judge is shown the worktree's diff against the node's base, assembled after the
gates have run — so a gate carrying a formatter, a codegen step or a `--fix`
flag changes the evidence and the verdict at once, and in a factory where no
human reads the diff there is no second line of defence.

## The rule this spec is asking for

**A verification step may not change what it is verifying, and when one does,
the attempt fails loudly, naming which gate wrote which file.**

### The ruling, made here rather than left to the implementer

Three shapes were available and this spec picks the third, with the first two
named so nobody re-litigates them mid-attempt.

- **Not a `HygieneViolation` on the output check.** `check_output` owns "which
  paths may not be in a diff". "Which gate wrote this" is a different question,
  and answering it there puts a second decider next to the one
  `factory/verify/diffcheck.py:171-176` warns about.
- **Not a synthetic `GateResult`.** A `name="gate-hygiene"` row would flow
  through the truth table for free, and would break `run_gates`'s promise of one
  result per *declared* gate (`factory/verify/gates.py:1094-1098`).
- **A marker on each gate's own result, plus a status.** The paths go on the
  `GateResult` for the gate that wrote them — the `concurrent_gates` shape
  (`factory/verify/models.py:301`), added with a default so no construction site
  breaks. And a gate that dirtied is reported with a status that is not PASS,
  which is what makes `gates_passed` (`factory/verify/models.py:490-492`) refuse
  it with no edit at all, and what makes the retry prompt render it: that loop
  `continue`s past every PASS (`factory/workgraph/prompt.py:693-695`), so a
  quiet boolean on a PASS row would be invisible to the next attempt. This is
  `CONFIG_ERROR`'s own precedent — "a status rather than a raised error so it
  flows through the verdict truth table" (`factory/verify/models.py:73-75`).

### The names, ruled here so three stories cannot disagree

US1 adds the fields, US2 renders them, US3 sets one of them, and the three
attempts never see each other's work. So the names are decided on this page
rather than by whichever attempt reaches them first.

- **`GateResult.worktree_writes: tuple[str, ...] = ()`** — the paths this gate
  changed, attributed to it by the name it was declared under; empty for a gate
  that changed nothing. A tuple because `GateResult` is frozen
  (`factory/verify/models.py:276-277`), defaulted for the reason
  `concurrent_gates` is (`factory/verify/models.py:301`).
- **`GateResult.writes_declared: bool = False`** — whether the manifest
  declared this gate a writer. A second scalar beside the paths, not a flag on
  each path entry, and **not a third `GateStatus` member**: a declared writer
  keeps PASS, so a new status would have to be taught to `gates_passed`
  (`factory/verify/models.py:478-492`), which is the single edit "one decider
  per half" forbids.
- **`writes:`** — the manifest key. Top-level, keyed by gate name, boolean
  value, sitting exactly where and how `timeouts:` sits
  (`factory/verify/factory_yaml.py:107`, `factory/verify/models.py:250`).
  Absent declares nothing; `false` means the same as absent.

## What this spec does not change

- **The sandbox stays writable.** `factory/verify/gates.py:630` binds the node
  worktree writable on purpose. Read-only breaks every gate that legitimately
  needs a scratch file, and is not what either reporter asked for. This spec
  observes; it does not prevent.
- **`check_output` keeps deciding what it already decides.**
  `factory/verify/diffcheck.py:171-176` states the constraint itself: "the
  moment two places can decide a FAIL, the stored row and the retry prompt can
  disagree." The gate half is decided by `gates_passed`
  (`factory/verify/models.py:478-492`) and stays decided there alone.
- **The existing hygiene refusal.** `hygiene_violations`
  (`factory/verify/diffcheck.py:262-290`) already refuses ignored and
  runtime-root paths that reach a diff, with the rule quoted to the next
  attempt. Not rebuilt, extended or renamed here.
- **`run_gates`'s complete-picture contract.** One result per declared gate; a
  failing gate never cancels the gates after it
  (`factory/verify/gates.py:1094-1098`). Nothing here becomes a synthetic gate.
- **The adjacent finding.** `verify/a-warm-pycache-suppresses-compile-time-
  warnings-so-warning-counts-are-not-comparable` — same surface, different
  consequence, out of scope.

## User Scenarios & Testing

### User Story 1 - A gate that writes into the worktree does not pass (Priority: P1)

As an operator, when a gate mutates the node's worktree, the run refuses it and
records which gate wrote which paths, instead of handing the mutated tree to the
judge.

**Why this priority**: P1 and it is the whole spec. Everything else here is how
the refusal reaches somebody.

**Independent Test**: run a gate whose command writes an untracked file and
assert the run refuses it, naming the gate and the file.

**Acceptance Scenarios**:

1. **Given** a declared gate whose command exits 0 and writes a file the target
   repo does not ignore, **When** the gates run, **Then** that gate is not
   reported as PASS and its result carries the path it wrote — proven by a
   committed test asserting the status and the path list.
2. **Given** a gate that writes only paths the target repo's `.gitignore`
   matches, **When** the gates run, **Then** it passes and records nothing —
   proven by a committed test. **This is the control**, and it is not a
   formality: this repository's own gate is `uv run pytest -q`
   (`factory.yaml`), which writes `__pycache__/` and `.pytest_cache/`, both
   ignored. A check that counted ignored paths would fail every gate run Ergane
   has ever made.
3. **Given** a gate that rewrites a tracked file the agent had already modified,
   **When** the gates run, **Then** it is refused and the file is named — proven
   by a committed test. `git status --porcelain` reports the identical line
   before and after this write, so the test also proves the measurement is
   content-based rather than status-based.
4. **Given** either gate-list runner — `_run_gate_list`
   (`factory/verify/gates.py:1244`) or `_run_gate_list_from_config` (`:1282`) —
   **When** a gate dirties the worktree, **Then** both refuse it, proven by a
   committed test covering each. A check in one runner is bypassable via the
   other, and which one a repo takes is decided by whether its worktree carries
   a candidate parser.
5. **Given** any `GateExecutor` — `SubprocessGateExecutor`
   (`factory/verify/gates.py:397`), `BwrapGateExecutor`
   (`factory/verify/gates.py:490`), or a stub implementing neither — **When** a
   gate dirties the worktree, **Then** it is refused, proven by a committed test
   naming the executor each case ran under. The stub is the load-bearing case:
   it is what proves the check sits at the seam both shipped executors pass
   through rather than inside one of them, and it is the only one of the three
   that runs on every host. `BwrapGateExecutor` needs a working `/usr/bin/bwrap`
   and namespace creation, which the node agent — itself sandboxed — may not
   have; its case is guarded and skipped the way this repository already guards
   every bwrap test, with `_bwrap_available()`
   (`tests/test_us4_boundary.py:165`) and the early returns at
   `tests/test_us4_boundary.py:208`, `:264` and `:321`.
6. **Given** a gate that both exits non-zero and dirties the worktree, **When**
   the gates run, **Then** its status stays FAIL, its exit code is preserved,
   the paths are still recorded, and the gates declared after it still ran —
   proven by a committed test. The exit code is the more actionable headline and
   the complete picture is a contract.
7. **Given** a worktree whose snapshot cannot be taken — git refuses it —
   **When** the gates run, **Then** the result is not PASS, the git error is in
   its output tail, and `run_gates` still returns a list rather than raising —
   proven by a committed test. An unreadable snapshot must never read as a clean
   worktree; this module fails closed everywhere else.
8. **Given** a recorded gate result carrying paths, **When** it is written to
   the evidence store and read back, **Then** the paths survive, and a row
   written before this field existed reads back as "nothing recorded" — proven
   by a committed test driving both codec halves
   (`factory/verify/store.py:668-692`).

---

### User Story 2 - The next attempt is told which gate wrote what (Priority: P1)

As the next attempt at this node, I am shown the gate that dirtied the worktree
and the files it wrote, so I can fix the cause instead of guessing.

**Why this priority**: P1. A refusal the next attempt cannot see is a node that
burns its ladder on a byte-identical mystery. That has happened here before:
`033-ergane-install/us2` failed four times reading "No failing gate output and
no judge feedback were recorded" (`factory/workgraph/prompt.py:722-724`).

**Independent Test**: build a retry prompt from an attempt whose gate dirtied
the worktree and assert the gate name and the paths appear in it.

**Acceptance Scenarios**:

1. **Given** an attempt whose gate dirtied the worktree, **When** the retry
   prompt is assembled, **Then** it names the gate, its command and every path
   that gate wrote, quoted rather than described — proven by a committed test
   asserting the rendered text.
2. **Given** an attempt whose gates all passed cleanly, **When** the retry
   prompt is assembled, **Then** nothing about worktree writes appears — proven
   by a committed test. **The control**: a green gate's output is noise in a
   prompt whose job is to say what went wrong
   (`factory/workgraph/prompt.py:681-683`), and that stays true.
3. **Given** an escalation message rendered for an attempt with a dirtied gate,
   **When** the operator reads it, **Then** the gate's line carries the marker —
   proven by a committed test asserting the rendered line. `concurrent_gates` is
   rendered there for exactly this reason
   (`factory/notify/messages.py:410-419`); a marker that lives only in the
   evidence store is one the operator never sees.

---

### User Story 3 - A gate that is supposed to write says so (Priority: P2)

As the author of a target repo's `factory.yaml`, I can declare that a particular
gate writes on purpose — a lockfile, a generated file — and that declaration is
visible in the evidence rather than hidden in config.

**Why this priority**: P2. Without it, a repo with a legitimate generating gate
cannot use the factory at all. With it done badly, this defect comes back
wearing a config key, which is why the declaration is per-gate and the writes
are still recorded. And with it done *half*, it is worse than absent: a key that
only one of the two runners honours reads as working and is dead on Ergane's own
nodes. That is S3, and it is the scenario this story is scored on hardest.

**Independent Test**: declare a gate's writes in a fixture manifest, let that
gate write, and assert the run passes — **through both gate-list runners** —
with the paths recorded as declared.

**Acceptance Scenarios**:

1. **Given** a manifest whose `writes:` block declares gate `X`, **When** `X`
   writes and exits 0, **Then** the run passes — proven by a committed test.
2. **Given** the same run, **When** the evidence is read, **Then** the paths `X`
   wrote are on its `worktree_writes` and its `writes_declared` is true, rather
   than the paths being omitted — proven by a committed test. **An opt-out
   nobody can see is how this defect returns.**
3. **Given** that same declaring manifest and either gate-list runner —
   `_run_gate_list` (`factory/verify/gates.py:1244`) or
   `_run_gate_list_from_config` (`factory/verify/gates.py:1282`) — **When** the
   declared gate writes and exits 0, **Then** both pass it and both record the
   paths as declared, proven by a committed test covering each runner. **This is
   the scenario without which this story can pass with the feature dead.**
   `_run_gate_list_from_config` is handed the whole `FactoryConfig` and gets the
   declaration for free; `_run_gate_list` is handed only the two views lifted
   off `_AcceptedConfig` (`factory/verify/gates.py:181-186`), which carries
   three fields and no room for a fourth. `_run_gate_list` is the runner
   Ergane's own nodes take — the fork is `if candidate_path.exists():` at
   `factory/verify/gates.py:1135` — so a declaration that reaches only the
   config runner is one that is silently dropped on this story's own
   verification path, by a manifest that looks correct.
4. **Given** a `writes:` block naming a gate the manifest does not declare as a
   gate, **When** it is parsed, **Then** it is refused as a manifest error
   naming the unknown gate — proven by a committed test. A declaration that
   silently applies to nothing is worse than no declaration.
5. **Given** a manifest that declares no `writes:` key, **When** it is parsed,
   **Then** it parses exactly as it does today — proven by a committed test.
   **The control**: every existing target repo's manifest keeps working.

## Requirements

### Functional Requirements

- **FR-001**: The gate runner MUST snapshot the node worktree's content around
  every gate execution, in both `_run_gate_list` and `_run_gate_list_from_config`.
- **FR-002**: "Dirtied" MUST mean exactly what the judge's diff can carry —
  tracked content changes and untracked paths the target repo does not ignore —
  measured the same way `worktree.diff` assembles the judge's patch. Ignored
  paths MUST NOT count.
- **FR-003**: A `GateResult` MUST record the paths its own gate changed on
  `worktree_writes`, attributing them to that gate by name, with a default so
  every existing construction site keeps working, and that field MUST round-trip
  through the evidence store with absence meaning "nothing recorded".
- **FR-004**: A gate whose command succeeded but whose execution changed the
  worktree MUST NOT be reported as PASS, and MUST fail the deterministic half of
  verification through the decider that already owns it.
- **FR-005**: A gate that failed or timed out MUST keep that status and MUST
  still record what it wrote; the runner MUST still return one result per
  declared gate and MUST NOT cancel the gates after it.
- **FR-006**: A snapshot that cannot be taken MUST NOT be reported as a clean
  worktree, and MUST NOT raise out of `run_gates`.
- **FR-007**: The retry prompt MUST name the offending gate, its command and
  every path it wrote, quoted verbatim.
- **FR-008**: The operator-facing gate line MUST carry the marker for a gate
  that wrote.
- **FR-009**: A manifest MUST accept a top-level `writes:` mapping from gate
  name to boolean, declaring that the named gate writes on purpose — the same
  position, shape and sparseness `timeouts:` already has
  (`factory/verify/factory_yaml.py:107`, `factory/verify/models.py:250`). An
  absent key and a `false` value both mean nothing is declared.
- **FR-010**: A gate with that declaration MUST still record what it wrote on
  `worktree_writes`, and MUST carry `writes_declared` true on its own result, so
  the evidence shows the writes were declared rather than omitting them. The
  declaration MUST NOT be expressed as a new `GateStatus` member: a declared
  writer keeps PASS.
- **FR-011**: A `writes:` entry naming a gate the manifest does not declare MUST
  be refused as a manifest error naming the unknown gate.
- **FR-012**: The `writes:` declaration MUST reach **both** gate-list runners,
  including the candidate-parser path, whose accepted-config shape carries no
  room for it today; a declared gate MUST be honoured identically whichever
  runner the target repo's worktree selects.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006]
  persona: opus-closer
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-007, FR-008]
  persona: opus-closer
US3:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-009, FR-010, FR-011, FR-012]
  persona: opus-closer
```

US2 and US3 merge-depend on US1 for different reasons and are independent of
each other. US2's is logic — it renders a field that does not exist until US1
lands. US3's is contention — it edits `factory/verify/gates.py`,
`factory/verify/models.py` and `factory/verify/store.py`, all three of which US1
rewrites. US2 touches `factory/workgraph/prompt.py` and
`factory/notify/messages.py`, sharing no file with US3, so they may run
concurrently.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Paste the runner refusing a gate that wrote an untracked file,
  showing the gate's name and the path in the recorded result.
- **SC-002**: Paste the control — a **fixture gate** that writes the same paths
  this repository's own gate writes, `__pycache__/` and `.pytest_cache/`, into a
  fixture repo whose `.gitignore` names them, run through the new check and
  still PASSing, with those paths shown as not counted. **It is a fixture gate
  and deliberately not a nested `uv run pytest -q`.** Read literally, that
  wording asked for this repository's full suite invoked as a gate, inside a
  gate run, inside the node's own gate run — the recursion that produced
  `hardening/orphaned-test-servers-exhaust-host-memory`, thousands of orphaned
  test servers OOM-killing this host from a single run. The real
  `uv run pytest -q` control is the operator's, run out of band against a live
  epic; it is in the plan's verification list and it is not this criterion.
- **SC-003**: Paste a gate that rewrote an already-modified tracked file being
  refused, alongside the byte-identical `git status --porcelain` output from
  before and after that write. The comparison is the evidence that the
  measurement is content-based.
- **SC-004**: Paste the same refusal produced through **each of the two
  gate-list runners**, and under `SubprocessGateExecutor` and under a **stub
  `GateExecutor`** that is neither shipped executor — the stub is what proves
  the check sits at the seam rather than inside an executor, and it runs on
  every host. `BwrapGateExecutor`'s case is pasted when the host has a working
  `/usr/bin/bwrap`; when it does not — and the node agent is itself sandboxed,
  so it may well not — paste the skip line **with its guard named beside it**:
  `_bwrap_available()` at `tests/test_us4_boundary.py:165`, the shape used at
  `tests/test_us4_boundary.py:208`, `:264` and `:321`. A bare `SKIPPED` is not
  evidence. A skip whose guard is quoted, next to a stub executor that actually
  ran, is.
- **SC-005**: Paste a failing gate that also dirtied the worktree — status FAIL,
  exit code intact, paths recorded — with the gate declared after it also
  present in the returned list.
- **SC-006**: Paste an unreadable snapshot producing a non-PASS result carrying
  git's own error, and `run_gates` returning a list rather than raising.
- **SC-007**: Paste the retry prompt for an attempt whose gate dirtied the
  worktree, showing the gate, its command and the paths.
- **SC-008**: Paste the operator-facing gate line for a dirtied gate, and the
  control line for a clean one.
- **SC-009**: Paste a fixture manifest whose `writes:` block declares a gate,
  that gate writing, the run passing, and the evidence showing the paths on
  `worktree_writes` with `writes_declared` true.
- **SC-010**: Paste a `writes:` entry naming an undeclared gate being refused,
  with the parser's own message.
- **SC-011**: Paste the declared gate passing through **each** of the two
  gate-list runners, with the paths recorded as declared in both. Name the
  candidate-parser runner explicitly, because that is the one the declaration
  reaches through nothing today and the one Ergane's own nodes take.

## Assumptions

- The scratch-index tree hash is the right measurement. Verified 2026-08-21 by
  live probe against a throwaway repository — output quoted in the frontmatter.
  An implementer who finds a cheaper measurement with the same three properties
  may use it, and must justify it in the diff.
- Only the two runner loops execute gates. Verified by reading
  `factory/verify/gates.py:1244-1315`. If a third path exists, it is in scope.
- No exhaustive `match` over `GateStatus` exists that a new member would break,
  and no downstream consumer needs an edit to refuse one. Verified 2026-08-21 by
  grepping every `GateStatus.` reference in `factory/`, and **independently
  re-verified the same day by a second reader** on the cross-spec critic pass:
  `gates_passed` (`factory/verify/models.py:478-492`) fails on any status that
  is not PASS, and `judge_required` (`factory/verify/models.py:505-524`) is
  built on `gates_passed` and inherits it. FR-004 rests on this, so it has now
  been read out of the tree twice.
- The worktree has no concurrent writer while gates run: the agent's attempt has
  finished, and each gate-list loop is sequential. Read out of those loops, not
  independently verified; if it is false, attribution to a single gate is
  approximate and the implementer should say so rather than assume.
- FR-009's shape is **no longer open**. `writes:` is a top-level mapping from
  gate name to boolean, ruled on the 2026-08-21 critic pass rather than left to
  whichever attempt reached it first. A mapping rather than a list of names
  because `timeouts:` is a mapping and the unknown-gate refusal FR-011 asks for
  is already written for that shape
  (`factory/verify/factory_yaml.py:386-393`). A boolean rather than a list of
  path globs because glob semantics — whose matcher, anchored where, matched
  against which of the two runners' path lists — is a second decision this
  defect does not need, and FR-010 keeps every written path visible anyway.
  Narrowing that value from boolean to a path list in a later spec adds no key
  and breaks no manifest, which is why the cheap shape is the right one now.
