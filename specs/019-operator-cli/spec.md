---
state: draft
# Drafted 2026-08-08 from round 2 of the standing audit report — findings U1
# (no front door) and U2 (three exit-code contracts, one of them accidental).
# Round 2 was produced by invoking every command rather than by reading source,
# which is why U2 exists at all: `factory-doctor` forgot to subclass
# ArgumentParser, so it exits 2 on a typo while its own module docstring says 2
# means a service is not answering. No source review would have caught it.
#
# Numbered 019: 010–014 stay reserved for audit-triage epics, 015 is the
# doctor, 016 the delta, 017 the peer channel, 018 agent home isolation.
#
# Scope is deliberately a rename plus a contract. Read the Assumptions before
# widening it: `refine`, `audit`, `debug`, `logs` and `stack` are named in this
# spec only so the grammar has room for them, and a plan or a task that
# implements one of them is out of scope. The single exception is stated
# outright in US4 and is not an accident.
#
# The 020 edge is a sequencing decision, not a code dependency. 020 rewrites
# `factory-epic landed`'s branch default and `_build_baseline`'s hardcoded
# "main" — the same parsers US2 and US3 port. Landing 020 second means porting
# them, then re-verifying this spec's reuse inventory against a moved target,
# for no gain. Declaring the edge here makes the roadmap enforce the order
# rather than leaving it to a note somebody has to read.
depends_on_landed: [005-workgraph-interpreter, 009-roadmap-scheduler, 015-factory-doctor, 020-landing-attribution]
---

# Feature Specification: The `ergane` Operator CLI

**Feature Branch**: `019-operator-cli`

**Created**: 2026-08-08

**Status**: Drafted the day the operator surface was audited by using it. The
factory ships four console scripts — `factory-epic`, `factory-usage`,
`factory-roadmap`, `factory-doctor` — and not one of them mentions the other
three. There is no command that lists them. An operator who knows one knows
one; the only complete inventory of the surface is a `[project.scripts]` table
in `pyproject.toml`, which is not a place anyone looks when they are trying to
find out what they can do.

**Input**: Two findings, and a third the first two produced between them.

**U1 — no front door.** The four scripts share a prefix and nothing else. They
were built one epic at a time and each named itself after the component it
came from, so the surface is organised by the factory's internals rather than
by the operator's job. `factory-epic` alone carries `derive`, `landed`,
`onboard`, `start` and `status` — five verbs spanning "compile a spec",
"read git", "check a clone", "spend money" and "look at a running workflow",
which are four different jobs sharing one noun because they shared one epic.

**U2 — three exit-code contracts.** `001/contracts/cli.md` says usage is `2`
and a missing ledger is `3`. `005/contracts/cli.md` says a user error is `1`
and transport is `2`. Both are binding, both landed, and they disagree. Worse,
`factory-doctor` honours neither: its module docstring claims 005's scheme,
but its parser is a plain `argparse.ArgumentParser` while the other two 005-era
CLIs subclass it to override `error()`. A typo exits 2 — argparse's native
usage code — which under the docstring's own contract means "a service is not
answering". A script that retries on 2 would retry a spelling mistake forever.

**The third finding is the mechanism.** 005's scheme is only reachable by
fighting argparse, and the way you forget to fight argparse is to not subclass
it. Every CLI written after 005 starts from a default that is wrong under 005's
contract and right under 001's. The divergence is not carelessness; it is the
predictable result of a contract that requires an override in every file that
will ever be written. The fix is to stop overriding: adopt usage `= 2`, so the
next CLI in this repository is correct by doing nothing.

None of this is a defect in what the commands *do*. Every one of them works,
and three of them were written in the same week the factory built itself. It
is a defect in how they are found, entered and scripted against.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - One front door, one contract (Priority: P1)

As the factory operator, I type `ergane` and see every noun the factory
answers to, with one line each; I type `ergane <noun>` and see its verbs; and
whatever I type, the exit code means the same thing, so that the surface can be
learned by exploring it and scripted against without reading four modules.

