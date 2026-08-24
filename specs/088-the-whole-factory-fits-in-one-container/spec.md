---
state: ready
# DRAFTED 2026-08-22 ~11:30 PM CT on branch spec-routing-plan, tree 838b9c3.
# REVISED 2026-08-23 ~8:30 AM CT: compose as front door, FR on same-path mounts.
#
# REWRITTEN 2026-08-23 ~9:45 PM CT, same session, after the research pass that
# produced docs/container-onramp-research-findings.md — read it before this
# spec; it is the evidence base. What changed and why:
#
#   - **The security assumption is now a measurement.** The earlier draft said
#     "Docker's defaults block unprivileged user namespaces ... not yet
#     measured". It is measured. The assumed apparmor=unconfined +
#     seccomp=unconfined pair DOES NOT WORK (as container root, bwrap skips
#     userns and needs CAP_SYS_ADMIN; unconfined AppArmor triggers Ubuntu's
#     capability-stripping transition). What works, verified end to end on the
#     floor host: non-root engine + init + cap_drop ALL + no-new-privileges +
#     a narrow seccomp profile + the `ergane-engine` AppArmor profile, with
#     the sandbox child staying confined under it. US1 and US3 now name those
#     artifacts instead of gesturing at "security options".
#   - **State mounts changed from a named volume to same-path binds.** The
#     host CLI reads the engine's SQLite stores directly (twelve modules);
#     measured safe on Linux over a plain bind mount, and the supervision
#     home must be mounted too or a recreate silently discards Temporal
#     history (findings §3, failure mode 5).
#   - **Compose moved out.** The operator's directive puts ease first: the
#     developer-facing front door is `ergane install`, which GENERATES the
#     compose project (spec 104), exactly as it generates systemd units today.
#     This spec ships the image, the committed security artifacts, a reference
#     compose the drift tests pin, and the docs. Nobody hand-edits the
#     reference to run a floor; 104 exists so nobody has to.
#   - The operator ran the config-G verification personally (apparmor_parser
#     load + probe suite) on 2026-08-23. Findings doc, appendix, has the run.
#
# ANCHOR STATUS: every file:line citation was read individually off 838b9c3
# (2026-08-22, re-confirmed 2026-08-23). The commits above 838b9c3 touch only
# docs/ and specs/, so every anchor still resolves.
#
# WHAT THE DRAFTING PASSES SETTLED, so nobody re-derives it:
#   - **`ergane install` needs no systemd.** The interview and --verify live in
#     factory/cli/install.py; systemd units are a different verb
#     (factory/cli/nouns/worker.py:29-33 → factory/supervision/units.py:716).
#     The one coupling that bites: temporal.mode="managed" is refused without
#     a user bus (factory/cli/install.py:848-852) — the container declares
#     `external` and runs the server itself.
#   - **The gate's silent bwrap fallback is unreachable on a dispatch path** —
#     see "What this spec does not change".
#   - **The image build cannot be a gate.** An agent inside bwrap has no
#     docker socket; US3's criteria are drift tests over committed text.
#   - **bwrap must not be PID 1 and must not run as root** (findings §1,
#     failure modes 1 and 2). The supervisor is the entrypoint (so bwrap is
#     always a grandchild), the image's runtime user is non-root, and US1's
#     probe asserts both properties rather than assuming them.
#
# FLIPPED READY 2026-08-23 ~10:05 PM CT on the operator's instruction, after
# validate passed every layer at both states. US3 remains the story most
# likely to be under-specified into a second attempt: read its sizing note
# before dispatch.
---

# Feature Specification: the whole factory fits in one container

**Created**: 2026-08-22
**Evidence base**: `docs/container-onramp-research-findings.md` (2026-08-23)

## The gap, stated precisely

Ergane installs cleanly at system level — `uv tool install`, `ergane install`,
`ergane init` — but that path asks a developer to stand up a LiteLLM gateway, a
Temporal server, a memory backend, a telemetry sink and an escalation channel
before anything moves. The program in `docs/container-onramp-program.md` closes
that gap in stages; this spec is the stage everything else stands on: **the
engine container exists, supervises itself, sandboxes its agents with bwrap
under a verified narrow confinement, and proves what it can actually do before
it accepts work.**

