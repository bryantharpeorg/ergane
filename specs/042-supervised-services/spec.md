---
state: landed
# Attested landed 2026-08-17. US1 b931f0cf3300 (#141), US2 df71bf78743f (#149),
# US3 b6233eec65b2 (#183), US4 4426faa48330 (#157) — all four observed on
# ergane-buildout by content.
#
# US3 is the epic's exception and worth reading before trusting its record. It
# burned four attempts: attempt 1 built the whole slice and opened #183, whose
# CI then went red on one of the story's OWN new tests; attempts 2 and 3 died
# instantly on Ollama 429s (quota exhaustion, zero signal about the code); the
# operator answered the resulting escalation and attempt 4 ran clean but, unable
# to reproduce the failure inside its sandbox, declared it flaky and committed
# nothing. The failure was not flaky. `_systemd_user_session_available()` shells
# out to `systemctl --user`, which fails in the bwrap gate (no user bus) and
# succeeds on a CI runner, so the refusal test inverted with the environment —
# green in the gate, red in CI, forever. An operator session reproduced the CI
# failure locally, patched the TEST ONLY (monkeypatch the probe to False; no
# production code touched), and pushed 0f6fe59 to the node branch; CI went green
# and the merge queue landed it normally. This is the first story in the tree
# with an operator-authored commit inside it — see the fail-out escape hatch,
# still unspecified as of this attestation.
# Split out of 033-ergane-install on 2026-08-13. 033 as drafted carried seven
# stories across three unrelated domains; this spec is the third — supervision
# and systemd. Was 033's US4 and US7; its FR-004..FR-011 were 033's FR-008,
# FR-012 and FR-016, expanded.
#
# THE PRIOR ART IS THE DESIGN INPUT, AND IT IS NOT IN THIS REPOSITORY. Five
# units and a probe script are running on the operator's host right now,
# hand-written on 2026-08-12 and living in a different repo entirely
# (/home/admin/code/homelab/infra/ergane-supervision/). They encode lessons
# bought with a host outage: KillMode=control-group so a stopped unit takes its
# agents and their spawned test servers with it; a probe deliberately OUTSIDE
# the contained slice so the supervisor outlives what it watches;
# StartLimitBurst so a restart loop cannot deepen an OOM storm;
# SuccessExitStatus=0 1 because a degraded verdict is a report and not a unit
# failure; --db-filename because without it every reboot silently discards
# in-flight workflow history (D-006). This epic generalises that prior art into
# something the engine installs on any host. plan.md quotes it line by line.
#
# It also does something the prior art does and systemd cannot: reap orphaned
# test-server processes. On 2026-08-11 8,131 of them held 123 GiB and OOM-killed
# the host. That capability is FR-006 here so that adopting engine-generated
# units cannot silently drop it.
depends_on_landed: [033-ergane-install, 041-escalation-workflow]
---

# Feature Specification: Supervised services

**Feature Branch**: `042-supervised-services`

**Created**: 2026-08-13

**Status**: Draft

**Input**: Operator direction from the 2026-08-11 provisioning session —
Temporal in `managed` mode means "ergane installs a recommended way", and
`ergane worker install` puts the worker under the same contract — together with
the standing supervision priority recorded after a five-hour undetected Temporal
death on 2026-08-11.

## The principle

Supervision is not an option of managed mode; it is what managed mode *means*.
A service ergane installs and does not watch is a worse outcome than a service
the operator installs themselves, because it carries ergane's implied promise.
The incident this clause exists to prevent is specific and recorded: Temporal
died and nothing noticed for five hours, and separately 8,131 orphaned
test-server processes took a 121 GiB host down. Both were found by a human
looking, which is not a supervision strategy.

## The one alert that can never be a workflow

041 made escalation a Temporal workflow, which is right for every escalation
except one: the alert that says Temporal is down cannot be hosted by the thing
it reports dead. The supervision probe therefore calls the messenger adapter
**directly** — out-of-band, fire-and-forget, no lifecycle, a local log as its
only record. This is precisely why 041 FR-002 requires the adapter to be a
plain library callable with no Temporal client and no workflow context: this
epic is that caller, and it runs when Temporal is gone.

