---
state: draft
# Drafted 2026-08-11 from an operator planning conversation (the brownfield
# onboarding / provisioning session). Decisions this spec assumes, made in that
# session: the brand rename (`.ergane/` runtime root, `ergane.yaml` manifest —
# now 040-manifest-rename, ordered before this); ONE Temporal namespace with
# the repo slug in workflow IDs; adapter-side token counting with OTEL export
# (which is 024's scope — this spec only provides the configuration surface it
# reads). Companion future-state runbook exists as an operator artifact; this
# spec is the durable form.
#
# SPLIT 2026-08-13. As drafted this spec carried seven stories across three
# unrelated domains — a config parser, a Temporal workflow type, and systemd
# unit management — sixteen FRs, and a live-tier criterion requiring a killed
# Temporal server. That is not one epic; it is three, and 032 is standing
# evidence of what an oversized story costs (killed at attempt four, 128M
# tokens, because the work could not be satisfied in one diff). The split,
# ordered by dependency and by ascending risk:
#
#   033 (this)  US1 parser, US2 verify, US3 walkthrough      — the config plane
#   041         EscalationWorkflow + messenger adapters      — was US5, US6
#   042         managed Temporal + worker units + alerts     — was US4, US7
#
# FR numbers are deliberately NOT renumbered: 034 FR-012 cites "033 FR-001",
# and stable numbers are worth more than a gapless list. FR-008, FR-012 and
# FR-016 moved to 042; FR-009, FR-010, FR-011 and FR-015 moved to 041. The
# gaps are the record of the split.
#
# Numbered 033: 025–031 are findings-promoted scaffolds, 032 was claimed by
# replay-determinism (48aa133) in a concurrent operator session, and 011–014
# stay reserved for audit-triage epics. This spec was briefly 032 before that
# collision surfaced; no other session ever saw it under the old number.
depends_on_landed: [008-operator-channel, 015-factory-doctor, 019-operator-cli, 040-manifest-rename]
---

# Feature Specification: Ergane Install — the control plane's config

**Feature Branch**: `033-ergane-install`

**Created**: 2026-08-11

**Status**: Draft (split 2026-08-13)

**Input**: Operator direction: "ergane install walks the user through
provisioning the background services required — LLM connectivity (gateway or
direct providers), memory backend (Hindsight default, BYOM seam), Temporal
(point at an existing instance incl. Temporal Cloud, or install a recommended
way), telemetry (tokenomics over OTEL), and escalation messaging (Telegram
today, with a bring-your-own-messenger seam like hermes/openclaw)."

**The principle.** Today the control plane exists as habits: a proxy at a
known port, a dev server in tmux, two Telegram env vars, and a shell script
that exports what the commands need. `ergane install` converts those habits
into a *declared, typed, proven* configuration — once per host, before any
repo is registered. Declared: one config file says what the factory connects
to, in which mode. Typed: the file parses to a schema that refuses violations
by name, in the same grammar the manifest established. Proven: install ends
by probing every declared subsystem and rendering findings, because a green
setup that never ran the thing is not a setup — the 015 doctor shipped a
command that could not start under exactly that illusion.

**What this epic is, after the split.** Declare, prove, interview. It builds
the file, the probes, and the walkthrough. It builds no workflow, installs no
systemd unit, and writes no adapter. Two things it *describes* are built
elsewhere and are named here only so the config can declare them: the
escalation transport (041) and managed-mode Temporal (042). Declaring a
subsystem this epic cannot yet prove is not a gap — it is the ordering, and
FR-006's skipped-and-deferred findings say so out loud rather than pretending.

**The five subsystems.** Each is declared in one of two modes — *external*
(bring your own: point at what you already run) or *managed* (ergane installs
and supervises it a recommended way):

1. **LLM connectivity** — `gateway` mode (a LiteLLM-shaped proxy: base URL +
   master-key reference) or `direct` mode (per-persona OpenAI-compatible
   endpoints). The adapter-side token counting that makes `direct` mode
   attribution-complete is 024's scope; this spec provides the configuration
   surface both modes share.
2. **Memory** — `hindsight` (URL; banks are path-scoped and recorded per repo
   at init time), `none`, or a named adapter. The factory calls zero memory
   operations today, so this spec *records the choice* and probes
   reachability; the ingest/recall contract is deliberately deferred to the
   first consumer (the brownfield inventory pipeline).