The seam that makes the container configurable already exists and is typed:
`ControlPlaneConfig` (`factory/controlplane/config.py:109`) parses five
mode-discriminated blocks, each naming the environment variable holding its
credential, and `ergane install --verify` (`factory/cli/nouns/install.py:129-133`)
probes every one. What is missing is the container, one process that supervises
the factory's three long-lived children inside it, and one honest preflight —
because in a container, for the first time, `bwrap` being *installed* and
`bwrap` being *able to run* come apart.

**The preflight defect is real today, container or not.** `_inspect_host`
(`factory/controlplane/verify.py:253`) decides the sandbox is usable from
`shutil.which("bwrap")` alone (`:261`), reporting `"usable": bwrap_path is not
None` (`:281-282`). Inside a container that is false in several distinct ways,
each measured (findings §1): the default seccomp profile blocks the namespace
syscalls; as root, bwrap takes a code path that needs `CAP_SYS_ADMIN`; as
PID 1 it fails writing the uid map; and on some kernels the fresh `/proc`
mount is refused. `install --verify` reports green, and the first dispatch
dies inside `BwrapBackend.launch` (`factory/workgraph/adapter.py:622`) with an
error that names neither cause nor remedy. A preflight that cannot tell
"installed" from "works" is worth less in a container than nothing.

## The rule this spec is asking for

**The engine container proves what it can actually do before it accepts work,
says plainly what it deliberately cannot, and carries its sandbox confinement
as named, committed artifacts rather than as `unconfined` flags.**

### The ruling, made here rather than left to the implementer

- **One container.** Splitting the engine across services would require the
  target clone, `ERGANE_ROOT` and every node worktree mounted identically into
  several containers, because gates and agents run as subprocesses in the node
  worktree on the same filesystem as the worker (`factory/verify/gates.py:421`,
  `factory/workgraph/adapter.py:622`). That buys isolation nobody asked for
  and costs a mount contract that will drift.

- **Temporal runs inside the container, through code that already landed.**
  `factory/supervision/temporal_server.py:68` is a `main(argv)` that starts
  the SDK's dev server against a SQLite file and blocks — written for 042's
  systemd unit, equally a container child. `config.toml` declares
  `temporal.mode = "external"` at `127.0.0.1:7233`: `managed` is refused
  without a systemd user session (`factory/cli/install.py:848-852`), and a
  container has no user bus (`factory/cli/install.py:818-819` names containers
  in so many words).

- **The sandbox stays `bwrap`, under config G, and the confinement is a set of
  committed files.** `SUPPORTED_BACKENDS` is `("bwrap",)`
  (`factory/verify/factory_yaml.py:90`) and stays that way — inside one
  container the host backend would let concurrent nodes read each other's
  worktrees, the SQLite stores and each other's per-node `HOME`
  (`factory/workgraph/adapter.py:742-750`). The confinement that lets bwrap
  run is not a pair of `unconfined` flags — measured: that pair does not even
  work — but two committed artifacts this spec ships:
  `container/seccomp-ergane.json` (moby's default profile plus exactly
  `unshare, clone, clone3, mount, umount2, pivot_root, setns` allowed
  unconditionally, with the `clone3`-ERRNO rule removed) and
  `container/ergane-engine.profile` (docker-default's template with `userns,`
  `mount,` `pivot_root,` allowed and every deny retained). The container runs
  as a non-root uid with `cap_drop: ALL`, `no-new-privileges`, and an init
  process as PID 1. All verified on the floor host 2026-08-23; findings §1
  and its appendix hold the full matrix and the artifact text.

- **The engine runs as the operator's uid:gid, and `HOME` is set by the
  entrypoint.** Non-root is what puts bwrap on its unprivileged-userns code
  path (as root it takes a `clone(CLONE_NEWNS)` that needs `CAP_SYS_ADMIN`),
  and the same choice makes every state file host-owned across the bind
  mounts. The image must tolerate an arbitrary uid with no passwd entry.