## What already runs, by hand, and is not in this repository

The operator's host is already supervised this way. Five unit files and a probe
script were hand-written on 2026-08-12 and live in a separate repository. They
work, they encode real lessons, and they are unportable — every `ExecStart`
names an absolute path inside that other repo, and the alert path is `curl`
against the Telegram API with credentials grepped out of a sops-decrypted file.

This epic's job is not to invent supervision. It is to make the engine produce
that same supervision, for any host, with the alert path going through 041's
adapter instead of a hardcoded `curl`, and with no path outside the operator's
own installation. `plan.md` treats the prior art as the specification of intent
and quotes it.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - An alert can reach the operator when Temporal is dead (Priority: P1)

As a supervision probe, I report a degraded stack by calling the configured
messenger adapter directly. I start no workflow, hold no lifecycle, and touch
no Temporal client — because the thing I am reporting may be Temporal.

**Why this priority**: every other story in this spec raises alerts through
this path, and it is the one capability that must work when the rest of the
stack does not.

**Independent Test**: with Temporal unreachable, a degraded verdict still
reaches the configured adapter; the call records locally; nothing raises.

**Evidence rule for every scenario below**: the judge is given the diff and
these criteria — never a terminal, never the base tree (constitution VIII).
Runtime claims are met by tool output pasted verbatim into a comment block in
the test file.

**Acceptance Scenarios**:

1. **Given** no Temporal server reachable at the configured address, **When**
   the out-of-band alert path sends a degraded report, **Then** it is delivered
   through the configured adapter and recorded in a local log, and the diff
   contains a test that runs with no Temporal client constructed at all.
2. **Given** the adapter itself failing, **When** an alert is sent, **Then** the
   failure is logged and nothing raises — a supervisor that crashes on a failed
   send has stopped supervising.
3. **Given** the out-of-band path, **When** the diff is inspected, **Then** it
   starts no workflow, creates no escalation record requiring an answer, and
   expects no reply — it is fire-and-forget, and silence from the operator is
   not a state it tracks.
4. **Given** an alert, **When** it is rendered, **Then** it names the service,
   the observed condition, and the duration — a page that says only "degraded"
   sends the operator to a terminal to find out what this spec already knew.

---

### User Story 2 - The worker installs, is contained, and is uninstallable (Priority: P1)

As an operator, `ergane worker install` puts the worker and the notify bridge
under systemd user units, inside a memory- and task-bounded slice, on paths
inside my own installation. `ergane worker uninstall` removes what install
created and nothing else.

**Why this priority**: the worker is what the operator runs today by hand, the
containment lessons are already paid for, and this story is where they become
portable. It rides ahead of managed Temporal because the worker is the process
whose children leak.

**Split note**: this story and US4 were one story until 2026-08-16. Built whole
it measured **103,057 bytes against a 61,440 ceiling — 1.68x** — and the
implementer reported that rather than trimming checks to fit, which is the
correct behaviour and the reason the split is along a seam the code already had
(`SupervisedUnit` versus `StackProbe`) rather than along a byte count. US4 owns
the probe. The dependency runs one way: the probe reads the unit names, never
the reverse.

**The probe unit's text belongs to US4, not here.** Generating a
`ergane-probe.service` that execs a module US4 has not written yet is a live
defect, not a stub: Python exits 1 on `ModuleNotFoundError`, 1 is *inside* the
generated `SuccessExitStatus=0 1`, and the timer would read green while
supervising nothing. That is the exact failure FR-015 exists to end, shipped by
the story that forbids it.

**Independent Test**: after install, the units are active and enabled with
linger; stopping the unit takes its whole process tree; uninstall leaves the
config file and every unit the engine did not write untouched.

**Evidence rule for every scenario below**: as US1.

**Acceptance Scenarios**:

1. **Given** a provisioned host, **When** `ergane worker install` runs, **Then**
   worker and bridge units are active and enabled, linger is enabled for the
   user, and every generated unit references only paths inside the operator's
   own installation — no path into any other repository.