The dispatcher is the whole of this story. It registers no work of its own —
nouns arrive in US2, US3 and US4 — and it is worth landing alone because it
converts four independent programs into one program with four rooms, and
because the contract it fixes is the thing every later story must inherit
rather than re-decide.

Four codes, and the reason each exists:

- **0** — it worked. Including an empty result: no findings, no specs, no
  remaining delta. Emptiness is an answer.
- **1** — the operator can fix it without leaving the terminal. A spec that
  does not parse, a graph with zero nodes, an epic id that names nothing, a
  branch that does not exist.
- **2** — the command line itself is wrong: unknown verb, unknown flag,
  missing argument. This is argparse's own code, unmodified, which is what
  makes it survivable.
- **3** — something the factory talks to did not answer: Temporal, the proxy,
  a missing ledger. Retryable by a script; `1` and `2` never are.

`130` is reserved for `Ctrl-C`, which is a signal and not a factory outcome.

**Why this priority**: every other story registers into this. It also has
standalone value the day it lands — `ergane --help` is the first complete
answer to "what can I do here" that has ever existed in this repository.

**Independent Test**: with only the dispatcher registered, `ergane` and
`ergane --help` list the nouns and exit 0; an unknown noun exits 2 with a usage
line on stderr and nothing on stdout; a handler that raises the shared operator
error exits 1 with one line on stderr; a handler that raises an unexpected
exception exits 1 with one line naming `--debug`, and `--debug` prints the
traceback; `Ctrl-C` exits 130. No subclass of `argparse.ArgumentParser` exists
anywhere under `factory/`.

**Acceptance Scenarios**:

1. **Given** no arguments, **When** `ergane` runs, **Then** it prints every
   registered noun with a one-line description and exits 0 — a bare invocation
   is a request for orientation, never an error.
2. **Given** an unknown noun or an unknown flag, **When** the command runs,
   **Then** it exits **2** with a usage line on stderr and stdout is empty.
3. **Given** a handler that raises the shared operator error, **When** the
   command runs, **Then** it exits **1**, the message is one line on stderr,
   and no traceback is printed.
4. **Given** a handler that raises an unexpected exception, **When** the command
   runs, **Then** it exits **1** with one line on stderr naming `--debug` as
   the way to see more, and **When** the same command runs with `--debug`,
   **Then** the traceback is printed.
5. **Given** `ergane --version`, **When** it runs, **Then** it prints the
   package version, the revision of the tree it is running from, and the
   Temporal address and proxy url it *would* dial, without dialling either and
   without printing any credential value.
6. **Given** any registered subcommand path, **When** it is given a bad flag,
   **Then** it exits 2 — the contract is a property of the dispatcher, not a
   habit each handler is trusted to keep.

---

### User Story 2 - The spec noun: everything before the money (Priority: P1)

As the factory operator, `ergane spec` is where I work on text — I list the
corpus, validate one spec before I spend anything on it, compile its graph, and
ask git which of its stories have landed — so that the cheap half of the job
has its own room and nothing in it can start a workflow.

The noun is `spec` and not `epic`. A spec is durable text an operator edits; an
epic is one `EpicWorkflow` execution of it. They share an id, they are not the
same object, and the CLI has been conflating them since `factory-epic derive`
— a command that never touches an epic — was named.

`validate` is the one verb here that is new, and it is a composition rather
than a capability: the frontmatter grammar, the derivation, and the persona
registry check all exist and all refuse independently today. Running them
together, before dispatch, is the pre-dispatch pass CLAUDE.md already names as
the measured leverage.

**Why this priority**: it is the half of the surface that costs nothing to run
and prevents the half that costs money. It is also the half an operator uses
most.

**Independent Test**: against a fixture corpus, `spec list` names every spec
with its state and each blocked spec's unsatisfied edges; `spec validate` exits
0 on a sound spec and 1 on a spec with a frontmatter error, a derivation
rejection and an unserved persona — reporting all three at once, not the first;
`spec landed` still resolves the branch 020 taught it to resolve, and says which
one; every verb's `--json` parses.

