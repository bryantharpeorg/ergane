---
state: draft
# Drafted 2026-08-11 in the same operator planning session as 033-ergane-install.
# The pair divides the provisioning model: 033 is once-per-host (the control
# plane), this is once-per-repo (membership). Decisions assumed, made in that
# session: the brand rename (`.ergane/` runtime root, `ergane.yaml` manifest —
# its own small spec, ordered before 023 lands); ONE Temporal namespace with the
# repo slug woven into workflow IDs; committed manifest = authoritative
# membership, engine registry = derived rebuildable cache; the repo is never
# absorbed into the tool's world (the anti-Gastown-rig stance — Bryan's exact
# grievance is still Q6, to be recorded here when he states it).
#
# Numbered 034: 032 is replay-determinism (48aa133, a concurrent session's),
# 033 is ergane-install, 011–014 stay reserved for audit-triage epics.
depends_on_landed: [003-merge-queue, 019-operator-cli, 040-manifest-rename]
---

# Feature Specification: Ergane Init

**Feature Branch**: `034-ergane-init`

**Created**: 2026-08-11

**Status**: Draft

**Input**: Operator direction: "when a new repo comes, ergane is available on
system as a CLI and the user runs `ergane init .` to register the repo as
something managed by ergane, in a way that keeps their git worktrees entirely
separate — the tool comes to the repo, `git init`-style, never the repo into
the tool's directory world."

**The principle.** Membership is a fact about the repo, carried *by* the
repo: a committed `ergane.yaml` is what makes a repo managed, exactly as a
`.git/` is what makes a directory a repository. `ergane init` is therefore
three bounded acts — write the declarations into the repo, point the engine
at it, prove the result — and none of them may change what the repo *is*: it
stays a normal repository, fully usable by someone who has never heard of
Ergane, its history written only by its operator. Init writes files; it
never commits, never pushes, never rearranges. The engine's registry is a
pointer cache derived from these committed facts, rebuildable at any time,
authoritative about nothing.