2. **Given** the worker running with agent subprocesses beneath it, **When** the
   unit is stopped, **Then** the entire process tree stops with it — a bare kill
   of the worker pid is what leaves orphans on PID 1, and the generated unit
   must make that impossible.
3. **Given** a repeatedly failing unit, **When** it restarts, **Then** the
   restart rate is bounded — a restart loop during a memory storm deepens it,
   and giving up loudly beats flapping quietly.
4. **Given** installed units, **When** `ergane worker uninstall` runs, **Then**
   exactly the units install created are removed, the config file is untouched,
   and any pre-existing unit of the same name that the engine did not write is
   reported rather than deleted.

---

### User Story 4 - The probe watches, reports, and never remediates (Priority: P1)

As a supervision timer, I read the state of the units US2 installed, reap the
orphaned test-server processes systemd cannot, and report degradation through
US1's alert path — without restarting anything, because systemd owns restarts.

**Why this priority**: P1 alongside US2 because units nobody watches are half
the value, and the orphan reaping is the one thing here systemd cannot do for
itself — it is the 2026-08-11 outage class, where 8,131 orphaned test-server
processes consumed 123 GiB and OOM-killed the host.

**Split note**: see US2. This half carries `probe.py`, the probe unit and timer
text, and the `PROBE_UNIT` / `PROBE_TIMER` constants, because a probe unit
without the module it execs is worse than no probe unit.

**Independent Test**: a seeded orphan population is reaped and reported; a dead
unit raises an alert naming the unit and its outage duration; a second identical
healthy run is silent; a probe that cannot deliver its alert exits non-zero.

**Evidence rule for every scenario below**: as US1.

**Acceptance Scenarios**:

1. **Given** orphaned test-server processes on the host, **When** the probe
   next fires, **Then** they are reaped, the count is reported, and a count
   above the configured threshold raises an alert through US1 — this is the
   2026-08-11 outage class, and it is the one thing the probe does that systemd
   cannot.
2. **Given** the worker process killed, **When** the probe next fires against a
   dead unit, **Then** an alert is delivered naming the unit and the outage
   duration, while the unit is still down.
3. **Given** a probe firing on its interval against an unchanged healthy stack,
   **When** it completes, **Then** no alert is sent — alerts are edge-triggered
   on a status change — **and** a periodic heartbeat is sent on its own much
   longer interval, so operator silence stays distinguishable from a dead probe.
   A test that observes only one run cannot tell edge-triggered from
   always-silent; the second identical run is the assertion.
4. **Given** a degraded stack, **When** the probe runs, **Then** it reports and
   does not restart anything — systemd owns restarts, and restarting into an
   already-dying host deepens a memory storm rather than ending it.
5. **Given** a probe that cannot deliver its alert at all, **When** it runs,
   **Then** it says so loudly in its own output and exits non-zero — a probe
   that cannot escalate is otherwise indistinguishable from a healthy floor,
   which is the exact failure this unit exists to end.

---

### User Story 3 - Managed Temporal is installed supervised or not at all (Priority: P2)

As an operator choosing `temporal.mode = "managed"`, ergane installs a Temporal
server under a systemd user unit with a bounded restart policy and persistent
storage, inside the same contained slice, watched by the same probe. Choosing
`external` installs nothing and says so: the remote server's uptime is
explicitly the operator's contract.

**Why this priority**: 033 refuses `managed` at parse time until this lands.
This story is what turns that refusal into a mode.

**Independent Test**: with managed mode selected, the Temporal unit is active
and its database file persists across a restart with workflow history intact;
killing the process produces a restart and, past the probe interval, an alert
delivered while the service is still down; with external mode selected, no unit
exists and verify's finding says whose contract the uptime is.

**Evidence rule for every scenario below**: as US1.

**Acceptance Scenarios**:

1. **Given** managed mode selected, **When** install completes, **Then** the
   Temporal unit and the probe timer are both active, linger is enabled, and
   033's parse-time refusal of `managed` no longer applies.