**Acceptance Scenarios**:

1. **Given** a specs root, **When** `ergane spec list` runs, **Then** every
   spec appears with its state and every blocked spec names its unsatisfied
   dependencies — never a bare "blocked" — matching what `factory-roadmap
   render` prints today.
2. **Given** a spec with a frontmatter error, a work-graph rejection and a
   persona alias no registry serves, **When** `ergane spec validate` runs,
   **Then** it exits 1 and every one of the three is named in the same run —
   an operator who fixes one and re-runs to find the next is paying for the
   round trip the staged-rejection discipline exists to avoid.
3. **Given** a spec that validates, **When** `ergane spec validate` runs,
   **Then** it exits 0 and says what it checked — a pass that does not name its
   checks is indistinguishable from a pass that checked nothing.
4. **Given** a target repository declaring `landing_branch` in `factory.yaml`
   (020's key), **When** `ergane spec landed <spec-dir>` runs with no branch
   argument, **Then** it reports against that declared branch and names it in
   the output — the port carries 020's resolution across unchanged rather than
   re-deciding it, and an explicit `--default-branch` still overrides.
5. **Given** `--json` on any of `list`, `validate`, `derive`, `landed`,
   **When** it runs, **Then** stdout is a single parseable document and the
   human rendering is absent — the two are formats of one answer, never two
   answers.

---

### User Story 3 - The build noun: everything that costs money or steers it (Priority: P1)

As the factory operator, `ergane build` is where runs live — I start one, watch
it, pause it, resume it, kill it, and answer what it asks me — so that the
five signals the interpreter has always accepted stop being reachable only
through `temporal workflow signal` and a hand-typed JSON array.

The signals are not new and Temporal is not superseded. `pause_epic`,
`resume_epic`, `kill_epic`, `question_answered` and `escalation_resolved` are
declared on `EpicWorkflow` and two of them are already sent from Python by the
notifier. This story gives them an operator surface — the same
`handle.signal(...)` call, typed by a human instead of by the Telegram bridge.
005's contract said to reach for the `temporal` binary instead; that scoping
call is what this spec supersedes, not the mechanism it named.

Two of the five need more than a signal to be usable. `answer` and `resolve`
require an id the operator does not have: `epic_status` reports nodes and
landings and says nothing about what is parked. The ids do exist and are
durable — the notifier writes every question and every escalation to the
verification store before it sends a message, precisely so a crash leaves
something recoverable. So `answer` and `resolve` with no id **list what is
pending** from that store, and with an id **send the signal**. No new record,
no new table, two existing readers.

`kill` confirms. A kill is never taken back — the interpreter has no un-kill
signal, by design — and a verb that spends an epic on one keystroke should ask.

**Why this priority**: this is the money. It is also where the operator's grip
is currently thinnest: pausing a running epic today means knowing that
`pause_epic` is spelled that way.

**Independent Test**: against a scripted workflow under time skipping, `build
start` refuses a zero-node graph and a missing proxy url before connecting;
`status` prints a document byte-identical to the query's under `--json` with
execution status and live spend as sibling keys; each of pause/resume/kill
sends exactly its own signal and nothing else; `kill` without `--yes` refuses
on a declined prompt and sends nothing; `answer` with no id lists the epic's
pending questions and sends nothing; `answer` with an expired id refuses
without signalling.

**Acceptance Scenarios**:

1. **Given** a compiled graph and a reachable proxy, **When** `ergane build
   start` runs, **Then** the preflight ladder runs before any workflow is
   started — graph parses, graph is structurally sound, proxy url is present,
   aliases are served — and a refusal at any rung starts nothing.
2. **Given** a preflight refusal caused by the proxy not answering, **When**
   `build start` runs, **Then** it exits **3**, not 1 — a dead proxy is a
   service, and a script that treats it as a bad spec will edit the spec.
3. **Given** a running epic, **When** `ergane build pause` runs, **Then** the
   node in flight finishes and nothing new dispatches, and **When** `ergane
   build resume` runs, **Then** dispatch continues — the signal's own
   documented contract, unchanged.
4. **Given** a running epic, **When** `ergane build kill` runs without `--yes`
   and the prompt is declined, **Then** no signal is sent and the exit code is
   1; **When** it runs with `--yes`, **Then** exactly `kill_epic` is sent.
5. **Given** an epic with a parked question, **When** `ergane build answer
   <epic-id>` runs with no question id, **Then** every pending question for
   that epic is listed with its id, its node, its text and its expiry, and no
   signal is sent.
6. **Given** a question id that has already been answered or has expired,
   **When** `ergane build answer` names it, **Then** the command exits 1
   saying which, and sends nothing — signalling a workflow that has already
   moved on is worse than refusing.
7. **Given** an escalation whose record offers a closed set of choices, **When**
   `ergane build resolve` is given a choice outside that set, **Then** it exits
   1 naming the choices the record actually offers; and **When** it is given no
   choice at all, **Then** it lists them and sends nothing — the command never
   picks one.

---

### User Story 4 - The rest of the surface, including the room with no door (Priority: P2)

As the factory operator, the remaining commands — the scheduler, the doctor,
the findings ledger, the spend table, clone onboarding — live under the same
front door with the same contract, so that "what can I do here" has exactly one
answer and no capability is reachable only by knowing it exists.

Four of the five are ports: the handlers already exist and move as they are.
The fifth is not, and the difference is worth stating rather than smuggling.

**`RoadmapWorkflow` has no operator surface at all.** It is registered in the
worker, it carries `pause_roadmap`, `resume_roadmap`, `promote_spec` and a
`roadmap_status` query, and the only shipped CLI for its package renders a
static view of the corpus. Nothing in this repository starts it, pauses it, or
asks it what it is doing. The scheduler — the component whose whole purpose is
to run the factory unattended — is reachable today only through Temporal's own
tooling. Wiring its existing signals to verbs adds no scheduler behaviour and
is the one place where "port only" would have left the new front door with a
locked room behind it.

`doctor` and `findings` split on the audit's own line: the doctor runs probes
and answers "can this machine build right now"; the findings ledger is the
durable record of what was found. One is a question, the other is a filing
cabinet, and they were one command because they were one epic.

**Why this priority**: real, and the roadmap gap is sharper than it looks — but
US2 and US3 are the daily surface, and an operator can reach these through the
old scripts until the cutover in US5.

**Independent Test**: `roadmap start` starts the workflow under the id
convention and refuses a running collision by name; `pause`/`resume`/`promote`
each send exactly their own signal; `status` prints the query document;
`doctor` runs every probe and files what it finds; `findings list --severity`
and `--status` filter the ledger; `usage` prints today's table unchanged;
`repo onboard` prints today's profile unchanged; every read verb has `--json`.

**Acceptance Scenarios**:

1. **Given** no roadmap running, **When** `ergane roadmap start` runs, **Then**
   the scheduler starts under a deterministic workflow id and the id is
   printed; **When** one is already running, **Then** it exits 1 naming the
   collision and starts nothing.
2. **Given** a running roadmap, **When** `ergane roadmap pause` runs, **Then**
   the child epic in flight finishes and nothing new dispatches; **When**
   `ergane roadmap promote <spec-dir>` runs, **Then** the spec is treated as
   ready on the next scheduling pass and `ergane roadmap status` reports the
   promotion as a promotion rather than as a file state.
3. **Given** the doctor's probes, **When** `ergane doctor` runs, **Then** a
   probe that cannot reach its service is reported as unreachable and exits
   **3**, and a probe that raises anything else is reported as one line naming
   `--debug` rather than as a traceback — `factory-doctor check` prints a
   thirty-line traceback today, reproduced 2026-08-08.
4. **Given** a ledger with findings of several severities and statuses, **When**
   `ergane findings list --severity critical --status open` runs, **Then** only
   matching findings are printed, and the same filters apply under `--json`.
5. **Given** no ledger file at all, **When** `ergane usage` runs, **Then** it
   exits **3** — the code 001 already chose for exactly this, now meaning the
   same thing everywhere.
6. **Given** `ergane env`, **When** it runs, **Then** every environment
   variable the CLI reads is listed with whether it is set and where it
   resolves from, and no value of any credential is printed — set or unset is
   the whole answer for a secret.
7. **Given** `ergane completion bash`, **When** it runs, **Then** it prints a
   completion script to stdout and exits 0, and sourcing it completes nouns and
   verbs.

---

### User Story 5 - The cutover (Priority: P2)

As the factory operator, the four `factory-*` scripts stop existing in the same
change that registers `ergane`, and every place in the repository that named
one of them names the new command instead, so that there is never a period in
which two front doors disagree about the contract.

No alias, no deprecation shim, no compatibility window. Nothing in this
repository shells out to the console scripts — the worker imports the packages
directly and the workflows call activities — so the blast radius is exactly:
`pyproject.toml`, the strings inside `factory/` that recommend a command to an
operator, the tests that invoke them, and the two operator-facing documents.
Verified by search rather than assumed; T001 re-verifies it against the tree
that hosts the work.

Landed spec files are **not** edited. `001/contracts/cli.md` and
`005/contracts/cli.md` keep their text; the decision log records the
supersession, which is the pattern D-031 and D-034 already established and the
only pattern under which a landed spec's fingerprint stays stable.

**Why this priority**: last by construction. It is also the story that makes
the epic honest — a front door that leaves four side doors open has not
replaced anything.

**Independent Test**: after the change, `pyproject.toml` registers `ergane` and
nothing else; a repository-wide search for the four old names finds them only
under `specs/` and `docs/decisions.md`; the CLAUDE.md sweep passes with its
command set moved; the full suite is green.

**Acceptance Scenarios**:

1. **Given** the change, **When** `pyproject.toml` is read, **Then**
   `[project.scripts]` names `ergane` and none of the four old scripts.
2. **Given** a repository-wide search for `factory-epic`, `factory-usage`,
   `factory-roadmap` or `factory-doctor`, **When** it runs after the change,
   **Then** every remaining hit is inside `specs/` or `docs/decisions.md` — the
   historical record, which is not edited.
3. **Given** an operator-facing string that recommends a command — a probe's
   remediation, a scaffolded finding, a zero-node graph's advice — **When** it
   is printed after the change, **Then** it names a command that exists.
4. **Given** `tests/test_claude_md.py`, **When** the suite runs after the
   change, **Then** it passes: every command CLAUDE.md names resolves, and its
   sweep asserts the new command set rather than the old one.
5. **Given** the decision log, **When** it is read after the change, **Then**
   one new entry records the two superseded exit-code tables and 005's CLI
   scoping clause, names what replaced them, and neither contract file has been
   modified.

### Edge Cases

- A spec directory named `status`, `start`, `pause` or any other verb: the
  grammar avoids this by construction — every noun's verb is required and
  positional, so a spec id is never in verb position. This is why
  `ergane build 019-foo` is not the spelling; see Assumptions.
- A `--json` flag on a verb whose only output is a workflow id: `--json` must
  still produce a document, not a bare string, or a script's parser breaks on
  the one command it thought it understood.
- `ergane doctor` while no worker is running: the doctor's own stale-worker
  probe is the answer, not an error. Unreachable *services* exit 3; a probe
  that successfully finds a problem exits under the doctor's own severity
  contract, unchanged by this spec.
- `ergane build answer` against an epic that is not running: the store may
  still hold a pending row from before the crash. Listing it is correct;
  signalling it is not, and the refusal must say the epic is gone rather than
  the question is bad.
- `ergane completion` on a shell that is not bash or zsh: exit 2 naming the
  shells supported. A completion script for the wrong shell is worse than none.
- The dispatcher itself failing to import a noun's module — a partially
  installed tree: the failure must name the noun and exit 1, not print a
  traceback about an import.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A single console script `ergane` MUST be the entry point.
  `ergane` with no arguments and `ergane --help` MUST list every registered
  noun with a one-line description; `ergane <noun>` and `ergane <noun> --help`
  MUST list that noun's verbs; `ergane <noun> <verb> --help` MUST document its
  flags. A bare invocation MUST exit 0.
- **FR-002**: Every subcommand MUST share one exit-code contract: `0` success
  including an empty result, `1` an operator-fixable error, `2` a usage error,
  `3` a service that did not answer, `130` interrupt. The contract MUST hold
  for every registered path, asserted by a sweep over the parser tree rather
  than by a test per command.
- **FR-003**: No subclass of `argparse.ArgumentParser` MUST exist under
  `factory/`; usage errors MUST take argparse's own exit code. The sweep MUST
  assert this, because the absence of an override is what makes the contract
  hold for CLIs not yet written.
- **FR-004**: One shared error boundary MUST wrap every handler: one operator
  error type rendered as a single line on stderr with exit 1; a service failure
  rendered with the address that was dialled and exit 3; any other exception
  rendered as one line naming `--debug`, with `--debug` printing the traceback.
  Only requested output MUST reach stdout, on every path.
- **FR-005**: `ergane --version` MUST report the package version, the revision
  of the tree it runs from, and the Temporal address and proxy url it would
  dial, without dialling either and without printing any credential value.
- **FR-006**: `ergane spec list [<specs-root>]` MUST render every spec with its
  state and name each blocked spec's unsatisfied dependencies, with `--json`.
- **FR-007**: `ergane spec validate <spec-dir>` MUST run the frontmatter
  grammar, the work-graph derivation and the persona-registry check against one
  spec and report **every** refusal in a single run, exiting 1 if any refused
  and 0 with a statement of what was checked if none did. It MUST NOT connect
  to any service.
- **FR-008**: `ergane spec derive <spec-dir> [--delta]` MUST compile the spec's
  graph, preserving today's derivation and delta provenance output, with
  `--json`.
- **FR-009**: `ergane spec landed <spec-dir>` MUST preserve 020's
  manifest-driven branch resolution unchanged — the port MUST NOT reintroduce a
  hardcoded default — and MUST name the branch it used in its output. The
  resolution itself is 020's requirement, not this spec's; all that is owed here
  is that moving the command does not lose it, and that the answer says what it
  was computed against.
- **FR-010**: `ergane build start <spec-dir>` MUST run the existing preflight
  ladder — graph parse, structural validation, proxy url presence, alias check
  — before any workflow is started, and a proxy that does not answer MUST exit
  3.
- **FR-011**: `ergane build status <epic-id> [--json]` MUST print the workflow
  query's document unchanged, carrying execution status and live spend as
  sibling keys, never merged into it.
- **FR-012**: `ergane build pause|resume|kill <epic-id>` MUST each send exactly
  the corresponding existing signal and nothing else. `kill` MUST require an
  interactive confirmation unless `--yes` is given, and a declined confirmation
  MUST send nothing.
- **FR-013**: `ergane build answer <epic-id> [<question-id> <text>]` MUST list
  the epic's pending questions from the existing verification store when no id
  is given, and send `question_answered` when one is. It MUST refuse an id that
  is already resolved or expired, naming which, and send nothing.
- **FR-014**: `ergane build resolve <epic-id> [<escalation-id> <choice>]` MUST
  behave as FR-013 for escalations, validating the choice against the closed
  set the record itself carries, and MUST NOT supply a default choice under any
  circumstance.
- **FR-015**: `ergane roadmap start|pause|resume|promote|status` MUST give
  `RoadmapWorkflow` its first operator surface, wiring its existing signals and
  query. It MUST add no scheduling behaviour: a running collision refuses by
  name, and `status` prints the query's document.
- **FR-016**: `ergane doctor` MUST run every probe, and `ergane findings
  list|report|resolve|promote` MUST carry the ledger verbs. `findings list`
  MUST accept `--severity` and `--status` filters and `--json`. A probe whose
  service does not answer MUST exit 3 and MUST NOT raise.
- **FR-017**: `ergane usage` MUST preserve today's aggregation and rendering
  exactly, including the unmeasured-cell convention, and a missing or
  unreadable ledger MUST exit 3.
- **FR-018**: `ergane repo onboard <clone> [--json]`, `ergane env` and `ergane
  completion bash|zsh` MUST exist; `env` MUST report whether each variable the
  CLI reads is set and never its value when the variable is a credential.
- **FR-019**: The four `factory-*` console scripts MUST be removed from
  `pyproject.toml` in the same change that registers `ergane`. No alias and no
  deprecation shim MUST be introduced.
- **FR-020**: Every reference to a removed script outside `specs/` and
  `docs/decisions.md` MUST move in the same change — operator-facing strings
  inside `factory/`, the tests that invoke them, `CLAUDE.md`,
  `docs/architecture.md` and `scripts/ergane-env.sh` — and the CLAUDE.md sweep
  MUST assert the new command set.
- **FR-021**: The decision log MUST record, at the next free number, the
  supersession of `001/contracts/cli.md`'s and `005/contracts/cli.md`'s
  exit-code tables and of 005's clause scoping signals to the `temporal`
  binary. Neither contract file MUST be edited.

### Key Entities

- **Noun** — a room in the CLI: `spec`, `build`, `roadmap`, `doctor`,
  `findings`, `usage`, `repo`. Named for the operator's job, never for the
  package the handler lives in.
- **Verb** — one action within a noun, always required and always positional,
  so no spec id can ever be mistaken for a command.
- **Exit contract** — the four codes plus the interrupt, one meaning each,
  enforced by the dispatcher rather than remembered by each handler.
- **Error boundary** — the single place a handler's exception becomes an exit
  code and a line of stderr.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator who knows only the word `ergane` can reach every
  command in the factory in two steps: `ergane`, then `ergane <noun>`.
- **SC-002**: A parametrised sweep over every registered subcommand path
  asserts a bad flag exits 2 and an unresolvable argument exits 1. Adding a
  noun without honouring the contract fails that sweep.
- **SC-003**: The behaviour of every ported command is unchanged: for each of
  `spec list`, `spec derive`, `spec landed`, `build status`, `usage`, `repo
  onboard` and `findings list`, the output matches what the corresponding old
  script printed for the same input.
- **SC-004**: No invocation of `ergane` prints a traceback without `--debug`.
  `ergane doctor` against a machine with no worker, no Temporal and no proxy
  reports each unreachable service and exits 3; a probe that fails for any
  other reason — there is one such defect open today — is one line, not thirty.
- **SC-005**: `RoadmapWorkflow` is startable, pausable, promotable and
  queryable from the CLI, with no use of the `temporal` binary or the Web UI.
- **SC-006**: A repository-wide search for the four old script names finds hits
  only under `specs/` and `docs/decisions.md`, and the full suite is green.

## Work Graph

A chain, not a fan-out, and deliberately so. US2, US3 and US4 each register a
noun into the dispatcher US1 lands, which means all three edit the same module.
Two concurrent worktrees editing one module is the collision that node
concurrency avoids by disjointness rather than by luck — the argument 018 made
about `adapter.py`, and the reason 009's first run built US2 against a tree
that had no `factory/roadmap/` in it. The default bound is one node at a time
anyway, so the chain costs nothing real and removes the hazard entirely.

Every edge is a **merge** edge. A pass edge here would let a node be dispatched
into a worktree whose base predates the dispatcher it is registering into,
which is the exact failure the merge edge exists for.

US5 chains last on US4 because it removes the scripts the other four stories'
tests still invoke: a cutover that lands before its predecessors turns their
worktrees red for a reason that has nothing to do with their work.

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-006, FR-007, FR-008, FR-009]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-010, FR-011, FR-012, FR-013, FR-014]
US4:
  depends_on: []
  depends_on_merged: [US3]
  implements: [FR-015, FR-016, FR-017, FR-018]