**What already exists.** The readiness judgment is built and pure:
`evaluate_repo` (mergequeue/onboard.py, the 003 crossover's US3) turns
gathered repo facts into findings — visibility, queue enabled on the default
branch, manifest valid, and the two-way gate↔check parity that keeps the LLM
judge out of CI. The activity that gathers those facts (`validate_target_repo`)
exists beside it. This spec puts a scaffold in front of that judgment and a
registry behind it; the judgment itself is reused, extended with the facts
init newly creates.

**Declared, never auto-detected.** D-009 governs the scaffold: the manifest
records what the operator *declares*, not what a detector guessed. The
interview may propose (it can see a `pyproject.toml` as well as anyone), but
every proposal is confirmed or corrected by the operator before it is
written, and nothing enters `ergane.yaml` silently. A wrong guess written
silently becomes a gate the factory enforces; a wrong guess proposed aloud
costs one keystroke.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The scaffold writes the repo's declarations (Priority: P1)

As an operator inside an app's checkout, `ergane init .` interviews me —
landing branch, gates (name and command, one or more), standards document
path, runtime image, repo slug (defaulting to the directory name) — and
writes exactly two things into the tree: `ergane.yaml` at the root, and a
`.gitignore` entry for `.ergane/`. It creates the `.ergane/` runtime root.
It commits nothing: the final output names the files written and shows the
`git add`/`git commit` the operator will run, because the repo's history
belongs to its operator.

Re-running init on a scaffolded repo loads the existing manifest as defaults
and edits rather than clobbers, mirroring 033's walkthrough contract:
validate at entry with the parser's own rules, never write what the parser
would refuse.

**Why this priority**: the committed manifest is membership; every other
story consumes it.

**Independent Test**: a scripted interview in a bare test repo produces an
`ergane.yaml` that the manifest parser accepts, a `.gitignore` containing
`.ergane/`, and an empty `.ergane/` directory; `git log` is unchanged and
`git status` shows exactly those paths; a second scripted run changing one
answer produces a diff touching exactly that key.

**Acceptance Scenarios**:

1. **Given** a git repo with no Ergane presence, **When** the operator
   completes the interview, **Then** `ergane.yaml` parses under the
   installed engine's manifest parser, declares every value the operator
   confirmed, and nothing the operator did not.
2. **Given** the interview proposes a gate command inferred from the tree
   (a visible `pyproject.toml` suggesting `uv run pytest -q`), **When** the
   operator corrects it, **Then** the corrected command is written and the
   proposal leaves no trace — proposals are ephemeral, declarations are not.
3. **Given** a completed init, **When** the operator runs `git log`,
   **Then** it is identical to before init ran — no commit, no branch, no
   tag was created by the tool.
4. **Given** a repo already scaffolded, **When** init re-runs and the
   operator changes only the standards path, **Then** the manifest diff
   touches exactly that key and `.gitignore` is untouched.
5. **Given** a directory that is not a git repository, **When** init runs,
   **Then** it refuses immediately, naming `git init` as the prerequisite —
   ergane joins repositories; it does not create them.
6. **Given** a checkout that is itself a git worktree of an
   ergane-managed repo (a factory node's worktree), **When** init runs,
   **Then** it refuses, naming the primary checkout — the factory's own
   workspaces are never registered as repos.
7. **Given** an operator standing in a repo, **When** they run bare
   `ergane init` with no path argument, **Then** it behaves exactly as
   `ergane init .` does — the path is optional and defaults to the working
   directory, as `git init` and every tool of this shape does. The output
   names the repo root it resolved, so a bare invocation is never ambiguous
   about which repository it joined.

---

### User Story 2 - The engine learns the repo exists (Priority: P1)

As an operator, completing init records the repo in the engine's registry —
slug, absolute path, manifest location — under the engine's state home,
never inside any repo. The slug is declared at init (defaulting to the
directory name), must be unique across the registry, and is the token woven
into workflow IDs, ledger rows, findings, and the per-repo memory-bank scope
(recorded here when the control plane declares a memory backend). `ergane
repo list` renders the registry with each entry's manifest status; `ergane
repo rebuild` re-verifies every entry against its committed manifest and
prunes entries whose repos are gone — the registry is a cache and must
always be treatable as one.

**Why this priority**: the scheduler and every fleet-level surface need to
enumerate managed repos; the committed manifest alone cannot be enumerated
without an index of where repos live.

**Independent Test**: after init in two test repos, `ergane repo list`
shows both slugs with valid-manifest status; deleting one repo's directory
and running `ergane repo rebuild` prunes exactly that entry; a third init
declaring an already-taken slug is refused naming the holder.

**Acceptance Scenarios**:

1. **Given** a completed init with slug `myapp`, **When** the registry is
   read, **Then** it maps `myapp` to the repo's absolute path, and the
   entry exists nowhere inside the repo itself.
2. **Given** a second repo declaring slug `myapp`, **When** init reaches
   registration, **Then** it refuses, naming the existing holder's path —
   slugs are the namespace token (one Temporal namespace, repo-scoped IDs)
   and collision would alias two repos' workflows.
3. **Given** a registry entry whose repo has been moved or deleted,
   **When** `ergane repo rebuild` runs, **Then** the dead entry is pruned
   and reported, and live entries are untouched — rebuilding is always
   safe.
4. **Given** the control plane declares a memory backend, **When** init
   completes, **Then** the repo's memory scope (its bank identity) is
   recorded on the registry entry, derived from the slug.
5. **Given** a repo whose manifest was deleted from the tree after
   registration, **When** `ergane repo list` runs, **Then** the entry
   renders with its manifest-missing status rather than disappearing —
   the cache reports drift from the authority; it never hides it.

---

### User Story 3 - GitHub is wired to enforce the declarations (Priority: P2)

As an operator, `ergane init` offers to wire the repo's GitHub side to
match the manifest: enable the merge queue on the declared landing branch,
require one status check named exactly after each declared gate, and — when
the repo has no CI producing those checks — scaffold a workflow file that
runs each declared gate command as a job of that exact name, written into
the tree for the operator to commit like everything else. Each wiring act
is idempotent and reported; anything the hosting plan forbids (a private
repo on a plan without merge queues, D-007) is refused with the constraint
named, not discovered later as a dead queue.

**Why this priority**: the gate↔check parity that `evaluate_repo` judges is
a contract between manifest and CI; init created the manifest half and must
offer the CI half, or every fresh repo fails its first check run.

**Independent Test**: against a disposable public GitHub repo, wiring
enables the queue, creates required checks matching the declared gates, and
writes a workflow file whose job names equal the gate names; re-running
wiring changes nothing and says so; a private test repo is refused at the
visibility check with D-007 cited.

**Acceptance Scenarios**:

1. **Given** a public repo with declared gates `test` and `smoke`, **When**
   wiring runs, **Then** the merge queue is enabled on the landing branch
   with required checks `test` and `smoke`, and the scaffolded workflow
   defines jobs named `test` and `smoke` running the declared commands.
2. **Given** wiring already applied, **When** it re-runs, **Then** every
   step reports already-satisfied and the repo's settings are unchanged.
3. **Given** a repo whose visibility forbids the merge queue, **When**
   wiring runs, **Then** it refuses at the visibility check, citing D-007
   and the two remedies (make it public, or a plan that queues private
   repos) — and the scaffold half of init is still usable.
4. **Given** `gh` is absent or unauthenticated, **When** wiring runs,
   **Then** it refuses naming the prerequisite and the exact login command,
   and offers to print the manual wiring steps instead.

---

### User Story 4 - Readiness is judged, not assumed (Priority: P2)

As an operator, `ergane init --check` (also the automatic last act of a
full init) gathers the repo's facts and renders findings through the
existing pure judgment, extended with what init itself created: manifest
present and parseable, `.ergane/` gitignored, registry entry present and
pointing here, landing branch exists, queue enabled, gate↔check parity
both ways, control plane reachable (delegated to 033's probes, reported as
one summary finding). One finding per check, failures actionable, no
failure masking another, exit non-zero on any failure.

**Why this priority**: the 003 judgment already refuses unready repos at
dispatch; surfacing the same refusals at init time moves the discovery from
the factory's first attempt (expensive, confusing) to the operator's
terminal (cheap, actionable).

**Independent Test**: a fully-wired test repo renders all-pass; breaking
each precondition one at a time — delete the gitignore line, drop the
registry entry, rename the landing branch, remove a required check — flips
exactly that finding to fail with a detail naming the fix.

**Acceptance Scenarios**:

1. **Given** a scaffolded, registered, wired repo, **When** `--check` runs,
   **Then** every finding passes and the exit code is 0.
2. **Given** `.ergane/` missing from `.gitignore`, **When** `--check`
   runs, **Then** that finding fails naming the exact line to add — the
   runtime root reaching git history is the failure the check exists to
   prevent.
3. **Given** a declared gate with no matching required check, **When**
   `--check` runs, **Then** the existing parity finding fails exactly as
   it does at dispatch today — one judgment, two doors.
4. **Given** the control plane down, **When** `--check` runs, **Then** the
   control-plane finding fails with 033's probe detail carried through,
   and every repo-local finding still renders.

---

### User Story 5 - A repo can leave (Priority: P3)

As an operator, `ergane repo forget <slug>` removes the registry entry
and nothing else. The manifest, the gitignore line, and `.ergane/` belong
to the repo; removing them is the operator's own git work if they want it.
An optional `--clean-runtime` additionally deletes the repo's `.ergane/`
contents after confirming no epic is currently running against the repo.

An optional `--export <dir>` writes the engine's repo-scoped records —
findings ledger rows, usage ledger rows, escalation history — into the
named directory in open formats (one JSONL file per store, plus one
human-readable markdown digest), so what the factory *learned* about the
repo leaves with the operator rather than with the engine. The directory
must lie outside `.ergane/` (which `--clean-runtime` may be emptying in
the same act); export writes files and commits nothing, like everything
else in this spec.

**Why this priority**: symmetry and trust — registration that cannot be
undone cleanly turns a pointer cache into a commitment. The export flag is
the portability principle's closing clause: the specs and constitution were
always the repo's; `--export` makes the engine-side history theirs too. It
is deliberately low priority — valuable at some point, blocking nothing
now, and nothing else in this spec depends on it.

**Independent Test**: after forget, `ergane repo list` no longer shows the
slug, the repo's tree is byte-identical, and a fresh `ergane init .` can
re-register it under the same slug. With `--export`, the directory contains
the repo's findings, usage, and escalation records in the documented
formats, and two exports against an untouched engine are byte-identical.

**Acceptance Scenarios**:

1. **Given** a registered repo, **When** forget runs, **Then** the registry
   entry is gone and the repo's working tree and history are untouched.
2. **Given** an epic currently running against the repo, **When** forget
   runs with `--clean-runtime`, **Then** it refuses, naming the running
   epic — the runtime root under an active epic is evidence in use.
3. **Given** a repo with findings, usage, and escalation history, **When**
   forget runs with `--export ./out`, **Then** `./out` contains one JSONL
   file per store holding exactly this repo's rows plus a markdown digest,
   the registry entry is gone, and nothing was written anywhere else.
4. **Given** forget run without `--export`, **When** it completes, **Then**
   no export is written — leaving quietly is the default; taking the
   records is a choice.

---

### User Story 6 - The repo gets a scheduler, not just a worker (Priority: P1)

As an operator, joining a repo gives it a roadmap schedule on the control
plane, so that flipping a spec to `ready` actually dispatches something.
Today nothing in this engine creates one: `factory/cli/roadmap.py` has
`start`, `pause`, `resume`, `status` and `promote`, and no verb that
creates a schedule; there is no `create_schedule` call anywhere in
`factory/`. The only roadmap that exists was made by hand with the
`temporal schedule` CLI. A repo that completes every other story in this
spec — scaffolded, registered, wired, passing `--check` — still has no
scheduler, and nothing tells the operator one was supposed to exist.

**Why this priority**: it is the difference between a joined repo and a
dispatchable one. The whole provisioning set ends with an operator flipping
a spec to `ready`; without this story that flip does nothing, forever, with
no error. It rides at P1 for the same reason the registry does — the repo
is not actually joined until this is true.

**Independent Test**: after init, a schedule exists on the control plane
whose identifier carries the repo's slug and whose arguments name that
repo's specs root, target repo and landing branch; flipping a spec to
`ready` produces a dispatch without any hand-run command; `ergane repo
forget` removes it.

**Evidence rule**: as US1 — the judge sees the diff and these criteria, so
the schedule's live behaviour is met by tool output pasted verbatim into a
comment block in the test file.

**Acceptance Scenarios**:

1. **Given** a repo being initialised, **When** init completes, **Then** a
   roadmap schedule exists whose identifier carries the repo's slug, and
   whose arguments carry that repo's specs root, target repo and landing
   branch — one shared control plane means the identifier must distinguish
   repos, exactly as workflow identifiers should and currently do not.
2. **Given** a manifest declaring a roadmap cadence and concurrency dials,
   **When** init completes, **Then** the live schedule carries those values,
   and changing them in the manifest and re-running init reconciles the live
   schedule to match — a dial reachable only by editing a base64-encoded
   workflow payload is not a dial an operator has.
3. **Given** an existing schedule for the slug, **When** init re-runs
   unchanged, **Then** it reports the schedule already-satisfied and changes
   nothing — same idempotence contract as every other act in this spec.
4. **Given** a registered repo with a schedule, **When** `ergane repo
   forget` runs, **Then** the schedule is deleted. A schedule that keeps
   firing at a repo the engine has forgotten dispatches work nobody is
   watching, against a specs root that may no longer exist.
5. **Given** a repo whose schedule is missing, paused, or pointed at a
   different specs root, **When** `ergane init --check` runs, **Then** a
   finding reports it and names the remedy — a joined repo with no
   scheduler must not read as ready.
6. **Given** a control plane that cannot be reached, **When** init runs,
   **Then** the scaffold and registry still complete and the schedule step
   reports as failed with the reason — the repo-local work must not be lost
   to an unreachable engine.

---

### Edge Cases

- Init run at a subdirectory of a repo: operate on the repo root (found via
  git), report the root being used.
- A schedule already exists under the slug's identifier and the engine did
  not create it: reported, reconciled only on the operator's confirmation —
  the same restraint every other collision in this set is given.
- The directory name yields an invalid slug (spaces, case, unicode):
  propose the normalized form; the operator confirms — declared, never
  silently rewritten.
- The repo already contains an `ergane.yaml` from a clone of another
  managed repo: the interview loads it as defaults and flags that the slug
  must differ if the original is still registered.
- Registry file corrupt or hand-edited into invalidity: every `repos`
  command refuses with the path named and offers `rebuild` — it is a cache;
  rebuilding it must always be the safe answer.
- Two inits racing on one registry: exclusive lock on the registry file,
  same contract as 033's config lock.
- A repo hosted somewhere without merge queues (no GitHub remote at all):
  scaffold and registration proceed; wiring refuses naming the constraint;
  `--check` reports the queue findings as failing with the same detail —
  the repo is registered but not dispatchable, and the findings say
  exactly that.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `ergane init` MUST operate on the git repository containing
  the working directory, refuse non-repositories naming `git init` as the
  prerequisite, and refuse factory-created worktrees naming the primary
  checkout. The path argument MUST be optional, defaulting to the working
  directory, so bare `ergane init` and `ergane init .` are the same
  invocation; the resolved repo root MUST be named in the output either way.
- **FR-002**: The scaffold MUST write exactly: `ergane.yaml` at the repo
  root, a `.gitignore` entry for `.ergane/`, the empty `.ergane/` runtime
  root, and (when accepted in US3) a CI workflow file. It MUST NOT commit,
  push, create branches or tags, or modify any other file. Its final output
  MUST name every file written.
- **FR-003**: Every manifest value MUST be operator-declared (D-009).
  Proposals inferred from the tree are permitted only as interview defaults
  the operator explicitly confirms; nothing is written silently.
- **FR-004**: The scaffold MUST validate each answer with the installed
  engine's manifest parser rules at entry time and MUST NOT write a
  manifest that parser would refuse. The schema version written is the
  newest the installed engine parses (the engine version, not the spec,
  decides — the 026 finding stands: the worker's installed parser is the
  parser that counts).
- **FR-005**: Re-running init on a scaffolded repo MUST load the existing
  manifest as defaults and edit rather than clobber; an unchanged interview
  MUST produce a byte-identical manifest.
- **FR-006**: The registry MUST live under the engine's XDG state home,
  never inside any repo; each entry carries slug, absolute repo path, and
  derived scopes (memory bank identity when the control plane declares a
  backend). The committed manifest is the sole authority on membership; the
  registry is a derived cache, and `ergane repo rebuild` MUST make
  re-deriving it safe at any time: verify every entry, prune dead ones,
  never touch live ones.
- **FR-007**: Slugs MUST be unique across the registry; a collision is
  refused naming the holder. The slug is the repo's namespace token — woven
  into workflow IDs and search attributes (one Temporal namespace, per the
  settled decision), ledger and findings dimensions, and memory-bank
  identity.
- **FR-008**: Registry mutations MUST hold an exclusive lock on the
  registry file, mirroring 033's config-lock contract.
- **FR-009**: Wiring MUST be idempotent and reported step by step: enable
  the merge queue on the declared landing branch, require one status check
  per declared gate named exactly after it, and offer a scaffolded workflow
  file whose job names equal the declared gate names, running the declared
  commands. Refusals (visibility per D-007, missing or unauthenticated
  `gh`) MUST name the constraint and the remedy at the point of refusal.
- **FR-010**: `ergane init --check` MUST gather facts and judge them
  through the existing pure `evaluate_repo` judgment, extended with
  init-created facts: gitignore coverage of `.ergane/`, registry presence
  and path agreement, landing-branch existence, and control-plane
  reachability (delegated to 033's probes as one summary finding). One
  finding per check, no masking, actionable detail, non-zero exit on any
  failure. A full `ergane init` run MUST end by executing this check.
- **FR-011**: `ergane repo list` MUST render every entry with its
  manifest status (valid, invalid, missing) rather than hiding drift;
  `ergane repo forget <slug>` MUST remove only the registry entry, with
  `--clean-runtime` additionally emptying `.ergane/` only after confirming
  no epic is running against the repo.
- **FR-012**: Per-repo runtime state (worktrees, verification evidence,
  transcripts) MUST live under the repo's own `.ergane/`, and fleet-level
  stores MUST NOT (033 FR-001's complement). Init MUST create that root and
  MUST NOT relocate existing data — migration of the current `.factory/`
  contents is the rename spec's scope.
- **FR-013**: `ergane repo forget --export <dir>` MUST write the engine's
  repo-scoped records — findings, usage, escalation history — to the named
  directory as one JSONL file per store plus a markdown digest, selected by
  the repo's slug, written outside `.ergane/`, containing no secret values,
  committing nothing. Export is strictly opt-in: forget without the flag
  writes no files. (Rides US5's priority; nothing else depends on it.)
- **FR-014**: `ergane init` MUST create or reconcile the repo's roadmap
  schedule on the control plane. The schedule's identifier MUST carry the
  repo's slug, and its arguments MUST carry that repo's specs root, target
  repo and landing branch. No repo may depend on a schedule created by hand.
- **FR-015**: The roadmap's cadence and its concurrency dials
  (`max_concurrent_epics`, `max_concurrent_nodes`) MUST be declared in the
  manifest and MUST be changeable by editing the manifest and re-running
  init. A dial reachable only by editing an encoded workflow payload does
  not count as declared.
- **FR-016**: `ergane repo forget` MUST delete the repo's schedule, and
  `--check` MUST render a finding when the schedule is absent, paused, or
  carrying arguments that disagree with the manifest.
- **FR-017**: An unreachable control plane MUST NOT lose the repo-local
  work: the scaffold and registry complete, and the schedule step reports
  as failed with its reason.

### Key Entities

- **RepoManifest**: the committed `ergane.yaml` — the authoritative fact of
  membership and the declarations (landing branch, gates, standards,
  runtime) the factory enforces.
- **RegistryEntry**: slug → absolute path + derived scopes; a pointer in a
  rebuildable cache under the engine's state home.
- **ReadinessFinding**: one check's judgment — the existing 003 grammar
  (check slug, passed, actionable detail), extended with init's checks.

## Success Criteria *(mandatory)*

- **SC-001**: On a fresh public GitHub repo, an operator (or an agent
  following the runbook) goes from `ergane init .` to an all-pass
  `ergane init --check` using only the commands and printed instructions —
  no consultation of source code.
- **SC-002**: After any init, `git log` is byte-identical to before, and
  `git status` shows only the scaffold's declared files — proven in the
  suite by comparing history and status before and after.
- **SC-003**: A second init run with unchanged answers is a no-op: manifest
  byte-identical, registry unchanged, wiring reports already-satisfied.
- **SC-004**: Each readiness precondition, broken one at a time, flips
  exactly its own finding with a detail naming the fix; the parity findings
  are produced by the same judgment the 003 dispatch path uses, verified by
  exercising both callers against one fixture set.
- **SC-005**: The registry survives its own destruction: delete it, run
  `ergane repo rebuild` seeded from the known repo paths (or re-init), and
  `ergane repo list` converges to the same entries — demonstrating the
  cache is derived, not authoritative.
- **SC-006**: A repo registered, forgotten, and re-registered under the
  same slug ends byte-identical in-tree across the cycle.
- **SC-007**: A repo taken through init end-to-end dispatches an epic from
  a spec flipped to `ready` with no hand-run command and no hand-created
  schedule — the whole provisioning set's closing claim, and the one that is
  false today.

## Assumptions

- The brand rename (`.ergane/`, `ergane.yaml`) lands before or with this
  epic; this spec never writes `factory`-branded paths.
- 033-ergane-install provides the control plane this spec's check probes;
  a host without a provisioned control plane can still scaffold (US1) but
  fails the control-plane finding in `--check`.
- 023 is orthogonal: the scaffold writes whatever manifest schema the
  installed engine parses (FR-004); when 023's `version: 2` is the
  installed schema, the interview grows its questions without changing
  this spec's contract.
- GitHub is the assumed hosting for wiring (US3); other hosts degrade to
  scaffold + registration with failing queue findings, honestly reported.

## Out of Scope

- Brownfield context — behavioral baseline, functionality inventory, spec
  reconstruction (workstream A, its own spec when Q1 names the first app).
- Control-plane provisioning (033).
- Migration of existing `.factory/` state and the rename itself (the
  rename spec).
- Dispatch, scheduling, and everything after readiness — init ends at
  proven membership.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-012]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-006, FR-007, FR-008, FR-011]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-009]
US4:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-010]
US6:
  depends_on: []
  depends_on_merged: [US4]
  implements: [FR-014, FR-015, FR-016, FR-017]
US5:
  depends_on: []
  depends_on_merged: [US6]
  implements: [FR-013]
```

US6 rides behind US4 rather than beside it because both extend the same
readiness finding set, and US5 rides behind US6 because `forget` must delete
the schedule US6 creates. The serial tail is deliberate: it costs merge
latency and buys the absence of two nodes editing one judgment.