- **Source repositories, the state root and the supervision home are mounted
  at the same absolute path inside and outside, and the container enforces the
  repo rule rather than asking.** Git records absolute paths in
  `.git/worktrees/<name>/gitdir` and each worktree's `.git` file, and
  `BwrapBackend._build_argv` binds the worktree at its own path
  (`factory/workgraph/adapter.py:477-478`). The supervision home matters for a
  subtler reason: the managed Temporal server's SQLite history lives there,
  **outside** the state root, and a recreate that mounts only the state root
  silently discards all workflow history. The supervisor reads the repo
  registry at startup and refuses when a registered repo is not at its own
  recorded path (FR-009). A rule the container checks is worth more than a
  rule the documentation states.

- **The compose project a developer runs is generated by `ergane install`
  (spec 104), not hand-edited.** This spec commits the `Dockerfile`, the two
  security artifacts, and `container/compose.reference.yaml` — the reference
  the drift tests pin and the docs quote, and the source of truth 104's
  generator derives from. `docs/container.md` says plainly that the reference
  is a reference: the operational project is `ergane install`'s output.

## What this spec does not change

- **The five-subsystem config surface.** `ControlPlaneConfig` gains no field.
- **`ergane install` and `ergane init`.** Neither changes here; 104 grows the
  container backend, 103 grows the persona proposal. This spec is the engine
  they bring up.
- **The gate executor's bwrap fallback.** `_resolve_gate_executor`
  (`factory/verify/gates.py:1241`) returns `SubprocessGateExecutor` when the
  manifest declares `runtime: bwrap` and the binary is not a file
  (`:1254-1256`) — unreachable on a dispatch path, because the adapter refuses
  first (`factory/workgraph/adapter.py:623-628`); deliberate in local/test
  paths per the comment at `:1249-1250`. Left alone, recorded so the next
  reader does not "fix" it.
- **`SUPPORTED_BACKENDS`.** No `runtime: container` value.
- **Spec 082's versioned worker deploy.** systemd instances have no container
  equivalent here; in a container the recreate is the deploy, which is why
  spec 099's restart-safety matters more on this path, not less. US4 makes the
  verbs say so; 105 gives the container path its own upgrade verb.

## User Scenarios & Testing

### User Story 1 - The preflight proves the sandbox runs (Priority: P1)

As an operator standing up a container, I want `ergane install --verify` to
tell me the sandbox cannot execute *before* I dispatch anything, so a blocked
user namespace reaches me as a named remedy instead of as a dead attempt.

**Why this priority**: P1 and first. Every other story is worth less if the
container can report itself green and then fail opaquely. It is also a real
defect on its own terms, container or not — and the measured failure modes
(root path, PID-1 path, kernel-dependent `/proc` mount) mean a naive probe
passes where dispatch fails.

**Independent Test**: with the exec seam stubbed to fail, the probe reports
bwrap unusable with a reason; with it stubbed to succeed, usable.

**Acceptance Scenarios**:

1. **Given** a host where `/usr/bin/bwrap` exists but cannot execute, **When**
   the host probe runs, **Then** it reports bwrap `present: true`,
   `usable: false`, and a remedy naming unprivileged user namespaces and the
   committed confinement artifacts (`container/seccomp-ergane.json`,
   `container/ergane-engine.profile`) — proven by a committed test.
2. **Given** a host with no bwrap at all, **When** the probe runs, **Then** the
   remedy is the install-bubblewrap one, textually distinct from scenario 1's —
   proven by a committed test asserting the two differ.
3. **Given** a host where bwrap executes, **When** the probe runs, **Then**
   `usable: true` — proven by a committed test that runs the real binary when
   present and skips by guard, never by marker, when it is not.