US5:
  depends_on: []
  depends_on_merged: [US4]
  implements: [FR-019, FR-020, FR-021]
```

## Assumptions

- **The verb is required; `ergane build <spec-dir>` is not the spelling.** The
  shorthand reads better and cannot be parsed: argparse cannot distinguish an
  optional subcommand from a positional without a normalisation hack in the
  dispatcher, and the hack silently turns a spec directory named `status` into
  a command. Every noun takes a required verb, which is also what makes the
  grammar uniform enough to complete and to sweep.
- **`refine`, `audit`, `debug`, `logs` and `stack` are named nowhere in this
  spec's requirements.** They are the intended shape of the grammar's growth
  and each is its own spec. A task that implements one of them is out of scope,
  and `stack` in particular should wrap supervised units rather than spawn
  processes, so two supervisors never disagree about whether the worker runs.
- **`ergane doctor` and `ergane usage` take no verb**, unlike every other noun.
  Each has exactly one action, and `brew doctor` is the convention. The rule is
  stated so the exception is a decision rather than an inconsistency: a noun
  with one action takes no verb; a noun with two or more always does.
- **The daemons stay outside the CLI.** `factory/worker.py` and
  `factory/notify/service.py` remain `python -m` entry points in this spec.
  Wrapping them is `stack`'s job and belongs with supervision.
- **020-landing-attribution has landed**, declared as a frontmatter edge. It
  owns branch resolution — `factory.yaml`'s `landing_branch`, `factory-epic
  landed`'s flag default, and `_build_baseline` — in the same parsers US2 and
  US3 port. This spec inherits that fix and asserts it survives the move; it
  does not restate it. Should 020 be abandoned or descoped, FR-009 and trap 2
  both have to be rewritten before this epic dispatches, because they currently
  assume the work is already done.
- **Nothing in this repository shells out to the console scripts**, verified by
  search at drafting time. If T001 finds that has changed, the cutover's blast
  radius has changed with it and the plan must be corrected before deriving.
- **The audit findings this spec answers are U1 and U2**, with U8 (the missing
  `findings list` filters) folded into FR-016 because it is one flag on a
  command this spec was already moving. The remaining U-findings are not in
  scope.

## Decision: the front door is a rename plus a contract, and the contract stops fighting argparse (decided 2026-08-08, Bryan)

Six calls, made in conversation the day the surface was audited by using it:

1. **The name is `ergane`, and there is exactly one.** `factory-` named the
   component; the operator does not work on components. Four scripts become one
   program with rooms.
2. **The object noun is `spec`, and the CLI never says "epic".** The glossary
   keeps **Epic** for one execution; the durable text an operator edits is a
   spec, and the run is a build. `factory-epic derive`, which never touched an
   epic, is what the conflation looks like in practice.
3. **Usage errors are 2.** 005's scheme was reachable only by overriding
   argparse in every file, and the way to forget is to write a new file. The
   contract now agrees with the default, so the next CLI is correct by doing
   nothing. This supersedes 005's table and adopts 001's, which was right for
   the wrong reason.
4. **Services are 3, everywhere.** 001 already used 3 for a missing ledger.
   Generalising it gives scripts one retryable code and leaves 1 and 2 as the
   two that never are.
5. **Hard cutover, no shim.** A deprecation window means two front doors with
   two contracts, which is the condition this spec exists to end. Nothing
   shells out to the scripts, so the window would buy nothing.
6. **The first spec adds no capabilities**, with one stated exception: the
   roadmap's verbs, because the scheduler has no operator surface at all and
   shipping a front door with a locked room behind it would be a worse outcome
   than a slightly wider scope.

**The decision-log number is deliberately unassigned here** — claimed at
landing time in `docs/decisions.md`, after whatever 017 and 018 consume.
