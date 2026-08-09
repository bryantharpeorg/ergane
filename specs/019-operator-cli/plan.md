# Implementation Plan: The `ergane` Operator CLI

**Branch**: `019-operator-cli` | **Date**: 2026-08-08 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/019-operator-cli/spec.md`

## Summary

Four console scripts become one. A new `factory/cli/` package holds the
`ergane` root parser, one shared error boundary, and one exit-code contract;
each existing CLI's handlers move behind a noun that names the operator's job
rather than the package the handler came from. Almost nothing is written — the
work is composition, and the reuse inventory below is most of the
implementation. The two genuinely new pieces are `spec validate` (a composition
of three existing refusals into one run) and the roadmap's verbs (the first
operator surface for a workflow that has never had one).

This plan is deliberately self-contained: the prompt assembler ships
spec/plan/tasks only, so every fact an implementer node needs is inlined, each
verified against the tree the day of drafting — and T001 re-verifies them
against the tree that actually hosts the work.

## Technical Context

**Language/Version**: Python 3.11+ (constitution III); the worker host runs
3.13.

**Primary Dependencies**: none added. `argparse` is stdlib and the roster
(`tests/test_final_sweep.py`, `APPROVED_THIRD_PARTY`) is untouched. **Do not
introduce `click`, `typer`, `rich`, or a completion library.** Every one of them
would fail `test_the_component_imports_only_the_approved_roster` on the first
import, and the whole point of the contract chosen here is that it needs no
framework to hold.

**Verified reuse inventory** (`file:line` as of 2026-08-08; T001 re-checks):

*The four entry points being replaced*

- `factory/workgraph/cli.py` (943 lines) — `derive|landed|onboard|start|status`.
  `EXIT_OK/EXIT_USER/EXIT_TRANSPORT = 0/1/2` at lines 102–104; `_OperatorError`
  at 117 carries its own exit code; `_Parser(argparse.ArgumentParser)` at 838
  overrides `error()` to exit 1; `main()` at 190 catches `_OperatorError` and
  `KeyboardInterrupt`.
- `factory/roadmap/cli.py` (198 lines) — `render` only. Same three constants
  (39–41), its own `_OperatorError` (48), its own `_Parser` (162). `main()` at
  62 catches `_OperatorError` but **not** `KeyboardInterrupt`.
- `factory/doctor/cli.py` (453 lines) — `report|list|resolve|check|promote`.
  Same three constants (50–52) but a distinct `_UserError` (83), and
  `_parse_args` at 91 builds a **plain** `argparse.ArgumentParser`. This is U2's
  mechanism: no subclass, so a typo takes argparse's native 2, which this
  module's own docstring reserves for a service not answering.
- `factory/usage/cli.py` (226 lines) — `EXIT_OK/EXIT_USAGE/EXIT_NO_LEDGER =
  0/2/3` (51–53), which is 001's contract and the one this spec adopts.
  `render_table` (168) and the `UNMEASURED = "-"` convention are behaviour to
  preserve byte-for-byte, not to reinterpret.

*Handlers that move as they are*

- `derive_command` (270), `landed_command` (215), `onboard_command` (410),
  `start_command` (469), `status_command` (629), `render_status` (771),
  `load_workgraph` (559), `_persona_registry` (596), `_live_spend` (700-ish),
  `_print_provenance` (389), `_build_baseline` (336) — all in
  `factory/workgraph/cli.py`.
- `render_command` (80) and `_render_roadmap` (123) in `factory/roadmap/cli.py`.
- `_report_command` (182), `_list_command` (239), `_resolve_command` (268),
  `_check_command` (275), `_promote_command` (327), `_run_probe` (303),
  `_report_if_new` (318), `_sanitize_finding` (162) in
  `factory/doctor/cli.py`.
- `render_table` (168), `open_readonly` (104), `_default_ledger_path` (153) in
  `factory/usage/cli.py`.

*The pieces `spec validate` composes — all three already refuse independently*

- `factory.roadmap.models.read_roadmap` (380) raises `RoadmapError` with staged
  findings naming offender and file; `compute_readiness` (527).
- `factory.workgraph.derive.derive_workgraph` (139) raises `DerivationError`
  carrying **every** rejection, not the first — the discipline `validate` is
  meant to extend across all three layers.
- `factory.workgraph.models.validate_workgraph`, called at
  `factory/workgraph/cli.py:498` with `_persona_registry(graph)`.
- `factory.workgraph.preflight.check_aliases`, reached through `_run_preflight`
  (`factory/workgraph/cli.py:160`) — **network**, so it belongs to `build
  start`, not to `validate`. FR-007 says `validate` connects to nothing.

*The signals `build` wires — all five already exist*

- `factory/workgraph/workflow.py:497-554`: `pause_epic`, `resume_epic`,
  `kill_epic`, `escalation_resolved(escalation_id, choice)` (530, name from
  `factory.notify.service.SIGNAL_NAME`), `question_answered(question_id,
  answer_text)` (541, `QUESTION_SIGNAL_NAME`).
- The call shape is already in the tree twice: `factory/notify/service.py:284`
  and `:321` do `await handle.signal(NAME, args=[id, value])`. The CLI makes the
  identical call. Import the two name constants; do not retype the strings.
- `_connect()` (`factory/workgraph/cli.py:819`) and `workflow_id(epic_id) ->
  f"epic-{epic_id}"` (207) are how a handle is obtained.

*Where `answer` and `resolve` get their ids — the store already has them*

- `factory/verify/store.py`: `connect` (167), `pending_questions` (742),
  `pending_escalations` (503), `get_question` (709), `get_escalation` (488).
- `QuestionRecord` (`factory/verify/models.py:499`) carries `question_id`,
  `epic_id`, `node_id`, `attempt`, `question_text`, `expires_at`, `resolution`.
  `EscalationRecord` (472) carries `escalation_id`, `epic_id`, `node_id`,
  `choices: list[EscalationChoice]`, `expires_at`, `resolution`.
- This is why FR-013/FR-014 add no record and no table: filtering
  `pending_questions(conn)` by `epic_id` is the whole listing feature, and
  `record.choices` is the closed set FR-014 validates against.

*The roadmap's surface — signals exist, CLI does not*

- `factory/roadmap/workflow.py:424-455`: `pause_roadmap`, `resume_roadmap`,
  `promote_spec(spec_dir)`, query `roadmap_status`.
- `factory/worker.py:90`: `WORKFLOWS = [EpicWorkflow, RoadmapWorkflow]` — it is
  registered and dispatchable.
- Nothing starts it. A repository-wide search for `RoadmapWorkflow` finds the
  worker, the docs, and specs; no CLI, no script. Confirmed 2026-08-08.
- Take the sibling id convention `roadmap-<specs-root-name>`, the shape 009's
  plan named, so ids cannot collide with `epic-*`.

*The cutover's blast radius, measured*

- `pyproject.toml:13-17` registers the four scripts. `version = "0.1.0"` at
  line 3 is what `--version` reports.
- Outside `specs/` and `docs/decisions.md`, the four names appear in: 12 modules
  under `factory/` (~28 hits, all operator-facing strings — probe remediations,
  scaffolded findings, the zero-node graph's advice at
  `factory/workgraph/cli.py:494`), 13 files under `tests/` (~40 hits),
  `docs/architecture.md` (10), `CLAUDE.md` (8), `docs/claude-md-plan.md` (6),
  `scripts/ergane-env.sh`.
- `tests/test_claude_md.py:164` asserts the named command set is exactly
  `{"factory-roadmap", "factory-epic", "factory-doctor", "factory-usage"}`. It
  goes red the moment CLAUDE.md says `ergane`, so it moves in the same change.
- **Nothing shells out to a console script.** Verified by search: the worker
  imports the packages and the workflows call activities. This is what makes a
  hard cutover cheap and what T001 must re-confirm.

**Storage**: none. The CLI reads the doctor's ledger, the usage ledger and the
verification store through their existing readers and adds no store of its own.

**Testing**: `pytest`. The existing per-CLI suites (`tests/test_epic_cli.py`,
`tests/test_roadmap_cli.py`, `tests/test_doctor_cli.py`, `tests/test_cli.py`)
are the behaviour contract for every ported handler — they move with their
handlers rather than being rewritten, which is what makes SC-003's "output
unchanged" a fact instead of a hope. `tests/test_live_epic.py` invokes the
scripts and needs the same treatment.

**Project Type**: single Python package; one new module directory
`factory/cli/`, mirroring the existing layout so the architecture doc's module
table extends rather than bends.

## Constitution Check

- **I (build order, vertical slices)**: each story is a usable slice — the
  dispatcher, then one noun at a time, then the cutover.
- **II (test-first)**: every task pairs a failing test with implementation. For
  ported handlers, the existing test is the failing test: point it at the new
  entry point first, watch it fail, then move the handler.
- **III (dependencies)**: none added. See the warning above about CLI
  frameworks.
- **IV (determinism at the core)**: the CLI is all edge. No workflow code
  changes in this epic — `build` and `roadmap` reach workflows only through
  signals and queries that already exist.
- **V (spend attributed)**: `--version` and `env` report the proxy url and
  whether credentials are set, never a value. `ergane env` is the single
  highest-risk surface in this epic for a leak; treat it as such.
- **VI (no work lost)**: untouched.
- **VII (personas over tiers)**: untouched — the CLI selects no model.

## Approach by story

### US1 — the dispatcher and the contract (FR-001…FR-005)

`factory/cli/main.py` holds the root parser and a noun registry;
`factory/cli/errors.py` holds one `OperatorError` (message + exit code, the
shape `factory/workgraph/cli.py:117` already has) and one `run_cli(entry)`
boundary that every noun's `main` goes through.

The boundary is the whole contract:

| Raised | stderr | exit |
|---|---|---|
| `OperatorError` | its message, one line | its code, default 1 |
| a service failure | the message **and the address dialled** | 3 |
| `KeyboardInterrupt` | nothing | 130 |
| anything else | one line + `re-run with --debug for the traceback` | 1 |
| `--debug` set | the traceback | as above |

**The one structural rule**: no `argparse.ArgumentParser` subclass. Both
existing subclasses (`workgraph/cli.py:838`, `roadmap/cli.py:162`) are deleted
rather than moved. This is not a style preference — it is the fix. 005's
contract could only be honoured by an override in every new file, so the third
file forgot; a contract that agrees with the library's default cannot be
forgotten by a file that does nothing.

`--version` reads `importlib.metadata.version("factory")` (or the package's
own `__version__` if metadata is unavailable in a worktree install), the git
revision via `git rev-parse --short HEAD` in the CLI's own tree, and the two
addresses from the environment. It dials nothing: a `--version` that hangs
because Temporal is down is a `--version` nobody trusts.

### US2 — the `spec` noun (FR-006…FR-009)

`list` is `render_command` + `_render_roadmap` moved verbatim, plus `--json`
over the same `Roadmap`/`Readiness` objects. `derive` and `landed` are
`derive_command` and `landed_command` moved verbatim.

`validate` is the only new code, and it is a sequencer, not a checker: read the
frontmatter (catch `RoadmapError`), derive the graph (catch `DerivationError`),
validate against the persona registry (catch `WorkGraphError`), and print
**every** collected refusal before exiting 1. Do not stop at the first — the
staged-rejection discipline `derive_workgraph` already implements inside one
layer is the behaviour FR-007 extends across three. On success, print what was
checked; a silent exit 0 is indistinguishable from a no-op.

`landed`'s branch resolution is a trap, below.

### US3 — the `build` noun (FR-010…FR-014)

`start` is `start_command` moved with its preflight ladder intact — the
env-before-client ordering is deliberate and must survive: everything checkable
without a server is checked without one, so a transport failure is always about
the server and never about the file. `status` is `status_command` +
`render_status` + `_live_spend` moved, with the sibling-key rule preserved
(execution status and live spend are siblings of the query document, never
merged into it).

`pause`, `resume`, `kill` are three functions of five lines each: `_connect()`,
`get_workflow_handle(workflow_id(epic_id))`, `handle.signal(NAME)`. Import the
signal names; do not retype them.

`answer` and `resolve` are the same plus a store read. With no id: open the
verification store, filter `pending_questions(conn)` / `pending_escalations(conn)`
by `epic_id`, print id / node / text-or-choices / expiry, send nothing. With an
id: fetch the record, refuse if `resolution` is not `None` (already answered, or
`EXPIRED`) naming which, otherwise signal.

`resolve` validates the choice against `record.choices` and **has no default**.
The escalation contract is that silence is a decision the operator is entitled
to make and expiry is part of it; a CLI that supplies a default choice
converts a deliberate silence into a press.

`kill` prompts. `kill_epic`'s own docstring says a kill is never taken back —
there is no un-kill signal by design — so `--yes` is the way to skip the prompt
and a declined prompt sends nothing and exits 1.

### US4 — the rest of the surface (FR-015…FR-018)

Ports first: `doctor` is `_check_command`; `findings` is the other four doctor
verbs plus `--severity`/`--status` filters, which are `WHERE` clauses over
columns the ledger already has; `usage` is `main` + `render_table`; `repo
onboard` is `onboard_command` + `_render_onboard`.

`roadmap` is new surface over old machinery. `start` builds the input and calls
`client.start_workflow(RoadmapWorkflow.run, ...)` with the sibling id
convention, refusing a `WorkflowAlreadyStartedError` by name the way
`_start_epic` already does. `pause`/`resume`/`promote` are one signal each.
`status` queries `roadmap_status` and prints the document — untyped, printed as
it arrived, so `--json` cannot drift from the workflow's own definition.

`env` enumerates every variable the CLI reads — the Temporal address, the proxy
url, the master key, the Telegram token, the specs root, the ledger path — and
prints `set` / `not set` plus where the value resolves from. It never prints a
credential value. `completion` emits a static bash/zsh script generated from
the parser tree; an unsupported shell exits 2 naming the two that work.

### US5 — the cutover (FR-019…FR-021)

Mechanical and wide. Remove the four scripts from `pyproject.toml:13-17`, add
`ergane = "factory.cli.main:main"`. Then sweep, in one change: operator-facing
strings under `factory/`, the tests that invoke the old scripts, `CLAUDE.md`,
`docs/architecture.md`, `docs/claude-md-plan.md`, `scripts/ergane-env.sh`, and
`tests/test_claude_md.py:164`'s command set.

`specs/**` is **not** touched. Neither is `docs/decisions.md`'s history — one
entry is appended at the next free number recording the supersession of
`001/contracts/cli.md`'s and `005/contracts/cli.md`'s exit-code tables and of
005's clause scoping signals to the `temporal` binary. This is the D-031 /
D-034 pattern, and it is also what keeps a landed spec's fingerprint stable:
`factory/workgraph/landed.py:242` reads only `spec.md`, so editing a contract
file would not register as drift — which is precisely why the discipline has to
be a rule rather than a consequence.

## Traps

Named hazards, so the implementer meets each as declared scope rather than as a
failure.

1. **This epic edits the CLI that runs it.** The worker imports factory code
   live and CLAUDE.md's standing rule is that factory code is never modified
   while an attempt is in flight. `factory/cli/` is a **new** package for US1
   through US4 — the four existing CLIs keep working, untouched, until US5. Any
   node that deletes or rewrites `factory/*/cli.py` before US5 breaks the run
   building it.

2. **`landed` defaults to the wrong branch.** The factory lands on
   `ergane-buildout`; `main` moves only when an operator promotes. Between
   promotions a `main` default silently under-reports which stories are landed,
   and this has been filed twice already
   (`cli/landed-defaults-to-the-wrong-branch`). `ergane spec landed` must
   resolve the target repository's own default branch and print the branch it
   used. A correct answer whose basis is invisible is one promotion away from
   being a wrong answer nobody notices.

3. **`_preflight_exit_code` returns the old constants.** It maps preflight
   findings to `EXIT_TRANSPORT`, which is `2` today and `3` under the new
   contract. Renumbering without moving it makes `build start` report a dead
   proxy as a usage error — a script would then retry nothing and an operator
   would edit a spec that is fine. Move the constants and the mapper together,
   in one commit, with the test that pins the pairing.

4. **The enforcement-word sweep reads help strings.**
   `tests/test_final_sweep.py:459` bans `budget`, `cap`, `caps`, `capped`,
   `quota`, `throttle`, `breach`, `enforce`, `exceed`, `overspend` and their
   inflections in identifiers **and non-docstring string constants**, across
   all of `factory/`. Argparse help text is a string constant. A `--help` line
   that says "spend cap" or "budget" fails the sweep. Say **bound** or
   **limit**; the concurrency flag is `--max-concurrent-nodes`, as it already
   is.

5. **`--json` is a dump, never a re-assembly.** `status_command`'s comment
   states the rule: the query payload is printed as it arrived so `EpicStatus`
   has exactly one definition and `--json` cannot drift from it. Every new
   `--json` surface follows it. Do not define a response schema for a document
   some other module already owns.

6. **Stdout stays clean, on every path.** All four existing CLIs guarantee that
   only requested output reaches stdout — errors, preflight findings and probe
   skips all go to stderr. The shared boundary is the single place this could
   regress for every command at once. The dispatcher's own help goes to stdout
   on a bare invocation (it was requested) and to stderr on a usage error (it
   was not).

7. **One probe is already broken, and it is not this epic's to fix.**
   `factory/doctor/probes.py:517` calls `described.status.is_completed`, an
   attribute `WorkflowExecutionStatus` does not have, so `StaleWorktreeProbe`
   raises `AttributeError` whenever Temporal is reachable and candidate epics
   exist — reproduced 2026-08-08 against a scratch database. `ergane doctor`
   must render it as one line naming `--debug` (FR-004), which is the CLI's
   whole responsibility here. Do **not** fix the probe inside this epic: it is
   filed separately, and a node that wanders into `probes.py` is a node whose
   diff the judge will score against the wrong scenarios.

8. **Two CLIs, two `_OperatorError` classes, one behaviour.** They are not
   identical — `workgraph`'s carries a per-raise exit code, `roadmap`'s does
   not, and `doctor` has a third class named `_UserError`. The shared type must
   keep the per-raise code, because `status_command` uses it to report a
   transport failure as transport. Collapsing them to a code-less exception
   would silently demote every transport error to 1.

## Complexity Tracking

| Risk | Why it is real | Mitigation |
|---|---|---|
| A ported handler's behaviour drifts | 943 + 453 + 226 + 198 lines move rooms | The existing per-CLI test files move with their handlers and are not rewritten (SC-003) |
| Transport errors silently become user errors | `EXIT_TRANSPORT` changes value from 2 to 3 | Trap 3: constants and `_preflight_exit_code` move together, pinned by a test |
| The contract holds for today's commands and not tomorrow's | Every per-command test passes while the next CLI diverges | FR-002/FR-003: a sweep over the **parser tree**, plus the no-subclass assertion |
| The cutover lands mid-epic and reddens siblings | US5 deletes scripts US2–US4's tests invoke | The work graph chains US5 last on US4 merged |
| A credential reaches `ergane env` | It is a command whose whole job is to report configuration | `env` prints set/not-set for anything credential-shaped, never a value; asserted by the 001 grep pattern |
| Help text fails the enforcement sweep | Argparse help is a scanned string constant | Trap 4, and the sweep runs in CI already |
| `ergane` collides with an installed binary | The name is new on this host | T001 checks `command -v ergane` before anything else |