4. **Given** the probe's assembled bwrap invocation, **When** it is inspected,
   **Then** it exercises the production mount shape — a fresh `--proc`, a
   `--dev`, a tmpfs, a read-only `/usr` bind — and executes the pinned
   `/usr/bin/bwrap` path, because a minimal `--ro-bind / / true` passes on
   kernels where the production `--proc` mount is refused (findings §1,
   failure mode 14) — proven by a committed test over the argv.

### User Story 2 - One process supervises the factory inside the container (Priority: P1)

As the container's entrypoint, I start the Temporal server, the worker and the
notify bridge in a defensible order, forward signals to all of them, and die
loudly naming whichever child died first — so bringing the engine up is a
floor that works and stopping it is a clean stop.

**Why this priority**: P1. This is the entrypoint; without it there is no
container. It is Python, so it is the part of the image the factory can prove.
It is also what guarantees bwrap is never PID 1: agents are grandchildren of a
supervisor that is itself a child of the container's init.

**Independent Test**: drive the supervisor against stub children and assert
startup order, the readiness wait, the exit code and name on a child death,
the signal fan-out, and the same-path mount refusal.

**Acceptance Scenarios**:

1. **Given** the supervisor with stub children, **When** it starts, **Then**
   the Temporal server starts first and the worker is not started until the
   configured address answers — proven by a committed test.
2. **Given** Temporal that never answers, **When** the bounded readiness wait
   expires, **Then** the supervisor exits nonzero with a message naming the
   address it waited on and the timeout it used — never a silent hang.
3. **Given** all three children running, **When** one exits, **Then** the
   supervisor stops the others and exits nonzero naming the child that died
   first — proven by a committed test.
4. **Given** all three children running, **When** the supervisor receives
   SIGTERM, **Then** every child is signalled, given the declared grace
   period, and SIGKILLed only after it — proven by a committed test.
5. **Given** the assembled child command lines, **When** they are inspected,
   **Then** none contains the substring `python -` — proven by a committed
   test, for the reason recorded at
   `factory/supervision/temporal_server.py:9-12`.
6. **Given** a repo registry naming a repo at a path that is not a directory
   inside the container, **When** the supervisor starts, **Then** it exits
   nonzero before starting any child, naming the repo's slug and the path that
   is missing — the same-path mount rule, checked rather than documented.
7. **Given** an empty registry — a container that has not run `ergane init`
   yet — **When** the supervisor starts, **Then** it starts normally. A fresh
   container has nothing to mount and that is not an error.

### User Story 3 - The image and its committed artifacts exist and cannot drift (Priority: P2)

As the program's packaging story, the repository carries the `Dockerfile`, the
two confinement artifacts and the reference compose — and none of them can
silently stop shipping something the preflight, the sandbox or the verified
configuration requires.

**Why this priority**: P2 and merge-dependent on US1 and US2 — it packages
them. Its criteria are diff-provable by construction: the agent authoring it
cannot build the image it writes (no docker socket inside bwrap).

**Independent Test**: tests parse the committed artifacts and fail when a
required element is removed.

**Acceptance Scenarios**:

1. **Given** the committed Dockerfile, **When** the drift test reads it,
   **Then** every binary `_inspect_host` probes for — bwrap, git, gh — plus
   the four `BwrapBackend._toolchain` resolves
   (`factory/workgraph/adapter.py:399`, `DEFAULT_EXECUTABLE` at `:97`) is
   installed by it, bwrap lands at `/usr/bin/bwrap` (the path both consumers
   pin), the entrypoint is US2's supervisor, and the test fails when any one
   is removed — proven red and green in the diff.
2. **Given** `container/seccomp-ergane.json`, **When** its drift test reads
   it, **Then** it parses as a seccomp profile whose unconditional allow list
   contains exactly `unshare, clone, clone3, mount, umount2, pivot_root,
   setns` beyond the vendored moby baseline, and contains no rule returning
   ERRNO for `clone3` — proven by a committed test.
3. **Given** `container/ergane-engine.profile`, **When** its drift test reads
   it, **Then** the profile text contains the `userns,` `mount,` and
   `pivot_root,` allows, retains the `deny` lines for `/proc` and `/sys`
   write paths that docker-default carries, and contains no `flags=(unconfined)`
   — proven by a committed test.