2. **Given** a managed Temporal server with workflow history, **When** the unit
   is restarted, **Then** the history survives — persistence is configured, and
   the diff shows a test that writes history, restarts, and reads it back.
3. **Given** the managed Temporal process killed, **When** the probe next fires
   against a dead service, **Then** an alert is delivered through US1's
   out-of-band path — while Temporal is still down — naming the service and the
   duration.
4. **Given** external mode selected, **When** install completes, **Then** no
   unit is installed, nothing on the host supervises the remote server, and the
   verify finding says so explicitly rather than passing silently.
5. **Given** a host without systemd user-session support, **When** managed mode
   is requested, **Then** it is refused at walkthrough time naming the
   constraint — not discovered at unit-install time, half-way through.

---

### Edge Cases

- A unit file of the same name already exists and the engine did not write it:
  reported, never overwritten — the operator's hand-written unit may be the one
  keeping their host alive.
- The probe runs while the slice is under memory pressure: the probe must not
  be inside the slice it watches, or it is reclaimed alongside the leak it
  exists to report.
- The probe's own alert path is misconfigured: it logs locally and exits
  non-zero without failing the unit — a degraded verdict is a report.
- `uninstall` run while an epic is in flight: refused naming the epic, on the
  same grounds as every other refusal in the provisioning set.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Supervision alerts MUST have an out-of-band delivery path that
  does not touch Temporal: the probe calls the messenger adapter directly,
  fire-and-forget, with a local log as its only record. An alert about a dead
  orchestrator MUST NOT be hosted by the orchestrator.
- **FR-002**: The out-of-band path MUST NOT raise on a failed send, MUST NOT
  create anything requiring an answer, and MUST name the service, the observed
  condition and the duration in the alert.
- **FR-003**: `ergane worker install` MUST install worker and notify-bridge
  systemd user units, enable linger, and place both in a memory- and
  task-bounded slice. Generated units MUST reference only paths inside the
  operator's own installation.
- **FR-004**: Generated service units MUST stop their entire process tree when
  the unit stops, so agents, gate subprocesses and anything they spawned are
  taken with them.
- **FR-005**: Generated service units MUST bound their restart rate rather than
  restarting without limit.
- **FR-006**: The probe MUST detect and reap orphaned test-server processes,
  report the count, and alert above a configured threshold. The probe MUST NOT
  run inside the slice it watches.
- **FR-007**: The probe MUST alert when a supervised unit is not active, naming
  the unit and the outage duration, through FR-001's path.
- **FR-008**: `ergane worker uninstall` MUST remove exactly the units install
  created, leave the config file untouched, and report rather than delete any
  same-named unit the engine did not write.
- **FR-009**: `temporal.mode = "managed"` MUST install a Temporal server unit
  with persistent storage whose workflow history survives a restart, under the
  same slice, restart bound and probe coverage as FR-003 through FR-007. It MUST
  clear 033's parse-time refusal of that mode.
- **FR-010**: `temporal.mode = "external"` MUST install no unit and MUST render
  a verify finding stating that the remote server's uptime is the operator's
  contract.
- **FR-011**: Managed mode MUST be refused at walkthrough time on a host
  without systemd user-session support, naming the constraint.
- **FR-012**: `uninstall` MUST refuse while an epic is in flight, naming the
  epic.
- **FR-013**: Alerts MUST be edge-triggered on a status change, and a heartbeat
  MUST be sent on its own much longer interval so that operator silence stays
  distinguishable from a dead probe. A probe firing every few minutes MUST NOT
  alert every few minutes.
- **FR-014**: The probe MUST NOT restart, kill or otherwise remediate any
  supervised service — systemd owns restarts, and remediating into an
  already-degraded host deepens the failure. Reaping orphaned processes
  (FR-006) is the sole exception, because nothing else in the system will ever
  reap them.
- **FR-015**: A probe that cannot deliver its alert MUST report that failure in
  its own output and exit non-zero, never silently — an unescalatable probe is
  indistinguishable from a healthy floor.

### Key Entities

- **SupervisedUnit**: one generated systemd user unit — its slice, restart
  bound, kill semantics, and the paths it references.