3. **Orchestration** — `external` Temporal (address + namespace + TLS/API-key
   reference; Temporal Cloud works) or `managed`. Exactly one namespace,
   always: the design never needs more, because repo identity lives in
   workflow IDs. **This epic parses and probes both modes; 042 is what makes
   `managed` install anything.** A host declaring `managed` before 042 lands
   is refused at parse time with 042 named — a mode that cannot act is worse
   than a mode that does not exist.
4. **Telemetry** — an OTLP endpoint, or none. Token metrics and workflow
   events export there with epic/node/attempt/persona/repo dimensions. The
   ledger remains the evidence store; attestation must never depend on a
   metrics backend being reachable.
5. **Escalation messaging** — the operator channel's transport. `telegram` is
   the reference; the adapter seam that admits others is 041. This epic
   declares the block — adapter name, authorized responders — and probes
   delivery through whatever transport exists at the time.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The control plane has a typed, refusing config (Priority: P1)

As an operator, I have one file — `~/.config/ergane/config.toml` (XDG paths
respected) — that declares all five subsystems, each in its mode, with every
secret referenced by environment-variable name and never by value. A config
that declares anything badly is refused with the exact rule named, before
anything connects.

This story is the parser and only the parser, deliberately mirroring 002's
manifest discipline: a `version: 1` config parses to a typed
`ControlPlaneConfig`; every violation — unknown subsystem, unknown mode, a
key that looks like a secret value rather than a reference, a Temporal block
naming two namespaces, an adapter name nothing registered — raises a config
error with a stable rule slug, the offending value `repr`-rendered, and the
source file named.

**Why this priority**: every other story consumes the parsed shape. Nothing
downstream exists until the file can say it.

**Independent Test**: a config exercising every subsystem and both modes
parses to the typed shape; each violation class raises its own named rule; a
config file is rejected if any secret-bearing field contains a literal that
is not an env-var reference.

**Evidence rule for every scenario below**: the judge is given the diff and
these criteria — never a terminal, never the base tree (constitution VIII).
Runtime claims are met by tool output pasted verbatim into a comment block in
the test file.

**Acceptance Scenarios**:

1. **Given** a `version: 1` config declaring `llm.mode = "direct"` with one
   persona block, `memory.backend = "hindsight"`, `temporal.mode =
   "external"` with address and namespace, an OTLP endpoint, and
   `escalation.adapter = "telegram"`, **When** it is parsed, **Then** the
   returned config carries exactly those choices typed, with every
   undeclared optional at its documented default.
2. **Given** a config whose `[temporal]` block declares a list of
   namespaces, **When** it is parsed, **Then** it is refused with a named
   rule stating the one-namespace design and why (repo identity lives in
   workflow IDs).