4. **Given** `container/compose.reference.yaml`, **When** its drift test reads
   it, **Then** it declares exactly one service; `init: true`; a non-root
   `user`; `cap_drop: [ALL]`; `security_opt` entries for `no-new-privileges`,
   the seccomp artifact by path and `apparmor=ergane-engine`; same-path bind
   mounts for the state root and the supervision home; environment passthrough
   for every variable the five subsystem blocks name; and a source-mount list
   shaped for one entry per registered repo, each same-path — with **no
   `unconfined` token anywhere in the file** — proven by a committed test.
5. **Given** `docs/container.md`, **When** it is read, **Then** it states:
   the same-path mount rule and that the supervisor enforces it; that the
   supervision home must be mounted or Temporal history dies with the
   container; the confinement artifacts and what each is for, with config F
   named as the documented fallback; the subscription-credential trade-off;
   the `FROM ergane:X.Y.Z` extension pattern for target toolchains; the verbs
   the container does not support; and that the reference compose is a
   reference — `ergane install` (spec 104) generates the operational project.

### User Story 4 - The systemd verbs refuse by name in a container (Priority: P3)

As a developer who typed `ergane worker install` inside the container because
the docs elsewhere mention it, I get a sentence telling me the container
supervises its own worker — not a D-Bus error.

**Why this priority**: P3, independent, droppable without harming the others.

**Acceptance Scenarios**:

1. **Given** no systemd user session, **When** `ergane worker install`,
   `deploy` or `migrate` runs, **Then** each exits nonzero with a message
   naming the missing user session, the container as its likely cause, and
   the container supervisor as what replaces the verb — proven by a committed
   test over all three verbs.
2. **Given** a host *with* a systemd user session, **When** the same verbs
   run, **Then** their behaviour is unchanged — proven by their existing
   tests passing unmodified.

## Requirements

### Functional Requirements

- **FR-001**: `_inspect_host`'s bwrap entry MUST derive `usable` from an
  actual execution of the pinned `/usr/bin/bwrap` under a bounded timeout,
  not from `shutil.which` alone, and MUST keep `present` derived from
  discovery so the two can differ.
- **FR-002**: The probe's bwrap invocation MUST exercise the production mount
  shape — fresh `--proc`, `--dev`, a tmpfs, read-only `/usr` — because the
  minimal invocation passes on kernels where the production one is refused.
- **FR-003**: A present-but-unrunnable bwrap MUST carry a remedy distinct from
  the absent one, naming unprivileged user namespaces and the committed
  confinement artifacts by path.
- **FR-004**: The execution the probe performs MUST be injectable so both
  branches are testable on any host, and the real-binary test MUST skip by
  guard rather than by marker.
- **FR-005**: A new module MUST supervise exactly three children — the
  Temporal dev server (`factory.supervision.temporal_server`), the worker
  (`factory.worker`) and the notify bridge (`factory.notify.service`) — with
  the set declared in one place.
- **FR-006**: The supervisor MUST wait, under a bounded and declared timeout,
  for the Temporal address to answer before starting the worker, and MUST
  exit nonzero naming the address and the timeout when it does not.
- **FR-007**: When any child exits, the supervisor MUST stop the remaining
  children and exit nonzero naming the child that exited first and its status.
- **FR-008**: On SIGTERM or SIGINT the supervisor MUST signal every child,
  wait a declared grace period, and SIGKILL only what remains.
- **FR-009**: Before starting any child, the supervisor MUST read the repo
  registry and verify every registered repo is a directory at its own
  recorded path, exiting nonzero naming each slug and missing path when one
  is not; an empty or absent registry MUST NOT be an error. No child command
  line may contain the substring `python -`.
- **FR-010**: A `Dockerfile` MUST exist that installs bubblewrap (at
  `/usr/bin/bwrap`), git, the GitHub CLI, uv, node, python **and the agent
  runner named by `DEFAULT_EXECUTABLE`
  (`factory/workgraph/adapter.py:97`)**, installs the `ergane-cli`
  distribution, runs as a non-root user, and sets the US2 supervisor as its
  entrypoint.
