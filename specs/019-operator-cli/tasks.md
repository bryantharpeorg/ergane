# Tasks: The `ergane` Operator CLI

**Input**: [spec.md](spec.md) and [plan.md](plan.md) in this directory.

Every task is test-first (constitution II): the test task is written and **must
fail** before its implementation task runs. A task that finds its test already
passing has found a defect in the test, not a task it may skip.

For a *ported* handler the failing test is not new code: point the existing
test file at the new entry point, watch it fail, then move the handler. That is
what makes "behaviour unchanged" (SC-003) a fact rather than a hope.

Tasks marked `[P]` touch disjoint files within their story and may be written
in any order. Tasks without it are sequential because they share a file.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (operator preflight — dispatched to no node)

- [x] T001 Operator: re-verify plan.md's reuse inventory against the tree that
      will host the work. The line numbers were taken 2026-08-08 against
      `ergane-buildout`; 017 and 018 may have moved them. Four things must be
      re-confirmed by hand, because the plan leans on each:
      (a) **nothing shells out to a console script** — `grep -rn
      "factory-epic\|factory-usage\|factory-roadmap\|factory-doctor"` finds no
      `subprocess`, `os.system` or shell caller under `factory/`; if that has
      changed, the hard cutover's blast radius has changed and this plan must
      be corrected before deriving, not the nodes after;
      (b) `command -v ergane` finds nothing on the host;
      (c) the five `EpicWorkflow` signals and the four `RoadmapWorkflow`
      signals/query still carry the names plan.md quotes;
      (d) `factory/verify/store.py` still exports `pending_questions` and
      `pending_escalations`, since FR-013/FR-014 add no store on the strength
      of it.
      **Answered 2026-08-09; all four hold.**
      **(a) Nothing shells out.** 21 hits under `factory/`, every one a
      docstring, a `prog=` string, or an `f"factory-…: {error}"` stderr prefix.
      No `subprocess`, no `os.system`, no shell caller. The hard cutover's blast
      radius is what US5 assumes. One hit is the U2 defect itself, in the tree
      and unchanged: `argparse.ArgumentParser(prog="factory-doctor")` at
      `factory/doctor/cli.py:92`, a plain parser where the two 005-era CLIs
      subclass — so a typo still exits 2 under a docstring that reads 2 as "a
      service is not answering".
      **(b) `ergane` is not on the host's PATH.** The name is free.
      **(c) Every signal name holds.** `EpicWorkflow`: `pause_epic`,
      `resume_epic`, `kill_epic`, `escalation_resolved`, `question_answered`,
      plus the `epic_status` query. `RoadmapWorkflow`: `pause_roadmap`,
      `resume_roadmap`, `promote_spec`, plus the `roadmap_status` query.
      **(d) Both store readers are exported**: `pending_escalations`
      (`factory/verify/store.py:503`) and `pending_questions` (`:742`).
      Nine of plan.md's file:line anchors were spot-checked the same day and all
      resolve to what the plan says they do — 017 and 018 have not dispatched,
      so nothing under `factory/` has moved since drafting.
      **The 020 overlap is now enforced, not remembered.** 020 rewrites
      `factory/workgraph/cli.py`'s `landed` parser (`:895`), its `--default-branch`
      resolution (`:232`) and `_build_baseline`'s hardcoded branch (`:348`) —
      the same parsers US2 and US3 replace. Rather than leave the ordering to
      this note, the spec's frontmatter declares `depends_on_landed:
      020-landing-attribution`, so the roadmap will not dispatch this epic until
      020 is landed. What T001 still owes: **re-run the line-anchor spot-check
      after 020 lands**, because 020 is the one epic guaranteed to move the exact
      lines this plan cites. FR-009 and trap 2 assume 020's fix is already in the
      tree — confirm it is before deriving.

---

## Phase 2: User Story 1 — One front door, one contract (Priority: P1) 🎯 MVP

**Goal**: `ergane` exists, lists its nouns, and every path through it obeys one
exit-code contract enforced in one place.

**Independent Test**: with only the dispatcher registered, help works, unknown
input exits 2, the boundary maps each error class to its code, and no
`ArgumentParser` subclass exists under `factory/`.

### Tests for User Story 1 (write FIRST, must fail)

- [ ] T002 [US1] Verify prerequisites in this worktree: `uv run pytest -q`
      green; `factory/workgraph/cli.py`, `factory/roadmap/cli.py`,
      `factory/doctor/cli.py` and `factory/usage/cli.py` all exist and still
      work — constitution II gate; STOP and report blocked if not satisfied.
- [ ] T003 [P] [US1] Write dispatcher cases FIRST in `tests/test_ergane_cli.py`:
      bare `ergane` prints every registered noun with a one-line description and
      exits 0; `--help` does the same; an unknown noun exits **2** with a usage
      line on stderr and **empty stdout**; `ergane <noun>` with no verb lists
      that noun's verbs — must fail.
- [ ] T004 [P] [US1] Write error-boundary cases FIRST against a deliberately
      failing handler registered for the test: the shared operator error exits
      1 with one line on stderr and no traceback; an operator error carrying
      its own code exits with that code (trap 8 — the per-raise code must
      survive); a service failure exits **3** and its message names the address
      dialled; an arbitrary exception exits 1 with one line naming `--debug`,
      and the same command under `--debug` prints the traceback;
      `KeyboardInterrupt` exits **130** — must fail.
- [ ] T005 [P] [US1] Write the two structural sweeps FIRST — these are the
      tests that make the contract outlive this epic:
      (i) no module under `factory/` defines a class inheriting from
      `argparse.ArgumentParser` (AST scan, the `tests/test_final_sweep.py`
      pattern);
      (ii) parametrised over **every registered subcommand path** discovered by
      walking the parser tree, a bad flag exits 2 — so a noun added later
      without honouring the contract fails here rather than in production
      (FR-002, FR-003, SC-002) — must fail.
- [ ] T006 [P] [US1] Write `--version` cases FIRST: exits 0; stdout names the
      package version, a revision, and the Temporal address and proxy url it
      would dial; **no network call is made** (assert with the client
      constructor patched to raise); no credential value appears in the output
      — must fail.

### Implementation for User Story 1

- [ ] T007 [US1] Implement `factory/cli/errors.py`: one `OperatorError`
      carrying message and exit code, and `run_cli(entry)` implementing
      plan.md's boundary table, until T004 passes. Keep the per-raise exit code
      — `status_command` depends on it to report transport as transport.
- [ ] T008 [US1] Implement `factory/cli/main.py`: the root parser, the noun
      registry, `--debug`, and `--version`, until T003, T005 and T006 pass. Use
      a plain `argparse.ArgumentParser` — **do not** subclass it, and do not
      override `error()`. A noun whose module fails to import must be reported
      by name with exit 1, never as an import traceback (spec Edge Cases).
- [ ] T009 [US1] Register `ergane = "factory.cli.main:main"` in
      `pyproject.toml` **alongside** the four existing scripts. They are not
      removed here — the four CLIs must keep working through US4 (trap 1),
      because the factory building this epic runs on them.

---

## Phase 3: User Story 2 — The spec noun (Priority: P1)

**Goal**: `ergane spec list|validate|derive|landed`, each with `--json`,
reusing today's handlers and connecting to nothing.

**Independent Test**: against a fixture corpus, list/derive/landed match
today's output; `validate` reports all three layers' refusals in one run;
`landed` resolves the repository's own default branch.

### Tests for User Story 2 (write FIRST, must fail)

- [ ] T010 [US2] Point `tests/test_roadmap_cli.py`'s render cases and the
      `derive`/`landed` cases in `tests/test_epic_cli.py` at `ergane spec ...`
      FIRST, unchanged in every other respect — they must fail on the new
      entry point and pass on the old one. This is SC-003's mechanism: the old
      assertions are the definition of "behaviour unchanged".
- [ ] T011 [P] [US2] Write `spec validate` cases FIRST: a spec with a
      frontmatter error **and** a work-graph rejection **and** an unserved
      persona alias reports **all three** in one run and exits 1 — assert the
      count, not just the exit code, or a first-refusal-wins implementation
      passes; a sound spec exits 0 and names what it checked; the command opens
      no socket (assert with the client constructor patched to raise) — must
      fail.
- [ ] T012 [P] [US2] Write the branch-resolution **regression** case FIRST
      (trap 2): against a target declaring `landing_branch` in `factory.yaml`,
      `ergane spec landed <spec-dir>` with no branch argument reports against
      the declared branch and names it in the output; an explicit
      `--default-branch` still overrides; and no `default="main"` appears
      anywhere in the new parser. This asserts 020's landed fix survives the
      port — it does not re-implement it. If this test passes before the port
      exists, that is the old entry point answering; point it at `ergane` — must
      fail.
- [ ] T013 [P] [US2] Write `--json` cases FIRST for all four verbs: stdout
      parses as a single document, the human rendering is absent, and the
      document carries the same facts the human view shows — must fail.

### Implementation for User Story 2

- [ ] T014 [US2] Implement `factory/cli/spec.py` — `list`, `derive`, `landed`
      as thin wrappers over `render_command`/`_render_roadmap`,
      `derive_command`, `landed_command`, plus `--json` — until T010, T012 and
      T013 pass. Import the handlers; do not copy them. The branch default is
      already correct when this dispatches (020) — carry it across, do not
      re-derive it, and do not reintroduce `default="main"`.
- [ ] T015 [US2] Implement `validate` as a sequencer over `read_roadmap`,
      `derive_workgraph` and `validate_workgraph`, collecting every refusal
      before exiting, until T011 passes. No new checking logic — all three
      already refuse with named findings; this composes them.

---

## Phase 4: User Story 3 — The build noun (Priority: P1)

**Goal**: `ergane build start|status|pause|resume|kill|answer|resolve` — the
preflight ladder intact, and the five existing signals given an operator
surface.

**Independent Test**: start refuses before connecting; status is byte-identical
under `--json`; each signal verb sends exactly its own signal; kill confirms;
answer/resolve list from the store and refuse resolved or expired ids.

### Tests for User Story 3 (write FIRST, must fail)

- [ ] T016 [US3] Point `tests/test_epic_cli.py`'s `start` and `status` cases at
      `ergane build ...` FIRST, unchanged — including the zero-node refusal,
      the missing-proxy refusal, and the sibling-key rule for `--json`. Add one
      case the old suite could not have: a preflight refusal caused by the
      proxy not answering exits **3**, not 2 (trap 3) — must fail.
- [ ] T017 [P] [US3] Write signal cases FIRST against a scripted workflow under
      time skipping: `pause`, `resume` and `kill` each send exactly their own
      signal and no other; `kill` without `--yes` on a declined prompt sends
      **nothing** and exits 1; `kill --yes` sends `kill_epic`; a signal against
      an epic id with no workflow exits 1 naming the id it looked for — must
      fail.
- [ ] T018 [P] [US3] Write `answer` cases FIRST: with no question id, every
      pending question for that epic is listed with id, node, text and expiry,
      and **no signal is sent**; with an id, `question_answered` is sent with
      `[question_id, text]`; an already-answered id and an expired id each exit
      1 naming which and send nothing; a question belonging to another epic is
      not listed — must fail.
- [ ] T019 [P] [US3] Write `resolve` cases FIRST: with no escalation id, every
      pending escalation is listed with its **own** choice set; a choice outside
      that set exits 1 naming the choices the record offers; no choice at all
      lists and sends nothing; the command supplies **no default choice** on any
      path — assert that a run with no choice sends nothing, because a default
      would convert the operator's deliberate silence into a press — must fail.

### Implementation for User Story 3

- [ ] T020 [US3] Implement `factory/cli/build.py` `start` and `status` over
      `start_command`, `status_command`, `render_status` and `_live_spend`
      until T016 passes. Move `EXIT_TRANSPORT` and `_preflight_exit_code`
      together (trap 3): the constant becomes 3 and the mapper moves in the
      same commit, or a dead proxy reports as a bad spec.
- [ ] T021 [US3] Implement the three signal verbs until T017 passes:
      `_connect()`, `get_workflow_handle(workflow_id(epic_id))`,
      `handle.signal(NAME)`. Import `SIGNAL_NAME` and `QUESTION_SIGNAL_NAME`
      from `factory.notify.service`; do not retype the strings.
- [ ] T022 [US3] Implement `answer` and `resolve` over
      `factory.verify.store.pending_questions` / `pending_escalations` /
      `get_question` / `get_escalation` until T018 and T019 pass. Read-only
      against the store: the workflow's own signal handler is what records the
      answer, and a CLI that also writes the row would give the same fact two
      authors.

---

## Phase 5: User Story 4 — The rest of the surface (Priority: P2)

**Goal**: `roadmap`, `doctor`, `findings`, `usage`, `repo onboard`, `env`,
`completion` — four ports and one room that has never had a door.

**Independent Test**: ported commands match today's output; the roadmap starts,
pauses, promotes and answers a query from the CLI; findings filter; env leaks
nothing; completion emits a script.

### Tests for User Story 4 (write FIRST, must fail)

- [ ] T023 [US4] Point `tests/test_doctor_cli.py` and `tests/test_cli.py`
      (usage) at `ergane doctor` / `ergane findings ...` / `ergane usage`
      FIRST, unchanged, plus the `repo onboard` cases from
      `tests/test_epic_cli.py`. Add two cases the old suites could not have: a
      probe that raises a non-service exception is reported as **one line**
      naming `--debug`, not a traceback (trap 7); a missing ledger exits **3**
      under the unified contract — must fail.
- [ ] T024 [P] [US4] Write roadmap-surface cases FIRST: `start` starts
      `RoadmapWorkflow` under the sibling id convention and prints the id; a
      collision with a running roadmap exits 1 naming it and starts nothing;
      `pause`, `resume` and `promote <spec-dir>` each send exactly their own
      signal; `status` prints the `roadmap_status` document unchanged, with
      `--json` printing it as it arrived — must fail.
- [ ] T025 [P] [US4] Write `findings list` filter cases FIRST: `--severity` and
      `--status` each narrow the result, they compose, an unknown value exits
      **2** (it is a bad argument, not a bad system), and the same filters apply
      under `--json` — must fail.
- [ ] T026 [P] [US4] Write `env` and `completion` cases FIRST: `env` lists every
      variable the CLI reads with set/not-set and where it resolves from, and
      **no credential value appears in stdout** for any variable, asserted with
      a fake secret planted in the environment (the 001 grep pattern);
      `completion bash` and `completion zsh` each exit 0 with a non-empty
      script; an unsupported shell exits 2 naming the two supported — must fail.

### Implementation for User Story 4

- [ ] T027 [US4] Implement `factory/cli/doctor.py` (`doctor` + `findings`) and
      `factory/cli/usage.py` and `repo onboard` over the existing handlers,
      adding the two filters, until T023 and T025 pass. Do not touch
      `factory/doctor/probes.py` (trap 7).
- [ ] T028 [US4] Implement `factory/cli/roadmap.py` until T024 passes:
      `start_workflow(RoadmapWorkflow.run, ...)` with the
      `roadmap-<specs-root-name>` id convention and the
      `WorkflowAlreadyStartedError` refusal `_start_epic` already models; one
      signal per verb; the query printed as it arrived. Add no scheduling
      behaviour — this story wires a surface, it does not change the scheduler.
- [ ] T029 [US4] Implement `env` and `completion` until T026 passes. Mind the
      enforcement-word sweep (trap 4): help text is a scanned string constant,
      so no `--help` line may say `budget`, `cap`, `quota`, `throttle`,
      `enforce`, `exceed` or `breach`. Say **bound** or **limit**.

---

## Phase 6: User Story 5 — The cutover (Priority: P2)

**Goal**: the four `factory-*` scripts stop existing, and every reference to
them outside the historical record moves in the same change.

**Independent Test**: `pyproject.toml` names only `ergane`; a repository-wide
search finds the old names only under `specs/` and `docs/decisions.md`; the
CLAUDE.md sweep passes with the new command set; the full suite is green.

### Tests for User Story 5 (write FIRST, must fail)

- [ ] T030 [US5] Write the cutover sweep FIRST: `pyproject.toml`'s
      `[project.scripts]` names `ergane` and none of the four; a
      repository-wide search for the four names finds hits only under `specs/`
      and `docs/decisions.md`; every operator-facing string under `factory/`
      that recommends a command names one that resolves — must fail.
- [ ] T031 [US5] Update `tests/test_claude_md.py` FIRST so its command set at
      the sweep assertion is `{"ergane"}` and its per-command checks invoke the
      new entry point — it must fail until CLAUDE.md itself moves, which is the
      point: the two are meant to be inseparable.

### Implementation for User Story 5

- [ ] T032 [US5] Remove the four scripts from `pyproject.toml`; leave `ergane`.
      Delete the two `argparse.ArgumentParser` subclasses
      (`factory/workgraph/cli.py`, `factory/roadmap/cli.py`) and the now-dead
      module-level `main`/`_parse_args` bodies the nouns replaced, keeping every
      handler the CLI package imports.
- [ ] T033 [US5] Move every remaining reference until T030 and T031 pass:
      operator-facing strings under `factory/` (probe remediations, scaffolded
      findings, the zero-node graph's advice), the tests that invoke the old
      scripts including `tests/test_live_epic.py`, `CLAUDE.md`,
      `docs/architecture.md`, `docs/claude-md-plan.md`, and
      `scripts/ergane-env.sh`. **Do not edit anything under `specs/`** — it is
      the historical record, and a landed spec's fingerprint reads only
      `spec.md`, so an edit there would be invisible drift rather than a caught
      one.
- [ ] T034 [US5] Append one `docs/decisions.md` entry at the next free number
      (FR-021): the supersession of `001/contracts/cli.md`'s and
      `005/contracts/cli.md`'s exit-code tables and of 005's clause scoping
      signals to the `temporal` binary; why usage is 2 (the old scheme was
      reachable only by overriding argparse in every new file, so the third
      file forgot); and the hard cutover with no shim. Extend
      `docs/architecture.md`'s module table with `factory/cli/`. Neither
      contract file is edited.

---

## Dependencies & Execution Order

- Phase 1 is operator work and gates everything — including re-confirming that
  nothing shells out to a console script, which is the assumption the whole
  cutover rests on.
- Phase 2 (US1) has no dependency and is the MVP: `ergane --help` is the first
  complete answer this repository has ever had to "what can I do here".
- Phases 3, 4 and 5 each chain on the previous **merged**, not passed. All
  three register a noun into the same dispatcher module, and two worktrees
  editing one module is a collision avoided by disjointness rather than by
  luck.
- Phase 6 chains last because it removes the scripts Phases 3–5's tests still
  invoke.

## Implementation Strategy

US1 alone is worth landing if anything must be cut: it fixes the contract, and
the contract is the finding. US2 is the daily surface and the cheap half of the
job. US3 is the money and the operator's grip on it. US4 closes the one room
with no door. US5 is what makes the epic honest — a front door that leaves four
side doors open has replaced nothing — and it is last because it is the only
story that can redden a sibling's worktree.

Nothing in this epic changes workflow code, an activity, or a probe. Every
reach into a running workflow goes through a signal or a query that already
exists, which is what keeps a CLI epic from becoming an interpreter epic.