- **StackProbe**: the periodic check — unit liveness, memory headroom, orphan
  count — rendering a verdict and, when degraded, an out-of-band alert.
- **OutOfBandAlert**: a fire-and-forget message through the messenger adapter
  with no Temporal involvement and no expected reply.

## Success Criteria *(mandatory)*

- **SC-001**: With managed Temporal installed, killing the Temporal process
  produces a restart, and an outage extended past the probe interval produces
  an alert through the configured adapter *while Temporal is still down* —
  proving the alert path does not depend on the thing it monitors. Measured,
  not assumed.
- **SC-002**: Stopping a generated worker unit that has agent subprocesses
  beneath it leaves no process behind — measured by process count before and
  after, pasted into the diff.
- **SC-003**: A seeded orphan population is reaped by the probe and reported,
  and a population above the threshold raises an alert.
- **SC-004**: A managed Temporal unit **persists its history across a restart**,
  proven three ways that are each obtainable: the generated unit declares
  persistent storage rather than in-memory, asserted on the unit text; a Temporal
  instance started from that same generated configuration, on a scratch port and
  a scratch data directory, still holds a written workflow after a stop and
  start; and the unit's `ExecStart` names a data path inside the operator's own
  installation rather than a temporary one.

  **Not** "restarted mid-epic on this host". That was the original wording and no
  implementer can satisfy it: the only managed Temporal here is
  `ergane-temporal.service`, the server the factory itself runs on, and
  restarting it mid-epic means taking an outage on a live floor to produce
  evidence. Repaired 2026-08-16, before US3 was dispatched, after the US2
  implementer found and reported the identical defect one criterion up in
  SC-002 — the third success criterion this week to demand evidence that could
  only be obtained by breaking the thing being measured. What SC-004 was
  defending is unchanged and is what the wording above now states.
- **SC-005**: `uninstall` on a host with one engine-written unit and one
  hand-written unit of a colliding name removes the first and reports the
  second, leaving it on disk.
- **SC-006**: No generated unit references a path outside the operator's own
  installation — asserted by scanning the generated unit text.

## Assumptions

- 033's config parser has landed (2026-08-15): `temporal.mode` and the managed
  refusal exist at `factory/controlplane/config.py` (`Temporal` block `:146`,
  `RULE_TEMPORAL_MANAGED_NOT_IMPLEMENTED` `:54`). The remaining 033 stories
  land ahead of this epic per `depends_on_landed`.
- 041 lands first and provides the messenger adapter as a plain library
  callable with no Temporal client (041 FR-002).
- 011-agent-sandbox has landed: agents — and gates — run inside a
  pid-namespaced boundary that dies with its attempt, so the orphan class the
  probe reaps (FR-006) is narrowed to non-attempt sources: operator-run
  suites, boundary-disabled control runs, and anything predating 011. The reap
  stays, as the backstop rather than the primary defense — the 2026-08-11
  outage taught that a class believed closed still deserves a net.
- systemd with user sessions is the supervision substrate; hosts without it can
  use every feature except managed mode and `worker install`.
- The operator's existing hand-written units are prior art, not a dependency:
  this epic generates its own and never edits theirs.

## Out of Scope

- Non-systemd supervision substrates.
- Multi-host control planes.
- Migrating the operator's existing hand-written units — this epic generates
  its own; adopting them is an operator action.
- Anything about what an escalation says or how it is answered (041).
- Detecting a live worker running stale code after a factory self-landing
  (`hardening/self-landing-stales-the-running-worker`, open critical): the
  worker stays *active* while every workflow task fails, so unit-liveness
  supervision cannot see it. It needs its own mechanism — restart-on-landing
  or task-failure detection — and folding it in here would give this epic a
  Temporal-client dependency its alert path exists to avoid.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-003, FR-004, FR-005, FR-008, FR-012]
US4:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-006, FR-007, FR-013, FR-014, FR-015]
US3:
  depends_on: []
  depends_on_merged: [US2, US4]
  implements: [FR-009, FR-010, FR-011]
```