- **FR-011**: `container/seccomp-ergane.json` and
  `container/ergane-engine.profile` MUST be committed with the exact content
  shape the findings appendix records (vendored moby baseline + the seven
  syscalls; docker-default template + userns/mount/pivot_root with every deny
  retained), each carrying a comment naming its upstream base and version.
- **FR-012**: `container/compose.reference.yaml` MUST be committed declaring
  exactly one service with `init: true`, a non-root `user`,
  `cap_drop: [ALL]`, `no-new-privileges`, the seccomp artifact and the
  `ergane-engine` profile by name, same-path bind mounts for the state root
  and the supervision home, environment passthrough for the five subsystem
  blocks' variables, and a per-repo same-path source-mount list — and MUST
  contain no `unconfined` token.
- **FR-013**: Committed drift tests MUST parse each artifact of FR-010..012
  and fail when a required element is removed, deriving required binary names
  from the probe and the sandbox toolchain resolution rather than restating
  them.
- **FR-014**: `docs/container.md` MUST state everything US3 scenario 5 lists.
- **FR-015**: `ergane worker install`, `deploy` and `migrate` MUST refuse by
  name when no systemd user session is available, naming the container as the
  likely cause and the supervisor as the replacement, and MUST behave
  unchanged where a session exists.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: []
  implements: [FR-005, FR-006, FR-007, FR-008, FR-009]
US3:
  depends_on: []
  depends_on_merged: [US1, US2]
  implements: [FR-010, FR-011, FR-012, FR-013, FR-014]
US4:
  depends_on: []
  implements: [FR-015]
```

US1 and US2 touch disjoint files — `factory/controlplane/verify.py` and a new
module under `factory/supervision/` — and run in parallel. US3 packages both
and needs them **merged**: its drift tests read the binary list US1's probe
requires and the entrypoint names US2's module. US4 is independent and
droppable.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Paste the probe's three branches in one run — absent, present
  but unrunnable, runnable — with the two remedies visibly different, and the
  probe argv showing the production mount shape.
- **SC-002**: Paste the supervisor's test run showing the readiness wait, the
  timeout refusal naming address and timeout, the child-death exit naming the
  child, the SIGTERM fan-out, and both same-path branches.
- **SC-003**: Paste each drift test red against its artifact with one required
  element removed and green against the committed one — both runs in the
  diff, for the Dockerfile, both confinement artifacts, and the reference
  compose.
- **SC-004**: Paste all three `worker` verbs refusing under a stubbed absent
  session, and the existing `worker` tests passing unmodified.

## Assumptions

- **The confinement configuration is measured, not assumed.** Verified on the
  floor host (Ubuntu 24.04.4, kernel 6.17, Docker 29.2.1, arm64) 2026-08-23:
  the full matrix, the artifact text and the failure modes are in
  `docs/container-onramp-research-findings.md`. Two cheap confirmations
  remain open — an x86_64 run and a stock-noble run — tracked in the program
  document; neither blocks this spec.
- **The temporalio SDK downloads the dev-server binary on first use and
  caches it** (`factory/supervision/temporal_server.py:3-5`). Whether that
  cache can be baked into an image layer is unverified; if not, the first
  bring-up needs network egress. The implementer measures it and
  `docs/container.md` records whichever is true.
- **The Claude subscription credential must be mounted read-write.**
  `discover_subscription_credential` (`factory/workgraph/adapter.py:767`)
  searches the operator's home and `_seed_node_home` (`:803`) copies the file
  into each per-node `HOME` (`:834`). The adapter already records the risk
  that a node's refresh may invalidate the operator's login (`:817-820`); the
  container makes that mount explicit. Documented, not changed.
- **`gh` authentication arrives as an environment variable or a mounted
  config** (`factory/controlplane/verify.py:250`, `:266-275`;
  `factory/mergequeue/gh.py:537`, `:698`). Unchanged contract; passthrough.