3. **Given** a config in which `api_key_env` (any subsystem) contains a
   value matching a known secret shape (e.g. begins `sk-`, contains a bot
   token's `:` grammar) rather than an env-var name, **When** it is parsed,
   **Then** it is refused naming the field — the config file never carries a
   credential, only the name of one.
4. **Given** a config declaring `escalation.adapter = "signal"` when no such
   adapter is registered, **When** it is parsed, **Then** it is refused
   naming the unknown adapter and listing the registered ones.
5. **Given** no config file at all, **When** any command that needs the
   control plane runs, **Then** it fails closed with a message naming
   `ergane install` as the remedy — never a half-configured default.
6. **Given** a config declaring `temporal.mode = "managed"`, **When** it is
   parsed, **Then** it is refused naming 042 as the epic that implements the
   mode — a declared mode that installs nothing would be discovered as an
   absent server, hours later, by a dispatch that had no reason to doubt it.

---

### User Story 2 - Install proves every connection (Priority: P1)

As an operator, `ergane install --verify` probes each declared subsystem —
completes a round trip against the LLM endpoint, pings Temporal and confirms
the namespace exists, resolves and exports a test datapoint to the OTLP
endpoint, reaches the memory backend, and delivers a test message through the
configured escalation transport — and renders one finding per check in the
doctor's findings grammar: check slug, passed, actionable detail. Exit code is
non-zero if any finding fails.

**Scope note, from the split**: the escalation probe here proves *delivery*
against the transport that exists when this epic runs — 008's Telegram
sender. The lifecycle half — deliver a test escalation and watch the
factory's own timer expire it — belongs to 041, which owns the workflow and
re-routes this probe through the adapter. Do not build an adapter seam here.
Build the probe against what exists, behind the same gather/judgment split as
the other four, so 041 changes one gather and no judgment.

**Why this priority**: proving is the point of the spec. The 015 lesson is
structural: the seam that makes judgment testable against scripted snapshots
is the seam that hides a gather that cannot run. Each probe here therefore
splits gather from judgment *and* the story's own gate must execute every
gather at least once against a live double (a loopback OTLP listener, a
local Temporal dev server, a stub HTTP endpoint) — no probe ships with its
gather path unexecuted.

**Independent Test**: against a fully-provisioned test double set, `--verify`
renders all-pass findings and exits 0; kill any one double and only that
subsystem's finding flips to fail with a detail an operator can act on; a
probe pointed at `127.0.0.1:1` fails closed within its timeout, never hangs.

**Evidence rule for every scenario below**: as US1 — runtime claims are met by
verbatim pasted output committed in the diff.

**Acceptance Scenarios**:

1. **Given** all five subsystems reachable, **When** `ergane install
   --verify` runs, **Then** every finding passes, each names what it
   actually did (not "ok" — "completed a 1-token completion against
   persona `implementer`"), and the exit code is 0.
2. **Given** Temporal reachable but the declared namespace absent, **When**
   verify runs, **Then** the temporal finding fails naming the namespace and
   the command that would create it, while the other four findings still
   render — one failure never masks the rest.
3. **Given** an escalation transport configured, **When** verify runs,
   **Then** a test message is delivered through it and the finding names the
   transport and what was delivered; the finding also records that lifecycle
   verification arrives with 041, so the operator reads a deferral rather
   than a pass that covered less than it appeared to.
4. **Given** any probe whose target does not answer, **When** verify runs,
   **Then** that probe fails within its declared timeout with the timeout
   named — hanging is a defect, not patience.
5. **Given** a subsystem declared `none` (memory or telemetry), **When**
   verify runs, **Then** that subsystem renders an explicit
   skipped-by-declaration finding — the operator sees the absence was
   chosen, not missed.

---

### User Story 3 - The walkthrough writes what the parser accepts (Priority: P2)

As an operator on a fresh host, `ergane install` interviews me subsystem by
subsystem — mode first, then only the fields that mode needs — writes the
config file, and immediately runs the US2 verification, so the last thing
install prints is proof, not hope. Re-running install on a configured host
loads the existing file as defaults and edits rather than clobbers.

**Why this priority**: the walkthrough is ergonomics over US1+US2; it must
never be the only way to produce the file (a hand-written config is equally
valid — the parser is the contract, the interview is a convenience).

**Independent Test**: a scripted interview session on a blank host produces a
config that parses (US1) and verifies (US2) with no manual edits; re-running
with one changed answer changes exactly that field.

**Evidence rule for every scenario below**: as US1.

**Acceptance Scenarios**:

1. **Given** a blank host, **When** the operator completes the interview,
   **Then** the resulting file parses under US1's parser and the automatic
   verify runs, and its findings are the command's final output.
2. **Given** an existing config, **When** install is re-run and the operator
   changes only the OTLP endpoint, **Then** the diff of the config file
   touches exactly the `[telemetry]` block.
3. **Given** an interview answer that would produce a refused config (a
   plaintext secret pasted where a reference belongs), **When** it is
   entered, **Then** the walkthrough refuses at entry time with the same
   named rule the parser would use — the interview never writes what the
   parser would reject.
4. **Given** two `ergane install` processes racing, **When** both reach the
   write, **Then** one holds an exclusive lock on the config path for the
   duration and the other waits or is refused — last-write-wins is
   unacceptable for an interview that ends in verification.

---

### Edge Cases

- Config file present but unreadable (permissions): fail closed naming the
  path and the permission, never fall back to defaults.
- Managed mode requested before 042 lands: refused at parse and at
  walkthrough time with the constraint named (US1-S6).
- A probe's subsystem is declared but its client library is absent: the
  finding fails naming the missing dependency, not an import traceback.

## Requirements *(mandatory)*

FR-008, FR-012 and FR-016 moved to 042; FR-009, FR-010, FR-011 and FR-015
moved to 041. The gaps are deliberate — see the frontmatter.

### Functional Requirements

- **FR-001**: Control-plane configuration MUST live in one file under the
  XDG config home (`~/.config/ergane/config.toml` by default), and mutable
  engine state (registry index, fleet databases) under the XDG state home
  (`~/.local/state/ergane/`); no control-plane state may live inside any
  managed repo's checkout.
- **FR-002**: The config MUST carry `version: 1` and parse to a typed shape
  whose violations are refused with stable named rules in the established
  `CONFIG_ERROR` grammar: rule slug, offending value `repr`-rendered, source
  file named. Unknown keys, subsystems, modes, and adapter names are
  refusals, never warnings.
- **FR-003**: Every secret-bearing field MUST be a reference (an env-var
  name, optionally resolved from a sops-encrypted file the operator
  decrypts into the environment); the parser MUST refuse values matching
  known credential shapes, and no code path may write a secret value into
  the config file or any log.
- **FR-004**: The five subsystems — `llm`, `memory`, `temporal`,
  `telemetry`, `escalation` — MUST each declare a mode/backend from a
  closed set: llm `gateway|direct`, memory `hindsight|none|<registered
  adapter>`, temporal `external|managed`, telemetry OTLP endpoint or
  `none`, escalation `<registered adapter>`. `temporal.mode = "managed"`
  MUST be refused until 042 lands, naming that epic.
- **FR-005**: The `temporal` block MUST accept exactly one namespace.
- **FR-006**: `ergane install --verify` MUST probe every declared subsystem
  with a gather/judgment split (015's pattern), render one finding per check
  in the doctor's findings grammar, bound every probe by an explicit
  timeout, let no failure mask another finding, and exit non-zero on any
  failure. Subsystems declared `none` MUST render skipped-by-declaration
  findings, and any check whose full proof is deferred to a later epic MUST
  say so in its detail rather than passing silently.
- **FR-007**: The interactive walkthrough MUST validate each answer with the
  same rules as the parser (refuse at entry, never write-then-fail), MUST
  load an existing config as defaults on re-run, MUST hold an exclusive
  lock on the config path while running, and MUST end by executing FR-006's
  verification.
- **FR-013**: Absence of a config file MUST fail closed in every command
  that needs the control plane, naming `ergane install` as the remedy.
- **FR-014**: The LLM block in `direct` mode MUST accept per-persona
  OpenAI-compatible endpoints (base URL, model, key reference) compatible
  with the existing `personas.yaml` registry semantics; in `gateway` mode it
  MUST accept a base URL plus master-key reference. This spec does not move
  token accounting — 024 owns that — but the config surface MUST be
  sufficient for both accounting designs to read.

### Key Entities

- **ControlPlaneConfig**: the parsed, typed form of `config.toml` — five
  subsystem blocks, each mode-discriminated; the only object the rest of
  the factory consults about the control plane.
- **SubsystemProbe**: one verification check — a thin gather returning a
  snapshot, a pure judgment over it, an explicit timeout; renders to a
  Finding.

## Success Criteria *(mandatory)*

- **SC-001**: On a fresh host with only `uv` and the four externally-provided
  subsystem endpoints available, an operator (or an agent following the
  runbook) reaches an all-green `ergane install --verify` using only `ergane`
  commands and their printed instructions — no consultation of source code.
- **SC-002**: Grepping the produced config file and the install/verify logs
  for every credential used in the session finds zero occurrences.
- **SC-006**: Every probe's gather path executes at least once in the suite
  against a live double; no probe's gather is covered only by scripted
  snapshots (the 015 regression, made a criterion).

## Assumptions

- 040-manifest-rename lands before this epic; this spec writes
  `ergane`-branded paths and verbs throughout and does not maintain
  `factory`-branded aliases.
- One host runs the control plane; multi-host is out of scope.
- The memory ingest/recall contract is deliberately NOT specified here; it
  arrives with its first consumer. This spec only records the backend
  choice and probes reachability.

## Out of Scope

- The EscalationWorkflow type and the messenger adapter seam (041).
- Managed-mode Temporal, systemd units of any kind, supervision probes, and
  the out-of-band alert path (042).
- `ergane init` and everything repo-scoped (034).
- The adapter-side token counting and OTEL emission mechanics (024's
  scope; this spec provides the config surface).
- Migration tooling from the current env-var/script setup; the operator
  runs the walkthrough once by hand.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-013, FR-014]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-006]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-007]
```
